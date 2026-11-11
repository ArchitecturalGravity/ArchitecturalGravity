"""Outline and Findings share the map's compact pending indicator lifecycle."""
import importlib.util
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class PanelPendingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import DocumentTab
        self.tab = DocumentTab('current', '[A]: value\n=> - Act\n',
                               background=True, map_enabled=False)
        # Hold dispatch deterministically; these tests exercise GUI publication.
        self.tab.controller.timer.stop()
        self.tab.resize(1100, 700)

    def tearDown(self):
        tab = self.tab
        workers = (tab.controller.parser_worker, tab.controller.process_worker,
                   tab.outline_worker.worker, tab.highlight_worker.worker, tab.graph.worker)
        tab.close()
        tab.deleteLater()
        self.app.processEvents()
        for worker in workers:
            self.assertTrue(worker.wait_closed(10))

    def show_panels(self):
        self.tab.show()
        self.tab.side_panel.show()
        self.app.processEvents()

    def spinners(self):
        return self.tab.outline_spinner, self.tab.diagnostic_spinner

    def assert_stopped(self, spinner):
        self.assertFalse(spinner.pending)
        self.assertTrue(spinner.isHidden())
        self.assertFalse(spinner.timer.isActive())
        self.assertEqual(spinner.accessibleDescription(), '')

    def publish(self):
        from AgStudio.shared.lint import analyze
        from AgStudio.shared.panel_projections import derive_outline, derive_findings
        from AgStudio.gui.panel_rendering import apply_outline, apply_findings
        result = analyze(self.tab.source)
        self.tab.analysis = result
        self.tab.document = result.document
        self.tab.diagnostics = result.diagnostics
        apply_outline(self.tab, derive_outline(result))
        apply_findings(self.tab, derive_findings(result))

    def test_initial_hidden_pending_animates_only_when_visible(self):
        for spinner in self.spinners():
            self.assertTrue(spinner.pending)
            self.assertFalse(spinner.timer.isActive())
            self.assertIn('pending', spinner.accessibleDescription())
        self.show_panels()
        for spinner in self.spinners():
            self.assertTrue(spinner.isVisible())
            self.assertTrue(spinner.timer.isActive())
            self.assertEqual(spinner.timer.interval(), 80)
            self.assertEqual((spinner.width(), spinner.height()), (20, 20))
            phase = spinner.phase
            spinner._advance()
            self.assertEqual(spinner.phase, (phase + 30) % 360)
        self.assertEqual(self.tab.outline_status.text(), '')
        self.assertEqual(self.tab.diagnostic_status.text(), '')
        self.tab.side_panel.hide()
        self.assertFalse(self.tab.outline_spinner.timer.isActive())
        phase = self.tab.outline_spinner.phase
        self.tab.outline_spinner._advance()
        self.assertEqual(self.tab.outline_spinner.phase, phase)
        self.assertTrue(self.tab.diagnostic_spinner.timer.isActive())
        self.tab.hide()
        self.assertTrue(all(not spinner.timer.isActive() for spinner in self.spinners()))
        self.show_panels()
        self.assertTrue(all(spinner.timer.isActive() for spinner in self.spinners()))

    def test_current_results_stop_both_and_new_revision_restarts_without_text(self):
        self.show_panels()
        self.publish()
        for spinner in self.spinners():
            self.assert_stopped(spinner)
        self.tab.refresh_model()
        self.tab.controller.timer.stop()
        for spinner in self.spinners():
            self.assertTrue(spinner.pending)
            self.assertTrue(spinner.timer.isActive())
            self.assertIn('stale', spinner.accessibleDescription())
        self.assertEqual(self.tab.outline_status.text(), '')
        self.assertEqual(self.tab.diagnostic_status.text(), '')
        self.assertFalse(self.tab._outline_current)
        self.assertFalse(self.tab._findings_current)
        self.publish()
        for spinner in self.spinners():
            self.assert_stopped(spinner)

    def test_errors_stop_affected_spinner_and_ignore_obsolete_failures(self):
        self.show_panels()
        revision = self.tab.controller.revision
        self.tab._analysis_failed(revision - 1, 'old')
        self.assertTrue(all(spinner.timer.isActive() for spinner in self.spinners()))
        self.tab._outline_failed(revision, 'outline failed')
        self.assert_stopped(self.tab.outline_spinner)
        self.assertTrue(self.tab.diagnostic_spinner.timer.isActive())
        self.assertEqual(self.tab.outline_status.text(), '· unavailable')
        self.tab._analysis_failed(revision, 'parse failed')
        for spinner in self.spinners():
            self.assert_stopped(spinner)
        self.assertIn('unavailable', self.tab.diagnostic_status.text())
        self.tab.refresh_model()
        self.tab.controller.timer.stop()
        self.assertTrue(all(spinner.timer.isActive() for spinner in self.spinners()))
        self.tab.controller.parsed_analysis = object()
        self.tab._analysis_failed(self.tab.controller.revision, 'findings failed')
        self.assert_stopped(self.tab.diagnostic_spinner)
        self.assertTrue(self.tab.outline_spinner.timer.isActive())

    def test_dispose_cancels_indicators_and_reopening_cannot_restart_timers(self):
        self.show_panels()
        self.tab.dispose_analysis()
        self.tab.hide()
        self.show_panels()
        for spinner in self.spinners():
            self.assert_stopped(spinner)

    def test_map_and_panels_use_identical_artwork(self):
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import DocumentMap
        from AgStudio.gui.pending_spinner import paint_pending_spinner
        editor = SourceEditor()
        view = DocumentMap(editor)
        view.resize(180, 200)
        view.show()
        self.show_panels()
        try:
            with patch('AgStudio.gui.document_map.paint_pending_spinner', wraps=paint_pending_spinner) as map_paint, \
                    patch('AgStudio.gui.pending_spinner.paint_pending_spinner', wraps=paint_pending_spinner) as panel_paint:
                view._spinner.grab()
                for spinner in self.spinners():
                    spinner.grab()
                self.assertTrue(map_paint.called)
                self.assertEqual(panel_paint.call_count, 2)
        finally:
            view.close()
            view.deleteLater()
            editor.deleteLater()
