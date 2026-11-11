"""Shared Findings-stage regression contracts, not new language authority."""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from AgStudio.shared.analysis_snapshot import (
    AnalysisRequest, calculate_analysis_snapshot, calculate_findings_update,
    calculate_parse_snapshot, pack_analysis, restore_analysis, restore_document,
)
from AgStudio.shared.core import LanguageCore
from AgStudio.shared.document import ParsedDocument
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.findings import assemble_diagnostics
from AgStudio.shared.lint.model import CanonicalDocument
from AgStudio.shared.lint.rules import RULES
from AgStudio.shared.lint.semantics import resolve
from AgStudio.shared.lint.syntax import parse
from AgStudio.shared.panel_projections import derive_findings
from AgStudio.shared.recognition import SourceSpan


ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_RULE = 'AG-OPERATION-LIST'
SOURCES = {
    'empty': '',
    'unicode_crlf_spelling': 'Task:\r\n- 🌍 Please recieve [Missing]\r\n=> - Active\r\n',
    'mixed_line_endings': 'Task:\r\n- 🌍 [Missing]\r=> - Active\n   - Odd\u2028=> 1. Act\x85Task: done\n',
    'literal': 'Source:\n""""\n"""\n=> - Literal [Hidden]\n"""\n""""\n\nTask:\n=> - Active\n',
    'unclosed_literal': 'Source:\n"""\n=> - Shielded\n[Open\n',
    'recovery_and_suppression': 'Task:\n[Open\n=>\n  => 01. Act\n=>\t- uncertain\n=> - Active\n',
    'identity': 'Task:\n- Use [Later]\n\n[Later]: []\n\n[Outer]:\n- [Nested]: value\n=> Collect AS [Exported]\n\nTask:\n- Use [Later]\n- Use [Exported]\n',
}
RECOGNITION_SOURCE = 'Scope:\n- "[Hidden]"\n=> - Active\n\n[A]: value\n\nTask:\n- Read [A]\n[Open\n'


def request_for(source, version='current', configuration=None, profile=None):
    return AnalysisRequest(source, version, profile, json.dumps(configuration or {}))


class AnalysisStageTests(unittest.TestCase):
    def test_complete_record_and_projection_parity_matrix(self):
        for name, source in SOURCES.items():
            for version in ('current', 'future-version'):
                for configuration in ({}, {'spellcheck': False}):
                    with self.subTest(source=name, version=version, configuration=configuration):
                        expected = analyze(source, arcgrav_version=version,
                                           profile='review', configuration=configuration)
                        parsed = calculate_parse_snapshot(request_for(
                            source, version, configuration, profile='review'))
                        self.assertEqual(parsed.diagnostics.status, 'pending')
                        self.assertEqual(parsed.diagnostics.findings, ())
                        self.assertTrue(parsed.document.canonical)
                        self.assertTrue(parsed.document.canonical)
                        for transport in (parsed, pack_analysis(parsed)):
                            completed = calculate_analysis_snapshot(transport)
                            actual = restore_analysis(completed.snapshot)
                            # Dataclass equality includes status/catalogue, which the
                            # public record intentionally does not serialize in full.
                            self.assertEqual(actual.diagnostics, expected.diagnostics)
                            self.assertEqual(actual.as_record(), expected.as_record())
                            self.assertEqual(completed.findings_projection, derive_findings(expected))
                            self.assertEqual(actual.document.source, source)
                            self.assertEqual(actual.document.session.configuration, configuration)
                            self.assertEqual(actual.document.session.profile, 'review')
                            self.assertEqual(actual.conformance, 'unknown')
                        update = calculate_findings_update(pack_analysis(parsed))
                        self.assertEqual(update.document_id, expected.document.document_id)
                        self.assertEqual(update.diagnostics, expected.diagnostics)
                        self.assertEqual(update.findings_projection, derive_findings(expected))
                        self.assertEqual(parsed.diagnostics.status, 'pending')
                        self.assertEqual(expected.diagnostics.status,
                                         'evaluated' if version == 'current' else 'unsupported_version')
                        self.assertEqual(expected.diagnostics.rules,
                                         RULES if version == 'current' else ())
                        if version != 'current':
                            self.assertEqual(expected.diagnostics.findings, ())
                            self.assertEqual(expected.diagnostics.rules, ())
                            self.assertEqual(expected.diagnostics.suppressed_conclusions, ())
                        if version == 'current' and name == 'recovery_and_suppression':
                            self.assertEqual(expected.diagnostics.suppressed_conclusions, (
                                ('AG-OPERATION-LIST', '3', (
                                    'missing_evidence:canonical_prefix_chain', 'unresolved_numeric_form')),
                                ('AG-OPERATION-LIST', '4', (
                                    'missing_evidence:canonical_prefix_chain', 'unresolved_marker_spacing')),
                            ))
                        if configuration.get('spellcheck') is False:
                            self.assertFalse(any(f.rule_id.startswith('AG-SPELL')
                                                 for f in expected.diagnostics.findings))
                        elif version == 'current' and name == 'unicode_crlf_spelling':
                            self.assertTrue(any(f.rule_id in ('AG-SPELLING', 'AG-SPELLCHECK-UNAVAILABLE')
                                                for f in expected.diagnostics.findings))

    def test_both_entry_points_pass_recognition_facts_to_the_same_stage(self):
        parsed = calculate_parse_snapshot(request_for(RECOGNITION_SOURCE))
        with patch('AgStudio.shared.lint.findings.assemble_diagnostics',
                   wraps=assemble_diagnostics) as stage:
            synchronous = analyze(RECOGNITION_SOURCE)
            completed = calculate_analysis_snapshot(parsed)
        self.assertEqual(stage.call_count, 2)
        canonical = synchronous.document
        self.assertIsInstance(canonical, CanonicalDocument)
        self.assertNotIn('[Hidden]', [f.span.extract(RECOGNITION_SOURCE)
                                      for f in canonical.occurrence_facts])
        for call, tree, semantics in (
                (stage.call_args_list[0], synchronous.tree, synchronous.semantics),
                (stage.call_args_list[1], parsed.tree, parsed.semantics)):
            document, actual_tree, actual_semantics = call.args
            self.assertIs(type(document), CanonicalDocument)
            self.assertIs(actual_tree, tree)
            self.assertIs(actual_semantics, semantics)
            self.assertNotIn('[Hidden]', [f.span.extract(RECOGNITION_SOURCE)
                                      for f in document.occurrence_facts])
            # Both stages shield quotes; semantic relationship authority still differs.
            reference = next(f for f in document.occurrence_facts
                             if f.span.start == RECOGNITION_SOURCE.index('[A]', RECOGNITION_SOURCE.index('Read')))
            self.assertEqual(document.relationship(reference.id, 'identity').status, 'supported')
            self.assertEqual(canonical.relationship(reference.id, 'identity').status, 'supported')
        self.assertEqual(restore_analysis(completed.snapshot).as_record(), synchronous.as_record())

    def test_parse_runs_once_and_findings_never_reparse_or_resolve(self):
        with ExitStack() as stack:
            recognition = stack.enter_context(patch.object(
                LanguageCore, 'parse_document', wraps=LanguageCore.parse_document))
            syntax = stack.enter_context(patch('AgStudio.arcgrav_language_engine.api.parse', wraps=parse))
            semantics = stack.enter_context(patch('AgStudio.arcgrav_language_engine.api.resolve', wraps=resolve))
            stack.enter_context(patch('AgStudio.shared.lint.findings.assemble_diagnostics',
                                     side_effect=AssertionError('parse ran Findings')))
            parsed = calculate_parse_snapshot(request_for(RECOGNITION_SOURCE))
        self.assertEqual((recognition.call_count, syntax.call_count, semantics.call_count), (1, 1, 1))
        expected = analyze(RECOGNITION_SOURCE)
        packed = pack_analysis(parsed)
        with ExitStack() as stack:
            for target in (
                    'AgStudio.shared.core.LanguageCore.open_source',
                    'AgStudio.shared.core.LanguageCore.parse_document',
                    'AgStudio.shared.document.model.ParsedDocument.__init__',
                    'AgStudio.shared.lint.model.CanonicalDocument.__init__',
                    'AgStudio.shared.lint.syntax.parse',
                    'AgStudio.shared.lint.semantics.resolve',
                    'AgStudio.shared.lint.parse',
                    'AgStudio.shared.lint.resolve',
                    'AgStudio.arcgrav_language_engine.api.parse',
                    'AgStudio.arcgrav_language_engine.api.resolve'):
                stack.enter_context(patch(target, side_effect=AssertionError('Findings repeated derivation')))
            for transport in (parsed, packed):
                result = calculate_analysis_snapshot(transport)
                self.assertEqual(result.snapshot.diagnostics, expected.diagnostics)
                self.assertEqual(calculate_findings_update(transport).diagnostics, expected.diagnostics)

    def test_stage_uses_one_runner_and_retains_its_suppression_records(self):
        parsed = calculate_parse_snapshot(request_for('=> - First\n=> - Second\n', configuration={'spellcheck': False}))
        document = restore_document(parsed.document)
        expected = assemble_diagnostics(document, parsed.tree, parsed.semantics)
        suppressed = (('AG-OPERATION-LIST', '1', ('unresolved_marker_spacing',)),)
        with patch('AgStudio.shared.lint.findings.evaluate_with_admission',
                   return_value=(expected.findings, suppressed)) as evaluate:
            result = assemble_diagnostics(document, parsed.tree, parsed.semantics)
        evaluate.assert_called_once_with(document, parsed.tree, parsed.semantics)
        self.assertEqual(result.findings, expected.findings)
        self.assertEqual(result.status, 'evaluated')
        self.assertEqual(result.document_id, document.document_id)
        self.assertEqual(result.suppressed_conclusions, suppressed)
        self.assertIs(result.rules, RULES)

    def test_consolidated_operation_rule_has_exact_identity_and_no_duplicates(self):
        source = ('Task:\r\n=> - Active\r\n  => - Child\n'
                  '=>  - Broader\n=>\t- Uncertain\n=> -\n- => Reverse\n'
                  '\nSource:\n"""\n=> - Literal\n"""\n\nTask: done\n')
        parsed = calculate_parse_snapshot(request_for(source, configuration={'spellcheck': False}))
        expected = [('=> - Active', '=> - '), ('=> - Child', '=> - '),
                    ('=>  - Broader', '=>  - '), ('=> -\n', '=> -'), ('- => Reverse', '- => ')]
        for result in (analyze(source, configuration={'spellcheck': False}),
                       restore_analysis(calculate_analysis_snapshot(pack_analysis(parsed)).snapshot)):
            found = [f for f in result.diagnostics.findings if f.rule_id == 'AG-OPERATION-LIST']
            self.assertEqual(len(found), len(expected))
            self.assertEqual(len({f.id for f in found}), len(expected))
            for finding, (fragment, highlighted) in zip(found, expected):
                start = source.index(fragment)
                self.assertEqual(finding.source_range.span, SourceSpan(start, start + len(highlighted)))
                self.assertEqual(finding.source_range.span.extract(source), highlighted)
                self.assertEqual(finding.id, sha256(
                    f'{result.document.document_id}:AG-OPERATION-LIST:{start}:{start + len(highlighted)}'.encode()).hexdigest())

    def test_real_cli_keeps_full_records_and_exact_ranges(self):
        source = SOURCES['unicode_crlf_spelling'] + SOURCES['recovery_and_suppression']
        for version in ('current', 'future-version'):
            with self.subTest(version=version):
                expected = analyze(source, arcgrav_version=version)
                process = subprocess.run(
                    [sys.executable, '-m', 'AgStudio.shared.cli', '--json', '--arcgrav-version', version, '-'],
                    cwd=ROOT, input=source.encode('utf-8'), capture_output=True, timeout=15,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                self.assertEqual(process.returncode, 1 if version == 'current' else 0, process.stderr)
                record = json.loads(process.stdout)['results'][0]
                self.assertEqual(record.pop('file'), '-')
                self.assertEqual(record, json.loads(json.dumps(expected.as_record())))

    @unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
    def test_gui_delivery_consumes_shared_stage_without_replacing_the_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            # Exercise the real GUI delivery boundary without starting widgets or
            # duplicate worker processes. Keep Qt out of the parent process so
            # subsequent core-only tests can enforce their import boundary.
            script = textwrap.dedent('''
                import unittest
                from unittest.mock import patch
                from AgStudio.gui.analysis import _restore_parse_result, _restore_result
                from AgStudio.shared.analysis_snapshot import (
                    calculate_findings_update, calculate_parse_snapshot, pack_analysis,
                )
                from AgStudio.shared.lint import analyze
                from AgStudio.shared.lint.findings import assemble_diagnostics
                from AgStudio.shared.panel_projections import derive_findings
                from AgStudio.shared.software_testing.test_analysis_stages import SOURCES, request_for

                check = unittest.TestCase()
                for version in ('current', 'future-version'):
                    source = SOURCES['unicode_crlf_spelling']
                    packed = pack_analysis(calculate_parse_snapshot(request_for(source, version)))
                    parsed, snapshot, _ = _restore_parse_result(packed)
                    with patch('AgStudio.shared.lint.findings.assemble_diagnostics',
                               wraps=assemble_diagnostics) as stage:
                        update = calculate_findings_update(packed)
                    check.assertEqual(stage.call_count, 1)
                    actual, completed, projection = _restore_result(update, parsed, snapshot)
                    expected = analyze(source, arcgrav_version=version)
                    check.assertEqual(actual.as_record(), expected.as_record())
                    check.assertEqual(completed.diagnostics, expected.diagnostics)
                    check.assertEqual(projection, derive_findings(expected))
                    check.assertIs(actual.document, parsed.document)
                    check.assertIs(actual.tree, parsed.tree)
                    check.assertIs(actual.semantics, parsed.semantics)
            ''')
            process = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                     capture_output=True, text=True, timeout=15, env={
                                         **os.environ, 'PYTHONDONTWRITEBYTECODE': '1',
                                         'QT_QPA_PLATFORM': 'offscreen', 'XDG_CONFIG_HOME': directory,
                                         'XDG_CACHE_HOME': directory, 'XDG_DATA_HOME': directory,
                                     })
            self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == '__main__':
    unittest.main()
