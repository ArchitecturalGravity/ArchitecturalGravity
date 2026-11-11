"""Versioned, payload-free lifecycle progress; never score or evidence authority.

Collectors publish only typed health/count snapshots. The shared publisher owns
sequence ordering and persistence; frontends do not parse captured telemetry.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
import re
from threading import RLock
from time import monotonic
import os
import tempfile

PHASES = frozenset({"admission", "execution", "evaluation", "finalization",
    "capability", "replay", "validation_retention", "cleanup", "preflight",
    "collector_readiness", "capture", "drain", "flush", "rollout_settlement",
    "evidence_validation", "normalization", "aggregation", "completion"})
SOURCE_STATES = frozenset({"pending", "disabled", "unsupported", "ready", "active",
    "settled", "partial", "unavailable", "failed"})
OUTCOMES = frozenset({"pending", "complete", "partial", "unavailable", "failed", "cancelled", "blocked", "interrupted", "timed_out", "unsupported", "completed_with_failures"})
_SOURCES = frozenset({"stdout", "stderr", "process", "rollout", "otel_logs", "otel_traces", "otel_metrics", "diagnostics"})
_SAFE_CODE = re.compile(r"[a-zA-Z0-9_.:/-]{1,240}\Z")
_ACTIVE = ContextVar("agmark_activity_publisher", default=None)


def _identity(value):
    return value is None or (isinstance(value, str) and bool(_SAFE_CODE.fullmatch(value)))


@dataclass(frozen=True)
class CaptureSourceActivity:
    source_id: str
    state: str
    received_events: int = 0
    received_bytes: int = 0
    dropped: int = 0
    rejected: int = 0
    parse_errors: int = 0
    partial: int = 0
    reason: str | None = None
    scope: str = "original"
    invocation_id: str | None = None
    treatment_id: str | None = None
    attempt_id: str | None = None

    def __post_init__(self):
        if self.source_id not in _SOURCES or self.state not in SOURCE_STATES or self.scope not in {"original", "replay"}:
            raise ValueError("invalid capture source identity or state")
        if any(type(value) is not int or value < 0 for value in (
            self.received_events, self.received_bytes, self.dropped, self.rejected, self.parse_errors, self.partial)):
            raise ValueError("invalid capture source count")
        if any(not _identity(value) for value in (self.reason, self.invocation_id, self.treatment_id, self.attempt_id)):
            raise ValueError("capture progress accepts safe identifiers/reason codes only")


REGISTERED_OUTCOMES = {"completed": "complete", "failed": "failed", "timed_out": "timed_out",
                       "cancelled": "cancelled", "unsupported": "unsupported"}


@dataclass(frozen=True)
class InvocationBenchmarkOutcome:
    invocation_id: str
    scope: str
    registered_outcome: str
    outcome: str
    treatment_id: str | None = None
    attempt_id: str | None = None

    def __post_init__(self):
        if self.scope not in {"original", "replay"} or not self.invocation_id or any(
                not _identity(value) for value in (self.invocation_id, self.treatment_id, self.attempt_id)):
            raise ValueError("invalid invocation outcome identity")
        if REGISTERED_OUTCOMES.get(self.registered_outcome) != self.outcome:
            raise ValueError("invalid registered invocation outcome")


def benchmark_outcome_from_observations(observations, *, cancelled=False, blocked=False):
    """Summarize registered execution outcomes, independently of score/telemetry.

    Historical failed attempts remain visible even after a successful retry.
    Unknown or unreadable original outcome evidence cannot become success.
    """
    if cancelled:
        return "cancelled"
    if blocked:
        return "blocked"
    terminal_states, attempt_states = [], []
    try:
        for raw in observations:
            observation = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            if not isinstance(observation, Mapping) or observation.get("terminal_status") not in REGISTERED_OUTCOMES:
                return "unavailable"
            terminal_states.append(observation["terminal_status"])
            for attempt in observation.get("attempts", ()):
                if not isinstance(attempt, Mapping) or attempt.get("status") not in REGISTERED_OUTCOMES:
                    return "unavailable"
                attempt_states.append(attempt["status"])
    except (ValueError, TypeError, UnicodeError):
        return "unavailable"
    if not terminal_states:
        return "unavailable"
    states = terminal_states + attempt_states
    if "cancelled" in terminal_states:
        return "cancelled"
    failures = set(states) - {"completed"}
    if not failures:
        return "complete"
    if "completed" in terminal_states:
        return "completed_with_failures"
    if len(set(terminal_states)) == 1:
        return REGISTERED_OUTCOMES[terminal_states[0]]
    return "failed"


@dataclass(frozen=True)
class RunActivity:
    generation_id: str
    sequence: int
    phase: str
    elapsed_seconds: float
    current: int = 0
    total: int = 0
    scope: str = "run"
    treatment_id: str | None = None
    attempt_id: str | None = None
    invocation_id: str | None = None
    sources: tuple[CaptureSourceActivity, ...] = ()
    evidence_sealed: bool = False
    benchmark_outcome: str = "pending"
    telemetry_outcome: str = "pending"
    terminal: bool = False
    finalization_complete: bool | None = None
    invocation_outcomes: tuple[InvocationBenchmarkOutcome, ...] = ()
    omitted_source_count: int = 0
    omitted_invocation_count: int = 0

    def __post_init__(self):
        if not isinstance(self.generation_id, str) or not self.generation_id or self.phase not in PHASES:
            raise ValueError("invalid activity identity or phase")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("invalid activity sequence")
        if type(self.elapsed_seconds) not in (float, int) or not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError("invalid activity elapsed time")
        if any(type(v) is not int for v in (self.current, self.total)) or not 0 <= self.current <= self.total:
            raise ValueError("invalid activity counts")
        if any(type(value) is not int or value < 0 for value in (self.omitted_source_count, self.omitted_invocation_count)):
            raise ValueError("invalid omitted capture counts")
        if self.scope not in {"run", "original", "replay"} or any(not _identity(value) for value in (self.treatment_id, self.attempt_id, self.invocation_id)):
            raise ValueError("invalid activity scope or identity")
        if self.benchmark_outcome not in OUTCOMES or self.telemetry_outcome not in OUTCOMES:
            raise ValueError("invalid activity outcome")
        if type(self.evidence_sealed) is not bool or type(self.terminal) is not bool:
            raise ValueError("invalid activity completion")
        if self.finalization_complete is None:
            object.__setattr__(self, "finalization_complete", self.terminal and self.benchmark_outcome in {"complete", "completed_with_failures"})
        if type(self.finalization_complete) is not bool or (self.finalization_complete and not self.terminal):
            raise ValueError("invalid lifecycle finalization")
        if any(type(value) is not InvocationBenchmarkOutcome for value in self.invocation_outcomes):
            raise ValueError("invalid invocation outcomes")
        object.__setattr__(self, "invocation_outcomes", tuple(self.invocation_outcomes))
        if any(type(value) is not CaptureSourceActivity for value in self.sources):
            raise ValueError("invalid capture source snapshot")
        object.__setattr__(self, "sources", tuple(self.sources))


class ActivityPublisher:
    def __init__(self, generation_id, callback=None, *, persistence_root=None):
        self.generation_id, self.callback = generation_id, callback
        self.started, self.sequence = monotonic(), 0
        self.persistence_root = persistence_root
        self.latest = None
        self._lock = RLock()
        self._sources = {}
        self._source_groups = {}
        self._latest_source_group = {}
        self._sealed = {}
        self._outcomes = {}
        self._invocation_outcomes = {}
        self._last_persisted = None

    @contextmanager
    def bind(self):
        token = _ACTIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE.reset(token)

    def emit(self, phase, current=0, total=0, **details):
        with self._lock:
            if self.latest is not None and self.latest.terminal:
                return self.latest
            scope = details.setdefault("scope", "replay" if phase in {"capability", "replay", "validation_retention", "cleanup"} else "run")
            invocation = details.get("invocation_id")
            registered_outcome = details.pop("registered_benchmark_outcome", None)
            if registered_outcome in REGISTERED_OUTCOMES and invocation is not None and scope in {"original", "replay"}:
                outcome = InvocationBenchmarkOutcome(invocation, scope, registered_outcome,
                    REGISTERED_OUTCOMES[registered_outcome], details.get("treatment_id"), details.get("attempt_id"))
                self._invocation_outcomes[(scope, invocation, outcome.attempt_id)] = outcome
                details["benchmark_outcome"] = outcome.outcome
            for source in details.pop("sources", ()):
                self._record_source(source)
            if invocation is not None:
                key = (scope, invocation)
                self._sealed[key] = details.pop("evidence_sealed", self._sealed.get(key, False))
                self._outcomes[key] = details.pop("telemetry_outcome", self._outcomes.get(key, "pending"))
            details.setdefault("evidence_sealed", bool(self._sealed) and all(self._sealed.values()))
            details.setdefault("telemetry_outcome", self._telemetry_outcome())
            current_outcome = self._invocation_outcomes.get((scope, invocation, details.get("attempt_id")))
            default_outcome = (current_outcome.outcome if current_outcome is not None else "pending") if invocation is not None else (self.latest.benchmark_outcome if self.latest else "pending")
            details.setdefault("benchmark_outcome", default_outcome)
            visible_sources, visible_invocations = self._recent_sources(scope, invocation)
            visible_groups = {(source.scope, source.invocation_id) for source in visible_sources}
            if invocation is not None:
                visible_groups.add((scope, invocation))
            visible_outcomes = tuple(outcome for outcome in self._invocation_outcomes.values()
                                     if (outcome.scope, outcome.invocation_id) in visible_groups)[-2:]
            if len(visible_outcomes) < 2:
                recent_outcomes = list(visible_outcomes)
                for key in reversed(self._invocation_outcomes):
                    outcome = self._invocation_outcomes[key]
                    if outcome not in recent_outcomes:
                        recent_outcomes.append(outcome)
                    if len(recent_outcomes) == 2:
                        break
                visible_outcomes = tuple(recent_outcomes)
            self.sequence += 1
            event = RunActivity(self.generation_id, self.sequence, phase,
                max(0.0, monotonic() - self.started), current, total,
                sources=visible_sources, invocation_outcomes=visible_outcomes, omitted_source_count=len(self._sources) - len(visible_sources),
                omitted_invocation_count=len(self._source_groups) - visible_invocations, **details)
            self.latest = event
            self._persist(event)
            if self.callback is not None:
                try:
                    self.callback(event)
                except Exception:
                    # A disconnected presentation client cannot gate work.
                    pass
            return event

    def _record_source(self, source):
        self._sources[(source.scope, source.invocation_id, source.source_id)] = source
        group = (source.scope, source.invocation_id)
        self._source_groups.setdefault(group, {})[source.source_id] = source
        self._latest_source_group[source.scope] = group

    def _recent_sources(self, scope, invocation):
        selected = []
        active = (scope, invocation)
        if active in self._source_groups:
            selected.append(active)
        for group in self._latest_source_group.values():
            if group not in selected:
                selected.append(group)
        if len(selected) < 2:
            for group in reversed(self._source_groups):
                if group not in selected:
                    selected.append(group)
                if len(selected) == 2:
                    break
        selected = selected[:2]
        return tuple(source for group in selected for source in self._source_groups[group].values()), len(selected)

    def _telemetry_outcome(self):
        states = set(self._outcomes.values())
        if not states:
            return "unavailable"
        for value in ("failed", "pending", "partial", "unavailable"):
            if value in states:
                return value
        return "complete"

    def finish(self, benchmark_outcome, *, finalization_complete=None):
        with self._lock:
            for key, source in tuple(self._sources.items()):
                if source.state in {"pending", "ready", "active"}:
                    self._record_source(replace(source, state="partial", partial=max(1, source.partial),
                                                 reason="finalization_not_confirmed"))
        telemetry = self._telemetry_outcome()
        if telemetry == "pending":
            telemetry = "partial" if self._sources else "unavailable"
        return self.emit("completion", terminal=True, benchmark_outcome=benchmark_outcome,
                         finalization_complete=finalization_complete, telemetry_outcome=telemetry, scope="run")

    def _persist(self, event):
        if self.persistence_root is None:
            return
        previous = self._last_persisted
        if previous is not None and not event.terminal and event.elapsed_seconds - previous.elapsed_seconds < 1.0:
            return
        try:
            path = _progress_path(self.persistence_root, self.generation_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink() or path.parent.is_symlink():
                return
            with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".progress-", delete=False) as stream:
                temporary = Path(stream.name)
                # Callbacks stay bounded; disk retains every invocation source.
                activity = asdict(event)
                activity.update(sources=[asdict(source) for source in self._sources.values()],
                                invocation_outcomes=[asdict(outcome) for outcome in self._invocation_outcomes.values()],
                                omitted_source_count=0, omitted_invocation_count=0)
                json.dump({"schema_version": "agmark.progress/1", "activity": activity}, stream, separators=(",", ":"))
            try:
                os.replace(temporary, path)
                self._last_persisted = event
            finally:
                temporary.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            # Progress persistence is presentation-only and never gates scoring.
            pass


@dataclass(frozen=True)
class CaptureSourceWindow:
    sources: tuple[CaptureSourceActivity, ...]
    omitted_source_count: int
    omitted_invocation_count: int
    shown_invocation_count: int


def capture_source_window(event):
    """Select active/recent progress groups, without aggregating telemetry."""
    groups = {}
    latest = {}
    for source in event.sources:
        group = (source.scope, source.invocation_id)
        groups.setdefault(group, []).append(source)
        latest[source.scope] = group
    selected = []
    active = (event.scope, event.invocation_id)
    if active in groups:
        selected.append(active)
    for group in latest.values():
        if group not in selected:
            selected.append(group)
    for group in reversed(groups):
        if len(selected) >= 2:
            break
        if group not in selected:
            selected.append(group)
    selected = selected[:2]
    sources = tuple(source for group in selected for source in groups[group])
    return CaptureSourceWindow(sources,
        event.omitted_source_count + len(event.sources) - len(sources),
        event.omitted_invocation_count + len(groups) - len(selected), len(selected))


def _progress_path(root, generation_id):
    if not re.fullmatch(r"generation-[a-zA-Z0-9_-]+", generation_id):
        raise ValueError("invalid progress generation")
    return Path(root) / ".agmark-progress" / (generation_id + ".json")


def retained_activity(root, generation_id):
    """Load typed safe progress, without interpreting provider evidence."""
    try:
        path = _progress_path(root, generation_id)
        from AgMark.shared.runtime.artifacts.archive import archive_path, read_archive_member
        sealed = archive_path(Path(root), generation_id)
        if sealed.exists():
            raw = read_archive_member(sealed, ".agmark-progress/" + generation_id + ".json")
            if len(raw) > 64_000_000:
                return None
            document = json.loads(raw)
        else:
            if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size > 64_000_000:
                return None
            document = json.loads(path.read_text())
        if document.get("schema_version") != "agmark.progress/1":
            return None
        fields = document["activity"]
        fields["sources"] = tuple(CaptureSourceActivity(**row) for row in fields["sources"])
        fields["invocation_outcomes"] = tuple(InvocationBenchmarkOutcome(**row) for row in fields.get("invocation_outcomes", ()))
        event = RunActivity(**fields)
        return event if event.generation_id == generation_id else None
    except (OSError, ValueError, TypeError, KeyError):
        return None


def delete_retained_activity(root, generation_id):
    path = _progress_path(root, generation_id)
    if not path.parent.is_symlink() and not path.is_symlink():
        path.unlink(missing_ok=True)


def capture_progress_callback(**context):
    """Bind publisher on the invoking thread before collectors create threads."""
    publisher = _ACTIVE.get()
    if publisher is None:
        return lambda _snapshot: None
    return lambda snapshot: _publish_capture_progress(publisher, snapshot, context)


def publish_capture_progress(snapshot, **context):
    """Adapter boundary for payload-free collector progress mappings."""
    publisher = _ACTIVE.get()
    if publisher is not None:
        _publish_capture_progress(publisher, snapshot, context)


def _publish_capture_progress(publisher, snapshot, context):
    try:
        values = dict(snapshot)
        scope = values.get("scope", context.get("scope", "original"))
        identity = {key: values.get(key, context.get(key)) for key in ("treatment_id", "attempt_id", "invocation_id")}
        sources = []
        for raw in values.get("sources", ()):
            row = {key: raw[key] for key in ("source_id", "state", "received_events", "received_bytes", "dropped", "rejected", "parse_errors", "partial", "reason") if key in raw}
            # Receiver reasons must remain codes, never payload/error messages.
            if not _identity(row.get("reason")):
                row["reason"] = "source_reported_unavailability"
            if type(row.get("partial")) is bool:
                row["partial"] = int(row["partial"])
            sources.append(CaptureSourceActivity(**row, scope=scope, **identity))
        completion = {key: values[key] for key in ("evidence_sealed", "telemetry_outcome") if key in values}
        if values.get("benchmark_outcome") in REGISTERED_OUTCOMES:
            completion["registered_benchmark_outcome"] = values["benchmark_outcome"]
        publisher.emit(values["phase"], scope=scope, sources=tuple(sources), **identity, **completion)
    except (ValueError, TypeError, KeyError):
        # Malformed presentation metadata cannot interrupt collection.
        return
