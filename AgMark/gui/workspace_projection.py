"""Compatibility façade for the workspace projection package."""

from .projection.retained_evidence import (
    _attempt_count,
    _attempt_text,
    _byte_count_text,
    _completed_status,
    _decode_retained_json_documents,
    _diagnostics_text,
    _mapping,
    _nonempty_text,
    _numeric,
    _observation_event_timestamp,
    _observation_stage,
    _observation_status,
    _observation_status_text,
    _plan_treatment_totals,
    _retained_generation_documents,
    _sequence,
    _status_icon,
    _status_tone,
    _telemetry,
    _terminal_records,
    _visible,
)
from .projection.workspace.artifacts import _artifacts_projection
from .projection.workspace.progress import (
    _active_progress_projection,
    _progress_projection,
    active_retained_progress_projection,
)
from .projection.workspace.projector import (
    SharedWorkspaceProjector,
    WorkspaceBoundary,
    WorkspaceCommands,
    _noop,
)
from .projection.workspace.reports import _report_components, _reports_projection
from .projection.workspace.results import _results_projection
from .projection.workspace.verification import _verification_projection
