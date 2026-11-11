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
from AgMark.shared.adapters.execution import validate_retained_parity_observation
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

# Fixed guidance only: startup exception messages can contain sensitive paths,
# configuration values or credentials and must not become console diagnostics.
_CAPTURE_SETUP_HINTS = {
    "codex_cli_telemetry_configuration_invalid":
        "Capture configuration was rejected before submission; verify the selected Capture Mode and runner setup.",
    "codex_cli_telemetry_initialization_failed":
        "Original-run capture could not initialize before submission; check the selected runtime setup.",
    "codex_cli_telemetry_collector_unavailable":
        "The local telemetry receiver could not start; check loopback access on the selected execution host.",
    "codex_cli_telemetry_diagnostics_unavailable":
        "Private diagnostic storage could not be created; check temporary-directory write permissions on the selected execution host.",
    "codex_cli_telemetry_selected_host_unavailable":
        "The telemetry helper did not become ready in the selected WSL distribution; check that distribution, Python 3 and temporary-directory access.",
    "codex_cli_telemetry_launch_configuration_failed":
        "Capture launch configuration failed before submission; check the selected executable and launch mode.",
}

from .contracts import RunnerTestResult
from .projector import _bounded_text, _decode_extension_text

def _runner_test_factory(registration: Mapping[str, object]):
    extensions = registration.get("extensions")
    if not isinstance(extensions, Mapping):
        raise RuntimeError("runner registration extensions are unavailable")
    entry_point = extensions.get(_RUNNER_ENTRY_POINT)
    if not isinstance(entry_point, str) or ":" not in entry_point:
        raise RuntimeError("runner registration does not declare an entry point")
    module_name, separator, attribute = entry_point.partition(":")
    if separator != ":" or not module_name or not attribute or "." in attribute:
        raise RuntimeError("runner entry point is invalid")
    module = import_module(module_name)
    factory = getattr(module, attribute)
    if not callable(factory):
        raise RuntimeError("runner entry point is not callable")
    return factory

def _runner_test_request(
    resolved: ResolvedRunnerTestRequest,
) -> dict[str, object]:
    boundary = resolved.execution_boundary
    prompt_sha = sha256_bytes(_RUNNER_TEST_PROMPT)
    input_sha = sha256_bytes(_RUNNER_TEST_INPUT)
    request_identity = {
        "accepted_generation_id": _RUNNER_TEST_GENERATION_ID,
        "request_id": "gui-runner-test:echo-test",
        "observation_id": "gui-runner-test:echo-test",
        "case_id": "echo-test",
        "treatment_id": "runner-functionality-test",
        "repetition": 1,
        "execution_boundary_fingerprint": boundary.fingerprint,
        "prompt_sha256": prompt_sha,
        "input_sha256": input_sha,
    }
    request: dict[str, object] = {
        "accepted_generation_id": _RUNNER_TEST_GENERATION_ID,
        "request_id": "gui-runner-test:echo-test",
        "observation_id": "gui-runner-test:echo-test",
        "benchmark_id": "gui-runner-test",
        "case_id": "echo-test",
        "treatment_id": "runner-functionality-test",
        "repetition": 1,
        "execution_boundary_fingerprint": boundary.fingerprint,
        "execution_boundary": boundary.to_dict(),
        "conversation_policy": {
            "new_conversation": True,
            "reuse_prior_observation_context": False,
        },
        "prompt": {"content": _RUNNER_TEST_PROMPT, "sha256": prompt_sha},
        "input": {"content": _RUNNER_TEST_INPUT, "sha256": input_sha},
        "request_identity": {
            "prompt_sha256": prompt_sha,
            "input_sha256": input_sha,
            "request_sha256": sha256_bytes(canonical_json_bytes(request_identity)),
        },
    }
    if resolved.runner_transient_values is not None:
        request["transient_invocation"] = dict(resolved.runner_transient_values)
    return request

def _runner_test_response_preview(observation: Mapping[str, object]) -> str:
    text, diagnostic = _decode_extension_text(observation)
    if diagnostic is not None or text is None:
        return ""
    return _bounded_text(text)

def _runner_test_diagnostics(observation: Mapping[str, object]) -> tuple[str, ...]:
    diagnostics: list[str] = []
    raw_diagnostics = observation.get("diagnostics", ())
    if (
        isinstance(raw_diagnostics, Sequence)
        and not isinstance(raw_diagnostics, (str, bytes, bytearray))
    ):
        diagnostics.extend(
            _bounded_text(value, limit=500)
            for value in raw_diagnostics
            if isinstance(value, str) and value
        )
    attempts = observation.get("attempts")
    if isinstance(attempts, Sequence) and not isinstance(
        attempts, (str, bytes, bytearray)
    ):
        for attempt in attempts:
            if not isinstance(attempt, Mapping):
                continue
            error_code = attempt.get("error_code")
            if isinstance(error_code, str) and error_code:
                diagnostics.append(_bounded_text(error_code, limit=500))
                hint = _CAPTURE_SETUP_HINTS.get(error_code)
                if hint is not None:
                    diagnostics.append(hint)
    return tuple(dict.fromkeys(diagnostics))

def _runner_test_result_from_observation(
    *,
    selected_runner: str,
    resolved: ResolvedRunnerTestRequest,
    observation: Mapping[str, object],
) -> RunnerTestResult:
    validate_retained_parity_observation(observation)
    boundary = resolved.execution_boundary.to_dict()
    runner = boundary.get("runner")
    runtime = boundary.get("provider_runtime")
    observed_runner = observation.get("runner")
    if (
        not isinstance(runner, Mapping)
        or not isinstance(observed_runner, Mapping)
        or observed_runner.get("id") != runner.get("id")
        or observed_runner.get("version") != runner.get("version")
    ):
        raise ValueError("runner test observation does not match resolved runner identity")
    extensions = observation.get("extensions")
    execution = (
        extensions.get("arcgrav.runner:execution")
        if isinstance(extensions, Mapping)
        else None
    )
    submission = execution.get("submission") if isinstance(execution, Mapping) else None
    response = observation.get("response")
    return RunnerTestResult(
        selected_runner=selected_runner,
        runner_id=(
            runner.get("id")
            if isinstance(runner, Mapping) and isinstance(runner.get("id"), str)
            else ""
        ),
        runner_version=(
            runner.get("version")
            if isinstance(runner, Mapping)
            and isinstance(runner.get("version"), str)
            else ""
        ),
        model=(
            runtime.get("model")
            if isinstance(runtime, Mapping) and isinstance(runtime.get("model"), str)
            else ""
        ),
        submitted=(
            submission.get("occurred") is True
            if isinstance(submission, Mapping)
            else isinstance(response, Mapping)
            and response.get("availability") == "retained"
        ),
        terminal_status=(
            observation.get("terminal_status")
            if isinstance(observation.get("terminal_status"), str)
            else None
        ),
        response_preview=_runner_test_response_preview(observation),
        diagnostics=_runner_test_diagnostics(observation),
    )

def _runner_test_failure(
    *,
    selected_runner: str | None,
    error: BaseException,
) -> RunnerTestResult:
    label = selected_runner if isinstance(selected_runner, str) and selected_runner else "runner"
    if isinstance(error, PermissionError):
        reason = "Runner test preparation was denied; check permissions on the selected execution host."
    elif isinstance(error, FileNotFoundError):
        reason = "Runner test preparation could not find a required executable or resource; check the selected runner setup."
    elif isinstance(error, TimeoutError):
        reason = "Runner test preparation timed out; check the selected execution host is available."
    elif isinstance(error, (ValueError, TypeError)):
        reason = "Runner test configuration was rejected; verify the selected runner and resolved controls."
    else:
        reason = "Runner test preparation failed before a valid result was available; check the selected runner setup."
    return RunnerTestResult(
        selected_runner=label,
        diagnostics=(reason,),
    )

def _runner_test_environment_entry(
    result: RunnerTestResult,
) -> EnvironmentDiagnosticEntry:
    details = [
        f"Submitted: {'yes' if result.submitted else 'no'}",
        f"Terminal status: {result.terminal_status or 'unavailable'}",
    ]
    if result.model:
        details.append(f"Model: {result.model}")
    if result.response_preview:
        details.append(f"Response: {result.response_preview}")
    if result.diagnostics:
        details.append("Diagnostics: " + "; ".join(result.diagnostics))
    return EnvironmentDiagnosticEntry(
        source="Runner Test",
        state="ready" if result.passed else "failure",
        summary=(
            "Echo: test completed with a retained response."
            if result.passed
            else "Echo: test did not complete successfully."
        ),
        details="\n".join(details),
        blocking=False,
    )
