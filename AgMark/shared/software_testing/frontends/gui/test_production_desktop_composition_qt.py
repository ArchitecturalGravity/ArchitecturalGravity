"""Production desktop repository-authority composition coverage."""

from __future__ import annotations

from dataclasses import dataclass, replace
import base64
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui import startup
from AgMark.gui.application import BenchmarkDesktopApplication
from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS
from AgMark.gui.design_system.tabs import DEFAULT_TAB_STYLES
from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    apply_application_theme,
    arcgrav_application_icon,
)
from AgMark.gui.design_system.typography import DEFAULT_TYPOGRAPHY
from AgMark.gui.composition import (
    compose_repository_planning_session,
    discover_repository_application_authority,
)
from AgMark.gui.request_resolution import RepositoryApplicationRequestResolver
from AgMark.gui.readiness import probe_registered_runner_model_discovery
from AgMark.gui.shell.window import (
    PYSIDE6_AVAILABLE,
    WORKSPACE_TAB_LABELS,
    SidebarControlInputSnapshot,
    SidebarInputSnapshot,
    WorkspaceProjection,
)
from AgMark.gui.views.progress import ProgressEventProjection, ProgressView
from AgMark.gui.workspace_projection import SharedWorkspaceProjector
from AgMark.shared.runtime.orchestration import AcceptedRun, BlockedRun
from AgMark.shared.adapters.execution import validate_retained_parity_observation
from AgMark.shared.adapters.Mock_Model import MockRunner

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy, QStyle, QWidget


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_SECRET_HANDLING = "arcgrav.adapters:secret_handling"
_ACCESS_METHODS = "arcgrav.adapters:access_methods"


def _registration_labels(values: tuple[object, ...]) -> tuple[str, ...]:
    labels: list[str] = []
    for value in values:
        registration = getattr(value, "registration", None)
        if isinstance(registration, dict):
            labels.append(
                f"{registration['registration_id']}@"
                f"{registration['registration_version']}"
            )
            continue
        labels.append(
            f"{value.registration_id}@{value.registration_version}"
        )
    return tuple(labels)


def _source_label(source: object) -> str:
    registration = source.registration
    return f"{registration['registration_id']}@{registration['registration_version']}"


def _provider_free_source(authority: object) -> object:
    return next(
        source
        for source in authority.runner_sources
        if source.registration.get("registration_id") == "arcgrav.mock-model.runner"
    )


def _credential_cli_source(authority: object) -> object:
    for source in authority.runner_sources:
        if source.registration.get("registration_id") == "openai.codex-cli":
            return source
    raise AssertionError(
        "expected admitted openai.codex-cli runner; "
        f"admitted={_registration_labels(authority.runner_sources)!r}; "
        f"repository_diagnostics={authority.repository_diagnostics!r}"
    )

def _offline_codex_model_discovery() -> dict[str, object]:
    return {
        "status": "ready",
        "provider_submitted": False,
        "effective_default_model_id": "gpt-5.6",
        "selectable_model_ids": ["gpt-5.6", "gpt-5.6-mini"],
        "choices": [
            {
                "model_id": "gpt-5.6",
                "selection_mode": "explicit",
                "label": "Default (GPT-5.6)",
                "reasoning_efforts": [{"value": "medium", "description": "Balanced"}, {"value": "high", "description": "More reasoning"}],
                "default_reasoning_effort": "medium",
            },
            {
                "model_id": "gpt-5.6-mini",
                "selection_mode": "explicit",
                "label": "GPT-5.6 Mini",
                "reasoning_efforts": [{"value": "low", "description": "Faster"}, {"value": "medium", "description": "Balanced"}],
                "default_reasoning_effort": "low",
            },
        ],
        "resolved_configuration": {
            "wsl_user": "gunnanmon",
            "codex_home": "/home/gunnanmon/.codex",
        },
    }


def _ready_discovery_for_source(source, controls=None):
    """Use real registered mock discovery, never the developer's live CLI.

    Switching the desktop to a live runner still tests control projection, but
    must not launch an installed Codex app-server or access external services.
    """
    if source.registration["registration_id"] == "arcgrav.mock-model.runner":
        return probe_registered_runner_model_discovery(
            source, repository_root=_REPOSITORY_ROOT,
            selected_control_values=dict(controls or {}),
        )
    if source.registration["registration_id"] == "openai.codex-cli":
        return _offline_codex_model_discovery()
    raise AssertionError("No offline discovery fixture for this registered adapter")


@dataclass(frozen=True)
class _FullClientRenderFixture:
    state: str
    window_size: tuple[int, int]
    sidebar_rect: tuple[int, int, int, int]
    current_run_rect: tuple[int, int, int, int]
    workspace_rect: tuple[int, int, int, int]
    console_rect: tuple[int, int, int, int]
    status_rect: tuple[int, int, int, int]


class _InertResolver:
    """Satisfy the composition interface without supplying lifecycle authority."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _unexpected(self, name: str):
        self.calls.append(name)
        raise AssertionError(
            f"repository discovery or blocked action must not invoke resolver method {name}"
        )

    def resolve_plan_request(self, *args, **kwargs):
        return self._unexpected("resolve_plan_request")

    def resolve_execution_request(self, *args, **kwargs):
        return self._unexpected("resolve_execution_request")

    def resolve_report_request(self, *args, **kwargs):
        return self._unexpected("resolve_report_request")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ProductionDesktopRepositoryCompositionTests(unittest.TestCase):
    def test_mock_discovery_fixture_preserves_its_declared_controls(self):
        source = SimpleNamespace(registration={"registration_id": "arcgrav.mock-model.runner"})
        controls = {"model_id": "mock-base", "request_timeout_ms": 2500, "maximum_attempts": 1}
        # The mock discovery fixture forwards only its own configuration.
        # Provider-free lifecycle coverage below invokes its registered adapter.
        with patch(__name__ + ".probe_registered_runner_model_discovery", return_value={"status": "ready"}) as probe:
            self.assertEqual({"status": "ready"}, _ready_discovery_for_source(source, controls))
        self.assertEqual(controls, probe.call_args.kwargs["selected_control_values"])
        self.assertEqual(2500, controls["request_timeout_ms"])

    def setUp(self):
        from AgMark.shared.software_testing.frontends.gui.isolated_repository import isolate_repository
        isolate_repository(self, "_REPOSITORY_ROOT")

    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def _activate_application_theme(self) -> None:
        application = self._application
        previous_palette = application.palette()
        previous_font = application.font()
        previous_sheet = application.styleSheet()
        previous_active = application.property("arcgravDesignSystemActive")
        previous_theme = application.property("arcgravDesignSystemTheme")

        self.addCleanup(
            application.setProperty,
            "arcgravDesignSystemTheme",
            previous_theme,
        )
        self.addCleanup(
            application.setProperty,
            "arcgravDesignSystemActive",
            previous_active,
        )
        def restore_visual_setting(getter, setter, value):
            # Window cleanups schedule deleteLater before theme restoration.
            # Without an outer event loop, those large report trees still exist
            # and a global style change needlessly lays them out again.
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            if getter() != value:
                setter(value)

        self.addCleanup(restore_visual_setting, application.styleSheet, application.setStyleSheet, previous_sheet)
        self.addCleanup(restore_visual_setting, application.font, application.setFont, previous_font)
        self.addCleanup(restore_visual_setting, application.palette, application.setPalette, previous_palette)
        apply_application_theme(application)

    def _assert_all_workspace_pages_use_projected_authority(self, window, generation_id):
        selected = window.workspace_tabs.currentIndex()
        window.activateWindow()
        for index, name in enumerate(WORKSPACE_TAB_LABELS):
            window.workspace_tabs.setCurrentIndex(index)
            QApplication.processEvents()
            page = window.workspace_pages[name]
            self.assertEqual(generation_id, page.run_id)
            self.assertEqual("presentation-only", page.authority_semantics)
            self.assertIsNone(page.findChild(QLabel, "workspaceEmptyStateMessage"))
            self.assertTrue(page.isVisible())
            self.assertFalse(page.grab().isNull())
            table = getattr(page, "table", getattr(page, "treatment_table", None))
            if table is not None and table.isVisible():
                self.assertTrue(table.accessibleName())
                self.assertNotEqual(Qt.FocusPolicy.NoFocus, table.focusPolicy())
                table.setFocus()
                QApplication.processEvents()
                self.assertTrue(table.hasFocus())
                if table.table_model.rowCount():
                    QTest.keyClick(table, Qt.Key.Key_Down)
                    self.assertTrue(table.currentIndex().isValid())
                    # Status meaning has readable text independent of color.
                    columns = [column.label for column in table.columns]
                    if "Status" in columns:
                        status = table.table_model.data(table.table_model.index(0, columns.index("Status")), int(Qt.ItemDataRole.DisplayRole))
                        self.assertTrue(str(status).strip())
            for action_name in ("expand_button", "export_button"):
                action = getattr(page, action_name, None)
                if action is not None:
                    self.assertTrue(action.text().strip())
                    if action.isEnabled():
                        action.setFocus()
                        self.assertTrue(action.hasFocus())
                        QTest.keyClick(action, Qt.Key.Key_Tab)
                        self.assertFalse(action.hasFocus())
            if name == "Evidence":
                for row in page.projection.artifacts.rows:
                    retained_file = bool(row.reference and row.reference.startswith(page.run_id + "/"))
                    self.assertEqual(row.open_action.available, retained_file)
                    self.assertEqual(row.reveal_action.available, retained_file)
                    if not retained_file:
                        self.assertTrue(row.open_action.unavailable_reason)
        window.workspace_tabs.setCurrentIndex(selected)
        QApplication.processEvents()

    def _assert_render_contains_color(self, widget: QWidget, expected: str) -> None:
        image = widget.grab().toImage()
        self.assertFalse(image.isNull())
        self.assertGreater(image.width(), 0)
        self.assertGreater(image.height(), 0)

        target = expected.lower()
        step_x = max(1, image.width() // 64)
        step_y = max(1, image.height() // 64)
        self.assertTrue(
            any(
                image.pixelColor(x, y).name().lower() == target
                for y in range(0, image.height(), step_y)
                for x in range(0, image.width(), step_x)
            ),
            f"rendered widget did not contain expected color {expected}",
        )

    def _assert_retained_model_outputs(self, window, retained) -> None:
        visible = window.console_widget.state.visible_text
        self.assertEqual(len(retained.treatment_observations), visible.count("Output:\n"))
        for raw in retained.treatment_observations:
            observation = raw if isinstance(raw, dict) else json.loads(raw)
            responses = [value for key, value in observation["extensions"].items()
                         if key.endswith(":response_base64")]
            self.assertEqual(1, len(responses))
            response = base64.b64decode(responses[0], validate=True).decode("utf-8")
            self.assertIn(observation["treatment_id"] + " - Output:\n" + response, visible)

    def _widget_rect_in_window(
        self,
        window: object,
        widget: QWidget,
    ) -> tuple[int, int, int, int]:
        origin = widget.mapTo(window, widget.rect().topLeft())
        return origin.x(), origin.y(), widget.width(), widget.height()

    def _assert_full_shell_semantic_contract(
        self,
        window: object,
        *,
        run_summary_name: str = "Current Run",
    ) -> None:
        semantic_regions = (
            (
                window.upper_work_area,
                "upperWorkArea",
                "Benchmark work area",
            ),
            (
                window.sidebar,
                "benchmarkSidebar",
                "Benchmark configuration and runs",
            ),
            (
                window.workspace,
                "benchmarkWorkspace",
                "Benchmark workspace",
            ),
            (
                window.current_run_region,
                "currentRunRegion",
                run_summary_name,
            ),
            (
                window.console_widget,
                "bottomConsole",
                "Bottom console",
            ),
            (
                window.shell_status_bar,
                "shellStatusBar",
                "Application status",
            ),
        )
        for widget, object_name, accessible_name in semantic_regions:
            with self.subTest(shell_region=object_name):
                self.assertEqual(object_name, widget.objectName())
                self.assertEqual(accessible_name, widget.accessibleName())

        self.assertEqual(
            "workspaceConsoleSplitter",
            window.vertical_splitter.objectName(),
        )
        self.assertEqual(
            "benchmarkSidebarScroll",
            window.sidebar_scroll.objectName(),
        )
        self.assertEqual(
            "benchmarkSidebarContent",
            window.sidebar_content.objectName(),
        )

        application = QApplication.instance()
        self.assertIsNotNone(application)
        assert application is not None
        application_style = application.styleSheet()
        for selector in (
            "QWidget#upperWorkArea",
            "QFrame#benchmarkWorkspace",
            "QFrame#currentRunRegion",
            "QFrame#benchmarkSidebar",
            "QScrollArea#benchmarkSidebarScroll",
            "QWidget#benchmarkSidebarContent",
            "QStatusBar#shellStatusBar",
            "QSplitter#workspaceConsoleSplitter::handle",
        ):
            with self.subTest(shell_selector=selector):
                self.assertIn(selector, application_style)

        self._assert_reference_workspace_tab_chrome(window)

    def _capture_full_client_render_fixture(
        self,
        window: object,
        *,
        state: str,
    ) -> _FullClientRenderFixture:
        # These fixtures inspect expanded console chrome; startup defaults have
        # separate no-flash coverage in test_ui_defaults_qt.
        window.console_widget.set_expanded(True)
        QApplication.processEvents()
        self.assertEqual((1440, 1080), (window.width(), window.height()))

        full_client = window.grab()
        self.assertFalse(full_client.isNull())
        full_image = full_client.toImage()
        self.assertFalse(full_image.isNull())
        self.assertGreater(full_image.width(), 0)
        self.assertGreater(full_image.height(), 0)

        application = QApplication.instance()
        self.assertIsNotNone(application)
        assert application is not None
        self.assertTrue(application.property("arcgravDesignSystemActive"))
        self.assertEqual(
            DEFAULT_LIGHT_THEME.name,
            application.property("arcgravDesignSystemTheme"),
        )
        self._assert_full_shell_semantic_contract(
            window,
            run_summary_name=(
                "Prior Run" if state == "retained-run" else "Current Run"
            ),
        )
        self._assert_icon_matches_arcgrav_application_identity(window.windowIcon())
        self.assertEqual(
            "Architectural Gravity Benchmark",
            window.windowTitle(),
        )

        for token in (
            "surface-background",
            "surface-panel",
            "console-background",
        ):
            with self.subTest(state=state, semantic_token=token):
                self._assert_render_contains_color(
                    window,
                    DEFAULT_LIGHT_THEME.color(token),
                )

        self._assert_render_contains_color(
            window.sidebar,
            DEFAULT_LIGHT_THEME.color("surface-panel"),
        )
        self._assert_render_contains_color(
            window.current_run_region,
            DEFAULT_LIGHT_THEME.color("surface-background"),
        )
        self._assert_render_contains_color(
            window.workspace,
            DEFAULT_LIGHT_THEME.color("surface-background"),
        )
        console_view = window.console_widget.console_view(
            window.console_widget.state.active_tab
        )
        self._assert_render_contains_color(
            console_view.viewport(),
            DEFAULT_LIGHT_THEME.color("console-background"),
        )
        self._assert_render_contains_color(
            window.shell_status_bar,
            DEFAULT_LIGHT_THEME.color("surface-status-bar"),
        )

        fixture = _FullClientRenderFixture(
            state=state,
            window_size=(window.width(), window.height()),
            sidebar_rect=self._widget_rect_in_window(window, window.sidebar),
            current_run_rect=self._widget_rect_in_window(
                window,
                # Compare shell regions, not the summary's scrollable child:
                # a visible vertical scrollbar legitimately narrows that child.
                window.current_run_scroll,
            ),
            workspace_rect=self._widget_rect_in_window(
                window,
                window.workspace_tabs,
            ),
            console_rect=self._widget_rect_in_window(
                window,
                window.console_widget,
            ),
            status_rect=self._widget_rect_in_window(
                window,
                window.shell_status_bar,
            ),
        )

        for region_name, rect in (
            ("sidebar", fixture.sidebar_rect),
            ("current-run", fixture.current_run_rect),
            ("workspace", fixture.workspace_rect),
            ("console", fixture.console_rect),
            ("status", fixture.status_rect),
        ):
            with self.subTest(state=state, region=region_name):
                x, y, width, height = rect
                self.assertGreater(width, 0)
                self.assertGreater(height, 0)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + width, window.width() + 1)
                self.assertLessEqual(y + height, window.height() + 1)

        sidebar_width = fixture.sidebar_rect[2]
        console_height = fixture.console_rect[3]
        active_workspace_page = window.workspace_tabs.currentWidget()
        geometry_diagnostic = (
            f"state={state!r}; sidebar_width={window.sidebar.width()}; "
            f"upper_width={window.upper_work_area.width()}; "
            f"workspace_min={window.workspace.minimumSizeHint().width()}; "
            f"tabs_min={window.workspace_tabs.minimumSizeHint().width()}; "
            f"page_min="
            f"{active_workspace_page.minimumSizeHint().width() if active_workspace_page is not None else None}"
        )
        self.assertEqual(sidebar_width, 300, geometry_diagnostic)
        self.assertGreaterEqual(console_height, 220)
        self.assertLessEqual(console_height, 280)
        self.assertEqual(
            0,
            window.sidebar_scroll.horizontalScrollBar().maximum(),
            "reference sidebar workflow must not require horizontal scrolling",
        )

        current_x, _current_y, current_width, _current_height = (
            fixture.current_run_rect
        )
        workspace_x, _workspace_y, workspace_width, _workspace_height = (
            fixture.workspace_rect
        )
        self.assertLessEqual(abs(current_x - workspace_x), 1)
        self.assertLessEqual(
            abs(
                (current_x + current_width)
                - (workspace_x + workspace_width)
            ),
            1,
        )

        console_x, _console_y, console_width, _console_height = fixture.console_rect
        status_x, status_y, status_width, status_height = fixture.status_rect
        self.assertLessEqual(abs(console_x), 1)
        self.assertLessEqual(abs(console_width - window.width()), 1)
        self.assertGreater(status_x, window.sidebar_header.geometry().right())
        self.assertLessEqual(abs(status_x + status_width - window.width()), 1)
        self.assertLessEqual(
            abs(status_y),
            1,
        )
        self.assertIs(window.centralWidget().layout().itemAt(0).widget(), window.vertical_splitter)
        self.assertLessEqual(
            status_y + status_height,
            window.workspace_scroll.mapTo(window, window.workspace_scroll.rect().topLeft()).y(),
        )
        return fixture

    def _assert_full_client_fixture_continuity(
        self,
        before: _FullClientRenderFixture,
        after: _FullClientRenderFixture,
    ) -> None:
        self.assertNotEqual(
            before.state,
            after.state,
            "state-matched continuity must compare distinct lifecycle captures",
        )
        self.assertEqual(before.window_size, after.window_size)
        self.assertEqual(before.sidebar_rect, after.sidebar_rect)
        self.assertEqual(before.console_rect, after.console_rect)
        self.assertEqual(before.status_rect, after.status_rect)
        self.assertEqual(before.current_run_rect[0], after.current_run_rect[0])
        self.assertEqual(before.current_run_rect[2], after.current_run_rect[2])
        self.assertEqual(before.workspace_rect[0], after.workspace_rect[0])
        self.assertEqual(before.workspace_rect[2], after.workspace_rect[2])

    def _assert_icon_matches_arcgrav_application_identity(self, icon: QIcon) -> None:
        self.assertFalse(icon.isNull())
        actual = icon.pixmap(32, 32).toImage()
        expected = arcgrav_application_icon().pixmap(32, 32).toImage()
        self.assertFalse(actual.isNull())
        self.assertEqual(expected, actual)

        rendered_colors = {
            actual.pixelColor(x, y).name().upper()
            for x in range(actual.width())
            for y in range(actual.height())
            if actual.pixelColor(x, y).alpha() > 0
        }
        for token in (
            "text-primary",
            "console-info",
            "surface-panel",
            "accent-primary",
        ):
            with self.subTest(token=token):
                self.assertIn(DEFAULT_LIGHT_THEME.color(token), rendered_colors)

        stock_images = {}
        for name, standard_pixmap in (
            ("computer", QStyle.StandardPixmap.SP_ComputerIcon),
            ("file", QStyle.StandardPixmap.SP_FileIcon),
            ("information", QStyle.StandardPixmap.SP_MessageBoxInformation),
        ):
            stock_icon = self._application.style().standardIcon(standard_pixmap)
            if not stock_icon.isNull():
                stock_images[name] = stock_icon.pixmap(32, 32).toImage()

        self.assertTrue(stock_images, "Qt style must expose at least one stock icon")
        for name, image in stock_images.items():
            with self.subTest(stock=name):
                self.assertNotEqual(
                    actual,
                    image,
                    "ArcGrav application identity must not be a Qt stock fallback",
                )

    def _compose(self, resolver: _InertResolver, **kwargs):
        kwargs.setdefault("authentication_probe", lambda *_args: True)
        kwargs.setdefault("model_discovery_probe", _ready_discovery_for_source)
        application = BenchmarkDesktopApplication.from_repository_authority(
            application_icon=QIcon(QPixmap(1, 1)),
            request_resolver=resolver,
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
            **kwargs,
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        QApplication.processEvents()
        return application

    def _compose_repository_session(
        self,
        resolver: _InertResolver,
        *,
        readiness_repository_root: Path | None = None,
        **kwargs,
    ):
        kwargs.setdefault("authentication_probe", lambda *_args: True)
        kwargs.setdefault("model_discovery_probe", _ready_discovery_for_source)
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        application = BenchmarkDesktopApplication.from_planning_session(
            application_icon=QIcon(QPixmap(1, 1)),
            session=composition.session,
            request_resolver=resolver,
            runner_sources=composition.authority.runner_sources,
            benchmark_candidates=composition.authority.benchmark_candidates,
            repository_root=(
                composition.authority.repository_root
                if readiness_repository_root is None
                else readiness_repository_root
            ),
            authority_dispatcher=lambda operation: operation(),
            **kwargs,
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        QApplication.processEvents()
        return application, composition.authority

    def _select_benchmark(self, application: object, benchmark_label: str) -> None:
        if application.window.benchmark_input.value != benchmark_label:
            application.window.benchmark_input.set_value(benchmark_label)
            QApplication.processEvents()
        self.assertEqual(benchmark_label, application.window.benchmark_input.value)

    def _select_runner(self, application: object, runner_label: str) -> None:
        if application.window.runner_input.value != runner_label:
            application.window.runner_input.set_value(runner_label)
            QApplication.processEvents()
        self.assertEqual(runner_label, application.window.runner_input.value)

    def _select_native_launch(self, application: object) -> None:
        launch = application.window.additional_control_inputs["launch_mode"]
        if launch.value != "native":
            launch.set_value("native")
            QApplication.processEvents()
        self.assertEqual("native", launch.value)

    def _assert_mock_configuration(self, application: object) -> None:
        window = application.window
        self.assertEqual(
            {"request_timeout_ms"},
            set(window.additional_control_inputs),
        )
        self.assertEqual({}, window.resolved_configuration_inputs)
        self.assertIsNone(window.reasoning_input)

    def _select_mock_scenario(self, application: object, scenario: str) -> None:
        window = application.window
        choices = {
            value.model_value: value
            for value in window._scenario_choice_by_label.values()
        }
        model_id = f"mock-base::scenario:{scenario}"
        self.assertIn(model_id, choices, application.environment_projection.render())
        choice = choices[model_id]
        window.scenario_input.set_value(choice.scenario_label)
        QApplication.processEvents()
        self.assertEqual(choice.model_value, window.sidebar_input_snapshot().model)

    def _assert_reference_workspace_tab_chrome(self, window: object) -> None:
        tabs = window.workspace_tabs
        tab_bar = tabs.tabBar()
        self.assertEqual(WORKSPACE_TAB_LABELS, tabs.labels)
        self.assertEqual(len(WORKSPACE_TAB_LABELS), tabs.count())
        self.assertEqual("tab-widget", tabs.property("arcgravSemanticComponent"))
        self.assertEqual("tab-bar", tab_bar.property("arcgravSemanticComponent"))
        self.assertFalse(tab_bar.drawBase())

        selected_style = DEFAULT_TAB_STYLES.resolve(
            "selected",
            theme=DEFAULT_LIGHT_THEME,
            metrics=DEFAULT_LAYOUT_METRICS,
            typography=DEFAULT_TYPOGRAPHY,
        )
        self.assertIsNotNone(selected_style.underline_color)
        self.assertIsNotNone(selected_style.underline_width_px)
        style_sheet = tabs.styleSheet()
        self.assertIn(
            'QTabWidget[arcgravSemanticComponent="tab-widget"]::pane {border: 0;}',
            style_sheet,
        )
        self.assertIn(
            (
                f"border-bottom: {selected_style.underline_width_px}px solid "
                f"{selected_style.underline_color};"
            ),
            style_sheet,
        )

        for index, label in enumerate(WORKSPACE_TAB_LABELS):
            self.assertEqual(label, tabs.tabText(index))
            self.assertTrue(tab_bar.isTabVisible(index))
            tab_rect = tab_bar.tabRect(index)
            self.assertTrue(tab_rect.isValid())
            self.assertGreater(tab_rect.width(), 0)
            self.assertGreater(tab_rect.height(), 0)
            self.assertTrue(tab_bar.rect().intersects(tab_rect))

        selected_page = tabs.currentWidget()
        self.assertIsNotNone(selected_page)
        page_top = selected_page.mapTo(
            tabs,
            selected_page.rect().topLeft(),
        ).y()
        tab_bottom = tab_bar.mapTo(
            tabs,
            tab_bar.rect().bottomLeft(),
        ).y()
        self.assertGreaterEqual(page_top, tab_bottom)
        self.assertLessEqual(page_top - tab_bottom, 2)

    def _assert_unavailable_progress_workspace(self, window: object) -> QWidget:
        self._assert_reference_workspace_tab_chrome(window)
        self.assertIsNone(window.workspace_projection_run_id)
        page = window.workspace_pages["Progress"]
        self.assertEqual("unavailable", page.property("projectionState"))
        self.assertTrue(page.isVisible())
        self.assertGreater(page.width(), 0)
        self.assertGreater(page.height(), 0)
        self.assertFalse(page.grab().isNull())
        return page

    def test_repository_authority_factory_runs_real_discovery_without_resolver_fallback(
        self,
    ) -> None:
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        self.assertTrue(
            authority.discovery.benchmarks,
            "production desktop composition requires real benchmark authority",
        )
        self.assertTrue(
            authority.discovery.runners,
            "production desktop composition requires real runner authority",
        )
        resolver = _InertResolver()
        application = self._compose(resolver)

        boundary = application.shared_application_boundary
        self.assertEqual(authority.discovery, boundary.discovery)
        self.assertEqual(
            _registration_labels(authority.discovery.benchmarks),
            application.window.benchmark_input.options,
        )
        self.assertEqual(
            _registration_labels(authority.discovery.runners),
            application.window.runner_input.options,
        )
        self.assertEqual([], resolver.calls)

    def test_archive_import_is_callable_and_history_is_a_read_only_snapshot(self) -> None:
        application = self._compose(_InertResolver())
        boundary = application.shared_application_boundary

        self.assertTrue(callable(boundary.import_run_archive))
        self.assertTrue(application.import_run_button.isEnabled())
        from AgMark.gui.widgets.buttons import ActionButton
        self.assertIsInstance(application.import_run_button, ActionButton)
        self.assertEqual(application.import_run_button.text(), "Import Run")
        self.assertEqual(application.import_run_button.minimumHeight(), 0)
        self.assertEqual(application.import_run_button.role, "secondary")
        self.assertEqual(application.import_run_button.property("arcgravSemanticComponent"),
                         "action-button")
        self.assertEqual((), boundary.historical_runs)
        with self.assertRaises(AttributeError):
            boundary.historical_runs = ()

    def test_import_button_cancel_does_not_validate_or_import(self) -> None:
        application = self._compose(_InertResolver())
        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=("", "")) as chooser, \
             patch("AgMark.shared.validation.validate_run_archive") as validate:
            application.import_run_button.click()
        chooser.assert_called_once_with(
            application.window, "Import AgMark Run", "", "AgMark archives (*.agmark)"
        )
        validate.assert_not_called()
        self.assertEqual((), application.shared_application_boundary.historical_runs)

    def test_repository_factory_selects_shared_workspace_projector_by_default(
        self,
    ) -> None:
        application = self._compose(_InertResolver())

        self.assertIsInstance(
            application._projector._workspace_projector,
            SharedWorkspaceProjector,
        )

    def test_reference_workspace_no_projection_renders_and_replaces_without_stale_state(
        self,
    ) -> None:
        application = self._compose(_InertResolver())
        window = application.window
        window.resize(1440, 1080)
        QApplication.processEvents()

        tabs = window.workspace_tabs
        unavailable_pages = dict(window.workspace_pages)
        for index, name in enumerate(WORKSPACE_TAB_LABELS):
            tabs.setCurrentIndex(index)
            QApplication.processEvents()
            page = unavailable_pages[name]
            self.assertEqual("unavailable", page.property("projectionState"))
            self.assertTrue(page.findChild(QLabel, "workspaceEmptyStateMessage").isVisible())
            self.assertFalse(page.grab().isNull())
        tabs.setCurrentIndex(0)
        self._assert_reference_workspace_tab_chrome(window)
        self.assertEqual("Progress", tabs.selected_label)

        unavailable_page = window.workspace_pages["Progress"]
        unavailable_card = unavailable_page.findChild(
            QWidget,
            "workspaceEmptyStateCard",
        )
        unavailable_message = unavailable_page.findChild(
            QLabel,
            "workspaceEmptyStateMessage",
        )
        self.assertIsNotNone(unavailable_card)
        self.assertIsNotNone(unavailable_message)
        self.assertEqual("unavailable", unavailable_page.property("projectionState"))
        self.assertTrue(unavailable_page.isVisible())
        self.assertTrue(unavailable_card.isVisible())
        self.assertTrue(unavailable_message.isVisible())
        self.assertGreater(unavailable_page.width(), 0)
        self.assertGreater(unavailable_page.height(), 0)
        self.assertGreater(unavailable_card.width(), 0)
        self.assertGreater(unavailable_card.height(), 0)
        self.assertGreater(unavailable_message.width(), 0)
        self.assertGreater(unavailable_message.height(), 0)
        self.assertTrue(unavailable_card.styleSheet().strip())
        self.assertFalse(unavailable_page.grab().isNull())
        self.assertFalse(unavailable_card.grab().isNull())
        self.assertFalse(unavailable_message.grab().isNull())

        console_active_tab = window.console_widget.state.active_tab
        console_expanded = window.console_widget.state.expanded
        console_height = window.console_widget.height()
        populated = WorkspaceProjection(
            progress=QLabel("Caller-supplied populated Progress projection"),
            results=QLabel("Caller-supplied populated Results projection"),
            reports=QLabel("Caller-supplied populated Reports projection"),
            verification=QLabel("Caller-supplied populated Verification projection"),
            evidence=QLabel("Caller-supplied populated Artifacts projection"),
            scoring=QLabel("Caller-supplied populated Scoring projection"),
        )
        window.set_workspace_projection(
            populated,
            run_id="production-rendered-workspace",
        )
        QApplication.processEvents()

        self._assert_reference_workspace_tab_chrome(window)
        self.assertEqual("Progress", tabs.selected_label)
        self.assertEqual(
            "production-rendered-workspace",
            window.workspace_projection_run_id,
        )
        self.assertIs(populated.progress, window.workspace_pages["Progress"])
        self.assertTrue(populated.progress.isVisible())
        self.assertFalse(populated.progress.grab().isNull())
        self.assertIsNone(
            populated.progress.findChild(QLabel, "workspaceEmptyStateMessage")
        )
        self.assertIsNone(unavailable_page.parent())
        self.assertEqual(
            console_active_tab,
            window.console_widget.state.active_tab,
        )
        self.assertEqual(
            console_expanded,
            window.console_widget.state.expanded,
        )
        self.assertEqual(console_height, window.console_widget.height())
        for index, name in enumerate(WORKSPACE_TAB_LABELS):
            tabs.setCurrentIndex(index)
            QApplication.processEvents()
            page = window.workspace_pages[name]
            self.assertIn("Caller-supplied populated", page.text())
            self.assertTrue(page.isVisible())
            self.assertFalse(page.grab().isNull())
            self.assertIsNone(unavailable_pages[name].parent())
            self.assertIsNone(page.findChild(QLabel, "workspaceEmptyStateMessage"))
            self._assert_reference_workspace_tab_chrome(window)

    def test_benchmark_switch_removes_stale_evidence_destination_blocker(
        self,
    ) -> None:
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        self.assertGreaterEqual(len(authority.benchmark_candidates), 2)
        blocked_candidate = authority.benchmark_candidates[0]
        ready_candidate = authority.benchmark_candidates[1]
        blocked_label = _source_label(blocked_candidate)
        ready_label = _source_label(ready_candidate)
        resolver = _InertResolver()

        with TemporaryDirectory() as temporary_root:
            ready_root = Path(temporary_root).joinpath(
                *ready_candidate.package_root.split("/")
            )
            ready_root.mkdir(parents=True)

            application, _authority = self._compose_repository_session(
                resolver,
                readiness_repository_root=Path(temporary_root),
                executable_resolver=lambda name: f"/validated/{name}",
                authentication_probe=lambda *_args: True,
                model_discovery_probe=_ready_discovery_for_source,
            )
            self._select_benchmark(application, blocked_label)
            blocked_names = {
                name
                for widget in application.window.prerequisite_diagnostic_widgets
                for name in (widget.property("diagnosticNames") or ())
            }
            self.assertIn("benchmark-evidence-destination", blocked_names)

            application.window.console_widget.set_active_tab("Environment")
            self._select_benchmark(application, ready_label)
            QApplication.processEvents()

            refreshed_names = {
                name
                for widget in application.window.prerequisite_diagnostic_widgets
                for name in (widget.property("diagnosticNames") or ())
            }
            self.assertNotIn("benchmark-evidence-destination", refreshed_names)
            benchmark_entry = next(
                entry
                for entry in application.environment_projection.entries
                if entry.source == "Benchmark"
            )
            self.assertEqual(ready_label, benchmark_entry.details)
            self.assertEqual(
                application.environment_projection.render(),
                application.window.console_widget.state.visible_text,
            )
            self.assertEqual([], resolver.calls)

    def test_selection_refresh_does_not_rewrite_prepared_plan_identity(
        self,
    ) -> None:
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        benchmark = next(
            candidate
            for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        other_benchmark = next(
            candidate
            for candidate in authority.benchmark_candidates
            if candidate is not benchmark
        )
        provider_free = _provider_free_source(authority)
        cli_source = _credential_cli_source(authority)
        application = BenchmarkDesktopApplication.from_repository_authority(
            application_icon=QIcon(QPixmap(1, 1)),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
            executable_resolver=lambda name: f"/validated/{name}",
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        QApplication.processEvents()

        benchmark_label = _source_label(benchmark)
        runner_label = _source_label(provider_free)
        self._select_benchmark(application, benchmark_label)
        self._select_runner(application, runner_label)
        application.request_build_plan(
            SidebarInputSnapshot(
                benchmark=benchmark_label,
                runner=runner_label,
                model="mock-base::scenario:completed",
                credential="",
                temperature=None,
                max_tokens=None,
                additional_controls=(
                    SidebarControlInputSnapshot("request_timeout_ms", "120000"),
                ),
            )
        )
        QApplication.processEvents()

        boundary = application.shared_application_boundary
        prepared_plan = boundary.session.prepared_plan
        plan_request = boundary.plan_request
        self.assertIsNotNone(prepared_plan)
        self.assertIsNotNone(plan_request)
        current_identity = application.window.current_run_identity_label.text()
        current_boundary_values = tuple(
            value.text()
            for _label, value in application.window.execution_boundary_rows
        )
        self.assertEqual(benchmark_label, current_boundary_values[0])
        self.assertEqual(runner_label, current_boundary_values[1])

        other_benchmark_label = _source_label(other_benchmark)
        cli_label = _source_label(cli_source)
        application.window.console_widget.set_active_tab("Environment")
        self._select_benchmark(application, other_benchmark_label)
        self._select_runner(application, cli_label)
        QApplication.processEvents()

        selected_intent = application.window.sidebar_input_snapshot()
        self.assertEqual(other_benchmark_label, selected_intent.benchmark)
        self.assertEqual(cli_label, selected_intent.runner)
        self.assertIs(prepared_plan, boundary.session.prepared_plan)
        self.assertIs(plan_request, boundary.plan_request)
        self.assertEqual(
            current_identity,
            application.window.current_run_identity_label.text(),
        )
        self.assertEqual(
            current_boundary_values,
            tuple(
                value.text()
                for _label, value in application.window.execution_boundary_rows
            ),
        )
        benchmark_entry = next(
            entry
            for entry in application.environment_projection.entries
            if entry.source == "Benchmark"
        )
        runner_entry = next(
            entry
            for entry in application.environment_projection.entries
            if entry.source == "Runner"
        )
        self.assertEqual(other_benchmark_label, benchmark_entry.details)
        self.assertEqual(cli_label, runner_entry.details)
        self.assertEqual(
            application.environment_projection.render(),
            application.window.console_widget.state.visible_text,
        )

    def test_runner_switch_refreshes_environment_and_drops_prior_runner_state(
        self,
    ) -> None:
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        cli_source = _credential_cli_source(authority)
        provider_free_source = _provider_free_source(authority)
        resolver = _InertResolver()
        application = self._compose(
            resolver,
            executable_resolver=lambda _name: None,
            authentication_probe=lambda *_args: False,
            model_discovery_probe=lambda *_args: None,
        )

        cli_label = _source_label(cli_source)
        self._select_runner(application, cli_label)
        self._select_native_launch(application)
        application.window.console_widget.set_active_tab("Environment")
        QApplication.processEvents()

        cli_sources = {
            entry.source for entry in application.environment_projection.entries
        }
        self.assertIn("Prerequisite runner-executable", cli_sources)
        self.assertEqual(
            application.environment_projection.render(),
            application.window.console_widget.state.visible_text,
        )

        provider_free_label = _source_label(provider_free_source)
        self._select_runner(application, provider_free_label)
        QApplication.processEvents()

        refreshed_sources = {
            entry.source for entry in application.environment_projection.entries
        }
        self.assertNotIn("Prerequisite runner-authentication", refreshed_sources)
        self.assertNotIn("Prerequisite runner-executable", refreshed_sources)
        self.assertIn("Prerequisite runner-model-discovery", refreshed_sources)
        self.assertIsNotNone(application.window.scenario_input)
        self.assertFalse(application.window.scenario_input.combo_box.isEnabled())
        runner_entry = next(
            entry
            for entry in application.environment_projection.entries
            if entry.source == "Runner"
        )
        self.assertEqual(provider_free_label, runner_entry.details)
        self.assertEqual(
            application.environment_projection.render(),
            application.window.console_widget.state.visible_text,
        )
        self.assertIsNone(application.window.model_input.value)
        self.assertEqual("", application.window.credential_input.value)
        self.assertEqual(
            {"request_timeout_ms"},
            set(application.window.additional_control_inputs),
        )
        self.assertEqual([], resolver.calls)

    def test_runner_switch_reverse_refreshes_cli_authority_and_drops_provider_free_state(
        self,
    ) -> None:
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        provider_free_source = _provider_free_source(authority)
        cli_source = _credential_cli_source(authority)
        resolver = _InertResolver()
        application = self._compose(
            resolver,
            executable_resolver=lambda name: f"/validated/{name}",
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
        )

        provider_free_label = _source_label(provider_free_source)
        self._select_runner(application, provider_free_label)
        self.assertEqual(
            {"request_timeout_ms"},
            set(application.window.additional_control_inputs),
        )

        application.window.console_widget.set_active_tab("Environment")
        cli_label = _source_label(cli_source)
        self._select_runner(application, cli_label)
        QApplication.processEvents()

        refreshed_sources = {
            entry.source for entry in application.environment_projection.entries
        }
        self.assertTrue(
            {
                "Prerequisite runner-executable",
                "Prerequisite runner-authentication",
                "Prerequisite runner-model-discovery",
            }.isdisjoint(refreshed_sources),
            refreshed_sources,
        )
        runner_entry = next(
            entry
            for entry in application.environment_projection.entries
            if entry.source == "Runner"
        )
        self.assertEqual(cli_label, runner_entry.details)
        self.assertEqual(
            application.environment_projection.render(),
            application.window.console_widget.state.visible_text,
        )
        self.assertEqual(
            ("Default (GPT-5.6)", "GPT-5.6 Mini"),
            application.window.model_input.options,
        )
        self.assertEqual(
            "Default (GPT-5.6)",
            application.window.model_input.value,
        )
        self.assertEqual("", application.window.credential_input.value)
        self.assertTrue(
            {"mock_outcome", "response_mode", "credential_source"}.isdisjoint(
                application.window.additional_control_inputs
            )
        )
        self.assertIn(
            "codex_home",
            application.window.resolved_configuration_inputs,
        )
        self.assertTrue(
            application.window.resolved_configuration_inputs[
                "codex_home"
            ].line_edit.isReadOnly()
        )
        switched_snapshot = application.window.sidebar_input_snapshot()
        self.assertEqual(cli_label, switched_snapshot.runner)
        self.assertEqual("gpt-5.6", switched_snapshot.model)
        self.assertEqual(
            "explicit",
            next(
                control.value
                for control in switched_snapshot.additional_controls
                if control.control_name == "model_selection_mode"
            ),
        )
        self.assertNotIn(
            "codex_home",
            {
                control.control_name
                for control in switched_snapshot.additional_controls
            },
        )
        self.assertEqual([], resolver.calls)

    def test_codex_wsl_configuration_is_visible_discovered_and_read_only_where_resolved(self) -> None:
        # Live Codex owns WSL controls; Mock Model has no launch settings.
        # No Windows/WSL executable or live provider is launched by this test.
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        catalog = _offline_codex_model_discovery()
        for source in (_credential_cli_source(authority),):
            with self.subTest(runner=source.registration["registration_id"]):
                expected_binary = source.registration["extensions"]["arcgrav.adapters:launch_environment"]["wsl"]["codex_binary_default"]
                resolver = _InertResolver()
                with patch("AgMark.gui.readiness.os_name", "nt"):
                    application = self._compose(
                        resolver,
                        executable_resolver=lambda name: (
                            name
                            if name == r"C:\Windows\System32\wsl.exe"
                            else None
                        ),
                        model_discovery_probe=lambda *_args, **_kwargs: catalog,
                    )
                    cli_label = _source_label(source)
                    self._select_runner(application, cli_label)
                    QApplication.processEvents()

                window = application.window
                self.assertEqual(
                    {"launch_mode", "wsl_distribution", "codex_binary", "capture_mode", "diagnostic_privacy_acknowledged"},
                    set(window.additional_control_inputs),
                )
                self.assertEqual("wsl", window.additional_control_inputs["launch_mode"].value)
                self.assertEqual(
                    "Ubuntu",
                    window.additional_control_inputs["wsl_distribution"].value,
                )
                self.assertEqual(
                    expected_binary,
                    window.additional_control_inputs["codex_binary"].value,
                )
                self.assertEqual(
                    ("Default (GPT-5.6)", "GPT-5.6 Mini"),
                    window.model_input.options,
                )
                self.assertEqual("Default (GPT-5.6)", window.model_input.value)

                self.assertEqual(
                    {"wsl_user", "codex_home"},
                    set(window.resolved_configuration_inputs),
                )
                self.assertEqual(
                    "gunnanmon",
                    window.resolved_configuration_inputs["wsl_user"].value,
                )
                self.assertEqual(
                    "/home/gunnanmon/.codex",
                    window.resolved_configuration_inputs["codex_home"].value,
                )
                self.assertTrue(
                    window.resolved_configuration_inputs["wsl_user"].line_edit.isReadOnly()
                )
                self.assertTrue(
                    window.resolved_configuration_inputs["codex_home"].line_edit.isReadOnly()
                )

                snapshot = window.sidebar_input_snapshot()
                self.assertEqual("gpt-5.6", snapshot.model)
                snapshot_controls = {
                    control.control_name: control.value
                    for control in snapshot.additional_controls
                }
                self.assertEqual("wsl", snapshot_controls["launch_mode"])
                self.assertEqual("Ubuntu", snapshot_controls["wsl_distribution"])
                self.assertEqual(expected_binary, snapshot_controls["codex_binary"])
                self.assertEqual("session", snapshot_controls["capture_mode"])
                self.assertEqual("not_acknowledged", snapshot_controls["diagnostic_privacy_acknowledged"])
                self.assertEqual("explicit", snapshot_controls["model_selection_mode"])
                self.assertNotIn("wsl_user", snapshot_controls)
                self.assertNotIn("codex_home", snapshot_controls)
                self.assertEqual([], resolver.calls)

    def test_codex_capture_controls_flow_from_sidebar_into_plan(self) -> None:
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        benchmark = next(
            candidate for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        def offline_planning_probe(source, controls):
            self.assertEqual("openai.codex-cli", source.registration["registration_id"])
            return {
                "status": "ready", "provider_submitted": False,
                "resolved_controls": dict(controls),
                "provider_runtime": {
                    "runtime_id": "openai.codex-cli", "runtime_version": "offline-fixture",
                    "provider": "OpenAI", "access_method": "cli", "model": controls["model_id"],
                },
            }

        resolver = RepositoryApplicationRequestResolver(
            authority, runner_planning_probe=offline_planning_probe,
        )
        application = BenchmarkDesktopApplication.from_repository_authority(
            request_resolver=resolver,
            executable_resolver=lambda name: f"/offline-fixture/{name}",
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        self._select_benchmark(application, _source_label(benchmark))
        self._select_runner(application, _source_label(_credential_cli_source(authority)))
        self._select_native_launch(application)
        window = application.window
        profile = window.additional_control_inputs["capture_mode"]
        acknowledgement = window.additional_control_inputs["diagnostic_privacy_acknowledged"]
        self.assertEqual("session", profile.value)
        self.assertEqual("not_acknowledged", acknowledgement.value)
        self.assertTrue(window.build_plan_button.isEnabled(), application.environment_projection.render())
        prior_snapshot = window.sidebar_input_snapshot()

        profile.set_value("deep_telemetry")
        QApplication.processEvents()
        dialog = window._diagnostic_dialog
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.isModal())
        self.assertTrue(dialog.isVisible())
        self.assertEqual("session", window.additional_control_inputs["capture_mode"].value)
        self.assertEqual("not_acknowledged", window.additional_control_inputs["diagnostic_privacy_acknowledged"].value)
        self.assertEqual(prior_snapshot, window.sidebar_input_snapshot())
        dialog.cancel_button.click()
        QApplication.processEvents()
        snapshot = window.sidebar_input_snapshot()
        self.assertEqual(prior_snapshot, snapshot)
        self.assertTrue(window.build_plan_button.isEnabled())
        snapshot_controls = {control.control_name: control.value for control in snapshot.additional_controls}
        self.assertEqual("session", snapshot_controls["capture_mode"])
        self.assertEqual("not_acknowledged", snapshot_controls["diagnostic_privacy_acknowledged"])
        application.request_build_plan(snapshot)
        QApplication.processEvents()
        request = application.shared_application_boundary.plan_request
        self.assertIsNotNone(request, application.environment_projection.render())
        plan_controls = {control["name"]: control["value"] for control in request.execution_boundary.to_dict()["controls"]}
        self.assertEqual("session", plan_controls["capture_mode"])
        self.assertEqual("not_acknowledged", plan_controls["diagnostic_privacy_acknowledged"])

    def test_production_startup_projects_unversioned_arcgrav_application_identity(
        self,
    ) -> None:
        application = self._application
        previous_name = application.applicationName()
        previous_display_name = application.applicationDisplayName()
        previous_version = application.applicationVersion()
        previous_icon = application.windowIcon()
        previous_palette = application.palette()
        previous_font = application.font()
        previous_sheet = application.styleSheet()
        previous_active = application.property("arcgravDesignSystemActive")
        previous_theme = application.property("arcgravDesignSystemTheme")

        self.addCleanup(
            application.setProperty,
            "arcgravDesignSystemTheme",
            previous_theme,
        )
        self.addCleanup(
            application.setProperty,
            "arcgravDesignSystemActive",
            previous_active,
        )
        self.addCleanup(application.setStyleSheet, previous_sheet)
        self.addCleanup(application.setFont, previous_font)
        self.addCleanup(application.setPalette, previous_palette)
        self.addCleanup(application.setWindowIcon, previous_icon)
        self.addCleanup(application.setApplicationVersion, previous_version)
        self.addCleanup(application.setApplicationDisplayName, previous_display_name)
        self.addCleanup(application.setApplicationName, previous_name)

        self.enterContext(patch("AgMark.gui.application.desktop.probe_registered_runner_authentication", return_value=True))
        self.enterContext(patch(
            "AgMark.gui.application.desktop.probe_registered_runner_model_discovery",
            side_effect=lambda source, **kwargs: _ready_discovery_for_source(source, kwargs.get("selected_control_values")),
        ))
        qt_application, desktop = startup.create_production_application([])
        self.assertIs(qt_application, application)
        self.addCleanup(desktop.window.deleteLater)
        desktop.show()
        desktop.window.resize(1440, 1080)
        QApplication.processEvents()

        window = desktop.window
        self.assertEqual("AgMark", application.applicationName())
        self.assertEqual(
            "Architectural Gravity Benchmark",
            application.applicationDisplayName(),
        )
        self.assertEqual(previous_version, application.applicationVersion())
        self.assertEqual(
            "Architectural Gravity Benchmark",
            window.windowTitle(),
        )

        self._assert_icon_matches_arcgrav_application_identity(
            application.windowIcon()
        )
        self._assert_icon_matches_arcgrav_application_identity(window.windowIcon())
        self.assertEqual(
            application.windowIcon().pixmap(32, 32).toImage(),
            window.windowIcon().pixmap(32, 32).toImage(),
        )

        self.assertTrue(application.property("arcgravDesignSystemActive"))
        self.assertEqual(
            DEFAULT_LIGHT_THEME.name,
            application.property("arcgravDesignSystemTheme"),
        )

    def test_real_provider_free_required_controls_block_build_plan_without_resolution(
        self,
    ) -> None:
        resolver = _InertResolver()
        application, authority = self._compose_repository_session(
            resolver,
            executable_resolver=lambda name: f"/validated/{name}",
            authentication_probe=lambda _source: True,
            model_discovery_probe=lambda *_args: None,
        )
        source = _provider_free_source(authority)
        self._select_runner(application, _source_label(source))

        self.assertTrue(application.window.prerequisite_diagnostic_widgets)
        self.assertIsNotNone(application.window.scenario_input)
        self.assertFalse(application.window.scenario_input.combo_box.isEnabled())
        self.assertEqual(
            {"request_timeout_ms"},
            set(application.window.additional_control_inputs),
        )
        self.assertFalse(application.window.build_plan_button.isEnabled())
        self.assertIn(
            "prerequisites",
            application.window.build_plan_button.accessibleDescription(),
        )

        application.window.build_plan_button.click()
        QApplication.processEvents()
        self.assertEqual([], resolver.calls)

    def test_real_provider_free_plan_replacement_preserves_current_run_reference_rendering(
        self,
    ) -> None:
        self._activate_application_theme()
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        benchmark = next(
            candidate
            for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        runner = _provider_free_source(authority)
        application = BenchmarkDesktopApplication.from_repository_authority(
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        window = application.window
        window.resize(1440, 1080)
        QApplication.processEvents()

        self.assertTrue(self._application.property("arcgravDesignSystemActive"))
        self.assertEqual(
            DEFAULT_LIGHT_THEME.name,
            self._application.property("arcgravDesignSystemTheme"),
        )

        window.workspace_tabs.setCurrentIndex(3)
        QApplication.processEvents()
        selected_workspace = window.workspace_tabs.currentIndex()

        empty_region = window.current_run_region
        empty_card = window.current_run_empty_state_card
        self.assertIsNotNone(empty_card)
        empty_layout = empty_region.layout()
        left, top, right, bottom = empty_layout.getContentsMargins()
        self.assertEqual(left, DEFAULT_LAYOUT_METRICS.metric("space-md"))
        self.assertEqual(right, DEFAULT_LAYOUT_METRICS.metric("space-md"))
        self.assertEqual(top, DEFAULT_LAYOUT_METRICS.metric("space-md"))
        self.assertEqual(bottom, DEFAULT_LAYOUT_METRICS.metric("space-md"))
        self.assertEqual(
            empty_layout.spacing(),
            DEFAULT_LAYOUT_METRICS.metric("space-sm"),
        )
        self.assertEqual(empty_card.geometry().left(), left)
        self.assertEqual(
            empty_card.width(),
            empty_region.contentsRect().width() - left - right,
        )
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
        empty_tab_gap = (
            window.workspace_tabs.geometry().top()
            - window.current_run_scroll.geometry().bottom()
            - 1
        )
        self._assert_render_contains_color(
            empty_region,
            DEFAULT_LIGHT_THEME.color("surface-background"),
        )
        self._assert_render_contains_color(
            empty_card,
            DEFAULT_LIGHT_THEME.color("surface-panel"),
        )

        benchmark_label = _source_label(benchmark)
        runner_label = _source_label(runner)
        application.request_build_plan(
            SidebarInputSnapshot(
                benchmark=benchmark_label,
                runner=runner_label,
                model="mock-base::scenario:completed",
                credential="",
                temperature=None,
                max_tokens=None,
                additional_controls=(
                    SidebarControlInputSnapshot("request_timeout_ms", "120000"),
                ),
            )
        )
        QApplication.processEvents()

        boundary = application.shared_application_boundary
        self.assertIsNotNone(
            boundary.plan_request,
            application.environment_projection.render(),
        )
        self.assertIsNotNone(boundary.session.prepared_plan)
        self.assertIsNot(empty_region, window.current_run_region)
        self.assertIsNone(window.current_run_empty_state_card)
        self.assertIsNone(window.current_run_empty_state_label)
        self.assertEqual(selected_workspace, window.workspace_tabs.currentIndex())

        populated_region = window.current_run_region
        populated_tab_gap = (
            window.workspace_tabs.geometry().top()
            - window.current_run_scroll.geometry().bottom()
            - 1
        )
        self.assertEqual(empty_tab_gap, populated_tab_gap)
        self.assertEqual(
            window.execution_boundary_card.accessibleName(),
            "Execution Boundary",
        )
        self.assertEqual(window.run_plan_card.accessibleName(), "Run Plan")
        self.assertGreater(
            window.run_plan_card.width(),
            window.execution_boundary_card.width(),
        )
        self.assertLess(
            window.accept_plan_button.geometry().left(),
            window.start_benchmark_button.geometry().left(),
        )

        boundary_document = boundary.plan_request.execution_boundary.to_dict()
        provider_runtime = boundary_document["provider_runtime"]
        runtime_model = provider_runtime.get("model")
        expected_model = (
            runtime_model
            if isinstance(runtime_model, str) and runtime_model
            else "None declared"
        )
        self.assertEqual(
            expected_model,
            window.execution_boundary_rows[2][1].text(),
        )
        self.assertNotEqual(
            window.model_input.value,
            window.execution_boundary_rows[2][1].text(),
        )

        self._assert_render_contains_color(
            populated_region,
            DEFAULT_LIGHT_THEME.color("surface-background"),
        )
        self._assert_render_contains_color(
            window.execution_boundary_card,
            DEFAULT_LIGHT_THEME.color("surface-panel"),
        )
        self._assert_render_contains_color(
            window.run_plan_card,
            DEFAULT_LIGHT_THEME.color("surface-panel"),
        )

    def test_real_provider_free_runner_completes_production_desktop_lifecycle(self) -> None:
        self._activate_application_theme()
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        benchmark = next(
            candidate
            for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        runner = _provider_free_source(authority)
        application = BenchmarkDesktopApplication.from_repository_authority(
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        application.window.resize(1440, 1080)
        QApplication.processEvents()
        boundary = application.shared_application_boundary
        benchmark_label = _source_label(benchmark)
        runner_label = _source_label(runner)

        self.assertIn(benchmark_label, application.window.benchmark_input.options)
        self.assertIn(runner_label, application.window.runner_input.options)
        application.window.console_widget.set_active_tab("Environment")
        environment_before_lifecycle = (
            application.window.console_widget.state.visible_text
        )
        self.assertTrue(environment_before_lifecycle)
        self.assertEqual(
            application.environment_projection.render(),
            environment_before_lifecycle,
        )
        self.assertIsNotNone(application.window.current_run_empty_state_card)
        self.assertIsNotNone(application.window.current_run_empty_state_label)
        self.assertIsNone(application.window.current_run_status)
        self.assertEqual({}, application.window.run_rows)
        self.assertIsNotNone(application.window.runs_empty_label)
        self.assertEqual(
            "No runs",
            application.window.runs_empty_label.text(),
        )
        self.assertEqual(
            "No runs",
            application.window.runs_empty_label.accessibleName(),
        )
        self.assertEqual(
            "presentation-only",
            application.window.runs_empty_label.property("authoritySemantics"),
        )
        no_plan_progress_page = self._assert_unavailable_progress_workspace(
            application.window
        )
        no_plan_fixture = self._capture_full_client_render_fixture(
            application.window,
            state="blocked-or-no-plan",
        )

        application.request_build_plan(
            SidebarInputSnapshot(
                benchmark=benchmark_label,
                runner=runner_label,
                model="mock-base::scenario:completed",
                credential="",
                temperature=None,
                max_tokens=None,
                additional_controls=(
                    SidebarControlInputSnapshot("request_timeout_ms", "120000"),
                ),
            )
        )
        QApplication.processEvents()
        self.assertIsNotNone(
            boundary.plan_request,
            application.environment_projection.render(),
        )
        self.assertIsNone(application.window.current_run_empty_state_card)
        self.assertIsNone(application.window.current_run_empty_state_label)
        self.assertIsNotNone(application.window.current_run_status)
        self.assertEqual("Pending", application.window.current_run_status.label)
        self._assert_unavailable_progress_workspace(application.window)
        prepared_fixture = self._capture_full_client_render_fixture(
            application.window,
            state="prepared",
        )
        self._assert_full_client_fixture_continuity(
            no_plan_fixture,
            prepared_fixture,
        )

        application.request_accept_plan()
        QApplication.processEvents()
        self.assertIsNotNone(boundary.accepted_snapshot)
        self.assertEqual("Accepted", application.window.current_run_status.label)
        environment_before_execution = (
            application.window.console_widget.state.visible_text
        )
        self.assertTrue(environment_before_execution)
        self.assertEqual(
            application.environment_projection.render(),
            environment_before_execution,
        )
        self._assert_unavailable_progress_workspace(application.window)

        execute_entered = Event()
        release_execution = Event()
        original_execute = boundary.session.execute_accepted_run

        def delayed_execute(request):
            execute_entered.set()
            if not release_execution.wait(30):
                raise RuntimeError("timed out waiting to inspect active Progress")
            return original_execute(request)

        def threaded_dispatch(operation):
            worker = Thread(
                target=operation,
                name="arcgrav-active-progress-test",
                daemon=True,
            )
            worker.start()
            return worker

        original_dispatcher = application._authority_dispatcher
        application._authority_dispatcher = threaded_dispatch
        with patch.object(
            boundary.session,
            "execute_accepted_run",
            side_effect=delayed_execute,
        ):
            worker = application.request_start_benchmark()
            try:
                self.assertTrue(execute_entered.wait(10))
                for _ in range(200):
                    QApplication.processEvents()
                    active_page = application.window.workspace_pages["Progress"]
                    if (
                        isinstance(active_page, ProgressView)
                        and active_page.projection.overall is not None
                    ):
                        break
                    Event().wait(0.005)
                else:
                    self.fail("active populated Progress projection was not rendered")

                active_page = application.window.workspace_pages["Progress"]
                active_projection = active_page.projection
                active_generation_id = active_projection.generation_id
                self.assertEqual(
                    active_generation_id,
                    application.window.workspace_projection_run_id,
                )
                self.assertEqual(active_generation_id, active_projection.run_id)
                self.assertEqual(0, active_projection.overall.completed_cases)
                self.assertGreater(active_projection.overall.total_cases, 0)
                self.assertTrue(active_projection.treatments)
                self.assertTrue(active_projection.events)
                self.assertTrue(
                    all(
                        event.generation_id == active_generation_id
                        for event in active_projection.events
                    )
                )
                self.assertIsNotNone(active_page.overall_ring)
                self.assertIsNotNone(active_page.overall_bar)
                self.assertEqual(
                    {
                        "Completed Cases",
                        "Remaining Cases",
                        "Total Cases",
                    },
                    set(active_page.summary_value_labels),
                )
                self.assertGreater(
                    active_page.treatment_table.table_model.rowCount(),
                    0,
                )
                self.assertIsNotNone(active_page.stage_stepper)
                self.assertIsNotNone(active_page.stage_description_card)
                self.assertEqual(active_page.run_stage_card.height(), active_page.treatment_card.height())
                self.assertGreater(active_page.width(), 0)
                self.assertGreater(active_page.height(), 0)
                self.assertFalse(active_page.grab().isNull())
                self._assert_reference_workspace_tab_chrome(application.window)
                for label in ("Results", "Reports", "Verification", "Evidence"):
                    self.assertEqual(
                        active_generation_id,
                        application.window.workspace_pages[label].run_id,
                    )

                stale_event = ProgressEventProjection(
                    generation_id="superseded-generation",
                    timestamp="2026-09-24T00:00:00Z",
                    event_icon="!",
                    text="stale generation event must not render",
                )
                active_page.push_event(stale_event)
                QApplication.processEvents()
                self.assertNotIn(
                    "stale generation event must not render",
                    tuple(event.text for event in active_page.visible_events),
                )
                active_fixture = self._capture_full_client_render_fixture(
                    application.window,
                    state="active-progress",
                )
                self._assert_full_client_fixture_continuity(
                    prepared_fixture,
                    active_fixture,
                )
            finally:
                release_execution.set()
                worker.join(60)
                application._authority_dispatcher = original_dispatcher
            self.assertFalse(worker.is_alive())

        QApplication.processEvents()
        retained = boundary.selected_terminal
        self.assertIs(type(retained), AcceptedRun)
        generation_id = retained.generation_id
        shared_retained_status = retained.run_outcome()["status"]
        self.assertEqual("accepted", shared_retained_status)
        self.assertEqual(active_generation_id, generation_id)
        self.assertEqual(
            "Completed · Report ready",
            application.window.run_rows[generation_id].status_badge.label,
        )
        self.assertTrue(application.window.run_rows[generation_id].selected)
        self.assertEqual(generation_id, application.window.selected_run_id)
        self.assertEqual(
            generation_id,
            application.window.workspace_projection_run_id,
        )
        self.assertEqual(
            generation_id,
            application.window.console_widget.state.active_generation_id,
        )
        self.assertEqual(
            "Environment",
            application.window.console_widget.state.active_tab,
        )
        self.assertEqual(
            environment_before_execution,
            application.window.console_widget.state.visible_text,
        )
        self.assertTrue(retained.artifact_index.artifacts)
        retained_progress_page = application.window.workspace_pages["Progress"]
        self.assertIsNot(retained_progress_page, active_page)
        self.assertIsNone(active_page.parent())
        self.assertEqual(generation_id, retained_progress_page.run_id)
        self.assertEqual(generation_id, retained_progress_page.generation_id)
        for label in ("Results", "Reports", "Verification", "Evidence"):
            self.assertEqual(
                generation_id,
                application.window.workspace_pages[label].run_id,
            )
        self._assert_reference_workspace_tab_chrome(application.window)
        terminal_fixture = self._capture_full_client_render_fixture(
            application.window,
            state="terminal",
        )
        self._assert_full_client_fixture_continuity(
            active_fixture,
            terminal_fixture,
        )

        application.request_select_run(generation_id)
        QApplication.processEvents()
        self.assertEqual(
            generation_id,
            application.window.workspace_projection_run_id,
        )
        self.assertEqual(generation_id, application.window.selected_run_id)
        self.assertEqual(
            generation_id,
            application.window.workspace_pages["Progress"].run_id,
        )
        self.assertIsNone(retained_progress_page.parent())
        self.assertEqual(
            environment_before_execution,
            application.window.console_widget.state.visible_text,
        )
        retained_fixture = self._capture_full_client_render_fixture(
            application.window,
            state="retained-run",
        )
        self._assert_full_client_fixture_continuity(
            terminal_fixture,
            retained_fixture,
        )

        execution = boundary.execution_request
        self.assertIsNotNone(execution)
        # The isolated store mirrors repository-central evidence authority,
        # not the former per-benchmark evidence destination.
        evidence_root = self._test_evidence_root / _REPOSITORY_ROOT.name
        self.assertEqual(evidence_root, execution.artifact_store.root)
        self.assertEqual("external", execution.artifact_store.destination.ownership)
        self.assertTrue(evidence_root.is_dir())

        QApplication.processEvents()
        bundle = boundary.report_bundle
        self.assertIsNotNone(bundle)
        report_id = bundle.report_document["report_id"]
        self.assertEqual(report_id, application.window.workspace_pages["Reports"].projection.report_id)
        self.assertEqual(bundle.human.data.decode(), application.window.workspace_pages["Reports"].projection.readable_content)

        QApplication.processEvents()
        self.assertEqual("complete", boundary.report_state(generation_id)[0])
        self.assertEqual(
            "passed",
            application.window.workspace_pages[
                "Verification"
            ].projection.banner.status,
        )
        self.assertEqual(
            environment_before_execution,
            application.window.console_widget.state.visible_text,
        )
        self.assertEqual(
            application.environment_projection.render(),
            application.window.console_widget.state.visible_text,
        )

        retained_boundary_values = tuple(
            value.text()
            for _label, value in application.window.execution_boundary_rows
        )
        retained_identity = application.window.current_run_identity_label.text()
        retained_row = application.window.run_rows[generation_id]
        retained_row_state = (
            retained_row.identity_label.text(),
            retained_row.status_badge.label,
            retained_row.timestamp_label.text(),
            retained_row.selected,
        )
        other_benchmark = next(
            candidate
            for candidate in authority.benchmark_candidates
            if _source_label(candidate) != benchmark_label
        )
        cli_source = _credential_cli_source(authority)
        self._select_benchmark(application, _source_label(other_benchmark))
        self._select_runner(application, _source_label(cli_source))
        QApplication.processEvents()

        self.assertIs(retained, boundary.selected_terminal)
        self.assertEqual(generation_id, application.window.selected_run_id)
        self.assertEqual(
            generation_id,
            application.window.workspace_projection_run_id,
        )
        self.assertEqual(
            retained_identity,
            application.window.current_run_identity_label.text(),
        )
        self.assertEqual(
            retained_boundary_values,
            tuple(
                value.text()
                for _label, value in application.window.execution_boundary_rows
            ),
        )
        refreshed_row = application.window.run_rows[generation_id]
        self.assertEqual(
            retained_row_state,
            (
                refreshed_row.identity_label.text(),
                refreshed_row.status_badge.label,
                refreshed_row.timestamp_label.text(),
                refreshed_row.selected,
            ),
        )
        self.assertNotEqual(
            environment_before_execution,
            application.window.console_widget.state.visible_text,
        )
        self.assertEqual(
            application.environment_projection.render(),
            application.window.console_widget.state.visible_text,
        )

    def test_registered_mock_projects_own_telemetry_to_results_and_report(self) -> None:
        self._activate_application_theme()
        application = BenchmarkDesktopApplication.from_repository_authority(
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        QApplication.processEvents()
        window = application.window
        self._select_runner(application, "arcgrav.mock-model.runner@1.0.0")
        self._assert_mock_configuration(application)
        self._select_mock_scenario(application, "structured_response")
        application.request_build_plan(window.sidebar_input_snapshot())
        application.request_accept_plan()
        application.request_start_benchmark()
        QApplication.processEvents()

        boundary = application.shared_application_boundary
        retained = boundary.selected_terminal
        self.assertIs(type(retained), AcceptedRun)
        self.assertTrue(retained.treatment_observations)
        for raw in retained.treatment_observations:
            observation = json.loads(raw)
            validate_retained_parity_observation(observation)
            extensions = observation["extensions"]
            self.assertFalse(any(key.startswith("openai.codex_cli:") for key in extensions))
            execution = extensions["arcgrav.runner:execution"]
            self.assertEqual("mock_json_v1", execution["request_framing"]["mode"])
            self.assertFalse(execution["usage"]["provider_reported"])
            self.assertFalse(execution["isolation"]["session_home_reused"])
            telemetry = {value["name"]: value for value in observation["telemetry"]}
            self.assertEqual(execution["request_framing"]["byte_length"], telemetry["framed_request_bytes"]["value"])
            self.assertNotIn("stdout_bytes", telemetry)
            self.assertEqual("excluded", execution["process"]["stdout"]["availability"])
            self.assertTrue(all(value["unit"] == "bytes" for value in telemetry.values()))
            self.assertGreaterEqual(observation["attempts"][0]["duration_ms"], 0)

        results = window.workspace_pages["Results"]
        before = results.projection
        self.assertTrue(before.rows)
        self.assertEqual("Treatments", results.treatment_heading.text())
        self.assertEqual([row.treatment for row in before.rows],
                         [button.text() for button in results.treatment_buttons])
        unavailable = (
            "total_tokens", "input_tokens", "cached_input_tokens", "output_tokens",
            "reasoning_tokens", "tool_calls", "failed_tool_calls", "cost",
        )
        for index, row in enumerate(before.rows):
            results.treatment_buttons[index].click()
            self.assertTrue(results.treatment_buttons[index].isChecked())
            self.assertEqual(row.treatment, results._selected_row.treatment)
            self.assertEqual(index, results.cache_table.currentIndex().row())
            for role in unavailable:
                self.assertIsNone(row.measurements[role]["value"], role)
                self.assertEqual("unavailable", row.measurements[role]["availability"], role)
            self.assertGreaterEqual(row.measurements["duration"]["value"], 0)
            self.assertEqual("available", row.measurements["duration"]["availability"])
            self.assertNotIn("Session measurements:", row.details)

        report = boundary.report_bundle.human.data.decode("utf-8")
        self.assertIn("Treatment Total Averaged Results", report)
        self.assertNotIn("openai.codex_cli:session-record", report)

        self.assertNotIn("claim_state", boundary.report_bundle.report_document)
        QApplication.processEvents()
        self.assertEqual("complete", boundary.report_state(boundary.selected_terminal.generation_id)[0])
        self.assertEqual(before, window.workspace_pages["Results"].projection)
        application.request_select_run(retained.generation_id)
        QApplication.processEvents()
        self.assertEqual(before, window.workspace_pages["Results"].projection)

    def test_registered_mock_renders_normal_desktop_lifecycle(self) -> None:
        self._activate_application_theme()
        application = BenchmarkDesktopApplication.from_repository_authority(
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        application.window.resize(1440, 1080)
        QApplication.processEvents()
        window = application.window
        window.console_widget.set_stream_live_view(True)
        self._select_runner(application, "arcgrav.mock-model.runner@1.0.0")
        self._assert_mock_configuration(application)
        self._select_mock_scenario(application, "structured_response")
        intent = window.sidebar_input_snapshot()
        self.assertEqual("mock-base::scenario:structured_response", intent.model)
        self.assertNotIn(
            "mock_outcome",
            {control.control_name for control in intent.additional_controls},
        )
        window.console_widget.set_active_tab("Environment")
        environment_text = window.console_widget.state.visible_text

        application.request_build_plan(intent)
        QApplication.processEvents()
        self.assertEqual("Pending", window.current_run_status.label)
        application.request_accept_plan()
        QApplication.processEvents()
        self.assertEqual("Accepted", window.current_run_status.label)

        boundary = application.shared_application_boundary
        entered, release = Event(), Event()
        original_execute = boundary.session.execute_accepted_run

        def delayed_execute(request):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("active mock execution was not released")
            return original_execute(request)

        def threaded_dispatch(operation):
            worker = Thread(target=operation, daemon=True)
            worker.start()
            return worker

        previous_dispatcher = application._authority_dispatcher
        application._authority_dispatcher = threaded_dispatch
        worker = None
        try:
            with patch.object(
                boundary.session, "execute_accepted_run", side_effect=delayed_execute,
            ):
                worker = application.request_start_benchmark()
                self.assertTrue(entered.wait(5))
                for _ in range(200):
                    QApplication.processEvents()
                    active = window.workspace_pages["Progress"]
                    if isinstance(active, ProgressView) and active.projection.overall:
                        break
                    Event().wait(0.005)
                else:
                    self.fail("registered mock active Progress did not populate")
                generation_id = active.generation_id
                self.assertEqual(0, active.projection.overall.completed_cases)
                self.assertEqual(5, active.projection.overall.total_cases)
                self.assertEqual(5, active.treatment_table.table_model.rowCount())
                self.assertTrue(active.projection.events)
                self.assertTrue(active.treatment_table.accessibleName())
                active.treatment_table.setFocus()
                QApplication.processEvents()
                self.assertTrue(active.treatment_table.hasFocus())
                QTest.keyClick(active.treatment_table, Qt.Key.Key_Down)
                self.assertTrue(active.treatment_table.currentIndex().isValid())
                status_column = next(
                    index for index, column in enumerate(active.treatment_table.columns)
                    if column.label == "Status"
                )
                self.assertTrue(str(active.treatment_table.table_model.data(
                    active.treatment_table.table_model.index(0, status_column),
                    int(Qt.ItemDataRole.DisplayRole),
                )).strip())
                self.assertFalse(active.grab().isNull())
                self.assertGreater(active.treatment_card.width(), active.run_stage_card.width())
                for panel in (
                    active.summary_card, active.treatment_card,
                    active.run_stage_card,
                ):
                    top_left = panel.mapTo(active, panel.rect().topLeft())
                    self.assertGreaterEqual(top_left.x(), 0)
                    self.assertGreaterEqual(top_left.y(), 0)
                    self.assertLessEqual(top_left.x() + panel.width(), active.width())
                    self.assertLessEqual(top_left.y() + panel.height(), active.height())
                self._capture_full_client_render_fixture(
                    window, state="active-progress",
                )
        finally:
            release.set()
            if worker is not None:
                worker.join(30)
            application._authority_dispatcher = previous_dispatcher
        assert worker is not None
        self.assertFalse(worker.is_alive())
        QApplication.processEvents()

        retained = boundary.selected_terminal
        self.assertIs(type(retained), AcceptedRun)
        self.assertEqual(generation_id, retained.generation_id)
        self.assertEqual("Completed · Report ready", window.run_rows[generation_id].status_badge.label)
        for raw in retained.treatment_observations:
            observation = json.loads(raw)
            validate_retained_parity_observation(observation)
            execution = observation["extensions"]["arcgrav.runner:execution"]
            self.assertEqual("mock-model", execution["target"]["class"])
            self.assertFalse(execution["submission"]["external_provider"])
        for name in WORKSPACE_TAB_LABELS:
            self.assertEqual(generation_id, window.workspace_pages[name].run_id)
        self._assert_all_workspace_pages_use_projected_authority(window, generation_id)
        self._capture_full_client_render_fixture(window, state="terminal")
        self.assertEqual(environment_text, window.console_widget.state.visible_text)
        window.console_widget.set_active_tab("Diagnostics")
        self.assertIn(
            "Treatments completed: 5/5",
            window.console_widget.state.visible_text,
        )
        window.console_widget.set_active_tab("Live View")
        self.assertIn("Input:\n", window.console_widget.state.visible_text)
        self.assertIn("Output:\n", window.console_widget.state.visible_text)
        self._assert_retained_model_outputs(window, retained)
        window.console_widget.set_active_tab("Environment")
        self.assertEqual(environment_text, window.console_widget.state.visible_text)

        application.request_select_run(generation_id)
        QApplication.processEvents()
        self._capture_full_client_render_fixture(window, state="retained-run")
        results_before = window.workspace_pages["Results"].projection
        selected_results = window.workspace_pages["Results"]
        self.assertTrue(results_before.rows)
        self.assertEqual([row.treatment for row in results_before.rows],
                         [button.text() for button in selected_results.treatment_buttons])
        for row in results_before.rows:
            for role in ("total_tokens", "input_tokens", "cached_input_tokens", "output_tokens", "cost", "tool_calls", "failed_tool_calls"):
                self.assertIsNone(row.measurements[role]["value"])
                self.assertEqual("unavailable", row.measurements[role]["availability"])
            self.assertGreaterEqual(row.measurements["duration"]["value"], 0)
            self.assertNotIn("Session measurements:", row.details)
        self.assertIsNotNone(boundary.report_bundle)
        QApplication.processEvents()

        self.assertNotIn("claim_state", boundary.report_bundle.report_document)
        self.assertEqual("complete", boundary.report_state(boundary.selected_terminal.generation_id)[0])
        QApplication.processEvents()
        self.assertEqual("complete", boundary.report_state(boundary.selected_terminal.generation_id)[0])
        self.assertEqual(results_before, window.workspace_pages["Results"].projection)
        report_page = window.workspace_pages["Reports"]
        self.assertEqual("passed", report_page.projection.verification_state)

        self.assertIn("Treatment Results", report_page.content_browser.toPlainText())
        self.assertIn("Treatment Total Averaged Results", report_page.content_browser.toPlainText())
        import tempfile
        with tempfile.TemporaryDirectory() as exported:
            destination = Path(exported) / "report.md"
            application.request_export_report(generation_id, report_page.projection.report_id, destination)
            self.assertEqual(boundary.report_bundle.human.data, destination.read_bytes())
            self.assertEqual(report_page.projection.readable_content.encode(), destination.read_bytes())
            self.assertIn(str(destination), report_page.export_feedback_label.text())
            application.request_export_report(generation_id, report_page.projection.report_id, Path(exported)/"missing"/"report.md")
            self.assertIn("Export failed", report_page.export_feedback_label.text())
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")):
            application.request_export_report(generation_id, report_page.projection.report_id)
        self.assertEqual("Export cancelled.", report_page.export_feedback_label.text())

        self.assertNotIn("claim_state", boundary.report_bundle.report_document)

        self.assertNotIn("claim_state", boundary.report_bundle.report_document)
        self.assertEqual(environment_text, window.console_widget.state.visible_text)
        self._assert_all_workspace_pages_use_projected_authority(window, generation_id)
        self.assertIsNone(window.workspace_pages["Verification"].projection.banner.summary)
        self.assertIsNone(window.workspace_pages["Verification"].projection.summary.notes)

    def test_automatic_reports_preserve_retained_scope_and_reject_deleted_exports(self):
        application = BenchmarkDesktopApplication.from_repository_authority(
            authentication_probe=lambda *_args: True,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT, authority_dispatcher=lambda operation: operation(),
            model_discovery_probe=_ready_discovery_for_source,
        )
        self.addCleanup(application.window.deleteLater)
        window = application.window
        application.show()
        QApplication.processEvents()
        self._select_runner(application, "arcgrav.mock-model.runner@1.0.0")
        self._assert_mock_configuration(application)
        self._select_mock_scenario(application, "structured_response")
        boundary = application.shared_application_boundary
        def run():
            application.request_build_plan(window.sidebar_input_snapshot())
            application.request_accept_plan()
            application.request_start_benchmark()
            QApplication.processEvents()
            self.assertIs(type(boundary.selected_terminal), AcceptedRun)
            return boundary.selected_terminal.generation_id
        first, second = run(), run()
        self.assertNotEqual(first, second)
        console_generation = window.console_widget.state.active_generation_id
        application.request_select_run(first)
        self.assertEqual(second, console_generation)
        self.assertEqual(first, window.console_widget.state.active_generation_id)
        first_report = boundary.report_bundle
        self.assertEqual(first, first_report.report_document["accepted_generation_id"])
        self.assertEqual("complete", boundary.report_state(first)[0])
        application.request_select_run(second)
        second_report = boundary.report_bundle
        self.assertEqual(second, second_report.report_document["accepted_generation_id"])
        self.assertNotEqual(first_report.report_document["report_id"], second_report.report_document["report_id"])
        application.request_delete_run(second)
        self.assertEqual((None, None), boundary.report_state(second))
        self.assertNotIn(second, boundary._report_bundles)
        self.assertIsNone(window.workspace_projection_run_id)
        application.request_select_run(first)
        self.assertIs(first_report, boundary.report_bundle)
        self.assertEqual(first_report.report_document["report_id"], window.workspace_pages["Reports"].projection.report_id)
        with TemporaryDirectory() as exported:
            destination = Path(exported) / "deleted-report.md"
            with self.assertRaisesRegex(ValueError, "export selection changed"):
                application.request_export_report(second, second_report.report_document["report_id"], destination)
            self.assertFalse(destination.exists())
        self.assertEqual(first, window.console_widget.state.active_generation_id)

    def test_registered_mock_failure_renders_blocked_desktop_state(self) -> None:
        self._assert_registered_mock_failure_renders_blocked_desktop_state(
            "process_failure", partial_output=False,
        )

    def test_registered_mock_partial_output_failure_renders_blocked_desktop_state(self) -> None:
        self._assert_registered_mock_failure_renders_blocked_desktop_state(
            "partial_output_failure", partial_output=True,
        )

    def test_registered_mock_empty_response_renders_blocked_desktop_state(self) -> None:
        self._assert_registered_mock_failure_renders_blocked_desktop_state(
            "empty_response", partial_output=False,
        )

    def test_registered_mock_rejections_render_blocked_desktop_state(self) -> None:
        for scenario in ("execution_rejection",):
            with self.subTest(scenario=scenario):
                self._assert_registered_mock_failure_renders_blocked_desktop_state(
                    scenario, partial_output=False,
                )

    def test_registered_mock_timeouts_render_blocked_desktop_state(self) -> None:
        for scenario, partial_output in (
            ("timeout", False), ("partial_output_timeout", True),
        ):
            with self.subTest(scenario=scenario):
                self._assert_registered_mock_failure_renders_blocked_desktop_state(
                    scenario, partial_output=partial_output,
                    terminal_status="timed_out", timeout_ms="2500",
                )

    def test_registered_mock_cancellations_render_blocked_desktop_state(self) -> None:
        for scenario, partial_output in (
            ("cancellation", False), ("partial_output_cancellation", True),
        ):
            with self.subTest(scenario=scenario):
                self._assert_registered_mock_failure_renders_blocked_desktop_state(
                    scenario, partial_output=partial_output,
                    terminal_status="cancelled", timeout_ms="2500",
                )

    def test_registered_mock_malformed_success_renders_scored_zero_diagnostic_state(self) -> None:
        self._activate_application_theme()
        application = BenchmarkDesktopApplication.from_repository_authority(
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        application.window.resize(1440, 1080)
        QApplication.processEvents()
        window = application.window
        self._select_runner(application, "arcgrav.mock-model.runner@1.0.0")
        self._assert_mock_configuration(application)
        self._select_mock_scenario(application, "malformed_output")
        intent = window.sidebar_input_snapshot()
        self.assertEqual("mock-base::scenario:malformed_output", intent.model)

        application.request_build_plan(intent)
        application.request_accept_plan()
        application.request_start_benchmark()
        QApplication.processEvents()
        boundary = application.shared_application_boundary
        retained = boundary.selected_terminal
        self.assertIs(AcceptedRun, type(retained))
        generation_id = retained.generation_id
        self.assertEqual("Completed · Report ready", window.run_rows[generation_id].status_badge.label)
        self.assertEqual(5, len(retained.treatment_observations))
        for raw in retained.treatment_observations:
            observation = raw if isinstance(raw, dict) else json.loads(raw)
            validate_retained_parity_observation(observation)
            self.assertEqual("completed", observation["terminal_status"])
            self.assertEqual("retained", observation["response"]["availability"])
            execution = observation["extensions"]["arcgrav.runner:execution"]
            self.assertEqual("mock-model", execution["target"]["class"])
            self.assertFalse(execution["submission"]["external_provider"])
        for raw in retained.score_artifacts:
            score = raw if isinstance(raw, dict) else json.loads(raw)
            self.assertEqual("scored", score["availability"])
            self.assertEqual(0.0, score["value"])
            self.assertIn("ARB_TREATMENT_MALFORMED", score["diagnostics"])
        self._capture_full_client_render_fixture(window, state="terminal")

        application.request_select_run(generation_id)
        QApplication.processEvents()
        self._capture_full_client_render_fixture(window, state="retained-run")
        self.assertIsNotNone(boundary.report_bundle)
        QApplication.processEvents()

        self.assertNotIn("claim_state", boundary.report_bundle.report_document)
        self.assertEqual("complete", boundary.report_state(boundary.selected_terminal.generation_id)[0])
        QApplication.processEvents()
        self.assertEqual("complete", boundary.report_state(boundary.selected_terminal.generation_id)[0])

        self.assertNotIn("claim_state", boundary.report_bundle.report_document)

    def _assert_registered_mock_failure_renders_blocked_desktop_state(
        self, scenario: str, *, partial_output: bool,
        terminal_status: str = "failed", timeout_ms: str | None = None,
    ) -> None:
        self._activate_application_theme()
        application = BenchmarkDesktopApplication.from_repository_authority(
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        application.window.resize(1440, 1080)
        QApplication.processEvents()
        window = application.window
        self._select_runner(application, "arcgrav.mock-model.runner@1.0.0")
        self._assert_mock_configuration(application)
        self._select_mock_scenario(application, scenario)
        intent = window.sidebar_input_snapshot()
        if timeout_ms is not None:
            intent = replace(
                intent,
                additional_controls=tuple(
                    control for control in intent.additional_controls
                    if control.control_name != "request_timeout_ms"
                ) + (SidebarControlInputSnapshot("request_timeout_ms", timeout_ms),),
            )
        self.assertEqual(f"mock-base::scenario:{scenario}", intent.model)

        application.request_build_plan(intent)
        application.request_accept_plan()
        if terminal_status == "cancelled":
            original_execute = MockRunner.execute
            cancelled_observations = []

            def cancel_real_worker(runner, request, **kwargs):
                # Interrupt the actual registered worker after it has had time
                # to emit partial output. The public cancellation callback is
                # independent of any provider transport or wire framing.
                deadline = time.monotonic() + 0.75
                kwargs["cancellation_requested"] = lambda: time.monotonic() >= deadline
                observation = original_execute(runner, request, **kwargs)
                cancelled_observations.append(observation)
                return observation

            with patch.object(MockRunner, "execute", cancel_real_worker):
                application.request_start_benchmark()
            self.assertEqual(5, len(cancelled_observations))
            for observation in cancelled_observations:
                extensions = observation["extensions"]
                self.assertNotIn("arcgrav.runner:process_stdout_base64", extensions)
                self.assertNotIn("arcgrav.runner:process_stderr_base64", extensions)
                self.assertEqual("cancelled", observation["terminal_status"])
        else:
            application.request_start_benchmark()
        QApplication.processEvents()
        boundary = application.shared_application_boundary
        blocked = boundary.selected_terminal
        self.assertIs(type(blocked), BlockedRun)
        generation_id = blocked.generation_id
        self.assertEqual("Failed", window.run_rows[generation_id].status_badge.label)
        self.assertEqual(generation_id, window.workspace_projection_run_id)
        self.assertEqual(5, len(blocked.treatment_observations))
        for raw in blocked.treatment_observations:
            observation = raw if isinstance(raw, dict) else json.loads(raw)
            validate_retained_parity_observation(observation)
            self.assertEqual(terminal_status, observation["terminal_status"])
            self.assertNotEqual("retained", observation["response"]["availability"])
            execution = observation["extensions"]["arcgrav.runner:execution"]
            self.assertEqual("mock-model", execution["target"]["class"])
            self.assertFalse(execution["submission"]["external_provider"])
            process_stdout = execution["process"]["stdout"]
            for channel in ("stdout", "stderr"):
                retained_channel = execution["process"][channel]
                self.assertEqual("excluded", retained_channel["availability"])
                self.assertIsNone(retained_channel["byte_length"])
                self.assertIsNone(retained_channel["sha256"])
                self.assertIsNone(retained_channel["reference"])
                self.assertNotIn("arcgrav.runner:process_" + channel + "_base64", observation["extensions"])
            self.assertEqual("not_applicable", execution["authentication"]["availability"])
        for name in WORKSPACE_TAB_LABELS:
            self.assertEqual(generation_id, window.workspace_pages[name].run_id)
        self.assertIsNone(window.workspace_pages["Reports"].projection.report_id)
        self.assertIsNone(boundary.report_bundle)
        self._capture_full_client_render_fixture(window, state="terminal")

        application.request_select_run(generation_id)
        QApplication.processEvents()
        self.assertEqual(generation_id, window.selected_run_id)
        self.assertIsNone(window.workspace_pages["Reports"].projection.report_id)
        self._capture_full_client_render_fixture(window, state="retained-run")

    def test_registered_mock_desktop_uses_common_state_without_codex_extensions(self) -> None:
        self._activate_application_theme()
        application = BenchmarkDesktopApplication.from_repository_authority(
            authentication_probe=lambda *_args: True,
            model_discovery_probe=_ready_discovery_for_source,
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        application.window.resize(1440, 1080)
        QApplication.processEvents()
        window = application.window
        window.console_widget.set_stream_live_view(True)
        self._select_runner(application, "arcgrav.mock-model.runner@1.0.0")
        self._assert_mock_configuration(application)
        self._select_mock_scenario(application, "structured_response")
        application.request_build_plan(window.sidebar_input_snapshot())
        application.request_accept_plan()

        application.request_start_benchmark()
        QApplication.processEvents()
        boundary = application.shared_application_boundary
        retained = boundary.selected_terminal
        self.assertIs(type(retained), AcceptedRun)
        self.assertEqual("Completed · Report ready", window.run_rows[retained.generation_id].status_badge.label)
        for raw in retained.treatment_observations:
            observation = json.loads(raw)
            validate_retained_parity_observation(observation)
            self.assertFalse(any(
                key.startswith("openai.codex_cli:")
                for key in observation["extensions"]
            ))
            self.assertEqual("mock-model", observation["extensions"][
                "arcgrav.runner:execution"
            ]["target"]["class"])
        progress = window.workspace_pages["Progress"]
        self.assertEqual(5, progress.projection.overall.completed_cases)
        self.assertEqual(5, progress.treatment_table.table_model.rowCount())
        self._capture_full_client_render_fixture(window, state="terminal")
        window.console_widget.set_active_tab("Diagnostics")
        self.assertIn("Treatments completed: 5/5", window.console_widget.state.visible_text)
        window.console_widget.set_active_tab("Live View")
        self.assertIn("Input:\n", window.console_widget.state.visible_text)
        self.assertIn("Output:\n", window.console_widget.state.visible_text)
        self._assert_retained_model_outputs(window, retained)
        self.assertIsNotNone(window.workspace_pages["Reports"].projection.report_id)
        QApplication.processEvents()

        self.assertNotIn("claim_state", boundary.report_bundle.report_document)
        QApplication.processEvents()
        self.assertEqual("complete", boundary.report_state(boundary.selected_terminal.generation_id)[0])

        self.assertNotIn("claim_state", boundary.report_bundle.report_document)

    def test_blocked_and_scored_zero_desktop_use_common_state_without_codex(self) -> None:
        def run(scenario: str) -> tuple[object, ...]:
            self._activate_application_theme()
            application = BenchmarkDesktopApplication.from_repository_authority(
                authentication_probe=lambda *_args: True,
                model_discovery_probe=_ready_discovery_for_source,
                application_icon=arcgrav_application_icon(),
                repository_root=_REPOSITORY_ROOT,
                authority_dispatcher=lambda operation: operation(),
            )
            self.addCleanup(application.window.deleteLater)
            application.show()
            application.window.resize(1440, 1080)
            QApplication.processEvents()
            window = application.window
            self._select_runner(application, "arcgrav.mock-model.runner@1.0.0")
            self._assert_mock_configuration(application)
            self._select_mock_scenario(application, scenario)
            application.request_build_plan(window.sidebar_input_snapshot())
            application.request_accept_plan()
            application.request_start_benchmark()
            QApplication.processEvents()
            boundary = application.shared_application_boundary
            terminal = boundary.selected_terminal
            self.assertIn(type(terminal), (AcceptedRun, BlockedRun))
            self._capture_full_client_render_fixture(window, state="terminal")
            observations = []
            for raw in terminal.treatment_observations:
                observation = raw if isinstance(raw, dict) else json.loads(raw)
                validate_retained_parity_observation(observation)
                self.assertFalse(any(
                    key.startswith("openai.codex_cli:")
                    for key in observation["extensions"]
                ))
                observations.append(observation)
            application.request_select_run(terminal.generation_id)
            QApplication.processEvents()
            self._capture_full_client_render_fixture(window, state="retained-run")
            report_available = boundary.report_bundle is not None
            overall = window.workspace_pages["Progress"].projection.overall
            signature = (
                type(terminal).__name__,
                window.run_rows[terminal.generation_id].status_badge.label,
                overall.completed_cases if overall is not None else None,
                window.console_widget.state.raw_response_available,
                report_available,
                tuple((
                    observation["terminal_status"],
                    observation["response"]["availability"],
                    observation["extensions"]["arcgrav.runner:execution"]["process"]["stdout"]["availability"],
                    observation["extensions"]["arcgrav.runner:execution"]["process"]["stderr"]["availability"],
                ) for observation in observations),
            )
            if type(terminal) is AcceptedRun:
                self.assertTrue(report_available)
                QApplication.processEvents()
                self.assertEqual("passed", window.workspace_pages["Reports"].projection.verification_state)
                return signature + (
                    boundary.report_state(terminal.generation_id)[0],
                    False,
                )
            self.assertFalse(report_available)
            self.assertIsNone(boundary.report_bundle)
            return signature + (None, False)

        for scenario in ("process_failure", "malformed_output"):
            with self.subTest(scenario=scenario):
                signature = run(scenario)
                expected = ("BlockedRun", "Failed", False) if scenario == "process_failure" else (
                    "AcceptedRun", "Completed · Report ready", True)
                self.assertEqual(expected[0], signature[0])
                self.assertEqual(expected[1], signature[1])
                self.assertEqual(expected[2], signature[4])
                self.assertEqual(5, len(signature[5]))

    def test_mock_live_switch_replaces_discovered_model_and_adapter_configuration(self) -> None:
        self._activate_application_theme()
        live_ready = {"executable": True, "authentication": True, "catalog": True}

        def resolve_executable(name: str) -> str | None:
            if name == "codex":
                return "/controlled/codex" if live_ready["executable"] else None
            candidate = _REPOSITORY_ROOT / name
            return str(candidate) if candidate.is_file() else None

        def discover_model(source, selected_control_values=None):
            if source.registration["registration_id"] == "openai.codex-cli":
                return _offline_codex_model_discovery() if live_ready["catalog"] else {
                    "status": "unsupported", "error_code": "codex_cli_authentication_failed",
                    "provider_submitted": False,
                }
            return probe_registered_runner_model_discovery(
                source,
                repository_root=_REPOSITORY_ROOT,
                selected_control_values=selected_control_values,
                executable_resolver=resolve_executable,
            )

        application = BenchmarkDesktopApplication.from_repository_authority(
            application_icon=arcgrav_application_icon(),
            repository_root=_REPOSITORY_ROOT,
            executable_resolver=resolve_executable,
            authentication_probe=lambda *_args: live_ready["authentication"],
            model_discovery_probe=discover_model,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        QApplication.processEvents()
        window = application.window
        mock_label = "arcgrav.mock-model.runner@1.0.0"
        live_label = "openai.codex-cli@2.0.0"
        window.console_widget.set_active_tab("Environment")

        self._select_runner(application, mock_label)
        self._assert_mock_configuration(application)
        self._select_mock_scenario(application, "process_failure")
        self.assertEqual(
            "mock-base::scenario:process_failure",
            window.sidebar_input_snapshot().model,
        )

        self._select_runner(application, live_label)
        self._select_native_launch(application)
        self.assertEqual(
            ("Default (GPT-5.6)", "GPT-5.6 Mini"),
            window.model_input.options,
        )
        self.assertEqual("gpt-5.6", window.sidebar_input_snapshot().model)
        self.assertEqual("codex", window.additional_control_inputs["codex_binary"].value)
        self.assertEqual("", window.credential_input.value)
        self.assertEqual(application.environment_projection.render(), window.console_widget.state.visible_text)
        self.assertEqual(live_label, next(entry.details for entry in application.environment_projection.entries if entry.source == "Runner"))
        live_environment = application.environment_projection.render()
        self.assertNotIn(mock_label, live_environment)
        self.assertNotIn(
            "Mock Base / process failure", window.model_input.options,
        )

        self._select_runner(application, mock_label)
        self._assert_mock_configuration(application)
        self.assertIn("Mock Base / process failure", window.model_input.options)
        self.assertEqual("mock-base", window.sidebar_input_snapshot().model)
        self.assertNotIn("codex_binary", window.additional_control_inputs)
        self.assertNotIn("launch_mode", window.additional_control_inputs)
        self.assertEqual("", window.credential_input.value)
        self.assertEqual(application.environment_projection.render(), window.console_widget.state.visible_text)
        self.assertNotIn(live_label, application.environment_projection.render())
        self.assertNotIn("Prerequisite runner-authentication", {entry.source for entry in application.environment_projection.entries})
        self.assertNotIn("Default (GPT-5.6)", window.model_input.options)
        self.assertEqual(
            mock_label,
            next(
                entry.details for entry in application.environment_projection.entries
                if entry.source == "Runner"
            ),
        )
        live_ready.update(executable=False, authentication=False, catalog=False)
        self._select_runner(application, live_label)
        self._select_native_launch(application)
        self.assertEqual((), window.model_input.options)
        sources = {entry.source for entry in application.environment_projection.entries}
        self.assertIn("Prerequisite runner-executable", sources)
        # This registration delegates authentication to the selected Codex
        # session; a session refusal is a discovery diagnostic, with no
        # benchmark-owned credential selector or duplicate auth prerequisite.
        self.assertNotIn("Prerequisite runner-authentication", sources)
        self.assertIn("Prerequisite runner-model-discovery", sources)
        self.assertNotIn(mock_label, application.environment_projection.render())
        self.assertFalse(window.build_plan_button.isEnabled())
        self._select_runner(application, mock_label)
        self._assert_mock_configuration(application)
        self.assertIn("Mock Base / process failure", window.model_input.options)
        sources = {entry.source for entry in application.environment_projection.entries}
        self.assertTrue({"Prerequisite runner-executable", "Prerequisite runner-authentication", "Prerequisite runner-model-discovery"}.isdisjoint(sources), sources)
        self.assertNotIn("codex_cli_authentication_failed", application.environment_projection.render())
        self.assertNotIn(live_label, application.environment_projection.render())
        self.assertTrue(window.build_plan_button.isEnabled())

    def test_environment_projection_failure_is_visible_and_never_ready(self) -> None:
        resolver = _InertResolver()
        with patch(
            "AgMark.gui.application.derive_application_environment",
            side_effect=RuntimeError("token=projection-secret"),
        ):
            application = self._compose(resolver)

        application.window.console_widget.set_active_tab("Environment")
        QApplication.processEvents()

        environment_text = application.window.console_widget.state.visible_text
        self.assertTrue(application.environment_projection.has_blockers)
        self.assertIn("Environment Projection", environment_text)
        self.assertIn("Environment projection could not be produced.", environment_text)
        self.assertIn("token=<redacted>", environment_text)
        self.assertNotIn("projection-secret", environment_text)
        self.assertEqual(
            "Environment projection failed",
            application.window.application_readiness_status.label,
        )
        self.assertEqual("error", application.window.application_readiness_status.tone)
        self.assertNotEqual("success", application.window.application_readiness_status.tone)
        self.assertEqual([], resolver.calls)

    def test_real_cli_preflight_diagnostics_are_actionable_and_block_build_plan(self) -> None:
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        for source in (_credential_cli_source(authority),):
            with self.subTest(runner=source.registration["registration_id"]):
                resolver = _InertResolver()
                application = self._compose(
                    resolver,
                    executable_resolver=lambda _name: None,
                    model_discovery_probe=lambda *_args: None,
                )
                self._select_runner(application, _source_label(source))
                self._select_native_launch(application)

                self.assertEqual(
                    1,
                    len(application.window.prerequisite_diagnostic_widgets),
                )
                pointer = application.window.prerequisite_diagnostic_widgets[0]
                diagnostic_names = set(pointer.property("diagnosticNames") or ())
                self.assertIn("runner-executable", diagnostic_names)
                self.assertNotIn("runner-authentication", diagnostic_names)
                self.assertIn("runner-model-discovery", diagnostic_names)
                self.assertEqual(
                    "Error; see Console → Environment",
                    pointer.accessibleName(),
                )
                self.assertEqual("Environment", pointer.property("consoleView"))
                self.assertNotIn(
                    "authentication",
                    pointer.accessibleDescription().lower(),
                )

                self.assertFalse(application.window.build_plan_button.isEnabled())
                application.window.resize(1440, 1080)
                QApplication.processEvents()
                self._assert_unavailable_progress_workspace(application.window)
                application.window.build_plan_button.click()
                QApplication.processEvents()
                self.assertEqual([], resolver.calls)

    def test_selected_benchmark_evidence_destination_blocker_reaches_desktop_action_gate(self) -> None:
        resolver = _InertResolver()
        with TemporaryDirectory() as temporary_root:
            application, _authority = self._compose_repository_session(
                resolver,
                readiness_repository_root=Path(temporary_root),
                executable_resolver=lambda name: f"/validated/{name}",
                authentication_probe=lambda _source: True,
            )

            self.assertEqual(
                1,
                len(application.window.prerequisite_diagnostic_widgets),
            )
            blocker = application.window.prerequisite_diagnostic_widgets[0]
            self.assertIn(
                "benchmark-evidence-destination",
                set(blocker.property("diagnosticNames") or ()),
            )
            self.assertEqual(
                "Error; see Console → Environment",
                blocker.accessibleName(),
            )
            self.assertEqual("Environment", blocker.property("consoleView"))
            self.assertFalse(application.window.build_plan_button.isEnabled())
            application.window.build_plan_button.click()
            QApplication.processEvents()
            self.assertEqual([], resolver.calls)


if __name__ == "__main__":
    unittest.main()
