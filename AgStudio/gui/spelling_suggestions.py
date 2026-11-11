"""Qt delivery for explicit editor-word correction requests, never analysis."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QEvent, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from ..shared.spelling_suggestions import SuggestionService


class SuggestionBroker(QObject):
    """Application-owned bridge; process work and native lifetime stay outside Qt."""
    completed = Signal(object)

    def __init__(self, parent=None, *, service=None):
        super().__init__(parent)
        self.service = service if service is not None else SuggestionService()
        self._active = None
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._poll)

    def submit(self, word):
        request = self.service.submit(word)
        self._active = request
        self.timer.start()
        return request

    def cancel(self, request):
        self.service.cancel(request)
        if request == self._active:
            self._active = None
            self.timer.stop()

    def _poll(self):
        outcomes = self.service.poll()
        for outcome in outcomes:
            self.completed.emit(outcome)
        if any(outcome.request_id == self._active for outcome in outcomes):
            self._active = None
            self.timer.stop()

    def close(self):
        self.timer.stop()
        self.service.close()


def application_suggestion_broker():
    app = QApplication.instance()
    broker = getattr(app, '_spelling_suggestion_broker', None)
    if broker is None:
        broker = SuggestionBroker(app)
        app._spelling_suggestion_broker = broker
        app.aboutToQuit.connect(broker.close)
    return broker


@dataclass(frozen=True)
class WordTarget:
    document: object
    revision: int
    start: int
    end: int
    word: str


class SpellingSuggestionController(QObject):
    """Only the mouse context event invokes attach(); menu construction is inert."""
    def __init__(self, editor, *, broker=None):
        super().__init__(editor)
        self.editor = editor
        self._broker = broker
        self._request = None
        self._menu = None
        self._target = None
        self._placeholder = None
        self._generation = 0
        editor.textChanged.connect(self.invalidate)
        editor.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Hide, QEvent.Type.ReadOnlyChange):
            self.invalidate()
        return False

    def invalidate(self):
        menu = self._menu
        self._generation += 1
        if self._request is not None:
            self._broker.cancel(self._request)
        self._request = None
        self._menu = None
        self._target = None
        self._placeholder = None
        if menu is not None and isValid(menu) and menu.isVisible():
            menu.close()

    def attach(self, menu, target):
        """Arm this existing menu following a mouse right-click on flagged text."""
        self.invalidate()
        if target is None:
            return
        self._menu, self._target = menu, target
        anchor = menu.actions()[0] if menu.actions() else None
        placeholder = menu.addAction('Loading suggestions…')
        placeholder.setEnabled(False)
        menu.insertAction(anchor, placeholder)
        self._placeholder = placeholder
        generation = self._generation
        menu.aboutToHide.connect(lambda: self.invalidate() if generation == self._generation else None)
        # aboutToShow fires before visibility is set; defer submission one turn.
        menu.aboutToShow.connect(lambda: QTimer.singleShot(0, lambda: self._start(generation)))

    def _valid(self):
        target, menu = self._target, self._menu
        if (target is None or menu is None or not isValid(menu) or not menu.isVisible()
                or not isValid(self.editor) or not self.editor.isVisible()
                or self.editor.isReadOnly() or self.editor.document() is not target.document
                or target.document.revision() != target.revision
                or not any(a == target.start and b == target.end
                           for a, b, _ in self.editor._spelling_ranges)):
            return False
        cursor = QTextCursor(target.document)
        cursor.setPosition(target.start)
        cursor.setPosition(target.end, QTextCursor.MoveMode.KeepAnchor)
        return cursor.selectedText() == target.word

    def _start(self, generation):
        if generation != self._generation or self._request is not None or not self._valid():
            return
        if self._broker is None:
            self._broker = application_suggestion_broker()
        # UniqueConnection is not supported for Python callbacks; connect once.
        if not getattr(self, '_connected', False):
            self._broker.completed.connect(self._complete)
            self._connected = True
            broker = self._broker
            self.destroyed.connect(lambda: broker.cancel(self._request) if self._request is not None else None)
        self._request = self._broker.submit(self._target.word)

    def _complete(self, outcome):
        if outcome.request_id != self._request:
            return
        self._request = None
        if not self._valid():
            self.invalidate()
            return
        menu, target, placeholder = self._menu, self._target, self._placeholder
        if outcome.error or not outcome.suggestions:
            placeholder.setText('Suggestions unavailable' if outcome.error else 'No spelling suggestions')
            return
        for replacement in outcome.suggestions[:5]:
            action = menu.addAction(replacement)
            menu.insertAction(placeholder, action)
            action.triggered.connect(lambda checked=False, text=replacement: self.editor._replace_spelling(
                target.start, target.end, target.word, target.revision, text))
        menu.removeAction(placeholder)
        placeholder.deleteLater()
