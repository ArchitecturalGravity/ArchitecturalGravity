"""Viewport-local compact Find panel geometry, navigation and tab lifetime."""
import tempfile
import unittest


class FindOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import StudioWindow, DocumentTab
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.color_schemes import SchemeStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window = StudioWindow('current', background=False, user_state=UserState(), scheme_store=SchemeStore(self.temp.name))
        self.tab = self.window._add_tab(DocumentTab('current', '\n'.join(f'Line {n} needle' for n in range(100))))
        self.window.resize(1100, 740)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.addCleanup(self.window.deleteLater)
        self.bar = self.tab.find_bar

    def assert_contained(self):
        viewport = self.tab.editor.viewport()
        self.assertIs(self.bar.parentWidget(), viewport)
        self.assertTrue(viewport.rect().contains(self.bar.geometry()))
        self.assertLessEqual(self.bar.width(), 440)
        self.assertEqual(self.bar.geometry().right(), viewport.width() - 7)
        for widget in (self.bar.query, self.bar.previous, self.bar.next, self.bar.case, self.bar.word, self.bar.feedback):
            self.assertTrue(self.bar.rect().contains(widget.mapTo(self.bar, widget.rect().topLeft())))
            self.assertTrue(self.bar.rect().contains(widget.mapTo(self.bar, widget.rect().bottomRight())))

    def test_viewport_overlay_does_not_relayout_editor_and_resizes_narrow(self):
        size = self.tab.editor.size()
        self.bar.open()
        self.app.processEvents()
        self.assertEqual(self.tab.editor.size(), size)
        self.assert_contained()
        self.assertLess(self.bar.height(), 90)
        image = self.bar.grab().toImage()
        self.assertEqual(image.pixelColor(5, 5).name(), '#edf2f7')
        self.assertFalse(self.bar.replace_row.isVisible())
        self.bar.disclosure.click()
        self.app.processEvents()
        self.assertTrue(self.bar.replace_row.isVisible())
        self.assertLess(self.bar.height(), 130)
        self.assertEqual(self.tab.editor.size(), size)
        self.window._show_side_panel()
        self.tab.editor_split.setSizes([270, 830])
        self.app.processEvents()
        self.assert_contained()
        self.assertEqual(self.bar.case.accessibleName(), 'Match case')
        self.assertEqual(self.bar.word.accessibleName(), 'Whole word')
        self.bar.query.setText('needle')
        self.bar.find()
        self.assertIn('of 100', self.bar.feedback.text())
        self.assert_contained()
        for widget in (self.bar.replacement, self.bar.replace, self.bar.replace_all):
            self.assertTrue(self.bar.rect().contains(widget.mapTo(self.bar, widget.rect().bottomRight())))
        self.window.resize(1400, 900)
        self.tab.editor_split.setSizes([1100, 300])
        self.app.processEvents()
        self.assert_contained()

    def test_keyboard_scroll_reopen_tab_switch_and_close(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        self.tab.editor.setFocus()
        QTest.keyClick(self.tab.editor, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        before = self.tab.source
        self.bar.query.setText('needle')
        QTest.keyClick(self.bar.query, Qt.Key.Key_Return)
        self.assertEqual(self.bar.feedback.text(), '1 of 100')
        QTest.keyClick(self.bar.query, Qt.Key.Key_Return)
        self.assertEqual(self.bar.feedback.text(), '2 of 100')
        QTest.keyClick(self.bar.query, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.bar.feedback.text(), '1 of 100')
        self.assertEqual(self.tab.source, before)
        self.tab.editor.verticalScrollBar().setValue(40)
        self.app.processEvents()
        self.assert_contained()
        QTest.keyClick(self.bar.query, Qt.Key.Key_Escape)
        self.assertTrue(self.bar.isHidden())
        self.bar.open()
        self.assertTrue(self.bar.query.hasFocus())
        self.bar.open()
        self.assert_contained()
        other = self.window.new_document()
        self.assertFalse(self.bar.active())
        self.assertFalse(self.bar.isVisible())
        self.assertFalse(self.bar.find())
        self.assertTrue(other.find_bar.isHidden())
        self.window.tabs.setCurrentWidget(self.tab)
        self.app.processEvents()
        self.assertTrue(self.bar.isVisible())
        self.assert_contained()
        self.window._close_tab(self.window.tabs.indexOf(self.tab))
        self.assertIs(self.window.current(), other)
        self.assertTrue(other.find_bar.isHidden())

    def test_selected_match_not_hidden_under_panel_when_space_available(self):
        from PySide6.QtGui import QTextCursor
        self.tab.editor.setPlainText('x' * 65 + ' needle\n' + '\n'.join('line' for _ in range(80)))
        self.tab.editor.moveCursor(QTextCursor.MoveOperation.Start)
        self.bar.open()
        self.bar.query.setText('needle')
        self.assertTrue(self.bar.find())
        self.app.processEvents()
        self.assert_contained()
        self.assertFalse(self.bar.geometry().intersects(self.tab.editor.cursorRect()))
        self.bar.disclosure.click()
        self.bar.replacement.setText('found')
        self.bar.replace_one()
        self.assertIn('found', self.tab.editor.toPlainText())
        self.tab.editor.undo()
        self.assertIn('needle', self.tab.editor.toPlainText())

    def test_backward_overlapping_matches_keep_valid_count(self):
        from PySide6.QtGui import QTextCursor
        self.tab.editor.selectAll()
        self.tab.editor.insertPlainText('aaa')
        self.tab.editor.moveCursor(QTextCursor.MoveOperation.Start)
        self.bar.open()
        self.bar.query.setText('aa')
        self.assertTrue(self.bar.find())
        self.assertEqual(self.bar.feedback.text(), '1 of 2')
        self.assertTrue(self.bar.find(True))
        self.assertEqual(self.bar.feedback.text(), '2 of 2 · Wrapped')
        self.bar.replacement.setText('x')
        self.bar.replace_everywhere()
        self.assertEqual(self.tab.editor.toPlainText(), 'xa')
        self.tab.editor.undo()
        self.assertEqual(self.tab.editor.toPlainText(), 'aaa')
