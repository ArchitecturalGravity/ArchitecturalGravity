"""Typed Finding List ordering and batch-safe Qt presentation updates."""
from contextlib import contextmanager

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QTreeWidgetItem

from ..shared.diagnostics import SEVERITY_ORDER


def finding_sort_key(finding, column, occurrence_key=()):
    """Separate a column's primary value from deterministic source-order ties."""
    start = finding.source_range.start
    primary = (
        SEVERITY_ORDER[finding.severity], finding.rule_id.casefold(),
        finding.message.casefold(), (start.line, start.column),
        (start.column, start.line),
    )[column]
    span = finding.source_range.span
    tie = (span.start, span.end, finding.rule_id, finding.message,
           finding.severity, occurrence_key)
    return primary, tie


class FindingItem(QTreeWidgetItem):
    """Sort actual diagnostic values, never their formatted display strings."""

    def __init__(self, key):
        super().__init__()
        self.finding_key = key

    def __lt__(self, other):
        tree = self.treeWidget()
        finding = self.data(0, Qt.ItemDataRole.UserRole)
        other_finding = other.data(0, Qt.ItemDataRole.UserRole)
        if tree is None or finding is None or other_finding is None:
            return super().__lt__(other)
        primary, tie = finding_sort_key(finding, tree.sortColumn(), self.finding_key)
        other_primary, other_tie = finding_sort_key(
            other_finding, tree.sortColumn(), getattr(other, 'finding_key', ()))
        if primary != other_primary:
            return primary < other_primary
        # Qt reverses the comparator for descending order. Keep equal-primary
        # findings in source order, including the initial severity-descending view.
        if tree.header().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder:
            return tie > other_tie
        return tie < other_tie


@contextmanager
def finding_update(tree):
    """Re-sort once after a batch and retain surviving selection and scroll."""
    blocker = QSignalBlocker(tree)
    sorting = tree.isSortingEnabled()
    current = tree.currentItem()
    selected = tree.selectedItems()
    scroll = tree.verticalScrollBar().value()
    tree.setSortingEnabled(False)
    try:
        yield sorting
    finally:
        tree.setSortingEnabled(sorting)
        if current is not None and current.treeWidget() is tree:
            tree.setCurrentItem(current)
        for item in selected:
            if item.treeWidget() is tree:
                item.setSelected(True)
        tree.verticalScrollBar().setValue(scroll)
        del blocker
