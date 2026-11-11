"""Semantic interactive-control states for the ArcGrav desktop GUI.

This module is presentation-only. It expresses required control-state distinctions
through existing design-system tokens and explicit non-color cues without creating
benchmark, lifecycle, evidence, report, scoring, or verification authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme


REQUIRED_INTERACTION_STATES = frozenset(
    {"default", "hover", "focus", "pressed", "selected", "disabled"}
)


@dataclass(frozen=True, slots=True)
class InteractionStyle:
    """Semantic presentation recipe for one interactive-control state."""

    background_token: str
    border_token: str
    text_token: str
    focus_visible: bool = False
    non_color_indicator: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        for field_name, value in (
            ("background_token", self.background_token),
            ("border_token", self.border_token),
            ("text_token", self.text_token),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty semantic token")

        if self.non_color_indicator is not None and (
            not isinstance(self.non_color_indicator, str)
            or not self.non_color_indicator
        ):
            raise ValueError("non_color_indicator must be a non-empty cue when supplied")

        if not isinstance(self.focus_visible, bool) or not isinstance(self.enabled, bool):
            raise ValueError("focus_visible and enabled must be boolean presentation flags")


@dataclass(frozen=True, slots=True)
class ResolvedInteractionStyle:
    """Concrete colors plus presentation cues resolved from semantic state data."""

    background: str
    border: str
    text: str
    focus_visible: bool
    non_color_indicator: str | None
    enabled: bool


@dataclass(frozen=True, slots=True)
class InteractionRegistry:
    """Immutable registry for the required interactive-control states."""

    styles: Mapping[str, InteractionStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_INTERACTION_STATES.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"interaction registry is missing required states: {joined}")

        invalid = {
            state: style
            for state, style in normalized.items()
            if not isinstance(state, str)
            or not state
            or not isinstance(style, InteractionStyle)
        }
        if invalid:
            joined = ", ".join(repr(state) for state in invalid)
            raise ValueError(f"interaction registry contains invalid states: {joined}")

        if not normalized["focus"].focus_visible:
            raise ValueError("focus state must preserve a visible keyboard-focus cue")
        if normalized["focus"].border_token != "focus-ring":
            raise ValueError("focus state must resolve through the semantic focus-ring token")
        if normalized["selected"].non_color_indicator is None:
            raise ValueError("selected state must include a non-color selection indicator")
        if normalized["disabled"].enabled:
            raise ValueError("disabled state must be semantically non-enabled")
        if normalized["disabled"].non_color_indicator is None:
            raise ValueError("disabled state must include a non-color disabled cue")
        for state in REQUIRED_INTERACTION_STATES.difference({"disabled"}):
            if not normalized[state].enabled:
                raise ValueError(f"{state} state must remain enabled")

        signatures: dict[tuple[object, ...], str] = {}
        for state in sorted(REQUIRED_INTERACTION_STATES):
            style = normalized[state]
            signature = (
                style.background_token,
                style.border_token,
                style.text_token,
                style.focus_visible,
                style.non_color_indicator,
                style.enabled,
            )
            if signature in signatures:
                raise ValueError(
                    "required interaction states must remain distinguishable: "
                    f"{signatures[signature]} and {state} are equivalent"
                )
            signatures[signature] = state

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, state: str) -> InteractionStyle:
        """Return the semantic recipe registered for an interaction state."""

        try:
            return self.styles[state]
        except KeyError as exc:
            raise KeyError(f"unknown semantic interaction state: {state}") from exc

    def resolve(
        self,
        state: str,
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
    ) -> ResolvedInteractionStyle:
        """Resolve an interaction state through the supplied semantic theme."""

        style = self.style(state)
        return ResolvedInteractionStyle(
            background=theme.color(style.background_token),
            border=theme.color(style.border_token),
            text=theme.color(style.text_token),
            focus_visible=style.focus_visible,
            non_color_indicator=style.non_color_indicator,
            enabled=style.enabled,
        )


DEFAULT_INTERACTIONS = InteractionRegistry(
    styles={
        "default": InteractionStyle(
            background_token="surface-panel",
            border_token="border-default",
            text_token="text-primary",
        ),
        "hover": InteractionStyle(
            background_token="surface-panel",
            border_token="accent-primary-hover",
            text_token="text-primary",
        ),
        "focus": InteractionStyle(
            background_token="surface-panel",
            border_token="focus-ring",
            text_token="text-primary",
            focus_visible=True,
            non_color_indicator="focus-outline",
        ),
        "pressed": InteractionStyle(
            background_token="surface-selected",
            border_token="accent-primary-hover",
            text_token="text-primary",
            non_color_indicator="pressed-affordance",
        ),
        "selected": InteractionStyle(
            background_token="surface-selected",
            border_token="accent-primary",
            text_token="text-primary",
            non_color_indicator="selection-indicator",
        ),
        "disabled": InteractionStyle(
            background_token="surface-panel",
            border_token="border-default",
            text_token="text-muted",
            non_color_indicator="disabled-affordance",
            enabled=False,
        ),
    }
)


def interaction_style(
    state: str, *, registry: InteractionRegistry = DEFAULT_INTERACTIONS
) -> InteractionStyle:
    """Return a semantic interaction-state recipe."""

    return registry.style(state)


def resolved_interaction(
    state: str,
    *,
    registry: InteractionRegistry = DEFAULT_INTERACTIONS,
    theme: Theme = DEFAULT_LIGHT_THEME,
) -> ResolvedInteractionStyle:
    """Resolve concrete presentation values for a semantic interaction state."""

    return registry.resolve(state, theme=theme)


__all__ = [
    "DEFAULT_INTERACTIONS",
    "InteractionRegistry",
    "InteractionStyle",
    "REQUIRED_INTERACTION_STATES",
    "ResolvedInteractionStyle",
    "interaction_style",
    "resolved_interaction",
]
