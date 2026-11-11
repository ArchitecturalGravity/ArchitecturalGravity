"""Revision and cancellation checks for the footprint-based Semantic Triad.

The controller tests deliberately deliver stale work after cancellation. The
integration tests also exercise the real spawned map process and automatic
source-aligned displays across revisions, visibility changes and mode switches.
"""
from concurrent.futures import Future
import importlib.util
import os
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from AgStudio.shared.graph.core import (
    GraphSnapshot, SemanticFootprint, SemanticOptions, SemanticView, calculate_graph,
)
from AgStudio.shared.graph.worker import GraphOutcome


class ManualWorker:
    def __init__(self):
        self.submissions = []
        self.outcomes = []
        self.busy = False
        self.closed = False

    def submit(self, revision, snapshot):
        self.submissions.append((revision, snapshot))
        self.busy = True

    def cancel(self):
        self.busy = False

    def poll(self):
        if self.outcomes:
            self.busy = False
            return self.outcomes.pop(0)
        return None

    def close(self):
        self.closed = True
        self.cancel()


def semantic_snapshot(decay=1.0, mode='semantic_triad_2'):
    return GraphSnapshot(
        (1, 2), (), ((1, 1), (2, 2)), mode=mode,
        options=SemanticOptions(decay=decay), points=((1, 10), (2, 20)),
        document_length=20,
        semantic_footprints=(SemanticFootprint('A', ((0, 8),)),
                             SemanticFootprint('B', ((10, 20),))),
        semantic_views=(SemanticView(1, 10, ('A',), 'named_block'),
                        SemanticView(2, 20, ('B',), 'named_block')))


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class TriadControllerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def controller(self, enabled=True):
        from AgStudio.gui.graph_analysis import GraphController
        worker = ManualWorker()
        controller = GraphController(enabled=enabled, worker=worker)
        self.addCleanup(controller.close)
        return controller, worker

    def test_kernel_change_rejects_stale_views_at_same_document_revision(self):
        controller, worker = self.controller()
        ready = Mock()
        controller.ready.connect(ready)
        controller.revision = 17
        controller.set_mode('semantic_triad_1')
        controller.set_options({'decay': 1.0})
        old_epoch = controller.epoch
        controller.set_options({'decay': 2.0})
        worker.outcomes.append(GraphOutcome(
            old_epoch, calculate_graph(semantic_snapshot(1.0, mode='semantic_triad_1'))))
        controller._collect()
        self.assertIsNone(controller.heat)
        ready.assert_not_called()

        expected = calculate_graph(semantic_snapshot(2.0, mode='semantic_triad_1'))
        worker.outcomes.append(GraphOutcome(controller.epoch, expected))
        controller._collect()
        ready.assert_called_once()
        self.assertEqual(ready.call_args.args[0], 17)
        self.assertEqual(controller.heat.decay, 2.0)
        self.assertTrue(expected.details)
        self.assertTrue(expected.view_details)
        self.assertTrue(expected.states)
        self.assertEqual(controller.heat.details, dict(expected.details))
        self.assertEqual(controller.heat.views, {view.node: view for view in expected.semantic_views})
        self.assertEqual(controller.heat.view_details, dict(expected.view_details))
        self.assertEqual(controller.heat.states, {
            block: dict(values) for block, values in expected.states})

    def test_interrupted_preparation_dispatches_only_latest_mode_and_kernel(self):
        controller, worker = self.controller()
        first, latest = Future(), Future()
        first.set_running_or_notify_cancel()
        old_analysis, new_analysis = object(), object()
        with patch('AgStudio.gui.graph_analysis._PREPARATION_POOL.submit',
                   side_effect=(first, latest)) as submit:
            controller.set_analysis(1, old_analysis)
            first_cancellation = controller._cancellation
            controller.set_mode('semantic_triad_1')
            controller.set_mode('semantic_triad_2')
            controller.set_options({'decay': 1.0})
            controller.set_analysis(2, new_analysis)
            controller.set_options({'decay': 2.0})
            self.assertTrue(first_cancellation.is_set())
            first.set_result(GraphSnapshot((99,), (), ()))
            controller._collect()
            self.assertEqual(worker.submissions, [])
            self.assertEqual(submit.call_count, 2)
            self.assertIs(submit.call_args.args[1], new_analysis)
            self.assertEqual(submit.call_args.kwargs,
                             {'mode': 'semantic_triad_2', 'options': {'decay': 2.0}})

            latest_snapshot = semantic_snapshot(2.0)
            latest.set_result(latest_snapshot)
            controller._collect()
            self.assertEqual(worker.submissions, [(controller.epoch, latest_snapshot)])
            self.assertEqual(controller.revision, 2)

    def test_hidden_mode_and_kernel_changes_only_prepare_latest_on_reveal(self):
        controller, worker = self.controller(enabled=False)
        future = Future()
        old, latest = object(), object()
        with patch('AgStudio.gui.graph_analysis._PREPARATION_POOL.submit',
                   return_value=future) as submit:
            controller.set_analysis(3, old)
            for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic', 'semantic_triad_2'):
                controller.set_mode(mode)
            controller.set_options({'decay': 1.0})
            controller.set_analysis(4, latest)
            controller.set_options({'decay': 2.0})
            controller._collect()
            submit.assert_not_called()
            self.assertEqual(worker.submissions, [])
            controller.set_enabled(True)
            submit.assert_called_once()
            self.assertIs(submit.call_args.args[1], latest)
            self.assertEqual(submit.call_args.kwargs['options'], {'decay': 2.0})
            future.set_result(semantic_snapshot(2.0))
            controller._collect()
            self.assertEqual(len(worker.submissions), 1)

    def test_rapid_three_mode_cycle_rejects_all_superseded_results_and_errors(self):
        controller, worker = self.controller()
        ready, failed = Mock(), Mock()
        controller.ready.connect(ready)
        controller.failed.connect(failed)
        stale = []
        for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic', 'semantic_triad_1'):
            controller.set_mode(mode)
            stale.append(GraphOutcome(controller.epoch, calculate_graph(semantic_snapshot())))
            stale.append(GraphOutcome(controller.epoch, error='obsolete mode failure'))
        controller.set_mode('semantic_triad_2')
        worker.outcomes.extend(stale)
        for _ in stale:
            controller._collect()
        self.assertIsNone(controller.heat)
        ready.assert_not_called()
        failed.assert_not_called()
        worker.outcomes.append(GraphOutcome(controller.epoch, calculate_graph(semantic_snapshot())))
        controller._collect()
        ready.assert_called_once()
        failed.assert_not_called()
        self.assertEqual(controller.heat.mode, 'semantic_triad_2')

    def test_st2_publishes_lazy_exact_vector_and_invalidates_it_on_mode_change(self):
        controller, worker = self.controller()
        controller.set_mode('semantic_triad_2')
        result = calculate_graph(semantic_snapshot())
        worker.outcomes.append(GraphOutcome(controller.epoch, result))
        controller._collect()
        heat = controller.heat
        self.assertIsNotNone(heat.position_evaluator)
        self.assertEqual(heat.position_snapshot, result.position_snapshot)
        self.assertEqual(heat.mode, 'semantic_triad_2')
        self.assertEqual(heat.view_details, {})
        self.assertEqual(heat.details, {})
        self.assertEqual(heat.states, {})
        self.assertEqual(heat.final_details, result.final_details)
        self.assertEqual(tuple(item.object for item in heat.final_details), ('A', 'B'))
        vector = heat.position_evaluator.details_at(5)
        self.assertEqual(tuple(item.object for item in vector), ('A', 'B'))
        self.assertGreater(vector[0].linked, 0)
        self.assertEqual(vector[1].linked, 0)
        controller.set_mode('semantic_triad_1')
        self.assertIsNone(controller.heat)

    def test_legacy_aliases_keep_the_current_canonical_st2_result(self):
        controller, worker = self.controller()
        controller.set_mode('semantic_triad_2')
        worker.outcomes.append(GraphOutcome(controller.epoch, calculate_graph(semantic_snapshot())))
        controller._collect()
        heat, epoch = controller.heat, controller.epoch
        for alias in ('semantic_triad', 'semantic_triad_3'):
            with self.subTest(alias=alias):
                controller.set_mode(alias)
                self.assertEqual(controller.mode, 'semantic_triad_2')
                self.assertEqual(controller.epoch, epoch)
                self.assertIs(controller.heat, heat)

    def test_hidden_and_closed_controllers_reject_late_states_and_errors(self):
        controller, worker = self.controller()
        ready, failed = Mock(), Mock()
        controller.ready.connect(ready)
        controller.failed.connect(failed)
        controller.set_mode('semantic_triad_2')
        controller.set_enabled(False)
        worker.outcomes.extend((
            GraphOutcome(controller.epoch, calculate_graph(semantic_snapshot())),
            GraphOutcome(controller.epoch, error='late failure'),
        ))
        controller._collect()
        controller._collect()
        controller.close()
        worker.outcomes.append(GraphOutcome(controller.epoch, calculate_graph(semantic_snapshot())))
        controller._collect()
        ready.assert_not_called()
        failed.assert_not_called()
        self.assertIsNone(controller.heat)
        self.assertTrue(worker.closed)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class TriadMapLifecycleTests(unittest.TestCase):
    SOURCE = '[A]:\n- first text\n\n[B]:\n- [A] second text\n\nTask:\n- [B]\n'

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, condition, timeout=10):
        from PySide6.QtTest import QTest
        stop = time.monotonic() + timeout
        while time.monotonic() < stop:
            if condition():
                return
            QTest.qWait(5)
        self.fail('map did not reach the expected current state')

    def tab(self, mode='semantic_triad_2'):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', self.SOURCE, inference_mode=mode,
                          background=False)
        tab.resize(1000, 620)
        tab.show()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.close)
        self.addCleanup(tab.dispose_analysis)
        self.wait_for(lambda: tab.document_map._heat_ready)
        return tab

    @staticmethod
    def displayed_segments(view):
        return tuple(view.position_segments(row) for row in view.rows)

    def test_repeated_rebuilds_and_mode_switches_keep_all_objects_and_diagnostics(self):
        tab = self.tab()
        analysis = tab.analysis
        diagnostics = tab.diagnostics
        views = dict(tab.document_map.heat.views)
        segments = self.displayed_segments(tab.document_map)
        final = tab.document_map.heat.final_details
        self.assertEqual({item.object for item in final},
                         {'A', 'B', '@element:2', '@element:5', '@element:6'})
        # Blank-only elements retain final values but have no painted source width.
        self.assertEqual({segment.object for values in segments for segment in values
                          if segment.object is not None}, {'A', 'B', '@element:6'})
        with patch.object(tab.graph.worker, 'submit', wraps=tab.graph.worker.submit) as submit:
            for _ in range(5):
                tab.document_map.rebuild()
                self.assertEqual(self.displayed_segments(tab.document_map), segments)
            submit.assert_not_called()
        for mode in ('heuristic', 'semantic_triad_1', 'semantic_triad_2') * 3:
            tab.set_inference_mode(mode)
        self.wait_for(lambda: tab.document_map._heat_ready)
        self.assertEqual(tab.document_map.heat.mode, 'semantic_triad_2')
        self.assertEqual(tab.document_map.heat.views, views)
        self.assertEqual(tab.document_map.heat.final_details, final)
        self.assertEqual(self.displayed_segments(tab.document_map), segments)
        self.assertIs(tab.analysis, analysis)
        self.assertIs(tab.diagnostics, diagnostics)

    def test_hidden_edit_reveals_only_current_automatic_objects(self):
        tab = self.tab()
        tab.set_map_enabled(False)
        with patch.object(tab.graph.worker, 'submit', wraps=tab.graph.worker.submit) as submit:
            tab.editor.setPlainText('[C]:\n- new current text\n\nTask:\n- [C]\n')
            self.assertEqual(tab.analysis.document.source, tab.source)
            self.assertIsNone(tab.document_map.heat)
            tab.graph._collect()
            submit.assert_not_called()
        tab.set_map_enabled(True)
        self.wait_for(lambda: tab.document_map._heat_ready)
        self.assertEqual({name for view in tab.document_map.heat.views.values()
                          for name in view.objects}, {'C', '@element:2', '@element:3'})
        self.assertEqual({item.object for item in tab.document_map.heat.final_details},
                         {'C', '@element:2', '@element:3'})
        self.assertEqual(tab.document_map.heat.view_details, {})
        self.assertEqual({segment.object for values in self.displayed_segments(tab.document_map)
                          for segment in values if segment.object is not None}, {'C', '@element:3'})

    def test_hidden_three_mode_cycle_reveals_only_latest_st1_block_components(self):
        tab = self.tab()
        tab.set_map_enabled(False)
        with patch.object(tab.graph.worker, 'submit', wraps=tab.graph.worker.submit) as submit:
            tab.editor.setPlainText('[C]:\n- latest current text\n\nTask:\n- [C]\n')
            for mode in ('heuristic', 'semantic_triad_2', 'semantic_triad_1'):
                tab.set_inference_mode(mode)
            tab.graph._collect()
            submit.assert_not_called()
        self.assertFalse(tab.document_map._heat_ready)
        tab.set_map_enabled(True)
        self.wait_for(lambda: tab.document_map._heat_ready)
        self.assertEqual(tab.graph.mode, 'semantic_triad_1')
        self.assertEqual(tab.document_map.heat.mode, 'semantic_triad_1')
        self.assertEqual({item.object for values in tab.document_map.heat.view_details.values()
                          for item in values}, {'C', '@element:2', '@element:3'})
        self.assertTrue(tab.document_map._block_summaries)
        self.assertTrue(all(len(values) == 1 and values[0][0] is None
                            for values in tab.document_map._display_segments.values()))

    def test_visible_edit_retains_old_frame_without_exposing_stale_views(self):
        from PySide6.QtCore import QPoint
        for mode in ('semantic_triad_1', 'semantic_triad_2'):
            with self.subTest(mode=mode):
                tab = self.tab(mode)
                display = dict(tab.document_map._display_segments)
                tab.document_map.grab()
                frame = tab.document_map._position_frame.copy()
                if mode == 'semantic_triad_2':
                    self.assertFalse(frame.isNull())
                tab.editor.setPlainText('[C]:\n- latest text\n\nTask:\n- [C]\n')
                self.assertIsNone(tab.document_map.heat)
                self.assertFalse(tab.document_map._heat_ready)
                self.assertEqual(tab.document_map._display_segments, display)
                if mode == 'semantic_triad_2':
                    self.assertEqual(tab.document_map._position_frame, frame)
                    self.assertTrue(all(not segments for segments in
                                        self.displayed_segments(tab.document_map)))
                self.assertEqual(tab.document_map.tooltip_at(QPoint()), tab.document_map.mode_help)
                self.wait_for(lambda: tab.document_map._heat_ready)
                self.assertEqual(tab.document_map.heat.mode, mode)
                self.assertEqual({item.object for item in tab.document_map.heat.final_details},
                                 {'C', '@element:2', '@element:3'})
                if mode == 'semantic_triad_2':
                    self.assertEqual(tab.document_map.heat.view_details, {})
                    self.assertEqual({segment.object
                                      for values in self.displayed_segments(tab.document_map)
                                      for segment in values if segment.object is not None},
                                     {'C', '@element:3'})
                else:
                    self.assertEqual({item.object for values in tab.document_map.heat.view_details.values()
                                      for item in values}, {'C', '@element:2', '@element:3'})


if __name__ == '__main__':
    unittest.main()
