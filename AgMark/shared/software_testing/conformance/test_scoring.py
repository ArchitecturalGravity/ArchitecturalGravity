"""Provider-free conformance tests for registered scoring and immutable score authority."""

from __future__ import annotations

from collections.abc import Mapping
import copy
import hashlib
from pathlib import Path
import unittest

from AgMark.shared.evaluation import (
    SCORER_INVOCATION_CONTRACT_ID,
    SCORER_INVOCATION_CONTRACT_VERSION,
    IdentityRef,
    ScoringContext,
    ScoringEvidenceInput,
    invoke_registered_scorer,
    validate_registered_scorer_outcome,
    validate_score_artifact,
)
from AgMark.shared.validation import (
    ArtifactSource,
    ContractRequirement,
    RetainedArtifactSource,
    validate_evidence_set_outcome,
    validate_lifecycle_evidence_outcome,
    validate_registration_binding_outcome,
)


_SCORER_ID = "arcgrav.scorer.conformance-test"
_SCORER_VERSION = "1.0.0"
_IMPLEMENTATION_ARTIFACT_ID = "conformance-scorer"
_IMPLEMENTATION_REFERENCE = (
    "AgMark/shared/software_testing/conformance/test_scoring.py"
)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _issue_codes(outcome: object) -> set[str]:
    return {issue.code for issue in getattr(outcome, "issues", ())}


def _metric_registration() -> dict[str, object]:
    return {
        "schema_id": "arcgrav.shared.schema.metric-registration",
        "schema_version": "1.0.0",
        "extensions": {},
        "registration_id": "arcgrav.metric.conformance-score",
        "registration_version": "1.0.0",
        "metric_id": "arcgrav.metric.conformance-score",
        "metric_version": "1.0.0",
        "name": "Conformance score",
        "description": "Provider-free registered scorer conformance metric.",
        "classification": "correctness",
        "comparison_track_id": "conformance",
        "is_primary_endpoint": False,
        "formula_or_algorithm": "Return a bounded score from exact retained response evidence.",
        "required_inputs": ["response"],
        "unit": "score",
        "valid_range": {
            "kind": "numeric",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "directionality": "higher_is_better",
        "numerator_denominator": {
            "uses_rate": False,
            "numerator_rule": "not a rate",
            "denominator_rule": "not a rate",
        },
        "repetition_aggregation": "identity",
        "case_aggregation": "identity",
        "state_treatment": [
            {
                "state": "completed",
                "disposition": "score",
            }
        ],
        "normalization_and_equivalence": "No normalization or semantic equivalence.",
        "availability_and_noncomparability": "Retain explicit shared availability states.",
        "required_companion_values": ["sample_count"],
        "presentation_precision": 3,
        "scorer_or_annotation": {
            "procedure_id": _SCORER_ID,
            "version": _SCORER_VERSION,
            "kind": "scorer",
        },
        "contracts": [
            {
                "id": SCORER_INVOCATION_CONTRACT_ID,
                "version": SCORER_INVOCATION_CONTRACT_VERSION,
            }
        ],
    }


def _scored_output(value: float = 1.0) -> dict[str, object]:
    return {
        "availability": "scored",
        "value": value,
        "companion_values": [
            {
                "name": "sample_count",
                "value": 1,
                "unit": "observation",
            }
        ],
        "failure_refs": [],
        "diagnostics": [],
        "extensions": {"arcgrav.test:conformance": "provider-free"},
    }


class RegisteredScoringConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        implementation_bytes = Path(__file__).read_bytes()
        self.implementation_source = ArtifactSource(
            artifact_id=_IMPLEMENTATION_ARTIFACT_ID,
            reference=_IMPLEMENTATION_REFERENCE,
            data=implementation_bytes,
        )
        self.registration = {
            "schema_id": "arcgrav.shared.schema.registration",
            "schema_version": "1.0.0",
            "extensions": {},
            "registration_id": _SCORER_ID,
            "registration_version": _SCORER_VERSION,
            "registration_kind": "scorer",
            "status": "active",
            "contracts": [
                {
                    "id": SCORER_INVOCATION_CONTRACT_ID,
                    "version": SCORER_INVOCATION_CONTRACT_VERSION,
                }
            ],
            "implementation_artifacts": [
                {
                    "artifact_id": _IMPLEMENTATION_ARTIFACT_ID,
                    "sha256": _sha256(implementation_bytes),
                    "reference": _IMPLEMENTATION_REFERENCE,
                    "availability": "retained",
                }
            ],
        }
        self.metric = _metric_registration()
        self.registration_outcome = validate_registration_binding_outcome(
            self.registration,
            expected_registration_id=_SCORER_ID,
            expected_registration_version=_SCORER_VERSION,
            contract_requirements=(
                ContractRequirement(
                    SCORER_INVOCATION_CONTRACT_ID,
                    (SCORER_INVOCATION_CONTRACT_VERSION,),
                ),
            ),
            artifact_sources=(self.implementation_source,),
            allowed_artifact_roots=(
                "AgMark/shared/software_testing/conformance",
            ),
            source_id="scorer-registration",
        )
        self.assertTrue(
            self.registration_outcome.valid,
            [issue.code for issue in self.registration_outcome.issues],
        )
        self.authority = validate_registered_scorer_outcome(
            self.registration,
            registration_outcome=self.registration_outcome,
            metric_registration=self.metric,
            implementation_artifact_id=_IMPLEMENTATION_ARTIFACT_ID,
            source_id="scorer-authority",
        )
        self.assertTrue(
            self.authority.valid,
            [issue.code for issue in self.authority.issues],
        )

        self.response_source = RetainedArtifactSource(
            artifact_id="response",
            reference="evidence/response.bin",
            data=b"retained response",
            provenance="runner:conformance",
        )
        self.response_artifact = {
            "artifact_id": "response",
            "sha256": self.response_source.sha256,
            "reference": self.response_source.reference,
            "availability": "retained",
        }
        self.evidence_outcome = self._evidence_outcome(
            generation_id="generation-scoring-conformance"
        )
        self.assertTrue(
            self.evidence_outcome.publication_authorized,
            [issue.code for issue in self.evidence_outcome.issues],
        )
        self.evidence = (
            ScoringEvidenceInput(
                role="response",
                artifact=self.response_artifact,
                source=self.response_source,
            ),
        )
        self.context = ScoringContext(
            accepted_generation_id="generation-scoring-conformance",
            accepted_snapshot_id="snapshot-scoring-conformance",
            execution_boundary_fingerprint=_sha256(b"boundary-scoring-conformance"),
            benchmark=IdentityRef("arcgrav.benchmark.conformance-test", "1.0.0"),
            case_set=IdentityRef("arcgrav.case-set.conformance-test", "1.0.0"),
            treatment_set=IdentityRef(
                "arcgrav.treatment-set.conformance-test",
                "1.0.0",
            ),
            case_id="case-scoring-conformance",
            treatment_id="treatment-scoring-conformance",
            repetition_ids=(1,),
            observation_ids=("observation-scoring-conformance",),
            scoring_grain="case",
            invocation_id="invocation-scoring-conformance",
        )

    def _evidence_outcome(self, *, generation_id: str):
        return validate_evidence_set_outcome(
            (self.response_artifact,),
            sources=(self.response_source,),
            evidence_set_id=f"evidence-set:{generation_id}",
            generation_id=generation_id,
            terminal_state="accepted",
            source_id=f"evidence:{generation_id}",
            required_artifact_ids=("response",),
        )

    def _invoke(self, scorer, *, metric=None, evidence=None, evidence_outcome=None, implementation_source=None):
        return invoke_registered_scorer(
            authority=self.authority,
            implementation_source=implementation_source or self.implementation_source,
            scorer=scorer,
            metric_registration=metric or self.metric,
            context=self.context,
            evidence=evidence or self.evidence,
            evidence_outcome=evidence_outcome or self.evidence_outcome,
            source_id="scorer-invocation",
        )

    def test_exact_registered_authority_and_input_binding_fail_closed(self) -> None:
        tampered_registration = copy.deepcopy(self.registration)
        tampered_registration["registration_version"] = "1.0.1"
        tampered_authority = validate_registered_scorer_outcome(
            tampered_registration,
            registration_outcome=self.registration_outcome,
            metric_registration=self.metric,
            implementation_artifact_id=_IMPLEMENTATION_ARTIFACT_ID,
            source_id="scorer-authority-tampered",
        )
        self.assertFalse(tampered_authority.valid)
        self.assertIn(
            "SCORER_REGISTRATION_AUTHORITY_MISMATCH",
            _issue_codes(tampered_authority),
        )

        wrong_role = (
            ScoringEvidenceInput(
                role="unexpected",
                artifact=self.response_artifact,
                source=self.response_source,
            ),
        )
        role_outcome = self._invoke(lambda _: _scored_output(), evidence=wrong_role)
        self.assertEqual("not_invoked", role_outcome.invocation_status)
        self.assertIn("SCORER_INPUT_ROLE_SET_MISMATCH", _issue_codes(role_outcome))

        generation_outcome = self._invoke(
            lambda _: _scored_output(),
            evidence_outcome=self._evidence_outcome(generation_id="generation-other"),
        )
        self.assertEqual("not_invoked", generation_outcome.invocation_status)
        self.assertIn(
            "SCORER_EVIDENCE_GENERATION_MISMATCH",
            _issue_codes(generation_outcome),
        )

        drifted_source = ArtifactSource(
            artifact_id=_IMPLEMENTATION_ARTIFACT_ID,
            reference=_IMPLEMENTATION_REFERENCE,
            data=self.implementation_source.data + b"\n# drift",
        )
        drift_outcome = self._invoke(
            lambda _: _scored_output(),
            implementation_source=drifted_source,
        )
        self.assertEqual("not_invoked", drift_outcome.invocation_status)
        self.assertIn(
            "SCORER_IMPLEMENTATION_HASH_MISMATCH",
            _issue_codes(drift_outcome),
        )

    def test_scorer_receives_mutation_isolated_registered_inputs(self) -> None:
        original_metric = copy.deepcopy(self.metric)
        original_artifact = copy.deepcopy(self.response_artifact)

        def scorer(call):
            with self.assertRaises(TypeError):
                call.metric_registration["name"] = "mutated"
            with self.assertRaises(TypeError):
                call.evidence_identity_by_role["response"]["artifact_id"] = "mutated"
            self.assertEqual(b"retained response", call.evidence_by_role["response"])
            return _scored_output()

        outcome = self._invoke(scorer)
        self.assertTrue(outcome.valid, [issue.code for issue in outcome.issues])
        self.assertEqual(original_metric, self.metric)
        self.assertEqual(original_artifact, self.response_artifact)

    def test_scorer_execution_failure_retains_no_score_authority(self) -> None:
        def failing_scorer(_):
            raise RuntimeError("provider-free scorer failure")

        outcome = self._invoke(failing_scorer)
        self.assertEqual("failed", outcome.invocation_status)
        self.assertIsNone(outcome.artifact)
        self.assertIn("SCORER_INVOCATION_FAILED", _issue_codes(outcome))

    def test_returned_result_domain_and_companion_rules_fail_closed(self) -> None:
        cases = (
            (
                "non-object",
                lambda _: "not-an-object",
                "SCORER_OUTPUT_INVALID",
            ),
            (
                "out-of-range",
                lambda _: _scored_output(1.5),
                "SCORER_OUTPUT_VALUE_RANGE_INVALID",
            ),
            (
                "missing-companion",
                lambda _: {
                    **_scored_output(),
                    "companion_values": [],
                },
                "SCORER_OUTPUT_REQUIRED_COMPANION_MISSING",
            ),
        )
        for label, scorer, expected_code in cases:
            with self.subTest(label=label):
                outcome = self._invoke(scorer)
                self.assertEqual("invalid_result", outcome.invocation_status)
                self.assertIsNone(outcome.artifact)
                self.assertIn(expected_code, _issue_codes(outcome))

    def test_score_artifact_retains_exact_identity_and_detects_tampering(self) -> None:
        outcome = self._invoke(lambda _: _scored_output())
        self.assertTrue(outcome.valid, [issue.code for issue in outcome.issues])
        artifact = outcome.artifact
        self.assertIsNotNone(artifact)
        assert artifact is not None

        self.assertTrue(str(artifact["score_artifact_id"]).startswith("score:"))
        role_bindings = artifact["extensions"][
            "arcgrav.shared.evaluation:input-role-bindings"
        ]
        self.assertEqual(
            self.response_artifact["sha256"],
            role_bindings["response"]["sha256"],
        )
        self.assertEqual(
            (),
            validate_score_artifact(
                artifact,
                authority=self.authority,
                metric_registration=self.metric,
                context=self.context,
                evidence=self.evidence,
                source_id="score-artifact",
            ),
        )

        tampered = _plain(artifact)
        assert isinstance(tampered, dict)
        tampered["value"] = 0.5
        issues = validate_score_artifact(
            tampered,
            authority=self.authority,
            metric_registration=self.metric,
            context=self.context,
            evidence=self.evidence,
            source_id="score-artifact-tampered",
        )
        self.assertIn(
            "SCORE_ARTIFACT_IDENTITY_INVALID",
            {issue.code for issue in issues},
        )

    def test_non_scored_results_require_and_retain_explicit_reason(self) -> None:
        metric = copy.deepcopy(self.metric)
        metric["required_companion_values"] = []

        valid = self._invoke(
            lambda _: {
                "availability": "failed",
                "companion_values": [],
                "failure_refs": ["failure:scorer-conformance"],
                "diagnostics": [],
                "extensions": {},
            },
            metric=metric,
        )
        self.assertTrue(valid.valid, [issue.code for issue in valid.issues])
        assert valid.artifact is not None
        self.assertEqual("failed", valid.artifact["availability"])
        self.assertNotIn("value", valid.artifact)
        self.assertEqual(
            ("failure:scorer-conformance",),
            valid.artifact["failure_refs"],
        )

        invalid = self._invoke(
            lambda _: {
                "availability": "failed",
                "companion_values": [],
                "failure_refs": [],
                "diagnostics": [],
                "extensions": {},
            },
            metric=metric,
        )
        self.assertEqual("invalid_result", invalid.invocation_status)
        self.assertIn("SCORER_OUTPUT_REASON_MISSING", _issue_codes(invalid))

    def test_score_artifact_cannot_replace_required_golden_lifecycle_authority(self) -> None:
        scored = self._invoke(lambda _: _scored_output())
        self.assertTrue(scored.valid, [issue.code for issue in scored.issues])
        assert scored.artifact is not None

        plan_hash = _sha256(b"run-plan")
        run_plan = {
            "schema_id": "arcgrav.shared.schema.run-plan",
            "schema_version": "1.0.0",
            "run_plan_id": "plan-scoring-conformance",
            "plan_sha256": plan_hash,
            "execution_boundary_fingerprint": self.context.execution_boundary_fingerprint,
            "golden_required": True,
            "contracts": [],
            "repetitions": 1,
            "observations": [
                {
                    "request_id": "request-scoring-conformance",
                    "observation_id": self.context.observation_ids[0],
                    "case_id": self.context.case_id,
                    "treatment_id": self.context.treatment_id,
                    "repetition": 1,
                    "execution_boundary_fingerprint": self.context.execution_boundary_fingerprint,
                }
            ],
        }
        run_outcome = {
            "schema_id": "arcgrav.shared.schema.run-outcome",
            "schema_version": "1.0.0",
            "generation_id": self.context.accepted_generation_id,
            "execution_boundary_fingerprint": self.context.execution_boundary_fingerprint,
            "run_plan": {
                "artifact_id": run_plan["run_plan_id"],
                "sha256": plan_hash,
            },
            "status": "blocked",
            "blocked_manifest": {},
            "finalized_at": "2026-01-01T00:02:00Z",
        }
        lifecycle = validate_lifecycle_evidence_outcome(
            run_plan=run_plan,
            plan_completed_at="2026-01-01T00:00:00Z",
            accepted_at="2026-01-01T00:01:00Z",
            run_outcome=run_outcome,
            golden_observation=None,
            treatment_observations=(),
            score_artifacts=(scored.artifact,),
            source_id="lifecycle-score-non-escalation",
        )

        self.assertFalse(lifecycle.valid)
        self.assertIn(
            "LIFECYCLE_SCORE_BEFORE_GOLDEN_AUTHORITY",
            _issue_codes(lifecycle),
        )


if __name__ == "__main__":
    unittest.main()
