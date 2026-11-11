"""Conformance tests for GUI interactive-state presentation semantics."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.interaction import (
    DEFAULT_INTERACTIONS,
    REQUIRED_INTERACTION_STATES,
    InteractionRegistry,
    InteractionStyle,
    interaction_style,
    resolved_interaction,
)


class DefaultInteractionRegistryTests(unittest.TestCase):
    def test_required_states_are_complete_immutable_and_distinguishable(self) -> None:
        self.assertEqual(
            frozenset(DEFAULT_INTERACTIONS.styles),
            REQUIRED_INTERACTION_STATES,
        )
        with self.assertRaises(TypeError):
            DEFAULT_INTERACTIONS.styles["default"] = InteractionStyle(  # type: ignore[index]
                background_token="surface-panel",
                border_token="border-default",
                text_token="text-primary",
            )

        signatures = {
            (
                style.background_token,
                style.border_token,
                style.text_token,
                style.focus_visible,
                style.non_color_indicator,
                style.enabled,
            )
            for style in DEFAULT_INTERACTIONS.styles.values()
        }
        self.assertEqual(len(signatures), len(REQUIRED_INTERACTION_STATES))

    def test_focus_selection_and_disabled_states_preserve_required_cues(self) -> None:
        focus = interaction_style("focus")
        self.assertTrue(focus.focus_visible)
        self.assertEqual(focus.border_token, "focus-ring")
        self.assertEqual(focus.non_color_indicator, "focus-outline")

        selected = interaction_style("selected")
        self.assertEqual(selected.background_token, "surface-selected")
        self.assertEqual(selected.border_token, "accent-primary")
        self.assertEqual(selected.non_color_indicator, "selection-indicator")

        disabled = interaction_style("disabled")
        self.assertFalse(disabled.enabled)
        self.assertEqual(disabled.text_token, "text-muted")
        self.assertEqual(disabled.non_color_indicator, "disabled-affordance")

    def test_resolution_uses_existing_semantic_theme_tokens(self) -> None:
        hover = resolved_interaction("hover")
        self.assertEqual(hover.background, "#FFFFFF")
        self.assertEqual(hover.border, "#0052DF")
        self.assertEqual(hover.text, "#0B1748")

        selected = resolved_interaction("selected")
        self.assertEqual(selected.background, "#DEEEFE")
        self.assertEqual(selected.border, "#005FFD")
        self.assertEqual(selected.text, "#0B1748")
        self.assertEqual(selected.non_color_indicator, "selection-indicator")

    def test_incomplete_or_semantically_invalid_registry_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_INTERACTIONS.styles)
        incomplete.pop("disabled")
        with self.assertRaisesRegex(ValueError, "disabled"):
            InteractionRegistry(styles=incomplete)

        no_focus = dict(DEFAULT_INTERACTIONS.styles)
        no_focus["focus"] = InteractionStyle(
            background_token="surface-panel",
            border_token="focus-ring",
            text_token="text-primary",
        )
        with self.assertRaisesRegex(ValueError, "visible keyboard-focus"):
            InteractionRegistry(styles=no_focus)

        color_only_selection = dict(DEFAULT_INTERACTIONS.styles)
        color_only_selection["selected"] = InteractionStyle(
            background_token="surface-selected",
            border_token="accent-primary",
            text_token="text-primary",
        )
        with self.assertRaisesRegex(ValueError, "non-color selection"):
            InteractionRegistry(styles=color_only_selection)

        enabled_disabled = dict(DEFAULT_INTERACTIONS.styles)
        enabled_disabled["disabled"] = InteractionStyle(
            background_token="surface-panel",
            border_token="border-default",
            text_token="text-muted",
            non_color_indicator="disabled-affordance",
        )
        with self.assertRaisesRegex(ValueError, "non-enabled"):
            InteractionRegistry(styles=enabled_disabled)

    def test_equivalent_required_states_fail_closed(self) -> None:
        duplicate = dict(DEFAULT_INTERACTIONS.styles)
        duplicate["hover"] = duplicate["default"]
        with self.assertRaisesRegex(ValueError, "distinguishable"):
            InteractionRegistry(styles=duplicate)

    def test_unknown_semantic_references_fail_on_resolution(self) -> None:
        invalid = dict(DEFAULT_INTERACTIONS.styles)
        invalid["hover"] = InteractionStyle(
            background_token="benchmark-success",
            border_token="accent-primary-hover",
            text_token="text-primary",
        )
        registry = InteractionRegistry(styles=invalid)

        with self.assertRaisesRegex(KeyError, "unknown semantic color token"):
            registry.resolve("hover")

    def test_unknown_interaction_state_is_rejected(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic interaction state"):
            interaction_style("accepted-run")


if __name__ == "__main__":
    unittest.main()
