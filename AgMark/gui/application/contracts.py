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
from threading import Thread
from typing import Protocol

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
    AcceptedRun,
    AcceptedRunSnapshot,
    BlockedRun,
    RunPlan,
)
from AgMark.shared.validation import BenchmarkDiscoveryCandidate

from AgMark.gui.composition import (
    RepositoryPrerequisiteDiagnostic,
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

def _text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value

@dataclass(frozen=True, slots=True)
class ConsoleProjectionUpdate:
    """Generation-bound console projection supplied by frontend projection code."""

    generation_id: str
    bind_generation: bool = False
    live_output: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    raw_response_supplied: bool = False
    raw_response: str | None = None
    live_view: tuple[tuple[str, str | None, str | None], ...] = ()
    live_view_treatments: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _text(self.generation_id, name="generation_id")
        if type(self.bind_generation) is not bool:
            raise ValueError("bind_generation must be boolean")
        if type(self.raw_response_supplied) is not bool:
            raise ValueError("raw_response_supplied must be boolean")
        live_output = tuple(self.live_output)
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(value, str) for value in live_output):
            raise ValueError("live_output must contain strings")
        if any(not isinstance(value, str) for value in diagnostics):
            raise ValueError("diagnostics must contain strings")
        if self.raw_response is not None and not isinstance(self.raw_response, str):
            raise ValueError("raw_response must be text or None")
        if self.raw_response is not None and not self.raw_response_supplied:
            raise ValueError("raw_response requires raw_response_supplied=True")
        object.__setattr__(self, "live_output", live_output)
        object.__setattr__(self, "diagnostics", diagnostics)
        live_view = tuple(self.live_view)
        for entry in live_view:
            if len(entry) != 3 or not isinstance(entry[0], str) or not entry[0]:
                raise ValueError("live_view requires invocation ID, input, output")
            if any(value is not None and not isinstance(value, str) for value in entry[1:]):
                raise ValueError("live_view input/output must be text or None")
        object.__setattr__(self, "live_view", live_view)
        treatments = tuple(self.live_view_treatments)
        for entry in treatments:
            if len(entry) != 2 or any(not isinstance(value, str) or not value for value in entry):
                raise ValueError("live_view_treatments requires invocation ID and treatment name")
        object.__setattr__(self, "live_view_treatments", treatments)

@dataclass(frozen=True, slots=True)
class ApplicationProjectionUpdate:
    """One authority-neutral update to the concrete desktop presentation."""

    sidebar: SidebarProjection | None = None
    current_run: CurrentRunProjection | None = None
    clear_current_run: bool = False
    workspace: WorkspaceProjection | None = None
    clear_workspace: bool = False
    workspace_run_id: str | None = None
    console: ConsoleProjectionUpdate | None = None
    environment: ApplicationEnvironmentProjection | None = None
    connectivity: tuple[str, str] | None = None
    application_status: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        if self.sidebar is not None and not isinstance(self.sidebar, SidebarProjection):
            raise ValueError("sidebar must be SidebarProjection or None")
        if self.current_run is not None and not isinstance(
            self.current_run, CurrentRunProjection
        ):
            raise ValueError("current_run must be CurrentRunProjection or None")
        if type(self.clear_current_run) is not bool:
            raise ValueError("clear_current_run must be boolean")
        if self.current_run is not None and self.clear_current_run:
            raise ValueError("current_run and clear_current_run are mutually exclusive")
        if self.workspace is not None and not isinstance(
            self.workspace, WorkspaceProjection
        ):
            raise ValueError("workspace must be WorkspaceProjection or None")
        if type(self.clear_workspace) is not bool:
            raise ValueError("clear_workspace must be boolean")
        if self.workspace is not None and self.clear_workspace:
            raise ValueError("workspace and clear_workspace are mutually exclusive")
        if self.workspace_run_id is not None:
            _text(self.workspace_run_id, name="workspace_run_id")
            if self.workspace is None:
                raise ValueError("workspace_run_id requires a workspace projection")
        if self.console is not None and not isinstance(
            self.console, ConsoleProjectionUpdate
        ):
            raise ValueError("console must be ConsoleProjectionUpdate or None")
        if self.environment is not None and not isinstance(
            self.environment, ApplicationEnvironmentProjection
        ):
            raise ValueError(
                "environment must be ApplicationEnvironmentProjection or None"
            )
        if self.connectivity is not None:
            if not isinstance(self.connectivity, tuple) or len(self.connectivity) != 2:
                raise ValueError("connectivity must be a (label, tone) tuple or None")
            _text(self.connectivity[0], name="connectivity label")
            _text(self.connectivity[1], name="connectivity tone")
        if self.application_status is not None:
            if (
                not isinstance(self.application_status, tuple)
                or len(self.application_status) != 2
            ):
                raise ValueError(
                    "application_status must be a (label, tone) tuple or None"
                )
            _text(self.application_status[0], name="application status label")
            _text(self.application_status[1], name="application status tone")

@dataclass(frozen=True, slots=True)
class RunnerTestResult:
    """Non-authoritative result from one GUI runner functionality diagnostic."""

    selected_runner: str
    runner_id: str = ""
    runner_version: str = ""
    model: str = ""
    submitted: bool = False
    terminal_status: str | None = None
    response_preview: str = ""
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.selected_runner, name="selected_runner")
        for name in ("runner_id", "runner_version", "model", "response_preview"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
        if type(self.submitted) is not bool:
            raise ValueError("submitted must be boolean")
        if self.terminal_status is not None and (
            not isinstance(self.terminal_status, str)
            or not self.terminal_status
        ):
            raise ValueError("terminal_status must be non-empty text or None")
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(value, str) for value in diagnostics):
            raise ValueError("diagnostics must contain strings")
        object.__setattr__(self, "diagnostics", diagnostics)

    @property
    def passed(self) -> bool:
        return (
            self.submitted
            and self.terminal_status == "completed"
            and bool(self.response_preview)
            and not self.diagnostics
        )

class SharedApplicationBoundary(Protocol):
    """Coarse shared application authority consumed by the GUI."""

    def discover(self) -> object:
        ...

    def build_plan(self, intent: SidebarInputSnapshot) -> object:
        ...

    def select_run(self, run_id: str) -> object:
        ...

    def delete_run(self, run_id: str) -> object:
        ...

    def accept_plan(self) -> object:
        ...

    def start_benchmark(self) -> object:
        ...



class DesktopCommandPort(Protocol):
    """Commands a GUI projector may bind to presentation actions."""


    def request_export_report(self, generation_id: str, report_id: str) -> object:
        ...

    def request_show_verification(self) -> object:
        ...


    def request_import_run_archive(self) -> object:
        """Optional read-only inspection; independent of native reporting."""
        ...

    def request_select_run(self, run_id: str) -> object:
        ...

    def request_delete_run(self, run_id: str) -> object:
        ...

class ApplicationProjector(Protocol):
    """GUI-owned conversion from exact shared results to presentation updates."""

    def __call__(
        self,
        command: str,
        result: object,
        commands: DesktopCommandPort,
    ) -> ApplicationProjectionUpdate:
        ...

class ApplicationRequestResolver(Protocol):
    """Resolve exact shared requests without owning lifecycle sequencing."""

    def resolve_plan_request(
        self,
        intent: SidebarInputSnapshot,
        discovery: ApplicationDiscovery,
    ) -> ApplicationPlanRequest:
        ...

    def resolve_execution_request(
        self,
        plan_request: ApplicationPlanRequest,
        accepted_snapshot: AcceptedRunSnapshot,
        *,
        credential: str,
        runner_transient_controls: tuple[SidebarControlInputSnapshot, ...] = (),
    ) -> ApplicationExecutionRequest:
        ...

    def resolve_report_request(
        self,
        retained_run: AcceptedRun,
    ) -> ApplicationReportRequest:
        ...



WorkspaceProjector = Callable[
    [str, object, DesktopCommandPort],
    WorkspaceProjection | None,
]
SidebarRefreshProjector = Callable[
    [SidebarInputSnapshot, str],
    SidebarProjection,
]
SidebarIntentProjector = Callable[
    [SidebarInputSnapshot],
    SidebarProjection,
]
SidebarEnvironmentProjector = Callable[
    [SidebarProjection],
    ApplicationEnvironmentProjection,
]

WorkspaceProjector = Callable[
    [str, object, DesktopCommandPort],
    WorkspaceProjection | None,
]
SidebarRefreshProjector = Callable[
    [SidebarInputSnapshot, str],
    SidebarProjection,
]
SidebarIntentProjector = Callable[
    [SidebarInputSnapshot],
    SidebarProjection,
]
SidebarEnvironmentProjector = Callable[
    [SidebarProjection],
    ApplicationEnvironmentProjection,
]
