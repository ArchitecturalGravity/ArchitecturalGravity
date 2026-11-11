"""Independent Qt-free recognition evidence for exact bracketed symbol tokens.

Guide-shaped [Name] tokens are non-normative recognition-only candidates;
definition versus invocation, name grammar, aliasing and resolution stay gap-bound.
"""

from dataclasses import FrozenInstanceError
import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import SourceSession
from AgStudio.shared.recognition import (
    RecognitionResult, SourceOccurrence, SourceSpan, recognize_source,
)


def session(source, *, configuration=None):
    return SourceSession(
        source, arcgrav_version="unverified-test-version",
        profile="symbol-fixture", configuration=configuration,
    )


def symbols(result):
    return tuple(o for o in result.occurrences if o.kind == "symbol_candidate")


class RecognitionSymbolTests(unittest.TestCase):
    def test_guide_tokens_keep_exact_spans_and_coexist_with_line_and_markers(self):
        source = (
            "[Source]: src/main.py\r\n"
            "Task:\n"
            "- Evaluate [Source] against [Reference]\r"
            "  [Target]: [Source] + [Property]\u2028"
            "=> Analyze [Target] ↳\n"
            "Prose [Optional] stays unclassified *\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.source, source)
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [o.kind for o in result.observations],
            ["section_scalar_candidate", "section_header_candidate",
             "unordered_list_candidate", "section_scalar_candidate",
             "operation_candidate", "unclassified"],
        )
        expected = [
            "[Source]", "[Source]", "[Reference]", "[Target]", "[Source]",
            "[Property]", "[Target]", "[Optional]",
        ]
        cursor = 0
        positions = []
        for token in expected:
            start = source.index(token, cursor)
            positions.append(SourceSpan(start, start + len(token)))
            cursor = start + len(token)
        self.assertEqual([o.span for o in symbols(result)], positions)
        self.assertEqual(
            [o.span.extract(source) for o in symbols(result)], expected
        )
        self.assertEqual(
            [o.span.start for o in result.occurrences],
            sorted(o.span.start for o in result.occurrences),
        )
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "block_binding_candidate"], [" ↳"],
        )
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "wildcard_candidate"], ["*"],
        )
        self.assertEqual(
            [o.span.extract(source) for o in result.occurrences
             if o.kind == "indentation_candidate"], ["  "],
        )
        surface = 'syntax.symbol'
        for occurrence in symbols(result):
            self.assertEqual(occurrence.claim_class, "recognition")
            self.assertEqual(occurrence.syntax_id, surface)
            self.assertEqual(occurrence.limitations, EXPECTED_LIMITATIONS[occurrence.kind])
        self.assertTrue(all(r.disposition == "unclassified" for r in result.regions))
        self.assertEqual(result.claim_class, "recognition")

    def test_ambiguous_boundaries_and_names_remain_unclassified_source(self):
        source = (
            "[] [Has Space] [A-B] [[Nested]] [unfinished [1] [*]\n"
            "Unclosed [Name\n"
            "Two [Good] [Other_2] tokens\n"
        )
        result = recognize_source(session(source))
        self.assertEqual(
            [o.span.extract(source) for o in symbols(result)],
            ["[Good]"],
        )
        self.assertEqual(result.round_trip(), source)
        self.assertTrue(all(o.kind == "unclassified" for o in result.observations))
        self.assertNotIn("normative", result.claim_class)

    def test_escaped_and_backtick_wrapped_tokens_do_not_become_symbols(self):
        source = (
            "Escaped \\[Name] and `wrapped [Other]`\r\n"
            "Immediate `[Third]` and [Visible]\n"
            '"""\n'
            "[Hidden]\n"
            '"""\n'
        )
        first = session(source, configuration={"z": [1], "a": True})
        same = session(source, configuration={"a": True, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(result, recognize_source(same))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual([o.span.extract(source) for o in symbols(result)],
                         ["[Visible]"])
        self.assertEqual([o.kind for o in result.observations],
                         ["unclassified", "unclassified", "literal_open",
                          "literal_content", "literal_close"])
        visible = symbols(result)[0]
        self.assertEqual(visible.span.extract(source), "[Visible]")
        self.assertEqual(visible.limitations, EXPECTED_LIMITATIONS[visible.kind])

    def test_paired_and_unterminated_literals_shield_all_symbol_candidates(self):
        source = (
            "[Outside]\n"
            '"""\n'
            "[Hidden]\n"
            '""""\n'
            '"""\n'
            "[Visible]\n"
            '""""\n'
            "[HiddenToEOF]"
        )
        result = recognize_source(session(source))
        self.assertEqual(
            [o.span.extract(source) for o in symbols(result)],
            ["[Outside]", "[Visible]"],
        )
        self.assertEqual(
            [o.kind for o in result.observations],
            ["unclassified", "literal_open", "literal_content",
             "literal_content", "literal_close", "unclassified",
             "unterminated_literal_open", "unterminated_literal_content"],
        )
        self.assertEqual(result.round_trip(), source)

    def test_validate_original_exact_tokens_and_literal_non_leakage(self):
        source = '[Valid] [Other]\n"""\n[Hidden]\n"""\n'
        result = recognize_source(session(source))
        valid, other = symbols(result)
        self.assertEqual(valid.span.extract(source), "[Valid]")
        invalid = (
            SourceOccurrence(
                SourceSpan(valid.span.start, valid.span.end - 1), "symbol_candidate"
            ),
            SourceOccurrence(
                SourceSpan(valid.span.start + 1, valid.span.end), "symbol_candidate"
            ),
            SourceOccurrence(
                SourceSpan(source.index("[Hidden]"), source.index("[Hidden]") + 8),
                "symbol_candidate",
            ),
        )
        for occurrence in invalid:
            with self.subTest(span=occurrence.span), self.assertRaises(ValueError):
                RecognitionResult(
                    result.session, result.regions, result.observations, (occurrence,)
                )
        for occurrences in ((valid, valid), (other, valid)):
            with self.assertRaises(ValueError):
                RecognitionResult(
                    result.session, result.regions, result.observations, occurrences
                )
        with self.assertRaises(TypeError):
            SourceOccurrence("not a span", "symbol_candidate")
        with self.assertRaises(ValueError):
            SourceOccurrence(valid.span, "unsupported")
        with self.assertRaises(FrozenInstanceError):
            valid.kind = "unclassified"

    def test_fixed_context_is_deterministic_and_document_actions_are_inert(self):
        source = (
            "[Source]: os.system('do not run')\r\n"
            "Task: [Source] AS [Alias]\n"
            "=> glob.glob('*.arc') [Alias] ↳\n"
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
        self.assertEqual(
            [o.span.extract(source) for o in symbols(result)],
            ["[Source]", "[Source]", "[Alias]", "[Alias]"],
        )
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(result.session.configuration, first.configuration)
        self.assertEqual(recognize_source(session("")).occurrences, ())


if __name__ == "__main__":
    unittest.main()
