"""Non-submitting Codex CLI model discovery and session projection."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from queue import Empty, Queue
import subprocess
import threading
import time
from typing import Any

from .runner import (
    _registered_executable_resolver,
    _registered_wsl_target_executable,
    _wsl_cli_argv,
)


_LAUNCH_ENVIRONMENT = "arcgrav.adapters:launch_environment"
_INITIALIZE_ID = "arcgrav-initialize"
_MODEL_LIST_ID = "arcgrav-model-list"
_CLIENT_INFO = {
    "name": "arcgrav_benchmarking",
    "title": "AgMark",
    "version": "1.1.0",
}
_WSL_SESSION_SCRIPT = r"""
set -eu
user="$(id -un)"
home="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6)"
if [ -z "${home:-}" ]; then
    home="${HOME:-}"
fi
printf '%s\n%s\n' "$user" "$home"
""".strip()


class ModelDiscoveryError(ValueError):
    """Raised when registered Codex model-discovery evidence is unusable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _encode_json_line(message: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _batch_request() -> bytes:
    messages = (
        {
            "id": _INITIALIZE_ID,
            "method": "initialize",
            "params": {
                "clientInfo": dict(_CLIENT_INFO),
                "capabilities": {
                    "experimentalApi": True,
                    "requestAttestation": False,
                },
            },
        },
        {"method": "initialized"},
        {
            "id": _MODEL_LIST_ID,
            "method": "model/list",
            "params": {"includeHidden": False, "limit": 1000},
        },
    )
    return b"".join(_encode_json_line(message) for message in messages)


def _pipe_reader(stream: Any, destination: Queue[bytes | None]) -> None:
    try:
        while True:
            line = stream.readline()
            if not line:
                return
            destination.put(line)
    except Exception:
        # A complete catalog is not trustworthy if its output stream could
        # not be read through process shutdown.
        destination.put(None)


def _response_from_line(line: bytes) -> Mapping[str, Any] | None:
    try:
        decoded = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _record_response_id(
    message: Mapping[str, Any],
    seen_response_ids: set[str],
    allowed_response_ids: set[str],
) -> str | None:
    """Accept notifications and only responses to this client's requests."""

    if "id" not in message:
        if (
            not isinstance(message.get("method"), str)
            or not message["method"].strip()
            or "result" in message
            or "error" in message
        ):
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex app-server emitted an invalid JSON-RPC notification",
            )
        return None
    response_id = message["id"]
    if isinstance(response_id, str) and response_id in seen_response_ids:
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex app-server repeated a JSON-RPC response id",
        )
    if not isinstance(response_id, str) or response_id not in allowed_response_ids:
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex app-server emitted an unexpected JSON-RPC response id",
        )
    seen_response_ids.add(response_id)
    return response_id


def _wait_for_response(
    process: subprocess.Popen[bytes],
    stdout_queue: Queue[bytes | None],
    stdout_reader: threading.Thread | None,
    stderr_queue: Queue[bytes | None],
    stdout_lines: list[bytes],
    stderr_lines: list[bytes],
    seen_response_ids: set[str],
    request_id: str,
    *,
    deadline: float,
) -> Mapping[str, Any]:
    while time.monotonic() < deadline:
        while True:
            try:
                stderr_line = stderr_queue.get_nowait()
                if stderr_line is None:
                    raise ModelDiscoveryError(
                        "codex_cli_model_catalog_unavailable",
                        "Codex app-server error output could not be read",
                    )
                stderr_lines.append(stderr_line)
            except Empty:
                break
        remaining = max(0.01, min(0.1, deadline - time.monotonic()))
        try:
            line = stdout_queue.get(timeout=remaining)
        except Empty:
            # Process exit can precede the reader's final queue.put(). Wait
            # for the pipe reader to finish before concluding no reply exists.
            exit_code = process.poll()
            if exit_code is not None and (
                stdout_reader is None or not stdout_reader.is_alive()
            ) and stdout_queue.empty():
                raise ModelDiscoveryError(
                    "codex_cli_model_catalog_unavailable",
                    f"Codex app-server exited before answering {request_id} "
                    f"(exit code {exit_code}); check the selected Codex executable",
                )
            continue
        if line is None:
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex app-server output could not be read",
            )
        stdout_lines.append(line)
        message = _response_from_line(line)
        if message is None:
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex app-server emitted invalid JSON-RPC output",
            )
        response_id = _record_response_id(
            message, seen_response_ids, {request_id}
        )
        if response_id == request_id:
            return message
    raise ModelDiscoveryError(
        "codex_cli_model_catalog_unavailable",
        f"Codex app-server did not answer {request_id}",
    )


def _run_interactive_model_list(
    argv: tuple[str, ...],
    *,
    cwd: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None,
    timeout: float,
) -> Mapping[str, Any]:
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=dict(env) if env is not None else None,
    )
    stdout_queue: Queue[bytes | None] = Queue()
    stderr_queue: Queue[bytes | None] = Queue()
    stdout_lines: list[bytes] = []
    stderr_lines: list[bytes] = []
    seen_response_ids: set[str] = set()
    stdout_reader: threading.Thread | None = None
    stderr_reader: threading.Thread | None = None
    if process.stdout is not None:
        stdout_reader = threading.Thread(
            target=_pipe_reader,
            args=(process.stdout, stdout_queue),
            daemon=True,
        )
        stdout_reader.start()
    if process.stderr is not None:
        stderr_reader = threading.Thread(
            target=_pipe_reader,
            args=(process.stderr, stderr_queue),
            daemon=True,
        )
        stderr_reader.start()

    deadline = time.monotonic() + timeout
    catalog_complete = False

    def send(message: Mapping[str, Any]) -> None:
        if process.stdin is None:
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex app-server stdin is unavailable",
            )
        process.stdin.write(_encode_json_line(message))
        process.stdin.flush()

    try:
        send(
            {
                "id": _INITIALIZE_ID,
                "method": "initialize",
                "params": {
                    "clientInfo": dict(_CLIENT_INFO),
                    "capabilities": {
                        "experimentalApi": True,
                        "requestAttestation": False,
                    },
                },
            }
        )
        initialized = _wait_for_response(
            process,
            stdout_queue,
            stdout_reader,
            stderr_queue,
            stdout_lines,
            stderr_lines,
            seen_response_ids,
            _INITIALIZE_ID,
            deadline=deadline,
        )
        if "error" in initialized or not isinstance(initialized.get("result"), Mapping):
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex app-server initialization failed",
            )
        send({"method": "initialized"})

        data: list[object] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        page = 0
        while True:
            page += 1
            request_id = f"{_MODEL_LIST_ID}-{page}"
            params: dict[str, object] = {
                "includeHidden": False,
                "limit": 1000,
            }
            if cursor is not None:
                params["cursor"] = cursor
            send(
                {
                    "id": request_id,
                    "method": "model/list",
                    "params": params,
                }
            )
            response = _wait_for_response(
                process,
                stdout_queue,
                stdout_reader,
                stderr_queue,
                stdout_lines,
                stderr_lines,
                seen_response_ids,
                request_id,
                deadline=deadline,
            )
            result = response.get("result")
            if "error" in response or not isinstance(result, Mapping):
                raise ModelDiscoveryError(
                    "codex_cli_model_catalog_unavailable",
                    "Codex app-server model/list failed",
                )
            page_data = result.get("data")
            if isinstance(page_data, (str, bytes)) or not isinstance(page_data, list):
                raise ModelDiscoveryError(
                    "codex_cli_model_catalog_unavailable",
                    "Codex model/list returned invalid model data",
                )
            data.extend(page_data)
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise ModelDiscoveryError(
                    "codex_cli_model_catalog_unavailable",
                    "Codex model/list returned an invalid cursor",
                )
            if next_cursor in seen_cursors:
                raise ModelDiscoveryError(
                    "codex_cli_model_catalog_unavailable",
                    "Codex model/list repeated a cursor",
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        catalog_complete = True
        return {"data": data, "nextCursor": None}
    finally:
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            try:
                exit_code = process.wait(
                    timeout=max(0.1, min(2.0, deadline - time.monotonic()))
                )
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
                # A complete catalog cannot authorize discovery if the external
                # app-server remains alive after its input is closed. Preserve any
                # earlier protocol failure when cleanup follows an incomplete read.
                if catalog_complete:
                    raise ModelDiscoveryError(
                        "codex_cli_model_catalog_unavailable",
                        "Codex app-server did not exit after model discovery",
                    )
            else:
                # A valid catalog is not successful discovery if the external
                # target subsequently exits unsuccessfully. Keep prior protocol
                # failures authoritative rather than masking them during cleanup.
                if catalog_complete and (type(exit_code) is not int or exit_code != 0):
                    raise ModelDiscoveryError(
                        "codex_cli_model_catalog_unavailable",
                        "Codex app-server exited unsuccessfully",
                    )
                if catalog_complete and stdout_reader is not None:
                    stdout_reader.join(timeout=1.0)
                    if stdout_reader.is_alive():
                        raise ModelDiscoveryError(
                            "codex_cli_model_catalog_unavailable",
                            "Codex app-server output did not close",
                        )
                    while True:
                        try:
                            line = stdout_queue.get_nowait()
                        except Empty:
                            break
                        if line is None:
                            raise ModelDiscoveryError(
                                "codex_cli_model_catalog_unavailable",
                                "Codex app-server output could not be read",
                            )
                        message = _response_from_line(line)
                        if message is None:
                            raise ModelDiscoveryError(
                                "codex_cli_model_catalog_unavailable",
                                "Codex app-server emitted invalid JSON-RPC output",
                            )
                        _record_response_id(message, seen_response_ids, set())
                if catalog_complete:
                    if stderr_reader is not None:
                        stderr_reader.join(timeout=1.0)
                        if stderr_reader.is_alive():
                            raise ModelDiscoveryError(
                                "codex_cli_model_catalog_unavailable",
                                "Codex app-server error output did not close",
                            )
                    while True:
                        try:
                            stderr_line = stderr_queue.get_nowait()
                        except Empty:
                            break
                        if stderr_line is None:
                            raise ModelDiscoveryError(
                                "codex_cli_model_catalog_unavailable",
                                "Codex app-server error output could not be read",
                            )
        finally:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def _decode_batch_model_list(stdout: bytes) -> Mapping[str, Any]:
    if not isinstance(stdout, bytes):
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex app-server output must be bytes",
        )
    initialize: Mapping[str, Any] | None = None
    model_list: Mapping[str, Any] | None = None
    seen_response_ids: set[str] = set()
    for raw_line in stdout.splitlines():
        if not raw_line.strip():
            continue
        message = _response_from_line(raw_line)
        if message is None:
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex app-server emitted invalid JSON-RPC output",
            )
        response_id = _record_response_id(
            message, seen_response_ids, {_INITIALIZE_ID, _MODEL_LIST_ID}
        )
        if response_id == _INITIALIZE_ID:
            initialize = message
        elif response_id == _MODEL_LIST_ID:
            if initialize is None or "error" in initialize or not isinstance(
                initialize.get("result"), Mapping
            ):
                raise ModelDiscoveryError(
                    "codex_cli_model_catalog_unavailable",
                    "Codex app-server returned model/list before initialization",
                )
            model_list = message
    if (
        initialize is None
        or "error" in initialize
        or not isinstance(initialize.get("result"), Mapping)
    ):
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex app-server initialization did not succeed",
        )
    if (
        model_list is None
        or "error" in model_list
        or not isinstance(model_list.get("result"), Mapping)
    ):
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex app-server model/list did not succeed",
        )
    return model_list["result"]


def decode_model_list_response(result: Mapping[str, Any]) -> dict[str, Any]:
    """Project a complete Codex model/list result into GUI choices."""

    if not isinstance(result, Mapping):
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex model/list result must be an object",
        )
    if result.get("nextCursor") is not None:
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex model/list result is incomplete",
        )
    raw_models = result.get("data")
    if isinstance(raw_models, (str, bytes)) or not isinstance(raw_models, list):
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex model/list result has no model data",
        )

    models: list[dict[str, object]] = []
    defaults: list[str] = []
    hidden_default = False
    seen: set[str] = set()
    for raw in raw_models:
        if not isinstance(raw, Mapping):
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex model/list entry is not an object",
            )
        model_id = raw.get("model")
        display_name = raw.get("displayName")
        hidden = raw.get("hidden", False)
        is_default = raw.get("isDefault", False)
        if (
            not isinstance(model_id, str)
            or not model_id.strip()
            or not isinstance(display_name, str)
            or not display_name.strip()
            or type(hidden) is not bool
            or type(is_default) is not bool
        ):
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex model/list entry is incomplete",
            )
        if model_id in seen:
            raise ModelDiscoveryError(
                "codex_cli_model_catalog_unavailable",
                "Codex model/list contains duplicate model identifiers",
            )
        seen.add(model_id)
        if hidden:
            hidden_default = hidden_default or is_default
            continue
        if is_default:
            defaults.append(model_id)
        item = {"model_id": model_id, "display_name": display_name}
        if "supportedReasoningEfforts" in raw or "defaultReasoningEffort" in raw:
            efforts = raw.get("supportedReasoningEfforts")
            default_effort = raw.get("defaultReasoningEffort")
            if not isinstance(efforts, list) or not efforts:
                raise ModelDiscoveryError(
                    "codex_cli_reasoning_catalog_unavailable",
                    "Codex model has no usable reasoning effort options",
                )
            options = []
            for effort in efforts:
                if (not isinstance(effort, Mapping)
                        or not isinstance(effort.get("reasoningEffort"), str)
                        or not effort["reasoningEffort"].strip()
                        or not isinstance(effort.get("description"), str)):
                    raise ModelDiscoveryError(
                        "codex_cli_reasoning_catalog_unavailable",
                        "Codex reasoning effort option is incomplete",
                    )
                options.append({"value": effort["reasoningEffort"],
                                "description": effort["description"]})
            values = [option["value"] for option in options]
            if len(set(values)) != len(values) or default_effort not in values:
                raise ModelDiscoveryError(
                    "codex_cli_reasoning_catalog_unavailable",
                    "Codex reasoning effort default or options are ambiguous",
                )
            item["reasoning_efforts"] = options
            item["default_reasoning_effort"] = default_effort
        # Preserve declared projection data verbatim; no runner scenario semantics.
        if "scenario" in raw:
            item["scenario"] = raw["scenario"]
        models.append(item)

    if not models:
        raise ModelDiscoveryError(
            "codex_cli_model_catalog_unavailable",
            "Codex model/list returned no selectable models",
        )
    if hidden_default:
        raise ModelDiscoveryError(
            "codex_cli_default_model_unresolved",
            "Codex model/list default model is not selectable",
        )
    if len(defaults) > 1:
        raise ModelDiscoveryError(
            "codex_cli_default_model_unresolved",
            "Codex model/list returned multiple default models",
        )
    if not defaults:
        raise ModelDiscoveryError(
            "codex_cli_default_model_unresolved",
            "Codex model/list did not identify a default model",
        )
    effective_default = defaults[0]
    by_id = {str(item["model_id"]): item for item in models}
    default_item = by_id[effective_default]

    label_counts: dict[str, int] = {}
    for item in models:
        label = str(item["display_name"])
        label_counts[label] = label_counts.get(label, 0) + 1

    choices: list[dict[str, Any]] = [
        {
            "model_id": effective_default,
            "selection_mode": "explicit",
            "label": f"Default ({default_item['display_name']})",
        }
    ]
    for item in models:
        model_id = str(item["model_id"])
        if model_id == effective_default:
            continue
        label = str(item["display_name"])
        if label_counts[label] > 1:
            label = f"{label} ({model_id})"
        choices.append(
            {
                "model_id": model_id,
                "selection_mode": "explicit",
                "label": label,
            }
        )

    for choice in choices:
        item = by_id[choice["model_id"]]
        if "scenario" in item:
            choice["scenario"] = item["scenario"]
        if "reasoning_efforts" in item:
            choice["reasoning_efforts"] = item["reasoning_efforts"]
            choice["default_reasoning_effort"] = item["default_reasoning_effort"]

    return {
        "effective_default_model_id": effective_default,
        "selectable_model_ids": [str(item["model_id"]) for item in models],
        "choices": choices,
    }


def _run(
    runner: Callable[..., object],
    argv: tuple[str, ...],
    *,
    input_bytes: bytes | None,
    cwd: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None,
    timeout: float,
) -> object:
    kwargs: dict[str, object] = {
        "input": input_bytes,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": timeout,
        "check": False,
    }
    if cwd is not None:
        kwargs["cwd"] = cwd
    if env is not None:
        kwargs["env"] = dict(env)
    return runner(argv, **kwargs)


def _anchor_resolved_executable(executable: str) -> str:
    """Bind a path-bearing resolver result before a different probe cwd is used."""

    if (
        not Path(executable).is_absolute()
        and not PureWindowsPath(executable).is_absolute()
        and ("/" in executable or "\\" in executable)
    ):
        return str(Path(executable).resolve())
    return executable


def _probe_wsl_session(
    launcher: str,
    distribution: str,
    *,
    runner: Callable[..., object],
    cwd: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None,
) -> dict[str, str]:
    try:
        completed = _run(
            runner,
            (
                launcher,
                "--distribution",
                distribution,
                "--exec",
                "sh",
                "-lc",
                _WSL_SESSION_SCRIPT,
            ),
            input_bytes=None,
            cwd=cwd,
            env=env,
            timeout=10.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ModelDiscoveryError(
            "codex_cli_wsl_session_unavailable",
            "The selected WSL user home could not be resolved",
        ) from exc
    if (
        type(getattr(completed, "returncode", None)) is not int
        or completed.returncode != 0
        or not isinstance(getattr(completed, "stderr", None), bytes)
    ):
        raise ModelDiscoveryError(
            "codex_cli_wsl_session_unavailable",
            "The selected WSL user home could not be resolved",
        )
    stdout = getattr(completed, "stdout", None)
    if not isinstance(stdout, bytes):
        raise ModelDiscoveryError(
            "codex_cli_wsl_session_unavailable",
            "The selected WSL user home could not be resolved",
        )
    try:
        lines = stdout.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise ModelDiscoveryError(
            "codex_cli_wsl_session_unavailable",
            "The selected WSL user home could not be resolved",
        ) from exc
    if (
        len(lines) != 2
        or not lines[0].strip()
        or not lines[1].strip()
        or not PurePosixPath(lines[1].strip()).is_absolute()
    ):
        raise ModelDiscoveryError(
            "codex_cli_wsl_session_unavailable",
            "The selected WSL user home could not be resolved",
        )
    user = lines[0].strip()
    home = lines[1].strip()
    codex_home = str(PurePosixPath(home) / ".codex")
    return {
        "wsl_user": user,
        "codex_home": codex_home,
    }


def _launch_command(
    registration: Mapping[str, Any],
    control_values: Mapping[str, object],
    *,
    executable_resolver: Callable[[str], str | None],
    platform_name: str,
    process_runner: Callable[..., object],
    process_cwd: str | os.PathLike[str] | None,
    process_env: Mapping[str, str] | None,
) -> tuple[tuple[str, ...], dict[str, str], dict[str, str]]:
    extensions = registration.get("extensions")
    if not isinstance(extensions, Mapping):
        raise ModelDiscoveryError(
            "codex_cli_boundary_unsupported",
            "runner registration has no extensions",
        )
    launch = extensions.get(_LAUNCH_ENVIRONMENT)
    if not isinstance(launch, Mapping):
        raise ModelDiscoveryError(
            "codex_cli_boundary_unsupported",
            "runner registration has no launch-environment authority",
        )
    supported_modes = launch.get("supported_modes")
    default_mode = "wsl" if platform_name == "nt" else "native"
    mode = control_values.get("launch_mode", default_mode)
    if (
        not isinstance(mode, str)
        or isinstance(supported_modes, (str, bytes))
        or not isinstance(supported_modes, list)
        or mode not in supported_modes
    ):
        raise ModelDiscoveryError(
            "codex_cli_boundary_unsupported",
            "selected launch mode is unsupported",
        )
    mode_config = launch.get(mode)
    if not isinstance(mode_config, Mapping):
        raise ModelDiscoveryError(
            "codex_cli_boundary_unsupported",
            "selected launch mode has no configuration",
        )
    codex_binary = control_values.get(
        "codex_binary",
        mode_config.get("codex_binary_default"),
    )
    if not isinstance(codex_binary, str) or not codex_binary:
        raise ModelDiscoveryError(
            "codex_cli_boundary_unsupported",
            "selected Codex executable is unresolved",
        )

    if mode == "native":
        try:
            executable = executable_resolver(codex_binary)
        except Exception:
            executable = None
        if not isinstance(executable, str) or not executable:
            raise ModelDiscoveryError(
                "codex_cli_executable_missing",
                "selected native Codex executable is unavailable",
            )
        # A resolver may return a path relative to the caller's directory.
        # Discovery can launch with a different cwd, so bind the resolved
        # executable before crossing that process boundary.
        executable = _anchor_resolved_executable(executable)
        codex_home = str(Path.home() / ".codex")
        return (
            executable,
            "app-server",
            "--listen",
            "stdio://",
        ), {
            "mode": "native",
            "executable": executable,
        }, {
            "codex_home": codex_home,
        }

    if platform_name != "nt":
        raise ModelDiscoveryError(
            "codex_cli_host_launcher_missing",
            "WSL model discovery requires a Windows host",
        )
    launcher_name = mode_config.get("launcher_default")
    distribution = control_values.get(
        "wsl_distribution",
        mode_config.get("distribution_default"),
    )
    if (
        not isinstance(launcher_name, str)
        or not launcher_name
        or not isinstance(distribution, str)
        or not distribution
    ):
        raise ModelDiscoveryError(
            "codex_cli_boundary_unsupported",
            "selected WSL launcher or distribution is unresolved",
        )
    try:
        launcher = executable_resolver(launcher_name)
    except Exception:
        launcher = None
    if not isinstance(launcher, str) or not launcher:
        raise ModelDiscoveryError(
            "codex_cli_host_launcher_missing",
            "selected WSL launcher is unavailable",
        )
    launcher = _anchor_resolved_executable(launcher)
    resolved_configuration = _probe_wsl_session(
        launcher,
        distribution,
        runner=process_runner,
        cwd=process_cwd,
        env=process_env,
    )
    executable = _registered_wsl_target_executable(registration, codex_binary)
    if executable is None:
        raise ModelDiscoveryError(
            "codex_cli_executable_missing",
            "selected WSL Codex executable is unavailable",
        )
    return _wsl_cli_argv(
        launcher,
        distribution,
        executable,
        ("app-server", "--listen", "stdio://"),
    ), {
        "mode": "wsl",
        "distribution": distribution,
        "executable": executable,
    }, resolved_configuration


def probe_model_discovery(
    registration: Mapping[str, Any],
    *,
    control_values: Mapping[str, object] | None = None,
    executable_resolver: Callable[[str], str | None] | None = None,
    process_runner: Callable[..., object] | None = None,
    platform_name: str | None = None,
    process_cwd: str | os.PathLike[str] | None = None,
    process_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Discover Codex picker models and resolved session paths without inference."""

    resolved_configuration: dict[str, str] = {}
    if not isinstance(registration, Mapping):
        return {
            "status": "unsupported",
            "error_code": "codex_cli_boundary_unsupported",
            "error_message": "Codex model-discovery boundary is unsupported",
            "provider_submitted": False,
            "resolved_configuration": resolved_configuration,
        }
    if control_values is not None and not isinstance(control_values, Mapping):
        return {
            "status": "unsupported",
            "error_code": "codex_cli_boundary_unsupported",
            "error_message": "Codex model-discovery boundary is unsupported",
            "provider_submitted": False,
            "resolved_configuration": resolved_configuration,
        }

    resolver = executable_resolver or _registered_executable_resolver(registration)
    runner = process_runner or subprocess.run
    platform = platform_name or os.name
    selected = dict(control_values or {})
    try:
        argv, launch_environment, resolved_configuration = _launch_command(
            registration,
            selected,
            executable_resolver=resolver,
            platform_name=platform,
            process_runner=runner,
            process_cwd=process_cwd,
            process_env=process_env,
        )
        if process_runner is None:
            model_list_result = _run_interactive_model_list(
                argv,
                cwd=process_cwd,
                env=process_env,
                timeout=10.0,
            )
        else:
            completed = _run(
                runner,
                argv,
                input_bytes=_batch_request(),
                cwd=process_cwd,
                env=process_env,
                timeout=10.0,
            )
            returncode = getattr(completed, "returncode", None)
            stdout = getattr(completed, "stdout", None)
            stderr = getattr(completed, "stderr", None)
            if (
                type(returncode) is not int
                or returncode != 0
                or not isinstance(stdout, bytes)
                or not isinstance(stderr, bytes)
            ):
                raise ModelDiscoveryError(
                    "codex_cli_model_catalog_unavailable",
                    "Codex app-server model discovery failed",
                )
            model_list_result = _decode_batch_model_list(stdout)
        projection = decode_model_list_response(model_list_result)
    except ModelDiscoveryError as exc:
        return {
            "status": "unsupported",
            "error_code": exc.code,
            "error_message": str(exc),
            "provider_submitted": False,
            "resolved_configuration": resolved_configuration,
        }
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return {
            "status": "unsupported",
            "error_code": "codex_cli_model_catalog_unavailable",
            "error_message": "Codex app-server model discovery failed",
            "provider_submitted": False,
            "resolved_configuration": resolved_configuration,
        }
    except Exception:
        return {
            "status": "unsupported",
            "error_code": "codex_cli_model_catalog_unavailable",
            "error_message": "Codex app-server model discovery failed",
            "provider_submitted": False,
            "resolved_configuration": resolved_configuration,
        }

    return {
        "status": "ready",
        "provider_submitted": False,
        "surface": {
            "kind": "codex_app_server_jsonrpc",
            "method": "model/list",
            "include_hidden": False,
        },
        "launch_environment": launch_environment,
        "resolved_configuration": resolved_configuration,
        "model_catalog_sha256": "sha256:" + hashlib.sha256(
            json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        **projection,
    }
