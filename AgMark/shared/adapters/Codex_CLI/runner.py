"""OpenAI Codex CLI runner adapter.

The adapter intentionally treats Codex CLI as the owner of authentication and
account configuration. AgMark owns the selected launch environment,
executable, explicit model, request framing, execution policy, and retained
evidence. WSL execution creates its observation working directory inside WSL
and reuses the selected WSL user's normal logged-in Codex session.
"""

from __future__ import annotations

from ...evaluation.telemetry import ATTEMPT_MEASUREMENTS
from .events import IncrementalResponseDecoder, extract_response
from .session import SESSION_RECORD, extract_session_measurements, returned_thread_id
from . import session_capture


from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
import base64
import copy
import json
from datetime import datetime, timezone
import os
from pathlib import Path, PureWindowsPath
from queue import Empty, Queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Iterator, Mapping

from ...runtime.identity.runtime_version import retained_runtime_version
from ...telemetry.profile import DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
from .._contract import (
    UnsupportedBoundaryError,
    sha256_bytes,
    terminal_observation,
    validate_boundary_support,
    validate_runner_request,
)
from ..execution import (
    ExecutionFailureKind,
    ExecutionIsolation,
    InvocationCapture,
    InvocationCancelled,
    InvocationContext,
    TargetCompositionDescriptor,
    TerminalExecutionResult,
    emit_terminal_observation,
    execute_target,
    temporary_workdir_isolation,
)

RUNNER_ID = "openai.codex-cli"
RUNNER_VERSION = "2.0.0"
_NAMESPACE = "openai.codex_cli"
_TARGET_COMPOSITION_EXTENSION = "arcgrav.adapters:target_composition"
_PRODUCTION_ENTRY_POINT = "AgMark.shared.adapters.Codex_CLI:CodexCliRunner"
# Per-invocation presentation state is neither a request field nor persistent
# runner configuration. Keep the established capture seam usable by transports
# and conformance instrumentation without adding kwargs to their run contract.
_LIVE_CAPTURE: ContextVar[dict[str, Any] | None] = ContextVar("codex_live_capture", default=None)
_PIPE_CALLBACKS: ContextVar[dict[str, Any] | None] = ContextVar("codex_pipe_callbacks", default=None)
_SESSION_CANCELLATION: ContextVar[Callable[[], bool] | None] = ContextVar("codex_session_cancellation", default=None)

_SUPPORTED_CONTROLS: dict[str, frozenset[Any] | None] = {
    "launch_mode": frozenset({"native", "wsl"}),
    "codex_binary": None,
    "wsl_distribution": None,
    "model_id": None,
    "reasoning_effort": None,
    "approval_mode": frozenset({"full_auto"}),
    "request_timeout_ms": None,
    "maximum_attempts": frozenset({1}),
    "capture_mode": frozenset({"session", "telemetry", "deep_telemetry"}),
    # Retain the historical literal only for non-diagnostic boundaries. Current
    # sensitive capture requires the exact versioned acknowledgement below.
    "diagnostic_privacy_acknowledged": frozenset({"not_acknowledged", "acknowledged", DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT}),
}
_REQUIRED_CONTROLS = frozenset(
    {
        "launch_mode",
        "codex_binary",
        "model_id",
        "approval_mode",
        "request_timeout_ms",
        "maximum_attempts",
    }
)
# New plans require and resolve reasoning_effort through registration and the
# planning probe. Older accepted boundaries without that control retain their
# original CLI behavior; they must not acquire a new implicit override.
_FIXED_CONTROLS = {
    "memory_policy": "disabled",
    "request_framing": "codex_cli",
    "sampling_mode": "provider_default",
    "tool_policy": "workspace_write",
}
_VERSION_RE = re.compile(
    r"(?<![0-9A-Za-z.+-])([0-9]+\.[0-9]+\.[0-9]+"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
    r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?)(?![0-9A-Za-z.+-])"
)
_AUTH_MARKERS = (
    b"401",
    b"api key",
    b"authentication",
    b"login",
    b"not logged in",
    b"unauthorized",
)

# Authentication is intentionally not projected into this process. Native
# execution keeps the user's home/session context; WSL gets its Linux HOME from
# the selected distribution. Only host values needed to launch the process are
# copied explicitly.
_ALLOWED_PARENT_ENV = (
    "APPDATA",
    "COMSPEC",
    "CODEX_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SystemRoot",
    "TZ",
    "USERPROFILE",
    "WINDIR",
)

_WSL_EXEC_SCRIPT = r"""
set -eu
linux_home="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6)"
if [ -n "${linux_home:-}" ]; then
    export HOME="$linux_home"
fi
workdir="$(mktemp -d /tmp/arcgrav-codex-work-XXXXXX)"
trap 'rm -rf "$workdir"' EXIT HUP INT TERM
cd "$workdir"
codex_binary="$1"
model_id="$2"
shift 2
# Repository-bundled scripts are resolved on the host and mounted by WSL.
# Run them through the selected distribution's Python, not as installed Codex.
python_script=""
case "$codex_binary" in
    [A-Za-z]:*)
        python_script="$(wslpath -u "$codex_binary")"
        codex_binary="python3"
        ;;
esac
set -- "$codex_binary" ${python_script:+"$python_script"} exec \
    --model "$model_id" \
    --approve-for-me \
    --ignore-user-config \
    --skip-git-repo-check \
    --color never \
    --json \
    "$@" \
    -
"$@"
""".strip()


def _wsl_cli_argv(
    launcher: str, distribution: str, executable: str, args: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve command names in the same login-shell PATH as WSL execution."""

    prefix = (launcher, "--distribution", distribution, "--exec")
    if PureWindowsPath(executable).is_absolute():
        # The registered mock script is in the Windows checkout: translate the
        # host path within the selected distribution; no WSL installation needed.
        return (
            *prefix, "sh", "-lc",
            'script="$(wslpath -u "$1")"; shift; exec python3 "$script" "$@"',
            "arcgrav-codex", executable, *args,
        )
    if "/" in executable:
        return (*prefix, executable, *args)
    return (*prefix, "sh", "-lc", 'exec "$@"', "arcgrav-codex", executable, *args)


@contextmanager
def _target_managed_isolation(
    *,
    cwd: Path,
    environment: Mapping[str, str],
    session_home_reused: bool | None,
) -> Iterator[InvocationContext]:
    """Expose isolation established inside the external target launch wrapper."""

    yield InvocationContext(
        cwd=cwd,
        environment=environment,
        isolation=ExecutionIsolation(
            fresh_process=True,
            fresh_workdir=True,
            prior_observation_context_reused=False,
            session_home_reused=session_home_reused,
        ),
    )


def load_registration() -> dict[str, Any]:
    with Path(__file__).with_name("registration.json").open("r", encoding="utf-8") as handle:
        import json
        return json.load(handle)


def _registered_wsl_target_executable(
    registration: Mapping[str, Any], selected: str
) -> str | None:
    """Resolve only declared repository artifacts into absolute host paths.

    WSL receives these paths via wslpath, so the bundled mock target needs no
    independently installed copy in /usr/local/bin. Other selected WSL binaries
    remain unchanged and are resolved inside their distribution.
    """

    artifacts = registration.get("implementation_artifacts", ())
    if not isinstance(artifacts, (list, tuple)):
        return selected
    if not any(
        isinstance(artifact, Mapping)
        and artifact.get("reference") == selected
        for artifact in artifacts
    ):
        return selected
    root = Path(__file__).resolve().parents[4]
    try:
        target = (root / selected).resolve(strict=True)
        target.relative_to(root)
    except (OSError, ValueError):
        return None
    return str(target) if target.is_file() else None


def _registered_executable_resolver(registration: Mapping[str, Any]):
    """Resolve registered repository artifacts independently of process cwd."""
    artifacts = registration.get("implementation_artifacts", ())
    if not isinstance(artifacts, (list, tuple)):
        artifacts = ()
    references = {
        artifact["reference"]
        for artifact in artifacts
        if isinstance(artifact, Mapping) and isinstance(artifact.get("reference"), str)
    }
    repository_root = Path(__file__).resolve().parents[4]

    def resolve(selected: str) -> str | None:
        if selected in references and not Path(selected).is_absolute():
            return shutil.which(str(repository_root / selected))
        return shutil.which(selected)

    return resolve


def _validated_registration(registration: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(registration, Mapping):
        raise TypeError("runner registration must be a mapping")
    value = copy.deepcopy(dict(registration))
    if value.get("registration_kind") != "runner" or value.get("status") != "active":
        raise ValueError("runner registration must be active")
    for name in ("registration_id", "registration_version"):
        field = value.get(name)
        if not isinstance(field, str) or not field:
            raise ValueError(f"{name} must be non-empty text")
    extensions = value.get("extensions")
    if not isinstance(extensions, Mapping):
        raise ValueError("registration extensions must be present")
    if extensions.get("arcgrav.adapters:entry_point") != _PRODUCTION_ENTRY_POINT:
        raise ValueError("registration must select the production Codex runner")
    if not isinstance(extensions.get(_TARGET_COMPOSITION_EXTENSION), Mapping):
        raise ValueError("target composition registration is required")
    return value


def _registered_runtime_provider(registration: Mapping[str, Any]) -> str:
    extensions = registration.get("extensions")
    composition = (
        extensions.get(_TARGET_COMPOSITION_EXTENSION)
        if isinstance(extensions, Mapping)
        else None
    )
    provider = composition.get("runtime_provider") if isinstance(composition, Mapping) else None
    if not isinstance(provider, str) or not provider:
        raise ValueError("target composition runtime_provider must be non-empty text")
    return provider


def _registered_authentication_source(
    registration: Mapping[str, Any],
) -> str | None:
    extensions = registration.get("extensions")
    composition = (
        extensions.get(_TARGET_COMPOSITION_EXTENSION)
        if isinstance(extensions, Mapping)
        else None
    )
    source = (
        composition.get("authentication_source")
        if isinstance(composition, Mapping)
        else None
    )
    if source is not None and (not isinstance(source, str) or not source):
        raise ValueError("target composition authentication_source is invalid")
    return source


def resolve_target_composition(
    registration: Mapping[str, Any],
    *,
    execution_boundary: Mapping[str, Any],
    launch_environment: Mapping[str, str],
) -> TargetCompositionDescriptor:
    """Resolve immutable target authority before Codex preflight or submission."""

    registration = _validated_registration(registration)
    extensions = registration.get("extensions")
    if not isinstance(extensions, Mapping):
        raise ValueError("registration extensions must be present")

    composition = extensions.get(_TARGET_COMPOSITION_EXTENSION)
    if not isinstance(composition, Mapping):
        raise ValueError("target composition registration is required")

    runtime = execution_boundary.get("provider_runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("provider_runtime must be present")
    runtime_id = runtime.get("runtime_id")
    if runtime_id != registration.get("registration_id"):
        raise ValueError("runtime_id must match registration_id")
    runtime_version = runtime.get("runtime_version")
    if runtime_version is not None and (
        not isinstance(runtime_version, str) or not runtime_version.strip()
    ):
        raise ValueError("runtime_version must be exact non-empty text or null")
    access_method = runtime.get("access_method")
    if not isinstance(access_method, str) or not access_method:
        raise ValueError("access_method must be non-empty text")

    access_methods = extensions.get("arcgrav.adapters:access_methods")
    if not isinstance(access_methods, list):
        raise ValueError("registered access methods must be present")
    matching_access_methods = [
        item
        for item in access_methods
        if isinstance(item, Mapping) and item.get("type") == access_method
    ]
    if len(matching_access_methods) != 1:
        raise ValueError("accepted access method must resolve exactly once")
    authentication_class = matching_access_methods[0].get("authentication_class")

    mode = launch_environment.get("mode")
    executable = launch_environment.get("executable")
    selector: dict[str, str] = {}
    if mode == "wsl":
        distribution = launch_environment.get("distribution")
        if not isinstance(distribution, str) or not distribution:
            raise ValueError("WSL target composition requires a distribution")
        selector["wsl_distribution"] = distribution
    elif mode != "native":
        raise ValueError("launch mode must be native or wsl")

    raw_artifacts = registration.get("implementation_artifacts")
    if not isinstance(raw_artifacts, list):
        raise ValueError("implementation artifacts must be present")
    registered_artifact_ids: set[str] = set()
    for artifact in raw_artifacts:
        if not isinstance(artifact, Mapping):
            raise ValueError("implementation artifact entries must be objects")
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id:
            raise ValueError("implementation artifact id must be non-empty text")
        if artifact_id in registered_artifact_ids:
            raise ValueError("implementation artifact ids must be unique")
        registered_artifact_ids.add(artifact_id)

    artifact_ids = composition.get("runner_implementation_artifact_ids")
    if (
        not isinstance(artifact_ids, list)
        or not artifact_ids
        or any(not isinstance(value, str) or not value for value in artifact_ids)
        or len(set(artifact_ids)) != len(artifact_ids)
        or any(value not in registered_artifact_ids for value in artifact_ids)
    ):
        raise ValueError(
            "target composition runner implementation artifact authority is invalid"
        )

    return TargetCompositionDescriptor.create(
        target_class=composition.get("target_class"),
        evidence_class=extensions.get("arcgrav.adapters:evidence_class"),
        runtime_id=runtime_id,
        runtime_version=runtime_version,
        access_method=access_method,
        external_provider_submission=composition.get(
            "external_provider_submission"
        ),
        launch_mode=mode,
        launch_environment_selector=selector,
        executable=executable,
        authentication_class=authentication_class,
        compatibility_profile=composition.get("compatibility_profile"),
        production_runner_entry_point=extensions.get(
            "arcgrav.adapters:entry_point"
        ),
        runner_implementation_artifact_ids=tuple(artifact_ids),
    )


class _SubprocessTransport:
    def read_session(self, thread_id, *, launch_environment, environment):
        if launch_environment["mode"] == "native":
            # A native filesystem call can itself stall. A bounded helper makes
            # the whole discovery/read operation cancellable, like the WSL path.
            argv = (sys.executable, "-I", session_capture.__file__, thread_id,
                    str(session_capture.session_root(environment)))
        else:
            # Use the same selected distribution and login-shell HOME as inference.
            # No Windows path conversion or account-state copying is involved.
            script = ('set -eu\n'
                      'linux_home="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6)"\n'
                      'if [ -n "${linux_home:-}" ]; then export HOME="$linux_home"; fi\n'
                      'exec python3 -c "$1" "$2"')
            argv = (launch_environment["launcher"], "--distribution",
                launch_environment["distribution"], "--exec", "sh", "-lc", script,
                "arcgrav-codex-session", Path(session_capture.__file__).read_text(encoding="utf-8"), thread_id)
        token = _PIPE_CALLBACKS.set({"cancellation_requested": _SESSION_CANCELLATION.get()})
        try:
            if launch_environment["mode"] == "native":
                # This is our local read-only helper, not another invocation of
                # a target-specific/mock CLI transport override.
                result = _SubprocessTransport.run_streaming(self, argv, input_bytes=None,
                    cwd=Path.cwd(), env=environment, timeout_ms=3000,
                    cancellation_requested=_SESSION_CANCELLATION.get())
            else:
                result = self.run(argv, input_bytes=None, cwd=Path.cwd(), env=environment, timeout_ms=3000)
        except InvocationCancelled:
            return {"availability": "unavailable", "thread_id": thread_id,
                    "capture_complete": False, "reason": "session_capture_cancelled"}
        except subprocess.TimeoutExpired:
            return {"availability": "unavailable", "thread_id": thread_id,
                    "capture_complete": False, "reason": "session_capture_timeout"}
        finally:
            _PIPE_CALLBACKS.reset(token)
        if result["returncode"] != 0:
            return {"availability": "unavailable", "thread_id": thread_id, "reason": "session_capture_failed"}
        import json
        return json.loads(result["stdout"])

    def run(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None,
        cwd: Path,
        env: Mapping[str, str],
        timeout_ms: int,
    ) -> dict[str, Any]:
        return self.run_streaming(
            argv, input_bytes=input_bytes, cwd=cwd, env=env,
            timeout_ms=timeout_ms,
            **(_PIPE_CALLBACKS.get() or {}),
        )

    def run_streaming(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None,
        cwd: Path,
        env: Mapping[str, str],
        timeout_ms: int,
        on_stdout: Callable[[bytes], None] | None = None,
        on_stderr: Callable[[bytes], None] | None = None,
        on_input: Callable[[], None] | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Drain binary pipes concurrently, delivering stdout before process exit.

        Threads make this work with Windows/WSL pipes as well as POSIX pipes.
        Only this controlling thread invokes callbacks. Input writing is also
        concurrent, avoiding a large-stdin/large-stderr pipe deadlock.
        """
        started = time.monotonic()
        if cancellation_requested is not None and cancellation_requested():
            raise InvocationCancelled()
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            cwd=str(cwd),
            env=dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=(os.name == "posix"),
        )
        chunks: Queue[tuple[str, bytes | BaseException | None]] = Queue()
        captured = {"stdout": bytearray(), "stderr": bytearray()}
        finished: set[str] = set()
        workers: list[threading.Thread] = []

        def read_pipe(channel: str, pipe: Any) -> None:
            try:
                while True:
                    chunk = pipe.read(65536)
                    if not chunk:
                        break
                    chunks.put((channel, chunk))
            except (OSError, ValueError) as exc:
                chunks.put(("error", exc))
            finally:
                pipe.close()
                chunks.put((channel, None))

        def write_input() -> None:
            try:
                remaining = memoryview(input_bytes)
                while remaining:
                    written = process.stdin.write(remaining)
                    if not written:
                        break
                    remaining = remaining[written:]
            except (BrokenPipeError, OSError, ValueError):
                # A process may exit without consuming stdin, as communicate()
                # permits. Its exit status and exact output remain authoritative.
                pass
            finally:
                process.stdin.close()

        def receive(item: tuple[str, bytes | BaseException | None], *, dispatch=True) -> None:
            channel, chunk = item
            if channel == "error":
                raise chunk
            if chunk is None:
                finished.add(channel)
            else:
                captured[channel].extend(chunk)
                if dispatch and channel == "stdout" and on_stdout is not None:
                    on_stdout(chunk)
                if dispatch and channel == "stderr" and on_stderr is not None:
                    on_stderr(chunk)

        def stop_process() -> None:
            # Stop descendants that inherited the capture pipes too. WSL's host
            # launcher is terminated through the normal Windows process API.
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                process.kill()
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()

        interrupted: str | None = None
        try:
            for channel in ("stdout", "stderr"):
                worker = threading.Thread(
                    target=read_pipe, args=(channel, getattr(process, channel)),
                    daemon=True,
                )
                workers.append(worker)
                worker.start()
            if input_bytes is not None:
                if on_input is not None:
                    on_input()
                writer = threading.Thread(target=write_input, daemon=True)
                workers.append(writer)
                writer.start()
            while len(finished) < 2 or process.poll() is None:
                if cancellation_requested is not None and cancellation_requested():
                    interrupted = "cancelled"
                    break
                remaining = timeout_ms / 1000 - (time.monotonic() - started)
                if remaining <= 0:
                    interrupted = "timed_out"
                    break
                try:
                    receive(chunks.get(timeout=min(0.05, remaining)))
                except Empty:
                    pass
        except KeyboardInterrupt:
            interrupted = "cancelled"
        finally:
            if interrupted is not None or len(finished) < 2 or process.poll() is None:
                stop_process()
            for worker in workers:
                worker.join(timeout=1.0)
            # Preserve all bytes emitted just before interruption without running
            # an unbounded backlog of optional presentation callbacks. Required
            # telemetry reconciles this unobserved suffix from the final bytes.
            while True:
                try:
                    receive(chunks.get_nowait(), dispatch=interrupted is None)
                except Empty:
                    break
        stdout, stderr = bytes(captured["stdout"]), bytes(captured["stderr"])
        if interrupted == "cancelled":
            raise InvocationCancelled(stdout=stdout, stderr=stderr)
        if interrupted == "timed_out":
            raise subprocess.TimeoutExpired(argv, timeout_ms / 1000, output=stdout, stderr=stderr)
        return {
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }


class CodexCliRunner:
    """Execute one non-interactive Codex CLI observation."""

    supports_live_view = True
    supports_live_view_control = True

    def __init__(
        self,
        *,
        transport: object | None = None,
        executable_resolver: Callable[[str], str | None] | None = None,
        timestamp: Callable[[], str] | None = None,
        monotonic: Callable[[], float] | None = None,
        platform_name: str | None = None,
        registration: Mapping[str, Any] | None = None,
        launch_selection: Mapping[str, str] | None = None,
    ) -> None:
        self._registration = _validated_registration(
            load_registration() if registration is None else registration
        )
        self._runner_id = self._registration["registration_id"]
        self._runner_version = self._registration["registration_version"]
        self._transport = transport or _SubprocessTransport()
        self._executable_resolver = executable_resolver or _registered_executable_resolver(self._registration)
        self._timestamp = timestamp or _utc_now
        self._monotonic = monotonic or time.monotonic
        self._platform_name = platform_name or os.name
        self._closed = False
        self._launch_selection = dict(launch_selection or {})
        self._description = self._build_description()

    def _build_description(self) -> dict[str, Any]:
        registration = self._registration
        launch = registration["extensions"]["arcgrav.adapters:launch_environment"]
        mode = "wsl" if self._platform_name == "nt" else "native"
        mode_defaults = launch[mode]
        registered_defaults = {control["name"]: control.get("default") for control in
            registration["extensions"]["arcgrav.adapters:supported_controls"]}
        controls: dict[str, Any] = {
            "launch_mode": {
                "required": True,
                "kind": "choice",
                "values": list(launch["supported_modes"]),
                "default": mode,
            },
            "codex_binary": {
                "required": True,
                "kind": "text",
                "default": mode_defaults["codex_binary_default"],
            },
            "wsl_distribution": {
                "required": True,
                "kind": "text",
                "default": launch["wsl"]["distribution_default"],
            },
            "model_id": {
                "required": True,
                "kind": "choice",
            },
            "model_selection_mode": {
                "required": True,
                "kind": "choice",
                "values": ["explicit"],
                "default": "explicit",
            },
            "approval_mode": {
                "required": True,
                "kind": "choice",
                "values": ["full_auto"],
            },
            "request_timeout_ms": {
                "required": True,
                "kind": "integer",
                "default": 120000,
            },
            "maximum_attempts": {
                "required": True,
                "kind": "integer",
                "values": [1],
                "default": 1,
            },
            "capture_mode": {
                "required": False, "kind": "choice",
                "values": ["session", "telemetry", "deep_telemetry"],
                "default": registered_defaults.get("capture_mode", "session"),
            },
            "diagnostic_privacy_acknowledged": {
                "required": False, "kind": "choice",
                "values": ["not_acknowledged", DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT],
                "default": "not_acknowledged",
            },
        }
        if "reasoning_effort" in registered_defaults:
            controls["reasoning_effort"] = {
                "required": True, "kind": "choice", "source": "model/list",
            }
        return {
            "runner": {"id": self._runner_id, "version": self._runner_version},
            "contract": {"id": "arcgrav.shared.runner-invocation", "version": "2.0.0"},
            "registration": registration,
            "supported_controls": controls,
            "fixed_controls": copy.deepcopy(_FIXED_CONTROLS),
            "capabilities": list(registration.get("capabilities", [])),
            "limitations": list(registration.get("limitations", [])),
            "access_methods": copy.deepcopy(
                list(
                    registration["extensions"][
                        "arcgrav.adapters:access_methods"
                    ]
                )
            ),
            "response_retention": {
                "mode": "stdout_inline_extension",
                "hash": "sha256",
                "normalization": "none",
            },
            "telemetry": {"provider_usage": False, "byte_measurements": True,
                          "persisted_session": True, "session_matching": "exact_thread_id"},
            "secret_handling": {
                "credentials_required": False,
                "transient_secrets_supported": False,
            },
        }

    def describe(self) -> dict[str, Any]:
        return copy.deepcopy(self._description)

    def execute(
        self, request: Mapping[str, Any], *,
        event_callback: Callable[[Mapping[str, str]], None] | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
        live_view_control=None,
    ) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("Codex CLI runner is closed")

        validated = validate_runner_request(request)
        if validated.boundary_controls.get("capture_mode", "session") != "session":
            from ...runtime.orchestration.activity import publish_capture_progress
            publish_capture_progress({"phase": "preflight", "scope": "original",
                "treatment_id": validated.treatment_id,
                "invocation_id": validated.observation_id,
                "attempt_id": validated.observation_id, "evidence_sealed": False})
        try:
            validate_boundary_support(
                validated,
                runner_id=self._runner_id,
                runner_version=self._runner_version,
                supported_controls=_SUPPORTED_CONTROLS,
                required_controls=_REQUIRED_CONTROLS,
                fixed_controls=_FIXED_CONTROLS,
            )
            self._validate_controls(validated.boundary_controls)
            self._validate_boundary(
                validated.execution_boundary,
                validated.boundary_controls,
            )
        except UnsupportedBoundaryError as exc:
            return self._terminal(
                validated,
                "unsupported",
                "codex_cli_boundary_unsupported",
                metadata={
                    "provider_submitted": False,
                    "boundary_error": exc.code,
                },
            )

        controls = validated.boundary_controls
        timeout_ms = int(controls["request_timeout_ms"])
        frame = validated.prompt_bytes + b"\n\n" + validated.input_bytes
        env = self._environment()
        launch_environment, launch_error = self._resolve_launch_environment(
            controls,
            Path.cwd(),
            env,
            min(timeout_ms, 10000),
        )
        if launch_error or launch_environment is None:
            return self._terminal(
                validated,
                "unsupported",
                launch_error or "codex_cli_boundary_unsupported",
                metadata={"provider_submitted": False},
            )

        try:
            target = resolve_target_composition(
                self._registration,
                execution_boundary=validated.execution_boundary,
                launch_environment=launch_environment,
            )
            authentication_source = _registered_authentication_source(
                self._registration
            )
        except (TypeError, ValueError):
            return self._terminal(
                validated,
                "unsupported",
                "codex_cli_boundary_unsupported",
                metadata={"provider_submitted": False},
            )

        preflight_started_at = self._timestamp()
        preflight_started_mono = self._monotonic()
        capture_mode = controls.get("capture_mode", "session")
        version, preflight_error = self._preflight(
            launch_environment,
            Path.cwd(),
            env,
            min(timeout_ms, 10000),
            require_version=capture_mode == "session",
        )
        launch_metadata = self._launch_metadata(launch_environment)
        if preflight_error:
            return self._preflight_terminal(
                validated,
                target=target,
                authentication_source=authentication_source,
                frame=frame,
                launch_metadata=launch_metadata,
                observed_version=version,
                error_code=preflight_error,
                started_at=preflight_started_at,
                started_mono=preflight_started_mono,
            )
        # Session retains its declared runtime-version contract. Neither telemetry
        # profile admits, rejects, or downgrades capture based on CLI version.
        if (capture_mode == "session" and target.runtime_version is not None
                and (version != self._launch_selection.get("expected_runtime_version", target.runtime_version)
                     or retained_runtime_version(version) != retained_runtime_version(target.runtime_version))):
            return self._preflight_terminal(
                validated,
                target=target,
                authentication_source=authentication_source,
                frame=frame,
                launch_metadata=launch_metadata,
                observed_version=version,
                error_code="codex_cli_version_unsupported",
                started_at=preflight_started_at,
                started_mono=preflight_started_mono,
            )

        if capture_mode != "session":
            # Original evidence identifies the observed runtime, not a stale
            # planned version. An unavailable version is recorded explicitly;
            # neither capture profile has runtime-version admission rules.
            version = version or "unobserved"
            target = replace(target, runtime_version=version)

        model_id = str(controls["model_id"])
        reasoning_effort = controls.get("reasoning_effort")
        if reasoning_effort is not None:
            try:
                self._resolve_reasoning_effort(launch_environment, model_id, reasoning_effort, env, timeout_ms)
            except UnsupportedBoundaryError as exc:
                return self._preflight_terminal(
                    validated, target=target, authentication_source=authentication_source,
                    frame=frame, launch_metadata=launch_metadata, observed_version=version,
                    error_code=exc.code, started_at=preflight_started_at,
                    started_mono=preflight_started_mono,
                )
        if target.launch_mode == "wsl":
            argv = self._wsl_exec_argv(launch_environment, model_id, reasoning_effort)
            isolation = {
                "fresh_process": True,
                "fresh_workdir": True,
                "workdir_scope": "wsl-native-mktemp",
                "session_home_reused": True,
                "codex_session_source": "selected-wsl-user-home",
            }
            return self._execute_process(
                validated,
                target=target,
                authentication_source=authentication_source,
                argv=argv,
                isolation_context=_target_managed_isolation(
                    cwd=Path.cwd(),
                    environment=env,
                    session_home_reused=True,
                ),
                env=env,
                timeout_ms=timeout_ms,
                frame=frame,
                version=version,
                launch_metadata=launch_metadata,
                isolation_metadata=isolation,
                event_callback=event_callback,
                cancellation_requested=cancellation_requested,
                live_view_control=live_view_control,
            )

        argv = self._native_exec_argv(launch_environment, model_id, reasoning_effort)
        isolation = {
            "fresh_process": True,
            "fresh_workdir": True,
            "workdir_scope": "native-temp",
            "session_home_reused": True,
            "codex_session_source": "selected-native-user-home",
        }
        return self._execute_process(
            validated,
            target=target,
            authentication_source=authentication_source,
            argv=argv,
            isolation_context=temporary_workdir_isolation(
                env,
                session_home_reused=True,
                prefix="arcgrav-codex-work-",
            ),
            env=env,
            timeout_ms=timeout_ms,
            frame=frame,
            version=version,
            launch_metadata=launch_metadata,
            isolation_metadata=isolation,
            event_callback=event_callback,
            cancellation_requested=cancellation_requested,
            live_view_control=live_view_control,
        )

    def close(self) -> None:
        self._closed = True

    def _validate_controls(self, controls: Mapping[str, Any]) -> None:
        if (controls.get("capture_mode") == "deep_telemetry"
                and controls.get("diagnostic_privacy_acknowledged") != DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT):
            raise UnsupportedBoundaryError(
                "runner_control_unsupported",
                "diagnostic capture requires an explicit current-version privacy acknowledgement",
            )
        model_id = controls.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise UnsupportedBoundaryError(
                "runner_control_unsupported",
                "model_id must be explicit non-empty text",
            )
        timeout_ms = controls.get("request_timeout_ms")
        if "reasoning_effort" in controls and (
                not isinstance(controls["reasoning_effort"], str)
                or not controls["reasoning_effort"].strip()):
            raise UnsupportedBoundaryError(
                "codex_cli_reasoning_effort_unsupported", "reasoning_effort must be explicit text",
            )
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or timeout_ms < 1
        ):
            raise UnsupportedBoundaryError(
                "runner_control_unsupported",
                "request_timeout_ms must be a positive integer",
            )
        if controls.get("maximum_attempts") != 1:
            raise UnsupportedBoundaryError(
                "runner_control_unsupported",
                "maximum_attempts must equal 1",
            )
        if controls.get("approval_mode") != "full_auto":
            raise UnsupportedBoundaryError(
                "runner_control_unsupported",
                "approval_mode must equal full_auto",
            )
        if controls.get("launch_mode") == "wsl":
            distribution = self._launch_selection.get("wsl_distribution", controls.get("wsl_distribution"))
            if not isinstance(distribution, str) or not distribution:
                raise UnsupportedBoundaryError(
                    "runner_control_unsupported",
                    "wsl_distribution is required for WSL execution",
                )

    def _validate_boundary(
        self,
        execution_boundary: Mapping[str, Any],
        controls: Mapping[str, Any],
    ) -> str | None:
        runtime = execution_boundary.get("provider_runtime")
        if not isinstance(runtime, Mapping):
            raise UnsupportedBoundaryError(
                "runner_boundary_unsupported",
                "provider_runtime must be present",
            )
        if runtime.get("runtime_id") != self._runner_id:
            raise UnsupportedBoundaryError(
                "runner_boundary_unsupported",
                "provider runtime identity does not select Codex CLI",
            )
        if runtime.get("access_method") != "cli":
            raise UnsupportedBoundaryError(
                "runner_boundary_unsupported",
                "provider runtime access method must be cli",
            )
        if runtime.get("model") != controls.get("model_id"):
            raise UnsupportedBoundaryError(
                "runner_boundary_unsupported",
                "provider runtime model does not match model_id",
            )
        version = runtime.get("runtime_version")
        if version is not None and (
            not isinstance(version, str) or not version.strip()
        ):
            raise UnsupportedBoundaryError(
                "runner_boundary_unsupported",
                "runtime_version must be exact non-empty text or null",
            )
        return version

    def _resolve_launch_environment(
        self,
        controls: Mapping[str, Any],
        cwd: Path,
        env: Mapping[str, str],
        timeout_ms: int,
    ) -> tuple[dict[str, str] | None, str | None]:
        registration = self._registration
        launch = registration["extensions"]["arcgrav.adapters:launch_environment"]
        mode = controls.get("launch_mode")
        binary = self._launch_selection.get("codex_binary", controls.get("codex_binary"))
        if binary == "runtime/codex":
            binary = "codex"
        if mode not in launch["supported_modes"]:
            return None, "codex_cli_boundary_unsupported"
        if not isinstance(binary, str) or not binary:
            return None, "codex_cli_executable_missing"

        if mode == "native":
            try:
                executable = self._executable_resolver(binary)
            except Exception:
                executable = None
            if not isinstance(executable, str) or not executable:
                return None, "codex_cli_executable_missing"
            # A resolver may return a relative executable path (including the
            # registered repository-local compatibility target). Preflight runs
            # from the caller's cwd, but accepted execution runs from a fresh
            # isolated cwd; anchor path-bearing results before that transition.
            # The selected comparison-relevant codex_binary control is unchanged.
            if not Path(executable).is_absolute() and (
                "/" in executable or "\\" in executable
            ):
                executable = str((cwd / executable).resolve())
            return {"mode": "native", "executable": executable}, None

        if self._platform_name != "nt":
            return None, "codex_cli_host_launcher_missing"
        launcher_name = launch["wsl"]["launcher_default"]
        try:
            launcher = self._executable_resolver(launcher_name)
        except Exception:
            launcher = None
        if not isinstance(launcher, str) or not launcher:
            return None, "codex_cli_host_launcher_missing"
        distribution = self._launch_selection.get("wsl_distribution", controls.get("wsl_distribution"))
        if not isinstance(distribution, str) or not distribution:
            return None, "codex_cli_boundary_unsupported"

        # Verify the exact target in WSL without touching authentication.
        executable = _registered_wsl_target_executable(registration, binary)
        if executable is None:
            return None, "codex_cli_executable_missing"
        if PureWindowsPath(executable).is_absolute():
            check_args = (
                "sh", "-lc",
                'test -r "$(wslpath -u "$1")" && command -v python3 >/dev/null',
                "arcgrav-codex", executable,
            )
        elif "/" in executable:
            check_args = ("test", "-x", executable)
        else:
            check_args = (
                "sh", "-lc",
                'resolved_executable="$(command -v "$1")" && test -x "$resolved_executable"',
                "arcgrav-codex", binary,
            )
        try:
            result = self._invoke(
                (
                    launcher,
                    "--distribution",
                    distribution,
                    "--exec",
                    *check_args,
                ),
                input_bytes=None,
                cwd=cwd,
                env=env,
                timeout_ms=timeout_ms,
            )
        except Exception:
            return None, "codex_cli_executable_missing"
        if result["returncode"] != 0:
            return None, "codex_cli_executable_missing"
        return {
            "mode": "wsl",
            "launcher": launcher,
            "distribution": distribution,
            "executable": executable,
        }, None

    def _preflight(
        self,
        launch_environment: Mapping[str, str],
        cwd: Path,
        env: Mapping[str, str],
        timeout_ms: int,
        *,
        require_version: bool = True,
    ) -> tuple[str | None, str | None]:
        # Version observation is evidence, not an admission gate for telemetry.
        version = None
        try:
            version_result = self._invoke(
                self._launch_argv(launch_environment, ("--version",)),
                input_bytes=None,
                cwd=cwd,
                env=env,
                timeout_ms=timeout_ms,
            )
            if version_result["returncode"] == 0:
                version = _extract_version(
                    version_result["stdout"] + b"\n" + version_result["stderr"]
                )
        except Exception:
            pass
        if require_version and version is None:
            return None, "codex_cli_version_unavailable"

        try:
            help_result = self._invoke(
                self._launch_argv(launch_environment, ("exec", "--help")),
                input_bytes=None,
                cwd=cwd,
                env=env,
                timeout_ms=timeout_ms,
            )
        except Exception:
            return version, "codex_cli_noninteractive_unavailable"
        if help_result["returncode"] != 0:
            return version, "codex_cli_noninteractive_unavailable"
        return version, None

    @staticmethod
    def _launch_argv(
        launch_environment: Mapping[str, str],
        args: tuple[str, ...],
    ) -> tuple[str, ...]:
        if launch_environment["mode"] == "native":
            return (launch_environment["executable"], *args)
        return _wsl_cli_argv(
            launch_environment["launcher"],
            launch_environment["distribution"],
            launch_environment["executable"],
            args,
        )

    def _resolve_reasoning_effort(
        self, launch_environment: Mapping[str, str], model_id: str,
        selected: object, environment: Mapping[str, str], timeout_ms: int,
    ) -> str:
        """Resolve or validate a concrete effort against the selected host's catalog."""
        from .model_discovery import _run_interactive_model_list, decode_model_list_response
        try:
            result = _run_interactive_model_list(
                self._launch_argv(launch_environment, ("app-server", "--listen", "stdio://")),
                cwd=Path.cwd(), env=environment, timeout=min(timeout_ms / 1000, 10.0),
            )
            catalog = decode_model_list_response(result)
            choice = next(choice for choice in catalog["choices"] if choice["model_id"] == model_id)
            options = [option["value"] for option in choice["reasoning_efforts"]]
            effort = choice["default_reasoning_effort"] if selected is None else selected
            if not isinstance(effort, str) or effort not in options:
                raise ValueError("unsupported reasoning effort")
            return effort
        except Exception as exc:
            raise UnsupportedBoundaryError(
                "codex_cli_reasoning_effort_unsupported",
                "Selected model and reasoning effort could not be validated",
            ) from exc

    @staticmethod
    def _capture_argv(argv, overrides, launch_mode, environment_overrides=None,
                      process_control_path=None):
        """Apply only declared stock configuration on the selected host."""
        if not overrides:
            return argv
        flags = tuple(part for setting in overrides for part in ("-c", setting))
        if launch_mode == "native":
            return (argv[0], *flags, *argv[1:])
        # WSL receives configuration as positional arguments, never shell text.
        # Its collector capability is separately gated by the capture profile.
        trace_root = (environment_overrides or {}).get("CODEX_ROLLOUT_TRACE_ROOT") or ""
        script = argv[6].replace('set -eu',
            'set -eu\ntrace_root="$1"\nshift\nunset CODEX_ROLLOUT_TRACE_ROOT\n'
            'if [ -n "$trace_root" ]; then export CODEX_ROLLOUT_TRACE_ROOT="$trace_root"; fi')
        if process_control_path is not None:
            from ...telemetry.wsl_process import GUARD_SOURCE
            script = script.replace('trace_root="$1"\nshift',
                'trace_root="$1"\nprocess_control="$2"\nguard_code="$3"\nshift 3')
            script = script.rsplit('"$@"', 1)[0] + 'python3 -c "$guard_code" "$process_control" "$@"'
            return (*argv[:6], script, argv[7], trace_root, process_control_path, GUARD_SOURCE, *argv[8:], *flags)
        return (*argv[:6], script, argv[7], trace_root, *argv[8:], *flags)

    @staticmethod
    def _native_exec_argv(
        launch_environment: Mapping[str, str],
        model_id: str,
        reasoning_effort: str | None = None,
    ) -> tuple[str, ...]:
        return (
            launch_environment["executable"],
            "exec",
            "--model",
            model_id,
            "--approve-for-me",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--json",
            *(("-c", "model_reasoning_effort=" + json.dumps(reasoning_effort)) if reasoning_effort is not None else ()),
            "-",
        )

    @staticmethod
    def _wsl_exec_argv(
        launch_environment: Mapping[str, str],
        model_id: str,
        reasoning_effort: str | None = None,
    ) -> tuple[str, ...]:
        return (
            launch_environment["launcher"],
            "--distribution",
            launch_environment["distribution"],
            "--exec",
            "sh",
            "-lc",
            _WSL_EXEC_SCRIPT,
            "arcgrav-codex",
            launch_environment["executable"],
            model_id,
            *(("-c", "model_reasoning_effort=" + json.dumps(reasoning_effort)) if reasoning_effort is not None else ()),
        )

    @staticmethod
    def _launch_metadata(
        launch_environment: Mapping[str, str],
    ) -> dict[str, str]:
        if launch_environment["mode"] == "native":
            return {
                "mode": "native",
                "executable": launch_environment["executable"],
            }
        return {
            "mode": "wsl",
            "distribution": launch_environment["distribution"],
            "executable": launch_environment["executable"],
        }

    def _preflight_terminal(
        self,
        validated: Any,
        *,
        target: TargetCompositionDescriptor,
        authentication_source: str | None,
        frame: bytes,
        launch_metadata: Mapping[str, str],
        observed_version: str | None,
        error_code: str,
        started_at: str,
        started_mono: float,
    ) -> dict[str, Any]:
        """Emit schema-bound evidence after composition but before inference.

        Version/help subprocesses are preflight probes, not a treatment
        submission. No process channels or isolation may be invented for an
        inference invocation that never occurred.
        """
        self._capture_preflight_unavailable(validated, error_code)
        execution = TerminalExecutionResult(
            terminal_status="unsupported",
            failure_kind=ExecutionFailureKind.PREFLIGHT_UNSUPPORTED,
            started_at=started_at,
            completed_at=self._timestamp(),
            duration_ms=self._duration(started_mono),
            invocation_occurred=False,
            capture=InvocationCapture(
                succeeded=False,
                exit_status=None,
                transport_status=None,
                stdout=b"",
                stderr=b"",
            ),
            response_bytes=None,
            isolation=None,
        )
        return emit_terminal_observation(
            validated,
            target=target,
            execution=execution,
            runner_id=self._runner_id,
            runner_version=self._runner_version,
            framed_request=frame,
            request_framing_mode="codex_cli",
            authentication_source=authentication_source,
            launch_environment_id=launch_metadata.get("distribution"),
            error_code=error_code,
            error_classification=error_code,
            error_message=error_code,
            extensions={
                f"{_NAMESPACE}:execution": {
                    "provider_submitted": False,
                    "observed_runtime_version": retained_runtime_version(observed_version),
                    "launch_environment": {"mode": launch_metadata["mode"], "executable": "runtime/codex"},
                },
                f"{_NAMESPACE}:provider_usage": {
                    "availability": "unavailable",
                    "reason": "not_reported_by_registered_surface",
                },
            },
        )

    def _execute_process(
        self,
        validated: Any,
        *,
        target: TargetCompositionDescriptor,
        authentication_source: str | None,
        argv: tuple[str, ...],
        isolation_context: Any,
        env: Mapping[str, str],
        timeout_ms: int,
        frame: bytes,
        version: str,
        launch_metadata: Mapping[str, str],
        isolation_metadata: Mapping[str, Any],
        event_callback: Callable[[Mapping[str, str]], None] | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
        live_view_control=None,
    ) -> dict[str, Any]:
        input_submitted = False
        telemetry = None
        telemetry_start_error = None
        effective_argv = argv
        effective_env = dict(env)
        from ...runtime.orchestration.activity import capture_progress_callback
        progress = capture_progress_callback(invocation_id=validated.observation_id)

        def capture_progress(event):
            progress({**event, "scope": "original", "treatment_id": validated.treatment_id,
                      "attempt_id": validated.observation_id})

        def submitted() -> None:
            nonlocal input_submitted
            input_submitted = True

        def before_invoke(context: InvocationContext) -> None:
            nonlocal telemetry, telemetry_start_error, effective_argv, effective_env
            from ..execution.orchestration import observe_startup
            # Replay retains the uninstrumented launch configuration and is a
            # separate execution. Invocation-local receiver endpoints never
            # enter replay argv or original measurement authority.
            observe_startup(observation_id=validated.observation_id,
                generation_id=validated.accepted_generation_id, argv=argv,
                environment=context.environment, cwd=context.cwd, runtime_version=version,
                launch_metadata=launch_metadata, framed_request_sha256=sha256_bytes(frame),
                external_provider_submission=target.external_provider_submission)
            selected = validated.boundary_controls.get("capture_mode", "session")
            if selected != "session":
                # This hook runs inside an already-established isolation context.
                # Keep telemetry preparation errors distinct from isolation
                # failures, without retaining exception text or private paths.
                setup_error = "codex_cli_telemetry_configuration_invalid"
                try:
                    from ...telemetry import CaptureProfile, CaptureSession
                    profile = CaptureProfile.from_control(selected,
                        diagnostic_privacy_acknowledged=(validated.boundary_controls.get(
                            "diagnostic_privacy_acknowledged") == DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT))
                    setup_error = "codex_cli_telemetry_initialization_failed"
                    capture_type = CaptureSession
                    capture_options = {"cancellation_requested": lambda: self._closed or (
                        cancellation_requested is not None and cancellation_requested())}
                    if launch_metadata["mode"] == "wsl":
                        from ...telemetry.wsl import WslCaptureSession
                        capture_type = WslCaptureSession
                        capture_options = {"launch_metadata": {**launch_metadata, "launcher": argv[0]},
                                           "environment": env}
                    telemetry = capture_type(profile=profile, runtime_version=version,
                        invocation_id=validated.observation_id,
                        launch_mode=launch_metadata["mode"], on_progress=capture_progress,
                        **capture_options)
                    telemetry.runtime.update({
                        "runner_id": self._runner_id, "runner_version": self._runner_version,
                        "accepted_boundary_fingerprint": validated.execution_boundary_fingerprint,
                        "framed_request_sha256": sha256_bytes(frame),
                        "configuration_authority": "accepted_execution_boundary",
                        "binary_sha256": None,
                        "binary_hash_reason": "selected_host_binary_not_locally_readable",
                    })
                    if launch_metadata["mode"] == "native":
                        try:
                            telemetry.runtime["binary_sha256"] = sha256_bytes(
                                Path(launch_metadata["executable"]).read_bytes())
                            telemetry.runtime["binary_hash_reason"] = None
                        except OSError:
                            pass
                    setup_error = ("codex_cli_telemetry_selected_host_unavailable"
                                   if launch_metadata["mode"] == "wsl"
                                   else "codex_cli_telemetry_collector_unavailable")
                    telemetry.start()
                    if launch_metadata["mode"] == "native" and telemetry.collector is None:
                        raise RuntimeError("required local receiver did not start")
                    if launch_metadata["mode"] == "native" and profile.diagnostics_enabled:
                        setup_error = "codex_cli_telemetry_diagnostics_unavailable"
                        if (telemetry.diagnostic_root is None
                                or telemetry.ledger.sources["diagnostics"]["state"] != "ready"):
                            raise RuntimeError("required diagnostic directory did not initialize")
                    setup_error = "codex_cli_telemetry_launch_configuration_failed"
                    effective_argv = self._capture_argv(argv, telemetry.config_overrides,
                        launch_metadata["mode"], telemetry.env_overrides,
                        getattr(telemetry, "process_control_path", None))
                    for name, value in telemetry.env_overrides.items():
                        if value is None or launch_metadata["mode"] == "wsl":
                            effective_env.pop(name, None)
                        else:
                            effective_env[name] = value
                except Exception as exc:
                    # Only fixed worker stage codes may refine a remote failure;
                    # arbitrary exception messages never become diagnostics.
                    if (setup_error == "codex_cli_telemetry_selected_host_unavailable"
                            and getattr(exc, "reason", None) in {
                                "selected_host_collector_unavailable", "selected_host_diagnostics_unavailable"}):
                        setup_error = {"selected_host_collector_unavailable": "codex_cli_telemetry_collector_unavailable",
                                       "selected_host_diagnostics_unavailable": "codex_cli_telemetry_diagnostics_unavailable"}[exc.reason]
                    telemetry_start_error = setup_error
                    raise

        def invoke(context: InvocationContext, attempt_timeout_ms: int) -> Any:
            token = _LIVE_CAPTURE.set({
                "event_callback": event_callback,
                "live_view_control": live_view_control,
                "cancellation_requested": lambda: self._closed or (
                    cancellation_requested is not None and cancellation_requested()
                ),
                "on_input": submitted,
                "telemetry": telemetry,
            })
            try:
                return self._invoke_capture(
                    effective_argv, input_bytes=frame, cwd=context.cwd,
                    env=effective_env, timeout_ms=attempt_timeout_ms,
                )
            finally:
                _LIVE_CAPTURE.reset(token)

        execution = execute_target(
            isolation=isolation_context,
            invoke=invoke,
            response_extractor=self._extract_response,
            timeout_ms=timeout_ms,
            timestamp=self._timestamp,
            monotonic=self._monotonic,
            before_invoke=before_invoke,
        )
        if telemetry_start_error is not None:
            try:
                if telemetry is not None:
                    telemetry.close()
            except Exception:
                pass
            return self._preflight_terminal(validated, target=target,
                authentication_source=authentication_source, frame=frame,
                launch_metadata=launch_metadata, observed_version=version,
                error_code=telemetry_start_error, started_at=execution.started_at,
                started_mono=self._monotonic())
        if telemetry is not None and launch_metadata["mode"] == "wsl":
            # The Windows launcher may exit before its Linux descendants. Stop
            # only the bridge-owned process group before rollout settlement.
            try:
                telemetry.stop_execution()
            except Exception:
                telemetry.ledger.count("process", partial=1)
                telemetry.ledger.state("process", "partial", "selected_host_cleanup_unconfirmed")
        error_code = self._execution_error_code(execution)
        metadata = {
            "provider_submitted": (
                execution.invocation_occurred
                and target.external_provider_submission
            ),
            "observed_runtime_version": retained_runtime_version(version),
            "launch_environment": {"mode": launch_metadata["mode"], "executable": "runtime/codex"},
            "isolation": ({k: isolation_metadata[k] for k in ("fresh_process", "fresh_workdir", "prior_observation_context_reused", "session_home_reused") if k in isolation_metadata} if execution.isolation is not None else {"availability": "unavailable"}),
            "authentication": {
                "class": target.authentication_class,
                "source": authentication_source,
                "credential_material_retained": False,
            },
            "request_framing": {
                "mode": "codex_cli",
                "separator": "LF LF",
                "sha256": sha256_bytes(frame),
                "byte_length": len(frame),
            },
            "process_exit_status": execution.capture.exit_status,
        }
        extensions: dict[str, Any] = {
            f"{_NAMESPACE}:execution": metadata,
            f"{_NAMESPACE}:provider_usage": {
                "availability": "unavailable",
                "reason": "not_reported_by_registered_surface",
            },
        }
        if error_code is not None:
            extensions[f"{_NAMESPACE}:error"] = {
                "classification": error_code,
                "message": error_code,
                "retryable": False,
                "details": {},
            }

        thread_id = returned_thread_id(execution.capture.stdout)
        record = {"availability": "unavailable", "thread_id": thread_id,
                  "reason": "returned_thread_id_missing" if thread_id is None else "session_capture_unavailable"}
        reader = getattr(self._transport, "read_session", None)
        if telemetry is not None:
            capture_progress({"phase": "rollout_settlement", "evidence_sealed": False})
        if thread_id is not None and callable(reader):
            token = _SESSION_CANCELLATION.set(lambda: self._closed or (
                cancellation_requested is not None and cancellation_requested()))
            try:
                record = reader(thread_id, launch_environment={**launch_metadata, "launcher": argv[0]}, environment=env)
                if not isinstance(record, Mapping):
                    raise ValueError("invalid session capture result")
            except (OSError, ValueError, TypeError, subprocess.SubprocessError):
                record = {"availability": "unavailable", "thread_id": thread_id, "reason": "session_capture_failed"}
            finally:
                _SESSION_CANCELLATION.reset(token)
        record = {**record, "generation_id": validated.accepted_generation_id,
                  "observation_id": validated.observation_id, "attempt": 1,
                  "launch_environment": dict(launch_metadata)}
        if telemetry is not None:
            from ...telemetry.normalization import normalize_capture
            try:
                if (telemetry.profile.diagnostics_enabled and execution.terminal_status != "cancelled"
                        and not self._closed and not (cancellation_requested is not None and cancellation_requested())):
                    telemetry.reduce_diagnostics(launch_metadata["executable"])
                manifest = telemetry.finish(stdout=execution.capture.stdout,
                    stderr=execution.capture.stderr, rollout_record=record,
                    process_status={"status": execution.terminal_status,
                        "exit_status": execution.capture.exit_status,
                        "transport_status": execution.capture.transport_status,
                        "started_at": execution.started_at, "completed_at": execution.completed_at,
                        "duration_ms": execution.duration_ms,
                        "process_channels_observed": execution.process_channels_observed})
                extensions["agmark.telemetry:capture"] = manifest
                capture_progress({"phase": "normalization", "evidence_sealed": False})
                extensions["agmark.telemetry:normalized"] = normalize_capture(manifest)
                capture_progress({"phase": "completion", "evidence_sealed": True,
                    "telemetry_outcome": manifest["completeness"]["status"],
                    "benchmark_outcome": execution.terminal_status})
            except Exception:
                # Telemetry quality cannot change registered response scoring.
                extensions["agmark.telemetry:error"] = {
                    "reason": "capture_or_normalization_failed",
                    "profile": validated.boundary_controls.get("capture_mode", "session")}
                capture_progress({"phase": "completion", "evidence_sealed": False,
                    "telemetry_outcome": "failed", "benchmark_outcome": execution.terminal_status})
            finally:
                try:
                    telemetry.close()
                except Exception:
                    extensions.setdefault("agmark.telemetry:error", {
                        "reason": "capture_cleanup_failed",
                        "profile": validated.boundary_controls.get("capture_mode", "session")})
        measurements, record = extract_session_measurements(
            record, execution.capture.stdout, runtime_version=version,
            process_complete=(execution.process_channels_observed
                              and execution.capture.exit_status is not None
                              and execution.capture.transport_status is None),
        )
        extensions[ATTEMPT_MEASUREMENTS] = measurements
        extensions[SESSION_RECORD] = record
        if input_submitted:
            extensions["arcgrav.runner:submitted_input"] = {
                "sha256": sha256_bytes(frame),
                "byte_length": len(frame),
                "encoding": "utf-8",
            }

        return emit_terminal_observation(
            validated,
            target=target,
            execution=execution,
            runner_id=self._runner_id,
            runner_version=self._runner_version,
            framed_request=frame,
            request_framing_mode="codex_cli",
            authentication_source=authentication_source,
            launch_environment_id=launch_metadata.get("distribution"),
            error_code=error_code,
            error_classification=error_code,
            error_message=error_code,
            extensions=extensions,
        )

    @staticmethod
    def _extract_response(capture: InvocationCapture) -> bytes | None:
        return extract_response(capture.stdout)

    @staticmethod
    def _execution_error_code(
        execution: TerminalExecutionResult,
    ) -> str | None:
        if execution.failure_kind is None:
            return None
        if execution.failure_kind is ExecutionFailureKind.PROCESS_FAILED:
            if any(
                marker in execution.capture.stderr.lower()
                for marker in _AUTH_MARKERS
            ):
                return "codex_cli_authentication_failed"
            return "codex_cli_process_failed"
        return {
            ExecutionFailureKind.ISOLATION_FAILED: "codex_cli_isolation_failed",
            ExecutionFailureKind.INVOCATION_FAILED: "codex_cli_process_failed",
            ExecutionFailureKind.CAPTURE_INVALID: "codex_cli_process_failed",
            ExecutionFailureKind.RESPONSE_EXTRACTION_FAILED: "codex_cli_process_failed",
            ExecutionFailureKind.RESPONSE_UNAVAILABLE: "codex_cli_response_unavailable",
            ExecutionFailureKind.TIMED_OUT: "codex_cli_process_timed_out",
            ExecutionFailureKind.CANCELLED: "codex_cli_process_cancelled",
        }[execution.failure_kind]

    def _invoke_capture(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None,
        cwd: Path,
        env: Mapping[str, str],
        timeout_ms: int,
    ) -> Any:
        live = (_LIVE_CAPTURE.get() if input_bytes is not None else None) or {}
        event_callback = live.get("event_callback")
        live_view_control = live.get("live_view_control")
        cancellation_requested = live.get("cancellation_requested")
        on_input = live.get("on_input")
        telemetry = live.get("telemetry")
        run = getattr(self._transport, "run", None)
        if not callable(run):
            raise TypeError("transport must expose run()")
        def emit(channel: str, text: str) -> None:
            if event_callback is not None and (live_view_control is None or live_view_control.snapshot()[0]):
                try:
                    event = {"channel": channel, "text": text, "mode": "snapshot"}
                    if live_view_control is not None:
                        event["stream_revision"] = (decoder.revision if channel == "output"
                                                    else live_view_control.snapshot()[1])
                    event_callback(event)
                except Exception:
                    # Presentation failure cannot alter retained evidence/scoring.
                    pass

        from .events import ControlledLiveResponseDecoder
        decoder = ControlledLiveResponseDecoder(lambda text: emit("output", text), live_view_control)

        def capture_chunk(source, chunk):
            if telemetry is None:
                return
            try:
                getattr(telemetry, "ingest_" + source)(chunk)
            except Exception:
                # A telemetry consumer cannot interrupt the stock process or
                # replace the independently retained benchmark response.
                telemetry.ledger.count(source, partial=1)
                telemetry.ledger.state(source, "partial", "stream_capture_failed")

        def stdout_received(chunk):
            capture_chunk("stdout", chunk)
            if event_callback is not None:
                decoder.feed(chunk)

        def submitted() -> None:
            if on_input is not None:
                on_input()
            if input_bytes is not None and event_callback is not None:
                try:
                    text = input_bytes.decode("utf-8")
                except UnicodeError:
                    # The invocation contract also permits arbitrary bytes.
                    # Never repair them or let a text-only view prevent submission.
                    return
                emit("input", text)

        kwargs = dict(input_bytes=input_bytes, cwd=cwd,
                      env=copy.deepcopy(dict(env)), timeout_ms=timeout_ms)
        streaming = getattr(self._transport, "run_streaming", None)
        if callable(streaming):
            callbacks = {
                "on_stdout": stdout_received if event_callback is not None or telemetry is not None else None,
                "on_input": submitted if input_bytes is not None else None,
                "cancellation_requested": cancellation_requested,
            }
            # Preserve the established injected-transport seam; production
            # drains both channels concurrently and reports incremental bytes.
            if telemetry is not None and isinstance(self._transport, _SubprocessTransport):
                callbacks["on_stderr"] = lambda chunk: capture_chunk("stderr", chunk)
            token = _PIPE_CALLBACKS.set(callbacks)
            interrupted = False
            try:
                if isinstance(self._transport, _SubprocessTransport):
                    # Preserve the run() instrumentation seam used by shared
                    # live/mock conformance; its production body streams pipes.
                    result = run(argv, **kwargs)
                else:
                    result = streaming(argv, **kwargs, **callbacks)
            except (InvocationCancelled, subprocess.TimeoutExpired):
                interrupted = True
                raise
            finally:
                _PIPE_CALLBACKS.reset(token)
                if not interrupted:
                    decoder.finish()
        else:
            # Existing injected transports retain their original run() contract.
            # Only the production pipe transport promises before-exit updates.
            if input_bytes is not None:
                submitted()
            result = run(argv, **kwargs)
            if event_callback is not None and isinstance(result, Mapping):
                stdout = result.get("stdout")
                if isinstance(stdout, bytes):
                    decoder.feed(stdout)
                    decoder.finish()
        if (event_callback is not None and isinstance(result, Mapping)
                and (live_view_control is None or live_view_control.snapshot()[0])):
            stdout = result.get("stdout")
            if isinstance(stdout, bytes):
                response = extract_response(stdout)
                if response is not None:
                    decoder.snapshot(response.decode("utf-8"))
        return result

    def _invoke(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None,
        cwd: Path,
        env: Mapping[str, str],
        timeout_ms: int,
    ) -> dict[str, Any]:
        raw = self._invoke_capture(
            argv,
            input_bytes=input_bytes,
            cwd=cwd,
            env=env,
            timeout_ms=timeout_ms,
        )
        if not isinstance(raw, Mapping):
            raise TypeError("transport run() must return a mapping")
        returncode = raw.get("returncode")
        stdout = raw.get("stdout", b"")
        stderr = raw.get("stderr", b"")
        if isinstance(returncode, bool) or not isinstance(returncode, int):
            raise TypeError("transport returncode must be an integer")
        if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
            raise TypeError("transport stdout/stderr must be bytes")
        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    @staticmethod
    def _environment() -> dict[str, str]:
        return {
            name: os.environ[name]
            for name in _ALLOWED_PARENT_ENV
            if name in os.environ
        }

    @staticmethod
    def _redacted_command(argv: tuple[str, ...]) -> list[str]:
        if "sh" in argv and "-lc" in argv:
            result = list(argv)
            try:
                script_index = result.index("-lc") + 1
            except ValueError:
                return result
            if script_index < len(result):
                result[script_index] = "<registered-wsl-exec-script>"
            return result
        return list(argv)

    def _duration(self, started: float) -> float:
        return max(0.0, (self._monotonic() - started) * 1000.0)

    @staticmethod
    def _capture_preflight_unavailable(validated, reason):
        profile = validated.boundary_controls.get("capture_mode", "session")
        if profile == "session":
            return
        from ...runtime.orchestration.activity import publish_capture_progress
        sources = [{"source_id": source, "state": "unsupported", "reason": reason}
                   for source in ("stdout", "stderr", "process", "rollout", "otel_logs",
                                  "otel_traces", "otel_metrics", "diagnostics")]
        if profile != "deep_telemetry":
            sources[-1].update(state="disabled", reason="explicit_sensitive_diagnostic_opt_in_required")
        publish_capture_progress({"phase": "completion", "scope": "original",
            "invocation_id": validated.observation_id, "treatment_id": validated.treatment_id,
            "attempt_id": validated.observation_id, "sources": sources,
            "evidence_sealed": False, "telemetry_outcome": "unavailable"})

    def _terminal(
        self,
        validated: Any,
        status: str,
        error_code: str | None,
        *,
        response_bytes: bytes | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        duration_ms: float | None = None,
        stdout: bytes = b"",
        stderr: bytes = b"",
        metadata: Mapping[str, Any],
        additional_extensions: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status == "unsupported":
            self._capture_preflight_unavailable(validated, error_code or "preflight_unsupported")
        extensions: dict[str, Any] = {
            f"{_NAMESPACE}:execution": {k: metadata[k] for k in ("provider_submitted", "observed_runtime_version") if k in metadata},
            f"{_NAMESPACE}:provider_usage": {
                "availability": "unavailable",
                "reason": "not_reported_by_registered_surface",
            },
        }
        if additional_extensions:
            extensions.update(copy.deepcopy(dict(additional_extensions)))
        if error_code:
            extensions[f"{_NAMESPACE}:error"] = {
                "classification": error_code,
                "message": error_code,
                "retryable": False,
                "details": {},
            }

        # Registration establishes the selected adapter identity, not a verified
        # host/runtime. Early failure still needs the shared terminal envelope so
        # lifecycle retention does not lose the unsupported outcome.
        registration_extensions = self._registration["extensions"]
        composition = registration_extensions["arcgrav.adapters:target_composition"]
        access = registration_extensions["arcgrav.adapters:access_methods"][0]
        declared = TargetCompositionDescriptor.create(
            target_class=composition["target_class"],
            evidence_class=registration_extensions["arcgrav.adapters:evidence_class"],
            runtime_id=self._runner_id, runtime_version=None,
            access_method=access["type"], external_provider_submission=composition["external_provider_submission"],
            launch_mode="unresolved", launch_environment_selector={}, executable="runtime/codex",
            authentication_class=access["authentication_class"], compatibility_profile=composition.get("compatibility_profile"),
            production_runner_entry_point=registration_extensions["arcgrav.adapters:entry_point"],
            runner_implementation_artifact_ids=composition["runner_implementation_artifact_ids"],
        )
        now = self._timestamp()
        execution = TerminalExecutionResult(
            terminal_status="unsupported", failure_kind=ExecutionFailureKind.PREFLIGHT_UNSUPPORTED,
            started_at=started_at or now, completed_at=completed_at or now,
            duration_ms=duration_ms if duration_ms is not None else 0.0,
            invocation_occurred=False, capture=InvocationCapture(False, None, None, b"", b""),
            response_bytes=None, isolation=None, process_channels_observed=False,
        )
        observation = emit_terminal_observation(
            validated, target=declared, execution=execution,
            runner_id=self._runner_id, runner_version=self._runner_version,
            framed_request=validated.prompt_bytes + b"\n\n" + validated.input_bytes,
            request_framing_mode="codex_cli", authentication_source=None,
            error_code=error_code, error_classification=error_code, error_message=error_code,
            extensions=extensions,
        )
        from ..execution.emission import EXECUTION_EVIDENCE_EXTENSION_KEY, validate_retained_parity_observation
        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        canonical["runtime"].update(availability="unavailable", runtime_version=None, model_id=None)
        canonical["launch_environment"].update(availability="unavailable", mode=None, executable="runtime/codex")
        canonical["authentication"].update(availability="unavailable", **{"class": None, "source": None})
        validate_retained_parity_observation(observation)
        return observation


def _extract_version(value: bytes) -> str | None:
    match = _VERSION_RE.search(value.decode("utf-8", errors="replace"))
    return match.group(1) if match and len(match.group(1)) <= 128 else None


def probe_planning_identity(
    registration: Mapping[str, Any],
    *,
    control_values: Mapping[str, Any] | None = None,
    transport: object | None = None,
    executable_resolver: Callable[[str], str | None] | None = None,
    platform_name: str | None = None,
) -> dict[str, Any]:
    """Resolve runtime identity and model capabilities without provider submission."""

    def blocked(
        error_code: str,
        *,
        observed_runtime_version: str | None = None,
        launch_environment: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "unsupported",
            "error_code": error_code,
            "provider_submitted": False,
            "resolved_controls": {},
        }
        if observed_runtime_version is not None:
            result["observed_runtime_version"] = retained_runtime_version(observed_runtime_version)
        if launch_environment is not None:
            result["launch_environment"] = {"mode": launch_environment["mode"], "executable": "runtime/codex"}
        return result

    try:
        registration = _validated_registration(registration)
        runtime_provider = _registered_runtime_provider(registration)
    except (TypeError, ValueError):
        return blocked("codex_cli_boundary_unsupported")
    if control_values is not None and not isinstance(control_values, Mapping):
        return blocked("codex_cli_boundary_unsupported")

    selected = dict(control_values or {})
    runner = CodexCliRunner(
        registration=registration,
        transport=transport,
        executable_resolver=executable_resolver,
        platform_name=platform_name,
    )
    launch = registration["extensions"]["arcgrav.adapters:launch_environment"]
    mode = selected.get(
        "launch_mode",
        "wsl" if runner._platform_name == "nt" else "native",
    )
    if mode not in launch["supported_modes"]:
        runner.close()
        return blocked("codex_cli_boundary_unsupported")

    defaults = launch[mode]
    executable = selected.get("codex_binary", defaults["codex_binary_default"])
    model_id = selected.get("model_id")
    timeout_ms = selected.get("request_timeout_ms", 120000)
    if (
        not isinstance(executable, str)
        or not executable
        or not isinstance(model_id, str)
        or not model_id.strip()
        or isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or timeout_ms < 1
    ):
        runner.close()
        return blocked("codex_cli_boundary_unsupported")

    controls: dict[str, Any] = {
        "launch_mode": mode,
        "codex_binary": executable,
        "model_id": model_id,
        "request_timeout_ms": timeout_ms,
    }
    resolved_controls: dict[str, Any] = {
        "launch_mode": mode,
        "codex_binary": executable,
    }
    if mode == "wsl":
        distribution = selected.get(
            "wsl_distribution",
            launch["wsl"]["distribution_default"],
        )
        if not isinstance(distribution, str) or not distribution:
            runner.close()
            return blocked("codex_cli_boundary_unsupported")
        controls["wsl_distribution"] = distribution
        resolved_controls["wsl_distribution"] = distribution

    try:
        env = runner._environment()
        launch_environment, launch_error = runner._resolve_launch_environment(
            controls,
            Path.cwd(),
            env,
            min(timeout_ms, 10000),
        )
        if launch_error or launch_environment is None:
            return blocked(launch_error or "codex_cli_boundary_unsupported")

        version, preflight_error = runner._preflight(
            launch_environment,
            Path.cwd(),
            env,
            min(timeout_ms, 10000),
        )
        launch_metadata = runner._launch_metadata(launch_environment)
        if preflight_error or version is None:
            return blocked(
                preflight_error or "codex_cli_version_unavailable",
                observed_runtime_version=version,
                launch_environment=launch_metadata,
            )
        discovery = registration["extensions"].get("arcgrav.adapters:model_discovery", {})
        if discovery.get("reasoning_effort_control") == "reasoning_effort":
            try:
                resolved_controls["reasoning_effort"] = runner._resolve_reasoning_effort(
                    launch_environment, model_id, selected.get("reasoning_effort"), env, timeout_ms,
                )
            except UnsupportedBoundaryError as exc:
                return blocked(exc.code, observed_runtime_version=version, launch_environment=launch_metadata)
        return {
            "status": "ready",
            "provider_submitted": False,
            "runtime_version": version,
            "provider_runtime": {
                "runtime_id": runner._runner_id,
                "runtime_version": retained_runtime_version(version),
                "provider": runtime_provider,
                "access_method": "cli",
                "model": model_id,
            },
            "resolved_controls": resolved_controls,
            "launch_environment": {"mode": mode, "executable": "runtime/codex"},
            "noninteractive_surface_verified": True,
        }
    except Exception:
        return blocked("codex_cli_isolation_failed")
    finally:
        runner.close()


def _bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace")
    return b""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
