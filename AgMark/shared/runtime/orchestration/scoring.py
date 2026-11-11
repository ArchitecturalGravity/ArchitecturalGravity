"""Registered accepted-run scoring and pre-publication lifecycle reconciliation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import binascii
import importlib
import json
from pathlib import Path, PurePosixPath
import sys

from AgMark.shared.evaluation import (
    METRIC_REGISTRATION_SCHEMA,
    SCORER_INVOCATION_CONTRACT_ID,
    SCORER_INVOCATION_CONTRACT_VERSION,
    SCORE_ARTIFACT_SCHEMA,
    IdentityRef as EvaluationIdentityRef,
    RegisteredScorerAuthority,
    ScoringContext,
    ScoringEvidenceInput,
    invoke_registered_scorer,
    validate_registered_scorer_outcome,
)
from AgMark.shared.runtime.artifacts import (
    ArtifactPayload,
    ArtifactRecord,
    ContractBinding,
    FilesystemArtifactStore,
    RETAINABLE_EVIDENCE,
    SchemaBinding,
    retain_artifact_stage,
    sha256_bytes,
)
from AgMark.shared.runtime.identity import (
    EXECUTION_BOUNDARY_SCHEMA_ID,
    EXECUTION_BOUNDARY_SCHEMA_VERSION,
    ExecutionBoundary,
    IdentityRef,
    canonical_json_bytes,
    canonical_sha256,
)
from AgMark.shared.validation import (
    ArtifactSource,
    LifecycleValidationOutcome,
    RegistrationValidationOutcome,
    RetainedArtifactSource,
    validate_evidence_set_outcome,
    validate_lifecycle_evidence_outcome,
)

from .admission import AcceptedExecutionError, AcceptedExecutionGate
from .execution import TreatmentExecutionResult
from .planning import AcceptedRunSnapshot, PlannedObservation, RunPlan


SCORER_ENTRY_POINT_EXTENSION = (
    "arcgrav.shared.runtime.orchestration:scorer-entry-point"
)
_RESULT_GUARD = object()


class AcceptedScoringError(AcceptedExecutionError):
    """Accepted scoring cannot preserve registered or retained authority."""


@dataclass(frozen=True, slots=True)
class RegisteredScoringDefinition:
    """One exact metric/scorer registration pair requested for accepted scoring."""

    metric_registration: Mapping[str, object]
    scorer_registration: Mapping[str, object]
    scorer_registration_outcome: RegistrationValidationOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.metric_registration, Mapping):
            raise TypeError("metric_registration must be a mapping")
        if not isinstance(self.scorer_registration, Mapping):
            raise TypeError("scorer_registration must be a mapping")
        if type(self.scorer_registration_outcome) is not RegistrationValidationOutcome:
            raise TypeError(
                "scorer_registration_outcome must be RegistrationValidationOutcome"
            )


@dataclass(frozen=True, init=False, slots=True)
class ScoringLifecycleResult:
    """Pre-publication classification from exact scoring and lifecycle evidence.

    This value does not claim terminal accepted/blocked artifact authority. A
    later finalization stage must publish exactly one terminal authority result.
    """

    generation_id: str
    accepted_snapshot_id: str
    run_plan_id: str
    plan_sha256: str
    execution_boundary_fingerprint: str
    classification: str
    reason_code: str | None
    diagnostics: tuple[str, ...]
    score_bytes: tuple[bytes, ...]
    retained_score_artifacts: tuple[ArtifactRecord, ...]
    retained_reporting_artifacts: tuple[ArtifactRecord, ...]
    terminal_candidate_bytes: bytes
    lifecycle_outcome: LifecycleValidationOutcome
    _guard: object

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by score_accepted_treatments")

    def scores(self) -> tuple[dict[str, object], ...]:
        self.revalidate()
        return tuple(
            _decoded_document(raw, "score artifact") for raw in self.score_bytes
        )

    def terminal_candidate(self) -> dict[str, object]:
        self.revalidate()
        return _decoded_document(
            self.terminal_candidate_bytes,
            "terminal lifecycle candidate",
        )

    def revalidate(
        self,
        artifact_store: FilesystemArtifactStore | None = None,
    ) -> None:
        if getattr(self, "_guard", None) is not _RESULT_GUARD:
            raise AcceptedScoringError("scoring lifecycle result authority is invalid")
        if self.classification not in {"accepted", "blocked"}:
            raise AcceptedScoringError("scoring lifecycle classification changed")
        if len(self.score_bytes) != len(self.retained_score_artifacts):
            raise AcceptedScoringError("retained score evidence count changed")
        for raw, record in zip(
            self.score_bytes,
            self.retained_score_artifacts,
            strict=True,
        ):
            document = _decoded_document(raw, "score artifact")
            artifact_id = document.get("score_artifact_id")
            if not isinstance(artifact_id, str) or record.artifact_id != artifact_id:
                raise AcceptedScoringError("retained score artifact identity changed")
            if record.role != "score_artifact":
                raise AcceptedScoringError("retained score artifact role changed")
            if record.sha256 != sha256_bytes(raw):
                raise AcceptedScoringError("retained score artifact bytes changed")
            if record.schema != SchemaBinding(
                SCORE_ARTIFACT_SCHEMA.schema_id,
                SCORE_ARTIFACT_SCHEMA.schema_version,
            ):
                raise AcceptedScoringError("retained score artifact schema changed")
            if record.contract != ContractBinding(
                SCORER_INVOCATION_CONTRACT_ID,
                SCORER_INVOCATION_CONTRACT_VERSION,
            ):
                raise AcceptedScoringError("retained score artifact contract changed")
            if not record.reference.startswith(self.generation_id + "/"):
                raise AcceptedScoringError("retained score artifact generation changed")
            if artifact_store is not None:
                if type(artifact_store) is not FilesystemArtifactStore:
                    raise TypeError("artifact_store must be FilesystemArtifactStore")
                try:
                    retained = artifact_store.read_verified(record)
                except Exception as exc:
                    raise AcceptedScoringError(
                        "retained score artifact failed exact revalidation"
                    ) from exc
                if retained != raw:
                    raise AcceptedScoringError(
                        "retained score artifact no longer matches result evidence"
                    )

        reporting_roles = [record.role for record in self.retained_reporting_artifacts]
        if self.classification == "accepted":
            if reporting_roles.count("execution_boundary") != 1:
                raise AcceptedScoringError(
                    "accepted scoring must retain exactly one reporting execution boundary"
                )
            if reporting_roles.count("metric_registration") < 1:
                raise AcceptedScoringError(
                    "accepted scoring must retain reporting metric authority"
                )
        elif reporting_roles:
            raise AcceptedScoringError(
                "blocked scoring cannot retain accepted reporting authority"
            )
        if any(
            role not in {"execution_boundary", "metric_registration"}
            for role in reporting_roles
        ):
            raise AcceptedScoringError("retained reporting authority role changed")
        for record in self.retained_reporting_artifacts:
            if not record.reference.startswith(self.generation_id + "/"):
                raise AcceptedScoringError(
                    "retained reporting authority generation changed"
                )
            if artifact_store is not None:
                try:
                    artifact_store.read_verified(record)
                except Exception as exc:
                    raise AcceptedScoringError(
                        "retained reporting authority failed exact revalidation"
                    ) from exc

        candidate = _decoded_document(
            self.terminal_candidate_bytes,
            "terminal lifecycle candidate",
        )
        if candidate.get("generation_id") != self.generation_id:
            raise AcceptedScoringError("terminal candidate generation changed")
        if candidate.get("accepted_snapshot_id") != self.accepted_snapshot_id:
            raise AcceptedScoringError("terminal candidate snapshot changed")
        if (
            candidate.get("execution_boundary_fingerprint")
            != self.execution_boundary_fingerprint
        ):
            raise AcceptedScoringError("terminal candidate boundary changed")
        if candidate.get("status") != self.classification:
            raise AcceptedScoringError("terminal candidate classification changed")
        if (
            sha256_bytes(self.terminal_candidate_bytes)
            != self.lifecycle_outcome.run_outcome_sha256
        ):
            raise AcceptedScoringError(
                "lifecycle validation no longer binds the terminal candidate"
            )
        if self.classification == "accepted" and not self.lifecycle_outcome.valid:
            raise AcceptedScoringError(
                "accepted scoring classification requires valid lifecycle authority"
            )


@dataclass(frozen=True, slots=True)
class _ResolvedScorer:
    metric_registration: dict[str, object]
    scorer_registration: dict[str, object]
    authority: RegisteredScorerAuthority
    implementation_source: ArtifactSource
    scorer: Callable


class _DefinitionFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def score_accepted_treatments(
    *,
    gate: AcceptedExecutionGate,
    snapshot: AcceptedRunSnapshot,
    benchmark: IdentityRef | Mapping[str, object],
    case_set: IdentityRef | Mapping[str, object],
    treatment_set: IdentityRef | Mapping[str, object],
    execution_boundary: ExecutionBoundary,
    treatment_result: TreatmentExecutionResult,
    artifact_store: FilesystemArtifactStore,
    scoring_definitions: Sequence[RegisteredScoringDefinition],
) -> ScoringLifecycleResult:
    """Invoke registered scorers over exact retained observations and reconcile lifecycle.

    Scorer behavior is selected exclusively by validated scorer registrations.
    No caller callback is accepted. Every successful score is retained before
    lifecycle validation; scorer failures and explicit non-success score states
    remain distinct and are never converted to synthetic values.
    """

    if type(gate) is not AcceptedExecutionGate:
        raise TypeError("gate must be AcceptedExecutionGate")
    if type(snapshot) is not AcceptedRunSnapshot:
        raise TypeError("snapshot must be AcceptedRunSnapshot")
    if type(execution_boundary) is not ExecutionBoundary:
        raise TypeError("execution_boundary must be ExecutionBoundary")
    if type(treatment_result) is not TreatmentExecutionResult:
        raise TypeError("treatment_result must be TreatmentExecutionResult")
    if type(artifact_store) is not FilesystemArtifactStore:
        raise TypeError("artifact_store must be FilesystemArtifactStore")

    definitions = _definitions(scoring_definitions)
    gate.revalidate()
    plan = snapshot.revalidate_authority(
        benchmark=benchmark,
        case_set=case_set,
        treatment_set=treatment_set,
        execution_boundary=execution_boundary,
    )
    _gate_matches_plan(gate, snapshot, plan)

    (
        golden_documents,
        golden_by_case,
        golden_stdout_by_case,
        golden_records,
        golden_failures,
    ) = _retained_golden_evidence(
        gate=gate,
        plan=plan,
        store=artifact_store,
    )
    (
        treatment_documents,
        treatment_by_observation,
        treatment_response_by_observation,
        treatment_records,
        treatment_failures,
    ) = _retained_treatment_evidence(
        result=treatment_result,
        gate=gate,
        snapshot=snapshot,
        plan=plan,
        store=artifact_store,
    )

    scoring_failures: list[str] = [*golden_failures, *treatment_failures]
    score_bytes: list[bytes] = []
    score_records: list[ArtifactRecord] = []

    definition_keys: set[tuple[str, ...]] = set()
    if not scoring_failures:
        for definition in definitions:
            metric = _json_clone(
                definition.metric_registration,
                label="metric registration",
            )
            registration = _json_clone(
                definition.scorer_registration,
                label="scorer registration",
            )
            key = _definition_key(metric, registration)
            if key in definition_keys:
                scoring_failures.append(
                    _diagnostic("SCORING_DEFINITION_DUPLICATE", key[0], "*")
                )
                continue
            definition_keys.add(key)

            try:
                resolved = _resolve_scorer(
                    definition=definition,
                    metric=metric,
                    registration=registration,
                )
            except _DefinitionFailure as exc:
                scoring_failures.append(
                    _diagnostic(exc.code, _metric_label(metric), "*")
                )
                continue

            for slot in plan.observations:
                try:
                    evidence, evidence_outcome = _scoring_evidence(
                        resolved=resolved,
                        slot=slot,
                        generation_id=gate.generation_id,
                        treatment_by_observation=treatment_by_observation,
                        treatment_response_by_observation=(
                            treatment_response_by_observation
                        ),
                        golden_by_case=golden_by_case,
                        golden_stdout_by_case=golden_stdout_by_case,
                    )
                except _DefinitionFailure as exc:
                    scoring_failures.append(
                        _diagnostic(
                            exc.code,
                            _metric_label(resolved.metric_registration),
                            slot.observation_id,
                        )
                    )
                    continue

                context = ScoringContext(
                    accepted_generation_id=gate.generation_id,
                    accepted_snapshot_id=snapshot.accepted_snapshot_id,
                    execution_boundary_fingerprint=plan.execution_boundary_fingerprint,
                    benchmark=_evaluation_identity(plan.benchmark),
                    case_set=_evaluation_identity(plan.case_set),
                    treatment_set=_evaluation_identity(plan.treatment_set),
                    case_id=slot.case_id,
                    treatment_id=slot.treatment_id,
                    repetition_ids=(slot.repetition,),
                    observation_ids=(slot.observation_id,),
                    scoring_grain="repetition",
                    invocation_id=_invocation_id(
                        generation_id=gate.generation_id,
                        metric=resolved.metric_registration,
                        scorer=resolved.scorer_registration,
                        slot=slot,
                    ),
                )
                outcome = invoke_registered_scorer(
                    authority=resolved.authority,
                    implementation_source=resolved.implementation_source,
                    scorer=resolved.scorer,
                    metric_registration=resolved.metric_registration,
                    context=context,
                    evidence=evidence,
                    evidence_outcome=evidence_outcome,
                    source_id=(
                        "runtime-scoring:"
                        + _metric_label(resolved.metric_registration)
                        + ":"
                        + slot.observation_id
                    ),
                )
                if not outcome.valid or outcome.artifact is None:
                    codes = tuple(sorted({issue.code for issue in outcome.issues}))
                    if not codes:
                        codes = ("SCORER_INVOCATION_NO_AUTHORITY",)
                    for code in codes:
                        scoring_failures.append(
                            _diagnostic(
                                code,
                                _metric_label(resolved.metric_registration),
                                slot.observation_id,
                            )
                        )
                    continue

                raw = canonical_json_bytes(outcome.artifact)
                artifact_id = outcome.artifact.get("score_artifact_id")
                if (
                    not isinstance(artifact_id, str)
                    or not artifact_id.startswith("score:")
                ):
                    scoring_failures.append(
                        _diagnostic(
                            "SCORE_ARTIFACT_ID_INVALID",
                            _metric_label(resolved.metric_registration),
                            slot.observation_id,
                        )
                    )
                    continue
                try:
                    (record,) = retain_artifact_stage(
                        store=artifact_store,
                        generation_id=gate.generation_id,
                        stage_id="score-" + artifact_id.removeprefix("score:"),
                        artifacts=(
                            ArtifactPayload(
                                artifact_id=artifact_id,
                                role="score_artifact",
                                relative_path="score.json",
                                data=raw,
                                provenance="arcgrav.shared.runtime.orchestration",
                                retention_class=RETAINABLE_EVIDENCE,
                                media_type="application/json",
                                encoding="utf-8",
                                schema=SchemaBinding(
                                    SCORE_ARTIFACT_SCHEMA.schema_id,
                                    SCORE_ARTIFACT_SCHEMA.schema_version,
                                ),
                                contract=ContractBinding(
                                    SCORER_INVOCATION_CONTRACT_ID,
                                    SCORER_INVOCATION_CONTRACT_VERSION,
                                ),
                            ),
                        ),
                    )
                except Exception:
                    scoring_failures.append(
                        _diagnostic(
                            "SCORE_ARTIFACT_RETENTION_FAILED",
                            _metric_label(resolved.metric_registration),
                            slot.observation_id,
                        )
                    )
                    continue
                if artifact_store.read_verified(record) != raw:
                    scoring_failures.append(
                        _diagnostic(
                            "SCORE_ARTIFACT_REVALIDATION_FAILED",
                            _metric_label(resolved.metric_registration),
                            slot.observation_id,
                        )
                    )
                    continue
                score_bytes.append(raw)
                score_records.append(record)

    expected_scores = len(definitions) * len(plan.observations)
    if not definitions:
        scoring_failures.append("SCORING_DEFINITION_SET_EMPTY")
    if len(score_records) != expected_scores:
        scoring_failures.append(
            f"SCORING_REQUIRED_SCORE_COUNT_MISMATCH:{len(score_records)}:{expected_scores}"
        )

    score_documents = tuple(
        _decoded_document(raw, "score artifact") for raw in score_bytes
    )
    finalized_at = _utc_now()
    scoring_complete = (
        not scoring_failures and len(score_records) == expected_scores
    )
    reporting_records: tuple[ArtifactRecord, ...] = ()
    if scoring_complete:
        try:
            reporting_records = _retain_reporting_authority(
                generation_id=gate.generation_id,
                execution_boundary=execution_boundary,
                definitions=definitions,
                artifact_store=artifact_store,
            )
        except Exception:
            scoring_failures.append("REPORTING_AUTHORITY_RETENTION_FAILED")
            scoring_complete = False

    all_records = _unique_records(
        (
            *gate.retained_plan_artifacts,
            *golden_records,
            treatment_result.retained_runner_registration_artifact,
            *treatment_records,
            *score_records,
            *reporting_records,
        )
    )
    classification = "accepted" if scoring_complete else "blocked"
    reason_code = None if scoring_complete else "registered_scoring_failed"
    diagnostics = tuple(scoring_failures)

    candidate = _run_outcome_candidate(
        generation_id=gate.generation_id,
        snapshot=snapshot,
        plan=plan,
        classification=classification,
        reason_code=reason_code,
        diagnostics=diagnostics,
        artifacts=all_records,
        finalized_at=finalized_at,
    )
    lifecycle = _validate_candidate(
        snapshot=snapshot,
        plan=plan,
        candidate=candidate,
        golden_documents=golden_documents,
        treatment_documents=treatment_documents,
        score_documents=score_documents,
        generation_id=gate.generation_id,
    )

    if classification == "accepted" and not lifecycle.valid:
        lifecycle_diagnostics = tuple(
            "LIFECYCLE:" + issue.code for issue in lifecycle.issues
        )
        diagnostics = tuple((*diagnostics, *lifecycle_diagnostics))
        classification = "blocked"
        reason_code = "lifecycle_validation_failed"
        candidate = _run_outcome_candidate(
            generation_id=gate.generation_id,
            snapshot=snapshot,
            plan=plan,
            classification=classification,
            reason_code=reason_code,
            diagnostics=diagnostics,
            artifacts=all_records,
            finalized_at=finalized_at,
        )
        lifecycle = _validate_candidate(
            snapshot=snapshot,
            plan=plan,
            candidate=candidate,
            golden_documents=golden_documents,
            treatment_documents=treatment_documents,
            score_documents=score_documents,
            generation_id=gate.generation_id,
        )

    value = object.__new__(ScoringLifecycleResult)
    for name, item in (
        ("generation_id", gate.generation_id),
        ("accepted_snapshot_id", snapshot.accepted_snapshot_id),
        ("run_plan_id", plan.run_plan_id),
        ("plan_sha256", plan.plan_sha256),
        ("execution_boundary_fingerprint", plan.execution_boundary_fingerprint),
        ("classification", classification),
        ("reason_code", reason_code),
        ("diagnostics", diagnostics),
        ("score_bytes", tuple(score_bytes)),
        ("retained_score_artifacts", tuple(score_records)),
        ("retained_reporting_artifacts", reporting_records),
        ("terminal_candidate_bytes", canonical_json_bytes(candidate)),
        ("lifecycle_outcome", lifecycle),
        ("_guard", _RESULT_GUARD),
    ):
        object.__setattr__(value, name, item)
    value.revalidate(artifact_store)
    return value


def _retain_reporting_authority(
    *,
    generation_id: str,
    execution_boundary: ExecutionBoundary,
    definitions: tuple[RegisteredScoringDefinition, ...],
    artifact_store: FilesystemArtifactStore,
) -> tuple[ArtifactRecord, ...]:
    payloads: list[ArtifactPayload] = [
        ArtifactPayload(
            artifact_id="execution-boundary:" + execution_boundary.boundary_id,
            role="execution_boundary",
            relative_path="execution-boundary.json",
            data=execution_boundary.canonical_bytes,
            provenance="arcgrav.shared.runtime.orchestration",
            retention_class=RETAINABLE_EVIDENCE,
            media_type="application/json",
            encoding="utf-8",
            schema=SchemaBinding(
                EXECUTION_BOUNDARY_SCHEMA_ID,
                EXECUTION_BOUNDARY_SCHEMA_VERSION,
            ),
        )
    ]
    metric_payloads: dict[str, ArtifactPayload] = {}
    for definition in definitions:
        metric = _json_clone(
            definition.metric_registration,
            label="metric registration",
        )
        registration_id = metric.get("registration_id")
        registration_version = metric.get("registration_version")
        if not isinstance(registration_id, str) or not registration_id:
            raise AcceptedScoringError(
                "metric registration lacks reporting identity"
            )
        if not isinstance(registration_version, str) or not registration_version:
            raise AcceptedScoringError(
                "metric registration lacks reporting version"
            )
        artifact_id = (
            "metric-registration:" + registration_id + "@" + registration_version
        )
        payload = ArtifactPayload(
            artifact_id=artifact_id,
            role="metric_registration",
            relative_path=(
                "metric-registrations/"
                + canonical_sha256(
                    {
                        "registration_id": registration_id,
                        "registration_version": registration_version,
                    }
                ).removeprefix("sha256:")
                + ".json"
            ),
            data=canonical_json_bytes(metric),
            provenance="arcgrav.shared.runtime.orchestration",
            retention_class=RETAINABLE_EVIDENCE,
            media_type="application/json",
            encoding="utf-8",
            schema=SchemaBinding(
                METRIC_REGISTRATION_SCHEMA.schema_id,
                METRIC_REGISTRATION_SCHEMA.schema_version,
            ),
        )
        previous = metric_payloads.get(artifact_id)
        if previous is not None and previous.data != payload.data:
            raise AcceptedScoringError(
                "metric registration reporting authority is ambiguous"
            )
        metric_payloads[artifact_id] = payload
    payloads.extend(metric_payloads[key] for key in sorted(metric_payloads))
    return retain_artifact_stage(
        store=artifact_store,
        generation_id=generation_id,
        stage_id="reporting-authority",
        artifacts=tuple(payloads),
    )


def _definitions(
    values: Sequence[RegisteredScoringDefinition],
) -> tuple[RegisteredScoringDefinition, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(
            "scoring_definitions must be a sequence of RegisteredScoringDefinition"
        )
    result = tuple(values)
    if any(type(value) is not RegisteredScoringDefinition for value in result):
        raise TypeError(
            "scoring_definitions must contain RegisteredScoringDefinition values"
        )
    return tuple(
        sorted(
            result,
            key=lambda value: _definition_key(
                value.metric_registration,
                value.scorer_registration,
            ),
        )
    )


def _definition_key(
    metric: Mapping[str, object],
    registration: Mapping[str, object],
) -> tuple[str, ...]:
    return (
        _text(metric.get("registration_id"), "metric.registration_id"),
        _text(metric.get("registration_version"), "metric.registration_version"),
        _text(metric.get("metric_id"), "metric_id"),
        _text(metric.get("metric_version"), "metric_version"),
        _text(registration.get("registration_id"), "registration_id"),
        _text(registration.get("registration_version"), "registration_version"),
    )


def _resolve_scorer(
    *,
    definition: RegisteredScoringDefinition,
    metric: dict[str, object],
    registration: dict[str, object],
) -> _ResolvedScorer:
    raw_artifacts = registration.get("implementation_artifacts")
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) != 1:
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_AUTHORITY_AMBIGUOUS")
    artifact = raw_artifacts[0]
    if not isinstance(artifact, Mapping):
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_ARTIFACT_INVALID")
    artifact_id = artifact.get("artifact_id")
    reference = artifact.get("reference")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_ARTIFACT_INVALID")
    if not isinstance(reference, str) or not reference:
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_ARTIFACT_INVALID")

    implementation_source = _implementation_source(
        artifact_id=artifact_id,
        reference=reference,
    )
    authority = validate_registered_scorer_outcome(
        registration,
        registration_outcome=definition.scorer_registration_outcome,
        metric_registration=metric,
        implementation_artifact_id=artifact_id,
        source_id=(
            "runtime-scorer-authority:"
            + str(registration.get("registration_id", "unknown"))
        ),
    )
    if not authority.valid:
        raise _DefinitionFailure("SCORER_REGISTERED_AUTHORITY_INVALID")

    extensions = registration.get("extensions")
    entry_point = (
        extensions.get(SCORER_ENTRY_POINT_EXTENSION)
        if isinstance(extensions, Mapping)
        else None
    )
    if not isinstance(entry_point, str) or ":" not in entry_point:
        raise _DefinitionFailure("SCORER_ENTRY_POINT_MISSING")
    module_name, separator, attribute = entry_point.partition(":")
    if (
        separator != ":"
        or not module_name.startswith("AgMark.")
        or not attribute
        or "." in attribute
    ):
        raise _DefinitionFailure("SCORER_ENTRY_POINT_INVALID")
    expected_reference = module_name.replace(".", "/") + ".py"
    if reference != expected_reference:
        raise _DefinitionFailure("SCORER_ENTRY_POINT_REFERENCE_MISMATCH")

    importlib.invalidate_caches()
    try:
        if module_name in sys.modules:
            module = importlib.reload(sys.modules[module_name])
        else:
            module = importlib.import_module(module_name)
        scorer = getattr(module, attribute)
    except Exception as exc:
        raise _DefinitionFailure("SCORER_ENTRY_POINT_UNAVAILABLE") from exc
    if not callable(scorer):
        raise _DefinitionFailure("SCORER_ENTRY_POINT_NOT_CALLABLE")
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise _DefinitionFailure("SCORER_MODULE_REFERENCE_UNAVAILABLE")
    if Path(module_file).resolve(strict=True) != _repository_path(reference):
        raise _DefinitionFailure("SCORER_MODULE_REFERENCE_MISMATCH")
    if _repository_path(reference).read_bytes() != implementation_source.data:
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_CHANGED_DURING_RESOLUTION")

    return _ResolvedScorer(
        metric_registration=metric,
        scorer_registration=registration,
        authority=authority,
        implementation_source=implementation_source,
        scorer=scorer,
    )


def _implementation_source(*, artifact_id: str, reference: str) -> ArtifactSource:
    path = _repository_path(reference)
    if not path.is_file():
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_UNAVAILABLE")
    return ArtifactSource(
        artifact_id=artifact_id,
        reference=reference,
        data=path.read_bytes(),
    )


def _repository_path(reference: str) -> Path:
    if not isinstance(reference, str) or not reference or "\\" in reference:
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_REFERENCE_INVALID")
    relative = PurePosixPath(reference)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_REFERENCE_INVALID")
    root = Path(__file__).resolve().parents[4]
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _DefinitionFailure("SCORER_IMPLEMENTATION_REFERENCE_INVALID") from exc
    return resolved


def _retained_treatment_evidence(
    *,
    result: TreatmentExecutionResult,
    gate: AcceptedExecutionGate,
    snapshot: AcceptedRunSnapshot,
    plan: RunPlan,
    store: FilesystemArtifactStore,
) -> tuple[
    tuple[dict[str, object], ...],
    dict[str, tuple[ArtifactRecord, RetainedArtifactSource]],
    dict[str, tuple[dict[str, object], RetainedArtifactSource]],
    tuple[ArtifactRecord, ...],
    tuple[str, ...],
]:
    failures: list[str] = []
    try:
        result.revalidate()
    except Exception:
        return (), {}, {}, (), ("ORCHESTRATION_TREATMENT_RESULT_INVALID",)

    expected = (
        gate.generation_id,
        snapshot.accepted_snapshot_id,
        plan.run_plan_id,
        plan.plan_sha256,
        plan.execution_boundary_fingerprint,
    )
    observed = (
        result.generation_id,
        result.accepted_snapshot_id,
        result.run_plan_id,
        result.plan_sha256,
        result.execution_boundary_fingerprint,
    )
    if observed != expected:
        failures.append("ORCHESTRATION_TREATMENT_PLAN_MISMATCH")

    expected_ids = tuple(slot.observation_id for slot in plan.observations)
    if result.observation_ids != expected_ids:
        failures.append("ORCHESTRATION_TREATMENT_MATRIX_MISMATCH")

    documents: list[dict[str, object]] = []
    by_observation: dict[str, tuple[ArtifactRecord, RetainedArtifactSource]] = {}
    response_by_observation: dict[
        str, tuple[dict[str, object], RetainedArtifactSource]
    ] = {}
    retained: list[ArtifactRecord] = []
    for raw, record in zip(
        result.observation_bytes,
        result.retained_observation_artifacts,
        strict=True,
    ):
        try:
            stored = store.read_verified(record)
        except Exception:
            failures.append("ORCHESTRATION_TREATMENT_ARTIFACT_INVALID")
            continue
        if stored != raw:
            failures.append("ORCHESTRATION_TREATMENT_ARTIFACT_MISMATCH")
            continue
        document = _decoded_document(raw, "treatment observation")
        observation_id = document.get("observation_id")
        if (
            not isinstance(observation_id, str)
            or observation_id in by_observation
        ):
            failures.append("ORCHESTRATION_TREATMENT_OBSERVATION_AMBIGUOUS")
            continue
        source = RetainedArtifactSource(
            artifact_id=record.artifact_id,
            reference=record.reference,
            data=stored,
            provenance=record.provenance,
        )
        documents.append(document)
        by_observation[observation_id] = (record, source)
        retained.append(record)

        try:
            response = _retained_treatment_response(
                observation_id=observation_id,
                document=document,
                observation_record=record,
            )
        except _DefinitionFailure:
            failures.append("ORCHESTRATION_TREATMENT_RESPONSE_INVALID")
            continue
        if response is not None:
            response_by_observation[observation_id] = response
    return (
        tuple(documents),
        by_observation,
        response_by_observation,
        tuple(retained),
        tuple(failures),
    )


def _retained_treatment_response(
    *,
    observation_id: str,
    document: Mapping[str, object],
    observation_record: ArtifactRecord,
) -> tuple[dict[str, object], RetainedArtifactSource] | None:
    response = document.get("response")
    if not isinstance(response, Mapping):
        raise _DefinitionFailure("ORCHESTRATION_TREATMENT_RESPONSE_INVALID")
    if response.get("availability") != "retained":
        return None

    reference = response.get("reference")
    digest = response.get("sha256")
    byte_length = response.get("byte_length")
    if (
        not isinstance(reference, str)
        or not reference.startswith("extensions:/")
        or reference == "extensions:/"
        or not isinstance(digest, str)
    ):
        raise _DefinitionFailure("ORCHESTRATION_TREATMENT_RESPONSE_INVALID")

    extensions = document.get("extensions")
    if not isinstance(extensions, Mapping):
        raise _DefinitionFailure("ORCHESTRATION_TREATMENT_RESPONSE_INVALID")
    extension_key = reference.removeprefix("extensions:/")
    encoded = extensions.get(extension_key)
    if not isinstance(encoded, str):
        raise _DefinitionFailure("ORCHESTRATION_TREATMENT_RESPONSE_INVALID")
    try:
        data = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise _DefinitionFailure(
            "ORCHESTRATION_TREATMENT_RESPONSE_INVALID"
        ) from exc

    if sha256_bytes(data) != digest:
        raise _DefinitionFailure("ORCHESTRATION_TREATMENT_RESPONSE_INVALID")
    if byte_length is not None and (
        isinstance(byte_length, bool)
        or not isinstance(byte_length, int)
        or byte_length < 0
        or byte_length != len(data)
    ):
        raise _DefinitionFailure("ORCHESTRATION_TREATMENT_RESPONSE_INVALID")

    artifact_id = observation_id + ".response"
    retained_reference = observation_record.reference + "#" + reference
    artifact = {
        "artifact_id": artifact_id,
        "sha256": digest,
        "reference": retained_reference,
        "availability": "retained",
    }
    source = RetainedArtifactSource(
        artifact_id=artifact_id,
        reference=retained_reference,
        data=data,
        provenance=observation_record.provenance,
    )
    return artifact, source


def _retained_golden_evidence(
    *,
    gate: AcceptedExecutionGate,
    plan: RunPlan,
    store: FilesystemArtifactStore,
) -> tuple[
    tuple[dict[str, object], ...],
    dict[str, tuple[ArtifactRecord, RetainedArtifactSource]],
    dict[str, tuple[ArtifactRecord, RetainedArtifactSource]],
    tuple[ArtifactRecord, ...],
    tuple[str, ...],
]:
    all_records = tuple(gate.retained_golden_artifacts)
    observation_records = tuple(
        record for record in all_records if record.role == "golden_observation"
    )
    if not plan.golden_required:
        if gate.golden_observations or all_records:
            return (
                (),
                {},
                {},
                all_records,
                ("ORCHESTRATION_UNPLANNED_GOLDEN_EVIDENCE",),
            )
        return (), {}, {}, (), ()

    failures: list[str] = []
    documents: list[dict[str, object]] = []
    by_case: dict[str, tuple[ArtifactRecord, RetainedArtifactSource]] = {}
    stdout_by_case: dict[str, tuple[ArtifactRecord, RetainedArtifactSource]] = {}
    observed_hashes: list[str] = []
    records_by_reference = {record.reference: record for record in all_records}
    if len(records_by_reference) != len(all_records):
        failures.append("ORCHESTRATION_GOLDEN_ARTIFACT_REFERENCE_AMBIGUOUS")

    for record in observation_records:
        try:
            raw = store.read_verified(record)
        except Exception:
            failures.append("ORCHESTRATION_GOLDEN_ARTIFACT_INVALID")
            continue
        document = _decoded_document(raw, "golden observation")
        extensions = document.get("extensions")
        evidence = (
            extensions.get("arcgrav.shared.golden:evidence")
            if isinstance(extensions, Mapping)
            else None
        )
        case_id = evidence.get("case_id") if isinstance(evidence, Mapping) else None
        if not isinstance(case_id, str) or not case_id or case_id in by_case:
            failures.append("ORCHESTRATION_GOLDEN_CASE_AUTHORITY_INVALID")
            continue
        source = RetainedArtifactSource(
            artifact_id=record.artifact_id,
            reference=record.reference,
            data=raw,
            provenance=record.provenance,
        )
        documents.append(document)
        by_case[case_id] = (record, source)
        observed_hashes.append(sha256_bytes(raw))

        try:
            stdout = _retained_golden_stdout(
                document=document,
                records_by_reference=records_by_reference,
                store=store,
            )
        except _DefinitionFailure:
            failures.append("ORCHESTRATION_GOLDEN_OUTPUT_INVALID")
            continue
        if stdout is not None:
            stdout_by_case[case_id] = stdout

    gate_hashes = sorted(sha256_bytes(raw) for raw in gate.golden_observations)
    if sorted(observed_hashes) != gate_hashes:
        failures.append("ORCHESTRATION_GOLDEN_EVIDENCE_MISMATCH")
    planned_cases = {slot.case_id for slot in plan.observations}
    if set(by_case) != planned_cases:
        failures.append("ORCHESTRATION_GOLDEN_CASE_SET_MISMATCH")
    return (
        tuple(documents),
        by_case,
        stdout_by_case,
        all_records,
        tuple(failures),
    )


def _retained_golden_stdout(
    *,
    document: Mapping[str, object],
    records_by_reference: Mapping[str, ArtifactRecord],
    store: FilesystemArtifactStore,
) -> tuple[ArtifactRecord, RetainedArtifactSource] | None:
    output = document.get("output")
    if not isinstance(output, Mapping):
        raise _DefinitionFailure("ORCHESTRATION_GOLDEN_OUTPUT_INVALID")
    if output.get("availability") != "retained":
        return None

    reference = output.get("reference")
    digest = output.get("sha256")
    byte_length = output.get("byte_length")
    if not isinstance(reference, str) or not isinstance(digest, str):
        raise _DefinitionFailure("ORCHESTRATION_GOLDEN_OUTPUT_INVALID")
    record = records_by_reference.get(reference)
    if (
        record is None
        or record.role != "golden_stdout"
        or record.sha256 != digest
    ):
        raise _DefinitionFailure("ORCHESTRATION_GOLDEN_OUTPUT_INVALID")
    try:
        data = store.read_verified(record)
    except Exception as exc:
        raise _DefinitionFailure("ORCHESTRATION_GOLDEN_OUTPUT_INVALID") from exc
    if sha256_bytes(data) != digest:
        raise _DefinitionFailure("ORCHESTRATION_GOLDEN_OUTPUT_INVALID")
    if byte_length is not None and (
        isinstance(byte_length, bool)
        or not isinstance(byte_length, int)
        or byte_length < 0
        or byte_length != len(data)
    ):
        raise _DefinitionFailure("ORCHESTRATION_GOLDEN_OUTPUT_INVALID")
    return (
        record,
        RetainedArtifactSource(
            artifact_id=record.artifact_id,
            reference=record.reference,
            data=data,
            provenance=record.provenance,
        ),
    )


def _scoring_evidence(
    *,
    resolved: _ResolvedScorer,
    slot: PlannedObservation,
    generation_id: str,
    treatment_by_observation: Mapping[
        str, tuple[ArtifactRecord, RetainedArtifactSource]
    ],
    treatment_response_by_observation: Mapping[
        str, tuple[dict[str, object], RetainedArtifactSource]
    ],
    golden_by_case: Mapping[
        str, tuple[ArtifactRecord, RetainedArtifactSource]
    ],
    golden_stdout_by_case: Mapping[
        str, tuple[ArtifactRecord, RetainedArtifactSource]
    ],
) -> tuple[tuple[ScoringEvidenceInput, ...], object]:
    required = resolved.metric_registration.get("required_inputs")
    if (
        not isinstance(required, list)
        or not required
        or any(not isinstance(role, str) or not role for role in required)
        or len(set(required)) != len(required)
    ):
        raise _DefinitionFailure("SCORER_REQUIRED_INPUTS_INVALID")

    inputs: list[ScoringEvidenceInput] = []
    for role in required:
        if role == "treatment_observation":
            selected = treatment_by_observation.get(slot.observation_id)
        elif role == "treatment_response":
            selected = treatment_response_by_observation.get(slot.observation_id)
        elif role == "golden_observation":
            selected = golden_by_case.get(slot.case_id)
        elif role == "golden_stdout":
            selected = golden_stdout_by_case.get(slot.case_id)
        else:
            raise _DefinitionFailure("SCORER_REQUIRED_INPUT_ROLE_UNSUPPORTED")
        if selected is None:
            raise _DefinitionFailure("SCORER_REQUIRED_INPUT_UNAVAILABLE")
        artifact_or_record, source = selected
        artifact = (
            artifact_or_record.to_artifact_ref()
            if type(artifact_or_record) is ArtifactRecord
            else artifact_or_record
        )
        inputs.append(
            ScoringEvidenceInput(
                role=role,
                artifact=artifact,
                source=source,
            )
        )

    artifacts = tuple(
        json.loads(canonical_json_bytes(value.artifact).decode("utf-8"))
        for value in inputs
    )
    sources = tuple(value.source for value in inputs)
    evidence_set_id = "scoring-evidence:" + canonical_sha256(
        {
            "generation_id": generation_id,
            "observation_id": slot.observation_id,
            "artifacts": list(artifacts),
        }
    ).removeprefix("sha256:")
    outcome = validate_evidence_set_outcome(
        artifacts,
        sources=sources,
        evidence_set_id=evidence_set_id,
        generation_id=generation_id,
        terminal_state="accepted",
        source_id=evidence_set_id,
        required_artifact_ids=tuple(source.artifact_id for source in sources),
    )
    return tuple(inputs), outcome


def _evaluation_identity(value: IdentityRef) -> EvaluationIdentityRef:
    return EvaluationIdentityRef(
        value.id,
        value.version,
        sha256=value.sha256,
        reference=value.reference,
    )


def _invocation_id(
    *,
    generation_id: str,
    metric: Mapping[str, object],
    scorer: Mapping[str, object],
    slot: PlannedObservation,
) -> str:
    return "score-invocation:" + canonical_sha256(
        {
            "generation_id": generation_id,
            "metric": {
                "id": metric.get("metric_id"),
                "version": metric.get("metric_version"),
                "registration_id": metric.get("registration_id"),
                "registration_version": metric.get("registration_version"),
            },
            "scorer": {
                "id": scorer.get("registration_id"),
                "version": scorer.get("registration_version"),
            },
            "observation_id": slot.observation_id,
        }
    ).removeprefix("sha256:")


def _gate_matches_plan(
    gate: AcceptedExecutionGate,
    snapshot: AcceptedRunSnapshot,
    plan: RunPlan,
) -> None:
    if (
        gate.accepted_snapshot_id != snapshot.accepted_snapshot_id
        or gate.run_plan_id != plan.run_plan_id
        or gate.plan_sha256 != plan.plan_sha256
        or gate.execution_boundary_fingerprint != plan.execution_boundary_fingerprint
    ):
        raise AcceptedScoringError(
            "accepted execution gate does not bind this exact accepted plan"
        )


def _run_outcome_candidate(
    *,
    generation_id: str,
    snapshot: AcceptedRunSnapshot,
    plan: RunPlan,
    classification: str,
    reason_code: str | None,
    diagnostics: tuple[str, ...],
    artifacts: tuple[ArtifactRecord, ...],
    finalized_at: str,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_id": "arcgrav.shared.schema.run-outcome",
        "schema_version": "1.0.0",
        "extensions": {key: value for key, value in plan.to_dict().get("extensions", {}).items()
                       if key == "arcgrav.runtime:treatment-content"},
        "generation_id": generation_id,
        "accepted_snapshot_id": snapshot.accepted_snapshot_id,
        "execution_boundary_fingerprint": plan.execution_boundary_fingerprint,
        "status": classification,
        "run_plan": {
            "artifact_id": plan.run_plan_id,
            "sha256": plan.plan_sha256,
            "availability": "retained",
        },
        "finalized_at": finalized_at,
    }
    refs = [record.to_artifact_ref() for record in artifacts]
    if classification == "accepted":
        value["artifact_index"] = refs
    else:
        value["blocked_manifest"] = {
            "reason_code": reason_code or "runtime_blocked",
            "diagnostics": list(diagnostics),
            "retained_diagnostics": refs,
        }
    return value


def _validate_candidate(
    *,
    snapshot: AcceptedRunSnapshot,
    plan: RunPlan,
    candidate: Mapping[str, object],
    golden_documents: Sequence[Mapping[str, object]],
    treatment_documents: Sequence[Mapping[str, object]],
    score_documents: Sequence[Mapping[str, object]],
    generation_id: str,
) -> LifecycleValidationOutcome:
    return validate_lifecycle_evidence_outcome(
        run_plan=plan.to_dict(),
        plan_completed_at=snapshot.plan_completed_at,
        accepted_at=snapshot.accepted_at,
        run_outcome=candidate,
        golden_observations=tuple(golden_documents),
        treatment_observations=tuple(treatment_documents),
        score_artifacts=tuple(score_documents),
        source_id="runtime-lifecycle:" + generation_id,
    )


def _unique_records(
    values: Sequence[ArtifactRecord],
) -> tuple[ArtifactRecord, ...]:
    result: dict[str, ArtifactRecord] = {}
    for record in values:
        if type(record) is not ArtifactRecord:
            raise AcceptedScoringError(
                "runtime evidence contains invalid artifact records"
            )
        previous = result.get(record.artifact_id)
        if previous is not None and previous != record:
            raise AcceptedScoringError(
                "runtime evidence artifact identity is ambiguous"
            )
        result[record.artifact_id] = record
    return tuple(sorted(result.values(), key=lambda item: item.artifact_id))


def _metric_label(metric: Mapping[str, object]) -> str:
    metric_id = metric.get("metric_id")
    metric_version = metric.get("metric_version")
    if isinstance(metric_id, str) and isinstance(metric_version, str):
        return metric_id + "@" + metric_version
    return "unknown-metric"


def _diagnostic(code: str, metric: str, observation: str) -> str:
    return code + ":" + metric + ":" + observation


def _json_clone(
    value: Mapping[str, object],
    *,
    label: str,
) -> dict[str, object]:
    try:
        decoded = json.loads(canonical_json_bytes(value).decode("utf-8"))
    except Exception as exc:
        raise AcceptedScoringError(
            label + " must be canonical JSON data"
        ) from exc
    if not isinstance(decoded, dict):
        raise AcceptedScoringError(label + " must be a JSON object")
    return decoded


def _decoded_document(raw: bytes, label: str) -> dict[str, object]:
    if not isinstance(raw, bytes):
        raise AcceptedScoringError(label + " must be exact bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptedScoringError(label + " is not canonical JSON") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise AcceptedScoringError(label + " is not canonical retained JSON")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcceptedScoringError(field + " must be a non-empty string")
    return value


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


__all__ = [
    "AcceptedScoringError",
    "RegisteredScoringDefinition",
    "SCORER_ENTRY_POINT_EXTENSION",
    "ScoringLifecycleResult",
    "score_accepted_treatments",
]
