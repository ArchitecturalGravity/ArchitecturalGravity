"""Semantic typography for the ArcGrav desktop GUI.

The registry is presentation-only. It names reusable text roles and semantic
font families without binding benchmark, lifecycle, evidence, report, or
verification meaning to typography.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


SYSTEM_UI_FAMILY = "system-ui"
SYSTEM_MONOSPACE_FAMILY = "system-monospace"
_ALLOWED_FAMILIES = frozenset({SYSTEM_UI_FAMILY, SYSTEM_MONOSPACE_FAMILY})

REQUIRED_TEXT_ROLES = frozenset(
    {
        "workspace-title",
        "section-heading",
        "card-heading",
        "table-heading",
        "body",
        "metadata",
        "console",
        "inspection-monospace",
    }
)


@dataclass(frozen=True, slots=True)
class TextStyle:
    """Presentation-only font semantics for one reusable text role."""

    family: str
    size_px: int
    weight: int = 400

    def __post_init__(self) -> None:
        if self.family not in _ALLOWED_FAMILIES:
            raise ValueError(f"unsupported semantic font family: {self.family!r}")
        if (
            isinstance(self.size_px, bool)
            or not isinstance(self.size_px, int)
            or self.size_px <= 0
        ):
            raise ValueError(
                "font size must be a positive integer logical-pixel value"
            )
        if (
            isinstance(self.weight, bool)
            or not isinstance(self.weight, int)
            or not 1 <= self.weight <= 1000
        ):
            raise ValueError("font weight must be an integer from 1 through 1000")

    @property
    def monospace(self) -> bool:
        """Whether the role requires a system monospace face."""

        return self.family == SYSTEM_MONOSPACE_FAMILY


@dataclass(frozen=True, slots=True)
class Typography:
    """Immutable semantic typography registry."""

    styles: Mapping[str, TextStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_TEXT_ROLES.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"typography is missing required text roles: {joined}")

        invalid = {
            role: style
            for role, style in normalized.items()
            if not isinstance(role, str)
            or not role
            or not isinstance(style, TextStyle)
        }
        if invalid:
            joined = ", ".join(repr(role) for role in invalid)
            raise ValueError(f"typography contains invalid text roles: {joined}")

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, role: str) -> TextStyle:
        """Return the exact style registered for a semantic text role."""

        try:
            return self.styles[role]
        except KeyError as exc:
            raise KeyError(f"unknown semantic text role: {role}") from exc


DEFAULT_TYPOGRAPHY = Typography(
    styles={
        "workspace-title": TextStyle(SYSTEM_UI_FAMILY, 26, 700),
        "section-heading": TextStyle(SYSTEM_UI_FAMILY, 16, 600),
        "card-heading": TextStyle(SYSTEM_UI_FAMILY, 14, 600),
        "table-heading": TextStyle(SYSTEM_UI_FAMILY, 13, 600),
        "body": TextStyle(SYSTEM_UI_FAMILY, 13, 400),
        "metadata": TextStyle(SYSTEM_UI_FAMILY, 13, 400),
        "console": TextStyle(SYSTEM_MONOSPACE_FAMILY, 15, 400),
        "inspection-monospace": TextStyle(SYSTEM_MONOSPACE_FAMILY, 13, 400),
    }
)


def text_style(
    role: str, *, typography: Typography = DEFAULT_TYPOGRAPHY
) -> TextStyle:
    """Resolve a semantic text style without exposing feature code to font literals."""

    return typography.style(role)


__all__ = [
    "DEFAULT_TYPOGRAPHY",
    "REQUIRED_TEXT_ROLES",
    "SYSTEM_MONOSPACE_FAMILY",
    "SYSTEM_UI_FAMILY",
    "TextStyle",
    "Typography",
    "text_style",
]
