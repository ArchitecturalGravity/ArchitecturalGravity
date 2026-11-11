"""Component floors, reflow, and local overflow with populated projections."""

import os
import unittest
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.shell.window import PYSIDE6_AVAILABLE

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QBoxLayout, QLabel, QPushButton, QWidget
    from AgMark.gui.shell.window import _TabContentScrollArea
    from AgMark.gui.views.results import ResultsView, ResultsProjection, ResultRowProjection
    from AgMark.gui.views.artifacts import ArtifactsView, ArtifactsProjection
    from AgMark.gui.views.verification import VerificationView
    from AgMark.gui.views.reports import ReportsView
    from AgMark.gui.views.progress import ProgressView
    from AgMark.shared.software_testing.frontends.gui.test_views_progress_qt import _projection as progress_projection
    from AgMark.shared.software_testing.frontends.gui.test_views_artifacts_qt import _row
    from AgMark.shared.software_testing.frontends.gui.test_views_verification_qt import _projection as verification_projection
    from AgMark.shared.software_testing.frontends.gui.test_views_reports_qt import _projection as reports_projection


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 unavailable")
class WorkspaceComponentSizingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def settle(self):
        for _ in range(8):
            self.app.processEvents()

    def scroll(self, page):
        page.setMinimumWidth(560)
        scroll = _TabContentScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        scroll.show()
        self.addCleanup(scroll.deleteLater)
        return scroll

    def contained(self, page, components):
        for component in components:
            with self.subTest(component=component.objectName()):
                point = component.mapTo(page, QPoint(0, 0))
                self.assertGreaterEqual(point.x(), 0)
                self.assertGreaterEqual(point.y(), 0)
                self.assertLessEqual(point.x() + component.width(), page.width())
                self.assertLessEqual(point.y() + component.height(), page.height())
                self.assertGreaterEqual(component.width(), component.minimumWidth())
                self.assertGreaterEqual(component.height(), component.minimumHeight())

    def test_results_and_artifacts_keep_readable_viewports_and_action_cells(self):
        results = ResultsView(ResultsProjection(run_id="sizing", rows=(
            ResultRowProjection(treatment="A", score=0, evidence="Retained",
                                status="Scored", status_icon="✓", details="Detail\n" * 40),
        )))
        artifacts = ArtifactsView(ArtifactsProjection(run_id="sizing", rows=(_row(),)))
        self.assertEqual(artifacts.table.minimumSize().toTuple(), (480, 260))
        self.assertEqual(results.treatment_scroll.minimumSize().toTuple(), (320, 64))
        for page, components in ((results, (results.treatment_scroll, results.cache_table)),
                                 (artifacts, (artifacts.table,))):
            scroll = self.scroll(page)
            for size in ((560, 240), (900, 650), (1280, 900), (900, 1200), (560, 240)):
                scroll.resize(*size)
                self.settle()
                self.contained(page, components)
                self.assertEqual(scroll.size().toTuple(), size)
            self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        self.assertGreaterEqual(results.cache_table.height(), 160)
        for _ in range(2):
            artifacts.set_projection(artifacts.projection)
            self.settle()
            holder = artifacts._action_holders[0]
            cell = artifacts.table.visualRect(artifacts.table.table_model.index(0, 5))
            self.assertGreaterEqual(cell.height(), holder.minimumHeight())
            self.assertGreaterEqual(cell.width(), holder.minimumWidth())
            self.assertLessEqual(artifacts.table.columnWidth(0), 360)
            self.assertLessEqual(artifacts.table.columnWidth(3), 280)

    def test_verification_stacks_and_long_ids_do_not_set_page_width(self):
        projection = verification_projection()
        projection = replace(projection, summary=replace(
            projection.summary, boundary_fingerprint="sha256:" + "a" * 64,
            manifest_id="manifest-" + "b" * 64,
        ))
        page = VerificationView(projection)
        scroll = self.scroll(page)
        for width, direction in ((900, QBoxLayout.Direction.LeftToRight),
                                 (580, QBoxLayout.Direction.TopToBottom),
                                 (1280, QBoxLayout.Direction.LeftToRight)):
            scroll.resize(width, 600)
            self.settle()
            self.assertEqual(page.layout().direction(), direction)
            self.assertLessEqual(page.width(), scroll.viewport().width())
            self.contained(page, (page.status_card, page.summary_card,
                                  *page._summary_value_labels.values(),
                                  *page.check_result_labels.values(),
                                  *page.check_disclosure_buttons.values()))
        scroll.resize(580, 320)
        self.settle()
        for button in page.check_disclosure_buttons.values():
            button.setChecked(True)
        self.settle()
        self.contained(page, (page.status_card, page.summary_card, *page.check_details_labels.values()))
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)

    def test_reports_actions_status_and_document_remain_reachable(self):
        page = ReportsView(replace(reports_projection(), run_id="generation-" + "c" * 64,
                                   export_feedback="Saved " + "path/" * 40))
        scroll = self.scroll(page)
        for size in ((580, 320), (900, 650), (1280, 900), (900, 1200), (580, 320)):
            scroll.resize(*size)
            self.settle()
            self.assertLessEqual(page.width(), scroll.viewport().width())
            self.contained(page, (page.heading_holder, page.actions_holder, page.status_card,
                                  page.export_feedback_label, page.content_browser))
            self.assertGreaterEqual(page.content_browser.height(), 300)
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        page.set_projection(reports_projection())
        self.settle()
        self.contained(page, (page.actions_holder, page.status_card, page.content_browser))

    def test_progress_bars_and_cells_remain_contained_at_all_workspace_sizes(self):
        page = ProgressView(progress_projection())
        scroll = self.scroll(page)
        for size in ((580, 320), (900, 650), (1280, 900), (900, 1200), (580, 320)):
            with self.subTest(size=size):
                scroll.resize(*size)
                self.settle()
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                self.contained(page, (page.summary_card, page.treatment_card,
                                      page.treatment_table, page.run_stage_card,
                                      page.overall_bar, page.overall_ring))
                for index, treatment in enumerate(page.projection.treatments):
                    holder = page.treatment_table.indexWidget(
                        page.treatment_table.table_model.index(index, 1))
                    progress = page.treatment_progress_widgets[treatment.treatment_id]
                    self.contained(holder, (progress.indicator,))
                    self.assertGreaterEqual(page.treatment_table.rowHeight(index),
                                            holder.minimumHeight() + 1)
                    self.assertGreaterEqual(page.treatment_table.columnWidth(1),
                                            holder.minimumWidth())

    def test_report_metadata_and_verification_rows_do_not_stretch_in_tall_workspaces(self):
        report = ReportsView(replace(
            reports_projection(),
            run_id="long-benchmark-run-20261003T170000Z-" + "a" * 32,
            report_id="report-" + "b" * 64,
            generated_at="2026-10-03T17:00:00.123456+00:00",
            limitations="Synthetic conformance evidence only; external validity is not established.",
        ))
        verification_data = verification_projection()
        verification = VerificationView(replace(
            verification_data,
            summary=replace(verification_data.summary,
                            manifest_id="manifest-" + "c" * 64,
                            boundary_fingerprint="sha256:" + "d" * 64),
        ))
        for page, controls in (
            (report, (report.heading_holder, report.status_card, report.actions_holder)),
            (verification, tuple(verification.findChildren(QWidget, "verificationSummaryRow_" + name)[0]
                                 for name in verification._summary_value_labels)),
        ):
            scroll = self.scroll(page)
            scroll.resize(900, 650)
            self.settle()
            heights = [control.height() for control in controls]
            scroll.resize(900, 1200)
            self.settle()
            self.contained(page, controls)
            for control, height in zip(controls, heights):
                with self.subTest(control=control.objectName()):
                    self.assertLessEqual(control.height(), height + 2)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)

    def test_artifact_buttons_fit_action_holders_through_reflow_and_refresh(self):
        page = ArtifactsView(ArtifactsProjection(run_id="density-fixture", rows=(
            _row(artifact_id="manifest", artifact="manifest/accepted-evidence-manifest.json"),
            _row(artifact_id="report", artifact="reports/reconstruction-verification-report.md",
                 reveal_available=False),
        )))
        scroll = self.scroll(page)
        for size in ((580, 320), (900, 650), (1280, 900), (900, 1200), (580, 320)):
            scroll.resize(*size)
            page.set_projection(page.projection)
            self.settle()
            for index, holder in enumerate(page._action_holders):
                with self.subTest(size=size, row=index):
                    buttons = holder.findChildren(QPushButton)
                    self.assertEqual(len(buttons), 2)
                    self.contained(holder, buttons)
                    cell = page.table.visualRect(page.table.table_model.index(index, 5))
                    self.assertGreaterEqual(cell.height(), holder.minimumHeight())
                    self.assertGreaterEqual(cell.width(), holder.minimumWidth())

    def test_progress_counter_captions_fit_their_cells_with_two_line_labels(self):
        page = ProgressView(progress_projection())
        scroll = self.scroll(page)
        for size in ((580, 320), (900, 650), (1280, 900), (900, 1200)):
            scroll.resize(*size)
            self.settle()
            counters = page.findChild(QWidget, "progressSummaryCounters")
            for value_label in page.summary_value_labels.values():
                cell = value_label.parentWidget()
                labels = cell.findChildren(QLabel)
                self.assertEqual(len(labels), 2)
                self.contained(counters, (cell,))
                self.contained(cell, labels)
                for label in labels:
                    required = (label.heightForWidth(label.width())
                                if label.hasHeightForWidth() else label.sizeHint().height())
                    self.assertGreaterEqual(label.height(), required,
                                            (size, label.text(), label.geometry()))
