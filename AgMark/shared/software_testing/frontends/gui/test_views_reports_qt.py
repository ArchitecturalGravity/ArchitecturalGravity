"""Single report reading, independent state, operation and replacement proof."""
from dataclasses import replace
import os
import threading
import unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from AgMark.gui.views.reports import PYSIDE6_AVAILABLE, ReportsProjection, ReportActionProjection, ReportsView
if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication, QLabel, QTableView
    from PySide6.QtCore import Qt


def _projection(calls=None):
    calls = calls if calls is not None else []
    return ReportsProjection(run_id="generation-a", report_id="report-a", readable_content="# Treatment summary\n\nRetained results.\n\n| Treatment | Accuracy |\n| --- | --- |\n| Control | 1 |\n",
        generation_state="complete", completeness="complete", generated_at="2026-09-30T00:00:00Z", verification_state="passed", limitations="Synthetic conformance only.",
        
        export_action=ReportActionProjection(lambda: calls.append("export"), True),
        )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 unavailable")
class ReportsViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_completion_diagnostics_are_plain_text_and_clear_on_replacement(self):
        lines = ("Archive publication: passed", "Post-publication cleanup: warning (PermissionError; published archive remains available)")
        view = ReportsView(replace(_projection(), completion_diagnostics=lines))
        self.addCleanup(view.deleteLater)
        self.assertEqual("\n".join(lines), view.completion_diagnostics_label.text())
        self.assertEqual(Qt.TextFormat.PlainText, view.completion_diagnostics_label.textFormat())
        self.assertTrue(view.export_button.isEnabled())
        self.assertEqual("complete", view.projection.generation_state)
        view.set_projection(ReportsProjection(run_id="generation-other", empty_state="No report."))
        self.assertEqual("", view.completion_diagnostics_label.text())
        self.assertTrue(view.completion_diagnostics_label.isHidden())
        self.assertFalse(view.export_button.isEnabled())

    def test_content_states_and_single_page(self):
        view = ReportsView(_projection())
        self.addCleanup(view.deleteLater)
        self.assertIn("Treatment summary", view.content_browser.toPlainText())
        self.assertIn("Control", view.content_browser.toPlainText())
        self.assertIn("Completeness: complete", view.status_label.text())
        self.assertIn("Completion validation: passed", view.status_label.text())
        self.assertNotIn("Claims:", view.status_label.text())
        self.assertNotIn("claim", view.status_label.accessibleName())

        self.assertIn("Synthetic conformance only.", view.status_label.text())
        self.assertFalse(view.findChildren(QTableView))
        self.assertTrue(view.export_button.isEnabled())
        self.assertEqual(view.authority_semantics, "presentation-only")

    def test_compact_header_has_description_without_redundant_title(self):
        view = ReportsView(_projection())
        self.addCleanup(view.deleteLater)
        self.assertFalse(view.findChildren(QLabel, "reportsHeading"))
        self.assertEqual(view.description_label.text(), view.projection.description)
        self.assertEqual(view.heading_holder.minimumHeight(), 20)
        self.assertEqual(view.heading_holder.layout().count(), 1)

    def test_supplied_export_and_verification_operations(self):
        calls = []
        view = ReportsView(_projection(calls))
        self.addCleanup(view.deleteLater)
        view.export_button.click()
        self.assertEqual(calls, ["export"])


    def test_native_report_remains_exportable_without_optional_verification(self):
        calls = []
        projection = replace(
            _projection(calls),
            verification_state="passed",

        )
        view = ReportsView(projection)
        self.addCleanup(view.deleteLater)
        self.assertIn("Treatment summary", view.content_browser.toPlainText())
        self.assertTrue(view.export_button.isEnabled())
        self.assertIn("Completion validation: passed", view.status_label.text())
        view.export_button.click()
        self.assertEqual(calls, ["export"])

    def test_empty_generation_failure_and_unavailable_actions(self):
        view = ReportsView(ReportsProjection(run_id="generation-b",  generation_state="failed", empty_state="Generator failed: unavailable source."))
        self.addCleanup(view.deleteLater)
        self.assertIn("Generator failed", view.content_browser.toPlainText())
        self.assertIn("Completion: failed", view.status_label.text())
        self.assertFalse(view.export_button.isEnabled())

    def test_worker_replacement_clears_content_and_old_actions(self):
        calls = []
        view = ReportsView(_projection(calls))
        self.addCleanup(view.deleteLater)
        prior_button = view.export_button
        following = ReportsProjection(run_id="generation-b",  empty_state="Report not generated.")
        worker = threading.Thread(target=view.set_projection, args=(following,))
        worker.start(); worker.join()
        QApplication.processEvents()
        self.assertEqual(view.run_id, "generation-b")
        self.assertNotIn("Control", view.content_browser.toPlainText())
        self.assertNotIn("report-a", view.status_label.text())
        self.assertFalse(prior_button.isEnabled())
        self.assertFalse(view.export_button.isEnabled())
        self.assertEqual(view.export_feedback_label.text(), "")

    def test_feedback_and_responsive_keyboard_access(self):
        for size in ((1100, 600), (960, 420)):
            view = ReportsView(replace(_projection(), export_feedback="Saved report to selected/report.md"))
            self.addCleanup(view.deleteLater)
            view.resize(*size); view.show(); QApplication.processEvents()
            self.assertTrue(view.export_feedback_label.isVisible())
            self.assertIn("selected/report.md", view.export_feedback_label.text())
            self.assertNotEqual(view.content_browser.focusPolicy(), Qt.FocusPolicy.NoFocus)
            self.assertGreater(view.content_browser.height(), 100)
            self.assertLessEqual(view.actions_holder.geometry().right(), view.width())
            self.assertFalse(view.grab().isNull())

    def test_content_and_export_require_exact_report_identity(self):
        with self.assertRaises(ValueError):
            ReportsProjection(run_id="a",  readable_content="orphan content")

    def test_report_native_formatting_and_source_preserved(self):
        from PySide6.QtGui import QTextTable
        projection = _projection()
        view = ReportsView(projection)
        self.addCleanup(view.deleteLater)
        browser = view.content_browser
        self.assertEqual(view.projection.readable_content, projection.readable_content)
        first = browser.document().begin()
        self.assertEqual(first.blockFormat().headingLevel(), 1)
        self.assertGreater(first.blockFormat().bottomMargin(), 0)
        from PySide6.QtGui import QTextCursor, QTextFormat
        cursor = QTextCursor(first)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
        self.assertEqual(cursor.charFormat().property(QTextFormat.Property.FontPixelSize), 18)
        tables = [f for f in browser.document().rootFrame().childFrames() if isinstance(f, QTextTable)]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].format().cellPadding(), 7)
        self.assertEqual(tables[0].cellAt(0, 0).format().background().color().name(), '#eaf1fa')
        self.assertEqual(view.section_selector.count(), 1)
        self.assertTrue(view.expand_button.isEnabled())

    def test_report_html_and_resource_loading_are_inert(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QTextDocument
        source = '# Safe\n\n<img src="file:///private/image.png">\n\n<script>bad()</script>\n\n![image](https://example.invalid/tracking.png)\n\n[link](https://example.invalid)\n\n```html\n<b>literal</b>\n```'
        view = ReportsView(replace(_projection(), readable_content=source))
        self.addCleanup(view.deleteLater)
        self.assertIn('<img', view.content_browser.toPlainText())
        self.assertIn('<b>literal</b>', view.content_browser.toPlainText())
        self.assertIsNone(view.content_browser.loadResource(QTextDocument.ResourceType.ImageResource, QUrl('file:///private/image.png')))
        self.assertFalse(view.content_browser.openLinks())
        self.assertFalse(view.content_browser.openExternalLinks())
        self.assertEqual(view.projection.readable_content, source)

    def test_jump_menu_shows_major_sections_not_each_provenance_field(self):
        source = (
            "# Benchmark report\n\n## Executive summary\n\nOverview.\n\n"
            "## Appendix — Telemetry\n\n### Candidate measurement provenance\n\n"
            "#### Total tokens\n\nRetained details.\n"
        )
        view = ReportsView(replace(_projection(), readable_content=source))
        self.addCleanup(view.deleteLater)
        headings = [
            view.section_selector.itemText(index)
            for index in range(view.section_selector.count())
        ]
        self.assertEqual(headings, [
            "Benchmark report", "Executive summary", "Appendix — Telemetry",
        ])
        self.assertIn(
            "Candidate / Total tokens",
            [title for title, _position in view.content_browser.sections],
        )

    def test_section_navigation_and_empty_replacement(self):
        source = '# Start\n\n' + ('A long paragraph. ' * 60 + '\n\n') * 20 + '## Final section\n\nExact final result.'
        view = ReportsView(replace(_projection(), readable_content=source))
        self.addCleanup(view.deleteLater)
        view.resize(720, 600); view.show(); QApplication.processEvents()
        view._select_section(1)
        self.assertGreater(view.content_browser.verticalScrollBar().value(), 0)
        self.assertEqual(view.content_browser.textCursor().block().text(), 'Final section')
        view.set_projection(ReportsProjection(run_id='next',  empty_state='No report.'))
        self.assertEqual(view.section_selector.count(), 0)
        self.assertFalse(view.expand_button.isEnabled())
        self.assertFalse(view.section_selector.isEnabled())

    def test_report_long_content_at_narrow_normal_and_wide_sizes(self):
        source = _projection().readable_content + '\n## Provenance\n\n' + ('Exact identity ' + 'a' * 200 + '\n\n') * 10
        for width in (540, 850, 1400):
            view = ReportsView(replace(_projection(), readable_content=source))
            self.addCleanup(view.deleteLater)
            view.resize(width, 700); view.show(); QApplication.processEvents()
            self.assertIn('a' * 200, view.content_browser.toPlainText())
            self.assertLessEqual(view.section_selector.geometry().right(), view.width())
            self.assertLessEqual(view.expand_button.geometry().right(), view.width())
            self.assertGreater(view.content_browser.viewport().height(), 100)
            self.assertFalse(view.grab().isNull())

    def test_expanded_reader_repeated_close_preserves_report(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QDialog
        from AgMark.gui.widgets.report_reader import ReportReader
        view = ReportsView(_projection())
        self.addCleanup(view.deleteLater)
        observed = []
        def close_reader():
            dialog = QApplication.activeModalWidget()
            observed.append(isinstance(dialog, QDialog))
            reader = dialog.findChild(ReportReader)
            observed.append(reader.toPlainText() == view.content_browser.toPlainText())
            dialog.reject()
        for _ in range(2):
            QTimer.singleShot(0, close_reader)
            view._expand_report()
            QApplication.processEvents()
        self.assertEqual(observed, [True, True, True, True])
        self.assertEqual(view.projection.readable_content, _projection().readable_content)

    def test_feedback_refresh_preserves_document_and_reading_position(self):
        from unittest.mock import patch
        source = '# Start\n\n' + ('Retained paragraph.\n\n' * 100) + '## End\n\nFinal.'
        view = ReportsView(replace(_projection(), readable_content=source, export_feedback="Ready."))
        self.addCleanup(view.deleteLater)
        view.resize(720, 500); view.show(); QApplication.processEvents()
        view._select_section(1)
        QApplication.processEvents()
        view.content_browser.verticalScrollBar().setValue(500)
        position = view.content_browser.textCursor().position()
        scroll = view.content_browser.verticalScrollBar().value()
        with patch.object(view.content_browser, 'set_report', side_effect=AssertionError('Unchanged report rebuilt')):
            for feedback in ('Saved report.', 'Export cancelled.', 'Saved report again.'):
                view.set_projection(replace(view.projection, export_feedback=feedback))
                QApplication.processEvents()
        self.assertEqual(position, view.content_browser.textCursor().position())
        self.assertEqual(scroll, view.content_browser.verticalScrollBar().value())
        self.assertEqual(view.export_feedback_label.text(), 'Saved report again.')

    def test_visible_large_report_replacement_batches_document_layout(self):
        from time import monotonic
        view = ReportsView(_projection())
        self.addCleanup(view.deleteLater)
        view.resize(720, 500); view.show(); QApplication.processEvents()
        source = '# Large report\n\n' + ('## Evidence\n\n| A | B |\n|---|---|\n| exact | retained |\n\n' * 200)
        started = monotonic()
        view.set_projection(replace(view.projection, readable_content=source))
        QApplication.processEvents()
        self.assertLess(monotonic() - started, 5, 'Visible report formatting repeatedly relaid out the document')
        self.assertTrue(view.content_browser.document().isLayoutEnabled())
        self.assertTrue(view.content_browser.updatesEnabled())
        self.assertEqual(view.projection.readable_content, source)
