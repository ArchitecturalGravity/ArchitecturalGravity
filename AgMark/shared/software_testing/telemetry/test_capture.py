"""Offline original capture, privacy, lifecycle and OTLP conservation tests."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from AgMark.shared.telemetry import CaptureProfile, CaptureSession, validate_manifest
from AgMark.shared.telemetry.collector import sanitized_signal_records
from AgMark.shared.telemetry.privacy import AliasRegistry, Sanitizer, runtime_identity
from AgMark.shared.telemetry.profile import observation_overrides


def attr(key, value):
    kind = "boolValue" if type(value) is bool else "intValue" if type(value) is int else "doubleValue" if type(value) is float else "stringValue"
    return {"key": key, "value": {kind: str(value) if kind == "intValue" else value}}


def otlp(signal, records):
    keys = {"logs": ("resourceLogs", "scopeLogs", "logRecords"),
            "traces": ("resourceSpans", "scopeSpans", "spans"),
            "metrics": ("resourceMetrics", "scopeMetrics", "metrics")}
    resource, scope, records_key = keys[signal]
    return {resource: [{"resource": {"attributes": [attr("service.name", "codex-cli"),
        attr("account.email", "private@example.test")]}, scope: [{"scope": {"name": "codex-otel", "version": "0.159.0"},
        "schemaUrl": "https://opentelemetry.io/schemas/1.34.0", records_key: records}]}]}


def post(capture, signal, document):
    body = json.dumps(document).encode() if not isinstance(document, bytes) else document
    request = Request(capture.collector.endpoint + "/v1/" + signal, data=body,
                      headers={"Content-Type": "application/json", "Authorization": "Bearer private-receiver-header"})
    with urlopen(request, timeout=2) as response:
        return response.status


def stdout(thread="thread-1"):
    return (json.dumps({"type": "thread.started", "thread_id": thread}) + "\n"
        + json.dumps({"type": "turn.started"}) + "\n"
        + json.dumps({"type": "item.completed", "item": {"id": "item-1", "type": "agent_message", "text": "PRIVATE ANSWER"}}) + "\n"
        + json.dumps({"type": "turn.completed", "usage": {"input_tokens": 13, "output_tokens": 2}}) + "\n").encode()


def rollout(thread="thread-1", *, truncated=False):
    events = [{"type": "session_meta", "payload": {"id": thread}},
        {"type": "token_usage_record", "payload": {"thread_id": thread, "turn_id": "turn-1", "session_id": "session-1",
            "root_turn_id": "turn-1", "response_id": "resp-1", "usage": {"input_tokens": 13, "cached_input_tokens": 10,
                "output_tokens": 2, "reasoning_output_tokens": 1}, "thread_token_usage": {"input_tokens": 13, "output_tokens": 2}}},
        {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "PRIVATE ANSWER"}}]
    raw = b"\n".join(json.dumps(e).encode() for e in events) + b"\n"
    if truncated:
        raw += b'{"type":"event_msg","payload":'
    return {"availability": "retained", "thread_id": thread, "content_base64": base64.b64encode(raw).decode()}


class CaptureTests(unittest.TestCase):
    def make_capture(self, **kwargs):
        session = CaptureSession(runtime_version="0.159.0", invocation_id="observation:fcdf225673a6f8a348acc987b0b35ea323cf83b9adc65841d1ae7d82b1a73234", **kwargs).start()
        self.addCleanup(session.close)
        return session

    def test_original_multi_signal_native_structure_privacy_and_seal(self):
        progress = []
        session = self.make_capture(on_progress=progress.append)
        self.assertEqual(session.env_overrides, {"CODEX_ROLLOUT_TRACE_ROOT": None})
        self.assertTrue(any("otel.metrics_exporter=" in x and "127.0.0.1" in x for x in session.config_overrides))
        self.assertIn("otel.tool_result.max_bytes=0", session.config_overrides)
        span = {"traceId": "a" * 32, "spanId": "b" * 16, "parentSpanId": "c" * 16,
            "name": "responses.stream_request", "startTimeUnixNano": "100", "endTimeUnixNano": "200",
            "attributes": [attr("response_id", "resp-1"), attr("authorization", "PRIVATE AUTH"),
                attr("future.numeric", 7), attr("future.private", "PRIVATE VALUE")],
            "futureSafeCount": 3, "events": [{"timeUnixNano": "150", "name": "codex.sse_event",
                "attributes": [attr("event.kind", "response.completed"), attr("input_token_count", 13)]}]}
        log = {"timeUnixNano": "150", "body": {"stringValue": "PRIVATE MESSAGE"},
            "attributes": [attr("event.name", "codex.api_request"), attr("duration_ms", 10),
                attr("arguments", "PRIVATE COMMAND"), attr("error.message", "PRIVATE ERROR")]}
        metric = {"name": "codex.responses_api_engine_iapi_tbt.duration_ms", "unit": "ms",
            "histogram": {"aggregationTemporality": 2, "dataPoints": [{"startTimeUnixNano": "100", "timeUnixNano": "200",
                "count": "3", "sum": 10, "explicitBounds": [1, 5], "bucketCounts": ["1", "1", "1"],
                "attributes": [attr("phase", "generation"), attr("transport", "websocket"), attr("future.flag", True)]}]}}
        for signal, record in (("traces", span), ("logs", log), ("metrics", metric)):
            self.assertEqual(post(session, signal, otlp(signal, [record])), 200)
        raw = stdout()
        session.ingest_stdout(raw[:19])
        session.ingest_stdout(raw[19:])
        session.ingest_stderr(b"PRIVATE SECRET STDERR")
        sealed = session.finish(raw, b"PRIVATE SECRET STDERR", rollout(), "completed")
        self.assertTrue(validate_manifest(sealed))
        self.assertEqual(sealed["completeness"]["status"], "complete")
        self.assertNotIn("PRIVATE", json.dumps(sealed))
        self.assertNotIn("private@example", json.dumps(sealed))
        self.assertGreater(sealed["privacy"]["excluded_fields"], 0)
        native = next(r["payload"] for r in sealed["records"] if r["source"] == "otel_metrics")
        expected_histogram = json.loads(json.dumps(metric["histogram"]))
        expected_histogram["dataPoints"][0]["attributes"].pop()
        expected_histogram["dataPoints"][0].update(startTimeUnixNano="0", timeUnixNano="100")
        self.assertEqual(native["histogram"], expected_histogram)
        self.assertEqual(native["_scope"], {"name": "codex-otel", "version": "0.159.0"})
        self.assertEqual(native["_schema_version"], "1.34.0")
        native_span = next(r["payload"] for r in sealed["records"] if r["source"] == "otel_traces")
        self.assertNotIn("futureSafeCount", native_span)
        self.assertNotIn(attr("future.numeric", 7), native_span["attributes"])
        self.assertNotIn("raw_sha256", sealed["sources"]["stdout"])
        self.assertNotIn("raw_byte_length", sealed["sources"]["stdout"])
        self.assertEqual(progress[-1]["phase"], "evidence_validation")
        self.assertTrue(progress[-1]["evidence_sealed"])
        self.assertTrue(all(not p["evidence_sealed"] for p in progress[:-1]))
        sealed["records"][0]["payload"]["status"] = "tampered"
        with self.assertRaises(ValueError):
            validate_manifest(sealed)
        self.assertTrue(validate_manifest(session.finish()))

    def test_parallel_source_order_and_bounded_shutdown(self):
        session = self.make_capture()
        def send(index):
            return post(session, "logs", otlp("logs", [{"timeUnixNano": str(index), "attributes": [attr("future.counter", index)]}]))
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(send, range(1, 13))), [200] * 12)
        start = time.monotonic()
        sealed = session.finish(stdout(), b"", rollout(), "cancelled")
        self.assertLess(time.monotonic() - start, 2)
        records = [r for r in sealed["records"] if r["source"] == "otel_logs"]
        self.assertEqual([r["source_sequence"] for r in records], list(range(1, 13)))
        self.assertEqual(len({r["payload"]["timeUnixNano"] for r in records}), 12)
        self.assertTrue(validate_manifest(sealed))

    def test_unspecified_observed_log_time_does_not_reject_a_real_timestamp(self):
        session = self.make_capture()
        timestamp = "1794350000000000000"
        self.assertEqual(post(session, "logs", otlp("logs", [
            {"timeUnixNano": "0", "observedTimeUnixNano": timestamp},
            {"timeUnixNano": timestamp, "observedTimeUnixNano": "0",
             "attributes": [attr("event.name", "codex.api_request")]},
            {"timeUnixNano": str(int(timestamp) + 10),
             "observedTimeUnixNano": str(int(timestamp) + 15)}])), 200)
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        logs = [r["payload"] for r in sealed["records"] if r["source"] == "otel_logs"]
        self.assertNotIn("timeUnixNano", logs[0])
        self.assertEqual("0", logs[0]["observedTimeUnixNano"])
        self.assertEqual("0", logs[1]["timeUnixNano"])
        self.assertNotIn("observedTimeUnixNano", logs[1])
        self.assertEqual("15", logs[2]["observedTimeUnixNano"])
        self.assertEqual(0, sealed["sources"]["otel_logs"]["rejected"])
        self.assertTrue(validate_manifest(sealed))

    def test_schema_two_reduced_graph_retains_recording_outcome_and_rejects_unknown_schema(self):
        for schema, complete in ((2, True), (2, False), (2, None), (3, True), (True, True)):
            with self.subTest(schema=schema, complete=complete):
                session = self.make_capture(profile=CaptureProfile(id="deep_telemetry",
                    diagnostic_privacy_acknowledged=True))
                bundle = session.diagnostic_root / "fixture"
                bundle.mkdir()
                state = {"schema_version": schema, "root_thread_id": "thread-1",
                         "recording_complete": complete, "threads": {}, "raw_payloads": {}}
                (bundle / "state.json").write_text(json.dumps(state))
                sealed = session.finish(stdout(), b"", rollout(), "completed")
                graphs = [r["payload"] for r in sealed["records"]
                          if r["source"] == "diagnostics" and r["payload"].get("type") == "reduced_graph"]
                supported = type(schema) is int and schema == 2 and type(complete) is bool
                self.assertEqual(supported, bool(graphs))
                if supported:
                    self.assertIs(complete, graphs[0]["recording_complete"])
                    self.assertEqual("settled" if complete else "partial", sealed["sources"]["diagnostics"]["state"])
                else:
                    self.assertGreater(sealed["sources"]["diagnostics"]["parse_errors"], 0)
                self.assertTrue(validate_manifest(sealed))

    def test_invalid_otlp_is_counted_without_losing_valid_records(self):
        session = self.make_capture()
        with self.assertRaises(HTTPError):
            post(session, "metrics", b'{"resourceMetrics":[],"resourceMetrics":[]}')
        with self.assertRaises(HTTPError):
            post(session, "metrics", {"resourceMetrics": "wrong"})
        post(session, "metrics", otlp("metrics", [{"name": "codex.future", "gauge": {"dataPoints": [{"asInt": "5"}]}}]))
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        health = sealed["sources"]["otel_metrics"]
        self.assertEqual(health["rejected"], 2)
        self.assertEqual(health["parse_errors"], 2)
        self.assertEqual(health["retained_events"], 1)
        self.assertEqual(health["state"], "partial")

    def test_conditional_no_export_is_unavailable_not_zero_or_full_coverage(self):
        session = self.make_capture()
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        for signal in ("otel_logs", "otel_traces", "otel_metrics"):
            self.assertEqual(sealed["sources"][signal]["state"], "unavailable")
            self.assertEqual(sealed["sources"][signal]["reason"], "signal_not_exported_or_not_emitted")
        self.assertEqual(sealed["completeness"]["status"], "partial")

    def test_native_capture_is_version_independent_and_preserves_dotted_identity(self):
        for version in ("0.159.0", "0.160.0", "9.9.9"):
            with self.subTest(version=version):
                identity = "observation:" + hashlib.sha256(version.encode()).hexdigest()
                session = CaptureSession(runtime_version=version, invocation_id=identity).start()
                self.addCleanup(session.close)
                self.assertIsNotNone(session.collector)
                self.assertEqual("supported", session.runtime["capability_status"])
                self.assertIn('otel.span_attributes={agmark_invocation_id="' + identity + '"}',
                              session.config_overrides)
                sealed = session.finish(stdout(), b"", rollout(), "completed")
                self.assertEqual(identity, sealed["invocation_id"])
                from AgMark.shared.telemetry.wsl import WslCaptureSession
                bridge = WslCaptureSession(runtime_version=version, invocation_id=identity,
                    launch_metadata={"launcher": "wsl", "distribution": "Fixture", "executable": "codex"})
                self.assertEqual(identity, bridge.invocation_id)
                self.assertEqual("unavailable", sealed["sources"]["otel_traces"]["state"])
                self.assertEqual("settled", sealed["sources"]["stdout"]["state"])

    def test_direct_wsl_capture_requires_environment_local_receiver_without_downgrade(self):
        session = CaptureSession(runtime_version="0.159.0", invocation_id="observation:d9298a10d1b0735837dc4bd85dac641b0f3cef27a47e5d53a54f2f3f5b2fcffa", launch_mode="wsl").start()
        self.addCleanup(session.close)
        self.assertIsNone(session.collector)
        self.assertEqual((), session.config_overrides)
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        for signal in ("otel_logs", "otel_traces", "otel_metrics"):
            self.assertEqual("unsupported", sealed["sources"][signal]["state"])
            self.assertEqual("execution_environment_local_receiver_unavailable", sealed["sources"][signal]["reason"])
        self.assertEqual("settled", sealed["sources"]["stdout"]["state"])

    def test_dotted_identity_support_does_not_allow_paths_or_unbounded_metadata(self):
        for identity in ("../escape", "echo..test", "with space", "line\nbreak", "x" * 129, "", None):
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(ValueError, "canonical non-personal invocation identifier"):
                    CaptureSession(runtime_version="0.159.0", invocation_id=identity)
                with self.assertRaisesRegex(ValueError, "canonical non-personal invocation identifier"):
                    observation_overrides(identity, "http://127.0.0.1:12345")

    def test_receiver_failure_preserves_execution_evidence(self):
        with patch("AgMark.shared.telemetry.collector.ThreadingHTTPServer.__init__", side_effect=OSError("socket denied")):
            session = self.make_capture()
        self.assertEqual((), session.config_overrides, "failed capture must not silently disable requested exporters")
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        self.assertEqual(sealed["sources"]["otel_logs"]["state"], "failed")
        self.assertEqual(sealed["process_status"], {"status": "completed"})

    def test_partial_malformed_rollout_keeps_previous_safe_events(self):
        session = self.make_capture()
        sealed = session.finish(stdout(), b"", rollout(truncated=True), "timeout")
        self.assertEqual(sealed["sources"]["rollout"]["state"], "partial")
        self.assertEqual(sealed["sources"]["rollout"]["parse_errors"], 1)
        self.assertTrue(any(r["payload"].get("type") == "token_usage_record" for r in sealed["records"]))

    def test_exact_thread_binding_and_interrupted_streams(self):
        session = self.make_capture()
        session.ingest_stdout(b'{"type":"thread.started","thread_id":"thread-1"}\n{"type":')
        sealed = session.finish(stderr=b"", rollout_record=rollout("other-thread"), process_status="cancelled")
        self.assertEqual(sealed["sources"]["rollout"]["reason"], "session_thread_id_mismatch")
        self.assertEqual(sealed["sources"]["stdout"]["parse_errors"], 1)
        self.assertEqual(sealed["process_status"]["status"], "cancelled")
        self.assertTrue(validate_manifest(sealed))

    def test_retention_limits_and_repeated_invocations(self):
        profile = CaptureProfile(max_records=2)
        first = self.make_capture(profile=profile)
        before = first.collector.endpoint
        sealed = first.finish(stdout(), b"", rollout(), "failed")
        self.assertTrue(any(s["dropped"] for s in sealed["sources"].values()))
        self.assertEqual(sealed["completeness"]["status"], "partial")
        second = self.make_capture()
        self.assertNotEqual(before, second.collector.endpoint)
        again = second.finish(b"", b"", None, "launch_failed")
        self.assertEqual(again["sources"]["otel_logs"]["retained_events"], 0)
        self.assertNotEqual(sealed["integrity"]["manifest_sha256"], again["integrity"]["manifest_sha256"])
        with self.assertRaises(RuntimeError):
            first.ingest_stdout(b"late")
        with self.assertRaises(RuntimeError):
            first.start()

    def test_sensitive_diagnostics_require_explicit_opt_in_and_keep_only_safe_spine(self):
        with self.assertRaises(ValueError):
            CaptureProfile.from_control("deep_telemetry")
        profile = CaptureProfile.from_control("deep_telemetry", diagnostic_privacy_acknowledged=True)
        # Fixture only: no stock process or provider is invoked, and no payload
        # capture is enabled in the environment of this test process.
        session = self.make_capture(profile=profile)
        root = session.diagnostic_root
        bundle = root / "fixture"
        bundle.mkdir()
        (bundle / "manifest.json").write_text('{"trace_id":"trace-1"}')
        (bundle / "trace.jsonl").write_text(json.dumps({"seq": 1, "kind": "inference.completed",
            "thread_id": "thread-1", "inference_call_id": "call-1", "payload": {"text": "PRIVATE PAYLOAD", "input_tokens": 3}}) + "\n")
        (bundle / "payloads").mkdir()
        (bundle / "payloads" / "secret.json").write_text('{"authorization":"PRIVATE AUTH"}')
        with patch("AgMark.shared.telemetry.capture.subprocess.run") as reduce:
            reduce.return_value.returncode = 0
            self.assertEqual(session.reduce_diagnostics("codex")[0]["status"], "completed")
            self.assertEqual(reduce.call_args.args[0][:3], ["codex", "debug", "trace-reduce"])
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        self.assertFalse(root.exists())
        self.assertNotIn("PRIVATE", json.dumps(sealed))
        self.assertEqual(sealed["sources"]["diagnostics"]["state"], "settled")
        self.assertTrue(any(r["source"] == "diagnostics" and r["payload"].get("seq") == 1 for r in sealed["records"]))

    def test_known_credential_shapes_are_excluded_even_in_structural_string_fields(self):
        secrets = ["sk-abcdefghijklmnop", "Bearer-token", "eyJabcdefghijk.abcdefghijk.abcdefghijk",
                   "ghp_abcdefghijklmnopqrst", "AKIA1234567890123456"]
        sanitizer = Sanitizer()
        for secret in secrets:
            self.assertIsNone(sanitizer.value(secret, key="name"))
        safe = sanitizer.value({"api_key": 1234, "future": 7, "futureObject": {"futureBool": True},
            "name": "codex.future", "attributes": [attr("access_token", 1234), attr("future.numeric", 9)]})
        self.assertEqual(safe, {"attributes": []})

    def test_exporter_endpoint_must_be_local_and_cannot_embed_credentials(self):
        for endpoint in ("https://example.test", "http://localhost:4318", "http://secret@127.0.0.1:4318", "http://127.0.0.1:4318/v1/traces"):
            with self.assertRaises(ValueError):
                observation_overrides("test-id", endpoint)

    def test_stock_string_numeric_fields_ids_clocks_and_metric_dimensions_survive(self):
        sanitizer = Sanitizer()
        attrs = [attr("duration_ms", "125"), attr("ttft_ms", "18"), attr("input_token_count", "42"),
            attr("tool_token_count", "49"), attr("auth.request_id", "req_abc123"), attr("success", "true"),
            attr("product_sku", "standard"), attr("reasoning_effort", "high")]
        expected = json.loads(json.dumps(attrs))
        expected[4]["value"]["stringValue"] = "local-1"
        self.assertEqual(sanitizer.attributes(attrs), expected)
        structural = {"timestamp": "2026-10-12T12:20:00.123456Z", "cli_version": "0.159.0",
            "aggregationTemporality": "AGGREGATION_TEMPORALITY_CUMULATIVE", "codex_turn_id": "turn-1",
            "upstream_request_id": "req_abc123", "runtime_cell_id": "cell-3", "parent_thread_id": "thread-1"}
        safe = sanitizer.value(structural)
        self.assertEqual(safe["timestamp"], "0")
        self.assertEqual(safe["upstream_request_id"], "local-1")
        self.assertEqual(safe["cli_version"], structural["cli_version"])
        self.assertEqual(safe["aggregationTemporality"], structural["aggregationTemporality"])
        for key in ("codex_turn_id", "runtime_cell_id", "parent_thread_id"):
            self.assertRegex(safe[key], r"^local-[0-9]+$")

    def test_late_collector_callback_cannot_regress_sealed_progress(self):
        progress = []
        session = self.make_capture(on_progress=progress.append)
        late = session.collector.on_change
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        number = len(progress)
        late()
        self.assertEqual(len(progress), number)
        self.assertTrue(progress[-1]["evidence_sealed"])
        self.assertEqual(session.finish(), sealed)

    def test_redacted_dimensions_are_explicit_and_do_not_claim_native_scope_complete(self):
        document = otlp("metrics", [{"name": "codex.future", "gauge": {"dataPoints": [{"asInt": "3",
            "attributes": [attr("phase", "generation"), attr("future.native.dimension", "private-category")]}]}}])
        record = sanitized_signal_records(document, "/v1/metrics")[0]
        self.assertEqual(record["_sanitization"], {"resource_excluded_attributes": 1,
            "scope_excluded_attributes": 0, "record_excluded_attributes": 1, "dimensions_complete": False})
        self.assertNotIn("private-category", json.dumps(record))

    def test_failed_sensitive_scratch_cleanup_is_visible_and_retryable(self):
        session = self.make_capture(profile=CaptureProfile(id="deep_telemetry", diagnostic_privacy_acknowledged=True))
        root = session.diagnostic_root
        with patch("AgMark.shared.telemetry.capture.subprocess.run", side_effect=PermissionError("fixture refusal")):
            sealed = session.finish(stdout(), b"", rollout(), "completed")
        self.assertEqual(sealed["sources"]["diagnostics"]["reason"], "sensitive_diagnostic_cleanup_failed")
        self.assertEqual(sealed["sources"]["diagnostics"]["state"], "partial")
        self.assertEqual(session.diagnostic_root, root)
        self.assertTrue(root.exists())
        session.close()
        self.assertFalse(root.exists())
        self.assertIsNone(session.diagnostic_root)

    def test_diagnostic_line_processing_deadline_retains_prefix_and_reports_partial(self):
        session = self.make_capture(profile=CaptureProfile(id="deep_telemetry",
            diagnostic_privacy_acknowledged=True, flush_timeout_seconds=0))
        bundle = session.diagnostic_root / "fixture"
        bundle.mkdir()
        line = json.dumps({"seq": 1, "thread_id": "thread-1", "payload": {
            "type": "inference_started", "inference_call_id": "fixture-call"}}) + "\n"
        (bundle / "trace.jsonl").write_text(line * 1000)
        original = session._record_json
        def slow_fixture_record(source, raw):
            if source == "diagnostics":
                time.sleep(.003)
            return original(source, raw)
        started = time.monotonic()
        with patch.object(session, "_record_json", side_effect=slow_fixture_record):
            session._finish_diagnostics()
        self.assertLess(time.monotonic() - started, 1)
        health = session.ledger.sources["diagnostics"]
        self.assertEqual("partial", health["state"])
        self.assertEqual("diagnostic_parse_deadline", health["processing"]["reason"])
        self.assertGreater(health["retained_events"], 0)
        self.assertLess(health["retained_events"], 1000)
        self.assertEqual("removed", health["cleanup"]["state"])

    def test_diagnostic_record_limit_and_cancellation_remain_explicit(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                session = self.make_capture(profile=CaptureProfile(id="deep_telemetry",
                    diagnostic_privacy_acknowledged=True, max_records=3),
                    cancellation_requested=lambda: cancelled)
                bundle = session.diagnostic_root / "fixture"
                bundle.mkdir()
                (bundle / "trace.jsonl").write_text('{"seq":1}\n' * 20)
                session._finish_diagnostics()
                health = session.ledger.sources["diagnostics"]
                self.assertEqual("partial", health["state"])
                self.assertEqual("diagnostic_capture_cancelled" if cancelled else "diagnostic_record_limit",
                                 health["processing"]["reason"])
                self.assertLess(health["retained_events"], 20)

    def test_diagnostic_cleanup_timeout_preserves_private_root_and_sealed_truth(self):
        session = self.make_capture(profile=CaptureProfile(id="deep_telemetry",
            diagnostic_privacy_acknowledged=True, flush_timeout_seconds=0))
        root = session.diagnostic_root
        original_run = subprocess.run
        def blocked_delete(argv, **kwargs):
            self.assertEqual(argv[:3], [sys.executable, "-I", "-c"])
            self.assertEqual(argv[-1], str(root))
            # Exercise the real timeout/reaping path using a local sleeping
            # fixture; never execute stock diagnostics or read payload data.
            return original_run([sys.executable, "-I", "-c", "import time; time.sleep(30)"], **kwargs)
        started = time.monotonic()
        with patch("AgMark.shared.telemetry.capture.subprocess.run", side_effect=blocked_delete):
            sealed = session.finish(stdout=stdout(), stderr=b"", rollout_record=rollout())
        self.assertLess(time.monotonic() - started, 1)
        self.assertTrue(validate_manifest(sealed))
        self.assertEqual("partial", sealed["sources"]["diagnostics"]["state"])
        self.assertEqual("incomplete", sealed["sources"]["diagnostics"]["cleanup"]["state"])
        self.assertEqual("diagnostic_cleanup_timeout", sealed["sources"]["diagnostics"]["cleanup"]["reason"])
        self.assertNotIn(str(root), json.dumps(sealed))
        self.assertTrue(root.exists())
        self.assertEqual(root, session.diagnostic_root)
        session.close()
        self.assertFalse(root.exists())
        self.assertEqual("incomplete", sealed["sources"]["diagnostics"]["cleanup"]["state"])
        self.assertEqual(session.finish(), sealed)

    def test_reduced_diagnostic_graph_preserves_typed_runtime_links_without_payloads(self):
        session = self.make_capture(profile=CaptureProfile(id="deep_telemetry", diagnostic_privacy_acknowledged=True))
        root = session.diagnostic_root
        bundle = root / "fixture"
        bundle.mkdir()
        execution = {"started_at_unix_ms": 100, "started_seq": 1, "ended_at_unix_ms": 150,
            "ended_seq": 9, "status": "completed"}
        state = {"schema_version": 1, "trace_id": "trace-1", "rollout_id": "rollout-1", "root_thread_id": "thread-1",
            "started_at_unix_ms": 100, "ended_at_unix_ms": 150, "status": "completed",
            "threads": {"thread-1": {"thread_id": "thread-1", "origin": {"type": "root"}, "execution": execution},
                "child-1": {"thread_id": "child-1", "origin": {"type": "spawned", "parent_thread_id": "thread-1", "spawn_edge_id": "edge-1", "task_name": "PRIVATE TASK"}, "execution": execution}},
            "code_cells": {"cell-1": {"code_cell_id": "cell-1", "runtime_cell_id": "runtime-1", "source_js": "PRIVATE CODE",
                "nested_tool_call_ids": ["tool-1"], "execution": execution}},
            "tool_calls": {"tool-1": {"tool_call_id": "tool-1", "thread_id": "thread-1", "kind": {"type": "exec_command"},
                "requester": {"type": "code_cell", "code_cell_id": "cell-1"}, "terminal_operation_id": "operation-1",
                "summary": {"label": "PRIVATE SUMMARY"}, "execution": execution}},
            "terminal_sessions": {"terminal-1": {"terminal_id": "terminal-1", "thread_id": "thread-1",
                "created_by_operation_id": "operation-1", "operation_ids": ["operation-1"], "execution": execution}},
            "terminal_operations": {"operation-1": {"operation_id": "operation-1", "terminal_id": "terminal-1", "tool_call_id": "tool-1", "kind": "exec_command", "execution": execution,
                "request": {"type": "exec_command", "command": ["PRIVATE COMMAND"], "cwd": "/PRIVATE/PATH", "yield_time_ms": 50},
                "result": {"exit_code": 0, "stdout": "PRIVATE OUTPUT", "stderr": "PRIVATE ERROR"}}},
            "interaction_edges": {"edge-1": {"edge_id": "edge-1", "kind": "spawn_agent", "source": {"type": "thread", "thread_id": "thread-1"}, "target": {"type": "thread", "thread_id": "child-1"}, "started_at_unix_ms": 102, "ended_at_unix_ms": 110}},
            "conversation_items": {"item-1": {"item_id": "item-1", "thread_id": "thread-1", "kind": "message",
                "body": {"parts": [{"type": "code", "source": "PRIVATE", "language": "js"}]},
                "produced_by": [{"type": "code_cell", "code_cell_id": "cell-1"}]}},
            "raw_payloads": {"payload-1": {"path": "PRIVATE/PATH", "authorization": "PRIVATE AUTH"}}}
        (bundle / "state.json").write_text(json.dumps(state))
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        records = [r["payload"] for r in sealed["records"] if r["source"] == "diagnostics"]
        nodes = {r["graph_object_id"]: r["node"] for r in records if r["type"] == "reduced_graph_node"}
        self.assertEqual(nodes[session.aliases.identity("tool-1")]["requester"], {"type": "code_cell", "code_cell_id": session.aliases.identity("cell-1")})
        self.assertEqual(nodes[session.aliases.identity("tool-1")]["terminal_operation_id"], session.aliases.identity("operation-1"))
        self.assertEqual(nodes[session.aliases.identity("operation-1")]["terminal_id"], session.aliases.identity("terminal-1"))
        self.assertEqual(nodes[session.aliases.identity("terminal-1")]["operation_ids"], [session.aliases.identity("operation-1")])
        self.assertEqual(nodes[session.aliases.identity("edge-1")]["source"], {"type": "thread", "thread_id": session.aliases.identity("thread-1")})
        self.assertEqual(nodes[session.aliases.identity("edge-1")]["target"], {"type": "thread", "thread_id": session.aliases.identity("child-1")})
        self.assertEqual(nodes[session.aliases.identity("cell-1")]["nested_tool_call_ids"], [session.aliases.identity("tool-1")])
        self.assertEqual(nodes[session.aliases.identity("operation-1")]["execution"],
            {**execution, "started_at_unix_ms": 0, "ended_at_unix_ms": 50})
        self.assertEqual(sealed["sources"]["diagnostics"]["reduced_graph"]["state"], "retained")
        self.assertNotIn("PRIVATE", json.dumps(sealed))
        self.assertFalse(root.exists())
        self.assertTrue(validate_manifest(sealed))

    def test_zero_trace_identifiers_cannot_create_false_correlations(self):
        sanitizer = Sanitizer()
        self.assertEqual(sanitizer.value({"traceId": "0" * 32, "spanId": "0" * 16,
            "parentSpanId": "0" * 16, "name": "codex.future"}), {})

    def test_auxiliary_root_graph_cannot_be_joined_to_the_selected_thread(self):
        session = self.make_capture(profile=CaptureProfile(id="deep_telemetry",
            diagnostic_privacy_acknowledged=True))
        bundle = session.diagnostic_root / "auxiliary"
        bundle.mkdir()
        (bundle / "state.json").write_text(json.dumps({"schema_version": 2,
            "recording_complete": True, "root_thread_id": "another-thread", "threads": {}}))
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        self.assertEqual("diagnostic_graph_root_unmatched", sealed["sources"]["diagnostics"]["reason"])
        self.assertEqual("partial", sealed["completeness"]["status"])
        self.assertFalse(any(r["payload"].get("type") == "reduced_graph" for r in sealed["records"]))
        self.assertTrue(validate_manifest(sealed))

    def test_producer_reported_loss_marks_capture_and_dimensions_partial(self):
        session = self.make_capture()
        document = otlp("traces", [{"traceId": "a" * 32, "spanId": "b" * 16, "name": "codex.future",
            "droppedAttributesCount": 2, "droppedEventsCount": 4, "droppedLinksCount": 1}])
        post(session, "traces", document)
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        health = sealed["sources"]["otel_traces"]
        self.assertEqual(health["state"], "partial")
        self.assertEqual(health["reason"], "producer_reported_dropped_telemetry")
        self.assertEqual(health["producer_reported_drops"], {"attributes": 2, "events": 4, "links": 1})
        self.assertEqual(health["dropped"], 0)
        record = next(r["payload"] for r in sealed["records"] if r["source"] == "otel_traces")
        self.assertFalse(record["_sanitization"]["dimensions_complete"])

    def test_finish_preserves_selected_host_cleanup_failure_and_progress(self):
        for state in ("partial", "failed"):
            with self.subTest(state=state):
                progress = []
                session = self.make_capture(on_progress=progress.append)
                session.ledger.count("process", partial=1)
                session.ledger.state("process", state, "selected_host_cleanup_unconfirmed")
                sealed = session.finish(stdout(), b"", rollout(), "cancelled")
                health = sealed["sources"]["process"]
                self.assertEqual(health["state"], state)
                self.assertEqual(health["reason"], "selected_host_cleanup_unconfirmed")
                self.assertEqual(health["partial"], 1)
                self.assertEqual(sealed["completeness"]["status"], "partial")
                self.assertEqual(sealed["process_status"]["status"], "cancelled")
                final_process = next(s for s in progress[-1]["sources"] if s["source_id"] == "process")
                self.assertEqual(final_process["state"], state)
                self.assertEqual(final_process["reason"], "selected_host_cleanup_unconfirmed")
                self.assertTrue(validate_manifest(sealed))

    def test_other_finish_stages_preserve_prior_source_failure_reasons(self):
        for state in ("partial", "failed"):
            with self.subTest(state=state):
                session = self.make_capture(profile=CaptureProfile(id="deep_telemetry", diagnostic_privacy_acknowledged=True))
                sources = ("stdout", "stderr", "rollout", "otel_logs", "otel_traces", "otel_metrics", "diagnostics")
                for source in sources:
                    session.ledger.count(source, partial=1)
                    session.ledger.state(source, state, "selected_host_bridge_backpressure")
                sealed = session.finish(stdout(), b"fixture stderr", rollout(), "completed")
                for source in sources:
                    self.assertEqual(sealed["sources"][source]["state"], state, source)
                    self.assertEqual(sealed["sources"][source]["reason"], "selected_host_bridge_backpressure", source)
                self.assertTrue(validate_manifest(sealed))

    def test_process_record_retention_failure_cannot_be_settled(self):
        session = self.make_capture(profile=CaptureProfile(max_records=1))
        sealed = session.finish(stdout(), b"", rollout(), "completed")
        health = sealed["sources"]["process"]
        self.assertEqual(health["state"], "partial")
        self.assertEqual(health["reason"], "capture_retention_limit")
        self.assertEqual(health["dropped"], 1)

    def test_reset_during_otlp_body_read_is_partial_without_thread_traceback(self):
        session = self.make_capture()
        post(session, "logs", otlp("logs", [{"timeUnixNano": "100", "attributes": [attr("event.name", "codex.api_request")]}]))
        entered = threading.Event()
        processed = threading.Event()
        handler = session.collector.server.RequestHandlerClass
        original_post = handler.do_POST
        session.collector.on_change = processed.set

        def observed_post(request):
            entered.set()
            return original_post(request)

        errors = io.StringIO()
        with patch.object(handler, "do_POST", observed_post), redirect_stderr(errors):
            connection = socket.create_connection(("127.0.0.1", session.collector.server.server_port), timeout=2)
            try:
                connection.sendall(b"POST /v1/logs HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 100000\r\n\r\n{")
                self.assertTrue(entered.wait(2), "receiver must admit the headers before reset")
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            finally:
                connection.close()
            self.assertTrue(processed.wait(2), "receiver must settle the interrupted request")
            sealed = session.finish(stdout(), b"", rollout(), "completed")
        health = sealed["sources"]["otel_logs"]
        self.assertEqual(health["state"], "partial")
        self.assertEqual(health["reason"], "otlp_transport_read_failed")
        self.assertEqual(health["rejected"], 1)
        self.assertEqual(health["partial"], 1)
        self.assertEqual(health["retained_events"], 1)
        self.assertNotIn("Traceback", errors.getvalue())
        self.assertNotIn("ConnectionResetError", errors.getvalue())


if __name__ == "__main__":
    unittest.main()


class EvidenceMinimizationTests(unittest.TestCase):
    def test_private_fields_unknown_numbers_labels_and_paths_are_excluded(self):
        safe = Sanitizer().value({"host.name": "Alice", "uid": 123, "device": {"count": 9},
            "future_flag": True, "name": "Alice", "type": "Alice", "phase": "Alice",
            "unit": "Alice", "cwd": "/home/Alice", "tool_name": "Alice-private-tool",
            "model": "/home/Alice/model", "usage": {"input_tokens": 9, "account_balance": 100}})
        self.assertEqual(safe, {"usage": {"input_tokens": 9}})

    def test_aliases_join_sources_without_retaining_source_identifiers(self):
        aliases = AliasRegistry()
        stdout = Sanitizer(aliases=aliases, source="stdout").value({"thread_id": "Alice@example.test"})
        otlp = Sanitizer(aliases=aliases, source="otel_traces").attributes([
            attr("conversation.id", "Alice@example.test")])
        self.assertEqual(stdout["thread_id"], otlp[0]["value"]["stringValue"])
        self.assertNotIn("Alice", json.dumps([stdout, otlp]))
        self.assertEqual(Sanitizer().value({"thread_id": "different-secret"}), stdout)

    def test_relative_source_clocks_preserve_duration_without_wall_dates(self):
        sanitizer = Sanitizer()
        safe = sanitizer.value({"startTimeUnixNano": "1700000000000000000", "endTimeUnixNano": "1700000000000000013"})
        self.assertEqual(safe, {"startTimeUnixNano": "0", "endTimeUnixNano": "13"})

    def test_runtime_inventory_excludes_unrelated_data(self):
        safe = runtime_identity({"version": "0.159.0", "launch_mode": "native",
            "hostname": "Alice", "pid": 99, "capabilities": {"token_usage_record_v1": True, "Alice": True},
            "binary_sha256": "sha256:" + "a" * 64, "runner_version": "/home/Alice"})
        self.assertNotIn("Alice", json.dumps(safe))
        self.assertNotIn("pid", safe)
        self.assertEqual(safe["capabilities"], {"token_usage_record_v1": True})

    def test_rehashed_unknown_fields_and_native_ids_are_rejected(self):
        from copy import deepcopy
        from AgMark.shared.telemetry.evidence import canonical_bytes, digest
        session = CaptureSession(runtime_version="0.159.0", invocation_id="observation:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08").start()
        capture = session.finish(stdout(), b"", rollout())
        for location in ("payload", "runtime", "source", "record", "top"):
            with self.subTest(location=location):
                bad = deepcopy(capture)
                record = bad["records"][0]
                if location == "payload":
                    record["payload"]["host_name"] = "Alice"
                    record["payload_sha256"] = digest(canonical_bytes(record["payload"]))
                elif location == "runtime": bad["runtime"]["host_name"] = "Alice"
                elif location == "source": bad["sources"]["stdout"]["host_name"] = "Alice"
                elif location == "record": record["host_name"] = "Alice"
                else: bad["host_name"] = "Alice"
                for source, health in bad["sources"].items():
                    health["records_sha256"] = digest(canonical_bytes([r for r in bad["records"] if r["source"] == source]))
                bad["integrity"].pop("manifest_sha256")
                bad["integrity"]["manifest_sha256"] = digest(canonical_bytes(bad))
                with self.assertRaises(ValueError): validate_manifest(bad)
