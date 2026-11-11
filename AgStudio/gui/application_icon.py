"""Application artwork and Windows taskbar identity for the Python launcher."""
from pathlib import Path
import sys

from PySide6.QtGui import QIcon


ICON_DIRECTORY = Path(__file__).resolve().with_name("icons")
WINDOWS_APP_ID = "ArchitecturalGravity.AgStudio"


def application_icon() -> QIcon:
    # Windows receives native multi-resolution artwork; SVG scales on other hosts.
    suffix = "ico" if sys.platform == "win32" else "svg"
    return QIcon(str(ICON_DIRECTORY / f"agstudio.{suffix}"))


def set_windows_app_id() -> None:
    """Keep the running editor separate from Python's default taskbar group.

    Call before constructing QApplication or any native windows. This changes
    only this process; it does not create shortcuts or alter Python's executable.
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except (AttributeError, OSError):
        # An unavailable shell API must not prevent the editor from opening.
        pass
