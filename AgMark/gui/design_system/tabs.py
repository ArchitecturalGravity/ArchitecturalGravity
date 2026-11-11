"""Semantic tab presentation for the ArcGrav desktop GUI.

This module is presentation-only. It centralizes text-tab selection styling without
creating benchmark, lifecycle, evidence, report, verification, or command authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from AgMark.gui.design_system.metrics import (
    DEFAULT_LAYOUT_METRICS,
    LayoutMetrics,
)
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    TextStyle,
    Typography,
)


REQUIRED_TAB_STATES = frozenset({"default", "selected"})


@dataclass(frozen=True, slots=True)
class TabStyle:
    """Semantic presentation recipe for one tab-selection state."""

    background_token: str
    text_token: str
    text_role: str = "body"
    underline_token: str | None = None
    underline_metric: str | None = None
    selection_indicator: str | None = None
    selected: bool = False
    navigation_shape: str = "text-tab"
    activation_semantics: str = "presentation-only"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("background_token", self.background_token),
            ("text_token", self.text_token),
            ("text_role", self.text_role),
            ("navigation_shape", self.navigation_shape),
            ("activation_semantics", self.activation_semantics),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty presentation value")

        for field_name, value in (
            ("underline_token", self.underline_token),
            ("underline_metric", self.underline_metric),
            ("selection_indicator", self.selection_indicator),
        ):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty cue when supplied")

        if not isinstance(self.selected, bool):
            raise ValueError("selected must be a boolean presentation flag")
        if self.navigation_shape != "text-tab":
            raise ValueError("tab navigation must use text-tab presentation rather than pills")
        if self.activation_semantics != "presentation-only":
            raise ValueError("tab activation semantics must remain presentation-only")
        if (self.underline_token is None) != (self.underline_metric is None):
            raise ValueError("tab underline token and metric must be supplied together")


@dataclass(frozen=True, slots=True)
class ResolvedTabStyle:
    """Concrete presentation values for one tab-selection state."""

    background: str
    text: str
    typography: TextStyle
    underline_color: str | None
    underline_width_px: int | None
    selection_indicator: str | None
    selected: bool
    navigation_shape: str
    activation_semantics: str


@dataclass(frozen=True, slots=True)
class TabRegistry:
    """Immutable registry for default and selected text-tab presentation."""

    styles: Mapping[str, TabStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_TAB_STATES.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"tab registry is missing required states: {joined}")

        invalid = {
            state: style
            for state, style in normalized.items()
            if not isinstance(state, str)
            or not state
            or not isinstance(style, TabStyle)
        }
        if invalid:
            joined = ", ".join(repr(state) for state in invalid)
            raise ValueError(f"tab registry contains invalid states: {joined}")

        default = normalized["default"]
        selected = normalized["selected"]

        if default.selected:
            raise ValueError("default tab state must remain unselected")
        if default.underline_token is not None or default.selection_indicator is not None:
            raise ValueError("default tab state must not carry a selection indicator")

        if not selected.selected:
            raise ValueError("selected tab state must be marked selected")
        if selected.background_token != default.background_token:
            raise ValueError("selected tabs must not use filled navigation-pill treatment")
        if selected.underline_token != "accent-primary":
            raise ValueError("selected tab must use the saturated accent underline")
        if selected.underline_metric != "selected-tab-underline":
            raise ValueError("selected tab must use the selected-tab-underline metric")
        if selected.selection_indicator != "persistent-underline":
            raise ValueError("selected tab must include a persistent underline selection cue")

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, state: str) -> TabStyle:
        """Return the semantic presentation recipe registered for a tab state."""

        try:
            return self.styles[state]
        except KeyError as exc:
            raise KeyError(f"unknown semantic tab state: {state}") from exc

    def resolve(
        self,
        state: str,
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
        metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
        typography: Typography = DEFAULT_TYPOGRAPHY,
    ) -> ResolvedTabStyle:
        """Resolve a tab state through semantic presentation registries."""

        style = self.style(state)
        return ResolvedTabStyle(
            background=theme.color(style.background_token),
            text=theme.color(style.text_token),
            typography=typography.style(style.text_role),
            underline_color=(
                theme.color(style.underline_token)
                if style.underline_token is not None
                else None
            ),
            underline_width_px=(
                metrics.metric(style.underline_metric)
                if style.underline_metric is not None
                else None
            ),
            selection_indicator=style.selection_indicator,
            selected=style.selected,
            navigation_shape=style.navigation_shape,
            activation_semantics=style.activation_semantics,
        )


DEFAULT_TAB_STYLES = TabRegistry(
    styles={
        "default": TabStyle(
            background_token="surface-panel",
            text_token="text-primary",
        ),
        "selected": TabStyle(
            background_token="surface-panel",
            text_token="text-primary",
            underline_token="accent-primary",
            underline_metric="selected-tab-underline",
            selection_indicator="persistent-underline",
            selected=True,
        ),
    }
)


def tab_style(
    state: str, *, registry: TabRegistry = DEFAULT_TAB_STYLES
) -> TabStyle:
    """Return the presentation recipe for an explicit tab-selection state."""

    return registry.style(state)


def resolved_tab(
    state: str,
    *,
    registry: TabRegistry = DEFAULT_TAB_STYLES,
    theme: Theme = DEFAULT_LIGHT_THEME,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
    typography: Typography = DEFAULT_TYPOGRAPHY,
) -> ResolvedTabStyle:
    """Resolve an explicit tab-selection state through semantic registries."""

    return registry.resolve(
        state,
        theme=theme,
        metrics=metrics,
        typography=typography,
    )


__all__ = [
    "DEFAULT_TAB_STYLES",
    "REQUIRED_TAB_STATES",
    "ResolvedTabStyle",
    "TabRegistry",
    "TabStyle",
    "resolved_tab",
    "tab_style",
]
