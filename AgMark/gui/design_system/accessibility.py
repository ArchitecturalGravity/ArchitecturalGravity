"""Presentation-only accessibility primitives for the ArcGrav desktop GUI.

This module supplies design-system checks for optional caller-selected contrast
standards, explicit keyboard focus ordering, non-color state cues, and local
presentation accommodations. It does not define benchmark, evidence, lifecycle, report, or
reconstruction authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from AgMark.gui.design_system.interaction import (
    DEFAULT_INTERACTIONS,
    InteractionRegistry,
)
from AgMark.gui.design_system.status import (
    DEFAULT_STATUS_STYLES,
    StatusRegistry,
)
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme


_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _channel_luminance(channel: int) -> float:
    value = channel / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """Return relative luminance for an exact ``#RRGGBB`` color."""

    if not isinstance(color, str) or _HEX_COLOR.fullmatch(color) is None:
        raise ValueError("color must be an exact #RRGGBB value")

    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    return (
        0.2126 * _channel_luminance(red)
        + 0.7152 * _channel_luminance(green)
        + 0.0722 * _channel_luminance(blue)
    )


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the luminance contrast ratio between two exact colors."""

    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter = max(first, second)
    darker = min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


@dataclass(frozen=True, slots=True)
class ContrastRequirement:
    """One semantic token pair required by an explicitly supplied contrast policy."""

    role: str
    foreground_token: str
    background_token: str
    minimum_ratio: float

    def __post_init__(self) -> None:
        for field_name, value in (
            ("role", self.role),
            ("foreground_token", self.foreground_token),
            ("background_token", self.background_token),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        ratio = self.minimum_ratio
        if (
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or not math.isfinite(ratio)
            or ratio < 1.0
            or ratio > 21.0
        ):
            raise ValueError("minimum_ratio must be a finite value from 1.0 through 21.0")
        object.__setattr__(self, "minimum_ratio", float(ratio))


@dataclass(frozen=True, slots=True)
class ContrastResult:
    """Resolved contrast evidence for one semantic requirement."""

    role: str
    foreground_token: str
    background_token: str
    actual_ratio: float
    minimum_ratio: float

    @property
    def passes(self) -> bool:
        return self.actual_ratio >= self.minimum_ratio


@dataclass(frozen=True, slots=True)
class ContrastStandard:
    """Named caller-supplied contrast policy.

    The normative default desktop palette is fixed by the design-system
    specification and reference mockups. This type remains available for
    explicitly supplied optional policies without inventing project thresholds.
    """

    name: str
    requirements: tuple[ContrastRequirement, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("contrast standard name must be non-empty")

        if isinstance(self.requirements, (str, bytes)):
            raise ValueError("contrast requirements must be a sequence of requirements")
        normalized = tuple(self.requirements)
        if not normalized:
            raise ValueError("contrast standard must contain at least one requirement")
        if any(not isinstance(item, ContrastRequirement) for item in normalized):
            raise ValueError("contrast standard contains an invalid requirement")

        roles = [item.role for item in normalized]
        if len(set(roles)) != len(roles):
            raise ValueError("contrast requirement roles must be unique")
        object.__setattr__(self, "requirements", normalized)

    def evaluate(
        self,
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
    ) -> tuple[ContrastResult, ...]:
        """Resolve all requirements against a semantic theme."""

        return tuple(
            ContrastResult(
                role=requirement.role,
                foreground_token=requirement.foreground_token,
                background_token=requirement.background_token,
                actual_ratio=contrast_ratio(
                    theme.color(requirement.foreground_token),
                    theme.color(requirement.background_token),
                ),
                minimum_ratio=requirement.minimum_ratio,
            )
            for requirement in self.requirements
        )

    def validate(
        self,
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
    ) -> tuple[ContrastResult, ...]:
        """Fail closed when any supplied contrast requirement is unmet."""

        results = self.evaluate(theme=theme)
        failures = tuple(result for result in results if not result.passes)
        if failures:
            details = ", ".join(
                f"{result.role}={result.actual_ratio:.2f}<{result.minimum_ratio:.2f}"
                for result in failures
            )
            raise ValueError(
                f"theme {theme.name!r} does not satisfy contrast standard "
                f"{self.name!r}: {details}"
            )
        return results


@dataclass(frozen=True, slots=True)
class KeyboardFocusOrder:
    """Explicit presentation-only keyboard traversal order."""

    control_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.control_ids, (str, bytes)):
            raise ValueError("keyboard focus order must be a sequence of control ids")
        normalized = tuple(self.control_ids)
        if not normalized:
            raise ValueError("keyboard focus order must contain at least one control")
        if any(not isinstance(value, str) or not value.strip() for value in normalized):
            raise ValueError("keyboard focus control ids must be non-empty strings")
        if len(set(normalized)) != len(normalized):
            raise ValueError("keyboard focus order must not contain duplicate controls")
        object.__setattr__(self, "control_ids", normalized)

    def position(self, control_id: str) -> int:
        """Return the zero-based traversal position for a declared control."""

        try:
            return self.control_ids.index(control_id)
        except ValueError as exc:
            raise KeyError(f"unknown keyboard focus control: {control_id}") from exc


@dataclass(frozen=True, slots=True)
class PresentationAccommodations:
    """Local presentation preferences that cannot carry benchmark authority."""

    font_scale: float = 1.0
    zoom: float = 1.0
    contrast_profile: str = "default"
    theme_name: str = DEFAULT_LIGHT_THEME.name

    def __post_init__(self) -> None:
        for field_name, value in (
            ("font_scale", self.font_scale),
            ("zoom", self.zoom),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0.0
            ):
                raise ValueError(f"{field_name} must be a finite positive value")
            object.__setattr__(self, field_name, float(value))

        for field_name, value in (
            ("contrast_profile", self.contrast_profile),
            ("theme_name", self.theme_name),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty presentation value")


def validate_non_color_state_cues(
    *,
    interactions: InteractionRegistry = DEFAULT_INTERACTIONS,
    statuses: StatusRegistry = DEFAULT_STATUS_STYLES,
) -> None:
    """Fail closed when material state presentation relies on color alone."""

    focus = interactions.style("focus")
    selected = interactions.style("selected")
    disabled = interactions.style("disabled")
    if not focus.focus_visible or focus.non_color_indicator is None:
        raise ValueError("keyboard focus must retain a visible non-color cue")
    if selected.non_color_indicator is None:
        raise ValueError("selection must retain a non-color cue")
    if disabled.non_color_indicator is None:
        raise ValueError("disabled presentation must retain a non-color cue")

    icon_keys = [statuses.style(tone).icon_key for tone in statuses.styles]
    if any(not icon_key for icon_key in icon_keys):
        raise ValueError("status presentation must retain non-color icon cues")
    if len(set(icon_keys)) != len(icon_keys):
        raise ValueError("material status tones must retain distinct non-color icon cues")


__all__ = [
    "ContrastRequirement",
    "ContrastResult",
    "ContrastStandard",
    "KeyboardFocusOrder",
    "PresentationAccommodations",
    "contrast_ratio",
    "relative_luminance",
    "validate_non_color_state_cues",
]
