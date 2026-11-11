"""Rendered conformance for design-system stability across shell replacement."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS
from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    apply_application_theme,
    compact_splitter_handle_extent,
)
from AgMark.gui.design_system.typography import DEFAULT_TYPOGRAPHY
from AgMark.gui.shell.window import (
    BenchmarkShellWindow,
    CurrentRunProjection,
    ExecutionBoundaryProjection,
    NumericInputProjection,
    PYSIDE6_AVAILABLE,
    RunPlanProjection,
    SidebarProjection,
    WorkspaceProjection,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QFrame, QLabel, QStyle, QStyleOption


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class RenderedShellRuntimeReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])
        apply_application_theme(cls._application)

    def _window(self) -> BenchmarkShellWindow:
        icon_pixmap = QPixmap(16, 16)
        icon_pixmap.fill(QColor(DEFAULT_LIGHT_THEME.color("accent-primary")))
        window = BenchmarkShellWindow(
            application_icon=QIcon(icon_pixmap),
            sidebar_projection=SidebarProjection(
                benchmark_options=("benchmark-a",),
                selected_benchmark="benchmark-a",
                runner_options=("runner-a",),
                selected_runner="runner-a",
                model_options=("model-a",),
                selected_model="model-a",
                temperature=NumericInputProjection(
                    value=0.2,
                    minimum=0.0,
                    maximum=2.0,
                    step=0.1,
                    decimals=1,
                ),
                max_tokens=NumericInputProjection(
                    value=512,
                    minimum=1,
                    maximum=4096,
                    step=1,
                    decimals=0,
                ),
            ),
        )
        self.addCleanup(window.deleteLater)
        window.resize(1440, 1080)
        window.show()
        QApplication.processEvents()
        return window

    def _corner_color(self, widget) -> str:
        image = widget.grab().toImage()
        self.assertFalse(image.isNull())
        self.assertGreater(image.width(), 2)
        self.assertGreater(image.height(), 2)
        return image.pixelColor(1, 1).name().lower()

    def _styled_surface_corner_color(self, widget) -> str:
        pixmap = QPixmap(widget.size())
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        option = QStyleOption()
        option.initFrom(widget)
        widget.style().drawPrimitive(
            QStyle.PrimitiveElement.PE_Widget,
            option,
            painter,
            widget,
        )
        painter.end()
        image = pixmap.toImage()
        self.assertFalse(image.isNull())
        self.assertGreater(image.width(), 2)
        self.assertGreater(image.height(), 2)
        return image.pixelColor(1, 1).name().lower()

    def _assert_semantic_control_style(
        self,
        widget,
        *,
        expected_tokens: tuple[str, ...],
        style_owner=None,
    ) -> None:
        component = widget.property("arcgravSemanticComponent")
        self.assertIsInstance(component, str)
        self.assertTrue(component)
        style_source = style_owner or widget
        stylesheet = style_source.styleSheet().lower()
        self.assertTrue(stylesheet)
        for token in expected_tokens:
            self.assertIn(DEFAULT_LIGHT_THEME.color(token).lower(), stylesheet)

    def _assert_rendered_splitter_separator(
        self,
        handle,
        *,
        separator_axis: str,
    ) -> tuple[str, ...]:
        self.assertTrue(handle.isVisible())
        pixmap = handle.grab()
        image = pixmap.toImage()
        self.assertFalse(image.isNull())

        extent = compact_splitter_handle_extent()
        border_width = DEFAULT_LAYOUT_METRICS.metric("border-width")
        device_ratio = max(1.0, float(pixmap.devicePixelRatio()))
        expected_separator_pixels = max(1, round(border_width * device_ratio))
        expected_color = DEFAULT_LIGHT_THEME.color("border-default").lower()

        if separator_axis == "vertical":
            self.assertEqual(extent, handle.width())
            sample_y = image.height() // 2
            colors = tuple(
                image.pixelColor(x, sample_y).name().lower()
                for x in range(image.width())
            )
        elif separator_axis == "horizontal":
            self.assertEqual(extent, handle.height())
            sample_x = image.width() // 2
            colors = tuple(
                image.pixelColor(sample_x, y).name().lower()
                for y in range(image.height())
            )
        else:
            self.fail(f"unsupported separator axis: {separator_axis}")

        self.assertEqual(round(extent * device_ratio), len(colors))
        painted = tuple(
            index for index, color in enumerate(colors) if color == expected_color
        )
        self.assertEqual(expected_separator_pixels, len(painted))
        self.assertEqual(
            tuple(range(painted[0], painted[-1] + 1)),
            painted,
        )
        self.assertLessEqual(
            abs(((painted[0] + painted[-1]) / 2) - ((len(colors) - 1) / 2)),
            0.5,
        )
        self.assertTrue(any(color != expected_color for color in colors))
        return colors

    def test_console_splitter_and_fixed_sidebar_survive_replacement(self) -> None:
        window = self._window()

        initial_sidebar_width = window.sidebar.width()
        vertical_handle = window.vertical_splitter.handle(1)
        before_vertical = self._assert_rendered_splitter_separator(
            vertical_handle,
            separator_axis="horizontal",
        )

        window.set_sidebar_projection(
            SidebarProjection(
                benchmark_options=("benchmark-b",),
                selected_benchmark="benchmark-b",
                runner_options=("runner-b",),
                selected_runner="runner-b",
            )
        )
        QApplication.processEvents()

        after_vertical = self._assert_rendered_splitter_separator(
            vertical_handle,
            separator_axis="horizontal",
        )
        self.assertEqual(window.sidebar.width(), initial_sidebar_width)
        self.assertIs(window.upper_work_area.layout().itemAt(0).widget(), window.sidebar)
        self.assertEqual(before_vertical, after_vertical)

    def test_initial_shell_native_primitives_render_from_pre_show_application_theme(self) -> None:
        application = QApplication.instance()
        self.assertIsNotNone(application)
        assert application is not None
        self.assertIn("QFrame#benchmarkSidebar", application.styleSheet())
        self.assertIn("QStatusBar#shellStatusBar", application.styleSheet())
        self.assertTrue(application.property("arcgravDesignSystemActive"))
        self.assertEqual(
            DEFAULT_LIGHT_THEME.name,
            application.property("arcgravDesignSystemTheme"),
        )
        self.assertEqual(
            DEFAULT_TYPOGRAPHY.style("body").size_px,
            application.font().pixelSize(),
        )

        window = self._window()
        expected_panel = DEFAULT_LIGHT_THEME.color("surface-panel").lower()
        expected_background = DEFAULT_LIGHT_THEME.color(
            "surface-background"
        ).lower()
        section_style = DEFAULT_TYPOGRAPHY.style("section-heading")
        heading_style = DEFAULT_TYPOGRAPHY.style("workspace-title")
        body_style = DEFAULT_TYPOGRAPHY.style("body")

        for widget in (
            window.sidebar,
            window.sidebar_scroll,
            window.sidebar_scroll.viewport(),
            window.sidebar_content,
        ):
            self.assertEqual(expected_panel, self._corner_color(widget))

        self.assertEqual(
            DEFAULT_LIGHT_THEME.color("surface-status-bar").lower(),
            self._corner_color(window.shell_status_bar),
        )

        for widget in (
            window.upper_work_area,
            window.workspace,
            window.current_run_region,
        ):
            self.assertEqual(
                expected_background,
                self._styled_surface_corner_color(widget),
            )
        unavailable_page = window.workspace_pages["Progress"]
        self.assertIsNotNone(unavailable_page)
        assert unavailable_page is not None
        self.assertEqual("unavailable", unavailable_page.property("projectionState"))
        self.assertEqual(expected_background, self._corner_color(unavailable_page))

        sidebar_heading = window.sidebar.findChild(QLabel, "sidebarSectionHeading")
        current_run_heading = window.current_run_region.findChild(
            QLabel,
            "currentRunHeading",
        )
        unavailable_message = unavailable_page.findChild(
            QLabel,
            "workspaceEmptyStateMessage",
        )
        self.assertIsNotNone(sidebar_heading)
        self.assertIsNotNone(current_run_heading)
        self.assertIsNotNone(unavailable_message)
        assert sidebar_heading is not None
        assert current_run_heading is not None
        assert unavailable_message is not None
        self.assertEqual(section_style.size_px, sidebar_heading.font().pixelSize())
        self.assertEqual(heading_style.size_px, current_run_heading.font().pixelSize())
        self.assertEqual(body_style.size_px, unavailable_message.font().pixelSize())

        self._assert_rendered_splitter_separator(
            window.vertical_splitter.handle(1),
            separator_axis="horizontal",
        )

    def test_reference_shell_places_governed_icons_with_accessible_text_and_state(self) -> None:
        window = self._window()
        window.console_widget.set_expanded(True)
        QApplication.processEvents()

        def assert_button_icon(widget, *, role: str, accessible_name: str) -> None:
            self.assertEqual(role, widget.property("semanticIconRole"))
            self.assertEqual(accessible_name, widget.accessibleName())
            self.assertFalse(widget.icon().isNull())
            self.assertFalse(widget.icon().pixmap(18, 18).isNull())

        assert_button_icon(
            window.build_plan_button,
            role="plan-build",
            accessible_name="Build Plan",
        )
        assert_button_icon(
            window.console_widget.clear_button,
            role="clear",
            accessible_name="Clear console view",
        )
        assert_button_icon(
            window.console_widget.collapse_button,
            role="expand",
            accessible_name="Collapse console",
        )

        console_header_layout = window.console_widget.collapse_button.parentWidget().layout()
        self.assertIs(
            console_header_layout.itemAt(1).widget(),
            window.console_widget.console_title_label,
        )
        self.assertEqual(
            "Console",
            window.console_widget.console_title_label.accessibleName(),
        )

        for badge in (
            window.connectivity_status,
        ):
            self.assertFalse(badge.semantic_icon.isNull())
            self.assertTrue(badge.accessibleName())
            self.assertTrue(badge.icon_text)

        populated = CurrentRunProjection(
            run_identity="run-icon-placement",
            state_label="Prepared",
            state_tone="active",
            timestamp="2026-09-26T00:00:00Z",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="benchmark-a",
                runner="runner-a",
                model="model-a",
                cases="1",
                boundary_fingerprint="b" * 64,
            ),
            run_plan=RunPlanProjection(
                treatments="1",
                cases="1",
                execution="provider-free",
                evaluation="registered scorer",
                outputs="retained evidence",
            ),
        )
        window.set_current_run_projection(populated)
        QApplication.processEvents()

        self.assertIsNotNone(window.current_run_status)
        assert window.current_run_status is not None
        self.assertFalse(window.current_run_status.semantic_icon.isNull())
        self.assertEqual("Prepared", window.current_run_status.accessibleName())

        for card, role, accessible_name in (
            (
                window.execution_boundary_card,
                "current-run-boundary",
                "Execution Boundary",
            ),
            (
                window.run_plan_card,
                "current-run-plan",
                "Run Plan",
            ),
        ):
            self.assertIsNotNone(card)
            assert card is not None
            self.assertEqual(role, card.icon_role)
            self.assertEqual(accessible_name, card.accessibleName())
            icon_label = card.title_icon_label
            self.assertIsNotNone(icon_label)
            assert icon_label is not None
            self.assertEqual(role, icon_label.property("semanticIconRole"))
            self.assertFalse(icon_label.pixmap().isNull())

        self.assertIsNotNone(window.accept_plan_button)
        self.assertIsNotNone(window.start_benchmark_button)
        assert window.accept_plan_button is not None
        assert window.start_benchmark_button is not None
        assert_button_icon(
            window.accept_plan_button,
            role="plan-accept",
            accessible_name="Accept Plan",
        )
        assert_button_icon(
            window.start_benchmark_button,
            role="benchmark-start",
            accessible_name="Start Benchmark",
        )
        self.assertFalse(window.accept_plan_button.isEnabled())
        self.assertFalse(window.start_benchmark_button.isEnabled())

    def test_native_control_chrome_rejects_toolkit_default_fallback(self) -> None:
        window = self._window()

        input_tokens = (
            "surface-panel",
            "border-default",
            "text-primary",
            "focus-ring",
        )
        for control in (
            window.benchmark_input.combo_box,
            window.runner_input.combo_box,
            window.model_input.combo_box,
            window.credential_input.line_edit,
            window.temperature_input.spin_box,
            window.max_tokens_input.spin_box,
        ):
            self._assert_semantic_control_style(
                control,
                expected_tokens=input_tokens,
            )
            self.assertEqual(
                DEFAULT_TYPOGRAPHY.style("body").size_px,
                control.font().pixelSize(),
            )

        self._assert_semantic_control_style(
            window.credential_input.reveal_button,
            expected_tokens=input_tokens,
        )
        self.assertEqual(
            "credential-visibility",
            window.credential_input.reveal_button.property("semanticRole"),
        )

        self._assert_semantic_control_style(
            window.build_plan_button,
            expected_tokens=(
                "surface-panel",
                "border-default",
                "text-muted",
                "focus-ring",
            ),
        )
        self.assertEqual("unavailable", window.build_plan_button.role)

        chrome_tokens = (
            "surface-panel",
            "border-default",
            "text-secondary",
            "surface-selected",
            "focus-ring",
        )
        for control in (
            window.console_widget.clear_button,
            window.console_widget.collapse_button,
        ):
            self._assert_semantic_control_style(
                control,
                expected_tokens=chrome_tokens,
            )

        self._assert_semantic_control_style(
            window.workspace_tabs.tabBar(),
            style_owner=window.workspace_tabs,
            expected_tokens=("surface-panel", "text-primary", "accent-primary"),
        )
        self._assert_semantic_control_style(
            window.console_widget.tab_bar,
            expected_tokens=(
                "console-background",
                "console-muted",
                "console-text",
                "accent-primary",
            ),
        )

        window.set_sidebar_projection(
            SidebarProjection(
                benchmark_options=("benchmark-b",),
                selected_benchmark="benchmark-b",
                runner_options=("runner-b",),
                selected_runner="runner-b",
                model_options=("model-b",),
                selected_model="model-b",
            )
        )
        QApplication.processEvents()
        self._assert_semantic_control_style(
            window.credential_input.reveal_button,
            expected_tokens=input_tokens,
        )

        populated = CurrentRunProjection(
            run_identity="run-native-chrome",
            state_label="Prepared",
            state_tone="active",
            timestamp="2026-09-26T00:00:00Z",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="benchmark-b",
                runner="runner-b",
                model="model-b",
                cases="1",
                boundary_fingerprint="c" * 64,
            ),
            run_plan=RunPlanProjection(
                treatments="1",
                cases="1",
                execution="provider-free",
                evaluation="registered scorer",
                outputs="retained evidence",
            ),
        )
        window.set_current_run_projection(populated)
        QApplication.processEvents()
        self.assertIsNotNone(window.accept_plan_button)
        self.assertIsNotNone(window.start_benchmark_button)
        assert window.accept_plan_button is not None
        assert window.start_benchmark_button is not None
        for control in (window.accept_plan_button, window.start_benchmark_button):
            self._assert_semantic_control_style(
                control,
                expected_tokens=(
                    "surface-panel",
                    "border-default",
                    "text-muted",
                    "focus-ring",
                ),
            )
            self.assertEqual("unavailable", control.role)

    def test_runtime_replacement_preserves_effective_shell_design_system(self) -> None:
        window = self._window()
        window.workspace_tabs.set_selected_index(5)
        window.console_widget.set_active_tab("Environment")
        environment_text = "[READY] Environment preserved across shell replacement"
        window.console_widget.set_environment(environment_text)
        QApplication.processEvents()

        expected_panel = DEFAULT_LIGHT_THEME.color("surface-panel").lower()
        expected_background = DEFAULT_LIGHT_THEME.color(
            "surface-background"
        ).lower()
        expected_console = DEFAULT_LIGHT_THEME.color("console-background").lower()
        section_style = DEFAULT_TYPOGRAPHY.style("section-heading")
        heading_style = DEFAULT_TYPOGRAPHY.style("workspace-title")
        console_title_style = DEFAULT_TYPOGRAPHY.style("card-heading")

        console_header = window.console_widget.console_title_label.parentWidget()
        self.assertIsNotNone(console_header)
        assert console_header is not None
        self.assertEqual(expected_panel, self._corner_color(console_header))
        self.assertEqual(
            console_title_style.size_px,
            window.console_widget.console_title_label.font().pixelSize(),
        )
        environment_view = window.console_widget.console_view("Environment")
        self.assertEqual(expected_console, self._corner_color(environment_view.viewport()))
        self.assertEqual(environment_text, environment_view.toPlainText())

        initial_sidebar = window.sidebar
        initial_sidebar_color = self._corner_color(initial_sidebar)
        self.assertEqual(expected_panel, initial_sidebar_color)

        window.set_sidebar_projection(
            SidebarProjection(
                benchmark_options=("benchmark-b",),
                selected_benchmark="benchmark-b",
                runner_options=("runner-b",),
                selected_runner="runner-b",
            )
        )
        QApplication.processEvents()

        self.assertIsNot(initial_sidebar, window.sidebar)
        self.assertEqual("benchmarkSidebar", window.sidebar.objectName())
        self.assertEqual(expected_panel, self._corner_color(window.sidebar))
        sidebar_heading = window.sidebar.findChild(QLabel, "sidebarSectionHeading")
        self.assertIsNotNone(sidebar_heading)
        assert sidebar_heading is not None
        self.assertEqual(section_style.size_px, sidebar_heading.font().pixelSize())

        populated = CurrentRunProjection(
            run_identity="run-rendered-replacement",
            state_label="Prepared",
            state_tone="active",
            timestamp="2026-09-25T12:00:00Z",
            execution_boundary=ExecutionBoundaryProjection(
                benchmark="benchmark-b",
                runner="runner-b",
                model="model-b",
                cases="1",
                boundary_fingerprint="a" * 64,
            ),
            run_plan=RunPlanProjection(
                treatments="1",
                cases="1",
                execution="provider-free",
                evaluation="registered scorer",
                outputs="retained evidence",
            ),
        )
        previous_current_run = window.current_run_region
        window.set_current_run_projection(populated)
        QApplication.processEvents()

        self.assertIsNot(previous_current_run, window.current_run_region)
        self.assertEqual("currentRunRegion", window.current_run_region.objectName())
        self.assertEqual(
            expected_background,
            self._corner_color(window.current_run_region),
        )
        current_run_heading = window.current_run_region.findChild(
            QLabel,
            "currentRunHeading",
        )
        self.assertIsNotNone(current_run_heading)
        assert current_run_heading is not None
        self.assertEqual(
            heading_style.size_px,
            current_run_heading.font().pixelSize(),
        )

        pages = tuple(QFrame() for _ in range(5))
        for page in pages:
            page.setProperty("projectionState", "unavailable")
        projection = WorkspaceProjection(*pages)
        window.set_workspace_projection(
            projection,
            run_id="run-rendered-replacement",
        )
        QApplication.processEvents()

        self.assertEqual("Reports", window.workspace_tabs.selected_label)
        self.assertEqual(
            "Environment",
            window.console_widget.state.active_tab,
        )
        self.assertEqual(environment_text, window.console_widget.state.visible_text)
        self.assertEqual(environment_text, environment_view.toPlainText())
        self.assertEqual(expected_panel, self._corner_color(console_header))
        self.assertEqual(expected_console, self._corner_color(environment_view.viewport()))
        for page in pages:
            self.assertEqual(expected_background, self._corner_color(page))

        fallback = QFrame()
        self.addCleanup(fallback.deleteLater)
        fallback.setAutoFillBackground(True)
        fallback.resize(80, 40)
        fallback.show()
        QApplication.processEvents()
        self.assertNotEqual(expected_panel, self._corner_color(fallback))


if __name__ == "__main__":
    unittest.main()
