"""Qt-free evidence for non-ASCII Zs-led compact section-shaped ambiguity.

A leading Unicode space separator is not guide-backed section indentation.
The whole-line section boundary and independent exact grouping-prefix fact
retain separate unresolved Stage 00 gaps, never grammar or conformance.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import LanguageCore, SourceSession
from AgStudio.shared.recognition import recognize_source


VERSION = "unverified-test-version"


def session(source, configuration=None):
    return SourceSession(
        source, arcgrav_version=VERSION, profile="unicode-leading-section-fixture",
        configuration=configuration,
    )


class UnicodeLeadingSectionBoundaryTests(unittest.TestCase):
    def test_zs_led_compact_lines_retain_exact_independent_gap_bound_facts(self):
        source = (
            "\u00a0Scope:\r\n"
            " \u2003Task: value\n"
            "\t\u202f[OnComplete]:\tNext\u2028"
            "\u3000Scope :Next\n"
            "\u00a0 \tScope:\u2003Value\n"
            "  Scope:\n"
            "Scope: value\n"
            "\u00a0 Two words: value\n"
            "\u200bScope: value\n"
            "\u00a0Scope:/path\n"
            "\u2003[Broken: value\n"
            "\u00a0Plain prose\n"
            "\u00a0 \t\n"
            "\u00a0Scope: [Field] * ↳\n"
            '"""\n'
            "\u00a0Hidden: value [Symbol] * ↳\n"
            '"""\n'
            '""""\n'
            "\u00a0Task: hidden at EOF\n"
        )
        configuration = {"z": {"choices": [1, "δ"]}, "a": [True]}
        first_session = session(source, configuration)
        configuration["z"]["choices"].append("caller mutation")
        equivalent = session(source, {"a": [True], "z": {"choices": [1, "δ"]}})
        with (
            mock.patch("builtins.open", side_effect=AssertionError("filesystem")),
            mock.patch("glob.glob", side_effect=AssertionError("expansion")),
            mock.patch("os.system", side_effect=AssertionError("process")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            result = recognize_source(first_session)
            for _ in range(3):
                self.assertEqual(result, recognize_source(equivalent))

        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(first_session.configuration["z"]["choices"], [1, "δ"])
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_boundary_candidate"] * 5
            + ["section_header_candidate", "section_scalar_candidate"]
            + ["unclassified"] * 6
            + ["section_boundary_candidate"]
            + ["literal_open", "literal_content", "literal_close",
               "unterminated_literal_open", "unterminated_literal_content"],
        )
        cursor = 0
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span.start, cursor)
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(region.disposition, "unclassified")
            self.assertEqual(observation.claim_class, "recognition")
            cursor = region.span.end
        self.assertEqual(cursor, len(source))
        for index in (0, 1, 2, 3, 4, 13):
            observation = result.observations[index]
            self.assertEqual(observation.kind, "section_boundary_candidate")
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertTrue(all(result.observations[i].syntax_id is None
                            and result.observations[i].limitations == ()
                            for i in range(7, 13)))

        unicode_prefixes = [
            o for o in result.occurrences
            if o.kind == "indentation_unicode_boundary_candidate"
        ]
        self.assertEqual(
            [o.span.extract(source) for o in unicode_prefixes],
            ["\u00a0", " \u2003", "\t\u202f", "\u3000", "\u00a0 \t",
             "\u00a0 ", "\u00a0", "\u2003", "\u00a0", "\u00a0"],
        )
        self.assertTrue(all(
            o.syntax_id == "syntax.grouping"
            and o.limitations == EXPECTED_LIMITATIONS[o.kind]
            and o.claim_class == "recognition"
            for o in unicode_prefixes
        ))
        self.assertEqual(
            [(o.kind, o.span.extract(source)) for o in result.occurrences
             if o.kind in ("symbol_candidate", "wildcard_candidate",
                           "block_binding_candidate")],
            [("symbol_candidate", "[OnComplete]"),
             ("symbol_candidate", "[Field]"), ("wildcard_candidate", "*"),
             ("block_binding_candidate", " ↳")],
        )
        for region_index in (15, 18):
            shielded_span = result.regions[region_index].span
            self.assertFalse(any(
                shielded_span.start <= occurrence.span.start < shielded_span.end
                for occurrence in result.occurrences
            ))
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "section_header_candidate"

    def test_unsupported_shapes_and_non_zs_prefixes_remain_deferred(self):
        source = (
            "\u00a0Scope:/path\n"
            "\u00a0Two words: value\n"
            "\u00a0[Broken: value\n"
            "\u200bScope: value\n"
            "\u00a0Scope:?next\n"
            "\u00a0 \t\n"
            "  Scope:\n"
            "\tScope: yes\n"
            "\u00a0Scope:\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unclassified"] * 6
            + ["section_header_candidate", "section_boundary_candidate",
               "section_boundary_candidate"],
        )
        self.assertEqual(result.observations[7].limitations, EXPECTED_LIMITATIONS[result.observations[7].kind])
        self.assertEqual(result.observations[8].limitations, EXPECTED_LIMITATIONS[result.observations[8].kind])
        self.assertTrue(all(o.syntax_id is None and o.limitations == ()
                            for o in result.observations[:6]))
        self.assertFalse(any(o.span.start == result.regions[5].span.start
                             for o in result.occurrences))
        self.assertEqual(result.claim_class, "recognition")


if __name__ == "__main__":
    unittest.main()
