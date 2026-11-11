"""Production application entry/composition root for the ArcGrav desktop GUI."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from AgMark.gui.diagnostics import (
    present_startup_failure,
    startup_failure_diagnostic,
)
from AgMark.gui.runtime_environment import require_managed_runtime


_NATIVE_ERROR_ENV = "AGMARK_GUI_NATIVE_STARTUP_ERRORS"
_APPLICATION_NAME = "AgMark"
_AGMARK_ROOT = Path(__file__).resolve().parents[1]


def repository_root() -> Path:
    """Return the repository root containing the AgMark package."""

    return Path(__file__).resolve().parents[2]


def _native_error_requested() -> bool:
    value = os.environ.get(_NATIVE_ERROR_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_production_application(argv: list[str] | None = None):
    """Construct the one production desktop composition from repository authority."""

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is unavailable in the active Python environment. "
            "Run AgMark\\Windows_Setup.bat before launching the desktop GUI."
        ) from exc

    from AgMark.gui.application import BenchmarkDesktopApplication
    from AgMark.gui.design_system.theme import (
        apply_application_theme,
        arcgrav_application_icon,
    )

    application = QApplication.instance()
    if application is None:
        application = QApplication(list(sys.argv if argv is None else argv))

    application.setApplicationName(_APPLICATION_NAME)
    application.setApplicationDisplayName(
        "Architectural Gravity Benchmark"
    )
    apply_application_theme(application)

    application_icon = arcgrav_application_icon()
    application.setWindowIcon(application_icon)

    desktop = BenchmarkDesktopApplication.from_repository_authority(
        application_icon=application_icon,
        repository_root=repository_root(),
    )
    return application, desktop


def main(argv: list[str] | None = None) -> int:
    """Start only in the managed runtime; no alternate runtime or cache cleanup."""

    try:
        require_managed_runtime(_AGMARK_ROOT)
        application, desktop = create_production_application(argv)
        desktop.show()
    except Exception as exc:
        present_startup_failure(
            startup_failure_diagnostic(exc),
            native=_native_error_requested(),
        )
        return 1

    return int(application.exec())


__all__ = [
    "create_production_application",
    "main",
    "repository_root",
]
