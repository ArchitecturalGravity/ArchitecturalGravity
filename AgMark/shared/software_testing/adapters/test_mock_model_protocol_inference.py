"""Conformance tests for provider-neutral mock-model inference."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import call, patch

from AgMark.shared.mock_model.protocol import (
    INFERENCE_OPERATION,
    MockRuntimeProtocol,
    ModelCatalogEntry,
    ModelProfileMapping,
    ProtocolInferenceError,
)
from AgMark.shared.mock_model.scenarios import EXECUTION_REJECTION_SCENARIO


class MockRuntimeProtocolInferenceTests(unittest.TestCase):
    def _protocol(self) -> MockRuntimeProtocol:
        return MockRuntimeProtocol(
            runtime_id="arcgrav.mock-model.test-runtime",
            runtime_version="2.0.0",
            models=(
                ModelCatalogEntry(
                    model_id="mock-base",
                    label="Mock Base",
                    is_default=True,
                ),
                ModelCatalogEntry(
                    model_id="mock-completed",
                    label="Completed Profile",
                    profile=ModelProfileMapping(
                        base_model_id="mock-base",
                        scenario_id="completed",
                    ),
                ),
                ModelCatalogEntry(
                    model_id="mock-execution-rejection",
                    label="Execution Rejection Profile",
                    profile=ModelProfileMapping(
                        base_model_id="mock-base",
                        scenario_id=EXECUTION_REJECTION_SCENARIO,
                    ),
                ),
                ModelCatalogEntry(
                    model_id="mock-timeout",
                    label="Timeout Profile",
                    profile=ModelProfileMapping(
                        base_model_id="mock-base",
                        scenario_id="timeout",
                    ),
                ),
                ModelCatalogEntry(
                    model_id="mock-cancellation",
                    label="Cancellation Profile",
                    profile=ModelProfileMapping(
                        base_model_id="mock-base",
                        scenario_id="cancellation",
                    ),
                ),
            ),
        )

    def test_inference_is_deterministic_and_byte_exact_in_its_inputs(self) -> None:
        protocol = self._protocol()

        first = protocol.infer(
            model_id="mock-base",
            request_bytes=b"request\x00bytes\n",
            invocation_id="invocation-1",
        )
        repeated = protocol.infer(
            model_id="mock-base",
            request_bytes=b"request\x00bytes\n",
            invocation_id="invocation-1",
        )
        different_bytes = protocol.infer(
            model_id="mock-base",
            request_bytes=b"request\x00bytes",
            invocation_id="invocation-1",
        )
        different_identity = protocol.infer(
            model_id="mock-base",
            request_bytes=b"request\x00bytes\n",
            invocation_id="invocation-2",
        )

        self.assertEqual(first, repeated)
        self.assertNotEqual(first.response, different_bytes.response)
        self.assertNotEqual(first.response, different_identity.response)
        self.assertTrue(first.response)
        self.assertEqual(b"", first.diagnostic)
        self.assertTrue(first.synthetic)
        with self.assertRaises(FrozenInstanceError):
            first.response = b"mutated"  # type: ignore[misc]

    def test_registered_profile_scenario_is_resolved_without_runner_semantics(self) -> None:
        protocol = self._protocol()

        implicit = protocol.infer(
            model_id="mock-completed",
            request_bytes=b"exact request",
            invocation_id="profile-invocation",
        )
        explicit = protocol.infer(
            model_id="mock-completed",
            request_bytes=b"exact request",
            invocation_id="profile-invocation",
            scenario_id="completed",
        )

        self.assertEqual(implicit, explicit)
        self.assertEqual("mock-completed", implicit.model_id)
        self.assertEqual("mock-base", implicit.base_model_id)
        self.assertEqual("completed", implicit.scenario_id)

    def test_execution_rejection_profile_exposes_process_facts_without_preclassification(self) -> None:
        protocol = self._protocol()

        first = protocol.infer(
            model_id="mock-execution-rejection",
            request_bytes=b"exact request",
            invocation_id="execution-rejection",
        )
        repeated = protocol.infer(
            model_id="mock-execution-rejection",
            request_bytes=b"exact request",
            invocation_id="execution-rejection",
        )

        self.assertEqual(first, repeated)
        self.assertEqual(EXECUTION_REJECTION_SCENARIO, first.scenario_id)
        self.assertEqual(b"", first.response)
        self.assertEqual(b"", first.stdout)
        self.assertTrue(first.stderr)
        self.assertEqual(first.stderr, first.diagnostic)
        self.assertNotEqual(0, first.exit_code)

    def test_unknown_model_and_unauthorized_scenario_fail_explicitly(self) -> None:
        protocol = self._protocol()

        with self.assertRaises(ProtocolInferenceError) as unknown:
            protocol.infer(
                model_id="missing",
                request_bytes=b"request",
                invocation_id="unknown-model",
            )
        self.assertEqual(INFERENCE_OPERATION, unknown.exception.operation)
        self.assertEqual("unknown_model", unknown.exception.code)
        self.assertEqual(b"", unknown.exception.diagnostic)

        with self.assertRaises(ProtocolInferenceError) as scenario:
            protocol.infer(
                model_id="mock-completed",
                request_bytes=b"request",
                invocation_id="bad-scenario",
                scenario_id="timeout",
            )
        self.assertEqual("unauthorized_scenario", scenario.exception.code)

    def test_timeout_and_cancellation_profiles_remain_running_until_interrupted(self) -> None:
        class ScenarioInterrupted(RuntimeError):
            pass

        protocol = self._protocol()

        with patch(
            "AgMark.shared.mock_model.scenarios.runtime.time.sleep",
            side_effect=ScenarioInterrupted("interrupted by owning execution boundary"),
        ) as sleeper:
            for model_id, scenario_id in (
                ("mock-timeout", "timeout"),
                ("mock-cancellation", "cancellation"),
            ):
                with self.assertRaises(ScenarioInterrupted):
                    protocol.infer(
                        model_id=model_id,
                        request_bytes=b"exact request",
                        invocation_id=f"{scenario_id}-invocation",
                    )

        self.assertEqual(2, sleeper.call_count)
        sleeper.assert_has_calls([call(1.0), call(1.0)])

    def test_inference_rejects_non_byte_request_material(self) -> None:
        protocol = self._protocol()

        with self.assertRaisesRegex(TypeError, "request_bytes must be bytes"):
            protocol.infer(
                model_id="mock-base",
                request_bytes=bytearray(b"request"),  # type: ignore[arg-type]
                invocation_id="invalid-bytes",
            )


if __name__ == "__main__":
    unittest.main()
