"""Semantic progress presentation for the ArcGrav desktop GUI.

This module is presentation-only. It projects caller-supplied progress through
semantic visual tokens without creating benchmark,
lifecycle, evidence, report, verification, or terminal-state authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme


REQUIRED_PROGRESS_FORMS = frozenset({"bar", "ring", "counter", "stepper"})


@dataclass(frozen=True, slots=True)
class ProgressStyle:
    """Semantic presentation recipe for one progress-control form."""

    background_token: str
    active_token: str
    text_token: str
    value_indicator: str
    completion_semantics: str = "visual-only"
    authority_semantics: str = "presentation-only"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("background_token", self.background_token),
            ("active_token", self.active_token),
            ("text_token", self.text_token),
            ("value_indicator", self.value_indicator),
            ("completion_semantics", self.completion_semantics),
            ("authority_semantics", self.authority_semantics),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty presentation value")

        if self.completion_semantics != "visual-only":
            raise ValueError("progress completion semantics must remain visual-only")
        if self.authority_semantics != "presentation-only":
            raise ValueError("progress authority semantics must remain presentation-only")


@dataclass(frozen=True, slots=True)
class ResolvedProgressPresentation:
    """Concrete presentation data derived only from supplied progress."""

    form: str
    current: int
    total: int
    label: str | None
    fraction: float
    percent: float
    visually_complete: bool
    background: str
    active: str
    text: str
    value_indicator: str
    completion_semantics: str
    authority_semantics: str


@dataclass(frozen=True, slots=True)
class ProgressRegistry:
    """Immutable registry for required progress-control forms."""

    styles: Mapping[str, ProgressStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_PROGRESS_FORMS.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"progress registry is missing required forms: {joined}")

        invalid = {
            form: style
            for form, style in normalized.items()
            if not isinstance(form, str)
            or not form
            or not isinstance(style, ProgressStyle)
        }
        if invalid:
            joined = ", ".join(repr(form) for form in invalid)
            raise ValueError(f"progress registry contains invalid forms: {joined}")

        for form in REQUIRED_PROGRESS_FORMS:
            style = normalized[form]
            if style.completion_semantics != "visual-only":
                raise ValueError(f"{form} progress completion must remain visual-only")
            if style.authority_semantics != "presentation-only":
                raise ValueError(f"{form} progress authority must remain presentation-only")

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, form: str) -> ProgressStyle:
        """Return the semantic presentation recipe for an explicit progress form."""

        try:
            return self.styles[form]
        except KeyError as exc:
            raise KeyError(f"unknown semantic progress form: {form}") from exc

    def resolve(
        self,
        current: int,
        total: int,
        *,
        form: str = "bar",
        label: str | None = None,
        theme: Theme = DEFAULT_LIGHT_THEME,
    ) -> ResolvedProgressPresentation:
        """Project supplied progress without deriving any authoritative terminal state."""

        if isinstance(current, bool) or not isinstance(current, int):
            raise ValueError("current progress must be an integer")
        if isinstance(total, bool) or not isinstance(total, int):
            raise ValueError("total progress must be an integer")
        if total <= 0:
            raise ValueError("total progress must be greater than zero")
        if current < 0 or current > total:
            raise ValueError("current progress must be between zero and total")

        if label is not None and (not isinstance(label, str) or not label.strip()):
            raise ValueError("progress label must be a non-empty supplied label")

        style = self.style(form)
        fraction = current / total
        return ResolvedProgressPresentation(
            form=form,
            current=current,
            total=total,
            label=label,
            fraction=fraction,
            percent=fraction * 100.0,
            visually_complete=current == total,
            background=theme.color(style.background_token),
            active=theme.color(style.active_token),
            text=theme.color(style.text_token),
            value_indicator=style.value_indicator,
            completion_semantics=style.completion_semantics,
            authority_semantics=style.authority_semantics,
        )


DEFAULT_PROGRESS_STYLES = ProgressRegistry(
    styles={
        "bar": ProgressStyle(
            background_token="border-default",
            active_token="accent-primary",
            text_token="text-primary",
            value_indicator="linear-fill",
        ),
        "ring": ProgressStyle(
            background_token="border-default",
            active_token="accent-primary",
            text_token="text-primary",
            value_indicator="radial-arc",
        ),
        "counter": ProgressStyle(
            background_token="surface-panel",
            active_token="accent-primary",
            text_token="text-primary",
            value_indicator="numeric-counter",
        ),
        "stepper": ProgressStyle(
            background_token="border-default",
            active_token="accent-primary",
            text_token="text-primary",
            value_indicator="stage-stepper",
        ),
    }
)


def progress_style(
    form: str, *, registry: ProgressRegistry = DEFAULT_PROGRESS_STYLES
) -> ProgressStyle:
    """Return the presentation recipe for an explicit progress-control form."""

    return registry.style(form)


def resolved_progress(
    current: int,
    total: int,
    *,
    form: str = "bar",
    label: str | None = None,
    registry: ProgressRegistry = DEFAULT_PROGRESS_STYLES,
    theme: Theme = DEFAULT_LIGHT_THEME,
) -> ResolvedProgressPresentation:
    """Resolve supplied progress through semantic presentation tokens only."""

    return registry.resolve(
        current,
        total,
        form=form,
        label=label,
        theme=theme,
    )


__all__ = [
    "DEFAULT_PROGRESS_STYLES",
    "ProgressRegistry",
    "ProgressStyle",
    "REQUIRED_PROGRESS_FORMS",
    "ResolvedProgressPresentation",
    "progress_style",
    "resolved_progress",
]
