#!/usr/bin/env python3
"""Ensure generated benchmark reports are not mistaken for research papers."""
from __future__ import annotations

import unittest

from validate_agent_references import RESEARCH, is_generated_agmark_report, sources


class GeneratedAgMarkReportSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run_dir = RESEARCH / "Prompt_Performance/Studies/AgMark_Runs/Data" / ("generation-" + "a" * 64)

    def test_only_hashed_agmark_report_is_excluded(self) -> None:
        self.assertTrue(is_generated_agmark_report(self.run_dir / "report.md"))
        self.assertFalse(is_generated_agmark_report(self.run_dir / "README.md"))
        self.assertFalse(is_generated_agmark_report(self.run_dir / "report-notes.md"))
        self.assertFalse(is_generated_agmark_report(
            RESEARCH / "Prompt_Performance/Studies/AgMark_Runs/Data" / ("generation-" + "z" * 64) / "report.md"
        ))
        self.assertFalse(is_generated_agmark_report(
            RESEARCH / "Prompt_Performance/Studies/AgMark_Runs" / ("generation-" + "a" * 64) / "report.md"
        ))
        self.assertFalse(is_generated_agmark_report(
            RESEARCH / "Prompt_Performance/Studies/AgMark_Runs/Data" / ("a" * 64) / "report.md"
        ))

    def test_curated_markdown_remains_eligible(self) -> None:
        self.assertFalse(is_generated_agmark_report(RESEARCH / "README.md"))
        self.assertFalse(is_generated_agmark_report(
            RESEARCH / "Operational_Leverage/Studies/ArcGrav_Longitudinal_Operational_Leverage.md"
        ))
        self.assertIn(RESEARCH / "README.md", sources())

    def test_sources_exclude_generated_reports(self) -> None:
        run_reports = list(
            (RESEARCH / "Prompt_Performance/Studies/AgMark_Runs/Data")
            .glob("generation-*/report.md")
        )
        self.assertEqual(len(run_reports), 5)
        for report in run_reports:
            self.assertTrue(is_generated_agmark_report(report))
            self.assertNotIn(report, sources())


if __name__ == "__main__":
    unittest.main()
