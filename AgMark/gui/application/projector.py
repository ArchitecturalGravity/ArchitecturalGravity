"""Production shared-authority binding for the ArcGrav desktop GUI.

The controller in this module initiates coarse application operations and projects
their results onto the desktop shell. It deliberately does not sequence shared
runtime internals or manufacture benchmark authority; the injected application
boundary owns discovery, planning, acceptance, accepted execution, reporting,
verification, and retained-run authority.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from importlib import import_module
from pathlib import Path
from threading import RLock, Thread
from typing import Protocol
from weakref import ref

from AgMark.shared.application import (
    ApplicationDiscovery,
    ApplicationExecutionRequest,
    ApplicationPlanRequest,
    ApplicationPrerequisiteProjection,
    ApplicationPrerequisiteState,
    ApplicationRegistrationSource,
    ApplicationReportRequest,
    ApplicationRunDeletion,
    PlanningApplicationSession,
)
from AgMark.shared.reporting import GeneratedReportBundle
from AgMark.shared.runtime.artifacts import sha256_bytes
from AgMark.shared.runtime.identity import canonical_json_bytes
from AgMark.shared.runtime.orchestration import (
    AcceptedRun, ExecutedRun,
    AcceptedRunSnapshot,
    BlockedRun,
    RunPlan,
)
from AgMark.shared.validation import BenchmarkDiscoveryCandidate
from AgMark.shared.adapters.execution import (
    CanonicalObservationError,
    validate_retained_parity_observation,
)

from AgMark.gui.composition import (
    RepositoryPrerequisiteDiagnostic,
    RepositoryCompositionError,
    compose_repository_planning_session,
)
from AgMark.gui.diagnostics import (
    ApplicationEnvironmentProjection,
    EnvironmentDiagnosticEntry,
    application_failure_diagnostic,
    environment_failure_entry,
    environment_projection_failure_entry,
)
from AgMark.gui.requests import RepositoryApplicationRequestResolver, ResolvedRunnerTestRequest
from AgMark.gui.readiness import (
    derive_application_environment,
    derive_benchmark_evidence_readiness,
    derive_runner_readiness,
    probe_registered_runner_authentication,
    probe_registered_runner_model_discovery,
)
from AgMark.gui.shell.window import (
    BenchmarkShellWindow,
    CurrentRunProjection,
    ExecutionBoundaryProjection,
    PYSIDE6_AVAILABLE,
    RetainedRunProjection,
    RunPlanProjection,
    SidebarChoiceControlProjection,
    SidebarControlInputSnapshot,
    SidebarInputSnapshot,
    SidebarModelChoiceProjection,
    SidebarPrerequisiteDiagnosticProjection,
    SidebarProjection,
    SidebarTextControlProjection,
    WorkspaceProjection,
)
from AgMark.gui.projection.workspace import (
    SharedWorkspaceProjector,
    active_retained_progress_projection,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtGui import QIcon


_COMMANDS = frozenset(
    {
        "discover",
        "build_plan",
        "select_run",
        "delete_run",
        "accept_plan",
        "start_benchmark",
        "test_runner",
    }
)
_RUNNER_ENTRY_POINT = "arcgrav.adapters:entry_point"
_RUNNER_TEST_PROMPT = b"Echo: test"
_RUNNER_TEST_INPUT = b""
_RUNNER_TEST_GENERATION_ID = "gui-runner-test"
_EXTENSION_REFERENCE_PREFIX = "extensions:/"
# Entries hold only weak authority references and two short display strings.
# Identity keys avoid hashing the potentially large immutable observation bytes.
_EXECUTED_TERMINAL_STATES = {}
_EXECUTED_TERMINAL_STATES_LOCK = RLock()

from .contracts import (
    ApplicationProjectionUpdate, ApplicationProjector, ConsoleProjectionUpdate,
    DesktopCommandPort, RunnerTestResult, _text,
)

@dataclass(frozen=True, slots=True)
class _RunPresentationContext:
    """Presentation-only binding from one execution generation to its accepted plan."""

    generation_id: str
    plan: RunPlan
    plan_request: ApplicationPlanRequest
    accepted_at: str

def _redacted_additional_controls(
    values: tuple[SidebarControlInputSnapshot, ...],
) -> tuple[SidebarControlInputSnapshot, ...]:
    """Return additional controls with transient secret values removed."""

    return tuple(
        replace(value, value="")
        if getattr(value, "secret", False)
        else value
        for value in values
    )

def _redacted_intent(intent: SidebarInputSnapshot) -> SidebarInputSnapshot:
    return SidebarInputSnapshot(
        prompt_folder=intent.prompt_folder,
        excluded_treatments=intent.excluded_treatments,
        benchmark=intent.benchmark,
        runner=intent.runner,
        model=intent.model,
        credential="",
        temperature=intent.temperature,
        max_tokens=intent.max_tokens,
        additional_controls=_redacted_additional_controls(
            intent.additional_controls
        ),
        model_discovery_context_fingerprints=intent.model_discovery_context_fingerprints,
        iterations=intent.iterations,
        randomize_treatment_start=intent.randomize_treatment_start,
        randomize_per_iteration=intent.randomize_per_iteration,
        run_cache_validation_replays=intent.run_cache_validation_replays,
    )


def _verified_plan_boundary(plan_document, boundary_document):
    """Read presentation facts only from the boundary bound into this plan."""
    from AgMark.shared.runtime.identity import ExecutionBoundary
    boundary = ExecutionBoundary.from_document(boundary_document)
    if (boundary.fingerprint != plan_document.get("execution_boundary_fingerprint")
            or boundary.canonical_sha256 != plan_document.get("execution_boundary", {}).get("sha256")):
        raise ValueError("Execution boundary does not match the retained plan")
    return boundary.to_dict()


def _execution_boundary_model(boundary_document):
    """Show the frozen model and reasoning selection, without inventing defaults."""
    provider_runtime = boundary_document.get("provider_runtime")
    model = provider_runtime.get("model") if isinstance(provider_runtime, Mapping) else None
    if not isinstance(model, str) or not model:
        return "None declared"
    controls = {item["name"]: item["value"] for item in boundary_document["controls"]}
    reasoning = controls.get("reasoning_effort")
    if isinstance(reasoning, str) and reasoning:
        label = {"xhigh": "Extra High"}.get(reasoning, reasoning.replace("_", " ").capitalize())
        return f"{model} ({label})"
    return model


def _capture_runtime_presentation(plan_document, boundary_document=None):
    """Present only the reference comparison frozen when this plan was built."""
    from AgMark.shared.telemetry.runtime_reference import PLAN_EXTENSION, read_runtime_advisory
    extensions = plan_document.get("extensions", {})
    if not isinstance(extensions, Mapping):
        return (), None, "neutral"
    cache_replays = extensions.get("arcgrav.runtime:cache-validation-replays", True) is True
    replay_details = ("Cache validation replays",) if cache_replays else ()
    if PLAN_EXTENSION not in extensions:
        details = (("Capture", "• Cache validation replays"),) if cache_replays else ()
        return details, None, "neutral"
    advisory = read_runtime_advisory(extensions[PLAN_EXTENSION])
    reference = advisory.get("reference_runtime_version") or "Unavailable"
    selected = advisory.get("selected_runtime_version") or "Unavailable"
    capture_mode = "Not recorded"
    if boundary_document is not None:
        boundary = _verified_plan_boundary(plan_document, boundary_document)
        controls = {item["name"]: item["value"] for item in boundary["controls"]}
        selected_mode = controls.get("capture_mode")
        if isinstance(selected_mode, str):
            capture_mode = {"session": "Session", "telemetry": "Telemetry",
                "deep_telemetry": "Deep Telemetry"}.get(selected_mode, selected_mode)
    capture_version = "\n".join(f"• {item}" for item in
        (reference, f"Mode: {capture_mode}", *replay_details))
    details = (
        ("Runtime version", selected),
        ("Capture", capture_version),
    )
    if advisory.get("status") == "mismatch":
        return details, (
            f"Runtime / capture version mismatch: this plan uses {selected} but "
            f"the capture version is {reference}. Capture fields may differ or fail entierly."
            "This warning does not block benchmark runs."
        ), "warning"
    if advisory.get("status") != "match":
        return details, (
            "The capture and runtime versions could not be compared. "
            "This notice does not block benchmark runs."
        ), "neutral"
    return details, None, "neutral"


def _shared_prerequisite_projection(
    sidebar: SidebarProjection,
    *,
    prepared_authority: bool = False,
) -> ApplicationPrerequisiteProjection:
    """Translate GUI readiness into shared operation-scoped prerequisite evidence."""

    if not isinstance(sidebar, SidebarProjection):
        raise ValueError("sidebar must be a SidebarProjection")
    if type(prepared_authority) is not bool:
        raise TypeError("prepared_authority must be boolean")

    states: list[ApplicationPrerequisiteState] = []
    for diagnostic in sidebar.prerequisite_diagnostics:
        operation = diagnostic.operation
        if prepared_authority and operation == "planning":
            # Canonical planning has already succeeded. Any current readiness
            # condition that was needed to construct that authority now owns
            # execution-time revalidation unless it is explicitly acceptance-scoped.
            operation = "execution"
        states.append(
            ApplicationPrerequisiteState(
                prerequisite_id=diagnostic.diagnostic_name,
                operation=operation,
                satisfied=False,
                diagnostic=diagnostic.message,
            )
        )
    return ApplicationPrerequisiteProjection.from_states(tuple(states))

def _matching_model_choice(
    choices: Sequence[SidebarModelChoiceProjection],
    *,
    model_value: object,
    control_values: Mapping[str, object],
) -> SidebarModelChoiceProjection | None:
    """Resolve one model choice from exact authority fields, never its label."""

    if not isinstance(model_value, str) or not model_value:
        return None
    candidates = [
        choice
        for choice in choices
        if choice.model_value == model_value
    ]
    matches = []
    for choice in candidates:
        if choice.selection_mode is None:
            matches.append(choice)
            continue
        if (
            choice.selection_mode_control_name is not None
            and control_values.get(choice.selection_mode_control_name)
            == choice.selection_mode
        ):
            matches.append(choice)
    if len(matches) == 1:
        return matches[0]
    if not matches and len(candidates) == 1:
        # A non-comparative presentation mode may be absent from an accepted
        # boundary. A unique concrete model identity is still unambiguous.
        return candidates[0]
    return None

def _selected_additional_control(
    control: SidebarTextControlProjection | SidebarChoiceControlProjection,
    control_values: Mapping[str, object],
) -> SidebarTextControlProjection | SidebarChoiceControlProjection:
    """Reapply current non-secret intent to one registration-derived control."""

    if control.control_name not in control_values:
        return control
    value = control_values[control.control_name]
    if isinstance(control, SidebarTextControlProjection):
        if isinstance(value, str):
            return replace(control, value=value)
        return control
    if isinstance(value, str) and value in control.options:
        return replace(control, selected_value=value)
    return control

def _repository_sidebar_projection(
    template: SidebarProjection | None,
    diagnostics: Sequence[RepositoryPrerequisiteDiagnostic],
) -> SidebarProjection:
    """Merge repository prerequisite blockers into caller presentation state."""

    projection = template or SidebarProjection()
    existing_names = {
        diagnostic.diagnostic_name
        for diagnostic in projection.prerequisite_diagnostics
    }
    repository_diagnostics = tuple(
        SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name=diagnostic.diagnostic_name,
            message=diagnostic.message,
            remediation=diagnostic.remediation,
        )
        for diagnostic in diagnostics
        if diagnostic.diagnostic_name not in existing_names
    )
    if not repository_diagnostics:
        return projection
    return replace(
        projection,
        prerequisite_diagnostics=(
            projection.prerequisite_diagnostics + repository_diagnostics
        ),
    )

def _application_status_for_sidebar(
    sidebar: SidebarProjection,
    status: tuple[str, str] | None,
) -> tuple[str, str] | None:
    """Keep visible application status aligned with actual prerequisite blockers."""

    if sidebar.prerequisite_diagnostics and (
        status is None or status[1] != "error"
    ):
        return ("Prerequisites unresolved", "warning")
    return status

def _registration_label(value: object) -> str:
    registration_id = getattr(value, "registration_id", None)
    registration_version = getattr(value, "registration_version", None)
    if (
        not isinstance(registration_id, str)
        or not registration_id
        or not isinstance(registration_version, str)
        or not registration_version
    ):
        raise ValueError("discovered registration identity is invalid")
    return f"{registration_id}@{registration_version}"

def _identity_label(value: object) -> str:
    identity_id = getattr(value, "id", None)
    identity_version = getattr(value, "version", None)
    if (
        not isinstance(identity_id, str)
        or not identity_id
        or not isinstance(identity_version, str)
        or not identity_version
    ):
        raise ValueError("shared identity reference is invalid")
    return f"{identity_id}@{identity_version}"

def _document_identity_label(value: object, *, name: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{name} identity is invalid")
    identity_id = value.get("id")
    identity_version = value.get("version")
    if (
        not isinstance(identity_id, str)
        or not identity_id
        or not isinstance(identity_version, str)
        or not identity_version
    ):
        raise ValueError(f"{name} identity is invalid")
    return f"{identity_id}@{identity_version}"

def _completion_state(boundary, terminal):
    state = getattr(boundary, "report_state", lambda _: (None, None))(terminal.generation_id)[0]
    if state == "complete":
        return "Completed · Report ready", "success"
    if state in {"validation_failed", "report_failed"}:
        return "Execution finished · Report release failed", "error"
    return _terminal_state(terminal)


def _terminal_state(value: AcceptedRun | BlockedRun) -> tuple[str, str]:
    """Map exact terminal authority to the stable desktop lifecycle vocabulary."""

    if type(value) is BlockedRun:
        return "Failed", "error"
    if type(value) is ExecutedRun:
        if value.cancelled:
            return "Cancelled", "warning"
        key = id(value)
        with _EXECUTED_TERMINAL_STATES_LOCK:
            cached = _EXECUTED_TERMINAL_STATES.get(key)
            if cached is not None and cached[0]() is value:
                return cached[1]
        state = (("Completed with errors", "warning") if any(
            json.loads(raw).get("terminal_status") != "completed"
            for raw in value.treatment_observations) else ("Completed", "success"))
        def release(reference):
            with _EXECUTED_TERMINAL_STATES_LOCK:
                cached = _EXECUTED_TERMINAL_STATES.get(key)
                if cached is not None and cached[0] is reference:
                    _EXECUTED_TERMINAL_STATES.pop(key, None)
        with _EXECUTED_TERMINAL_STATES_LOCK:
            _EXECUTED_TERMINAL_STATES[key] = (ref(value, release), state)
        return state
    if type(value) in (AcceptedRun, ExecutedRun):
        return "Completed", "success"
    raise TypeError("terminal result must be AcceptedRun or BlockedRun")

def _bounded_text(value: str, *, limit: int = 240) -> str:
    rendered = " ".join(value.splitlines()).strip()
    if not rendered:
        rendered = value.strip()
    return rendered[:limit] + ("..." if len(rendered) > limit else "")

def _decode_retained_json_documents(
    values: object,
    *,
    label: str,
) -> tuple[tuple[Mapping[str, object], ...], tuple[str, ...]]:
    documents: list[Mapping[str, object]] = []
    diagnostics: list[str] = []
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values,
        Sequence,
    ):
        return (), (f"Retained {label} collection is unavailable.\n",)
    for index, raw in enumerate(values, start=1):
        if not isinstance(raw, (bytes, bytearray)):
            diagnostics.append(
                f"Retained {label} {index} is not UTF-8 JSON bytes.\n"
            )
            continue
        try:
            value = json.loads(bytes(raw).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            diagnostics.append(
                f"Retained {label} {index} could not be decoded as UTF-8 JSON: "
                f"{exc.__class__.__name__}.\n"
            )
            continue
        if not isinstance(value, Mapping):
            diagnostics.append(f"Retained {label} {index} is not a JSON object.\n")
            continue
        if label == "treatment observation":
            try:
                validate_retained_parity_observation(value)
            except CanonicalObservationError:
                diagnostics.append(
                    f"Retained {label} {index} has invalid canonical execution evidence.\n"
                )
                continue
        documents.append(value)
    return tuple(documents), tuple(diagnostics)

def _extension_reference_key(reference: object) -> str | None:
    if not isinstance(reference, str) or not reference:
        return None
    if reference.startswith(_EXTENSION_REFERENCE_PREFIX):
        return reference.removeprefix(_EXTENSION_REFERENCE_PREFIX)
    marker = "#" + _EXTENSION_REFERENCE_PREFIX
    if marker in reference:
        return reference.rsplit(marker, 1)[1]
    return None

def _decode_extension_text(
    observation: Mapping[str, object],
) -> tuple[str | None, str | None]:
    response = observation.get("response")
    extensions = observation.get("extensions")
    if not isinstance(response, Mapping):
        return None, "Retained observation response metadata is unavailable.\n"
    if not isinstance(extensions, Mapping):
        return None, "Retained observation extensions are unavailable.\n"
    key = _extension_reference_key(response.get("reference"))
    if key is None:
        return None, "Retained observation response reference is unsupported.\n"
    encoded = extensions.get(key)
    if not isinstance(encoded, str) or not encoded:
        return None, f"Retained response extension {key!r} is unavailable.\n"
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except Exception as exc:
        return (
            None,
            f"Retained response extension {key!r} could not be base64-decoded: "
            f"{exc.__class__.__name__}.\n",
        )
    if response.get("availability") != "retained":
        return None, "Retained observation response is unavailable.\n"
    if response.get("sha256") != sha256_bytes(raw):
        return None, "Retained observation response integrity check failed.\n"
    byte_length = response.get("byte_length")
    if byte_length is not None and (
        type(byte_length) is not int or byte_length != len(raw)
    ):
        return None, "Retained observation response length check failed.\n"
    return raw.decode("utf-8", errors="replace"), None

def _telemetry_map(observation: Mapping[str, object]) -> Mapping[str, object]:
    telemetry: dict[str, object] = {}
    raw_values = observation.get("telemetry", ())
    if isinstance(raw_values, (str, bytes, bytearray)) or not isinstance(
        raw_values,
        Sequence,
    ):
        return telemetry
    for value in raw_values:
        if not isinstance(value, Mapping):
            continue
        name = value.get("name")
        if isinstance(name, str) and name:
            telemetry[name] = value.get("value")
    return telemetry

def _byte_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value

def _treatment_label(observation: Mapping[str, object], index: int) -> str:
    treatment = observation.get("treatment_id")
    if isinstance(treatment, str) and treatment.strip():
        return treatment.strip()
    observation_id = observation.get("observation_id")
    if isinstance(observation_id, str) and observation_id.strip():
        return observation_id.strip()
    return f"observation-{index}"

def _runner_label(observations: Sequence[Mapping[str, object]]) -> str:
    for observation in observations:
        runner = observation.get("runner")
        if not isinstance(runner, Mapping):
            continue
        runner_id = runner.get("id")
        runner_version = runner.get("version")
        if isinstance(runner_id, str) and runner_id:
            if isinstance(runner_version, str) and runner_version:
                return f"{runner_id}@{runner_version}"
            return runner_id
    return "Unavailable"

def _named_byte_counts(
    observations: Sequence[Mapping[str, object]],
    telemetry_name: str,
) -> tuple[int | None, tuple[str, ...]]:
    total = 0
    observed = False
    parts: list[str] = []
    for index, observation in enumerate(observations, start=1):
        value = _byte_count(_telemetry_map(observation).get(telemetry_name))
        if value is None:
            parts.append(f"{_treatment_label(observation, index)}=unavailable")
            continue
        observed = True
        total += value
        parts.append(f"{_treatment_label(observation, index)}={value:,}")
    return (total if observed else None), tuple(parts)

@dataclass(frozen=True)
class PreparedApplicationResult:
    """Worker-prepared presentation evidence; UI state is applied separately."""

    command: str
    result: object
    workspace: object | None = None
    workspace_prepared: bool = False
    historical_current: CurrentRunProjection | None = None
    console: object | None = None
    history_diagnostics: tuple[str, ...] | None = None


class SharedApplicationProjector:
    """Default projector for exact shared lifecycle identities and states."""

    def __init__(
        self,
        boundary: PlanningSessionApplicationBoundary,
        *,
        sidebar_template: SidebarProjection | None = None,
        workspace_projector: WorkspaceProjector | None = None,
        runner_sources: Sequence[ApplicationRegistrationSource] | None = None,
        benchmark_candidates: Sequence[BenchmarkDiscoveryCandidate] | None = None,
        repository_root: str | Path | None = None,
        executable_resolver: Callable[[str], str | None] | None = None,
        authentication_probe: Callable[..., bool | None] | None = None,
        model_discovery_probe: Callable[
            ..., Mapping[str, object] | None
        ] | None = None,
        environment_entries: Sequence[EnvironmentDiagnosticEntry] = (),
    ) -> None:
        from .session_boundary import PlanningSessionApplicationBoundary

        if not isinstance(boundary, PlanningSessionApplicationBoundary):
            raise ValueError(
                "boundary must be PlanningSessionApplicationBoundary"
            )
        if workspace_projector is not None and not callable(workspace_projector):
            raise ValueError("workspace_projector must be callable or None")
        if runner_sources is not None:
            if isinstance(runner_sources, (str, bytes)) or not isinstance(
                runner_sources, Sequence
            ):
                raise ValueError("runner_sources must be a sequence or None")
            if any(
                not isinstance(source, ApplicationRegistrationSource)
                for source in runner_sources
            ):
                raise ValueError(
                    "runner_sources must contain ApplicationRegistrationSource values"
                )
        if benchmark_candidates is not None:
            if isinstance(benchmark_candidates, (str, bytes)) or not isinstance(
                benchmark_candidates, Sequence
            ):
                raise ValueError("benchmark_candidates must be a sequence or None")
            if any(
                not isinstance(candidate, BenchmarkDiscoveryCandidate)
                for candidate in benchmark_candidates
            ):
                raise ValueError(
                    "benchmark_candidates must contain BenchmarkDiscoveryCandidate values"
                )
        if (benchmark_candidates is None) != (repository_root is None):
            raise ValueError(
                "benchmark_candidates and repository_root must be supplied together"
            )
        if repository_root is not None and not isinstance(repository_root, (str, Path)):
            raise ValueError("repository_root must be a string, pathlib.Path, or None")
        if executable_resolver is not None and not callable(executable_resolver):
            raise ValueError("executable_resolver must be callable or None")
        if authentication_probe is not None and not callable(authentication_probe):
            raise ValueError("authentication_probe must be callable or None")
        if model_discovery_probe is not None and not callable(model_discovery_probe):
            raise ValueError("model_discovery_probe must be callable or None")
        if isinstance(environment_entries, (str, bytes)) or not isinstance(
            environment_entries, Sequence
        ):
            raise ValueError("environment_entries must be a sequence")
        if any(
            not isinstance(entry, EnvironmentDiagnosticEntry)
            for entry in environment_entries
        ):
            raise ValueError(
                "environment_entries must contain EnvironmentDiagnosticEntry values"
            )
        self._boundary = boundary
        self._sidebar_template = sidebar_template or SidebarProjection()
        self._workspace_projector = (
            workspace_projector
            if workspace_projector is not None
            else SharedWorkspaceProjector(boundary)
        )
        self._runner_sources = (
            None if runner_sources is None else tuple(runner_sources)
        )
        self._benchmark_candidates = (
            None if benchmark_candidates is None else tuple(benchmark_candidates)
        )
        self._repository_root = repository_root
        self._executable_resolver = executable_resolver
        self._authentication_probe = authentication_probe
        self._model_discovery_probe = model_discovery_probe
        self._environment_entries = tuple(environment_entries)
        self._viewing_prior_run_id: str | None = None
        self._mounted_workspace_run_id: str | None = None
        self._pending_delete_run_id: str | None = None
        self._suppress_current_projection_after_delete = False

    def _sidebar(
        self,
        *,
        sidebar_intent: SidebarInputSnapshot | None = None,
        selected_runner_override: str | None = None,
        runner_selection_changed: bool = False,
    ) -> SidebarProjection:
        discovery = self._boundary.discovery
        template = self._sidebar_template
        if discovery is None:
            return SidebarProjection(
                model_visible=template.model_visible,
                credentials_visible=template.credentials_visible,
                model_options=template.model_options,
                selected_model=template.selected_model,
                model_choices=template.model_choices,
                scenario_visible=template.scenario_visible,
                selected_model_selection_mode=(
                    template.selected_model_selection_mode
                ),
                model_editable=template.model_editable,
                model_required=template.model_required,
                model_discovery_determining_controls=(
                    template.model_discovery_determining_controls
                ),
                model_discovery_context_fingerprints=(
                    template.model_discovery_context_fingerprints
                ),
                temperature=template.temperature,
                max_tokens=template.max_tokens,
                additional_controls=_redacted_additional_controls(
                    template.additional_controls
                ),
                resolved_configuration=template.resolved_configuration,
                build_plan_available=template.build_plan_available,
                prerequisite_diagnostics=template.prerequisite_diagnostics,
            )

        benchmark_options = tuple(
            _registration_label(value) for value in discovery.benchmarks
        )
        runner_options = tuple(
            _registration_label(value) for value in discovery.runners
        )

        plan = self._boundary.session.prepared_plan
        request = self._boundary.plan_request
        selected_benchmark = (
            sidebar_intent.benchmark
            if (
                sidebar_intent is not None
                and sidebar_intent.benchmark in benchmark_options
            )
            else (
                _identity_label(plan.benchmark)
                if plan is not None
                else (
                    template.selected_benchmark
                    if template.selected_benchmark in benchmark_options
                    else (benchmark_options[0] if benchmark_options else None)
                )
            )
        )
        selected_runner: str | None = (
            selected_runner_override
            if selected_runner_override in runner_options
            else None
        )
        if (
            selected_runner is None
            and sidebar_intent is not None
            and sidebar_intent.runner in runner_options
        ):
            selected_runner = sidebar_intent.runner

        runner_test_supported = template.runner_test_supported
        model_visible = template.model_visible
        credentials_visible = template.credentials_visible
        model_options = list(template.model_options)
        model_choices = list(template.model_choices)
        scenario_visible = template.scenario_visible
        reasoning_effort_control_name = template.reasoning_effort_control_name
        selected_reasoning_effort = template.selected_reasoning_effort
        selected_model = template.selected_model
        selected_model_selection_mode = (
            template.selected_model_selection_mode
        )
        model_editable = template.model_editable
        model_required = template.model_required
        model_discovery_determining_controls = (
            template.model_discovery_determining_controls
        )
        model_discovery_context_fingerprints = (
            template.model_discovery_context_fingerprints
        )
        authentication_satisfied = False
        runner_connectivity = ("Runner not checked", "neutral",
                               "Runner connection has not been checked.")

        if request is not None:
            boundary_document = request.execution_boundary.to_dict()
            if selected_runner is None:
                selected_runner = _document_identity_label(
                    boundary_document["runner"],
                    name="runner",
                )
            provider_runtime = boundary_document.get("provider_runtime")
            if isinstance(provider_runtime, dict):
                exact_model = provider_runtime.get("model")
                if (
                    sidebar_intent is None
                    and isinstance(exact_model, str)
                    and exact_model
                ):
                    boundary_control_values = {
                        control.get("name"): control.get("value")
                        for control in boundary_document.get("controls", ())
                        if isinstance(control, Mapping)
                        and isinstance(control.get("name"), str)
                        and "value" in control
                    }
                    model_choice = _matching_model_choice(
                        model_choices,
                        model_value=exact_model,
                        control_values=boundary_control_values,
                    )
                    if model_choice is not None:
                        selected_model = model_choice.model_value
                        selected_model_selection_mode = (
                            model_choice.selection_mode
                        )
                    elif not model_choices:
                        if exact_model not in model_options:
                            model_options.append(exact_model)
                        selected_model = exact_model

        if selected_runner is None:
            selected_runner = (
                template.selected_runner
                if template.selected_runner in runner_options
                else (runner_options[0] if runner_options else None)
            )

        if (
            sidebar_intent is not None
            and not runner_selection_changed
            and isinstance(sidebar_intent.model, str)
            and sidebar_intent.model
        ):
            intent_control_values = {
                control.control_name: control.value
                for control in sidebar_intent.additional_controls
                if control.value is not None
            }
            model_choice = _matching_model_choice(
                model_choices,
                model_value=sidebar_intent.model,
                control_values=intent_control_values,
            )
            if model_choice is not None:
                selected_model = model_choice.model_value
                selected_model_selection_mode = model_choice.selection_mode
            elif not model_choices:
                if sidebar_intent.model not in model_options:
                    model_options.append(sidebar_intent.model)
                selected_model = sidebar_intent.model

        temperature = template.temperature
        if (
            sidebar_intent is not None
            and not runner_selection_changed
            and temperature is not None
            and sidebar_intent.temperature is not None
        ):
            temperature = replace(
                temperature,
                value=sidebar_intent.temperature,
            )

        max_tokens = template.max_tokens
        if (
            sidebar_intent is not None
            and not runner_selection_changed
            and max_tokens is not None
            and sidebar_intent.max_tokens is not None
        ):
            max_tokens = replace(
                max_tokens,
                value=sidebar_intent.max_tokens,
            )

        additional_controls = tuple(template.additional_controls)
        resolved_configuration = tuple(template.resolved_configuration)
        prerequisite_diagnostics = tuple(template.prerequisite_diagnostics)
        if self._runner_sources is not None and selected_runner is not None:
            discovered_runner = next(
                (
                    value
                    for value in discovery.runners
                    if _registration_label(value) == selected_runner
                ),
                None,
            )
            if discovered_runner is not None:
                selected_control_values: dict[str, object] = {}
                if request is not None:
                    boundary_document = request.execution_boundary.to_dict()
                    boundary_runner = _document_identity_label(
                        boundary_document["runner"],
                        name="runner",
                    )
                    if boundary_runner == selected_runner and not runner_selection_changed:
                        boundary_controls = boundary_document.get("controls", ())
                        if (
                            not isinstance(boundary_controls, (str, bytes))
                            and isinstance(boundary_controls, Sequence)
                        ):
                            for control in boundary_controls:
                                if not isinstance(control, Mapping):
                                    continue
                                control_name = control.get("name")
                                if (
                                    isinstance(control_name, str)
                                    and control_name
                                    and "value" in control
                                ):
                                    selected_control_values[control_name] = control.get(
                                        "value"
                                    )
                        # Retained launch identities are deliberately redacted.
                        # Rehydrate only from this live plan's transient inputs;
                        # never feed runtime/codex back into process discovery.
                        selected_control_values.update(
                            self._boundary.transient_plan_launch_controls
                        )

                # The switch callback receives a snapshot of the previous
                # runner's sidebar. Even identically named controls (for
                # example codex_binary) belong to that previous registration.
                # Resolve new defaults from the selected registration instead.
                if sidebar_intent is not None and not runner_selection_changed:
                    for control in sidebar_intent.additional_controls:
                        if not control.secret and control.value is not None:
                            selected_control_values[control.control_name] = control.value

                readiness = derive_runner_readiness(
                    discovered_runner=discovered_runner,
                    runner_sources=self._runner_sources,
                    executable_resolver=self._executable_resolver,
                    authentication_probe=self._authentication_probe,
                    model_discovery_probe=self._model_discovery_probe,
                    selected_control_values=selected_control_values,
                )
                runner_test_supported = readiness.runner_test_supported
                runner_connectivity = readiness.runner_connectivity
                authentication_satisfied = readiness.authentication_satisfied
                model_visible = readiness.model_control_present
                scenario_visible = readiness.scenario_visible
                reasoning_effort_control_name = readiness.reasoning_effort_control_name
                selected_reasoning_effort = selected_control_values.get(reasoning_effort_control_name)
                credentials_visible = readiness.credentials_required
                resolved_configuration = readiness.resolved_configuration
                if readiness.model_control_present:
                    model_options = list(readiness.model_options)
                    model_choices = list(readiness.model_choices)
                    selected_model = readiness.selected_model
                    selected_model_selection_mode = (
                        readiness.selected_model_selection_mode
                    )
                    model_editable = readiness.model_editable
                    model_required = readiness.model_required
                    model_discovery_determining_controls = (
                        readiness.model_discovery_determining_controls
                    )
                    model_discovery_context_fingerprints = (
                        readiness.model_discovery_context_fingerprints
                    )

                    intent_model = (
                        sidebar_intent.model
                        if (
                            sidebar_intent is not None
                            and isinstance(sidebar_intent.model, str)
                            and sidebar_intent.model.strip()
                        )
                        else None
                    )
                    discovery_context_matches = (
                        not readiness.model_discovery_authoritative
                        or not model_discovery_context_fingerprints
                        or (
                            sidebar_intent is not None
                            and sidebar_intent.model_discovery_context_fingerprints
                            == model_discovery_context_fingerprints
                        )
                    )
                    if intent_model is not None and discovery_context_matches:
                        intent_control_values = {
                            control.control_name: control.value
                            for control in sidebar_intent.additional_controls
                            if control.value is not None
                        }
                        intent_choice = _matching_model_choice(
                            model_choices,
                            model_value=intent_model,
                            control_values=intent_control_values,
                        )
                        if intent_choice is not None:
                            selected_model = intent_choice.model_value
                            selected_model_selection_mode = (
                                intent_choice.selection_mode
                            )
                        elif model_editable:
                            selected_model = intent_model
                        elif (
                            not readiness.model_discovery_authoritative
                            and intent_model in model_options
                        ):
                            selected_model = intent_model

                    if request is not None and sidebar_intent is None:
                        boundary_document = request.execution_boundary.to_dict()
                        provider_runtime = boundary_document.get("provider_runtime")
                        if isinstance(provider_runtime, dict):
                            exact_model = provider_runtime.get("model")
                            if isinstance(exact_model, str) and exact_model:
                                boundary_control_values = {
                                    control.get("name"): control.get("value")
                                    for control in boundary_document.get("controls", ())
                                    if isinstance(control, Mapping)
                                    and isinstance(control.get("name"), str)
                                    and "value" in control
                                }
                                boundary_choice = _matching_model_choice(
                                    model_choices,
                                    model_value=exact_model,
                                    control_values=boundary_control_values,
                                )
                                if boundary_choice is not None:
                                    selected_model = boundary_choice.model_value
                                    selected_model_selection_mode = (
                                        boundary_choice.selection_mode
                                    )
                                elif model_editable:
                                    selected_model = exact_model
                                elif not readiness.model_discovery_authoritative:
                                    if exact_model not in model_options:
                                        model_options.append(exact_model)
                                    selected_model = exact_model
                else:
                    model_options = []
                    model_choices = []
                    selected_model = None
                    selected_model_selection_mode = None
                    model_editable = False
                    model_required = False
                    model_discovery_determining_controls = ()
                    model_discovery_context_fingerprints = ()

                if readiness.numeric_controls_projected:
                    temperature = readiness.temperature
                    max_tokens = readiness.max_tokens
                    if sidebar_intent is not None:
                        if (
                            temperature is not None
                            and temperature.editable
                            and sidebar_intent.temperature is not None
                            and temperature.minimum
                            <= sidebar_intent.temperature
                            <= temperature.maximum
                        ):
                            temperature = replace(
                                temperature,
                                value=sidebar_intent.temperature,
                            )
                        if (
                            max_tokens is not None
                            and max_tokens.editable
                            and sidebar_intent.max_tokens is not None
                            and max_tokens.minimum
                            <= sidebar_intent.max_tokens
                            <= max_tokens.maximum
                        ):
                            max_tokens = replace(
                                max_tokens,
                                value=sidebar_intent.max_tokens,
                            )

                current_additional_controls = tuple(
                    _selected_additional_control(
                        control,
                        selected_control_values,
                    )
                    for control in readiness.additional_controls
                )
                derived_names = {
                    control.control_name
                    for control in current_additional_controls
                }
                additional_controls = tuple(
                    control
                    for control in additional_controls
                    if control.control_name not in derived_names
                ) + current_additional_controls
                derived_diagnostic_names = {
                    diagnostic.diagnostic_name
                    for diagnostic in readiness.diagnostics
                }
                prerequisite_diagnostics = tuple(
                    diagnostic
                    for diagnostic in prerequisite_diagnostics
                    if diagnostic.diagnostic_name
                    not in derived_diagnostic_names
                ) + readiness.diagnostics


        if (
            self._benchmark_candidates is not None
            and self._repository_root is not None
            and selected_benchmark is not None
        ):
            discovered_benchmark = next(
                (
                    value
                    for value in discovery.benchmarks
                    if _registration_label(value) == selected_benchmark
                ),
                None,
            )
            if discovered_benchmark is not None:
                evidence_readiness = derive_benchmark_evidence_readiness(
                    discovered_benchmark=discovered_benchmark,
                    benchmark_candidates=self._benchmark_candidates,
                    repository_root=self._repository_root,
                )
                derived_diagnostic_names = {
                    diagnostic.diagnostic_name
                    for diagnostic in evidence_readiness.diagnostics
                }
                prerequisite_diagnostics = tuple(
                    diagnostic
                    for diagnostic in prerequisite_diagnostics
                    if diagnostic.diagnostic_name
                    not in derived_diagnostic_names
                ) + evidence_readiness.diagnostics

        retained_runs = self._boundary.retained_runs
        retained_by_id = {
            run.generation_id: run
            for run in retained_runs
        }
        execution_request = self._boundary.execution_request
        current_terminal_id = (
            execution_request.generation_id
            if (
                execution_request is not None
                and execution_request.generation_id in retained_by_id
            )
            else None
        )

        run_rows: list[RetainedRunProjection] = []
        for run in retained_runs:
            context = self._boundary.run_context(run.generation_id)
            state_label, state_tone = _completion_state(self._boundary, run)
            run_rows.append(
                RetainedRunProjection(
                    run_id=run.generation_id,
                    display_identity=run.generation_id,
                    state_label=state_label,
                    state_tone=state_tone,
                    timestamp=(
                        context.accepted_at
                        if context is not None
                        else "Retained run"
                    ),
                    selected=(
                        not self._suppress_current_projection_after_delete
                        and (
                            run.generation_id == self._viewing_prior_run_id
                            or (
                                self._viewing_prior_run_id is None
                                and run.generation_id == current_terminal_id
                            )
                        )
                    ),
                    selectable=True,
                )
            )

        plan = self._boundary.session.prepared_plan
        active_context = (
            self._boundary.run_context(execution_request.generation_id)
            if execution_request is not None
            else None
        )
        active_current = (
            execution_request is not None
            and active_context is not None
            and plan is not None
            and active_context.plan.run_plan_id == plan.run_plan_id
            and execution_request.generation_id not in retained_by_id
        )
        if (
            active_current
            and current_terminal_id is None
            and not self._suppress_current_projection_after_delete
        ):
            run_rows.append(
                RetainedRunProjection(
                    run_id=execution_request.generation_id,
                    display_identity=execution_request.generation_id,
                    state_label="Running",
                    state_tone="active",
                    timestamp=active_context.accepted_at,
                    selectable=False,
                )
            )

        for run in self._boundary.historical_runs:
            run_rows.append(RetainedRunProjection(
                run_id=run.generation_id, display_identity=run.generation_id,
                state_label=run.state_label, state_tone=run.state_tone,
                timestamp=run.timestamp, selected=run.generation_id == self._viewing_prior_run_id,
                selectable=True))
        runs = tuple(run_rows)

        from AgMark.shared.treatments import CONTENT, POLICY, contaminated, freeze
        treatment_warning = False
        if self._repository_root is not None:
            for candidate in self._benchmark_candidates or ():
                registration = candidate.registration
                if registration.get("registration_id", "") + "@" + registration.get("registration_version", "") == selected_benchmark:
                    break
            else:
                candidate = None
            if candidate is not None and registration.get("extensions", {}).get(POLICY, {}).get("mismatch") == "contaminated":
                from AgMark.gui.requests.repository_resources import _resource, _selected_authority, _safe_file
                try:
                    _, document = _resource(Path(self._repository_root), registration, _selected_authority(registration)["treatment_set"], "treatment_set")
                    entries = [freeze(t["treatment_id"], t["prompt"], _safe_file(Path(self._repository_root),
                        t["prompt"]["reference"], package_root=candidate.package_root).read_bytes())
                        for t in document["treatments"] if t["treatment_id"] not in (sidebar_intent.excluded_treatments if sidebar_intent else ())]
                    treatment_warning = contaminated({"extensions": {CONTENT: entries}})
                except (OSError, ValueError, RepositoryCompositionError) as exc:
                    prerequisite_diagnostics += (SidebarPrerequisiteDiagnosticProjection(
                        "treatment-content", "Treatment content is unavailable for planning.",
                        "Restore the selected benchmark resources before building a plan.",
                        details=str(exc)),)

        if plan is not None and sidebar_intent is None:
            treatment_warning = contaminated(plan.to_dict())
        return SidebarProjection(
            treatments_contaminated=treatment_warning,
            runner_connectivity=runner_connectivity,
            prompt_folder_visible=any(b.registration_id + "@" + b.registration_version == selected_benchmark and "unscored-prompt-folder" in b.capabilities for b in discovery.benchmarks),
            prompt_folder=sidebar_intent.prompt_folder if sidebar_intent else "",
            benchmark_options=benchmark_options,
            runner_test_supported=runner_test_supported,
            model_visible=model_visible,
            scenario_visible=scenario_visible,
            reasoning_effort_control_name=reasoning_effort_control_name,
            selected_reasoning_effort=selected_reasoning_effort,
            credentials_visible=credentials_visible,
            selected_benchmark=selected_benchmark,
            runner_options=runner_options,
            selected_runner=selected_runner,
            model_options=tuple(model_options),
            selected_model=selected_model,
            model_choices=tuple(model_choices),
            selected_model_selection_mode=selected_model_selection_mode,
            model_editable=model_editable,
            model_required=model_required,
            model_discovery_determining_controls=(
                model_discovery_determining_controls
            ),
            model_discovery_context_fingerprints=(
                model_discovery_context_fingerprints
            ),
            credential_value=(
                ""
                if (
                    not credentials_visible
                    or authentication_satisfied
                    or runner_selection_changed
                )
                else (
                    sidebar_intent.credential
                    if sidebar_intent is not None
                    else ""
                )
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            additional_controls=_redacted_additional_controls(
                additional_controls
            ),
            resolved_configuration=resolved_configuration,
            build_plan_available=bool(benchmark_options and runner_options),
            runs=runs,
            prerequisite_diagnostics=prerequisite_diagnostics,
        )

    def prerequisite_projection(
        self,
        intent: SidebarInputSnapshot | None = None,
    ) -> ApplicationPrerequisiteProjection:
        """Resolve operation-scoped readiness for current or prepared authority."""

        if intent is not None and not isinstance(intent, SidebarInputSnapshot):
            raise ValueError("intent must be SidebarInputSnapshot or None")
        return _shared_prerequisite_projection(
            self._sidebar(sidebar_intent=intent),
            prepared_authority=(
                intent is None
                and self._boundary.session.prepared_plan is not None
                and self._boundary.plan_request is not None
            ),
        )

    def environment_for_sidebar(
        self,
        sidebar: SidebarProjection,
    ) -> ApplicationEnvironmentProjection:
        """Project current application/session state without generation identity."""

        if not isinstance(sidebar, SidebarProjection):
            raise ValueError("sidebar must be SidebarProjection")

        evidence_destination: Path | None = None
        discovery = self._boundary.discovery
        if (
            discovery is not None
            and self._benchmark_candidates is not None
            and self._repository_root is not None
            and sidebar.selected_benchmark is not None
        ):
            discovered_benchmark = next(
                (
                    value
                    for value in discovery.benchmarks
                    if _registration_label(value) == sidebar.selected_benchmark
                ),
                None,
            )
            if discovered_benchmark is not None:
                readiness = derive_benchmark_evidence_readiness(
                    discovered_benchmark=discovered_benchmark,
                    benchmark_candidates=self._benchmark_candidates,
                    repository_root=self._repository_root,
                )
                if not readiness.diagnostics:
                    evidence_destination = readiness.destination_root

        from . import derive_application_environment as environment_projector

        return environment_projector(
            discovery=discovery,
            sidebar=sidebar,
            evidence_destination=evidence_destination,
            supplied_entries=self._environment_entries,
        )

    def _environment_update(
        self,
        sidebar: SidebarProjection,
        status: tuple[str, str] | None,
    ) -> tuple[
        ApplicationEnvironmentProjection,
        tuple[str, str] | None,
    ]:
        """Fail closed when the current Environment projection cannot be produced."""

        try:
            environment = self.environment_for_sidebar(sidebar)
        except Exception as exc:
            environment = ApplicationEnvironmentProjection(
                entries=(environment_projection_failure_entry(exc),)
            )
            status = ("Environment projection failed", "error")
        return environment, _application_status_for_sidebar(sidebar, status)

    def sidebar_from_intent(
        self,
        intent: SidebarInputSnapshot,
    ) -> SidebarProjection:
        """Re-project prerequisite readiness from current presentation-only intent."""

        if not isinstance(intent, SidebarInputSnapshot):
            raise ValueError("intent must be SidebarInputSnapshot")
        return self._sidebar(sidebar_intent=intent)

    def sidebar_for_runner(
        self,
        intent: SidebarInputSnapshot,
        selected_runner: str,
    ) -> SidebarProjection:
        """Re-project runner readiness from current presentation-only intent."""

        if not isinstance(intent, SidebarInputSnapshot):
            raise ValueError("intent must be SidebarInputSnapshot")
        _text(selected_runner, name="selected_runner")
        return self._sidebar(
            sidebar_intent=intent,
            selected_runner_override=selected_runner,
            runner_selection_changed=True,
        )

    def _plan_summary(
        self,
        plan: RunPlan,
        request: ApplicationPlanRequest,
    ) -> tuple[ExecutionBoundaryProjection, RunPlanProjection]:
        plan_document = plan.to_dict()
        boundary_document = _verified_plan_boundary(plan_document, request.execution_boundary.to_dict())
        capture_details, capture_advisory, capture_tone = _capture_runtime_presentation(plan_document, boundary_document)
        model = _execution_boundary_model(boundary_document)

        case_ids: list[str] = []
        treatment_ids: list[str] = []
        for observation in plan.observations:
            if observation.case_id not in case_ids:
                case_ids.append(observation.case_id)
            if observation.treatment_id not in treatment_ids:
                treatment_ids.append(observation.treatment_id)

        unscored = request.extensions.get("arcgrav.runtime:execution-only") is True
        return (
            ExecutionBoundaryProjection(
                benchmark="Custom Benchmark" if unscored else _identity_label(plan.benchmark),
                runner=_document_identity_label(
                    boundary_document["runner"],
                    name="runner",
                ),
                model=model,
                cases=_identity_label(plan.case_set),
                boundary_fingerprint=plan.execution_boundary_fingerprint,
                runtime_details=capture_details,
            ),
            RunPlanProjection(
                treatments=", ".join(treatment_ids),
                cases=f"{len(case_ids)} case(s)",
                execution=f"{len(plan.observations)} planned observation(s)",
                execution_details=(
                    ("Planned observations", str(len(plan.observations))),
                    ("Iterations", str(plan.repetitions)),
                ),
                evaluation="Not applicable" if unscored else f"{len(plan.contracts)} bound shared contract(s)",
                outputs="Responses and execution measurements" if unscored else f"Canonical plan {plan.plan_sha256}",
                treatment_files=tuple(treatment_ids),
                capture_runtime_advisory=capture_advisory,
                capture_runtime_advisory_tone=capture_tone,
            ),
        )

    def _current_terminal(
        self,
        plan: RunPlan,
    ) -> AcceptedRun | BlockedRun | None:
        execution_request = self._boundary.execution_request
        if execution_request is None:
            return None
        context = self._boundary.run_context(execution_request.generation_id)
        if context is None or context.plan.run_plan_id != plan.run_plan_id:
            return None
        return next(
            (
                run
                for run in self._boundary.retained_runs
                if run.generation_id == execution_request.generation_id
            ),
            None,
        )

    def _current_run(
        self,
        result: object,
    ) -> CurrentRunProjection | None:
        plan = self._boundary.session.prepared_plan
        request = self._boundary.plan_request
        if plan is None or request is None:
            return None

        execution_boundary, run_plan = self._plan_summary(plan, request)
        snapshot = self._boundary.accepted_snapshot
        current_terminal = self._current_terminal(plan)
        execution_request = self._boundary.execution_request
        active_context = (
            self._boundary.run_context(execution_request.generation_id)
            if execution_request is not None
            else None
        )
        active_current = (
            execution_request is not None
            and active_context is not None
            and active_context.plan.run_plan_id == plan.run_plan_id
            and current_terminal is None
        )
        acceptance_prerequisites_clear = execution_prerequisites_clear = False
        if type(result) in (RunPlan, AcceptedRunSnapshot) or (current_terminal is None and not active_current):
            prepared_prerequisites = self.prerequisite_projection()
            acceptance_prerequisites_clear = prepared_prerequisites.ready_for("acceptance")
            execution_prerequisites_clear = prepared_prerequisites.ready_for("execution")

        if type(result) is RunPlan:
            run_identity = result.run_plan_id
            state_label, state_tone = "Pending", "neutral"
            timestamp = "Awaiting acceptance"
            accept_available = acceptance_prerequisites_clear
            start_available = False
        elif type(result) is AcceptedRunSnapshot:
            run_identity = result.run_plan_id
            state_label, state_tone = "Accepted", "success"
            timestamp = result.accepted_at
            accept_available = False
            start_available = execution_prerequisites_clear
        elif current_terminal is not None:
            run_identity = current_terminal.generation_id
            state_label, state_tone = _completion_state(self._boundary, current_terminal)
            context = self._boundary.run_context(current_terminal.generation_id)
            timestamp = (
                context.accepted_at if context is not None else "Retained run"
            )
            accept_available = False
            start_available = False
        elif active_current:
            run_identity = execution_request.generation_id
            state_label, state_tone = "Running", "active"
            timestamp = active_context.accepted_at
            accept_available = False
            start_available = False
        elif snapshot is not None and snapshot.run_plan_id == plan.run_plan_id:
            run_identity = snapshot.run_plan_id
            state_label, state_tone = "Accepted", "success"
            timestamp = snapshot.accepted_at
            accept_available = False
            start_available = execution_prerequisites_clear
        else:
            run_identity = plan.run_plan_id
            state_label, state_tone = "Pending", "neutral"
            timestamp = "Awaiting acceptance"
            accept_available = acceptance_prerequisites_clear
            start_available = False

        return CurrentRunProjection(
            run_identity=run_identity,
            state_label=state_label,
            state_tone=state_tone,
            timestamp=timestamp,
            execution_boundary=execution_boundary,
            run_plan=run_plan,
            unscored=request.extensions.get("arcgrav.runtime:execution-only") is True,
            heading="Current Run",
            accept_plan_available=accept_available,
            start_benchmark_available=start_available,
        )

    def _prior_run(
        self,
        terminal: AcceptedRun | BlockedRun,
    ) -> CurrentRunProjection | None:
        context = self._boundary.run_context(terminal.generation_id)
        if context is None:
            return None
        execution_boundary, run_plan = self._plan_summary(
            context.plan,
            context.plan_request,
        )
        state_label, state_tone = _completion_state(self._boundary, terminal)
        return CurrentRunProjection(
            run_identity=terminal.generation_id,
            state_label=state_label,
            state_tone=state_tone,
            timestamp=context.accepted_at,
            execution_boundary=execution_boundary,
            run_plan=run_plan,
            unscored=type(terminal) is ExecutedRun,
            heading="Prior Run",
            is_prior_run=True,
            accept_plan_available=False,
            start_benchmark_available=False,
            delete_run_available=True,
        )

    def execution_blocked_current_run(
        self,
    ) -> CurrentRunProjection | None:
        """Preserve accepted authority while fail-closing a rejected start attempt."""

        projection = self._current_run(
            self._boundary.accepted_snapshot,
        )
        if projection is None:
            return None
        return replace(projection, start_benchmark_available=False)

    def active_execution_workspace(
        self,
        execution_request: ApplicationExecutionRequest,
        plan: RunPlan,
    ) -> WorkspaceProjection | None:
        """Project one active accepted execution without creating lifecycle authority."""

        if type(execution_request) is not ApplicationExecutionRequest:
            raise ValueError(
                "execution_request must be an ApplicationExecutionRequest"
            )
        if type(plan) is not RunPlan:
            raise ValueError("plan must be a RunPlan")
        active_projector = getattr(
            self._workspace_projector,
            "active_execution",
            None,
        )
        if not callable(active_projector):
            return None
        return active_projector(execution_request.generation_id, plan)

    def execution_started_update(
        self,
        execution_request: ApplicationExecutionRequest,
        plan: RunPlan,
    ) -> ApplicationProjectionUpdate:
        """Project the exact accepted generation while execution is active."""

        workspace = self.active_execution_workspace(execution_request, plan)
        self._viewing_prior_run_id = None
        self._mounted_workspace_run_id = (
            execution_request.generation_id if workspace is not None else None
        )
        sidebar = self._sidebar()
        return ApplicationProjectionUpdate(
            sidebar=sidebar,
            current_run=self._current_run(execution_request),
            workspace=workspace,
            workspace_run_id=(
                execution_request.generation_id
                if workspace is not None
                else None
            ),
            console=ConsoleProjectionUpdate(
                generation_id=execution_request.generation_id,
                bind_generation=True,
                live_output=(
                    "Accepted execution started for generation "
                    f"{execution_request.generation_id}.\n",
                ),
            ),
            application_status=("Running", "active"),
        )

    def execution_failed_update(self, *, preserve_progress=False) -> ApplicationProjectionUpdate:
        """Restore accepted current authority after a nonterminal start failure."""

        self._viewing_prior_run_id = None
        if not preserve_progress:
            self._mounted_workspace_run_id = None
        current = self.execution_blocked_current_run()
        if preserve_progress and current is not None:
            current = replace(current, state_label="Failed", state_tone="error")
        return ApplicationProjectionUpdate(
            sidebar=self._sidebar(),
            current_run=current,
            clear_workspace=not preserve_progress,
        )

    def build_plan_requested_update(self) -> ApplicationProjectionUpdate:
        """Unmount any generation-bound workspace before planning is dispatched."""

        self._mounted_workspace_run_id = None
        return ApplicationProjectionUpdate(clear_workspace=True)

    def delete_run_requested_update(
        self,
        run_id: str,
    ) -> ApplicationProjectionUpdate:
        """Clear selected Prior Run presentation while shared deletion executes."""

        run_id = _text(run_id, name="run_id")
        if self._viewing_prior_run_id != run_id:
            raise ValueError("delete_run must target the selected prior run")
        if not any(
            run.generation_id == run_id
            for run in (*self._boundary.retained_runs,
                        *(run for run in self._boundary.historical_runs if run.can_delete))
        ):
            raise ValueError("delete_run requires a retained terminal generation")

        self._pending_delete_run_id = run_id
        self._viewing_prior_run_id = None
        self._mounted_workspace_run_id = None
        self._suppress_current_projection_after_delete = True

        sidebar = self._sidebar()
        sidebar = replace(
            sidebar,
            runs=tuple(run for run in sidebar.runs if run.run_id != run_id),
        )
        environment, application_status = self._environment_update(
            sidebar,
            (f"Deleting run {run_id}", "active"),
        )
        return ApplicationProjectionUpdate(
            sidebar=sidebar,
            clear_current_run=True,
            clear_workspace=True,
            environment=environment,
            application_status=application_status,
        )

    def delete_run_failed_update(
        self,
        run_id: str,
    ) -> ApplicationProjectionUpdate:
        """Restore authoritative Prior Run presentation after deletion failure."""

        run_id = _text(run_id, name="run_id")
        if self._pending_delete_run_id != run_id:
            return ApplicationProjectionUpdate()

        historical = next((run for run in self._boundary.historical_runs
                           if run.generation_id == run_id), None)
        if historical is not None:
            update = self("select_run", historical, None)
            return replace(update, application_status=(f"Could not delete run {run_id}", "error"))

        self._pending_delete_run_id = None
        self._suppress_current_projection_after_delete = False
        selected_terminal = self._boundary.selected_terminal
        retained = any(
            run.generation_id == run_id
            for run in self._boundary.retained_runs
        )
        if (
            retained
            and type(selected_terminal) in (AcceptedRun, BlockedRun, ExecutedRun)
            and selected_terminal.generation_id == run_id
        ):
            self._viewing_prior_run_id = run_id
            current_run = self._prior_run(selected_terminal)
        else:
            self._viewing_prior_run_id = None
            current_run = self._current_run(selected_terminal)

        return ApplicationProjectionUpdate(
            sidebar=self._sidebar(),
            current_run=current_run,
            clear_current_run=current_run is None,
            clear_workspace=True,
        )

    def prepare_result(self, command, result, commands):
        """Reconstruct, validate and persist pure data without mutating GUI state."""
        from .history import HistoricalRun
        # Sidebar/current/prior projections reuse these immutable lifecycle
        # labels after worker preparation; they never need to decode large
        # retained observations again merely to display completion status.
        for terminal in self._boundary.retained_runs:
            _terminal_state(terminal)
        if type(result) in (AcceptedRun, BlockedRun, ExecutedRun):
            _terminal_state(result)
        if command == "select_run" and isinstance(result, HistoricalRun):
            from .console_projection import historical_console_update
            current, workspace = result.prepare_presentation()
            return PreparedApplicationResult(command, result, workspace, True, current,
                historical_console_update(result))
        if command not in {"start_benchmark", "select_run"}:
            return None
        prepare = getattr(self._workspace_projector, "prepare_result", None)
        workspace_prepared = callable(prepare) and callable(getattr(self._workspace_projector, "render", None))
        workspace = prepare(command, result, commands) if workspace_prepared else None
        console = None
        if command == "start_benchmark":
            from .console_projection import _terminal_console_update
            console = _terminal_console_update(result, getattr(self._boundary, "completion_diagnostics", lambda _: ())(result.generation_id))
        elif command == "select_run":
            console = ConsoleProjectionUpdate(result.generation_id, bind_generation=True,
                diagnostics=tuple(line + "\n" for line in getattr(self._boundary, "completion_diagnostics", lambda _: ())(result.generation_id)))
        diagnostics = None
        if workspace is not None:
            generation_id = workspace.results.run_id
            terminal = (result if type(result) in (AcceptedRun, BlockedRun, ExecutedRun)
                        else next((run for run in self._boundary.retained_runs
                                   if run.generation_id == generation_id), None))
            persist = getattr(self._boundary, "prepare_history_presentation", None)
            if terminal is not None and callable(persist):
                diagnostics = persist(generation_id, self._prior_run(terminal), workspace)
        return PreparedApplicationResult(command, result, workspace, workspace_prepared,
            console=console, history_diagnostics=diagnostics)

    def __call__(
        self,
        command: str,
        result: object,
        commands: DesktopCommandPort,
        *,
        prepared: PreparedApplicationResult | None = None,
    ) -> ApplicationProjectionUpdate:
        from .history import HistoricalRun
        if prepared is not None:
            if not isinstance(prepared, PreparedApplicationResult) or prepared.command != command or prepared.result is not result:
                raise ValueError("prepared application projection does not match its result")
            if prepared.history_diagnostics is not None:
                self._boundary.apply_history_diagnostics(prepared.history_diagnostics)
        if command == "select_run" and isinstance(result, HistoricalRun):
            self._viewing_prior_run_id = result.generation_id
            self._mounted_workspace_run_id = result.generation_id
            self._pending_delete_run_id = None
            self._suppress_current_projection_after_delete = False
            if prepared is None:
                current, workspace = result.presentation()
            else:
                from AgMark.gui.projection.workspace.projector import render_workspace
                current, workspace = prepared.historical_current, render_workspace(prepared.workspace)
            if current.state_label != result.state_label:
                self._boundary.record_history_state(result.generation_id, current.state_label, current.state_tone)
            from .console_projection import historical_console_update
            return ApplicationProjectionUpdate(
                sidebar=self._sidebar(), current_run=current, workspace=workspace,
                workspace_run_id=result.generation_id,
                application_status=(current.state_label, current.state_tone),
                console=prepared.console if prepared is not None else historical_console_update(result))
        if command == "discover":
            if type(result) is not ApplicationDiscovery:
                raise ValueError("discover projection requires ApplicationDiscovery")
            self._viewing_prior_run_id = None
            self._mounted_workspace_run_id = None
            self._pending_delete_run_id = None
            self._suppress_current_projection_after_delete = False
            sidebar = self._sidebar()
            environment, application_status = self._environment_update(
                sidebar,
                ("Ready", "success"),
            )
            return ApplicationProjectionUpdate(
                sidebar=sidebar,
                clear_current_run=True,
                clear_workspace=True,
                environment=environment,
                application_status=application_status,
            )

        if command == "test_runner":
            if type(result) is not RunnerTestResult:
                raise ValueError("test_runner projection requires RunnerTestResult")
            # Runner-test completion is presentation-only and is handled by the
            # desktop Environment projection. It must not reproject sidebar,
            # readiness, Current Run, workspace, or application status.
            return ApplicationProjectionUpdate()

        clear_workspace = False
        console: ConsoleProjectionUpdate | None = None
        application_status: tuple[str, str] | None = None

        if command == "build_plan":
            if type(result) is not RunPlan:
                raise ValueError("build_plan projection requires RunPlan")
            # A successful replacement plan establishes a new Current Run
            # presentation scope. Detach every generation-bound workspace page
            # immediately, independent of retained-run selection bookkeeping.
            clear_workspace = True
            self._viewing_prior_run_id = None
            self._mounted_workspace_run_id = None
            self._pending_delete_run_id = None
            self._suppress_current_projection_after_delete = False
            application_status = ("Plan ready", "neutral")
        elif command == "accept_plan":
            if type(result) is not AcceptedRunSnapshot:
                raise ValueError(
                    "accept_plan projection requires AcceptedRunSnapshot"
                )
            # Acceptance belongs to the replacement Current Run. Retained
            # terminal workspace content must not be reprojected here.
            clear_workspace = True
            self._viewing_prior_run_id = None
            self._mounted_workspace_run_id = None
            self._pending_delete_run_id = None
            self._suppress_current_projection_after_delete = False
            application_status = ("Plan accepted", "success")
        elif command in ("start_benchmark", "select_run"):
            if type(result) not in (AcceptedRun, BlockedRun, ExecutedRun):
                raise ValueError(
                    f"{command} projection requires terminal shared authority"
                )
            state_label, state_tone = _terminal_state(result)
            completion = getattr(self._boundary, "report_state", lambda _: (None, None))(result.generation_id)[0]
            if completion == "complete":
                state_label, state_tone = "Completed · Report ready", "success"
            elif completion in {"validation_failed", "report_failed"}:
                state_label, state_tone = "Execution finished · Report release failed", "error"
            self._mounted_workspace_run_id = result.generation_id
            self._pending_delete_run_id = None
            self._suppress_current_projection_after_delete = False
            application_status = (state_label, state_tone)
            if command == "start_benchmark":
                self._viewing_prior_run_id = None
                from .console_projection import _terminal_console_update
                console = prepared.console if prepared is not None else _terminal_console_update(result, getattr(self._boundary, "completion_diagnostics", lambda _: ())(result.generation_id))
            else:
                self._viewing_prior_run_id = result.generation_id
                console = prepared.console if prepared is not None else ConsoleProjectionUpdate(
                    result.generation_id, bind_generation=True,
                    diagnostics=tuple(line + "\n" for line in getattr(self._boundary, "completion_diagnostics", lambda _: ())(result.generation_id)))
        elif command == "delete_run":
            if type(result) is not ApplicationRunDeletion:
                raise ValueError(
                    "delete_run projection requires ApplicationRunDeletion"
                )
            expected_delete_run_id = (
                self._pending_delete_run_id
                if self._pending_delete_run_id is not None
                else self._viewing_prior_run_id
            )
            if expected_delete_run_id != result.generation_id:
                raise ValueError(
                    "delete_run must target the selected prior run"
                )
            self._pending_delete_run_id = None
            self._viewing_prior_run_id = None
            self._mounted_workspace_run_id = None
            self._suppress_current_projection_after_delete = True
            clear_workspace = True
            application_status = (
                f"Run {result.generation_id} deleted",
                "success",
            )
        else:
            raise ValueError("unsupported application projection command")

        selected_terminal = self._boundary.selected_terminal
        if self._suppress_current_projection_after_delete:
            current_run = None
        elif self._viewing_prior_run_id is not None:
            current_run = (
                self._prior_run(selected_terminal)
                if (
                    type(selected_terminal) in (AcceptedRun, BlockedRun, ExecutedRun)
                    and selected_terminal.generation_id
                    == self._viewing_prior_run_id
                )
                else None
            )
        else:
            current_run = self._current_run(result)

        workspace = None
        workspace_run_id = None
        mounted_run_id = self._mounted_workspace_run_id
        mounted_terminal_matches = (
            mounted_run_id is not None
            and type(selected_terminal) in (AcceptedRun, BlockedRun, ExecutedRun)
            and selected_terminal.generation_id == mounted_run_id
        )
        if (
            not clear_workspace
            and mounted_terminal_matches
            and self._workspace_projector is not None
        ):
            if prepared is not None and prepared.workspace_prepared:
                if prepared.workspace is not None and prepared.workspace.results.run_id != mounted_run_id:
                    raise ValueError("prepared workspace does not match the selected generation")
                workspace = (None if prepared.workspace is None
                             else self._workspace_projector.render(prepared.workspace))
            else:
                workspace = self._workspace_projector(command, result, commands)
            if workspace is not None:
                workspace_run_id = mounted_run_id
                if prepared is None or not prepared.workspace_prepared:
                    self._boundary.save_history_presentation(mounted_run_id, current_run, workspace)
                if self._boundary.history_diagnostics:
                    application_status = ("Run available; saving history failed", "warning")

        sidebar = self._sidebar()
        environment, application_status = self._environment_update(
            sidebar,
            application_status,
        )
        return ApplicationProjectionUpdate(
            sidebar=sidebar,
            current_run=current_run,
            clear_current_run=(
                current_run is None
                and (
                    command == "delete_run"
                    or self._suppress_current_projection_after_delete
                )
            ),
            workspace=workspace,
            clear_workspace=clear_workspace,
            workspace_run_id=workspace_run_id,
            console=console,
            environment=environment,
            application_status=application_status,
        )


AuthorityOperation = Callable[[], object]
AuthorityDispatcher = Callable[[AuthorityOperation], object]
FailureGenerationProvider = Callable[[], str | None]
FailureHandler = Callable[[str, BaseException], None]
