"""Standard-library worker executed in the selected WSL distribution.

The parent transfers exact package source through stdin. Neither environment nor
credentials are serialized. Only sanitized progress and sealed evidence return.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import types
import uuid


def main():
    output_lock = threading.Lock()
    session = None
    control_root = None
    process_control_path = None
    stop_owned_process = None
    last_stop_result = None
    maximum = 192 * 1024 * 1024

    def emit(value):
        encoded = json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        with output_lock:
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()

    def decode_bytes(value):
        return None if value is None else base64.b64decode(value, validate=True)

    def stop_execution():
        nonlocal last_stop_result
        try:
            result = stop_owned_process(process_control_path)
        except Exception:
            result = {"status": "failed", "reason": "selected_host_cleanup_unconfirmed"}
        if session is not None:
            if result.get("status") in {"failed", "unavailable"}:
                session.ledger.count("process", partial=1)
                session.ledger.state("process", "partial", result.get("reason", "selected_host_cleanup_unconfirmed"))
            session.ledger.add("process", {"phase": "selected_host_cleanup", **result})
        last_stop_result = result
        return result

    try:
        while True:
            raw = sys.stdin.buffer.readline(maximum + 1)
            if not raw:
                break
            if len(raw) > maximum or not raw.endswith(b"\n"):
                raise ValueError("bridge_command_limit")
            command = json.loads(raw)
            operation, request_id = command.get("op"), command.get("request_id")
            failure_reason = "selected_host_" + str(operation) + "_failed"
            try:
                if operation == "start":
                    if session is not None:
                        raise ValueError("bridge_already_started")
                    package = types.ModuleType("agmark_selected_host_telemetry")
                    package.__path__ = []
                    sys.modules[package.__name__] = package
                    for name in ("runtime_reference", "profile", "privacy", "evidence", "collector", "capture", "wsl_process"):
                        source = command["modules"][name]
                        if not isinstance(source, str) or len(source) > 512 * 1024:
                            raise ValueError("bridge_module_limit")
                        fullname = package.__name__ + "." + name
                        module = types.ModuleType(fullname)
                        module.__package__ = package.__name__
                        sys.modules[fullname] = module
                        exec(compile(source, "<agmark-selected-host-" + name + ">", "exec"), module.__dict__)
                    from agmark_selected_host_telemetry.profile import CaptureProfile
                    from agmark_selected_host_telemetry.capture import CaptureSession
                    from agmark_selected_host_telemetry.wsl_process import stop_owned_process
                    profile = CaptureProfile(**command["profile"])
                    session = CaptureSession(profile=profile, runtime_version=command["runtime_version"],
                        invocation_id=command["invocation_id"], launch_mode="native",
                        on_progress=lambda event: emit({"kind": "progress", "event": event}))
                    if session.runtime["capability_status"] != "supported":
                        raise ValueError("selected_runtime_capability_unverified")
                    # Receiver and CLI share this distribution's local network and
                    # filesystem. Host-only WSL capture never gets this admission.
                    session.runtime.update(command.get("runtime", {}))
                    session.runtime.update(launch_mode="wsl", receiver_environment="selected_distribution",
                                           capability_status="supported", reason=None)
                    session.runtime.update(binary_sha256=None, binary_hash_reason="selected_host_binary_unreadable")
                    try:
                        executable = shutil.which(command["executable"])
                        binary = Path(executable or command["executable"])
                        if binary.is_file() and binary.stat().st_size <= 512 * 1024 * 1024:
                            hasher = hashlib.sha256()
                            with binary.open("rb") as handle:
                                while chunk := handle.read(1024 * 1024):
                                    hasher.update(chunk)
                            session.runtime.update(binary_sha256="sha256:" + hasher.hexdigest(), binary_hash_reason=None)
                    except OSError:
                        pass
                    failure_reason = "selected_host_collector_unavailable"
                    session.start()
                    if session.profile.enabled and session.collector is None:
                        raise ValueError("selected_host_collector_unavailable")
                    if session.profile.diagnostics_enabled:
                        failure_reason = "selected_host_diagnostics_unavailable"
                        if (session.diagnostic_root is None
                                or session.ledger.sources["diagnostics"]["state"] != "ready"):
                            raise ValueError("selected_host_diagnostics_unavailable")
                    failure_reason = "selected_host_process_control_unavailable"
                    control_root = Path(tempfile.mkdtemp(prefix="agmark-original-process-"))
                    control_root.chmod(0o700)
                    owner_marker = control_root / ".agmark-process-owner"
                    owner_marker.write_text(uuid.uuid4().hex, encoding="ascii")
                    owner_marker.chmod(0o600)
                    process_control_path = str(control_root / "process.json")
                    result = {"config_overrides": list(session.config_overrides),
                              "env_overrides": session.env_overrides, "runtime": session.runtime,
                              "process_control_path": process_control_path}
                elif session is None:
                    raise ValueError("bridge_not_started")
                elif operation in {"stdout", "stderr"}:
                    chunk = decode_bytes(command["bytes"])
                    if len(chunk) > 65536:
                        raise ValueError("bridge_chunk_limit")
                    getattr(session, "ingest_" + operation)(chunk)
                    continue
                elif operation == "health":
                    source = command["source"]
                    if source not in session.ledger.sources:
                        raise ValueError("unknown_bridge_source")
                    if command.get("counts"):
                        session.ledger.count(source, **command["counts"])
                    if command.get("state"):
                        session.ledger.state(source, command["state"], command.get("reason"))
                    continue
                elif operation == "reduce":
                    result = session.reduce_diagnostics(command["executable"],
                        timeout_seconds=command.get("timeout_seconds", 10))
                elif operation == "stop_execution":
                    result = stop_execution()
                elif operation in {"finish", "close"}:
                    stop_execution()
                    session.runtime.update(command.get("runtime", {}))
                    for source, count in command.get("dropped", {}).items():
                        if count and source in session.ledger.sources:
                            session.ledger.count(source, dropped=count)
                            session.ledger.state(source, "partial", "selected_host_bridge_backpressure")
                    result = session.finish(stdout=decode_bytes(command.get("stdout")),
                        stderr=decode_bytes(command.get("stderr")), rollout_record=command.get("rollout_record"),
                        process_status=command.get("process_status", "cancelled"))
                    emit({"kind": "reply", "request_id": request_id, "result": result})
                    break
                else:
                    raise ValueError("unknown_bridge_operation")
                emit({"kind": "reply", "request_id": request_id, "result": result})
            except Exception:
                # Exceptions may contain paths or source text; never export them.
                emit({"kind": "reply", "request_id": request_id,
                      "error": failure_reason})
                if session is not None and operation in {"stdout", "stderr"}:
                    session.ledger.count(operation, partial=1)
                    session.ledger.state(operation, "partial", "selected_host_stream_capture_failed")
                if operation in {"start", "finish", "close"}:
                    break
    finally:
        if process_control_path is not None and stop_owned_process is not None:
            try:
                stop_execution()
            except Exception:
                pass
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        # Keep the private recovery authority if targeted cleanup could not be
        # acknowledged. Removing it would make surviving descendants unowned.
        if control_root is not None and last_stop_result and last_stop_result.get("status") in {
                "not_started", "already_exited", "stopped"}:
            shutil.rmtree(control_root, ignore_errors=True)


if __name__ == "__main__":
    main()
