"""Provider-free conformance tests for shared failure taxonomy resolution."""

from __future__ import annotations

import copy
import unittest

from AgMark.shared.evaluation.failures import (
    ExtensionFailureClassRegistration,
    FailureCandidate,
    FailureValidationError,
    MetricPrecedenceOverride,
    resolve_failures,
    resolve_metric_failures,
    runner_terminal_failure_class,
)
from AgMark.shared.validation import (
    SchemaIdentity,
    SourceArtifact,
    ValidationResult,
    sha256_bytes,
)


def _candidate(
    candidate_id: str,
    failure_class: str,
    authority_layer: str,
    *,
    affected_evidence_id: str = "evidence-1",
    source_id: str = "source-1",
    diagnostic_id: str = "diagnostic-1",
    class_version: str | None = None,
    redacted_details: dict[str, object] | None = None,
) -> FailureCandidate:
    return FailureCandidate(
        candidate_id=candidate_id,
        failure_class=failure_class,
        authority_layer=authority_layer,
        affected_evidence_id=affected_evidence_id,
        source_id=source_id,
        diagnostic_id=diagnostic_id,
        class_version=class_version,
        redacted_details=redacted_details or {},
    )


class FailureResolutionConformanceTests(unittest.TestCase):
    def test_earlier_authority_layers_dominate_and_all_candidates_are_retained(self) -> None:
        candidates = (
            _candidate("task", "task_incorrect", "task"),
            _candidate(
                "integrity",
                "artifact_integrity_mismatch",
                "identity_integrity",
            ),
            _candidate("registration", "registration_invalid", "registration"),
        )

        forward = resolve_failures(candidates)
        reverse = resolve_failures(tuple(reversed(candidates)))

        self.assertEqual("registration", forward.primary.candidate_id)
        self.assertEqual(
            ("registration", "integrity", "task"),
            tuple(candidate.candidate_id for candidate in forward.candidates),
        )
        self.assertEqual(
            ("integrity", "task"),
            tuple(candidate.candidate_id for candidate in forward.suppressed),
        )
        self.assertEqual(forward.to_dict(), reverse.to_dict())
        self.assertEqual(forward.resolution_sha256, reverse.resolution_sha256)

    def test_default_within_layer_precedence_and_tie_breaking_are_deterministic(self) -> None:
        resolution = resolve_failures(
            (
                _candidate("failed", "execution_failed", "execution"),
                _candidate("timeout", "timed_out", "execution"),
                _candidate("unsupported", "unsupported_execution", "execution"),
            )
        )
        self.assertEqual("unsupported", resolution.primary.candidate_id)
        self.assertEqual(
            ("unsupported", "timeout", "failed"),
            tuple(candidate.candidate_id for candidate in resolution.candidates),
        )

        tied = (
            _candidate(
                "candidate-z",
                "evidence_missing",
                "evidence",
                affected_evidence_id="evidence-b",
                source_id="source-a",
            ),
            _candidate(
                "candidate-b",
                "evidence_missing",
                "evidence",
                affected_evidence_id="evidence-a",
                source_id="source-b",
            ),
            _candidate(
                "candidate-a",
                "evidence_missing",
                "evidence",
                affected_evidence_id="evidence-a",
                source_id="source-a",
            ),
        )
        tied_resolution = resolve_failures(tied)
        self.assertEqual(
            ("candidate-a", "candidate-b", "candidate-z"),
            tuple(candidate.candidate_id for candidate in tied_resolution.candidates),
        )

    def test_metric_override_reorders_only_registered_classes_within_one_layer(self) -> None:
        candidates = (
            _candidate("timeout", "timed_out", "execution"),
            _candidate("failed", "execution_failed", "execution"),
        )
        override = MetricPrecedenceOverride(
            metric_registration_id="arcgrav.metric.conformance",
            metric_registration_version="1.0.0",
            authority_layer="execution",
            ordered_classes=("execution_failed", "timed_out"),
        )

        global_resolution = resolve_failures(candidates)
        metric_resolution = resolve_metric_failures(
            candidates,
            precedence_override=override,
        )

        self.assertEqual("timeout", global_resolution.primary.candidate_id)
        self.assertEqual("failed", metric_resolution.primary.candidate_id)
        self.assertEqual("metric_override", metric_resolution.precedence_basis["mode"])
        self.assertEqual(
            "arcgrav.metric.conformance",
            metric_resolution.precedence_basis["metric_rule"][
                "metric_registration_id"
            ],
        )

        invalid_override = MetricPrecedenceOverride(
            metric_registration_id="arcgrav.metric.invalid",
            metric_registration_version="1.0.0",
            authority_layer="execution",
            ordered_classes=("task_incorrect",),
        )
        with self.assertRaises(FailureValidationError) as raised:
            resolve_metric_failures(
                candidates,
                precedence_override=invalid_override,
            )
        self.assertEqual(
            {"FAILURE_METRIC_OVERRIDE_CLASS_INVALID"},
            {issue.code for issue in raised.exception.issues},
        )

    def test_unknown_alias_and_class_layer_mismatch_fail_closed(self) -> None:
        invalid_candidates = (
            _candidate("alias", "timeout", "execution"),
            _candidate("wrong-layer", "timed_out", "task"),
        )

        with self.assertRaises(FailureValidationError) as raised:
            resolve_failures(invalid_candidates)

        self.assertEqual(
            {"FAILURE_CLASS_LAYER_MISMATCH", "FAILURE_CLASS_UNKNOWN"},
            {issue.code for issue in raised.exception.issues},
        )
        self.assertEqual(
            tuple(sorted(raised.exception.issues)),
            raised.exception.issues,
        )

    def test_runner_status_mapping_is_explicit_and_does_not_mutate_source_evidence(self) -> None:
        observation = {
            "terminal_status": "timed_out",
            "response": {"availability": "not_produced", "content": b""},
        }
        original = copy.deepcopy(observation)

        self.assertEqual(
            "timed_out",
            runner_terminal_failure_class(observation["terminal_status"]),
        )
        self.assertIsNone(runner_terminal_failure_class("completed"))
        self.assertEqual("unsupported_execution", runner_terminal_failure_class("unsupported"))
        self.assertEqual("cancelled", runner_terminal_failure_class("cancelled"))
        self.assertEqual("execution_failed", runner_terminal_failure_class("failed"))
        self.assertEqual(original, observation)

        with self.assertRaises(ValueError):
            runner_terminal_failure_class("unknown")

    def test_task_and_extension_classes_cannot_outrank_earlier_shared_authority(self) -> None:
        extension = ExtensionFailureClassRegistration(
            class_id="arcgrav.test:task_policy_failure",
            version="1.0.0",
            meaning="Provider-free task-layer extension for conformance testing.",
            producing_authority="arcgrav.test:registered-scorer",
            applicable_evidence_scope="completed task observation",
            authority_layer="task",
            anchor_class="task_malformed",
            position="before",
        )
        resolution = resolve_failures(
            (
                _candidate(
                    "extension-task",
                    extension.class_id,
                    "task",
                    class_version=extension.version,
                ),
                _candidate("task", "task_incorrect", "task"),
                _candidate("execution", "execution_failed", "execution"),
            ),
            extension_classes=(extension,),
        )

        self.assertEqual("execution", resolution.primary.candidate_id)
        self.assertEqual(
            {"extension-task", "task"},
            {candidate.candidate_id for candidate in resolution.suppressed},
        )

    def test_secret_bearing_retained_diagnostics_are_rejected_before_resolution(self) -> None:
        with self.assertRaises(ValueError):
            _candidate(
                "secret-details",
                "evidence_invalid",
                "evidence",
                redacted_details={
                    "context": {
                        "credential_value": "must-not-enter-retained-evidence"
                    }
                },
            )

        with self.assertRaises(ValueError):
            FailureCandidate(
                candidate_id="secret-extension",
                failure_class="evidence_invalid",
                authority_layer="evidence",
                affected_evidence_id="evidence-1",
                source_id="source-1",
                diagnostic_id="diagnostic-1",
                extensions={
                    "arcgrav.test:credential_value": "must-not-enter-retained-evidence"
                },
            )


class ValidationCoreDependencyRegressionTests(unittest.TestCase):
    def test_shared_schema_and_extension_identity_syntax_accepts_canonical_values(self) -> None:
        schema = SchemaIdentity(
            "arcgrav.shared.schema.validation-result",
            "1.0.0",
        )
        source = SourceArtifact(
            artifact_id="validation-core-regression",
            sha256=sha256_bytes(b"validation-core-regression"),
        )
        result = ValidationResult.create(
            validation_id="validation-core-regression",
            schema=schema,
            source_artifact=source,
            extensions={"arcgrav.test:note": "provider-free"},
        )

        self.assertEqual(
            {
                "schema_id": "arcgrav.shared.schema.validation-result",
                "schema_version": "1.0.0",
            },
            schema.to_dict(),
        )
        self.assertEqual(
            {"arcgrav.test:note": "provider-free"},
            result.to_dict()["extensions"],
        )

        with self.assertRaises(ValueError):
            SchemaIdentity("arcgravXsharedXschemaXvalidation-result", "1.0.0")
        with self.assertRaises(ValueError):
            SchemaIdentity("arcgrav.shared.schema.validation-result", "1x0x0")
        with self.assertRaises(ValueError):
            ValidationResult.create(
                validation_id="validation-core-invalid-extension",
                schema=schema,
                source_artifact=source,
                extensions={"arcgrav.test:bad key": "must-reject-whitespace"},
            )


if __name__ == "__main__":
    unittest.main()
