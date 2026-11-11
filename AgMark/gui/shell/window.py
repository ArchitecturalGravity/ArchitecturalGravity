"""Persistent presentation shell for the ArcGrav desktop benchmarking GUI.

This module owns only desktop composition and presentation-only shell state. It
does not construct benchmark identity, lifecycle authority, execution
sequencing, evidence, reports, or verification state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from math import isfinite
from threading import Thread

from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS
from AgMark.gui.design_system.status import DEFAULT_STATUS_STYLES
from AgMark.gui.shell.registration_choices import registration_choices
from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    compact_splitter_handle_extent,
    semantic_icon,
)
from AgMark.gui.widgets.buttons import (
    ActionButton,
    PYSIDE6_AVAILABLE as BUTTONS_PYSIDE6_AVAILABLE,
)
from AgMark.gui.widgets.console import (
    BottomConsoleWidget,
    CONSOLE_TABS,
    PYSIDE6_AVAILABLE as CONSOLE_PYSIDE6_AVAILABLE,
)
from AgMark.gui.widgets.containers import (
    CardWidget,
    PYSIDE6_AVAILABLE as CONTAINERS_PYSIDE6_AVAILABLE,
)
from AgMark.gui.widgets.inputs import (
    CredentialInput,
    NumericInput,
    PYSIDE6_AVAILABLE as INPUTS_PYSIDE6_AVAILABLE,
    SelectInput,
)
from AgMark.gui.widgets.status import (
    PYSIDE6_AVAILABLE as STATUS_PYSIDE6_AVAILABLE,
    StatusDropdownButton,
)
from AgMark.gui.widgets.tabs import (
    PYSIDE6_AVAILABLE as TABS_PYSIDE6_AVAILABLE,
    TabWidget,
)

try:
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtWidgets import (
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QLayout,
        QMainWindow,
        QMenu,
        QProgressBar,
        QMessageBox,
        QScrollArea,
        QSizePolicy,
        QSplitter,
        QStatusBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = (
        BUTTONS_PYSIDE6_AVAILABLE
        and CONSOLE_PYSIDE6_AVAILABLE
        and CONTAINERS_PYSIDE6_AVAILABLE
        and INPUTS_PYSIDE6_AVAILABLE
        and STATUS_PYSIDE6_AVAILABLE
        and TABS_PYSIDE6_AVAILABLE
    )


APP_VERSION = "1.0.0-alpha"
WINDOW_TITLE = f"Architectural Gravity Benchmark - Ver. {APP_VERSION}"
REFERENCE_WINDOW_WIDTH = 1440
REFERENCE_WINDOW_HEIGHT = 1080
REFERENCE_SIDEBAR_WIDTH = 300
MINIMUM_RESPONSIVE_SIDEBAR_WIDTH = 180
MINIMUM_TAB_CONTENT_WIDTH = 560
MINIMUM_TAB_CONTENT_HEIGHT = 240
REFERENCE_CONFIGURATION_VIEWPORT_HEIGHT = 260
REFERENCE_CONSOLE_HEIGHT = 260
SHELL_WINDOW_WIDTH_KEY = "shell/window_width"
SHELL_WINDOW_HEIGHT_KEY = "shell/window_height"
SHELL_SIDEBAR_WIDTH_KEY = "shell/sidebar_width"
SHELL_WORKSPACE_TAB_KEY = "shell/workspace_tab"
SHELL_CONSOLE_TAB_KEY = "shell/console_tab"
SHELL_CONSOLE_EXPANDED_KEY = "shell/console_expanded"
SIDEBAR_SECTION_ORDER = (
    "Build Plan",
    "Benchmark",
    "Runner",
    "Configuration",
    "Runs",
)
CURRENT_RUN_BOUNDARY_LABELS = (
    "Benchmark:",
    "Runner:",
    "Model:",
)
CURRENT_RUN_PLAN_LABELS = (
    "Treatments",
    "Cases",
    "Execution",
    "Evaluation",
)
CURRENT_RUN_EMPTY_TITLE = "No current plan or run"
CURRENT_RUN_EMPTY_MESSAGE = (
    "No current plan or run is available. "
    "Use Build Plan when prerequisites are satisfied."
)
WORKSPACE_EMPTY_STATE_TITLE_TEMPLATE = "{label} unavailable"
WORKSPACE_EMPTY_STATE_MESSAGE_TEMPLATE = (
    "No authoritative {label} projection is available for the current workspace selection."
)
SIDEBAR_PREREQUISITE_OPERATIONS = ("planning", "acceptance", "execution")
SIDEBAR_PREREQUISITE_SCOPE_LABELS = {
    "planning": "Planning prerequisite",
    "acceptance": "Acceptance prerequisite",
    "execution": "Execution readiness",
}



from .command_router import ShellCommandRouter
from .input_snapshot import SidebarControlInputSnapshot, SidebarInputSnapshot
from .preferences import (
    _stored_bool,
    _stored_console_tab,
    _stored_positive_int,
    _stored_tab_index,
)
from .current_run import CurrentRunPanelMixin
if PYSIDE6_AVAILABLE:
    from .current_run import CurrentRunScrollArea
from .retained_runs import _RetainedRunRow
from .sidebar import SidebarControllerMixin
from .projections import (
    WORKSPACE_TAB_LABELS,
    CurrentRunProjection,
    ExecutionBoundaryProjection,
    NumericInputProjection,
    RetainedRunProjection,
    RunPlanProjection,
    SidebarChoiceControlProjection,
    SidebarModelChoiceProjection,
    SidebarNumericControlProjection,
    SidebarPrerequisiteDiagnosticProjection,
    SidebarProjection,
    SidebarResolvedTextProjection,
    SidebarTextControlProjection,
    WorkspaceProjection,
    _require_bool,
    _require_non_empty,
    _selected_option,
    _visible_options,
)

if PYSIDE6_AVAILABLE:

    class _FixedWidthRunnerButton(StatusDropdownButton):
        """Keep status readable without allowing long runner names to widen the sidebar."""

        def _update_status_text(self) -> None:
            super()._update_status_text()
            overflow = self.sizeHint().width() - self.width()
            if overflow <= 0:
                return
            metrics = self.fontMetrics()
            if self._context_label is not None:
                context = metrics.elidedText(
                    self._context_label, Qt.TextElideMode.ElideRight,
                    max(0, metrics.horizontalAdvance(self._context_label) - overflow),
                )
                self.setText(f"{context}: {self.label}" if context else self.label)
            else:
                self.setText(metrics.elidedText(
                    self.label, Qt.TextElideMode.ElideRight,
                    max(0, metrics.horizontalAdvance(self.label) - overflow),
                ))
            # setText leaves the full accessible name assigned by the base intact.

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            if hasattr(self, "_status"):
                self._update_status_text()


    class _WorkspaceScrollArea(QScrollArea):
        """Bound the shell to its viewport; content overflow belongs to individual tabs."""

        def setWidget(self, widget: QWidget) -> None:
            super().setWidget(widget)
            self._resize_workspace_canvas()

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            self._resize_workspace_canvas()

        def _resize_workspace_canvas(self) -> None:
            canvas = self.widget()
            if canvas is None:
                return
            viewport_size = self.viewport().size()
            target_width = viewport_size.width()
            target_height = viewport_size.height()
            summary = canvas.findChild(QScrollArea, "currentRunScroll")
            if summary is not None and summary.widget() is not None:
                summary._refresh_summary_height(target_width, target_height)
            if canvas.width() != target_width or canvas.height() != target_height:
                canvas.resize(target_width, target_height)


    class _TabContentScrollArea(QScrollArea):
        """Pass available width to responsive pages, keeping their floors local."""

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            page = self.widget()
            if page is not None and hasattr(page, "set_available_width"):
                page.set_available_width(self.viewport().width())


    class BenchmarkShellWindow(SidebarControllerMixin, CurrentRunPanelMixin, QMainWindow):
        """Native desktop shell with presentation-only persistent regions."""

        def __init__(
            self,
            *,
            application_icon: QIcon,
            connectivity_label: str = "Runner not selected",
            connectivity_tone: str = "neutral",
            application_status_label: str = "Application status unavailable",
            application_status_tone: str = "neutral",
            shell_preferences: MutableMapping[str, object] | None = None,
            console_preferences: MutableMapping[str, int] | None = None,
            sidebar_projection: SidebarProjection | None = None,
            current_run_projection: CurrentRunProjection | None = None,
            retained_workspace_projections: Mapping[str, WorkspaceProjection] | None = None,
            on_benchmark_selected: RunSelectionOperation | None = None,
            on_runner_selected: RunSelectionOperation | None = None,
            on_sidebar_intent_changed: SidebarIntentOperation | None = None,
            on_build_plan: BuildPlanOperation | None = None,
            on_test_runner: TestRunnerOperation | None = None,
            on_check_runner: SidebarIntentOperation | None = None,
            on_run_selected: RunSelectionOperation | None = None,
            on_delete_run: RunSelectionOperation | None = None,
            on_accept_plan: LifecycleOperation | None = None,
            on_start_benchmark: LifecycleOperation | None = None,
            command_dispatcher: CommandDispatcher | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            _require_non_empty(connectivity_label, name="connectivity_label")
            _require_non_empty(connectivity_tone, name="connectivity_tone")
            _require_non_empty(application_status_label, name="application_status_label")
            _require_non_empty(application_status_tone, name="application_status_tone")
            if not isinstance(application_icon, QIcon) or application_icon.isNull():
                raise ValueError("application_icon must be a non-null QIcon")
            if shell_preferences is not None and not isinstance(
                shell_preferences,
                MutableMapping,
            ):
                raise ValueError("shell_preferences must be a mutable mapping or None")
            self._shell_preferences = shell_preferences
            restored_width = _stored_positive_int(
                shell_preferences,
                SHELL_WINDOW_WIDTH_KEY,
                REFERENCE_WINDOW_WIDTH,
            )
            restored_height = _stored_positive_int(
                shell_preferences,
                SHELL_WINDOW_HEIGHT_KEY,
                REFERENCE_WINDOW_HEIGHT,
            )
            restored_workspace_tab = _stored_tab_index(
                shell_preferences,
                SHELL_WORKSPACE_TAB_KEY,
            )
            restored_console_tab = _stored_console_tab(
                shell_preferences,
                SHELL_CONSOLE_TAB_KEY,
                CONSOLE_TABS[0],
            )
            restored_console_expanded = _stored_bool(
                shell_preferences,
                SHELL_CONSOLE_EXPANDED_KEY,
                False,
            )
            if on_benchmark_selected is not None and not callable(on_benchmark_selected):
                raise ValueError("on_benchmark_selected must be callable or None")
            if on_runner_selected is not None and not callable(on_runner_selected):
                raise ValueError("on_runner_selected must be callable or None")
            if (
                on_sidebar_intent_changed is not None
                and not callable(on_sidebar_intent_changed)
            ):
                raise ValueError(
                    "on_sidebar_intent_changed must be callable or None"
                )
            if on_build_plan is not None and not callable(on_build_plan):
                raise ValueError("on_build_plan must be callable or None")
            if on_test_runner is not None and not callable(on_test_runner):
                raise ValueError("on_test_runner must be callable or None")
            if on_run_selected is not None and not callable(on_run_selected):
                raise ValueError("on_run_selected must be callable or None")
            if on_delete_run is not None and not callable(on_delete_run):
                raise ValueError("on_delete_run must be callable or None")
            if on_accept_plan is not None and not callable(on_accept_plan):
                raise ValueError("on_accept_plan must be callable or None")
            if on_start_benchmark is not None and not callable(on_start_benchmark):
                raise ValueError("on_start_benchmark must be callable or None")
            if command_dispatcher is not None and not callable(command_dispatcher):
                raise ValueError("command_dispatcher must be callable or None")

            projection = sidebar_projection or SidebarProjection()
            if not isinstance(projection, SidebarProjection):
                raise ValueError("sidebar_projection must be SidebarProjection or None")
            self._sidebar_projection = projection
            self._requested_connectivity_status = (
                connectivity_label,
                connectivity_tone,
            )
            self._requested_application_status = (
                application_status_label,
                application_status_tone,
            )
            if projection.build_plan_effectively_available and on_build_plan is None:
                raise ValueError(
                    "on_build_plan is required when build_plan_available is true"
                )

            if retained_workspace_projections is None:
                workspace_projections: dict[str, WorkspaceProjection] = {}
            else:
                if not isinstance(retained_workspace_projections, Mapping):
                    raise ValueError(
                        "retained_workspace_projections must be a mapping or None"
                    )
                workspace_projections = dict(retained_workspace_projections)
                run_ids = {run.run_id for run in projection.runs}
                if set(workspace_projections) != run_ids:
                    raise ValueError(
                        "retained_workspace_projections must cover exactly the "
                        "supplied retained run IDs"
                    )
                if any(
                    not isinstance(value, WorkspaceProjection)
                    for value in workspace_projections.values()
                ):
                    raise ValueError(
                        "retained_workspace_projections values must be "
                        "WorkspaceProjection instances"
                    )
                for workspace_projection in workspace_projections.values():
                    pages = workspace_projection.ordered_pages
                    if any(not isinstance(page, QWidget) for page in pages):
                        raise ValueError(
                            "WorkspaceProjection pages must be QWidget instances"
                        )
                    if len({id(page) for page in pages}) != len(pages):
                        raise ValueError(
                            "WorkspaceProjection pages must be distinct widgets"
                        )

            current_run = current_run_projection
            if current_run is not None and not isinstance(
                current_run,
                CurrentRunProjection,
            ):
                raise ValueError(
                    "current_run_projection must be CurrentRunProjection or None"
                )
            if (
                current_run is not None
                and current_run.accept_plan_available
                and on_accept_plan is None
            ):
                raise ValueError(
                    "on_accept_plan is required when accept_plan_available is true"
                )
            if (
                current_run is not None
                and current_run.start_benchmark_available
                and on_start_benchmark is None
            ):
                raise ValueError(
                    "on_start_benchmark is required when "
                    "start_benchmark_available is true"
                )
            if (
                current_run is not None
                and current_run.delete_run_available
                and on_delete_run is None
            ):
                raise ValueError(
                    "on_delete_run is required when delete_run_available is true"
                )

            self._on_benchmark_selected = on_benchmark_selected
            self._on_runner_selected = on_runner_selected
            self._on_sidebar_intent_changed = on_sidebar_intent_changed
            self._operation_labels = ()
            self._operation_locks_controls = False
            self._treatment_exclusion_scope: tuple[str | None, str] | None = None
            self._excluded_treatments: set[str] = set()
            self._on_build_plan = on_build_plan
            if on_check_runner is not None and not callable(on_check_runner):
                raise ValueError("on_check_runner must be callable or None")
            self._on_check_runner = on_check_runner
            self._on_test_runner = on_test_runner
            self._on_run_selected = on_run_selected
            self._on_delete_run = on_delete_run
            self._on_accept_plan = on_accept_plan
            self._on_start_benchmark = on_start_benchmark
            self._command_router = ShellCommandRouter(
                command_dispatcher=command_dispatcher,
                on_build_plan=on_build_plan,
                on_test_runner=on_test_runner,
                on_run_selected=on_run_selected,
                on_delete_run=on_delete_run,
                on_accept_plan=on_accept_plan,
                on_start_benchmark=on_start_benchmark,
            )
            self._retained_workspace_projections = workspace_projections

            self._runner_check_pending = False
            self.runner_menu = QMenu(self)
            self.runner_menu.setAccessibleName("Runner actions")
            self.runner_test_action = QAction("Test", self.runner_menu)
            self.runner_test_action.triggered.connect(self._invoke_test_runner)
            self.runner_menu.addAction(self.runner_test_action)
            self.runner_check_action = QAction("Check", self.runner_menu)
            self.runner_check_action.triggered.connect(self._invoke_check_runner)
            self.runner_menu.addAction(self.runner_check_action)
            self.runner_menu.aboutToShow.connect(self._refresh_runner_menu_availability)

            self.setWindowTitle(WINDOW_TITLE)
            self.setWindowIcon(application_icon)
            self.resize(restored_width, restored_height)

            self.upper_work_area = QWidget(self)
            self.upper_work_area.setObjectName("upperWorkArea")
            self.upper_work_area.setAccessibleName("Benchmark work area")
            upper_layout = QHBoxLayout(self.upper_work_area)
            upper_layout.setContentsMargins(0, 0, 0, 0)
            upper_layout.setSpacing(0)
            self.upper_layout = upper_layout

            self.sidebar = QFrame(self.upper_work_area)
            self.sidebar.setObjectName("benchmarkSidebar")
            self.sidebar.setAccessibleName("Benchmark configuration and runs")
            self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
            self.sidebar.setStyleSheet(
                "QFrame#benchmarkSidebar { border: 0; "
                f"border-right: 1px solid {DEFAULT_LIGHT_THEME.color('text-muted')}; }}"
            )
            self.sidebar.setFixedWidth(REFERENCE_SIDEBAR_WIDTH)
            self.sidebar.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Expanding,
            )
            self._populate_sidebar(projection)
            upper_layout.addWidget(self.sidebar)

            self.workspace_column = QWidget(self.upper_work_area)
            self.workspace_column.setObjectName("workspaceColumn")
            self.workspace_column.setMinimumSize(0, 0)
            workspace_column_layout = QVBoxLayout(self.workspace_column)
            workspace_column_layout.setContentsMargins(0, 0, 0, 0)
            workspace_column_layout.setSpacing(0)
            self.workspace_scroll = _WorkspaceScrollArea(self.workspace_column)
            self.workspace_scroll.setObjectName("benchmarkWorkspaceScroll")
            self.workspace_scroll.setAccessibleName("Benchmark workspace viewport")
            self.workspace_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.workspace_scroll.setWidgetResizable(False)
            self.workspace_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.workspace_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.workspace_scroll.setMinimumSize(0, 0)
            self.workspace_scroll.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self.workspace_scroll.viewport().setObjectName(
                "benchmarkWorkspaceViewport"
            )

            self.workspace = QFrame()
            self.workspace.setObjectName("benchmarkWorkspace")
            self.workspace.setAccessibleName("Benchmark workspace")
            self.workspace.setFrameShape(QFrame.Shape.NoFrame)
            self.workspace.setMinimumSize(0, 0)
            self.workspace.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Ignored,
            )
            self.workspace_layout = QVBoxLayout(self.workspace)
            self.workspace_layout.setContentsMargins(0, 0, 0, 0)
            self.workspace_layout.setSpacing(0)
            self.workspace_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

            self.current_run_scroll = CurrentRunScrollArea(self.workspace)
            self.current_run_scroll.setObjectName("currentRunScroll")
            self.current_run_scroll.setAccessibleName("Current run summary viewport")
            self.current_run_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.current_run_scroll.setWidgetResizable(True)
            self.current_run_scroll.setMinimumSize(0, 0)
            self.current_run_scroll.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
            )
            self.workspace_layout.addWidget(self.current_run_scroll)
            self._populate_current_run(current_run)

            selected_run_id = next(
                (run.run_id for run in projection.runs if run.selected),
                None,
            )
            initial_workspace_projection = (
                workspace_projections.get(selected_run_id)
                if selected_run_id is not None
                else None
            )
            self._workspace_projection_run_id = (
                selected_run_id if initial_workspace_projection is not None else None
            )
            self.workspace_pages: dict[str, QWidget] = {}
            workspace_tab_entries: list[tuple[str, QWidget]] = []
            if initial_workspace_projection is None:
                for label in WORKSPACE_TAB_LABELS:
                    page = self._create_workspace_empty_state_page(label)
                    self.workspace_pages[label] = page
                    workspace_tab_entries.append((label, self._wrap_workspace_page(label, page)))
            else:
                for label, page in zip(
                    WORKSPACE_TAB_LABELS,
                    self._workspace_page_order(initial_workspace_projection),
                    strict=True,
                ):
                    if not page.accessibleName():
                        page.setAccessibleName(f"{label} workspace")
                    self.workspace_pages[label] = page
                    workspace_tab_entries.append((label, self._wrap_workspace_page(label, page)))

            self.workspace_tabs = TabWidget(
                tuple(workspace_tab_entries),
                selected_index=restored_workspace_tab,
                parent=self.workspace,
            )
            self.workspace_tabs.setAccessibleName("Benchmark workspace tabs")
            self.workspace_tabs.setObjectName("workspaceTabs")
            # Match navigation to the common content viewport inset.
            tab_inset = DEFAULT_LAYOUT_METRICS.metric("page-padding")
            self.workspace_tabs.setStyleSheet(
                self.workspace_tabs.styleSheet()
                + f"QTabWidget#workspaceTabs::tab-bar {{ left: {tab_inset}px; }}"
                + 'QTabBar[arcgravSemanticComponent="tab-bar"]::tab:disabled { color: #929AA6; }'
            )
            self.workspace_tabs.currentChanged.connect(
                self._on_workspace_tab_changed
            )
            self.workspace_tabs.setMinimumSize(0, 0)
            self.workspace_tabs.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
            )
            self._apply_workspace_tab_visibility()
            self.workspace_layout.addWidget(self.workspace_tabs, 1)
            self.workspace_scroll.setWidget(self.workspace)
            workspace_column_layout.addWidget(self.workspace_scroll, 1)
            upper_layout.addWidget(self.workspace_column, 1)

            self.console_widget = BottomConsoleWidget(
                preferences=console_preferences,
                default_expanded_height=REFERENCE_CONSOLE_HEIGHT,
                parent=self,
            )
            self.console_widget.setObjectName("bottomConsole")
            self.console_widget.setAccessibleName("Bottom console")
            self.console_widget.set_active_tab(restored_console_tab)
            self.console_widget.activeTabChanged.connect(
                self._on_console_tab_changed
            )

            self.vertical_splitter = QSplitter(Qt.Orientation.Vertical, self)
            self.vertical_splitter.setObjectName("workspaceConsoleSplitter")
            self.vertical_splitter.setChildrenCollapsible(False)
            self.vertical_splitter.setHandleWidth(
                compact_splitter_handle_extent()
            )
            self.vertical_splitter.addWidget(self.upper_work_area)
            self.vertical_splitter.addWidget(self.console_widget)
            self.vertical_splitter.setStretchFactor(0, 1)
            self.vertical_splitter.setStretchFactor(1, 0)
            self.vertical_splitter.setSizes(
                [
                    REFERENCE_WINDOW_HEIGHT - REFERENCE_CONSOLE_HEIGHT,
                    self.console_widget.state.last_nonzero_expanded_height,
                ]
            )
            self.vertical_splitter.splitterMoved.connect(self._on_splitter_moved)
            self.console_widget.expandedHeightRequested.connect(
                self._restore_console_height
            )
            self.console_widget.expandedChanged.connect(
                self._on_console_expanded_changed
            )
            self.console_widget.set_expanded(restored_console_expanded)

            self.shell_status_bar = QStatusBar(self)
            self.shell_status_bar.setObjectName("shellStatusBar")
            self.shell_status_bar.setAccessibleName("Application status")
            self.shell_status_bar.setSizeGripEnabled(False)
            page_padding = DEFAULT_LAYOUT_METRICS.metric("page-padding")
            # QStatusBar supplies a two-pixel leading item gap itself.
            self.shell_status_bar.setContentsMargins(page_padding - 2, 0, page_padding, 0)
            self.shell_content = QWidget(self)
            shell_layout = QVBoxLayout(self.shell_content)
            shell_layout.setContentsMargins(0, 0, 0, 0)
            shell_layout.setSpacing(0)
            # Each column owns its header height; the short status bar must not
            # reserve the two-button stack's height above the workspace.
            workspace_column_layout.insertWidget(0, self.shell_status_bar)
            shell_layout.addWidget(self.vertical_splitter, 1)
            self.setCentralWidget(self.shell_content)

            self.connectivity_status = _FixedWidthRunnerButton(
                connectivity_label,
                connectivity_tone,
                parent=self.sidebar_header,
            )
            self.connectivity_status.setAccessibleDescription("Connectivity status")
            self._set_connectivity_runner_name(projection)
            self.connectivity_status.setMenu(self.runner_menu)
            self.connectivity_status.setMinimumHeight(self.build_plan_button.minimumHeight())
            self.sidebar_header.layout().insertWidget(0, self.connectivity_status)

            self._apply_application_status()

            self.operation_banner = QFrame(self.shell_status_bar)
            self.operation_banner.setObjectName("statusBarActivity")
            busy_layout = QHBoxLayout(self.operation_banner)
            busy_layout.setContentsMargins(0, 0, 0, 0)
            self.operation_label = QLabel(self.operation_banner)
            self.operation_label.setMinimumWidth(0)
            self.operation_label.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
            )
            self.operation_label.setAccessibleName("Operation in progress")
            from AgMark.gui.widgets.activity import BlueActivitySpinner
            self.operation_progress = BlueActivitySpinner(self.operation_banner)
            busy_layout.addWidget(self.operation_progress)
            busy_layout.addWidget(self.operation_label, 1)
            self.cancel_execution_button = ActionButton(
                "Cancel", "secondary", content_sized=True, parent=self.operation_banner
            )
            self.cancel_execution_button.setAccessibleName("Cancel benchmark")
            self.cancel_execution_button.setVisible(False)
            busy_layout.addWidget(self.cancel_execution_button)
            self.shell_status_bar.addWidget(self.operation_banner, 1)
            self.operation_banner.hide()

            # Reserve the activity row's height even when no operation is pending.
            self.shell_status_bar.setMinimumHeight(
                max(self.shell_status_bar.sizeHint().height(),
                    self.operation_banner.sizeHint().height() + 4)
            )
            self._configure_keyboard_focus_order()

        def _wrap_workspace_page(self, label: str, page: QWidget) -> QScrollArea:
            """Own one consistent inset around idle and projected page content."""
            page.setMinimumSize(
                max(getattr(page, "minimum_viewport_width", MINIMUM_TAB_CONTENT_WIDTH), page.minimumWidth()),
                max(MINIMUM_TAB_CONTENT_HEIGHT, page.minimumHeight()),
            )
            scroll = _TabContentScrollArea(self.workspace)
            scroll.setObjectName("workspaceTabScroll")
            scroll.setAccessibleName(f"{label} content viewport")
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            # Padding belongs to the shell, not individual projection views.
            # Viewport margins preserve page identity and give responsive
            # width calculations the actual inset content area.
            padding = DEFAULT_LAYOUT_METRICS.metric("page-padding")
            scroll.setViewportMargins(padding, padding, padding, padding)
            scroll.setWidgetResizable(True)
            scroll.setMinimumSize(0, 0)
            scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            scroll.setWidget(page)
            return scroll

        def _release_workspace_page(self, index: int) -> None:
            scroll = self.workspace_tabs.widget(index)
            self.workspace_tabs.removeTab(index)
            if isinstance(scroll, QScrollArea):
                # Projections own their pages and may install them again later.
                page = scroll.takeWidget()
                if page is not None:
                    page.setParent(None)
                scroll.deleteLater()

        def _create_workspace_empty_state_page(self, label: str) -> QWidget:
            """Create one deliberate presentation-only page for missing projection state."""

            label = _require_non_empty(label, name="workspace label")
            page = QWidget(self.workspace)
            page.setObjectName(f"{label.lower()}WorkspacePage")
            page.setAccessibleName(f"{label} workspace")
            page.setProperty("authoritySemantics", "presentation-only")
            page.setProperty("projectionState", "unavailable")

            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(0)

            empty_content = QWidget(page)
            empty_layout = QVBoxLayout(empty_content)
            empty_layout.setContentsMargins(0, 0, 0, 0)
            empty_layout.setSpacing(0)

            empty_message = QLabel(
                WORKSPACE_EMPTY_STATE_MESSAGE_TEMPLATE.format(label=label),
                empty_content,
            )
            empty_message.setObjectName("workspaceEmptyStateMessage")
            empty_message.setAccessibleName(f"{label} unavailable")
            empty_message.setWordWrap(True)
            empty_message.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            empty_layout.addWidget(empty_message)

            empty_card = CardWidget(
                WORKSPACE_EMPTY_STATE_TITLE_TEMPLATE.format(label=label),
                empty_content,
                parent=page,
            )
            empty_card.setObjectName("workspaceEmptyStateCard")
            empty_card.setProperty("authoritySemantics", "presentation-only")
            page_layout.addWidget(empty_card)
            return page

        def _workspace_page_order(self, projection: WorkspaceProjection) -> tuple[QWidget, ...]:
            """Supply Scoring when callers provide only the five core pages."""
            pages = projection.ordered_pages
            if projection.scoring is None:
                from AgMark.gui.views.results import ResultsView
                from AgMark.gui.views.scoring import ScoringView

                scoring = (
                    ScoringView(projection.results.projection)
                    if isinstance(projection.results, ResultsView)
                    else self._create_workspace_empty_state_page("Scoring")
                )
                pages = (pages[0], scoring, *pages[1:])
            return pages

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def selected_run_id(self) -> str | None:
            for run_id, row in self.run_rows.items():
                if row.selected:
                    return run_id
            return None

        @property
        def workspace_projection_run_id(self) -> str | None:
            return self._workspace_projection_run_id

        def _apply_workspace_tab_visibility(self, *, selected_index: int | None = None) -> None:
            """Keep execution-only workspaces free of unsupported navigation."""

            selected_benchmark = self.benchmark_input.value
            custom_benchmark = (
                isinstance(selected_benchmark, str)
                and selected_benchmark.partition("@")[0] == "arcgrav.custom.benchmark.core"
            )
            results_page = self.workspace_pages.get("Results")
            results_unscored = bool(
                getattr(getattr(results_page, "projection", None), "unscored", False)
            )
            execution_only = custom_benchmark or results_unscored
            available_pages = {"Progress", "Scoring", "Results", "Evidence"}
            contaminated = getattr(self, "_workspace_contaminated", None)
            if contaminated is None:
                contaminated = self._sidebar_projection.treatments_contaminated
            self.contamination_warning.setVisible(contaminated)

            if selected_index is None:
                selected_index = self.workspace_tabs.currentIndex()
            if not 0 <= selected_index < len(WORKSPACE_TAB_LABELS):
                selected_index = WORKSPACE_TAB_LABELS.index("Results")
            if execution_only and WORKSPACE_TAB_LABELS[selected_index] not in available_pages:
                selected_index = WORKSPACE_TAB_LABELS.index("Results")

            for index, label in enumerate(WORKSPACE_TAB_LABELS):
                self.workspace_tabs.setTabVisible(
                    index, contaminated or not execution_only or label in available_pages
                )
            for index, label in enumerate(WORKSPACE_TAB_LABELS):
                restricted = contaminated and label in {"Verification", "Reports"}
                self.workspace_tabs.setTabEnabled(index, not restricted)
                icon = semantic_icon("status-error") if restricted else QIcon()
                if restricted:
                    # Qt must retain the red error glyph even for a disabled tab.
                    icon.addPixmap(icon.pixmap(18, 18), QIcon.Mode.Disabled)
                self.workspace_tabs.setTabIcon(index, icon)
                if restricted and selected_index == index:
                    selected_index = WORKSPACE_TAB_LABELS.index("Results")
            self.workspace_tabs.set_selected_index(selected_index)

        def _remember_results_divider(self) -> None:
            from AgMark.gui.views.results import ResultsView
            page = self.workspace_pages.get("Results")
            if isinstance(page, ResultsView) and page.projection.rows:
                self._results_divider_state = page.results_splitter.saveState()

        def set_workspace_projection(
            self,
            projection: WorkspaceProjection,
            *,
            run_id: str | None = None,
        ) -> None:
            """Replace workspace pages without changing tab or console state."""

            if not isinstance(projection, WorkspaceProjection):
                raise ValueError("projection must be a WorkspaceProjection")
            if run_id is not None:
                _require_non_empty(run_id, name="run_id")

            self._workspace_contaminated = projection.treatments_contaminated
            pages = self._workspace_page_order(projection)
            if any(not isinstance(page, QWidget) for page in pages):
                raise ValueError("WorkspaceProjection pages must be QWidget instances")
            if len({id(page) for page in pages}) != len(pages):
                raise ValueError("WorkspaceProjection pages must be distinct widgets")

            self._remember_results_divider()
            from AgMark.gui.views.results import ResultsView
            if isinstance(projection.results, ResultsView):
                state = getattr(self, "_results_divider_state", None)
                if state is not None:
                    projection.results.results_splitter.restoreState(state)

            selected_index = self.workspace_tabs.currentIndex()
            for index, (label, page) in enumerate(
                zip(WORKSPACE_TAB_LABELS, pages, strict=True)
            ):
                self._release_workspace_page(index)
                if not page.accessibleName():
                    page.setAccessibleName(f"{label} workspace")
                self.workspace_tabs.insertTab(index, self._wrap_workspace_page(label, page), label)
                self.workspace_pages[label] = page

            self._apply_workspace_tab_visibility(selected_index=selected_index)
            self._workspace_projection_run_id = run_id

        def clear_workspace_projection(self) -> None:
            """Return workspace tabs to their deliberate current-run empty state."""
            self._workspace_contaminated = None

            self._remember_results_divider()

            selected_index = self.workspace_tabs.currentIndex()
            for index, label in enumerate(WORKSPACE_TAB_LABELS):
                self._release_workspace_page(index)
                page = self._create_workspace_empty_state_page(label)
                self.workspace_tabs.insertTab(index, self._wrap_workspace_page(label, page), label)
                self.workspace_pages[label] = page

            self._apply_workspace_tab_visibility(selected_index=selected_index)
            self._workspace_projection_run_id = None

        def set_environment_projection(self, text: str) -> None:
            """Replace session Environment content without changing console navigation."""

            self.console_widget.set_environment(text)

        def set_sidebar_projection(
            self,
            projection: SidebarProjection,
        ) -> None:
            """Replace runtime discovery/configuration presentation in place."""

            if not isinstance(projection, SidebarProjection):
                raise ValueError("projection must be a SidebarProjection")
            if projection.build_plan_effectively_available and self._on_build_plan is None:
                raise ValueError(
                    "on_build_plan is required when build_plan_available is true"
                )

            previous_projection = self._sidebar_projection
            preserve_configuration_scroll = (
                previous_projection.selected_benchmark == projection.selected_benchmark
                and previous_projection.selected_runner == projection.selected_runner
            )
            previous_sidebar = self.sidebar
            if self.upper_layout.indexOf(previous_sidebar) < 0:
                raise RuntimeError("sidebar is not attached to the upper work area")
            scroll_position = self.sidebar_scroll.verticalScrollBar().value()
            configuration_scroll_position = (
                self.configuration_scroll.verticalScrollBar().value()
                if preserve_configuration_scroll
                else 0
            )
            focus_identity = self._sidebar_focus_identity()
            self.runner_menu.close()
            self._sidebar_projection = projection
            self.set_runner_connectivity(projection)

            self.sidebar = QFrame()
            self.sidebar.setObjectName("benchmarkSidebar")
            self.sidebar.setAccessibleName("Benchmark configuration and runs")
            self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
            self.sidebar.setStyleSheet(
                "QFrame#benchmarkSidebar { border: 0; "
                f"border-right: 1px solid {DEFAULT_LIGHT_THEME.color('text-muted')}; }}"
            )
            self.sidebar.setFixedWidth(REFERENCE_SIDEBAR_WIDTH)
            self.sidebar.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Expanding,
            )
            self._populate_sidebar(projection)
            replaced_item = self.upper_layout.replaceWidget(previous_sidebar, self.sidebar)
            if replaced_item is None:
                raise RuntimeError("sidebar replacement failed")
            if replaced_item.widget() is not previous_sidebar:
                raise RuntimeError("sidebar replacement returned an unexpected widget")
            del replaced_item

            # Keep retired sidebars owned by this window until deferred deletion.
            # Reparenting to None can turn a queued show into a top-level window
            # during consecutive refreshes, stealing keyboard focus from the shell.
            previous_sidebar.hide()
            previous_sidebar.deleteLater()
            self.sidebar.show()
            self._configure_keyboard_focus_order()
            self._apply_workspace_tab_visibility()
            self._apply_application_status()
            self._apply_operation_controls()
            QTimer.singleShot(
                0,
                self,
                lambda: self._restore_sidebar_refresh_state(
                    scroll_position,
                    configuration_scroll_position,
                    focus_identity,
                ),
            )

        def set_current_run_projection(
            self,
            projection: CurrentRunProjection | None,
        ) -> None:
            """Replace current-run presentation without creating lifecycle authority."""

            if projection is not None and not isinstance(
                projection,
                CurrentRunProjection,
            ):
                raise ValueError(
                    "projection must be CurrentRunProjection or None"
                )
            if (
                projection is not None
                and projection.accept_plan_available
                and self._on_accept_plan is None
            ):
                raise ValueError(
                    "on_accept_plan is required when accept_plan_available is true"
                )
            if (
                projection is not None
                and projection.start_benchmark_available
                and self._on_start_benchmark is None
            ):
                raise ValueError(
                    "on_start_benchmark is required when "
                    "start_benchmark_available is true"
                )
            if (
                projection is not None
                and projection.delete_run_available
                and self._on_delete_run is None
            ):
                raise ValueError(
                    "on_delete_run is required when delete_run_available is true"
                )

            console_height = self.vertical_splitter.sizes()[1]
            previous_region = self.current_run_scroll.takeWidget()
            self._populate_current_run(projection)
            self.workspace_scroll._resize_workspace_canvas()
            previous_region.deleteLater()
            self._configure_keyboard_focus_order()
            self._set_console_splitter_height(console_height)

        def set_operation_activity(self, labels: tuple[str, ...], *, lock_controls: bool) -> None:
            """Show dispatch activity without inventing lifecycle or percentage progress."""
            self._operation_labels = labels
            self._operation_locks_controls = lock_controls
            if lock_controls:
                self._dismiss_diagnostic_dialog()
            self.operation_label.setText(" · ".join(labels))
            self.operation_label.setAccessibleName(" · ".join(labels) or "Operation in progress")
            self.operation_banner.setVisible(bool(labels))
            self.operation_progress.set_busy(bool(labels))
            self._apply_operation_controls()

        def closeEvent(self, event) -> None:
            self._dismiss_diagnostic_dialog()
            self._clear_diagnostic_selection()
            self._diagnostic_window_closed.set()
            notice = getattr(self, "_diagnostic_dispatch_notice", None)
            if notice is not None:
                notice.reject()
            profile = self.additional_control_inputs.get("capture_mode")
            acknowledgement = self.additional_control_inputs.get("diagnostic_privacy_acknowledged")
            if profile is not None and profile.value == "deep_telemetry":
                self._set_diagnostic_control(profile, self._diagnostic_safe_profile(profile))
            if acknowledgement is not None:
                self._set_diagnostic_control(acknowledgement, "not_acknowledged")
            super().closeEvent(event)

        def showEvent(self, event) -> None:
            if self._diagnostic_window_closed.is_set():
                from threading import Event
                self._diagnostic_window_closed = Event()
            super().showEvent(event)

        def _apply_operation_controls(self) -> None:
            # Parent gating preserves each child's authoritative enabled state and
            # also covers replacement projections arriving while work is pending.
            self.sidebar.setEnabled(not self._operation_locks_controls)
            self.current_run_scroll.setEnabled(not self._operation_locks_controls)
            self._refresh_build_plan_availability()

        def set_runner_check_pending(self, pending: bool) -> None:
            self._runner_check_pending = pending
            self._refresh_runner_menu_availability()

        def set_runner_connectivity(self, projection: SidebarProjection) -> None:
            self._set_connectivity_runner_name(projection)
            if projection.selected_runner is None:
                label, tone, detail = ("Runner not selected", "neutral",
                                       "Select a runner to check its connection.")
            else:
                label, tone, detail = projection.runner_connectivity
            self.set_runner_status(label, tone, detail)

        def set_runner_status(self, label: str, tone: str, detail: str) -> None:
            """Display runner action status with its selected-runner context."""
            self.set_connectivity_status(label, tone)
            identity = self._sidebar_projection.selected_runner or "No selected runner"
            self.connectivity_status.setAccessibleDescription(f"{identity}. {detail}")

        def _set_connectivity_runner_name(self, projection: SidebarProjection) -> None:
            name = "No runner"
            if projection.selected_runner is not None:
                labels = registration_choices(projection.runner_options, "runner")["option_labels"]
                name = labels[projection.runner_options.index(projection.selected_runner)]
            self.connectivity_status.set_context_label(name)

        def set_connectivity_status(self, label: str, tone: str) -> None:
            """Project connectivity independently from application readiness."""

            self.connectivity_status.set_status(label, tone)
            self._requested_connectivity_status = (label, tone)

        def set_application_status(self, label: str, tone: str) -> None:
            """Project application status without masking known readiness blockers."""

            # Validate the caller-supplied status before retaining it for restoration
            # after prerequisite blockers clear.
            DEFAULT_STATUS_STYLES.resolve(label, tone, theme=DEFAULT_LIGHT_THEME)
            self._requested_application_status = (label, tone)
            self._apply_application_status()

        def _apply_application_status(self) -> None:
            label, tone = self._requested_application_status
            if self._sidebar_projection.prerequisite_diagnostics and tone != "error":
                label, tone = ("Prerequisites unresolved", "warning")
            self.application_readiness_status = DEFAULT_STATUS_STYLES.resolve(
                label, tone, theme=DEFAULT_LIGHT_THEME
            )
            self.console_widget.append_history(label)

        def _persist_shell_preference(self, key: str, value: object) -> None:
            if self._shell_preferences is not None:
                self._shell_preferences[key] = value

        def _on_workspace_tab_changed(self, index: int) -> None:
            if 0 <= index < len(WORKSPACE_TAB_LABELS):
                self._persist_shell_preference(SHELL_WORKSPACE_TAB_KEY, WORKSPACE_TAB_LABELS[index])

        def _on_console_tab_changed(self, label: str) -> None:
            if label in CONSOLE_TABS:
                self._persist_shell_preference(SHELL_CONSOLE_TAB_KEY, label)

        def _configure_keyboard_focus_order(self) -> None:
            controls: list[QWidget] = [
                self.connectivity_status,
                self.build_plan_button,
                self.benchmark_input.combo_box,
                self.iterations_input,
                self.cache_replays_checkbox,
                self.randomize_treatment_start_checkbox,
                self.randomize_per_iteration_checkbox,
                self.runner_input.combo_box,
            ]
            if self._model_configuration_visible:
                controls.append(self._model_focus_target)
            if self.reasoning_input is not None:
                controls.append(self.reasoning_input.combo_box)
            if self.scenario_input is not None:
                controls.append(self.scenario_input.combo_box)
            if self._credential_configuration_visible:
                controls.extend(
                    (
                        self.credential_input.line_edit,
                        self.credential_input.reveal_button,
                    )
                )
            if self.temperature_input is not None:
                controls.append(self.temperature_input.spin_box)
            if self.max_tokens_input is not None:
                controls.append(self.max_tokens_input.spin_box)
            controls.extend(self._additional_control_focus_targets)
            for row in self.run_rows.values():
                controls.append(row)
            controls.extend(self.treatment_remove_buttons.values())
            if self.accept_plan_button is not None:
                controls.append(self.accept_plan_button)
            if self.start_benchmark_button is not None:
                controls.append(self.start_benchmark_button)
            if self.delete_run_button is not None:
                controls.append(self.delete_run_button)
            controls.append(self.workspace_tabs.tabBar())
            controls.append(self.console_widget.tab_bar)
            controls.extend(
                self.console_widget.console_view(tab) for tab in CONSOLE_TABS
            )
            controls.extend(
                (
                    self.console_widget.collapse_button,
                    self.console_widget.stream_input_checkbox,
                    self.console_widget.stream_output_checkbox,
                    self.console_widget.clear_button,
                )
            )
            focus_order = tuple(
                control
                for control in controls
                if control.focusPolicy() != Qt.FocusPolicy.NoFocus
            )
            for first, second in zip(focus_order, focus_order[1:]):
                QWidget.setTabOrder(first, second)
            self._keyboard_focus_order = focus_order

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            self._persist_shell_preference(SHELL_WINDOW_WIDTH_KEY, self.width())
            self._persist_shell_preference(SHELL_WINDOW_HEIGHT_KEY, self.height())

        def set_console_height(self, height: int) -> None:
            """Set and retain presentation-only console height."""

            if isinstance(height, bool) or not isinstance(height, int):
                raise TypeError("console height must be an integer")
            if height <= 0:
                raise ValueError("console height must be positive")
            self._set_console_splitter_height(height)
            self.console_widget.record_splitter_height(height)

        def _invoke_build_plan(self, checked: bool = False) -> None:
            del checked
            if self._on_build_plan is None or not self.build_plan_button.isEnabled():
                return
            self._command_router.build_plan(self.sidebar_input_snapshot())

        def _invoke_check_runner(self, checked: bool = False) -> None:
            del checked
            if (not self._operation_locks_controls
                    and self._on_check_runner is not None
                    and self.runner_check_action is not None
                    and self.runner_check_action.isEnabled()):
                self._on_check_runner(self.sidebar_input_snapshot())

        def _invoke_test_runner(self, checked: bool = False) -> None:
            del checked
            if (
                self._operation_locks_controls
                or self._on_test_runner is None
                or self.runner_test_action is None
                or not self.runner_test_action.isEnabled()
            ):
                return
            self._command_router.test_runner(self.sidebar_input_snapshot())

        def _handle_run_selection(self, run_id: str) -> None:
            for candidate_id, row in self.run_rows.items():
                row.set_selected(candidate_id == run_id)
            workspace_projection = self._retained_workspace_projections.get(run_id)
            if workspace_projection is not None:
                self.set_workspace_projection(workspace_projection, run_id=run_id)
            self._command_router.select_run(run_id)

        def _confirm_delete_run(self, run_id: str) -> bool:
            run_id = _require_non_empty(run_id, name="run_id")
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle("Delete Run")
            dialog.setText(f"Delete run {run_id}?")
            dialog.setInformativeText(
                "This permanently removes the retained run and its locally retained "
                "evidence, reports, and verification data. This cannot be undone."
            )
            cancel_button = dialog.addButton(
                "Cancel",
                QMessageBox.ButtonRole.RejectRole,
            )
            delete_button = dialog.addButton(
                "Delete Run",
                QMessageBox.ButtonRole.DestructiveRole,
            )
            dialog.setDefaultButton(cancel_button)
            dialog.exec()
            return dialog.clickedButton() == delete_button

        def _invoke_delete_run(
            self,
            run_id: str,
            checked: bool = False,
        ) -> None:
            del checked
            if not self._confirm_delete_run(run_id):
                return
            self._command_router.delete_run(run_id)

        def _invoke_remove_treatment(self, filename: str) -> None:
            button = self.treatment_remove_buttons.get(filename)
            if (
                button is None
                or not button.isEnabled()
                or self._on_build_plan is None
                or self._operation_locks_controls
            ):
                return
            # Rebuild through the ordinary planning authority. Merely hiding a
            # row would leave the accepted treatment set and execution unchanged.
            self.sidebar_input_snapshot()  # Refresh the folder/benchmark scope.
            self._excluded_treatments.add(filename)
            for remove_button in self.treatment_remove_buttons.values():
                remove_button.setEnabled(False)
            self._command_router.build_plan(self.sidebar_input_snapshot())

        def _invoke_accept_plan(self, checked: bool = False) -> None:
            del checked
            self._command_router.accept_plan()

        def _invoke_start_benchmark(self, checked: bool = False) -> None:
            del checked
            self._command_router.start_benchmark()

        def _set_console_splitter_height(self, height: int) -> None:
            sizes = self.vertical_splitter.sizes()
            total = sum(sizes)
            if total <= height:
                total = max(self.height(), height + 1)
            self.vertical_splitter.setSizes([max(1, total - height), height])

        def _on_splitter_moved(self, _position: int, index: int) -> None:
            if index != 1:
                return
            console_height = self.vertical_splitter.sizes()[1]
            if console_height > 0:
                self.console_widget.record_splitter_height(console_height)

        def _restore_console_height(self, height: int) -> None:
            self._set_console_splitter_height(height)

        def _on_console_expanded_changed(self, expanded: bool) -> None:
            self._persist_shell_preference(SHELL_CONSOLE_EXPANDED_KEY, expanded)
            if expanded:
                return
            collapsed_height = max(1, self.console_widget.sizeHint().height())
            self._set_console_splitter_height(collapsed_height)

else:

    class BenchmarkShellWindow:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for BenchmarkShellWindow")


__all__ = [
    "BenchmarkShellWindow",
    "BuildPlanOperation",
    "CommandDispatcher",
    "CommandOperation",
    "CURRENT_RUN_BOUNDARY_LABELS",
    "CURRENT_RUN_PLAN_LABELS",
    "CurrentRunProjection",
    "ExecutionBoundaryProjection",
    "LifecycleOperation",
    "NumericInputProjection",
    "PYSIDE6_AVAILABLE",
    "MINIMUM_RESPONSIVE_SIDEBAR_WIDTH",
    "MINIMUM_TAB_CONTENT_HEIGHT",
    "MINIMUM_TAB_CONTENT_WIDTH",
    "REFERENCE_CONFIGURATION_VIEWPORT_HEIGHT",
    "REFERENCE_CONSOLE_HEIGHT",
    "REFERENCE_SIDEBAR_WIDTH",
    "REFERENCE_WINDOW_HEIGHT",
    "REFERENCE_WINDOW_WIDTH",
    "RetainedRunProjection",
    "RunPlanProjection",
    "RunSelectionOperation",
    "ShellCommandRouter",
    "SIDEBAR_SECTION_ORDER",
    "SidebarChoiceControlProjection",
    "SidebarControlInputSnapshot",
    "SidebarInputSnapshot",
    "SidebarModelChoiceProjection",
    "SidebarNumericControlProjection",
    "SidebarProjection",
    "SidebarResolvedTextProjection",
    "SidebarTextControlProjection",
    "SHELL_CONSOLE_EXPANDED_KEY",
    "SHELL_CONSOLE_TAB_KEY",
    "SHELL_WINDOW_HEIGHT_KEY",
    "SHELL_WINDOW_WIDTH_KEY",
    "SHELL_WORKSPACE_TAB_KEY",
    "TestRunnerOperation",
    "WINDOW_TITLE",
    "WORKSPACE_TAB_LABELS",
    "WorkspaceProjection",
]
