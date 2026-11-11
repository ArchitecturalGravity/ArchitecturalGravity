"""Invocation-scoped telemetry bridge into the selected WSL distribution.

The receiver, diagnostic scratch and reducer run beside the original CLI. The
host handles no remote endpoint and never treats Windows loopback as WSL-local.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import asdict
import json
import io
from pathlib import Path
from queue import Empty, Full, Queue
import subprocess
import threading
import time

from .evidence import validate_manifest
from .profile import is_safe_invocation_id
from .profile import CaptureProfile, capability

BOOTSTRAP = (
    "import sys; n=int(sys.stdin.buffer.readline(32)); "
    "assert 0<n<1048576; source=sys.stdin.buffer.read(n); "
    "assert len(source)==n; exec(compile(source,'<agmark-wsl-worker>','exec'))"
)
_SHELL = (
    'set -eu\n'
    'linux_home="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6)"\n'
    'if [ -n "${linux_home:-}" ]; then export HOME="$linux_home"; fi\n'
    'unset CODEX_ROLLOUT_TRACE_ROOT\n'
    'exec python3 -u -c "$1"'
)


class WslCaptureUnavailable(RuntimeError):
    """Selected-distribution telemetry preparation failed before stock exec."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _RemoteLedger:
    """The runner can report callback health without accessing remote state."""
    def __init__(self, owner):
        self.owner = owner

    def count(self, source, **counts):
        self.owner._enqueue({"op": "health", "source": source, "counts": counts}, source=source)

    def state(self, source, state, reason=None):
        self.owner._enqueue({"op": "health", "source": source, "state": state, "reason": reason}, source=source)


class WslCaptureSession:
    """CaptureSession-compatible facade; readiness is acknowledged before launch."""
    def __init__(self, profile=None, runtime_version=None, invocation_id=None, on_progress=None, *,
                 launch_metadata, environment=None, launch_mode="wsl", startup_timeout_seconds=10.0,
                 operation_timeout_seconds=15.0, popen_factory=None):
        self.profile = profile or CaptureProfile()
        if not isinstance(self.profile, CaptureProfile):
            raise TypeError("capture requires a versioned CaptureProfile")
        if launch_mode != "wsl":
            raise ValueError("selected-distribution bridge requires WSL launch")
        import re
        if not is_safe_invocation_id(invocation_id):
            raise ValueError("capture requires a canonical non-personal invocation identifier")
        self.launch_metadata = dict(launch_metadata)
        for key in ("launcher", "distribution", "executable"):
            if not isinstance(self.launch_metadata.get(key), str) or not self.launch_metadata[key]:
                raise ValueError("selected-distribution bridge needs " + key)
        if not 0 < startup_timeout_seconds <= 30 or not 0 < operation_timeout_seconds <= 45:
            raise ValueError("bridge timeouts must be bounded")
        self.environment = dict(environment or {})
        self.invocation_id = invocation_id
        self.on_progress = on_progress
        self.runtime = capability(runtime_version, "native")
        self.runtime.update(launch_mode="wsl", receiver_environment="selected_distribution")
        self.config_overrides = ()
        self.env_overrides = {"CODEX_ROLLOUT_TRACE_ROOT": None}
        self.process_control_path = None
        self.ledger = _RemoteLedger(self)
        self.startup_timeout_seconds = startup_timeout_seconds
        self.operation_timeout_seconds = operation_timeout_seconds
        self._popen = popen_factory or subprocess.Popen
        self._process = None
        self._writer = None
        self._reader = None
        self._queue = Queue(maxsize=256)
        self._condition = threading.Condition()
        self._replies = {}
        self._request_number = 0
        self._failure = None
        self._eof = False
        self._started = False
        self._closed = False
        self._manifest = None
        self._dropped = {"stdout": 0, "stderr": 0, "process": 0}
        self._maximum_reply = 2 * self.profile.max_retained_bytes + 8 * 1024 * 1024

    def _write_messages(self):
        def write_all(raw):
            remaining = memoryview(raw)
            while remaining:
                count = self._process.stdin.write(remaining)
                if not count:
                    raise OSError("bridge_pipe_closed")
                remaining = remaining[count:]
        try:
            worker = Path(__file__).with_name("wsl_worker.py").read_bytes()
            write_all(str(len(worker)).encode() + b"\n" + worker)
            self._process.stdin.flush()
            while True:
                command = self._queue.get()
                if command is None:
                    break
                raw = json.dumps(command, separators=(",", ":"), allow_nan=False).encode() + b"\n"
                if len(raw) > 192 * 1024 * 1024:
                    raise ValueError("bridge_command_limit")
                write_all(raw)
                self._process.stdin.flush()
        except (OSError, ValueError, TypeError):
            self._mark_failure("selected_host_bridge_write_failed")
        finally:
            try:
                self._process.stdin.close()
            except (OSError, ValueError):
                pass

    def _read_messages(self):
        reader = io.BufferedReader(self._process.stdout, buffer_size=65536)
        try:
            while True:
                raw = reader.readline(self._maximum_reply + 1)
                if not raw:
                    break
                if len(raw) > self._maximum_reply or not raw.endswith(b"\n"):
                    raise ValueError("bridge_reply_limit")
                message = json.loads(raw)
                if message.get("kind") == "progress":
                    if self.on_progress is not None:
                        try:
                            self.on_progress(message["event"])
                        except Exception:
                            pass
                elif message.get("kind") == "reply":
                    with self._condition:
                        self._replies[message["request_id"]] = message
                        self._condition.notify_all()
                else:
                    raise ValueError("invalid_bridge_reply")
        except (OSError, ValueError, KeyError, TypeError):
            self._mark_failure("selected_host_bridge_read_failed")
        finally:
            try:
                reader.close()
            except (OSError, ValueError):
                pass
            with self._condition:
                self._eof = True
                self._condition.notify_all()

    def _mark_failure(self, reason):
        with self._condition:
            self._failure = reason
            self._condition.notify_all()

    def _enqueue(self, command, *, source="process"):
        if self._closed or self._failure or not self._started:
            self._dropped[source] = self._dropped.get(source, 0) + 1
            return False
        try:
            self._queue.put_nowait(command)
            return True
        except Full:
            self._dropped[source] = self._dropped.get(source, 0) + 1
            return False

    def _request(self, command, timeout):
        deadline = time.monotonic() + timeout
        with self._condition:
            self._request_number += 1
            request_id = self._request_number
        command = {**command, "request_id": request_id}
        try:
            self._queue.put(command, timeout=max(0, deadline - time.monotonic()))
        except Full as exc:
            raise WslCaptureUnavailable("selected_host_bridge_queue_timeout") from exc
        with self._condition:
            while request_id not in self._replies and not self._failure and not self._eof:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            message = self._replies.pop(request_id, None)
        if message is None:
            raise WslCaptureUnavailable(self._failure or "selected_host_bridge_reply_unavailable")
        if message.get("error"):
            raise WslCaptureUnavailable(message["error"])
        return message["result"]

    def start(self):
        if self._started:
            raise RuntimeError("capture session is invocation-scoped and cannot restart")
        self._started = True
        if self.runtime["capability_status"] != "supported":
            raise WslCaptureUnavailable("selected_runtime_capability_unverified")
        command = (self.launch_metadata["launcher"], "--distribution", self.launch_metadata["distribution"],
                   "--exec", "sh", "-lc", _SHELL, "agmark-telemetry-bridge", BOOTSTRAP)
        try:
            self._process = self._popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=self.environment, bufsize=0)
            self._writer = threading.Thread(target=self._write_messages, name="agmark-wsl-capture-write", daemon=True)
            self._reader = threading.Thread(target=self._read_messages, name="agmark-wsl-capture-read", daemon=True)
            self._writer.start()
            self._reader.start()
            root = Path(__file__).parent
            modules = {name: (root / (name + ".py")).read_text(encoding="utf-8")
                       for name in ("runtime_reference", "profile", "privacy", "evidence", "collector", "capture", "wsl_process")}
            ready = self._request({"op": "start", "profile": asdict(self.profile), "modules": modules,
                "runtime_version": self.runtime["version"], "invocation_id": self.invocation_id,
                "runtime": self.runtime, "executable": self.launch_metadata["executable"]}, self.startup_timeout_seconds)
            self.config_overrides = tuple(ready["config_overrides"])
            self.env_overrides = dict(ready["env_overrides"])
            self.runtime.update(ready["runtime"])
            self.process_control_path = ready["process_control_path"]
            return self
        except Exception as exc:
            self._dispose()
            if isinstance(exc, WslCaptureUnavailable):
                raise
            raise WslCaptureUnavailable("selected_host_bridge_start_failed") from exc

    def _ingest(self, source, chunk):
        if not isinstance(chunk, bytes):
            self._dropped[source] += 1
            return
        for offset in range(0, len(chunk), 65536):
            self._enqueue({"op": source, "bytes": base64.b64encode(chunk[offset:offset + 65536]).decode("ascii")}, source=source)

    def ingest_stdout(self, chunk):
        self._ingest("stdout", chunk)

    def ingest_stderr(self, chunk):
        self._ingest("stderr", chunk)

    def reduce_diagnostics(self, executable, *, timeout_seconds=10):
        if not self.profile.diagnostics_enabled:
            raise ValueError("diagnostic reduction requires explicit privacy opt-in")
        return self._request({"op": "reduce", "executable": str(executable),
                              "timeout_seconds": timeout_seconds}, min(40, timeout_seconds + 5))

    def stop_execution(self):
        """Stop only this invocation's guarded process group before settlement."""
        if self._closed:
            return None
        return self._request({"op": "stop_execution"}, 4.0)

    def finish(self, stdout=None, stderr=None, rollout_record=None, process_status="completed"):
        if self._manifest is not None:
            return deepcopy(self._manifest)
        if not self._started:
            self.start()
        command = {"op": "finish", "process_status": process_status,
                   "rollout_record": rollout_record, "runtime": self.runtime, "dropped": dict(self._dropped)}
        remaining_bytes = self.profile.max_retained_bytes
        for source, raw in (("stdout", stdout), ("stderr", stderr)):
            if raw is not None and not isinstance(raw, bytes):
                raise TypeError("captured streams must be bytes")
            if raw is not None and len(raw) > remaining_bytes:
                command["dropped"][source] = command["dropped"].get(source, 0) + 1
                raw = None
            if raw is not None:
                remaining_bytes -= len(raw)
            command[source] = None if raw is None else base64.b64encode(raw).decode("ascii")
        if isinstance(rollout_record, dict) and len(rollout_record.get("content_base64", "")) > remaining_bytes * 4 // 3 + 4:
            command["rollout_record"] = {"availability": "unavailable", "reason": "selected_host_bridge_rollout_limit"}
        try:
            manifest = self._request(command, self.operation_timeout_seconds)
            validate_manifest(manifest)
            if manifest.get("invocation_id") != self.invocation_id or manifest.get("authority") != "original":
                raise WslCaptureUnavailable("selected_host_bridge_identity_mismatch")
            self._manifest = manifest
            return deepcopy(manifest)
        finally:
            self._dispose()

    def _dispose(self):
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is None:
            return
        try:
            self._queue.put_nowait(None)
        except Full:
            pass
        # EOF requests cleanup even when readiness/reduction failed. A hung
        # selected-host process cannot keep the GUI worker waiting indefinitely.
        if self._writer is not None:
            self._writer.join(timeout=0.2)
        try:
            process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
        if self._reader is not None:
            self._reader.join(timeout=0.2)

    def close(self):
        if self._manifest is not None:
            self._dispose()
            return deepcopy(self._manifest)
        if self._closed:
            return None
        return self.finish(process_status="cancelled")

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
