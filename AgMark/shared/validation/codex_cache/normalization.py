"""Evidence-gated stock OTLP request/completion association by span ancestry.

An admission requires one request and at most one token completion below each
sampling-request ancestor. Ambiguity is explicit; timestamps only order already
identified requests and never establish completion association or duration.
"""
from .models import REQUEST_FIELDS, ProviderRequestCacheRecord, ProviderRequestFieldAvailability as Field
from .metrics import observed, derive_request
from .capabilities import HTTP_METHOD, HTTP_WEBSOCKET_METHOD
from .diagnostics import PROFILE, unique_spans, apply_field_reasons

TOKEN_ATTRIBUTES = {
    "input_tokens": "gen_ai.usage.input_tokens",
    "cached_input_tokens": "gen_ai.usage.cache_read.input_tokens",
    "cache_write_input_tokens": "gen_ai.usage.cache_write.input_tokens",
    "output_tokens": "gen_ai.usage.output_tokens",
    "reasoning_tokens": "codex.usage.reasoning_output_tokens",
}


def normalize_spans(spans, *, validation_id, capabilities, evidence_reference, profile=PROFILE):
    if profile != PROFILE:
        raise ValueError("unsupported telemetry normalization profile")
    spans = unique_spans(spans)
    if capabilities.fields["validation_id"].status != "supported":
        return (), ("validation_correlation_unavailable",)
    if capabilities.fields["request_boundaries"].status != "supported" or capabilities.fields["completion_correlation"].status != "supported":
        return (), ("deterministic_request_correlation_unavailable",)
    methods = {field.method for field in capabilities.fields.values()}
    if len(methods) != 1 or not methods <= {HTTP_METHOD, HTTP_WEBSOCKET_METHOD}:
        return (), ("unsupported_capability_method",)
    # Trace and span form identity together. Reject duplicates, foreign evidence,
    # missing ancestors and cycles rather than selecting a convenient candidate.
    byid = {}
    for span in spans:
        if span.get("attributes", {}).get("validation_id") != validation_id:
            continue
        key = (span.get("trace_id"), span.get("span_id"))
        if not all(isinstance(v, str) and v for v in key) or key in byid:
            return (), ("ambiguous_span_identity",)
        byid[key] = span
    def ancestor(span, name="try_run_sampling_request"):
        seen = set()
        while span is not None:
            key = (span["trace_id"], span["span_id"])
            if key in seen:
                return None
            seen.add(key)
            if span["name"] == name:
                return key
            span = byid.get((span["trace_id"], span.get("parent_span_id")))
        return None
    groups = {}
    limitations = []
    websocket_admitted = capabilities.fields["transport"].method == HTTP_WEBSOCKET_METHOD
    warmups = []
    for span in byid.values():
        if span["name"] not in {"responses.stream_request", "responses_websocket.stream_request", "handle_responses"}:
            continue
        if span["name"] == "handle_responses" and not any(k in span["attributes"] for k in TOKEN_ATTRIBUTES.values()):
            continue
        root = ancestor(span)
        if span["name"] == "responses_websocket.stream_request":
            if not websocket_admitted:
                limitations.append("websocket_capability_not_demonstrated")
                continue
            client = ancestor(span, "model_client.stream_responses_websocket")
            warmup = byid[client]["attributes"].get("websocket.warmup") if client else None
            if type(warmup) is not bool:
                limitations.append("websocket_request_kind_unavailable")
                continue
            if warmup:
                warmups.append(span)
                continue
        if root is None:
            limitations.append("request_span_ancestry_unavailable")
            continue
        entry = groups.setdefault(root, {"requests": [], "completions": []})
        if span["name"] in {"responses.stream_request", "responses_websocket.stream_request"}:
            entry["requests"].append(span)
        elif any(k in span["attributes"] for k in TOKEN_ATTRIBUTES.values()):
            entry["completions"].append(span)
    records = []
    for root, group in groups.items():
        if not group["requests"]:
            limitations.append("request_boundary_unavailable")
            if any(s["attributes"].get("transport") == "responses_websocket" for s in byid.values()):
                limitations.append("websocket_boundary_not_observed" if websocket_admitted else "websocket_capability_not_demonstrated")
            continue
        if len(group["requests"]) > 1 or len(group["completions"]) > 1:
            limitations.append("ambiguous_request_completion_ancestry")
            continue
        request = group["requests"][0]
        complete = group["completions"][0] if group["completions"] else None
        values = {k: Field.unavailable("supported_exporter_field_not_established", "codex_otlp", "capability_gate") for k in REQUEST_FIELDS}
        if complete:
            for field, attribute in TOKEN_ATTRIBUTES.items():
                value = complete["attributes"].get(attribute)
                if capabilities.fields[field].status == "supported" and type(value) is int and value >= 0:
                    values[field] = observed(value, "terminal_completion_span_ancestry", (evidence_reference,))
        transport = request["attributes"].get("transport")
        expected_transport = "responses_websocket" if request["name"] == "responses_websocket.stream_request" else "responses_http"
        if transport != expected_transport:
            limitations.append("request_transport_identity_conflict" if websocket_admitted else "transport_capability_not_demonstrated")
            continue
        transport = {"responses_http": "http", "responses_websocket": "websocket"}.get(transport, "unknown")
        if transport != "http" and not (transport == "websocket" and websocket_admitted):
            limitations.append("transport_capability_not_demonstrated")
            continue
        if capabilities.fields["transport"].status != "supported":
            transport = "unknown"
        kind = "generation" if capabilities.fields["request_kind"].status in {"supported", "partial"} else "unknown"
        # The sampling ancestor identifies generation in the controlled supported
        # surface; helper/warmup spans are not inferred from cache counters.
        record = ProviderRequestCacheRecord(request["trace_id"] + ":" + request["span_id"], 1, kind, transport,
            "unknown", values, "span_ancestry", root[0] + ":" + root[1], limitations=(
                "Logical request duration, response/continuation identity, cache key, retry and reconnect are unavailable on this admitted surface.",),
            evidence_references=(evidence_reference,))
        records.append((int(request.get("start_time_ns") or 0), record))
    for request in warmups:
        if request["attributes"].get("transport") != "responses_websocket":
            limitations.append("request_transport_identity_conflict")
            continue
        values = {k: Field.unavailable("warmup_usage_not_exported", "codex_otlp", "capability_gate") for k in REQUEST_FIELDS}
        values["generate"] = observed(False, "observed_websocket_warmup", (evidence_reference,))
        record = ProviderRequestCacheRecord(request["trace_id"] + ":" + request["span_id"], 1, "warmup", "websocket",
            "unknown", values, "span_ancestry", request["trace_id"] + ":" + request["span_id"],
            limitations=("Warmup existence observed; usage, continuation and lifecycle duration unavailable.",), evidence_references=(evidence_reference,))
        records.append((int(request.get("start_time_ns") or 0), record))
    from dataclasses import replace
    records.sort(key=lambda pair: (pair[0], pair[1].request_id))
    if len({start for start, _ in records}) != len(records):
        return (), ("request_order_unavailable",)
    result = tuple(derive_request(replace(record, request_ordinal=i)) for i, (_, record) in enumerate(records, 1))
    result = apply_field_reasons(result)
    return result, tuple(sorted(set(limitations)))
