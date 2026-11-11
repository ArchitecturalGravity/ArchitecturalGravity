"""Synthetic render regressions; these are not provider or production benchmarks."""
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from AgMark.gui.views import results
from AgMark.gui.widgets.telemetry_details import TelemetryDetails
from AgMark.shared.software_testing.frontends.gui.test_expanded_telemetry_qt import supplied
from AgMark.shared.software_testing.validation.codex_cache.fixtures import replay, request
from AgMark.shared.validation.codex_cache.metrics import treatment_summary


class ResultsRenderCostQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def view(self, projection):
        view = results.ResultsView(projection)
        self.addCleanup(view.deleteLater)
        return view

    def test_worker_prepares_cells_once_and_gui_uses_snapshot_without_reprojection(self):
        main_thread = threading.get_ident()
        prepared_on = []
        original = results.project_comparison_table

        def record_preparation(*args, **kwargs):
            prepared_on.append(threading.get_ident())
            return original(*args, **kwargs)

        rows = tuple(results.ResultRowProjection(name, .5, "retained", "Completed", "✓",
            telemetry_projection=supplied(index)) for index, name in enumerate(("A", "B")))
        with patch.object(results, "project_comparison_table", side_effect=record_preparation):
            with ThreadPoolExecutor(max_workers=1) as pool:
                projection = pool.submit(results.ResultsProjection, "synthetic-render", rows).result()
        self.assertEqual(1, len(prepared_on))
        self.assertNotEqual(main_thread, prepared_on[0])
        with patch.object(results, "project_comparison_table", side_effect=AssertionError("GUI reprojected telemetry")), \
                patch.object(results, "measurement_cell", side_effect=AssertionError("GUI serialized measurements")):
            view = self.view(projection)
            view.cache_table.selectRow(1)
            self.assertEqual("B", view._selected_row.treatment)
            view.set_projection(projection)
            self.assertEqual("B", view._selected_row.treatment)
            self.assertEqual(["A", "B"], [button.text() for button in view.treatment_buttons])

    def test_identical_snapshot_preserves_widgets_selection_widths_and_scroll(self):
        row = results.ResultRowProjection("A", 1, "retained", "Completed", "✓", telemetry_projection=supplied())
        projection = results.ResultsProjection("synthetic-stable", (row,))
        view = self.view(projection)
        view.resize(900, 750)
        view.show()
        self.app.processEvents()
        view.cache_tabs.setCurrentWidget(view.telemetry_details)
        view.telemetry_details.tabs.setCurrentIndex(4)
        tree = view.telemetry_details.trees["errors_diagnostics"]
        item = tree.topLevelItem(0)
        tree.setCurrentItem(item)
        button = view.treatment_buttons[0]
        view.cache_table.setColumnWidth(0, 233)
        view.cache_table.horizontalScrollBar().setValue(view.cache_table.horizontalScrollBar().maximum())
        scroll = view.cache_table.horizontalScrollBar().value()
        resets = []
        view.cache_table.table_model.modelReset.connect(lambda: resets.append(True))
        view.set_projection(projection)
        self.assertFalse(resets)
        self.assertIs(button, view.treatment_buttons[0])
        self.assertTrue(button.isChecked())
        self.assertIs(tree, view.telemetry_details.tabs.currentWidget())
        self.assertIs(item, tree.currentItem())
        self.assertEqual(233, view.cache_table.columnWidth(0))
        self.assertEqual(scroll, view.cache_table.horizontalScrollBar().value())

    def test_large_retained_metadata_and_items_survive_projection_refresh(self):
        projection = supplied()
        row = projection["sections"][0]["rows"][0]
        row["evidence_references"] = [f"synthetic-reference-{index}" for index in range(4000)]
        widget = TelemetryDetails()
        self.addCleanup(widget.deleteLater)
        widget.set_projection(projection)
        item = widget.trees["tokens_cache"].topLevelItem(0)
        self.assertIs(row, item._retained)
        widget.set_projection(projection)
        self.assertIs(item, widget.trees["tokens_cache"].topLevelItem(0))

    def test_scoring_and_results_cell_display_and_replacement(self):
        from dataclasses import replace
        from AgMark.gui.views.scoring import ScoringView
        from AgMark.gui.widgets.tables import TableCell

        validation = treatment_summary(generation_id="generation", treatment_id="treatment",
            replays=(replay(requests=(request(1),)),), scored_observation_ids=("observation-1",))
        row = results.ResultRowProjection("treatment", .5, "retained", "Completed", "✓",
            validation=validation, telemetry_projection=supplied(),
            measurements={"cached_input_tokens": {"value": 12, "unit": "tokens"}})
        projection = results.ResultsProjection("generation", (row,))
        view = self.view(projection)
        scoring = ScoringView(projection)
        self.addCleanup(scoring.deleteLater)
        for table in (scoring.table, view.cache_table, view.replay_table, view.comparison_table):
            model = table.table_model
            table.set_rows(({table.columns[0].key: TableCell("Visible",
                action_available=False, action_unavailable_reason="Unavailable reason")},))
            self.assertEqual("Visible", model.data(model.index(0, 0)))
        updated = supplied(987)
        updated["sections"][0]["id"] = "replacement-section"
        view.set_projection(results.ResultsProjection("generation", (replace(row, telemetry_projection=updated),)))
        self.assertEqual(987, view.telemetry_details.trees["replacement-section"].topLevelItem(0)._retained["value"])


    def test_sections_reuse_widgets_and_keep_selection_while_changing_exact_values(self):
        widget = TelemetryDetails()
        self.addCleanup(widget.deleteLater)
        widget.set_projection(supplied())
        tree = widget.trees["requests_timing"]
        widget.tabs.setCurrentWidget(tree)
        tree.setCurrentItem(tree.topLevelItem(0))
        tree.setColumnWidth(2, 401)
        updated = supplied(987)
        widget.set_projection(updated)
        self.assertIs(tree, widget.tabs.currentWidget())
        self.assertEqual(401, tree.columnWidth(2))
        self.assertEqual("987 ms (partial)", tree.currentItem().text(1))
        self.assertEqual(updated["sections"][1]["rows"][0], tree.currentItem()._retained)
        widget.set_projection({})
        self.assertEqual(0, widget.tabs.count())
        self.assertFalse(widget.trees)

    def test_replay_descendants_are_lazy_but_all_retained_requests_remain_inspectable(self):
        retained = replay(requests=tuple(request(index) for index in range(1, 129)))
        validation = treatment_summary(generation_id="generation", treatment_id="treatment", replays=(retained,),
            scored_observation_ids=("observation-1",))
        row = results.ResultRowProjection("treatment", 1, "retained", "Completed", "✓", validation=validation)
        view = self.view(results.ResultsProjection("generation", (row,)))
        root = view.provenance_details.topLevelItem(2)
        self.assertFalse(root._expanded_children)
        self.assertEqual(retained.to_dict(), root._retained)
        self.assertFalse(root._expanded_children)
        root.setExpanded(True)
        self.assertTrue(root._expanded_children)
        requests = next(root.child(index) for index in range(root.childCount()) if root.child(index).text(0) == "requests")
        self.assertFalse(requests._expanded_children)
        requests.setExpanded(True)
        self.assertEqual(128, requests.childCount())
        for index, record in enumerate(retained.requests):
            item = requests.child(index)
            self.assertFalse(item._expanded_children)
            self.assertEqual(record.to_dict(), item._retained)
        request_root = view.request_details.topLevelItem(0)
        self.assertFalse(request_root._expanded_children)
        request_root.setExpanded(True)
        self.assertEqual(128, request_root.childCount())
        for index, record in enumerate(retained.requests):
            self.assertEqual(record.to_dict(), request_root.child(index)._retained)
        view.set_projection(results.ResultsProjection("next-generation", (), "No retained results"))
        self.assertEqual(0, view.provenance_details.topLevelItemCount())
        self.assertEqual(0, view.request_details.topLevelItemCount())

    def test_history_persists_canonical_rows_and_rebuilds_only_transient_presentation(self):
        from AgMark.gui.application.history import _decode, _encode
        row = results.ResultRowProjection("A", 1, "retained", "Completed", "✓", telemetry_projection=supplied())
        original = results.ResultsProjection("synthetic-history", (row,))
        encoded = _encode(original)
        self.assertNotIn("_presentation", encoded["fields"])
        reopened = _decode(encoded)
        self.assertIsNot(original._presentation, reopened._presentation)
        self.assertEqual(encoded, _encode(reopened))
        view = self.view(reopened)
        self.assertEqual(original._presentation["rows"], reopened._presentation["rows"])
        self.assertEqual("A", view.treatment_buttons[0].text())
        self.assertEqual("123 ms (partial)", view.telemetry_details.trees["tokens_cache"].topLevelItem(0).text(1))


if __name__ == "__main__":
    unittest.main()
