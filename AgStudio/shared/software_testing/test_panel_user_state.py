"""Application panel preferences survive document changes and restart."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from AgStudio.gui.user_state import UserState

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class PanelStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        from AgStudio.gui.color_schemes import SchemeStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(str(Path(self.temp.name) / 'state.ini'), QSettings.Format.IniFormat)
        self.store = SchemeStore(Path(self.temp.name) / 'colors')

    def window(self):
        from AgStudio.gui.app import StudioWindow
        window = StudioWindow('current', background=False, scheme_store=self.store, user_state=UserState(self.settings))
        window.resize(1180, 780)
        window.show()
        self.addCleanup(window.deleteLater)
        self.app.processEvents()
        return window

    def check(self, window, side, errors, document_map=True):
        expected = {'side_panel': side, 'error_list': errors, 'document_map': document_map}
        self.assertEqual(window.user_state.panels, expected)
        self.assertEqual({name: action.isChecked() for name, action in window.panel_actions.items()}, expected)
        for i in range(window.tabs.count()):
            tab = window.tabs.widget(i)
            self.assertEqual(not tab.side_panel.isHidden(), side)
            self.assertEqual(not tab.diagnostics_panel.isHidden(), errors)
            self.assertEqual(not tab.document_map.isHidden(), document_map)

    def test_first_run_independent_choices_all_documents_restart_and_actions(self):
        from PySide6.QtGui import QTextCursor
        window = self.window()
        self.check(window, True, True, True)
        first = window.current()
        first.editor.insertPlainText('unsaved 🌍')
        cursor = first.editor.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        first.editor.setTextCursor(cursor)
        before = (first.source, first.dirty, cursor.position(), cursor.anchor(),
                  first.editor.document().isUndoAvailable())
        window.panel_actions['side_panel'].trigger()
        self.check(window, False, True, True)
        second = window.new_document()
        self.check(window, False, True, True)
        window.panel_actions['document_map'].trigger()
        self.check(window, False, True, False)
        path = Path(self.temp.name) / 'file.txt'
        path.write_text('[A]: value\n', encoding='utf-8')
        opened = window.open_file(path)
        self.assertIs(window.open_file(path), opened)
        opened.refresh_model()
        window.tabs.setCurrentWidget(first)
        self.check(window, False, True, False)
        self.assertEqual((first.source, first.dirty, first.editor.textCursor().position(),
                          first.editor.textCursor().anchor(), first.editor.document().isUndoAvailable()), before)
        window.panel_actions['error_list'].trigger()
        self.check(window, False, False, False)
        restarted = self.window()
        self.check(restarted, False, False, False)
        actions = {a.text(): a for a in restarted.view_menu.actions()}
        actions['Outline'].trigger()
        self.check(restarted, True, False, False)
        actions['Finding List'].trigger()
        self.check(restarted, True, True, False)
        actions['Infer Map'].trigger()
        self.check(restarted, True, True, True)
        self.check(self.window(), True, True, True)
        self.assertFalse(any(item.isExpanded() for item in restarted.current()._outline_items.values()))
        # Neither parent-window hiding nor inactive tabs can save a false preference.
        before = self.settings.value(UserState.KEY)
        restarted.hide()
        window.tabs.setCurrentWidget(second)
        self.assertEqual(self.settings.value(UserState.KEY), before)

    def test_programmatic_visibility_syncs_actions_and_show_helpers_are_idempotent(self):
        window = self.window()
        window.new_document()
        for key in window.panel_actions:
            for visible in (False, False, True, True):
                window._set_panel_visibility(key, visible)
                expected = {**window.user_state.panels, key: visible}
                self.check(window, expected['side_panel'], expected['error_list'], expected['document_map'])
        for helper, key in ((window._show_side_panel, 'side_panel'),
                            (window._show_diagnostics, 'error_list')):
            window._set_panel_visibility(key, False)
            for _ in range(3):
                helper()
                self.assertTrue(window.panel_actions[key].isChecked())
                self.assertTrue(window.user_state.panels[key])
        self.check(window, True, True, True)

    def test_invalid_missing_and_partial_state_defaults_are_safe(self):
        defaults = {'side_panel': True, 'error_list': True, 'document_map': True}
        for saved in (None, '{', '[]', 'null', '{}', '{"version":2,"side_panel":false}',
                      '{"version":true,"side_panel":false}'):
            with self.subTest(saved=saved):
                if saved is None:
                    self.settings.remove(UserState.KEY)
                else:
                    self.settings.setValue(UserState.KEY, saved)
                self.assertEqual(UserState(self.settings).panels, defaults)
        self.settings.setValue(UserState.KEY, json.dumps({'version': 1, 'side_panel': False, 'error_list': 'false'}))
        before = self.settings.value(UserState.KEY)
        state = UserState(self.settings)
        self.assertEqual(state.panels, {'side_panel': False, 'error_list': True, 'document_map': True})
        self.assertEqual(self.settings.value(UserState.KEY), before)
        state.set_panel('error_list', False)
        state.set_panel('document_map', False)
        self.assertEqual(UserState(self.settings).panels, {'side_panel': False, 'error_list': False, 'document_map': False})
        self.assertEqual(json.loads(self.settings.value(UserState.KEY)),
                         {'version': 1, 'side_panel': False, 'error_list': False, 'document_map': False})
        for invalid in ('false', 0, None, [], {}):
            with self.subTest(document_map=invalid):
                self.settings.setValue(UserState.KEY, json.dumps({'version': 1, 'document_map': invalid}))
                self.assertEqual(UserState(self.settings).panels, defaults)

    def test_old_version_one_state_defaults_document_map_open_without_rewriting(self):
        old = json.dumps({'version': 1, 'side_panel': False, 'error_list': False})
        self.settings.setValue(UserState.KEY, old)
        window = self.window()
        self.check(window, False, False, True)
        self.assertEqual(self.settings.value(UserState.KEY), old)
        window.panel_actions['document_map'].trigger()
        saved = json.loads(self.settings.value(UserState.KEY))
        self.assertEqual(saved, {'version': 1, 'side_panel': False, 'error_list': False, 'document_map': False})
