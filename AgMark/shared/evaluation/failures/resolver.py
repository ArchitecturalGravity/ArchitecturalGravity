"""Deterministic benchmark-neutral failure taxonomy resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Final


FAILURE_TAXONOMY_CONTRACT_ID: Final[str] = "arcgrav.shared.failure-taxonomy"
FAILURE_TAXONOMY_CONTRACT_VERSION: Final[str] = "1.0.0"

AUTHORITY_LAYERS: Final[tuple[str, ...]] = (
    "registration",
    "identity_integrity",
    "admission_isolation",
    "execution",
    "evidence",
    "scoring",
    "availability",
    "task",
)

_CANONICAL_CLASS_PRECEDENCE = {
    "registration": (
        "contract_incompatible",
        "schema_incompatible",
        "registration_invalid",
    ),
    "identity_integrity": (
        "secret_retention_violation",
        "artifact_integrity_mismatch",
        "identity_mismatch",
        "source_drift",
    ),
    "admission_isolation": (
        "admission_blocked",
        "isolation_violation",
    ),
    "execution": (
        "unsupported_execution",
        "timed_out",
        "cancelled",
        "execution_failed",
    ),
    "evidence": (
        "evidence_invalid",
        "evidence_missing",
        "evidence_duplicate",
        "evidence_unexpected",
        "evidence_nonterminal",
    ),
    "scoring": (
        "scorer_unavailable",
        "scorer_failed",
        "score_artifact_invalid",
    ),
    "availability": (
        "required_input_unavailable",
        "required_measurement_unavailable",
        "non_comparable",
        "completed_non_scorable",
    ),
    "task": (
        "task_malformed",
        "task_refused",
        "task_incorrect",
    ),
}
CANONICAL_CLASS_PRECEDENCE: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    _CANONICAL_CLASS_PRECEDENCE
)
_CANONICAL_CLASS_LAYER: Final[dict[str, str]] = {
    class_id: layer
    for layer, classes in _CANONICAL_CLASS_PRECEDENCE.items()
    for class_id in classes
}

_RUNNER_STATUS_FAILURE_CLASS = {
    "completed": None,
    "unsupported": "unsupported_execution",
    "timed_out": "timed_out",
    "cancelled": "cancelled",
    "failed": "execution_failed",
}
RUNNER_STATUS_FAILURE_CLASS: Final[Mapping[str, str | None]] = MappingProxyType(
    _RUNNER_STATUS_FAILURE_CLASS
)

_SEMVER = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
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


@dataclass(frozen=True, slots=True)
class ContractIdentity:
    """Exact durable contract identity retained with a failure candidate."""

    id: str
    version: str

    def __post_init__(self) -> None:
        _require_nonempty(self.id, "id")
        _require_semver(self.version, "version")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True, slots=True)
class FailureCandidate:
    """One already-detected failure candidate offered to shared resolution."""

    candidate_id: str
    failure_class: str
    authority_layer: str
    affected_evidence_id: str
    source_id: str
    diagnostic_id: str
    generation_id: str | None = None
    class_version: str | None = None
    upstream_contracts: tuple[ContractIdentity, ...] = ()
    redacted_details: Mapping[str, object] = field(default_factory=dict)
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "candidate_id",
            "failure_class",
            "authority_layer",
            "affected_evidence_id",
            "source_id",
            "diagnostic_id",
        ):
            _require_nonempty(getattr(self, name), name)
        if self.generation_id is not None:
            _require_nonempty(self.generation_id, "generation_id")
        if self.class_version is not None:
            _require_semver(self.class_version, "class_version")
        if not isinstance(self.upstream_contracts, tuple) or any(
            type(value) is not ContractIdentity for value in self.upstream_contracts
        ):
            raise TypeError("upstream_contracts must be a tuple of ContractIdentity values")
        if len({(value.id, value.version) for value in self.upstream_contracts}) != len(
            self.upstream_contracts
        ):
            raise ValueError("upstream_contracts must not contain duplicates")

        details = _freeze_json_mapping(
            self.redacted_details,
            field_name="redacted_details",
            require_namespaced_keys=False,
        )
        extensions = _freeze_json_mapping(
            self.extensions,
            field_name="extensions",
            require_namespaced_keys=True,
        )
        object.__setattr__(self, "redacted_details", details)
        object.__setattr__(self, "extensions", extensions)

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "candidate_id": self.candidate_id,
            "failure_class": self.failure_class,
            "authority_layer": self.authority_layer,
            "affected_evidence_id": self.affected_evidence_id,
            "source_id": self.source_id,
            "diagnostic_id": self.diagnostic_id,
            "upstream_contracts": [
                item.to_dict()
                for item in sorted(
                    self.upstream_contracts,
                    key=lambda item: (_serialized_identifier_key(item.id), _serialized_identifier_key(item.version)),
                )
            ],
            "redacted_details": _thaw_json(self.redacted_details),
            "extensions": _thaw_json(self.extensions),
        }
        if self.generation_id is not None:
            value["generation_id"] = self.generation_id
        if self.class_version is not None:
            value["class_version"] = self.class_version
        return value


@dataclass(frozen=True, slots=True)
class ExtensionFailureClassRegistration:
    """Validated authority describing one namespaced extension failure class."""

    class_id: str
    version: str
    meaning: str
    producing_authority: str
    applicable_evidence_scope: str
    authority_layer: str
    anchor_class: str
    position: str
    compatibility_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_namespaced(self.class_id, "class_id")
        if self.class_id in _CANONICAL_CLASS_LAYER:
            raise ValueError("class_id must not replace a canonical failure class")
        _require_semver(self.version, "version")
        for name in ("meaning", "producing_authority", "applicable_evidence_scope"):
            _require_nonempty(getattr(self, name), name)
        if self.authority_layer not in AUTHORITY_LAYERS:
            raise ValueError("authority_layer must be a canonical authority layer")
        expected_anchor_layer = _CANONICAL_CLASS_LAYER.get(self.anchor_class)
        if expected_anchor_layer != self.authority_layer:
            raise ValueError(
                "anchor_class must be a canonical class in the declared authority_layer"
            )
        if self.position not in {"before", "after"}:
            raise ValueError("position must be 'before' or 'after'")
        if not isinstance(self.compatibility_constraints, tuple) or any(
            not isinstance(value, str) or not value
            for value in self.compatibility_constraints
        ):
            raise TypeError(
                "compatibility_constraints must be a tuple of non-empty strings"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "class_id": self.class_id,
            "version": self.version,
            "meaning": self.meaning,
            "producing_authority": self.producing_authority,
            "applicable_evidence_scope": self.applicable_evidence_scope,
            "authority_layer": self.authority_layer,
            "anchor_class": self.anchor_class,
            "position": self.position,
            "compatibility_constraints": list(self.compatibility_constraints),
        }


@dataclass(frozen=True, slots=True)
class MetricPrecedenceOverride:
    """Metric-local reordering of classes within one authority layer."""

    metric_registration_id: str
    metric_registration_version: str
    authority_layer: str
    ordered_classes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonempty(self.metric_registration_id, "metric_registration_id")
        _require_semver(
            self.metric_registration_version,
            "metric_registration_version",
        )
        if self.authority_layer not in AUTHORITY_LAYERS:
            raise ValueError("authority_layer must be a canonical authority layer")
        if not isinstance(self.ordered_classes, tuple) or not self.ordered_classes:
            raise ValueError("ordered_classes must be a non-empty tuple")
        if any(not isinstance(value, str) or not value for value in self.ordered_classes):
            raise TypeError("ordered_classes must contain non-empty strings")
        if len(set(self.ordered_classes)) != len(self.ordered_classes):
            raise ValueError("ordered_classes must not contain duplicates")

    def to_dict(self) -> dict[str, object]:
        return {
            "metric_registration_id": self.metric_registration_id,
            "metric_registration_version": self.metric_registration_version,
            "authority_layer": self.authority_layer,
            "ordered_classes": list(self.ordered_classes),
        }


@dataclass(frozen=True, order=True, slots=True)
class CandidateValidationIssue:
    """Stable validation issue raised before failure precedence is applied."""

    code: str
    candidate_id: str
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "candidate_id": self.candidate_id,
            "field": self.field,
            "message": self.message,
        }


class FailureValidationError(ValueError):
    """Raised when an invalid candidate set cannot yield failure authority."""

    def __init__(self, issues: Sequence[CandidateValidationIssue]) -> None:
        normalized = tuple(sorted(set(issues)))
        if not normalized:
            raise ValueError("FailureValidationError requires at least one issue")
        self.issues = normalized
        super().__init__(
            "; ".join(
                f"{issue.code}:{issue.candidate_id}:{issue.field}"
                for issue in normalized
            )
        )


@dataclass(frozen=True, slots=True)
class FailureResolution:
    """Deterministic primary failure plus all retained and suppressed candidates."""

    primary: FailureCandidate
    candidates: tuple[FailureCandidate, ...]
    suppressed: tuple[FailureCandidate, ...]
    precedence_basis: Mapping[str, object]
    resolution_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": {
                "id": FAILURE_TAXONOMY_CONTRACT_ID,
                "version": FAILURE_TAXONOMY_CONTRACT_VERSION,
            },
            "primary": self.primary.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "suppressed": [candidate.to_dict() for candidate in self.suppressed],
            "precedence_basis": _thaw_json(self.precedence_basis),
            "resolution_sha256": self.resolution_sha256,
        }


def runner_terminal_failure_class(terminal_status: str) -> str | None:
    """Map a normalized runner terminal status without mutating runner evidence."""

    if not isinstance(terminal_status, str):
        raise TypeError("terminal_status must be a string")
    try:
        return _RUNNER_STATUS_FAILURE_CLASS[terminal_status]
    except KeyError as exc:
        raise ValueError(f"unknown runner terminal status {terminal_status!r}") from exc


def resolve_failures(
    candidates: Sequence[FailureCandidate],
    *,
    extension_classes: Sequence[ExtensionFailureClassRegistration] = (),
) -> FailureResolution:
    """Resolve the global shared primary failure using default contract precedence."""

    return _resolve_failures(
        candidates,
        extension_classes=extension_classes,
        metric_override=None,
    )


def resolve_metric_failures(
    candidates: Sequence[FailureCandidate],
    *,
    precedence_override: MetricPrecedenceOverride,
    extension_classes: Sequence[ExtensionFailureClassRegistration] = (),
) -> FailureResolution:
    """Resolve a metric-local disposition with a permitted within-layer override."""

    if type(precedence_override) is not MetricPrecedenceOverride:
        raise TypeError("precedence_override must be MetricPrecedenceOverride")
    return _resolve_failures(
        candidates,
        extension_classes=extension_classes,
        metric_override=precedence_override,
    )


def _resolve_failures(
    candidates: Sequence[FailureCandidate],
    *,
    extension_classes: Sequence[ExtensionFailureClassRegistration],
    metric_override: MetricPrecedenceOverride | None,
) -> FailureResolution:
    candidate_values = _typed_tuple(candidates, FailureCandidate, "candidates")
    extension_values = _typed_tuple(
        extension_classes,
        ExtensionFailureClassRegistration,
        "extension_classes",
    )
    extension_by_id, registration_issues = _extension_index(extension_values)
    issues = list(registration_issues)
    issues.extend(_validate_candidates(candidate_values, extension_by_id))

    class_orders = {
        layer: _layer_class_order(layer, extension_values)
        for layer in AUTHORITY_LAYERS
    }
    if metric_override is not None:
        issues.extend(_validate_metric_override(metric_override, class_orders))
        if not issues:
            class_orders[metric_override.authority_layer] = _apply_partial_override(
                class_orders[metric_override.authority_layer],
                metric_override.ordered_classes,
            )

    if issues:
        raise FailureValidationError(issues)

    layer_index = {layer: index for index, layer in enumerate(AUTHORITY_LAYERS)}
    class_index = {
        layer: {class_id: index for index, class_id in enumerate(order)}
        for layer, order in class_orders.items()
    }
    ordered = tuple(
        sorted(
            candidate_values,
            key=lambda candidate: (
                layer_index[candidate.authority_layer],
                class_index[candidate.authority_layer][candidate.failure_class],
                _serialized_identifier_key(candidate.affected_evidence_id),
                _serialized_identifier_key(candidate.source_id),
                _serialized_identifier_key(candidate.candidate_id),
            ),
        )
    )
    primary = ordered[0]
    suppressed = ordered[1:]

    basis: dict[str, object] = {
        "mode": "default" if metric_override is None else "metric_override",
        "selected_authority_layer": primary.authority_layer,
        "selected_class_order": list(class_orders[primary.authority_layer]),
    }
    if metric_override is not None:
        basis["metric_rule"] = metric_override.to_dict()

    frozen_basis = _freeze_json_mapping(
        basis,
        field_name="precedence_basis",
        require_namespaced_keys=False,
        reject_secret_names=False,
    )
    payload = {
        "contract": {
            "id": FAILURE_TAXONOMY_CONTRACT_ID,
            "version": FAILURE_TAXONOMY_CONTRACT_VERSION,
        },
        "primary": primary.to_dict(),
        "candidates": [candidate.to_dict() for candidate in ordered],
        "suppressed": [candidate.to_dict() for candidate in suppressed],
        "precedence_basis": _thaw_json(frozen_basis),
    }
    return FailureResolution(
        primary=primary,
        candidates=ordered,
        suppressed=suppressed,
        precedence_basis=frozen_basis,
        resolution_sha256=_canonical_sha256(payload),
    )


def _extension_index(
    registrations: tuple[ExtensionFailureClassRegistration, ...],
) -> tuple[
    dict[str, ExtensionFailureClassRegistration],
    tuple[CandidateValidationIssue, ...],
]:
    by_id: dict[str, ExtensionFailureClassRegistration] = {}
    issues: list[CandidateValidationIssue] = []
    for registration in registrations:
        if registration.class_id in by_id:
            issues.append(
                CandidateValidationIssue(
                    "FAILURE_EXTENSION_CLASS_AMBIGUOUS",
                    registration.class_id,
                    "extension_classes",
                    "extension class registration is duplicated",
                )
            )
        else:
            by_id[registration.class_id] = registration
    return by_id, tuple(issues)


def _validate_candidates(
    candidates: tuple[FailureCandidate, ...],
    extension_by_id: Mapping[str, ExtensionFailureClassRegistration],
) -> tuple[CandidateValidationIssue, ...]:
    issues: list[CandidateValidationIssue] = []
    if not candidates:
        return (
            CandidateValidationIssue(
                "FAILURE_CANDIDATES_EMPTY",
                "<set>",
                "candidates",
                "at least one failure candidate is required",
            ),
        )

    seen_ids: set[str] = set()
    for candidate in candidates:
        if candidate.candidate_id in seen_ids:
            issues.append(
                CandidateValidationIssue(
                    "FAILURE_CANDIDATE_ID_AMBIGUOUS",
                    candidate.candidate_id,
                    "candidate_id",
                    "candidate_id is duplicated",
                )
            )
        seen_ids.add(candidate.candidate_id)

        canonical_layer = _CANONICAL_CLASS_LAYER.get(candidate.failure_class)
        if canonical_layer is not None:
            if candidate.authority_layer != canonical_layer:
                issues.append(
                    CandidateValidationIssue(
                        "FAILURE_CLASS_LAYER_MISMATCH",
                        candidate.candidate_id,
                        "authority_layer",
                        "canonical class does not belong to the declared authority layer",
                    )
                )
            if candidate.class_version is not None:
                issues.append(
                    CandidateValidationIssue(
                        "FAILURE_CANONICAL_CLASS_VERSION_FORBIDDEN",
                        candidate.candidate_id,
                        "class_version",
                        "canonical classes are versioned by the failure-taxonomy contract",
                    )
                )
            continue

        registration = extension_by_id.get(candidate.failure_class)
        if registration is None:
            issues.append(
                CandidateValidationIssue(
                    "FAILURE_CLASS_UNKNOWN",
                    candidate.candidate_id,
                    "failure_class",
                    "failure class is neither canonical nor registered",
                )
            )
            continue
        if candidate.authority_layer != registration.authority_layer:
            issues.append(
                CandidateValidationIssue(
                    "FAILURE_EXTENSION_LAYER_MISMATCH",
                    candidate.candidate_id,
                    "authority_layer",
                    "extension class does not belong to the declared authority layer",
                )
            )
        if candidate.class_version != registration.version:
            issues.append(
                CandidateValidationIssue(
                    "FAILURE_EXTENSION_VERSION_MISMATCH",
                    candidate.candidate_id,
                    "class_version",
                    "extension class version does not match its registration",
                )
            )
    return tuple(issues)


def _validate_metric_override(
    override: MetricPrecedenceOverride,
    class_orders: Mapping[str, tuple[str, ...]],
) -> tuple[CandidateValidationIssue, ...]:
    allowed = set(class_orders[override.authority_layer])
    issues = []
    for class_id in override.ordered_classes:
        if class_id not in allowed:
            issues.append(
                CandidateValidationIssue(
                    "FAILURE_METRIC_OVERRIDE_CLASS_INVALID",
                    override.metric_registration_id,
                    "ordered_classes",
                    f"{class_id!r} is not registered in authority layer {override.authority_layer!r}",
                )
            )
    return tuple(issues)


def _layer_class_order(
    layer: str,
    registrations: tuple[ExtensionFailureClassRegistration, ...],
) -> tuple[str, ...]:
    before: dict[str, list[str]] = {}
    after: dict[str, list[str]] = {}
    for registration in registrations:
        if registration.authority_layer != layer:
            continue
        target = before if registration.position == "before" else after
        target.setdefault(registration.anchor_class, []).append(registration.class_id)

    ordered: list[str] = []
    for canonical in _CANONICAL_CLASS_PRECEDENCE[layer]:
        ordered.extend(sorted(before.get(canonical, ()), key=_serialized_identifier_key))
        ordered.append(canonical)
        ordered.extend(sorted(after.get(canonical, ()), key=_serialized_identifier_key))
    return tuple(ordered)


def _apply_partial_override(
    default_order: tuple[str, ...],
    ordered_classes: tuple[str, ...],
) -> tuple[str, ...]:
    positions = sorted(default_order.index(class_id) for class_id in ordered_classes)
    result = list(default_order)
    for position, class_id in zip(positions, ordered_classes):
        result[position] = class_id
    return tuple(result)


def _typed_tuple(values: Sequence[object], expected: type, field_name: str):
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    result = tuple(values)
    if any(type(value) is not expected for value in result):
        raise TypeError(f"{field_name} must contain only {expected.__name__} values")
    return result


def _freeze_json_mapping(
    value: Mapping[str, object],
    *,
    field_name: str,
    require_namespaced_keys: bool,
    reject_secret_names: bool = True,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    copied = _normalize_json(value, path=field_name)
    if reject_secret_names:
        _reject_secret_keys(copied, path=field_name)
    if require_namespaced_keys:
        for key in copied:
            _require_namespaced(key, f"{field_name} key")
    return _freeze_json(copied)


def _normalize_json(value: object, *, path: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string object key")
            normalized[key] = _normalize_json(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path} contains unsupported JSON value type {type(value).__name__}")


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _reject_secret_keys(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_secret_name(key, f"{path}.{key}")
            _reject_secret_keys(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_secret_keys(item, path=f"{path}[{index}]")


def _reject_secret_name(name: str, path: str) -> None:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if normalized in _FORBIDDEN_EXACT_NAMES or _FORBIDDEN_SUFFIX.search(normalized):
        raise ValueError(f"{path} is secret-bearing and cannot enter retained failure evidence")


def _require_nonempty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_semver(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an exact semantic version")
    return value


def _require_namespaced(value: object, field_name: str) -> str:
    text = _require_nonempty(value, field_name)
    if ":" not in text:
        raise ValueError(f"{field_name} must be namespaced")
    return text


def _serialized_identifier_key(value: str) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(rendered).hexdigest()


__all__ = [
    "AUTHORITY_LAYERS",
    "CANONICAL_CLASS_PRECEDENCE",
    "FAILURE_TAXONOMY_CONTRACT_ID",
    "FAILURE_TAXONOMY_CONTRACT_VERSION",
    "RUNNER_STATUS_FAILURE_CLASS",
    "CandidateValidationIssue",
    "ContractIdentity",
    "ExtensionFailureClassRegistration",
    "FailureCandidate",
    "FailureResolution",
    "FailureValidationError",
    "MetricPrecedenceOverride",
    "resolve_failures",
    "resolve_metric_failures",
    "runner_terminal_failure_class",
]
