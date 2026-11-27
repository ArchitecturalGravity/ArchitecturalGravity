#!/usr/bin/env python3
"""Ensure generated benchmark reports are not mistaken for research papers."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from load_agent_reference import original_section, section_aliases

from validate_agent_references import RESEARCH, is_generated_agmark_report, sources, source_headings, heading_keys, inline_reference_link_issues, ROOT


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


class ReferenceAnchorTests(unittest.TestCase):
    def test_explicit_generated_detached_and_nested_fences(self) -> None:
        source = (
            '<a id="original"></a>\n\n<p>Cover</p>\n\n'
            '<a id="current"></a>\n# Title\n\n'
            '~~~text\n```md\n## Not a heading\n```\n~~~\n\n'
            '## Real section\nBody\n'
        )
        headings, ids = source_headings(source, Path("study.md"), [])
        self.assertEqual([(x[1], x[2]) for x in headings], [
            ("current", ("current",)), ("real-section", ())
        ])
        self.assertEqual(ids, {"current", "original"})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.md"
            path.write_text(source)
            self.assertEqual(original_section(path, "real-section"), "## Real section\nBody")
            self.assertIn("## Not a heading", original_section(path, "current"))

    def test_every_depth_contributes_a_required_key(self) -> None:
        md = "# Title\n## Section\n### Subsection\n#### Detail\n##### Example\n###### Caveat\n"
        problems = []
        self.assertEqual(heading_keys(md, Path("source.md"), problems),
                         ["title", "section", "subsection", "detail", "example", "caveat"])
        self.assertEqual(problems, [])

    def test_alias_parsing_and_duplicate_rejection(self) -> None:
        self.assertEqual(section_aliases("sections:\n"), {})
        content = "section_aliases:\n  legacy: current\nsections:\n"
        self.assertEqual(section_aliases(content), {"legacy": "current"})
        with self.assertRaises(ValueError):
            section_aliases(content.replace("sections:", "  legacy: another\nsections:"))

    def test_relative_reference_link_checks(self) -> None:
        ref = ROOT / "Research/Agent_References/Context_Triad/Context_Triad.yaml"
        self.assertEqual(inline_reference_link_issues(
            ref, "[good](../../Context_Triad/Context_Triad.md#paper-context-triad)"
        ), [])
        self.assertTrue(inline_reference_link_issues(ref, "[bad](missing.md)"))
        self.assertTrue(inline_reference_link_issues(
            ref, "[bad](../../Context_Triad/Context_Triad.md#does-not-exist)"
        ))


if __name__ == "__main__":
    unittest.main()
