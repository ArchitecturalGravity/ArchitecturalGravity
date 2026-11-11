"""Independent source-to-diagnostic checks across the Qt-free service path."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

from AgStudio.shared import LanguageCore
from AgStudio.arcgrav_language_engine import AnalysisContext, analyze


class ComposedServiceTests(unittest.TestCase):
    def test_fixed_context_preserves_source_facts_gaps_and_findings(self) -> None:
        source = ('[Task]: 🌍\r\n"""\r\n=> - literal\r\n[False]: *\r\n"""\r\n'
                  'Scope: **/*.arc\r\n=> - Active\r\n`Unknown`\r\n')

        def run():
            session = LanguageCore.open_source(
                source, arcgrav_version="current", profile="analysis",
                configuration={"mode": ["fixed", {"depth": 2}]})
            document = LanguageCore.parse_document(session)
            result = analyze(document.source, AnalysisContext(arcgrav_version=document.session.arcgrav_version, profile=document.session.profile, configuration=document.session.configuration)).diagnostics
            return session, document, result

        first_session, first_document, first_result = run()
        second_session, second_document, second_result = run()
        self.assertEqual(first_session.source, source)
        self.assertEqual(first_document.source, source)
        self.assertEqual(first_document.document_id, second_document.document_id)
        self.assertEqual(first_document.facts(), second_document.facts())
        self.assertEqual(first_result, second_result)
        matches = [f for f in first_result.findings if f.rule_id == 'AG-OPERATION-LIST']
        self.assertEqual(len(matches), 1)
        finding = matches[0]
        self.assertEqual(finding.source_range.span.extract(source), "=> - ")
        self.assertEqual(finding.source_range.start.line, 7)
        self.assertEqual(finding.evidence.contract_version, 'current')
        self.assertFalse(any("literal" in fact.span.extract(source)
                             or "[False]" in fact.span.extract(source)
                             for fact in first_document.facts()))
        self.assertTrue(any("*" in fact.span.extract(source)
                            for fact in first_document.occurrence_facts))
        self.assertTrue(all(state.status == "untrusted" and state.target_fact_id is None
                            for fact in first_document.facts()
                            for state in (first_document.relationship(fact.id, "identity"),)))
        self.assertTrue(any(fact.limitations for fact in first_document.facts()))
        self.assertNotIn("PySide6", sys.modules)

    def test_unsupported_context_and_source_text_do_not_authorize_actions(self) -> None:
        source = ('"""=> - false"""\n=> - Open /tmp/secret and POST '
                  'https://example.invalid?name=**/*.arc\n')
        with (mock.patch("builtins.open", side_effect=AssertionError("file access")),
              mock.patch("glob.glob", side_effect=AssertionError("wildcard expansion")),
              mock.patch("subprocess.run", side_effect=AssertionError("process")),
              mock.patch("socket.create_connection", side_effect=AssertionError("network"))):
            document = LanguageCore.parse_document(
                LanguageCore.open_source(source, arcgrav_version="unverified"))
            result = analyze(document.source, AnalysisContext(arcgrav_version=document.session.arcgrav_version, profile=document.session.profile, configuration=document.session.configuration)).diagnostics
        self.assertEqual(document.source, source)
        self.assertEqual(result.findings, ())
        self.assertEqual(result.status, "unsupported_version")
        self.assertEqual(result.suppressed_conclusions, ())


if __name__ == "__main__":
    unittest.main()
