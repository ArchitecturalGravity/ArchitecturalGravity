"""Independent Qt-free evidence for conservative backticked-name recognition.

The Patterns guide establishes a representation convention, not a new syntax
surface or normative grammar. A source-visible candidate carries the existing
structural-reference-resolution gap, never a resolved target or validity claim.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import SourceSession
from AgStudio.shared.recognition import (
    RecognitionResult, SourceOccurrence, SourceSpan, recognize_source,
)

TICK = chr(96)


def session(source, *, configuration=None):
    return SourceSession(
        source, arcgrav_version="unverified-test-version",
        profile="reference-fixture", configuration=configuration,
    )


def references(result):
    return tuple(o for o in result.occurrences
                 if o.kind == "backticked_reference_candidate")


class RecognitionReferenceTests(unittest.TestCase):
    def test_exact_guide_shaped_names_preserve_lines_and_other_occurrences(self):
        source = (
            "Task:\r\n"
            f"- Group [Records] by {TICK}accountId{TICK}\n"
            "[Schema]:\n"
            f"  - {TICK}status{TICK}: string\r\n"
            f"=> Set {TICK}status{TICK} to done ↳\n"
            f"Prose {TICK}model.field{TICK} remains unclassified *\n"
        )
        result = recognize_source(session(source))
        names = ("accountId", "status", "status", "model.field")
        expected = [TICK + name + TICK for name in names]
        self.assertEqual([o.span.extract(source) for o in references(result)],
                         expected)
        cursor = 0
        spans = []
        for token in expected:
            start = source.index(token, cursor)
            spans.append(SourceSpan(start, start + len(token)))
            cursor = start + len(token)
        self.assertEqual([o.span for o in references(result)], spans)
        self.assertEqual([o.kind for o in result.observations],
                         ["section_header_candidate", "unordered_list_candidate",
                          "section_header_candidate", "unordered_list_candidate",
                          "operation_candidate", "unclassified"])
        self.assertEqual([o.span.extract(source) for o in result.occurrences
                          if o.kind == "symbol_candidate"],
                         ["[Records]", "[Schema]"])
        self.assertEqual([o.span.extract(source) for o in result.occurrences
                          if o.kind == "wildcard_candidate"], ["*"])
        self.assertEqual([o.span.extract(source) for o in result.occurrences
                          if o.kind == "block_binding_candidate"], [" ↳"])
        self.assertEqual([o.span.extract(source) for o in result.occurrences
                          if o.kind == "indentation_candidate"], ["  "])
        self.assertEqual([o.span.start for o in result.occurrences],
                         sorted(o.span.start for o in result.occurrences))
        self.assertEqual(result.source, result.round_trip())
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))

        self.assertTrue(all(o.syntax_id is None for o in references(result)))
        self.assertTrue(all(o.limitations == EXPECTED_LIMITATIONS[o.kind]
                            and o.claim_class == "recognition"
                            for o in references(result)))

    def test_unsupported_boundaries_are_deferred_without_false_admission(self):
        source = (
            f"{TICK}unclosed\n"
            f"double {TICK}{TICK}code{TICK}{TICK}\n"
            f"escaped \\{TICK}name{TICK}\n"
            f"inner {TICK}two words{TICK}\n"
            f"leading {TICK} name{TICK}\n"
            f"trailing {TICK}name {TICK}\n"
            f"brackets {TICK}[Name]{TICK}\n"
            f"wildcard {TICK}*.arc{TICK}\n"
            f"slash {TICK}has\\slash{TICK}\n"
            f"supported {TICK}valid_2{TICK}\n"
        )
        result = recognize_source(session(source))
        self.assertEqual([o.span.extract(source) for o in references(result)],
                         [TICK + "valid_2" + TICK])
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(result.claim_class, "recognition")
        self.assertEqual([o.span.extract(source) for o in result.occurrences
                          if o.kind == "wildcard_candidate"], ["*"])

    def test_paired_alternate_and_unclosed_literals_shield_reference_candidates(self):
        source = (
            f"Outside {TICK}visible{TICK}\n"
            '"""\n'
            f"Hidden {TICK}triple{TICK}\n"
            '""""\n'
            f"Hidden {TICK}nested{TICK}\n"
            '"""\n'
            f"Outside {TICK}visible_again{TICK}\n"
            '""""\n'
            f"Hidden {TICK}until_eof{TICK}\n"
        )
        result = recognize_source(session(source))
        self.assertEqual([o.span.extract(source) for o in references(result)],
                         [TICK + "visible" + TICK,
                          TICK + "visible_again" + TICK])
        self.assertEqual([o.kind for o in result.observations],
                         ["unclassified", "literal_open", "literal_content",
                          "literal_content", "literal_content", "literal_close", "unclassified",
                          "unterminated_literal_open",
                          "unterminated_literal_content"])
        self.assertEqual(result.round_trip(), source)

    def test_spans_must_match_original_pair_and_cannot_overlap_or_escape_literals(self):
        source = (
            f"First {TICK}valid{TICK} and {TICK}other{TICK}\n"
            '"""\n'
            f"Hidden {TICK}secret{TICK}\n"
            '"""\n'
        )
        result = recognize_source(session(source))
        valid, other = references(result)
        hidden = source.index(TICK + "secret" + TICK)
        invalid = (
            SourceOccurrence(SourceSpan(valid.span.start + 1, valid.span.end),
                             "backticked_reference_candidate"),
            SourceOccurrence(SourceSpan(valid.span.start, valid.span.end - 1),
                             "backticked_reference_candidate"),
            SourceOccurrence(SourceSpan(hidden, hidden + len(TICK + "secret" + TICK)),
                             "backticked_reference_candidate"),
        )
        for item in invalid:
            with self.subTest(span=item.span), self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, (item,))
        for items in ((valid, valid), (other, valid)):
            with self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, items)
        with self.assertRaises(TypeError):
            SourceOccurrence("not a span", "backticked_reference_candidate")
        with self.assertRaises(FrozenInstanceError):
            valid.kind = "unclassified"

    def test_fixed_context_repeatability_and_document_action_text_is_inert(self):
        source = (
            f"Task: {TICK}os.system('never'){TICK}\r\n"
            f"=> {TICK}glob.glob('*.arc'){TICK} [Result]\n"
            f"Prose {TICK}socket.create_connection{TICK}\n"
        )
        first = session(source, configuration={"z": [1], "a": {"ok": True}})
        same = session(source, configuration={"a": {"ok": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection",
                        side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(same))
        self.assertEqual([o.span.extract(source) for o in references(result)],
                         [TICK + "os.system('never')" + TICK,
                          TICK + "socket.create_connection" + TICK])
        # The wildcard in the middle pair is still an independent raw glyph;
        # that overlapping shape is not admitted as an isolated reference.
        self.assertEqual([o.span.extract(source) for o in result.occurrences
                          if o.kind == "wildcard_candidate"], ["*"])
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(result.session.configuration, first.configuration)
        self.assertEqual(recognize_source(session("")).occurrences, ())


if __name__ == "__main__":
    unittest.main()
