"""Conformance tests for concrete PySide6 action and icon widgets."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.widgets.buttons import (
    ActionButton,
    IconButton,
    PYSIDE6_AVAILABLE,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ActionWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_action_button_preserves_label_and_explicit_role(self) -> None:
        button = ActionButton(
            "Run benchmark",
            "primary",
            icon_role="plan-build",
        )
        self.addCleanup(button.deleteLater)

        self.assertEqual(button.displayed_label, "Run benchmark")
        self.assertEqual(button.accessibleName(), "Run benchmark")
        self.assertEqual(button.role, "primary")
        self.assertEqual(button.icon_role, "plan-build")
        self.assertFalse(button.icon().isNull())
        self.assertTrue(button.isEnabled())
        self.assertEqual(button.presentation.background, "#005FFD")
        self.assertEqual(button.non_color_indicator, "primary-action")
        self.assertEqual(button.authority_semantics, "presentation-only")

    def test_label_text_never_infers_availability_or_authority(self) -> None:
        button = ActionButton("blocked", "primary")
        self.addCleanup(button.deleteLater)
        self.assertTrue(button.isEnabled())
        self.assertEqual(button.role, "primary")

        button.set_label("accepted")
        self.assertEqual(button.displayed_label, "accepted")
        self.assertEqual(button.role, "primary")
        self.assertTrue(button.isEnabled())

        button.set_role("unavailable")
        self.assertEqual(button.displayed_label, "accepted")
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.non_color_indicator, "disabled-affordance")
        self.assertEqual(
            button.property("nonColorIndicator"),
            "disabled-affordance",
        )

    def test_icon_button_preserves_explicit_cue_accessibility_and_role(self) -> None:
        button = IconButton("i", "Information")
        self.addCleanup(button.deleteLater)

        self.assertEqual(button.icon_text, "i")
        self.assertEqual(button.accessibleName(), "Information")
        self.assertEqual(button.role, "contextual")
        self.assertTrue(button.presentation.compact)
        self.assertTrue(button.isEnabled())
        self.assertEqual(button.authority_semantics, "presentation-only")

        button.set_role("unavailable")
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.icon_text, "i")
        self.assertEqual(button.accessibleName(), "Information")

    def test_invalid_semantic_or_accessible_input_fails_closed(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic button role"):
            ActionButton("Run", "accepted-run")

        with self.assertRaisesRegex(ValueError, "label"):
            ActionButton("   ", "primary")

        with self.assertRaisesRegex(KeyError, "unknown semantic icon role"):
            ActionButton("Run", "primary", icon_role="stock-forward")

        with self.assertRaisesRegex(ValueError, "icon_role"):
            ActionButton("Run", "primary", icon_role="   ")

        with self.assertRaisesRegex(ValueError, "icon_text"):
            IconButton("", "More actions")

        with self.assertRaisesRegex(ValueError, "accessible_name"):
            IconButton("i", "   ")


if __name__ == "__main__":
    unittest.main()
