"""Production workspace projection from exact shared lifecycle authority.

This module converts retained shared terminal, report, and reconstruction
verification objects into the five desktop workspace views.  It is deliberately
benchmark-neutral: presentation is derived only from shared public authority and
canonical report evidence, and unavailable presentation data remains explicit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
import json
from numbers import Real
from pathlib import Path
from typing import Protocol

from AgMark.shared.reporting import (
    GeneratedReportBundle,
    GeneratedReportComponent,
)
from AgMark.shared.runtime.artifacts import ArtifactRecord, FilesystemArtifactStore
from AgMark.shared.runtime.orchestration import AcceptedRun, ExecutedRun, BlockedRun, RunPlan

from AgMark.gui.shell.window import WorkspaceProjection
from AgMark.gui.views.artifacts import (
    ArtifactActionProjection,
    ArtifactRowProjection,
    ArtifactsProjection,
    ArtifactsView,
)
from AgMark.gui.views.progress import (
    OverallProgressProjection,
    ProgressEventProjection,
    ProgressProjection,
    ProgressView,
    TreatmentProgressProjection,
)
from AgMark.gui.views.reports import (
    ReportActionProjection,
    ReportsProjection,
    ReportsView,
)
from AgMark.gui.views.results import (
    ResultRowProjection,
    ResultsProjection,
    ResultsView,
)
from AgMark.gui.views.verification import (
    VerificationBannerProjection,
    VerificationCheckProjection,
    VerificationProjection,
    VerificationSummaryProjection,
    VerificationView,
)


_EXECUTION_WINDOW_EXTENSION = "arcgrav.shared.runtime.orchestration:execution-window"

from ..retained_evidence import _decode_retained_json_documents, _diagnostics_text, _mapping, _numeric, _sequence, _status_icon, _status_tone, _visible
from AgMark.shared.telemetry.projection import project_treatment_telemetry

def _measurement_details(measurements, evidence, metric=None):
    lines = [f"Evidence: {evidence}"]
    if metric:
        lines.append("Registered metric: " + json.dumps(metric, ensure_ascii=False, default=str))
        if metric.get("aggregation"):
            lines.append(
                f"Aggregation: {metric['aggregation']}; "
                f"denominator {metric.get('denominator')} {metric.get('denominator_unit')}; "
                f"evaluated observations {metric.get('evaluated_observations')}"
            )
    for role, entry in measurements.get("roles", {}).items():
        lines.extend([f"{role}: {entry.get('availability')} ({entry.get('unit')})",
                      f"Value: {entry.get('value')}; kind: {entry.get('kind')}; method: {entry.get('method')}",
                      f"Source: {entry.get('source')}; meaning: {entry.get('meaning')}",
                      "Details: " + json.dumps(entry.get("details", {}), ensure_ascii=False, default=str),
                      "Evidence references: " + ", ".join(entry.get("evidence_references", ()))])
    lines.append("Efficiency: " + json.dumps(measurements.get("efficiency", {"availability": "unavailable"}), default=str))
    for session in measurements.get("sessions", ()):
        lines.extend(["", f"Trial: {session['observation_id']}; attempt: {session['attempt']}",
                      f"Thread: {session['thread_id']}; model: {session['model']}; reasoning: {session['reasoning_effort']}",
                      "Session measurements: " + json.dumps(session, ensure_ascii=False, default=str)])
    return "\n".join(lines)

def _results_projection(
    terminal: AcceptedRun | BlockedRun,
    bundle: GeneratedReportBundle | None,
    *, plan=None, store=None,
) -> ResultsProjection:
    run_id = terminal.generation_id
    rows: list[ResultRowProjection] = []
    from AgMark.shared.reporting.results import treatment_execution_states
    planned = {}
    if plan is not None:
        for slot in plan.observations:
            planned[slot.treatment_id] = planned.get(slot.treatment_id, 0) + 1
    validations = {}
    validation_diagnostic = None
    if type(terminal) in (AcceptedRun, ExecutedRun) and store is not None:
        from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore
        try:
            validations = {v.treatment_id: v for v in ValidationArtifactStore(store).read(terminal)}
        except (ValueError, OSError) as exc:
            validation_diagnostic = f"Replay validation unavailable: {exc}"
    from AgMark.shared.evaluation.telemetry import retained_run_measurements
    try:
        measurements = retained_run_measurements(terminal, plan=plan, store=store)
    except ValueError as exc:
        return ResultsProjection(run_id=run_id, empty_state=f"Retained measurement authority unavailable: {exc}")
    execution_states = treatment_execution_states(getattr(terminal, "treatment_observations", ()),
        planned_observations=planned, cancelled=getattr(terminal, "cancelled", False))
    if type(terminal) is ExecutedRun:
        observations = [json.loads(raw) for raw in terminal.treatment_observations]
        treatments = tuple(dict.fromkeys(slot.treatment_id for slot in plan.observations)) if plan else tuple(measurements)
        for treatment_id in treatments:
            items = [o for o in observations if o["treatment_id"] == treatment_id]
            execution = execution_states.get(treatment_id, {})
            expected = execution.get("planned_observations", len(items))
            status = execution.get("status", "unavailable")
            details = [f"{len(items)} of {expected} observations retained."]
            for observation in items:
                details.append(f"Iteration {observation['repetition']}: {observation['terminal_status']}")
                details.extend(_diagnostics_text(observation))
            supplied = measurements.get(treatment_id, {})
            rows.append(ResultRowProjection(treatment=treatment_id, score=None, evidence=status,
                status=status, status_icon=_status_icon(status), status_semantics=_status_tone(status),
                measurements=supplied.get("roles", {}), root_cache_policies=supplied.get("root_cache_policies", ()), validation=validations.get(treatment_id),
                telemetry_projection=project_treatment_telemetry(supplied),
                execution_summary=execution_states.get(treatment_id, {}),
                details="\n".join(details) + "\n" + _measurement_details(supplied, status)))
        return ResultsProjection(run_id=run_id, rows=tuple(rows), unscored=True,
            empty_state=None if rows else "No prompts were executed.")
    evidence = _mapping(
        getattr(bundle, "canonical_evidence_document", None)
        if type(bundle) is GeneratedReportBundle
        else None
    )
    if type(terminal) in (AcceptedRun, ExecutedRun):
        score_documents, score_diagnostics = _decode_retained_json_documents(
            getattr(terminal, "score_artifacts", ()),
            label="score artifact",
        )
        if store is not None and plan is not None:
            from AgMark.shared.reporting.results import (
                registered_rate_summary, registered_score_details, score_details_text,
            )
            registrations = [json.loads(store.read_verified(r)) for r in terminal.artifact_index.artifacts if r.role == "metric_registration"]
            if len(registrations) != 1:
                raise ValueError("Results requires the exact registered primary metric")
            grouped = {}
            for score in score_documents:
                grouped.setdefault(score["treatment_id"], []).append(score)
            for treatment_id, scores in grouped.items():
                registered = registered_rate_summary(scores, registrations[0])
                states = tuple(dict.fromkeys(str(score.get("availability", "unavailable")) for score in scores))
                state = execution_states.get(treatment_id, {}).get("status", "unavailable")
                supplied = measurements.get(treatment_id, {})
                details = _measurement_details(supplied, ", ".join(states), registered)
                retained_score_details = registered_score_details(scores, registrations[0])
                comparison_details = score_details_text(retained_score_details)
                if comparison_details:
                    details += "\n\n" + comparison_details
                if validation_diagnostic:
                    details += "\n" + validation_diagnostic
                rows.append(ResultRowProjection(treatment=treatment_id, score=registered["value"], evidence=", ".join(states),
                    status=state, status_icon=_status_icon(state), status_semantics=_status_tone(state),
                    measurements=supplied.get("roles", {}), root_cache_policies=supplied.get("root_cache_policies", ()), details=details,
                    score_details=tuple(retained_score_details),
                    telemetry_projection=project_treatment_telemetry(supplied),
                    execution_summary=execution_states.get(treatment_id, {}),
                    validation=validations.get(treatment_id)))
            if rows:
                return ResultsProjection(run_id=run_id, rows=tuple(rows))
        for score in score_documents:
            treatment_id = score.get("treatment_id")
            if not isinstance(treatment_id, str) or not treatment_id.strip():
                treatment_id = _visible(score.get("score_artifact_id"), "score")
            availability = _visible(score.get("availability"), "unavailable")
            diagnostics = _diagnostics_text(score)
            diagnostic_text = "; ".join(diagnostics)
            run_state = execution_states.get(treatment_id, {}).get("status")
            rows.append(
                ResultRowProjection(
                    treatment=treatment_id,
                    validation=validations.get(treatment_id),
                    measurements=measurements.get(treatment_id, {}).get("roles", {}),
                    telemetry_projection=project_treatment_telemetry(measurements.get(treatment_id, {})),
                    execution_summary=execution_states.get(treatment_id, {}),
                    root_cache_policies=measurements.get(treatment_id, {}).get("root_cache_policies", ()),
                    details=_measurement_details(measurements.get(treatment_id, {}), availability, {"metric": score.get("metric"), "metric_registration": score.get("metric_registration"), "unit": score.get("unit"), "evaluated_observations": score.get("count", 1)}) + ("\n" + validation_diagnostic if validation_diagnostic else ""),
                    score=_numeric(score.get("value")),
                    evidence=(
                        availability
                        if not diagnostic_text
                        else f"{availability}: {diagnostic_text}"
                    ),
                    status=(
                        (run_state or "Run unavailable")
                        + (f"; score {availability}: {diagnostic_text}" if diagnostic_text else "")
                    ),
                    status_icon=_status_icon(run_state or availability),
                    status_semantics=_status_tone(run_state or availability),
                )
            )
        for index, diagnostic in enumerate(score_diagnostics, start=1):
            rows.append(
                ResultRowProjection(
                    treatment=f"score-artifact-{index}",
                    score=None,
                    evidence="decode_error",
                    status=diagnostic,
                    status_icon=_status_icon("decode_error"),
                    status_semantics=_status_tone("decode_error"),
                )
            )
        if rows:
            return ResultsProjection(run_id=run_id, rows=tuple(rows))
    if type(terminal) is BlockedRun:
        reason = _visible(getattr(terminal, "reason_code", None), "blocked")
        empty = (
            f"Run {run_id} is BlockedRun ({reason}); no accepted treatment "
            "summary is available."
        )
    elif type(bundle) is GeneratedReportBundle:
        empty = (
            "The generated shared report contains no treatment-summary rows "
            "for this retained run."
        )
    else:
        empty = (
            "No benchmark-neutral treatment summary is retained for this "
            "AcceptedRun yet."
        )
    return ResultsProjection(run_id=run_id, rows=(), empty_state=empty)


def active_results_projection(generation_id, plan, store):
    from AgMark.shared.evaluation.telemetry.consumption import active_treatment_measurements
    measurements = active_treatment_measurements(generation_id, plan, store)
    unscored = plan.to_dict().get("extensions", {}).get("arcgrav.runtime:execution-only") is True
    return ResultsProjection(run_id=generation_id, unscored=unscored, rows=tuple(
        ResultRowProjection(treatment=treatment, score=None, evidence="active/incomplete",
            status="Executing", status_icon="●", status_semantics="info", measurements=value["roles"],
            root_cache_policies=value.get("root_cache_policies", ()),
            telemetry_projection=project_treatment_telemetry(value, provisional=True),
            execution_summary={"status": "executing", "provisional": True},
            details=_measurement_details(value, "Execution in progress." if unscored else "Retained active evidence; Accuracy not finalized."))
        for treatment, value in measurements.items()))
