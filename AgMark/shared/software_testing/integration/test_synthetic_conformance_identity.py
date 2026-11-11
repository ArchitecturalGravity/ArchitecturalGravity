"""Synthetic identity classification over revalidated canonical target facts."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from AgMark.shared.reporting.revalidation import (
    ReportingInputRevalidationError,
    _synthetic_conformance_from_evidence,
)


def _scope(runner_id: str, *targets: dict[str, str] | None, registered_synthetic: bool = False) -> bool:
    records = {}
    documents = {"boundary": {"runner": {"id": runner_id, "version": "1.0.0"}}}
    if registered_synthetic:
        records["registration"] = SimpleNamespace(
            artifact_id="registration", role="runner_registration",
        )
        documents["registration"] = {
            "registration_id": runner_id,
            "registration_version": "1.0.0",
            "extensions": {
                "arcgrav.adapters:target_composition": {"target_class": "mock-model"},
            },
        }
    for index, target in enumerate(targets):
        artifact_id = f"observation-{index}"
        records[artifact_id] = SimpleNamespace(
            artifact_id=artifact_id,
            role="treatment_observation",
        )
        documents[artifact_id] = {
            "extensions": (
                {"arcgrav.runner:execution": {"target": target}}
                if target is not None
                else {}
            )
        }
    return _synthetic_conformance_from_evidence(
        execution_boundary_artifact_id="boundary",
        records=records,
        documents=documents,
    )


class SyntheticConformanceIdentityTests(unittest.TestCase):
    def test_registered_scenarios_preserve_synthetic_identity(self) -> None:
        mock = {
            "class": "mock-model",
            "evidence_class": "provider-free-mock-model-execution",
        }
        # Scenario labels do not affect the result: classification comes from
        # the validated target composition and exact retained target evidence.
        self.assertTrue(_scope("arcgrav.mock-model.runner", mock, mock, registered_synthetic=True))
        self.assertTrue(_scope("arcgrav.mock-model.runner", registered_synthetic=True))

    def test_versioned_target_evidence_catches_other_mock_compositions(self) -> None:
        self.assertTrue(
            _scope(
                "other.registered-runner",
                {"class": "mock-model", "evidence_class": "provider-free"},
            )
        )
        self.assertFalse(
            _scope(
                "other.registered-runner",
                {"class": "live-provider", "evidence_class": "live-provider"},
            )
        )
        # An unrelated identity alone cannot assert a synthetic profile.
        self.assertFalse(_scope("unrelated.registered-runner", None))

    def test_registered_mock_missing_or_live_looking_evidence_fails_closed(self) -> None:
        with self.assertRaises(ReportingInputRevalidationError):
            _scope("arcgrav.mock-model.runner", None, registered_synthetic=True)
        with self.assertRaises(ReportingInputRevalidationError):
            _scope(
                "arcgrav.mock-model.runner",
                {"class": "live-provider", "evidence_class": "live-provider"},
                registered_synthetic=True,
            )


if __name__ == "__main__":
    unittest.main()
