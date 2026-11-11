"""Exact-byte runtime artifact records.

This module owns storage-neutral identity for retained runtime artifacts. It does
not decide whether a run is accepted or blocked and does not infer benchmark
semantics from artifact content.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Final


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SCHEMA_ID = re.compile(r"^arcgrav\.shared\.schema\.[a-z0-9._-]+$")

RETAINED_AVAILABILITY: Final[str] = "retained"
RETAINABLE_EVIDENCE: Final[str] = "retainable_evidence"
TRANSIENT_INVOCATION: Final[str] = "transient_invocation"
ARTIFACT_RETENTION_CLASSES: Final[frozenset[str]] = frozenset(
    {RETAINABLE_EVIDENCE, TRANSIENT_INVOCATION}
)
BLOCKED_ROLE_AVAILABILITY: Final[frozenset[str]] = frozenset(
    {"retained", "not_produced", "unavailable", "invalid", "excluded"}
)


class ArtifactError(ValueError):
    """Base class for artifact-domain validation failures."""


class ArtifactIntegrityError(ArtifactError):
    """Exact retained bytes no longer match their declared identity."""


@dataclass(frozen=True)
class SchemaBinding:
    """Exact shared-schema identity associated with retained bytes."""

    schema_id: str
    schema_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.schema_id, str) or _SCHEMA_ID.fullmatch(self.schema_id) is None:
            raise ArtifactError("schema_id must be a published shared-schema identifier")
        if (
            not isinstance(self.schema_version, str)
            or _SEMVER.fullmatch(self.schema_version) is None
        ):
            raise ArtifactError("schema_version must be an exact semantic version")

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ContractBinding:
    """Exact behavioral-contract identity associated with retained bytes."""

    contract_id: str
    contract_version: str

    def __post_init__(self) -> None:
        _nonempty(self.contract_id, "contract_id")
        if (
            not isinstance(self.contract_version, str)
            or _SEMVER.fullmatch(self.contract_version) is None
        ):
            raise ArtifactError("contract_version must be an exact semantic version")


@dataclass(frozen=True)
class ArtifactPayload:
    """Exact bytes proposed for durable runtime-artifact retention.

    retention_class is intentionally explicit at the storage boundary.
    Unclassified payloads may be constructed for upstream processing but are
    rejected before staging. Secret-bearing or invocation-only material must be
    classified as transient_invocation and is never retainable.
    """

    artifact_id: str
    role: str
    relative_path: str
    data: bytes
    provenance: str
    retention_class: str | None = None
    media_type: str | None = None
    encoding: str | None = None
    schema: SchemaBinding | None = None
    contract: ContractBinding | None = None

    def __post_init__(self) -> None:
        _nonempty(self.artifact_id, "artifact_id")
        _nonempty(self.role, "role")
        _nonempty(self.relative_path, "relative_path")
        _nonempty(self.provenance, "provenance")
        if not isinstance(self.data, bytes):
            raise TypeError("data must be exact bytes")
        if (
            self.retention_class is not None
            and self.retention_class not in ARTIFACT_RETENTION_CLASSES
        ):
            raise ArtifactError(
                "retention_class must be retainable_evidence or transient_invocation"
            )
        if self.media_type is not None:
            _nonempty(self.media_type, "media_type")
        if self.encoding is not None:
            _nonempty(self.encoding, "encoding")
        if self.schema is not None and type(self.schema) is not SchemaBinding:
            raise TypeError("schema must be SchemaBinding when provided")
        if self.contract is not None and type(self.contract) is not ContractBinding:
            raise TypeError("contract must be ContractBinding when provided")

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.data)


@dataclass(frozen=True)
class ArtifactRecord:
    """Immutable metadata for one exact retained artifact."""

    artifact_id: str
    role: str
    reference: str
    sha256: str
    provenance: str
    availability: str = RETAINED_AVAILABILITY
    media_type: str | None = None
    encoding: str | None = None
    schema: SchemaBinding | None = None
    contract: ContractBinding | None = None

    def __post_init__(self) -> None:
        _nonempty(self.artifact_id, "artifact_id")
        _nonempty(self.role, "role")
        _nonempty(self.reference, "reference")
        _nonempty(self.provenance, "provenance")
        if not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None:
            raise ArtifactError("sha256 must use 'sha256:' plus 64 lowercase hex digits")
        if self.availability != RETAINED_AVAILABILITY:
            raise ArtifactError("ArtifactRecord represents retained evidence only")
        if self.media_type is not None:
            _nonempty(self.media_type, "media_type")
        if self.encoding is not None:
            _nonempty(self.encoding, "encoding")
        if self.schema is not None and type(self.schema) is not SchemaBinding:
            raise TypeError("schema must be SchemaBinding when provided")
        if self.contract is not None and type(self.contract) is not ContractBinding:
            raise TypeError("contract must be ContractBinding when provided")

    @classmethod
    def from_payload(cls, payload: ArtifactPayload, *, reference: str) -> "ArtifactRecord":
        if type(payload) is not ArtifactPayload:
            raise TypeError("payload must be ArtifactPayload")
        return cls(
            artifact_id=payload.artifact_id,
            role=payload.role,
            reference=reference,
            sha256=payload.sha256,
            provenance=payload.provenance,
            media_type=payload.media_type,
            encoding=payload.encoding,
            schema=payload.schema,
            contract=payload.contract,
        )

    def to_artifact_ref(self) -> dict[str, object]:
        """Return the shared run-outcome artifact-reference projection."""

        value: dict[str, object] = {
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "reference": self.reference,
            "availability": self.availability,
        }
        if self.schema is not None:
            value["schema"] = self.schema.to_dict()
        return value


@dataclass(frozen=True)
class BlockedEvidenceRole:
    """Explicit state for one blocked-run evidence role."""

    role: str
    availability: str
    reason: str

    def __post_init__(self) -> None:
        _nonempty(self.role, "role")
        _nonempty(self.reason, "reason")
        if self.availability not in BLOCKED_ROLE_AVAILABILITY:
            raise ArtifactError(
                "blocked evidence role availability must be retained, not_produced, "
                "unavailable, invalid, or excluded"
            )


def sha256_bytes(data: bytes) -> str:
    """Return the shared-form SHA-256 identity for exact retained bytes."""

    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactError(f"{field} must be a non-empty string")
    return value


__all__ = [
    "ARTIFACT_RETENTION_CLASSES",
    "ArtifactError",
    "ArtifactIntegrityError",
    "ArtifactPayload",
    "ArtifactRecord",
    "BLOCKED_ROLE_AVAILABILITY",
    "BlockedEvidenceRole",
    "ContractBinding",
    "RETAINABLE_EVIDENCE",
    "RETAINED_AVAILABILITY",
    "SchemaBinding",
    "TRANSIENT_INVOCATION",
    "sha256_bytes",
]
