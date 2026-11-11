"""Explicit definitions precede uses, including same-line alias ordering."""
import unittest
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission

FORWARD = 'AG-SYMBOL-BEFORE-DEFINITION'
MISSING = 'AG-SYMBOL-NO-LOCAL-ANCHOR'


class DefinitionOrderTests(unittest.TestCase):
    def errors(self, source):
        return [(f.rule_id, f.source_range.span.extract(source), f.source_range.start.line)
                for f in analyze(source).diagnostics.findings if f.severity == 'error']

    def test_definition_before_use_and_undefined_repeated_uses(self):
        self.assertEqual(self.errors('[Message]: []\nUse [Message]'), [])
        self.assertEqual(self.errors('Use [Message]\n[Message]: []'), [(FORWARD, '[Message]', 1), ('AG-SYMBOL-UNUSED', '[Message]', 2)])
        self.assertEqual(self.errors('Use [Missing]\nUse [Missing]'), [(MISSING, '[Missing]', 1), (MISSING, '[Missing]', 2)])
        self.assertEqual(self.errors('Message: value\nUse [Message]'), [(MISSING, '[Message]', 2)])

    def test_alias_order_export_and_existing_identity(self):
        self.assertEqual(self.errors('Create AS [Result]\nUse [Result]'), [])
        self.assertEqual(self.errors('Use [Result] AS [Result]\nUse [Result]'), [(FORWARD, '[Result]', 1)])
        self.assertEqual(self.errors('[Outer]:\nCreate AS [Result]\nTask:\nUse [Result]'),
                         [('AG-SYMBOL-UNUSED', '[Outer]', 1)])
        result = analyze('[Result]: value\n[Outer]:\nCreate AS [Result]\nTask:\nUse [Result]')
        self.assertTrue(all(r.candidates == (result.semantics.symbols[0].span,) for r in result.semantics.resolutions))
        self.assertEqual(self.errors('Use [A]\n[A]: 1\n[A]: 2\nUse [A]'),
                         [(FORWARD, '[A]', 1), ('AG-SYMBOL-DUPLICATE-INSTANTIATION', '[A]', 3)])

    def test_opaque_and_invalid_definitions_cannot_satisfy_references(self):
        for text in ('"[A]: value"', '`[A]: value`', '"""\n[A]: value\n"""'):
            self.assertEqual(self.errors(text + '\nUse [A]')[-1][:2], (MISSING, '[A]'))
        self.assertEqual(self.errors('[Outer]:\n- [Bad]: value\nTask:\nUse [Bad]'),
                         [('AG-SYMBOL-UNUSED', '[Outer]', 1),
                           ('AG-SYMBOL-NESTED-DECLARATION', '[Bad]', 2), (MISSING, '[Bad]', 4)])
        self.assertFalse(any(f.rule_id in (FORWARD, MISSING) for f in analyze('[A]:: uncertain\nUse [A]').diagnostics.findings))

    def test_exact_range_and_admission(self):
        result = analyze('🌍 Use [A]\r\n[A]: value')
        finding = next(f for f in result.diagnostics.findings if f.rule_id == FORWARD)
        self.assertEqual(finding.source_range.start.column, 7)
        candidate = Candidate(FORWARD, finding.source_range.span, 0, 'untrusted', REGISTRY[FORWARD].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        missing = analyze('🌍 Use [A]')
        self.assertIn('missing_semantic_resolution', admission(candidate, missing.document, missing.tree, missing.semantics))
