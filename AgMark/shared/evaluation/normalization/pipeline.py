"""Explicit registered normalization over retained bytes.

This module owns only benchmark-neutral transform registration, deterministic
application order, reconstructable trace evidence, and fail-closed execution.
It never performs implicit cleanup or falls back to raw bytes after failure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import re
from typing import Final

from ...runtime.identity import canonical_json_bytes, canonical_sha256, sha256_bytes
from ..availability import AvailabilityRecord


_SEMVER: Final[re.Pattern[str]] = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
)
NormalizerImplementation = Callable[[bytes, object], bytes]


class NormalizationError(ValueError):
    """Base error for invalid normalization authority or execution."""


class NormalizerRegistrationError(NormalizationError):
    """Raised when normalizer registration authority is invalid."""


@dataclass(frozen=True, slots=True)
class NormalizerRegistration:
    """Immutable transform registration with canonical configuration identity."""

    transform_id: str
    transform_version: str
    configuration_json: bytes
    configuration_sha256: str

    def __post_init__(self) -> None:
        _require_nonempty(self.transform_id, "transform_id")
        _require_semver(self.transform_version, "transform_version")
        if type(self.configuration_json) is not bytes:
            raise TypeError("configuration_json must be bytes")
        try:
            decoded = json.loads(self.configuration_json.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NormalizerRegistrationError(
                "configuration_json must contain valid UTF-8 JSON"
            ) from exc
        canonical = canonical_json_bytes(decoded)
        if canonical != self.configuration_json:
            raise NormalizerRegistrationError(
                "configuration_json must use arcgrav.canonical-json.v1"
            )
        expected = sha256_bytes(canonical)
        if self.configuration_sha256 != expected:
            raise NormalizerRegistrationError(
                "configuration_sha256 does not match configuration_json"
            )

    @classmethod
    def create(
        cls,
        transform_id: str,
        transform_version: str,
        configuration: object,
    ) -> "NormalizerRegistration":
        """Create a registration from JSON-compatible configuration."""

        canonical = canonical_json_bytes(configuration)
        return cls(
            transform_id=transform_id,
            transform_version=transform_version,
            configuration_json=canonical,
            configuration_sha256=sha256_bytes(canonical),
        )

    @property
    def identity(self) -> str:
        """Return the exact comparison-facing normalization identity."""

        return (
            f"{self.transform_id}@{self.transform_version}:"
            f"{self.configuration_sha256}"
        )

    def configuration(self) -> object:
        """Return a fresh decoded configuration value for transform execution."""

        return json.loads(self.configuration_json.decode("utf-8"))

    def to_dict(self) -> dict[str, str]:
        return {
            "transform_id": self.transform_id,
            "transform_version": self.transform_version,
            "configuration_sha256": self.configuration_sha256,
            "identity": self.identity,
        }


class NormalizerRegistry:
    """Explicit identity/version registry for deterministic byte transforms."""

    def __init__(self) -> None:
        self._implementations: dict[tuple[str, str], NormalizerImplementation] = {}

    def register(
        self,
        transform_id: str,
        transform_version: str,
        implementation: NormalizerImplementation,
    ) -> None:
        _require_nonempty(transform_id, "transform_id")
        _require_semver(transform_version, "transform_version")
        if not callable(implementation):
            raise TypeError("implementation must be callable")
        key = (transform_id, transform_version)
        if key in self._implementations:
            raise NormalizerRegistrationError(
                f"normalizer {transform_id}@{transform_version} is already registered"
            )
        self._implementations[key] = implementation

    def resolve(
        self,
        registration: NormalizerRegistration,
    ) -> NormalizerImplementation | None:
        if type(registration) is not NormalizerRegistration:
            raise TypeError("registration must be NormalizerRegistration")
        return self._implementations.get(
            (registration.transform_id, registration.transform_version)
        )


@dataclass(frozen=True, slots=True)
class NormalizationStepEvidence:
    """Reconstructable trace for one declared normalization step."""

    order: int
    transform_id: str
    transform_version: str
    configuration_sha256: str
    normalization_identity: str
    input_sha256: str
    output_sha256: str | None
    computation_sha256: str
    availability: AvailabilityRecord
    failure_code: str | None = None
    failure_detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.order, int) or isinstance(self.order, bool) or self.order < 0:
            raise ValueError("order must be a non-negative integer")
        for field_name in (
            "transform_id",
            "transform_version",
            "configuration_sha256",
            "normalization_identity",
            "input_sha256",
            "computation_sha256",
        ):
            _require_nonempty(getattr(self, field_name), field_name)
        _require_semver(self.transform_version, "transform_version")
        if type(self.availability) is not AvailabilityRecord:
            raise TypeError("availability must be AvailabilityRecord")
        if self.availability.affected_kind != "measurement":
            raise ValueError("step availability must describe a measurement")
        if self.availability.source_identity != self.computation_sha256:
            raise ValueError(
                "step availability source_identity must equal computation_sha256"
            )
        failed = self.failure_code is not None
        if failed:
            _require_nonempty(self.failure_code, "failure_code")
            _require_nonempty(self.failure_detail, "failure_detail")
            if self.output_sha256 is not None:
                raise ValueError("failed normalization step cannot have output_sha256")
            if self.availability.state != "failed":
                raise ValueError("failed normalization step must be unavailable as failed")
        else:
            if self.failure_detail is not None:
                raise ValueError("failure_detail requires failure_code")
            _require_nonempty(self.output_sha256, "output_sha256")
            if self.availability.state != "available":
                raise ValueError("successful normalization step must be available")

    @property
    def succeeded(self) -> bool:
        return self.failure_code is None

    def to_dict(self) -> dict[str, object]:
        return {
            "order": self.order,
            "transform_id": self.transform_id,
            "transform_version": self.transform_version,
            "configuration_sha256": self.configuration_sha256,
            "normalization_identity": self.normalization_identity,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "computation_sha256": self.computation_sha256,
            "availability": self.availability.to_dict(),
            "failure_code": self.failure_code,
            "failure_detail": self.failure_detail,
        }


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Normalization output plus explicit success/failure trace authority."""

    source_identity: str
    measurement_identity: str
    input_sha256: str
    output_sha256: str | None
    output_bytes: bytes | None
    declared_normalization_identities: tuple[str, ...]
    steps: tuple[NormalizationStepEvidence, ...]
    computation_sha256: str
    availability: AvailabilityRecord

    def __post_init__(self) -> None:
        _require_nonempty(self.source_identity, "source_identity")
        _require_nonempty(self.measurement_identity, "measurement_identity")
        _require_nonempty(self.input_sha256, "input_sha256")
        _require_nonempty(self.computation_sha256, "computation_sha256")
        if not self.declared_normalization_identities:
            raise ValueError("normalization requires at least one declared transform")
        if any(
            not isinstance(identity, str) or not identity.strip()
            for identity in self.declared_normalization_identities
        ):
            raise ValueError(
                "declared_normalization_identities must contain non-empty strings"
            )
        if not self.steps:
            raise ValueError("normalization result must retain at least one step")
        if any(type(step) is not NormalizationStepEvidence for step in self.steps):
            raise TypeError("steps must contain NormalizationStepEvidence values")
        if tuple(step.order for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("normalization step order must be contiguous from zero")
        if type(self.availability) is not AvailabilityRecord:
            raise TypeError("availability must be AvailabilityRecord")
        if self.availability.affected_kind != "measurement":
            raise ValueError("normalization availability must describe a measurement")
        if self.availability.affected != self.measurement_identity:
            raise ValueError(
                "normalization availability affected value must equal measurement_identity"
            )
        if self.availability.source_identity != self.computation_sha256:
            raise ValueError(
                "normalization availability source_identity must equal computation_sha256"
            )

        failed = any(not step.succeeded for step in self.steps)
        if failed:
            if self.output_bytes is not None or self.output_sha256 is not None:
                raise ValueError("failed normalization cannot expose comparison bytes")
            if self.availability.state != "failed":
                raise ValueError("failed normalization must retain failed availability")
        else:
            if len(self.steps) != len(self.declared_normalization_identities):
                raise ValueError(
                    "successful normalization must execute every declared transform"
                )
            if type(self.output_bytes) is not bytes:
                raise TypeError("successful normalization output_bytes must be bytes")
            expected = sha256_bytes(self.output_bytes)
            if self.output_sha256 != expected:
                raise ValueError("output_sha256 does not match output_bytes")
            if self.availability.state != "available":
                raise ValueError("successful normalization must be available")

    @property
    def succeeded(self) -> bool:
        return self.output_bytes is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "source_identity": self.source_identity,
            "measurement_identity": self.measurement_identity,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "declared_normalization_identities": list(
                self.declared_normalization_identities
            ),
            "steps": [step.to_dict() for step in self.steps],
            "computation_sha256": self.computation_sha256,
            "availability": self.availability.to_dict(),
        }


def normalize_bytes(
    input_bytes: bytes,
    *,
    source_identity: str,
    measurement_identity: str,
    registrations: tuple[NormalizerRegistration, ...],
    registry: NormalizerRegistry,
) -> NormalizationResult:
    """Apply every declared transform in order or fail without raw fallback."""

    if type(input_bytes) is not bytes:
        raise TypeError("input_bytes must be bytes")
    _require_nonempty(source_identity, "source_identity")
    _require_nonempty(measurement_identity, "measurement_identity")
    if (
        not isinstance(registrations, tuple)
        or not registrations
        or any(type(item) is not NormalizerRegistration for item in registrations)
    ):
        raise NormalizerRegistrationError(
            "registrations must be a non-empty tuple of NormalizerRegistration values"
        )
    if type(registry) is not NormalizerRegistry:
        raise TypeError("registry must be NormalizerRegistry")

    identities = tuple(item.identity for item in registrations)
    if len(set(identities)) != len(identities):
        raise NormalizerRegistrationError(
            "normalization pipeline must not contain duplicate registrations"
        )

    original_input_sha256 = sha256_bytes(input_bytes)
    current = input_bytes
    steps: list[NormalizationStepEvidence] = []

    for order, registration in enumerate(registrations):
        step_input_sha256 = sha256_bytes(current)
        implementation = registry.resolve(registration)
        if implementation is None:
            step = _failed_step(
                order=order,
                registration=registration,
                input_sha256=step_input_sha256,
                measurement_identity=measurement_identity,
                failure_code="NORMALIZER_NOT_REGISTERED",
                failure_detail=(
                    f"no implementation registered for "
                    f"{registration.transform_id}@{registration.transform_version}"
                ),
            )
            steps.append(step)
            return _result(
                source_identity=source_identity,
                measurement_identity=measurement_identity,
                input_sha256=original_input_sha256,
                output_bytes=None,
                identities=identities,
                steps=tuple(steps),
            )

        try:
            transformed = implementation(current, registration.configuration())
        except Exception as exc:
            step = _failed_step(
                order=order,
                registration=registration,
                input_sha256=step_input_sha256,
                measurement_identity=measurement_identity,
                failure_code="NORMALIZER_EXECUTION_FAILED",
                failure_detail=f"{type(exc).__name__}: {exc}",
            )
            steps.append(step)
            return _result(
                source_identity=source_identity,
                measurement_identity=measurement_identity,
                input_sha256=original_input_sha256,
                output_bytes=None,
                identities=identities,
                steps=tuple(steps),
            )

        if type(transformed) is not bytes:
            step = _failed_step(
                order=order,
                registration=registration,
                input_sha256=step_input_sha256,
                measurement_identity=measurement_identity,
                failure_code="NORMALIZER_INVALID_OUTPUT",
                failure_detail="normalizer implementation must return bytes",
            )
            steps.append(step)
            return _result(
                source_identity=source_identity,
                measurement_identity=measurement_identity,
                input_sha256=original_input_sha256,
                output_bytes=None,
                identities=identities,
                steps=tuple(steps),
            )

        step = _successful_step(
            order=order,
            registration=registration,
            input_sha256=step_input_sha256,
            output_sha256=sha256_bytes(transformed),
            measurement_identity=measurement_identity,
        )
        steps.append(step)
        current = transformed

    return _result(
        source_identity=source_identity,
        measurement_identity=measurement_identity,
        input_sha256=original_input_sha256,
        output_bytes=current,
        identities=identities,
        steps=tuple(steps),
    )


def _successful_step(
    *,
    order: int,
    registration: NormalizerRegistration,
    input_sha256: str,
    output_sha256: str,
    measurement_identity: str,
) -> NormalizationStepEvidence:
    payload = _step_payload(
        order=order,
        registration=registration,
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        failure_code=None,
        failure_detail=None,
    )
    computation_sha256 = canonical_sha256(payload)
    return NormalizationStepEvidence(
        order=order,
        transform_id=registration.transform_id,
        transform_version=registration.transform_version,
        configuration_sha256=registration.configuration_sha256,
        normalization_identity=registration.identity,
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        computation_sha256=computation_sha256,
        availability=AvailabilityRecord(
            affected_kind="measurement",
            affected=f"{measurement_identity}:normalization:{order}",
            state="available",
            reason="registered normalization transform completed",
            source_identity=computation_sha256,
        ),
    )


def _failed_step(
    *,
    order: int,
    registration: NormalizerRegistration,
    input_sha256: str,
    measurement_identity: str,
    failure_code: str,
    failure_detail: str,
) -> NormalizationStepEvidence:
    payload = _step_payload(
        order=order,
        registration=registration,
        input_sha256=input_sha256,
        output_sha256=None,
        failure_code=failure_code,
        failure_detail=failure_detail,
    )
    computation_sha256 = canonical_sha256(payload)
    return NormalizationStepEvidence(
        order=order,
        transform_id=registration.transform_id,
        transform_version=registration.transform_version,
        configuration_sha256=registration.configuration_sha256,
        normalization_identity=registration.identity,
        input_sha256=input_sha256,
        output_sha256=None,
        computation_sha256=computation_sha256,
        availability=AvailabilityRecord(
            affected_kind="measurement",
            affected=f"{measurement_identity}:normalization:{order}",
            state="failed",
            reason=failure_code,
            source_identity=computation_sha256,
        ),
        failure_code=failure_code,
        failure_detail=failure_detail,
    )


def _step_payload(
    *,
    order: int,
    registration: NormalizerRegistration,
    input_sha256: str,
    output_sha256: str | None,
    failure_code: str | None,
    failure_detail: str | None,
) -> dict[str, object]:
    return {
        "order": order,
        "transform_id": registration.transform_id,
        "transform_version": registration.transform_version,
        "configuration_sha256": registration.configuration_sha256,
        "normalization_identity": registration.identity,
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "failure_code": failure_code,
        "failure_detail": failure_detail,
    }


def _result(
    *,
    source_identity: str,
    measurement_identity: str,
    input_sha256: str,
    output_bytes: bytes | None,
    identities: tuple[str, ...],
    steps: tuple[NormalizationStepEvidence, ...],
) -> NormalizationResult:
    output_sha256 = None if output_bytes is None else sha256_bytes(output_bytes)
    payload = {
        "source_identity": source_identity,
        "measurement_identity": measurement_identity,
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "declared_normalization_identities": list(identities),
        "steps": [step.to_dict() for step in steps],
    }
    computation_sha256 = canonical_sha256(payload)
    failed = output_bytes is None
    availability = AvailabilityRecord(
        affected_kind="measurement",
        affected=measurement_identity,
        state="failed" if failed else "available",
        reason=(
            "registered normalization failed closed"
            if failed
            else "registered normalization completed"
        ),
        source_identity=computation_sha256,
    )
    return NormalizationResult(
        source_identity=source_identity,
        measurement_identity=measurement_identity,
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        output_bytes=output_bytes,
        declared_normalization_identities=identities,
        steps=steps,
        computation_sha256=computation_sha256,
        availability=availability,
    )


def _require_nonempty(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_semver(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a semantic version")


__all__ = [
    "NormalizationError",
    "NormalizationResult",
    "NormalizationStepEvidence",
    "NormalizerImplementation",
    "NormalizerRegistration",
    "NormalizerRegistrationError",
    "NormalizerRegistry",
    "normalize_bytes",
]
