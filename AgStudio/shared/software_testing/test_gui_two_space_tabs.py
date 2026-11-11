"""The source editor admits fixed two-space indentation, never literal tabs."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class TwoSpaceTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import SourceEditor
        self.editor = SourceEditor()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def assert_round_trip(self, before, after):
        self.assertEqual(self.editor.toPlainText(), after)
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), before)
        self.editor.redo()
        self.assertEqual(self.editor.toPlainText(), after)

    def test_tab_key_inserts_two_spaces_at_any_column_and_replaces_selection(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtGui import QTextCursor
        for source in ('', 'x', 'xy', '🌍'):
            with self.subTest(source=source):
                self.editor.setPlainText(source)
                self.editor.moveCursor(QTextCursor.MoveOperation.End)
                QTest.keyClick(self.editor, Qt.Key.Key_Tab)
                self.assert_round_trip(source, source + '  ')
        self.editor.setPlainText('replace')
        self.editor.selectAll()
        QTest.keyClick(self.editor, Qt.Key.Key_Tab)
        self.assert_round_trip('replace', '  ')
        self.editor.setReadOnly(True)
        QTest.keyClick(self.editor, Qt.Key.Key_Tab)
        self.assertEqual(self.editor.toPlainText(), '  ')

    def test_load_and_programmatic_insert_normalize_before_undo(self):
        self.editor.setPlainText('\t🌍\tx\t\t')
        self.assertEqual(self.editor.toPlainText(), '  🌍  x    ')
        self.assertFalse(self.editor.document().isUndoAvailable())
        for insert in (self.editor.insertPlainText,
                       lambda text: self.editor.textCursor().insertText(text)):
            self.editor.setPlainText('')
            insert('🌍\tx\t\t\ny\t')
            self.assert_round_trip('', '🌍  x    \ny  ')
        self.editor.setPlainText('first')
        self.editor.appendPlainText('\tlast')
        self.assert_round_trip('first', 'first\n  last')

    def test_direct_document_edits_and_accessibility_cannot_restore_tabs(self):
        from PySide6.QtGui import QTextCursor
        for source in ('', 'original 🌍 text'):
            self.editor.setPlainText(source)
            cursor = QTextCursor(self.editor.document())
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText('🌍\tvalue\n\tend')
            self.assert_round_trip(source, '🌍  value\n  end')
            self.assertEqual(self.editor.source_position(12), (2, 3))
        self.editor.document().setPlainText('🌍\tloaded')
        self.assertEqual(self.editor.toPlainText(), '🌍  loaded')

    def test_native_paste_and_mime_drop_are_single_undo_edits(self):
        from PySide6.QtCore import QMimeData
        data = QMimeData()
        data.setText('🌍\tleft\t\tright\n\tend')
        for insert in (lambda: self.editor.insertFromMimeData(data), self.editor.paste):
            self.editor.setPlainText('old')
            self.editor.selectAll()
            self.app.clipboard().setText(data.text())
            insert()
            self.assert_round_trip('old', '🌍  left    right\n  end')
            self.assertEqual(self.app.clipboard().text(), data.text())

    def test_input_method_commit_normalizes(self):
        from PySide6.QtGui import QInputMethodEvent
        event = QInputMethodEvent()
        event.setCommitString('🌍\tword')
        self.app.sendEvent(self.editor, event)
        self.assert_round_trip('', '🌍  word')

    def test_loaded_tabs_are_dirty_until_explicit_save_and_preserve_encoding_endings(self):
        from AgStudio.gui.app import DocumentTab
        for ending in ('\n', '\r\n', '\r'):
            with self.subTest(ending=repr(ending)), tempfile.TemporaryDirectory() as directory:
                source = '\t🌍\t' + ending + '\t\ttail' + ending
                path = Path(directory) / 'tabs.arc'
                path.write_bytes(source.encode('utf-8-sig'))
                tab = DocumentTab('current', source, path, 'utf-8-sig', background=False)
                try:
                    self.assertTrue(tab.dirty)
                    self.assertTrue(tab.editor.document().isModified())
                    self.assertFalse(tab.editor.document().isUndoAvailable())
                    self.assertEqual(tab.source, source.replace('\t', '  '))
                    self.assertEqual(tab.document.source, tab.source)
                    self.assertEqual(path.read_bytes(), source.encode('utf-8-sig'))
                    tab.editor.insertPlainText('edit\t')
                    tab.editor.undo()
                    self.assertEqual(tab.source, source.replace('\t', '  '))
                    self.assertTrue(tab.dirty)
                    tab.save()
                    self.assertFalse(tab.dirty)
                    self.assertEqual(path.read_bytes(), source.replace('\t', '  ').encode('utf-8-sig'))
                finally:
                    tab.close()
                    tab.deleteLater()

    def test_direct_cursor_edit_keeps_model_and_prior_history_consistent(self):
        from PySide6.QtGui import QTextCursor
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', 'original 🌍', background=False)
        try:
            cursor = tab.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.beginEditBlock()
            cursor.insertText(' first')
            cursor.endEditBlock()
            direct = QTextCursor(tab.editor.document())
            direct.movePosition(QTextCursor.MoveOperation.End)
            direct.beginEditBlock()
            direct.insertText('\tsecond')
            direct.endEditBlock()
            self.assertEqual(tab.source, 'original 🌍 first  second')
            self.assertEqual(tab.document.source, tab.source)
            tab.editor.undo()
            self.assertEqual(tab.source, 'original 🌍 first')
            tab.editor.undo()
            self.assertEqual(tab.source, 'original 🌍')
            self.assertFalse(tab.dirty)
            tab.editor.redo()
            tab.editor.redo()
            self.assertEqual(tab.source, 'original 🌍 first  second')
            self.assertEqual(tab.document.source, tab.source)
        finally:
            tab.close()
            tab.deleteLater()

    def test_replace_all_normalizes_and_undo_restores_source(self):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.user_state import UserState
        window = StudioWindow('current', user_state=UserState(), background=False)
        tab = window.current()
        try:
            tab.editor.insertPlainText('word word')
            bar = tab.find_bar
            bar.query.setText('word')
            bar.replacement.setText('a\tb')
            bar.replace_everywhere()
            self.assertEqual(tab.source, 'a  b a  b')
            tab.editor.undo()
            self.assertEqual(tab.source, 'word word')
            tab.editor.redo()
            self.assertEqual(tab.source, 'a  b a  b')
        finally:
            tab.dirty = False
            window.close()
            window.deleteLater()
