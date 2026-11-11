"""Initial plain-section advice without inferring retrieval semantics."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest

from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.document_end import START_RULE_ID, START_MESSAGE
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission
from AgStudio.shared.recognition import SourceSpan

ROOT = Path(__file__).resolve().parents[3]
MESSAGE = 'Define an initial invocation at the top like "Scope" to constrain the overall LLM inference boundary.'


class DocumentStartSectionTests(unittest.TestCase):
    def findings(self, source, **kwargs):
        return [f for f in analyze(source, **kwargs).diagnostics.findings if f.rule_id == START_RULE_ID]

    def test_plain_first_section_and_children_pass(self):
        for source in ('Task:\n- Read text\n', 'Retrieval: value\n', 'Context:\nOrdinary text\n',
                       '\n \nScope:\n- Parent:\n  - Child\n',
                       'Task:\n- Use [Action]\n', 'Task: "[Action]"\n',
                       'Scope: value\n\n[Something]:\n- Whatever\n'):
            self.assertFalse(self.findings(source), source)
        for source in ('', '\n', ' \t\r\n\n'):
            self.assertFalse(self.findings(source))
        self.assertFalse(self.findings('[Something]: value', arcgrav_version='future'))

    def test_exact_message_severity_and_symbolic_first(self):
        source = '[Something]:\n- Whatever\n\n'
        result = analyze(source)
        findings = self.findings(source)
        self.assertEqual(START_MESSAGE, MESSAGE)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual((finding.message, finding.severity),
                         (MESSAGE, 'information'))
        self.assertEqual(finding.source_range.span.extract(source), '[Something]:')
        end = next(f for f in result.diagnostics.findings if f.rule_id == 'AG-DOCUMENT-END-SECTION')
        self.assertEqual(end.severity, 'critical')
        self.assertEqual(result.document.source, source)

    def test_later_section_does_not_cure_first_element(self):
        for first in ('Ordinary prose', '[Something]: value', '=> Read text', '- Read text',
                      '"Task:"', '`Task:`', '"""\nTask:\n"""', '```\nTask:\n```',
                      '~~~\nTask:\n~~~', '[Open', '   Task:', 'Task :', 'Task:\t',
                      'Task: [Action]', 'Task: value AS [Action]', 'Task: value ↳'):
            source = first + '\n\nTask:\n- Read text\n'
            with self.subTest(first=first):
                self.assertEqual(len(self.findings(source)), 1)
                self.assertEqual(self.findings(source)[0].source_range.span.extract(source), first.split('\n')[0].strip())

    def test_admission_requires_exact_first_element_evidence(self):
        source = 'Ordinary prose\n\nTask: value\n'
        result = analyze(source)
        finding = self.findings(source)[0]
        candidate = Candidate(START_RULE_ID, finding.source_range.span, 0, 'untrusted',
                              REGISTRY[START_RULE_ID].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
        self.assertIn('unsupported_document_start', admission(replace(candidate, span=SourceSpan(0, 2)),
                      result.document, result.tree, result.semantics))
        valid = analyze('Task: value\n')
        self.assertIn('unsupported_document_start', admission(replace(candidate, span=SourceSpan(0, 5)),
                      valid.document, valid.tree, valid.semantics))

    def test_cli_unicode_ranges_and_info_threshold(self):
        for ending in ('\n', '\r\n', '\u2028'):
            source = ending + '🌍 Read text' + ending + ending + 'Task: value' + ending
            process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '-'],
                                     input=source.encode(), cwd=ROOT, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            finding = next(f for f in json.loads(process.stdout)['results'][0]['findings']
                           if f['rule_id'] == START_RULE_ID)
            self.assertEqual((finding['message'], finding['severity']), (MESSAGE, 'information'))
            start, end = len(ending), len(ending) + len('🌍 Read text')
            self.assertEqual(finding['source_range'], {
                'span': {'start': start, 'end': end},
                'start': {'offset': start, 'line': 2, 'column': 1},
                'end': {'offset': end, 'line': 2, 'column': 12},
            })
        self.assertFalse(self.findings('Task:\n- Read text\n'))
        source = 'Read text\n\nTask: value\n'
        for threshold in ('critical', 'error', 'warning', 'never'):
            process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '--fail-on', threshold, '-'],
                                     input=source.encode(), cwd=ROOT, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            findings = json.loads(process.stdout)['results'][0]['findings']
            self.assertEqual([(f['rule_id'], f['severity'], f['message']) for f in findings],
                             [(START_RULE_ID, 'information', MESSAGE)])

    def test_bom_is_ignored_by_existing_cli_file_decoding(self):
        source = '\ufeff\nTask:\r\n- Read text\r\n'
        process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '-'],
                                 input=source.encode('utf-8'), cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)['results'][0]['findings'], [])
