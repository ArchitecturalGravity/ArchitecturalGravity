"""Real spawn-process coverage for independent editor feature workers."""
import importlib.util
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, call, patch

from AgStudio.shared.feature_worker import FeatureOutcome, FeatureWorker


def _feature_calculation(snapshot):
    """Importable fixture, deliberately keeping all Qt imports in test methods."""
    kind, *args = snapshot
    if kind == 'runtime':
        return (os.getpid(), multiprocessing.get_start_method(),
                any(name.startswith('PySide') for name in sys.modules),
                any(name.startswith('AgStudio.gui') for name in sys.modules))
    if kind == 'hang':
        marker, ignore_terminate = args
        if ignore_terminate and hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        Path(marker).write_text(str(os.getpid()), encoding='ascii')
        # CPU-bound and noncooperative: no sleeps or cancellation callbacks.
        counter = 0
        while True:
            counter = (counter + 1) % 1000000
    if kind == 'crash':
        os._exit(31)
    if kind == 'raise':
        raise ValueError('deliberate feature failure')
    if kind == 'large':
        return tuple((index, str(index)) for index in range(args[0]))
    if kind == 'deserialize':
        return _ResultProbe(args[0])
    if kind == 'unpicklable':
        return lambda: None
    return args[0] if args else None


class _SnapshotProbe:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        Path(self.marker).write_text(threading.current_thread().name, encoding='ascii')
        time.sleep(0.3)
        return tuple, (('value', 'serialized'),)


class _ResultProbe:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        return _restore_result, (self.marker,)


def _restore_result(marker):
    Path(marker).write_text(threading.current_thread().name, encoding='ascii')
    time.sleep(0.3)
    return 'deserialized'


class _ReleaseProbe:
    def __init__(self, released, threads):
        self.released, self.threads = released, threads

    def __del__(self):
        self.threads.append(threading.current_thread().name)
        self.released.set()


class FeatureWorkerTests(unittest.TestCase):
    def make_worker(self, calculation=_feature_calculation, name='feature'):
        worker = FeatureWorker(calculation, name=name)
        self.addCleanup(self.close_worker, worker)
        return worker

    def close_worker(self, worker):
        worker.close()
        self.assertTrue(worker.wait_closed(10), 'feature supervisor did not exit')
        self.assertIsNone(worker.active_pid)

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.005)
        self.fail('timed out waiting for feature worker')

    def outcome(self, worker):
        return self.wait_for(worker.poll)

    def assert_quick(self, operation):
        start = time.monotonic()
        result = operation()
        self.assertLess(time.monotonic() - start, 0.25)
        return result

    def start_hanging(self, worker, marker, *, ignore_terminate=False, revision=1):
        worker.submit(revision, ('hang', str(marker), ignore_terminate))
        self.wait_for(marker.exists)
        pid = int(self.wait_for(lambda: marker.read_text(encoding='ascii')))
        self.assertEqual(worker.active_pid, pid)
        return pid

    def assert_reaped(self, pid):
        self.assertNotIn(pid, [child.pid for child in multiprocessing.active_children()])

    def test_calculation_is_in_a_spawned_qt_free_process(self):
        worker = self.make_worker(name='outline')
        self.assert_quick(lambda: worker.submit(7, ('runtime',)))
        outcome = self.outcome(worker)
        self.assertEqual(outcome.revision, 7)
        self.assertIsNone(outcome.error)
        pid, start_method, qt_loaded, gui_loaded = outcome.result
        self.assertNotEqual(pid, os.getpid())
        self.assertEqual(outcome.worker_pid, pid)
        self.assertEqual(start_method, 'spawn')
        self.assertFalse(qt_loaded)
        self.assertFalse(gui_loaded)
        self.assertFalse(worker.busy)
        self.assertIsNone(worker.poll())
        self.assert_reaped(pid)

    def test_feature_and_graph_workers_share_global_process_lifecycle_guard(self):
        from AgStudio.shared.graph.worker import GraphWorker
        from AgStudio.shared.process_lifecycle import PROCESS_LOCK
        outline = self.make_worker(name='outline')
        findings = self.make_worker(name='findings')
        graph = GraphWorker()
        self.addCleanup(self.close_worker, graph)
        for worker in (outline, findings, graph):
            self.assertIs(worker._process_lock, PROCESS_LOCK)

    def test_outline_findings_highlighting_processes_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            workers = [self.make_worker(name=name)
                       for name in ('outline', 'findings', 'highlighting')]
            pids = [self.start_hanging(worker, Path(directory) / str(index))
                    for index, worker in enumerate(workers)]
            self.assertEqual(len(set(pids + [os.getpid()])), 4)
            self.assertTrue(all(worker.busy for worker in workers))
            workers[0].cancel()
            workers[1].submit(2, ('value', 'findings completed'))
            outcome = self.outcome(workers[1])
            self.assertEqual(outcome.result, 'findings completed')
            self.assertEqual(outcome.revision, 2)
            self.assertEqual(workers[2].active_pid, pids[2])
            self.assertTrue(workers[2].busy)
            self.assertIsNone(workers[0].poll())
            self.wait_for(lambda: workers[0].active_pid is None)
            for pid in pids[:2]:
                self.assert_reaped(pid)

    def test_replacement_reaps_old_child_and_discards_reused_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = self.make_worker()
            pid = self.start_hanging(worker, Path(directory) / 'started', revision=9)
            self.assert_quick(lambda: worker.submit(9, ('value', 'newer')))
            outcome = self.outcome(worker)
            self.assertEqual(outcome.revision, 9)
            self.assertEqual(outcome.result, 'newer')
            self.assert_reaped(pid)
            self.assertIsNone(worker.poll())

    def test_cancel_drops_running_and_already_received_results(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = self.make_worker()
            pid = self.start_hanging(worker, Path(directory) / 'started')
            self.assert_quick(worker.cancel)
            self.assertFalse(worker.busy)
            self.wait_for(lambda: worker.active_pid is None)
            self.assert_reaped(pid)
            self.assertIsNone(worker.poll())
            worker.submit(2, ('value', 'queued result'))
            self.wait_for(lambda: not worker.busy)
            worker.cancel()
            self.assertIsNone(worker.poll())
            worker.submit(3, ('value', 'fresh result'))
            self.assertEqual(self.outcome(worker).result, 'fresh result')

    @unittest.skipUnless(os.name == 'posix', 'SIGTERM ignoring is POSIX-specific')
    def test_cancel_escalates_for_noncooperative_child(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = self.make_worker()
            pid = self.start_hanging(worker, Path(directory) / 'started',
                                     ignore_terminate=True)
            self.assert_quick(worker.cancel)
            self.wait_for(lambda: worker.active_pid is None)
            self.assert_reaped(pid)
            self.assertIsNone(worker.poll())

    def test_exception_and_crash_recover_independently(self):
        failed = self.make_worker(name='findings')
        unaffected = self.make_worker(name='highlighting')
        for index, kind in enumerate(('raise', 'crash', 'value')):
            with self.subTest(kind=kind):
                failed.submit(index, (kind, 'recovered'))
                unaffected.submit(index, ('value', 'unaffected'))
                outcome = self.outcome(failed)
                self.assertEqual(outcome.revision, index)
                if kind == 'raise':
                    self.assertIn('ValueError: deliberate feature failure', outcome.error)
                elif kind == 'crash':
                    self.assertIn('without a result', outcome.error)
                    self.assertIn('exit code 31', outcome.error)
                else:
                    self.assertIsNone(outcome.error)
                    self.assertEqual(outcome.result, 'recovered')
                self.assertIsNone(failed.active_pid)
                self.assertEqual(self.outcome(unaffected).result, 'unaffected')

    def test_startup_and_result_serialization_failures_have_no_inline_fallback(self):
        calls = []
        worker = self.make_worker(lambda snapshot: calls.append(snapshot))
        self.assert_quick(lambda: worker.submit(1, ('value', 4)))
        outcome = self.outcome(worker)
        self.assertIsNotNone(outcome.error)
        self.assertIn('<lambda>', outcome.error)
        self.assertEqual(calls, [])
        self.assertIsNone(worker.active_pid)
        valid_worker = self.make_worker()
        valid_worker.submit(2, ('unpicklable',))
        self.assertIsNotNone(self.outcome(valid_worker).error)
        valid_worker.submit(3, ('value', None))
        outcome = self.outcome(valid_worker)
        self.assertIsNone(outcome.error)
        self.assertIsNone(outcome.result)

    def test_startup_serialization_and_result_deserialization_are_off_caller_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = self.make_worker(name='outline')
            marker = Path(directory) / 'serialize-thread'
            self.assert_quick(lambda: worker.submit(1, _SnapshotProbe(str(marker))))
            self.assertEqual(self.outcome(worker).result, 'serialized')
            self.assertEqual(marker.read_text(encoding='ascii'), 'outline-process-supervisor')
            marker = Path(directory) / 'deserialize-thread'
            worker.submit(2, ('deserialize', str(marker)))
            self.wait_for(marker.exists)
            self.assert_quick(worker.poll)
            self.assertEqual(self.outcome(worker).result, 'deserialized')
            self.assertEqual(marker.read_text(encoding='ascii'), 'outline-process-supervisor')

    def test_large_results_are_received_without_blocking_poll(self):
        worker = self.make_worker()
        worker.submit(1, ('large', 150000))
        deadline = time.monotonic() + 15
        outcome = None
        while time.monotonic() < deadline:
            outcome = self.assert_quick(worker.poll)
            if outcome is not None:
                break
            time.sleep(0.002)
        self.assertIsNotNone(outcome)
        self.assertIsNone(outcome.error)
        self.assertEqual(len(outcome.result), 150000)
        self.assertEqual(outcome.result[-1], (149999, '149999'))

    def test_child_send_exit_race_drains_queued_result(self):
        worker = self.make_worker()
        receive = Mock()
        receive.poll.side_effect = (False, True)
        receive.recv.return_value = ('result', 'finished', 12345)
        send = Mock()
        process = Mock(pid=12345, exitcode=0)
        process.is_alive.return_value = False
        context = Mock()
        context.Pipe.return_value = (receive, send)
        context.Process.return_value = process
        with patch.object(worker, '_context', context):
            worker.submit(7, ('value', 'finished'))
            outcome = self.outcome(worker)
        self.assertEqual(outcome, FeatureOutcome(7, 'finished', worker_pid=12345))
        self.assertEqual(receive.poll.call_args_list, [call(0.02), call()])
        receive.recv.assert_called_once_with()
        process.close.assert_called_once_with()

    def test_cancellation_during_startup_never_publishes_stale_results(self):
        worker = self.make_worker()
        for revision in range(20):
            self.assert_quick(lambda: worker.submit(revision, ('value', revision)))
            self.assert_quick(worker.cancel)
        worker.submit(100, ('value', 'latest'))
        outcome = self.outcome(worker)
        self.assertEqual(outcome.revision, 100)
        self.assertEqual(outcome.result, 'latest')
        self.assertIsNone(worker.poll())

    def test_cancellation_never_waits_for_supervisor_process_reaping_lock(self):
        worker = self.make_worker()
        joining, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        receive, send = Mock(), Mock()
        receive.poll.return_value = True
        receive.recv.return_value = ('result', 'obsolete', 12345)
        process = Mock(pid=12345, exitcode=0)
        process.is_alive.return_value = False

        def join(timeout=None):
            joining.set()
            if not release.wait(5):
                raise TimeoutError('test did not release process join')

        process.join.side_effect = join
        context = Mock()
        context.Pipe.return_value = (receive, send)
        context.Process.return_value = process
        with patch.object(worker, '_context', context):
            worker.submit(1, ('value', 'obsolete'))
            self.wait_for(joining.is_set)
            self.assert_quick(worker.cancel)
            self.assert_quick(worker.close)
            # Calling terminate here would race join's waitpid bookkeeping.
            process.terminate.assert_not_called()
            release.set()
            self.assertTrue(worker.wait_closed(10))
        process.close.assert_called_once_with()
        self.assertIsNone(worker.poll())

    def test_close_is_nonblocking_idempotent_and_reaps_active_child(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = self.make_worker()
            pid = self.start_hanging(worker, Path(directory) / 'started')
            self.assert_quick(worker.close)
            self.assert_quick(worker.close)
            self.assertTrue(worker.closed)
            self.assertFalse(worker.busy)
            self.assertTrue(worker.wait_closed(10))
            self.assert_reaped(pid)
            self.assertIsNone(worker.poll())
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                worker.submit(2, ('value', 'too late'))

    def test_interpreter_exit_reaps_unclosed_active_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = str(Path(directory) / 'started')
            program = '''
from pathlib import Path
import time
from AgStudio.shared.feature_worker import FeatureWorker
from AgStudio.shared.software_testing.test_feature_process import _feature_calculation
worker = FeatureWorker(_feature_calculation)
worker.submit(1, ('hang', %r, False))
deadline = time.monotonic() + 10
while not Path(%r).exists() and time.monotonic() < deadline:
    time.sleep(0.01)
assert Path(%r).exists()
''' % (marker, marker, marker)
            result = subprocess.run([sys.executable, '-c', program],
                                    cwd=Path(__file__).resolve().parents[3],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('Traceback', result.stderr)


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class FeatureControllerTests(unittest.TestCase):
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
        self.fail('timed out waiting for feature controller')

    def delete_object(self, obj):
        from PySide6.QtCore import QCoreApplication, QEvent
        from shiboken6 import isValid
        if isValid(obj):
            obj.deleteLater()
            QCoreApplication.sendPostedEvents(obj, QEvent.Type.DeferredDelete)

    def make_controller(self, parent=None, name='outline', worker=None):
        from AgStudio.gui.feature_analysis import FeatureController
        controller = FeatureController(parent, calculation=_feature_calculation,
                                       name=name, worker=worker)
        self.addCleanup(self.delete_object, controller)
        self.addCleanup(self.close_worker, controller.worker)
        return controller

    def close_worker(self, worker):
        worker.close()
        self.assertTrue(worker.wait_closed(10))

    def test_retired_data_model_is_destroyed_off_qt_thread_without_retention(self):
        from AgStudio.gui.feature_analysis import retire_snapshot
        released, threads = threading.Event(), []
        model = _ReleaseProbe(released, threads)
        retire_snapshot(model)
        del model
        self.assertFalse(released.is_set())
        self.wait_for(released.is_set)
        self.assertEqual(len(threads), 1)
        self.assertTrue(threads[0].startswith('agstudio-analysis-delivery'))

    def test_timer_publishes_latest_revision_on_qt_thread(self):
        from PySide6.QtCore import QThread
        controller = self.make_controller()
        ready, failed = [], []
        controller.ready.connect(lambda revision, result:
                                 ready.append((revision, result, QThread.currentThread())))
        controller.failed.connect(lambda *args: failed.append(args))
        controller.request(3, ('value', 'old'))
        controller.request(3, ('value', 'new'))
        self.wait_for(lambda: ready)
        self.assertEqual(ready, [(3, 'new', self.app.thread())])
        self.assertEqual(failed, [])
        self.assertEqual(controller.result, 'new')
        self.assertNotEqual(controller.worker_pid, os.getpid())
        self.assertIsNotNone(controller.worker_pid)
        self.assertFalse(controller.poll.isActive())

    def test_ready_handler_can_request_new_work_reentrantly(self):
        controller = self.make_controller()
        results = []

        def accept(revision, result):
            results.append((revision, result))
            if revision == 1:
                controller.request(2, ('value', 'second'))

        controller.ready.connect(accept)
        controller.request(1, ('value', 'first'))
        self.wait_for(lambda: len(results) == 2)
        self.assertEqual(results, [(1, 'first'), (2, 'second')])
        self.assertFalse(controller.poll.isActive())

    def test_epoch_rejects_stale_ready_and_failure_for_reused_revision(self):
        worker = Mock(busy=False)
        controller = self.make_controller(worker=worker)
        ready, failed = Mock(), Mock()
        controller.ready.connect(ready)
        controller.failed.connect(failed)
        controller.request(8, ('value', 'old'))
        old_epoch = controller.epoch
        controller.request(8, ('value', 'new'))
        for outcome in (FeatureOutcome(old_epoch, 'old'),
                        FeatureOutcome(old_epoch, error='stale crash')):
            worker.poll.return_value = outcome
            controller._collect()
        ready.assert_not_called()
        failed.assert_not_called()
        worker.poll.return_value = FeatureOutcome(controller.epoch, 'new', worker_pid=123)
        controller._collect()
        ready.assert_called_once_with(8, 'new')
        self.assertEqual(controller.worker_pid, 123)
        self.assertFalse(controller.poll.isActive())

    def test_failure_is_local_and_request_recovers(self):
        controller = self.make_controller(name='outline')
        other = self.make_controller(name='highlighting')
        ready, failed, other_ready = [], [], []
        controller.ready.connect(lambda *args: ready.append(args))
        controller.failed.connect(lambda *args: failed.append(args))
        other.ready.connect(lambda *args: other_ready.append(args))
        controller.request(1, ('crash',))
        other.request(1, ('value', 'unaffected'))
        self.wait_for(lambda: failed and other_ready)
        self.assertIn('exit code 31', failed[0][1])
        self.assertEqual(other_ready, [(1, 'unaffected')])
        self.assertIsNone(controller.result)
        self.assertFalse(controller.poll.isActive())
        controller.request(2, ('value', 'recovered'))
        self.wait_for(lambda: ready)
        self.assertEqual(ready, [(2, 'recovered')])

    def test_qobject_destruction_closes_worker_without_close_event(self):
        from PySide6.QtCore import QObject
        from shiboken6 import isValid
        parent = QObject()
        self.addCleanup(self.delete_object, parent)
        controller = self.make_controller(parent)
        ready, failed = Mock(), Mock()
        controller.ready.connect(ready)
        controller.failed.connect(failed)
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'started'
            controller.request(4, ('hang', str(marker), False))
            self.wait_for(marker.exists)
            pid = controller.worker.active_pid
            self.delete_object(parent)
            self.assertFalse(isValid(controller))
            self.assertTrue(controller.worker.closed)
            self.assertTrue(controller.worker.wait_closed(10))
            self.assertIsNone(controller.worker.active_pid)
            self.assertNotIn(pid, [child.pid for child in multiprocessing.active_children()])
            ready.assert_not_called()
            failed.assert_not_called()

    def test_application_shutdown_closes_workers_and_late_requests_are_ignored(self):
        controller = self.make_controller()
        ready, failed = Mock(), Mock()
        controller.ready.connect(ready)
        controller.failed.connect(failed)
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'started'
            controller.request(4, ('hang', str(marker), False))
            self.wait_for(marker.exists)
            self.app.aboutToQuit.emit()
            self.assertTrue(controller.closed)
            self.assertTrue(controller.worker.closed)
            self.assertTrue(controller.worker.wait_closed(10))
            self.assertFalse(controller.poll.isActive())
            revision = controller.revision
            self.assertEqual(controller.request(9, ('value', 'late')), revision)
            controller._collect()
            ready.assert_not_called()
            failed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
