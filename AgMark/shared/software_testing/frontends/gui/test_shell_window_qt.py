"""Conformance tests for the concrete PySide6 persistent desktop shell frame."""

from __future__ import annotations

import os
import unittest

from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS
from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    compact_splitter_handle_extent,
    semantic_icon,
)
from AgMark.gui.shell.window import (
    BenchmarkShellWindow,
    CURRENT_RUN_BOUNDARY_LABELS,
    CURRENT_RUN_EMPTY_MESSAGE,
    CURRENT_RUN_EMPTY_TITLE,
    CURRENT_RUN_PLAN_LABELS,
    CurrentRunProjection,
    ExecutionBoundaryProjection,
    NumericInputProjection,
    PYSIDE6_AVAILABLE,
    MINIMUM_TAB_CONTENT_HEIGHT,
    MINIMUM_TAB_CONTENT_WIDTH,
    REFERENCE_CONFIGURATION_VIEWPORT_HEIGHT,
    REFERENCE_SIDEBAR_WIDTH,
    REFERENCE_WINDOW_HEIGHT,
    REFERENCE_WINDOW_WIDTH,
    RetainedRunProjection,
    RunPlanProjection,
    SIDEBAR_SECTION_ORDER,
    SidebarChoiceControlProjection,
    SidebarControlInputSnapshot,
    SidebarInputSnapshot,
    SidebarModelChoiceProjection,
    SidebarNumericControlProjection,
    SidebarPrerequisiteDiagnosticProjection,
    SidebarProjection,
    SidebarTextControlProjection,
    SHELL_CONSOLE_EXPANDED_KEY,
    SHELL_CONSOLE_TAB_KEY,
    SHELL_SIDEBAR_WIDTH_KEY,
    SHELL_WINDOW_HEIGHT_KEY,
    SHELL_WINDOW_WIDTH_KEY,
    SHELL_WORKSPACE_TAB_KEY,
    WINDOW_TITLE,
    WORKSPACE_TAB_LABELS,
    WorkspaceProjection,
)
from AgMark.gui.widgets.console import CONSOLE_TABS, LAST_EXPANDED_HEIGHT_KEY
from AgMark.gui.views.progress import (
    ProgressEventProjection,
    ProgressProjection,
    ProgressView,
)


def _inline_dispatch(operation):
    return operation()


if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QMenuBar,
        QSizePolicy,
        QSplitter,
        QWidget,
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class BenchmarkShellWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.preferences: dict[str, int] = {}
        icon_pixmap = QPixmap(16, 16)
        icon_pixmap.fill(Qt.GlobalColor.black)
        self.application_icon = QIcon(icon_pixmap)
        self.window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            connectivity_label="Offline",
            connectivity_tone="neutral",
            console_preferences=self.preferences,
            shell_preferences={SHELL_CONSOLE_EXPANDED_KEY: True},
        )
        self.addCleanup(self.window.deleteLater)

    def test_status_bar_actions_fit_text_without_fixed_height(self) -> None:
        from AgMark.gui.widgets.buttons import ActionButton
        button = ActionButton("Import Run", "secondary", content_sized=True)
        self.window.shell_status_bar.addPermanentWidget(button)
        self.window.show()
        self._application.processEvents()
        for action in (button, self.window.cancel_execution_button):
            self.assertEqual(action.minimumHeight(), 0)
            self.assertGreater(action.maximumHeight(), 1000)
            self.assertGreaterEqual(action.sizeHint().height(), action.fontMetrics().height())
        ordinary = ActionButton("Ordinary", "secondary")
        self.assertEqual(ordinary.minimumHeight(), DEFAULT_LAYOUT_METRICS.metric("control-height"))
        ordinary.deleteLater()

    def test_native_window_and_primary_region_order_match_shell_contract(self) -> None:
        self.assertEqual(self.window.windowTitle(), WINDOW_TITLE)
        self.assertFalse(self.window.windowIcon().isNull())
        self.assertEqual(
            self.window.windowIcon().cacheKey(),
            self.application_icon.cacheKey(),
        )
        self.assertIsNone(self.window.menuWidget())
        self.assertEqual(self.window.findChildren(QMenuBar), [])
        self.assertEqual(self.window.authority_semantics, "presentation-only")

        splitter = self.window.vertical_splitter
        self.assertIs(self.window.centralWidget().layout().itemAt(0).widget(), splitter)
        self.assertEqual(splitter.orientation(), Qt.Orientation.Vertical)
        self.assertEqual(splitter.count(), 2)
        self.assertIs(splitter.widget(0), self.window.upper_work_area)
        self.assertIs(splitter.widget(1), self.window.console_widget)

        upper_layout = self.window.upper_work_area.layout()
        self.assertEqual(upper_layout.count(), 2)
        self.assertIs(upper_layout.itemAt(0).widget(), self.window.sidebar)
        self.assertIs(upper_layout.itemAt(1).widget(), self.window.workspace_column)
        self.assertEqual(upper_layout.spacing(), 0)
        self.assertEqual(
            [item for item in self.window.findChildren(QSplitter)
             if item.orientation() == Qt.Orientation.Horizontal], [],
        )
        self.assertEqual(self.window.sidebar.minimumWidth(), REFERENCE_SIDEBAR_WIDTH)
        self.assertEqual(self.window.sidebar.maximumWidth(), REFERENCE_SIDEBAR_WIDTH)
        self.assertIs(self.window.workspace_scroll.widget(), self.window.workspace)
        self.assertFalse(self.window.workspace_scroll.widgetResizable())
        self.assertEqual(
            self.window.workspace_scroll.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(
            self.window.workspace_scroll.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(self.window.workspace.minimumWidth(), 0)
        self.assertEqual(self.window.workspace.minimumHeight(), 0)
        self.assertEqual(self.window.sidebar.width(), REFERENCE_SIDEBAR_WIDTH)
        page_padding = DEFAULT_LAYOUT_METRICS.metric("page-padding")
        self.assertEqual(
            self.window.sidebar_layout.getContentsMargins(),
            (page_padding, page_padding, page_padding, page_padding),
        )
        self.assertEqual(
            self.window.sidebar_layout.spacing(),
            DEFAULT_LAYOUT_METRICS.metric("stack-gap"),
        )
        self.assertEqual(
            self.window.configuration_form_layout.horizontalSpacing(),
            DEFAULT_LAYOUT_METRICS.metric("related-gap"),
        )
        self.assertEqual(
            self.window.configuration_form_layout.verticalSpacing(),
            DEFAULT_LAYOUT_METRICS.metric("related-gap"),
        )
        unavailable_page = self.window.workspace_pages[WORKSPACE_TAB_LABELS[0]]
        unavailable_scroll = self.window.workspace_tabs.widget(0)
        self.assertIs(unavailable_scroll.widget(), unavailable_page)
        margins = unavailable_scroll.viewportMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (page_padding, page_padding, page_padding, page_padding),
        )
        self.assertEqual(unavailable_page.layout().getContentsMargins(), (0, 0, 0, 0))

    def test_current_run_empty_state_is_deliberate_and_replaced_by_projection(
        self,
    ) -> None:
        self.assertEqual(self.window.current_run_heading.text(), "Current Run")
        self.assertEqual(
            self.window.current_run_empty_state_card.title,
            CURRENT_RUN_EMPTY_TITLE,
        )
        self.assertEqual(
            self.window.current_run_empty_state_label.text(),
            CURRENT_RUN_EMPTY_MESSAGE,
        )
        self.assertEqual(
            self.window.current_run_empty_state_label.accessibleName(),
            "Current Run empty state",
        )
        self.assertTrue(self.window.current_run_empty_state_label.wordWrap())
        self.assertEqual(
            self.window.current_run_empty_state_card.property("authoritySemantics"),
            "presentation-only",
        )
        self.assertIsNone(self.window.current_run_identity_label)
        self.assertIsNone(self.window.current_run_status)
        self.assertIsNone(self.window.accept_plan_button)
        self.assertIsNone(self.window.start_benchmark_button)

        projection = CurrentRunProjection(
            run_identity="Run A",
            state_label="Planned",
            state_tone="neutral",
            timestamp="2026-09-22 21:00",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="Authority Resolution",
                runner="Codex CLI",
                model="gpt-5.6",
                cases="24",
                boundary_fingerprint="sha256:caller-owned-boundary",
            ),
            run_plan=RunPlanProjection(
                treatments="Baseline, treatment-a",
                cases="24 cases",
                execution="2 repetitions",
                evaluation="Exact + semantic",
                outputs="Accepted evidence + report",
            ),
        )
        self.window.set_current_run_projection(projection)
        QApplication.processEvents()

        self.assertIsNone(self.window.current_run_empty_state_card)
        self.assertIsNone(self.window.current_run_empty_state_label)
        self.assertEqual(self.window.current_run_identity_label.text(), "Run A")
        self.assertEqual(self.window.current_run_status.label, "Planned")
        self.assertEqual(
            self.window.execution_boundary_card.icon_role,
            "current-run-boundary",
        )
        self.assertEqual(self.window.run_plan_card.icon_role, "current-run-plan")
        self.assertEqual(self.window.accept_plan_button.icon_role, "plan-accept")
        self.assertEqual(
            self.window.start_benchmark_button.icon_role,
            "benchmark-start",
        )

        self.window.set_current_run_projection(None)
        QApplication.processEvents()

        self.assertEqual(
            self.window.current_run_empty_state_card.title,
            CURRENT_RUN_EMPTY_TITLE,
        )
        self.assertEqual(
            self.window.current_run_empty_state_label.text(),
            CURRENT_RUN_EMPTY_MESSAGE,
        )
        self.assertIsNone(self.window.current_run_identity_label)
        self.assertIsNone(self.window.current_run_status)

    def test_current_run_reference_geometry_is_bounded_and_stable_across_replacement(
        self,
    ) -> None:
        self.window.resize(REFERENCE_WINDOW_WIDTH, REFERENCE_WINDOW_HEIGHT)
        self.window.show()
        QApplication.processEvents()

        empty_card = self.window.current_run_empty_state_card
        expected_empty_minimum = (
            DEFAULT_LAYOUT_METRICS.metric("control-height")
            + (2 * DEFAULT_LAYOUT_METRICS.metric("panel-padding"))
            + DEFAULT_LAYOUT_METRICS.metric("section-gap")
        )
        self.assertGreaterEqual(empty_card.minimumHeight(), expected_empty_minimum)
        self.assertEqual(
            empty_card.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Expanding,
        )
        self.assertIsNone(self.window.current_run_identity_label)
        self.assertIsNone(self.window.current_run_status)

        self.window.workspace_tabs.setCurrentIndex(3)
        QApplication.processEvents()

        long_boundary_fingerprint = "sha256:" + ("a" * 160)
        long_outputs = "artifact://" + ("output-segment/" * 30)
        projection = CurrentRunProjection(
            run_identity="Run geometry",
            state_label="Prepared",
            state_tone="neutral",
            timestamp="2026-09-25 10:34",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="Authority Resolution",
                runner="Codex CLI",
                model="gpt-5.6",
                cases="24",
                boundary_fingerprint=long_boundary_fingerprint,
            ),
            run_plan=RunPlanProjection(
                treatments="Baseline, treatment-a",
                cases="24 cases",
                execution="2 repetitions",
                evaluation="Exact + semantic",
                outputs=long_outputs,
            ),
        )
        self.window.set_current_run_projection(projection)
        QApplication.processEvents()

        self.assertEqual(self.window.workspace_tabs.currentIndex(), 3)
        self.assertEqual(
            self.window.execution_boundary_card.accessibleName(),
            "Execution Boundary",
        )
        self.assertEqual(self.window.run_plan_card.accessibleName(), "Run Plan")
        self.assertGreater(
            self.window.run_plan_card.width(),
            self.window.execution_boundary_card.width(),
        )
        self.assertLess(
            self.window.accept_plan_button.geometry().left(),
            self.window.start_benchmark_button.geometry().left(),
        )
        self.assertNotIn(
            long_boundary_fingerprint,
            [value.text() for _, value in self.window.execution_boundary_rows],
        )
        self.assertEqual(long_outputs, projection.run_plan.outputs)
        self.assertNotIn(long_outputs, projection.run_plan.ordered_values)
        for _label, value in (
            *self.window.execution_boundary_rows,
            *self.window.run_plan_rows,
        ):
            self.assertTrue(value.wordWrap())
            self.assertEqual(
                value.sizePolicy().horizontalPolicy(),
                QSizePolicy.Policy.Ignored,
            )

        self.window.set_current_run_projection(None)
        QApplication.processEvents()
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 3)

    def test_workspace_fits_viewport_and_tab_content_scrolls_below_floor(self) -> None:
        self.window.show()
        for width, height in ((1440, 1320), (1440, 1080), (820, 620), (1440, 1320)):
            self.window.resize(width, height)
            QApplication.processEvents()
            scroll = self.window.workspace_scroll
            self.assertEqual(self.window.workspace.size(), scroll.viewport().size())
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
            for index, label in enumerate(WORKSPACE_TAB_LABELS):
                self.window.workspace_tabs.setCurrentIndex(index)
                QApplication.processEvents()
                local = self.window.workspace_tabs.widget(index)
                page = self.window.workspace_pages[label]
                self.assertIs(local.widget(), page)
                self.assertGreaterEqual(page.width(), MINIMUM_TAB_CONTENT_WIDTH)
                self.assertGreaterEqual(page.height(), MINIMUM_TAB_CONTENT_HEIGHT)
                self.assertEqual(local.horizontalScrollBar().maximum() > 0,
                                 local.viewport().width() < page.width())
                self.assertEqual(local.verticalScrollBar().maximum() > 0,
                                 local.viewport().height() < page.height())
                self.assertLessEqual(self.window.workspace_tabs.geometry().bottom(),
                                     self.window.workspace.height())

    def test_local_overflow_survives_projection_replacement_and_console_resize(self) -> None:
        self.window.show()
        self.window.resize(820, 620)
        self.window.workspace_tabs.setCurrentIndex(3)
        pages = [QLabel(label) for label in WORKSPACE_TAB_LABELS]
        pages[1].setMinimumSize(900, 500)
        projection = WorkspaceProjection(
            progress=pages[0], scoring=pages[1], results=pages[2],
            evidence=pages[3], verification=pages[4], reports=pages[5],
        )
        for _ in range(2):
            self.window.set_workspace_projection(projection, run_id="sizing-test")
            self.assertEqual(self.window.sidebar.width(), REFERENCE_SIDEBAR_WIDTH)
            self.window.set_console_height(320)
            QApplication.processEvents()
            self.assertEqual(self.window.workspace_tabs.currentIndex(), 3)
            self.assertEqual(self.window.workspace.size(),
                             self.window.workspace_scroll.viewport().size())
            for index, page in enumerate(pages):
                local = self.window.workspace_tabs.widget(index)
                self.assertIs(local.widget(), page)
                self.assertGreaterEqual(page.minimumWidth(), MINIMUM_TAB_CONTENT_WIDTH)
                self.assertGreaterEqual(page.minimumHeight(), MINIMUM_TAB_CONTENT_HEIGHT)
            self.assertEqual(pages[1].minimumWidth(), 900)
            self.assertEqual(pages[1].minimumHeight(), 500)
            self.window.clear_workspace_projection()
            QApplication.processEvents()
            self.assertTrue(all(page.parent() is None for page in pages))
            self.assertEqual(self.window.workspace_tabs.currentIndex(), 3)

    def test_sidebar_omits_inapplicable_model_and_credentials_controls(self) -> None:
        runner = "arcgrav.fixture.runner-no-model@1.0.0"
        projection = SidebarProjection(
            runner_options=(runner,),
            selected_runner=runner,
            model_visible=False,
            credentials_visible=False,
            additional_controls=(
                SidebarChoiceControlProjection(
                    control_name="diagnostic_mode",
                    label="Diagnostic Mode",
                    options=("completed", "failed"),
                    selected_value="completed",
                    required=True,
                ),
            ),
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            console_preferences={},
            sidebar_projection=projection,
        )
        self.addCleanup(window.deleteLater)

        self.assertNotIn("Model", window.configuration_row_labels)
        self.assertNotIn("Credentials", window.configuration_row_labels)
        self.assertTrue(window.model_input.isHidden())
        self.assertTrue(window.credential_input.isHidden())
        self.assertNotIn(window._model_focus_target, window._keyboard_focus_order)
        self.assertNotIn(
            window.credential_input.line_edit,
            window._keyboard_focus_order,
        )
        self.assertIn("diagnostic_mode", window.additional_control_inputs)

        snapshot = window.sidebar_input_snapshot()
        self.assertIsNone(snapshot.model)
        self.assertEqual(snapshot.credential, "")

    def test_sidebar_preserves_workflow_order_and_routes_only_caller_owned_intent(
        self,
    ) -> None:
        build_plan_snapshots: list[SidebarInputSnapshot] = []
        selected_runs: list[str] = []
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution", "Custom Benchmark"),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI", "Mock Model"),
            selected_runner="Codex CLI",
            model_options=("gpt-5.6", "gpt-5.6-mini"),
            selected_model="gpt-5.6",
            credential_value="transient-secret",
            temperature=NumericInputProjection(
                0.2,
                minimum=0.0,
                maximum=2.0,
                step=0.1,
                decimals=1,
            ),
            max_tokens=NumericInputProjection(
                4096,
                minimum=1,
                maximum=32768,
                step=1,
                decimals=0,
            ),
            build_plan_available=True,
            runs=(
                RetainedRunProjection(
                    run_id="run-a",
                    display_identity="Run A",
                    state_label="Accepted",
                    state_tone="success",
                    timestamp="2026-09-21 14:00",
                    selected=True,
                ),
                RetainedRunProjection(
                    run_id="run-b",
                    display_identity="Run B",
                    state_label="Blocked",
                    state_tone="neutral",
                    timestamp="2026-09-21 14:10",
                ),
            ),
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            console_preferences={},
            sidebar_projection=projection,
            on_build_plan=build_plan_snapshots.append,
            on_run_selected=selected_runs.append,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        self.assertEqual(
            SIDEBAR_SECTION_ORDER,
            ("Build Plan", "Benchmark", "Runner", "Configuration", "Runs"),
        )
        layout = window.sidebar_layout
        self.assertIs(window.sidebar.layout().itemAt(0).widget(), window.sidebar_header)
        self.assertIs(window.sidebar.layout().itemAt(1).widget(), window.sidebar_scroll)
        self.assertIs(window.build_plan_button.parentWidget(), window.sidebar_header)
        top_level_widgets = [
            window.benchmark_card,
            window.runner_card,
            window.runs_card,
        ]
        indices = [layout.indexOf(widget) for widget in top_level_widgets]
        self.assertEqual(indices, sorted(indices))

        self.assertEqual(window.benchmark_card.title, "Benchmark")
        self.assertEqual(window.runner_card.title, "Runner")
        self.assertEqual(window.runs_card.title, "Runs")
        self.assertEqual(window.benchmark_card.title_role, "section-heading")
        self.assertEqual(window.runner_card.title_role, "section-heading")
        self.assertEqual(window.runs_card.title_role, "section-heading")
        self.assertTrue(window.benchmark_card.isAncestorOf(window.benchmark_input))
        self.assertTrue(window.runner_card.isAncestorOf(window.runner_input))
        self.assertTrue(window.runner_card.isAncestorOf(window.configuration_heading))
        self.assertTrue(window.runner_card.isAncestorOf(window.configuration_scroll))
        self.assertTrue(window.runs_card.isAncestorOf(window.run_rows["run-a"]))
        self.assertTrue(window.runs_card.isAncestorOf(window.run_rows["run-b"]))
        self.assertFalse(window.benchmark_input.label_visible)
        self.assertFalse(window.runner_input.label_visible)

        self.assertEqual(window.benchmark_input.label, "Benchmark")
        self.assertEqual(window.runner_input.label, "Runner")
        self.assertEqual(window.configuration_heading.text(), "Configuration")
        self.assertEqual(window.model_input.label, "Model")
        self.assertEqual(window.credential_input.label, "Credentials")
        self.assertTrue(window.credential_input.obscured)
        self.assertEqual(window.temperature_input.label, "Temperature")
        self.assertEqual(window.max_tokens_input.label, "Max Tokens")
        self.assertEqual(window.build_plan_button.displayed_label, "Build Plan")
        self.assertEqual(window.build_plan_button.role, "primary")
        self.assertEqual(window.build_plan_button.icon_role, "plan-build")
        self.assertEqual(
            window.build_plan_button.property("semanticIconRole"),
            "plan-build",
        )
        self.assertFalse(window.build_plan_button.icon().isNull())

        run_a = window.run_rows["run-a"]
        run_a_layout = run_a.layout()
        self.assertEqual(
            run_a_layout.getContentsMargins(),
            (
                DEFAULT_LAYOUT_METRICS.metric("compact-panel-padding-x"),
                DEFAULT_LAYOUT_METRICS.metric("compact-panel-padding-y"),
                DEFAULT_LAYOUT_METRICS.metric("compact-panel-padding-x"),
                DEFAULT_LAYOUT_METRICS.metric("compact-panel-padding-y"),
            ),
        )
        self.assertEqual(
            run_a_layout.spacing(),
            DEFAULT_LAYOUT_METRICS.metric("compact-panel-gap"),
        )
        self.assertTrue(run_a.selected)
        self.assertIsInstance(run_a.identity_label, QLabel)
        self.assertEqual(run_a.identity_label.text(), "Run A")
        self.assertEqual(run_a.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        self.assertEqual(run_a.status_badge.label, "Accepted")
        self.assertEqual(run_a.timestamp_label.text(), "2026-09-21 14:00")

        run_b = window.run_rows["run-b"]

        self.assertTrue(
            run_b.identity_label.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
        )
        self.assertTrue(
            run_b.timestamp_label.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
        )
        self.assertTrue(
            run_b.status_badge.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
        )

        window.show()
        QApplication.processEvents()
        window.console_widget.bind_generation("generation-a")
        QTest.mouseClick(
            run_b,
            Qt.MouseButton.LeftButton,
            pos=run_b.timestamp_label.geometry().center(),
        )
        QApplication.processEvents()
        self.assertEqual(selected_runs, ["run-b"])
        self.assertEqual(window.selected_run_id, "run-b")
        self.assertFalse(window.run_rows["run-a"].selected)
        self.assertTrue(window.run_rows["run-b"].selected)
        self.assertEqual(
            window.console_widget.state.active_generation_id,
            "generation-a",
        )

        QTest.mouseClick(
            run_a,
            Qt.MouseButton.LeftButton,
            pos=run_a.status_badge.geometry().center(),
        )
        QApplication.processEvents()
        self.assertEqual(selected_runs, ["run-b", "run-a"])
        self.assertEqual(window.selected_run_id, "run-a")
        self.assertTrue(window.run_rows["run-a"].selected)
        self.assertFalse(window.run_rows["run-b"].selected)

        run_b.setFocus()
        QTest.keyClick(run_b, Qt.Key.Key_Space)
        QApplication.processEvents()
        self.assertEqual(selected_runs, ["run-b", "run-a", "run-b"])
        self.assertEqual(window.selected_run_id, "run-b")
        self.assertFalse(window.run_rows["run-a"].selected)
        self.assertTrue(window.run_rows["run-b"].selected)

        window.benchmark_input.set_value("Custom Benchmark")
        window.runner_input.set_value("Mock Model")
        window.model_input.set_value("gpt-5.6-mini")
        window.credential_input.set_value("next-transient-secret")
        window.temperature_input.set_value(0.4)
        window.max_tokens_input.set_value(8192)
        window.build_plan_button.click()
        QApplication.processEvents()

        self.assertEqual(
            build_plan_snapshots,
            [
                SidebarInputSnapshot(
                    benchmark="Custom Benchmark",
                    runner="Mock Model",
                    model="gpt-5.6-mini",
                    credential="next-transient-secret",
                    temperature=0.4,
                    max_tokens=8192.0,
                )
            ],
        )
        self.assertEqual(window.authority_semantics, "presentation-only")

    def test_discovered_model_labels_submit_exact_model_and_selection_mode(
        self,
    ) -> None:
        snapshots: list[SidebarInputSnapshot] = []
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            model_choices=(
                SidebarModelChoiceProjection(
                    label="Default (GPT-5.6)",
                    model_value="gpt-5.6",
                    selection_mode="cli-default",
                    selection_mode_control_name="model_selection_mode",
                ),
                SidebarModelChoiceProjection(
                    label="GPT-5.6",
                    model_value="gpt-5.6",
                    selection_mode="explicit",
                    selection_mode_control_name="model_selection_mode",
                ),
            ),
            selected_model="gpt-5.6",
            selected_model_selection_mode="cli-default",
            build_plan_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection,
            on_build_plan=snapshots.append,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        self.assertEqual(
            ("Default (GPT-5.6)", "GPT-5.6"),
            window.model_input.options,
        )
        self.assertEqual("Default (GPT-5.6)", window.model_input.value)
        self.assertEqual({}, window.additional_control_inputs)
        default_snapshot = window.sidebar_input_snapshot()
        self.assertEqual("gpt-5.6", default_snapshot.model)
        self.assertEqual(
            (
                SidebarControlInputSnapshot(
                    "model_selection_mode",
                    "cli-default",
                ),
            ),
            default_snapshot.additional_controls,
        )

        window.model_input.set_value("GPT-5.6")
        window.build_plan_button.click()
        QApplication.processEvents()

        self.assertEqual(1, len(snapshots))
        self.assertEqual("gpt-5.6", snapshots[0].model)
        self.assertEqual(
            (
                SidebarControlInputSnapshot(
                    "model_selection_mode",
                    "explicit",
                ),
            ),
            snapshots[0].additional_controls,
        )

    def test_discovery_context_controls_emit_current_sidebar_intent(
        self,
    ) -> None:
        snapshots: list[SidebarInputSnapshot] = []
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            model_choices=(
                SidebarModelChoiceProjection(
                    label="Default (GPT-5.6)",
                    model_value="gpt-5.6",
                    selection_mode="cli-default",
                    selection_mode_control_name="model_selection_mode",
                ),
            ),
            selected_model="gpt-5.6",
            selected_model_selection_mode="cli-default",
            model_discovery_determining_controls=(
                "codex_binary",
                "credential_source",
            ),
            model_discovery_context_fingerprints=(
                "authentication_context=sha256:" + ("a" * 64),
                "configuration_context=sha256:" + ("b" * 64),
            ),
            additional_controls=(
                SidebarTextControlProjection(
                    control_name="codex_binary",
                    label="Codex Binary",
                    value="codex",
                    required=True,
                ),
                SidebarChoiceControlProjection(
                    control_name="credential_source",
                    label="Credential Source",
                    options=(
                        "environment",
                        "os_credential_lookup",
                    ),
                    selected_value="environment",
                    required=True,
                ),
            ),
            build_plan_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection,
            on_sidebar_intent_changed=snapshots.append,
            on_build_plan=lambda _snapshot: None,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        credential_source = window.additional_control_inputs[
            "credential_source"
        ]
        credential_source.set_value("os_credential_lookup")
        QApplication.processEvents()
        self.assertTrue(snapshots)
        self.assertEqual(
            projection.model_discovery_context_fingerprints,
            snapshots[-1].model_discovery_context_fingerprints,
        )
        self.assertIn(
            SidebarControlInputSnapshot(
                "credential_source",
                "os_credential_lookup",
            ),
            snapshots[-1].additional_controls,
        )

        codex_binary = window.additional_control_inputs["codex_binary"]
        codex_binary.set_value("codex-preview")
        codex_binary.line_edit.editingFinished.emit()
        QApplication.processEvents()
        self.assertIn(
            SidebarControlInputSnapshot(
                "codex_binary",
                "codex-preview",
            ),
            snapshots[-1].additional_controls,
        )

    def test_sidebar_projection_refresh_preserves_focused_runner_control(
        self,
    ) -> None:
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            additional_controls=(
                SidebarTextControlProjection(
                    control_name="codex_binary",
                    label="Codex Binary",
                    value="codex",
                    required=True,
                ),
                SidebarChoiceControlProjection(
                    control_name="credential_source",
                    label="Credential Source",
                    options=("environment", "codex_session"),
                    selected_value="environment",
                    required=True,
                ),
            ),
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection,
        )
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()

        codex_binary = window.additional_control_inputs["codex_binary"]
        codex_binary.line_edit.setFocus()
        QApplication.processEvents()
        self.assertTrue(codex_binary.line_edit.hasFocus())

        window.set_sidebar_projection(projection)
        QApplication.processEvents()

        refreshed = window.additional_control_inputs["codex_binary"]
        self.assertTrue(refreshed.line_edit.hasFocus())

        credential_source = window.additional_control_inputs["credential_source"]
        credential_source.combo_box.setFocus()
        QApplication.processEvents()
        self.assertTrue(credential_source.combo_box.hasFocus())

        window.set_sidebar_projection(projection)
        QApplication.processEvents()

        refreshed_credential_source = window.additional_control_inputs[
            "credential_source"
        ]
        self.assertTrue(refreshed_credential_source.combo_box.hasFocus())

    def test_consecutive_sidebar_refreshes_never_create_top_level_windows(self) -> None:
        window = self.window
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
        )
        window.set_sidebar_projection(projection)
        window.show()
        window.activateWindow()
        QApplication.processEvents()
        window.benchmark_input.combo_box.setFocus()
        QApplication.processEvents()
        self.assertTrue(window.benchmark_input.combo_box.hasFocus())

        retired_sidebars = []
        for _ in range(3):
            retired_sidebars.append(window.sidebar)
            window.set_sidebar_projection(projection)
            self.assertTrue(window.sidebar.isVisible())
            self.assertIs(retired_sidebars[-1].parentWidget(), window.upper_work_area)
            self.assertTrue(retired_sidebars[-1].isHidden())

        for _ in range(5):
            QApplication.processEvents()
        self.assertIs(QApplication.activeWindow(), window)
        self.assertTrue(window.benchmark_input.combo_box.hasFocus())
        self.assertFalse(any(sidebar in QApplication.topLevelWidgets()
                             for sidebar in retired_sidebars))

    def test_unresolved_required_model_discovery_has_no_editable_fallback(
        self,
    ) -> None:
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            model_required=True,
            build_plan_available=True,
            prerequisite_diagnostics=(
                SidebarPrerequisiteDiagnosticProjection(
                    diagnostic_name="runner-model-discovery",
                    message="Authoritative model discovery is unresolved.",
                    remediation="Restore discovery prerequisites.",
                ),
            ),
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        self.assertEqual((), window.model_input.options)
        self.assertFalse(window.model_input.combo_box.isEditable())
        self.assertFalse(window.model_input.combo_box.isEnabled())
        self.assertFalse(window.build_plan_button.isEnabled())

    def test_reference_configuration_label_placement_and_local_overflow_are_presentation_only(
        self,
    ) -> None:
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI", "Mock Model"),
            selected_runner="Codex CLI",
            model_options=("gpt-5.6",),
            selected_model="gpt-5.6",
            credential_value="transient-secret",
            temperature=NumericInputProjection(
                0.2,
                minimum=0.0,
                maximum=2.0,
                step=0.1,
                decimals=1,
            ),
            max_tokens=NumericInputProjection(
                4096,
                minimum=1,
                maximum=32768,
                step=1,
                decimals=0,
            ),
            additional_controls=(
                SidebarTextControlProjection(
                    control_name="workspace",
                    label="Workspace",
                    value="",
                    required=True,
                ),
                SidebarChoiceControlProjection(
                    control_name="launch_mode",
                    label="Launch Mode",
                    options=("native", "wsl"),
                    selected_value="native",
                    required=True,
                ),
                SidebarNumericControlProjection(
                    control_name="timeout_seconds",
                    label="Timeout",
                    numeric=NumericInputProjection(
                        120,
                        minimum=1,
                        maximum=600,
                        step=1,
                        decimals=0,
                    ),
                ),
            ),
            build_plan_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection,
            on_build_plan=lambda _snapshot: None,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)
        window.resize(REFERENCE_WINDOW_WIDTH, REFERENCE_WINDOW_HEIGHT)
        window.show()
        QApplication.processEvents()

        self.assertFalse(window.model_input.label_visible)
        self.assertFalse(window.credential_input.label_visible)
        self.assertFalse(window.temperature_input.label_visible)
        self.assertFalse(window.max_tokens_input.label_visible)
        self.assertEqual(
            set(window.configuration_row_labels),
            {"Model", "Credentials", "Temperature", "Max Tokens"},
        )
        for label, input_widget in (
            ("Model", window.model_input),
            ("Credentials", window.credential_input),
        ):
            label_widget = window.configuration_row_labels[label]
            self.assertEqual(label_widget.parentWidget(), input_widget.parentWidget())
            self.assertEqual(
                label_widget.geometry().left(),
                input_widget.geometry().left(),
            )
            self.assertLess(
                label_widget.geometry().bottom(),
                input_widget.geometry().top(),
            )

        numeric_field_lefts = {
            window.temperature_input.geometry().left(),
            window.max_tokens_input.geometry().left(),
        }
        self.assertEqual(len(numeric_field_lefts), 1)
        self.assertLessEqual(
            window.credential_input.reveal_button.geometry().right(),
            window.credential_input.width(),
        )
        self.assertLessEqual(
            window.temperature_input.spin_box.geometry().right(),
            window.temperature_input.width(),
        )
        self.assertLessEqual(
            window.max_tokens_input.spin_box.geometry().right(),
            window.max_tokens_input.width(),
        )
        self.assertEqual(
            window.sidebar_scroll.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(
            window.configuration_scroll.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(
            window.configuration_scroll.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertEqual(
            window.configuration_scroll.maximumHeight(),
            REFERENCE_CONFIGURATION_VIEWPORT_HEIGHT,
        )
        self.assertGreater(
            window.configuration_scroll.verticalScrollBar().maximum(),
            0,
        )

        workspace_control = window.additional_control_inputs["workspace"]
        launch_mode_control = window.additional_control_inputs["launch_mode"]
        timeout_control = window.additional_control_inputs["timeout_seconds"]
        for control in (
            workspace_control,
            launch_mode_control,
            timeout_control,
        ):
            self.assertTrue(window.configuration_content.isAncestorOf(control))
            self.assertTrue(control.isVisible())

        snapshot_before = window.sidebar_input_snapshot()
        scroll_bar = window.configuration_scroll.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())
        preserved_position = scroll_bar.value()
        self.assertGreater(preserved_position, 0)

        window.set_sidebar_projection(projection)
        QApplication.processEvents()
        self.assertEqual(
            window.configuration_scroll.verticalScrollBar().value(),
            preserved_position,
        )
        self.assertEqual(window.sidebar_input_snapshot(), snapshot_before)

        self.assertEqual(window.build_plan_button.role, "unavailable")
        workspace_control = window.additional_control_inputs["workspace"]
        workspace_control.set_value("project-a")
        QApplication.processEvents()
        self.assertEqual(window.build_plan_button.role, "primary")
        self.assertEqual(window.sidebar_layout.indexOf(window.build_plan_button), -1)
        self.assertIs(window.build_plan_button.parentWidget(), window.sidebar_header)
        self.assertEqual(
            window.sidebar_input_snapshot().additional_controls,
            (
                SidebarControlInputSnapshot(
                    control_name="workspace",
                    value="project-a",
                    secret=False,
                ),
                SidebarControlInputSnapshot(
                    control_name="launch_mode",
                    value="native",
                    secret=False,
                ),
                SidebarControlInputSnapshot(
                    control_name="timeout_seconds",
                    value=120.0,
                    secret=False,
                ),
            ),
        )

        window.configuration_scroll.verticalScrollBar().setValue(
            window.configuration_scroll.verticalScrollBar().maximum()
        )
        window.build_plan_button.setFocus()
        changed_projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI", "Mock Model"),
            selected_runner="Mock Model",
            model_options=("gpt-5.6",),
            selected_model="gpt-5.6",
            credential_value="transient-secret",
            temperature=projection.temperature,
            max_tokens=projection.max_tokens,
            additional_controls=projection.additional_controls,
            build_plan_available=True,
        )
        window.set_sidebar_projection(changed_projection)
        QApplication.processEvents()
        self.assertEqual(
            window.configuration_scroll.verticalScrollBar().value(),
            0,
        )

    def test_build_plan_header_stays_visible_while_sidebar_scrolls_and_resizes(self) -> None:
        from PySide6.QtCore import QPoint

        window = self.window
        window.show()
        for width, height in ((1440, 900), (900, 600), (640, 480)):
            with self.subTest(width=width, height=height):
                window.resize(width, height)
                window.vertical_splitter.setSizes([height // 2, height // 2])
                QApplication.processEvents()
                scrollbar = window.sidebar_scroll.verticalScrollBar()
                self.assertGreater(scrollbar.maximum(), 0)
                button = window.build_plan_button
                scrollbar.setValue(0)
                QApplication.processEvents()
                position = button.mapTo(window, QPoint())
                benchmark_top = window.benchmark_card.mapTo(
                    window.sidebar_scroll.viewport(), QPoint()
                ).y()
                self.assertEqual(benchmark_top, DEFAULT_LAYOUT_METRICS.metric("page-padding"))
                benchmark_heading = window.benchmark_input.mapTo(window, QPoint())
                self.assertGreater(benchmark_heading.y(), window.sidebar_header.geometry().bottom())
                for value in (scrollbar.maximum() // 2, scrollbar.maximum(), 0):
                    scrollbar.setValue(value)
                    QApplication.processEvents()
                    self.assertEqual(button.mapTo(window, QPoint()), position)
                    self.assertTrue(button.isVisible())
                    self.assertTrue(window.sidebar_header.rect().contains(button.geometry()))
                    self.assertLess(window.sidebar_header.geometry().bottom(),
                                    window.sidebar_scroll.mapTo(window, QPoint()).y())
                    self.assertGreaterEqual(button.height(), button.minimumHeight())
                scrollbar.setValue(scrollbar.maximum())
                QApplication.processEvents()
                runs_bottom = window.runs_card.mapTo(
                    window.sidebar_scroll.viewport(), window.runs_card.rect().bottomLeft()
                ).y()
                self.assertLess(runs_bottom, window.sidebar_scroll.viewport().height())

    def test_workspace_tab_strip_stays_within_tabs_when_resized(self) -> None:
        window = self.window
        window.show()
        for width, height in ((1440, 900), (900, 600), (640, 480)):
            with self.subTest(width=width, height=height):
                window.resize(width, height)
                window.set_sidebar_projection(SidebarProjection())
                QApplication.processEvents()
                tabs = window.workspace_tabs
                bar = tabs.tabBar()
                self.assertLessEqual(bar.geometry().right(), tabs.rect().right())

    def test_action_header_style_changes_preserve_geometry_and_identity(self) -> None:
        window = self.window
        window.show()
        QApplication.processEvents()
        header = window.sidebar_header
        style = header.styleSheet()
        styled_geometry = (header.geometry(), window.connectivity_status.geometry(),
                           window.build_plan_button.geometry())
        button_styles = (window.build_plan_button.styleSheet(),
                         window.connectivity_status.styleSheet())
        header.setStyleSheet("")
        QApplication.processEvents()
        self.assertEqual(styled_geometry,
                         (header.geometry(), window.connectivity_status.geometry(),
                          window.build_plan_button.geometry()))
        self.assertEqual(button_styles, (window.build_plan_button.styleSheet(),
                                        window.connectivity_status.styleSheet()))
        header.setStyleSheet(style)
        window.set_sidebar_projection(SidebarProjection())
        QApplication.processEvents()
        self.assertIs(window.sidebar_header, header)
        for _ in range(2):
            window.set_sidebar_projection(SidebarProjection())
            QApplication.processEvents()
            self.assertIs(window.sidebar_header, header)

    def test_long_runner_context_elides_without_hiding_status_or_resizing_sidebar(self) -> None:
        window = self.window
        runner_name = "Mock Model (Local Test with a very long descriptive runner name)"
        window.set_sidebar_projection(SidebarProjection(
            runner_options=(runner_name,), selected_runner=runner_name,
        ))
        window.show()
        for width in (1440, 640, 1180):
            window.resize(width, 700)
            for status in ("Checking runner…", "Testing runner…"):
                with self.subTest(width=width, status=status):
                    window.set_connectivity_status(status, "neutral")
                    QApplication.processEvents()
                    runner = window.connectivity_status
                    self.assertEqual(window.sidebar.width(), REFERENCE_SIDEBAR_WIDTH)
                    self.assertEqual(runner.size(), window.build_plan_button.size())
                    self.assertTrue(runner.displayed_label.endswith(status))
                    self.assertNotIn(runner_name, runner.displayed_label)
                    self.assertIn(runner_name, runner.accessibleName())
                    self.assertIn(status, runner.accessibleName())
                    self.assertLessEqual(runner.sizeHint().width(), runner.width())

    def test_stacked_runner_and_plan_header_survives_refresh_and_pending_work(self) -> None:
        from dataclasses import replace
        from PySide6.QtCore import QPoint

        window = self.window
        projection = SidebarProjection(
            runner_options=("Mock Model (Local Test)",),
            selected_runner="Mock Model (Local Test)",
            build_plan_available=True,
        )
        window._on_build_plan = lambda snapshot: None
        window.set_sidebar_projection(projection)
        window.show()
        runner = window.connectivity_status
        header = window.sidebar_header
        for width, height in ((1440, 900), (900, 600), (640, 480)):
            window.resize(width, height)
            for label in ("Connected", "Testing runner…", "Test failed", "Runner not selected"):
                window.set_sidebar_projection(replace(projection))
                window.set_connectivity_status(label, "neutral")
                QApplication.processEvents()
                plan = window.build_plan_button
                self.assertIs(window.sidebar_header, header)
                self.assertIs(window.connectivity_status, runner)
                self.assertIs(runner.parentWidget(), header)
                self.assertIs(plan.parentWidget(), header)
                self.assertIs(header.layout().itemAt(0).widget(), runner)
                self.assertIs(header.layout().itemAt(1).widget(), plan)
                self.assertEqual(runner.size(), plan.size())
                self.assertGreater(runner.width(), 0)
                self.assertLess(runner.geometry().bottom(), plan.geometry().top())
                self.assertLess(header.geometry().right(), window.shell_status_bar.mapTo(window, QPoint()).x())
                self.assertEqual(header.mapTo(window, QPoint()).y(), 0)
                status_bottom = window.shell_status_bar.mapTo(
                    window, window.shell_status_bar.rect().bottomLeft()).y()
                workspace_top = window.workspace_scroll.mapTo(window, QPoint()).y()
                self.assertEqual(workspace_top, status_bottom + 1)
                self.assertLess(workspace_top, header.height())
                self.assertEqual(window.workspace_column.mapTo(window, QPoint()).y(), 0)
                self.assertEqual(window.sidebar_scroll.y(), header.height())
                self.assertEqual(window.console_widget.width(), window.width())
                self.assertIs(runner.menu(), window.runner_menu)
                self.assertLess(window._keyboard_focus_order.index(runner),
                                window._keyboard_focus_order.index(plan))
        window._operation_locks_controls = True
        window._apply_operation_controls()
        self.assertFalse(window.build_plan_button.isEnabled())
        window.set_sidebar_projection(projection)
        QApplication.processEvents()
        self.assertFalse(window.build_plan_button.isEnabled())
        window._operation_locks_controls = False
        window._apply_operation_controls()
        self.assertTrue(window.build_plan_button.isEnabled())

    def test_build_plan_header_preserves_dispatch_and_refresh_availability(self) -> None:
        from dataclasses import replace

        snapshots = []
        projection = SidebarProjection(build_plan_available=True)
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection,
            on_build_plan=snapshots.append,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()
        window.sidebar_scroll.verticalScrollBar().setValue(
            window.sidebar_scroll.verticalScrollBar().maximum()
        )
        window.build_plan_button.setFocus()
        QTest.keyClick(window.build_plan_button, Qt.Key.Key_Space)
        self.assertEqual(len(snapshots), 1)
        preserved_scroll = window.sidebar_scroll.verticalScrollBar().value()
        window.set_sidebar_projection(projection)
        QApplication.processEvents()
        self.assertIs(window.focusWidget(), window.build_plan_button)
        self.assertEqual(window.sidebar_scroll.verticalScrollBar().value(), preserved_scroll)
        window.set_sidebar_projection(replace(projection, build_plan_available=False))
        QApplication.processEvents()
        self.assertFalse(window.build_plan_button.isEnabled())
        window.build_plan_button.click()
        self.assertEqual(len(snapshots), 1)
        window.set_sidebar_projection(projection)
        QApplication.processEvents()
        self.assertTrue(window.build_plan_button.isEnabled())
        self.assertIs(window.build_plan_button.parentWidget(), window.sidebar_header)
        QTest.mouseClick(window.build_plan_button, Qt.MouseButton.LeftButton)
        self.assertEqual(len(snapshots), 2)

    def test_compact_configuration_does_not_show_local_scrollbar(self) -> None:
        self.window.resize(REFERENCE_WINDOW_WIDTH, REFERENCE_WINDOW_HEIGHT)
        self.window.show()
        QApplication.processEvents()

        self.assertEqual(
            self.window.configuration_scroll.verticalScrollBar().maximum(),
            0,
        )
        self.assertFalse(
            self.window.configuration_scroll.verticalScrollBar().isVisible()
        )

    def test_execution_settings_preserve_values_and_refresh_with_plan(self) -> None:
        from dataclasses import replace

        details = (("Planned observations", "12"), ("Iterations", "3"),
                   ("Cache validation replays", "Enabled"))
        plan = RunPlanProjection("A", "4 cases", "12 planned observations",
                                 "Bound contracts", "Evidence", execution_details=details)
        projection = CurrentRunProjection(
            "Run A", "Planned", "neutral", "Now",
            ExecutionBoundaryProjection("Benchmark", "Runner", "Model", "Cases", "hash"),
            plan,
        )
        self.window.set_current_run_projection(projection)
        self.assertEqual(
            tuple((name.text(), value.text()) for name, value in self.window.execution_detail_rows),
            details,
        )
        revised = (("Planned observations", "4"), ("Iterations", "1"),
                   ("Cache validation replays", "Disabled by user"))
        self.window.set_current_run_projection(replace(
            projection, run_plan=replace(plan, execution="4 planned observations", execution_details=revised)
        ))
        self.assertEqual(
            tuple((name.text(), value.text()) for name, value in self.window.execution_detail_rows),
            revised,
        )
        self.window.set_current_run_projection(None)
        self.assertEqual(self.window.execution_detail_rows, ())

    def test_current_run_projects_exact_shared_state_and_routes_authorized_actions(
        self,
    ) -> None:
        accept_calls: list[str] = []
        start_calls: list[str] = []
        projection = CurrentRunProjection(
            run_identity="Run A",
            state_label="Planned",
            state_tone="neutral",
            timestamp="2026-09-21 14:30",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="Authority Resolution",
                runner="Codex CLI",
                model="gpt-5.6",
                cases="24",
                boundary_fingerprint="sha256:caller-owned-boundary",
            ),
            run_plan=RunPlanProjection(
                treatments="Baseline, treatment-a",
                cases="24 cases",
                execution="2 repetitions",
                evaluation="Exact + semantic",
                outputs="Accepted evidence + report",
            ),
            accept_plan_available=True,
            start_benchmark_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            current_run_projection=projection,
            on_accept_plan=lambda: accept_calls.append("accept"),
            on_start_benchmark=lambda: start_calls.append("start"),
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        self.assertEqual(window.current_run_heading.text(), "Current Run")
        self.assertEqual(
            window.current_run_region.property("authoritySemantics"),
            "presentation-only",
        )
        self.assertEqual(window.current_run_identity_label.text(), "Run A")
        self.assertEqual(window.current_run_status.label, "Planned")
        self.assertEqual(window.current_run_timestamp_label.text(), "2026-09-21 14:30")

        self.assertEqual(window.execution_boundary_card.title, "Execution Boundary")
        self.assertEqual(
            window.execution_boundary_card.icon_role,
            "current-run-boundary",
        )
        self.assertFalse(
            window.execution_boundary_card.title_icon_label.pixmap().isNull()
        )
        self.assertEqual(window.run_plan_card.title, "Run Plan")
        self.assertEqual(window.run_plan_card.icon_role, "current-run-plan")
        self.assertFalse(window.run_plan_card.title_icon_label.pixmap().isNull())
        self.assertEqual(
            [label.text() for label, _value in window.execution_boundary_rows],
            list(CURRENT_RUN_BOUNDARY_LABELS),
        )
        self.assertEqual(
            [value.text() for _label, value in window.execution_boundary_rows],
            [
                "Authority Resolution",
                "Codex CLI",
                "gpt-5.6",
            ],
        )
        self.assertEqual(
            [label.text() for label, _value in window.run_plan_rows],
            [
                f"{index}. {label}"
                for index, label in enumerate(CURRENT_RUN_PLAN_LABELS, start=1)
            ],
        )
        self.assertEqual(
            [value.text() for _label, value in window.run_plan_rows],
            [
                "Baseline, treatment-a",
                "24 cases",
                "2 repetitions",
                "Exact + semantic",
            ],
        )
        self.assertEqual(window.accept_plan_button.displayed_label, "Accept Plan")
        self.assertEqual(window.accept_plan_button.role, "secondary")
        self.assertEqual(window.accept_plan_button.icon_role, "plan-accept")
        self.assertFalse(window.accept_plan_button.icon().isNull())
        self.assertEqual(
            window.start_benchmark_button.displayed_label,
            "Start Benchmark",
        )
        self.assertEqual(window.start_benchmark_button.role, "primary")
        self.assertEqual(
            window.start_benchmark_button.icon_role,
            "benchmark-start",
        )
        self.assertFalse(window.start_benchmark_button.icon().isNull())

        window.accept_plan_button.click()
        window.start_benchmark_button.click()
        QApplication.processEvents()
        self.assertEqual(accept_calls, ["accept"])
        self.assertEqual(start_calls, ["start"])

        unavailable = CurrentRunProjection(
            run_identity="Run B",
            state_label="Draft",
            state_tone="neutral",
            timestamp="2026-09-21 14:31",
            execution_boundary=projection.execution_boundary,
            run_plan=projection.run_plan,
        )
        unavailable_window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            current_run_projection=unavailable,
        )
        self.addCleanup(unavailable_window.deleteLater)
        self.assertEqual(unavailable_window.accept_plan_button.role, "unavailable")
        self.assertFalse(unavailable_window.accept_plan_button.isEnabled())
        self.assertEqual(
            unavailable_window.start_benchmark_button.role,
            "unavailable",
        )
        self.assertFalse(unavailable_window.start_benchmark_button.isEnabled())

    def test_prior_run_hides_lifecycle_actions_and_routes_confirmed_deletion(self) -> None:
        delete_calls: list[str] = []
        projection = CurrentRunProjection(
            run_identity="generation-prior",
            state_label="Completed",
            state_tone="success",
            timestamp="2026-09-21 15:00",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="Authority Resolution",
                runner="Codex CLI",
                model="gpt-5.6",
                cases="24",
                boundary_fingerprint="sha256:prior-boundary",
            ),
            run_plan=RunPlanProjection(
                treatments="Baseline, treatment-a",
                cases="24 cases",
                execution="2 repetitions",
                evaluation="Exact + semantic",
                outputs="Accepted evidence + report",
            ),
            heading="Prior Run",
            is_prior_run=True,
            delete_run_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            current_run_projection=projection,
            on_delete_run=lambda run_id: delete_calls.append(run_id),
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        self.assertEqual("Prior Run", window.current_run_heading.text())
        self.assertIsNone(window.accept_plan_button)
        self.assertIsNone(window.start_benchmark_button)
        self.assertIsNotNone(window.delete_run_button)
        self.assertEqual("Delete Run", window.delete_run_button.displayed_label)
        self.assertEqual("destructive", window.delete_run_button.role)
        self.assertEqual("run-delete", window.delete_run_button.icon_role)
        self.assertFalse(window.delete_run_button.icon().isNull())
        self.assertIn(window.delete_run_button, window._keyboard_focus_order)

        window._confirm_delete_run = lambda _run_id: False
        window.delete_run_button.click()
        QApplication.processEvents()
        self.assertEqual([], delete_calls)

        window._confirm_delete_run = lambda _run_id: True
        window.delete_run_button.click()
        QApplication.processEvents()
        self.assertEqual(["generation-prior"], delete_calls)

    def test_delete_confirmation_accepts_equivalent_qt_button_wrapper(self) -> None:
        class _Button:
            def __init__(self, label: str) -> None:
                self.label = label

            def __eq__(self, other: object) -> bool:
                return isinstance(other, _Button) and self.label == other.label

        class _Icon:
            Warning = object()

        class _ButtonRole:
            RejectRole = object()
            DestructiveRole = object()

        class _MessageBox:
            Icon = _Icon
            ButtonRole = _ButtonRole

            def __init__(self, _parent) -> None:
                self._delete_button: _Button | None = None

            def setIcon(self, _icon) -> None:
                pass

            def setWindowTitle(self, _title: str) -> None:
                pass

            def setText(self, _text: str) -> None:
                pass

            def setInformativeText(self, _text: str) -> None:
                pass

            def addButton(self, label: str, role) -> _Button:
                button = _Button(label)
                if role is self.ButtonRole.DestructiveRole:
                    self._delete_button = button
                return button

            def setDefaultButton(self, _button: _Button) -> None:
                pass

            def exec(self) -> None:
                pass

            def clickedButton(self) -> _Button:
                assert self._delete_button is not None
                return _Button(self._delete_button.label)

        with patch("AgMark.gui.shell.window.QMessageBox", _MessageBox):
            self.assertTrue(self.window._confirm_delete_run("generation-prior"))

    def test_current_run_terminal_projection_updates_exact_shared_state(self) -> None:
        boundary = ExecutionBoundaryProjection(
            benchmark="Authority Resolution",
            runner="Codex CLI",
            model="gpt-5.6",
            cases="24",
            boundary_fingerprint="sha256:caller-owned-boundary",
        )
        plan = RunPlanProjection(
            treatments="Baseline, treatment-a",
            cases="24 cases",
            execution="2 repetitions",
            evaluation="Exact + semantic",
            outputs="Accepted evidence + report",
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            current_run_projection=CurrentRunProjection(
                run_identity="Run A",
                state_label="InProgress",
                state_tone="neutral",
                timestamp="2026-09-21 14:30",
                execution_boundary=boundary,
                run_plan=plan,
            ),
        )
        self.addCleanup(window.deleteLater)
        window.console_widget.bind_generation("generation-active")

        window.set_current_run_projection(
            CurrentRunProjection(
                run_identity="Run A",
                state_label="AcceptedRun",
                state_tone="success",
                timestamp="2026-09-21 14:31",
                execution_boundary=boundary,
                run_plan=plan,
            )
        )
        QApplication.processEvents()

        self.assertEqual(window.current_run_identity_label.text(), "Run A")
        self.assertEqual(window.current_run_status.label, "AcceptedRun")
        self.assertEqual(window.current_run_timestamp_label.text(), "2026-09-21 14:31")
        self.assertEqual(window.accept_plan_button.role, "unavailable")
        self.assertEqual(window.start_benchmark_button.role, "unavailable")
        self.assertFalse(window.accept_plan_button.isEnabled())
        self.assertFalse(window.start_benchmark_button.isEnabled())
        self.assertEqual(
            window.console_widget.state.active_generation_id,
            "generation-active",
        )

        window.set_current_run_projection(
            CurrentRunProjection(
                run_identity="Run A",
                state_label="BlockedRun",
                state_tone="neutral",
                timestamp="2026-09-21 14:32",
                execution_boundary=boundary,
                run_plan=plan,
            )
        )
        QApplication.processEvents()

        self.assertEqual(window.current_run_status.label, "BlockedRun")
        self.assertEqual(window.current_run_timestamp_label.text(), "2026-09-21 14:32")
        self.assertEqual(
            [value.text() for _label, value in window.execution_boundary_rows],
            list(boundary.ordered_values),
        )
        self.assertEqual(
            [value.text() for _label, value in window.run_plan_rows],
            list(plan.ordered_values),
        )
        self.assertEqual(
            window.console_widget.state.active_generation_id,
            "generation-active",
        )
        self.assertEqual(
            window.current_run_region.property("authoritySemantics"),
            "presentation-only",
        )

    def test_integrated_progress_and_console_reject_stale_generation_events(self) -> None:
        progress_view = ProgressView(
            ProgressProjection(
                run_id="run-active",
                generation_id="generation-current",
                overall=None,
                treatments=(),
                active_stage_index=None,
                active_stage_description=None,
                events=(),
                summary_empty_state="Progress summary unavailable",
                treatment_empty_state="Treatment progress unavailable",
                run_stage_empty_state="Run stage unavailable",
                
            )
        )
        self.addCleanup(progress_view.deleteLater)
        workspace = WorkspaceProjection(
            progress=progress_view,
            results=QLabel("Results"),
            reports=QLabel("Reports"),
            verification=QLabel("Verification"),
            evidence=QLabel("Artifacts"),
            scoring=QLabel("Scoring"),
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
        )
        self.addCleanup(window.deleteLater)
        window.set_workspace_projection(workspace, run_id="run-active")
        window.console_widget.bind_generation("generation-current")

        progress_view.push_event(
            ProgressEventProjection(
                generation_id="generation-stale",
                timestamp="14:30:00",
                event_icon="!",
                text="Stale progress event",
            )
        )
        progress_view.push_event(
            ProgressEventProjection(
                generation_id="generation-current",
                timestamp="14:30:01",
                event_icon="●",
                text="Current progress event",
            )
        )

        self.assertFalse(
            window.console_widget.append_live_output(
                "generation-stale",
                "stale live output",
            )
        )
        self.assertTrue(
            window.console_widget.append_live_output(
                "generation-current",
                "current live output",
            )
        )
        self.assertFalse(
            window.console_widget.append_diagnostic(
                "generation-stale",
                "stale diagnostic",
            )
        )
        self.assertTrue(
            window.console_widget.append_diagnostic(
                "generation-current",
                "current diagnostic",
            )
        )
        self.assertFalse(
            window.console_widget.set_raw_response(
                "generation-stale",
                "stale retained response",
            )
        )
        self.assertTrue(
            window.console_widget.set_raw_response(
                "generation-current",
                "exact retained response",
            )
        )
        QApplication.processEvents()

        self.assertEqual(
            tuple(event.text for event in progress_view.visible_events),
            ("Current progress event",),
        )
        window.console_widget.set_stream_live_view(True)
        window.console_widget.set_active_tab("Live View")
        self.assertEqual(
            window.console_widget.state.visible_text,
            "Input:\nInput unavailable.\n\nOutput:\nexact retained response",
        )
        window.console_widget.set_active_tab("Diagnostics")
        self.assertEqual(
            window.console_widget.state.visible_text,
            "current live outputcurrent diagnostic",
        )
        self.assertEqual(window.workspace_projection_run_id, "run-active")
        self.assertEqual(
            window.console_widget.state.active_generation_id,
            "generation-current",
        )

    def test_workspace_tabs_match_required_order_and_remain_presentation_only(self) -> None:
        tabs = self.window.workspace_tabs
        console = self.window.console_widget
        console.bind_generation("generation-a")

        self.assertIs(
            self.window.workspace_layout.itemAt(0).widget().widget(),
            self.window.current_run_region,
        )
        self.assertTrue(self.window.shell_status_bar.isAncestorOf(self.window.operation_banner))
        self.assertTrue(self.window.operation_banner.isHidden())
        self.assertIs(self.window.workspace_layout.itemAt(1).widget(), tabs)
        self.assertEqual(tabs.labels, ("Progress", "Scoring", "Results", "Evidence", "Verification", "Reports"))
        self.assertEqual(tabs.selected_index, 0)
        self.assertEqual(tabs.selected_label, "Progress")
        self.assertEqual(tabs.authority_semantics, "presentation-only")
        self.assertEqual(tabs.property("activationSemantics"), "presentation-only")

        empty_pages = tuple(self.window.workspace_pages.values())
        for index, label in enumerate(WORKSPACE_TAB_LABELS):
            self.assertEqual(tabs.tabText(index), label)
            page = self.window.workspace_pages[label]
            self.assertIs(tabs.widget(index).widget(), page)
            self.assertEqual(page.accessibleName(), f"{label} workspace")
            self.assertEqual(
                page.property("authoritySemantics"),
                "presentation-only",
            )
            self.assertEqual(page.property("projectionState"), "unavailable")

            empty_card = page.findChild(QWidget, "workspaceEmptyStateCard")
            empty_message = page.findChild(QLabel, "workspaceEmptyStateMessage")
            self.assertIsNotNone(empty_card)
            self.assertIsNotNone(empty_message)
            self.assertEqual(empty_card.title, f"{label} unavailable")
            self.assertEqual(
                empty_card.property("authoritySemantics"),
                "presentation-only",
            )
            self.assertEqual(
                empty_message.text(),
                (
                    f"No authoritative {label} projection is available "
                    "for the current workspace selection."
                ),
            )
            self.assertEqual(
                empty_message.accessibleName(),
                f"{label} unavailable",
            )
            self.assertTrue(empty_message.wordWrap())

        tabs.set_selected_index(5)
        QApplication.processEvents()
        self.assertEqual(tabs.selected_label, "Reports")
        self.assertEqual(console.state.active_generation_id, "generation-a")

        projection = WorkspaceProjection(
            progress=QLabel("Projected progress"),
            results=QLabel("Projected results"),
            reports=QLabel("Projected reports"),
            verification=QLabel("Projected verification"),
            evidence=QLabel("Projected artifacts"),
            scoring=QLabel("Scoring"),
        )
        self.window.set_workspace_projection(projection, run_id="run-projected")
        QApplication.processEvents()

        self.assertEqual(tabs.selected_label, "Reports")
        self.assertEqual(
            self.window.workspace_projection_run_id,
            "run-projected",
        )
        self.assertEqual(
            tuple(tabs.widget(index).widget() for index in range(len(WORKSPACE_TAB_LABELS))),
            projection.ordered_pages,
        )
        for empty_page in empty_pages:
            self.assertIsNone(empty_page.parent())
        for page in projection.ordered_pages:
            self.assertIsNone(page.findChild(QLabel, "workspaceEmptyStateMessage"))
        self.assertEqual(console.state.active_generation_id, "generation-a")

    def test_custom_benchmark_tabs_and_browse_follow_selection(self) -> None:
        custom = "arcgrav.custom.benchmark.core@1.0.0"
        authority = "arcgrav.authority-resolution.benchmark.core@1.0.0"
        selected: list[str] = []
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=SidebarProjection(
                benchmark_options=(authority, custom),
                selected_benchmark=custom,
                prompt_folder_visible=True,
            ),
            on_benchmark_selected=selected.append,
        )
        self.addCleanup(window.deleteLater)

        tabs = window.workspace_tabs
        available = {"Progress", "Scoring", "Results", "Evidence"}
        for index, label in enumerate(WORKSPACE_TAB_LABELS):
            self.assertEqual(tabs.isTabVisible(index), label in available)
        self.assertEqual(window.prompt_folder_browse.role, "secondary")
        self.assertEqual(
            window.prompt_folder_browse.property("arcgravSemanticComponent"),
            "action-button",
        )
        self.assertIn("background-color:", window.prompt_folder_browse.styleSheet())

        window.benchmark_input.set_value(authority)
        self.assertEqual(selected, [authority])
        self.assertTrue(all(tabs.isTabVisible(i) for i in range(tabs.count())))

        tabs.set_selected_index(WORKSPACE_TAB_LABELS.index("Verification"))
        window.benchmark_input.set_value(custom)
        self.assertEqual(selected, [authority, custom])
        self.assertEqual(tabs.selected_label, "Results")
        for index, label in enumerate(WORKSPACE_TAB_LABELS):
            self.assertEqual(tabs.isTabVisible(index), label in available)

        tabs.set_selected_index(WORKSPACE_TAB_LABELS.index("Scoring"))
        self.assertEqual(tabs.selected_label, "Scoring")
        window.clear_workspace_projection()
        self.assertEqual(tabs.selected_label, "Scoring")
        for index, label in enumerate(WORKSPACE_TAB_LABELS):
            self.assertEqual(tabs.isTabVisible(index), label in available)
        window.set_sidebar_projection(SidebarProjection(
            benchmark_options=(authority, custom),
            selected_benchmark=authority,
        ))
        self.assertTrue(all(tabs.isTabVisible(i) for i in range(tabs.count())))

    def test_retained_run_selection_binds_workspace_projection_without_retargeting_console(
        self,
    ) -> None:
        def workspace(prefix: str) -> WorkspaceProjection:
            return WorkspaceProjection(
                progress=QLabel(f"{prefix} progress"),
                results=QLabel(f"{prefix} results"),
                reports=QLabel(f"{prefix} reports"),
                verification=QLabel(f"{prefix} verification"),
                evidence=QLabel(f"{prefix} artifacts"),
                scoring=QLabel("Scoring"),
            )

        run_a_workspace = workspace("run-a")
        run_b_workspace = workspace("run-b")
        projection = SidebarProjection(
            runs=(
                RetainedRunProjection(
                    run_id="run-a",
                    display_identity="Run A",
                    state_label="Accepted",
                    state_tone="success",
                    timestamp="2026-09-21 14:00",
                    selected=True,
                ),
                RetainedRunProjection(
                    run_id="run-b",
                    display_identity="Run B",
                    state_label="Blocked",
                    state_tone="neutral",
                    timestamp="2026-09-21 14:10",
                ),
            )
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection,
            retained_workspace_projections={
                "run-a": run_a_workspace,
                "run-b": run_b_workspace,
            },
        )
        self.addCleanup(window.deleteLater)

        self.assertEqual(window.workspace_projection_run_id, "run-a")
        self.assertEqual(window.workspace_tabs.labels, WORKSPACE_TAB_LABELS)
        self.assertEqual(
            tuple(window.workspace_tabs.widget(index).widget() for index in range(len(WORKSPACE_TAB_LABELS))),
            run_a_workspace.ordered_pages,
        )
        self.assertNotEqual(
            window.run_rows["run-b"].focusPolicy(),
            Qt.FocusPolicy.NoFocus,
        )

        window.workspace_tabs.set_selected_index(5)
        window.console_widget.bind_generation("generation-a")
        environment_text = "[READY] Repository: application session ready"
        window.set_environment_projection(environment_text)
        window.console_widget.set_active_tab("Environment")
        window.set_console_height(317)
        window.console_widget.set_expanded(False)
        QTest.mouseClick(
            window.run_rows["run-b"],
            Qt.MouseButton.LeftButton,
        )
        QApplication.processEvents()

        self.assertEqual(window.selected_run_id, "run-b")
        self.assertEqual(window.workspace_projection_run_id, "run-b")
        self.assertEqual(window.workspace_tabs.selected_label, "Reports")
        self.assertEqual(window.workspace_tabs.labels, WORKSPACE_TAB_LABELS)
        self.assertEqual(
            tuple(window.workspace_tabs.widget(index).widget() for index in range(len(WORKSPACE_TAB_LABELS))),
            run_b_workspace.ordered_pages,
        )
        self.assertEqual(
            window.console_widget.state.active_generation_id,
            "generation-a",
        )
        self.assertEqual(window.console_widget.state.active_tab, "Environment")
        self.assertFalse(window.console_widget.state.expanded)
        self.assertEqual(
            window.console_widget.state.last_nonzero_expanded_height,
            317,
        )
        self.assertEqual(window.console_widget.state.visible_text, environment_text)

        QTest.mouseClick(
            window.run_rows["run-a"],
            Qt.MouseButton.LeftButton,
        )
        QApplication.processEvents()
        self.assertEqual(window.workspace_projection_run_id, "run-a")
        self.assertEqual(window.workspace_tabs.selected_label, "Reports")
        self.assertEqual(
            tuple(window.workspace_tabs.widget(index).widget() for index in range(len(WORKSPACE_TAB_LABELS))),
            run_a_workspace.ordered_pages,
        )
        self.assertEqual(
            window.console_widget.state.active_generation_id,
            "generation-a",
        )
        self.assertEqual(window.console_widget.state.active_tab, "Environment")
        self.assertFalse(window.console_widget.state.expanded)
        self.assertEqual(window.console_widget.state.visible_text, environment_text)

    def test_reference_geometry_preserves_console_and_header_regions(self) -> None:
        self.window.show()
        QApplication.processEvents()

        splitter = self.window.vertical_splitter
        self.assertEqual(self.window.upper_work_area.width(), splitter.width())
        self.assertEqual(self.window.console_widget.width(), splitter.width())
        self.assertEqual(self.window.upper_work_area.width(), self.window.width())

        console_height = splitter.sizes()[1]
        self.assertGreaterEqual(console_height, 220)

    def test_long_console_overflow_stays_local_under_compact_splitter(self) -> None:
        self.window.resize(REFERENCE_WINDOW_WIDTH, REFERENCE_WINDOW_HEIGHT)
        self.window.show()
        QApplication.processEvents()

        console = self.window.console_widget
        console.bind_generation("generation-overflow")
        console.set_active_tab("Diagnostics")
        QApplication.processEvents()

        splitter = self.window.vertical_splitter
        header = console.clear_button.parentWidget()
        self.assertIsNotNone(header)
        assert header is not None
        self.assertEqual(
            splitter.handleWidth(),
            compact_splitter_handle_extent(),
        )

        baseline_splitter_sizes = tuple(splitter.sizes())
        baseline_sidebar_geometry = self.window.sidebar.geometry()
        baseline_workspace_geometry = self.window.workspace.geometry()
        baseline_status_geometry = self.window.shell_status_bar.geometry()
        baseline_console_geometry = console.geometry()
        baseline_header_geometry = header.geometry()
        baseline_tab_geometry = console.tab_bar.geometry()

        long_line = "[2026-09-25T12:00:00Z]   WARNING   " + ("x" * 1600)
        payload = "\n".join(f"{long_line}{index}" for index in range(180))
        self.assertTrue(
            console.append_diagnostic("generation-overflow", payload)
        )
        QApplication.processEvents()

        view = console.console_view("Diagnostics")
        horizontal = view.horizontalScrollBar()
        vertical = view.verticalScrollBar()
        self.assertGreater(horizontal.maximum(), 0)
        self.assertGreater(vertical.maximum(), 0)

        self.assertEqual(tuple(splitter.sizes()), baseline_splitter_sizes)
        self.assertEqual(self.window.sidebar.geometry(), baseline_sidebar_geometry)
        self.assertEqual(self.window.workspace.geometry(), baseline_workspace_geometry)
        self.assertEqual(self.window.shell_status_bar.geometry(), baseline_status_geometry)
        self.assertEqual(console.geometry(), baseline_console_geometry)
        self.assertEqual(header.geometry(), baseline_header_geometry)
        self.assertEqual(console.tab_bar.geometry(), baseline_tab_geometry)

        view_geometry = view.geometry()
        horizontal.setValue(horizontal.maximum())
        vertical.setValue(vertical.maximum())
        QApplication.processEvents()

        self.assertEqual(view.geometry(), view_geometry)
        self.assertEqual(tuple(splitter.sizes()), baseline_splitter_sizes)
        self.assertEqual(self.window.sidebar.geometry(), baseline_sidebar_geometry)
        self.assertEqual(self.window.workspace.geometry(), baseline_workspace_geometry)
        self.assertEqual(self.window.shell_status_bar.geometry(), baseline_status_geometry)
        self.assertEqual(console.geometry(), baseline_console_geometry)
        self.assertEqual(header.geometry(), baseline_header_geometry)
        self.assertEqual(console.tab_bar.geometry(), baseline_tab_geometry)
        self.assertEqual(
            console.state.active_generation_id,
            "generation-overflow",
        )
        self.assertEqual(console.state.active_tab, "Diagnostics")

    def test_bottom_console_is_full_width_splitter_region_and_presentation_only(self) -> None:
        console = self.window.console_widget
        console.bind_generation("generation-a")
        console.append_diagnostic("generation-a", "resize-preserved")
        console.set_active_tab("Diagnostics")
        self.window.workspace_tabs.set_selected_index(5)
        self.window.set_current_run_projection(
            CurrentRunProjection(
                run_identity="Run resize",
                state_label="Planned",
                state_tone="neutral",
                timestamp="2026-09-24 16:00",
                execution_boundary=ExecutionBoundaryProjection(
                    benchmark="Authority Resolution",
                    runner="Codex CLI",
                    model="gpt-5.6",
                    cases="24",
                    boundary_fingerprint="sha256:resize-boundary",
                ),
                run_plan=RunPlanProjection(
                    treatments="Baseline, treatment-a",
                    cases="24 cases",
                    execution="2 repetitions",
                    evaluation="Exact + semantic",
                    outputs="Accepted evidence + report",
                ),
                accept_plan_available=False,
                start_benchmark_available=False,
            )
        )
        self.assertEqual(console.tab_labels, CONSOLE_TABS)
        self.assertEqual(console.authority_semantics, "presentation-only")

        self.window.show()
        QApplication.processEvents()
        splitter = self.window.vertical_splitter
        self.assertEqual(
            splitter.handleWidth(),
            compact_splitter_handle_extent(),
        )

        splitter.moveSplitter(
            splitter.height() - splitter.handleWidth() - 220,
            1,
        )
        QApplication.processEvents()
        smaller_height = splitter.sizes()[1]
        self.assertAlmostEqual(smaller_height, 220, delta=6)
        QApplication.processEvents()
        self.assertAlmostEqual(splitter.sizes()[1], smaller_height, delta=1)

        splitter.moveSplitter(
            splitter.height() - splitter.handleWidth() - 360,
            1,
        )
        QApplication.processEvents()
        resized_height = splitter.sizes()[1]
        self.assertGreater(resized_height, smaller_height)
        self.assertAlmostEqual(resized_height, 360, delta=6)
        QApplication.processEvents()
        self.assertAlmostEqual(splitter.sizes()[1], resized_height, delta=1)

        self.assertEqual(
            self.preferences[LAST_EXPANDED_HEIGHT_KEY],
            resized_height,
        )
        self.assertEqual(console.state.last_nonzero_expanded_height, resized_height)
        self.assertEqual(console.state.active_generation_id, "generation-a")
        self.assertEqual(console.state.active_tab, "Diagnostics")
        self.assertEqual(console.state.visible_text, "resize-preserved")
        self.assertEqual(self.window.workspace_tabs.selected_label, "Reports")
        self.assertEqual(self.window.current_run_identity_label.text(), "Run resize")
        self.assertFalse(self.window.accept_plan_button.isEnabled())
        self.assertFalse(self.window.start_benchmark_button.isEnabled())

        console.set_expanded(False)
        QApplication.processEvents()
        collapsed_height = splitter.sizes()[1]
        self.assertFalse(console.expanded)
        self.assertLess(collapsed_height, resized_height)
        self.assertEqual(console.collapse_button.accessibleName(), "Expand console")
        self.assertTrue(console.collapse_button.isVisible())
        self.assertEqual(console.state.active_generation_id, "generation-a")
        self.assertEqual(console.state.active_tab, "Diagnostics")
        self.assertEqual(console.state.visible_text, "resize-preserved")
        self.assertEqual(self.window.workspace_tabs.selected_label, "Reports")
        self.assertEqual(self.window.current_run_identity_label.text(), "Run resize")
        self.assertFalse(self.window.accept_plan_button.isEnabled())
        self.assertFalse(self.window.start_benchmark_button.isEnabled())

        console.collapse_button.click()
        QApplication.processEvents()
        self.assertTrue(console.expanded)
        self.assertEqual(console.collapse_button.accessibleName(), "Collapse console")
        self.assertEqual(console.state.last_nonzero_expanded_height, resized_height)
        self.assertAlmostEqual(splitter.sizes()[1], resized_height, delta=1)
        self.assertEqual(console.state.active_generation_id, "generation-a")
        self.assertEqual(console.state.active_tab, "Diagnostics")
        self.assertEqual(console.state.visible_text, "resize-preserved")
        self.assertEqual(self.window.workspace_tabs.selected_label, "Reports")
        self.assertEqual(self.window.current_run_identity_label.text(), "Run resize")
        self.assertFalse(self.window.accept_plan_button.isEnabled())
        self.assertFalse(self.window.start_benchmark_button.isEnabled())

        restored_window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            connectivity_label="Offline",
            connectivity_tone="neutral",
            console_preferences=self.preferences,
            shell_preferences={SHELL_CONSOLE_EXPANDED_KEY: True},
        )
        self.addCleanup(restored_window.deleteLater)
        restored_window.show()
        QApplication.processEvents()
        self.assertEqual(
            restored_window.console_widget.state.last_nonzero_expanded_height,
            resized_height,
        )
        self.assertAlmostEqual(
            restored_window.vertical_splitter.sizes()[1],
            resized_height,
            delta=1,
        )

    def test_console_restore_compatibility_clamps_oversized_height(self) -> None:
        preferred_height = REFERENCE_WINDOW_HEIGHT * 2
        console_preferences = {LAST_EXPANDED_HEIGHT_KEY: preferred_height}
        shell_preferences = {
            SHELL_CONSOLE_EXPANDED_KEY: True,
            SHELL_WINDOW_WIDTH_KEY: 900,
            SHELL_WINDOW_HEIGHT_KEY: 640,
        }
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            connectivity_label="Offline",
            connectivity_tone="neutral",
            shell_preferences=shell_preferences,
            console_preferences=console_preferences,
        )
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()

        actual_height = window.vertical_splitter.sizes()[1]
        self.assertGreater(actual_height, 0)
        self.assertLess(actual_height, preferred_height)
        self.assertGreater(window.vertical_splitter.sizes()[0], 0)
        self.assertEqual(
            window.console_widget.state.last_nonzero_expanded_height,
            preferred_height,
        )
        self.assertEqual(
            console_preferences[LAST_EXPANDED_HEIGHT_KEY],
            preferred_height,
        )

        window.console_widget.set_expanded(False)
        QApplication.processEvents()
        collapsed_height = window.vertical_splitter.sizes()[1]
        self.assertLess(collapsed_height, actual_height)
        self.assertEqual(
            window.console_widget.collapse_button.accessibleName(),
            "Expand console",
        )

        window.console_widget.collapse_button.click()
        QApplication.processEvents()
        self.assertTrue(window.console_widget.expanded)
        self.assertGreater(window.vertical_splitter.sizes()[1], collapsed_height)
        self.assertLess(
            window.vertical_splitter.sizes()[1],
            preferred_height,
        )

    def test_console_layout_preferences_do_not_enter_build_plan_intent(self) -> None:
        build_plan_snapshots: list[SidebarInputSnapshot] = []
        preferences = {LAST_EXPANDED_HEIGHT_KEY: 301}
        shell_preferences: dict[str, object] = {}
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            model_options=("gpt-5.6",),
            selected_model="gpt-5.6",
            credential_value="ephemeral-input",
            build_plan_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            shell_preferences=shell_preferences,
            console_preferences=preferences,
            sidebar_projection=projection,
            on_build_plan=build_plan_snapshots.append,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()

        window.workspace_tabs.set_selected_index(WORKSPACE_TAB_LABELS.index("Evidence"))
        window.console_widget.bind_generation("generation-a")
        window.console_widget.set_active_tab("Diagnostics")
        window.set_console_height(333)
        window.console_widget.set_expanded(False)
        QApplication.processEvents()

        self.assertEqual(window.workspace_tabs.selected_label, "Evidence")
        self.assertEqual(window.console_widget.state.active_generation_id, "generation-a")
        self.assertEqual(window.console_widget.state.active_tab, "Diagnostics")
        self.assertEqual(preferences[LAST_EXPANDED_HEIGHT_KEY], 333)
        self.assertEqual(window.console_widget.collapse_button.accessibleName(), "Expand console")
        self.assertTrue(window.console_widget.collapse_button.isVisible())

        window.build_plan_button.click()
        QApplication.processEvents()
        expected_snapshot = SidebarInputSnapshot(
            benchmark="Authority Resolution",
            runner="Codex CLI",
            model="gpt-5.6",
            credential="ephemeral-input",
            temperature=None,
            max_tokens=None,
        )
        self.assertEqual(build_plan_snapshots, [expected_snapshot])
        self.assertEqual(
            set(SidebarInputSnapshot.__dataclass_fields__),
            {
                "benchmark",
                "runner",
                "model",
                "credential",
                "temperature",
                "max_tokens",
                "additional_controls",
                "model_discovery_context_fingerprints",
                "prompt_folder",
                "excluded_treatments",
                "iterations",
                "randomize_treatment_start",
                "randomize_per_iteration",
                "run_cache_validation_replays",
            },
        )

        restored_window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            console_preferences=preferences,
            sidebar_projection=projection,
            on_build_plan=build_plan_snapshots.append,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(restored_window.deleteLater)
        restored_window.show()
        QApplication.processEvents()
        self.assertEqual(restored_window.console_widget.state.last_nonzero_expanded_height, 333)
        restored_window.build_plan_button.click()
        QApplication.processEvents()
        self.assertEqual(build_plan_snapshots, [expected_snapshot, expected_snapshot])
        self.assertNotIn("ephemeral-input", repr(shell_preferences))
        self.assertNotIn("ephemeral-input", repr(preferences))

    def test_zero_retained_runs_have_deliberate_empty_state(self) -> None:
        self.assertEqual(self.window.runs_card.title, "Runs")
        self.assertEqual(self.window.runs_card.title_role, "section-heading")
        self.assertEqual(self.window.run_rows, {})
        self.assertIsNotNone(self.window.runs_empty_label)
        self.assertEqual(self.window.runs_empty_label.text(), "No runs")
        self.assertEqual(
            self.window.runs_empty_label.accessibleName(),
            "No runs",
        )
        self.assertEqual(
            self.window.runs_empty_label.property("authoritySemantics"),
            "presentation-only",
        )
        self.assertTrue(
            self.window.runs_card.isAncestorOf(self.window.runs_empty_label)
        )
        self.assertIs(self.window.build_plan_button.parentWidget(), self.window.sidebar_header)
        self.assertFalse(self.window.sidebar_content.isAncestorOf(self.window.build_plan_button))

    def test_sidebar_error_pointer_does_not_render_diagnostic_content(self) -> None:
        long_fragment = (
            "Repository runner readiness remains unresolved because the configured "
            "provider-free execution prerequisite includes deliberately verbose "
            "diagnostic context that must never be repeated in the sidebar. "
        )
        remediation = (
            "Resolve the prerequisite and refresh Environment before building a plan. "
        ) * 5
        blocker = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="long-runner-readiness",
            message=long_fragment * 4,
            remediation=remediation,
            details="codex_cli_model_catalog_unavailable — api_key=sidebar-secret",
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=SidebarProjection(
                build_plan_available=True,
                prerequisite_diagnostics=(blocker,),
            ),
            on_build_plan=lambda _snapshot: None,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)
        window.resize(REFERENCE_WINDOW_WIDTH, REFERENCE_WINDOW_HEIGHT)
        window.show()
        QApplication.processEvents()

        self.assertEqual(window.sidebar.width(), REFERENCE_SIDEBAR_WIDTH)
        self.assertEqual(
            window.workspace_scroll.mapTo(window, QPoint()).x(),
            (
                window.sidebar.geometry().right()
                + 1
            ),
        )
        self.assertFalse(window.sidebar_scroll.horizontalScrollBar().isVisible())

        self.assertEqual(1, len(window.prerequisite_diagnostic_widgets))
        viewport_width = window.sidebar_scroll.viewport().width()
        diagnostic_frame = window.prerequisite_diagnostic_widgets[0]
        diagnostic_layout = diagnostic_frame.layout()
        self.assertEqual(
            diagnostic_layout.getContentsMargins(),
            (
                DEFAULT_LAYOUT_METRICS.metric("compact-panel-padding-x"),
                DEFAULT_LAYOUT_METRICS.metric("compact-panel-padding-y"),
                DEFAULT_LAYOUT_METRICS.metric("compact-panel-padding-x"),
                DEFAULT_LAYOUT_METRICS.metric("compact-panel-padding-y"),
            ),
        )
        self.assertEqual(
            diagnostic_layout.spacing(),
            DEFAULT_LAYOUT_METRICS.metric("compact-panel-gap"),
        )
        self.assertLessEqual(diagnostic_frame.width(), viewport_width)
        self.assertEqual(
            ("long-runner-readiness",),
            diagnostic_frame.property("diagnosticNames"),
        )
        self.assertEqual("Environment", diagnostic_frame.property("consoleView"))
        self.assertEqual(
            "Error; see Console → Environment",
            diagnostic_frame.accessibleName(),
        )

        error_icon_label = diagnostic_frame.findChild(
            QLabel,
            "sidebarPrerequisiteErrorIcon",
        )
        self.assertIsNotNone(error_icon_label)
        assert error_icon_label is not None
        self.assertEqual(
            "status-error",
            error_icon_label.property("semanticIconRole"),
        )
        self.assertFalse(error_icon_label.pixmap().isNull())
        self.assertEqual(
            semantic_icon(
                "status-error",
                theme=DEFAULT_LIGHT_THEME,
                size=16,
            ).pixmap(16, 16).toImage(),
            error_icon_label.pixmap().toImage(),
        )

        message_label = diagnostic_frame.findChild(
            QLabel,
            "sidebarPrerequisiteMessage",
        )
        self.assertIsNotNone(message_label)
        assert message_label is not None
        self.assertEqual(
            "see Console → Environment",
            message_label.text(),
        )
        self.assertTrue(message_label.wordWrap())
        self.assertNotIn("Error", message_label.text())

        sidebar_text = " ".join(
            label.text()
            for label in window.sidebar.findChildren(QLabel)
        )
        sidebar_accessibility = (
            diagnostic_frame.accessibleName()
            + " "
            + diagnostic_frame.accessibleDescription()
        )
        for hidden_detail in (
            long_fragment.strip(),
            remediation.strip(),
            "codex_cli_model_catalog_unavailable",
            "sidebar-secret",
        ):
            self.assertNotIn(hidden_detail, sidebar_text)
            self.assertNotIn(hidden_detail, sidebar_accessibility)

        visible_sidebar_text = {
            label.text()
            for label in window.sidebar.findChildren(QLabel)
            if label.isVisible()
        }
        self.assertIn("Configuration", visible_sidebar_text)
        self.assertIn("Runs", visible_sidebar_text)
        self.assertTrue(window.build_plan_button.isVisible())

    def test_prerequisite_errors_are_consolidated_without_changing_scope(self) -> None:
        planning = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="planning-boundary",
            message="Canonical planning identity is unresolved.",
            remediation="Resolve the planning identity.",
            operation="planning",
        )
        execution = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="runner-authentication",
            message="Runner authentication is unresolved.",
            remediation="Restore the registered authentication source.",
            operation="execution",
        )
        selected_runs: list[str] = []
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            connectivity_label="Ready",
            connectivity_tone="success",
            sidebar_projection=SidebarProjection(
                build_plan_available=True,
                prerequisite_diagnostics=(planning, execution),
                runs=(
                    RetainedRunProjection(
                        run_id="run-a",
                        display_identity="Run A",
                        state_label="Accepted",
                        state_tone="success",
                        timestamp="2026-09-21 14:00",
                    ),
                ),
            ),
            on_build_plan=lambda _snapshot: None,
            on_run_selected=selected_runs.append,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        layout = window.sidebar_layout
        self.assertEqual(1, len(window.prerequisite_diagnostic_widgets))
        pointer = window.prerequisite_diagnostic_widgets[0]
        self.assertLess(
            layout.indexOf(window.runner_card),
            layout.indexOf(pointer),
        )
        self.assertLess(
            layout.indexOf(pointer),
            layout.indexOf(window.runs_card),
        )
        self.assertEqual(layout.indexOf(window.build_plan_button), -1)
        self.assertIs(window.build_plan_button.parentWidget(), window.sidebar_header)
        self.assertEqual(
            ("planning-boundary", "runner-authentication"),
            pointer.property("diagnosticNames"),
        )
        self.assertEqual(
            ("planning", "execution"),
            pointer.property("prerequisiteOperations"),
        )
        self.assertEqual("Environment", pointer.property("consoleView"))
        self.assertEqual(
            "see Console → Environment",
            pointer.findChild(
                QLabel,
                "sidebarPrerequisiteMessage",
            ).text(),
        )
        self.assertEqual(
            "status-error",
            pointer.findChild(
                QLabel,
                "sidebarPrerequisiteErrorIcon",
            ).property("semanticIconRole"),
        )
        self.assertEqual(window.build_plan_button.role, "unavailable")
        self.assertIn("run-a", window.run_rows)

        QTest.mouseClick(
            window.run_rows["run-a"],
            Qt.MouseButton.LeftButton,
        )
        QApplication.processEvents()
        self.assertEqual(["run-a"], selected_runs)
        self.assertEqual(window.build_plan_button.role, "unavailable")

        execution_only = SidebarProjection(
            build_plan_available=True,
            prerequisite_diagnostics=(execution,),
            runs=(
                RetainedRunProjection(
                    run_id="run-a",
                    display_identity="Run A",
                    state_label="Accepted",
                    state_tone="success",
                    timestamp="2026-09-21 14:00",
                ),
            ),
        )
        window.set_sidebar_projection(execution_only)
        QApplication.processEvents()

        self.assertTrue(execution_only.build_plan_effectively_available)
        self.assertEqual(window.build_plan_button.role, "primary")
        self.assertEqual(1, len(window.prerequisite_diagnostic_widgets))
        self.assertEqual(
            ("runner-authentication",),
            window.prerequisite_diagnostic_widgets[0].property(
                "diagnosticNames"
            ),
        )
        self.assertIn("run-a", window.run_rows)

    def test_small_window_preserves_primary_regions_and_fixed_sidebar(self) -> None:
        self.window.resize(760, 700)
        self.window.show()
        QApplication.processEvents()

        self.assertEqual(self.window.sidebar.width(), REFERENCE_SIDEBAR_WIDTH)
        self.assertGreater(
            self.window.workspace.width(),
            self.window.sidebar.width(),
        )
        self.assertTrue(self.window.current_run_region.isVisible())
        self.assertTrue(self.window.workspace_tabs.isVisible())
        self.assertTrue(self.window.console_widget.collapse_button.isVisible())
        self.assertTrue(self.window.shell_status_bar.isVisible())

    def test_keyboard_focus_order_spans_shell_commands_workspace_console_and_status(self) -> None:
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            model_options=("gpt-5.6",),
            selected_model="gpt-5.6",
            credential_value="transient-secret",
            build_plan_available=True,
            runs=(
                RetainedRunProjection(
                    run_id="run-a",
                    display_identity="Run A",
                    state_label="Accepted",
                    state_tone="success",
                    timestamp="2026-09-21 14:00",
                    selected=True,
                ),
            ),
        )
        current_run = CurrentRunProjection(
            run_identity="Run A",
            state_label="Planned",
            state_tone="neutral",
            timestamp="2026-09-21 14:30",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="Authority Resolution",
                runner="Codex CLI",
                model="gpt-5.6",
                cases="24",
                boundary_fingerprint="sha256:caller-owned-boundary",
            ),
            run_plan=RunPlanProjection(
                treatments="Baseline",
                cases="24 cases",
                execution="1 repetition",
                evaluation="Exact",
                outputs="Accepted evidence",
            ),
            accept_plan_available=True,
            start_benchmark_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection,
            current_run_projection=current_run,
            on_build_plan=lambda _snapshot: None,
            on_run_selected=lambda _run_id: None,
            on_accept_plan=lambda: None,
            on_start_benchmark=lambda: None,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        focus_order = window._keyboard_focus_order
        anchors = (
            window.build_plan_button,
            window.benchmark_input.combo_box,
            window.runner_input.combo_box,
            window.model_input.combo_box,
            window.credential_input.line_edit,
            window.run_rows["run-a"],
            window.accept_plan_button,
            window.start_benchmark_button,
            window.workspace_tabs.tabBar(),
            window.console_widget.tab_bar,
            window.console_widget.collapse_button,
        )
        indices = [focus_order.index(control) for control in anchors]
        self.assertEqual(indices, sorted(indices))
        for control in anchors:
            self.assertNotEqual(control.focusPolicy(), Qt.FocusPolicy.NoFocus)

        self.assertTrue(window.run_rows["run-a"].selected)
        self.assertEqual(
            window.run_rows["run-a"].identity_label.text(),
            "Run A",
        )
        self.assertEqual(
            window.run_rows["run-a"].accessibleDescription(),
            "Selected retained run",
        )
        self.assertTrue(window.run_rows["run-a"].status_badge.icon_text)

    def test_shell_persists_only_local_window_tab_and_console_presentation_state(self) -> None:
        shell_preferences: dict[str, object] = {}
        console_preferences: dict[str, int] = {}
        build_plan_snapshots: list[SidebarInputSnapshot] = []
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            model_options=("gpt-5.6",),
            selected_model="gpt-5.6",
            credential_value="ephemeral-input",
            build_plan_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            shell_preferences=shell_preferences,
            console_preferences=console_preferences,
            sidebar_projection=projection,
            on_build_plan=build_plan_snapshots.append,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()

        window.resize(1024, 768)
        window.show()
        QApplication.processEvents()
        selected_sidebar_width = REFERENCE_SIDEBAR_WIDTH
        self.assertEqual(window.sidebar.width(), selected_sidebar_width)
        window.workspace_tabs.set_selected_index(WORKSPACE_TAB_LABELS.index("Verification"))
        window.console_widget.set_active_tab("Diagnostics")
        window.set_console_height(333)
        window.console_widget.set_expanded(False)
        QApplication.processEvents()

        self.assertEqual(shell_preferences[SHELL_WINDOW_WIDTH_KEY], 1024)
        self.assertEqual(shell_preferences[SHELL_WINDOW_HEIGHT_KEY], 768)
        self.assertNotIn(SHELL_SIDEBAR_WIDTH_KEY, shell_preferences)
        self.assertEqual(shell_preferences[SHELL_WORKSPACE_TAB_KEY], "Verification")
        self.assertEqual(shell_preferences[SHELL_CONSOLE_TAB_KEY], "Diagnostics")
        self.assertIs(shell_preferences[SHELL_CONSOLE_EXPANDED_KEY], False)
        self.assertEqual(console_preferences[LAST_EXPANDED_HEIGHT_KEY], 333)
        self.assertEqual(
            set(shell_preferences),
            {
                SHELL_WINDOW_WIDTH_KEY,
                SHELL_WINDOW_HEIGHT_KEY,
                SHELL_WORKSPACE_TAB_KEY,
                SHELL_CONSOLE_TAB_KEY,
                SHELL_CONSOLE_EXPANDED_KEY,
            },
        )

        window.build_plan_button.click()
        QApplication.processEvents()
        expected_snapshot = SidebarInputSnapshot(
            benchmark="Authority Resolution",
            runner="Codex CLI",
            model="gpt-5.6",
            credential="ephemeral-input",
            temperature=None,
            max_tokens=None,
        )
        self.assertEqual(build_plan_snapshots, [expected_snapshot])

        restored = BenchmarkShellWindow(
            application_icon=self.application_icon,
            shell_preferences=shell_preferences,
            console_preferences=console_preferences,
            sidebar_projection=projection,
            on_build_plan=build_plan_snapshots.append,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(restored.deleteLater)
        restored.show()
        QApplication.processEvents()

        self.assertEqual((restored.width(), restored.height()), (1024, 768))
        self.assertAlmostEqual(
            restored.sidebar.width(),
            selected_sidebar_width,
            delta=1,
        )
        self.assertEqual(restored.workspace_tabs.selected_label, "Verification")
        self.assertEqual(restored.console_widget.state.active_tab, "Diagnostics")
        self.assertFalse(restored.console_widget.expanded)
        self.assertEqual(
            restored.console_widget.state.last_nonzero_expanded_height,
            333,
        )
        restored.build_plan_button.click()
        QApplication.processEvents()
        self.assertEqual(build_plan_snapshots, [expected_snapshot, expected_snapshot])

    def test_sidebar_is_fixed_across_window_resize_and_preserves_projected_state(
        self,
    ) -> None:
        shell_preferences: dict[str, object] = {}
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            model_options=("gpt-5.6",),
            selected_model="gpt-5.6",
            credential_value="ephemeral-input",
            runs=(
                RetainedRunProjection(
                    run_id="run-a",
                    display_identity="Run A",
                    state_label="Accepted",
                    state_tone="success",
                    timestamp="2026-09-21 14:00",
                    selected=True,
                ),
            ),
        )
        current_run = CurrentRunProjection(
            run_identity="Run Prepared",
            state_label="Planned",
            state_tone="neutral",
            timestamp="2026-09-21 14:30",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="Authority Resolution",
                runner="Codex CLI",
                model="gpt-5.6",
                cases="24",
                boundary_fingerprint="sha256:resize-preservation",
            ),
            run_plan=RunPlanProjection(
                treatments="Baseline, treatment-a",
                cases="24 cases",
                execution="2 repetitions",
                evaluation="Exact + semantic",
                outputs="Accepted evidence + report",
            ),
            accept_plan_available=True,
            start_benchmark_available=True,
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            shell_preferences=shell_preferences,
            sidebar_projection=projection,
            current_run_projection=current_run,
            on_accept_plan=lambda: None,
            on_start_benchmark=lambda: None,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)
        window.resize(1024, 700)
        window.show()
        QApplication.processEvents()

        expected_snapshot = window.sidebar_input_snapshot()
        window.workspace_tabs.set_selected_index(WORKSPACE_TAB_LABELS.index("Results"))
        window.console_widget.bind_generation("generation-a")
        window.console_widget.set_active_tab("Live View")
        QApplication.processEvents()

        selected_width = REFERENCE_SIDEBAR_WIDTH
        self.assertEqual(window.sidebar.width(), selected_width)
        initial_workspace_width = window.workspace_column.width()
        window.resize(760, 700)
        QApplication.processEvents()
        self.assertEqual(window.sidebar.width(), selected_width)
        self.assertLess(window.workspace_column.width(), initial_workspace_width)
        self.assertGreater(window.workspace_column.width(), 0)
        self.assertNotIn(SHELL_SIDEBAR_WIDTH_KEY, shell_preferences)

        self.assertEqual(window.sidebar_input_snapshot(), expected_snapshot)
        self.assertEqual(window.workspace_tabs.selected_label, "Results")
        self.assertEqual(
            window.console_widget.state.active_generation_id,
            "generation-a",
        )
        self.assertEqual(window.console_widget.state.active_tab, "Live View")
        self.assertTrue(window.run_rows["run-a"].selected)
        self.assertTrue(window.accept_plan_button.isEnabled())
        self.assertTrue(window.start_benchmark_button.isEnabled())

        window.resize(1180, 700)
        QApplication.processEvents()
        self.assertAlmostEqual(window.sidebar.width(), selected_width, delta=1)
        self.assertEqual(window.sidebar_input_snapshot(), expected_snapshot)
        self.assertEqual(window.workspace_tabs.selected_label, "Results")
        self.assertEqual(
            window.console_widget.state.active_generation_id,
            "generation-a",
        )
        self.assertEqual(window.console_widget.state.active_tab, "Live View")
        self.assertTrue(window.run_rows["run-a"].selected)

        restored = BenchmarkShellWindow(
            application_icon=self.application_icon,
            shell_preferences=shell_preferences,
            sidebar_projection=projection,
            current_run_projection=current_run,
            on_accept_plan=lambda: None,
            on_start_benchmark=lambda: None,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(restored.deleteLater)
        restored.show()
        QApplication.processEvents()

        self.assertAlmostEqual(restored.sidebar.width(), selected_width, delta=1)
        self.assertEqual(restored.sidebar_input_snapshot(), expected_snapshot)
        self.assertEqual(restored.sidebar_scroll.verticalScrollBar().value(), 0)

        clamped_preferences = dict(shell_preferences)
        clamped_preferences[SHELL_WINDOW_WIDTH_KEY] = 520
        clamped_preferences[SHELL_SIDEBAR_WIDTH_KEY] = 10_000
        clamped = BenchmarkShellWindow(
            application_icon=self.application_icon,
            shell_preferences=clamped_preferences,
            sidebar_projection=projection,
            current_run_projection=current_run,
            on_accept_plan=lambda: None,
            on_start_benchmark=lambda: None,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(clamped.deleteLater)
        clamped.show()
        QApplication.processEvents()

        self.assertEqual(clamped.sidebar.width(), REFERENCE_SIDEBAR_WIDTH)
        self.assertGreater(clamped.workspace_column.width(), 0)
        self.assertEqual(
            clamped_preferences[SHELL_SIDEBAR_WIDTH_KEY],
            10_000,
        )

    def test_sidebar_fixed_width_and_scroll_survive_resize_and_projection_refresh(self) -> None:
        diagnostics = tuple(
            SidebarPrerequisiteDiagnosticProjection(
                diagnostic_name=f"diagnostic-{index}",
                message=(
                    "Repository readiness remains unresolved and must stay inspectable "
                    "without moving the user-controlled sidebar scroll position. "
                )
                * 3,
                remediation="Inspect Environment and resolve the prerequisite.",
            )
            for index in range(18)
        )
        projection = SidebarProjection(
            benchmark_options=("Authority Resolution",),
            selected_benchmark="Authority Resolution",
            runner_options=("Codex CLI",),
            selected_runner="Codex CLI",
            prerequisite_diagnostics=diagnostics,
        )
        shell_preferences: dict[str, object] = {}
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            shell_preferences=shell_preferences,
            sidebar_projection=projection,
        )
        self.addCleanup(window.deleteLater)
        window.resize(1024, 640)
        window.show()
        QApplication.processEvents()

        self.assertEqual(window.sidebar_scroll.verticalScrollBar().value(), 0)
        selected_width = REFERENCE_SIDEBAR_WIDTH
        self.assertEqual(window.sidebar.width(), selected_width)
        self.assertNotIn(SHELL_SIDEBAR_WIDTH_KEY, shell_preferences)

        scroll_bar = window.sidebar_scroll.verticalScrollBar()
        self.assertGreater(scroll_bar.maximum(), 0)
        requested_scroll = min(120, scroll_bar.maximum())
        scroll_bar.setValue(requested_scroll)
        QApplication.processEvents()
        self.assertEqual(scroll_bar.value(), requested_scroll)

        window.resize(1180, 700)
        QApplication.processEvents()
        self.assertAlmostEqual(window.sidebar.width(), selected_width, delta=1)

        window.set_sidebar_projection(projection)
        QApplication.processEvents()
        self.assertAlmostEqual(window.sidebar.width(), selected_width, delta=1)
        self.assertEqual(
            window.sidebar_scroll.verticalScrollBar().value(),
            min(
                requested_scroll,
                window.sidebar_scroll.verticalScrollBar().maximum(),
            ),
        )

    def test_status_bar_projects_diagnostic_connectivity_and_application_identity(self) -> None:
        self.window.resize(REFERENCE_WINDOW_WIDTH, REFERENCE_WINDOW_HEIGHT)
        self.window.show()
        QApplication.processEvents()

        status_bar = self.window.shell_status_bar
        self.assertIs(self.window.centralWidget().layout().itemAt(0).widget(), self.window.vertical_splitter)
        self.assertIs(self.window.workspace_column.layout().itemAt(0).widget(), status_bar)
        self.assertEqual(status_bar.accessibleName(), "Application status")
        self.assertFalse(status_bar.isSizeGripEnabled())
        self.assertGreater(status_bar.mapTo(self.window, QPoint()).x(), self.window.sidebar_header.geometry().right())
        self.assertEqual(status_bar.mapTo(self.window, status_bar.rect().topRight()).x(), self.window.contentsRect().right())
        self.assertLess(
            status_bar.mapTo(self.window, status_bar.rect().bottomLeft()).y(),
            self.window.workspace_scroll.mapTo(self.window, QPoint()).y(),
        )

        self.assertEqual(self.window.connectivity_status.label, "Offline")
        self.assertEqual(self.window.connectivity_status.tone, "neutral")
        self.assertTrue(self.window.connectivity_status.icon_key)
        self.assertTrue(self.window.connectivity_status.icon_text)
        self.assertEqual(
            self.window.connectivity_status.authority_semantics,
            "presentation-only",
        )
        self.assertEqual(self.window.connectivity_status.accessibleName(), "No runner: Offline")
        self.assertEqual(
            self.window.connectivity_status.accessibleDescription(),
            "Connectivity status",
        )
        self.assertEqual(
            self.window.application_readiness_status.label,
            "Application status unavailable",
        )
        self.assertEqual(self.window.application_readiness_status.tone, "neutral")
        from AgMark.gui.widgets.status import StatusDropdownButton
        self.assertEqual(
            self.window.sidebar_header.findChildren(StatusDropdownButton),
            [self.window.connectivity_status],
        )
        console = self.window.console_widget
        console.set_active_tab("History")
        self.assertIn("Application status unavailable", console.state.visible_text)
        self.window.set_application_status("Ready", "success")
        self.window.set_application_status("Ready", "success")
        self.assertEqual(console.state.visible_text.count("] Ready\n"), 2)
        self.assertEqual(console.console_view("History").toPlainText(), console.state.visible_text)
        self.assertFalse(console.clear_button.isEnabled())
        console.clear_visible()
        self.assertEqual(console.state.visible_text.count("] Ready\n"), 2)
        console.set_active_tab("Diagnostics")
        self.assertTrue(console.clear_button.isEnabled())
        self.assertEqual(self.window.windowTitle(), WINDOW_TITLE)

        self.window.set_connectivity_status("Connected", "success")
        QApplication.processEvents()
        self.assertEqual(self.window.connectivity_status.label, "Connected")
        self.assertEqual(self.window.connectivity_status.tone, "success")
        self.assertEqual(self.window.authority_semantics, "presentation-only")

    def test_runner_status_displays_selected_name_and_preserves_icon_order(self) -> None:
        runners = ("arcgrav.mock-model.runner@1.0.0", "openai.codex-cli@1.0.0")
        self.window.show()
        QApplication.processEvents()
        badge = self.window.connectivity_status
        for runner, name, status, tone in (
            (runners[0], "Mock Model (Local Test)", "Connected", "success"),
            (runners[1], "OpenAI Codex CLI", "Checking connection", "active"),
            (runners[1], "OpenAI Codex CLI", "Runner unavailable", "error"),
            (None, "No runner", "Runner not selected", "neutral"),
        ):
            with self.subTest(runner=runner, status=status):
                self.window.set_runner_connectivity(SidebarProjection(
                    runner_options=runners, selected_runner=runner,
                    runner_connectivity=(status, tone, "Connection detail"),
                ))
                self.assertTrue(badge.displayed_label.endswith(status))
                if status == "Connected":
                    self.assertEqual(badge.displayed_label, f"{name}: {status}")
                self.assertEqual(badge.accessibleName(), f"{name}: {status}")
                self.assertEqual(badge.label, status)
                self.assertEqual(badge.tone, tone)
                self.assertFalse(badge.semantic_icon.isNull())
                self.assertEqual(badge.layoutDirection(), Qt.LayoutDirection.LeftToRight)
                self.assertIs(badge.menu(), self.window.runner_menu)
        self.window.set_runner_connectivity(SidebarProjection(
            runner_options=runners, selected_runner=runners[0],
            runner_connectivity=("Connected", "success", "Handshake succeeded"),
        ))
        self.window.set_connectivity_status("Offline", "warning")
        self.assertEqual(badge.displayed_label, "Mock Model (Local Test): Offline")

    def test_runner_menu_dismiss_switch_and_busy_gating(self) -> None:
        from PySide6.QtCore import QPoint
        checks, diagnostics = [], []
        runners = ("fixture.unsupported@1.0.0", "fixture.supported@1.0.0")
        projection = SidebarProjection(runner_options=runners, selected_runner=runners[0],
                                       model_visible=False, credentials_visible=False)
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            sidebar_projection=projection, on_check_runner=checks.append,
            on_test_runner=diagnostics.append, command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()
        self.assertEqual([a.text() for a in window.runner_menu.actions()], ["Test", "Check"])
        self.assertFalse(window.runner_test_action.isEnabled())
        self.assertTrue(window.runner_check_action.isEnabled())
        window.runner_menu.popup(window.connectivity_status.mapToGlobal(QPoint(0, 30)))
        QApplication.processEvents()
        self.assertTrue(window.runner_menu.isVisible())
        QTest.keyClick(window.runner_menu, Qt.Key.Key_Escape)
        QApplication.processEvents()
        self.assertFalse(window.runner_menu.isVisible())
        window.runner_menu.popup(window.connectivity_status.mapToGlobal(QPoint(0, 30)))
        QApplication.processEvents()
        self.assertTrue(window.runner_menu.isVisible())
        window.set_sidebar_projection(SidebarProjection(
            runner_options=runners, selected_runner=runners[1], runner_test_supported=True,
            model_visible=False, credentials_visible=False,
        ))
        QApplication.processEvents()
        self.assertFalse(window.runner_menu.isVisible())
        self.assertTrue(window.runner_test_action.isEnabled())
        self.assertIn("Fixture Supported:", window.connectivity_status.accessibleName())
        self.assertTrue(window.connectivity_status.text().endswith("Runner not checked"))
        window.set_operation_activity(("Checking runner",), lock_controls=True)
        self.assertFalse(window.runner_check_action.isEnabled())
        self.assertFalse(window.runner_test_action.isEnabled())
        window._invoke_check_runner()
        window._invoke_test_runner()
        self.assertEqual(checks, [])
        self.assertEqual(diagnostics, [])
        window.set_operation_activity((), lock_controls=False)
        self.assertTrue(window.runner_check_action.isEnabled())
        self.assertTrue(window.runner_test_action.isEnabled())
        window.runner_check_action.trigger()
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].runner, runners[1])
        window.set_sidebar_projection(SidebarProjection(runner_options=runners))
        self.assertFalse(window.runner_check_action.isEnabled())
        self.assertFalse(window.runner_test_action.isEnabled())

    def test_readiness_blockers_do_not_overwrite_connectivity_or_identity(self) -> None:
        blocker = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="runner-authentication",
            message="Runner authentication is unresolved.",
            remediation="Restore the configured authentication source.",
        )
        selected_runner = "fixture.runner@1"
        connected = ("Connected", "success", "Selected runner handshake succeeded.")
        blocked = SidebarProjection(
            runner_options=(selected_runner,), selected_runner=selected_runner,
            runner_connectivity=connected,
            build_plan_available=True,
            prerequisite_diagnostics=(blocker,),
        )
        window = BenchmarkShellWindow(
            application_icon=self.application_icon,
            connectivity_label="Ready",
            connectivity_tone="success",
            sidebar_projection=blocked,
            on_build_plan=lambda _snapshot: None,
            command_dispatcher=_inline_dispatch,
        )
        self.addCleanup(window.deleteLater)

        self.assertEqual(window.build_plan_button.role, "unavailable")
        self.assertFalse(window._sidebar_projection.build_plan_effectively_available)
        self.assertEqual(window.connectivity_status.label, "Ready")
        self.assertEqual(window.connectivity_status.tone, "success")
        self.assertEqual(
            window.application_readiness_status.label,
            "Prerequisites unresolved",
        )
        self.assertEqual(window.application_readiness_status.tone, "warning")
        self.assertEqual(window.windowTitle(), WINDOW_TITLE)

        window.set_connectivity_status("Connected", "success")
        window.set_application_status("Application ready", "success")
        self.assertEqual(window.connectivity_status.label, "Connected")
        self.assertEqual(window.connectivity_status.tone, "success")
        self.assertEqual(
            window.application_readiness_status.label,
            "Prerequisites unresolved",
        )
        self.assertEqual(window.application_readiness_status.tone, "warning")

        window.set_sidebar_projection(SidebarProjection(
            runner_options=(selected_runner,), selected_runner=selected_runner,
            runner_connectivity=connected, build_plan_available=True,
        ))
        self.assertEqual(window.build_plan_button.role, "primary")
        self.assertEqual(window.build_plan_button.icon_role, "plan-build")
        self.assertFalse(window.build_plan_button.icon().isNull())
        self.assertTrue(window._sidebar_projection.build_plan_effectively_available)
        self.assertEqual(window.connectivity_status.label, "Connected")
        self.assertEqual(window.connectivity_status.tone, "success")
        self.assertEqual(
            window.application_readiness_status.label,
            "Application ready",
        )
        self.assertEqual(window.application_readiness_status.tone, "success")
        self.assertEqual(window.windowTitle(), WINDOW_TITLE)

    def test_shell_rejects_invalid_local_presentation_inputs(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "application_icon must be a non-null QIcon",
        ):
            BenchmarkShellWindow(
                application_icon=QIcon(),
            )

        with self.assertRaisesRegex(ValueError, "console height must be positive"):
            self.window.set_console_height(0)
        with self.assertRaisesRegex(TypeError, "console height must be an integer"):
            self.window.set_console_height(True)

        with self.assertRaisesRegex(
            ValueError,
            "on_build_plan is required when build_plan_available is true",
        ):
            BenchmarkShellWindow(
                application_icon=self.application_icon,
                sidebar_projection=SidebarProjection(build_plan_available=True),
            )

        with self.assertRaisesRegex(
            ValueError,
            "selected_benchmark must be None or one of the supplied options",
        ):
            SidebarProjection(
                benchmark_options=("A",),
                selected_benchmark="B",
            )

        with self.assertRaisesRegex(
            ValueError,
            "operation must be one of planning, acceptance, or execution",
        ):
            SidebarPrerequisiteDiagnosticProjection(
                diagnostic_name="unsupported-scope",
                message="Unsupported scope.",
                remediation="Use a supported lifecycle scope.",
                operation="reporting",
            )

        retained_run = RetainedRunProjection(
            run_id="run-a",
            display_identity="Run A",
            state_label="Accepted",
            state_tone="success",
            timestamp="2026-09-21 14:00",
        )
        with self.assertRaisesRegex(
            ValueError,
            "retained_workspace_projections must cover exactly",
        ):
            BenchmarkShellWindow(
                application_icon=self.application_icon,
                sidebar_projection=SidebarProjection(runs=(retained_run,)),
                retained_workspace_projections={},
            )

        current_run = CurrentRunProjection(
            run_identity="Run A",
            state_label="Planned",
            state_tone="neutral",
            timestamp="2026-09-21 14:30",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="Authority Resolution",
                runner="Codex CLI",
                model="gpt-5.6",
                cases="24",
                boundary_fingerprint="sha256:caller-owned-boundary",
            ),
            run_plan=RunPlanProjection(
                treatments="Baseline",
                cases="24 cases",
                execution="1 repetition",
                evaluation="Exact",
                outputs="Accepted evidence",
            ),
            accept_plan_available=True,
        )
        with self.assertRaisesRegex(
            ValueError,
            "on_accept_plan is required when accept_plan_available is true",
        ):
            BenchmarkShellWindow(
                application_icon=self.application_icon,
                current_run_projection=current_run,
            )


if __name__ == "__main__":
    unittest.main()
