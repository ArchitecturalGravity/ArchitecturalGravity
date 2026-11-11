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

from ..retained_evidence import _mapping, _sequence, _status_icon, _status_tone, _visible

def _verification_projection(terminal, bundle, verification, commands):
    run_id = terminal.generation_id
    ready = type(bundle) is GeneratedReportBundle
    status = "passed" if ready else "unavailable"
    note = (None if ready else "No completed report is available. See Reports for the completion outcome.")
    return VerificationProjection(
        run_id=run_id,
        banner=VerificationBannerProjection(status, "✓" if ready else "—", "Completion validation passed" if ready else "Report unavailable", note, "success" if ready else "neutral"),
        summary=VerificationSummaryProjection("Completion record", "Retained with run", status, "Run completion", "See archive", "See archive", "See retained evidence", note),
        checks=(), checks_empty_state=note,
    )
