"""Launchable local editor. Run: python -m AgStudio.gui --arcgrav-version LABEL.

Qt owns editing and display only. All structural and diagnostic data comes
from one disposable ParsedDocument built by LanguageCore for each source state.
"""

from __future__ import annotations

import argparse
import math
import time
from bisect import bisect_right
from pathlib import Path
import sys

from PySide6.QtCore import QEvent, QMimeData, QTimer, QPoint, QRect, QSize, Qt, QSignalBlocker, QSettings, Signal
from PySide6.QtGui import QInputMethodEvent, QShortcut, QActionGroup, QColor, QFont, QIcon, QPainter, QPolygon, QPalette, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QHeaderView,
    QMenu, QMessageBox, QPlainTextEdit, QTextEdit, QSplitter, QStackedWidget, QTabBar, QSizePolicy, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QToolButton, QStyle, QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem, QToolTip,
)

from ..shared import LanguageCore
from ..shared.document import ParsedDocument
from ..shared.diagnostics import DiagnosticResult, Finding
from ..shared.recognition import SourceSpan
from ..shared.lint import analyze
from .image_export import ExportDialog, export_path, render_document, write_image
from .spelling_suggestions import SpellingSuggestionController, WordTarget
from .application_icon import application_icon, set_windows_app_id
from .analysis import AnalysisController
from .feature_analysis import FeatureController, retire_snapshot
from .syntax_highlighter import _CoreHighlighter
from ..shared.highlight_projection import derive_highlighting
from ..shared.panel_projections import derive_outline, derive_findings
from ..shared.analysis_snapshot import freeze_analysis
from .panel_rendering import apply_outline, apply_findings
from .panel_headers import panel_heading_layout, add_heading_control
from .column_sizing import ContentSizedTree
from .finding_controls import FindingExpansionButton, style_finding_header
from .graph_analysis import GraphController
from .inference_heat import MODE_LABELS, MODE_HELP, MODE_CODES, normalize_graph_mode
from .document_map import DocumentMap, SourcePositionIndex
from .pending_spinner import PendingSpinner
from .user_state import UserState
from .session_state import SessionStore
from .spelling_vocabulary import SpellingVocabularyStore
from .color_schemes import SchemeStore, default_scheme, validate_scheme, SYNTAX_ROLES


APP_VERSION = "1.0.0-beta"
WINDOW_TITLE = f"Architectural Gravity Studio - Ver. {APP_VERSION}"

ARC_FILTER = "ArcGrav (*.arc)"
TEXT_FILTER = "Text files (*.txt)"
SAVE_FILTERS = ARC_FILTER + ";;" + TEXT_FILTER
OPEN_FILTERS = "ArcGrav source (*.arc *.txt);;" + SAVE_FILTERS
FINDING_ICONS = {
    "critical": Path(__file__).with_name("icons") / "critical.svg",
    "error": QStyle.StandardPixmap.SP_MessageBoxCritical,
    "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,
    "information": QStyle.StandardPixmap.SP_MessageBoxInformation,
}


def _finding_icon(style: QStyle, severity: str) -> QIcon:
    """Share severity artwork between counts and rows, including HiDPI SVGs."""
    icon = FINDING_ICONS[severity]
    return QIcon(str(icon)) if isinstance(icon, Path) else style.standardIcon(icon)


def _save_path(path: Path, selected_filter: str = ARC_FILTER) -> Path:
    if not path.suffix:
        path = path.with_suffix(".txt" if selected_filter == TEXT_FILTER else ".arc")
    if path.suffix.lower() not in {".arc", ".txt"}:
        raise ValueError("save destination must be an .arc or .txt file")
    return path


def _line_ending(source: str) -> str:
    crlf = source.count("\r\n")
    lf = source.count("\n") - crlf
    cr = source.count("\r") - crlf
    if not (crlf or lf or cr):
        return "\n"
    return max(((crlf, "\r\n"), (lf, "\n"), (cr, "\r")), key=lambda pair: pair[0])[1]


def _ending_label(source: str) -> str:
    kinds = [name for text, name in (("\r\n", "CRLF"), ("\n", "LF"), ("\r", "CR"))
             if (source.count(text) if text == "\r\n" else
                 source.count(text) - source.count("\r\n"))]
    return "+".join(kinds) if kinds else "none"


def _display_offset(source: str, offset: int) -> int:
    """Map canonical code-point offset into Qt's normalized UTF-16 view."""
    normalized = source[:offset].replace("\r\n", "\n").replace("\r", "\n")
    return len(normalized.encode("utf-16-le")) // 2


class _OutlineTree(ContentSizedTree):
    def contentWidth(self, column):
        if column != 0:
            return super().contentWidth(column)
        # Context's natural width comes from top-level labels. Revealing
        # descendants must not widen its content-based minimum.
        width = 0
        for row in range(self.topLevelItemCount()):
            item = self.topLevelItem(row)
            if not item.isHidden():
                index = self.indexFromItem(item, column)
                width = max(width, self.sizeHintForIndex(index).width())
        return width + (self.indentation() if self.rootIsDecorated() else 0)

    def drawBranches(self, painter, rect, index):
        item = self.itemFromIndex(index)
        if item is None:
            return
        center = (rect.left() + self.indentation() // 2 if self.layoutDirection() == Qt.LayoutDirection.RightToLeft
                  else rect.right() - self.indentation() // 2)
        y = rect.center().y()
        painter.save()
        painter.setPen(QColor('#59616b'))
        step = self.indentation() * (-1 if self.layoutDirection() == Qt.LayoutDirection.RightToLeft else 1)
        parent = item.parent()
        if parent is not None:
            x = center - step
            last = parent.indexOfChild(item) == parent.childCount() - 1
            painter.drawLine(x, rect.top(), x, y if last else rect.bottom())
            painter.drawLine(x, y, center, y)
            ancestor = parent
            while ancestor.parent() is not None:
                x -= step
                owner = ancestor.parent()
                if owner.indexOfChild(ancestor) < owner.childCount() - 1:
                    painter.drawLine(x, rect.top(), x, rect.bottom())
                ancestor = owner
        if item.childCount() and item.isExpanded():
            painter.drawLine(center, y + 5, center, rect.bottom())
        painter.restore()
        if (not item.childCount()
                or item.childIndicatorPolicy() == QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator):
            return
        points = ([(center - 4, y - 2), (center + 4, y - 2), (center, y + 3)]
                  if item.isExpanded() else
                  [(center - 2, y - 4), (center - 2, y + 4), (center + 3, y)])
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('white'))
        painter.drawPolygon(QPolygon([QPoint(x, y) for x, y in points]))
        painter.restore()


class _OutlineDelegate(QStyledItemDelegate):
    def __init__(self, tree):
        super().__init__(tree)
        self.active_row = None

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        if self.active_row is not None and self.active_row['foreground'][3]:
            option.palette.setColor(QPalette.ColorRole.HighlightedText, QColor(*self.active_row['foreground']))
        elif brush is not None:
            option.palette.setBrush(QPalette.ColorRole.HighlightedText, brush)

    def paint(self, painter, option, index):
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        painter.fillRect(option.rect, QColor('black'))
        if selected and self.active_row is not None:
            painter.fillRect(option.rect, QColor(*self.active_row['background']))
            option.palette.setBrush(QPalette.ColorRole.Text,
                                    option.palette.brush(QPalette.ColorRole.HighlightedText))
        # Native focus/hover/selection painting must not replace scheme RGBA.
        option.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus
                          | QStyle.StateFlag.State_MouseOver)
        option.backgroundBrush = Qt.BrushStyle.NoBrush
        option.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        painter.restore()


class _LineArea(QWidget):
    def __init__(self, editor: "SourceEditor") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.editor.paint_gutter(event)


def _spaces_for_tabs(text: str) -> str:
    """Use a fixed two spaces per tab, independent of its current column."""
    return text.replace("\t", "  ")


class _SourceCursor(QTextCursor):
    def insertText(self, text, *args):  # noqa: N802 - Qt API
        super().insertText(_spaces_for_tabs(text), *args)


class SourceEditor(QPlainTextEdit):
    colorSchemeChanged = Signal()
    spellingVocabularyRequested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        font = QFont("monospace", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 2)
        self.setObjectName("sourceEditor")
        self.context_highlight = None
        self.context_depths = {}
        self._base_selections = []
        self._pulse_selections = []
        self._spelling_selections = []
        self._spelling_ranges = ()
        self.vocabulary_enabled = False
        self.spelling_suggestions = SpellingSuggestionController(self)
        self._spelling_starts = ()
        self.color_scheme = default_scheme()
        self.gutter = _LineArea(self)
        self.finding_lines: frozenset[int] = frozenset()
        self.finding_severities: dict[int, str] = {}
        self._line_positions = (0,)
        self._display_bytes = b""
        self._normalizing_tabs = False
        self._tabs_pending = False
        self.textChanged.connect(self._normalize_document_tabs)
        self.document().contentsChange.connect(self._source_contents_changed)
        self.blockCountChanged.connect(self._update_width)
        self.updateRequest.connect(self._update_gutter)
        self._update_width()
        self.cursorPositionChanged.connect(self._highlight_active_line)
        self.apply_color_scheme(self.color_scheme)

    def _normalize_document_tabs(self):
        # Accessibility and external QTextCursor users can bypass every widget
        # entry point. Replace their just-created undo command, rather than add
        # a cleanup command whose Undo would bring literal tabs back.
        if self._normalizing_tabs or not self._tabs_pending:
            return
        self._tabs_pending = False
        raw = self.document().toRawText()
        if "\t" not in raw:
            return
        desired = _spaces_for_tabs(raw)
        saved = self.textCursor()
        def mapped(position):
            prefix = raw.encode("utf-16-le")[:position * 2].decode("utf-16-le")
            return position + prefix.count("\t")
        anchor, position = mapped(saved.anchor()), mapped(saved.position())
        self._normalizing_tabs = True
        try:
            if not self.document().isUndoAvailable():
                super().setPlainText(desired.replace("\u2029", "\n"))
            else:
                self.document().undo()
                previous = self.document().toRawText()
                start = 0
                while start < min(len(previous), len(desired)) and previous[start] == desired[start]:
                    start += 1
                end = 0
                while (end < min(len(previous), len(desired)) - start
                       and previous[-end - 1] == desired[-end - 1]):
                    end += 1
                old_stop = len(previous) - end
                new_stop = len(desired) - end
                cursor = QTextCursor(self.document())
                cursor.setPosition(len(previous[:start].encode("utf-16-le")) // 2)
                cursor.setPosition(len(previous[:old_stop].encode("utf-16-le")) // 2,
                                   QTextCursor.MoveMode.KeepAnchor)
                cursor.beginEditBlock()
                cursor.insertText(desired[start:new_stop])
                cursor.endEditBlock()
            saved = self.textCursor()
            saved.setPosition(anchor)
            saved.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(saved)
        finally:
            self._normalizing_tabs = False
            self._tabs_pending = False

    def setPlainText(self, text):  # noqa: N802 - Qt API
        super().setPlainText(_spaces_for_tabs(text))

    def insertPlainText(self, text):  # noqa: N802 - Qt API
        super().insertPlainText(_spaces_for_tabs(text))

    def appendPlainText(self, text):  # noqa: N802 - Qt API
        super().appendPlainText(_spaces_for_tabs(text))

    def textCursor(self):  # noqa: N802 - Qt API
        return _SourceCursor(super().textCursor())

    def insertFromMimeData(self, source):  # noqa: N802 - Qt API
        # Native paste (including the context menu) and text drops use this
        # virtual entry point. Normalize before the undo command is created.
        normalized = QMimeData()
        normalized.setText(_spaces_for_tabs(source.text()))
        super().insertFromMimeData(normalized)

    def keyPressEvent(self, event):  # noqa: N802 - Qt API
        if (event.key() == Qt.Key.Key_Tab
                and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                             | Qt.KeyboardModifier.AltModifier
                                             | Qt.KeyboardModifier.MetaModifier)):
            if not self.isReadOnly():
                self.insertPlainText("  ")
            event.accept()
            return
        super().keyPressEvent(event)

    def inputMethodEvent(self, event):  # noqa: N802 - Qt API
        normalized = QInputMethodEvent(_spaces_for_tabs(event.preeditString()), event.attributes())
        normalized.setCommitString(_spaces_for_tabs(event.commitString()),
                                   event.replacementStart(), event.replacementLength())
        super().inputMethodEvent(normalized)
        event.setAccepted(normalized.isAccepted())

    def apply_color_scheme(self, scheme) -> None:
        self.color_scheme = validate_scheme(scheme)
        palette = self.palette()
        for key, role, kind in ((QPalette.ColorRole.Text, 'editor', 'foreground'),
                                (QPalette.ColorRole.Highlight, 'selection', 'background'),
                                (QPalette.ColorRole.HighlightedText, 'selection', 'foreground')):
            palette.setColor(key, QColor(*scheme[role][kind]))
        self.setPalette(palette)
        def css(role, kind):
            return 'rgba(' + ', '.join(str(c) for c in scheme[role][kind]) + ')'
        self.setStyleSheet('QPlainTextEdit#sourceEditor { font-size: 16px; color: ' + css('editor', 'foreground') + '; selection-background-color: ' + css('selection', 'background') + '; selection-color: ' + css('selection', 'foreground') + '; }')
        # Keep content backgrounds off the scroll area: native scrollbar styles
        # can use its Base color for their track, even with a separate bar palette.
        self.viewport().setObjectName('sourceEditorViewport')
        self.viewport().setStyleSheet(
            'QWidget#sourceEditorViewport { background: ' + css('editor', 'background') + '; }')
        self._highlight_active_line()
        self.set_spelling_ranges(self._spelling_ranges)
        self.viewport().update()
        self.colorSchemeChanged.emit()

    def _highlight_active_line(self) -> None:
        # An independent, empty extra selection paints the viewport width while
        # leaving the real cursor/anchor (including diagnostic spans) untouched.
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(*self.color_scheme['active_row']['background']))
        if self.color_scheme['active_row']['foreground'][3]:
            selection.format.setForeground(QColor(*self.color_scheme['active_row']['foreground']))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        selections = [selection]
        if self.context_highlight is not None:
            start, end = self.context_highlight
            block = self.document().findBlock(start)
            selections = []
            deepest = max(self.context_depths.values(), default=0)
            while block.isValid() and block.position() <= end:
                row = QTextEdit.ExtraSelection()
                row.format = QTextCharFormat(selection.format)
                depth = self.context_depths.get(block.blockNumber(), 0)
                floor = self.color_scheme['deepest_child_opacity'] / 100
                factor = 1 - (1 - floor) * depth / deepest if deepest else 1
                for role, setter in (('background', row.format.setBackground),
                                     ('foreground', row.format.setForeground)):
                    rgba = self.color_scheme['active_row'][role]
                    if role == 'background' or rgba[3]:
                        setter(QColor(*rgba[:3], round(rgba[3] * factor)))
                row.cursor = QTextCursor(block)
                row.cursor.clearSelection()
                selections.append(row)
                block = block.next()
        self._base_selections = selections
        self._refresh_extra_selections()
        self.gutter.update()

    def _refresh_extra_selections(self):
        self.setExtraSelections(self._base_selections + self._pulse_selections + self._spelling_selections)

    def set_spelling_ranges(self, ranges):
        ranges = tuple(sorted(ranges))
        if ranges != self._spelling_ranges:
            self.spelling_suggestions.invalidate()
        had_spelling = bool(self._spelling_ranges)
        self._spelling_ranges = ranges
        if had_spelling and not self._spelling_ranges:
            QToolTip.hideText()
        self._spelling_starts = tuple(start for start, _, _ in self._spelling_ranges)
        self._spelling_selections = []
        for start, end, message in self._spelling_ranges:
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(self.document())
            selection.cursor.setPosition(start)
            selection.cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            selection.format.setUnderlineColor(QColor(*self.color_scheme['spelling_underline']['foreground']))
            self._spelling_selections.append(selection)
        self._refresh_extra_selections()

    def spelling_message_at(self, position):
        index = bisect_right(self._spelling_starts, position) - 1
        if index >= 0:
            start, end, message = self._spelling_ranges[index]
            if start <= position < end:
                return message
        return None

    def viewportEvent(self, event):  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.ToolTip:
            QToolTip.hideText()
            return True
        return super().viewportEvent(event)

    def spelling_context_menu(self, position, *, native_actions=True):
        """Construct existing actions only; construction never requests corrections."""
        menu = self.createStandardContextMenu() if native_actions else QMenu(self)
        index = bisect_right(self._spelling_starts, position) - 1
        if index < 0 or self.isReadOnly():
            return menu
        start, end, _ = self._spelling_ranges[index]
        if not start <= position < end:
            return menu
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        word = cursor.selectedText()
        revision = self.document().revision()
        anchor = menu.actions()[0] if menu.actions() else None
        if self.vocabulary_enabled:
            menu.insertSeparator(anchor)
            for label, scope in (('Add to user dictionary', 'accepted'),
                                 ('Ignore word for this user (persistent)', 'ignored')):
                action = menu.addAction(label)
                menu.insertAction(anchor, action)
                action.triggered.connect(
                    lambda checked=False, scope=scope: self._request_vocabulary(
                        start, end, word, revision, scope))
        menu.insertSeparator(anchor)
        return menu

    def spelling_target_at(self, position):
        index = bisect_right(self._spelling_starts, position) - 1
        if index < 0 or self.isReadOnly():
            return None
        start, end, _ = self._spelling_ranges[index]
        if not start <= position < end:
            return None
        document = self.document()
        cursor = QTextCursor(document)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return WordTarget(document, document.revision(), start, end, cursor.selectedText())

    def _request_vocabulary(self, start, end, word, revision, scope):
        if (self.isReadOnly() or self.document().revision() != revision
                or not any(a == start and b == end for a, b, _ in self._spelling_ranges)):
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        if cursor.selectedText() == word:
            self.spellingVocabularyRequested.emit(scope, word)

    def _replace_spelling(self, start, end, word, revision, replacement):
        if self.isReadOnly() or self.document().revision() != revision:
            return
        if not any(a == start and b == end for a, b, _ in self._spelling_ranges):
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        if cursor.selectedText() != word:
            return
        cursor.beginEditBlock()
        cursor.insertText(_spaces_for_tabs(replacement))
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def contextMenuEvent(self, event):  # noqa: N802 - Qt API
        keyboard = event.reason() == event.Reason.Keyboard
        position = self.textCursor().position() if keyboard else self.cursorForPosition(event.pos()).position()
        menu = self.spelling_context_menu(position)
        if event.reason() == event.Reason.Mouse:
            self.spelling_suggestions.attach(menu, self.spelling_target_at(position))
        point = self.viewport().mapToGlobal(self.cursorRect().bottomLeft()) if keyboard else event.globalPos()
        try:
            menu.exec(point)
        finally:
            menu.deleteLater()
        event.accept()

    def set_pulse_ranges(self, ranges):
        self._pulse_selections = []
        for start, end in ranges:
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(self.document())
            selection.cursor.setPosition(start)
            selection.cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            self._pulse_selections.append(selection)
        self._refresh_extra_selections()

    def paint_pulse(self, factor):
        rgba = self.color_scheme['correlation_pulse']['background']
        color = QColor(*rgba[:3], round(rgba[3] * factor))
        for selection in self._pulse_selections:
            selection.format.setBackground(color)
        self._refresh_extra_selections()

    def _source_contents_changed(self, position, removed, added):
        if not (removed or added):
            return  # Formatting changes carry no source changes.
        # Cursor signals may arrive before DocumentTab schedules reanalysis.
        # Never rebuild a large old context selection against the edited source.
        self.context_highlight = None
        self.context_depths = {}
        cursor = QTextCursor(self.document())
        limit = max(0, self.document().characterCount() - 1)
        cursor.setPosition(min(position, limit))
        cursor.setPosition(min(position + added, limit), QTextCursor.MoveMode.KeepAnchor)
        fragment = cursor.selection().toRawText()
        self._tabs_pending |= "\t" in fragment
        inserted = fragment.encode("utf-16-le")
        old_length = len(self._display_bytes) // 2
        removed = min(removed, max(0, old_length - position))
        added = len(inserted) // 2
        stop = position + removed
        left = bisect_right(self._line_positions, position)
        right = bisect_right(self._line_positions, stop)
        starts = list(self._line_positions[:left])
        offset = position
        for line in fragment.splitlines(keepends=True):
            offset += len(line.encode("utf-16-le")) // 2
            if line and line[-1] in "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029":
                starts.append(offset)
        starts.extend(value + added - removed for value in self._line_positions[right:])
        self._line_positions = tuple(starts) or (0,)
        self._display_bytes = (self._display_bytes[:position * 2] + inserted
                               + self._display_bytes[stop * 2:])
        self.set_spelling_ranges(())
        self._update_width()
        self.gutter.update()

    def source_position(self, position: int) -> tuple[int, int]:
        """Canonical line and code-point column from a Qt UTF-16 position."""
        index = max(0, bisect_right(self._line_positions, position) - 1)
        prefix = self._display_bytes[self._line_positions[index] * 2:position * 2]
        return index + 1, len(prefix.decode("utf-16-le", errors="replace")) + 1

    def gutter_rows(self, block):
        """Project each real visual row, including U+2028 within a block."""
        layout = block.layout()
        for index in range(layout.lineCount()):
            line = layout.lineAt(index)
            number, _ = self.source_position(block.position() + line.textStart())
            yield number, round(line.y()), round(line.height())

    def gutter_width(self) -> int:
        digits = len(str(max(1, len(self._line_positions))))
        return 24 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_width(self, *_args) -> None:
        width = self.gutter_width()
        if getattr(self, '_last_gutter_width', None) != width:
            self.setViewportMargins(width, 0, 0, 0)
            self._last_gutter_width = width

    def _update_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_width()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.gutter.setGeometry(QRect(self.contentsRect().left(),
                                      self.contentsRect().top(), self.gutter_width(),
                                      self.contentsRect().height()))

    def paint_gutter(self, event) -> None:
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor(*self.color_scheme['gutter']['background']))
        block = self.firstVisibleBlock()
        active, _ = self.source_position(self.textCursor().position())
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                for number, offset, row_height in self.gutter_rows(block):
                    row_top = top + offset
                    if number == active:
                        painter.fillRect(0, row_top, self.gutter.width(), row_height, QColor(*self.color_scheme['active_row']['background']))
                    painter.setPen(QColor(*self.color_scheme['gutter']['foreground']))
                    painter.drawText(0, row_top, self.gutter.width() - 5, row_height,
                                     Qt.AlignmentFlag.AlignRight, str(number))
                    if number in self.finding_lines:
                        painter.setBrush(QColor({"critical": "#8b1020", "error": "#b42d35", "warning": "#b67b13",
                                                "information": "#527b9d"}.get(
                                                    self.finding_severities.get(number), "#527b9d")))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawEllipse(2, row_top + max(1, (row_height - 6) // 2), 6, 6)
            block = block.next()
            top += height



class DocumentTab(QWidget):
    inferenceModeRequested = Signal(str)

    def __init__(self, version: str, source: str = "", path: Path | None = None,
                 encoding: str = "utf-8", *, background: bool = False,
                 map_enabled: bool = True, inference_mode: str = 'heuristic') -> None:
        super().__init__()
        self.version = version
        self.profile = None
        self.configuration = {}
        self.analysis = None
        self._retained_analysis = None
        self._map_analysis = None
        self.map_enabled = map_enabled
        self._source_snapshots = {}
        self._source_history = {}
        self._map_color_history = {}
        self._pending_map_colors = None
        self._pending_exact_source = None
        self.controller = AnalysisController(self, heat_enabled=map_enabled) if background else None
        if self.controller:
            self.controller.parsed.connect(self._analysis_parsed)
            self.controller.ready.connect(self._analysis_ready)
            self.controller.failed.connect(self._analysis_failed)
        self.graph = self.controller.graph if self.controller else GraphController(self, enabled=map_enabled)
        self.graph.set_mode(inference_mode)
        self.graph.ready.connect(self._graph_ready)
        self.graph.failed.connect(self._graph_failed)
        self.path = path
        self.encoding = encoding
        loaded_source = source
        source = _spaces_for_tabs(source)
        self.original_source = source
        self.line_ending = _line_ending(source)
        self.dirty = False
        self._refreshing = False
        self.editor = SourceEditor()
        self._pulse_ranges = ()
        self._pulse_phase = 0.0
        self._pulse_last = time.monotonic()
        self.pulse_timer = QTimer(self)
        self.pulse_timer.setInterval(33)
        self.pulse_timer.timeout.connect(self._pulse_tick)
        self.highlighter = _CoreHighlighter(self.editor)
        self.outline_worker = FeatureController(self, calculation=derive_outline, name='outline') if self.controller else None
        self.highlight_worker = FeatureController(self, calculation=derive_highlighting, name='highlighting') if self.controller else None
        if self.outline_worker:
            self.outline_worker.ready.connect(self._outline_ready)
            self.outline_worker.failed.connect(self._outline_failed)
            self.highlight_worker.ready.connect(self._highlight_ready)
            self.highlight_worker.failed.connect(self._highlight_failed)
        self._outline_document_id = None
        self._findings_document_id = None
        self._outline_current = False
        self._findings_current = False
        self._highlight_document_id = None
        self._outline_requested_revision = None
        self._feature_snapshot = None
        self.outline = _OutlineTree()
        self.outline.setObjectName("contextOutline")
        self.outline.setHeaderLabels(["Context", "Line"])
        self.outline.setUniformRowHeights(True)
        self.outline.setIndentation(16)
        self.outline.header().setStretchLastSection(False)
        self.outline.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._outline_items = {}
        self._outline_expanded = set()
        self.outline.setItemDelegate(_OutlineDelegate(self.outline))
        self.outline.itemExpanded.connect(lambda item: self._outline_expansion(item, True))
        self.outline.itemCollapsed.connect(lambda item: self._outline_expansion(item, False))
        self._syncing_context = False
        self.diagnostic_list = ContentSizedTree()
        self.diagnostic_list.setObjectName("diagnosticTable")
        style_finding_header(self.diagnostic_list.header())
        self.diagnostic_list.setHeaderLabels(["Severity", "Rule ID", "Message", "Line", "Column"])
        self.diagnostic_list.setRootIsDecorated(False)
        self.diagnostic_list.setAlternatingRowColors(True)
        self.diagnostic_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.diagnostic_list.setUniformRowHeights(True)
        self.diagnostic_list.header().setSortIndicator(0, Qt.SortOrder.DescendingOrder)
        self.diagnostic_list.setSortingEnabled(True)
        header = self.diagnostic_list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.document: ParsedDocument | None = None
        self.diagnostics: DiagnosticResult | None = None

        self.outline.setToolTip("Recognition candidates; only supported containment creates parent edges")
        self.side_panel = QWidget()
        self.side_panel.setObjectName("sidePanel")
        self.side_panel.installEventFilter(self)
        outline_layout = QVBoxLayout(self.side_panel)
        outline_layout.setContentsMargins(0, 0, 0, 0)
        outline_layout.setSpacing(0)
        heading = QWidget()
        self.outline_heading = heading
        heading_layout = panel_heading_layout(heading)
        self.outline_title = QLabel("Outline")
        self.outline_title.setObjectName("outlineTitle")
        add_heading_control(heading_layout, self.outline_title)
        self.outline_spinner = PendingSpinner(self.editor, "Outline", heading)
        self.outline_spinner.setObjectName("outlinePendingSpinner")
        add_heading_control(heading_layout, self.outline_spinner)
        self.outline_status = QLabel('')
        self.outline_status.setObjectName('outlineStatus')
        add_heading_control(heading_layout, self.outline_status)
        heading_layout.addStretch()
        self.outline_toggle = QToolButton()
        self.outline_toggle.setObjectName('outlineExpansionToggle')
        self.outline_toggle.clicked.connect(self._toggle_outline)
        add_heading_control(heading_layout, self.outline_toggle)
        self._update_outline_toggle()
        outline_layout.addWidget(heading)
        outline_layout.addWidget(self.outline, 1)
        self.correlations_panel = QWidget()
        correlation_layout = QVBoxLayout(self.correlations_panel)
        correlation_layout.setContentsMargins(0, 0, 0, 0)
        correlation_layout.setSpacing(0)
        self.correlations_heading = QWidget()
        correlation_heading_layout = panel_heading_layout(self.correlations_heading)
        self.correlations_title = QLabel('Correlations')
        self.correlations_title.setObjectName('correlationsTitle')
        add_heading_control(correlation_heading_layout, self.correlations_title)
        correlation_heading_layout.addStretch()
        correlation_layout.addWidget(self.correlations_heading)
        self.correlations = ContentSizedTree()
        self.correlations.setItemDelegate(_OutlineDelegate(self.correlations))
        self.correlations.setObjectName('contextCorrelations')
        self.correlations.setHeaderLabels(['Symbol', 'Line', 'Column'])
        self.correlations.header().setStretchLastSection(False)
        self.correlations.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.correlations.setRootIsDecorated(False)
        self.correlations.setMaximumHeight(220)
        self.correlations.currentItemChanged.connect(self._correlation_selected)
        self.correlations.itemClicked.connect(self._correlation_clicked)
        correlation_layout.addWidget(self.correlations)
        outline_layout.addWidget(self.correlations_panel)
        self._correlation_document_id = None
        self.correlations_panel.hide()
        self.side_panel.hide()
        self.document_map = DocumentMap(self.editor, enabled=map_enabled, mode=inference_mode)
        self.document_map.moveRequested.connect(self._move_map_block)
        self.document_map.objectSelected.connect(self._map_object_selected)
        # Keep compact Find/Replace usable while allowing the map to resize.
        self.editor.setMinimumWidth(270)
        self.editor_map_split = QSplitter(Qt.Orientation.Horizontal)
        self.editor_map_split.setObjectName('editorMapSplitter')
        self.editor_map_split.setChildrenCollapsible(False)
        self.editor_column = QWidget()
        self.editor_column_layout = QVBoxLayout(self.editor_column)
        self.editor_column_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_column_layout.setSpacing(0)
        self.editor_header = QWidget()
        self.editor_header_layout = QHBoxLayout(self.editor_header)
        self.editor_header_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_header_layout.setSpacing(0)
        self.editor_column_layout.addWidget(self.editor_header)
        self.editor_column_layout.addWidget(self.editor, 1)
        self.map_column = QWidget()
        map_layout = QVBoxLayout(self.map_column)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)
        self.map_heading = QWidget()
        self.map_heading.setObjectName('panelHeading')
        map_heading_layout = QHBoxLayout(self.map_heading)
        map_heading_layout.setContentsMargins(4, 0, 2, 0)
        map_heading_layout.setSpacing(0)
        # Extra wrapped tab rows grow this header, but its controls stay
        # anchored beside the first row rather than drifting to the center.
        map_heading_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.map_title = QToolButton()
        self.map_title.setText('Infer Map')
        self.map_title.setAccessibleName('Infer Map')
        self.map_title.setObjectName('inferenceEditToggle')
        self.map_title.setCheckable(True)
        self.map_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.map_title.setStyleSheet(
            'QToolButton { padding: 0px 4px; }'
            'QToolButton:checked { background-color: #ed8b23; color: #000000; }')
        self.map_title.setToolTip('Toggle Infer Edit (inference paused)')
        self.map_title.toggled.connect(self.set_map_edit_mode)
        map_heading_layout.addWidget(self.map_title, 1)
        self.inference_mode_button = QToolButton()
        self.inference_mode_button.setObjectName('inferenceModeCycle')
        self.inference_mode_button.setAutoRaise(True)
        self.inference_mode_button.setStyleSheet('QToolButton { padding: 0px; }')
        self.inference_mode_button.setMinimumWidth(30)
        self.inference_mode_button.clicked.connect(self._cycle_inference_mode)
        map_heading_layout.addWidget(self.inference_mode_button)
        self._update_mode_button()
        map_layout.addWidget(self.map_heading)
        map_layout.addWidget(self.document_map, 1)
        self.editor_map_split.addWidget(self.editor_column)
        self.editor_map_split.addWidget(self.map_column)
        self.map_column.setVisible(map_enabled)
        self.document_map.setVisible(map_enabled)
        self.editor_map_split.setStretchFactor(0, 1)
        self.editor_map_split.setStretchFactor(1, 0)
        self.editor_map_split.setSizes([724, 176])
        self.editor_split = QSplitter(Qt.Orientation.Horizontal)
        self.editor_split.addWidget(self.editor_map_split)
        self.editor_split.addWidget(self.side_panel)
        self.editor_split.setStretchFactor(0, 4)
        self.editor_split.setStretchFactor(1, 1)
        self.editor_split.setSizes([900, 300])

        self.diagnostics_panel = QWidget()
        self.diagnostics_panel.setObjectName("diagnosticsPanel")
        diagnostics_layout = QVBoxLayout(self.diagnostics_panel)
        diagnostics_layout.setContentsMargins(0, 0, 0, 0)
        diagnostics_layout.setSpacing(0)
        heading = QWidget()
        self.findings_header = heading
        heading_layout = panel_heading_layout(heading, left=0)
        self.diagnostics_toggle = FindingExpansionButton()
        self.diagnostics_toggle.setObjectName('findingListExpansionToggle')
        self.diagnostics_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.diagnostics_toggle.setAutoRaise(True)
        self.diagnostics_toggle.setFixedWidth(20)
        self.diagnostics_toggle.setStyleSheet('QToolButton { padding: 0px; }')
        self.diagnostics_toggle.setAccessibleName('Collapse Finding List')
        self.diagnostics_toggle.setToolTip('Collapse Finding List')
        self.diagnostics_toggle.clicked.connect(self._toggle_diagnostics)
        add_heading_control(heading_layout, self.diagnostics_toggle)
        self.diagnostics_heading = QLabel("Finding List")
        add_heading_control(heading_layout, self.diagnostics_heading)
        self.diagnostic_counts = QWidget()
        counts_layout = QHBoxLayout(self.diagnostic_counts)
        counts_layout.setContentsMargins(0, 0, 0, 0)
        counts_layout.setSpacing(12)
        self.diagnostic_count_labels = {}
        self.diagnostic_count_icons = {}
        for severity in FINDING_ICONS:
            pair = QWidget()
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(4)
            count = QLabel('0')
            count.setAlignment(Qt.AlignmentFlag.AlignCenter)
            picture = QLabel()
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            picture.setPixmap(_finding_icon(self.style(), severity).pixmap(
                QSize(16, 16), self.devicePixelRatioF()))
            picture.setAccessibleName(severity.capitalize())
            pair_layout.addWidget(count)
            pair_layout.addWidget(picture)
            counts_layout.addWidget(pair)
            self.diagnostic_count_labels[severity] = count
            self.diagnostic_count_icons[severity] = picture
        add_heading_control(heading_layout, self.diagnostic_counts)
        self.diagnostic_spinner = PendingSpinner(self.editor, "Finding List", heading)
        self.diagnostic_spinner.setObjectName("findingsPendingSpinner")
        add_heading_control(heading_layout, self.diagnostic_spinner)
        self.diagnostic_status = QLabel()
        add_heading_control(heading_layout, self.diagnostic_status)
        self._update_finding_counts()
        heading_layout.addStretch()
        diagnostics_layout.addWidget(heading)
        diagnostics_layout.addWidget(self.diagnostic_list, 1)
        self.split = QSplitter(Qt.Orientation.Vertical)
        self.split.addWidget(self.editor_split)
        self.split.addWidget(self.diagnostics_panel)
        self.split.setStretchFactor(0, 4)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([560, 180])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        from .find_bar import FindBar
        self.find_bar = FindBar(self)
        layout.addWidget(self.split)
        self.set_header_height(max(self.map_heading.minimumSizeHint().height(),
                                   self.outline_heading.minimumSizeHint().height()))

        self.editor.setPlainText(source)
        self._source_snapshots[self.editor.document().toRawText().replace('\u2029', '\n')] = source
        self._source_history[(0, self.editor.document().toRawText().replace('\u2029', '\n'))] = source
        self.dirty = source != loaded_source
        self.editor.document().setModified(self.dirty)
        self._source_changed_pending = False
        self.editor.document().contentsChange.connect(self._source_edited)
        self.editor.document().undoCommandAdded.connect(self._source_command_added)
        self.editor.textChanged.connect(self._edited)
        self.outline.currentItemChanged.connect(self._outline_selected)
        self.outline.itemClicked.connect(self._outline_clicked)
        self.editor.cursorPositionChanged.connect(self._editor_context_changed)
        self.diagnostic_list.itemActivated.connect(self._navigate_finding)
        self.diagnostic_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.diagnostic_list.customContextMenuRequested.connect(self._spelling_finding_menu)
        self.refresh_model()

    def _update_finding_counts(self, findings=(), status=''):
        counts = dict.fromkeys(FINDING_ICONS, 0)
        for finding in findings:
            counts[finding.severity] += 1
        for severity, count in counts.items():
            label = self.diagnostic_count_labels[severity]
            label.setText(str(count))
            description = f"{count} {severity} {'finding' if count == 1 else 'findings'}"
            label.setAccessibleName(description)
            label.parentWidget().setToolTip(description)
        self.diagnostic_spinner.set_pending(False)
        self.diagnostic_status.setText(f'· {status}' if status else '')
        self.diagnostic_status.setVisible(bool(status))

    def _toggle_diagnostics(self):
        expand = self.diagnostic_list.isHidden()
        if not expand:
            self._diagnostics_split_sizes = self.split.sizes()
        self.diagnostic_list.setVisible(expand)
        self.diagnostics_toggle.setArrowType(Qt.ArrowType.DownArrow if expand else Qt.ArrowType.UpArrow)
        self.diagnostics_toggle.setAccessibleName(
            'Collapse Finding List' if expand else 'Expand Finding List')
        self.diagnostics_toggle.setToolTip(self.diagnostics_toggle.accessibleName())
        if expand:
            self.diagnostics_panel.setMaximumHeight(16777215)
            self.split.setSizes(self._diagnostics_split_sizes)
        else:
            self.diagnostics_panel.setMaximumHeight(self.diagnostics_heading.parentWidget().sizeHint().height())

    @property
    def source(self) -> str:
        if not self.dirty and not getattr(self, '_source_changed_pending', False):
            return self.original_source
        display = self.editor.document().toRawText().replace('\u2029', '\n')
        if self._pending_exact_source and self._pending_exact_source[0] == display:
            return self._pending_exact_source[1]
        key = self.editor.document().availableUndoSteps(), display
        if key in self._source_history:
            return self._source_history[key]
        if display in self._source_snapshots:
            return self._source_snapshots[display]
        return display.replace("\n", self.line_ending)

    def _source_edited(self, _position, removed, added):
        if removed or added:
            self._source_changed_pending = True

    def _source_command_added(self):
        # An edit after undo replaces that future. Normalized text alone cannot
        # identify history: two permutations may differ only in line endings.
        steps = self.editor.document().availableUndoSteps()
        self._source_history = {key: source for key, source in self._source_history.items()
                                if key[0] < steps}
        self._map_color_history = {key: colors for key, colors in self._map_color_history.items()
                                   if key[0] < steps}

    def _move_map_block(self, expected_source, plan):
        """Apply a validated permutation as one exact-source undo command."""
        view = self.document_map
        if (self.editor.isReadOnly() or not view.edit_mode
                or self.source != expected_source or plan.source == expected_source):
            return
        # QTextDocument stores normalized display text. Keep both exact source
        # snapshots so undo/redo round-trip mixed endings, BOM and Unicode too.
        current_display = self.editor.document().toRawText().replace('\u2029', '\n')
        target = QTextDocument()
        target.setPlainText(plan.source)
        target_display = target.toRawText().replace('\u2029', '\n')
        self._source_history[(self.editor.document().availableUndoSteps(), current_display)] = expected_source
        self._pending_exact_source = (target_display, plan.source)
        colors = view.freeze_colors()
        if colors is not None:
            self._map_color_history[(self.editor.document().availableUndoSteps(), expected_source,
                                     view.mode)] = colors
            self._pending_map_colors = colors.moved(plan)
        index = SourcePositionIndex(expected_source)
        start, end = min(plan.old_start, plan.destination), max(plan.old_end, plan.destination)
        target_index = SourcePositionIndex(plan.source)
        target_cursor = QTextCursor(target)
        target_cursor.setPosition(target_index.display(start))
        target_cursor.setPosition(target_index.display(end), QTextCursor.MoveMode.KeepAnchor)
        replacement = target_cursor.selection().toRawText().replace('\u2029', '\n')
        view._selection_restore = (plan.source, plan.new_start)
        view._committing_move = True
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(index.display(start))
        cursor.setPosition(index.display(end), QTextCursor.MoveMode.KeepAnchor)
        try:
            cursor.beginEditBlock()
            # Qt treats U+FEFF at the beginning of insertText as a BOM, even
            # mid-document. A temporary ordinary character protects it; both
            # insert/remove remain inside the same atomic undo command.
            cursor.insertText('\u200b' + replacement)
            sentinel = QTextCursor(self.editor.document())
            sentinel.setPosition(index.display(start))
            sentinel.setPosition(index.display(start) + 1, QTextCursor.MoveMode.KeepAnchor)
            sentinel.removeSelectedText()
            cursor.endEditBlock()
            self._source_history[(self.editor.document().availableUndoSteps(), target_display)] = plan.source
            if self._pending_map_colors is not None:
                self._map_color_history[(self.editor.document().availableUndoSteps(), plan.source,
                                         view.mode)] = self._pending_map_colors
        finally:
            self._pending_exact_source = None
            self._pending_map_colors = None
            view._committing_move = False

    def _edited(self) -> None:
        if self._refreshing or not self._source_changed_pending:
            return
        self._source_changed_pending = False
        self._clear_correlations()
        self._highlight_context(None)
        self.dirty = self.editor.document().isModified()
        # Source offsets and named evidence belong to this exact source revision.
        self.graph.clear_options()
        self.refresh_model()

    def refresh_model(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.document_map.set_model(None)
        self.editor.set_spelling_ranges(())
        self._clear_correlations()
        try:
            if self.controller:
                self._highlight_context(None)
                # These fields are authoritative current-source state. Presentation
                # retains its last snapshot, but none of its offsets can act on edits.
                if self.analysis is not None:
                    retire_snapshot(self._retained_analysis)
                    self._retained_analysis = self.analysis
                self.document = None
                self.diagnostics = None
                self.analysis = None
                self._feature_snapshot = None
                self._outline_requested_revision = None
                self._outline_current = False
                self._findings_current = False
                self.editor.finding_lines = frozenset()
                self.editor.finding_severities = {}
                self.editor.gutter.update()
                self.highlighter.invalidate()
                self.diagnostic_status.clear()
                self.diagnostic_status.hide()
                self.outline_status.clear()
                self.outline_status.setToolTip('')
                self.diagnostic_spinner.set_pending(True, stale=bool(self.diagnostic_list.topLevelItemCount()))
                self.outline_spinner.set_pending(True, stale=bool(self._outline_items))
                self.diagnostics_heading.setToolTip("Analysis pending; previous results are stale and navigation is unavailable")
                revision = self.controller.request(self.source, self.version, profile=self.profile,
                                                   configuration=self.configuration)
                self.outline_worker.invalidate(revision)
                self.highlight_worker.invalidate(revision)
            else:
                self._refresh_model_contents()
        finally:
            self._refreshing = False

    def _refresh_model_contents(self) -> None:
        self.analysis = analyze(self.source, arcgrav_version=self.version,
                                profile=self.profile, configuration=self.configuration)
        self.document = self.analysis.document
        self.diagnostics = self.analysis.diagnostics
        self._map_analysis = self.analysis
        self.graph.set_analysis(self.graph.revision + 1, self._map_analysis)
        self._render_analysis()

    def _current_analysis_result(self, revision, result):
        return (self.controller and not self.controller.closed and revision == self.controller.revision
                and result.document.source == self.source
                and result.document.session.arcgrav_version == self.version
                and result.document.session.profile == self.profile
                and result.document.session.configuration == self.configuration)

    def _analysis_parsed(self, revision, result):
        if not self._current_analysis_result(revision, result):
            return
        self.analysis = result
        self.document = result.document
        self._map_analysis = result
        self._feature_snapshot = self.controller.packed_snapshot or self.controller.analysis_snapshot
        if self._feature_snapshot is None:
            self._feature_snapshot = freeze_analysis(result)
        self.highlight_worker.request(revision, self._feature_snapshot)
        self.ensure_outline()
        self._render_map()

    def _analysis_ready(self, revision, result):
        if not self._current_analysis_result(revision, result):
            return
        self.analysis = result
        self.document = result.document
        self.diagnostics = result.diagnostics
        self._refreshing = True
        try:
            # A slow Findings process cannot hold up Outline, Highlighting or Map.
            # Each feature publishes its own current-revision presentation.
            projection = self.controller.findings_projection
            if projection is None:  # Explicit custom analyzer seam, never production.
                projection = derive_findings(result)
            apply_findings(self, projection)
        finally:
            self._refreshing = False

    def _analysis_failed(self, revision, message):
        if self.controller and not self.controller.closed and revision == self.controller.revision:
            self.editor.set_spelling_ranges(())
            self.diagnostic_spinner.set_pending(False)
            self.diagnostic_status.setText('· unavailable · stale' if self.diagnostic_list.topLevelItemCount() else '· unavailable')
            self.diagnostic_status.show()
            self.diagnostics_heading.setToolTip(f"Analysis failed: {message}; overall conformance unknown")
            if self.controller.parsed_analysis is None:
                self.outline_spinner.set_pending(False)
                self.outline_status.setText('· unavailable · stale' if self._outline_items else '· unavailable')
                self.document_map.set_error(message)

    def set_analysis_context(self, version, *, profile=None, configuration=None):
        self.editor.spelling_suggestions.invalidate()
        session = LanguageCore.open_source(self.source, arcgrav_version=version,
                                           profile=profile, configuration=configuration)
        self.version, self.profile = version, profile
        self.configuration = session.configuration
        self.refresh_model()

    def dispose_analysis(self):
        self.outline_spinner.set_pending(False)
        self.diagnostic_spinner.set_pending(False)
        self.pulse_timer.stop()
        self.editor.set_pulse_ranges(())
        self.editor.set_spelling_ranges(())
        if self.controller:
            self.controller.close()
        self.graph.close()
        if self.outline_worker:
            self.outline_worker.close()
            self.highlight_worker.close()

    def closeEvent(self, event):
        self.dispose_analysis()
        super().closeEvent(event)

    def set_map_enabled(self, enabled):
        changed = self.map_enabled != enabled
        self.map_enabled = enabled
        self.document_map.set_analysis_enabled(enabled)
        self.document_map.setVisible(enabled)
        self.map_column.setVisible(enabled)
        self.graph.set_enabled(enabled and not self.document_map.edit_mode)
        if changed and enabled and self.document is not None:
            self._render_map()

    def set_map_edit_mode(self, enabled):
        self.document_map.set_edit_mode(enabled)
        self.map_title.setChecked(enabled)
        self.map_title.setText('Infer Edit' if enabled else 'Infer Map')
        self.map_title.setAccessibleName(self.map_title.text())
        self.inference_mode_button.setEnabled(not enabled)
        self.graph.set_enabled(self.map_enabled and not enabled)
        self._render_map()

    def _cycle_inference_mode(self):
        if self.document_map.edit_mode:
            return
        modes = tuple(MODE_LABELS)
        mode = modes[(modes.index(self.graph.mode) + 1) % len(modes)]
        self.inferenceModeRequested.emit(mode)

    def _update_mode_button(self):
        modes = tuple(MODE_LABELS)
        mode = self.graph.mode
        next_mode = modes[(modes.index(mode) + 1) % len(modes)]
        self.inference_mode_button.setText(MODE_CODES[mode])
        self.inference_mode_button.setAccessibleName(
            f'Inference mode: {MODE_LABELS[mode]}. Switch to {MODE_LABELS[next_mode]}')
        self.inference_mode_button.setToolTip(
            f'{MODE_LABELS[mode]}\n\n{MODE_HELP[mode]}')

    def set_header_height(self, height):
        for heading in (self.editor_header, self.map_heading):
            heading.setFixedHeight(height)
        outline_height = max(self.outline_heading.minimumSizeHint().height(),
                             self.findings_header.minimumSizeHint().height())
        self.outline_heading.setFixedHeight(outline_height)
        self.outline.header().setFixedHeight(outline_height)
        self.findings_header.setFixedHeight(outline_height)
        self.correlations_heading.setFixedHeight(outline_height)
        self.correlations.header().setFixedHeight(outline_height)

    def set_inference_mode(self, mode):
        self.graph.set_mode(mode)
        self._update_mode_button()
        self.document_map.set_mode(mode)
        # Cancelled graph results must disappear before the replacement arrives.
        self._render_map()

    def set_semantic_options(self, options):
        self.graph.set_options(options)
        self._render_map()

    def _graph_ready(self, revision, heat):
        if (self.graph.closed or not self.map_enabled or self.document_map.edit_mode or revision != self.graph.revision
                or self.graph.analysis is not self._map_analysis):
            return
        self._map_color_history.clear()
        self._render_map()

    def _graph_failed(self, revision, message):
        if (not self.graph.closed and self.map_enabled and not self.document_map.edit_mode and revision == self.graph.revision
                and self.graph.analysis is self._map_analysis):
            self.document_map.set_error(message)

    def _render_map(self):
        if not self.map_enabled:
            return
        heat = self.graph.heat if self.graph.analysis is self._map_analysis else None
        colors = None
        if self.document is not None and self.document_map.edit_mode:
            colors = self._pending_map_colors or self._map_color_history.get(
                (self.editor.document().availableUndoSteps(), self.document.source, self.document_map.mode))
        self.document_map.set_model(self.document, self.analysis.tree if self.analysis else None,
                                    heat=heat, semantics=self.analysis.semantics if self.analysis else None,
                                    colors=colors)

    def _render_analysis(self):
        """Explicit synchronous preview path; production uses process slots."""
        self._render_map()
        self.highlighter.update_model(self.document)
        self._highlight_document_id = self.document.document_id
        self.ensure_outline()
        if self.analysis:
            projection = derive_findings(self.analysis)
        else:
            from types import SimpleNamespace
            projection = derive_findings(SimpleNamespace(document=self.document, diagnostics=self.diagnostics))
        apply_findings(self, projection)

    def ensure_outline(self):
        if self.document is None or (self._outline_current and self._outline_document_id == self.document.document_id):
            return
        if self.controller:
            # Context navigation also consumes Outline when its panel is hidden.
            if self._feature_snapshot is None:
                return
            if self._outline_requested_revision != self.controller.revision:
                self._outline_requested_revision = self.controller.revision
                self.outline_worker.request(self.controller.revision, self._feature_snapshot)
        else:
            apply_outline(self, derive_outline(self.analysis or self.document))

    def _outline_ready(self, revision, projection):
        if (not self.controller or self.controller.closed or revision != self.controller.revision
                or self.document is None or projection.document_id != self.document.document_id):
            return
        apply_outline(self, projection)

    def _outline_failed(self, revision, message):
        if self.controller and not self.controller.closed and revision == self.controller.revision:
            self.outline_spinner.set_pending(False)
            self.outline_status.setText('· unavailable · stale' if self._outline_items else '· unavailable')
            self.outline_status.setToolTip(message)

    def _highlight_ready(self, revision, projection):
        if (not self.controller or self.controller.closed or revision != self.controller.revision
                or self.document is None or projection.document_id != self.document.document_id):
            return
        if self.highlighter.apply_projection(projection):
            self._highlight_document_id = projection.document_id
            self.editor.setToolTip('')

    def _highlight_failed(self, revision, message):
        if self.controller and revision == self.controller.revision:
            self.editor.setToolTip('Syntax highlighting unavailable: ' + message)

    def _outline_expansion(self, item, expanded):
        key = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if key is not None:
            if expanded:
                self._outline_expanded.add(key)
            else:
                self._outline_expanded.discard(key)
        self._update_outline_toggle()

    def _update_outline_toggle(self):
        parents = [item for item in self._outline_items.values() if item.childCount()
                   and item.childIndicatorPolicy() != QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator]
        expand = not parents or any(not item.isExpanded() for item in parents)
        self.outline_toggle.setEnabled(bool(parents))
        self.outline_toggle.setText('⊞' if expand else '⊟')
        action = 'Expand All' if expand else 'Collapse All'
        self.outline_toggle.setAccessibleName(action)

    def _toggle_outline(self):
        expand = self.outline_toggle.accessibleName() == 'Expand All'
        # Signals record stable path keys exactly as manual expansion does.
        for item in self._outline_items.values():
            if item.childCount() and item.childIndicatorPolicy() != QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator:
                item.setExpanded(expand)
        self._update_outline_toggle()

    def apply_outline_scheme(self):
        scheme = self.editor.color_scheme
        background = QColor(*scheme['active_row']['background'])
        # Branch/row areas outside delegate cells use the same RGBA over black.
        rgb = ', '.join(str(round(value * background.alphaF())) for value in background.getRgb()[:3])
        for tree in (self.outline, self.correlations):
            tree.itemDelegate().active_row = scheme['active_row']
            stylesheet = (f'QTreeWidget {{ selection-background-color: rgb({rgb}); }} '
                          'QTreeWidget::item { background: transparent; }')
            if tree.styleSheet() != stylesheet:
                tree.setStyleSheet(stylesheet)
            viewport_name = tree.objectName() + 'Viewport'
            tree.viewport().setObjectName(viewport_name)
            tree.viewport().setStyleSheet(
                f'QWidget#{viewport_name} {{ background: black; alternate-background-color: black; }}')
            tree.viewport().update()
        items = list(self._outline_items.values())
        items.extend(self.correlations.topLevelItem(i) for i in range(self.correlations.topLevelItemCount()))
        for item in items:
            role = item.data(0, Qt.ItemDataRole.UserRole + 2) or 'editor'
            color = QColor(*scheme[role]['foreground'])
            for column in range(item.columnCount()):
                item.setForeground(column, color)
        self.outline.viewport().update()
        self._sync_pulse()

    def eventFilter(self, watched, event):
        if watched is self.side_panel and event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            self._sync_pulse()
            if event.type() == QEvent.Type.Show:
                QTimer.singleShot(0, self.ensure_outline)
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_pulse()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._stop_pulse()

    def _stop_pulse(self):
        self.pulse_timer.stop()
        self.editor.set_pulse_ranges(())

    def _sync_pulse(self):
        scheme = self.editor.color_scheme
        eligible = (self.isVisible() and self.side_panel.isVisible()
                    and self.document is not None
                    and self._correlation_document_id == self.document.document_id
                    and self.document.source == self.source and self._pulse_ranges
                    and scheme['pulse_cycles_per_minute']
                    and scheme['correlation_pulse']['background'][3])
        if not eligible:
            self._stop_pulse()
            return
        if not self.pulse_timer.isActive():
            self._pulse_phase = 0.0
            self._pulse_last = time.monotonic()
            self.editor.set_pulse_ranges(self._pulse_ranges)
            self.pulse_timer.start()
        self.editor.paint_pulse((1 - math.cos(self._pulse_phase)) / 2)

    def _pulse_tick(self):
        now = time.monotonic()
        self._pulse_phase = (self._pulse_phase + (now - self._pulse_last)
                             * self.editor.color_scheme['pulse_cycles_per_minute'] * math.tau / 60) % math.tau
        self._pulse_last = now
        self.editor.paint_pulse((1 - math.cos(self._pulse_phase)) / 2)

    def _editor_context_changed(self):
        self._sync_context(reveal=not self._refreshing)

    def _sync_context(self, *_args, reveal=False):
        if (self._syncing_context or self.document is None
                or getattr(self, '_source_changed_pending', False)):
            return
        if self.document.source != self.source:
            blocker = QSignalBlocker(self.outline)
            self.outline.setCurrentItem(None)
            self._highlight_context(None)
            return
        self.ensure_outline()
        if not self._outline_current or self._outline_document_id != self.document.document_id:
            return
        if (not reveal and self._correlation_document_id == self.document.document_id
                and self.outline.currentItem() is not None):
            # Panel/tab switches retain the parent context used to navigate
            # correlations, even while the cursor is at a reference elsewhere.
            return
        line, column = self.editor.source_position(self.editor.textCursor().position())
        position = self._context_line_starts[min(line - 1, len(self._context_line_starts) - 1)] + column - 1
        entries = [fact for fact in self.document.structural_facts if fact.id in self._outline_items]
        def selection_span(fact):
            return self._context_spans.get(fact.id, fact.span) if fact.kind == 'literal_open' else fact.span
        containing = [fact for fact in entries
                      if selection_span(fact).start <= position < selection_span(fact).end]
        if containing:
            fact = min(containing, key=lambda fact: fact.span.end - fact.span.start)
        else:
            # Unclassified text follows only a parser-supported owner, never
            # a previous sibling or an ended child block. Blank lines may have none.
            fact = None
            if self.analysis:
                node = next((n for n in self.analysis.tree.nodes
                             if n.span.start <= position < n.span.end), None)
                seen = set()
                while node is not None and node.id not in seen:
                    seen.add(node.id)
                    owner = node.parent if node.parent is not None else node.section
                    node = self.analysis.tree.nodes[owner] if owner is not None else None
                    fact = next((f for f in entries if node is not None and f.span == node.span), None)
                    if fact is not None:
                        break
        item = self._outline_items.get(fact.id) if fact else None
        blocker = QSignalBlocker(self.outline)
        self.outline.setCurrentItem(item)
        if item:
            parent = item.parent()
            while parent:
                key = parent.data(0, Qt.ItemDataRole.UserRole + 1)
                parent.setExpanded(reveal or key in self._outline_expanded)
                if reveal:
                    self._outline_expansion(parent, True)
                parent = parent.parent()
            if reveal:
                self.outline.scrollToItem(item)
        del blocker
        self._highlight_context(item)
        if reveal:
            self._update_correlations(item)

    def _map_object_selected(self, document, span):
        if (self.document is None or document.document_id != self.document.document_id
                or document.source != self.source):
            return
        self.ensure_outline()
        if not self._outline_current or self._outline_document_id != document.document_id:
            return
        fact = next((fact for fact in document.structural_facts
                     if fact.span == span and fact.id in self._outline_items), None)
        if fact is None:
            return
        item = self._outline_items[fact.id]
        blocker = QSignalBlocker(self.outline)
        self.outline.setCurrentItem(item)
        self.outline.scrollToItem(item)
        del blocker
        # Also handles repeated clicks, source offsets, scope and correlations.
        self._outline_clicked(item)

    def _outline_selected(self, item, _previous):
        self._outline_clicked(item)

    def _outline_clicked(self, item, _column=0):
        if (self._syncing_context or item is None or self.document is None
                or self.document.source != self.source
                or not self._outline_current or self._outline_document_id != self.document.document_id):
            return
        fact = self.document.fact(item.data(0, Qt.ItemDataRole.UserRole))
        if fact is None:
            return
        self._syncing_context = True
        try:
            cursor = self.editor.textCursor()
            cursor.setPosition(_display_offset(self.document.source, fact.span.start))
            self.editor.setTextCursor(cursor)
            self.editor.centerCursor()
            self._highlight_context(item)
            self._update_correlations(item)
        finally:
            self._syncing_context = False

    def _clear_correlations(self):
        self._stop_pulse()
        self._pulse_ranges = ()
        self._correlation_document_id = None
        blocker = QSignalBlocker(self.correlations)
        self.correlations.clear()
        self.correlations_panel.hide()

    def _update_correlations(self, item):
        self._clear_correlations()
        if (item is None or item.parent() is not None or self.analysis is None
                or self.document is None or self.document.source != self.source
                or not self._outline_current or self._outline_document_id != self.document.document_id):
            return
        fact = self.document.fact(item.data(0, Qt.ItemDataRole.UserRole))
        node = next((n for n in self.analysis.tree.nodes if n.span == fact.span), None)
        if node is None or node.symbol_body_span is None:
            return  # Nonsymbol sections do not imply semantic correlations.
        semantics = self.analysis.semantics
        declaration = next((symbol for symbol in semantics.symbols
                            if symbol.kind == 'anchor' and symbol.span == node.symbol_body_span), None)
        if declaration is None:
            resolution = next((r for r in semantics.resolutions
                               if r.reference.span == node.symbol_body_span
                               and r.status in ('unique_prior_anchor', 'unique_prior_alias')
                               and len(r.candidates) == 1), None)
            if resolution is not None:
                declaration = next((symbol for symbol in semantics.symbols
                                    if symbol.span == resolution.candidates[0]
                                    and symbol.kind in ('anchor', 'alias')), None)
        if declaration is None:
            return
        spans = {declaration.span}
        spans.update(r.reference.span for r in semantics.resolutions
                     if r.status in ('unique_prior_anchor', 'unique_prior_alias')
                     and r.candidates == (declaration.span,))
        for span in sorted(spans, key=lambda span: span.start):
            point = self.document.source_range(span).start
            row = QTreeWidgetItem([f'[{declaration.name}]', str(point.line), str(point.column)])
            row.setData(0, Qt.ItemDataRole.UserRole, span)
            row.setData(0, Qt.ItemDataRole.UserRole + 2, 'symbol')
            row.setToolTip(0, 'Declaration' if span == declaration.span else 'Reference')
            self.correlations.addTopLevelItem(row)
        self._correlation_document_id = self.document.document_id
        self._pulse_ranges = tuple((_display_offset(self.source, span.start),
                                    _display_offset(self.source, span.end))
                                   for span in sorted(spans, key=lambda span: span.start))
        self.apply_outline_scheme()
        self.correlations_panel.show()

    def _correlation_selected(self, item, _previous):
        self._correlation_clicked(item)

    def _correlation_clicked(self, item, _column=0):
        if (item is None or self.document is None or self._syncing_context
                or self.document.document_id != self._correlation_document_id
                or self.document.source != self.source):
            return
        span = item.data(0, Qt.ItemDataRole.UserRole)
        self._syncing_context = True
        try:
            cursor = self.editor.textCursor()
            cursor.setPosition(_display_offset(self.document.source, span.start))
            self.editor.setTextCursor(cursor)
            self.editor.centerCursor()
            # Keep the selected parent, its scope highlight and this list.
        finally:
            self._syncing_context = False

    def _highlight_context(self, item):
        self.editor.context_highlight = None
        self.editor.context_depths = {}
        if item is not None and self.document is not None and self.document.source == self.source:
            span = self._context_spans.get(item.data(0, Qt.ItemDataRole.UserRole))
            if span is not None:
                # Exclude the final line break so the next sibling row is not painted.
                end = span.end
                while end > span.start and self.document.source[end - 1] in '\r\n':
                    end -= 1
                self.editor.context_highlight = (_display_offset(self.document.source, span.start),
                                                 _display_offset(self.document.source, end))
                pending = [(item, 0)]
                while pending:
                    current, depth = pending.pop()
                    child_span = self._context_spans[current.data(0, Qt.ItemDataRole.UserRole)]
                    child_end = child_span.end
                    while child_end > child_span.start and self.document.source[child_end - 1] in '\r\n':
                        child_end -= 1
                    block = self.editor.document().findBlock(_display_offset(self.document.source, child_span.start))
                    last = _display_offset(self.document.source, child_end)
                    while block.isValid() and block.position() <= last:
                        number = block.blockNumber()
                        self.editor.context_depths[number] = max(depth, self.editor.context_depths.get(number, 0))
                        block = block.next()
                    pending.extend((current.child(i), depth + 1) for i in range(current.childCount()))
        self.editor._highlight_active_line()

    def _spelling_finding_menu(self, point):
        item = self.diagnostic_list.itemAt(point)
        if (item is None or self.document is None or self.document.source != self.source
                or not self._findings_current or self._findings_document_id != self.document.document_id):
            return
        finding = item.data(0, Qt.ItemDataRole.UserRole)
        if finding is None or finding.rule_id != 'AG-SPELLING':
            return
        menu = self.editor.spelling_context_menu(
            _display_offset(self.source, finding.source_range.span.start), native_actions=False)
        try:
            menu.exec(self.diagnostic_list.viewport().mapToGlobal(point))
        finally:
            menu.deleteLater()

    def _navigate_finding(self, item, _column: int = 0) -> None:
        if (self.document is None or self.document.source != self.source
                or not self._findings_current or self._findings_document_id != self.document.document_id):
            return
        finding: Finding = item.data(0, Qt.ItemDataRole.UserRole)
        self.navigate(finding.source_range.span.start, finding.source_range.span.end)

    def navigate(self, start: int, end: int) -> None:
        if self.document is None or self.document.source != self.source:
            return
        self.document.source_range(SourceSpan(start, end))
        cursor = self.editor.textCursor()
        cursor.setPosition(_display_offset(self.document.source, start))
        cursor.setPosition(_display_offset(self.document.source, end),
                           QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.editor.setFocus()

    def save(self, path: Path | None = None) -> Path:
        destination = path or self.path
        if destination is None:
            raise ValueError("a destination path is required")
        destination = _save_path(destination)
        source = self.source
        destination.write_bytes(source.encode(self.encoding))
        self.path = destination
        self.original_source = source
        self.dirty = False
        self.editor.document().setModified(False)
        return destination

    def status_text(self) -> str:
        return (f"{self.encoding} · "
                f"{_ending_label(self.source)} · "
                f"{'modified' if self.dirty else ('saved' if self.path else 'untitled')}")


class _TabButton(QToolButton):
    """A focusable tab with mouse dragging across wrapped rows."""
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self.setCheckable(True)
        self.setObjectName('documentTab')
        self._press = None

    def mousePressEvent(self, event):
        self._press = event.globalPosition().toPoint()
        self.bar.setCurrentIndex(self.bar._buttons.index(self))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.bar._movable and self._press is not None and event.buttons() & Qt.MouseButton.LeftButton
                and (event.globalPosition().toPoint() - self._press).manhattanLength()
                >= QApplication.startDragDistance()):
            destination = self.bar.tabAt(self.bar.mapFromGlobal(event.globalPosition().toPoint()))
            source = self.bar._buttons.index(self)
            if destination >= 0 and destination != source:
                self.bar.moveTab(source, destination)
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        direction = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(event.key())
        if direction is not None and self.bar.count():
            index = (self.bar.currentIndex() + direction) % self.bar.count()
            self.bar.setCurrentIndex(index)
            self.bar._buttons[index].setFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        super().mouseReleaseEvent(event)


class _DocumentTabBar(QWidget):
    """A wrapping document strip with real focusable tabs and close controls.

    Unlike QTabBar's single scrolling row, every tab stays inside the editor
    column. Rows after the first start at the column's left edge, under +.
    """
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)
    tabMoved = Signal(int, int)
    heightChanged = Signal()

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self._buttons = []
        self._closes = []
        self._labels = []
        self._tips = []
        self._current = -1
        self._closable = True
        self._movable = True
        self._height = 0
        self._laying_out = False
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def rowHeight(self):
        plus = self.owner.cornerWidget(Qt.Corner.TopLeftCorner)
        tab = self.owner.currentWidget()
        # Use the compact Outline heading as the baseline, rather than the
        # main toolbar's padded New button. Wrapped tabs retain whole rows.
        return max(self.fontMetrics().height() + 2, plus.sizeHint().height() if plus else 0,
                   tab.outline_heading.minimumSizeHint().height() if tab else 0)

    def sizeHint(self):
        return QSize(300, max(self._height, self.rowHeight()))

    def minimumSizeHint(self):
        return QSize(0, self.rowHeight())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._reflow()

    def _reflow(self):
        if self._laying_out:
            return
        self._laying_out = True
        try:
            height = self.rowHeight()
            width = max(1, self.width())
            plus = self.owner.cornerWidget(Qt.Corner.TopLeftCorner)
            x = min(width, plus.sizeHint().width()) if plus else 0
            if plus:
                plus.setGeometry(0, 0, x, height)
                plus.raise_()
            y = 0
            for index, button in enumerate(self._buttons):
                desired = self.fontMetrics().horizontalAdvance(self._labels[index]) + 48
                tab_width = min(desired, width)
                if x and x + tab_width > width:
                    # A very long first tab shares the first row with +.
                    if index == 0:
                        tab_width = max(1, width - x)
                    else:
                        x, y = 0, y + height
                button.setGeometry(x, y, tab_width, height)
                button.setText(self.fontMetrics().elidedText(self._labels[index], Qt.TextElideMode.ElideRight,
                                                           max(0, tab_width - 44)))
                close = self._closes[index]
                close.setGeometry(x + max(0, tab_width - 20), y + (height - 18) // 2, 18, 18)
                close.raise_()
                x += tab_width
            total = y + height
            if self._height != total:
                self._height = total
                self.setFixedHeight(total)
                self.updateGeometry()
                self.heightChanged.emit()
        finally:
            self._laying_out = False

    def addTab(self, label):
        button = _TabButton(self)
        close = QToolButton(self)
        close.setText('×')
        close.setObjectName('documentTabClose')
        close.setStyleSheet('QToolButton { padding: 0px; border: 0px; background: transparent; }')
        self._buttons.append(button)
        self._closes.append(close)
        self._labels.append(label)
        self._tips.append('')
        button.clicked.connect(lambda: self.setCurrentIndex(self._buttons.index(button)))
        close.clicked.connect(lambda: self.tabCloseRequested.emit(self._closes.index(close)))
        button.show()
        close.setVisible(self._closable)
        index = len(self._buttons) - 1
        self.setTabText(index, label)
        if self._current < 0:
            self.setCurrentIndex(0)
        return index

    def removeTab(self, index):
        if not 0 <= index < self.count():
            return
        current = self._buttons[self._current] if self._current >= 0 else None
        for controls in (self._buttons, self._closes):
            control = controls.pop(index)
            control.hide()
            control.deleteLater()
        self._labels.pop(index)
        self._tips.pop(index)
        next_index = self._buttons.index(current) if current in self._buttons else min(index, self.count() - 1)
        self._current = -1
        self._reflow()
        self.setCurrentIndex(next_index)

    def moveTab(self, before, after):
        if before == after or not (0 <= before < self.count() and 0 <= after < self.count()):
            return
        selected = self._buttons[self._current]
        for values in (self._buttons, self._closes, self._labels, self._tips):
            values.insert(after, values.pop(before))
        self._current = self._buttons.index(selected)
        self._reflow()
        self.tabMoved.emit(before, after)

    def setCurrentIndex(self, index):
        if index < -1 or index >= self.count():
            return
        changed = index != self._current
        self._current = index
        for i, button in enumerate(self._buttons):
            button.setChecked(i == index)
        if changed:
            self.currentChanged.emit(index)

    def setTabText(self, index, text):
        changed = self._labels[index] != text
        self._labels[index] = text
        self._buttons[index].setAccessibleName(text)
        self._closes[index].setAccessibleName(f'Close {text}')
        self._closes[index].setToolTip(f'Close {text}')
        if changed or not self._buttons[index].text():
            self._reflow()

    def setTabToolTip(self, index, text):
        self._tips[index] = text
        self._buttons[index].setToolTip(text)

    def count(self): return len(self._buttons)
    def currentIndex(self): return self._current
    def tabText(self, index): return self._labels[index]
    def tabToolTip(self, index): return self._tips[index]
    def tabRect(self, index): return self._buttons[index].geometry()
    def tabAt(self, point):
        return next((i for i, button in enumerate(self._buttons) if button.geometry().contains(point)), -1)
    def tabButton(self, index, side):
        return self._closes[index] if side == QTabBar.ButtonPosition.RightSide else None
    def setTabsClosable(self, enabled):
        self._closable = enabled
        for close in self._closes: close.setVisible(enabled)
    def setMovable(self, enabled): self._movable = enabled


class _DocumentTabs(QWidget):
    """One document stack; its shared navigation strip lives over the editor only.

    Panels remain owned by their document, so switching tabs never transfers
    analysis, selection, splitters, or unsaved source between documents.
    """
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self._stack = QStackedWidget()
        self._strip = QWidget()
        self._strip_layout = QHBoxLayout(self._strip)
        self._strip_layout.setContentsMargins(0, 0, 0, 0)
        self._strip_layout.setSpacing(0)
        self._corner = None
        self._bar = _DocumentTabBar(self)
        self._strip_layout.addWidget(self._bar, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self._bar.currentChanged.connect(self._select)
        self._bar.tabCloseRequested.connect(self.tabCloseRequested)
        self._bar.tabMoved.connect(self._move)
        self._bar.heightChanged.connect(self._sync_header)
        self._strip.installEventFilter(self)
        for key, direction in (('Ctrl+Tab', 1), ('Ctrl+Shift+Tab', -1)):
            shortcut = QShortcut(key, self)
            shortcut.activated.connect(lambda direction=direction: self._cycle_tab(direction))

    def _cycle_tab(self, direction):
        if self.count():
            self.setCurrentIndex((self.currentIndex() + direction) % self.count())

    def eventFilter(self, watched, event):
        if watched is self._strip and event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.FontChange):
            self._sync_header()
        return super().eventFilter(watched, event)

    def _sync_header(self):
        tab = self.currentWidget()
        if tab is not None:
            height = max(self._bar.sizeHint().height(), self._corner.sizeHint().height() if self._corner else 0,
                         tab.map_heading.minimumSizeHint().height(), tab.outline_heading.minimumSizeHint().height())
            tab.set_header_height(height)

    def _select(self, index):
        self._stack.setCurrentIndex(index)
        tab = self._stack.widget(index)
        if tab is not None:
            tab.editor_header_layout.addWidget(self._strip)
            self._strip.show()
            self._sync_header()
        self.currentChanged.emit(index)

    def _move(self, before, after):
        widget = self._stack.widget(before)
        self._stack.removeWidget(widget)
        self._stack.insertWidget(after, widget)
        self._select(self._bar.currentIndex())

    def addTab(self, widget, label):
        self._stack.addWidget(widget)
        return self._bar.addTab(label)

    def removeTab(self, index):
        # Detach shared navigation before the removed document is deleted.
        self._strip.setParent(self)
        self._strip.hide()
        self._stack.removeWidget(self._stack.widget(index))
        self._bar.removeTab(index)
        self._select(self._bar.currentIndex())

    def setCornerWidget(self, widget, corner):
        self._corner = widget
        widget.setParent(self._bar)
        widget.show()
        self._bar._reflow()
        self._sync_header()

    def cornerWidget(self, corner):
        return self._corner if corner == Qt.Corner.TopLeftCorner else None

    def tabBar(self): return self._bar
    def count(self): return self._stack.count()
    def widget(self, index): return self._stack.widget(index)
    def indexOf(self, widget): return self._stack.indexOf(widget)
    def currentWidget(self): return self._stack.currentWidget()
    def currentIndex(self): return self._bar.currentIndex()
    def setCurrentIndex(self, index): self._bar.setCurrentIndex(index)
    def setCurrentWidget(self, widget): self.setCurrentIndex(self.indexOf(widget))
    def setTabText(self, index, text): self._bar.setTabText(index, text)
    def tabText(self, index): return self._bar.tabText(index)
    def setTabToolTip(self, index, text): self._bar.setTabToolTip(index, text)
    def tabToolTip(self, index): return self._bar.tabToolTip(index)
    def setTabsClosable(self, enabled): self._bar.setTabsClosable(enabled)
    def setMovable(self, enabled): self._bar.setMovable(enabled)


class _ViewMenu(QMenu):
    """Let several view choices change without dismissing the popup."""

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt API
        if not self.rect().contains(event.position().toPoint()):
            # Do not forward hover to the menu bar and switch menus merely
            # because the pointer left View. An outside click still dismisses.
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            action = self.actionAt(event.position().toPoint())
            if action is not None and action.isEnabled() and action.isCheckable():
                action.trigger()
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            action = self.activeAction()
            if action is not None and action.isEnabled() and action.isCheckable():
                action.trigger()
                event.accept()
                return
        super().keyPressEvent(event)


class StudioWindow(QMainWindow):
    def __init__(self, arcgrav_version: str, *, background: bool = True, scheme_store=None, user_state=None, vocabulary_store=None) -> None:
        super().__init__()
        self.user_state = user_state if user_state is not None else UserState(QSettings("ArchitecturalGravity", "AgStudio"))
        self._startup_layout_enabled = False
        self.session_store = SessionStore(self.user_state.settings)
        self.vocabulary_store = (vocabulary_store if vocabulary_store is not None
                                 else SpellingVocabularyStore(self.user_state.settings))
        self._session_enabled = False
        self._session_timer = QTimer(self)
        self._session_timer.setSingleShot(True)
        self._session_timer.setInterval(500)
        self._session_timer.timeout.connect(self._checkpoint_session)
        self.version = arcgrav_version
        self.scheme_store = scheme_store if scheme_store is not None else SchemeStore()
        self.scheme_name, self.color_scheme, self.scheme_error = self.scheme_store.selected()
        self.background = background
        self.setFont(QFont("sans-serif", 11))
        self.tabs = _DocumentTabs()
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(self._update_status)
        self.tabs.currentChanged.connect(self._schedule_session)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(application_icon())
        self.tabs.setMovable(True)
        self.setStyleSheet(STUDIO_STYLE)
        file_menu: QMenu = self.menuBar().addMenu("File")
        self.new_action = file_menu.addAction("New", self.new_document, "Ctrl+N")
        self.open_action = file_menu.addAction("Open…", self._open_dialog, "Ctrl+O")
        self.save_action = file_menu.addAction("Save", self._save_current, "Ctrl+S")
        file_menu.addAction("Save As…", lambda: self._save_current(True), "Ctrl+Shift+S")
        file_menu.addSeparator()
        file_menu.addAction("Close tab", lambda: self._close_tab(self.tabs.currentIndex()))
        edit_menu: QMenu = self.menuBar().addMenu("Edit")
        self.undo_action = edit_menu.addAction("Undo", lambda: self.current().editor.undo() if self.current() else None,
                                             "Ctrl+Z")
        self.redo_action = edit_menu.addAction("Redo", lambda: self.current().editor.redo() if self.current() else None,
                                             "Ctrl+Y")
        edit_menu.addSeparator()
        edit_menu.addAction('Find…', lambda: self.current().find_bar.open() if self.current() else None, 'Ctrl+F')
        edit_menu.addAction('Find Next', lambda: self.current().find_bar.find() if self.current() else None, 'F3')
        edit_menu.addAction('Find Previous', lambda: self.current().find_bar.find(True) if self.current() else None, 'Shift+F3')
        edit_menu.addSeparator()
        edit_menu.addAction('Spelling vocabulary…', self._edit_spelling_vocabulary)
        self.view_menu = _ViewMenu("View", self)
        self.menuBar().addMenu(self.view_menu)
        self.panel_actions = {}
        for name, label in (
                ('side_panel', 'Outline'),
                ('error_list', 'Finding List'),
                ('document_map', 'Infer Map')):
            action = self.view_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.user_state.panels[name])
            action.toggled.connect(lambda visible, name=name: self._set_panel_visibility(name, visible))
            self.panel_actions[name] = action
        self.view_menu.addSeparator()
        self.inference_menu = self.view_menu.addMenu('Inference mode')
        self.inference_mode_group = QActionGroup(self)
        self.inference_mode_group.setExclusive(True)
        self.inference_mode_actions = {}
        for mode, label in MODE_LABELS.items():
            action = self.inference_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == self.user_state.inference_mode)
            action.setToolTip(MODE_HELP[mode])
            action.setStatusTip(MODE_HELP[mode])
            self.inference_mode_group.addAction(action)
            action.triggered.connect(lambda checked=False, mode=mode: self._set_inference_mode(mode))
            self.inference_mode_actions[mode] = action
        self.inference_menu.setToolTipsVisible(True)
        export_menu: QMenu = self.menuBar().addMenu("Export")
        self.export_action = export_menu.addAction("Code Image", self._export_current_image)
        self.menuBar().addAction("Color Scheme", self._edit_color_scheme)
        for action, icon in ((self.open_action, QStyle.StandardPixmap.SP_DirOpenIcon),
                             (self.save_action, QStyle.StandardPixmap.SP_DialogSaveButton)):
            action.setIcon(self.style().standardIcon(icon))
        new_button = QToolButton()
        new_button.setText("+")
        new_button.setStyleSheet('QToolButton { padding: 0px 10px; }')
        new_button.setAccessibleName("New document")
        new_button.setToolTip("New document (Ctrl+N)")
        new_button.clicked.connect(self.new_document)
        self.tabs.setCornerWidget(new_button, Qt.Corner.TopLeftCorner)
        self.new_document()
        if self.vocabulary_store.error:
            self.statusBar().showMessage('Could not load user spelling vocabulary: ' + self.vocabulary_store.error, 15000)
        if self.scheme_error:
            self.statusBar().showMessage("Could not load selected color scheme; using Default: " + self.scheme_error, 15000)

    def initialize_startup(self, file: Path | None = None, *, settings=None) -> None:
        """Restore open documents, then select explicit input or the first-run tour.

        Call once after constructing the window. Never replace an edited tab.
        New documents remain blank; the tutorial keeps its actual file path.
        """
        self._startup_layout_enabled = True
        layout = self.user_state.layout
        self.resize(*layout['window_size'])
        self.setWindowState(Qt.WindowState.WindowMaximized if layout['maximized'] else Qt.WindowState.WindowNoState)
        # Restore ratios after the window and its tutorial tab have been laid out.
        QTimer.singleShot(0, self._restore_current_layout)
        if self._session_enabled:
            if file is not None:
                self._open_startup_file(file)
            return
        initial = self.current()
        pristine = (self.tabs.count() == 1 and initial is not None
                    and not initial.path and not initial.source and not initial.dirty)
        restored = []
        active_tab = None
        saved = self.session_store.load() if pristine else {'tabs': [], 'active': None}
        for item_index, item in enumerate(saved['tabs']):
            try:
                tab = self._restore_session_tab(item)
            except (OSError, UnicodeError, ValueError, RuntimeError):
                continue
            if not any(existing is tab for existing, _ in restored):
                restored.append((tab, item))
                if item_index == saved['active']:
                    active_tab = tab
        if restored:
            self._close_tab(self.tabs.indexOf(initial))
            active = active_tab or restored[0][0]
            self.tabs.setCurrentWidget(active)
        if file is not None:
            self._open_startup_file(file)
            if pristine and self.tabs.indexOf(initial) >= 0 and self.tabs.count() > 1:
                self._close_tab(self.tabs.indexOf(initial))
        elif not restored and pristine:
            settings = settings if settings is not None else QSettings("ArchitecturalGravity", "AgStudio")
            if not settings.value("startup/helloWorldShown", False, type=bool):
                example = self.open_file(Path(__file__).resolve().parents[1] / "examples" / "HelloWorld.arc", remember_directory=False)
                self._close_tab(self.tabs.indexOf(initial))
                self.tabs.setCurrentWidget(example)
                settings.setValue("startup/helloWorldShown", True)
                settings.sync()
        # Geometry must settle before restoring scrollbars. Inactive tabs defer
        # their scroll restoration until first shown at their actual size.
        for tab, item in restored:
            tab._session_view = item
        self._session_enabled = True
        QTimer.singleShot(0, self._finish_session_startup)

    def _restore_session_tab(self, item):
        if 'source' not in item:  # Saved-file metadata from earlier versions.
            return self.open_file(Path(item['path']), remember_directory=False)
        path = Path(item['path']) if item['path'] else None
        tab = DocumentTab(self.version, item['source'], path, item['encoding'],
                          background=self.background,
                          map_enabled=self.user_state.panels['document_map'],
                          inference_mode=self.user_state.inference_mode)
        dirty = item['dirty']
        if path is not None:
            try:
                # Preserve the snapshot if the file changed or disappeared while
                # closed. Mark it unsaved; never overwrite the external file.
                dirty = dirty or path.read_bytes() != item['source'].encode(item['encoding'])
            except (OSError, UnicodeError):
                dirty = True
        tab.dirty = dirty
        tab.editor.document().setModified(dirty)
        return self._add_tab(tab)

    def _open_startup_file(self, file):
        try:
            self.open_file(file)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc))

    def _finish_session_startup(self):
        if not self._session_enabled:
            return
        self._restore_session_view()
        self._checkpoint_session()

    def _restore_session_view(self):
        tab = self.current()
        item = getattr(tab, '_session_view', None)
        if item is None:
            return
        del tab._session_view
        if 'layout' in item:
            self._apply_tab_layout(tab, item['layout'])
        cursor = tab.editor.textCursor()
        maximum = tab.editor.document().characterCount() - 1
        cursor.setPosition(min(item['anchor'], maximum))
        cursor.setPosition(min(item['position'], maximum), QTextCursor.MoveMode.KeepAnchor)
        tab.editor.setTextCursor(cursor)
        tab.editor.verticalScrollBar().setValue(item['vertical'])
        tab.editor.horizontalScrollBar().setValue(item['horizontal'])

    def _schedule_session(self, *_args):
        if self._session_enabled:
            # A bounded checkpoint, not a trailing debounce: continuous movement
            # cannot postpone persistence indefinitely.
            if not self._session_timer.isActive():
                self._session_timer.start()
            if getattr(self.current(), '_session_view', None) is not None:
                QTimer.singleShot(0, self._restore_session_view)

    def _checkpoint_session(self):
        if not self._session_enabled:
            return True
        tabs = []
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            cursor = tab.editor.textCursor()
            view = getattr(tab, '_session_view', None)
            item = dict(view) if view is not None else {
                'anchor': cursor.anchor(), 'position': cursor.position(),
                'vertical': tab.editor.verticalScrollBar().value(),
                'horizontal': tab.editor.horizontalScrollBar().value(),
            }
            if view is None:
                item['layout'] = self._tab_layout(tab)
            item.update(path=str(tab.path.resolve()) if tab.path else None,
                        source=tab.source, dirty=tab.dirty, encoding=tab.encoding)
            tabs.append(item)
        saved = self.session_store.save({'version': 2, 'tabs': tabs,
                                         'active': self.tabs.currentIndex()})
        if not saved:
            self.statusBar().showMessage('Could not save session: ' + self.session_store.error, 15000)
        return saved

    def _restore_current_layout(self):
        tab = self.current()
        if tab is not None:
            view = getattr(tab, '_session_view', {})
            self._apply_tab_layout(tab, view.get('layout', self.user_state.layout))

    def _apply_tab_layout(self, tab, layout):
        if not tab.diagnostic_list.isHidden():
            tab.split.setSizes(layout['finding_sizes'])
        if tab.diagnostic_list.isHidden() != layout['finding_collapsed']:
            tab._toggle_diagnostics()
        # Keep the expanded dimensions even when this tab starts collapsed.
        tab._diagnostics_split_sizes = layout['finding_sizes'].copy()
        tab.editor_split.setSizes(layout['editor_outline_sizes'])
        tab.editor_map_split.setSizes(layout['editor_map_sizes'])
        tab._editor_map_sizes = layout['editor_map_sizes'].copy()
        tab.document_map.rebuild()
        tab.document_map._fit = layout['map_fit']
        tab.document_map.scale = layout['map_scale']
        tab.document_map._clamp_scale()
        tab.document_map.update()

    def _tab_layout(self, tab):
        return {
            'editor_map_sizes': (tab.editor_map_split.sizes() if not tab.document_map.isHidden()
                                 else getattr(tab, '_editor_map_sizes', self.user_state.layout['editor_map_sizes'])),
            'editor_outline_sizes': (tab.editor_split.sizes() if not tab.side_panel.isHidden()
                                     else self.user_state.layout['editor_outline_sizes']),
            'finding_sizes': (getattr(tab, '_diagnostics_split_sizes', self.user_state.layout['finding_sizes'])
                              if tab.diagnostic_list.isHidden() or tab.diagnostics_panel.isHidden()
                              else tab.split.sizes()),
            'finding_collapsed': tab.diagnostic_list.isHidden(),
            'map_fit': tab.document_map._fit,
            'map_scale': 1.0 if tab.document_map._fit else tab.document_map.scale,
        }

    def _save_current_layout(self):
        tab = self.current()
        if tab is None:
            return
        normal = self.normalGeometry().size() if self.isMaximized() else self.size()
        self.user_state.save_layout({
            'window_size': [normal.width(), normal.height()],
            'maximized': self.isMaximized(),
            **self._tab_layout(tab),
        })

    def _apply_spelling_vocabulary(self, tab):
        words = self.vocabulary_store.words
        if tab.configuration.get('spelling_words', []) != words:
            tab.set_analysis_context(tab.version, profile=tab.profile,
                                     configuration={**tab.configuration, 'spelling_words': words})

    def _refresh_spelling_vocabulary(self):
        self.vocabulary_store.reload()
        for index in range(self.tabs.count()):
            self._apply_spelling_vocabulary(self.tabs.widget(index))
        if self.vocabulary_store.error:
            self.statusBar().showMessage('Could not load user spelling vocabulary: ' + self.vocabulary_store.error, 15000)

    def _broadcast_spelling_vocabulary(self):
        self._refresh_spelling_vocabulary()
        for window in QApplication.topLevelWidgets():
            if (isinstance(window, StudioWindow) and window is not self
                    and self.vocabulary_store.path is not None
                    and window.vocabulary_store.path == self.vocabulary_store.path):
                window._refresh_spelling_vocabulary()

    def _add_spelling_word(self, scope, word):
        if not self.vocabulary_store.update(add=word, scope=scope):
            QMessageBox.warning(self, 'Could not save spelling vocabulary', self.vocabulary_store.error)
            return
        self._broadcast_spelling_vocabulary()

    def _edit_spelling_vocabulary(self):
        from .spelling_vocabulary_dialog import SpellingVocabularyDialog
        self._refresh_spelling_vocabulary()
        if self.vocabulary_store.error:
            QMessageBox.warning(self, 'Could not load spelling vocabulary', self.vocabulary_store.error)
            return
        dialog = SpellingVocabularyDialog(self.vocabulary_store, self)
        if dialog.exec():
            self._broadcast_spelling_vocabulary()
        dialog.deleteLater()

    def _set_inference_mode(self, mode):
        mode = normalize_graph_mode(mode)
        self.user_state.set_inference_mode(mode)
        for key, action in self.inference_mode_actions.items():
            with QSignalBlocker(action):
                action.setChecked(key == mode)
        for index in range(self.tabs.count()):
            self.tabs.widget(index).set_inference_mode(mode)

    def _edit_color_scheme(self):
        from .color_scheme_dialog import ColorSchemeDialog
        ColorSchemeDialog(self).exec()

    def apply_color_scheme(self, scheme, name='Custom'):
        self.color_scheme = validate_scheme(scheme)
        self.scheme_name = name
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            tab.editor.apply_color_scheme(self.color_scheme)
            tab.highlighter.apply_color_scheme(self.color_scheme)
            tab.apply_outline_scheme()

    def _show_diagnostics(self) -> None:
        self._set_panel_visibility('error_list', True)

    def _show_side_panel(self) -> None:
        self._set_panel_visibility('side_panel', True)
        if self.current():
            self.current().ensure_outline()
            self.current()._sync_context()

    def _set_panel_visibility(self, name, visible):
        self.user_state.set_panel(name, visible)
        with QSignalBlocker(self.panel_actions[name]):
            self.panel_actions[name].setChecked(visible)
        for index in range(self.tabs.count()):
            self._apply_panel_visibility(self.tabs.widget(index))
        if name == 'side_panel' and visible and self.current():
            self.current().ensure_outline()
            self.current()._sync_context()

    def _apply_panel_visibility(self, tab):
        if not tab.document_map.isHidden() and not self.user_state.panels['document_map']:
            tab._editor_map_sizes = tab.editor_map_split.sizes()
        tab.side_panel.setVisible(self.user_state.panels['side_panel'])
        tab.diagnostics_panel.setVisible(self.user_state.panels['error_list'])
        tab.set_map_enabled(self.user_state.panels['document_map'])

    def current(self) -> DocumentTab | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, DocumentTab) else None

    def _add_tab(self, tab: DocumentTab) -> DocumentTab:
        if tab.graph.mode != self.user_state.inference_mode:
            tab.set_inference_mode(self.user_state.inference_mode)
        tab.editor.apply_color_scheme(self.color_scheme)
        tab.highlighter.apply_color_scheme(self.color_scheme)
        tab.apply_outline_scheme()
        tab.inferenceModeRequested.connect(self._set_inference_mode)
        tab.editor.vocabulary_enabled = True
        tab.editor.spellingVocabularyRequested.connect(self._add_spelling_word)
        self._apply_spelling_vocabulary(tab)
        self._apply_panel_visibility(tab)
        self.tabs.addTab(tab, tab.path.name if tab.path else "Untitled.arc")
        self.tabs.setCurrentWidget(tab)
        if self._startup_layout_enabled:
            QTimer.singleShot(0, lambda: self._apply_tab_layout(
                tab, getattr(tab, '_session_view', {}).get('layout', self.user_state.layout)))
        for splitter in (tab.split, tab.editor_split, tab.editor_map_split):
            splitter.splitterMoved.connect(self._schedule_session)
        tab.diagnostics_toggle.clicked.connect(self._schedule_session)
        tab.editor.textChanged.connect(self._update_status)
        tab.editor.textChanged.connect(self._schedule_session)
        tab.editor.selectionChanged.connect(self._schedule_session)
        tab.editor.verticalScrollBar().valueChanged.connect(self._schedule_session)
        tab.editor.horizontalScrollBar().valueChanged.connect(self._schedule_session)
        tab.editor.undoAvailable.connect(self._update_status)
        tab.editor.redoAvailable.connect(self._update_status)
        tab.editor.cursorPositionChanged.connect(self._update_status)
        tab.editor.cursorPositionChanged.connect(self._schedule_session)
        self._update_status()
        return tab

    def new_document(self) -> DocumentTab:
        return self._add_tab(DocumentTab(self.version, background=self.background,
                                         map_enabled=self.user_state.panels['document_map'],
                                         inference_mode=self.user_state.inference_mode))

    def open_file(self, path: Path, *, remember_directory: bool = True) -> DocumentTab:
        if path.suffix.lower() not in {".arc", ".txt"}:
            raise ValueError("open source must be an .arc or .txt file")
        path = path.resolve()
        for index in range(self.tabs.count()):
            existing = self.tabs.widget(index)
            if isinstance(existing, DocumentTab) and existing.path and existing.path.resolve() == path:
                self.tabs.setCurrentWidget(existing)
                if remember_directory:
                    self.user_state.remember_file_directory(path.parent)
                return existing
        data = path.read_bytes()
        encoding = "utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8"
        source = data.decode(encoding)
        tab = self._add_tab(DocumentTab(self.version, source, path, encoding,
                                         background=self.background,
                                         map_enabled=self.user_state.panels['document_map'],
                                         inference_mode=self.user_state.inference_mode))

        if remember_directory:
            self.user_state.remember_file_directory(path.parent)
        return tab

    def _open_directory(self) -> Path:
        directory = Path(self.user_state.file_directory) if self.user_state.file_directory else None
        if directory is not None and directory.is_dir():
            return directory
        return Path(__file__).resolve().parents[1] / "examples"

    def _open_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Open ArcGrav source", str(self._open_directory()), OPEN_FILTERS)
        if name:
            try:
                self.open_file(Path(name))
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.critical(self, "Open failed", str(exc))

    def _export_current_image(self) -> None:
        tab = self.current()
        if tab is None:
            return
        dialog = ExportDialog(self)
        if not dialog.exec():
            return
        options = dialog.options()
        suffix = '.png' if options.format == 'PNG' else '.jpg'
        initial = tab.path.with_suffix(suffix) if tab.path else Path('Untitled' + suffix)
        file_filter = 'PNG (*.png)' if options.format == 'PNG' else 'JPG (*.jpg *.jpeg)'
        name, _ = QFileDialog.getSaveFileName(
            self, 'Export Code Image', str(initial), file_filter,
            options=QFileDialog.Option.DontConfirmOverwrite)
        if not name:
            return
        path = export_path(name, options)
        if path.exists():
            answer = QMessageBox.question(
                self, 'Replace image?', f'{path} already exists. Replace it?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            image = render_document(tab.editor, options)
            write_image(image, path, options)
        except (OSError, ValueError, MemoryError) as exc:
            QMessageBox.critical(self, 'Export failed', str(exc))
            return
        self.statusBar().showMessage(f'Exported {path.name} ({image.width} × {image.height})', 7000)

    def _save_current(self, save_as: bool = False) -> None:
        tab = self.current()
        if tab is not None:
            self._save_tab(tab, save_as)

    def _save_tab(self, tab: DocumentTab, save_as: bool = False) -> bool:
        path = None if save_as else tab.path
        try:
            if path is None:
                initial_filter = TEXT_FILTER if tab.path and tab.path.suffix.lower() == ".txt" else ARC_FILTER
                name, selected_filter = QFileDialog.getSaveFileName(
                    self, "Save ArcGrav source", str(tab.path) if tab.path else "",
                    SAVE_FILTERS, initial_filter)
                if not name:
                    return False
                requested = Path(name)
                path = _save_path(requested, selected_filter)
                # The native dialog confirms explicit filenames. If we added a
                # suffix, confirm the actual destination before overwriting it.
                if path != requested and path.exists():
                    answer = QMessageBox.question(
                        self, "Replace file?", f"{path} already exists. Replace it?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No)
                    if answer != QMessageBox.StandardButton.Yes:
                        return False
            path = tab.save(path)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self.user_state.remember_file_directory(path.resolve().parent)
        self.tabs.setTabText(self.tabs.indexOf(tab), path.name)
        self._update_status()
        self._schedule_session()
        return True

    def _close_tab(self, index: int) -> None:
        if index < 0 or index >= self.tabs.count():
            return
        tab = self.tabs.widget(index)
        if isinstance(tab, DocumentTab) and tab.dirty:
            name = tab.path.name if tab.path else "Untitled.arc"
            dialog = QMessageBox(QMessageBox.Icon.Question, "Unsaved changes",
                                f"Do you want to save changes to ‘{name}’ before closing?",
                                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                | QMessageBox.StandardButton.Cancel, self)
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.button(QMessageBox.StandardButton.Discard).setText("Don't Save")
            dialog.setDefaultButton(QMessageBox.StandardButton.Save)
            dialog.setEscapeButton(QMessageBox.StandardButton.Cancel)
            answer = dialog.exec()
            dialog.deleteLater()
            if answer == QMessageBox.StandardButton.Save:
                if not self._save_tab(tab):
                    return
            elif answer != QMessageBox.StandardButton.Discard:
                return
        self.tabs.removeTab(index)
        tab.dispose_analysis()
        tab.deleteLater()
        if not self.tabs.count():
            self.new_document()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not self._checkpoint_session():
            QMessageBox.critical(self, "Could not retain session",
                                 "AgStudio could not retain your open documents. "
                                 "The window will remain open so your work is not lost.\n\n"
                                 + str(self.session_store.error))
            event.ignore()
            return
        self._session_timer.stop()
        self._session_enabled = False
        for index in range(self.tabs.count()):
            self.tabs.widget(index).dispose_analysis()
        if self._startup_layout_enabled:
            self._save_current_layout()
        event.accept()

    def _update_status(self, *_args) -> None:
        tab = self.current()
        if tab:
            for index in range(self.tabs.count()):
                document_tab = self.tabs.widget(index)
                label = document_tab.path.name if document_tab.path else "Untitled.arc"
                self.tabs.setTabText(index, label + (" *" if document_tab.dirty else ""))
                self.tabs.setTabToolTip(index, str(document_tab.path) if document_tab.path else "Unsaved document")
            cursor = tab.editor.textCursor()
            line, column = tab.editor.source_position(cursor.position())
            self.statusBar().showMessage(f"{tab.status_text()} · Ln {line}, Col {column}")
            self.setWindowTitle(f"{WINDOW_TITLE} - {tab.path.name if tab.path else 'Untitled.arc'}{' *' if tab.dirty else ''}")
        # currentChanged can fire before the actions exist during initialization.
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(bool(tab and tab.editor.document().isUndoAvailable()))
            self.redo_action.setEnabled(bool(tab and tab.editor.document().isRedoAvailable()))


STUDIO_STYLE = """
QWidget { font-size: 14px; }
QPlainTextEdit#sourceEditor { font-size: 16px; }
QMainWindow, QStatusBar { background: #eaf0f6; color: #24394d; }
QMenuBar { background: #f4f7fa; color: #24394d; border-bottom: 1px solid #cad6e2; }
QMenuBar::item { padding: 7px 12px; }
QToolButton { padding: 5px 10px; border: 1px solid transparent; border-radius: 4px; }
QToolButton:hover { background: #e0eaf5; border-color: #b4c9df; }
QTabBar::tab { background: #e4ecf4; padding: 3px 18px; border: 1px solid #cad6e2; color: #425c74; }
QTabBar::tab:selected { background: white; color: #172d43; border-bottom-color: white; }
QToolButton#documentTab { background: #e6eef5; color: #456078; border: 1px solid #cad6e2; padding: 0px 24px 0px 10px; }
QToolButton#documentTab:checked { background: white; color: #24394d; }
QToolButton#documentTab:hover { background: #f6faff; }
QPlainTextEdit, QTreeWidget { color: #202f3e; border: 0; selection-background-color: #286eb7; selection-color: white; }
QTreeWidget { alternate-background-color: #f6f9fc; }
QTreeWidget::item { padding: 5px 7px; }
QTreeWidget#contextOutline::item { padding: 2px 5px; }
QTreeWidget#contextOutline QHeaderView::section,
QTreeWidget#contextCorrelations QHeaderView::section { padding: 0px 12px; background: #eaf0f6; color: #24394d; }
QToolButton#inferenceEditToggle, QLabel#outlineTitle, QLabel#correlationsTitle { color: #000000; font-weight: normal; }
QHeaderView::section { background: #f5f8fb; color: #354e66; padding: 7px; border: 0; border-right: 1px solid #d8e2ec; border-bottom: 1px solid #cad6e2; }
QTreeWidget#diagnosticTable QHeaderView::section { padding: 1px 7px; }
QSplitter::handle { background: #dce5ee; }
QSplitter::handle:vertical { height: 6px; }
QSplitter::handle:horizontal { width: 6px; }
QWidget#panelHeading QToolButton { padding: 0px 6px; }
QWidget#panelHeading { background: #eaf0f6; border-bottom: 1px solid #cad6e2; }
QStatusBar { border-top: 1px solid #cad6e2; padding: 0px; }
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local AgStudio .arc and .txt editor")
    parser.add_argument("--arcgrav-version", required=True,
                        help="explicit version label; does not imply normative admission")
    parser.add_argument("file", nargs="?", type=Path)
    args = parser.parse_args(argv)
    set_windows_app_id()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setWindowIcon(application_icon())
    try:
        window = StudioWindow(args.arcgrav_version)
    except (OSError, ValueError) as error:
        QMessageBox.critical(None, 'Could not start AgStudio', str(error))
        return 1
    window.initialize_startup(args.file)
    window.show()
    return app.exec()
