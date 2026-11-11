"""Semantic surfaces and restrained elevation for the ArcGrav desktop GUI.

This module is presentation-only. It composes existing semantic color and layout
registries into reusable surface roles without creating benchmark, lifecycle,
evidence, report, scoring, or verification authority.
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


REQUIRED_SURFACE_ROLES = frozenset(
    {
        "workspace",
        "panel",
        "card",
        "grouped-control",
        "selected-row",
        "focused-control",
        "active-tab",
        "console",
    }
)


@dataclass(frozen=True, slots=True)
class SurfaceStyle:
    """Semantic surface recipe expressed only through design-system tokens."""

    background_token: str
    border_token: str | None = None
    radius_metric: str | None = None
    border_width_metric: str | None = None
    elevation: int = 0

    def __post_init__(self) -> None:
        for field_name, value in (
            ("background_token", self.background_token),
            ("border_token", self.border_token),
            ("radius_metric", self.radius_metric),
            ("border_width_metric", self.border_width_metric),
        ):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty semantic token")

        if (self.border_token is None) != (self.border_width_metric is None):
            raise ValueError(
                "border_token and border_width_metric must be supplied together"
            )

        if (
            isinstance(self.elevation, bool)
            or not isinstance(self.elevation, int)
            or self.elevation not in (0, 1)
        ):
            raise ValueError(
                "surface elevation must be 0 (flat) or 1 (restrained)"
            )


@dataclass(frozen=True, slots=True)
class ResolvedSurfaceStyle:
    """Concrete presentation values resolved from semantic registries."""

    background: str
    border: str | None
    radius_px: int
    border_width_px: int
    elevation: int


@dataclass(frozen=True, slots=True)
class SurfaceRegistry:
    """Immutable semantic registry for workspace and component surfaces."""

    styles: Mapping[str, SurfaceStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_SURFACE_ROLES.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"surface registry is missing required roles: {joined}")

        invalid = {
            role: style
            for role, style in normalized.items()
            if not isinstance(role, str)
            or not role
            or not isinstance(style, SurfaceStyle)
        }
        if invalid:
            joined = ", ".join(repr(role) for role in invalid)
            raise ValueError(f"surface registry contains invalid roles: {joined}")

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, role: str) -> SurfaceStyle:
        """Return the semantic recipe registered for a surface role."""

        try:
            return self.styles[role]
        except KeyError as exc:
            raise KeyError(f"unknown semantic surface role: {role}") from exc

    def resolve(
        self,
        role: str,
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
        metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
    ) -> ResolvedSurfaceStyle:
        """Resolve one surface through the supplied theme and layout registries."""

        style = self.style(role)
        background = theme.color(style.background_token)
        border = (
            None if style.border_token is None else theme.color(style.border_token)
        )
        radius_px = (
            0 if style.radius_metric is None else metrics.metric(style.radius_metric)
        )
        border_width_px = (
            0
            if style.border_width_metric is None
            else metrics.metric(style.border_width_metric)
        )
        return ResolvedSurfaceStyle(
            background=background,
            border=border,
            radius_px=radius_px,
            border_width_px=border_width_px,
            elevation=style.elevation,
        )


DEFAULT_SURFACES = SurfaceRegistry(
    styles={
        "workspace": SurfaceStyle(background_token="surface-background"),
        "panel": SurfaceStyle(
            background_token="surface-panel",
            border_token="border-default",
            radius_metric="panel-radius",
            border_width_metric="border-width",
        ),
        "card": SurfaceStyle(
            background_token="surface-panel",
            border_token="border-default",
            radius_metric="panel-radius",
            border_width_metric="border-width",
        ),
        "grouped-control": SurfaceStyle(
            background_token="surface-panel",
            border_token="border-default",
            radius_metric="panel-radius",
            border_width_metric="border-width",
        ),
        "selected-row": SurfaceStyle(
            background_token="surface-selected",
            border_token="border-strong",
            border_width_metric="border-width",
        ),
        "focused-control": SurfaceStyle(
            background_token="surface-panel",
            border_token="focus-ring",
            radius_metric="panel-radius",
            border_width_metric="border-width",
        ),
        "active-tab": SurfaceStyle(
            background_token="surface-panel",
            border_token="accent-primary",
            border_width_metric="border-width",
        ),
        "console": SurfaceStyle(
            background_token="console-background",
            border_token="border-strong",
            border_width_metric="border-width",
        ),
    }
)


def surface_style(
    role: str, *, registry: SurfaceRegistry = DEFAULT_SURFACES
) -> SurfaceStyle:
    """Resolve a semantic surface recipe without exposing feature code to literals."""

    return registry.style(role)


def resolved_surface(
    role: str,
    *,
    registry: SurfaceRegistry = DEFAULT_SURFACES,
    theme: Theme = DEFAULT_LIGHT_THEME,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
) -> ResolvedSurfaceStyle:
    """Resolve concrete presentation values for a semantic surface role."""

    return registry.resolve(role, theme=theme, metrics=metrics)


__all__ = [
    "DEFAULT_SURFACES",
    "REQUIRED_SURFACE_ROLES",
    "ResolvedSurfaceStyle",
    "SurfaceRegistry",
    "SurfaceStyle",
    "resolved_surface",
    "surface_style",
]
