"""Host-local replay worker. Standard library only; collector source is prepended.

Runs inside the selected execution environment, including WSL. Credentials are
never returned: authentication is copied only into a private disposable home.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _hash(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _identity(value):
    return _hash(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _runtime_identity(executable, *, environment=None):
    """Observe the launched binary, rather than inheriting a probe's label."""
    binary = _hash(Path(executable).read_bytes())
    version = subprocess.run([executable, "--version"], capture_output=True, timeout=10,
        check=True, env=environment)
    if _hash(Path(executable).read_bytes()) != binary:
        raise ValueError("runtime_changed_during_identity_capture")
    return {"version": version.stdout.decode().strip(), "binary_sha256": binary}


def _profile(home):
    paths = [home / n for n in ("config.toml", "AGENTS.md", "AGENTS.override.md", "models_cache.json")]
    for name in ("rules", "skills", "hooks"):
        directory = home / name
        if directory.is_symlink():
            raise ValueError("profile_symlink_not_reproducible")
        if directory.exists():
            paths.extend(directory.rglob("*"))
    files = {}
    size = 0
    for path in paths:
        if path.is_symlink():
            raise ValueError("profile_symlink_not_reproducible")
        if not path.is_file():
            continue
        size += path.stat().st_size
        if size > 16 * 1024 * 1024 or len(files) >= 2000:
            raise ValueError("profile_capture_limit")
        files[str(path.relative_to(home))] = _hash(path.read_bytes())
    return files


def _snapshot(payload):
    executable = shutil.which(payload["executable"])
    if not executable:
        raise ValueError("runtime_executable_unavailable")
    executable = str(Path(executable).resolve())
    # Ignore user config is a registered launch control, not an inferred default.
    args = payload["args"]
    if "--ignore-user-config" not in args or any("otel." in x for x in args):
        raise ValueError("unsupported_scored_launch_configuration")
    home = Path(payload.get("profile_home") or os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    parent = Path(payload.get("work_parent") or tempfile.gettempdir()).resolve()
    ancestors = {}
    for directory in (parent, *parent.parents):
        for name in ("AGENTS.md", "AGENTS.override.md"):
            path = directory / name
            if path.is_symlink():
                raise ValueError("ancestor_instruction_symlink")
            if path.is_file():
                ancestors[str(path)] = _hash(path.read_bytes())
    identity = _runtime_identity(executable)
    safe_environment = {k: v for k, v in os.environ.items() if k in (
        "HOME", "USERPROFILE", "PATH", "PATHEXT", "SystemRoot", "SYSTEMROOT", "LANG",
        "LC_ALL", "LC_CTYPE", "TZ", "APPDATA", "LOCALAPPDATA", "COMSPEC", "WINDIR")}
    profile = _profile(home)
    result = {"executable": executable, **identity, "args": args,
        "home": str(home), "work_parent": str(parent), "profile": profile,
        "profile_sha256": _identity(profile), "ancestors": ancestors,
        "instructions_sha256": _identity({"profile": profile, "ancestors": ancestors}),
        "environment_sha256": _identity(safe_environment),
        "platform": os.name, "workspace_state_id": _identity({}),
        "launch_controls_sha256": _identity(args)}
    if payload.get("retain"):
        retained = Path(tempfile.mkdtemp(prefix="agmark-startup-"))
        owner = str(uuid.uuid4())
        try:
            (retained / ".agmark-startup-owner").write_text(owner)
            for name, expected in profile.items():
                source = home / name
                raw = source.read_bytes()
                if source.is_symlink() or _hash(raw) != expected:
                    raise ValueError("profile_changed_during_startup")
                destination = retained / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.touch(mode=0o600); destination.write_bytes(raw)
            result.update(retained_home=str(retained), retained_owner=owner)
        except Exception:
            shutil.rmtree(retained)
            raise
    return result



def _run_process(args, *, data, cwd, env, timeout):
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, cwd=cwd, env=env, start_new_session=os.name == "posix")
    try:
        process.communicate(data, timeout=timeout)
        return process.returncode, None
    except subprocess.TimeoutExpired:
        return None, "replay_timeout"
    finally:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            # taskkill terminates the process tree, not just the CLI launcher.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        process.wait()


def _capture(payload):
    expected = payload["snapshot"]
    observed = _snapshot({"executable": expected["executable"], "args": expected["args"],
                          "work_parent": expected["work_parent"], "profile_home": expected["retained_home"]})
    observed.update(home=expected["home"], retained_home=expected["retained_home"], retained_owner=expected["retained_owner"])
    if observed != expected:
        return {"status": "unavailable", "reason": "replay_starting_configuration_changed", "observed": observed, "spans": []}
    with tempfile.TemporaryDirectory(prefix="agmark-replay-", dir=expected["work_parent"]) as directory:
        root = Path(directory)
        home, work = root / "home", root / "work"
        home.mkdir(mode=0o700); work.mkdir(mode=0o700)
        source = Path(expected["retained_home"])
        for name, digest in expected["profile"].items():
            path = source / name
            if path.is_symlink():
                raise ValueError("profile_changed")
            raw = path.read_bytes()
            if _hash(raw) != digest:
                raise ValueError("profile_changed")
            destination = home / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        # Authentication remains transient and is never part of returned evidence.
        auth = Path(expected["home"]) / "auth.json"
        if auth.exists():
            if auth.is_symlink() or auth.stat().st_size > 1024 * 1024:
                raise ValueError("authentication_not_isolatable")
            destination = home / "auth.json"
            destination.touch(mode=0o600)
            destination.write_bytes(auth.read_bytes())
        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(home)
        with LoopbackTraceCollector() as collector:
            args = [expected["executable"]]
            for setting in observation_overrides(payload["validation_id"], collector.endpoint):
                args.extend(("-c", setting))
            args.extend(expected["args"])
            result, reason = _run_process(args, data=base64.b64decode(payload["frame_base64"], validate=True),
                cwd=work, env=environment, timeout=payload["timeout"])
            return {"status": "completed" if result == 0 else "failed", "reason": reason,
                "observed": observed, "spans": collector.spans, "rejected_payloads": collector.rejected_payloads}


def _probe_transport(payload, transport):
    import struct
    snapshot = payload["snapshot"]
    requests = []
    generations = 0
    class Provider(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *args):
            pass
        def events(self, body):
            nonlocal generations
            n = len(requests) + 1
            warmup = body.get("generate") is False
            if not warmup:
                generations += 1
            requests.append({"ordinal": n} if transport == "http" else
                {"ordinal": n, "kind": "warmup" if warmup else "generation"})
            item = ({"type": "function_call", "call_id": "probe", "name": "exec_command", "namespace": "functions",
                "arguments": json.dumps({"cmd": "echo agmark-capability-probe", "max_output_tokens": 20})}
                if not warmup and generations == 1 else
                {"type": "message", "role": "assistant", "id": "answer", "content": [{"type": "output_text", "text": "probe-complete"}]})
            return [{"type": "response.created", "response": {"id": "resp_" + str(n)}},
                *([] if warmup else [{"type": "response.output_item.done", "item": item}]),
                {"type": "response.completed", "response": {"id": "resp_" + str(n), "usage": {
                    "input_tokens": 100*n, "input_tokens_details": {"cached_tokens": 20*n, "cache_write_tokens": 11*n},
                    "output_tokens": 7*n, "output_tokens_details": {"reasoning_tokens": 3*n}, "total_tokens": 107*n}}}]
        def do_POST(self):
            # The CLI can also query e.g. analytics/codex/turn-costs. Those
            # requests are not Responses generations and cannot supply probe
            # counters or consume a scripted tool response.
            if self.path != "/v1/responses":
                self.send_error(404); return
            if transport != "http":
                self.send_error(400); return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 4 * 1024 * 1024:
                self.send_error(400); return
            events = self.events(json.loads(self.rfile.read(length)))
            raw = "".join("event: " + x["type"] + "\ndata: " + json.dumps(x) + "\n\n" for x in events).encode()
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if (self.path != "/v1/responses" or transport != "websocket"
                    or self.headers.get("Upgrade", "").lower() != "websocket"):
                self.send_error(400); return
            accept = base64.b64encode(hashlib.sha1((self.headers["Sec-WebSocket-Key"] +
                "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            self.send_response(101); self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade"); self.send_header("Sec-WebSocket-Accept", accept); self.end_headers()
            self.connection.settimeout(10)
            try:
                while True:
                    head = self.rfile.read(2)
                    if len(head) != 2: return
                    opcode, length = head[0] & 15, head[1] & 127
                    if length == 126: length = struct.unpack("!H", self.rfile.read(2))[0]
                    elif length == 127: length = struct.unpack("!Q", self.rfile.read(8))[0]
                    if length > 4 * 1024 * 1024 or not head[1] & 128 or not head[0] & 128: return
                    mask = self.rfile.read(4); raw = self.rfile.read(length)
                    if len(mask) != 4 or len(raw) != length: return
                    raw = bytes(v ^ mask[i % 4] for i, v in enumerate(raw))
                    if opcode == 8: return
                    if opcode != 1: return
                    for event in self.events(json.loads(raw)):
                        data = json.dumps(event).encode()
                        header = bytes([0x81, len(data)]) if len(data) < 126 else bytes([0x81, 126]) + struct.pack("!H", len(data))
                        self.wfile.write(header + data); self.wfile.flush()
            except (OSError, ValueError, struct.error):
                return
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="agmark-probe-") as directory, LoopbackTraceCollector() as collector:
            root = Path(directory); home = root / "home"; home.mkdir(mode=0o700)
            validation_id = str(uuid.uuid4())
            config = ['model_provider="agmark_probe"', 'model_providers.agmark_probe.name="Controlled probe"',
                'model_providers.agmark_probe.base_url="http://127.0.0.1:' + str(server.server_port) + '/v1"',
                'model_providers.agmark_probe.wire_api="responses"', 'model_providers.agmark_probe.requires_openai_auth=false',
                'model_providers.agmark_probe.supports_websockets=' + ("true" if transport == "websocket" else "false"),
                *observation_overrides(validation_id, collector.endpoint)]
            args = [snapshot["executable"]]
            for setting in config: args.extend(("-c", setting))
            args.extend(["exec", "--json", "--ignore-user-config", "--skip-git-repo-check", "--model", "gpt-5-codex", "-"])
            environment = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in ("TOKEN", "SECRET", "KEY", "CREDENTIAL"))}
            environment["CODEX_HOME"] = str(home)
            identity = _runtime_identity(snapshot["executable"], environment=environment)
            if any(identity[key] != snapshot[key] for key in identity):
                raise ValueError("probe_runtime_identity_changed")
            result, reason = _run_process(args, data=b"Controlled local telemetry probe.", cwd=root,
                env=environment, timeout=25)
            if _runtime_identity(snapshot["executable"], environment=environment) != identity:
                raise ValueError("probe_runtime_identity_changed")
            return {"runtime_version": identity["version"], "runtime_binary_sha256": identity["binary_sha256"],
                "validation_id": validation_id, "returncode": result, "provider_requests": requests,
                "spans": collector.spans, "rejected_payloads": collector.rejected_payloads,
                "purpose": "Controlled " + ("WebSocket warmup and generation" if transport == "websocket" else "HTTP generation") +
                    " with independently supplied synthetic counters; not live-provider behavior."}
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def _probe(payload):
    result = _probe_transport(payload, "http")
    result["websocket_probe"] = _probe_transport(payload, "websocket")
    return result


def _main():
    import sys
    try:
        payload = json.load(sys.stdin)
        op = payload["operation"]
        if op == "snapshot": result = _snapshot(payload)
        elif op == "capture": result = _capture(payload)
        elif op == "probe": result = _probe(payload)
        elif op == "cleanup":
            path = Path(payload["retained_home"])
            if path.parent != Path(tempfile.gettempdir()) or not path.name.startswith("agmark-startup-") or path.is_symlink():
                raise ValueError("unsafe_startup_cleanup")
            if path.exists():
                if (path / ".agmark-startup-owner").read_text() != payload["retained_owner"]:
                    raise ValueError("startup_owner_mismatch")
                shutil.rmtree(path)
            result = {"cleaned": True}
        else: raise ValueError("unknown_host_operation")
        print(json.dumps({"result": result}, separators=(",", ":")))
    except Exception as exc:
        # No exception message can leak file contents or authentication details.
        print(json.dumps({"error": type(exc).__name__}))


if __name__ == "__main__":
    _main()
