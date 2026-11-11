"""Rebuild only AgMark/Runtime/.venv; no backups or rollback."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

if __package__:
    from .runtime_environment import install_runtime_hook, plain_directory, runtime_environment
else:
    from runtime_environment import install_runtime_hook, plain_directory, runtime_environment


def fresh_setup(agmark_root: Path, run=None) -> Path:
    run = run or subprocess.run
    root = agmark_root.absolute()
    for path in (root, root / "gui"):
        plain_directory(path)
    requirements = root / "gui" / "requirements.txt"
    if not requirements.is_file() or requirements.is_symlink():
        raise RuntimeError(f"Production dependency metadata is missing or linked: {requirements}")
    runtime = root / "Runtime"
    target = runtime / ".venv"
    for path in (runtime, target):
        plain_directory(path)
    environment = runtime_environment(root, create=True)
    lock = runtime / ".setup-lock"
    plain_directory(lock)
    lock.mkdir()  # A second setup must not delete an environment being installed.
    creating = False
    try:
        if target.exists():
            shutil.rmtree(target)
        creating = True
        # Bootstrap without pip: install the strict temp policy before ensurepip
        # (and its child Python processes) can create temporary files.
        run([sys.executable, "-m", "venv", "--without-pip", str(target)], check=True, env=environment)
        install_runtime_hook(target, environment)
        python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([str(python), "-m", "ensurepip", "--upgrade", "--default-pip"], check=True, env=environment)
        run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-cache-dir", "--requirement", str(requirements)], check=True, env=environment)
        run([str(python), "-c", "import PySide6; from PySide6.QtWidgets import QApplication"],
            check=True, env=environment)
        print(f"[AgMark GUI] Fresh setup complete: {target}")
        return target
    except BaseException:
        if creating and target.exists():
            plain_directory(target)
            shutil.rmtree(target)
        raise
    finally:
        lock.rmdir()


def main() -> int:
    try:
        if sys.version_info.major != 3 or sys.version_info.minor not in (10, 11, 12, 13, 14):
            raise RuntimeError("Python 3.10 through 3.14 is required.")
        fresh_setup(Path(__file__).absolute().parent.parent)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[AgMark GUI] SETUP FAILED: {exc}", file=sys.stderr)
        print("Resolve the error and rerun AgMark/Windows_Setup.bat. No setup backups are kept; credentials are untouched.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
