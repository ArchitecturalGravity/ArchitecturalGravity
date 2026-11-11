"""Qt-free recognition evidence for tab-bearing post-colon section ambiguity.

These are source-shape observations tied to the Stage 00 section gap, not
accepted ArcGrav syntax, binding decisions, or normative conformance.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import SourceSession
from AgStudio.shared.recognition import recognize_source


VERSION = "unverified-test-version"


def session(source, configuration=None):
    return SourceSession(
        source, arcgrav_version=VERSION, profile="tab-section-recognition-fixture",
        configuration=configuration,
    )


class TabBearingSectionBoundaryTests(unittest.TestCase):
    def test_immediate_postcolon_tab_is_exact_gap_bound_boundary(self):
        source = (
            "Scope:\tValue\r\n"
            "[OnComplete]: \tNext\n"
            "Task:\t  Nested\u2028"
            "Scope: \t\n"
            "Scope:\t\n"
            "Scope: normal\n"
            "Scope:  still ascii\n"
            "Scope:  \n"
            "Scope:\n"
            "Scope:\u00a0NonAscii\n"
            "Two words:\tvalue\n"
            "\tScope:\tvalue\n"
            "Scope: plain\tbody\n"
            '"""\n'
            "Task:\tHidden [Symbol] * ↳\n"
            '"""\n'
            '""""\n'
            "Task:\tHidden to EOF"
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

        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        expected = (
            ["section_boundary_candidate"] * 5
            + ["section_scalar_candidate"] * 2
            + ["section_header_candidate"] * 2
            + ["section_boundary_candidate"]
            + ["unclassified", "section_boundary_candidate"]
            + ["section_scalar_candidate"]
            + ["literal_open", "literal_content", "literal_close",
               "unterminated_literal_open", "unterminated_literal_content"]
        )
        self.assertEqual([o.kind for o in result.observations], expected)
        cursor = 0
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span.start, cursor)
            self.assertEqual(observation.span, region.span)
            self.assertEqual(observation.span.extract(source), region.text)
            self.assertEqual(observation.claim_class, "recognition")
            self.assertEqual(region.disposition, "unclassified")
            cursor = region.span.end
        self.assertEqual(cursor, len(source))
        for observation in result.observations[:5] + result.observations[9:10]:
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertTrue(all(o.kind not in (
            "section_header_candidate", "section_scalar_candidate"
        ) for o in result.observations[:5]))
        self.assertEqual(result.observations[10].limitations, ())
        self.assertEqual(result.observations[11].syntax_id, "syntax.section")
        self.assertEqual(result.observations[11].limitations, EXPECTED_LIMITATIONS[result.observations[11].kind])
        hidden = source.index("Task:\tHidden [Symbol]")
        self.assertTrue(all(
            not (hidden <= o.span.start < hidden + len("Task:\tHidden [Symbol] * ↳"))
            for o in result.occurrences
        ))
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "section_scalar_candidate"

    def test_boundary_is_only_immediate_separator_not_tab_in_value(self):
        source = (
            "Scope: value\tstill value\n"
            "Scope:  value\tstill value\n"
            "[Key]:\tvalue\n"
            "Scope:\t/path\n"
            "Scope: \t\t\n"
            "Scope:\u00a0value\n"
            "Scope:\u200bvalue\n"
            "[Broken:\tvalue\n"
            "Two words:\tvalue\n"
            "https://example.invalid/path:\tvalue"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_scalar_candidate"] * 2
            + ["section_boundary_candidate"] * 4
            + ["unclassified"] * 4,
        )
        self.assertEqual(result.observations[3].span.extract(source),
                         "Scope:\t/path\n")
        self.assertTrue(all(o.limitations == EXPECTED_LIMITATIONS[o.kind]
                            for o in result.observations[2:6]))
        self.assertTrue(all(o.limitations == ()
                            for o in result.observations[6:]))
        self.assertEqual(result.claim_class, "recognition")


if __name__ == "__main__":
    unittest.main()
