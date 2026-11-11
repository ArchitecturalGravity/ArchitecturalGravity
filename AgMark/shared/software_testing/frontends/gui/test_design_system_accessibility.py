"""Conformance tests for GUI accessibility presentation primitives."""

from __future__ import annotations

from dataclasses import fields
import unittest

from AgMark.gui.design_system.accessibility import (
    ContrastRequirement,
    ContrastStandard,
    KeyboardFocusOrder,
    PresentationAccommodations,
    contrast_ratio,
    relative_luminance,
    validate_non_color_state_cues,
)


class AccessibilityPrimitiveTests(unittest.TestCase):
    def test_color_math_uses_exact_relative_luminance_and_contrast(self) -> None:
        self.assertAlmostEqual(relative_luminance("#000000"), 0.0)
        self.assertAlmostEqual(relative_luminance("#FFFFFF"), 1.0)
        self.assertAlmostEqual(contrast_ratio("#000000", "#FFFFFF"), 21.0)

        with self.assertRaisesRegex(ValueError, "#RRGGBB"):
            relative_luminance("white")

    def test_caller_supplied_contrast_standard_validates_semantic_theme_tokens(self) -> None:
        standard = ContrastStandard(
            name="desktop-example",
            requirements=(
                ContrastRequirement(
                    role="primary-text",
                    foreground_token="text-primary",
                    background_token="surface-panel",
                    minimum_ratio=4.5,
                ),
                ContrastRequirement(
                    role="focus-indicator",
                    foreground_token="focus-ring",
                    background_token="surface-panel",
                    minimum_ratio=3.0,
                ),
            ),
        )

        results = standard.validate()
        self.assertEqual(
            tuple(result.role for result in results),
            ("primary-text", "focus-indicator"),
        )
        self.assertTrue(all(result.passes for result in results))

    def test_optional_contrast_validation_fails_closed_for_caller_supplied_policy(self) -> None:
        strict = ContrastStandard(
            name="caller-selected-threshold",
            requirements=(
                ContrastRequirement(
                    role="muted-text",
                    foreground_token="text-muted",
                    background_token="surface-panel",
                    minimum_ratio=4.5,
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "muted-text"):
            strict.validate()

        unknown_token = ContrastStandard(
            name="unknown-token",
            requirements=(
                ContrastRequirement(
                    role="unknown",
                    foreground_token="benchmark-success",
                    background_token="surface-panel",
                    minimum_ratio=3.0,
                ),
            ),
        )
        with self.assertRaisesRegex(KeyError, "unknown semantic color token"):
            unknown_token.evaluate()

    def test_contrast_policy_inputs_are_explicit_and_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "1.0 through 21.0"):
            ContrastRequirement(
                role="bad",
                foreground_token="text-primary",
                background_token="surface-panel",
                minimum_ratio=0.5,
            )

        requirement = ContrastRequirement(
            role="duplicate",
            foreground_token="text-primary",
            background_token="surface-panel",
            minimum_ratio=4.5,
        )
        with self.assertRaisesRegex(ValueError, "roles must be unique"):
            ContrastStandard(
                name="duplicates",
                requirements=(requirement, requirement),
            )

    def test_keyboard_focus_order_is_explicit_immutable_and_unique(self) -> None:
        order = KeyboardFocusOrder(("benchmark", "runner", "run"))
        self.assertEqual(order.position("benchmark"), 0)
        self.assertEqual(order.position("run"), 2)

        with self.assertRaisesRegex(KeyError, "unknown keyboard focus control"):
            order.position("report")

        with self.assertRaisesRegex(ValueError, "duplicate"):
            KeyboardFocusOrder(("run", "run"))

        with self.assertRaisesRegex(ValueError, "sequence"):
            KeyboardFocusOrder("run")  # type: ignore[arg-type]

    def test_presentation_accommodations_carry_only_local_presentation_state(self) -> None:
        accommodations = PresentationAccommodations(
            font_scale=1.25,
            zoom=1.5,
            contrast_profile="high-contrast",
            theme_name="accessibility-light",
        )
        self.assertEqual(accommodations.font_scale, 1.25)
        self.assertEqual(accommodations.zoom, 1.5)

        field_names = {field.name for field in fields(PresentationAccommodations)}
        self.assertEqual(
            field_names,
            {"font_scale", "zoom", "contrast_profile", "theme_name"},
        )
        self.assertTrue(
            field_names.isdisjoint(
                {
                    "benchmark_id",
                    "evidence",
                    "report",
                    "reconstruction",
                    "accepted_run",
                }
            )
        )

        with self.assertRaisesRegex(ValueError, "finite positive"):
            PresentationAccommodations(font_scale=0.0)

    def test_default_state_recipes_preserve_non_color_accessibility_cues(self) -> None:
        self.assertIsNone(validate_non_color_state_cues())


if __name__ == "__main__":
    unittest.main()
