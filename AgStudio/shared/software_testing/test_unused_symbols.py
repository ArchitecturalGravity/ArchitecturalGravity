"""Required later references, independent identity checks and duplicate declarations."""
from dataclasses import replace
import unittest
from unittest.mock import patch
from AgStudio.shared.lint import rules
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission

RULE = 'AG-SYMBOL-UNUSED'


class UnusedSymbolTests(unittest.TestCase):
    def unused(self, source):
        result = analyze(source)
        return [f.source_range.span.extract(source) for f in result.diagnostics.findings if f.rule_id == RULE]

    def test_explicit_anchors_aliases_and_exact_ranges(self):
        self.assertEqual(self.unused('[Unused]: value'), ['[Unused]'])
        self.assertEqual(self.unused('=> Collect AS [Result]'), ['[Result]'])
        self.assertEqual(self.unused('[Outer]:\n=> Collect AS [Result]\nTask:\n- Use [Outer]'), ['[Result]'])
        self.assertFalse(self.unused('[Outer]:\n=> Collect AS [Result]\nTask:\n- Use [Result] and [Outer]'))
        self.assertFalse(self.unused('Read [Implicit]'))

    def test_declaring_is_not_using_and_literals_are_opaque(self):
        for suffix in ('\nText: "[A]"', '\nText: `[A]`', '\n"""\n[A]\n"""'):
            self.assertEqual(self.unused('[A]: value' + suffix), ['[A]'])
        self.assertEqual(self.unused('[A]: value\n[A]: other'), ['[A]'])
        self.assertFalse(self.unused('[A]:\n- Use [A]'))
        self.assertFalse(self.unused('=> Collect AS [A]\nTask:\n- Use [A]'))

    def test_unrelated_uncertainty_does_not_hide_unused_identity(self):
        for suffix in ('\n[Open', '\n- [État]', '\n   - Recovered', '\n"""\nunfinished',
                       '\n[Body]:\n- [Missing]'):
            self.assertIn('[A]', self.unused('[A]: value' + suffix))
        self.assertFalse(analyze('[A]: value', arcgrav_version='future').diagnostics.findings)

    def test_uncertainty_for_same_name_only_suppresses_its_identity(self):
        source = '[A]: value\n - Refer to [A]\n[B]: value\n'
        analysis = analyze(source)
        self.assertTrue(any(symbol.kind == 'uncertain' and symbol.name == 'A'
                            for symbol in analysis.semantics.symbols))
        self.assertEqual(self.unused(source), ['[B]'])

    def test_admission_and_severity(self):
        result = analyze('[A]: value')
        finding = next(f for f in result.diagnostics.findings if f.rule_id == RULE)
        self.assertEqual(finding.severity, 'error')
        candidate = Candidate(RULE, finding.source_range.span, 0, 'untrusted', REGISTRY[RULE].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
        used = analyze('[A]: value\nUse [A]')
        self.assertIn('unsupported_unused_declaration', admission(candidate, used.document, used.tree, used.semantics))
        nested = analyze('[Outer]:\n- [New]: value\n\nTask: value\n')
        self.assertEqual([(f.rule_id, f.severity) for f in nested.diagnostics.findings],
                         [(RULE, 'error'), ('AG-DOCUMENT-START-SECTION', 'information'),
                          ('AG-SYMBOL-NESTED-DECLARATION', 'error')])

    def test_unused_evidence_is_indexed_once_per_admission_batch(self):
        # Deterministic complexity guard: two scans regardless of error count,
        # one for proposals and one independent reconstruction for admission.
        for count in (10, 1000):
            source = "\n".join(f'[Name{i}]: value' for i in range(count))
            with patch.object(rules, '_unused_declarations', wraps=rules._unused_declarations) as scan:
                result = analyze(source)
            self.assertEqual(scan.call_count, 2)
            self.assertEqual(sum(f.rule_id == RULE for f in result.diagnostics.findings), count)

    def test_duplicate_instantiations_do_not_satisfy_later_reference(self):
        cases = (
            ('[Name]: first\n[Name]: second', 'AG-SYMBOL-DUPLICATE-INSTANTIATION'),
            ('Collect AS [Name]\nCollect again AS [Name]', 'AG-ALIAS-DUPLICATE-INSTANTIATION'),
            ('[Name]: first\nCollect AS [Name]', 'AG-ALIAS-DUPLICATE-INSTANTIATION'),
            ('Collect AS [Name]\n[Name]: second', 'AG-SYMBOL-DUPLICATE-INSTANTIATION'),
        )
        for source, rule in cases:
            with self.subTest(source=source):
                analysis = analyze(source)
                relevant = [f for f in analysis.diagnostics.findings
                            if f.rule_id in (RULE, rule)]
                self.assertEqual([f.rule_id for f in relevant], [RULE, rule])
                self.assertTrue(all(f.severity == 'error' for f in relevant))
                self.assertEqual([s.kind for s in analysis.semantics.symbols],
                                 ['alias' if source.startswith('Collect') else 'anchor',
                                  'duplicate_alias' if rule == 'AG-ALIAS-DUPLICATE-INSTANTIATION'
                                  else 'duplicate_anchor'])
                self.assertEqual(relevant[0].source_range.span.extract(source), '[Name]')
                self.assertEqual(relevant[1].source_range.span.extract(source), '[Name]')

    def test_reference_before_instantiation_does_not_count_as_later_use(self):
        source = 'Task:\n- Use [Name]\n[Name]: value'
        analysis = analyze(source)
        self.assertEqual([f.rule_id for f in analysis.diagnostics.findings
                          if f.rule_id.startswith('AG-SYMBOL-')],
                         ['AG-SYMBOL-BEFORE-DEFINITION', RULE])

    def test_batch_admission_rejects_fabricated_unused_candidate(self):
        source = '[Used]: value\n[Unused]: value\nUse [Used]'
        result = analyze(source)
        used = next(s for s in result.semantics.symbols if s.kind == 'anchor' and s.name == 'Used')

        def fabricate(*args):
            candidate = Candidate(*args)
            if candidate.rule_id == RULE:
                return replace(candidate, span=used.span, node_id=used.node)
            return candidate

        with patch.object(rules, 'Candidate', side_effect=fabricate):
            findings, suppressed = rules.evaluate_with_admission(result.document, result.tree, result.semantics)
        self.assertFalse(any(f.rule_id == RULE for f in findings))
        self.assertTrue(any(rule == RULE and 'unsupported_unused_declaration' in blockers
                            for rule, _, blockers in suppressed))
