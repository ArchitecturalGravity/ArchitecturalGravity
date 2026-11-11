"""Persistent, live-preview colors for the Infer Map's visible-editor overlay."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from AgStudio.gui.color_schemes import SchemeStore, SYNTAX_ROLES, default_scheme, validate_scheme


class MapViewportSchemeTests(unittest.TestCase):
    def test_defaults_match_shipped_palette_and_are_not_syntax(self):
        # Default.json is authoritative, including user-tuned overlay opacity.
        path = Path(__file__).resolve().parents[2] / 'color_schemes' / 'Default.json'
        shipped = json.loads(path.read_text(encoding='utf-8'))['colors']['map_viewport']
        self.assertEqual(default_scheme()['map_viewport'], shipped)
        self.assertNotIn('map_viewport', SYNTAX_ROLES)

    def test_legacy_named_default_and_selected_palettes_migrate_without_rewrites(self):
        old = default_scheme()
        del old['map_viewport']
        old['editor']['background'] = [1, 2, 3, 4]
        original = deepcopy(old)
        expected = validate_scheme(old)
        self.assertEqual(old, original)
        self.assertEqual(expected['editor'], old['editor'])
        self.assertEqual(expected['map_viewport'], default_scheme()['map_viewport'])
        with tempfile.TemporaryDirectory() as directory:
            store = SchemeStore(directory)
            for name in ('Legacy', 'Default'):
                path = store.path(name)
                path.write_text(json.dumps({'version': 1, 'name': name, 'colors': old}))
                before = path.read_bytes()
                self.assertEqual(store.load(name), expected)
                self.assertEqual(path.read_bytes(), before)
            path = Path(directory) / 'selected.json'
            path.write_text(json.dumps({'version': 1, 'name': 'Legacy', 'colors': old}))
            before = path.read_bytes()
            self.assertEqual(store.selected(), ('Legacy', expected, None))
            self.assertEqual(path.read_bytes(), before)

    def test_custom_border_fill_alpha_round_trip_and_validation(self):
        scheme = default_scheme()
        scheme['map_viewport'] = {'foreground': [12, 34, 56, 78], 'background': [98, 76, 54, 32]}
        with tempfile.TemporaryDirectory() as directory:
            store = SchemeStore(directory)
            store.save('Viewport', scheme)
            store.select('Viewport', scheme)
            self.assertEqual(store.load('Viewport'), scheme)
            self.assertEqual(store.selected(), ('Viewport', scheme, None))
        for kind in ('foreground', 'background'):
            for invalid in ([0, 0, 0], [0, 0, 0, 256], [0, 0, 0, True]):
                bad = deepcopy(scheme)
                bad['map_viewport'][kind] = invalid
                with self.assertRaises(ValueError):
                    validate_scheme(bad)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class MapViewportColorGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.user_state import UserState
        self.directory = tempfile.TemporaryDirectory()
        self.store = SchemeStore(self.directory.name)
        self.window = StudioWindow('current', background=False,
                                   scheme_store=self.store, user_state=UserState())
        self.window.resize(1200, 800)
        self.window.show()
        self.dialogs = []
        self.app.processEvents()

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox
        for dialog in self.dialogs:
            dialog.reject()
            dialog.deleteLater()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def dialog(self):
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        dialog = ColorSchemeDialog(self.window)
        self.dialogs.append(dialog)
        dialog.roles.setCurrentIndex(dialog.roles.findData('map_viewport'))
        return dialog

    def set_colors(self, dialog, border, fill):
        for kind, color in (('foreground', border), ('background', fill)):
            for spin, value in zip(dialog.controls[kind], color):
                spin.setValue(value)
        self.app.processEvents()

    def test_live_preview_cancel_apply_reload_new_tabs_and_role_labels(self):
        tab = self.window.current()
        tab.editor.insertPlainText('Task: preserve unsaved text\n')
        source, dirty, undo, analysis = (tab.source, tab.dirty,
                                        tab.editor.document().availableUndoSteps(), tab.analysis)
        original = deepcopy(self.window.color_scheme)
        border, fill = [200, 10, 20, 240], [30, 90, 210, 70]
        dialog = self.dialog()
        self.assertEqual(dialog.roles.currentText(), 'Infer Map — Visible Editor Area')
        for kind, label in (('foreground', 'Border color'), ('background', 'Fill color')):
            self.assertEqual(dialog.color_buttons[kind].parentWidget().title(), label)
            self.assertTrue(dialog.color_buttons[kind].parentWidget().isEnabled())
            self.assertEqual(dialog.controls[kind][3].accessibleName(), label + ' Alpha (0–255)')
        self.set_colors(dialog, border, fill)
        expected = {'foreground': border, 'background': fill}
        self.assertEqual(tab.editor.color_scheme['map_viewport'], expected)
        second = self.window.new_document()
        self.assertEqual(second.editor.color_scheme['map_viewport'], expected)
        dialog.reject()
        self.assertEqual(tab.editor.color_scheme, original)
        self.assertEqual(second.editor.color_scheme, original)
        dialog = self.dialog()
        self.set_colors(dialog, border, fill)
        self.assertTrue(dialog.apply_scheme())
        self.store.save('Viewport', dialog.working)
        dialog.reset_default()
        self.assertEqual(tab.editor.color_scheme['map_viewport'], default_scheme()['map_viewport'])
        dialog.refresh_names()
        dialog.schemes.setCurrentText('Viewport')
        dialog.load_scheme()
        self.assertEqual(tab.editor.color_scheme['map_viewport'], expected)
        dialog.roles.setCurrentIndex(dialog.roles.findData('editor'))
        self.assertEqual(dialog.color_buttons['foreground'].parentWidget().title(), 'Character color')
        self.assertEqual(dialog.color_buttons['background'].parentWidget().title(), 'Background color')
        dialog.reject()
        self.assertEqual(tab.editor.color_scheme['map_viewport'], expected)
        self.assertEqual(SchemeStore(self.directory.name).selected()[1]['map_viewport'], expected)
        self.assertEqual((tab.source, tab.dirty, tab.editor.document().availableUndoSteps(), tab.analysis),
                         (source, dirty, undo, analysis))

    def test_border_and_fill_pickers_preview_alpha_and_cancel_independently(self):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog, QDialog
        dialog = self.dialog()
        original = deepcopy(self.window.color_scheme)
        for kind, title in (('foreground', 'Border color'), ('background', 'Fill color')):
            observed = []
            def execute(picker):
                self.assertEqual(picker.windowTitle(), 'Choose ' + title.lower())
                self.assertTrue(picker.testOption(QColorDialog.ColorDialogOption.ShowAlphaChannel))
                picker.setCurrentColor(QColor(11, 22, 33, 44))
                observed.append(deepcopy(self.window.current().editor.color_scheme['map_viewport'][kind]))
                return QDialog.DialogCode.Rejected
            with patch.object(QColorDialog, 'exec', execute):
                dialog.choose_color(kind)
            self.assertEqual(observed, [[11, 22, 33, 44]])
            self.assertEqual(self.window.color_scheme, original)
            self.assertEqual(dialog.working, original)

    def test_rendered_border_fill_and_transparency_follow_live_scheme_in_every_mode(self):
        from PySide6.QtCore import QRectF
        from AgStudio.gui.inference_heat import MODE_LABELS
        tab = self.window.current()
        view = tab.document_map
        scheme = deepcopy(self.window.color_scheme)
        scheme['editor']['background'] = [20, 40, 60, 255]
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab.set_inference_mode(mode)
                self.app.processEvents()
                rectangle = QRectF(10, 20, view.width() - 20, 100)
                # Keep content independent from the overlay under test.
                with patch.object(view, 'mapped_viewport', return_value=rectangle), \
                     patch.object(view, 'shapes', ()), patch.object(view, '_display_segments', False):
                    scheme['map_viewport'] = {'foreground': [220, 30, 40, 255],
                                              'background': [40, 180, 70, 255]}
                    self.window.apply_color_scheme(scheme)
                    self.app.processEvents()
                    image = view.grab().toImage()
                    x = view.width() // 2
                    self.assertEqual(image.pixelColor(x, 20).getRgb(), (220, 30, 40, 255))
                    self.assertEqual(image.pixelColor(x, 60).getRgb(), (40, 180, 70, 255))
                    scheme['map_viewport']['foreground'][3] = 0
                    scheme['map_viewport']['background'][3] = 0
                    self.window.apply_color_scheme(scheme)
                    transparent = view.grab().toImage()
                    self.assertEqual(transparent.pixelColor(x, 20).getRgb(), (20, 40, 60, 255))
                    self.assertEqual(transparent.pixelColor(x, 60).getRgb(), (20, 40, 60, 255))
                    scheme['map_viewport']['background'] = [220, 40, 60, 128]
                    self.window.apply_color_scheme(scheme)
                    translucent = view.grab().toImage().pixelColor(x, 60).getRgb()
                    self.assertLessEqual(abs(translucent[0] - 120), 1)
                    self.assertEqual(translucent[1:], (40, 60, 255))
