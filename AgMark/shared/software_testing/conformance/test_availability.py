"""Provider-free conformance tests for shared availability semantics."""

from __future__ import annotations

import unittest

from AgMark.shared.evaluation.availability import (
    AvailabilityRecord,
    MetricAvailabilityEffect,
    bind_metric_effect,
    preserve_availability,
)


class AvailabilityConformanceTests(unittest.TestCase):
    def test_non_success_states_preserve_reason_and_source_identity(self) -> None:
        for state in (
            "unavailable",
            "invalid",
            "missing",
            "not_applicable",
            "non_comparable",
            "failed",
            "completed_non_scorable",
        ):
            with self.subTest(state=state):
                record = AvailabilityRecord(
                    affected_kind="measurement",
                    affected="metric.primary",
                    state=state,
                    reason=f"explicit {state} reason",
                    source_identity=f"source:{state}",
                )
                serialized = record.to_dict()

                self.assertEqual(state, serialized["state"])
                self.assertEqual(
                    f"explicit {state} reason",
                    serialized["reason"],
                )
                self.assertEqual(
                    f"source:{state}",
                    serialized["source_identity"],
                )
                self.assertNotIn("value", serialized)
                self.assertNotIn("numeric_value", serialized)
                self.assertNotIn("evidence", serialized)

    def test_excluded_state_requires_and_retains_exclusion_authority(self) -> None:
        with self.assertRaises(ValueError):
            AvailabilityRecord(
                affected_kind="evidence_role",
                affected="candidate_output",
                state="excluded",
                reason="registered metric excludes this evidence",
                source_identity="evidence:candidate-output",
            )

        record = AvailabilityRecord(
            affected_kind="evidence_role",
            affected="candidate_output",
            state="excluded",
            reason="registered metric excludes this evidence",
            source_identity="evidence:candidate-output",
            exclusion_authority="metric.primary@1.0.0:exclude-refusal",
        )
        serialized = record.to_dict()

        self.assertEqual("excluded", serialized["state"])
        self.assertEqual(
            "metric.primary@1.0.0:exclude-refusal",
            serialized["exclusion_authority"],
        )
        self.assertEqual(
            "evidence:candidate-output",
            serialized["source_identity"],
        )

    def test_preserve_availability_projects_without_state_or_provenance_coercion(
        self,
    ) -> None:
        source = AvailabilityRecord(
            affected_kind="evidence_role",
            affected="runner_output",
            state="missing",
            reason="planned evidence was not produced",
            source_identity="observation:case-7:treatment-a:rep-2",
        )

        projected = preserve_availability(
            source,
            affected_kind="measurement",
            affected="metric.primary",
        )

        self.assertEqual("measurement", projected.affected_kind)
        self.assertEqual("metric.primary", projected.affected)
        self.assertEqual(source.state, projected.state)
        self.assertEqual(source.reason, projected.reason)
        self.assertEqual(source.source_identity, projected.source_identity)
        self.assertEqual((), projected.downstream_effects)

    def test_metric_effect_binding_retains_state_and_serializes_registration_identity(
        self,
    ) -> None:
        source = AvailabilityRecord(
            affected_kind="measurement",
            affected="metric.primary",
            state="non_comparable",
            reason="paired observation scope is incompatible",
            source_identity="pair:case-7",
        )
        effect = MetricAvailabilityEffect(
            metric_registration_id="metric.primary",
            metric_registration_version="1.0.0",
            rule_id="non-comparable-withhold",
            effect="withhold relative comparison value",
        )

        bound = bind_metric_effect(source, effect)
        serialized = bound.to_dict()

        self.assertEqual(source.state, bound.state)
        self.assertEqual(source.reason, bound.reason)
        self.assertEqual(source.source_identity, bound.source_identity)
        self.assertEqual((effect,), bound.downstream_effects)
        self.assertEqual(
            [
                {
                    "metric_registration_id": "metric.primary",
                    "metric_registration_version": "1.0.0",
                    "rule_id": "non-comparable-withhold",
                    "effect": "withhold relative comparison value",
                }
            ],
            serialized["downstream_effects"],
        )
        self.assertEqual("non_comparable", serialized["state"])
        self.assertNotIn("value", serialized)

    def test_availability_validation_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            AvailabilityRecord(
                affected_kind="measurement",
                affected="metric.primary",
                state="unsupported_state",
                reason="must not be accepted",
                source_identity="source:invalid-state",
            )

        with self.assertRaises(ValueError):
            MetricAvailabilityEffect(
                metric_registration_id="metric.primary",
                metric_registration_version="1",
                rule_id="bad-version",
                effect="must not be accepted",
            )


if __name__ == "__main__":
    unittest.main()
