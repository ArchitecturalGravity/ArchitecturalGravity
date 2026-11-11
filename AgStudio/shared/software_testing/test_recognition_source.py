"""Independent, Qt-free Stage 01 source-preservation evidence.

These are recognition-only cases, not normative ArcGrav conformance fixtures.
Source-partition checks alone do not establish named-family coverage, complete
literal isolation or recovery; these have separate fixtures and remaining
Stage 01 obligations.
"""

import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import LanguageCore, SourceSession
from AgStudio.shared.recognition import (
    RecognitionResult, SourceRegion, SourceSpan, recognize_source,
)


class RecognitionSourceTests(unittest.TestCase):
    @staticmethod
    def session(source, *, configuration=None):
        return SourceSession(
            source, arcgrav_version="unverified-test-version",
            profile="fixture", configuration=configuration,
        )

    def assert_exact_partition(self, source):
        result = recognize_source(self.session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(result.claim_class, "recognition")
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        cursor = 0
        for region in result.regions:
            self.assertEqual(region.span.start, cursor)
            self.assertEqual(region.span.end, cursor + len(region.text))
            self.assertEqual(region.span.extract(source), region.text)
            cursor = region.span.end
        self.assertEqual(cursor, len(source))
        return result

    def test_empty_and_unterminated_source(self):
        self.assertEqual(self.assert_exact_partition("").regions, ())
        self.assertEqual(
            [r.text for r in self.assert_exact_partition("No final newline ").regions],
            ["No final newline "],
        )

    def test_mixed_terminators_and_unicode_are_preserved(self):
        source = "α🪐\r\n\tβ  \nγ\rδ\u2028\x00malformed"
        result = self.assert_exact_partition(source)
        self.assertEqual(
            [r.text for r in result.regions],
            ["α🪐\r\n", "\tβ  \n", "γ\r", "δ\u2028", "\x00malformed"],
        )

    def test_mixed_arcgrav_like_prose_literal_and_malformed_text(self):
        source = (
            "Scope:  \r\n  - Item => [Anchor] AS [Alias] ↳\n"
            "plain language with \x60quoted [Reference]\x60 and **/*.arc\r"
            '"""\n=> not an instruction\n- not a list\n"""\n'
            "[unterminated \n"
        )
        result = self.assert_exact_partition(source)
        self.assertEqual(len(result.regions), 8)
        self.assertIn("=> not an instruction", result.round_trip())
        self.assertNotIn("normative", result.claim_class)

    def test_same_fixed_context_has_same_result_and_detached_configuration(self):
        source = "[Input]:\n- value\n"
        first = self.session(source, configuration={"z": [1], "a": {"ok": True}})
        second = self.session(source, configuration={"a": {"ok": True}, "z": [1]})
        first_result = recognize_source(first)
        self.assertEqual(first_result, recognize_source(second))
        copied = first_result.session.configuration
        copied["z"].append(2)
        self.assertEqual(first_result, recognize_source(first))
        self.assertEqual(first_result.session.configuration["z"], [1])

    def test_stage_zero_session_handoff_retains_context_gaps_and_recovery_trust(self):
        source = "Task:\r\n[Open\nOrdinary prose"
        configuration = {"z": [1], "a": {"safe": True}}
        opened = LanguageCore.open_source(
            source, arcgrav_version="unsupported-version", profile="handoff",
            configuration=configuration,
        )
        configuration["z"].append("caller mutation")
        result = recognize_source(opened)
        repeated = recognize_source(LanguageCore.open_source(
            source, arcgrav_version="unsupported-version", profile="handoff",
            configuration={"a": {"safe": True}, "z": [1]},
        ))
        self.assertEqual(result, repeated)
        self.assertEqual(result.session, opened)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(result.session.arcgrav_version, "unsupported-version")
        self.assertEqual(result.session.profile, "handoff")
        self.assertEqual(result.session.configuration["z"], [1])
        self.assertEqual([o.kind for o in result.observations],
                         ["section_header_candidate", "unclassified", "unclassified"])
        self.assertEqual(result.observations[0].limitations, EXPECTED_LIMITATIONS[result.observations[0].kind])
        self.assertEqual([o.kind for o in result.occurrences],
                         ["symbol_boundary_candidate"])
        self.assertEqual(result.recoveries[0].trust, "untrusted")
        self.assertEqual(result.recoveries[0].limitations, EXPECTED_LIMITATIONS[result.recoveries[0].kind])

    def test_inert_contents_and_no_external_action(self):
        source = "=> run os.system('echo dangerous')\n- https://example.invalid/*\n"
        session = self.session(source)
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem access")), \
             mock.patch("os.system", side_effect=AssertionError("process execution")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process execution")):
            self.assert_exact_partition(source)
            self.assertEqual(recognize_source(session).source, source)

    def test_reject_non_session_and_broken_partitions(self):
        with self.assertRaises(TypeError):
            recognize_source("not a session")
        for bounds in [(-1, 0), (3, 2)]:
            with self.assertRaises(ValueError):
                SourceSpan(*bounds)
        with self.assertRaises(TypeError):
            SourceSpan(True, 1)
        session = self.session("a\nb")
        for broken in [
            (SourceRegion(SourceSpan(0, 2), "a\n"),),
            (SourceRegion(SourceSpan(1, 3), "\nb"),),
            (SourceRegion(SourceSpan(0, 3), "xxx"),),
        ]:
            with self.assertRaises(ValueError):
                RecognitionResult(session, broken)


if __name__ == "__main__":
    unittest.main()
