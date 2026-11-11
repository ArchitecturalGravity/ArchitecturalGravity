"""Invocation-owned Linux process guard for a selected WSL distribution.

The same standard-library source runs as a stock CLI wrapper in WSL and backs
the worker's cleanup API. It forwards the original channels without inspection.
Only an owner-marked private directory and verified PID/start-time identities
authorize cleanup; no distribution-wide or name-based process kill is used.
"""
from __future__ import annotations


_IMPLEMENTATION = r'''
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import uuid

_OWNER_FILE = ".agmark-process-owner"
_STOP_FILE = ".agmark-process-stop"
_CONTROL_FILE = "process.json"


def _read_file(directory_fd, name, limit=16384):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid() or details.st_mode & 0o077:
            raise ValueError("unsafe_control_file")
        raw = os.read(descriptor, limit + 1)
        if len(raw) > limit:
            raise ValueError("oversized_control_file")
        return raw
    finally:
        os.close(descriptor)


def _open_directory(control_path):
    path = Path(control_path)
    if not path.is_absolute() or path.name != _CONTROL_FILE or ".." in path.parts:
        raise ValueError("invalid_control_path")
    for component in (path.parent, *path.parent.parents):
        if component.is_symlink():
            raise ValueError("symlink_control_path")
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        details = os.fstat(directory_fd)
        if details.st_uid != os.getuid() or details.st_mode & 0o077:
            raise ValueError("control_directory_not_private")
        owner = _read_file(directory_fd, _OWNER_FILE, 128)
        if owner is None or not re.fullmatch(rb"[0-9a-f]{32,64}", owner):
            raise ValueError("control_owner_missing_or_invalid")
        return directory_fd, owner
    except BaseException:
        os.close(directory_fd)
        raise


def _atomic_write(directory_fd, name, raw):
    temporary = ".agmark-process-tmp-" + uuid.uuid4().hex
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _write_control(directory_fd, owner, value):
    value = dict(value)
    value["signature"] = hmac.new(owner, _canonical(value), hashlib.sha256).hexdigest()
    _atomic_write(directory_fd, _CONTROL_FILE, _canonical(value))


def _read_control(directory_fd, owner):
    raw = _read_file(directory_fd, _CONTROL_FILE)
    if raw is None:
        return None
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid_control_record")
    signature = value.pop("signature", None)
    expected = hmac.new(owner, _canonical(value), hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise ValueError("control_record_ownership_mismatch")
    if value.get("schema_version") != 1:
        raise ValueError("unsupported_control_record")
    for field in ("guard_pid", "child_pid", "guard_starttime", "child_starttime"):
        if type(value.get(field)) is not int or value[field] <= (1 if field.endswith("pid") else 0):
            raise ValueError("invalid_process_identity")
    return value


def _process_identity(pid):
    if type(pid) is not int or pid <= 1:
        return None
    try:
        root = Path("/proc") / str(pid)
        if root.stat().st_uid != os.getuid():
            return None
        # Linux comm can contain spaces and parentheses; split after its last ).
        fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "state": fields[0], "parent_pid": int(fields[1]),
                "group_id": int(fields[2]), "session_id": int(fields[3]), "starttime": int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


def _live_group_members(group_id):
    members = []
    try:
        for path in Path("/proc").iterdir():
            if path.name.isdecimal():
                process = _process_identity(int(path.name))
                if (process and process["group_id"] == group_id and process["session_id"] == group_id
                        and process["state"] not in {"Z", "X"}):
                    members.append(process)
    except OSError:
        return None
    return members


def _send_owned_group(child_pid, child_starttime, signal_number):
    process = _process_identity(child_pid)
    if process is not None and (process["starttime"] != child_starttime
            or process["group_id"] != child_pid or process["session_id"] != child_pid):
        return False
    # A departed leader can leave descendants in its original group. Its PGID
    # remains reserved while that group exists; a new leader is checked above.
    members = _live_group_members(child_pid)
    if members is None:
        return False
    if not members:
        return True
    try:
        os.killpg(child_pid, signal_number)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return True


def _terminate_owned_group(child_pid, child_starttime, timeout_seconds):
    timeout = max(0.1, min(float(timeout_seconds), 5.0))
    deadline = time.monotonic() + timeout
    if not _send_owned_group(child_pid, child_starttime, signal.SIGTERM):
        return False
    soft_deadline = time.monotonic() + timeout / 2
    while time.monotonic() < soft_deadline:
        members = _live_group_members(child_pid)
        if members == []:
            return True
        if members is None:
            return False
        time.sleep(min(0.02, max(0, soft_deadline - time.monotonic())))
    if not _send_owned_group(child_pid, child_starttime, signal.SIGKILL):
        return False
    while time.monotonic() < deadline:
        members = _live_group_members(child_pid)
        if members == []:
            return True
        if members is None:
            return False
        time.sleep(min(0.02, max(0, deadline - time.monotonic())))
    return _live_group_members(child_pid) == []


def _guard_matches(value, control_path, expected_source):
    process = _process_identity(value["guard_pid"])
    if not process or process["starttime"] != value["guard_starttime"] or process["state"] in {"Z", "X"}:
        return False
    try:
        argv = (Path("/proc") / str(value["guard_pid"]) / "cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    return len(argv) >= 4 and argv[1] == b"-c" and argv[2] == expected_source.encode() and argv[3] == os.fsencode(control_path)


def _stop_owned_process(control_path, timeout_seconds, expected_source):
    directory_fd = None
    try:
        directory_fd, owner = _open_directory(control_path)
        value = _read_control(directory_fd, owner)
        # Cancellation before PID registration must also stop a future launch.
        _atomic_write(directory_fd, _STOP_FILE, owner)
        if value is None:
            return {"status": "not_started", "reason": "invocation_launch_cancelled_before_registration"}
        child = _process_identity(value["child_pid"])
        if child is not None and (child["starttime"] != value["child_starttime"]
                or child["group_id"] != value["child_pid"] or child["session_id"] != value["child_pid"]):
            return {"status": "unavailable", "reason": "saved_child_process_identity_changed"}
        guard_matches = _guard_matches(value, control_path, expected_source)
        guard = _process_identity(value["guard_pid"])
        if guard and guard["starttime"] == value["guard_starttime"] and not guard_matches:
            return {"status": "unavailable", "reason": "saved_guard_process_is_not_invocation_guard"}
        if child and guard_matches and child["parent_pid"] != value["guard_pid"]:
            return {"status": "unavailable", "reason": "saved_child_parent_identity_changed"}
        if guard_matches:
            try:
                os.kill(value["guard_pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
        members = _live_group_members(value["child_pid"])
        if members is None:
            return {"status": "unavailable", "reason": "linux_process_table_unavailable"}
        if not members:
            return {"status": "already_exited", "reason": "owned_process_group_empty"}
        if not _terminate_owned_group(value["child_pid"], value["child_starttime"], timeout_seconds):
            return {"status": "failed", "reason": "owned_process_group_did_not_stop"}
        return {"status": "stopped", "reason": "verified_invocation_process_group_terminated"}
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        return {"status": "unavailable", "reason": "invalid_or_unavailable_private_control"}
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _guard_main(arguments):
    if len(arguments) < 2:
        return 125
    control_path, child_arguments = arguments[0], arguments[1:]
    directory_fd = None
    child = None
    child_identity = None
    control = None
    stopping = False

    def interrupted(signal_number, frame):
        nonlocal stopping
        if stopping:
            return
        stopping = True
        if child_identity is not None:
            _terminate_owned_group(child_identity["pid"], child_identity["starttime"], 1.0)

    try:
        directory_fd, owner = _open_directory(control_path)
        if _read_control(directory_fd, owner) is not None:
            return 125  # Each directory is a single-use invocation authority.
        if _read_file(directory_fd, _STOP_FILE, 128) is not None:
            return 143
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        signal.signal(signal.SIGHUP, interrupted)
        if stopping or _read_file(directory_fd, _STOP_FILE, 128) is not None:
            return 143
        child = subprocess.Popen(child_arguments, start_new_session=True)
        child_identity = _process_identity(child.pid)
        guard_identity = _process_identity(os.getpid())
        if child_identity is None or guard_identity is None:
            child.kill()
            child.wait()
            return 125
        control = {"schema_version": 1, "state": "active", "guard_pid": os.getpid(),
            "guard_starttime": guard_identity["starttime"], "child_pid": child.pid,
            "child_starttime": child_identity["starttime"]}
        _write_control(directory_fd, owner, control)
        if stopping or _read_file(directory_fd, _STOP_FILE, 128) is not None:
            _terminate_owned_group(child.pid, child_identity["starttime"], 1.0)
        result = child.wait()
        # A successful CLI can still leave a tool descendant in the owned group.
        cleaned = _terminate_owned_group(child.pid, child_identity["starttime"], 1.0)
        _write_control(directory_fd, owner, {**control, "state": "exited", "exit_status": result,
            "group_cleanup_complete": cleaned})
        return result if result >= 0 else 128 - result
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        if child is not None:
            if child_identity is not None:
                _terminate_owned_group(child.pid, child_identity["starttime"], 1.0)
            elif child.poll() is None:
                child.kill()
            try:
                child.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
        return 125
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
'''

GUARD_SOURCE = _IMPLEMENTATION + "\nif __name__ == '__main__':\n    sys.exit(_guard_main(sys.argv[1:]))\n"

_namespace = {"__name__": "agmark_wsl_process_guard"}
exec(compile(_IMPLEMENTATION, "<agmark-wsl-process-guard>", "exec"), _namespace)


def stop_owned_process(control_path, *, timeout_seconds=1.0):
    """Stop only the signed invocation's matching Linux PID/start-time group.

Returns a safe ``status``/``reason`` mapping. Invalid controls and reused PIDs
never authorize signals. A stop before registration prevents a later launch.
    """
    return _namespace["_stop_owned_process"](str(control_path), timeout_seconds, GUARD_SOURCE)
