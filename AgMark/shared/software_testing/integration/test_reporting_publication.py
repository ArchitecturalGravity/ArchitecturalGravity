"""Provider-free integration tests for reporting publication validation."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest

from AgMark.shared.validation import (
    RetainedArtifactSource,
    validate_evidence_set_outcome,
    validate_lifecycle_evidence_outcome,
    validate_reporting_handoff,
)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _source(artifact_id: str, reference: str, value: object) -> RetainedArtifactSource:
    return RetainedArtifactSource(
        artifact_id=artifact_id,
        reference=reference,
        data=_json_bytes(value),
        provenance="integration:reporting-publication",
    )


def _ref(
    source: RetainedArtifactSource,
    *,
    schema_id: str | None = None,
    schema_version: str | None = None,
    availability: str = "retained",
) -> dict[str, object]:
    value: dict[str, object] = {
        "artifact_id": source.artifact_id,
        "sha256": source.sha256,
        "reference": source.reference,
        "availability": availability,
    }
    if schema_id is not None or schema_version is not None:
        assert schema_id is not None and schema_version is not None
        value["schema"] = {
            "schema_id": schema_id,
            "schema_version": schema_version,
        }
    return value


def _codes(issues: object) -> set[str]:
    return {issue.code for issue in issues}  # type: ignore[union-attr]


class ReportingPublicationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_id = "integration-reporting-publication"
        self.generation_id = "generation-reporting-publication"
        self.boundary = _sha256(b"boundary-reporting-publication")
        self.plan_hash = _sha256(b"plan-reporting-publication")
        self.golden_contract = {
            "id": "arcgrav.shared.contract.golden-execution",
            "version": "1.0.0",
        }
        self.treatment_contract = {
            "id": "arcgrav.shared.contract.runner-invocation",
            "version": "1.0.0",
        }
        self.run_plan = {
            "schema_id": "arcgrav.shared.schema.run-plan",
            "schema_version": "1.0.0",
            "run_plan_id": "plan-reporting-publication",
            "plan_sha256": self.plan_hash,
            "execution_boundary_fingerprint": self.boundary,
            "golden_required": True,
            "contracts": [self.golden_contract, self.treatment_contract],
            "repetitions": 1,
            "observations": [
                {
                    "request_id": "request-reporting-publication",
                    "observation_id": "observation-reporting-publication",
                    "case_id": "case-reporting-publication",
                    "treatment_id": "treatment-reporting-publication",
                    "repetition": 1,
                    "execution_boundary_fingerprint": self.boundary,
                }
            ],
        }
        self.golden_observation = {
            "schema_id": "arcgrav.shared.schema.golden-observation",
            "schema_version": "2.0.0",
            "accepted_generation_id": self.generation_id,
            "execution_boundary_fingerprint": self.boundary,
            "contract": self.golden_contract,
            "started_at": "2026-01-01T00:01:10Z",
            "completed_at": "2026-01-01T00:01:20Z",
            "admission_state": "admitted",
            "status": "completed",
            "output": {"availability": "retained"},
        }
        self.treatment_observation = {
            "schema_id": "arcgrav.shared.schema.treatment-observation",
            "schema_version": "1.0.0",
            "accepted_generation_id": self.generation_id,
            "execution_boundary_fingerprint": self.boundary,
            "contract": self.treatment_contract,
            "request_id": "request-reporting-publication",
            "observation_id": "observation-reporting-publication",
            "case_id": "case-reporting-publication",
            "treatment_id": "treatment-reporting-publication",
            "repetition": 1,
            "attempts": [
                {
                    "started_at": "2026-01-01T00:01:30Z",
                    "completed_at": "2026-01-01T00:01:40Z",
                }
            ],
        }
        self.score_artifact = {
            "schema_id": "arcgrav.shared.schema.score-artifact",
            "schema_version": "1.0.0",
            "accepted_generation_id": self.generation_id,
            "execution_boundary_fingerprint": self.boundary,
            "observation_ids": ["observation-reporting-publication"],
        }
        self.accepted_source = RetainedArtifactSource(
            artifact_id="accepted-reporting-evidence",
            reference="accepted/reporting-evidence.json",
            data=b'{"accepted":true}',
            provenance="runtime:accepted-reporting-evidence",
        )
        self.accepted_ref = _ref(self.accepted_source)
        self.run_outcome = {
            "schema_id": "arcgrav.shared.schema.run-outcome",
            "schema_version": "1.0.0",
            "generation_id": self.generation_id,
            "execution_boundary_fingerprint": self.boundary,
            "run_plan": {
                "artifact_id": self.run_plan["run_plan_id"],
                "sha256": self.plan_hash,
            },
            "status": "accepted",
            "artifact_index": [self.accepted_ref],
            "finalized_at": "2026-01-01T00:02:00Z",
        }
        self.lifecycle = validate_lifecycle_evidence_outcome(
            run_plan=self.run_plan,
            plan_completed_at="2026-01-01T00:00:00Z",
            accepted_at="2026-01-01T00:01:00Z",
            run_outcome=self.run_outcome,
            golden_observation=self.golden_observation,
            treatment_observations=(self.treatment_observation,),
            score_artifacts=(self.score_artifact,),
            source_id=self.source_id,
        )
        self.assertTrue(self.lifecycle.valid, _codes(self.lifecycle.issues))
        self.evidence = validate_evidence_set_outcome(
            (self.accepted_ref,),
            sources=(self.accepted_source,),
            evidence_set_id="evidence-set-reporting-publication",
            generation_id=self.generation_id,
            terminal_state="accepted",
            source_id=self.source_id,
            required_artifact_ids=(self.accepted_source.artifact_id,),
        )
        self.assertTrue(self.evidence.publication_authorized, _codes(self.evidence.issues))

    def test_valid_accepted_handoff_is_authorized(self) -> None:
        self.assertEqual(
            (),
            validate_reporting_handoff(
                run_outcome=self.run_outcome,
                lifecycle_outcome=self.lifecycle,
                evidence_outcome=self.evidence,
                source_id=self.source_id,
            ),
        )

    def test_reporting_handoff_rejects_nonaccepted_or_mismatched_authority(self) -> None:
        blocked = copy.deepcopy(self.run_outcome)
        blocked["status"] = "blocked"
        blocked["blocked_manifest"] = {}
        issues = validate_reporting_handoff(
            run_outcome=blocked,
            lifecycle_outcome=self.lifecycle,
            evidence_outcome=self.evidence,
            source_id=self.source_id,
        )
        codes = _codes(issues)
        self.assertIn("PUBLICATION_LIFECYCLE_AUTHORITY_MISMATCH", codes)
        self.assertIn("PUBLICATION_RUN_NOT_ACCEPTED", codes)

        other_evidence = validate_evidence_set_outcome(
            (self.accepted_ref,),
            sources=(self.accepted_source,),
            evidence_set_id="evidence-set-other-generation",
            generation_id="generation-other",
            terminal_state="accepted",
            source_id=self.source_id,
            required_artifact_ids=(self.accepted_source.artifact_id,),
        )
        mismatch = validate_reporting_handoff(
            run_outcome=self.run_outcome,
            lifecycle_outcome=self.lifecycle,
            evidence_outcome=other_evidence,
            source_id=self.source_id,
        )
        self.assertIn("PUBLICATION_EVIDENCE_GENERATION_MISMATCH", _codes(mismatch))


if __name__ == "__main__":
    unittest.main()
