"""Production editor features: independent processes and stable stale rendering."""
from functools import partial
import importlib.util
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def _controlled_feature(snapshot, *, feature, marker=None, release=None, crash=False):
    """Qt-free spawn fixture: block only this feature, then use its real code."""
    if marker is not None:
        Path(marker).write_text(str(os.getpid()), encoding='ascii')
    if crash:
        os._exit(37)
    deadline = time.monotonic() + 20
    while release is not None and not Path(release).exists():
        # Genuine CPU work with no cooperative cancellation or GIL handoff.
        sum(index * index for index in range(10000))
        if time.monotonic() > deadline:
            raise TimeoutError('test did not release feature process')
    if feature == 'parse':
        from AgStudio.shared.analysis_snapshot import calculate_parse_snapshot
        return calculate_parse_snapshot(snapshot)
    if feature == 'findings':
        from AgStudio.shared.analysis_snapshot import calculate_analysis_snapshot
        return calculate_analysis_snapshot(snapshot)
    if feature == 'outline':
        from AgStudio.shared.panel_projections import derive_outline
        return derive_outline(snapshot)
    from AgStudio.shared.highlight_projection import derive_highlighting
    return derive_highlighting(snapshot)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class EditorFeatureProcessTests(unittest.TestCase):
    SOURCE = '[Root]:\n- Parent:\n  - Child\n=> - Act\nUse `two words`\n'

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def wait_for(self, predicate, timeout=15):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            QTest.qWait(5)
        self.fail('editor features did not reach the expected state')

    def workers(self, tab):
        return (tab.controller.process_worker, tab.outline_worker.worker,
                tab.highlight_worker.worker, tab.graph.worker, tab.controller.parser_worker)

    def close_tab(self, tab):
        from PySide6.QtCore import QCoreApplication, QEvent
        from shiboken6 import isValid
        workers = self.workers(tab) if tab.controller else (tab.graph.worker,)
        if isValid(tab):
            tab.close()
            tab.deleteLater()
            QCoreApplication.sendPostedEvents(tab, QEvent.Type.DeferredDelete)
        for worker in workers:
            worker.close()
            self.assertTrue(worker.wait_closed(10), 'feature child was not reaped')
            self.assertIsNone(worker.active_pid)

    def make_tab(self, source=None, *, background=True, map_enabled=False):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', source if source is not None else self.SOURCE,
                          background=background, map_enabled=map_enabled)
        self.addCleanup(self.close_tab, tab)
        tab.resize(1100, 700)
        tab.show()
        tab.side_panel.show()
        tab.ensure_outline()
        self.app.processEvents()
        if background:
            self.settled(tab)
        return tab

    def settled(self, tab):
        self.wait_for(lambda: tab.analysis is not None
                      and tab.diagnostics is not None
                      and tab.analysis.document.source == tab.source
                      and tab._outline_document_id == tab.document.document_id
                      and tab._findings_document_id == tab.document.document_id
                      and tab._highlight_document_id == tab.document.document_id
                      and tab._outline_current and tab._findings_current)

    def append(self, tab, text='\n'):
        # Editing with a separate cursor preserves the user's current caret.
        from PySide6.QtGui import QTextCursor
        cursor = QTextCursor(tab.editor.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)

    def marker(self, name):
        return Path(self.directory.name) / name

    def hold(self, worker, feature, suffix=''):
        started = self.marker(feature + suffix + '.started')
        release = self.marker(feature + suffix + '.release')
        calculation = partial(_controlled_feature, feature=feature,
                              marker=str(started), release=str(release))
        return patch.object(worker, '_calculation', calculation), started, release

    def test_four_features_and_parser_deliver_from_five_distinct_child_pids(self):
        tab = self.make_tab(map_enabled=True)
        self.wait_for(lambda: tab.graph.worker_pid is not None)
        pids = (tab.controller.worker_pid, tab.outline_worker.worker_pid,
                tab.highlight_worker.worker_pid, tab.graph.worker_pid, tab.controller.parser_pid)
        self.assertTrue(all(isinstance(pid, int) for pid in pids))
        self.assertEqual(len(set(pids + (os.getpid(),))), 6)
        self.assertTrue(tab._outline_items)
        self.assertGreater(tab.diagnostic_list.topLevelItemCount(), 0)
        self.assertTrue(tab.highlighter.ranges)
        self.assertTrue(all(worker.active_pid is None for worker in self.workers(tab)))

    def test_spelling_warning_process_retains_row_blocks_stale_actions_and_corrects(self):
        from PySide6.QtGui import QTextCursor
        source = 'Task:\n- 🌍 Please recieve text\n'
        tab = self.make_tab(source)
        self.assertNotEqual(tab.controller.worker_pid, os.getpid())
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 1)
        row = tab.diagnostic_list.topLevelItem(0)
        self.assertEqual((row.text(0), row.text(1), row.text(3), row.text(4)),
                         ('Warning', 'AG-SPELLING', '2', '12'))
        self.assertEqual(tab.diagnostic_count_labels['warning'].text(), '1')
        self.assertEqual(tab.editor.finding_severities, {2: 'warning'})
        tab._navigate_finding(row)
        self.assertEqual(tab.editor.textCursor().selectedText(), 'recieve')
        tab.diagnostic_list.setCurrentItem(row)
        start = tab.editor.textCursor().selectionStart()
        menu = tab.editor.spelling_context_menu(start)
        self.addCleanup(menu.deleteLater)
        target = tab.editor.spelling_target_at(start)
        self.assertNotIn('receive', [a.text() for a in menu.actions()])
        hold, started, release = self.hold(tab.controller.process_worker, 'findings')
        with hold:
            self.append(tab)
            tab.editor.moveCursor(QTextCursor.MoveOperation.End)
            position = tab.editor.textCursor().position()
            self.wait_for(started.exists)
            self.assertIs(tab.diagnostic_list.topLevelItem(0), row)
            self.assertEqual(tab.diagnostic_count_labels['warning'].text(), '1')
            self.assertFalse(tab._findings_current)
            tab._navigate_finding(row)
            tab.editor._replace_spelling(target.start, target.end, target.word, target.revision, 'receive')
            self.assertEqual(tab.editor.textCursor().position(), position)
            self.assertEqual(tab.source, source + '\n')
            release.touch()
            self.settled(tab)
        self.assertIs(tab.diagnostic_list.topLevelItem(0), row)
        self.assertIs(tab.diagnostic_list.currentItem(), row)
        tab._navigate_finding(row)
        self.assertEqual(tab.editor.textCursor().selectedText(), 'recieve')
        fresh_menu = tab.editor.spelling_context_menu(tab.editor.textCursor().selectionStart())
        self.addCleanup(fresh_menu.deleteLater)
        target = tab.editor.spelling_target_at(tab.editor.textCursor().selectionStart())
        tab.editor._replace_spelling(target.start, target.end, target.word, target.revision, 'receive')
        self.settled(tab)
        self.assertIn('receive text', tab.source)
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 0)
        self.assertEqual(tab.diagnostic_count_labels['warning'].text(), '0')
        self.assertFalse(tab.editor.finding_lines)
        self.assertFalse(tab.editor._spelling_ranges)

    def test_pending_keeps_rows_colors_selection_expansion_scroll_and_blocks_navigation(self):
        source = self.SOURCE + ''.join(f'Section {index}:\n- Value {index}\n=> - Act\n'
                                      for index in range(45))
        tab = self.make_tab(source)
        parent = next(item for item in tab._outline_items.values()
                      if item.text(0) == '- Parent:')
        parent.parent().setExpanded(True)
        parent.setExpanded(True)
        selected = parent.child(0)
        tab.outline.setCurrentItem(selected)
        finding = tab.diagnostic_list.topLevelItem(0)
        tab.diagnostic_list.setCurrentItem(finding)
        tab.outline.verticalScrollBar().setValue(8)
        tab.diagnostic_list.verticalScrollBar().setValue(8)
        self.app.processEvents()
        outline_scroll = tab.outline.verticalScrollBar().value()
        findings_scroll = tab.diagnostic_list.verticalScrollBar().value()
        outlines = dict(tab._outline_by_key)
        findings = dict(tab._finding_by_key)
        ranges = tab.highlighter.ranges
        counts = {key: label.text() for key, label in tab.diagnostic_count_labels.items()}
        hold, started, release = self.hold(tab.controller.parser_worker, 'parse')
        with hold:
            self.append(tab)
            self.assertIsNone(tab.document)
            self.assertEqual(tab._outline_by_key, outlines)
            self.assertEqual(tab._finding_by_key, findings)
            self.assertEqual(tab.highlighter.ranges, ranges)
            self.assertEqual({key: label.text() for key, label in tab.diagnostic_count_labels.items()}, counts)
            self.assertEqual(tab.outline_status.text(), '')
            self.assertEqual(tab.diagnostic_status.text(), '')
            self.assertTrue(tab.outline_spinner.isVisible())
            self.assertTrue(tab.diagnostic_spinner.isVisible())
            self.assertIn('stale', tab.outline_spinner.accessibleDescription())
            self.assertIn('stale', tab.diagnostic_spinner.accessibleDescription())
            position = tab.editor.textCursor().position()
            anchor = tab.editor.textCursor().anchor()
            tab._outline_clicked(parent)
            tab._navigate_finding(finding)
            self.assertEqual((tab.editor.textCursor().position(), tab.editor.textCursor().anchor()),
                             (position, anchor))
            self.wait_for(started.exists)
            self.assertIsNone(tab.document)
            release.touch()
            self.settled(tab)
        for key, item in outlines.items():
            self.assertIs(tab._outline_by_key[key], item)
        for key, item in findings.items():
            self.assertIs(tab._finding_by_key[key], item)
        self.assertIs(tab.outline.currentItem(), selected)
        self.assertIs(tab.diagnostic_list.currentItem(), finding)
        self.assertTrue(parent.isExpanded())
        self.assertEqual(tab.outline.verticalScrollBar().value(), outline_scroll)
        self.assertEqual(tab.diagnostic_list.verticalScrollBar().value(), findings_scroll)

    def test_slow_outline_and_highlighting_do_not_block_sibling_or_event_loop(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        for feature, other_id in (('outline', '_highlight_document_id'),
                                  ('highlighting', '_outline_document_id')):
            with self.subTest(feature=feature):
                tab = self.make_tab()
                controller = tab.outline_worker if feature == 'outline' else tab.highlight_worker
                old_id = tab.document.document_id
                old_rows = tuple(tab._outline_items.values())
                old_ranges = tab.highlighter.ranges
                hold, started, release = self.hold(controller.worker, feature)
                ticks = []
                timer = QTimer(tab)
                timer.setInterval(5)
                timer.timeout.connect(lambda: ticks.append(time.monotonic()))
                timer.start()
                with hold:
                    self.append(tab, '\nNew section:\n- New value\n')
                    self.wait_for(started.exists)
                    self.wait_for(lambda: tab.document is not None
                                  and tab._findings_document_id == tab.document.document_id
                                  and getattr(tab, other_id) == tab.document.document_id)
                    self.assertNotEqual(tab.document.document_id, old_id)
                    self.assertTrue(controller.worker.busy)
                    if feature == 'outline':
                        self.assertEqual(tab._outline_document_id, old_id)
                        self.assertEqual(tuple(tab._outline_items.values()), old_rows)
                        position = tab.editor.textCursor().position()
                        tab._outline_clicked(old_rows[0])
                        self.assertEqual(tab.editor.textCursor().position(), position)
                    else:
                        self.assertEqual(tab._highlight_document_id, old_id)
                        self.assertTrue(set(old_ranges).issubset(set(tab.highlighter.ranges)))
                    before = len(ticks)
                    QTest.qWait(60)
                    self.assertGreater(len(ticks), before + 2)
                    release.touch()
                    self.settled(tab)
                timer.stop()

    def test_feature_crashes_are_local_and_next_edit_recovers(self):
        for feature in ('outline', 'highlighting'):
            with self.subTest(feature=feature):
                tab = self.make_tab()
                controller = tab.outline_worker if feature == 'outline' else tab.highlight_worker
                errors = []
                controller.failed.connect(lambda *args: errors.append(args))
                old_id = tab.document.document_id
                old_rows = tuple(tab._outline_items.values())
                other_id = '_highlight_document_id' if feature == 'outline' else '_outline_document_id'
                crash = partial(_controlled_feature, feature=feature, crash=True)
                with patch.object(controller.worker, '_calculation', crash):
                    self.append(tab)
                    self.wait_for(lambda: errors and tab.document is not None
                                  and getattr(tab, other_id) == tab.document.document_id
                                  and tab._findings_current
                                  and tab._findings_document_id == tab.document.document_id)
                    self.assertIn('exit code 37', errors[0][1])
                    self.assertEqual(tab._findings_document_id, tab.document.document_id)
                    if feature == 'outline':
                        self.assertEqual(tab._outline_document_id, old_id)
                        self.assertEqual(tuple(tab._outline_items.values()), old_rows)
                        self.assertIn('unavailable', tab.outline_status.text())
                    else:
                        self.assertEqual(tab._highlight_document_id, old_id)
                        self.assertIn('unavailable', tab.editor.toolTip())
                self.append(tab)
                self.settled(tab)
                if feature == 'highlighting':
                    self.assertNotIn('unavailable', tab.editor.toolTip())

    def test_findings_crash_retains_its_rows_while_other_features_complete_and_recovers(self):
        tab = self.make_tab()
        findings = dict(tab._finding_by_key)
        errors = []
        tab.controller.failed.connect(lambda *args: errors.append(args))
        crash = partial(_controlled_feature, feature='findings', crash=True)
        with patch.object(tab.controller.process_worker, '_calculation', crash):
            self.append(tab)
            self.wait_for(lambda: errors and tab.document is not None
                          and tab._outline_document_id == tab.document.document_id
                          and tab._highlight_document_id == tab.document.document_id)
            self.assertIn('exit code 37', errors[0][1])
            self.assertIsNone(tab.diagnostics)
            self.assertEqual(tab._finding_by_key, findings)
            self.assertIn('unavailable', tab.diagnostic_status.text())
        self.append(tab)
        self.settled(tab)

    def test_slow_findings_does_not_delay_outline_highlighting_or_map(self):
        tab = self.make_tab(map_enabled=True)
        self.wait_for(lambda: tab.graph.worker_pid is not None)
        findings = dict(tab._finding_by_key)
        old_id = tab._findings_document_id
        hold, started, release = self.hold(tab.controller.process_worker, 'findings')
        with hold:
            self.append(tab, '\nNew section:\n- New value\n')
            self.wait_for(started.exists)
            self.wait_for(lambda: tab.document is not None
                          and tab._outline_document_id == tab.document.document_id
                          and tab._highlight_document_id == tab.document.document_id
                          and tab.graph.worker_pid is not None)
            self.assertTrue(tab.controller.process_worker.busy)
            self.assertFalse(tab.outline_spinner.pending)
            self.assertFalse(tab.outline_spinner.timer.isActive())
            self.assertTrue(tab.diagnostic_spinner.pending)
            self.assertTrue(tab.diagnostic_spinner.timer.isActive())
            self.assertIsNone(tab.diagnostics)
            self.assertNotEqual(tab.document.document_id, old_id)
            self.assertEqual(tab._findings_document_id, old_id)
            self.assertEqual(tab._finding_by_key, findings)
            position = tab.editor.textCursor().position()
            tab._navigate_finding(next(iter(findings.values())))
            self.assertEqual(tab.editor.textCursor().position(), position)
            release.touch()
            self.settled(tab)

    def test_same_source_refresh_does_not_authorize_old_actions_by_document_id(self):
        tab = self.make_tab()
        old_id = tab.document.document_id
        outline = next(iter(tab._outline_items.values()))
        finding = tab.diagnostic_list.topLevelItem(0)
        outline_hold, outline_started, outline_release = self.hold(
            tab.outline_worker.worker, 'outline')
        findings_hold, findings_started, findings_release = self.hold(
            tab.controller.process_worker, 'findings')
        with outline_hold, findings_hold:
            tab.refresh_model()
            self.wait_for(lambda: outline_started.exists() and findings_started.exists())
            self.assertIsNotNone(tab.document)
            self.assertEqual(tab.document.document_id, old_id)
            self.assertEqual(tab._outline_document_id, old_id)
            self.assertEqual(tab._findings_document_id, old_id)
            self.assertFalse(tab._outline_current)
            self.assertFalse(tab._findings_current)
            cursor = tab.editor.textCursor()
            cursor.setPosition(len(tab.editor.toPlainText()))
            tab.editor.setTextCursor(cursor)
            before = (cursor.position(), cursor.anchor())
            tab._outline_clicked(outline)
            tab._navigate_finding(finding)
            after = tab.editor.textCursor()
            self.assertEqual((after.position(), after.anchor()), before)
            outline_release.touch()
            findings_release.touch()
            self.settled(tab)

    def test_multiple_tabs_churn_process_stages_without_losing_supervisors(self):
        from PySide6.QtTest import QTest
        tabs = [self.make_tab(map_enabled=True), self.make_tab(map_enabled=True)]
        for revision in range(6):
            for index, tab in enumerate(tabs):
                self.append(tab, f'\nStage {revision} tab {index}:\n')
                tab.controller.timer.start(0)
            # Publish common parses, then replace the source while downstream
            # processes from both tabs are starting, returning or being reaped.
            self.wait_for(lambda: all(tab.document is not None for tab in tabs))
            QTest.qWait(10)
        for tab in tabs:
            self.settled(tab)
            self.wait_for(lambda: tab.graph.worker_pid is not None)
            self.assertEqual(tab.analysis.document.source, tab.source)
            self.assertTrue(all(worker._thread.is_alive() for worker in self.workers(tab)))
            self.assertTrue(all(worker.active_pid is None for worker in self.workers(tab)))

    def test_rapid_typing_undo_redo_and_caret_do_not_run_inline_derivation(self):
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
        tab = self.make_tab()
        ready_sources = []
        tab.controller.ready.connect(lambda revision, result: ready_sources.append(result.document.source))
        workers = self.workers(tab)[:3]
        with patch('AgStudio.gui.app.analyze', side_effect=AssertionError('inline analysis')), \
                patch('AgStudio.gui.app.derive_outline', side_effect=AssertionError('inline outline')), \
                patch('AgStudio.gui.app.derive_findings', side_effect=AssertionError('inline findings')), \
                patch('AgStudio.gui.app.derive_highlighting', side_effect=AssertionError('inline highlighting')), \
                patch.object(workers[0], 'submit', wraps=workers[0].submit) as findings_submit, \
                patch.object(workers[1], 'submit', wraps=workers[1].submit) as outline_submit, \
                patch.object(workers[2], 'submit', wraps=workers[2].submit) as highlight_submit:
            tab.editor.moveCursor(QTextCursor.MoveOperation.End)
            for text in ('\n', 'Latest', ':', '\n', '- Keep'):
                tab.editor.insertPlainText(text)
            expected = tab.source
            tab.editor.undo()
            self.assertNotEqual(tab.source, expected)
            tab.editor.redo()
            self.assertEqual(tab.source, expected)
            self.settled(tab)
            self.assertEqual(ready_sources, [expected])
            self.assertEqual(tab.analysis.document.source, expected)
            revision = tab.controller.revision
            counts = (findings_submit.call_count, outline_submit.call_count, highlight_submit.call_count)
            projection = tab.highlighter._projection
            for position in (0, 2, 8, 0):
                cursor = tab.editor.textCursor()
                cursor.setPosition(position)
                tab.editor.setTextCursor(cursor)
            QTest.qWait(250)
            self.assertEqual(tab.controller.revision, revision)
            self.assertEqual((findings_submit.call_count, outline_submit.call_count,
                              highlight_submit.call_count), counts)
            self.assertIs(tab.highlighter._projection, projection)

    def test_close_reaps_both_active_feature_processes_without_waiting_on_gui(self):
        tab = self.make_tab()
        outline_hold, outline_started, _ = self.hold(tab.outline_worker.worker, 'outline')
        highlight_hold, highlight_started, _ = self.hold(tab.highlight_worker.worker, 'highlighting')
        with outline_hold, highlight_hold:
            self.append(tab)
            self.wait_for(lambda: outline_started.exists() and highlight_started.exists())
            pids = (tab.outline_worker.worker.active_pid, tab.highlight_worker.worker.active_pid)
            self.assertEqual(len(set(pids)), 2)
            started = time.monotonic()
            tab.close()
            self.assertLess(time.monotonic() - started, 0.25)
            for worker in self.workers(tab):
                self.assertTrue(worker.closed)
                self.assertTrue(worker.wait_closed(10))
                self.assertIsNone(worker.active_pid)
            active = [child.pid for child in multiprocessing.active_children()]
            self.assertTrue(all(pid not in active for pid in pids))

    def test_explicit_nonbackground_mode_still_has_synchronous_results(self):
        tab = self.make_tab(background=False)
        self.assertIsNone(tab.controller)
        self.assertIsNone(tab.outline_worker)
        self.assertIsNone(tab.highlight_worker)
        self.assertIsNotNone(tab.analysis)
        self.assertEqual(tab._outline_document_id, tab.document.document_id)
        self.assertEqual(tab._highlight_document_id, tab.document.document_id)
        self.assertTrue(tab._outline_items)
        self.assertTrue(tab.highlighter.ranges)
        self.append(tab, '\nNew section:\n')
        self.assertEqual(tab.analysis.document.source, tab.source)
        self.assertEqual(tab._outline_document_id, tab.document.document_id)


if __name__ == '__main__':
    unittest.main()
