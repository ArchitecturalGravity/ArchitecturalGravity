"""Registered fractional summaries preserve case weight and detail provenance."""

import copy
import unittest

from AgMark.shared.reporting.results import (
    AGGREGATION_EXTENSION,
    SCORE_DETAILS_EXTENSION,
    registered_rate_summary,
    registered_score_details,
    score_details_text,
)


def _registration(*, macro=True):
    return {
        "registration_id": "fixture.metric",
        "registration_version": "1.0.0",
        "metric_id": "fixture.accuracy",
        "unit": "proportion",
        "numerator_denominator": {"uses_rate": True},
        "state_treatment": [
            {"state": "failed", "disposition": "zero"},
            {"state": "missing", "disposition": "zero"},
            {"state": "excluded", "disposition": "exclude"},
            {"state": "unavailable", "disposition": "unavailable"},
            {"state": "non_comparable", "disposition": "non_comparable"},
        ],
        "extensions": {
            **({AGGREGATION_EXTENSION: {"repetition_reducer": "mean", "case_reducer": "mean"}} if macro else {}),
            SCORE_DETAILS_EXTENSION: {"extension_keys": ["fixture:comparison"]},
        },
    }


def _score(case, value, repetition=1, *, availability="scored"):
    return {
        "score_artifact_id": f"score-{case}-{repetition}",
        "metric_registration": {"id": "fixture.metric", "version": "1.0.0"},
        "case_id": case,
        "treatment_id": "treatment",
        "repetition_ids": [repetition],
        "availability": availability,
        **({"value": value} if availability == "scored" else {}),
        "unit": "proportion",
        "companion_values": [],
        "diagnostics": [],
        "extensions": {},
    }


class RegisteredScoreReportingTests(unittest.TestCase):
    def test_unequal_repetitions_do_not_change_case_weight(self):
        scores = [_score("a", .25, 1), _score("a", .75, 2), _score("a", .5, 3), _score("b", 1, 1)]
        before = copy.deepcopy(scores)
        summary = registered_rate_summary(scores, _registration())
        self.assertEqual(.75, summary["value"])
        self.assertEqual(1.5, summary["numerator"])
        self.assertEqual(2, summary["denominator"])
        self.assertEqual("cases", summary["denominator_unit"])
        self.assertEqual(4, summary["evaluated_observations"])
        self.assertEqual([.5, 1], [case["value"] for case in summary["case_summaries"]])
        self.assertEqual(summary, registered_rate_summary(reversed(scores), _registration()))
        self.assertEqual(before, scores)

    def test_legacy_registration_keeps_observation_weight(self):
        scores = [_score("a", .25, 1), _score("a", .75, 2), _score("a", .5, 3), _score("b", 1, 1)]
        summary = registered_rate_summary(scores, _registration(macro=False))
        self.assertEqual(.625, summary["value"])
        self.assertEqual(4, summary["denominator"])
        self.assertNotIn("denominator_unit", summary)

    def test_registered_zero_exclusion_and_unavailability_are_distinct(self):
        summary = registered_rate_summary([
            _score("a", 1), _score("a", None, 2, availability="missing"),
            _score("b", None, availability="excluded"),
        ], _registration())
        self.assertEqual(.5, summary["value"])
        self.assertEqual(1, summary["denominator"])
        self.assertEqual(2, summary["evaluated_observations"])
        for state in ("unavailable", "non_comparable", "invalid"):
            with self.subTest(state=state):
                blocked = registered_rate_summary([
                    _score("a", 1), _score("b", None, availability=state),
                ], _registration())
                self.assertIsNone(blocked["value"])
                self.assertIsNone(blocked["numerator"])
                self.assertIsNone(blocked["denominator"])
                self.assertEqual(1, blocked["availability_counts"][state])

    def test_registered_mean_requires_case_identity_and_known_policy(self):
        score = _score("a", .5)
        del score["case_id"]
        with self.assertRaisesRegex(ValueError, "case identity"):
            registered_rate_summary([score], _registration())
        registration = _registration()
        registration["extensions"][AGGREGATION_EXTENSION]["case_reducer"] = "sum"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            registered_rate_summary([_score("a", .5)], registration)

    def test_detail_projection_retains_counts_diagnostics_and_selected_payload_only(self):
        score = _score("a", 47 / 49)
        score["companion_values"] = [
            {"name": "correct_units", "value": 47},
            {"name": "expected_units", "value": 48},
            {"name": "unexpected_units", "value": 1},
        ]
        score["diagnostics"] = ["FIXTURE_MISMATCH"]
        score["extensions"] = {
            "fixture:comparison": {"path": "/records/0/value", "expected": 8, "observed": 9},
            "fixture:unselected": {"not_selected": True},
        }
        before = copy.deepcopy(score)
        details = registered_score_details([score], _registration())
        text = score_details_text(details)
        self.assertIn("correct units: 47", text)
        self.assertIn("expected units: 48", text)
        self.assertIn("unexpected units: 1", text)
        self.assertIn("FIXTURE_MISMATCH", text)
        self.assertIn("/records/0/value", text)
        self.assertNotIn("unselected", text)
        details[0]["extensions"]["fixture:comparison"]["observed"] = 10
        self.assertEqual(before, score)
        registration = _registration()
        registration["extensions"].pop(SCORE_DETAILS_EXTENSION)
        self.assertEqual([], registered_score_details([score], registration))


if __name__ == "__main__":
    unittest.main()
