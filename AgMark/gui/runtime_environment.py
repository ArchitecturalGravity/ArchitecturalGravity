"""One fail-closed policy for the managed AgMark/Runtime environment."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from typing import Mapping


_POLICY_VERSION = 2
_RUNTIME_KEYS = ("PYTHONPYCACHEPREFIX", "TEMP", "TMP", "TMPDIR", "PIP_CACHE_DIR")


def plain_directory(path: Path) -> None:
    """Refuse links, junctions, non-directories and paths through linked parents."""
    if path.is_symlink() or path.resolve() != path.absolute():
        raise RuntimeError(f"Refusing linked setup path: {path}")
    if path.exists():
        if not path.is_dir():
            raise RuntimeError(f"Refusing non-directory setup path: {path}")
        if getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise RuntimeError(f"Refusing reparse-point setup path: {path}")


def _writable_directory(path: Path) -> None:
    """Probe this exact directory; never ask tempfile to choose a destination."""
    descriptor, name = tempfile.mkstemp(prefix=".agmark-check-", dir=str(path))
    try:
        os.close(descriptor)
    finally:
        os.unlink(name)


def runtime_environment(
    root: Path, base: Mapping[str, str] | None = None, *, create: bool = False,
) -> dict[str, str]:
    """Validate the sole runtime layout; only setup may create its directories."""
    root = Path(root).absolute()
    runtime = root / "Runtime"
    directories = (root, runtime, runtime / "__pycache__", runtime / "temp", runtime / "pip-cache")
    for path in directories:
        plain_directory(path)
    if not root.is_dir():
        raise RuntimeError(f"AgMark root is missing: {root}")
    for path in directories[1:]:
        if create:
            path.mkdir(exist_ok=True)
        if not path.is_dir():
            raise RuntimeError(f"Required Runtime directory is missing: {path}. Run AgMark/Windows_Setup.bat.")
    for path in directories[2:]:
        _writable_directory(path)
    environment = dict(os.environ if base is None else base)
    environment.update({
        "PYTHONPYCACHEPREFIX": str(runtime / "__pycache__"),
        "TEMP": str(runtime / "temp"),
        "TMP": str(runtime / "temp"),
        "TMPDIR": str(runtime / "temp"),
        "PIP_CACHE_DIR": str(runtime / "pip-cache"),
    })
    return environment


def _require_interpreter(root: Path) -> None:
    target = root / "Runtime" / ".venv"
    plain_directory(target)
    if sys.flags.no_site or Path(sys.prefix).absolute() != target or sys.prefix == sys.base_prefix:
        raise RuntimeError("AgMark requires Runtime/.venv with site initialization enabled. Run AgMark/Windows_Setup.bat and use the AgMark launchers.")


def activate_runtime(root: Path) -> None:
    """Called by the venv hook before application/pip imports, never by a fallback."""
    root = Path(root).absolute()
    _require_interpreter(root)
    environment = runtime_environment(root)
    sys.pycache_prefix = environment["PYTHONPYCACHEPREFIX"]
    # Setting only TMPDIR permits tempfile's system-directory search. Pin its
    # public cached default instead: later missing/unwritable paths must fail.
    tempfile.tempdir = environment["TMPDIR"]
    os.environ.update({key: environment[key] for key in _RUNTIME_KEYS})
    sys._agmark_runtime_policy = (_POLICY_VERSION, root)


def _same_path(value: object, expected: str) -> bool:
    # Windows paths are case-insensitive; require the same path, not spelling.
    return isinstance(value, str) and Path(value) == Path(expected)


def require_managed_runtime(root: Path) -> None:
    """Reject absent/old hooks, unmanaged interpreters, and altered runtime paths."""
    root = Path(root).absolute()
    _require_interpreter(root)
    if getattr(sys, "_agmark_runtime_policy", None) != (_POLICY_VERSION, root):
        raise RuntimeError("AgMark Runtime startup hook is missing or outdated. Run AgMark/Windows_Setup.bat.")
    environment = runtime_environment(root)
    if (not _same_path(sys.pycache_prefix, environment["PYTHONPYCACHEPREFIX"])
            or not _same_path(tempfile.tempdir, environment["TMPDIR"])
            or any(not _same_path(os.environ.get(key), environment[key]) for key in _RUNTIME_KEYS)):
        raise RuntimeError("AgMark Runtime cache/temp settings were changed. Use the AgMark launchers; no alternate location is supported.")


def install_runtime_hook(target: Path, environment: Mapping[str, str]) -> None:
    """Install a fail-closed venv-local hook; no global site or environment edits."""
    root = target.parent.parent
    expected = runtime_environment(root)
    if any(environment.get(key) != expected[key] for key in _RUNTIME_KEYS):
        raise RuntimeError("Cannot install a hook with non-Runtime paths.")
    relative = "Lib/site-packages" if os.name == "nt" else (
        f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    )
    site_packages = target / relative
    plain_directory(site_packages)
    if not site_packages.is_dir():
        raise RuntimeError(f"Virtual environment site-packages is missing: {site_packages}")
    # site.py catches ordinary .pth exceptions and continues. Convert every
    # bootstrap failure to SystemExit so application code cannot run unpinned.
    # Execute the one source policy without writing a source-adjacent cache.
    code = '''try:
    _agmark_no_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    _agmark_root = os.path.dirname(os.path.dirname(sys.prefix))
    _agmark_source = os.path.join(_agmark_root, "gui", "runtime_environment.py")
    _agmark_namespace = {"__name__": "_agmark_runtime_hook", "__file__": _agmark_source}
    with open(_agmark_source, "rb") as _agmark_file:
        exec(compile(_agmark_file.read(), _agmark_source, "exec"), _agmark_namespace)
    _agmark_namespace["activate_runtime"](_agmark_root)
    sys.dont_write_bytecode = _agmark_no_bytecode
except BaseException as _agmark_error:
    raise SystemExit("AgMark Runtime initialization failed: " + str(_agmark_error))
'''
    (site_packages / "00_agmark_runtime.pth").write_text(
        "import os, sys; exec(" + ascii(code) + ")\n", encoding="utf-8",
    )
