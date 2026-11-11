"""Independent guide fixtures for extended analysis and CLI contracts."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import RULES

ROOT = Path(__file__).resolve().parents[3]


class LintPipelineTests(unittest.TestCase):
    def ids(self, source):
        # Fragment fixtures isolate local syntax; document completion has its own gate.
        return [f.rule_id for f in analyze(source).diagnostics.findings
                if f.rule_id not in {'AG-DOCUMENT-END-SECTION', 'AG-DOCUMENT-START-SECTION'}]

    def test_lossless_lexer_and_deterministic_output(self):
        source = '[A]: 🌍\r\n""""\r\n"""\r\n=> - [Fake]\r\n"""\r\n""""\r\n=> Apply [A]\r\n'
        result = analyze(source)
        self.assertEqual(''.join(t.span.extract(source) for t in result.tree.tokens), source)
        self.assertEqual(result, analyze(source))
        self.assertEqual(result.as_record(), analyze(source).as_record())
        self.assertEqual(self.ids(result.document.source), [])
        self.assertEqual([r.reference.name for r in result.semantics.resolutions], ['A'])
        self.assertTrue(any(t.kind == 'literal' for t in result.tree.tokens))

    def test_literal_tree_keeps_section_owner_and_body_containment(self):
        result = analyze('[Source]:\n"""\nbody\n\n"""\n')
        nodes = result.tree.nodes
        self.assertEqual(nodes[1].section, 0)
        for node in nodes[2:]:
            self.assertEqual(node.parent, 1)
            self.assertEqual(node.section, 0)
        self.assertEqual([f.rule_id for f in result.diagnostics.findings],
                         ['AG-SYMBOL-UNUSED', 'AG-DOCUMENT-END-SECTION', 'AG-DOCUMENT-START-SECTION'])

    def test_guide_marker_matrix(self):
        for source in ['- => Act', '=> 1. Act', '1. => Act', 'P0. => Act', '=> P0. Act', '=>  - Act']:
            with self.subTest(source=source):
                findings = [f for f in analyze(source).diagnostics.findings
                            if f.rule_id not in {'AG-DOCUMENT-END-SECTION', 'AG-DOCUMENT-START-SECTION'}]
                self.assertEqual(len(findings), 1)
                self.assertEqual((findings[0].rule_id, findings[0].severity),
                                 ('AG-OPERATION-LIST', 'error'))
        self.assertEqual(self.ids('=> - Act'), ['AG-OPERATION-LIST'])
        for source in ['=> Compare x - y', 'Task:\n1. One\n3. Three', 'Constraint:\nP0. One\nP0. Two',
                       'Scope: C:\\Project', '"""\n- => Literal\n"""', '  => Act']:
            with self.subTest(source=source):
                self.assertEqual(self.ids(source), [])
        self.assertEqual(self.ids('- 1. Act'), ['AG-LIST-MIXED'])

    def test_indentation_and_bounded_recovery(self):
        self.assertEqual(self.ids('   - Odd'), ['AG-INDENT-WIDTH'])
        self.assertEqual(self.ids(' \t- Mixed'), ['AG-INDENT-MIXED'])
        result = analyze('[Open\n=>\n=> - Act\n')
        self.assertEqual([f.rule_id for f in result.diagnostics.findings],
                         ['AG-DOCUMENT-START-SECTION', 'AG-SYNTAX-INCOMPLETE', 'AG-OPERATION-INCOMPLETE', 'AG-OPERATION-LIST',
                          'AG-DOCUMENT-END-SECTION'])
        self.assertEqual(result.document.recoveries[0].resume_at, len('[Open\n'))
        self.assertEqual(self.ids('"""\n=> - Act\n[Missing]\n'), ['AG-LITERAL-UNCLOSED'])
        self.assertEqual(self.ids('""""\n"""\n=> - Act\n'), ['AG-LITERAL-UNCLOSED'])

    def test_sections_and_containment_are_separate(self):
        result = analyze('[A]:\n- Value\n[B]:\n=> Transform [A] ↳\n  - Child\n')
        nodes = result.tree.nodes
        self.assertEqual(nodes[1].section, 0)
        self.assertIsNone(nodes[1].parent)
        self.assertEqual(nodes[3].section, 2)
        self.assertEqual(nodes[4].parent, 3)
        self.assertEqual([f.rule_id for f in result.diagnostics.findings], ['AG-DOCUMENT-START-SECTION', 'AG-BLOCK-SEPARATOR', 'AG-SYMBOL-UNUSED', 'AG-DOCUMENT-END-SECTION'])
        self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_anchor')

    def test_anchor_resolution_cross_section_recursion_and_forward_use(self):
        for source in ['[A]: value\n\nTask:\n- Use [A]', '[Traverse]:\n=> Apply [Traverse]']:
            result = analyze(source)
            self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_anchor')
            self.assertEqual(self.ids(result.document.source), [])
        self.assertEqual(self.ids('A: value\n- Use [A]'), ['AG-SYMBOL-NO-LOCAL-ANCHOR'])
        self.assertEqual(self.ids('- Use [A]\n[A]: value'), ['AG-SYMBOL-BEFORE-DEFINITION', 'AG-SYMBOL-UNUSED'])
        for value in ['0', '{}', '[]', 'unset']:
            self.assertEqual(self.ids('- Use [A]\n[A]: ' + value), ['AG-SYMBOL-BEFORE-DEFINITION', 'AG-SYMBOL-UNUSED'])

    def test_alias_target_not_reference_and_same_line_order(self):
        result = analyze('Collect records AS [R]\n- Use [R]')
        self.assertEqual([s.kind for s in result.semantics.symbols], ['alias', 'reference'])
        self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_alias')
        self.assertEqual(self.ids(result.document.source), [])
        self.assertEqual(self.ids('Use [R] AS [R]'), ['AG-SYMBOL-BEFORE-DEFINITION', 'AG-SYMBOL-UNUSED'])
        result = analyze('Collect records AS [R]\nCollect more AS [R]')
        self.assertEqual(self.ids(result.document.source), ['AG-SYMBOL-UNUSED', 'AG-ALIAS-DUPLICATE-INSTANTIATION'])
        self.assertEqual(result.semantics.resolutions[-1].status, 'duplicate_alias_instantiation')

    def test_mutability_nested_scope_and_non_ascii_names_not_invented(self):
        result = analyze('[A]: []\n[A]: {}\n- Use [A]')
        self.assertEqual(len(result.semantics.symbols), 3)
        self.assertEqual(self.ids(result.document.source), ['AG-SYMBOL-DUPLICATE-INSTANTIATION'])
        self.assertEqual([r.status for r in result.semantics.resolutions],
                         ['duplicate_symbol_instantiation', 'unique_prior_anchor'])
        result = analyze('Parent:\n  [A]: value\n- Use [A]\n[État]: valeur')
        self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_anchor')
        self.assertEqual([s.name for s in result.semantics.symbols], ['A', 'A'])
        self.assertIn('AG-SYNTAX-INCOMPLETE', self.ids(result.document.source))
        self.assertFalse(any(value.startswith('CORE-GAP-') for value in result.unresolved))
        self.assertEqual(result.conformance, 'unknown')

    def test_binder_owns_expression_not_symbol(self):
        result = analyze('[A]: value\n=> Act [A] ↳\n  - Child')
        binding = result.semantics.bindings[0]
        self.assertEqual(binding.owner.extract(result.document.source), '=> Act [A] ↳\n')
        self.assertEqual(binding.children, (2,))
        self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_anchor')
        self.assertEqual(self.ids(result.document.source), [])
        self.assertEqual(self.ids('=> Act ↳\n- Peer'), ['AG-BINDING-CHILD'])

    def test_every_rule_has_executable_fixture_and_local_evidence(self):
        cases = ['[A]:\n- `parent`:\n  - `child`\n  - Use `child`\n- Use `parent`', '[A]:\n- Use `item`\n- `item`\n- Read [A].missing\n\n[B]:\n- `item`', '"""\n""""\n"""', 'First: value\nSecond: value', '- Parent\n  - Child', '- Done.', '[A]↳', '- Trailing ', '[Empty]:', '- `two words`', '- => Act', '- 1. Act', '   - Act', ' \t- Act', '"""\ntext', '[Open', '=>',
                 '[A]\n[A]: value', '[Missing]', '[A]: 0\n[A]: 1', 'Get AS [A]\nGet AS [A]', '=> Act ↳',
                 '- Derive from [A]:\n  - Child', '1. Parent\n  1. Child',
                 'Empty:', 'Scope:\n    - Child', 'AS [Alias]', '-', '=> => Act', '*', '[Outer]:\n- [New]: value']
        cases.append('[A]:\n- `item`\n\n[B]:\n- `item`\n\n[C]:\n1. Inspect:\n  - `item`')
        cases.append('[A]:\n- Check `neverDefined` exists\n')  # AG-MEMBER-UNDEFINED
        cases.append('- Please recieve the document')
        cases.append('Task: "unmatched"\n')
        cases.append('Task: "This line contains a "double" quote within it"\n')
        findings = [f for source in cases for f in analyze(source).diagnostics.findings]
        with mock.patch('AgStudio.shared.lint.spelling._CHECKER', None):
            findings.extend(analyze('- Ordinary prose').diagnostics.findings)
        self.assertEqual({r.id for r in RULES}, {f.rule_id for f in findings})
        for finding in findings:
            self.assertEqual(finding.evidence.contract_version, 'current')
            self.assertTrue(finding.evidence.syntax_id.startswith('syntax.'))
            self.assertTrue(finding.evidence.premises)
            self.assertTrue(finding.suppression_prerequisites)

    def test_ranges_versions_and_no_external_actions(self):
        source = '[A]: 🌍\r\n  - => Act\r\n'
        with (mock.patch('builtins.open', side_effect=AssertionError('I/O')),
              mock.patch('subprocess.run', side_effect=AssertionError('execution')),
              mock.patch('socket.create_connection', side_effect=AssertionError('network'))):
            result = analyze(source)
        finding = next(f for f in result.diagnostics.findings if f.rule_id == 'AG-OPERATION-LIST')
        self.assertEqual(finding.source_range.start.line, 2)
        self.assertEqual(finding.source_range.start.column, 3)
        self.assertEqual(finding.source_range.span.extract(source), '- => ')
        other = analyze(source, arcgrav_version='unknown')
        self.assertEqual(other.diagnostics.findings, ())
        self.assertEqual(other.diagnostics.rules, ())

    def test_cli_parity_exit_codes_encoding_and_io_errors(self):
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.arc'
            source = '[A]: 🌍\r\n- => Act\r\n'
            path.write_bytes(source.encode('utf-8-sig'))
            def run(*args):
                return subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', *args],
                                      cwd=ROOT, env=env, capture_output=True, text=True)
            process = run(str(path))
            self.assertEqual(process.returncode, 1, process.stderr)
            record = json.loads(process.stdout)['results'][0]
            expected = json.loads(json.dumps(analyze(source).as_record()))
            self.assertEqual({k: v for k, v in record.items() if k != 'file'}, expected)
            self.assertEqual(run('--fail-on', 'never', str(path)).returncode, 0)
            path.write_text('[Outer]:\n- [Missing]')
            self.assertEqual(run(str(path)).returncode, 1)
            self.assertEqual(run('--fail-on', 'warning', str(path)).returncode, 1)
            path.write_bytes(b'\xff')
            self.assertEqual(run(str(path)).returncode, 2)
            self.assertEqual(run(str(path) + '.missing').returncode, 2)


if __name__ == '__main__':
    unittest.main()
