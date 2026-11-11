"""Conformance tests for GUI spacing and density semantics."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.metrics import (
    DEFAULT_LAYOUT_METRICS,
    REQUIRED_LAYOUT_METRICS,
    LayoutMetrics,
    metric,
)


class DefaultLayoutMetricsTests(unittest.TestCase):
    def test_reference_metrics_are_complete_and_immutable(self) -> None:
        self.assertEqual(
            REQUIRED_LAYOUT_METRICS,
            frozenset(DEFAULT_LAYOUT_METRICS.values),
        )
        with self.assertRaises(TypeError):
            DEFAULT_LAYOUT_METRICS.values["panel-padding"] = 20  # type: ignore[index]

    def test_incomplete_registry_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_LAYOUT_METRICS.values)
        incomplete.pop("control-height")

        with self.assertRaisesRegex(ValueError, "control-height"):
            LayoutMetrics(values=incomplete)

    def test_invalid_metric_values_fail_closed(self) -> None:
        invalid = dict(DEFAULT_LAYOUT_METRICS.values)
        invalid["panel-padding"] = 0

        with self.assertRaisesRegex(ValueError, "panel-padding"):
            LayoutMetrics(values=invalid)

        invalid["panel-padding"] = True
        with self.assertRaisesRegex(ValueError, "panel-padding"):
            LayoutMetrics(values=invalid)

    def test_grouping_invariant_fails_closed(self) -> None:
        invalid = dict(DEFAULT_LAYOUT_METRICS.values)
        invalid["related-gap"] = invalid["section-gap"]

        with self.assertRaisesRegex(ValueError, "related-gap"):
            LayoutMetrics(values=invalid)

    def test_semantic_lookup_rejects_unknown_metrics(self) -> None:
        self.assertEqual(metric("control-height"), DEFAULT_LAYOUT_METRICS.metric("control-height"))
        with self.assertRaisesRegex(KeyError, "unknown semantic layout metric"):
            metric("accepted-run-padding")


if __name__ == "__main__":
    unittest.main()
