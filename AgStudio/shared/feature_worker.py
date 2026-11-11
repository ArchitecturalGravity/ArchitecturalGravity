"""Qt-free, latest-only process execution for editor feature projections.

Every instance owns its own supervisor and disposable spawn process. Only the
child invokes the calculation. Startup/pickling, pipe deserialization and child
reaping happen in the supervisor, never in the caller's UI thread. This follows
the graph worker's process contract without coupling feature results to graphs.

Snapshots and results must be detached, picklable data, with no Qt objects or
callbacks into a document. Treat a submitted snapshot as immutable. Calculations
must be importable module-level callables in Qt-free modules (a partial of such
a callable is also supported). There is deliberately no inline fallback.
"""
from __future__ import annotations

import atexit
from dataclasses import dataclass
import multiprocessing
from multiprocessing.connection import Connection
import os
import threading
from typing import Callable
import weakref

from .process_lifecycle import PROCESS_LOCK


Calculation = Callable[[object], object]


@dataclass(frozen=True, slots=True)
class FeatureOutcome:
    revision: int
    result: object = None
    error: str | None = None
    worker_pid: int | None = None


@dataclass(frozen=True, slots=True)
class _Job:
    generation: int
    revision: int
    snapshot: object


def _calculate_child(send: Connection, calculation: Calculation,
                     snapshot: object) -> None:
    """Importable under Windows spawn; never imports a presentation module."""
    try:
        send.send(('result', calculation(snapshot), os.getpid()))
    except BaseException as exc:
        # Exception objects (and even calculation results) can be unpicklable.
        # Text keeps failure delivery independent of their implementation.
        try:
            send.send(('error', f'{type(exc).__name__}: {exc}', os.getpid()))
        except (EOFError, OSError):
            pass
    finally:
        send.close()


_workers: weakref.WeakSet[FeatureWorker] = weakref.WeakSet()
_workers_lock = threading.Lock()


def _shutdown_workers() -> None:
    # Register after importing Connection/multiprocessing.util so this runs
    # before multiprocessing's interpreter-exit joins of outstanding children.
    with _workers_lock:
        workers = tuple(_workers)
    for worker in workers:
        worker.close()
    for worker in workers:
        worker.wait_closed()


atexit.register(_shutdown_workers)


class FeatureWorker:
    """One independent latest-only feature job, with at most one live child.

    An internal generation also protects callers that reuse a document revision.
    Cancel/close terminate uncooperative child calculations without waiting; the
    supervisor escalates to kill and reaps the child before starting another.
    ``wait_closed`` is only for tests or non-UI shutdown, never a GUI callback.
    """

    def __init__(self, calculation: Calculation, *, name: str = 'feature') -> None:
        self._calculation = calculation
        self._name = name
        self._context = multiprocessing.get_context('spawn')
        self._condition = threading.Condition()
        # Process.start() polls every manager's children through _cleanup;
        # all feature and graph supervisors must share the same guard.
        self._process_lock = PROCESS_LOCK
        self._generation = 0
        self._pending: _Job | None = None
        self._running_generation: int | None = None
        self._process: multiprocessing.Process | None = None
        self._outcome: FeatureOutcome | None = None
        self._closed = False
        self._thread = threading.Thread(
            target=self._supervise, name=f'{name}-process-supervisor', daemon=True)
        with _workers_lock:
            _workers.add(self)
        try:
            self._thread.start()
        except BaseException:
            with _workers_lock:
                _workers.discard(self)
            raise

    @property
    def busy(self) -> bool:
        """Whether the latest, uncanceled submission still needs a result."""
        with self._condition:
            return (self._pending is not None
                    or self._running_generation == self._generation)

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    @property
    def active_pid(self) -> int | None:
        """Diagnostic PID, including a canceled child still being reaped."""
        with self._condition:
            return self._process.pid if self._process is not None else None

    def submit(self, revision: int, snapshot: object) -> None:
        """Replace current work without serializing or starting a child here."""
        with self._condition:
            if self._closed:
                raise RuntimeError(f'{self._name} worker is closed')
            self._generation += 1
            self._pending = _Job(self._generation, revision, snapshot)
            self._outcome = None
            self._terminate_locked()
            self._condition.notify()

    def cancel(self) -> None:
        """Discard pending results and signal the active child without waiting."""
        with self._condition:
            self._generation += 1
            self._pending = None
            self._outcome = None
            self._terminate_locked()
            self._condition.notify()

    def poll(self) -> FeatureOutcome | None:
        """Take an already deserialized result; never read a pipe or wait."""
        with self._condition:
            outcome, self._outcome = self._outcome, None
            return outcome

    def close(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._generation += 1
            self._pending = None
            self._outcome = None
            self._terminate_locked()
            self._condition.notify()

    def wait_closed(self, timeout: float | None = None) -> bool:
        """Wait outside the UI thread for the process and supervisor to exit."""
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _terminate_locked(self) -> None:
        # terminate only sends an OS signal. The lock prevents Process.close
        # racing a caller; joining and escalation belong to the supervisor.
        if self._process is not None and self._process_lock.acquire(blocking=False):
            try:
                self._process.terminate()
            except (OSError, ValueError):
                pass
            finally:
                self._process_lock.release()
        # If the supervisor owns the process lock, the generation check
        # observes cancellation on its next poll and performs termination.

    def _superseded(self, job: _Job) -> bool:
        with self._condition:
            return self._closed or job.generation != self._generation

    def _supervise(self) -> None:
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(
                        lambda: self._closed or self._pending is not None)
                    if self._closed:
                        return
                    job, self._pending = self._pending, None
                    self._running_generation = job.generation
                outcome = self._run(job)
                with self._condition:
                    self._running_generation = None
                    if not self._closed and job.generation == self._generation:
                        self._outcome = outcome
                # Idle controllers must not retain consumed large snapshots.
                del job, outcome
        finally:
            with _workers_lock:
                _workers.discard(self)

    def _run(self, job: _Job) -> FeatureOutcome | None:
        receive = send = process = None
        outcome = None
        failure = None
        pid = None
        try:
            if self._superseded(job):
                return None
            receive, send = self._context.Pipe(duplex=False)
            process = self._context.Process(
                target=_calculate_child,
                args=(send, self._calculation, job.snapshot),
                name=f'{self._name}-calculation-{job.revision}', daemon=True)
            with self._process_lock:
                if self._superseded(job):
                    return None
                process.start()
            pid = process.pid
            send.close()
            with self._condition:
                self._process = process
                if self._closed or job.generation != self._generation:
                    self._terminate_locked()
            while not self._superseded(job):
                ready = receive.poll(0.02)
                with self._process_lock:
                    alive = process.is_alive()
                if not ready and not alive:
                    # The child may have sent and exited after the timed poll.
                    ready = receive.poll()
                    if not ready:
                        failure = f'{self._name} worker exited without a result'
                        break
                if ready:
                    kind, value, worker_pid = receive.recv()
                    if kind == 'result' and worker_pid == pid:
                        outcome = FeatureOutcome(job.revision, result=value,
                                                 worker_pid=worker_pid)
                    elif kind == 'error' and isinstance(value, str) and worker_pid == pid:
                        outcome = FeatureOutcome(job.revision, error=value,
                                                 worker_pid=worker_pid)
                    else:
                        failure = f'invalid {self._name} worker response'
                    break
        except EOFError:
            failure = f'{self._name} worker closed its pipe without a result'
        except Exception as exc:
            failure = f'{type(exc).__name__}: {exc}'
        finally:
            if send is not None:
                send.close()
            if receive is not None:
                receive.close()
            if process is not None:
                with self._process_lock:
                    if process.pid is not None:
                        if self._superseded(job):
                            try:
                                process.terminate()
                            except OSError:
                                pass
                        process.join(0.2)
                        if process.is_alive():
                            process.kill()
                            process.join()
                        if failure is not None:
                            failure += f' (exit code {process.exitcode})'
                    with self._condition:
                        if self._process is process:
                            self._process = None
                        process.close()
        if self._superseded(job):
            return None
        if outcome is not None:
            return outcome
        return FeatureOutcome(job.revision, error=failure or f'{self._name} worker failed',
                              worker_pid=pid)
