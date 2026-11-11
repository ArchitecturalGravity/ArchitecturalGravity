"""Accepted-only canonical benchmark-neutral reporting model.

This module defines the in-memory reporting boundary. It deliberately does not
revalidate retained bytes, schemas, registrations, or completion authority;
those trust transitions remain separate reporting/validation responsibilities.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import math
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from .revalidation import RevalidatedReportingInput

from ..evaluation.availability import AvailabilityRecord
from ..evaluation.scoring import IdentityRef
from ..runtime.artifacts import AcceptedArtifactIndex, ArtifactRecord


REPORT_SCHEMA_ID: Final[str] = "arcgrav.shared.schema.report"
REPORT_SCHEMA_VERSION: Final[str] = "3.0.0"

REPORT_STATUSES: Final[frozenset[str]] = frozenset(
    {"complete", "complete_with_deviations", "incomplete", "invalid", "dry_run"}
)
SYNTHETIC_CONFORMANCE_EXTENSION: Final[str] = "arcgrav.reporting:synthetic-conformance"
SECTION_AVAILABILITY: Final[frozenset[str]] = frozenset(
    {"available", "unavailable", "not_applicable", "non_comparable"}
)
REQUIRED_REPORT_SECTIONS: Final[tuple[str, ...]] = (
    "executive_summary",
    "identity_execution_boundary",
    "registered_metrics_scoring_rules",
    "treatment_summary",
    "observation_matrix",
    "case_level_result_matrix",
    "paired_treatment_comparisons",
    "failure_class_summary",
    "repetition_consistency_summary",
    "case_category_summary",
    "prompt_construction_summary",
    "telemetry_efficiency_summary",
    "measurement_availability",
    "missing_excluded_deviation_record",
    "statistical_summary",
    "machine_readable_evidence",
    "scope_bounded_conclusion",
)

_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_NAMESPACE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[^\s]+$")
_ACCEPTED_REPORTING_INPUT_GUARD = object()


@dataclass(frozen=True, slots=True)
class ReportArtifactRef:
    """Storage-neutral exact artifact identity retained by the report model."""

    artifact_id: str
    sha256: str
    reference: str | None = None
    availability: str | None = None
    schema_id: str | None = None
    schema_version: str | None = None

    def __post_init__(self) -> None:
        _text(self.artifact_id, "artifact_id")
        _sha(self.sha256, "sha256")
        if self.reference is not None:
            _text(self.reference, "reference")
        if self.availability is not None:
            _text(self.availability, "availability")
        if (self.schema_id is None) != (self.schema_version is None):
            raise ValueError("schema_id and schema_version must be provided together")
        if self.schema_id is not None:
            _text(self.schema_id, "schema_id")
            _semver(self.schema_version, "schema_version")

    @classmethod
    def from_record(cls, record: ArtifactRecord) -> "ReportArtifactRef":
        if type(record) is not ArtifactRecord:
            raise TypeError("record must be ArtifactRecord")
        return cls(
            artifact_id=record.artifact_id,
            sha256=record.sha256,
            reference=record.reference,
            availability=record.availability,
            schema_id=None if record.schema is None else record.schema.schema_id,
            schema_version=None if record.schema is None else record.schema.schema_version,
        )

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
        }
        if self.reference is not None:
            value["reference"] = self.reference
        if self.availability is not None:
            value["availability"] = self.availability
        if self.schema_id is not None:
            value["schema"] = {
                "schema_id": self.schema_id,
                "schema_version": self.schema_version,
            }
        return value


@dataclass(frozen=True, slots=True)
class RegisteredReportMetric:
    """Exact preregistered metric/scorer contract retained without reinterpretation."""

    registration: Mapping[str, object]
    scorer: IdentityRef
    scoring_contracts: tuple[IdentityRef, ...]

    def __post_init__(self) -> None:
        registration = _freeze_mapping(self.registration, "registration")
        object.__setattr__(self, "registration", registration)
        if type(self.scorer) is not IdentityRef:
            raise TypeError("scorer must be IdentityRef")
        if not isinstance(self.scoring_contracts, tuple) or any(
            type(value) is not IdentityRef for value in self.scoring_contracts
        ):
            raise TypeError("scoring_contracts must be a tuple of IdentityRef values")
        if not self.scoring_contracts:
            raise ValueError("scoring_contracts must not be empty")
        identities = tuple(
            (value.id, value.version, value.sha256, value.reference)
            for value in self.scoring_contracts
        )
        if len(set(identities)) != len(identities):
            raise ValueError("scoring_contracts must not contain duplicates")

        for field in (
            "registration_id",
            "registration_version",
            "metric_id",
            "metric_version",
            "comparison_track_id",
        ):
            _text(registration.get(field), f"registration.{field}")
        _semver(registration["registration_version"], "registration.registration_version")
        _semver(registration["metric_version"], "registration.metric_version")
        if type(registration.get("is_primary_endpoint")) is not bool:
            raise ValueError("registration.is_primary_endpoint must be boolean")

    @property
    def registration_id(self) -> str:
        return str(self.registration["registration_id"])

    @property
    def registration_version(self) -> str:
        return str(self.registration["registration_version"])

    @property
    def metric_id(self) -> str:
        return str(self.registration["metric_id"])

    @property
    def metric_version(self) -> str:
        return str(self.registration["metric_version"])

    @property
    def comparison_track_id(self) -> str:
        return str(self.registration["comparison_track_id"])

    @property
    def is_primary_endpoint(self) -> bool:
        return bool(self.registration["is_primary_endpoint"])


@dataclass(frozen=True, slots=True)
class ObservationCounts:
    planned: int
    finalized: int
    completed: int
    scored: int
    failed: int
    missing: int
    excluded: int
    non_scorable: int

    def __post_init__(self) -> None:
        for field in (
            "planned",
            "finalized",
            "completed",
            "scored",
            "failed",
            "missing",
            "excluded",
            "non_scorable",
        ):
            _count(getattr(self, field), field)
        if self.finalized > self.planned:
            raise ValueError("finalized cannot exceed planned")
        if self.completed > self.finalized:
            raise ValueError("completed cannot exceed finalized")
        if self.scored > self.completed:
            raise ValueError("scored cannot exceed completed")
        for field in ("failed", "missing", "excluded", "non_scorable"):
            if getattr(self, field) > self.planned:
                raise ValueError(f"{field} cannot exceed planned")

    def to_dict(self) -> dict[str, int]:
        return {
            "planned": self.planned,
            "finalized": self.finalized,
            "completed": self.completed,
            "scored": self.scored,
            "failed": self.failed,
            "missing": self.missing,
            "excluded": self.excluded,
            "non_scorable": self.non_scorable,
        }


@dataclass(frozen=True, slots=True)
class ObservationMatrixEntry:
    """One planned case x treatment x repetition x boundary observation."""

    observation_id: str
    request_id: str
    case_id: str
    treatment_id: str
    repetition_id: int
    execution_boundary_fingerprint: str
    availability: AvailabilityRecord
    evidence_refs: tuple[ReportArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        for field in ("observation_id", "request_id", "case_id", "treatment_id"):
            _text(getattr(self, field), field)
        _positive_int(self.repetition_id, "repetition_id")
        _sha(self.execution_boundary_fingerprint, "execution_boundary_fingerprint")
        if type(self.availability) is not AvailabilityRecord:
            raise TypeError("availability must be AvailabilityRecord")
        _artifact_refs(self.evidence_refs, "evidence_refs")

    @property
    def coordinate(self) -> tuple[str, str, int, str]:
        return (
            self.case_id,
            self.treatment_id,
            self.repetition_id,
            self.execution_boundary_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class CaseResultEntry:
    """One case x treatment x boundary result for one registered metric."""

    case_id: str
    treatment_id: str
    execution_boundary_fingerprint: str
    metric_registration_id: str
    metric_registration_version: str
    availability: AvailabilityRecord
    value: object | None
    evidence_refs: tuple[ReportArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        for field in (
            "case_id",
            "treatment_id",
            "metric_registration_id",
        ):
            _text(getattr(self, field), field)
        _semver(self.metric_registration_version, "metric_registration_version")
        _sha(self.execution_boundary_fingerprint, "execution_boundary_fingerprint")
        if type(self.availability) is not AvailabilityRecord:
            raise TypeError("availability must be AvailabilityRecord")
        if self.availability.state not in {"scored", "available"} and self.value is not None:
            raise ValueError("non-value availability cannot carry a result value")
        object.__setattr__(self, "value", _freeze_json(self.value, "value"))
        _artifact_refs(self.evidence_refs, "evidence_refs")

    @property
    def coordinate(self) -> tuple[str, str, str, str]:
        return (
            self.case_id,
            self.treatment_id,
            self.execution_boundary_fingerprint,
            self.metric_registration_id,
        )


@dataclass(frozen=True, slots=True)
class TreatmentSummary:
    """Treatment-level retained metric summary without denominator conflation."""

    treatment_id: str
    metric_registration_id: str
    metric_registration_version: str
    availability: AvailabilityRecord
    planned: int
    finalized: int
    completed: int
    scorable: int
    failed: int
    missing: int
    excluded: int
    non_scorable: int
    numerator: int | float | None
    denominator: int | None
    value: object | None

    def __post_init__(self) -> None:
        _text(self.treatment_id, "treatment_id")
        _text(self.metric_registration_id, "metric_registration_id")
        _semver(self.metric_registration_version, "metric_registration_version")
        if type(self.availability) is not AvailabilityRecord:
            raise TypeError("availability must be AvailabilityRecord")
        for field in (
            "planned",
            "finalized",
            "completed",
            "scorable",
            "failed",
            "missing",
            "excluded",
            "non_scorable",
        ):
            _count(getattr(self, field), field)
        if self.finalized > self.planned:
            raise ValueError("finalized cannot exceed planned")
        if self.completed > self.finalized:
            raise ValueError("completed cannot exceed finalized")
        if self.scorable > self.completed:
            raise ValueError("scorable cannot exceed completed")
        if self.denominator is not None:
            _count(self.denominator, "denominator")
        if self.numerator is not None:
            _number(self.numerator, "numerator")
        if self.denominator is None and self.numerator is not None:
            raise ValueError("numerator requires an explicit denominator")
        if self.availability.state not in {"scored", "available"} and self.value is not None:
            raise ValueError("non-value availability cannot carry a summary value")
        object.__setattr__(self, "value", _freeze_json(self.value, "value"))


@dataclass(frozen=True, slots=True)
class ReportSection:
    """Canonical standard section state with exact retained artifact references."""

    availability: str
    reason: str | None = None
    artifact_refs: tuple[ReportArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        if self.availability not in SECTION_AVAILABILITY:
            raise ValueError("invalid report section availability")
        if self.availability == "available":
            if self.reason is not None:
                _text(self.reason, "reason")
        else:
            _text(self.reason, "reason")
        _artifact_refs(self.artifact_refs, "artifact_refs")

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {"availability": self.availability}
        if self.reason is not None:
            value["reason"] = self.reason
        if self.artifact_refs:
            value["artifact_refs"] = [ref.to_dict() for ref in self.artifact_refs]
        return value


@dataclass(frozen=True, init=False, slots=True)
class AcceptedReportingInput:
    """Internal accepted evidence projected from one finalized runtime run.

    Only the finalized-run reporting admission boundary can mint this value.
    It carries the exact accepted artifact index and runtime identities into the
    retained-byte/schema/registration revalidation performed by that boundary.
    """

    artifact_index: AcceptedArtifactIndex
    accepted_snapshot_id: str
    execution_boundary: ReportArtifactRef
    execution_boundary_fingerprint: str
    benchmark: IdentityRef
    case_set: IdentityRef
    treatment_set: IdentityRef
    comparison_track_id: str
    primary_endpoint: IdentityRef
    metrics: tuple[RegisteredReportMetric, ...]
    observation_counts: ObservationCounts
    observation_matrix: tuple[ObservationMatrixEntry, ...]
    case_result_matrix: tuple[CaseResultEntry, ...]
    treatment_summaries: tuple[TreatmentSummary, ...]
    _guard: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "created only by admit_finalized_run_for_reporting"
        )

    def __post_init__(self) -> None:
        if getattr(self, "_guard", None) is not _ACCEPTED_REPORTING_INPUT_GUARD:
            raise TypeError(
                "accepted reporting input lacks finalized runtime authority"
            )
        if type(self.artifact_index) is not AcceptedArtifactIndex:
            raise TypeError("artifact_index must be AcceptedArtifactIndex")
        # Invokes the publication guard without re-reading retained bytes.
        self.artifact_index.to_run_outcome_field()
        _text(self.accepted_snapshot_id, "accepted_snapshot_id")
        if type(self.execution_boundary) is not ReportArtifactRef:
            raise TypeError("execution_boundary must be ReportArtifactRef")
        _sha(self.execution_boundary_fingerprint, "execution_boundary_fingerprint")
        for value, name in (
            (self.benchmark, "benchmark"),
            (self.case_set, "case_set"),
            (self.treatment_set, "treatment_set"),
            (self.primary_endpoint, "primary_endpoint"),
        ):
            if type(value) is not IdentityRef:
                raise TypeError(f"{name} must be IdentityRef")
        _text(self.comparison_track_id, "comparison_track_id")
        if type(self.observation_counts) is not ObservationCounts:
            raise TypeError("observation_counts must be ObservationCounts")
        _typed_tuple(self.metrics, RegisteredReportMetric, "metrics", nonempty=True)
        _typed_tuple(
            self.observation_matrix,
            ObservationMatrixEntry,
            "observation_matrix",
            nonempty=False,
        )
        _typed_tuple(
            self.case_result_matrix,
            CaseResultEntry,
            "case_result_matrix",
            nonempty=False,
        )
        _typed_tuple(
            self.treatment_summaries,
            TreatmentSummary,
            "treatment_summaries",
            nonempty=False,
        )

        metric_ids = [
            (value.registration_id, value.registration_version)
            for value in self.metrics
        ]
        if len(set(metric_ids)) != len(metric_ids):
            raise ValueError("metrics must not duplicate registration identity")
        if any(
            value.comparison_track_id != self.comparison_track_id
            for value in self.metrics
        ):
            raise ValueError("all metrics must bind the registered comparison track")
        primary_matches = [
            value for value in self.metrics
            if value.metric_id == self.primary_endpoint.id
            and value.metric_version == self.primary_endpoint.version
        ]
        if len(primary_matches) != 1 or not primary_matches[0].is_primary_endpoint:
            raise ValueError("primary_endpoint must match exactly one primary metric")

        observation_ids = [value.observation_id for value in self.observation_matrix]
        coordinates = [value.coordinate for value in self.observation_matrix]
        request_ids = [value.request_id for value in self.observation_matrix]
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("observation_matrix must not duplicate observation_id")
        if len(set(coordinates)) != len(coordinates):
            raise ValueError("observation_matrix must not duplicate planned coordinates")
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("observation_matrix must not duplicate request_id")
        if any(
            value.execution_boundary_fingerprint != self.execution_boundary_fingerprint
            for value in self.observation_matrix
        ):
            raise ValueError("observation_matrix must bind one execution boundary")
        if self.observation_counts.planned != len(self.observation_matrix):
            raise ValueError("planned count must equal observation_matrix size")

        case_coordinates = [value.coordinate for value in self.case_result_matrix]
        if len(set(case_coordinates)) != len(case_coordinates):
            raise ValueError("case_result_matrix must not duplicate case results")
        if any(
            value.execution_boundary_fingerprint != self.execution_boundary_fingerprint
            for value in self.case_result_matrix
        ):
            raise ValueError("case_result_matrix must bind one execution boundary")
        registrations = set(metric_ids)
        if any(
            (value.metric_registration_id, value.metric_registration_version)
            not in registrations
            for value in self.case_result_matrix
        ):
            raise ValueError("case_result_matrix references an unregistered metric")

        summary_ids = [
            (
                value.treatment_id,
                value.metric_registration_id,
                value.metric_registration_version,
            )
            for value in self.treatment_summaries
        ]
        if len(set(summary_ids)) != len(summary_ids):
            raise ValueError("treatment_summaries must not duplicate treatment/metric")
        if any(
            (value.metric_registration_id, value.metric_registration_version)
            not in registrations
            for value in self.treatment_summaries
        ):
            raise ValueError("treatment_summaries reference an unregistered metric")

    @property
    def accepted_generation_id(self) -> str:
        return self.artifact_index.generation_id

    @property
    def accepted_artifact_refs(self) -> tuple[ReportArtifactRef, ...]:
        return tuple(ReportArtifactRef.from_record(value) for value in self.artifact_index.artifacts)


def _mint_accepted_reporting_input(
    *,
    artifact_index: AcceptedArtifactIndex,
    accepted_snapshot_id: str,
    execution_boundary: ReportArtifactRef,
    execution_boundary_fingerprint: str,
    benchmark: IdentityRef,
    case_set: IdentityRef,
    treatment_set: IdentityRef,
    comparison_track_id: str,
    primary_endpoint: IdentityRef,
    metrics: tuple[RegisteredReportMetric, ...],
    observation_counts: ObservationCounts,
    observation_matrix: tuple[ObservationMatrixEntry, ...],
    case_result_matrix: tuple[CaseResultEntry, ...],
    treatment_summaries: tuple[TreatmentSummary, ...],
) -> AcceptedReportingInput:
    value = object.__new__(AcceptedReportingInput)
    for name, item in (
        ("artifact_index", artifact_index),
        ("accepted_snapshot_id", accepted_snapshot_id),
        ("execution_boundary", execution_boundary),
        ("execution_boundary_fingerprint", execution_boundary_fingerprint),
        ("benchmark", benchmark),
        ("case_set", case_set),
        ("treatment_set", treatment_set),
        ("comparison_track_id", comparison_track_id),
        ("primary_endpoint", primary_endpoint),
        ("metrics", metrics),
        ("observation_counts", observation_counts),
        ("observation_matrix", observation_matrix),
        ("case_result_matrix", case_result_matrix),
        ("treatment_summaries", treatment_summaries),
        ("_guard", _ACCEPTED_REPORTING_INPUT_GUARD),
    ):
        object.__setattr__(value, name, item)
    value.__post_init__()
    return value


@dataclass(frozen=True, slots=True)
class CanonicalReportModel:
    """One immutable benchmark-neutral report model for one accepted generation."""

    report_id: str
    report_version: str
    accepted: "RevalidatedReportingInput"
    status: str
    sections: Mapping[str, ReportSection]
    report_manifest_id: str
    generated_at: str
    extensions: Mapping[str, object]
    validations: tuple = ()
    validation_inputs: tuple[ReportArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        _text(self.report_id, "report_id")
        _semver(self.report_version, "report_version")
        from .revalidation import RevalidatedReportingInput

        if type(self.accepted) is not RevalidatedReportingInput or not self.accepted.valid:
            raise TypeError("accepted must be RevalidatedReportingInput")
        if self.status not in REPORT_STATUSES:
            raise ValueError("invalid report status")
        _text(self.report_manifest_id, "report_manifest_id")
        _datetime(self.generated_at, "generated_at")

        sections = _freeze_sections(self.sections)
        object.__setattr__(self, "sections", sections)
        extensions = dict(self.extensions)
        from .replay import VALIDATION_EXTENSION, validate_consumers
        validations = validate_consumers(self.validations, self.accepted_generation_id)
        from AgMark.shared.validation.codex_cache.serialization import validation_bytes
        from ..runtime.artifacts import sha256_bytes
        inputs = tuple(self.validation_inputs)
        if len(inputs) != len(validations) or any(type(ref) is not ReportArtifactRef or ref.sha256 != sha256_bytes(validation_bytes(value))
                for ref,value in zip(inputs,validations)):
            raise ValueError("report validation requires exact retained treatment input references")
        object.__setattr__(self, "validation_inputs", inputs)
        observations = {entry.observation_id: entry for entry in self.accepted.accepted.observation_matrix}
        for value in validations:
            expected_ids = {entry.observation_id for entry in observations.values() if entry.treatment_id == value.treatment_id}
            if set(value.scored_observation_ids) != expected_ids:
                raise ValueError("report validation treatment observation linkage differs")
            for replay in value.replays:
                entry = observations.get(replay.validates_observation_id)
                if entry is None or str(entry.repetition_id) != replay.repetition_id or entry.treatment_id != replay.treatment_id:
                    raise ValueError("report validation repetition linkage differs")
        if validations:
            if VALIDATION_EXTENSION in extensions:
                raise ValueError("validation authority is separately reporting-owned")
            extensions[VALIDATION_EXTENSION] = [v.to_dict() for v in validations]
        object.__setattr__(self, "validations", validations)
        if self.accepted.synthetic_conformance:
            if SYNTHETIC_CONFORMANCE_EXTENSION in extensions:
                raise ValueError("synthetic conformance identity is reporting-owned")
            extensions[SYNTHETIC_CONFORMANCE_EXTENSION] = {
                "model_identity_kind": "synthetic_conformance_profile",
            }
        object.__setattr__(self, "extensions", _freeze_extensions(extensions))

    @property
    def accepted_generation_id(self) -> str:
        return self.accepted.accepted_generation_id

    @property
    def schema_identity(self) -> tuple[str, str]:
        return (REPORT_SCHEMA_ID, REPORT_SCHEMA_VERSION)


def build_canonical_report_model(
    accepted: "RevalidatedReportingInput",
    *,
    report_id: str,
    report_version: str,
    status: str,
    sections: Mapping[str, ReportSection],
    report_manifest_id: str,
    generated_at: str,
    extensions: Mapping[str, object] | None = None,
    validations: tuple = (),
    validation_inputs: tuple[ReportArtifactRef, ...] = (),
) -> CanonicalReportModel:
    """Assemble one canonical model from previously revalidated accepted authority."""

    from .revalidation import RevalidatedReportingInput

    if type(accepted) is not RevalidatedReportingInput or not accepted.valid:
        raise TypeError("accepted must be RevalidatedReportingInput")
    return CanonicalReportModel(
        report_id=report_id,
        report_version=report_version,
        accepted=accepted,
        status=status,
        sections=sections,
        report_manifest_id=report_manifest_id,
        generated_at=generated_at,
        extensions={} if extensions is None else extensions,
        validations=validations,
        validation_inputs=validation_inputs,
    )


def _freeze_sections(value: Mapping[str, ReportSection]) -> Mapping[str, ReportSection]:
    if not isinstance(value, Mapping):
        raise TypeError("sections must be a mapping")
    names = set(value)
    required = set(REQUIRED_REPORT_SECTIONS)
    if names != required:
        missing = sorted(required - names)
        extra = sorted(names - required)
        detail: list[str] = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise ValueError("sections must contain exactly the required standard sections: " + "; ".join(detail))
    copied: dict[str, ReportSection] = {}
    for name in REQUIRED_REPORT_SECTIONS:
        section = value[name]
        if type(section) is not ReportSection:
            raise TypeError(f"sections[{name!r}] must be ReportSection")
        copied[name] = section
    return MappingProxyType(copied)


def _freeze_extensions(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("extensions must be a mapping")
    copied: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or _NAMESPACE.fullmatch(key) is None:
            raise ValueError("extension keys must be namespaced")
        copied[key] = _freeze_json(item, f"extensions[{key!r}]")
    return MappingProxyType(dict(sorted(copied.items())))


def _freeze_mapping(value: Mapping[str, object], field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    copied: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field} keys must be strings")
        copied[key] = _freeze_json(item, f"{field}.{key}")
    return MappingProxyType(copied)


def _freeze_json(value: object, field: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field} cannot contain NaN or infinity")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field} object keys must be strings")
            copied[key] = _freeze_json(item, field)
        return MappingProxyType(copied)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_json(item, field) for item in value)
    raise TypeError(f"{field} must contain only JSON-compatible values")


def _artifact_refs(values: object, field: str) -> None:
    _typed_tuple(values, ReportArtifactRef, field, nonempty=False)
    ids = [value.artifact_id for value in values]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{field} must not duplicate artifact_id")


def _typed_tuple(values: object, cls: type, field: str, *, nonempty: bool) -> None:
    if not isinstance(values, tuple) or any(type(value) is not cls for value in values):
        raise TypeError(f"{field} must be a tuple of {cls.__name__} values")
    if nonempty and not values:
        raise ValueError(f"{field} must not be empty")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _semver(value: object, field: str) -> str:
    if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
        raise ValueError(f"{field} must be an exact semantic version")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be canonical SHA-256")
    return value


def _count(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _number(value: object, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return value


def _datetime(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be an RFC3339 date-time string")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC3339 date-time string") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return value


__all__ = [
    "REPORT_SCHEMA_ID",
    "REPORT_SCHEMA_VERSION",
    "REPORT_STATUSES",
    "REQUIRED_REPORT_SECTIONS",
    "SECTION_AVAILABILITY",
    "AcceptedReportingInput",
    "CanonicalReportModel",
    "CaseResultEntry",
    "ObservationCounts",
    "ObservationMatrixEntry",
    "RegisteredReportMetric",
    "ReportArtifactRef",
    "ReportSection",
    "TreatmentSummary",
    "build_canonical_report_model",
]
