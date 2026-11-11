"""Read-only durable run history backed exclusively by .agmark archives.

Presentation never grants AcceptedRun authority. All saved pages are verified
against the archive inventory before they can be reconstructed into UI data.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from collections.abc import Mapping
from pathlib import Path
import json
import re
from threading import Lock, RLock
from weakref import WeakValueDictionary

from AgMark.gui.shell.projections import CurrentRunProjection, ExecutionBoundaryProjection, RunPlanProjection, WorkspaceProjection
from AgMark.gui.views import progress, results, reports, verification, artifacts
from AgMark.gui.artifact_actions import restore_artifact_actions
from AgMark.gui.projection.workspace.projector import WorkspaceData, render_workspace
from AgMark.shared.runtime.artifacts.archive import (
    archive_path, canonical_bytes, read_archive_member, revise_archive, validate_archive,
)

_ID = re.compile(r"generation-[a-zA-Z0-9_-]+\Z")
_REASON = "Saved history is read-only."
_GENERATION_LOCKS = WeakValueDictionary()
_GENERATION_LOCKS_GUARD = Lock()
_MODULES = (progress, results, reports, verification, artifacts)
_TYPES = {value.__name__: value for module in _MODULES for value in vars(module).values()
          if isinstance(value, type) and is_dataclass(value) and value.__module__ == module.__name__}
_TYPES.update({cls.__name__: cls for cls in (CurrentRunProjection, ExecutionBoundaryProjection, RunPlanProjection)})
from AgMark.shared.validation.codex_cache import models as _validation_models
_TYPES.update({cls.__name__: cls for cls in vars(_validation_models).values()
               if isinstance(cls,type) and is_dataclass(cls) and cls.__module__ == _validation_models.__name__})

def _noop():
    pass


def _encode(value):
    if is_dataclass(value):
        if type(value).__name__ not in _TYPES:
            raise ValueError("Unsupported history projection")
        return {"type": type(value).__name__, "fields": {f.name: _encode(getattr(value, f.name))
                for f in fields(value) if f.name != "operation" and not f.metadata.get("transient", False)}}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, (tuple, list)):
        return [_encode(v) for v in value]
    if isinstance(value, Mapping):
        return {k: _encode(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("Unsupported history value")


def _decode(value):
    if isinstance(value, list):
        return tuple(_decode(v) for v in value)
    if not isinstance(value, dict):
        return value
    if set(value) == {"decimal"}:
        return Decimal(value["decimal"])
    if set(value) == {"type", "fields"}:
        cls = _TYPES[value["type"]]
        transient = {f.name for f in fields(cls) if f.metadata.get("transient", False)}
        args = {k: _decode(v) for k, v in value["fields"].items() if k not in transient}
        if "operation" in {f.name for f in fields(cls)}:
            args.update(operation=_noop, available=False, unavailable_reason=_REASON)
        return cls(**args)
    return {k: _decode(v) for k, v in value.items()}


def history_generation_lock(root, generation_id):
    """Serialize same-generation UI snapshot and reporting revisions."""
    key = (Path(root).resolve(), generation_id)
    with _GENERATION_LOCKS_GUARD:
        lock = _GENERATION_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _GENERATION_LOCKS[key] = lock
        return lock


@dataclass(frozen=True)
class HistoricalRun:
    generation_id: str
    root: Path
    state_label: str
    state_tone: str
    timestamp: str
    note: str = ""
    ambiguous: bool = False
    diagnostic_only: bool = False

    @property
    def can_delete(self):
        try:
            self._validate_deletion()
            return True
        except (OSError, ValueError):
            return False

    def _validate_deletion(self):
        if self.diagnostic_only or self.ambiguous or not _ID.fullmatch(self.generation_id):
            raise ValueError("Invalid history generation")
        target = archive_path(self.root, self.generation_id)
        if target.is_symlink() or not target.is_file():
            raise ValueError("Archived generation is unavailable or unsafe")
        return target

    def delete(self):
        from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination
        with history_generation_lock(self.root, self.generation_id):
            self._validate_deletion()
            store = FilesystemArtifactStore(PublicationDestination.central(
                self.root, repository_root=self.root.parent.parent))
            store.delete_generation(self.generation_id)
            from AgMark.shared.runtime.completion_diagnostics import delete_completion_diagnostics
            delete_completion_diagnostics(self.root, self.generation_id)

    def presentation(self):
        return load_presentation(self)

    def prepare_presentation(self):
        return prepare_presentation(self)


def discover_history(repository_root):
    """Discover sealed archives and explicitly non-authoritative completion diagnostics."""
    root = Path(repository_root) / "AgMark" / "run_evidence"
    if root.is_symlink() or not root.is_dir():
        return {}
    found = {}
    for path in sorted(root.glob("generation-*.agmark")):
        if path.is_symlink() or not path.is_file() or not _ID.fullmatch(path.stem):
            continue
        gid = path.stem
        try:
            manifest = validate_archive(path)
            status = manifest["terminal_status"]
            label, tone = (("Blocked (saved)", "warning") if status == "blocked"
                           else ("Completed (saved)", "success"))
            from AgMark.shared.validation.run_archive import read_completion_record
            completion = read_completion_record(path)
            if completion["status"] in {"validation_failed", "report_failed"}:
                label, tone = "Report release failed (saved)", "error"
            elif completion["status"] == "complete":
                label, tone = "Report ready (saved)", "success"
            note = ("Archive integrity checks passed; saved presentation is read-only.")
            stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        except (OSError, ValueError) as exc:
            label, tone, stamp = "Evidence changed", "warning", "Unknown"
            note = "Archive integrity failed: " + str(exc)
        found[gid] = HistoricalRun(gid, root, label, tone, stamp, note)
    from AgMark.shared.runtime.completion_diagnostics import list_retained_completion_diagnostics
    for gid, diagnostics in list_retained_completion_diagnostics(root).items():
        if gid not in found:
            found[gid] = HistoricalRun(gid, root, "Completion diagnostic (saved)", "warning",
                "Unknown", "Diagnostic only; no sealed archive or report is available.", diagnostic_only=True)
    return dict(sorted(found.items(), key=lambda item: item[1].timestamp, reverse=True))


def save_presentation(root, generation_id, current, workspace):
    """Validate the retained archive; presentation never revises released bytes."""
    validate_archive(archive_path(root, generation_id))


def prepare_presentation(run):
    """Read the authoritative completion record and exact retained report bytes."""
    if run.diagnostic_only:
        return _diagnostic_only_presentation(run)
    manifest = validate_archive(archive_path(run.root, run.generation_id))
    return _native_archive_presentation(run, manifest)


def _diagnostic_only_presentation(run):
    from AgMark.gui.completion_diagnostics import retained_diagnostic_lines
    gid = run.generation_id
    lines = retained_diagnostic_lines(run.root, gid, {})
    note = "Completion diagnostic only. No sealed archive or report is available."
    current = CurrentRunProjection(gid, run.state_label, run.state_tone, run.timestamp,
        ExecutionBoundaryProjection("Unavailable", "Unavailable", "Unavailable", "Unavailable", "Unavailable"),
        RunPlanProjection("Unavailable", "Unavailable", "Unavailable", "Unavailable", "Unavailable"),
        heading="Prior Run", is_prior_run=True, delete_run_available=False)
    pages = WorkspaceData(
        progress=progress.ProgressProjection(gid, gid, None, (), None, None, (),
            summary_empty_state=note, treatment_empty_state=note, run_stage_empty_state="Run is not active."),
        results=results.ResultsProjection(gid, (), note),
        reports=reports.ReportsProjection(gid, generation_state="unavailable", verification_state="unavailable",
            empty_state=note, completion_diagnostics=lines),
        verification=verification.VerificationProjection(gid,
            verification.VerificationBannerProjection("unavailable", "—", "Unavailable", note, "neutral"),
            verification.VerificationSummaryProjection("Unavailable", "Unavailable", "unavailable",
                "Unavailable", "Unavailable", "Unavailable", "Unavailable", note),
            checks_empty_state=note),
        artifacts=artifacts.ArtifactsProjection(gid, (), "No sealed generation artifacts are available."))
    return current, pages


def _native_archive_presentation(run, manifest):
    """Build a non-authoritative archive inspector when no GUI snapshot was saved.

    This is not an imported AcceptedRun or a legacy evidence-directory fallback.
    Scores and reports are read from their retained bytes.
    """
    from zipfile import ZipFile
    from AgMark.gui.artifact_actions import artifact_actions

    gid, root = run.generation_id, run.root
    target = archive_path(root, gid)
    with ZipFile(target, "r") as source:
        sizes = {info.filename: info.file_size for info in source.infolist()}
    entries = []
    for reference, checksum in sorted(manifest["core_files"].items()):
        # Non-generation metadata stays in the validated archive but does not
        # masquerade as a benchmark artifact in the retained evidence table.
        if not reference.startswith(gid + "/"):
            continue
        actions = artifact_actions(root, gid, reference, checksum)
        name = reference.removeprefix(gid + "/")
        entries.append(artifacts.ArtifactRowProjection(
            reference, name, "▤", Path(name).suffix or "binary",
            "Retained", "•", checksum, str(sizes[reference]),
            actions[0], actions[1], reference=reference,
        ))
    observations = sum(path.endswith("/observation.json") for path in manifest["core_files"]
                       if path.startswith(gid + "/"))
    scores = sum(path.endswith("/score.json") for path in manifest["core_files"]
                 if path.startswith(gid + "/"))
    is_blocked = manifest["terminal_status"] == "blocked"
    note = ("Archive integrity checks passed. "
            "No provider invocation, rescoring, or report reconstruction was performed.")
    model, capture_details, capture_advisory, capture_tone = _archived_execution_boundary_presentation(run, manifest)
    current = CurrentRunProjection(
        gid, run.state_label, run.state_tone, run.timestamp,
        ExecutionBoundaryProjection(
            "Saved benchmark", "Saved execution", model,
            "Archived generation", manifest["core_sha256"],
            runtime_details=capture_details,
        ),
        RunPlanProjection(
            f"{observations} retained observations",
            f"{scores} retained scores",
            "Finalized blocked run" if is_blocked else "Finalized run",
            "Original result evidence retained",
            f"{len(entries)} archived generation files",
            capture_runtime_advisory=capture_advisory,
            capture_runtime_advisory_tone=capture_tone,
        ),
        heading="Prior Run", is_prior_run=True, delete_run_available=run.can_delete,
    )
    reason = "Read-only imported archive."
    pages = WorkspaceData(
        treatments_contaminated=_archive_contaminated(run, manifest),
        progress=progress.ProgressProjection(
            gid, gid, None, (), None, None, (),
            summary_empty_state=note,
            treatment_empty_state="Treatment progress is unavailable in this read-only archive view.",
            run_stage_empty_state="Run is no longer active.",
        ),
        results=_archived_unscored_results(run, manifest) if manifest["terminal_status"] == "executed" else results.ResultsProjection(
            gid, (), "Scores retained as original archive artifacts; no rescore was performed.",
        ),
        reports=_retained_report_projection(run),
        verification=verification.VerificationProjection(
            gid,
            verification.VerificationBannerProjection(
                "unavailable", "—", "Verification details unavailable", note, "neutral",
            ),
            verification.VerificationSummaryProjection(
                "Unavailable", "Unavailable", "unavailable",
                "Unavailable", "Unavailable", "Unavailable",
                manifest["core_sha256"], note,
            ),
            checks_empty_state=reason,
        ),
        artifacts=artifacts.ArtifactsProjection(
            gid, tuple(entries), "No retained generation artifacts.",
        ),
    )
    return current, pages


def _archived_execution_boundary_presentation(run, manifest):
    """Read frozen model, reasoning, and capture facts, never today's selections."""
    from AgMark.shared.telemetry.runtime_reference import PLAN_EXTENSION
    reference = run.generation_id + "/accepted-plan/plan.json"
    if reference not in manifest["core_files"]:
        return "See archived evidence", (), None, "neutral"
    document = json.loads(read_archive_member(archive_path(run.root, run.generation_id), reference),
        object_pairs_hook=_unique_object)
    from AgMark.shared.runtime.orchestration import RunPlan
    from .projector import _capture_runtime_presentation, _execution_boundary_model, _verified_plan_boundary
    plan = RunPlan.from_document(document)
    boundary_reference = run.generation_id + "/reporting-authority/execution-boundary.json"
    boundary_document = None
    model = "See archived evidence"
    if boundary_reference in manifest["core_files"]:
        boundary_document = json.loads(
            read_archive_member(archive_path(run.root, run.generation_id), boundary_reference),
            object_pairs_hook=_unique_object)
        boundary_document = _verified_plan_boundary(plan.to_dict(), boundary_document)
        model = _execution_boundary_model(boundary_document)
    if PLAN_EXTENSION not in plan.to_dict().get("extensions", {}):
        return model, (), None, "neutral"
    details, message, tone = _capture_runtime_presentation(plan.to_dict(), boundary_document)
    if message is not None:
        message = "Recorded at plan build: " + message
    return model, details, message, tone


def _archived_unscored_results(run, manifest):
    """Project retained execution-only facts without minting runtime authority."""
    from AgMark.shared.validation import SchemaIdentity, resolve_catalog_entry, validate_cataloged_document
    from AgMark.shared.reporting.results import treatment_execution_states
    from AgMark.shared.evaluation.telemetry.consumption import aggregate_treatment_measurements
    from AgMark.gui.projection.retained_evidence import _status_icon, _status_tone
    from AgMark.gui.projection.workspace.results import _measurement_details
    from AgMark.shared.telemetry.projection import project_treatment_telemetry

    schema_root = Path(__file__).resolve().parents[2] / "shared" / "schemas"
    catalog = json.loads((schema_root / "catalog.json").read_bytes())
    catalog_schema = json.loads((schema_root / "schema_catalog.schema.json").read_bytes())
    target = archive_path(run.root, run.generation_id)
    def document(reference, schema_id, filename):
        value = json.loads(read_archive_member(target, reference), object_pairs_hook=_unique_object)
        entry, issues = resolve_catalog_entry(catalog, expected=SchemaIdentity(schema_id, "1.0.0"),
            catalog_schema_document=catalog_schema)
        if issues or entry is None or entry.file != "AgMark/shared/schemas/" + filename:
            raise ValueError("Archived execution structural contract is unavailable")
        issues = validate_cataloged_document(value,
            schema_document=json.loads((schema_root / filename).read_bytes()), entry=entry, source_id=reference)
        if issues:
            raise ValueError("Invalid archived execution structure: " + issues[0].code)
        return value

    plan_reference = run.generation_id + "/accepted-plan/plan.json"
    plan = None
    slots, planned = {}, {}
    if plan_reference in manifest["core_files"]:
        plan = document(plan_reference, "arcgrav.shared.schema.run-plan", "run_plan.schema.json")
        if plan.get("extensions", {}).get("arcgrav.runtime:execution-only") is not True:
            raise ValueError("Archived executed generation lacks execution-only plan")
        slots = {slot["observation_id"]: slot for slot in plan["observations"]}
        if len(slots) != len(plan["observations"]):
            raise ValueError("Archived execution plan repeats an observation identity")
        for slot in slots.values():
            planned[slot["treatment_id"]] = planned.get(slot["treatment_id"], 0) + 1
    observations, seen = [], set()
    for reference, checksum in sorted(manifest["core_files"].items()):
        if not reference.startswith(run.generation_id + "/") or not reference.endswith("/observation.json"):
            continue
        value = document(reference, "arcgrav.shared.schema.treatment-observation", "treatment_observation.schema.json")
        slot = slots.get(value["observation_id"])
        if (value["accepted_generation_id"] != run.generation_id
                or value["observation_id"] in seen
                or (plan is not None and (
                    value["execution_boundary_fingerprint"] != plan["execution_boundary_fingerprint"]
                    or slot is None
                    or any(value[key] != slot[key] for key in ("request_id", "case_id", "treatment_id", "repetition"))))):
            raise ValueError("Archived execution observation identity mismatch")
        seen.add(value["observation_id"])
        observations.append((value, checksum))
    boundaries = {value["execution_boundary_fingerprint"] for value, _ in observations}
    if len(boundaries) > 1:
        raise ValueError("Archived execution observations mix execution boundaries")
    states = treatment_execution_states([value for value, _ in observations], planned_observations=planned or None)
    measurements = aggregate_treatment_measurements(observations, generation_id=run.generation_id,
        planned_observations=planned, boundary_fingerprint=plan["execution_boundary_fingerprint"]) if plan else {}
    rows = []
    for treatment in (states if plan is not None else sorted(states)):
        state = dict(states[treatment])
        if plan is None:
            state["planned_observations"] = None
            state["coverage_availability"] = "unavailable"
        supplied = measurements.get(treatment, {})
        status = state["status"]
        rows.append(results.ResultRowProjection(treatment=treatment, score=None,
            evidence="Retained unscored execution", status=status, status_icon=_status_icon(status),
            status_semantics=_status_tone(status), measurements=supplied.get("roles", {}),
            root_cache_policies=supplied.get("root_cache_policies", ()),
            telemetry_projection=project_treatment_telemetry(supplied), execution_summary=state,
            details="Read-only archived observations; scoring was not performed.\n"
                + ("Planned coverage and aggregates unavailable: original plan was not retained.\n" if plan is None else "")
                + _measurement_details(supplied, "retained unscored execution")))
    return results.ResultsProjection(run.generation_id, tuple(rows),
        None if rows else "No retained prompt observations.", unscored=True)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate saved presentation member")
        value[key] = item
    return value


def load_presentation(run):
    current, prepared = prepare_presentation(run)
    return current, render_workspace(prepared)


def _archive_contaminated(run, manifest):
    from AgMark.shared.treatments import contaminated
    for reference in manifest["core_files"]:
        if reference == run.generation_id + "/accepted-plan/plan.json":
            value = json.loads(read_archive_member(archive_path(run.root, run.generation_id), reference))
            if isinstance(value, dict) and value.get("schema_id") == "arcgrav.shared.schema.run-plan":
                if contaminated(value):
                    return True
    return False


def _retained_report_projection(run):
    from AgMark.shared.validation.run_archive import read_retained_report, read_completion_record
    target = archive_path(run.root, run.generation_id)
    completed = read_completion_record(target)
    retained = read_retained_report(target)
    from AgMark.gui.completion_diagnostics import retained_diagnostic_lines
    diagnostics = retained_diagnostic_lines(run.root, run.generation_id, completed)
    disabled = reports.ReportActionProjection(_noop, False, "Reports are completed automatically; saved runs are read-only.")
    if retained is None:
        return reports.ReportsProjection(run.generation_id,
            generation_state=completed["status"], completion_diagnostics=diagnostics,
            verification_state=completed["validation"]["status"],
            empty_state=completed["validation"].get("diagnostic") or "No scored report was released for this run.")
    def export():
        from PySide6.QtWidgets import QFileDialog, QApplication
        destination, _ = QFileDialog.getSaveFileName(QApplication.activeWindow(), "Export Report", "report.md", "Markdown (*.md);;All files (*)")
        if destination:
            try:
                export_retained_report(run, retained.report_id, destination)
            except (OSError, ValueError) as exc:
                from AgMark.gui.artifact_actions import _error
                _error(str(exc))
    document = retained.report_document
    return reports.ReportsProjection(run.generation_id,
        report_id=retained.report_id, readable_content=retained.markdown_bytes.decode("utf-8"),
        generation_state=completed["status"], verification_state=completed["validation"]["status"],
        completeness=document.get("status", "complete"), generated_at=document.get("generated_at", "Retained with run"),
        limitations="Archive integrity checks passed.",
        export_action=reports.ReportActionProjection(export, True), completion_diagnostics=diagnostics)


def export_retained_report(run, report_id, destination):
    """Revalidate on export and copy the exact retained bytes atomically."""
    import os
    import tempfile
    from AgMark.shared.validation.run_archive import read_retained_report
    retained = read_retained_report(archive_path(run.root, run.generation_id))
    if retained is None or retained.report_id != report_id:
        raise ValueError("Retained report identity changed")
    target = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".agmark-report-", delete=False) as output:
            temporary = Path(output.name)
            output.write(retained.markdown_bytes)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
