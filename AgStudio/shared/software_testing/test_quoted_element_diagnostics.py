"""Unmatched active double-quoted elements are source-anchored engine warnings."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from AgStudio.arcgrav_language_engine import AnalysisContext, analyze, diagnose, prepare, SourceSpan
from AgStudio.arcgrav_language_engine.lint import rules
from AgStudio.arcgrav_language_engine.lint.rule_units import quoted_unmatched
from AgStudio.arcgrav_language_engine.lint.quoted_elements import RULE_ID, unmatched_quoted_elements

CONTEXT = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})


class QuotedElementDiagnosticTests(unittest.TestCase):
    def warnings(self, source):
        return [f for f in analyze(source, CONTEXT).diagnostics.findings if f.rule_id == RULE_ID]

    def test_three_distinct_user_examples_each_warn(self):
        values = ('"This is a double quoted element"', '"This is something else"',
                  '"this is something else"')
        source = 'Task:\n' + '\n'.join('- ' + v for v in values)
        findings = self.warnings(source)
        self.assertEqual([f.source_range.span.extract(source) for f in findings], list(values))
        self.assertTrue(all(f.severity == 'warning' for f in findings))

    def test_exact_pairs_match_each_other_without_order_or_scope_restrictions(self):
        for source in ('Task:\n- "same" "same"\n',
                       'First: "same"\n\nLast:\n  - "same"\n',
                       'Task:\n- "same" "same" "same"\n'):
            with self.subTest(source=source):
                self.assertEqual(self.warnings(source), [])

    def test_self_bare_case_whitespace_substrings_and_other_quote_kinds_do_not_match(self):
        for other in ('same', '"Same"', '"same "', '" same"', '"same more"',
                      '\'same\'', '`same`', '"sa me"', '"sa\tme"'):
            source = 'Task:\n- "same"\n- ' + other + '\n'
            with self.subTest(other=other):
                self.assertIn('"same"', [f.source_range.span.extract(source) for f in self.warnings(source)])
        self.assertEqual(len(self.warnings('Task: "same"\n')), 1)

    def test_fences_do_not_supply_matches_or_generate_warnings(self):
        for opening, closing in (('"""', '"""'), ('""""', '""""'), ('```arc', '```'), ('~~~', '~~~')):
            fenced = opening + '\n"same"\n"inside only"\n' + closing + '\n'
            with self.subTest(opening=opening):
                self.assertEqual(self.warnings('Task:\n' + fenced), [])
                source = 'Task:\n' + fenced + '- "same"\n'
                findings = self.warnings(source)
                self.assertEqual([f.source_range.span.start for f in findings], [source.rindex('"same"')])

    def test_unfinished_and_repeated_quote_values_are_not_lookup_elements(self):
        source = 'Task:\n- "unfinished\n- "a\\"\n- """inline"""\n'
        self.assertEqual(self.warnings(source), [])

    def test_exact_unicode_and_crlf_coordinates(self):
        source = 'Task:\r\n- 🌍 "é"\r\n- "e\u0301"\r\n'
        findings = self.warnings(source)
        self.assertEqual(len(findings), 2)
        first = findings[0].source_range
        self.assertEqual(first.span, SourceSpan(source.index('"é"'), source.index('"é"') + 3))
        self.assertEqual((first.start.line, first.start.column), (2, 5))

    def test_prepare_diagnose_pipeline_and_unsupported_version(self):
        source = 'Task: "missing"\n'
        prepared = prepare(source, CONTEXT)
        self.assertEqual(prepared.diagnostics.findings, ())
        with patch('AgStudio.arcgrav_language_engine.api.prepare', side_effect=AssertionError('reparse')):
            result = diagnose(prepared)
        self.assertEqual(len([f for f in result.findings if f.rule_id == RULE_ID]), 1)
        self.assertEqual(result, analyze(source, CONTEXT).diagnostics)
        self.assertFalse(any(f.rule_id == RULE_ID for f in analyze(
            source, AnalysisContext(arcgrav_version='future')).diagnostics.findings))

    def test_admission_rejects_invented_missing_matches_and_partial_ranges(self):
        result = analyze('Task: "same" "same" "alone"\n', CONTEXT)
        finding = next(f for f in result.diagnostics.findings if f.rule_id == RULE_ID)
        node = result.tree.nodes[0]
        candidate = rules.Candidate(RULE_ID, finding.source_range.span, node.id, 'forged',
                                    rules.REGISTRY[RULE_ID].required_evidence)
        self.assertEqual(rules.admission(candidate, result.document, result.tree, result.semantics), ())
        for span in (SourceSpan(finding.source_range.span.start + 1, finding.source_range.span.end - 1),
                     next(t.span for t in node.tokens if t.text == '"same"')):
            self.assertIn('unsupported_quoted_element_match', rules.admission(
                replace(candidate, span=span), result.document, result.tree, result.semantics))

    def test_index_is_built_twice_for_batch_not_once_per_element(self):
        source = 'Task:\n' + ''.join('- "value ' + str(i) + '"\n' for i in range(300))
        with patch.object(quoted_unmatched, 'unmatched_quoted_elements',
                          wraps=unmatched_quoted_elements) as index:
            self.assertEqual(len(self.warnings(source)), 300)
        self.assertEqual(index.call_count, 2)  # Proposal and independent admission.


if __name__ == '__main__':
    unittest.main()
