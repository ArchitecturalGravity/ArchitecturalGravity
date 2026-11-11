"""Qt-backed presentation preference adapter for the bottom console."""

from __future__ import annotations

# Optional concrete Python desktop surface. Keeping these imports below the
# toolkit-independent state boundary lets centralized non-GUI tests import this
# module even when PySide6 is not installed.
from AgMark.gui.design_system.buttons import resolved_button
from AgMark.gui.design_system.console import resolved_console_presentation
from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS, LayoutMetrics
from AgMark.gui.design_system.surfaces import resolved_surface
from AgMark.gui.design_system.tabs import resolved_tab
from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    Theme,
    semantic_icon,
)
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    Typography,
)

try:
    from PySide6.QtCore import QRect, QSize, QSettings, Qt, Signal
    from PySide6.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QPainter,
        QSyntaxHighlighter,
        QTextCharFormat,
        QTextCursor,
    )
    from PySide6.QtWidgets import (
        QAbstractScrollArea,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QStackedWidget,
        QTabBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True

if PYSIDE6_AVAILABLE:

    class _QtSettingsPreferences:
        """Small integer mapping facade over QSettings for presentation preferences."""

        def __init__(self, settings: QSettings) -> None:
            self._settings = settings

        def get(self, key: str, default: object = None) -> object:
            return self._settings.value(key, default)

        def __setitem__(self, key: str, value: int) -> None:
            self._settings.setValue(key, value)
