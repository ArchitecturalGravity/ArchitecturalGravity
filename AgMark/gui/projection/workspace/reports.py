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
from AgMark.shared.runtime.orchestration import AcceptedRun, BlockedRun, RunPlan

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

from ..retained_evidence import _mapping, _sequence, _status_icon, _visible

def _noop() -> None:
    return None


def _report_components(
    bundle: GeneratedReportBundle | None,
    verification: None,
) -> tuple[GeneratedReportComponent, ...]:
    components: dict[str, GeneratedReportComponent] = {}
    if type(bundle) is GeneratedReportBundle:
        for value in _sequence(getattr(bundle, "components", ())):
            if type(value) is GeneratedReportComponent:
                components[value.artifact_id] = value
        manifest = getattr(bundle, "manifest", None)
        if type(manifest) is GeneratedReportComponent:
            components[manifest.artifact_id] = manifest
    return tuple(components.values())

def _reports_projection(terminal, bundle, verification, commands, *, generation_state=None, generation_reason=None, export_feedback="", completion_diagnostics=()):
    run_id = terminal.generation_id
    disabled = ReportActionProjection(_noop, False, "Reports are completed automatically with the run.")
    if type(bundle) is not GeneratedReportBundle:
        return ReportsProjection(run_id=run_id, 
            generation_state=generation_state or "unavailable",
            verification_state="failed" if generation_state == "validation_failed" else "unavailable",
            empty_state=generation_reason or ("Report release failed. Retained evidence remains available." if generation_state in {"validation_failed", "report_failed"} else "A scored report is not applicable to this run."),
            export_feedback=export_feedback, completion_diagnostics=completion_diagnostics)
    report = bundle.report_document
    if report.get("accepted_generation_id") != run_id:
        raise ValueError("report generation does not match selected run")
    report_id = report["report_id"]
    export = getattr(commands, "request_export_report", None)
    return ReportsProjection(run_id=run_id, report_id=report_id, 
        readable_content=bundle.human.data.decode(bundle.human.encoding), generation_state="complete",
        completeness=report["status"], generated_at=report["generated_at"], verification_state="passed",
        limitations="Synthetic conformance evidence from deterministic fixtures; no live model measurements." if report.get("extensions", {}).get("arcgrav.reporting:synthetic-conformance") else "",
        export_action=ReportActionProjection((lambda: export(run_id, report_id)) if callable(export) else _noop,
            callable(export), None if callable(export) else "No caller-owned export operation supplied."),
        export_feedback=export_feedback, completion_diagnostics=completion_diagnostics)
