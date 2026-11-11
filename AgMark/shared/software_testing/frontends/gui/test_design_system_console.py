"""Conformance tests for GUI console-presentation semantics."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from AgMark.gui.design_system.console import (
    DEFAULT_CONSOLE_PRESENTATION,
    ConsolePresentationStyle,
    resolved_console_presentation,
)
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    SYSTEM_UI_FAMILY,
    TextStyle,
    Typography,
)


class ConsolePresentationTests(unittest.TestCase):
    def test_default_console_resolves_reference_terminal_scheme(self) -> None:
        resolved = resolved_console_presentation()

        self.assertEqual(resolved.background, "#18212C")
        self.assertEqual(resolved.text, "#F2F5F8")
        self.assertEqual(resolved.muted, "#9AA8BA")
        self.assertEqual(resolved.info, "#31B7FF")
        self.assertEqual(resolved.progress, "#43D35C")
        self.assertEqual(resolved.warning, "#FFB423")
        self.assertEqual(resolved.error, "#F0212D")
        self.assertTrue(resolved.monospace)
        self.assertEqual(resolved.font_family, "system-monospace")
        self.assertGreaterEqual(resolved.font_size_px, 14)
        self.assertLessEqual(resolved.font_size_px, 16)

    def test_console_contract_preserves_source_and_remains_presentation_only(self) -> None:
        resolved = resolved_console_presentation()

        self.assertEqual(resolved.source_content_semantics, "preserve-exact-source")
        self.assertEqual(resolved.authority_semantics, "presentation-only")
        with self.assertRaises(FrozenInstanceError):
            DEFAULT_CONSOLE_PRESENTATION.text_token = "text-primary"  # type: ignore[misc]

    def test_console_style_rejects_content_or_authority_reinterpretation(self) -> None:
        with self.assertRaisesRegex(ValueError, "preserve exact source"):
            ConsolePresentationStyle(source_content_semantics="normalized")
        with self.assertRaisesRegex(ValueError, "presentation-only"):
            ConsolePresentationStyle(authority_semantics="claim-ready")

    def test_console_resolution_requires_monospace_typography(self) -> None:
        styles = dict(DEFAULT_TYPOGRAPHY.styles)
        styles["console"] = TextStyle(SYSTEM_UI_FAMILY, 15, 400)
        typography = Typography(styles=styles)

        with self.assertRaisesRegex(ValueError, "monospace"):
            resolved_console_presentation(typography=typography)

    def test_console_resolution_uses_semantic_tokens_and_fails_closed(self) -> None:
        with self.assertRaises(KeyError):
            resolved_console_presentation(
                style=ConsolePresentationStyle(text_token="not-a-token")
            )

        colors = dict(DEFAULT_LIGHT_THEME.colors)
        colors["console-text"] = colors["console-background"]
        indistinguishable_theme = Theme(
            name="indistinguishable-console",
            colors=colors,
        )
        with self.assertRaisesRegex(ValueError, "distinguishable"):
            resolved_console_presentation(theme=indistinguishable_theme)


if __name__ == "__main__":
    unittest.main()
