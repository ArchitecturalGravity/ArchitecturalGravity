"""Conformance tests for provider-neutral mock-model runtime probes."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from AgMark.shared.mock_model.protocol import (
    CAPABILITY_INSPECTION_OPERATION,
    MODEL_DISCOVERY_OPERATION,
    RUNTIME_IDENTITY_OPERATION,
    MockRuntimeProtocol,
    ModelCatalogEntry,
    ModelProfileMapping,
    ProbeFailure,
    ProtocolProbeError,
)


class MockRuntimeProtocolProbeTests(unittest.TestCase):
    def test_runtime_identity_is_stable_synthetic_and_immutable(self) -> None:
        protocol = MockRuntimeProtocol(
            runtime_id="arcgrav.mock-model.test-runtime",
            runtime_version="7.4.1",
        )

        first = protocol.runtime_identity()
        second = protocol.runtime_identity()

        self.assertEqual(first, second)
        self.assertEqual("arcgrav.mock-model.test-runtime", first.runtime_id)
        self.assertEqual("7.4.1", first.runtime_version)
        self.assertTrue(first.synthetic)
        with self.assertRaises(FrozenInstanceError):
            first.runtime_version = "mutated"  # type: ignore[misc]

    def test_capability_inspection_is_stable_and_canonical(self) -> None:
        protocol = MockRuntimeProtocol(
            capabilities=(
                "runtime.version",
                "runtime.capabilities",
                "model.discovery",
            )
        )

        first = protocol.inspect_capabilities()
        second = protocol.inspect_capabilities()

        self.assertEqual(first, second)
        self.assertEqual(
            (
                "model.discovery",
                "runtime.capabilities",
                "runtime.version",
            ),
            first.capabilities,
        )
        self.assertTrue(first.synthetic)

    def test_model_discovery_is_stable_immutable_and_keeps_identity_separate(self) -> None:
        registered_models = [
            ModelCatalogEntry(
                model_id="mock-base",
                label="Mock Base",
                is_default=True,
            ),
            ModelCatalogEntry(
                model_id="mock-completed",
                label="Completed Response",
                profile=ModelProfileMapping(
                    base_model_id="mock-base",
                    scenario_id="completed",
                ),
            ),
            ModelCatalogEntry(
                model_id="mock-hidden",
                label="Hidden Diagnostic",
                hidden=True,
            ),
        ]
        protocol = MockRuntimeProtocol(models=registered_models)
        registered_models.clear()

        first = protocol.discover_models()
        second = protocol.discover_models()

        self.assertEqual(first, second)
        self.assertEqual("mock-base", first.default_model_id)
        self.assertEqual(
            ("mock-base", "mock-completed", "mock-hidden"),
            tuple(model.model_id for model in first.models),
        )
        self.assertEqual(
            ("Mock Base", "Completed Response", "Hidden Diagnostic"),
            tuple(model.label for model in first.models),
        )
        self.assertFalse(first.models[0].hidden)
        self.assertTrue(first.models[2].hidden)
        self.assertTrue(first.models[0].is_default)
        self.assertEqual(
            ModelProfileMapping(
                base_model_id="mock-base",
                scenario_id="completed",
            ),
            first.models[1].profile,
        )
        self.assertTrue(first.synthetic)
        self.assertTrue(all(model.synthetic for model in first.models))
        with self.assertRaises(FrozenInstanceError):
            first.models[0].label = "mutated"  # type: ignore[misc]

    def test_model_catalog_validation_fails_closed(self) -> None:
        base = ModelCatalogEntry(model_id="mock-base", label="Mock Base")

        with self.assertRaisesRegex(ValueError, "duplicate model_id"):
            MockRuntimeProtocol(models=(base, base))
        with self.assertRaisesRegex(ValueError, "multiple defaults"):
            MockRuntimeProtocol(
                models=(
                    ModelCatalogEntry(
                        model_id="mock-a",
                        label="Mock A",
                        is_default=True,
                    ),
                    ModelCatalogEntry(
                        model_id="mock-b",
                        label="Mock B",
                        is_default=True,
                    ),
                )
            )
        with self.assertRaisesRegex(ValueError, "base_model_id"):
            MockRuntimeProtocol(
                models=(
                    ModelCatalogEntry(
                        model_id="mock-profile",
                        label="Mock Profile",
                        profile=ModelProfileMapping(
                            base_model_id="missing-base",
                            scenario_id="completed",
                        ),
                    ),
                )
            )

    def test_model_discovery_failure_is_explicit_and_operation_scoped(self) -> None:
        failure = ProbeFailure(
            code="model_catalog_unavailable",
            diagnostic=b"synthetic discovery failure\n",
        )
        protocol = MockRuntimeProtocol(
            models=(ModelCatalogEntry(model_id="mock-base", label="Mock Base"),),
            probe_failures={MODEL_DISCOVERY_OPERATION: failure},
        )

        with self.assertRaises(ProtocolProbeError) as captured:
            protocol.discover_models()

        self.assertEqual(MODEL_DISCOVERY_OPERATION, captured.exception.operation)
        self.assertEqual(failure.code, captured.exception.code)
        self.assertEqual(failure.diagnostic, captured.exception.diagnostic)
        self.assertTrue(protocol.runtime_identity().synthetic)

    def test_empty_model_catalog_fails_discovery_explicitly(self) -> None:
        protocol = MockRuntimeProtocol()

        with self.assertRaises(ProtocolProbeError) as captured:
            protocol.discover_models()

        self.assertEqual(MODEL_DISCOVERY_OPERATION, captured.exception.operation)
        self.assertEqual("model_catalog_unavailable", captured.exception.code)

    def test_probe_failures_are_explicit_deterministic_and_operation_scoped(self) -> None:
        protocol = MockRuntimeProtocol(
            capabilities=("runtime.capabilities",),
            probe_failures={
                RUNTIME_IDENTITY_OPERATION: ProbeFailure(
                    code="runtime_identity_unavailable",
                    diagnostic=b"synthetic identity probe failure\n",
                )
            },
        )

        for _ in range(2):
            with self.assertRaises(ProtocolProbeError) as captured:
                protocol.runtime_identity()
            self.assertEqual(
                RUNTIME_IDENTITY_OPERATION,
                captured.exception.operation,
            )
            self.assertEqual(
                "runtime_identity_unavailable",
                captured.exception.code,
            )
            self.assertEqual(
                b"synthetic identity probe failure\n",
                captured.exception.diagnostic,
            )

        self.assertEqual(
            ("runtime.capabilities",),
            protocol.inspect_capabilities().capabilities,
        )

    def test_capability_failure_does_not_turn_identity_probe_into_inference(self) -> None:
        failures = {
            CAPABILITY_INSPECTION_OPERATION: ProbeFailure(
                code="capabilities_unavailable",
                diagnostic=b"no capabilities\n",
            )
        }
        protocol = MockRuntimeProtocol(
            runtime_id="arcgrav.mock-model.synthetic",
            runtime_version="1.2.3",
            probe_failures=failures,
        )
        failures.clear()

        self.assertEqual(
            "arcgrav.mock-model.synthetic",
            protocol.runtime_identity().runtime_id,
        )
        with self.assertRaises(ProtocolProbeError) as captured:
            protocol.inspect_capabilities()
        self.assertEqual(
            CAPABILITY_INSPECTION_OPERATION,
            captured.exception.operation,
        )
        self.assertEqual("capabilities_unavailable", captured.exception.code)

    def test_invalid_probe_configuration_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported probe operation"):
            MockRuntimeProtocol(
                probe_failures={
                    "inference": ProbeFailure(code="must-not-be-accepted")
                }
            )
        with self.assertRaisesRegex(ValueError, "duplicate capability"):
            MockRuntimeProtocol(capabilities=("model.discovery", "model.discovery"))


if __name__ == "__main__":
    unittest.main()
