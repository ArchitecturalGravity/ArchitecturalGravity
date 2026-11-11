"""Conformance tests for explicit caller-owned action widgets."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.widgets.actions import ArtifactActionButton, PYSIDE6_AVAILABLE

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ArtifactActionWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_artifact_action_uses_explicit_availability_and_caller_operation(self) -> None:
        calls: list[str] = []
        button = ArtifactActionButton(
            "Download",
            lambda: calls.append("download"),
            available=True,
        )
        self.addCleanup(button.deleteLater)

        self.assertEqual(button.displayed_label, "Download")
        self.assertEqual(button.requested_role, "contextual")
        self.assertEqual(button.role, "contextual")
        self.assertTrue(button.available)
        self.assertTrue(button.isEnabled())
        self.assertEqual(button.authority_semantics, "presentation-only")
        self.assertEqual(calls, [])

        button.click()
        self.assertEqual(calls, ["download"])

        button.set_available(False)
        self.assertFalse(button.available)
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.role, "unavailable")
        button.click()
        self.assertEqual(calls, ["download"])

    def test_artifact_action_label_never_infers_permission(self) -> None:
        calls: list[str] = []
        enabled = ArtifactActionButton(
            "blocked",
            lambda: calls.append("enabled"),
            available=True,
        )
        unavailable = ArtifactActionButton(
            "verified",
            lambda: calls.append("unavailable"),
            available=False,
        )
        self.addCleanup(enabled.deleteLater)
        self.addCleanup(unavailable.deleteLater)

        self.assertTrue(enabled.isEnabled())
        self.assertFalse(unavailable.isEnabled())

        enabled.click()
        unavailable.click()
        self.assertEqual(calls, ["enabled"])

    def test_invalid_inputs_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "operation"):
            ArtifactActionButton("Download", object(), available=True)

        with self.assertRaisesRegex(ValueError, "available"):
            ArtifactActionButton("Download", lambda: None, available="yes")

        with self.assertRaisesRegex(KeyError, "unknown semantic button role"):
            ArtifactActionButton("Download", lambda: None, available=False, role="verified")

        with self.assertRaisesRegex(ValueError, "enabled semantic action role"):
            ArtifactActionButton("Download", lambda: None, available=False, role="unavailable")


if __name__ == "__main__":
    unittest.main()
