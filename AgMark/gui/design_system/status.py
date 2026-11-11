"""Semantic status presentation for the ArcGrav desktop GUI.

This module is presentation-only. It styles an explicitly supplied presentation
tone while preserving the caller-supplied state label exactly. It never infers
benchmark or lifecycle meaning from display text and cannot create execution,
evidence, report, scoring, or verification authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme


REQUIRED_STATUS_TONES = frozenset(
    {"success", "warning", "error", "active", "neutral"}
)

_REQUIRED_STATUS_TOKEN_PAIRS = {
    "success": ("state-success", "state-success-surface"),
    "warning": ("state-warning", "state-warning-surface"),
    "error": ("state-error", "state-error-surface"),
    "active": ("state-active", "state-active-surface"),
    "neutral": ("state-neutral", "state-neutral-surface"),
}


@dataclass(frozen=True, slots=True)
class StatusStyle:
    """Semantic color and non-color presentation recipe for one status tone."""

    foreground_token: str
    background_token: str
    icon_key: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("foreground_token", self.foreground_token),
            ("background_token", self.background_token),
            ("icon_key", self.icon_key),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty presentation value")


@dataclass(frozen=True, slots=True)
class ResolvedStatusBadge:
    """Resolved presentation data that preserves the supplied label verbatim."""

    label: str
    tone: str
    foreground: str
    background: str
    icon_key: str


@dataclass(frozen=True, slots=True)
class StatusRegistry:
    """Immutable registry for required semantic status tones."""

    styles: Mapping[str, StatusStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_STATUS_TONES.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"status registry is missing required tones: {joined}")

        invalid = {
            tone: style
            for tone, style in normalized.items()
            if not isinstance(tone, str)
            or not tone
            or not isinstance(style, StatusStyle)
        }
        if invalid:
            joined = ", ".join(repr(tone) for tone in invalid)
            raise ValueError(f"status registry contains invalid tones: {joined}")

        for tone, expected_tokens in _REQUIRED_STATUS_TOKEN_PAIRS.items():
            style = normalized[tone]
            actual_tokens = (style.foreground_token, style.background_token)
            if actual_tokens != expected_tokens:
                raise ValueError(
                    f"{tone} status tone must use semantic state tokens "
                    f"{expected_tokens[0]} and {expected_tokens[1]}"
                )

        signatures: dict[tuple[str, str, str], str] = {}
        for tone in sorted(REQUIRED_STATUS_TONES):
            style = normalized[tone]
            signature = (
                style.foreground_token,
                style.background_token,
                style.icon_key,
            )
            if signature in signatures:
                raise ValueError(
                    "required status tones must remain semantically distinct: "
                    f"{signatures[signature]} and {tone} are equivalent"
                )
            signatures[signature] = tone

        icon_keys = [normalized[tone].icon_key for tone in REQUIRED_STATUS_TONES]
        if len(set(icon_keys)) != len(icon_keys):
            raise ValueError(
                "required status tones must use distinct non-color icon cues"
            )

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, tone: str) -> StatusStyle:
        """Return the semantic recipe registered for an explicit tone."""

        try:
            return self.styles[tone]
        except KeyError as exc:
            raise KeyError(f"unknown semantic status tone: {tone}") from exc

    def resolve(
        self,
        label: str,
        tone: str,
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
    ) -> ResolvedStatusBadge:
        """Resolve an explicit presentation tone while preserving label text."""

        if not isinstance(label, str) or not label.strip():
            raise ValueError("status label must be a non-empty supplied label")

        style = self.style(tone)
        return ResolvedStatusBadge(
            label=label,
            tone=tone,
            foreground=theme.color(style.foreground_token),
            background=theme.color(style.background_token),
            icon_key=style.icon_key,
        )


DEFAULT_STATUS_STYLES = StatusRegistry(
    styles={
        "success": StatusStyle(
            foreground_token="state-success",
            background_token="state-success-surface",
            icon_key="status-success",
        ),
        "warning": StatusStyle(
            foreground_token="state-warning",
            background_token="state-warning-surface",
            icon_key="status-warning",
        ),
        "error": StatusStyle(
            foreground_token="state-error",
            background_token="state-error-surface",
            icon_key="status-error",
        ),
        "active": StatusStyle(
            foreground_token="state-active",
            background_token="state-active-surface",
            icon_key="status-active",
        ),
        "neutral": StatusStyle(
            foreground_token="state-neutral",
            background_token="state-neutral-surface",
            icon_key="status-neutral",
        ),
    }
)


def status_style(
    tone: str, *, registry: StatusRegistry = DEFAULT_STATUS_STYLES
) -> StatusStyle:
    """Return a presentation recipe for an explicit semantic status tone."""

    return registry.style(tone)


def resolved_status(
    label: str,
    tone: str,
    *,
    registry: StatusRegistry = DEFAULT_STATUS_STYLES,
    theme: Theme = DEFAULT_LIGHT_THEME,
) -> ResolvedStatusBadge:
    """Resolve status presentation without deriving meaning from the label."""

    return registry.resolve(label, tone, theme=theme)


__all__ = [
    "DEFAULT_STATUS_STYLES",
    "REQUIRED_STATUS_TONES",
    "ResolvedStatusBadge",
    "StatusRegistry",
    "StatusStyle",
    "resolved_status",
    "status_style",
]
