"""Concrete Progress workspace view for the ArcGrav desktop GUI.

This view projects caller-supplied active-generation progress. Visual completion,
labels, colors, and recent events remain presentation-only and never create
accepted, blocked, verified, report authority.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from AgMark.gui.widgets.containers import (
    PYSIDE6_AVAILABLE as CONTAINERS_AVAILABLE,
    CardWidget,
)
from AgMark.gui.widgets.progress import (
    PYSIDE6_AVAILABLE as PROGRESS_AVAILABLE,
    ProgressIndicator,
    StageStepper,
)
from AgMark.gui.widgets.tables import (
    PYSIDE6_AVAILABLE as TABLES_AVAILABLE,
    STATUS_SEMANTICS_ROLE,
    SemanticTableView,
    TableCell,
    TableColumn,
    TableRow,
)

RUN_STAGES = (
    "Planning",
    "Golden Admission",
    "Execution",
    "Evaluation",
    "Finalization",
)
CAPTURE_SOURCE_COLUMNS = (
    TableColumn("capture", "Run / Treatment / Attempt"),
    TableColumn("source", "Source"),
    TableColumn("state", "State"),
    TableColumn("events", "Events"),
    TableColumn("bytes", "Bytes"),
    TableColumn("health", "Capture Health"),
    TableColumn("reason", "Availability / Reason"),
)
TREATMENT_PROGRESS_COLUMNS = (
    TableColumn("treatment", "Treatment"),
    TableColumn("progress", "Progress"),
    TableColumn("cases", "Cases"),
    TableColumn("current_stage", "Current Stage"),
    TableColumn("status", "Status"),
)


def _text(value: str | None, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")
    return value


def _progress(completed: int, total: int, prefix: str) -> None:
    if isinstance(completed, bool) or not isinstance(completed, int):
        raise ValueError(f"{prefix} completed cases must be an integer")
    if isinstance(total, bool) or not isinstance(total, int):
        raise ValueError(f"{prefix} total cases must be an integer")
    if total <= 0:
        raise ValueError(f"{prefix} total cases must be greater than zero")
    if completed < 0 or completed > total:
        raise ValueError(
            f"{prefix} completed cases must be between zero and total cases"
        )


@dataclass(frozen=True, slots=True)
class OverallProgressProjection:
    completed_cases: int
    total_cases: int
    elapsed_time: str

    def __post_init__(self) -> None:
        _progress(self.completed_cases, self.total_cases, "overall")
        _text(self.elapsed_time, "elapsed_time")

    @property
    def remaining_cases(self) -> int:
        return self.total_cases - self.completed_cases


@dataclass(frozen=True, slots=True)
class TreatmentProgressProjection:
    treatment_id: str
    treatment: str
    completed_cases: int
    total_cases: int
    current_stage: str
    status: str
    status_icon: str
    status_semantics: str | None = None

    def __post_init__(self) -> None:
        _text(self.treatment_id, "treatment_id")
        _text(self.treatment, "treatment")
        _progress(self.completed_cases, self.total_cases, "treatment")
        _text(self.current_stage, "current_stage")
        _text(self.status, "status")
        _text(self.status_icon, "status_icon")
        _text(self.status_semantics, "status_semantics", optional=True)

    @property
    def percent(self) -> float:
        return self.completed_cases / self.total_cases * 100.0

    def to_table_row(self, *, finalizing=False) -> TableRow:
        return TableRow(
            {
                "treatment": self.treatment,
                "progress": (
                    f"{self.completed_cases}/{self.total_cases} cases · finalizing"
                    if finalizing else
                    f"{self.completed_cases} of {self.total_cases} ({self.percent:.0f}%)"
                ),
                "cases": f"{self.completed_cases}/{self.total_cases}",
                "current_stage": self.current_stage,
                "status": TableCell(
                    f"{self.status_icon} {self.status}",
                    status_semantics=self.status_semantics,
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class ProgressEventProjection:
    generation_id: str
    timestamp: str
    event_icon: str
    text: str

    def __post_init__(self) -> None:
        _text(self.generation_id, "event generation_id")
        _text(self.timestamp, "timestamp")
        _text(self.event_icon, "event_icon")
        _text(self.text, "event text")


@dataclass(frozen=True, slots=True)
class CaptureSourceProjection:
    capture: str
    source: str
    state: str
    events: str
    bytes: str
    health: str
    reason: str
    scope: str | None = None
    invocation_id: str | None = None
    treatment_id: str | None = None
    attempt_id: str | None = None

    def __post_init__(self):
        for name in ("capture", "source", "state", "events", "bytes", "health", "reason"):
            _text(getattr(self, name), name)
        if self.scope not in {None, "original", "replay"}:
            raise ValueError("capture scope must be original or replay")
        for name in ("invocation_id", "treatment_id", "attempt_id"):
            _text(getattr(self, name), name, optional=True)

    def to_table_row(self):
        return TableRow({name: getattr(self, name) for name in
                        ("capture", "source", "state", "events", "bytes", "health", "reason")})


@dataclass(frozen=True, slots=True)
class ProgressProjection:
    run_id: str
    generation_id: str
    overall: OverallProgressProjection | None
    treatments: Sequence[TreatmentProgressProjection]
    active_stage_index: int | None
    active_stage_description: str | None
    events: Sequence[ProgressEventProjection]
    summary_empty_state: str | None = None
    treatment_empty_state: str | None = None
    run_stage_empty_state: str | None = None
    activity_text: str | None = None
    current_stage_step: int | None = None
    unscored: bool = False
    run_active: bool = False
    lifecycle_complete: bool = False
    capture_sources: Sequence[CaptureSourceProjection] = ()
    capture_summary: str | None = None
    capture_stage: str | None = None
    capture_identity: str | None = None
    evidence_status: str | None = None
    benchmark_status: str | None = None
    telemetry_status: str | None = None

    def __post_init__(self) -> None:
        if type(self.run_active) is not bool or type(self.lifecycle_complete) is not bool:
            raise ValueError("activity/completion flags must be booleans")
        if self.run_active and self.lifecycle_complete:
            raise ValueError("active work cannot claim completed lifecycle")
        for name in ("capture_summary", "capture_stage", "capture_identity", "evidence_status", "benchmark_status", "telemetry_status"):
            _text(getattr(self, name), name, optional=True)
        sources = tuple(self.capture_sources)
        if any(type(source) is not CaptureSourceProjection for source in sources):
            raise ValueError("capture_sources must contain CaptureSourceProjection values")
        object.__setattr__(self, "capture_sources", sources)
        _text(self.activity_text, "activity_text", optional=True)
        if self.current_stage_step is not None and (
            type(self.current_stage_step) is not int
            or not 1 <= self.current_stage_step <= 7
        ):
            raise ValueError("current_stage_step must be an integer from 1 to 7 or None")
        _text(self.run_id, "run_id")
        _text(self.generation_id, "generation_id")

        if self.overall is not None and not isinstance(
            self.overall, OverallProgressProjection
        ):
            raise ValueError("overall must be an OverallProgressProjection or None")
        summary_empty = _text(
            self.summary_empty_state, "summary_empty_state", optional=True
        )
        if self.overall is None and summary_empty is None:
            raise ValueError(
                "missing overall progress requires an explicit summary_empty_state"
            )
        if self.overall is not None and summary_empty is not None:
            raise ValueError(
                "summary_empty_state is only valid when overall progress is unavailable"
            )

        if isinstance(self.treatments, (str, bytes)):
            raise ValueError("treatments must be a projection sequence")
        treatments = tuple(self.treatments)
        if any(not isinstance(row, TreatmentProgressProjection) for row in treatments):
            raise ValueError(
                "treatments must contain only TreatmentProgressProjection values"
            )
        ids = tuple(row.treatment_id for row in treatments)
        if len(ids) != len(set(ids)):
            raise ValueError("treatment_id values must be unique within a projection")
        treatment_empty = _text(
            self.treatment_empty_state, "treatment_empty_state", optional=True
        )
        if not treatments and treatment_empty is None:
            raise ValueError(
                "empty treatment progress requires an explicit treatment_empty_state"
            )
        if treatments and treatment_empty is not None:
            raise ValueError(
                "treatment_empty_state is only valid when no treatment rows are supplied"
            )
        object.__setattr__(self, "treatments", treatments)

        stage_description = _text(
            self.active_stage_description, "active_stage_description", optional=True
        )
        stage_empty = _text(
            self.run_stage_empty_state, "run_stage_empty_state", optional=True
        )
        if self.active_stage_index is None:
            if stage_description is not None:
                raise ValueError("active_stage_description requires active_stage_index")
            if stage_empty is None:
                raise ValueError(
                    "missing active stage requires an explicit run_stage_empty_state"
                )
        else:
            if isinstance(self.active_stage_index, bool) or not isinstance(
                self.active_stage_index, int
            ):
                raise ValueError("active_stage_index must be an integer or None")
            if not 0 <= self.active_stage_index < len(RUN_STAGES):
                raise ValueError(
                    "active_stage_index must identify one of the five run stages"
                )
            if stage_description is None:
                raise ValueError(
                    "active_stage_index requires active_stage_description"
                )
            if stage_empty is not None:
                raise ValueError(
                    "run_stage_empty_state is only valid without an active stage"
                )

        if isinstance(self.events, (str, bytes)):
            raise ValueError("events must be a projection sequence")
        events = tuple(self.events)
        if any(not isinstance(event, ProgressEventProjection) for event in events):
            raise ValueError(
                "events must contain only ProgressEventProjection values"
            )
        object.__setattr__(self, "events", events)


    @property
    def wheel_progress(self) -> tuple[int, int] | None:
        """Display case progress (90%) plus current run stage (10%).

        The final stage share is earned only when the lifecycle is complete.
        This indicator is visual-only, not a remaining-time prediction.
        """
        if self.overall is None:
            return None
        stage_count = len(RUN_STAGES)
        substeps = 7  # Typed capture stages refine the Execution stage.
        reached_stages = (
            stage_count * substeps if self.lifecycle_complete
            else (
                (self.active_stage_index or 0) * substeps
                + (
                    self.current_stage_step or 0
                    if self.active_stage_index == 2 else 0
                )
            )
        )
        return (
            9 * self.overall.completed_cases * stage_count * substeps
            + reached_stages * self.overall.total_cases,
            10 * self.overall.total_cases * stage_count * substeps,
        )


PYSIDE6_AVAILABLE = bool(
    CONTAINERS_AVAILABLE and PROGRESS_AVAILABLE and TABLES_AVAILABLE
)

try:
    if not PYSIDE6_AVAILABLE:
        raise ImportError
    from PySide6.QtCore import QThread, Qt, Signal
    from PySide6.QtWidgets import (
        QFrame,
        QHeaderView,
        QProgressBar,
        QHBoxLayout,
        QLabel,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:
    from AgMark.gui.widgets.responsive import (
        ResponsiveView,
        apply_minimum,
        wrap_text,
    )

    class ProgressView(ResponsiveView):
        projectionRequested = Signal(object)
        eventRequested = Signal(object)

        def __init__(
            self,
            projection: ProgressProjection,
            *,
            parent: QWidget | None = None,
        ) -> None:
            if not isinstance(projection, ProgressProjection):
                raise ValueError("projection must be a ProgressProjection")
            super().__init__(parent)
            self.setObjectName("progressWorkspaceView")
            self.setAccessibleName("Progress workspace")
            self.setProperty("authoritySemantics", "presentation-only")
            self.setProperty("completionSemantics", "visual-only")

            self._projection = projection
            self._projection_applied = False
            self._summary_values: dict[str, QLabel] = {}
            self._progress_holders: list[QWidget] = []
            self._treatment_progress: dict[str, ProgressIndicator] = {}
            self._treatment_holders: dict[str, QWidget] = {}
            self._treatment_percentages: dict[str, QLabel] = {}
            self.overall_ring: ProgressIndicator | None = None
            self.overall_bar: ProgressIndicator | None = None
            self.stage_stepper: StageStepper | None = None
            self.stage_description_card: CardWidget | None = None
            self.stage_description_label: QLabel | None = None

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(8)

            self.summary_card = QFrame(self)
            self.summary_card.setObjectName("progressSummaryCard")
            self.summary_card.setAccessibleName("Overall benchmark progress summary")
            self.summary_card.setProperty("authoritySemantics", "presentation-only")
            self.summary_card.setFrameShape(QFrame.Shape.StyledPanel)
            apply_minimum(self.summary_card, 510, 128, vertical_expanding=False)
            self._summary_layout = QHBoxLayout(self.summary_card)
            self._summary_layout.setContentsMargins(12, 12, 12, 12)
            self._summary_layout.setSpacing(8)
            root.addWidget(self.summary_card)

            body = QHBoxLayout()
            self._body_layout = body
            body.setSpacing(8)
            root.addLayout(body, 1)

            treatment_body = QWidget(self)
            treatment_layout = QVBoxLayout(treatment_body)
            treatment_layout.setContentsMargins(0, 0, 0, 0)
            treatment_layout.setSpacing(8)
            self.treatment_empty_label = QLabel(treatment_body)
            self.treatment_empty_label.setAccessibleName(
                "Treatment progress availability"
            )
            wrap_text(self.treatment_empty_label)
            apply_minimum(self.treatment_empty_label, 320, 64, vertical_expanding=False)
            treatment_layout.addWidget(self.treatment_empty_label)
            self.treatment_table = SemanticTableView(
                TREATMENT_PROGRESS_COLUMNS,
                accessible_name="Treatment progress",
                parent=treatment_body,
            )
            self.treatment_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            # Keep measured/manual column widths, but let Status absorb unused
            # horizontal space as the Progress tab grows or shrinks.
            self.treatment_table.horizontalHeader().setStretchLastSection(True)
            apply_minimum(self.treatment_table, 480, 220)
            treatment_layout.addWidget(self.treatment_table, 1)
            self.treatment_card = CardWidget(
                "Treatment Progress", treatment_body, compact=True, parent=self
            )
            apply_minimum(self.treatment_card, 510, 280)
            body.addWidget(self.treatment_card, 2)

            right = QWidget(self)
            apply_minimum(right, 300, 300)
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(8)

            self.run_stage_body = QWidget(right)
            self._stage_layout = QVBoxLayout(self.run_stage_body)
            self._stage_layout.setContentsMargins(0, 0, 0, 0)
            self._stage_layout.setSpacing(8)
            self.run_stage_card = CardWidget(
                "Run Stage", self.run_stage_body, compact=True, parent=right
            )
            apply_minimum(self.run_stage_card, 300, 300)
            right_layout.addWidget(self.run_stage_card, 1)

            body.addWidget(right, 1)

            self.projectionRequested.connect(
                self._apply_projection, Qt.ConnectionType.QueuedConnection
            )
            self.eventRequested.connect(
                self._apply_event, Qt.ConnectionType.QueuedConnection
            )
            self._apply_projection(projection)
            self.add_responsive_layout(self._summary_layout, 760)
            self.add_responsive_layout(body, 840)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def completion_semantics(self) -> str:
            return "visual-only"

        @property
        def projection(self) -> ProgressProjection:
            return self._projection

        @property
        def run_id(self) -> str:
            return self._projection.run_id

        @property
        def generation_id(self) -> str:
            return self._projection.generation_id

        @property
        def visible_events(self) -> tuple[ProgressEventProjection, ...]:
            return tuple(e for e in self._projection.events if e.generation_id == self.generation_id)

        @property
        def summary_value_labels(self) -> dict[str, QLabel]:
            return dict(self._summary_values)

        @property
        def treatment_progress_widgets(self) -> dict[str, ProgressIndicator]:
            return dict(self._treatment_progress)

        def set_projection(self, projection: ProgressProjection) -> None:
            if not isinstance(projection, ProgressProjection):
                raise ValueError("projection must be a ProgressProjection")
            if QThread.currentThread() == self.thread():
                self._apply_projection(projection)
            else:
                self.projectionRequested.emit(projection)

        def push_event(self, event: ProgressEventProjection) -> None:
            if not isinstance(event, ProgressEventProjection):
                raise ValueError("event must be a ProgressEventProjection")
            if QThread.currentThread() == self.thread():
                self._apply_event(event)
            else:
                self.eventRequested.emit(event)

        def _apply_event(self, event: ProgressEventProjection) -> None:
            if event.generation_id != self.generation_id:
                return
            self._apply_projection(
                replace(
                    self._projection,
                    events=self._projection.events + (event,),
                )
            )

        @staticmethod
        def _clear(layout) -> None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.deleteLater()
                elif item.layout() is not None:
                    ProgressView._clear(item.layout())

        def _summary_cell(self, label: str, value: str) -> QWidget:
            cell = QWidget(self.summary_card)
            apply_minimum(cell, 90, 64, vertical_expanding=False)
            layout = QVBoxLayout(cell)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            value_label = QLabel(value, cell)
            value_label.setAccessibleName(label)
            layout.addWidget(value_label)
            caption = QLabel(label, cell)
            wrap_text(caption)
            caption.setMinimumHeight(caption.heightForWidth(90))
            layout.addWidget(caption)
            self._summary_values[label] = value_label
            return cell

        @staticmethod
        def _set_text(label: QLabel, text: str) -> None:
            if label.text() != text:
                label.setText(text)

        def _rebuild_summary(self, projection: ProgressProjection) -> None:
            self.activity_label = None
            self.activity_indicator = None
            self._clear(self._summary_layout)
            self._summary_values.clear()
            self.overall_ring = None
            self.overall_bar = None
            overall = projection.overall
            if overall is None:
                label = QLabel(projection.summary_empty_state or "", self.summary_card)
                self._summary_empty_label = label
                label.setAccessibleName("Overall progress availability")
                wrap_text(label)
                apply_minimum(label, 320, 64, vertical_expanding=False)
                self._summary_layout.addWidget(label)
                return

            main = QWidget(self.summary_card)
            main.setObjectName("progressSummaryOverview")
            apply_minimum(main, 312, 104, vertical_expanding=False)
            main_layout = QHBoxLayout(main)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(8)
            self.overall_ring = ProgressIndicator(
                *projection.wheel_progress,
                form="ring",
                parent=main,
            )
            self.overall_ring.setAccessibleName("Cases and current stage progress")
            self.overall_ring.setMinimumSize(80, 80)
            main_layout.addWidget(self.overall_ring)

            block = QWidget(main)
            block.setObjectName("progressSummaryText")
            apply_minimum(block, 220, 104, vertical_expanding=False)
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(4)
            self._summary_heading = QLabel("Run Progress" if projection.run_active else "Overall Progress", block)
            block_layout.addWidget(self._summary_heading)
            count = QLabel(
                f"{overall.completed_cases} of {overall.total_cases} cases completed",
                block,
            )
            wrap_text(count)
            self._summary_count = count
            block_layout.addWidget(count)
            self.overall_bar = ProgressIndicator(
                overall.completed_cases,
                overall.total_cases,
                form="bar",
                parent=block,
            )
            # Retain the stage-aware ring while finalizing; the bar is case-only.
            pending_finalization = projection.run_active and overall.completed_cases == overall.total_cases
            self.overall_bar.setVisible(not pending_finalization)
            self.overall_bar.indicator.setMinimumHeight(24)
            apply_minimum(self.overall_bar, 180, 24, vertical_expanding=False)
            block_layout.addWidget(self.overall_bar)
            elapsed = QLabel(f"Elapsed: {overall.elapsed_time}", block)
            self._summary_elapsed = elapsed
            wrap_text(elapsed)
            block_layout.addWidget(elapsed)
            self.activity_label = QLabel(block)
            self.activity_label.setAccessibleName("Current benchmark activity")
            wrap_text(self.activity_label)
            block_layout.addWidget(self.activity_label)
            self.activity_indicator = QProgressBar(block)
            self.activity_indicator.setRange(0, 0)
            self.activity_indicator.setTextVisible(False)
            self.activity_indicator.setAccessibleName("Benchmark work is active; duration unknown")
            block_layout.addWidget(self.activity_indicator)
            main_layout.addWidget(block, 1)
            self._summary_layout.addWidget(main, 1)
            counters = QWidget(self.summary_card)
            counters.setObjectName("progressSummaryCounters")
            apply_minimum(counters, 286, 64, vertical_expanding=False)
            counters_layout = QHBoxLayout(counters)
            counters_layout.setContentsMargins(0, 0, 0, 0)
            counters_layout.setSpacing(8)
            for label, value in (
                ("Completed Cases", overall.completed_cases),
                ("Remaining Cases", overall.remaining_cases),
                ("Total Cases", overall.total_cases),
            ):
                counters_layout.addWidget(
                    self._summary_cell(label, str(value))
                )
            self._summary_layout.addWidget(counters, 0, Qt.AlignmentFlag.AlignVCenter)
            self._update_summary(projection)

        def _update_summary(self, projection: ProgressProjection) -> None:
            overall = projection.overall
            if overall is None:
                self._set_text(self._summary_empty_label, projection.summary_empty_state or "")
                return
            self._set_text(self._summary_heading, "Run Progress" if projection.run_active else "Overall Progress")
            self._set_text(self._summary_count, f"{overall.completed_cases} of {overall.total_cases} cases completed")
            self._set_text(self._summary_elapsed, f"Elapsed: {overall.elapsed_time}")
            wheel_current, wheel_total = projection.wheel_progress
            if (self.overall_ring.current, self.overall_ring.total) != (wheel_current, wheel_total):
                self.overall_ring.set_progress(wheel_current, wheel_total)
            if (self.overall_bar.current, self.overall_bar.total) != (overall.completed_cases, overall.total_cases):
                self.overall_bar.set_progress(overall.completed_cases, overall.total_cases)
            self.overall_bar.setVisible(not (
                projection.run_active and overall.completed_cases == overall.total_cases
            ))
            has_activity = projection.activity_text is not None or projection.run_active
            self._set_text(self.activity_label, projection.activity_text or "Preparing execution and telemetry capture…")
            self.activity_label.setVisible(has_activity)
            self.activity_indicator.setVisible(projection.run_active)
            for label, value in (("Completed Cases", overall.completed_cases),
                                 ("Remaining Cases", overall.remaining_cases), ("Total Cases", overall.total_cases)):
                self._set_text(self._summary_values[label], str(value))

        def _treatment_rows(self, projection):
            return tuple(row.to_table_row(finalizing=projection.run_active and row.completed_cases == row.total_cases)
                         for row in projection.treatments)

        def _rebuild_treatments(self, projection: ProgressProjection) -> None:
            self._progress_holders.clear()
            self._treatment_progress.clear()
            self._treatment_holders.clear()
            self._treatment_percentages.clear()
            # A reset owns deletion of the old index widgets. Only structural
            # identity changes reach this path; live counters preserve them.
            self.treatment_table.set_rows(self._treatment_rows(projection))
            self._update_treatments(projection, rows_changed=False)
            self.treatment_table.resizeColumnToContents(1)

        def _update_treatments(self, projection: ProgressProjection, *, rows_changed=True) -> None:
            if rows_changed:
                self.treatment_table.table_model.update_rows(self._treatment_rows(projection))
            has_rows = bool(projection.treatments)
            self.treatment_table.setVisible(has_rows)
            self.treatment_empty_label.setVisible(not has_rows)
            self._set_text(self.treatment_empty_label, "" if has_rows else (projection.treatment_empty_state or ""))
            model = self.treatment_table.table_model
            for index, row in enumerate(projection.treatments):
                key = row.treatment_id
                if projection.run_active and row.completed_cases == row.total_cases:
                    # The delegate owns the finalizing label. Remove only the
                    # widget whose case progress just completed, never paint a
                    # percentage behind finalization text.
                    holder = self._treatment_holders.pop(key, None)
                    if holder is not None:
                        self.treatment_table.setIndexWidget(model.index(index, 1), None)
                        self._treatment_progress.pop(key, None)
                        self._treatment_percentages.pop(key, None)
                    if self.treatment_table.rowHeight(index) != 33:
                        self.treatment_table.setRowHeight(index, 33)
                    width = self.treatment_table.fontMetrics().horizontalAdvance(
                        f"{row.completed_cases}/{row.total_cases} cases · finalizing") + 24
                    if width > self.treatment_table.columnWidth(1):
                        self.treatment_table.setColumnWidth(1, width)
                    continue
                progress = self._treatment_progress.get(key)
                if progress is None:
                    holder = QWidget(self.treatment_table)
                    holder.setAutoFillBackground(True)
                    layout = QHBoxLayout(holder)
                    layout.setContentsMargins(2, 2, 2, 2)
                    progress = ProgressIndicator(row.completed_cases, row.total_cases, form="bar", parent=holder)
                    if hasattr(progress.indicator, "setTextVisible"):
                        progress.indicator.setTextVisible(False)
                    progress.indicator.setMinimumHeight(16)
                    layout.addWidget(progress, 1)
                    percentage = QLabel(f"{row.percent:.0f}%", holder)
                    # Reserve the largest normal percent width once, so count
                    # updates do not trigger table column measurement.
                    percentage.setMinimumWidth(percentage.fontMetrics().horizontalAdvance("100%"))
                    layout.addWidget(percentage)
                    holder.ensurePolished()
                    minimum = layout.minimumSize()
                    holder.setMinimumSize(max(150, minimum.width()), max(32, minimum.height()))
                    self.treatment_table.setIndexWidget(model.index(index, 1), holder)
                    self.treatment_table.setRowHeight(index, holder.minimumHeight() + 1)
                    self.treatment_table.setColumnWidth(1, max(self.treatment_table.columnWidth(1), holder.minimumWidth()))
                    self._treatment_holders[key] = holder
                    self._treatment_progress[key] = progress
                    self._treatment_percentages[key] = percentage
                else:
                    if (progress.current, progress.total) != (row.completed_cases, row.total_cases):
                        progress.set_progress(row.completed_cases, row.total_cases)
                    self._set_text(self._treatment_percentages[key], f"{row.percent:.0f}%")
            self._progress_holders = list(self._treatment_holders.values())

        def _rebuild_stage(self, projection: ProgressProjection) -> None:
            self._clear(self._stage_layout)
            self.stage_stepper = None
            self.stage_description_card = None
            self.stage_description_label = None
            if projection.active_stage_index is None:
                label = QLabel(
                    projection.run_stage_empty_state or "", self.run_stage_body
                )
                self._stage_empty_label = label
                label.setAccessibleName("Run stage availability")
                wrap_text(label)
                apply_minimum(label, 260, 64, vertical_expanding=False)
                self._stage_layout.addWidget(label)
                return

            index = projection.active_stage_index
            stages = ("Planning", "Execution", "Finalization") if projection.unscored else RUN_STAGES
            position = (0 if index == 0 else 1 if index < 4 else 2) if projection.unscored else index
            self.stage_stepper = StageStepper(stages,
                len(stages) if projection.lifecycle_complete else position,
                orientation="vertical", parent=self.run_stage_body)
            apply_minimum(self.stage_stepper, 260, 160, vertical_expanding=False)
            self._stage_layout.addWidget(self.stage_stepper)
            description_body = QWidget(self.run_stage_body)
            description_layout = QVBoxLayout(description_body)
            description_layout.setContentsMargins(0, 0, 0, 0)
            self.stage_description_label = QLabel(
                projection.active_stage_description or "", description_body
            )
            wrap_text(self.stage_description_label)
            self.stage_description_label.setMinimumHeight(36)
            # Long generation identifiers must wrap inside the allotted stage
            # column rather than impose their unbroken width on the workspace.
            description_policy = QSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum,
            )
            description_policy.setHeightForWidth(True)
            self.stage_description_label.setSizePolicy(description_policy)
            description_layout.addWidget(self.stage_description_label)
            self.stage_description_card = CardWidget(
                ("Finished" if projection.lifecycle_complete else
                 ("Finalization" if index == 4 else "Execution") if projection.unscored else RUN_STAGES[index]),
                description_body, compact=True, parent=self.run_stage_body
            )
            apply_minimum(self.stage_description_card, 260, 90, vertical_expanding=False)
            self._stage_layout.addWidget(self.stage_description_card)
            self._capture_stage_label = QLabel(self.run_stage_body)
            self._capture_stage_label.setAccessibleName("Current capture and finalization stage")
            wrap_text(self._capture_stage_label)
            self._stage_layout.addWidget(self._capture_stage_label)
            self._capture_identity_label = QLabel(self.run_stage_body)
            self._capture_identity_label.setAccessibleName("Active run treatment and attempt")
            wrap_text(self._capture_identity_label)
            self._stage_layout.addWidget(self._capture_identity_label)
            self._stage_layout.addStretch(1)
            self._update_stage(projection)

        def _update_stage(self, projection: ProgressProjection) -> None:
            index = projection.active_stage_index
            if index is None:
                self._set_text(self._stage_empty_label, projection.run_stage_empty_state or "")
                return
            position = (0 if index == 0 else 1 if index < 4 else 2) if projection.unscored else index
            current = len(self.stage_stepper.stages) if projection.lifecycle_complete else position
            if self.stage_stepper.current != current:
                self.stage_stepper.set_progress(current)
            title = ("Finished" if projection.lifecycle_complete else
                     ("Finalization" if index == 4 else "Execution") if projection.unscored else RUN_STAGES[index])
            if self.stage_description_card.title != title:
                self.stage_description_card.set_title(title)
            self._set_text(self.stage_description_label, projection.active_stage_description or "")
            for label, value in ((self._capture_stage_label, projection.capture_stage),
                                 (self._capture_identity_label, projection.capture_identity)):
                self._set_text(label, value or "")
                label.setVisible(bool(value))

        def _apply_projection(self, projection: ProgressProjection) -> None:
            previous = self._projection
            same_generation = self._projection_applied and previous.generation_id == projection.generation_id
            self._projection = projection
            if not same_generation or (previous.overall is None) != (projection.overall is None):
                self._rebuild_summary(projection)
            elif any(getattr(previous, field) != getattr(projection, field) for field in
                     ("overall", "summary_empty_state", "activity_text", "run_active", "benchmark_status",
                      "active_stage_index", "current_stage_step", "lifecycle_complete")):
                self._update_summary(projection)
            if not same_generation or tuple(row.treatment_id for row in previous.treatments) != tuple(row.treatment_id for row in projection.treatments):
                self._rebuild_treatments(projection)
            elif (previous.treatments, previous.run_active, previous.treatment_empty_state) != (projection.treatments, projection.run_active, projection.treatment_empty_state):
                self._update_treatments(projection)
            if not same_generation or (previous.active_stage_index is None, previous.unscored) != (projection.active_stage_index is None, projection.unscored):
                self._rebuild_stage(projection)
            elif any(getattr(previous, field) != getattr(projection, field) for field in
                     ("active_stage_index", "active_stage_description", "run_stage_empty_state", "lifecycle_complete", "capture_stage", "capture_identity")):
                self._update_stage(projection)
            self._projection_applied = True



else:

    class ProgressView:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for ProgressView")


__all__ = [
    "PYSIDE6_AVAILABLE",
    "RUN_STAGES",
    "STATUS_SEMANTICS_ROLE",
    "TREATMENT_PROGRESS_COLUMNS",
    "OverallProgressProjection",
    "ProgressEventProjection",
    "ProgressProjection",
    "ProgressView",
    "TreatmentProgressProjection",
]
