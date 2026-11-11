"""Qt-free evidence for tab-bearing leading-prefix section-shaped ambiguity.

A leading tab is not promoted to a guide-illustrated section header/scalar.
These exact-line facts retain the Stage 00 section gap; independent prefix
occurrences retain grouping uncertainty. Neither establishes ArcGrav grammar.
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
        source, arcgrav_version=VERSION, profile="leading-tab-section-fixture",
        configuration=configuration,
    )


class LeadingTabSectionBoundaryTests(unittest.TestCase):
    def test_compact_tab_led_lines_are_exact_gap_bound_not_headers_or_scalars(self):
        source = (
            "\tScope:\r\n"
            " \tTask: Value\n"
            "  \t[OnComplete]:\tNext\u2028"
            "\tScope :Next\n"
            "\tScope:\u00a0NonAscii\n"
            "  Scope:\n"
            "\tTwo words: value\n"
            " \tScope:/path\n"
            " \t[Broken: Value\n"
            " \tScope\u200b: value\n"
            "\tPlain prose\n"
            " \tScope: [Field] * ↳\n"
            '"""\n'
            "\tHidden: Value [Symbol] * ↳\n"
            '"""\n'
            '""""\n'
            "  \tTask: Hidden to EOF"
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
            + ["section_header_candidate"]
            + ["unclassified"] * 5
            + ["section_boundary_candidate"]
            + ["literal_open", "literal_content", "literal_close",
               "unterminated_literal_open", "unterminated_literal_content"]
        )
        self.assertEqual([o.kind for o in result.observations], expected)

        cursor = 0
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span.start, cursor)
            self.assertEqual(observation.span, region.span)
            self.assertEqual(observation.span.extract(source), region.text)
            self.assertEqual(region.disposition, "unclassified")
            self.assertEqual(observation.claim_class, "recognition")
            cursor = region.span.end
        self.assertEqual(cursor, len(source))

        for index in (0, 1, 2, 3, 4, 11):
            observation = result.observations[index]
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
            self.assertNotIn(observation.kind, (
                "section_header_candidate", "section_scalar_candidate",
            ))
        self.assertTrue(all(result.observations[i].syntax_id is None
                            for i in range(6, 11)))
        self.assertTrue(all(result.observations[i].limitations == ()
                            for i in range(6, 11)))

        prefixes = [
            o for o in result.occurrences
            if o.kind == "indentation_tab_boundary_candidate"
        ]
        self.assertEqual([o.span.extract(source) for o in prefixes],
                         ["\t", " \t", "  \t", "\t", "\t",
                          "\t", " \t", " \t", " \t", "\t", " \t"])
        self.assertTrue(all(o.syntax_id == "syntax.grouping"
                            and o.limitations == EXPECTED_LIMITATIONS[o.kind]
                            for o in prefixes))
        self.assertIn(("symbol_candidate", "[Field]"), [
            (o.kind, o.span.extract(source)) for o in result.occurrences
        ])
        self.assertIn(("wildcard_candidate", "*"), [
            (o.kind, o.span.extract(source)) for o in result.occurrences
        ])
        self.assertIn(("block_binding_candidate", " ↳"), [
            (o.kind, o.span.extract(source)) for o in result.occurrences
        ])
        hidden = source.index("\tHidden: Value")
        self.assertTrue(all(
            not (hidden <= o.span.start < hidden + len("\tHidden: Value [Symbol] * ↳"))
            for o in result.occurrences
        ))
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "section_scalar_candidate"

    def test_unsupported_labels_non_zs_prefixes_and_suffixes_remain_deferred(self):
        source = (
            "\tScope:/path\n"
            " \tTwo words: value\n"
            "\t[Broken: value\n"
            "\tScope\u200b: value\n"
            "\tScope:?next\n"
            "\u00a0\tScope: value\n"
            "\tPlain prose\n"
            "\tScope: yes\n"
            "\tScope:\n"
            "Scope: yes\n"
            "Scope:\tboundary\n"
            "\t- Scope: text"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual([o.kind for o in result.observations],
                         ["unclassified"] * 5
                         + ["section_boundary_candidate", "unclassified"]
                         + ["section_boundary_candidate"] * 2
                         + ["section_scalar_candidate",
                            "section_boundary_candidate", "unclassified"])
        self.assertEqual(
            [result.observations[i].limitations for i in (5, 7, 8)],
            [("section_boundary",)] * 3,
        )
        self.assertEqual(result.claim_class, "recognition")


if __name__ == "__main__":
    unittest.main()
