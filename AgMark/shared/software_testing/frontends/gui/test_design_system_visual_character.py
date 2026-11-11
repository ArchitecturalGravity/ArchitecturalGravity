"""Semantic status cues must remain distinguishable in the GUI."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.status import REQUIRED_STATUS_TONES, resolved_status


class DefaultVisualCharacterTests(unittest.TestCase):
    def test_required_status_tones_remain_semantically_distinct(self) -> None:
        resolved = {
            tone: resolved_status(f"state-{tone}", tone)
            for tone in REQUIRED_STATUS_TONES
        }

        self.assertEqual(set(resolved), {"success", "warning", "error", "active", "neutral"})
        self.assertEqual(
            len({(badge.foreground, badge.background, badge.icon_key) for badge in resolved.values()}),
            len(REQUIRED_STATUS_TONES),
        )


if __name__ == "__main__":
    unittest.main()
