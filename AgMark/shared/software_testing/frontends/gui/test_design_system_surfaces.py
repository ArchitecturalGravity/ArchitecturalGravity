"""Conformance tests for GUI borders, surfaces, and elevation semantics."""

from __future__ import annotations

import unittest

from AgMark.gui.design_system.surfaces import (
    DEFAULT_SURFACES,
    REQUIRED_SURFACE_ROLES,
    SurfaceRegistry,
    SurfaceStyle,
    surface_style,
)


class DefaultSurfaceRegistryTests(unittest.TestCase):
    def test_required_surface_roles_are_complete_and_immutable(self) -> None:
        self.assertEqual(
            frozenset(DEFAULT_SURFACES.styles),
            REQUIRED_SURFACE_ROLES,
        )
        with self.assertRaises(TypeError):
            DEFAULT_SURFACES.styles["panel"] = SurfaceStyle(  # type: ignore[index]
                background_token="surface-background"
            )

    def test_workspace_console_selection_focus_and_active_tab_are_distinct(self) -> None:
        self.assertNotEqual(
            surface_style("workspace").background_token,
            surface_style("console").background_token,
        )
        self.assertNotEqual(
            surface_style("panel").background_token,
            surface_style("selected-row").background_token,
        )
        self.assertEqual(surface_style("focused-control").border_token, "focus-ring")
        self.assertEqual(surface_style("active-tab").border_token, "accent-primary")
        self.assertEqual(surface_style("selected-row").border_token, "border-strong")

    def test_incomplete_registry_fails_closed(self) -> None:
        incomplete = dict(DEFAULT_SURFACES.styles)
        incomplete.pop("console")

        with self.assertRaisesRegex(ValueError, "console"):
            SurfaceRegistry(styles=incomplete)

    def test_invalid_border_pairing_and_heavy_elevation_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "supplied together"):
            SurfaceStyle(
                background_token="surface-panel",
                border_token="border-default",
            )

        with self.assertRaisesRegex(ValueError, "restrained"):
            SurfaceStyle(
                background_token="surface-panel",
                elevation=2,
            )

    def test_unknown_semantic_references_fail_on_resolution(self) -> None:
        invalid = dict(DEFAULT_SURFACES.styles)
        invalid["panel"] = SurfaceStyle(background_token="benchmark-success")
        registry = SurfaceRegistry(styles=invalid)

        with self.assertRaisesRegex(KeyError, "unknown semantic color token"):
            registry.resolve("panel")

    def test_unknown_surface_role_is_rejected(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic surface role"):
            surface_style("accepted-run")


if __name__ == "__main__":
    unittest.main()
