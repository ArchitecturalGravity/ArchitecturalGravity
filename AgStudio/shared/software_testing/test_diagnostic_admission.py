"""Adversarial source premises are rejected independently of proposals."""
from dataclasses import replace
import unittest
from unittest.mock import patch
from AgStudio.arcgrav_language_engine import AnalysisContext, prepare, restore_document
from AgStudio.arcgrav_language_engine.lint import rules
from AgStudio.arcgrav_language_engine.recognition import SourceSpan

class DiagnosticAdmissionTests(unittest.TestCase):
    def setUp(self):
        snapshot = prepare('Task:\n=> - Active\n', AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False}))
        self.document = restore_document(snapshot.document)
        self.tree, self.semantics = snapshot.tree, snapshot.semantics
        self.rule = rules.REGISTRY['AG-OPERATION-LIST']
        self.candidate = rules.Candidate(self.rule.id, SourceSpan(6, 11), 1, 'proposal', ('canonical_prefix_chain',))

    def admission(self, candidate):
        return rules.admission(candidate, self.document, self.tree, self.semantics)

    def test_evidence_is_required_and_exact_source_is_independently_verified(self):
        self.assertEqual(self.admission(self.candidate), ())
        self.assertIn('missing_evidence:canonical_prefix_chain', self.admission(replace(self.candidate, evidence=())))
        self.assertIn('imprecise_prefix_range', self.admission(replace(self.candidate, span=SourceSpan(6, 7))))
        self.assertIn('imprecise_range', self.admission(replace(self.candidate, span=SourceSpan(0, 7))))
        self.assertEqual(self.admission(replace(self.candidate, node_id=999)), ('missing_canonical_node',))
        self.assertEqual(self.admission(replace(self.candidate, rule_id='unknown')), ('unknown_rule',))

    def test_severity_and_relationship_requirements_are_enforced(self):
        for severity in ('critical', 'information'):
            with patch.dict(rules.REGISTRY, {self.rule.id: replace(self.rule, severity=severity)}):
                found, _ = rules.evaluate_with_admission(self.document, self.tree, self.semantics)
            self.assertEqual([f.severity for f in found if f.rule_id == self.rule.id], [severity])
        with patch.dict(rules.REGISTRY, {self.rule.id: replace(self.rule, severity='unknown')}):
            self.assertIn('invalid_severity', self.admission(self.candidate))
        with patch.dict(rules.REGISTRY, {self.rule.id: replace(self.rule, required_relationships=('physical_whole_line',))}):
            self.assertIn('untrusted_relationship:physical_whole_line', self.admission(self.candidate))

    def test_recovery_and_quoted_text_do_not_validate_forged_mixed_prefixes(self):
        for source in ('Task:\n=>\n', 'Task:\n"=> - Active"\n', 'Task:\n"""\n=> - Hidden\n"""\n'):
            snapshot = prepare(source, AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False}))
            document = restore_document(snapshot.document)
            forged = replace(self.candidate, span=SourceSpan(6, 7))
            self.assertTrue(rules.admission(forged, document, snapshot.tree, snapshot.semantics))

    def test_no_legacy_findings_parameter_is_accepted(self):
        with self.assertRaises(TypeError):
            rules.evaluate_with_admission(self.document, self.tree, self.semantics, ())
