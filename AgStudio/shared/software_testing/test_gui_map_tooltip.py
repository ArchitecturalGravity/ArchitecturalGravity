"""Infer Map overflow retains every object without taking editor focus."""
import importlib.util
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class MapTooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QWidget
        from AgStudio.gui.map_tooltip import MapTooltip
        self.window = QWidget()
        self.editor = QPlainTextEdit()
        self.editor.setPlainText('[A]: original source\n[B]: [A]\n')
        self.source = QWidget()
        self.source.setMinimumWidth(100)
        self.source.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QHBoxLayout(self.window)
        layout.addWidget(self.editor)
        layout.addWidget(self.source)
        self.window.resize(500, 300)
        self.window.show()
        self.window.activateWindow()
        self.editor.setFocus()
        self.app.processEvents()
        self.tooltip = MapTooltip(self.source)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)
        self.addCleanup(self.tooltip.hide)

    def text(self):
        return '\n'.join(
            f'Object {number:02}: linked coverage at readout\n'
            '  Influence 1.23; shared 0.12; other-only 4.56\n'
            '  Complete document-level relationship evidence'
            for number in range(1, 61))

    def show_overflow(self, point=None):
        self.tooltip.show_text(self.text(), point or self.source.mapToGlobal(self.source.rect().center()))
        self.app.processEvents()
        self.assertTrue(self.tooltip._popup.isVisible())
        self.assertEqual(self.tooltip._popup.accessibleName(), 'Infer Map details')
        return self.tooltip._reader

    def test_short_text_uses_native_tooltip_and_preserves_authored_lines(self):
        with patch('AgStudio.gui.map_tooltip.QToolTip.showText') as show:
            self.tooltip.show_text('A < B\nSecond line', self.source.mapToGlobal(self.source.rect().center()))
        self.assertEqual(show.call_count, 1)
        self.assertIn('A &lt; B<br>Second line', show.call_args.args[1])
        self.assertFalse(self.tooltip._popup.isVisible())

    def test_sixty_objects_full_text_and_last_object_are_scrollable(self):
        from PySide6.QtGui import QTextCursor
        reader = self.show_overflow()
        self.assertEqual(reader.toPlainText(), self.text())
        self.assertEqual(reader.document().blockCount(), 180)
        scrollbar = reader.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(scrollbar.maximum())
        self.app.processEvents()
        cursor = QTextCursor(reader.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.assertTrue(reader.viewport().rect().intersects(reader.cursorRect(cursor)))
        self.assertIn('Object 60:', reader.toPlainText())
        old_value = scrollbar.value()
        self.tooltip.show_text(self.text(), self.source.mapToGlobal(self.source.rect().center()))
        self.assertEqual(scrollbar.value(), old_value)

    def test_popup_stays_inside_available_screen_at_every_corner(self):
        bounds = self.source.screen().availableGeometry()
        for point in (bounds.topLeft(), bounds.topRight(), bounds.bottomLeft(), bounds.bottomRight()):
            with self.subTest(point=point):
                self.tooltip.hide()
                self.show_overflow(point)
                self.assertTrue(bounds.contains(self.tooltip._popup.frameGeometry()))

    def test_long_unbroken_lines_have_horizontal_overflow_without_truncation(self):
        text = '<plain text> ' + 'long-object-name' * 250
        self.tooltip.show_text(text, self.source.mapToGlobal(self.source.rect().center()))
        self.app.processEvents()
        self.assertEqual(self.tooltip._reader.toPlainText(), text)
        self.assertGreater(self.tooltip._reader.horizontalScrollBar().maximum(), 0)
        self.assertTrue(self.source.screen().availableGeometry().contains(self.tooltip._popup.frameGeometry()))

    def test_wheel_and_click_scroll_without_changing_source_or_editor_cursor(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtTest import QTest
        source, position = self.editor.toPlainText(), self.editor.textCursor().position()
        focus = self.app.focusWidget()
        reader = self.show_overflow()
        self.assertIs(self.app.focusWidget(), focus)
        self.assertTrue(reader.isReadOnly())
        self.assertEqual(reader.focusPolicy(), Qt.FocusPolicy.NoFocus)
        viewport = reader.viewport()
        local = viewport.rect().center()
        event = QWheelEvent(QPointF(local), QPointF(viewport.mapToGlobal(local)),
                            QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        self.app.sendEvent(viewport, event)
        self.assertGreater(reader.verticalScrollBar().value(), 0)
        QTest.mouseClick(reader.verticalScrollBar(), Qt.MouseButton.LeftButton,
                         pos=reader.verticalScrollBar().rect().center())
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=local)
        self.assertIs(self.app.focusWidget(), focus)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertEqual(self.editor.textCursor().position(), position)
        self.assertTrue(self.tooltip.isVisible())

    def test_leave_grace_allows_entering_popup_then_dismisses_outside(self):
        from PySide6.QtCore import QEvent, QPoint
        from PySide6.QtGui import QEnterEvent
        from PySide6.QtTest import QTest
        self.show_overflow()
        self.app.sendEvent(self.source, QEvent(QEvent.Type.Leave))
        self.assertTrue(self.tooltip._dismiss_timer.isActive())
        self.assertTrue(self.tooltip.isVisible())
        position = self.tooltip._reader.viewport().rect().center()
        event = QEnterEvent(position, position, self.tooltip._reader.viewport().mapToGlobal(position))
        self.app.sendEvent(self.tooltip._reader.viewport(), event)
        self.assertFalse(self.tooltip._dismiss_timer.isActive())
        self.app.sendEvent(self.tooltip._popup, QEvent(QEvent.Type.Leave))
        with patch('AgStudio.gui.map_tooltip.QCursor.pos', return_value=QPoint(-10000, -10000)):
            QTest.qWait(self.tooltip.LEAVE_GRACE_MS + 50)
        self.assertFalse(self.tooltip.isVisible())

    def test_escape_dismisses_while_focus_remains_in_editor(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.show_overflow()
        QTest.keyClick(self.editor, Qt.Key.Key_Escape)
        self.assertFalse(self.tooltip.isVisible())
        self.assertIs(self.app.focusWidget(), self.editor)

    def test_explicit_invalidation_and_parent_hide_dismiss_immediately(self):
        from PySide6.QtCore import QEvent
        self.show_overflow()
        self.app.sendEvent(self.source, QEvent(QEvent.Type.Leave))
        self.tooltip.hide()  # DocumentMap invalidation/mode publication hook.
        self.assertFalse(self.tooltip.isVisible())
        self.assertFalse(self.tooltip._dismiss_timer.isActive())
        self.assertFalse(self.tooltip._application_filter)
        self.show_overflow()
        self.window.hide()
        self.assertFalse(self.tooltip.isVisible())
        self.window.show()
        self.app.processEvents()
        self.assertFalse(self.tooltip.isVisible())

    def test_replacement_text_resets_scroll_and_removes_stale_evidence(self):
        reader = self.show_overflow()
        reader.verticalScrollBar().setValue(reader.verticalScrollBar().maximum())
        new_text = self.text().replace('Object', 'Replacement')
        self.tooltip.show_text(new_text, self.source.mapToGlobal(self.source.rect().center()))
        self.assertEqual(reader.verticalScrollBar().value(), 0)
        self.assertEqual(reader.toPlainText(), new_text)
        self.assertNotIn('Object', reader.toPlainText())

    def test_short_replacement_and_empty_text_do_not_leave_overflow_window(self):
        self.show_overflow()
        with patch('AgStudio.gui.map_tooltip.QToolTip.showText') as show:
            self.tooltip.show_text('Replacement summary', self.source.mapToGlobal(self.source.rect().center()))
        self.assertEqual(show.call_count, 1)
        self.assertFalse(self.tooltip._popup.isVisible())
        self.assertFalse(self.tooltip._application_filter)
        self.tooltip.show_text('', self.source.mapToGlobal(self.source.rect().center()))
        self.assertFalse(self.tooltip.isVisible())

    def test_source_destruction_owns_popup_and_removes_live_event_filter(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QWidget
        from shiboken6 import isValid
        from AgStudio.gui.map_tooltip import MapTooltip
        source = QWidget()
        source.resize(100, 100)
        source.show()
        tooltip = MapTooltip(source)
        tooltip.show_text(self.text(), source.mapToGlobal(source.rect().center()))
        self.assertTrue(tooltip.isVisible())
        popup = tooltip._popup
        source.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertFalse(isValid(tooltip))
        self.assertFalse(isValid(popup))


if __name__ == '__main__':
    unittest.main()
