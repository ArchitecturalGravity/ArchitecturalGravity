"""Small Qt delivery controller for independent editor-feature processes.

Only detached data crosses the worker boundary. A timer delivers already
deserialized results on the Qt thread; calculations never execute here.
"""
from functools import partial

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

from ..shared.feature_worker import FeatureWorker


def _release_snapshot(holder):
    # Mutate the holder rather than relying on callback/future destruction:
    # Qt may keep a callback wrapper alive after this task has already run.
    holder.clear()


def _queue_snapshot_release(holder):
    # Reuse the bounded-thread restoration executor; no extra persistent
    # thread, cache, or QObject reference is needed to retire a data model.
    from .analysis import _RESTORE_POOL
    _RESTORE_POOL.submit(_release_snapshot, holder)


def retire_snapshot(snapshot):
    """Release an obsolete data-only model away from the GUI edit callback.

    Call on replacement of a settled model, before dropping its last UI-owned
    reference. Deferring the handoff one Qt event turn lets the caller finish
    dropping those references before the background thread clears the holder.
    This is not a per-keystroke queue: pending edits have no settled model to
    retire. The executor drains every holder instead of retaining a last model.
    """
    if snapshot is None:
        return
    holder = [snapshot]
    if QCoreApplication.instance() is not None and not QCoreApplication.closingDown():
        QTimer.singleShot(0, partial(_queue_snapshot_release, holder))
    else:
        _queue_snapshot_release(holder)


def _dispose_worker(worker, *_):
    # Do not capture a controller whose C++ QObject may already be destroyed.
    worker.close()


class FeatureController(QObject):
    ready = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, parent=None, *, calculation=None, name='feature', worker=None):
        super().__init__(parent)
        if worker is None and calculation is None:
            raise TypeError('feature controller requires a calculation or worker')
        self.worker = worker if worker is not None else FeatureWorker(calculation, name=name)
        self.name = name
        self.revision = 0
        self.epoch = 0
        self.closed = False
        self.result = None
        self.worker_pid = None
        self._submitted = None
        self.poll = QTimer(self)
        self.poll.setInterval(20)
        self.poll.timeout.connect(self._collect)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.close)
        self.destroyed.connect(partial(_dispose_worker, self.worker))

    @property
    def busy(self):
        return not self.closed and (self._submitted is not None or self.worker.busy)

    def invalidate(self, revision):
        """Drop stale work immediately, including an already received result."""
        if self.closed:
            return
        self.epoch += 1
        self.revision = revision
        self._submitted = None
        self.result = None
        self.worker_pid = None
        self.poll.stop()
        self.worker.cancel()

    def cancel(self):
        self.invalidate(self.revision)

    def request(self, revision, snapshot):
        if self.closed:
            return self.revision
        self.invalidate(revision)
        epoch = self.epoch
        try:
            self.worker.submit(epoch, snapshot)
        except Exception as exc:
            self.failed.emit(revision, f'{type(exc).__name__}: {exc}')
        else:
            self._submitted = epoch
            self.poll.start()
        return revision

    def _collect(self):
        if self.closed:
            return
        outcome = self.worker.poll()
        if (outcome is not None and outcome.revision == self.epoch
                and self._submitted == self.epoch):
            self._submitted = None
            self.worker_pid = outcome.worker_pid
            if outcome.error is not None:
                self.failed.emit(self.revision, outcome.error)
            else:
                self.result = outcome.result
                self.ready.emit(self.revision, self.result)
        # A ready/failed handler may submit new work reentrantly.
        if not self.busy:
            self.poll.stop()

    def close(self):
        if self.closed:
            return
        self.invalidate(self.revision + 1)
        self.closed = True
        self.worker.close()
