"""Immutable pre-terminal evidence retention for accepted generations.

This module complements terminal artifact publication with a narrow staging
primitive for evidence that must be durably fixed before later lifecycle stages
may begin. It preserves the same filesystem authority, exact-byte identity, and
secret-admission rules as the runtime artifact store without creating accepted
or blocked terminal authority.
"""

from __future__ import annotations

from collections.abc import Sequence
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile

from .model import (
    ArtifactIntegrityError,
    ArtifactPayload,
    ArtifactRecord,
    RETAINABLE_EVIDENCE,
    sha256_bytes,
)
from .storage import (
    ArtifactCollisionError,
    ArtifactPathError,
    FilesystemArtifactStore,
    GenerationReuseError,
    SecretRetentionError,
)


def retain_artifact_stage(
    *,
    store: FilesystemArtifactStore,
    generation_id: str,
    stage_id: str,
    artifacts: Sequence[ArtifactPayload],
) -> tuple[ArtifactRecord, ...]:
    """Atomically retain one immutable pre-terminal evidence stage.

    References remain under the accepted generation namespace so terminal
    publication can later revalidate and index the returned records. A stage is
    write-once. New stages are rejected after a terminal claim exists.
    """

    if type(store) is not FilesystemArtifactStore:
        raise TypeError("store must be FilesystemArtifactStore")
    generation = _safe_segment(generation_id, "generation_id")
    stage_name = _safe_segment(stage_id, "stage_id")
    payloads = _validate_payloads(artifacts)

    root = store.root
    terminal_claim = root / f".{generation}.terminal"
    if terminal_claim.exists() or terminal_claim.is_symlink():
        raise GenerationReuseError(
            f"generation {generation!r} is terminal and cannot retain new evidence"
        )

    generation_dir = root / generation
    if generation_dir.is_symlink():
        raise ArtifactPathError("generation storage must not be a symlink")
    generation_dir.mkdir(mode=0o700, exist_ok=True)
    if not generation_dir.is_dir():
        raise ArtifactPathError("generation storage must be a directory")
    _reject_symlinks_between(root, generation_dir)

    final_dir = generation_dir / stage_name
    if final_dir.exists() or final_dir.is_symlink():
        raise GenerationReuseError(
            f"stage {stage_name!r} already exists for generation {generation!r}"
        )

    scratch = Path(
        tempfile.mkdtemp(
            prefix=f".{generation}.{stage_name}.stage-",
            dir=root,
        )
    )
    installed = False
    try:
        records: list[ArtifactRecord] = []
        artifact_ids: set[str] = set()
        paths: set[PurePosixPath] = set()
        for payload in payloads:
            if payload.artifact_id in artifact_ids:
                raise ArtifactCollisionError(
                    f"duplicate artifact_id {payload.artifact_id!r}"
                )
            artifact_ids.add(payload.artifact_id)

            relative = _safe_relative_path(payload.relative_path)
            if relative in paths:
                raise ArtifactCollisionError(
                    f"duplicate artifact output path {payload.relative_path!r}"
                )
            paths.add(relative)

            destination = scratch.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _reject_symlinks_between(scratch, destination.parent)
            if destination.exists() or destination.is_symlink():
                raise ArtifactCollisionError(
                    f"artifact output collision at {payload.relative_path!r}"
                )
            _write_exact(destination, payload.data)
            if sha256_bytes(destination.read_bytes()) != payload.sha256:
                raise ArtifactIntegrityError(
                    f"staged bytes for {payload.artifact_id!r} failed SHA-256 verification"
                )
            records.append(
                ArtifactRecord.from_payload(
                    payload,
                    reference=(
                        f"{generation}/{stage_name}/{relative.as_posix()}"
                    ),
                )
            )

        _fsync_directory(scratch)
        if terminal_claim.exists() or terminal_claim.is_symlink():
            raise GenerationReuseError(
                f"generation {generation!r} became terminal during staged retention"
            )
        if final_dir.exists() or final_dir.is_symlink():
            raise GenerationReuseError(
                f"stage {stage_name!r} was retained concurrently"
            )
        os.replace(scratch, final_dir)
        installed = True
        _fsync_directory(generation_dir)
        _fsync_directory(root)

        retained = tuple(sorted(records, key=lambda item: item.artifact_id))
        for record in retained:
            store.revalidate(record)
        _make_tree_read_only(final_dir)
        return retained
    except Exception:
        if installed and final_dir.exists():
            _make_tree_writable(final_dir)
            shutil.rmtree(final_dir, ignore_errors=True)
        elif scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
        raise


def _validate_payloads(
    artifacts: Sequence[ArtifactPayload],
) -> tuple[ArtifactPayload, ...]:
    if isinstance(artifacts, (str, bytes, bytearray)):
        raise TypeError("artifacts must be a sequence of ArtifactPayload values")
    values = tuple(artifacts)
    if not values:
        raise ValueError("at least one retained artifact is required")
    if not all(type(value) is ArtifactPayload for value in values):
        raise TypeError("artifacts must contain only ArtifactPayload values")
    for payload in values:
        if payload.retention_class != RETAINABLE_EVIDENCE:
            if payload.retention_class is None:
                raise SecretRetentionError(
                    f"artifact {payload.artifact_id!r} lacks explicit retainable-evidence classification"
                )
            raise SecretRetentionError(
                f"artifact {payload.artifact_id!r} is transient invocation material "
                "and cannot enter durable storage"
            )
    return values


def _safe_segment(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactPathError(f"{field} must be a non-empty string")
    invalid = '<>:"/\\|?*'
    if (
        value in {".", ".."}
        or any(character in invalid or ord(character) < 32 for character in value)
        or value.endswith((" ", "."))
    ):
        raise ArtifactPathError(
            f"{field} must be a portable safe single path segment"
        )
    return value


def _safe_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ArtifactPathError("artifact reference must be a non-empty relative path")
    if "\\" in value or "\x00" in value:
        raise ArtifactPathError("artifact references must use normalized POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts:
        raise ArtifactPathError("artifact reference must be relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ArtifactPathError("artifact reference contains traversal or ambiguous segments")
    return path


def _write_exact(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        total = 0
        while total < len(view):
            written = os.write(fd, view[total:])
            if written <= 0:
                raise OSError("failed to write complete artifact bytes")
            total += written
        os.fsync(fd)
    finally:
        os.close(fd)


def _reject_symlinks_between(root: Path, target: Path) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ArtifactPathError("artifact path escapes evidence-store root") from exc
    current = root
    if current.is_symlink():
        raise ArtifactPathError("artifact-store root must not be a symlink")
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ArtifactPathError("symlink components are not valid artifact paths")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _make_tree_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            raise ArtifactPathError("retained artifact stage contains a symlink")
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)


def _make_tree_writable(root: Path) -> None:
    if not root.exists():
        return
    root.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        path.chmod(0o755 if path.is_dir() else 0o644)


__all__ = ["retain_artifact_stage"]
