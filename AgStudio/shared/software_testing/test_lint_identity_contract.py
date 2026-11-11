"""Author-clarified first identity, symbol-body and AS export contracts."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission
from AgStudio.shared.lint.semantics import Resolution

RULE = 'AG-SYMBOL-NESTED-DECLARATION'
ROOT = Path(__file__).resolve().parents[3]


class IdentityContractTests(unittest.TestCase):
    def test_use_requires_prior_explicit_definition(self):
        a = analyze('Task:\n- Use [Findings]\n\n[Findings]: []\n- Modify [Findings]\n\nTask: value\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['reference', 'anchor', 'reference'])
        self.assertEqual([r.status for r in a.semantics.resolutions], ['forward_candidate', 'unique_prior_anchor'])
        self.assertEqual([f.rule_id for f in a.diagnostics.findings], ['AG-SYMBOL-BEFORE-DEFINITION'])
        reference = a.semantics.resolutions[0].reference
        fact = next(f for f in a.document.occurrence_facts if f.span == reference.span)
        self.assertEqual(a.document.relationship(fact.id, 'identity').status, 'untrusted')

    def test_plain_header_never_establishes_bracket_identity(self):
        a = analyze('Findings:\n- Value\n\nTask:\n- Use [Findings]\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['reference'])
        self.assertEqual([f.rule_id for f in a.diagnostics.findings], ['AG-SYMBOL-NO-LOCAL-ANCHOR'])

    def test_repeated_values_and_mutation_words_never_infer_mutability(self):
        for value in ('[]', '{}', '0', 'unset', 'ordinary text'):
            source = f'[Findings]: {value}\n[Findings]: {value}\n\nTask:\n- Read [Findings]\n- Mutate [Findings]\n'
            a = analyze(source)
            self.assertEqual([f.rule_id for f in a.diagnostics.findings], ['AG-DOCUMENT-START-SECTION', 'AG-SYMBOL-DUPLICATE-INSTANTIATION'])
            self.assertEqual([s.kind for s in a.semantics.symbols], ['anchor', 'duplicate_anchor', 'reference', 'reference'])
            self.assertFalse(any(hasattr(s, 'mutable') for s in a.semantics.symbols))

    def test_scalar_body_and_same_indent_members_cannot_introduce_symbols(self):
        for source in ('[Outer]:\n- [New]: value\n', '[Outer]:\n  [New]: value\n'):
            a = analyze(source + '\nTask: value\n')
            self.assertEqual(a.semantics.symbols[1].kind, 'reference')
            self.assertEqual(a.semantics.resolutions[0].status, 'forbidden_nested_declaration')
            self.assertEqual(a.semantics.symbols[1].body, 0)
            self.assertEqual({f.rule_id for f in a.diagnostics.findings},
                             {'AG-DOCUMENT-START-SECTION', RULE, 'AG-SYMBOL-UNUSED'})

    def test_invalid_nested_introduction_does_not_reserve_or_export_name(self):
        a = analyze('[Outer]:\n- [Local]: value\n\nTask:\n- Use [Local]\n- Use [Local]\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['anchor', 'reference', 'reference', 'reference'])
        self.assertEqual(a.semantics.resolutions[0].candidates, ())
        self.assertEqual(a.semantics.resolutions[-1].status, 'missing_local_anchor')

    def test_known_references_and_recursive_self_uses_inside_symbol_are_allowed(self):
        a = analyze('[Known]: value\n\n[Outer]:\n- Use [Known]\n=> Apply [Outer]\n\nTask: value\n')
        self.assertEqual([f.rule_id for f in a.diagnostics.findings], ['AG-DOCUMENT-START-SECTION'])
        self.assertEqual([r.status for r in a.semantics.resolutions], ['unique_prior_anchor'] * 2)

    def test_plain_section_occurrences_do_not_create_body_for_following_peers(self):
        a = analyze('Task:\n- Use [A]\n- Use [B] ↳\n  - Use [C]\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['reference'] * 3)
        self.assertEqual([s.body for s in a.semantics.symbols], [None] * 3)
        self.assertEqual([f.rule_id for f in a.diagnostics.findings], ['AG-SYMBOL-NO-LOCAL-ANCHOR'] * 3)

    def test_nested_plain_section_keeps_outer_symbol_body(self):
        a = analyze('[Outer]:\n  Context:\n  - Use [New]\n\nTask:\n- Use [Later]\n')
        self.assertEqual(a.semantics.symbols[1].body, 0)
        self.assertEqual(a.semantics.symbols[-1].kind, 'reference')
        self.assertIsNone(a.semantics.symbols[-1].body)

    def test_as_inside_symbol_exports_after_declaration(self):
        for prefix in ('', '  '):
            a = analyze('[Process]:\n' + prefix + '=> Collect records AS [Candidates]\n\nTask:\n- Use [Candidates]\n')
            self.assertEqual([s.kind for s in a.semantics.symbols], ['anchor', 'alias', 'reference'])
            self.assertEqual(a.semantics.resolutions[-1].status, 'unique_prior_alias')
            self.assertEqual(a.semantics.resolutions[-1].candidates, (a.semantics.symbols[1].span,))
            self.assertEqual([f.rule_id for f in a.diagnostics.findings], ['AG-SYMBOL-UNUSED', 'AG-DOCUMENT-START-SECTION'])

    def test_same_line_alias_does_not_retroactively_bind_earlier_body_use(self):
        a = analyze('[Process]:\n=> Use [R] AS [R]\n\nTask:\n- Use [R]\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['anchor', 'reference', 'alias', 'reference'])
        self.assertEqual(a.semantics.resolutions[0].status, 'forward_candidate')
        self.assertEqual(a.semantics.resolutions[-1].status, 'unique_prior_alias')
        self.assertEqual(len(a.diagnostics.findings), 3)
        self.assertIn('AG-SYMBOL-UNUSED', [f.rule_id for f in a.diagnostics.findings])

    def test_same_line_prior_outside_occurrence_retains_identity_through_as(self):
        a = analyze('Task:\n- Use [R] AS [R]\n- More AS [R]\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['reference', 'alias', 'duplicate_alias'])
        self.assertEqual([f.rule_id for f in a.diagnostics.findings],
                         ['AG-SYMBOL-BEFORE-DEFINITION', 'AG-SYMBOL-UNUSED', 'AG-ALIAS-DUPLICATE-INSTANTIATION'])
        self.assertEqual([r.status for r in a.semantics.resolutions],
                         ['forward_candidate', 'duplicate_alias_instantiation'])

    def test_literal_quoted_and_uncertain_names_do_not_declare(self):
        a = analyze('Source:\n"""\n[A]: [B]\nGet AS [C]\n"""\n\nTask:\n- "[D]"\n- [État]\n- [A]\n- [A]\n')
        self.assertEqual([(s.name, s.kind) for s in a.semantics.symbols],
                         [('A', 'reference'), ('A', 'reference')])
        self.assertEqual([f.rule_id for f in a.diagnostics.findings],
                         ['AG-QUOTED-ELEMENT-NO-MATCH', 'AG-SYNTAX-INCOMPLETE',
                          'AG-SYMBOL-NO-LOCAL-ANCHOR', 'AG-SYMBOL-NO-LOCAL-ANCHOR'])

    def test_recovery_cannot_establish_accidental_new_identities(self):
        a = analyze('[Outer]:\n - Broken [A]\n- Use [B]\n\nTask:\n- Use [B]\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['anchor', 'uncertain', 'uncertain', 'reference'])

    def test_admission_rejects_forged_body_or_known_identity(self):
        a = analyze('[Known]: value\n\n[Outer]:\n- Use [Known]\n')
        reference = a.semantics.resolutions[-1].reference
        forged_semantics = replace(a.semantics, resolutions=(Resolution(reference, (), 'forbidden_nested_declaration', 'fake'),))
        candidate = Candidate(RULE, reference.span, reference.node, 'fake', ('forbidden_nested_declaration',))
        self.assertIn('prior_identity_exists', admission(candidate, a.document, a.tree, forged_semantics))
        outside = analyze('[A]\n[A]\n')
        reference = outside.semantics.resolutions[0].reference
        candidate = replace(candidate, span=reference.span, node_id=reference.node)
        self.assertIn('missing_nested_introduction_evidence', admission(candidate, outside.document, outside.tree, outside.semantics))

    def test_retired_rebinding_ids_stay_retired(self):
        retired = frozenset(('AG-SYMBOL-REBINDING', 'AG-ALIAS-REBINDING'))
        self.assertTrue(retired.isdisjoint(REGISTRY))
        a = analyze('[A]: first\n[A]: second')
        self.assertTrue(retired.isdisjoint({rule.id for rule in a.diagnostics.rules}))
        self.assertTrue(retired.isdisjoint({f.rule_id for f in a.diagnostics.findings}))
        duplicate = a.semantics.symbols[-1]
        for rule_id in retired:
            self.assertNotIn(rule_id, REGISTRY)
            candidate = Candidate(rule_id, duplicate.span, duplicate.node,
                                  'obsolete', ())
            self.assertIn('unknown_rule',
                          admission(candidate, a.document, a.tree, a.semantics))

    def test_duplicate_instantiation_rule_ids_are_active_and_evidence_gated(self):
        for source, rule in (('[A]: one\n[A]: two', 'AG-SYMBOL-DUPLICATE-INSTANTIATION'),
                             ('Collect AS [A]\nAgain AS [A]', 'AG-ALIAS-DUPLICATE-INSTANTIATION')):
            with self.subTest(rule=rule):
                a = analyze(source)
                finding = next(f for f in a.diagnostics.findings if f.rule_id == rule)
                node = next(n for n in a.tree.nodes
                            if n.span.start <= finding.source_range.span.start < n.span.end)
                candidate = Candidate(rule, finding.source_range.span, node.id,
                                      'test', REGISTRY[rule].required_evidence)
                self.assertEqual(admission(candidate, a.document, a.tree, a.semantics), ())
                self.assertTrue(admission(replace(candidate, evidence=()), a.document,
                                          a.tree, a.semantics))

    def test_semantic_evidence_does_not_rescan_declaration_text(self):
        from types import SimpleNamespace
        from AgStudio.shared.lint.rules import _semantic_evidence

        class UnneededSymbols:
            def __iter__(self):
                raise AssertionError('independent semantic-resolution scan')

        evidence = SimpleNamespace(symbols=UnneededSymbols(), resolutions=(), bindings=())
        self.assertEqual(_semantic_evidence(evidence), ({}, set()))
        self.assertEqual(_semantic_evidence(None), ({}, set()))

    def test_property_and_external_contents_are_not_resolved_or_loaded(self):
        with patch('builtins.open', side_effect=AssertionError('external read')), \
             patch('socket.create_connection', side_effect=AssertionError('external network')):
            a = analyze('[Local]: value\n\nTask:\n- Read [Local].outer\nImport:\n- https://example.invalid/context\n')
        self.assertEqual(a.semantics.resolutions[0].status, 'unique_prior_anchor')
        self.assertEqual([s.name for s in a.semantics.symbols], ['Local', 'Local'])
        self.assertEqual(a.conformance, 'unknown')

    def test_cli_and_gui_project_same_clarified_identity_diagnostics(self):
        from PySide6.QtWidgets import QApplication
        from AgStudio.gui.app import DocumentTab
        source = '[Outer]:\r\n- 🌍 [New]\r\n=> Collect AS [Exported]\r\n\nTask:\r\n- Use [Exported]\r\n'
        expected = analyze(source)
        process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '-'], input=source.encode(),
                                 cwd=ROOT, capture_output=True, timeout=15)
        record = json.loads(process.stdout)['results'][0]
        record.pop('file')
        self.assertEqual(record, json.loads(json.dumps(expected.as_record())))
        self.assertEqual({f.rule_id for f in expected.diagnostics.findings},
                         {'AG-DOCUMENT-START-SECTION', 'AG-SYMBOL-UNUSED',
                          'AG-SYMBOL-NO-LOCAL-ANCHOR'})
        app = QApplication.instance() or QApplication([])
        tab = DocumentTab('current', source, map_enabled=False)
        try:
            self.assertEqual(tab.analysis.as_record(), expected.as_record())
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 3)
            row = next(tab.diagnostic_list.topLevelItem(i)
                       for i in range(tab.diagnostic_list.topLevelItemCount())
                       if tab.diagnostic_list.topLevelItem(i).text(1) == 'AG-SYMBOL-NO-LOCAL-ANCHOR')
            tab._navigate_finding(row)
            cursor = tab.editor.textCursor()
            self.assertEqual(cursor.selectedText(), '[New]')
            self.assertEqual(cursor.blockNumber(), 1)
            self.assertEqual(cursor.selectionStart() - cursor.block().position(), 5)
            self.assertEqual(cursor.selectionEnd() - cursor.block().position(), 10)
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

    def test_line_local_root_bracket_recovery_does_not_poison_later_identity(self):
        a = analyze('[Open\n[A]: value\nUse [A]\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['anchor', 'reference'])
        self.assertEqual(a.semantics.resolutions[0].status, 'unique_prior_anchor')

    def test_colonless_symbol_parent_is_uncertain_without_leaking_declaration(self):
        for parent in ('[A]', '- [A]'):
            a = analyze(parent + '\n  - [B]\n\nTask:\n- [B]\n')
            self.assertEqual([s.kind for s in a.semantics.symbols], ['reference', 'uncertain', 'reference'])
            self.assertNotIn(RULE, [f.rule_id for f in a.diagnostics.findings])
        a = analyze('Task:\n- Use [A] ↳\n  - [B]\n')
        self.assertEqual([s.kind for s in a.semantics.symbols], ['reference', 'reference'])
