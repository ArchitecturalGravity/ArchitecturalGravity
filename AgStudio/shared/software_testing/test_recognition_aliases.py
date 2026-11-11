"""Independent Qt-free evidence for bounded inline alias marker recognition.

Terminal guide-shaped AS [Alias] is observed as a source-exact AS marker next
to an independent symbol token. This establishes no alias grammar, immediate-
context binding, name validity, version applicability or conformance.
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
        profile="alias-recognition-fixture", configuration=configuration,
    )


def aliases(result):
    return tuple(o for o in result.occurrences
                 if o.kind == "alias_marker_candidate")


def symbols(result):
    return tuple(o for o in result.occurrences if o.kind == "symbol_candidate")


class RecognitionAliasTests(unittest.TestCase):
    def test_guide_suffixes_keep_exact_markers_and_independent_symbols(self):
        source = (
            "Task:\r\n"
            "- Extract [Source] AS [Records]\r\n"
            "  1. Normalize [Records] AS [Normalized]\n"
            "Goal: Determine support AS [Fulfillable]\u2028"
            "Collect values AS [Candidates]  \n"
            "Prose without aliases\n"
        )
        result = recognize_source(session(source))
        expected = ("[Records]", "[Normalized]", "[Fulfillable]", "[Candidates]")
        starts = [source.index("AS " + name) for name in expected]
        self.assertEqual([o.span for o in aliases(result)],
                         [SourceSpan(start, start + 3) for start in starts])
        self.assertEqual([o.span.extract(source) for o in aliases(result)],
                         ["AS "] * len(expected))
        self.assertEqual([o.span.extract(source) for o in symbols(result)],
                         ["[Source]", "[Records]", "[Records]", "[Normalized]",
                          "[Fulfillable]", "[Candidates]"])
        self.assertEqual([o.kind for o in result.observations],
                         ["section_header_candidate", "unordered_list_candidate",
                          "ordered_list_candidate", "section_scalar_candidate",
                          "unclassified", "unclassified"])
        surface = 'syntax.alias'
        self.assertIsNotNone(surface)
        for marker, name in zip(aliases(result), expected):
            self.assertEqual(marker.claim_class, "recognition")
            self.assertEqual(marker.syntax_id, surface)
            self.assertEqual(marker.limitations, EXPECTED_LIMITATIONS[marker.kind])
            self.assertEqual(source[marker.span.end:
                                    marker.span.end + len(name)], name)
        self.assertEqual([o.span.start for o in result.occurrences],
                         sorted(o.span.start for o in result.occurrences))
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        self.assertEqual(result.claim_class, "recognition")

    def test_unillustrated_boundaries_defer_while_binder_overlap_is_observed(self):
        source = (
            "AS [NoContext]\n"
            "xAS [Adjacent]\n"
            "x  AS [DoubleSpace]\n"
            "x\tAS [Tab]\n"
            "x AS[MissingSpace]\n"
            "x AS  [DoubleAfter]\n"
            "x as [Lowercase]\n"
            "x AS []\n"
            "x AS [Two Words]\n"
            "x AS [A-B]\n"
            "x AS [[Nested]]\n"
            "x AS [Midline] then prose\n"
            "x AS [WithBinder] ↳\n"
            "x AS [Visible]\n"
        )
        result = recognize_source(session(source))
        self.assertEqual([o.span.start for o in aliases(result)],
                         [source.index("AS [WithBinder]"),
                          source.index("AS [Visible]")])
        self.assertEqual(result.round_trip(), source)
        self.assertNotIn("normative", result.claim_class)

    def test_alias_and_trailing_binder_keep_distinct_exact_occurrences(self):
        source = (
            "=> Derive [Input] AS [Result] ↳\r\n"
            "  => Reuse [Result] AS [Output]\t↳\n"
            '"""\n'
            "Hidden AS [Literal] ↳\n"
            '"""\n'
            "Ordinary AS [Visible] ↳\n"
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
        self.assertEqual([o.span.extract(source) for o in aliases(result)],
                         ["AS ", "AS ", "AS "])
        self.assertEqual([o.span.extract(source) for o in symbols(result)],
                         ["[Input]", "[Result]", "[Result]", "[Output]",
                          "[Visible]"])
        binders = [o for o in result.occurrences
                   if o.kind.startswith("block_binding_")]
        self.assertEqual([(o.kind, o.span.extract(source)) for o in binders],
                         [("block_binding_candidate", " ↳"),
                          ("block_binding_tab_boundary_candidate", "\t↳"),
                          ("block_binding_candidate", " ↳")])
        self.assertTrue(all(o.span.end <= source.index('"""\n') or
                            o.span.start >= source.rindex('"""\n') + 4
                            for o in result.occurrences))

    def test_paired_and_unterminated_literal_candidates_shield_aliases(self):
        source = (
            "Outside AS [Visible]\n"
            '"""\n'
            "Hidden AS [Literal]\n"
            '""""\n'
            '"""\n'
            "Outside AS [Again]\n"
            '""""\n'
            "Hidden AS [UntilEOF]"
        )
        result = recognize_source(session(source))
        self.assertEqual([o.span.start for o in aliases(result)],
                         [source.index("AS [Visible]"), source.index("AS [Again]")])
        self.assertEqual([o.kind for o in result.observations],
                         ["unclassified", "literal_open", "literal_content",
                          "literal_content", "literal_close", "unclassified",
                          "unterminated_literal_open", "unterminated_literal_content"])
        self.assertEqual(result.round_trip(), source)

    def test_reject_fabricated_overlapping_or_literal_contained_markers(self):
        source = 'Extract AS [One] AS [Two]\n"""\nHidden AS [Secret]\n"""\n'
        result = recognize_source(session(source))
        (marker,) = aliases(result)
        self.assertEqual(marker.span.extract(source), "AS ")
        invalid = (
            SourceOccurrence(SourceSpan(marker.span.start - 1, marker.span.end),
                             "alias_marker_candidate"),
            SourceOccurrence(SourceSpan(marker.span.start, marker.span.end - 1),
                             "alias_marker_candidate"),
            SourceOccurrence(SourceSpan(source.index("AS [Secret]"),
                                        source.index("AS [Secret]") + 3),
                             "alias_marker_candidate"),
        )
        for item in invalid:
            with self.subTest(span=item.span), self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, (item,))
        for items in ((marker, marker), (symbols(result)[-1], marker)):
            with self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, items)
        with self.assertRaises(TypeError):
            SourceOccurrence("not a span", "alias_marker_candidate")
        with self.assertRaises(FrozenInstanceError):
            marker.kind = "unclassified"

    def test_fixed_context_repeatability_and_document_actions_are_inert(self):
        source = (
            "Task: os.system('no') AS [Result]\r\n"
            "- glob.glob('*.arc') AS [Matches]\n"
            "https://example.invalid/* AS [Network]\n"
        )
        first = session(source, configuration={"z": [1], "a": {"ok": True}})
        same = session(source, configuration={"a": {"ok": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")):
            with mock.patch("glob.glob", side_effect=AssertionError("expansion")):
                with mock.patch("os.system", side_effect=AssertionError("process")):
                    with mock.patch("subprocess.run", side_effect=AssertionError("process")):
                        with mock.patch("socket.create_connection",
                                        side_effect=AssertionError("network")):
                            result = recognize_source(first)
                            self.assertEqual(result, recognize_source(same))
        self.assertEqual(len(aliases(result)), 3)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(result.session.configuration, first.configuration)
        self.assertEqual(recognize_source(session("")).occurrences, ())


if __name__ == "__main__":
    unittest.main()
