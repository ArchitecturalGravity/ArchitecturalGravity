"""Reusable model/view table surfaces for the ArcGrav desktop GUI.

The table surfaces preserve caller-supplied columns, rows, semantic status state,
and action availability. They are presentation-only: no column label, cell text,
selection, color, or availability flag is interpreted as benchmark, lifecycle,
evidence, scoring, report, reconstruction, or verification authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from AgMark.gui.design_system.tables import (
    DEFAULT_TABLE_STYLES,
    ResolvedTableStyle,
    TableRegistry,
)
from AgMark.gui.design_system.theme import DEFAULT_LIGHT_THEME, Theme
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    TextStyle,
    Typography,
)


STATUS_SEMANTICS_ROLE = 0x0101
ACTION_AVAILABLE_ROLE = 0x0102
ACTION_UNAVAILABLE_REASON_ROLE = 0x0103


def _require_visible_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")
    return value


def _optional_visible_text(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_visible_text(value, name=name)


@dataclass(frozen=True, slots=True)
class TableColumn:
    """Caller-owned table-column identity, label, and presentation alignment."""

    key: str
    label: str
    alignment: str = "left"

    def __post_init__(self) -> None:
        _require_visible_text(self.key, name="column key")
        _require_visible_text(self.label, name="column label")
        if self.alignment not in {"left", "center", "right"}:
            raise ValueError("column alignment must be 'left', 'center', or 'right'")


@dataclass(frozen=True, slots=True)
class TableCell:
    """Exact caller-supplied cell text plus optional semantic presentation state."""

    text: str
    status_semantics: str | None = None
    action_available: bool | None = None
    action_unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("table cell text must be a string")
        _optional_visible_text(
            self.status_semantics,
            name="status_semantics",
        )
        if self.action_available is not None and not isinstance(
            self.action_available, bool
        ):
            raise ValueError("action_available must be a boolean or None")
        reason = _optional_visible_text(
            self.action_unavailable_reason,
            name="action_unavailable_reason",
        )
        if reason is not None and self.action_available is not False:
            raise ValueError(
                "action_unavailable_reason requires action_available=False"
            )


@dataclass(frozen=True, slots=True)
class TableRow:
    """Immutable caller-supplied row keyed by explicit column identity."""

    cells: Mapping[str, TableCell | str]

    def __post_init__(self) -> None:
        if not isinstance(self.cells, Mapping):
            raise ValueError("row cells must be a mapping")

        normalized: dict[str, TableCell] = {}
        for key, value in self.cells.items():
            _require_visible_text(key, name="row cell key")
            if isinstance(value, TableCell):
                cell = value
            elif isinstance(value, str):
                cell = TableCell(value)
            else:
                raise ValueError("row cell values must be strings or TableCell")
            normalized[key] = cell

        object.__setattr__(self, "cells", MappingProxyType(normalized))


def _normalize_columns(columns: Sequence[TableColumn]) -> tuple[TableColumn, ...]:
    if isinstance(columns, (str, bytes)):
        raise ValueError("columns must be a sequence of TableColumn values")
    normalized = tuple(columns)
    if not normalized:
        raise ValueError("table requires at least one column")
    if not all(isinstance(column, TableColumn) for column in normalized):
        raise ValueError("columns must contain only TableColumn values")
    keys = [column.key for column in normalized]
    if len(set(keys)) != len(keys):
        raise ValueError("table column keys must be unique")
    return normalized


def _normalize_rows(
    rows: Sequence[TableRow | Mapping[str, TableCell | str]],
    *,
    columns: Sequence[TableColumn],
) -> tuple[TableRow, ...]:
    if isinstance(rows, (str, bytes)):
        raise ValueError("rows must be a sequence of mappings or TableRow values")

    column_keys = {column.key for column in columns}
    normalized: list[TableRow] = []
    for supplied in rows:
        row = supplied if isinstance(supplied, TableRow) else TableRow(supplied)
        unknown = set(row.cells).difference(column_keys)
        if unknown:
            joined = ", ".join(sorted(unknown))
            raise ValueError(f"row contains unknown column keys: {joined}")
        normalized.append(row)
    return tuple(normalized)


try:
    from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
    from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase
    from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:

    def _font(style: TextStyle) -> QFont:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPixelSize(style.size_px)
        font.setWeight(QFont.Weight(style.weight))
        return font


    def _alignment(value: str) -> Qt.AlignmentFlag:
        horizontal = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }[value]
        return horizontal | Qt.AlignmentFlag.AlignVCenter


    class SemanticTableModel(QAbstractTableModel):
        """Read-only model that exposes only explicit caller-supplied semantics."""

        def __init__(
            self,
            columns: Sequence[TableColumn],
            rows: Sequence[TableRow | Mapping[str, TableCell | str]] = (),
            *,
            presentation: ResolvedTableStyle,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._presentation = presentation
            self._columns = _normalize_columns(columns)
            self._rows = _normalize_rows(rows, columns=self._columns)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def columns(self) -> tuple[TableColumn, ...]:
            return self._columns

        @property
        def rows(self) -> tuple[TableRow, ...]:
            return self._rows

        def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
            return 0 if parent.isValid() else len(self._rows)

        def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
            return 0 if parent.isValid() else len(self._columns)

        def _cell(self, index: QModelIndex) -> TableCell:
            column = self._columns[index.column()]
            return self._rows[index.row()].cells.get(column.key, TableCell(""))

        def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
            if not index.isValid():
                return None

            cell = self._cell(index)
            column = self._columns[index.column()]

            if role == int(Qt.ItemDataRole.DisplayRole):
                return cell.text
            if role == int(Qt.ItemDataRole.TextAlignmentRole):
                return int(_alignment(column.alignment))
            if role == STATUS_SEMANTICS_ROLE:
                return cell.status_semantics
            if role == ACTION_AVAILABLE_ROLE:
                return cell.action_available
            if role == ACTION_UNAVAILABLE_REASON_ROLE:
                return cell.action_unavailable_reason
            if role == int(Qt.ItemDataRole.AccessibleTextRole):
                return cell.text
            if role == int(Qt.ItemDataRole.AccessibleDescriptionRole):
                if cell.action_available is False:
                    return cell.action_unavailable_reason or "Unavailable action"
                return cell.status_semantics or ""
            if role == int(Qt.ItemDataRole.ForegroundRole) and cell.action_available is False:
                return QBrush(QColor(self._presentation.unavailable_action_text))
            if role == int(Qt.ItemDataRole.FontRole) and cell.action_available is False:
                font = _font(self._presentation.body_typography)
                font.setItalic(True)
                return font
            return None

        def headerData(
            self,
            section: int,
            orientation: Qt.Orientation,
            role: int = int(Qt.ItemDataRole.DisplayRole),
        ):
            if orientation != Qt.Orientation.Horizontal:
                return None
            if section < 0 or section >= len(self._columns):
                return None

            column = self._columns[section]
            if role == int(Qt.ItemDataRole.DisplayRole):
                return column.label
            if role == int(Qt.ItemDataRole.TextAlignmentRole):
                return int(_alignment(column.alignment))
            if role == int(Qt.ItemDataRole.AccessibleTextRole):
                return column.label
            return None

        def flags(self, index: QModelIndex) -> Qt.ItemFlag:
            if not index.isValid():
                return Qt.ItemFlag.NoItemFlags
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

        def set_rows(
            self,
            rows: Sequence[TableRow | Mapping[str, TableCell | str]],
        ) -> None:
            """Replace caller-owned row projection without deriving table semantics."""

            normalized = _normalize_rows(rows, columns=self._columns)
            self.beginResetModel()
            self._rows = normalized
            self.endResetModel()

        def update_rows(
            self,
            rows: Sequence[TableRow | Mapping[str, TableCell | str]],
        ) -> None:
            """Update stable caller-owned row identities without resetting views.

            The caller owns row ordering/identity. Use set_rows when identities
            change; a row-count change falls back to that structural reset.
            """
            normalized = _normalize_rows(rows, columns=self._columns)
            if len(normalized) != len(self._rows):
                self.set_rows(normalized)
                return
            previous = self._rows
            self._rows = normalized
            for row_index, (before, after) in enumerate(zip(previous, normalized)):
                if before == after:
                    continue
                changed = [index for index, column in enumerate(self._columns)
                           if before.cells.get(column.key) != after.cells.get(column.key)]
                if changed:
                    self.dataChanged.emit(self.index(row_index, min(changed)),
                                          self.index(row_index, max(changed)), [])

        def replace(
            self,
            columns: Sequence[TableColumn],
            rows: Sequence[TableRow | Mapping[str, TableCell | str]],
        ) -> None:
            """Replace the complete caller-owned table projection atomically."""

            normalized_columns = _normalize_columns(columns)
            normalized_rows = _normalize_rows(rows, columns=normalized_columns)
            self.beginResetModel()
            self._columns = normalized_columns
            self._rows = normalized_rows
            self.endResetModel()


    class SemanticTableView(QTableView):
        """Dense reusable table view over explicit caller-supplied projection data."""

        def __init__(
            self,
            columns: Sequence[TableColumn],
            rows: Sequence[TableRow | Mapping[str, TableCell | str]] = (),
            *,
            role: str = "default",
            accessible_name: str = "Data table",
            registry: TableRegistry = DEFAULT_TABLE_STYLES,
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            parent: QWidget | None = None,
        ) -> None:
            accessible_name = _require_visible_text(
                accessible_name,
                name="accessible_name",
            )
            presentation = registry.resolve(
                role,
                theme=theme,
                typography=typography,
            )
            super().__init__(parent)

            self._role = role
            self._presentation = presentation
            self._table_model = SemanticTableModel(
                columns,
                rows,
                presentation=presentation,
                parent=self,
            )

            self.setObjectName("semanticDataTable")
            self.setProperty("arcgravSemanticComponent", "data-table")
            self.setAccessibleName(accessible_name)
            self.setModel(self._table_model)
            self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setMouseTracking(True)
            self.setWordWrap(False)
            self.setSortingEnabled(False)
            self.setShowGrid(True)
            self.verticalHeader().setVisible(False)
            self.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents
            )
            self.horizontalHeader().setStretchLastSection(False)
            self.setFont(_font(presentation.body_typography))
            self.horizontalHeader().setFont(_font(presentation.header_typography))
            self.setStyleSheet(
                'QTableView[arcgravSemanticComponent="data-table"] {'
                f"background-color: {presentation.body_background};"
                f"color: {presentation.body_text};"
                f"border: 1px solid {presentation.body_border};"
                f"gridline-color: {presentation.body_border};"
                f"selection-background-color: {presentation.selected_background};"
                f"selection-color: {presentation.body_text};"
                "}"
                'QTableView[arcgravSemanticComponent="data-table"]::item {'
                "padding: 4px 8px;"
                "}"
                'QTableView[arcgravSemanticComponent="data-table"]::item:hover:!selected {'
                f"background-color: {presentation.selected_background};"
                "}"
                'QTableView[arcgravSemanticComponent="data-table"]::item:selected {'
                f"border-bottom: 1px solid {presentation.header_border};"
                "}"
                'QTableView[arcgravSemanticComponent="data-table"] QHeaderView::section {'
                f"background-color: {presentation.header_background};"
                f"color: {presentation.header_text};"
                f"border: 0;"
                f"border-right: 1px solid {presentation.header_border};"
                f"border-bottom: 1px solid {presentation.header_border};"
                "padding: 5px 8px;"
                "}"
            )

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def role(self) -> str:
            return self._role

        @property
        def presentation(self) -> ResolvedTableStyle:
            return self._presentation

        @property
        def table_model(self) -> SemanticTableModel:
            return self._table_model

        @property
        def columns(self) -> tuple[TableColumn, ...]:
            return self._table_model.columns

        @property
        def rows(self) -> tuple[TableRow, ...]:
            return self._table_model.rows

        def set_rows(
            self,
            rows: Sequence[TableRow | Mapping[str, TableCell | str]],
        ) -> None:
            self._table_model.set_rows(rows)
            self.resizeColumnsToContents()

        def replace(
            self,
            columns: Sequence[TableColumn],
            rows: Sequence[TableRow | Mapping[str, TableCell | str]],
        ) -> None:
            self._table_model.replace(columns, rows)
            self.resizeColumnsToContents()


else:

    class SemanticTableModel:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for SemanticTableModel")


    class SemanticTableView:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for SemanticTableView")


__all__ = [
    "ACTION_AVAILABLE_ROLE",
    "ACTION_UNAVAILABLE_REASON_ROLE",
    "PYSIDE6_AVAILABLE",
    "STATUS_SEMANTICS_ROLE",
    "SemanticTableModel",
    "SemanticTableView",
    "TableCell",
    "TableColumn",
    "TableRow",
]
