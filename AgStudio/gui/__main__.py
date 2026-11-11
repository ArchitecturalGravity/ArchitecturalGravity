from multiprocessing import freeze_support
from pathlib import Path

from .crash_logging import launch


def _main() -> int:
    from .app import main
    return main()


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(launch(Path(__file__).resolve().parent.parent, "AgStudio.gui", _main))
