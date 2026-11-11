"""Provider-free conformance tests for registered category aggregation."""

from __future__ import annotations

import unittest

from AgMark.shared.evaluation.aggregation import (
    AggregationInput,
    AggregationRule,
    CategoryDefinition,
    StateDisposition,
    aggregate_category,
    aggregate_repetitions,
)


_BOUNDARY = "sha256:" + ("1" * 64)
_CASE_RULE = AggregationRule(
    rule_id="arcgrav.aggregation.case-test",
    rule_version="1.0.0",
    reducer="mean",
    missing_action="unavailable",
    state_dispositions=(
        StateDisposition("failed", "unavailable"),
        StateDisposition("excluded", "exclude"),
    ),
    implementation="provider-free-test",
    software_version="1.0.0",
)
_CATEGORY_RULE = AggregationRule(
    rule_id="arcgrav.aggregation.category-test",
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


class CategoryAggregationConformanceTests(unittest.TestCase):
    def test_preregistered_category_retains_definition_and_planned_rate(self) -> None:
        case_a = _case("case-a", 1.0)
        case_b = _case("case-b", 0.0)
        definition = CategoryDefinition(
            definition_id="arcgrav.category.behavior-family",
            definition_version="1.0.0",
            category_kind="behavior_family",
            category_value="lookup",
            case_ids=("case-b", "case-a"),
            preregistered=True,
        )

        first = aggregate_category(
            (case_a, case_b),
            definition=definition,
            rule=_CATEGORY_RULE,
        )
        second = aggregate_category(
            (case_b, case_a),
            definition=definition,
            rule=_CATEGORY_RULE,
        )

        self.assertEqual(definition.analysis_status, "preregistered")
        self.assertTrue(definition.definition_sha256.startswith("sha256:"))
        self.assertEqual(first.aggregate.planned_unit_ids, ("case-b", "case-a"))
        self.assertEqual(first.aggregate.case_ids, ("case-b", "case-a"))
        self.assertEqual(first.aggregate.value, 0.5)
        self.assertEqual(first.aggregate.numerator, 1)
        self.assertEqual(first.aggregate.denominator, 2)
        self.assertEqual(first.computation_sha256, second.computation_sha256)

    def test_post_hoc_category_is_exploratory_and_preserves_missing_case(self) -> None:
        definition = CategoryDefinition(
            definition_id="arcgrav.category.post-hoc",
            definition_version="1.0.0",
            category_kind="input_feature",
            category_value="observed-after-execution",
            case_ids=("case-a", "case-missing"),
            preregistered=False,
        )
        evidence = aggregate_category(
            (_case("case-a", 1.0), _case("case-outside", 0.0)),
            definition=definition,
            rule=_CATEGORY_RULE,
        )

        self.assertEqual(definition.analysis_status, "exploratory")
        self.assertEqual(
            evidence.to_dict()["category_definition"]["analysis_status"],
            "exploratory",
        )
        self.assertEqual(evidence.aggregate.planned_count, 2)
        self.assertEqual(evidence.aggregate.missing_count, 1)
        self.assertEqual(evidence.aggregate.availability, "unavailable")
        self.assertIsNone(evidence.aggregate.value)

    def test_definition_identity_binds_membership_and_status(self) -> None:
        base = CategoryDefinition(
            definition_id="arcgrav.category.identity",
            definition_version="1.0.0",
            category_kind="difficulty",
            category_value="hard",
            case_ids=("case-a",),
            preregistered=True,
        )
        changed_membership = CategoryDefinition(
            definition_id="arcgrav.category.identity",
            definition_version="1.0.0",
            category_kind="difficulty",
            category_value="hard",
            case_ids=("case-a", "case-b"),
            preregistered=True,
        )
        exploratory = CategoryDefinition(
            definition_id="arcgrav.category.identity",
            definition_version="1.0.0",
            category_kind="difficulty",
            category_value="hard",
            case_ids=("case-a",),
            preregistered=False,
        )

        self.assertNotEqual(base.definition_sha256, changed_membership.definition_sha256)
        self.assertNotEqual(base.definition_sha256, exploratory.definition_sha256)


if __name__ == "__main__":
    unittest.main()
