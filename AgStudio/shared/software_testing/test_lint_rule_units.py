"""Rule-unit contracts: isolation, independent verification, and phase caches."""
from dataclasses import replace
import unittest

from AgStudio.arcgrav_language_engine import AnalysisContext, prepare
from AgStudio.arcgrav_language_engine.lint import rules
from AgStudio.arcgrav_language_engine.lint.rule_units import RuleContext, build_units
from AgStudio.arcgrav_language_engine.recognition import SourceSpan
from AgStudio.arcgrav_language_engine.snapshot import restore_document


CASES = {
    "AG-INDENT-WIDTH": "   - Odd indent\n",
    "AG-INDENT-MIXED": " \t- Mixed indent\n",
    "AG-LITERAL-UNCLOSED": "Task:\n\"\"\"\nUnclosed literal\n",
    "AG-SYNTAX-INCOMPLETE": "Task:\n- [badName]\n",
    "AG-OPERATION-INCOMPLETE": "=>\n",
    "AG-BACKTICK-WHITESPACE": "Task:\n- `two words`\n",
}


class RuleUnitTests(unittest.TestCase):
    def prepared(self, source):
        snapshot = prepare(source, AnalysisContext(
            arcgrav_version="current", configuration={"spellcheck": False}))
        document = restore_document(snapshot.document)
        return RuleContext(document, snapshot.tree, snapshot.semantics)

    def test_uniform_contract_and_explicit_metadata(self):
        units = build_units(rules.REGISTRY)
        self.assertEqual(set(units), {definition.id for definition in rules.RULES})
        self.assertTrue(set(CASES).issubset(units))
        for rule_id, unit in units.items():
            with self.subTest(rule=rule_id):
                self.assertEqual(unit.id, rule_id)
                self.assertIs(unit.definition, rules.REGISTRY[rule_id])
                self.assertTrue(unit.requires)
                self.assertIn(unit.scope, ('node', 'document'))
                self.assertIn(unit.literal_policy, ('any', 'only', 'exclude'))
                self.assertTrue(callable(unit.detect))
                self.assertTrue(callable(unit.verify))
        for scope in ("node", "document"):
            scheduled = sorted((u for u in units.values() if u.scope == scope),
                               key=lambda unit: unit.order)
            self.assertEqual([unit.order for unit in scheduled],
                             list(range(len(scheduled))))
        with self.assertRaises(ValueError):
            build_units({})

    def test_each_unit_detects_and_independently_verifies_exact_evidence(self):
        for rule_id, source in CASES.items():
            with self.subTest(rule=rule_id):
                context = self.prepared(source)
                unit = rules._RULE_UNITS[rule_id]
                proposals = tuple(proposal for node in context.tree.nodes
                                  for proposal in unit.detect(context, node))
                self.assertTrue(proposals, rule_id)
                for proposal in proposals:
                    candidate = rules.Candidate(
                        rule_id, proposal.span, proposal.node_id,
                        proposal.message, proposal.evidence,
                    )
                    self.assertEqual(unit.verify(context, candidate), ())
                    self.assertEqual(rules.admission(
                        candidate, context.document, context.tree,
                        context.semantics), ())
                    forged = replace(candidate, span=SourceSpan(0, 0))
                    self.assertTrue(unit.verify(context, forged))
                findings, _ = rules.evaluate_with_admission(
                    context.document, context.tree, context.semantics)
                self.assertTrue(any(f.rule_id == rule_id for f in findings))

    def test_document_scoped_unit_owns_detection_and_verification(self):
        context = self.prepared("[Unused]: value\n")
        rule = rules._RULE_UNITS["AG-SYMBOL-UNUSED"]
        self.assertEqual(rule.scope, "document")
        self.assertEqual(tuple(rule.detect(context, context.tree.nodes[0])), ())
        proposals = tuple(rule.detect(context, None))
        self.assertEqual(len(proposals), 1)
        proposed = proposals[0]
        candidate = rules.Candidate(rule.id, proposed.span, proposed.node_id,
                                    proposed.message, proposed.evidence)
        self.assertEqual(rule.verify(context, candidate), ())
        self.assertEqual(rules.admission(candidate, context.document,
                                         context.tree, context.semantics), ())

    def test_lazy_evidence_is_scoped_to_detection_and_verification(self):
        context = self.prepared("Task:\n- Read\n")
        calls = []
        def make(label):
            def factory():
                calls.append(label)
                return (label,)
            return factory

        a = context.evidence("tokens", make("detect"))
        self.assertIs(a, context.evidence("tokens", make("should-not-run")))
        b = context.evidence("tokens", make("verify"), verification=True)
        self.assertIs(b, context.evidence("tokens", make("should-not-run"),
                                          verification=True))
        self.assertEqual(calls, ["detect", "verify"])
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
