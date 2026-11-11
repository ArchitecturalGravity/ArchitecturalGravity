"""Dynamic common-evidence invariance for live/mock target-specific data.

The static identity-dispatch guard prevents obvious source-level branches. These
behavioral tests exercise the shared emission and parity projection directly so
target-specific identity values and opaque adapter extension payloads cannot
become common downstream requirements.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from AgMark.shared.adapters._contract import validate_runner_request
from AgMark.shared.adapters.execution import (
    EXECUTION_EVIDENCE_EXTENSION_KEY,
    ExecutionIsolation,
    InvocationCapture,
    TargetCompositionDescriptor,
    TerminalExecutionResult,
    emit_terminal_observation,
    validate_execution_evidence,
)
from AgMark.shared.software_testing.conformance.test_conformance import _runner_request, _boundary


_ROOT = Path(__file__).resolve().parents[4]
_REGISTRATION = _ROOT / "AgMark/shared/adapters/Mock_Model/registration.json"
_TIMESTAMP = "2026-01-01T00:00:00Z"
_RUNNER_ENTRY_POINT = "AgMark.shared.adapters.Mock_Model:MockRunner"
_RUNNER_ARTIFACTS = (
    "AgMark/shared/adapters/Mock_Model/runner.py",
    "AgMark/shared/adapters/execution/orchestration.py",
    "AgMark/shared/adapters/execution/emission.py",
)


def _registration() -> dict[str, object]:
    return json.loads(_REGISTRATION.read_text(encoding="utf-8"))


def _target(
    registration: dict[str, object],
    *,
    target_class: str,
    evidence_class: str,
    compatibility_profile: str | None,
) -> TargetCompositionDescriptor:
    return TargetCompositionDescriptor.create(
        target_class=target_class,
        evidence_class=evidence_class,
        runtime_id=str(registration["registration_id"]),
        runtime_version="1.0.0",
        access_method="cli",
        external_provider_submission=False,
        launch_mode="native",
        launch_environment_selector={},
        executable="arcgrav-dynamic-parity-cli",
        authentication_class="not_applicable",
        compatibility_profile=compatibility_profile,
        production_runner_entry_point=_RUNNER_ENTRY_POINT,
        runner_implementation_artifact_ids=_RUNNER_ARTIFACTS,
    )


def _completed_execution() -> TerminalExecutionResult:
    return TerminalExecutionResult(
        terminal_status="completed",
        failure_kind=None,
        started_at=_TIMESTAMP,
        completed_at=_TIMESTAMP,
        duration_ms=0.0,
        invocation_occurred=True,
        capture=InvocationCapture(
            succeeded=True,
            exit_status=0,
            transport_status=None,
            stdout=b"dynamic response",
            stderr=b"",
        ),
        response_bytes=b"dynamic response",
        isolation=ExecutionIsolation(
            fresh_process=True,
            fresh_workdir=True,
            prior_observation_context_reused=False,
            session_home_reused=True,
        ),
    )


class MockModelExtensionIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registration = _registration()
        self.validated = validate_runner_request(
            _runner_request(_boundary())
        )

    def _observation(
        self,
        target: TargetCompositionDescriptor,
        *,
        extensions: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return emit_terminal_observation(
            self.validated,
            target=target,
            execution=_completed_execution(),
            runner_id=str(self.registration["registration_id"]),
            runner_version=str(self.registration["registration_version"]),
            framed_request=b"adapter prompt\n\nadapter input",
            request_framing_mode="mock_json_v1",
            authentication_source=None,
            launch_environment_id=None,
            usage_provider_reported=None,
            usage_provenance=None,
            extensions=extensions,
        )

    def test_common_emission_is_invariant_to_target_identity_values(self) -> None:
        mock_observation = self._observation(
            _target(
                self.registration,
                target_class="mock-model",
                evidence_class="diagnostic-synthetic",
                compatibility_profile=None,
            ),
        )
        live_shaped_observation = self._observation(
            _target(
                self.registration,
                target_class="live-provider",
                evidence_class="provider-observed",
                compatibility_profile=None,
            ),
        )

        for observation in (mock_observation, live_shaped_observation):
            validate_execution_evidence(observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY])
        self.assertEqual(
            mock_observation["terminal_status"],
            live_shaped_observation["terminal_status"],
        )
        self.assertEqual(
            mock_observation["response"],
            live_shaped_observation["response"],
        )
        self.assertEqual(
            [item["name"] for item in mock_observation["telemetry"]],
            [item["name"] for item in live_shaped_observation["telemetry"]],
        )

        mock_evidence = mock_observation["extensions"][
            EXECUTION_EVIDENCE_EXTENSION_KEY
        ]
        live_evidence = live_shaped_observation["extensions"][
            EXECUTION_EVIDENCE_EXTENSION_KEY
        ]
        self.assertEqual("mock-model", mock_evidence["target"]["class"])
        self.assertEqual("live-provider", live_evidence["target"]["class"])
        self.assertEqual(mock_evidence["submission"], live_evidence["submission"])
        self.assertEqual(mock_evidence["process"], live_evidence["process"])
        self.assertEqual(mock_evidence["usage"], live_evidence["usage"])
        self.assertEqual(mock_evidence["error"], live_evidence["error"])

    def test_adapter_extension_namespace_is_not_common_evidence_authority(self) -> None:
        from AgMark.shared.adapters.execution.emission import CanonicalObservationError
        target = _target(self.registration, target_class="mock-model",
                         evidence_class="diagnostic-synthetic", compatibility_profile=None)
        with self.assertRaises(CanonicalObservationError):
            self._observation(target, extensions={"openai.codex_cli:execution": {
                "unexpected_common_requirement": {"process": {"stdout": "do-not-read"}}}})


if __name__ == "__main__":
    unittest.main()
