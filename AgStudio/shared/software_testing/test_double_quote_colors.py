"""Inline textual values have separate delimiter/content presentation roles."""
from copy import deepcopy
import unittest
from AgStudio.shared import LanguageCore
from AgStudio.shared.lint import analyze
from AgStudio.shared.highlighting import highlight_tokens
from AgStudio.gui.color_schemes import default_scheme, validate_scheme, SchemeStore


def models(source):
    yield analyze(source).document
    yield LanguageCore.parse_document(LanguageCore.open_source(source, arcgrav_version='current'))


class DoubleQuoteTests(unittest.TestCase):
    def test_exact_text_and_shielding_in_both_projections(self):
        source = '[A]: value\r\n\r\nTask:\r\n=> Set `status` to "🌍 [A] * => AS [B] ↳" and use [A]\r\n'
        for document in models(source):
            tokens = highlight_tokens(document)
            quotes = [t for t in tokens if t.role.startswith('double_quote')]
            self.assertEqual([(t.role, t.span.extract(source)) for t in quotes],
                             [('double_quote', '"'), ('double_quote_content', '🌍 [A] * => AS [B] ↳'), ('double_quote', '"')])
            content = quotes[1].span
            self.assertFalse(any(content.start <= t.span.start < content.end and t.role != 'double_quote_content' for t in tokens))
        result = analyze(source)
        self.assertEqual(len([r for r in result.semantics.resolutions if r.reference.name == 'A']), 1)
        self.assertFalse(any(r.reference.name == 'B' for r in result.semantics.resolutions))

    def test_empty_unclosed_backslash_recovery_and_triple_quote_distinction(self):
        cases = [('""', [('double_quote', '"'), ('double_quote', '"')]),
                 ('"unfinished', [('double_quote', '"'), ('double_quote_content', 'unfinished')]),
                 ('"a\\"b"', [('double_quote', '"'), ('double_quote_content', 'a\\"b'), ('double_quote', '"')]),
                 ('"a\\"', [('double_quote', '"'), ('double_quote_content', 'a\\"')]),
                 ('"a\\\\"', [('double_quote', '"'), ('double_quote_content', 'a\\\\'), ('double_quote', '"')])]
        for text, expected in cases:
            source = '- ' + text + '\r\n=> Next\r\n'
            for document in models(source):
                with self.subTest(text=text, canonical=hasattr(document, 'syntax')):
                    tokens = highlight_tokens(document)
                    self.assertEqual([(t.role, t.span.extract(source)) for t in tokens if t.role.startswith('double_quote')], expected)
                    self.assertTrue(any(t.role == 'operation' and t.span.start == source.index('=>') for t in tokens))
        for document in models('"""\n"[A] * =>"\n"""\n'):
            self.assertEqual([t.role for t in highlight_tokens(document)], ['delimiter', 'literal', 'delimiter'])
        for document in models('- """opaque [A]"""\n'):
            self.assertFalse(any(t.role.startswith('double_quote') for t in highlight_tokens(document)))

    def test_migration_copies_literal_without_aliasing_or_replacing_new_roles(self):
        scheme = default_scheme()
        old = deepcopy(scheme)
        for role in ('double_quote', 'double_quote_content'):
            del old[role]
        old['literal'] = {'foreground': [12, 34, 56, 78], 'background': [87, 65, 43, 21]}
        migrated = validate_scheme(old)
        for key, value in old.items():
            self.assertEqual(migrated[key], value)
        for role in ('double_quote', 'double_quote_content'):
            self.assertEqual(migrated[role], old['literal'])
        migrated['double_quote']['foreground'][0] = 111
        self.assertEqual(migrated['double_quote_content'], old['literal'])
        self.assertEqual(validate_scheme(migrated), migrated)
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            store = SchemeStore(directory)
            store.save('Quotes', migrated)
            self.assertEqual(store.load('Quotes'), migrated)

    def test_gui_independent_controls_preview_cancel_and_weights(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow, DocumentTab
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        import tempfile
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            window = StudioWindow('current', user_state=UserState(), background=False, scheme_store=SchemeStore(directory))
            dialog = ColorSchemeDialog(window)
            try:
                original = deepcopy(window.color_scheme)
                for role, red in [('double_quote', 23), ('double_quote_content', 177)]:
                    dialog.roles.setCurrentIndex(dialog.roles.findData(role))
                    self.assertTrue(dialog.controls['foreground'][0].isEnabled())
                    dialog.controls['foreground'][0].setValue(red)
                    self.assertEqual(window.color_scheme[role]['foreground'][0], red)
                self.assertIn('"complete"', dialog.preview.toPlainText())
                tab = DocumentTab('current', '- "🌍 value"\r\n')
                try:
                    tab.highlighter.apply_color_scheme(window.color_scheme)
                    self.assertEqual(tab.highlighter._formats['double_quote'].fontWeight(), QFont.Weight.Bold)
                    self.assertEqual(tab.highlighter._formats['double_quote_content'].fontWeight(), QFont.Weight.Normal)
                    self.assertEqual(tab.highlighter._formats['double_quote_content'].foreground().color().red(), 177)
                    self.assertEqual([role for _, _, role in tab.highlighter.ranges if role.startswith('double_quote')],
                                     ['double_quote', 'double_quote_content', 'double_quote'])
                finally:
                    tab.close()
                    tab.deleteLater()
                dialog.reject()
                self.assertEqual(window.color_scheme, original)
            finally:
                dialog.deleteLater()
                window.deleteLater()
                app.processEvents()
