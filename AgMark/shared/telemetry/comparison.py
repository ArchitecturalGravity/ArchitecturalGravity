"""Wide treatment comparison from typed Original Run presentation records.

No provider payload is parsed here. Structured records keep their representation
and provenance; they are never converted into invented scalar measurements.
"""
from copy import deepcopy
from collections.abc import Mapping

from .projection import presentation_measurement, _section


LEGACY_COMPARISON_METRICS = (
    ("input_tokens", "Input Tokens"), ("reasoning_tokens", "Reasoning Output Tokens"),
    ("output_tokens", "Output Tokens"), ("total_tokens", "Total Tokens"),
    ("context_window", "Context Window"), ("inference_call_count", "Inference Call Count"),
    ("token_usage_event_count", "Token Usage Events"), ("provider_request_count", "Provider Request Count"),
    ("total_inference_ms", "Inference Duration"), ("average_inference_ms", "Average Inference Duration"),
    ("duration", "Treatment Duration"), ("session_span_minutes", "Session Duration"),
    ("average_ttft_ms", "Average TTFT (Proxy)"), ("average_tbt_ms", "Average TBT (Proxy)"),
    ("average_request_duration_ms", "Average Logical Request Duration"),
    ("average_direct_ttft_ms", "Average Direct TTFT"), ("average_direct_tbt_ms", "Average Direct TBT"),
    ("tool_calls", "Tool Calls"), ("distinct_tool_count", "Distinct Tools"),
    ("failed_tool_calls", "Failed Tool Calls"), ("prompt_count", "Prompts"),
    ("avg_gap_between_user_prompts_minutes", "Average Prompt Gap"),
    ("average_characters_per_prompt", "Average Prompt Characters"),
    ("compaction_count", "Compactions"), ("turn_aborted", "Aborted Turns"), ("cost", "Cost"),
)
_LABELS = dict(LEGACY_COMPARISON_METRICS) | {
    "cached_input_tokens": "Cached Input", "cache_write_input_tokens": "Cache Write Input",
    "uncached_input_tokens": "Uncached Input", "cache_read_fraction": "Cache Read Fraction",
    "completed_response_usage_count": "Completed Responses With Usage",
    "observed_request_duration_ms": "Observed Request Duration",
    "first_output_item_latency_ms": "First Output Item Latency (Proxy)",
    "completed_turn_count": "Completed Turns", "capture_duration": "Capture Duration",
    "telemetry_completeness": "Telemetry Completeness",
}
_RELATED = {
    "input_tokens": ("cached_input_tokens", "cache_write_input_tokens", "uncached_input_tokens", "cache_read_fraction"),
    "inference_call_count": ("completed_response_usage_count", "diagnostic_inference_count"),
    "duration": ("capture_duration",),
    "average_ttft_ms": ("first_output_item_latency_ms",),
    "average_request_duration_ms": ("observed_request_duration_ms",),
    "failed_tool_calls": ("diagnostic_tool_call_count", "diagnostic_code_cell_count", "completed_turn_count"),
    "turn_aborted": ("telemetry_completeness", "contradictions"),
}
_SECTION_ANCHORS = {
    "tokens_cache": "total_tokens", "requests_timing": "average_direct_tbt_ms",
    "tools_turns": "failed_tool_calls", "prompts_context": "average_characters_per_prompt",
    "errors_diagnostics": "turn_aborted", "configuration_cost": "cost", "provenance_events": "cost",
}
_SOURCE_COUNTERS = {
    "received_events": ("Received Events", "events", "Retained source receipt count"),
    "received_bytes": ("Received Bytes", "bytes", "Retained source receipt byte count"),
    "dropped": ("Dropped Records", "records", "Retained count of records dropped by this source"),
    "rejected": ("Rejected Records", "records", "Retained count of records rejected by this source"),
    "parse_errors": ("Parse Errors", "errors", "Retained source parse-error count"),
    "partial": ("Partial Capture", "1", "Retained source partial-capture indicator"),
}


def _comparison_record(role, measurement, section):
    row = presentation_measurement(role, measurement)
    row["comparison_section"] = section
    row["comparison_label"] = _LABELS.get(role, str(row.get("name", role)).replace("_", " ").title())
    value = row.get("value")
    if isinstance(value, (Mapping, list, tuple)):
        native = row.get("native", value)
        metric_type = native.get("metric_type") if isinstance(native, Mapping) else None
        label = ("Native histogram" if metric_type in {"histogram", "exponentialHistogram"}
                 else "Native metric series" if role.startswith("native_metric:") else "Structured evidence")
        row["comparison_representation"] = label
        row["comparison_display"] = label + " — see details"
        if row["availability"] not in {"available", "complete"}:
            row["comparison_display"] += " (" + str(row["availability"]).replace("_", " ") + ")"
    elif value is None:
        row["comparison_display"] = str(row["availability"]).replace("_", " ").capitalize()
    return row


def _records(projection, legacy):
    records = {}
    if projection.get("phase", "original") == "original":
        for section in projection.get("sections", ()):
            for row in section.get("rows", ()):
                role = row["id"]
                if role.startswith("event:") or row.get("authority", "original") != "original":
                    continue
                records.setdefault(role, _comparison_record(role, row, section["id"]))
        for role, row in projection.get("overview", {}).items():
            if role != "run_status" and row.get("authority", "original") == "original":
                records.setdefault(role, _comparison_record(role, row, _section(role)))
        # These are existing shared capture-health counters, not event-derived
        # aggregates. Only declared counters become columns; missing is not zero.
        for source, health in projection.get("sources", {}).items():
            for field, (label, unit, definition) in _SOURCE_COUNTERS.items():
                if field not in health:
                    continue
                role = f"source:{source}:{field}"
                state = health.get("state", "unavailable")
                availability = ("non_comparable" if projection.get("availability") == "non_comparable" else
                    "available" if state in {"settled", "sealed", "complete"} and not any(health.get(key) for key in ("partial", "dropped", "rejected", "parse_errors")) else
                    state if state in {"disabled", "unavailable", "unsupported", "failed", "rejected", "settlement_timeout"} else "partial")
                references = deepcopy(records.get("source:" + source, {}).get("evidence_references", []))
                for retained in (health, *health.get("invocations", ())):
                    if retained.get("records_sha256"):
                        references.append("source_records_sha256:" + retained["records_sha256"])
                record = _comparison_record(role, {
                    "value": None if availability == "non_comparable" else deepcopy(health[field]),
                    "unit": unit, "availability": availability, "definition": definition + "; no raw events are recounted.",
                    "source": source, "classification": "observed", "scope": "capture_source_health",
                    "method": "shared capture-health projection@1.0.0", "method_version": "1.0.0",
                    "coverage": deepcopy(health), "reason": health.get("reason") or "",
                    "evidence_references": list(dict.fromkeys(references)),
                }, "provenance_events")
                record["comparison_label"] = source.replace("_", " ").title() + " · " + label
                records[role] = record
    for role, measurement in legacy.items():
        if measurement.get("authority", "original") == "original":
            records.setdefault(role, _comparison_record(role, measurement, _section(role)))
    for role, _ in LEGACY_COMPARISON_METRICS:
        records.setdefault(role, _comparison_record(role, {"value": None, "availability": "unavailable",
            "reason": "No retained Original Run measurement was supplied for this treatment."}, _section(role)))
    return records


def _column_order(role, record):
    legacy = {key: index for index, (key, _) in enumerate(LEGACY_COMPARISON_METRICS)}
    if role in legacy:
        return legacy[role], 0, role
    for anchor, related in _RELATED.items():
        if role in related:
            return legacy[anchor], related.index(role) + 1, role
    section = record["comparison_section"]
    anchor = _SECTION_ANCHORS.get(section, "cost")
    return legacy[anchor], 100 if section != "provenance_events" else 200, role


def project_comparison_table(projections, *, legacy_measurements=()):
    """Union columns across treatments using original typed rows and metadata.

    The legacy ordering is stable as a subsequence. New related metrics sit next
    to their matching legacy metric; unknown future scalar summaries use their
    typed category. Event rows stay in the existing per-treatment drilldown.
    """
    legacy_measurements = tuple(legacy_measurements)
    rows = [_records(projection, legacy_measurements[index] if index < len(legacy_measurements) else {})
            for index, projection in enumerate(projections)]
    templates = _records({}, {})
    for row in rows:
        for key, value in row.items():
            if key not in templates or templates[key].get("source") == "not_observed":
                templates[key] = value
    ordered = sorted(templates, key=lambda key: _column_order(key, templates[key]))
    for row in rows:
        for role in ordered:
            if role not in row:
                template = templates[role]
                row[role] = _comparison_record(role, {"value": None, "unit": template["unit"],
                    "availability": "unavailable", "definition": template["definition"],
                    "reason": "No retained Original Run measurement was supplied for this treatment."},
                    template["comparison_section"])
    return {"schema_version": "agmark.telemetry.comparison.v1", "columns": [
        {"key": key, "label": templates[key]["comparison_label"], "alignment": "right"} for key in ordered], "rows": rows}
