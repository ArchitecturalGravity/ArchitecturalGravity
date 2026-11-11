"""Final root parent is a section; ordinary child content may follow it."""
from dataclasses import replace
from pathlib import Path
import json
import subprocess
import sys
import unittest

from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.document_end import RULE_ID, document_end_span
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission
from AgStudio.shared.recognition import SourceSpan

ROOT = Path(__file__).resolve().parents[3]


class DocumentEndSectionTests(unittest.TestCase):
    def findings(self, source, **kwargs):
        return [f for f in analyze(source, **kwargs).diagnostics.findings if f.rule_id == RULE_ID]

    def test_final_section_may_have_prose_lists_and_nested_children(self):
        for source in ('Task:', 'Task:\nOrdinary prose\n', 'Task:\n- Read text\n\n  \n',
                       'Task:\n  - Read text\n', 'Task:\n- Parent:\n  - Child\n',
                       'Task:\n  Details:\n  - Child\n', 'Task:\n=> Read text\n',
                       'Task:\n=> Parent:\n  - Child\n',
                       'Context: value\n\nTask:\n- Read text\n',
                       'Context: value\n',
                       '=> Parent:\n  - Child\n\nTask:\n- Read text\n'):
            with self.subTest(source=source):
                self.assertFalse(self.findings(source))
        # Existing empty-section advice is a separate rule, not silently removed.
        self.assertIn('AG-SECTION-EMPTY', [f.rule_id for f in analyze('Task:').diagnostics.findings])

    def test_final_distinct_root_nonsection_parent_fails(self):
        # A scalar section closes preceding same-indent section ownership.
        source = 'Task:\n- Read text\n\nResult: value\n\n=> Finish:\n  - Child\n'
        result = analyze(source)
        final = result.tree.nodes[5]
        self.assertIsNone(final.parent)
        self.assertIsNone(final.section)
        finding = self.findings(source)[0]
        self.assertEqual((finding.severity), ('critical'))
        self.assertEqual(finding.source_range.span.extract(source), '=> Finish:')
        self.assertEqual(len(self.findings(source)), 1)
        self.assertEqual(len(self.findings('=> Parent:\n  Task:\n  - Child\n')), 1)
        self.assertEqual(len(self.findings('Finish ↳\n  - Child\n')), 1)

    def test_last_parent_is_not_last_root_leaf_or_last_nonblank_line(self):
        self.assertFalse(self.findings('Context: value\n- Read ordinary text\n'))
        self.assertFalse(self.findings('Task:\n- Read ordinary text\n\n'))
        source = '=> Parent:\n  - Child\nTrailing prose\n'
        self.assertEqual(self.findings(source)[0].source_range.span.extract(source), '=> Parent:')

    def test_fake_sections_do_not_satisfy_requirement(self):
        for source in ('"Task:"\n', '`Task:`\n', '"""\nTask:\n"""\n',
                       '"""\nTask:\n', '```arcgrav\nTask:\n```\n', '~~~\nTask:\n~~~\n',
                       '   Task:\n', '\tTask:\n', 'Task :\n', 'Task:\t\n',
                       'Several words:\n', '- Task:\n  - Child\n', '=> Task:\n  - Child\n',
                       'Context: value\n```\nTask:\n```\n=> Parent:\n  - Child\n'):
            with self.subTest(source=source):
                self.assertEqual(len(self.findings(source)), 1)
        self.assertFalse(self.findings('```\nTask:\n```\n\nTask:\n- Read text\n'))

    def test_empty_documents_and_exact_failure_range(self):
        for source in ('', '\n', ' \t\r\n\n'):
            self.assertFalse(self.findings(source))
        source = '- 🌍 Read text\r\n \r\n'
        finding = self.findings(source)[0]
        self.assertEqual(finding.source_range.span, SourceSpan(0, len('- 🌍 Read text')))
        literal = '"""\nTask:\n  \n'
        self.assertEqual(self.findings(literal)[0].source_range.span.extract(literal), 'Task:')
        for ending in ('\n', '\r\n', '\u2028'):
            self.assertFalse(self.findings(ending.join(['Task:', '- Read text', '', ''])))
        self.assertFalse(self.findings('- Read text', arcgrav_version='future'))

    def test_admission_rebuilds_hierarchy_and_rejects_forged_or_partial_ranges(self):
        source = '=> Parent:\n  - Child\n'
        result = analyze(source)
        finding = self.findings(source)[0]
        candidate = Candidate(RULE_ID, finding.source_range.span, 0, 'untrusted', REGISTRY[RULE_ID].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
        self.assertIn('unsupported_document_end', admission(
            replace(candidate, span=SourceSpan(0, 2)), result.document, result.tree, result.semantics))
        valid = analyze('Task: value\n')
        forged = replace(candidate, span=SourceSpan(0, 4))
        self.assertIn('unsupported_document_end', admission(forged, valid.document, valid.tree, result.semantics))
        # Document-boundary evidence can point at a protected final source range,
        # without admitting a claim about the literal's contents.
        literal = analyze('"Task:"\n')
        node_id, span = document_end_span(literal.tree)
        self.assertEqual(admission(replace(candidate, node_id=node_id, span=span),
                                   literal.document, literal.tree, literal.semantics), ())

    def test_cli_critical_severity_ranges_and_correction(self):
        source = '- 🌍 Read text\r\n'
        for threshold, expected in [('critical', 1), ('error', 1), ('warning', 1), ('never', 0)]:
            process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '--fail-on', threshold, '-'],
                                     input=source.encode(), cwd=ROOT, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, expected, process.stderr)
            findings = json.loads(process.stdout)['results'][0]['findings']
            finding = next(f for f in findings if f['rule_id'] == RULE_ID)
            self.assertEqual(finding['severity'], 'critical')
            self.assertEqual(finding['source_range'], {
                'span': {'start': 0, 'end': 13},
                'start': {'offset': 0, 'line': 1, 'column': 1},
                'end': {'offset': 13, 'line': 1, 'column': 14},
            })
        self.assertFalse(self.findings('Task:\n- Read text\n'))

    def test_exact_unsaved_symbolic_parent_is_critical(self):
        source = '[Something]:\n- Whatever\n\n'
        result = analyze(source)
        findings = self.findings(source)
        self.assertEqual(len(findings), 1)
        self.assertEqual((findings[0].severity), ('critical'))
        self.assertEqual(findings[0].source_range.span.extract(source), '[Something]:')
        self.assertIn('plain section', findings[0].message)
        self.assertIn('AG-SYMBOL-UNUSED', [f.rule_id for f in result.diagnostics.findings])
        self.assertEqual(result.document.source, source)

    def test_symbolic_definition_reference_and_alias_decoration_fail(self):
        for source in ('[Task]:\n- Read text\n', '[Task]: value\n',
                       '[Task]: value\n\n[Task]:\n- Read text\n',
                       'Task: [Action]\n', 'Task: value AS [Action]\n',
                       'Task: value ↳\n  - Child\n', '[Task] ↳\n  - Child\n',
                       '[État]:\n- Read text\n', '[Task :\n', '[Task]:\t\n',
                       '[Task]: value\n[Task] AS [Task]\n'):
            with self.subTest(source=source):
                self.assertEqual(len(self.findings(source)), 1)
        for source in ('[Action]: value\n\nTask:\n- Use [Action]\n',
                       'Task: "[Action]"\n', 'Task: `Action`\n',
                       '[Action]: value\n\nTask:\n  Details:\n  - Use [Action]\n'):
            self.assertFalse(self.findings(source), source)

    def test_plain_ending_with_symbolic_last_child(self):
        source = ('[Operationalization]: Run checks\n\n[OutputContract]: Output results\n\n'
                  '[Divergence]: Inspect differences\n\nTask:\n1. Run [Operationalization]\n'
                  '2. Return output conforming to [OutputContract]\n3. Run [Divergence]\n')
        ending = ('Task:\n1. Run [Operationalization]\n'
                  '2. Return output conforming to [OutputContract]\n3. Run [Divergence]\n')
        self.assertTrue(source.endswith(ending))
        self.assertFalse(self.findings(source))
        symbolic = source[:-len(ending)] + ending.replace('Task:', '[Task]:', 1)
        findings = self.findings(symbolic)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].source_range.span.extract(symbolic), '[Task]:')

    def test_symbolic_failure_admission_and_source_range(self):
        for ending in ('\n', '\r\n', '\u2028'):
            source = ending.join(['[Something]:', '- Whatever', '', ''])
            result = analyze(source)
            finding = self.findings(source)[0]
            candidate = Candidate(RULE_ID, finding.source_range.span, 0, 'untrusted',
                                  REGISTRY[RULE_ID].required_evidence)
            self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
            self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
            fixed = analyze(source.replace('[Something]:', 'Task:', 1))
            self.assertIn('unsupported_document_end', admission(
                replace(candidate, span=SourceSpan(0, 5)), fixed.document, fixed.tree, result.semantics))
            self.assertEqual(finding.severity, 'critical')
            self.assertEqual(finding.source_range.span, SourceSpan(0, 12))
            self.assertEqual((finding.source_range.start.line, finding.source_range.start.column), (1, 1))
            self.assertEqual((finding.source_range.end.line, finding.source_range.end.column), (1, 13))
