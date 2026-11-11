"""Qt delivery for disposable graph work, independent of diagnostic analysis.

Only immutable, detached snapshots cross the process boundary. Parser adaptation
and scoring run in the same dedicated map process. The compatibility
preparation thread only detaches snapshots; Qt publication is exclusively polled.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
import json
from copy import deepcopy
from threading import Event

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

from ..shared.graph import HeatCancelled
from ..shared.graph.adapter import build_graph_snapshot
from ..shared.graph.worker import GraphWorker
from ..shared.graph.core import GraphSnapshot
from ..shared.graph.map_request import MapRequest, calculate_map_request
from ..shared.analysis_snapshot import AnalysisSnapshot, DocumentSnapshot, freeze_analysis, freeze_document
from .inference_heat import HeatModel, MODE_LABELS, normalize_graph_mode

_PREPARATION_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='agstudio-graph-input')


@dataclass(frozen=True)
class _MapPreparation:
    analysis: object


def _prepare(analysis, cancellation, *, mode="heuristic", options=None):
    if cancellation.is_set():
        raise HeatCancelled()
    if isinstance(analysis, _MapPreparation):
        original = analysis.analysis
        snapshot = (original if isinstance(original, (AnalysisSnapshot, DocumentSnapshot))
                    else freeze_analysis(original) if hasattr(original, 'tree')
                    else freeze_document(original))
        return MapRequest(snapshot, mode, json.dumps(options or {}, allow_nan=False))
    # An explicitly injected numeric/custom worker retains the original adapter
    # seam. Production always sends detached analysis to its own map process.
    if hasattr(analysis, 'tree'):
        tree, semantics = analysis.tree, analysis.semantics
    else:
        # Legacy preview has a ParsedDocument but no canonical analysis result.
        from ..shared.lint.syntax import parse
        from ..shared.lint.semantics import resolve
        tree = parse(analysis)
        semantics = resolve(analysis, tree)
    kwargs = {} if mode == "heuristic" and not options else {"mode": mode, "options": options}
    return build_graph_snapshot(tree, semantics, cancelled=cancellation.is_set, **kwargs)


def _dispose_worker(worker, cancellation, *_):
    cancellation[0].set()
    worker.close()


class GraphController(QObject):
    ready = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, parent=None, *, enabled=True, worker=None):
        super().__init__(parent)
        self.worker = worker if worker is not None else GraphWorker(
            calculate_map_request, input_type=(GraphSnapshot, MapRequest))
        self._process_preparation = (getattr(self.worker, 'input_type', None)
                                     == (GraphSnapshot, MapRequest))
        self.enabled = enabled
        self.closed = False
        self.revision = 0
        self.epoch = 0
        self.analysis = None
        self.analysis_snapshot = None
        self.mode = "heuristic"
        self._options = {}
        self.heat = None
        self.worker_pid = None
        self.running = None
        self.pending = None
        self._submitted = None
        self._cancellation = Event()
        self._cancellation_ref = [self._cancellation]
        self.poll = QTimer(self)
        self.poll.setInterval(20)
        self.poll.timeout.connect(self._collect)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.close)
        # QObject deletion must also reclaim processes if a host skips closeEvent.
        self.destroyed.connect(partial(_dispose_worker, self.worker, self._cancellation_ref))

    def _cancel(self):
        self.epoch += 1
        self._cancellation.set()
        self.pending = None
        if self.running:
            self.running[1].cancel()
        self.worker.cancel()
        self._submitted = None
        self.heat = None
        self.worker_pid = None

    def invalidate(self, revision):
        if self.closed:
            return
        self._cancel()
        self.revision = revision
        self.analysis = None
        self.analysis_snapshot = None

    def set_enabled(self, enabled):
        if self.closed or self.enabled == enabled:
            return
        self.enabled = enabled
        self._cancel()
        if enabled and self.analysis is not None:
            self._schedule()

    @property
    def options(self):
        return deepcopy(self._options)

    def set_mode(self, mode):
        mode = normalize_graph_mode(mode)
        if not isinstance(mode, str) or mode not in MODE_LABELS:
            raise ValueError('Unknown inference mode')
        if self.closed or self.mode == mode:
            return
        self._cancel()
        self.mode = mode
        if self.enabled and self.analysis is not None:
            self._schedule()

    def set_options(self, options):
        # Detach caller-owned dictionaries before preparation threads see them.
        if not isinstance(options, dict):
            raise ValueError('Semantic options must be a JSON object')
        detached = json.loads(json.dumps(options, allow_nan=False))
        if self.closed or self._options == detached:
            return
        self._cancel()
        self._options = detached
        if self.enabled and self.analysis is not None:
            self._schedule()

    def clear_options(self):
        """Drop source-coordinate declarations on edits without extra work."""
        if self._options:
            self._cancel()
            self._options = {}

    def set_analysis(self, revision, analysis, *, snapshot=None):
        if self.closed:
            return
        self._cancel()
        self.revision = revision
        self.analysis = analysis
        self.analysis_snapshot = snapshot
        if self.enabled:
            self._schedule()

    def _schedule(self):
        self.pending = (self.epoch, self.analysis, self.mode, self.options, self.analysis_snapshot)
        self.poll.start()
        self._dispatch()

    def _dispatch(self):
        if self.closed or not self.enabled or self.running or self.pending is None:
            return
        epoch, analysis, mode, options, snapshot = self.pending
        self.pending = None
        self._cancellation = Event()
        self._cancellation_ref[0] = self._cancellation
        if self._process_preparation and snapshot is not None:
            # Canonical analysis already supplied its detached transport. There
            # is no parser adaptation, source scan, or preparation-thread work.
            try:
                self.worker.submit(epoch, MapRequest(
                    snapshot, mode, json.dumps(options, allow_nan=False)))
                self._submitted = epoch
            except Exception as exc:
                self.failed.emit(self.revision, f'{type(exc).__name__}: {exc}')
            return
        if self._process_preparation:
            analysis = _MapPreparation(analysis)
        kwargs = {} if mode == 'heuristic' and not options else {'mode': mode, 'options': options}
        self.running = (epoch, _PREPARATION_POOL.submit(
            _prepare, analysis, self._cancellation, **kwargs))

    def _collect(self):
        if self.closed:
            return
        if self.running and self.running[1].done():
            epoch, future = self.running
            self.running = None
            try:
                snapshot = future.result()
            except Exception as exc:
                if epoch == self.epoch and self.enabled:
                    self.failed.emit(self.revision, f'{type(exc).__name__}: {exc}')
            else:
                if epoch == self.epoch and self.enabled:
                    try:
                        self.worker.submit(epoch, snapshot)
                        self._submitted = epoch
                    except Exception as exc:
                        self.failed.emit(self.revision, f'{type(exc).__name__}: {exc}')
        outcome = self.worker.poll()
        if outcome is not None and outcome.revision == self.epoch and self.enabled:
            self._submitted = None
            self.worker_pid = outcome.worker_pid
            if outcome.error is not None:
                self.failed.emit(self.revision, outcome.error)
            else:
                result = outcome.result
                self.heat = HeatModel(dict(result.owners), dict(result.scores), result.relations, self.mode,
                                      {block: dict(values) for block, values in result.states},
                                      details=dict(result.details), decay=self._options.get('decay', 1.0),
                                      views={view.node: view for view in result.semantic_views},
                                      view_details=dict(result.view_details),
                                      position_values=dict(result.position_values),
                                      position_maximum=result.position_maximum,
                                      position_snapshot=result.position_snapshot, final_details=result.final_details)
                self.ready.emit(self.revision, self.heat)
        self._dispatch()
        if not self.running and self.pending is None and self._submitted is None and not self.worker.busy:
            self.poll.stop()

    def close(self):
        if self.closed:
            return
        self._cancel()
        self.closed = True
        self.revision += 1
        self.analysis = None
        self.analysis_snapshot = None
        self.poll.stop()
        self.running = None
        self.worker.close()
