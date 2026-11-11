"""Embedded unescaped quotes fail without treating separate values as nested."""
from dataclasses import replace
import unittest

from AgStudio.arcgrav_language_engine import AnalysisContext, analyze, diagnose, prepare, SourceSpan
from AgStudio.arcgrav_language_engine.lint import rules
from AgStudio.arcgrav_language_engine.lint.quoted_elements import COLLISION_RULE_ID, RULE_ID

CONTEXT = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})
EXAMPLE = '"This line contains a "double" quote within it"'


class DoubleQuoteCollisionTests(unittest.TestCase):
    def result(self, text):
        return analyze(text, CONTEXT)

    def collisions(self, text):
        return [f for f in self.result(text).diagnostics.findings if f.rule_id == COLLISION_RULE_ID]

    def test_exact_user_example_is_error_with_literal_block_advice(self):
        for prefix in ('', '- ', '=> Return ', 'Task: '):
            source = 'Task:\n' + prefix + EXAMPLE + '\n'
            with self.subTest(prefix=prefix):
                result = self.result(source)
                errors = [f for f in result.diagnostics.findings if f.rule_id == COLLISION_RULE_ID]
                self.assertEqual(len(errors), 1)
                self.assertEqual(errors[0].severity, 'error')
                self.assertEqual(errors[0].source_range.span.extract(source), EXAMPLE)
                self.assertIn('Use a literal quote block instead', errors[0].message)
                self.assertFalse(any(f.rule_id == RULE_ID for f in result.diagnostics.findings))
                self.assertEqual(result.tree.find_quoted_element('"This line contains a "'), ())
                self.assertEqual(result.tree.find_quoted_element('" quote within it"'), ())

    def test_literal_alternative_and_markdown_fences_stay_opaque(self):
        for opening, closing in (('"""', '"""'), ('""""', '""""'), ('```arc', '```'), ('~~~', '~~~')):
            source = 'Task:\n' + opening + '\n' + EXAMPLE + '\n' + closing + '\n'
            with self.subTest(opening=opening):
                self.assertFalse(any(f.rule_id in (RULE_ID, COLLISION_RULE_ID)
                                     for f in self.result(source).diagnostics.findings))

    def test_ordinary_and_separate_elements_remain_lookup_elements(self):
        for value in ('"one"', '"one" "two"', '"one" and "two"',
                      '"one", "two"', '"one","two"', '"one" => "two"',
                      '"one"\t"two"', '"one" "two" "three"'):
            with self.subTest(value=value):
                source = 'Task:\n- ' + value + '\n'
                self.assertEqual(self.collisions(source), [])
                self.assertEqual(len(self.result(source).tree.find_quoted_element('"one"')), 1)

    def test_existing_escape_shielding_and_other_quotes_are_preserved(self):
        for value in ('"This contains a \\"double\\" quote"', '\'' + EXAMPLE + '\'',
                      '`' + EXAMPLE + '`', '"""inline "double" quotes"""', '"unfinished'):
            with self.subTest(value=value):
                self.assertEqual(self.collisions('Task:\n- ' + value + '\n'), [])
        value = '"This contains a \\"double\\" quote"'
        self.assertEqual(len(self.result('Task: ' + value).tree.find_quoted_element(value)), 1)

    def test_collision_fragments_do_not_supply_matches_elsewhere(self):
        source = 'Task:\n- ' + EXAMPLE + ' and "valid"\n- "This line contains a "\n'
        result = self.result(source)
        warnings = [f.source_range.span.extract(source) for f in result.diagnostics.findings if f.rule_id == RULE_ID]
        self.assertEqual(warnings, ['"valid"', '"This line contains a "'])
        self.assertEqual(len(result.tree.find_quoted_element('"This line contains a "')), 1)

    def test_multiple_collisions_are_coalesced_and_line_bounded(self):
        value = '"A "first" and "second" quote"'
        self.assertEqual([f.source_range.span.extract(value) for f in self.collisions(value)], [value])
        self.assertEqual(self.collisions('Task:\n- "one"\nword\n- "two"\n'), [])

    def test_unicode_crlf_and_prepare_diagnose_agree(self):
        source = 'Task:\r\n- 🌍 ' + EXAMPLE + '\r\n'
        prepared = prepare(source, CONTEXT)
        self.assertEqual(prepared.diagnostics.findings, ())
        self.assertEqual(diagnose(prepared), self.result(source).diagnostics)
        finding = self.collisions(source)[0]
        self.assertEqual((finding.source_range.start.line, finding.source_range.start.column), (2, 5))
        self.assertEqual(finding.source_range.span, SourceSpan(source.index(EXAMPLE), source.index(EXAMPLE) + len(EXAMPLE)))
        self.assertEqual(analyze(source, AnalysisContext(arcgrav_version='future')).diagnostics.findings, ())

    def test_admission_rejects_partial_ranges_and_fabricated_evidence(self):
        source = 'Task:\n- ' + EXAMPLE + '\n- "ordinary"\n'
        result = self.result(source)
        finding = self.collisions(source)[0]
        candidate = rules.Candidate(COLLISION_RULE_ID, finding.source_range.span, 1, 'forged',
                                    rules.REGISTRY[COLLISION_RULE_ID].required_evidence)
        self.assertEqual(rules.admission(candidate, result.document, result.tree, result.semantics), ())
        for forged in (replace(candidate, span=SourceSpan(candidate.span.start + 1, candidate.span.end)),
                       replace(candidate, node_id=2, span=next(t.span for t in result.tree.nodes[2].tokens if t.kind == 'quoted_scalar'))):
            self.assertIn('unsupported_double_quote_collision', rules.admission(forged, result.document, result.tree, result.semantics))


if __name__ == '__main__':
    unittest.main()
