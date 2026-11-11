"""Read-only typed telemetry drilldowns supplied by the shared projection layer."""
from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


def telemetry_row_text(row):
    """Format shared display fields without parsing or calculating telemetry."""
    value = row.get("value")
    display = str(value) if value is not None else "Unavailable"
    if value is not None and row.get("unit") not in {None, "", "1"}:
        display += " " + str(row["unit"])
    availability = row.get("availability", "unavailable")
    if availability not in {"available", "complete"} and not (
            value is None and availability == "unavailable"):
        display += " (" + str(availability).replace("_", " ") + ")"
    return (str(row.get("name", row.get("id", "Metric"))), display,
            str(row.get("definition", "Unavailable")), str(row.get("source", "Unavailable")),
            str(row.get("classification", "Unavailable")), str(row.get("coverage_text", "See retained details")))


class RetainedItem(QTreeWidgetItem):
    """Keep exact retained metadata for selection and expandable detail rows."""

    def __init__(self, text, retained):
        super().__init__(text)
        self._retained = retained


class TelemetryDetails(QWidget):
    """Render normalized presentation records without interpreting source payloads."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel(self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Original Run telemetry completeness")
        layout.addWidget(self.status)
        self.tabs = QTabWidget(self)
        self.tabs.setAccessibleName("Original Run telemetry categories")
        self.tabs.setUsesScrollButtons(True)
        layout.addWidget(self.tabs, 1)
        self.trees = {}

    def set_projection(self, supplied: Mapping, *, presentation=None):
        if getattr(self, "_projection", None) is supplied:
            return
        self._projection = supplied
        selected = self.tabs.currentWidget().property("sectionId") if self.tabs.currentWidget() else None
        completeness = supplied.get("overview", {}).get("telemetry_completeness", {})
        value = completeness.get("value", "Unavailable") if isinstance(completeness, Mapping) else completeness
        provisional = supplied.get("provisional", False)
        self.status.setText(("Provisional — evidence is not sealed. " if provisional else "Retained Original Run evidence. ")
                            + "Telemetry: " + str(value or "Unavailable")
                            + ". Response scoring is independent of telemetry quality.")
        sections = supplied.get("sections", ())
        section_ids = {section["id"] for section in sections}
        for key in tuple(self.trees):
            if key not in section_ids:
                tree = self.trees.pop(key)
                self.tabs.removeTab(self.tabs.indexOf(tree))
                tree.deleteLater()
        for position, section in enumerate(sections):
            key = section["id"]
            tree = self.trees.get(key)
            if tree is None:
                tree = QTreeWidget(self.tabs)
                tree.setProperty("sectionId", key)
                tree.setAccessibleName(section["title"] + " telemetry metrics")
                tree.setHeaderLabels(("Metric", "Value", "Definition", "Source", "Classification", "Coverage"))
                tree.setRootIsDecorated(False)
                tree.setAlternatingRowColors(True)
                tree.setUniformRowHeights(True)
                for column, width in enumerate((210, 160, 300, 180, 130, 220)):
                    tree.setColumnWidth(column, width)
                self.trees[key] = tree
                self.tabs.insertTab(position, tree, section["title"])
            elif self.tabs.indexOf(tree) != position:
                self.tabs.removeTab(self.tabs.indexOf(tree))
                self.tabs.insertTab(position, tree, section["title"])
            else:
                self.tabs.setTabText(position, section["title"])
            rows = section.get("rows", ())
            if getattr(tree, "_retained_rows", None) is not rows:
                horizontal, vertical = tree.horizontalScrollBar().value(), tree.verticalScrollBar().value()
                current = tree.currentItem()
                selected_id = current._retained.get("id") if isinstance(current, RetainedItem) else None
                tree.setUpdatesEnabled(False)
                tree.clear()
                prepared = presentation.get(key, ()) if presentation is not None else ()
                items = [RetainedItem(prepared[index] if index < len(prepared) else telemetry_row_text(row), row)
                         for index, row in enumerate(rows)]
                tree.addTopLevelItems(items)
                tree._retained_rows = rows
                for item in items:
                    if selected_id is not None and item._retained.get("id") == selected_id:
                        tree.setCurrentItem(item)
                        break
                tree.horizontalScrollBar().setValue(horizontal)
                tree.verticalScrollBar().setValue(vertical)
                tree.setUpdatesEnabled(True)
            if selected == key:
                self.tabs.setCurrentWidget(tree)
