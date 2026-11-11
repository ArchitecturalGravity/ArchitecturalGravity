"""Render typed shared progress; never parse telemetry or infer metric values."""
from dataclasses import replace
from AgMark.shared.runtime.orchestration.activity import capture_source_window
from AgMark.gui.views.progress import CaptureSourceProjection

_PHASE_LABELS = {
    "admission": "Checking accepted execution prerequisites…",
    "preflight": "Discovering stock CLI capture capabilities…",
    "collector_readiness": "Starting invocation collectors and checking readiness…",
    "execution": "Running accepted cases…",
    "capture": "Capturing invocation sources…",
    "drain": "Draining stdout, stderr and process lifecycle…",
    "flush": "Flushing local telemetry receivers…",
    "rollout_settlement": "Waiting for bounded exact-thread rollout settlement…",
    "evidence_validation": "Validating and sealing captured evidence…",
    "normalization": "Normalizing versioned telemetry facts…",
    "aggregation": "Aggregating compatible original-run measurements…",
    "evaluation": "Evaluating scored cases…",
    "finalization": "Finalizing scored results…",
    "capability": "Checking HTTP and WebSocket replay capabilities…",
    "validation_retention": "Saving and checking validation evidence…",
    "cleanup": "Cleaning up temporary replay profiles…",
    "completion": "Run lifecycle finished.",
}
_SOURCE_LABELS = {"stdout": "stdout JSONL", "stderr": "stderr", "process": "Process lifecycle",
    "rollout": "Exact-thread rollout", "otel_logs": "OTel logs", "otel_traces": "OTel traces",
    "otel_metrics": "OTel metrics", "diagnostics": "Sensitive diagnostics"}
_CAPTURE_STAGE_STEPS = {
    "preflight": 1,
    "collector_readiness": 2,
    "execution": 3,
    "capture": 3,
    "drain": 4,
    "flush": 4,
    "rollout_settlement": 4,
    "evidence_validation": 5,
    "normalization": 6,
    "aggregation": 6,
    "completion": 7,
}
_CAPTURE_STAGES = {
    "preflight": "1 · Preflight / capability discovery",
    "collector_readiness": "2 · Collector readiness",
    "execution": "3 · Execution / source capture",
    "capture": "3 · Execution / source capture",
    "drain": "4 · Stream drain",
    "flush": "4 · Receiver flush",
    "rollout_settlement": "4 · Bounded rollout settlement",
    "evidence_validation": "5 · Evidence validation / sealing",
    "normalization": "6 · Normalization",
    "aggregation": "6 · Compatible aggregation",
    "completion": "7 · Completion",
}


def activity_text(event):
    if event.phase == "completion" and not event.terminal:
        return "Invocation " + event.benchmark_outcome.replace("_", " ") + "; run finalization is pending."
    if event.phase == "replay":
        return f"Validating replay {event.current} of {event.total} (non-scored)…"
    if event.terminal:
        outcome = {"cancelled": "Cancelled; available evidence and final capture health retained.",
                   "failed": "Benchmark failed; available capture health retained.",
                   "blocked": "Benchmark blocked before completion.",
                   "interrupted": "Run interrupted; finalization was not confirmed.",
                   "timed_out": "Benchmark timed out; available capture health retained.",
                   "unsupported": "Benchmark execution unsupported; capability reasons retained.",
                   "completed_with_failures": "Run finalized with failed observations or attempts."}.get(event.benchmark_outcome)
        if outcome:
            return outcome
        if event.telemetry_outcome in {"failed", "partial", "unavailable"}:
            return "Benchmark finalized; telemetry " + event.telemetry_outcome + "."
    return _PHASE_LABELS[event.phase]


def _source_projection(source):
    identity = " / ".join(filter(None, (
        "Original Run" if source.scope == "original" else "Validation Replay",
        source.treatment_id, source.attempt_id or source.invocation_id)))
    return CaptureSourceProjection(
        capture=identity, source=_SOURCE_LABELS[source.source_id], state=source.state,
        events="—" if source.state in {"disabled", "unsupported", "unavailable"} and not source.received_events else str(source.received_events),
        bytes="—" if source.state in {"disabled", "unsupported", "unavailable"} and not source.received_bytes else str(source.received_bytes),
        health=f"Partial {source.partial} · Dropped {source.dropped} · Rejected {source.rejected} · Parse errors {source.parse_errors}",
        reason=source.reason.replace("_", " ") if source.reason else "—",
        scope=source.scope, invocation_id=source.invocation_id,
        treatment_id=source.treatment_id, attempt_id=source.attempt_id)


def with_activity(projection, event, elapsed_seconds):
    if projection.generation_id != event.generation_id:
        return projection
    text = activity_text(event)
    stage = {"admission": 1, "preflight": 1, "collector_readiness": 2, "execution": 2,
             "capture": 2, "drain": 2, "flush": 2, "rollout_settlement": 2,
             "evidence_validation": 2, "normalization": 2, "aggregation": 3,
             "evaluation": 3}.get(event.phase, 4)
    overall = projection.overall
    if overall is not None:
        seconds = int(max(event.elapsed_seconds, elapsed_seconds))
        overall = replace(overall, elapsed_time=f"{seconds // 60:02d}:{seconds % 60:02d}")
        if not event.terminal and stage == 4 and overall.completed_cases == overall.total_cases:
            text = ("Cases complete. " if projection.unscored else "Scored cases complete. ") + text
    scope = {"original": "Original Run", "replay": "Validation Replay", "run": "Run"}[event.scope]
    identity = " / ".join(filter(None, (scope, event.treatment_id,
                                       event.attempt_id or event.invocation_id)))
    treatments = projection.treatments
    if event.treatment_id and not event.terminal:
        treatments = tuple(replace(row, current_stage=_CAPTURE_STAGES.get(event.phase, text),
                                   status="Finalizing capture" if event.phase in {"drain", "flush", "rollout_settlement", "evidence_validation", "normalization"} else row.status)
                           if row.treatment_id == event.treatment_id else row for row in treatments)
    evidence = ("Evidence sealed (original captures)" if event.evidence_sealed and all(source.scope == "original" for source in event.sources) else
                "Evidence sealed" if event.evidence_sealed else
                "Evidence unsealed / unavailable" if event.terminal else
                "Provisional — evidence not yet sealed")
    if event.scope == "replay" and not event.terminal:
        evidence += "; validation replay finalization pending"
    window = capture_source_window(event)
    capture_summary = None
    if window.omitted_source_count:
        capture_summary = (f"Showing {window.shown_invocation_count} recent captures; "
            f"{window.omitted_invocation_count} earlier captures / {window.omitted_source_count} source rows "
            "remain in saved progress. Counts below apply to each displayed capture.")
    return replace(projection, overall=overall, treatments=treatments, active_stage_index=stage,
        active_stage_description=text, run_stage_empty_state=None, activity_text=text,
        current_stage_step=_CAPTURE_STAGE_STEPS.get(event.phase),
        run_active=not event.terminal, lifecycle_complete=event.finalization_complete,
        capture_sources=tuple(_source_projection(source) for source in window.sources),
        capture_summary=capture_summary,
        capture_stage=_CAPTURE_STAGES.get(event.phase), capture_identity=identity,
        evidence_status=evidence, benchmark_status=("Invocation: " if event.scope in {"original", "replay"} and event.invocation_id is not None and not event.terminal else "Benchmark: ") + event.benchmark_outcome.replace("_", " "),
        telemetry_status="Telemetry: " + event.telemetry_outcome)


def with_retained_activity(projection, artifact_store):
    if artifact_store is None:
        return projection
    from AgMark.shared.runtime.orchestration.activity import retained_activity
    event = retained_activity(artifact_store.root, projection.generation_id)
    return with_activity(projection, event, event.elapsed_seconds) if event is not None else projection
