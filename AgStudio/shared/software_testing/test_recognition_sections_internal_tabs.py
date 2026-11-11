"""Qt-free section-boundary evidence for compact two-part labels.

The illustrated narrow cases and selected longer horizontal separators
remain source-exact, section-gap-bound candidates. ASCII-space prose,
extra label parts, unsupported suffixes and literal bodies are not
promoted to headers, scalars or ArcGrav conformance.
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
        profile="section-internal-tab-fixture", configuration=configuration,
    )


class InternalTabSectionBoundaryTests(unittest.TestCase):
    def test_only_single_internal_tab_between_two_compact_parts_is_observed(self):
        source = (
            "Task\tName:\r\n"
            "  Task\tName: value\n"
            "Task\tName:Next\u2028"
            "Task\tName::\n"
            "\tTask\tName: value\n"
            "Task\tName:/path\n"
            "Task Name: value\n"
            "Task\tName\tExtra: value\n"
            "Task\tName!: value\n"
            "Task\tName\u00a0: value\n"
            "Ordinary prose.\n"
            "Task\t Name: value\n"           # separate mixed ASCII boundary
            "Task \tName: value\n"
            "- Task\tName:\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_boundary_candidate"] * 5
            + ["unclassified"] * 6
            + ["section_boundary_candidate"] * 2 + ["unordered_list_candidate"],
        )
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
            self.assertEqual(observation.claim_class, "recognition")
        for observation in result.observations[:5]:
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
            self.assertNotIn(observation.kind,
                             ("section_header_candidate", "section_scalar_candidate"))
        for observation in result.observations[5:11]:
            self.assertIsNone(observation.syntax_id)
            self.assertEqual(observation.limitations, ())
        for observation in result.observations[11:13]:
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        self.assertEqual(
            [(o.kind, o.span.extract(source)) for o in result.occurrences
             if o.kind.startswith("indentation_")],
            [("indentation_candidate", "  "),
             ("indentation_tab_boundary_candidate", "\t")],
        )
        self.assertEqual(result.claim_class, "recognition")
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "section_header_candidate"

    def test_literal_shielding_reproducibility_and_inert_document_text(self):
        source = (
            "Task\tName: glob.glob('*.arc') ↳\r\n"
            '"""\n'
            "Task\tName: Hidden * ↳\n"
            '"""\n'
            '""""\n'
            "Task\tName: Hidden to EOF * ↳\n"
        )
        first = session(source, {"z": [1], "a": {"safe": True}})
        equivalent = session(source, {"a": {"safe": True}, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_boundary_candidate", "literal_open", "literal_content",
             "literal_close", "unterminated_literal_open",
             "unterminated_literal_content"],
        )
        self.assertEqual(
            [(o.kind, o.span.extract(source)) for o in result.occurrences],
            [("wildcard_candidate", "*"), ("block_binding_candidate", " ↳")],
        )
        self.assertEqual(result.observations[0].limitations, EXPECTED_LIMITATIONS[result.observations[0].kind])
        self.assertTrue(all(o.claim_class == "recognition"
                            for o in result.observations + result.occurrences))
        self.assertEqual(result.session.configuration, first.configuration)


    def test_bracketed_single_tab_label_keeps_gaps_and_negative_isolation(self):
        positive = (
            "[Task\tName]:\r\n",
            "  [Task\tName]: value\n",
            "[Task\tName]:Next\u2028",
            "[Task\tName]::\n",
            "\t[Task\tName]: \tNext\n",
            "[Task\tName]: glob.glob('*.arc') ↳\n",
            "[Task\t\t\t\t\tName]: value\n",
        )
        deferred = (
            "[Task Name]: value\n",             # ordinary ASCII-space prose
            "[Task\tName\tExtra]: value\n",   # three parts
            "[[Task\tName]]: value\n",         # nested brackets
            "[Task\tName] \t: value\n",        # separate pre-colon ambiguity
            "[Task\tName]:/path\n",            # unsupported suffix
            "[Task\tName]:\u200bNext\n",       # non-Zs post-colon separator
            "[Task\tName!]: value\n",          # unsupported label punctuation
        )
        comparisons = (
            "[Task \tName]: value\n",          # separate mixed ASCII boundary
            "Task\tName: value\n",             # existing bare-tab boundary
            "Task: value\n",                   # compact scalar
            "[Task]: value\n",                 # compact bracketed scalar
            "- [Task\tName]: value\n",        # list prefix is still distinct
        )
        shielded = (
            '"""\n',
            "[Task\tName]: Hidden [Symbol] * ↳\n",
            '"""\n',
            '""""\n',
            "[Task\tName]: Hidden to EOF * ↳\n",
        )
        source = "".join(positive + deferred + comparisons + shielded)
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
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_boundary_candidate"] * len(positive)
            + ["unclassified"] * len(deferred)
            + ["section_boundary_candidate", "section_boundary_candidate",
               "section_scalar_candidate", "section_scalar_candidate",
               "unordered_list_candidate"]
            + ["literal_open", "literal_content", "literal_close",
               "unterminated_literal_open", "unterminated_literal_content"],
        )
        cursor = 0
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span.start, cursor)
            self.assertEqual(region.span, observation.span)
            self.assertEqual(observation.span.extract(source), region.text)
            self.assertEqual(region.disposition, "unclassified")
            self.assertEqual(observation.claim_class, "recognition")
            cursor = region.span.end
        self.assertEqual(cursor, len(source))
        for observation in result.observations[:len(positive)]:
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
            self.assertNotIn(observation.kind,
                             ("section_header_candidate", "section_scalar_candidate"))
        for observation in result.observations[
                len(positive):len(positive) + len(deferred)]:
            self.assertIsNone(observation.syntax_id)
            self.assertEqual(observation.limitations, ())
        self.assertEqual(
            [(o.kind, o.span.extract(source)) for o in result.occurrences],
            [("indentation_candidate", "  "),
             ("indentation_tab_boundary_candidate", "\t"),
             ("wildcard_candidate", "*"),
             ("block_binding_candidate", " ↳"),
             ("symbol_candidate", "[Task]")],
        )
        self.assertEqual(result.session.configuration, first.configuration)
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].kind = "section_header_candidate"

if __name__ == "__main__":
    unittest.main()
