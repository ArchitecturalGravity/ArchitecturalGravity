"""Content-based tree columns that share spare space without clipping content."""
from PySide6.QtWidgets import QTreeWidget


class ContentSizedTree(QTreeWidget):
    """Keep ResizeToContents semantics, distributing spare width proportionally."""

    def contentWidth(self, column):
        return super().sizeHintForColumn(column)

    def sizeHintForColumn(self, column):
        header = self.header()
        # Header labels (including sort indicators) are content too. Derive
        # proportions from natural widths, never the previously expanded sizes.
        widths = [0 if header.isSectionHidden(i) else
                  max(self.contentWidth(i), header.sectionSizeHint(i), header.minimumSectionSize())
                  for i in range(self.columnCount())]
        total = sum(widths)
        if not total or not 0 <= column < len(widths):
            return super().sizeHintForColumn(column)
        available = max(total, self.viewport().width())
        start = sum(widths[:column])
        # Cumulative rounding consumes every spare pixel without shrinking any
        # column below its content width. A narrow viewport scrolls instead.
        return (start + widths[column]) * available // total - start * available // total

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # ResizeToContents normally reacts to data, not unused viewport space.
        self.header().resizeSections()
