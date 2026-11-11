"""Real offline English dictionary, canonical prose boundaries and safe failure."""
from dataclasses import replace
from pathlib import Path
import json
import io
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

from AgStudio.shared.lint import analyze
from AgStudio.shared.lint import spelling
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission
from AgStudio.shared.recognition import SourceSpan

ROOT = Path(__file__).resolve().parents[3]


class SpellingTests(unittest.TestCase):
    def test_all_71_technical_terms_are_loaded_into_native_hunspell(self):
        checker = spelling._get_checker()
        self.assertIsNotNone(checker)
        self.assertEqual(len(spelling.TECHNICAL_WORDS), 71)
        for word in spelling.TECHNICAL_WORDS:
            with self.subTest(word=word):
                self.assertTrue(checker.spell(word))
                self.assertTrue(spelling._known(word + "'s"))
        self.assertFalse(self.findings('- ' + ' '.join(sorted(spelling.TECHNICAL_WORDS)) + '\n'))

    def test_fixed_utf8_dictionary_ignores_environment_override(self):
        with patch.dict('os.environ', {'HUNSPELL_DATA': '/missing/untrusted/dictionary'}):
            checker = spelling._load_checker()
        self.assertIsNotNone(checker)
        self.assertEqual(checker._dic_encoding.upper().replace('-', ''), 'UTF8')
        self.assertFalse(checker.spell('αβγzzzz'))

    def test_hunspell_suggestion_order_is_preserved_and_deduplicated(self):
        spelling._suggestions.cache_clear()
        checker = Mock()
        checker.suggest.return_value = ('ranked', 'first', 'ranked', '', 'third', 'fourth', 'fifth', 'sixth')
        with patch.object(spelling, '_get_checker', return_value=checker):
            self.assertEqual(spelling._suggestions('rankingprobe'),
                             ('ranked', 'first', 'third', 'fourth', 'fifth'))
        spelling._suggestions.cache_clear()

    def findings(self, source, **kwargs):
        return [f for f in analyze(source, **kwargs).diagnostics.findings if f.rule_id == 'AG-SPELLING']

    def words(self, source):
        return [f.source_range.span.extract(source) for f in self.findings(source)]

    def test_real_dictionary_misspellings_and_deterministic_suggestions(self):
        checker = spelling._get_checker()
        self.assertIsNotNone(checker, 'Install AgStudio/gui/requirements.txt')
        self.assertTrue(checker.spell('hello'))
        self.assertFalse(checker.spell('mispelled'))
        source = '- Please recieve the mispelled document\n'
        findings = self.findings(source)
        self.assertEqual(self.words(source), ['recieve', 'mispelled'])
        self.assertEqual(findings[0].message, 'Possible English misspelling: recieve')
        self.assertIn('receive', spelling.suggestions_for_word('recieve'))
        self.assertEqual(findings[1].message, 'Possible English misspelling: mispelled')
        self.assertIn('misspelled', spelling.suggestions_for_word('mispelled'))
        self.assertTrue(all((f.severity) == ('warning') for f in findings))
        self.assertEqual(analyze(source).as_record(), analyze(source).as_record())

    def test_english_casing_contractions_possessives_and_inflections(self):
        correct = ("- The developers’ applications aren’t running correctly\n"
                   "- Don't change the developer's settings or the children's documents\n"
                   '- Well-defined requirements describe useful behavior\n'
                   '- These processes were tested carefully\n')
        self.assertFalse(self.findings(correct))
        source = '- Mispelled and MISPELLED ordinary prose\n'
        self.assertEqual(self.words(source), ['Mispelled', 'MISPELLED'])
        self.assertIn('Misspelled', spelling.suggestions_for_word('Mispelled'))
        self.assertIn('MISSPELLED', spelling.suggestions_for_word('MISPELLED'))
        self.assertEqual(self.words('- mispelled-word\n'), ['mispelled'])

    def test_prose_in_sections_lists_operations_and_parentheses(self):
        source = 'Mispelled: text\n\n1. Inspect mispelled descriptions\n=> Read (mispelled) prose\n'
        self.assertEqual(self.words(source), ['Mispelled', 'mispelled', 'mispelled'])

    def test_identifiers_and_protected_tokens_are_opaque(self):
        source = ('[Mispelled]:\n- `recieve`: "mispelled text"\n'
                  '- Read [Mispelled].recieve and `mispelled`\n'
                  '- "mispelled" \'recieve\'\n'
                  '- Read projectMispellt, ProjectMispellt, snake_mispellt and v1mispellt\n'
                  '=> Read [Mispelled] AS [Recieve] ↳\n  - Read [Recieve]\n')
        self.assertFalse(self.findings(source))

    def test_source_context_masks_split_technical_runs_and_spaced_calls(self):
        source = ('- Visit https://mispellt.invalid/mispellt?q=recieve#fragment\n'
                  '- Email recieve@mispellt.invalid or open /tmp/mispellt.txt\n'
                  '- Read C:\\mispellt\\recieve.txt or ../mispellt/file or folder/mispellt\n'
                  '- Read obj.mispellt, [Thing].mispellt, [Thing].`recieve` and *.mispellt\n'
                  '- Run call(mispellt, recieve) or call( mispelled ) or --mispellt=value\n'
                  'mispellt = recieve + mispelled\n'
                  '- Read <mispellt> {recieve} 1.2.3 $mispellt\n')
        self.assertFalse(self.findings(source))
        self.assertEqual(self.words(source + '- Then recieve ordinary text\n'), ['recieve'])
        self.assertEqual(self.words('- See https://example.invalid?q=value then recieve text\n'), ['recieve'])
        self.assertEqual(self.words('- "Some x = value" then recieve text\n'), ['recieve'])
        self.assertEqual(self.words('- "Example(" "[Open" then recieve text\n'), ['recieve'])
        self.assertFalse(self.findings('- Read call("x)", mispelled) and ["x]" mispelled]\n'))

    def test_literal_fences_quotes_recovery_and_uncertain_bodies(self):
        for source in ('"""\nmispelled\n```python\nrecieve\n"""\n',
                       '```python\nprint(mispelled)\nrecieve\n```\n',
                       '~~~python\nmispelled\n~~~\n',
                       '- "unfinished mispelled\n',
                       '[Open mispelled\n', '   - mispelled\n',
                       '[A]\n  - mispelled\n'):
            self.assertFalse(self.findings(source), source)
        self.assertEqual(self.words('"""\n```python\n"""\n- mispelled\n'), ['mispelled'])
        self.assertEqual(self.words('```\nmispelled\n```\n- recieve\n'), ['recieve'])
        self.assertFalse(self.findings('```\nmispelled\n'))

    def test_unicode_offsets_line_endings_and_gui_ranges(self):
        from PySide6.QtWidgets import QApplication
        from AgStudio.gui.app import DocumentTab
        app = QApplication.instance() or QApplication([])
        for ending in ('\n', '\r\n', '\u2028'):
            source = '- Correct text' + ending + '- 🌍 mispelled, aren’t wrong' + ending
            finding = self.findings(source)[0]
            self.assertEqual(finding.source_range.span,
                             SourceSpan(source.index('mispelled'), source.index('mispelled') + 9))
            self.assertEqual((finding.source_range.start.line, finding.source_range.start.column), (2, 5))
            self.assertEqual((finding.source_range.end.line, finding.source_range.end.column), (2, 14))
            self.assertEqual(finding.severity, 'warning')
            tab = DocumentTab('current', source, map_enabled=False)
            try:
                row = next(tab.diagnostic_list.topLevelItem(i)
                           for i in range(tab.diagnostic_list.topLevelItemCount())
                           if tab.diagnostic_list.topLevelItem(i).text(1) == 'AG-SPELLING')
                self.assertEqual(row.text(0), 'Warning')
                self.assertEqual((row.text(3), row.text(4)), ('2', '5'))
                tab._navigate_finding(row)
                cursor = tab.editor.textCursor()
                self.assertEqual(cursor.selectedText(), 'mispelled')
                # Qt keeps U+2028 in one paragraph and collapses CRLF.
                self.assertEqual(cursor.blockNumber(), 0 if ending == '\u2028' else 1)
                start = 20 if ending == '\u2028' else 5
                self.assertEqual(cursor.selectionStart() - cursor.block().position(), start)
                self.assertEqual(cursor.selectionEnd() - cursor.block().position(), start + 9)
            finally:
                tab.close()
                tab.deleteLater()
                app.processEvents()

    def test_dictionary_normalization_preserves_source_span(self):
        source = '- 🌍 re\u0301cieve\n'
        findings = self.findings(source)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].source_range.span.extract(source), 're\u0301cieve')
        self.assertEqual(spelling._normalize('AREN’T'), "aren't")

    def test_cached_repeated_words_bounded_suggestions_and_long_unknowns(self):
        checker = spelling._get_checker()
        self.assertIsNotNone(checker, 'Install AgStudio/gui/requirements.txt')
        spelling._known.cache_clear()
        spelling._suggestions.cache_clear()
        source = '- ' + 'mispelled ' * 1500 + '\n'
        started = time.monotonic()
        wrapped = Mock(wraps=checker)
        with patch.object(spelling, '_get_checker', return_value=wrapped):
            self.assertEqual(len(self.findings(source)), 1500)
            self.assertEqual(wrapped.suggest.call_count, 0)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(spelling._known.cache_info().maxsize, 8192)
        self.assertEqual(spelling._suggestions.cache_info().maxsize, 8192)
        source = '- ' + 'z' * 64 + '\n'
        wrapped.suggest.side_effect = AssertionError('long suggestions')
        with patch.object(spelling, '_get_checker', return_value=wrapped):
            self.assertEqual(len(self.findings(source)), 1)
        self.assertLessEqual(len(spelling._suggestions('mispelled')), 5)

    def test_missing_or_broken_dependency_is_explicit_and_never_a_fallback_dictionary(self):
        with patch('hunspell.Hunspell', side_effect=OSError('missing dictionary')):
            self.assertIsNone(spelling._load_checker())
        real_import = __import__
        def unavailable(name, *args, **kwargs):
            if name == 'hunspell':
                raise ImportError('unavailable')
            return real_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=unavailable):
            self.assertIsNone(spelling._load_checker())
        source = '- mispelled ordinary text\n- recieve\n'
        with patch.object(spelling, '_CHECKER', None):
            findings = analyze(source).diagnostics.findings
            statuses = [f for f in findings if f.rule_id.startswith('AG-SPELL')]
            self.assertEqual([(f.rule_id, f.severity) for f in statuses], [('AG-SPELLCHECK-UNAVAILABLE', 'information')])
            self.assertIn('requirements.txt', statuses[0].message)
            self.assertEqual(statuses[0].source_range.span.extract(source), 'mispelled')
            self.assertFalse([f for f in analyze('"mispelled"\n').diagnostics.findings
                              if f.rule_id.startswith('AG-SPELL')])

    def test_admission_rebuilds_exact_word_evidence_and_rejects_protected_spans(self):
        source = '- mispelled and `recieve`\n'
        result = analyze(source)
        finding = self.findings(source)[0]
        candidate = Candidate('AG-SPELLING', finding.source_range.span, 0, 'untrusted',
                              REGISTRY['AG-SPELLING'].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
        protected = SourceSpan(source.index('recieve'), source.index('recieve') + 7)
        self.assertIn('unsupported_spelling_evidence', admission(replace(candidate, span=protected),
                      result.document, result.tree, result.semantics))
        shortened = SourceSpan(candidate.span.start, candidate.span.end - 1)
        self.assertIn('unsupported_spelling_evidence', admission(replace(candidate, span=shortened),
                      result.document, result.tree, result.semantics))
        clean = analyze('- correctly and `recieve`\n')
        self.assertIn('unsupported_spelling_evidence', admission(candidate, clean.document, clean.tree, result.semantics))

    def test_no_document_io_no_automatic_changes_disable_and_unknown_version(self):
        source = '- mispelled https://example.invalid/mispellt\n'
        with patch('builtins.open', side_effect=AssertionError('document file read')), \
             patch('socket.create_connection', side_effect=AssertionError('network')), \
             patch('subprocess.run', side_effect=AssertionError('execution')):
            result = analyze(source)
        self.assertEqual(result.document.source, source)
        self.assertEqual(len(self.words(source)), 1)
        self.assertFalse(self.findings(source, configuration={'spellcheck': False}))
        self.assertFalse(analyze(source, arcgrav_version='future').diagnostics.findings)
        self.assertFalse(self.findings((ROOT / 'AgStudio/examples/HelloWorld.arc').read_text()))

    def test_analysis_and_cli_never_generate_corrections(self):
        from AgStudio.shared.cli import main
        source = '- Please recieve the mispelled document\n'
        checker = spelling._get_checker()
        wrapped = Mock(wraps=checker)
        wrapped.suggest.side_effect = AssertionError('analysis must not suggest')
        spelling._known.cache_clear()
        spelling._suggestions.cache_clear()
        with patch.object(spelling, '_get_checker', return_value=wrapped), \
             patch.object(spelling, 'suggestions_for_word', side_effect=AssertionError('eager suggestion')):
            record = analyze(source).as_record()
            findings = [f for f in record['findings'] if f['rule_id'] == 'AG-SPELLING']
            self.assertEqual(len(findings), 2)
            self.assertTrue(all('Suggestions:' not in f['message'] for f in findings))
            for arguments in (['--json', '--fail-on', 'never', '-'], ['--fail-on', 'never', '-']):
                stdin = io.TextIOWrapper(io.BytesIO(source.encode()))
                output = io.StringIO()
                with patch('sys.stdin', stdin), patch('sys.stdout', output):
                    self.assertEqual(main(arguments), 0)
                self.assertIn('Possible English misspelling', output.getvalue())
                self.assertNotIn('Suggestions:', output.getvalue())
            wrapped.suggest.assert_not_called()

    def test_cli_spelling_is_advisory_without_suggestions(self):
        source = 'Task:\n- Please recieve the document\n'
        for arguments, expected in [([], 0), (['--fail-on', 'warning'], 1)]:
            process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', *arguments, '-'],
                                     input=source.encode(), cwd=ROOT, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, expected, process.stderr)
            record = json.loads(process.stdout)['results'][0]
            finding = next(f for f in record['findings'] if f['rule_id'] == 'AG-SPELLING')
            self.assertEqual(finding['severity'], 'warning')
            self.assertEqual(finding['message'], 'Possible English misspelling: recieve')


class SpellingFindingProjectionTests(unittest.TestCase):
    def test_warning_rows_counts_order_and_gutter_use_admitted_severity(self):
        from AgStudio.shared.diagnostics import SEVERITY_ORDER
        from AgStudio.shared.panel_projections import derive_findings
        source = 'Task:\n- Please recieve text.\n- mispelled text\n'
        analysis = analyze(source)
        projection = derive_findings(analysis)
        rows = [row for row in projection.rows if row.finding.rule_id == 'AG-SPELLING']
        self.assertEqual(len(rows), 2)
        self.assertEqual([row.texts[0] for row in rows], ['Warning', 'Warning'])
        self.assertEqual([row.texts[3:] for row in rows], [('2', '10'), ('3', '3')])
        self.assertEqual([row.finding.source_range.span.extract(source) for row in rows],
                         ['recieve', 'mispelled'])
        self.assertEqual(dict(projection.counts)['warning'], 2)
        self.assertEqual(dict(projection.severities), {2: 'error', 3: 'warning'})
        order = [SEVERITY_ORDER[row.finding.severity] for row in projection.rows]
        self.assertEqual(order, sorted(order, reverse=True))
        self.assertEqual(len(projection.spelling), 2)
        self.assertEqual(sum(dict(projection.counts).values()), len(analysis.diagnostics.findings))

    def test_no_rows_for_correct_disabled_protected_or_suppressed_spelling(self):
        from AgStudio.shared.panel_projections import derive_findings
        for source, options in (
                ('Task:\n- receive text\n', {}),
                ('Task:\n- recieve text\n', {'configuration': {'spellcheck': False}}),
                ('Task:\n- `recieve` text\n', {}),
                ('Task:\n- recieve text\n', {'arcgrav_version': 'future'})):
            with self.subTest(source=source, options=options):
                projection = derive_findings(analyze(source, **options))
                self.assertFalse([row for row in projection.rows if row.finding.rule_id == 'AG-SPELLING'])
                self.assertFalse(projection.spelling)
        # Projection consumes admitted findings only, never suppressed candidates.
        analysis = analyze('Task:\n- recieve text\n')
        suppressed = replace(analysis, diagnostics=replace(analysis.diagnostics, findings=(),
                             suppressed_conclusions=(('AG-SPELLING', '1', ('unsupported_spelling_evidence',)),)))
        projection = derive_findings(suppressed)
        self.assertFalse(projection.rows)
        self.assertFalse(projection.spelling)
        self.assertIn('1 suppressed conclusions', projection.heading_tooltip)
