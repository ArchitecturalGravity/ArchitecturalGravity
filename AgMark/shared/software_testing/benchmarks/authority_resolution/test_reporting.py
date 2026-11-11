"""Provider-free ARB reporting-policy verification over registered authority.

These fixtures exercise registered report/logic bindings and factual prerequisite outcomes.
They are developer-test inputs only and are never accepted benchmark evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from AgMark.shared.reporting import (
    GeneratedReportBundle,
    GeneratedReportComponent,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_BENCHMARK_REGISTRATION = (
    _REPOSITORY_ROOT
    / "AgMark/Authority_Resolution_Benchmark/registrations/v2.0.0/"
    "benchmark-core.json"
)
_REPORT_CONFIGURATION = (
    _REPOSITORY_ROOT
    / "AgMark/Authority_Resolution_Benchmark/reporting/v2.0.0/"
    "report-configuration.json"
)
_LOGIC_SET = (
    _REPOSITORY_ROOT
    / "AgMark/Authority_Resolution_Benchmark/logic/v2.0.0/logic-set.json"
)
_AUTHORITY_EXTENSION = "arcgrav.authority-resolution:benchmark-authority"
_REPORT_CONFIGURATION_EXTENSION = (
    "arcgrav.authority-resolution:report-configuration"
)
_REPORT_INTERPRETATION_EXTENSION = (
    "arcgrav.authority-resolution:report-interpretation"
)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _bundle(
    *,
    report_configuration: dict[str, object],
    logic_set: dict[str, object],
    prerequisite_results: tuple[bool, ...],
    reasons: tuple[str, ...] = (),
    report_status: str = "complete",
) -> GeneratedReportBundle:
    generation_id = "generation-arb-reporting-policy-fixture"
    report_id = "report-arb-reporting-policy-fixture"
    manifest_id = "manifest-arb-reporting-policy-fixture"

    configuration = report_configuration["extensions"][
        _REPORT_CONFIGURATION_EXTENSION
    ]
    assert isinstance(configuration, dict)
    prerequisites = logic_set["registered_prerequisites"]
    assert isinstance(prerequisites, list)
    if len(prerequisite_results) != len(prerequisites):
        raise ValueError("prerequisite result count must match registered authority")

    policy = configuration["registered_prerequisites"]
    assert isinstance(policy, dict)
    extension = {
        "configuration": {
            "id": report_configuration["registration_id"],
            "version": report_configuration["registration_version"],
        },
        "sections": {
            "arb_registered_prerequisites": {
                "availability": "available",
                "state": "satisfied" if all(prerequisite_results) else "unsatisfied",
                "registered_logic_set": {
                    "id": logic_set["logic_set_id"],
                    "version": logic_set["logic_set_version"],
                },
                "registered_logic_prerequisites": [
                    {
                        "prerequisite": prerequisite,
                        "state": "satisfied" if satisfied else "unsatisfied",
                    }
                    for prerequisite, satisfied in zip(
                        prerequisites,
                        prerequisite_results,
                        strict=True,
                    )
                ],
                "finalized_accepted_run_required": policy[
                    "require_finalized_accepted_run"
                ],
                "completion_validation": "required",
                "reasons": list(reasons),
            }
        },
    }
    report_document = {
        "schema_id": "arcgrav.shared.schema.report",
        "schema_version": "3.0.0",
        "report_id": report_id,
        "report_version": "1.0.0",
        "accepted_generation_id": generation_id,
        "status": report_status,
        "report_manifest_id": manifest_id,
        "extensions": {_REPORT_INTERPRETATION_EXTENSION: extension},
    }
    canonical_evidence_document = {
        "report_id": report_id,
        "accepted_generation_id": generation_id,
        "extensions": {_REPORT_INTERPRETATION_EXTENSION: extension},
    }

    report = GeneratedReportComponent(
        artifact_id=f"{report_id}:machine-report",
        reference="generated/report.json",
        data=_json_bytes(report_document),
        media_type="application/json",
        encoding="utf-8",
        schema_id="arcgrav.shared.schema.report",
        schema_version="3.0.0",
    )
    canonical = GeneratedReportComponent(
        artifact_id=f"{report_id}:canonical-evidence",
        reference="generated/canonical-evidence.json",
        data=_json_bytes(canonical_evidence_document),
        media_type="application/json",
        encoding="utf-8",
    )
    human = GeneratedReportComponent(
        artifact_id=f"{report_id}:human-report",
        reference="generated/report.md",
        data=b"# ARB reporting policy fixture\n",
        media_type="text/markdown",
        encoding="utf-8",
    )
    manifest_document = {
        "schema_id": "arcgrav.shared.schema.report-manifest",
        "schema_version": "1.0.0",
        "extensions": {},
        "manifest_id": manifest_id,
        "accepted_generation_id": generation_id,
        "report": report.to_artifact_ref().to_dict(),
        "inputs": [
            {
                "artifact_id": "accepted-input-arb-reporting-policy-fixture",
                "sha256": "sha256:" + ("1" * 64),
                "reference": "accepted/input.json",
                "availability": "retained",
            }
        ],
        "input_evidence_set_id": "evidence-set-arb-reporting-policy-fixture",
        "procedure": {
            "id": "arcgrav.procedure.arb-reporting-policy-fixture",
            "version": "1.0.0",
            "command_or_procedure": "provider-free policy completion fixture",
        },
        "generator": {
            "id": "arcgrav.generator.arb-reporting-policy-fixture",
            "version": "1.0.0",
        },
        "components": [
            report.to_artifact_ref().to_dict(),
            canonical.to_artifact_ref().to_dict(),
            human.to_artifact_ref().to_dict(),
        ],
        "generated_at": "2026-09-20T00:00:00Z",
    }
    manifest = GeneratedReportComponent(
        artifact_id=manifest_id,
        reference="generated/report-manifest.json",
        data=_json_bytes(manifest_document),
        media_type="application/json",
        encoding="utf-8",
        schema_id="arcgrav.shared.schema.report-manifest",
        schema_version="1.0.0",
    )
    return GeneratedReportBundle(
        report_document=report_document,
        canonical_evidence_document=canonical_evidence_document,
        report_manifest=manifest_document,
        report=report,
        canonical_evidence=canonical,
        human=human,
        manifest=manifest,
    )


class AuthorityResolutionReportingPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registration = _read_json(_BENCHMARK_REGISTRATION)
        self.report_configuration = _read_json(_REPORT_CONFIGURATION)
        self.logic_set = _read_json(_LOGIC_SET)
        self.configuration = self.report_configuration["extensions"][
            _REPORT_CONFIGURATION_EXTENSION
        ]
        assert isinstance(self.configuration, dict)
        self.policy = self.configuration["registered_prerequisites"]
        assert isinstance(self.policy, dict)
        prerequisites = self.logic_set["registered_prerequisites"]
        assert isinstance(prerequisites, list)
        self.prerequisites = tuple(prerequisites)

    def test_active_registration_and_report_policy_bind_exact_logic_authority(self) -> None:
        selected = self.registration["extensions"][_AUTHORITY_EXTENSION][
            "selected_authority"
        ]
        self.assertEqual(
            {
                "module": "AgMark.Authority_Resolution_Benchmark.reporting.prerequisites",
                "callable": "evaluate_report_extensions",
                "artifact_id": "arb-report-prerequisites",
            },
            selected["report_evaluator"],
        )
        self.assertEqual(
            {
                "registration_id": self.report_configuration["registration_id"],
                "registration_version": self.report_configuration[
                    "registration_version"
                ],
                "artifact_id": "arb-core-report-configuration",
            },
            selected["report_configuration"],
        )
        self.assertEqual(
            {
                "id": self.logic_set["logic_set_id"],
                "version": self.logic_set["logic_set_version"],
            },
            self.policy["logic_set"],
        )
        self.assertTrue(
            self.policy["require_all_registered_logic_set_prerequisites"]
        )
        self.assertTrue(self.policy["require_finalized_accepted_run"])
        self.assertTrue(
            self.policy["require_automatic_completion_validation"]
        )
        self.assertGreater(len(self.prerequisites), 0)

    def test_satisfied_prerequisites_have_no_permission_state(self) -> None:
        from AgMark.shared.reporting.completion import completion_record
        bundle = _bundle(
            report_configuration=self.report_configuration,
            logic_set=self.logic_set,
            prerequisite_results=(True,) * len(self.prerequisites),
        )
        completion = completion_record("generation-arb-reporting-policy-fixture", status="complete", bundle=bundle)
        self.assertNotIn("claim_eligibility", completion)
        self.assertNotIn("claim_state", bundle.report_document)
        section = bundle.report_document["extensions"][_REPORT_INTERPRETATION_EXTENSION]["sections"]["arb_registered_prerequisites"]
        self.assertEqual("satisfied", section["state"])
        self.assertEqual(bundle.report.sha256, next(
            item["sha256"] for item in completion["report"]["components"]
            if item["role"] == "machine_json"))

    def test_each_prerequisite_failure_is_retained(self) -> None:
        from AgMark.shared.reporting.completion import completion_record
        for index, prerequisite in enumerate(self.prerequisites):
            with self.subTest(prerequisite=prerequisite):
                results = [True] * len(self.prerequisites)
                results[index] = False
                bundle = _bundle(
                    report_configuration=self.report_configuration,
                    logic_set=self.logic_set,
                    prerequisite_results=tuple(results),
                    reasons=(f"registered_logic_prerequisite_unsatisfied:{index}",),
                )
                completion = completion_record("generation-arb-reporting-policy-fixture", status="complete", bundle=bundle)
                self.assertNotIn("claim_eligibility", completion)
                retained = json.loads(bundle.report.data)
                self.assertNotIn("claim_state", retained)
                section = retained["extensions"][_REPORT_INTERPRETATION_EXTENSION]["sections"]["arb_registered_prerequisites"]
                self.assertEqual("unsatisfied", section["registered_logic_prerequisites"][index]["state"])
                self.assertIn(f"registered_logic_prerequisite_unsatisfied:{index}", section["reasons"])

    def test_measurement_limitations_preserve_metric_semantics(self) -> None:
        self.assertIn("non_comparable", self.configuration["availability_handling"]["preserve_states"])
        self.assertTrue(any("ordering" in text for text in self.configuration["conclusion_boundaries"]))
        for key in ("eligible_label", "ineligible_label", "no_implicit_promotion_from_report_status"):
            self.assertNotIn(key, self.policy)

    def test_unsuccessful_completion_cannot_retain_a_report(self) -> None:
        from AgMark.shared.reporting.completion import completion_record
        bundle = _bundle(
            report_configuration=self.report_configuration,
            logic_set=self.logic_set,
            prerequisite_results=(True,) * len(self.prerequisites),
        )
        for status in ("validation_failed", "report_failed", "not_applicable"):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    completion_record("generation-arb-reporting-policy-fixture", status=status, bundle=bundle)
                failed = completion_record("generation-arb-reporting-policy-fixture", status=status)
                self.assertIsNone(failed["report"])
                self.assertNotIn("claim_eligibility", failed)


if __name__ == "__main__":
    unittest.main()
