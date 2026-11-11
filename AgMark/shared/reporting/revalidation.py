"""Fail-closed accepted-evidence revalidation for canonical reporting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from typing import Any, Final

from ..evaluation.availability import AvailabilityRecord
from ..adapters.execution import (
    CanonicalObservationError,
    validate_retained_parity_observation,
)
from ..evaluation.scoring import IdentityRef
from ..runtime.artifacts import ArtifactRecord, FilesystemArtifactStore
from ..runtime.orchestration.finalization import AcceptedRun
from ..runtime.identity import (
    EXECUTION_BOUNDARY_SCHEMA_ID,
    EXECUTION_BOUNDARY_SCHEMA_VERSION,
    ExecutionBoundary,
)
from ..validation import (
    CatalogEntry,
    SchemaIdentity,
)
from ..validation.structure import prepare_cataloged_validator
from .model import (
    AcceptedReportingInput,
    CaseResultEntry,
    ObservationCounts,
    ObservationMatrixEntry,
    RegisteredReportMetric,
    ReportArtifactRef,
    TreatmentSummary,
    _mint_accepted_reporting_input,
    _freeze_json,
)


_METRIC_REGISTRATION_SCHEMA: Final[SchemaIdentity] = SchemaIdentity(
    "arcgrav.shared.schema.metric-registration",
    "1.0.0",
)
_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
_CATALOG_PATH = _SCHEMA_ROOT / "catalog.json"
_AUTHORITY_GUARD = object()
_SYNTHETIC_EVIDENCE_CLASS: Final[str] = "provider-free-mock-model-execution"


class ReportingInputRevalidationError(ValueError):
    """Accepted reporting input failed an authority-sensitive revalidation."""


@dataclass(frozen=True, init=False)
class RevalidatedReportingInput:
    """Opaque authority proving exact reporting inputs were revalidated."""

    accepted: AcceptedReportingInput
    artifact_identities: tuple[tuple[str, str, str], ...]
    synthetic_conformance: bool
    treatment_measurements: Mapping[str, object]
    score_details: tuple[Mapping[str, object], ...]
    observation_results: tuple[Mapping[str, object], ...]
    model_id: str | None
    reasoning_effort: str | None

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "created only by revalidate_accepted_reporting_input"
        )

    @property
    def valid(self) -> bool:
        return (
            getattr(self, "_authority_guard", None) is _AUTHORITY_GUARD
            and type(getattr(self, "accepted", None)) is AcceptedReportingInput
            and isinstance(getattr(self, "artifact_identities", None), tuple)
            and type(getattr(self, "synthetic_conformance", None)) is bool
        )

    @property
    def accepted_generation_id(self) -> str:
        if not self.valid:
            raise ReportingInputRevalidationError(
                "revalidated reporting authority is invalid"
            )
        return self.accepted.accepted_generation_id


def admit_finalized_run_for_reporting(
    finalized: AcceptedRun,
    *,
    store: FilesystemArtifactStore,
    execution_boundary: ReportArtifactRef,
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
) -> RevalidatedReportingInput:
    """Mint and revalidate reporting authority from one finalized AcceptedRun."""

    if type(finalized) is not AcceptedRun:
        raise TypeError("finalized must be AcceptedRun")
    if type(store) is not FilesystemArtifactStore:
        raise TypeError("store must be FilesystemArtifactStore")
    finalized.revalidate(store)
    from AgMark.shared.treatments import require_certifiable
    require_certifiable(json.loads(finalized.run_outcome_bytes))
    accepted = _mint_accepted_reporting_input(
        artifact_index=finalized.artifact_index,
        accepted_snapshot_id=finalized.accepted_snapshot_id,
        execution_boundary=execution_boundary,
        execution_boundary_fingerprint=finalized.execution_boundary_fingerprint,
        benchmark=benchmark,
        case_set=case_set,
        treatment_set=treatment_set,
        comparison_track_id=comparison_track_id,
        primary_endpoint=primary_endpoint,
        metrics=metrics,
        observation_counts=observation_counts,
        observation_matrix=observation_matrix,
        case_result_matrix=case_result_matrix,
        treatment_summaries=treatment_summaries,
    )
    if accepted.accepted_generation_id != finalized.generation_id:
        raise ReportingInputRevalidationError(
            "reporting admission generation differs from finalized AcceptedRun"
        )
    return revalidate_accepted_reporting_input(accepted, store=store)


def revalidate_accepted_reporting_input(
    accepted: AcceptedReportingInput,
    *,
    store: FilesystemArtifactStore,
) -> RevalidatedReportingInput:
    """Revalidate exact accepted evidence before canonical report assembly.

    The transition is fail-closed. It rereads every accepted retained artifact,
    validates each declared shared-schema document against cataloged schema
    authority, reconstitutes the execution boundary, binds inline metric
    registrations to exact retained metric-registration artifacts, checks
    scorer/contracts/comparison authority, and ensures every report-consumed
    artifact reference is an exact member of the accepted artifact index.
    """

    if type(accepted) is not AcceptedReportingInput:
        raise TypeError("accepted must be AcceptedReportingInput")
    if type(store) is not FilesystemArtifactStore:
        raise TypeError("store must be FilesystemArtifactStore")

    try:
        accepted.artifact_index.to_run_outcome_field()
    except Exception as exc:
        raise ReportingInputRevalidationError(
            "accepted artifact-index authority is invalid"
        ) from exc

    generation_id = accepted.accepted_generation_id
    records: dict[str, ArtifactRecord] = {}
    documents: dict[str, Mapping[str, Any]] = {}
    identities: list[tuple[str, str, str]] = []
    schemas = _ReportingSchemaPreparation()

    for record in accepted.artifact_index.artifacts:
        if type(record) is not ArtifactRecord:
            raise ReportingInputRevalidationError(
                "accepted artifact index contains an invalid record"
            )
        if record.artifact_id in records:
            raise ReportingInputRevalidationError(
                f"accepted artifact id {record.artifact_id!r} is ambiguous"
            )
        if not record.reference.startswith(generation_id + "/"):
            raise ReportingInputRevalidationError(
                f"accepted artifact {record.artifact_id!r} is outside the accepted generation"
            )
        try:
            data = store.read_verified(record)
        except Exception as exc:
            raise ReportingInputRevalidationError(
                f"accepted artifact {record.artifact_id!r} failed exact-byte revalidation"
            ) from exc
        records[record.artifact_id] = record
        identities.append((record.artifact_id, record.sha256, record.reference))
        if record.schema is not None:
            documents[record.artifact_id] = _validate_schema_bound_document(
                record,
                data,
                schemas=schemas,
            )

    from AgMark.shared.treatments import require_certifiable
    for document in documents.values():
        require_certifiable(document)
    _validate_execution_boundary(
        accepted,
        records=records,
        documents=documents,
    )
    _validate_metrics(
        accepted,
        records=records,
        documents=documents,
        schemas=schemas,
    )
    _validate_consumed_evidence(accepted, records=records)
    _validate_availability_effects(accepted)
    synthetic_conformance = _synthetic_conformance_from_evidence(
        execution_boundary_artifact_id=accepted.execution_boundary.artifact_id,
        records=records,
        documents=documents,
    )

    from ..evaluation.telemetry import aggregate_treatment_measurements
    from ..evaluation.telemetry.model import TelemetryError
    planned = {}
    for entry in accepted.observation_matrix:
        planned[entry.treatment_id] = planned.get(entry.treatment_id, 0) + 1
    try:
        treatment_measurements = aggregate_treatment_measurements(
            [(documents[r.artifact_id], r.sha256) for r in records.values() if r.role == "treatment_observation"],
            generation_id=generation_id, planned_observations=planned,
            boundary_fingerprint=accepted.execution_boundary_fingerprint)
    except (TelemetryError, KeyError) as exc:
        raise ReportingInputRevalidationError("invalid retained treatment measurements") from exc

    from .results import SCORE_DETAILS_EXTENSION, registered_score_details
    score_details = []
    for metric in accepted.metrics:
        if SCORE_DETAILS_EXTENSION not in metric.registration.get("extensions", {}):
            continue
        try:
            registered_score_details((), metric.registration)
        except (TypeError, ValueError) as exc:
            raise ReportingInputRevalidationError("invalid registered score detail selection") from exc
        expected_identity = {"id": metric.registration_id, "version": metric.registration_version}
        consumed_score_ids = {
            ref.artifact_id
            for result in accepted.case_result_matrix
            if (result.metric_registration_id, result.metric_registration_version)
            == (metric.registration_id, metric.registration_version)
            for ref in result.evidence_refs
        }
        for record in sorted(records.values(), key=lambda item: item.artifact_id):
            if record.role != "score_artifact" or record.artifact_id not in consumed_score_ids:
                continue
            document = documents.get(record.artifact_id)
            if document is None:
                raise ReportingInputRevalidationError("score details require schema-bound score evidence")
            if document.get("metric_registration") != expected_identity:
                raise ReportingInputRevalidationError("score detail metric differs from its case result")
            try:
                selected_details = registered_score_details((document,), metric.registration)
            except (TypeError, ValueError) as exc:
                raise ReportingInputRevalidationError("invalid registered score detail selection") from exc
            for detail in selected_details:
                detail["source_artifact"] = {
                    "artifact_id": record.artifact_id,
                    "sha256": record.sha256,
                    "reference": record.reference,
                }
                score_details.append(detail)

    from .run_report import project_observation_results
    try:
        observation_results = project_observation_results(accepted, documents=documents, records=records)
    except (ValueError, TypeError, KeyError) as exc:
        raise ReportingInputRevalidationError("invalid retained observation report results") from exc

    value = object.__new__(RevalidatedReportingInput)
    object.__setattr__(value, "accepted", accepted)
    object.__setattr__(
        value,
        "artifact_identities",
        tuple(sorted(identities)),
    )
    object.__setattr__(value, "synthetic_conformance", synthetic_conformance)
    object.__setattr__(value, "treatment_measurements", _freeze_json(treatment_measurements, "treatment_measurements"))
    object.__setattr__(value, "score_details", _freeze_json(score_details, "score_details"))
    object.__setattr__(value, "observation_results", _freeze_json(observation_results, "observation_results"))
    boundary_document = documents[accepted.execution_boundary.artifact_id]
    object.__setattr__(value, "model_id", boundary_document["provider_runtime"].get("model"))
    effort = next((control["value"] for control in boundary_document["controls"]
                   if control["name"] == "reasoning_effort"), None)
    # Do not infer a runtime default when the accepted boundary did not retain it.
    object.__setattr__(value, "reasoning_effort", effort if isinstance(effort, str) and effort.strip() else None)
    object.__setattr__(value, "_authority_guard", _AUTHORITY_GUARD)
    return value


def _synthetic_conformance_from_evidence(
    *,
    execution_boundary_artifact_id: str,
    records: Mapping[str, ArtifactRecord],
    documents: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Derive synthetic conformance identity from exact revalidated run evidence.

    Registered target capabilities and retained execution evidence determine
    synthetic identity independently of adapter names. A contradictory live-looking
    target cannot launder a declared synthetic registration.
    Scenario-bearing model IDs remain opaque comparison identity, never
    independent model-capability variants.
    """

    boundary = documents.get(execution_boundary_artifact_id)
    if not isinstance(boundary, Mapping):
        raise ReportingInputRevalidationError(
            "synthetic identity requires the revalidated execution boundary"
        )
    runner = boundary.get("runner")
    registered_synthetic = False
    for record in records.values():
        if record.role != "runner_registration":
            continue
        registration = documents.get(record.artifact_id)
        if not isinstance(registration, Mapping):
            raise ReportingInputRevalidationError("runner registration evidence is unavailable")
        if (not isinstance(runner, Mapping)
                or registration.get("registration_id") != runner.get("id")
                or registration.get("registration_version") != runner.get("version")):
            raise ReportingInputRevalidationError("runner registration differs from accepted boundary")
        extensions = registration.get("extensions", {})
        composition = extensions.get("arcgrav.adapters:target_composition", {})
        registered_synthetic = registered_synthetic or (
            composition.get("target_class") == "mock-model"
            or extensions.get("arcgrav.adapters:evidence_class") == _SYNTHETIC_EVIDENCE_CLASS)
    observed_synthetic = False
    for record in records.values():
        if record.role != "treatment_observation":
            continue
        observation = documents.get(record.artifact_id)
        extensions = observation.get("extensions") if isinstance(observation, Mapping) else None
        execution = (
            extensions.get("arcgrav.runner:execution")
            if isinstance(extensions, Mapping) else None
        )
        target = execution.get("target") if isinstance(execution, Mapping) else None
        if not isinstance(target, Mapping):
            if registered_synthetic:
                raise ReportingInputRevalidationError(
                    "synthetic conformance observation lacks shared execution target evidence"
                )
            continue
        mock_target = target.get("class") == "mock-model"
        mock_evidence = target.get("evidence_class") == _SYNTHETIC_EVIDENCE_CLASS
        if registered_synthetic and not (mock_target and mock_evidence):
            raise ReportingInputRevalidationError(
                "synthetic conformance registration contradicts retained target evidence"
            )
        observed_synthetic = observed_synthetic or mock_target or mock_evidence
    return registered_synthetic or observed_synthetic


def _validate_schema_bound_document(
    record: ArtifactRecord,
    data: bytes,
    *, schemas=None,
) -> Mapping[str, Any]:
    assert record.schema is not None
    try:
        decoded = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportingInputRevalidationError(
            f"schema-bound artifact {record.artifact_id!r} is not exact UTF-8 JSON"
        ) from exc
    if not isinstance(decoded, Mapping):
        raise ReportingInputRevalidationError(
            f"schema-bound artifact {record.artifact_id!r} must decode to an object"
        )
    schema = SchemaIdentity(
        record.schema.schema_id,
        record.schema.schema_version,
    )
    prepared = (schemas or _ReportingSchemaPreparation()).validator(schema)
    issues = prepared(decoded, source_id=f"reporting-revalidation:{record.artifact_id}")
    if issues:
        codes = ", ".join(issue.code for issue in issues)
        raise ReportingInputRevalidationError(
            f"schema-bound artifact {record.artifact_id!r} failed shared-schema "
            f"revalidation: {codes}"
        )
    if record.role == "treatment_observation":
        try:
            validate_retained_parity_observation(decoded)
        except CanonicalObservationError as exc:
            raise ReportingInputRevalidationError(
                f"treatment observation {record.artifact_id!r} has invalid shared execution evidence"
            ) from exc
    return decoded


def _validate_execution_boundary(
    accepted: AcceptedReportingInput,
    *,
    records: Mapping[str, ArtifactRecord],
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    record = _require_authorized_ref(
        accepted.execution_boundary,
        records=records,
        context="execution boundary",
    )
    if (
        record.schema is None
        or record.schema.schema_id != EXECUTION_BOUNDARY_SCHEMA_ID
        or record.schema.schema_version != EXECUTION_BOUNDARY_SCHEMA_VERSION
    ):
        raise ReportingInputRevalidationError(
            "execution boundary lacks exact published schema authority"
        )
    document = documents.get(record.artifact_id)
    if document is None:
        raise ReportingInputRevalidationError(
            "execution boundary retained document was not revalidated"
        )
    try:
        boundary = ExecutionBoundary.from_document(document)
    except Exception as exc:
        raise ReportingInputRevalidationError(
            "execution boundary canonical identity failed revalidation"
        ) from exc
    if boundary.fingerprint != accepted.execution_boundary_fingerprint:
        raise ReportingInputRevalidationError(
            "execution boundary fingerprint differs from accepted reporting authority"
        )


def _validate_metrics(
    accepted: AcceptedReportingInput,
    *,
    records: Mapping[str, ArtifactRecord],
    documents: Mapping[str, Mapping[str, Any]],
    schemas=None,
) -> None:
    retained_metrics = [
        (record, documents.get(record.artifact_id))
        for record in records.values()
        if record.schema is not None
        and record.schema.schema_id == _METRIC_REGISTRATION_SCHEMA.schema_id
        and record.schema.schema_version == _METRIC_REGISTRATION_SCHEMA.schema_version
    ]

    for metric in accepted.metrics:
        registration = _plain_json(metric.registration)
        if not isinstance(registration, Mapping):
            raise ReportingInputRevalidationError(
                "metric registration must remain an object"
            )
        _validate_metric_binding(
            metric,
            registration=registration,
            comparison_track_id=accepted.comparison_track_id,
            schemas=schemas,
        )

        matches = [
            document
            for _record, document in retained_metrics
            if isinstance(document, Mapping)
            and document.get("registration_id") == metric.registration_id
            and document.get("registration_version") == metric.registration_version
        ]
        if len(matches) != 1:
            raise ReportingInputRevalidationError(
                f"metric registration {metric.registration_id!r}@"
                f"{metric.registration_version} must resolve to exactly one retained "
                "accepted metric-registration artifact"
            )
        if dict(matches[0]) != dict(registration):
            raise ReportingInputRevalidationError(
                f"retained metric registration {metric.registration_id!r}@"
                f"{metric.registration_version} differs from accepted reporting authority"
            )


def _validate_metric_binding(
    metric: RegisteredReportMetric,
    *,
    registration: Mapping[str, Any],
    comparison_track_id: str,
    schemas=None,
) -> None:
    prepared = (schemas or _ReportingSchemaPreparation()).validator(_METRIC_REGISTRATION_SCHEMA)
    issues = prepared(registration, source_id=f"reporting-revalidation:{metric.registration_id}")
    if issues:
        codes = ", ".join(issue.code for issue in issues)
        raise ReportingInputRevalidationError(
            f"metric registration {metric.registration_id!r} failed shared-schema "
            f"revalidation: {codes}"
        )

    if registration.get("comparison_track_id") != comparison_track_id:
        raise ReportingInputRevalidationError(
            f"metric registration {metric.registration_id!r} changed comparison scope"
        )
    scorer = registration.get("scorer_or_annotation")
    if (
        not isinstance(scorer, Mapping)
        or scorer.get("procedure_id") != metric.scorer.id
        or scorer.get("version") != metric.scorer.version
    ):
        raise ReportingInputRevalidationError(
            f"metric registration {metric.registration_id!r} does not bind the exact scorer"
        )
    contracts = registration.get("contracts")
    expected_contracts = [
        value.to_dict() for value in metric.scoring_contracts
    ]
    if contracts != expected_contracts:
        raise ReportingInputRevalidationError(
            f"metric registration {metric.registration_id!r} changed scoring contracts"
        )


def _validate_consumed_evidence(
    accepted: AcceptedReportingInput,
    *,
    records: Mapping[str, ArtifactRecord],
) -> None:
    _require_authorized_ref(
        accepted.execution_boundary,
        records=records,
        context="execution boundary",
    )
    for index, observation in enumerate(accepted.observation_matrix):
        for ref in observation.evidence_refs:
            _require_authorized_ref(
                ref,
                records=records,
                context=f"observation_matrix[{index}] evidence",
            )
    for index, result in enumerate(accepted.case_result_matrix):
        for ref in result.evidence_refs:
            _require_authorized_ref(
                ref,
                records=records,
                context=f"case_result_matrix[{index}] evidence",
            )


def _validate_availability_effects(
    accepted: AcceptedReportingInput,
) -> None:
    registered = {
        (metric.registration_id, metric.registration_version)
        for metric in accepted.metrics
    }
    records: list[AvailabilityRecord] = [
        *(value.availability for value in accepted.observation_matrix),
        *(value.availability for value in accepted.case_result_matrix),
        *(value.availability for value in accepted.treatment_summaries),
    ]
    for availability in records:
        for effect in availability.downstream_effects:
            identity = (
                effect.metric_registration_id,
                effect.metric_registration_version,
            )
            if identity not in registered:
                raise ReportingInputRevalidationError(
                    "availability downstream effect references an unregistered metric"
                )


def _require_authorized_ref(
    ref: ReportArtifactRef,
    *,
    records: Mapping[str, ArtifactRecord],
    context: str,
) -> ArtifactRecord:
    if type(ref) is not ReportArtifactRef:
        raise TypeError("ref must be ReportArtifactRef")
    record = records.get(ref.artifact_id)
    if record is None:
        raise ReportingInputRevalidationError(
            f"{context} references artifact {ref.artifact_id!r} outside accepted authority"
        )
    if ref != ReportArtifactRef.from_record(record):
        raise ReportingInputRevalidationError(
            f"{context} reference for {ref.artifact_id!r} differs from exact accepted authority"
        )
    return record


class _ReportingSchemaPreparation:
    """Fresh catalog/schema authority and prepared validators for one admission."""

    def __init__(self):
        self.catalog = None
        self.validators = {}

    def validator(self, schema):
        key = (schema.schema_id, schema.schema_version)
        if key not in self.validators:
            if self.catalog is None:
                self.catalog = _read_schema_catalog()
            entry, document = _schema_authority(*key, catalog=self.catalog)
            self.validators[key] = prepare_cataloged_validator(schema_document=document, entry=entry)
        return self.validators[key]


def _read_schema_catalog():
    try:
        catalog = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportingInputRevalidationError(
            "published shared schema catalog is unavailable or invalid"
        ) from exc
    if not isinstance(catalog, Mapping):
        raise ReportingInputRevalidationError(
            "published shared schema catalog must be an object"
        )
    return catalog


def _schema_authority(
    schema_id: str,
    schema_version: str,
    *, catalog=None,
) -> tuple[CatalogEntry, Mapping[str, Any]]:
    if catalog is None:
        catalog = _read_schema_catalog()
    raw_entries = catalog.get("entries")
    if not isinstance(raw_entries, list):
        raise ReportingInputRevalidationError(
            "published shared schema catalog entries are invalid"
        )
    matches = [
        item
        for item in raw_entries
        if isinstance(item, Mapping)
        and item.get("schema_id") == schema_id
        and item.get("schema_version") == schema_version
    ]
    if len(matches) != 1:
        raise ReportingInputRevalidationError(
            f"shared schema {schema_id!r}@{schema_version} does not resolve exactly once"
        )
    try:
        entry = CatalogEntry.from_mapping(matches[0])
    except ValueError as exc:
        raise ReportingInputRevalidationError(
            f"shared schema {schema_id!r}@{schema_version} has invalid catalog authority"
        ) from exc

    relative = PurePosixPath(entry.file)
    expected_prefix = PurePosixPath("AgMark/shared/schemas")
    try:
        local_relative = relative.relative_to(expected_prefix)
    except ValueError as exc:
        raise ReportingInputRevalidationError(
            "shared schema catalog entry escapes published schema authority"
        ) from exc
    if any(part in {"", ".", ".."} for part in local_relative.parts):
        raise ReportingInputRevalidationError(
            "shared schema catalog entry contains an invalid path"
        )
    local_path = _SCHEMA_ROOT.joinpath(*local_relative.parts)
    try:
        schema_document = json.loads(local_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportingInputRevalidationError(
            f"shared schema {schema_id!r}@{schema_version} is unavailable or invalid"
        ) from exc
    if not isinstance(schema_document, Mapping):
        raise ReportingInputRevalidationError(
            f"shared schema {schema_id!r}@{schema_version} must be an object"
        )
    return entry, schema_document


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


__all__ = [
    "ReportingInputRevalidationError",
    "admit_finalized_run_for_reporting",
    "RevalidatedReportingInput",
    "revalidate_accepted_reporting_input",
]
