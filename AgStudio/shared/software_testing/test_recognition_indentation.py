"""Independent Qt-free recognition evidence for exact indentation-prefix shapes.

A complete leading run of two-space units is a source occurrence only: no
grouping, parenthood, indentation level, malformedness or normative version
applicability is inferred. Complete odd ASCII-space runs are separate
gap-bound boundary candidates; tab-bearing runs have separate uncertain
boundary facts; non-ASCII Unicode category Zs-bearing prefixes have their own
uncertain source facts. Whitespace-only and other Unicode whitespace are deferred.
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
        profile="indentation-fixture", configuration=configuration,
    )


def indentations(result):
    return tuple(o for o in result.occurrences if o.kind == "indentation_candidate")


def indentation_boundaries(result):
    return tuple(o for o in result.occurrences
                 if o.kind == "indentation_boundary_candidate")


def tab_boundaries(result):
    return tuple(o for o in result.occurrences
                 if o.kind == "indentation_tab_boundary_candidate")


def unicode_boundaries(result):
    return tuple(o for o in result.occurrences
                 if o.kind == "indentation_unicode_boundary_candidate")


class RecognitionIndentationTests(unittest.TestCase):
    def test_illustrated_prefixes_coexist_with_line_facts_and_keep_exact_ranges(self):
        source = (
            "Key:\r\n"
            "- Parent:\n"
            "  - Child one\r"
            "    => Nested operation\r\n"
            "  [Field]: value\u2028"
            "  Ordinary prose\n"
            " - odd one\n"
            "   - odd three\n"
            "\t  - tab-first\n"
            "  \t- mixed\n"
            "  \n"
            "  - Outside ↳\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations[:6]],
            ["section_header_candidate", "unordered_list_candidate",
             "unordered_list_candidate", "operation_candidate",
             "section_scalar_candidate", "unclassified"],
        )
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in result.regions))
        expected = [
            SourceSpan(source.index(line), source.index(line) + spaces)
            for line, spaces in (
                ("  - Child one", 2),
                ("    => Nested operation", 4),
                ("  [Field]: value", 2),
                ("  Ordinary prose", 2),
                ("  - Outside ↳", 2),
            )
        ]
        self.assertEqual([o.span for o in indentations(result)], expected)
        self.assertEqual([o.span.extract(source) for o in indentations(result)],
                         ["  ", "    ", "  ", "  ", "  "])
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "block_binding_candidate"],
            [" ↳"],
        )
        self.assertEqual(
            [o.span.start for o in result.occurrences],
            sorted(o.span.start for o in result.occurrences),
        )
        surface = 'syntax.grouping'
        self.assertIsNotNone(surface)
        for o in indentations(result):
            self.assertEqual(o.claim_class, "recognition")
            self.assertEqual(o.syntax_id, surface)
            self.assertEqual(o.limitations, EXPECTED_LIMITATIONS[o.kind])
        self.assertEqual(result.claim_class, "recognition")

    def test_odd_and_unsupported_leading_shapes_retain_uncertainty(self):
        source = (
            " - single\n"
            "   - odd\n"
            "\t  - tab-first\n"
            "  \t- mixed\n"
            "  \n"
            "    \r\n"
            "\n"
            "  Plain prose\n"
            "      - six spaces"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.span.extract(source) for o in indentations(result)],
            ["  ", "      "],
        )
        self.assertEqual(
            [o.span.start for o in indentations(result)],
            [source.index("  Plain prose"), source.index("      - six spaces")],
        )
        self.assertEqual(
            [o.span.extract(source) for o in indentation_boundaries(result)],
            [" ", "   "],
        )
        self.assertEqual(
            [o.span.start for o in indentation_boundaries(result)],
            [source.index(" - single"), source.index("   - odd")],
        )
        self.assertEqual([o.span.extract(source) for o in tab_boundaries(result)],
                         ["\t  ", "  \t"])
        for unsupported in ("  \n", "    \r\n"):
            start = source.index(unsupported)
            self.assertFalse(any(
                o.span.start == start and o.kind.startswith("indentation_")
                for o in result.occurrences
            ))
        # The physical text remains unclassified even when its prefix is seen.
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in result.regions))
        self.assertNotIn("normative", result.claim_class)

    def test_illustrated_literal_shields_both_paired_and_unterminated_prefixes(self):
        source = (
            "  - Outside\n"
            '"""\n'
            "  - Hidden under triple\n"
            '""""\n'
            '"""\n'
            "    => Outside again\n"
            '""""\n'
            "      - Hidden until EOF"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unordered_list_candidate", "literal_open", "literal_content",
             "literal_content", "literal_close", "operation_candidate",
             "unterminated_literal_open", "unterminated_literal_content"],
        )
        self.assertEqual(
            [o.span.start for o in indentations(result)],
            [source.index("  - Outside"), source.index("    => Outside again")],
        )

    def test_validation_rejects_fabricated_misaligned_and_shielded_prefixes(self):
        source = '  - A\n"""\n  - Hidden\n"""\n  Plain\n'
        result = recognize_source(session(source))
        valid = indentations(result)[0]
        hidden_start = source.index("  - Hidden")
        invalid = (
            SourceOccurrence(SourceSpan(valid.span.start + 1, valid.span.end),
                             "indentation_candidate"),
            SourceOccurrence(SourceSpan(valid.span.start, valid.span.end + 1),
                             "indentation_candidate"),
            SourceOccurrence(SourceSpan(hidden_start, hidden_start + 2),
                             "indentation_candidate"),
        )
        for occurrence in invalid:
            with self.subTest(span=occurrence.span), self.assertRaises(ValueError):
                RecognitionResult(
                    result.session, result.regions, result.observations, (occurrence,)
                )
        with self.assertRaises(ValueError):
            RecognitionResult(
                result.session, result.regions, result.observations, (valid, valid)
            )
        with self.assertRaises(TypeError):
            SourceOccurrence("not a span", "indentation_candidate")
        with self.assertRaises(ValueError):
            SourceOccurrence(valid.span, "unknown_kind")
        with self.assertRaises(FrozenInstanceError):
            valid.kind = "unclassified"

    def test_odd_prefix_boundaries_are_exact_shielded_validated_and_inert(self):
        source = (
            " - One * ↳\r\n"
            "   => os.system('never execute') [Name]\n"
            "     Plain text\u2028"
            "  - Even\n"
            "\t - tab-first\n"
            " \t- mixed\n"
            "   \n"
            '"""\n'
            " - Hidden\n"
            '"""\n'
            '""""\n'
            "   - Hidden to EOF"
        )
        first = session(source, configuration={"z": [1], "a": {"safe": True}})
        equivalent = session(source, configuration={"a": {"safe": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.source, result.round_trip())
        boundaries = indentation_boundaries(result)
        expected = [
            SourceSpan(source.index(line), source.index(line) + width)
            for line, width in (
                (" - One", 1),
                ("   => os.system", 3),
                ("     Plain text", 5),
            )
        ]
        self.assertEqual([o.span for o in boundaries], expected)
        self.assertEqual([o.span.extract(source) for o in boundaries],
                         [" ", "   ", "     "])
        self.assertEqual([o.span.extract(source) for o in indentations(result)],
                         ["  "])
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        self.assertEqual([o.span.start for o in result.occurrences],
                         sorted(o.span.start for o in result.occurrences))
        for observation in boundaries:
            self.assertEqual(observation.claim_class, "recognition")
            self.assertEqual(observation.syntax_id, "syntax.grouping")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertEqual([o.span.extract(source) for o in tab_boundaries(result)],
                         ["\t ", " \t"])
        for unsupported in ("   \n",
                            " - Hidden", "   - Hidden to EOF"):
            start = source.index(unsupported)
            self.assertFalse(any(
                o.span.start == start and o.kind.startswith("indentation_")
                for o in result.occurrences
            ))
        self.assertEqual(result.observations[-1].kind,
                         "unterminated_literal_content")
        # A mislabeled parity, truncated/misaligned prefix, literal-contained
        # candidate or duplicate cannot be injected into an immutable result.
        bad = (
            SourceOccurrence(boundaries[0].span, "indentation_candidate"),
            SourceOccurrence(indentations(result)[0].span,
                             "indentation_boundary_candidate"),
            SourceOccurrence(SourceSpan(boundaries[1].span.start,
                                        boundaries[1].span.end - 1),
                             "indentation_boundary_candidate"),
            SourceOccurrence(SourceSpan(source.index(" - Hidden"),
                                        source.index(" - Hidden") + 1),
                             "indentation_boundary_candidate"),
        )
        for occurrence in bad:
            with self.subTest(occurrence=occurrence), self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, (occurrence,))
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              result.observations, (boundaries[0], boundaries[0]))
        with self.assertRaises(FrozenInstanceError):
            boundaries[0].kind = "indentation_candidate"

    def test_tab_bearing_prefixes_are_distinct_exact_gap_bound_and_inert(self):
        source = (
            "\t- tab-only\r\n"
            " \t- mixed * ↳\n"
            "\t  => os.system('never execute')\n"
            "  \t[Field]: value\u2028"
            "\t \tPlain prose\n"
            "  - even\n"
            "   - odd\n"
            "\t  \n"
            "  \t\r\n"
            "\u00a0- unicode-led\n"
            '"""\n'
            "\t- Hidden in paired literal\n"
            '"""\n'
            '""""\n'
            " \t- Hidden to EOF"
        )
        first = session(source, configuration={"z": [1], "a": {"safe": True}})
        equivalent = session(source, configuration={"a": {"safe": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in result.regions))
        candidates = tab_boundaries(result)
        expected = [
            SourceSpan(source.index(line), source.index(line) + width)
            for line, width in (
                ("\t- tab-only", 1),
                (" \t- mixed", 2),
                ("\t  => os.system", 3),
                ("  \t[Field]", 3),
                ("\t \tPlain prose", 3),
            )
        ]
        self.assertEqual([o.span for o in candidates], expected)
        self.assertEqual([o.span.extract(source) for o in candidates],
                         ["\t", " \t", "\t  ", "  \t", "\t \t"])
        self.assertEqual([o.span.extract(source) for o in indentations(result)], ["  "])
        self.assertEqual([o.span.extract(source) for o in indentation_boundaries(result)],
                         ["   "])
        self.assertEqual([o.span.extract(source) for o in result.occurrences
                          if o.kind == "wildcard_candidate"], ["*"])
        self.assertEqual([o.span.extract(source) for o in result.occurrences
                          if o.kind == "block_binding_candidate"], [" ↳"])
        self.assertEqual([o.span.start for o in result.occurrences],
                         sorted(o.span.start for o in result.occurrences))
        for candidate in candidates:
            self.assertEqual(candidate.claim_class, "recognition")
            self.assertEqual(candidate.syntax_id, "syntax.grouping")
            self.assertEqual(candidate.limitations, EXPECTED_LIMITATIONS[candidate.kind])
        self.assertEqual(result.claim_class, "recognition")
        self.assertEqual([o.span.extract(source) for o in unicode_boundaries(result)],
                         ["\u00a0"])
        for unsupported in ("\t  \n", "  \t\r\n",
                            "\t- Hidden in paired literal", " \t- Hidden to EOF"):
            start = source.index(unsupported)
            self.assertFalse(any(o.span.start == start and o.kind.startswith("indentation_")
                                 for o in result.occurrences))
        bad = (
            SourceOccurrence(candidates[1].span, "indentation_candidate"),
            SourceOccurrence(SourceSpan(candidates[1].span.start,
                                        candidates[1].span.end - 1),
                             "indentation_tab_boundary_candidate"),
            SourceOccurrence(SourceSpan(source.index("\t- Hidden in paired literal"),
                                        source.index("\t- Hidden in paired literal") + 1),
                             "indentation_tab_boundary_candidate"),
        )
        for occurrence in bad:
            with self.subTest(occurrence=occurrence), self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, (occurrence,))
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              result.observations, (candidates[0], candidates[0]))
        with self.assertRaises(FrozenInstanceError):
            candidates[0].kind = "indentation_candidate"


    def test_unicode_zs_prefixes_are_source_exact_gap_bound_shielded_and_inert(self):
        source = (
            "\u00a0- nbsp * ↳\r\n"
            " \u2003\t=> os.system('never execute') [Name]\n"
            "\t\u2009  Plain prose\u2028"
            "\u200b- other Unicode category\n"
            "\u00a0 \t\n"
            " \u2003\r\n"
            "  - even\n"
            "\t- tab\n"
            '"""\n'
            "\u00a0- hidden in paired literal\n"
            '"""\n'
            '""""\n'
            " \u2003- hidden to EOF"
        )
        first = session(source, configuration={"z": [1], "a": {"safe": True}})
        equivalent = session(source, configuration={"a": {"safe": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        candidates = unicode_boundaries(result)
        expected = [
            SourceSpan(source.index(line), source.index(line) + width)
            for line, width in (
                ("\u00a0- nbsp", 1),
                (" \u2003\t=>", 3),
                ("\t\u2009  Plain", 4),
            )
        ]
        self.assertEqual([o.span for o in candidates], expected)
        self.assertEqual([o.span.extract(source) for o in candidates],
                         ["\u00a0", " \u2003\t", "\t\u2009  "])
        self.assertEqual([o.span.extract(source) for o in indentations(result)], ["  "])
        self.assertEqual([o.span.extract(source) for o in tab_boundaries(result)], ["\t"])
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "wildcard_candidate"], ["*"]
        )
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "block_binding_candidate"], [" ↳"]
        )
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "symbol_candidate"], ["[Name]"]
        )
        self.assertEqual([o.span.start for o in result.occurrences],
                         sorted(o.span.start for o in result.occurrences))
        for candidate in candidates:
            self.assertEqual(candidate.claim_class, "recognition")
            self.assertEqual(candidate.syntax_id, "syntax.grouping")
            self.assertEqual(candidate.limitations, EXPECTED_LIMITATIONS[candidate.kind])
        surface = 'syntax.grouping'
        for unsupported in (
            "\u200b- other Unicode category", "\u00a0 \t\n", " \u2003\r\n",
            "\u00a0- hidden in paired literal", " \u2003- hidden to EOF",
        ):
            start = source.index(unsupported)
            self.assertFalse(any(
                o.span.start == start and o.kind.startswith("indentation_")
                for o in result.occurrences
            ))
        self.assertEqual(result.observations[-1].kind,
                         "unterminated_literal_content")
        bad = (
            SourceOccurrence(candidates[0].span, "indentation_candidate"),
            SourceOccurrence(candidates[1].span, "indentation_tab_boundary_candidate"),
            SourceOccurrence(SourceSpan(candidates[1].span.start,
                                        candidates[1].span.end - 1),
                             "indentation_unicode_boundary_candidate"),
            SourceOccurrence(SourceSpan(source.index("\u00a0 \t\n"),
                                        source.index("\u00a0 \t\n") + 3),
                             "indentation_unicode_boundary_candidate"),
            SourceOccurrence(SourceSpan(source.index("\u00a0- hidden"),
                                        source.index("\u00a0- hidden") + 1),
                             "indentation_unicode_boundary_candidate"),
        )
        for occurrence in bad:
            with self.subTest(occurrence=occurrence), self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, (occurrence,))
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              result.observations, (candidates[0], candidates[0]))
        with self.assertRaises(FrozenInstanceError):
            candidates[0].kind = "indentation_candidate"

    def test_repeatable_fixed_context_and_no_document_directed_actions(self):
        source = (
            "  => os.system('never run') glob.glob('*.arc') ↳\r\n"
            "    - https://example.invalid/path\n"
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
        self.assertEqual(
            [o.kind for o in result.occurrences],
            ["indentation_candidate", "wildcard_candidate",
             "block_binding_candidate", "indentation_candidate"],
        )
        self.assertEqual(
            [o.span.extract(source) for o in indentations(result)], ["  ", "    "]
        )
        self.assertEqual(result.session.configuration, first.configuration)
        self.assertEqual(recognize_source(session("")).occurrences, ())


if __name__ == "__main__":
    unittest.main()
