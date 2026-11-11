"""Presentation-only capture workspace for original and replay telemetry."""

from __future__ import annotations

from AgMark.gui.views.progress import CAPTURE_SOURCE_COLUMNS, ProgressProjection
from AgMark.gui.widgets.tables import PYSIDE6_AVAILABLE as TABLES_AVAILABLE, SemanticTableView

PYSIDE6_AVAILABLE = TABLES_AVAILABLE

try:
    if not PYSIDE6_AVAILABLE:
        raise ImportError
    from PySide6.QtCore import QThread, Qt, Signal
    from PySide6.QtWidgets import QHeaderView, QLabel, QVBoxLayout, QWidget
except ImportError:
    PYSIDE6_AVAILABLE = False


if PYSIDE6_AVAILABLE:
    from AgMark.gui.widgets.responsive import ResponsiveView, wrap_text

    class CaptureView(ResponsiveView):
        projectionRequested = Signal(object)

        def __init__(
            self,
            projection: ProgressProjection,
            *,
            parent: QWidget | None = None,
        ) -> None:
            if not isinstance(projection, ProgressProjection):
                raise ValueError("projection must be a ProgressProjection")
            super().__init__(parent)
            self.setObjectName("captureWorkspaceView")
            self.setAccessibleName("Capture workspace")
            self.setProperty("authoritySemantics", "presentation-only")
            self._projection = projection
            self._projection_applied = False

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            self.capture_status_label = QLabel(self)
            self.capture_status_label.setAccessibleName(
                "Capture completion and independent outcomes"
            )
            wrap_text(self.capture_status_label)
            layout.addWidget(self.capture_status_label)

            self.capture_source_table = SemanticTableView(
                CAPTURE_SOURCE_COLUMNS,
                accessible_name="Original Run and Validation Replay capture sources",
                parent=self,
            )
            self.capture_source_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Interactive
            )
            self.capture_source_table.setMinimumHeight(150)
            layout.addWidget(self.capture_source_table, 1)

            self.projectionRequested.connect(
                self._apply_projection, Qt.ConnectionType.QueuedConnection
            )
            self._apply_projection(projection)

        @property
        def projection(self) -> ProgressProjection:
            return self._projection

        @property
        def run_id(self) -> str:
            return self._projection.run_id

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        def set_projection(self, projection: ProgressProjection) -> None:
            if not isinstance(projection, ProgressProjection):
                raise ValueError("projection must be a ProgressProjection")
            if QThread.currentThread() == self.thread():
                self._apply_projection(projection)
            else:
                self.projectionRequested.emit(projection)

        def _apply_projection(self, projection: ProgressProjection) -> None:
            previous = self._projection
            same_generation = (
                self._projection_applied
                and previous.generation_id == projection.generation_id
            )
            self._projection = projection
            if not same_generation or previous.capture_sources != projection.capture_sources:
                rows = tuple(source.to_table_row() for source in projection.capture_sources)
                if (same_generation
                        and tuple((source.capture, source.source) for source in previous.capture_sources)
                        == tuple((source.capture, source.source) for source in projection.capture_sources)):
                    self.capture_source_table.table_model.update_rows(rows)
                else:
                    vertical = (
                        self.capture_source_table.verticalScrollBar().value()
                        if same_generation else 0
                    )
                    horizontal = (
                        self.capture_source_table.horizontalScrollBar().value()
                        if same_generation else 0
                    )
                    self.capture_source_table.set_rows(rows)
                    self.capture_source_table.verticalScrollBar().setValue(vertical)
                    self.capture_source_table.horizontalScrollBar().setValue(horizontal)

            self.capture_source_table.setVisible(bool(projection.capture_sources))
            status = " · ".join(value for value in (
                projection.evidence_status,
                projection.benchmark_status,
                projection.telemetry_status,
                projection.capture_summary,
            ) if value)
            self.capture_status_label.setText(
                status or "Capture information is not yet available."
            )
            self._projection_applied = True

else:
    class CaptureView:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for CaptureView")


__all__ = ["PYSIDE6_AVAILABLE", "CaptureView"]
