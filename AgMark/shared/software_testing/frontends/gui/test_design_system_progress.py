"""Conformance tests for GUI progress-presentation semantics."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.progress import (
    DEFAULT_PROGRESS_STYLES,
    REQUIRED_PROGRESS_FORMS,
    ProgressRegistry,
    ProgressStyle,
    progress_style,
    resolved_progress,
)


class DefaultProgressRegistryTests(unittest.TestCase):
    def test_required_forms_are_complete_immutable_and_explicit(self) -> None:
        self.assertEqual(
            frozenset(DEFAULT_PROGRESS_STYLES.styles),
            REQUIRED_PROGRESS_FORMS,
        )
        with self.assertRaises(TypeError):
            DEFAULT_PROGRESS_STYLES.styles["bar"] = ProgressStyle(  # type: ignore[index]
                background_token="border-default",
                active_token="accent-primary",
                text_token="text-primary",
                value_indicator="replacement",
            )

        self.assertEqual(
            {
                form: progress_style(form).value_indicator
                for form in REQUIRED_PROGRESS_FORMS
            },
            {
                "bar": "linear-fill",
                "ring": "radial-arc",
                "counter": "numeric-counter",
                "stepper": "stage-stepper",
            },
        )

    def test_projection_preserves_only_supplied_progress_and_label(self) -> None:
        projection = resolved_progress(
            3,
            8,
            form="stepper",
            label="Scoring observations",
        )

        self.assertEqual(projection.form, "stepper")
        self.assertEqual(projection.current, 3)
        self.assertEqual(projection.total, 8)
        self.assertEqual(projection.label, "Scoring observations")
        self.assertEqual(projection.fraction, 3 / 8)
        self.assertEqual(projection.percent, 37.5)
        self.assertFalse(projection.visually_complete)

    def test_visual_completion_cannot_synthesize_authoritative_terminal_state(self) -> None:
        projection = resolved_progress(4, 4, form="ring", label="Generation")

        self.assertTrue(projection.visually_complete)
        self.assertEqual(projection.completion_semantics, "visual-only")
        self.assertEqual(projection.authority_semantics, "presentation-only")

    def test_all_required_forms_resolve_through_semantic_theme_tokens(self) -> None:
        for form in REQUIRED_PROGRESS_FORMS:
            with self.subTest(form=form):
                projection = resolved_progress(1, 2, form=form)
                self.assertEqual(projection.active, "#005FFD")
                self.assertEqual(projection.text, "#0B1748")
                expected_background = (
                    "#FFFFFF" if form == "counter" else "#D7E3EF"
                )
                self.assertEqual(projection.background, expected_background)

    def test_invalid_progress_inputs_fail_closed(self) -> None:
        invalid_values = (
            (-1, 4),
            (5, 4),
            (0, 0),
        )
        for current, total in invalid_values:
            with self.subTest(current=current, total=total):
                with self.assertRaises(ValueError):
                    resolved_progress(current, total)

        with self.assertRaisesRegex(ValueError, "integer"):
            resolved_progress(True, 4)
        with self.assertRaisesRegex(ValueError, "non-empty supplied label"):
            resolved_progress(1, 4, label="   ")

    def test_invalid_registry_or_unknown_form_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_PROGRESS_STYLES.styles)
        incomplete.pop("ring")
        with self.assertRaisesRegex(ValueError, "ring"):
            ProgressRegistry(styles=incomplete)

        with self.assertRaisesRegex(ValueError, "visual-only"):
            ProgressStyle(
                background_token="border-default",
                active_token="accent-primary",
                text_token="text-primary",
                value_indicator="linear-fill",
                completion_semantics="accepted",
            )

        with self.assertRaisesRegex(KeyError, "unknown semantic progress form"):
            progress_style("claim-ready")


if __name__ == "__main__":
    unittest.main()
