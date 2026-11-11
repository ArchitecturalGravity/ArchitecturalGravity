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

from ..retained_evidence import _completed_status, _decode_retained_json_documents, _observation_event_timestamp, _observation_stage, _observation_status, _observation_status_text, _plan_treatment_totals, _retained_generation_documents, _status_icon, _status_tone, _visible

def active_retained_progress_projection(
    generation_id: str,
    plan: RunPlan,
    artifact_store: FilesystemArtifactStore,
) -> ProgressProjection:
    """Project active retained observations/scores without creating run authority."""

    if not isinstance(generation_id, str) or not generation_id.strip():
        raise ValueError("generation_id must be a non-empty string")
    if type(plan) is not RunPlan:
        raise ValueError("plan must be a RunPlan")
    if type(artifact_store) is not FilesystemArtifactStore:
        raise ValueError("artifact_store must be a FilesystemArtifactStore")

    observations = tuple(plan.observations)
    if not observations:
        return _active_progress_projection(generation_id, plan)

    observation_documents, observation_diagnostics = _retained_generation_documents(
        artifact_store.root,
        generation_id,
        stage_prefix="observation-",
        filename="observation.json",
    )
    score_documents, score_diagnostics = _retained_generation_documents(
        artifact_store.root,
        generation_id,
        stage_prefix="score-",
        filename="score.json",
    )

    observed_by_id: dict[str, Mapping[str, object]] = {}
    for document in observation_documents:
        observation_id = document.get("observation_id")
        if isinstance(observation_id, str) and observation_id:
            observed_by_id[observation_id] = document

    treatment_totals = _plan_treatment_totals(plan)
    treatment_completed = {treatment_id: 0 for treatment_id in treatment_totals}
    treatment_latest: dict[str, Mapping[str, object]] = {}
    completed_slots = 0
    for slot in observations:
        document = observed_by_id.get(slot.observation_id)
        if document is None:
            continue
        status = _observation_status(document)
        if _completed_status(status):
            completed_slots += 1
            treatment_completed[slot.treatment_id] = (
                treatment_completed.get(slot.treatment_id, 0) + 1
            )
        treatment_latest[slot.treatment_id] = document

    scoring_started = bool(score_documents)
    active_stage_index = 3 if scoring_started else 2
    active_stage_description = (
        f"Scoring retained observations for {generation_id}."
        if scoring_started
        else (
            f"Executing accepted observations for {generation_id}; "
            f"{len(observed_by_id)} of {len(observations)} observation artifact(s) "
            "are retained."
        )
    )
    if score_documents and len(score_documents) >= len(observations):
        active_stage_index = 4
        active_stage_description = (
            "All available score artifacts are retained; finalization is pending."
        )

    treatments: list[TreatmentProgressProjection] = []
    for treatment_id, total in treatment_totals.items():
        completed = treatment_completed.get(treatment_id, 0)
        latest = treatment_latest.get(treatment_id)
        if latest is not None:
            status = _observation_status(latest)
            status_text = _observation_status_text(latest)
            stage = _observation_stage(latest)
            icon = _status_icon(status)
            semantics = _status_tone(status)
        elif observed_by_id:
            status_text = "Waiting"
            stage = "Execution"
            icon = "•"
            semantics = "neutral"
        else:
            status_text = "Starting"
            stage = "Execution"
            icon = "•"
            semantics = "neutral"
        treatments.append(
            TreatmentProgressProjection(
                treatment_id=treatment_id,
                treatment=treatment_id,
                completed_cases=completed,
                total_cases=total,
                current_stage=stage,
                status=status_text,
                status_icon=icon,
                status_semantics=semantics,
            )
        )

    events: list[ProgressEventProjection] = []
    for slot in observations:
        document = observed_by_id.get(slot.observation_id)
        if document is None:
            continue
        status = _observation_status(document)
        events.append(
            ProgressEventProjection(
                generation_id=generation_id,
                timestamp=_observation_event_timestamp(document),
                event_icon=_status_icon(status),
                text=f"{slot.treatment_id}: {_observation_status_text(document)}.",
            )
        )
    for index, score in enumerate(score_documents, start=1):
        status = _visible(score.get("availability"), "scored")
        treatment = _visible(score.get("treatment_id"), f"score-{index}")
        events.append(
            ProgressEventProjection(
                generation_id=generation_id,
                timestamp="Retained score evidence",
                event_icon=_status_icon(status),
                text=f"{treatment}: score artifact retained ({status}).",
            )
        )
    for diagnostic in (*observation_diagnostics, *score_diagnostics):
        events.append(
            ProgressEventProjection(
                generation_id=generation_id,
                timestamp="Retained evidence",
                event_icon=_status_icon("decode_error"),
                text=diagnostic,
            )
        )
    if not events:
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        events.append(
            ProgressEventProjection(
                generation_id=generation_id,
                timestamp=started_at,
                event_icon="•",
                text="Accepted execution request dispatched.",
            )
        )

    return ProgressProjection(
        run_id=generation_id,
        generation_id=generation_id,
        run_active=True,
        unscored=plan.to_dict().get("extensions", {}).get("arcgrav.runtime:execution-only") is True,
        overall=OverallProgressProjection(
            completed_cases=completed_slots,
            total_cases=len(observations),
            elapsed_time="Active",
        ),
        treatments=tuple(treatments),
        active_stage_index=active_stage_index,
        active_stage_description=active_stage_description,
        events=tuple(events),
        
        
    )

def _active_progress_projection(
    generation_id: str,
    plan: RunPlan,
) -> ProgressProjection:
    """Project exact accepted-plan work as presentation-only execution-start state."""

    if not isinstance(generation_id, str) or not generation_id.strip():
        raise ValueError("generation_id must be a non-empty string")
    if type(plan) is not RunPlan:
        raise ValueError("plan must be a RunPlan")

    observations = tuple(plan.observations)
    if not observations:
        raise ValueError("active execution progress requires planned observations")

    treatment_totals = _plan_treatment_totals(plan)

    stage_index = 1 if plan.golden_required else 2
    stage_name = "Golden Admission" if plan.golden_required else "Execution"
    stage_description = (
        "Accepted execution has started with required golden admission before "
        "treatment execution."
        if plan.golden_required
        else "Accepted execution has started for the exact accepted observation plan."
    )
    treatment_status = "Waiting" if plan.golden_required else "Starting"

    treatments = tuple(
        TreatmentProgressProjection(
            treatment_id=treatment_id,
            treatment=treatment_id,
            completed_cases=0,
            total_cases=total,
            current_stage=stage_name,
            status=treatment_status,
            status_icon="•",
            status_semantics="neutral",
        )
        for treatment_id, total in treatment_totals.items()
    )
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    return ProgressProjection(
        run_id=generation_id,
        generation_id=generation_id,
        run_active=True,
        unscored=plan.to_dict().get("extensions", {}).get("arcgrav.runtime:execution-only") is True,
        overall=OverallProgressProjection(
            completed_cases=0,
            total_cases=len(observations),
            elapsed_time="0s",
        ),
        treatments=treatments,
        active_stage_index=stage_index,
        active_stage_description=stage_description,
        events=(
            ProgressEventProjection(
                generation_id=generation_id,
                timestamp=started_at,
                event_icon="•",
                text="Accepted execution request dispatched.",
            ),
        ),
        
        
    )

def _progress_projection(
    terminal: AcceptedRun | BlockedRun,
    artifact_store=None,
) -> ProgressProjection:
    run_id = terminal.generation_id
    if type(terminal) in (AcceptedRun, ExecutedRun):
        observation_documents, decode_diagnostics = _decode_retained_json_documents(
            getattr(terminal, "treatment_observations", ()),
            label="treatment observation",
        )
        treatments: list[TreatmentProgressProjection] = []
        events: list[ProgressEventProjection] = []
        treatment_counts: dict[str, int] = {}
        completed_count = 0
        for index, observation in enumerate(observation_documents, start=1):
            treatment = _visible(
                observation.get("treatment_id"),
                f"observation-{index}",
            )
            treatment_counts[treatment] = treatment_counts.get(treatment, 0) + 1
            row_id = (
                treatment
                if treatment_counts[treatment] == 1
                else f"{treatment}#{treatment_counts[treatment]}"
            )
            status = _observation_status(observation)
            completed = _completed_status(status)
            if completed:
                completed_count += 1
            status_text = _observation_status_text(observation)
            treatments.append(
                TreatmentProgressProjection(
                    treatment_id=row_id,
                    treatment=treatment,
                    completed_cases=1 if completed else 0,
                    total_cases=1,
                    current_stage=_observation_stage(observation),
                    status=status_text,
                    status_icon=_status_icon(status),
                    status_semantics=_status_tone(status),
                )
            )
            events.append(
                ProgressEventProjection(
                    generation_id=run_id,
                    timestamp=_observation_event_timestamp(observation),
                    event_icon=_status_icon(status),
                    text=f"{treatment}: {status_text}.",
                )
            )
        for diagnostic in decode_diagnostics:
            events.append(
                ProgressEventProjection(
                    generation_id=run_id,
                    timestamp="Retained evidence",
                    event_icon=_status_icon("decode_error"),
                    text=diagnostic,
                )
            )
        active_stage_index = 4
        stage_description = (
            "Shared finalization produced AcceptedRun authority with "
            f"{completed_count} of {len(observation_documents)} retained treatment "
            "observation(s) completed."
            if observation_documents
            else "Shared finalization produced AcceptedRun authority."
        )
        stage_empty = None
        overall = (
            OverallProgressProjection(
                completed_cases=completed_count,
                total_cases=len(observation_documents),
                elapsed_time="Retained",
            )
            if observation_documents
            else None
        )
        summary_empty = (
            None
            if observation_documents
            else (
                "Terminal AcceptedRun authority retained no decodable treatment "
                "observations."
            )
        )
        treatment_empty = (
            None
            if treatments
            else (
                "Terminal AcceptedRun authority retained no decodable per-treatment "
                "progress rows."
            )
        )
        events_empty = (
            None
            if events
            else (
                "No generation-bound progress events are retained by this "
                "application boundary."
            )
        )
    else:
        active_stage_index = None
        stage_description = None
        stage_empty = (
            "BlockedRun does not identify a single presentation-safe active "
            "lifecycle stage."
        )
        overall = None
        treatments = []
        events = []
        summary_empty = (
            "Terminal shared authority does not supply elapsed-time or "
            "case-progress counters."
        )
        treatment_empty = (
            "Terminal shared authority does not supply per-treatment progress "
            "rows."
        )
        events_empty = (
            "No generation-bound progress events are retained by this "
            "application boundary."
        )

    projection = ProgressProjection(
        run_id=run_id,
        generation_id=run_id,
        unscored=type(terminal) is ExecutedRun,
        lifecycle_complete=type(terminal) in (AcceptedRun, ExecutedRun) and not getattr(terminal, "cancelled", False),
        overall=overall,
        treatments=tuple(treatments),
        active_stage_index=active_stage_index,
        active_stage_description=stage_description,
        events=tuple(events),
        summary_empty_state=summary_empty,
        treatment_empty_state=treatment_empty,
        run_stage_empty_state=stage_empty,
        
        
        
    )

    from .activity import with_retained_activity
    return with_retained_activity(projection, artifact_store)
