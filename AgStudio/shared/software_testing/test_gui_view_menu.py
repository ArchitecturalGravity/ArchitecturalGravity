"""View choices stay open, synchronize checks, and never edit documents."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class ViewMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        from AgStudio.gui.user_state import UserState
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window = StudioWindow('current', background=False, user_state=UserState(),
                                   scheme_store=SchemeStore(Path(self.temp.name)))
        self.window.resize(1180, 780)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox
        self.window.view_menu.hide()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def open_view(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        menu = self.window.view_menu
        bar = self.window.menuBar()
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.actionGeometry(menu.menuAction()).center())
        self.app.processEvents()
        self.assertTrue(menu.isVisible())
        return menu

    def assert_panels(self):
        for key, attribute in (('side_panel', 'side_panel'), ('error_list', 'diagnostics_panel'),
                               ('document_map', 'document_map')):
            checked = self.window.panel_actions[key].isChecked()
            self.assertEqual(self.window.user_state.panels[key], checked)
            for index in range(self.window.tabs.count()):
                self.assertEqual(not getattr(self.window.tabs.widget(index), attribute).isHidden(), checked)

    def test_repeated_mouse_toggles_keep_same_popup_open_and_preserve_source_selection(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QSignalSpy, QTest
        first = self.window.current()
        first.editor.insertPlainText('Task: Keep 🌍 exact text\n- Child\n')
        cursor = first.editor.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
        first.editor.setTextCursor(cursor)
        before = (first.source, first.dirty, cursor.position(), cursor.anchor(),
                  first.editor.document().isUndoAvailable())
        self.window.new_document()
        self.window.tabs.setCurrentWidget(first)
        menu = self.open_view()
        spies = {key: QSignalSpy(action.triggered) for key, action in self.window.panel_actions.items()}
        for round_number in range(4):
            for key, action in self.window.panel_actions.items():
                QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center())
                self.app.processEvents()
                self.assertEqual(action.isChecked(), bool(round_number % 2))
                self.assertEqual(spies[key].count(), round_number + 1)
                self.assertTrue(menu.isVisible())
                self.assertIs(self.app.activePopupWidget(), menu)
                self.assert_panels()
            # Moving beyond the menu, including over another menu-bar item,
            # must not end this popup session or silently change a choice.
            QTest.mouseMove(menu, QPoint(menu.width() + 25, menu.height() + 25))
            file_action = self.window.menuBar().actions()[0]
            over_file = self.window.menuBar().mapToGlobal(self.window.menuBar().actionGeometry(file_action).center())
            QTest.mouseMove(menu, menu.mapFromGlobal(over_file))
            self.app.processEvents()
            self.assertTrue(menu.isVisible())
            self.assertIs(self.app.activePopupWidget(), menu)
        self.assertEqual((first.source, first.dirty, first.editor.textCursor().position(),
                          first.editor.textCursor().anchor(), first.editor.document().isUndoAvailable()), before)
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=QPoint(menu.width() + 30, menu.height() + 30))
        self.app.processEvents()
        self.assertFalse(menu.isVisible())
        self.assert_panels()

    def test_keyboard_activation_keeps_popup_open_and_escape_dismisses(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        menu = self.open_view()
        for key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            for action in self.window.panel_actions.values():
                previous = action.isChecked()
                menu.setActiveAction(action)
                QTest.keyClick(menu, key)
                self.app.processEvents()
                self.assertEqual(action.isChecked(), not previous)
                self.assertTrue(menu.isVisible())
                self.assert_panels()
        before = self.window.user_state.panels.copy()
        QTest.keyClick(menu, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(menu.isVisible())
        self.assertEqual(self.window.user_state.panels, before)

    def test_top_level_color_scheme_action_opens_dialog_and_cancel_rolls_back(self):
        from copy import deepcopy
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QDialog
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        actions = self.window.menuBar().actions()
        self.assertEqual([a.text() for a in actions], ['File', 'Edit', 'View', 'Color Scheme'])
        color_action = actions[-1]
        self.assertIsNone(color_action.menu())
        self.assertNotIn(color_action, self.window.view_menu.actions())
        tab = self.window.current()
        tab.editor.insertPlainText('Task: Preserve selection\n')
        cursor = tab.editor.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
        tab.editor.setTextCursor(cursor)
        source = (tab.source, tab.dirty, cursor.position(), cursor.anchor(), tab.editor.document().isUndoAvailable())
        original = deepcopy(self.window.color_scheme)
        opened = []
        def cancel_preview(dialog):
            opened.append(dialog)
            self.assertEqual(dialog.windowTitle(), 'Color Scheme')
            dialog.roles.setCurrentIndex(dialog.roles.findData('editor'))
            dialog.controls['background'][0].setValue((original['editor']['background'][0] + 31) % 256)
            self.assertNotEqual(self.window.color_scheme, original)
            dialog.reject()
            return QDialog.DialogCode.Rejected
        with patch.object(ColorSchemeDialog, 'exec', new=cancel_preview):
            QTest.mouseClick(self.window.menuBar(), Qt.MouseButton.LeftButton,
                             pos=self.window.menuBar().actionGeometry(color_action).center())
        self.assertEqual(len(opened), 1)
        self.assertEqual(self.window.color_scheme, original)
        self.assertEqual((tab.source, tab.dirty, tab.editor.textCursor().position(), tab.editor.textCursor().anchor(),
                          tab.editor.document().isUndoAvailable()), source)
        self.assertFalse((Path(self.temp.name) / 'selected.json').exists())


if __name__ == '__main__':
    unittest.main()
