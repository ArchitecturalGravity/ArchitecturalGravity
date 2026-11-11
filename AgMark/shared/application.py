"""Coarse shared application boundary over benchmark-neutral lifecycle authority.

This module exposes registration-driven discovery, canonical planning,
acceptance, accepted execution, exact terminal-run retention and deletion, and
automatic validated report completion. Frontends never sequence lower-level
lifecycle stages.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from AgMark.shared.evaluation.scoring import IdentityRef as ReportingIdentityRef
from AgMark.shared.reporting import (
    CaseResultEntry,
    GeneratedReportBundle,
    ObservationCounts,
    ObservationMatrixEntry,
    RegisteredReportMetric,
    ReportArtifactRef,
    ReportSection,
    TreatmentSummary,
    admit_finalized_run_for_reporting,
    build_canonical_report_model,
    generate_report_bundle,
)
from AgMark.shared.runtime.artifacts import FilesystemArtifactStore
from AgMark.shared.runtime.golden import GoldenCaseInput, GoldenDeclaration
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef
from AgMark.shared.runtime.orchestration import (
    AcceptedExecutionGate,
    AcceptedRun, ExecutedRun, EXECUTION_ONLY, finalize_unscored_run,
    AcceptedRunSnapshot,
    BlockedRun,
    PlannedCaseInput,
    RegisteredScoringDefinition,
    RunPlan,
    TreatmentCaseInput,
    TreatmentPrompt,
    accept_run_plan,
    admit_accepted_execution,
    execute_planned_treatments,
    finalize_scored_run,
    plan_run,
    score_accepted_treatments,
)
from AgMark.shared.validation import (
    BenchmarkDiscoveryCandidate,
    RegistrationValidationOutcome,
    validate_benchmark_discovery,
)


class ApplicationDiscoveryError(ValueError):
    """Raised when explicit registrations cannot authorize discovery."""


class ApplicationPlanningError(ValueError):
    """Raised when an application planning request lacks discovered authority."""


class ApplicationExecutionError(ValueError):
    """Raised when a coarse accepted-execution request cannot proceed."""


class ApplicationReportingError(ValueError):
    """Raised when automatic report completion cannot proceed."""


class ApplicationRetentionError(ValueError):
    """Raised when retained-generation management cannot proceed safely."""


class ApplicationAcceptanceError(ApplicationPlanningError):
    """Raised when a prepared plan cannot cross the shared acceptance boundary."""


ApplicationPrerequisiteOperation = Literal["planning", "acceptance", "execution"]
_PREREQUISITE_OPERATIONS = frozenset(("planning", "acceptance", "execution"))


@dataclass(frozen=True, slots=True)
class ApplicationPrerequisiteState:
    """One benchmark-neutral prerequisite at its earliest material transition."""

    prerequisite_id: str
    operation: ApplicationPrerequisiteOperation
    satisfied: bool
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.prerequisite_id, str) or not self.prerequisite_id.strip():
            raise ValueError("prerequisite_id must be a non-empty string")
        if self.operation not in _PREREQUISITE_OPERATIONS:
            raise ValueError(
                "operation must be one of planning, acceptance, or execution"
            )
        if type(self.satisfied) is not bool:
            raise TypeError("satisfied must be a boolean")
        if self.diagnostic is not None and (
            not isinstance(self.diagnostic, str) or not self.diagnostic.strip()
        ):
            raise ValueError("diagnostic must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class ApplicationPrerequisiteProjection:
    """Immutable operation-specific prerequisite state for one application session."""

    planning: Sequence[ApplicationPrerequisiteState] = ()
    acceptance: Sequence[ApplicationPrerequisiteState] = ()
    execution: Sequence[ApplicationPrerequisiteState] = ()

    def __post_init__(self) -> None:
        buckets = (
            ("planning", self.planning),
            ("acceptance", self.acceptance),
            ("execution", self.execution),
        )
        seen: set[str] = set()
        for operation, values in buckets:
            if isinstance(values, (str, bytes, bytearray)) or not isinstance(
                values, Sequence
            ):
                raise TypeError(f"{operation} prerequisites must be a sequence")
            normalized = tuple(values)
            for item in normalized:
                if type(item) is not ApplicationPrerequisiteState:
                    raise TypeError(
                        f"{operation} prerequisites must contain "
                        "ApplicationPrerequisiteState values"
                    )
                if item.operation != operation:
                    raise ValueError(
                        f"{item.prerequisite_id!r} is scoped to {item.operation!r}, "
                        f"not {operation!r}"
                    )
                if item.prerequisite_id in seen:
                    raise ValueError(
                        f"prerequisite identity {item.prerequisite_id!r} is duplicated"
                    )
                seen.add(item.prerequisite_id)
            object.__setattr__(self, operation, normalized)

    @classmethod
    def from_states(
        cls,
        states: Sequence[ApplicationPrerequisiteState],
    ) -> "ApplicationPrerequisiteProjection":
        if isinstance(states, (str, bytes, bytearray)) or not isinstance(
            states, Sequence
        ):
            raise TypeError("states must be a sequence")
        grouped: dict[str, list[ApplicationPrerequisiteState]] = {
            "planning": [],
            "acceptance": [],
            "execution": [],
        }
        for state in states:
            if type(state) is not ApplicationPrerequisiteState:
                raise TypeError("states must contain ApplicationPrerequisiteState values")
            grouped[state.operation].append(state)
        return cls(
            planning=tuple(grouped["planning"]),
            acceptance=tuple(grouped["acceptance"]),
            execution=tuple(grouped["execution"]),
        )

    def for_operation(
        self,
        operation: ApplicationPrerequisiteOperation,
    ) -> tuple[ApplicationPrerequisiteState, ...]:
        if operation not in _PREREQUISITE_OPERATIONS:
            raise ValueError(
                "operation must be one of planning, acceptance, or execution"
            )
        return tuple(getattr(self, operation))

    def unresolved_for(
        self,
        operation: ApplicationPrerequisiteOperation,
    ) -> tuple[ApplicationPrerequisiteState, ...]:
        return tuple(
            state for state in self.for_operation(operation) if not state.satisfied
        )

    def ready_for(self, operation: ApplicationPrerequisiteOperation) -> bool:
        return not self.unresolved_for(operation)


@dataclass(frozen=True, slots=True)
class ApplicationRegistrationSource:
    """One explicitly supplied, previously validated non-benchmark registration."""

    registration_source_id: str
    registration: Mapping[str, Any]
    registration_validation: RegistrationValidationOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.registration_source_id, str) or not self.registration_source_id:
            raise ValueError("registration_source_id must be a non-empty string")
        if not isinstance(self.registration, Mapping):
            raise TypeError("registration must be a mapping")
        if type(self.registration_validation) is not RegistrationValidationOutcome:
            raise TypeError(
                "registration_validation must be a RegistrationValidationOutcome"
            )


@dataclass(frozen=True, slots=True)
class DiscoveredRegistration:
    """Exact immutable registration identity projected by application discovery."""

    registration_id: str
    registration_version: str
    registration_kind: str
    registration_sha256: str
    registration_source_id: str
    capabilities: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ApplicationDiscovery:
    """Registration-driven benchmark and runner discovery result."""

    benchmarks: tuple[DiscoveredRegistration, ...]
    runners: tuple[DiscoveredRegistration, ...]


@dataclass(frozen=True, slots=True)
class ApplicationPlanRequest:
    """Resolved benchmark-neutral inputs for one canonical plan request.

    This value is not accepted authority.  `PlanningApplicationSession` checks
    that the selected benchmark and runner were discovered from exact validated
    registrations before delegating canonical materialization to `plan_run`.
    """

    benchmark: IdentityRef | Mapping[str, object]
    case_set: IdentityRef | Mapping[str, object]
    treatment_set: IdentityRef | Mapping[str, object]
    cases: Sequence[PlannedCaseInput]
    treatments: Sequence[str]
    repetitions: int
    execution_boundary: ExecutionBoundary
    golden_required: bool
    contracts: Sequence[IdentityRef | Mapping[str, object]] = ()
    extensions: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.execution_boundary) is not ExecutionBoundary:
            raise TypeError("execution_boundary must be an ExecutionBoundary")
        if isinstance(self.cases, (str, bytes)):
            raise TypeError("cases must be a sequence of PlannedCaseInput values")
        if isinstance(self.treatments, (str, bytes)):
            raise TypeError("treatments must be a sequence of treatment identities")
        if isinstance(self.contracts, (str, bytes)):
            raise TypeError("contracts must be a sequence of identity references")
        if not isinstance(self.extensions, Mapping):
            raise TypeError("extensions must be a mapping")
        object.__setattr__(self, "cases", tuple(self.cases))
        object.__setattr__(self, "treatments", tuple(self.treatments))
        object.__setattr__(self, "contracts", tuple(self.contracts))
        object.__setattr__(self, "extensions", MappingProxyType(dict(self.extensions)))


@dataclass(frozen=True, slots=True)
class ApplicationExecutionRequest:
    """Resolved inputs for one accepted execution generation.

    The request carries invocation material only. Lifecycle sequencing and
    terminal classification remain owned by shared runtime orchestration.
    Transient values are passed only to their declared golden or runner invocation
    boundary and are not retained by the application session.
    """

    generation_id: str
    benchmark: IdentityRef | Mapping[str, object]
    case_set: IdentityRef | Mapping[str, object]
    treatment_set: IdentityRef | Mapping[str, object]
    execution_boundary: ExecutionBoundary
    benchmark_root: str | Path
    artifact_store: FilesystemArtifactStore
    repository_root: str | Path
    runner_registration: Mapping[str, object]
    case_inputs: Sequence[TreatmentCaseInput]
    treatment_prompts: Sequence[TreatmentPrompt]
    scoring_definitions: Sequence[RegisteredScoringDefinition]
    golden_declaration: GoldenDeclaration | None = None
    golden_case_inputs: Sequence[GoldenCaseInput] = ()
    transient_values: Mapping[str, str] | None = field(default=None, repr=False)
    runner_transient_values: Mapping[str, str] | None = field(default=None, repr=False)
    runner_launch_selection: Mapping[str, str] | None = field(default=None, repr=False, compare=False)
    live_view_callback: Callable[[Mapping[str, object]], None] | None = field(default=None, repr=False, compare=False)
    replay_capture_options: Mapping[str, object] | None = field(default=None, repr=False, compare=False)
    activity_callback: Callable[[object], None] | None = field(default=None, repr=False, compare=False)
    live_view_control: object | None = field(default=None, repr=False, compare=False)
    cancellation_requested: Callable[[], bool] | None = field(default=None, repr=False, compare=False)
    report_request_factory: Callable[[AcceptedRun], ApplicationReportRequest] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.report_request_factory is not None and not callable(self.report_request_factory):
            raise TypeError("report_request_factory must be callable or None")
        if self.live_view_control is not None:
            from .adapters.execution.live_view import LiveViewControl
            if not isinstance(self.live_view_control, LiveViewControl):
                raise TypeError("live_view_control must be LiveViewControl or None")
        if not isinstance(self.generation_id, str) or not self.generation_id:
            raise ValueError("generation_id must be a non-empty string")
        if self.activity_callback is not None and not callable(self.activity_callback):
            raise TypeError("activity_callback must be callable or None")
        if self.live_view_callback is not None and not callable(self.live_view_callback):
            raise TypeError("live_view_callback must be callable or None")
        if type(self.execution_boundary) is not ExecutionBoundary:
            raise TypeError("execution_boundary must be an ExecutionBoundary")
        if type(self.artifact_store) is not FilesystemArtifactStore:
            raise TypeError("artifact_store must be a FilesystemArtifactStore")
        if not isinstance(self.benchmark_root, (str, Path)):
            raise TypeError("benchmark_root must be a string or Path")
        if not isinstance(self.repository_root, (str, Path)):
            raise TypeError("repository_root must be a string or Path")
        if not isinstance(self.runner_registration, Mapping):
            raise TypeError("runner_registration must be a mapping")
        if isinstance(self.case_inputs, (str, bytes, bytearray)):
            raise TypeError("case_inputs must be a sequence")
        if isinstance(self.treatment_prompts, (str, bytes, bytearray)):
            raise TypeError("treatment_prompts must be a sequence")
        if isinstance(self.scoring_definitions, (str, bytes, bytearray)):
            raise TypeError("scoring_definitions must be a sequence")
        if isinstance(self.golden_case_inputs, (str, bytes, bytearray)):
            raise TypeError("golden_case_inputs must be a sequence")
        if self.golden_declaration is not None and type(self.golden_declaration) is not GoldenDeclaration:
            raise TypeError("golden_declaration must be GoldenDeclaration or None")
        for value, name in (
            (self.transient_values, "transient_values"),
            (self.runner_transient_values, "runner_transient_values"),
        ):
            if value is None:
                continue
            if not isinstance(value, Mapping):
                raise TypeError(f"{name} must be a mapping or None")
            if any(
                not isinstance(key, str) or not isinstance(item, str)
                for key, item in value.items()
            ):
                raise TypeError(f"{name} must contain only string keys and values")
        object.__setattr__(self, "case_inputs", tuple(self.case_inputs))
        object.__setattr__(self, "treatment_prompts", tuple(self.treatment_prompts))
        object.__setattr__(self, "scoring_definitions", tuple(self.scoring_definitions))
        object.__setattr__(self, "golden_case_inputs", tuple(self.golden_case_inputs))


@dataclass(frozen=True, slots=True)
class ApplicationReportRequest:
    """Resolved benchmark-neutral inputs for one report-generation operation."""

    generation_id: str
    execution_boundary: ReportArtifactRef
    benchmark: ReportingIdentityRef
    case_set: ReportingIdentityRef
    treatment_set: ReportingIdentityRef
    comparison_track_id: str
    primary_endpoint: ReportingIdentityRef
    metrics: Sequence[RegisteredReportMetric]
    observation_counts: ObservationCounts
    observation_matrix: Sequence[ObservationMatrixEntry]
    case_result_matrix: Sequence[CaseResultEntry]
    treatment_summaries: Sequence[TreatmentSummary]
    report_id: str
    report_version: str
    status: str
    sections: Mapping[str, ReportSection]
    report_manifest_id: str
    generated_at: str
    input_evidence_set_id: str
    generator: ReportingIdentityRef
    procedure_id: str
    procedure_version: str
    command_or_procedure: str
    report_reference: str
    canonical_evidence_reference: str
    human_reference: str
    manifest_reference: str
    extensions: Mapping[str, object] = field(default_factory=dict)
    extension_evaluator: Callable[..., Mapping[str, object]] | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.generation_id, "generation_id"),
            (self.comparison_track_id, "comparison_track_id"),
            (self.report_id, "report_id"),
            (self.report_version, "report_version"),
            (self.status, "status"),
            (self.report_manifest_id, "report_manifest_id"),
            (self.generated_at, "generated_at"),
            (self.input_evidence_set_id, "input_evidence_set_id"),
            (self.procedure_id, "procedure_id"),
            (self.procedure_version, "procedure_version"),
            (self.command_or_procedure, "command_or_procedure"),
            (self.report_reference, "report_reference"),
            (self.canonical_evidence_reference, "canonical_evidence_reference"),
            (self.human_reference, "human_reference"),
            (self.manifest_reference, "manifest_reference"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if type(self.execution_boundary) is not ReportArtifactRef:
            raise TypeError("execution_boundary must be ReportArtifactRef")
        for value, name in (
            (self.benchmark, "benchmark"),
            (self.case_set, "case_set"),
            (self.treatment_set, "treatment_set"),
            (self.primary_endpoint, "primary_endpoint"),
            (self.generator, "generator"),
        ):
            if type(value) is not ReportingIdentityRef:
                raise TypeError(f"{name} must be reporting IdentityRef")
        if type(self.observation_counts) is not ObservationCounts:
            raise TypeError("observation_counts must be ObservationCounts")
        for value, name in (
            (self.metrics, "metrics"),
            (self.observation_matrix, "observation_matrix"),
            (self.case_result_matrix, "case_result_matrix"),
            (self.treatment_summaries, "treatment_summaries"),
        ):
            if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
                raise TypeError(f"{name} must be a sequence")
        if not isinstance(self.sections, Mapping):
            raise TypeError("sections must be a mapping")
        if self.extension_evaluator is not None and not callable(self.extension_evaluator):
            raise TypeError("extension_evaluator must be callable")
        if not isinstance(self.extensions, Mapping):
            raise TypeError("extensions must be a mapping")
        object.__setattr__(self, "metrics", tuple(self.metrics))
        object.__setattr__(self, "observation_matrix", tuple(self.observation_matrix))
        object.__setattr__(self, "case_result_matrix", tuple(self.case_result_matrix))
        object.__setattr__(self, "treatment_summaries", tuple(self.treatment_summaries))
        object.__setattr__(self, "sections", MappingProxyType(dict(self.sections)))
        object.__setattr__(self, "extensions", MappingProxyType(dict(self.extensions)))


@dataclass(frozen=True, slots=True)
class _RetainedTerminalRun:
    outcome: AcceptedRun | BlockedRun
    artifact_store: FilesystemArtifactStore


@dataclass(frozen=True, slots=True)
class _RetainedGeneratedReport:
    generation_id: str
    bundle: GeneratedReportBundle


@dataclass(frozen=True, slots=True)
class ApplicationRunDeletion:
    """Exact retained-generation identity removed by application authority."""

    generation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.generation_id, str) or not self.generation_id:
            raise ValueError("generation_id must be a non-empty string")


class PlanningApplicationSession:
    """Public application session through planning, acceptance, and terminal execution."""

    def __init__(
        self,
        *,
        benchmark_candidates: Sequence[BenchmarkDiscoveryCandidate],
        runner_sources: Sequence[ApplicationRegistrationSource],
        prerequisite_projection: ApplicationPrerequisiteProjection | None = None,
    ) -> None:
        if isinstance(benchmark_candidates, (str, bytes)):
            raise TypeError("benchmark_candidates must be a sequence")
        if isinstance(runner_sources, (str, bytes)):
            raise TypeError("runner_sources must be a sequence")
        if prerequisite_projection is None:
            prerequisite_projection = ApplicationPrerequisiteProjection()
        if type(prerequisite_projection) is not ApplicationPrerequisiteProjection:
            raise TypeError(
                "prerequisite_projection must be an ApplicationPrerequisiteProjection"
            )
        self._benchmark_candidates = tuple(benchmark_candidates)
        self._prerequisite_projection = prerequisite_projection
        self._runner_sources = tuple(runner_sources)
        self._prepared_plan: RunPlan | None = None
        self._prepared_boundary: ExecutionBoundary | None = None
        self._accepted_snapshot: AcceptedRunSnapshot | None = None
        self._attempted_generation_ids: set[str] = set()
        self._retained_runs: dict[str, _RetainedTerminalRun] = {}
        self._generated_reports: dict[str, _RetainedGeneratedReport] = {}
        self._selected_run_id: str | None = None
        self._validation_diagnostics: dict[str, str] = {}
        self._completion_records: dict[str, Mapping[str, object]] = {}
        self._completed_reports: dict[str, GeneratedReportBundle] = {}

    @property
    def prepared_plan(self) -> RunPlan | None:
        return self._prepared_plan

    @property
    def accepted_snapshot(self) -> AcceptedRunSnapshot | None:
        return self._accepted_snapshot

    @property
    def retained_run_ids(self) -> tuple[str, ...]:
        return tuple(self._retained_runs)

    @property
    def selected_run_id(self) -> str | None:
        return self._selected_run_id

    @property
    def prerequisite_projection(self) -> ApplicationPrerequisiteProjection:
        return self._prerequisite_projection

    def set_prerequisite_projection(
        self,
        projection: ApplicationPrerequisiteProjection,
    ) -> None:
        """Replace current readiness evidence without mutating lifecycle authority."""

        if type(projection) is not ApplicationPrerequisiteProjection:
            raise TypeError(
                "projection must be an ApplicationPrerequisiteProjection"
            )
        self._prerequisite_projection = projection

    def discover(self) -> ApplicationDiscovery:
        return discover_application_authority(
            benchmark_candidates=self._benchmark_candidates,
            runner_sources=self._runner_sources,
        )

    def build_plan(self, request: ApplicationPlanRequest) -> RunPlan:
        if not isinstance(request, ApplicationPlanRequest):
            raise TypeError("request must be an ApplicationPlanRequest")
        self._require_prerequisites("planning")

        discovery = self.discover()
        benchmark = IdentityRef.from_value(request.benchmark, field="benchmark")
        _require_discovered_benchmark(benchmark, discovery.benchmarks)
        _require_discovered_runner(request.execution_boundary, discovery.runners)
        from .telemetry.runtime_reference import PLAN_EXTENSION, build_runtime_advisory
        boundary_document = request.execution_boundary.to_dict()
        selected_runner = boundary_document["runner"]
        runner_source = next(source for source in self._runner_sources
            if source.registration["registration_id"] == selected_runner["id"]
            and source.registration["registration_version"] == selected_runner["version"])
        extensions = dict(request.extensions)
        # This advisory comes only from the exact discovered registration and
        # selected runtime. A caller cannot forge or suppress its retained basis.
        extensions.pop(PLAN_EXTENSION, None)
        advisory = build_runtime_advisory(runner_source.registration, boundary_document["provider_runtime"])
        if advisory is not None:
            extensions[PLAN_EXTENSION] = advisory
        from .treatments import POLICY, content_entries
        for candidate in self._benchmark_candidates:
            registration = candidate.registration
            if registration.get("registration_id") != benchmark.id or registration.get("registration_version") != benchmark.version:
                continue
            policy = registration.get("extensions", {}).get(POLICY, {})
            if policy.get("mismatch") == "contaminated":
                entries = content_entries({"extensions": dict(request.extensions)})
                if {e["treatment_id"] for e in entries} != set(request.treatments):
                    raise ApplicationPlanningError("registered treatments require frozen content identities")
                prompts = [a for a in registration["implementation_artifacts"] if a["artifact_id"] in policy["prompt_artifacts"].values()]
                for entry in entries:
                    expected = entry["expected"]
                    if not any(a["artifact_id"] == policy["prompt_artifacts"].get(entry["treatment_id"]) and a["reference"] == candidate.package_root + "/" + expected["reference"] and a["sha256"] == expected["sha256"] for a in prompts):
                        raise ApplicationPlanningError("expected treatment content is not registered")

        plan = plan_run(
            benchmark=request.benchmark,
            case_set=request.case_set,
            treatment_set=request.treatment_set,
            cases=request.cases,
            treatments=request.treatments,
            repetitions=request.repetitions,
            execution_boundary=request.execution_boundary,
            golden_required=request.golden_required,
            contracts=request.contracts,
            extensions=extensions,
        )
        self._prepared_plan = plan
        self._prepared_boundary = request.execution_boundary
        self._accepted_snapshot = None
        return plan

    def accept_plan(self) -> AcceptedRunSnapshot:
        if self._accepted_snapshot is not None:
            raise ApplicationPlanningError(
                "the current application plan has already been accepted"
            )
        if self._prepared_plan is None or self._prepared_boundary is None:
            raise ApplicationPlanningError("no canonical plan is prepared for acceptance")
        self._require_prerequisites("acceptance")
        snapshot = accept_run_plan(
            plan=self._prepared_plan,
            execution_boundary=self._prepared_boundary,
        )
        self._accepted_snapshot = snapshot
        return snapshot

    def execute_accepted_run(
        self,
        request: ApplicationExecutionRequest,
    ) -> AcceptedRun | BlockedRun:
        """Own accepted lifecycle sequencing and return one exact terminal result."""

        if not isinstance(request, ApplicationExecutionRequest):
            raise TypeError("request must be an ApplicationExecutionRequest")
        snapshot = self._accepted_snapshot
        if snapshot is None:
            raise ApplicationExecutionError(
                "no accepted snapshot exists for accepted execution"
            )
        if (
            request.generation_id in self._attempted_generation_ids
            or request.generation_id in self._retained_runs
        ):
            raise ApplicationExecutionError(
                "the requested execution generation has already been attempted"
            )
        accepted_extensions = snapshot.plan().to_dict().get("extensions", {})
        run_cache_replays = accepted_extensions.get("arcgrav.runtime:cache-validation-replays", True)
        execution_only = accepted_extensions.get(EXECUTION_ONLY) is True
        if type(run_cache_replays) is not bool:
            raise ApplicationExecutionError("accepted cache validation replay policy must be boolean")
        if execution_only:
            if request.scoring_definitions or request.golden_declaration is not None:
                raise ApplicationExecutionError("Unscored execution cannot select scoring or golden authority")
        self._require_prerequisites("execution")

        from .runtime.orchestration.activity import ActivityPublisher, benchmark_outcome_from_observations
        activity = ActivityPublisher(request.generation_id, request.activity_callback,
                                     persistence_root=request.artifact_store.root)
        activity.emit("admission")
        try:
            gate = admit_accepted_execution(
                generation_id=request.generation_id,
                snapshot=snapshot,
                benchmark=request.benchmark,
                case_set=request.case_set,
                treatment_set=request.treatment_set,
                execution_boundary=request.execution_boundary,
                benchmark_root=request.benchmark_root,
                artifact_store=request.artifact_store,
                golden_declaration=request.golden_declaration,
                golden_case_inputs=request.golden_case_inputs,
                transient_values=request.transient_values,
            )
        except BaseException:
            activity.finish("cancelled" if bool(request.cancellation_requested and request.cancellation_requested()) else "failed")
            raise
        if type(gate) is BlockedRun:
            retained = self._retain_terminal_run(gate, request.artifact_store)
            activity.finish("blocked")
            self._complete_run(retained, request)
            return retained
        if type(gate) is not AcceptedExecutionGate:
            activity.finish("failed")
            raise ApplicationExecutionError(
                "accepted execution admission returned invalid shared authority"
            )

        self._attempted_generation_ids.add(gate.generation_id)
        from .validation.codex_cache.startup import StartupCollector
        from .adapters.execution.orchestration import observe_invocation_startup
        from .runtime.orchestration.replay import supports_validation_replay
        capture_startup = run_cache_replays and supports_validation_replay(request.runner_registration)
        startup = None
        progress_outcome = "failed"
        progress_finalized = False
        retained = None
        try:
            startup = StartupCollector() if capture_startup else None
            activity.emit("execution")
            with activity.bind(), (observe_invocation_startup(startup) if capture_startup else nullcontext()):
                treatment = execute_planned_treatments(
                    gate=gate,
                    snapshot=snapshot,
                    benchmark=request.benchmark,
                    case_set=request.case_set,
                    treatment_set=request.treatment_set,
                    execution_boundary=request.execution_boundary,
                    artifact_store=request.artifact_store,
                    repository_root=request.repository_root,
                    runner_registration=request.runner_registration,
                    case_inputs=request.case_inputs,
                    treatment_prompts=request.treatment_prompts,
                    runner_transient_values=request.runner_transient_values,
                    runner_launch_selection=request.runner_launch_selection,
                    live_view_callback=request.live_view_callback,
                    live_view_control=request.live_view_control,
                    cancellation_requested=request.cancellation_requested,
                )
            if execution_only:
                activity.emit("finalization")
                terminal = finalize_unscored_run(gate=gate, snapshot=snapshot,
                    treatment_result=treatment, artifact_store=request.artifact_store,
                    cancelled=bool(request.cancellation_requested and request.cancellation_requested()))
            else:
                activity.emit("evaluation")
                scoring = score_accepted_treatments(
                    gate=gate,
                    snapshot=snapshot,
                    benchmark=request.benchmark,
                    case_set=request.case_set,
                    treatment_set=request.treatment_set,
                    execution_boundary=request.execution_boundary,
                    treatment_result=treatment,
                    artifact_store=request.artifact_store,
                    scoring_definitions=request.scoring_definitions,
                )
                activity.emit("finalization")
                terminal = finalize_scored_run(
                    gate=gate,
                    treatment_result=treatment,
                    scoring_result=scoring,
                    artifact_store=request.artifact_store,
                )
            retained = self._retain_terminal_run(terminal, request.artifact_store)
            progress_outcome = benchmark_outcome_from_observations(
                getattr(retained, "treatment_observations", ()),
                cancelled=bool(getattr(retained, "cancelled", False) or request.cancellation_requested and request.cancellation_requested()),
                blocked=type(retained) is BlockedRun)
            progress_finalized = type(retained) in (AcceptedRun, ExecutedRun)
            activity.emit("finalization", benchmark_outcome=progress_outcome)
            if type(retained) in (AcceptedRun, ExecutedRun):
                from .runtime.orchestration.replay import validate_finalized_run, disabled_validation_summaries
                from .runtime.artifacts.validation import ValidationArtifactStore
                try:
                    capture_evidence = {}
                    source_evidence = {}
                    if run_cache_replays and not (type(retained) is ExecutedRun and retained.cancelled):
                        validations = validate_finalized_run(terminal=retained, artifact_store=request.artifact_store,
                            boundary=request.execution_boundary, case_inputs=request.case_inputs,
                            treatment_prompts=request.treatment_prompts, capture_options=request.replay_capture_options,
                            temporary_root=request.artifact_store.root, capture_evidence=capture_evidence,
                            startup_records=startup.records if startup is not None else None, source_evidence=source_evidence, startup_diagnostics=startup.diagnostics if startup is not None else None, activity=activity)
                    else:
                        validations = disabled_validation_summaries(retained, cancelled=type(retained) is ExecutedRun and retained.cancelled)
                    activity.emit("validation_retention")
                    ValidationArtifactStore(request.artifact_store).retain(retained, validations, capture_evidence=capture_evidence, source_evidence=source_evidence)
                except (ValueError, TypeError, OSError) as exc:
                    # Scored finalization has already succeeded. A separate validation
                    # failure cannot turn it into a failed scored execution.
                    from .runtime.completion_diagnostics import completion_diagnostic
                    category = completion_diagnostic("post_treatment_validation", "failed", exc)["error_class"]
                    self._validation_diagnostics[retained.generation_id] = "post_treatment_validation_failed:" + category
                    try:
                        activity.emit("validation_retention")
                        ValidationArtifactStore(request.artifact_store).retain_failure(retained, self._validation_diagnostics[retained.generation_id])
                    except (ValueError, TypeError, OSError):
                        # Missing/deleted storage cannot be repaired after finalization.
                        pass

            return retained
        finally:
            activity.emit("cleanup")
            try:
                if startup is not None:
                    startup.close()
            finally:
                if request.cancellation_requested and request.cancellation_requested():
                    progress_outcome = "cancelled"
                activity.finish(progress_outcome, finalization_complete=progress_finalized)
                if retained is not None:
                    self._complete_run(retained, request)

    def completed_report(self, generation_id: str) -> GeneratedReportBundle | None:
        """Return only the exact report committed by automatic completion."""
        return self._completed_reports.get(generation_id)

    def completion_record(self, generation_id: str) -> Mapping[str, object] | None:
        """Return completion facts without rerunning validation or generation."""
        record = self._completion_records.get(generation_id)
        return json.loads(json.dumps(record)) if record is not None else None

    def _complete_run(self, terminal, request: ApplicationExecutionRequest) -> None:
        from .reporting.completion import completion_record, report_components
        from .runtime.completion_diagnostics import completion_diagnostic, persist_completion_diagnostics, ERROR_CLASSES
        from .runtime.artifacts.archive import ArchiveCleanupWarning, COMPLETION_MEMBER, read_archive_member
        generation_id = terminal.generation_id
        if generation_id in self._completion_records:
            raise ApplicationReportingError("completion is write-once")
        diagnostics = []

        def record_stage(stage, outcome="passed", error=None, error_class=None, operation=None):
            row = completion_diagnostic(stage, outcome, error, operation=operation)
            if error_class is not None:
                row["error_class"] = error_class if error_class in ERROR_CLASSES else "Exception"
            diagnostics.append(row)
            try:
                persist_completion_diagnostics(request.artifact_store.root, generation_id, diagnostics)
            except Exception as exc:
                # Diagnostic storage must not hide the original failure or change
                # published evidence authority. Surface its own failure in memory.
                warning = completion_diagnostic("diagnostic_persistence", "warning", exc)
                if warning not in diagnostics:
                    diagnostics.append(warning)

        bundle = None
        diagnostic = self.validation_diagnostic(generation_id)
        status = "not_applicable"
        if type(terminal) is AcceptedRun:
            status = "validation_failed" if diagnostic else "report_failed"
            if diagnostic is not None:
                record_stage("post_treatment_validation", "failed", error_class=diagnostic.rsplit(":", 1)[-1])
            else:
                stage = "source_validation"
                try:
                    status = "validation_failed"
                    terminal.revalidate(request.artifact_store)
                    from .runtime.artifacts.validation import ValidationArtifactStore
                    ValidationArtifactStore(request.artifact_store).read(terminal, required=True)
                    record_stage(stage)
                    status = "report_failed"
                    stage = "report_request"
                    if request.report_request_factory is None:
                        raise ApplicationReportingError("report request factory is required")
                    report_request = request.report_request_factory(terminal)
                    if type(report_request) is not ApplicationReportRequest:
                        raise TypeError("report factory must return ApplicationReportRequest")
                    if report_request.generation_id != generation_id:
                        raise ApplicationReportingError("report factory generation mismatch")
                    prefix = "reports/" + generation_id + "/"
                    report_request = replace(report_request,
                        report_reference=prefix + "report.json",
                        canonical_evidence_reference=prefix + "canonical-evidence.json",
                        human_reference=prefix + "report.md",
                        manifest_reference=prefix + "report-manifest.json")
                    record_stage(stage)
                    stage = "report_build"
                    bundle = self._build_report(report_request)
                    if bundle.report_document.get("status") not in {"complete", "complete_with_deviations", "dry_run"}:
                        raise ApplicationReportingError("report did not reach complete status")
                    record_stage(stage)
                    status = "validation_failed"
                    stage = "prepublication_validation"
                    terminal.revalidate(request.artifact_store)
                    ValidationArtifactStore(request.artifact_store).read(terminal, required=True)
                    record_stage(stage)
                    status = "complete"
                except Exception as exc:
                    bundle = None
                    diagnostic = "automatic_" + status + ":" + completion_diagnostic(stage, "failed", exc)["error_class"]
                    record_stage(stage, "failed", exc)
        record = completion_record(generation_id, status=status,
                                   bundle=bundle, diagnostic=diagnostic)
        record["diagnostics"] = list(diagnostics)
        if request.artifact_store.destination.ownership == "central":
            stage = "publication"
            try:
                try:
                    sealed = request.artifact_store.seal_generation(generation_id,
                        report_components=report_components(bundle), completion_record=record)
                except ArchiveCleanupWarning as warning:
                    sealed = warning.archive_path
                    for issue in warning.issues:
                        record_stage("post_publication_cleanup", "warning",
                            error_class=issue.rsplit(":", 1)[-1],
                            operation=issue.split(":", 1)[0])
                record_stage(stage)
                stage = "archive_readback"
                record = json.loads(read_archive_member(sealed, COMPLETION_MEMBER))
                record_stage(stage)
            except Exception as exc:
                # Never retry publication, reconstruct evidence, or fall back.
                bundle = None
                record_stage(stage, "failed", exc)
                record = {**record, "status": "report_failed", "report": None,
                    "publication": {"status": "failed", "diagnostic":
                        "automatic_publication_failed:" + completion_diagnostic(stage, "failed", exc)["error_class"]}}
        record["diagnostics"] = list(diagnostics)
        self._completion_records[generation_id] = record
        if bundle is not None:
            self._completed_reports[generation_id] = bundle
            self._generated_reports[bundle.report_document["report_id"]] = _RetainedGeneratedReport(
                generation_id=generation_id, bundle=bundle)

    def validation_diagnostic(self, generation_id: str) -> str | None:
        """Independent non-scored failure status; contains no captured content."""
        return self._validation_diagnostics.get(generation_id)

    def select_run(self, generation_id: str) -> AcceptedRun | BlockedRun:
        """Return one retained terminal result without altering active execution."""

        if not isinstance(generation_id, str) or not generation_id:
            raise ValueError("generation_id must be a non-empty string")
        retained = self._retained_runs.get(generation_id)
        if retained is None:
            raise ApplicationExecutionError(
                "retained execution generation is not available"
            )
        outcome = retained.outcome
        if type(outcome) in (AcceptedRun, ExecutedRun):
            outcome.revalidate(retained.artifact_store)
        self._selected_run_id = generation_id
        return outcome

    def delete_run(self, generation_id: str) -> ApplicationRunDeletion:
        """Delete one retained generation without making its identity reusable."""

        if not isinstance(generation_id, str) or not generation_id:
            raise ValueError("generation_id must be a non-empty string")
        retained = self._retained_runs.get(generation_id)
        if retained is None:
            raise ApplicationRetentionError(
                "retained execution generation is not available for deletion"
            )

        retained.artifact_store.delete_generation(generation_id)
        from .runtime.orchestration.activity import delete_retained_activity
        delete_retained_activity(retained.artifact_store.root, generation_id)
        from .runtime.artifacts.validation import ValidationArtifactStore
        ValidationArtifactStore(retained.artifact_store).delete_generation(generation_id)
        from .runtime.completion_diagnostics import delete_completion_diagnostics
        delete_completion_diagnostics(retained.artifact_store.root, generation_id)
        self._validation_diagnostics.pop(generation_id, None)
        self._completion_records.pop(generation_id, None)
        self._completed_reports.pop(generation_id, None)

        report_ids = tuple(
            report_id
            for report_id, retained_report in self._generated_reports.items()
            if retained_report.generation_id == generation_id
        )
        for report_id in report_ids:
            self._generated_reports.pop(report_id, None)
        self._retained_runs.pop(generation_id, None)
        if self._selected_run_id == generation_id:
            self._selected_run_id = None

        # Intentionally preserve _attempted_generation_ids. Retention deletion
        # withdraws local availability; it does not authorize identity reuse.
        return ApplicationRunDeletion(generation_id=generation_id)

    def _build_report(self, request: ApplicationReportRequest) -> GeneratedReportBundle:
        """Generate one report bundle from an exact retained accepted generation."""

        if not isinstance(request, ApplicationReportRequest):
            raise TypeError("request must be an ApplicationReportRequest")
        if request.report_id in self._generated_reports:
            raise ApplicationReportingError(
                "the requested report identity has already been generated"
            )

        retained = self._retained_runs.get(request.generation_id)
        if retained is None:
            raise ApplicationReportingError(
                "retained execution generation is not available for reporting"
            )
        finalized = retained.outcome
        if type(finalized) is not AcceptedRun:
            raise ApplicationReportingError(
                "blocked execution generations cannot authorize reporting"
            )

        finalized.revalidate(retained.artifact_store)
        from .treatments import require_certifiable
        require_certifiable(json.loads(finalized.run_outcome_bytes))
        authority = admit_finalized_run_for_reporting(
            finalized,
            store=retained.artifact_store,
            execution_boundary=request.execution_boundary,
            benchmark=request.benchmark,
            case_set=request.case_set,
            treatment_set=request.treatment_set,
            comparison_track_id=request.comparison_track_id,
            primary_endpoint=request.primary_endpoint,
            metrics=tuple(request.metrics),
            observation_counts=request.observation_counts,
            observation_matrix=tuple(request.observation_matrix),
            case_result_matrix=tuple(request.case_result_matrix),
            treatment_summaries=tuple(request.treatment_summaries),
        )
        from .runtime.artifacts.validation import ValidationArtifactStore
        validation_store = ValidationArtifactStore(retained.artifact_store)
        report_extensions = dict(request.extensions)
        if request.extension_evaluator is not None:
            evaluated = request.extension_evaluator(
                report_id=request.report_id,
                report_status=request.status,
                finalized=finalized,
                reporting=authority,
                artifact_store=retained.artifact_store,
            )
            if not isinstance(evaluated, Mapping):
                raise ApplicationReportingError("report extension evaluator must return a mapping")
            if report_extensions.keys() & evaluated.keys():
                raise ApplicationReportingError("evaluated report extensions collide with request extensions")
            report_extensions.update(evaluated)
        validations, validation_records = validation_store.read_with_records(finalized, required=True)
        validation_inputs = tuple(ReportArtifactRef.from_record(r)
                                  for r in validation_records)
        model = build_canonical_report_model(
            authority,
            report_id=request.report_id,
            report_version=request.report_version,
            status=request.status,
            sections=request.sections,
            report_manifest_id=request.report_manifest_id,
            generated_at=request.generated_at,
            extensions=report_extensions,
            validations=validations,
            validation_inputs=validation_inputs,
        )
        bundle = generate_report_bundle(
            model,
            input_evidence_set_id=request.input_evidence_set_id,
            generator=request.generator,
            procedure_id=request.procedure_id,
            procedure_version=request.procedure_version,
            command_or_procedure=request.command_or_procedure,
            report_reference=request.report_reference,
            canonical_evidence_reference=request.canonical_evidence_reference,
            human_reference=request.human_reference,
            manifest_reference=request.manifest_reference,
        )
        if type(bundle) is not GeneratedReportBundle:
            raise ApplicationReportingError(
                "report generation returned invalid shared reporting authority"
            )
        return bundle

    def _require_prerequisites(
        self,
        operation: ApplicationPrerequisiteOperation,
    ) -> None:
        unresolved = self._prerequisite_projection.unresolved_for(operation)
        if not unresolved:
            return
        identities = ", ".join(state.prerequisite_id for state in unresolved)
        message = f"{operation} prerequisites are unresolved: {identities}"
        if operation == "execution":
            raise ApplicationExecutionError(message)
        if operation == "acceptance":
            raise ApplicationAcceptanceError(message)
        raise ApplicationPlanningError(message)

    def _retain_terminal_run(
        self,
        outcome: AcceptedRun | BlockedRun,
        artifact_store: FilesystemArtifactStore,
    ) -> AcceptedRun | BlockedRun:
        if type(outcome) not in (AcceptedRun, BlockedRun, ExecutedRun):
            raise ApplicationExecutionError(
                "accepted execution did not return a terminal shared outcome"
            )
        generation_id = outcome.generation_id
        if generation_id in self._retained_runs:
            raise ApplicationExecutionError(
                "terminal authority already exists for this execution generation"
            )
        if type(outcome) in (AcceptedRun, ExecutedRun):
            outcome.revalidate(artifact_store)
        self._attempted_generation_ids.add(generation_id)
        self._retained_runs[generation_id] = _RetainedTerminalRun(
            outcome=outcome,
            artifact_store=artifact_store,
        )
        return outcome


def discover_application_authority(
    *,
    benchmark_candidates: Sequence[BenchmarkDiscoveryCandidate],
    runner_sources: Sequence[ApplicationRegistrationSource],
) -> ApplicationDiscovery:
    """Return exact active benchmark/runner registrations or fail closed.

    Candidate sets are explicit inputs.  Filesystem or package presence is never
    treated as activation authority.
    """

    benchmarks = tuple(benchmark_candidates)
    runners = tuple(runner_sources)
    issues = validate_benchmark_discovery(benchmarks)
    if issues:
        codes = ", ".join(issue.code for issue in issues)
        raise ApplicationDiscoveryError(
            f"benchmark discovery authority is invalid: {codes}"
        )

    benchmark_results = tuple(
        sorted(
            (_benchmark_projection(candidate) for candidate in benchmarks),
            key=_registration_sort_key,
        )
    )
    runner_results = tuple(
        sorted(
            (_runner_projection(source) for source in runners),
            key=_registration_sort_key,
        )
    )
    _require_unique_registration_identities(runner_results, kind="runner")
    return ApplicationDiscovery(benchmark_results, runner_results)


def _benchmark_projection(candidate: BenchmarkDiscoveryCandidate) -> DiscoveredRegistration:
    registration = candidate.registration
    validation = candidate.registration_validation
    if registration is None or validation is None or not validation.valid:
        raise ApplicationDiscoveryError(
            "benchmark discovery candidate lacks valid registration authority"
        )
    return _projection(
        registration,
        validation=validation,
        source_id=candidate.registration_source_id,
        expected_kind="benchmark",
    )


def _runner_projection(source: ApplicationRegistrationSource) -> DiscoveredRegistration:
    validation = source.registration_validation
    registration = source.registration
    if not validation.matches(registration, source_id=source.registration_source_id):
        raise ApplicationDiscoveryError(
            "runner registration validation does not match exact registration bytes"
        )
    if not validation.valid:
        raise ApplicationDiscoveryError("runner registration validation failed")
    return _projection(
        registration,
        validation=validation,
        source_id=source.registration_source_id,
        expected_kind="runner",
    )


def _projection(
    registration: Mapping[str, Any],
    *,
    validation: RegistrationValidationOutcome,
    source_id: str,
    expected_kind: str,
) -> DiscoveredRegistration:
    registration_id = registration.get("registration_id")
    registration_version = registration.get("registration_version")
    registration_kind = registration.get("registration_kind")
    if registration_kind != expected_kind:
        raise ApplicationDiscoveryError(
            f"{expected_kind} discovery requires registration_kind={expected_kind!r}"
        )
    if registration.get("status") != "active":
        raise ApplicationDiscoveryError(
            f"only active {expected_kind} registrations may be discovered"
        )
    if not isinstance(registration_id, str) or not registration_id:
        raise ApplicationDiscoveryError("registration_id must be a non-empty string")
    if not isinstance(registration_version, str) or not registration_version:
        raise ApplicationDiscoveryError(
            "registration_version must be a non-empty string"
        )
    return DiscoveredRegistration(
        registration_id=registration_id,
        registration_version=registration_version,
        registration_kind=registration_kind,
        registration_sha256=validation.registration_sha256,
        registration_source_id=source_id,
        capabilities=_string_tuple(registration.get("capabilities", ()), "capabilities"),
        limitations=_string_tuple(registration.get("limitations", ()), "limitations"),
    )


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ApplicationDiscoveryError(f"{field} must be an array of strings")
    result = tuple(value)
    if any(not isinstance(item, str) for item in result):
        raise ApplicationDiscoveryError(f"{field} must contain only strings")
    return result


def _registration_sort_key(value: DiscoveredRegistration) -> tuple[str, str]:
    return (value.registration_id, value.registration_version)


def _require_unique_registration_identities(
    values: Sequence[DiscoveredRegistration],
    *,
    kind: str,
) -> None:
    seen: set[tuple[str, str]] = set()
    for value in values:
        identity = (value.registration_id, value.registration_version)
        if identity in seen:
            raise ApplicationDiscoveryError(
                f"{kind} registration identity {identity!r} is ambiguous"
            )
        seen.add(identity)


def _require_discovered_benchmark(
    benchmark: IdentityRef,
    discovered: Sequence[DiscoveredRegistration],
) -> None:
    for item in discovered:
        if (
            item.registration_id == benchmark.id
            and item.registration_version == benchmark.version
        ):
            if benchmark.sha256 != item.registration_sha256:
                raise ApplicationPlanningError(
                    "benchmark identity does not match discovered registration authority"
                )
            return
    raise ApplicationPlanningError(
        "benchmark identity is not present in discovered application authority"
    )


def _require_discovered_runner(
    boundary: ExecutionBoundary,
    discovered: Sequence[DiscoveredRegistration],
) -> None:
    runner = IdentityRef.from_value(boundary.to_dict()["runner"], field="runner")
    if any(
        item.registration_id == runner.id
        and item.registration_version == runner.version
        for item in discovered
    ):
        return
    raise ApplicationPlanningError(
        "execution boundary runner is not present in discovered application authority"
    )


__all__ = [
    "ApplicationAcceptanceError",
    "ApplicationDiscovery",
    "ApplicationDiscoveryError",
    "ApplicationExecutionError",
    "ApplicationExecutionRequest",
    "ApplicationPlanRequest",
    "ApplicationPlanningError",
    "ApplicationPrerequisiteOperation",
    "ApplicationPrerequisiteProjection",
    "ApplicationPrerequisiteState",
    "ApplicationReportRequest",
    "ApplicationReportingError",
    "ApplicationRetentionError",
    "ApplicationRunDeletion",
    "ApplicationRegistrationSource",
    "DiscoveredRegistration",
    "PlanningApplicationSession",
    "discover_application_authority",
]
