"""Semantic input presentation for the ArcGrav desktop GUI.

The registry is presentation-only. It centralizes label, focus, validation,
accessory, credential-visibility, and numeric-input affordances without storing
input values or creating benchmark, lifecycle, evidence, report, or verification
authority.
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


REQUIRED_INPUT_ROLES = frozenset({"text", "credential", "numeric"})


@dataclass(frozen=True, slots=True)
class InputStyle:
    """Semantic presentation recipe for one explicit input role."""

    label_placement: str
    accessory_placement: str
    control_height_metric: str
    background_token: str
    border_token: str
    text_token: str
    placeholder_token: str
    focus_border_token: str
    validation_border_token: str
    validation_indicator: str
    obscured_by_default: bool = False
    allows_transient_reveal: bool = False
    numeric_spinner: bool = False

    def __post_init__(self) -> None:
        for field_name, value in (
            ("label_placement", self.label_placement),
            ("accessory_placement", self.accessory_placement),
            ("control_height_metric", self.control_height_metric),
            ("background_token", self.background_token),
            ("border_token", self.border_token),
            ("text_token", self.text_token),
            ("placeholder_token", self.placeholder_token),
            ("focus_border_token", self.focus_border_token),
            ("validation_border_token", self.validation_border_token),
            ("validation_indicator", self.validation_indicator),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty semantic value")

        for field_name, value in (
            ("obscured_by_default", self.obscured_by_default),
            ("allows_transient_reveal", self.allows_transient_reveal),
            ("numeric_spinner", self.numeric_spinner),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{field_name} must be a boolean presentation flag")

        if self.allows_transient_reveal and not self.obscured_by_default:
            raise ValueError(
                "transient reveal is valid only for an input obscured by default"
            )


@dataclass(frozen=True, slots=True)
class ResolvedInputStyle:
    """Concrete presentation values for one input role."""

    label_placement: str
    accessory_placement: str
    control_height_px: int
    background: str
    border: str
    text: str
    placeholder: str
    focus_border: str
    validation_border: str
    validation_indicator: str
    obscured_by_default: bool
    allows_transient_reveal: bool
    numeric_spinner: bool


@dataclass(frozen=True, slots=True)
class InputRegistry:
    """Immutable registry for reusable input-presentation roles."""

    styles: Mapping[str, InputStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_INPUT_ROLES.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"input registry is missing required roles: {joined}")

        invalid = {
            role: style
            for role, style in normalized.items()
            if not isinstance(role, str)
            or not role
            or not isinstance(style, InputStyle)
        }
        if invalid:
            joined = ", ".join(repr(role) for role in invalid)
            raise ValueError(f"input registry contains invalid roles: {joined}")

        common_fields = (
            "label_placement",
            "accessory_placement",
            "control_height_metric",
            "background_token",
            "border_token",
            "text_token",
            "placeholder_token",
            "focus_border_token",
            "validation_border_token",
            "validation_indicator",
        )
        baseline = normalized["text"]
        inconsistent = [
            role
            for role in sorted(REQUIRED_INPUT_ROLES.difference({"text"}))
            if any(
                getattr(normalized[role], field) != getattr(baseline, field)
                for field in common_fields
            )
        ]
        if inconsistent:
            joined = ", ".join(inconsistent)
            raise ValueError(
                "required input roles must preserve consistent label, control, "
                f"focus, validation, and accessory presentation: {joined}"
            )

        credential = normalized["credential"]
        if not credential.obscured_by_default:
            raise ValueError("credential input must be obscured by default")
        if not credential.allows_transient_reveal:
            raise ValueError(
                "credential input must expose only an explicit transient reveal affordance"
            )

        for role in ("text", "numeric"):
            style = normalized[role]
            if style.obscured_by_default or style.allows_transient_reveal:
                raise ValueError(
                    f"{role} input must not inherit credential-visibility behavior"
                )

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, role: str) -> InputStyle:
        """Return the semantic presentation recipe registered for an input role."""

        try:
            return self.styles[role]
        except KeyError as exc:
            raise KeyError(f"unknown semantic input role: {role}") from exc

    def resolve(
        self,
        role: str,
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
        metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
    ) -> ResolvedInputStyle:
        """Resolve an input role through semantic theme and metric registries."""

        style = self.style(role)
        return ResolvedInputStyle(
            label_placement=style.label_placement,
            accessory_placement=style.accessory_placement,
            control_height_px=metrics.metric(style.control_height_metric),
            background=theme.color(style.background_token),
            border=theme.color(style.border_token),
            text=theme.color(style.text_token),
            placeholder=theme.color(style.placeholder_token),
            focus_border=theme.color(style.focus_border_token),
            validation_border=theme.color(style.validation_border_token),
            validation_indicator=style.validation_indicator,
            obscured_by_default=style.obscured_by_default,
            allows_transient_reveal=style.allows_transient_reveal,
            numeric_spinner=style.numeric_spinner,
        )


_COMMON_INPUT_STYLE = {
    "label_placement": "above",
    "accessory_placement": "trailing",
    "control_height_metric": "control-height",
    "background_token": "surface-panel",
    "border_token": "border-default",
    "text_token": "text-primary",
    "placeholder_token": "text-muted",
    "focus_border_token": "focus-ring",
    "validation_border_token": "state-error",
    "validation_indicator": "validation-message",
}

DEFAULT_INPUT_STYLES = InputRegistry(
    styles={
        "text": InputStyle(**_COMMON_INPUT_STYLE),
        "credential": InputStyle(
            **_COMMON_INPUT_STYLE,
            obscured_by_default=True,
            allows_transient_reveal=True,
        ),
        "numeric": InputStyle(
            **_COMMON_INPUT_STYLE,
            numeric_spinner=True,
        ),
    }
)


def input_style(
    role: str, *, registry: InputRegistry = DEFAULT_INPUT_STYLES
) -> InputStyle:
    """Return the semantic presentation recipe for an explicit input role."""

    return registry.style(role)


def resolved_input(
    role: str,
    *,
    registry: InputRegistry = DEFAULT_INPUT_STYLES,
    theme: Theme = DEFAULT_LIGHT_THEME,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
) -> ResolvedInputStyle:
    """Resolve input presentation without deriving workflow or benchmark authority."""

    return registry.resolve(role, theme=theme, metrics=metrics)


def credential_echo_mode(
    *,
    reveal_requested: bool = False,
    registry: InputRegistry = DEFAULT_INPUT_STYLES,
) -> str:
    """Return a stateless semantic echo mode for a credential field.

    The function accepts only a transient reveal request and never a secret value,
    so using the reveal affordance cannot persist credential contents here.
    """

    if not isinstance(reveal_requested, bool):
        raise ValueError("reveal_requested must be a boolean presentation flag")

    credential = registry.style("credential")
    if reveal_requested:
        if not credential.allows_transient_reveal:
            raise ValueError("credential input does not allow transient reveal")
        return "visible"
    return "obscured" if credential.obscured_by_default else "visible"


__all__ = [
    "DEFAULT_INPUT_STYLES",
    "InputRegistry",
    "InputStyle",
    "REQUIRED_INPUT_ROLES",
    "ResolvedInputStyle",
    "credential_echo_mode",
    "input_style",
    "resolved_input",
]
