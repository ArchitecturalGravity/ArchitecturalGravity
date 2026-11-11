"""Codex-compatible external surface for the provider-neutral mock model runtime.

This module owns only adapter-specific command and JSON-RPC compatibility. It
maps external Codex-style operations onto provider-neutral mock-model
operations and does not construct AgMark observations or choose runner terminal
states.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import sys
import tomllib
from uuid import uuid4
from typing import Any, BinaryIO, TextIO

from AgMark.shared.mock_model.protocol import (
    DEFAULT_RUNTIME_VERSION,
    MockRuntimeProtocol,
    ModelCatalogEntry,
    ModelProfileMapping,
    ProtocolInferenceError,
    ProtocolProbeError,
)
from AgMark.shared.mock_model.scenarios import (
    DISCOVERY_PROTOCOL_INVALID_SCENARIO,
    EXECUTION_REJECTION_SCENARIO,
    KNOWN_INFERENCE_SCENARIOS,
    KNOWN_PREFLIGHT_SCENARIOS,
)

PROGRAM_NAME = "arcgrav-mock-model-cli"
EXEC_CAPABILITY = "inference"
DEFAULT_CAPABILITIES = (
    EXEC_CAPABILITY,
    "model.discovery",
    "runtime.capabilities",
    "runtime.version",
)
BASE_MODEL_ID = "mock-base"
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
DEFAULT_REASONING_EFFORT = "medium"
SCENARIO_MODEL_ID_PREFIX = f"{BASE_MODEL_ID}::scenario:"
AUTHENTICATION_LIKE_MODEL_ID = (
    f"{SCENARIO_MODEL_ID_PREFIX}authentication_like_rejection"
)
PREFLIGHT_PROFILE_ENV = "ARCGRAV_MOCK_CLI_PREFLIGHT_PROFILE"
PREFLIGHT_TARGET_PROFILES = frozenset(KNOWN_PREFLIGHT_SCENARIOS)
_AUTHENTICATION_LIKE_DIAGNOSTIC = b"Not logged in; authentication required\n"
DEFAULT_MODELS = (
    ModelCatalogEntry(
        model_id=BASE_MODEL_ID,
        label="Mock Base",
        is_default=True,
    ),
    *(
        ModelCatalogEntry(
            model_id=f"{SCENARIO_MODEL_ID_PREFIX}{scenario_id}",
            label=f"Mock Base / {scenario_id}",
            profile=ModelProfileMapping(
                base_model_id=BASE_MODEL_ID,
                scenario_id=scenario_id,
            ),
        )
        for scenario_id in sorted(KNOWN_INFERENCE_SCENARIOS)
    ),
    ModelCatalogEntry(
        model_id=AUTHENTICATION_LIKE_MODEL_ID,
        label="Mock Base / authentication-like rejection",
        profile=ModelProfileMapping(
            base_model_id=BASE_MODEL_ID,
            scenario_id=EXECUTION_REJECTION_SCENARIO,
        ),
    ),
)

_APP_SERVER_ARGS = ("app-server", "--listen", "stdio://")
_EXEC_SUFFIX = (
    "--approve-for-me",
    "--ephemeral",
    "--ignore-user-config",
    "--skip-git-repo-check",
    "--color",
    "never",
    "-",
)
_CURSOR_PREFIX = "offset:"
_JSONRPC_PARSE_ERROR = -32700
_JSONRPC_INVALID_REQUEST = -32600
_JSONRPC_METHOD_NOT_FOUND = -32601
_JSONRPC_INVALID_PARAMS = -32602
_JSONRPC_SERVER_ERROR = -32000

_EXEC_HELP = f"""Usage: {PROGRAM_NAME} exec [OPTIONS] -

Non-interactive mock-model execution surface.

Options:
  --model <MODEL_ID>         Select one discovered canonical model identifier.
  -c model_reasoning_effort=<JSON_STRING>  Select discovered reasoning effort.
  --approve-for-me           Accepted compatibility flag.
  --ephemeral                Skip persisted session records.
  --ignore-user-config       Ignore ambient user configuration.
  --skip-git-repo-check      Do not require a repository worktree.
  --color <WHEN>             Output-color compatibility selector.
  --json                     Emit synthetic exec JSONL events.
  --help                     Show this help message and exit.
"""


def _default_protocol(
    *,
    preflight_profile_id: str | None = None,
) -> MockRuntimeProtocol:
    if (
        preflight_profile_id is not None
        and preflight_profile_id not in PREFLIGHT_TARGET_PROFILES
    ):
        raise ValueError(
            f"unsupported compatibility preflight profile: {preflight_profile_id}"
        )
    return MockRuntimeProtocol(
        capabilities=DEFAULT_CAPABILITIES,
        models=DEFAULT_MODELS,
        preflight_scenario_id=preflight_profile_id,
    )


def _read_exact_bytes(stream: TextIO | BinaryIO) -> bytes:
    """Read exact process bytes when a binary buffer is available."""

    buffer = getattr(stream, "buffer", None)
    value = buffer.read() if buffer is not None else stream.read()
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError("stdin stream must return str or bytes")


def _write_exact_bytes(stream: TextIO | BinaryIO, value: bytes) -> None:
    """Write exact process bytes when a binary buffer is available."""

    if not value:
        return
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(value)
        buffer.flush()
        return
    try:
        stream.write(value)  # type: ignore[arg-type]
    except TypeError:
        stream.write(value.decode("utf-8", errors="replace"))  # type: ignore[arg-type]
    stream.flush()


def _exec_selection(args: tuple[str, ...]) -> tuple[str, str] | None:
    effort = DEFAULT_REASONING_EFFORT
    seen = set()
    # The production runner supplies stock capture configuration in addition to
    # model controls. Accept its declared wire surface without fabricating any
    # provider telemetry: absent mock exporter data remains unavailable.
    telemetry_keys = {"otel.log_user_prompt", "otel.log_agent_responses",
        "otel.log_guardian_assessments", "otel.tool_result.max_bytes",
        "otel.exporter", "otel.trace_exporter", "otel.metrics_exporter",
        "otel.span_attributes"}
    while "-c" in args:
        index = args.index("-c")
        if index + 1 >= len(args):
            return None
        key, separator, encoded = args[index + 1].partition("=")
        if not separator or key in seen:
            return None
        seen.add(key)
        if key == "model_reasoning_effort":
            try:
                effort = json.loads(encoded)
            except (ValueError, TypeError):
                return None
            if not isinstance(effort, str) or effort not in REASONING_EFFORTS:
                return None
        elif key in telemetry_keys:
            try:
                tomllib.loads(args[index + 1])
            except tomllib.TOMLDecodeError:
                return None
        else:
            return None
        args = args[:index] + args[index + 2:]
    if args[-2:] == ("--json", "-"):
        args = (*args[:-2], "-")
    if len(args) not in {9, 10} or args[:2] != ("exec", "--model"):
        return None
    model_id = args[2]
    persisted_suffix = tuple(arg for arg in _EXEC_SUFFIX if arg != "--ephemeral")
    if not model_id.strip() or args[3:] not in {_EXEC_SUFFIX, persisted_suffix}:
        return None
    return model_id, effort


def _exec_invocation_id(model_id: str, request_bytes: bytes) -> str:
    digest = hashlib.sha256()
    for value in (model_id.encode("utf-8"), request_bytes):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return f"{PROGRAM_NAME}:exec:{digest.hexdigest()}"


def _write_inference_failure(
    error: ProtocolInferenceError,
    stderr: TextIO | BinaryIO,
) -> None:
    diagnostic = error.diagnostic or error.code.encode("utf-8")
    if not diagnostic.endswith(b"\n"):
        diagnostic += b"\n"
    _write_exact_bytes(stderr, diagnostic)


def _run_exec(
    runtime: MockRuntimeProtocol,
    *,
    model_id: str,
    stdin: TextIO | BinaryIO,
    stdout: TextIO | BinaryIO,
    stderr: TextIO | BinaryIO,
    json_output: bool = False,
    persist_session: bool = False,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> int:
    request_bytes = _read_exact_bytes(stdin)
    thread_id = str(uuid4())
    session_path = None
    if persist_session:
        user_home = os.environ.get("USERPROFILE") if os.name == "nt" else os.environ.get("HOME")
        codex_home = Path(os.environ.get("CODEX_HOME") or str(Path(user_home or Path.home()) / ".codex"))
        now = datetime.now(timezone.utc)
        directory = codex_home / "sessions" / now.strftime("%Y/%m/%d")
        directory.mkdir(parents=True, exist_ok=True)
        session_path = directory / f"rollout-{now.strftime('%Y-%m-%dT%H-%M-%S')}-{thread_id}.jsonl"

    def record(kind, payload):
        if session_path is not None:
            entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "type": kind, "payload": payload}
            with session_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    record("session_meta", {"id": thread_id, "cwd": str(Path.cwd()), "cli_version": DEFAULT_RUNTIME_VERSION})
    record("turn_context", {"model": model_id, "effort": reasoning_effort})
    record("response_item", {"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": request_bytes.decode("utf-8", errors="replace")}]})
    record("event_msg", {"type": "task_started", "model_context_window": 8192})
    if json_output:
        _write_json_line(stdout, {"type": "thread.started", "thread_id": thread_id})
        _write_json_line(stdout, {"type": "turn.started"})

    def stream_partial_output(partial_stdout: bytes, partial_stderr: bytes) -> None:
        if json_output and partial_stdout:
            _write_json_line(stdout, {"type": "item.started", "item": {
                "id": "mock-message", "type": "agent_message", "text": partial_stdout.decode("utf-8")}})
        else:
            _write_exact_bytes(stdout, partial_stdout)
        _write_exact_bytes(stderr, partial_stderr)

    try:
        result = runtime.infer(
            model_id=model_id,
            request_bytes=request_bytes,
            invocation_id=_exec_invocation_id(model_id, request_bytes),
            partial_output_sink=stream_partial_output,
        )
    except ProtocolInferenceError as exc:
        record("event_msg", {"type": "turn_aborted"})
        _write_inference_failure(exc, stderr)
        if json_output:
            _write_json_line(stdout, {"type": "turn.failed", "error": {"message": exc.code}})
        return 2

    if result.exit_code == 0:
        record("event_msg", {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 40, "cached_input_tokens": 10,
                "cache_write_input_tokens": 0, "output_tokens": 2, "reasoning_output_tokens": 0, "total_tokens": 42},
            "last_token_usage": {"output_tokens": 2}, "model_context_window": 8192}})
    record("event_msg", {"type": "task_complete"})
    if json_output:
        if result.stdout:
            _write_json_line(stdout, {"type": "item.completed", "item": {
                "id": "mock-message", "type": "agent_message", "text": result.stdout.decode("utf-8")}})
        if result.exit_code == 0:
            # Fixed synthetic runtime counters, never provider billing usage.
            _write_json_line(stdout, {"type": "turn.completed", "usage": {
                "input_tokens": 40, "cached_input_tokens": 10,
                "output_tokens": 2, "reasoning_output_tokens": 0}})
        else:
            _write_json_line(stdout, {"type": "turn.failed", "error": {"message": "mock process failed"}})
    else:
        _write_exact_bytes(stdout, result.stdout)
    _write_exact_bytes(stderr, result.stderr)
    if result.exit_code == 0:
        # A fixed synthetic runtime counter exercises production extraction;
        # this is no provider billing or performance measurement.
        _write_exact_bytes(stderr, b"\ntokens used\n42\n")
    if model_id == AUTHENTICATION_LIKE_MODEL_ID and result.exit_code != 0:
        _write_exact_bytes(stderr, _AUTHENTICATION_LIKE_DIAGNOSTIC)
    return result.exit_code


def _write_probe_failure(error: ProtocolProbeError, stderr: TextIO) -> None:
    if error.diagnostic:
        stderr.write(error.diagnostic.decode("utf-8", errors="replace"))
        if not error.diagnostic.endswith(b"\n"):
            stderr.write("\n")
        return
    stderr.write(f"{error.code}\n")


def _write_json_line(stdout: TextIO, message: Mapping[str, Any]) -> None:
    _write_exact_bytes(stdout, (json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8"))


def _error_response(
    request_id: object,
    code: int,
    message: str,
) -> dict[str, object]:
    return {
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _request_id(message: Mapping[str, Any]) -> object:
    return message["id"] if "id" in message else None


def _decode_cursor(value: object, *, model_count: int) -> int:
    if value is None:
        return 0
    if not isinstance(value, str) or not value.startswith(_CURSOR_PREFIX):
        raise ValueError("cursor must be a compatibility pagination cursor")
    raw_offset = value[len(_CURSOR_PREFIX) :]
    if not raw_offset.isdecimal():
        raise ValueError("cursor must be a compatibility pagination cursor")
    offset = int(raw_offset)
    if offset <= 0 or offset >= model_count:
        raise ValueError("cursor is outside the model catalog")
    return offset


def _model_list_result(
    runtime: MockRuntimeProtocol,
    params: Mapping[str, Any],
) -> dict[str, object]:
    include_hidden = params.get("includeHidden", False)
    limit = params.get("limit", 1000)
    cursor = params.get("cursor")

    if type(include_hidden) is not bool:
        raise ValueError("includeHidden must be boolean")
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")

    catalog = runtime.discover_models()
    models = tuple(
        model
        for model in catalog.models
        if include_hidden or not model.hidden
    )
    offset = _decode_cursor(cursor, model_count=len(models))
    selected = models[offset : offset + limit]
    next_offset = offset + len(selected)
    next_cursor = (
        f"{_CURSOR_PREFIX}{next_offset}"
        if next_offset < len(models)
        else None
    )

    return {
        "data": [
            {
                "model": model.model_id,
                "displayName": model.label,
                "supportedReasoningEfforts": [
                    {"reasoningEffort": effort, "description": f"Synthetic {effort} reasoning effort"}
                    for effort in REASONING_EFFORTS],
                "defaultReasoningEffort": DEFAULT_REASONING_EFFORT,
                "hidden": model.hidden,
                "isDefault": model.model_id == catalog.default_model_id,
                "scenario": {
                    "scenario_id": (
                        "authentication_like_rejection" if model.model_id == AUTHENTICATION_LIKE_MODEL_ID
                        else model.profile.scenario_id if model.profile is not None
                        else "default"
                    ),
                    "label": (
                        "Authentication-like rejection" if model.model_id == AUTHENTICATION_LIKE_MODEL_ID
                        else model.profile.scenario_id.replace("_", " ").capitalize() if model.profile is not None
                        else "Default response"
                    ),
                    "base_model_id": model.profile.base_model_id if model.profile is not None else model.model_id,
                    "model_id": model.model_id,
                    "is_default": model.model_id == catalog.default_model_id,
                },
            }
            for model in selected
        ],
        "nextCursor": next_cursor,
    }


def _run_app_server(
    runtime: MockRuntimeProtocol,
    *,
    stdin: TextIO,
    stdout: TextIO,
    preflight_profile_id: str | None = None,
) -> int:
    initialized = False
    initialized_notification = False

    for raw_line in stdin:
        if not raw_line.strip():
            continue
        try:
            decoded = json.loads(raw_line)
        except json.JSONDecodeError:
            _write_json_line(
                stdout,
                _error_response(None, _JSONRPC_PARSE_ERROR, "Parse error"),
            )
            continue

        if not isinstance(decoded, Mapping):
            _write_json_line(
                stdout,
                _error_response(None, _JSONRPC_INVALID_REQUEST, "Invalid Request"),
            )
            continue

        request_id = _request_id(decoded)
        method = decoded.get("method")
        params = decoded.get("params", {})
        if not isinstance(method, str) or not method:
            _write_json_line(
                stdout,
                _error_response(
                    request_id,
                    _JSONRPC_INVALID_REQUEST,
                    "Invalid Request",
                ),
            )
            continue
        if not isinstance(params, Mapping):
            if "id" in decoded:
                _write_json_line(
                    stdout,
                    _error_response(
                        request_id,
                        _JSONRPC_INVALID_PARAMS,
                        "Invalid params",
                    ),
                )
            continue

        if method == "initialize":
            if "id" not in decoded:
                _write_json_line(
                    stdout,
                    _error_response(
                        None,
                        _JSONRPC_INVALID_REQUEST,
                        "initialize requires a request id",
                    ),
                )
                continue
            try:
                identity = runtime.runtime_identity()
            except ProtocolProbeError as exc:
                _write_json_line(
                    stdout,
                    _error_response(
                        request_id,
                        _JSONRPC_SERVER_ERROR,
                        exc.code,
                    ),
                )
                continue
            initialized = True
            initialized_notification = False
            _write_json_line(
                stdout,
                {
                    "id": request_id,
                    "result": {
                        "capabilities": {},
                        "serverInfo": {
                            "name": PROGRAM_NAME,
                            "title": "ArcGrav Mock Model CLI",
                            "version": identity.runtime_version,
                        },
                    },
                },
            )
            continue

        if method == "initialized":
            if initialized:
                initialized_notification = True
            continue

        if method == "model/list":
            if "id" not in decoded:
                _write_json_line(
                    stdout,
                    _error_response(
                        None,
                        _JSONRPC_INVALID_REQUEST,
                        "model/list requires a request id",
                    ),
                )
                continue
            if not initialized or not initialized_notification:
                _write_json_line(
                    stdout,
                    _error_response(
                        request_id,
                        _JSONRPC_SERVER_ERROR,
                        "server is not initialized",
                    ),
                )
                continue
            try:
                result = _model_list_result(runtime, params)
            except ProtocolProbeError as exc:
                if (
                    preflight_profile_id == DISCOVERY_PROTOCOL_INVALID_SCENARIO
                    and exc.code == "protocol_invalid_result"
                    and exc.diagnostic
                ):
                    _write_exact_bytes(stdout, exc.diagnostic)
                else:
                    _write_json_line(
                        stdout,
                        _error_response(
                            request_id,
                            _JSONRPC_SERVER_ERROR,
                            exc.code,
                        ),
                    )
            except ValueError as exc:
                _write_json_line(
                    stdout,
                    _error_response(
                        request_id,
                        _JSONRPC_INVALID_PARAMS,
                        str(exc),
                    ),
                )
            else:
                _write_json_line(stdout, {"id": request_id, "result": result})
            continue

        if "id" in decoded:
            _write_json_line(
                stdout,
                _error_response(
                    request_id,
                    _JSONRPC_METHOD_NOT_FOUND,
                    "Method not found",
                ),
            )

    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    protocol: MockRuntimeProtocol | None = None,
    stdin: TextIO | BinaryIO | None = None,
    stdout: TextIO | BinaryIO | None = None,
    stderr: TextIO | BinaryIO | None = None,
) -> int:
    """Run one adapter-owned compatibility command."""

    args = tuple(sys.argv[1:] if argv is None else argv)
    inp = stdin or sys.stdin
    out = stdout or sys.stdout
    err = stderr or sys.stderr

    preflight_profile_id: str | None = None
    if protocol is None:
        configured_profile = os.environ.get(PREFLIGHT_PROFILE_ENV)
        if configured_profile is not None and configured_profile.strip():
            preflight_profile_id = configured_profile.strip()
        try:
            runtime = _default_protocol(
                preflight_profile_id=preflight_profile_id,
            )
        except ValueError as exc:
            err.write(f"{PROGRAM_NAME}: {exc}\n")
            return 2
    else:
        runtime = protocol

    if args == ("--version",):
        try:
            identity = runtime.runtime_identity()
        except ProtocolProbeError as exc:
            _write_probe_failure(exc, err)
            return 1
        out.write(f"{PROGRAM_NAME} {identity.runtime_version}\n")
        return 0

    if args == ("exec", "--help"):
        try:
            capabilities = runtime.inspect_capabilities()
        except ProtocolProbeError as exc:
            _write_probe_failure(exc, err)
            return 1
        if EXEC_CAPABILITY not in capabilities.capabilities:
            err.write("non-interactive execution capability unavailable\n")
            return 1
        out.write(_EXEC_HELP)
        return 0

    if args == _APP_SERVER_ARGS:
        return _run_app_server(
            runtime,
            stdin=inp,
            stdout=out,
            preflight_profile_id=preflight_profile_id,
        )

    selection = _exec_selection(args)
    if selection is not None:
        model_id, reasoning_effort = selection
        return _run_exec(
            runtime,
            model_id=model_id,
            stdin=inp,
            stdout=out,
            stderr=err,
            json_output="--json" in args,
            persist_session="--ephemeral" not in args,
            reasoning_effort=reasoning_effort,
        )

    err.write(f"{PROGRAM_NAME}: unsupported command\n")
    return 2


__all__ = [
    "AUTHENTICATION_LIKE_MODEL_ID",
    "BASE_MODEL_ID",
    "DEFAULT_CAPABILITIES",
    "DEFAULT_MODELS",
    "EXEC_CAPABILITY",
    "PREFLIGHT_PROFILE_ENV",
    "PREFLIGHT_TARGET_PROFILES",
    "PROGRAM_NAME",
    "SCENARIO_MODEL_ID_PREFIX",
    "main",
]
