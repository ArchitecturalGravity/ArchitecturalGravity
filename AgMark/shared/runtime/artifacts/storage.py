"""Fail-closed local filesystem retention for runtime artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile

from .model import (
    ArtifactError,
    ArtifactIntegrityError,
    ArtifactPayload,
    ArtifactRecord,
    RETAINABLE_EVIDENCE,
    sha256_bytes,
)


class ArtifactPathError(ArtifactError):
    """A storage reference is unsafe or escapes its evidence-store root."""


class ArtifactDestinationError(ArtifactPathError):
    """A publication destination lacks benchmark/external store authority."""


class ArtifactCollisionError(ArtifactError):
    """Two artifacts would claim the same identity or output path."""


class GenerationReuseError(ArtifactError):
    """A generation already has retained storage and cannot be overwritten."""


class TerminalAuthorityConflictError(ArtifactError):
    """A generation already carries terminal artifact authority."""


class SecretRetentionError(ArtifactError):
    """Unclassified or transient invocation material reached durable retention."""


@dataclass(frozen=True)
class PublicationDestination:
    """Validated ownership authority for one filesystem evidence-store root.

    Benchmark-owned destinations must be confined beneath an already validated
    benchmark package root. External destinations must be outside the supplied
    repository root. forbidden_roots lets the caller carry explicit repository
    authority for frontend or other non-evidence subtrees without teaching
    shared code directory-name semantics.
    """

    root: Path
    ownership: str
    authority_root: Path
    forbidden_roots: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if self.ownership not in {"benchmark", "external", "central"}:
            raise ArtifactDestinationError("ownership must be benchmark or external")
        if not isinstance(self.root, Path) or not isinstance(self.authority_root, Path):
            raise TypeError("root and authority_root must be pathlib.Path values")
        if any(not isinstance(value, Path) for value in self.forbidden_roots):
            raise TypeError("forbidden_roots must contain pathlib.Path values")
        self._validate_candidate(self.root)

    @classmethod
    def benchmark_owned(
        cls,
        root: str | os.PathLike[str],
        *,
        benchmark_root: str | os.PathLike[str],
        forbidden_roots: Sequence[str | os.PathLike[str]] = (),
    ) -> "PublicationDestination":
        authority = _resolved_authority_root(benchmark_root, "benchmark_root")
        candidate = _resolved_candidate(root)
        forbidden = tuple(_resolved_authority_root(p, "forbidden_root") for p in forbidden_roots)
        return cls(
            root=candidate,
            ownership="benchmark",
            authority_root=authority,
            forbidden_roots=forbidden,
        )

    @classmethod
    def central(
        cls,
        root: str | os.PathLike[str],
        *,
        repository_root: str | os.PathLike[str],
    ) -> "PublicationDestination":
        """Restrict production evidence ownership to AgMark/run_evidence."""
        repository = _resolved_authority_root(repository_root, "repository_root")
        candidate = _resolved_candidate(root)
        return cls(root=candidate, ownership="central", authority_root=repository)

    @classmethod
    def external(
        cls,
        root: str | os.PathLike[str],
        *,
        repository_root: str | os.PathLike[str],
    ) -> "PublicationDestination":
        repository = _resolved_authority_root(repository_root, "repository_root")
        candidate = _resolved_candidate(root)
        return cls(
            root=candidate,
            ownership="external",
            authority_root=repository,
        )

    def validate_resolved_root(self, resolved_root: Path) -> None:
        """Recheck authority after directory creation/symlink resolution."""

        if not isinstance(resolved_root, Path) or not resolved_root.is_absolute():
            raise TypeError("resolved_root must be an absolute pathlib.Path")
        self._validate_candidate(resolved_root)

    def _validate_candidate(self, candidate: Path) -> None:
        if self.ownership == "central":
            if candidate != self.authority_root / "AgMark" / "run_evidence":
                raise ArtifactDestinationError("central evidence must live in AgMark/run_evidence")
        elif self.ownership == "benchmark":
            if not _is_within(candidate, self.authority_root):
                raise ArtifactDestinationError(
                    "benchmark-owned evidence store must remain beneath benchmark_root"
                )
            if any(_is_within(candidate, forbidden) for forbidden in self.forbidden_roots):
                raise ArtifactDestinationError(
                    "benchmark-owned evidence store lies beneath a forbidden repository root"
                )
        elif _is_within(candidate, self.authority_root):
            raise ArtifactDestinationError(
                "external evidence store must be outside repository_root"
            )


class FilesystemArtifactStore:
    """Retain exact runtime evidence beneath one authorized storage root.

    Generation publication is fail-closed: destination authority and payload
    retention classification are checked before staging; bytes are written to
    an isolated staging directory, verified there, atomically installed by
    directory rename, verified again from the installed location, and only then
    returned as retained ArtifactRecord values.

    This is a storage primitive, not terminal accepted/blocked authority.
    """

    def __init__(self, destination: PublicationDestination) -> None:
        if type(destination) is not PublicationDestination:
            raise TypeError(
                "destination must be PublicationDestination; raw filesystem paths "
                "are not publication authority"
            )
        raw = destination.root
        if raw.exists() and raw.is_symlink():
            raise ArtifactPathError("artifact-store root must not be a symlink")
        raw.mkdir(parents=True, exist_ok=True)
        if not raw.is_dir():
            raise ArtifactPathError("artifact-store root must be a directory")
        self._root = raw.resolve(strict=True)
        destination.validate_resolved_root(self._root)
        self._destination = destination

    @property
    def root(self) -> Path:
        return self._root

    @property
    def destination(self) -> PublicationDestination:
        return self._destination

    def publish_generation(
        self,
        generation_id: str,
        artifacts: Sequence[ArtifactPayload],
    ) -> tuple[ArtifactRecord, ...]:
        from .archive import _publication_lock
        generation = _safe_generation_id(generation_id)
        with _publication_lock(self._root, generation):
            return self._publish_generation(generation, artifacts)

    def _publish_generation(self, generation_id: str,
                            artifacts: Sequence[ArtifactPayload]) -> tuple[ArtifactRecord, ...]:
        generation = _safe_generation_id(generation_id)
        payloads = _validate_payloads(artifacts)
        final_dir = self._root / generation
        claim = self._root / f".{generation}.generation-claim"
        terminal_claim = self._root / f".{generation}.terminal"
        deletion_tombstone = self._root / f".{generation}.deleted"
        if deletion_tombstone.exists() or deletion_tombstone.is_symlink():
            raise GenerationReuseError(
                f"generation {generation!r} was deleted and cannot be reused"
            )
        if terminal_claim.exists() or terminal_claim.is_symlink():
            raise GenerationReuseError(
                f"generation {generation!r} is already terminal and cannot retain new artifacts"
            )
        sealed = self._root / (generation + ".agmark")
        if sealed.exists() or sealed.is_symlink():
            raise GenerationReuseError("generation already has a sealed .agmark archive")
        if final_dir.exists() or final_dir.is_symlink():
            raise GenerationReuseError(
                f"generation {generation!r} already has retained storage"
            )
        claim_fd: int | None = None
        try:
            claim_fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        except FileExistsError as exc:
            raise GenerationReuseError(
                f"generation {generation!r} is already claimed"
            ) from exc
        finally:
            if claim_fd is not None:
                os.close(claim_fd)

        stage = Path(
            tempfile.mkdtemp(prefix=f".{generation}.stage-", dir=self._root)
        )
        installed = False
        try:
            staged_records: list[ArtifactRecord] = []
            for payload in payloads:
                relative = _safe_relative_path(payload.relative_path)
                destination = stage.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                _reject_symlinks_between(stage, destination.parent)
                if destination.exists() or destination.is_symlink():
                    raise ArtifactCollisionError(
                        f"artifact output collision at {payload.relative_path!r}"
                    )
                _write_exact(destination, payload.data)
                if sha256_bytes(destination.read_bytes()) != payload.sha256:
                    raise ArtifactIntegrityError(
                        f"staged bytes for {payload.artifact_id!r} failed SHA-256 verification"
                    )
                reference = f"{generation}/{relative.as_posix()}"
                staged_records.append(
                    ArtifactRecord.from_payload(payload, reference=reference)
                )

            _fsync_directory(stage)
            if final_dir.exists() or final_dir.is_symlink():
                raise GenerationReuseError(
                    f"generation {generation!r} was published concurrently"
                )
            os.replace(stage, final_dir)
            installed = True
            _fsync_directory(self._root)

            final_records = tuple(sorted(staged_records, key=lambda item: item.artifact_id))
            for record in final_records:
                self.revalidate(record)
            _make_tree_read_only(final_dir)
            return final_records
        except Exception:
            if installed and final_dir.exists():
                _make_tree_writable(final_dir)
                shutil.rmtree(final_dir, ignore_errors=True)
            elif stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            try:
                claim.unlink()
            except FileNotFoundError:
                pass
            raise

    def claim_terminal_status(self, generation_id: str, status: str) -> None:
        """Persist one immutable accepted-or-blocked terminal status per generation."""

        from .archive import _publication_lock
        generation = _safe_generation_id(generation_id)
        with _publication_lock(self._root, generation):
            self._claim_terminal_status(generation, status)

    def _claim_terminal_status(self, generation_id: str, status: str) -> None:
        generation = _safe_generation_id(generation_id)
        if status not in {"accepted", "blocked", "executed"}:
            raise ValueError("status must be accepted or blocked")
        claim = self._root / f".{generation}.terminal"
        deletion_tombstone = self._root / f".{generation}.deleted"
        if (self._root / (generation + ".agmark")).exists():
            raise TerminalAuthorityConflictError("generation is already sealed")
        if deletion_tombstone.exists() or deletion_tombstone.is_symlink():
            raise TerminalAuthorityConflictError(
                f"generation {generation!r} was deleted and cannot receive terminal authority"
            )
        encoded = status.encode("ascii")
        try:
            fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        except FileExistsError:
            if claim.is_symlink() or not claim.is_file():
                raise TerminalAuthorityConflictError(
                    f"generation {generation!r} terminal claim is invalid"
                )
            existing = claim.read_bytes()
            raise TerminalAuthorityConflictError(
                f"generation {generation!r} already has "
                f"{existing.decode('ascii', errors='replace')!r} terminal authority"
            )

        try:
            view = memoryview(encoded)
            total = 0
            while total < len(view):
                written = os.write(fd, view[total:])
                if written <= 0:
                    raise OSError("failed to persist terminal authority")
                total += written
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_directory(self._root)

    def delete_generation(self, generation_id: str) -> None:
        """Remove one finalized generation as a unit while permanently retiring its ID."""

        from .archive import _publication_lock
        generation = _safe_generation_id(generation_id)
        with _publication_lock(self._root, generation):
            self._delete_generation(generation)

    def _delete_generation(self, generation_id: str) -> None:
        generation = _safe_generation_id(generation_id)
        final_dir = self._root / generation
        generation_claim = self._root / f".{generation}.generation-claim"
        terminal_claim = self._root / f".{generation}.terminal"
        deletion_tombstone = self._root / f".{generation}.deleted"
        archive = self._root / (generation + ".agmark")
        if archive.is_symlink() or (archive.exists() and not archive.is_file()):
            raise ArtifactPathError("generation archive is not a regular file")

        for path, expected_directory in (
            (final_dir, True),
            (generation_claim, False),
            (terminal_claim, False),
            (deletion_tombstone, False),
        ):
            if path.is_symlink():
                raise ArtifactPathError(
                    f"generation deletion encountered unsafe symlink {path.name!r}"
                )
            if path.exists() and (
                (expected_directory and not path.is_dir())
                or (not expected_directory and not path.is_file())
            ):
                raise ArtifactPathError(
                    f"generation deletion encountered invalid storage node {path.name!r}"
                )

        if not deletion_tombstone.exists():
            encoded = b"deleted"
            fd = os.open(
                deletion_tombstone,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o400,
            )
            try:
                view = memoryview(encoded)
                total = 0
                while total < len(view):
                    written = os.write(fd, view[total:])
                    if written <= 0:
                        raise OSError("failed to persist generation deletion tombstone")
                    total += written
                os.fsync(fd)
            finally:
                os.close(fd)
            _fsync_directory(self._root)

        archive.unlink(missing_ok=True)
        if final_dir.exists():
            _make_tree_writable(final_dir)
            shutil.rmtree(final_dir)
        for claim in (generation_claim, terminal_claim):
            try:
                claim.chmod(0o600)
            except FileNotFoundError:
                continue
            try:
                claim.unlink()
            except FileNotFoundError:
                pass
        _fsync_directory(self._root)

    def read_member(self, reference: str) -> bytes:
        """Read from the active run stage or a fully validated sealed archive."""
        relative = _safe_relative_path(reference)
        parts = relative.parts
        if parts[0].startswith("generation-"):
            generation = parts[0]
        elif parts[0] == ".agmark-validation" and len(parts) >= 3:
            generation = parts[1]
        else:
            raise ArtifactPathError("member reference is not run-scoped")
        from .archive import archive_path, read_archive_member, _active_archive_reader
        sealed = archive_path(self._root, generation)
        if _active_archive_reader(sealed) is not None or sealed.exists() or sealed.is_symlink():
            try:
                return read_archive_member(sealed, relative.as_posix())
            except ValueError as exc:
                raise ArtifactIntegrityError(str(exc)) from exc
        return self._path_for_reference(reference).read_bytes()

    @contextmanager
    def verified_reads(self, generation_id: str):
        """Batch one operation's archived reads, never cache loose evidence."""
        from .archive import verified_archive_reads, _active_archive_reader
        generation = _safe_generation_id(generation_id)
        sealed = self._root / (generation + ".agmark")
        if _active_archive_reader(sealed) is not None or sealed.exists() or sealed.is_symlink():
            with verified_archive_reads(sealed) as reader:
                yield reader
        else:
            yield None

    def revalidate(self, record: ArtifactRecord) -> None:
        """Fail closed when a retained artifact no longer matches authority."""
        if type(record) is not ArtifactRecord:
            raise TypeError("record must be ArtifactRecord")
        from .archive import _active_archive_reader
        relative = _safe_relative_path(record.reference)
        reader = _active_archive_reader(self._root / (relative.parts[0] + ".agmark"))
        if reader is not None:
            try:
                reader.verify_member(record.reference, record.sha256)
            except ValueError as exc:
                raise ArtifactIntegrityError(str(exc)) from exc
            return
        if sha256_bytes(self.read_member(record.reference)) != record.sha256:
            raise ArtifactIntegrityError(
                f"retained artifact {record.artifact_id!r} no longer matches SHA-256 authority"
            )

    def read_verified(self, record: ArtifactRecord) -> bytes:
        """Read once, verifying the archive and expected artifact digest."""
        if type(record) is not ArtifactRecord:
            raise TypeError("record must be ArtifactRecord")
        data = self.read_member(record.reference)
        if sha256_bytes(data) != record.sha256:
            raise ArtifactIntegrityError("retained artifact no longer matches SHA-256 authority")
        return data

    def seal_generation(self, generation_id: str, *,
                        report_components: Mapping[str, bytes],
                        completion_record: Mapping[str, object]) -> Path:
        if self._destination.ownership != "central":
            raise ArtifactDestinationError("sealing requires central run-evidence storage")
        from .archive import seal_generation
        return seal_generation(self._root, generation_id,
                               report_components=report_components,
                               completion_record=completion_record)

    def revise_generation(self, generation_id: str, additions: Mapping[str, bytes]) -> Path:
        if self._destination.ownership != "central":
            raise ArtifactDestinationError("revision requires central run-evidence storage")
        from .archive import revise_archive
        return revise_archive(self._root, generation_id, additions)

    def _path_for_reference(self, reference: str) -> Path:
        relative = _safe_relative_path(reference)
        candidate = self._root.joinpath(*relative.parts)
        _reject_symlinks_between(self._root, candidate)
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ArtifactIntegrityError("retained artifact reference is missing") from exc
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise ArtifactPathError("artifact reference escapes evidence-store root") from exc
        return resolved


def _validate_payloads(
    artifacts: Sequence[ArtifactPayload],
) -> tuple[ArtifactPayload, ...]:
    if isinstance(artifacts, (str, bytes, bytearray)):
        raise TypeError("artifacts must be a sequence of ArtifactPayload values")
    values = tuple(artifacts)
    if not values:
        raise ArtifactError("at least one retained artifact is required")
    if not all(type(value) is ArtifactPayload for value in values):
        raise TypeError("artifacts must contain only ArtifactPayload values")

    artifact_ids: set[str] = set()
    paths: set[PurePosixPath] = set()
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
    return values


def _resolved_authority_root(
    value: str | os.PathLike[str], field: str
) -> Path:
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ArtifactDestinationError(f"{field} must already exist") from exc
    if not resolved.is_dir():
        raise ArtifactDestinationError(f"{field} must be a directory")
    return resolved


def _resolved_candidate(value: str | os.PathLike[str]) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_generation_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactPathError("generation_id must be a non-empty string")
    invalid = '<>:"/\\|?*'
    if (
        value in {".", ".."}
        or any(character in invalid or ord(character) < 32 for character in value)
        or value.endswith((" ", "."))
    ):
        raise ArtifactPathError(
            "generation_id is not a portable safe single path segment"
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
            raise ArtifactPathError("published artifact tree contains a symlink")
        if path.is_dir():
            path.chmod(0o555)
        else:
            path.chmod(0o444)
    root.chmod(0o555)


def _make_tree_writable(root: Path) -> None:
    if not root.exists():
        return
    root.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        path.chmod(0o755 if path.is_dir() else 0o644)


__all__ = [
    "ArtifactCollisionError",
    "ArtifactDestinationError",
    "ArtifactPathError",
    "FilesystemArtifactStore",
    "GenerationReuseError",
    "PublicationDestination",
    "SecretRetentionError",
    "TerminalAuthorityConflictError",
]
