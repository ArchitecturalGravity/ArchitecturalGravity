"""Validation-scoped loopback OTLP/HTTP JSON collector with an allowlist.

Prompt, response, Guardian, authorization and arbitrary event content are never
retained. Resource payloads and headers are discarded at ingress.
"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import re

# Retain only fields consumed by the admitted stock normalizer. Arbitrary
# span names and string attributes can carry prompt/response content too.
SAFE_ATTRIBUTES = frozenset({
    "validation_id", "gen_ai.usage.input_tokens", "gen_ai.usage.cache_read.input_tokens",
    "gen_ai.usage.cache_write.input_tokens", "gen_ai.usage.output_tokens",
    "codex.usage.reasoning_output_tokens", "transport", "websocket.warmup",
})
SAFE_SPAN_NAMES = frozenset({"try_run_sampling_request", "responses.stream_request", "handle_responses",
    "responses_websocket.stream_request", "model_client.stream_responses_websocket"})


def _identifier(value, length):
    return value if (isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{" + str(length) + "}", value)
                     and any(c != "0" for c in value)) else None


def _timestamp(value):
    return str(value) if isinstance(value, (str, int)) and re.fullmatch(r"[0-9]{1,20}", str(value)) else None


def _attributes(values):
    output = {}
    for entry in values or ():
        key, value = entry.get("key"), entry.get("value", {})
        if key not in SAFE_ATTRIBUTES:
            continue
        if len(value) != 1:
            continue
        kind, raw = next(iter(value.items()))
        if kind == "intValue":
            try:
                raw = int(raw)
            except (TypeError, ValueError):
                continue
        elif kind not in {"stringValue", "boolValue", "doubleValue"}:
            continue
        if key == "validation_id":
            if kind != "stringValue" or not isinstance(raw, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", raw):
                continue
        elif key == "websocket.warmup":
            if kind != "boolValue" or type(raw) is not bool:
                continue
        elif key == "transport":
            if kind != "stringValue" or raw not in {"responses_http", "responses_websocket"}:
                continue
        elif kind != "intValue" or type(raw) is not int or raw < 0:
            continue
        output[key] = raw
    return output


# The controlled capability surface emits these narrow diagnostics. They are
# not logical lifecycle events or token timestamps. Never retain error strings,
# headers, account identifiers, model payloads, or arbitrary event attributes.
SAFE_EVENT_FIELDS = {
    "codex.api_request": {"attempt", "duration_ms", "http.response.status_code"},
    "codex.websocket_request": {"duration_ms", "auth.connection_reused"},
    "codex.websocket_connect": {"duration_ms", "auth.connection_reused", "http.response.status_code"},
    "codex.sse_event": {"event.kind", "input_token_count", "output_token_count",
        "cached_token_count", "cache_write_token_count", "reasoning_token_count", "ttft_ms"},
}


def _safe_events(events):
    result = []
    for event in events or ():
        if not isinstance(event, dict):
            continue
        attributes = {}
        duplicate = set()
        for entry in event.get("attributes", ()):
            if not isinstance(entry, dict) or not isinstance(entry.get("value"), dict):
                continue
            key, value = entry.get("key"), entry["value"]
            if key in attributes:
                duplicate.add(key)
            if len(value) == 1:
                attributes[key] = next(iter(value.items()))
        if duplicate:
            continue
        name = attributes.get("event.name", (None, None))[1]
        allowed = SAFE_EVENT_FIELDS.get(name) if isinstance(name, str) else None
        stamp = _timestamp(event.get("timeUnixNano"))
        if allowed is None or stamp is None:
            continue
        safe = {"event.name": name}
        for key in allowed:
            kind, raw = attributes.get(key, (None, None))
            if key == "auth.connection_reused":
                if kind == "boolValue" and type(raw) is bool:
                    safe[key] = raw
            elif key == "event.kind":
                if kind == "stringValue" and raw == "response.completed":
                    safe[key] = raw
            elif kind in {"intValue", "stringValue"} and type(raw) in {int, str} and re.fullmatch(r"[0-9]{1,18}", str(raw)):
                safe[key] = int(raw)
        if name == "codex.sse_event" and safe.get("event.kind") != "response.completed":
            continue
        item = {"time_ns": stamp, "attributes": safe}
        if item not in result:
            result.append(item)
    return result


def sanitized_spans(document):
    result = []
    for resource in document.get("resourceSpans", ()):
        for scope in resource.get("scopeSpans", ()):
            for span in scope.get("spans", ()):
                result.append({
                    "trace_id": _identifier(span.get("traceId"), 32), "span_id": _identifier(span.get("spanId"), 16),
                    "parent_span_id": _identifier(span.get("parentSpanId"), 16), "name": span.get("name") if isinstance(span.get("name"), str) and span.get("name") in SAFE_SPAN_NAMES else "unobserved",
                    "start_time_ns": _timestamp(span.get("startTimeUnixNano")),
                    "end_time_ns": _timestamp(span.get("endTimeUnixNano")),
                    "attributes": _attributes(span.get("attributes")),
                    "events": _safe_events(span.get("events")),
                })
    return result


def canonical_capture_spans(spans):
    """Apply the same narrow ingress policy to independently supplied bytes."""
    from collections.abc import Mapping
    if not isinstance(spans, (list, tuple)) or any(not isinstance(s, Mapping) or not isinstance(s.get("attributes", {}), Mapping) for s in spans):
        raise ValueError("capture spans require typed objects and attributes")
    return minimized_span_identities(sanitized_spans({"resourceSpans": [{"scopeSpans": [{"spans": [
        {"traceId": s.get("trace_id"), "spanId": s.get("span_id"),
         "parentSpanId": s.get("parent_span_id"), "name": s.get("name"),
         "startTimeUnixNano": s.get("start_time_ns"), "endTimeUnixNano": s.get("end_time_ns"),
         "events": [{"timeUnixNano": e.get("time_ns"), "attributes": [
             {"key": k, "value": {"boolValue" if type(v) is bool else "intValue" if type(v) is int else "stringValue": v}}
             for k, v in e.get("attributes", {}).items()]} for e in s.get("events", ())],
         "attributes": [{"key": k, "value": {"boolValue" if type(v) is bool else "intValue" if type(v) is int else "stringValue": v}}
                        for k, v in s.get("attributes", {}).items()]}
        for s in spans]}]}]}))


def minimized_span_identities(spans):
    """Preserve invocation-local graph topology and timing, not native IDs/time.

    Canonicalization is deterministic and idempotent. The complete invocation
    is projected together so separate exporter batches cannot alias each other.
    """
    traces, identities = {}, {}
    times = [int(s[k]) for s in spans for k in ("start_time_ns", "end_time_ns") if s[k] is not None]
    times += [int(e["time_ns"]) for s in spans for e in s["events"]]
    origin = min(times, default=0)
    def trace(value):
        if value is None:
            return None
        return traces.setdefault(value, format(len(traces) + 1, "032x"))
    def alias(owner, value):
        if value is None:
            return None
        return identities.setdefault((owner, value), format(len(identities) + 1, "016x"))
    result = []
    for span in spans:
        owner = span["trace_id"]
        result.append({**span, "trace_id": trace(owner),
            "span_id": alias(owner, span["span_id"]),
            "parent_span_id": alias(owner, span["parent_span_id"]),
            **{k: str(int(span[k]) - origin) if span[k] is not None else None
               for k in ("start_time_ns", "end_time_ns")},
            "events": [{**event, "time_ns": str(int(event["time_ns"]) - origin)} for event in span["events"]]})
    return result


class LoopbackTraceCollector:
    def __init__(self):
        self._spans = []
        self._lock = threading.Lock()
        self.rejected_payloads = 0
        self.server = None

    def __enter__(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if self.path != "/v1/traces" or not 0 < length <= 4 * 1024 * 1024:
                        raise ValueError("invalid signal or payload size")
                    document = json.loads(self.rfile.read(length))
                    spans = sanitized_spans(document)
                    with owner._lock:
                        owner._spans.extend(spans)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{}")
                except (ValueError, TypeError, AttributeError):
                    owner.rejected_payloads += 1
                    self.send_error(400)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def endpoint(self):
        if self.server is None:
            raise RuntimeError("collector is not active")
        return f"http://127.0.0.1:{self.server.server_port}/v1/traces"

    @property
    def spans(self):
        with self._lock:
            return canonical_capture_spans(self._spans)

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.server = None


def observation_overrides(validation_id, endpoint):
    """Validation-only stock settings, admitted by a controlled runtime probe."""
    from urllib.parse import urlsplit
    from uuid import UUID
    UUID(validation_id)
    url = urlsplit(endpoint)
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.path != "/v1/traces":
        raise ValueError("validation exporter requires loopback trace endpoint")
    return (
        "otel.log_user_prompt=false", "otel.log_agent_responses=false",
        "otel.log_guardian_assessments=false", 'otel.exporter="none"',
        'otel.metrics_exporter="none"',
        'otel.trace_exporter={otlp-http={endpoint=' + json.dumps(endpoint) + ',protocol="json"}}',
        "otel.span_attributes={validation_id=" + json.dumps(validation_id) + "}",
    )
