"""Provider-free checks of the selected-distribution worker protocol.

The worker runs in a local subprocess instead of WSL; this validates its actual
pipe/receiver lifecycle, not native Windows/WSL installation acceptance.
"""
from __future__ import annotations

import base64
import json
import hashlib
import os
from pathlib import Path
from queue import Queue
import subprocess
import shutil
import sys
import tempfile
import time
import unittest
from urllib.request import Request, urlopen

from AgMark.shared.telemetry.evidence import validate_manifest
from AgMark.shared.telemetry.profile import CaptureProfile
from AgMark.shared.telemetry.wsl import BOOTSTRAP, WslCaptureSession, WslCaptureUnavailable
from AgMark.shared.telemetry.wsl_process import GUARD_SOURCE


def streams():
    stdout = b'{"type":"thread.started","thread_id":"thread-1"}\n{"type":"turn.completed"}\n'
    raw = b'{"timestamp":"2026-10-12T00:00:00Z","type":"session_meta","payload":{"id":"thread-1"}}\n{"type":"event_msg","payload":{"type":"task_complete"}}\n'
    return stdout, {"availability": "retained", "thread_id": "thread-1", "content_base64": base64.b64encode(raw).decode()}


class WslBridgeTests(unittest.TestCase):
    def session(self, **kwargs):
        self.commands = []
        selected_executable = kwargs.pop("selected_executable", "/usr/bin/codex")
        runtime_version = kwargs.pop("runtime_version", "0.159.0")

        def local_worker(command, **options):
            self.commands.append(command)
            return subprocess.Popen((sys.executable, "-u", "-c", BOOTSTRAP), **options)

        return WslCaptureSession(runtime_version=runtime_version, invocation_id="observation:711f9c76f2c26aae25f2a8042fd0e669739ccc599d0fe9d0aa684b348d500ada",
            launch_metadata={"launcher": "wsl.exe", "distribution": "Selected Distribution", "executable": selected_executable},
            environment=dict(os.environ), popen_factory=local_worker, **kwargs)

    def test_selected_distribution_receives_all_signals_and_seals_same_invocation(self):
        progress = []
        capture = self.session(on_progress=progress.append)
        capture.runtime["runtime_binary_sha256"] = "sha256:" + "1" * 64
        capture.start()
        self.addCleanup(capture.close)
        self.assertEqual(self.commands[0][:6], ("wsl.exe", "--distribution", "Selected Distribution", "--exec", "sh", "-lc"))
        self.assertIn('unset CODEX_ROLLOUT_TRACE_ROOT', self.commands[0][6])
        self.assertLess(sum(len(part) for part in self.commands[0]), 2048)
        self.assertEqual(capture.env_overrides, {"CODEX_ROLLOUT_TRACE_ROOT": None})
        self.assertEqual(capture.runtime["receiver_environment"], "selected_distribution")
        import tomllib
        configuration = tomllib.loads("\n".join(capture.config_overrides))["otel"]
        bodies = {
            "exporter": {"resourceLogs": [{"scopeLogs": [{"logRecords": [{"attributes": [
                {"key": "event.name", "value": {"stringValue": "codex.api_request"}},
                {"key": "duration_ms", "value": {"stringValue": "3"}},
                {"key": "authorization", "value": {"stringValue": "NEVER_RETAIN"}}]}]}]}]},
            "trace_exporter": {"resourceSpans": [{"scopeSpans": [{"spans": [{"name": "try_run_sampling_request",
                "traceId": "a" * 32, "spanId": "b" * 16}]}]}]},
            "metrics_exporter": {"resourceMetrics": [{"scopeMetrics": [{"metrics": [{"name": "codex.api_request",
                "sum": {"aggregationTemporality": 2, "dataPoints": [{"asInt": "1"}]}}]}]}]},
        }
        for exporter, body in bodies.items():
            endpoint = configuration[exporter]["otlp-http"]["endpoint"]
            request = Request(endpoint, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=2) as response:
                self.assertEqual(response.status, 200)
        stdout, rollout = streams()
        capture.ingest_stdout(stdout[:35])
        capture.ingest_stdout(stdout[35:])
        capture.ingest_stderr(b"private stderr content")
        manifest = capture.finish(stdout=stdout, stderr=b"private stderr content", rollout_record=rollout)
        self.assertTrue(validate_manifest(manifest))
        self.assertEqual(manifest["runtime"]["launch_mode"], "wsl")
        self.assertEqual(manifest["runtime"]["runtime_binary_sha256"], "sha256:" + "1" * 64)
        for source in ("otel_logs", "otel_traces", "otel_metrics", "stdout", "stderr", "rollout"):
            self.assertEqual(manifest["sources"][source]["state"], "settled")
        self.assertNotIn("NEVER_RETAIN", json.dumps(manifest))
        self.assertNotIn("private stderr content", json.dumps(manifest))
        self.assertTrue(any(event["phase"] == "collector_readiness" for event in progress))
        self.assertTrue(progress[-1]["evidence_sealed"])
        self.assertIsNotNone(capture._process.poll())
        self.assertEqual(capture.finish(), manifest)

    def test_sensitive_root_is_remote_opt_in_and_removed_after_finish(self):
        capture = self.session(profile=CaptureProfile("deep_telemetry", diagnostic_privacy_acknowledged=True)).start()
        self.addCleanup(capture.close)
        root = Path(capture.env_overrides["CODEX_ROLLOUT_TRACE_ROOT"])
        self.assertTrue(root.is_dir())
        bundle = root / "bundle"
        bundle.mkdir()
        (bundle / "trace.jsonl").write_text(json.dumps({"seq": 1, "thread_id": "thread-1", "payload": {
            "type": "inference_completed", "inference_call_id": "call-1", "response_id": "resp-1",
            "text": "PRIVATE_PAYLOAD"}}) + "\n")
        # Do not execute stock tracing or any provider, even in this opt-in fixture.
        stdout, rollout = streams()
        manifest = capture.finish(stdout=stdout, stderr=b"", rollout_record=rollout)
        self.assertFalse(root.exists())
        self.assertNotIn("PRIVATE_PAYLOAD", json.dumps(manifest))
        self.assertGreater(manifest["sources"]["diagnostics"]["retained_events"], 0)

    def test_repeated_runs_use_distinct_receiver_and_reject_restart(self):
        first = self.session().start()
        first_config = first.config_overrides
        first.close()
        with self.assertRaises(RuntimeError):
            first.start()
        second = self.session().start()
        self.addCleanup(second.close)
        self.assertNotEqual(first_config, second.config_overrides)
        manifest = second.close()
        self.assertEqual(manifest["process_status"]["status"], "cancelled")
        self.assertEqual(manifest["sources"]["otel_logs"]["received_events"], 0)

    def test_backpressure_is_nonblocking_and_retained_as_partial_health(self):
        capture = self.session()
        capture._queue = Queue(maxsize=1)
        capture._started = True
        capture._queue.put({"op": "health"})
        started = time.monotonic()
        capture.ingest_stdout(b"x" * 131072)
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertEqual(capture._dropped["stdout"], 2)
        capture._queue.get_nowait()
        capture._started = False
        capture.start()
        self.addCleanup(capture.close)
        stdout, rollout = streams()
        manifest = capture.finish(stdout=stdout, stderr=b"", rollout_record=rollout)
        self.assertEqual(manifest["sources"]["stdout"]["dropped"], 2)
        self.assertEqual(manifest["completeness"]["status"], "partial")

    def test_unavailable_selected_worker_never_reports_collector_readiness(self):
        def exited_worker(command, **options):
            return subprocess.Popen((sys.executable, "-c", "pass"), **options)
        progress = []
        capture = WslCaptureSession(runtime_version="0.159.0", invocation_id="observation:79f68f315287727f486d3d7ee002ae9caa5c5588bb91d84285f426de44051f4b",
            launch_metadata={"launcher": "wsl.exe", "distribution": "Missing", "executable": "codex"},
            popen_factory=exited_worker, on_progress=progress.append, startup_timeout_seconds=0.5)
        started = time.monotonic()
        with self.assertRaises(WslCaptureUnavailable):
            capture.start()
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(progress, [])
        self.assertIsNotNone(capture._process.poll())

    def test_different_runtime_version_starts_selected_host_collector(self):
        capture = self.session(runtime_version="0.160.0").start()
        self.addCleanup(capture.close)
        self.assertEqual("0.160.0", capture.runtime["version"])
        self.assertEqual("supported", capture.runtime["capability_status"])
        self.assertTrue(any("otel.metrics_exporter=" in value for value in capture.config_overrides))

    def test_explicitly_unsupported_capability_is_rejected_before_starting_worker(self):
        capture = self.session()
        capture.runtime.update(version="0.158.0", capability_status="unsupported")
        with self.assertRaises(WslCaptureUnavailable):
            capture.start()
        self.assertEqual(self.commands, [])

    def test_binary_identity_is_observed_in_worker_before_readiness(self):
        capture = self.session(selected_executable=sys.executable)
        capture.runtime.update(binary_sha256=None, binary_hash_reason="host_cannot_read")
        capture.start()
        self.addCleanup(capture.close)
        expected = "sha256:" + hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        self.assertEqual(capture.runtime["binary_sha256"], expected)
        self.assertIsNone(capture.runtime["binary_hash_reason"])
        self.assertEqual(capture.close()["runtime"]["binary_sha256"], expected)

    def _guarded_sleep(self, capture):
        process = subprocess.Popen((sys.executable, "-c", GUARD_SOURCE, capture.process_control_path,
            sys.executable, "-c", "import time; time.sleep(30)"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def cleanup():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 3
        while not Path(capture.process_control_path).exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(Path(capture.process_control_path).is_file())
        return process

    def test_cancel_stops_only_owned_group_before_rollout_settlement(self):
        capture = self.session().start()
        self.addCleanup(capture.close)
        unrelated = subprocess.Popen((sys.executable, "-c", "import time; time.sleep(30)"))
        self.addCleanup(lambda: unrelated.wait(timeout=3))
        self.addCleanup(unrelated.terminate)
        guard = self._guarded_sleep(capture)
        result = capture.stop_execution()
        self.assertIn(result["status"], {"stopped", "already_exited"})
        guard.wait(timeout=3)
        self.assertIsNone(unrelated.poll())
        root = Path(capture.process_control_path).parent
        manifest = capture.finish(process_status="cancelled")
        self.assertFalse(root.exists())
        self.assertEqual(manifest["process_status"]["status"], "cancelled")

    def test_worker_eof_stops_owned_group_and_disposes_control_directory(self):
        capture = self.session().start()
        self.addCleanup(capture._dispose)
        guard = self._guarded_sleep(capture)
        root = Path(capture.process_control_path).parent
        capture._queue.put(None)
        capture._process.wait(timeout=4)
        guard.wait(timeout=3)
        self.assertFalse(root.exists())

    def test_unconfirmed_cleanup_is_partial_and_keeps_private_recovery_control(self):
        capture = self.session().start()
        self.addCleanup(capture.close)
        root = Path(capture.process_control_path).parent
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        (root / ".agmark-process-owner").write_text("invalid-owner", encoding="ascii")
        self.assertEqual(capture.stop_execution()["status"], "unavailable")
        manifest = capture.finish(process_status="cancelled")
        self.assertGreater(manifest["sources"]["process"]["partial"], 0)
        self.assertEqual(manifest["completeness"]["status"], "partial")
        self.assertTrue(root.exists())


if __name__ == "__main__":
    unittest.main()
