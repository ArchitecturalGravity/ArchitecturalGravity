"""Find/replace arrow artwork and native interactions across installed Qt styles."""
import unittest


class FindCaretTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtWidgets import QStyleFactory
        self.original_style = self.app.style().objectName()
        self.styles = [name for name in QStyleFactory.keys()
                       if name.casefold() in ('fusion', 'windows', 'windowsvista', 'windows11')]
        self.windows = []

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        for window in self.windows:
            window.close()
            window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.setStyle(self.original_style)

    def make_bar(self, style):
        from PySide6.QtWidgets import QWidget, QPlainTextEdit, QVBoxLayout
        from AgStudio.gui.find_bar import FindBar
        self.app.setStyle(style)
        tab = QWidget()
        tab.editor = QPlainTextEdit('needle one needle two needle')
        layout = QVBoxLayout(tab)
        layout.addWidget(tab.editor)
        bar = FindBar(tab)
        self.windows.append(tab)
        tab.resize(650, 350)
        tab.show()
        tab.activateWindow()
        bar.open()
        bar.query.setText('needle')
        self.app.processEvents()
        return tab, bar

    def test_native_hit_targets_navigation_disclosure_and_keyboard(self):
        from PySide6.QtCore import QPoint, QSize, Qt
        from PySide6.QtTest import QTest
        from AgStudio.gui.compact_arrow import CompactArrowButton
        for style in self.styles:
            with self.subTest(style=style):
                tab, bar = self.make_bar(style)
                before = tab.editor.toPlainText()
                undo = tab.editor.document().availableUndoSteps()
                for button, name in ((bar.previous, 'Previous match'), (bar.next, 'Next match'),
                                     (bar.disclosure, 'Show Replace')):
                    self.assertIsInstance(button, CompactArrowButton)
                    self.assertEqual(button.size(), QSize(23, 24))
                    self.assertEqual(button.accessibleName(), name)
                    self.assertIn(name, button.toolTip())
                QTest.mouseClick(bar.next, Qt.MouseButton.LeftButton, pos=QPoint(1, 22))
                self.assertEqual(bar.feedback.text(), '1 of 3')
                bar.next.setFocus()
                QTest.keyClick(bar.next, Qt.Key.Key_Space)
                self.assertEqual(bar.feedback.text(), '2 of 3')
                QTest.mouseClick(bar.previous, Qt.MouseButton.LeftButton, pos=QPoint(1, 22))
                self.assertEqual(bar.feedback.text(), '1 of 3')
                self.assertEqual(bar.disclosure.arrowType(), Qt.ArrowType.RightArrow)
                QTest.mouseClick(bar.disclosure, Qt.MouseButton.LeftButton, pos=QPoint(1, 22))
                self.assertTrue(bar.replace_row.isVisible())
                self.assertEqual(bar.disclosure.arrowType(), Qt.ArrowType.DownArrow)
                self.assertEqual(bar.disclosure.accessibleName(), 'Hide Replace')
                bar.disclosure.setFocus()
                QTest.keyClick(bar.disclosure, Qt.Key.Key_Space)
                self.assertFalse(bar.replace_row.isVisible())
                self.assertEqual(bar.disclosure.accessibleName(), 'Show Replace')
                bar.query.setFocus()
                QTest.keyClick(bar.query, Qt.Key.Key_Return)
                self.assertEqual(bar.feedback.text(), '2 of 3')
                QTest.keyClick(bar.query, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
                self.assertEqual(bar.feedback.text(), '1 of 3')
                self.assertEqual(tab.editor.toPlainText(), before)
                self.assertEqual(tab.editor.document().availableUndoSteps(), undo)
                bar.query.clear()
                self.assertFalse(bar.next.isEnabled())
                self.assertFalse(bar.previous.isEnabled())
                QTest.mouseClick(bar.next, Qt.MouseButton.LeftButton)
                self.assertEqual(bar.feedback.text(), '')

    def test_artwork_is_centered_and_bounded_in_each_state(self):
        from PySide6.QtCore import Qt
        for style in self.styles:
            tab, bar = self.make_bar(style)
            for expanded in (False, True):
                bar.disclosure.setChecked(expanded)
                for enabled in (True, False):
                    for button in (bar.previous, bar.next, bar.disclosure):
                        with self.subTest(style=style, expanded=expanded, enabled=enabled,
                                          button=button.accessibleName()):
                            button.setEnabled(enabled)
                            bar.query.setFocus()
                            self.app.processEvents()
                            box = button.glyph_rect()
                            self.assertEqual(box.width(), 8)
                            self.assertEqual(box.height(), 8)
                            self.assertEqual(box.center().x(), button.width() / 2)
                            self.assertEqual(box.center().y(), button.height() / 2)
                            image = button.grab().toImage()
                            arrow = button.arrowType()
                            button.setArrowType(Qt.ArrowType.NoArrow)
                            base = button.grab().toImage()
                            button.setArrowType(arrow)
                            scale = image.devicePixelRatio()
                            changed = [(x / scale, y / scale)
                                       for x in range(image.width()) for y in range(image.height())
                                       if image.pixel(x, y) != base.pixel(x, y)]
                            self.assertTrue(changed)
                            for x, y in changed:
                                self.assertGreaterEqual(x, box.left() - 1)
                                self.assertLessEqual(x, box.right() + 1)
                                self.assertGreaterEqual(y, box.top() - 1)
                                self.assertLessEqual(y, box.bottom() + 1)
