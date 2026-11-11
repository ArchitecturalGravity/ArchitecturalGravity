"""Typed session metrics and pooling rules shared by Results and reports.

Runtime adapters own parsing. This module pools only validated measurements and
their sample counts; it never reads a provider's rollout format.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path

from .model import TelemetryError

SESSION_METRICS = "arcgrav.telemetry:session-metrics"
SCHEMA_ID = "arcgrav.shared.schema.session-metrics"
SCHEMA_VERSION = "1.0.0"
# role: (unit, aggregation). Averages carry their own numerator and denominator.
METRICS = {
    "cache_write_input_tokens": ("tokens", "sum"),
    "context_window": ("tokens", "max"),
    "prompt_count": ("prompts", "sum"),
    "session_span_minutes": ("minutes", "sum"),
    "prompt_span_minutes": ("minutes", "sum"),
    "avg_gap_between_user_prompts_minutes": ("minutes", "weighted_average"),
    "average_characters_per_prompt": ("characters", "weighted_average"),
    "tool_call_span_duration": ("ms", "sum"),
    "tool_call_avg_duration": ("ms", "weighted_average"),
    "distinct_tool_count": ("tools", "union"),
    "compaction_count": ("events", "sum"),
    "total_inference_ms": ("ms", "sum"),
    "average_inference_ms": ("ms", "weighted_average"),
    "inference_call_count": ("events", "sum"),
    "average_ttft_ms": ("ms", "weighted_average"),
    "average_tbt_ms": ("ms", "weighted_average"),
    "turn_aborted": ("events", "sum"),
}


# Additive roles: absent from historical 3.0/3.1 envelopes. Keep their exact
# reconstruction and do not pool direct timings with legacy item-duration proxies.
RAW_METRICS = {
    "token_usage_event_count": ("events", "sum"),
    "provider_request_count": ("calls", "sum"),
    "average_request_duration_ms": ("ms", "weighted_average"),
    "average_direct_ttft_ms": ("ms", "weighted_average"),
    "average_direct_tbt_ms": ("ms", "weighted_average"),
}
ALL_METRICS = {**METRICS, **RAW_METRICS}


def validate_session_metrics(value):
    from ...validation import CatalogEntry, SchemaIdentity, validate_cataloged_document
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas/session_metrics.schema.json").read_text())
    entry = CatalogEntry(SchemaIdentity(SCHEMA_ID, SCHEMA_VERSION), schema["$id"], "AgMark/shared/schemas/session_metrics.schema.json")
    issues = validate_cataloged_document(value, schema_document=schema, entry=entry, source_id=SESSION_METRICS)
    if issues:
        raise TelemetryError("invalid session metrics: " + issues[0].message)
    for role, measurement in value["roles"].items():
        number = measurement["value"]
        if measurement["unit"] != ALL_METRICS[role][0]:
            raise TelemetryError("session metric unit mismatch")
        if number is None:
            if measurement["availability"] in {"available", "partial"}:
                raise TelemetryError("observed session metric lacks value")
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
            raise TelemetryError("invalid session metric number")
        if ALL_METRICS[role][0] in {"tokens", "prompts", "tools", "events", "calls"} and type(number) is not int:
            raise TelemetryError("session counters must be integers")
        if measurement["availability"] not in {"available", "partial"} or not measurement["evidence_references"]:
            raise TelemetryError("session metric lacks observed source")
        aggregation = ALL_METRICS[role][1]
        details = measurement["details"]
        if aggregation == "weighted_average":
            numerator, denominator = details.get("numerator"), details.get("denominator")
            if (isinstance(numerator, bool) or not isinstance(numerator, (int, float)) or not math.isfinite(numerator)
                    or numerator < 0 or type(denominator) is not int or denominator < 1
                    or not math.isclose(number, numerator / denominator, rel_tol=1e-12, abs_tol=1e-12)):
                raise TelemetryError("session average lacks consistent samples")
        if aggregation == "union":
            names = details.get("tool_names")
            if not isinstance(names, list) or any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names) or number != len(names):
                raise TelemetryError("distinct tool count lacks exact tool identities")
    return value


def aggregate_session_metrics(attempts, *, observed, planned):
    from .consumption import _compatibility, _tool_counts, observed_measurement, unavailable_measurement
    roles = {}
    sessions = []
    for document, attempt, envelope, evidence in attempts:
        if envelope is None:
            continue
        session = envelope.get("extensions", {}).get(SESSION_METRICS)
        if session is not None:
            validate_session_metrics(session)
            sessions.append({"observation_id": document["observation_id"], "attempt": attempt["attempt"],
                             "evidence_reference": evidence, **session,
                             "token_roles": envelope["roles"], "tool_roles": _tool_counts(envelope), "tool_events": envelope["tool_events"],
                             "tool_trace_complete": envelope["tool_trace_complete"]})
    for role, (unit, aggregation) in ALL_METRICS.items():
        supplied = [s["roles"][role] for s in sessions if role in s["roles"]]
        if role in RAW_METRICS and not supplied:
            continue
        entries = [m for m in supplied if m["value"] is not None]
        if not entries:
            roles[role] = unavailable_measurement(role, "No recorded session samples for this metric.", unit=unit)
            if role in RAW_METRICS and supplied:
                roles[role]["details"]["inputs"] = supplied
                roles[role]["meaning"] = supplied[0]["meaning"]
            continue
        first = entries[0]
        if len({_compatibility(m) for m in entries}) != 1:
            roles[role] = unavailable_measurement(role, "Incompatible session measurement sources or rules.", unit=unit)
            roles[role]["availability"] = "non_comparable"
            continue
        details = {"runtime_version": first["details"].get("runtime_version"),
                   "coverage": {"measured_attempts": len(entries), "observed_attempts": len(attempts),
                                "observed_observations": observed, "planned_observations": planned},
                   "inputs": entries}
        if aggregation == "weighted_average":
            numerator = sum(m["details"]["numerator"] for m in entries)
            denominator = sum(m["details"]["denominator"] for m in entries)
            number = numerator / denominator
            details.update(numerator=numerator, denominator=denominator)
        elif aggregation == "union":
            names = sorted({name for m in entries for name in m["details"]["tool_names"]})
            number = len(names)
            details["tool_names"] = names
        elif aggregation == "max":
            number = max(m["value"] for m in entries)
        else:
            number = sum(m["value"] for m in entries)
        roles[role] = observed_measurement(number, unit=unit, kind=first["kind"], source=first["source"],
            meaning=first["meaning"], method=aggregation + " compatible session samples", details=details,
            evidence_references=sorted({ref for m in entries for ref in m["evidence_references"]}))
        if observed != planned or len(entries) != len(attempts) or any(m["availability"] != "available" for m in entries):
            roles[role]["availability"] = "partial"
    return roles, sessions
