"""Read only the persisted rollout belonging to an exact Codex thread.

This module deliberately uses only the standard library: its source also runs
inside the selected WSL distribution, with that user's login-shell environment.
"""
from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
import re
import stat
import time

MAX_DISCOVERY_ENTRIES = 100000
MAX_ROLLOUT_BYTES = 64 * 1024 * 1024


def _scan_candidates(root, thread_id, *, deadline, maximum_entries, cancellation_requested):
    """A candidate is authoritative only after the entire bounded scan finishes."""
    pending, candidates, examined = [root], [], 0
    while pending:
        if cancellation_requested is not None and cancellation_requested():
            return (), examined, "session_capture_cancelled"
        if time.monotonic() >= deadline:
            return (), examined, "session_discovery_timeout"
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if cancellation_requested is not None and cancellation_requested():
                    return (), examined, "session_capture_cancelled"
                if time.monotonic() >= deadline:
                    return (), examined, "session_discovery_timeout"
                examined += 1
                if examined > maximum_entries:
                    return (), examined, "session_discovery_entry_limit"
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.name == thread_id + ".jsonl" or entry.name.endswith("-" + thread_id + ".jsonl"):
                    candidates.append(Path(entry.path))
                    if len(candidates) > 1:
                        return (), examined, "ambiguous_session_records"
    return candidates, examined, None


def _read_bounded(path, *, deadline, maximum_bytes, cancellation_requested):
    raw = bytearray()
    with path.open("rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            return None, "invalid_session_path"
        while True:
            if cancellation_requested is not None and cancellation_requested():
                return None, "session_capture_cancelled"
            if time.monotonic() >= deadline:
                return None, "session_settlement_timeout"
            chunk = handle.read(min(65536, maximum_bytes + 1 - len(raw)))
            if not chunk:
                return bytes(raw), None
            raw.extend(chunk)
            if len(raw) > maximum_bytes:
                return None, "session_record_byte_limit"


def session_root(environment):
    home = environment.get("CODEX_HOME")
    if home:
        return Path(home) / "sessions"
    user_home = environment.get("USERPROFILE") if os.name == "nt" else environment.get("HOME")
    return Path(user_home or Path.home()) / ".codex" / "sessions"


def read_session(thread_id, *, root=None, timeout_seconds=1.0,
                 cancellation_requested=None, maximum_entries=MAX_DISCOVERY_ENTRIES,
                 maximum_bytes=MAX_ROLLOUT_BYTES):
    """Match both filename suffix and session_meta ID; never select by mtime.

    The caller has waited for the CLI process to exit. Two identical reads avoid
    taking a snapshot in the middle of the final append. A truncated final line
    is retained as partial evidence by the parser rather than discarded.
    """
    if (type(timeout_seconds) not in {int, float} or not math.isfinite(timeout_seconds)
            or not 0 <= timeout_seconds <= 30 or type(maximum_entries) is not int
            or not 1 <= maximum_entries <= MAX_DISCOVERY_ENTRIES
            or type(maximum_bytes) is not int or not 1 <= maximum_bytes <= MAX_ROLLOUT_BYTES):
        raise ValueError("session capture limits must be bounded")
    root = Path(root) if root is not None else session_root(os.environ)
    absent = {"availability": "unavailable", "thread_id": thread_id,
              "root": str(root), "reason": "session_record_missing", "capture_complete": False,
              "capture_limits": {"timeout_seconds": timeout_seconds, "maximum_entries": maximum_entries,
                                 "maximum_bytes": maximum_bytes}, "discovery_entries_examined": 0}
    if not isinstance(thread_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", thread_id):
        return {**absent, "reason": "invalid_thread_id"}
    deadline = time.monotonic() + timeout_seconds
    previous = None
    settled = None
    while True:
        try:
            if cancellation_requested is not None and cancellation_requested():
                return {**absent, "reason": "session_capture_cancelled"}
            if root.is_dir():
                candidates, examined, problem = _scan_candidates(root, thread_id, deadline=deadline,
                    maximum_entries=maximum_entries - absent["discovery_entries_examined"],
                    cancellation_requested=cancellation_requested)
                absent["discovery_entries_examined"] += examined
                if problem is not None:
                    return {**absent, "reason": problem}
            else:
                candidates = []
            if not candidates:
                previous = settled = None
            if len(candidates) > 1:
                return {**absent, "reason": "ambiguous_session_records"}
            if candidates:
                path = candidates[0]
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                    return {**absent, "reason": "invalid_session_path"}
                if not path.is_file() or path.stat().st_size > maximum_bytes:
                    return {**absent, "reason": "session_record_byte_limit" if path.is_file() else "invalid_session_path"}
                raw, problem = _read_bounded(path, deadline=deadline, maximum_bytes=maximum_bytes,
                    cancellation_requested=cancellation_requested)
                if problem is not None:
                    return {**absent, "reason": problem}
                first = raw.lstrip(b"\r\n").split(b"\n", 1)[0]
                try:
                    metadata = json.loads(first)
                except (ValueError, UnicodeError):
                    metadata = {}
                if isinstance(metadata, dict) and metadata:
                    payload = metadata.get("payload")
                    if metadata.get("type") != "session_meta" or not isinstance(payload, dict) or payload.get("id") != thread_id:
                        return {**absent, "reason": "session_thread_id_mismatch"}
                    if previous == raw:
                        settled = {**absent, "availability": "retained", "thread_id": thread_id,
                                   "root": str(root), "path": str(path),
                                   "content_base64": base64.b64encode(raw).decode("ascii")}
                        try:
                            last = json.loads(raw.rstrip(b"\r\n").rsplit(b"\n", 1)[-1])
                            terminal = last.get("type") == "event_msg" and last.get("payload", {}).get("type") in {"task_complete", "turn_aborted"}
                        except (ValueError, UnicodeError, StopIteration, AttributeError):
                            terminal = False
                        if terminal:
                            settled["capture_complete"] = True
                            settled.pop("reason", None)
                            return settled
                        settled["reason"] = "session_terminal_event_unobserved"
                    else:
                        settled = None
                    previous = raw
        except OSError:
            return {**absent, "reason": "session_record_unreadable"}
        if time.monotonic() >= deadline:
            if settled is not None:
                return settled
            return {**absent, "reason": "session_writer_not_settled" if previous is not None else absent["reason"]}
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    import sys
    print(json.dumps(read_session(sys.argv[1], root=sys.argv[2] if len(sys.argv) > 2 else None)))
