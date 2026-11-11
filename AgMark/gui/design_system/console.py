"""Semantic console presentation for the ArcGrav desktop GUI.

This module is presentation-only. It resolves the terminal-oriented console
through semantic color and typography registries while preserving source text
verbatim and never deriving benchmark, lifecycle, evidence, report, verification
authority from visible console content.
"""

from __future__ import annotations

from dataclasses import dataclass

from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    Typography,
)


@dataclass(frozen=True, slots=True)
class ConsolePresentationStyle:
    """Semantic recipe for raw and diagnostic console inspection surfaces."""

    background_token: str = "console-background"
    text_token: str = "console-text"
    muted_token: str = "console-muted"
    info_token: str = "console-info"
    progress_token: str = "console-progress"
    warning_token: str = "console-warning"
    error_token: str = "state-error"
    typography_role: str = "console"
    source_content_semantics: str = "preserve-exact-source"
    authority_semantics: str = "presentation-only"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("background_token", self.background_token),
            ("text_token", self.text_token),
            ("muted_token", self.muted_token),
            ("info_token", self.info_token),
            ("progress_token", self.progress_token),
            ("warning_token", self.warning_token),
            ("error_token", self.error_token),
            ("typography_role", self.typography_role),
            ("source_content_semantics", self.source_content_semantics),
            ("authority_semantics", self.authority_semantics),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty presentation value")

        if self.source_content_semantics != "preserve-exact-source":
            raise ValueError("console presentation must preserve exact source content")
        if self.authority_semantics != "presentation-only":
            raise ValueError("console presentation authority must remain presentation-only")


@dataclass(frozen=True, slots=True)
class ResolvedConsolePresentation:
    """Concrete console presentation resolved from semantic registries."""

    background: str
    text: str
    muted: str
    info: str
    progress: str
    warning: str
    error: str
    font_family: str
    font_size_px: int
    font_weight: int
    monospace: bool
    source_content_semantics: str
    authority_semantics: str


DEFAULT_CONSOLE_PRESENTATION = ConsolePresentationStyle()


def resolved_console_presentation(
    *,
    style: ConsolePresentationStyle = DEFAULT_CONSOLE_PRESENTATION,
    theme: Theme = DEFAULT_LIGHT_THEME,
    typography: Typography = DEFAULT_TYPOGRAPHY,
) -> ResolvedConsolePresentation:
    """Resolve console visuals without changing source text or creating authority."""

    text_style = typography.style(style.typography_role)
    if not text_style.monospace:
        raise ValueError("console typography must use a system monospace role")

    background = theme.color(style.background_token)
    text = theme.color(style.text_token)
    if background == text:
        raise ValueError("console text must remain distinguishable from its background")

    return ResolvedConsolePresentation(
        background=background,
        text=text,
        muted=theme.color(style.muted_token),
        info=theme.color(style.info_token),
        progress=theme.color(style.progress_token),
        warning=theme.color(style.warning_token),
        error=theme.color(style.error_token),
        font_family=text_style.family,
        font_size_px=text_style.size_px,
        font_weight=text_style.weight,
        monospace=text_style.monospace,
        source_content_semantics=style.source_content_semantics,
        authority_semantics=style.authority_semantics,
    )


__all__ = [
    "ConsolePresentationStyle",
    "DEFAULT_CONSOLE_PRESENTATION",
    "ResolvedConsolePresentation",
    "resolved_console_presentation",
]
