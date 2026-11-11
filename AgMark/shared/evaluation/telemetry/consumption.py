"""Versioned attempt consumption and deterministic treatment measurements.

Adapters extract source evidence. This boundary validates common roles and
aggregates retained attempts; it never interprets provider logs or correctness.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import datetime
import base64
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import threading

from ...runtime.identity import canonical_sha256, sha256_bytes
from .model import TelemetryError

ATTEMPT_MEASUREMENTS = "arcgrav.telemetry:attempt-measurements"
MEASUREMENT_SCHEMA_ID = "arcgrav.shared.schema.attempt-measurements"
MEASUREMENT_SCHEMA_VERSION = "1.0.0"
TOKEN_ROLES = ("total_tokens", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")
RESOURCE_ROLES = (*TOKEN_ROLES, "duration", "tool_calls", "failed_tool_calls", "cost")


class _ActiveProjectionCache:
    """Bounded immutable JSON snapshots; input bytes are verified before lookup."""
    def __init__(self, *, max_bytes=64 * 1024 * 1024, max_entries=4):
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.entries = OrderedDict()
        self.byte_length = 0
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            encoded = self.entries.get(key)
            if encoded is not None:
                self.entries.move_to_end(key)
        return json.loads(encoded) if encoded is not None else None

    def put(self, key, value):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(encoded) > self.max_bytes:
            return
        with self.lock:
            previous = self.entries.pop(key, None)
            self.byte_length -= len(previous) if previous is not None else 0
            self.entries[key] = encoded
            self.byte_length += len(encoded)
            while len(self.entries) > self.max_entries or self.byte_length > self.max_bytes:
                _, removed = self.entries.popitem(last=False)
                self.byte_length -= len(removed)


_ACTIVE_PROJECTION_CACHE = _ActiveProjectionCache()


def unavailable_measurement(role, reason, *, source="not_observed", unit=None):
    return {"value": None, "availability": "unavailable", "unit": unit or ("tokens" if role in TOKEN_ROLES else "calls" if "calls" in role else "ms" if role == "duration" else "currency"),
            "kind": "unavailable", "source": source, "meaning": reason,
            "method": "none", "evidence_references": [], "details": {"reason": reason}}


def observed_measurement(value, *, unit, kind, source, meaning, method, evidence_references, details=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise TelemetryError("consumption must be finite and nonnegative")
    return {"value": value, "availability": "available", "unit": unit, "kind": kind,
            "source": source, "meaning": meaning, "method": method,
            "evidence_references": list(evidence_references), "details": dict(details or {})}


def attempt_measurements(*, runtime_version, source_identity, tokens=None, tool_events=(), trace_complete=False,
                         source="registered runtime", counting_rules=None):
    """Create independently available roles, retaining source subset definitions.

    Tool identities are scoped by attempt. Proposed events do not count; events
    sharing an invocation identity must agree on tool and terminal outcome.
    """
    roles = {role: unavailable_measurement(role, "Source does not expose this component.", source=source) for role in TOKEN_ROLES}
    roles["cost"] = unavailable_measurement("cost", "No compatible billing usage and retained pricing evidence.")
    for role, value in (tokens or {}).items():
        if role not in TOKEN_ROLES:
            raise TelemetryError("unknown token role")
        roles[role] = observed_measurement(value, unit="tokens", kind="runtime_counter", source=source,
            meaning=(counting_rules or {}).get(role, "Source-defined runtime counter; billing meaning unestablished."),
            method="registered adapter extraction@1.0.0", evidence_references=(source_identity,),
            details={"runtime_version": runtime_version, "extraction_version": MEASUREMENT_SCHEMA_VERSION,
                     "counting_rules": dict(counting_rules or {})})
    value = {"schema_id": MEASUREMENT_SCHEMA_ID, "schema_version": MEASUREMENT_SCHEMA_VERSION,
             "extensions": {}, "runtime_version": runtime_version, "roles": roles,
             "tool_events": list(tool_events), "tool_trace_complete": trace_complete,
             "source_identity": source_identity}
    validate_attempt_measurements(value)
    return value


def validate_attempt_measurements(value):
    from ...validation import CatalogEntry, SchemaIdentity, validate_cataloged_document
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "attempt_measurements.schema.json").read_text())
    entry = CatalogEntry(SchemaIdentity(MEASUREMENT_SCHEMA_ID, MEASUREMENT_SCHEMA_VERSION), schema["$id"], "AgMark/shared/schemas/attempt_measurements.schema.json")
    errors = validate_cataloged_document(value, schema_document=schema, entry=entry, source_id=ATTEMPT_MEASUREMENTS)
    if errors:
        raise TelemetryError("invalid common attempt measurements: " + errors[0].message)
    from .session_metrics import SESSION_METRICS, validate_session_metrics
    session = value["extensions"].get(SESSION_METRICS)
    if session is not None:
        validate_session_metrics(session)
    for role, measurement in value["roles"].items():
        numeric = measurement["value"]
        if numeric is not None and (isinstance(numeric, bool) or not math.isfinite(numeric)):
            raise TelemetryError("invalid consumption number")
        if measurement["availability"] in {"available", "partial"}:
            if numeric is None or not measurement["evidence_references"]:
                raise TelemetryError("observed consumption requires a value and source evidence")
            if role in TOKEN_ROLES and type(numeric) is not int:
                raise TelemetryError("token counters must be integers")
            if role in TOKEN_ROLES and measurement["unit"] != "tokens":
                raise TelemetryError("token roles require token units")
            if role in TOKEN_ROLES and measurement["kind"] not in {"runtime_counter", "provider_reported_usage", "offline_token_estimate"}:
                raise TelemetryError("token role has unsupported measurement meaning")
            if role == "cost" and measurement["kind"] not in {"provider_reported_cost", "estimated_cost"}:
                raise TelemetryError("cost role requires reported or estimated billing meaning")
            if role in TOKEN_ROLES and measurement["kind"] == "runtime_counter" and measurement["details"].get("runtime_version") != value["runtime_version"]:
                raise TelemetryError("counter runtime provenance mismatch")
        elif numeric is not None:
            raise TelemetryError("unavailable consumption must have null value")
    # Subsets are retained, never added again to total or parent components.
    roles = value["roles"]
    for subset, parent in (("cached_input_tokens", "input_tokens"), ("reasoning_tokens", "output_tokens")):
        child, outer = roles.get(subset, {}), roles.get(parent, {})
        if child.get("value") is not None and outer.get("value") is not None:
            rules = outer.get("details", {}).get("counting_rules", {})
            if rules.get(subset + "_subset_of_" + parent) == "true" and child["value"] > outer["value"]:
                raise TelemetryError("token subset exceeds parent component")
    _tool_counts(value)
    cost = roles["cost"]
    if cost["availability"] in {"available", "partial"} and cost["kind"] == "estimated_cost":
        try:
            source = base64.b64decode(cost["details"]["pricing_source_base64"], validate=True)
            expected = estimate_component_cost(roles, pricing=cost["details"]["pricing"],
                pricing_evidence=source, input_includes_cached=cost["details"]["input_includes_cached"])
        except (KeyError, ValueError, TypeError) as exc:
            raise TelemetryError("estimated cost lacks reconstructable price evidence") from exc
        if cost != expected:
            raise TelemetryError("estimated cost does not reconstruct from retained components and price")
    return value


def _compatibility(measurement):
    """Only declared source meaning and comparison dimensions can be pooled."""
    details = measurement.get("details", {})
    return (measurement["kind"], measurement["source"], measurement["unit"],
            measurement["meaning"], details.get("runtime_version"),
            json.dumps(details.get("counting_rules", {}), sort_keys=True),
            json.dumps(details.get("compatibility", {}), sort_keys=True),
            details.get("input_includes_cached"),
            json.dumps(details.get("pricing", {}), sort_keys=True))


def _attempt_envelopes(document):
    attempts = document.get("attempts", ())
    attempt_ids = [a["attempt"] for a in attempts]
    if any(type(n) is not int or n < 1 for n in attempt_ids) or len(set(attempt_ids)) != len(attempt_ids):
        raise TelemetryError("invalid or duplicate attempt identity")
    extensions = document.get("extensions", {})
    extension = extensions.get(ATTEMPT_MEASUREMENTS)
    indexed = extensions.get("arcgrav.telemetry:attempt-series")
    if extension is not None:
        validate_attempt_measurements(extension)
    if indexed is not None:
        if not isinstance(indexed, Mapping) or set(indexed) != {str(n) for n in attempt_ids}:
            raise TelemetryError("attempt series must identify every exact retained attempt")
        for envelope in indexed.values():
            validate_attempt_measurements(envelope)
        if extension is not None and (len(attempts) != 1 or indexed[str(attempt_ids[0])] != extension):
            raise TelemetryError("conflicting attempt measurement envelopes")
    return [(a, indexed[str(a["attempt"])] if indexed is not None else extension if len(attempts) == 1 else None) for a in attempts]


def _tool_counts(value):
    invocations = {}
    for event in value["tool_events"]:
        if event["status"] == "proposed":
            continue
        identity = event["invocation_id"]
        prior = invocations.get(identity)
        if prior and prior["tool_id"] != event["tool_id"]:
            raise TelemetryError("one invocation cannot identify different tools")
        if prior and prior["status"] in {"completed", "failed"}:
            if event["status"] in {"completed", "failed"} and prior["status"] != event["status"]:
                raise TelemetryError("conflicting terminal tool outcomes")
            continue
        invocations[identity] = event
    complete = value["tool_trace_complete"]
    known = sum(e["status"] in {"completed", "failed"} for e in invocations.values())
    evidence = sorted({ref for e in value["tool_events"] for ref in e["evidence_references"]}) or [value["source_identity"]]
    counts = {}
    for role, number, fully_known in (("tool_calls", len(invocations), complete),
                                      ("failed_tool_calls", sum(e["status"] == "failed" for e in invocations.values()), complete and known == len(invocations))):
        if not invocations and not complete:
            counts[role] = unavailable_measurement(role, "Tool invocation trace is absent or incomplete.")
        else:
            counts[role] = observed_measurement(number, unit="calls", kind="invocation_count", source="registered tool-event stream",
                meaning="Actual invocations, including failures and retries; deduplicated within attempt.",
                method="distinct invocation identity; observed terminal classification", evidence_references=evidence,
                details={"runtime_version": value["runtime_version"], "trace_complete": complete,
                         "known_terminal_outcomes": known, "invocations": list(invocations.values())})
            if not fully_known:
                counts[role]["availability"] = "partial"
    return counts


def _timestamp(value):
    if value is None:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise TelemetryError("invalid attempt timestamp") from exc
    if result.tzinfo is None:
        raise TelemetryError("attempt timestamps must identify their clock offset")
    return result


def aggregate_treatment_measurements(observations, *, generation_id, planned_observations, boundary_fingerprint=None):
    """Produce all treatment roles from exact generation/boundary input evidence.

    planned_observations maps treatment IDs to authorized observation counts.
    Each observation must carry its exact retained artifact SHA-256 alongside it.
    """
    groups = {key: [] for key in planned_observations}
    capture_groups = {key: [] for key in planned_observations}
    capture_exclusions = {key: [] for key in planned_observations}
    capture_profiles = {key: set() for key in planned_observations}
    seen = set()
    session_threads = set()
    for document, evidence_identity in observations:
        if document.get("accepted_generation_id") != generation_id:
            raise TelemetryError("measurement generation mismatch")
        if boundary_fingerprint is not None and document.get("execution_boundary_fingerprint") != boundary_fingerprint:
            raise TelemetryError("measurement boundary mismatch")
        identity = document["observation_id"]
        if identity in seen:
            raise TelemetryError("duplicate observation measurement input")
        seen.add(identity)
        treatment = document["treatment_id"]
        if treatment not in groups:
            raise TelemetryError("unplanned treatment measurement")
        from ...telemetry.normalization import reconstruct_capture_extensions, _runtime_capture_identity
        capture = None
        try:
            capture = reconstruct_capture_extensions(document.get("extensions", {}))
            if capture is not None:
                if len(document.get("attempts", ())) != 1:
                    raise ValueError("Invocation capture lacks exact per-attempt assignment for a multi-attempt observation.")
                if capture.get("invocation_id") != identity:
                    raise ValueError("Invocation capture does not belong to the owning observation.")
                runtime = capture.get("runtime", {})
                captured_boundary = runtime.get("accepted_boundary_fingerprint")
                observation_boundary = document.get("execution_boundary_fingerprint")
                if (isinstance(captured_boundary, str) and captured_boundary
                        and isinstance(observation_boundary, str) and observation_boundary
                        and captured_boundary != observation_boundary):
                    raise ValueError("Invocation capture execution boundary differs from the owning observation.")
                execution = document.get("extensions", {}).get("arcgrav.runner:execution", {})
                framing = execution.get("request_framing", {}) if isinstance(execution, Mapping) else {}
                expected_frame = framing.get("sha256") if isinstance(framing, Mapping) and framing.get("availability") == "observed" else None
                captured_frame = runtime.get("framed_request_sha256")
                if (isinstance(captured_frame, str) and captured_frame
                        and isinstance(expected_frame, str) and expected_frame
                        and captured_frame != expected_frame):
                    raise ValueError("Invocation capture framed request differs from retained runner request-framing evidence.")
                capture_groups[treatment].append(capture)
        except (ValueError, KeyError, TypeError) as exc:
            capture_exclusions[treatment].append({"observation_id": identity, "evidence_reference": evidence_identity,
                                                  "reason": str(exc), "authority": "original"})
            capture = None
        declared_capture = document.get("extensions", {}).get("agmark.telemetry:capture")
        profile = declared_capture.get("profile") if isinstance(declared_capture, dict) else None
        runtime_identity = _runtime_capture_identity(declared_capture.get("runtime", {})) if isinstance(declared_capture, dict) else None
        capture_condition = {"profile": profile, "runtime": runtime_identity} if isinstance(declared_capture, dict) else None
        capture_profiles[treatment].add(json.dumps(capture_condition, sort_keys=True))
        # The v1 extension describes one attempt; retries require attempt-indexed
        # envelopes, rather than incorrectly reusing the last attempt's usage.
        for attempt, measured in _attempt_envelopes(document):
            if measured is not None and profile is not None:
                measured = deepcopy(measured)
                role_sets = [measured["roles"]]
                from .session_metrics import SESSION_METRICS
                if SESSION_METRICS in measured.get("extensions", {}):
                    role_sets.append(measured["extensions"][SESSION_METRICS]["roles"])
                for role_set in role_sets:
                    for measurement in role_set.values():
                        compatibility = measurement.setdefault("details", {}).setdefault("compatibility", {})
                        compatibility["capture_profile"] = profile
                        compatibility["capture_runtime"] = runtime_identity
            if measured is not None:
                from .session_metrics import SESSION_METRICS
                session = measured.get("extensions", {}).get(SESSION_METRICS)
                thread_id = session.get("thread_id") if session is not None else None
                if thread_id is not None:
                    session_key = (document["observation_id"], attempt.get("attempt"), thread_id)
                    if session_key in session_threads:
                        raise TelemetryError("one persisted session cannot be reused across trial attempts")
                    session_threads.add(session_key)
            groups[treatment].append((document, attempt, measured, evidence_identity))
    result = {}
    for treatment, attempts in groups.items():
        planned = planned_observations[treatment]
        if type(planned) is not int or planned < 0:
            raise TelemetryError("invalid planned observation count")
        observed = len({x[0]["observation_id"] for x in attempts})
        if observed > planned:
            raise TelemetryError("observed measurements exceed authorized plan")
        roles = {}
        for role in (*TOKEN_ROLES, "tool_calls", "failed_tool_calls", "cost"):
            entries = []
            for _, _, envelope, ref in attempts:
                if envelope is None:
                    continue
                measurement = (_tool_counts(envelope).get(role) if "calls" in role else envelope["roles"].get(role))
                if measurement and measurement["value"] is not None:
                    entries.append((measurement, ref))
            if not entries:
                roles[role] = unavailable_measurement(role, "No measured compatible evidence for this role.")
            else:
                compatibility = {_compatibility(m) for m, _ in entries}
                if len(compatibility) != 1:
                    roles[role] = unavailable_measurement(role, "Incompatible measurement sources or counting/billing rules.")
                    roles[role]["availability"] = "non_comparable"
                else:
                    first = entries[0][0]
                    complete = observed == planned and len(entries) == len(attempts) and all(m["availability"] == "available" for m, _ in entries)
                    roles[role] = observed_measurement(sum(m["value"] for m, _ in entries), unit=first["unit"], kind=first["kind"],
                        source=first["source"], meaning=first["meaning"], method="sum compatible measured attempts including failures/retries",
                        evidence_references=sorted({ref for _, ref in entries} | {ref for m, _ in entries for ref in m["evidence_references"]}),
                        details={**{key: first["details"][key] for key in ("runtime_version", "counting_rules", "compatibility", "pricing") if key in first["details"]},
                                 "execution_boundary_fingerprint": boundary_fingerprint,
                                 "inputs": [dict(m) for m, _ in entries], "coverage": {"measured_attempts": len(entries), "observed_attempts": len(attempts), "observed_observations": observed, "planned_observations": planned}})
                    roles[role]["availability"] = "available" if complete else "partial"
        starts = [_timestamp(a.get("started_at")) for _, a, _, _ in attempts]
        ends = [_timestamp(a.get("completed_at")) for _, a, _, _ in attempts]
        if starts and all(x is not None for x in starts) and any(x is not None for x in ends):
            if any(end is not None and end < start for start, end in zip(starts, ends)):
                raise TelemetryError("attempt terminal time precedes start")
            first, last = min(starts), max(e for e in ends if e is not None)
            roles["duration"] = observed_measurement((last-first).total_seconds()*1000, unit="ms", kind="wall_clock_duration", source="runner UTC clock",
                meaning="First authorized treatment attempt start to last terminal; includes waiting/retries; excludes framework work.",
                method="last terminal minus first start", evidence_references=sorted({ref for _, _, _, ref in attempts}),
                details={"started_at": first.isoformat(), "completed_at": last.isoformat(), "clock": "UTC wall clock", "observed_observations": observed, "planned_observations": planned})
            if observed != planned or any(e is None for e in ends):
                roles["duration"]["availability"] = "partial"
                roles["duration"]["details"]["state"] = "elapsed/incomplete"
        else:
            roles["duration"] = unavailable_measurement("duration", "Complete authorized timing boundaries unavailable.")
        from .session_metrics import aggregate_session_metrics
        session_roles, sessions = aggregate_session_metrics(attempts, observed=observed, planned=planned)
        if sessions:
            roles.update(session_roles)
        from .paired_cache import aggregate_paired_cache
        roles.update(aggregate_paired_cache(attempts, observed=observed, planned=planned,
                                           boundary_fingerprint=boundary_fingerprint))
        value = {"schema_version": "1.0.0", "generation_id": generation_id, "treatment_id": treatment,
                 "boundary_fingerprint": boundary_fingerprint, "roles": roles,
                 "efficiency": {"availability": "unavailable", "reason": "No registered efficiency formula supplied."}}
        if sessions:
            value["sessions"] = sessions
        from .root_cache_policy import project_root_cache_policies
        value["root_cache_policies"] = project_root_cache_policies(attempts)
        if capture_groups[treatment] or capture_exclusions[treatment]:
            from ...telemetry.normalization import aggregate_telemetry
            value["telemetry"] = aggregate_telemetry(capture_groups[treatment])
            value["telemetry"]["exclusions"].extend(capture_exclusions[treatment])
            if capture_exclusions[treatment]:
                value["telemetry"]["availability"] = "partial" if capture_groups[treatment] else "unavailable"
        if len(capture_profiles[treatment]) > 1:
            for role, previous in list(roles.items()):
                roles[role] = unavailable_measurement(role, "Capture profiles or runtime capabilities differ across treatment attempts.", unit=previous["unit"])
                roles[role]["availability"] = "non_comparable"
                roles[role]["details"]["inputs"] = previous.get("details", {}).get("inputs", [])
                roles[role]["evidence_references"] = previous.get("evidence_references", [])
        value["computation_sha256"] = canonical_sha256(value)
        result[treatment] = value
    return result


def retained_run_measurements(run, *, plan=None, store=None):
    """Validate exact accepted observation bytes before measurement projection."""
    from ...adapters.execution import validate_retained_parity_observation
    from ...runtime.orchestration import AcceptedRun, ExecutedRun, RunPlan
    if type(run) not in (AcceptedRun, ExecutedRun) or type(plan) is not RunPlan:
        return {}
    run.revalidate(store)
    if plan.plan_sha256 != run.plan_sha256 or plan.execution_boundary_fingerprint != run.execution_boundary_fingerprint:
        raise TelemetryError("measurement plan identity mismatch")
    planned = {}
    for item in plan.observations:
        planned[item.treatment_id] = planned.get(item.treatment_id, 0) + 1
    records = [r for r in run.artifact_index.artifacts if r.role == "treatment_observation"]
    records_by_digest = {}
    for record in records:
        records_by_digest.setdefault(record.sha256, []).append(record)
    observations = []
    authorized = {item.observation_id: item for item in plan.observations}
    for raw in run.treatment_observations:
        identity = sha256_bytes(raw)
        matches = records_by_digest.get(identity, ())
        if len(matches) != 1:
            raise TelemetryError("measurement bytes lack exact accepted artifact identity")
        record = matches[0]
        if store is not None and store.read_verified(record) != raw:
            raise TelemetryError("retained measurement byte drift")
        document = json.loads(raw)
        validate_retained_parity_observation(document)
        _validate_planned_scope(document, authorized)
        observations.append((document, record.sha256))
    return aggregate_treatment_measurements(observations, generation_id=run.generation_id,
        planned_observations=planned, boundary_fingerprint=run.execution_boundary_fingerprint)


def _validate_planned_scope(document, authorized):
    slot = authorized.get(document.get("observation_id"))
    if slot is None or any(document.get(field) != getattr(slot, field) for field in ("request_id", "case_id", "treatment_id", "repetition")):
        raise TelemetryError("measurement evidence outside exact authorized observation scope")


def estimate_component_cost(roles, *, pricing, pricing_evidence=None, input_includes_cached=True):
    """Compute an estimate only from applicable, observed billing components."""
    required = ("identity", "date", "currency", "source_sha256", "units", "rates")
    if (not isinstance(pricing, Mapping) or any(k not in pricing for k in required)
        or isinstance(pricing["units"], bool) or not isinstance(pricing["units"], (int, float))
        or not math.isfinite(pricing["units"]) or pricing["units"] <= 0
        or any(not isinstance(pricing[k], str) or not pricing[k].strip() for k in ("identity", "date", "currency", "source_sha256"))
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", pricing["source_sha256"])):
        raise TelemetryError("complete retained pricing identity and rates required")
    try:
        datetime.strptime(pricing["date"], "%Y-%m-%d")
    except ValueError as exc:
        raise TelemetryError("invalid pricing date") from exc
    if pricing_evidence is None:
        return unavailable_measurement("cost", "Exact retained pricing source unavailable.")
    if not isinstance(pricing_evidence, bytes) or sha256_bytes(pricing_evidence) != pricing["source_sha256"]:
        raise TelemetryError("pricing source integrity mismatch")
    try:
        source = json.loads(pricing_evidence)
    except (ValueError, UnicodeError) as exc:
        raise TelemetryError("invalid pricing source document") from exc
    if source != {key: value for key, value in pricing.items() if key != "source_sha256"}:
        raise TelemetryError("pricing metadata differs from exact source")
    inputs = {}
    for role in ("input_tokens", "cached_input_tokens", "output_tokens"):
        value = roles.get(role, {})
        if value.get("availability") != "available" or value.get("kind") != "provider_reported_usage":
            return unavailable_measurement("cost", "Applicable billing usage components unavailable.")
        inputs[role] = value["value"]
    contexts = [roles[k].get("details", {}).get("compatibility") for k in inputs]
    from .model import TelemetryCompatibility
    try:
        if any(not isinstance(context, Mapping) for context in contexts):
            raise TelemetryError("missing billing compatibility")
        identities = [TelemetryCompatibility(**context) for context in contexts]
    except (TypeError, TelemetryError):
        return unavailable_measurement("cost", "Applicable billing compatibility unavailable.")
    if (len({context.identity for context in identities}) != 1
        or identities[0].pricing_source != pricing["identity"] or identities[0].currency != pricing["currency"]
        or pricing.get("model_identity") != identities[0].model_identity):
        value = unavailable_measurement("cost", "Incompatible billing components or price applicability.")
        value["availability"] = "non_comparable"
        return value
    if input_includes_cached:
        inputs["input_tokens"] -= inputs["cached_input_tokens"]
        if inputs["input_tokens"] < 0:
            raise TelemetryError("cached billing subset exceeds input")
    rates = pricing["rates"]
    if not isinstance(rates, Mapping) or set(rates) != set(inputs) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in rates.values()):
        raise TelemetryError("invalid component prices")
    return observed_measurement(sum(inputs[k]*rates[k]/pricing["units"] for k in inputs), unit=pricing["currency"],
        kind="estimated_cost", source=pricing["identity"], meaning="Applicable billable components times retained component rates.",
        method="sum(component * rate / price units)", evidence_references=sorted({pricing["source_sha256"]} | {ref for k in inputs for ref in roles[k]["evidence_references"]}),
        details={"pricing": dict(pricing), "pricing_source_base64": base64.b64encode(pricing_evidence).decode("ascii"),
                 "compatibility": dict(contexts[0]), "billable_components": inputs, "input_includes_cached": input_includes_cached})


def registered_resource_efficiency(measurement, *, correct_results, formula):
    """Recomputable registered resource-per-correct-result ratio."""
    from .model import RegisteredEfficiencyFormula
    if type(formula) is not RegisteredEfficiencyFormula:
        raise TelemetryError("registered efficiency authority required")
    if formula.denominator_role != "correct_results" or formula.numerator_role not in RESOURCE_ROLES:
        raise TelemetryError("unsupported registered resource ratio")
    if type(correct_results) is not int or correct_results < 0:
        raise TelemetryError("correct results must be observed nonnegative integer")
    if not correct_results or measurement.get("availability") != "available":
        return unavailable_measurement("efficiency", "Unavailable input or zero correctness denominator.", unit=formula.output_unit)
    return observed_measurement(measurement["value"]/correct_results, unit=formula.output_unit, kind="efficiency",
        source=formula.identity, meaning="Registered resource per correct result.", method="numerator / correct_results",
        evidence_references=measurement["evidence_references"],
        details={"formula": formula.to_dict(), "numerator": measurement["value"], "denominator": correct_results})


def registered_baseline_savings(current, baseline, *, baseline_identity, registration_identity):
    """Registered compatible relative savings, with an explicit baseline."""
    if any(not isinstance(value, str) or not value.strip() for value in (baseline_identity, registration_identity)):
        raise TelemetryError("baseline and registered savings identity required")
    contexts = [entry.get("details", {}) for entry in (current, baseline)]
    if any(not (context.get("execution_boundary_fingerprint") or context.get("compatibility")) for context in contexts):
        return unavailable_measurement("savings", "Baseline comparison context unavailable.", unit="ratio")
    if (_compatibility(current) != _compatibility(baseline)
        or current.get("details", {}).get("execution_boundary_fingerprint") != baseline.get("details", {}).get("execution_boundary_fingerprint")):
        value = unavailable_measurement("savings", "Incompatible baseline.", unit="ratio")
        value["availability"] = "non_comparable"
        return value
    if current.get("availability") != "available" or baseline.get("availability") != "available" or not baseline.get("value"):
        return unavailable_measurement("savings", "Unavailable input or zero baseline.", unit="ratio")
    # Savings can be negative (higher consumption), unlike raw consumption.
    return {"value": (baseline["value"]-current["value"])/baseline["value"], "availability": "available", "unit": "ratio",
            "kind": "efficiency", "source": registration_identity, "meaning": "Registered relative baseline savings.",
            "method": "(baseline - current) / baseline", "evidence_references": sorted(set(current["evidence_references"]+baseline["evidence_references"])),
            "details": {"baseline_identity": baseline_identity, "current": current["value"], "baseline": baseline["value"], "registration_identity": registration_identity}}


def active_treatment_measurements(generation_id, plan, store):
    """Project exact retained bytes; unchanged evidence reuses a bounded snapshot.

    File contents are read and SHA-256 checked on every call. Neither filesystem
    timestamps nor claimed observation/manifest IDs can produce a cache hit.
    """
    from ...adapters.execution import validate_retained_parity_observation
    from ...runtime.orchestration import RunPlan
    if type(plan) is not RunPlan or not isinstance(generation_id, str) or not generation_id:
        raise TelemetryError("active measurement plan/generation required")
    if Path(generation_id).name != generation_id:
        raise TelemetryError("invalid generation path")
    planned = {}
    authorized = {item.observation_id: item for item in plan.observations}
    for item in plan.observations:
        planned[item.treatment_id] = planned.get(item.treatment_id, 0) + 1
    snapshots = []
    from ...runtime.artifacts.archive import archive_path, validate_archive
    target = archive_path(store.root, generation_id)
    if target.exists() or target.is_symlink():
        # Finalized measurements come only from manifest-listed, hash-validated
        # archive members; no loose evidence directories survive finalization.
        from zipfile import ZipFile
        manifest = validate_archive(target)
        prefix = generation_id + "/observation-"
        names = sorted(name for name in manifest["core_files"]
                       if name.startswith(prefix)
                       and name.endswith("/observation.json")
                       and name.count("/") == 2)
        with ZipFile(target) as sealed:
            for name in names:
                raw = sealed.read(name)
                identity = sha256_bytes(raw)
                if identity != manifest["core_files"][name]:
                    raise TelemetryError("retained measurement evidence integrity differs")
                snapshots.append((name, raw, identity))
    else:
        # In-progress runs have a private staging directory until sealed.
        for path in sorted((store.root/generation_id).glob("observation-*/observation.json")):
            raw = path.read_bytes()
            snapshots.append((path.name + "/" + path.parent.name, raw, sha256_bytes(raw)))
    scope = tuple((item.observation_id, item.request_id, item.case_id, item.treatment_id, item.repetition) for item in plan.observations)
    cache_context = (str(store.root.resolve()), generation_id, plan.plan_sha256, plan.execution_boundary_fingerprint,
                     scope, tuple((path, identity) for path, _, identity in snapshots))
    key = (sha256_bytes(json.dumps(cache_context, separators=(",", ":"), ensure_ascii=True).encode()),
           validate_retained_parity_observation)
    cached = _ACTIVE_PROJECTION_CACHE.get(key)
    if cached is not None:
        return cached
    documents = []
    for _, raw, identity in snapshots:
        document = json.loads(raw)
        validate_retained_parity_observation(document)
        _validate_planned_scope(document, authorized)
        documents.append((document, identity))
    snapshots.clear()
    result = aggregate_treatment_measurements(documents, generation_id=generation_id,
        planned_observations=planned, boundary_fingerprint=plan.execution_boundary_fingerprint)
    _ACTIVE_PROJECTION_CACHE.put(key, result)
    return result
