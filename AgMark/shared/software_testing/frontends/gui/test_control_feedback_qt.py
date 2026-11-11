"""Interaction feedback regressions for actual application controls."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from AgMark.gui.widgets.buttons import ActionButton, IconButton, PYSIDE6_AVAILABLE

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QEvent, QPoint, Qt
    from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QCheckBox, QTabBar
    from AgMark.gui.design_system.theme import apply_application_theme


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is unavailable")
class ControlFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_application_theme(cls.app)

    def polish(self, widget):
        self.addCleanup(widget.deleteLater)
        widget.ensurePolished()
        self.app.sendEvent(widget, QEvent(QEvent.Type.Enter))
        return widget

    def test_clickable_controls_get_pointer_and_disabled_controls_do_not(self):
        for control in (ActionButton("Build Plan", "primary"), IconButton("i", "Details"), QComboBox(), QCheckBox("Enabled")):
            with self.subTest(control=type(control).__name__):
                self.polish(control)
                self.assertEqual(control.cursor().shape(), Qt.CursorShape.PointingHandCursor)
                control.setEnabled(False)
                self.assertEqual(control.cursor().shape(), Qt.CursorShape.ArrowCursor)
                control.setEnabled(True)
                self.assertEqual(control.cursor().shape(), Qt.CursorShape.PointingHandCursor)

    def test_text_inputs_keep_text_cursor(self):
        control = self.polish(QLineEdit())
        self.assertEqual(control.cursor().shape(), Qt.CursorShape.IBeamCursor)
        combo = QComboBox()
        combo.setEditable(True)
        self.polish(combo)
        self.assertEqual(combo.lineEdit().cursor().shape(), Qt.CursorShape.IBeamCursor)

    def test_tab_gaps_do_not_claim_to_be_clickable(self):
        tabs = QTabBar()
        tabs.addTab("Summary")
        with patch("AgMark.gui.widgets.interaction.QCursor") as cursor:
            cursor.pos.return_value = tabs.mapToGlobal(QPoint(-100, -100))
            self.polish(tabs)
            self.assertEqual(tabs.cursor().shape(), Qt.CursorShape.ArrowCursor)
            cursor.pos.return_value = tabs.mapToGlobal(tabs.tabRect(0).center())
            self.app.sendEvent(tabs, QEvent(QEvent.Type.Enter))
            self.assertEqual(tabs.cursor().shape(), Qt.CursorShape.PointingHandCursor)
            tabs.setTabEnabled(0, False)
            self.app.sendEvent(tabs, QEvent(QEvent.Type.Enter))
            self.assertEqual(tabs.cursor().shape(), Qt.CursorShape.ArrowCursor)

    def test_semantic_buttons_have_guarded_hover_and_preserve_focus(self):
        for role in ("primary", "secondary", "contextual", "destructive", "unavailable"):
            button = self.polish(ActionButton("Action", role))
            sheet = button.styleSheet()
            self.assertIn(":hover:enabled", sheet)
            self.assertIn(":pressed:enabled", sheet)
            self.assertIn(":focus:enabled", sheet)
            self.assertIn(":disabled", sheet)
            self.assertLess(sheet.index(":hover:enabled"), sheet.index(":focus:enabled"))

    def test_cursor_installation_is_idempotent(self):
        previous = self.app._arcgrav_control_cursors
        apply_application_theme(self.app)
        self.assertIs(previous, self.app._arcgrav_control_cursors)
