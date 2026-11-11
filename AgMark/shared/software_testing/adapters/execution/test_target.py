"""Focused conformance tests for immutable execution target composition."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from AgMark.shared.adapters.execution import TargetCompositionDescriptor


class TargetCompositionDescriptorTests(unittest.TestCase):
    def _descriptor(self, **overrides: object) -> TargetCompositionDescriptor:
        values: dict[str, object] = {
            "target_class": "live-provider",
            "evidence_class": "live-provider-execution",
            "runtime_id": "openai.codex-cli",
            "runtime_version": "1.2.3",
            "access_method": "cli",
            "external_provider_submission": True,
            "launch_mode": "wsl",
            "launch_environment_selector": {
                "wsl_distribution": "Ubuntu",
            },
            "executable": "/usr/bin/codex",
            "authentication_class": "codex_session",
            "compatibility_profile": None,
            "production_runner_entry_point": (
                "AgMark.shared.adapters.Codex_CLI:CodexCliRunner"
            ),
            "runner_implementation_artifact_ids": [
                "AgMark/shared/adapters/_contract.py",
                "AgMark/shared/adapters/Codex_CLI/runner.py",
                "AgMark/shared/adapters/Codex_CLI/model_discovery.py",
            ],
        }
        values.update(overrides)
        return TargetCompositionDescriptor.create(**values)  # type: ignore[arg-type]

    def test_descriptor_retains_truthful_target_and_runner_authority(self) -> None:
        descriptor = self._descriptor()

        self.assertEqual("live-provider", descriptor.target_class)
        self.assertEqual("live-provider-execution", descriptor.evidence_class)
        self.assertEqual("openai.codex-cli", descriptor.runtime_id)
        self.assertEqual("1.2.3", descriptor.runtime_version)
        self.assertEqual("cli", descriptor.access_method)
        self.assertTrue(descriptor.external_provider_submission)
        self.assertEqual("wsl", descriptor.launch_mode)
        self.assertEqual(
            (("wsl_distribution", "Ubuntu"),),
            descriptor.launch_environment_selector,
        )
        self.assertEqual("/usr/bin/codex", descriptor.executable)
        self.assertEqual("codex_session", descriptor.authentication_class)
        self.assertIsNone(descriptor.compatibility_profile)
        self.assertEqual(
            (
                "AgMark.shared.adapters.Codex_CLI:CodexCliRunner",
                (
                    "AgMark/shared/adapters/_contract.py",
                    "AgMark/shared/adapters/Codex_CLI/runner.py",
                    "AgMark/shared/adapters/Codex_CLI/model_discovery.py",
                ),
            ),
            descriptor.runner_authority,
        )

    def test_descriptor_defensively_freezes_collection_inputs(self) -> None:
        selectors = {"wsl_distribution": "Ubuntu"}
        artifacts = ["AgMark/shared/adapters/Codex_CLI/runner.py"]
        descriptor = self._descriptor(
            launch_environment_selector=selectors,
            runner_implementation_artifact_ids=artifacts,
        )

        selectors["wsl_distribution"] = "Debian"
        artifacts.append("AgMark/shared/adapters/Codex_CLI/model_discovery.py")

        self.assertEqual(
            (("wsl_distribution", "Ubuntu"),),
            descriptor.launch_environment_selector,
        )
        self.assertEqual(
            ("AgMark/shared/adapters/Codex_CLI/runner.py",),
            descriptor.runner_implementation_artifact_ids,
        )
        with self.assertRaises(FrozenInstanceError):
            descriptor.target_class = "mock-model"  # type: ignore[misc]

    def test_mock_target_can_share_runner_authority_without_live_identity(self) -> None:
        live = self._descriptor()
        mock = self._descriptor(
            target_class="mock-model",
            evidence_class="provider-free-conformance",
            runtime_id="arcgrav.mock-model-cli",
            runtime_version="1.0.0",
            external_provider_submission=False,
            launch_mode="native",
            launch_environment_selector={},
            executable="arcgrav-mock-codex",
            authentication_class="not_applicable",
            compatibility_profile="codex-cli",
        )

        self.assertEqual(live.runner_authority, mock.runner_authority)
        self.assertNotEqual(live.target_class, mock.target_class)
        self.assertNotEqual(live.runtime_id, mock.runtime_id)
        self.assertNotEqual(live.authentication_class, mock.authentication_class)

    def test_invalid_or_ambiguous_authority_fails_closed(self) -> None:
        cases = (
            {"target_class": ""},
            {"external_provider_submission": "yes"},
            {"production_runner_entry_point": "missing-separator"},
            {"runner_implementation_artifact_ids": []},
            {
                "runner_implementation_artifact_ids": [
                    "AgMark/shared/adapters/Codex_CLI/runner.py",
                    "AgMark/shared/adapters/Codex_CLI/runner.py",
                ]
            },
            {"launch_environment_selector": (("launch_mode", []),)},
        )
        for override in cases:
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    self._descriptor(**override)


if __name__ == "__main__":
    unittest.main()
