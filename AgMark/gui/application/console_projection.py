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

from .contracts import ConsoleProjectionUpdate
from .projector import (
    _decode_extension_text, _decode_retained_json_documents, _named_byte_counts,
    _runner_label, _treatment_label,
)

def _score_diagnostic_summary(
    scores: Sequence[Mapping[str, object]],
) -> str:
    availability_counts: dict[str, int] = {}
    diagnostic_counts: dict[str, int] = {}
    for score in scores:
        availability = score.get("availability")
        if isinstance(availability, str) and availability.strip():
            key = availability.strip()
            availability_counts[key] = availability_counts.get(key, 0) + 1
        diagnostics = score.get("diagnostics", ())
        if isinstance(diagnostics, (str, bytes, bytearray)) or not isinstance(
            diagnostics,
            Sequence,
        ):
            continue
        for diagnostic in diagnostics:
            if isinstance(diagnostic, str) and diagnostic.strip():
                key = diagnostic.strip()
                diagnostic_counts[key] = diagnostic_counts.get(key, 0) + 1
    parts = [
        f"{name}={count}"
        for name, count in sorted(availability_counts.items())
    ]
    parts.extend(
        f"{name} x{count}"
        for name, count in sorted(diagnostic_counts.items())
    )
    return "; ".join(parts) if parts else "none"

def _accepted_run_raw_response(
    observations: Sequence[Mapping[str, object]],
) -> tuple[str | None, tuple[str, ...]]:
    sections: list[str] = []
    diagnostics: list[str] = []
    for index, observation in enumerate(observations, start=1):
        text, diagnostic = _decode_extension_text(observation)
        if diagnostic is not None:
            treatment = _treatment_label(observation, index)
            diagnostics.append(f"{treatment}: {diagnostic}")
            continue
        assert text is not None
        sections.append(f"--- {_treatment_label(observation, index)} ---\n{text}")
    return ("\n\n".join(sections) if sections else None), tuple(diagnostics)

def _live_view_treatments(observations):
    return tuple(
        (str(observation.get("observation_id") or f"retained-{index}"), observation["treatment_id"])
        for index, observation in enumerate(observations, start=1)
        if isinstance(observation.get("treatment_id"), str) and observation["treatment_id"]
    )


def _accepted_run_live_view(observations):
    """Read exact invocation evidence; never reconstruct old prompts from files."""
    sections = []
    diagnostics = []
    for index, observation in enumerate(observations, start=1):
        output, diagnostic = _decode_extension_text(observation)
        if diagnostic:
            diagnostics.append(diagnostic)
        input_text = None
        # Current evidence deliberately excludes the framed invocation text.
        # Necessary benchmark/scoring inputs have separate retained authority;
        # do not recover a legacy raw payload from incidental runner metadata.
        invocation_id = observation.get("observation_id") or f"retained-{index}"
        sections.append((str(invocation_id), input_text, output))
    return tuple(sections), tuple(diagnostics)

def _accepted_run_live_output(
    terminal: AcceptedRun,
    observations: Sequence[Mapping[str, object]],
    scores: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    completed = sum(
        1
        for observation in observations
        if observation.get("terminal_status") == "completed"
    )
    response_total, response_parts = _named_byte_counts(
        observations,
        "response_bytes",
    )
    stderr_total, stderr_parts = _named_byte_counts(
        observations,
        "stderr_bytes",
    )
    response_detail = ", ".join(response_parts) if response_parts else "unavailable"
    stderr_detail = ", ".join(stderr_parts) if stderr_parts else "unavailable"
    response_summary = (
        f"{response_total:,} observed total"
        if response_total is not None else "Unavailable"
    )
    stderr_summary = (
        f"{stderr_total:,} observed total"
        if stderr_total is not None else "Unavailable"
    )
    return (
        (
            f"Generation: {terminal.generation_id}\n"
            f"Runner: {_runner_label(observations)}\n"
            f"Treatments completed: {completed}/{len(observations)}\n"
            f"Response bytes: {response_summary} ({response_detail})\n"
            f"Stderr bytes: {stderr_summary} ({stderr_detail}); "
            "retained, not displayed\n"
            f"Score diagnostics: {_score_diagnostic_summary(scores)}\n"
        ),
    )

def _terminal_console_update(
    terminal: AcceptedRun | BlockedRun,
    completion_diagnostics: tuple[str, ...] = (),
) -> ConsoleProjectionUpdate:
    completion_diagnostics = tuple(line + "\n" for line in completion_diagnostics)
    if type(terminal) is BlockedRun:
        return ConsoleProjectionUpdate(
            generation_id=terminal.generation_id,
            bind_generation=True,
            diagnostics=terminal.diagnostics + completion_diagnostics,
        )
    if type(terminal) not in (AcceptedRun, ExecutedRun):
        raise TypeError("terminal must be AcceptedRun or BlockedRun")

    observations, observation_diagnostics = _decode_retained_json_documents(
        getattr(terminal, "treatment_observations", ()),
        label="treatment observation",
    )
    scores, score_diagnostics = _decode_retained_json_documents(
        getattr(terminal, "score_artifacts", ()),
        label="score artifact",
    )
    live_view, raw_diagnostics = _accepted_run_live_view(observations)
    return ConsoleProjectionUpdate(
        generation_id=terminal.generation_id,
        bind_generation=True,
        live_output=_accepted_run_live_output(terminal, observations, scores),
        diagnostics=(
            observation_diagnostics
            + score_diagnostics
            + raw_diagnostics
            + completion_diagnostics
        ),
        live_view=live_view, live_view_treatments=_live_view_treatments(observations),
    )


def historical_console_update(run):
    """Display only exact original observations from a validated .agmark archive."""
    from AgMark.shared.runtime.artifacts.archive import (
        archive_path, read_archive_member, validate_archive,
    )
    if getattr(run, "diagnostic_only", False):
        from AgMark.gui.completion_diagnostics import retained_diagnostic_lines
        return ConsoleProjectionUpdate(run.generation_id, bind_generation=True,
            diagnostics=("Completion diagnostic only; no sealed archive or report is available.\n",)
                + tuple(line + "\n" for line in retained_diagnostic_lines(run.root, run.generation_id, {})))
    observations = []
    diagnostics = ["Opened sealed run evidence without starting a benchmark.\n"]
    try:
        target = archive_path(run.root, run.generation_id)
        manifest = validate_archive(target)
        prefix = run.generation_id + "/"
        paths = sorted(name for name in manifest["core_files"]
                       if name.startswith(prefix) and name.endswith("/observation.json"))
        for reference in paths:
            raw = read_archive_member(target, reference)
            observation = json.loads(raw)
            if (not isinstance(observation, Mapping)
                    or observation.get("accepted_generation_id") != run.generation_id
                    or not isinstance(observation.get("treatment_id"), str)):
                raise ValueError("saved observation has invalid generation or treatment identity")
            observations.append(observation)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        observations = []
        diagnostics.append("Saved Live View evidence is unavailable: " + str(exc))
    from AgMark.shared.validation.run_archive import read_completion_record
    from AgMark.gui.completion_diagnostics import retained_diagnostic_lines
    try:
        completion = read_completion_record(archive_path(run.root, run.generation_id))
        diagnostics.extend(line + "\n" for line in retained_diagnostic_lines(run.root, run.generation_id, completion))
    except (OSError, ValueError, TypeError, KeyError):
        diagnostics.append("Completion diagnostics unavailable.")
    live_view, decode_diagnostics = _accepted_run_live_view(observations)
    return ConsoleProjectionUpdate(run.generation_id, bind_generation=True,
        live_view=live_view, live_view_treatments=_live_view_treatments(observations), diagnostics=tuple(diagnostics) + decode_diagnostics)
