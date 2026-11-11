"""Semantic button hierarchy for the ArcGrav desktop GUI.

This module is presentation-only. It exposes explicit visual roles for actions
without deriving workflow meaning, executable authority, or availability from
button labels or local GUI state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme


REQUIRED_BUTTON_ROLES = frozenset(
    {"primary", "secondary", "contextual", "destructive", "unavailable"}
)


@dataclass(frozen=True, slots=True)
class ButtonStyle:
    """Semantic presentation recipe for one explicit action role."""

    background_token: str
    border_token: str
    text_token: str
    compact: bool = False
    enabled: bool = True
    non_color_indicator: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("background_token", self.background_token),
            ("border_token", self.border_token),
            ("text_token", self.text_token),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty semantic token")
        if not isinstance(self.compact, bool) or not isinstance(self.enabled, bool):
            raise ValueError("compact and enabled must be boolean presentation flags")
        if self.non_color_indicator is not None and (
            not isinstance(self.non_color_indicator, str)
            or not self.non_color_indicator
        ):
            raise ValueError("non_color_indicator must be a non-empty cue when supplied")


@dataclass(frozen=True, slots=True)
class ResolvedButtonStyle:
    """Concrete colors plus non-color presentation cues for a button role."""

    background: str
    border: str
    text: str
    compact: bool
    enabled: bool
    non_color_indicator: str | None


@dataclass(frozen=True, slots=True)
class ButtonRegistry:
    """Immutable registry for the required action-hierarchy roles."""

    styles: Mapping[str, ButtonStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_BUTTON_ROLES.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"button registry is missing required roles: {joined}")

        invalid = {
            role: style
            for role, style in normalized.items()
            if not isinstance(role, str)
            or not role
            or not isinstance(style, ButtonStyle)
        }
        if invalid:
            joined = ", ".join(repr(role) for role in invalid)
            raise ValueError(f"button registry contains invalid roles: {joined}")

        primary = normalized["primary"]
        if (
            primary.background_token != "accent-primary"
            or primary.border_token != "accent-primary"
            or primary.text_token != "surface-panel"
        ):
            raise ValueError(
                "primary button must use the saturated accent with light text"
            )

        if normalized["contextual"].compact is not True:
            raise ValueError("contextual action must preserve compact presentation")
        if normalized["unavailable"].enabled:
            raise ValueError("unavailable action must be non-enabled")
        if normalized["unavailable"].non_color_indicator is None:
            raise ValueError("unavailable action must include a non-color disabled cue")
        for role in REQUIRED_BUTTON_ROLES.difference({"unavailable"}):
            if not normalized[role].enabled:
                raise ValueError(f"{role} action must remain enabled")

        signatures: dict[tuple[object, ...], str] = {}
        for role in sorted(REQUIRED_BUTTON_ROLES):
            style = normalized[role]
            signature = (
                style.background_token,
                style.border_token,
                style.text_token,
                style.compact,
                style.enabled,
                style.non_color_indicator,
            )
            if signature in signatures:
                raise ValueError(
                    "required button roles must remain visually distinguishable: "
                    f"{signatures[signature]} and {role} are equivalent"
                )
            signatures[signature] = role

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, role: str) -> ButtonStyle:
        """Return the semantic presentation recipe registered for an action role."""

        try:
            return self.styles[role]
        except KeyError as exc:
            raise KeyError(f"unknown semantic button role: {role}") from exc

    def resolve(
        self,
        role: str,
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
    ) -> ResolvedButtonStyle:
        """Resolve a button role through the supplied semantic theme."""

        style = self.style(role)
        return ResolvedButtonStyle(
            background=theme.color(style.background_token),
            border=theme.color(style.border_token),
            text=theme.color(style.text_token),
            compact=style.compact,
            enabled=style.enabled,
            non_color_indicator=style.non_color_indicator,
        )


DEFAULT_BUTTON_STYLES = ButtonRegistry(
    styles={
        "primary": ButtonStyle(
            background_token="accent-primary",
            border_token="accent-primary",
            text_token="surface-panel",
            non_color_indicator="primary-action",
        ),
        "secondary": ButtonStyle(
            background_token="surface-panel",
            border_token="border-strong",
            text_token="text-primary",
            non_color_indicator="secondary-action",
        ),
        "contextual": ButtonStyle(
            background_token="surface-panel",
            border_token="border-default",
            text_token="text-secondary",
            compact=True,
            non_color_indicator="contextual-action",
        ),
        "destructive": ButtonStyle(
            background_token="surface-panel",
            border_token="state-error",
            text_token="state-error",
            non_color_indicator="destructive-action",
        ),
        "unavailable": ButtonStyle(
            background_token="surface-panel",
            border_token="border-default",
            text_token="text-muted",
            enabled=False,
            non_color_indicator="disabled-affordance",
        ),
    }
)


def button_style(
    role: str, *, registry: ButtonRegistry = DEFAULT_BUTTON_STYLES
) -> ButtonStyle:
    """Return the presentation recipe for an explicit action-hierarchy role."""

    return registry.style(role)


def resolved_button(
    role: str,
    *,
    registry: ButtonRegistry = DEFAULT_BUTTON_STYLES,
    theme: Theme = DEFAULT_LIGHT_THEME,
) -> ResolvedButtonStyle:
    """Resolve button presentation without deriving action authority."""

    return registry.resolve(role, theme=theme)


__all__ = [
    "ButtonRegistry",
    "ButtonStyle",
    "DEFAULT_BUTTON_STYLES",
    "REQUIRED_BUTTON_ROLES",
    "ResolvedButtonStyle",
    "button_style",
    "resolved_button",
]
