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
from AgMark.shared.adapters.execution import (
    CanonicalObservationError,
    validate_retained_parity_observation,
)

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

def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}

def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()

def _visible(value: object, fallback: str = "Unavailable") -> str:
    return value if isinstance(value, str) and value.strip() else fallback

def _numeric(value: object) -> Real | Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (Real, Decimal)):
        return value
    return None

def _status_tone(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {
        "accepted",
        "available",
        "completed",
        "retained",
        "scored",
        "succeeded",
        "verified",
    }:
        return "success"
    if normalized in {"failed", "invalid", "mismatched", "blocked"}:
        return "error"
    if normalized in {
        "decode_error",
        "missing",
        "unavailable",
        "excluded",
        "non_scorable",
    }:
        return "warning"
    return "neutral"

def _status_icon(status: str) -> str:
    tone = _status_tone(status)
    if tone == "success":
        return "✓"
    if tone == "error":
        return "✕"
    if tone == "warning":
        return "!"
    return "•"

def _terminal_records(
    terminal: AcceptedRun | BlockedRun,
) -> tuple[ArtifactRecord, ...]:
    if type(terminal) in (AcceptedRun, ExecutedRun):
        index = getattr(terminal, "artifact_index", None)
        records = getattr(index, "artifacts", ())
    else:
        manifest = getattr(terminal, "artifact_manifest", None)
        records = getattr(manifest, "retained_diagnostics", ())
    return tuple(
        value for value in _sequence(records) if type(value) is ArtifactRecord
    )

def _decode_retained_json_documents(
    values: object,
    *,
    label: str,
) -> tuple[tuple[Mapping[str, object], ...], tuple[str, ...]]:
    documents: list[Mapping[str, object]] = []
    diagnostics: list[str] = []
    for index, raw in enumerate(_sequence(values), start=1):
        if not isinstance(raw, (bytes, bytearray)):
            diagnostics.append(
                f"Retained {label} {index} is not UTF-8 JSON bytes."
            )
            continue
        try:
            decoded = bytes(raw).decode("utf-8")
            value = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            diagnostics.append(
                f"Retained {label} {index} could not be decoded as UTF-8 JSON: "
                f"{exc.__class__.__name__}."
            )
            continue
        if not isinstance(value, Mapping):
            diagnostics.append(f"Retained {label} {index} is not a JSON object.")
            continue
        if label == "treatment observation":
            try:
                validate_retained_parity_observation(value)
            except CanonicalObservationError:
                diagnostics.append(
                    f"Retained {label} {index} has invalid canonical execution evidence."
                )
                continue
        documents.append(value)
    return tuple(documents), tuple(diagnostics)

def _nonempty_text(value: object) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""

def _telemetry(document: Mapping[str, object]) -> Mapping[str, object]:
    values: dict[str, object] = {}
    for item in _sequence(document.get("telemetry")):
        entry = _mapping(item)
        name = entry.get("name")
        if isinstance(name, str) and name:
            values[name] = entry.get("value")
    return values

def _byte_count_text(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return f"{value:,} B"

def _observation_status(document: Mapping[str, object]) -> str:
    return _visible(document.get("terminal_status"), "unavailable")

def _completed_status(status: str) -> bool:
    return status.strip().lower() in {"accepted", "completed", "scored", "succeeded"}

def _attempt_count(document: Mapping[str, object]) -> int:
    return len(_sequence(document.get("attempts")))

def _attempt_text(count: int) -> str:
    return f"{count} attempt" if count == 1 else f"{count} attempts"

def _observation_stage(document: Mapping[str, object]) -> str:
    window = _mapping(_mapping(document.get("extensions")).get(_EXECUTION_WINDOW_EXTENSION))
    completed = _nonempty_text(window.get("completed_at"))
    if completed:
        return f"Execution completed {completed}"
    started = _nonempty_text(window.get("started_at"))
    if started:
        return f"Execution started {started}"
    return "Execution"

def _observation_event_timestamp(document: Mapping[str, object]) -> str:
    window = _mapping(_mapping(document.get("extensions")).get(_EXECUTION_WINDOW_EXTENSION))
    return (
        _nonempty_text(window.get("completed_at"))
        or _nonempty_text(window.get("started_at"))
        or "Retained evidence"
    )

def _observation_status_text(document: Mapping[str, object]) -> str:
    status = _observation_status(document).replace("_", " ").title()
    telemetry = _telemetry(document)
    parts = [status, _attempt_text(_attempt_count(document))]
    response_bytes = _byte_count_text(telemetry.get("response_bytes"))
    stderr_bytes = _byte_count_text(telemetry.get("stderr_bytes"))
    if response_bytes is not None:
        parts.append(f"response {response_bytes}")
    if stderr_bytes is not None:
        parts.append(f"stderr {stderr_bytes}")
    return "; ".join(parts)

def _diagnostics_text(document: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in _sequence(document.get("diagnostics"))
        if isinstance(value, str) and value.strip()
    )

def _plan_treatment_totals(plan: RunPlan) -> dict[str, int]:
    totals: dict[str, int] = {}
    for observation in plan.observations:
        totals[observation.treatment_id] = (
            totals.get(observation.treatment_id, 0) + 1
        )
    return totals

def _retained_generation_documents(
    root: Path,
    generation_id: str,
    *,
    stage_prefix: str,
    filename: str,
) -> tuple[tuple[Mapping[str, object], ...], tuple[str, ...]]:
    from AgMark.shared.runtime.artifacts.archive import archive_path, read_archive_member, validate_archive
    generation = root / generation_id
    archive = archive_path(root, generation_id)
    documents: list[Mapping[str, object]] = []
    diagnostics: list[str] = []
    if archive.exists() or archive.is_symlink():
        try:
            manifest = validate_archive(archive)
            names = sorted(name for name in manifest["core_files"]
                if name.startswith(generation_id + "/" + stage_prefix)
                and name.endswith("/" + filename)
                and name.count("/") == 2)
            retained = [(name, read_archive_member(archive, name)) for name in names]
        except (OSError, ValueError) as exc:
            return (), ("Archived evidence is invalid: " + str(exc),)
    elif generation.is_dir():
        # An active, not-yet-terminal invocation still publishes into a staging tree.
        retained = []
        for path in sorted(generation.glob(f"{stage_prefix}*/{filename}")):
            try:
                retained.append((path.relative_to(root).as_posix(), path.read_bytes()))
            except OSError as exc:
                diagnostics.append("Active artifact unavailable: " + str(exc))
    else:
        return (), ()

    for name, raw in retained:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            diagnostics.append(
                f"Retained {name} could not be decoded: {exc.__class__.__name__}."
            )
            continue
        if not isinstance(value, Mapping):
            diagnostics.append(f"Retained {name} is not a JSON object.")
            continue
        if filename == "observation.json":
            try:
                validate_retained_parity_observation(value)
            except CanonicalObservationError:
                diagnostics.append(f"Retained {name} has invalid canonical execution evidence.")
                continue
        documents.append(value)
    return tuple(documents), tuple(diagnostics)
