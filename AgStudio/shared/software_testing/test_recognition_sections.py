"""Independent, Qt-free Stage 01 evidence for conservative section observations.

Guide-illustrated source shapes are candidates, not an ArcGrav header grammar,
semantic section binding, version admission or normative conformance cases.
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
        profile="section-fixture", configuration=configuration,
    )


class RecognitionSectionTests(unittest.TestCase):
    def test_illustrated_header_and_scalar_shapes_keep_exact_source_and_gaps(self):
        source = (
            "Scope:\r\n"
            "- Value one\n"
            "  Context:  \n"
            "[OnComplete]:\r"
            "Task: Inspect [Scope]\u2028"
            "Scope: C:\\Project"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            [
                "section_header_candidate", "unordered_list_candidate",
                "section_header_candidate", "section_header_candidate",
                "section_scalar_candidate", "section_scalar_candidate",
            ],
        )
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(observation.claim_class, "recognition")
            if observation.kind.startswith("section_"):
                self.assertEqual(observation.syntax_id, "syntax.section")
                self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
            elif observation.kind == "unordered_list_candidate":
                self.assertEqual(observation.syntax_id, "syntax.unordered")
                self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
            else:
                self.assertIsNone(observation.syntax_id)
                self.assertEqual(observation.limitations, ())

    def test_prose_and_unillustrated_boundaries_are_deferred_not_validated(self):
        source = (
            "An ordinary line.\n"
            "Two words: not a compact Key shape\n"
            "- Scope:\n"
            "1. Scope:\n"
            "P0. Scope:\n"
            "Scope:NoInventedScalarBoundary\n"
            "Scope::\n"
            "https://example.invalid/path\n"
            "\tScope:\n"
            "[Open:\n"
            "Other, punctuation: value\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unclassified", "unclassified", "unordered_list_candidate",
             "ordered_list_candidate", "priority_list_candidate"]
            + ["section_boundary_candidate"] * 2
            + ["unclassified", "section_boundary_candidate"]
            + ["unclassified"] * 2,
        )
        self.assertTrue(all(
            o.kind != "section_header_candidate"
            and o.kind != "section_scalar_candidate"
            for o in result.observations
        ))
        self.assertTrue(all(
            o.syntax_id == "syntax.section"
            and o.limitations == EXPECTED_LIMITATIONS[o.kind]
            for o in result.observations[5:7] + result.observations[8:9]
        ))
        self.assertTrue(all(
            o.syntax_id is None and o.limitations == ()
            for o in (result.observations[:2] + result.observations[7:8]
                      + result.observations[9:])
        ))
        self.assertNotIn("normative", result.claim_class)

    def test_colon_adjacent_boundaries_are_gap_bound_not_header_or_scalar(self):
        source = (
            "Scope:Value\r\n"
            "[OnComplete]:Next\n"
            "Task:42\u2028"
            "Scope::\n"
            "Scope: normal\n"
            "Scope:\n"
            "https://example.invalid/a:b\n"
            "C:\\Project\n"
            "Two words:Next\n"
            "Scope:/path\n"
            '"""\n'
            "Task:Hidden\n"
            '"""\n'
            "Task:Visible"
        )
        first = recognize_source(session(source, configuration={"x": [1]}))
        repeated = recognize_source(session(source, configuration={"x": [1]}))
        self.assertEqual(first, repeated)
        self.assertEqual(first.round_trip(), source)
        self.assertEqual(
            [o.kind for o in first.observations],
            ["section_boundary_candidate"] * 4
            + ["section_scalar_candidate", "section_header_candidate"]
            + ["unclassified"] * 4
            + ["literal_open", "literal_content", "literal_close",
               "section_boundary_candidate"],
        )
        self.assertTrue(all(r.disposition == "unclassified" for r in first.regions))
        for region, observation in zip(first.regions, first.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(observation.claim_class, "recognition")
            if observation.kind == "section_boundary_candidate":
                self.assertEqual(observation.syntax_id, "syntax.section")
                self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertTrue(all(o.kind not in ("section_header_candidate",
                                           "section_scalar_candidate")
                            for o in first.observations[:4]))
        self.assertEqual(first.claim_class, "recognition")

    def test_precolon_horizontal_whitespace_remains_a_gap_bound_boundary(self):
        source = (
            "Scope :\r\n"
            "  [OnComplete]\t: value\n"
            "Task :Next\u2028"
            "Scope \t:  C:\\Project\n"
            "Scope: C:\\Project\n"
            "Scope:\n"
            "Two words : value\n"
            "\tScope : value\n"
            "Scope :/path\n"
            "C :\\Project\n"
            '"""\n'
            "Hidden : value\n"
            '"""\n'
            "After : yes"
        )
        first = recognize_source(session(source, configuration={"flags": [True]}))
        repeated = recognize_source(session(source, configuration={"flags": [True]}))
        self.assertEqual(first, repeated)
        self.assertEqual(first.source, first.round_trip())
        self.assertEqual(
            [o.kind for o in first.observations],
            ["section_boundary_candidate"] * 4
            + ["section_scalar_candidate", "section_header_candidate"]
            + ["unclassified", "section_boundary_candidate"]
            + ["unclassified"] * 2
            + ["literal_open", "literal_content", "literal_close",
               "section_boundary_candidate"],
        )
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in first.regions))
        for region, observation in zip(first.regions, first.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(observation.claim_class, "recognition")
            if observation.kind == "section_boundary_candidate":
                self.assertEqual(observation.syntax_id, "syntax.section")
                self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertEqual([o.kind for o in first.observations[6:10]],
                         ["unclassified", "section_boundary_candidate",
                          "unclassified", "unclassified"])
        self.assertEqual(first.observations[7].limitations, EXPECTED_LIMITATIONS[first.observations[7].kind])
        self.assertEqual(first.observations[11].kind, "literal_content")
        self.assertEqual(first.claim_class, "recognition")

    def test_unicode_postcolon_space_separators_remain_gap_bound_boundaries(self):
        source = (
            "Scope:\u00a0Value\r\n"
            "[OnComplete]:\u2003Next\n"
            "Task:\u202f\u00a0nested\u2028"
            "Scope:\u3000/path\n"
            "Scope:\u00a0\n"
            "Scope: normal\n"
            "Scope:\n"
            "Scope:\u200bNotASpace\n"
            "Two words:\u00a0value\n"
            "\tScope:\u00a0value\n"
            '"""\n'
            "Task:\u00a0Hidden\n"
            '"""\n'
            '""""\n'
            "Scope:\u2003Hidden until EOF"
        )
        original = session(source, configuration={"z": [1], "a": {"safe": True}})
        equivalent = session(source, configuration={"a": {"safe": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(original)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [observation.kind for observation in result.observations],
            ["section_boundary_candidate"] * 5
            + ["section_scalar_candidate", "section_header_candidate"]
            + ["unclassified"] * 2 + ["section_boundary_candidate"]
            + ["literal_open", "literal_content", "literal_close",
               "unterminated_literal_open", "unterminated_literal_content"],
        )
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in result.regions))
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(observation.claim_class, "recognition")
        for observation in result.observations[:5]:
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertTrue(all(observation.syntax_id is None
                            and observation.limitations == ()
                            for observation in result.observations[7:9]))
        self.assertEqual(result.observations[9].limitations, EXPECTED_LIMITATIONS[result.observations[9].kind])
        self.assertEqual(result.observations[11].kind, "literal_content")
        self.assertEqual(result.observations[-1].kind,
                         "unterminated_literal_content")
        self.assertEqual(result.claim_class, "recognition")


    def test_unicode_precolon_space_separators_are_gap_bound_not_section_grammar(self):
        source = (
            "Scope\u00a0:\r\n"
            "  [OnComplete]\u2003: value\n"
            "Task \u202f:\u3000Next\u2028"
            "Scope \u00a0:\tC:\\Project\n"
            "Scope\u00a0::\n"
            "Scope: normal\n"
            "Scope:\n"
            "Scope\u200b: no\n"
            "Two words\u00a0: value\n"
            "\u00a0Scope: value\n"
            "\tScope\u00a0: value\n"
            "Scope\u00a0:/path\n"
            "Scope\u00a0:\u200bNotASpace\n"
            '"""\n'
            "Task\u00a0: Hidden\n"
            '"""\n'
            '""""\n'
            "Scope\u2003: Hidden to EOF"
        )
        first = session(source, configuration={"z": [1], "a": {"safe": True}})
        equivalent = session(source, configuration={"a": {"safe": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [observation.kind for observation in result.observations],
            ["section_boundary_candidate"] * 5
            + ["section_scalar_candidate", "section_header_candidate"]
            + ["unclassified"] * 2 + ["section_boundary_candidate"] * 2
            + ["unclassified"] * 2
            + ["literal_open", "literal_content", "literal_close",
               "unterminated_literal_open", "unterminated_literal_content"],
        )
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in result.regions))
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(observation.claim_class, "recognition")
        for observation in result.observations[:5]:
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertTrue(all(observation.syntax_id is None
                            and observation.limitations == ()
                            for observation in result.observations[7:9] + result.observations[11:13]))
        self.assertEqual(
            [result.observations[i].limitations for i in (9, 10)],
            [("section_boundary",)] * 2,
        )
        self.assertEqual(result.observations[14].kind, "literal_content")
        self.assertEqual(result.observations[-1].kind, "unterminated_literal_content")
        self.assertEqual(result.claim_class, "recognition")

    def test_literal_contents_and_unterminated_openers_prevent_section_leakage(self):
        source = (
            "Scope:\n"
            '"""\n'
            "Task:\n"
            "Scope: Hidden\n"
            '"""\n'
            "Task: Visible\n"
            '""""\n'
            "[OnComplete]:\n"
            '"""\n'
            "Scope: Hidden to EOF\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(
            [o.kind for o in result.observations],
            [
                "section_header_candidate", "literal_open", "literal_content",
                "literal_content", "literal_close", "section_scalar_candidate",
                "unterminated_literal_open", "unterminated_literal_content",
                "unterminated_literal_content", "unterminated_literal_content",
            ],
        )
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.syntax_id for o in result.observations[6:]],
            ["syntax.literal"] * 4,
        )

    def test_fixed_context_repeatable_immutable_and_inert(self):
        source = (
            "Scope : https://example.invalid/*\r\n"
            "[OnComplete]:\n"
            "Task: os.system('must remain plain text')\n"
        )
        first = session(source, configuration={"z": [1], "a": {"ok": True}})
        second = session(source, configuration={"a": {"ok": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("wildcard")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(second))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_boundary_candidate", "section_header_candidate",
             "section_scalar_candidate"],
        )
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "literal_content"
        self.assertEqual(result.session.configuration, first.configuration)


if __name__ == "__main__":
    unittest.main()
