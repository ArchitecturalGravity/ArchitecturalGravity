"""Per-tab literal find/replace with native document boundaries and undo."""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QTextCursor, QTextDocument, QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox, QPushButton, QToolButton, QLabel, QLayout

from .compact_arrow import CompactArrowButton


class FindBar(QWidget):
    def __init__(self, tab):
        super().__init__(tab.editor.viewport())
        self.tab = tab
        self.editor = tab.editor
        self.setObjectName('editorFindOverlay')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet('QWidget#editorFindOverlay { background: #edf2f7; border: 1px solid #8d9aa8; border-radius: 4px; }'
                           'QWidget#editorFindOverlay QLineEdit { min-height: 22px; }'
                           'QWidget#editorFindOverlay QToolButton { padding: 0px; }')
        self._positioning = False
        self._avoid_selection = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(3)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('Find')
        self.query.setAccessibleName('Find text')
        self.case = QCheckBox('Match case')
        self.word = QCheckBox('Whole word')
        self.previous = CompactArrowButton()
        self.previous.setArrowType(Qt.ArrowType.UpArrow)
        self.previous.setAccessibleName('Previous match')
        self.previous.setToolTip('Previous match (Shift+Enter)')
        self.next = CompactArrowButton()
        self.next.setArrowType(Qt.ArrowType.DownArrow)
        self.next.setAccessibleName('Next match')
        self.next.setToolTip('Next match (Enter)')
        self.disclosure = CompactArrowButton()
        self.disclosure.setAccessibleName('Show Replace')
        self.disclosure.setToolTip('Show Replace')
        self.disclosure.setCheckable(True)
        self.disclosure.setArrowType(Qt.ArrowType.RightArrow)
        self.disclosure.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.feedback = QLabel()
        self.feedback.setAccessibleName('Search status')
        close = QToolButton()
        close.setText('×')
        close.setAccessibleName('Close Find')
        row.setSpacing(3)
        self.query.setMinimumWidth(0)
        for widget in (self.disclosure, self.query, self.previous, self.next, close):
            row.addWidget(widget, 1 if widget is self.query else 0)
        for widget in (self.disclosure, self.previous, self.next, close):
            widget.setFixedSize(23, 24)
        layout.addLayout(row)
        options = self.options = QHBoxLayout()
        options.setSpacing(8)
        self.case.setAccessibleName('Match case')
        self.word.setAccessibleName('Whole word')
        for widget in (self.case, self.word):
            options.addWidget(widget)
        options.addStretch()
        self.feedback.setMinimumWidth(0)
        options.addWidget(self.feedback)
        layout.addLayout(options)
        self.status_row = QWidget()
        self.status_layout = QHBoxLayout(self.status_row)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.addStretch()
        layout.addWidget(self.status_row)
        self.status_row.hide()
        self.replace_row = QWidget()
        replacements = QHBoxLayout(self.replace_row)
        replacements.setContentsMargins(0, 0, 0, 0)
        self.replacement = QLineEdit()
        self.replacement.setPlaceholderText('Replace with')
        self.replacement.setAccessibleName('Replacement text')
        self.replacement.setMinimumWidth(0)
        self.replace = QPushButton('Replace')
        self.replace_all = QPushButton('Replace All')
        self.replace.setAccessibleName('Replace current match')
        self.replace_all.setAccessibleName('Replace All')
        self.replace.setToolTip('Replace current match')
        self.replace_all.setToolTip('Replace All')
        replacements.setSpacing(3)
        for widget in (self.replacement, self.replace, self.replace_all):
            replacements.addWidget(widget, 1 if widget is self.replacement else 0)
        layout.addWidget(self.replace_row)
        self.replace_row.hide()
        self.disclosure.toggled.connect(self._disclose)
        close.clicked.connect(self.dismiss)
        self.next.clicked.connect(lambda: self.find())
        self.previous.clicked.connect(lambda: self.find(True))
        self.query.returnPressed.connect(lambda: self.find())
        self.replace.clicked.connect(self.replace_one)
        self.replace_all.clicked.connect(self.replace_everywhere)
        self.editor.textChanged.connect(self._reset)
        self.query.textChanged.connect(self._reset)
        self.case.toggled.connect(self._reset)
        self.word.toggled.connect(self._reset)
        self.query.installEventFilter(self)
        for key, action in (('Escape', self.dismiss),):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)
        self.editor.viewport().installEventFilter(self)
        self.editor.verticalScrollBar().valueChanged.connect(lambda _: self._position())
        self.editor.horizontalScrollBar().valueChanged.connect(lambda _: self._position())
        self.editor.cursorPositionChanged.connect(self._position)
        self._reset()
        self.hide()

    def keyPressEvent(self, event):
        # Unhandled line-edit keys (notably Return) must not bubble through the
        # viewport into QPlainTextEdit and modify the document underneath.
        event.accept()

    def keyReleaseEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def active(self):
        window = self.tab.window()
        return not hasattr(window, 'current') or window.current() is self.tab

    def open(self):
        if not self.active():
            return
        selection = self.editor.textCursor().selectedText()
        if selection and '\u2029' not in selection:
            self.query.setText(selection)
        self.show()
        self._position()
        self.raise_()
        self.query.setFocus()
        self.query.selectAll()

    def eventFilter(self, watched, event):
        if (watched is self.query and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.find(True)
            return True
        if watched is self.editor.viewport() and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._position()
        return super().eventFilter(watched, event)

    def _position(self):
        if self.isHidden() or self._positioning:
            return
        self._positioning = True
        try:
            viewport = self.editor.viewport()
            width = max(0, min(440, viewport.width() - 12))
            compact = width < 380
            narrow = width < 300
            if narrow and self.feedback.parentWidget() is not self.status_row:
                self.options.removeWidget(self.feedback)
                self.status_layout.addWidget(self.feedback)
            elif not narrow and self.feedback.parentWidget() is self.status_row:
                self.status_layout.removeWidget(self.feedback)
                self.options.addWidget(self.feedback)
            self.status_row.setVisible(narrow)
            self.feedback.show()
            self.case.setText('Aa' if compact else 'Match case')
            self.word.setText('Word' if compact else 'Whole word')
            self.case.setToolTip('Match case' if compact else '')
            self.word.setToolTip('Whole word' if compact else '')
            self.replace.setText('↵' if compact else 'Replace')
            self.replace_all.setText('All' if compact else 'Replace All')
            for button in (self.replace, self.replace_all):
                button.setMinimumWidth(0)
                button.setMaximumWidth(32 if compact else 90)
            self.setFixedWidth(width)
            self.layout().activate()
            height = min(self.layout().sizeHint().height(), max(0, viewport.height() - 12))
            x, y = max(0, viewport.width() - width - 6), 6
            if self._avoid_selection:
                cursor = self.editor.cursorRect()
                if cursor.right() >= x and cursor.top() < y + height and cursor.bottom() >= y:
                    # Near the first line, scrolling cannot reveal text above the
                    # document. Shift the panel just below that match when it fits.
                    if cursor.bottom() + 6 + height <= viewport.height() - 6:
                        y = cursor.bottom() + 6
            self.setGeometry(x, y, width, height)
            self.raise_()
        finally:
            self._positioning = False

    def dismiss(self):
        self.hide()
        if self.active():
            self.editor.setFocus()

    def _disclose(self, checked):
        self.replace_row.setVisible(checked)
        self.disclosure.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.disclosure.setAccessibleName('Hide Replace' if checked else 'Show Replace')
        self.disclosure.setToolTip(self.disclosure.accessibleName())
        self._position()

    def _reset(self, *_):
        self._avoid_selection = False
        self._match_cache = None
        self.feedback.clear()
        self._position()
        for button in (self.next, self.previous, self.replace, self.replace_all):
            button.setEnabled(bool(self.query.text()))

    def flags(self, backwards=False):
        flags = QTextDocument.FindFlag(0)
        if self.case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.word.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        if backwards:
            flags |= QTextDocument.FindFlag.FindBackward
        return flags

    def _matches(self):
        key = (self.editor.document().revision(), self.query.text(), self.case.isChecked(), self.word.isChecked())
        if self._match_cache is None or self._match_cache[0] != key:
            positions = []
            cursor = QTextCursor(self.editor.document())
            while True:
                cursor = self.editor.document().find(self.query.text(), cursor, self.flags())
                if cursor.isNull():
                    break
                positions.append((cursor.selectionStart(), cursor.selectionEnd()))
                cursor.setPosition(cursor.selectionStart() + 1)
            self._match_cache = key, positions
        return self._match_cache[1]

    def find(self, backwards=False):
        if not self.active() or not self.query.text():
            return False
        document = self.editor.document()
        match = document.find(self.query.text(), self.editor.textCursor(), self.flags(backwards))
        wrapped = match.isNull()
        if wrapped:
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.MoveOperation.End if backwards else QTextCursor.MoveOperation.Start)
            match = document.find(self.query.text(), cursor, self.flags(backwards))
        if match.isNull():
            self.feedback.setText('No matches')
            return False
        self._avoid_selection = True
        self.editor.setTextCursor(match)
        self.editor.ensureCursorVisible()
        self._position()
        positions = self._matches()
        number = positions.index((match.selectionStart(), match.selectionEnd())) + 1
        self.feedback.setText(f'{number} of {len(positions)}' + (' · Wrapped' if wrapped else ''))
        self._position()
        return True

    def replace_one(self):
        if not self.active() or not self.query.text() or self.editor.isReadOnly():
            return
        cursor = self.editor.textCursor()
        match = self.editor.document().find(self.query.text(), cursor.selectionStart(), self.flags())
        if (not cursor.hasSelection() or match.isNull() or match.selectionStart() != cursor.selectionStart()
                or match.selectionEnd() != cursor.selectionEnd()):
            self.find()
            return
        cursor.beginEditBlock()
        cursor.insertText(self.replacement.text().replace("\t", "  "))
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.find()

    def replace_everywhere(self):
        if not self.active() or not self.query.text() or self.editor.isReadOnly():
            return
        document = self.editor.document()
        matches = []
        cursor = QTextCursor(document)
        while True:
            cursor = document.find(self.query.text(), cursor, self.flags())
            if cursor.isNull():
                break
            matches.append(QTextCursor(cursor))
        saved = self.editor.textCursor()
        edit = QTextCursor(document)
        edit.beginEditBlock()
        for cursor in reversed(matches):
            cursor.insertText(self.replacement.text().replace("\t", "  "))
        edit.endEditBlock()
        self.editor.setTextCursor(saved)
        self.feedback.setText(f'Replaced {len(matches)} matches' if matches else 'No matches')
