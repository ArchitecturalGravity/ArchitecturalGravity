"""Content-free stock transport diagnostics, independent of request authority.

Exact trace/span ownership is retained; timestamp proximity never associates
completion counters with a request. No diagnostic upgrades capability admission.
"""
from dataclasses import replace
import json
from .models import ProviderRequestFieldAvailability as Field

EXTENSION = "arcgrav.telemetry:stock-transport-diagnostics-v2"
PROFILE = "stock-capability-diagnostics-v2"
UNSUPPORTED = {
    "response_id": "The controlled probe does not establish correlated provider response IDs.",
    "previous_response_id": "The controlled probe does not establish correlated continuation response IDs.",
    "retry": "HTTP attempt indices may be exported as diagnostics; complete logical-request retry correlation is not established.",
    "reconnect": "Connection reuse is not reconnect evidence; the controlled probe does not establish a correlated reconnect lifecycle.",
    "request_duration_ms": "No matched finalized-transmission and terminal-completion events; span/send/connect durations are not logical request duration.",
}
TIMING_LIMITS = {
    "direct_ttft_ms": "The controlled probe does not establish correlated request-start and first actual token timestamps. Exported ttft_ms semantics are not independently established.",
    "direct_tbt_ms": "The controlled probe does not establish ordered actual token timestamps. SSE/WebSocket polling durations or text chunks are not token intervals.",
    "warmup_usage": "Warmup completion counters are not deterministically correlated on the admitted trace surface; existence does not establish usage.",
    "warmup_duration_ms": "Warmup lacks correlated finalized-transmission and terminal-completion events.",
}
EVENT_MEANINGS = {
    "codex.api_request": "Exported HTTP attempt and duration diagnostics; timing semantics are not independently established, not logical request duration or total retry count.",
    "codex.websocket_request": "Exported WebSocket duration and connection-reused diagnostics; timing semantics are not independently established, not logical request duration or reconnect count.",
    "codex.websocket_connect": "Exported connection duration and reuse diagnostics; timing semantics are not independently established, not logical request duration or reconnect count.",
    "codex.sse_event": "Usage as exported on this span. ttft_ms semantics are not independently established, not first-token timing. No timestamp-based request/warmup association.",
}


def unique_spans(spans):
    """Ignore identical exporter deliveries; retain conflicting identities to fail closed."""
    result = []
    for span in spans:
        if span not in result:
            result.append(span)
    return result


def diagnostic_field(spans, *, validation_id, evidence_reference):
    events = []
    for span in unique_spans(spans):
        if span.get("attributes", {}).get("validation_id") != validation_id:
            continue
        for event in span.get("events", ()):
            name = event["attributes"]["event.name"]
            item = {"trace_id": span["trace_id"], "span_id": span["span_id"],
                    "parent_span_id": span.get("parent_span_id"), "exported_span": span["name"], "event": event, "meaning": EVENT_MEANINGS[name]}
            if item not in events:
                events.append(item)
    data = {"profile": PROFILE, "transport_events": events,
            "availability": "observed" if events else "unavailable",
            "reason": "No allowlisted trace events retained." if not events else "Exported diagnostics only; no new request capability is established.",
            "unsupported_fields": {**UNSUPPORTED, **TIMING_LIMITS}}
    return Field(json.dumps(data, sort_keys=True, separators=(",", ":")), "available",
                 "stock Codex OTLP traces", "allowlisted_exported_span_events",
                 evidence_references=(evidence_reference,))


def apply_field_reasons(records):
    """Explain unavailable fields on the current capability-admitted surface."""
    result = []
    for record in records:
        values = dict(record.fields)
        for key, reason in UNSUPPORTED.items():
            if values[key].value is None:
                values[key] = Field.unavailable(reason, "stock Codex OTLP traces", "source_contract_limit")
        result.append(replace(record, fields=values))
    return tuple(result)


def retained_diagnostics(replay):
    """Presentation reads only normalized retained metadata, never provider payloads."""
    field = replay.extensions.get(EXTENSION)
    if field is not None:
        try:
            value = json.loads(field.value)
            if isinstance(value, dict) and value.get("profile") == PROFILE:
                return value
        except (ValueError, TypeError):
            pass
    return {
        "availability": "unavailable", "reason": "No retained transport diagnostics for the current capability profile.",
        "unsupported_fields": {**UNSUPPORTED, **TIMING_LIMITS}}
