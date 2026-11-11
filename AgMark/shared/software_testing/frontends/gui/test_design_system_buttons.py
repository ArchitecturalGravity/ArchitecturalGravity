"""Conformance tests for GUI button and action-hierarchy presentation."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.buttons import (
    DEFAULT_BUTTON_STYLES,
    REQUIRED_BUTTON_ROLES,
    ButtonRegistry,
    ButtonStyle,
    button_style,
    resolved_button,
)


class DefaultButtonRegistryTests(unittest.TestCase):
    def test_required_roles_are_complete_immutable_and_distinguishable(self) -> None:
        self.assertEqual(
            frozenset(DEFAULT_BUTTON_STYLES.styles),
            REQUIRED_BUTTON_ROLES,
        )
        with self.assertRaises(TypeError):
            DEFAULT_BUTTON_STYLES.styles["primary"] = ButtonStyle(  # type: ignore[index]
                background_token="accent-primary",
                border_token="accent-primary",
                text_token="surface-panel",
            )

        signatures = {
            (
                style.background_token,
                style.border_token,
                style.text_token,
                style.compact,
                style.enabled,
                style.non_color_indicator,
            )
            for style in DEFAULT_BUTTON_STYLES.styles.values()
        }
        self.assertEqual(len(signatures), len(REQUIRED_BUTTON_ROLES))

    def test_primary_secondary_and_contextual_roles_preserve_action_hierarchy(self) -> None:
        primary = button_style("primary")
        self.assertEqual(primary.background_token, "accent-primary")
        self.assertEqual(primary.border_token, "accent-primary")
        self.assertEqual(primary.text_token, "surface-panel")
        self.assertTrue(primary.enabled)

        secondary = button_style("secondary")
        self.assertEqual(secondary.background_token, "surface-panel")
        self.assertEqual(secondary.border_token, "border-strong")
        self.assertEqual(secondary.text_token, "text-primary")
        self.assertTrue(secondary.enabled)

        contextual = button_style("contextual")
        self.assertTrue(contextual.compact)
        self.assertEqual(contextual.text_token, "text-secondary")
        self.assertTrue(contextual.enabled)

    def test_destructive_role_is_outlined_error_and_not_color_only(self) -> None:
        destructive = button_style("destructive")
        self.assertEqual(destructive.background_token, "surface-panel")
        self.assertEqual(destructive.border_token, "state-error")
        self.assertEqual(destructive.text_token, "state-error")
        self.assertTrue(destructive.enabled)
        self.assertEqual(
            destructive.non_color_indicator,
            "destructive-action",
        )

        resolved = resolved_button("destructive")
        self.assertEqual(resolved.background, "#FFFFFF")
        self.assertEqual(resolved.border, "#F0212D")
        self.assertEqual(resolved.text, "#F0212D")

    def test_unavailable_role_is_disabled_and_not_color_only(self) -> None:
        unavailable = button_style("unavailable")
        self.assertFalse(unavailable.enabled)
        self.assertEqual(unavailable.text_token, "text-muted")
        self.assertEqual(unavailable.non_color_indicator, "disabled-affordance")

    def test_resolution_uses_existing_semantic_theme_tokens(self) -> None:
        primary = resolved_button("primary")
        self.assertEqual(primary.background, "#005FFD")
        self.assertEqual(primary.border, "#005FFD")
        self.assertEqual(primary.text, "#FFFFFF")
        self.assertTrue(primary.enabled)

        contextual = resolved_button("contextual")
        self.assertEqual(contextual.background, "#FFFFFF")
        self.assertEqual(contextual.border, "#D7E3EF")
        self.assertEqual(contextual.text, "#44527A")
        self.assertTrue(contextual.compact)

    def test_incomplete_or_semantically_invalid_registry_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_BUTTON_STYLES.styles)
        incomplete.pop("unavailable")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            ButtonRegistry(styles=incomplete)

        invalid_primary = dict(DEFAULT_BUTTON_STYLES.styles)
        invalid_primary["primary"] = ButtonStyle(
            background_token="surface-panel",
            border_token="border-strong",
            text_token="text-primary",
            non_color_indicator="primary-action",
        )
        with self.assertRaisesRegex(ValueError, "saturated accent"):
            ButtonRegistry(styles=invalid_primary)

        enabled_unavailable = dict(DEFAULT_BUTTON_STYLES.styles)
        enabled_unavailable["unavailable"] = ButtonStyle(
            background_token="surface-panel",
            border_token="border-default",
            text_token="text-muted",
            non_color_indicator="disabled-affordance",
        )
        with self.assertRaisesRegex(ValueError, "non-enabled"):
            ButtonRegistry(styles=enabled_unavailable)

        color_only_unavailable = dict(DEFAULT_BUTTON_STYLES.styles)
        color_only_unavailable["unavailable"] = ButtonStyle(
            background_token="surface-panel",
            border_token="border-default",
            text_token="text-muted",
            enabled=False,
        )
        with self.assertRaisesRegex(ValueError, "non-color disabled cue"):
            ButtonRegistry(styles=color_only_unavailable)

    def test_unknown_semantic_reference_fails_on_resolution(self) -> None:
        invalid = dict(DEFAULT_BUTTON_STYLES.styles)
        invalid["secondary"] = ButtonStyle(
            background_token="benchmark-ready",
            border_token="border-strong",
            text_token="text-primary",
            non_color_indicator="secondary-action",
        )
        registry = ButtonRegistry(styles=invalid)

        with self.assertRaisesRegex(KeyError, "unknown semantic color token"):
            registry.resolve("secondary")

    def test_unknown_button_role_is_rejected(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic button role"):
            button_style("accepted-run")


if __name__ == "__main__":
    unittest.main()
