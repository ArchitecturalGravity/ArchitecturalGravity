"""QObject and application shutdown reclaim graph work without closeEvent."""
from functools import partial
import importlib.util
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from AgStudio.shared.graph.core import GraphSnapshot
from AgStudio.shared.graph.worker import GraphWorker
from AgStudio.shared.software_testing.graph_worker_fixtures import controllable_calculation

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class GraphLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate, timeout=10):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            QTest.qWait(5)
        self.fail('lifecycle operation did not reach the expected state')

    def delete_object(self, obj):
        from PySide6.QtCore import QCoreApplication, QEvent
        from shiboken6 import isValid
        if isValid(obj):
            obj.deleteLater()
            QCoreApplication.sendPostedEvents(obj, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(obj))

    def owner(self):
        from PySide6.QtCore import QObject
        owner = QObject()
        self.addCleanup(self.delete_object, owner)
        return owner

    def close_worker(self, worker):
        worker.close()
        self.assertTrue(worker.wait_closed(10), 'graph supervisor did not finish')
        self.assertIsNone(worker.active_pid)

    def active_controller(self, parent):
        from AgStudio.gui.graph_analysis import GraphController
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        marker = Path(directory.name) / 'child.started'
        worker = GraphWorker(partial(controllable_calculation, started_file=str(marker)))
        self.addCleanup(self.close_worker, worker)
        controller = GraphController(parent, worker=worker)
        initial_cancellation = controller._cancellation
        with patch('AgStudio.gui.graph_analysis._prepare',
                   return_value=GraphSnapshot((1,), (), ())):
            controller.set_analysis(7, object())
            self.wait_for(marker.exists)
            pid = int(self.wait_for(lambda: marker.read_text(encoding='ascii')))
        self.assertNotEqual(pid, os.getpid())
        self.assertEqual(worker.active_pid, pid)
        self.assertTrue(worker.busy)
        self.assertIsNot(controller._cancellation, initial_cancellation)
        self.assertFalse(controller._cancellation.is_set())
        return controller, worker, pid

    def assert_reaped(self, worker, pid):
        self.assertTrue(worker.closed)
        self.assertTrue(worker.wait_closed(10), 'active graph child was not reaped')
        self.assertIsNone(worker.active_pid)
        self.assertNotIn(pid, [child.pid for child in multiprocessing.active_children()])
        self.assertFalse(worker.busy)
        self.assertIsNone(worker.poll())

    def publications(self, controller):
        ready, failed = Mock(), Mock()
        controller.ready.connect(ready)
        controller.failed.connect(failed)
        return ready, failed

    def assert_no_publications(self, *signals):
        from PySide6.QtTest import QTest
        QTest.qWait(50)
        for signal in signals:
            signal.assert_not_called()

    def test_qobject_destruction_reaps_active_cpu_without_close_event(self):
        from shiboken6 import isValid
        owner = self.owner()
        controller, worker, pid = self.active_controller(owner)
        cancellation = controller._cancellation
        ready, failed = self.publications(controller)

        # Deleting a plain QObject parent bypasses every widget closeEvent.
        self.delete_object(owner)

        self.assertFalse(isValid(controller))
        self.assertTrue(cancellation.is_set())
        self.assert_reaped(worker, pid)
        self.assert_no_publications(ready, failed)

    def test_qobject_destruction_cancels_running_preparation(self):
        from AgStudio.gui.graph_analysis import GraphController
        owner = self.owner()
        controller = GraphController(owner)
        worker = controller.worker
        self.addCleanup(self.close_worker, worker)
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        ready, failed = self.publications(controller)
        preparation_cancellations = []

        def prepare(analysis, cancellation):
            preparation_cancellations.append(cancellation)
            started.set()
            if not release.wait(10):
                raise TimeoutError('test did not release snapshot preparation')
            return GraphSnapshot((2,), (), ())

        with patch('AgStudio.gui.graph_analysis._prepare', side_effect=prepare), \
                patch.object(worker, 'submit', wraps=worker.submit) as submit:
            controller.set_analysis(3, object())
            self.wait_for(started.is_set)
            future = controller.running[1]
            cancellation = controller._cancellation
            self.assertEqual(preparation_cancellations, [cancellation])
            self.assertFalse(cancellation.is_set())

            self.delete_object(owner)

            self.assertTrue(cancellation.is_set())
            self.assertTrue(worker.closed)
            self.assertTrue(worker.wait_closed(10))
            release.set()
            self.assertEqual(future.result(timeout=10), GraphSnapshot((2,), (), ()))
            self.assert_no_publications(ready, failed)
            submit.assert_not_called()
            self.assertIsNone(worker.poll())

    def test_about_to_quit_closes_active_graph_and_pending_diagnostics(self):
        from AgStudio.gui.analysis import AnalysisController
        owner = self.owner()
        graph, worker, pid = self.active_controller(owner)
        cancellation = graph._cancellation
        graph_ready, graph_failed = self.publications(graph)
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []
        diagnostic_result = object()

        def diagnose(source, **kwargs):
            calls.append(source)
            started.set()
            if not release.wait(10):
                raise TimeoutError('test did not release diagnostic analysis')
            return diagnostic_result

        analysis = AnalysisController(owner, worker=diagnose, delay_ms=10000)
        self.addCleanup(self.close_worker, analysis.graph.worker)
        analysis_ready, analysis_failed = self.publications(analysis)
        analysis.request('running', 'current', immediate=True)
        self.wait_for(started.is_set)
        future = analysis.running[1]
        analysis.request('pending', 'current')
        self.assertIsNotNone(analysis.pending)
        self.assertTrue(analysis.timer.isActive())
        self.assertTrue(analysis.poll.isActive())

        # Exercise registered shutdown slots without terminating the shared app.
        self.app.aboutToQuit.emit()

        self.assertTrue(graph.closed)
        self.assertTrue(cancellation.is_set())
        self.assertFalse(graph.poll.isActive())
        self.assert_reaped(worker, pid)
        self.assertTrue(analysis.closed)
        self.assertTrue(analysis.graph.closed)
        self.assertTrue(analysis.graph.worker.closed)
        self.assertTrue(analysis.graph.worker.wait_closed(10))
        self.assertIsNone(analysis.pending)
        self.assertIsNone(analysis.running)
        self.assertIsNone(analysis.prepared_analysis)
        self.assertFalse(analysis.timer.isActive())
        self.assertFalse(analysis.poll.isActive())

        release.set()
        self.assertIs(future.result(timeout=10), diagnostic_result)
        # Even a late timer delivery or new request must not resurrect work.
        graph._collect()
        analysis._collect()
        revision = analysis.revision
        self.assertEqual(analysis.request('after shutdown', 'current', immediate=True), revision)
        analysis._dispatch()
        self.assert_no_publications(graph_ready, graph_failed, analysis_ready, analysis_failed)
        self.assertEqual(calls, ['running'])
        self.assertIsNone(worker.poll())


if __name__ == '__main__':
    unittest.main()
