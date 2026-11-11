"""Conformance tests for the GUI semantic design-token registry."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    SEMANTIC_ICON_ROLES,
    Theme,
    apply_application_theme,
    application_style_sheet,
    color,
    semantic_icon,
)


_EXPECTED_ICON_ROLES = {
    "benchmark-start",
    "clear",
    "collapse",
    "console",
    "current-run-boundary",
    "current-run-plan",
    "current-run-treatments",
    "expand",
    "information",
    "plan-accept",
    "plan-build",
    "run-delete",
    "status-active",
    "status-error",
    "status-neutral",
    "status-success",
    "status-warning",
}


class DefaultLightThemeTests(unittest.TestCase):
    def test_semantic_icon_roles_are_explicit_and_fail_closed(self) -> None:
        self.assertEqual(SEMANTIC_ICON_ROLES, frozenset(_EXPECTED_ICON_ROLES))
        with self.assertRaisesRegex(KeyError, "unknown semantic icon role"):
            semantic_icon("generic-forward-arrow")
        with self.assertRaisesRegex(ValueError, "positive integer"):
            semantic_icon("plan-build", size=0)

    def test_status_bar_surface_is_subtle_gray(self) -> None:
        self.assertEqual(color("surface-status-bar"), "#D8DEE7")
        self.assertIn("background-color: #D8DEE7", application_style_sheet())
        self.assertIn("border-bottom: 1px solid #B8C9DC", application_style_sheet())

    def test_palette_is_immutable(self) -> None:
        with self.assertRaises(TypeError):
            DEFAULT_LIGHT_THEME.colors["text-primary"] = "#000000"  # type: ignore[index]

    def test_incomplete_theme_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_LIGHT_THEME.colors)
        incomplete.pop("focus-ring")

        with self.assertRaisesRegex(ValueError, "focus-ring"):
            Theme(name="incomplete", colors=incomplete)

    def test_invalid_color_fails_closed(self) -> None:
        invalid = dict(DEFAULT_LIGHT_THEME.colors)
        invalid["focus-ring"] = "blue"

        with self.assertRaisesRegex(ValueError, "focus-ring"):
            Theme(name="invalid", colors=invalid)

    def test_semantic_lookup_uses_registered_value_and_rejects_unknown_tokens(self) -> None:
        self.assertEqual(color("accent-primary"), DEFAULT_LIGHT_THEME.color("accent-primary"))
        with self.assertRaisesRegex(KeyError, "unknown semantic color token"):
            color("benchmark-is-successful")


try:
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication, QMenu, QStyle
except ImportError:
    _PYSIDE6_AVAILABLE = False
else:
    _PYSIDE6_AVAILABLE = True


@unittest.skipUnless(_PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class SemanticIconRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_application_theme_activation_sets_governed_palette_font_and_sheet(self) -> None:
        application = self._application
        previous_palette = application.palette()
        previous_font = application.font()
        previous_sheet = application.styleSheet()
        previous_active = application.property("arcgravDesignSystemActive")
        previous_theme = application.property("arcgravDesignSystemTheme")

        try:
            apply_application_theme(application)

            self.assertTrue(application.property("arcgravDesignSystemActive"))
            self.assertEqual(
                DEFAULT_LIGHT_THEME.name,
                application.property("arcgravDesignSystemTheme"),
            )
            self.assertEqual(
                DEFAULT_LIGHT_THEME.color("surface-background"),
                application.palette()
                .color(QPalette.ColorRole.Window)
                .name()
                .upper(),
            )
            self.assertEqual(
                DEFAULT_LIGHT_THEME.color("surface-panel"),
                application.palette()
                .color(QPalette.ColorRole.Base)
                .name()
                .upper(),
            )
            self.assertGreater(application.font().pixelSize(), 0)
            self.assertTrue(application.font().family())
            self.assertEqual(application_style_sheet(), application.styleSheet())
        finally:
            application.setPalette(previous_palette)
            application.setFont(previous_font)
            application.setStyleSheet(previous_sheet)
            application.setProperty("arcgravDesignSystemActive", previous_active)
            application.setProperty("arcgravDesignSystemTheme", previous_theme)

    def test_popup_menu_renders_semantic_surface_selection_and_disabled_text(self) -> None:
        menu = QMenu()
        menu.setStyleSheet(application_style_sheet())
        disabled = menu.addAction("Test")
        disabled.setEnabled(False)
        enabled = menu.addAction("Check")
        try:
            menu.show()
            self._application.processEvents()
            disabled_rect = menu.actionGeometry(disabled)
            enabled_rect = menu.actionGeometry(enabled)
            self.assertGreaterEqual(enabled_rect.height(), 30)
            normal = menu.grab().toImage()
            self.assertEqual(
                normal.pixelColor(enabled_rect.right() - 8, enabled_rect.center().y()).name().upper(),
                color("surface-panel"),
            )
            menu.setActiveAction(enabled)
            self._application.processEvents()
            selected = menu.grab().toImage()
            self.assertEqual(
                selected.pixelColor(enabled_rect.right() - 8, enabled_rect.center().y()).name().upper(),
                color("surface-selected"),
            )
            disabled_colors = {
                selected.pixelColor(x, y).name().upper()
                for x in range(disabled_rect.left(), disabled_rect.right())
                for y in range(disabled_rect.top(), disabled_rect.bottom())
            }
            self.assertIn(color("text-muted"), disabled_colors)
            self.assertNotIn(color("surface-selected"), disabled_colors)
            self.assertFalse(disabled.isEnabled())
        finally:
            menu.close()
            menu.deleteLater()

    def test_every_governed_role_renders_a_repository_owned_icon(self) -> None:
        for role in sorted(SEMANTIC_ICON_ROLES):
            with self.subTest(role=role):
                icon = semantic_icon(role)
                self.assertFalse(icon.isNull())
                pixmap = icon.pixmap(18, 18)
                self.assertFalse(pixmap.isNull())
                image = pixmap.toImage()
                self.assertTrue(
                    any(
                        image.pixelColor(x, y).alpha() > 0
                        for x in range(image.width())
                        for y in range(image.height())
                    )
                )

    def test_governed_roles_do_not_collapse_to_generic_or_unrelated_fallback_icons(self) -> None:
        rendered = {
            role: semantic_icon(role, size=24).pixmap(24, 24).toImage()
            for role in sorted(SEMANTIC_ICON_ROLES)
        }
        for role, image in rendered.items():
            with self.subTest(role=role):
                self.assertFalse(image.isNull())

        roles = tuple(rendered)
        for index, role in enumerate(roles):
            for other_role in roles[index + 1 :]:
                with self.subTest(role=role, other_role=other_role):
                    self.assertNotEqual(
                        rendered[role],
                        rendered[other_role],
                        "governed semantic roles must not share one generic fallback image",
                    )

        stock_images = {}
        style = self._application.style()
        for name, standard_pixmap in (
            ("arrow-right", QStyle.StandardPixmap.SP_ArrowRight),
            ("file", QStyle.StandardPixmap.SP_FileIcon),
            ("information", QStyle.StandardPixmap.SP_MessageBoxInformation),
        ):
            icon = style.standardIcon(standard_pixmap)
            if icon.isNull():
                continue
            image = icon.pixmap(24, 24).toImage()
            if not image.isNull():
                stock_images[name] = image

        self.assertTrue(stock_images, "Qt style must expose at least one stock fallback icon")
        for role, image in rendered.items():
            for stock_name, stock_image in stock_images.items():
                with self.subTest(role=role, stock=stock_name):
                    self.assertNotEqual(
                        image,
                        stock_image,
                        "repository-owned semantic icon must not resolve to Qt stock fallback",
                    )


if __name__ == "__main__":
    unittest.main()
