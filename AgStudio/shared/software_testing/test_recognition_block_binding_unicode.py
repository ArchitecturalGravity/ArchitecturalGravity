"""Qt-free evidence for a Unicode Zs boundary before a trailing binder."""

import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import LanguageCore, SourceSession
from AgStudio.shared.recognition import RecognitionResult, SourceOccurrence, SourceSpan, recognize_source


def session(source):
    return SourceSession(
        source, arcgrav_version="unverified-test-version",
        profile="unicode-block-binding-fixture",
    )


class UnicodeBlockBindingBoundaryTests(unittest.TestCase):
    def test_exact_suffix_overlap_and_deferred_shapes(self):
        source = (
            "Operation [Context]\u00a0↳\r\n"
            "Result AS [Alias]\u2003↳\n"
            "Operation\u202f↳  \n"
            "Operation\u200b↳\n"       # non-Zs glyph
            "\u00a0\u00a0↳\n"            # no preceding expression
            "Operation\u00a0↳ inline\n" # not terminal
            "Operation↳\n"              # no separator
        )
        result = recognize_source(session(source))
        binders = [fact for fact in result.occurrences
                   if fact.kind.startswith("block_binding_")]
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [(fact.kind, fact.span.extract(source)) for fact in binders],
            [("block_binding_unicode_boundary_candidate", "\u00a0↳"),
             ("block_binding_unicode_boundary_candidate", "\u2003↳"),
             ("block_binding_unicode_boundary_candidate", "\u202f↳")],
        )
        for fact in binders:
            self.assertEqual(fact.syntax_id, "syntax.block_binding")
            self.assertEqual(fact.limitations, EXPECTED_LIMITATIONS[fact.kind])
            self.assertEqual(fact.claim_class, "recognition")
        self.assertEqual(
            [fact.span.extract(source) for fact in result.occurrences
             if fact.kind == "alias_marker_candidate"], ["AS "],
        )

        forged_start = source.index("\u200b↳")
        forged = SourceOccurrence(SourceSpan(forged_start, forged_start + 2),
                                  "block_binding_unicode_boundary_candidate")
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions, result.observations,
                              tuple(sorted((*result.occurrences, forged),
                                           key=lambda fact: fact.span.start)),
                              result.recoveries)

    def test_literals_fixed_context_and_inert_document_text(self):
        source = (
            "Operation glob.glob('*.arc')\u00a0↳\n"
            '"""\n'
            "Hidden\u2003↳ * [Symbol]\n"
            '"""\n'
            "Visible\u202f↳\n"
        )
        original = session(source)
        with (
            mock.patch("builtins.open", side_effect=AssertionError("filesystem")),
            mock.patch("glob.glob", side_effect=AssertionError("expansion")),
            mock.patch("os.system", side_effect=AssertionError("process")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            result = recognize_source(original)
            self.assertEqual(result, recognize_source(session(source)))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [fact.span.extract(source) for fact in result.occurrences
             if fact.kind == "block_binding_unicode_boundary_candidate"],
            ["\u00a0↳", "\u202f↳"],
        )
        literal_start = source.index('"""\n')
        literal_end = source.rindex('"""\n') + len('"""\n')
        self.assertTrue(all(not (literal_start <= fact.span.start < literal_end)
                            for fact in result.occurrences))


if __name__ == "__main__":
    unittest.main()
