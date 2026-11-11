"""Regression gates for one typed syntax/semantic model and rule admission."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, admission
from AgStudio.shared.recognition import SourceSpan
from AgStudio.shared.highlighting import highlight_tokens
from AgStudio.gui.structure import outline_entries


class CanonicalLinterTests(unittest.TestCase):
    def test_ambiguous_declarations_never_become_anchors(self):
        for first in ('AS [A]', '- AS [A]', '=> AS [A]', '[A]:: broken', '[A]:=> broken',
                      'Get AS [A] ↳\n  - Child'):
            with self.subTest(first=first):
                result = analyze(first + '\n- Use [A]')
                self.assertEqual(result.semantics.symbols[0].kind, 'uncertain')
                self.assertEqual(result.semantics.symbols[-1].kind, 'reference')
                self.assertEqual([r.status for r in result.semantics.resolutions], ['uncertain_identity'])
                self.assertFalse(any(f.rule_id == 'AG-BINDING-CHILD' for f in result.diagnostics.findings))

    def test_unicode_physical_line_endings_have_same_semantics(self):
        for newline in ('\n', '\r', '\r\n', '\v', '\f', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029'):
            with self.subTest(newline=newline):
                result = analyze('Get AS [A]' + newline + '- Use [A]' + newline + '=>' + newline)
                self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_alias')
                findings = result.diagnostics.findings
                self.assertEqual([f.rule_id for f in findings], ['AG-DOCUMENT-START-SECTION', 'AG-DOCUMENT-END-SECTION', 'AG-OPERATION-INCOMPLETE'])
                self.assertEqual(findings[-1].source_range.start.line, 3)

    def test_quoted_scalars_are_inert_typed_values(self):
        source = '[Text]: "[Missing] AS [False] ↳ *"\n\nTask:\n- Use [Text]'
        result = analyze(source)
        self.assertEqual([f.rule_id for f in result.diagnostics.findings],
                         ['AG-DOCUMENT-START-SECTION', 'AG-QUOTED-ELEMENT-NO-MATCH'])
        self.assertEqual([s.name for s in result.semantics.symbols], ['Text', 'Text'])
        self.assertTrue(any(t.kind == 'quoted_scalar' for t in result.tree.tokens))
        literal = next(t for t in highlight_tokens(result.document) if t.role == 'double_quote_content')
        self.assertIn('[Missing]', literal.span.extract(source))
        self.assertFalse(any(f.span.extract(source) == '[Missing]' for f in result.document.occurrence_facts))

    def test_tree_drives_outline_and_identity(self):
        result = analyze('[A]: value\nTask:\n- Use [A]\nWork using [A] ↳\n  - Child')
        doc = result.document
        self.assertIs(doc.syntax, result.tree)
        self.assertIs(doc.semantics, result.semantics)
        self.assertFalse(any(f.rule_id == 'AG-BINDING-CHILD' for f in result.diagnostics.findings))
        child = next(f for f in doc.structural_facts if '- Child' in f.span.extract(doc.source))
        parent = doc.relationship(child.id, 'containment')
        self.assertEqual(parent.status, 'supported')
        self.assertIn('Work using', doc.fact(parent.target_fact_id).span.extract(doc.source))
        ref = next(f for f in doc.occurrence_facts if f.span == result.semantics.resolutions[0].reference.span)
        identity = doc.relationship(ref.id, 'identity')
        self.assertEqual(identity.status, 'supported')
        self.assertEqual(doc.fact(identity.target_fact_id).span.extract(doc.source), '[A]')
        self.assertTrue(any(e.fact_id == child.id and e.containment.status == 'supported' for e in outline_entries(doc)))
        self.assertEqual(doc.relationship(child.id, 'containment').status, 'supported')

    def test_complete_prefix_chains_and_uncertain_numeric_forms(self):
        for source in ('- - => Act', '=> => - Act'):
            self.assertIn('AG-OPERATION-LIST', [f.rule_id for f in analyze(source).diagnostics.findings])
        for source in ('=> 000. Act', '=> P00. Act', '=> 0. Act'):
            result = analyze(source)
            self.assertEqual([f.rule_id for f in result.diagnostics.findings], ['AG-DOCUMENT-END-SECTION', 'AG-DOCUMENT-START-SECTION'])
            self.assertTrue(result.diagnostics.suppressed_conclusions)
            self.assertIn('unresolved_numeric_form', result.diagnostics.suppressed_conclusions[0][2])

    def test_admission_rejects_invented_semantic_or_literal_evidence(self):
        result = analyze('"[Hidden]"\n[A]: value\n- Use [A]')
        fake = Candidate('AG-SYMBOL-NO-LOCAL-ANCHOR', SourceSpan(1, 9), 0, 'fake', ('missing_local_anchor',))
        blockers = admission(fake, result.document, result.tree, result.semantics)
        self.assertIn('literal_source', blockers)
        self.assertIn('missing_semantic_resolution', blockers)
        ref = result.semantics.resolutions[0].reference
        fake = replace(fake, span=ref.span, node_id=ref.node)
        self.assertIn('missing_semantic_resolution', admission(fake, result.document, result.tree, result.semantics))
        wrong = replace(fake, span=SourceSpan(0, len(result.document.source) + 1))
        self.assertIn('imprecise_range', admission(wrong, result.document, result.tree, result.semantics))

    def test_admission_rechecks_lexical_evidence_and_spacing(self):
        result = analyze('Ordinary prose')
        for rule, evidence in [('AG-INDENT-WIDTH', 'active_indentation'),
                               ('AG-OPERATION-INCOMPLETE', 'bare_operation'),
                               ('AG-LITERAL-UNCLOSED', 'unclosed_literal'),
                               ('AG-SYNTAX-INCOMPLETE', 'malformed_symbol')]:
            candidate = Candidate(rule, SourceSpan(0, 1), 0, 'fake', (evidence,))
            self.assertTrue(admission(candidate, result.document, result.tree, result.semantics))
        for source in ('=>\t- Act', '\t=> - Act'):
            result = analyze(source)
            self.assertFalse(any(f.rule_id == 'AG-OPERATION-LIST' for f in result.diagnostics.findings))
            self.assertTrue(result.diagnostics.suppressed_conclusions)

    def test_lexer_does_not_depend_on_presentation(self):
        with patch('AgStudio.shared.highlighting.highlight_tokens', side_effect=AssertionError('presentation is not grammar')):
            result = analyze('[A]: value\n=> Apply [A]\n\nTask: value\n')
        self.assertEqual([f.rule_id for f in result.diagnostics.findings], ['AG-DOCUMENT-START-SECTION'])
        self.assertIn('symbol', [t.kind for t in result.tree.tokens])
        self.assertIn('operation', [t.kind for t in result.tree.tokens])


if __name__ == '__main__':
    unittest.main()
