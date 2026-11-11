"""Regression tests for backtick palettes and explicit editor requirements."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission
from AgStudio.shared.highlighting import highlight_tokens
from AgStudio.gui.color_schemes import SchemeStore, default_scheme, validate_scheme

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
NEW = {'AG-LINE-ENDING', 'AG-BINDING-SPACING', 'AG-TRAILING-WHITESPACE', 'AG-SYMBOL-ORPHAN'}


class EditorRequirementsTests(unittest.TestCase):
    def test_precise_errors_and_admission(self):
        cases = {
            'AG-LINE-ENDING': ('Task:\r\n- Finish!\r\n', '!'),
            'AG-BINDING-SPACING': ('[Symbol]: Value\n=> Use [Symbol]  ↳\n  - Child', '  ↳'),
            'AG-TRAILING-WHITESPACE': ('- 🌍 Done \t\r\n', ' \t'),
            'AG-SYMBOL-ORPHAN': ('[Symbol]:\n\nTask: Work', '[Symbol]'),
        }
        for id, (source, expected) in cases.items():
            with self.subTest(id=id):
                a = analyze(source)
                f = next(f for f in a.diagnostics.findings if f.rule_id == id)
                self.assertEqual((f.severity), ('error'))
                self.assertEqual(f.source_range.span.extract(source), expected)
                node = next(n for n in a.tree.nodes if n.span.start <= f.source_range.span.start < n.span.end)
                candidate = Candidate(id, f.source_range.span, node.id, 'untrusted', REGISTRY[id].required_evidence)
                self.assertEqual(admission(candidate, a.document, a.tree, a.semantics), ())
                self.assertTrue(admission(replace(candidate, evidence=()), a.document, a.tree, a.semantics))
                self.assertEqual(analyze(source, arcgrav_version='future').diagnostics.findings, ())

    def test_valid_punctuation_endings_and_literal_preservation(self):
        for source in ['[A]: value\n=> Use [A]', 'Scope:\n- src/*', '- "Hello World!"',
                       '- `key!`', '- https://example.com/', '- C:\\project\\',
                       '- ./folder/', '[State]: []', '[State]: {}', '- Keep (this)',
                       '- run();', '- 🌍', '[A]: value\n=> Use [A] ↳\n  - Child',
                       '"""\nText.  \n[A]↳\n2. \n"""', '- "exact  "', '- `exact  `']:
            with self.subTest(source=source):
                self.assertFalse(NEW & {f.rule_id for f in analyze(source).diagnostics.findings})

    def test_invalid_endings_and_all_physical_line_endings(self):
        for marker in ['.', ',', ';', '!', '?', '…', '+', '=', ')', ']', '}']:
            for ending in ['\n', '\r\n', '\r', '\u2028', '']:
                with self.subTest(marker=marker, ending=ending):
                    self.assertIn('AG-LINE-ENDING', {f.rule_id for f in analyze('- Done' + marker + ending).diagnostics.findings})

    def test_binder_requires_exactly_one_ascii_space(self):
        for separator in ['', '  ', '\t', ' \t', '\u00a0']:
            source = '[A]: Value\n=> Use [A]' + separator + '↳\n  - Child'
            self.assertIn('AG-BINDING-SPACING', {f.rule_id for f in analyze(source).diagnostics.findings})
        for source in ['=> Use [A] ↳\n  - Child', '- "[A]↳"', '- `[A]↳`']:
            self.assertNotIn('AG-BINDING-SPACING', {f.rule_id for f in analyze(source).diagnostics.findings})

    def test_trailing_whitespace_and_empty_items(self):
        for source in ['- Done ', '- Done\t', '   ', '- Done\u00a0', '"""  \nx\n"""']:
            self.assertIn('AG-TRAILING-WHITESPACE', {f.rule_id for f in analyze(source).diagnostics.findings})
        source = '[Symbol]:\n1. Something\n2. \n3. Instruction'
        findings = tuple(f for f in analyze(source).diagnostics.findings if f.severity == 'error')
        self.assertEqual({f.rule_id for f in findings}, {'AG-LIST-EMPTY', 'AG-TRAILING-WHITESPACE', 'AG-SYMBOL-UNUSED'})
        self.assertTrue(all(f.severity == 'error' for f in findings))
        self.assertEqual(next(f for f in findings if f.rule_id == 'AG-LIST-EMPTY').source_range.span.extract(source), '2.')
        for source in ['[A]:', '[A]:\n1.\n', '- [A]:']:
            self.assertIn('AG-SYMBOL-ORPHAN', {f.rule_id for f in analyze(source).diagnostics.findings})
        for source in ['[A]', '[A]:\n1. Content', '[A]:\n"""\n\n"""', '[A]: value',
                       '[A]:\n  - Child', '[A]:\n[Broken']:
            self.assertNotIn('AG-SYMBOL-ORPHAN', {f.rule_id for f in analyze(source).diagnostics.findings})

    def test_backticks_shield_language_and_preserve_exact_ranges(self):
        source = '- 🌍 `a [B] AS [C] ↳ *`'
        a = analyze(source)
        self.assertFalse(a.semantics.symbols)
        self.assertEqual([t.role for t in highlight_tokens(a.document)], ['bullet', 'backtick', 'backtick_content', 'backtick'])
        self.assertEqual([t.span.extract(source) for t in highlight_tokens(a.document)][1:], ['`', 'a [B] AS [C] ↳ *', '`'])
        self.assertEqual([f.rule_id for f in a.diagnostics.findings], ['AG-DOCUMENT-END-SECTION', 'AG-DOCUMENT-START-SECTION', 'AG-BACKTICK-WHITESPACE'])
        for source in ['"""\n`inside`\n"""', '- "`inside`"', '- ``inside``', r'- \`inside\`']:
            self.assertFalse([t for t in highlight_tokens(analyze(source).document) if t.role == 'backtick'])

    def test_legacy_palette_migration_and_roundtrip(self):
        old = {k: v for k,v in default_scheme().items() if k not in {'backtick', 'backtick_content'}}
        old['symbol']['foreground'] = [1, 2, 3, 255]
        upgraded = validate_scheme(old)
        self.assertEqual(upgraded['symbol'], old['symbol'])
        self.assertEqual(upgraded['backtick']['foreground'], default_scheme()['backtick']['foreground'])
        self.assertEqual(upgraded['backtick_content']['foreground'], default_scheme()['backtick_content']['foreground'])
        self.assertNotIn('backtick', old)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'selected.json'
            data = json.dumps({'version': 1, 'name': 'Old', 'colors': old})
            path.write_text(data)
            store = SchemeStore(directory)
            self.assertEqual(store.selected(), ('Old', upgraded, None))
            self.assertEqual(path.read_text(), data)
            upgraded['backtick']['foreground'] = [3, 4, 5, 255]
            upgraded['backtick_content']['foreground'] = [6, 7, 8, 255]
            store.save('New', upgraded)
            self.assertEqual(store.load('New'), upgraded)
            store.select('New', upgraded)
            self.assertEqual(store.selected()[1], upgraded)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class BacktickGuiTests(unittest.TestCase):
    def test_editable_roles_formats_and_utf16_positions(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            window = StudioWindow('current', user_state=UserState(), background=False, scheme_store=SchemeStore(directory))
            try:
                tab = window.current()
                tab.editor.setPlainText('🌍 `message`')
                dialog = ColorSchemeDialog(window)
                try:
                    for role, color in [('backtick', default_scheme()['backtick']['foreground']), ('backtick_content', default_scheme()['backtick_content']['foreground'])]:
                        self.assertGreaterEqual(dialog.roles.findData(role), 0)
                        self.assertEqual(list(tab.highlighter._formats[role].foreground().color().getRgb()), color)
                    self.assertTrue(any(role == 'backtick_content' for _, _, role in dialog.highlighter.ranges))
                    self.assertEqual(tab.highlighter._formats['backtick'].fontWeight(), QFont.Weight.Bold)
                    self.assertEqual(tab.highlighter._formats['backtick_content'].fontWeight(), QFont.Weight.Normal)
                    self.assertEqual(tab.highlighter.ranges, ((3,4,'backtick'), (4,11,'backtick_content'), (11,12,'backtick')))
                    dialog.roles.setCurrentIndex(dialog.roles.findData('backtick_content'))
                    dialog.controls['foreground'][0].setValue(125)
                    self.assertEqual(tab.highlighter._formats['backtick_content'].foreground().color().red(), 125)
                    self.assertEqual(tab.highlighter._formats['backtick'].foreground().color().red(), default_scheme()['backtick']['foreground'][0])
                    dialog.reject()
                    self.assertEqual(tab.source, '🌍 `message`')
                finally:
                    dialog.deleteLater()
            finally:
                window.deleteLater()
