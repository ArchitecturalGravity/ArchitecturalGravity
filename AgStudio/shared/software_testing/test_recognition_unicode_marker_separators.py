"""Qt-free evidence for Unicode Zs immediately after list and arrow markers."""

import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import LanguageCore, SourceSession
from AgStudio.shared.recognition import recognize_source


def session(source, configuration=None):
    return SourceSession(
        source, arcgrav_version="unverified-test-version",
        profile="unicode-marker-separator-fixture",
        configuration=configuration,
    )


class UnicodeMarkerSeparatorTests(unittest.TestCase):
    def test_exact_marker_boundaries_and_deferred_shapes(self):
        candidates = (
            ("-\u00a0Item\r\n", "unordered_list_unicode_boundary_candidate",
             "syntax.unordered"),
            ("  12.\u2003Step\n", "ordered_list_unicode_boundary_candidate",
             "syntax.ordered"),
            ("P3.\u202fPriority\u2028", "priority_list_unicode_boundary_candidate",
             "syntax.priority"),
            ("=>\u00a0Transform\n", "operation_boundary_candidate",
             "syntax.operation"),
            ("  =>\u2003Transform\n", "operation_boundary_candidate",
             "syntax.operation"),
        )
        deferred = (
            "\t-\u00a0Tab-indented\n",
            "p3.\u00a0Lowercase priority\n",
            "-\u200bNon-Zs separator\n",
            "\t=>\u00a0Tab-indented\n",
            "Inline =>\u00a0arrow\n",
            "=>\u200bNon-Zs separator\n",
        )
        source = "".join(row[0] for row in candidates) + "".join(deferred)
        result = recognize_source(session(source))

        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [fact.kind for fact in result.observations],
            [row[1] for row in candidates] + ["unclassified"] * len(deferred),
        )
        cursor = 0
        for region, fact in zip(result.regions, result.observations):
            self.assertEqual(region.span.start, cursor)
            self.assertEqual(region.span, fact.span)
            self.assertEqual(region.text, fact.span.extract(source))
            cursor = region.span.end
        self.assertEqual(cursor, len(source))
        for fact, (_, _, syntax_id) in zip(result.observations, candidates):
            self.assertEqual(fact.syntax_id, syntax_id)
            self.assertEqual(fact.limitations, EXPECTED_LIMITATIONS[fact.kind])
            self.assertEqual(fact.claim_class, "recognition")

    def test_literal_shielding_fixed_context_and_no_document_actions(self):
        source = (
            "-\u00a0glob.glob('*.arc') *\n"
            '"""\n'
            "P3.\u202fHidden * [Symbol]\n"
            "=>\u00a0Hidden operation\n"
            '"""\n'
            "=>\u2003Visible operation\n"
        )
        original = session(source, {"scope": ["local"]})
        equivalent = session(source, {"scope": ["local"]})
        with (
            mock.patch("builtins.open", side_effect=AssertionError("filesystem")),
            mock.patch("glob.glob", side_effect=AssertionError("expansion")),
            mock.patch("os.system", side_effect=AssertionError("process")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            result = recognize_source(original)
            self.assertEqual(result, recognize_source(equivalent))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual(
            [fact.kind for fact in result.observations],
            ["unordered_list_unicode_boundary_candidate", "literal_open",
             "literal_content", "literal_content", "literal_close",
             "operation_boundary_candidate"],
        )
        self.assertEqual(
            [(fact.kind, fact.span.extract(source)) for fact in result.occurrences],
            [("wildcard_candidate", "*"), ("wildcard_candidate", "*")],
        )


if __name__ == "__main__":
    unittest.main()
