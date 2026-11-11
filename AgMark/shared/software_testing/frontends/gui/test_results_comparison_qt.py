"""Wide Original Run comparison uses shared rows, never raw telemetry math."""
import copy
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from AgMark.gui.views.results import ResultRowProjection, ResultsProjection, ResultsView
from AgMark.shared.reporting.measurement_presentation import presentation_measurement as displayed_measurement
from AgMark.shared.telemetry.comparison import LEGACY_COMPARISON_METRICS, project_comparison_table
from AgMark.shared.telemetry.normalization import normalize_capture
from AgMark.shared.telemetry.projection import project_telemetry, project_treatment_telemetry
from AgMark.shared.software_testing.telemetry.test_normalization import manifest, snapshot


def expanded():
    histogram = {"name": "codex.api_request.duration_ms", "unit": "ms", "_scope": {"name": "codex"},
        "_sanitization": {"dimensions_complete": True}, "histogram": {"aggregationTemporality": 2,
        "dataPoints": [{"count": "2", "sum": 32, "bucketCounts": ["1", "1"], "explicitBounds": [20]}]}}
    return project_treatment_telemetry({"telemetry": normalize_capture(manifest(
        [("rollout", snapshot()), ("otel_metrics", histogram)]))})


class ResultsComparisonQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def view(self, rows):
        generation = next((row.validation.generation_id for row in rows if row.validation), "wide-comparison")
        view = ResultsView(ResultsProjection(generation, rows))
        self.addCleanup(view.deleteLater)
        return view

    def cell(self, view, key, row=0):
        cell = view.projection._presentation["rows"][row].cells[key]
        return cell.text

    def test_scoring_retains_original_columns_without_a_second_results_table(self):
        supplied = expanded()
        retained = copy.deepcopy(supplied)
        view = self.view((ResultRowProjection("A", .75, "retained", "Completed", "✓", telemetry_projection=supplied),))
        keys = [column.key for column in view.projection._presentation["columns"]]
        detail_keys = {row["id"] for section in supplied["sections"] for row in section["rows"] if not row["id"].startswith("event:")}
        self.assertTrue(detail_keys <= set(keys), detail_keys - set(keys))
        legacy = [key for key, _ in LEGACY_COMPARISON_METRICS]
        self.assertEqual(["treatment", "status", "score"], keys[:3])
        self.assertEqual(legacy, [key for key in keys if key in legacy])
        self.assertEqual(["input_tokens", "cached_input_tokens", "cache_write_input_tokens", "uncached_input_tokens", "cache_read_fraction", "reasoning_tokens"],
            keys[keys.index("input_tokens"):keys.index("reasoning_tokens") + 1])
        self.assertFalse(any(key.startswith("event:") for key in keys))
        self.assertEqual("Treatments", view.treatment_heading.text())
        self.assertEqual(["A"], [button.text() for button in view.treatment_buttons])
        self.assertTrue(view.treatment_buttons[0].isChecked())
        self.assertEqual("Telemetry Details", view.cache_heading.text())
        self.assertEqual(7, view.telemetry_details.tabs.count())
        self.assertEqual(retained, view.projection.rows[0].telemetry_projection)

    def test_scoring_projection_and_details_share_authority_and_convert_minutes_once(self):
        legacy = {"session_span_minutes": {"value": 1.5, "unit": "minutes", "availability": "partial",
            "source": "retained session", "evidence_references": ["session-proof"]},
            "inference_call_count": {"value": 3, "unit": "calls", "kind": "timing_estimate", "availability": "partial",
                "method": "registered Codex session extraction@1", "source": "retained session"}}
        supplied = project_treatment_telemetry({"telemetry": normalize_capture(manifest([("rollout", snapshot())])), "roles": legacy})
        view = self.view((ResultRowProjection("A", .5, "retained", "Completed", "✓", measurements=legacy, telemetry_projection=supplied),))
        for section in supplied["sections"]:
            for row in section["rows"]:
                if row["id"].startswith("event:"):
                    continue
                cell = displayed_measurement(row["id"], view.projection._presentation["scoring_measurements"][0][row["id"]])
                expected = displayed_measurement(row["id"], row)
                for field in ("value", "unit", "source", "classification", "availability", "coverage", "evidence_references"):
                    self.assertEqual(expected[field], cell[field], (row["id"], field))
        self.assertEqual("90000 ms (partial)", self.cell(view, "session_span_minutes"))
        self.assertIn("token-event proxy", self.cell(view, "inference_call_count"))
        self.assertEqual(legacy["session_span_minutes"], view.projection.rows[0].measurements["session_span_minutes"])
        detail = next(row for section in supplied["sections"] for row in section["rows"] if row["id"] == "session_span_minutes")
        self.assertEqual((1.5, "minutes"), (detail["value"], detail["unit"]))
        view.set_projection(view.projection)
        self.assertEqual("90000 ms (partial)", self.cell(view, "session_span_minutes"))

    def test_structured_metrics_keep_native_shape_without_fabricated_totals(self):
        supplied = expanded()
        view = self.view((ResultRowProjection("A", 1, "retained", "Completed", "✓", telemetry_projection=supplied),))
        role = next(column.key for column in view.projection._presentation["columns"] if column.key.startswith("native_metric:"))
        self.assertEqual("Native histogram — see details", self.cell(view, role))
        metadata = view.projection._presentation["scoring_measurements"][0][role]
        self.assertEqual(["1", "1"], metadata["value"]["points"][0]["bucketCounts"])
        self.assertEqual(2, metadata["value"]["temporality"])
        self.assertEqual("native_metric_series", metadata["scope"])
        self.assertEqual("Unavailable", self.cell(view, "provider_request_count"))
        self.assertEqual("Structured evidence — see details", self.cell(view, "profile"))
        partial = copy.deepcopy(supplied)
        metric = next(row for section in partial["sections"] for row in section["rows"] if row["id"] == role)
        metric["availability"] = "partial"
        row = project_comparison_table((partial,))["rows"][0][role]
        self.assertEqual("Native histogram — see details (partial)", row["comparison_display"])
        self.assertEqual(metadata["value"], row["value"])
        metric.update(value=None, availability="unsupported", reason="metric exporter unsupported")
        self.assertEqual("Unsupported", project_comparison_table((partial,))["rows"][0][role]["comparison_display"])

    def test_scoring_union_missing_unsupported_partial_and_replay_separation(self):
        from AgMark.shared.software_testing.frontends.gui.test_replay_results_qt import summary
        first = project_treatment_telemetry({"roles": {"custom_latency": {"value": 12, "unit": "ms", "availability": "partial", "source": "original"}}})
        second = project_treatment_telemetry({"roles": {"custom_counter": {"value": 0, "unit": "calls", "availability": "available", "source": "original"},
            "custom_latency": {"value": None, "unit": "ms", "availability": "unsupported", "reason": "stock capability absent"}}})
        rows = (ResultRowProjection("treatment", 1, "retained", "Completed", "✓", validation=summary(), telemetry_projection=first),
                ResultRowProjection("B", None, "missing", "Failed", "!", telemetry_projection=second))
        view = self.view(rows)
        keys = [column.key for column in view.projection._presentation["columns"]]
        self.assertEqual("12 ms (partial)", self.cell(view, "custom_latency"))
        self.assertEqual("Unsupported", self.cell(view, "custom_latency", 1))
        self.assertEqual("Unavailable", self.cell(view, "custom_counter"))
        self.assertEqual("0", self.cell(view, "custom_counter", 1))
        self.assertEqual("Unavailable", self.cell(view, "cached_input_tokens"))
        self.assertTrue(all(not key.startswith("generation_") for key in keys))
        view.cache_table.selectRow(1)
        self.assertEqual(["treatment", "B"], [button.text() for button in view.treatment_buttons])
        self.assertEqual("B", view._selected_row.treatment)
        view.set_projection(ResultsProjection(view.run_id, tuple(reversed(rows))))
        self.assertEqual(keys, [column.key for column in view.projection._presentation["columns"]])
        self.assertTrue(view.treatment_buttons[0].isChecked())
        self.assertEqual("B", view._selected_row.treatment)

    def test_buttons_switch_the_selected_treatment_telemetry_without_new_authority(self):
        def measured(value):
            return project_treatment_telemetry({"roles": {"input_tokens": {
                "value": value, "unit": "tokens", "availability": "available"}}})
        first = measured(12)
        second = measured(44)
        view = self.view((ResultRowProjection("first", .5, "retained", "Scored", "✓",
                    telemetry_projection=first),
            ResultRowProjection("second", .7, "retained", "Scored", "✓",
                    telemetry_projection=second)))
        view.cache_tabs.setCurrentWidget(view.telemetry_details)
        self.assertIs(first, view.telemetry_details._projection)
        view.treatment_buttons[1].click()
        self.assertIs(second, view.telemetry_details._projection)
        self.assertEqual("second", view._selected_row.treatment)
        self.assertTrue(view.treatment_buttons[1].isChecked())
        self.assertEqual(1, view.cache_table.currentIndex().row())
        tree = view.telemetry_details.trees["tokens_cache"]
        value = next(tree.topLevelItem(i).text(1) for i in range(tree.topLevelItemCount())
                     if tree.topLevelItem(i)._retained["id"] == "input_tokens")
        self.assertEqual("44 tokens", value)
        view.cache_table.selectRow(0)
        self.assertTrue(view.treatment_buttons[0].isChecked())
        self.assertIs(first, view.telemetry_details._projection)

    def test_source_health_counts_retain_explicit_availability_and_provenance(self):
        for state in ("unsupported", "unavailable", "failed", "partial"):
            with self.subTest(state=state):
                health = {"state": state, "received_events": 0, "received_bytes": 10, "parse_errors": 1,
                    "partial": state == "partial", "reason": "source fixture reason", "records_sha256": "sha256:retained-source"}
                supplied = project_telemetry({"sealed": True, "sources": {"otel_logs": health}, "measurements": {}})
                projected = project_comparison_table((supplied,))["rows"][0]
                count = projected["source:otel_logs:received_events"]
                self.assertEqual(0, count["value"])
                self.assertEqual(state, count["availability"])
                self.assertEqual(health, count["coverage"])
                self.assertEqual("shared capture-health projection@1.0.0", count["method"])
                self.assertIn("source_records_sha256:sha256:retained-source", count["evidence_references"])
                self.assertNotIn("source:otel_logs:dropped", projected)
                view = self.view((ResultRowProjection("A", 1, "retained", "Completed", "✓", telemetry_projection=supplied),))
                self.assertEqual(f"0 events ({state})", self.cell(view, "source:otel_logs:received_events"))


if __name__ == "__main__":
    unittest.main()
