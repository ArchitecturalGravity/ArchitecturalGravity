"""Find/replace tab isolation, section styles and reversible Outline expansion."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from AgStudio.shared.lint import analyze
from AgStudio.shared.highlighting import highlight_tokens


class EditingControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import StudioWindow, DocumentTab
        from AgStudio.gui.color_schemes import SchemeStore
        from AgStudio.gui.user_state import UserState
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.window = StudioWindow('current', background=False, user_state=UserState(), scheme_store=SchemeStore(self.directory.name))
        self.tab = self.window._add_tab(DocumentTab('current', 'Cat cat scatter cat\n🌍 café caféine café\n'))
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.addCleanup(self.window.deleteLater)
        self.bar = self.tab.find_bar

    def start(self, query):
        from PySide6.QtGui import QTextCursor
        self.tab.editor.moveCursor(QTextCursor.MoveOperation.Start)
        self.bar.open()
        self.bar.query.setText(query)

    def test_shortcut_case_word_repeat_wrap_and_no_match(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.tab.editor.setFocus()
        QTest.keyClick(self.tab.editor, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.bar.isVisible())
        self.assertTrue(self.bar.query.hasFocus())
        self.start('cat')
        self.bar.case.setChecked(True)
        self.bar.word.setChecked(True)
        self.assertTrue(self.bar.find())
        self.assertEqual(self.tab.editor.textCursor().selectionStart(), 4)
        self.assertTrue(self.bar.find())
        self.assertEqual(self.tab.editor.textCursor().selectionStart(), 16)
        self.assertTrue(self.bar.find())
        self.assertIn('Wrapped', self.bar.feedback.text())
        self.assertEqual(self.tab.editor.textCursor().selectionStart(), 4)
        self.assertTrue(self.bar.find(True))
        self.assertEqual(self.tab.editor.textCursor().selectionStart(), 16)
        self.start('café')
        self.assertTrue(self.bar.find())
        first = self.tab.editor.textCursor().selectionStart()
        self.assertTrue(self.bar.find())
        self.assertGreater(self.tab.editor.textCursor().selectionStart(), first + 10)
        before = self.tab.editor.textCursor()
        self.bar.query.setText('absent')
        self.assertFalse(self.bar.find())
        self.assertEqual(self.bar.feedback.text(), 'No matches')
        self.assertEqual(self.tab.editor.textCursor().selectionStart(), before.selectionStart())
        self.bar.query.clear()
        self.assertFalse(self.bar.replace_all.isEnabled())

    def test_replace_once_all_undo_and_literal_query(self):
        self.start('cat')
        self.bar.word.setChecked(True)
        self.bar.disclosure.click()
        self.assertTrue(self.bar.replace_row.isVisible())
        self.bar.replacement.setText('dog')
        original = self.tab.source
        self.bar.replace_one()  # Find first; no arbitrary selection replacement.
        self.assertEqual(self.tab.source, original)
        self.bar.replace_one()
        self.assertTrue(self.tab.source.startswith('dog cat'))
        self.tab.editor.undo()
        self.assertEqual(self.tab.source, original)
        self.bar.replace_everywhere()
        self.assertEqual(self.bar.feedback.text(), 'Replaced 3 matches')
        self.assertTrue(self.tab.source.startswith('dog dog scatter dog'))
        self.tab.editor.undo()
        self.assertEqual(self.tab.source, original)
        self.tab.editor.redo()
        self.assertTrue(self.tab.source.startswith('dog dog scatter dog'))
        self.tab.editor.selectAll()
        self.tab.editor.insertPlainText('a.b aXb a.b')
        self.start('a.b')
        self.bar.word.setChecked(False)
        self.bar.replacement.setText('a.b!')
        self.bar.replace_everywhere()
        self.assertEqual(self.tab.source, 'a.b! aXb a.b!')
        self.tab.editor.undo()
        self.assertEqual(self.tab.source, 'a.b aXb a.b')

    def test_replacement_unicode_crlf_empty_text_and_case_toggle(self):
        from AgStudio.gui.app import DocumentTab
        from PySide6.QtGui import QTextCursor
        source = 'Cat cat scatter\r\n🌍 café café\r\n'
        tab = self.window._add_tab(DocumentTab('current', source))
        bar = tab.find_bar
        bar.open()
        bar.query.setText('cat')
        bar.case.setChecked(False)
        bar.find()
        self.assertEqual(tab.editor.textCursor().selectionStart(), 0)
        bar.case.setChecked(True)
        tab.editor.moveCursor(QTextCursor.MoveOperation.Start)
        bar.find()
        self.assertEqual(tab.editor.textCursor().selectionStart(), 4)
        bar.word.setChecked(False)
        bar.find()
        self.assertEqual(tab.editor.textCursor().selectionStart(), 9)
        bar.query.setText('café')
        bar.replacement.setText('')
        bar.replace_everywhere()
        self.assertEqual(tab.source, 'Cat cat scatter\r\n🌍  \r\n')
        tab.editor.undo()
        self.assertEqual(tab.source, source)

    def test_tab_isolation_dismiss_reopen_and_stale_selection(self):
        from AgStudio.gui.app import DocumentTab
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.start('cat')
        self.bar.find()
        self.bar.replacement.setText('dog')
        before = self.tab.source
        other = self.window._add_tab(DocumentTab('current', 'cat other'))
        self.bar.replace_one()
        self.bar.replace_everywhere()
        self.assertFalse(self.bar.find())
        self.assertEqual(self.tab.source, before)
        self.assertEqual(other.source, 'cat other')
        other.find_bar.open()
        self.assertEqual(other.find_bar.query.text(), '')
        self.window.tabs.setCurrentWidget(self.tab)
        self.bar.query.setText('different')
        self.bar.replace_one()
        self.assertEqual(self.tab.source, before)
        self.bar.query.setFocus()
        QTest.keyClick(self.bar.query, Qt.Key.Key_Escape)
        self.assertFalse(self.bar.isVisible())
        self.assertTrue(self.tab.editor.hasFocus())
        self.bar.open()
        self.assertTrue(self.bar.isVisible())
        self.assertTrue(self.tab.editor.textCursor().hasSelection())
        self.tab.editor.setReadOnly(True)
        self.bar.query.setText('cat')
        self.bar.replace_everywhere()
        self.assertEqual(self.tab.source, before)

    def test_outline_toggle_partial_refresh_empty_and_tab_state(self):
        from AgStudio.gui.app import DocumentTab
        source = 'Root:\n- Parent:\n  - Child\n\nOther:\n- Item\n'
        self.tab.editor.setPlainText(source)
        self.window._show_side_panel()
        self.tab.ensure_outline()
        button = self.tab.outline_toggle
        parents = lambda: [item for item in self.tab._outline_items.values() if item.childCount()]
        self.assertEqual(button.accessibleName(), 'Expand All')
        self.assertEqual(button.toolTip(), '')
        button.click()
        self.assertTrue(all(item.isExpanded() for item in parents()))
        self.assertEqual(button.accessibleName(), 'Collapse All')
        keys = self.tab._outline_expanded.copy()
        self.tab.refresh_model()
        self.assertEqual(self.tab._outline_expanded, keys)
        self.assertTrue(all(item.isExpanded() for item in parents()))
        parents()[0].setExpanded(False)
        self.assertEqual(button.accessibleName(), 'Expand All')
        button.click()
        button.click()
        self.assertTrue(all(not item.isExpanded() for item in parents()))
        self.assertEqual(button.accessibleName(), 'Expand All')
        other = self.window._add_tab(DocumentTab('current', source))
        other.ensure_outline()
        other.outline_toggle.click()
        self.window.tabs.setCurrentWidget(self.tab)
        self.assertTrue(all(not item.isExpanded() for item in parents()))
        self.tab.editor.setPlainText('')
        self.tab.ensure_outline()
        self.assertFalse(button.isEnabled())
        self.tab.editor.setPlainText('Plain text')
        self.tab.ensure_outline()
        self.assertFalse(button.isEnabled())

    def test_section_role_roundtrip_live_edit_and_legacy_migration(self):
        from AgStudio.gui.color_schemes import default_scheme, validate_scheme
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        old = default_scheme()
        del old['section']
        old['colon']['foreground'] = [1, 2, 3, 255]
        old['editor']['foreground'] = [4, 5, 6, 255]
        migrated = validate_scheme(old)
        for key in old:
            self.assertEqual(migrated[key], old[key])
        self.assertEqual(migrated['section']['foreground'], [4, 5, 6, 255])
        self.window.apply_color_scheme(migrated)
        dialog = ColorSchemeDialog(self.window)
        self.addCleanup(dialog.deleteLater)
        dialog.roles.setCurrentIndex(dialog.roles.findData('section'))
        dialog.controls['foreground'][0].setValue(191)
        self.assertEqual(dialog.working['colon'], old['colon'])
        self.assertTrue(dialog.apply_scheme())
        self.assertEqual(self.window.scheme_store.selected()[1]['section']['foreground'][0], 191)
        self.tab.editor.setPlainText('Task: value')
        self.app.processEvents()
        formats = self.tab.editor.document().firstBlock().layout().formats()
        self.assertTrue(any(f.start == 0 and f.length == 4 and f.format.foreground().color().red() == 191 for f in formats))
        self.assertTrue(any(f.start == 4 and f.length == 1 and f.format.foreground().color().red() == 1 for f in formats))
        path = Path(self.directory.name) / 'Legacy.json'
        path.write_text(json.dumps({'version': 1, 'name': 'Legacy', 'colors': old}))
        before = path.read_bytes()
        self.assertEqual(self.window.scheme_store.load('Legacy'), migrated)
        self.assertEqual(path.read_bytes(), before)


class SectionProjectionTests(unittest.TestCase):
    def test_header_colon_and_content_are_separate_and_literals_opaque(self):
        source = 'Task: value\n- Parent:\n  - Child\nPlain prose x:y\n[Symbol]: value\n"""\nHidden: value\n"""\n'
        tokens = highlight_tokens(analyze(source).document)
        self.assertEqual([(t.span.extract(source), t.role) for t in tokens if t.role in ('section', 'colon')],
                         [('Task', 'section'), (':', 'colon'), (':', 'colon')])
        self.assertFalse(any(t.role == 'section' and t.span.extract(source) in ('value', 'Hidden') for t in tokens))
