"""Concrete PySide6 conformance tests for reusable semantic tables."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.widgets.tables import (
    ACTION_AVAILABLE_ROLE,
    ACTION_UNAVAILABLE_REASON_ROLE,
    PYSIDE6_AVAILABLE,
    STATUS_SEMANTICS_ROLE,
    SemanticTableView,
    TableCell,
    TableColumn,
    TableRow,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class SemanticTableWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_display_and_accessible_description_roles(self):
        cells = (
            TableCell("Visible text"),
            TableCell("Warning", status_semantics="warning"),
            TableCell("Disabled action", action_available=False, action_unavailable_reason="Not available"),
        )
        table = SemanticTableView((TableColumn("value", "Value"),), tuple({"value": cell} for cell in cells))
        self.addCleanup(table.deleteLater)
        for row, cell in enumerate(cells):
            index = table.table_model.index(row, 0)
            self.assertEqual(cell.text, table.table_model.data(index))
        self.assertEqual("Not available", table.table_model.data(
            table.table_model.index(2, 0), Qt.ItemDataRole.AccessibleDescriptionRole))


    def test_model_preserves_exact_cells_and_only_explicit_semantic_roles(self) -> None:
        view = SemanticTableView(
            (
                TableColumn("status", "Status"),
                TableColumn("score", "Score", alignment="right"),
                TableColumn("action", "Action"),
            ),
            (
                {
                    "status": TableCell("accepted", status_semantics="warning"),
                    "score": "0",
                    "action": TableCell(
                        "Open",
                        action_available=False,
                        action_unavailable_reason="Caller disabled this action",
                    ),
                },
            ),
            accessible_name="Benchmark rows",
        )
        self.addCleanup(view.deleteLater)
        model = view.table_model

        status = model.index(0, 0)
        score = model.index(0, 1)
        action = model.index(0, 2)

        self.assertEqual(model.data(status, int(Qt.ItemDataRole.DisplayRole)), "accepted")
        self.assertEqual(model.data(status, STATUS_SEMANTICS_ROLE), "warning")
        self.assertEqual(model.data(score, int(Qt.ItemDataRole.DisplayRole)), "0")
        self.assertEqual(model.data(action, ACTION_AVAILABLE_ROLE), False)
        self.assertEqual(
            model.data(action, ACTION_UNAVAILABLE_REASON_ROLE),
            "Caller disabled this action",
        )
        self.assertEqual(model.data(action, int(Qt.ItemDataRole.AccessibleDescriptionRole)),
                         "Caller disabled this action")
        self.assertFalse(model.flags(status) & Qt.ItemFlag.ItemIsEditable)
        self.assertEqual(view.accessibleName(), "Benchmark rows")
        self.assertEqual(view.authority_semantics, "presentation-only")

    def test_stable_rows_emit_only_changed_cells_without_model_reset(self) -> None:
        view = SemanticTableView((TableColumn("identity", "Identity"), TableColumn("events", "Events")),
            ({"identity": "stdout", "events": "1"}, {"identity": "stderr", "events": "0"}))
        self.addCleanup(view.deleteLater)
        model = view.table_model
        changed, reset = [], []
        model.dataChanged.connect(lambda first, last, roles: changed.append((first.row(), first.column(), last.row(), last.column())))
        model.modelReset.connect(lambda: reset.append(True))
        rows = (TableRow({"identity": "stdout", "events": TableCell("2", status_semantics="info")}),
                TableRow({"identity": "stderr", "events": "0"}))
        model.update_rows(rows)
        self.assertEqual([(0, 1, 0, 1)], changed)
        self.assertEqual([], reset)
        self.assertEqual("2", model.data(model.index(0, 1)))
        self.assertEqual("info", model.data(model.index(0, 1), int(Qt.ItemDataRole.AccessibleDescriptionRole)))
        model.update_rows(rows)
        self.assertEqual(1, len(changed))
        model.update_rows(rows[:1])
        self.assertEqual([True], reset)
        self.assertEqual(1, model.rowCount())

    def test_visible_labels_and_values_do_not_infer_benchmark_authority(self) -> None:
        view = SemanticTableView(
            (
                TableColumn("state", "Accepted"),
                TableColumn("value", "Verification"),
            ),
            ({"state": "blocked", "value": "verified"},),
        )
        self.addCleanup(view.deleteLater)
        model = view.table_model

        state = model.index(0, 0)
        value = model.index(0, 1)
        self.assertEqual(model.data(state, STATUS_SEMANTICS_ROLE), None)
        self.assertEqual(model.data(state, ACTION_AVAILABLE_ROLE), None)
        self.assertEqual(model.data(value, STATUS_SEMANTICS_ROLE), None)
        self.assertEqual(view.authority_semantics, "presentation-only")

        view.set_rows(({"state": "accepted", "value": "claim-ready"},))
        self.assertEqual(
            model.data(model.index(0, 0), int(Qt.ItemDataRole.DisplayRole)),
            "accepted",
        )
        self.assertEqual(model.data(model.index(0, 0), STATUS_SEMANTICS_ROLE), None)

    def test_invalid_table_contract_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            SemanticTableView((), ())

        with self.assertRaisesRegex(ValueError, "unique"):
            SemanticTableView(
                (
                    TableColumn("value", "One"),
                    TableColumn("value", "Two"),
                ),
                (),
            )

        with self.assertRaisesRegex(ValueError, "unknown column keys"):
            SemanticTableView(
                (TableColumn("value", "Value"),),
                ({"other": "unexpected"},),
            )

        with self.assertRaisesRegex(ValueError, "requires action_available=False"):
            TableCell(
                "Open",
                action_available=True,
                action_unavailable_reason="No permission",
            )


if __name__ == "__main__":
    unittest.main()
