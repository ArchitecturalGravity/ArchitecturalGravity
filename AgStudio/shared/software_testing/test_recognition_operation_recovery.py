"""Qt-free evidence for line-local, untrusted bare-arrow recovery."""

import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import LanguageCore, SourceSession
from AgStudio.shared.recognition import RecognitionResult, SourceRecovery, SourceSpan, recognize_source


def session(source):
    return SourceSession(
        source, arcgrav_version="unverified-test-version",
        profile="bare-operation-recovery-fixture",
    )


class BareOperationRecoveryTests(unittest.TestCase):
    def test_bare_arrows_resume_at_physical_lines_without_validity_claims(self):
        source = (
            "=>\r\n"
            "  =>\u2028"
            "Task: value\n"
            "=>NoSpace\n"
            "\t=>\n"
            "=> \n"
            "=>"
        )
        result = recognize_source(session(source))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual([fact.kind for fact in result.observations], [
            "operation_boundary_candidate", "operation_boundary_candidate",
            "section_scalar_candidate", "unclassified", "unclassified",
            "operation_candidate", "operation_boundary_candidate",
        ])
        self.assertEqual([fact.kind for fact in result.recoveries],
                         ["unfinished_operation"] * 3)
        for recovery in result.recoveries:
            self.assertEqual(recovery.span.extract(source), "=>")
            self.assertEqual(recovery.trust, "untrusted")
            self.assertEqual(recovery.claim_class, "recognition")
            self.assertEqual(recovery.limitations, EXPECTED_LIMITATIONS[recovery.kind])
            self.assertEqual(recovery.resume_at,
                             next(region.span.end for region in result.regions
                                  if region.span.start <= recovery.span.start
                                  < region.span.end))

        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              result.observations, result.occurrences,
                              result.recoveries[:-1])
        forged = SourceRecovery(SourceSpan(source.index("=>NoSpace"),
                                           source.index("=>NoSpace") + 2),
                                source.index("=>NoSpace") + len("=>NoSpace\n"),
                                "unfinished_operation")
        with self.assertRaises(ValueError):
            RecognitionResult(result.session, result.regions,
                              result.observations, result.occurrences,
                              tuple(sorted((*result.recoveries, forged),
                                           key=lambda item: item.span.start)))

    def test_literal_isolation_repeatability_and_inert_document_text(self):
        source = (
            "=>\n"
            '"""\n'
            "=>\n"
            '"""\n'
            "=> glob.glob('*.arc')\n"
            "  =>"
        )
        with (
            mock.patch("builtins.open", side_effect=AssertionError("filesystem")),
            mock.patch("glob.glob", side_effect=AssertionError("expansion")),
            mock.patch("os.system", side_effect=AssertionError("process")),
            mock.patch("subprocess.run", side_effect=AssertionError("process")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
        ):
            result = recognize_source(session(source))
            self.assertEqual(result, recognize_source(session(source)))
        self.assertEqual(result.round_trip(), source)
        self.assertEqual([fact.kind for fact in result.observations], [
            "operation_boundary_candidate", "literal_open", "literal_content",
            "literal_close", "operation_candidate", "operation_boundary_candidate",
        ])
        self.assertEqual([fact.span.extract(source) for fact in result.recoveries],
                         ["=>", "=>"])


if __name__ == "__main__":
    unittest.main()
