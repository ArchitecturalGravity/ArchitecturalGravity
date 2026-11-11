"""Pane-header usability and shared document-navigation regression contracts."""
import importlib.util
import json
import os
from contextlib import ExitStack
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class PaneHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from AgStudio.gui.color_schemes import SchemeStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(str(Path(self.temp.name) / 'headers.ini'), QSettings.Format.IniFormat)
        self.store = SchemeStore(Path(self.temp.name) / 'colors')
        self.windows = []

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            for window in self.windows:
                window.close()
                window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def window(self, *, background=False):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.user_state import UserState
        window = StudioWindow('current', background=background, user_state=UserState(self.settings),
                              scheme_store=self.store)
        self.windows.append(window)
        window.resize(1180, 780)
        window.show()
        self.settle()
        return window

    def settle(self):
        # Reparenting the shared strip can post another layout request.
        for _ in range(3):
            self.app.processEvents()

    def bounds(self, widget, window):
        from PySide6.QtCore import QPoint, QRect
        return QRect(widget.mapTo(window, QPoint()), widget.size())

    def assert_header_controls_available(self, window):
        tab = window.current()
        strip = window.tabs.tabBar().parentWidget()
        self.assertIs(strip.parentWidget(), tab.editor_header)
        self.assertTrue(strip.isVisible())
        if not tab.map_column.isHidden():
            self.assertTrue(tab.document_map.isVisible())
            self.assertTrue(tab.map_heading.rect().contains(tab.inference_mode_button.geometry()))

    def snapshot(self, tab):
        cursor = tab.editor.textCursor()
        return (tab.path, tab.source, tab.dirty, cursor.position(), cursor.anchor(),
                tab.editor.document().availableUndoSteps(), tab.document, tab.analysis,
                tab.diagnostics, tab.editor.verticalScrollBar().value(),
                tab.editor.horizontalScrollBar().value())

    def test_panel_toggles_preserve_document_state_across_resizes(self):
        window = self.window()
        tab = window.current()
        tab.editor.insertPlainText('Task:\n- preserve unsaved source\n')
        before = self.snapshot(tab)
        for width in (780, 1180, 1500):
            window.resize(width, 780)
            self.settle()
            for _ in range(2):
                window.panel_actions['side_panel'].trigger()
                self.settle()
            self.assertEqual(self.snapshot(tab), before)

    def test_finding_header_controls_center_and_stay_compact(self):
        from PySide6.QtCore import QPoint
        window = self.window()
        tab = window.current()
        window._show_diagnostics()
        self.settle()
        heading = tab.findings_header
        height = heading.height()
        for pending in (False, True, False):
            tab.diagnostic_spinner.set_pending(pending)
            tab.diagnostic_status.setText('Pending' if pending else '')
            tab.diagnostic_status.setVisible(pending)
            for count in tab.diagnostic_count_labels.values():
                count.setText('12345')
            for _ in range(2):
                tab._toggle_diagnostics()
                self.settle()
                self.assertEqual(heading.height(), height)
                controls = [tab.diagnostics_toggle, tab.diagnostics_heading,
                            tab.diagnostic_counts, tab.diagnostic_spinner, tab.diagnostic_status,
                            *tab.diagnostic_count_labels.values(), *tab.diagnostic_count_icons.values()]
                center = heading.height() / 2
                for control in controls:
                    if not control.isVisible():
                        continue
                    position = control.mapTo(heading, QPoint())
                    self.assertLessEqual(abs(position.y() + control.height() / 2 - center), 1,
                                         (control.objectName(), position, control.size()))
                    self.assertGreaterEqual(position.y(), 0)
                    self.assertLessEqual(position.y() + control.height(), heading.height())
        self.assertEqual(heading.layout().contentsMargins().bottom(), 0)
        self.assertEqual(heading.layout().spacing(), tab.outline_heading.layout().spacing())

    def test_finding_header_fits_text_after_font_size_changes(self):
        from AgStudio.gui.app import STUDIO_STYLE
        window = self.window()
        for size in (14, 18, 14):
            window.setStyleSheet(STUDIO_STYLE + f'\nQWidget {{ font-size: {size}px; }}')
            self.settle()
            tab = window.current()
            self.assertGreaterEqual(tab.findings_header.height(),
                                    tab.diagnostics_heading.sizeHint().height())

    def show_correlations(self, window):
        tab = window.current()
        tab.editor.insertPlainText('[A]:\n- Content\n\nTask:\n- Use [A]\n- Another [A]\n')
        parent = tab.outline.topLevelItem(0)
        tab.outline.setCurrentItem(parent)
        tab._outline_clicked(parent)
        self.settle()
        self.assertTrue(tab.correlations_panel.isVisible())
        return tab

    def assert_correlation_columns(self, window):
        tab = window.current()
        self.assertEqual([tab.correlations.headerItem().text(i) for i in range(3)],
                         ['Symbol', 'Line', 'Column'])

    def test_correlation_columns_and_rows_survive_font_and_size_changes(self):
        from AgStudio.gui.app import STUDIO_STYLE
        window = self.window()
        tab = self.show_correlations(window)
        for size in (14, 18, 14):
            window.setStyleSheet(STUDIO_STYLE + f'\nQWidget {{ font-size: {size}px; }}')
            for width in (780, 1180, 1500):
                window.resize(width, 780)
                self.settle()
                self.assert_correlation_columns(window)
                self.assertEqual(tab.correlations.topLevelItemCount(), 3)

    def test_correlation_headers_reappear_without_changing_selection_or_navigation(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        window = self.window()
        tab = self.show_correlations(window)
        parent = tab.outline.currentItem()
        row = tab.correlations.topLevelItem(1)
        QTest.mouseClick(tab.correlations.viewport(), Qt.MouseButton.LeftButton,
                         pos=tab.correlations.visualItemRect(row).center())
        self.settle()
        self.assertIs(tab.correlations.currentItem(), row)
        self.assertEqual(tab.editor.textCursor().position(),
                         row.data(0, Qt.ItemDataRole.UserRole).start)
        before = self.snapshot(tab)
        for _ in range(2):
            window.panel_actions['side_panel'].trigger()
            self.settle()
            window.panel_actions['side_panel'].trigger()
            self.settle()
            self.assert_correlation_columns(window)
            self.assertIs(tab.outline.currentItem(), parent)
            self.assertIs(tab.correlations.currentItem(), row)
            self.assertEqual(self.snapshot(tab), before)
        other = self.add_named_tab(window, 9)
        self.assertTrue(other.correlations_panel.isHidden())
        window.tabs.setCurrentWidget(tab)
        self.settle()
        self.assert_correlation_columns(window)
        self.assertEqual(self.snapshot(tab), before)

    def test_font_size_changes_preserve_document_state(self):
        from AgStudio.gui.app import STUDIO_STYLE
        window = self.window()
        tab = self.show_correlations(window)
        before = self.snapshot(tab)
        for size in (14, 18, 14):
            window.setStyleSheet(STUDIO_STYLE + f'\nQWidget {{ font-size: {size}px; }}')
            self.settle()
        self.assertEqual(self.snapshot(tab), before)

    def test_map_title_toggle_retains_edit_state(self):
        from AgStudio.gui.app import STUDIO_STYLE
        window = self.window()
        tab = self.show_correlations(window)
        source = tab.source
        for size in (14, 18, 14):
            window.setStyleSheet(STUDIO_STYLE + f'\nQWidget {{ font-size: {size}px; }}')
            self.settle()
            for _ in range(2):
                tab.map_title.click()
                self.settle()
                self.assertTrue(tab.map_title.isChecked())
                tab.map_title.click()
                self.settle()
                self.assertFalse(tab.map_title.isChecked())
        self.assertEqual(tab.source, source)

    def add_named_tab(self, window, number):
        from AgStudio.gui.app import DocumentTab
        path = Path(self.temp.name) / f'document_{number:02d}_with_a_long_name.arc'
        source = f'[Document{number}]: Exact source {number} 🌍\r\n- Keep this text\r\n'
        return window._add_tab(DocumentTab('current', source, path,
                                           map_enabled=window.user_state.panels['document_map']))

    def assert_tab_order(self, window, expected, current, snapshots):
        self.assertEqual(window.tabs.count(), len(expected))
        self.assertIs(window.current(), current)
        self.assertEqual(window.tabs.currentIndex(), expected.index(current))
        bar = window.tabs.tabBar()
        buttons = [bar.childAt(bar.tabRect(index).center()) for index in range(len(expected))]
        self.assertTrue(all(button is not None for button in buttons))
        self.assertEqual([index for index, button in enumerate(buttons) if button.isChecked()],
                         [expected.index(current)], 'Exactly the current document tab must remain checked')
        for index, tab in enumerate(expected):
            self.assertIs(window.tabs.widget(index), tab)
            self.assertEqual(window.tabs.indexOf(tab), index)
            label = tab.path.name if tab.path else 'Untitled.arc'
            self.assertEqual(window.tabs.tabText(index), label + (' *' if tab.dirty else ''))
            self.assertEqual(self.snapshot(tab), snapshots[tab])
        self.assert_header_controls_available(window)

    def test_map_editor_and_outline_align_through_window_and_splitter_resizes(self):
        window = self.window()
        tab = window.current()
        tab.editor.insertPlainText('Task:\n- ' + 'wide ' * 100 + '\n' + '- line\n' * 70)
        for width, height in ((1180, 780), (780, 550), (1500, 950), (900, 620)):
            window.resize(width, height)
            for map_sizes in ([700, 130], [500, 260], [100000, 1]):
                with self.subTest(size=(width, height), map_sizes=map_sizes):
                    tab.editor_map_split.setSizes(map_sizes)
                    self.settle()
                    self.assert_header_controls_available(window)
                    self.assertGreaterEqual(tab.editor.width(), 270)
                    tab.split.moveSplitter(max(180, tab.height() // 2), 1)
                    self.settle()
                    self.assert_header_controls_available(window)
        tab.editor_split.moveSplitter(tab.editor_split.handle(1).x() - 80, 1)
        self.settle()
        self.assert_header_controls_available(window)

    def test_map_edit_button_stays_compact_across_modes_and_wrapped_headers(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        window = self.window()
        for number in range(5):
            self.add_named_tab(window, number)
        tab = window.current()
        for width in (780, 1500):
            window.resize(width, 620)
            for mode in MODE_LABELS:
                window.inference_mode_actions[mode].trigger()
                for _ in range(2):
                    tab.map_title.click()
                    self.settle()
                    self.assert_header_controls_available(window)
                    self.assertLess(tab.map_title.height(), tab.map_heading.height())

    def test_map_controls_stay_at_top_when_tab_rows_grow_and_shrink(self):
        window = self.window()
        for number in range(8):
            self.add_named_tab(window, number)
        for width in (780, 1500, 900):
            window.resize(width, 780)
            self.settle()
            tab = window.current()
            self.assertGreater(window.tabs.tabBar().height(), window.tabs.tabBar().rowHeight())
            self.assert_header_controls_available(window)
            for control in (tab.map_title, tab.inference_mode_button):
                self.assertEqual(control.y(), 0)
        while window.tabs.count() > 1:
            window._close_tab(window.tabs.count() - 1)
            self.settle()
            tab = window.current()
            self.assert_header_controls_available(window)
            self.assertEqual(tab.map_title.y(), 0)
            self.assertEqual(tab.inference_mode_button.y(), 0)
        self.assertEqual(tab.map_heading.height(), tab.outline_heading.height())

    def test_standalone_document_keeps_header_and_map_geometry_aligned(self):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', 'Task:\n- source\n')
        try:
            tab.side_panel.show()
            tab.resize(1000, 620)
            tab.show()
            self.settle()
            for widget in (tab.map_heading, tab.outline_heading):
                self.assertEqual(self.bounds(widget, tab).top(), self.bounds(tab.editor_header, tab).top())
                self.assertEqual(widget.height(), tab.editor_header.height())
            self.assertEqual(self.bounds(tab.editor, tab).top(), self.bounds(tab.document_map, tab).top())
            self.assertEqual(self.bounds(tab.editor, tab).bottom(), self.bounds(tab.document_map, tab).bottom())
        finally:
            tab.close()
            tab.deleteLater()
            self.settle()

    def test_hidden_panels_remove_their_headers_and_restore_alignment_on_every_tab(self):
        window = self.window()
        first = window.current()
        first.editor.insertPlainText('First: retain source\n')
        second = self.add_named_tab(window, 2)
        snapshots = {tab: self.snapshot(tab) for tab in (first, second)}
        for hidden in (('document_map',), ('side_panel',),
                       ('document_map', 'side_panel'), ('error_list',), ()):
            with self.subTest(hidden=hidden):
                for name, action in window.panel_actions.items():
                    action.setChecked(name not in hidden)
                for tab in (first, second):
                    window.tabs.setCurrentWidget(tab)
                    self.settle()
                    self.assertEqual(tab.map_column.isHidden(), 'document_map' in hidden)
                    self.assertEqual(tab.document_map.isHidden(), 'document_map' in hidden)
                    self.assertEqual(tab.map_heading.isVisible(), 'document_map' not in hidden)
                    self.assertEqual(tab.side_panel.isHidden(), 'side_panel' in hidden)
                    self.assertEqual(tab.diagnostics_panel.isHidden(), 'error_list' in hidden)
                    if 'document_map' in hidden:
                        self.assertEqual(tab.editor_map_split.sizes()[1], 0)
                    self.assert_header_controls_available(window)
                    self.assertEqual(self.snapshot(tab), snapshots[tab])
        window.panel_actions['document_map'].setChecked(False)
        window.panel_actions['side_panel'].setChecked(False)
        third = window.new_document()
        self.settle()
        self.assertTrue(third.map_column.isHidden())
        self.assertTrue(third.side_panel.isHidden())
        self.assert_header_controls_available(window)
        for name in ('document_map', 'side_panel'):
            window.panel_actions[name].setChecked(True)
        self.settle()
        self.assert_header_controls_available(window)

    def assert_wrapped_tabs(self, window):
        """Every tab stays in the editor header; additional rows start at its left edge."""
        from PySide6.QtCore import QRect
        bar = window.tabs.tabBar()
        header = self.bounds(window.current().editor_header, window)
        rows = {}
        rectangles = []
        for index in range(window.tabs.count()):
            local = bar.tabRect(index)
            rect = QRect(bar.mapTo(window, local.topLeft()), local.size())
            self.assertGreater(rect.width(), 0)
            self.assertGreater(rect.height(), 0)
            self.assertTrue(header.contains(rect), f'Tab {index} escapes editor header: {rect}, {header}')
            for earlier in rectangles:
                self.assertFalse(rect.intersects(earlier), f'Tab {index} overlaps another tab')
            rectangles.append(rect)
            rows.setdefault(rect.top(), []).append(rect)
        for top in sorted(rows)[1:]:
            self.assertEqual(rows[top][0].left(), header.left(), 'Wrapped row must return to editor left edge')
        self.assert_header_controls_available(window)
        return len(rows)

    def test_many_tabs_wrap_reflow_and_reorder_without_swapping_document_state(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
        window = self.window()
        expected = [window.current()] + [self.add_named_tab(window, n) for n in range(1, 10)]
        edited = expected[4]
        edited.editor.insertPlainText('Unsaved addition\n')
        cursor = edited.editor.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
        edited.editor.setTextCursor(cursor)
        window.resize(780, 750)
        self.settle()
        snapshots = {tab: self.snapshot(tab) for tab in expected}
        current = expected[-1]
        bar = window.tabs.tabBar()
        narrow_rows = self.assert_wrapped_tabs(window)
        self.assertGreater(narrow_rows, 1)
        narrow_header_height = current.editor_header.height()
        QTest.mouseClick(current.inference_mode_button, Qt.MouseButton.LeftButton)
        self.assert_mode(window, 'semantic_triad_1')
        self.assert_tab_order(window, expected, current, snapshots)
        # Both selected and inactive moves must preserve the widget/label pairing.
        for before, after in ((9, 1), (5, 0), (0, 8), (1, 7)):
            moving = expected.pop(before)
            expected.insert(after, moving)
            bar.moveTab(before, after)
            self.settle()
            self.assert_tab_order(window, expected, current, snapshots)
            self.assert_wrapped_tabs(window)
        # Click first, last, and intermediate rows twice: a selected tab must stay checked.
        for index in (0, 0, len(expected) - 1, len(expected) - 1, 3, 3, 0, 0):
            current = expected[index]
            button = bar.childAt(bar.tabRect(index).center())
            self.assertIsNotNone(button)
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            self.settle()
            self.assert_tab_order(window, expected, current, snapshots)
            self.assert_wrapped_tabs(window)
        window.resize(1800, 950)
        self.settle()
        wide_rows = self.assert_wrapped_tabs(window)
        self.assertLess(wide_rows, narrow_rows)
        self.assertLess(current.editor_header.height(), narrow_header_height)
        self.assert_tab_order(window, expected, current, snapshots)
        window.resize(780, 750)
        self.settle()
        restored_rows = self.assert_wrapped_tabs(window)
        self.assertGreater(restored_rows, wide_rows)
        for panel in ('document_map', 'side_panel'):
            window.panel_actions[panel].setChecked(False)
        self.settle()
        self.assertLess(self.assert_wrapped_tabs(window), restored_rows)
        self.assert_tab_order(window, expected, current, snapshots)
        for panel in ('document_map', 'side_panel'):
            window.panel_actions[panel].setChecked(True)
        self.settle()
        self.assert_wrapped_tabs(window)
        self.assert_tab_order(window, expected, current, snapshots)

    def test_closing_wrapped_tabs_reclaims_rows_and_keeps_map_editor_alignment(self):
        window = self.window()
        for number in range(8):
            self.add_named_tab(window, number)
        window.resize(800, 780)
        self.settle()
        rows = initial_rows = self.assert_wrapped_tabs(window)
        height = initial_height = window.current().editor_header.height()
        self.assertGreater(rows, 1)
        while window.tabs.count() > 1:
            window.tabs.tabCloseRequested.emit(window.tabs.currentIndex())
            self.settle()
            new_rows = self.assert_wrapped_tabs(window)
            new_height = window.current().editor_header.height()
            self.assertLessEqual(new_rows, rows)
            self.assertLessEqual(new_height, height)
            rows, height = new_rows, new_height
        self.assertEqual(rows, 1)
        self.assertLess(rows, initial_rows)
        self.assertLess(height, initial_height)
        self.assertEqual(window.current().source, '')
        self.assertFalse(window.current().dirty)

    def test_mouse_drag_reorders_tabs_across_wrapped_rows(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QSignalSpy, QTest
        window = self.window()
        tabs = [window.current()] + [self.add_named_tab(window, number) for number in range(5)]
        window.resize(800, 750)
        self.settle()
        self.assertGreater(self.assert_wrapped_tabs(window), 1)
        snapshots = {tab: self.snapshot(tab) for tab in tabs}
        current = tabs[-1]
        bar = window.tabs.tabBar()
        source_rect, target_rect = bar.tabRect(len(tabs) - 1), bar.tabRect(1)
        self.assertNotEqual(source_rect.top(), target_rect.top())
        button = bar.childAt(source_rect.center())
        self.assertIsNotNone(button)
        moved = QSignalSpy(bar.tabMoved)
        QTest.mousePress(button, Qt.MouseButton.LeftButton)
        QTest.mouseMove(button, button.mapFrom(bar, target_rect.center()), delay=20)
        QTest.mouseRelease(button, Qt.MouseButton.LeftButton)
        self.settle()
        self.assertEqual(moved.count(), 1, 'Mouse drag did not reorder the wrapped tabs')
        self.assertEqual(moved.at(0), [len(tabs) - 1, 1])
        tabs.insert(1, tabs.pop())
        self.assert_tab_order(window, tabs, current, snapshots)
        self.assert_wrapped_tabs(window)

    def test_close_inactive_active_cancelled_and_last_tab_keeps_navigation_alive(self):
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMessageBox, QTabBar
        window = self.window()
        first = window.current()
        second = self.add_named_tab(window, 2)
        third = self.add_named_tab(window, 3)
        first.editor.insertPlainText('Unsaved first document\n')
        window.resize(1600, 780)
        self.settle()
        snapshots = {tab: self.snapshot(tab) for tab in (first, second, third)}
        bar = window.tabs.tabBar()
        strip = bar.parentWidget()

        def close_button(tab):
            index = window.tabs.indexOf(tab)
            return (bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
                    or bar.tabButton(index, QTabBar.ButtonPosition.LeftSide))

        QTest.mouseClick(close_button(second), Qt.MouseButton.LeftButton)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.settle()
        self.assert_tab_order(window, [first, third], third, snapshots)
        self.assertIs(bar.parentWidget(), strip)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No) as ask:
            QTest.mouseClick(close_button(first), Qt.MouseButton.LeftButton)
        self.assertEqual(ask.call_count, 1)
        self.assert_tab_order(window, [first, third], third, snapshots)
        QTest.mouseClick(close_button(third), Qt.MouseButton.LeftButton)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.settle()
        self.assert_tab_order(window, [first], first, snapshots)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(close_button(first), Qt.MouseButton.LeftButton)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.settle()
        self.assertEqual(window.tabs.count(), 1)
        self.assertEqual(window.current().source, '')
        self.assertIsNone(window.current().path)
        self.assertFalse(window.current().dirty)
        self.assertIs(bar.parentWidget(), strip)
        self.assert_header_controls_available(window)
        window.new_document()
        self.settle()
        self.assertEqual(window.tabs.count(), 2)
        self.assert_header_controls_available(window)

    def test_keyboard_tab_navigation_crosses_wrapped_rows_without_losing_source(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        window = self.window()
        tabs = [window.current()] + [self.add_named_tab(window, number) for number in range(4)]
        window.resize(800, 650)
        window.activateWindow()
        self.settle()
        self.assertGreater(self.assert_wrapped_tabs(window), 1)
        snapshots = {tab: self.snapshot(tab) for tab in tabs}
        window.tabs.setCurrentIndex(0)
        self.settle()
        for index in (1, 2, 3, 4, 0):
            window.current().editor.setFocus()
            QTest.keyClick(window.current().editor, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
            self.settle()
            self.assert_tab_order(window, tabs, tabs[index], snapshots)
        window.current().editor.setFocus()
        QTest.keyClick(window.current().editor, Qt.Key.Key_Tab,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.settle()
        self.assert_tab_order(window, tabs, tabs[-1], snapshots)

    def assert_mode(self, window, mode):
        from AgStudio.gui.inference_heat import MODE_HELP, MODE_LABELS
        from AgStudio.gui.user_state import UserState
        modes = tuple(MODE_LABELS)
        next_mode = modes[(modes.index(mode) + 1) % len(modes)]
        self.assertEqual(window.user_state.inference_mode, mode)
        self.assertEqual([name for name, action in window.inference_mode_actions.items()
                          if action.isChecked()], [mode])
        for index in range(window.tabs.count()):
            tab = window.tabs.widget(index)
            self.assertEqual(tab.graph.mode, mode)
            self.assertEqual(tab.document_map.mode, mode)
            self.assertEqual(tab.inference_mode_button.text(), {'heuristic': 'H', 'semantic_triad_1': 'ST1', 'semantic_triad_2': 'ST2'}[mode])
            self.assertEqual(tab.inference_mode_button.accessibleName(),
                             f'Inference mode: {MODE_LABELS[mode]}. Switch to {MODE_LABELS[next_mode]}')
            self.assertEqual(tab.inference_mode_button.toolTip(),
                             f'{MODE_LABELS[mode]}\n\n{MODE_HELP[mode]}')
            self.assertNotIn('Click to switch to', tab.inference_mode_button.toolTip())
        self.assertEqual(json.loads(self.settings.value(UserState.INFERENCE_MODE_KEY)),
                         {'version': 1, 'mode': mode})

    def test_mode_button_cycles_all_modes_globally_without_lint_and_persists(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QSignalSpy, QTest
        window = self.window()
        first = window.current()
        first.editor.insertPlainText('[A]: Preserve 🌍 source\n[B]: [A]\n')
        cursor = first.editor.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(8, QTextCursor.MoveMode.KeepAnchor)
        first.editor.setTextCursor(cursor)
        second = self.add_named_tab(window, 2)
        self.settle()
        snapshots = {tab: self.snapshot(tab) for tab in (first, second)}
        with ExitStack() as stack:
            for tab in (first, second):
                stack.enter_context(patch.object(tab, 'refresh_model', side_effect=AssertionError('mode reran lint')))
            stack.enter_context(patch('AgStudio.gui.app.analyze', side_effect=AssertionError('mode reran lint')))
            for index, mode in enumerate(('semantic_triad_1', 'semantic_triad_2', 'heuristic', 'semantic_triad_1', 'semantic_triad_2')):
                tab = (first, second)[index % 2]
                window.tabs.setCurrentWidget(tab)
                self.settle()
                spy = QSignalSpy(tab.inferenceModeRequested)
                QTest.mouseClick(tab.inference_mode_button, Qt.MouseButton.LeftButton)
                self.settle()
                self.assertEqual(spy.count(), 1)
                self.assertEqual(spy.at(0), [mode])
                self.assert_mode(window, mode)
                self.assert_header_controls_available(window)
                for original in (first, second):
                    self.assertEqual(self.snapshot(original), snapshots[original])
        new = window.new_document()
        self.settle()
        self.assertEqual(new.graph.mode, 'semantic_triad_2')
        self.assert_mode(window, 'semantic_triad_2')
        path = Path(self.temp.name) / 'opened.arc'
        content = b'[Open]: untouched\r\n'
        path.write_bytes(content)
        opened = window.open_file(path)
        self.settle()
        self.assertEqual(opened.source, content.decode())
        self.assert_mode(window, 'semantic_triad_2')
        self.assertEqual(path.read_bytes(), content)
        restarted = self.window()
        self.assert_mode(restarted, 'semantic_triad_2')
        self.assert_header_controls_available(restarted)

    def test_menu_mode_syncs_button_and_keyboard_cycle_after_hidden_map(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        window = self.window()
        first = window.current()
        second = self.add_named_tab(window, 2)
        window.panel_actions['document_map'].setChecked(False)
        window.inference_mode_actions['semantic_triad_2'].trigger()
        self.assert_mode(window, 'semantic_triad_2')
        self.assertTrue(all(not tab.graph.enabled for tab in (first, second)))
        window.panel_actions['document_map'].setChecked(True)
        self.settle()
        self.assert_mode(window, 'semantic_triad_2')
        button = window.current().inference_mode_button
        button.setFocus()
        QTest.keyClick(button, Qt.Key.Key_Space)
        self.settle()
        self.assert_mode(window, 'heuristic')
        QTest.keyClick(button, Qt.Key.Key_Space)
        self.settle()
        self.assert_mode(window, 'semantic_triad_1')
        self.assert_header_controls_available(window)

    def test_background_analysis_revision_is_unchanged_by_header_mode_cycle(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        window = self.window(background=True)
        tab = window.current()
        tab.editor.insertPlainText('[A]: source\n[B]: [A]\n')
        deadline = time.monotonic() + 10
        while (tab.analysis is None or tab.analysis.document.source != tab.source) and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNotNone(tab.analysis, 'initial background analysis did not publish')
        self.assertEqual(tab.analysis.document.source, tab.source)
        before = (tab.controller.revision, self.snapshot(tab))
        with patch.object(tab.controller, 'request', side_effect=AssertionError('mode requested lint')):
            for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic'):
                QTest.mouseClick(tab.inference_mode_button, Qt.MouseButton.LeftButton)
                self.settle()
                self.assert_mode(window, mode)
                self.assertEqual((tab.controller.revision, self.snapshot(tab)), before)

if __name__ == '__main__':
    unittest.main()
