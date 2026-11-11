"""Benchmark-neutral telemetry measurement and derivation evidence.

This module keeps observed values, unavailable values, provider-reported values,
offline estimates, cost calculations, latency boundaries, and derived efficiency
evidence structurally explicit. It never imputes missing numeric telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Final, Iterable

from ...runtime.identity import canonical_sha256, sha256_bytes
from ..availability import AvailabilityRecord


MEASUREMENT_KINDS: Final[frozenset[str]] = frozenset(
    {
        "runner_measured_bytes",
        "provider_reported_usage",
        "offline_token_estimate",
        "provider_reported_cost",
        "estimated_cost",
        "latency",
        "efficiency",
        "generic_numeric",
    }
)
NONVALUE_STATES: Final[frozenset[str]] = frozenset(
    {
        "not_produced",
        "unavailable",
        "invalid",
        "excluded",
        "missing",
        "failed",
        "completed_non_scorable",
        "not_applicable",
        "non_comparable",
    }
)
_SEMVER: Final[re.Pattern[str]] = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
)


class TelemetryError(ValueError):
    """Base error for invalid telemetry authority or evidence."""


class TelemetryCompatibilityError(TelemetryError):
    """Raised when measurements cannot be compared or pooled safely."""


@dataclass(frozen=True, slots=True)
class TelemetryCompatibility:
    """Explicit identities that bound telemetry comparison authority.

    Every comparison dimension is required. Callers must supply an explicit
    registered identity or an explicit not-applicable marker; missing ambient
    information is never treated as compatible merely because both sides omit it.
    """

    tokenizer_identity: str
    request_representation: str
    provider_framing: str
    timestamp_boundary: str
    usage_source: str
    pricing_source: str
    currency: str
    runner_identity: str
    model_identity: str
    execution_boundary_identity: str
    registered_scope: str

    def __post_init__(self) -> None:
        for field_name in (
            "tokenizer_identity",
            "request_representation",
            "provider_framing",
            "timestamp_boundary",
            "usage_source",
            "pricing_source",
            "currency",
            "runner_identity",
            "model_identity",
            "execution_boundary_identity",
            "registered_scope",
        ):
            _require_nonempty(getattr(self, field_name), field_name)

    @property
    def identity(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, str]:
        return {
            "tokenizer_identity": self.tokenizer_identity,
            "request_representation": self.request_representation,
            "provider_framing": self.provider_framing,
            "timestamp_boundary": self.timestamp_boundary,
            "usage_source": self.usage_source,
            "pricing_source": self.pricing_source,
            "currency": self.currency,
            "runner_identity": self.runner_identity,
            "model_identity": self.model_identity,
            "execution_boundary_identity": self.execution_boundary_identity,
            "registered_scope": self.registered_scope,
        }


@dataclass(frozen=True, slots=True)
class TelemetryCompanion:
    """One retained companion value needed to reconstruct a derivation."""

    name: str
    value: int | float
    unit: str
    source_identity: str

    def __post_init__(self) -> None:
        _require_nonempty(self.name, "name")
        _require_number(self.value, "value")
        _require_nonempty(self.unit, "unit")
        _require_nonempty(self.source_identity, "source_identity")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True, slots=True)
class RegisteredEfficiencyFormula:
    """Validated registered formula authority supplied by the caller."""

    registration_identity: str
    formula_id: str
    formula_version: str
    numerator_role: str
    denominator_role: str
    output_unit: str

    def __post_init__(self) -> None:
        _require_nonempty(self.registration_identity, "registration_identity")
        _require_nonempty(self.formula_id, "formula_id")
        _require_semver(self.formula_version, "formula_version")
        _require_nonempty(self.numerator_role, "numerator_role")
        _require_nonempty(self.denominator_role, "denominator_role")
        _require_nonempty(self.output_unit, "output_unit")

    @property
    def identity(self) -> str:
        return (
            f"{self.formula_id}@{self.formula_version}:"
            f"{self.registration_identity}"
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "registration_identity": self.registration_identity,
            "formula_id": self.formula_id,
            "formula_version": self.formula_version,
            "numerator_role": self.numerator_role,
            "denominator_role": self.denominator_role,
            "output_unit": self.output_unit,
            "identity": self.identity,
        }


@dataclass(frozen=True, slots=True)
class TelemetryMeasurement:
    """Reconstructable numeric telemetry evidence.

    A non-available measurement always carries value=None. A numeric zero is
    therefore representable only as an explicitly available observed or derived
    value rather than as a missing-data sentinel.
    """

    measurement_identity: str
    measurement_kind: str
    value: int | float | None
    unit: str
    source: str
    method: str
    observation_scope: str
    compatibility_group: str
    compatibility: TelemetryCompatibility
    availability: AvailabilityRecord
    evidence_references: tuple[str, ...]
    companions: tuple[TelemetryCompanion, ...]
    method_details: tuple[tuple[str, str], ...]
    comparison_context: str | None
    computation_sha256: str

    def __post_init__(self) -> None:
        _require_nonempty(self.measurement_identity, "measurement_identity")
        if self.measurement_kind not in MEASUREMENT_KINDS:
            raise TelemetryError(
                f"unknown telemetry measurement_kind {self.measurement_kind!r}"
            )
        _require_nonempty(self.unit, "unit")
        _require_nonempty(self.source, "source")
        _require_nonempty(self.method, "method")
        _require_nonempty(self.observation_scope, "observation_scope")
        _require_nonempty(self.compatibility_group, "compatibility_group")
        if type(self.compatibility) is not TelemetryCompatibility:
            raise TypeError("compatibility must be TelemetryCompatibility")
        if type(self.availability) is not AvailabilityRecord:
            raise TypeError("availability must be AvailabilityRecord")
        if self.availability.affected_kind != "measurement":
            raise TelemetryError(
                "telemetry availability must describe a measurement"
            )
        if self.availability.affected != self.measurement_identity:
            raise TelemetryError(
                "availability affected identity must equal measurement_identity"
            )
        if self.availability.source_identity != self.computation_sha256:
            raise TelemetryError(
                "availability source_identity must equal computation_sha256"
            )

        if self.availability.state == "available":
            if self.value is None:
                raise TelemetryError(
                    "available telemetry requires an explicit numeric value"
                )
            _require_number(self.value, "value")
        else:
            if self.value is not None:
                raise TelemetryError(
                    "non-available telemetry must retain value=None"
                )

        _require_string_tuple(
            self.evidence_references,
            "evidence_references",
            allow_empty=False,
        )
        if len(set(self.evidence_references)) != len(self.evidence_references):
            raise TelemetryError(
                "evidence_references must not contain duplicate identities"
            )

        if not isinstance(self.companions, tuple) or any(
            type(value) is not TelemetryCompanion
            for value in self.companions
        ):
            raise TypeError(
                "companions must be a tuple of TelemetryCompanion values"
            )
        companion_names = tuple(value.name for value in self.companions)
        if len(set(companion_names)) != len(companion_names):
            raise TelemetryError("companion names must be unique")

        _require_method_details(self.method_details)
        if self.comparison_context is not None:
            _require_nonempty(self.comparison_context, "comparison_context")
        _require_nonempty(self.computation_sha256, "computation_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "measurement_identity": self.measurement_identity,
            "measurement_kind": self.measurement_kind,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "method": self.method,
            "observation_scope": self.observation_scope,
            "compatibility_group": self.compatibility_group,
            "compatibility": self.compatibility.to_dict(),
            "availability": self.availability.to_dict(),
            "evidence_references": list(self.evidence_references),
            "companions": [value.to_dict() for value in self.companions],
            "method_details": {
                key: value for key, value in self.method_details
            },
            "comparison_context": self.comparison_context,
            "computation_sha256": self.computation_sha256,
        }


def record_measurement(
    *,
    measurement_identity: str,
    measurement_kind: str,
    value: int | float,
    unit: str,
    source: str,
    method: str,
    observation_scope: str,
    compatibility_group: str,
    compatibility: TelemetryCompatibility,
    reason: str,
    evidence_references: tuple[str, ...],
    companions: tuple[TelemetryCompanion, ...] = (),
    method_details: tuple[tuple[str, str], ...] = (),
    comparison_context: str | None = None,
) -> TelemetryMeasurement:
    """Record one explicit available numeric telemetry value."""

    _require_number(value, "value")
    return _build_measurement(
        measurement_identity=measurement_identity,
        measurement_kind=measurement_kind,
        value=value,
        unit=unit,
        source=source,
        method=method,
        observation_scope=observation_scope,
        compatibility_group=compatibility_group,
        compatibility=compatibility,
        availability_state="available",
        reason=reason,
        evidence_references=evidence_references,
        companions=companions,
        method_details=method_details,
        comparison_context=comparison_context,
        exclusion_authority=None,
    )


def record_unavailable_measurement(
    *,
    measurement_identity: str,
    measurement_kind: str,
    unit: str,
    source: str,
    method: str,
    observation_scope: str,
    compatibility_group: str,
    compatibility: TelemetryCompatibility,
    availability_state: str,
    reason: str,
    evidence_references: tuple[str, ...],
    method_details: tuple[tuple[str, str], ...] = (),
    comparison_context: str | None = None,
    exclusion_authority: str | None = None,
) -> TelemetryMeasurement:
    """Record explicit absent/non-comparable telemetry without zero imputation."""

    if availability_state == "available":
        raise TelemetryError(
            "record_unavailable_measurement cannot create available evidence"
        )
    if availability_state not in NONVALUE_STATES:
        raise TelemetryError(
            "telemetry absent state must be an explicit non-value state"
        )
    return _build_measurement(
        measurement_identity=measurement_identity,
        measurement_kind=measurement_kind,
        value=None,
        unit=unit,
        source=source,
        method=method,
        observation_scope=observation_scope,
        compatibility_group=compatibility_group,
        compatibility=compatibility,
        availability_state=availability_state,
        reason=reason,
        evidence_references=evidence_references,
        companions=(),
        method_details=method_details,
        comparison_context=comparison_context,
        exclusion_authority=exclusion_authority,
    )


def measure_bytes(
    data: bytes,
    *,
    measurement_identity: str,
    source_identity: str,
    observation_scope: str,
    compatibility_group: str,
    compatibility: TelemetryCompatibility,
    comparison_context: str | None = None,
) -> TelemetryMeasurement:
    """Measure exact retained bytes without treating byte count as token usage."""

    if type(data) is not bytes:
        raise TypeError("data must be bytes")
    _require_nonempty(source_identity, "source_identity")
    byte_sha256 = sha256_bytes(data)
    return record_measurement(
        measurement_identity=measurement_identity,
        measurement_kind="runner_measured_bytes",
        value=len(data),
        unit="byte",
        source="runner_retained_bytes",
        method="exact_byte_count",
        observation_scope=observation_scope,
        compatibility_group=compatibility_group,
        compatibility=compatibility,
        reason="exact retained bytes measured",
        evidence_references=(
            (source_identity,)
            if source_identity == byte_sha256
            else (source_identity, byte_sha256)
        ),
        method_details=(("byte_sha256", byte_sha256),),
        comparison_context=comparison_context,
    )


def measure_latency(
    *,
    measurement_identity: str,
    start_ns: int,
    end_ns: int,
    start_boundary: str,
    end_boundary: str,
    clock_source: str,
    source_identity: str,
    observation_scope: str,
    compatibility_group: str,
    compatibility: TelemetryCompatibility,
    comparison_context: str | None = None,
) -> TelemetryMeasurement:
    """Measure latency from retained monotonic timestamps and explicit boundaries."""

    _require_nonnegative_int(start_ns, "start_ns")
    _require_nonnegative_int(end_ns, "end_ns")
    if end_ns < start_ns:
        raise TelemetryError("end_ns must not precede start_ns")
    _require_nonempty(start_boundary, "start_boundary")
    _require_nonempty(end_boundary, "end_boundary")
    _require_nonempty(clock_source, "clock_source")
    _require_nonempty(source_identity, "source_identity")
    timestamp_boundary = (
        f"{start_boundary}->{end_boundary}@{clock_source}"
    )
    if compatibility.timestamp_boundary != timestamp_boundary:
        raise TelemetryCompatibilityError(
            "compatibility timestamp_boundary must exactly match the retained "
            "latency start/end boundary and clock source"
        )
    return record_measurement(
        measurement_identity=measurement_identity,
        measurement_kind="latency",
        value=end_ns - start_ns,
        unit="nanosecond",
        source="retained_timestamps",
        method="end_minus_start",
        observation_scope=observation_scope,
        compatibility_group=compatibility_group,
        compatibility=compatibility,
        reason="latency calculated from retained timestamps",
        evidence_references=(source_identity,),
        method_details=(
            ("start_boundary", start_boundary),
            ("end_boundary", end_boundary),
            ("clock_source", clock_source),
            ("start_ns", str(start_ns)),
            ("end_ns", str(end_ns)),
        ),
        comparison_context=comparison_context,
    )


def estimate_cost(
    usage: TelemetryMeasurement,
    *,
    measurement_identity: str,
    price_per_unit: int | float,
    usage_units_per_price_unit: int | float,
    pricing_date: str,
    calculation_method: str,
    observation_scope: str,
    compatibility_group: str,
    compatibility: TelemetryCompatibility,
    comparison_context: str | None = None,
) -> TelemetryMeasurement:
    """Calculate explicit estimated cost from retained usage and pricing authority."""

    usage = _require_measurement(usage, "usage")
    if usage.availability.state != "available" or usage.value is None:
        raise TelemetryError(
            "estimated cost requires available retained usage evidence"
        )
    if usage.measurement_kind not in {
        "provider_reported_usage",
        "offline_token_estimate",
        "generic_numeric",
    }:
        raise TelemetryError(
            "estimated cost usage must be explicit usage or estimate evidence"
        )
    _require_number(price_per_unit, "price_per_unit")
    _require_number(usage_units_per_price_unit, "usage_units_per_price_unit")
    if price_per_unit < 0:
        raise TelemetryError("price_per_unit must be non-negative")
    if usage_units_per_price_unit <= 0:
        raise TelemetryError(
            "usage_units_per_price_unit must be greater than zero"
        )
    _require_nonempty(pricing_date, "pricing_date")
    _require_nonempty(calculation_method, "calculation_method")
    _require_context_match_except(
        usage.compatibility,
        compatibility,
        allowed_differences=frozenset({"pricing_source", "currency"}),
    )
    if usage.compatibility_group != compatibility_group:
        raise TelemetryCompatibilityError(
            "usage and estimated cost compatibility_group must match"
        )
    value = usage.value * price_per_unit / usage_units_per_price_unit
    return record_measurement(
        measurement_identity=measurement_identity,
        measurement_kind="estimated_cost",
        value=value,
        unit=compatibility.currency,
        source="registered_pricing_source",
        method=calculation_method,
        observation_scope=observation_scope,
        compatibility_group=compatibility_group,
        compatibility=compatibility,
        reason="cost estimated from retained usage and registered pricing",
        evidence_references=(
            usage.computation_sha256,
            compatibility.pricing_source,
        ),
        companions=(
            TelemetryCompanion(
                name="usage",
                value=usage.value,
                unit=usage.unit,
                source_identity=usage.computation_sha256,
            ),
            TelemetryCompanion(
                name="price_per_unit",
                value=price_per_unit,
                unit=compatibility.currency,
                source_identity=compatibility.pricing_source,
            ),
            TelemetryCompanion(
                name="usage_units_per_price_unit",
                value=usage_units_per_price_unit,
                unit=usage.unit,
                source_identity=compatibility.pricing_source,
            ),
        ),
        method_details=(
            ("pricing_date", pricing_date),
            ("pricing_source", compatibility.pricing_source),
            ("currency", compatibility.currency),
        ),
        comparison_context=comparison_context,
    )


def derive_efficiency_ratio(
    *,
    measurement_identity: str,
    numerator_value: int | float,
    numerator_unit: str,
    numerator_source_identity: str,
    denominator: TelemetryMeasurement,
    formula: RegisteredEfficiencyFormula,
    observation_scope: str,
    compatibility_group: str,
    compatibility: TelemetryCompatibility,
    comparison_context: str | None = None,
) -> TelemetryMeasurement:
    """Apply one registered ratio formula while retaining both companion values."""

    _require_number(numerator_value, "numerator_value")
    _require_nonempty(numerator_unit, "numerator_unit")
    _require_nonempty(numerator_source_identity, "numerator_source_identity")
    denominator = _require_measurement(denominator, "denominator")
    if type(formula) is not RegisteredEfficiencyFormula:
        raise TypeError("formula must be RegisteredEfficiencyFormula")
    if denominator.availability.state != "available" or denominator.value is None:
        raise TelemetryError(
            "efficiency denominator must be available retained evidence"
        )
    if denominator.value == 0:
        raise TelemetryError(
            "efficiency denominator must be non-zero; undefined ratios fail closed"
        )
    _require_context_match(denominator.compatibility, compatibility)
    if denominator.compatibility_group != compatibility_group:
        raise TelemetryCompatibilityError(
            "denominator and derived efficiency compatibility_group must match"
        )
    value = numerator_value / denominator.value
    return record_measurement(
        measurement_identity=measurement_identity,
        measurement_kind="efficiency",
        value=value,
        unit=formula.output_unit,
        source="registered_efficiency_formula",
        method=formula.identity,
        observation_scope=observation_scope,
        compatibility_group=compatibility_group,
        compatibility=compatibility,
        reason="registered efficiency ratio derived from retained companions",
        evidence_references=(
            numerator_source_identity,
            denominator.computation_sha256,
            formula.registration_identity,
        ),
        companions=(
            TelemetryCompanion(
                name=formula.numerator_role,
                value=numerator_value,
                unit=numerator_unit,
                source_identity=numerator_source_identity,
            ),
            TelemetryCompanion(
                name=formula.denominator_role,
                value=denominator.value,
                unit=denominator.unit,
                source_identity=denominator.computation_sha256,
            ),
        ),
        method_details=(("formula_identity", formula.identity),),
        comparison_context=comparison_context,
    )


def assert_poolable(
    measurements: Iterable[TelemetryMeasurement],
    *,
    comparison_context: str,
) -> str:
    """Fail closed unless measurements share complete comparison authority.

    Returns a deterministic comparison-context identity for downstream pooling.
    """

    _require_nonempty(comparison_context, "comparison_context")
    values = tuple(measurements)
    if not values:
        raise TelemetryCompatibilityError(
            "at least one measurement is required for pooling"
        )
    for index, value in enumerate(values):
        _require_measurement(value, f"measurements[{index}]")
        if value.availability.state != "available":
            raise TelemetryCompatibilityError(
                "non-available telemetry cannot enter numeric pooling"
            )
        if value.comparison_context != comparison_context:
            raise TelemetryCompatibilityError(
                "measurement comparison_context does not match pooling context"
            )

    first = values[0]
    for value in values[1:]:
        if value.measurement_kind != first.measurement_kind:
            raise TelemetryCompatibilityError(
                "different telemetry kinds cannot be pooled"
            )
        if value.unit != first.unit:
            raise TelemetryCompatibilityError(
                "different telemetry units cannot be pooled"
            )
        if value.source != first.source or value.method != first.method:
            raise TelemetryCompatibilityError(
                "different telemetry source/method provenance cannot be pooled"
            )
        if value.observation_scope != first.observation_scope:
            raise TelemetryCompatibilityError(
                "different observation scopes cannot be pooled"
            )
        if value.compatibility_group != first.compatibility_group:
            raise TelemetryCompatibilityError(
                "different compatibility groups cannot be pooled"
            )
        _require_context_match(first.compatibility, value.compatibility)

    return canonical_sha256(
        {
            "comparison_context": comparison_context,
            "measurement_kind": first.measurement_kind,
            "unit": first.unit,
            "observation_scope": first.observation_scope,
            "compatibility_group": first.compatibility_group,
            "compatibility": first.compatibility.to_dict(),
            "members": [
                value.computation_sha256 for value in values
            ],
        }
    )


def _build_measurement(
    *,
    measurement_identity: str,
    measurement_kind: str,
    value: int | float | None,
    unit: str,
    source: str,
    method: str,
    observation_scope: str,
    compatibility_group: str,
    compatibility: TelemetryCompatibility,
    availability_state: str,
    reason: str,
    evidence_references: tuple[str, ...],
    companions: tuple[TelemetryCompanion, ...],
    method_details: tuple[tuple[str, str], ...],
    comparison_context: str | None,
    exclusion_authority: str | None,
) -> TelemetryMeasurement:
    _require_nonempty(measurement_identity, "measurement_identity")
    if measurement_kind not in MEASUREMENT_KINDS:
        raise TelemetryError(
            f"unknown telemetry measurement_kind {measurement_kind!r}"
        )
    _require_nonempty(unit, "unit")
    _require_nonempty(source, "source")
    _require_nonempty(method, "method")
    _require_nonempty(observation_scope, "observation_scope")
    _require_nonempty(compatibility_group, "compatibility_group")
    if type(compatibility) is not TelemetryCompatibility:
        raise TypeError("compatibility must be TelemetryCompatibility")
    _require_nonempty(reason, "reason")
    _require_string_tuple(
        evidence_references,
        "evidence_references",
        allow_empty=False,
    )
    if not isinstance(companions, tuple) or any(
        type(value) is not TelemetryCompanion for value in companions
    ):
        raise TypeError(
            "companions must be a tuple of TelemetryCompanion values"
        )
    _require_method_details(method_details)
    if comparison_context is not None:
        _require_nonempty(comparison_context, "comparison_context")
    if exclusion_authority is not None:
        _require_nonempty(exclusion_authority, "exclusion_authority")
    if availability_state == "excluded" and exclusion_authority is None:
        raise TelemetryError(
            "excluded telemetry requires exclusion_authority"
        )
    if availability_state != "excluded" and exclusion_authority is not None:
        raise TelemetryError(
            "exclusion_authority is permitted only for excluded telemetry"
        )

    payload = {
        "measurement_identity": measurement_identity,
        "measurement_kind": measurement_kind,
        "value": value,
        "unit": unit,
        "source": source,
        "method": method,
        "observation_scope": observation_scope,
        "compatibility_group": compatibility_group,
        "compatibility": compatibility.to_dict(),
        "availability_state": availability_state,
        "availability_reason": reason,
        "evidence_references": list(evidence_references),
        "companions": [item.to_dict() for item in companions],
        "method_details": {
            key: detail for key, detail in method_details
        },
        "comparison_context": comparison_context,
        "exclusion_authority": exclusion_authority,
    }
    computation_sha256 = canonical_sha256(payload)
    availability = AvailabilityRecord(
        affected_kind="measurement",
        affected=measurement_identity,
        state=availability_state,
        reason=reason,
        source_identity=computation_sha256,
        exclusion_authority=exclusion_authority,
    )
    return TelemetryMeasurement(
        measurement_identity=measurement_identity,
        measurement_kind=measurement_kind,
        value=value,
        unit=unit,
        source=source,
        method=method,
        observation_scope=observation_scope,
        compatibility_group=compatibility_group,
        compatibility=compatibility,
        availability=availability,
        evidence_references=evidence_references,
        companions=companions,
        method_details=method_details,
        comparison_context=comparison_context,
        computation_sha256=computation_sha256,
    )


def _require_context_match(
    left: TelemetryCompatibility,
    right: TelemetryCompatibility,
) -> None:
    _require_context_match_except(
        left,
        right,
        allowed_differences=frozenset(),
    )


def _require_context_match_except(
    left: TelemetryCompatibility,
    right: TelemetryCompatibility,
    *,
    allowed_differences: frozenset[str],
) -> None:
    if type(left) is not TelemetryCompatibility:
        raise TypeError("left compatibility must be TelemetryCompatibility")
    if type(right) is not TelemetryCompatibility:
        raise TypeError("right compatibility must be TelemetryCompatibility")
    left_values = left.to_dict()
    right_values = right.to_dict()
    for field_name, left_value in left_values.items():
        if field_name in allowed_differences:
            continue
        if right_values[field_name] != left_value:
            raise TelemetryCompatibilityError(
                "telemetry compatibility identities do not match on "
                f"{field_name}"
            )


def _require_measurement(
    value: TelemetryMeasurement,
    field_name: str,
) -> TelemetryMeasurement:
    if type(value) is not TelemetryMeasurement:
        raise TypeError(f"{field_name} must be TelemetryMeasurement")
    return value


def _require_nonempty(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_semver(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a semantic version")


def _require_number(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be int or float")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")


def _require_nonnegative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_string_tuple(
    value: object,
    field_name: str,
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) or not item.strip()
        for item in value
    ):
        raise ValueError(
            f"{field_name} must be a tuple of non-empty strings"
        )
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")


def _require_method_details(value: object) -> None:
    if not isinstance(value, tuple):
        raise TypeError(
            "method_details must be a tuple of (key, value) string pairs"
        )
    keys: list[str] = []
    for item in value:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0].strip()
            or not isinstance(item[1], str)
            or not item[1].strip()
        ):
            raise ValueError(
                "method_details must contain non-empty string key/value pairs"
            )
        keys.append(item[0])
    if len(set(keys)) != len(keys):
        raise ValueError("method_details keys must be unique")


__all__ = [
    "MEASUREMENT_KINDS",
    "NONVALUE_STATES",
    "RegisteredEfficiencyFormula",
    "TelemetryCompanion",
    "TelemetryCompatibility",
    "TelemetryCompatibilityError",
    "TelemetryError",
    "TelemetryMeasurement",
    "assert_poolable",
    "derive_efficiency_ratio",
    "estimate_cost",
    "measure_bytes",
    "measure_latency",
    "record_measurement",
    "record_unavailable_measurement",
]
