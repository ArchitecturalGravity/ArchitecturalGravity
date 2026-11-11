"""Read-only Markdown presentation; retained source and export stay untouched."""
from PySide6.QtCore import Qt
from PySide6.QtGui import (QColor, QFont, QTextBlockFormat, QTextCursor,
                          QTextDocument, QTextFormat, QTextLength, QTextOption, QTextTable)
from PySide6.QtWidgets import QTextBrowser
from .report_provenance import readable_provenance


class ReportReader(QTextBrowser):
    """Style Qt's parsed document directly (Markdown ignores HTML CSS rules)."""

    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent)
        self.compact = compact
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDocumentMargin(14)

    def loadResource(self, resource_type, url):
        # Report text is evidence, never authority to load local or remote images.
        return None

    def set_report(self, source):
        # Formatting each block of a visible document otherwise forces repeated
        # whole-document layout. Batch parsing and styling before one layout.
        document = self.document()
        document.setLayoutEnabled(False)
        self.setUpdatesEnabled(False)
        try:
            self._set_report_contents(source)
        finally:
            document.setLayoutEnabled(True)
            self.setUpdatesEnabled(True)

    def _set_report_contents(self, source):
        self.document().setMarkdown(readable_provenance(source), QTextDocument.MarkdownFeature.MarkdownDialectGitHub |
                         QTextDocument.MarkdownFeature.MarkdownNoHTML)
        document = self.document()
        self.sections = []
        self.major_sections = []
        treatment = None
        block = document.begin()
        while block.isValid():
            cursor = QTextCursor(block)
            fmt = block.blockFormat()
            level = fmt.headingLevel()
            in_table = cursor.currentTable() is not None
            if level:
                title = block.text()
                if level <= 3:
                    treatment = title.removesuffix(" measurement provenance") if level == 3 and title.endswith(" measurement provenance") else None
                navigation_title = f"{treatment} / {title}" if treatment and level == 4 else title
                self.sections.append((navigation_title, block.position()))
                if level <= 2:
                    self.major_sections.append((title, block.position()))
                fmt.setTopMargin((8 if self.compact else 18) if block.position() else 0)
                fmt.setBottomMargin(4 if self.compact else 8)
                fmt.setLineHeight(115, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
                cursor.setBlockFormat(fmt)
                # Replace the size on each fragment: merging cannot remove Qt's
                # relative heading-size property. Preserve inline links/emphasis.
                fragments = []
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    if fragment.isValid():
                        fragments.append((fragment.position(), fragment.length(), fragment.charFormat()))
                    iterator += 1
                for position, length, char in fragments:
                    char.clearProperty(QTextFormat.Property.FontSizeAdjustment)
                    char.clearProperty(QTextFormat.Property.FontPointSize)
                    char.setProperty(QTextFormat.Property.FontPixelSize, 18 if level == 1 else 16 if level == 2 else 14)
                    char.setFontWeight(QFont.Weight.DemiBold)
                    cursor.setPosition(position)
                    cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
                    cursor.setCharFormat(char)
            else:
                fmt.setTopMargin(0)
                fmt.setBottomMargin(2 if self.compact else 3 if in_table or block.textList() else 9)
                fmt.setLineHeight(115 if self.compact else 135, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
                cursor.setBlockFormat(fmt)
            if block.textList():
                list_format = block.textList().format()
                list_format.setIndent(max(1, list_format.indent()))
                block.textList().setFormat(list_format)
            block = block.next()
        self._style_tables(document.rootFrame())
        self.moveCursor(QTextCursor.MoveOperation.Start)

    def _style_tables(self, frame):
        for child in frame.childFrames():
            if isinstance(child, QTextTable):
                fmt = child.format()
                fmt.setCellPadding(4 if self.compact else 7)
                fmt.setCellSpacing(0)
                fmt.setBorder(0.5)
                fmt.setBorderBrush(QColor('#d6e0eb'))
                fmt.setHeaderRowCount(1)
                fmt.setTopMargin(4)
                fmt.setBottomMargin(6 if self.compact else 12)
                fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
                child.setFormat(fmt)
                for row in range(child.rows()):
                    for col in range(child.columns()):
                        cell = child.cellAt(row, col)
                        cell_format = cell.format()
                        cell_format.setBackground(QColor('#eaf1fa' if row == 0 else '#f6f9fc' if row % 2 == 0 else '#ffffff'))
                        cell.setFormat(cell_format)
            self._style_tables(child)

    def go_to_section(self, position):
        cursor = QTextCursor(self.document())
        cursor.setPosition(position)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        # Align the section with the reader's top rather than its bottom.
        rect = self.cursorRect()
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + rect.top())
        self.setFocus(Qt.FocusReason.OtherFocusReason)
