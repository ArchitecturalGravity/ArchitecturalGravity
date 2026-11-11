"""Captured first-run layout with preference overrides and separate saved-file session restoration."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from AgStudio.gui.user_state import UserState, DEFAULT_LAYOUT, validated_layout
from AgStudio.gui.color_schemes import SchemeStore, default_scheme

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class InitialLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtCore import QSettings
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(str(Path(self.temp.name) / 'clean.ini'), QSettings.Format.IniFormat)
        self.store = SchemeStore(Path(self.temp.name) / 'colors')

    def window(self):
        from AgStudio.gui.app import StudioWindow
        window = StudioWindow('current', background=False, user_state=UserState(self.settings), scheme_store=self.store)
        self.addCleanup(window.deleteLater)
        window.initialize_startup(settings=self.settings)
        window.show()
        self.app.processEvents()
        return window

    def test_clean_profile_uses_captured_layout_and_only_helloworld(self):
        self.assertEqual(self.settings.allKeys(), [])
        window = self.window()
        tab = window.current()
        example = Path(__file__).resolve().parents[2] / 'examples/HelloWorld.arc'
        self.assertEqual(tab.source, example.read_text())
        self.assertEqual(tab.path, example.resolve())
        self.assertFalse(tab.dirty)
        self.assertEqual(window.size().toTuple(), (1180, 780))
        self.assertFalse(window.isMaximized())
        self.assertFalse(tab.side_panel.isHidden())
        self.assertFalse(tab.diagnostics_panel.isHidden())
        self.assertFalse(tab.document_map.isHidden())
        self.assertTrue(all(action.isChecked() for action in window.panel_actions.values()))
        self.assertTrue(tab.diagnostic_list.isHidden())
        self.assertEqual(tab.diagnostics_toggle.accessibleName(), 'Expand Finding List')
        self.assertEqual(tab.editor_map_split.sizes()[1], 130)
        self.assertEqual(tab.editor_split.sizes()[1], 275)
        # Removing the toolbar and compacting pane headings returns their
        # space to the editor instead of preserving the old 613-pixel budget.
        self.assertGreater(tab.editor.height(), 613)
        self.assertLessEqual(abs(tab.split.sizes()[1] - 23), 2)
        self.assertTrue(tab.document_map._fit)
        self.assertEqual(tab.document_map.scale, tab.document_map.minimum_scale)
        self.assertTrue(tab.find_bar.isHidden())
        self.assertFalse(any(item.isExpanded() for item in tab._outline_items.values()))
        self.assertEqual(window.color_scheme['spelling_underline']['foreground'], [255, 0, 0, 255])
        self.assertFalse(self.settings.contains(UserState.LAYOUT_KEY))
        new = window.new_document()
        self.app.processEvents()
        self.assertEqual(new.source, '')
        self.assertTrue(new.diagnostic_list.isHidden())
        self.assertEqual(new.editor_map_split.sizes()[1], 130)

    def test_existing_preferences_override_layout_panels_and_palette(self):
        state = UserState(self.settings)
        state.set_panel('side_panel', False)
        state.set_panel('error_list', False)
        state.set_panel('document_map', False)
        state.save_layout({**DEFAULT_LAYOUT, 'window_size': [1000, 650],
                           'editor_map_sizes': [600, 190], 'finding_collapsed': False,
                           'map_fit': False, 'map_scale': 1.0})
        custom = default_scheme()
        custom['spelling_underline']['foreground'] = [211, 47, 47, 255]
        self.store.select('Saved custom', custom)
        before = self.settings.value(UserState.LAYOUT_KEY)
        palette_before = (self.store.directory / 'selected.json').read_bytes()
        window = self.window()
        tab = window.current()
        self.assertEqual(window.size().toTuple(), (1000, 650))
        self.assertTrue(tab.side_panel.isHidden())
        self.assertTrue(tab.diagnostics_panel.isHidden())
        self.assertTrue(tab.document_map.isHidden())
        self.assertFalse(any(action.isChecked() for action in window.panel_actions.values()))
        self.assertFalse(tab.diagnostic_list.isHidden())
        self.assertFalse(tab.document_map._fit)
        self.assertEqual(window.color_scheme, custom)
        self.assertEqual(self.settings.value(UserState.LAYOUT_KEY), before)
        self.assertEqual((self.store.directory / 'selected.json').read_bytes(), palette_before)

    def test_saved_layout_and_session_reopen_without_screen_position(self):
        window = self.window()
        window.resize(1050, 720)
        tab = window.current()
        tab.editor_map_split.setSizes([650, 180])
        tab._toggle_diagnostics()
        tab.document_map._fit = False
        tab.document_map.scale = 1.0
        self.app.processEvents()
        expected_map = tab.editor_map_split.sizes()
        window.close()
        payload = json.loads(self.settings.value(UserState.LAYOUT_KEY))
        self.assertEqual(set(payload), {'version', *DEFAULT_LAYOUT})
        self.assertEqual(payload['window_size'], [1050, 720])
        self.assertEqual(payload['editor_map_sizes'], expected_map)
        self.assertFalse(payload['finding_collapsed'])
        restarted = self.window()
        self.assertEqual(restarted.size().toTuple(), (1050, 720))
        self.assertFalse(restarted.current().diagnostic_list.isHidden())
        self.assertFalse(restarted.current().document_map._fit)
        self.assertEqual(restarted.current().source, tab.source)
        self.assertEqual(restarted.current().path, tab.path)

    def test_hidden_map_preserves_width_zoom_and_layout_across_restart(self):
        from PySide6.QtGui import QTextCursor
        window = self.window()
        tab = window.current()
        source = 'Task:\n' + '- Keep exact text\n' * 100
        tab.editor.setPlainText(source)
        cursor = tab.editor.textCursor()
        cursor.setPosition(3)
        cursor.setPosition(12, QTextCursor.MoveMode.KeepAnchor)
        tab.editor.setTextCursor(cursor)
        tab.editor_map_split.setSizes([650, 190])
        tab.document_map.rebuild()
        tab.document_map._fit = False
        tab.document_map.scale = 0.75
        tab.document_map._clamp_scale()
        self.app.processEvents()
        sizes = tab.editor_map_split.sizes()
        scale = tab.document_map.scale
        document = (tab.source, tab.dirty, cursor.position(), cursor.anchor(), tab.editor.document().isUndoAvailable())
        for _ in range(3):
            window.panel_actions['document_map'].trigger()
            self.app.processEvents()
            self.assertTrue(tab.document_map.isHidden())
            self.assertEqual(tab.editor_map_split.sizes()[1], 0)
            window._save_current_layout()
            saved = json.loads(self.settings.value(UserState.LAYOUT_KEY))
            self.assertEqual(saved['editor_map_sizes'], sizes)
            self.assertFalse(saved['map_fit'])
            self.assertEqual(saved['map_scale'], scale)
            window.panel_actions['document_map'].trigger()
            self.app.processEvents()
            self.assertFalse(tab.document_map.isHidden())
            self.assertLessEqual(abs(tab.editor_map_split.sizes()[1] - sizes[1]), 1)
            self.assertFalse(tab.document_map._fit)
            self.assertEqual(tab.document_map.scale, scale)
        self.assertEqual((tab.source, tab.dirty, tab.editor.textCursor().position(), tab.editor.textCursor().anchor(),
                          tab.editor.document().isUndoAvailable()), document)
        window.panel_actions['document_map'].trigger()
        window._save_current_layout()
        restarted = self.window()
        restored = restarted.current()
        self.assertTrue(restored.document_map.isHidden())
        self.assertFalse(restarted.panel_actions['document_map'].isChecked())
        self.assertEqual(restarted.user_state.layout['editor_map_sizes'], sizes)
        # Supply the same document again; source/session restoration is not a preference.
        restored.editor.setPlainText(source)
        restarted._restore_current_layout()
        restarted.panel_actions['document_map'].trigger()
        self.app.processEvents()
        self.assertFalse(restored.document_map.isHidden())
        self.assertGreater(restored.editor_map_split.sizes()[1], 0)
        self.assertLessEqual(abs(restored.editor_map_split.sizes()[1] - sizes[1]), 1)
        self.assertFalse(restored.document_map._fit)
        self.assertEqual(restored.document_map.scale, scale)

    def test_invalid_layout_fields_fall_back_and_unknown_data_is_excluded(self):
        for saved in ('{', '[]', '{"version":true}', '{"version":2}'):
            self.settings.setValue(UserState.LAYOUT_KEY, saved)
            self.assertEqual(UserState(self.settings).layout, DEFAULT_LAYOUT)
        malformed = {'window_size': [-1, 780], 'map_scale': float('nan'),
                     'finding_collapsed': 'false', 'editor_map_sizes': [True, 10],
                     'file': 'coordinate-space-requirements.txt', 'source': 'unsaved'}
        self.assertEqual(validated_layout(malformed), DEFAULT_LAYOUT)
        self.assertEqual(validated_layout({'window_size': [900, 650]})['window_size'], [900, 650])
        state = UserState()
        state.layout['window_size'][0] = 900
        self.assertEqual(UserState().layout['window_size'], [1180, 780])


if __name__ == '__main__':
    unittest.main()
