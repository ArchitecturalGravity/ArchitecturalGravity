"""Map object selection shares Outline's source-exact navigation."""
import unittest
from unittest.mock import patch
from . import test_gui_inference_map as inference_tests


class MapNavigationTests(unittest.TestCase):
    setUpClass = classmethod(inference_tests.InferenceMapTests.setUpClass.__func__)
    make_tab = inference_tests.InferenceMapTests.make_tab
    settle = inference_tests.InferenceMapTests.settle
    point = inference_tests.InferenceMapTests.point

    def click_row(self, tab, index):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        view = tab.document_map
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=self.point(view, view.rows[index]))
        self.app.processEvents()

    def test_selection_matches_outline_all_modes_and_edit(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        from AgStudio.gui.app import _display_offset
        source = '[A]:\r\n- alpha 😀\r\n\r\n[B]:\r\n  Detail:\r\n    - use [A]\r\n'
        for mode in MODE_LABELS:
            for edit in (False, True):
                with self.subTest(mode=mode, edit=edit):
                    tab = self.make_tab(source, inference_mode=mode)
                    if edit:
                        tab.map_title.click()
                        tab.document_map.rebuild()
                    tab.editor.setFocus()
                    self.click_row(tab, 4)  # Nested body belongs to whole object B.
                    self.assertEqual(tab.editor.textCursor().position(), _display_offset(source, source.index('[B]')))
                    self.assertEqual(tab.outline.currentItem().text(0), '[B]:')
                    self.assertFalse(tab.correlations_panel.isHidden())
                    self.assertEqual(tab.source, source)
                    self.assertFalse(tab.editor.document().isModified())
                    self.assertFalse(tab.editor.document().isUndoAvailable())
                    if edit:
                        self.assertTrue(tab.document_map.hasFocus())
                    else:
                        self.assertTrue(tab.editor.hasFocus())
                    self.click_row(tab, 1)
                    self.assertEqual(tab.outline.currentItem().text(0), '[A]:')

    def test_repeated_selection_recenters_with_hidden_outline(self):
        source = '[A]:\n- alpha\n' + '\n' * 80 + '[B]:\n- beta\n' + '\n' * 80
        tab = self.make_tab(source)
        self.assertTrue(tab.side_panel.isHidden())
        for _ in range(2):
            tab.editor.verticalScrollBar().setValue(0)
            self.click_row(tab, 2)
            self.assertEqual(tab.editor.source_position(tab.editor.textCursor().position())[0], 83)
            self.assertLess(abs(tab.editor.cursorRect().center().y() - tab.editor.viewport().height() / 2), 30)
            self.assertTrue(tab.side_panel.isHidden())

    def test_blank_right_click_and_stale_pixels_do_not_navigate(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        tab = self.make_tab('[A]:\n- alpha\n[B]:\n- beta\n')
        view = tab.document_map
        before = tab.editor.textCursor().position()
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=QPoint(view.width() - 1, view.height() - 1))
        QTest.mouseClick(view, Qt.MouseButton.RightButton, pos=self.point(view, view.rows[2]))
        self.assertEqual(tab.editor.textCursor().position(), before)
        point = self.point(view, view.rows[2])
        old_document = view._document
        old_span = view._tree.nodes[view.rows[2].owner].span
        tab.editor.insertPlainText('changed ')
        before = tab.editor.textCursor().position()
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=point)
        tab._map_object_selected(old_document, old_span)
        self.assertEqual(tab.editor.textCursor().position(), before)

    def test_drag_and_escape_do_not_navigate(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        tab = self.make_tab('[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- gamma\n')
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        with patch.object(tab, '_outline_clicked') as navigate:
            start = self.point(view, view.rows[2])
            QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(view, start + QPoint(0, 25))
            QTest.keyClick(view, Qt.Key.Key_Escape)
            QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=start)
            navigate.assert_not_called()
        self.click_row(tab, 2)
        self.assertEqual(tab.outline.currentItem().text(0), '[B]:')
