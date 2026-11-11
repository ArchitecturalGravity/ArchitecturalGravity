"""Read-only .agmark integrity inspection and explicitly untrusted archive import.

An internally consistent manifest does not prove execution, authorship, or
authenticity. Optional caller-supplied SHA-256 anchors must be obtained from an
independently trusted publisher (for example, GitHub provenance attestation).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import tempfile

from AgMark.shared.runtime.artifacts.archive import (
    ArchiveError, archive_path, validate_archive, _publication_lock, _sync_directory,
)

_GENERATION = re.compile(r"generation-[A-Za-z0-9_-]+\Z")


@dataclass(frozen=True, slots=True)
class RunArchiveValidation:
    generation_id: str | None
    status: str
    files_checked: int
    issues: tuple[str, ...]

    def __post_init__(self):
        if self.status not in {"consistent", "invalid"} or self.files_checked < 0:
            raise ValueError("invalid imported run validation result")
        if (self.status == "consistent") != (not self.issues):
            raise ValueError("consistent result must have no issues")

    @property
    def consistent(self) -> bool:
        return self.status == "consistent"


def _whole_file_hash(path: Path) -> str:
    state = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            state.update(block)
    return "sha256:" + state.hexdigest()


def validate_run_archive(
    snapshot_path: str | Path, *, expected_archive_sha256: str | None = None
) -> RunArchiveValidation:
    """Validate complete .agmark archive (retaining the existing public API name).

    The result never grants AcceptedRun, reconstruction, or publication authority.
    """
    if not isinstance(snapshot_path, (str, Path)):
        raise TypeError("snapshot_path must be a file path")
    source = Path(snapshot_path)
    generation_id = source.stem if _GENERATION.fullmatch(source.stem) else None
    try:
        manifest = validate_archive(source)
        if expected_archive_sha256 is not None:
            expected = expected_archive_sha256
            if not isinstance(expected, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
                raise ArchiveError("invalid independent archive hash supplied")
            if _whole_file_hash(source) != expected:
                raise ArchiveError("archive bytes differ from trusted external SHA-256")
        return RunArchiveValidation(manifest["generation_id"], "consistent",
                                     len(manifest["files"]), ())
    except (OSError, ValueError) as exc:
        return RunArchiveValidation(generation_id, "invalid", 0, (str(exc),))


def import_run_archive(
    source_path: str | Path, repository_root: str | Path,
    *, expected_archive_sha256: str | None = None
) -> Path:
    """Copy a validated archive into central run history; never rehydrate authority."""
    inspection = validate_run_archive(
        source_path, expected_archive_sha256=expected_archive_sha256)
    if not inspection.consistent or inspection.generation_id is None:
        raise ArchiveError("import refused: " + "; ".join(inspection.issues))
    repository = Path(repository_root).resolve(strict=True)
    if not repository.is_dir() or (repository / "AgMark").is_symlink():
        raise ArchiveError("invalid repository owner for imported run")
    root = repository / "AgMark" / "run_evidence"
    if root.is_symlink():
        raise ArchiveError("run-evidence root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    if not root.resolve(strict=True).is_relative_to(repository):
        raise ArchiveError("archive import path escapes repository")
    source = Path(source_path).resolve(strict=True)
    with _publication_lock(root, inspection.generation_id):
        target = archive_path(root, inspection.generation_id)
        gid = inspection.generation_id
        conflicts = [target, root / gid,
                     *(root / ("." + gid + suffix) for suffix in
                       (".deleted", ".generation-claim", ".terminal")),
                     root / ".agmark-validation" / gid,
                     root / ".agmark-progress" / (gid + ".json")]
        if any(path.exists() or path.is_symlink() for path in conflicts):
            raise ArchiveError("imported generation identity is already retained, active, or deleted")
        fd, temp_name = tempfile.mkstemp(dir=root, prefix=".agmark-import-", suffix=".tmp")
        temporary = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as output, source.open("rb") as stream:
                shutil.copyfileobj(stream, output, 1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            # Repeat content checks against the *copied* bytes, not just the input.
            validate_archive(temporary, _expected_generation_id=inspection.generation_id)
            if expected_archive_sha256 is not None and _whole_file_hash(temporary) != expected_archive_sha256:
                raise ArchiveError("copied archive differs from trusted external SHA-256")
            # Hardlink installation is no-overwrite and atomic; temporary and target
            # are in the same directory/filesystem. No partial archive is published.
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise ArchiveError("import destination appeared concurrently") from exc
            validate_archive(target)
            _sync_directory(root)
            return target
        finally:
            temporary.unlink(missing_ok=True)



__all__ = ["RunArchiveValidation", "validate_run_archive", "import_run_archive"]


@dataclass(frozen=True, slots=True)
class RetainedRunReport:
    """Producer's exact retained report; integrity is not execution authenticity."""

    generation_id: str
    report_id: str
    markdown_bytes: bytes
    report_document: dict
    completion_record: dict
    markdown_reference: str
    markdown_sha256: str


def read_completion_record(path: str | Path) -> dict:
    """Read the supported sealed completion record, never rerun release policy."""
    from AgMark.shared.runtime.artifacts.archive import COMPLETION_MEMBER, _json, read_archive_member
    return _json(read_archive_member(path, COMPLETION_MEMBER))


def read_retained_report(path: str | Path) -> RetainedRunReport | None:
    """Open exact validated report bytes, with no regeneration or verifier path."""
    from AgMark.shared.runtime.artifacts.archive import _json, read_archive_member
    record = read_completion_record(path)
    if record["status"] != "complete":
        return None
    report = record["report"]
    components = {item["role"]: item for item in report["components"]}
    markdown = components["markdown"]
    return RetainedRunReport(
        generation_id=record["generation_id"], report_id=report["report_id"],
        markdown_bytes=read_archive_member(path, markdown["reference"]),
        report_document=_json(read_archive_member(path, components["machine_json"]["reference"])),
        completion_record=record, markdown_reference=markdown["reference"],
        markdown_sha256=markdown["sha256"],
    )


__all__ += ["RetainedRunReport", "read_completion_record", "read_retained_report"]
