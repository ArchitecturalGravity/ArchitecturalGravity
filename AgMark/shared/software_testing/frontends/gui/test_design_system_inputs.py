"""Conformance tests for GUI input-presentation semantics."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.inputs import (
    DEFAULT_INPUT_STYLES,
    REQUIRED_INPUT_ROLES,
    InputRegistry,
    InputStyle,
    credential_echo_mode,
    input_style,
    resolved_input,
)


class DefaultInputRegistryTests(unittest.TestCase):
    def test_required_roles_are_complete_and_immutable(self) -> None:
        self.assertEqual(frozenset(DEFAULT_INPUT_STYLES.styles), REQUIRED_INPUT_ROLES)
        with self.assertRaises(TypeError):
            DEFAULT_INPUT_STYLES.styles["text"] = input_style("numeric")  # type: ignore[index]

    def test_required_roles_share_consistent_layout_focus_and_validation(self) -> None:
        styles = [input_style(role) for role in sorted(REQUIRED_INPUT_ROLES)]
        common = {
            (
                style.label_placement,
                style.accessory_placement,
                style.control_height_metric,
                style.focus_border_token,
                style.validation_border_token,
                style.validation_indicator,
            )
            for style in styles
        }
        self.assertEqual(
            common,
            {
                (
                    "above",
                    "trailing",
                    "control-height",
                    "focus-ring",
                    "state-error",
                    "validation-message",
                )
            },
        )

    def test_credential_is_obscured_by_default_and_reveal_is_stateless(self) -> None:
        credential = input_style("credential")
        self.assertTrue(credential.obscured_by_default)
        self.assertTrue(credential.allows_transient_reveal)
        self.assertEqual(credential_echo_mode(), "obscured")
        self.assertEqual(credential_echo_mode(reveal_requested=True), "visible")
        self.assertEqual(credential_echo_mode(), "obscured")
        with self.assertRaisesRegex(ValueError, "boolean"):
            credential_echo_mode(reveal_requested=1)  # type: ignore[arg-type]

    def test_numeric_input_exposes_optional_spinner_affordance_only(self) -> None:
        self.assertTrue(input_style("numeric").numeric_spinner)
        self.assertFalse(input_style("text").numeric_spinner)
        self.assertFalse(input_style("credential").numeric_spinner)

    def test_resolution_uses_existing_theme_and_metric_registries(self) -> None:
        resolved = resolved_input("credential")
        self.assertEqual(resolved.control_height_px, 40)
        self.assertEqual(resolved.background, "#FFFFFF")
        self.assertEqual(resolved.border, "#D7E3EF")
        self.assertEqual(resolved.text, "#0B1748")
        self.assertEqual(resolved.placeholder, "#6C7A99")
        self.assertEqual(resolved.focus_border, "#0B73FF")
        self.assertEqual(resolved.validation_border, "#F0212D")
        self.assertEqual(resolved.validation_indicator, "validation-message")
        self.assertTrue(resolved.obscured_by_default)

    def test_incomplete_or_inconsistent_registry_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_INPUT_STYLES.styles)
        incomplete.pop("credential")
        with self.assertRaisesRegex(ValueError, "credential"):
            InputRegistry(styles=incomplete)

        inconsistent = dict(DEFAULT_INPUT_STYLES.styles)
        original = inconsistent["numeric"]
        inconsistent["numeric"] = InputStyle(
            label_placement="inline",
            accessory_placement=original.accessory_placement,
            control_height_metric=original.control_height_metric,
            background_token=original.background_token,
            border_token=original.border_token,
            text_token=original.text_token,
            placeholder_token=original.placeholder_token,
            focus_border_token=original.focus_border_token,
            validation_border_token=original.validation_border_token,
            validation_indicator=original.validation_indicator,
            numeric_spinner=True,
        )
        with self.assertRaisesRegex(ValueError, "consistent"):
            InputRegistry(styles=inconsistent)

    def test_credential_visibility_contract_fails_closed(self) -> None:
        invalid = dict(DEFAULT_INPUT_STYLES.styles)
        original = invalid["credential"]
        invalid["credential"] = InputStyle(
            label_placement=original.label_placement,
            accessory_placement=original.accessory_placement,
            control_height_metric=original.control_height_metric,
            background_token=original.background_token,
            border_token=original.border_token,
            text_token=original.text_token,
            placeholder_token=original.placeholder_token,
            focus_border_token=original.focus_border_token,
            validation_border_token=original.validation_border_token,
            validation_indicator=original.validation_indicator,
        )
        with self.assertRaisesRegex(ValueError, "obscured by default"):
            InputRegistry(styles=invalid)

    def test_unknown_semantic_references_fail_on_resolution(self) -> None:
        invalid = dict(DEFAULT_INPUT_STYLES.styles)
        original = invalid["text"]
        invalid["text"] = InputStyle(
            label_placement=original.label_placement,
            accessory_placement=original.accessory_placement,
            control_height_metric="accepted-run-height",
            background_token=original.background_token,
            border_token=original.border_token,
            text_token=original.text_token,
            placeholder_token=original.placeholder_token,
            focus_border_token=original.focus_border_token,
            validation_border_token=original.validation_border_token,
            validation_indicator=original.validation_indicator,
        )
        invalid["credential"] = InputStyle(
            label_placement=invalid["text"].label_placement,
            accessory_placement=invalid["text"].accessory_placement,
            control_height_metric=invalid["text"].control_height_metric,
            background_token=invalid["text"].background_token,
            border_token=invalid["text"].border_token,
            text_token=invalid["text"].text_token,
            placeholder_token=invalid["text"].placeholder_token,
            focus_border_token=invalid["text"].focus_border_token,
            validation_border_token=invalid["text"].validation_border_token,
            validation_indicator=invalid["text"].validation_indicator,
            obscured_by_default=True,
            allows_transient_reveal=True,
        )
        invalid["numeric"] = InputStyle(
            label_placement=invalid["text"].label_placement,
            accessory_placement=invalid["text"].accessory_placement,
            control_height_metric=invalid["text"].control_height_metric,
            background_token=invalid["text"].background_token,
            border_token=invalid["text"].border_token,
            text_token=invalid["text"].text_token,
            placeholder_token=invalid["text"].placeholder_token,
            focus_border_token=invalid["text"].focus_border_token,
            validation_border_token=invalid["text"].validation_border_token,
            validation_indicator=invalid["text"].validation_indicator,
            numeric_spinner=True,
        )
        registry = InputRegistry(styles=invalid)
        with self.assertRaisesRegex(KeyError, "unknown semantic layout metric"):
            registry.resolve("text")

    def test_unknown_input_role_is_rejected(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic input role"):
            input_style("accepted-run")


if __name__ == "__main__":
    unittest.main()
