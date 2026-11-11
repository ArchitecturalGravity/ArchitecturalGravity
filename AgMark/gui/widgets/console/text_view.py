"""Read-only console text view and line-number presentation."""

from __future__ import annotations

from .state import (
    BottomConsoleState,
    CONSOLE_TABS,
    LAST_EXPANDED_HEIGHT_KEY,
    RAW_RESPONSE_UNAVAILABLE,
    _require_generation_id,
    _require_height,
    _require_tab,
)

# Optional concrete Python desktop surface. Keeping these imports below the
# toolkit-independent state boundary lets centralized non-GUI tests import this
# module even when PySide6 is not installed.
from AgMark.gui.design_system.buttons import resolved_button
from AgMark.gui.design_system.console import resolved_console_presentation
from AgMark.gui.design_system.metrics import DEFAULT_LAYOUT_METRICS, LayoutMetrics
from AgMark.gui.design_system.surfaces import resolved_surface
from AgMark.gui.design_system.tabs import resolved_tab
from AgMark.gui.design_system.theme import (
    DEFAULT_LIGHT_THEME,
    Theme,
    semantic_icon,
)
from AgMark.gui.design_system.typography import (
    DEFAULT_TYPOGRAPHY,
    Typography,
)

try:
    from PySide6.QtCore import QMimeData, QRect, QSize, QSettings, Qt, Signal
    from PySide6.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QPainter,
        QSyntaxHighlighter,
        QTextCharFormat,
        QTextCursor,
    )
    from PySide6.QtWidgets import (
        QAbstractScrollArea,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QStackedWidget,
        QTabBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True

if PYSIDE6_AVAILABLE:
    from .syntax import _ConsoleSyntaxHighlighter


    class _LineNumberArea(QWidget):
        def __init__(self, editor: "ConsoleTextView") -> None:
            super().__init__(editor)
            self._editor = editor

        def sizeHint(self) -> QSize:
            return QSize(self._editor.line_number_area_width(), 0)

        def paintEvent(self, event) -> None:
            self._editor.line_number_area_paint_event(event)


    class ConsoleTextView(QPlainTextEdit):
        """Read-only, selectable, line-numbered console inspection surface."""

        def __init__(
            self,
            *,
            tab: str = "Live View",
            theme: Theme = DEFAULT_LIGHT_THEME,
            typography: Typography = DEFAULT_TYPOGRAPHY,
            metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._tab = _require_tab(tab)
            self._source_text = ""
            self._display_text = ""
            self._presentation = resolved_console_presentation(
                theme=theme,
                typography=typography,
            )
            self._line_number_area = _LineNumberArea(self)
            self.blockCountChanged.connect(self._update_line_number_area_width)
            self.updateRequest.connect(self._update_line_number_area)
            self._update_line_number_area_width(0)

            self.setReadOnly(True)
            self.setUndoRedoEnabled(False)
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            self.setSizeAdjustPolicy(
                QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
            )
            self.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
            fixed_font.setPixelSize(self._presentation.font_size_px)
            fixed_font.setWeight(QFont.Weight(self._presentation.font_weight))
            self.setFont(fixed_font)
            self.setProperty("arcgravSemanticComponent", "console-text-view")
            scrollbar_extent = 10
            scrollbar_minimum = 24
            scrollbar_radius = metrics.metric("space-xs")
            self.setStyleSheet(
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] {'
                f"background-color: {self._presentation.background};"
                f"color: {self._presentation.text};"
                "border: 0px;"
                f"selection-background-color: {theme.color('accent-primary')};"
                "}"
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar:vertical {"
                f"background: {self._presentation.background};"
                f"width: {scrollbar_extent}px;"
                "margin: 0px;"
                "}"
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar::handle:vertical {"
                f"background: {self._presentation.muted};"
                f"min-height: {scrollbar_minimum}px;"
                f"border-radius: {scrollbar_radius}px;"
                "}"
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar::handle:vertical:hover {"
                f"background: {self._presentation.info};"
                "}"
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar:horizontal {"
                f"background: {self._presentation.background};"
                f"height: {scrollbar_extent}px;"
                "margin: 0px;"
                "}"
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar::handle:horizontal {"
                f"background: {self._presentation.muted};"
                f"min-width: {scrollbar_minimum}px;"
                f"border-radius: {scrollbar_radius}px;"
                "}"
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar::handle:horizontal:hover {"
                f"background: {self._presentation.info};"
                "}"
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar::add-line, "
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar::sub-line {"
                "width: 0px;"
                "height: 0px;"
                "background: transparent;"
                "}"
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar::add-page, "
                'QPlainTextEdit[arcgravSemanticComponent="console-text-view"] '
                "QScrollBar::sub-page {"
                f"background: {self._presentation.background};"
                "}"
            )
            self.setAccessibleName("Console text")
            self._highlighter = _ConsoleSyntaxHighlighter(
                self.document(),
                tab=self._tab,
                presentation=self._presentation,
            )

        @property
        def authority_semantics(self) -> str:
            return self._presentation.authority_semantics

        def set_source_text(self, text: str, *, follow_output: bool = False) -> None:
            if not isinstance(text, str):
                raise TypeError("console text must be a string")
            if self._source_text == text:
                return
            # Qt renders CR/CRLF as paragraph boundaries. Keep source separately
            # so copying never rewrites prompt/response whitespace or line endings.
            display = text.replace("\r\n", "\n").replace("\r", "\n")
            old = self._display_text
            vertical = self.verticalScrollBar()
            horizontal = self.horizontalScrollBar()
            previous_scroll = vertical.value()
            previous_horizontal = horizontal.value()
            selection = self.textCursor()
            anchor, position = selection.anchor(), selection.position()
            at_end = previous_scroll >= vertical.maximum() - 1
            should_follow = follow_output and at_end and not selection.hasSelection()

            if display.startswith(old):
                # Streaming normally only extends the final Output. Inserting the
                # suffix avoids resetting/re-highlighting the complete document.
                cursor = QTextCursor(self.document())
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertText(display[len(old):])
            else:
                # A final snapshot may replace a partial response or update an
                # earlier concurrent invocation. Change only the differing span.
                prefix = 0
                limit = min(len(old), len(display))
                while prefix < limit and old[prefix] == display[prefix]:
                    prefix += 1
                suffix = 0
                while suffix < limit - prefix and old[-suffix - 1] == display[-suffix - 1]:
                    suffix += 1
                old_end = len(old) - suffix
                new_end = len(display) - suffix
                cursor = QTextCursor(self.document())
                cursor.setPosition(len(old[:prefix].encode("utf-16-le")) // 2)
                cursor.setPosition(
                    len(old[:old_end].encode("utf-16-le")) // 2,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.insertText(display[prefix:new_end])
            self._source_text = text
            self._display_text = display
            # Restore selection and inspection position instead of stealing the
            # cursor on each chunk. Autoscroll resumes when the user reaches end.
            last = self.document().characterCount() - 1
            selection.setPosition(min(anchor, last))
            selection.setPosition(min(position, last), QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(selection)
            if should_follow:
                vertical.setValue(vertical.maximum())
            else:
                vertical.setValue(previous_scroll)
            horizontal.setValue(previous_horizontal)

        def createMimeDataFromSelection(self) -> QMimeData:
            selection = self.textCursor()
            start, end = selection.selectionStart(), selection.selectionEnd()
            source = self._source_text
            # Map Qt's UTF-16 cursor offsets to original source offsets. This is
            # performed only on copy, not on the streaming render path.
            offsets: dict[int, int] = {0: 0}
            source_index = qt_index = 0
            while source_index < len(source) and qt_index <= end:
                char = source[source_index]
                source_index += 1
                if char == "\r" and source_index < len(source) and source[source_index] == "\n":
                    source_index += 1
                qt_index += 2 if ord(char) > 0xFFFF else 1
                if qt_index == start or qt_index == end:
                    offsets[qt_index] = source_index
            # Keep Qt's native MIME ownership (creating a Python-owned QMimeData
            # here can crash the offscreen clipboard during application teardown).
            mime = super().createMimeDataFromSelection()
            mime.text()  # Materialize Qt's lazy selection fragment first.
            mime.setText(source[offsets.get(start, 0):offsets.get(end, len(source))])
            return mime

        def line_number_area_width(self) -> int:
            digits = max(1, len(str(max(1, self.blockCount()))))
            return 12 + self.fontMetrics().horizontalAdvance("9") * digits

        def _update_line_number_area_width(self, _block_count: int) -> None:
            self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

        def _update_line_number_area(self, rect: QRect, dy: int) -> None:
            if dy:
                self._line_number_area.scroll(0, dy)
            else:
                self._line_number_area.update(
                    0,
                    rect.y(),
                    self._line_number_area.width(),
                    rect.height(),
                )
            if rect.contains(self.viewport().rect()):
                self._update_line_number_area_width(0)

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            contents = self.contentsRect()
            self._line_number_area.setGeometry(
                QRect(
                    contents.left(),
                    contents.top(),
                    self.line_number_area_width(),
                    contents.height(),
                )
            )

        def line_number_area_paint_event(self, event) -> None:
            painter = QPainter(self._line_number_area)
            painter.fillRect(event.rect(), QColor(self._presentation.background))
            painter.setPen(QColor(self._presentation.muted))

            block = self.firstVisibleBlock()
            block_number = block.blockNumber()
            top = int(
                self.blockBoundingGeometry(block)
                .translated(self.contentOffset())
                .top()
            )
            bottom = top + int(self.blockBoundingRect(block).height())

            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    painter.drawText(
                        0,
                        top,
                        self._line_number_area.width() - 6,
                        self.fontMetrics().height(),
                        int(Qt.AlignmentFlag.AlignRight),
                        str(block_number + 1),
                    )
                block = block.next()
                top = bottom
                bottom = top + int(self.blockBoundingRect(block).height())
                block_number += 1

else:

    class ConsoleTextView:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for ConsoleTextView")
