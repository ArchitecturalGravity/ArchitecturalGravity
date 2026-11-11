"""Independent Qt-free evidence for non-expanding wildcard glyph observations.

A source-visible asterisk outside illustrated literal candidates is only a
gap-associated recognition candidate. Neither single/adjacent glyphs nor this
fixture establish path grammar, expansion, validity, or version admission.
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
        profile="wildcard-fixture", configuration=configuration,
    )


def occurrences_of(result, kind):
    return tuple(item for item in result.occurrences if item.kind == kind)


class RecognitionWildcardTests(unittest.TestCase):
    def test_guide_patterns_retain_each_exact_glyph_and_gap_without_expanding(self):
        source = (
            "Scope:\r\n"
            "- Data_*.txt\n"
            "- Guide/Syntax/*.md\r"
            "- src/**/index.ts\u2028"
            "Files: *Service.test.ts\n"
            "- **/*.json\n"
            "Plain prose * remains unclassified\n"
            "=> glob.glob('*.arc') ↳\n"
        )
        result = recognize_source(session(source))
        glyphs = occurrences_of(result, "wildcard_candidate")
        expected = [offset for offset, char in enumerate(source) if char == "*"]
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [item.span for item in glyphs],
            [SourceSpan(start, start + 1) for start in expected],
        )
        self.assertEqual(
            [item.kind for item in result.observations],
            ["section_header_candidate", "unordered_list_candidate",
             "unordered_list_candidate", "unordered_list_candidate",
             "section_scalar_candidate", "unordered_list_candidate",
             "unclassified", "operation_candidate"],
        )
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in result.regions))
        self.assertEqual(
            [item.span.extract(source) for item in glyphs], ["*"] * len(expected)
        )
        self.assertEqual(
            [item.span.start for item in result.occurrences],
            sorted(item.span.start for item in result.occurrences),
        )
        binders = occurrences_of(result, "block_binding_candidate")
        self.assertEqual([item.span.extract(source) for item in binders], [" ↳"])
        surface = 'syntax.wildcard'
        self.assertIsNotNone(surface)
        for item in glyphs:
            self.assertEqual(item.claim_class, "recognition")
            self.assertEqual(item.syntax_id, surface)
            self.assertEqual(item.limitations, EXPECTED_LIMITATIONS[item.kind])
        # Adjacent stars remain separate source glyphs, not an inferred
        # recursive wildcard production or an expanded set of paths.
        double_start = source.index("**")
        self.assertEqual(
            [item.span.start for item in glyphs
             if double_start <= item.span.start < double_start + 2],
            [double_start, double_start + 1],
        )
        self.assertEqual(result.claim_class, "recognition")

    def test_paired_alternate_width_and_unclosed_literals_shield_asterisks(self):
        source = (
            "- outside/*.arc\n"
            '"""\n'
            "- hidden/**/a.arc\n"
            '""""\n'
            '"""\n'
            "- outside2/*.arc\n"
            '""""\n'
            "- hidden/to/EOF/*.arc"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [item.kind for item in result.observations],
            ["unordered_list_candidate", "literal_open", "literal_content",
             "literal_content", "literal_close", "unordered_list_candidate",
             "unterminated_literal_open", "unterminated_literal_content"],
        )
        self.assertEqual(
            [item.span.start for item in occurrences_of(result, "wildcard_candidate")],
            [source.index("*"), source.index("*", source.index("outside2"))],
        )
        self.assertFalse(occurrences_of(result, "block_binding_candidate"))

    def test_occurrences_validate_original_source_region_and_literal_boundary(self):
        source = '- *.arc\n"""\n- hidden/*.arc\n"""\n'
        result = recognize_source(session(source))
        valid = occurrences_of(result, "wildcard_candidate")[0]
        self.assertEqual(valid.span.extract(source), "*")
        hidden_start = source.index("*", source.index("hidden"))
        for invalid in (
            SourceOccurrence(SourceSpan(0, 1), "wildcard_candidate"),
            SourceOccurrence(
                SourceSpan(valid.span.start, valid.span.end + 1),
                "wildcard_candidate",
            ),
            SourceOccurrence(
                SourceSpan(hidden_start, hidden_start + 1),
                "wildcard_candidate",
            ),
        ):
            with self.subTest(span=invalid.span), self.assertRaises(ValueError):
                RecognitionResult(
                    result.session, result.regions, result.observations, (invalid,)
                )
        with self.assertRaises(ValueError):
            RecognitionResult(
                result.session, result.regions, result.observations, (valid, valid)
            )
        with self.assertRaises(TypeError):
            SourceOccurrence("not a span", "wildcard_candidate")
        with self.assertRaises(ValueError):
            SourceOccurrence(valid.span, "unknown")
        with self.assertRaises(FrozenInstanceError):
            valid.kind = "unclassified"

    def test_fixed_context_and_document_text_cannot_trigger_external_actions(self):
        source = (
            "Files:\r\n"
            "- src/**/index.ts\n"
            "=> os.system('do not run') glob.glob('*.arc')\n"
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
            [item.span.extract(source) for item in occurrences_of(
                result, "wildcard_candidate"
            )], ["*", "*", "*"],
        )
        self.assertEqual(result.session.configuration, first.configuration)
        self.assertEqual(recognize_source(session("")).occurrences, ())


if __name__ == "__main__":
    unittest.main()
