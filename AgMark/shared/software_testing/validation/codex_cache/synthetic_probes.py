"""Maintained synthetic inputs for replay-admission contract tests.

These spans are authored test data, not captured Codex execution. Runtime version
and binary hashes are modeled identities required by the admission API. Passing
these tests does not verify exporter output, installed binary behavior, or provider
cache behavior. Expected token tuples remain explicit in the consuming tests.
"""
import hashlib
import json
from pathlib import Path

from AgMark.shared.validation.codex_cache.models import CAPABILITY_FIELDS
from AgMark.shared.validation.codex_cache.collector import canonical_capture_spans


HTTP_ID = "11111111-1111-4111-8111-111111111111"
WS_ID = "22222222-2222-4222-8222-222222222222"
BINARY = "sha256:" + "a" * 64


def _span(number, parent, name, validation_id, *, attributes=None):
    return {
        "trace_id": "a" * 32,
        "span_id": f"{number:016x}",
        "parent_span_id": f"{parent:016x}" if parent is not None else None,
        "name": name,
        "start_time_ns": str(number * 100),
        "end_time_ns": str(number * 100 + 50),
        "attributes": {"validation_id": validation_id, **(attributes or {})},
        "events": [],
    }


def _counters(ordinal):
    return {
        "gen_ai.usage.input_tokens": 100 * ordinal,
        "gen_ai.usage.cache_read.input_tokens": 20 * ordinal,
        "gen_ai.usage.cache_write.input_tokens": 11 * ordinal,
        "gen_ai.usage.output_tokens": 7 * ordinal,
        "codex.usage.reasoning_output_tokens": 3 * ordinal,
    }


def synthetic_http_probe(runtime_version="0.159.0"):
    spans = []
    for ordinal in (1, 2):
        root = ordinal * 10000
        spans.extend((
            _span(root, None, "try_run_sampling_request", HTTP_ID),
            _span(root + 1, root, "responses.stream_request", HTTP_ID,
                  attributes={"transport": "responses_http"}),
            _span(root + 2, root, "handle_responses", HTTP_ID,
                  attributes=_counters(ordinal)),
        ))
    return {
        "runtime_version": "codex-cli " + runtime_version, "runtime_binary_sha256": BINARY,
        "validation_id": HTTP_ID, "returncode": 0, "rejected_payloads": 0,
        "provider_requests": [{"ordinal": 1}, {"ordinal": 2}], "spans": canonical_capture_spans(spans),
        "purpose": "Controlled HTTP generation with independently supplied synthetic counters; not live-provider behavior.",
    }


def synthetic_dual_probe(runtime_version="0.159.0"):
    probe = synthetic_http_probe(runtime_version)
    spans = []
    for ordinal in (1, 2, 3):
        root = ordinal * 10000
        warmup = ordinal == 1
        spans.extend((
            _span(root, None, "try_run_sampling_request", WS_ID),
            _span(root + 1, root, "model_client.stream_responses_websocket", WS_ID,
                  attributes={"websocket.warmup": warmup, "transport": "responses_websocket"}),
            _span(root + 2, root + 1, "responses_websocket.stream_request", WS_ID,
                  attributes={"transport": "responses_websocket"}),
        ))
        if not warmup:
            spans.append(_span(root + 3, root, "handle_responses", WS_ID,
                               attributes=_counters(ordinal)))
    probe["websocket_probe"] = {
        "runtime_version": probe["runtime_version"], "runtime_binary_sha256": BINARY,
        "validation_id": WS_ID, "returncode": 0, "rejected_payloads": 0,
        "provider_requests": [{"ordinal": 1, "kind": "warmup"},
                              {"ordinal": 2, "kind": "generation"},
                              {"ordinal": 3, "kind": "generation"}],
        "spans": canonical_capture_spans(spans),
        "purpose": "Controlled WebSocket warmup and generation with independently supplied synthetic counters; not live-provider behavior.",
    }
    return probe


def write_http_bundle(directory, runtime_version="0.159.0"):
    """Write independently authored admission inputs for file-integrity tests."""
    root = Path(directory)
    probe = synthetic_http_probe(runtime_version)
    raw = (json.dumps(probe, sort_keys=True, separators=(",", ":")) + "\n").encode()
    identity = "sha256:" + hashlib.sha256(raw).hexdigest()
    supported = {"validation_id", "request_boundaries", "completion_correlation",
                 "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                 "output_tokens", "reasoning_tokens", "transport"}
    fields = {
        name: {"status": "supported" if name in supported else "partial" if name == "request_kind" else "unsupported",
               "method": "controlled_stock_http_sampling_span_ancestry_v1",
               "evidence_references": [identity],
               "limitation": None if name in supported else "Not independently established beyond HTTP generation counters."}
        for name in CAPABILITY_FIELDS
    }
    document = {"runtime_version": runtime_version, "runtime_binary_sha256": BINARY,
                "fields": fields, "probe_reference": "probe.json",
                "probe_sha256": identity,
                "scope": "controlled HTTP generation only; no provider cache behavior or request trajectory claim"}
    (root / "probe.json").write_bytes(raw)
    (root / "synthetic-capabilities.json").write_text(json.dumps(document))
    return root
