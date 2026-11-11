"""Admission evidence remains independent while unused work stays bounded."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from AgStudio.arcgrav_language_engine import AnalysisContext, prepare
from AgStudio.arcgrav_language_engine.lint import rules
from AgStudio.arcgrav_language_engine.recognition import SourceSpan
from AgStudio.arcgrav_language_engine.snapshot import restore_document


def prepared(source, *, version='current', configuration=None):
    snapshot = prepare(source, AnalysisContext(
        arcgrav_version=version, configuration=configuration))
    return restore_document(snapshot.document), snapshot.tree, snapshot.semantics


class DiagnosticEvidenceIndexTests(unittest.TestCase):
    def test_absent_families_skip_admission_reconstruction(self):
        for configuration in (None, {}, {'spellcheck': False}):
            with self.subTest(configuration=configuration):
                document, tree, semantics = prepared('Task:\n- Read the document\n',
                                                      configuration=configuration)
                # Control family absence even in a base install, where a
                # missing optional dictionary itself proposes a status finding.
                with patch.object(rules, 'resolve_members', side_effect=AssertionError('unused member evidence')), \
                     patch.object(rules, 'spelling_spans', return_value={}) as spelling:
                    found, _ = rules.evaluate_with_admission(document, tree, semantics)
                self.assertEqual(spelling.call_count, 1)  # Proposal pass only.
                self.assertFalse(any(f.rule_id in rules.SPELLING_MESSAGES for f in found))

    def test_present_families_reconstruct_exact_evidence(self):
        document, tree, semantics = prepared('[A]:\n- `item`\n- mispelled\n')
        with patch.object(rules, 'resolve_members', wraps=rules.resolve_members) as members, \
             patch.object(rules, 'spelling_spans', wraps=rules.spelling_spans) as spelling:
            found, _ = rules.evaluate_with_admission(document, tree, semantics)
        self.assertEqual(members.call_count, 1)
        self.assertEqual(spelling.call_count, 2)
        self.assertTrue(any(f.rule_id in rules.MEMBER_FINDING_MESSAGES for f in found))
        self.assertTrue(any(f.rule_id in rules.SPELLING_MESSAGES for f in found))

    def test_forged_member_proposal_is_not_reused_as_admission_evidence(self):
        _, _, bad_semantics = prepared('[A]:\n- `item`\n')
        document, tree, semantics = prepared('[A]:\n- `item`\n- Use `item`\n')
        forged = replace(semantics, members=bad_semantics.members)
        with patch.object(rules, 'resolve_members', wraps=rules.resolve_members) as members:
            found, suppressed = rules.evaluate_with_admission(document, tree, forged)
        self.assertEqual(members.call_count, 1)
        self.assertFalse(any(f.rule_id in rules.MEMBER_FINDING_MESSAGES for f in found))
        self.assertTrue(any('unsupported_member_evidence' in row[2] for row in suppressed))

    def test_forged_spelling_proposal_is_rechecked_against_protected_source(self):
        source = '- correct and `recieve`\n'
        document, tree, semantics = prepared(source)
        span = SourceSpan(source.index('recieve'), source.index('recieve') + 7)
        real_spelling = rules.spelling_spans
        calls = []

        def proposed_then_independent(*args, **kwargs):
            calls.append(None)
            if len(calls) == 1:
                return {('AG-SPELLING', tree.nodes[0].id, span): 'forged'}
            return real_spelling(*args, **kwargs)

        with patch.object(rules, 'spelling_spans', side_effect=proposed_then_independent):
            found, suppressed = rules.evaluate_with_admission(document, tree, semantics)
        self.assertEqual(len(calls), 2)
        self.assertFalse(any(f.rule_id in rules.SPELLING_MESSAGES for f in found))
        self.assertTrue(any('unsupported_spelling_evidence' in row[2] for row in suppressed))

    def test_unavailable_dictionary_candidate_still_gets_independent_evidence(self):
        from AgStudio.arcgrav_language_engine.lint import spelling
        document, tree, semantics = prepared('- mispelled ordinary text\n')
        with patch.object(spelling, '_CHECKER', None), \
             patch.object(rules, 'spelling_spans', wraps=rules.spelling_spans) as spans:
            found, _ = rules.evaluate_with_admission(document, tree, semantics)
        self.assertEqual(spans.call_count, 2)
        self.assertEqual([f.rule_id for f in found if f.rule_id in rules.SPELLING_MESSAGES],
                         ['AG-SPELLCHECK-UNAVAILABLE'])

    def test_unsupported_version_never_builds_family_evidence(self):
        document, tree, semantics = prepared('- mispelled\n', version='future')
        with patch.object(rules, 'resolve_members', side_effect=AssertionError('members')), \
             patch.object(rules, 'spelling_spans', side_effect=AssertionError('spelling')):
            self.assertEqual(rules.evaluate_with_admission(document, tree, semantics), ((), ()))





    def test_operation_candidates_are_evaluated_once_at_both_scales(self):
        for count in (64, 256):
            document, tree, semantics = prepared('=> - active\n' * count, configuration={'spellcheck': False})
            found, suppressed = rules.evaluate_with_admission(document, tree, semantics)
            matches = [f for f in found if f.rule_id == 'AG-OPERATION-LIST']
            self.assertEqual(len(matches), count)
            self.assertEqual([f.source_range.span.start for f in matches], [n.span.start for n in tree.nodes])
            self.assertFalse(suppressed)


if __name__ == '__main__':
    unittest.main()
