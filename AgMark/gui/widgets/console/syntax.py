"""Syntax highlighting for the bottom console."""

from __future__ import annotations

import re

from .state import (
    BottomConsoleState,
    CONSOLE_TABS,
    LAST_EXPANDED_HEIGHT_KEY,
    RAW_RESPONSE_UNAVAILABLE,
    _require_generation_id,
    _require_height,
    _require_tab,
)

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

    _LIVE_OUTPUT_PATTERN = re.compile(
        r"^(\[\d{2}:\d{2}:\d{2}\])(\s+)(\[[^\]\r\n]+\])(\s+\|\s?)(.*)$"
    )
    _DIAGNOSTIC_PATTERN = re.compile(
        r"^(\[[^\]\r\n]+\])(\s+)([A-Za-z][A-Za-z0-9_-]*)(\s+)(.*)$"
    )
    _JSON_STRING_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"')
    _JSON_NUMBER_PATTERN = re.compile(
        r"(?<![\w.])-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])"
    )
    _JSON_LITERAL_PATTERN = re.compile(r"\b(?:true|false|null)\b")


    def _level_color(level: str, presentation) -> str:
        normalized = level.strip("[]").upper()
        if normalized in {"WARN", "WARNING"}:
            return presentation.warning
        if normalized in {"ERROR", "ERR", "FATAL"}:
            return presentation.error
        if normalized in {"PROGRESS", "RUNNING"}:
            return presentation.progress
        return presentation.info


    def _char_format(color: str, *, bold: bool = False) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(color))
        if bold:
            text_format.setFontWeight(QFont.Weight.DemiBold)
        return text_format


    class _ConsoleSyntaxHighlighter(QSyntaxHighlighter):
        """Presentation-only semantic formatting that never changes source text."""

        def __init__(self, document, *, tab: str, presentation) -> None:
            super().__init__(document)
            self._tab = _require_tab(tab)
            self._presentation = presentation

        def _format_match(
            self,
            match: re.Match[str],
            group: int,
            color: str,
            *,
            bold: bool = False,
        ) -> None:
            start, end = match.span(group)
            self.setFormat(start, end - start, _char_format(color, bold=bold))

        def highlightBlock(self, text: str) -> None:
            # Formatting is optional. A very long unbroken model response must
            # not stall rendering in regex/string-span highlighting work.
            if len(text) > 16384:
                return
            if self._tab in {"Diagnostics", "Environment"}:
                match = _LIVE_OUTPUT_PATTERN.match(text) or _DIAGNOSTIC_PATTERN.match(text)
                if match is not None:
                    self._format_match(match, 1, self._presentation.muted)
                    self._format_match(
                        match,
                        3,
                        _level_color(match.group(3), self._presentation),
                        bold=True,
                    )
                return

            if text in {"Input:", "Output:"} or text.endswith((" - Input:", " - Output:")):
                self.setFormat(0, len(text), _char_format(self._presentation.info, bold=True))
                return

            string_spans: list[tuple[int, int]] = []
            for match in _JSON_STRING_PATTERN.finditer(text):
                start, end = match.span()
                string_spans.append((start, end))
                remainder = text[end:]
                is_property = re.match(r"\s*:", remainder) is not None
                color = (
                    self._presentation.warning
                    if is_property
                    else self._presentation.progress
                )
                self.setFormat(start, end - start, _char_format(color))

            def inside_string(position: int) -> bool:
                return any(start <= position < end for start, end in string_spans)

            for pattern in (_JSON_NUMBER_PATTERN, _JSON_LITERAL_PATTERN):
                for match in pattern.finditer(text):
                    if not inside_string(match.start()):
                        self.setFormat(
                            match.start(),
                            match.end() - match.start(),
                            _char_format(self._presentation.info),
                        )
