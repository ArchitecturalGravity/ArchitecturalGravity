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
from threading import Condition, Thread
from collections import OrderedDict
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

AuthorityOperation = Callable[[], object]
AuthorityDispatcher = Callable[[AuthorityOperation], object]
FailureGenerationProvider = Callable[[], str | None]
FailureHandler = Callable[[str, BaseException], None]

def _dispatch_in_background(operation: AuthorityOperation) -> Thread:
    worker = Thread(
        target=operation,
        name="agmark-gui-authority",
        daemon=True,
    )
    worker.start()
    return worker


class _ProjectionWorker:
    """One worker, with at most one pending replacement per presentation key.

    Callers own immutable snapshots and stale-result checks. A newer refresh
    replaces queued work; it never interrupts evidence validation in flight.
    Closing drops pending presentation only, not shared execution authority.
    """

    def __init__(self):
        self._condition = Condition()
        self._pending = OrderedDict()
        self._closed = False
        self._thread = None

    def submit(self, key, operation, *, priority=False):
        with self._condition:
            if self._closed:
                return
            self._pending[key] = operation
            if priority:
                self._pending.pop("active", None)
                self._pending.move_to_end(key, last=False)
            if self._thread is None:
                self._thread = Thread(target=self._run, name="agmark-gui-projection", daemon=True)
                self._thread.start()
            self._condition.notify()
            return self._thread

    def close(self):
        with self._condition:
            self._closed = True
            self._pending.clear()
            self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                while not self._pending and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                _, operation = self._pending.popitem(last=False)
            operation()

if PYSIDE6_AVAILABLE:
    class _GuiResultDispatcher(QObject):
        """Marshal shared-operation state back onto the Qt GUI thread."""

        execution_started = Signal(object, object)
        activity_ready = Signal(object)
        result_ready = Signal(str, object)
        failure_ready = Signal(str, object, object)
        operation_ready = Signal(str, object, int, int)
        operation_failed = Signal(str, object, object, int)
        prepared_ready = Signal(str, object, object, int, int, object)
        active_projection_ready = Signal(str, int, object, object)
        activity_pending = Signal()
        sidebar_ready = Signal(int, object, object, object)
else:
    _GuiResultDispatcher = None
