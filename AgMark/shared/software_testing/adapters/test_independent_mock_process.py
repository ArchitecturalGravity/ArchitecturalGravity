"""The mock runner and literal mock model remain separate process/protocol roles."""
import base64
import copy
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from AgMark.shared.adapters.Mock_Model import MockRunner, load_registration
from AgMark.shared.adapters.Mock_Model.catalog import RUNNER_ID, VERSION
from AgMark.shared.adapters._contract import sha256_bytes
from AgMark.shared.mock_model.protocol import MockRuntimeProtocol
from AgMark.shared.validation import ArtifactSource, ContractRequirement, validate_registration_binding_outcome


def request(model="mock-base", timeout=3000):
    registration = load_registration()
    raw = b"input with exact bytes\x00\xff"
    digest = sha256_bytes(raw)
    value = {key: key for key in ("accepted_generation_id", "request_id", "observation_id",
                                 "benchmark_id", "case_id", "treatment_id")}
    value.update(repetition=1, execution_boundary_fingerprint=digest,
        execution_boundary={"fingerprint": digest, "runner": {"id": RUNNER_ID, "version": VERSION},
            "provider_runtime": {"runtime_id": RUNNER_ID, "runtime_version": VERSION,
                "access_method": "local_process", "model": model},
            "controls": [{"name": "model_id", "value": model},
                {"name": "request_timeout_ms", "value": timeout}, {"name": "maximum_attempts", "value": 1},
                *registration["extensions"]["arcgrav.adapters:fixed_controls"]]},
        conversation_policy={"new_conversation": True, "reuse_prior_observation_context": False},
        prompt={"content": raw, "sha256": digest}, input={"content": raw, "sha256": digest},
        request_identity={"prompt_sha256": digest, "input_sha256": digest, "request_sha256": digest})
    return value


class IndependentMockProcessTests(unittest.TestCase):
    def test_runner_cannot_embed_model_inference_or_provider_runtime(self):
        events = []
        with patch.object(MockRuntimeProtocol, "infer", side_effect=AssertionError("parent process must never infer")):
            runner = MockRunner()
            try:
                observed = runner.execute(request(), event_callback=events.append)
            finally:
                runner.close()
        self.assertEqual("completed", observed["terminal_status"])
        evidence = observed["extensions"]["arcgrav.runner:execution"]
        self.assertEqual("mock_json_v1", evidence["request_framing"]["mode"])
        self.assertTrue(evidence["isolation"]["fresh_process"])
        self.assertTrue(evidence["isolation"]["fresh_workdir"])
        self.assertFalse(evidence["isolation"]["session_home_reused"])
        self.assertFalse(evidence["submission"]["external_provider"])
        self.assertFalse(any("codex" in key.lower() for key in observed["extensions"]))
        self.assertEqual(["input", "output"], [event["channel"] for event in events])
        ref = observed["response"]["reference"].removeprefix("extensions:/")
        self.assertTrue(base64.b64decode(observed["extensions"][ref]).startswith(b"arcgrav-mock-response-v1:"))

    def test_literal_model_failures_timeout_and_cancellation_preserve_common_outcomes(self):
        cases = (("process_failure", "failed", 3000, None),
                 ("partial_output_timeout", "timed_out", 150, None),
                 ("partial_output_timeout", "cancelled", 3000, 0.15))
        for scenario, expected, timeout, cancel_after in cases:
            with self.subTest(scenario=scenario, expected=expected):
                runner = MockRunner()
                started = time.monotonic()
                try:
                    observed = runner.execute(request("mock-base::scenario:" + scenario, timeout),
                        cancellation_requested=(lambda: time.monotonic() - started > cancel_after) if cancel_after else None)
                finally:
                    runner.close()
                self.assertEqual(expected, observed["terminal_status"], observed)
                self.assertEqual("not_produced", observed["response"]["availability"])
                self.assertIsNotNone(observed["attempts"][0]["error_code"])

    def test_pre_cancel_does_not_claim_model_submission(self):
        with patch("AgMark.shared.adapters.Mock_Model.runner.subprocess.Popen") as process:
            runner = MockRunner()
            observed = runner.execute(request(), cancellation_requested=lambda: True)
            runner.close()
        process.assert_not_called()
        self.assertEqual("cancelled", observed["terminal_status"])
        self.assertFalse(observed["extensions"]["arcgrav.runner:execution"]["submission"]["occurred"])

    def test_cancellation_during_preparation_does_not_claim_submission(self):
        checks = iter((False, True))
        with patch("AgMark.shared.adapters.Mock_Model.runner.subprocess.Popen") as process:
            runner = MockRunner()
            observed = runner.execute(request(), cancellation_requested=lambda: next(checks))
            runner.close()
        process.assert_not_called()
        self.assertEqual("cancelled", observed["terminal_status"])
        self.assertFalse(observed["extensions"]["arcgrav.runner:execution"]["submission"]["occurred"])

    def test_codex_controls_are_not_mock_configuration(self):
        value = request()
        value["execution_boundary"]["controls"].append({"name": "codex_binary", "value": "codex"})
        with patch("AgMark.shared.adapters.Mock_Model.runner.subprocess.Popen") as process:
            runner = MockRunner(); observed = runner.execute(value); runner.close()
        process.assert_not_called()
        self.assertEqual("unsupported", observed["terminal_status"])

    def test_registered_model_source_is_integrity_bound_without_broadening_roots(self):
        from AgMark.shared.runtime.orchestration.execution import _RUNNER_ARTIFACT_ROOTS
        registration = load_registration()
        root = Path(__file__).resolve().parents[4]
        allowed = tuple(p.as_posix() for p in _RUNNER_ARTIFACT_ROOTS)
        self.assertIn("AgMark/shared/mock_model", allowed)
        self.assertNotIn("AgMark/shared", allowed)
        sources = [ArtifactSource(a["artifact_id"], a["reference"], (root/a["reference"]).read_bytes())
                   for a in registration["implementation_artifacts"]]
        def validate(values):
            return validate_registration_binding_outcome(registration,
                expected_registration_id=RUNNER_ID, expected_registration_version=VERSION,
                contract_requirements=(ContractRequirement("arcgrav.shared.runner-invocation", ("2.0.0",)),),
                artifact_sources=values, allowed_artifact_roots=allowed, source_id="independent-mock")
        self.assertTrue(validate(sources).valid)
        index = next(i for i, source in enumerate(sources) if source.reference.endswith("mock_model/protocol/runtime.py"))
        original = sources[index]
        sources[index] = ArtifactSource(original.artifact_id, original.reference, original.data + b"\n# drift\n")
        self.assertFalse(validate(sources).valid)
