"""Conformance tests for GUI table-presentation semantics."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.tables import (
    DEFAULT_TABLE_STYLES,
    REQUIRED_TABLE_ROLES,
    TableRegistry,
    TableStyle,
    resolved_table,
    table_score_text,
    table_status_label,
    table_style,
)


class DefaultTableRegistryTests(unittest.TestCase):
    def test_required_roles_are_complete_and_immutable(self) -> None:
        self.assertEqual(frozenset(DEFAULT_TABLE_STYLES.styles), REQUIRED_TABLE_ROLES)
        with self.assertRaises(TypeError):
            DEFAULT_TABLE_STYLES.styles["default"] = table_style()  # type: ignore[index]

    def test_alignment_actions_and_required_columns_use_stable_policies(self) -> None:
        style = table_style()
        self.assertEqual(style.row_alignment_policy, "grid")
        self.assertEqual(style.column_alignment_policy, "declared")
        self.assertEqual(style.action_column_location, "trailing")
        self.assertEqual(style.action_alignment, "right")
        self.assertEqual(style.horizontal_overflow_policy, "horizontal-scroll")
        self.assertEqual(style.required_column_policy, "preserve")

    def test_unavailable_actions_are_deemphasized_with_non_color_cue(self) -> None:
        style = table_style()
        resolved = resolved_table()
        self.assertEqual(style.unavailable_action_text_token, "text-muted")
        self.assertNotEqual(resolved.unavailable_action_text, resolved.body_text)
        self.assertEqual(style.unavailable_action_indicator, "disabled-affordance")

    def test_supplied_status_labels_are_preserved_exactly(self) -> None:
        for label in (
            "accepted",
            "blocked",
            "in-progress",
            "unavailable",
            "non-comparable",
            "not-generated",
        ):
            self.assertEqual(table_status_label(label), label)
        self.assertEqual(table_status_label(" pending "), " pending ")
        with self.assertRaisesRegex(ValueError, "non-empty"):
            table_status_label("   ")

    def test_missing_scores_are_not_rendered_as_numeric_zero(self) -> None:
        missing = table_score_text(None)
        self.assertEqual(missing, "—")
        self.assertNotEqual(missing, "0")
        self.assertEqual(table_score_text("0"), "0")
        self.assertEqual(table_score_text("0.000"), "0.000")

    def test_invalid_table_contracts_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "horizontal_overflow_policy"):
            TableStyle(
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
                horizontal_overflow_policy="drop-columns",
            )

        original = table_style()
        with self.assertRaisesRegex(ValueError, "numeric zero"):
            TableStyle(
                header_background_token=original.header_background_token,
                header_border_token=original.header_border_token,
                header_text_token=original.header_text_token,
                header_text_role=original.header_text_role,
                body_background_token=original.body_background_token,
                body_border_token=original.body_border_token,
                body_text_token=original.body_text_token,
                body_text_role=original.body_text_role,
                selected_background_token=original.selected_background_token,
                unavailable_action_text_token=original.unavailable_action_text_token,
                unavailable_action_indicator=original.unavailable_action_indicator,
                missing_score_placeholder="0.0",
            )

    def test_incomplete_registry_and_unknown_semantic_references_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "default"):
            TableRegistry(styles={})

        original = table_style()
        invalid = TableRegistry(
            styles={
                "default": TableStyle(
                    header_background_token="accepted-run",
                    header_border_token=original.header_border_token,
                    header_text_token=original.header_text_token,
                    header_text_role=original.header_text_role,
                    body_background_token=original.body_background_token,
                    body_border_token=original.body_border_token,
                    body_text_token=original.body_text_token,
                    body_text_role=original.body_text_role,
                    selected_background_token=original.selected_background_token,
                    unavailable_action_text_token=original.unavailable_action_text_token,
                    unavailable_action_indicator=original.unavailable_action_indicator,
                )
            }
        )
        with self.assertRaisesRegex(KeyError, "unknown semantic color token"):
            invalid.resolve()

        with self.assertRaisesRegex(KeyError, "unknown semantic table role"):
            table_style("accepted-run")


if __name__ == "__main__":
    unittest.main()
