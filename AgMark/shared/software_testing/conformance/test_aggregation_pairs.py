"""Provider-free conformance tests for pairwise aggregation evidence."""

from __future__ import annotations

from dataclasses import replace
import unittest

from AgMark.shared.evaluation.aggregation import (
    AggregationError,
    AggregationInput,
    AggregationRule,
    PairwiseProtocol,
    StateDisposition,
    aggregate_pairs,
    aggregate_repetitions,
)


_BOUNDARY = "sha256:" + ("3" * 64)
_CASE_RULE = AggregationRule(
    rule_id="arcgrav.aggregation.pairwise-case-test",
    rule_version="1.0.0",
    reducer="mean",
    missing_action="unavailable",
    state_dispositions=(
        StateDisposition("failed", "unavailable"),
        StateDisposition("excluded", "exclude"),
        StateDisposition("non_comparable", "non_comparable"),
    ),
    implementation="provider-free-test",
    software_version="1.0.0",
)
_PROTOCOL = PairwiseProtocol(
    protocol_id="arcgrav.pairwise.conformance",
    protocol_version="1.0.0",
    reference_treatment_id="reference",
    comparison_treatment_id="comparison",
    difference_direction="comparison_minus_reference",
    comparison_win_when="positive",
    tie_tolerance=0.1,
    missing_pair_disposition="unavailable",
    failure_pair_disposition="exclude",
    required_observation_scope="case",
    implementation="provider-free-test",
    software_version="1.0.0",
)


def _case(
    treatment_id: str,
    case_id: str,
    value: float | None,
    *,
    availability: str = "scored",
    failure_class: str | None = None,
    comparison_context_id: str = "comparison-a",
    observation_scope: str = "case",
):
    retained = AggregationInput(
        evidence_id=f"score:{treatment_id}:{case_id}",
        case_id=case_id,
        treatment_id=treatment_id,
        repetition_id="rep-1",
        metric_id="metric-a",
        metric_version="1.0.0",
        metric_registration_id="metric-registration-a",
        metric_registration_version="1.0.0",
        execution_boundary_fingerprint=_BOUNDARY,
        comparison_context_id=comparison_context_id,
        observation_scope=observation_scope,
        availability=availability,
        value=value,
        failure_class=failure_class,
    )
    return aggregate_repetitions(
        (retained,),
        planned_repetition_ids=("rep-1",),
        rule=_CASE_RULE,
    )


class PairwiseAggregationConformanceTests(unittest.TestCase):
    def test_complete_pairs_preserve_direction_outcomes_and_protocol_identity(self) -> None:
        reference = (
            _case("reference", "case-a", 1.0),
            _case("reference", "case-b", 4.0),
            _case("reference", "case-c", 5.0),
        )
        comparison = (
            _case("comparison", "case-a", 3.0),
            _case("comparison", "case-b", 2.0),
            _case("comparison", "case-c", 5.05),
        )

        first = aggregate_pairs(
            reference,
            comparison,
            planned_case_ids=("case-c", "case-a", "case-b"),
            protocol=_PROTOCOL,
        )
        second = aggregate_pairs(
            tuple(reversed(reference)),
            tuple(reversed(comparison)),
            planned_case_ids=("case-c", "case-a", "case-b"),
            protocol=_PROTOCOL,
        )

        self.assertEqual(
            tuple(pair.case_id for pair in first.pairs),
            ("case-c", "case-a", "case-b"),
        )
        self.assertEqual(
            tuple(pair.outcome for pair in first.pairs),
            ("tie", "comparison_win", "reference_win"),
        )
        self.assertEqual(first.comparable_pair_count, 3)
        self.assertEqual(first.comparison_win_count, 1)
        self.assertEqual(first.reference_win_count, 1)
        self.assertEqual(first.tie_count, 1)
        self.assertAlmostEqual(first.mean_difference, (0.05 + 2.0 - 2.0) / 3.0)
        self.assertAlmostEqual(first.comparison_win_rate, 1.0 / 3.0)
        self.assertAlmostEqual(first.reference_win_rate, 1.0 / 3.0)
        self.assertAlmostEqual(first.tie_rate, 1.0 / 3.0)
        self.assertEqual(first.availability, "available")
        self.assertEqual(first.computation_sha256, second.computation_sha256)

        protocol = first.to_dict()["protocol"]
        self.assertEqual(protocol["id"], _PROTOCOL.protocol_id)
        self.assertEqual(protocol["version"], _PROTOCOL.protocol_version)
        self.assertEqual(protocol["difference_direction"], "comparison_minus_reference")
        self.assertEqual(protocol["comparison_win_when"], "positive")
        self.assertEqual(protocol["missing_pair_disposition"], "unavailable")
        self.assertEqual(protocol["failure_pair_disposition"], "exclude")
        self.assertEqual(protocol["implementation"], "provider-free-test")
        self.assertEqual(protocol["software_version"], "1.0.0")

    def test_missing_planned_pair_is_unavailable_and_withholds_relative_values(self) -> None:
        evidence = aggregate_pairs(
            (
                _case("reference", "case-a", 1.0),
                _case("reference", "case-b", 2.0),
            ),
            (_case("comparison", "case-a", 2.0),),
            planned_case_ids=("case-a", "case-b"),
            protocol=_PROTOCOL,
        )

        missing = evidence.pairs[1]
        self.assertEqual(missing.case_id, "case-b")
        self.assertEqual(missing.availability, "unavailable")
        self.assertIsNone(missing.comparison_evidence_id)
        self.assertIsNone(missing.difference)
        self.assertIsNone(missing.outcome)
        self.assertEqual(evidence.missing_pair_count, 1)
        self.assertEqual(evidence.unavailable_pair_count, 1)
        self.assertEqual(evidence.availability, "unavailable")
        self.assertIsNone(evidence.mean_difference)
        self.assertIsNone(evidence.comparison_win_rate)
        self.assertIsNone(evidence.reference_win_rate)
        self.assertIsNone(evidence.tie_rate)

    def test_failed_pair_uses_registered_disposition_and_withholds_relative_values(self) -> None:
        evidence = aggregate_pairs(
            (
                _case("reference", "case-a", 1.0),
                _case("reference", "case-b", 2.0),
            ),
            (
                _case("comparison", "case-a", 2.0),
                _case(
                    "comparison",
                    "case-b",
                    None,
                    availability="failed",
                    failure_class="execution.timeout",
                ),
            ),
            planned_case_ids=("case-a", "case-b"),
            protocol=_PROTOCOL,
        )

        failed = evidence.pairs[1]
        self.assertEqual(failed.availability, "excluded")
        self.assertEqual(failed.failure_classes, ("execution.timeout",))
        self.assertEqual(evidence.failed_pair_count, 1)
        self.assertEqual(evidence.excluded_pair_count, 1)
        self.assertEqual(evidence.availability, "unavailable")
        self.assertIsNone(evidence.mean_difference)
        self.assertIsNone(evidence.comparison_win_rate)

    def test_non_comparable_pair_withholds_relative_values(self) -> None:
        evidence = aggregate_pairs(
            (_case("reference", "case-a", 1.0),),
            (
                _case(
                    "comparison",
                    "case-a",
                    None,
                    availability="non_comparable",
                ),
            ),
            planned_case_ids=("case-a",),
            protocol=replace(_PROTOCOL, failure_pair_disposition="non_comparable"),
        )

        self.assertEqual(evidence.pairs[0].availability, "non_comparable")
        self.assertEqual(evidence.non_comparable_pair_count, 1)
        self.assertEqual(evidence.availability, "non_comparable")
        self.assertIsNone(evidence.mean_difference)
        self.assertIsNone(evidence.comparison_win_rate)

    def test_pair_compatibility_rejects_context_and_scope_mismatch(self) -> None:
        reference = (_case("reference", "case-a", 1.0),)

        with self.assertRaisesRegex(AggregationError, "comparison_context_id"):
            aggregate_pairs(
                reference,
                (
                    _case(
                        "comparison",
                        "case-a",
                        2.0,
                        comparison_context_id="comparison-b",
                    ),
                ),
                planned_case_ids=("case-a",),
                protocol=_PROTOCOL,
            )

        with self.assertRaisesRegex(AggregationError, "observation scope"):
            aggregate_pairs(
                reference,
                (
                    _case(
                        "comparison",
                        "case-a",
                        2.0,
                        observation_scope="request",
                    ),
                ),
                planned_case_ids=("case-a",),
                protocol=_PROTOCOL,
            )


if __name__ == "__main__":
    unittest.main()
