"""Fail-closed retained-artifact and evidence-set validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import re
from typing import Any

from .core import SchemaIdentity, ValidationIssue, sha256_bytes


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_AVAILABILITY = frozenset({
    "retained", "not_produced", "unavailable", "invalid", "excluded",
    "missing", "failed", "completed_non_scorable", "scored",
    "not_applicable", "non_comparable",
})
_PRESENT = frozenset({"retained", "completed_non_scorable", "scored"})
_GUARD = object()


@dataclass(frozen=True)
class RetainedArtifactSource:
    """Trusted exact bytes and provenance for one retained artifact."""

    artifact_id: str
    reference: str
    data: bytes
    provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id:
            raise ValueError("artifact_id must be a non-empty string")
        if not isinstance(self.reference, str) or not self.reference:
            raise ValueError("reference must be a non-empty string")
        if not isinstance(self.data, bytes):
            raise TypeError("data must be exact bytes")
        if not isinstance(self.provenance, str) or not self.provenance:
            raise ValueError("provenance must be a non-empty string")

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.data)


@dataclass(frozen=True, init=False)
class EvidenceSetValidationOutcome:
    """Opaque authority minted for one exact retained evidence set."""

    evidence_set_id: str
    generation_id: str
    source_id: str
    terminal_state: str
    evidence_fingerprint: str
    issues: tuple[ValidationIssue, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by validate_evidence_set_outcome")

    @property
    def valid(self) -> bool:
        return (
            getattr(self, "_guard", None) is _GUARD
            and isinstance(getattr(self, "issues", None), tuple)
            and not self.issues
        )

    @property
    def publication_authorized(self) -> bool:
        return self.valid and self.terminal_state == "accepted"

    def authorizes(self, artifact_id: str, sha256: str) -> bool:
        return (
            self.publication_authorized
            and (artifact_id, sha256) in getattr(self, "_identities", ())
        )


def validate_artifact_reference(
    artifact: Mapping[str, Any],
    *,
    source: RetainedArtifactSource | None,
    source_id: str,
    json_pointer: str = "",
    expected_schema: SchemaIdentity | None = None,
    require_available: bool = False,
) -> tuple[ValidationIssue, ...]:
    """Validate an artifact declaration against exact retained bytes."""

    _source_id(source_id)
    if not isinstance(artifact, Mapping):
        raise TypeError("artifact must be a mapping")
    if source is not None and type(source) is not RetainedArtifactSource:
        raise TypeError("source must be RetainedArtifactSource")
    if expected_schema is not None and type(expected_schema) is not SchemaIdentity:
        raise TypeError("expected_schema must be SchemaIdentity")

    issues: list[ValidationIssue] = []
    aid = artifact.get("artifact_id")
    digest = artifact.get("sha256")
    reference = artifact.get("reference")
    availability = artifact.get("availability")
    if not isinstance(aid, str) or not aid:
        _add(issues, "EVIDENCE_ARTIFACT_ID_INVALID", source_id, _ptr(json_pointer, "artifact_id"), "artifact_id must be non-empty")
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        _add(issues, "EVIDENCE_ARTIFACT_HASH_INVALID", source_id, _ptr(json_pointer, "sha256"), "sha256 must be canonical")
    if not isinstance(reference, str) or not reference:
        _add(issues, "EVIDENCE_ARTIFACT_REFERENCE_MISSING", source_id, _ptr(json_pointer, "reference"), "retained evidence requires a path or reference")
    if availability not in _AVAILABILITY:
        _add(issues, "EVIDENCE_AVAILABILITY_INVALID", source_id, _ptr(json_pointer, "availability"), "availability must be an explicit shared evidence state")

    if expected_schema is not None:
        raw = artifact.get("schema")
        if not isinstance(raw, Mapping):
            _add(issues, "EVIDENCE_SCHEMA_IDENTITY_MISSING", source_id, _ptr(json_pointer, "schema"), "required schema identity is missing")
        else:
            if raw.get("schema_id") != expected_schema.schema_id:
                _add(issues, "EVIDENCE_SCHEMA_ID_MISMATCH", source_id, _ptr(_ptr(json_pointer, "schema"), "schema_id"), "schema_id does not match required authority")
            if raw.get("schema_version") != expected_schema.schema_version:
                _add(issues, "EVIDENCE_SCHEMA_VERSION_MISMATCH", source_id, _ptr(_ptr(json_pointer, "schema"), "schema_version"), "schema_version does not match required authority")

    if source is not None:
        if aid != source.artifact_id:
            _add(issues, "EVIDENCE_ARTIFACT_SOURCE_ID_MISMATCH", source_id, _ptr(json_pointer, "artifact_id"), "artifact identity does not match trusted source")
        if reference != source.reference:
            _add(issues, "EVIDENCE_ARTIFACT_REFERENCE_MISMATCH", source_id, _ptr(json_pointer, "reference"), "artifact reference does not match trusted source")
        if digest != source.sha256:
            _add(issues, "EVIDENCE_ARTIFACT_HASH_MISMATCH", source_id, _ptr(json_pointer, "sha256"), "artifact hash does not match exact retained bytes")
    elif availability in _PRESENT:
        _add(issues, "EVIDENCE_ARTIFACT_SOURCE_MISSING", source_id, json_pointer, "authority-bearing retained evidence requires exact trusted bytes")

    if require_available and availability not in _PRESENT:
        _add(issues, "EVIDENCE_REQUIRED_ARTIFACT_UNAVAILABLE", source_id, _ptr(json_pointer, "availability"), "required evidence is not authority-bearing")
    return _norm(issues)


def validate_evidence_set(
    artifacts: Sequence[Mapping[str, Any]],
    *,
    sources: Sequence[RetainedArtifactSource],
    evidence_set_id: str,
    generation_id: str,
    terminal_state: str,
    source_id: str,
    required_artifact_ids: Sequence[str] = (),
    expected_schemas: Mapping[str, SchemaIdentity] | None = None,
) -> tuple[ValidationIssue, ...]:
    """Validate retained evidence without inferring or repairing authority."""

    _nonempty(evidence_set_id, "evidence_set_id")
    _nonempty(generation_id, "generation_id")
    _source_id(source_id)
    if terminal_state not in {"accepted", "blocked"}:
        raise ValueError("terminal_state must be 'accepted' or 'blocked'")
    required = _ids(required_artifact_ids)
    schemas = dict(expected_schemas or {})
    if any(not isinstance(k, str) or not k or type(v) is not SchemaIdentity for k, v in schemas.items()):
        raise TypeError("expected_schemas must map artifact IDs to SchemaIdentity")
    by_source: dict[str, RetainedArtifactSource] = {}
    for source in sources:
        if type(source) is not RetainedArtifactSource:
            raise TypeError("sources must contain RetainedArtifactSource")
        if source.artifact_id in by_source:
            raise ValueError(f"duplicate source for {source.artifact_id!r}")
        by_source[source.artifact_id] = source

    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    authoritative: set[str] = set()
    for index, artifact in enumerate(artifacts):
        pointer = f"/artifacts/{index}"
        if not isinstance(artifact, Mapping):
            _add(issues, "EVIDENCE_ARTIFACT_INVALID", source_id, pointer, "artifact declaration must be an object")
            continue
        aid = artifact.get("artifact_id")
        if not isinstance(aid, str) or not aid:
            issues.extend(validate_artifact_reference(artifact, source=None, source_id=source_id, json_pointer=pointer))
            continue
        if aid in seen:
            _add(issues, "EVIDENCE_ARTIFACT_ID_AMBIGUOUS", source_id, f"{pointer}/artifact_id", "artifact_id is duplicated")
        seen.add(aid)
        local = validate_artifact_reference(
            artifact,
            source=by_source.get(aid),
            source_id=source_id,
            json_pointer=pointer,
            expected_schema=schemas.get(aid),
            require_available=aid in required,
        )
        issues.extend(local)
        if not local and artifact.get("availability") in _PRESENT:
            authoritative.add(aid)

    for aid in sorted(required - seen):
        _add(issues, "EVIDENCE_REQUIRED_ARTIFACT_MISSING", source_id, "/artifacts", f"required artifact {aid!r} is missing")
    for aid in sorted((required & seen) - authoritative):
        _add(issues, "EVIDENCE_REQUIRED_ARTIFACT_NOT_AUTHORITATIVE", source_id, "/artifacts", f"required artifact {aid!r} lacks exact retained authority")
    for aid in sorted(set(by_source) - seen):
        _add(issues, "EVIDENCE_SOURCE_UNDECLARED", source_id, "/artifacts", f"trusted bytes for undeclared artifact {aid!r} were provided")
    return _norm(issues)


def validate_evidence_set_outcome(
    artifacts: Sequence[Mapping[str, Any]],
    **kwargs: Any,
) -> EvidenceSetValidationOutcome:
    """Validate and mint authority bound to exact artifact declarations and sources."""

    issues = validate_evidence_set(artifacts, **kwargs)
    sources = kwargs["sources"]
    payload = {
        "evidence_set_id": kwargs["evidence_set_id"],
        "generation_id": kwargs["generation_id"],
        "terminal_state": kwargs["terminal_state"],
        "artifacts": [dict(value) for value in artifacts],
        "sources": [
            {"artifact_id": s.artifact_id, "reference": s.reference, "sha256": s.sha256, "provenance": s.provenance}
            for s in sorted(sources, key=lambda item: item.artifact_id)
        ],
    }
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence authority inputs must be JSON-compatible") from exc
    identities = tuple(sorted(
        (a["artifact_id"], a["sha256"])
        for a in artifacts
        if isinstance(a, Mapping)
        and isinstance(a.get("artifact_id"), str)
        and isinstance(a.get("sha256"), str)
        and a.get("availability") in _PRESENT
    ))
    value = object.__new__(EvidenceSetValidationOutcome)
    for name, item in (
        ("evidence_set_id", kwargs["evidence_set_id"]),
        ("generation_id", kwargs["generation_id"]),
        ("source_id", kwargs["source_id"]),
        ("terminal_state", kwargs["terminal_state"]),
        ("evidence_fingerprint", sha256_bytes(encoded)),
        ("issues", issues),
        ("_identities", identities),
        ("_guard", _GUARD),
    ):
        object.__setattr__(value, name, item)
    return value


def _ids(values: Sequence[str]) -> frozenset[str]:
    if isinstance(values, str):
        raise TypeError("required_artifact_ids must be a sequence")
    result = tuple(values)
    if any(not isinstance(v, str) or not v for v in result):
        raise ValueError("required_artifact_ids must contain non-empty strings")
    if len(set(result)) != len(result):
        raise ValueError("required_artifact_ids must be unique")
    return frozenset(result)


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _source_id(value: str) -> None:
    _nonempty(value, "source_id")


def _ptr(pointer: str, segment: str) -> str:
    segment = segment.replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{segment}" if pointer else f"/{segment}"


def _add(issues: list[ValidationIssue], code: str, source_id: str, pointer: str, message: str) -> None:
    issues.append(ValidationIssue(code=code, source_id=source_id, json_pointer=pointer, message=message))


def _norm(issues: Sequence[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


__all__ = [
    "EvidenceSetValidationOutcome",
    "RetainedArtifactSource",
    "validate_artifact_reference",
    "validate_evidence_set",
    "validate_evidence_set_outcome",
]
