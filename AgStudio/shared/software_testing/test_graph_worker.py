"""Real spawn-process isolation, failure, cancellation and reaping checks."""
from functools import partial
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, call, patch

from AgStudio.shared.graph.core import GraphSnapshot, calculate_graph
from AgStudio.shared.graph.worker import GraphWorker
from AgStudio.shared.software_testing.graph_worker_fixtures import (
    controllable_calculation, crashing_calculation, failing_calculation,
    inspect_runtime, large_calculation, malformed_calculation,
    recoverable_calculation,
)


class GraphWorkerTests(unittest.TestCase):
    def make_worker(self, calculation=calculate_graph):
        worker = GraphWorker(calculation)
        self.addCleanup(self.close_worker, worker)
        return worker

    def close_worker(self, worker):
        worker.close()
        self.assertTrue(worker.wait_closed(10), 'worker cleanup did not finish')
        self.assertIsNone(worker.active_pid)

    def wait_until(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(0.005)
        self.fail('timed out waiting for graph worker')

    def outcome(self, worker):
        return self.wait_until(worker.poll)

    def assert_quick(self, action):
        started = time.monotonic()
        result = action()
        self.assertLess(time.monotonic() - started, 0.25)
        return result

    def slow_worker(self, directory, *, ignore_terminate=False):
        marker = Path(directory) / 'child.started'
        worker = self.make_worker(partial(
            controllable_calculation, started_file=str(marker),
            ignore_terminate=ignore_terminate))
        worker.submit(1, GraphSnapshot((1,), (), ()))
        self.wait_until(marker.exists)
        # The marker may become visible just before the write completes.
        pid = self.wait_until(lambda: marker.read_text(encoding='ascii'))
        return worker, int(pid)

    def assert_pid_reaped(self, pid):
        self.assertNotIn(pid, [child.pid for child in multiprocessing.active_children()])

    def test_default_calculation_matches_pure_core(self):
        snapshot = GraphSnapshot((1, 2, 3), ((1, 2), (1, 2), (2, 3)), ((9, 1),))
        worker = self.make_worker()
        self.assert_quick(lambda: worker.submit(7, snapshot))
        result = self.outcome(worker)
        self.assertEqual(result.revision, 7)
        self.assertEqual(result.result, calculate_graph(snapshot))
        self.assertIsNone(result.error)
        self.assertFalse(worker.busy)
        self.assertIsNone(worker.poll())

    def test_calculation_is_in_a_spawned_qt_free_process(self):
        worker = self.make_worker(inspect_runtime)
        worker.submit(1, GraphSnapshot((), (), ()))
        outcome = self.outcome(worker)
        self.assertIsNone(outcome.error)
        (pid, spawned), (qt_loaded, lint_loaded) = outcome.result.owners
        self.assertNotEqual(pid, os.getpid())
        self.assertEqual(spawned, 1)
        self.assertEqual((qt_loaded, lint_loaded), (0, 0))
        self.assert_pid_reaped(pid)

    def test_cancel_stops_uncooperative_cpu_and_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            worker, pid = self.slow_worker(directory)
            self.assertTrue(worker.busy)
            self.assertEqual(worker.active_pid, pid)
            self.assert_quick(worker.cancel)
            self.assertFalse(worker.busy)
            self.assertIsNone(worker.poll())
            self.wait_until(lambda: worker.active_pid is None)
            self.assert_pid_reaped(pid)
            snapshot = GraphSnapshot((2,), (), ((4, 2),))
            worker.submit(2, snapshot)
            result = self.outcome(worker)
            self.assertEqual(result.revision, 2)
            self.assertEqual(result.result, calculate_graph(snapshot))

    def test_replacement_reaps_old_child_and_only_reports_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            worker, pid = self.slow_worker(directory)
            snapshot = GraphSnapshot((2,), (), ())
            self.assert_quick(lambda: worker.submit(2, snapshot))
            outcome = self.outcome(worker)
            self.assertEqual(outcome.revision, 2)
            self.assertEqual(outcome.result, calculate_graph(snapshot))
            self.assert_pid_reaped(pid)
            self.assertIsNone(worker.poll())

    def test_repeated_revision_does_not_release_a_previous_result(self):
        worker = self.make_worker()
        worker.submit(1, GraphSnapshot((1,), (), ()))
        self.wait_until(lambda: not worker.busy)
        newer = GraphSnapshot((2,), (), ((8, 2),))
        worker.submit(1, newer)
        self.assertEqual(self.outcome(worker).result, calculate_graph(newer))
        self.assertIsNone(worker.poll())

    def test_cancel_drops_an_already_received_result(self):
        worker = self.make_worker()
        worker.submit(1, GraphSnapshot((), (), ()))
        self.wait_until(lambda: not worker.busy)
        worker.cancel()
        self.assertIsNone(worker.poll())

    def test_close_is_quick_idempotent_and_reaps_active_cpu(self):
        with tempfile.TemporaryDirectory() as directory:
            worker, pid = self.slow_worker(directory)
            self.assert_quick(worker.close)
            self.assert_quick(worker.close)
            self.assertTrue(worker.closed)
            self.assertFalse(worker.busy)
            self.assertTrue(worker.wait_closed(10))
            self.assert_pid_reaped(pid)
            self.assertIsNone(worker.poll())
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                worker.submit(2, GraphSnapshot((), (), ()))

    @unittest.skipUnless(os.name == 'posix', 'SIGTERM ignoring is POSIX-specific')
    def test_cancellation_escalates_if_calculation_ignores_termination(self):
        with tempfile.TemporaryDirectory() as directory:
            worker, pid = self.slow_worker(directory, ignore_terminate=True)
            self.assert_quick(worker.cancel)
            self.wait_until(lambda: worker.active_pid is None)
            self.assert_pid_reaped(pid)
            self.assertIsNone(worker.poll())

    def test_calculation_exception_becomes_error_outcome(self):
        worker = self.make_worker(failing_calculation)
        worker.submit(4, GraphSnapshot((), (), ()))
        outcome = self.outcome(worker)
        self.assertEqual(outcome.revision, 4)
        self.assertIsNone(outcome.result)
        self.assertIn('ValueError: deliberate graph failure', outcome.error)
        self.assertFalse(worker.busy)
        self.assertIsNone(worker.active_pid)

    def test_crash_becomes_error_outcome_without_hanging(self):
        worker = self.make_worker(crashing_calculation)
        worker.submit(9, GraphSnapshot((), (), ()))
        outcome = self.outcome(worker)
        self.assertEqual(outcome.revision, 9)
        self.assertIsNone(outcome.result)
        self.assertIn('without a result', outcome.error)
        self.assertIn('exit code 23', outcome.error)
        self.assertFalse(worker.busy)

    def test_child_sends_and_exits_between_poll_and_liveness_check(self):
        # Deterministically reproduce the short race window: the timed poll
        # sees nothing; the child then sends its result and exits before the
        # supervisor checks is_alive. The final pipe poll must still drain it.
        worker = self.make_worker()
        snapshot = GraphSnapshot((1,), (), ())
        result = calculate_graph(snapshot)
        receive = Mock()
        receive.poll.side_effect = (False, True)
        receive.recv.return_value = ('result', result)
        send = Mock()
        process = Mock(pid=12345, exitcode=0)
        process.is_alive.return_value = False
        context = Mock()
        context.Pipe.return_value = (receive, send)
        context.Process.return_value = process
        with patch.object(worker, '_context', context):
            worker.submit(7, snapshot)
            outcome = self.outcome(worker)
        self.assertIsNone(outcome.error)
        self.assertEqual(outcome.result, result)
        self.assertEqual(outcome.revision, 7)
        self.assertEqual(receive.poll.call_args_list, [call(0.02), call()])
        receive.recv.assert_called_once_with()
        process.close.assert_called_once_with()

    def test_startup_pickling_failure_is_reported_and_closed(self):
        worker = self.make_worker(lambda snapshot: calculate_graph(snapshot))
        self.assert_quick(lambda: worker.submit(1, GraphSnapshot((), (), ())))
        outcome = self.outcome(worker)
        self.assertIsNone(outcome.result)
        self.assertIn('<lambda>', outcome.error)
        self.assertFalse(worker.busy)
        self.assertIsNone(worker.active_pid)

    def test_malformed_calculation_is_reported(self):
        worker = self.make_worker(malformed_calculation)
        worker.submit(1, GraphSnapshot((), (), ()))
        self.assertIn('must return GraphResult', self.outcome(worker).error)

    def test_manager_recovers_after_error_and_crash(self):
        worker = self.make_worker(recoverable_calculation)
        for revision, block in enumerate((-1, 1, -2, 2)):
            with self.subTest(block=block):
                snapshot = GraphSnapshot((block,), (), ())
                worker.submit(revision, snapshot)
                outcome = self.outcome(worker)
                self.assertEqual(outcome.revision, revision)
                self.assertIsNone(worker.active_pid)
                if block < 0:
                    self.assertIsNotNone(outcome.error)
                else:
                    self.assertIsNone(outcome.error)
                    self.assertEqual(outcome.result, calculate_graph(snapshot))

    def test_managers_keep_revisions_and_cancellation_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            slow, pid = self.slow_worker(directory)
            fast = self.make_worker()
            snapshot = GraphSnapshot((2,), (), ())
            fast.submit(1, snapshot)
            self.assertEqual(self.outcome(fast).result, calculate_graph(snapshot))
            self.assertTrue(slow.busy)
            self.assertEqual(slow.active_pid, pid)
            slow.cancel()
            fast.submit(2, snapshot)
            self.assertEqual(self.outcome(fast).revision, 2)
            self.assertIsNone(slow.poll())

    def test_large_result_is_received_in_background(self):
        worker = self.make_worker(large_calculation)
        worker.submit(1, GraphSnapshot((), (), ()))
        deadline = time.monotonic() + 15
        outcome = None
        while time.monotonic() < deadline:
            outcome = self.assert_quick(worker.poll)
            if outcome is not None:
                break
            time.sleep(0.001)
        self.assertIsNotNone(outcome)
        self.assertIsNone(outcome.error)
        self.assertEqual(len(outcome.result.owners), 150000)
        self.assertEqual(outcome.result.owners[-1], (149999, 149999))

    def test_cancel_during_startup_never_publishes_stale_result(self):
        worker = self.make_worker()
        for revision in range(20):
            self.assert_quick(lambda: worker.submit(revision, GraphSnapshot((revision,), (), ())))
            self.assert_quick(worker.cancel)
        final = GraphSnapshot((100,), (), ())
        worker.submit(100, final)
        outcome = self.outcome(worker)
        self.assertEqual(outcome.revision, 100)
        self.assertEqual(outcome.result, calculate_graph(final))

    def test_interpreter_exit_closes_an_unclosed_active_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = str(Path(directory) / 'exit.started')
            program = '''
from functools import partial
from pathlib import Path
import time
from AgStudio.shared.graph.core import GraphSnapshot
from AgStudio.shared.graph.worker import GraphWorker
from AgStudio.shared.software_testing.graph_worker_fixtures import controllable_calculation
worker = GraphWorker(partial(controllable_calculation, started_file=%r))
worker.submit(1, GraphSnapshot((1,), (), ()))
deadline = time.monotonic() + 10
while not Path(%r).exists() and time.monotonic() < deadline:
    time.sleep(0.01)
assert Path(%r).exists()
''' % (marker, marker, marker)
            result = subprocess.run(
                [sys.executable, '-c', program],
                cwd=Path(__file__).resolve().parents[3],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
