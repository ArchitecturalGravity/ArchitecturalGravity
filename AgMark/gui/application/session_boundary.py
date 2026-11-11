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
    AcceptedRun, ExecutedRun,
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

from .contracts import (
    ApplicationProjectionUpdate, ApplicationProjector, ApplicationRequestResolver,
    ConsoleProjectionUpdate, DesktopCommandPort, RunnerTestResult, SharedApplicationBoundary,
    _text,
)
from .projector import _RunPresentationContext, _redacted_additional_controls, _redacted_intent
from .runner_testing import (
    _runner_test_factory, _runner_test_failure, _runner_test_request,
    _runner_test_result_from_observation,
)
from AgMark.gui.shell.diagnostic_consent import DiagnosticConsentRequired

def _validate_request_resolver(resolver: object) -> None:
    for name in (
        "resolve_plan_request",
        "resolve_execution_request",
        "resolve_report_request",
    ):
        if not callable(getattr(resolver, name, None)):
            raise ValueError(
                "request_resolver must expose callable "
                f"{name}()"
            )



class PlanningSessionApplicationBoundary:
    """Production GUI bridge over the complete shared application session.

    The bridge owns only command adaptation and transient GUI input handling.
    Exact request construction is delegated to a benchmark-neutral resolver,
    while discovery, canonical planning, acceptance, execution sequencing,
    terminal retention, reporting, and reconstruction verification remain owned
    by PlanningApplicationSession.
    """

    def __init__(
        self,
        *,
        session: PlanningApplicationSession,
        request_resolver: ApplicationRequestResolver,
        repository_root: str | Path | None = None,
    ) -> None:
        if type(session) is not PlanningApplicationSession:
            raise ValueError("session must be a PlanningApplicationSession")
        _validate_request_resolver(request_resolver)
        from .history import discover_history
        self._selected_history_id = None
        self._repository_root = Path(repository_root) if repository_root is not None else None
        self._history_enabled = repository_root is not None
        self._history = discover_history(repository_root) if self._history_enabled else {}
        self.history_diagnostics = []
        from threading import Event
        self._cancellation = Event()
        self._session = session
        self._request_resolver = request_resolver
        self._discovery: ApplicationDiscovery | None = None
        self._plan_request: ApplicationPlanRequest | None = None
        self._accepted_snapshot: AcceptedRunSnapshot | None = None
        self._execution_request: ApplicationExecutionRequest | None = None
        self._terminal_runs: dict[str, AcceptedRun | BlockedRun] = {}
        self._run_contexts: dict[str, _RunPresentationContext] = {}
        self._artifact_stores = {}
        self._selected_terminal: AcceptedRun | BlockedRun | None = None
        self._report_bundles: dict[str, GeneratedReportBundle] = {}
        self._verifications: dict[str] = {}
        self._report_states: dict[str, tuple[str, str | None]] = {}
        self._export_feedback: dict[tuple[str, str], str] = {}
        self._transient_credential = ""
        self._transient_runner_controls: tuple[SidebarControlInputSnapshot, ...] = ()

    @property
    def session(self) -> PlanningApplicationSession:
        return self._session

    @property
    def discovery(self) -> ApplicationDiscovery | None:
        return self._discovery

    @property
    def plan_request(self) -> ApplicationPlanRequest | None:
        return self._plan_request

    @property
    def transient_plan_launch_controls(self) -> dict[str, str]:
        """Current plan's process-local launch inputs, never serialized evidence."""
        resolve = getattr(self._request_resolver, "transient_plan_launch_controls", None)
        if self._plan_request is None or not callable(resolve):
            return {}
        return resolve(self._plan_request)

    @property
    def accepted_snapshot(self) -> AcceptedRunSnapshot | None:
        return self._accepted_snapshot

    @property
    def execution_request(self) -> ApplicationExecutionRequest | None:
        return self._execution_request

    @property
    def retained_runs(self) -> tuple[AcceptedRun | BlockedRun, ...]:
        return tuple(self._terminal_runs.values())

    @property
    def selected_terminal(self) -> AcceptedRun | BlockedRun | None:
        return self._selected_terminal

    def artifact_store(self, generation_id):
        return self._artifact_stores.get(generation_id)

    def run_context(self, generation_id: str) -> _RunPresentationContext | None:
        _text(generation_id, name="generation_id")
        return self._run_contexts.get(generation_id)

    @property
    def report_bundle(self) -> GeneratedReportBundle | None:
        selected = self._selected_terminal
        if selected is None:
            return None
        return self._report_bundles.get(selected.generation_id)

    @property
    def verification(self) -> None:
        """There is no separate reconstruction result after completion."""
        return None

    def workspace_evidence(self, generation_id):
        """Read the completed report independently of current selection."""
        return self._report_bundles.get(generation_id), None

    def discover(self) -> ApplicationDiscovery:
        result = self._session.discover()
        if type(result) is not ApplicationDiscovery:
            raise RuntimeError("shared discovery returned invalid application authority")
        self._discovery = result
        return result

    def set_prerequisite_projection(
        self,
        projection: ApplicationPrerequisiteProjection,
    ) -> None:
        """Supply current verified readiness to the shared lifecycle boundary."""

        self._session.set_prerequisite_projection(projection)

    def build_plan(self, intent: SidebarInputSnapshot) -> RunPlan:
        if not isinstance(intent, SidebarInputSnapshot):
            raise ValueError("intent must be SidebarInputSnapshot")
        discovery = self._discovery or self.discover()
        request = self._request_resolver.resolve_plan_request(
            _redacted_intent(intent),
            discovery,
        )
        if type(request) is not ApplicationPlanRequest:
            raise TypeError(
                "resolve_plan_request must return ApplicationPlanRequest"
            )
        result = self._session.build_plan(request)
        if type(result) is not RunPlan:
            raise RuntimeError("shared planning returned invalid RunPlan authority")
        self._plan_request = request
        self._accepted_snapshot = None
        self._execution_request = None
        self._selected_terminal = None
        self._transient_credential = intent.credential
        self._transient_runner_controls = _redacted_additional_controls(
            intent.additional_controls
        )
        return result

    def accept_plan(self) -> AcceptedRunSnapshot:
        if self._plan_request is None:
            raise RuntimeError("no shared run plan is prepared for acceptance")
        result = self._session.accept_plan()
        if type(result) is not AcceptedRunSnapshot:
            raise RuntimeError(
                "shared acceptance returned invalid AcceptedRunSnapshot authority"
            )
        self._accepted_snapshot = result
        return result

    def cancel_benchmark(self):
        if self._plan_request and self._plan_request.extensions.get("arcgrav.runtime:execution-only") is True:
            self._cancellation.set()

    def start_benchmark(
        self,
        *,
        on_execution_started: (
            Callable[[ApplicationExecutionRequest, RunPlan], None] | None
        ) = None,
        on_live_view=None,
        on_activity=None,
        live_view_control=None,
        before_execution: Callable[[], None] | None = None,
    ) -> AcceptedRun | BlockedRun:
        request = self._plan_request
        snapshot = self._accepted_snapshot
        if request is None or snapshot is None:
            raise RuntimeError("accepted shared authority is required before execution")
        if on_execution_started is not None and not callable(on_execution_started):
            raise ValueError("on_execution_started must be callable or None")
        if before_execution is not None:
            before_execution()
        self._cancellation.clear()
        try:
            execution = self._request_resolver.resolve_execution_request(
                request,
                snapshot,
                credential=self._transient_credential,
                runner_transient_controls=self._transient_runner_controls,
            )
            if type(execution) is not ApplicationExecutionRequest:
                raise TypeError(
                    "resolve_execution_request must return "
                    "ApplicationExecutionRequest"
                )
            if before_execution is not None:
                before_execution()
            execution = replace(execution, live_view_callback=on_live_view, activity_callback=on_activity,
                                live_view_control=live_view_control,
                                report_request_factory=self._request_resolver.resolve_report_request)
            retained_execution = replace(
                execution,
                live_view_callback=None,
                activity_callback=None,
                live_view_control=None,
                transient_values=None,
                runner_transient_values=None,
                runner_launch_selection=None,
            )
            execution = replace(execution, cancellation_requested=self._cancellation.is_set)
            accepted_plan = snapshot.plan()
            self._execution_request = retained_execution
            previous_store = self._artifact_stores.get(retained_execution.generation_id)
            previous_context = self._run_contexts.get(retained_execution.generation_id)
            self._artifact_stores[retained_execution.generation_id] = retained_execution.artifact_store
            self._run_contexts[retained_execution.generation_id] = (
                _RunPresentationContext(
                    generation_id=retained_execution.generation_id,
                    plan=accepted_plan,
                    plan_request=request,
                    accepted_at=snapshot.accepted_at,
                )
            )
            if on_execution_started is not None:
                try:
                    on_execution_started(retained_execution, accepted_plan)
                except Exception:
                    # Presentation notification cannot gate shared execution.
                    pass
            try:
                if before_execution is not None:
                    before_execution()
                result = self._session.execute_accepted_run(execution)
            except DiagnosticConsentRequired:
                self._execution_request = None
                if previous_store is None:
                    self._artifact_stores.pop(retained_execution.generation_id, None)
                else:
                    self._artifact_stores[retained_execution.generation_id] = previous_store
                if previous_context is None:
                    self._run_contexts.pop(retained_execution.generation_id, None)
                else:
                    self._run_contexts[retained_execution.generation_id] = previous_context
                raise
            except BaseException:
                self._execution_request = None
                self._run_contexts.pop(retained_execution.generation_id, None)
                raise
        finally:
            self._transient_credential = ""
            self._transient_runner_controls = ()
        if type(result) not in (AcceptedRun, BlockedRun, ExecutedRun):
            raise RuntimeError(
                "shared accepted execution returned invalid terminal authority"
            )
        diagnostic = self._session.validation_diagnostic(result.generation_id)
        if diagnostic:
            self.history_diagnostics.append("Replay validation unavailable: " + diagnostic)
        self._terminal_runs[result.generation_id] = result
        bundle = self._session.completed_report(result.generation_id)
        if bundle is not None:
            self._report_bundles[result.generation_id] = bundle
        completion = self._session.completion_record(result.generation_id) or {}
        self._report_states[result.generation_id] = (completion.get("status", "unavailable"), completion.get("validation", {}).get("diagnostic"))
        self._selected_terminal = result
        return result

    def test_runner(self, intent: SidebarInputSnapshot, *, before_execution=None) -> RunnerTestResult:
        """Run one non-authoritative live runner functionality diagnostic."""

        if not isinstance(intent, SidebarInputSnapshot):
            raise ValueError("intent must be SidebarInputSnapshot")
        selected_runner = intent.runner
        try:
            if before_execution is not None:
                before_execution()
            discovery = self._discovery or self.discover()
            resolver = getattr(
                self._request_resolver,
                "resolve_runner_test_request",
                None,
            )
            if not callable(resolver):
                raise RuntimeError(
                    "request resolver does not support runner diagnostics"
                )
            resolved = resolver(intent, discovery)
            if type(resolved) is not ResolvedRunnerTestRequest:
                raise TypeError(
                    "resolve_runner_test_request must return "
                    "ResolvedRunnerTestRequest"
                )
            if before_execution is not None:
                before_execution()
            factory = _runner_test_factory(resolved.runner_registration)
            runner = factory(launch_selection=resolved.runner_launch_selection) if resolved.runner_launch_selection else factory()
            try:
                execute = getattr(runner, "execute", None)
                if not callable(execute):
                    raise RuntimeError("runner does not expose execute()")
                if before_execution is not None:
                    before_execution()
                raw_observation = execute(_runner_test_request(resolved))
            finally:
                close = getattr(runner, "close", None)
                if callable(close):
                    close()
            if not isinstance(raw_observation, Mapping):
                raise RuntimeError("runner returned a non-object observation")
            return _runner_test_result_from_observation(
                selected_runner=_text(
                    selected_runner or "runner",
                    name="selected_runner",
                ),
                resolved=resolved,
                observation=raw_observation,
            )
        except DiagnosticConsentRequired:
            raise
        except Exception as exc:
            return _runner_test_failure(
                selected_runner=selected_runner,
                error=exc,
            )

    def import_run_archive(self, source_path):
        """Import validated bytes for read-only history without minting run authority."""
        if self._repository_root is None:
            raise RuntimeError("repository root required for archive import")
        from AgMark.shared.validation.run_archive import import_run_archive
        destination = import_run_archive(source_path, self._repository_root)
        from .history import discover_history
        self._history = discover_history(self._repository_root)
        return destination

    @property
    def historical_runs(self):
        return tuple(run for key, run in self._history.items() if key not in self._terminal_runs)

    def record_history_state(self, generation_id, state_label, state_tone):
        run = self._history.get(generation_id)
        if run is not None:
            self._history[generation_id] = replace(run, state_label=state_label, state_tone=state_tone)

    def prepare_history_presentation(self, generation_id, current, workspace):
        """Persist pure projections in a worker; return diagnostics without UI mutation."""
        from .history import save_presentation
        if not self._history_enabled:
            return None
        store = self.artifact_store(generation_id)
        if store is None or current is None:
            return None
        try:
            save_presentation(store.root, generation_id, current, workspace)
            return ()
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            import logging
            message = "Run history could not be saved; sealed archive unavailable or invalid."
            logging.getLogger(__name__).warning(message)
            return (message,)

    def apply_history_diagnostics(self, diagnostics):
        if diagnostics is not None:
            self.history_diagnostics[:] = diagnostics

    def save_history_presentation(self, generation_id, current, workspace):
        self.apply_history_diagnostics(self.prepare_history_presentation(generation_id, current, workspace))

    def select_run(self, run_id: str) -> AcceptedRun | BlockedRun:
        _text(run_id, name="run_id")
        if run_id in self._history and run_id not in self._terminal_runs:
            self._selected_terminal = None
            self._selected_history_id = run_id
            return self._history[run_id]
        self._selected_history_id = None
        result = self._session.select_run(run_id)
        if type(result) not in (AcceptedRun, BlockedRun, ExecutedRun):
            raise RuntimeError("shared run selection returned invalid terminal authority")
        self._terminal_runs[result.generation_id] = result
        bundle = self._session.completed_report(result.generation_id)
        if bundle is not None:
            self._report_bundles[result.generation_id] = bundle
        completion = self._session.completion_record(result.generation_id) or {}
        self._report_states[result.generation_id] = (completion.get("status", "unavailable"), completion.get("validation", {}).get("diagnostic"))
        self._selected_terminal = result
        return result

    def delete_run(self, run_id: str) -> ApplicationRunDeletion:
        run_id = _text(run_id, name="run_id")
        historical = self._history.get(run_id) if run_id not in self._terminal_runs else None
        if historical is not None:
            if self._selected_history_id != run_id:
                raise ValueError("delete_run must target the selected saved run")
            if self._execution_request is not None and self._execution_request.generation_id == run_id:
                raise ValueError("Cannot delete an active execution generation")
            historical.delete()
            result = ApplicationRunDeletion(generation_id=run_id)
        else:
            result = self._session.delete_run(run_id)
        if type(result) is not ApplicationRunDeletion:
            raise RuntimeError(
                "shared run deletion returned invalid ApplicationRunDeletion authority"
            )

        self._history.pop(run_id, None)
        if self._selected_history_id == run_id:
            self._selected_history_id = None
        self._report_bundles.pop(run_id, None)
        self._report_states.pop(run_id, None)
        self._export_feedback = {key: value for key, value in self._export_feedback.items() if key[0] != run_id}
        self._terminal_runs.pop(run_id, None)
        self._run_contexts.pop(run_id, None)
        self._artifact_stores.pop(run_id, None)
        if (
            self._selected_terminal is not None
            and self._selected_terminal.generation_id == run_id
        ):
            self._selected_terminal = None
        if (
            self._execution_request is not None
            and self._execution_request.generation_id == run_id
        ):
            self._execution_request = None
        return result

    def completion_diagnostics(self, generation_id):
        from AgMark.gui.completion_diagnostics import completion_diagnostic_lines
        completion = getattr(self._session, "completion_record", lambda _: None)(generation_id) or {}
        return completion_diagnostic_lines(completion.get("diagnostics", ()))

    def report_state(self, generation_id):
        return self._report_states.get(generation_id, (None, None))

    def set_report_state(self, generation_id, state, reason=None):
        if generation_id not in self._terminal_runs:
            return
        self._report_states[generation_id] = (state, reason)

    def export_feedback(self, generation_id, report_id):
        return self._export_feedback.get((generation_id, report_id), "")

    def export_report(self, generation_id, report_id, destination):
        """Export exact generated readable bytes under captured report identity."""
        import os
        import tempfile
        from AgMark.shared.runtime.artifacts import sha256_bytes
        bundle = self._report_bundles.get(generation_id)
        if bundle is None or bundle.report_document.get("report_id") != report_id or bundle.report_document.get("accepted_generation_id") != generation_id:
            raise ValueError("export report identity is no longer retained")
        matches = [ref for ref in bundle.report_manifest["components"] if ref["artifact_id"] == bundle.human.artifact_id]
        if len(matches) != 1 or matches[0]["sha256"] != sha256_bytes(bundle.human.data):
            raise ValueError("readable report integrity mismatch")
        if destination is None:
            self._export_feedback[(generation_id, report_id)] = "Export cancelled."
            return None
        data = bundle.human.data
        store = self.artifact_store(generation_id)
        if store is not None and store.destination.ownership == "central":
            from AgMark.shared.runtime.artifacts.archive import archive_path
            from AgMark.shared.validation.run_archive import read_retained_report
            retained = read_retained_report(archive_path(store.root, generation_id))
            if retained is None or retained.report_id != report_id or retained.markdown_bytes != data:
                raise ValueError("Sealed report differs from retained completion")
            data = retained.markdown_bytes
        target = Path(destination)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".agmark-report-", delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except Exception as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            self._export_feedback[(generation_id, report_id)] = f"Export failed: {exc}"
            raise
        self._export_feedback[(generation_id, report_id)] = f"Saved report to {target}"
        return target



def _validate_boundary(boundary: object) -> None:
    for name in (
        "discover",
        "build_plan",
        "select_run",
        "delete_run",
        "accept_plan",
        "start_benchmark",
    ):
        if not callable(getattr(boundary, name, None)):
            raise ValueError(
                "shared_application_boundary must expose callable "
                f"{name}()"
            )
