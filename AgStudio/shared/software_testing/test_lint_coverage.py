"""Guide-backed coverage additions; uncertainty is an asserted result."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission
from AgStudio.shared.recognition import SourceSpan


class GuideCoverageTests(unittest.TestCase):
    CASES = {
        'AG-SECTION-EMPTY': ('Empty:\r\n', ':'),
        'AG-INDENT-JUMP': ('Scope:\n    - Child\n', '    '),
        'AG-ALIAS-SOURCE': ('AS [Alias]\n', 'AS'),
        'AG-LIST-EMPTY': ('P0.\n', 'P0.'),
        'AG-OPERATION-MULTIPLE': ('=> => Work\n', '=> =>'),
        'AG-WILDCARD-BARE': ('- *\n', '*'),
    }

    def test_exact_ranges_and_independent_admission(self):
        for rule_id, (source, text) in self.CASES.items():
            with self.subTest(rule=rule_id):
                a = analyze(source)
                finding = next(f for f in a.diagnostics.findings if f.rule_id == rule_id)
                self.assertEqual(finding.source_range.span.extract(source), text)
                node = next(n for n in a.tree.nodes if n.span.start <= finding.source_range.span.start < n.span.end)
                candidate = Candidate(rule_id, finding.source_range.span, node.id, 'untrusted', REGISTRY[rule_id].required_evidence)
                self.assertEqual(admission(candidate, a.document, a.tree, a.semantics), ())
                self.assertTrue(admission(replace(candidate, evidence=()), a.document, a.tree, a.semantics))
                safe = analyze('Context: Value\n')
                fabricated = replace(candidate, span=SourceSpan(0, 1), node_id=0)
                self.assertIn('unsupported_structural_evidence', admission(fabricated, safe.document, safe.tree, safe.semantics))

    def test_empty_sections_accept_physical_members_children_and_literals(self):
        for source in ('Scope:\n- A\n', 'Scope:\n  - A\n', 'Scope:\n"""\n\n"""\n',
                       'Scope:\nNatural prose\n', 'Scope: C:\\Project\n', 'Scope:\n - Malformed child\n'):
            with self.subTest(source=source):
                self.assertNotIn('AG-SECTION-EMPTY', [f.rule_id for f in analyze(source).diagnostics.findings])
        self.assertIn('AG-SECTION-EMPTY', [f.rule_id for f in analyze('Scope:\n\nTask: Act\n').diagnostics.findings])

    def test_indentation_jump_requires_adjacent_clear_parent_context(self):
        for source in ('    - Partial fragment\n', 'Scope:\n  - Child\n', 'Scope:\n \t- Unclear\n    - Child\n'):
            self.assertNotIn('AG-INDENT-JUMP', [f.rule_id for f in analyze(source).diagnostics.findings])

    def test_alias_missing_source_does_not_create_identity(self):
        for source in ('AS [Name]', '- AS [Name]', '=> AS [Name]', 'Context: AS [Name]'):
            a = analyze(source)
            self.assertIn('AG-ALIAS-SOURCE', [f.rule_id for f in a.diagnostics.findings])
            self.assertEqual(a.semantics.symbols[-1].kind, 'uncertain')
        self.assertNotIn('AG-ALIAS-SOURCE', [f.rule_id for f in analyze('Read AS [Name] ↳').diagnostics.findings])

    def test_operation_prose_and_unknown_markers_are_not_reinterpreted(self):
        for source in ('=> Describe a => b', '01.', 'P00.', '0.', '=>\t=> Act'):
            ids = [f.rule_id for f in analyze(source).diagnostics.findings]
            self.assertNotIn('AG-OPERATION-MULTIPLE', ids)
            self.assertNotIn('AG-LIST-EMPTY', ids)

    def test_bare_wildcard_is_only_a_possible_breadth_warning(self):
        for source in ('Scope:\n- *', 'Root:\n  - *', '- src/*', '- "*"'):
            self.assertNotIn('AG-WILDCARD-BARE', [f.rule_id for f in analyze(source).diagnostics.findings])
        finding = next(f for f in analyze('*').diagnostics.findings if f.rule_id == 'AG-WILDCARD-BARE')
        self.assertEqual(finding.severity, 'warning')
        self.assertIn('unknown', finding.message)

    def test_new_checks_are_inert_inside_literal_source_and_quotes(self):
        payload = '\n'.join(source for source, _ in self.CASES.values())
        for source in ('Source:\n"""\n' + payload + '\n"""\n', '- "AS [Name] => => *"\n'):
            self.assertFalse(set(self.CASES) & {f.rule_id for f in analyze(source).diagnostics.findings})

    def test_list_prefixed_nested_introductions_do_not_establish_identity(self):
        a = analyze('[People]:\n- [Alice]:\n  - Role: Owner\nTask:\n- Use [Alice]\n')
        alice = [s for s in a.semantics.symbols if s.name == 'Alice']
        self.assertEqual([s.kind for s in alice], ['reference', 'reference'])
        self.assertEqual(a.semantics.resolutions[0].status, 'forbidden_nested_declaration')
        self.assertIn('AG-SYMBOL-NO-LOCAL-ANCHOR', [f.rule_id for f in a.diagnostics.findings])

    def test_analysis_does_not_read_execute_import_or_expand_source(self):
        with patch('builtins.open', side_effect=AssertionError('document-triggered I/O')), \
             patch('subprocess.run', side_effect=AssertionError('document-triggered execution')), \
             patch('glob.glob', side_effect=AssertionError('document-triggered expansion')):
            a = analyze('Import:\n- https://example.invalid/secret\nScope:\n- /etc/*\nTask:\n=> Execute rm -rf /\n')
        self.assertEqual(a.conformance, 'unknown')

    def test_unsupported_version_admits_no_additional_checks(self):
        for source, _ in self.CASES.values():
            self.assertEqual(analyze(source, arcgrav_version='future').diagnostics.findings, ())
