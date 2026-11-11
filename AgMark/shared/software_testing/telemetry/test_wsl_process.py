"""Linux-local WSL process guard fixtures; no WSL or provider needed."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from AgMark.shared.telemetry.wsl_process import GUARD_SOURCE, stop_owned_process


def identity(pid):
    try:
        fields = Path("/proc", str(pid), "stat").read_text().rsplit(")", 1)[1].split()
        return {"starttime": int(fields[19]), "state": fields[0]}
    except OSError:
        return None


def active(pid):
    value = identity(pid)
    return value is not None and value["state"] not in {"Z", "X"}


@unittest.skipUnless(os.name == "posix" and Path("/proc").is_dir(), "Linux process identity fixture")
class WslProcessGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="agmark-process-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.root.chmod(0o700)
        self.owner = uuid.uuid4().hex.encode()
        owner_file = self.root / ".agmark-process-owner"
        owner_file.touch(mode=0o600)
        owner_file.write_bytes(self.owner)
        self.control = self.root / "process.json"
        self.children = []
        self.addCleanup(self.cleanup_processes)

    def cleanup_processes(self):
        stop_owned_process(self.control, timeout_seconds=0.3)
        for process in self.children:
            if process.poll() is None:
                process.kill()
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    def launch(self, code):
        process = subprocess.Popen([sys.executable, "-c", GUARD_SOURCE, str(self.control),
            sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.children.append(process)
        return process

    def await_control(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.control.exists():
                return json.loads(self.control.read_text())
            time.sleep(0.01)
        self.fail("guard did not register its process identity")

    def signed_record(self, record):
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        record = {**record, "signature": hmac.new(self.owner, canonical, hashlib.sha256).hexdigest()}
        self.control.touch(mode=0o600, exist_ok=True)
        self.control.write_text(json.dumps(record))

    def test_guard_preserves_channels_and_exact_normal_exit_status(self):
        process = self.launch("import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); sys.stderr.buffer.write(b'fixture stderr'); sys.exit(7)")
        out, err = process.communicate(b"original stdin\x00bytes\n", timeout=3)
        self.assertEqual((process.returncode, out, err), (7, b"original stdin\x00bytes\n", b"fixture stderr"))
        saved = self.await_control()
        self.assertEqual(saved["state"], "exited")
        self.assertEqual(saved["exit_status"], 7)
        self.assertTrue(saved["group_cleanup_complete"])
        self.assertEqual(stop_owned_process(self.control)["status"], "already_exited")

    def test_cancel_kills_group_descendants_but_not_an_unrelated_session(self):
        sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        self.children.append(sibling)
        code = ("import os, subprocess, sys, time; "
                "child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)']); "
                "print(os.getpid(),child.pid,flush=True); time.sleep(30)")
        process = self.launch(code)
        saved = self.await_control()
        line = process.stdout.readline()
        child_pid, descendant_pid = map(int, line.split())
        self.assertEqual(saved["child_pid"], child_pid)
        start = time.monotonic()
        result = stop_owned_process(self.control, timeout_seconds=1)
        process.communicate(timeout=3)
        self.assertLess(time.monotonic() - start, 3)
        self.assertIn(result["status"], {"stopped", "already_exited"})
        self.assertFalse(active(child_pid))
        self.assertFalse(active(descendant_pid))
        self.assertIsNone(sibling.poll())

    def test_normal_completion_cleans_a_leftover_descendant(self):
        process = self.launch("import subprocess,sys; child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print(child.pid,flush=True)")
        out, err = process.communicate(timeout=3)
        self.assertEqual(process.returncode, 0)
        self.assertFalse(active(int(out.strip())))
        self.assertEqual(err, b"")

    def test_worker_recovers_after_guard_is_killed(self):
        process = self.launch("import time; time.sleep(30)")
        saved = self.await_control()
        process.kill()
        process.wait(timeout=2)
        self.assertTrue(active(saved["child_pid"]))
        result = stop_owned_process(self.control, timeout_seconds=1)
        self.assertEqual(result["status"], "stopped")
        self.assertFalse(active(saved["child_pid"]))

    def test_sigterm_resistant_child_is_killed_within_bound(self):
        process = self.launch("import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(30)")
        saved = self.await_control()
        self.assertEqual(process.stdout.readline(), b"ready\n")
        started = time.monotonic()
        result = stop_owned_process(self.control, timeout_seconds=0.4)
        process.communicate(timeout=2)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(process.returncode, 137)
        self.assertFalse(active(saved["child_pid"]))

    def test_control_directory_cannot_be_reused_for_another_invocation(self):
        first = self.launch("pass")
        first.communicate(timeout=2)
        self.assertEqual(first.returncode, 0)
        marker = self.root / "should-not-run"
        second = self.launch("from pathlib import Path; Path(" + repr(str(marker)) + ").touch()")
        second.communicate(timeout=2)
        self.assertEqual(second.returncode, 125)
        self.assertFalse(marker.exists())

    def test_stop_before_registration_prevents_later_exec(self):
        self.assertEqual(stop_owned_process(self.control)["status"], "not_started")
        marker = self.root / "should-not-run"
        process = self.launch("from pathlib import Path; Path(" + repr(str(marker)) + ").touch()")
        process.communicate(timeout=3)
        self.assertEqual(process.returncode, 143)
        self.assertFalse(marker.exists())

    def test_mismatched_saved_starttime_never_signals_reused_pid(self):
        sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        self.children.append(sibling)
        self.signed_record({"schema_version": 1, "state": "active", "guard_pid": os.getpid(),
            "guard_starttime": identity(os.getpid())["starttime"], "child_pid": sibling.pid,
            "child_starttime": identity(sibling.pid)["starttime"] + 1})
        result = stop_owned_process(self.control)
        self.assertEqual(result, {"status": "unavailable", "reason": "saved_child_process_identity_changed"})
        self.assertIsNone(sibling.poll())

    def test_unrelated_process_is_not_accepted_as_guard(self):
        sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        self.children.append(sibling)
        self.signed_record({"schema_version": 1, "state": "active", "guard_pid": os.getpid(),
            "guard_starttime": identity(os.getpid())["starttime"], "child_pid": sibling.pid,
            "child_starttime": identity(sibling.pid)["starttime"]})
        result = stop_owned_process(self.control)
        self.assertEqual(result["reason"], "saved_guard_process_is_not_invocation_guard")
        self.assertIsNone(sibling.poll())

    def test_tampered_control_and_symlinks_never_authorize_cleanup(self):
        self.control.touch(mode=0o600)
        self.control.write_text('{"child_pid":2,"signature":"not-an-owner-signature"}')
        self.assertEqual(stop_owned_process(self.control)["status"], "unavailable")
        self.control.unlink()
        untouched = self.root / "untouched"
        untouched.touch(mode=0o600)
        untouched.write_text("sentinel")
        self.control.symlink_to(untouched)
        self.assertEqual(stop_owned_process(self.control)["status"], "unavailable")
        self.assertEqual(untouched.read_text(), "sentinel")
        linked_root = self.root / "link"
        linked_root.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(stop_owned_process(linked_root / "process.json")["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
