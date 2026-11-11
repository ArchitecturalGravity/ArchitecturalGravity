"""Concrete Results workspace view for the ArcGrav desktop GUI.

The view is a projection client. It renders caller-supplied retained-result state
without deriving benchmark, evidence, or acceptance authority from visible
labels, colors, icons, or file/report presence.
"""

from __future__ import annotations

from collections.abc import Sequence, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from numbers import Real
from threading import Lock
from AgMark.shared.validation.codex_cache.models import ProviderRequestCacheTreatmentSummary
from AgMark.shared.reporting.replay import SUMMARY_LABELS, field_text
from AgMark.shared.reporting.measurement_presentation import presentation_measurement
from AgMark.shared.telemetry.comparison import LEGACY_COMPARISON_METRICS, project_comparison_table

from AgMark.gui.widgets.tables import (
    PYSIDE6_AVAILABLE,
    STATUS_SEMANTICS_ROLE,
    SemanticTableView,
    TableCell,
    TableColumn,
    TableRow,
)


RESULTS_COLUMNS = (
    TableColumn("treatment", "Treatment"),
    TableColumn("status", "Status"),
    TableColumn("score", "Accuracy", alignment="right"),
    *(TableColumn(key, label, alignment="right") for key, label in LEGACY_COMPARISON_METRICS),

)

CACHE_COMPARISON_COLUMNS = (
    TableColumn("metric", "Metric"),
    TableColumn("original", "Original Run", alignment="right"),
    TableColumn("replay", "Validation Replay", alignment="right"),
)
CACHE_METRICS = (
    ("cached_input_tokens", "generation_cached_input_tokens", "Cached Input"),
    ("cache_write_input_tokens", "generation_cache_write_input_tokens", "Cache Write Input"),
    ("uncached_input_tokens", "generation_uncached_input_tokens", "Uncached Input"),
    ("cache_read_fraction", "generation_cache_read_fraction", "Cache Read Fraction"),
    *((None, key, label) for key, label in SUMMARY_LABELS
      if key not in {"generation_cached_input_tokens", "generation_cache_write_input_tokens",
                     "generation_uncached_input_tokens", "generation_cache_read_fraction"}),
)


CACHE_COLUMNS = (
    TableColumn("treatment", "Treatment"),
    TableColumn("status", "Status"),
    *(TableColumn(key, label, alignment="right") for key, _, label in CACHE_METRICS[:4]),
)


def original_cache_cell(row, key):
    measurement = row.measurements.get(key, {}) if key else {}
    if measurement.get("value") is not None:
        return measurement_cell(measurement, role=key)
    availability = measurement.get("availability", "unavailable")
    return TableCell("Unavailable" if availability == "unavailable" else availability.replace("_", " ").capitalize())


def replay_cache_cell(value, key):
    if value is not None and value.sampling_policy == "disabled_by_user":
        return TableCell("Disabled by user")
    metric = value.metrics.get(key, {}).get("mean") if value else None
    if metric is None:
        return TableCell("Unavailable")
    text = "Average: " + field_text(metric.field) if metric.field.value is not None else "Unavailable"
    return TableCell(text + f" [{metric.contributors}/{metric.eligible}]")


def replay_status_cell(value):
    if value is None:
        return TableCell("Unavailable")
    if value.sampling_policy == "disabled_by_user":
        return TableCell("Disabled by user — not run")
    coverage = value.coverage
    # Display retained outcomes and coverage, without inventing aggregate success.
    outcomes = ", ".join(dict.fromkeys(replay.status.replace("_", " ") for replay in value.replays)) or "Unavailable"
    partial = " (partial)" if coverage.comparable_coverage.availability == "partial" else ""
    return TableCell(f"{outcomes.capitalize()}; {coverage.validation_replays_comparable}/{coverage.scored_observation_count} comparable{partial}")


def measurement_text(measurement):
    value = measurement.get("value")
    if value is None:
        return "—"
    text = f"{value:g}" if isinstance(value, float) else str(value)
    unit = measurement.get("unit", "")
    if unit not in {None, "", "1", "tokens", "calls"}:
        text += f" {unit}"
    if measurement.get("kind") == "token_event_proxy":
        text += " (estimate: token-event proxy)"
    elif measurement.get("kind") in {"estimated_cost", "offline_token_estimate", "timing_estimate"}:
        text += " (estimate)"
    elif measurement.get("kind") == "provider_reported_cost":
        text += " (reported)"
    if measurement.get("availability") == "partial":
        text += " (partial)"
    elif measurement.get("availability") in {"unsupported", "disabled", "failed", "rejected", "settlement_timeout", "non_comparable"}:
        text += " (" + measurement["availability"].replace("_", " ") + ")"
    elif measurement.get("scope") == "capture_source_health" and measurement.get("availability") == "unavailable":
        text += " (unavailable)"
    return text


def measurement_cell(measurement, *, role=""):
    displayed = presentation_measurement(role, measurement)
    text = displayed["comparison_display"] if "comparison_display" in displayed else measurement_text(displayed)
    if "comparison_display" not in displayed and displayed.get("value") is None and role in {"provider_request_count", "average_request_duration_ms", "average_direct_ttft_ms", "average_direct_tbt_ms", "token_usage_event_count"}:
        text = "Unavailable"
    return TableCell(text)



def _prepare_inspection(row):
    """Prepare immutable-snapshot display data without creating Qt objects."""
    value = row.validation
    requests = []
    disabled = value is not None and value.sampling_policy == "disabled_by_user"
    if disabled:
        status = "Original Run: retained treatment aggregate. Validation Replay: Disabled by user — not run."
    elif value:
        coverage = value.coverage
        status = ("Original Run: retained treatment aggregate. Validation Replay: generation metrics, "
            "averages of comparable replays (separate aggregate, not request pairs). "
            f"Coverage: {coverage.validation_replays_comparable}/{coverage.scored_observation_count} comparable; "
            f"{coverage.validation_replays_completed}/{coverage.validation_replays_planned} completed. "
            f"Sampling: {value.sampling_policy.replace('_', ' ')}. Replays excluded from score.")
    else:
        status = "Original Run: retained treatment aggregate. Validation unavailable; no retained replay authority."
    comparison = tuple(TableRow({"metric": label, "original": original_cache_cell(row, original_key),
        "replay": replay_cache_cell(value, replay_key)}) for original_key, replay_key, label in CACHE_METRICS)
    records = [("Original Run — retained measurements", {
        key: row.measurements.get(key, {"value": None, "availability": "unavailable"})
        for key, _, _ in CACHE_METRICS if key}, (("Root cache key — inferred",
            row.root_cache_policies or {"value": None, "availability": "unavailable",
                "reason": "No retained audited original-run root cache policy supplied by the shared layer."}),))]
    for score in row.score_details:
        repetitions = ", ".join(str(value) for value in score.get("repetition_ids", ()))
        records.append((
            f"Score evidence — case {score.get('case_id')}; repetitions {repetitions}",
            score,
            (),
        ))
    if value:
        summary = value.to_dict()
        replay_records = summary.pop("replays", ())
        records.append(("Validation Replay — treatment statistics and coverage", summary, ()))
        from AgMark.shared.validation.codex_cache.diagnostics import retained_diagnostics
        for replay, retained in zip(value.replays, replay_records):
            label = f"Replay {replay.validation_id} · observation {replay.validates_observation_id} · repetition {replay.repetition_id}"
            if retained["requests"]:
                requests.append((label, retained["requests"], ()))
            records.append((label,
                retained, (("Transport diagnostics and direct telemetry availability", retained_diagnostics(replay)),
                    ("Root cache key — inferred", {"value": None, "availability": "unavailable",
                        "reason": "This replay has no retained audited fresh-root cache-policy inference. Original-run policy does not identify replay policy."}))))
    request_status = ("Validation Replay disabled by user — not run." if disabled else
        "Retained Validation Replay requests, grouped by replay." if requests else
        "No retained Validation Replay request records for this treatment.")
    return {"status": status, "comparison": comparison, "records": tuple(records),
            "requests": tuple(requests), "request_status": request_status}


def _prepare_results(projection):
    """Build display-only cells once where the caller constructs the snapshot.

    Desktop projection workers perform this Python work before GUI delivery.
    Nothing in this cache is retained authority or part of saved history.
    """
    comparison = project_comparison_table(tuple(row.telemetry_projection for row in projection.rows),
        legacy_measurements=tuple(row.measurements for row in projection.rows))
    columns = tuple(c for c in RESULTS_COLUMNS[:3] if not projection.unscored or c.key != "score") + tuple(
        TableColumn(**column) for column in comparison["columns"])
    tables = {"columns": columns, "rows": tuple(row.to_table_row(unscored=projection.unscored, comparison_measurements=values)
        for row, values in zip(projection.rows, comparison["rows"]))}
    # Transient original-run numeric records for display-only Scoring rankings.
    tables["scoring_measurements"] = tuple(comparison["rows"])
    for key, replay in (("original", False), ("replay", True)):
        tables[key] = tuple(TableRow({"treatment": row.treatment,
            "status": replay_status_cell(row.validation) if replay else TableCell(
                f"{row.status_icon} {row.status}", status_semantics=row.status_semantics),
            **{role: replay_cache_cell(row.validation, replay_key) if replay else original_cache_cell(row, role)
               for role, replay_key, _ in CACHE_METRICS[:4]}}) for row in projection.rows)
    tables["inspection"] = tuple(_prepare_inspection(row) for row in projection.rows)
    if PYSIDE6_AVAILABLE:
        from AgMark.gui.widgets.telemetry_details import telemetry_row_text
        tables["telemetry"] = tuple({section["id"]: tuple(telemetry_row_text(metric) for metric in section.get("rows", ()))
            for section in row.telemetry_projection.get("sections", ())} for row in projection.rows)
    else:
        tables["telemetry"] = tuple({} for row in projection.rows)
    return tables


def _require_visible_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")
    return value


def _optional_visible_text(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_visible_text(value, name=name)


def _score_text(value: Real | Decimal | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        raise ValueError("score must be numeric or None")
    return str(value)


@dataclass(frozen=True, slots=True)
class ResultRowProjection:
    """Caller-supplied presentation state for one Results table row."""

    treatment: str
    score: Real | Decimal | None
    evidence: str
    status: str
    status_icon: str
    status_semantics: str | None = None
    measurements: Mapping[str, object] = field(default_factory=dict)
    details: str = ""
    validation: ProviderRequestCacheTreatmentSummary | None = None
    root_cache_policies: Sequence[Mapping[str, object]] = ()
    telemetry_projection: Mapping[str, object] = field(default_factory=dict)
    execution_summary: Mapping[str, object] = field(default_factory=dict)
    score_details: Sequence[Mapping[str, object]] = ()

    def __post_init__(self) -> None:
        _require_visible_text(self.treatment, name="treatment")
        _score_text(self.score)
        _require_visible_text(self.evidence, name="evidence")
        _require_visible_text(self.status, name="status")
        _require_visible_text(self.status_icon, name="status_icon")
        _optional_visible_text(self.status_semantics, name="status_semantics")
        if not self.telemetry_projection:
            from AgMark.shared.telemetry.projection import project_treatment_telemetry
            object.__setattr__(self, "telemetry_projection", project_treatment_telemetry(
                {"roles": self.measurements, "root_cache_policies": self.root_cache_policies}))
        if self.validation is not None:
            if type(self.validation) is not ProviderRequestCacheTreatmentSummary or self.validation.treatment_id != self.treatment:
                raise ValueError("typed treatment validation differs from Results row")
            from AgMark.shared.validation.codex_cache.serialization import admit_validation
            admit_validation(self.validation.to_dict())

    def to_table_row(self, *, unscored=False, comparison_measurements=None) -> TableRow:
        if comparison_measurements is None:
            comparison_measurements = project_comparison_table((self.telemetry_projection,),
                legacy_measurements=(self.measurements,))["rows"][0]
        return TableRow(
            {
                "treatment": self.treatment,
                **({} if unscored else {"score": TableCell(_score_text(self.score))}),
                **{key: measurement_cell(value, role=key)
                   for key, value in comparison_measurements.items()},
                "status": TableCell(
                    f"{self.status_icon} {self.status}",
                    status_semantics=self.status_semantics,
                ),
            }
        )

@dataclass(frozen=True, slots=True)
class ResultsProjection:
    """Exact retained-run Results projection supplied by shared GUI boundaries."""

    run_id: str
    rows: Sequence[ResultRowProjection] = ()
    empty_state: str | None = None
    unscored: bool = False
    _presentation: Mapping = field(init=False, repr=False, compare=False, metadata={"transient": True})

    def __post_init__(self) -> None:
        _require_visible_text(self.run_id, name="run_id")
        if isinstance(self.rows, (str, bytes)):
            raise ValueError("rows must be a sequence of ResultRowProjection values")
        rows = tuple(self.rows)
        if any(not isinstance(row, ResultRowProjection) for row in rows):
            raise ValueError("rows must contain only ResultRowProjection values")
        empty_state = _optional_visible_text(self.empty_state, name="empty_state")
        if not rows and empty_state is None:
            raise ValueError(
                "empty Results projections require an explicit caller-supplied empty_state"
            )
        object.__setattr__(self, "rows", rows)
        if any(row.validation is not None and row.validation.generation_id != self.run_id for row in rows):
            raise ValueError("validation generation differs from Results")
        object.__setattr__(self, "_presentation", _prepare_results(self))


try:
    if not PYSIDE6_AVAILABLE:
        raise ImportError
    from PySide6.QtCore import QThread, Qt, Signal
    from PySide6.QtWidgets import QTabWidget, QLabel, QSplitter, QSplitterHandle, QVBoxLayout, QHBoxLayout, QLayout, QWidget, QPushButton, QButtonGroup, QScrollArea, QFrame, QTreeWidget, QTreeWidgetItem, QHeaderView
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:
    from AgMark.gui.widgets.responsive import ResponsiveView, apply_minimum
    from AgMark.gui.widgets.telemetry_details import RetainedItem

    class _RetainedBranchItem(RetainedItem):
        """Keep every typed record available; create descendants on expansion."""

        def __init__(self, label, data, extras=()):
            recorded = isinstance(data, Mapping) and "value" in data and "availability" in data
            value = data.get("value") if isinstance(data, Mapping) else data
            text = [label, (str(value) if value is not None else "Unavailable") if recorded or not isinstance(data, (Mapping, tuple, list)) else "",
                    str(data.get("availability", "")) if isinstance(data, Mapping) else "",
                    " / ".join(str(data[k]) for k in ("source", "method") if k in data) if isinstance(data, Mapping) else ""]
            super().__init__(text, data)
            self._expanded_children = False
            self._recorded = recorded
            self._extras = extras
            if (isinstance(data, (Mapping, tuple, list)) and data) or extras:
                self.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

        def materialize(self):
            if self._expanded_children:
                return
            self._expanded_children = True
            data = self._retained
            if isinstance(data, Mapping):
                children = ((key.replace("_", " "), child) for key, child in data.items()
                    if not self._recorded or key not in {"value", "availability", "source", "method"})
            elif isinstance(data, (tuple, list)):
                children = ((str(index), child) for index, child in enumerate(data, 1))
            else:
                children = ()
            self.addChildren([_RetainedBranchItem(label, child) for label, child in (*children, *self._extras)])
            self.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless)

        def childCount(self):
            self.materialize()
            return super().childCount()

        def child(self, index):
            self.materialize()
            return super().child(index)

    class _ResultsSplitterHandle(QSplitterHandle):
        def __init__(self, orientation, parent):
            super().__init__(orientation, parent)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setCursor(Qt.CursorShape.SplitVCursor)
            self.setAccessibleName("Resize treatment selector and telemetry details")
            self.setAccessibleDescription("Drag to resize the treatment selector and telemetry details. Use Up/Down when focused.")

        def keyPressEvent(self, event):
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                step = 32 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 8
                offset = -step if event.key() == Qt.Key.Key_Up else step
                self.moveSplitter(self.splitter().sizes()[0] + offset)
                event.accept()
            else:
                super().keyPressEvent(event)

        def paintEvent(self, event):
            super().paintEvent(event)
            from PySide6.QtGui import QColor, QPainter
            from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME
            painter = QPainter(self)
            painter.setPen(QColor(DEFAULT_LIGHT_THEME.color("focus-ring" if self.hasFocus() else "text-secondary")))
            x, y = self.width() // 2, self.height() // 2
            for dy in (-2, 2):
                painter.drawLine(x - 18, y + dy, x + 18, y + dy)

    class _ResultsSplitter(QSplitter):
        def createHandle(self):
            return _ResultsSplitterHandle(self.orientation(), self)

    class ResultsView(ResponsiveView):
        """Run treatment buttons with synchronized telemetry and replay inspection."""

        projectionRequested = Signal(object)

        def __init__(self, projection: ResultsProjection, *, parent=None):
            if not isinstance(projection, ResultsProjection):
                raise ValueError("projection must be a ResultsProjection")
            super().__init__(parent)
            self.setObjectName("resultsWorkspaceView")
            self.setAccessibleName("Results workspace")
            self.setProperty("authoritySemantics", "presentation-only")
            self._projection = projection
            self._revision_lock = Lock()
            self._projection_revision = 0
            self._selected_row = None
            self._selected_validation = None
            self._rendered_projection = None
            self._inspection_row = None
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            self.empty_state_label = QLabel(self)
            self.empty_state_label.setWordWrap(True)
            self.empty_state_label.setAccessibleName("Results availability")
            apply_minimum(self.empty_state_label, 320, 64, False)
            layout.addWidget(self.empty_state_label)
            self.results_splitter = _ResultsSplitter(Qt.Orientation.Vertical, self)
            self.results_splitter.setObjectName("resultsMeasurementsSplitter")
            self.results_splitter.setChildrenCollapsible(False)
            self.results_splitter.setHandleWidth(12)
            layout.addWidget(self.results_splitter, 1)
            self.treatment_panel = QWidget(self.results_splitter)
            treatments = QVBoxLayout(self.treatment_panel)
            treatments.setContentsMargins(0, 0, 0, 0)
            self.treatment_heading = QLabel("Treatments", self.treatment_panel)
            treatments.addWidget(self.treatment_heading)
            self.treatment_scroll = QScrollArea(self.treatment_panel)
            self.treatment_scroll.setObjectName("resultsTreatmentScroll")
            self.treatment_scroll.setAccessibleName("Treatments in this run")
            self.treatment_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.treatment_scroll.setWidgetResizable(True)
            self.treatment_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.treatment_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            apply_minimum(self.treatment_scroll, 320, 64, False)
            self.treatment_buttons_host = QWidget(self.treatment_scroll)
            self.treatment_buttons_layout = QHBoxLayout(self.treatment_buttons_host)
            self.treatment_buttons_layout.setContentsMargins(4, 4, 4, 4)
            self.treatment_buttons_layout.setSpacing(8)
            self.treatment_buttons_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
            self.treatment_buttons_layout.addStretch()
            self.treatment_scroll.setWidget(self.treatment_buttons_host)
            treatments.addWidget(self.treatment_scroll, 1)
            self.treatment_button_group = QButtonGroup(self)
            self.treatment_button_group.setExclusive(True)
            self.treatment_buttons = []
            self._treatment_button_ids = ()
            self.results_splitter.addWidget(self.treatment_panel)
            self.cache_panel = QWidget(self.results_splitter)
            cache = QVBoxLayout(self.cache_panel)
            cache.setContentsMargins(0, 0, 0, 0)
            self.cache_heading = QLabel("Telemetry Details", self.cache_panel)
            cache.addWidget(self.cache_heading)
            for heading in (self.treatment_heading, self.cache_heading):
                heading.setStyleSheet("font-weight: 600;")
            self.cache_tabs = QTabWidget(self.cache_panel)
            self.cache_tabs.setAccessibleName("Result measurements and details")
            self.cache_tabs.setUsesScrollButtons(True)
            self.cache_table = SemanticTableView(CACHE_COLUMNS, accessible_name="Original Run cache measurements")
            self.replay_table = SemanticTableView(CACHE_COLUMNS, accessible_name="Validation Replay cache averages")
            for table, title in ((self.cache_table, "Original Run"), (self.replay_table, "Validation Replay")):
                apply_minimum(table, 480, 160)
                self.cache_tabs.addTab(table, title)
                table.selectionModel().currentRowChanged.connect(self._select_treatment)
            from AgMark.gui.widgets.telemetry_details import TelemetryDetails
            self.telemetry_details = TelemetryDetails(self.cache_tabs)
            self.cache_tabs.addTab(self.telemetry_details, "Original Run details")
            self.comparison_panel = QWidget(self.cache_tabs)
            comparison = QVBoxLayout(self.comparison_panel)
            comparison.setContentsMargins(0, 0, 0, 0)
            self.validation_status = QLabel(self.comparison_panel)
            self.validation_status.setWordWrap(True)
            self.validation_status.setAccessibleName("Cache source and replay coverage")
            comparison.addWidget(self.validation_status)
            self.comparison_table = SemanticTableView(CACHE_COMPARISON_COLUMNS,
                accessible_name="Selected treatment original versus replay comparison", parent=self.comparison_panel)
            self.comparison_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            comparison.addWidget(self.comparison_table, 1)
            self.cache_tabs.addTab(self.comparison_panel, "Comparison")
            self.request_panel = QWidget(self.cache_tabs)
            requests = QVBoxLayout(self.request_panel)
            requests.setContentsMargins(0, 0, 0, 0)
            self.request_status = QLabel(self.request_panel)
            self.request_status.setWordWrap(True)
            self.request_status.setAccessibleName("Retained request availability")
            requests.addWidget(self.request_status)
            self.request_details = self._retained_tree("Selected treatment Validation Replay requests", self.request_panel)
            requests.addWidget(self.request_details, 1)
            self.cache_tabs.addTab(self.request_panel, "Request details")
            self.provenance_details = self._retained_tree("Selected treatment retained evidence and provenance", self.cache_tabs)
            self.cache_tabs.addTab(self.provenance_details, "Provenance")
            cache.addWidget(self.cache_tabs, 1)
            self.cache_coverage_note = QLabel("Replay cells: Average [contributing / comparable replays]. "
                "Select a treatment, then use Comparison, Request details or Provenance.", self.cache_panel)
            self.cache_coverage_note.setWordWrap(True)
            cache.addWidget(self.cache_coverage_note)
            self.cache_tabs.currentChanged.connect(self._show_source_note)
            self.results_splitter.addWidget(self.cache_panel)
            self.results_splitter.setStretchFactor(0, 0)
            self.results_splitter.setStretchFactor(1, 1)
            self.results_splitter.setSizes([96, 444])
            self.projectionRequested.connect(self._apply_queued_projection, Qt.ConnectionType.QueuedConnection)
            self._apply_projection(projection)

        @property
        def authority_semantics(self): return "presentation-only"

        @property
        def projection(self): return self._projection

        @property
        def run_id(self): return self._projection.run_id

        def set_available_width(self, width):
            # QSplitter and QTabWidget do not propagate height-for-width from
            # wrapped labels. Include their required height before the shell
            # decides whether this workspace needs vertical scrolling.
            if hasattr(self, "provenance_details"):
                for panel, available in ((self.comparison_panel, width - 4),
                                         (self.request_panel, width - 4),
                                         (self.cache_panel, width)):
                    layout = panel.layout()
                    layout.invalidate()
                    height = max(layout.minimumSize().height(), layout.totalMinimumHeightForWidth(max(1, available)))
                    if panel.minimumHeight() != height:
                        panel.setMinimumHeight(height)
            super().set_available_width(width)

        @staticmethod
        def _retained_tree(accessible_name, parent):
            tree = QTreeWidget(parent)
            tree.setAccessibleName(accessible_name)
            tree.setUniformRowHeights(True)
            tree.setAlternatingRowColors(True)
            tree.setHeaderLabels(("Record / Field", "Value", "Availability", "Provenance"))
            tree.setColumnWidth(0, 280)
            tree.setColumnWidth(1, 180)
            tree.itemExpanded.connect(lambda item: item.materialize() if isinstance(item, _RetainedBranchItem) else None)
            return tree

        def set_projection(self, projection):
            if not isinstance(projection, ResultsProjection):
                raise ValueError("projection must be a ResultsProjection")
            with self._revision_lock:
                self._projection_revision += 1
                revision = self._projection_revision
            if QThread.currentThread() == self.thread():
                self._apply_projection(projection)
            else:
                self.projectionRequested.emit((revision, projection))

        def _apply_queued_projection(self, update):
            revision, projection = update
            with self._revision_lock:
                if revision != self._projection_revision:
                    return
            self._apply_projection(projection)

        def _update_treatment_buttons(self):
            ids = tuple(row.treatment for row in self._projection.rows)
            if ids != self._treatment_button_ids:
                for button in self.treatment_buttons:
                    self.treatment_button_group.removeButton(button)
                    self.treatment_buttons_layout.removeWidget(button)
                    button.hide()
                    button.deleteLater()
                self.treatment_buttons = []
                for index, row in enumerate(self._projection.rows):
                    button = QPushButton(row.treatment, self.treatment_buttons_host)
                    button.setObjectName("resultsTreatmentButton")
                    button.setCheckable(True)
                    button.setMinimumHeight(36)
                    button.setAccessibleName("Select treatment " + row.treatment)
                    button.clicked.connect(lambda _checked=False, index=index: self._select_treatment_button(index))
                    self.treatment_button_group.addButton(button, index)
                    self.treatment_buttons_layout.insertWidget(index, button)
                    self.treatment_buttons.append(button)
                self._treatment_button_ids = ids
            for button, row in zip(self.treatment_buttons, self._projection.rows):
                description = "Status: " + row.status
                if not self._projection.unscored:
                    description += "; Accuracy: " + _score_text(row.score)
                button.setAccessibleDescription(description)

        def _select_treatment_button(self, index):
            if self._updating_projection or not 0 <= index < len(self._projection.rows):
                return
            self._set_selected_treatment(index)

        def _select_treatment(self, current, *_):
            if self._updating_projection:
                return
            index = current.row()
            if not 0 <= index < len(self._projection.rows):
                return
            self._set_selected_treatment(index)

        def _set_selected_treatment(self, index):
            row = self._projection.rows[index] if 0 <= index < len(self._projection.rows) else None
            self._selected_row = row
            self._selected_validation = row.validation if row else None
            if row and index < len(self.treatment_buttons):
                self.treatment_buttons[index].setChecked(True)
            for table in (self.cache_table, self.replay_table):
                selection = table.selectionModel()
                selection.blockSignals(True)
                if row:
                    table.selectRow(index)
                else:
                    table.clearSelection()
                selection.blockSignals(False)
            if row is not self._inspection_row:
                self._show_cache(index)
                self._inspection_row = row
            self.telemetry_details.set_projection(row.telemetry_projection if row else {},
                presentation=self._projection._presentation["telemetry"][index] if row else {})

        def _show_source_note(self, *_):
            self.cache_coverage_note.setVisible(self.cache_tabs.currentWidget() in (self.cache_table, self.replay_table))

        def _show_cache(self, index):
            row = self._selected_row
            self.request_details.clear()
            self.provenance_details.clear()
            inspection = self._projection._presentation["inspection"][index] if row else None
            self.validation_status.setText(inspection["status"] if inspection else
                "Original Run: retained treatment aggregate. Validation unavailable; no retained replay authority.")
            if inspection:
                self.provenance_details.addTopLevelItems([_RetainedBranchItem(label, data, extras)
                    for label, data, extras in inspection["records"]])
                self.request_details.addTopLevelItems([_RetainedBranchItem(label, data, extras)
                    for label, data, extras in inspection["requests"]])
            self.request_status.setText(inspection["request_status"] if inspection else "No retained request records.")
            self.comparison_table.replace(CACHE_COMPARISON_COLUMNS, inspection["comparison"] if inspection else ())

        @staticmethod
        def _replace_table(table, columns, rows):
            changed_columns = table.columns != columns
            horizontal, vertical = table.horizontalScrollBar().value(), table.verticalScrollBar().value()
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            table.replace(columns, rows)
            if changed_columns or not getattr(table, "_results_sized", False):
                metrics = table.fontMetrics()
                for index, column in enumerate(columns):
                    sample = [column.label, *(row.cells[column.key].text for row in rows[:20] if column.key in row.cells)]
                    table.setColumnWidth(index, min(320, max(90, max(metrics.horizontalAdvance(text[:120]) for text in sample) + 24)))
                table._results_sized = True
            table.horizontalScrollBar().setValue(horizontal)
            table.verticalScrollBar().setValue(vertical)

        def _apply_projection(self, projection):
            if self._rendered_projection is projection:
                return
            self._rendered_projection = projection
            self._updating_projection = True
            same_run = self._projection.run_id == projection.run_id
            treatment = self._selected_row.treatment if same_run and self._selected_row else None
            self._projection = projection
            self._selected_row = None
            self.treatment_heading.setText("Execution Treatments" if projection.unscored else "Treatments")
            self._update_treatment_buttons()
            presentation = projection._presentation
            for table, source in ((self.cache_table, "original"), (self.replay_table, "replay")):
                selection = table.selectionModel()
                selection.blockSignals(True)
                self._replace_table(table, CACHE_COLUMNS, presentation[source])
                selection.blockSignals(False)
            index = next((i for i, row in enumerate(projection.rows) if row.treatment == treatment), 0)
            if not same_run:
                self.cache_tabs.setCurrentIndex(0)
                self.treatment_scroll.horizontalScrollBar().setValue(0)
            self._set_selected_treatment(index)
            has_rows = bool(projection.rows)
            self.results_splitter.setVisible(has_rows)
            self.empty_state_label.setVisible(not has_rows)
            self.empty_state_label.setText("" if has_rows else projection.empty_state or "")
            self._updating_projection = False

else:
    class ResultsView:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for ResultsView")


__all__ = ["PYSIDE6_AVAILABLE", "RESULTS_COLUMNS", "CACHE_COLUMNS", "CACHE_COMPARISON_COLUMNS", "CACHE_METRICS",
           "ResultRowProjection", "ResultsProjection", "ResultsView", "STATUS_SEMANTICS_ROLE"]
