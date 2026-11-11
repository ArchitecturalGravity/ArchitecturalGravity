"""Reusable presentation-only card and disclosure widgets.

These widgets preserve caller-supplied labels, content, availability, and
expansion state while consuming only shared design-system presentation tokens.
They never infer benchmark, lifecycle, evidence, scoring, report,
reconstruction, or verification authority from visible content.
"""

from __future__ import annotations

from AgMark.gui.design_system.metrics import (
    DEFAULT_LAYOUT_METRICS,
    LayoutMetrics,
)
from AgMark.gui.design_system.surfaces import (
    DEFAULT_SURFACES,
    ResolvedSurfaceStyle,
    SurfaceRegistry,
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


def _require_bool(value: bool, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:

    def _font(typography: Typography, role: str) -> QFont:
        text_style = typography.style(role)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPixelSize(text_style.size_px)
        font.setWeight(QFont.Weight(text_style.weight))
        return font


    def _surface_stylesheet(
        selector: str,
        surface: ResolvedSurfaceStyle,
    ) -> str:
        border = (
            "border: 0;"
            if surface.border is None or surface.border_width_px == 0
            else f"border: {surface.border_width_px}px solid {surface.border};"
        )
        return (
            f"{selector} {{"
            f"background-color: {surface.background};"
            f"{border}"
            f"border-radius: {surface.radius_px}px;"
            "}"
        )


    class CardWidget(QFrame):
        """Flat semantic card with caller-owned title, content, and availability."""

        def __init__(
            self,
            title: str,
            content: QWidget,
            *,
            available: bool = True,
            icon_role: str | None = None,
            title_role: str = "card-heading",
            compact: bool = False,
            surfaces: SurfaceRegistry = DEFAULT_SURFACES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            title = _require_visible_text(title, name="title")
            if not isinstance(content, QWidget):
                raise ValueError("content must be a QWidget")
            available = _require_bool(available, name="available")
            title_role = _require_visible_text(title_role, name="title_role")
            if title_role not in typography.styles:
                raise ValueError(f"unknown card title_role: {title_role!r}")

            super().__init__(parent)
            self._surfaces = surfaces
            self._theme = theme
            self._typography = typography
            self._metrics = metrics
            self._content_widget = content
            self._icon_role = icon_role
            self._title_role = title_role
            self._title_icon_label: QLabel | None = None
            self._surface = surfaces.resolve(
                "card",
                theme=theme,
                metrics=metrics,
            )
            self._available = True

            self.setObjectName("semanticCardWidget")
            self.setProperty("arcgravSemanticComponent", "card")
            self.setProperty("authoritySemantics", "presentation-only")

            layout = QVBoxLayout(self)
            padding = metrics.metric("space-md" if compact else "panel-padding")
            layout.setContentsMargins(padding, padding, padding, padding)
            layout.setSpacing(metrics.metric("space-xs" if compact else "related-gap"))

            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(metrics.metric("space-sm"))
            if icon_role is not None:
                if not isinstance(icon_role, str) or not icon_role.strip():
                    raise ValueError("icon_role must be None or a non-empty string")
                self._title_icon_label = QLabel(self)
                self._title_icon_label.setObjectName("semanticCardTitleIcon")
                self._title_icon_label.setProperty(
                    "semanticIconRole",
                    icon_role,
                )
                self._title_icon_label.setPixmap(
                    semantic_icon(icon_role, theme=theme).pixmap(18, 18)
                )
                header_layout.addWidget(self._title_icon_label)

            self._title_label = QLabel(title, self)
            self._title_label.setObjectName("semanticCardTitle")
            self._title_label.setProperty("arcgravSemanticComponent", "card-title")
            self._title_label.setProperty("typographyRole", title_role)
            self._title_label.setFont(_font(typography, title_role))
            header_layout.addWidget(self._title_label)
            header_layout.addStretch(1)
            layout.addLayout(header_layout)
            layout.addWidget(content, 1)

            self.setStyleSheet(
                _surface_stylesheet(
                    'QFrame[arcgravSemanticComponent="card"]',
                    self._surface,
                )
                + 'QLabel[arcgravSemanticComponent="card-title"] {'
                f"color: {theme.color('text-primary')};"
                "background: transparent;"
                "border: 0;"
                "}"
            )
            self.set_title(title)
            self.set_available(available)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def title(self) -> str:
            return self._title_label.text()

        @property
        def content_widget(self) -> QWidget:
            return self._content_widget

        @property
        def icon_role(self) -> str | None:
            return self._icon_role

        @property
        def title_role(self) -> str:
            return self._title_role

        @property
        def title_icon_label(self) -> QLabel | None:
            return self._title_icon_label

        @property
        def available(self) -> bool:
            return self._available

        @property
        def surface(self) -> ResolvedSurfaceStyle:
            return self._surface

        def set_title(self, title: str) -> None:
            """Replace visible title without deriving any semantic state from it."""

            title = _require_visible_text(title, name="title")
            self._title_label.setText(title)
            self.setAccessibleName(title)

        def set_available(self, available: bool) -> None:
            """Project explicit caller availability without inferring permission."""

            available = _require_bool(available, name="available")
            self._available = available
            self.setEnabled(available)
            self.setProperty("available", available)
            self.setAccessibleDescription(
                "Available presentation" if available else "Unavailable presentation"
            )


    class DisclosureWidget(QFrame):
        """Expandable content controlled only by explicit caller state or activation."""

        def __init__(
            self,
            label: str,
            content: QWidget,
            *,
            expanded: bool,
            available: bool = True,
            surfaces: SurfaceRegistry = DEFAULT_SURFACES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            label = _require_visible_text(label, name="label")
            if not isinstance(content, QWidget):
                raise ValueError("content must be a QWidget")
            expanded = _require_bool(expanded, name="expanded")
            available = _require_bool(available, name="available")

            super().__init__(parent)
            self._surfaces = surfaces
            self._theme = theme
            self._typography = typography
            self._metrics = metrics
            self._content_widget = content
            self._surface = surfaces.resolve(
                "grouped-control",
                theme=theme,
                metrics=metrics,
            )
            self._expanded = False
            self._available = True

            self.setObjectName("semanticDisclosureWidget")
            self.setProperty("arcgravSemanticComponent", "disclosure")
            self.setProperty("authoritySemantics", "presentation-only")

            layout = QVBoxLayout(self)
            padding = metrics.metric("space-sm")
            layout.setContentsMargins(padding, padding, padding, padding)
            layout.setSpacing(metrics.metric("related-gap"))

            self._toggle = QToolButton(self)
            self._toggle.setObjectName("semanticDisclosureToggle")
            self._toggle.setProperty("arcgravSemanticComponent", "disclosure-toggle")
            self._toggle.setCheckable(True)
            self._toggle.setAutoRaise(True)
            self._toggle.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            self._toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self._toggle.setFont(_font(typography, "body"))
            self._toggle.toggled.connect(self.set_expanded)
            layout.addWidget(self._toggle)
            layout.addWidget(content)

            focus = theme.color("focus-ring")
            text = theme.color("text-primary")
            self.setStyleSheet(
                _surface_stylesheet(
                    'QFrame[arcgravSemanticComponent="disclosure"]',
                    self._surface,
                )
                + 'QToolButton[arcgravSemanticComponent="disclosure-toggle"] {'
                "background: transparent;"
                "border: 0;"
                f"color: {text};"
                f"padding: {metrics.metric('space-xs')}px;"
                "text-align: left;"
                "}"
                + 'QToolButton[arcgravSemanticComponent="disclosure-toggle"]:focus {'
                f"border: {metrics.metric('border-width')}px solid {focus};"
                "}"
            )

            self.set_label(label)
            self.set_expanded(expanded)
            self.set_available(available)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def label(self) -> str:
            return self._toggle.text()

        @property
        def content_widget(self) -> QWidget:
            return self._content_widget

        @property
        def expanded(self) -> bool:
            return self._expanded

        @property
        def available(self) -> bool:
            return self._available

        @property
        def surface(self) -> ResolvedSurfaceStyle:
            return self._surface

        @property
        def toggle_button(self) -> QToolButton:
            return self._toggle

        def set_label(self, label: str) -> None:
            """Replace visible label without changing expansion or availability."""

            label = _require_visible_text(label, name="label")
            self._toggle.setText(label)
            self._toggle.setAccessibleName(label)
            self.setAccessibleName(label)

        def set_expanded(self, expanded: bool) -> None:
            """Project explicit expansion state without deriving benchmark meaning."""

            expanded = _require_bool(expanded, name="expanded")
            self._expanded = expanded

            previous = self._toggle.blockSignals(True)
            try:
                self._toggle.setChecked(expanded)
            finally:
                self._toggle.blockSignals(previous)

            self._toggle.setArrowType(
                Qt.ArrowType.DownArrow
                if expanded
                else Qt.ArrowType.RightArrow
            )
            self._content_widget.setVisible(expanded)
            self.setProperty("expanded", expanded)
            self._update_accessibility()

        def set_available(self, available: bool) -> None:
            """Project explicit caller availability without rewriting expansion state."""

            available = _require_bool(available, name="available")
            self._available = available
            self.setEnabled(available)
            self.setProperty("available", available)
            self._update_accessibility()

        def _update_accessibility(self) -> None:
            state = "Expanded" if self._expanded else "Collapsed"
            if not self._available:
                state += "; unavailable"
            self._toggle.setAccessibleDescription(state)
            self.setAccessibleDescription(state)


else:

    class CardWidget:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for CardWidget")


    class DisclosureWidget:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for DisclosureWidget")


__all__ = [
    "CardWidget",
    "DisclosureWidget",
    "PYSIDE6_AVAILABLE",
]
