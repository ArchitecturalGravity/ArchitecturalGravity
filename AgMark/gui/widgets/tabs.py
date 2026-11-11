"""Reusable presentation-only tab widget for the ArcGrav desktop GUI.

The widget preserves caller-supplied labels and selection state while delegating
visual semantics to the GUI design system. Tab activation changes only local
presentation state and never creates benchmark, lifecycle, evidence, scoring,
report, reconstruction, or verification authority.
"""

from __future__ import annotations

from collections.abc import Sequence

from AgMark.gui.design_system.metrics import (
    DEFAULT_LAYOUT_METRICS,
    LayoutMetrics,
)
from AgMark.gui.design_system.tabs import DEFAULT_TAB_STYLES, TabRegistry
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    Typography,
)


def _require_visible_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")
    return value


def _validate_selected_index(selected_index: int, *, count: int) -> int:
    if isinstance(selected_index, bool) or not isinstance(selected_index, int):
        raise ValueError("selected_index must be an integer")
    if not 0 <= selected_index < count:
        raise ValueError("selected_index must identify a supplied tab")
    return selected_index


try:
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QTabWidget, QWidget
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


    class TabWidget(QTabWidget):
        """Text-tab navigation with explicit caller-owned initial selection."""

        def __init__(
            self,
            tabs: Sequence[tuple[str, QWidget]],
            *,
            selected_index: int,
            registry: TabRegistry = DEFAULT_TAB_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            if isinstance(tabs, (str, bytes)):
                raise ValueError("tabs must be a sequence of (label, widget) pairs")
            entries = tuple(tabs)
            if not entries:
                raise ValueError("tabs must contain at least one (label, widget) pair")

            normalized: list[tuple[str, QWidget]] = []
            for entry in entries:
                if not isinstance(entry, tuple) or len(entry) != 2:
                    raise ValueError(
                        "tabs must be a sequence of (label, widget) pairs"
                    )
                label, widget = entry
                label = _require_visible_text(label, name="tab label")
                if not isinstance(widget, QWidget):
                    raise ValueError("each tab content value must be a QWidget")
                normalized.append((label, widget))

            selected_index = _validate_selected_index(
                selected_index,
                count=len(normalized),
            )

            super().__init__(parent)
            self._registry = registry
            self._theme = theme
            self._typography = typography
            self._metrics = metrics
            self._labels = tuple(label for label, _ in normalized)

            self.setObjectName("semanticTabWidget")
            self.setProperty("arcgravSemanticComponent", "tab-widget")
            self.setAccessibleName("Tabs")
            self.setProperty("activationSemantics", "presentation-only")
            self.tabBar().setObjectName("semanticTabBar")
            self.tabBar().setProperty("arcgravSemanticComponent", "tab-bar")
            self.tabBar().setAccessibleName("Tab navigation")
            self.tabBar().setDrawBase(False)
            self.tabBar().setExpanding(False)
            self.tabBar().setFont(_font(typography))

            for label, widget in normalized:
                self.addTab(widget, label)

            self._apply_stylesheet()
            self.set_selected_index(selected_index)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def labels(self) -> tuple[str, ...]:
            return self._labels

        @property
        def selected_index(self) -> int:
            return self.currentIndex()

        @property
        def selected_label(self) -> str:
            return self.tabText(self.currentIndex())

        def set_selected_index(self, selected_index: int) -> None:
            """Apply only an explicit caller-supplied tab selection."""

            selected_index = _validate_selected_index(
                selected_index,
                count=self.count(),
            )
            self.setCurrentIndex(selected_index)

        def _apply_stylesheet(self) -> None:
            default = self._registry.resolve(
                "default",
                theme=self._theme,
                metrics=self._metrics,
                typography=self._typography,
            )
            selected = self._registry.resolve(
                "selected",
                theme=self._theme,
                metrics=self._metrics,
                typography=self._typography,
            )
            if selected.underline_color is None or selected.underline_width_px is None:
                raise ValueError("selected tab presentation must define an underline")

            horizontal_padding = self._metrics.metric("space-md")
            vertical_padding = self._metrics.metric("space-sm")

            self.setStyleSheet(
                'QTabWidget[arcgravSemanticComponent="tab-widget"]::pane {'
                "border: 0;"
                "}"
                'QTabBar[arcgravSemanticComponent="tab-bar"]::tab {'
                f"background: {default.background};"
                f"color: {default.text};"
                "border: 0;"
                f"border-bottom: {selected.underline_width_px}px solid transparent;"
                f"padding: {vertical_padding}px {horizontal_padding}px;"
                "}"
                'QTabBar[arcgravSemanticComponent="tab-bar"]::tab:hover:enabled:!selected {'
                f"background: {self._theme.color('surface-selected')};"
                f"color: {self._theme.color('accent-primary-hover')};"
                "}"
                'QTabBar[arcgravSemanticComponent="tab-bar"]::tab:selected:hover:enabled {'
                f"color: {self._theme.color('accent-primary-hover')};"
                "}"
                'QTabBar[arcgravSemanticComponent="tab-bar"]::tab:selected {'
                f"background: {selected.background};"
                f"color: {selected.text};"
                f"border-bottom: {selected.underline_width_px}px solid "
                f"{selected.underline_color};"
                "}"
            )


else:

    class TabWidget:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for TabWidget")


__all__ = [
    "PYSIDE6_AVAILABLE",
    "TabWidget",
]
