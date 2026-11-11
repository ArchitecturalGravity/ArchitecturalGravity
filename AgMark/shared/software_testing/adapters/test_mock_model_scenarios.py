"""Focused tests for finite cause-side mock-model scenarios."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from AgMark.shared.mock_model.protocol import (
    MockRuntimeProtocol,
    ModelCatalogEntry,
    ModelProfileMapping,
    ProtocolInferenceError,
)
from AgMark.shared.mock_model.scenarios import (
    CAPABILITY_FAILURE_SCENARIO,
    COMPLETED_SCENARIO,
    DISCOVERY_FAILURE_SCENARIO,
    DISCOVERY_PROTOCOL_INVALID_SCENARIO,
    EMPTY_RESPONSE_SCENARIO,
    EXECUTION_REJECTION_SCENARIO,
    MALFORMED_OUTPUT_SCENARIO,
    PARTIAL_OUTPUT_FAILURE_SCENARIO,
    PARTIAL_OUTPUT_TIMEOUT_SCENARIO,
    PARTIAL_OUTPUT_CANCELLATION_SCENARIO,
    PROCESS_FAILURE_SCENARIO,
    RUNTIME_PROBE_FAILURE_SCENARIO,
    RUNTIME_VERSION_MISMATCH_SCENARIO,
    STRUCTURED_RESPONSE_SCENARIO,
    SUCCESS_WITH_STDERR_SCENARIO,
    evaluate_preflight_scenario,
)


class MockModelFiniteScenarioTests(unittest.TestCase):
    def _protocol(self) -> MockRuntimeProtocol:
        scenario_ids = (
            COMPLETED_SCENARIO,
            STRUCTURED_RESPONSE_SCENARIO,
            EMPTY_RESPONSE_SCENARIO,
            EXECUTION_REJECTION_SCENARIO,
            MALFORMED_OUTPUT_SCENARIO,
            PROCESS_FAILURE_SCENARIO,
            SUCCESS_WITH_STDERR_SCENARIO,
            PARTIAL_OUTPUT_FAILURE_SCENARIO,
        )
        models = [
            ModelCatalogEntry(
                model_id="mock-base",
                label="Mock Base",
                is_default=True,
            )
        ]
        models.extend(
            ModelCatalogEntry(
                model_id=f"mock-{scenario_id}",
                label=scenario_id,
                profile=ModelProfileMapping(
                    base_model_id="mock-base",
                    scenario_id=scenario_id,
                ),
            )
            for scenario_id in scenario_ids
        )
        return MockRuntimeProtocol(models=models)

    def _infer(self, scenario_id: str, *, invocation_id: str = "invocation-1"):
        return self._protocol().infer(
            model_id=f"mock-{scenario_id}",
            request_bytes=b"exact\\x00request\\n",
            invocation_id=invocation_id,
        )

    def test_success_scenarios_keep_process_and_response_conditions_distinct(self) -> None:
        completed = self._infer(COMPLETED_SCENARIO)
        self.assertEqual(0, completed.exit_code)
        self.assertTrue(completed.response)
        self.assertEqual(completed.response, completed.stdout)
        self.assertEqual(b"", completed.stderr)

        structured = self._infer(STRUCTURED_RESPONSE_SCENARIO)
        self.assertEqual(0, structured.exit_code)
        self.assertEqual(structured.response, structured.stdout)
        self.assertTrue(json.loads(structured.response)["synthetic"])

        empty = self._infer(EMPTY_RESPONSE_SCENARIO)
        self.assertEqual(0, empty.exit_code)
        self.assertEqual(b"", empty.response)
        self.assertEqual(b"", empty.stdout)

        malformed = self._infer(MALFORMED_OUTPUT_SCENARIO)
        self.assertEqual(0, malformed.exit_code)
        self.assertTrue(malformed.response)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(malformed.response)

    def test_failure_stderr_and_partial_output_are_exact_process_facts(self) -> None:
        failed = self._infer(PROCESS_FAILURE_SCENARIO)
        self.assertNotEqual(0, failed.exit_code)
        self.assertEqual(b"", failed.response)
        self.assertEqual(b"", failed.stdout)
        self.assertTrue(failed.stderr)
        self.assertEqual(failed.stderr, failed.diagnostic)

        rejected = self._infer(EXECUTION_REJECTION_SCENARIO)
        self.assertNotEqual(0, rejected.exit_code)
        self.assertEqual(b"", rejected.response)
        self.assertEqual(b"", rejected.stdout)
        self.assertTrue(rejected.stderr)
        self.assertEqual(rejected.stderr, rejected.diagnostic)
        self.assertNotEqual(failed.exit_code, rejected.exit_code)
        self.assertNotEqual(failed.stderr, rejected.stderr)

        warning = self._infer(SUCCESS_WITH_STDERR_SCENARIO)
        self.assertEqual(0, warning.exit_code)
        self.assertTrue(warning.response)
        self.assertEqual(warning.response, warning.stdout)
        self.assertTrue(warning.stderr)

        partial = self._infer(PARTIAL_OUTPUT_FAILURE_SCENARIO)
        self.assertNotEqual(0, partial.exit_code)
        self.assertEqual(b"", partial.response)
        self.assertTrue(partial.stdout)
        self.assertTrue(partial.stderr)

    def test_scenario_bytes_are_reproducible_from_immutable_invocation_inputs(self) -> None:
        first = self._infer(PARTIAL_OUTPUT_FAILURE_SCENARIO, invocation_id="same")
        repeated = self._infer(PARTIAL_OUTPUT_FAILURE_SCENARIO, invocation_id="same")
        different = self._infer(PARTIAL_OUTPUT_FAILURE_SCENARIO, invocation_id="different")

        self.assertEqual(first, repeated)
        self.assertNotEqual(first.stdout, different.stdout)
        self.assertNotEqual(first.stderr, different.stderr)

    def test_partial_output_is_streamed_before_external_interruption(self) -> None:
        class Interrupted(RuntimeError):
            pass

        for scenario_id in (
            PARTIAL_OUTPUT_TIMEOUT_SCENARIO,
            PARTIAL_OUTPUT_CANCELLATION_SCENARIO,
        ):
            with self.subTest(scenario=scenario_id):
                protocol = MockRuntimeProtocol(
                    models=(
                        ModelCatalogEntry(model_id="mock-base", label="Mock Base"),
                        ModelCatalogEntry(
                            model_id="mock-interrupted",
                            label="Interrupted",
                            profile=ModelProfileMapping(
                                base_model_id="mock-base", scenario_id=scenario_id,
                            ),
                        ),
                    )
                )
                emissions: list[tuple[bytes, bytes]] = []
                with patch(
                    "AgMark.shared.mock_model.scenarios.runtime.time.sleep",
                    side_effect=Interrupted("external interruption"),
                ):
                    with self.assertRaises(Interrupted):
                        protocol.infer(
                            model_id="mock-interrupted",
                            request_bytes=b"exact request bytes",
                            invocation_id="fixed invocation",
                            partial_output_sink=lambda stdout, stderr: emissions.append(
                                (stdout, stderr)
                            ),
                        )
                self.assertEqual(1, len(emissions))
                self.assertTrue(
                    emissions[0][0].startswith(b"arcgrav-mock-interrupted-stdout-v1:")
                )
                self.assertTrue(
                    emissions[0][1].startswith(b"arcgrav-mock-interrupted-stderr-v1:")
                )

    def test_registered_but_unknown_scenario_fails_through_protocol_boundary(self) -> None:
        protocol = MockRuntimeProtocol(
            models=(
                ModelCatalogEntry(model_id="mock-base", label="Mock Base"),
                ModelCatalogEntry(
                    model_id="mock-unknown",
                    label="Unknown",
                    profile=ModelProfileMapping(
                        base_model_id="mock-base",
                        scenario_id="not-registered",
                    ),
                ),
            )
        )

        with self.assertRaises(ProtocolInferenceError) as captured:
            protocol.infer(
                model_id="mock-unknown",
                request_bytes=b"request",
                invocation_id="unknown-scenario",
            )
        self.assertEqual("unknown_scenario", captured.exception.code)

    def test_preflight_scenarios_are_registered_deterministic_target_facts(self) -> None:
        scenario_ids = (
            RUNTIME_PROBE_FAILURE_SCENARIO,
            RUNTIME_VERSION_MISMATCH_SCENARIO,
            CAPABILITY_FAILURE_SCENARIO,
            DISCOVERY_FAILURE_SCENARIO,
            DISCOVERY_PROTOCOL_INVALID_SCENARIO,
        )

        for scenario_id in scenario_ids:
            first = evaluate_preflight_scenario(scenario_id)
            repeated = evaluate_preflight_scenario(scenario_id)
            self.assertEqual(first, repeated)
            self.assertEqual(scenario_id, first.scenario_id)

        invalid_discovery = evaluate_preflight_scenario(
            DISCOVERY_PROTOCOL_INVALID_SCENARIO
        )
        self.assertTrue(invalid_discovery.protocol_payload)
        self.assertIsNone(invalid_discovery.failure_code)


    def test_unknown_preflight_scenario_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown preflight scenario"):
            evaluate_preflight_scenario("not-registered")


if __name__ == "__main__":
    unittest.main()
