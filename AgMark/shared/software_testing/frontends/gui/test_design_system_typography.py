"""Conformance tests for the GUI semantic typography registry."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    REQUIRED_TEXT_ROLES,
    SYSTEM_UI_FAMILY,
    TextStyle,
    Typography,
    text_style,
)


class DefaultTypographyTests(unittest.TestCase):
    def test_required_roles_are_complete_and_immutable(self) -> None:
        self.assertEqual(
            REQUIRED_TEXT_ROLES,
            frozenset(DEFAULT_TYPOGRAPHY.styles),
        )
        with self.assertRaises(TypeError):
            DEFAULT_TYPOGRAPHY.styles["body"] = TextStyle(  # type: ignore[index]
                SYSTEM_UI_FAMILY,
                14,
            )

    def test_incomplete_registry_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_TYPOGRAPHY.styles)
        incomplete.pop("console")
        with self.assertRaisesRegex(ValueError, "console"):
            Typography(styles=incomplete)

    def test_invalid_font_semantics_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "font family"):
            TextStyle("benchmark-success", 13)
        with self.assertRaisesRegex(ValueError, "font size"):
            TextStyle(SYSTEM_UI_FAMILY, 0)
        with self.assertRaisesRegex(ValueError, "font weight"):
            TextStyle(SYSTEM_UI_FAMILY, 13, 0)

    def test_semantic_lookup_rejects_unknown_roles(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic text role"):
            text_style("accepted-run")


if __name__ == "__main__":
    unittest.main()
