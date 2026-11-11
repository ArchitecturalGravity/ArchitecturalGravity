"""Marker extents and independent color controls, with exact source shielding."""
from copy import deepcopy
import tempfile
import unittest
from AgStudio.shared import LanguageCore
from AgStudio.shared.lint import analyze
from AgStudio.shared.highlighting import highlight_tokens
from AgStudio.gui.color_schemes import default_scheme, validate_scheme, SchemeStore


class MarkerRoleTests(unittest.TestCase):
    def documents(self, source):
        return (analyze(source).document,
                LanguageCore.parse_document(LanguageCore.open_source(source, arcgrav_version='current')))

    def test_list_markers_exclude_all_separator_whitespace(self):
        source = '- 🌍 bullet\r\n12. number\r\nP12. priority\r\n  - child\r\n'
        for document in self.documents(source):
            tokens = [t for t in highlight_tokens(document) if t.role in {'bullet', 'sequence', 'priority'}]
            self.assertEqual([t.span.extract(source) for t in tokens], ['-', '12.', 'P12.', '-'])
            for token in tokens:
                self.assertEqual(source[token.span.end], ' ')
                self.assertFalse(token.span.extract(source).endswith(' '))

    def test_operation_binder_roles_and_shielding(self):
        source = '=> Work 🌍 ↳\r\n  - Child\r\nText: "=> ↳"\r\n"""\r\n=> Work ↳\r\n"""\r\n'
        for document in self.documents(source):
            tokens = [t for t in highlight_tokens(document) if t.role in {'operation', 'binder'}]
            self.assertEqual([(t.span.extract(source), t.role) for t in tokens], [('=>', 'operation'), ('↳', 'binder')])

    def test_colon_wildcard_and_quoted_literal_exclusions(self):
        source = 'Scope: 🌍 file*; prose\r\nText: "* : => ↳"\r\nOther: `* : => ↳`\r\n"""\r\nScope: * => ↳\r\n"""\r\n'
        for document in self.documents(source):
            active = [(t.span.extract(source), t.role) for t in highlight_tokens(document)
                      if t.role in {'colon', 'wildcard', 'operation', 'binder'}]
            self.assertEqual(active, [(':', 'colon'), ('*', 'wildcard'), (':', 'colon'), (':', 'colon')])
            self.assertFalse(any(t.span.extract(source) == ';' for t in highlight_tokens(document)))

    def test_legacy_shared_style_migration_and_roundtrip(self):
        colors = default_scheme()
        old = deepcopy(colors)
        old['marker'] = {'foreground': [11, 22, 33, 44], 'background': [55, 66, 77, 88]}
        for role in ('colon', 'wildcard', 'binder'):
            del old[role]
        old['operation'] = {'foreground': [1, 2, 3, 4], 'background': [5, 6, 7, 8]}
        migrated = validate_scheme(old)
        for role in ('colon', 'wildcard'):
            self.assertEqual(migrated[role], old['marker'])
        self.assertEqual(migrated['binder'], old['operation'])
        migrated['binder']['foreground'][0] = 99
        self.assertEqual(migrated['operation'], old['operation'])
        self.assertNotIn('binder', old)
        with tempfile.TemporaryDirectory() as directory:
            store = SchemeStore(directory)
            store.save('Split colors', migrated)
            self.assertEqual(store.load('Split colors'), migrated)


class MarkerRoleGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_marker_background_stops_before_separator_in_qt(self):
        from AgStudio.gui.app import DocumentTab
        source = '- 🌍 bullet\r\n12. number\r\nP12. priority\r\n'
        tab = DocumentTab('current', source)
        try:
            colors = default_scheme()
            for role in ('bullet', 'sequence', 'priority'):
                colors[role]['background'] = [10, 20, 30, 255]
            tab.highlighter.apply_color_scheme(colors)
            self.app.processEvents()
            block = tab.editor.document().firstBlock()
            for length in (1, 3, 4):
                formats = block.layout().formats()
                self.assertTrue(any(f.start == 0 and f.length == length for f in formats))
                self.assertFalse(any(f.start <= length < f.start + f.length for f in formats))
                block = block.next()
            self.assertEqual(tab.source, source)
        finally:
            tab.deleteLater()

    def test_split_roles_have_independent_editable_controls(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        with tempfile.TemporaryDirectory() as directory:
            window = StudioWindow('current', user_state=UserState(), background=False, scheme_store=SchemeStore(directory))
            dialog = ColorSchemeDialog(window)
            try:
                for original_role, edited_role in (('operation', 'binder'), ('colon', 'wildcard')):
                    original = deepcopy(dialog.working[original_role])
                    dialog.roles.setCurrentIndex(dialog.roles.findData(edited_role))
                    self.assertEqual(dialog.roles.currentData(), edited_role)
                    dialog.controls['foreground'][0].setValue(17)
                    dialog.controls['background'][3].setValue(119)
                    self.assertEqual(dialog.working[edited_role]['foreground'][0], 17)
                    self.assertEqual(dialog.working[edited_role]['background'][3], 119)
                    self.assertEqual(dialog.working[original_role], original)
                self.assertTrue(dialog.apply_scheme())
                self.assertEqual(window.scheme_store.selected()[1], dialog.working)
            finally:
                dialog.deleteLater()
                window.deleteLater()
