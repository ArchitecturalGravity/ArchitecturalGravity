"""Executable syntax contracts and concrete unsupported-source boundaries."""
from dataclasses import fields
import unittest
from unittest.mock import patch
from AgStudio.arcgrav_language_engine import AnalysisContext, analyze, prepare
from AgStudio.arcgrav_language_engine.syntax_contract import SYMBOL_NAME, NUMERIC_LIST

class SyntaxContractTests(unittest.TestCase):
    def analyze(self, source):
        return analyze(source, AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False}))

    def test_exact_symbol_names_and_numeric_forms(self):
        for name in ('A', 'GoodName2', 'ABC9'):
            self.assertIsNotNone(SYMBOL_NAME.fullmatch(name))
        for name in ('', 'badName', 'Has Space', 'Bad_Name', 'Éclair', 'A-B', 'A\n'):
            self.assertIsNone(SYMBOL_NAME.fullmatch(name), name)
        for marker in ('1.', '99.', 'P0.', 'P10.'):
            self.assertIsNotNone(NUMERIC_LIST.fullmatch(marker))
        for marker in ('0.', '01.', 'P01.', 'p1.', '-1.', '1. '):
            self.assertIsNone(NUMERIC_LIST.fullmatch(marker), marker)

    def test_symbol_definition_alias_use_and_duplicate_are_executable(self):
        result = self.analyze('[Value]: text\n\nTask:\n- Use [Value]\n- Collect AS [Alias]\n- Use [Alias]\n')
        self.assertEqual([s.kind for s in result.semantics.symbols], ['anchor', 'reference', 'alias', 'reference'])
        self.assertEqual([r.status for r in result.semantics.resolutions], ['unique_prior_anchor', 'unique_prior_alias'])
        duplicate = self.analyze('[Value]: one\n[Value]: two\n')
        self.assertIn('AG-SYMBOL-DUPLICATE-INSTANTIATION', [f.rule_id for f in duplicate.diagnostics.findings])

    def test_supported_source_has_no_blanket_specification_questions(self):
        result = self.analyze('Scope:\n- Read text\n\nTask:\n- Act\n')
        self.assertEqual(result.unresolved, ())
        self.assertTrue(all(not fact.limitations for fact in result.document.facts()))
        source = 'Task:\n=>\n[Open\n'
        result = self.analyze(source)
        self.assertIn('unfinished_operation', result.unresolved)
        self.assertIn('unfinished_symbol', result.unresolved)
        self.assertEqual(result.document.source, source)

    def test_separator_boundaries_are_preserved_not_normalized(self):
        source = 'Task:\n=>\t- Work\n   - Odd\n'
        result = self.analyze(source)
        self.assertEqual(result.document.source, source)
        self.assertIn('operation_boundary', result.unresolved)
        self.assertIn('indentation_boundary', result.unresolved)
        self.assertNotIn('AG-OPERATION-LIST', [f.rule_id for f in result.diagnostics.findings])
        self.assertIn('AG-INDENT-WIDTH', [f.rule_id for f in result.diagnostics.findings])

    def test_quoted_escaped_and_unfinished_literal_source_stays_inert(self):
        for source in ('Task:\n"[bad Name] => - Text"\n', 'Task:\n"""\n=> - Text\n[Open\n', 'Task:\n- \\[Hidden]\n'):
            result = self.analyze(source)
            self.assertEqual(result.document.source, source)
            self.assertNotIn('AG-OPERATION-LIST', [f.rule_id for f in result.diagnostics.findings])
            self.assertFalse(result.semantics.resolutions)

    def test_external_paths_wildcards_and_commands_never_execute(self):
        self.analyze('Task:\n- Warm imports\n')
        source = 'Scope:\n- /private/**/file.arc\n\nTask:\n=> Send `Remote` to https://example.invalid\n'
        with patch('builtins.open', side_effect=AssertionError('I/O')), patch('glob.glob', side_effect=AssertionError('expansion')), patch('subprocess.run', side_effect=AssertionError('execution')), patch('socket.create_connection', side_effect=AssertionError('network')):
            result = self.analyze(source)
        self.assertIn('wildcard_not_expanded', result.unresolved)
        self.assertIn('external_resolution_not_performed', result.unresolved)
        self.assertEqual(result.document.source, source)

    def test_unknown_version_never_selects_current_rules(self):
        for version in ('v1', 'future', ' current'):
            context = AnalysisContext(arcgrav_version=version, configuration={'spellcheck': False})
            result = analyze('=> - Work\n', context)
            self.assertEqual(result.diagnostics.status, 'unsupported_version')
            self.assertEqual(result.diagnostics.rules, ())
            self.assertEqual(result.diagnostics.findings, ())
            self.assertIn('unsupported_version', result.unresolved)
