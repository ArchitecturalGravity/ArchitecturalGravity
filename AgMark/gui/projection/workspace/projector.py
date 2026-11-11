"""Production workspace projection from exact shared lifecycle authority.

This module converts retained shared terminal, report, and reconstruction
verification objects into the desktop workspace views.  It is deliberately
benchmark-neutral: presentation is derived only from shared public authority and
canonical report evidence, and unavailable presentation data remains explicit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass, replace
from AgMark.shared.treatments import contaminated
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
from AgMark.gui.views.evidence import EvidenceProjection, EvidenceView
from AgMark.gui.views.scoring import ScoringView
from AgMark.gui.views.artifacts import (
    ArtifactActionProjection,
    ArtifactRowProjection,
    ArtifactsProjection,
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

from .progress import _active_progress_projection, _progress_projection, active_retained_progress_projection
from .results import _results_projection
from .reports import _reports_projection
from .verification import _verification_projection
from .artifacts import _artifacts_projection


@contextmanager
def _workspace_verified_reads(store, generation_id):
    """Share verified archive reads without changing unavailable projections.

    Stores without this optional capability retain their original read path.
    Initial archive rejection also uses that path so each projection can render
    its existing unavailable diagnostic. Drift during an admitted operation is
    still raised, including at scope exit.
    """
    operation = getattr(store, "verified_reads", None)
    if not callable(operation):
        yield
        return
    scope = ExitStack()
    try:
        scope.enter_context(operation(generation_id))
    except (ValueError, OSError):
        scope.close()
        yield
    else:
        with scope:
            yield


class WorkspaceBoundary(Protocol):
    """Shared application state required by the workspace projection."""

    @property
    def selected_terminal(self) -> AcceptedRun | BlockedRun | None:
        ...

    @property
    def report_bundle(self) -> GeneratedReportBundle | None:
        ...

    @property
    def verification(self) -> None:
        ...

class WorkspaceCommands(Protocol):
    """Caller-owned actions that workspace controls may invoke."""



def _noop() -> None:
    """Unavailable presentation action."""


@dataclass(frozen=True)
class WorkspaceData:
    """Prepared page data; construction performs no QWidget operations."""

    progress: ProgressProjection
    results: ResultsProjection
    reports: ReportsProjection
    verification: VerificationProjection
    artifacts: ArtifactsProjection
    treatments_contaminated: bool = False


def render_workspace(prepared: WorkspaceData) -> WorkspaceProjection:
    """Construct widgets from prepared projections on the GUI thread only."""
    if prepared.treatments_contaminated:
        prepared = replace(prepared,
            reports=replace(prepared.reports, limitations="Treatments Contaminated. " + prepared.reports.limitations))
    return WorkspaceProjection(
        treatments_contaminated=prepared.treatments_contaminated,
        progress=ProgressView(prepared.progress), scoring=ScoringView(prepared.results),
        results=ResultsView(prepared.results),
        reports=ReportsView(prepared.reports), verification=VerificationView(prepared.verification),
        evidence=EvidenceView(EvidenceProjection(prepared.progress, prepared.artifacts, prepared.treatments_contaminated)),
    )

class SharedWorkspaceProjector:
    """Default production projector for retained and active shared-authority state."""

    def __init__(self, boundary: WorkspaceBoundary) -> None:
        self._boundary = boundary

    def active_execution(
        self,
        generation_id: str,
        plan: RunPlan,
    ) -> WorkspaceProjection:
        """Build the normal workspace for one exact accepted execution start."""

        progress = _active_progress_projection(generation_id, plan)
        active_reason = (
            "This view is unavailable until accepted execution reaches retained "
            "terminal authority."
        )
        report_reason = (
            "Report generation is unavailable until an AcceptedRun is retained."
        )
        report_action = ReportActionProjection(
            operation=_noop,
            available=False,
            unavailable_reason=report_reason,
        )
        verification_reason = (
            "Completion validation and report release run automatically after execution."
        )
        active_results = ResultsProjection(
            run_id=generation_id,
            rows=(),
            empty_state=active_reason,
            unscored=plan.to_dict().get("extensions", {}).get("arcgrav.runtime:execution-only") is True,
        )
        return WorkspaceProjection(
            treatments_contaminated=contaminated(plan.to_dict()),
            progress=ProgressView(progress),
            scoring=ScoringView(active_results),
            results=ResultsView(active_results),
            reports=ReportsView(
                ReportsProjection(
                    run_id=generation_id,
                    empty_state=report_reason,
                )
            ),
            verification=VerificationView(
                VerificationProjection(
                    run_id=generation_id,
                    banner=VerificationBannerProjection(
                        status="unavailable",
                        icon="—",
                        heading="Unavailable",
                        summary=verification_reason,
                        tone="neutral",
                    ),
                    summary=VerificationSummaryProjection(
                        manifest_id="Unavailable",
                        verification_time="Unavailable",
                        result="unavailable",
                        verified_by="Unavailable",
                        artifacts_checked="Unavailable",
                        total_size="Unavailable",
                        boundary_fingerprint=plan.execution_boundary_fingerprint,
                        notes=verification_reason,
                    ),
                    checks=(),
                    checks_empty_state=verification_reason,
                )
            ),
            evidence=EvidenceView(
                EvidenceProjection(
                    progress,
                    ArtifactsProjection(
                        run_id=generation_id,
                        rows=(),
                        empty_state="Saved files will appear here when the run finishes retaining its evidence.",
                    ),
                    contaminated(plan.to_dict()),
                )
            ),
        )

    def prepare_result(
        self,
        command: str,
        result: object,
        commands: WorkspaceCommands,
    ) -> WorkspaceData | None:
        if command in {"start_benchmark", "select_run"}:
            terminal = result
        else:
            terminal = self._boundary.selected_terminal

        if type(terminal) not in (AcceptedRun, BlockedRun, ExecutedRun):
            return None

        evidence = getattr(self._boundary, "workspace_evidence", None)
        bundle, verification = (evidence(terminal.generation_id) if callable(evidence)
                                else (self._boundary.report_bundle, self._boundary.verification))
        if type(bundle) is not GeneratedReportBundle:
            bundle = None

        context = getattr(self._boundary, "run_context", lambda _: None)(terminal.generation_id)
        is_contaminated = contaminated(context.plan.to_dict()) if context else (
            contaminated(json.loads(terminal.run_outcome_bytes)) if type(terminal) is AcceptedRun else False)
        store = getattr(self._boundary, "artifact_store", lambda _: None)(terminal.generation_id)
        with _workspace_verified_reads(store, terminal.generation_id):
            return WorkspaceData(
                treatments_contaminated=is_contaminated,
                progress=_progress_projection(terminal,
                    getattr(self._boundary, "artifact_store", lambda _: None)(terminal.generation_id)),
                results=_results_projection(terminal, bundle,
                    plan=getattr(getattr(self._boundary, "run_context", lambda _: None)(terminal.generation_id), "plan", None),
                    store=getattr(self._boundary, "artifact_store", lambda _: None)(terminal.generation_id)),
                reports=_reports_projection(terminal, bundle, verification, commands,
                        generation_state=getattr(self._boundary, "report_state", lambda _: (None, None))(terminal.generation_id)[0],
                        generation_reason=getattr(self._boundary, "report_state", lambda _: (None, None))(terminal.generation_id)[1],
                        completion_diagnostics=getattr(self._boundary, "completion_diagnostics", lambda _: ())(terminal.generation_id),
                        export_feedback=getattr(self._boundary, "export_feedback", lambda *args: "")(terminal.generation_id, bundle.report_document["report_id"]) if bundle else ""),
                verification=_verification_projection(
                        terminal,
                        bundle,
                        verification,
                        commands,
                ),
                artifacts=_artifacts_projection(terminal, bundle, verification,
                        store=getattr(self._boundary, "artifact_store", lambda _: None)(terminal.generation_id)),
            )

    @staticmethod
    def render(prepared: WorkspaceData) -> WorkspaceProjection:
        return render_workspace(prepared)

    def __call__(self, command, result, commands):
        prepared = self.prepare_result(command, result, commands)
        return None if prepared is None else self.render(prepared)


__all__ = ["SharedWorkspaceProjector", "WorkspaceData", "render_workspace", "active_retained_progress_projection"]
