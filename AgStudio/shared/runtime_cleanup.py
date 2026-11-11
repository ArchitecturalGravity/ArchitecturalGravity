"""Retire the pre-Runtime layout after setup has verified its replacement.

Run as a script with Runtime/.venv's Python; importing AgStudio is unnecessary.
Only generated artifacts beneath this AgStudio checkout are cleanup targets.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import sys


def _is_link(path: Path) -> bool:
    """Include Windows junctions/reparse points on supported Python versions."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def cleanup_legacy_runtime(studio: Path) -> None:
    """Remove recognized legacy artifacts, without traversing linked folders.

    The caller must verify the new environment before calling this function.
    Runtime itself and hidden development folders are never traversed.
    """
    studio = studio.resolve(strict=True)
    legacy_venv = studio / ".venv"
    if os.path.lexists(legacy_venv):
        if (_is_link(legacy_venv) or not legacy_venv.is_dir()
                or not (legacy_venv / "pyvenv.cfg").is_file()):
            raise OSError(f"Refusing to remove unrecognized legacy environment: {legacy_venv}")
        shutil.rmtree(legacy_venv)

    def walk_error(error: OSError) -> None:
        raise error

    for directory, names, _ in os.walk(studio, topdown=True, onerror=walk_error,
                                       followlinks=False):
        parent = Path(directory)
        for name in names[:]:
            path = parent / name
            if name == "__pycache__":
                if _is_link(path):
                    raise OSError(f"Refusing to remove linked cache directory: {path}")
                shutil.rmtree(path)
                names.remove(name)
            elif (path == studio / "Runtime" or name.startswith(".")
                  or _is_link(path)):
                names.remove(name)


def main() -> int:
    studio = Path(__file__).resolve().parents[1]
    # A direct/manual invocation must not remove the interpreter running it.
    if Path(sys.prefix).resolve() != studio / "Runtime" / ".venv":
        print("[AgStudio] Cleanup requires Runtime/.venv's Python.", file=sys.stderr)
        return 1
    try:
        cleanup_legacy_runtime(studio)
    except OSError as exc:
        print(f"[AgStudio] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
