"""Qt-free evidence for narrow, non-normative unfinished symbol source fragments.

An unescaped terminal [Identifier-like fragment is a gap-bound source observation,
not accepted symbol syntax, an invalidity verdict, or a recovered reference.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import SourceSession
from AgStudio.shared.recognition import (
    RecognitionResult, SourceOccurrence, SourceSpan, recognize_source,
)


VERSION = "unverified-test-version"
SYMBOL_GAPS = (
    "CORE-GAP-SYMBOL-NAME",
    "CORE-GAP-SYMBOL-DEFINITION",
    "CORE-GAP-STRUCTURAL-REFERENCE-RESOLUTION",
)


def session(source, configuration=None):
    return SourceSession(
        source, arcgrav_version=VERSION,
        profile="unfinished-symbol-recognition-fixture",
        configuration=configuration,
    )


def boundaries(result):
    return tuple(o for o in result.occurrences
                 if o.kind == "symbol_boundary_candidate")


class UnfinishedSymbolBoundaryTests(unittest.TestCase):
    def test_terminal_unfinished_shapes_keep_exact_gap_bound_source(self):
        source = (
            "Scope: [Open\r\n"
            "Ordinary prose [Tail  \n"
            "[Standalone\u2028"
            "[Complete] [Another\n"
            "- [Child\n"
            '"""\n'
            "Hidden [Inside\n"
            '"""\n'
            '""""\n'
            "Hidden to EOF [Last"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_scalar_candidate", "unclassified", "unclassified",
             "unclassified", "unordered_list_candidate", "literal_open",
             "literal_content", "literal_close",
             "unterminated_literal_open", "unterminated_literal_content"],
        )
        expected = ["[Open", "[Tail", "[Standalone", "[Another", "[Child"]
        self.assertEqual([o.span.extract(source) for o in boundaries(result)], expected)
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "symbol_candidate"],
            ["[Complete]"],
        )
        for occurrence in boundaries(result):
            self.assertEqual(occurrence.claim_class, "recognition")
            self.assertEqual(occurrence.syntax_id, "syntax.symbol")
            self.assertEqual(occurrence.limitations, EXPECTED_LIMITATIONS[occurrence.kind])
            self.assertEqual(occurrence.span.extract(source)[0], "[")
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in result.regions))
        self.assertTrue(all(not (source.index("Hidden [Inside")
                                 <= o.span.start < len(source))
                            for o in result.occurrences))
        cursor = 0
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span.start, cursor)
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            cursor = region.span.end
        self.assertEqual(cursor, len(source))
        self.assertEqual(result.claim_class, "recognition")

    def test_escapes_nested_and_nonidentifier_boundaries_remain_deferred(self):
        source = (
            "\\[Escaped\n"
            "[[Nested\n"
            "[Bad-Name\n"
            "[Has Space\n"
            "[1\n"
            "[Closed]\n"
            "[Earlier [Nested\n"
            "[Tail plus words\n"
            "Ordinary prose α🪐\n"
            "[Balanced] followed by [Closed]\n"
            "[Complete] [Trailing  \n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual([o.span.extract(source) for o in boundaries(result)],
                         ["[Trailing"])
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "symbol_candidate"],
            ["[Closed]", "[Balanced]", "[Closed]", "[Complete]"],
        )
        self.assertTrue(all(o.kind == "unclassified"
                            for o in result.observations))
        self.assertTrue(all(o.syntax_id is None and o.limitations == ()
                            for o in result.observations))

    def test_misaligned_and_literal_occurrences_are_rejected(self):
        source = '[Complete] [Open\n"""\n[Hidden\n"""\n'
        result = recognize_source(session(source))
        (actual,) = boundaries(result)
        complete_at = source.index("[Complete]")
        hidden_at = source.index("[Hidden")
        invalid = (
            SourceOccurrence(SourceSpan(actual.span.start + 1, actual.span.end),
                             "symbol_boundary_candidate"),
            SourceOccurrence(SourceSpan(actual.span.start, actual.span.end - 1),
                             "symbol_boundary_candidate"),
            SourceOccurrence(SourceSpan(complete_at, complete_at + len("[Complete]")),
                             "symbol_boundary_candidate"),
            SourceOccurrence(SourceSpan(hidden_at, hidden_at + len("[Hidden")),
                             "symbol_boundary_candidate"),
        )
        for occurrence in invalid:
            with self.subTest(span=occurrence.span), self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, (occurrence,))
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              result.observations, (actual, actual))
        with self.assertRaises(FrozenInstanceError):
            actual.kind = "symbol_candidate"

    def test_fixed_detached_context_is_repeatable_and_source_actions_are_inert(self):
        source = (
            "Task: [Pending\r\n"
            "Ordinary prose [Another  \n"
            "[Complete] [Last *\n"
            "=> subprocess.run('untrusted') [Final"
        )
        first = session(source, {"z": [1], "a": {"safe": True}})
        equivalent = session(source, {"a": {"safe": True}, "z": [1]})
        with (
            mock.patch("builtins.open", side_effect=AssertionError("filesystem")),
            mock.patch("glob.glob", side_effect=AssertionError("expansion")),
            mock.patch("os.system", side_effect=AssertionError("process")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual([o.span.extract(source) for o in boundaries(result)],
                         ["[Pending", "[Another", "[Final"])
        self.assertIn(("wildcard_candidate", "*"), [
            (o.kind, o.span.extract(source)) for o in result.occurrences
        ])
        self.assertEqual(result.claim_class, "recognition")


if __name__ == "__main__":
    unittest.main()
