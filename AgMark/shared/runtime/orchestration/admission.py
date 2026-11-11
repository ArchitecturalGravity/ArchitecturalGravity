"""Accepted-execution admission before any treatment construction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from AgMark.shared.runtime.artifacts import (
    ArtifactRecord,
    BlockedArtifactManifest,
    BlockedEvidenceRole,
    FilesystemArtifactStore,
    publish_blocked_artifact_manifest,
)
from AgMark.shared.runtime.golden import (
    GoldenCaseInput,
    GoldenDeclaration,
    GoldenExecutionResult,
    execute_required_golden,
)
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef

from .planning import AcceptedRunSnapshot, RunPlan


class AcceptedExecutionError(ValueError):
    """Accepted execution cannot establish the next lifecycle authority."""


_ADMISSION_GUARD = object()


@dataclass(frozen=True, init=False, slots=True)
class AcceptedExecutionGate:
    """Opaque authority proving all required golden work completed first."""

    generation_id: str
    accepted_snapshot_id: str
    run_plan_id: str
    plan_sha256: str
    execution_boundary_fingerprint: str
    golden_observations: tuple[bytes, ...]
    retained_golden_artifacts: tuple[ArtifactRecord, ...]
    retained_plan_artifacts: tuple[ArtifactRecord, ...]
    _admission_guard: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by admit_accepted_execution")

    def revalidate(self) -> None:
        if getattr(self, "_admission_guard", None) is not _ADMISSION_GUARD:
            raise AcceptedExecutionError("accepted execution gate authority is invalid")


@dataclass(frozen=True, init=False, slots=True)
class BlockedRun:
    """Terminal blocked authority for one accepted execution generation."""

    generation_id: str
    accepted_snapshot_id: str
    run_plan_id: str
    plan_sha256: str
    execution_boundary_fingerprint: str
    reason_code: str
    diagnostics: tuple[str, ...]
    golden_observations: tuple[bytes, ...]
    treatment_observations: tuple[object, ...]
    artifact_manifest: BlockedArtifactManifest

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by accepted execution orchestration")

    @property
    def status(self) -> str:
        return "blocked"


def admit_accepted_execution(
    *,
    generation_id: str,
    snapshot: AcceptedRunSnapshot,
    benchmark: IdentityRef | Mapping[str, object],
    case_set: IdentityRef | Mapping[str, object],
    treatment_set: IdentityRef | Mapping[str, object],
    execution_boundary: ExecutionBoundary,
    benchmark_root: str | Path,
    artifact_store: FilesystemArtifactStore,
    golden_declaration: GoldenDeclaration | None = None,
    golden_case_inputs: Sequence[GoldenCaseInput] = (),
    transient_values: Mapping[str, str] | None = None,
) -> AcceptedExecutionGate | BlockedRun:
    """Revalidate accepted authority and complete required golden admission.

    No treatment collaborator is accepted by this boundary. A later treatment
    stage can therefore require AcceptedExecutionGate and cannot be reached
    from a blocked golden admission.
    """

    generation = _safe_generation_id(generation_id)
    if type(snapshot) is not AcceptedRunSnapshot:
        raise TypeError("snapshot must be an AcceptedRunSnapshot")
    if type(execution_boundary) is not ExecutionBoundary:
        raise TypeError("execution_boundary must be an ExecutionBoundary")
    if type(artifact_store) is not FilesystemArtifactStore:
        raise TypeError("artifact_store must be a FilesystemArtifactStore")

    plan = snapshot.revalidate_authority(
        benchmark=benchmark,
        case_set=case_set,
        treatment_set=treatment_set,
        execution_boundary=execution_boundary,
    )

    from AgMark.shared.treatments import CONTENT
    from AgMark.shared.telemetry.runtime_reference import PLAN_EXTENSION
    plan_records = ()
    if {CONTENT, PLAN_EXTENSION}.intersection(plan.to_dict().get("extensions", {})):
        from AgMark.shared.runtime.artifacts import ArtifactPayload, SchemaBinding, RETAINABLE_EVIDENCE, retain_artifact_stage
        plan_records = retain_artifact_stage(store=artifact_store, generation_id=generation,
            stage_id="accepted-plan", artifacts=(ArtifactPayload(
                artifact_id=plan.run_plan_id, role="run_plan", relative_path="plan.json",
                data=plan.canonical_bytes, provenance="arcgrav.shared.runtime.orchestration",
                retention_class=RETAINABLE_EVIDENCE, media_type="application/json", encoding="utf-8",
                schema=SchemaBinding("arcgrav.shared.schema.run-plan", "1.0.0")),))
    if not plan.golden_required:
        if golden_declaration is not None or tuple(golden_case_inputs) or transient_values:
            raise AcceptedExecutionError(
                "golden inputs are not permitted when the accepted plan does not require golden authority"
            )
        return _mint_gate(
            generation=generation,
            snapshot=snapshot,
            plan=plan,
            golden_results=(),
            plan_records=plan_records,
        )

    if type(golden_declaration) is not GoldenDeclaration:
        raise AcceptedExecutionError(
            "required golden execution needs one validated GoldenDeclaration"
        )
    inputs = _validated_golden_inputs(plan, golden_case_inputs)
    results: list[GoldenExecutionResult] = []

    for case_input in inputs:
        result = execute_required_golden(
            accepted_generation_id=generation,
            benchmark=plan.benchmark,
            benchmark_root=benchmark_root,
            accepted_boundary=snapshot._accepted_boundary,
            retained_boundary_document=execution_boundary.to_dict(),
            declaration=golden_declaration,
            case_input=case_input,
            artifact_store=artifact_store,
            transient_values=transient_values,
        )
        results.append(result)
        if not result.treatment_authorized:
            return _blocked_from_golden(
                generation=generation,
                snapshot=snapshot,
                plan=plan,
                results=tuple(results),
                plan_records=plan_records,
                artifact_store=artifact_store,
            )

    return _mint_gate(
        generation=generation,
        snapshot=snapshot,
        plan=plan,
        golden_results=tuple(results),
        plan_records=plan_records,
    )


def _validated_golden_inputs(
    plan: RunPlan,
    values: Sequence[GoldenCaseInput],
) -> tuple[GoldenCaseInput, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("golden_case_inputs must be a sequence of GoldenCaseInput values")
    inputs = tuple(values)
    if not inputs or any(type(value) is not GoldenCaseInput for value in inputs):
        raise AcceptedExecutionError(
            "required golden authority needs exact GoldenCaseInput values for every planned case"
        )
    by_case = {value.case_id: value for value in inputs}
    if len(by_case) != len(inputs):
        raise AcceptedExecutionError("golden case-input identities must be unique")

    expected_order: list[str] = []
    expected: dict[str, tuple[str, int | None]] = {}
    for observation in plan.observations:
        authority = (observation.input_sha256, observation.input_byte_length)
        previous = expected.get(observation.case_id)
        if previous is None:
            expected_order.append(observation.case_id)
            expected[observation.case_id] = authority
        elif previous != authority:
            raise AcceptedExecutionError(
                "accepted plan contains inconsistent input authority for one case"
            )

    if set(by_case) != set(expected):
        raise AcceptedExecutionError(
            "golden case inputs must exactly match the accepted planned case set"
        )
    for case_id, (expected_sha256, expected_length) in expected.items():
        observed = by_case[case_id]
        if observed.sha256 != expected_sha256:
            raise AcceptedExecutionError(
                f"golden case input bytes do not match accepted authority for {case_id!r}"
            )
        if expected_length is not None and len(observed.data) != expected_length:
            raise AcceptedExecutionError(
                f"golden case input length does not match accepted authority for {case_id!r}"
            )
    return tuple(by_case[case_id] for case_id in expected_order)


def _blocked_from_golden(
    *,
    generation: str,
    snapshot: AcceptedRunSnapshot,
    plan: RunPlan,
    results: tuple[GoldenExecutionResult, ...],
    plan_records: tuple[ArtifactRecord, ...],
    artifact_store: FilesystemArtifactStore,
) -> BlockedRun:
    artifacts = tuple(
        sorted(
            (*plan_records, *(record for result in results for record in result.retained_artifacts)),
            key=lambda record: record.artifact_id,
        )
    )
    observations = tuple(result.observation_bytes for result in results)
    diagnostics = tuple(
        diagnostic
        for result in results
        for diagnostic in result.observation.get("diagnostics", [])
        if isinstance(diagnostic, str)
    )
    reason_code = _reason_code(diagnostics)

    retained_roles = sorted({record.role for record in artifacts})
    roles = [
        BlockedEvidenceRole(
            role=role,
            availability="retained",
            reason="retained partial evidence from blocked required-golden admission",
        )
        for role in retained_roles
    ]
    if "golden_observation" not in retained_roles:
        roles.append(
            BlockedEvidenceRole(
                role="golden_observation",
                availability="invalid",
                reason="required golden observation could not establish retained authority",
            )
        )
    roles.extend(
        (
            BlockedEvidenceRole(
                role="treatment_observations",
                availability="not_produced",
                reason="required golden admission blocked before treatment authorization",
            ),
            BlockedEvidenceRole(
                role="score_artifacts",
                availability="not_produced",
                reason="scoring is not authorized before required golden admission",
            ),
            BlockedEvidenceRole(
                role="accepted_artifact_index",
                availability="not_produced",
                reason="blocked golden admission cannot create accepted artifact authority",
            ),
        )
    )
    manifest = publish_blocked_artifact_manifest(
        store=artifact_store,
        generation_id=generation,
        terminal_status="blocked",
        reason_code=reason_code,
        diagnostics=diagnostics,
        evidence_roles=tuple(roles),
        retained_diagnostics=artifacts,
    )
    return _mint(
        BlockedRun,
        generation_id=generation,
        accepted_snapshot_id=snapshot.accepted_snapshot_id,
        run_plan_id=plan.run_plan_id,
        plan_sha256=plan.plan_sha256,
        execution_boundary_fingerprint=plan.execution_boundary_fingerprint,
        reason_code=reason_code,
        diagnostics=diagnostics,
        golden_observations=observations,
        treatment_observations=(),
        artifact_manifest=manifest,
    )


def _mint_gate(
    *,
    generation: str,
    snapshot: AcceptedRunSnapshot,
    plan: RunPlan,
    golden_results: tuple[GoldenExecutionResult, ...],
    plan_records: tuple[ArtifactRecord, ...],
) -> AcceptedExecutionGate:
    value = _mint(
        AcceptedExecutionGate,
        generation_id=generation,
        accepted_snapshot_id=snapshot.accepted_snapshot_id,
        run_plan_id=plan.run_plan_id,
        plan_sha256=plan.plan_sha256,
        execution_boundary_fingerprint=plan.execution_boundary_fingerprint,
        retained_plan_artifacts=plan_records,
        golden_observations=tuple(result.observation_bytes for result in golden_results),
        retained_golden_artifacts=tuple(
            sorted(
                (record for result in golden_results for record in result.retained_artifacts),
                key=lambda record: record.artifact_id,
            )
        ),
    )
    object.__setattr__(value, "_admission_guard", _ADMISSION_GUARD)
    return value


def _mint(cls: type, **fields: object):
    value = object.__new__(cls)
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    return value


def _reason_code(diagnostics: tuple[str, ...]) -> str:
    if diagnostics:
        candidate = diagnostics[0].partition(":")[0]
        if candidate:
            return candidate
    return "GOLDEN_ADMISSION_BLOCKED"


def _safe_generation_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise AcceptedExecutionError("generation_id must be a non-empty string")
    if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise AcceptedExecutionError("generation_id must be a safe single segment")
    return value


__all__ = [
    "AcceptedExecutionError",
    "AcceptedExecutionGate",
    "BlockedRun",
    "admit_accepted_execution",
]
