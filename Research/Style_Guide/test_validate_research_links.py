#!/usr/bin/env python3
"""Regression checks for archive-backed versus ordinary Research links."""
from __future__ import annotations

import unittest
from pathlib import Path

from validate_research_links import ROOT, archived_agmark_link_exists

DATA = ROOT / "Prompt_Performance/Studies/AgMark_Runs/Data"
ARCHIVED_NAMES = ("report.json", "canonical-evidence.json", "report-manifest.json")


class ArchivedAgMarkLinkTests(unittest.TestCase):
    def test_known_links_exist_in_all_five_archives(self) -> None:
        reports = sorted(DATA.glob("generation-*/report.md"))
        self.assertEqual(len(reports), 5)
        for report in reports:
            for member in ARCHIVED_NAMES:
                with self.subTest(report=report.parent.name, member=member):
                    self.assertTrue(archived_agmark_link_exists(report, member))

    def test_unknown_member_is_not_exempt(self) -> None:
        report = next(DATA.glob("generation-*/report.md"))
        self.assertFalse(archived_agmark_link_exists(report, "nonexistent.json"))
        self.assertFalse(archived_agmark_link_exists(report, "../report.json"))
        self.assertFalse(archived_agmark_link_exists(report, "report.md"))

    def test_curated_research_links_are_not_exempt(self) -> None:
        self.assertFalse(
            archived_agmark_link_exists(
                ROOT / "Prompt_Performance/Studies/AgMark_Runs/AgMark_Prompt_Performance.md",
                "report.json",
            )
        )
        self.assertFalse(archived_agmark_link_exists(Path("/tmp/report.md"), "report.json"))


if __name__ == "__main__":
    unittest.main()
