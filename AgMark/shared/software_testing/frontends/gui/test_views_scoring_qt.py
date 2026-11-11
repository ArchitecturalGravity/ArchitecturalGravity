"""Regression coverage for the fixed-column Scoring workspace."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.views.results import ResultRowProjection, ResultsProjection
from AgMark.gui.views.scoring import (
    PYSIDE6_AVAILABLE,
    SCORING_COLUMNS,
    ScoringView,
    scoring_columns,
    scoring_rows,
)


EXPECTED_LABELS = (
    "Treatment",
    "Accuracy",
    "Input Tokens",
    "Uncached Input",
    "Reasoning Output Tokens",
    "Output Tokens",
    "Total Tokens",
    "Cache Read Fraction",
    "Average Inference Duration",
    "Average TTFT (Proxy)",
    "Average TBT (Proxy)",
    "Average Direct TTFT",
    "Average Direct TBT",
    "Tool Calls",
    "Distinct Tool Calls",
    "Failed Tool Calls",
)


EXPECTED_UNSCORED_LABELS = tuple(label for label in EXPECTED_LABELS if label != "Accuracy")


def _projection(score=0.75, *, unscored=False):
    return ResultsProjection(
        run_id="scoring-test-run",
        unscored=unscored,
        rows=(ResultRowProjection(
            treatment="treatment-a",
            score=score,
            evidence="available",
            status="Scored",
            status_icon="✓",
        ),),
    )


def _ranked_projection(scores, metric_values, *, states=None, unscored=False):
    states = states or {}
    rows = []
    for index, score in enumerate(scores):
        measurements = {
            key: {
                "value": values[index],
                "availability": states.get(key, ("available",) * len(scores))[index],
                "unit": "1",
            }
            for key, values in metric_values.items()
        }
        rows.append(ResultRowProjection(
            treatment=f"treatment-{index}",
            score=score,
            evidence="Retained evidence",
            status="Scored",
            status_icon="✓",
            measurements=measurements,
        ))
    return ResultsProjection("ranked-scoring-run", tuple(rows), unscored=unscored)


class ScoringTableProjectionTests(unittest.TestCase):
    def test_exact_column_order_and_retained_result_cells(self):
        self.assertEqual(tuple(column.label for column in SCORING_COLUMNS), EXPECTED_LABELS)
        self.assertEqual(len({column.key for column in SCORING_COLUMNS}), 16)
        projected = scoring_rows(_projection())
        self.assertEqual(len(projected), 1)
        self.assertEqual(tuple(projected[0].cells), tuple(column.key for column in SCORING_COLUMNS))
        self.assertEqual(projected[0].cells["treatment"].text, "treatment-a")
        self.assertEqual(projected[0].cells["score"].text, "🥇 75%")
        self.assertEqual(projected[0].cells["input_tokens"].text, "Unavailable")

    def test_execution_only_run_omits_accuracy_column(self):
        projection = _projection(None, unscored=True)
        columns = scoring_columns(projection)
        self.assertEqual(tuple(column.label for column in columns), EXPECTED_UNSCORED_LABELS)
        row = scoring_rows(projection)[0]
        self.assertEqual(tuple(row.cells), tuple(column.key for column in columns))
        self.assertNotIn("score", row.cells)
        self.assertEqual(row.cells["treatment"].text, "treatment-a")


    def test_all_measurement_directions_and_only_three_places(self):
        lower = tuple(column.key for column in SCORING_COLUMNS
                      if column.key not in {"treatment", "score", "cache_read_fraction"})
        metrics = {key: (400, 100, 200, 300) for key in lower}
        metrics["cache_read_fraction"] = (0.1, 0.4, 0.3, 0.2)
        projection = _ranked_projection((0.9, 0.1, 0.8, 0.7), metrics)
        rows = scoring_rows(projection)
        self.assertEqual(
            [row.cells["score"].text.split(" ")[0] for row in rows],
            ["🥇", "10%", "🥈", "🥉"],
        )
        for key in (*lower, "cache_read_fraction"):
            self.assertFalse(rows[0].cells[key].text.startswith(("🥇", "🥈", "🥉")))
            self.assertEqual(
                [rows[i].cells[key].text.split(" ")[0] for i in (1, 2, 3)],
                ["🥇", "🥈", "🥉"],
            )
        self.assertEqual(
            projection._presentation["rows"][1].cells["input_tokens"].text,
            "100",
        )
        self.assertEqual(rows[1].cells["treatment"].text, "treatment-1")

    def test_output_tokens_fewer_is_better_independently_of_reasoning_tokens(self):
        projection = _ranked_projection(
            (0.4, 0.5, 0.6),
            {"output_tokens": (240, 80, 160), "reasoning_tokens": (20, 40, 30)},
        )
        rows = scoring_rows(projection)
        self.assertEqual(
            [row.cells["output_tokens"].text for row in rows],
            ["🥉 240", "🥇 80", "🥈 160"],
        )
        self.assertEqual(
            [row.cells["reasoning_tokens"].text for row in rows],
            ["🥇 20", "🥉 40", "🥈 30"],
        )

    def test_ties_share_a_medal_without_skipping_the_next_medal(self):
        projection = _ranked_projection(
            (0.9, 0.9, 0.8, 0.7),
            {"input_tokens": (1, 1, 2, 3)},
        )
        rows = scoring_rows(projection)
        self.assertEqual(
            [row.cells["score"].text for row in rows],
            ["🥇 (tie) 90%", "🥇 (tie) 90%", "🥈 80%", "🥉 70%"],
        )
        self.assertEqual(
            [row.cells["input_tokens"].text for row in rows],
            ["🥇 (tie) 1", "🥇 (tie) 1", "🥈 2", "🥉 3"],
        )

    def test_three_way_gold_tie_still_awards_silver_and_bronze(self):
        projection = _ranked_projection(
            (0.9, 0.9, 0.9, 0.8, 0.7),
            {"input_tokens": (10, 10, 10, 20, 30)},
        )
        rows = scoring_rows(projection)
        self.assertEqual(
            [row.cells["score"].text for row in rows],
            ["🥇 (tie) 90%"] * 3 + ["🥈 80%", "🥉 70%"],
        )
        self.assertEqual(
            [row.cells["input_tokens"].text for row in rows],
            ["🥇 (tie) 10"] * 3 + ["🥈 20", "🥉 30"],
        )

    def test_second_and_third_place_ties_are_labeled(self):
        for scores, expected in (
            ((0.9, 0.8, 0.8, 0.7),
             ("🥇 90%", "🥈 (tie) 80%", "🥈 (tie) 80%", "🥉 70%")),
            ((0.9, 0.8, 0.7, 0.7, 0.6),
             ("🥇 90%", "🥈 80%", "🥉 (tie) 70%", "🥉 (tie) 70%", "60%")),
        ):
            with self.subTest(scores=scores):
                rows = scoring_rows(_ranked_projection(scores, {}))
                self.assertEqual(tuple(row.cells["score"].text for row in rows), expected)

    def test_unavailable_noncomparable_and_non_numeric_values_not_ranked(self):
        projection = _ranked_projection(
            (None, None, None, None, None),
            {"input_tokens": (7, 2, 1, "0", 4)},
            states={"input_tokens": (
                "available", "partial", "non_comparable", "available", "unsupported"
            )},
        )
        rows = scoring_rows(projection)
        self.assertTrue(rows[1].cells["input_tokens"].text.startswith("🥇 "))
        self.assertTrue(rows[0].cells["input_tokens"].text.startswith("🥈 "))
        for index in (2, 3, 4):
            self.assertFalse(rows[index].cells["input_tokens"].text.startswith(("🥇", "🥈", "🥉")))
        self.assertTrue(all(row.cells["score"].text == "—" for row in rows))

    def test_execution_only_skips_accuracy_but_ranks_available_usage(self):
        projection = _ranked_projection(
            (0.9, 0.2), {"total_tokens": (500, 200)}, unscored=True
        )
        rows = scoring_rows(projection)
        self.assertTrue(all("score" not in row.cells for row in rows))
        self.assertTrue(rows[0].cells["total_tokens"].text.startswith("🥈 "))
        self.assertTrue(rows[1].cells["total_tokens"].text.startswith("🥇 "))


if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ScoringViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._application = QApplication.instance() or QApplication([])

    def test_table_renders_and_updates_without_changing_column_order(self):
        view = ScoringView(_projection())
        self.addCleanup(view.deleteLater)
        self.assertEqual(view.accessibleName(), "Scoring workspace")
        self.assertEqual(
            tuple(column.label for column in view.table.columns), EXPECTED_LABELS
        )
        self.assertEqual(len(view.table.rows), 1)
        self.assertEqual(view.table.rows[0].cells["score"].text, "🥇 75%")

        view.set_projection(_projection(None, unscored=True))
        self.assertEqual(
            tuple(column.label for column in view.table.columns), EXPECTED_UNSCORED_LABELS
        )
        self.assertNotIn("score", view.table.rows[0].cells)

        view.set_projection(_projection(0.5))
        self.assertEqual(tuple(column.label for column in view.table.columns), EXPECTED_LABELS)
        self.assertEqual(view.table.rows[0].cells["score"].text, "🥇 50%")
        self.assertEqual(view.run_id, "scoring-test-run")


if __name__ == "__main__":
    unittest.main()
