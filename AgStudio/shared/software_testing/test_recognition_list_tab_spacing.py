"""Independent Qt-free evidence for tab-first list-marker boundaries.

The illustrated ASCII-space forms remain ordinary recognition candidates.
A tab-first separator is a separate unresolved marker boundary, not
an ArcGrav list grammar, conformance finding or child relationship.
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
        source, arcgrav_version=VERSION,
        profile="list-tab-boundary-fixture", configuration=configuration,
    )


class ImmediateTabListBoundaryTests(unittest.TestCase):
    def test_three_marker_families_keep_exact_tab_boundary_and_surface_gaps(self):
        source = (
            "-\talpha.arc\r\n"
            "  01.\tβ.arc\n"
            "P12.\tPreserve source\r"
            "  P0.\t\r\n"
            "1.\tValue with internal spaces\u2028"
            "- Item\n"
            "1. Step\n"
            "P0. Constraint\n"
            "Ordinary prose"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        expected = [
            ('unordered_list_tab_boundary_candidate', 'syntax.unordered', EXPECTED_LIMITATIONS['unordered_list_tab_boundary_candidate']),
            ('ordered_list_tab_boundary_candidate', 'syntax.ordered', EXPECTED_LIMITATIONS['ordered_list_tab_boundary_candidate']),
            ('priority_list_tab_boundary_candidate', 'syntax.priority', EXPECTED_LIMITATIONS['priority_list_tab_boundary_candidate']),
            ('priority_list_tab_boundary_candidate', 'syntax.priority', EXPECTED_LIMITATIONS['priority_list_tab_boundary_candidate']),
            ('ordered_list_tab_boundary_candidate', 'syntax.ordered', EXPECTED_LIMITATIONS['ordered_list_tab_boundary_candidate']),
            ('unordered_list_candidate', 'syntax.unordered', EXPECTED_LIMITATIONS['unordered_list_candidate']),
            ('ordered_list_candidate', 'syntax.ordered', EXPECTED_LIMITATIONS['ordered_list_candidate']),
            ('priority_list_candidate', 'syntax.priority', EXPECTED_LIMITATIONS['priority_list_candidate']),
            ("unclassified", None, ()),
        ]
        self.assertEqual(
            [(o.kind, o.syntax_id, o.limitations) for o in result.observations],
            expected,
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
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "unordered_list_candidate"

    def test_repeated_and_mixed_tab_first_separators_remain_gap_bound(self):
        source = (
            "-\t\tDouble tab\r\n"
            "1.\t Next\n"
            "P0.\t\tMore tabs\u2028"
            "-\t \tMixed run\n"
            "12.\t\t\t\tValue\n"
            "P4.\t \t\t\n"
            "- \tSpace first\n"
            "3.  \tSpace first\n"
            "P2. \tSpace first\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual([o.kind for o in result.observations], [
            "unordered_list_tab_boundary_candidate",
            "ordered_list_tab_boundary_candidate",
            "priority_list_tab_boundary_candidate",
            "unordered_list_tab_boundary_candidate",
            "ordered_list_tab_boundary_candidate",
            "priority_list_tab_boundary_candidate",
            "unordered_list_candidate", "ordered_list_candidate",
            "priority_list_candidate",
        ])
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(observation.span, region.span)
            self.assertEqual(observation.span.extract(source), region.text)
            self.assertEqual(observation.claim_class, "recognition")
        for observation in result.observations[:6]:
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
            self.assertIsNotNone(observation.syntax_id)

    def test_unsupported_marker_shapes_remain_deferred(self):
        deferred = (
            "\t-\tTab indentation\n"
            "\t1.\tTab indentation\n"
            "p0.\tLowercase priority\n"
            "1)\tOther punctuation\n"
            "-NoSeparator\n"
            "1.NoSeparator\n"
            "P0.NoSeparator\n"
            "Prose -\tInline marker\n"
        )
        unchanged = "- Item\n1. Step\nP0. Level\n- \tExisting space-first candidate\n"
        result = recognize_source(session(deferred + unchanged))
        self.assertEqual(result.round_trip(), deferred + unchanged)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unclassified"] * 8
            + ["unordered_list_candidate", "ordered_list_candidate",
               "priority_list_candidate", "unordered_list_candidate"],
        )
        self.assertTrue(all(o.syntax_id is None and not o.limitations
                            for o in result.observations[:8]))

    def test_literals_fixed_context_and_inert_document_content(self):
        source = (
            "-\tglob.glob('*.arc') and os.system('never run')\r\n"
            '"""\n'
            "1.\tHidden * [Symbol]\n"
            '"""\n'
            "P0.\tVisible\n"
            '""""\n'
            "-\tHidden to EOF * ↳\n"
        )
        first = session(source, {"z": [1], "a": {"safe": True}})
        same = session(source, {"a": {"safe": True}, "z": [1]})
        with (
            mock.patch("builtins.open", side_effect=AssertionError("filesystem")),
            mock.patch("glob.glob", side_effect=AssertionError("expansion")),
            mock.patch("os.system", side_effect=AssertionError("process")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(same))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unordered_list_tab_boundary_candidate", "literal_open",
             "literal_content", "literal_close",
             "priority_list_tab_boundary_candidate",
             "unterminated_literal_open", "unterminated_literal_content"],
        )
        self.assertEqual(
            [(o.kind, o.span.extract(source)) for o in result.occurrences],
            [("wildcard_candidate", "*")],
        )
        self.assertTrue(all(o.claim_class == "recognition"
                            for o in result.observations + result.occurrences))
        self.assertEqual(result.session.configuration, first.configuration)


if __name__ == "__main__":
    unittest.main()
