"""Deterministic primitives for production validation.

The validation package reports authority-blocking issues. It never repairs,
fills, or rewrites caller-owned data.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import ClassVar, Iterable, Mapping


_ISSUE_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SCHEMA_ID = re.compile(r"^arcgrav\.shared\.schema\.[a-z0-9._-]+$")
_SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXTENSION_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[^\s]+$")
_AVAILABILITY = frozenset({
    "retained",
    "not_produced",
    "unavailable",
    "invalid",
    "excluded",
    "missing",
    "failed",
    "completed_non_scorable",
    "scored",
    "not_applicable",
    "non_comparable",
})


@dataclass(frozen=True)
class SchemaIdentity:
    """Exact published shared-schema identity."""

    schema_id: str
    schema_version: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_id, str)
            or _SCHEMA_ID.fullmatch(self.schema_id) is None
        ):
            raise ValueError(
                "schema_id must be a published shared-schema identifier"
            )
        if (
            not isinstance(self.schema_version, str)
            or _SEMANTIC_VERSION.fullmatch(self.schema_version) is None
        ):
            raise ValueError("schema_version must be an exact semantic version")

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ValidationIssue:
    """One stable validation issue."""

    code: str
    source_id: str
    message: str
    json_pointer: str | None = None
    schema: SchemaIdentity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not _ISSUE_CODE.fullmatch(self.code):
            raise ValueError("validation issue code must be stable uppercase identifier")
        if not isinstance(self.source_id, str) or not self.source_id:
            raise ValueError("validation issue source_id must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("validation issue message must be a non-empty string")
        if self.json_pointer is not None and (
            not isinstance(self.json_pointer, str)
            or not _valid_json_pointer(self.json_pointer)
        ):
            raise ValueError("json_pointer must be an RFC 6901 JSON Pointer")
        if self.schema is not None and type(self.schema) is not SchemaIdentity:
            raise ValueError("validation issue schema must be a SchemaIdentity")

    def sort_key(self) -> tuple[str, str, str, str, str, str]:
        schema_id = self.schema.schema_id if self.schema else ""
        schema_version = self.schema.schema_version if self.schema else ""
        return (
            self.source_id,
            self.json_pointer or "",
            self.code,
            schema_id,
            schema_version,
            self.message,
        )

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "code": self.code,
            "source_id": self.source_id,
            "message": self.message,
        }
        if self.json_pointer is not None:
            value["json_pointer"] = self.json_pointer
        if self.schema is not None:
            value["schema"] = self.schema.to_dict()
        return value


@dataclass(frozen=True)
class SourceArtifact:
    """Identity of the source bytes validated by a result."""

    artifact_id: str
    sha256: str
    schema: SchemaIdentity | None = None
    reference: str | None = None
    availability: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id:
            raise ValueError("artifact_id must be a non-empty string")
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise ValueError("sha256 must use the form 'sha256:' plus 64 lowercase hex digits")
        if self.schema is not None and type(self.schema) is not SchemaIdentity:
            raise ValueError("artifact schema must be a SchemaIdentity")
        if self.reference is not None and (
            not isinstance(self.reference, str) or not self.reference
        ):
            raise ValueError("reference must be a non-empty string when provided")
        if self.availability is not None and (
            not isinstance(self.availability, str)
            or self.availability not in _AVAILABILITY
        ):
            raise ValueError("availability is not a declared shared evidence state")

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
        }
        if self.schema is not None:
            value["schema"] = self.schema.to_dict()
        if self.reference is not None:
            value["reference"] = self.reference
        if self.availability is not None:
            value["availability"] = self.availability
        return value


@dataclass(frozen=True)
class ValidationResult:
    """Deterministic validation result matching the shared result schema."""

    validation_id: str
    schema: SchemaIdentity
    source_artifact: SourceArtifact
    issues: tuple[ValidationIssue, ...]
    extensions: Mapping[str, object]

    SCHEMA_ID: ClassVar[str] = "arcgrav.shared.schema.validation-result"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.validation_id, str) or not self.validation_id:
            raise ValueError("validation_id must be a non-empty string")
        if type(self.schema) is not SchemaIdentity:
            raise ValueError("schema must be a SchemaIdentity")
        if type(self.source_artifact) is not SourceArtifact:
            raise ValueError("source_artifact must be a SourceArtifact")
        if not isinstance(self.issues, tuple) or not all(
            type(issue) is ValidationIssue for issue in self.issues
        ):
            raise ValueError("issues must be a tuple of ValidationIssue values")
        normalized = tuple(sorted(set(self.issues), key=ValidationIssue.sort_key))
        if self.issues != normalized:
            raise ValueError("issues must be unique and deterministically ordered")
        if not isinstance(self.extensions, Mapping):
            raise ValueError("extensions must be a mapping")
        if not all(
            isinstance(key, str) and _EXTENSION_KEY.fullmatch(key)
            for key in self.extensions
        ):
            raise ValueError("extension keys must be namespaced")
        if not all(_is_json_value(value) for value in self.extensions.values()):
            raise ValueError("extension values must be JSON-compatible")

    @classmethod
    def create(
        cls,
        *,
        validation_id: str,
        schema: SchemaIdentity,
        source_artifact: SourceArtifact,
        issues: Iterable[ValidationIssue] = (),
        extensions: Mapping[str, object] | None = None,
    ) -> "ValidationResult":
        if not isinstance(validation_id, str) or not validation_id:
            raise ValueError("validation_id must be a non-empty string")
        raw_issues = tuple(issues)
        if not all(type(issue) is ValidationIssue for issue in raw_issues):
            raise ValueError("issues must contain only ValidationIssue values")
        if extensions is not None and not isinstance(extensions, Mapping):
            raise ValueError("extensions must be a mapping when provided")
        normalized = tuple(sorted(set(raw_issues), key=ValidationIssue.sort_key))
        return cls(
            validation_id=validation_id,
            schema=schema,
            source_artifact=source_artifact,
            issues=normalized,
            extensions=dict(extensions or {}),
        )

    @property
    def valid(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_id": self.SCHEMA_ID,
            "schema_version": self.SCHEMA_VERSION,
            "extensions": dict(self.extensions),
            "validation_id": self.validation_id,
            "schema": self.schema.to_dict(),
            "source_artifact": self.source_artifact.to_dict(),
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def sha256_bytes(data: bytes) -> str:
    """Return the canonical retained-artifact hash string for exact bytes."""

    return "sha256:" + hashlib.sha256(data).hexdigest()


def _valid_json_pointer(pointer: str) -> bool:
    if pointer == "":
        return True
    if not pointer.startswith("/"):
        return False
    segments = pointer[1:].split("/")
    return all(_valid_pointer_segment(segment) for segment in segments)


def _valid_pointer_segment(segment: str) -> bool:
    index = 0
    while index < len(segment):
        if segment[index] != "~":
            index += 1
            continue
        if index + 1 >= len(segment) or segment[index + 1] not in {"0", "1"}:
            return False
        index += 2
    return True


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


__all__ = [
    "SchemaIdentity",
    "SourceArtifact",
    "ValidationIssue",
    "ValidationResult",
    "sha256_bytes",
]
