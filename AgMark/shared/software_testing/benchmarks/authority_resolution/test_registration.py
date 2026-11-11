"""Provider-free ARB active-registration authority tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from AgMark.shared.validation import (
    ArtifactSource,
    BenchmarkDiscoveryCandidate,
    ContractRequirement,
    validate_benchmark_discovery,
    validate_registration_binding_outcome,
)


_ROOT = Path(__file__).resolve().parents[5]
_REGISTRATION_REFERENCE = (
    "AgMark/Authority_Resolution_Benchmark/registrations/v2.0.0/"
    "benchmark-core.json"
)
_REGISTRATION_ID = "arcgrav.authority-resolution.benchmark.core"
_REGISTRATION_VERSION = "2.0.0"
_AUTHORITY_EXTENSION = "arcgrav.authority-resolution:benchmark-authority"

_CONTRACTS = (
    ("arcgrav.shared.runner-invocation", "2.0.0"),
    ("arcgrav.shared.launch-environment", "1.0.0"),
    ("arcgrav.shared.transient-invocation", "1.0.0"),
    ("arcgrav.shared.golden-execution", "2.0.0"),
    ("arcgrav.shared.run-lifecycle", "1.0.0"),
    ("arcgrav.shared.evidence-validation", "1.0.0"),
    ("arcgrav.shared.scorer-invocation", "1.0.0"),
    ("arcgrav.shared.failure-taxonomy", "1.0.0"),
    ("arcgrav.shared.report-generation", "3.0.0"),
    ("arcgrav.shared.run-completion", "2.0.0"),
)

_EXPECTED_ARTIFACT_IDS = {
    "arb-core-case-set",
    "arb-core-case-input",
    "arb-core-treatment-set",
    "arb-prompt-arcgrav",
    "arb-prompt-common-prose",
    "arb-prompt-markdown",
    "arb-prompt-xml",
    "arb-prompt-yaml",
    "arb-core-logic-set",
    "arb-frozen-golden-source",
    "arb-structured-output-parser",
    "arb-primary-metric-registration",
    "arb-primary-scorer-registration",
    "arb-field-accuracy-scorer",
    "arb-core-report-configuration",
    "arb-report-prerequisites",
}


def _load_registration() -> dict[str, object]:
    return json.loads((_ROOT / _REGISTRATION_REFERENCE).read_text(encoding="utf-8"))


def _artifact_sources(
    registration: dict[str, object],
) -> tuple[ArtifactSource, ...]:
    return tuple(
        ArtifactSource(
            artifact_id=artifact["artifact_id"],
            reference=artifact["reference"],
            data=(_ROOT / artifact["reference"]).read_bytes(),
        )
        for artifact in registration["implementation_artifacts"]
    )


def _registration_outcome(
    registration: dict[str, object],
):
    return validate_registration_binding_outcome(
        registration,
        expected_registration_id=_REGISTRATION_ID,
        expected_registration_version=_REGISTRATION_VERSION,
        contract_requirements=tuple(
            ContractRequirement(contract_id, (version,))
            for contract_id, version in _CONTRACTS
        ),
        artifact_sources=_artifact_sources(registration),
        allowed_artifact_roots=("AgMark/Authority_Resolution_Benchmark",),
        source_id="arb-core-benchmark-registration",
    )


class ActiveAuthorityResolutionRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registration = _load_registration()

    def test_complete_core_registration_is_valid_and_discoverable(self) -> None:
        outcome = _registration_outcome(self.registration)
        self.assertTrue(outcome.valid, [issue.code for issue in outcome.issues])
        self.assertEqual("benchmark", self.registration["registration_kind"])
        self.assertEqual("active", self.registration["status"])
        self.assertEqual(
            _EXPECTED_ARTIFACT_IDS,
            {
                artifact["artifact_id"]
                for artifact in self.registration["implementation_artifacts"]
            },
        )

        authority = self.registration["extensions"][_AUTHORITY_EXTENSION]
        selected = authority["selected_authority"]
        self.assertEqual(
            ("arcgrav.authority-resolution.case-set.core", "1.0.0"),
            (selected["case_set"]["id"], selected["case_set"]["version"]),
        )
        self.assertEqual(
            ("arcgrav.authority-resolution.treatment-set.core", "2.0.0"),
            (
                selected["treatment_set"]["id"],
                selected["treatment_set"]["version"],
            ),
        )
        self.assertEqual(
            ("arcgrav.authority-resolution.logic-set.core", "2.0.0"),
            (selected["logic_set"]["id"], selected["logic_set"]["version"]),
        )
        self.assertTrue(selected["primary_metric"]["is_primary_endpoint"])
        self.assertEqual(
            "arcgrav.authority-resolution.field-accuracy",
            authority["comparison_track_id"],
        )
        self.assertEqual("registered_file", selected["golden_authority"]["input_transport"])
        self.assertEqual("arb-core-case-input", selected["golden_authority"]["input_artifact_id"])
        self.assertEqual(
            ["arb-frozen-golden-source", "arb-core-case-input"],
            selected["golden_authority"]["implementation_artifact_ids"],
        )
        self.assertEqual(
            "arcgrav.authority-resolution.metric.field-accuracy",
            selected["primary_metric"]["metric_id"],
        )
        self.assertTrue(
            selected["golden_authority"][
                "requires_successful_nonempty_retained_stdout_before_treatments"
            ]
        )

        discovery = validate_benchmark_discovery(
            (
                BenchmarkDiscoveryCandidate(
                    package_root="AgMark/Authority_Resolution_Benchmark",
                    registration_source_id="arb-core-benchmark-registration",
                    registration=self.registration,
                    registration_validation=outcome,
                ),
            ),
            source_id="arb-core-benchmark-discovery",
        )
        self.assertEqual((), discovery)

    def test_selected_resource_drift_fails_closed_before_discovery(self) -> None:
        drifted = copy.deepcopy(self.registration)
        artifact = next(
            item
            for item in drifted["implementation_artifacts"]
            if item["artifact_id"] == "arb-core-case-set"
        )
        artifact["sha256"] = "sha256:" + "0" * 64

        outcome = _registration_outcome(drifted)
        self.assertFalse(outcome.valid)
        self.assertIn(
            "REGISTRATION_ARTIFACT_HASH_MISMATCH",
            {issue.code for issue in outcome.issues},
        )

        discovery = validate_benchmark_discovery(
            (
                BenchmarkDiscoveryCandidate(
                    package_root="AgMark/Authority_Resolution_Benchmark",
                    registration_source_id="arb-core-benchmark-registration",
                    registration=drifted,
                    registration_validation=outcome,
                ),
            ),
            source_id="arb-core-benchmark-discovery",
        )
        self.assertIn(
            "BENCHMARK_DISCOVERY_REGISTRATION_INVALID",
            {issue.code for issue in discovery},
        )

    def test_post_validation_selection_mutation_cannot_acquire_authority(self) -> None:
        outcome = _registration_outcome(self.registration)
        self.assertTrue(outcome.valid)

        mutated = copy.deepcopy(self.registration)
        authority = mutated["extensions"][_AUTHORITY_EXTENSION]
        authority["selected_authority"]["optional_metric"] = {
            "registration_id": "arcgrav.authority-resolution.metric.unregistered",
            "registration_version": "1.0.0",
        }

        discovery = validate_benchmark_discovery(
            (
                BenchmarkDiscoveryCandidate(
                    package_root="AgMark/Authority_Resolution_Benchmark",
                    registration_source_id="arb-core-benchmark-registration",
                    registration=mutated,
                    registration_validation=outcome,
                ),
            ),
            source_id="arb-core-benchmark-discovery",
        )
        self.assertIn(
            "BENCHMARK_DISCOVERY_REGISTRATION_VALIDATION_MISMATCH",
            {issue.code for issue in discovery},
        )

    def test_unselected_extension_families_remain_explicitly_inactive(self) -> None:
        authority = self.registration["extensions"][_AUTHORITY_EXTENSION]
        inactive = authority["inactive_by_default"]
        self.assertTrue(inactive)
        self.assertTrue(all(inactive.values()))
        self.assertNotIn("optional_metric", authority["selected_authority"])

    def test_registered_v1_case_resource_is_installed(self) -> None:
        arb_root = _ROOT / "AgMark/Authority_Resolution_Benchmark"
        self.assertTrue((arb_root / "cases/v1.0.0/arb-core-001.json").is_file())


if __name__ == "__main__":
    unittest.main()
