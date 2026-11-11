"""Benchmark-neutral availability records and preservation helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Final


AVAILABILITY_STATES: Final[frozenset[str]] = frozenset(
    {
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
        "available",
    }
)
AFFECTED_KINDS: Final[frozenset[str]] = frozenset(
    {"evidence_role", "measurement"}
)
_SEMVER = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
)


@dataclass(frozen=True, slots=True)
class MetricAvailabilityEffect:
    """One registered metric rule's explicit downstream treatment of a state."""

    metric_registration_id: str
    metric_registration_version: str
    rule_id: str
    effect: str

    def __post_init__(self) -> None:
        _require_nonempty(
            self.metric_registration_id,
            "metric_registration_id",
        )
        _require_semver(
            self.metric_registration_version,
            "metric_registration_version",
        )
        _require_nonempty(self.rule_id, "rule_id")
        _require_nonempty(self.effect, "effect")

    @property
    def identity(self) -> tuple[str, str, str]:
        return (
            self.metric_registration_id,
            self.metric_registration_version,
            self.rule_id,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "metric_registration_id": self.metric_registration_id,
            "metric_registration_version": self.metric_registration_version,
            "rule_id": self.rule_id,
            "effect": self.effect,
        }


@dataclass(frozen=True, slots=True)
class AvailabilityRecord:
    """Explicit availability state for one evidence role or measurement.

    This record intentionally carries no numeric or byte payload. Consumers must
    use the referenced source evidence for values, preventing an absent state
    from being represented as successful empty evidence or an inferred zero.
    """

    affected_kind: str
    affected: str
    state: str
    reason: str
    source_identity: str
    downstream_effects: tuple[MetricAvailabilityEffect, ...] = ()
    exclusion_authority: str | None = None

    def __post_init__(self) -> None:
        if self.affected_kind not in AFFECTED_KINDS:
            raise ValueError(
                "affected_kind must be 'evidence_role' or 'measurement'"
            )
        _require_nonempty(self.affected, "affected")
        if self.state not in AVAILABILITY_STATES:
            raise ValueError(
                f"unknown shared availability state {self.state!r}"
            )
        _require_nonempty(self.reason, "reason")
        _require_nonempty(self.source_identity, "source_identity")

        if not isinstance(self.downstream_effects, tuple) or any(
            type(value) is not MetricAvailabilityEffect
            for value in self.downstream_effects
        ):
            raise TypeError(
                "downstream_effects must be a tuple of "
                "MetricAvailabilityEffect values"
            )
        effect_ids = tuple(
            value.identity for value in self.downstream_effects
        )
        if len(set(effect_ids)) != len(effect_ids):
            raise ValueError(
                "downstream_effects must not contain duplicate metric rules"
            )

        if self.state == "excluded":
            if self.exclusion_authority is None:
                raise ValueError(
                    "excluded availability requires exclusion_authority "
                    "identifying the rule or process"
                )
            _require_nonempty(
                self.exclusion_authority,
                "exclusion_authority",
            )
        elif self.exclusion_authority is not None:
            raise ValueError(
                "exclusion_authority is permitted only when state is "
                "'excluded'"
            )

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "affected_kind": self.affected_kind,
            "affected": self.affected,
            "state": self.state,
            "reason": self.reason,
            "source_identity": self.source_identity,
            "downstream_effects": [
                effect.to_dict() for effect in self.downstream_effects
            ],
        }
        if self.exclusion_authority is not None:
            value["exclusion_authority"] = self.exclusion_authority
        return value


def preserve_availability(
    record: AvailabilityRecord,
    *,
    affected_kind: str | None = None,
    affected: str | None = None,
    downstream_effects: tuple[MetricAvailabilityEffect, ...] | None = None,
) -> AvailabilityRecord:
    """Project availability downstream without changing state or provenance."""

    if type(record) is not AvailabilityRecord:
        raise TypeError("record must be AvailabilityRecord")
    return replace(
        record,
        affected_kind=(
            record.affected_kind
            if affected_kind is None
            else affected_kind
        ),
        affected=record.affected if affected is None else affected,
        downstream_effects=(
            record.downstream_effects
            if downstream_effects is None
            else downstream_effects
        ),
    )


def bind_metric_effect(
    record: AvailabilityRecord,
    effect: MetricAvailabilityEffect,
) -> AvailabilityRecord:
    """Attach one registered metric rule without changing availability."""

    if type(record) is not AvailabilityRecord:
        raise TypeError("record must be AvailabilityRecord")
    if type(effect) is not MetricAvailabilityEffect:
        raise TypeError("effect must be MetricAvailabilityEffect")
    return preserve_availability(
        record,
        downstream_effects=record.downstream_effects + (effect,),
    )


def _require_nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_semver(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a semantic version")


__all__ = [
    "AFFECTED_KINDS",
    "AVAILABILITY_STATES",
    "AvailabilityRecord",
    "MetricAvailabilityEffect",
    "bind_metric_effect",
    "preserve_availability",
]
