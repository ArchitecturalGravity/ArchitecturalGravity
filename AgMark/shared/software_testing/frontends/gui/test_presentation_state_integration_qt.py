"""Integrated conformance for GUI presentation-state isolation.

This test keeps shell and console preferences on the frontend side of the public
command boundary while exercising the real provider-free shared lifecycle.  It
does not create benchmark authority; it verifies that GUI-local persistence
cannot flow into shared planning, accepted snapshots, evidence, reports, or
reconstruction verification.
"""

from __future__ import annotations

from contextlib import ExitStack
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import AgMark.shared.software_testing.self_testing.dry_run as shared_dry_run
from AgMark.gui.shell.window import (
    BenchmarkShellWindow,
    PYSIDE6_AVAILABLE,
    REFERENCE_SIDEBAR_WIDTH,
    SHELL_CONSOLE_EXPANDED_KEY,
    SHELL_CONSOLE_TAB_KEY,
    SHELL_SIDEBAR_WIDTH_KEY,
    SHELL_WINDOW_HEIGHT_KEY,
    SHELL_WINDOW_WIDTH_KEY,
    SHELL_WORKSPACE_TAB_KEY,
    SidebarInputSnapshot,
    SidebarProjection,
)
from AgMark.gui.widgets.console import LAST_EXPANDED_HEIGHT_KEY

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QApplication


_PRESENTATION_KEYS = (
    SHELL_WINDOW_WIDTH_KEY,
    SHELL_WINDOW_HEIGHT_KEY,
    SHELL_SIDEBAR_WIDTH_KEY,
    SHELL_WORKSPACE_TAB_KEY,
    SHELL_CONSOLE_TAB_KEY,
    SHELL_CONSOLE_EXPANDED_KEY,
    LAST_EXPANDED_HEIGHT_KEY,
)

_SHARED_BOUNDARIES = (
    "plan_run",
    "accept_run_plan",
    "admit_accepted_execution",
    "execute_planned_treatments",
    "score_accepted_treatments",
    "finalize_scored_run",
    "admit_finalized_run_for_reporting",
    "build_canonical_report_model",
    "generate_report_bundle",
)


def _inline_dispatch(operation):
    return operation()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class PresentationStateIsolationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        icon_pixmap = QPixmap(16, 16)
        icon_pixmap.fill(Qt.GlobalColor.black)
        self.application_icon = QIcon(icon_pixmap)

    def _assert_presentation_keys_absent(self, value: object, *, context: str) -> None:
        rendered = repr(value)
        for key in _PRESENTATION_KEYS:
            self.assertNotIn(key, rendered, msg=f"{key!r} leaked into {context}")

    def test_persisted_layout_state_never_enters_shared_authority(self) -> None:
        shell_preferences: dict[str, object] = {
            SHELL_WINDOW_WIDTH_KEY: 1111,
            SHELL_WINDOW_HEIGHT_KEY: 777,
            SHELL_SIDEBAR_WIDTH_KEY: 10_000,
            SHELL_WORKSPACE_TAB_KEY: 4,
            SHELL_CONSOLE_TAB_KEY: "Diagnostics",
            SHELL_CONSOLE_EXPANDED_KEY: False,
        }
        console_preferences: dict[str, int] = {
            LAST_EXPANDED_HEIGHT_KEY: 341,
        }
        snapshots: list[SidebarInputSnapshot] = []
        lifecycle_results: list[shared_dry_run.DeterministicDryRunResult] = []
        observed_boundaries: list[str] = []

        def build_plan(snapshot: SidebarInputSnapshot) -> None:
            self._assert_presentation_keys_absent(
                snapshot,
                context="GUI Build Plan intent",
            )
            snapshots.append(snapshot)
            lifecycle_results.append(shared_dry_run.run_deterministic_dry_run())

        sidebar = SidebarProjection(
            benchmark_options=("Shared diagnostic",),
            selected_benchmark="Shared diagnostic",
            runner_options=("Deterministic mock",),
            selected_runner="Deterministic mock",
            model_options=("Provider-free",),
            selected_model="Provider-free",
            credential_value="transient-only-secret",
            build_plan_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            shell_preferences=shell_preferences,
            console_preferences=console_preferences,
            sidebar_projection=sidebar,
            on_build_plan=build_plan,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()

        self.assertEqual(window.workspace_tabs.tabText(window.workspace_tabs.currentIndex()), "Evidence")
        self.assertEqual(window.sidebar.width(), REFERENCE_SIDEBAR_WIDTH)
        self.assertEqual(shell_preferences[SHELL_SIDEBAR_WIDTH_KEY], 10_000)

        originals = {
            name: getattr(shared_dry_run, name)
            for name in _SHARED_BOUNDARIES
        }

        def wrapper(name: str):
            original = originals[name]

            def invoke(*args, **kwargs):
                self._assert_presentation_keys_absent(
                    (args, kwargs),
                    context=f"{name} input",
                )
                result = original(*args, **kwargs)
                self._assert_presentation_keys_absent(
                    result,
                    context=f"{name} result",
                )
                observed_boundaries.append(name)
                return result

            return invoke

        with ExitStack() as stack:
            for name in _SHARED_BOUNDARIES:
                stack.enter_context(
                    patch.object(shared_dry_run, name, side_effect=wrapper(name))
                )

            window.build_plan_button.click()
            QApplication.processEvents()

            window.resize(1234, 812)
            QApplication.processEvents()
            self.assertEqual(window.sidebar.width(), REFERENCE_SIDEBAR_WIDTH)
            self.assertEqual(shell_preferences[SHELL_SIDEBAR_WIDTH_KEY], 10_000)
            reports_index = next(
                index for index in range(window.workspace_tabs.count())
                if window.workspace_tabs.tabText(index) == "Reports"
            )
            window.workspace_tabs.set_selected_index(reports_index)
            window.console_widget.set_active_tab("Live View")
            window.set_console_height(409)
            window.console_widget.set_expanded(True)
            QApplication.processEvents()

            window.build_plan_button.click()
            QApplication.processEvents()

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(
            snapshots[0],
            SidebarInputSnapshot(
                benchmark="Shared diagnostic",
                runner="Deterministic mock",
                model="Provider-free",
                credential="transient-only-secret",
                temperature=None,
                max_tokens=None,
            ),
        )
        self.assertEqual(lifecycle_results[0], lifecycle_results[1])
        self.assertEqual(
            lifecycle_results[0].verification_result.status,
            "verified",
        )
        self.assertFalse(lifecycle_results[0].authoritative)

        for name in _SHARED_BOUNDARIES:
            self.assertEqual(
                observed_boundaries.count(name),
                2,
                msg=f"{name} was not exercised once per GUI command",
            )

        self.assertEqual(shell_preferences[SHELL_WINDOW_WIDTH_KEY], 1234)
        self.assertEqual(shell_preferences[SHELL_WINDOW_HEIGHT_KEY], 812)
        self.assertEqual(
            shell_preferences[SHELL_SIDEBAR_WIDTH_KEY],
            10_000,
        )
        self.assertEqual(shell_preferences[SHELL_WORKSPACE_TAB_KEY], "Reports")
        self.assertEqual(shell_preferences[SHELL_CONSOLE_TAB_KEY], "Live View")
        self.assertIs(shell_preferences[SHELL_CONSOLE_EXPANDED_KEY], True)
        self.assertEqual(console_preferences[LAST_EXPANDED_HEIGHT_KEY], 409)

        self._assert_presentation_keys_absent(
            lifecycle_results,
            context="shared lifecycle observable results",
        )


if __name__ == "__main__":
    unittest.main()
