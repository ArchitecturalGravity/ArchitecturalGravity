"""Conformance tests for provider-neutral mock-model preflight probes."""

from __future__ import annotations

import unittest

from AgMark.shared.mock_model.protocol import (
    CAPABILITY_INSPECTION_OPERATION,
    DEFAULT_EXECUTABLE_ID,
    DEFAULT_RUNTIME_ID,
    DEFAULT_RUNTIME_VERSION,
    MODEL_DISCOVERY_OPERATION,
    RUNTIME_IDENTITY_OPERATION,
    MockRuntimeProtocol,
    ModelCatalogEntry,
    ProbeFailure,
    ProtocolProbeError,
)
from AgMark.shared.mock_model.scenarios import (
    CAPABILITY_FAILURE_SCENARIO,
    DISCOVERY_FAILURE_SCENARIO,
    DISCOVERY_PROTOCOL_INVALID_SCENARIO,
    RUNTIME_PROBE_FAILURE_SCENARIO,
    RUNTIME_VERSION_MISMATCH_SCENARIO,
)


class MockModelProtocolPreflightTests(unittest.TestCase):
    def test_runtime_identity_is_stable_synthetic_and_executable_bound(self) -> None:
        protocol = MockRuntimeProtocol()

        first = protocol.runtime_identity()
        second = protocol.runtime_identity()

        self.assertEqual(first, second)
        self.assertEqual(DEFAULT_RUNTIME_ID, first.runtime_id)
        self.assertEqual(DEFAULT_RUNTIME_VERSION, first.runtime_version)
        self.assertEqual(DEFAULT_EXECUTABLE_ID, first.executable_id)
        self.assertTrue(first.synthetic)

    def test_capability_inspection_is_canonical_and_runtime_bound(self) -> None:
        protocol = MockRuntimeProtocol(
            capabilities=("model-discovery", "inference", "capability-inspection")
        )

        first = protocol.inspect_capabilities()
        second = protocol.inspect_capabilities()

        self.assertEqual(first, second)
        self.assertEqual(DEFAULT_RUNTIME_ID, first.runtime_id)
        self.assertEqual(DEFAULT_RUNTIME_VERSION, first.runtime_version)
        self.assertEqual(DEFAULT_EXECUTABLE_ID, first.executable_id)
        self.assertEqual(
            ("capability-inspection", "inference", "model-discovery"),
            first.capabilities,
        )
        self.assertTrue(first.synthetic)

    def test_runtime_identity_failure_is_explicit_repeatable_and_probe_local(self) -> None:
        failure = ProbeFailure(
            code="runtime_identity_unavailable",
            diagnostic=b"synthetic runtime identity unavailable\n",
        )
        protocol = MockRuntimeProtocol(
            capabilities=("inference",),
            probe_failures={RUNTIME_IDENTITY_OPERATION: failure},
        )

        for _ in range(2):
            with self.assertRaises(ProtocolProbeError) as captured:
                protocol.runtime_identity()
            self.assertEqual(RUNTIME_IDENTITY_OPERATION, captured.exception.operation)
            self.assertEqual(failure.code, captured.exception.code)
            self.assertEqual(failure.diagnostic, captured.exception.diagnostic)

        self.assertEqual(("inference",), protocol.inspect_capabilities().capabilities)

    def test_capability_failure_is_explicit_repeatable_and_probe_local(self) -> None:
        failure = ProbeFailure(
            code="capability_probe_failed",
            diagnostic=b"synthetic capability probe failed\n",
        )
        protocol = MockRuntimeProtocol(
            probe_failures={CAPABILITY_INSPECTION_OPERATION: failure},
        )

        with self.assertRaises(ProtocolProbeError) as captured:
            protocol.inspect_capabilities()

        self.assertEqual(
            CAPABILITY_INSPECTION_OPERATION,
            captured.exception.operation,
        )
        self.assertEqual(failure.code, captured.exception.code)
        self.assertEqual(failure.diagnostic, captured.exception.diagnostic)
        self.assertEqual(DEFAULT_RUNTIME_ID, protocol.runtime_identity().runtime_id)

    def test_registered_runtime_preflight_scenarios_are_runner_opaque(self) -> None:
        unavailable = MockRuntimeProtocol(
            capabilities=("inference",),
            preflight_scenario_id=RUNTIME_PROBE_FAILURE_SCENARIO,
        )
        with self.assertRaises(ProtocolProbeError) as captured:
            unavailable.runtime_identity()
        self.assertEqual(RUNTIME_IDENTITY_OPERATION, captured.exception.operation)
        self.assertEqual("runtime_identity_unavailable", captured.exception.code)
        self.assertEqual(("inference",), unavailable.inspect_capabilities().capabilities)

        mismatch = MockRuntimeProtocol(
            preflight_scenario_id=RUNTIME_VERSION_MISMATCH_SCENARIO,
        )
        first = mismatch.runtime_identity()
        second = mismatch.runtime_identity()
        self.assertEqual(first, second)
        self.assertEqual("0.0.0-incompatible", first.runtime_version)
        self.assertEqual(DEFAULT_RUNTIME_ID, first.runtime_id)

    def test_registered_capability_preflight_scenario_is_probe_local(self) -> None:
        protocol = MockRuntimeProtocol(
            preflight_scenario_id=CAPABILITY_FAILURE_SCENARIO,
        )

        with self.assertRaises(ProtocolProbeError) as captured:
            protocol.inspect_capabilities()

        self.assertEqual(CAPABILITY_INSPECTION_OPERATION, captured.exception.operation)
        self.assertEqual("capability_probe_failed", captured.exception.code)
        self.assertEqual(DEFAULT_RUNTIME_ID, protocol.runtime_identity().runtime_id)

    def test_registered_discovery_scenarios_preserve_distinct_target_causes(self) -> None:
        models = (ModelCatalogEntry(model_id="mock-base", label="Mock Base"),)

        failure = MockRuntimeProtocol(
            models=models,
            preflight_scenario_id=DISCOVERY_FAILURE_SCENARIO,
        )
        with self.assertRaises(ProtocolProbeError) as captured:
            failure.discover_models()
        self.assertEqual(MODEL_DISCOVERY_OPERATION, captured.exception.operation)
        self.assertEqual("model_catalog_unavailable", captured.exception.code)
        self.assertTrue(captured.exception.diagnostic)

        invalid = MockRuntimeProtocol(
            models=models,
            preflight_scenario_id=DISCOVERY_PROTOCOL_INVALID_SCENARIO,
        )
        with self.assertRaises(ProtocolProbeError) as captured:
            invalid.discover_models()
        self.assertEqual(MODEL_DISCOVERY_OPERATION, captured.exception.operation)
        self.assertEqual("protocol_invalid_result", captured.exception.code)
        self.assertEqual(
            b"arcgrav-mock-invalid-discovery-v1\n",
            captured.exception.diagnostic,
        )
        self.assertEqual(DEFAULT_RUNTIME_ID, invalid.runtime_identity().runtime_id)

    def test_registered_preflight_selection_fails_closed_on_conflict_or_unknown(self) -> None:
        with self.assertRaisesRegex(ValueError, "conflicts"):
            MockRuntimeProtocol(
                probe_failures={
                    RUNTIME_IDENTITY_OPERATION: ProbeFailure(code="explicit-failure")
                },
                preflight_scenario_id=RUNTIME_PROBE_FAILURE_SCENARIO,
            )

        with self.assertRaisesRegex(ValueError, "unknown preflight scenario"):
            MockRuntimeProtocol(preflight_scenario_id="not-registered")

    def test_invalid_probe_configuration_fails_before_any_probe(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported probe operation"):
            MockRuntimeProtocol(
                probe_failures={
                    "inference": ProbeFailure(code="not-a-preflight-operation")
                }
            )

        with self.assertRaisesRegex(TypeError, "ProbeFailure"):
            MockRuntimeProtocol(
                probe_failures={RUNTIME_IDENTITY_OPERATION: object()}  # type: ignore[dict-item]
            )

    def test_invalid_identity_and_capability_configuration_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            MockRuntimeProtocol(runtime_id="")
        with self.assertRaises(ValueError):
            MockRuntimeProtocol(runtime_version=" ")
        with self.assertRaises(ValueError):
            MockRuntimeProtocol(executable_id="")
        with self.assertRaisesRegex(ValueError, "duplicate capability"):
            MockRuntimeProtocol(capabilities=("inference", "inference"))
        with self.assertRaises(ValueError):
            MockRuntimeProtocol(capabilities=("inference", ""))


if __name__ == "__main__":
    unittest.main()
