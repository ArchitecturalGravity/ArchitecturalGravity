"""Public benchmark-neutral runtime orchestration authority."""

from .unscored import ExecutedRun, EXECUTION_ONLY, finalize_unscored_run

from .admission import (
    AcceptedExecutionError,
    AcceptedExecutionGate,
    BlockedRun,
    admit_accepted_execution,
)
from .execution import (
    RUNNER_INVOCATION_CONTRACT_ID,
    RUNNER_INVOCATION_CONTRACT_VERSION,
    TREATMENT_OBSERVATION_SCHEMA_ID,
    TREATMENT_OBSERVATION_SCHEMA_VERSION,
    TreatmentCaseInput,
    TreatmentExecutionError,
    TreatmentExecutionResult,
    TreatmentPrompt,
    execute_planned_treatments,
)
from .scoring import (
    AcceptedScoringError,
    RegisteredScoringDefinition,
    SCORER_ENTRY_POINT_EXTENSION,
    ScoringLifecycleResult,
    score_accepted_treatments,
)
from .finalization import (
    AcceptedRun,
    RuntimeFinalizationError,
    finalize_scored_run,
)
from .planning import (
    AcceptedRunSnapshot,
    AcceptedSnapshotIntegrityError,
    DuplicatePlanIdentityError,
    IncompletePlanError,
    PlanIntegrityError,
    PlannedCaseInput,
    PlannedObservation,
    PlanningError,
    RUN_LIFECYCLE_CONTRACT_ID,
    RUN_LIFECYCLE_CONTRACT_VERSION,
    RUN_PLAN_SCHEMA_ID,
    RUN_PLAN_SCHEMA_VERSION,
    RunPlan,
    accept_run_plan,
    plan_run,
)

__all__ = [
    "AcceptedExecutionError",
    "AcceptedExecutionGate",
    "AcceptedRun",
    "AcceptedRunSnapshot",
    "AcceptedScoringError",
    "AcceptedSnapshotIntegrityError",
    "BlockedRun",
    "DuplicatePlanIdentityError",
    "IncompletePlanError",
    "PlanIntegrityError",
    "PlannedCaseInput",
    "PlannedObservation",
    "PlanningError",
    "RUNNER_INVOCATION_CONTRACT_ID",
    "RUNNER_INVOCATION_CONTRACT_VERSION",
    "RegisteredScoringDefinition",
    "RUN_LIFECYCLE_CONTRACT_ID",
    "RUN_LIFECYCLE_CONTRACT_VERSION",
    "RUN_PLAN_SCHEMA_ID",
    "RUN_PLAN_SCHEMA_VERSION",
    "RunPlan",
    "RuntimeFinalizationError",
    "SCORER_ENTRY_POINT_EXTENSION",
    "ScoringLifecycleResult",
    "TREATMENT_OBSERVATION_SCHEMA_ID",
    "TREATMENT_OBSERVATION_SCHEMA_VERSION",
    "TreatmentCaseInput",
    "TreatmentExecutionError",
    "TreatmentExecutionResult",
    "TreatmentPrompt",
    "accept_run_plan",
    "admit_accepted_execution",
    "execute_planned_treatments",
    "finalize_scored_run",
    "plan_run",
    "score_accepted_treatments",
]
