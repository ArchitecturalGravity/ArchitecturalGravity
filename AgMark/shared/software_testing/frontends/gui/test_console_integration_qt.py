"""Integrated conformance for the GUI bottom-console authority boundary."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.shell.window import (
    BenchmarkShellWindow,
    CurrentRunProjection,
    ExecutionBoundaryProjection,
    PYSIDE6_AVAILABLE,
    RetainedRunProjection,
    RunPlanProjection,
    SidebarProjection,
    WorkspaceProjection,
)
from AgMark.gui.views.results import (
    ResultRowProjection,
    ResultsProjection,
    ResultsView,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel


def _workspace(prefix: str) -> WorkspaceProjection:
    return WorkspaceProjection(
        progress=QLabel(f"{prefix} progress"),
        results=QLabel(f"{prefix} results"),
        reports=QLabel(f"{prefix} reports"),
        verification=QLabel(f"{prefix} verification"),
        evidence=QLabel(f"{prefix} artifacts"),
        scoring=QLabel("Scoring"),
    )


def _current_run(state_label: str, *, timestamp: str) -> CurrentRunProjection:
    return CurrentRunProjection(
        run_identity="Run Active",
        state_label=state_label,
        state_tone="neutral",
        timestamp=timestamp,
        execution_boundary=ExecutionBoundaryProjection(
            benchmark="Authority Resolution",
            runner="Codex CLI",
            model="gpt-5.6",
            cases="1 case",
            boundary_fingerprint="sha256:boundary",
        ),
        run_plan=RunPlanProjection(
            treatments="1 treatment",
            cases="1 case",
            execution="1 execution",
            evaluation="1 evaluation",
            outputs="Retained evidence",
        ),
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class IntegratedConsoleBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        icon_pixmap = QPixmap(16, 16)
        icon_pixmap.fill(Qt.GlobalColor.black)
        self.application_icon = QIcon(icon_pixmap)

    def test_generation_bound_console_preserves_redaction_and_cannot_create_authority(self) -> None:
        results_view = ResultsView(
            ResultsProjection(
                run_id="run-a",
                rows=(
                    ResultRowProjection(
                        treatment="Control",
                        score=1,
                        evidence="Available",
                        status="Accepted",
                        status_icon="✓",
                    ),
                    ResultRowProjection(
                        treatment="Treatment A",
                        score=0,
                        evidence="Available",
                        status="Accepted",
                        status_icon="✓",
                    ),
                ),
            )
        )
        run_a_workspace = WorkspaceProjection(
            progress=QLabel("run-a progress"),
            results=results_view,
            reports=QLabel("run-a reports"),
            verification=QLabel("run-a verification"),
            evidence=QLabel("run-a artifacts"),
            scoring=QLabel("Scoring"),
        )
        run_b_workspace = _workspace("run-b")
        sidebar = SidebarProjection(
            runs=(
                RetainedRunProjection(
                    run_id="run-a",
                    display_identity="Run A",
                    state_label="AcceptedRun",
                    state_tone="success",
                    timestamp="2026-09-21 14:00",
                    selected=True,
                ),
                RetainedRunProjection(
                    run_id="run-b",
                    display_identity="Run B",
                    state_label="BlockedRun",
                    state_tone="neutral",
                    timestamp="2026-09-21 14:10",
                ),
            )
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=sidebar,
            current_run_projection=_current_run("InProgress", timestamp="2026-09-21 14:20"),
            retained_workspace_projections={
                "run-a": run_a_workspace,
                "run-b": run_b_workspace,
            },
        )
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()

        console = window.console_widget
        environment_text = (
            "[READY] Runtime: provider-free\n"
            "[INFO] Evidence: benchmark-owned\n"
        )
        console.set_environment(environment_text)
        console.bind_generation("generation-current")

        secret = "should-never-render"
        self.assertFalse(
            console.append_live_output(
                "generation-stale",
                f"Authorization: Bearer {secret}\n",
            )
        )
        self.assertFalse(
            console.append_diagnostic(
                "generation-stale",
                f"token={secret}\n",
            )
        )
        self.assertFalse(
            console.set_raw_response(
                "generation-stale",
                "stale retained response",
            )
        )

        redacted_live = "Authorization: Bearer [redacted]\nAcceptedRun\n"
        redacted_diagnostic = "token=[redacted]\ndiagnostic success\n"
        retained_response = '{"response":"exact-retained-payload","ok":true}\n'

        self.assertTrue(
            console.append_live_output("generation-current", redacted_live)
        )
        self.assertTrue(
            console.append_diagnostic("generation-current", redacted_diagnostic)
        )
        self.assertTrue(
            console.set_raw_response("generation-current", retained_response)
        )
        QApplication.processEvents()

        console.set_active_tab("Live View")
        self.assertEqual("", console.state.visible_text)
        console.stream_output_checkbox.setChecked(True)
        self.assertTrue(console.state.visible_text.endswith(retained_response))
        self.assertNotIn(secret, console.state.visible_text)
        console.set_active_tab("Diagnostics")
        self.assertEqual(console.state.visible_text, redacted_live + redacted_diagnostic)
        self.assertNotIn(secret, console.state.visible_text)
        console.set_active_tab("Live View")
        self.assertIn("Output:\n" + retained_response, console.state.visible_text)
        self.assertEqual(console.state.retained_raw_response, retained_response)
        self.assertNotIn(redacted_live, console.state.visible_text)
        self.assertNotIn(redacted_diagnostic, console.state.visible_text)
        console.set_active_tab("Environment")
        self.assertEqual(console.state.visible_text, environment_text)
        self.assertNotIn(retained_response, console.state.visible_text)
        self.assertNotIn(redacted_live, console.state.visible_text)
        self.assertNotIn(redacted_diagnostic, console.state.visible_text)

        self.assertEqual(window.current_run_status.label, "InProgress")
        self.assertEqual(
            window.current_run_region.property("authoritySemantics"),
            "presentation-only",
        )

        window.workspace_tabs.setCurrentIndex(1)
        results_view.cache_table.selectRow(1)
        QApplication.processEvents()
        self.assertEqual(
            results_view.cache_table.currentIndex().row(),
            1,
        )
        self.assertEqual(2, len(results_view.treatment_buttons))
        self.assertEqual(console.state.active_generation_id, "generation-current")
        self.assertEqual(console.state.retained_raw_response, retained_response)
        self.assertEqual(console.state.active_tab, "Environment")
        self.assertEqual(console.state.visible_text, environment_text)
        console.set_active_tab("Live View")
        self.assertTrue(console.state.visible_text.endswith(retained_response))
        console.set_active_tab("Live View")
        self.assertIn("Output:\n" + retained_response, console.state.visible_text)
        console.set_active_tab("Diagnostics")
        self.assertEqual(console.state.visible_text, redacted_live + redacted_diagnostic)
        console.set_active_tab("Environment")
        self.assertEqual(console.state.visible_text, environment_text)

        QTest.mouseClick(
            window.run_rows["run-b"],
            Qt.MouseButton.LeftButton,
        )
        QApplication.processEvents()
        self.assertEqual(window.selected_run_id, "run-b")
        self.assertEqual(window.workspace_projection_run_id, "run-b")
        self.assertEqual(console.state.active_generation_id, "generation-current")
        self.assertEqual(console.state.retained_raw_response, retained_response)
        self.assertEqual(console.state.active_tab, "Environment")
        self.assertEqual(console.state.visible_text, environment_text)

        window.set_current_run_projection(
            _current_run("AcceptedRun", timestamp="2026-09-21 14:30")
        )
        QApplication.processEvents()
        self.assertEqual(window.current_run_status.label, "AcceptedRun")
        self.assertEqual(console.state.active_generation_id, "generation-current")
        self.assertEqual(console.state.retained_raw_response, retained_response)
        self.assertEqual(console.state.active_tab, "Environment")
        self.assertEqual(console.state.visible_text, environment_text)


if __name__ == "__main__":
    unittest.main()
