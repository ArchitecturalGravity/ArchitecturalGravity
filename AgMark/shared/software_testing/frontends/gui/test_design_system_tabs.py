"""Conformance tests for GUI tab-presentation semantics."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.tabs import (
    DEFAULT_TAB_STYLES,
    REQUIRED_TAB_STATES,
    TabRegistry,
    TabStyle,
    resolved_tab,
    tab_style,
)


class DefaultTabRegistryTests(unittest.TestCase):
    def test_required_states_are_complete_and_immutable(self) -> None:
        self.assertEqual(frozenset(DEFAULT_TAB_STYLES.styles), REQUIRED_TAB_STATES)
        with self.assertRaises(TypeError):
            DEFAULT_TAB_STYLES.styles["default"] = tab_style("selected")  # type: ignore[index]

    def test_selected_tab_is_text_navigation_with_persistent_accent_underline(self) -> None:
        default = tab_style("default")
        selected = tab_style("selected")

        self.assertEqual(default.navigation_shape, "text-tab")
        self.assertEqual(selected.navigation_shape, "text-tab")
        self.assertEqual(selected.background_token, default.background_token)
        self.assertEqual(selected.underline_token, "accent-primary")
        self.assertEqual(selected.underline_metric, "selected-tab-underline")
        self.assertEqual(selected.selection_indicator, "persistent-underline")
        self.assertTrue(selected.selected)
        self.assertFalse(default.selected)

        resolved = resolved_tab("selected")
        self.assertEqual(resolved.background, "#FFFFFF")
        self.assertEqual(resolved.text, "#0B1748")
        self.assertEqual(resolved.underline_color, "#005FFD")
        self.assertEqual(resolved.underline_width_px, 3)
        self.assertEqual(resolved.selection_indicator, "persistent-underline")

    def test_default_tab_has_no_selection_indicator(self) -> None:
        resolved = resolved_tab("default")
        self.assertIsNone(resolved.underline_color)
        self.assertIsNone(resolved.underline_width_px)
        self.assertIsNone(resolved.selection_indicator)
        self.assertFalse(resolved.selected)

    def test_tab_selection_remains_presentation_only(self) -> None:
        for state in REQUIRED_TAB_STATES:
            style = tab_style(state)
            self.assertEqual(style.activation_semantics, "presentation-only")
            self.assertEqual(style.navigation_shape, "text-tab")

    def test_invalid_selected_contracts_fail_closed(self) -> None:
        default = tab_style("default")

        with self.assertRaisesRegex(ValueError, "filled navigation-pill"):
            TabRegistry(
                styles={
                    "default": default,
                    "selected": TabStyle(
                        background_token="surface-selected",
                        text_token="text-primary",
                        underline_token="accent-primary",
                        underline_metric="selected-tab-underline",
                        selection_indicator="persistent-underline",
                        selected=True,
                    ),
                }
            )

        with self.assertRaisesRegex(ValueError, "saturated accent underline"):
            TabRegistry(
                styles={
                    "default": default,
                    "selected": TabStyle(
                        background_token="surface-panel",
                        text_token="text-primary",
                        underline_token="border-strong",
                        underline_metric="selected-tab-underline",
                        selection_indicator="persistent-underline",
                        selected=True,
                    ),
                }
            )

        with self.assertRaisesRegex(ValueError, "persistent underline"):
            TabRegistry(
                styles={
                    "default": default,
                    "selected": TabStyle(
                        background_token="surface-panel",
                        text_token="text-primary",
                        underline_token="accent-primary",
                        underline_metric="selected-tab-underline",
                        selected=True,
                    ),
                }
            )

    def test_incomplete_registry_and_unknown_semantic_references_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "selected"):
            TabRegistry(styles={"default": tab_style("default")})

        invalid = TabRegistry(
            styles={
                "default": TabStyle(
                    background_token="surface-panel",
                    text_token="accepted-run",
                ),
                "selected": tab_style("selected"),
            }
        )
        with self.assertRaisesRegex(KeyError, "unknown semantic color token"):
            invalid.resolve("default")

        with self.assertRaisesRegex(KeyError, "unknown semantic tab state"):
            tab_style("accepted-run")


if __name__ == "__main__":
    unittest.main()
