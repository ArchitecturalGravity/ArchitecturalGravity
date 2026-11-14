"""The permanent status counter reports code points in the active exact source."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class CharacterCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.user_state import UserState
        self.window = StudioWindow('current', user_state=UserState(), background=False)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def assertCount(self, count):
        self.assertEqual(self.window.char_count_label.text(), f'Char Count: {count}')

    def test_empty_edits_undo_redo_and_unicode(self):
        editor = self.window.current().editor
        self.assertCount(0)
        editor.insertPlainText('A🌍e\u0301\n')
        self.assertCount(5)
        editor.undo()
        self.assertCount(0)
        editor.redo()
        self.assertCount(5)
        editor.selectAll()
        editor.insertPlainText('Z')
        self.assertCount(1)
        editor.selectAll()
        editor.textCursor().removeSelectedText()
        self.assertCount(0)

    def test_open_tabs_line_endings_and_close(self):
        with tempfile.TemporaryDirectory() as folder:
            lf = Path(folder) / 'lf.arc'
            crlf = Path(folder) / 'crlf.arc'
            lf.write_bytes('A\n🌍'.encode())
            crlf.write_bytes('A\r\n🌍'.encode('utf-8-sig'))
            first = self.window.open_file(lf)
            self.assertCount(3)
            second = self.window.open_file(crlf)
            self.assertCount(4)
            self.window.tabs.setCurrentWidget(first)
            self.assertCount(3)
            # A background-tab edit must not replace the active document's count.
            second.editor.insertPlainText('B')
            self.assertCount(3)
            self.window._close_tab(self.window.tabs.indexOf(first))
            self.assertEqual(self.window.char_count_label.text(),
                             f'Char Count: {len(self.window.current().source)}')
            self.window.new_document()
            self.assertCount(0)

    def test_permanent_right_alignment_and_transient_message(self):
        from PySide6.QtCore import Qt
        self.window.show()
        self.window.current().editor.insertPlainText('abc')
        self.app.processEvents()
        label = self.window.char_count_label
        self.assertTrue(label.alignment() & Qt.AlignmentFlag.AlignRight)
        self.assertTrue(label.isVisible())
        self.window.statusBar().showMessage('Temporary status', 10000)
        self.app.processEvents()
        self.assertEqual(self.window.statusBar().currentMessage(), 'Temporary status')
        self.assertCount(3)
        self.assertTrue(label.isVisible())
        self.assertGreater(label.geometry().center().x(), self.window.statusBar().width() // 2)

    def test_counter_matches_status_bar_typography_and_palette(self):
        from PySide6.QtGui import QPalette
        self.window.show()
        self.app.processEvents()
        bar = self.window.statusBar()
        label = self.window.char_count_label
        self.assertEqual(label.font(), bar.font())
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Window):
            self.assertEqual(label.palette().color(role), bar.palette().color(role))
        self.assertEqual(label.margin(), 0)
        self.assertEqual(label.indent(), -1)
        self.assertEqual(label.frameWidth(), 0)
        margins = label.contentsMargins()
        self.assertEqual((margins.left(), margins.top(), margins.right(), margins.bottom()),
                         (0, 0, 7, 0))
