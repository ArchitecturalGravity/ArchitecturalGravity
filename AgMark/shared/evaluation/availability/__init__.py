"""Shared benchmark-neutral availability semantics."""

from .model import (
    AFFECTED_KINDS,
    AVAILABILITY_STATES,
    AvailabilityRecord,
    MetricAvailabilityEffect,
    bind_metric_effect,
    preserve_availability,
)

__all__ = [
    "AFFECTED_KINDS",
    "AVAILABILITY_STATES",
    "AvailabilityRecord",
    "MetricAvailabilityEffect",
    "bind_metric_effect",
    "preserve_availability",
]
