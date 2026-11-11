"""Conformance tests for GUI semantic status presentation."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.status import (
    DEFAULT_STATUS_STYLES,
    REQUIRED_STATUS_TONES,
    StatusRegistry,
    StatusStyle,
    resolved_status,
    status_style,
)


class DefaultStatusRegistryTests(unittest.TestCase):
    def test_required_tones_are_complete_immutable_and_non_color_distinct(self) -> None:
        self.assertEqual(
            frozenset(DEFAULT_STATUS_STYLES.styles),
            REQUIRED_STATUS_TONES,
        )
        with self.assertRaises(TypeError):
            DEFAULT_STATUS_STYLES.styles["neutral"] = StatusStyle(  # type: ignore[index]
                foreground_token="state-neutral",
                background_token="state-neutral-surface",
                icon_key="replacement",
            )

        icon_keys = {
            status_style(tone).icon_key for tone in REQUIRED_STATUS_TONES
        }
        self.assertEqual(len(icon_keys), len(REQUIRED_STATUS_TONES))

    def test_required_tones_use_their_semantic_state_tokens(self) -> None:
        expected = {
            "success": ("state-success", "state-success-surface"),
            "warning": ("state-warning", "state-warning-surface"),
            "error": ("state-error", "state-error-surface"),
            "active": ("state-active", "state-active-surface"),
            "neutral": ("state-neutral", "state-neutral-surface"),
        }
        actual = {
            tone: (
                status_style(tone).foreground_token,
                status_style(tone).background_token,
            )
            for tone in REQUIRED_STATUS_TONES
        }
        self.assertEqual(actual, expected)

    def test_resolution_preserves_supplied_label_without_state_inference(self) -> None:
        shared_labels = (
            "accepted",
            "blocked",
            "in-progress",
            "pending",
            "ready",
            "verified",
            "unavailable",
            "missing",
            "failed",
            "excluded",
            "non-scorable",
            "non-comparable",
            "not-generated",
        )
        for label in shared_labels:
            with self.subTest(label=label):
                badge = resolved_status(label, "neutral")
                self.assertEqual(badge.label, label)
                self.assertEqual(badge.tone, "neutral")
                self.assertEqual(badge.icon_key, "status-neutral")

    def test_resolution_uses_existing_semantic_theme_tokens(self) -> None:
        badge = resolved_status("example-state", "success")
        self.assertEqual(badge.foreground, "#0AA12A")
        self.assertEqual(badge.background, "#E9F8EA")
        self.assertEqual(badge.icon_key, "status-success")

    def test_incomplete_or_semantically_invalid_registry_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_STATUS_STYLES.styles)
        incomplete.pop("neutral")
        with self.assertRaisesRegex(ValueError, "neutral"):
            StatusRegistry(styles=incomplete)

        wrong_tokens = dict(DEFAULT_STATUS_STYLES.styles)
        wrong_tokens["warning"] = StatusStyle(
            foreground_token="state-error",
            background_token="state-error-surface",
            icon_key="status-warning",
        )
        with self.assertRaisesRegex(ValueError, "semantic state tokens"):
            StatusRegistry(styles=wrong_tokens)

        duplicate_icon = dict(DEFAULT_STATUS_STYLES.styles)
        duplicate_icon["active"] = StatusStyle(
            foreground_token="state-active",
            background_token="state-active-surface",
            icon_key="status-neutral",
        )
        with self.assertRaisesRegex(ValueError, "distinct non-color icon"):
            StatusRegistry(styles=duplicate_icon)

    def test_unknown_tone_and_empty_label_are_rejected(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic status tone"):
            status_style("benchmark-passed")

        with self.assertRaisesRegex(ValueError, "non-empty supplied label"):
            resolved_status("   ", "neutral")


if __name__ == "__main__":
    unittest.main()
