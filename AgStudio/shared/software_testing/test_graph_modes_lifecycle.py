"""Mode changes use the graph lifecycle without touching diagnostic scheduling."""
import importlib.util
import os
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class GraphModeLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_controller(self, enabled=True):
        from AgStudio.gui.graph_analysis import GraphController
        worker = Mock()
        worker.poll.return_value = None
        worker.busy = False
        controller = GraphController(enabled=enabled, worker=worker)
        self.addCleanup(controller.close)
        return controller, worker

    def wait_for(self, predicate):
        from PySide6.QtTest import QTest
        stop = time.monotonic() + 5
        while time.monotonic() < stop:
            if predicate():
                return
            QTest.qWait(5)
        self.fail('graph operation timed out')

    def test_switch_cancels_and_uses_current_analysis_without_lint(self):
        from AgStudio.shared.graph import GraphSnapshot
        controller, worker = self.make_controller()
        analysis = object()
        snapshot = GraphSnapshot((), (), ())
        with patch('AgStudio.gui.graph_analysis._prepare', return_value=snapshot) as prepare:
            controller.set_analysis(41, analysis)
            self.wait_for(lambda: worker.submit.called)
            for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic'):
                with self.subTest(mode=mode):
                    epoch = controller.epoch
                    worker.submit.reset_mock()
                    controller.set_mode(mode)
                    self.assertGreater(controller.epoch, epoch)
                    self.assertIsNone(controller.heat)
                    self.assertIs(controller.analysis, analysis)
                    self.assertEqual(controller.revision, 41)
                    self.wait_for(lambda: worker.submit.called)
                    self.assertEqual(prepare.call_args.kwargs.get('mode', 'heuristic'), mode)
                    self.assertIs(prepare.call_args.args[0], analysis)
                    worker.cancel.assert_called()

    def test_hidden_mode_and_options_do_not_prepare_or_submit(self):
        controller, worker = self.make_controller(False)
        with patch('AgStudio.gui.graph_analysis._prepare') as prepare:
            controller.set_analysis(2, object())
            for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic', 'semantic_triad_1'):
                controller.set_mode(mode)
            controller.set_options({'decay': 2.0})
            controller._collect()
            prepare.assert_not_called()
            worker.submit.assert_not_called()
            self.assertIsNone(controller.heat)

    def test_old_mode_outcome_never_publishes_after_switch(self):
        from AgStudio.shared.graph import GraphResult
        from AgStudio.shared.graph.worker import GraphOutcome
        controller, worker = self.make_controller()
        ready = Mock()
        controller.ready.connect(ready)
        old_epoch = controller.epoch
        controller.set_mode('semantic_triad_2')
        worker.poll.return_value = GraphOutcome(old_epoch, GraphResult((), (), ()))
        controller._collect()
        ready.assert_not_called()
        self.assertIsNone(controller.heat)

    def test_result_carries_current_mode_and_close_rejects_results(self):
        from AgStudio.shared.graph import GraphResult
        from AgStudio.shared.graph.worker import GraphOutcome
        controller, worker = self.make_controller()
        for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic'):
            controller.set_mode(mode)
            worker.poll.return_value = GraphOutcome(controller.epoch, GraphResult((), (), ()))
            controller._collect()
            self.assertEqual(controller.heat.mode, mode)
        controller.close()
        controller._collect()
        self.assertIsNone(controller.heat)
        worker.close.assert_called_once()

    def test_previous_triad_aliases_normalize_to_st2_without_duplicate_work(self):
        controller, worker = self.make_controller()
        controller.set_mode('semantic_triad')
        self.assertEqual(controller.mode, 'semantic_triad_2')
        epoch = controller.epoch
        worker.cancel.reset_mock()
        controller.set_mode('semantic_triad_2')
        controller.set_mode('semantic_triad')
        controller.set_mode('semantic_triad_3')
        self.assertEqual(controller.epoch, epoch)
        worker.cancel.assert_not_called()

    def test_options_are_detached_and_clear_invalidates_without_rescheduling(self):
        controller, worker = self.make_controller()
        options = {'representations': [{'object': 'A', 'position': 0, 'weight': 1}]}
        controller.set_options(options)
        options['representations'][0]['weight'] = 99
        self.assertEqual(controller.options['representations'][0]['weight'], 1)
        copied = controller.options
        copied.clear()
        self.assertTrue(controller.options)
        epoch = controller.epoch
        controller.clear_options()
        self.assertEqual(controller.options, {})
        self.assertGreater(controller.epoch, epoch)
        worker.submit.assert_not_called()

    def test_invalid_mode_and_nonfinite_options_fail_without_mutation(self):
        controller, _ = self.make_controller()
        epoch = controller.epoch
        for mode in ('semantic_basic', 'semantic_full', 'unknown'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                controller.set_mode(mode)
            self.assertEqual(controller.epoch, epoch)
        with self.assertRaises(ValueError):
            controller.set_options({'decay': float('nan')})
        self.assertEqual(controller.mode, 'heuristic')
        self.assertEqual(controller.options, {})

    def test_switch_preserves_diagnostics_and_does_not_request_analysis(self):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', '[A]:\n- Keep\n\n[B]:\n- [A]\n', background=True)
        self.addCleanup(tab.dispose_analysis)
        self.wait_for(lambda: tab.analysis is not None)
        analysis = tab.analysis
        revision = tab.controller.revision
        from PySide6.QtGui import QTextCursor
        cursor = tab.editor.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)
        tab.editor.setTextCursor(cursor)
        before = (tab.source, tab.dirty, cursor.position(), cursor.anchor(),
                  tab.editor.document().isUndoAvailable())
        with patch.object(tab.controller, 'request', wraps=tab.controller.request) as request:
            for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic') * 3:
                tab.set_inference_mode(mode)
            self.assertIs(tab.analysis, analysis)
            self.assertEqual(tab.controller.revision, revision)
            self.assertEqual((tab.source, tab.dirty, tab.editor.textCursor().position(),
                              tab.editor.textCursor().anchor(),
                              tab.editor.document().isUndoAvailable()), before)
            request.assert_not_called()
