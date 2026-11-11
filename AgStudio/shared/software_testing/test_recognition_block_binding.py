"""Independent Qt-free evidence for trailing explicit block-binding occurrences.

Marker observations remain recognition only: they establish neither parenthood,
child indentation, version applicability nor ArcGrav conformance.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import SourceSession
from AgStudio.shared.recognition import (
    RecognitionResult, SourceOccurrence, SourceSpan, recognize_source,
)


def session(source, *, configuration=None):
    return SourceSession(
        source, arcgrav_version="unverified-test-version",
        profile="block-binding-fixture", configuration=configuration,
    )


class RecognitionBlockBindingTests(unittest.TestCase):
    def test_guide_suffix_has_exact_offsets_and_independent_line_observations(self):
        source = (
            "=> Operation using [Context] ↳\r\n"
            "  - Child instruction\n"
            "  => Nested operation ↳\r"
            "Task: Keep [Context] ↳\u2028"
            "=> With trailing blanks ↳ \t\n"
            "Ordinary expression ↳"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["operation_candidate", "unordered_list_candidate",
             "operation_candidate", "section_scalar_candidate",
             "operation_candidate", "unclassified"],
        )
        marker_starts = []
        start = 0
        for line in source.splitlines(keepends=True):
            if " ↳" in line:
                marker_starts.append(start + line.index(" ↳"))
            start += len(line)
        binders = tuple(o for o in result.occurrences
                        if o.kind == "block_binding_candidate")
        self.assertEqual(
            [o.span for o in binders],
            [SourceSpan(start, start + 2) for start in marker_starts],
        )
        surface = 'syntax.block_binding'
        self.assertIsNotNone(surface)
        for occurrence in binders:
            self.assertEqual(occurrence.span.extract(source), " ↳")
            self.assertEqual(occurrence.kind, "block_binding_candidate")
            self.assertEqual(occurrence.claim_class, "recognition")
            self.assertEqual(occurrence.syntax_id, surface)
            self.assertEqual(occurrence.limitations, EXPECTED_LIMITATIONS[occurrence.kind])
        self.assertEqual(len(binders), 5)
        self.assertEqual(
            sum(o.kind == "indentation_candidate" for o in result.occurrences), 2
        )
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        self.assertEqual(result.claim_class, "recognition")

    def test_unsupported_marker_boundaries_are_deferred_without_binding_claims(self):
        source = (
            "↳\n"
            " ↳\n"
            "=>WithoutSpace↳\n"
            "=> Mid ↳ tail\n"
            "=> tab\t↳\n"
            "this ↳ is prose\n"
            "↳ is leading\n"
            "=> visible ↳\n"
            "=> more ↳ \t\r\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "block_binding_candidate"], [" ↳", " ↳"]
        )
        self.assertEqual(
            [(o.kind, o.span.extract(source), o.limitations)
             for o in result.occurrences
             if o.kind == "block_binding_tab_boundary_candidate"],
            [('block_binding_tab_boundary_candidate', '\t↳', EXPECTED_LIMITATIONS['block_binding_tab_boundary_candidate'])],
        )
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "indentation_boundary_candidate"], [" "]
        )
        self.assertEqual(
            [o.kind for o in result.observations[:7]],
            ["unclassified", "unclassified", "unclassified",
             "operation_candidate", "operation_candidate", "unclassified",
             "unclassified"],
        )
        self.assertNotIn("normative", result.claim_class)

    def test_tab_boundary_keeps_exact_span_later_source_and_literal_shield(self):
        source = (
            "=> First\t↳\r\n"
            "Task:\t↳\n"
            '"""\n'
            "=> Hidden\t↳\n"
            '"""\n'
            "=> Last\t↳ \t\n"
        )
        first = session(source, configuration={"z": [1], "a": True})
        same = session(source, configuration={"a": True, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(same))
        self.assertEqual(result.round_trip(), source)
        tab_binders = [o for o in result.occurrences
                       if o.kind == "block_binding_tab_boundary_candidate"]
        self.assertEqual([o.span.extract(source) for o in tab_binders],
                         ["\t↳", "\t↳", "\t↳"])
        self.assertEqual([o.syntax_id for o in tab_binders],
                         ["syntax.block_binding"] * 3)
        self.assertTrue(all(o.limitations == EXPECTED_LIMITATIONS[o.kind]
                            for o in tab_binders))
        self.assertTrue(all(o.span.end <= source.index('"""\n') or
                            o.span.start >= source.rindex('"""\n') + 4
                            for o in tab_binders))
        with self.assertRaises(ValueError):
            RecognitionResult(
                result.session, result.regions, result.observations,
                (SourceOccurrence(tab_binders[0].span, "block_binding_candidate"),),
            )

    def test_paired_and_unterminated_literals_shield_marker_occurrences(self):
        source = (
            "=> Outside ↳\n"
            '"""\n'
            "=> Hidden ↳\n"
            '""""\n'
            '"""\n'
            "=> Outside again ↳\n"
            '""""\n'
            "=> Hidden until EOF ↳"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["operation_candidate", "literal_open", "literal_content",
             "literal_content", "literal_close", "operation_candidate",
             "unterminated_literal_open", "unterminated_literal_content"],
        )
        self.assertEqual(
            [o.span.start for o in result.occurrences],
            [source.index(" ↳"), source.index(" ↳", source.index("Outside again"))],
        )

    def test_occurrences_reject_unsourced_literal_cross_region_and_invalid_facts(self):
        source = '=> Valid ↳\n"""\n=> Hidden ↳\n"""\n'
        result = recognize_source(session(source))
        valid = result.occurrences[0]
        self.assertEqual(valid.span.extract(source), " ↳")
        with self.assertRaises(ValueError):
            RecognitionResult(
                result.session, result.regions, result.observations,
                (SourceOccurrence(SourceSpan(0, 2), "block_binding_candidate"),),
            )
        hidden_start = source.index(" ↳", source.index('"""'))
        with self.assertRaises(ValueError):
            RecognitionResult(
                result.session, result.regions, result.observations,
                (SourceOccurrence(
                    SourceSpan(hidden_start, hidden_start + 2),
                    "block_binding_candidate",
                ),),
            )
        with self.assertRaises(ValueError):
            RecognitionResult(
                result.session, result.regions, result.observations,
                (SourceOccurrence(
                    SourceSpan(valid.span.start, valid.span.end + 1),
                    "block_binding_candidate",
                ),),
            )
        with self.assertRaises(ValueError):
            RecognitionResult(
                result.session, result.regions, result.observations,
                (valid, valid),
            )
        with self.assertRaises(TypeError):
            SourceOccurrence("not a span", "block_binding_candidate")
        with self.assertRaises(ValueError):
            SourceOccurrence(valid.span, "unsupported_kind")
        with self.assertRaises(FrozenInstanceError):
            valid.kind = "unsupported_kind"

    def test_context_repeatability_and_no_document_directed_actions(self):
        source = (
            "=> os.system('do not execute') ↳\r\n"
            "  - glob.glob('**/*.arc')\n"
            "Task: https://example.invalid/* ↳\n"
        )
        first = session(source, configuration={"z": [1], "a": {"ok": True}})
        same = session(source, configuration={"a": {"ok": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(same))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(sum(item.kind == "block_binding_candidate"
                             for item in result.occurrences), 2)
        self.assertEqual(sum(item.kind == "wildcard_candidate"
                             for item in result.occurrences), 4)
        self.assertEqual(result.session.configuration, first.configuration)
        self.assertEqual(recognize_source(session("")).occurrences, ())


if __name__ == "__main__":
    unittest.main()
