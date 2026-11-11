"""Unscored terminal execution; never grants scored/report/verification authority."""
from dataclasses import dataclass
from AgMark.shared.runtime.artifacts import ArtifactRecord
from .admission import AcceptedExecutionGate
from .execution import TreatmentExecutionResult
from .planning import AcceptedRunSnapshot

EXECUTION_ONLY = "arcgrav.runtime:execution-only"


@dataclass(frozen=True)
class ExecutionArtifactIndex:
    generation_id: str
    artifacts: tuple[ArtifactRecord, ...]


_GUARD = object()


@dataclass(frozen=True, init=False)
class ExecutedRun:
    generation_id: str
    accepted_snapshot_id: str
    run_plan_id: str
    plan_sha256: str
    execution_boundary_fingerprint: str
    treatment_observations: tuple[bytes, ...]
    artifact_index: ExecutionArtifactIndex
    cancelled: bool = False
    golden_observations: tuple = ()
    score_artifacts: tuple = ()

    def __init__(self, *args, **kwargs):
        raise TypeError("created only by finalize_unscored_run")

    def revalidate(self, artifact_store=None):
        if getattr(self, "_guard", None) is not _GUARD:
            raise ValueError("Unscored execution result is invalid")
        if self.artifact_index.generation_id != self.generation_id:
            raise ValueError("Execution generation differs")
        if self.score_artifacts or self.golden_observations:
            raise ValueError("Unscored execution cannot contain score or golden artifacts")
        if artifact_store is not None:
            for record in self.artifact_index.artifacts:
                artifact_store.revalidate(record)


def finalize_unscored_run(*, gate, snapshot, treatment_result, artifact_store, cancelled=False):
    if type(gate) is not AcceptedExecutionGate or type(snapshot) is not AcceptedRunSnapshot or type(treatment_result) is not TreatmentExecutionResult:
        raise TypeError("Unscored finalization requires planned treatment execution")
    plan = snapshot.plan()
    if plan.to_dict().get("extensions", {}).get(EXECUTION_ONLY) is not True or plan.golden_required:
        raise ValueError("Plan does not authorize unscored execution")
    gate.revalidate()
    treatment_result.revalidate()
    for name in ("generation_id", "accepted_snapshot_id", "run_plan_id", "plan_sha256", "execution_boundary_fingerprint"):
        if getattr(gate, name) != getattr(treatment_result, name):
            raise ValueError("Treatment result differs from admitted execution")
    records = (treatment_result.retained_runner_registration_artifact, *treatment_result.retained_observation_artifacts)
    expected_ids = tuple(o.observation_id for o in plan.observations)
    observed_ids = treatment_result.observation_ids
    if observed_ids != expected_ids and not (cancelled and observed_ids == expected_ids[:len(observed_ids)]):
        raise ValueError("Unscored observations do not reconcile with the plan")
    run = object.__new__(ExecutedRun)
    for name in ("generation_id", "accepted_snapshot_id", "run_plan_id", "plan_sha256", "execution_boundary_fingerprint"):
        object.__setattr__(run, name, getattr(gate, name))
    for name, value in (("treatment_observations", treatment_result.observation_bytes),
                        ("artifact_index", ExecutionArtifactIndex(gate.generation_id, records)),
                        ("cancelled", cancelled), ("golden_observations", ()),
                        ("score_artifacts", ()), ("_guard", _GUARD)):
        object.__setattr__(run, name, value)
    run.revalidate(artifact_store)
    artifact_store.claim_terminal_status(run.generation_id, "executed")
    return run
