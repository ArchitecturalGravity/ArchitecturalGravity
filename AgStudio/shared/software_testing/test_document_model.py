"""Qt-free checks of the shared Stage 02 source and relationship contract."""

from dataclasses import FrozenInstanceError
import sys
import unittest
from unittest import mock

from AgStudio.shared import LanguageCore
from AgStudio.shared.document import ParsedDocument, SourcePoint, parse_document
from AgStudio.shared.recognition import SourceSpan, recognize_source


VERSION = "unverified-test-version"


def session(source, configuration=None):
    return LanguageCore.open_source(
        source, arcgrav_version=VERSION, profile="document-model-fixture",
        configuration=configuration,
    )


class ParsedDocumentTests(unittest.TestCase):
    def test_exact_physical_coordinates_and_reconstruction(self):
        source = "Task:\r\nα\u2028- Item\n"
        first = parse_document(session(source, {"z": [1], "a": True}))
        second = LanguageCore.parse_document(session(source, {"a": True, "z": [1]}))
        self.assertEqual(first, second)
        self.assertEqual(first.document_id, second.document_id)
        self.assertEqual(first.source, source)
        self.assertEqual(first.recognition.round_trip(), source)
        self.assertEqual(first.line_starts, (0, 7, 9, len(source)))
        self.assertEqual(first.position(0), SourcePoint(0, 1, 1))
        self.assertEqual(first.position(6), SourcePoint(6, 1, 7))
        self.assertEqual(first.position(7), SourcePoint(7, 2, 1))
        self.assertEqual(first.position(9), SourcePoint(9, 3, 1))
        self.assertEqual(first.position(len(source)),
                         SourcePoint(len(source), 4, 1))
        line = first.source_range(SourceSpan(7, 9))
        self.assertEqual((line.start.line, line.end.line), (2, 3))
        self.assertEqual(line.span.extract(source), "α\u2028")
        self.assertEqual(first.at(len(source)), ())
        with self.assertRaises(ValueError):
            first.position(-1)
        with self.assertRaises(ValueError):
            first.position(len(source) + 1)
        with self.assertRaises(ValueError):
            first.source_range(SourceSpan(0, len(source) + 1))
        with self.assertRaises(FrozenInstanceError):
            first.document_id = "changed"
        self.assertNotEqual(first.document_id,
                            parse_document(session(source, {"a": False, "z": [1]})).document_id)

    def test_indexes_trust_recovery_and_literal_exclusion(self):
        source = (
            "Task: value\n"
            "- Use [Source] and src/*.arc\n"
            "=>\n"
            "[Open\n"
            '"""\n'
            "- Hidden [Symbol] * ↳\n"
            '"""\n'
            "Visible [Ref]\n"
        )
        document = parse_document(session(source))
        self.assertEqual(document.source, source)
        self.assertIn("section_scalar_candidate", document.structural_index)
        self.assertIn("unordered_list_candidate", document.structural_index)
        self.assertIn("wildcard_candidate", document.occurrence_index)
        self.assertEqual(
            [fact.span.extract(source) for fact in document.facts("occurrence", "wildcard_candidate")],
            ["*"],
        )
        literal_start = source.index("- Hidden")
        self.assertEqual(document.at(literal_start), ())
        self.assertTrue(all(fact.span.start != literal_start
                            for fact in document.facts()))
        bare_arrow = next(fact for fact in document.structural_facts
                          if fact.span.extract(source) == "=>\n")
        self.assertEqual(bare_arrow.source_trust, "recovered_untrusted")
        self.assertEqual(bare_arrow.recovery.kind, "unfinished_operation")
        self.assertEqual(bare_arrow.recovery.kind, "unfinished_operation")
        unfinished = next(fact for fact in document.occurrence_facts
                          if fact.kind == "symbol_boundary_candidate")
        self.assertEqual(unfinished.source_trust, "recovered_untrusted")
        self.assertEqual(unfinished.recovery.kind, "unfinished_symbol")
        self.assertEqual([item.kind for item in document.recoveries],
                         ["unfinished_operation", "unfinished_symbol"])

        symbol = next(fact for fact in document.occurrence_facts
                      if fact.span.extract(source) == "[Source]")
        relations = [document.relationship(symbol.id, kind)
                     for kind in ("containment", "ownership", "identity")]
        self.assertEqual([item.kind for item in relations],
                         ["containment", "ownership", "identity"])
        self.assertTrue(all(item.status == "untrusted" and item.target_fact_id is None
                            for item in relations))
        with self.assertRaises(KeyError):
            document.relationship("missing", "identity")
        with self.assertRaises(ValueError):
            document.facts("other")

    def test_fixed_context_is_inert_and_qt_free(self):
        source = (
            "=> glob.glob('*.arc') [Source] *\n"
            '"""\n'
            "os.system('never run') [Hidden] *\n"
            '"""\n'
        )
        original_configuration = {"scope": ["local"]}
        original = session(source, original_configuration)
        original_configuration["scope"].append("caller mutation")
        with (
            mock.patch("builtins.open", side_effect=AssertionError("filesystem")),
            mock.patch("glob.glob", side_effect=AssertionError("expansion")),
            mock.patch("os.system", side_effect=AssertionError("process")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            document = LanguageCore.parse_document(original)
            repeated = LanguageCore.parse_document(session(source, {"scope": ["local"]}))
        self.assertEqual(document, repeated)
        self.assertEqual(document.session.configuration, {"scope": ["local"]})
        self.assertNotIn("PySide6", sys.modules)
        self.assertEqual(sum(fact.kind == "wildcard_candidate"
                             for fact in document.occurrence_facts), 2)
        self.assertTrue(all(fact.claim_class == "recognition"
                            for fact in document.facts()))
        with self.assertRaises(TypeError):
            ParsedDocument("not recognition")

    def test_independent_consumers_share_one_model_without_reparsing(self):
        source = "Task:\n- Use [Field] *\n"
        opened = session(source)
        with mock.patch("AgStudio.shared.document.model.recognize_source",
                        wraps=recognize_source) as recognizer:
            document = LanguageCore.parse_document(opened)

            def outline(model):
                return tuple((fact.id, fact.source_range.start)
                             for fact in model.facts("structure"))

            def occurrence_navigation(model):
                return tuple((fact.id, model.position(fact.span.start))
                             for fact in model.facts("occurrence"))

            structure = outline(document)
            occurrences = occurrence_navigation(document)
            self.assertEqual(recognizer.call_count, 1)

        self.assertTrue(structure)
        self.assertTrue(occurrences)
        self.assertEqual(structure[0][1], SourcePoint(0, 1, 1))
        self.assertEqual(occurrences[0][1].line, 2)
        copied_index = document.structural_index
        copied_index.clear()
        self.assertTrue(document.structural_index)
        for fact in document.facts():
            for kind in ("containment", "ownership", "identity"):
                self.assertEqual(document.relationship(fact.id, kind).status,
                                 "untrusted")


if __name__ == "__main__":
    unittest.main()
