"""Reject unmanaged module launches before importing the desktop frontend."""
import sys
from pathlib import Path

from AgMark.gui.runtime_environment import require_managed_runtime


def launch() -> int:
    try:
        require_managed_runtime(Path(__file__).absolute().parent.parent)
    except (OSError, RuntimeError) as exc:
        print(f"[AgMark GUI] STARTUP FAILED: {exc}", file=sys.stderr)
        return 1
    from AgMark.gui.startup import main
    return main()


if __name__ == "__main__":
    from AgMark.gui.crash_logging import launch as supervised_launch
    raise SystemExit(supervised_launch(Path(__file__).resolve().parent.parent, "AgMark.gui", launch))
