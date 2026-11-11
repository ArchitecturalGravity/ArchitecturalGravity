"""Bounded, Qt-free on-demand suggestions in one reusable isolated process.

Submission/polling never perform native work, pipe IO or process startup on the
caller thread. Only explicitly submitted words reach Hunspell. The latest request
wins; obsolete work is terminated so it cannot delay the next user's request.
"""
from __future__ import annotations

import atexit
from dataclasses import dataclass
import multiprocessing
import threading
import time
from typing import Callable
import weakref

from .process_lifecycle import PROCESS_LOCK


@dataclass(frozen=True, slots=True)
class SuggestionOutcome:
    request_id: int
    suggestions: tuple[str, ...] = ()
    error: str | None = None


def _suggest_word(word: str) -> tuple[str, ...]:
    from .lint.spelling import _get_checker, suggestions_for_word
    if _get_checker() is None:
        raise RuntimeError('Hunspell is unavailable')
    return suggestions_for_word(word)


def _serve(connection, provider):
    """Importable spawn target; no Qt state or document crosses this boundary."""
    try:
        while True:
            request_id, word = connection.recv()
            try:
                result = tuple(provider(word))[:5]
                if not all(isinstance(item, str) and len(item) <= 256 for item in result):
                    raise ValueError('Invalid suggestion result')
                connection.send((request_id, result, None))
            except Exception as exc:
                connection.send((request_id, (), f'{type(exc).__name__}: {exc}'[:512]))
    except (EOFError, OSError):
        pass
    finally:
        connection.close()


_services = weakref.WeakSet()
_services_lock = threading.Lock()


def _shutdown():
    with _services_lock:
        services = tuple(_services)
    for service in services:
        service.close()
    for service in services:
        service.wait_closed()


atexit.register(_shutdown)


class SuggestionService:
    """One running and at most one pending request; bounded result retention.

    ``provider`` is a Qt-free importable callable test seam. Native resources
    and their bounded lexical caches belong exclusively to the child process.
    ``timeout`` bounds each request including cold startup. Cancellation and
    shutdown reap the child in the supervisor, never on the caller's thread.
    """
    def __init__(self, *, provider: Callable[[str], tuple[str, ...]] = _suggest_word,
                 timeout: float = 5.0):
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        self._provider = provider
        self._timeout = timeout
        self._context = multiprocessing.get_context('spawn')
        self._condition = threading.Condition()
        self._generation = 0
        self._pending = None
        self._outcome = None
        self._closed = False
        self._process = None
        self._connection = None
        self._thread = threading.Thread(target=self._supervise,
                                        name='spelling-suggestion-supervisor', daemon=True)
        with _services_lock:
            _services.add(self)
        self._thread.start()

    def submit(self, word: str) -> int:
        if not isinstance(word, str) or not 1 <= len(word) <= 128:
            raise ValueError('suggestion word must contain 1–128 characters')
        with self._condition:
            if self._closed:
                raise RuntimeError('Suggestion service is closed')
            self._generation += 1
            self._pending = (self._generation, word)
            self._outcome = None
            self._condition.notify()
            return self._generation

    def cancel(self, request_id: int) -> None:
        with self._condition:
            if request_id == self._generation:
                self._generation += 1
                self._pending = None
                self._outcome = None
                self._condition.notify()

    def poll(self) -> tuple[SuggestionOutcome, ...]:
        with self._condition:
            result, self._outcome = self._outcome, None
            return (result,) if result is not None else ()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._generation += 1
            self._pending = self._outcome = None
            self._condition.notify()

    def wait_closed(self, timeout: float | None = None) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _obsolete(self, request_id):
        with self._condition:
            return self._closed or self._generation != request_id

    def _start(self):
        if self._process is not None:
            with PROCESS_LOCK:
                alive = self._process.is_alive()
            if alive:
                return
            self._stop()
        parent, child = self._context.Pipe()
        process = self._context.Process(target=_serve, args=(child, self._provider),
                                        name='spelling-suggestions', daemon=True)
        try:
            with PROCESS_LOCK:
                process.start()
            self._process, self._connection = process, parent
        except BaseException:
            parent.close()
            with PROCESS_LOCK:
                process.close()
            raise
        finally:
            child.close()

    def _stop(self):
        connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()
        process, self._process = self._process, None
        if process is not None:
            with PROCESS_LOCK:
                if process.is_alive():
                    process.terminate()
                process.join(0.2)
                if process.is_alive():
                    process.kill()
                    process.join()
                process.close()

    def _run(self, request_id, word):
        deadline = time.monotonic() + self._timeout
        try:
            if self._obsolete(request_id):
                return None
            self._start()
            self._connection.send((request_id, word))
            while not self._obsolete(request_id):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Spelling suggestions timed out')
                if self._connection.poll(0.02):
                    response_id, values, error = self._connection.recv()
                    if (response_id != request_id or not isinstance(values, tuple)
                            or len(values) > 5 or not all(isinstance(s, str) and len(s) <= 256 for s in values)
                            or (error is not None and not isinstance(error, str))):
                        raise ValueError('Invalid suggestion worker response')
                    return SuggestionOutcome(request_id, values, error)
                with PROCESS_LOCK:
                    if not self._process.is_alive():
                        raise RuntimeError('Suggestion worker exited')
            self._stop()
            return None
        except Exception as exc:
            self._stop()
            return SuggestionOutcome(request_id, error=f'{type(exc).__name__}: {exc}'[:512])

    def _supervise(self):
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closed or self._pending is not None)
                    if self._closed:
                        break
                    request, self._pending = self._pending, None
                request_id, word = request
                outcome = self._run(request_id, word)
                with self._condition:
                    if not self._closed and self._generation == request_id:
                        self._outcome = outcome
        finally:
            self._stop()
            with _services_lock:
                _services.discard(self)
