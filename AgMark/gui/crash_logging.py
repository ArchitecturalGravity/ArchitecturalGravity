"""Opt-in, standard-library-only GUI crash supervision.

The two desktop applications carry identical standalone copies so neither
application depends on the other's installation. Document contents and locals
are not collected; exception messages and tracebacks can contain user paths.
"""
from __future__ import annotations

import ast
import faulthandler
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid


def enabled(root: Path) -> bool:
    try:
        settings = json.loads((root / "shared" / "config.json").read_text(encoding="utf-8"))
        return isinstance(settings, dict) and settings.get("crash_logging_enabled") is True
    except FileNotFoundError:
        return False
    except (OSError, ValueError) as exc:
        print(f"[{root.name}] Crash logging disabled: cannot read config ({exc}).", file=sys.stderr)
        return False


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied: conservatively alive.
        try:
            status = ctypes.c_ulong()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(status)) or status.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _storage(root: Path) -> tuple[Path, Path]:
    capture = root / "Runtime" / "crash_logs"
    try:
        capture.mkdir(parents=True, exist_ok=True)
        for folder in (capture, root):
            with tempfile.TemporaryFile(dir=folder):
                pass
        return capture, root
    except OSError:
        base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
        fallback = base / "ArchitecturalGravity" / root.name / "diagnostics"
        fallback.mkdir(parents=True, exist_ok=True)
        print(f"[{root.name}] Crash diagnostics location: {fallback}", file=sys.stderr)
        return fallback, fallback


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def _version(root: Path) -> str:
    path = root / ("gui/shell/window.py" if root.name == "AgMark" else "gui/app.py")
    try:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "APP_VERSION" for t in node.targets):
                return str(ast.literal_eval(node.value))
    except (OSError, ValueError, SyntaxError):
        pass
    return "unknown"


def _publish(folder: Path, metadata: dict, output: Path, reason: str) -> None:
    import platform
    try:
        qt = importlib.metadata.version("PySide6")
    except importlib.metadata.PackageNotFoundError:
        qt = "not installed"
    header = {**metadata, "outcome": reason, "python": sys.version, "pyside6": qt,
              "os": platform.platform()}
    # Bound reports even when a failing process emitted excessive output.
    try:
        with output.open("rb") as stream:
            stream.seek(0, 2)
            length = stream.tell()
            stream.seek(max(0, length - 1024 * 1024))
            details = stream.read().decode("utf-8", "replace")
        if length > 1024 * 1024:
            details = "[Earlier output truncated]\n" + details
    except OSError:
        details = "No fault output available."
    report = json.dumps(header, indent=2) + "\n\n" + details
    # Unique retained reports avoid concurrent instances overwriting history.
    archive = folder / f"error.{metadata['run_id']}.log"
    archive.write_text(report, encoding="utf-8")
    temporary = folder / f".error-{uuid.uuid4().hex}.tmp"
    temporary.write_text(report, encoding="utf-8")
    temporary.replace(folder / "error.log")
    for old in sorted(folder.glob("error.*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[5:]:
        old.unlink(missing_ok=True)
    print(f"Crash report: {folder / 'error.log'}", file=sys.stderr)


def _recover(capture: Path, reports: Path) -> None:
    for marker in capture.glob("*.run.json"):
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            if _alive(int(data.get("supervisor_pid", 0))) or _alive(int(data.get("child_pid", 0))):
                continue
            output = marker.with_name(data["run_id"] + ".stderr")
            clean = marker.with_name(data["run_id"] + ".clean")
            if not clean.exists():
                _publish(reports, data, output, "Previous session ended unexpectedly; cause unavailable")
            for path in (output, clean, marker):
                path.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Cannot recover crash marker {marker.name}: {exc}", file=sys.stderr)


def _capture_stderr(pipe, output: Path) -> None:
    """Drain stderr even if capture storage fails; never break the GUI's pipe."""
    stream = None
    try:
        try:
            stream = output.open("w+b")
        except OSError:
            pass
        with pipe:
            while True:
                chunk = pipe.read1(65536)
                if not chunk:
                    break
                if stream is None:
                    continue
                try:
                    stream.write(chunk)
                    if stream.tell() > 1024 * 1024:
                        stream.seek(-512 * 1024, 2)
                        tail = stream.read()
                        stream.seek(0)
                        stream.truncate()
                        stream.write(b"[Earlier output truncated]\n" + tail)
                    stream.flush()
                except OSError:
                    try:
                        stream.close()
                    except OSError:
                        pass
                    stream = None
    except OSError:
        pass
    finally:
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def supervise(root: Path, module: str, arguments: list[str]) -> int:
    capture, reports = _storage(root)
    _recover(capture, reports)
    run_id = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex
    output = capture / (run_id + ".stderr")
    marker = capture / (run_id + ".run.json")
    clean = capture / (run_id + ".clean")
    metadata = {"run_id": run_id, "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "app": root.name, "version": _version(root), "supervisor_pid": os.getpid()}
    _write_json(marker, metadata)
    env = os.environ.copy()
    env["AG_DESKTOP_CRASH_CHILD"] = str(root.resolve())
    env["AG_DESKTOP_CRASH_CLEAN"] = str(clean)
    output.touch()
    collector = None
    try:
        child = subprocess.Popen([sys.executable, "-m", module, *arguments], env=env, stderr=subprocess.PIPE)
    except OSError as exc:
        output.write_text(str(exc), encoding="utf-8")
        result = 1
    else:
        collector = threading.Thread(target=_capture_stderr, args=(child.stderr, output), daemon=True)
        collector.start()
        metadata["child_pid"] = child.pid
        try:
            _write_json(marker, metadata)
        except OSError as exc:
            # A storage failure must not abandon a successfully started GUI.
            print(f"Crash marker update failed; continuing supervision: {exc}", file=sys.stderr)
        try:
            result = child.wait()
        except KeyboardInterrupt:
            # Preserve marker/output if supervisor itself is interrupted.
            return 130
        # A surviving descendant may still hold stderr open after a hard kill.
        collector.join(timeout=2)
    metadata["exit_code"] = result
    try:
        if result != 0 or not clean.exists():
            _publish(reports, metadata, output, "Abnormal GUI exit" if result != 0 else "Exited without normal shutdown")
        if collector is None or not collector.is_alive():
            # Delete the marker last so incomplete cleanup remains recoverable.
            for path in (output, clean, marker):
                path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"Crash report could not be finalized; capture retained at {output}: {exc}", file=sys.stderr)
    return result


def launch(root: Path, module: str, callback) -> int:
    """Wrap a lazy GUI entrypoint, without importing Qt when logging is off."""
    child = os.environ.get("AG_DESKTOP_CRASH_CHILD") == str(root.resolve())
    if not child:
        if enabled(root):
            return supervise(root, module, sys.argv[1:])
        return callback()
    # Remove control flags before GUI-created analysis processes are spawned.
    os.environ.pop("AG_DESKTOP_CRASH_CHILD", None)
    clean = Path(os.environ.pop("AG_DESKTOP_CRASH_CLEAN"))
    faulthandler.enable(all_threads=True)
    old_hook, old_thread_hook = sys.excepthook, threading.excepthook
    def report_exception(kind, value, tb):
        print("Unhandled Python/Qt callback exception (may be nonfatal):", file=sys.stderr)
        traceback.print_exception(kind, value, tb)
    def report_thread(args):
        report_exception(args.exc_type, args.exc_value, args.exc_traceback)
    sys.excepthook = report_exception
    threading.excepthook = report_thread
    try:
        try:
            result = callback()
        except SystemExit as exc:
            if exc.code in (None, 0):
                clean.write_text("normal shutdown", encoding="utf-8")
            raise
        if result in (None, 0):
            clean.write_text("normal shutdown", encoding="utf-8")
        return result or 0
    finally:
        sys.excepthook, threading.excepthook = old_hook, old_thread_hook
