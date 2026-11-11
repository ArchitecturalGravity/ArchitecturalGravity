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
from shutil import which
from threading import Lock, Thread
from time import monotonic
from AgMark.shared.runtime.orchestration.activity import RunActivity
from AgMark.gui.projection.workspace.activity import activity_text, with_activity
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
    from PySide6.QtCore import QEvent, QObject, QTimer, Signal
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication


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

from .contracts import (
    ApplicationProjectionUpdate, ApplicationProjector, ApplicationRequestResolver,
    RunnerTestResult, SharedApplicationBoundary, SidebarEnvironmentProjector,
    SidebarIntentProjector, SidebarRefreshProjector, WorkspaceProjector, _text,
)
from .dispatch import AuthorityDispatcher, FailureGenerationProvider, FailureHandler, _GuiResultDispatcher, _ProjectionWorker, _dispatch_in_background
from .projector import SharedApplicationProjector, _repository_sidebar_projection
from .runner_testing import _runner_test_environment_entry
from .session_boundary import PlanningSessionApplicationBoundary, _validate_boundary
from AgMark.gui.shell.diagnostic_consent import DiagnosticConsentRequired

if PYSIDE6_AVAILABLE:
    class _WindowLifetime(QObject):
        def __init__(self, close, parent):
            super().__init__(parent)
            self._close = close

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Close:
                self._close()
            return False

    class BenchmarkDesktopApplication:
        """Concrete desktop binding to one shared public application boundary."""

        def __init__(
            self,
            *,
            application_icon: QIcon,
            shared_application_boundary: SharedApplicationBoundary,
            projector: ApplicationProjector,
            shell_preferences=None,
            console_preferences=None,
            initial_sidebar_projection: SidebarProjection | None = None,
            sidebar_refresh_projector: SidebarRefreshProjector | None = None,
            sidebar_intent_projector: SidebarIntentProjector | None = None,
            sidebar_environment_projector: SidebarEnvironmentProjector | None = None,
            authority_dispatcher: AuthorityDispatcher | None = None,
            failure_handler: FailureHandler | None = None,
            parent=None,
        ) -> None:
            _validate_boundary(shared_application_boundary)
            if not callable(projector):
                raise ValueError("projector must be callable")
            if sidebar_refresh_projector is not None and not callable(
                sidebar_refresh_projector
            ):
                raise ValueError(
                    "sidebar_refresh_projector must be callable or None"
                )
            if sidebar_intent_projector is not None and not callable(
                sidebar_intent_projector
            ):
                raise ValueError(
                    "sidebar_intent_projector must be callable or None"
                )
            if sidebar_environment_projector is not None and not callable(
                sidebar_environment_projector
            ):
                raise ValueError(
                    "sidebar_environment_projector must be callable or None"
                )
            if authority_dispatcher is not None and not callable(authority_dispatcher):
                raise ValueError("authority_dispatcher must be callable or None")
            if failure_handler is not None and not callable(failure_handler):
                raise ValueError("failure_handler must be callable or None")

            self._pending_commands: set[str] = set()
            self._selecting_run = False
            self._boundary = shared_application_boundary
            self._projector = projector
            self._sidebar_refresh_projector = sidebar_refresh_projector
            self._sidebar_intent_projector = sidebar_intent_projector
            self._sidebar_environment_projector = sidebar_environment_projector
            self._authority_dispatcher = authority_dispatcher or _dispatch_in_background
            self._background_projection = authority_dispatcher is None
            self._projection_worker = _ProjectionWorker()
            self._selection_worker = _ProjectionWorker()
            self._sidebar_worker = _ProjectionWorker()
            self._sidebar_refresh_revision = 0
            self._sidebar_refresh_pending = False
            self._closed = False
            self._command_revisions = {}
            self._authority_dispatch_lock = Lock()
            self._queued_authority_commands = {}
            self._workspace_revision = 0
            self._prepared_for_apply = None
            self._activity_lock = Lock()
            self._queued_activity = None
            self._activity_generation_id = None
            self._activity_notification_pending = False
            self._failure_handler = failure_handler
            self._environment_projection = ApplicationEnvironmentProjection()
            self._gui_dispatcher = _GuiResultDispatcher()
            self._gui_dispatcher.execution_started.connect(
                self._apply_execution_started
            )
            self._gui_dispatcher.activity_ready.connect(self._apply_activity)
            self._active_activity = None
            self._activity_received_at = None
            self._gui_dispatcher.result_ready.connect(self._apply_result)
            self._gui_dispatcher.failure_ready.connect(self._apply_failure)
            self._gui_dispatcher.operation_ready.connect(self._receive_result)
            self._gui_dispatcher.operation_failed.connect(self._receive_failure)
            self._gui_dispatcher.prepared_ready.connect(self._receive_prepared_result)
            self._gui_dispatcher.active_projection_ready.connect(self._apply_active_projection)
            self._gui_dispatcher.activity_pending.connect(self._drain_activity)
            self._gui_dispatcher.sidebar_ready.connect(self._receive_sidebar_refresh)
            self._active_progress_generation_id: str | None = None
            self._active_progress_plan: RunPlan | None = None
            self._active_progress_store = None
            self._active_projection_epoch = 0
            self._active_projection_pending = None
            self._active_progress_projection = None
            self._active_progress_started_at = None
            self._preparing_benchmark_results = False
            self._active_progress_timer = QTimer()
            self._active_progress_timer.setInterval(1000)
            self._active_progress_timer.timeout.connect(
                self._refresh_active_progress
            )

            sidebar = initial_sidebar_projection or SidebarProjection()
            self.window = BenchmarkShellWindow(
                application_icon=application_icon,
                shell_preferences=shell_preferences,
                console_preferences=console_preferences,
                sidebar_projection=sidebar,
                on_benchmark_selected=(
                    self._refresh_benchmark_selection
                    if self._sidebar_intent_projector is not None
                    else None
                ),
                on_runner_selected=(
                    self._refresh_runner_selection
                    if self._sidebar_refresh_projector is not None
                    else None
                ),
                on_sidebar_intent_changed=(
                    self._refresh_sidebar_intent
                    if self._sidebar_intent_projector is not None
                    else None
                ),
                on_build_plan=self.request_build_plan,
                on_test_runner=(
                    self.request_test_runner
                    if callable(getattr(self._boundary, "test_runner", None))
                    else None
                ),
                on_check_runner=(self.request_refresh_connectivity
                                 if self._sidebar_intent_projector is not None else None),
                on_run_selected=self.request_select_run,
                on_delete_run=self.request_delete_run,
                on_accept_plan=self.request_accept_plan,
                on_start_benchmark=self.request_start_benchmark,
                command_dispatcher=lambda operation: operation(),
                parent=parent,
            )
            # Imported-run inspection is an opt-in, global tool. It is available
            # without selecting or verifying any native report.
            from AgMark.gui.widgets.buttons import ActionButton
            self.window.set_runner_connectivity(sidebar)
            import_available = callable(getattr(self._boundary, "import_run_archive", None))
            self.import_run_button = ActionButton(
                "Import Run", "secondary" if import_available else "unavailable",
                content_sized=True,
                parent=self.window,
            )
            self.import_run_button.setAccessibleName("Import validated .agmark run archive")
            self.import_run_button.clicked.connect(
                lambda _checked=False: self.request_import_run_archive()
            )
            self.window.shell_status_bar.addPermanentWidget(self.import_run_button)

            self._window_lifetime = _WindowLifetime(self._close_presentation, self.window)
            self.window.installEventFilter(self._window_lifetime)
            self.window.destroyed.connect(self._close_presentation)

        def _close_presentation(self, *_):
            with self._authority_dispatch_lock:
                if self._closed:
                    return
                self._closed = True
                queued = bool(self._queued_authority_commands)
                self._queued_authority_commands.clear()
            if queued:
                try:
                    self.window.set_application_status("Window closed; queued operation not started.", "warning")
                except RuntimeError:
                    # Destruction can also close presentation after Qt has
                    # already removed the window's underlying widgets.
                    pass
            self._pending_commands.clear()
            self._active_progress_timer.stop()
            self._active_projection_epoch += 1
            self._projection_worker.close()
            self._selection_worker.close()
            self._sidebar_worker.close()
            self._sidebar_refresh_revision += 1
            with self._activity_lock:
                self._queued_activity = None

        def _emit(self, signal, *args):
            if not self._closed:
                try:
                    signal.emit(*args)
                except RuntimeError:
                    # A worker may finish after Qt has destroyed its receiver.
                    pass

        @classmethod
        def from_planning_session(
            cls,
            *,
            application_icon: QIcon,
            session: PlanningApplicationSession,
            request_resolver: ApplicationRequestResolver,
            shell_preferences=None,
            console_preferences=None,
            initial_sidebar_projection: SidebarProjection | None = None,
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
            authority_dispatcher: AuthorityDispatcher | None = None,
            failure_handler: FailureHandler | None = None,
            parent=None,
        ) -> "BenchmarkDesktopApplication":
            """Compose the desktop over the concrete shared application session."""

            boundary = PlanningSessionApplicationBoundary(
                session=session,
                request_resolver=request_resolver,
                repository_root=repository_root,
            )
            projector = SharedApplicationProjector(
                boundary,
                sidebar_template=initial_sidebar_projection,
                workspace_projector=workspace_projector,
                runner_sources=runner_sources,
                benchmark_candidates=benchmark_candidates,
                repository_root=repository_root,
                executable_resolver=executable_resolver,
                authentication_probe=authentication_probe,
                model_discovery_probe=model_discovery_probe,
                environment_entries=environment_entries,
            )
            return cls(
                application_icon=application_icon,
                shared_application_boundary=boundary,
                projector=projector,
                shell_preferences=shell_preferences,
                console_preferences=console_preferences,
                initial_sidebar_projection=initial_sidebar_projection,
                sidebar_refresh_projector=projector.sidebar_for_runner,
                sidebar_intent_projector=projector.sidebar_from_intent,
                sidebar_environment_projector=projector.environment_for_sidebar,
                authority_dispatcher=authority_dispatcher,
                failure_handler=failure_handler,
                parent=parent,
            )

        @classmethod
        def from_repository_authority(
            cls,
            *,
            application_icon: QIcon,
            request_resolver: ApplicationRequestResolver | None = None,
            repository_root: str | Path | None = None,
            shell_preferences=None,
            console_preferences=None,
            initial_sidebar_projection: SidebarProjection | None = None,
            workspace_projector: WorkspaceProjector | None = None,
            executable_resolver: Callable[[str], str | None] | None = None,
            authentication_probe: Callable[..., bool | None] | None = None,
            model_discovery_probe: Callable[
                ..., Mapping[str, object] | None
            ] | None = None,
            environment_entries: Sequence[EnvironmentDiagnosticEntry] = (),
            authority_dispatcher: AuthorityDispatcher | None = None,
            failure_handler: FailureHandler | None = None,
            parent=None,
        ) -> "BenchmarkDesktopApplication":
            """Compose the desktop from validated repository registration authority."""

            composition = compose_repository_planning_session(repository_root)
            if executable_resolver is None:
                registered_references = {
                    artifact["reference"]
                    for source in composition.authority.runner_sources
                    for artifact in source.registration.get("implementation_artifacts", ())
                    if isinstance(artifact, Mapping) and isinstance(artifact.get("reference"), str)
                }
                def executable_resolver(selected: str) -> str | None:
                    # Registered path selections belong to repository authority,
                    # independently of the directory that launched the desktop.
                    if selected in registered_references and not Path(selected).is_absolute():
                        return which(str(composition.authority.repository_root / selected))
                    return which(selected)
            repository_request_resolver = request_resolver
            if repository_request_resolver is None:
                repository_request_resolver = RepositoryApplicationRequestResolver(
                    composition.authority
                )
            repository_sidebar_projection = _repository_sidebar_projection(
                initial_sidebar_projection,
                composition.authority.prerequisite_diagnostics,
            )
            repository_authentication_probe = authentication_probe
            if repository_authentication_probe is None:
                repository_authentication_probe = (
                    lambda source, selected_control_values=None: (
                        probe_registered_runner_authentication(
                            source,
                            repository_root=composition.authority.repository_root,
                            selected_control_values=selected_control_values,
                        )
                    )
                )
            repository_model_discovery_probe = model_discovery_probe
            if repository_model_discovery_probe is None:
                repository_model_discovery_probe = (
                    lambda source, selected_control_values=None: (
                        probe_registered_runner_model_discovery(
                            source,
                            repository_root=composition.authority.repository_root,
                            selected_control_values=selected_control_values,
                            executable_resolver=executable_resolver,
                        )
                    )
                )
            return cls.from_planning_session(
                application_icon=application_icon,
                session=composition.session,
                request_resolver=repository_request_resolver,
                shell_preferences=shell_preferences,
                console_preferences=console_preferences,
                initial_sidebar_projection=repository_sidebar_projection,
                workspace_projector=workspace_projector,
                runner_sources=composition.authority.runner_sources,
                benchmark_candidates=composition.authority.benchmark_candidates,
                repository_root=composition.authority.repository_root,
                executable_resolver=executable_resolver,
                authentication_probe=repository_authentication_probe,
                model_discovery_probe=repository_model_discovery_probe,
                environment_entries=environment_entries,
                authority_dispatcher=authority_dispatcher,
                failure_handler=failure_handler,
                parent=parent,
            )

        @property
        def shared_application_boundary(self) -> SharedApplicationBoundary:
            return self._boundary

        @property
        def application_projector(self) -> ApplicationProjector:
            return self._projector

        @property
        def environment_projection(self) -> ApplicationEnvironmentProjection:
            return self._environment_projection

        @property
        def authority_semantics(self) -> str:
            return "shared-application-client"

        def show(self) -> object:
            self.window.show()
            return self.request_discovery()

        def _apply_sidebar_refresh(self, projection: SidebarProjection) -> None:
            """Apply selected-scope sidebar state and refresh Environment with it."""

            if not isinstance(projection, SidebarProjection):
                raise ValueError("projection must be a SidebarProjection")
            self.window.set_sidebar_projection(projection)

            environment_projector = self._sidebar_environment_projector
            if environment_projector is None:
                return
            try:
                environment = environment_projector(projection)
                if not isinstance(environment, ApplicationEnvironmentProjection):
                    raise ValueError(
                        "sidebar_environment_projector must return "
                        "ApplicationEnvironmentProjection"
                    )
            except Exception as exc:
                environment = ApplicationEnvironmentProjection(
                    entries=(environment_projection_failure_entry(exc),)
                )
            self._environment_projection = environment
            self.window.set_environment_projection(environment.render())

        def _queue_sidebar_refresh(self, operation, runner_label):
            if self._closed:
                return
            self._sidebar_refresh_revision += 1
            revision = self._sidebar_refresh_revision
            self._sidebar_refresh_pending = True
            label = "Checking runner…" if runner_label else "Runner not selected"
            self.window.set_connectivity_status(label, "active" if runner_label else "neutral")
            check_detail = (
                f"{runner_label or 'No selected runner'}\nChecking the selected runner's declared connection surface."
            )
            self.window.connectivity_status.setAccessibleDescription(check_detail)
            self.window.build_plan_button.setEnabled(False)
            self.window.set_runner_check_pending(True)

            def refresh():
                try:
                    projection = operation()
                    if not isinstance(projection, SidebarProjection):
                        raise ValueError("sidebar projector must return SidebarProjection")
                    environment = None
                    if self._sidebar_environment_projector is not None:
                        environment = self._sidebar_environment_projector(projection)
                        if not isinstance(environment, ApplicationEnvironmentProjection):
                            raise ValueError("environment projector returned invalid state")
                    result = (revision, projection, environment, None)
                except Exception as exc:
                    result = (revision, None, None, exc)
                if self._background_projection:
                    self._emit(self._gui_dispatcher.sidebar_ready, *result)
                else:
                    self._receive_sidebar_refresh(*result)

            if self._background_projection:
                self._sidebar_worker.submit("sidebar", refresh)
            else:
                refresh()

        def _receive_sidebar_refresh(self, revision, projection, environment, error):
            if self._closed or revision != self._sidebar_refresh_revision:
                return
            self._sidebar_refresh_pending = False
            self.window.set_runner_check_pending(False)
            if error is not None:
                self.window.set_connectivity_status("Runner check failed", "error")
                runner = self.window.sidebar_input_snapshot().runner or "No selected runner"
                detail = f"{runner}\nThe selected-runner check failed. Use Check to retry."
                self.window.connectivity_status.setAccessibleDescription(detail)
                # Do not restore stale build authority after a failed refresh.
                self.window.build_plan_button.setEnabled(False)
                if self._failure_handler is not None:
                    self._failure_handler("runner_connectivity", error)
                return
            self.window.set_sidebar_projection(projection)
            if environment is not None:
                self._environment_projection = environment
                self.window.set_environment_projection(environment.render())

        def request_refresh_connectivity(self, *_):
            if self._sidebar_intent_projector is None or self._pending_commands:
                return
            self._refresh_sidebar_intent(self.window.sidebar_input_snapshot())

        def _refresh_benchmark_selection(self, benchmark_label: str) -> None:
            refresher = self._sidebar_intent_projector
            if refresher is None:
                return
            _text(benchmark_label, name="benchmark_label")
            self._refresh_sidebar_intent(self.window.sidebar_input_snapshot())

        def _refresh_runner_selection(self, runner_label: str) -> None:
            refresher = self._sidebar_refresh_projector
            if refresher is None:
                return
            intent = self.window.sidebar_input_snapshot()
            self._queue_sidebar_refresh(lambda: refresher(intent, runner_label), runner_label)

        def _refresh_sidebar_intent(self, intent: SidebarInputSnapshot) -> None:
            refresher = self._sidebar_intent_projector
            if refresher is None:
                return
            if not isinstance(intent, SidebarInputSnapshot):
                raise ValueError("intent must be SidebarInputSnapshot")
            # Until the new runner's projection arrives, controls still belong
            # to the previously displayed runner. Never carry those values
            # into a replacement refresh for the new runner.
            projected_runner = self.window._sidebar_projection.selected_runner
            if (intent.runner is not None and intent.runner != projected_runner
                    and self._sidebar_refresh_projector is not None):
                self._queue_sidebar_refresh(
                    lambda: self._sidebar_refresh_projector(intent, intent.runner), intent.runner
                )
            else:
                self._queue_sidebar_refresh(lambda: refresher(intent), intent.runner)

        def _active_generation_for(self, generation_id: str | None) -> str | None:
            active_generation_id = (
                self.window.console_widget.state.active_generation_id
            )
            if (
                generation_id is None
                or active_generation_id is None
                or generation_id != active_generation_id
            ):
                return None
            return active_generation_id

        def _selected_bound_generation_id(self) -> str | None:
            selected = getattr(self._boundary, "selected_terminal", None)
            selected_generation_id = getattr(selected, "generation_id", None)
            if not isinstance(selected_generation_id, str):
                return None
            return self._active_generation_for(selected_generation_id)

        def request_discovery(self) -> object:
            return self._submit("discover", self._boundary.discover)

        def _sync_prerequisite_projection(
            self,
            intent: SidebarInputSnapshot | None = None,
        ) -> None:
            """Refresh shared prerequisite evidence without using widget state as authority."""

            if not isinstance(self._boundary, PlanningSessionApplicationBoundary):
                return
            if not isinstance(self._projector, SharedApplicationProjector):
                return
            projection = self._projector.prerequisite_projection(intent)
            self._boundary.set_prerequisite_projection(projection)

        def request_build_plan(self, intent: SidebarInputSnapshot) -> object:
            if self._command_blocked("build_plan"):
                return None
            if not isinstance(intent, SidebarInputSnapshot):
                raise ValueError("intent must be SidebarInputSnapshot")
            if isinstance(self._projector, SharedApplicationProjector):
                self.apply_projection_update(
                    self._projector.build_plan_requested_update()
                )

            def build_plan() -> object:
                self._sync_prerequisite_projection(intent)
                return self._boundary.build_plan(intent)

            return self._submit(
                "build_plan",
                build_plan,
            )

        def request_select_run(self, run_id: str) -> object:
            _text(run_id, name="run_id")
            return self._submit(
                "select_run",
                lambda: self._boundary.select_run(run_id),
                failure_generation_id=self._active_generation_for(run_id),
            )

        def request_delete_run(self, run_id: str) -> object:
            if self._command_blocked("delete_run"):
                return None
            run_id = _text(run_id, name="run_id")
            if isinstance(self._projector, SharedApplicationProjector):
                self.apply_projection_update(
                    self._projector.delete_run_requested_update(run_id)
                )
            return self._submit(
                "delete_run",
                lambda: self._boundary.delete_run(run_id),
                failure_generation_id=run_id,
            )

        def request_accept_plan(self) -> object:
            if isinstance(
                self._boundary,
                PlanningSessionApplicationBoundary,
            ):
                def accept_plan() -> object:
                    self._sync_prerequisite_projection()
                    return self._boundary.accept_plan()

                return self._submit("accept_plan", accept_plan)
            return self._submit("accept_plan", self._boundary.accept_plan)

        def request_cancel_benchmark(self):
            cancel = getattr(self._boundary, "cancel_benchmark", None)
            if callable(cancel):
                cancel()
                self.window.cancel_execution_button.setEnabled(False)
                self.window.cancel_execution_button.setText("Cancelling…")

        def request_start_benchmark(self) -> object:
            if self._command_blocked("start_benchmark"):
                return None
            # The accepted request owns the capture identity. Current sidebar
            # values may describe a different, unplanned safe configuration.
            accepted_request = getattr(self._boundary, "plan_request", None)
            accepted_snapshot = getattr(self._boundary, "accepted_snapshot", None)
            execution_boundary = getattr(accepted_request, "execution_boundary", None)
            before_execution = None
            if execution_boundary is not None:
                document = execution_boundary.to_dict()
                controls = {item["name"]: item["value"] for item in document["controls"]}
                if controls.get("capture_mode") == "deep_telemetry":
                    runner = document["runner"]
                    try:
                        grant = self.window.diagnostic_execution_grant(
                            f"{runner['id']}@{runner['version']}",
                            controls.get("diagnostic_privacy_acknowledged"))
                    except DiagnosticConsentRequired:
                        self.window.show_diagnostic_consent_required()
                        return None

                    def before_execution():
                        grant.require_valid()
                        if (getattr(self._boundary, "plan_request", None) is not accepted_request
                                or getattr(self._boundary, "accepted_snapshot", None) is not accepted_snapshot):
                            raise DiagnosticConsentRequired()

            if isinstance(
                self._boundary,
                PlanningSessionApplicationBoundary,
            ):
                button = self.window.cancel_execution_button
                if not getattr(self, "_cancel_connected", False):
                    button.clicked.connect(self.request_cancel_benchmark)
                    self._cancel_connected = True
                button.setText("Cancel")
                button.setEnabled(True)
                active_generation: dict[str, str | None] = {"generation_id": None}

                def execution_started(
                    execution_request: ApplicationExecutionRequest,
                    plan: RunPlan,
                ) -> None:
                    active_generation["generation_id"] = (
                        execution_request.generation_id
                    )
                    self._emit_execution_started(execution_request, plan)

                def start_benchmark() -> object:
                    self._sync_prerequisite_projection()
                    if before_execution is not None:
                        before_execution()
                    return self._boundary.start_benchmark(
                        on_execution_started=execution_started,
                        on_live_view=self._queue_live_view,
                        live_view_control=self.window.console_widget.live_view_control,
                        on_activity=self._queue_activity,
                        before_execution=before_execution,
                    )

                return self._submit(
                    "start_benchmark",
                    start_benchmark,
                    failure_generation_id_provider=(
                        lambda: active_generation["generation_id"]
                    ),
                )
            def start_benchmark():
                if before_execution is not None:
                    before_execution()
                return self._boundary.start_benchmark()
            return self._submit("start_benchmark", start_benchmark)

        def _queue_live_view(self, event) -> None:
            if self._closed:
                return
            channel = event.get("channel")
            if channel not in {"input", "output"}:
                return
            self.window.console_widget.queue_live_view(
                event["generation_id"], event["invocation_id"],
                input_text=event["text"] if channel == "input" else None,
                output_text=event["text"] if channel == "output" else None,
                stream_revision=event.get("stream_revision"),
                treatment_name=event.get("treatment_name"),
            )

        def request_test_runner(self, intent: SidebarInputSnapshot) -> object:
            if not isinstance(intent, SidebarInputSnapshot):
                raise ValueError("intent must be SidebarInputSnapshot")
            if self._command_blocked("test_runner"):
                return None
            controls = {item.control_name: item.value for item in intent.additional_controls}
            before_execution = None
            if controls.get("capture_mode") == "deep_telemetry":
                try:
                    grant = self.window.diagnostic_execution_grant(
                        intent.runner, controls.get("diagnostic_privacy_acknowledged"))
                except DiagnosticConsentRequired:
                    self.window.show_diagnostic_consent_required()
                    return None
                before_execution = grant.require_valid
            test_runner = getattr(self._boundary, "test_runner", None)
            if not callable(test_runner):
                raise RuntimeError("runner diagnostic is unavailable")
            def execute_test():
                if before_execution is not None:
                    before_execution()
                if isinstance(self._boundary, PlanningSessionApplicationBoundary):
                    return test_runner(intent, before_execution=before_execution)
                return test_runner(intent)
            return self._submit("test_runner", execute_test)

        def _emit_execution_started(
            self,
            execution_request: ApplicationExecutionRequest,
            plan: RunPlan,
        ) -> None:
            """Queue non-authoritative active execution presentation on the GUI thread."""

            if self._closed or "start_benchmark" not in self._pending_commands:
                return
            if isinstance(self._boundary, PlanningSessionApplicationBoundary):
                current = self._boundary.execution_request
                if current is None or current.generation_id != execution_request.generation_id:
                    return
            # Prime the producer-side generation before a fast subprocess can
            # emit its first bytes; actual widget binding stays on the GUI thread.
            with self._activity_lock:
                self._activity_generation_id = execution_request.generation_id
                self._queued_activity = None
            self.window.console_widget.queue_bind_generation(execution_request.generation_id)
            self._emit(self._gui_dispatcher.execution_started,
                execution_request,
                plan,
            )

        def _refresh_report_page(self):
            terminal = getattr(self._boundary, "selected_terminal", None)
            if type(terminal) not in (AcceptedRun, BlockedRun):
                return
            from AgMark.gui.projection.workspace.reports import _reports_projection
            page = self.window.workspace_pages.get("Reports")
            if not hasattr(page, "set_projection") or page.run_id != terminal.generation_id:
                return
            state, reason = getattr(self._boundary, "report_state", lambda _: (None, None))(terminal.generation_id)
            bundle = getattr(self._boundary, "report_bundle", None)
            feedback = getattr(self._boundary, "export_feedback", lambda *args: "")(terminal.generation_id, bundle.report_document["report_id"]) if bundle else ""
            page.set_projection(_reports_projection(terminal, bundle, getattr(self._boundary, "verification", None), self,
                generation_state=state, generation_reason=reason, export_feedback=feedback,
                completion_diagnostics=getattr(self._boundary, "completion_diagnostics", lambda _: ())(terminal.generation_id)))

        def request_import_run_archive(self, snapshot_path=None):
            """Validate and import a sealed .agmark file into untrusted run history."""
            if snapshot_path is None:
                from PySide6.QtWidgets import QFileDialog
                snapshot_path, _ = QFileDialog.getOpenFileName(
                    self.window,
                    "Import AgMark Run",
                    "",
                    "AgMark archives (*.agmark)",
                )
                if not snapshot_path:
                    return None
            from AgMark.shared.validation import validate_run_archive
            result = validate_run_archive(snapshot_path)
            imported = False
            issue = None
            if result.consistent:
                try:
                    self._boundary.import_run_archive(snapshot_path)
                    imported = True
                    self.request_discovery()
                except (OSError, ValueError, RuntimeError) as exc:
                    issue = str(exc)
            from PySide6.QtWidgets import QMessageBox
            dialog = QMessageBox(self.window)
            dialog.setWindowTitle("Run archive import")
            dialog.setIcon(
                QMessageBox.Icon.Information if imported
                else QMessageBox.Icon.Warning
            )
            dialog.setText(
                f"Checked {result.files_checked} archived members: "
                + ("imported as a read-only saved run." if imported else
                   ("archive import failed." if issue else "integrity checks did not pass."))
            )
            dialog.setInformativeText(
                "This does not authenticate the run, its author, or its results. "
                "Only supported completed archives can expose retained reports."
            )
            if result.issues or issue:
                dialog.setDetailedText("\n".join((*result.issues, *((issue,) if issue else ()))))
            dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
            dialog.open()
            self._import_validation_dialog = dialog
            return result

        def request_show_verification(self):
            from AgMark.gui.shell.projections import WORKSPACE_TAB_LABELS
            self.window.workspace_tabs.set_selected_index(WORKSPACE_TAB_LABELS.index("Verification"))

        def request_export_report(self, generation_id, report_id, destination=None):
            selected = getattr(self._boundary, "selected_terminal", None)
            bundle = getattr(self._boundary, "report_bundle", None)
            if selected is None or selected.generation_id != generation_id or bundle is None or bundle.report_document.get("report_id") != report_id:
                raise ValueError("export selection changed")
            if destination is None:
                from PySide6.QtWidgets import QFileDialog
                destination, _ = QFileDialog.getSaveFileName(self.window, "Export Report", "report.md", "Markdown (*.md);;All files (*)")
                if not destination:
                    destination = None
            try:
                result = self._boundary.export_report(generation_id, report_id, destination)
            except Exception:
                self._refresh_report_page()
                return None
            self._refresh_report_page()
            return result



        def _command_blocked(self, command: str) -> bool:
            # Selection remains independently scoped during reporting/verification.
            exclusive = {"discover", "build_plan", "accept_plan", "test_runner", "delete_run"}
            return self._closed or (self._sidebar_refresh_pending and command in {
                "build_plan", "accept_plan", "test_runner", "start_benchmark"
            }) or (self._selecting_run and command in {
                "delete_run"
            }) or bool(self._pending_commands & exclusive) or (
                command != "select_run" and command in self._pending_commands
            ) or (command in exclusive and "start_benchmark" in self._pending_commands)

        def _refresh_operation_activity(self) -> None:
            if self._closed:
                return
            request = getattr(self._boundary, "plan_request", None)
            custom = request is not None and request.extensions.get("arcgrav.runtime:execution-only") is True
            self.window.cancel_execution_button.setVisible(custom and "start_benchmark" in self._pending_commands)
            labels = {
                "discover": "Loading benchmarks…", "build_plan": "Building plan…",
                "accept_plan": "Accepting plan…", "start_benchmark": "Running benchmark…",
                "test_runner": "Testing runner…", "delete_run": "Deleting run…",
            }
            if self._active_activity is not None:
                labels["start_benchmark"] = activity_text(self._active_activity)
            if self._preparing_benchmark_results:
                labels["start_benchmark"] = "Preparing retained results and saving history…"
            self.window.set_operation_activity(
                (("Loading selected run…",) if self._selecting_run else ()) +
                tuple(labels[command] for command in labels if command in self._pending_commands),
                lock_controls=bool(self._pending_commands & {
                    "discover", "build_plan", "accept_plan", "test_runner", "delete_run"
                }),
            )

        def _finish_operation(self, command: str) -> None:
            self._pending_commands.discard(command)
            if command == "select_run":
                self._set_selecting_run(False)
            self._refresh_operation_activity()

        def _set_selecting_run(self, value):
            self._selecting_run = value
            if self._closed:
                return

        def _submit(
            self,
            command: str,
            operation: AuthorityOperation,
            *,
            failure_generation_id: str | None = None,
            failure_generation_id_provider: (
                FailureGenerationProvider | None
            ) = None,
        ) -> object:
            if command not in _COMMANDS:
                raise ValueError("unsupported application command")
            if failure_generation_id is not None:
                _text(failure_generation_id, name="failure_generation_id")
            if failure_generation_id_provider is not None and not callable(
                failure_generation_id_provider
            ):
                raise ValueError(
                    "failure_generation_id_provider must be callable or None"
                )

            if self._command_blocked(command):
                return None
            revision = self._command_revisions.get(command, 0) + 1
            self._command_revisions[command] = revision
            if command in {"discover", "build_plan", "accept_plan", "start_benchmark", "select_run", "delete_run"}:
                self._workspace_revision += 1
            workspace_revision = self._workspace_revision
            if command == "select_run":
                self._set_selecting_run(True)
                self._refresh_operation_activity()
            if command != "select_run":
                self._pending_commands.add(command)
                self._refresh_operation_activity()
            if command == "test_runner":
                self.window.set_runner_status(
                    "Testing runner…", "active",
                    "Diagnostic Test in progress. The connection Check is separate.",
                )
            with self._authority_dispatch_lock:
                # Keep only the latest queued revision for each command, just
                # as selection dispatch replaces superseded pending work.
                self._queued_authority_commands[command] = revision

            def invoke() -> None:
                with self._authority_dispatch_lock:
                    if self._queued_authority_commands.get(command) == revision:
                        self._queued_authority_commands.pop(command)
                    if self._closed or (command == "select_run" and revision != self._command_revisions.get(command)):
                        return
                try:
                    result = operation()
                except BaseException as exc:
                    failure_target = failure_generation_id
                    if (
                        failure_target is None
                        and failure_generation_id_provider is not None
                    ):
                        try:
                            failure_target = failure_generation_id_provider()
                        except Exception:
                            failure_target = None
                        if failure_target is not None:
                            try:
                                _text(
                                    failure_target,
                                    name="failure_generation_id",
                                )
                            except ValueError:
                                failure_target = None
                    self._emit(self._gui_dispatcher.operation_failed,
                        command,
                        exc,
                        failure_target,
                        revision,
                    )
                    return
                self._emit(self._gui_dispatcher.operation_ready, command, result, revision, workspace_revision)

            try:
                if command == "select_run" and self._background_projection:
                    # Serial authority selection prevents an older slow read
                    # from mutating the selected boundary after the latest one.
                    return self._selection_worker.submit("select", invoke)
                return self._authority_dispatcher(invoke)
            except Exception as exc:
                with self._authority_dispatch_lock:
                    if self._queued_authority_commands.get(command) == revision:
                        self._queued_authority_commands.pop(command)
                self._apply_failure(command, exc, failure_generation_id)
                return None

        def _receive_failure(self, command, error, generation_id, revision):
            if self._closed or revision != self._command_revisions.get(command):
                return
            self._gui_dispatcher.failure_ready.emit(command, error, generation_id)

        def _receive_result(self, command, result, revision, workspace_revision):
            if self._closed or revision != self._command_revisions.get(command):
                return
            if command == "start_benchmark":
                self._preparing_benchmark_results = True
                # Invalidate in-flight evidence refreshes while retaining the
                # timer for elapsed time and the visible finalization stage.
                self._active_projection_epoch += 1
                self._active_projection_pending = None
                self._refresh_operation_activity()
                self._render_active_progress()
            prepare = getattr(self._projector, "prepare_result", None)
            if (self._background_projection and callable(prepare)
                    and command in {"start_benchmark", "select_run"}):
                if command != "start_benchmark":
                    # Priority work replaces a queued active refresh. Invalidate
                    # its token so the next timer tick can request a fresh one.
                    self._active_projection_epoch += 1
                    self._active_projection_pending = None

                def prepare_projection():
                    try:
                        prepared, error = prepare(command, result, self), None
                    except Exception as exc:
                        prepared, error = None, exc
                    self._emit(self._gui_dispatcher.prepared_ready,
                               command, result, prepared, revision, workspace_revision, error)

                self._projection_worker.submit("result:" + command, prepare_projection, priority=True)
                return
            self._receive_prepared_result(command, result, None, revision, workspace_revision, None)

        def _receive_prepared_result(self, command, result, prepared, revision, workspace_revision, error):
            if self._closed or revision != self._command_revisions.get(command):
                return
            # One native notification for the whole execution, after all cases
            # and retained results finish, even if another run is now selected.
            if command == "start_benchmark" and command in self._pending_commands and error is None:
                QApplication.beep()
            if workspace_revision != self._workspace_revision and command in {"start_benchmark", "select_run"}:
                if command == "start_benchmark":
                    self._stop_active_progress_poll()
                self._finish_operation(command)
                return
            if error is not None:
                self._apply_failure(command, error, getattr(result, "generation_id", None))
                return
            self._prepared_for_apply = (command, result, prepared)
            try:
                self._gui_dispatcher.result_ready.emit(command, result)
            finally:
                self._prepared_for_apply = None

        def _apply_execution_started(
            self,
            execution_request: object,
            plan: object,
        ) -> None:
            """Project exact active-generation state on the GUI thread."""

            if self._closed or "start_benchmark" not in self._pending_commands:
                return
            if type(execution_request) is not ApplicationExecutionRequest:
                return
            if isinstance(self._boundary, PlanningSessionApplicationBoundary):
                current = self._boundary.execution_request
                if current is None or current.generation_id != execution_request.generation_id:
                    return
            if type(plan) is not RunPlan:
                return
            started_projector = getattr(
                self._projector,
                "execution_started_update",
                None,
            )
            if not callable(started_projector):
                return
            update = started_projector(execution_request, plan)
            if not isinstance(update, ApplicationProjectionUpdate):
                raise ValueError(
                    "execution-start projector must return ApplicationProjectionUpdate"
                )
            self.apply_projection_update(update)
            self._start_active_progress_poll(execution_request, plan)

        def _queue_activity(self, event):
            """Constant-time ingress: retain the latest snapshot, not a Qt queue per event."""
            if self._closed or type(event) is not RunActivity:
                return
            with self._activity_lock:
                expected_generation = self._activity_generation_id or self._active_progress_generation_id
                if event.generation_id != expected_generation:
                    return
                previous = self._queued_activity
                if previous is None or previous.generation_id != event.generation_id or event.sequence > previous.sequence:
                    self._queued_activity = event
                if self._activity_notification_pending:
                    return
                self._activity_notification_pending = True
            self._emit(self._gui_dispatcher.activity_pending)

        def _drain_activity(self):
            with self._activity_lock:
                event = self._queued_activity
                self._queued_activity = None
                self._activity_notification_pending = False
            if not self._closed and event is not None:
                self._gui_dispatcher.activity_ready.emit(event)

        def _apply_activity(self, event):
            if (self._closed or type(event) is not RunActivity or "start_benchmark" not in self._pending_commands
                    or event.generation_id != self._active_progress_generation_id
                    or (self._active_activity is not None and event.sequence <= self._active_activity.sequence)):
                return
            previous_phase = self._active_activity.phase if self._active_activity is not None else None
            self._active_activity = event
            self._activity_received_at = monotonic()
            if previous_phase != event.phase or event.terminal:
                self._refresh_operation_activity()
                self._render_active_progress()

        def _start_active_progress_poll(
            self,
            execution_request: ApplicationExecutionRequest,
            plan: RunPlan,
        ) -> None:
            self._active_activity = None
            self._activity_received_at = None
            self._active_progress_started_at = monotonic()
            self._preparing_benchmark_results = False
            self._active_progress_generation_id = execution_request.generation_id
            self._active_progress_plan = plan
            self._active_progress_store = execution_request.artifact_store
            with self._activity_lock:
                self._activity_generation_id = execution_request.generation_id
            self._active_projection_epoch += 1
            self._active_projection_pending = None
            self._active_progress_projection = getattr(self.window.workspace_pages.get("Progress"), "projection", None)
            self._refresh_active_progress()
            if not self._active_progress_timer.isActive():
                self._active_progress_timer.start()

        def _stop_active_progress_poll(self) -> None:
            if self._active_progress_timer.isActive():
                self._active_progress_timer.stop()
            self._active_activity = None
            self._activity_received_at = None
            self._active_progress_started_at = None
            self._preparing_benchmark_results = False
            self._active_progress_generation_id = None
            self._active_progress_plan = None
            self._active_progress_store = None
            with self._activity_lock:
                self._activity_generation_id = None
                self._queued_activity = None
            self._active_projection_epoch += 1
            self._active_projection_pending = None
            self._active_progress_projection = None

        def _render_active_progress(self):
            if self._closed or self._active_progress_projection is None:
                return
            if self.window.workspace_projection_run_id != self._active_progress_generation_id:
                return
            page = self.window.workspace_pages.get("Progress")
            if not hasattr(page, "set_projection"):
                return
            projection = self._active_progress_projection
            if self._active_activity is not None:
                elapsed = self._active_activity.elapsed_seconds + max(0, monotonic() - self._activity_received_at)
                projection = with_activity(projection, self._active_activity, elapsed)
            elif self._active_progress_started_at is not None and projection.overall is not None:
                seconds = int(max(0, monotonic() - self._active_progress_started_at))
                projection = replace(projection, overall=replace(
                    projection.overall, elapsed_time=f"{seconds // 60:02d}:{seconds % 60:02d}"))
            if "start_benchmark" in self._pending_commands and (
                    projection.lifecycle_complete or self._preparing_benchmark_results):
                # Shared execution completion precedes desktop preparation.
                # Keep its outcome/evidence facts, but reserve visual completion
                # until the prepared workspace has actually been applied.
                text = "Preparing retained results and saving history…"
                projection = replace(projection, run_active=True, lifecycle_complete=False,
                    active_stage_index=4, active_stage_description=text,
                    run_stage_empty_state=None, activity_text=text, current_stage_step=None)
            page.set_projection(projection)
            evidence_page = self.window.workspace_pages.get("Evidence")
            if (hasattr(evidence_page, "set_capture_projection")
                    and evidence_page.run_id == projection.run_id):
                evidence_page.set_capture_projection(projection)

        def _refresh_active_progress(self) -> None:
            if self._closed:
                return
            if self._preparing_benchmark_results:
                self._render_active_progress()
                return
            generation_id = self._active_progress_generation_id
            plan = self._active_progress_plan
            store = self._active_progress_store
            if generation_id is None or type(plan) is not RunPlan or store is None:
                self._stop_active_progress_poll()
                return
            if self.window.workspace_projection_run_id != generation_id:
                return
            self._render_active_progress()
            token = (generation_id, self._active_projection_epoch)
            if self._active_projection_pending == token:
                return
            self._active_projection_pending = token

            def prepare_active():
                from AgMark.gui.projection.workspace.results import active_results_projection
                from AgMark.gui.projection.workspace.activity import with_retained_activity
                from AgMark.gui.views.results import ResultsProjection
                try:
                    progress = with_retained_activity(active_retained_progress_projection(generation_id, plan, store), store)
                except Exception:
                    progress = None
                try:
                    results = active_results_projection(generation_id, plan, store)
                except Exception:
                    results = ResultsProjection(run_id=generation_id, empty_state="Active measurement evidence unavailable or invalid.")
                self._emit(self._gui_dispatcher.active_projection_ready, generation_id, token[1], progress, results)

            if self._background_projection:
                self._projection_worker.submit("active", prepare_active)
            else:
                prepare_active()

        def _apply_active_projection(self, generation_id, epoch, progress, results):
            if self._closed or (generation_id, epoch) != self._active_projection_pending:
                return
            self._active_projection_pending = None
            if generation_id != self._active_progress_generation_id or self.window.workspace_projection_run_id != generation_id:
                return
            if progress is not None:
                self._active_progress_projection = progress
                self._render_active_progress()
            results_page = self.window.workspace_pages.get("Results")
            if hasattr(results_page, "set_projection") and results_page.run_id == generation_id:
                results_page.set_projection(results)
            scoring_page = self.window.workspace_pages.get("Scoring")
            if hasattr(scoring_page, "set_projection") and scoring_page.run_id == generation_id:
                scoring_page.set_projection(results)

        def _apply_result(self, command: str, result: object) -> None:
            if self._closed:
                return
            try:
                self._project_result(command, result)
            except Exception as exc:
                self._apply_failure(command, exc, None)
            finally:
                self._finish_operation(command)

        def _project_result(self, command: str, result: object) -> None:
            if command == "test_runner":
                if type(result) is not RunnerTestResult:
                    raise ValueError("test_runner projection requires RunnerTestResult")
                test_entry = _runner_test_environment_entry(result)
                retained_entries = tuple(
                    entry
                    for entry in self._environment_projection.entries
                    if entry.source != test_entry.source
                )
                self._environment_projection = ApplicationEnvironmentProjection(
                    entries=retained_entries + (test_entry,)
                )
                self.window.set_environment_projection(
                    self._environment_projection.render()
                )
                self.window.set_runner_status(
                    "Test passed" if result.passed else "Test failed",
                    "success" if result.passed else "error",
                    ("The diagnostic Test completed with a retained response."
                     if result.passed else
                     "The diagnostic Test failed or had no retained response.")
                    + " The connection Check is separate; details are in Environment.",
                )
                return

            prepared = self._prepared_for_apply
            if prepared is not None and prepared[0] == command and prepared[1] is result and prepared[2] is not None:
                update = self._projector(command, result, self, prepared=prepared[2])
            else:
                update = self._projector(command, result, self)
            if not isinstance(update, ApplicationProjectionUpdate):
                raise ValueError("projector must return ApplicationProjectionUpdate")
            self.apply_projection_update(update)
            if command in {
                "build_plan",
                "accept_plan",
                "start_benchmark",
                "select_run",
                "delete_run",
            } and not (command == "select_run" and "start_benchmark" in self._pending_commands):
                self._stop_active_progress_poll()

        def _apply_failure(
            self,
            command: str,
            error: object,
            generation_id: object,
        ) -> None:
            if self._closed:
                return
            self._finish_operation(command)
            if isinstance(error, DiagnosticConsentRequired):
                if command == "test_runner":
                    self.window.set_runner_status(
                        "Test not run", "neutral",
                        "The diagnostic Test did not run because consent is required. "
                        "The connection Check is separate.",
                    )
                if command == "start_benchmark":
                    if isinstance(generation_id, str):
                        self.window.console_widget.detach_generation(generation_id)
                    self._stop_active_progress_poll()
                    if (isinstance(self._projector, SharedApplicationProjector)
                            and self._boundary.accepted_snapshot is not None):
                        self.apply_projection_update(self._projector(
                            "accept_plan", self._boundary.accepted_snapshot, self))
                self.window.show_diagnostic_consent_required()
                return
            if not isinstance(error, BaseException):
                error = RuntimeError("shared application operation failed")
            if generation_id is not None and not isinstance(generation_id, str):
                generation_id = None

            label = command.replace("_", " ").title()
            self.window.set_application_status(f"{label} failed", "error")
            if command == "test_runner":
                self.window.set_runner_status(
                    "Test failed", "error",
                    "The diagnostic Test failed before returning a valid result. "
                    "The connection Check is separate; see Environment for details.",
                )

            if generation_id is not None:
                self.window.console_widget.append_diagnostic(
                    generation_id,
                    application_failure_diagnostic(error, source=label),
                )
            else:
                failure_entry = environment_failure_entry(error, source=label)
                retained_entries = tuple(
                    entry
                    for entry in self._environment_projection.entries
                    if entry.source != failure_entry.source
                )
                self._environment_projection = ApplicationEnvironmentProjection(
                    entries=retained_entries + (failure_entry,)
                )
                self.window.set_environment_projection(
                    self._environment_projection.render()
                )

            if command == "start_benchmark" and self._preparing_benchmark_results:
                page = self.window.workspace_pages.get("Progress")
                progress = getattr(page, "projection", None)
                if progress is not None:
                    text = "Retained result preparation or history saving failed."
                    self._active_progress_projection = replace(progress, run_active=False,
                        lifecycle_complete=False, active_stage_description=text, activity_text=text)
                    self._active_activity = None
                    self._render_active_progress()
                self._stop_active_progress_poll()
                if isinstance(self._projector, SharedApplicationProjector):
                    self.apply_projection_update(
                        self._projector.execution_failed_update(preserve_progress=progress is not None))
            elif (
                command == "start_benchmark"
                and isinstance(self._projector, SharedApplicationProjector)
            ):
                preserve_progress = self._active_activity is not None
                if self._active_activity is not None and not self._active_activity.terminal:
                    self._active_activity = replace(self._active_activity, phase="completion", terminal=True,
                        benchmark_outcome="failed", telemetry_outcome="partial" if self._active_activity.sources else "unavailable")
                self._refresh_active_progress()
                self._stop_active_progress_poll()
                self.apply_projection_update(
                    self._projector.execution_failed_update(preserve_progress=preserve_progress)
                )
            elif (
                command == "delete_run"
                and isinstance(self._projector, SharedApplicationProjector)
                and isinstance(generation_id, str)
            ):
                self.apply_projection_update(
                    self._projector.delete_run_failed_update(generation_id)
                )

            if self._failure_handler is not None:
                self._failure_handler(command, error)

        def apply_projection_update(
            self,
            update: ApplicationProjectionUpdate,
        ) -> None:
            """Apply one already-projected update on the GUI thread."""

            if self._closed:
                return
            if not isinstance(update, ApplicationProjectionUpdate):
                raise ValueError("update must be ApplicationProjectionUpdate")
            if update.sidebar is not None and not self._sidebar_refresh_pending:
                self.window.set_sidebar_projection(update.sidebar)
            if update.environment is not None:
                self._environment_projection = update.environment
                self.window.set_environment_projection(update.environment.render())
            if update.clear_current_run:
                self.window.set_current_run_projection(None)
            elif update.current_run is not None:
                self.window.set_current_run_projection(update.current_run)
            if update.clear_workspace:
                self.window.clear_workspace_projection()
            elif update.workspace is not None:
                self.window.set_workspace_projection(
                    update.workspace,
                    run_id=update.workspace_run_id,
                )
            if update.connectivity is not None:
                self.window.set_connectivity_status(*update.connectivity)
            if update.application_status is not None:
                self.window.set_application_status(*update.application_status)
            if update.console is not None:
                console = update.console
                if console.bind_generation:
                    self.window.console_widget.bind_generation(console.generation_id)
                for value in console.live_output:
                    self.window.console_widget.append_live_output(
                        console.generation_id,
                        value,
                    )
                for value in console.diagnostics:
                    self.window.console_widget.append_diagnostic(
                        console.generation_id,
                        value,
                    )
                for invocation_id, input_text, output_text in console.live_view:
                    self.window.console_widget.set_live_view(
                        console.generation_id, invocation_id,
                        input_text=input_text, output_text=output_text,
                        treatment_name=dict(console.live_view_treatments).get(invocation_id),
                    )
                if console.raw_response_supplied:
                    self.window.console_widget.set_raw_response(
                        console.generation_id,
                        console.raw_response,
                    )
else:
    class BenchmarkDesktopApplication:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for BenchmarkDesktopApplication")
