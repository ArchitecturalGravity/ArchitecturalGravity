"""Semantic correlations retain their parent while centering exact occurrences."""
import os
import tempfile
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

class CorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        self.temp = tempfile.TemporaryDirectory()
        self.window = StudioWindow('current', user_state=UserState(), background=False, scheme_store=SchemeStore(self.temp.name))
        self.window.resize(1100, 700)
        self.window.show()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.window.deleteLater)

    def load(self, source):
        from AgStudio.gui.app import DocumentTab
        tab = self.window._add_tab(DocumentTab('current', source))
        self.window._show_side_panel()
        self.app.processEvents()
        return tab

    def item(self, tab, label):
        return next(item for item in tab._outline_items.values() if item.text(0) == label)

    def select(self, tab, label):
        item = self.item(tab, label)
        tab.outline.setCurrentItem(item)
        tab._outline_clicked(item)
        self.app.processEvents()
        return item

    def test_identity_exact_occurrences_and_retained_parent(self):
        from PySide6.QtCore import Qt
        from AgStudio.gui.app import _display_offset
        source = '[A]: value\r\n\r\nTask:\r\n- 🌍 [A] and [A]\r\n- "[A]" and `[A]`\r\n- [AB]\r\n"""\r\n[A]\r\n"""\r\n'
        tab = self.load(source)
        self.assertTrue(tab.correlations_panel.isHidden())
        parent = self.select(tab, '[A]: value')
        self.assertFalse(tab.correlations_panel.isHidden())
        self.assertEqual(tab.correlations.topLevelItemCount(), 3)
        rows = [tab.correlations.topLevelItem(i) for i in range(3)]
        self.assertEqual([(r.text(0), r.text(1), r.text(2)) for r in rows],
                         [('[A]', '1', '1'), ('[A]', '4', '5'), ('[A]', '4', '13')])
        context = tab.editor.context_highlight
        for row in rows:
            tab.correlations.setCurrentItem(row)
            tab._correlation_clicked(row)
            span = row.data(0, Qt.ItemDataRole.UserRole)
            self.assertEqual(tab.editor.textCursor().position(), _display_offset(source, span.start))
            self.assertIs(tab.outline.currentItem(), parent)
            self.assertEqual(tab.editor.context_highlight, context)
            self.assertEqual(tab.correlations.topLevelItemCount(), 3)
        cursor = tab.editor.textCursor()
        cursor.setPosition(_display_offset(source, source.index('Task:')))
        tab.editor.setTextCursor(cursor)
        self.assertTrue(tab.correlations_panel.isHidden())
        self.assertEqual(tab.source, source)

    def test_child_nonsymbol_and_edits_hide_and_tabs_are_isolated(self):
        from PySide6.QtGui import QTextCursor
        tab = self.load('[A]:\n- Content\n\nTask:\n- Use [A]\n')
        self.select(tab, '[A]:')
        self.assertFalse(tab.correlations_panel.isHidden())
        self.select(tab, '- Content')
        self.assertTrue(tab.correlations_panel.isHidden())
        self.select(tab, '[A]:')
        other = self.load('Other:\n- Value\n')
        self.assertTrue(other.correlations_panel.isHidden())
        self.window.tabs.setCurrentWidget(tab)
        self.assertFalse(tab.correlations_panel.isHidden())
        tab.editor.moveCursor(QTextCursor.MoveOperation.End)
        tab.editor.insertPlainText('- Added [A]\n')
        self.assertTrue(tab.correlations_panel.isHidden())
        self.select(tab, '[A]:')
        self.assertEqual(tab.correlations.topLevelItemCount(), 3)
        self.select(tab, 'Task:')
        self.assertTrue(tab.correlations_panel.isHidden())

    def test_panel_and_document_toggles_retain_correlation_parent(self):
        tab = self.load('[A]:\n- Content\n\nTask:\n- Use [A]\n')
        parent = self.select(tab, '[A]:')
        context = tab.editor.context_highlight
        row = tab.correlations.topLevelItem(1)
        tab.correlations.setCurrentItem(row)
        position = tab.editor.textCursor().position()

        def assert_retained():
            self.app.processEvents()
            self.assertIs(tab.outline.currentItem(), parent)
            self.assertEqual(tab.editor.context_highlight, context)
            self.assertEqual(tab.editor.textCursor().position(), position)
            self.assertFalse(tab.correlations_panel.isHidden())
            self.assertIs(tab.correlations.currentItem(), row)
            self.assertEqual(tab.correlations.topLevelItemCount(), 2)

        tab.side_panel.hide()
        assert_retained()
        self.window._show_side_panel()
        assert_retained()
        other = self.load('Other:\n- Value\n')
        self.assertTrue(other.correlations_panel.isHidden())
        self.window.tabs.setCurrentWidget(tab)
        assert_retained()
        tab._sync_context()  # Also cover passive synchronization on tab reveal.
        assert_retained()
        cursor = tab.editor.textCursor()
        cursor.setPosition(position + 1)
        tab.editor.setTextCursor(cursor)
        self.assertTrue(tab.correlations_panel.isHidden())
        self.assertIs(tab.outline.currentItem(), self.item(tab, '- Use [A]'))

    def test_outline_and_repeated_correlation_clicks_center_viewport(self):
        source = '[A]: value\n\nTask:\n' + '- Padding\n' * 65 + '- Use [A]\n' + '- Padding\n' * 65
        tab = self.load(source)
        target = self.select(tab, '- Use [A]')
        self.assertLess(abs(tab.editor.cursorRect().center().y() - tab.editor.viewport().height() / 2), 30)
        tab.editor.verticalScrollBar().setValue(0)
        tab._outline_clicked(target)
        self.assertLess(abs(tab.editor.cursorRect().center().y() - tab.editor.viewport().height() / 2), 30)
        self.select(tab, '[A]: value')
        row = tab.correlations.topLevelItem(1)
        for _ in range(2):
            tab.editor.verticalScrollBar().setValue(0)
            tab._correlation_clicked(row)
            self.assertLess(abs(tab.editor.cursorRect().center().y() - tab.editor.viewport().height() / 2), 30)
            self.assertFalse(tab.correlations_panel.isHidden())

    def test_panel_scheme_rgba_selection_and_live_updates(self):
        from copy import deepcopy
        from PySide6.QtCore import Qt, QRect
        from PySide6.QtGui import QColor, QImage, QPainter, QPalette
        from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        scheme = deepcopy(self.window.color_scheme)
        scheme['symbol']['foreground'] = [60, 220, 140, 190]
        scheme['active_row'] = {'foreground': [200, 40, 100, 128], 'background': [40, 100, 200, 128]}
        tab = self.load('[A]: value\n\nTask:\n- Use [A]\n')
        self.select(tab, '[A]: value')
        self.window.apply_color_scheme(scheme)

        def verify(target):
            for tree in (target.outline, target.correlations):
                item = tree.topLevelItem(0)
                self.assertEqual(tree.viewport().palette().color(QPalette.ColorRole.Base), QColor('black'))
                self.assertEqual(item.data(0, Qt.ItemDataRole.UserRole + 2), 'symbol')
                for column in range(item.columnCount()):
                    self.assertEqual(item.foreground(column).color(), QColor(*scheme['symbol']['foreground']))
                for extra in (QStyle.StateFlag.State_None, QStyle.StateFlag.State_HasFocus,
                              QStyle.StateFlag.State_MouseOver, QStyle.StateFlag.State_Active):
                    option = QStyleOptionViewItem()
                    option.initFrom(tree)
                    option.widget = tree
                    option.rect = QRect(0, 0, 240, 28)
                    option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected | extra
                    index = tree.indexFromItem(item)
                    tree.itemDelegate().initStyleOption(option, index)
                    rgba = (scheme['active_row']['foreground'] if scheme['active_row']['foreground'][3]
                            else scheme['symbol']['foreground'])
                    self.assertEqual(option.palette.color(QPalette.ColorRole.HighlightedText), QColor(*rgba))
                    image = QImage(240, 28, QImage.Format.Format_ARGB32)
                    image.fill(QColor('magenta'))
                    painter = QPainter(image)
                    tree.itemDelegate().paint(painter, option, index)
                    painter.end()
                    expected = QImage(1, 1, QImage.Format.Format_ARGB32)
                    expected.fill(QColor('black'))
                    painter = QPainter(expected)
                    painter.fillRect(expected.rect(), QColor(*scheme['active_row']['background']))
                    painter.end()
                    self.assertEqual(image.pixelColor(235, 14), expected.pixelColor(0, 0))
                    # Some text pixels must differ from the background.
                    self.assertTrue(any(image.pixelColor(x, y) != expected.pixelColor(0, 0)
                                        for x in range(100) for y in range(28)))
                    painter = QPainter(expected)
                    painter.fillRect(expected.rect(), QColor(*rgba))
                    painter.end()
                    # Glyph antialiasing may leave no completely covered pixel.
                    self.assertTrue(any(max(abs(a - b) for a, b in zip(
                                            image.pixelColor(x, y).getRgb(), expected.pixelColor(0, 0).getRgb())) < 16
                                        for x in range(100) for y in range(28)))

        verify(tab)
        scheme['active_row']['foreground'] = [0, 0, 0, 0]
        scheme['active_row']['background'] = [0, 0, 0, 0]
        self.window.apply_color_scheme(scheme)
        verify(tab)
        other = self.load('[B]: value\n\nTask:\n- [B]\n')
        self.select(other, '[B]: value')
        verify(other)
        dialog = ColorSchemeDialog(self.window)
        try:
            dialog.roles.setCurrentIndex(dialog.roles.findData('active_row'))
            dialog.controls['background'][0].setValue(211)
            for target in (tab, other):
                self.assertEqual(target.correlations.itemDelegate().active_row['background'][0], 211)
                self.assertEqual(target.outline.itemDelegate().active_row['background'][0], 211)
            dialog.reject()
            verify(tab)
            verify(other)
        finally:
            dialog.deleteLater()

    def test_forward_and_unresolved_references_are_not_correlated(self):
        source = 'Before:\n- [A]\n\n[A]: value\n\nTask:\n- [A]\n'
        tab = self.load(source)
        self.select(tab, '[A]: value')
        self.assertEqual([tab.correlations.topLevelItem(i).text(1) for i in range(tab.correlations.topLevelItemCount())], ['4', '7'])

    def test_pending_analysis_invalidates_correlation_ranges(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        from PySide6.QtTest import QTest
        import time
        window = StudioWindow('current', user_state=UserState(), scheme_store=SchemeStore(self.temp.name))
        self.addCleanup(window.deleteLater)
        tab = window.current()
        source = '[A]: value\n\nTask:\n- [A]\n'
        tab.editor.setPlainText(source)
        deadline = time.monotonic() + 5
        while (tab.analysis is None or not tab._outline_current or tab.diagnostics is None) and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNotNone(tab.analysis)
        self.assertTrue(tab._outline_current)
        item = self.item(tab, '[A]: value')
        tab.outline.setCurrentItem(item)
        tab._outline_clicked(item)
        self.assertEqual(tab.correlations.topLevelItemCount(), 2)
        tab.editor.insertPlainText('prefix ')
        self.assertTrue(tab.correlations_panel.isHidden())
        self.assertIsNone(tab._correlation_document_id)
        self.assertEqual(tab.correlations.topLevelItemCount(), 0)
        deadline = time.monotonic() + 5
        while (tab.analysis is None or not tab._outline_current or tab.diagnostics is None) and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNotNone(tab.analysis)
        self.assertTrue(tab.correlations_panel.isHidden())
        tab.dispose_analysis()
