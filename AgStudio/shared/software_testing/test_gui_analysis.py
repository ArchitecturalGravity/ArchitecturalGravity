"""Production analyzer parity and background lifecycle regression tests."""
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from AgStudio.shared.lint import analyze


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class BackgroundAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        self.window = StudioWindow('current', user_state=UserState())
        self.window.show()
        self.app.processEvents()
        self.releases = []

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox
        for release in self.releases:
            release.set()
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_for(self, condition, timeout=5):
        from PySide6.QtTest import QTest
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            QTest.qWait(10)
        self.assertTrue(condition(), 'analysis did not reach expected state')

    def settled(self, tab):
        self.wait_for(lambda: tab.analysis is not None and tab.diagnostics is not None and tab.analysis.document.source == tab.source)

    def test_production_default_and_cli_core_parity(self):
        tab = self.window.current()
        self.assertIsNotNone(tab.controller)
        tab.editor.setPlainText('[A]: 🌍\n=> 1. Act\nUse [Later]\n[Later]: value\n')
        self.assertIsNone(tab.document)
        self.assertEqual(tab.diagnostics_heading.text(), 'Finding List')
        self.assertEqual(tab.diagnostic_status.text(), '')
        self.assertTrue(tab.diagnostic_spinner.pending)
        self.assertTrue(all(label.text() == '0' for label in tab.diagnostic_count_labels.values()))
        self.assertIn('pending', tab.diagnostics_heading.toolTip())
        self.settled(tab)
        result = analyze(tab.source)
        self.assertEqual(tab.analysis.as_record(), result.as_record())
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), len(result.diagnostics.findings))
        for i in range(tab.diagnostic_list.topLevelItemCount()):
            from PySide6.QtCore import Qt
            finding = tab.diagnostic_list.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            tab._navigate_finding(tab.diagnostic_list.topLevelItem(i))
            self.assertEqual(tab.editor.textCursor().selectedText(), finding.source_range.span.extract(tab.source))

    def test_manual_diagnose_action_and_shortcut_are_absent(self):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu
        actions = self.window.findChildren(QAction)
        self.assertFalse(any(action.text() == 'Diagnose' for action in actions))
        self.assertFalse(any(shortcut.toString() == 'F5'
                             for action in actions for shortcut in action.shortcuts()))
        self.assertFalse(any(menu.title() == 'Diagnostics' for menu in self.window.findChildren(QMenu)))
        self.assertTrue(any(action.text() == 'Finding List' for action in actions))

    def test_rapid_typing_coalesces_and_never_publishes_old_result(self):
        tab = self.window.current()
        started, release = threading.Event(), threading.Event()
        self.releases.append(release)
        calls = []
        def worker(source, **kwargs):
            calls.append(source)
            if len(calls) == 1:
                started.set()
                release.wait(3)
            return analyze(source, **kwargs)
        tab.controller.worker = worker
        tab.editor.setPlainText('=> - Old')
        self.wait_for(started.is_set)
        old_revision = tab.controller.revision
        for i in range(20):
            tab.editor.setPlainText(f'Scope: value{i}')
        self.assertIsNone(tab.document)
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 0)
        release.set()
        self.settled(tab)
        self.assertEqual(calls, ['=> - Old', 'Scope: value19'])
        current = tab.analysis
        # Even an artificially reordered late result cannot replace current B.
        tab._analysis_ready(old_revision, analyze('=> - Old'))
        self.assertIs(tab.analysis, current)
        self.assertEqual(tab.diagnostics.findings, ())

    def test_switch_close_and_replace_tab_with_running_worker(self):
        tab = self.window.current()
        started, release = threading.Event(), threading.Event()
        self.releases.append(release)
        def worker(source, **kwargs):
            started.set()
            release.wait(3)
            return analyze(source, **kwargs)
        tab.controller.worker = worker
        tab.editor.setPlainText('=> - Old')
        self.wait_for(started.is_set)
        second = self.window.new_document()
        second.editor.setPlainText('Scope: new')
        self.settled(second)
        from PySide6.QtWidgets import QMessageBox
        controller = tab.controller
        with mock.patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Discard):
            self.window._close_tab(0)
        self.assertTrue(controller.closed)
        release.set()
        self.app.processEvents()
        self.assertIs(self.window.current(), second)
        self.assertEqual(second.analysis.document.source, 'Scope: new')

    def test_undo_redo_literal_and_bom_crlf_save_while_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.arc'
            raw = b'\xef\xbb\xbf=> - Active\r\n'
            path.write_bytes(raw)
            tab = self.window.open_file(path)
            self.settled(tab)
            self.assertEqual(len(tab.diagnostics.findings), 3)
            tab.editor.insertPlainText('"""\n')
            self.settled(tab)
            self.assertEqual([f.rule_id for f in tab.diagnostics.findings], ['AG-DOCUMENT-START-SECTION', 'AG-LITERAL-UNCLOSED', 'AG-DOCUMENT-END-SECTION'])
            tab.editor.undo()
            self.settled(tab)
            self.assertEqual(tab.source.encode(tab.encoding), raw)
            tab.editor.redo()
            tab.save()
            self.settled(tab)
            self.assertEqual(path.read_bytes(), tab.source.encode(tab.encoding))
            self.assertIn('\r\n', tab.source)
            self.assertEqual(tab.analysis.document.source, tab.source)

    def test_failure_clears_old_diagnostics_and_next_edit_recovers(self):
        tab = self.window.current()
        self.settled(tab)
        def broken(*args, **kwargs):
            raise RuntimeError('intentional test failure')
        tab.controller.worker = broken
        tab.editor.setPlainText('=> - Act')
        self.wait_for(lambda: 'Analysis failed' in tab.diagnostics_heading.toolTip())
        self.assertEqual(tab.diagnostics_heading.text(), 'Finding List')
        self.assertEqual(tab.diagnostic_status.text(), '· unavailable')
        self.assertTrue(all(label.text() == '0' for label in tab.diagnostic_count_labels.values()))
        self.assertIn('intentional test failure', tab.diagnostics_heading.toolTip())
        self.assertIsNone(tab.document)
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 0)
        tab.controller.worker = analyze
        tab.editor.setPlainText('=> - Updated')
        self.settled(tab)
        self.assertEqual(len(tab.diagnostics.findings), 3)
        self.assertEqual(tab.diagnostics_heading.text(), 'Finding List')
        self.assertEqual(sum(int(label.text()) for label in tab.diagnostic_count_labels.values()), tab.diagnostic_list.topLevelItemCount())
        self.assertEqual(tab.diagnostic_status.text(), '')
        self.assertNotIn('failed', tab.diagnostics_heading.toolTip())

    def test_error_list_has_one_heading_and_keeps_errors_and_warnings(self):
        from PySide6.QtWidgets import QLabel
        tab = self.window.current()
        tab.editor.setPlainText('=> - Act\nUse `two words`\n- mispelled text\n')
        self.settled(tab)
        self.assertEqual(tab.diagnostics_heading.text(), 'Finding List')
        self.assertEqual(sum(int(label.text()) for label in tab.diagnostic_count_labels.values()), tab.diagnostic_list.topLevelItemCount())
        self.assertEqual(tab.diagnostic_status.text(), '')
        self.assertEqual([label.text() for label in tab.diagnostics_panel.findChildren(QLabel)].count('Finding List'), 1)
        self.assertEqual(tab.diagnostics_panel.layout().count(), 2)
        severities = {tab.diagnostic_list.topLevelItem(i).text(0)
                      for i in range(tab.diagnostic_list.topLevelItemCount())}
        self.assertEqual(severities, {'Critical', 'Error', 'Warning', 'Info'})
        self.window.panel_actions['error_list'].trigger()
        self.assertTrue(tab.diagnostics_panel.isHidden())
        self.window._show_diagnostics()
        self.assertFalse(tab.diagnostics_panel.isHidden())
        tab.editor.setPlainText('Task: valid prose')
        self.settled(tab)
        self.assertEqual(tab.diagnostics_heading.text(), 'Finding List')
        self.assertEqual(sum(int(label.text()) for label in tab.diagnostic_count_labels.values()), tab.diagnostic_list.topLevelItemCount())
        self.assertEqual(tab.diagnostic_status.text(), '')
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 0)
        self.assertIn('conformance unknown', tab.diagnostics_heading.toolTip())

    def test_spelling_underlines_clear_while_pending_and_after_correction(self):
        tab = self.window.current()
        tab.editor.setPlainText('Task:\n- mispelled text\n')
        self.settled(tab)
        self.assertEqual(len(tab.editor._spelling_selections), 1)
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 1)
        self.assertEqual(tab.diagnostic_list.topLevelItem(0).text(0), 'Warning')
        tab.editor.setPlainText('Task:\n- correctly spelled text\n')
        self.assertFalse(tab.editor._spelling_selections)
        self.settled(tab)
        self.assertFalse(tab.editor._spelling_selections)
        tab.editor.setPlainText('Task:\n- recieve text\n')
        self.settled(tab)
        self.assertEqual(len(tab.editor._spelling_selections), 1)
        tab.editor.setPlainText('Task:\n- `recieve` text\n')
        self.assertFalse(tab.editor._spelling_selections)
        self.settled(tab)
        self.assertFalse(tab.editor._spelling_selections)

    def test_context_identity_and_stale_error_are_guarded(self):
        tab = self.window.current()
        tab.editor.setPlainText('=> - Act')
        self.settled(tab)
        old_result, revision = tab.analysis, tab.controller.revision
        options = {'mode': ['one']}
        tab.set_analysis_context('unknown', profile='review', configuration=options)
        options['mode'].append('two')
        self.settled(tab)
        self.assertEqual(tab.configuration, {'mode': ['one']})
        self.assertEqual(tab.diagnostics.findings, ())
        tab._analysis_ready(revision, old_result)
        tab._analysis_failed(revision, 'stale failure')
        self.assertEqual(tab.analysis.document.session.arcgrav_version, 'unknown')
        self.assertNotIn('failed', tab.diagnostics_heading.toolTip())

    def test_highlight_interval_index_handles_overlap_boundaries_and_clear(self):
        highlighter = self.window.current().highlighter
        highlighter.ranges = ((0, 30, 'literal'), (5, 7, 'symbol'),
                              (20, 25, 'colon'), (30, 32, 'operation'))
        for start, end in [(0, 5), (7, 20), (25, 30), (30, 32), (40, 45)]:
            expected = tuple(r for r in highlighter.ranges if r[1] > start and r[0] < end)
            actual = tuple(r for r in highlighter.block_ranges(start, end)
                           if r[1] > start and r[0] < end)
            self.assertEqual(actual, expected)
        highlighter.ranges = tuple((i * 10, i * 10 + 2, 'colon') for i in range(10000))
        self.assertEqual(len(highlighter.block_ranges(90000, 90010)), 1)
        highlighter.ranges = ()
        self.assertEqual(highlighter.block_ranges(0, 100000), ())

    def test_large_document_visits_only_local_highlight_ranges(self):
        from AgStudio.gui.app import DocumentTab
        source = 'Scope: value\n\n[Source]: value\n' + '- Read [Source]\n' * 3000 + '\nTask: value\n'
        tab = DocumentTab('current')
        try:
            tab.editor.setPlainText(source)
            visits = []
            original = tab.highlighter.block_ranges
            def counted(start, end):
                spans = original(start, end)
                visits.append(len(spans))
                return spans
            tab._refreshing = True  # Match the production delivery reentrancy guard.
            try:
                with mock.patch.object(tab.highlighter, 'block_ranges', side_effect=counted):
                    tab.highlighter.rehighlight()
            finally:
                tab._refreshing = False
            self.assertGreater(len(visits), 3000)
            self.assertLessEqual(sum(visits), len(tab.highlighter.ranges))
            self.assertEqual(tab.diagnostics.findings, ())
        finally:
            tab.close()
            tab.deleteLater()

    def test_controlled_future_coalescing_stale_failure_and_closed_delivery(self):
        from concurrent.futures import Future
        from AgStudio.gui.analysis import AnalysisController
        controller = AnalysisController(worker=lambda source, **kwargs: analyze(source, **kwargs), delay_ms=1)
        futures = [Future(), Future(), Future()]
        delivered, failures = [], []
        controller.ready.connect(lambda revision, result: delivered.append((revision, result)))
        controller.failed.connect(lambda revision, error: failures.append((revision, error)))
        try:
            with mock.patch('AgStudio.gui.analysis._POOL.submit', side_effect=futures) as submit:
                controller.request('old', 'current')
                controller.timer.stop()
                controller._dispatch()
                for source in ['intermediate', 'latest']:
                    controller.request(source, 'current')
                    controller.timer.stop()
                    controller._dispatch()
                self.assertEqual(submit.call_count, 1)
                futures[0].set_exception(RuntimeError('stale failure'))
                controller._collect()
                self.assertEqual(submit.call_count, 2)
                self.assertEqual(submit.call_args.args[1], 'latest')
                self.assertEqual(failures, [])
                futures[1].set_result(analyze('latest'))
                controller._collect()
                self.assertEqual(len(delivered), 1)
                self.assertEqual(delivered[0][0], controller.revision)
                controller.request('closing', 'current')
                controller.timer.stop()
                controller._dispatch()
                futures[2].set_running_or_notify_cancel()
                controller.close()
                futures[2].set_result(analyze('closing'))
                controller._collect()
                self.assertEqual(len(delivered), 1)
                self.assertEqual(failures, [])
        finally:
            controller.close()
            controller.deleteLater()

    def test_pending_worker_does_not_block_event_loop_or_editing(self):
        from PySide6.QtCore import QTimer
        tab = self.window.current()
        started, release = threading.Event(), threading.Event()
        self.releases.append(release)
        def worker(source, **kwargs):
            started.set()
            release.wait(3)
            return analyze(source, **kwargs)
        tab.controller.worker = worker
        tab.editor.setPlainText('Scope: initial')
        self.wait_for(started.is_set)
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        tab.editor.insertPlainText('typed ')
        self.wait_for(lambda: bool(ticks))
        self.assertIn('typed ', tab.source)
        self.assertFalse(release.is_set())
        release.set()
        self.settled(tab)


if __name__ == '__main__':
    unittest.main()
