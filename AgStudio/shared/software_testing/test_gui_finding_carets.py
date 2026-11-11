"""Scoped sort-arrow placement and bounded disclosure artwork across Qt styles."""
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class FindingCaretTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtWidgets import QStyleFactory
        self.styles = [style for style in ('Fusion', 'Windows', 'windowsvista', 'Windows11')
                       if style.casefold() in {name.casefold() for name in QStyleFactory.keys()}]
        self.original_style = self.app.style().objectName()
        self.windows = []
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            for window in self.windows:
                window.close()
                window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.setStyle(self.original_style)
        self.app.processEvents()
        self.directory.cleanup()

    def window(self, style):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.color_schemes import SchemeStore
        self.app.setStyle(style)
        window = StudioWindow('current', background=False, user_state=UserState(),
                              scheme_store=SchemeStore(self.directory.name))
        self.windows.append(window)
        window.resize(1200, 800)
        window.show()
        window._show_diagnostics()
        tab = window.current()
        if tab.diagnostic_list.isHidden():
            tab._toggle_diagnostics()
        self.settle()
        return window

    def settle(self):
        for _ in range(3):
            self.app.processEvents()

    def test_sort_arrow_is_right_center_without_switching_application_style(self):
        from PySide6.QtCore import QPoint, QRect, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QStyle, QStyleOptionHeader
        from AgStudio.gui.app import STUDIO_STYLE
        for style in self.styles:
            window = self.window(style)
            tab = window.current()
            header = tab.diagnostic_list.header()
            self.assertEqual(header._finding_style.objectName().casefold(), 'fusion')
            self.assertIs(header._finding_style.parent(), header)
            self.assertEqual(self.app.style().objectName().casefold(), style.casefold())
            for size in (14, 18):
                window.setStyleSheet(STUDIO_STYLE + f'\nQWidget {{ font-size: {size}px; }}')
                self.settle()
                for column in range(5):
                    for _ in range(2):
                        with self.subTest(style=style, size=size, column=column):
                            old_column, old_order = header.sortIndicatorSection(), header.sortIndicatorOrder()
                            point = QPoint(header.sectionViewportPosition(column) + header.sectionSize(column) // 2,
                                           header.height() // 2)
                            QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=point)
                            self.settle()
                            self.assertEqual(header.sortIndicatorSection(), column)
                            if old_column == column:
                                self.assertNotEqual(header.sortIndicatorOrder(), old_order)
                            option = QStyleOptionHeader()
                            header.initStyleOption(option)
                            header.initStyleOptionForIndex(option, column)
                            option.rect = QRect(header.sectionViewportPosition(column), 0,
                                                header.sectionSize(column), header.height())
                            arrow = header.style().subElementRect(QStyle.SubElement.SE_HeaderArrow, option, header)
                            label = header.style().subElementRect(QStyle.SubElement.SE_HeaderLabel, option, header)
                            self.assertTrue(option.rect.contains(arrow))
                            self.assertGreater(arrow.center().x(), option.rect.center().x())
                            self.assertLessEqual(abs(arrow.center().y() - option.rect.center().y()), 2)
                            self.assertLessEqual(label.left() + header.fontMetrics().horizontalAdvance(option.text),
                                                 arrow.left() - 2)
                            self.assertEqual(header.style().styleHint(QStyle.StyleHint.SH_Header_ArrowAlignment,
                                                                     option, header),
                                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            self.assertEqual(self.app.style().objectName().casefold(), style.casefold())

    def test_disclosure_glyph_stays_small_but_edge_click_and_keyboard_toggle(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        for style in self.styles:
            with self.subTest(style=style):
                window = self.window(style)
                tab = window.current()
                button = tab.diagnostics_toggle
                tab.editor.insertPlainText('Task: preserve unsaved work\n')
                snapshot = (tab.source, tab.dirty, tab.editor.document().availableUndoSteps())
                self.assertEqual(button.width(), 20)
                self.assertGreaterEqual(button.height(), 20)
                self.assertEqual(button.arrowType(), Qt.ArrowType.DownArrow)
                for _ in range(3):
                    # Click well outside the 8-pixel artwork, still inside its native hit target.
                    QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(1, button.height() - 2))
                    self.settle()
                    self.assertTrue(tab.diagnostic_list.isHidden())
                    self.assertEqual(button.arrowType(), Qt.ArrowType.UpArrow)
                    self.assertEqual(button.accessibleName(), 'Expand Finding List')
                    self.assertEqual(button.toolTip(), button.accessibleName())
                    self.assert_bounded_glyph(tab)
                    button.setFocus()
                    QTest.keyClick(button, Qt.Key.Key_Space)
                    self.settle()
                    self.assertFalse(tab.diagnostic_list.isHidden())
                    self.assertEqual(button.arrowType(), Qt.ArrowType.DownArrow)
                    self.assertEqual(button.accessibleName(), 'Collapse Finding List')
                    self.assert_bounded_glyph(tab)
                button.setEnabled(False)
                QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(1, button.height() - 2))
                self.assertFalse(tab.diagnostic_list.isHidden())
                button.setEnabled(True)
                self.assertEqual((tab.source, tab.dirty, tab.editor.document().availableUndoSteps()), snapshot)

    def assert_bounded_glyph(self, tab):
        button = tab.diagnostics_toggle
        button.clearFocus()
        tab.editor.setFocus()
        self.settle()
        box = button.glyph_rect()
        self.assertLessEqual(box.width(), 8)
        self.assertLessEqual(box.height(), 8)
        self.assertEqual(box.center().x(), button.width() / 2)
        self.assertEqual(box.center().y(), button.height() / 2)
        image = button.grab().toImage()
        scale = image.devicePixelRatio()
        points = [(x / scale, y / scale) for x in range(image.width()) for y in range(image.height())
                  if max(image.pixelColor(x, y).getRgb()[:3]) < 110]
        self.assertTrue(points)
        for x, y in points:
            self.assertGreaterEqual(x, box.left() - 1)
            self.assertLessEqual(x, box.right() + 1)
            self.assertGreaterEqual(y, box.top() - 1)
            self.assertLessEqual(y, box.bottom() + 1)
