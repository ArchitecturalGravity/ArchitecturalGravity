"""Independent Qt-free evidence for bounded, untrusted recognition recovery.

The two narrow source shapes remain gap-bound candidates. Neither the
candidate nor its recovery limit establishes ArcGrav malformedness or validity.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import LanguageCore, SourceSession
from AgStudio.shared.recognition import (
    RecognitionResult, SourceObservation, SourceRecovery, SourceSpan,
    recognize_source,
)


def session(source, configuration=None):
    return SourceSession(source, arcgrav_version="unverified-test-version",
                         profile="recovery-fixture", configuration=configuration)


class BoundedRecoveryTests(unittest.TestCase):
    def test_unfinished_symbol_resumes_at_each_line_without_consuming_unrelated_source(self):
        source = (
            "Scope: [Open  \r\n"
            "Task: value\n"
            "- [Child\u2028"
            "=> next operation\n"
            "\\[Escaped\n"
            "[[Nested\n"
            "[Bad-Name\n"
            "Ordinary prose *\n"
        )
        original = session(source, {"z": [1], "a": {"safe": True}})
        equivalent = session(source, {"a": {"safe": True}, "z": [1]})
        with (
            mock.patch("builtins.open", side_effect=AssertionError("filesystem")),
            mock.patch("glob.glob", side_effect=AssertionError("expansion")),
            mock.patch("os.system", side_effect=AssertionError("process")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            result = recognize_source(original)
            self.assertEqual(result, recognize_source(equivalent))

        self.assertEqual(result.round_trip(), source)
        self.assertEqual([o.kind for o in result.observations], [
            "section_scalar_candidate", "section_scalar_candidate",
            "unordered_list_candidate", "operation_candidate",
            "unclassified", "unclassified", "unclassified", "unclassified",
        ])
        self.assertEqual([r.span.extract(source) for r in result.recoveries],
                         ["[Open", "[Child"])
        for recovery in result.recoveries:
            self.assertEqual(recovery.kind, "unfinished_symbol")
            self.assertEqual(recovery.trust, "untrusted")
            self.assertEqual(recovery.claim_class, "recognition")
            self.assertEqual(recovery.resume_at,
                             next(region.span.end for region in result.regions
                                  if region.span.start <= recovery.span.start
                                  < region.span.end))
            self.assertEqual(recovery.limitations, EXPECTED_LIMITATIONS[recovery.kind])
            self.assertEqual(recovery.limitations, EXPECTED_LIMITATIONS[recovery.kind])
            self.assertEqual(recovery.limitations, EXPECTED_LIMITATIONS[recovery.kind])
        self.assertEqual(result.occurrences[-1].kind, "wildcard_candidate")

    def test_unterminated_literal_recovers_only_at_eof_and_shields_its_body(self):
        source = (
            "[Before\n"
            '"""\n'
            "[Hidden * ↳\n"
            '"""\n'
            "Task: visible\n"
            '""""\r\n'
            "=> hidden [Inside] * ↳\n"
            '"""\n'  # A different-width delimiter remains shielded.
            "- hidden until EOF\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, result.round_trip())
        self.assertEqual([r.kind for r in result.recoveries],
                         ["unfinished_symbol", "unterminated_literal"])
        unfinished, literal = result.recoveries
        self.assertEqual(unfinished.resume_at, result.regions[0].span.end)
        self.assertEqual(literal.span.start, result.regions[5].span.start)
        self.assertEqual(literal.span.end, len(source))
        self.assertEqual(literal.resume_at, len(source))
        self.assertEqual(literal.limitations, EXPECTED_LIMITATIONS[literal.kind])
        self.assertEqual([o.kind for o in result.observations[5:]],
                         ["unterminated_literal_open"]
                         + ["unterminated_literal_content"] * 3)
        self.assertTrue(all(o.span.end <= literal.span.start
                            for o in result.occurrences))

    def test_recovery_records_must_match_source_evidence_and_cannot_be_mutated(self):
        source = '[Open\r\nTask: value\n"""\n* hidden\n'
        result = recognize_source(session(source))
        symbol, literal = result.recoveries
        with self.assertRaises(FrozenInstanceError):
            symbol.trust = "trusted"
        with self.assertRaises(ValueError):
            SourceRecovery(symbol.span, symbol.span.start, "unfinished_symbol")
        invalid = (
            SourceRecovery(SourceSpan(symbol.span.start + 1, symbol.span.end),
                           symbol.resume_at, "unfinished_symbol"),
            SourceRecovery(symbol.span, symbol.resume_at + 1,
                           "unfinished_symbol"),
            SourceRecovery(SourceSpan(literal.span.start + 1, len(source)),
                           len(source), "unterminated_literal"),
            SourceRecovery(SourceSpan(source.index("*"), source.index("*") + 1),
                           len(source), "unfinished_symbol"),
        )
        for forged in invalid:
            with self.subTest(forged=forged), self.assertRaises(ValueError):
                RecognitionResult(result.session, result.regions,
                                  result.observations, result.occurrences,
                                  (forged,))
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              result.observations, result.occurrences,
                              (literal, symbol))

    def test_literal_shields_and_recovery_cannot_be_silently_removed(self):
        source = '[Open\n"""\nHidden: *\n"""\nVisible: value\n'
        result = recognize_source(session(source))
        self.assertEqual([item.kind for item in result.recoveries],
                         ["unfinished_symbol"])
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              result.observations, result.occurrences, ())
        forged_observations = list(result.observations)
        forged_observations[2] = SourceObservation(
            result.regions[2].span, "unclassified"
        )
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              tuple(forged_observations), result.occurrences,
                              result.recoveries)

        unclosed = recognize_source(session('"""\nHidden: *\n'))
        self.assertEqual([item.kind for item in unclosed.recoveries],
                         ["unterminated_literal"])
        with self.assertRaises(ValueError):
            RecognitionResult(unclosed.session, unclosed.regions,
                              unclosed.observations, unclosed.occurrences, ())
        wrong_content = list(unclosed.observations)
        wrong_content[1] = SourceObservation(
            unclosed.regions[1].span, "literal_content"
        )
        with self.assertRaises(ValueError):
            RecognitionResult(unclosed.session, unclosed.regions,
                              tuple(wrong_content), unclosed.occurrences,
                              unclosed.recoveries)


if __name__ == "__main__":
    unittest.main()
