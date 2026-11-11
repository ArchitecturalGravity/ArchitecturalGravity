"""Explicit mouse-only suggestion requests and safe asynchronous menu delivery."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def make_fake_broker():
    from PySide6.QtCore import QObject, Signal
    class FakeBroker(QObject):
        completed = Signal(object)
        def __init__(self):
            super().__init__()
            self.words = []
            self.cancelled = []
        def submit(self, word):
            self.words.append(word)
            return len(self.words)
        def cancel(self, request):
            self.cancelled.append(request)
        def deliver(self, request=1, suggestions=('receive',), error=None):
            self.completed.emit(SimpleNamespace(request_id=request, suggestions=suggestions, error=error))
    return FakeBroker()


class RightClickSuggestionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global QObject, QPoint, QTimer, Signal, Qt, QContextMenuEvent, QTextCursor, QApplication, QMenu, QTest, SourceEditor
        from PySide6.QtCore import QObject, QPoint, QTimer, Signal, Qt
        from PySide6.QtGui import QContextMenuEvent, QTextCursor
        from PySide6.QtWidgets import QApplication, QMenu
        from PySide6.QtTest import QTest
        from AgStudio.gui.app import SourceEditor
        cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.editor = SourceEditor()
        self.editor.setPlainText('- recieve text')
        self.editor.set_spelling_ranges(((2, 9, 'Possible English misspelling: recieve'),))
        self.broker = make_fake_broker()
        self.editor.spelling_suggestions._broker = self.broker
        self.editor.show()
        self.app.processEvents()
        self.menus = []
    def tearDown(self):
        for menu in self.menus:
            menu.close()
            menu.deleteLater()
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()
    def popup(self):
        menu = self.editor.spelling_context_menu(3)
        self.menus.append(menu)
        self.editor.spelling_suggestions.attach(menu, self.editor.spelling_target_at(3))
        menu.popup(self.editor.mapToGlobal(QPoint(10, 10)))
        QTest.qWait(10)
        return menu
    def test_construction_and_plain_edit_actions_never_request(self):
        menu = self.editor.spelling_context_menu(3)
        self.menus.append(menu)
        QTest.qWait(5)
        self.assertEqual(self.broker.words, [])
        self.assertFalse(any('suggestion' in a.text().lower() for a in menu.actions()))
    def test_async_response_and_undo(self):
        menu = self.popup()
        self.assertEqual(self.broker.words, ['recieve'])
        self.assertEqual(menu.actions()[0].text(), 'Loading suggestions…')
        self.broker.deliver()
        action = next(a for a in menu.actions() if a.text() == 'receive')
        self.app.processEvents()
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center())
        self.assertEqual(self.editor.toPlainText(), '- receive text')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), '- recieve text')
    def test_empty_and_failure_are_distinct(self):
        menu = self.popup()
        self.broker.deliver(suggestions=())
        self.assertEqual(menu.actions()[0].text(), 'No spelling suggestions')
        menu.close()
        menu = self.popup()
        self.broker.deliver(request=2, suggestions=(), error='worker failed')
        self.assertEqual(menu.actions()[0].text(), 'Suggestions unavailable')
    def test_closed_menu_superseded_request_and_changed_text_are_ignored(self):
        first = self.popup()
        first.close()
        second = self.popup()
        self.broker.deliver(request=1)
        self.assertNotIn('receive', [a.text() for a in second.actions()])
        self.editor.insertPlainText('changed')
        self.broker.deliver(request=2)
        self.assertNotIn('receive', [a.text() for a in second.actions()])
        self.assertIn(1, self.broker.cancelled)
    def test_readonly_range_changes_and_tab_hide_invalidate(self):
        for change in (lambda: self.editor.setReadOnly(True),
                       lambda: self.editor.set_spelling_ranges(()),
                       lambda: self.editor.hide()):
            with self.subTest(change=change):
                self.editor.setReadOnly(False)
                self.editor.show()
                self.editor.set_spelling_ranges(((2, 9, 'typo'),))
                menu = self.popup()
                request = len(self.broker.words)
                change()
                self.broker.deliver(request=request)
                self.assertNotIn('receive', [a.text() for a in menu.actions()])
                menu.close()
    def test_identical_analysis_refresh_and_old_hide_do_not_cancel_new_request(self):
        first = self.popup()
        second = self.popup()
        request = len(self.broker.words)
        first.aboutToHide.emit()
        self.editor.set_spelling_ranges(self.editor._spelling_ranges)
        self.broker.deliver(request=request)
        self.assertIn('receive', [a.text() for a in second.actions()])

    def test_real_service_delivers_without_blocking_gui(self):
        from AgStudio.gui.spelling_suggestions import SuggestionBroker
        import time
        broker = SuggestionBroker()
        self.editor.spelling_suggestions._broker = broker
        ticks = []
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: ticks.append(True))
        timer.start()
        try:
            menu = self.popup()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and 'receive' not in [a.text() for a in menu.actions()]:
                QTest.qWait(10)
            self.assertIn('receive', [a.text() for a in menu.actions()])
            self.assertTrue(ticks)
        finally:
            timer.stop()
            menu.close()
            broker.close()
            self.assertTrue(broker.service.wait_closed(5))

    def test_only_mouse_event_on_flagged_word_requests(self):
        for reason, position, expected in ((QContextMenuEvent.Reason.Keyboard, 3, 0),
                                           (QContextMenuEvent.Reason.Mouse, 12, 0),
                                           (QContextMenuEvent.Reason.Mouse, 3, 1)):
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(position)
            self.editor.setTextCursor(cursor)
            point = self.editor.cursorRect(cursor).center()
            event = QContextMenuEvent(reason, point, self.editor.viewport().mapToGlobal(point))
            def close():
                popup = QApplication.activePopupWidget()
                if isinstance(popup, QMenu):
                    popup.close()
            QTimer.singleShot(30, close)
            self.editor.contextMenuEvent(event)
            self.assertEqual(len(self.broker.words), expected)
