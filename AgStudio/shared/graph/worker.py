"""Qt-free, disposable process execution for immutable graph calculations.

Only the child process calculates. A small supervisor thread owns startup,
IPC deserialization and process reaping, so none of those operations runs in
``submit``, ``poll``, ``cancel`` or ``close``. Replacing/canceling work sends an
OS termination request without waiting when process bookkeeping is idle; otherwise
the supervisor observes cancellation on its next poll. Neither path depends on
cooperative checks inside the calculation. The supervisor reaps the old child before starting
the next one. No callback can reach an editor or other GUI object.
"""
from __future__ import annotations

import atexit
from dataclasses import dataclass
import multiprocessing
from multiprocessing.connection import Connection
import threading
from typing import Callable
import weakref

from ..process_lifecycle import PROCESS_LOCK
from .core import GraphResult, GraphSnapshot, calculate_graph


Calculation = Callable[[object], GraphResult]


@dataclass(frozen=True, slots=True)
class GraphOutcome:
    revision: int
    result: GraphResult | None = None
    error: str | None = None
    worker_pid: int | None = None


@dataclass(frozen=True, slots=True)
class _Job:
    generation: int
    revision: int
    snapshot: object


def _calculate_child(send: Connection, calculation: Calculation,
                     snapshot: object) -> None:
    """Top-level entry point: importable under Windows' spawn semantics."""
    try:
        result = calculation(snapshot)
        if not isinstance(result, GraphResult):
            raise TypeError('graph calculation must return GraphResult')
        send.send(('result', result))
    except BaseException as exc:
        # Send text instead of an arbitrary exception object, which may not
        # be picklable. Serialization failures take this path as well.
        try:
            send.send(('error', f'{type(exc).__name__}: {exc}'))
        except (EOFError, OSError):
            pass
    finally:
        send.close()


_workers: weakref.WeakSet[GraphWorker] = weakref.WeakSet()
_workers_lock = threading.Lock()


def _shutdown_workers() -> None:
    # Connection imports multiprocessing.util before this registration, so
    # this runs before multiprocessing's own interpreter-exit child joins.
    with _workers_lock:
        workers = tuple(_workers)
    for worker in workers:
        worker.close()
    for worker in workers:
        worker.wait_closed()


atexit.register(_shutdown_workers)


class GraphWorker:
    """One replaceable graph job and at most one live child process.

    ``calculation`` may be injected for tests or a future numeric algorithm.
    It must be a module-level, spawn-picklable callable accepting a snapshot.
    ``input_type`` permits the map adapter to send a detached analysis request;
    ordinary numeric callers retain the strict GraphSnapshot input contract.
    Each submission has an internal generation as well as the caller's
    revision; even reusing a revision cannot publish an older submission.

    ``close`` is idempotent and nonblocking. Use ``wait_closed`` only where
    waiting is appropriate (tests or non-UI teardown). Interpreter shutdown
    also terminates and reaps any managers not explicitly closed.
    """

    def __init__(self, calculation: Calculation = calculate_graph, *,
                 input_type=GraphSnapshot) -> None:
        self._calculation = calculation
        self.input_type = input_type
        self._context = multiprocessing.get_context('spawn')
        self._condition = threading.Condition()
        # Process.start polls every manager's children through _cleanup;
        # all feature and graph supervisors must share this guard.
        self._process_lock = PROCESS_LOCK
        self._generation = 0
        self._pending: _Job | None = None
        self._running_generation: int | None = None
        self._process: multiprocessing.Process | None = None
        self._outcome: GraphOutcome | None = None
        self._closed = False
        self._thread = threading.Thread(
            target=self._supervise, name='graph-process-supervisor', daemon=True)
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
        """Replace current work without starting or joining a child here."""
        if not isinstance(snapshot, self.input_type):
            raise TypeError(f'graph worker requires {self.input_type!r}')
        with self._condition:
            if self._closed:
                raise RuntimeError('graph worker is closed')
            self._generation += 1
            self._pending = _Job(self._generation, revision, snapshot)
            self._outcome = None
            self._terminate_locked()
            self._condition.notify()

    def cancel(self) -> None:
        """Invalidate pending/results and signal the active child to stop."""
        with self._condition:
            self._generation += 1
            self._pending = None
            self._outcome = None
            self._terminate_locked()
            self._condition.notify()

    def poll(self) -> GraphOutcome | None:
        """Take an already received result; never reads a pipe or waits."""
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
        """Wait for a closed manager's child, pipe and thread to be reaped."""
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _terminate_locked(self) -> None:
        # terminate may poll waitpid internally, so it must not race a
        # supervisor's join or another manager's Process.start/_cleanup.
        # UI cancellation never waits on process bookkeeping or child reaping.
        if self._process is not None and self._process_lock.acquire(blocking=False):
            try:
                self._process.terminate()
            except (OSError, ValueError):
                pass  # It may have exited between the request and the signal.
            finally:
                self._process_lock.release()
        # A busy lock defers signaling to the supervisor's generation check.

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
                # Do not keep canceled snapshots or consumed large results
                # alive for as long as an idle tab keeps this manager open.
                del job, outcome
        finally:
            with _workers_lock:
                _workers.discard(self)

    def _run(self, job: _Job) -> GraphOutcome | None:
        receive = send = process = None
        outcome = None
        failure = None
        try:
            if self._superseded(job):
                return None
            receive, send = self._context.Pipe(duplex=False)
            process = self._context.Process(
                target=_calculate_child,
                args=(send, self._calculation, job.snapshot),
                name=f'graph-calculation-{job.revision}', daemon=True)
            with self._process_lock:
                if self._superseded(job):
                    return None
                process.start()
            send.close()  # Only the child owns the pipe's writing endpoint.
            with self._condition:
                self._process = process
                if self._closed or job.generation != self._generation:
                    self._terminate_locked()
            while not self._superseded(job):
                ready = receive.poll(0.02)
                with self._process_lock:
                    alive = process.is_alive()
                if not ready and not alive:
                    # The child can send and exit between the timed poll
                    # and the liveness check. Its exit proves no more bytes
                    # will be sent, but a complete result may now be queued.
                    ready = receive.poll()
                    if not ready:
                        failure = 'graph worker exited without a result'
                        break
                if ready:
                    kind, value = receive.recv()
                    if kind == 'result' and isinstance(value, GraphResult):
                        outcome = GraphOutcome(job.revision, result=value,
                                               worker_pid=process.pid)
                    elif kind == 'error' and isinstance(value, str):
                        outcome = GraphOutcome(job.revision, error=value,
                                               worker_pid=process.pid)
                    else:
                        failure = 'invalid graph worker response'
                    break
        except EOFError:
            failure = 'graph worker closed its pipe without a result'
        except Exception as exc:
            failure = f'{type(exc).__name__}: {exc}'
        finally:
            if send is not None:
                send.close()
            if receive is not None:
                receive.close()
            if process is not None:
                # Only this supervisor joins. Escalation also handles an
                # injected/noncooperative calculation that ignores SIGTERM.
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
        return GraphOutcome(job.revision, error=failure or 'graph worker failed')
