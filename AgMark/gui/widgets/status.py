"""Reusable semantic status-badge widget for the ArcGrav desktop GUI.

The widget consumes an explicit caller-supplied label and semantic tone. It is
presentation-only: it never derives benchmark, lifecycle, evidence, scoring,
report, reconstruction, or verification authority from display text.
"""

from __future__ import annotations

from AgMark.gui.design_system.metrics import (
    DEFAULT_LAYOUT_METRICS,
    LayoutMetrics,
)
from AgMark.gui.design_system.status import (
    DEFAULT_STATUS_STYLES,
    ResolvedStatusBadge,
    StatusRegistry,
)
from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    Theme,
    semantic_icon,
)
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    Typography,
)

_STATUS_ICON_TEXT = {
    "status-success": "✓",
    "status-warning": "!",
    "status-error": "×",
    "status-active": "●",
    "status-neutral": "–",
}


def _icon_text(icon_key: str) -> str:
    """Return a visible non-color cue for a semantic status icon key."""

    return _STATUS_ICON_TEXT.get(icon_key, f"[{icon_key}]")


try:
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
except ImportError:
    PYSIDE6_AVAILABLE = False

else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:

    class StatusBadge(QWidget):
        """Compact status presentation that preserves caller-supplied semantics."""

        def __init__(
            self,
            label: str,
            tone: str,
            *,
            registry: StatusRegistry = DEFAULT_STATUS_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._registry = registry
            self._theme = theme
            self._typography = typography
            self._metrics = metrics
            self._resolved: ResolvedStatusBadge | None = None
            self._context_label: str | None = None
            self._icon_text_value = ""
            self._semantic_icon = None

            layout = QHBoxLayout(self)
            layout.setContentsMargins(
                metrics.metric("space-sm"),
                metrics.metric("space-xs"),
                metrics.metric("space-sm"),
                metrics.metric("space-xs"),
            )
            layout.setSpacing(metrics.metric("space-xs"))

            self._icon_label = QLabel(self)
            self._icon_label.setAccessibleName("Status cue")
            layout.addWidget(self._icon_label)

            self._text_label = QLabel(self)
            layout.addWidget(self._text_label)

            text_style = typography.style("metadata")
            font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
            font.setPixelSize(text_style.size_px)
            font.setWeight(QFont.Weight(text_style.weight))
            self._icon_label.setFont(font)
            self._text_label.setFont(font)

            self.set_status(label, tone)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def status(self) -> ResolvedStatusBadge:
            if self._resolved is None:
                raise RuntimeError("status badge has not been initialized")
            return self._resolved

        @property
        def label(self) -> str:
            return self.status.label

        @property
        def tone(self) -> str:
            return self.status.tone

        @property
        def icon_key(self) -> str:
            return self.status.icon_key

        @property
        def displayed_label(self) -> str:
            return self._text_label.text()

        def set_context_label(self, label: str | None) -> None:
            """Prefix the presentation without changing the underlying status."""
            if label is not None and (not isinstance(label, str) or not label.strip()):
                raise ValueError("context label must be a non-empty string or None")
            self._context_label = label
            self._update_displayed_label()

        def _update_displayed_label(self) -> None:
            text = self.label
            if self._context_label is not None:
                text = f"{self._context_label}: {text}"
            self._text_label.setText(text)
            self.setAccessibleName(text)

        @property
        def icon_text(self) -> str:
            return self._icon_text_value

        @property
        def semantic_icon(self):
            return self._semantic_icon

        def set_status(self, label: str, tone: str) -> None:
            """Apply explicit semantic presentation without inferring from label text."""

            resolved = self._registry.resolve(label, tone, theme=self._theme)
            self._resolved = resolved

            self._icon_text_value = _icon_text(resolved.icon_key)
            self._semantic_icon = semantic_icon(
                resolved.icon_key,
                theme=self._theme,
                size=14,
            )
            self._icon_label.setText("")
            self._icon_label.setPixmap(self._semantic_icon.pixmap(14, 14))
            self._icon_label.setAccessibleName(resolved.icon_key)
            self._icon_label.setProperty("semanticIconRole", resolved.icon_key)
            self._update_displayed_label()

            self.setObjectName("semanticStatusBadge")
            self.setProperty("arcgravSemanticComponent", "status-badge")
            self.setStyleSheet(
                'QWidget[arcgravSemanticComponent="status-badge"] {'
                f"background-color: {resolved.background};"
                f"border-radius: {self._metrics.metric('panel-radius')}px;"
                "}"
                'QWidget[arcgravSemanticComponent="status-badge"] QLabel {'
                f"color: {resolved.foreground};"
                "background: transparent;"
                "}"
            )

    from AgMark.gui.widgets.buttons import ActionButton

    class StatusDropdownButton(ActionButton):
        """Standard action button with a live semantic status and attached menu."""

        def __init__(self, label: str, tone: str, *, parent=None):
            super().__init__(label, "secondary", content_sized=True, parent=parent)
            self._context_label = None
            self.set_status(label, tone)

        @property
        def status(self):
            return self._status

        @property
        def label(self):
            return self._status.label

        @property
        def tone(self):
            return self._status.tone

        @property
        def icon_key(self):
            return self._status.icon_key

        @property
        def icon_text(self):
            return _icon_text(self.icon_key)

        @property
        def semantic_icon(self):
            return self.icon()

        def set_context_label(self, label):
            if label is not None and (not isinstance(label, str) or not label.strip()):
                raise ValueError("context label must be a non-empty string or None")
            self._context_label = label
            self._update_status_text()

        def _update_status_text(self):
            text = self.label
            if self._context_label is not None:
                text = f"{self._context_label}: {text}"
            self.set_label(text)

        def set_status(self, label, tone):
            self._status = DEFAULT_STATUS_STYLES.resolve(label, tone, theme=self._theme)
            self.set_icon_role(self.icon_key)
            self._update_status_text()


else:

    class StatusBadge:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for StatusBadge")

    StatusDropdownButton = StatusBadge


__all__ = [
    "PYSIDE6_AVAILABLE",
    "StatusBadge",
    "StatusDropdownButton",
]
