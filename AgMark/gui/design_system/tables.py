"""Semantic table presentation for the ArcGrav desktop GUI.

This module is presentation-only. It centralizes table hierarchy, alignment,
overflow, unavailable-action, status-label, and missing-score presentation without
creating benchmark, lifecycle, score, evidence, report, or verification authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    TextStyle,
    Typography,
)


REQUIRED_TABLE_ROLES = frozenset({"default"})


@dataclass(frozen=True, slots=True)
class TableStyle:
    """Semantic presentation recipe for a reusable data table."""

    header_background_token: str
    header_border_token: str
    header_text_token: str
    header_text_role: str
    body_background_token: str
    body_border_token: str
    body_text_token: str
    body_text_role: str
    selected_background_token: str
    unavailable_action_text_token: str
    unavailable_action_indicator: str
    row_alignment_policy: str = "grid"
    column_alignment_policy: str = "declared"
    action_column_location: str = "trailing"
    action_alignment: str = "right"
    horizontal_overflow_policy: str = "horizontal-scroll"
    required_column_policy: str = "preserve"
    missing_score_placeholder: str = "—"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("header_background_token", self.header_background_token),
            ("header_border_token", self.header_border_token),
            ("header_text_token", self.header_text_token),
            ("header_text_role", self.header_text_role),
            ("body_background_token", self.body_background_token),
            ("body_border_token", self.body_border_token),
            ("body_text_token", self.body_text_token),
            ("body_text_role", self.body_text_role),
            ("selected_background_token", self.selected_background_token),
            ("unavailable_action_text_token", self.unavailable_action_text_token),
            ("unavailable_action_indicator", self.unavailable_action_indicator),
            ("missing_score_placeholder", self.missing_score_placeholder),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty presentation value")

        expected_policies = {
            "row_alignment_policy": "grid",
            "column_alignment_policy": "declared",
            "action_column_location": "trailing",
            "action_alignment": "right",
            "horizontal_overflow_policy": "horizontal-scroll",
            "required_column_policy": "preserve",
        }
        for field_name, expected in expected_policies.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} must be {expected!r}")

        if (
            self.header_background_token == self.body_background_token
            and self.header_border_token == self.body_border_token
            and self.header_text_role == self.body_text_role
        ):
            raise ValueError("table headers must remain visually distinct from body cells")

        try:
            if Decimal(self.missing_score_placeholder.strip()) == 0:
                raise ValueError("missing score presentation must not use numeric zero")
        except InvalidOperation:
            pass


@dataclass(frozen=True, slots=True)
class ResolvedTableStyle:
    """Concrete table presentation values resolved from semantic registries."""

    header_background: str
    header_border: str
    header_text: str
    header_typography: TextStyle
    body_background: str
    body_border: str
    body_text: str
    body_typography: TextStyle
    selected_background: str
    unavailable_action_text: str
    unavailable_action_indicator: str
    row_alignment_policy: str
    column_alignment_policy: str
    action_column_location: str
    action_alignment: str
    horizontal_overflow_policy: str
    required_column_policy: str
    missing_score_placeholder: str


@dataclass(frozen=True, slots=True)
class TableRegistry:
    """Immutable registry for reusable table-presentation roles."""

    styles: Mapping[str, TableStyle]

    def __post_init__(self) -> None:
        normalized = dict(self.styles)
        missing = REQUIRED_TABLE_ROLES.difference(normalized)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"table registry is missing required roles: {joined}")

        invalid = {
            role: style
            for role, style in normalized.items()
            if not isinstance(role, str)
            or not role
            or not isinstance(style, TableStyle)
        }
        if invalid:
            joined = ", ".join(repr(role) for role in invalid)
            raise ValueError(f"table registry contains invalid roles: {joined}")

        object.__setattr__(self, "styles", MappingProxyType(normalized))

    def style(self, role: str = "default") -> TableStyle:
        """Return the semantic recipe registered for a table role."""

        try:
            return self.styles[role]
        except KeyError as exc:
            raise KeyError(f"unknown semantic table role: {role}") from exc

    def resolve(
        self,
        role: str = "default",
        *,
        theme: Theme = DEFAULT_LIGHT_THEME,
        typography: Typography = DEFAULT_TYPOGRAPHY,
    ) -> ResolvedTableStyle:
        """Resolve a table role through semantic color and typography registries."""

        style = self.style(role)
        return ResolvedTableStyle(
            header_background=theme.color(style.header_background_token),
            header_border=theme.color(style.header_border_token),
            header_text=theme.color(style.header_text_token),
            header_typography=typography.style(style.header_text_role),
            body_background=theme.color(style.body_background_token),
            body_border=theme.color(style.body_border_token),
            body_text=theme.color(style.body_text_token),
            body_typography=typography.style(style.body_text_role),
            selected_background=theme.color(style.selected_background_token),
            unavailable_action_text=theme.color(style.unavailable_action_text_token),
            unavailable_action_indicator=style.unavailable_action_indicator,
            row_alignment_policy=style.row_alignment_policy,
            column_alignment_policy=style.column_alignment_policy,
            action_column_location=style.action_column_location,
            action_alignment=style.action_alignment,
            horizontal_overflow_policy=style.horizontal_overflow_policy,
            required_column_policy=style.required_column_policy,
            missing_score_placeholder=style.missing_score_placeholder,
        )


DEFAULT_TABLE_STYLES = TableRegistry(
    styles={
        "default": TableStyle(
            header_background_token="surface-background",
            header_border_token="border-strong",
            header_text_token="text-primary",
            header_text_role="table-heading",
            body_background_token="surface-panel",
            body_border_token="border-default",
            body_text_token="text-primary",
            body_text_role="body",
            selected_background_token="surface-selected",
            unavailable_action_text_token="text-muted",
            unavailable_action_indicator="disabled-affordance",
        )
    }
)


def table_style(
    role: str = "default", *, registry: TableRegistry = DEFAULT_TABLE_STYLES
) -> TableStyle:
    """Return the semantic presentation recipe for a table role."""

    return registry.style(role)


def resolved_table(
    role: str = "default",
    *,
    registry: TableRegistry = DEFAULT_TABLE_STYLES,
    theme: Theme = DEFAULT_LIGHT_THEME,
    typography: Typography = DEFAULT_TYPOGRAPHY,
) -> ResolvedTableStyle:
    """Resolve table presentation without deriving benchmark or workflow authority."""

    return registry.resolve(role, theme=theme, typography=typography)


def table_status_label(label: str) -> str:
    """Preserve an explicitly supplied status label exactly for table display."""

    if not isinstance(label, str) or not label.strip():
        raise ValueError("table status label must be a non-empty supplied label")
    return label


def table_score_text(
    value_text: str | None, *, style: TableStyle | None = None
) -> str:
    """Preserve supplied score text and render absence with a non-zero placeholder."""

    selected_style = DEFAULT_TABLE_STYLES.style() if style is None else style
    if not isinstance(selected_style, TableStyle):
        raise ValueError("style must be a TableStyle")
    if value_text is None:
        return selected_style.missing_score_placeholder
    if not isinstance(value_text, str) or not value_text.strip():
        raise ValueError("score text must be a non-empty supplied value when present")
    return value_text


__all__ = [
    "DEFAULT_TABLE_STYLES",
    "REQUIRED_TABLE_ROLES",
    "ResolvedTableStyle",
    "TableRegistry",
    "TableStyle",
    "resolved_table",
    "table_score_text",
    "table_status_label",
    "table_style",
]
