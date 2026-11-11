"""Focused, read-only Scoring workspace table over retained Results data.

Columns use a fixed measurement set, omitting Accuracy for unscored runs.
Values and provenance come from the existing Results projection; this view
never scores or reinterprets provider evidence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from numbers import Real

from AgMark.gui.views.results import ResultsProjection, measurement_text
from AgMark.gui.widgets.tables import (
    PYSIDE6_AVAILABLE,
    SemanticTableView,
    TableCell,
    TableColumn,
    TableRow,
)


SCORING_COLUMNS = (
    TableColumn("treatment", "Treatment"),
    TableColumn("score", "Accuracy", alignment="right"),
    TableColumn("input_tokens", "Input Tokens", alignment="right"),
    TableColumn("uncached_input_tokens", "Uncached Input", alignment="right"),
    TableColumn("reasoning_tokens", "Reasoning Output Tokens", alignment="right"),
    TableColumn("output_tokens", "Output Tokens", alignment="right"),
    TableColumn("total_tokens", "Total Tokens", alignment="right"),
    TableColumn("cache_read_fraction", "Cache Read Fraction", alignment="right"),
    TableColumn("average_inference_ms", "Average Inference Duration", alignment="right"),
    TableColumn("average_ttft_ms", "Average TTFT (Proxy)", alignment="right"),
    TableColumn("average_tbt_ms", "Average TBT (Proxy)", alignment="right"),
    TableColumn("average_direct_ttft_ms", "Average Direct TTFT", alignment="right"),
    TableColumn("average_direct_tbt_ms", "Average Direct TBT", alignment="right"),
    TableColumn("tool_calls", "Tool Calls", alignment="right"),
    TableColumn("distinct_tool_count", "Distinct Tool Calls", alignment="right"),
    TableColumn("failed_tool_calls", "Failed Tool Calls", alignment="right"),
)


def scoring_columns(projection: ResultsProjection) -> tuple[TableColumn, ...]:
    """Use resource-only columns for execution-only Results projections."""
    if not isinstance(projection, ResultsProjection):
        raise ValueError("projection must be a ResultsProjection")
    return (
        tuple(column for column in SCORING_COLUMNS if column.key != "score")
        if projection.unscored else SCORING_COLUMNS
    )


# Higher scores and cache reuse are better; all other measurements favor less.
_MAXIMIZE = frozenset({"score", "cache_read_fraction"})
_RANKABLE_AVAILABILITY = frozenset({"available", "complete", "partial"})
_MEDALS = ("🥇", "🥈", "🥉")


def _finite_number(value: object) -> Decimal | None:
    """Accept only finite retained scalar measurements, never formatted text."""
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        return None
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return numeric if numeric.is_finite() else None


def _scoring_medals(projection: ResultsProjection) -> dict[tuple[int, str], str]:
    """Award medals to the three best distinct values; ties share a medal."""
    measurements = projection._presentation["scoring_measurements"]
    medals: dict[tuple[int, str], str] = {}
    for column in scoring_columns(projection)[1:]:
        candidates: list[tuple[int, Decimal]] = []
        for index, row in enumerate(projection.rows):
            if column.key == "score":
                value = None if projection.unscored else row.score
            else:
                retained = measurements[index].get(column.key, {})
                if retained.get("availability") not in _RANKABLE_AVAILABILITY:
                    continue
                value = retained.get("value")
            numeric = _finite_number(value)
            if numeric is not None:
                candidates.append((index, numeric))

        candidates.sort(key=lambda candidate: candidate[1], reverse=column.key in _MAXIMIZE)
        counts = Counter(value for _, value in candidates)
        previous: Decimal | None = None
        place = 0
        for index, numeric in candidates:
            if numeric != previous:
                place += 1
                previous = numeric
            if place > len(_MEDALS):
                break
            medal = _MEDALS[place - 1]
            medals[(index, column.key)] = f"{medal} (tie)" if counts[numeric] > 1 else medal
    return medals


def scoring_rows(projection: ResultsProjection) -> tuple[TableRow, ...]:
    """Format percentages and rank cells without changing retained authority."""
    if not isinstance(projection, ResultsProjection):
        raise ValueError("projection must be a ResultsProjection")
    unavailable = TableCell("Unavailable")
    columns = scoring_columns(projection)
    medals = _scoring_medals(projection)
    rows = []
    for index, source in enumerate(projection._presentation["rows"]):
        cells = {}
        for column in columns:
            cell = source.cells.get(column.key, unavailable)
            if column.key in _MAXIMIZE:
                measurement = (
                    {"value": None if projection.unscored else projection.rows[index].score}
                    if column.key == "score"
                    else projection._presentation["scoring_measurements"][index].get(column.key, {})
                )
                numeric = _finite_number(measurement.get("value"))
                if numeric is not None:
                    percentage = f"{numeric * 100:.2f}".rstrip("0").rstrip(".") + "%"
                    cell = replace(cell, text=measurement_text(
                        {**measurement, "value": percentage, "unit": "1"}
                    ))
            medal = medals.get((index, column.key))
            cells[column.key] = replace(cell, text=f"{medal} {cell.text}") if medal else cell
        rows.append(TableRow(cells))
    return tuple(rows)

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QLabel, QVBoxLayout

    from AgMark.gui.widgets.responsive import ResponsiveView, apply_minimum

    class ScoringView(ResponsiveView):
        """Treatment measurement comparison, without a second scoring pipeline."""

        def __init__(self, projection: ResultsProjection, *, parent=None):
            if not isinstance(projection, ResultsProjection):
                raise ValueError("projection must be a ResultsProjection")
            super().__init__(parent)
            self.setObjectName("scoringWorkspaceView")
            self.setAccessibleName("Scoring workspace")
            self.setProperty("authoritySemantics", "presentation-only")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            self.empty_state_label = QLabel(self)
            self.empty_state_label.setWordWrap(True)
            self.empty_state_label.setAccessibleName("Scoring availability")
            layout.addWidget(self.empty_state_label)
            self.table = SemanticTableView(
                scoring_columns(projection), accessible_name="Scoring measurements", parent=self
            )
            self.table.setObjectName("scoringMeasurementsTable")
            apply_minimum(self.table, 480, 120)
            layout.addWidget(self.table, 1)
            self._projection = projection
            self.set_projection(projection)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def projection(self) -> ResultsProjection:
            return self._projection

        @property
        def run_id(self) -> str:
            return self._projection.run_id

        def set_projection(self, projection: ResultsProjection) -> None:
            if not isinstance(projection, ResultsProjection):
                raise ValueError("projection must be a ResultsProjection")
            self._projection = projection
            self.table.replace(scoring_columns(projection), scoring_rows(projection))
            has_rows = bool(projection.rows)
            self.empty_state_label.setVisible(not has_rows)
            self.empty_state_label.setText(
                "" if has_rows else projection.empty_state or "No scoring measurements available."
            )

else:
    class ScoringView:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for ScoringView")


__all__ = ["PYSIDE6_AVAILABLE", "SCORING_COLUMNS", "ScoringView", "scoring_columns", "scoring_rows"]
