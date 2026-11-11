"""Deterministic benchmark-neutral repetition, case, and paired aggregation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Final, Sequence


_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_VALUE_STATES: Final = frozenset({"scored", "available"})
_ACTIONS: Final = frozenset({"exclude", "unavailable", "non_comparable"})
_REDUCERS: Final = frozenset({"mean", "sum", "min", "max", "rate"})


class AggregationError(ValueError):
    """Raised when retained evidence cannot be combined under registered authority."""


@dataclass(frozen=True, slots=True)
class StateDisposition:
    state: str
    action: str

    def __post_init__(self) -> None:
        _text(self.state, "state")
        if self.state in _VALUE_STATES or self.action not in _ACTIONS:
            raise ValueError("invalid non-value state disposition")

    def to_dict(self) -> dict[str, str]:
        return {"state": self.state, "action": self.action}


@dataclass(frozen=True, slots=True)
class AggregationRule:
    rule_id: str
    rule_version: str
    reducer: str
    missing_action: str
    state_dispositions: tuple[StateDisposition, ...]
    implementation: str
    software_version: str

    def __post_init__(self) -> None:
        _text(self.rule_id, "rule_id")
        _semver(self.rule_version, "rule_version")
        if self.reducer not in _REDUCERS:
            raise ValueError("unsupported reducer")
        if self.missing_action not in _ACTIONS:
            raise ValueError("invalid missing_action")
        if not isinstance(self.state_dispositions, tuple) or any(
            type(v) is not StateDisposition for v in self.state_dispositions
        ):
            raise TypeError("state_dispositions must be StateDisposition values")
        states = [v.state for v in self.state_dispositions]
        if len(states) != len(set(states)):
            raise ValueError("state_dispositions must not duplicate states")
        _text(self.implementation, "implementation")
        _text(self.software_version, "software_version")

    @property
    def actions(self) -> dict[str, str]:
        return {v.state: v.action for v in self.state_dispositions}

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "reducer": self.reducer,
            "missing_action": self.missing_action,
            "state_dispositions": [v.to_dict() for v in self.state_dispositions],
            "implementation": self.implementation,
            "software_version": self.software_version,
        }


@dataclass(frozen=True, slots=True)
class AggregationInput:
    evidence_id: str
    case_id: str
    treatment_id: str
    repetition_id: str
    metric_id: str
    metric_version: str
    metric_registration_id: str
    metric_registration_version: str
    execution_boundary_fingerprint: str
    comparison_context_id: str
    observation_scope: str
    availability: str
    value: int | float | None
    failure_class: str | None = None
    exclusion_authority: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "evidence_id", "case_id", "treatment_id", "repetition_id",
            "metric_id", "metric_registration_id", "comparison_context_id",
            "observation_scope", "availability",
        ):
            _text(getattr(self, name), name)
        _semver(self.metric_version, "metric_version")
        _semver(self.metric_registration_version, "metric_registration_version")
        _sha(self.execution_boundary_fingerprint, "execution_boundary_fingerprint")
        if self.availability in _VALUE_STATES:
            _number(self.value, "value")
        elif self.value is not None:
            raise ValueError("non-value states cannot carry a numeric value")
        if self.availability == "failed" and self.failure_class is None:
            raise ValueError("failed input requires failure_class")
        if self.failure_class is not None:
            _text(self.failure_class, "failure_class")
        if self.availability == "excluded":
            _text(self.exclusion_authority, "exclusion_authority")
        elif self.exclusion_authority is not None:
            raise ValueError("exclusion_authority is valid only for excluded input")


@dataclass(frozen=True, slots=True)
class AggregateEvidence:
    level: str
    case_id: str | None
    treatment_id: str
    metric_id: str
    metric_version: str
    metric_registration_id: str
    metric_registration_version: str
    comparison_context_id: str
    observation_scope: str
    rule_id: str
    rule_version: str
    rule_reducer: str
    rule_missing_action: str
    rule_state_dispositions: tuple[tuple[str, str], ...]
    rule_implementation: str
    rule_software_version: str
    planned_unit_ids: tuple[str, ...]
    input_evidence_ids: tuple[str, ...]
    case_ids: tuple[str, ...]
    repetition_ids: tuple[str, ...]
    execution_boundary_fingerprints: tuple[str, ...]
    availability_counts: tuple[tuple[str, int], ...]
    exclusion_authorities: tuple[str, ...]
    failure_classes: tuple[str, ...]
    planned_count: int
    included_count: int
    missing_count: int
    excluded_count: int
    failed_count: int
    unavailable_count: int
    non_comparable_count: int
    retained_missing_count: int
    retained_exclusion_count: int
    retained_failure_count: int
    availability: str
    reason: str | None
    value: int | float | None
    numerator: int | float | None
    denominator: int | None
    computation_sha256: str

    @property
    def evidence_id(self) -> str:
        return self.computation_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "case_id": self.case_id,
            "treatment_id": self.treatment_id,
            "metric": {"id": self.metric_id, "version": self.metric_version},
            "metric_registration": {
                "id": self.metric_registration_id,
                "version": self.metric_registration_version,
            },
            "comparison_context_id": self.comparison_context_id,
            "observation_scope": self.observation_scope,
            "rule": {
                "id": self.rule_id,
                "version": self.rule_version,
                "reducer": self.rule_reducer,
                "missing_action": self.rule_missing_action,
                "state_dispositions": [
                    {"state": state, "action": action}
                    for state, action in self.rule_state_dispositions
                ],
                "implementation": self.rule_implementation,
                "software_version": self.rule_software_version,
            },
            "planned_unit_ids": list(self.planned_unit_ids),
            "input_evidence_ids": list(self.input_evidence_ids),
            "case_ids": list(self.case_ids),
            "repetition_ids": list(self.repetition_ids),
            "execution_boundary_fingerprints": list(self.execution_boundary_fingerprints),
            "availability_counts": [
                {"state": state, "count": count}
                for state, count in self.availability_counts
            ],
            "exclusion_authorities": list(self.exclusion_authorities),
            "failure_classes": list(self.failure_classes),
            "planned_count": self.planned_count,
            "included_count": self.included_count,
            "missing_count": self.missing_count,
            "excluded_count": self.excluded_count,
            "failed_count": self.failed_count,
            "unavailable_count": self.unavailable_count,
            "non_comparable_count": self.non_comparable_count,
            "retained_missing_count": self.retained_missing_count,
            "retained_exclusion_count": self.retained_exclusion_count,
            "retained_failure_count": self.retained_failure_count,
            "availability": self.availability,
            "reason": self.reason,
            "value": self.value,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "computation_sha256": self.computation_sha256,
        }


@dataclass(frozen=True, slots=True)
class CategoryDefinition:
    definition_id: str
    definition_version: str
    category_kind: str
    category_value: str
    case_ids: tuple[str, ...]
    preregistered: bool

    def __post_init__(self) -> None:
        _text(self.definition_id, "definition_id")
        _semver(self.definition_version, "definition_version")
        _text(self.category_kind, "category_kind")
        _text(self.category_value, "category_value")
        if not isinstance(self.case_ids, tuple):
            raise TypeError("case_ids must be a tuple")
        _planned(self.case_ids, "case_ids")
        if type(self.preregistered) is not bool:
            raise TypeError("preregistered must be bool")

    @property
    def analysis_status(self) -> str:
        return "preregistered" if self.preregistered else "exploratory"

    def _identity_payload(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "definition_version": self.definition_version,
            "category_kind": self.category_kind,
            "category_value": self.category_value,
            "case_ids": list(self.case_ids),
            "analysis_status": self.analysis_status,
        }

    @property
    def definition_sha256(self) -> str:
        return _hash(self._identity_payload())

    def to_dict(self) -> dict[str, object]:
        return {
            **self._identity_payload(),
            "definition_sha256": self.definition_sha256,
        }


@dataclass(frozen=True, slots=True)
class CategoryEvidence:
    definition: CategoryDefinition
    aggregate: AggregateEvidence
    computation_sha256: str

    def __post_init__(self) -> None:
        if type(self.definition) is not CategoryDefinition:
            raise TypeError("definition must be CategoryDefinition")
        if type(self.aggregate) is not AggregateEvidence:
            raise TypeError("aggregate must be AggregateEvidence")
        if self.aggregate.level != "category":
            raise ValueError("category evidence requires a category-level aggregate")
        if self.aggregate.planned_unit_ids != self.definition.case_ids:
            raise ValueError("category aggregate does not match definition case membership")
        _sha(self.computation_sha256, "computation_sha256")

    @property
    def evidence_id(self) -> str:
        return self.computation_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "category_definition": self.definition.to_dict(),
            "aggregate": self.aggregate.to_dict(),
            "computation_sha256": self.computation_sha256,
        }


@dataclass(frozen=True, slots=True)
class StatisticalSummaryMethod:
    method_id: str
    method_version: str
    method: str
    confidence_level: float | None
    resampling_procedure: str | None
    correction_method: str | None
    missing_disposition: str
    excluded_disposition: str
    failure_disposition: str
    implementation: str
    software_version: str
    preregistered: bool

    def __post_init__(self) -> None:
        _text(self.method_id, "method_id")
        _semver(self.method_version, "method_version")
        _text(self.method, "method")
        if self.confidence_level is not None:
            level = _number(self.confidence_level, "confidence_level")
            if not 0 < level < 1:
                raise ValueError("confidence_level must be strictly between zero and one")
        for value, name in (
            (self.resampling_procedure, "resampling_procedure"),
            (self.correction_method, "correction_method"),
        ):
            if value is not None:
                _text(value, name)
        for value, name in (
            (self.missing_disposition, "missing_disposition"),
            (self.excluded_disposition, "excluded_disposition"),
            (self.failure_disposition, "failure_disposition"),
        ):
            if value not in _ACTIONS:
                raise ValueError(f"invalid {name}")
        _text(self.implementation, "implementation")
        _text(self.software_version, "software_version")
        if type(self.preregistered) is not bool:
            raise TypeError("preregistered must be bool")

    @property
    def analysis_status(self) -> str:
        return "preregistered" if self.preregistered else "exploratory"

    def _identity_payload(self) -> dict[str, object]:
        return {
            "method_id": self.method_id,
            "method_version": self.method_version,
            "method": self.method,
            "confidence_level": self.confidence_level,
            "resampling_procedure": self.resampling_procedure,
            "correction_method": self.correction_method,
            "missing_disposition": self.missing_disposition,
            "excluded_disposition": self.excluded_disposition,
            "failure_disposition": self.failure_disposition,
            "implementation": self.implementation,
            "software_version": self.software_version,
            "analysis_status": self.analysis_status,
        }

    @property
    def method_sha256(self) -> str:
        return _hash(self._identity_payload())

    def to_dict(self) -> dict[str, object]:
        return {
            **self._identity_payload(),
            "method_sha256": self.method_sha256,
        }


@dataclass(frozen=True, slots=True)
class StatisticalSummaryEvidence:
    method: StatisticalSummaryMethod
    aggregate: AggregateEvidence
    category_definition: CategoryDefinition | None
    computation_sha256: str

    def __post_init__(self) -> None:
        if type(self.method) is not StatisticalSummaryMethod:
            raise TypeError("method must be StatisticalSummaryMethod")
        if type(self.aggregate) is not AggregateEvidence:
            raise TypeError("aggregate must be AggregateEvidence")
        if self.category_definition is not None:
            if type(self.category_definition) is not CategoryDefinition:
                raise TypeError("category_definition must be CategoryDefinition or None")
            if self.aggregate.level != "category":
                raise ValueError("category_definition requires category aggregate evidence")
            if self.aggregate.planned_unit_ids != self.category_definition.case_ids:
                raise ValueError("statistical category membership disagrees with aggregate")
        elif self.aggregate.level == "category":
            raise ValueError("category aggregate requires its CategoryDefinition")

        if self.method.missing_disposition != self.aggregate.rule_missing_action:
            raise ValueError("statistical missing disposition disagrees with source aggregate rule")
        source_actions = dict(self.aggregate.rule_state_dispositions)
        for state, disposition in (
            ("excluded", self.method.excluded_disposition),
            ("failed", self.method.failure_disposition),
        ):
            if state in source_actions and source_actions[state] != disposition:
                raise ValueError(
                    f"statistical {state} disposition disagrees with source aggregate rule"
                )
        _sha(self.computation_sha256, "computation_sha256")

    @property
    def analysis_status(self) -> str:
        if not self.method.preregistered:
            return "exploratory"
        if self.category_definition is not None and not self.category_definition.preregistered:
            return "exploratory"
        return "preregistered"

    @property
    def evidence_id(self) -> str:
        return self.computation_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method.to_dict(),
            "analysis_status": self.analysis_status,
            "category_definition": (
                None
                if self.category_definition is None
                else self.category_definition.to_dict()
            ),
            "aggregate": self.aggregate.to_dict(),
            "computation_sha256": self.computation_sha256,
        }


@dataclass(frozen=True, slots=True)
class PairwiseProtocol:
    protocol_id: str
    protocol_version: str
    reference_treatment_id: str
    comparison_treatment_id: str
    difference_direction: str
    comparison_win_when: str
    tie_tolerance: int | float
    missing_pair_disposition: str
    failure_pair_disposition: str
    required_observation_scope: str
    implementation: str
    software_version: str

    def __post_init__(self) -> None:
        _text(self.protocol_id, "protocol_id")
        _semver(self.protocol_version, "protocol_version")
        _text(self.reference_treatment_id, "reference_treatment_id")
        _text(self.comparison_treatment_id, "comparison_treatment_id")
        if self.reference_treatment_id == self.comparison_treatment_id:
            raise ValueError("paired treatments must differ")
        if self.difference_direction not in {
            "comparison_minus_reference", "reference_minus_comparison"
        }:
            raise ValueError("invalid difference_direction")
        if self.comparison_win_when not in {"positive", "negative"}:
            raise ValueError("invalid comparison_win_when")
        _number(self.tie_tolerance, "tie_tolerance")
        if self.tie_tolerance < 0:
            raise ValueError("tie_tolerance must be non-negative")
        if self.missing_pair_disposition not in {"unavailable", "exclude"}:
            raise ValueError("invalid missing_pair_disposition")
        if self.failure_pair_disposition not in _ACTIONS:
            raise ValueError("invalid failure_pair_disposition")
        _text(self.required_observation_scope, "required_observation_scope")
        _text(self.implementation, "implementation")
        _text(self.software_version, "software_version")

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "reference_treatment_id": self.reference_treatment_id,
            "comparison_treatment_id": self.comparison_treatment_id,
            "difference_direction": self.difference_direction,
            "comparison_win_when": self.comparison_win_when,
            "tie_tolerance": self.tie_tolerance,
            "missing_pair_disposition": self.missing_pair_disposition,
            "failure_pair_disposition": self.failure_pair_disposition,
            "required_observation_scope": self.required_observation_scope,
            "implementation": self.implementation,
            "software_version": self.software_version,
        }


@dataclass(frozen=True, slots=True)
class PairResult:
    case_id: str
    reference_evidence_id: str | None
    comparison_evidence_id: str | None
    availability: str
    reason: str | None
    difference: int | float | None
    outcome: str | None
    failure_classes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "reference_evidence_id": self.reference_evidence_id,
            "comparison_evidence_id": self.comparison_evidence_id,
            "availability": self.availability,
            "reason": self.reason,
            "difference": self.difference,
            "outcome": self.outcome,
            "failure_classes": list(self.failure_classes),
        }


@dataclass(frozen=True, slots=True)
class PairwiseEvidence:
    protocol_id: str
    protocol_version: str
    difference_direction: str
    comparison_win_when: str
    tie_tolerance: int | float
    missing_pair_disposition: str
    failure_pair_disposition: str
    protocol_implementation: str
    protocol_software_version: str
    reference_treatment_id: str
    comparison_treatment_id: str
    metric_id: str
    metric_version: str
    metric_registration_id: str
    metric_registration_version: str
    comparison_context_id: str
    observation_scope: str
    planned_case_ids: tuple[str, ...]
    pairs: tuple[PairResult, ...]
    comparable_pair_count: int
    missing_pair_count: int
    unavailable_pair_count: int
    non_comparable_pair_count: int
    excluded_pair_count: int
    failed_pair_count: int
    comparison_win_count: int
    reference_win_count: int
    tie_count: int
    mean_difference: float | None
    comparison_win_rate: float | None
    reference_win_rate: float | None
    tie_rate: float | None
    availability: str
    reason: str | None
    computation_sha256: str

    @property
    def evidence_id(self) -> str:
        return self.computation_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": {
                "id": self.protocol_id,
                "version": self.protocol_version,
                "difference_direction": self.difference_direction,
                "comparison_win_when": self.comparison_win_when,
                "tie_tolerance": self.tie_tolerance,
                "missing_pair_disposition": self.missing_pair_disposition,
                "failure_pair_disposition": self.failure_pair_disposition,
                "implementation": self.protocol_implementation,
                "software_version": self.protocol_software_version,
            },
            "reference_treatment_id": self.reference_treatment_id,
            "comparison_treatment_id": self.comparison_treatment_id,
            "metric": {"id": self.metric_id, "version": self.metric_version},
            "metric_registration": {
                "id": self.metric_registration_id,
                "version": self.metric_registration_version,
            },
            "comparison_context_id": self.comparison_context_id,
            "observation_scope": self.observation_scope,
            "planned_case_ids": list(self.planned_case_ids),
            "pairs": [pair.to_dict() for pair in self.pairs],
            "comparable_pair_count": self.comparable_pair_count,
            "missing_pair_count": self.missing_pair_count,
            "unavailable_pair_count": self.unavailable_pair_count,
            "non_comparable_pair_count": self.non_comparable_pair_count,
            "excluded_pair_count": self.excluded_pair_count,
            "failed_pair_count": self.failed_pair_count,
            "comparison_win_count": self.comparison_win_count,
            "reference_win_count": self.reference_win_count,
            "tie_count": self.tie_count,
            "mean_difference": self.mean_difference,
            "comparison_win_rate": self.comparison_win_rate,
            "reference_win_rate": self.reference_win_rate,
            "tie_rate": self.tie_rate,
            "availability": self.availability,
            "reason": self.reason,
            "computation_sha256": self.computation_sha256,
        }


def aggregate_repetitions(
    inputs: Sequence[AggregationInput],
    *,
    planned_repetition_ids: Sequence[str],
    rule: AggregationRule,
) -> AggregateEvidence:
    values = _typed(inputs, AggregationInput, "inputs")
    if not values:
        raise AggregationError("retained input is required")
    planned = _planned(planned_repetition_ids, "planned_repetition_ids")
    by_id = _unique(values, "repetition_id")
    _reject_unplanned(by_id, planned, "repetition")
    anchor = values[0]
    _same(values, anchor, (
        "case_id", "treatment_id", "metric_id", "metric_version",
        "metric_registration_id", "metric_registration_version",
        "comparison_context_id", "observation_scope",
    ))
    ordered = tuple(by_id[i] for i in planned if i in by_id)
    return _aggregate(
        level="case",
        case_id=anchor.case_id,
        treatment_id=anchor.treatment_id,
        metric_id=anchor.metric_id,
        metric_version=anchor.metric_version,
        metric_registration_id=anchor.metric_registration_id,
        metric_registration_version=anchor.metric_registration_version,
        comparison_context_id=anchor.comparison_context_id,
        observation_scope=anchor.observation_scope,
        planned_ids=planned,
        input_ids=tuple(v.evidence_id for v in ordered),
        present_ids=tuple(v.repetition_id for v in ordered),
        case_ids=(anchor.case_id,),
        repetition_ids=tuple(v.repetition_id for v in ordered),
        fingerprints=_ordered_unique(v.execution_boundary_fingerprint for v in ordered),
        states=tuple(
            (v.availability, v.value, v.failure_class, v.exclusion_authority)
            for v in ordered
        ),
        rule=rule,
    )


def aggregate_cases(
    inputs: Sequence[AggregateEvidence],
    *,
    planned_case_ids: Sequence[str],
    rule: AggregationRule,
) -> AggregateEvidence:
    values = _typed(inputs, AggregateEvidence, "inputs")
    if not values or any(v.level != "case" or v.case_id is None for v in values):
        raise AggregationError(
            "case aggregation requires case-level values; repetitions cannot "
            "inflate independent case count"
        )
    planned = _planned(planned_case_ids, "planned_case_ids")
    by_id = _unique(values, "case_id")
    _reject_unplanned(by_id, planned, "case")
    anchor = values[0]
    _same(values, anchor, (
        "treatment_id", "metric_id", "metric_version",
        "metric_registration_id", "metric_registration_version",
        "comparison_context_id", "observation_scope",
    ))
    ordered = tuple(by_id[i] for i in planned if i in by_id)
    return _aggregate(
        level="treatment",
        case_id=None,
        treatment_id=anchor.treatment_id,
        metric_id=anchor.metric_id,
        metric_version=anchor.metric_version,
        metric_registration_id=anchor.metric_registration_id,
        metric_registration_version=anchor.metric_registration_version,
        comparison_context_id=anchor.comparison_context_id,
        observation_scope=anchor.observation_scope,
        planned_ids=planned,
        input_ids=tuple(v.evidence_id for v in ordered),
        present_ids=tuple(v.case_id for v in ordered if v.case_id),
        case_ids=tuple(v.case_id for v in ordered if v.case_id),
        repetition_ids=(),
        fingerprints=_ordered_unique(
            fp for v in ordered for fp in v.execution_boundary_fingerprints
        ),
        states=tuple((v.availability, v.value, None, None) for v in ordered),
        rule=rule,
        carried_failures=_ordered_unique(
            x for v in ordered for x in v.failure_classes
        ),
        carried_exclusions=_ordered_unique(
            x for v in ordered for x in v.exclusion_authorities
        ),
        carried_missing_count=sum(v.retained_missing_count for v in ordered),
        carried_exclusion_count=sum(v.retained_exclusion_count for v in ordered),
        carried_failure_count=sum(v.retained_failure_count for v in ordered),
    )


def aggregate_category(
    inputs: Sequence[AggregateEvidence],
    *,
    definition: CategoryDefinition,
    rule: AggregationRule,
) -> CategoryEvidence:
    if type(definition) is not CategoryDefinition:
        raise TypeError("definition must be CategoryDefinition")
    values = _typed(inputs, AggregateEvidence, "inputs")
    if not values or any(v.level != "case" or v.case_id is None for v in values):
        raise AggregationError("category aggregation requires retained case-level authority")
    by_id = _unique(values, "case_id")
    anchor = values[0]
    _same(values, anchor, (
        "treatment_id", "metric_id", "metric_version",
        "metric_registration_id", "metric_registration_version",
        "comparison_context_id", "observation_scope",
    ))
    ordered = tuple(by_id[i] for i in definition.case_ids if i in by_id)
    aggregate = _aggregate(
        level="category",
        case_id=None,
        treatment_id=anchor.treatment_id,
        metric_id=anchor.metric_id,
        metric_version=anchor.metric_version,
        metric_registration_id=anchor.metric_registration_id,
        metric_registration_version=anchor.metric_registration_version,
        comparison_context_id=anchor.comparison_context_id,
        observation_scope=anchor.observation_scope,
        planned_ids=definition.case_ids,
        input_ids=tuple(v.evidence_id for v in ordered),
        present_ids=tuple(v.case_id for v in ordered if v.case_id),
        case_ids=tuple(v.case_id for v in ordered if v.case_id),
        repetition_ids=(),
        fingerprints=_ordered_unique(
            fp for v in ordered for fp in v.execution_boundary_fingerprints
        ),
        states=tuple((v.availability, v.value, None, None) for v in ordered),
        rule=rule,
        carried_failures=_ordered_unique(
            failure for v in ordered for failure in v.failure_classes
        ),
        carried_exclusions=_ordered_unique(
            authority for v in ordered for authority in v.exclusion_authorities
        ),
        carried_missing_count=sum(v.retained_missing_count for v in ordered),
        carried_exclusion_count=sum(v.retained_exclusion_count for v in ordered),
        carried_failure_count=sum(v.retained_failure_count for v in ordered),
    )
    payload = {
        "category_definition": definition.to_dict(),
        "aggregate": aggregate.to_dict(),
    }
    return CategoryEvidence(
        definition=definition,
        aggregate=aggregate,
        computation_sha256=_hash(payload),
    )


def summarize_statistical(
    aggregate: AggregateEvidence,
    *,
    method: StatisticalSummaryMethod,
    category_definition: CategoryDefinition | None = None,
) -> StatisticalSummaryEvidence:
    if type(aggregate) is not AggregateEvidence:
        raise TypeError("aggregate must be AggregateEvidence")
    if type(method) is not StatisticalSummaryMethod:
        raise TypeError("method must be StatisticalSummaryMethod")

    probe = StatisticalSummaryEvidence(
        method=method,
        aggregate=aggregate,
        category_definition=category_definition,
        computation_sha256="sha256:" + ("0" * 64),
    )
    payload = {
        "method": method.to_dict(),
        "analysis_status": probe.analysis_status,
        "category_definition": (
            None if category_definition is None else category_definition.to_dict()
        ),
        "aggregate": aggregate.to_dict(),
    }
    return StatisticalSummaryEvidence(
        method=method,
        aggregate=aggregate,
        category_definition=category_definition,
        computation_sha256=_hash(payload),
    )


def aggregate_pairs(
    reference_cases: Sequence[AggregateEvidence],
    comparison_cases: Sequence[AggregateEvidence],
    *,
    planned_case_ids: Sequence[str],
    protocol: PairwiseProtocol,
) -> PairwiseEvidence:
    refs = _case_map(reference_cases, protocol.reference_treatment_id, "reference_cases")
    comps = _case_map(comparison_cases, protocol.comparison_treatment_id, "comparison_cases")
    planned = _planned(planned_case_ids, "planned_case_ids")
    _reject_unplanned(refs, planned, "reference case")
    _reject_unplanned(comps, planned, "comparison case")
    anchor = next((refs.get(i) or comps.get(i) for i in planned if refs.get(i) or comps.get(i)), None)
    if anchor is None:
        raise AggregationError("pairwise evidence requires retained authority")

    pairs: list[PairResult] = []
    for case_id in planned:
        ref, comp = refs.get(case_id), comps.get(case_id)
        if ref is None or comp is None:
            pairs.append(PairResult(
                case_id,
                None if ref is None else ref.evidence_id,
                None if comp is None else comp.evidence_id,
                "excluded" if protocol.missing_pair_disposition == "exclude" else "unavailable",
                "planned pair is missing retained evidence",
                None,
                None,
            ))
            continue
        _pair_compatible(ref, comp, anchor, protocol)
        if ref.availability != "available" or comp.availability != "available":
            failed = ref.retained_failure_count > 0 or comp.retained_failure_count > 0
            if failed:
                action = protocol.failure_pair_disposition
                state = "excluded" if action == "exclude" else action
            else:
                state = (
                    "non_comparable"
                    if "non_comparable" in {ref.availability, comp.availability}
                    else "unavailable"
                )
            pairs.append(PairResult(
                case_id, ref.evidence_id, comp.evidence_id, state,
                "paired evidence is not jointly available", None, None,
                failure_classes=_ordered_unique(
                    ref.failure_classes + comp.failure_classes
                ),
            ))
            continue
        rv, cv = _number(ref.value, "reference value"), _number(comp.value, "comparison value")
        diff = cv - rv if protocol.difference_direction == "comparison_minus_reference" else rv - cv
        if abs(diff) <= protocol.tie_tolerance:
            outcome = "tie"
        else:
            positive = diff > 0
            comparison_wins = positive if protocol.comparison_win_when == "positive" else not positive
            outcome = "comparison_win" if comparison_wins else "reference_win"
        pairs.append(PairResult(case_id, ref.evidence_id, comp.evidence_id, "available", None, diff, outcome))

    comparable = [p for p in pairs if p.availability == "available"]
    missing = sum(p.reference_evidence_id is None or p.comparison_evidence_id is None for p in pairs)
    unavailable = sum(p.availability == "unavailable" for p in pairs)
    noncomp = sum(p.availability == "non_comparable" for p in pairs)
    excluded = sum(p.availability == "excluded" for p in pairs)
    failed_pairs = sum(bool(p.failure_classes) for p in pairs)
    cw = sum(p.outcome == "comparison_win" for p in comparable)
    rw = sum(p.outcome == "reference_win" for p in comparable)
    ties = sum(p.outcome == "tie" for p in comparable)
    complete = len(comparable) == len(planned)
    if complete:
        denom = len(comparable)
        mean_diff = math.fsum(_number(p.difference, "pair difference") for p in comparable) / denom
        rates = (cw / denom, rw / denom, ties / denom)
        availability, reason = "available", None
    else:
        mean_diff, rates = None, (None, None, None)
        availability = "non_comparable" if noncomp else "unavailable"
        reason = (
            "planned pair set is incomplete or non-comparable; relative "
            "differences and rates are withheld"
        )

    payload = {
        "protocol_id": protocol.protocol_id,
        "protocol_version": protocol.protocol_version,
        "difference_direction": protocol.difference_direction,
        "comparison_win_when": protocol.comparison_win_when,
        "tie_tolerance": protocol.tie_tolerance,
        "missing_pair_disposition": protocol.missing_pair_disposition,
        "failure_pair_disposition": protocol.failure_pair_disposition,
        "protocol_implementation": protocol.implementation,
        "protocol_software_version": protocol.software_version,
        "reference_treatment_id": protocol.reference_treatment_id,
        "comparison_treatment_id": protocol.comparison_treatment_id,
        "metric_id": anchor.metric_id,
        "metric_version": anchor.metric_version,
        "metric_registration_id": anchor.metric_registration_id,
        "metric_registration_version": anchor.metric_registration_version,
        "comparison_context_id": anchor.comparison_context_id,
        "observation_scope": anchor.observation_scope,
        "planned_case_ids": planned,
        "pairs": tuple(pairs),
        "comparable_pair_count": len(comparable),
        "missing_pair_count": missing,
        "unavailable_pair_count": unavailable,
        "non_comparable_pair_count": noncomp,
        "excluded_pair_count": excluded,
        "failed_pair_count": failed_pairs,
        "comparison_win_count": cw,
        "reference_win_count": rw,
        "tie_count": ties,
        "mean_difference": mean_diff,
        "comparison_win_rate": rates[0],
        "reference_win_rate": rates[1],
        "tie_rate": rates[2],
        "availability": availability,
        "reason": reason,
    }
    hash_payload = dict(payload)
    hash_payload["pairs"] = [p.to_dict() for p in pairs]
    return PairwiseEvidence(
        **payload,
        computation_sha256=_hash(hash_payload),
    )


def _aggregate(
    *,
    level: str,
    case_id: str | None,
    treatment_id: str,
    metric_id: str,
    metric_version: str,
    metric_registration_id: str,
    metric_registration_version: str,
    comparison_context_id: str,
    observation_scope: str,
    planned_ids: tuple[str, ...],
    input_ids: tuple[str, ...],
    present_ids: tuple[str, ...],
    case_ids: tuple[str, ...],
    repetition_ids: tuple[str, ...],
    fingerprints: tuple[str, ...],
    states: tuple[tuple[str, int | float | None, str | None, str | None], ...],
    rule: AggregationRule,
    carried_failures: tuple[str, ...] = (),
    carried_exclusions: tuple[str, ...] = (),
    carried_missing_count: int = 0,
    carried_exclusion_count: int = 0,
    carried_failure_count: int = 0,
) -> AggregateEvidence:
    if type(rule) is not AggregationRule:
        raise TypeError("rule must be AggregationRule")
    missing = len(planned_ids) - len(present_ids)
    excluded = missing if rule.missing_action == "exclude" else 0
    unavailable = missing if rule.missing_action == "unavailable" else 0
    noncomp = missing if rule.missing_action == "non_comparable" else 0
    failures = list(carried_failures)
    exclusions = list(carried_exclusions)
    counts: dict[str, int] = {"missing": missing} if missing else {}
    values: list[int | float] = []
    failed_count = 0
    actions = rule.actions

    for state, value, failure_class, exclusion_authority in states:
        counts[state] = counts.get(state, 0) + 1
        if failure_class:
            failures.append(failure_class)
        if exclusion_authority:
            exclusions.append(exclusion_authority)
        if state == "failed":
            failed_count += 1
        if state in _VALUE_STATES:
            values.append(_number(value, "aggregate input value"))
            continue
        if state not in actions:
            raise AggregationError(
                f"registered rule has no disposition for state {state!r}"
            )
        action = actions[state]
        if action == "exclude":
            excluded += 1
        elif action == "unavailable":
            unavailable += 1
        else:
            noncomp += 1

    if noncomp:
        availability, reason, value, numerator, denominator = (
            "non_comparable",
            "registered rule preserves non-comparable planned units",
            None, None, None,
        )
    elif unavailable or not values:
        availability, reason, value, numerator, denominator = (
            "unavailable",
            "registered rule preserves unavailable planned units"
            if unavailable
            else "no value-bearing units remain after registered exclusions",
            None, None, None,
        )
    else:
        value, numerator, denominator = _reduce(values, rule.reducer)
        availability, reason = "available", None

    payload = {
        "level": level,
        "case_id": case_id,
        "treatment_id": treatment_id,
        "metric_id": metric_id,
        "metric_version": metric_version,
        "metric_registration_id": metric_registration_id,
        "metric_registration_version": metric_registration_version,
        "comparison_context_id": comparison_context_id,
        "observation_scope": observation_scope,
        "rule_id": rule.rule_id,
        "rule_version": rule.rule_version,
        "rule_reducer": rule.reducer,
        "rule_missing_action": rule.missing_action,
        "rule_state_dispositions": tuple(
            (item.state, item.action) for item in rule.state_dispositions
        ),
        "rule_implementation": rule.implementation,
        "rule_software_version": rule.software_version,
        "planned_unit_ids": planned_ids,
        "input_evidence_ids": input_ids,
        "case_ids": case_ids,
        "repetition_ids": repetition_ids,
        "execution_boundary_fingerprints": fingerprints,
        "availability_counts": tuple(
            (state, counts[state]) for state in sorted(counts, key=_key)
        ),
        "exclusion_authorities": tuple(sorted(set(exclusions), key=_key)),
        "failure_classes": tuple(sorted(set(failures), key=_key)),
        "planned_count": len(planned_ids),
        "included_count": len(values),
        "missing_count": missing,
        "excluded_count": excluded,
        "failed_count": failed_count,
        "unavailable_count": unavailable,
        "non_comparable_count": noncomp,
        "retained_missing_count": carried_missing_count + missing,
        "retained_exclusion_count": carried_exclusion_count + excluded,
        "retained_failure_count": carried_failure_count + failed_count,
        "availability": availability,
        "reason": reason,
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
    }
    return AggregateEvidence(**payload, computation_sha256=_hash(payload))


def _reduce(values: Sequence[int | float], reducer: str):
    if reducer == "sum":
        return math.fsum(values), None, None
    if reducer == "mean":
        return math.fsum(values) / len(values), None, None
    if reducer == "min":
        return min(values), None, None
    if reducer == "max":
        return max(values), None, None
    if any(v not in {0, 1, 0.0, 1.0} for v in values):
        raise AggregationError(
            "rate reducer requires explicit binary values; non-value states "
            "cannot be converted to zero"
        )
    numerator, denominator = int(math.fsum(values)), len(values)
    return numerator / denominator, numerator, denominator


def _case_map(values, treatment_id: str, name: str) -> dict[str, AggregateEvidence]:
    items = _typed(values, AggregateEvidence, name)
    result: dict[str, AggregateEvidence] = {}
    for value in items:
        if value.level != "case" or value.case_id is None:
            raise AggregationError(f"{name} must contain case-level evidence")
        if value.treatment_id != treatment_id:
            raise AggregationError(f"{name} contains the wrong treatment")
        if value.case_id in result:
            raise AggregationError(f"{name} contains a duplicate case")
        result[value.case_id] = value
    return result


def _pair_compatible(ref, comp, anchor, protocol) -> None:
    for value in (ref, comp):
        for field in (
            "metric_id", "metric_version", "metric_registration_id",
            "metric_registration_version", "comparison_context_id",
        ):
            if getattr(value, field) != getattr(anchor, field):
                raise AggregationError(f"paired evidence disagrees on {field}")
        if value.observation_scope != protocol.required_observation_scope:
            raise AggregationError("paired evidence has incompatible observation scope")
    if ref.case_id != comp.case_id:
        raise AggregationError("paired evidence must share case identity")


def _same(values, anchor, fields) -> None:
    for value in values:
        for field in fields:
            if getattr(value, field) != getattr(anchor, field):
                raise AggregationError(f"incompatible evidence disagrees on {field}")


def _planned(values: Sequence[str], name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError(f"{name} must be a sequence")
    result = tuple(values)
    if not result or any(not isinstance(v, str) or not v for v in result):
        raise ValueError(f"{name} must contain non-empty identifiers")
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _typed(values, expected, name):
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError(f"{name} must be a sequence")
    result = tuple(values)
    if any(type(v) is not expected for v in result):
        raise TypeError(f"{name} contains the wrong value type")
    return result


def _unique(values, field: str) -> dict[str, object]:
    result = {}
    for value in values:
        key = getattr(value, field)
        if key in result:
            raise AggregationError(f"duplicate {field} {key!r}")
        result[key] = value
    return result


def _reject_unplanned(present: dict[str, object], planned: tuple[str, ...], unit: str) -> None:
    extras = set(present) - set(planned)
    if extras:
        raise AggregationError(
            f"{unit} evidence contains unplanned identities "
            f"{sorted(extras, key=_key)!r}"
        )


def _ordered_unique(values) -> tuple[str, ...]:
    seen, result = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _semver(value, name: str) -> str:
    if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
        raise ValueError(f"{name} must be an exact semantic version")
    return value


def _sha(value, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase sha256: identity")
    return value


def _number(value, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _key(value: str) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _hash(value: object) -> str:
    def default(item):
        if isinstance(item, PairResult):
            return item.to_dict()
        raise TypeError(type(item).__name__)
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=default,
    ).encode()
    return "sha256:" + hashlib.sha256(rendered).hexdigest()


__all__ = [
    "AggregateEvidence",
    "AggregationError",
    "AggregationInput",
    "AggregationRule",
    "CategoryDefinition",
    "CategoryEvidence",
    "PairResult",
    "PairwiseEvidence",
    "PairwiseProtocol",
    "StateDisposition",
    "StatisticalSummaryEvidence",
    "StatisticalSummaryMethod",
    "aggregate_cases",
    "aggregate_category",
    "aggregate_pairs",
    "aggregate_repetitions",
    "summarize_statistical",
]
