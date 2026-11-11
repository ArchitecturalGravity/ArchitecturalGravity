"""Singular terminal finalization for accepted runtime execution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import json

from AgMark.shared.runtime.artifacts import (
    AcceptedArtifactIndex,
    ArtifactRecord,
    BlockedEvidenceRole,
    FilesystemArtifactStore,
    publish_accepted_artifact_index,
    publish_blocked_artifact_manifest,
)

from .admission import AcceptedExecutionError, AcceptedExecutionGate, BlockedRun
from .execution import TreatmentExecutionResult
from .scoring import ScoringLifecycleResult


_FINALIZATION_GUARD = object()


class RuntimeFinalizationError(AcceptedExecutionError):
    """Terminal runtime authority could not be published without contradiction."""


@dataclass(frozen=True, init=False, slots=True)
class AcceptedRun:
    """Finalized accepted authority for one exact accepted execution generation."""

    generation_id: str
    accepted_snapshot_id: str
    run_plan_id: str
    plan_sha256: str
    execution_boundary_fingerprint: str
    golden_observations: tuple[bytes, ...]
    treatment_observations: tuple[bytes, ...]
    score_artifacts: tuple[bytes, ...]
    artifact_index: AcceptedArtifactIndex
    run_outcome_bytes: bytes
    _guard: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by finalize_scored_run")

    def run_outcome(self) -> dict[str, object]:
        """Return a fresh decoded terminal outcome document."""

        self.revalidate()
        value = json.loads(self.run_outcome_bytes.decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeFinalizationError("accepted run outcome is not an object")
        return value

    def revalidate(self, artifact_store: FilesystemArtifactStore | None = None) -> None:
        """Recheck immutable accepted authority and optionally exact retained bytes."""

        if getattr(self, "_guard", None) is not _FINALIZATION_GUARD:
            raise RuntimeFinalizationError("accepted run authority is invalid")
        if type(self.artifact_index) is not AcceptedArtifactIndex:
            raise RuntimeFinalizationError("accepted artifact index authority changed")
        if self.artifact_index.generation_id != self.generation_id:
            raise RuntimeFinalizationError("accepted artifact index generation changed")

        try:
            document = json.loads(self.run_outcome_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeFinalizationError("accepted run outcome bytes are invalid") from exc
        if not isinstance(document, dict):
            raise RuntimeFinalizationError("accepted run outcome is not an object")
        if document.get("status") != "accepted":
            raise RuntimeFinalizationError("accepted run outcome status changed")
        if document.get("generation_id") != self.generation_id:
            raise RuntimeFinalizationError("accepted run generation changed")
        if document.get("accepted_snapshot_id") != self.accepted_snapshot_id:
            raise RuntimeFinalizationError("accepted run snapshot changed")
        if (
            document.get("execution_boundary_fingerprint")
            != self.execution_boundary_fingerprint
        ):
            raise RuntimeFinalizationError("accepted run execution boundary changed")
        run_plan = document.get("run_plan")
        if not isinstance(run_plan, dict):
            raise RuntimeFinalizationError("accepted run plan reference is invalid")
        if run_plan.get("artifact_id") != self.run_plan_id:
            raise RuntimeFinalizationError("accepted run plan identity changed")
        if run_plan.get("sha256") != self.plan_sha256:
            raise RuntimeFinalizationError("accepted run plan bytes changed")

        expected_index = self.artifact_index.to_run_outcome_field()
        if document.get("artifact_index") != expected_index:
            raise RuntimeFinalizationError(
                "accepted run outcome no longer matches published artifact authority"
            )
        if "blocked_manifest" in document:
            raise RuntimeFinalizationError(
                "accepted run outcome cannot carry blocked authority"
            )

        if artifact_store is not None:
            if type(artifact_store) is not FilesystemArtifactStore:
                raise TypeError("artifact_store must be FilesystemArtifactStore")
            for record in self.artifact_index.artifacts:
                artifact_store.revalidate(record)


def finalize_scored_run(
    *,
    gate: AcceptedExecutionGate,
    treatment_result: TreatmentExecutionResult,
    scoring_result: ScoringLifecycleResult,
    artifact_store: FilesystemArtifactStore,
) -> AcceptedRun | BlockedRun:
    """Publish exactly one terminal result from validated scoring/lifecycle authority.

    No caller-supplied terminal status, artifact list, persistence writer, or
    reporting object is accepted. Terminal authority is derived exclusively from
    the admitted execution gate, retained treatment evidence, and the validated
    scoring/lifecycle classification.
    """

    if type(gate) is not AcceptedExecutionGate:
        raise TypeError("gate must be AcceptedExecutionGate")
    if type(treatment_result) is not TreatmentExecutionResult:
        raise TypeError("treatment_result must be TreatmentExecutionResult")
    if type(scoring_result) is not ScoringLifecycleResult:
        raise TypeError("scoring_result must be ScoringLifecycleResult")
    if type(artifact_store) is not FilesystemArtifactStore:
        raise TypeError("artifact_store must be FilesystemArtifactStore")

    treatment_result.revalidate()
    scoring_result.revalidate(artifact_store)
    _require_same_execution(gate, treatment_result, scoring_result)

    records = _unique_records(
        (
            *gate.retained_plan_artifacts,
            *gate.retained_golden_artifacts,
            treatment_result.retained_runner_registration_artifact,
            *treatment_result.retained_observation_artifacts,
            *scoring_result.retained_score_artifacts,
            *scoring_result.retained_reporting_artifacts,
        )
    )
    candidate = scoring_result.terminal_candidate()
    expected_refs = [record.to_artifact_ref() for record in records]

    try:
        if scoring_result.classification == "accepted":
            if not scoring_result.lifecycle_outcome.valid:
                raise RuntimeFinalizationError(
                    "accepted classification requires valid lifecycle authority"
                )
            if candidate.get("artifact_index") != expected_refs:
                raise RuntimeFinalizationError(
                    "validated accepted candidate does not match retained runtime evidence"
                )
            index = publish_accepted_artifact_index(
                store=artifact_store,
                generation_id=scoring_result.generation_id,
                terminal_status="accepted",
                artifacts=records,
            )
            value = object.__new__(AcceptedRun)
            for name, item in (
                ("generation_id", scoring_result.generation_id),
                ("accepted_snapshot_id", scoring_result.accepted_snapshot_id),
                ("run_plan_id", scoring_result.run_plan_id),
                ("plan_sha256", scoring_result.plan_sha256),
                (
                    "execution_boundary_fingerprint",
                    scoring_result.execution_boundary_fingerprint,
                ),
                ("golden_observations", tuple(gate.golden_observations)),
                (
                    "treatment_observations",
                    tuple(treatment_result.observation_bytes),
                ),
                ("score_artifacts", tuple(scoring_result.score_bytes)),
                ("artifact_index", index),
                ("run_outcome_bytes", bytes(scoring_result.terminal_candidate_bytes)),
                ("_guard", _FINALIZATION_GUARD),
            ):
                object.__setattr__(value, name, item)
            value.revalidate(artifact_store)
            return value

        if scoring_result.classification != "blocked":
            raise RuntimeFinalizationError(
                "scoring lifecycle classification must be accepted or blocked"
            )

        blocked_candidate = candidate.get("blocked_manifest")
        if not isinstance(blocked_candidate, dict):
            raise RuntimeFinalizationError(
                "validated blocked candidate lacks blocked manifest authority"
            )
        if blocked_candidate.get("retained_diagnostics", []) != expected_refs:
            raise RuntimeFinalizationError(
                "validated blocked candidate does not match retained runtime evidence"
            )

        roles = _blocked_roles(records)
        manifest = publish_blocked_artifact_manifest(
            store=artifact_store,
            generation_id=scoring_result.generation_id,
            terminal_status="blocked",
            reason_code=scoring_result.reason_code or "runtime_blocked",
            diagnostics=scoring_result.diagnostics,
            evidence_roles=roles,
            retained_diagnostics=records,
        )
        value = object.__new__(BlockedRun)
        for name, item in (
            ("generation_id", scoring_result.generation_id),
            ("accepted_snapshot_id", scoring_result.accepted_snapshot_id),
            ("run_plan_id", scoring_result.run_plan_id),
            ("plan_sha256", scoring_result.plan_sha256),
            (
                "execution_boundary_fingerprint",
                scoring_result.execution_boundary_fingerprint,
            ),
            ("reason_code", scoring_result.reason_code or "runtime_blocked"),
            ("diagnostics", tuple(scoring_result.diagnostics)),
            ("golden_observations", tuple(gate.golden_observations)),
            (
                "treatment_observations",
                tuple(treatment_result.observations()),
            ),
            ("artifact_manifest", manifest),
        ):
            object.__setattr__(value, name, item)
        return value
    except RuntimeFinalizationError:
        raise
    except Exception as exc:
        raise RuntimeFinalizationError(
            "terminal runtime publication failed closed"
        ) from exc


def _require_same_execution(
    gate: AcceptedExecutionGate,
    treatment_result: TreatmentExecutionResult,
    scoring_result: ScoringLifecycleResult,
) -> None:
    expected = (
        gate.generation_id,
        gate.accepted_snapshot_id,
        gate.run_plan_id,
        gate.plan_sha256,
        gate.execution_boundary_fingerprint,
    )
    treatment = (
        treatment_result.generation_id,
        treatment_result.accepted_snapshot_id,
        treatment_result.run_plan_id,
        treatment_result.plan_sha256,
        treatment_result.execution_boundary_fingerprint,
    )
    scoring = (
        scoring_result.generation_id,
        scoring_result.accepted_snapshot_id,
        scoring_result.run_plan_id,
        scoring_result.plan_sha256,
        scoring_result.execution_boundary_fingerprint,
    )
    if treatment != expected:
        raise RuntimeFinalizationError(
            "treatment evidence does not match admitted execution authority"
        )
    if scoring != expected:
        raise RuntimeFinalizationError(
            "scoring evidence does not match admitted execution authority"
        )


def _unique_records(values: Sequence[ArtifactRecord]) -> tuple[ArtifactRecord, ...]:
    records: dict[str, ArtifactRecord] = {}
    references: set[str] = set()
    for record in values:
        if type(record) is not ArtifactRecord:
            raise RuntimeFinalizationError(
                "terminal runtime evidence contains an invalid artifact record"
            )
        previous = records.get(record.artifact_id)
        if previous is not None and previous != record:
            raise RuntimeFinalizationError(
                "terminal runtime artifact identity is ambiguous"
            )
        if record.reference in references and (
            previous is None or previous.reference != record.reference
        ):
            raise RuntimeFinalizationError(
                "terminal runtime artifact reference is ambiguous"
            )
        records[record.artifact_id] = record
        references.add(record.reference)
    return tuple(sorted(records.values(), key=lambda record: record.artifact_id))


def _blocked_roles(
    records: tuple[ArtifactRecord, ...],
) -> tuple[BlockedEvidenceRole, ...]:
    retained_roles = sorted({record.role for record in records})
    roles = [
        BlockedEvidenceRole(
            role=role,
            availability="retained",
            reason="retained exact evidence from started blocked execution",
        )
        for role in retained_roles
    ]
    if "score_artifact" not in retained_roles:
        roles.append(
            BlockedEvidenceRole(
                role="score_artifact",
                availability="not_produced",
                reason="registered scoring did not establish retained score authority",
            )
        )
    roles.append(
        BlockedEvidenceRole(
            role="accepted_artifact_index",
            availability="not_produced",
            reason="blocked finalization cannot create accepted artifact authority",
        )
    )
    return tuple(roles)


__all__ = [
    "AcceptedRun",
    "RuntimeFinalizationError",
    "finalize_scored_run",
]
