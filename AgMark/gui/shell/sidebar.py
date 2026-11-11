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

from AgMark.gui.shell.registration_choices import registration_choices
from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS
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
    IntegerInput,
    PYSIDE6_AVAILABLE as INPUTS_PYSIDE6_AVAILABLE,
    SelectInput,
)
from AgMark.gui.widgets.status import (
    PYSIDE6_AVAILABLE as STATUS_PYSIDE6_AVAILABLE,
    StatusBadge,
)
from AgMark.gui.widgets.tabs import (
    PYSIDE6_AVAILABLE as TABS_PYSIDE6_AVAILABLE,
    TabWidget,
)

try:
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QCheckBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
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


WINDOW_TITLE = "AgMark"
REFERENCE_WINDOW_WIDTH = 1440
REFERENCE_WINDOW_HEIGHT = 1080
REFERENCE_SIDEBAR_WIDTH = 300
MINIMUM_RESPONSIVE_SIDEBAR_WIDTH = 180
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
from .diagnostic_controller import DiagnosticConsentController
from AgMark.shared.telemetry.profile import DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
from .input_snapshot import SidebarControlInputSnapshot, SidebarInputSnapshot
from .preferences import (
    _stored_bool,
    _stored_console_tab,
    _stored_positive_int,
    _stored_tab_index,
)
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

from .retained_runs import _RetainedRunRow

if PYSIDE6_AVAILABLE:

    class SidebarControllerMixin(DiagnosticConsentController):
        def _sidebar_focus_identity(self) -> tuple[str, str | None] | None:
            """Capture stable sidebar focus identity before passive replacement."""
    
            focused = self.focusWidget()
            if focused is None:
                return None
            direct_targets = (
                ("benchmark", self.benchmark_input.combo_box),
                ("randomize_treatment_start", self.randomize_treatment_start_checkbox),
                ("randomize_per_iteration", self.randomize_per_iteration_checkbox),
                ("runner", self.runner_input.combo_box),
                ("scenario", self.scenario_input.combo_box if self.scenario_input is not None else None),
                ("reasoning", self.reasoning_input.combo_box if self.reasoning_input is not None else None),
                (
                    "model",
                    self._model_focus_target
                    if self._model_configuration_visible
                    else None,
                ),
                (
                    "credential",
                    self.credential_input.line_edit
                    if self._credential_configuration_visible
                    else None,
                ),
                ("temperature", (
                    self.temperature_input.spin_box
                    if self.temperature_input is not None
                    else None
                )),
                ("max_tokens", (
                    self.max_tokens_input.spin_box
                    if self.max_tokens_input is not None
                    else None
                )),
                ("build_plan", self.build_plan_button),
            )
            for identity, target in direct_targets:
                if target is not None and focused is target:
                    return identity, None
    
            current = focused
            while current is not None:
                control_name = current.property("runnerControlName")
                if isinstance(control_name, str) and control_name:
                    return "runner_control", control_name
                if current is self.sidebar:
                    break
                current = current.parentWidget()
            return None

        def _restore_sidebar_focus(
            self,
            identity: tuple[str, str | None] | None,
        ) -> None:
            """Restore ordinary focus to the equivalent refreshed control."""
    
            if identity is None:
                return
            kind, control_name = identity
            target: QWidget | None = None
            if kind == "benchmark":
                target = self.benchmark_input.combo_box
            elif kind == "randomize_treatment_start":
                target = self.randomize_treatment_start_checkbox
            elif kind == "randomize_per_iteration":
                target = self.randomize_per_iteration_checkbox
            elif kind == "runner":
                target = self.runner_input.combo_box
            elif kind == "scenario" and self.scenario_input is not None:
                target = self.scenario_input.combo_box
            elif kind == "reasoning" and self.reasoning_input is not None:
                target = self.reasoning_input.combo_box
            elif kind == "model" and self._model_configuration_visible:
                target = self._model_focus_target
            elif kind == "credential" and self._credential_configuration_visible:
                target = self.credential_input.line_edit
            elif kind == "temperature" and self.temperature_input is not None:
                target = self.temperature_input.spin_box
            elif kind == "max_tokens" and self.max_tokens_input is not None:
                target = self.max_tokens_input.spin_box
            elif kind == "build_plan":
                target = self.build_plan_button
            elif kind == "runner_control" and control_name is not None:
                control_input = self.additional_control_inputs.get(control_name)
                if isinstance(control_input, CredentialInput):
                    target = control_input.line_edit
                elif isinstance(control_input, SelectInput):
                    target = control_input.combo_box
                elif isinstance(control_input, NumericInput):
                    target = control_input.spin_box
            if target is not None and target.isEnabled():
                target.setFocus(Qt.FocusReason.OtherFocusReason)

        def _restore_sidebar_refresh_state(
            self,
            scroll_position: int,
            configuration_scroll_position: int,
            focus_identity: tuple[str, str | None] | None,
        ) -> None:
            scroll_bar = self.sidebar_scroll.verticalScrollBar()
            scroll_bar.setValue(min(scroll_position, scroll_bar.maximum()))
            configuration_scroll_bar = self.configuration_scroll.verticalScrollBar()
            configuration_scroll_bar.setValue(
                min(
                    configuration_scroll_position,
                    configuration_scroll_bar.maximum(),
                )
            )
            self._restore_sidebar_focus(focus_identity)

        def _populate_sidebar(self, projection: SidebarProjection) -> None:
            self._begin_diagnostic_sidebar(projection)
            layout_metrics = DEFAULT_LAYOUT_METRICS
            sidebar_root = QVBoxLayout(self.sidebar)
            sidebar_root.setContentsMargins(0, 0, 0, 0)
            sidebar_root.setSpacing(0)
    
            self.sidebar_scroll = QScrollArea(self.sidebar)
            self.sidebar_scroll.setObjectName("benchmarkSidebarScroll")
            self.sidebar_scroll.setWidgetResizable(True)
            self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.sidebar_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            sidebar_root.addWidget(self.sidebar_scroll, 1)
    
            self.sidebar_content = QWidget(self.sidebar_scroll)
            self.sidebar_content.setObjectName("benchmarkSidebarContent")
            self.sidebar_content.setMinimumWidth(0)
            self.sidebar_content.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            self.sidebar_scroll.setWidget(self.sidebar_content)
    
            self.sidebar_layout = QVBoxLayout(self.sidebar_content)
            page_padding = layout_metrics.metric("page-padding")
            self.sidebar_layout.setContentsMargins(
                page_padding,
                page_padding,
                page_padding,
                page_padding,
            )
            self.sidebar_layout.setSpacing(layout_metrics.metric("stack-gap"))
    
            benchmark_content = QWidget(self.sidebar_content)
            benchmark_content.setObjectName("sidebarBenchmarkContent")
            benchmark_layout = QVBoxLayout(benchmark_content)
            benchmark_layout.setContentsMargins(0, 0, 0, 0)
            benchmark_layout.setSpacing(0)
    
            self.benchmark_input = SelectInput(
                "Benchmark",
                projection.benchmark_options,
                projection.selected_benchmark,
                **registration_choices(projection.benchmark_options, "benchmark"),
                show_label=False,
                parent=benchmark_content,
            )
            self.benchmark_input.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            benchmark_layout.addWidget(self.benchmark_input)
            self.contamination_warning = QWidget(benchmark_content)
            warning_layout = QHBoxLayout(self.contamination_warning)
            warning_layout.setContentsMargins(0, 4, 0, 4)
            warning_layout.setSpacing(4)
            self.contamination_icon = QLabel(self.contamination_warning)
            self.contamination_icon.setPixmap(semantic_icon("status-error").pixmap(18, 18))
            self.contamination_text = QLabel("Treatments Contaminated", self.contamination_warning)
            self.contamination_text.setStyleSheet("color: #F0212D;")
            warning_layout.addWidget(self.contamination_icon)
            warning_layout.addWidget(self.contamination_text)
            warning_layout.addStretch()
            self.contamination_warning.setVisible(projection.treatments_contaminated)
            benchmark_layout.addWidget(self.contamination_warning)
            self.prompt_folder_controls = QWidget(benchmark_content)
            folder_layout = QVBoxLayout(self.prompt_folder_controls)
            folder_layout.setContentsMargins(0, 4, 0, 4)
            folder_layout.addWidget(QLabel("Prompt folder", self.prompt_folder_controls))
            self.prompt_folder_input = QLineEdit(self.prompt_folder_controls)
            self.prompt_folder_input.setAccessibleName("Prompt folder")
            self.prompt_folder_input.setPlaceholderText("Folder containing treatment files")
            self.prompt_folder_input.setText(getattr(self, "_prompt_folder", projection.prompt_folder))
            self.prompt_folder_input.textChanged.connect(lambda value: setattr(self, "_prompt_folder", value))
            folder_layout.addWidget(self.prompt_folder_input)
            self.prompt_folder_browse = ActionButton(
                "Browse…",
                "secondary",
                parent=self.prompt_folder_controls,
            )
            self.prompt_folder_browse.clicked.connect(self._browse_prompt_folder)
            folder_layout.addWidget(self.prompt_folder_browse)
            self.prompt_folder_controls.setVisible(projection.prompt_folder_visible)
            benchmark_layout.addWidget(self.prompt_folder_controls)
            iterations_row = QWidget(benchmark_content)
            iterations_layout = QVBoxLayout(iterations_row)
            iterations_layout.setContentsMargins(0, layout_metrics.metric("stack-gap"), 0, 0)
            iterations_control = IntegerInput("Iterations", getattr(self, "_iteration_count", 1),
                minimum=1, maximum=10000, parent=iterations_row)
            self.iterations_input = iterations_control.spin_box
            self.iterations_input.setAccessibleName("Benchmark iterations")
            self.iterations_input.valueChanged.connect(self._set_iteration_count)
            iterations_layout.addWidget(iterations_control)
            benchmark_layout.addWidget(iterations_row)
            preferences = self._shell_preferences or {}
            replay_row = QWidget(benchmark_content)
            replay_layout = QHBoxLayout(replay_row)
            replay_layout.setContentsMargins(0, layout_metrics.metric("stack-gap"), 0, 0)
            self.cache_replays_checkbox = QCheckBox(replay_row)
            replay_label = QLabel("Cache Validation Replays", replay_row)
            replay_label.setWordWrap(True)
            replay_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.cache_replays_checkbox.setFixedHeight(replay_label.fontMetrics().lineSpacing())
            replay_label.setBuddy(self.cache_replays_checkbox)
            self.cache_replays_checkbox.setAccessibleName(replay_label.text())
            enabled = getattr(self, "_cache_replays_enabled", preferences.get("run_cache_validation_replays", False))
            self.cache_replays_checkbox.setChecked(enabled if type(enabled) is bool else False)
            self.cache_replays_checkbox.toggled.connect(self._set_cache_replays_enabled)
            replay_layout.addWidget(self.cache_replays_checkbox, 0, Qt.AlignmentFlag.AlignTop)
            replay_layout.addWidget(replay_label, 1)
            benchmark_layout.addWidget(replay_row)
            randomize_row = QWidget(benchmark_content)
            randomize_layout = QHBoxLayout(randomize_row)
            randomize_layout.setContentsMargins(0, layout_metrics.metric("stack-gap"), 0, 0)
            self.randomize_treatment_start_checkbox = QCheckBox(randomize_row)
            randomize_label = QLabel("Randomize Treatment Start", randomize_row)
            randomize_label.setWordWrap(True)
            randomize_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.randomize_treatment_start_checkbox.setFixedHeight(
                randomize_label.fontMetrics().lineSpacing()
            )
            randomize_label.setBuddy(self.randomize_treatment_start_checkbox)
            self.randomize_treatment_start_checkbox.setAccessibleName(randomize_label.text())
            randomized = getattr(
                self, "_randomize_treatment_start_enabled",
                preferences.get("randomize_treatment_start", True),
            )
            self.randomize_treatment_start_checkbox.setChecked(
                randomized if type(randomized) is bool else True
            )
            self.randomize_treatment_start_checkbox.toggled.connect(
                self._set_randomize_treatment_start_enabled
            )
            randomize_layout.addWidget(
                self.randomize_treatment_start_checkbox, 0, Qt.AlignmentFlag.AlignTop
            )
            randomize_layout.addWidget(randomize_label, 1)
            benchmark_layout.addWidget(randomize_row)
            per_iteration_row = QWidget(benchmark_content)
            per_iteration_layout = QHBoxLayout(per_iteration_row)
            per_iteration_layout.setContentsMargins(
                layout_metrics.metric("related-gap"),
                layout_metrics.metric("stack-gap"), 0, 0,
            )
            self.randomize_per_iteration_checkbox = QCheckBox(per_iteration_row)
            per_iteration_label = QLabel("Randomize Per Iteration", per_iteration_row)
            per_iteration_label.setWordWrap(True)
            per_iteration_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            self.randomize_per_iteration_checkbox.setFixedHeight(
                per_iteration_label.fontMetrics().lineSpacing()
            )
            per_iteration_label.setBuddy(self.randomize_per_iteration_checkbox)
            self.randomize_per_iteration_checkbox.setAccessibleName(
                per_iteration_label.text()
            )
            per_iteration_enabled = getattr(
                self, "_randomize_per_iteration_enabled",
                preferences.get("randomize_per_iteration", True),
            )
            self.randomize_per_iteration_checkbox.setChecked(
                per_iteration_enabled if type(per_iteration_enabled) is bool else True
            )
            self.randomize_per_iteration_checkbox.toggled.connect(
                self._set_randomize_per_iteration_enabled
            )
            per_iteration_layout.addWidget(
                self.randomize_per_iteration_checkbox, 0, Qt.AlignmentFlag.AlignTop
            )
            per_iteration_layout.addWidget(per_iteration_label, 1)
            benchmark_layout.addWidget(per_iteration_row)
            per_iteration_row.setEnabled(
                self.randomize_treatment_start_checkbox.isChecked()
            )
            self.randomize_treatment_start_checkbox.toggled.connect(
                per_iteration_row.setEnabled
            )
            self.benchmark_card = CardWidget(
                "Benchmark",
                benchmark_content,
                title_role="section-heading",
                parent=self.sidebar_content,
            )
            self.benchmark_card.setObjectName("sidebarBenchmarkCard")
            self.sidebar_layout.addWidget(self.benchmark_card)
            self.benchmark_input.combo_box.currentIndexChanged.connect(
                self._handle_benchmark_selection_changed
            )
    
            runner_content = QWidget(self.sidebar_content)
            runner_content.setObjectName("sidebarRunnerContent")
            runner_layout = QVBoxLayout(runner_content)
            runner_layout.setContentsMargins(0, 0, 0, 0)
            runner_layout.setSpacing(layout_metrics.metric("related-gap"))
    
            self.runner_input = SelectInput(
                "Runner",
                projection.runner_options,
                projection.selected_runner,
                **registration_choices(projection.runner_options, "runner"),
                show_label=False,
                parent=runner_content,
            )
            self.runner_input.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            runner_layout.addWidget(self.runner_input)
            self.runner_input.combo_box.currentIndexChanged.connect(
                self._handle_runner_selection_changed
            )
    
            self.configuration_heading = QLabel("Configuration", runner_content)
            self.configuration_heading.setObjectName("sidebarSectionHeading")
            self.configuration_heading.setAccessibleName("Configuration")
            runner_layout.addWidget(self.configuration_heading)
    
            self.configuration_scroll = QScrollArea(runner_content)
            self.configuration_scroll.setObjectName("sidebarConfigurationScroll")
            self.configuration_scroll.setAccessibleName(
                "Configuration controls"
            )
            self.configuration_scroll.setProperty(
                "authoritySemantics",
                "presentation-only",
            )
            self.configuration_scroll.setWidgetResizable(True)
            self.configuration_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.configuration_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.configuration_scroll.setMaximumHeight(
                REFERENCE_CONFIGURATION_VIEWPORT_HEIGHT
            )
            self.configuration_scroll.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
    
            self.configuration_content = QWidget(self.configuration_scroll)
            self.configuration_content.setObjectName("sidebarConfigurationContent")
            self.configuration_content.setMinimumWidth(0)
            self.configuration_content.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            self.configuration_content_layout = QVBoxLayout(
                self.configuration_content
            )
            configuration_padding = layout_metrics.metric("space-md")
            self.configuration_content_layout.setContentsMargins(
                configuration_padding,
                configuration_padding,
                configuration_padding,
                configuration_padding,
            )
            self.configuration_content_layout.setSpacing(
                layout_metrics.metric("related-gap")
            )
            self.configuration_scroll.setWidget(self.configuration_content)
            runner_layout.addWidget(self.configuration_scroll)
    
            self.configuration_widget = QWidget(self.configuration_content)
            self.configuration_widget.setObjectName("sidebarConfigurationRows")
            self.configuration_widget.setAccessibleName("Configuration primary controls")
            self.configuration_widget.setProperty(
                "authoritySemantics",
                "presentation-only",
            )
            self.configuration_form_layout = QFormLayout(self.configuration_widget)
            self.configuration_form_layout.setContentsMargins(0, 0, 0, 0)
            self.configuration_form_layout.setHorizontalSpacing(
                layout_metrics.metric("related-gap")
            )
            self.configuration_form_layout.setVerticalSpacing(
                layout_metrics.metric("related-gap")
            )
            self.configuration_form_layout.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            self.configuration_form_layout.setRowWrapPolicy(
                QFormLayout.RowWrapPolicy.DontWrapRows
            )
            self.configuration_form_layout.setLabelAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.configuration_form_layout.setFormAlignment(
                Qt.AlignmentFlag.AlignTop
            )
            self.configuration_row_labels: dict[str, QLabel] = {}
            self._model_configuration_visible = projection.model_visible
            self._credential_configuration_visible = projection.credentials_visible
    
            def add_reference_configuration_row(
                label: str,
                input_widget: QWidget,
                focus_target: QWidget,
                *,
                label_above: bool = False,
                visible: bool = True,
            ) -> None:
                if not visible:
                    input_widget.hide()
                    return
                label_widget = QLabel(label, self.configuration_widget)
                label_widget.setObjectName("configurationRowLabel")
                label_widget.setAccessibleName(f"{label} label")
                label_widget.setBuddy(focus_target)
                self.configuration_row_labels[label] = label_widget
                if label_above:
                    stacked_row = QWidget(self.configuration_widget)
                    stacked_layout = QVBoxLayout(stacked_row)
                    stacked_layout.setContentsMargins(0, 0, 0, 0)
                    stacked_layout.setSpacing(layout_metrics.metric("space-xs"))
                    stacked_layout.addWidget(label_widget)
                    stacked_layout.addWidget(input_widget)
                    self.configuration_form_layout.addRow(stacked_row)
                    return
                self.configuration_form_layout.addRow(label_widget, input_widget)
    
            self._model_choice_by_label: dict[
                str,
                SidebarModelChoiceProjection,
            ] = {}
            if projection.model_editable:
                self.model_input = CredentialInput(
                    "Model",
                    projection.selected_model or "",
                    show_label=False,
                    parent=self.configuration_widget,
                )
                self.model_input.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
                self.model_input.reveal_button.hide()
                self._model_focus_target = self.model_input.line_edit
            else:
                if projection.model_choices:
                    self._model_choice_by_label = {
                        choice.label: choice for choice in projection.model_choices
                    }
                    selected_choice = projection.selected_model_choice
                    model_options = tuple(self._model_choice_by_label)
                    selected_value = (
                        selected_choice.label
                        if selected_choice is not None
                        else None
                    )
                else:
                    model_options = projection.model_options
                    selected_value = projection.selected_model
                self.model_input = SelectInput(
                    "Model",
                    model_options,
                    selected_value,
                    show_label=False,
                    parent=self.configuration_widget,
                )
                if projection.model_required and not model_options:
                    self.model_input.combo_box.setEnabled(False)
                    self.model_input.setAccessibleDescription(
                        "Model discovery is unresolved"
                    )
                self._model_focus_target = self.model_input.combo_box
            self._model_required = projection.model_required
            self._model_discovery_context_fingerprints = (
                projection.model_discovery_context_fingerprints
            )
            add_reference_configuration_row(
                "Model",
                self.model_input,
                self._model_focus_target,
                label_above=True,
                visible=projection.model_visible,
            )
    
            self.reasoning_input: SelectInput | None = None
            self._reasoning_effort_control_name = projection.reasoning_effort_control_name
            if self._reasoning_effort_control_name is not None:
                self.reasoning_input = SelectInput(
                    "Reasoning Level", (), placeholder="Reasoning levels unavailable",
                    show_label=False, parent=self.configuration_widget,
                )
                self._refresh_reasoning_options(projection.selected_reasoning_effort)
                add_reference_configuration_row(
                    "Reasoning Level", self.reasoning_input, self.reasoning_input.combo_box,
                    label_above=True,
                )
                self.model_input.combo_box.currentIndexChanged.connect(self._handle_reasoning_model_changed)
                self.reasoning_input.combo_box.currentIndexChanged.connect(self._refresh_build_plan_availability)
                self.reasoning_input.combo_box.currentIndexChanged.connect(self._handle_sidebar_intent_changed)

            self.scenario_input: SelectInput | None = None
            self._scenario_choice_by_label = {}
            if projection.scenario_visible:
                self._scenario_choice_by_label = {
                    choice.scenario_label: choice for choice in projection.model_choices
                    if choice.scenario_id is not None
                }
                selected_scenario = next((
                    choice.scenario_label for choice in self._scenario_choice_by_label.values()
                    if choice.model_value == projection.selected_model
                ), None)
                self.scenario_input = SelectInput(
                    "Scenario", tuple(self._scenario_choice_by_label), selected_scenario,
                    placeholder="Scenario discovery unresolved", show_label=False,
                    parent=self.configuration_widget,
                )
                self.scenario_input.combo_box.setEnabled(bool(self._scenario_choice_by_label))
                self.scenario_input.combo_box.setAccessibleDescription(
                    "Registered scenario mapped to the selected canonical model"
                    if self._scenario_choice_by_label else "Scenario discovery is unresolved"
                )
                add_reference_configuration_row(
                    "Scenario", self.scenario_input, self.scenario_input.combo_box,
                    label_above=True,
                )
                self.scenario_input.combo_box.currentIndexChanged.connect(self._handle_scenario_changed)
                self.model_input.combo_box.currentIndexChanged.connect(self._handle_model_scenario_changed)

            self.credential_input = CredentialInput(
                "Credentials",
                projection.credential_value,
                show_label=False,
                parent=self.configuration_widget,
            )
            add_reference_configuration_row(
                "Credentials",
                self.credential_input,
                self.credential_input.line_edit,
                label_above=True,
                visible=projection.credentials_visible,
            )
    
            self.temperature_input: NumericInput | None = None
            if projection.temperature is not None:
                temperature = projection.temperature
                self.temperature_input = NumericInput(
                    "Temperature",
                    temperature.value,
                    minimum=temperature.minimum,
                    maximum=temperature.maximum,
                    step=temperature.step,
                    decimals=temperature.decimals,
                    show_label=False,
                    parent=self.configuration_widget,
                )
                self.temperature_input.spin_box.setEnabled(temperature.editable)
                add_reference_configuration_row(
                    "Temperature",
                    self.temperature_input,
                    self.temperature_input.spin_box,
                )
    
            self.max_tokens_input: NumericInput | None = None
            if projection.max_tokens is not None:
                max_tokens = projection.max_tokens
                self.max_tokens_input = NumericInput(
                    "Max Tokens",
                    max_tokens.value,
                    minimum=max_tokens.minimum,
                    maximum=max_tokens.maximum,
                    step=max_tokens.step,
                    decimals=max_tokens.decimals,
                    show_label=False,
                    parent=self.configuration_widget,
                )
                self.max_tokens_input.spin_box.setEnabled(max_tokens.editable)
                add_reference_configuration_row(
                    "Max Tokens",
                    self.max_tokens_input,
                    self.max_tokens_input.spin_box,
                )
    
            self.configuration_content_layout.addWidget(self.configuration_widget)
    
            self._temperature_required = (
                projection.temperature is not None and projection.temperature.required
            )
            self._max_tokens_required = (
                projection.max_tokens is not None and projection.max_tokens.required
            )
    
            self.additional_control_inputs: dict[str, QWidget] = {}
            self._additional_control_focus_targets: list[QWidget] = []
            self._additional_control_secret_flags: dict[str, bool] = {}
            self._required_additional_control_names: set[str] = set()
            for control in projection.additional_controls:
                control_focus_targets: list[QWidget] = []
                if isinstance(control, SidebarTextControlProjection):
                    control_input = CredentialInput(
                        control.label,
                        control.value,
                        parent=self.configuration_content,
                    )
                    if control.secret:
                        control_focus_targets.extend(
                            (control_input.line_edit, control_input.reveal_button)
                        )
                    else:
                        control_input.line_edit.setEchoMode(
                            QLineEdit.EchoMode.Normal
                        )
                        control_input.reveal_button.hide()
                        control_focus_targets.append(control_input.line_edit)
                elif isinstance(control, SidebarChoiceControlProjection):
                    capture_mode_labels = {
                        "capture_mode": {
                            "session": "Session",
                            "telemetry": "Telemetry",
                            "deep_telemetry": "Deep Telemetry",
                        },
                    }.get(control.control_name)
                    control_input = SelectInput(
                        control.label,
                        control.options,
                        control.selected_value,
                        **({"option_labels": tuple(capture_mode_labels.get(value, value)
                            for value in control.options)} if capture_mode_labels else {}),
                        parent=self.configuration_content,
                    )
                    control_focus_targets.append(control_input.combo_box)
                else:
                    numeric = control.numeric
                    control_input = NumericInput(
                        control.label,
                        numeric.value,
                        minimum=numeric.minimum,
                        maximum=numeric.maximum,
                        step=numeric.step,
                        decimals=numeric.decimals,
                        parent=self.configuration_content,
                    )
                    control_input.spin_box.setEnabled(numeric.editable)
                    control_focus_targets.append(control_input.spin_box)
                control_input.setProperty(
                    "runnerControlName",
                    control.control_name,
                )
                self.additional_control_inputs[control.control_name] = control_input
                self._additional_control_secret_flags[control.control_name] = (
                    isinstance(control, SidebarTextControlProjection)
                    and control.secret
                )
                if control.required:
                    self._required_additional_control_names.add(
                        control.control_name
                    )
                if control.control_name == "diagnostic_privacy_acknowledged":
                    # Preserve the registered control in actual plan provenance,
                    # but only the consent dialog can grant it in the GUI.
                    control_input.hide()
                    control_focus_targets.clear()
                else:
                    self.configuration_content_layout.addWidget(control_input)
                self._additional_control_focus_targets.extend(
                    control_focus_targets
                )
            self._initialize_diagnostic_controls()
    
            self.resolved_configuration_inputs: dict[str, CredentialInput] = {}
            for resolved in projection.resolved_configuration:
                resolved_input = CredentialInput(
                    resolved.label,
                    resolved.value,
                    parent=self.configuration_content,
                )
                resolved_input.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
                resolved_input.reveal_button.hide()
                resolved_input.line_edit.setReadOnly(True)
                resolved_input.setProperty(
                    "runnerResolvedConfigurationName",
                    resolved.control_name,
                )
                resolved_input.setAccessibleDescription(
                    "Automatically resolved from the selected runner environment"
                )
                self.resolved_configuration_inputs[
                    resolved.control_name
                ] = resolved_input
                self.configuration_content_layout.addWidget(resolved_input)
    
            self._runner_diagnostic_supported = projection.runner_test_supported
            self.configuration_content_layout.addStretch(1)
            configuration_content_height = (
                self.configuration_content.sizeHint().height()
                + (2 * layout_metrics.metric("border-width"))
            )
            self.configuration_scroll.setMinimumHeight(
                min(
                    REFERENCE_CONFIGURATION_VIEWPORT_HEIGHT,
                    configuration_content_height,
                )
            )
    
            self.runner_card = CardWidget(
                "Runner",
                runner_content,
                title_role="section-heading",
                parent=self.sidebar_content,
            )
            self.runner_card.setObjectName("sidebarRunnerCard")
            self.sidebar_layout.addWidget(self.runner_card)
    
            if self._on_sidebar_intent_changed is not None:
                for control_name in projection.model_discovery_determining_controls:
                    if control_name in ("capture_mode", "diagnostic_privacy_acknowledged"):
                        continue
                    control_input = self.additional_control_inputs.get(control_name)
                    if isinstance(control_input, CredentialInput):
                        control_input.line_edit.editingFinished.connect(
                            self._handle_sidebar_intent_changed
                        )
                    elif isinstance(control_input, SelectInput):
                        control_input.combo_box.currentIndexChanged.connect(
                            self._handle_sidebar_intent_changed
                        )
                    elif isinstance(control_input, NumericInput):
                        control_input.spin_box.editingFinished.connect(
                            self._handle_sidebar_intent_changed
                        )
    
            prerequisite_diagnostic_widgets: list[QFrame] = []
            if projection.prerequisite_diagnostics:
                diagnostic_frame = QFrame(self.sidebar_content)
                diagnostic_frame.setObjectName("sidebarPrerequisiteDiagnostic")
                diagnostic_frame.setProperty(
                    "diagnosticNames",
                    tuple(
                        diagnostic.diagnostic_name
                        for diagnostic in projection.prerequisite_diagnostics
                    ),
                )
                diagnostic_frame.setProperty(
                    "prerequisiteOperations",
                    tuple(
                        diagnostic.operation
                        for diagnostic in projection.prerequisite_diagnostics
                    ),
                )
                diagnostic_frame.setProperty(
                    "consoleView",
                    "Environment",
                )
                diagnostic_frame.setProperty(
                    "authoritySemantics",
                    "presentation-only",
                )
                diagnostic_frame.setAccessibleName(
                    "Error; see Console → Environment"
                )
                diagnostic_frame.setAccessibleDescription(
                    "See the Environment tab in Console for diagnostic details and remediation."
                )
    
                diagnostic_layout = QHBoxLayout(diagnostic_frame)
                diagnostic_layout.setContentsMargins(
                    layout_metrics.metric("compact-panel-padding-x"),
                    layout_metrics.metric("compact-panel-padding-y"),
                    layout_metrics.metric("compact-panel-padding-x"),
                    layout_metrics.metric("compact-panel-padding-y"),
                )
                diagnostic_layout.setSpacing(
                    layout_metrics.metric("compact-panel-gap")
                )
    
                error_icon_label = QLabel(diagnostic_frame)
                error_icon_label.setObjectName("sidebarPrerequisiteErrorIcon")
                error_icon_label.setProperty(
                    "semanticIconRole",
                    "status-error",
                )
                error_icon_label.setAccessibleName("")
                error_icon_label.setPixmap(
                    semantic_icon(
                        "status-error",
                        theme=DEFAULT_LIGHT_THEME,
                        size=16,
                    ).pixmap(16, 16)
                )
                error_icon_label.setFixedSize(16, 16)
                diagnostic_layout.addWidget(
                    error_icon_label,
                    0,
                    Qt.AlignmentFlag.AlignVCenter,
                )
    
                message_label = QLabel(
                    "see Console → Environment",
                    diagnostic_frame,
                )
                message_label.setObjectName("sidebarPrerequisiteMessage")
                message_label.setWordWrap(True)
                diagnostic_layout.addWidget(message_label, 1)
    
                self.sidebar_layout.addWidget(diagnostic_frame)
                prerequisite_diagnostic_widgets.append(diagnostic_frame)
            self.prerequisite_diagnostic_widgets = tuple(
                prerequisite_diagnostic_widgets
            )
    
            self._projected_build_plan_available = (
                projection.build_plan_effectively_available
            )
            build_plan_available = (
                self._projected_build_plan_available
                and self._required_default_controls_resolved()
                and self._required_additional_controls_resolved()
            )
            # Keep primary actions outside both sidebar scrolling and replacement.
            if not hasattr(self, "sidebar_header"):
                self.sidebar_header = QWidget(self)
                self.sidebar_header.setObjectName("benchmarkSidebarHeader")
                self.sidebar_header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                self.sidebar_header.setStyleSheet(
                    "QWidget#benchmarkSidebarHeader {"
                    "background-color: #FFFFFF;"
                    "border: 0;"
                    "border-radius: 0px;"
                    "}"
                )
                self.sidebar_header.setSizePolicy(
                    QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed,
                )
                header_layout = QVBoxLayout(self.sidebar_header)
                # The sidebar owns the final pixel of the trailing inset as its divider.
                header_layout.setContentsMargins(
                    page_padding, page_padding, page_padding - 1, page_padding,
                )
                header_layout.setSpacing(layout_metrics.metric("related-gap"))
            else:
                header_layout = self.sidebar_header.layout()
                header_layout.removeWidget(self.build_plan_button)
                self.build_plan_button.hide()
                self.build_plan_button.deleteLater()
            sidebar_root.insertWidget(0, self.sidebar_header)
            self.build_plan_button = ActionButton(
                "Build Plan",
                "primary" if build_plan_available else "unavailable",
                icon_role="plan-build",
                parent=self.sidebar_header,
            )
            if self._on_build_plan is not None:
                self.build_plan_button.clicked.connect(self._invoke_build_plan)
            if self._model_required:
                if isinstance(self.model_input, CredentialInput):
                    self.model_input.line_edit.textChanged.connect(
                        self._refresh_build_plan_availability
                    )
                else:
                    self.model_input.combo_box.currentIndexChanged.connect(
                        self._refresh_build_plan_availability
                    )
            if self._temperature_required and self.temperature_input is not None:
                self.temperature_input.spin_box.valueChanged.connect(
                    self._refresh_build_plan_availability
                )
            if self._max_tokens_required and self.max_tokens_input is not None:
                self.max_tokens_input.spin_box.valueChanged.connect(
                    self._refresh_build_plan_availability
                )
            for control_name in self._required_additional_control_names:
                control_input = self.additional_control_inputs[control_name]
                if isinstance(control_input, CredentialInput):
                    control_input.line_edit.textChanged.connect(
                        self._refresh_build_plan_availability
                    )
                elif isinstance(control_input, SelectInput):
                    control_input.combo_box.currentIndexChanged.connect(
                        self._refresh_build_plan_availability
                    )
                else:
                    control_input.spin_box.valueChanged.connect(
                        self._refresh_build_plan_availability
                    )
            self._refresh_build_plan_availability()
            header_layout.addWidget(self.build_plan_button)
    
            runs_content = QWidget(self.sidebar_content)
            runs_content.setObjectName("sidebarRunsContent")
            runs_layout = QVBoxLayout(runs_content)
            runs_layout.setContentsMargins(0, 0, 0, 0)
            runs_layout.setSpacing(layout_metrics.metric("related-gap"))
    
            self.run_rows: dict[str, _RetainedRunRow] = {}
            for run in projection.runs:
                row = _RetainedRunRow(
                    run,
                    selection_operation=(
                        self._handle_run_selection
                        if (
                            run.selectable
                            and (
                                self._command_router.run_selection_available
                                or bool(self._retained_workspace_projections)
                            )
                        )
                        else None
                    ),
                    parent=runs_content,
                )
                self.run_rows[run.run_id] = row
                runs_layout.addWidget(row)
    
            self.runs_empty_label: QLabel | None = None
            if not projection.runs:
                self.runs_empty_label = QLabel(
                    "No runs",
                    runs_content,
                )
                self.runs_empty_label.setObjectName("sidebarRunsEmptyState")
                self.runs_empty_label.setAccessibleName("No runs")
                self.runs_empty_label.setProperty(
                    "authoritySemantics",
                    "presentation-only",
                )
                self.runs_empty_label.setWordWrap(True)
                runs_layout.addWidget(self.runs_empty_label)
    
            self.runs_card = CardWidget(
                "Runs",
                runs_content,
                title_role="section-heading",
                parent=self.sidebar_content,
            )
            self.runs_card.setObjectName("sidebarRunsCard")
            self.sidebar_layout.addWidget(self.runs_card)
            self.sidebar_layout.addStretch(1)

        def _required_default_controls_resolved(self) -> bool:
            if self.reasoning_input is not None and self.reasoning_input.value is None:
                return False
            if self.scenario_input is not None:
                scenario = self._scenario_choice_by_label.get(self.scenario_input.value)
                model = self._model_choice_by_label.get(self.model_input.value)
                if scenario is None or model is None or scenario.model_value != model.model_value:
                    return False
            if self._model_required:
                value = self.model_input.value
                if not isinstance(value, str) or not value.strip():
                    return False
            if (
                self._temperature_required
                and self.temperature_input is not None
                and self.temperature_input.value is None
            ):
                return False
            if (
                self._max_tokens_required
                and self.max_tokens_input is not None
                and self.max_tokens_input.value is None
            ):
                return False
            return True

        def _required_additional_controls_resolved(self) -> bool:
            profile = self.additional_control_inputs.get("capture_mode")
            acknowledgement = self.additional_control_inputs.get("diagnostic_privacy_acknowledged")
            if profile and profile.value == "deep_telemetry" and (
                    not acknowledgement or acknowledgement.value != DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
                    or not self._diagnostic_is_accepted()):
                return False
            for control_name in self._required_additional_control_names:
                value = self.additional_control_inputs[control_name].value
                if value is None:
                    return False
                if isinstance(value, str) and not value.strip():
                    return False
            return True

        def _refresh_runner_menu_availability(self) -> None:
            controls_resolved = (self._required_default_controls_resolved()
                                 and self._required_additional_controls_resolved())
            test_available = (self._on_test_runner is not None
                              and self._runner_diagnostic_supported and controls_resolved)
            self.runner_test_action.setEnabled(test_available and not self._operation_locks_controls
                                               and not self._runner_check_pending)
            self.runner_check_action.setEnabled(
                self._on_check_runner is not None and self._sidebar_projection.selected_runner is not None
                and not self._operation_locks_controls and not self._runner_check_pending
            )

        def _refresh_build_plan_availability(self, *args: object) -> None:
            del args
            if not hasattr(self, "build_plan_button"):
                return
            controls_resolved = (
                self._required_default_controls_resolved()
                and self._required_additional_controls_resolved()
            )
            self._refresh_runner_menu_availability()
            available = (
                self._projected_build_plan_available
                and controls_resolved
            )
            self.build_plan_button.set_role(
                "primary" if available else "unavailable"
            )
            self.build_plan_button.setEnabled(available and not self._operation_locks_controls)
            if not self._projected_build_plan_available:
                self.build_plan_button.setAccessibleDescription(
                    "Unavailable until projected discovery and prerequisites permit planning"
                )
            elif not self._required_default_controls_resolved():
                self.build_plan_button.setAccessibleDescription(
                    "Unavailable until every required default runner control has a value"
                )
            elif not available:
                profile = self.additional_control_inputs.get("capture_mode")
                reason = ("Sensitive diagnostics require an explicit privacy and overhead acknowledgement"
                          if profile and profile.value == "deep_telemetry" else
                          "Unavailable until every required runner control has a value")
                self.build_plan_button.setAccessibleDescription(reason)
            else:
                self.build_plan_button.setAccessibleDescription("")

        def sidebar_input_snapshot(self) -> SidebarInputSnapshot:
            """Return current transient sidebar intent without creating authority."""
    
            selected_model_value = self.model_input.value
            model_authority_controls: tuple[SidebarControlInputSnapshot, ...] = ()
            if self._model_choice_by_label and selected_model_value is not None:
                selected_choice = self._model_choice_by_label[selected_model_value]
                selected_model_value = selected_choice.model_value
                if selected_choice.selection_mode is not None:
                    model_authority_controls = (
                        SidebarControlInputSnapshot(
                            control_name=selected_choice.selection_mode_control_name,
                            value=selected_choice.selection_mode,
                        ),
                    )
    
            projected_additional_controls = tuple(
                SidebarControlInputSnapshot(
                    control_name=control_name,
                    value=control_input.value,
                    secret=self._additional_control_secret_flags[control_name],
                )
                for control_name, control_input
                in self.additional_control_inputs.items()
            )
            if self.reasoning_input is not None:
                projected_additional_controls += (SidebarControlInputSnapshot(
                    control_name=self._reasoning_effort_control_name,
                    value=self.reasoning_input.value,
                ),)
            scope = (self.benchmark_input.value, self.prompt_folder_input.text())
            if getattr(self, "_treatment_exclusion_scope", None) != scope:
                self._treatment_exclusion_scope = scope
                self._excluded_treatments = set()
            return SidebarInputSnapshot(
                iterations=self.iterations_input.value(),
                randomize_treatment_start=self.randomize_treatment_start_checkbox.isChecked(),
                randomize_per_iteration=(
                    self.randomize_treatment_start_checkbox.isChecked()
                    and self.randomize_per_iteration_checkbox.isChecked()
                ),
                run_cache_validation_replays=self.cache_replays_checkbox.isChecked(),
                prompt_folder=self.prompt_folder_input.text(),
                excluded_treatments=tuple(sorted(self._excluded_treatments)),
                benchmark=self.benchmark_input.value,
                runner=self.runner_input.value,
                model=selected_model_value,
                credential=self.credential_input.value,
                temperature=(
                    self.temperature_input.value
                    if self.temperature_input is not None
                    else None
                ),
                max_tokens=(
                    self.max_tokens_input.value
                    if self.max_tokens_input is not None
                    else None
                ),
                additional_controls=(
                    model_authority_controls + projected_additional_controls
                ),
                model_discovery_context_fingerprints=(
                    self._model_discovery_context_fingerprints
                ),
            )

        def _browse_prompt_folder(self):
            folder = QFileDialog.getExistingDirectory(self, "Choose prompt folder", self.prompt_folder_input.text())
            if folder:
                self.prompt_folder_input.setText(folder)

        def _set_randomize_treatment_start_enabled(self, enabled: bool) -> None:
            self._randomize_treatment_start_enabled = enabled
            self._persist_shell_preference("randomize_treatment_start", enabled)

        def _set_randomize_per_iteration_enabled(self, enabled: bool) -> None:
            self._randomize_per_iteration_enabled = enabled
            self._persist_shell_preference("randomize_per_iteration", enabled)

        def _set_cache_replays_enabled(self, enabled: bool) -> None:
            self._cache_replays_enabled = enabled
            self._persist_shell_preference("run_cache_validation_replays", enabled)

        def _set_iteration_count(self, value: int) -> None:
            self._iteration_count = value

        def _handle_benchmark_selection_changed(self, *args: object) -> None:
            del args
            selected_benchmark = self.benchmark_input.value
            if selected_benchmark is None:
                return
            self._apply_workspace_tab_visibility()
            if self._on_benchmark_selected is not None:
                self._on_benchmark_selected(selected_benchmark)

        def _handle_runner_selection_changed(self, *args: object) -> None:
            del args
            self._diagnostic_runner_changed()
            if self._on_runner_selected is None:
                return
            selected_runner = self.runner_input.value
            if selected_runner is None:
                return
            self._on_runner_selected(selected_runner)

        def _refresh_reasoning_options(self, selected: str | None = None) -> None:
            choice = self._model_choice_by_label.get(self.model_input.value)
            efforts = choice.reasoning_efforts if choice is not None else ()
            options = tuple(value for value, _ in efforts)
            default = choice.default_reasoning_effort if choice is not None else None
            self.reasoning_input.set_options(
                options, selected if selected in options else default,
                option_labels=tuple(
                    {"xhigh": "Extra High"}.get(value, value.replace("_", " ").capitalize())
                    + (" (default)" if value == default else "")
                    for value in options
                ),
            )
            self.reasoning_input.combo_box.setEnabled(bool(options))

        def _handle_reasoning_model_changed(self, *args: object) -> None:
            del args
            self._refresh_reasoning_options(self.reasoning_input.value)
            self._refresh_build_plan_availability()
            self._handle_sidebar_intent_changed()

        def _handle_scenario_changed(self, *args: object) -> None:
            del args
            choice = self._scenario_choice_by_label.get(self.scenario_input.value)
            previous = self.model_input.combo_box.blockSignals(True)
            try:
                self.model_input.set_value(choice.label if choice is not None else None)
            finally:
                self.model_input.combo_box.blockSignals(previous)
            self._refresh_build_plan_availability()
            self._handle_sidebar_intent_changed()

        def _handle_model_scenario_changed(self, *args: object) -> None:
            del args
            choice = self._model_choice_by_label.get(self.model_input.value)
            previous = self.scenario_input.combo_box.blockSignals(True)
            try:
                self.scenario_input.set_value(choice.scenario_label if choice is not None else None)
            finally:
                self.scenario_input.combo_box.blockSignals(previous)
            self._refresh_build_plan_availability()
            self._handle_sidebar_intent_changed()

        def _handle_sidebar_intent_changed(self, *args: object) -> None:
            del args
            if self._on_sidebar_intent_changed is None:
                return
            self._on_sidebar_intent_changed(self.sidebar_input_snapshot())

else:

    class SidebarControllerMixin:
        pass
