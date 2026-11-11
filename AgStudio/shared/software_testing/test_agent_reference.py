"""The shipped ArcGrav agent YAML mirrors executable contracts, never replaces them."""
from __future__ import annotations

from importlib import resources
from pathlib import Path
import unittest

import yaml

from AgStudio.arcgrav_language_engine import AnalysisContext, analyze
from AgStudio.arcgrav_language_engine.lint.rules import RULES, REGISTRY
from AgStudio.arcgrav_language_engine.recognition.source import (
    ObservationKind, OccurrenceKind,
)
from AgStudio.arcgrav_language_engine.syntax_contract import (
    INDENT_WIDTH, NUMERIC_LIST, SYMBOL_NAME,
)
from AgStudio.shared.software_testing.generate_agent_reference import (
    REFERENCE, build_reference, main,
)
from typing import get_args


class AgentReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = REFERENCE.read_text(encoding="utf-8")
        cls.reference = yaml.safe_load(cls.text)

    def test_reference_exactly_matches_generated_engine_contracts(self):
        self.assertEqual(self.reference, build_reference())
        self.assertEqual(main(["--check"]), 0)

    def test_every_registered_rule_has_all_public_metadata(self):
        catalogue = self.reference["diagnostics"]["rules"]
        self.assertGreater(len(catalogue), 30)
        self.assertEqual(set(catalogue), set(REGISTRY))
        self.assertEqual(set(catalogue), {rule.id for rule in RULES})
        for rule in RULES:
            with self.subTest(rule=rule.id):
                self.assertEqual(catalogue[rule.id], {
                    "claim": rule.claim,
                    "severity": rule.severity,
                    "syntax_id": rule.syntax_id,
                    "limits": rule.limits,
                    "required_evidence": list(rule.required_evidence),
                    "required_relationships": list(rule.required_relationships),
                })

    def test_recognition_and_lexical_contracts_are_derived(self):
        syntax = self.reference["syntax"]
        self.assertEqual(syntax["symbol"]["identifier_regex"], SYMBOL_NAME.pattern)
        self.assertEqual(syntax["list_prefixes"]["numeric_marker_regex"], NUMERIC_LIST.pattern)
        self.assertEqual(syntax["indentation"]["width"], INDENT_WIDTH)
        self.assertEqual(syntax["recognition_kinds"]["observations"], list(get_args(ObservationKind)))
        self.assertEqual(syntax["recognition_kinds"]["occurrences"], list(get_args(OccurrenceKind)))

    def test_examples_refer_to_real_engine_behavior(self):
        context = AnalysisContext(
            arcgrav_version="current",
            configuration={"spellcheck": False},
        )
        ids = set()
        for sample in self.reference["examples"]:
            with self.subTest(sample=sample["id"]):
                self.assertNotIn(sample["id"], ids)
                ids.add(sample["id"])
                source = sample["source"]
                result = analyze(source, context)
                self.assertEqual(result.document.source, source)
                found = {finding.rule_id for finding in result.diagnostics.findings}
                if "expected_rule_id" in sample:
                    self.assertIn(sample["expected_rule_id"], found)
                if "excluded_rule_id" in sample:
                    self.assertNotIn(sample["excluded_rule_id"], found)

    def test_installed_package_resource_is_accessible_without_a_yaml_api(self):
        import AgStudio.arcgrav_language_engine as engine

        packaged = resources.files(engine).joinpath("arcgrav_agent_reference.yaml")
        self.assertEqual(packaged.read_text(encoding="utf-8"), self.text)
        self.assertEqual(self.reference["diagnostics"]["conformance"], "unknown")
        self.assertIn("unsupported_version", self.reference["diagnostics"]["status_values"])
        self.assertNotIn("AGENTS.", self.text)
        self.assertTrue(Path(REFERENCE).name == "arcgrav_agent_reference.yaml")


if __name__ == "__main__":
    unittest.main()
