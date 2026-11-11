"""Dedicated mock runner using shared lifecycle helpers, never a provider adapter."""
from __future__ import annotations
import base64
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from collections.abc import Mapping

from .._contract import validate_runner_request, validate_boundary_support, UnsupportedBoundaryError
from ..execution import (TargetCompositionDescriptor, InvocationCapture, InvocationCancelled,
    TerminalExecutionResult, ExecutionFailureKind, execute_target, temporary_workdir_isolation,
    emit_terminal_observation)
from .catalog import RUNNER_ID, VERSION, MODELS


def load_registration():
    return json.loads(Path(__file__).with_name("registration.json").read_text(encoding="utf-8"))


class MockRunner:
    """Fresh local worker per observation with exact bytes and no persistent state."""
    supports_live_view = True
    supports_live_view_control = True

    def __init__(self, *, registration=None):
        self._registration = copy.deepcopy(registration if registration is not None else load_registration())
        if (self._registration.get("registration_id"), self._registration.get("registration_version")) != (RUNNER_ID, VERSION):
            raise ValueError("mock runner registration identity mismatch")
        self._closed = False

    def describe(self):
        extensions = self._registration["extensions"]
        return {"runner": {"id": RUNNER_ID, "version": VERSION},
            "contract": {"id": "arcgrav.shared.runner-invocation", "version": "2.0.0"},
            "registration": copy.deepcopy(self._registration),
            "supported_controls": {item["name"]: {k: v for k, v in item.items() if k != "name"}
                                   for item in extensions["arcgrav.adapters:supported_controls"]},
            "fixed_controls": {item["name"]: item["value"] for item in extensions["arcgrav.adapters:fixed_controls"]},
            "access_methods": copy.deepcopy(extensions["arcgrav.adapters:access_methods"]),
            "capabilities": list(self._registration["capabilities"]),
            "limitations": list(self._registration["limitations"]),
            "secret_handling": {"credentials_required": False, "transient_secrets_supported": False},
            "telemetry": {"provider_usage": False, "byte_measurements": True, "persisted_session": False}}

    def execute(self, request, *, cancellation_requested=None, event_callback=None, live_view_control=None):
        if self._closed:
            raise RuntimeError("runner is closed")
        validated = validate_runner_request(request)
        def present(channel, data):
            if channel == "output" and not data:
                return
            if callable(event_callback) and (live_view_control is None or live_view_control.snapshot()[0]):
                event = {"channel": channel, "text": data.decode("utf-8", errors="replace")}
                if live_view_control is not None:
                    event["stream_revision"] = live_view_control.snapshot()[1]
                try:
                    event_callback(event)
                except Exception:
                    pass  # Presentation cannot alter observation authority.

        fixed = self.describe()["fixed_controls"]
        controls = validated.boundary_controls
        framed = json.dumps({"protocol": "agmark.mock-worker/1", "model_id": controls.get("model_id"),
            "invocation_id": validated.observation_id,
            "prompt_base64": base64.b64encode(validated.prompt_bytes).decode("ascii"),
            "input_base64": base64.b64encode(validated.input_bytes).decode("ascii")},
            sort_keys=True, separators=(",", ":")).encode("utf-8")
        target = TargetCompositionDescriptor.create(target_class="mock-model",
            evidence_class="provider-free-mock-model-execution", runtime_id=RUNNER_ID,
            runtime_version=VERSION, access_method="local_process", external_provider_submission=False,
            launch_mode="native", launch_environment_selector={"worker_protocol": "agmark.mock-worker/1"},
            executable=sys.executable, authentication_class="not_applicable", compatibility_profile=None,
            production_runner_entry_point=self._registration["extensions"]["arcgrav.adapters:entry_point"],
            runner_implementation_artifact_ids=[item["artifact_id"] for item in self._registration["implementation_artifacts"]])
        error = None
        try:
            if (not isinstance(controls.get("model_id"), str)
                    or type(controls.get("maximum_attempts")) is not int
                    or controls.get("maximum_attempts") != 1):
                raise UnsupportedBoundaryError("mock_boundary_unsupported", "invalid model or retry control")
            validate_boundary_support(validated, runner_id=RUNNER_ID, runner_version=VERSION,
                supported_controls={"model_id": frozenset(m.model_id for m in MODELS),
                    "request_timeout_ms": None, "maximum_attempts": frozenset({1})},
                required_controls=frozenset({"model_id", "request_timeout_ms", "maximum_attempts"}),
                fixed_controls=fixed)
            timeout = controls["request_timeout_ms"]
            if type(timeout) is not int or timeout < 1:
                raise UnsupportedBoundaryError("mock_timeout_unsupported", "timeout must be positive integer")
            provider = validated.execution_boundary.get("provider_runtime", {})
            if (provider.get("runtime_id"), provider.get("runtime_version"), provider.get("access_method"), provider.get("model")) != (
                    RUNNER_ID, VERSION, "local_process", controls["model_id"]):
                raise UnsupportedBoundaryError("mock_runtime_unsupported", "runtime boundary differs")
        except UnsupportedBoundaryError as exc:
            error = exc.code
            now = datetime.now(timezone.utc).isoformat()
            execution = TerminalExecutionResult("unsupported", ExecutionFailureKind.PREFLIGHT_UNSUPPORTED,
                now, now, 0.0, False, InvocationCapture(False, None, None, b"", b""), None, None, False)
        else:
            if cancellation_requested and cancellation_requested():
                now = datetime.now(timezone.utc).isoformat()
                execution = TerminalExecutionResult("cancelled", ExecutionFailureKind.CANCELLED,
                    now, now, 0.0, False, InvocationCapture(False, None, None, b"", b""), None, None, False)
                return emit_terminal_observation(validated, target=target, execution=execution,
                    runner_id=RUNNER_ID, runner_version=VERSION, framed_request=framed,
                    request_framing_mode="mock_json_v1", usage_provider_reported=False,
                    usage_provenance="provider-free deterministic mock; no token or billing authority")
            # Deliberately do not inherit credentials, provider configuration,
            # session paths, or Python startup customization into the worker.
            environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
            root = Path(__file__).resolve().parents[4]
            bootstrap = "import sys; sys.path.insert(0, " + repr(str(root)) + "); from AgMark.shared.adapters.Mock_Model.worker import main; raise SystemExit(main())"
            command = (sys.executable, "-I", "-c", bootstrap)
            def before_invoke(context):
                if cancellation_requested and cancellation_requested():
                    raise KeyboardInterrupt
            def invoke(context, timeout_ms):
                present("input", validated.prompt_bytes + b"\n\n" + validated.input_bytes)
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, cwd=context.cwd, env=context.environment)
                deadline = time.monotonic() + timeout_ms / 1000
                payload = framed
                presented = 0
                try:
                    while True:
                        try:
                            stdout, stderr = process.communicate(input=payload, timeout=min(0.05, max(0.001, deadline-time.monotonic())))
                            present("output", stdout[presented:])
                            return InvocationCapture(process.returncode == 0, process.returncode, "local_process", stdout, stderr)
                        except subprocess.TimeoutExpired as pending:
                            partial = pending.output or b""
                            if len(partial) > presented:
                                present("output", partial[presented:])
                                presented = len(partial)
                            payload = None
                            if cancellation_requested and cancellation_requested():
                                process.kill(); stdout, stderr = process.communicate()
                                raise InvocationCancelled(stdout=stdout, stderr=stderr)
                            if time.monotonic() >= deadline:
                                process.kill(); stdout, stderr = process.communicate()
                                raise subprocess.TimeoutExpired(command, timeout_ms / 1000, output=stdout, stderr=stderr)
                finally:
                    if process.poll() is None:
                        process.kill(); process.communicate()
            execution = execute_target(isolation=temporary_workdir_isolation(environment,
                    session_home_reused=False, prefix="agmark-mock-work-"), invoke=invoke,
                response_extractor=lambda capture: capture.stdout if capture.stdout else None, timeout_ms=timeout,
                before_invoke=before_invoke)
        return emit_terminal_observation(validated, target=target, execution=execution,
            runner_id=RUNNER_ID, runner_version=VERSION, framed_request=framed,
            request_framing_mode="mock_json_v1", usage_provider_reported=False,
            usage_provenance="provider-free deterministic mock; no token or billing authority",
            error_code=error)

    def close(self):
        self._closed = True
