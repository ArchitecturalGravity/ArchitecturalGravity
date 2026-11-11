"""Fail-closed authority for registered supplemental validation extensions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
import re
from typing import Any

from .core import ValidationIssue, sha256_bytes
from .registration import ArtifactSource, RegistrationValidationOutcome
from .structure import _instance_issues, _schema_definition_issues

_NAMESPACE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[^\s]+$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_PREFIX = re.compile(r"^EXT_[A-Z][A-Z0-9_]*_$")
_KINDS = frozenset({"supplemental_schema", "logic"})
_GUARD = object()
_MISSING = object()


@dataclass(frozen=True)
class ValidationExtensionDeclaration:
    """Exact declaration stored at one namespaced registration extension key."""

    extension_key: str
    extension_id: str
    extension_version: str
    validation_kind: str
    implementation_artifact_id: str
    issue_code_prefix: str
    compatibility_scope: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _namespaced(self.extension_key) or not _namespaced(self.extension_id):
            raise ValueError("extension_key and extension_id must be namespaced")
        if not isinstance(self.extension_version, str) or not _SEMVER.fullmatch(self.extension_version):
            raise ValueError("extension_version must be an exact semantic version")
        if self.validation_kind not in _KINDS:
            raise ValueError("validation_kind must be supplemental_schema or logic")
        if not isinstance(self.implementation_artifact_id, str) or not self.implementation_artifact_id:
            raise ValueError("implementation_artifact_id must be non-empty")
        if not isinstance(self.issue_code_prefix, str) or not _PREFIX.fullmatch(self.issue_code_prefix):
            raise ValueError("issue_code_prefix must be an EXT_-namespaced uppercase prefix")
        namespace = re.sub(r"[^A-Za-z0-9]+", "_", self.extension_key.split(":", 1)[0]).strip("_").upper()
        if not self.issue_code_prefix.startswith(f"EXT_{namespace}_"):
            raise ValueError("issue_code_prefix must be namespaced to extension_key")
        if isinstance(self.compatibility_scope, str) or not isinstance(self.compatibility_scope, tuple) or not self.compatibility_scope:
            raise ValueError("compatibility_scope must be a non-empty tuple")
        if not all(_namespaced(value) for value in self.compatibility_scope):
            raise ValueError("compatibility_scope values must be namespaced")
        if len(set(self.compatibility_scope)) != len(self.compatibility_scope):
            raise ValueError("compatibility_scope must not contain duplicates")

    def to_dict(self) -> dict[str, object]:
        return {
            "extension_id": self.extension_id,
            "extension_version": self.extension_version,
            "validation_kind": self.validation_kind,
            "implementation_artifact_id": self.implementation_artifact_id,
            "issue_code_prefix": self.issue_code_prefix,
            "compatibility_scope": list(self.compatibility_scope),
        }


@dataclass(frozen=True, init=False)
class RegisteredValidationExtensionAuthority:
    """Opaque authority bound to exact validated registration and artifact identity."""

    source_id: str
    registration_sha256: str
    declaration: ValidationExtensionDeclaration
    artifact_reference: str | None
    artifact_sha256: str | None
    issues: tuple[ValidationIssue, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("authority values are minted by validate_registered_validation_extension_outcome")

    @property
    def valid(self) -> bool:
        return (
            getattr(self, "_guard", None) is _GUARD
            and not getattr(self, "issues", (None,))
            and isinstance(getattr(self, "artifact_reference", None), str)
            and isinstance(getattr(self, "artifact_sha256", None), str)
        )


def validate_registered_validation_extension(
    registration: Mapping[str, Any],
    *,
    registration_outcome: RegistrationValidationOutcome,
    declaration: ValidationExtensionDeclaration,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Require an active exact registration declaration and validated artifact."""

    _source(source_id)
    if not isinstance(registration, Mapping):
        raise TypeError("registration must be a mapping")
    if type(registration_outcome) is not RegistrationValidationOutcome:
        raise TypeError("registration_outcome must be RegistrationValidationOutcome")
    if type(declaration) is not ValidationExtensionDeclaration:
        raise TypeError("declaration must be ValidationExtensionDeclaration")

    issues: list[ValidationIssue] = []
    if not registration_outcome.valid:
        _add(issues, "VALIDATION_EXTENSION_REGISTRATION_AUTHORITY_INVALID", source_id, "/extensions", "valid registration authority is required")
    elif not registration_outcome.matches(registration, source_id=registration_outcome.source_id):
        _add(issues, "VALIDATION_EXTENSION_REGISTRATION_AUTHORITY_MISMATCH", source_id, "/extensions", "registration authority does not bind this exact registration")
    if registration.get("status") != "active":
        _add(issues, "VALIDATION_EXTENSION_REGISTRATION_NOT_ACTIVE", source_id, "/status", "only active registration may authorize validation extensions")

    extensions = registration.get("extensions")
    pointer = f"/extensions/{_escape(declaration.extension_key)}"
    if not isinstance(extensions, Mapping):
        _add(issues, "VALIDATION_EXTENSION_DECLARATIONS_INVALID", source_id, "/extensions", "registration extensions must be an object")
    else:
        registered = extensions.get(declaration.extension_key, _MISSING)
        if registered is _MISSING:
            _add(issues, "VALIDATION_EXTENSION_DECLARATION_MISSING", source_id, pointer, "validation extension is not explicitly registered")
        elif not _json_equal(registered, declaration.to_dict()):
            _add(issues, "VALIDATION_EXTENSION_DECLARATION_MISMATCH", source_id, pointer, "registered validation declaration does not match exactly")

    artifact = _artifact(registration, declaration.implementation_artifact_id)
    if artifact is None:
        _add(issues, "VALIDATION_EXTENSION_ARTIFACT_MISSING", source_id, "/implementation_artifacts", "exactly one registered implementation artifact is required")
    elif not isinstance(artifact.get("reference"), str) or not isinstance(artifact.get("sha256"), str):
        _add(issues, "VALIDATION_EXTENSION_ARTIFACT_IDENTITY_INVALID", source_id, "/implementation_artifacts", "registered extension artifact requires reference and SHA-256 identity")
    return _norm(issues)


def validate_registered_validation_extension_outcome(
    registration: Mapping[str, Any],
    *,
    registration_outcome: RegistrationValidationOutcome,
    declaration: ValidationExtensionDeclaration,
    source_id: str,
) -> RegisteredValidationExtensionAuthority:
    """Mint opaque authority for one exact registered validation extension."""

    issues = validate_registered_validation_extension(
        registration,
        registration_outcome=registration_outcome,
        declaration=declaration,
        source_id=source_id,
    )
    artifact = _artifact(registration, declaration.implementation_artifact_id)
    reference = artifact.get("reference") if artifact is not None else None
    digest = artifact.get("sha256") if artifact is not None else None
    value = object.__new__(RegisteredValidationExtensionAuthority)
    object.__setattr__(value, "source_id", source_id)
    object.__setattr__(value, "registration_sha256", registration_outcome.registration_sha256)
    object.__setattr__(value, "declaration", declaration)
    object.__setattr__(value, "artifact_reference", reference if isinstance(reference, str) else None)
    object.__setattr__(value, "artifact_sha256", digest if isinstance(digest, str) else None)
    object.__setattr__(value, "issues", issues)
    object.__setattr__(value, "_guard", _GUARD)
    return value


def validate_registered_supplemental_schema(
    document: Any,
    *,
    authority: RegisteredValidationExtensionAuthority,
    schema_source: ArtifactSource,
    compatibility_scope: str,
    source_id: str,
    shared_issues: Sequence[ValidationIssue],
) -> tuple[ValidationIssue, ...]:
    """Apply an exact registered schema only after shared validation succeeds."""

    shared = _shared(shared_issues)
    gate = _gate(authority, "supplemental_schema", schema_source, compatibility_scope, source_id)
    if shared or gate:
        return _norm((*shared, *gate))
    try:
        schema = _json_object(schema_source.data)
        value = _clone_json(document)
    except (TypeError, ValueError):
        return _norm((*shared, _issue("VALIDATION_EXTENSION_INPUT_INVALID", source_id, None, "supplemental schema and input must be finite JSON-compatible values")))

    definition = _schema_definition_issues(
        schema,
        root=schema,
        identity=None,
        source_id=schema_source.reference,
        schema_pointer="",
    )
    if definition:
        return _norm((*shared, *(_namespace(item, authority.declaration) for item in definition)))
    found = _instance_issues(
        value,
        schema,
        root=schema,
        identity=None,
        source_id=source_id,
        pointer="",
        ref_stack=(),
    )
    return _norm((*shared, *(_namespace(item, authority.declaration) for item in found)))


def validate_registered_logic(
    document: Any,
    *,
    authority: RegisteredValidationExtensionAuthority,
    logic_source: ArtifactSource,
    validator: Callable[[Any], Sequence[ValidationIssue]],
    compatibility_scope: str,
    source_id: str,
    shared_issues: Sequence[ValidationIssue],
) -> tuple[ValidationIssue, ...]:
    """Invoke benchmark-owned logic as a mutation-isolated additive issue producer."""

    if not callable(validator):
        raise TypeError("validator must be callable")
    shared = _shared(shared_issues)
    gate = _gate(authority, "logic", logic_source, compatibility_scope, source_id)
    if shared or gate:
        return _norm((*shared, *gate))
    try:
        value = _clone_json(document)
    except (TypeError, ValueError):
        return _norm((*shared, _issue("VALIDATION_EXTENSION_INPUT_INVALID", source_id, None, "registered logic input must be a finite JSON-compatible value")))
    try:
        raw = validator(value)
    except Exception:
        return _norm((*shared, _extension_issue(authority.declaration, "EXECUTION_FAILED", source_id, None, "registered validation logic failed")))
    extension = _logic_issues(raw, authority.declaration, source_id)
    if extension is None:
        return _norm((*shared, _issue("VALIDATION_EXTENSION_OUTPUT_INVALID", source_id, None, "registered logic returned invalid or non-namespaced issues")))
    return _norm((*shared, *extension))


def _gate(
    authority: RegisteredValidationExtensionAuthority,
    kind: str,
    source: ArtifactSource,
    scope: str,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    _source(source_id)
    if type(authority) is not RegisteredValidationExtensionAuthority:
        raise TypeError("authority must be RegisteredValidationExtensionAuthority")
    if type(source) is not ArtifactSource:
        raise TypeError("extension source must be ArtifactSource")
    if not _namespaced(scope):
        raise ValueError("compatibility_scope must be namespaced")
    if not authority.valid:
        return (_issue("VALIDATION_EXTENSION_AUTHORITY_INVALID", source_id, None, "registered extension authority is invalid"),)
    issues: list[ValidationIssue] = []
    if kind != authority.declaration.validation_kind:
        _add(issues, "VALIDATION_EXTENSION_KIND_MISMATCH", source_id, None, "extension kind does not authorize this operation")
    if scope not in authority.declaration.compatibility_scope:
        _add(issues, "VALIDATION_EXTENSION_SCOPE_UNAUTHORIZED", source_id, None, "extension does not authorize this compatibility scope")
    if source.artifact_id != authority.declaration.implementation_artifact_id:
        _add(issues, "VALIDATION_EXTENSION_ARTIFACT_ID_MISMATCH", source_id, None, "extension artifact_id does not match registered authority")
    if source.reference != authority.artifact_reference:
        _add(issues, "VALIDATION_EXTENSION_ARTIFACT_REFERENCE_MISMATCH", source_id, None, "extension artifact reference does not match registered authority")
    if sha256_bytes(source.data) != authority.artifact_sha256:
        _add(issues, "VALIDATION_EXTENSION_ARTIFACT_HASH_MISMATCH", source_id, None, "extension artifact bytes do not match registered authority")
    return _norm(issues)


def _logic_issues(values: object, declaration: ValidationExtensionDeclaration, source_id: str) -> tuple[ValidationIssue, ...] | None:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        return None
    issues = tuple(values)
    if not all(type(item) is ValidationIssue for item in issues):
        return None
    if any(not item.code.startswith(declaration.issue_code_prefix) or item.source_id != source_id or item.schema is not None for item in issues):
        return None
    return _norm(issues)


def _artifact(registration: Mapping[str, Any], artifact_id: str) -> Mapping[str, Any] | None:
    artifacts = registration.get("implementation_artifacts")
    if not isinstance(artifacts, list):
        return None
    matches = [item for item in artifacts if isinstance(item, Mapping) and item.get("artifact_id") == artifact_id]
    return matches[0] if len(matches) == 1 else None


def _json_object(data: bytes) -> Mapping[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid JSON bytes") from exc
    if not isinstance(value, Mapping):
        raise ValueError("schema must be a JSON object")
    return value


def _clone_json(value: Any) -> Any:
    if not _json_value(value):
        raise ValueError("not JSON-compatible")
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))


def _json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False


def _shared(values: Sequence[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("shared_issues must be a sequence")
    issues = tuple(values)
    if not all(type(item) is ValidationIssue for item in issues):
        raise TypeError("shared_issues must contain ValidationIssue values")
    return _norm(issues)


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(_json_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def _namespace(issue: ValidationIssue, declaration: ValidationExtensionDeclaration) -> ValidationIssue:
    return ValidationIssue(code=declaration.issue_code_prefix + issue.code, source_id=issue.source_id, message=issue.message, json_pointer=issue.json_pointer)


def _extension_issue(declaration: ValidationExtensionDeclaration, suffix: str, source_id: str, pointer: str | None, message: str) -> ValidationIssue:
    return _issue(declaration.issue_code_prefix + suffix, source_id, pointer, message)


def _namespaced(value: object) -> bool:
    return isinstance(value, str) and _NAMESPACE.fullmatch(value) is not None


def _source(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id must be a non-empty string")


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _issue(code: str, source_id: str, pointer: str | None, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, source_id=source_id, json_pointer=pointer, message=message)


def _add(issues: list[ValidationIssue], code: str, source_id: str, pointer: str | None, message: str) -> None:
    issues.append(_issue(code, source_id, pointer, message))


def _norm(issues: Sequence[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


__all__ = [
    "RegisteredValidationExtensionAuthority",
    "ValidationExtensionDeclaration",
    "validate_registered_logic",
    "validate_registered_supplemental_schema",
    "validate_registered_validation_extension",
    "validate_registered_validation_extension_outcome",
]
