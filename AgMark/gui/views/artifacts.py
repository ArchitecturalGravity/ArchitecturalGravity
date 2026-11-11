"""Concrete Artifacts workspace view for the ArcGrav desktop GUI.

The view is a projection client. It renders caller-supplied retained-artifact
metadata and invokes only caller-supplied operations whose availability has
already been established by shared/GUI authority. Visible names, statuses,
hashes, and file presence never determine safe-open availability or verification
and acceptance status.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from AgMark.gui.widgets.actions import ArtifactActionButton, Operation
from AgMark.gui.widgets.tables import (
    PYSIDE6_AVAILABLE,
    STATUS_SEMANTICS_ROLE,
    SemanticTableView,
    TableCell,
    TableColumn,
    TableRow,
)


ARTIFACTS_COLUMNS = (
    TableColumn("artifact", "Artifact"),
    TableColumn("type", "Type"),
    TableColumn("status", "Status"),
    TableColumn("integrity_hash", "Integrity Hash (SHA256)"),
    TableColumn("size", "Size", alignment="right"),
    TableColumn("actions", "Actions"),
)


def _require_visible_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")
    return value


def _optional_visible_text(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_visible_text(value, name=name)


def _require_bool(value: bool, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _require_operation(value: Operation, *, name: str) -> Operation:
    if not callable(value):
        raise ValueError(f"{name} must be callable")
    return value


@dataclass(frozen=True, slots=True)
class ArtifactActionProjection:
    """Caller-owned operation availability for one artifact action."""

    operation: Operation
    available: bool
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        _require_operation(self.operation, name="operation")
        available = _require_bool(self.available, name="available")
        reason = _optional_visible_text(
            self.unavailable_reason,
            name="unavailable_reason",
        )
        if reason is not None and available:
            raise ValueError(
                "unavailable_reason requires available=False"
            )


@dataclass(frozen=True, slots=True)
class ArtifactRowProjection:
    """Caller-supplied presentation state for one retained artifact."""

    artifact_id: str
    artifact: str
    artifact_icon: str
    artifact_type: str
    status: str
    status_icon: str
    integrity_hash: str
    size: str
    open_action: ArtifactActionProjection
    reveal_action: ArtifactActionProjection
    status_semantics: str | None = None
    reference: str | None = None
    capture_invocation_ids: tuple[str, ...] = ()
    capture_scope: str | None = None

    def __post_init__(self) -> None:
        _require_visible_text(self.artifact_id, name="artifact_id")
        _require_visible_text(self.artifact, name="artifact")
        _require_visible_text(self.artifact_icon, name="artifact_icon")
        _require_visible_text(self.artifact_type, name="artifact_type")
        _require_visible_text(self.status, name="status")
        _require_visible_text(self.status_icon, name="status_icon")
        _require_visible_text(self.integrity_hash, name="integrity_hash")
        _require_visible_text(self.size, name="size")
        if not isinstance(self.open_action, ArtifactActionProjection):
            raise ValueError("open_action must be an ArtifactActionProjection")
        if not isinstance(self.reveal_action, ArtifactActionProjection):
            raise ValueError("reveal_action must be an ArtifactActionProjection")
        _optional_visible_text(self.status_semantics, name="status_semantics")
        if isinstance(self.capture_invocation_ids, (str, bytes)):
            raise ValueError("capture_invocation_ids must be a sequence of identities")
        identities = tuple(self.capture_invocation_ids)
        for identity in identities:
            _require_visible_text(identity, name="capture invocation identity")
        if self.capture_scope not in {None, "original", "replay"}:
            raise ValueError("capture_scope must be original or replay")
        if identities and self.capture_scope is None:
            raise ValueError("linked capture identities require a scope")
        object.__setattr__(self, "capture_invocation_ids", identities)

    def to_table_row(self) -> TableRow:
        return TableRow(
            {
                "artifact": f"{self.artifact_icon} {self.artifact}",
                "type": self.artifact_type,
                "status": TableCell(
                    f"{self.status_icon} {self.status}",
                    status_semantics=self.status_semantics,
                ),
                "integrity_hash": self.integrity_hash,
                "size": self.size,
                "actions": "Open  Reveal",
            }
        )


@dataclass(frozen=True, slots=True)
class ArtifactsProjection:
    """Exact retained-run artifact projection supplied by shared GUI boundaries."""

    run_id: str
    rows: Sequence[ArtifactRowProjection] = ()
    empty_state: str | None = None

    def __post_init__(self) -> None:
        _require_visible_text(self.run_id, name="run_id")
        if isinstance(self.rows, (str, bytes)):
            raise ValueError("rows must be a sequence of ArtifactRowProjection values")
        rows = tuple(self.rows)
        if any(not isinstance(row, ArtifactRowProjection) for row in rows):
            raise ValueError("rows must contain only ArtifactRowProjection values")
        artifact_ids = tuple(row.artifact_id for row in rows)
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("artifact_id values must be unique within a projection")
        empty_state = _optional_visible_text(self.empty_state, name="empty_state")
        if not rows and empty_state is None:
            raise ValueError(
                "empty Artifacts projections require an explicit caller-supplied empty_state"
            )
        object.__setattr__(self, "rows", rows)


try:
    if not PYSIDE6_AVAILABLE:
        raise ImportError
    from PySide6.QtCore import QThread, Qt, Signal
    from PySide6.QtWidgets import QApplication, QHBoxLayout, QHeaderView, QLabel, QVBoxLayout, QWidget
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:
    from AgMark.gui.widgets.responsive import ResponsiveView, apply_minimum, wrap_text

    class ArtifactsView(ResponsiveView):
        """Compact six-column retained-artifact projection."""

        projectionRequested = Signal(object)

        def __init__(
            self,
            projection: ArtifactsProjection,
            *,
            parent: QWidget | None = None,
        ) -> None:
            if not isinstance(projection, ArtifactsProjection):
                raise ValueError("projection must be an ArtifactsProjection")
            super().__init__(parent)

            self.setObjectName("artifactsWorkspaceView")
            self.setAccessibleName("Artifacts workspace")
            self.setProperty("authoritySemantics", "presentation-only")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.empty_state_label = QLabel(self)
            self.empty_state_label.setObjectName("artifactsEmptyState")
            self.empty_state_label.setAccessibleName("Artifact availability")
            self.empty_state_label.setWordWrap(True)
            apply_minimum(self.empty_state_label, 320, 64, False)
            layout.addWidget(self.empty_state_label)

            self.table = SemanticTableView(
                ARTIFACTS_COLUMNS,
                accessible_name="Retained artifacts",
                parent=self,
            )
            apply_minimum(self.table, 480, 260)
            for column in (0, 3):
                self.table.horizontalHeader().setSectionResizeMode(
                    column, QHeaderView.ResizeMode.Interactive
                )
            layout.addWidget(self.table, 1)

            self._projection = projection
            self._action_holders: list[QWidget] = []
            self._action_buttons: dict[
                str, tuple[ArtifactActionButton, ArtifactActionButton]
            ] = {}

            self.projectionRequested.connect(
                self._apply_projection,
                Qt.ConnectionType.QueuedConnection,
            )
            self._apply_projection(projection)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def projection(self) -> ArtifactsProjection:
            return self._projection

        @property
        def run_id(self) -> str:
            return self._projection.run_id

        @property
        def action_buttons(
            self,
        ) -> Mapping[str, tuple[ArtifactActionButton, ArtifactActionButton]]:
            return MappingProxyType(self._action_buttons)

        def set_projection(self, projection: ArtifactsProjection) -> None:
            """Replace caller-owned retained-artifact state on the GUI event thread."""

            if not isinstance(projection, ArtifactsProjection):
                raise ValueError("projection must be an ArtifactsProjection")
            if QThread.currentThread() == self.thread():
                self._apply_projection(projection)
                return
            self.projectionRequested.emit(projection)

        def _clear_action_widgets(self) -> None:
            for holder in self._action_holders:
                holder.deleteLater()
            self._action_holders.clear()
            self._action_buttons.clear()

        def _action_button(
            self,
            label: str,
            action: ArtifactActionProjection,
            *,
            parent: QWidget,
        ) -> ArtifactActionButton:
            button = ArtifactActionButton(
                label,
                action.operation,
                available=action.available,
                parent=parent,
            )
            button.setMinimumHeight(32)
            button.setProperty(
                "callerUnavailableReason",
                action.unavailable_reason or "",
            )
            if action.unavailable_reason is not None:
                button.setAccessibleDescription(action.unavailable_reason)
            return button

        def _install_action_widgets(self, rows: Sequence[ArtifactRowProjection]) -> None:
            model = self.table.table_model
            action_column = len(ARTIFACTS_COLUMNS) - 1
            for row_index, row in enumerate(rows):
                holder = QWidget(self.table)
                holder.setObjectName("artifactActions")
                holder.setAccessibleName(f"Actions for {row.artifact}")

                actions_layout = QHBoxLayout(holder)
                actions_layout.setContentsMargins(4, 2, 4, 2)
                actions_layout.setSpacing(6)

                open_button = self._action_button(
                    "Open",
                    row.open_action,
                    parent=holder,
                )
                reveal_button = self._action_button(
                    "Reveal",
                    row.reveal_action,
                    parent=holder,
                )
                open_button.ensurePolished()
                reveal_button.ensurePolished()
                holder.setAutoFillBackground(True)
                actions_layout.addWidget(open_button)
                actions_layout.addWidget(reveal_button)
                actions_layout.addStretch(1)
                holder.setMinimumSize(
                    open_button.minimumSizeHint().width()
                    + reveal_button.minimumSizeHint().width() + actions_layout.spacing() + 8,
                    max(32, open_button.minimumSizeHint().height(),
                        reveal_button.minimumSizeHint().height()) + 4,
                )

                self.table.setIndexWidget(
                    model.index(row_index, action_column),
                    holder,
                )
                self._action_holders.append(holder)
                self._action_buttons[row.artifact_id] = (
                    open_button,
                    reveal_button,
                )

        def _fit_text_columns(self) -> None:
            # Keep long filenames and hashes from pushing actions off screen.
            width = self.table.viewport().width()
            self.table.setColumnWidth(0, max(240, min(360, int(width * 0.34))))
            self.table.setColumnWidth(3, max(180, min(280, int(width * 0.25))))

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            if hasattr(self, "table"):
                self._fit_text_columns()

        def _apply_projection(self, projection: ArtifactsProjection) -> None:
            self._clear_action_widgets()
            self._projection = projection
            self.table.set_rows(tuple(row.to_table_row() for row in projection.rows))

            has_rows = bool(projection.rows)
            self.table.setVisible(has_rows)
            self.empty_state_label.setVisible(not has_rows)
            self.empty_state_label.setText(
                "" if has_rows else (projection.empty_state or "")
            )
            if has_rows:
                self._install_action_widgets(projection.rows)
                self.table.resizeRowsToContents()
                # Index widgets are not represented by the model's size hints.
                for index, holder in enumerate(self._action_holders):
                    self.table.setRowHeight(index, max(
                        self.table.rowHeight(index), holder.minimumHeight() + 4
                    ))
                action_column = len(ARTIFACTS_COLUMNS) - 1
                self.table.horizontalHeader().setSectionResizeMode(
                    action_column, QHeaderView.ResizeMode.Fixed
                )
                self.table.setColumnWidth(action_column, max(
                    max(holder.minimumWidth(), holder.minimumSizeHint().width())
                    for holder in self._action_holders
                ) + 2)
            self._fit_text_columns()


else:

    class ArtifactsView:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for ArtifactsView")


__all__ = [
    "ARTIFACTS_COLUMNS",
    "ArtifactActionProjection",
    "ArtifactRowProjection",
    "ArtifactsProjection",
    "ArtifactsView",
    "PYSIDE6_AVAILABLE",
    "STATUS_SEMANTICS_ROLE",
]
