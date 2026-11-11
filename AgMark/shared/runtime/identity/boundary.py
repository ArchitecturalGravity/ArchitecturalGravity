"""Canonical execution-boundary identity and immutable acceptance primitives."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Final

from .runtime_version import retained_runtime_version

from .canonical import (
    CANONICALIZATION,
    CanonicalizationError,
    canonical_json_bytes,
    canonical_sha256,
)


EXECUTION_BOUNDARY_SCHEMA_ID: Final[str] = "arcgrav.shared.schema.execution-boundary"
EXECUTION_BOUNDARY_SCHEMA_VERSION: Final[str] = "1.0.0"

_SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXTENSION_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[^\s]+$")

_FORBIDDEN_EXACT_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "auth_token",
        "bearer_token",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "private_key",
        "credential",
        "credentials",
        "credential_value",
        "credential_source",
        "credential_locator",
        "credential_handle",
        "authorization",
        "cookie",
        "session_cookie",
    }
)
_FORBIDDEN_SUFFIX = re.compile(
    r"(?:^|_)(?:secret|token|password|passwd|private_key|api_key|apikey|credential)"
    r"_(?:value|locator|handle|path|file|env|environment_variable)$"
)

# Durable identity is a closed measurement-control surface, not a configuration dump.
_RETAINED_CONTROLS = frozenset({
    "model", "model_id", "reasoning_effort", "temperature", "max_tokens",
    "request_timeout_ms", "maximum_attempts", "memory_policy", "request_framing",
    "sampling_mode", "tool_policy", "approval_mode", "launch_mode", "capture_mode",
    "diagnostic_privacy_acknowledged", "network_access", "response_mode", "mock_outcome",
    "codex_binary", "model_selection_mode",
})
_RETAINED_ENVIRONMENT = frozenset({"runtime_family", "golden.environment_family", "golden.runtime_sha256"})


def _retained_reference(value: str) -> None:
    path = PurePosixPath(value)
    if (not value or "\\" in value or PureWindowsPath(value).drive or path.is_absolute()
            or ".." in path.parts or "://" in value or value != path.as_posix()):
        raise IdentityError("retained identity reference must be a normalized relative resource reference")


def _retained_control(name: str, value: object, field: str) -> None:
    allowed = _RETAINED_ENVIRONMENT if field == "environment" else _RETAINED_CONTROLS
    if name not in allowed:
        raise IdentityError("identity contains an undeclared retained control")
    if value is not None and type(value) not in {str, int, float, bool}:
        raise IdentityError("retained controls must be scalar measurement settings")
    if isinstance(value, str):
        if (len(value) > 256 or "\\" in value or value.startswith(("/", "~"))
                or PureWindowsPath(value).drive or "@" in value and name != "diagnostic_privacy_acknowledged"
                or any(ord(c) < 32 for c in value) or "://" in value):
            raise IdentityError("retained controls cannot contain identifying locators or free-form text")
        if name == "codex_binary":
            _retained_reference(value)
            if value != "runtime/codex":
                raise IdentityError("retained executable control must use its runtime-relative logical reference")
    if name in {"temperature", "max_tokens", "request_timeout_ms", "maximum_attempts"} and type(value) not in {int, float}:
        raise IdentityError("numeric retained controls require numbers")
    if name == "golden.runtime_sha256":
        _require_sha256(value, "golden.runtime_sha256")


_BOUNDARY_KEYS = frozenset(
    {
        "schema_id",
        "schema_version",
        "extensions",
        "boundary_id",
        "canonicalization",
        "canonical_sha256",
        "fingerprint",
        "framework",
        "runner",
        "provider_runtime",
        "controls",
        "environment",
    }
)
_COMPARISON_KEYS = (
    "schema_id",
    "schema_version",
    "extensions",
    "canonicalization",
    "framework",
    "runner",
    "provider_runtime",
    "controls",
    "environment",
)


class IdentityError(ValueError):
    """Base class for runtime identity failures."""


class SecretIdentityInputError(IdentityError):
    """Raised when a secret-bearing field is offered to canonical identity."""


class IdentityIntegrityError(IdentityError):
    """Raised when retained identity no longer matches its canonical hashes."""


class DuplicateExecutionBoundaryFingerprint(IdentityError):
    """Raised when one plan contains a repeated comparison fingerprint."""


@dataclass(frozen=True)
class IdentityRef:
    """Exact identity/version reference used by an execution boundary."""

    id: str
    version: str
    sha256: str | None = None
    reference: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.id, "identity id")
        _require_semver(self.version, "identity version")
        if self.sha256 is not None:
            _require_sha256(self.sha256, "identity sha256")
        if self.reference is not None:
            _require_nonempty(self.reference, "identity reference")
            _retained_reference(self.reference)

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {"id": self.id, "version": self.version}
        if self.sha256 is not None:
            value["sha256"] = self.sha256
        if self.reference is not None:
            value["reference"] = self.reference
        return value

    @classmethod
    def from_value(cls, value: "IdentityRef | Mapping[str, object]", *, field: str) -> "IdentityRef":
        if type(value) is cls:
            return value
        if not isinstance(value, Mapping):
            raise IdentityError(f"{field} must be an IdentityRef or mapping")
        allowed = {"id", "version", "sha256", "reference"}
        unknown = set(value) - allowed
        if unknown:
            raise IdentityError(f"{field} contains undeclared fields: {sorted(unknown)!r}")
        if "id" not in value or "version" not in value:
            raise IdentityError(f"{field} requires id and version")
        return cls(
            id=_require_type(value["id"], str, f"{field}.id"),
            version=_require_type(value["version"], str, f"{field}.version"),
            sha256=_optional_string(value.get("sha256"), f"{field}.sha256"),
            reference=_optional_string(value.get("reference"), f"{field}.reference"),
        )


@dataclass(frozen=True)
class ProviderRuntimeIdentity:
    """Declared provider/runtime/model access identity."""

    runtime_id: str
    access_method: str
    runtime_version: str | None = None
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.runtime_id, "provider_runtime.runtime_id")
        _require_nonempty(self.access_method, "provider_runtime.access_method")
        for field, value in (
            ("runtime_version", self.runtime_version),
            ("provider", self.provider),
            ("model", self.model),
        ):
            if value is not None and not isinstance(value, str):
                raise IdentityError(f"provider_runtime.{field} must be string or null")
            if isinstance(value, str) and (len(value) > 256 or value.startswith(("/", "~"))
                    or "\\" in value or "@" in value or "://" in value
                    or any(ord(c) < 32 for c in value)):
                raise IdentityError("runtime identity cannot contain identifying locators")

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime_id": self.runtime_id,
            "runtime_version": retained_runtime_version(self.runtime_version),
            "provider": self.provider,
            "access_method": self.access_method,
            "model": self.model,
        }

    @classmethod
    def from_value(
        cls,
        value: "ProviderRuntimeIdentity | Mapping[str, object]",
    ) -> "ProviderRuntimeIdentity":
        if type(value) is cls:
            return value
        if not isinstance(value, Mapping):
            raise IdentityError("provider_runtime must be ProviderRuntimeIdentity or mapping")
        allowed = {"runtime_id", "runtime_version", "provider", "access_method", "model"}
        unknown = set(value) - allowed
        if unknown:
            raise IdentityError(
                f"provider_runtime contains undeclared fields: {sorted(unknown)!r}"
            )
        if "runtime_id" not in value or "access_method" not in value:
            raise IdentityError("provider_runtime requires runtime_id and access_method")
        return cls(
            runtime_id=_require_type(value["runtime_id"], str, "provider_runtime.runtime_id"),
            runtime_version=_optional_nullable_string(
                value.get("runtime_version"), "provider_runtime.runtime_version"
            ),
            provider=_optional_nullable_string(value.get("provider"), "provider_runtime.provider"),
            access_method=_require_type(
                value["access_method"], str, "provider_runtime.access_method"
            ),
            model=_optional_nullable_string(value.get("model"), "provider_runtime.model"),
        )


@dataclass(frozen=True)
class ExecutionBoundary:
    """Immutable canonical declared execution boundary.

    Directly observed effective-execution facts are intentionally not accepted by
    this type. They remain separate evidence bound later by the boundary
    fingerprint.
    """

    boundary_id: str
    canonical_sha256: str
    fingerprint: str
    _canonical_bytes: bytes
    _comparison_bytes: bytes

    @classmethod
    def build(
        cls,
        *,
        boundary_id: str,
        framework: IdentityRef | Mapping[str, object],
        runner: IdentityRef | Mapping[str, object],
        provider_runtime: ProviderRuntimeIdentity | Mapping[str, object],
        controls: Mapping[str, object] | None = None,
        environment: Mapping[str, object] | None = None,
        extensions: Mapping[str, object] | None = None,
    ) -> "ExecutionBoundary":
        _require_nonempty(boundary_id, "boundary_id")
        document = {
            "schema_id": EXECUTION_BOUNDARY_SCHEMA_ID,
            "schema_version": EXECUTION_BOUNDARY_SCHEMA_VERSION,
            "extensions": _normalize_extensions(extensions or {}),
            "boundary_id": boundary_id,
            "canonicalization": CANONICALIZATION,
            "framework": IdentityRef.from_value(framework, field="framework").to_dict(),
            "runner": IdentityRef.from_value(runner, field="runner").to_dict(),
            "provider_runtime": ProviderRuntimeIdentity.from_value(provider_runtime).to_dict(),
            "controls": _normalize_named_values(controls or {}, field="controls"),
            "environment": _normalize_named_values(environment or {}, field="environment"),
        }
        return cls._from_normalized_base(document)

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "ExecutionBoundary":
        """Validate and reconstitute a retained execution-boundary document."""

        if not isinstance(document, Mapping):
            raise IdentityError("execution boundary document must be a mapping")
        unknown = set(document) - _BOUNDARY_KEYS
        missing = _BOUNDARY_KEYS - set(document)
        if unknown:
            raise IdentityError(f"execution boundary contains undeclared fields: {sorted(unknown)!r}")
        if missing:
            raise IdentityError(f"execution boundary is missing fields: {sorted(missing)!r}")
        if document["schema_id"] != EXECUTION_BOUNDARY_SCHEMA_ID:
            raise IdentityError("execution boundary schema_id is not supported")
        if document["schema_version"] != EXECUTION_BOUNDARY_SCHEMA_VERSION:
            raise IdentityError("execution boundary schema_version is not supported")
        if document["canonicalization"] != CANONICALIZATION:
            raise IdentityError("execution boundary canonicalization is not supported")

        boundary_id = _require_type(document["boundary_id"], str, "boundary_id")
        _require_nonempty(boundary_id, "boundary_id")
        claimed_canonical = _require_type(
            document["canonical_sha256"], str, "canonical_sha256"
        )
        claimed_fingerprint = _require_type(document["fingerprint"], str, "fingerprint")
        _require_sha256(claimed_canonical, "canonical_sha256")
        _require_sha256(claimed_fingerprint, "fingerprint")

        framework = IdentityRef.from_value(
            _require_mapping(document["framework"], "framework"), field="framework"
        ).to_dict()
        runner = IdentityRef.from_value(
            _require_mapping(document["runner"], "runner"), field="runner"
        ).to_dict()
        raw_runtime = _require_mapping(document["provider_runtime"], "provider_runtime")
        version = raw_runtime.get("runtime_version")
        if version is not None and retained_runtime_version(version) != version:
            raise IdentityError("provider_runtime.runtime_version must be a retained numeric core")
        provider_runtime = ProviderRuntimeIdentity.from_value(raw_runtime).to_dict()
        controls = _normalize_named_value_records(document["controls"], field="controls")
        environment = _normalize_named_value_records(
            document["environment"], field="environment"
        )
        extensions = _normalize_extensions(
            _require_mapping(document["extensions"], "extensions")
        )

        base = {
            "schema_id": EXECUTION_BOUNDARY_SCHEMA_ID,
            "schema_version": EXECUTION_BOUNDARY_SCHEMA_VERSION,
            "extensions": extensions,
            "boundary_id": boundary_id,
            "canonicalization": CANONICALIZATION,
            "framework": framework,
            "runner": runner,
            "provider_runtime": provider_runtime,
            "controls": controls,
            "environment": environment,
        }
        rebuilt = cls._from_normalized_base(base)
        if rebuilt.fingerprint != claimed_fingerprint:
            raise IdentityIntegrityError(
                "execution boundary fingerprint does not match canonical comparison controls"
            )
        if rebuilt.canonical_sha256 != claimed_canonical:
            raise IdentityIntegrityError(
                "execution boundary canonical_sha256 does not match retained canonical record"
            )
        return rebuilt

    @classmethod
    def _from_normalized_base(cls, base: Mapping[str, object]) -> "ExecutionBoundary":
        comparison = {key: base[key] for key in _COMPARISON_KEYS}
        comparison_bytes = canonical_json_bytes(comparison)
        fingerprint = canonical_sha256(comparison)
        artifact_preimage = dict(base)
        artifact_preimage["fingerprint"] = fingerprint
        canonical_digest = canonical_sha256(artifact_preimage)
        document = dict(artifact_preimage)
        document["canonical_sha256"] = canonical_digest
        canonical_bytes = canonical_json_bytes(document)
        return cls(
            boundary_id=_require_type(base["boundary_id"], str, "boundary_id"),
            canonical_sha256=canonical_digest,
            fingerprint=fingerprint,
            _canonical_bytes=canonical_bytes,
            _comparison_bytes=comparison_bytes,
        )

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def comparison_bytes(self) -> bytes:
        return self._comparison_bytes

    def to_dict(self) -> dict[str, object]:
        return json.loads(self._canonical_bytes.decode("utf-8"))

    def revalidate(self) -> None:
        ExecutionBoundary.from_document(self.to_dict())


@dataclass(frozen=True)
class AcceptedBoundaryIdentity:
    """Frozen accepted identity for one exact canonical execution boundary."""

    accepted_identity_id: str
    boundary_id: str
    canonical_sha256: str
    fingerprint: str
    _canonical_bytes: bytes

    @classmethod
    def accept(
        cls,
        *,
        accepted_identity_id: str,
        boundary: ExecutionBoundary,
    ) -> "AcceptedBoundaryIdentity":
        _require_nonempty(accepted_identity_id, "accepted_identity_id")
        if type(boundary) is not ExecutionBoundary:
            raise IdentityError("boundary must be an ExecutionBoundary")
        boundary.revalidate()
        return cls(
            accepted_identity_id=accepted_identity_id,
            boundary_id=boundary.boundary_id,
            canonical_sha256=boundary.canonical_sha256,
            fingerprint=boundary.fingerprint,
            _canonical_bytes=boundary.canonical_bytes,
        )

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    def boundary(self) -> ExecutionBoundary:
        return ExecutionBoundary.from_document(
            json.loads(self._canonical_bytes.decode("utf-8"))
        )

    def revalidate(self, retained_document: Mapping[str, object]) -> ExecutionBoundary:
        current = ExecutionBoundary.from_document(retained_document)
        if current.boundary_id != self.boundary_id:
            raise IdentityIntegrityError("accepted boundary_id changed after acceptance")
        if current.fingerprint != self.fingerprint:
            raise IdentityIntegrityError("accepted comparison fingerprint changed after acceptance")
        if current.canonical_sha256 != self.canonical_sha256:
            raise IdentityIntegrityError("accepted canonical boundary changed after acceptance")
        if current.canonical_bytes != self._canonical_bytes:
            raise IdentityIntegrityError("accepted canonical bytes changed after acceptance")
        return current


def ensure_unique_boundary_fingerprints(
    boundaries: Iterable[ExecutionBoundary],
) -> None:
    """Reject duplicate comparison identities before plan acceptance."""

    seen: dict[str, str] = {}
    for index, boundary in enumerate(boundaries):
        if type(boundary) is not ExecutionBoundary:
            raise IdentityError(
                f"boundaries[{index}] must be an ExecutionBoundary"
            )
        boundary.revalidate()
        prior = seen.get(boundary.fingerprint)
        if prior is not None:
            raise DuplicateExecutionBoundaryFingerprint(
                "duplicate execution-boundary comparison fingerprint "
                f"{boundary.fingerprint} for {prior!r} and {boundary.boundary_id!r}"
            )
        seen[boundary.fingerprint] = boundary.boundary_id


def _normalize_named_values(
    values: Mapping[str, object],
    *,
    field: str,
) -> list[dict[str, object]]:
    if not isinstance(values, Mapping):
        raise IdentityError(f"{field} must be a mapping of comparison-relevant values")
    normalized: list[dict[str, object]] = []
    for name, value in values.items():
        if not isinstance(name, str) or not name:
            raise IdentityError(f"{field} names must be non-empty strings")
        _reject_secret_name(name, f"{field}.{name}")
        normalized_value = _canonical_roundtrip(value, path=f"{field}.{name}")
        _reject_secret_keys(normalized_value, path=f"{field}.{name}")
        _retained_control(name, normalized_value, field)
        normalized.append({"name": name, "value": normalized_value})
    normalized.sort(key=lambda item: item["name"])
    return normalized


def _normalize_named_value_records(value: object, *, field: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise IdentityError(f"{field} must be an array of name/value records")
    normalized: list[dict[str, object]] = []
    names: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {"name", "value"}:
            raise IdentityError(f"{field}[{index}] must contain exactly name and value")
        name = _require_type(item["name"], str, f"{field}[{index}].name")
        if not name:
            raise IdentityError(f"{field}[{index}].name must be non-empty")
        if name in names:
            raise IdentityError(f"{field} contains duplicate control name {name!r}")
        names.add(name)
        _reject_secret_name(name, f"{field}.{name}")
        normalized_value = _canonical_roundtrip(item["value"], path=f"{field}.{name}")
        _reject_secret_keys(normalized_value, path=f"{field}.{name}")
        _retained_control(name, normalized_value, field)
        normalized.append({"name": name, "value": normalized_value})
    expected = sorted(normalized, key=lambda item: item["name"])
    if normalized != expected:
        raise IdentityError(f"{field} records are not in canonical name order")
    return normalized


def _normalize_extensions(extensions: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(extensions, Mapping):
        raise IdentityError("extensions must be a mapping")
    normalized: dict[str, object] = {}
    for key, value in extensions.items():
        if not isinstance(key, str) or _EXTENSION_KEY.fullmatch(key) is None:
            raise IdentityError(f"extension key {key!r} is not namespaced")
        _reject_secret_name(key.split(":", 1)[1], f"extensions.{key}")
        normalized_value = _canonical_roundtrip(value, path=f"extensions.{key}")
        _reject_secret_keys(normalized_value, path=f"extensions.{key}")
        raise IdentityError("undeclared execution-boundary extensions cannot enter retained identity")
    return normalized


def _canonical_roundtrip(value: object, *, path: str) -> object:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except CanonicalizationError as exc:
        raise IdentityError(f"{path}: {exc}") from exc


def _reject_secret_keys(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_secret_name(key, f"{path}.{key}")
            _reject_secret_keys(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_keys(item, path=f"{path}[{index}]")


def _reject_secret_name(name: str, path: str) -> None:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if normalized in _FORBIDDEN_EXACT_NAMES or _FORBIDDEN_SUFFIX.search(normalized):
        raise SecretIdentityInputError(
            f"{path} is secret-bearing or a raw credential locator and cannot enter identity"
        )


def _require_nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise IdentityError(f"{field} must be a non-empty string")
    return value


def _require_semver(value: object, field: str) -> str:
    if not isinstance(value, str) or _SEMANTIC_VERSION.fullmatch(value) is None:
        raise IdentityError(f"{field} must be an exact semantic version")
    return value


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise IdentityError(f"{field} must use 'sha256:' plus 64 lowercase hex digits")
    return value


def _require_type(value: object, expected: type, field: str):
    if not isinstance(value, expected):
        raise IdentityError(f"{field} must be {expected.__name__}")
    return value


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise IdentityError(f"{field} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise IdentityError(f"{field} keys must be strings")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise IdentityError(f"{field} must be a string when provided")
    return value


def _optional_nullable_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise IdentityError(f"{field} must be string or null")
    return value


__all__ = [
    "EXECUTION_BOUNDARY_SCHEMA_ID",
    "EXECUTION_BOUNDARY_SCHEMA_VERSION",
    "AcceptedBoundaryIdentity",
    "DuplicateExecutionBoundaryFingerprint",
    "ExecutionBoundary",
    "IdentityError",
    "IdentityIntegrityError",
    "IdentityRef",
    "ProviderRuntimeIdentity",
    "SecretIdentityInputError",
    "ensure_unique_boundary_fingerprints",
]
