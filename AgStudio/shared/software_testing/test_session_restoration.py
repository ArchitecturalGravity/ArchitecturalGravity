"""Document sessions preserve open work without changing source files."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = QSettings(str(self.root / 'prefs.ini'), QSettings.Format.IniFormat)
        self.settings.setValue('startup/helloWorldShown', True)
        self.settings.sync()
        self.windows = []
        self.addCleanup(self.dispose)

    def dispose(self):
        for window in self.windows:
            window._session_timer.stop()
            window._session_enabled = False
            for i in range(window.tabs.count()):
                window.tabs.widget(i).dispose_analysis()
            window.deleteLater()
        self.app.processEvents()

    def window(self, file=None):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        from AgStudio.gui.user_state import UserState
        window = StudioWindow('current', background=False, user_state=UserState(self.settings),
                              scheme_store=SchemeStore(self.root / 'colors'))
        self.windows.append(window)
        window.initialize_startup(file, settings=self.settings)
        window.show()
        self.app.processEvents()
        return window

    def file(self, name='one.arc', source='Task:\n' + '- text ' + 'wide ' * 100 + '\n'):
        path = self.root / name
        path.write_text(source, encoding='utf-8')
        return path

    def paths(self, window):
        return [window.tabs.widget(i).path for i in range(window.tabs.count())]

    def test_open_folder_tracks_successful_open_save_and_restart(self):
        from PySide6.QtWidgets import QFileDialog
        from AgStudio.gui import app
        examples = Path(app.__file__).resolve().parents[1] / 'examples'
        window = self.window()
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')) as picker:
            window._open_dialog()
        self.assertEqual(picker.call_args.args[2], str(examples))
        opened = self.file()
        window.open_file(opened)
        self.assertEqual(window._open_directory(), self.root)
        saved_folder = self.root / 'saved'
        saved_folder.mkdir()
        with patch.object(QFileDialog, 'getSaveFileName',
                          return_value=(str(saved_folder / 'copy.arc'), 'ArcGrav source (*.arc)')):
            self.assertTrue(window._save_tab(window.current(), save_as=True))
        # Restoring other tabs must not replace the last successful save folder.
        saved_tab = window.current()
        window.open_file(opened)
        self.assertTrue(window._save_tab(saved_tab))
        self.assertEqual(window._open_directory(), saved_folder)
        window.close()
        restarted = self.window()
        self.assertEqual(restarted._open_directory(), saved_folder)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')) as picker:
            restarted._open_dialog()
        self.assertEqual(picker.call_args.args[2], str(saved_folder))

    def test_open_folder_ignores_failed_or_canceled_operations(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        window = self.window(self.file())
        folder = window._open_directory()
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(self.root / 'missing' / 'x.arc'), '')), \
                patch.object(QMessageBox, 'critical'):
            window._open_dialog()
        with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            self.assertFalse(window._save_tab(window.current(), save_as=True))
        with patch.object(window.current(), 'save', side_effect=OSError('failed')), \
                patch.object(QMessageBox, 'critical'):
            self.assertFalse(window._save_tab(window.current()))
        self.assertEqual(window._open_directory(), folder)
        window.user_state.remember_file_directory(self.root / 'removed')
        self.assertEqual(window._open_directory().name, 'examples')

    def test_restart_order_active_and_both_tab_views(self):
        from PySide6.QtGui import QTextCursor
        one = self.file(source=('Task:\n' + '- ' + 'wide ' * 80 + '\n') * 80)
        two = self.file('two.txt', one.read_text())
        window = self.window(one)
        first = window.current()
        second = window.open_file(two)
        self.app.processEvents()
        for tab in (first, second):
            window.tabs.setCurrentWidget(tab)
            self.app.processEvents()
            cursor = tab.editor.textCursor()
            cursor.setPosition(500)
            cursor.setPosition(100, QTextCursor.MoveMode.KeepAnchor)
            tab.editor.setTextCursor(cursor)
            tab.editor.verticalScrollBar().setValue(40)
            tab.editor.horizontalScrollBar().setValue(70)
        window.tabs.tabBar().moveTab(1, 0)
        window.tabs.setCurrentWidget(first)
        self.app.processEvents()
        self.assertTrue(window.close())
        restored = self.window()
        self.assertEqual(self.paths(restored), [two, one])
        self.assertEqual(restored.current().path, one)
        for i in (1, 0):
            restored.tabs.setCurrentIndex(i)
            self.app.processEvents()
            editor = restored.current().editor
            self.assertEqual((editor.textCursor().anchor(), editor.textCursor().position()), (500, 100))
            self.assertEqual(editor.verticalScrollBar().value(), 40)
            self.assertEqual(editor.horizontalScrollBar().value(), 70)
            self.assertFalse(restored.current().dirty)

    def test_each_tab_retains_layout_after_restart(self):
        window = self.window(self.file())
        first = window.current()
        second = window.new_document()
        self.app.processEvents()
        expected = []
        for tab, collapsed, map_sizes, outline_sizes in (
                (first, True, [600, 200], [800, 300]),
                (second, False, [350, 450], [600, 500])):
            window.tabs.setCurrentWidget(tab)
            self.app.processEvents()
            if tab.diagnostic_list.isHidden() != collapsed:
                tab._toggle_diagnostics()
            tab.editor_split.setSizes(outline_sizes)
            tab.editor_map_split.setSizes(map_sizes)
            self.app.processEvents()
            expected.append((collapsed, tab.editor_map_split.sizes(), tab.editor_split.sizes()))
        # First tab must retain its separate layout while inactive at shutdown.
        window.tabs.setCurrentWidget(second)
        self.assertTrue(window.close())
        restored = self.window()
        # Also retain the inactive tab across a second checkpoint before visiting it.
        self.assertTrue(restored.close())
        restored = self.window()
        for index, (collapsed, map_sizes, outline_sizes) in enumerate(expected):
            restored.tabs.setCurrentIndex(index)
            self.app.processEvents()
            tab = restored.current()
            self.assertEqual(tab.diagnostic_list.isHidden(), collapsed)
            for actual, saved in ((tab.editor_map_split.sizes(), map_sizes),
                                  (tab.editor_split.sizes(), outline_sizes)):
                self.assertAlmostEqual(actual[0] / sum(actual), saved[0] / sum(saved), delta=0.02)

    def test_deleted_moved_and_external_changes_preserve_snapshot(self):
        one, two = self.file(), self.file('two.arc')
        original = two.read_text()
        window = self.window(one)
        window.open_file(two)
        window.close()
        one.rename(self.root / 'moved.arc')
        two.write_text('external change', encoding='utf-8')
        restored = self.window()
        self.assertEqual(self.paths(restored), [one, two])
        for index in range(2):
            self.assertEqual(restored.tabs.widget(index).source, original)
            self.assertTrue(restored.tabs.widget(index).dirty)
        self.assertEqual(two.read_text(), 'external change')
        self.assertFalse(one.exists())

    def test_unsaved_and_untitled_tabs_restore_without_prompt(self):
        from PySide6.QtWidgets import QMessageBox
        path = self.file()
        original = path.read_bytes()
        window = self.window(path)
        window.current().editor.insertPlainText('SAVED FILE EDIT')
        edited = window.current().source
        window.new_document().editor.setPlainText('DRAFT ONE')
        window.new_document().editor.setPlainText('DRAFT TWO')
        window.tabs.setCurrentIndex(1)
        with patch.object(QMessageBox, 'question') as prompt:
            self.assertTrue(window.close())
        prompt.assert_not_called()
        restored = self.window()
        self.assertEqual(self.paths(restored), [path, None, None])
        self.assertEqual(restored.tabs.currentIndex(), 1)
        self.assertEqual([restored.tabs.widget(i).source for i in range(3)],
                         [edited, 'DRAFT ONE', 'DRAFT TWO'])
        self.assertTrue(all(restored.tabs.widget(i).dirty for i in range(3)))
        self.assertEqual(path.read_bytes(), original)
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Discard):
            restored._close_tab(1)
        restored.close()
        again = self.window()
        self.assertEqual([again.tabs.widget(i).source for i in range(2)], [edited, 'DRAFT TWO'])

    def test_failed_checkpoint_prevents_window_close(self):
        from PySide6.QtWidgets import QMessageBox
        window = self.window(self.file())
        window.current().editor.insertPlainText('keep this edit')
        before = window.session_store.path.read_bytes()
        window.session_store.error = 'read only'
        with patch.object(window.session_store, 'save', return_value=False), \
                patch.object(QMessageBox, 'critical') as error:
            self.assertFalse(window.close())
        error.assert_called_once()
        self.assertTrue(window._session_enabled)
        self.assertTrue(window.current().dirty)
        self.assertEqual(window.session_store.path.read_bytes(), before)
        self.assertTrue(window.close())
        self.assertIn('keep this edit', self.window().current().source)

    def test_command_line_merges_deduplicates_and_selects(self):
        from PySide6.QtWidgets import QMessageBox
        one, two = self.file(), self.file('two.arc')
        self.window(one).close()
        restored = self.window(two)
        self.assertEqual(self.paths(restored), [one, two])
        self.assertEqual(restored.current().path, two)
        restored.close()
        same = self.window(one)
        self.assertEqual(self.paths(same), [one, two])
        self.assertEqual(same.current().path, one)
        same.close()
        with patch.object(QMessageBox, 'critical') as error:
            failed = self.window(self.root / 'missing.arc')
        error.assert_called_once()
        self.assertEqual(self.paths(failed), [one, two])

    def test_malformed_metadata_and_unknown_versions(self):
        from AgStudio.gui.session_state import SessionStore
        from AgStudio.gui.session_state import validated_session
        store = SessionStore(self.settings)
        for data in ('{', '[]', '{"version":true}', '{"version":99,"tabs":[]}',
                     '{"version":1,"tabs":[null,{"path":7},{"path":"relative.arc"}]}'):
            store.path.write_text(data)
            window = self.window()
            self.assertEqual(self.paths(window), [None])
            window.close()
        value = validated_session({'version': 1, 'tabs': [
            {'path': str(self.file()), 'anchor': -2, 'position': True, 'vertical': 'bad',
             'horizontal': 999999999999, 'source': 'SECRET'}], 'active': []})
        self.assertEqual(set(value['tabs'][0]), {'path', 'anchor', 'position', 'vertical', 'horizontal'})
        self.assertEqual(value['tabs'][0]['position'], 0)

    def test_legacy_session_migration_and_untitled_active_restore(self):
        from AgStudio.gui.session_state import SessionStore
        one = self.file()
        invalid = self.file('invalid.arc')
        invalid.write_bytes(b'\xff\xfe')
        store = SessionStore(self.settings)
        store.save({'version': 1, 'tabs': [{'path': str(one)}, {'path': str(one)},
                                         {'path': str(invalid)}], 'active': str(invalid)})
        window = self.window()
        self.assertEqual(self.paths(window), [one])
        window.new_document()
        window.close()
        restored = self.window()
        self.assertEqual(self.paths(restored), [one, None])
        self.assertIsNone(restored.current().path)
        self.assertFalse(restored.current().dirty)

    def test_tab_move_and_close_are_checkpointed_during_use(self):
        from PySide6.QtTest import QTest
        one, two = self.file(), self.file('two.arc')
        window = self.window(one)
        window.open_file(two)
        QTest.qWait(600)
        window.tabs.tabBar().moveTab(1, 0)
        QTest.qWait(600)
        self.assertEqual([tab['path'] for tab in window.session_store.load()['tabs']],
                         [str(two), str(one)])
        window._close_tab(1)
        QTest.qWait(600)
        self.assertEqual([tab['path'] for tab in window.session_store.load()['tabs']], [str(two)])

    def test_cursor_only_activity_is_checkpointed_without_close(self):
        from PySide6.QtTest import QTest
        window = self.window(self.file())
        QTest.qWait(600)
        for position in range(1, 10):
            cursor = window.current().editor.textCursor()
            cursor.setPosition(position)
            window.current().editor.setTextCursor(cursor)
            QTest.qWait(100)
        # Continuous movement must have written a checkpoint before it stops.
        saved = window.session_store.load()['tabs'][0]['position']
        self.assertGreaterEqual(saved, 4)
        QTest.qWait(600)
        self.assertEqual(window.session_store.load()['tabs'][0]['position'], 9)

    def test_save_as_is_checkpointed(self):
        from PySide6.QtTest import QTest
        window = self.window()
        path = self.root / 'saved.arc'
        window.current().editor.setPlainText('Task:\n- saved')
        with patch('AgStudio.gui.app.QFileDialog.getSaveFileName', return_value=(str(path), 'ArcGrav (*.arc)')):
            window._save_current()
        QTest.qWait(600)
        self.assertEqual(window.session_store.load()['tabs'][0]['path'], str(path))

    def test_atomic_failure_keeps_previous_metadata(self):
        window = self.window(self.file())
        store = window.session_store
        before = store.path.read_bytes()
        with patch('AgStudio.gui.session_state.QSaveFile') as factory:
            factory.return_value.open.return_value = False
            factory.return_value.errorString.return_value = 'read only'
            self.assertFalse(store.save({'version': 1, 'tabs': []}))
        self.assertEqual(store.path.read_bytes(), before)
        self.assertEqual(store.error, 'read only')

    def test_abnormal_exit_keeps_bounded_source_checkpoint(self):
        from AgStudio.gui.session_state import SessionStore
        path = self.file()
        script = '''
import os, sys
from pathlib import Path
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication
from AgStudio.gui.app import StudioWindow
from AgStudio.gui.user_state import UserState
from AgStudio.gui.color_schemes import SchemeStore
app = QApplication([])
settings = QSettings(sys.argv[1], QSettings.Format.IniFormat)
w = StudioWindow('current', background=False, user_state=UserState(settings), scheme_store=SchemeStore(sys.argv[3]))
w.initialize_startup(Path(sys.argv[2]), settings=settings)
w.show()
def edit():
    w.current().editor.insertPlainText('PRIVATE UNSAVED')
    c = w.current().editor.textCursor()
    c.setPosition(8)
    w.current().editor.setTextCursor(c)
QTimer.singleShot(50, edit)
QTimer.singleShot(900, lambda: os._exit(23))
app.exec()
'''
        result = subprocess.run([sys.executable, '-c', script, self.settings.fileName(), str(path),
                                 str(self.root / 'colors')], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 23, result.stderr.decode())
        store = SessionStore(self.settings)
        self.assertIn('PRIVATE', store.path.read_text())
        restored = self.window()
        self.assertEqual(restored.current().path, path)
        self.assertEqual(restored.current().source, 'PRIVATE UNSAVED' + path.read_text())
        self.assertTrue(restored.current().dirty)
        self.assertEqual(restored.current().editor.textCursor().position(), 8)


if __name__ == '__main__':
    unittest.main()
