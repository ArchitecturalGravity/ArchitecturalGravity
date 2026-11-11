"""First-run example, file-backed Default palette, and backtick-error regression coverage."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from AgStudio.gui.color_schemes import default_scheme, SchemeStore
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, admission
from AgStudio.shared.highlighting import highlight_tokens
from AgStudio.shared.recognition import SourceSpan

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / 'AgStudio/examples/HelloWorld.arc'
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class DefaultTests(unittest.TestCase):
    def test_default_matches_shipped_file_and_preserves_selection(self):
        base = json.loads((ROOT / 'AgStudio/color_schemes/Default.json').read_text())['colors']
        self.assertEqual(default_scheme(), base)
        with tempfile.TemporaryDirectory() as directory:
            store = SchemeStore(directory)
            self.assertEqual(store.selected()[1], base)
            custom = default_scheme()
            custom['editor']['foreground'] = [1, 2, 3, 255]
            store.select('My colors', custom)
            self.assertEqual(store.selected(), ('My colors', custom, None))

    def test_factory_example_has_only_initial_section_advice_and_preserves_syntax(self):
        source = EXAMPLE.read_text(encoding='utf-8')
        result = analyze(source)
        self.assertEqual([(f.rule_id, f.severity) for f in result.diagnostics.findings],
                         [('AG-DOCUMENT-START-SECTION', 'information')])
        self.assertEqual([(m.path, m.kind) for m in result.semantics.members],
                         [(('value',), 'definition'), (('value',), 'invocation'),
                           (('value',), 'reference')])
        self.assertEqual({t.role for t in highlight_tokens(result.document)},
                         {'symbol', 'symbol_body', 'operation', 'alias', 'priority',
                          'sequence', 'bullet', 'section', 'colon', 'wildcard', 'binder', 'delimiter', 'literal', 'backtick', 'backtick_content'})
        kinds = {t.kind for t in result.tree.tokens}
        self.assertTrue({'binder', 'wildcard', 'section_colon', 'alias_keyword', 'literal_open',
                         'literal_close', 'indentation'} <= kinds)
        self.assertNotIn('quoted_scalar', kinds)
        self.assertIn('P0. Output only the assembled characters on one line', source)
        self.assertNotIn('Hello World!', source)
        self.assertIn('[Message]: []\n\nTask:', source)
        self.assertEqual([t.text for t in result.tree.tokens if t.kind == 'alias_keyword'], ['AS'])
        self.assertIn('AS [Codes]', source)
        self.assertIn('2. For each code point in [Codes] in order:\n'
                      '  => Invoke [CharacterFactory] and append its `value` to [Message]', source)

    def test_backtick_error_exact_range_and_admission(self):
        source = 'Context:\r\n- 🌍 `two words` and `another name`\r\n'
        result = analyze(source)
        findings = result.diagnostics.findings
        self.assertEqual(len(findings), 2)
        self.assertEqual([f.source_range.span.extract(source) for f in findings],
                         ['`two words`', '`another name`'])
        for f in findings:
            self.assertEqual((f.rule_id, f.severity),
                             ('AG-BACKTICK-WHITESPACE', 'error'))
            self.assertIn('use double quotes', f.message)
            self.assertIn('whitespace-free structural identifier', f.message)
        node = result.tree.nodes[1]
        fake = Candidate('AG-BACKTICK-WHITESPACE', SourceSpan(node.span.start, node.span.start + 1),
                         node.id, 'fabricated', ('backtick_whitespace',))
        self.assertIn('unsupported_backtick_whitespace', admission(fake, result.document, result.tree))
        self.assertFalse(analyze(source, arcgrav_version='unknown').diagnostics.findings)

    def test_backtick_shielding_and_uncertain_forms(self):
        for source in ['- `accountId`', '- "`two words`"', "- '`two words`'",
                       '"""\n`two words`\n"""', '- ``two words``', '- `unfinished words',
                       r'- \`two words\`', '- `one\ntwo`']:
            with self.subTest(source=source):
                self.assertFalse([f for f in analyze(source).diagnostics.findings
                                  if f.rule_id == 'AG-BACKTICK-WHITESPACE'])

    def test_cli_error_meets_default_threshold(self):
        for arguments, expected in [([], 1), (['--fail-on', 'warning'], 1),
                                    (['--fail-on', 'critical'], 0)]:
            result = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', *arguments, '-'],
                                    input='Task:\n- Read `two words`', text=True, capture_output=True, cwd=ROOT)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertEqual(json.loads(result.stdout)['results'][0]['findings'][0]['severity'], 'error')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class StartupGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(str(Path(self.temp.name) / 'startup.ini'), QSettings.Format.IniFormat)
        self.store = SchemeStore(Path(self.temp.name) / 'colors')

    def window(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        window = StudioWindow('current', user_state=UserState(), background=False, scheme_store=self.store)
        self.addCleanup(window.deleteLater)
        return window

    def test_first_launch_existing_example_next_launch_blank_and_new_blank(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtGui import QFont
        from AgStudio.gui.app import APP_VERSION
        window = self.window()
        window.initialize_startup(settings=self.settings)
        self.assertEqual(window.tabs.count(), 1)
        tab = window.current()
        self.assertEqual(tab.source, EXAMPLE.read_text(encoding='utf-8'))
        self.assertEqual(tab.path, EXAMPLE.resolve())
        self.assertFalse(tab.dirty)
        self.assertEqual(window.windowTitle(), f'Architectural Gravity Studio - Ver. {APP_VERSION} - HelloWorld.arc')
        self.assertEqual(window.tabs.tabText(0), 'HelloWorld.arc')
        self.assertEqual(window.tabs.tabToolTip(0), str(EXAMPLE.resolve()))
        for role, fmt in tab.highlighter._formats.items():
            self.assertEqual(fmt.fontWeight(), QFont.Weight.Normal if role in {'literal', 'backtick_content', 'double_quote_content'} else QFont.Weight.Bold)
        self.assertEqual(EXAMPLE.read_text(encoding='utf-8'), tab.source)
        self.assertEqual(window.new_document().source, '')
        reopened = self.window()
        persisted = QSettings(self.settings.fileName(), QSettings.Format.IniFormat)
        reopened.initialize_startup(settings=persisted)
        self.assertEqual(reopened.current().source, '')

    def test_explicit_file_and_edited_document_preserved(self):
        path = Path(self.temp.name) / 'mine.arc'
        original = b'Scope:\r\n- My saved document\r\n'
        path.write_bytes(original)
        window = self.window()
        window.initialize_startup(path, settings=self.settings)
        self.assertEqual(window.current().path, path)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(self.settings.contains('startup/helloWorldShown'))
        edited = self.window()
        edited.current().editor.setPlainText('Unsaved work')
        edited.initialize_startup(settings=self.settings)
        self.assertEqual(edited.current().source, 'Unsaved work')
        self.assertFalse(self.settings.contains('startup/helloWorldShown'))
