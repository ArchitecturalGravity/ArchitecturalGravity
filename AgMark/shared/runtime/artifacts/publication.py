"""Immutable accepted/blocked terminal publication for retained runtime artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .model import ArtifactError, ArtifactRecord, BlockedEvidenceRole
from .storage import FilesystemArtifactStore


class TerminalPublicationError(ArtifactError):
    """Terminal artifact publication would weaken lifecycle authority."""


_PUBLICATION_GUARD = object()


@dataclass(frozen=True, init=False)
class AcceptedArtifactIndex:
    """Immutable accepted-only artifact index for one finalized generation."""

    generation_id: str
    artifacts: tuple[ArtifactRecord, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by publish_accepted_artifact_index")

    def to_run_outcome_field(self) -> list[dict[str, object]]:
        """Return the schema-compatible artifact_index value."""

        _require_guard(self)
        return [record.to_artifact_ref() for record in self.artifacts]


@dataclass(frozen=True, init=False)
class BlockedArtifactManifest:
    """Immutable blocked-only evidence manifest for one finalized generation.

    evidence_roles preserves structured blocked-role state in memory. The
    current shared run-outcome schema has no structured role-state field, so the
    run-outcome projection also emits deterministic role-state diagnostics while
    retaining exact available diagnostic artifact references separately.
    """

    generation_id: str
    reason_code: str
    diagnostics: tuple[str, ...]
    evidence_roles: tuple[BlockedEvidenceRole, ...]
    retained_diagnostics: tuple[ArtifactRecord, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by publish_blocked_artifact_manifest")

    def to_run_outcome_field(self) -> dict[str, object]:
        """Return the schema-compatible blocked_manifest value."""

        _require_guard(self)
        role_diagnostics = [
            f"evidence_role[{role.role}]={role.availability}: {role.reason}"
            for role in sorted(self.evidence_roles, key=lambda value: value.role)
        ]
        value: dict[str, object] = {
            "reason_code": self.reason_code,
            "diagnostics": [*self.diagnostics, *role_diagnostics],
        }
        if self.retained_diagnostics:
            value["retained_diagnostics"] = [
                record.to_artifact_ref() for record in self.retained_diagnostics
            ]
        return value


def publish_accepted_artifact_index(
    *,
    store: FilesystemArtifactStore,
    generation_id: str,
    terminal_status: str,
    artifacts: Sequence[ArtifactRecord],
) -> AcceptedArtifactIndex:
    """Publish accepted authority only after retained bytes revalidate.

    Runtime orchestration supplies the terminal status. The filesystem store
    revalidates exact retained bytes and durably claims accepted terminal
    artifact authority before the immutable index is returned.
    """

    _store(store)
    generation = _generation_id(generation_id)
    if terminal_status != "accepted":
        raise TerminalPublicationError(
            "accepted artifact index requires terminal_status='accepted'"
        )
    records = _verified_records_for_generation(store, artifacts, generation)
    if not records:
        raise TerminalPublicationError(
            "accepted artifact index requires at least one retained artifact"
        )
    value = _mint(
        AcceptedArtifactIndex,
        generation_id=generation,
        artifacts=records,
    )
    store.claim_terminal_status(generation, "accepted")
    return value


def publish_blocked_artifact_manifest(
    *,
    store: FilesystemArtifactStore,
    generation_id: str,
    terminal_status: str,
    reason_code: str,
    diagnostics: Sequence[str] = (),
    evidence_roles: Sequence[BlockedEvidenceRole] = (),
    retained_diagnostics: Sequence[ArtifactRecord] = (),
) -> BlockedArtifactManifest:
    """Publish blocked authority without creating an accepted artifact index."""

    _store(store)
    generation = _generation_id(generation_id)
    if terminal_status != "blocked":
        raise TerminalPublicationError(
            "blocked artifact manifest requires terminal_status='blocked'"
        )
    _nonempty(reason_code, "reason_code")
    diagnostics_tuple = tuple(diagnostics)
    if any(not isinstance(value, str) for value in diagnostics_tuple):
        raise TypeError("diagnostics must contain only strings")

    roles = tuple(evidence_roles)
    if any(type(value) is not BlockedEvidenceRole for value in roles):
        raise TypeError("evidence_roles must contain only BlockedEvidenceRole values")
    role_names = [value.role for value in roles]
    if len(set(role_names)) != len(role_names):
        raise TerminalPublicationError("blocked evidence roles must be unique")

    records = _verified_records_for_generation(
        store, retained_diagnostics, generation
    )
    retained_roles = {record.role for record in records}
    declared_retained = {
        role.role for role in roles if role.availability == "retained"
    }
    declared_nonretained = {
        role.role for role in roles if role.availability != "retained"
    }
    missing = declared_retained - retained_roles
    unexpected = retained_roles - declared_retained
    contradictory = retained_roles & declared_nonretained
    if missing:
        raise TerminalPublicationError(
            "blocked retained roles lack exact retained artifacts: "
            + ", ".join(sorted(missing))
        )
    if unexpected or contradictory:
        raise TerminalPublicationError(
            "blocked retained diagnostics are not matched by retained role authority"
        )

    value = _mint(
        BlockedArtifactManifest,
        generation_id=generation,
        reason_code=reason_code,
        diagnostics=diagnostics_tuple,
        evidence_roles=roles,
        retained_diagnostics=records,
    )
    store.claim_terminal_status(generation, "blocked")
    return value


def _verified_records_for_generation(
    store: FilesystemArtifactStore,
    values: Sequence[ArtifactRecord],
    generation_id: str,
) -> tuple[ArtifactRecord, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("artifact records must be a sequence")
    records = tuple(values)
    if any(type(record) is not ArtifactRecord for record in records):
        raise TypeError("artifact records must contain only ArtifactRecord values")

    artifact_ids: set[str] = set()
    references: set[str] = set()
    prefix = generation_id + "/"
    for record in records:
        if not record.reference.startswith(prefix):
            raise TerminalPublicationError(
                f"artifact {record.artifact_id!r} does not belong to generation "
                f"{generation_id!r}"
            )
        if record.artifact_id in artifact_ids:
            raise TerminalPublicationError(
                f"duplicate artifact_id {record.artifact_id!r} in terminal publication"
            )
        if record.reference in references:
            raise TerminalPublicationError(
                f"duplicate artifact reference {record.reference!r} in terminal publication"
            )
        store.revalidate(record)
        artifact_ids.add(record.artifact_id)
        references.add(record.reference)
    return tuple(sorted(records, key=lambda value: value.artifact_id))


def _mint(cls: type, **fields: object):
    value = object.__new__(cls)
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    object.__setattr__(value, "_publication_guard", _PUBLICATION_GUARD)
    return value


def _require_guard(value: object) -> None:
    if getattr(value, "_publication_guard", None) is not _PUBLICATION_GUARD:
        raise TerminalPublicationError("terminal publication authority is invalid")


def _store(value: object) -> FilesystemArtifactStore:
    if type(value) is not FilesystemArtifactStore:
        raise TypeError("store must be FilesystemArtifactStore")
    return value


def _generation_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TerminalPublicationError("generation_id must be a non-empty string")
    if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise TerminalPublicationError("generation_id must be a safe single segment")
    return value


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise TerminalPublicationError(f"{field} must be a non-empty string")
    return value


__all__ = [
    "AcceptedArtifactIndex",
    "BlockedArtifactManifest",
    "TerminalPublicationError",
    "publish_accepted_artifact_index",
    "publish_blocked_artifact_manifest",
]
