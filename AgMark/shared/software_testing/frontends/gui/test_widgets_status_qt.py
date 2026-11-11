"""Conformance tests for the concrete PySide6 semantic status-badge widget."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.widgets.status import PYSIDE6_AVAILABLE, StatusBadge

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class StatusBadgeWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.widget = StatusBadge("accepted", "neutral")
        self.addCleanup(self.widget.deleteLater)

    def test_context_label_survives_status_changes_without_changing_semantics(self) -> None:
        self.widget.set_context_label("Selected runner")
        self.widget.set_status("Connected", "success")
        self.assertEqual(self.widget.displayed_label, "Selected runner: Connected")
        self.assertEqual(self.widget.label, "Connected")
        self.assertEqual(self.widget.accessibleName(), self.widget.displayed_label)
        self.widget.set_context_label(None)
        self.assertEqual(self.widget.displayed_label, "Connected")
        with self.assertRaises(ValueError):
            self.widget.set_context_label("")

    def test_badge_preserves_explicit_label_and_tone_as_presentation_only(self) -> None:
        self.assertEqual(self.widget.label, "accepted")
        self.assertEqual(self.widget.displayed_label, "accepted")
        self.assertEqual(self.widget.tone, "neutral")
        self.assertEqual(self.widget.icon_key, "status-neutral")
        self.assertFalse(self.widget.semantic_icon.isNull())
        self.assertFalse(self.widget._icon_label.pixmap().isNull())
        self.assertEqual(
            self.widget._icon_label.property("semanticIconRole"),
            "status-neutral",
        )
        self.assertEqual(self.widget.accessibleName(), "accepted")
        self.assertEqual(self.widget.authority_semantics, "presentation-only")

    def test_label_text_does_not_infer_or_override_semantic_tone(self) -> None:
        self.widget.set_status("accepted", "error")

        self.assertEqual(self.widget.label, "accepted")
        self.assertEqual(self.widget.displayed_label, "accepted")
        self.assertEqual(self.widget.tone, "error")
        self.assertEqual(self.widget.icon_key, "status-error")

        self.widget.set_status("blocked", "success")
        self.assertEqual(self.widget.label, "blocked")
        self.assertEqual(self.widget.tone, "success")
        self.assertEqual(self.widget.icon_key, "status-success")

    def test_required_tones_have_distinct_visible_non_color_cues(self) -> None:
        icon_texts = set()
        for tone in ("success", "warning", "error", "active", "neutral"):
            with self.subTest(tone=tone):
                self.widget.set_status("same-label", tone)
                icon_texts.add(self.widget.icon_text)
                self.assertEqual(self.widget.displayed_label, "same-label")

        self.assertEqual(len(icon_texts), 5)

    def test_invalid_semantic_input_fails_closed(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic status tone"):
            self.widget.set_status("accepted", "benchmark-passed")

        with self.assertRaisesRegex(ValueError, "non-empty supplied label"):
            self.widget.set_status("   ", "neutral")


if __name__ == "__main__":
    unittest.main()
