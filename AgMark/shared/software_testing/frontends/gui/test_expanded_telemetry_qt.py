"""Offline Results rendering and explicit diagnostic opt-in regressions."""
import os
import json
import unittest
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt
from AgMark.gui.views.results import ResultRowProjection, ResultsProjection, ResultsView
from AgMark.shared.telemetry.profile import DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
from AgMark.gui.shell.diagnostic_consent import DiagnosticConsentRequired
from AgMark.gui.shell.window import BenchmarkShellWindow, SidebarProjection, SidebarChoiceControlProjection
from AgMark.gui.application.history import _encode, _decode


def supplied(value=123, *, provisional=False):
    return {"schema_version": "1.0.0", "phase": "original", "provisional": provisional,
        "overview": {"telemetry_completeness": {"value": "Partial", "availability": "partial",
            "definition": "Retained source coverage", "classification": "observed", "source": "sealed manifest",
            "coverage": {"logs": "partial"}, "reason": "dropped records"}},
        "sections": [{"id": key, "title": title, "rows": [{"id": "deliberately_supplied",
            "name": "Projected metric", "value": value, "unit": "ms", "availability": "partial",
            "definition": "The supplied shared definition", "source": "fixture source",
            "classification": "proxy", "coverage": {"contributing": 2, "eligible": 3},
            "coverage_text": "2/3 eligible contributors",
            "reason": "One source unavailable", "evidence_references": ["sha256:fixture"]}]}
            for key, title in (("tokens_cache", "Tokens / cache"), ("requests_timing", "Requests / timing"),
                ("tools_turns", "Tools / turns"), ("prompts_context", "Prompts / context"),
                ("errors_diagnostics", "Errors / diagnostics"), ("configuration_cost", "Configuration / cost"),
                ("provenance_raw_events", "Provenance / raw events"))]}


class ExpandedTelemetryQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_shared_coverage_summaries_keep_exact_details_out_of_visible_cells(self):
        from AgMark.shared.telemetry.projection import presentation_measurement
        original = {"source_state": "settled", "received_events": 42, "partial": True,
                    "dropped": 2, "rejected": 0, "parse_errors": 1, "sealed": True}
        row = presentation_measurement("provider_request_count", {"coverage": original})
        self.assertEqual("Partial; Settled; 42 events; 2 dropped; 1 parse error", row["coverage_text"])
        self.assertEqual(original, row["coverage"])
        self.assertEqual("2/3 eligible contributors", presentation_measurement("ratio", {
            "coverage": {"contributing": 2, "eligible": 3}})["coverage_text"])
        self.assertEqual("Unavailable", presentation_measurement("missing", {})["coverage_text"])

    def test_execution_outcomes_remain_independent_of_telemetry_and_scoring(self):
        from AgMark.shared.reporting.results import treatment_execution_states
        observations = ({"treatment_id": "A", "terminal_status": "completed"},
                        {"treatment_id": "A", "terminal_status": "failed"})
        statuses = treatment_execution_states(observations, planned_observations={"A": 2, "B": 1}, cancelled=True)
        self.assertEqual("partial", statuses["A"]["status"])
        self.assertEqual(["completed", "failed"], statuses["A"]["outcomes"])
        self.assertEqual("cancelled", statuses["B"]["status"])
        self.assertEqual(0, statuses["B"]["retained_observations"])
        unreadable = treatment_execution_states((observations[0], b"{"), planned_observations={"A": 1})
        self.assertEqual("partial", unreadable["A"]["status"])
        self.assertEqual(1, unreadable["A"]["unclassified_observation_count"])

    def test_typed_projection_preserves_definitions_scope_and_provisional_state(self):
        row = ResultRowProjection("A", .75, "Retained score", "Completed", "✓",
            measurements={"total_tokens": {"value": 500, "unit": "tokens"}},
            telemetry_projection=supplied(provisional=True))
        view = ResultsView(ResultsProjection("generation-expanded", (row,)))
        self.addCleanup(view.deleteLater)
        self.assertEqual(7, view.telemetry_details.tabs.count())
        self.assertIn("not sealed", view.telemetry_details.status.text())
        self.assertEqual(["Original Run", "Validation Replay", "Original Run details",
                          "Comparison", "Request details", "Provenance"],
                         [view.cache_tabs.tabText(i) for i in range(view.cache_tabs.count())])
        view.cache_tabs.setCurrentIndex(2)
        self.assertTrue(view.request_panel.isHidden())
        self.assertTrue(view.comparison_panel.isHidden())
        self.assertTrue(view.provenance_details.isHidden())
        tree = view.telemetry_details.trees["requests_timing"]
        item = tree.topLevelItem(0)
        self.assertEqual("123 ms (partial)", item.text(1))
        self.assertEqual("The supplied shared definition", item.text(2))
        self.assertEqual("fixture source", item.text(3))
        self.assertEqual("proxy", item.text(4))
        self.assertIn("eligible", item.text(5))
        self.assertIn("sha256:fixture", item._retained["evidence_references"])
        # No source payload is parsed and no metric is recomputed in the GUI.
        updated = replace(row, telemetry_projection=supplied(value=987))
        view.set_projection(ResultsProjection("generation-expanded", (updated,)))
        self.assertEqual("987 ms (partial)", view.telemetry_details.trees["requests_timing"].topLevelItem(0).text(1))
        self.assertNotIn("not sealed", view.telemetry_details.status.text())
        self.assertEqual(.75, view.projection.rows[0].score)
        self.assertEqual(json.dumps(updated.telemetry_projection, sort_keys=True),
                         json.dumps(_decode(_encode(updated)).telemetry_projection, sort_keys=True))
        view.set_projection(ResultsProjection("generation-next", (), "No retained result"))
        self.assertEqual(0, view.telemetry_details.tabs.count())
        self.assertFalse(view.telemetry_details.trees)

    def test_sensitive_profile_needs_explicit_privacy_acknowledgement(self):
        sidebar = SidebarProjection(build_plan_available=True,
            runner_options=("openai.codex-cli@1.0.0",), selected_runner="openai.codex-cli@1.0.0", additional_controls=(
            SidebarChoiceControlProjection("capture_mode", "Capture Mode",
                ("session", "telemetry", "deep_telemetry"), "telemetry"),
            SidebarChoiceControlProjection("diagnostic_privacy_acknowledged", "Diagnostic privacy",
                ("not_acknowledged", DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT), "not_acknowledged")))
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.black)
        window = BenchmarkShellWindow(sidebar_projection=sidebar,
            application_icon=QIcon(pixmap), shell_preferences={}, on_build_plan=lambda _: None)
        self.addCleanup(window.deleteLater)
        profile = window.additional_control_inputs["capture_mode"]
        privacy = window.additional_control_inputs["diagnostic_privacy_acknowledged"]
        expected_labels = ["Session", "Telemetry", "Deep Telemetry"]
        self.assertEqual(expected_labels, [
            profile.combo_box.itemText(index) for index in range(profile.combo_box.count())
        ])
        self.assertEqual(("session", "telemetry", "deep_telemetry"), tuple(
            profile.combo_box.itemData(index, Qt.ItemDataRole.UserRole)
            for index in range(profile.combo_box.count())
        ))
        self.assertIn("Deep Telemetry", str(DiagnosticConsentRequired()))
        self.assertEqual("telemetry", profile.value)
        self.assertEqual("not_acknowledged", privacy.value)
        self.assertTrue(privacy.isHidden())
        profile.set_value("deep_telemetry")
        self.assertEqual("telemetry", profile.value)
        dialog = window._diagnostic_dialog
        self.assertTrue(dialog.isModal())
        self.assertFalse(dialog.save_decision.isChecked())
        notice = " ".join(label.text() for label in dialog.findChildren(QLabel))
        self.assertIn("Deep Telemetry", notice)
        for text in ("prompts", "overhead", "inference-call header", "best-effort", "Payload text may contain secrets"):
            self.assertIn(text, notice)
        dialog.accept_button.click()
        self.assertTrue(window._required_additional_controls_resolved())
        controls = {item.control_name: item.value for item in window.sidebar_input_snapshot().additional_controls}
        self.assertEqual("deep_telemetry", controls["capture_mode"])
        self.assertEqual(DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT, controls["diagnostic_privacy_acknowledged"])


if __name__ == "__main__":
    unittest.main()
