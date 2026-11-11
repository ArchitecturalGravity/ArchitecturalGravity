"""Provider-free conformance tests for registered statistical aggregation evidence."""

from __future__ import annotations

import unittest

from AgMark.shared.evaluation.aggregation import (
    AggregationInput,
    AggregationRule,
    CategoryDefinition,
    StateDisposition,
    StatisticalSummaryMethod,
    aggregate_cases,
    aggregate_category,
    aggregate_repetitions,
    summarize_statistical,
)


_BOUNDARY = "sha256:" + ("2" * 64)
_CASE_RULE = AggregationRule(
    rule_id="arcgrav.aggregation.statistical-case-test",
    rule_version="1.0.0",
    reducer="rate",
    missing_action="unavailable",
    state_dispositions=(
        StateDisposition("failed", "unavailable"),
        StateDisposition("excluded", "exclude"),
    ),
    implementation="provider-free-test",
    software_version="1.0.0",
)
_TREATMENT_RULE = AggregationRule(
    rule_id="arcgrav.aggregation.statistical-treatment-test",
    rule_version="1.0.0",
    reducer="rate",
    missing_action="unavailable",
    state_dispositions=(
        StateDisposition("failed", "unavailable"),
        StateDisposition("excluded", "exclude"),
    ),
    implementation="provider-free-test",
    software_version="1.0.0",
)
_METHOD = StatisticalSummaryMethod(
    method_id="arcgrav.statistics.primary-rate",
    method_version="1.0.0",
    method="registered_case_rate",
    confidence_level=0.95,
    resampling_procedure="case-identity bootstrap",
    correction_method="holm",
    missing_disposition="unavailable",
    excluded_disposition="exclude",
    failure_disposition="unavailable",
    implementation="provider-free-test",
    software_version="1.0.0",
    preregistered=True,
)


def _case(case_id: str, value: float):
    retained = AggregationInput(
        evidence_id=f"score:{case_id}",
        case_id=case_id,
        treatment_id="treatment-a",
        repetition_id="rep-1",
        metric_id="metric-a",
        metric_version="1.0.0",
        metric_registration_id="metric-registration-a",
        metric_registration_version="1.0.0",
        execution_boundary_fingerprint=_BOUNDARY,
        comparison_context_id="comparison-a",
        observation_scope="case",
        availability="scored",
        value=value,
    )
    return aggregate_repetitions(
        (retained,),
        planned_repetition_ids=("rep-1",),
        rule=_CASE_RULE,
    )


class StatisticalAggregationConformanceTests(unittest.TestCase):
    def test_preregistered_summary_retains_method_and_rate_authority(self) -> None:
        case_a = _case("case-a", 1.0)
        case_b = _case("case-b", 0.0)
        aggregate = aggregate_cases(
            (case_b, case_a),
            planned_case_ids=("case-a", "case-b"),
            rule=_TREATMENT_RULE,
        )

        first = summarize_statistical(aggregate, method=_METHOD)
        second = summarize_statistical(
            aggregate_cases(
                (case_a, case_b),
                planned_case_ids=("case-a", "case-b"),
                rule=_TREATMENT_RULE,
            ),
            method=_METHOD,
        )

        self.assertEqual(first.analysis_status, "preregistered")
        self.assertEqual(first.aggregate.numerator, 1)
        self.assertEqual(first.aggregate.denominator, 2)
        self.assertEqual(first.aggregate.retained_missing_count, 0)
        self.assertEqual(first.aggregate.retained_exclusion_count, 0)
        self.assertEqual(first.aggregate.retained_failure_count, 0)
        self.assertEqual(first.method.confidence_level, 0.95)
        self.assertEqual(first.method.resampling_procedure, "case-identity bootstrap")
        self.assertEqual(first.method.correction_method, "holm")
        self.assertTrue(first.method.method_sha256.startswith("sha256:"))
        self.assertEqual(first.computation_sha256, second.computation_sha256)

    def test_post_hoc_category_forces_exploratory_statistical_status(self) -> None:
        definition = CategoryDefinition(
            definition_id="arcgrav.category.post-hoc-statistical",
            definition_version="1.0.0",
            category_kind="difficulty",
            category_value="observed-after-execution",
            case_ids=("case-a", "case-b"),
            preregistered=False,
        )
        category = aggregate_category(
            (_case("case-a", 1.0), _case("case-b", 0.0)),
            definition=definition,
            rule=_TREATMENT_RULE,
        )

        evidence = summarize_statistical(
            category.aggregate,
            method=_METHOD,
            category_definition=definition,
        )

        self.assertEqual(evidence.analysis_status, "exploratory")
        self.assertEqual(
            evidence.to_dict()["category_definition"]["definition_sha256"],
            definition.definition_sha256,
        )

    def test_statistical_method_must_match_registered_source_dispositions(self) -> None:
        aggregate = aggregate_cases(
            (_case("case-a", 1.0),),
            planned_case_ids=("case-a", "case-missing"),
            rule=_TREATMENT_RULE,
        )
        mismatched = StatisticalSummaryMethod(
            method_id="arcgrav.statistics.mismatch",
            method_version="1.0.0",
            method="registered_case_rate",
            confidence_level=None,
            resampling_procedure=None,
            correction_method=None,
            missing_disposition="exclude",
            excluded_disposition="exclude",
            failure_disposition="unavailable",
            implementation="provider-free-test",
            software_version="1.0.0",
            preregistered=True,
        )

        with self.assertRaisesRegex(ValueError, "missing disposition"):
            summarize_statistical(aggregate, method=mismatched)


if __name__ == "__main__":
    unittest.main()
