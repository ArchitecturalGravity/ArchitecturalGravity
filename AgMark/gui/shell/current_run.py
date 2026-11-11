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
    StatusBadge,
)
from AgMark.gui.widgets.tabs import (
    PYSIDE6_AVAILABLE as TABS_PYSIDE6_AVAILABLE,
    TabWidget,
)

try:
    from PySide6.QtCore import QEvent, QTimer, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QGridLayout,
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

if PYSIDE6_AVAILABLE:
    from AgMark.gui.widgets.wrapping_text import WrappingText

    class CurrentRunRegion(QFrame):
        """Reflow summary cards at their readable floors, not their text lengths."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.cards_layout = None
            self.cards = []
            self._columns = None

        def set_available_width(self, width):
            if self.cards_layout is None or not self.cards:
                return
            margins = self.layout().contentsMargins()
            available = max(0, width - margins.left() - margins.right())
            gap = self.cards_layout.horizontalSpacing()
            floors = [max(card.minimumWidth(), card.minimumSizeHint().width())
                      for card in self.cards]
            if available >= sum(floors) + gap * (len(floors) - 1):
                columns = len(self.cards)
            elif len(self.cards) > 1 and available >= sum(floors[:2]) + gap:
                columns = 2
            else:
                columns = 1
            if columns == self._columns:
                return
            self._columns = columns
            while self.cards_layout.count():
                self.cards_layout.takeAt(0)
            for column in range(3):
                self.cards_layout.setColumnStretch(column, 0)
            for index, card in enumerate(self.cards):
                if columns == 2 and index == 2:
                    self.cards_layout.addWidget(card, 1, 0, 1, 2)
                else:
                    self.cards_layout.addWidget(card, index // columns, index % columns)
            for column in range(columns):
                self.cards_layout.setColumnStretch(column, 4 if column == 1 else 3)
            self.layout().invalidate()
            self.updateGeometry()

        def resizeEvent(self, event):
            self.set_available_width(event.size().width())
            super().resizeEvent(event)


    class CurrentRunScrollArea(QScrollArea):
        """Use the viewport width before old grid minima can force overflow."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._refresh_pending = False
            self._last_refresh_state = None
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._refresh_summary_height)

        def setWidget(self, widget):
            super().setWidget(widget)
            widget.installEventFilter(self)
            self._refresh_pending = False
            self._last_refresh_state = None

        def _refresh_summary_height(self, available_width=None, available_height=None):
            self._refresh_pending = False
            region = self.widget()
            if region is None:
                return
            # Start from the width without a vertical scrollbar. A scrollbar
            # left over from a taller, narrower layout must not force the cards
            # back into one column when a two-column summary now fits.
            width = self.maximumViewportSize().width() if available_width is None else available_width
            layout = region.layout()
            tabs = getattr(self.window(), "workspace_tabs", None)
            tab_bar_height = tabs.tabBar().sizeHint().height() if tabs is not None else 36
            available = self.parentWidget().height() if available_height is None else available_height
            # Allocate the content's actual requirement, not QScrollArea's cached
            # preferred size. Only scroll after the summary and tab floors compete.
            budget = max(0, min(available - 120, max(96, available - 240 - tab_bar_height)))
            def layout_state():
                return (region, width, available, region._columns,
                        layout.minimumSize(), layout.totalHeightForWidth(width),
                        tuple((reader.width(), reader.minimumHeight())
                              for reader in region.findChildren(WrappingText)))

            # A trial reflow itself posts LayoutRequest. Ignore its unchanged
            # follow-up, but remeasure when the viewport or child requirements
            # change (including wrapped text after its real resize).
            if layout_state() == self._last_refresh_state:
                return
            region.set_available_width(width)
            height = layout.totalHeightForWidth(width)
            layout_width = width
            if height > budget:
                layout_width = max(0, width - self.verticalScrollBar().sizeHint().width())
                region.set_available_width(layout_width)
                height = layout.totalHeightForWidth(layout_width)
            maximum = min(max(0, height), budget)
            if self.minimumHeight() != maximum or self.maximumHeight() != maximum:
                self.setFixedHeight(maximum)
            # setFixedHeight can synchronously resize using the old viewport
            # width, before Qt removes its now-unneeded scrollbar.
            region.set_available_width(layout_width)
            self._last_refresh_state = layout_state()

        def eventFilter(self, watched, event):
            if (event.type() == QEvent.Type.LayoutRequest
                    and not getattr(self, "_refresh_pending", False)):
                self._refresh_pending = True
                self._refresh_timer.start(0)
            return super().eventFilter(watched, event)

        def resizeEvent(self, event):
            region = self.widget()
            if isinstance(region, CurrentRunRegion):
                region.set_available_width(self.viewport().width())
            super().resizeEvent(event)


    class CurrentRunPanelMixin:
        def _populate_current_run(
            self,
            projection: CurrentRunProjection | None,
        ) -> None:
            self.current_run_region = CurrentRunRegion(self.workspace)
            self.current_run_region.setObjectName("currentRunRegion")
            summary_heading = (
                projection.heading if projection is not None else "Current Run"
            )
            self.current_run_region.setAccessibleName(summary_heading)
            self.current_run_region.setProperty(
                "authoritySemantics",
                "presentation-only",
            )
            self.current_run_region.setMinimumWidth(0)
            self.current_run_region.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            layout_metrics = DEFAULT_LAYOUT_METRICS
    
            root = QVBoxLayout(self.current_run_region)
            root.setContentsMargins(
                layout_metrics.metric("space-md"),
                layout_metrics.metric("space-md"),
                layout_metrics.metric("space-md"),
                layout_metrics.metric("space-md"),
            )
            root.setSpacing(layout_metrics.metric("space-sm"))
            root.setAlignment(Qt.AlignmentFlag.AlignTop)
    
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(layout_metrics.metric("space-sm"))
    
            self.current_run_heading = QLabel(
                summary_heading,
                self.current_run_region,
            )
            self.current_run_heading.setObjectName("currentRunHeading")
            self.current_run_heading.setAccessibleName(summary_heading)
            header.addWidget(self.current_run_heading)
            header.addStretch(1)
    
            self.current_run_identity_label: QLabel | None = None
            self.current_run_status: StatusBadge | None = None
            self.current_run_timestamp_label: WrappingText | None = None
            self.execution_boundary_card: CardWidget | None = None
            self.run_plan_card: CardWidget | None = None
            self.treatments_card: CardWidget | None = None
            self.treatment_file_labels: tuple[WrappingText, ...] = ()
            self.treatment_remove_buttons: dict[str, QToolButton] = {}
            self.execution_boundary_rows: tuple[tuple[QLabel, WrappingText], ...] = ()
            self.run_plan_rows: tuple[tuple[QLabel, QWidget], ...] = ()
            self.execution_detail_rows: tuple[tuple[QLabel, WrappingText], ...] = ()
            self.capture_runtime_advisory: QFrame | None = None
            self.capture_runtime_advisory_icon: QLabel | None = None
            self.capture_runtime_advisory_text: WrappingText | None = None
            self.accept_plan_button: ActionButton | None = None
            self.start_benchmark_button: ActionButton | None = None
            self.delete_run_button: ActionButton | None = None
            self.current_run_empty_state_card: CardWidget | None = None
            self.current_run_empty_state_label: QLabel | None = None
    
            if projection is not None:
                self.current_run_identity_label = QLabel(
                    projection.run_identity,
                    self.current_run_region,
                )
                self.current_run_identity_label.setAccessibleName("Run identity")
                self.current_run_identity_label.setMinimumWidth(0)
                self.current_run_identity_label.setSizePolicy(
                    QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
                )
                header.addWidget(self.current_run_identity_label, 1)
    
                self.current_run_status = StatusBadge(
                    projection.state_label,
                    projection.state_tone,
                    parent=self.current_run_region,
                )
                header.addWidget(self.current_run_status)
    
                self.current_run_timestamp_label = WrappingText(
                    projection.timestamp,
                    self.current_run_region,
                )
                self.current_run_timestamp_label.setAccessibleName("Run timestamp")
                timestamp_policy = self.current_run_timestamp_label.sizePolicy()
                timestamp_policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
                self.current_run_timestamp_label.setSizePolicy(timestamp_policy)
                header.addWidget(self.current_run_timestamp_label)
    
            root.addLayout(header)
    
            if projection is None:
                empty_content = QWidget(self.current_run_region)
                empty_layout = QVBoxLayout(empty_content)
                empty_layout.setContentsMargins(0, 0, 0, 0)
                empty_layout.setSpacing(layout_metrics.metric("space-xs"))
    
                self.current_run_empty_state_label = QLabel(
                    CURRENT_RUN_EMPTY_MESSAGE,
                    empty_content,
                )
                self.current_run_empty_state_label.setObjectName(
                    "currentRunEmptyStateMessage"
                )
                self.current_run_empty_state_label.setAccessibleName(
                    "Current Run empty state"
                )
                self.current_run_empty_state_label.setWordWrap(True)
                self.current_run_empty_state_label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                empty_layout.addWidget(self.current_run_empty_state_label)
    
                self.current_run_empty_state_card = CardWidget(
                    CURRENT_RUN_EMPTY_TITLE,
                    empty_content,
                    parent=self.current_run_region,
                )
                self.current_run_empty_state_card.setObjectName(
                    "currentRunEmptyStateCard"
                )
                self.current_run_empty_state_card.setProperty(
                    "authoritySemantics",
                    "presentation-only",
                )
                self.current_run_empty_state_card.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Minimum,
                )
                self.current_run_empty_state_card.setMinimumHeight(
                    layout_metrics.metric("control-height")
                    + (2 * layout_metrics.metric("panel-padding"))
                    + layout_metrics.metric("section-gap")
                )
                root.addWidget(self.current_run_empty_state_card)
    
            if projection is not None:
                cards = QGridLayout()
                self.current_run_region.cards_layout = cards
                cards.setContentsMargins(0, 0, 0, 0)
                cards.setSpacing(layout_metrics.metric("related-gap"))
    
                boundary_content = QWidget(self.current_run_region)
                boundary_layout = QVBoxLayout(boundary_content)
                boundary_layout.setContentsMargins(0, 0, 0, 0)
                boundary_layout.setSpacing(layout_metrics.metric("space-xs"))
                boundary_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                boundary_rows: list[tuple[QLabel, WrappingText]] = []
                boundary_items = tuple(zip(
                    CURRENT_RUN_BOUNDARY_LABELS,
                    projection.execution_boundary.ordered_values,
                    strict=True,
                ))
                boundary_items = (
                    *boundary_items[:3],
                    *((f"{label}:", value) for label, value
                      in projection.execution_boundary.runtime_details),
                    *boundary_items[3:],
                )
                for label, value in boundary_items:
                    row_content = QWidget(boundary_content)
                    row_content.setMinimumWidth(0)
                    row_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                    label_widget = QLabel(label, row_content)
                    if "\n" in value:
                        label_widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                    value_widget = WrappingText(value, row_content)
                    value_widget.setAccessibleName(label.removesuffix(":"))
                    value_widget.setTextInteractionFlags(
                        Qt.TextInteractionFlag.TextSelectableByMouse
                    )
                    value_widget.setMinimumWidth(100)
                    row = QFormLayout(row_content)
                    row.setContentsMargins(0, 0, 0, 0)
                    row.setSpacing(layout_metrics.metric("space-xs"))
                    row.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
                    row.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                    if label == "Capture:":
                        row.addRow(label_widget)
                        row.addRow(value_widget)
                    else:
                        row.addRow(label_widget, value_widget)
                    boundary_layout.addWidget(row_content)
                    boundary_rows.append((label_widget, value_widget))
                self.execution_boundary_rows = tuple(boundary_rows)
                self.execution_boundary_card = CardWidget(
                    "Execution Boundary",
                    boundary_content,
                    icon_role="current-run-boundary",
                    compact=True,
                    parent=self.current_run_region,
                )
                self.execution_boundary_card.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                self.execution_boundary_card.setMinimumWidth(260)
                self.current_run_region.cards.append(self.execution_boundary_card)
    
                plan_content = QWidget(self.current_run_region)
                plan_layout = QFormLayout(plan_content)
                plan_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
                plan_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                plan_layout.setContentsMargins(0, 0, 0, 0)
                plan_layout.setSpacing(layout_metrics.metric("space-xs"))
                plan_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                plan_rows: list[tuple[QLabel, QWidget]] = []
                plan_items = tuple(zip(
                    CURRENT_RUN_PLAN_LABELS,
                    projection.run_plan.ordered_values,
                    strict=True,
                ))
                if projection.unscored:
                    plan_items = tuple(
                        (label, value) for label, value in plan_items
                        if label not in {"Treatments", "Cases", "Evaluation"}
                    )
                elif projection.run_plan.treatment_files:
                    plan_items = tuple(
                        (label, value) for label, value in plan_items
                        if label != "Treatments"
                    )
                for index, (label, value) in enumerate(plan_items, start=1):
                    label_widget = QLabel(f"{index}. {label}", plan_content)
                    if label == "Execution" and projection.run_plan.execution_details:
                        details_widget = QWidget(plan_content)
                        details_widget.setMinimumWidth(0)
                        details_widget.setAccessibleName("Execution settings")
                        details_layout = QFormLayout(details_widget)
                        details_layout.setContentsMargins(0, 0, 0, 0)
                        details_layout.setHorizontalSpacing(layout_metrics.metric("space-sm"))
                        details_layout.setVerticalSpacing(layout_metrics.metric("space-xs"))
                        details_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
                        details_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                        detail_rows = []
                        for detail_label, detail_value in projection.run_plan.execution_details:
                            name_widget = QLabel(detail_label, details_widget)
                            field_widget = WrappingText(detail_value, details_widget)
                            field_widget.setMinimumWidth(0)
                            field_widget.setAccessibleName(detail_label)
                            field_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                            details_layout.addRow(name_widget, field_widget)
                            detail_rows.append((name_widget, field_widget))
                        self.execution_detail_rows = tuple(detail_rows)
                        plan_layout.addRow(label_widget, details_widget)
                        plan_rows.append((label_widget, details_widget))
                        continue
                    value_widget = WrappingText(value, plan_content)
                    value_widget.setTextInteractionFlags(
                        Qt.TextInteractionFlag.TextSelectableByMouse
                    )
                    value_widget.setMinimumWidth(100)
                    plan_layout.addRow(label_widget, value_widget)
                    plan_rows.append((label_widget, value_widget))
                self.run_plan_rows = tuple(plan_rows)

                if projection.run_plan.capture_runtime_advisory is not None:
                    advisory = projection.run_plan.capture_runtime_advisory
                    tone = projection.run_plan.capture_runtime_advisory_tone
                    self.capture_runtime_advisory = QFrame(plan_content)
                    self.capture_runtime_advisory.setObjectName("captureRuntimeAdvisory")
                    self.capture_runtime_advisory.setAccessibleName(
                        "Capture runtime warning" if tone == "warning" else "Capture runtime information")
                    self.capture_runtime_advisory.setProperty("authoritySemantics", "presentation-only")
                    self.capture_runtime_advisory.setProperty("statusTone", tone)
                    self.capture_runtime_advisory.setStyleSheet(
                        "QFrame#captureRuntimeAdvisory { background: "
                        + DEFAULT_LIGHT_THEME.color("state-" + tone + "-surface")
                        + "; border-radius: 4px; }")
                    advisory_layout = QHBoxLayout(self.capture_runtime_advisory)
                    advisory_layout.setContentsMargins(8, 8, 8, 8)
                    advisory_layout.setSpacing(layout_metrics.metric("space-sm"))
                    self.capture_runtime_advisory_icon = QLabel(self.capture_runtime_advisory)
                    self.capture_runtime_advisory_icon.setObjectName("captureRuntimeAdvisoryIcon")
                    self.capture_runtime_advisory_icon.setAccessibleName(
                        "Warning: runtime version mismatch" if tone == "warning" else "Runtime version information")
                    icon_role = projection.run_plan.capture_runtime_advisory_icon_role
                    self.capture_runtime_advisory_icon.setProperty("iconRole", icon_role)
                    self.capture_runtime_advisory_icon.setPixmap(semantic_icon(icon_role).pixmap(18, 18))
                    advisory_layout.addWidget(self.capture_runtime_advisory_icon, 0, Qt.AlignmentFlag.AlignTop)
                    self.capture_runtime_advisory_text = WrappingText(advisory, self.capture_runtime_advisory)
                    self.capture_runtime_advisory_text.setObjectName("captureRuntimeAdvisoryText")
                    self.capture_runtime_advisory_text.setAccessibleName(advisory)
                    self.capture_runtime_advisory_text.setMinimumWidth(0)
                    self.capture_runtime_advisory_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    advisory_layout.addWidget(self.capture_runtime_advisory_text, 1)
                    plan_layout.addRow(self.capture_runtime_advisory)
    
                if not projection.is_prior_run:
                    action_row = QHBoxLayout()
                    action_row.setContentsMargins(
                        0,
                        layout_metrics.metric("space-xs"),
                        0,
                        0,
                    )
                    action_row.setSpacing(layout_metrics.metric("space-sm"))
                    action_row.addStretch(1)
    
                    self.accept_plan_button = ActionButton(
                        "Accept Plan",
                        (
                            "secondary"
                            if projection.accept_plan_available
                            else "unavailable"
                        ),
                        icon_role="plan-accept",
                        parent=plan_content,
                    )
                    if projection.accept_plan_available:
                        self.accept_plan_button.clicked.connect(
                            self._invoke_accept_plan
                        )
                    action_row.addWidget(self.accept_plan_button)
    
                    self.start_benchmark_button = ActionButton(
                        "Start Benchmark",
                        (
                            "primary"
                            if projection.start_benchmark_available
                            else "unavailable"
                        ),
                        icon_role="benchmark-start",
                        parent=plan_content,
                    )
                    if projection.start_benchmark_available:
                        self.start_benchmark_button.clicked.connect(
                            self._invoke_start_benchmark
                        )
                    action_row.addWidget(self.start_benchmark_button)
                    plan_layout.addRow(action_row)
    
                self.run_plan_card = CardWidget(
                    "Run Plan",
                    plan_content,
                    icon_role="current-run-plan",
                    compact=True,
                    parent=self.current_run_region,
                )
                self.run_plan_card.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                self.run_plan_card.setMinimumWidth(300)
                self.current_run_region.cards.append(self.run_plan_card)

                if projection.unscored or projection.run_plan.treatment_files:
                    treatments_content = QWidget(self.current_run_region)
                    treatments_layout = QVBoxLayout(treatments_content)
                    treatments_layout.setContentsMargins(0, 0, 0, 0)
                    treatments_layout.setSpacing(layout_metrics.metric("space-xs"))
                    treatments_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                    file_labels: list[WrappingText] = []
                    filenames = projection.run_plan.treatment_files
                    can_remove = (
                        not projection.is_prior_run
                        and projection.state_label in {"Pending", "Accepted"}
                        and self._on_build_plan is not None
                        and len(filenames) > 1
                    )
                    for filename in filenames:
                        file_row = QHBoxLayout()
                        file_row.setContentsMargins(0, 0, 0, 0)
                        file_row.setSpacing(layout_metrics.metric("space-xs"))
                        file_label = WrappingText(filename, treatments_content)
                        file_label.setAccessibleName(f"Treatment {filename}")
                        file_label.setTextInteractionFlags(
                            Qt.TextInteractionFlag.TextSelectableByMouse
                        )
                        file_row.addWidget(file_label, 1)
                        remove_button = QToolButton(treatments_content)
                        remove_button.setObjectName("removeTreatmentButton")
                        remove_button.setText("×")
                        remove_button.setAutoRaise(True)
                        remove_button.setAccessibleName(f"Remove treatment {filename}")
                        remove_button.setEnabled(can_remove)
                        if can_remove:
                            remove_button.clicked.connect(
                                lambda checked=False, name=filename:
                                    self._invoke_remove_treatment(name)
                            )
                        file_row.addWidget(remove_button)
                        treatments_layout.addLayout(file_row)
                        file_labels.append(file_label)
                        self.treatment_remove_buttons[filename] = remove_button
                    if not filenames:
                        treatments_layout.addWidget(
                            QLabel("No treatments", treatments_content)
                        )
                    self.treatment_file_labels = tuple(file_labels)
                    self.treatments_card = CardWidget(
                        "Treatments",
                        treatments_content,
                        icon_role="current-run-treatments",
                        compact=True,
                        parent=self.current_run_region,
                    )
                    self.treatments_card.setSizePolicy(
                        QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Preferred,
                    )
                    self.treatments_card.setMinimumWidth(180)
                    self.current_run_region.cards.append(self.treatments_card)
                root.addLayout(cards)
                self.current_run_region.set_available_width(self.current_run_scroll.viewport().width())
    
                if projection.is_prior_run and projection.delete_run_available:
                    self.delete_run_button = ActionButton(
                        "Delete Run",
                        "destructive",
                        icon_role="run-delete",
                        parent=self.current_run_region,
                    )
                    run_id = projection.run_identity
                    self.delete_run_button.clicked.connect(
                        lambda checked=False, value=run_id: self._invoke_delete_run(
                            value,
                            checked,
                        )
                    )
                    header.addWidget(self.delete_run_button)
    
            self.current_run_scroll.setWidget(self.current_run_region)

else:

    class CurrentRunRegion:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for the current run region")


    class CurrentRunScrollArea:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for the current run scroll area")


    class CurrentRunPanelMixin:
        pass
