"""Production request resolution from validated repository authority."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path, PurePosixPath
from random import shuffle
import sys

from AgMark.gui.composition import (
    RepositoryApplicationAuthority,
    RepositoryCompositionError,
)
from AgMark.gui.shell.window import (
    SidebarControlInputSnapshot,
    SidebarInputSnapshot,
)
from AgMark.shared.application import (
    ApplicationDiscovery,
    ApplicationExecutionRequest,
    ApplicationPlanRequest,
    ApplicationReportRequest,
)
from AgMark.shared.evaluation import (
    SCORER_INVOCATION_CONTRACT_ID,
    SCORER_INVOCATION_CONTRACT_VERSION,
    IdentityRef as ReportingIdentityRef,
)
from AgMark.shared.evaluation.availability import AvailabilityRecord
from AgMark.shared.reporting import (
    REQUIRED_REPORT_SECTIONS,
    CaseResultEntry,
    GeneratedReportBundle,
    ObservationCounts,
    ObservationMatrixEntry,
    RegisteredReportMetric,
    ReportArtifactRef,
    ReportSection,
    TreatmentSummary,
)
from AgMark.shared.runtime.artifacts import (
    FilesystemArtifactStore,
    PublicationDestination,
    sha256_bytes,
)
from AgMark.shared.runtime.golden import (
    GoldenArtifactRequirement,
    GoldenCaseInput,
    GoldenDeclaration,
    TransientEnvironmentBinding,
)
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    AcceptedRun,
    AcceptedRunSnapshot,
    PlannedCaseInput,
    RegisteredScoringDefinition,
    RUN_LIFECYCLE_CONTRACT_ID,
    RUN_LIFECYCLE_CONTRACT_VERSION,
    TreatmentCaseInput,
    TreatmentPrompt,
)
from AgMark.shared.validation import (
    ArtifactSource,
    ContractRequirement,
    validate_registration_binding_outcome,
)


_SUPPORTED_CONTROLS = "arcgrav.adapters:supported_controls"
_FIXED_CONTROLS = "arcgrav.adapters:fixed_controls"
_ACCESS_METHODS = "arcgrav.adapters:access_methods"
_SECRET_HANDLING = "arcgrav.adapters:secret_handling"
_TRANSIENT_INPUTS = "transient_inputs"
_PLANNING_PROBE = "arcgrav.adapters:planning_probe"
_CREDENTIAL_SOURCE_CONTROL = "credential_source"
_TRANSIENT_CREDENTIAL_SOURCE = "credential_source"
_TRANSIENT_CREDENTIAL_MATERIAL = "credential_material"
_MODEL_CONTROLS = frozenset({"model", "model_id"})
_LAUNCH_ENVIRONMENT = "arcgrav.adapters:launch_environment"
_MISSING = object()
_REPORT_GENERATION_CONTRACT = ("arcgrav.shared.report-generation", "3.0.0")
_RUN_COMPLETION_CONTRACT = ("arcgrav.shared.run-completion", "2.0.0")
_REPORT_GENERATOR = ReportingIdentityRef(
    "arcgrav.generator.shared-report-bundle",
    "1.0.0",
)
_REPORT_PROCEDURE_ID = "arcgrav.procedure.shared-report-bundle"
_REPORT_PROCEDURE_VERSION = "1.0.0"
_REPORT_SELECTION_EXTENSION = "arcgrav.gui:registered-report-selection"

from .repository_resources import _exact_benchmark_candidate, _exact_runner_source, _mapping, _package_directory, _resource, _selected_authority, _selected_candidate, _selected_runner, _text
from .runner_boundary import _revalidate_runner_execution_readiness, _runner_boundary, _runner_transient_values
from .planning import _cases, _contracts, _treatments
from .execution import _execution_case_inputs, _execution_treatment_prompts, _golden_declaration, _golden_transient_values, _scoring_definition
from .reporting import _report_request_from_accepted

@dataclass(frozen=True, slots=True)
class ResolvedRunnerTestRequest:
    """Registered runner material for one non-authoritative GUI diagnostic."""

    execution_boundary: ExecutionBoundary
    runner_registration: Mapping[str, object]
    runner_transient_values: Mapping[str, str] | None
    runner_launch_selection: Mapping[str, str] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.execution_boundary) is not ExecutionBoundary:
            raise TypeError("execution_boundary must be an ExecutionBoundary")
        if not isinstance(self.runner_registration, Mapping):
            raise TypeError("runner_registration must be a mapping")
        if self.runner_transient_values is not None:
            if not isinstance(self.runner_transient_values, Mapping):
                raise TypeError("runner_transient_values must be a mapping or None")
            if any(
                not isinstance(name, str) or not isinstance(value, str)
                for name, value in self.runner_transient_values.items()
            ):
                raise TypeError("runner_transient_values must map strings to strings")

class RepositoryApplicationRequestResolver:
    """Resolve production requests from exact repository-authorized inputs."""

    def __init__(
        self,
        authority: RepositoryApplicationAuthority,
        *,
        repetitions: int = 1,
        golden_environment_family: str = "native",
        golden_runtime_executable: str | Path | None = None,
        runner_planning_probe: (
            Callable[[object, Mapping[str, object]], object] | None
        ) = None,
    ) -> None:
        if not isinstance(authority, RepositoryApplicationAuthority):
            raise TypeError("authority must be RepositoryApplicationAuthority")
        if type(repetitions) is not int or repetitions < 1:
            raise ValueError("repetitions must be a positive integer")
        if runner_planning_probe is not None and not callable(runner_planning_probe):
            raise ValueError("runner_planning_probe must be callable or None")
        executable = Path(golden_runtime_executable or sys.executable).resolve(strict=True)
        if not executable.is_file():
            raise RepositoryCompositionError("golden runtime executable is not a file")
        self._folder_prompts = {}
        self._launch_selections = {}
        self._authority = authority
        self._repetitions = repetitions
        self._golden_environment_family = _text(
            golden_environment_family,
            "golden_environment_family",
        )
        self._golden_runtime_executable = executable
        self._runner_planning_probe = runner_planning_probe

    def transient_plan_launch_controls(self, request: ApplicationPlanRequest) -> dict[str, str]:
        """Return live launch inputs without promoting them to retained authority."""
        selection = self._launch_selections.get(id(request.execution_boundary), {})
        return {name: selection[name] for name in ("codex_binary", "wsl_distribution")
                if isinstance(selection.get(name), str)}

    def resolve_plan_request(
        self,
        intent: SidebarInputSnapshot,
        discovery: ApplicationDiscovery,
    ) -> ApplicationPlanRequest:
        if discovery != self._authority.discovery:
            raise RepositoryCompositionError(
                "planning discovery does not match repository authority"
            )
        benchmark_label = _text(intent.benchmark, "selected benchmark")
        runner_label = _text(intent.runner, "selected runner")
        candidate = _selected_candidate(self._authority, benchmark_label)
        source = _selected_runner(self._authority, runner_label)
        registration = _mapping(candidate.registration, "benchmark registration")
        treatment_content = []
        folder_source = registration.get("extensions", {}).get("arcgrav.benchmark:prompt-folder")
        if folder_source is not None:
            from .repository_resources import _artifact, _safe_file, _verified_bytes
            declaration = _artifact(registration, folder_source["artifact_id"])
            _verified_bytes(_safe_file(self._authority.repository_root, declaration["reference"]), declaration["sha256"], "prompt loader")
            module, name = folder_source["entry_point"].split(":")
            loader = getattr(import_module(module), name)
            prompts = loader(intent.prompt_folder)
            excluded = set(intent.excluded_treatments)
            available = {prompt.treatment_id for prompt in prompts}
            if excluded - available:
                raise ValueError(
                    "Excluded treatment files are not in the selected folder: "
                    + ", ".join(sorted(excluded - available))
                )
            prompts = tuple(
                prompt for prompt in prompts
                if prompt.treatment_id not in excluded
            )
            if not prompts:
                raise ValueError("At least one treatment file must remain in the plan.")
            from AgMark.shared.runtime.identity import canonical_sha256
            digest = canonical_sha256([{ "name": p.treatment_id, "sha256": p.sha256 } for p in prompts])
            case_set = IdentityRef("arcgrav.prompt-folder.empty-case", "1.0.0", sha256=canonical_sha256({"case_id": "prompt", "input": ""}))
            treatment_set = IdentityRef("arcgrav.prompt-folder.treatments", "1.0.0", sha256=digest)
            from AgMark.shared.runtime.orchestration import PlannedCaseInput
            cases = (PlannedCaseInput("prompt", sha256_bytes(b""), byte_length=0),)
            treatments = tuple(p.treatment_id for p in prompts)
            golden_required = False
            self._folder_prompts[digest] = prompts
        else:
            selected = _selected_authority(registration)

            case_set, case_document = _resource(
                self._authority.repository_root,
                registration,
                _mapping(selected.get("case_set"), "selected case_set"),
                "case_set",
            )
            treatment_set, treatment_document = _resource(
                self._authority.repository_root,
                registration,
                _mapping(selected.get("treatment_set"), "selected treatment_set"),
                "treatment_set",
            )
            package_root = _text(candidate.package_root, "benchmark package root")
            cases = _cases(
                self._authority.repository_root,
                package_root,
                case_document,
            )
            from AgMark.shared.treatments import POLICY, freeze
            allow_contamination = registration.get("extensions", {}).get(POLICY, {}).get("mismatch") == "contaminated"
            treatments = _treatments(
                self._authority.repository_root,
                package_root,
                treatment_document,
                allow_contamination=allow_contamination,
            )
            excluded = set(intent.excluded_treatments)
            unknown = excluded.difference(treatments)
            if unknown:
                raise ValueError(
                    "Excluded treatments are not in the selected benchmark: "
                    + ", ".join(sorted(unknown))
                )
            treatments = tuple(
                treatment for treatment in treatments if treatment not in excluded
            )
            if not treatments:
                raise ValueError("At least one treatment must remain in the plan.")
            if allow_contamination:
                from .repository_resources import _safe_file
                treatment_content = [freeze(t["treatment_id"], t["prompt"],
                    _safe_file(self._authority.repository_root, t["prompt"]["reference"], package_root=package_root).read_bytes())
                    for t in treatment_document["treatments"] if t["treatment_id"] in treatments]
            golden_required = selected.get("golden_authority") is not None
            if golden_required:
                _mapping(selected["golden_authority"], "selected golden authority")

        # Fix one shuffled order unless canonical planning will shuffle each iteration.
        if intent.randomize_treatment_start and not intent.randomize_per_iteration:
            shuffled_treatments = list(treatments)
            shuffle(shuffled_treatments)
            treatments = tuple(shuffled_treatments)

        launch_selection = {}
        runner, runtime, controls = _runner_boundary(
            intent,
            source,
            repository_root=self._authority.repository_root,
            planning_probe=self._runner_planning_probe,
            launch_selection=launch_selection,
        )
        environment = {}
        if golden_required:
            environment = {
                "golden.environment_family": self._golden_environment_family,
                "golden.runtime_sha256": sha256_bytes(self._golden_runtime_executable.read_bytes()),
            }
        boundary = ExecutionBoundary.build(
            boundary_id=f"boundary-gui-production:{benchmark_label}:{runner_label}",
            framework=IdentityRef("arcgrav.framework", "1.0.0"),
            runner=runner,
            provider_runtime=runtime,
            controls=controls,
            environment=environment,
        )
        self._launch_selections[id(boundary)] = dict(launch_selection)
        benchmark = IdentityRef(
            _text(registration.get("registration_id"), "benchmark id"),
            _text(registration.get("registration_version"), "benchmark version"),
            sha256=candidate.registration_validation.registration_sha256,
            reference=candidate.registration_source_id,
        )
        return ApplicationPlanRequest(
            benchmark=benchmark,
            case_set=case_set,
            treatment_set=treatment_set,
            cases=cases,
            treatments=treatments,
            repetitions=getattr(intent, "iterations", self._repetitions),
            extensions={
                **({"arcgrav.runtime:treatment-content": treatment_content} if treatment_content else {}),
                "arcgrav.runtime:cache-validation-replays": intent.run_cache_validation_replays,
                "arcgrav.runtime:randomize-treatment-start": intent.randomize_treatment_start,
                "arcgrav.runtime:randomize-per-iteration": (
                    intent.randomize_treatment_start and intent.randomize_per_iteration
                ),
                **({"arcgrav.runtime:execution-only": True} if folder_source is not None else {}),
            },
            execution_boundary=boundary,
            golden_required=golden_required,
            contracts=_contracts(registration),
        )

    def resolve_runner_test_request(
        self,
        intent: SidebarInputSnapshot,
        discovery: ApplicationDiscovery,
    ) -> ResolvedRunnerTestRequest:
        """Resolve one non-authoritative runner diagnostic from sidebar intent."""

        if discovery != self._authority.discovery:
            raise RepositoryCompositionError(
                "runner test discovery does not match repository authority"
            )
        runner_label = _text(intent.runner, "selected runner")
        source = _selected_runner(self._authority, runner_label)
        launch_selection = {}
        runner, runtime, controls = _runner_boundary(
            intent,
            source,
            repository_root=self._authority.repository_root,
            planning_probe=self._runner_planning_probe,
            launch_selection=launch_selection,
        )
        boundary = ExecutionBoundary.build(
            boundary_id=f"boundary-gui-runner-test:{runner_label}",
            framework=IdentityRef("arcgrav.framework", "1.0.0"),
            runner=runner,
            provider_runtime=runtime,
            controls=controls,
        )
        runner_transient_values = _runner_transient_values(
            source,
            intent.additional_controls,
            credential=intent.credential,
        )
        _revalidate_runner_execution_readiness(
            source,
            repository_root=self._authority.repository_root,
            execution_boundary=boundary,
            launch_selection=launch_selection,
            runner_transient_values=runner_transient_values,
            planning_probe=self._runner_planning_probe,
        )
        return ResolvedRunnerTestRequest(
            execution_boundary=boundary,
            runner_registration=source.registration,
            runner_transient_values=runner_transient_values,
            runner_launch_selection=launch_selection,
        )

    def resolve_execution_request(
        self,
        plan_request: ApplicationPlanRequest,
        accepted_snapshot: AcceptedRunSnapshot,
        *,
        credential: str,
        runner_transient_controls: Sequence[SidebarControlInputSnapshot] = (),
    ) -> ApplicationExecutionRequest:
        if type(plan_request) is not ApplicationPlanRequest:
            raise TypeError("plan_request must be an ApplicationPlanRequest")
        if type(accepted_snapshot) is not AcceptedRunSnapshot:
            raise TypeError("accepted_snapshot must be an AcceptedRunSnapshot")

        benchmark = IdentityRef.from_value(plan_request.benchmark, field="benchmark")
        candidate = _exact_benchmark_candidate(self._authority, benchmark)
        source = _exact_runner_source(
            self._authority,
            plan_request.execution_boundary,
        )
        accepted_snapshot.revalidate_authority(
            benchmark=plan_request.benchmark,
            case_set=plan_request.case_set,
            treatment_set=plan_request.treatment_set,
            execution_boundary=plan_request.execution_boundary,
        )
        runner_transient_values = _runner_transient_values(
            source,
            runner_transient_controls,
            credential=credential,
        )
        _revalidate_runner_execution_readiness(
            source,
            repository_root=self._authority.repository_root,
            execution_boundary=plan_request.execution_boundary,
            launch_selection=self._launch_selections.get(id(plan_request.execution_boundary)),
            runner_transient_values=runner_transient_values,
            planning_probe=self._runner_planning_probe,
        )

        registration = candidate.registration
        package_root = candidate.package_root
        benchmark_root = _package_directory(self._authority.repository_root, package_root)
        if plan_request.extensions.get("arcgrav.runtime:execution-only") is True:
            if "arcgrav.benchmark:prompt-folder" not in registration.get("extensions", {}):
                raise RepositoryCompositionError("Benchmark does not support folder execution")
            treatment_prompts = self._folder_prompts.get(plan_request.treatment_set.sha256)
            if treatment_prompts is None:
                raise RepositoryCompositionError("Prompt selection is unavailable; build a new plan")
            from AgMark.shared.runtime.orchestration import TreatmentCaseInput
            case_inputs = (TreatmentCaseInput("prompt", b""),)
            golden_case_inputs, golden, scoring, golden_transient_values = (), None, None, None
        else:
            selected = _selected_authority(registration)
            package_root = candidate.package_root
            benchmark_root = _package_directory(
                self._authority.repository_root,
                package_root,
            )
            case_set_selected = _mapping(
                selected.get("case_set"),
                "selected case set",
            )
            treatment_set_selected = _mapping(
                selected.get("treatment_set"),
                "selected treatment set",
            )
            case_set_identity, case_set_document = _resource(
                self._authority.repository_root,
                registration,
                case_set_selected,
                "case_set",
            )
            treatment_set_identity, treatment_set_document = _resource(
                self._authority.repository_root,
                registration,
                treatment_set_selected,
                "treatment_set",
            )
            if case_set_identity.to_dict() != IdentityRef.from_value(
                plan_request.case_set,
                field="case_set",
            ).to_dict():
                raise RepositoryCompositionError(
                    "registered case-set authority changed after plan acceptance"
                )
            if treatment_set_identity.to_dict() != IdentityRef.from_value(
                plan_request.treatment_set,
                field="treatment_set",
            ).to_dict():
                raise RepositoryCompositionError(
                    "registered treatment-set authority changed after plan acceptance"
                )

            case_inputs, golden_case_inputs = _execution_case_inputs(
                self._authority.repository_root,
                package_root,
                case_set_document,
            )
            from AgMark.shared.treatments import CONTENT, content_entries
            from base64 import b64decode
            entries = content_entries({"extensions": dict(plan_request.extensions)})
            if entries:
                expected = {t["treatment_id"]: t["prompt"] for t in treatment_set_document["treatments"]}
                if any(e["expected"] != expected.get(e["treatment_id"]) for e in entries):
                    raise RepositoryCompositionError("retained expected treatment identity changed")
                registered_prompts = tuple(TreatmentPrompt(e["treatment_id"], b64decode(e["content_base64"], validate=True)) for e in entries)
            else:
                registered_prompts = _execution_treatment_prompts(
                    self._authority.repository_root, package_root, treatment_set_document,
                )
            prompts_by_id = {
                prompt.treatment_id: prompt for prompt in registered_prompts
            }
            if not set(plan_request.treatments).issubset(prompts_by_id):
                raise RepositoryCompositionError(
                    "accepted treatment selection is not in the registered treatment set"
                )
            treatment_prompts = tuple(
                prompts_by_id[treatment_id] for treatment_id in plan_request.treatments
            )
            scoring = _scoring_definition(
                self._authority.repository_root,
                package_root,
                registration,
                selected,
            )
            golden, bindings = _golden_declaration(
                self._authority.repository_root,
                package_root,
                registration,
                selected,
                environment_family=self._golden_environment_family,
                runtime_executable=self._golden_runtime_executable,
            )
            if plan_request.golden_required != (golden is not None):
                raise RepositoryCompositionError(
                    "registered golden authority changed after plan acceptance"
                )

            golden_transient_values = _golden_transient_values(
                credential,
                bindings,
                credential_claimed_by_runner=runner_transient_values is not None,
            )

        destination = PublicationDestination.central(
            self._authority.repository_root / "AgMark" / "run_evidence",
            repository_root=self._authority.repository_root,
        )
        artifact_store = FilesystemArtifactStore(destination)
        generation_preimage = (
            accepted_snapshot.accepted_snapshot_id
            + "\x00"
            + accepted_snapshot.accepted_at
        ).encode("utf-8")
        generation_id = "generation-" + sha256(generation_preimage).hexdigest()

        return ApplicationExecutionRequest(
            generation_id=generation_id,
            benchmark=plan_request.benchmark,
            case_set=plan_request.case_set,
            treatment_set=plan_request.treatment_set,
            execution_boundary=plan_request.execution_boundary,
            benchmark_root=benchmark_root,
            artifact_store=artifact_store,
            repository_root=self._authority.repository_root,
            runner_registration=source.registration,
            case_inputs=case_inputs,
            treatment_prompts=treatment_prompts,
            scoring_definitions=(scoring,) if scoring is not None else (),
            golden_declaration=golden,
            golden_case_inputs=golden_case_inputs if golden is not None else (),
            transient_values=golden_transient_values,
            runner_transient_values=runner_transient_values,
            runner_launch_selection=self._launch_selections.get(id(plan_request.execution_boundary)),
            report_request_factory=self.resolve_report_request,
        )

    def resolve_report_request(self, retained_run: AcceptedRun) -> ApplicationReportRequest:
        return _report_request_from_accepted(self._authority, retained_run)



__all__ = ["RepositoryApplicationRequestResolver", "ResolvedRunnerTestRequest"]
