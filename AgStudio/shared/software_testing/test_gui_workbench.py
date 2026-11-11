"""Editor-first presentation and repeated/interrupted Qt workflows."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 is not installed")
class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        self.window = StudioWindow("current", user_state=UserState(), background=False)
        self.window.resize(1100, 750)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_window_title_uses_full_name_and_tracks_untitled_dirty_state(self):
        from AgStudio.gui.app import APP_VERSION
        tab = self.window.current()
        title = f'Architectural Gravity Studio - Ver. {APP_VERSION} - Untitled.arc'
        self.assertEqual(self.window.windowTitle(), title)
        tab.editor.insertPlainText('Task: preserve source\n')
        self.assertEqual(self.window.windowTitle(), title + ' *')
        self.assertEqual(self.window.tabs.tabText(self.window.tabs.currentIndex()), 'Untitled.arc *')
        tab.editor.undo()
        self.assertEqual(self.window.windowTitle(), title)
        self.assertFalse(tab.dirty)

    def test_window_title_tracks_selected_filename_and_save_as(self):
        from PySide6.QtWidgets import QFileDialog
        from AgStudio.gui.app import APP_VERSION
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / 'First file.arc'
            second_path = Path(directory) / 'Second file.arc'
            first_path.write_text('First: source\n', encoding='utf-8')
            second_path.write_text('Second: source\n', encoding='utf-8')
            first = self.window.open_file(first_path)
            first.editor.insertPlainText('Changed ')
            source = first.source
            second = self.window.open_file(second_path)
            self.assertEqual(self.window.windowTitle(), f'Architectural Gravity Studio - Ver. {APP_VERSION} - Second file.arc')
            self.window.tabs.setCurrentWidget(first)
            self.assertEqual(self.window.windowTitle(), f'Architectural Gravity Studio - Ver. {APP_VERSION} - First file.arc *')
            renamed = Path(directory) / 'Renamed file.arc'
            with mock.patch.object(QFileDialog, 'getSaveFileName',
                                   return_value=(str(renamed), 'ArcGrav source (*.arc)')):
                self.window._save_current(save_as=True)
            self.assertEqual(self.window.windowTitle(), f'Architectural Gravity Studio - Ver. {APP_VERSION} - Renamed file.arc')
            self.assertEqual(first.source, source)
            self.assertFalse(first.dirty)
            self.window.tabs.setCurrentWidget(second)
            self.assertEqual(self.window.windowTitle(), f'Architectural Gravity Studio - Ver. {APP_VERSION} - Second file.arc')
            self.window._close_tab(self.window.tabs.currentIndex())
            self.assertEqual(self.window.windowTitle(), f'Architectural Gravity Studio - Ver. {APP_VERSION} - Renamed file.arc')

    def test_editor_first_and_repeated_panel_restore(self):
        from PySide6.QtCore import Qt
        tab = self.window.current()
        self.assertEqual(tab.split.orientation(), Qt.Orientation.Vertical)
        self.assertFalse(tab.side_panel.isHidden())
        self.assertGreater(tab.editor.height(), tab.diagnostics_panel.height())
        for _ in range(3):
            tab.diagnostics_panel.hide()
            self.window._show_diagnostics()
            self.assertFalse(tab.diagnostics_panel.isHidden())
            self.window._show_side_panel()
            self.assertFalse(tab.side_panel.isHidden())
            tab.side_panel.hide()
        self.assertIn("conformance unknown", tab.diagnostics_heading.toolTip())

    def test_outline_menu_toggle_and_reopen_preserve_state(self):
        from PySide6.QtWidgets import QToolButton, QTextBrowser
        from AgStudio.gui import structure
        from AgStudio.gui.app import DocumentTab
        view = self.window.view_menu
        self.assertIs(view, next(action.menu() for action in self.window.menuBar().actions() if action.text() == 'View'))
        actions = [action for action in view.actions() if not action.isSeparator()]
        self.assertEqual([action.text() for action in actions], ['Outline', 'Finding List', 'Infer Map', 'Inference mode'])
        toggle = self.window.panel_actions['side_panel']
        self.assertTrue(toggle.isCheckable())
        self.assertTrue(toggle.isChecked())
        tab = self.window._add_tab(DocumentTab('current'))
        self.assertFalse(hasattr(tab, 'inspector'))
        self.assertFalse(hasattr(structure, 'inspect_fact'))
        self.assertFalse(tab.findChildren(QTextBrowser))
        tab.editor.setPlainText('[A]:\n- Child\n\nTask:\n' + '- Padding\n' * 60 + '- [A]\n' + '- Padding\n' * 60)
        self.window._show_side_panel()
        self.app.processEvents()
        parent = tab.outline.topLevelItem(0)
        tab.outline.setCurrentItem(parent)
        parent.setExpanded(False)
        tab.correlations.setCurrentItem(tab.correlations.topLevelItem(1))
        tab.editor.verticalScrollBar().setValue(12)
        position = tab.editor.textCursor().position()
        scroll = tab.editor.verticalScrollBar().value()
        self.assertEqual(tab.side_panel.findChildren(QToolButton), [tab.outline_toggle])
        self.assertEqual(tab.diagnostics_panel.findChildren(QToolButton), [tab.diagnostics_toggle])
        for _ in range(3):
            toggle.trigger()
            self.assertTrue(tab.side_panel.isHidden())
            self.assertFalse(toggle.isChecked())
            toggle.trigger()
            for _ in range(2):
                self.window._show_side_panel()
                self.app.processEvents()
                self.assertFalse(tab.side_panel.isHidden())
                self.assertTrue(toggle.isChecked())
                self.assertIs(tab.outline.currentItem(), parent)
                self.assertFalse(parent.isExpanded())
                self.assertEqual(tab.editor.textCursor().position(), position)
                self.assertEqual(tab.editor.verticalScrollBar().value(), scroll)
                self.assertEqual(tab.correlations.topLevelItemCount(), 2)
        other = self.window.new_document()
        self.assertFalse(other.side_panel.isHidden())
        self.window.tabs.setCurrentWidget(tab)
        self.assertFalse(tab.side_panel.isHidden())
        self.assertIs(tab.outline.currentItem(), parent)

    def test_edits_automatically_replace_rows_and_keep_exact_navigation(self):
        tab = self.window.current()
        for index in range(3):
            source = f"[Task]: 🌍\n=> - Active {index}\n"
            tab.editor.setPlainText(source)
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), len(tab.diagnostics.findings))
            # Presentation is severity-ordered, while engine results are source-
            # ordered. Locate the target rule without discarding other findings.
            row = next(tab.diagnostic_list.topLevelItem(i)
                       for i in range(tab.diagnostic_list.topLevelItemCount())
                       if tab.diagnostic_list.topLevelItem(i).text(1) == 'AG-OPERATION-LIST')
            finding = next(f for f in tab.diagnostics.findings
                           if f.rule_id == 'AG-OPERATION-LIST')
            self.assertEqual(row.text(1), finding.rule_id)
            self.assertEqual(row.text(3), str(finding.source_range.start.line))
            self.assertEqual(row.text(4), str(finding.source_range.start.column))
            tab._navigate_finding(row)
            self.assertEqual(tab.editor.textCursor().selectedText(), "=> - ")
            self.assertEqual(tab.source, source)

    def test_menu_actions_remain_available_without_toolbar(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QToolBar
        self.assertEqual(self.window.findChildren(QToolBar), [])
        menus = {action.text(): action.menu() for action in self.window.menuBar().actions()}
        for action, menu, shortcut in (
                (self.window.open_action, 'File', 'Ctrl+O'),
                (self.window.save_action, 'File', 'Ctrl+S'),
                (self.window.undo_action, 'Edit', 'Ctrl+Z'),
                (self.window.redo_action, 'Edit', 'Ctrl+Y')):
            self.assertIn(action, menus[menu].actions())
            self.assertEqual(action.shortcut().toString(), shortcut)
        button = self.window.tabs.cornerWidget(Qt.Corner.TopLeftCorner)
        self.assertEqual(button.accessibleName(), 'New document')
        count = self.window.tabs.count()
        button.click()
        self.assertEqual(self.window.tabs.count(), count + 1)

    def test_menu_undo_redo_and_dirty_label_follow_active_tab(self):
        tab = self.window.current()
        tab.editor.insertPlainText("[Task]: item")
        self.assertTrue(self.window.undo_action.isEnabled())
        self.assertTrue(self.window.tabs.tabText(0).endswith(" *"))
        self.window.undo_action.trigger()
        self.assertEqual(tab.source, "")
        self.assertFalse(tab.dirty)
        self.assertTrue(self.window.redo_action.isEnabled())
        self.window.redo_action.trigger()
        self.assertEqual(tab.source, "[Task]: item")
        self.window.new_document()
        self.assertFalse(self.window.undo_action.isEnabled())
        self.window.tabs.setCurrentWidget(tab)
        self.assertTrue(self.window.undo_action.isEnabled())

    def test_cancel_tab_close_keeps_unsaved_source(self):
        from PySide6.QtWidgets import QMessageBox
        tab = self.window.current()
        tab.editor.insertPlainText("keep this")
        for _ in range(2):
            with mock.patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel):
                self.window._close_tab(0)
            self.assertIs(self.window.current(), tab)
            self.assertEqual(tab.source, "keep this")

    def test_close_tab_save_targets_inactive_document(self):
        from PySide6.QtWidgets import QMessageBox
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'First.arc'
            path.write_text('original', encoding='utf-8')
            tab = self.window.open_file(path)
            tab.editor.insertPlainText('changed ')
            other = self.window.new_document()
            other.editor.insertPlainText('keep this')

            def save_answer(dialog):
                self.assertEqual(dialog.windowTitle(), 'Unsaved changes')
                self.assertEqual(dialog.text(), 'Do you want to save changes to ‘First.arc’ before closing?')
                self.assertEqual(dialog.button(QMessageBox.StandardButton.Discard).text(), "Don't Save")
                self.assertIs(dialog.escapeButton(), dialog.button(QMessageBox.StandardButton.Cancel))
                return QMessageBox.StandardButton.Save

            with mock.patch.object(QMessageBox, 'exec', save_answer):
                self.window._close_tab(self.window.tabs.indexOf(tab))
            self.assertEqual(path.read_text(encoding='utf-8'), 'changed original')
            self.assertEqual(self.window.tabs.indexOf(tab), -1)
            self.assertIs(self.window.current(), other)
            self.assertTrue(other.dirty)
            self.assertEqual(other.source, 'keep this')

    def test_close_untitled_save_cancellation_failure_and_success(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        tab = self.window.current()
        tab.editor.insertPlainText('keep this')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Saved.arc'
            with mock.patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Save):
                with mock.patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
                    self.window._close_tab(0)
                self.assertIs(self.window.current(), tab)
                self.assertTrue(tab.dirty)
                with mock.patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')), \
                        mock.patch.object(tab, 'save', side_effect=OSError('not writable')), \
                        mock.patch.object(QMessageBox, 'critical') as error:
                    self.window._close_tab(0)
                error.assert_called_once_with(self.window, 'Save failed', 'not writable')
                self.assertIs(self.window.current(), tab)
                self.assertTrue(tab.dirty)
                with mock.patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
                    self.window._close_tab(0)
            self.assertEqual(path.read_text(encoding='utf-8'), 'keep this')
            self.assertIsNot(self.window.current(), tab)
            self.assertEqual(self.window.tabs.count(), 1)

    def test_close_tab_discard_and_dismiss(self):
        from PySide6.QtWidgets import QMessageBox
        tab = self.window.current()
        tab.editor.insertPlainText('discard this')
        with mock.patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.NoButton):
            self.window._close_tab(0)
        self.assertIs(self.window.current(), tab)

        def discard_answer(dialog):
            self.assertEqual(dialog.text(), 'Do you want to save changes to ‘Untitled.arc’ before closing?')
            return QMessageBox.StandardButton.Discard

        with mock.patch.object(QMessageBox, 'exec', discard_answer), \
                mock.patch.object(tab, 'save') as save:
            self.window._close_tab(0)
        save.assert_not_called()
        self.assertIsNot(self.window.current(), tab)
        self.assertEqual(self.window.current().source, '')

    def test_close_last_tab_recreates_one_document_and_invalid_index_is_safe(self):
        self.window._close_tab(-1)
        self.window._close_tab(100)
        self.assertEqual(self.window.tabs.count(), 1)
        for _ in range(3):
            self.window._close_tab(0)
            self.assertEqual(self.window.tabs.count(), 1)
            self.assertEqual(self.window.current().source, "")

    def test_cancel_open_and_save_as_leave_document_unchanged(self):
        from PySide6.QtWidgets import QFileDialog
        tab = self.window.current()
        tab.editor.insertPlainText("unsaved")
        for _ in range(2):
            with mock.patch.object(QFileDialog, "getOpenFileName", return_value=("", "")):
                self.window._open_dialog()
            with mock.patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
                self.window._save_current(True)
        self.assertIs(self.window.current(), tab)
        self.assertIsNone(tab.path)
        self.assertTrue(tab.dirty)
        self.assertEqual(tab.source, "unsaved")

    def test_reopen_selects_existing_dirty_document_without_reading_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.arc"
            path.write_text("original")
            tab = self.window.open_file(path)
            tab.editor.insertPlainText("edited ")
            for _ in range(3):
                with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("reopened")):
                    self.assertIs(self.window.open_file(path), tab)
            self.assertEqual(self.window.tabs.count(), 2)
            self.assertEqual(tab.source, "edited original")

    def test_failed_save_preserves_path_dirty_state_and_source(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        tab = self.window.current()
        tab.editor.insertPlainText("unsaved")
        with (mock.patch.object(QFileDialog, "getSaveFileName", return_value=("/missing/test.arc", "")),
              mock.patch.object(Path, "write_bytes", side_effect=OSError("read only")),
              mock.patch.object(QMessageBox, "critical") as error):
            self.window._save_current()
        error.assert_called_once()
        self.assertTrue(tab.dirty)
        self.assertIsNone(tab.path)
        self.assertEqual(tab.source, "unsaved")

    def test_save_and_undo_preserve_encoding_line_endings_and_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.arc"
            raw = b'\xef\xbb\xbf[Task]: item\r\n=> - Active\r\n'
            path.write_bytes(raw)
            tab = self.window.open_file(path)
            tab.editor.insertPlainText("🌍")
            self.window.undo_action.trigger()
            self.assertFalse(tab.dirty)
            self.assertEqual(tab.source.encode(tab.encoding), raw)
            self.window.redo_action.trigger()
            self.window._save_current()
            self.assertFalse(tab.dirty)
            self.assertEqual(path.read_bytes(), tab.source.encode(tab.encoding))
            self.assertEqual(tab.document.source, tab.source)
            self.assertIn("CRLF", tab.status_text())

    def test_arc_and_txt_roundtrip_and_startup(self):
        from PySide6.QtWidgets import QFileDialog
        from AgStudio.gui.app import OPEN_FILTERS
        raw = '\ufeffScope:\r\n- café 🌍\r\n'.encode('utf-8')
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ('.arc', '.txt', '.TXT'):
                path = Path(directory) / ('source' + suffix)
                path.write_bytes(raw)
                self.window.initialize_startup(path)
                tab = self.window.current()
                self.assertEqual(tab.path, path)
                self.window._save_current()
                self.assertEqual(path.read_bytes(), raw)
                with mock.patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path), '')) as dialog:
                    self.window._open_dialog()
                self.assertEqual(dialog.call_args.args[3], OPEN_FILTERS)
                self.assertIs(self.window.current(), tab)

    def test_save_as_extensions_and_filter_defaults(self):
        from PySide6.QtWidgets import QFileDialog
        from AgStudio.gui.app import ARC_FILTER, TEXT_FILTER
        with tempfile.TemporaryDirectory() as directory:
            cases = [('plain', ARC_FILTER, 'plain.arc'), ('text', TEXT_FILTER, 'text.txt'),
                     ('explicit.txt', ARC_FILTER, 'explicit.txt'),
                     ('explicit.arc', TEXT_FILTER, 'explicit.arc')]
            for name, selected, expected in cases:
                tab = self.window.new_document()
                tab.editor.setPlainText('café 🌍')
                with mock.patch.object(QFileDialog, 'getSaveFileName', return_value=(str(Path(directory) / name), selected)):
                    self.window._save_current(True)
                self.assertEqual(tab.path, Path(directory) / expected)
                self.assertEqual(tab.path.read_text(), 'café 🌍')
                self.assertEqual(self.window.tabs.tabText(self.window.tabs.indexOf(tab)), expected)
                with mock.patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')) as dialog:
                    self.window._save_current(True)
                self.assertEqual(dialog.call_args.args[4], TEXT_FILTER if expected.endswith('.txt') else ARC_FILTER)
            direct = self.window.new_document()
            self.assertEqual(direct.save(Path(directory) / 'direct').suffix, '.arc')

    def test_extensionless_overwrite_confirmation_and_unsupported_suffix(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from AgStudio.gui.app import TEXT_FILTER
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'existing.txt'
            path.write_text('original')
            tab = self.window.new_document()
            tab.editor.setPlainText('replacement')
            for answer in (QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes):
                with mock.patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path.with_suffix('')), TEXT_FILTER)), \
                     mock.patch.object(QMessageBox, 'question', return_value=answer) as confirm:
                    self.window._save_current(True)
                confirm.assert_called_once()
                if answer == QMessageBox.StandardButton.No:
                    self.assertIsNone(tab.path)
                    self.assertTrue(tab.dirty)
                    self.assertEqual(path.read_text(), 'original')
                else:
                    self.assertEqual(path.read_text(), 'replacement')
            with mock.patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path.with_suffix('.pdf')), TEXT_FILTER)), \
                 mock.patch.object(QMessageBox, 'critical') as error:
                self.window._save_current(True)
            error.assert_called_once()
            self.assertEqual(tab.path, path)
            self.assertFalse(path.with_suffix('.pdf').exists())

    def test_new_tab_button_stays_left_of_scrolling_tabs(self):
        from PySide6.QtCore import Qt
        button = self.window.tabs.cornerWidget(Qt.Corner.TopLeftCorner)
        self.assertIsNotNone(button)
        self.assertEqual(button.accessibleName(), 'New document')
        self.assertIsNone(self.window.tabs.cornerWidget(Qt.Corner.TopRightCorner))
        for _ in range(20):
            self.window.new_document()
        self.window.resize(550, 500)
        for index in (0, 10, 20):
            self.window.tabs.setCurrentIndex(index)
            self.app.processEvents()
            self.assertTrue(button.isVisible())
            self.assertLessEqual(button.geometry().right(), self.window.tabs.tabBar().tabRect(0).left())
        count = self.window.tabs.count()
        button.click()
        self.assertEqual(self.window.tabs.count(), count + 1)
        self.assertEqual(self.window.current().source, '')

    def test_error_list_column_headers_fit_text_without_changing_rows(self):
        from PySide6.QtWidgets import QHeaderView
        from AgStudio.gui.app import STUDIO_STYLE
        compact_rule = 'QTreeWidget#diagnosticTable QHeaderView::section { padding: 1px 7px; }'
        tab = self.window.current()
        tab.editor.setPlainText('=> - Act')
        header = tab.diagnostic_list.header()
        for font_size in (14, 18, 24):
            with self.subTest(font_size=font_size):
                style = STUDIO_STYLE + f"\nQWidget {{ font-size: {font_size}px; }}"
                self.window.setStyleSheet(style.replace(compact_rule, ''))
                self.app.processEvents()
                row_height = tab.diagnostic_list.sizeHintForRow(0)
                outline_height = tab.outline.header().sizeHint().height()
                old_height = header.height()
                self.window.setStyleSheet(style)
                self.app.processEvents()
                self.assertGreaterEqual(header.height(), header.fontMetrics().height())
                self.assertLessEqual(header.height(), header.fontMetrics().height() + 8)
                self.assertLess(header.height(), old_height)
                self.assertEqual(tab.diagnostic_list.sizeHintForRow(0), row_height)
                self.assertEqual(tab.outline.header().sizeHint().height(), outline_height)
                for column in range(5):
                    self.assertEqual(header.sectionResizeMode(column), QHeaderView.ResizeMode.ResizeToContents)
                    label = tab.diagnostic_list.headerItem().text(column)
                    self.assertGreaterEqual(header.sectionSize(column), header.fontMetrics().horizontalAdvance(label))

    def test_compact_status_bar_fits_text_and_size_grip(self):
        from PySide6.QtWidgets import QLabel, QSizeGrip
        from PySide6.QtTest import QTest
        from AgStudio.gui.app import STUDIO_STYLE
        status = self.window.statusBar()
        self.window.current().editor.setPlainText('Document\n')
        for font_size in (14, 18, 24):
            with self.subTest(font_size=font_size):
                self.window.setStyleSheet(STUDIO_STYLE + f"\nQWidget {{ font-size: {font_size}px; }}")
                self.app.processEvents()
                QTest.qWait(10)  # Allow posted font-change layout requests to settle.
                self.assertNotIn('ArcGrav', status.currentMessage())
                self.assertIn('utf-8', status.currentMessage())
                self.assertIn('LF', status.currentMessage())
                self.assertIn('Ln ', status.currentMessage())
                self.assertIn('Col ', status.currentMessage())
                self.assertGreaterEqual(status.height(), status.fontMetrics().height())
                self.assertLessEqual(status.height(), status.fontMetrics().height() + 8)
                self.assertEqual(status.findChildren(QLabel), [])
                self.window.current().editor.insertPlainText('changed')
                self.assertIn('modified', status.currentMessage())
                grip = status.findChild(QSizeGrip)
                self.assertTrue(grip.isVisible())
                self.assertGreaterEqual(grip.height(), grip.sizeHint().height())
                self.assertTrue(status.rect().contains(grip.geometry()))

    def test_compact_tabs_and_diagnostics_heading_do_not_clip_controls(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTabBar, QToolButton
        for font_size in (14, 18):
            with self.subTest(font_size=font_size):
                self.window.setStyleSheet(self.window.styleSheet() + f"\nQWidget {{ font-size: {font_size}px; }}")
                self.app.processEvents()
                bar = self.window.tabs.tabBar()
                plus = self.window.tabs.cornerWidget(Qt.Corner.TopLeftCorner)
                self.assertEqual(bar.tabRect(0).height(), plus.sizeHint().height())
                self.assertLessEqual(abs(plus.height() - bar.tabRect(0).height()), 1)
                close = bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
                self.assertIsNotNone(close)
                self.assertTrue(bar.tabRect(0).contains(close.geometry()))
                tab = self.window.current()
                heading = tab.diagnostics_heading.parentWidget()
                self.assertLessEqual(heading.height(), tab.diagnostics_heading.sizeHint().height() + 6)
                self.assertGreaterEqual(heading.height(), tab.diagnostics_heading.sizeHint().height())
                for control in heading.findChildren(QToolButton):
                    self.assertGreaterEqual(control.height(), control.fontMetrics().height())
                self.assertGreater(tab.diagnostic_list.height(), heading.height())


if __name__ == "__main__":
    unittest.main()
