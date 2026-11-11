"""Reusable semantic action widgets for the ArcGrav desktop GUI.

These widgets consume explicit caller-supplied presentation roles. They do not
infer benchmark, lifecycle, evidence, scoring, report, reconstruction, or
verification authority from labels, icons, or local interaction state.
"""

from __future__ import annotations

from AgMark.gui.design_system.buttons import (
    DEFAULT_BUTTON_STYLES,
    ButtonRegistry,
    ResolvedButtonStyle,
)
from AgMark.gui.design_system.metrics import (
    DEFAULT_LAYOUT_METRICS,
    LayoutMetrics,
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


def _require_visible_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")
    return value


try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase, QIcon
    from PySide6.QtWidgets import QPushButton, QToolButton, QWidget
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:

    def _font(typography: Typography) -> QFont:
        text_style = typography.style("body")
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPixelSize(text_style.size_px)
        font.setWeight(QFont.Weight(text_style.weight))
        return font


    def _stylesheet(
        selector: str,
        resolved: ResolvedButtonStyle,
        *,
        theme: Theme,
        metrics: LayoutMetrics,
    ) -> str:
        border_width = metrics.metric("border-width")
        radius = metrics.metric("panel-radius")
        vertical_padding = metrics.metric("space-xs")
        horizontal_padding = metrics.metric(
            "space-sm" if resolved.compact else "space-md"
        )
        focus = theme.color("focus-ring")
        primary = resolved.background == theme.color("accent-primary")
        hover_background = theme.color("accent-primary-hover" if primary else "surface-selected")
        hover_border = resolved.border if resolved.border == theme.color("state-error") else theme.color("accent-primary-hover")
        return (
            f"{selector} {{"
            f"background-color: {resolved.background};"
            f"border: {border_width}px solid {resolved.border};"
            f"border-radius: {radius}px;"
            f"color: {resolved.text};"
            f"padding: {vertical_padding}px {horizontal_padding}px;"
            "}"
            f"{selector}:hover:enabled {{"
            f"background-color: {hover_background};"
            f"border-color: {hover_border};"
            "}"
            f"{selector}:pressed:enabled, {selector}:checked:enabled {{"
            f"background-color: {hover_background};"
            f"border-color: {hover_border};"
            "}"
            f"{selector}:focus:enabled {{"
            f"border: {border_width}px solid {focus};"
            "}"
            f"{selector}:disabled {{"
            f"background-color: {theme.color('surface-panel')};"
            f"border-color: {theme.color('border-default')};"
            f"color: {theme.color('text-muted')};"
            "}"
        )


    class ActionButton(QPushButton):
        """Text action button with caller-supplied semantic presentation."""

        def __init__(
            self,
            label: str,
            role: str,
            *,
            icon_role: str | None = None,
            content_sized: bool = False,
            registry: ButtonRegistry = DEFAULT_BUTTON_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            label = _require_visible_text(label, name="label")
            super().__init__(label, parent)
            self._registry = registry
            self._theme = theme
            self._typography = typography
            self._metrics = metrics
            self._role = ""
            self._icon_role: str | None = None
            self._presentation: ResolvedButtonStyle | None = None

            self.setObjectName("semanticActionButton")
            self.setProperty("arcgravSemanticComponent", "action-button")
            self.setAccessibleName(label)
            self.setFont(_font(typography))
            if not content_sized:
                self.setMinimumHeight(metrics.metric("control-height"))
            self.set_role(role)
            self.set_icon_role(icon_role)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def role(self) -> str:
            return self._role

        @property
        def displayed_label(self) -> str:
            return self.text()

        @property
        def icon_role(self) -> str | None:
            return self._icon_role

        @property
        def presentation(self) -> ResolvedButtonStyle:
            if self._presentation is None:
                raise RuntimeError("action button has not been initialized")
            return self._presentation

        @property
        def non_color_indicator(self) -> str | None:
            return self.presentation.non_color_indicator

        def set_label(self, label: str) -> None:
            """Replace visible text without deriving or changing semantic role."""

            label = _require_visible_text(label, name="label")
            self.setText(label)
            self.setAccessibleName(label)

        def set_icon_role(self, icon_role: str | None) -> None:
            """Apply an optional repository-owned semantic presentation icon."""

            if icon_role is None:
                self._icon_role = None
                self.setIcon(QIcon())
                self.setProperty("semanticIconRole", "")
                return
            if not isinstance(icon_role, str) or not icon_role.strip():
                raise ValueError("icon_role must be None or a non-empty string")
            self.setIcon(semantic_icon(icon_role, theme=self._theme))
            self._icon_role = icon_role
            self.setProperty("semanticIconRole", icon_role)

        def set_role(self, role: str) -> None:
            """Apply an explicit semantic role and its caller-selected availability."""

            resolved = self._registry.resolve(role, theme=self._theme)
            self._role = role
            self._presentation = resolved
            self.setEnabled(resolved.enabled)
            self.setProperty("semanticRole", role)
            self.setProperty(
                "nonColorIndicator", resolved.non_color_indicator or ""
            )
            self.setAccessibleDescription(resolved.non_color_indicator or "")
            self.setStyleSheet(
                _stylesheet(
                    'QPushButton[arcgravSemanticComponent="action-button"]',
                    resolved,
                    theme=self._theme,
                    metrics=self._metrics,
                )
            )


    class IconButton(QToolButton):
        """Compact icon/cue action with an explicit accessible name and role."""

        def __init__(
            self,
            icon_text: str,
            accessible_name: str,
            role: str = "contextual",
            *,
            registry: ButtonRegistry = DEFAULT_BUTTON_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            icon_text = _require_visible_text(icon_text, name="icon_text")
            accessible_name = _require_visible_text(
                accessible_name, name="accessible_name"
            )
            super().__init__(parent)
            self._registry = registry
            self._theme = theme
            self._typography = typography
            self._metrics = metrics
            self._role = ""
            self._presentation: ResolvedButtonStyle | None = None

            self.setObjectName("semanticIconButton")
            self.setProperty("arcgravSemanticComponent", "icon-button")
            self.setText(icon_text)
            self.setAccessibleName(accessible_name)
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.setFont(_font(typography))
            self.set_role(role)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def role(self) -> str:
            return self._role

        @property
        def icon_text(self) -> str:
            return self.text()

        @property
        def presentation(self) -> ResolvedButtonStyle:
            if self._presentation is None:
                raise RuntimeError("icon button has not been initialized")
            return self._presentation

        @property
        def non_color_indicator(self) -> str | None:
            return self.presentation.non_color_indicator

        def set_role(self, role: str) -> None:
            """Apply an explicit semantic role without inspecting icon or label text."""

            resolved = self._registry.resolve(role, theme=self._theme)
            self._role = role
            self._presentation = resolved
            self.setEnabled(resolved.enabled)
            self.setProperty("semanticRole", role)
            self.setProperty(
                "nonColorIndicator", resolved.non_color_indicator or ""
            )
            self.setAccessibleDescription(resolved.non_color_indicator or "")

            height = self._metrics.metric("control-height")
            if resolved.compact:
                height -= self._metrics.metric("space-sm")
            self.setFixedSize(height, height)
            self.setStyleSheet(
                _stylesheet(
                    'QToolButton[arcgravSemanticComponent="icon-button"]',
                    resolved,
                    theme=self._theme,
                    metrics=self._metrics,
                )
            )

else:

    class ActionButton:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for ActionButton")


    class IconButton:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for IconButton")


__all__ = [
    "ActionButton",
    "IconButton",
    "PYSIDE6_AVAILABLE",
]
