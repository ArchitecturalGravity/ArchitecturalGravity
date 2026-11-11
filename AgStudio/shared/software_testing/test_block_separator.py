"""Blank separators at parsed sibling block boundaries, never content lines."""
from dataclasses import replace
import unittest
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission

RULE = 'AG-BLOCK-SEPARATOR'


class BlockSeparatorTests(unittest.TestCase):
    def findings(self, source):
        return [f for f in analyze(source).diagnostics.findings if f.rule_id == RULE]

    def test_distinct_block_pairs(self):
        for first in ('First:\n- Content', '[First]:\n- Content', '[First]: value', 'First: value'):
            for second in ('Second:\n- Content', '[Second]: value'):
                with self.subTest(first=first, second=second):
                    source = first + '\n' + second
                    findings = self.findings(source)
                    self.assertEqual(len(findings), 1)
                    self.assertEqual(findings[0].severity, 'critical')
                    self.assertEqual(findings[0].source_range.span.extract(source),
                                     '[Second]' if second.startswith('[') else ':')

    def test_initial_blocks_and_existing_separators(self):
        for source in ('First:\n- Content', '[First]: value', 'Prose\nFirst:\n- Content',
                       'First: value\n\nSecond: value', 'First: value\r\n\r\nSecond: value',
                       'First: value\n  \nSecond: value'):
            self.assertFalse(self.findings(source), source)

    def test_parent_content_siblings_and_nested_blocks(self):
        for source in ('Root:\n  Child:\n  - Content', 'Root:\n- One\n- Two',
                       'Root:\n  One:\n  - Content\n\n  Two:\n  - Content',
                       '[A]:\n- [New]: value', '[A]: value\n[A]: other',
                       '[A]: value\nTask:\n- Use [A]\n- Use [A]'):
            expected = 1 if '\nTask:' in source else 0
            self.assertEqual(len(self.findings(source)), expected, source)
        self.assertEqual(len(self.findings('Root:\n  One:\n  - Content\n  Two:\n  - Content')), 1)
        self.assertEqual(len(self.findings('Root:\n  One: value\nNext:\n- Content')), 1)

    def test_literal_quotes_aliases_recovery_and_versions(self):
        for source in ('Root:\n"""\nFirst: value\nSecond: value\n"""',
                       'Root:\n- "First: value"\n- "[Second]: value"',
                       'Root:\n=> Collect AS [Result]\n- Use [Result]',
                       'First: value\n   - Broken\nSecond: value'):
            self.assertFalse(self.findings(source), source)
        self.assertEqual(len(self.findings('Root:\n"""\n\n"""\nNext: value')), 1)
        self.assertFalse(analyze('First: value\nSecond: value', arcgrav_version='future').diagnostics.findings)

    def test_independent_admission(self):
        source = 'First: value\nSecond: value'
        result = analyze(source)
        finding = self.findings(source)[0]
        candidate = Candidate(RULE, finding.source_range.span, 1, 'untrusted', REGISTRY[RULE].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
        first_colon = next(t.span for t in result.tree.nodes[0].tokens if t.kind == 'section_colon')
        self.assertIn('unsupported_block_boundary', admission(replace(candidate, span=first_colon, node_id=0),
                      result.document, result.tree, result.semantics))

    def test_critical_serialization_cli_thresholds_and_ranges(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        source = 'First: 🌍\r\nSecond: value\r\n'
        result = analyze(source)
        self.assertEqual([(f.rule_id, f.severity) for f in result.diagnostics.findings],
                         [(RULE, 'critical')])
        self.assertEqual(result.as_record()['findings'][0]['severity'], 'critical')
        root = Path(__file__).resolve().parents[3]
        for threshold, expected in [(None, 1), ('critical', 1), ('error', 1), ('warning', 1), ('never', 0)]:
            args = [] if threshold is None else ['--fail-on', threshold]
            process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', *args, '-'],
                                     input=source.encode(), cwd=root, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, expected, process.stderr)
            record = json.loads(process.stdout)
            self.assertEqual(record['schema_version'], 1)
            finding = record['results'][0]['findings'][0]
            self.assertEqual(finding['severity'], 'critical')
            start = source.index(':', source.index('Second'))
            self.assertEqual(finding['source_range'], {
                'span': {'start': start, 'end': start + 1},
                'start': {'offset': start, 'line': 2, 'column': 7},
                'end': {'offset': start + 1, 'line': 2, 'column': 8},
            })
        process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--fail-on', 'critical', '-'],
                                 input=b'Task:\n- Done.\n', cwd=root, capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn(b'error AG-LINE-ENDING', process.stdout)
        self.assertEqual([r.id for r in REGISTRY.values() if r.severity == 'critical'], [RULE, 'AG-DOCUMENT-END-SECTION'])
        self.assertEqual(REGISTRY['AG-MEMBER-AMBIGUOUS'].severity, 'warning')

    def test_lint_admission_rejects_unknown_severity(self):
        from unittest.mock import patch
        source = 'First: value\nSecond: value'
        result = analyze(source)
        candidate = Candidate(RULE, self.findings(source)[0].source_range.span, 1,
                              'untrusted', REGISTRY[RULE].required_evidence)
        with patch.dict(REGISTRY, {RULE: replace(REGISTRY[RULE], severity='unknown')}):
            self.assertIn('invalid_severity', admission(candidate, result.document, result.tree, result.semantics))
