"""Semantic presentation tokens for the ArcGrav desktop GUI.

This module is presentation-only.  It centralizes the design-system palette so
feature modules can consume semantic names without duplicating literal colors or
creating benchmark, evidence, lifecycle, report, or verification authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType

from AgMark.gui.design_system.metrics import (
    DEFAULT_LAYOUT_METRICS,
    LayoutMetrics,
)
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    Typography,
)


_HEX_COLOR = re.compile(r"^#[0-9A-F]{6}$")

REQUIRED_COLOR_TOKENS = frozenset(
    {
        "surface-background",
        "surface-status-bar",
        "surface-panel",
        "surface-selected",
        "border-default",
        "border-strong",
        "text-primary",
        "text-secondary",
        "text-muted",
        "accent-primary",
        "accent-primary-hover",
        "state-success",
        "state-success-surface",
        "state-warning",
        "state-warning-surface",
        "state-error",
        "state-error-surface",
        "state-active",
        "state-active-surface",
        "state-neutral",
        "state-neutral-surface",
        "console-background",
        "console-text",
        "console-muted",
        "console-info",
        "console-progress",
        "console-warning",
        "focus-ring",
    }
)


SEMANTIC_ICON_ROLES = frozenset(
    {
        "benchmark-start",
        "clear",
        "collapse",
        "console",
        "current-run-boundary",
        "current-run-plan",
        "current-run-treatments",
        "expand",
        "information",
        "plan-accept",
        "plan-build",
        "run-delete",
        "status-active",
        "status-error",
        "status-neutral",
        "status-success",
        "status-warning",
    }
)


@dataclass(frozen=True, slots=True)
class Theme:
    """Immutable semantic color theme.

    Theme construction validates only structural design-system requirements.
    Accessibility contrast remains a rendering-level conformance obligation.
    """

    name: str
    colors: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("theme name must be non-empty")

        normalized = dict(self.colors)
        missing = REQUIRED_COLOR_TOKENS.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"theme is missing required semantic tokens: {joined}")

        invalid = {
            token: value
            for token, value in normalized.items()
            if not isinstance(token, str)
            or not token
            or not isinstance(value, str)
            or _HEX_COLOR.fullmatch(value) is None
        }
        if invalid:
            joined = ", ".join(
                f"{token!r}={value!r}" for token, value in sorted(invalid.items())
            )
            raise ValueError(f"theme contains invalid semantic colors: {joined}")

        object.__setattr__(self, "colors", MappingProxyType(normalized))

    def color(self, token: str) -> str:
        """Return the exact color registered for a semantic token."""

        try:
            return self.colors[token]
        except KeyError as exc:
            raise KeyError(f"unknown semantic color token: {token}") from exc


DEFAULT_LIGHT_THEME = Theme(
    name="default-light",
    colors={
        "surface-background": "#F3F8FC",
        "surface-status-bar": "#D8DEE7",
        "surface-panel": "#FFFFFF",
        "surface-selected": "#DEEEFE",
        "border-default": "#D7E3EF",
        "border-strong": "#B8C9DC",
        "text-primary": "#0B1748",
        "text-secondary": "#44527A",
        "text-muted": "#6C7A99",
        "accent-primary": "#005FFD",
        "accent-primary-hover": "#0052DF",
        "state-success": "#0AA12A",
        "state-success-surface": "#E9F8EA",
        "state-warning": "#F39A00",
        "state-warning-surface": "#FFF3DE",
        "state-error": "#F0212D",
        "state-error-surface": "#FDE7EA",
        "state-active": "#0B73FF",
        "state-active-surface": "#E7F2FF",
        "state-neutral": "#71809F",
        "state-neutral-surface": "#EEF2F7",
        "console-background": "#18212C",
        "console-text": "#F2F5F8",
        "console-muted": "#9AA8BA",
        "console-info": "#31B7FF",
        "console-progress": "#43D35C",
        "console-warning": "#FFB423",
        "focus-ring": "#0B73FF",
    },
)


def color(token: str, *, theme: Theme = DEFAULT_LIGHT_THEME) -> str:
    """Resolve a semantic color without exposing feature code to palette literals."""

    return theme.color(token)


def compact_splitter_handle_extent(
    *,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
) -> int:
    """Return the semantic interactive extent for shell splitter handles.

    The hit target is intentionally wider than the painted separator.  The
    application stylesheet uses the same extent to leave only the semantic
    border-width visible, keeping splitters directly draggable without exposing
    toolkit-default oversized gutters.
    """

    return metrics.metric("space-sm") + metrics.metric("border-width")


def application_style_sheet(
    *,
    theme: Theme = DEFAULT_LIGHT_THEME,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
    typography: Typography = DEFAULT_TYPOGRAPHY,
) -> str:
    """Return the deterministic application-level ArcGrav Qt style sheet.

    The application sheet binds native shell primitives that do not own a
    reusable semantic widget style. Component-local style sheets remain free to
    provide more-specific semantic treatments.
    """

    body = typography.style("body")
    section = typography.style("section-heading")
    workspace_title = typography.style("workspace-title")
    splitter_extent = compact_splitter_handle_extent(metrics=metrics)
    separator_width = metrics.metric("border-width")
    divider_margin = max(
        0,
        (splitter_extent - separator_width) // 2,
    )
    separator_start = divider_margin / splitter_extent
    separator_end = (divider_margin + separator_width) / splitter_extent
    separator_epsilon = 1 / (splitter_extent * 1000)
    separator_before = max(0.0, separator_start - separator_epsilon)
    separator_after = min(1.0, separator_end + separator_epsilon)
    splitter_border = theme.color("border-default")

    return f"""
QMainWindow {{
    background-color: {theme.color("surface-background")};
    color: {theme.color("text-primary")};
    font-size: {body.size_px}px;
}}
QWidget#upperWorkArea,
QScrollArea#benchmarkWorkspaceScroll,
QScrollArea#workspaceTabScroll,
QScrollArea#currentRunScroll,
QWidget#benchmarkWorkspaceViewport,
QFrame#benchmarkWorkspace,
QFrame#currentRunRegion,
QWidget[projectionState="unavailable"] {{
    background-color: {theme.color("surface-background")};
    color: {theme.color("text-primary")};
}}
QFrame#benchmarkSidebar,
QScrollArea#benchmarkSidebarScroll,
QWidget#benchmarkSidebarContent {{
    background-color: {theme.color("surface-panel")};
    color: {theme.color("text-primary")};
    border: 0px;
}}
QScrollArea#sidebarConfigurationScroll {{
    background-color: {theme.color("surface-panel")};
    color: {theme.color("text-primary")};
    border: {metrics.metric("border-width")}px solid {theme.color("border-default")};
    border-radius: {metrics.metric("panel-radius")}px;
}}
QWidget#sidebarConfigurationContent {{
    background-color: {theme.color("surface-panel")};
    color: {theme.color("text-primary")};
    border: 0px;
}}
QLabel#currentRunHeading {{
    color: {theme.color("text-primary")};
    font-size: {workspace_title.size_px}px;
    font-weight: {workspace_title.weight};
}}
QLabel#sidebarSectionHeading {{
    color: {theme.color("text-primary")};
    font-size: {section.size_px}px;
    font-weight: {section.weight};
}}
QLabel#workspaceEmptyStateMessage {{
    color: {theme.color("text-muted")};
    font-size: {body.size_px}px;
}}
QStatusBar#shellStatusBar {{
    background-color: {theme.color("surface-status-bar")};
    color: {theme.color("text-secondary")};
    border-bottom: {metrics.metric("border-width")}px solid {theme.color("border-strong")};
}}
QStatusBar#shellStatusBar::item {{
    border: 0px;
}}
QSplitter#sidebarWorkspaceSplitter::handle {{
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 rgba(0, 0, 0, 0),
        stop: {separator_before:.6f} rgba(0, 0, 0, 0),
        stop: {separator_start:.6f} {splitter_border},
        stop: {separator_end:.6f} {splitter_border},
        stop: {separator_after:.6f} rgba(0, 0, 0, 0),
        stop: 1 rgba(0, 0, 0, 0)
    );
}}
QSplitter#workspaceConsoleSplitter::handle {{
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 rgba(0, 0, 0, 0),
        stop: {separator_before:.6f} rgba(0, 0, 0, 0),
        stop: {separator_start:.6f} {splitter_border},
        stop: {separator_end:.6f} {splitter_border},
        stop: {separator_after:.6f} rgba(0, 0, 0, 0),
        stop: 1 rgba(0, 0, 0, 0)
    );
}}
QMenu {{
    background-color: {theme.color("surface-panel")};
    color: {theme.color("text-primary")};
    border: {metrics.metric("border-width")}px solid {theme.color("border-default")};
    border-radius: {metrics.metric("panel-radius")}px;
    padding: {metrics.metric("space-xs")}px;
    font-size: {body.size_px}px;
}}
QMenu::item {{
    padding: {metrics.metric("space-sm")}px {metrics.metric("space-lg")}px;
    border-radius: {metrics.metric("space-xs")}px;
    background-color: transparent;
    color: {theme.color("text-primary")};
}}
QMenu::item:selected {{
    background-color: {theme.color("surface-selected")};
    color: {theme.color("text-primary")};
}}
QMenu::item:disabled {{
    background-color: transparent;
    color: {theme.color("text-muted")};
}}
QMenu::separator {{
    height: {metrics.metric("border-width")}px;
    background-color: {theme.color("border-default")};
    margin: {metrics.metric("space-xs")}px {metrics.metric("space-sm")}px;
}}
QPushButton:hover:enabled, QToolButton:hover:enabled {{
    background-color: {theme.color("surface-selected")};
    border-color: {theme.color("accent-primary-hover")};
}}
QCheckBox:hover:enabled, QRadioButton:hover:enabled {{
    color: {theme.color("accent-primary-hover")};
}}
QComboBox:hover:enabled, QLineEdit:hover:enabled:!read-only,
QSpinBox:hover:enabled, QDoubleSpinBox:hover:enabled {{
    border-color: {theme.color("accent-primary-hover")};
}}
QPushButton:focus:enabled, QToolButton:focus:enabled,
QComboBox:focus:enabled, QLineEdit:focus:enabled,
QSpinBox:focus:enabled, QDoubleSpinBox:focus:enabled {{
    border-color: {theme.color("focus-ring")};
}}
""".strip()


def apply_application_theme(
    application: object,
    *,
    theme: Theme = DEFAULT_LIGHT_THEME,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
    typography: Typography = DEFAULT_TYPOGRAPHY,
) -> None:
    """Activate ArcGrav presentation on one Qt application.

    Activation is presentation-only. It establishes governed palette, body
    typography, and native-shell styling before production desktop composition.
    """

    try:
        from PySide6.QtGui import QColor, QFont, QPalette
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is required to activate the ArcGrav application theme"
        ) from exc

    if not isinstance(application, QApplication):
        raise TypeError("application must be a QApplication")

    from AgMark.gui.widgets.interaction import install_control_cursors

    install_control_cursors(application)
    palette = QPalette(application.palette())
    role_colors = {
        QPalette.ColorRole.Window: "surface-background",
        QPalette.ColorRole.WindowText: "text-primary",
        QPalette.ColorRole.Base: "surface-panel",
        QPalette.ColorRole.AlternateBase: "surface-selected",
        QPalette.ColorRole.Text: "text-primary",
        QPalette.ColorRole.Button: "surface-panel",
        QPalette.ColorRole.ButtonText: "text-primary",
        QPalette.ColorRole.BrightText: "state-error",
        QPalette.ColorRole.Highlight: "accent-primary",
        QPalette.ColorRole.HighlightedText: "surface-panel",
        QPalette.ColorRole.Link: "accent-primary",
        QPalette.ColorRole.LinkVisited: "accent-primary",
        QPalette.ColorRole.PlaceholderText: "text-muted",
    }
    for role, token in role_colors.items():
        palette.setColor(role, QColor(theme.color(token)))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            role,
            QColor(theme.color("text-muted")),
        )

    body = typography.style("body")
    font = QFont(application.font())
    font.setPixelSize(body.size_px)

    application.setPalette(palette)
    application.setFont(font)
    application.setStyleSheet(
        application_style_sheet(
            theme=theme,
            metrics=metrics,
            typography=typography,
        )
    )
    application.setProperty("arcgravDesignSystemActive", True)
    application.setProperty("arcgravDesignSystemTheme", theme.name)


def semantic_icon(
    role: str,
    *,
    theme: Theme = DEFAULT_LIGHT_THEME,
    size: int = 18,
):
    """Build one deterministic repository-owned semantic presentation icon.

    Roles are explicit presentation semantics.  They never infer lifecycle,
    benchmark, evidence, or readiness state from visible text.
    """

    if role not in SEMANTIC_ICON_ROLES:
        raise KeyError(f"unknown semantic icon role: {role}")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError("semantic icon size must be a positive integer")

    try:
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is required to construct ArcGrav semantic icons"
        ) from exc

    token_by_role = {
        "run-delete": "state-error",
        "status-success": "state-success",
        "status-warning": "state-warning",
        "status-error": "state-error",
        "status-active": "state-active",
        "status-neutral": "state-neutral",
    }
    token = token_by_role.get(role, "accent-primary")
    foreground = QColor(theme.color(token))

    icon = QIcon()
    for render_size in sorted({16, 20, 24, 32, size}):
        pixmap = QPixmap(render_size, render_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        unit = render_size / 18.0
        stroke = max(1.25, 1.65 * unit)
        pen = QPen(
            foreground,
            stroke,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        def point(x: float, y: float) -> QPointF:
            return QPointF(x * unit, y * unit)

        def line(x1: float, y1: float, x2: float, y2: float) -> None:
            painter.drawLine(point(x1, y1), point(x2, y2))

        if role == "plan-build":
            for y in (5.0, 9.0, 13.0):
                painter.drawEllipse(point(3.1, y), 0.7 * unit, 0.7 * unit)
                line(5.3, y, 10.7, y)
            line(11.8, 9.0, 15.0, 9.0)
            line(13.4, 7.4, 15.0, 9.0)
            line(13.4, 10.6, 15.0, 9.0)
        elif role == "plan-accept":
            painter.drawEllipse(QRectF(2.4 * unit, 2.4 * unit, 13.2 * unit, 13.2 * unit))
            line(5.2, 9.1, 7.8, 11.6)
            line(7.8, 11.6, 12.9, 6.3)
        elif role == "benchmark-start":
            painter.drawEllipse(QRectF(2.4 * unit, 2.4 * unit, 13.2 * unit, 13.2 * unit))
            painter.setBrush(foreground)
            painter.drawPolygon(
                QPolygonF([point(7.4, 5.8), point(13.0, 9.0), point(7.4, 12.2)])
            )
        elif role == "current-run-boundary":
            painter.drawRoundedRect(
                QRectF(2.2 * unit, 3.0 * unit, 13.6 * unit, 12.0 * unit),
                2.0 * unit,
                2.0 * unit,
            )
            for x, y in ((5.2, 6.2), (12.8, 6.2), (9.0, 11.8)):
                painter.setBrush(foreground)
                painter.drawEllipse(point(x, y), 1.0 * unit, 1.0 * unit)
                painter.setBrush(Qt.BrushStyle.NoBrush)
            line(6.1, 6.7, 8.3, 10.8)
            line(11.9, 6.7, 9.7, 10.8)
        elif role == "current-run-plan":
            for y in (5.0, 9.0, 13.0):
                painter.setBrush(foreground)
                painter.drawEllipse(point(3.2, y), 0.75 * unit, 0.75 * unit)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                line(5.6, y, 14.2, y)
        elif role == "current-run-treatments":
            # Stacked documents represent the selected treatment prompt files.
            line(2.8, 5.5, 2.8, 15.8)
            line(2.8, 15.8, 12.3, 15.8)
            painter.drawRoundedRect(
                QRectF(5.5 * unit, 2.8 * unit, 9.5 * unit, 11.5 * unit),
                1.2 * unit,
                1.2 * unit,
            )
            line(8.0, 6.5, 12.5, 6.5)
            line(8.0, 9.5, 12.5, 9.5)
        elif role == "console":
            line(3.2, 5.0, 6.8, 8.4)
            line(6.8, 8.4, 3.2, 11.8)
            line(8.5, 12.2, 14.6, 12.2)
        elif role in {"clear", "run-delete"}:
            painter.drawRoundedRect(
                QRectF(5.0 * unit, 5.5 * unit, 8.0 * unit, 9.0 * unit),
                1.0 * unit,
                1.0 * unit,
            )
            line(4.2, 4.2, 13.8, 4.2)
            line(7.0, 2.8, 11.0, 2.8)
            line(7.4, 7.5, 7.4, 12.2)
            line(10.6, 7.5, 10.6, 12.2)
        elif role in {"collapse", "expand"}:
            if role == "collapse":
                line(4.0, 11.2, 9.0, 6.3)
                line(9.0, 6.3, 14.0, 11.2)
            else:
                line(4.0, 6.8, 9.0, 11.7)
                line(9.0, 11.7, 14.0, 6.8)
        elif role == "information":
            painter.drawEllipse(QRectF(2.6 * unit, 2.6 * unit, 12.8 * unit, 12.8 * unit))
            painter.setBrush(foreground)
            painter.drawEllipse(point(9.0, 5.8), 0.85 * unit, 0.85 * unit)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            line(9.0, 8.3, 9.0, 12.2)
        elif role == "status-warning":
            painter.drawPolygon(
                QPolygonF([point(9.0, 2.8), point(15.2, 14.8), point(2.8, 14.8)])
            )
            line(9.0, 6.6, 9.0, 10.4)
            painter.setBrush(foreground)
            painter.drawEllipse(point(9.0, 12.5), 0.6 * unit, 0.6 * unit)
        elif role in {"status-success", "status-error", "status-active", "status-neutral"}:
            painter.drawEllipse(QRectF(2.8 * unit, 2.8 * unit, 12.4 * unit, 12.4 * unit))
            if role == "status-success":
                line(5.4, 9.1, 7.8, 11.4)
                line(7.8, 11.4, 12.7, 6.5)
            elif role == "status-error":
                line(6.1, 6.1, 11.9, 11.9)
                line(11.9, 6.1, 6.1, 11.9)
            elif role == "status-active":
                painter.setBrush(foreground)
                painter.drawEllipse(point(9.0, 9.0), 2.2 * unit, 2.2 * unit)
            else:
                line(6.2, 9.0, 11.8, 9.0)
        else:
            painter.end()
            raise RuntimeError(f"semantic icon role has no renderer: {role}")

        painter.end()
        icon.addPixmap(pixmap)

    return icon


def arcgrav_application_icon(*, theme: Theme = DEFAULT_LIGHT_THEME):
    """Build the repository-owned ArcGrav desktop application identity.

    The icon is constructed from design-system tokens rather than a toolkit or
    operating-system stock icon so production cannot silently regress to a
    generic application/computer glyph.
    """

    try:
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is required to construct the ArcGrav application icon"
        ) from exc

    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        inset = max(1.0, size * 0.06)
        bounds = QRectF(inset, inset, size - (2.0 * inset), size - (2.0 * inset))
        radius = max(2.0, size * 0.19)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.color("text-primary")))
        painter.drawRoundedRect(bounds, radius, radius)

        center = QPointF(size * 0.5, size * 0.5)
        painter.save()
        painter.translate(center)
        painter.rotate(-24.0)
        orbit_pen = QPen(
            QColor(theme.color("console-info")),
            max(1.25, size * 0.055),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(orbit_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            QRectF(-size * 0.33, -size * 0.20, size * 0.66, size * 0.40),
            18 * 16,
            292 * 16,
        )
        painter.restore()

        mark_pen = QPen(
            QColor(theme.color("surface-panel")),
            max(1.5, size * 0.072),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(mark_pen)
        painter.drawLine(
            QPointF(size * 0.31, size * 0.71),
            QPointF(size * 0.50, size * 0.27),
        )
        painter.drawLine(
            QPointF(size * 0.50, size * 0.27),
            QPointF(size * 0.69, size * 0.71),
        )
        painter.drawLine(
            QPointF(size * 0.39, size * 0.56),
            QPointF(size * 0.61, size * 0.56),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.color("accent-primary")))
        dot_radius = max(1.0, size * 0.055)
        painter.drawEllipse(
            QPointF(size * 0.72, size * 0.32),
            dot_radius,
            dot_radius,
        )
        painter.end()

        icon.addPixmap(pixmap)

    return icon


__all__ = [
    "DEFAULT_LIGHT_THEME",
    "REQUIRED_COLOR_TOKENS",
    "SEMANTIC_ICON_ROLES",
    "Theme",
    "apply_application_theme",
    "application_style_sheet",
    "arcgrav_application_icon",
    "color",
    "compact_splitter_handle_extent",
    "semantic_icon",
]
