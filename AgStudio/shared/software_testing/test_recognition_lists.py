"""Qt-free Stage 01 recognition evidence for guide-backed list markers.

These are conservative, source-aligned occurrence candidates, not accepted
numeric forms, indentation binding, item validity, or ArcGrav conformance.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import SourceSession
from AgStudio.shared.recognition import recognize_source


def session(source, *, configuration=None):
    return SourceSession(
        source, arcgrav_version="unverified-test-version",
        profile="listing-fixture", configuration=configuration,
    )


class RecognitionListTests(unittest.TestCase):
    def test_illustrated_markers_keep_exact_source_and_distinct_surface_gaps(self):
        source = (
            "Files:\r\n"
            "- alpha.arc\n"
            "  - β.arc\r"
            "Task:\u2028"
            "1. Read [Files]\n"
            "  2. Identify inconsistencies\n"
            "Constraint:\n"
            "P0. Preserve source\n"
            "  P12. Unverified priority boundary\n"
            "01. Unverified numeric boundary\n"
            "- \n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_header_candidate", "unordered_list_candidate",
             "unordered_list_candidate", "section_header_candidate",
             "ordered_list_candidate", "ordered_list_candidate",
             "section_header_candidate", "priority_list_candidate",
             "priority_list_candidate", "ordered_list_candidate",
             "unordered_list_candidate"],
        )
        provenance = {'unordered_list_candidate': ('syntax.unordered', EXPECTED_LIMITATIONS['unordered_list_candidate']), 'ordered_list_candidate': ('syntax.ordered', EXPECTED_LIMITATIONS['ordered_list_candidate']), 'priority_list_candidate': ('syntax.priority', EXPECTED_LIMITATIONS['priority_list_candidate'])}
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(observation.claim_class, "recognition")
            if observation.kind in provenance:
                self.assertEqual(
                    (observation.syntax_id, observation.limitations),
                    provenance[observation.kind],
                )
        # A leading zero, multi-digit priority, or empty item is merely a
        # candidate. The Core surface admits no normative versioned grammar.
        self.assertEqual(result.session.arcgrav_version, "unverified-test-version")
        self.assertNotIn("normative", result.claim_class)

    def test_unillustrated_boundaries_and_prose_are_not_promoted(self):
        source = (
            "A - list-looking phrase\n"
            "-NoSpace\n"
            "1.NoSpace\n"
            "P0.NoSpace\n"
            "p0. Lowercase marker\n"
            "1) Alternative punctuation\n"
            "9.2 Decimal-looking prefix\n"
            "\t- Tab-indented marker\n"
            "+ Other marker\n"
            "-\n"
            "1.\n"
            "P0.\n"
            "https://example.invalid/*\n"
            "a. Not an ordered numeric marker\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(o.kind == "unclassified" for o in result.observations))
        self.assertTrue(all(o.syntax_id is None for o in result.observations))

    def test_section_precedence_and_no_inferred_child_binding(self):
        source = "Scope: - text\n- Scope:\n1. Task: value\nP0. Scope:\n"
        result = recognize_source(session(source))
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_scalar_candidate", "unordered_list_candidate",
             "ordered_list_candidate", "priority_list_candidate"],
        )
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))

    def test_paired_nested_and_unterminated_literals_shield_list_markers(self):
        source = (
            "- Visible\n"
            '"""\n'
            "1. Hidden\n"
            "P0. Hidden\n"
            '"""\n'
            "P1. Visible\n"
            '""""\n'
            "- Hidden\n"
            '"""\n'
            "2. Hidden to EOF\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unordered_list_candidate", "literal_open", "literal_content",
             "literal_content", "literal_close", "priority_list_candidate",
             "unterminated_literal_open", "unterminated_literal_content",
             "unterminated_literal_content", "unterminated_literal_content"],
        )
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(
            o.syntax_id == "syntax.literal" for o in result.observations[6:]
        ))

    def test_repeatability_frozen_facts_and_no_document_directed_actions(self):
        source = (
            "- https://example.invalid/*\r\n"
            "1. subprocess.run(['echo', 'never execute'])\n"
            "P0. os.system('never execute')\n"
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
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "unclassified"
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unordered_list_candidate", "ordered_list_candidate",
             "priority_list_candidate"],
        )


if __name__ == "__main__":
    unittest.main()
