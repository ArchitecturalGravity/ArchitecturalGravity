"""Shared presentation for telemetry; GUI and reports do not parse provider data."""
from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
import json

from .normalization import NORMALIZED_EXTENSION, aggregate_telemetry

SECTIONS = (("tokens_cache", "Tokens / cache"), ("requests_timing", "Requests / timing"),
            ("tools_turns", "Tools / turns"), ("prompts_context", "Prompts / context"),
            ("errors_diagnostics", "Errors / diagnostics"), ("configuration_cost", "Configuration / cost"),
            ("provenance_events", "Provenance / raw events"))


def coverage_summary(coverage):
    """Compact display of retained coverage; the full record remains separate."""
    if not isinstance(coverage, Mapping) or not coverage:
        return "Not recorded"
    if coverage.get("expanded_capture") is False:
        return "Session capture; expanded telemetry unavailable"
    parts = []
    if coverage.get("compatibility_groups", 0) > 1:
        parts.append(f"{coverage['compatibility_groups']} incompatible capture groups")
    for numerator, denominator, label in (
            ("paired_attempts", "observed_attempts", "attempts paired"),
            ("measured_attempts", "observed_attempts", "attempts measured"),
            ("measured_invocations", "observed_invocations", "invocations measured"),
            ("contributing", "eligible", "eligible contributors")):
        if numerator in coverage:
            total = coverage.get(denominator)
            prefix = str(coverage[numerator]) + (f"/{total}" if total is not None else "")
            parts.append(f"{prefix} {label}")
            break
    if "source_families" in coverage:
        parts.append(f"{coverage['source_families']} sources")
        for key, label in (("incomplete_sources", "incomplete"), ("active_sources", "active"), ("disabled_sources", "disabled")):
            if coverage.get(key):
                parts.append(f"{len(coverage[key])} {label}")
    elif "source_sequence" in coverage:
        sequence = coverage.get("source_sequence")
        parts.append(f"Record {sequence}" if sequence is not None else "Retained record")
        identities = coverage.get("identities", {})
        parts.append(f"{len(identities)} " + ("ID" if len(identities) == 1 else "IDs") if identities else "No IDs")
    else:
        state = coverage.get("source_state", coverage.get("state"))
        if state:
            parts.append(str(state).replace("_", " ").capitalize())
        if coverage.get("received_events") is not None:
            parts.append(f"{coverage['received_events']} " + ("event" if coverage["received_events"] == 1 else "events"))
        for key, label in (("dropped", "dropped"), ("rejected", "rejected"), ("parse_errors", "parse errors")):
            if coverage.get(key):
                if key == "parse_errors" and coverage[key] == 1:
                    label = "parse error"
                parts.append(f"{coverage[key]} {label}")
    if not parts and "records" in coverage:
        parts.append(f"{len(coverage['records'])} retained records")
    if coverage.get("partial") and not any("partial" in part.lower() for part in parts):
        parts.insert(0, "Partial")
    if parts:
        return "; ".join(parts)
    if coverage.get("availability"):
        return str(coverage["availability"]).replace("_", " ").capitalize()
    return "See retained details"


def presentation_measurement(role, measurement):
    """Enrich historical and new measurements without changing their authority."""
    value = deepcopy(measurement or {})
    details = value.get("details", {})
    coverage = deepcopy(value.get("coverage", details.get("coverage", {"availability": value.get("availability", "unavailable")})))
    kind = value.get("kind", "unavailable")
    classification = value.get("classification")
    if classification is None:
        classification = "proxy" if kind in {"token_event_proxy", "timing_estimate"} else "estimated" if kind in {"estimated_cost", "offline_token_estimate"} else "derived" if details.get("numerator") is not None or role in {"cache_read_fraction", "uncached_input_tokens"} else "observed"
    return {**value, "id": role, "name": role.replace("_", " ").replace("native metric:", "Metric: "),
            "value": value.get("value"), "unit": value.get("unit", "1"),
            "availability": value.get("availability", "unavailable"),
            "definition": value.get("definition", value.get("meaning", "No measurement definition was retained.")),
            "source": value.get("source", "not_observed"), "classification": classification,
            "coverage": coverage, "coverage_text": coverage_summary(coverage),
            "reason": value.get("reason", details.get("reason", "")),
            "method": value.get("method", "not_observed"),
            "evidence_references": list(value.get("evidence_references", ())),
            "authority": value.get("authority", "original"), "scope": value.get("scope", "retained_attempt")}


def _bounded_preview(value, limit=4096):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True)
    return deepcopy(value) if len(encoded) <= limit else {"preview": encoded[:limit], "omitted_characters": len(encoded) - limit,
                                                        "full_value": "Retained sealed evidence; follow evidence references."}


def _section(role):
    if role.startswith("native_metric:"):
        return "requests_timing"
    if "token" in role or "cache" in role or role == "completed_response_usage_count":
        return "tokens_cache"
    if role in {"prompt_count", "context_window", "prompt_span_minutes", "avg_gap_between_user_prompts_minutes", "average_characters_per_prompt"}:
        return "prompts_context"
    if "tool" in role or role in {"completed_turn_count", "compaction_count"}:
        return "tools_turns"
    if role in {"cost", "profile", "runtime", "configuration"}:
        return "configuration_cost"
    if "error" in role or "aborted" in role or "diagnostic" in role or "contradiction" in role:
        return "errors_diagnostics"
    return "requests_timing"


def _descriptive(role, value, definition, *, source="capture manifest", availability="available", reason="", coverage=None):
    return presentation_measurement(role, {"value": value, "unit": "1", "availability": availability,
        "definition": definition, "source": source, "classification": "observed", "reason": reason,
        "coverage": coverage or {}, "method": "shared telemetry projection@1.0.0", "evidence_references": []})


def _source_summary(document):
    sources = deepcopy(document.get("sources", {}))
    if not sources:
        for invocation in document.get("invocations", ()):
            for key, state in invocation.get("sources", {}).items():
                incoming_state = state.get("state", "unknown")
                current = sources.setdefault(key, {"state": incoming_state, "received_events": 0, "received_bytes": 0,
                    "partial": False, "dropped": 0, "rejected": 0, "parse_errors": 0, "invocations": []})
                current["invocations"].append({"invocation_id": invocation.get("invocation_id"), **state})
                for field in ("received_events", "received_bytes", "dropped", "rejected", "parse_errors"):
                    current[field] += state.get(field, 0) or 0
                current["partial"] = current["partial"] or bool(state.get("partial"))
                if current["state"] != incoming_state:
                    complete_states = {"complete", "sealed", "settled"}
                    current["state"] = ("complete" if {current["state"], incoming_state} <= complete_states else "mixed")
                reasons = dict.fromkeys(item.get("reason") for item in current["invocations"] if item.get("reason"))
                current["reason"] = "; ".join(reasons)
    return sources


def project_telemetry(document):
    """Project normalized evidence or a homogeneous compatible aggregate."""
    provisional = not document.get("sealed", False)
    non_comparable = document.get("availability") == "non_comparable"
    rows = {role: presentation_measurement(role, value) for role, value in document.get("measurements", {}).items()}
    buckets = {key: [] for key, _ in SECTIONS}
    for role, row in rows.items():
        buckets[_section(role)].append(row)
    sources = _source_summary(document)
    problematic = [key for key, source in sources.items() if source.get("partial") or any(source.get(k) for k in ("dropped", "rejected", "parse_errors"))
                   or source.get("state") in {"failed", "partial", "unavailable", "unsupported", "rejected", "settlement_timeout", "mixed"}]
    active = [key for key, source in sources.items() if source.get("state") in {"pending", "starting", "ready", "active", "collecting", "draining", "settling"}]
    complete = bool(document.get("sealed")) and not non_comparable and not problematic and not active and not document.get("exclusions")
    label = "Provisional" if provisional else "Non-comparable" if non_comparable else "Partial" if problematic or active or document.get("exclusions") else "Sealed" if sources else "Session evidence"
    coverage = {"sealed": not provisional, "source_families": len(sources), "incomplete_sources": problematic,
                "active_sources": active, "disabled_sources": [key for key, value in sources.items() if value.get("state") == "disabled"]}
    if non_comparable:
        coverage["compatibility_groups"] = len(document.get("compatibility_groups", ()))
    completeness = _descriptive("telemetry_completeness", label,
        "Capture completeness describes source health and sealing, independently of benchmark score.",
        availability="non_comparable" if non_comparable else "available" if complete else "partial" if sources else "unavailable", coverage=coverage,
        reason=document.get("reason", "Incompatible capture groups are not pooled.") if non_comparable else "Live measurements remain provisional until streams drain, settlement and evidence validation finish." if provisional
               else "; ".join(f'{key}: {sources[key].get("reason") or sources[key].get("state")}' for key in problematic))
    buckets["errors_diagnostics"].append(completeness)
    contradictions = document.get("contradictions", ())
    buckets["errors_diagnostics"].append(_descriptive("contradictions", len(contradictions),
        "Contradictory observations retained without inventing a reconciliation.", coverage={"records": deepcopy(contradictions)}))
    buckets["configuration_cost"].extend([
        _descriptive("profile", deepcopy(document.get("profile", {})), "Versioned instrumentation and privacy profile; only compatible profiles are pooled."),
        _descriptive("runtime", deepcopy(document.get("runtime", {"version": document.get("runtime_version")})), "Captured runtime version and demonstrated stock capabilities.")])
    for key, source in sources.items():
        buckets["provenance_events"].append(_descriptive("source:" + key, source.get("state", "unknown"),
            "Capture source health and evidence counters.", source=key, availability="partial" if key in problematic else "available",
            reason=source.get("reason", ""), coverage=source))
    buckets["provenance_events"].extend([
        _descriptive("evidence_integrity", deepcopy(document.get("capture_integrity", {})), "Immutable capture manifest and source hashes; sanitized evidence is labeled separately from raw evidence."),
        _descriptive("privacy", deepcopy(document.get("privacy", {})), "Explicit redaction, exclusion and diagnostic privacy choices."),
        _descriptive("uncorrelated_records", len(document.get("uncorrelated", ())), "Records without a demonstrated exact-ID or span-ancestry link; timestamps never establish correlations.")])
    facts = document.get("facts", ())
    if not facts and document.get("invocations"):
        facts = [fact for invocation in document["invocations"] for fact in invocation.get("facts", ())]
    # The projection supplies bounded typed event rows; clients never decode OTLP.
    for fact in facts[:100]:
        event = _descriptive("event:" + fact["id"], fact.get("event_type", fact.get("metric_name", fact.get("kind"))),
            "Sanitized retained source record; exact source ordering and native metric representation are preserved.",
            source=fact.get("source", "unknown"), coverage={"identities": deepcopy(fact.get("identities", {})),
                "source_sequence": fact.get("source_sequence"), "kind": fact.get("kind"),
                "native": _bounded_preview(fact.get("native")), "dimensions": deepcopy(fact.get("dimensions")),
                "temporality": fact.get("temporality"), "instrumentation_scope": deepcopy(fact.get("instrumentation_scope"))})
        event["evidence_references"] = list(fact.get("evidence_references", ()))
        buckets["provenance_events"].append(event)
    if len(facts) > 100:
        buckets["provenance_events"].append(_descriptive("additional_event_records", len(facts) - 100,
            "Additional sanitized records remain in sealed capture evidence; the compact projection shows the first 100, with bounded previews and full evidence references."))
    if document.get("exclusions"):
        buckets["errors_diagnostics"].append(_descriptive("capture_exclusions", deepcopy(document["exclusions"]),
            "Unusable or incompatible telemetry excluded without changing response scoring.", availability="partial"))
    overview = {role: rows.get(role, presentation_measurement(role, {})) for role in
                ("duration", "total_tokens", "cached_input_tokens", "cache_read_fraction")}
    overview["telemetry_completeness"] = completeness
    if "run_status" in document:
        overview["run_status"] = _descriptive("run_status", document["run_status"], "Original benchmark process outcome, independent of telemetry health.")
    return {"schema_version": "agmark.telemetry.projection.v1", "phase": document.get("authority", "original"),
            "provisional": provisional, "overview": overview,
            "sections": [{"id": key, "title": title, "rows": buckets[key]} for key, title in SECTIONS],
            "sources": sources, "contradictions": deepcopy(contradictions),
            "availability": "non_comparable" if non_comparable else "partial" if provisional or problematic else "available",
            **({"reason": document.get("reason", "Incompatible capture groups are not pooled."), "compatibility_groups": deepcopy(document.get("compatibility_groups", [])),
                "invocations": [{key: deepcopy(invocation.get(key)) for key in
                    ("invocation_id", "authority", "sealed", "profile", "runtime", "parser_version", "sources", "capture_integrity", "privacy")}
                    for invocation in document.get("invocations", ())]} if non_comparable else {})}


def project_treatment_telemetry(supplied, *, provisional=False):
    """Project current or historical treatment aggregates through one shared API.

    Original benchmark roles remain authoritative. Expanded source facts enrich
    drill-downs; they never replace scoring, replay or retained resource totals.
    """
    supplied = supplied or {}
    expanded = supplied.get("telemetry", supplied.get("normalized_telemetry", supplied.get(NORMALIZED_EXTENSION)))
    if isinstance(expanded, list):
        expanded = aggregate_telemetry(expanded)
    if expanded is None and "measurements" in supplied:
        expanded = supplied
    aggregate_exclusions = deepcopy(expanded.get("exclusions", [])) if isinstance(expanded, dict) else []
    if isinstance(expanded, dict) and expanded.get("groups"):
        original = [group for group in expanded["groups"] if group.get("authority", "original") == "original"]
        if len(original) == 1:
            expanded = original[0]
        elif len(original) > 1:
            reason = "Capture profiles, runtime capabilities or parser versions differ; telemetry metrics are not pooled across these groups."
            invocations = [invocation for group in original for invocation in group.get("invocations", ())]
            measurements = {}
            for group in original:
                for role, measurement in group.get("measurements", {}).items():
                    if role not in measurements:
                        measurements[role] = {**deepcopy(measurement), "value": None, "availability": "non_comparable", "reason": reason,
                            "coverage": {"compatibility_groups": len(original), "group_measurements": []}, "contributors": []}
                    measurements[role]["coverage"]["group_measurements"].append({"contributors": deepcopy(group.get("contributors", [])),
                        "profile": deepcopy(group.get("profile")), "runtime": deepcopy(group.get("runtime")), "measurement": deepcopy(measurement)})
                    measurements[role]["evidence_references"] = sorted(set(measurements[role].get("evidence_references", ()))
                        | set(measurement.get("evidence_references", ())))
            expanded = {"sealed": all(group.get("sealed") for group in original), "measurements": measurements, "authority": "original",
                "availability": "non_comparable", "reason": reason, "invocations": invocations,
                "compatibility_groups": [{key: deepcopy(group.get(key)) for key in
                    ("profile", "runtime", "parser_version", "contributors", "sealed")} for group in original],
                "profile": {"availability": "non_comparable", "groups": [deepcopy(group.get("profile")) for group in original]},
                "runtime": {"availability": "non_comparable", "groups": [deepcopy(group.get("runtime")) for group in original]},
                "capture_integrity": {invocation["invocation_id"]: deepcopy(invocation.get("capture_integrity", {})) for invocation in invocations},
                "privacy": {invocation["invocation_id"]: deepcopy(invocation.get("privacy", {})) for invocation in invocations},
                "uncorrelated": [item for invocation in invocations for item in invocation.get("uncorrelated", ())],
                "contradictions": [item for group in original for item in group.get("contradictions", ())] + [{"reason": reason}]}
    document = deepcopy(expanded) if isinstance(expanded, dict) else {"sealed": not provisional, "authority": "original", "measurements": {}}
    if document.get("authority", "original") != "original":
        document = {"sealed": not provisional, "authority": "original", "measurements": {}, "exclusions": [{"reason": "Replay cannot supply original measurements."}]}
    document["sealed"] = bool(document.get("sealed", not provisional)) and not provisional
    document.setdefault("measurements", {})
    if aggregate_exclusions:
        document.setdefault("exclusions", []).extend(aggregate_exclusions)
    # These are already validated shared measurements, never provider payloads.
    protected = {"total_tokens", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "duration", "cost", "tool_calls", "failed_tool_calls", "cache_read_fraction", "uncached_input_tokens"}
    for role, measurement in supplied.get("roles", {}).items():
        existing = document["measurements"].get(role)
        if role in protected or existing is None or measurement.get("value") is not None:
            document["measurements"][role] = deepcopy(measurement)
            if document.get("availability") == "non_comparable":
                document["measurements"][role].update(value=None, availability="non_comparable", reason=document["reason"])
                if existing is not None:
                    document["measurements"][role]["coverage"] = deepcopy(existing["coverage"])
    if "run_status" in supplied:
        document["run_status"] = supplied["run_status"]
    result = project_telemetry(document)
    if expanded is None:
        result["overview"]["telemetry_completeness"] = _descriptive("telemetry_completeness", "Provisional" if provisional else "Session evidence",
            "Historical retained measurement availability; expanded source capture was not declared for this run.",
            availability="partial" if provisional else "unavailable", reason="No versioned multi-signal capture manifest is retained.",
            coverage={"sealed": not provisional, "expanded_capture": False})
        for section in result["sections"]:
            for index, row in enumerate(section["rows"]):
                if row["id"] == "telemetry_completeness":
                    section["rows"][index] = deepcopy(result["overview"]["telemetry_completeness"])
    return result
