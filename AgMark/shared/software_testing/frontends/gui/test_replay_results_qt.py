"""Variable-length replay inspection, separate scored values and retained reopen."""
from dataclasses import replace
import os
from pathlib import Path
import unittest
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from AgMark.gui.views.results import ResultsView, ResultsProjection, ResultRowProjection, RESULTS_COLUMNS
from AgMark.shared.software_testing.validation.codex_cache.fixtures import replay, request
from AgMark.shared.validation.codex_cache.metrics import treatment_summary
from AgMark.gui.application.history import save_presentation, discover_history


def summary(gid="generation-replay-view"):
    a=replace(replay(),generation_id=gid)
    b=replace(replay(2,requests=(request(kind="warmup",write=None),request(2),request(3))),generation_id=gid)
    return treatment_summary(generation_id=gid,treatment_id="treatment",replays=(a,b),scored_observation_ids=("observation-1","observation-2"))


class ReplayResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_request_tab_preserves_exact_requests_and_clears_unavailable_treatments(self):
        import json
        value = summary()
        row = ResultRowProjection("treatment", 1, "retained", "Scored", "✓", validation=value)
        other = ResultRowProjection("<b>other</b>", None, "unavailable", "Failed", "!")
        view = ResultsView(ResultsProjection(value.generation_id, (row, other)))
        self.addCleanup(view.deleteLater)
        view.cache_tabs.setCurrentWidget(view.request_panel)
        self.assertEqual(len(value.replays), view.request_details.topLevelItemCount())
        for index, replay_record in enumerate(value.replays):
            branch = view.request_details.topLevelItem(index)
            self.assertIn(replay_record.validation_id, branch.text(0))
            self.assertIn(replay_record.validates_observation_id, branch.text(0))
            self.assertEqual(replay_record.to_dict()["requests"], branch._retained)
            self.assertFalse(branch._expanded_children)
            branch.setExpanded(True)
            self.assertEqual(len(replay_record.requests), branch.childCount())
            for position, request_record in enumerate(replay_record.requests):
                self.assertEqual(request_record.to_dict(), branch.child(position)._retained)
        view.treatment_buttons[1].click()
        self.assertIs(view.request_panel, view.cache_tabs.currentWidget())
        self.assertEqual(0, view.request_details.topLevelItemCount())
        self.assertIn("No retained", view.request_status.text())
        view.treatment_buttons[0].click()
        view.set_projection(ResultsProjection(value.generation_id, (other, row)))
        self.assertIs(view.request_panel, view.cache_tabs.currentWidget())
        self.assertEqual("treatment", view._selected_row.treatment)
        self.assertEqual(len(value.replays), view.request_details.topLevelItemCount())
        disabled = treatment_summary(generation_id=value.generation_id, treatment_id="treatment",
            replays=(), scored_observation_ids=("one",), sampling_policy="disabled_by_user")
        view.set_projection(ResultsProjection(value.generation_id, (replace(row, validation=disabled),)))
        self.assertIs(view.request_panel, view.cache_tabs.currentWidget())
        self.assertEqual(0, view.request_details.topLevelItemCount())
        self.assertIn("disabled by user", view.request_status.text())
        view.set_projection(ResultsProjection("empty", (), "No results"))
        self.assertEqual(0, view.request_details.topLevelItemCount())
        self.assertEqual(0, view.provenance_details.topLevelItemCount())

    def test_detail_tabs_use_available_height_and_keyboard_navigation(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        value = summary()
        view = ResultsView(ResultsProjection(value.generation_id, (
            ResultRowProjection("treatment", 1, "retained", "Scored", "✓", validation=value),)))
        self.addCleanup(view.close)
        view.resize(1000, 900)
        view.show()
        self.app.processEvents()
        for page, content, old_limit in ((view.comparison_panel, view.comparison_table, 160),
                (view.request_panel, view.request_details, 260),
                (view.provenance_details, view.provenance_details, 260)):
            view.cache_tabs.setCurrentWidget(page)
            self.app.processEvents()
            self.assertTrue(content.isVisible())
            self.assertGreater(content.height(), old_limit)
            for other in (view.cache_table, view.replay_table, view.telemetry_details,
                          view.comparison_table, view.request_details, view.provenance_details):
                if other is not content:
                    self.assertFalse(other.isVisible())
            previous_height = content.height()
            view.resize(1000, 1050)
            self.app.processEvents()
            self.assertGreater(content.height(), previous_height)
            view.resize(1000, 900)
        view.cache_tabs.setCurrentWidget(view.comparison_panel)
        view.cache_tabs.tabBar().setFocus()
        QTest.keyClick(view.cache_tabs.tabBar(), Qt.Key.Key_Right)
        self.assertIs(view.request_panel, view.cache_tabs.currentWidget())
        QTest.keyClick(view.cache_tabs.tabBar(), Qt.Key.Key_Right)
        self.assertIs(view.provenance_details, view.cache_tabs.currentWidget())
        view.resize(560, 900)
        self.app.processEvents()
        self.assertTrue(view.cache_tabs.usesScrollButtons())
        self.assertTrue(view.provenance_details.isVisible())
        self.assertGreater(view.provenance_details.height(), 260)
        view.resize(560, 350)
        for page, content in ((view.comparison_panel, view.comparison_table),
                              (view.request_panel, view.request_details),
                              (view.provenance_details, view.provenance_details)):
            view.cache_tabs.setCurrentWidget(page)
            for _ in range(5):
                self.app.processEvents()
            origin = content.mapTo(view, QPoint(0, 0))
            self.assertLessEqual(origin.y() + content.height(), view.height())

    def test_cache_sources_remain_distinct_and_selection_does_not_leak_replay(self):
        from PySide6.QtWidgets import QComboBox
        value = summary()
        first = ResultRowProjection("treatment", 1, "retained", "Scored", "✓", validation=value,
            measurements={"cached_input_tokens": {"value": 7000, "unit": "tokens", "availability": "available"}})
        second = ResultRowProjection("other", None, "partial", "Executing", "•",
            measurements={"cached_input_tokens": {"value": 0, "unit": "tokens", "availability": "partial"}})
        view = ResultsView(ResultsProjection(value.generation_id, (first, second)))
        self.addCleanup(view.deleteLater)
        model = view.comparison_table.table_model
        self.assertEqual(["Metric", "Original Run", "Validation Replay"], [c.label for c in view.comparison_table.columns])
        self.assertEqual(0, len(view.findChildren(QComboBox)))
        self.assertEqual("7000", model.data(model.index(0, 1)))
        self.assertIn("Average: ", model.data(model.index(0, 2)))
        self.assertNotIn("7000", model.data(model.index(0, 2)))
        self.assertEqual("Unavailable", model.data(model.index(1, 1)))
        self.assertEqual("Unavailable", model.data(model.index(2, 1)))
        self.assertIn("not request pairs", view.validation_status.text())
        self.assertEqual(4, view.provenance_details.topLevelItemCount())
        for index, replay in enumerate(value.replays, 2):
            item = view.provenance_details.topLevelItem(index)
            self.assertIn(replay.validates_observation_id, item.text(0))
            self.assertIn(replay.validation_id, item.text(0))
            self.assertIn('requests', item._retained)
        view.cache_tabs.setCurrentWidget(view.provenance_details)
        self.assertFalse(view.provenance_details.isHidden())
        view.cache_table.selectRow(1)
        self.assertEqual("0 (partial)", model.data(model.index(0, 1)))
        self.assertEqual("Unavailable", model.data(model.index(0, 2)))
        self.assertEqual(1, view.provenance_details.topLevelItemCount())

    def test_root_policy_inference_preserves_version_availability_and_run_scope(self):
        import json
        value = summary()
        policy = {"observation_id": "original-observation", "attempt": 1,
            "scope": "original_run_root", "runtime_version": "0.159.0",
            "availability": "inferred", "policy": {"cache_key_value": "original-root",
                "cache_key_provenance": "inferred_codex_0_159_0_root_default",
                "cache_key_observed": False, "derived_contexts_observed": False,
                "fresh_root_conditions": "exec source, matching session/root ID, no parent or fork"}}
        unsupported = {"observation_id": "other-original", "attempt": 1,
            "scope": "original_run_root", "runtime_version": "0.158.0",
            "availability": "unavailable", "policy": None, "reason": "unaudited_codex_runtime_version"}
        row = ResultRowProjection("treatment", 1, "retained", "Scored", "✓", validation=value,
            root_cache_policies=(policy, unsupported))
        view = ResultsView(ResultsProjection(value.generation_id, (row,)))
        self.addCleanup(view.deleteLater)
        root = view.provenance_details.topLevelItem(0)
        inferred = root.child(root.childCount() - 1)
        self.assertEqual("Root cache key — inferred", inferred.text(0))
        self.assertEqual((policy, unsupported), inferred._retained)
        for index, replay in enumerate(value.replays, 2):
            root = view.provenance_details.topLevelItem(index)
            own_policy = root.child(root.childCount() - 1)
            self.assertEqual("Root cache key — inferred", own_policy.text(0))
            self.assertEqual("unavailable", own_policy._retained["availability"])
            self.assertNotIn("original-root", str(own_policy._retained))
            self.assertEqual(replay.to_dict(), root._retained)
        view.set_projection(ResultsProjection(value.generation_id, (replace(row, root_cache_policies=()),)))
        root = view.provenance_details.topLevelItem(0)
        self.assertEqual("unavailable", root.child(root.childCount() - 1)._retained["availability"])

    def test_replay_aggregate_retains_all_statistics_and_request_sequences(self):
        import json
        value = summary()
        row = ResultRowProjection("treatment", 1, "accepted", "Scored", "✓", validation=value)
        view = ResultsView(ResultsProjection(value.generation_id, (row,)))
        self.addCleanup(view.deleteLater)
        for index, replay in enumerate(value.replays, 2):
            retained = view.provenance_details.topLevelItem(index)._retained
            self.assertEqual(replay.to_dict(), retained)
            self.assertEqual(len(replay.requests), len(retained['requests']))
        summary_data = view.provenance_details.topLevelItem(1)._retained
        self.assertEqual(value.to_dict()['metrics'], summary_data['metrics'])
        self.assertEqual({'mean', 'median', 'min', 'max'}, set(summary_data['metrics']['generation_cached_input_tokens']))

    def test_disabled_validation_preserves_original_counts_without_measured_zero_replays(self):
        value = treatment_summary(generation_id="disabled-run", treatment_id="treatment", replays=(),
            scored_observation_ids=("one", "two"), sampling_policy="disabled_by_user", sampling_reason="Disabled by user")
        row = ResultRowProjection("treatment", 1, "retained", "Scored", "✓", validation=value,
            measurements={"cached_input_tokens": {"value": 37, "unit": "tokens", "availability": "available"}})
        view = ResultsView(ResultsProjection(value.generation_id, (row,)))
        self.addCleanup(view.deleteLater)
        model = view.comparison_table.table_model
        self.assertEqual("37", model.data(model.index(0, 1)))
        self.assertTrue(all(model.data(model.index(i, 2)) == "Disabled by user" for i in range(model.rowCount())))
        self.assertIn("not run", view.validation_status.text())
        self.assertEqual(2, view.provenance_details.topLevelItemCount())

    def test_all_scored_columns_survive_replay_attachment_in_each_run_state(self):
        value = summary()
        measured = {column.key: {"value": index, "unit": "tokens", "availability": "available"}
                    for index, column in enumerate(RESULTS_COLUMNS[3:], 1)}
        measured["cached_input_tokens"] = {"value": 0, "unit": "tokens", "availability": "available"}
        measured["cost"] = {"value": None, "availability": "unavailable"}
        for state, score in (("Executing", None), ("Scored", .75), ("Unavailable", None)):
            with self.subTest(state=state):
                row = ResultRowProjection("treatment", score, "retained", state, "•", measurements=measured)
                view = ResultsView(ResultsProjection(value.generation_id, (row,)))
                self.addCleanup(view.deleteLater)
                def cells():
                    prepared = view.projection._presentation["rows"][0].cells
                    return tuple(prepared[column.key].text for column in RESULTS_COLUMNS)
                before = cells()
                view.set_projection(ResultsProjection(value.generation_id, (replace(row, validation=value),)))
                self.assertEqual(before, cells())
                view.cache_tabs.setCurrentWidget(view.provenance_details)
                self.assertEqual(before, cells())
                view.set_projection(ResultsProjection(value.generation_id, (row,)))
                self.assertEqual(before, cells())

    def test_replacement_generation_treatment_and_unavailable_clear_selected_replay(self):
        value=summary()
        row=ResultRowProjection("treatment",1,"accepted","Scored","✓",validation=value)
        view=ResultsView(ResultsProjection(value.generation_id,(row,)))
        self.addCleanup(view.deleteLater)
        view.cache_tabs.setCurrentWidget(view.provenance_details)
        view.set_projection(ResultsProjection("generation-replaced",(ResultRowProjection("other",None,"unavailable","Unavailable","•"),)))
        self.assertEqual(1,view.provenance_details.topLevelItemCount())
        self.assertGreater(view.comparison_table.table_model.rowCount(), 3)
        self.assertIn("Validation unavailable",view.validation_status.text())
        self.assertIsNone(view._selected_validation)

    def test_empty_projection_clears_hidden_replay_authority(self):
        value = summary()
        view = ResultsView(ResultsProjection(value.generation_id, (ResultRowProjection("treatment", 1, "accepted", "Scored", "✓", validation=value),)))
        self.addCleanup(view.deleteLater)
        view.set_projection(ResultsProjection("empty-generation", (), "No results"))
        self.assertEqual(0, view.provenance_details.topLevelItemCount())
        self.assertEqual(0, view.comparison_table.table_model.rowCount())
        self.assertIsNone(view._selected_validation)
        self.assertIsNone(view._selected_row)
        self.assertEqual([], view.treatment_buttons)

    def test_all_treatment_tabs_order_average_coverage_and_keyboard_selection(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        value = summary()
        rows = (ResultRowProjection("other", None, "partial", "Failed", "!"),
                ResultRowProjection("treatment", 1, "retained", "Scored", "✓", validation=value,
                    measurements={"cached_input_tokens": {"value": 7000, "unit": "tokens", "availability": "partial"},
                                  "input_tokens": {"value": 9000, "unit": "tokens", "availability": "available"}}))
        view = ResultsView(ResultsProjection(value.generation_id, rows))
        self.addCleanup(view.close)
        view.resize(1000, 900)
        view.show()
        self.app.processEvents()
        self.assertEqual(["Original Run", "Validation Replay", "Original Run details",
                          "Comparison", "Request details", "Provenance"],
                         [view.cache_tabs.tabText(i) for i in range(view.cache_tabs.count())])
        self.assertEqual(["other", "treatment"], [button.text() for button in view.treatment_buttons])
        self.assertEqual(0, view.cache_tabs.currentIndex())
        self.assertFalse(view.comparison_table.isVisible())
        headers = ["Treatment", "Status", "Cached Input", "Cache Write Input", "Uncached Input", "Cache Read Fraction"]
        for table in (view.cache_table, view.replay_table):
            self.assertEqual(headers, [c.label for c in table.columns])
            self.assertEqual(["other", "treatment"], [r.cells["treatment"].text for r in table.rows])
        original = view.cache_table.rows[1].cells
        self.assertEqual("7000 (partial)", original["cached_input_tokens"].text)
        # Even with input and cached counters, the widget must not derive these.
        for key in ("uncached_input_tokens", "cache_read_fraction"):
            self.assertEqual("Unavailable", original[key].text)
        self.assertIn("Failed", view.cache_table.rows[0].cells["status"].text)
        replay_cells = view.replay_table.rows[1].cells
        metric = value.metrics["generation_cached_input_tokens"]["mean"]
        self.assertEqual("Average: " + str(metric.field.value) + " [2/2]", replay_cells["cached_input_tokens"].text)
        self.assertIn("contributing / comparable", view.cache_coverage_note.text())
        view.cache_tabs.setCurrentIndex(1)
        view.replay_table.setFocus()
        QTest.keyClick(view.replay_table, Qt.Key.Key_Down)
        self.assertEqual("treatment", view._selected_row.treatment)
        self.assertTrue(view.treatment_buttons[1].isChecked())
        self.assertEqual(1, view.cache_tabs.currentIndex())
        self.assertFalse(view.comparison_table.isVisible())
        view.cache_tabs.setCurrentWidget(view.provenance_details)
        self.assertTrue(view.provenance_details.isVisible())
        self.assertEqual(1, view.cache_table.currentIndex().row())
        self.assertEqual(4, view.provenance_details.topLevelItemCount())
        view.treatment_buttons[0].click()
        self.assertEqual("other", view._selected_row.treatment)
        self.assertEqual(0, view.replay_table.currentIndex().row())
        view.treatment_buttons[1].click()
        self.assertEqual("treatment", view._selected_row.treatment)
        self.assertEqual(4, view.provenance_details.topLevelItemCount())
        # Reordered refresh keeps treatment identity and the selected detail tab.
        view.set_projection(ResultsProjection(value.generation_id, tuple(reversed(rows))))
        self.assertIs(view.provenance_details, view.cache_tabs.currentWidget())
        self.assertEqual(0, view.replay_table.currentIndex().row())
        self.assertEqual("treatment", view._selected_row.treatment)
        self.assertTrue(view.treatment_buttons[0].isChecked())
        self.assertIs(view.provenance_details, view.cache_tabs.currentWidget())
        view.set_projection(ResultsProjection("new-generation", (rows[0],)))
        self.assertEqual(0, view.cache_tabs.currentIndex())
        self.assertIsNone(view._selected_validation)
        self.assertEqual(["other"], [button.text() for button in view.treatment_buttons])
        self.assertTrue(view.treatment_buttons[0].isChecked())
        self.assertEqual(1, view.provenance_details.topLevelItemCount())

    def test_failed_partial_and_disabled_replay_rows_preserve_independent_originals(self):
        for failed_only in (False, True):
            replays = (replay(state="failed"),) if failed_only else (replay(), replay(2, state="failed"))
            value = treatment_summary(generation_id="generation", treatment_id="treatment", replays=replays,
                scored_observation_ids=tuple(r.validates_observation_id for r in replays))
            row = ResultRowProjection("treatment", 1, "retained", "Scored", "✓", validation=value,
                measurements={"cached_input_tokens": {"value": 37, "unit": "tokens", "availability": "available"}})
            view = ResultsView(ResultsProjection("generation", (row,)))
            self.addCleanup(view.deleteLater)
            cells = view.replay_table.rows[0].cells
            self.assertIn("failed", cells["status"].text.lower())
            self.assertIn("Unavailable" if failed_only else "(partial)", cells["cached_input_tokens"].text)
            self.assertIn("[0/0]" if failed_only else "[1/1]", cells["cached_input_tokens"].text)
            self.assertEqual("37", view.cache_table.rows[0].cells["cached_input_tokens"].text)
        disabled = treatment_summary(generation_id="generation", treatment_id="treatment", replays=(),
            scored_observation_ids=("observation-1",), sampling_policy="disabled_by_user")
        view.set_projection(ResultsProjection("generation", (replace(row, validation=disabled),)))
        self.assertEqual("37", view.cache_table.rows[0].cells["cached_input_tokens"].text)
        self.assertTrue(all(cell.text.startswith("Disabled by user")
            for key, cell in view.replay_table.rows[0].cells.items() if key != "treatment"))
        self.assertEqual(2, view.provenance_details.topLevelItemCount())

    def test_history_preserves_replay_evidence_without_restoring_gui_snapshot(self):
        import json
        import tempfile
        from AgMark.shared.runtime.artifacts.archive import archive_path, read_archive_member
        from AgMark.shared.software_testing.validation.test_imported_run import seal_generation
        from zipfile import ZipFile

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repo = Path(temporary.name)
        root = repo / "AgMark" / "run_evidence"
        gid = "generation-retained-replays"
        generation = root / gid
        generation.mkdir(parents=True)
        value = summary(gid)
        retained_bytes = json.dumps(value.to_dict(), sort_keys=True).encode()
        (generation / "replay-summary.json").write_bytes(retained_bytes)
        (root / ("." + gid + ".terminal")).write_text("accepted")
        archive = seal_generation(root, gid)
        current, workspace = discover_history(repo)[gid].presentation()
        # A frontend-only projection cannot revise the released archive or
        # establish result authority when the archive is reopened.
        injected_page = ResultsView(ResultsProjection(gid, (
            ResultRowProjection("treatment", 1, "accepted", "Scored", "✓", validation=value),
        )))
        self.addCleanup(injected_page.deleteLater)
        save_presentation(root, gid, current, replace(workspace, results=injected_page))
        with patch("subprocess.Popen", side_effect=AssertionError("No execution on reopening")):
            _, reopened = discover_history(repo)[gid].presentation()
        self.assertEqual((), reopened.results.projection.rows)
        self.assertEqual("# Exact retained report\n", reopened.reports.projection.readable_content)
        self.assertEqual(retained_bytes, read_archive_member(archive, gid + "/replay-summary.json"))
        artifacts = reopened.evidence.projection.artifacts.rows
        self.assertEqual([gid + "/replay-summary.json"], [row.reference for row in artifacts])
        self.assertTrue(artifacts[0].open_action.available)
        with ZipFile(archive_path(root, gid), "a") as bundle:
            bundle.writestr("unexpected-companion.txt", "tampered")
        state = discover_history(repo)[gid]
        self.assertEqual("Evidence changed", state.state_label)
        with self.assertRaises(ValueError):
            state.presentation()

if __name__=='__main__': unittest.main()
