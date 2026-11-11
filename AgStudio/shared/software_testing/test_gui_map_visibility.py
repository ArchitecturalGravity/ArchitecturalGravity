"""View-disabled inference maps do no scoring or geometry, without stopping lint."""
from concurrent.futures import Future
from functools import partial
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from AgStudio.shared.software_testing.graph_worker_fixtures import slow_graph

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class ManualGraphWorker:
    """Expose late outcomes that an already-cancelled worker cannot publish."""
    def __init__(self):
        self.submissions = []
        self.outcomes = []
        self.active = None
        self.cancel_count = 0
        self.closed = False

    @property
    def busy(self):
        return self.active is not None

    def submit(self, revision, snapshot):
        self.submissions.append((revision, snapshot))
        self.active = revision

    def cancel(self):
        self.cancel_count += 1
        self.active = None

    def poll(self):
        if not self.outcomes:
            return None
        outcome = self.outcomes.pop(0)
        if outcome.revision == self.active:
            self.active = None
        return outcome

    def close(self):
        self.closed = True
        self.cancel()


class InferenceHeatCancellationTests(unittest.TestCase):
    def test_relation_scoring_cancels_during_graph_traversal(self):
        from AgStudio.gui.inference_heat import HeatCancelled, score_relations
        occurrences = tuple((index, index - 1) for index in range(1, 500))
        checks = 0
        # Let adjacency construction finish, then interrupt the first traversal.
        stop_at = 2 * len(occurrences) + 20
        def cancelled():
            nonlocal checks
            checks += 1
            return checks >= stop_at
        with self.assertRaises(HeatCancelled):
            score_relations(range(500), occurrences, cancelled=cancelled)
        self.assertEqual(checks, stop_at)

    def test_heat_preparation_checks_cancellation_after_it_starts(self):
        from AgStudio.gui.inference_heat import HeatCancelled, compute_heat
        from AgStudio.shared.lint import analyze
        source = '[A0]: value\n' + ''.join(
            f'[A{index}]:\n- [A{index - 1}]\n' for index in range(1, 30))
        result = analyze(source)
        checks = 0
        def cancelled():
            nonlocal checks
            checks += 1
            return checks >= 10
        with self.assertRaises(HeatCancelled):
            compute_heat(result.tree, result.semantics, cancelled=cancelled)
        self.assertEqual(checks, 10)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class InferenceMapVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, condition, timeout=5):
        from PySide6.QtTest import QTest
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            QTest.qWait(10)
        self.assertTrue(condition(), 'map or analysis did not reach expected state')

    def wait_heat(self, tab):
        try:
            self.wait_for(lambda: tab.document_map._heat_ready)
        except AssertionError:
            graph = tab.graph
            self.fail(f'graph did not publish: enabled={graph.enabled}, '
                      f'closed={graph.closed}, revision={graph.revision}, epoch={graph.epoch}, '
                      f'polling={graph.poll.isActive()}, running={graph.running}, '
                      f'pending={graph.pending is not None}, submitted={graph._submitted}, '
                      f'busy={graph.worker.busy}, pid={getattr(graph.worker, "active_pid", None)}, '
                      f'heat={graph.heat is not None}, error={tab.document_map.error}, '
                      f'geometry_timer={tab.document_map._timer.isActive()}')

    def make_tab(self, source='', **kwargs):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', source, **kwargs)
        tab.resize(1000, 620)
        tab.show()
        self.app.processEvents()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.close)
        return tab

    def settle(self, tab):
        self.wait_for(lambda: tab.analysis is not None
                      and tab.diagnostics is not None
                      and tab.analysis.document.source == tab.source
                      and (tab.controller is None
                           or (tab.controller.running is None
                               and tab.controller.pending is None)))

    def assert_current_diagnostics(self, tab):
        from AgStudio.shared.lint import analyze
        expected = analyze(tab.source)
        self.assertEqual(tab.analysis.as_record(), expected.as_record())
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(),
                         len(expected.diagnostics.findings))
        self.assertEqual(tab.diagnostic_status.text(), '')

    def test_saved_hidden_startup_open_and_new_tabs_never_score_or_build_geometry(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMessageBox
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        from AgStudio.gui.document_map import DocumentMap
        from AgStudio.gui.user_state import UserState
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = QSettings(str(root / 'settings.ini'), QSettings.Format.IniFormat)
            UserState(settings).set_panel('document_map', False)
            source_file = root / 'source.arc'
            source_file.write_text('=> - Act\n', encoding='utf-8')
            with patch('AgStudio.gui.graph_analysis.build_graph_snapshot') as prepare, \
                    patch('AgStudio.gui.graph_analysis.GraphWorker.submit') as submit, \
                    patch.object(DocumentMap, '_geometry') as geometry:
                window = StudioWindow('current', background=False,
                                      user_state=UserState(settings),
                                      scheme_store=SchemeStore(root / 'schemes'))
                try:
                    window.initialize_startup(source_file, settings=settings)
                    window.show()
                    opened = window.current()
                    self.assert_current_diagnostics(opened)
                    window.new_document()
                    window._restore_current_layout()
                    QTest.qWait(60)
                    self.assertFalse(window.panel_actions['document_map'].isChecked())
                    for index in range(window.tabs.count()):
                        tab = window.tabs.widget(index)
                        self.assertTrue(tab.document_map.isHidden())
                        self.assertIsNone(tab.document_map.heat)
                        self.assertFalse(tab.document_map._timer.isActive())
                        self.assertEqual(tab.document_map.rebuild_count, 0)
                    prepare.assert_not_called()
                    submit.assert_not_called()
                    geometry.assert_not_called()
                finally:
                    with patch.object(QMessageBox, 'question',
                                      return_value=QMessageBox.StandardButton.Yes):
                        window.close()
                    window.deleteLater()
                    self.app.processEvents()

    def test_disabled_map_rejects_direct_models_and_explicit_geometry_rebuilds(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest
        from AgStudio.gui.document_map import MAP_HELP
        from AgStudio.shared.lint import analyze
        tab = self.make_tab('Task: initial\n', map_enabled=False)
        m = tab.document_map
        result = analyze('[A]: value\n[B]:\n- [A]\n')
        with patch('AgStudio.gui.document_map.parse') as parse, \
                patch('AgStudio.gui.graph_analysis.build_graph_snapshot') as prepare, \
                patch.object(tab.graph.worker, 'submit') as submit, \
                patch.object(m, '_geometry') as geometry:
            m.set_model(result.document, result.tree, heat=object())
            m.schedule_rebuild()
            m.rebuild()
            tab.resize(1100, 680)
            tab.editor.insertPlainText(' more')
            QTest.qWait(60)
            parse.assert_not_called()
            prepare.assert_not_called()
            submit.assert_not_called()
            geometry.assert_not_called()
        self.assertEqual(m.rebuild_count, 0)
        self.assertFalse(m._timer.isActive())
        self.assertIsNone(m.heat)
        self.assertEqual(m.tooltip_at(QPoint()), MAP_HELP)
        self.assert_current_diagnostics(tab)

    def test_view_action_disables_every_tab_and_new_tabs_inherit_the_choice(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMessageBox
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        from AgStudio.gui.document_map import DocumentMap
        from AgStudio.gui.user_state import UserState
        with tempfile.TemporaryDirectory() as directory:
            window = StudioWindow('current', background=False, user_state=UserState(),
                                  scheme_store=SchemeStore(Path(directory)))
            try:
                first = window.current()
                second = window.new_document()
                window.show()
                window.panel_actions['document_map'].trigger()
                with patch('AgStudio.gui.graph_analysis.build_graph_snapshot') as prepare, \
                        patch.object(DocumentMap, '_geometry') as geometry:
                    third = window.new_document()
                    tabs = (first, second, third)
                    for tab in tabs:
                        tab.editor.setPlainText('[A]: value\n[B]:\n- [A]\n')
                        self.assertTrue(tab.document_map.isHidden())
                        self.assert_current_diagnostics(tab)
                    QTest.qWait(60)
                    prepare.assert_not_called()
                    geometry.assert_not_called()
                window.panel_actions['document_map'].trigger()
                for tab in tabs:
                    # Inactive tabs retain the View preference and are ready
                    # when selected; ancestor visibility is not the setting.
                    self.assertFalse(tab.document_map.isHidden())
                    self.wait_heat(tab)
                    tab.document_map.rebuild()
                    self.assertEqual(tab.document_map._heat_range, (1, 1))
            finally:
                with patch.object(QMessageBox, 'question',
                                  return_value=QMessageBox.StandardButton.Yes):
                    window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_synchronous_hidden_edits_keep_diagnostics_and_reveal_latest_graph(self):
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
        source = '[A]: value\n[B]:\n- [A] [A] [A]\n'
        tab = self.make_tab(source)
        self.wait_heat(tab)
        tab.document_map.rebuild()
        self.assertEqual(tab.document_map._heat_range, (1, 3))
        cursor = tab.editor.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
        tab.editor.setTextCursor(cursor)
        before = (tab.source, tab.dirty, cursor.position(), cursor.anchor(),
                  tab.editor.document().isUndoAvailable())
        analysis = tab.analysis
        tab.set_map_enabled(False)
        self.assertIs(tab.analysis, analysis)
        self.assertEqual((tab.source, tab.dirty, tab.editor.textCursor().position(),
                          tab.editor.textCursor().anchor(),
                          tab.editor.document().isUndoAvailable()), before)
        rebuilds = tab.document_map.rebuild_count
        with patch('AgStudio.gui.graph_analysis.build_graph_snapshot') as prepare, \
                patch.object(tab.document_map, '_geometry') as geometry:
            tab.editor.setPlainText('=> - Act\n')
            self.assert_current_diagnostics(tab)
            self.assertGreater(tab.diagnostic_list.topLevelItemCount(), 0)
            tab.editor.setPlainText('[A]: value\n[B]:\n- [A]\n')
            self.assert_current_diagnostics(tab)
            QTest.qWait(60)
            prepare.assert_not_called()
            geometry.assert_not_called()
        self.assertEqual(tab.document_map.rebuild_count, rebuilds)
        latest_analysis = tab.analysis
        tab.set_map_enabled(True)
        self.wait_heat(tab)
        tab.document_map.rebuild()
        self.assertIs(tab.analysis, latest_analysis)
        self.assertIs(tab.document_map._document, tab.document)
        self.assertEqual(tab.document_map._heat_range, (1, 1))
        self.assertEqual(tab.document_map._document_influence, 2)

    def test_hidden_background_edits_keep_diagnostics_and_resume_worker_scoring(self):
        from AgStudio.gui.graph_analysis import build_graph_snapshot
        with patch('AgStudio.gui.graph_analysis.build_graph_snapshot',
                   wraps=build_graph_snapshot) as prepare:
            tab = self.make_tab('=> - Old\n', background=True, map_enabled=False)
            self.settle(tab)
            self.assert_current_diagnostics(tab)
            tab.editor.setPlainText('[A]: value\n[B]:\n- [A]\n')
            self.settle(tab)
            self.assert_current_diagnostics(tab)
            prepare.assert_not_called()
            self.assertEqual(tab.document_map.rebuild_count, 0)
            latest_analysis = tab.analysis
            with patch.object(tab.controller, 'request',
                              side_effect=AssertionError('show must reuse existing diagnostics')):
                tab.set_map_enabled(True)
                self.wait_heat(tab)
            self.assertIs(tab.analysis, latest_analysis)
            prepare.assert_not_called()
            self.assertNotEqual(tab.graph.worker_pid, os.getpid())
            self.assertIs(tab.controller.graph, tab.graph)
            self.assertIs(tab.controller.heat, tab.document_map.heat)
            self.assertEqual(tab.document_map._heat_range, (1, 1))
            self.assert_current_diagnostics(tab)

    def test_rapid_off_on_off_while_lint_runs_skips_heat_and_keeps_current_diagnostics(self):
        from AgStudio.shared.lint import analyze
        tab = self.make_tab('', background=True, map_enabled=False)
        self.settle(tab)
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def worker(source, **options):
            started.set()
            release.wait(4)
            return analyze(source, **options)

        tab.controller.worker = worker
        with patch('AgStudio.gui.graph_analysis.build_graph_snapshot') as prepare:
            tab.editor.setPlainText('=> - Pending\n')
            self.wait_for(started.is_set)
            tab.set_map_enabled(True)
            tab.set_map_enabled(False)
            tab.set_map_enabled(True)
            tab.editor.setPlainText('=> - Latest\n')
            tab.set_map_enabled(False)
            release.set()
            self.settle(tab)
            self.assert_current_diagnostics(tab)
            prepare.assert_not_called()
            self.assertIsNone(tab.document_map.heat)
            self.assertIsNone(tab.controller.heat)
            self.assertFalse(tab.document_map._timer.isActive())

    def test_completed_lint_after_disable_publishes_diagnostics_without_graph_work(self):
        from AgStudio.gui.analysis import AnalysisController
        from AgStudio.shared.lint import analyze
        controller = AnalysisController(worker=lambda source, **kwargs: analyze(source, **kwargs), delay_ms=1)
        self.addCleanup(controller.deleteLater)
        self.addCleanup(controller.close)
        future = Future()
        delivered = []
        controller.ready.connect(lambda revision, result: delivered.append(result))
        result = analyze('=> - Act\n')
        with patch('AgStudio.gui.analysis._POOL.submit', return_value=future), \
                patch('AgStudio.gui.graph_analysis.build_graph_snapshot') as prepare:
            controller.request(result.document.source, 'current')
            controller.timer.stop()
            controller._dispatch()
            controller.graph.set_enabled(False)
            future.set_result(result)
            controller._collect()
            self.app.processEvents()
        self.assertEqual(delivered, [result])
        self.assertIs(controller.prepared_analysis, result)
        self.assertIsNone(controller.heat)
        prepare.assert_not_called()

    def test_slow_graph_process_does_not_block_current_diagnostics_or_gui_events(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        from AgStudio.shared.graph.worker import GraphWorker
        # Both the regular UI and the synchronous-lint test mode must keep graph
        # calculation asynchronous and out of the GUI interpreter process.
        for background in (False, True):
            with self.subTest(background=background), tempfile.TemporaryDirectory() as directory:
                started = Path(directory) / 'started'
                release = Path(directory) / 'release'
                worker = GraphWorker(calculation=partial(
                    slow_graph, started_path=str(started), release_path=str(release)))
                self.addCleanup(worker.close)
                with patch('AgStudio.gui.graph_analysis.GraphWorker', return_value=worker):
                    tab = self.make_tab('=> - Old\n', background=background, map_enabled=False)
                self.settle(tab)
                ticks = []
                timer = QTimer(tab)
                timer.setInterval(10)
                timer.timeout.connect(lambda: ticks.append(time.monotonic()))
                timer.start()
                try:
                    tab.set_map_enabled(True)
                    self.wait_for(lambda: started.exists() and bool(started.read_text().strip()))
                    self.assertNotEqual(int(started.read_text().splitlines()[0]), os.getpid())
                    self.assertTrue(worker.busy)
                    self.assertIsNone(tab.document_map.heat)
                    latest = '=> - Latest\n[A]: value\n[B]:\n- [A]\n'
                    before = len(ticks)
                    tab.editor.setPlainText(latest)
                    self.settle(tab)
                    self.assert_current_diagnostics(tab)
                    self.assertGreater(tab.diagnostic_list.topLevelItemCount(), 0)
                    self.assertIsNone(tab.document_map.heat)
                    QTest.qWait(120)
                    self.assertGreaterEqual(len(ticks) - before, 3)
                    self.wait_for(lambda: len(started.read_text().splitlines()) == 2)
                    self.assertFalse(release.exists())
                    release.touch()
                    self.wait_heat(tab)
                    self.assertEqual(tab.document_map._document.source, latest)
                    self.assertEqual(tab.document_map._heat_range, (0, 1))
                    self.assertEqual(tab.document_map._document_influence, 2)
                finally:
                    timer.stop()
                    release.touch()
                    tab.close()
                    worker.close()
                    self.assertTrue(worker.wait_closed(5), 'graph process was not reaped on close')

    def test_hide_cancels_active_process_and_reopen_computes_only_latest_analysis(self):
        from PySide6.QtTest import QTest
        from AgStudio.shared.graph.worker import GraphWorker
        with tempfile.TemporaryDirectory() as directory:
            started = Path(directory) / 'started'
            release = Path(directory) / 'release'
            worker = GraphWorker(calculation=partial(
                slow_graph, started_path=str(started), release_path=str(release)))
            self.addCleanup(worker.close)
            with patch('AgStudio.gui.graph_analysis.GraphWorker', return_value=worker):
                tab = self.make_tab('[A]: old\n[B]:\n- [A] [A] [A]\n',
                                    background=True, map_enabled=False)
            self.settle(tab)
            tab.set_map_enabled(True)
            self.wait_for(lambda: started.exists() and bool(started.read_text().strip()))
            tab.set_map_enabled(False)
            self.assertFalse(worker.busy)
            self.wait_for(lambda: worker.active_pid is None)
            self.assertFalse(release.exists())
            self.assertIsNone(tab.graph.heat)
            self.assertIsNone(tab.document_map.heat)
            self.assertFalse(tab.document_map._timer.isActive())
            with patch('AgStudio.gui.graph_analysis.build_graph_snapshot') as prepare:
                tab.editor.setPlainText('=> - Intermediate\n')
                self.settle(tab)
                latest = '[A]: value\n[B]:\n- [A]\n'
                tab.editor.setPlainText(latest)
                self.settle(tab)
                self.assert_current_diagnostics(tab)
                QTest.qWait(80)
                prepare.assert_not_called()
                self.assertEqual(len(started.read_text().splitlines()), 1)
            analysis = tab.analysis
            release.touch()
            with patch.object(tab.controller, 'request',
                              side_effect=AssertionError('reopen must not rerun diagnostics')):
                tab.set_map_enabled(True)
                self.wait_heat(tab)
            self.assertIs(tab.analysis, analysis)
            self.assertIs(tab.graph.analysis, tab.controller.parsed_analysis)
            self.assertEqual(tab.graph.analysis.document.document_id, analysis.document.document_id)
            self.assertEqual(tab.document_map._document.source, latest)
            self.assertEqual(tab.document_map._heat_range, (1, 1))
            self.assertEqual(tab.document_map._document_influence, 2)
            self.assertEqual(len(started.read_text().splitlines()), 2)
            tab.close()
            self.assertTrue(worker.wait_closed(5), 'graph process was not reaped on close')

    def test_late_pre_hide_success_and_failure_cannot_publish_after_reenable(self):
        from AgStudio.gui.graph_analysis import GraphController
        from AgStudio.shared.graph import calculate_graph
        from AgStudio.shared.graph.worker import GraphOutcome
        from AgStudio.shared.lint import analyze
        worker = ManualGraphWorker()
        controller = GraphController(worker=worker)
        self.addCleanup(controller.deleteLater)
        self.addCleanup(controller.close)
        ready, failed = [], []
        controller.ready.connect(lambda revision, heat: ready.append((revision, heat)))
        controller.failed.connect(lambda revision, error: failed.append((revision, error)))
        old = analyze('[A]: old\n[B]:\n- [A] [A] [A]\n')
        latest = analyze('[A]: latest\n[B]:\n- [A]\n')
        controller.set_analysis(1, old)
        self.wait_for(lambda: len(worker.submissions) == 1)
        old_epoch, old_snapshot = worker.submissions[0]
        controller.set_enabled(False)
        controller.set_analysis(2, latest)
        controller.set_enabled(True)
        self.wait_for(lambda: len(worker.submissions) == 2)
        latest_epoch, latest_snapshot = worker.submissions[1]
        self.assertNotEqual(old_epoch, latest_epoch)
        worker.outcomes.extend((GraphOutcome(old_epoch, result=calculate_graph(old_snapshot)),
                                GraphOutcome(old_epoch, error='obsolete failure')))
        controller._collect()
        controller._collect()
        self.assertEqual(ready, [])
        self.assertEqual(failed, [])
        self.assertIsNone(controller.heat)
        expected = calculate_graph(latest_snapshot)
        worker.outcomes.append(GraphOutcome(latest_epoch, result=expected))
        controller._collect()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0][0], 2)
        self.assertEqual(controller.heat.scores, dict(expected.scores))
        self.assertEqual(controller.heat.relations, expected.relations)
        self.assertIs(controller.analysis, latest)
        controller.close()
        self.assertTrue(worker.closed)

    def test_late_snapshot_preparation_cannot_submit_or_fail_after_hide_and_new_edit(self):
        from AgStudio.gui.graph_analysis import GraphController
        from AgStudio.shared.graph.adapter import build_graph_snapshot
        from AgStudio.shared.lint import analyze
        old = analyze('[A]: old\n[B]:\n- [A] [A] [A]\n')
        latest = analyze('[A]: latest\n[B]:\n- [A]\n')
        old_snapshot = build_graph_snapshot(old.tree, old.semantics)
        latest_snapshot = build_graph_snapshot(latest.tree, latest.semantics)
        for obsolete_failure in (False, True):
            with self.subTest(obsolete_failure=obsolete_failure):
                worker = ManualGraphWorker()
                controller = GraphController(worker=worker)
                self.addCleanup(controller.deleteLater)
                self.addCleanup(controller.close)
                first, second = Future(), Future()
                first.set_running_or_notify_cancel()
                failures = []
                controller.failed.connect(lambda revision, error: failures.append(error))
                with patch('AgStudio.gui.graph_analysis._PREPARATION_POOL.submit',
                           side_effect=(first, second)) as prepare:
                    controller.set_analysis(1, old)
                    controller.set_enabled(False)
                    controller.set_analysis(2, latest)
                    controller.set_enabled(True)
                    if obsolete_failure:
                        first.set_exception(RuntimeError('obsolete preparation failed'))
                    else:
                        first.set_result(old_snapshot)
                    controller._collect()
                    self.assertEqual(worker.submissions, [])
                    self.assertEqual(failures, [])
                    self.assertEqual(prepare.call_count, 2)
                    second.set_result(latest_snapshot)
                    controller._collect()
                self.assertEqual(worker.submissions, [(controller.epoch, latest_snapshot)])
                self.assertIs(controller.analysis, latest)
                controller.close()

    def test_process_completion_between_poll_and_idle_check_still_publishes(self):
        from AgStudio.gui.graph_analysis import GraphController
        from AgStudio.shared.graph import calculate_graph
        from AgStudio.shared.graph.worker import GraphOutcome
        from AgStudio.shared.lint import analyze

        class JustCompletedWorker(ManualGraphWorker):
            staged = False

            def poll(self):
                if self.submissions and not self.staged:
                    revision, snapshot = self.submissions[-1]
                    self.outcomes.append(GraphOutcome(revision, result=calculate_graph(snapshot)))
                    self.active = None
                    self.staged = True
                    # Model a supervisor finishing immediately after poll took
                    # its empty result, before the controller checks busy.
                    return None
                return super().poll()

        worker = JustCompletedWorker()
        controller = GraphController(worker=worker)
        self.addCleanup(controller.deleteLater)
        self.addCleanup(controller.close)
        ready = []
        controller.ready.connect(lambda revision, heat: ready.append((revision, heat)))
        controller.set_analysis(3, analyze('[A]: value\n[B]:\n- [A]\n'))
        self.wait_for(lambda: bool(ready))
        self.assertTrue(worker.staged)
        self.assertEqual([revision for revision, _ in ready], [3])
        self.assertEqual(sum(score.total for score in ready[0][1].scores.values()), 2)

    def test_same_revision_reenable_rejects_previous_graph_epoch(self):
        from AgStudio.gui.graph_analysis import GraphController
        from AgStudio.shared.graph import calculate_graph
        from AgStudio.shared.graph.worker import GraphOutcome
        from AgStudio.shared.lint import analyze
        worker = ManualGraphWorker()
        controller = GraphController(worker=worker)
        self.addCleanup(controller.deleteLater)
        self.addCleanup(controller.close)
        ready, failed = [], []
        controller.ready.connect(lambda revision, heat: ready.append((revision, heat)))
        controller.failed.connect(lambda revision, error: failed.append(error))
        analysis = analyze('[A]: value\n[B]:\n- [A]\n')
        controller.set_analysis(7, analysis)
        self.wait_for(lambda: len(worker.submissions) == 1)
        old_epoch, snapshot = worker.submissions[0]
        controller.set_enabled(False)
        controller.set_enabled(True)
        self.wait_for(lambda: len(worker.submissions) == 2)
        current_epoch, _ = worker.submissions[1]
        self.assertEqual(controller.revision, 7)
        self.assertNotEqual(old_epoch, current_epoch)
        result = calculate_graph(snapshot)
        worker.outcomes.extend((GraphOutcome(old_epoch, result=result),
                                GraphOutcome(old_epoch, error='stale same-revision error')))
        controller._collect()
        controller._collect()
        self.assertEqual(ready, [])
        self.assertEqual(failed, [])
        self.assertIsNone(controller.heat)
        worker.outcomes.append(GraphOutcome(current_epoch, result=result))
        controller._collect()
        self.assertEqual([revision for revision, _ in ready], [7])
        self.assertEqual(controller.heat.scores, dict(result.scores))
        controller.close()
        worker.outcomes.append(GraphOutcome(current_epoch, result=result))
        controller._collect()
        self.assertEqual(len(ready), 1)

    def test_graph_failure_leaves_diagnostics_current_and_reopen_can_retry(self):
        from AgStudio.shared.graph import calculate_graph
        from AgStudio.shared.graph.worker import GraphOutcome
        worker = ManualGraphWorker()
        with patch('AgStudio.gui.graph_analysis.GraphWorker', return_value=worker):
            tab = self.make_tab('=> - Act\n[A]: value\n[B]:\n- [A]\n',
                                background=True, map_enabled=False)
        self.settle(tab)
        analysis = tab.analysis
        failed = []
        tab.graph.failed.connect(lambda revision, error: failed.append(error))
        tab.set_map_enabled(True)
        self.wait_for(lambda: len(worker.submissions) == 1)
        epoch, _ = worker.submissions[0]
        worker.outcomes.append(GraphOutcome(epoch, error='controlled graph failure'))
        self.wait_for(lambda: bool(failed))
        self.assertEqual(failed, ['controlled graph failure'])
        self.assertIs(tab.analysis, analysis)
        self.assert_current_diagnostics(tab)
        self.assertIsNone(tab.document_map.heat)
        self.assertIsNone(tab.graph.heat)
        tab.set_map_enabled(False)
        tab.set_map_enabled(True)
        self.wait_for(lambda: len(worker.submissions) == 2)
        epoch, snapshot = worker.submissions[-1]
        worker.outcomes.append(GraphOutcome(epoch, result=calculate_graph(snapshot)))
        self.wait_heat(tab)
        self.assert_current_diagnostics(tab)
        self.assertEqual(tab.document_map._document_influence, 2)


if __name__ == '__main__':
    unittest.main()
