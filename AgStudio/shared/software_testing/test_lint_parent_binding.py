"""Exact editor regression for explicit reference binding and ordered parents."""
from dataclasses import replace
import unittest

from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission
from AgStudio.shared.recognition import SourceSpan


ANNOTATED = ('[SomeSymbol]:\n- Context\n\n[SomethingElse]:\u2028'
             '- Derive from [SomeSymbol]:      // Violation: should have an arrow instead of a colon\n'
             '  - Whatever\n\n[Test]:\n1. One\n'
             '2. Two                          // Error: missing colon\n  1. One\n'
             '\nTask:\n- Use [SomethingElse] and [Test]\n')
BINDING = 'AG-BINDING-REFERENCE-COLON'
ORDERED = 'AG-ORDERED-PARENT-COLON'


class ParentBindingTests(unittest.TestCase):
    def ids(self, source):
        # Local binding fixtures do not assert document-level completion.
        return {f.rule_id for f in analyze(source).diagnostics.findings
                if f.rule_id not in {'AG-DOCUMENT-END-SECTION', 'AG-DOCUMENT-START-SECTION'}}

    def test_exact_annotated_editor_snapshot(self):
        a = analyze(ANNOTATED)
        self.assertEqual([f.rule_id for f in a.diagnostics.findings], ['AG-DOCUMENT-START-SECTION', BINDING, ORDERED])
        self.assertEqual([f.source_range.span.extract(ANNOTATED) for f in a.diagnostics.findings[1:]], [':', '2.'])
        self.assertEqual(a.document.source, ANNOTATED)
        self.assertEqual(a.diagnostics.findings, analyze(ANNOTATED).diagnostics.findings)
        refs = [s for s in a.semantics.symbols if s.name == 'SomeSymbol']
        self.assertEqual([s.kind for s in refs], ['anchor', 'reference'])
        self.assertEqual(a.semantics.resolutions[0].status, 'unique_prior_anchor')

    def test_independent_corrections_and_unicode_line_separators(self):
        for separator in ('\n', '\r\n', '\u2028', '\u2029', '\x85'):
            source = ANNOTATED.replace('\u2028', '\n').replace('\n', separator)
            self.assertEqual(self.ids(source), {BINDING, ORDERED})
            first = source.replace('from [SomeSymbol]:', 'from [SomeSymbol] ↳')
            self.assertEqual(self.ids(first), {ORDERED})
            second = source.replace('2. Two ', '2. Two: ', 1)
            self.assertEqual(self.ids(second), {BINDING})
            self.assertFalse(self.ids(first.replace('2. Two ', '2. Two: ', 1)))

    def test_binding_requires_expression_and_clear_child(self):
        for source in ('[SomeSymbol]:\n- Context\n',
                       '- [SomeSymbol]:\n  - Context\n',
                       '- Derive from [SomeSymbol]:\n- Peer\n',
                       '- Derive from [SomeSymbol]:\n   - Uncertain indentation\n',
                       '- Derive from [SomeSymbol]:\n  Ordinary prose\n',
                       '- Derive from "[SomeSymbol]:"\n  - Child\n',
                       '- Value AS [SomeSymbol]:\n  - Child\n',
                       '- Derive from [Unknown-Name]:\n  - Child\n',
                       '- Derive from [SomeSymbol].field:\n  - Child\n',
                       '- Derive from [SomeSymbol]: More text\n  - Child\n'):
            with self.subTest(source=source):
                self.assertNotIn(BINDING, self.ids(source))

    def test_ordered_parent_excludes_ambiguous_or_unrelated_forms(self):
        for source in ('1. Parent:\n  1. Child\n', '1. Parent ↳\n  1. Child\n',
                       '1. Parent\n2. Peer\n', '01. Parent\n  1. Child\n',
                       '1. [Symbol]\n  1. Child\n',
                       '0. Parent\n  1. Child\n', 'P0. Parent\n  1. Child\n',
                       '- Parent\n  - Child\n', '1.\tParent\n  1. Child\n',
                       '1. Parent\n   1. Uncertain\n', '1. Parent [Broken\n  1. Child\n',
                       '1. Value AS [Alias]\n  1. Child\n'):
            with self.subTest(source=source):
                self.assertNotIn(ORDERED, self.ids(source))

    def test_annotations_do_not_reinterpret_quotes_or_urls(self):
        for source in ('- Use [SomeSymbol]: "// prose"\n  - Child\n',
                       '- Use [SomeSymbol]: https://example.test\n  - Child\n',
                       '- Use [SomeSymbol]: path//name\n  - Child\n'):
            self.assertNotIn(BINDING, self.ids(source))
        self.assertIn(ORDERED, self.ids('1. Parent "// :"\n  1. Child\n'))
        self.assertIn(ORDERED, self.ids('1. Parent https://example.test\n  1. Child\n'))

    def test_ordered_reference_and_operation_binding_do_not_cascade(self):
        for prefix in ('1.', '=>'):
            source = '[A]: Value\n' + prefix + ' Derive from [A]:\n  - Child\n'
            self.assertEqual(self.ids(source), {BINDING})
            self.assertFalse(self.ids(source.replace('from [A]:', 'from [A] ↳')))
        self.assertEqual(self.ids('1. Parent ":"\n  1. Child\n'),
                         {ORDERED, 'AG-QUOTED-ELEMENT-NO-MATCH'})
        self.assertEqual(self.ids('=> Parent\n  - Child\n'), {'AG-PARENT-BLOCK-OPENER'})

    def test_missing_openers_exact_examples_and_nested_lists(self):
        cases = [('[SpecificationModes]\n- Root\n- Local', '[SpecificationModes]'),
                 ('[Modes]:\n- Root:\n  - Non-sibjective\n- Local\n  - Subjective', '-'),
                 ('[SpecificationModes]\n\n- Root', '[SpecificationModes]'),
                 ('Scope:\n  [Modes]\n  - Root', '[Modes]'),
                 ('- Outer:\n  - Inner\n\n    - Child', '-'),
                 ('P0. Parent\n  - Child', 'P0.'),
                 ('- [Parent]\n  - Child', '-')]
        cases += [(source.replace('\n', '\r\n'), marker) for source, marker in cases]
        for source, marker in cases:
            with self.subTest(source=source):
                a = analyze(source)
                findings = [f for f in a.diagnostics.findings if f.rule_id == 'AG-PARENT-BLOCK-OPENER']
                self.assertEqual(len(findings), 1)
                f = findings[0]
                self.assertEqual(f.severity, 'error')
                self.assertEqual(f.source_range.span.extract(source), marker)
                node = next(n for n in a.tree.nodes if n.span.start <= f.source_range.span.start < n.span.end)
                candidate = Candidate(f.rule_id, f.source_range.span, node.id, 'untrusted', REGISTRY[f.rule_id].required_evidence)
                self.assertEqual(admission(candidate, a.document, a.tree, a.semantics), ())
                self.assertTrue(admission(replace(candidate, evidence=()), a.document, a.tree, a.semantics))
                safe = analyze('Task: Work')
                fake = replace(candidate, span=SourceSpan(0, 1), node_id=0)
                self.assertIn('unsupported_structural_evidence', admission(fake, safe.document, safe.tree, safe.semantics))

    def test_missing_opener_excludes_valid_blocks_siblings_and_opaque_source(self):
        for source in ('[Modes]:\n- Root\n- Local', '[Modes] ↳\n  - Root',
                       '- Local:\n  - Subjective', '- Local ↳\n  - Subjective',
                       '- Root\n- Local', '[Modes]', 'Plain prose\n  - List', '[Modes]\nTask: Act',
                       '[Modes]\nProse\n- List', '- Parent\n   - Uncertain',
                       '"""\n[Modes]\n- Root\n- Local\n  - Child\n"""',
                       '- "[Modes]"', '=> Parent ↳\n  - Child'):
            with self.subTest(source=source):
                self.assertNotIn('AG-PARENT-BLOCK-OPENER', self.ids(source))
        self.assertEqual(self.ids('1. Parent\n  - Child'), {ORDERED})
        self.assertFalse(analyze('[Modes]\n- Root', arcgrav_version='future').diagnostics.findings)

    def test_literal_shielding_and_version_gate(self):
        for delimiter in ('"""', '""""'):
            self.assertFalse({BINDING, ORDERED} & self.ids(delimiter + '\n' + ANNOTATED + delimiter + '\n'))
            self.assertFalse({BINDING, ORDERED} & self.ids(delimiter + '\n' + ANNOTATED))
        self.assertFalse(analyze(ANNOTATED, arcgrav_version='future').diagnostics.findings)

    def test_admission_reconstructs_exact_premises(self):
        a = analyze(ANNOTATED)
        for finding in a.diagnostics.findings:
            if finding.rule_id not in {BINDING, ORDERED}:
                continue
            span = finding.source_range.span
            node = next(n for n in a.tree.nodes if n.span.start <= span.start < n.span.end)
            candidate = Candidate(finding.rule_id, span, node.id, 'Untrusted', REGISTRY[finding.rule_id].required_evidence)
            self.assertEqual(admission(candidate, a.document, a.tree, a.semantics), ())
            self.assertTrue(admission(replace(candidate, evidence=()), a.document, a.tree, a.semantics))
            bad = replace(candidate, span=SourceSpan(span.start, span.end + 1))
            self.assertIn('unsupported_structural_evidence', admission(bad, a.document, a.tree, a.semantics))
            safe = analyze('1. Parent:\n  1. Child\n')
            forged = replace(candidate, span=SourceSpan(0, 2), node_id=0)
            self.assertIn('unsupported_structural_evidence', admission(forged, safe.document, safe.tree, safe.semantics))
