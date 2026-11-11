"""Common lifecycle contract across distinct, independently configured adapters.

Codex uses an injected local transport. Mock uses its own bundled JSON worker.
Configurations, protocols and telemetry are deliberately not compared for equality.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from AgMark.shared.adapters.Codex_CLI import CodexCliRunner, load_registration as codex_registration
from AgMark.shared.adapters.Mock_Model import MockRunner, load_registration as mock_registration
from AgMark.shared.adapters.execution import validate_execution_evidence, validate_retained_parity_observation, InvocationCancelled
from AgMark.shared.adapters.execution.live_view import LiveViewControl
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef
from AgMark.shared.software_testing.adapters.mock_model_support import resolve_model_identity
from AgMark.shared.software_testing.adapters.codex_cli.test_runner import FakeCodexTransport, _boundary


def request(boundary, *, suffix="contract"):
    prompt, data = b"exact prompt\r\n", b"exact input\x00"
    digest = lambda value: "sha256:" + hashlib.sha256(value).hexdigest()
    return {"accepted_generation_id": "generation-contract", "request_id": "request-" + suffix,
        "observation_id": "observation:" + hashlib.sha256(suffix.encode("utf-8")).hexdigest(), "benchmark_id": "contract", "case_id": "case",
        "treatment_id": "treatment", "repetition": 1,
        "execution_boundary_fingerprint": boundary["fingerprint"], "execution_boundary": copy.deepcopy(boundary),
        "conversation_policy": {"new_conversation": True, "reuse_prior_observation_context": False},
        "prompt": {"content": prompt, "sha256": digest(prompt)},
        "input": {"content": data, "sha256": digest(data)},
        "request_identity": {"prompt_sha256": digest(prompt), "input_sha256": digest(data),
                             "request_sha256": digest(suffix.encode())}}


def mock_boundary(model="mock-base", *, timeout=2000):
    runtime, controls = resolve_model_identity(model)
    controls["request_timeout_ms"] = timeout
    return ExecutionBoundary.build(boundary_id="mock-contract", framework=IdentityRef("framework", "1.0.0"),
        runner=IdentityRef("arcgrav.mock-model.runner", "1.0.0"), provider_runtime=runtime,
        controls=controls).to_dict()


class ScenarioCodexTransport(FakeCodexTransport):
    """Offline protocol fixture; never starts a CLI or reads a session directory."""
    def __init__(self, scenario):
        super().__init__()
        self.scenario = scenario

    def run_streaming(self, argv, *, on_stdout=None, on_input=None,
                      cancellation_requested=None, **kwargs):
        if kwargs["input_bytes"] is None:
            return self.run(argv, **kwargs)
        if cancellation_requested and cancellation_requested():
            raise InvocationCancelled()
        if on_input:
            on_input()
        partial = self.scenario.startswith("partial_output")
        self.response = b"partial answer\r\n" if partial else b"exact final answer\n"
        if self.scenario in {"timeout", "cancellation", "process_failure"}:
            self.response = b""
        result = self.run(argv, **kwargs)
        stdout = result["stdout"] if partial or self.scenario == "completed" else b""
        stderr = b"fixture diagnostic\r\n" if self.scenario != "completed" else b""
        if stdout and on_stdout:
            # Exercise incremental decoding across arbitrary byte boundaries.
            midpoint = len(stdout) // 2
            on_stdout(stdout[:midpoint]); on_stdout(stdout[midpoint:])
        if "cancellation" in self.scenario:
            if not cancellation_requested or not cancellation_requested():
                raise AssertionError("fixture cancellation must be requested by caller")
            raise InvocationCancelled(stdout=stdout, stderr=stderr)
        if "timeout" in self.scenario:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout_ms"] / 1000,
                                          output=stdout, stderr=stderr)
        return {"returncode": 24 if "failure" in self.scenario else 0,
                "stdout": stdout, "stderr": stderr}


class RegisteredRunnerContractTests(unittest.TestCase):
    def setUp(self):
        # Fail closed if an offline fixture ever falls through to a real CLI.
        real_popen = subprocess.Popen
        def local_worker_only(command, *args, **kwargs):
            self.assertEqual(sys.executable, command[0])
            self.assertEqual(("-I", "-c"), tuple(command[1:3]))
            self.assertIn("from AgMark.shared.adapters.Mock_Model.worker import main", command[3])
            return real_popen(command, *args, **kwargs)
        self.enterContext(patch("subprocess.Popen", side_effect=local_worker_only))
        self.enterContext(patch('AgMark.shared.adapters.Codex_CLI.model_discovery._run_interactive_model_list',
            return_value={"data": [{"model": "fixture-model", "displayName": "Fixture", "isDefault": True,
                "supportedReasoningEfforts": [{"reasoningEffort": "medium", "description": "Balanced"}], "defaultReasoningEffort": "medium"}], "nextCursor": None}))

    def adapters(self, scenario="completed"):
        transport = ScenarioCodexTransport(scenario)
        codex = CodexCliRunner(transport=transport, executable_resolver=lambda _: "/controlled/codex-fixture", platform_name="posix")
        boundary = _boundary(model_id="fixture-model")
        boundary["controls"].append({"name": "reasoning_effort", "value": "medium"})
        mock = MockRunner()
        self.addCleanup(codex.close); self.addCleanup(mock.close)
        return ((codex, request(boundary), "openai.codex-cli"),
                (mock, request(mock_boundary("mock-base::scenario:" + scenario,
                                              timeout=1000)), "arcgrav.mock-model.runner"))

    def assert_common_observation(self, observed, invocation, identity, status):
        validate_retained_parity_observation(observed)
        evidence = observed["extensions"]["arcgrav.runner:execution"]
        validate_execution_evidence(evidence)
        self.assertEqual(status, observed["terminal_status"], observed)
        for field in ("accepted_generation_id", "request_id", "observation_id", "case_id",
                      "treatment_id", "repetition", "execution_boundary_fingerprint"):
            self.assertEqual(invocation[field], observed[field])
        self.assertEqual(identity, observed["runner"]["id"])
        self.assertEqual(1, len(observed["attempts"]))
        return evidence

    def retained_bytes(self, observed, channel):
        reference = channel["reference"]
        self.assertTrue(reference.startswith("extensions:/"))
        raw = base64.b64decode(observed["extensions"][reference[len("extensions:/"):]], validate=True)
        self.assertEqual(len(raw), channel["byte_length"])
        self.assertEqual("sha256:" + hashlib.sha256(raw).hexdigest(), channel["sha256"])
        return raw

    def assert_process_excluded(self, observed, channel):
        self.assertEqual({"availability": "excluded", "sha256": None, "byte_length": None, "reference": None}, channel)
        self.assertNotIn("arcgrav.runner:process_stdout_base64", observed["extensions"])
        self.assertNotIn("arcgrav.runner:process_stderr_base64", observed["extensions"])

    def test_common_failure_timeout_and_partial_output_contract(self):
        for scenario, status in (("process_failure", "failed"), ("timeout", "timed_out"),
                ("partial_output_failure", "failed"), ("partial_output_timeout", "timed_out")):
            for adapter, invocation, identity in self.adapters(scenario):
                with self.subTest(adapter=identity, scenario=scenario):
                    original = copy.deepcopy(invocation)
                    observed = adapter.execute(invocation)
                    self.assertEqual(original, invocation)
                    evidence = self.assert_common_observation(observed, invocation, identity, status)
                    self.assertTrue(evidence["submission"]["occurred"])
                    self.assertNotEqual("completed", observed["terminal_status"])
                    self.assertNotEqual("retained", observed["response"]["availability"])
                    self.assertIsNotNone(evidence["error"]["code"])
                    if scenario.startswith("partial_output"):
                        for name in ("stdout", "stderr"):
                            self.assert_process_excluded(observed, evidence["process"][name])

    def test_common_cancellation_excludes_partial_streams_from_retention(self):
        for adapter, invocation, identity in self.adapters("partial_output_cancellation"):
            with self.subTest(adapter=identity):
                events = []
                def cancelled():
                    return any(e["channel"] == "output" and e["text"] for e in events)
                observed = adapter.execute(invocation, event_callback=events.append,
                                           cancellation_requested=cancelled)
                evidence = self.assert_common_observation(observed, invocation, identity, "cancelled")
                self.assertTrue(cancelled())
                self.assertTrue(evidence["submission"]["occurred"])
                self.assertNotEqual("retained", observed["response"]["availability"])
                for name in ("stdout", "stderr"):
                    self.assert_process_excluded(observed, evidence["process"][name])

    def test_common_stream_visibility_and_callback_failure_do_not_change_authority(self):
        for adapter, invocation, identity in self.adapters():
            with self.subTest(adapter=identity):
                events = []
                visible = adapter.execute(invocation, event_callback=events.append)
                self.assert_common_observation(visible, invocation, identity, "completed")
                self.assertTrue(any(e["channel"] == "input" for e in events))
                self.assertTrue(any(e["channel"] == "output" and e["text"] for e in events))
                presented = ""
                for event in events:
                    if event["channel"] == "output":
                        presented = event["text"] if event.get("mode") == "snapshot" else presented + event["text"]
                response = visible["response"]
                self.assertEqual(self.retained_bytes(visible, response).decode("utf-8"), presented)
                def broken_callback(event):
                    raise RuntimeError("presentation failure")
                hidden_events = []
                hidden = adapter.execute(invocation, event_callback=hidden_events.append,
                                         live_view_control=LiveViewControl(enabled=False))
                broken = adapter.execute(invocation, event_callback=broken_callback)
                self.assertEqual([], hidden_events)
                for result in (hidden, broken):
                    self.assert_common_observation(result, invocation, identity, "completed")
                    self.assertEqual(visible["response"]["sha256"], result["response"]["sha256"])

    def test_common_raw_process_reintroduction_is_rejected(self):
        for adapter, invocation, identity in self.adapters():
            with self.subTest(adapter=identity):
                observed = adapter.execute(invocation)
                self.assert_common_observation(observed, invocation, identity, "completed")
                channel = observed["extensions"]["arcgrav.runner:execution"]["process"]["stdout"]
                self.assert_process_excluded(observed, channel)
                tampered = copy.deepcopy(observed)
                tampered["extensions"]["arcgrav.runner:process_stdout_base64"] = base64.b64encode(b"private process output").decode()
                with self.assertRaises(ValueError):
                    validate_retained_parity_observation(tampered)

    def test_common_isolation_and_result_immutability_across_observations(self):
        for adapter, invocation, identity in self.adapters():
            with self.subTest(adapter=identity):
                workdirs = []
                from AgMark.shared.adapters.execution import orchestration
                real_mkdtemp = orchestration.tempfile.mkdtemp
                def record_workdir(*args, **kwargs):
                    result = real_mkdtemp(*args, **kwargs)
                    workdirs.append(Path(result))
                    return result
                with patch.object(orchestration.tempfile, "mkdtemp", side_effect=record_workdir):
                    first = adapter.execute(invocation)
                    frozen = copy.deepcopy(first)
                    second_request = request(invocation["execution_boundary"], suffix="next")
                    second = adapter.execute(second_request)
                for observed, accepted in ((first, invocation), (second, second_request)):
                    evidence = self.assert_common_observation(observed, accepted, identity, "completed")
                    isolation = evidence["isolation"]
                    self.assertTrue(isolation["fresh_process"])
                    self.assertTrue(isolation["fresh_workdir"])
                    self.assertFalse(isolation["prior_observation_context_reused"])
                self.assertGreaterEqual(len(workdirs), 2)
                self.assertEqual(len(workdirs), len(set(workdirs)))
                self.assertTrue(all(not path.exists() for path in workdirs))
                adapter.close(); adapter.close()
                self.assertEqual(frozen, first)

    def test_distinct_entrypoints_and_adapter_owned_configuration(self):
        live, mock = codex_registration(), mock_registration()
        self.assertNotEqual(live["extensions"]["arcgrav.adapters:entry_point"], mock["extensions"]["arcgrav.adapters:entry_point"])
        names = lambda registration: {v["name"] for v in registration["extensions"]["arcgrav.adapters:supported_controls"]}
        self.assertIn("reasoning_effort", names(live))
        self.assertNotIn("reasoning_effort", names(mock))
        self.assertNotIn("codex_binary", names(mock))
        self.assertNotIn("capture_mode", names(mock))
        self.assertEqual({"model_id", "request_timeout_ms", "maximum_attempts"}, names(mock))

    def test_stable_description_and_independent_close_contract(self):
        for adapter, invocation, identity in self.adapters():
            with self.subTest(adapter=identity):
                self.assertEqual(adapter.describe(), adapter.describe())
                self.assertEqual(identity, adapter.describe()["runner"]["id"])
                adapter.close(); adapter.close()
                with self.assertRaises(RuntimeError):
                    adapter.execute(invocation)

    def test_normalized_identity_terminal_and_retention_contract(self):
        for adapter, invocation, identity in self.adapters():
            with self.subTest(adapter=identity):
                observed = adapter.execute(invocation)
                validate_retained_parity_observation(observed)
                validate_execution_evidence(observed["extensions"]["arcgrav.runner:execution"])
                self.assertEqual("completed", observed["terminal_status"], observed)
                for field in ("accepted_generation_id", "request_id", "observation_id", "case_id", "treatment_id", "repetition", "execution_boundary_fingerprint"):
                    self.assertEqual(invocation[field], observed[field])
                self.assertEqual(identity, observed["runner"]["id"])
                self.assertEqual("retained", observed["response"]["availability"])
                self.assertTrue(observed["response"]["sha256"].startswith("sha256:"))

    def test_unsupported_configuration_never_submits(self):
        for adapter, invocation, identity in self.adapters():
            with self.subTest(adapter=identity):
                invocation["execution_boundary"]["controls"].append({"name": "unknown_required_control", "value": True})
                with patch("subprocess.Popen", side_effect=AssertionError("unsupported request must not launch")):
                    observed = adapter.execute(invocation)
                self.assertEqual("unsupported", observed["terminal_status"])
                self.assertEqual("not_produced", observed["response"]["availability"])
                self.assertFalse(observed["extensions"].get("arcgrav.runner:execution", {}).get("submission", {}).get("occurred", False))

    def test_mock_execution_does_not_call_codex_or_claim_provider_telemetry(self):
        runner = MockRunner(); self.addCleanup(runner.close)
        with patch.object(CodexCliRunner, "execute", side_effect=AssertionError("wrong adapter")):
            observed = runner.execute(request(mock_boundary()))
        evidence = observed["extensions"]["arcgrav.runner:execution"]
        self.assertFalse(evidence["submission"]["external_provider"])
        self.assertNotIn("openai.codex_cli:session-record", observed["extensions"])
        self.assertNotIn("openai.codex_cli:session-capture", observed["extensions"])
        self.assertFalse(runner.describe()["telemetry"]["provider_usage"])
        self.assertFalse(runner.describe()["telemetry"]["persisted_session"])

    def test_dispatch_factory_is_not_limited_to_two_builtin_adapter_classes(self):
        from AgMark.shared.runtime.orchestration.execution import _new_runner_instance
        class ThirdAdapter:
            def __init__(self, *, registration): self.registration = registration
            def describe(self): return {"runner": {"id": "third.adapter", "version": "1.0.0"}}
            def execute(self, request): return request
            def close(self): pass
        metadata = {"registration_id": "third.adapter", "extensions": {"third:options": {"mode": "custom"}}}
        instance = _new_runner_instance(SimpleNamespace(factory=ThirdAdapter, registration=metadata))
        self.assertIsInstance(instance, ThirdAdapter)
        self.assertEqual(metadata, instance.registration)
        self.assertIsNot(metadata, instance.registration)
