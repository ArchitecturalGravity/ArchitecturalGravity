"""Shared parse and independent Findings processes with checked Qt delivery.

Production parsing and Findings calculations each have a disposable child.
The explicit custom-worker seam remains thread-based so tests can use local
closures and threading events, which cannot be sent to a spawn process.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

from ..shared.analysis_snapshot import (
    AnalysisRequest, AnalysisWorkResult, FindingsUpdate, PackedAnalysisSnapshot,
    calculate_findings_update, calculate_packed_parse, restore_analysis, unpack_analysis,
)
from ..shared.feature_worker import FeatureWorker
from ..shared.lint import analyze
from .graph_analysis import GraphController

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='agstudio-analysis-test')
_RESTORE_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='agstudio-analysis-delivery')


def _restore_parse_result(result):
    snapshot = unpack_analysis(result)
    packed = result if isinstance(result, PackedAnalysisSnapshot) else None
    return restore_analysis(snapshot), snapshot, packed


def _restore_result(result, analysis, snapshot):
    if isinstance(result, FindingsUpdate):
        if (result.document_id != analysis.document.document_id
                or result.diagnostics.document_id != result.document_id
                or result.diagnostics.arcgrav_version != analysis.document.session.arcgrav_version):
            raise ValueError('findings update does not match the parsed document')
        return (replace(analysis, diagnostics=result.diagnostics),
                replace(snapshot, diagnostics=result.diagnostics), result.findings_projection)
    if isinstance(result, AnalysisWorkResult):
        # Explicit process test fixtures can retain the original full result.
        return restore_analysis(result.snapshot), result.snapshot, result.findings_projection
    raise TypeError('findings worker must return FindingsUpdate or AnalysisWorkResult')


class AnalysisController(QObject):
    parsed = Signal(int, object)
    ready = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, parent=None, worker=analyze, delay_ms=180, *, heat_enabled=True):
        super().__init__(parent)
        self.graph = GraphController(self, enabled=heat_enabled)
        self.worker = worker
        self.parser_worker = FeatureWorker(calculate_packed_parse, name='parse')
        self.process_worker = FeatureWorker(calculate_findings_update, name='findings')
        self.delay_ms = delay_ms
        self.revision = 0
        self.closed = False
        self.pending = None
        self.running = None
        self._parse_submitted = None
        self._submitted = None
        self._parse_preparing = None
        self._preparing = None
        self.parsed_analysis = None
        self.prepared_analysis = None
        self.analysis_snapshot = None
        self.packed_snapshot = None
        self.findings_projection = None
        self.parser_pid = None
        self.worker_pid = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(delay_ms)
        self.timer.timeout.connect(self._dispatch)
        self.poll = QTimer(self)
        self.poll.setInterval(20)
        self.poll.timeout.connect(self._collect)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.close)
        # Retain only workers, never widgets, for deletion without closeEvent.
        self.destroyed.connect(self.parser_worker.close)
        self.destroyed.connect(self.process_worker.close)

    @property
    def document_snapshot(self):
        return self.analysis_snapshot.document if self.analysis_snapshot is not None else None

    @property
    def heat(self):
        return self.graph.heat

    @property
    def heat_enabled(self):
        return self.graph.enabled

    def set_heat_enabled(self, enabled):
        self.graph.set_enabled(enabled)

    def request(self, source, version, *, profile=None, configuration=None, immediate=False):
        if self.closed:
            return self.revision
        self.revision += 1
        self.graph.invalidate(self.revision)
        self.parsed_analysis = None
        self.prepared_analysis = None
        self.analysis_snapshot = None
        self.packed_snapshot = None
        self.findings_projection = None
        self.parser_pid = None
        self.worker_pid = None
        self.parser_worker.cancel()
        self.process_worker.cancel()
        self._parse_submitted = self._submitted = None
        for preparation in (self._parse_preparing, self._preparing):
            if preparation is not None:
                preparation[1].cancel()
        self._parse_preparing = self._preparing = None
        options = json.loads(json.dumps(configuration or {}, allow_nan=False))
        self.pending = (self.revision, source, version, profile, options)
        self.timer.start(0 if immediate else self.delay_ms)
        return self.revision

    def _dispatch(self):
        if self.closed or self.running is not None or self.pending is None:
            return
        revision, source, version, profile, configuration = self.pending
        self.pending = None
        if self.worker is analyze:
            request = AnalysisRequest(source, version, profile,
                                      json.dumps(configuration, allow_nan=False))
            try:
                self.parser_worker.submit(revision, request)
            except Exception as exc:
                if revision == self.revision:
                    self.failed.emit(revision, f'{type(exc).__name__}: {exc}')
                return
            self._parse_submitted = revision
        else:
            # Local test closures/events are not spawn-picklable. Production
            # language analysis never executes in this interpreter pool.
            self.running = (revision, _POOL.submit(
                self.worker, source, arcgrav_version=version,
                profile=profile, configuration=configuration))
        self.poll.start()

    def _publish_parsed(self, revision, result):
        if self.closed or revision != self.revision:
            return
        self.parsed_analysis = result
        self.parsed.emit(revision, result)
        # A signal slot can edit or close. Graph consumes this exact parse once;
        # completed diagnostics must not restart a currently computing map.
        if not self.closed and revision == self.revision:
            self.graph.set_analysis(revision, result,
                                    snapshot=self.packed_snapshot or self.analysis_snapshot)

    def _publish(self, revision, result):
        if self.closed or revision != self.revision:
            return
        self.prepared_analysis = result
        self.ready.emit(revision, result)

    def _collect(self):
        if self.closed:
            return
        if self.running is not None and self.running[1].done():
            revision, future = self.running
            self.running = None
            try:
                result = future.result()
            except Exception as exc:
                if revision == self.revision:
                    self.failed.emit(revision, f'{type(exc).__name__}: {exc}')
            else:
                self._publish_parsed(revision, result)
                self._publish(revision, result)

        parsed = self.parser_worker.poll()
        if (parsed is not None and parsed.revision == self.revision
                and parsed.revision == self._parse_submitted):
            self._parse_submitted = None
            if parsed.error is not None:
                self.failed.emit(parsed.revision, parsed.error)
            else:
                self._parse_preparing = (
                    parsed.revision, _RESTORE_POOL.submit(_restore_parse_result, parsed.result),
                    parsed.worker_pid,
                )
        if self._parse_preparing is not None and self._parse_preparing[1].done():
            revision, future, parser_pid = self._parse_preparing
            self._parse_preparing = None
            try:
                result, snapshot, packed = future.result()
            except Exception as exc:
                if revision == self.revision:
                    self.failed.emit(revision, f'{type(exc).__name__}: {exc}')
            else:
                if revision == self.revision:
                    self.analysis_snapshot = snapshot
                    self.packed_snapshot = packed
                    self.parser_pid = parser_pid
                    self._publish_parsed(revision, result)
                    if not self.closed and revision == self.revision:
                        try:
                            self.process_worker.submit(revision, packed or snapshot)
                        except Exception as exc:
                            self.failed.emit(revision, f'{type(exc).__name__}: {exc}')
                        else:
                            self._submitted = revision

        outcome = self.process_worker.poll()
        if (outcome is not None and outcome.revision == self.revision
                and outcome.revision == self._submitted):
            self._submitted = None
            if outcome.error is not None:
                self.failed.emit(outcome.revision, outcome.error)
            else:
                # Restoration only rebuilds indexes, but even that O(n) work
                # remains outside the Qt event loop.
                self._preparing = (
                    outcome.revision, _RESTORE_POOL.submit(
                        _restore_result, outcome.result, self.parsed_analysis, self.analysis_snapshot),
                    outcome.worker_pid,
                )
        if self._preparing is not None and self._preparing[1].done():
            revision, future, worker_pid = self._preparing
            self._preparing = None
            try:
                result, snapshot, projection = future.result()
            except Exception as exc:
                if revision == self.revision:
                    self.failed.emit(revision, f'{type(exc).__name__}: {exc}')
            else:
                if revision == self.revision:
                    self.analysis_snapshot = snapshot
                    self.findings_projection = projection
                    self.worker_pid = worker_pid
                    self._publish(revision, result)
        if not self.timer.isActive():
            self._dispatch()
        if (self.running is None and self._parse_submitted is None
                and self._submitted is None and self._parse_preparing is None
                and self._preparing is None):
            self.poll.stop()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.graph.close()
        self.parser_worker.close()
        self.process_worker.close()
        self.revision += 1
        self.pending = None
        self.parsed_analysis = None
        self.prepared_analysis = None
        self.analysis_snapshot = None
        self.packed_snapshot = None
        self.findings_projection = None
        self.parser_pid = None
        self.worker_pid = None
        self.timer.stop()
        self.poll.stop()
        for future in (self.running, self._parse_preparing, self._preparing):
            if future:
                future[1].cancel()
        self.running = self._parse_preparing = self._preparing = None
        self._parse_submitted = self._submitted = None
