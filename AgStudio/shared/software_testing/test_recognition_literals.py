"""Qt-free recognition-only evidence for a bounded literal observation overlay.

The guide illustrates separate-line triple-double-quote and nested-example
four-double-quote delimiters; these tests verify shielding, source integrity,
uncertainty and inertness only.
They neither define complete ArcGrav literal grammar nor prove conformance.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import SourceSession
from AgStudio.shared.recognition import (
    RecognitionResult, SourceObservation, SourceSpan, recognize_source,
)


def session(source, *, configuration=None):
    return SourceSession(
        source, arcgrav_version="unverified-test-version",
        profile="literal-fixture", configuration=configuration,
    )


class RecognitionLiteralTests(unittest.TestCase):
    def test_paired_literal_retains_original_slices_and_isolates_apparent_syntax(self):
        source = (
            "Scope:\r\n"
            '  """\n'
            "[NotASection]:\r"
            "=> never an active operation\u2028"
            "- not a list; **/*.arc\n"
            "  ↳ AS [Alias] \x00\n"
            '  """\r\n'
            "Task:\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(result.claim_class, "recognition")
        self.assertEqual(
            [observation.kind for observation in result.observations],
            [
                "section_header_candidate", "literal_open", "literal_content",
                "literal_content", "literal_content", "literal_content",
                "literal_close", "section_header_candidate",
            ],
        )
        self.assertTrue(all(region.disposition == "unclassified" for region in result.regions))
        self.assertEqual(
            [(r.span, r.text) for r in result.regions],
            [(o.span, o.span.extract(source)) for o in result.observations],
        )
        for observation in result.observations[1:7]:
            self.assertEqual(observation.claim_class, "recognition")
            self.assertEqual(observation.syntax_id, "syntax.literal")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        for observation in (result.observations[0], result.observations[-1]):
            self.assertEqual(observation.syntax_id, "syntax.section")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])

    def test_unterminated_literal_shields_all_remaining_source_with_explicit_uncertainty(self):
        source = 'Scope:\n"""\r\n=> not active\n[Hidden]:\n*/*.arc'
        result = recognize_source(session(source))
        self.assertEqual(
            [observation.kind for observation in result.observations],
            [
                "section_header_candidate", "unterminated_literal_open",
                "unterminated_literal_content", "unterminated_literal_content",
                "unterminated_literal_content",
            ],
        )
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(
            all(o.syntax_id == "syntax.literal"
                for o in result.observations[1:])
        )
        self.assertTrue(
            all(o.limitations == EXPECTED_LIMITATIONS[o.kind]
                for o in result.observations[1:])
        )

    def test_separate_pairs_and_nonstandalone_markers_do_not_consume_other_regions(self):
        source = (
            'before """ inline\n'
            '"""\n'
            'one\n'
            '"""\n'
            'between\n'
            '"""\n'
            'two\n'
            '"""\n'
            'after """ inline\n'
            '"" \n'  # Two quotes are not a block delimiter.
            '\\"""\n'  # No invented escape grammar.
        )
        result = recognize_source(session(source))
        self.assertEqual(
            [o.kind for o in result.observations],
            [
                "unclassified", "literal_open", "literal_content",
                "literal_close", "unclassified", "literal_open",
                "literal_content", "literal_close", "unclassified",
                "unclassified", "unclassified",
            ],
        )
        self.assertEqual(result.round_trip(), source)

    def test_guide_nested_example_four_quote_wrapper_shields_inner_markers(self):
        source = (
            "[Outer]:\r\n"
            '  """"\n'
            "[Inner]:\n"
            '"""\n'
            '=> os.system("must stay source")\u2028'
            '"""\n'
            '  """"\r\n'
            "Task:\n"
        )
        with mock.patch("glob.glob", side_effect=AssertionError("wildcard action")):
            with mock.patch("os.system", side_effect=AssertionError("process action")):
                result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_header_candidate", "literal_open", "literal_content",
             "literal_content", "literal_content", "literal_content",
             "literal_close", "section_header_candidate"],
        )
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(region.span, observation.span)
            self.assertEqual(region.text, observation.span.extract(source))
        self.assertEqual(result.regions[3].text, '"""\n')
        for observation in result.observations[1:7]:
            self.assertEqual(observation.claim_class, "recognition")
            self.assertEqual(observation.syntax_id, "syntax.literal")
            self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])

    def test_four_quote_candidates_pair_only_with_same_standalone_delimiter(self):
        source = (
            '"" \n'  # Fewer than three quotes do not open a block.
            '""""\r\n'
            '"""\n'  # Different-length inner marker stays literal source.
            'body\n'
            '""""\n'
            'between\n'
            '"""\n'
            '""""\n'  # A four-quote line does not close a three-quote block.
            '"""\n'
            "after\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unclassified", "literal_open", "literal_content",
             "literal_content", "literal_close", "unclassified",
             "literal_open", "literal_content", "literal_close", "unclassified"],
        )
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(result, recognize_source(session(source)))

    def test_unterminated_four_quote_candidate_shields_to_eof(self):
        source = 'before\n  """"\r\n[Inner]:\n"""\n=> not active'
        result = recognize_source(session(source))
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unclassified", "unterminated_literal_open",
             "unterminated_literal_content", "unterminated_literal_content",
             "unterminated_literal_content"],
        )
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(
            o.limitations == EXPECTED_LIMITATIONS[o.kind] for o in result.observations[1:]
        ))
        self.assertEqual(
            recognize_source(session(source, configuration={"z": [1], "a": True})),
            recognize_source(session(source, configuration={"a": True, "z": [1]})),
        )

    def test_fixed_context_repeatability_and_frozen_fact_overlay(self):
        source = 'α:\r\n"""\n=> [KeepLiteral]\n"""\nβ'
        first = recognize_source(session(source, configuration={"z": [1], "a": {"x": True}}))
        second = recognize_source(session(source, configuration={"a": {"x": True}, "z": [1]}))
        self.assertEqual(first, second)
        self.assertEqual(
            [(o.kind, o.span.start, o.span.end, o.limitations)
             for o in first.observations],
            [(o.kind, o.span.start, o.span.end, o.limitations)
             for o in second.observations],
        )
        with self.assertRaises(FrozenInstanceError):
            first.observations[1].kind = "unclassified"
        self.assertEqual(first.source, source)

    def test_observations_must_be_original_source_aligned(self):
        original = session('"""\nbody\n"""\n')
        result = recognize_source(original)
        with self.assertRaises(ValueError):
            RecognitionResult(original, result.regions, result.observations[:-1])
        with self.assertRaises(ValueError):
            RecognitionResult(
                original, result.regions,
                (SourceObservation(SourceSpan(1, 2), "unclassified"),)
                + result.observations[1:],
            )
        with self.assertRaises(ValueError):
            SourceObservation(SourceSpan(0, 1), "unsupported_kind")
        with self.assertRaises(TypeError):
            SourceObservation("not a span", "unclassified")
        self.assertEqual(recognize_source(session("")).observations, ())

    def test_literal_contents_cannot_direct_external_actions(self):
        source = (
            '"""\n=> import subprocess; subprocess.run(["echo", "unsafe"])\n'
            '- https://example.invalid/*\n'
            'os.system("echo unsafe")\n"""\n'
        )
        with mock.patch("builtins.open", side_effect=AssertionError("file action")), \
             mock.patch("glob.glob", side_effect=AssertionError("wildcard expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process action")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process action")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network action")):
            result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["literal_open", "literal_content", "literal_content",
             "literal_content", "literal_close"],
        )


if __name__ == "__main__":
    unittest.main()
