"""Qt-free recognition evidence for guide-illustrated context-operation prefixes.

This suite verifies only non-normative line candidates. It supplies no
operation grammar, transformation semantics, child binding or version admission.
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
        profile="operation-fixture", configuration=configuration,
    )


class RecognitionOperationTests(unittest.TestCase):
    def test_guide_line_prefixes_retain_exact_source_and_stage_zero_gap(self):
        source = (
            "[Derived]:\r\n"
            "=> Transform [Source] into [Shape]\n"
            "  => Concatenate without line break:\r"
            "    => Nested operation candidate\u2028"
            "=> \n"
            "Ordinary prose"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_header_candidate"] + ["operation_candidate"] * 4
            + ["unclassified"],
        )
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        surface = 'syntax.operation'
        self.assertIsNotNone(surface)
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(observation.claim_class, "recognition")
            if observation.kind == "operation_candidate":
                self.assertEqual(observation.syntax_id, surface)
                self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        # Even an empty instruction body remains only a marker candidate.
        self.assertEqual(result.observations[4].kind, "operation_candidate")
        self.assertEqual(result.claim_class, "recognition")

    def test_prose_unsupported_boundaries_and_other_marker_precedence(self):
        source = (
            "Prose => inline arrow\n"
            "=>NoSpace\n"
            "=>\tTabOnly\n"
            "= > Separated arrow\n"
            "\t=> Tab-indented prefix\n"
            "==> Other arrow\n"
            "- => unordered child\n"
            "1. => ordered child\n"
            "P0. => priority child\n"
            "Task: => inline section scalar\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unclassified", "unclassified", "operation_boundary_candidate"]
            + ["unclassified"] * 3 + [
                "unordered_list_candidate", "ordered_list_candidate",
                "priority_list_candidate", "section_scalar_candidate",
            ],
        )
        self.assertTrue(all(
            o.kind != "operation_candidate" for o in result.observations
        ))
        self.assertEqual(result.observations[2].syntax_id, "syntax.operation")
        self.assertEqual(result.observations[2].limitations, EXPECTED_LIMITATIONS[result.observations[2].kind])
        self.assertTrue(all(result.observations[i].syntax_id is None
                            for i in (0, 1, 3, 4, 5)))

    def test_tab_separated_arrows_preserve_exact_boundary_and_literal_isolation(self):
        source = (
            "=>\tTransform [Source] *\r\n"
            "  =>\t\tNested\n"
            "=>\t Mixed separator\u2028"
            '"""\n'
            "=>\tHidden *\n"
            '"""\n'
            "\t=>\tTab-indented arrow\n"
            "Inline =>\tArrow\n"
        )
        first = session(source, configuration={"z": [1], "a": True})
        equivalent = session(source, configuration={"a": True, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual([o.kind for o in result.observations], [
            "operation_boundary_candidate", "operation_boundary_candidate",
            "operation_boundary_candidate", "literal_open", "literal_content",
            "literal_close", "unclassified", "unclassified",
        ])
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(observation.span, region.span)
            self.assertEqual(observation.span.extract(source), region.text)
        for observation in result.observations[:3]:
            self.assertEqual(observation.syntax_id, "syntax.operation")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertEqual([(o.kind, o.span.extract(source)) for o in result.occurrences],
                         [("symbol_candidate", "[Source]"),
                          ("wildcard_candidate", "*"),
                          ("indentation_candidate", "  "),
                          ("indentation_tab_boundary_candidate", "\t")])

    def test_paired_alternate_width_and_unmatched_literals_shield_operations(self):
        source = (
            "=> Visible\n"
            '"""\n'
            "  => Hidden\n"
            '""""\n'
            '"""\n'
            "  => Visible after close\n"
            '""""\n'
            "=> Hidden to EOF"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            [
                "operation_candidate", "literal_open", "literal_content",
                "literal_content", "literal_close", "operation_candidate",
                "unterminated_literal_open", "unterminated_literal_content",
            ],
        )
        self.assertTrue(all(
            o.syntax_id == "syntax.literal"
            for o in result.observations[1:5] + result.observations[6:]
        ))

    def test_fixed_context_immutable_gap_bound_and_no_document_actions(self):
        source = (
            "=> glob.glob('*.arc') and os.system('do not execute')\r\n"
            "  => subprocess.run(['echo', 'do not execute'])\n"
            "=> https://example.invalid/*"
        )
        first = session(source, configuration={"z": [1], "a": {"ok": True}})
        same = session(source, configuration={"a": {"ok": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("wildcard")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(same))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations], ["operation_candidate"] * 3
        )
        self.assertTrue(all(
            o.limitations == EXPECTED_LIMITATIONS[o.kind]
            for o in result.observations
        ))
        self.assertEqual(result.session.configuration, first.configuration)
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "unclassified"


if __name__ == "__main__":
    unittest.main()
