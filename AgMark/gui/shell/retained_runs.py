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
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
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
    class _RetainedRunRow(QFrame):
        """One retained-run projection row with presentation-only local selection."""

        def __init__(
            self,
            projection: RetainedRunProjection,
            *,
            selection_operation: RunSelectionOperation | None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.run_id = projection.run_id
            self._selection_operation = selection_operation
            self.setObjectName("retainedRunRow")
            self.setProperty("authoritySemantics", "presentation-only")

            layout_metrics = DEFAULT_LAYOUT_METRICS
            root = QVBoxLayout(self)
            root.setContentsMargins(
                layout_metrics.metric("compact-panel-padding-x"),
                layout_metrics.metric("compact-panel-padding-y"),
                layout_metrics.metric("compact-panel-padding-x"),
                layout_metrics.metric("compact-panel-padding-y"),
            )
            root.setSpacing(layout_metrics.metric("compact-panel-gap"))

            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(layout_metrics.metric("space-xs"))

            self.identity_label = QLabel(projection.display_identity, self)
            self.identity_label.setObjectName("retainedRunIdentity")
            self.identity_label.setAccessibleName("Run identity")
            self.identity_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                True,
            )
            header.addWidget(self.identity_label, 1)

            self.status_badge = StatusBadge(
                projection.state_label,
                projection.state_tone,
                parent=self,
            )
            self.status_badge.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                True,
            )
            header.addWidget(self.status_badge)

            root.addLayout(header)

            self.timestamp_label = QLabel(projection.timestamp, self)
            self.timestamp_label.setObjectName("retainedRunTimestamp")
            self.timestamp_label.setAccessibleName("Run timestamp")
            self.timestamp_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                True,
            )
            root.addWidget(self.timestamp_label)

            self.setAccessibleName(
                (
                    f"Select prior run {projection.display_identity}"
                    if projection.selectable
                    else f"Current run {projection.display_identity}"
                )
            )
            self.setFocusPolicy(
                Qt.FocusPolicy.StrongFocus
                if selection_operation is not None
                else Qt.FocusPolicy.NoFocus
            )
            self.setProperty("clickableRunRow", selection_operation is not None)
            if selection_operation is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor)

            self.set_selected(projection.selected)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def selected(self) -> bool:
            return bool(self.property("selected"))

        def set_selected(self, selected: bool) -> None:
            selected = _require_bool(selected, name="selected")
            self.setProperty("selected", selected)

            background = DEFAULT_LIGHT_THEME.color(
                "surface-selected" if selected else "surface-panel"
            )
            border = DEFAULT_LIGHT_THEME.color(
                "accent-primary" if selected else "border-default"
            )
            focus_border = DEFAULT_LIGHT_THEME.color("focus-ring")
            self.setStyleSheet(
                "QFrame#retainedRunRow {"
                f"background-color: {background};"
                f"border: 1px solid {border};"
                "border-radius: 4px;"
                "}"
                'QFrame#retainedRunRow[clickableRunRow="true"]:hover:enabled {'
                f"border-color: {DEFAULT_LIGHT_THEME.color('accent-primary-hover')};"
                "}"
                "QFrame#retainedRunRow:focus:hover:enabled, QFrame#retainedRunRow:focus {"
                f"border: 2px solid {focus_border};"
                "}"
            )
            self.setAccessibleDescription(
                "Selected retained run" if selected else "Retained run"
            )

        def mouseReleaseEvent(self, event) -> None:
            if (
                self._selection_operation is not None
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._activate()
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def keyPressEvent(self, event) -> None:
            if (
                self._selection_operation is not None
                and event.key()
                in (
                    Qt.Key.Key_Return,
                    Qt.Key.Key_Enter,
                    Qt.Key.Key_Space,
                )
            ):
                self._activate()
                event.accept()
                return
            super().keyPressEvent(event)

        def _activate(self, checked: bool = False) -> None:
            del checked
            if self._selection_operation is not None:
                self._selection_operation(self.run_id)
else:

    class _RetainedRunRow:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for retained-run rows")
