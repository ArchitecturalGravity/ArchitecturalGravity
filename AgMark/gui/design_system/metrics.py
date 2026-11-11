"""Semantic layout metrics for the ArcGrav desktop GUI.

This module is presentation-only. It centralizes spacing and density semantics so
feature modules can consume named logical-pixel metrics without coupling layout
state to benchmark configuration, evidence, lifecycle, reports, or identity.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


REQUIRED_LAYOUT_METRICS = frozenset(
    {
        "space-xs",
        "space-sm",
        "space-md",
        "space-lg",
        "page-padding",
        "stack-gap",
        "compact-panel-padding-x",
        "compact-panel-padding-y",
        "compact-panel-gap",
        "related-gap",
        "section-gap",
        "panel-padding",
        "control-height",
        "panel-radius",
        "border-width",
        "selected-tab-underline",
    }
)


@dataclass(frozen=True, slots=True)
class LayoutMetrics:
    """Immutable logical-pixel metrics for presentation layout."""

    values: Mapping[str, int]

    def __post_init__(self) -> None:
        normalized = dict(self.values)
        missing = REQUIRED_LAYOUT_METRICS.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"layout metrics are missing required tokens: {joined}")

        invalid_tokens = [
            token
            for token in normalized
            if not isinstance(token, str) or not token
        ]
        if invalid_tokens:
            joined = ", ".join(sorted(map(repr, invalid_tokens)))
            raise ValueError(f"layout metrics contain invalid tokens: {joined}")

        invalid_values = {
            token: value
            for token, value in normalized.items()
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0
        }
        if invalid_values:
            joined = ", ".join(
                f"{token!r}={value!r}"
                for token, value in sorted(invalid_values.items())
            )
            raise ValueError(
                "layout metrics must be positive integer logical-pixel values: "
                f"{joined}"
            )

        if normalized["related-gap"] >= normalized["section-gap"]:
            raise ValueError(
                "related-gap must be smaller than section-gap to preserve visual grouping"
            )

        object.__setattr__(self, "values", MappingProxyType(normalized))

    def metric(self, token: str) -> int:
        """Return the exact logical-pixel value registered for a semantic metric."""

        try:
            return self.values[token]
        except KeyError as exc:
            raise KeyError(f"unknown semantic layout metric: {token}") from exc


DEFAULT_LAYOUT_METRICS = LayoutMetrics(
    values={
        "space-xs": 4,
        "space-sm": 8,
        "space-md": 12,
        "space-lg": 16,
        "page-padding": 12,
        "stack-gap": 10,
        "compact-panel-padding-x": 8,
        "compact-panel-padding-y": 6,
        "compact-panel-gap": 2,
        "related-gap": 8,
        "section-gap": 16,
        "panel-padding": 14,
        "control-height": 40,
        "panel-radius": 8,
        "border-width": 1,
        "selected-tab-underline": 3,
    }
)


def metric(
    token: str, *, metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS
) -> int:
    """Resolve a semantic layout metric without exposing feature code to literals."""

    return metrics.metric(token)


__all__ = [
    "DEFAULT_LAYOUT_METRICS",
    "LayoutMetrics",
    "REQUIRED_LAYOUT_METRICS",
    "metric",
]
