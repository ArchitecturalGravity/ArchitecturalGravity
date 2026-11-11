"""Offline production-runner coverage of the selected-distribution bridge.

Only the wsl.exe boundary is replaced by local sh: the production pipe transport,
wrapper, process guard, worker, receiver, capture and normalizer all execute.
This is not actual Windows/WSL or live-provider acceptance evidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.adapters.Codex_CLI import CodexCliRunner
from AgMark.shared.adapters.Codex_CLI.runner import _SubprocessTransport
from AgMark.shared.adapters.Codex_CLI.session_capture import read_session
from AgMark.shared.software_testing.adapters.codex_cli.test_runner import _boundary, _request
from AgMark.shared.telemetry.evidence import validate_manifest
from AgMark.shared.telemetry.wsl import WslCaptureSession


FAKE_CODEX = r'''
import json, os, pathlib, sys, time, tomllib, uuid
from urllib.request import Request, urlopen
fixture = pathlib.Path(FIXTURE)
if '--version' in sys.argv:
    print('codex-cli 0.159.0')
    raise SystemExit(0)
if '--help' in sys.argv:
    print('Usage: codex exec --json --ignore-user-config --approve-for-me')
    raise SystemExit(0)
arguments = sys.argv[1:]
(fixture / 'launched.json').write_text(json.dumps({'args': arguments, 'cwd': os.getcwd(), 'trace_root': os.environ.get('CODEX_ROLLOUT_TRACE_ROOT')}))
sys.stdin.buffer.read()
overrides = [arguments[i + 1] for i, arg in enumerate(arguments[:-1]) if arg == '-c']
configuration = tomllib.loads('\n'.join(overrides))['otel']
documents = {
    'exporter': {'resourceLogs': [{'scopeLogs': [{'logRecords': [{'attributes': [
        {'key':'event.name','value':{'stringValue':'codex.api_request'}},
        {'key':'auth.request_id','value':{'stringValue':'req-offline-wsl'}},
        {'key':'duration_ms','value':{'stringValue':'12'}},
        {'key':'authorization','value':{'stringValue':'Bearer offline-discard'}}]}]}]}]},
    'trace_exporter': {'resourceSpans':[{'scopeSpans':[{'spans':[{'name':'try_run_sampling_request',
        'traceId':'a'*32,'spanId':'b'*16,'startTimeUnixNano':'100','endTimeUnixNano':'200'}]}]}]},
    'metrics_exporter': {'resourceMetrics':[{'scopeMetrics':[{'metrics':[{'name':'codex.api_request.duration_ms',
        'unit':'ms','histogram':{'aggregationTemporality':2,'dataPoints':[{'count':'1','sum':12,
        'bucketCounts':['0','1'],'explicitBounds':[10]}]}}]}]}]},
}
for exporter, document in documents.items():
    endpoint = configuration[exporter]['otlp-http']['endpoint']
    with urlopen(Request(endpoint, data=json.dumps(document).encode(), headers={'Content-Type':'application/json'}), timeout=3) as reply:
        assert reply.status == 200
thread_id = str(uuid.uuid4())
print(json.dumps({'type':'thread.started','thread_id':thread_id}), flush=True)
rollout = fixture / (thread_id + '.jsonl')
rollout.write_text(json.dumps({'timestamp':'2026-10-12T00:00:00Z','type':'session_meta','payload':{'id':thread_id}}) + '\n')
if (fixture / 'cancel-mode').exists():
    (fixture / 'cancel-ready').write_text('ready')
    time.sleep(30)
usage = {'input_tokens':100,'cached_input_tokens':20,'output_tokens':8,'reasoning_output_tokens':2,'total_tokens':108}
with rollout.open('a') as handle:
    handle.write(json.dumps({'timestamp':'2026-10-12T00:00:01Z','type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':usage}}})+'\n')
    handle.write(json.dumps({'timestamp':'2026-10-12T00:00:01Z','type':'event_msg','payload':{'type':'task_complete'}})+'\n')
print(json.dumps({'type':'item.completed','item':{'id':'answer','type':'agent_message','text':'offline WSL answer'}}), flush=True)
print(json.dumps({'type':'turn.completed','usage':usage}), flush=True)
'''


class LocalSelectedHostTransport(_SubprocessTransport):
    def __init__(self, fixture):
        self.fixture = fixture
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append((tuple(argv), kwargs.get("input_bytes") is not None))
        if tuple(argv)[1:2] != ("--distribution",) or argv[3] != "--exec":
            raise AssertionError("runner escaped selected distribution")
        return super().run(tuple(argv[4:]), **kwargs)

    def read_session(self, thread_id, *, launch_environment, environment):
        return read_session(thread_id, root=self.fixture, timeout_seconds=0.2)


@unittest.skipUnless(os.name == "posix", "local sh and Linux process fixture required")
class WslRunnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="agmark-wsl-runner-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = Path(self.temporary.name)
        self.binary = self.fixture / "offline codex"
        self.binary.write_text("#!" + sys.executable + "\nFIXTURE = " + repr(str(self.fixture)) + "\n" + FAKE_CODEX)
        self.binary.chmod(0o700)
        self.transport = LocalSelectedHostTransport(self.fixture)
        self.bridge_instances = []
        self.bridge_commands = []
        self.runner = CodexCliRunner(transport=self.transport, platform_name="nt", executable_resolver=lambda value: value,
            launch_selection={"codex_binary": str(self.binary), "wsl_distribution": "Selected Fixture Distribution"})

    def request(self, suffix="wsl"):
        boundary = _boundary(launch_mode="wsl", runtime_version="0.159.0", timeout_ms=10000)
        boundary["controls"].append({"name":"capture_mode","value":"telemetry"})
        return _request(boundary, suffix=suffix)

    def bridge(self, *args, **kwargs):
        def local_worker(command, **options):
            self.bridge_commands.append(command)
            return subprocess.Popen(command[4:], **options)
        instance = WslCaptureSession(*args, **kwargs, popen_factory=local_worker)
        self.bridge_instances.append(instance)
        self.addCleanup(instance.close)
        return instance

    def test_production_wrapper_and_bridge_capture_all_three_signals(self):
        request = self.request()
        request["execution_boundary"]["controls"].append({"name": "reasoning_effort", "value": "high"})
        with patch("AgMark.shared.telemetry.wsl.WslCaptureSession", side_effect=self.bridge), \
                patch.object(self.runner, "_resolve_reasoning_effort", return_value="high"):
            observation = self.runner.execute(request)
        self.assertEqual(observation["terminal_status"], "completed", observation.get("extensions"))
        capture = observation["extensions"]["agmark.telemetry:capture"]
        self.assertTrue(validate_manifest(capture))
        self.assertEqual(capture["runtime"]["launch_mode"], "wsl")
        self.assertEqual(capture["runtime"]["receiver_environment"], "selected_distribution")
        self.assertEqual(capture["runtime"]["binary_hash_reason"], None)
        for name in ("otel_logs", "otel_traces", "otel_metrics", "stdout", "rollout"):
            self.assertGreater(capture["sources"][name]["received_events"], 0)
        self.assertNotIn("offline-discard", json.dumps(capture))
        self.assertIn("agmark.telemetry:normalized", observation["extensions"])
        launched = json.loads((self.fixture / "launched.json").read_text())
        self.assertIsNone(launched["trace_root"])
        self.assertEqual(launched["args"][0], "exec")
        self.assertEqual(launched["args"][-1], "-")
        self.assertEqual(launched["args"].count("-c"), 9)
        self.assertIn('model_reasoning_effort="high"', launched["args"])
        execution_command = next(argv for argv, actual in self.transport.calls if actual)
        self.assertEqual(execution_command[2], "Selected Fixture Distribution")
        self.assertIn('python3 -c "$guard_code" "$process_control" "$@"', execution_command[6])
        self.assertNotIn("otel.exporter=", execution_command[6])
        self.assertFalse(Path(self.bridge_instances[0].process_control_path).parent.exists())

    def test_selected_worker_start_failure_blocks_original_without_fallback(self):
        def dead_bridge(*args, **kwargs):
            def exited(command, **options):
                return subprocess.Popen((sys.executable, "-c", "pass"), **options)
            return WslCaptureSession(*args, **kwargs, popen_factory=exited, startup_timeout_seconds=0.5)
        with patch("AgMark.shared.telemetry.wsl.WslCaptureSession", side_effect=dead_bridge):
            observation = self.runner.execute(self.request("failed-worker"))
        self.assertEqual(observation["terminal_status"], "unsupported")
        self.assertFalse(any(actual for _, actual in self.transport.calls))
        self.assertFalse((self.fixture / "launched.json").exists())

    def test_cancellation_seals_partial_and_preserves_unrelated_process(self):
        (self.fixture / "cancel-mode").touch()
        sibling = subprocess.Popen((sys.executable, "-c", "import time; time.sleep(30)"))
        self.addCleanup(lambda: sibling.wait(timeout=3))
        self.addCleanup(sibling.terminate)
        with patch("AgMark.shared.telemetry.wsl.WslCaptureSession", side_effect=self.bridge):
            observation = self.runner.execute(self.request("cancelled"),
                cancellation_requested=lambda: (self.fixture / "cancel-ready").exists())
        self.assertEqual(observation["terminal_status"], "cancelled")
        capture = observation["extensions"]["agmark.telemetry:capture"]
        self.assertTrue(validate_manifest(capture))
        self.assertEqual(capture["completeness"]["status"], "partial")
        self.assertEqual(capture["process_status"]["status"], "cancelled")
        self.assertGreater(capture["sources"]["otel_metrics"]["received_events"], 0)
        self.assertIsNone(sibling.poll())
        self.assertFalse(Path(self.bridge_instances[0].process_control_path).parent.exists())


if __name__ == "__main__":
    unittest.main()
