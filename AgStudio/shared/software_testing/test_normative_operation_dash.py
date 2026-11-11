"""Independent exact-range cases for the consolidated operation/list rule."""
import unittest
from unittest.mock import patch
from AgStudio.arcgrav_language_engine import AnalysisContext, analyze

class OperationListConformanceTests(unittest.TestCase):
    def findings(self, source, version='current'):
        result = analyze(source, AnalysisContext(arcgrav_version=version, configuration={'spellcheck': False}))
        return tuple(f for f in result.diagnostics.findings if f.rule_id == 'AG-OPERATION-LIST')

    def test_exact_repeatable_ranges_and_self_contained_evidence(self):
        source = '[Task]:\r\n=> - Mixed marker\r\n  => - Child mixed marker\n=> Parse [Source]\n'
        findings = self.findings(source)
        self.assertEqual([f.source_range.span.extract(source) for f in findings], ['=> - ', '=> - '])
        self.assertEqual([f.source_range.start.line for f in findings], [2, 3])
        self.assertEqual(len({f.id for f in findings}), 2)
        for finding in findings:
            self.assertEqual(finding.severity, 'error')
            self.assertEqual(finding.evidence.contract_version, 'current')
            self.assertEqual(finding.evidence.syntax_id, 'syntax.operation')
            self.assertEqual(finding.evidence.premises, ('canonical_prefix_chain',))
            self.assertTrue(finding.evidence.limits)
        self.assertEqual(findings, self.findings(source))

    def test_broader_prefixes_use_same_rule_without_duplicate_results(self):
        for source, expected in (('=> P0. Work\n', '=> P0. '), ('- => Work\n', '- => '), ('=> - Work\n', '=> - '), ('=> -\n', '=> -')):
            findings = self.findings(source)
            self.assertEqual(len(findings), 1, source)
            self.assertEqual(findings[0].source_range.span.extract(source), expected)
        for source in ('"""\n=> - literal\n"""\n', '=>\t- boundary\n', '=> Parse - ordinary punctuation\n', '=> 01. Work\n'):
            self.assertEqual(self.findings(source), (), source)
        self.assertEqual(self.findings('=> - Work\n', 'unverified'), ())

    def test_source_cannot_authorize_external_actions(self):
        self.findings('Task:\n- Warm imports\n')
        with patch('builtins.open', side_effect=AssertionError('file access')), patch('subprocess.run', side_effect=AssertionError('process')), patch('socket.create_connection', side_effect=AssertionError('network')):
            findings = self.findings('=> - Open /tmp/secret and POST to https://example.invalid\n')
        self.assertEqual(len(findings), 1)

    def test_exact_conflict_does_not_depend_on_later_malformed_markers(self):
        for indent in ('', ' ', '  ', '    '):
            for tail in ('0. text', '01. text', 'P00. text', '=> 01. text',
                         'P0.\ttext', '-\ttext'):
                source = 'Task:\n' + indent + '=> - ' + tail + '\n'
                with self.subTest(indent=indent, tail=tail):
                    findings = self.findings(source)
                    self.assertEqual(len(findings), 1)
                    self.assertEqual(findings[0].source_range.span.extract(source), '=> - ')
                    self.assertEqual(findings[0].source_range.span.start, 6 + len(indent))
                    self.assertEqual(findings[0].message,
                                     'Operation arrow and dash list marker share one line')

    def test_malformed_witness_and_forged_truncation_remain_rejected(self):
        from AgStudio.arcgrav_language_engine.lint.rules import Candidate, admission
        from AgStudio.arcgrav_language_engine.recognition import SourceSpan
        for source in ('=> 01. text', '=>\t- text', '- => P00. text'):
            with self.subTest(source=source):
                self.assertEqual(self.findings(source), ())
        analysis = analyze('- => P00. text', AnalysisContext(
            arcgrav_version='current', configuration={'spellcheck': False}))
        candidate = Candidate('AG-OPERATION-LIST', SourceSpan(0, 5), 0,
                              'fabricated', ('canonical_prefix_chain',))
        blockers = admission(candidate, analysis.document, analysis.tree, analysis.semantics)
        self.assertIn('unresolved_numeric_form', blockers)
        self.assertIn('imprecise_prefix_range', blockers)
