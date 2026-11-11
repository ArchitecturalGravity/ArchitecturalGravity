"""Canonical physical lines must not be confused with Qt paragraph blocks."""
import importlib.util
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class SourceCoordinateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_unicode_separator_gutter_rows_and_exact_finding_positions(self):
        from AgStudio.gui.app import DocumentTab
        from AgStudio.shared.software_testing.test_lint_parent_binding import ANNOTATED
        tab = DocumentTab('current', ANNOTATED)
        try:
            tab.show()
            self.app.processEvents()
            block = tab.editor.document().findBlockByNumber(3)
            rows = list(tab.editor.gutter_rows(block))
            self.assertEqual([row[0] for row in rows], [4, 5])
            self.assertGreater(rows[1][1], rows[0][1])
            self.assertEqual(tab.editor.finding_lines, {1, 5, 10})
            self.assertEqual(list(tab.editor.gutter_rows(block.next()))[0][0], 6)
            for expected in ((1, 1), (5, 27), (10, 1)):
                row = next(tab.diagnostic_list.topLevelItem(i)
                           for i in range(tab.diagnostic_list.topLevelItemCount())
                           if (int(tab.diagnostic_list.topLevelItem(i).text(3)),
                               int(tab.diagnostic_list.topLevelItem(i).text(4))) == expected)
                tab._navigate_finding(row)
                cursor = tab.editor.textCursor()
                self.assertEqual(tab.editor.source_position(cursor.selectionStart()), expected)
                self.assertIn(expected[0], [row[0] for row in tab.editor.gutter_rows(cursor.block())])
            self.assertEqual(tab.source, ANNOTATED)
        finally:
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_codepoint_columns_crlf_and_repeated_edits(self):
        from AgStudio.gui.app import SourceEditor, _display_offset
        editor = SourceEditor()
        try:
            for source in ('A\r\n🌍B\u2028C\n', 'A\n🌍B\u2028C\n', '', 'One\nTwo\n'):
                editor.setPlainText(source)
                starts = [0]
                offset = 0
                for line in source.splitlines(keepends=True):
                    offset += len(line)
                    if line.endswith(('\n', '\u2028')):
                        starts.append(offset)
                for line, start in enumerate(starts, 1):
                    self.assertEqual(editor.source_position(_display_offset(source, start)), (line, 1))
                if 'B' in source:
                    self.assertEqual(editor.source_position(_display_offset(source, source.index('B'))), (2, 2))
        finally:
            editor.close()
            editor.deleteLater()
            self.app.processEvents()

    def test_window_status_uses_physical_line_and_codepoint_column(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow, _display_offset
        from PySide6.QtWidgets import QMessageBox
        from unittest.mock import patch
        window = StudioWindow('current', user_state=UserState(), background=False)
        try:
            tab = window.current()
            source = 'Header:\u2028🌍Text\n'
            tab.editor.setPlainText(source)
            cursor = tab.editor.textCursor()
            cursor.setPosition(_display_offset(source, source.index('Text')))
            tab.editor.setTextCursor(cursor)
            window._update_status()
            self.assertIn('Ln 2, Col 2', window.statusBar().currentMessage())
        finally:
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
                window.close()
            window.deleteLater()
            self.app.processEvents()
