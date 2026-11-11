"""Conformance tests for concrete PySide6 reusable input widgets."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.widgets.inputs import (
    CredentialInput,
    NumericInput,
    PYSIDE6_AVAILABLE,
    SelectInput,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication, QLineEdit


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class InputWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_select_preserves_supplied_options_selection_and_semantics(self) -> None:
        widget = SelectInput(
            "Outcome",
            ("accepted", "blocked", "unresolved"),
            "accepted",
            accessory_text="Caller supplied",
        )
        self.addCleanup(widget.deleteLater)

        self.assertEqual(widget.label, "Outcome")
        self.assertEqual(
            widget.options,
            ("accepted", "blocked", "unresolved"),
        )
        self.assertEqual(widget.value, "accepted")
        self.assertEqual(widget.accessory_text, "Caller supplied")
        self.assertEqual(widget.role, "text")
        self.assertEqual(widget.authority_semantics, "presentation-only")

        widget.set_value("blocked")
        self.assertEqual(widget.value, "blocked")
        self.assertEqual(widget.combo_box.currentText(), "blocked")

        widget.set_value(None)
        self.assertIsNone(widget.value)
        self.assertEqual(widget.combo_box.currentIndex(), -1)

    def test_select_rejects_unsupplied_or_ambiguous_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            SelectInput("Mode", ("same", "same"))

        widget = SelectInput("Mode", ("one", "two"))
        self.addCleanup(widget.deleteLater)
        with self.assertRaisesRegex(ValueError, "supplied options"):
            widget.set_value("accepted-run")

    def test_credential_is_obscured_and_reveal_is_hold_only(self) -> None:
        secret = "not-for-persistence"
        widget = CredentialInput(
            "API key",
            secret,
            accessory_text="Session only",
        )
        self.addCleanup(widget.deleteLater)

        self.assertEqual(widget.value, secret)
        self.assertTrue(widget.obscured)
        self.assertEqual(
            widget.line_edit.echoMode(),
            QLineEdit.EchoMode.Password,
        )
        self.assertEqual(widget.accessory_text, "Session only")
        self.assertNotIn(secret, widget.accessibleName())
        self.assertNotIn(secret, widget.reveal_button.accessibleName())

        widget.reveal_button.pressed.emit()
        self.assertFalse(widget.obscured)
        self.assertEqual(widget.line_edit.echoMode(), QLineEdit.EchoMode.Normal)
        self.assertEqual(widget.value, secret)

        widget.reveal_button.released.emit()
        self.assertTrue(widget.obscured)
        self.assertEqual(widget.line_edit.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(widget.value, secret)

    def test_validation_and_accessory_state_are_explicit_presentation(self) -> None:
        widget = CredentialInput("Token")
        self.addCleanup(widget.deleteLater)

        self.assertTrue(widget.is_valid)
        self.assertIsNone(widget.validation_message)
        self.assertEqual(
            widget.line_edit.property("validationState"),
            "valid",
        )

        widget.set_validation_message("Required")
        self.assertFalse(widget.is_valid)
        self.assertEqual(widget.validation_message, "Required")
        self.assertEqual(
            widget.line_edit.property("validationState"),
            "invalid",
        )
        self.assertEqual(widget.accessibleDescription(), "Required")

        widget.set_accessory_text("Transient")
        self.assertEqual(widget.accessory_text, "Transient")
        widget.set_validation_message(None)
        widget.set_accessory_text(None)
        self.assertTrue(widget.is_valid)
        self.assertIsNone(widget.validation_message)
        self.assertIsNone(widget.accessory_text)

    def test_numeric_input_preserves_explicit_range_step_and_value(self) -> None:
        widget = NumericInput(
            "Temperature",
            0.7,
            minimum=0.0,
            maximum=2.0,
            step=0.1,
            decimals=1,
        )
        self.addCleanup(widget.deleteLater)

        self.assertEqual(widget.role, "numeric")
        self.assertEqual(widget.authority_semantics, "presentation-only")
        self.assertEqual(widget.minimum, 0.0)
        self.assertEqual(widget.maximum, 2.0)
        self.assertAlmostEqual(widget.value, 0.7)
        self.assertAlmostEqual(widget.spin_box.singleStep(), 0.1)
        self.assertEqual(widget.spin_box.decimals(), 1)

        widget.set_value(1.5)
        self.assertAlmostEqual(widget.value, 1.5)

        with self.assertRaisesRegex(ValueError, "numeric range"):
            widget.set_value(3.0)
        self.assertAlmostEqual(widget.value, 1.5)

    def test_invalid_caller_input_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "label"):
            CredentialInput("   ")

        with self.assertRaisesRegex(ValueError, "string"):
            CredentialInput("Token", 7)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "numeric range"):
            NumericInput(
                "Count",
                1,
                minimum=2,
                maximum=2,
            )

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            NumericInput(
                "Count",
                1,
                minimum=0,
                maximum=2,
                step=0,
            )

        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            NumericInput(
                "Count",
                1,
                minimum=0,
                maximum=2,
                decimals=True,  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
