"""Presentation-model contracts for the persistent benchmark shell."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from AgMark.gui.widgets.console import CONSOLE_TABS

WORKSPACE_TAB_LABELS = (
    "Progress",
    "Scoring",
    "Results",
    "Evidence",
    "Verification",
    "Reports",
)
SIDEBAR_PREREQUISITE_OPERATIONS = ("planning", "acceptance", "execution")
SIDEBAR_PREREQUISITE_SCOPE_LABELS = {
    "planning": "Planning prerequisite",
    "acceptance": "Acceptance prerequisite",
    "execution": "Execution readiness",
}

def _require_non_empty(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_bool(value: bool, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value

def _visible_options(values: Sequence[str], *, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a sequence of visible strings")
    normalized = tuple(_require_non_empty(value, name=name) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must contain unique visible strings")
    return normalized


def _selected_option(
    value: str | None,
    *,
    options: tuple[str, ...],
    name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in options:
        raise ValueError(f"{name} must be None or one of the supplied options")
    return value

@dataclass(frozen=True, slots=True)
class NumericInputProjection:
    """Explicit caller-owned numeric configuration intent."""

    value: float | None
    minimum: float
    maximum: float
    step: float = 1.0
    decimals: int = 0
    required: bool = False
    editable: bool = True

    def __post_init__(self) -> None:
        normalized: dict[str, float] = {}
        for name in ("minimum", "maximum", "step"):
            raw = getattr(self, name)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            number = float(raw)
            if not isfinite(number):
                raise ValueError(f"{name} must be a finite number")
            normalized[name] = number
            object.__setattr__(self, name, number)
        if self.value is not None:
            raw_value = self.value
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise ValueError("value must be a finite number or None")
            value = float(raw_value)
            if not isfinite(value):
                raise ValueError("value must be a finite number or None")
            object.__setattr__(self, "value", value)
            normalized["value"] = value
        if normalized["minimum"] > normalized["maximum"]:
            raise ValueError("minimum must be less than or equal to maximum")
        if normalized["step"] <= 0:
            raise ValueError("step must be greater than zero")
        if (
            self.value is not None
            and not normalized["minimum"] <= self.value <= normalized["maximum"]
        ):
            raise ValueError("value must be within the supplied numeric range")
        if (
            not isinstance(self.decimals, int)
            or isinstance(self.decimals, bool)
            or self.decimals < 0
        ):
            raise ValueError("decimals must be a non-negative integer")
        _require_bool(self.required, name="required")
        _require_bool(self.editable, name="editable")
        if not self.editable and self.value is None:
            raise ValueError("non-editable numeric input must have a value")


@dataclass(frozen=True, slots=True)
class SidebarTextControlProjection:
    """Caller-supplied free-text or transient-secret runner control."""

    control_name: str
    label: str
    value: str = ""
    secret: bool = False
    required: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.control_name, name="control_name")
        _require_non_empty(self.label, name="label")
        if not isinstance(self.value, str):
            raise ValueError("value must be a string")
        _require_bool(self.secret, name="secret")
        _require_bool(self.required, name="required")


@dataclass(frozen=True, slots=True)
class SidebarResolvedTextProjection:
    """Read-only resolved runner configuration shown without becoming user intent."""

    control_name: str
    label: str
    value: str

    def __post_init__(self) -> None:
        _require_non_empty(self.control_name, name="control_name")
        _require_non_empty(self.label, name="label")
        _require_non_empty(self.value, name="value")


@dataclass(frozen=True, slots=True)
class SidebarChoiceControlProjection:
    """Caller-supplied finite-choice runner control."""

    control_name: str
    label: str
    options: tuple[str, ...]
    selected_value: str | None = None
    required: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.control_name, name="control_name")
        _require_non_empty(self.label, name="label")
        options = _visible_options(self.options, name="options")
        if not options:
            raise ValueError("options must contain at least one visible value")
        object.__setattr__(self, "options", options)
        object.__setattr__(
            self,
            "selected_value",
            _selected_option(
                self.selected_value,
                options=options,
                name="selected_value",
            ),
        )
        _require_bool(self.required, name="required")


@dataclass(frozen=True, slots=True)
class SidebarNumericControlProjection:
    """Caller-supplied named numeric runner control."""

    control_name: str
    label: str
    numeric: NumericInputProjection
    required: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.control_name, name="control_name")
        _require_non_empty(self.label, name="label")
        if not isinstance(self.numeric, NumericInputProjection):
            raise ValueError("numeric must be NumericInputProjection")
        _require_bool(self.required, name="required")


@dataclass(frozen=True, slots=True)
class SidebarPrerequisiteDiagnosticProjection:
    """Caller-supplied prerequisite state with console-owned diagnostic detail."""

    diagnostic_name: str
    message: str
    remediation: str
    operation: str = "planning"
    details: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.diagnostic_name, name="diagnostic_name")
        _require_non_empty(self.message, name="message")
        _require_non_empty(self.remediation, name="remediation")
        if self.details is not None:
            _require_non_empty(self.details, name="details")
        if self.operation not in SIDEBAR_PREREQUISITE_OPERATIONS:
            raise ValueError(
                "operation must be one of planning, acceptance, or execution"
            )

    @property
    def scope_label(self) -> str:
        """Return the concise lifecycle scope used by sidebar presentation."""

        return SIDEBAR_PREREQUISITE_SCOPE_LABELS[self.operation]


@dataclass(frozen=True, slots=True)
class RetainedRunProjection:
    """Caller-supplied run-list presentation state."""

    run_id: str
    display_identity: str
    state_label: str
    state_tone: str
    timestamp: str
    selected: bool = False
    selectable: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(self.run_id, name="run_id")
        _require_non_empty(self.display_identity, name="display_identity")
        _require_non_empty(self.state_label, name="state_label")
        _require_non_empty(self.state_tone, name="state_tone")
        _require_non_empty(self.timestamp, name="timestamp")
        _require_bool(self.selected, name="selected")
        _require_bool(self.selectable, name="selectable")
        if self.selected and not self.selectable:
            raise ValueError("a non-selectable run row cannot be selected")


@dataclass(frozen=True, slots=True)
class SidebarModelChoiceProjection:
    """One discovered model choice with presentation and authority kept separate."""

    label: str
    model_value: str
    selection_mode: str | None = None
    selection_mode_control_name: str | None = None
    scenario_id: str | None = None
    scenario_label: str | None = None
    base_model_id: str | None = None
    scenario_default: bool = False
    reasoning_efforts: tuple[tuple[str, str], ...] = ()
    default_reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.label, name="label")
        _require_non_empty(self.model_value, name="model_value")
        efforts = tuple(self.reasoning_efforts)
        for value, description in efforts:
            _require_non_empty(value, name="reasoning effort")
            if not isinstance(description, str):
                raise ValueError("reasoning effort description must be text")
        values = tuple(value for value, _ in efforts)
        if len(set(values)) != len(values):
            raise ValueError("reasoning efforts must be unique")
        if (efforts or self.default_reasoning_effort is not None) and self.default_reasoning_effort not in values:
            raise ValueError("reasoning default must be a supported effort")
        object.__setattr__(self, "reasoning_efforts", efforts)
        scenario_fields = (self.scenario_id, self.scenario_label, self.base_model_id)
        if any(value is not None for value in scenario_fields):
            for value in scenario_fields:
                _require_non_empty(value, name="scenario metadata")
        _require_bool(self.scenario_default, name="scenario_default")
        if self.scenario_default and self.scenario_id is None:
            raise ValueError("a default scenario requires scenario metadata")
        if (self.selection_mode is None) != (
            self.selection_mode_control_name is None
        ):
            raise ValueError(
                "selection_mode and selection_mode_control_name must be supplied together"
            )
        if self.selection_mode is not None:
            _require_non_empty(self.selection_mode, name="selection_mode")
            _require_non_empty(
                self.selection_mode_control_name,
                name="selection_mode_control_name",
            )

    @property
    def authority_identity(self) -> tuple[str, str | None, str | None]:
        """Return exact non-presentation identity for this model choice."""

        return (
            self.model_value,
            self.selection_mode_control_name,
            self.selection_mode,
        )


@dataclass(frozen=True, slots=True)
class SidebarProjection:
    """Authority-neutral sidebar projection supplied by discovery/shared state."""

    runner_connectivity: tuple[str, str, str] = (
        "Runner not checked", "neutral", "Runner connection has not been checked."
    )
    runner_test_supported: bool = False
    treatments_contaminated: bool = False
    prompt_folder_visible: bool = False
    prompt_folder: str = ""
    benchmark_options: tuple[str, ...] = ()
    selected_benchmark: str | None = None
    runner_options: tuple[str, ...] = ()
    selected_runner: str | None = None
    model_visible: bool = True
    scenario_visible: bool = False
    reasoning_effort_control_name: str | None = None
    selected_reasoning_effort: str | None = None
    credentials_visible: bool = True
    model_options: tuple[str, ...] = ()
    selected_model: str | None = None
    model_choices: tuple[SidebarModelChoiceProjection, ...] = ()
    selected_model_selection_mode: str | None = None
    model_editable: bool = False
    model_required: bool = False
    model_discovery_determining_controls: tuple[str, ...] = ()
    model_discovery_context_fingerprints: tuple[str, ...] = ()
    credential_value: str = ""
    temperature: NumericInputProjection | None = None
    max_tokens: NumericInputProjection | None = None
    additional_controls: tuple[
        SidebarTextControlProjection
        | SidebarChoiceControlProjection
        | SidebarNumericControlProjection,
        ...,
    ] = ()
    resolved_configuration: tuple[SidebarResolvedTextProjection, ...] = ()
    build_plan_available: bool = False
    runs: tuple[RetainedRunProjection, ...] = ()
    prerequisite_diagnostics: tuple[
        SidebarPrerequisiteDiagnosticProjection,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        if (not isinstance(self.runner_connectivity, tuple)
                or len(self.runner_connectivity) != 3
                or any(not isinstance(value, str) or not value.strip()
                       for value in self.runner_connectivity)):
            raise ValueError("runner_connectivity requires label, tone and detail")
        benchmark_options = _visible_options(
            self.benchmark_options,
            name="benchmark_options",
        )
        runner_options = _visible_options(
            self.runner_options,
            name="runner_options",
        )
        model_options = _visible_options(
            self.model_options,
            name="model_options",
        )
        model_choices = tuple(self.model_choices)
        if any(
            not isinstance(choice, SidebarModelChoiceProjection)
            for choice in model_choices
        ):
            raise ValueError(
                "model_choices must contain only SidebarModelChoiceProjection values"
            )
        if model_options and model_choices:
            raise ValueError(
                "model_options and model_choices cannot both supply Model authority"
            )
        choice_labels = tuple(choice.label for choice in model_choices)
        if len(set(choice_labels)) != len(choice_labels):
            raise ValueError("model_choices must contain unique presentation labels")
        choice_identities = tuple(
            choice.authority_identity for choice in model_choices
        )
        if len(set(choice_identities)) != len(choice_identities):
            raise ValueError("model_choices must contain unique authority identities")
        object.__setattr__(self, "benchmark_options", benchmark_options)
        object.__setattr__(self, "runner_options", runner_options)
        _require_bool(self.runner_test_supported, name="runner_test_supported")
        _require_bool(self.model_visible, name="model_visible")
        _require_bool(self.scenario_visible, name="scenario_visible")
        _require_bool(self.credentials_visible, name="credentials_visible")
        object.__setattr__(self, "model_options", model_options)
        object.__setattr__(self, "model_choices", model_choices)
        object.__setattr__(
            self,
            "selected_benchmark",
            _selected_option(
                self.selected_benchmark,
                options=benchmark_options,
                name="selected_benchmark",
            ),
        )
        object.__setattr__(
            self,
            "selected_runner",
            _selected_option(
                self.selected_runner,
                options=runner_options,
                name="selected_runner",
            ),
        )
        _require_bool(self.model_editable, name="model_editable")
        _require_bool(self.model_required, name="model_required")
        selected_mode = self.selected_model_selection_mode
        if selected_mode is not None:
            selected_mode = _require_non_empty(
                selected_mode,
                name="selected_model_selection_mode",
            )
        if self.model_editable:
            if model_options or model_choices:
                raise ValueError(
                    "model options/choices must be empty when model_editable is true"
                )
            if selected_mode is not None:
                raise ValueError(
                    "editable Model input cannot carry a selection-mode identity"
                )
            selected_model = self.selected_model
            if selected_model is not None:
                selected_model = _require_non_empty(
                    selected_model,
                    name="selected_model",
                )
        elif model_choices:
            selected_model = self.selected_model
            if selected_model is None:
                if selected_mode is not None:
                    raise ValueError(
                        "selected_model_selection_mode requires selected_model"
                    )
            else:
                selected_model = _require_non_empty(
                    selected_model,
                    name="selected_model",
                )
                matches = tuple(
                    choice
                    for choice in model_choices
                    if choice.model_value == selected_model
                    and choice.selection_mode == selected_mode
                )
                if len(matches) != 1:
                    raise ValueError(
                        "selected Model authority must resolve to exactly one model choice"
                    )
        else:
            if selected_mode is not None:
                raise ValueError(
                    "selected_model_selection_mode requires discovered model_choices"
                )
            selected_model = _selected_option(
                self.selected_model,
                options=model_options,
                name="selected_model",
            )
        object.__setattr__(self, "selected_model", selected_model)
        object.__setattr__(
            self,
            "selected_model_selection_mode",
            selected_mode,
        )
        determining_controls = _visible_options(
            self.model_discovery_determining_controls,
            name="model_discovery_determining_controls",
        )
        object.__setattr__(
            self,
            "model_discovery_determining_controls",
            determining_controls,
        )
        context_fingerprints = _visible_options(
            self.model_discovery_context_fingerprints,
            name="model_discovery_context_fingerprints",
        )
        object.__setattr__(
            self,
            "model_discovery_context_fingerprints",
            context_fingerprints,
        )
        if not isinstance(self.credential_value, str):
            raise ValueError("credential_value must be a string")
        if self.temperature is not None and not isinstance(
            self.temperature,
            NumericInputProjection,
        ):
            raise ValueError("temperature must be NumericInputProjection or None")
        if self.max_tokens is not None and not isinstance(
            self.max_tokens,
            NumericInputProjection,
        ):
            raise ValueError("max_tokens must be NumericInputProjection or None")
        additional_controls = tuple(self.additional_controls)
        supported_control_types = (
            SidebarTextControlProjection,
            SidebarChoiceControlProjection,
            SidebarNumericControlProjection,
        )
        if any(
            not isinstance(control, supported_control_types)
            for control in additional_controls
        ):
            raise ValueError(
                "additional_controls must contain only supported sidebar controls"
            )
        control_names = tuple(
            control.control_name for control in additional_controls
        )
        if len(set(control_names)) != len(control_names):
            raise ValueError(
                "additional_controls must contain unique control_name values"
            )
        model_authority_control_names = {
            choice.selection_mode_control_name
            for choice in model_choices
            if choice.selection_mode_control_name is not None
        }
        if model_authority_control_names.intersection(control_names):
            raise ValueError(
                "model selection-mode authority must not be duplicated in additional_controls"
            )
        object.__setattr__(self, "additional_controls", additional_controls)
        resolved_configuration = tuple(self.resolved_configuration)
        if any(
            not isinstance(control, SidebarResolvedTextProjection)
            for control in resolved_configuration
        ):
            raise ValueError(
                "resolved_configuration must contain only SidebarResolvedTextProjection values"
            )
        resolved_names = tuple(
            control.control_name for control in resolved_configuration
        )
        if len(set(resolved_names)) != len(resolved_names):
            raise ValueError(
                "resolved_configuration must contain unique control_name values"
            )
        if set(resolved_names).intersection(control_names):
            raise ValueError(
                "resolved_configuration must not duplicate editable runner controls"
            )
        object.__setattr__(
            self,
            "resolved_configuration",
            resolved_configuration,
        )
        prerequisite_diagnostics = tuple(self.prerequisite_diagnostics)
        if any(
            not isinstance(
                diagnostic,
                SidebarPrerequisiteDiagnosticProjection,
            )
            for diagnostic in prerequisite_diagnostics
        ):
            raise ValueError(
                "prerequisite_diagnostics must contain only "
                "SidebarPrerequisiteDiagnosticProjection values"
            )
        diagnostic_names = tuple(
            diagnostic.diagnostic_name
            for diagnostic in prerequisite_diagnostics
        )
        if len(set(diagnostic_names)) != len(diagnostic_names):
            raise ValueError(
                "prerequisite_diagnostics must contain unique diagnostic_name values"
            )
        object.__setattr__(
            self,
            "prerequisite_diagnostics",
            prerequisite_diagnostics,
        )
        _require_bool(self.build_plan_available, name="build_plan_available")
        runs = tuple(self.runs)
        if any(not isinstance(run, RetainedRunProjection) for run in runs):
            raise ValueError("runs must contain only RetainedRunProjection values")
        run_ids = tuple(run.run_id for run in runs)
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("runs must contain unique run_id values")
        if sum(run.selected for run in runs) > 1:
            raise ValueError("runs may contain at most one selected retained run")
        object.__setattr__(self, "runs", runs)

    @property
    def selected_model_choice(self) -> SidebarModelChoiceProjection | None:
        """Return exact selected discovered choice without interpreting its label."""

        if not self.model_choices or self.selected_model is None:
            return None
        matches = tuple(
            choice
            for choice in self.model_choices
            if choice.model_value == self.selected_model
            and choice.selection_mode == self.selected_model_selection_mode
        )
        return matches[0] if len(matches) == 1 else None

    @property
    def planning_prerequisite_diagnostics(
        self,
    ) -> tuple[SidebarPrerequisiteDiagnosticProjection, ...]:
        """Return only diagnostics that gate canonical plan construction."""

        return tuple(
            diagnostic
            for diagnostic in self.prerequisite_diagnostics
            if diagnostic.operation == "planning"
        )

    @property
    def build_plan_effectively_available(self) -> bool:
        """Return caller availability after planning-scoped blockers only."""

        return (
            self.build_plan_available
            and not self.planning_prerequisite_diagnostics
        )


@dataclass(frozen=True, slots=True)
class ExecutionBoundaryProjection:
    """Read-only caller-supplied execution-boundary summary."""

    benchmark: str
    runner: str
    model: str
    cases: str
    boundary_fingerprint: str
    runtime_details: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "benchmark",
            "runner",
            "model",
            "cases",
            "boundary_fingerprint",
        ):
            _require_non_empty(getattr(self, name), name=name)
        details = tuple(self.runtime_details)
        for label, value in details:
            _require_non_empty(label, name="runtime detail label")
            _require_non_empty(value, name="runtime detail value")
        object.__setattr__(self, "runtime_details", details)

    @property
    def ordered_values(self) -> tuple[str, ...]:
        return (
            self.benchmark,
            self.runner,
            self.model,
        )


@dataclass(frozen=True, slots=True)
class RunPlanProjection:
    """Read-only caller-supplied run-plan summary."""

    treatments: str
    cases: str
    execution: str
    evaluation: str
    outputs: str
    treatment_files: tuple[str, ...] = ()
    execution_details: tuple[tuple[str, str], ...] = ()
    capture_runtime_advisory: str | None = None
    capture_runtime_advisory_tone: str = "neutral"

    def __post_init__(self) -> None:
        for name in ("treatments", "cases", "execution", "evaluation", "outputs"):
            _require_non_empty(getattr(self, name), name=name)
        if isinstance(self.treatment_files, (str, bytes)):
            raise ValueError("treatment_files must be file names")
        files = tuple(self.treatment_files)
        if (
            any(not isinstance(name, str) or not name for name in files)
            or len(set(files)) != len(files)
        ):
            raise ValueError("treatment_files must contain unique file names")
        object.__setattr__(self, "treatment_files", files)
        details = tuple(self.execution_details)
        for label, value in details:
            _require_non_empty(label, name="execution detail label")
            _require_non_empty(value, name="execution detail value")
        object.__setattr__(self, "execution_details", details)
        if self.capture_runtime_advisory is not None:
            _require_non_empty(self.capture_runtime_advisory, name="capture runtime advisory")
        if self.capture_runtime_advisory_tone not in {"warning", "neutral"}:
            raise ValueError("capture runtime advisory must be non-blocking warning or information")

    @property
    def capture_runtime_advisory_icon_role(self) -> str:
        return "status-warning" if self.capture_runtime_advisory_tone == "warning" else "status-neutral"

    @property
    def ordered_values(self) -> tuple[str, ...]:
        return (
            self.treatments,
            self.cases,
            self.execution,
            self.evaluation,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceProjection:
    """Caller-supplied presentation pages for one retained run."""

    progress: object
    results: object
    reports: object
    verification: object
    evidence: object
    scoring: object | None = None
    treatments_contaminated: bool = False

    @property
    def ordered_pages(self) -> tuple[object, ...]:
        return (
            self.progress,
            *((self.scoring,) if self.scoring is not None else ()),
            self.results,
            self.evidence,
            self.verification,
            self.reports,
        )


@dataclass(frozen=True, slots=True)
class CurrentRunProjection:
    """Caller-supplied run-summary state without local authority synthesis."""

    run_identity: str
    state_label: str
    state_tone: str
    timestamp: str
    execution_boundary: ExecutionBoundaryProjection
    run_plan: RunPlanProjection
    heading: str = "Current Run"
    is_prior_run: bool = False
    accept_plan_available: bool = False
    start_benchmark_available: bool = False
    delete_run_available: bool = False
    unscored: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.run_identity, name="run_identity")
        _require_non_empty(self.state_label, name="state_label")
        _require_non_empty(self.state_tone, name="state_tone")
        _require_non_empty(self.timestamp, name="timestamp")
        _require_non_empty(self.heading, name="heading")
        if not isinstance(self.execution_boundary, ExecutionBoundaryProjection):
            raise ValueError(
                "execution_boundary must be ExecutionBoundaryProjection"
            )
        if not isinstance(self.run_plan, RunPlanProjection):
            raise ValueError("run_plan must be RunPlanProjection")
        _require_bool(self.is_prior_run, name="is_prior_run")
        _require_bool(self.accept_plan_available, name="accept_plan_available")
        _require_bool(
            self.start_benchmark_available,
            name="start_benchmark_available",
        )
        _require_bool(self.delete_run_available, name="delete_run_available")
        if self.is_prior_run and (
            self.accept_plan_available or self.start_benchmark_available
        ):
            raise ValueError(
                "prior-run projection cannot expose Accept Plan or Start Benchmark"
            )
        if self.delete_run_available and not self.is_prior_run:
            raise ValueError(
                "delete_run_available requires an explicit prior-run projection"
            )


__all__ = [
    "NumericInputProjection", "SidebarTextControlProjection", "SidebarResolvedTextProjection",
    "SidebarChoiceControlProjection", "SidebarNumericControlProjection",
    "SidebarPrerequisiteDiagnosticProjection", "RetainedRunProjection",
    "SidebarModelChoiceProjection", "SidebarProjection", "ExecutionBoundaryProjection",
    "RunPlanProjection", "WorkspaceProjection", "CurrentRunProjection",
]
