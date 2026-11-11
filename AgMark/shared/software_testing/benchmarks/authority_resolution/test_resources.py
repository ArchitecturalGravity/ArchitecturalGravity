"""Conformance of the active ARB resource graph, independent of Git history."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

from AgMark.Authority_Resolution_Benchmark.evaluation.field_scorer import (
    FIELD_ACCURACY_COMPANIONS,
    FIELD_SCORING_CONTROLS,
)


_ROOT = Path(__file__).resolve().parents[5]
_ARB = _ROOT / "AgMark/Authority_Resolution_Benchmark"
_REGISTRATION = _ARB / "registrations/v2.0.0/benchmark-core.json"


def _document(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _ordered_json(text: str):
    # Tuples preserve object members/order and remain distinct from JSON arrays.
    return json.loads(text, object_pairs_hook=tuple)


class AuthorityResolutionResourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registration = _document(_REGISTRATION)
        self.artifacts = {x["artifact_id"]: x for x in self.registration["implementation_artifacts"]}
        self.selected = self.registration["extensions"][
            "arcgrav.authority-resolution:benchmark-authority"
        ]["selected_authority"]
        self.treatments = self.resource(self.selected["treatment_set"]["artifact_id"])
        self.logic = self.resource(self.selected["logic_set"]["artifact_id"])

    def resource(self, artifact_id: str):
        return _document(_ROOT / self.artifacts[artifact_id]["reference"])

    def assert_binding(self, binding: dict, root: Path) -> None:
        raw = (root / binding["reference"]).read_bytes()
        self.assertEqual("sha256:" + hashlib.sha256(raw).hexdigest(), binding["sha256"])
        if "byte_length" in binding:
            self.assertEqual(len(raw), binding["byte_length"])

    def test_all_selected_artifact_bindings_match_exact_current_bytes(self) -> None:
        for binding in self.artifacts.values():
            with self.subTest(artifact=binding["artifact_id"]):
                self.assert_binding(binding, _ROOT)
        scorer = self.resource(self.selected["scorer"]["registration_artifact_id"])
        for binding in scorer["implementation_artifacts"]:
            with self.subTest(scorer_artifact=binding["artifact_id"]):
                self.assert_binding(binding, _ROOT)
                self.assertEqual(self.artifacts[binding["artifact_id"]], binding)

    def test_prompt_and_provenance_bindings_are_verified_independently(self) -> None:
        self.assertEqual(5, len(self.treatments["treatments"]))
        for treatment in self.treatments["treatments"]:
            with self.subTest(treatment=treatment["treatment_id"]):
                self.assert_binding(treatment["prompt"], _ARB)
                self.assert_binding(treatment["provenance"], _ARB)
                registered_prompt = self.artifacts["arb-prompt-" + treatment["treatment_id"].removeprefix("arb-")]
                self.assertEqual(treatment["prompt"]["sha256"], registered_prompt["sha256"])
                self.assertEqual(_ARB / treatment["prompt"]["reference"], _ROOT / registered_prompt["reference"])

    def test_v2_prompts_and_archived_provenance_have_independent_bindings(self) -> None:
        for treatment in self.treatments["treatments"]:
            with self.subTest(treatment=treatment["treatment_id"]):
                reference = treatment["prompt"]["reference"]
                self.assertTrue(reference.startswith("treatments/v2.0.0/prompts/"))
                prompt_bytes = (_ARB / reference).read_bytes()
                provenance_bytes = (_ARB / treatment["provenance"]["reference"]).read_bytes()
                # Archived provenance is checked independently of the active
                # prompt, regardless of whether the current bytes happen to match.
                self.assertNotEqual(reference, treatment["provenance"]["reference"])
                self.assertEqual("sha256:" + hashlib.sha256(prompt_bytes).hexdigest(),
                                 treatment["prompt"]["sha256"])
                self.assertEqual("sha256:" + hashlib.sha256(provenance_bytes).hexdigest(),
                                 treatment["provenance"]["sha256"])

    def test_case_and_golden_metadata_bind_the_default_input_and_implementation(self) -> None:
        cases = self.resource(self.selected["case_set"]["artifact_id"])
        self.assertEqual(1, len(cases["cases"]))
        self.assert_binding(cases["cases"][0]["input"], _ARB)
        self.assert_binding(self.logic["frozen_golden_source"], _ARB)
        golden = self.selected["golden_authority"]
        self.assertEqual("registered_file", golden["input_transport"])
        self.assertIn(golden["input_artifact_id"], golden["implementation_artifact_ids"])
        self.assertIn(golden["artifact_id"], golden["implementation_artifact_ids"])
        self.assertEqual(_ARB / cases["cases"][0]["input"]["reference"],
                         _ROOT / self.artifacts[golden["input_artifact_id"]]["reference"])
        self.assertEqual(self.logic["frozen_golden_source"]["sha256"],
                         self.artifacts[golden["artifact_id"]]["sha256"])

    def test_all_five_embedded_sources_match_case_occurrences_and_member_order(self) -> None:
        input_binding = self.artifacts[self.selected["golden_authority"]["input_artifact_id"]]
        expected = _ordered_json((_ROOT / input_binding["reference"]).read_text(encoding="utf-8"))
        for treatment in self.treatments["treatments"]:
            with self.subTest(treatment=treatment["treatment_id"]):
                path = _ARB / treatment["prompt"]["reference"]
                text = path.read_text(encoding="utf-8")
                if path.suffix == ".xml":
                    root = ET.fromstring(text)
                    sources = root.findall("source")
                    self.assertEqual(1, len(sources))
                    source = sources[0].text
                    self.assertIsNotNone(source)
                    actual = _ordered_json(source.strip())
                else:
                    marker = re.search(r"(?m)^(?:\[Source\]|Source):", text)
                    self.assertIsNotNone(marker)
                    source_start = text.index("{", marker.end())
                    actual, _ = json.JSONDecoder(object_pairs_hook=tuple).raw_decode(text[source_start:])
                self.assertEqual(expected, actual)

    def test_logic_symbols_and_all_correlated_atom_references_resolve(self) -> None:
        source = (_ARB / self.logic["frozen_golden_source"]["reference"]).read_text(encoding="utf-8")
        module = ast.parse(source)
        symbols = set()
        for node in module.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.add(node.name)
            elif isinstance(node, ast.Assign):
                symbols.update(target.id for target in node.targets if isinstance(target, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                symbols.add(node.target.id)
        atoms = {atom["atom_id"] for atom in self.logic["atom_inventory"]}
        self.assertIn("arb.logic.structured-output-contract", atoms)
        self.assertNotIn("arb.logic.rendered-output-contract", atoms)
        for atom in self.logic["atom_inventory"]:
            with self.subTest(atom=atom["atom_id"]):
                self.assertTrue(set(atom["source_symbols"]) <= symbols)
        for dependency in self.logic["dependencies"]:
            self.assertIn(dependency["atom_id"], atoms)
            self.assertTrue(set(dependency["depends_on"]) <= atoms)
        for leakage in self.logic["leakage_classes"]:
            self.assertTrue(set(leakage["trace_atoms"]) <= atoms)
        mappings = self.logic["treatment_mapping"]["mappings"]
        self.assertEqual({x["treatment_id"] for x in self.treatments["treatments"]},
                         {x["treatment_id"] for x in mappings})
        for mapping in mappings:
            self.assertEqual(atoms, set(mapping["required_atoms"]))

    def test_metric_controls_companions_and_entrypoints_match_selected_implementation(self) -> None:
        metric = self.resource(self.selected["primary_metric"]["artifact_id"])
        self.assertEqual(dict(FIELD_SCORING_CONTROLS),
                         metric["extensions"]["arcgrav.authority-resolution:field-scoring"])
        self.assertEqual(list(FIELD_ACCURACY_COMPANIONS), metric["required_companion_values"])
        self.assertEqual({"repetition_reducer": "mean", "case_reducer": "mean"},
                         metric["extensions"]["arcgrav.shared.reporting:aggregation"])
        self.assertEqual(self.selected["primary_metric"]["metric_id"], metric["metric_id"])
        scorer = self.resource(self.selected["scorer"]["registration_artifact_id"])
        self.assertEqual(self.selected["scorer"]["registration_id"], scorer["registration_id"])
        entrypoints = (
            self.selected["parser"]["entry_point"],
            scorer["extensions"]["arcgrav.shared.runtime.orchestration:scorer-entry-point"],
        )
        for entrypoint in entrypoints:
            module, function = entrypoint.split(":")
            self.assertTrue(callable(getattr(importlib.import_module(module), function)))


if __name__ == "__main__":
    unittest.main()
