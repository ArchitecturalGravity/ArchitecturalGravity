"""Shared benchmark-neutral telemetry evidence and calculations."""

from .model import (
    MEASUREMENT_KINDS,
    NONVALUE_STATES,
    RegisteredEfficiencyFormula,
    TelemetryCompanion,
    TelemetryCompatibility,
    TelemetryCompatibilityError,
    TelemetryError,
    TelemetryMeasurement,
    assert_poolable,
    derive_efficiency_ratio,
    estimate_cost,
    measure_bytes,
    measure_latency,
    record_measurement,
    record_unavailable_measurement,
)

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

from .consumption import (ATTEMPT_MEASUREMENTS, attempt_measurements, validate_attempt_measurements, aggregate_treatment_measurements, retained_run_measurements)
