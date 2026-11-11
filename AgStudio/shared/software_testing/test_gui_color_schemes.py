"""Editable RGBA schemes preserve source, support live rollback and safe storage."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from AgStudio.gui.color_schemes import SchemeStore, default_scheme, validate_scheme, ROLE_LABELS
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

class SchemeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SchemeStore(self.temp.name)

    def test_roundtrip_and_selection(self):
        scheme = default_scheme()
        scheme['symbol']['foreground'] = [1, 2, 3, 4]
        scheme['symbol']['background'] = [250, 251, 252, 253]
        self.store.save('Ocean 2', scheme)
        self.assertEqual(self.store.load('Ocean 2'), scheme)
        self.assertEqual(self.store.names(), ['Default', 'Ocean 2'])
        self.store.select('Ocean 2', scheme)
        self.assertEqual(self.store.selected(), ('Ocean 2', scheme, None))
        self.assertEqual(self.store.names(), ['Default', 'Ocean 2'])
        self.assertEqual(json.loads((Path(self.temp.name) / 'Ocean 2.json').read_text())['version'], 1)

    def test_child_opacity_validation_legacy_and_roundtrip(self):
        old = default_scheme()
        del old['deepest_child_opacity']
        self.assertEqual(validate_scheme(old)['deepest_child_opacity'], default_scheme()['deepest_child_opacity'])
        self.assertNotIn('deepest_child_opacity', old)
        for value in (0, 25, 67, 100):
            scheme = {**old, 'deepest_child_opacity': value}
            self.store.save('Opacity', scheme)
            self.assertEqual(self.store.load('Opacity'), scheme)
            self.store.select('Opacity', scheme)
            self.assertEqual(self.store.selected()[1], scheme)
        for invalid in (-1, 101, True, 25.5, '25', None):
            with self.assertRaises(ValueError):
                validate_scheme({**old, 'deepest_child_opacity': invalid})

    def test_spelling_underline_migration_and_persistence(self):
        from copy import deepcopy
        from AgStudio.gui.color_schemes import SYNTAX_ROLES
        original = default_scheme()
        self.assertEqual(original['spelling_underline']['foreground'], [255, 0, 0, 255])
        self.assertNotIn('spelling_underline', SYNTAX_ROLES)
        old = deepcopy(original)
        del old['spelling_underline']
        old['editor']['foreground'] = [1, 2, 3, 4]
        migrated = validate_scheme(old)
        self.assertEqual(migrated['editor'], old['editor'])
        self.assertEqual(migrated['spelling_underline'], original['spelling_underline'])
        for name in ('Legacy', 'Default'):
            path = self.store.path(name)
            path.write_text(json.dumps({'version': 1, 'name': name, 'colors': old}))
            before = path.read_bytes()
            self.assertEqual(self.store.load(name), migrated)
            self.assertEqual(path.read_bytes(), before)
        migrated['spelling_underline']['foreground'] = [11, 22, 33, 44]
        self.store.save('Spelling', migrated)
        self.store.select('Spelling', migrated)
        self.assertEqual(self.store.load('Spelling'), migrated)
        self.assertEqual(SchemeStore(self.temp.name).selected(), ('Spelling', migrated, None))

    def test_names_and_defaults_are_safe(self):
        for name in ['default', '../evil', '/tmp/x', 'a/b', 'a\\b', '', ' a', 'a ', 'CON', 'selected']:
            with self.assertRaises(ValueError):
                self.store.save(name, default_scheme())
        first = default_scheme()
        first['symbol']['foreground'][0] = (first['symbol']['foreground'][0] + 1) % 256
        self.assertNotEqual(first, default_scheme())
        self.assertEqual(self.store.load('Default'), default_scheme())

    def test_bad_colors_and_unknown_roles_rejected(self):
        for bad in [[0, 0, 0], [0, 0, 0, 256], [0, 0, 0, -1], [0, 0, 0, True], [0, 0, 0, 0.1]]:
            value = default_scheme()
            value['symbol']['foreground'] = bad
            with self.assertRaises(ValueError):
                validate_scheme(value)
        value = default_scheme()
        value['invented_keyword'] = value['symbol']
        with self.assertRaises(ValueError):
            validate_scheme(value)

    def test_malformed_and_version_fallback(self):
        path = Path(self.temp.name) / 'selected.json'
        for contents in ['[', '{}', '{"version": 2}', 'null']:
            path.write_text(contents)
            name, colors, error = self.store.selected()
            self.assertEqual((name, colors), ('Default', default_scheme()))
            self.assertTrue(error)
        self.store.save('Valid', default_scheme())
        path = self.store.path('Valid')
        value = json.loads(path.read_text())
        value['version'] = 2
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.store.load('Valid')

    def test_failed_atomic_replace_preserves_previous_file(self):
        path = self.store.save('Safe', default_scheme())
        before = path.read_bytes()
        with patch('AgStudio.gui.color_schemes.os.replace', side_effect=OSError('denied')):
            with self.assertRaises(OSError):
                self.store.save('Safe', default_scheme())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(Path(self.temp.name).glob('*.tmp')), [])

@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class SchemeGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SchemeStore(self.temp.name)
        self.window = StudioWindow('current', user_state=UserState(), background=False, scheme_store=self.store)
        self.addCleanup(self.window.deleteLater)

    def dialog(self):
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        result = ColorSchemeDialog(self.window)
        self.addCleanup(result.deleteLater)
        return result

    def test_spelling_underline_live_apply_cancel_load_and_new_tabs(self):
        tab = self.window.current()
        source = 'Task: Please recieve text\n'
        tab.editor.setPlainText(source)
        original = (255, 0, 0, 255)
        def underline(editor):
            return editor._spelling_selections[0].format.underlineColor().getRgb()
        self.assertEqual(underline(tab.editor), original)
        analysis = tab.analysis
        dialog = self.dialog()
        dialog.roles.setCurrentIndex(dialog.roles.findData('spelling_underline'))
        self.assertIn('Misspelled word underline', dialog.roles.currentText())
        self.assertEqual(dialog.color_buttons['foreground'].parentWidget().title(), 'Underline color')
        self.assertFalse(dialog.color_buttons['background'].parentWidget().isEnabled())
        color = (11, 222, 33, 144)
        for spin, value in zip(dialog.controls['foreground'], color):
            spin.setValue(value)
        self.assertEqual(underline(tab.editor), color)
        self.assertEqual(underline(dialog.preview), color)
        self.assertIs(tab.analysis, analysis)
        self.assertEqual(tab.source, source)
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 1)
        self.assertEqual(tab.diagnostic_list.topLevelItem(0).text(0), 'Warning')
        dialog.reject()
        self.assertEqual(underline(tab.editor), original)
        dialog = self.dialog()
        dialog.roles.setCurrentIndex(dialog.roles.findData('spelling_underline'))
        for spin, value in zip(dialog.controls['foreground'], color):
            spin.setValue(value)
        self.assertTrue(dialog.apply_scheme())
        self.store.save('Spelling', dialog.working)
        dialog.reset_default()
        self.assertEqual(underline(tab.editor), original)
        dialog.refresh_names()
        dialog.schemes.setCurrentText('Spelling')
        dialog.load_scheme()
        self.assertEqual(underline(tab.editor), color)
        dialog.controls['foreground'][3].setValue(0)
        self.assertEqual(underline(tab.editor)[3], 0)
        dialog.reject()
        self.assertEqual(underline(tab.editor), color)
        other = self.window.new_document()
        other.editor.setPlainText(source)
        self.assertEqual(underline(other.editor), color)
        self.assertEqual(self.store.selected()[1]['spelling_underline']['foreground'], list(color))

    def test_child_opacity_slider_live_cancel_apply_load_and_reset(self):
        tab = self.window.current()
        tab.editor.setPlainText('Task:\n- Child')
        scheme = default_scheme()
        scheme['active_row']['background'] = [40, 80, 120, 200]
        self.window.apply_color_scheme(scheme, 'Custom')
        analysis = tab.analysis
        dialog = self.dialog()
        self.assertEqual((dialog.child_opacity.minimum(), dialog.child_opacity.maximum()), (0, 100))
        for value in (0, 25, 67, 100):
            dialog.child_opacity.setValue(value)
            self.assertEqual(dialog.child_opacity_value.text(), f'{value}%')
            rows = tab.editor.extraSelections()
            self.assertEqual(rows[0].format.background().color().getRgb(), (40, 80, 120, 200))
            self.assertEqual(rows[-1].format.background().color().getRgb(), (40, 80, 120, round(200 * value / 100)))
            self.assertIs(tab.analysis, analysis)
        cursor = tab.editor.textCursor()
        cursor.setPosition(len('Task:\n'))
        tab.editor.setTextCursor(cursor)
        dialog.child_opacity.setValue(0)
        rows = tab.editor.extraSelections()
        self.assertEqual(rows[0].format.background().color().alpha(), 200)
        dialog.reject()
        self.assertEqual(self.window.color_scheme['deepest_child_opacity'], scheme['deepest_child_opacity'])
        dialog = self.dialog()
        dialog.child_opacity.setValue(67)
        self.assertTrue(dialog.apply_scheme())
        self.assertEqual(self.store.selected()[1]['deepest_child_opacity'], 67)
        self.store.save('Saved opacity', dialog.working)
        dialog.reset_default()
        self.assertEqual(dialog.child_opacity.value(), default_scheme()['deepest_child_opacity'])
        dialog.refresh_names()
        dialog.schemes.setCurrentText('Saved opacity')
        dialog.load_scheme()
        self.assertEqual(dialog.child_opacity.value(), 67)
        dialog.child_opacity.setValue(0)
        dialog.reject()
        self.assertEqual(self.window.color_scheme['deepest_child_opacity'], 67)

    def test_default_is_listed_once_and_failed_reset_preserves_live_document(self):
        dialog = self.dialog()
        self.assertEqual([dialog.schemes.itemText(i) for i in range(dialog.schemes.count())].count('Default'), 1)
        tab = self.window.current()
        tab.editor.insertPlainText('unsaved content')
        before = (tab.source, tab.dirty, tab.editor.document().isUndoAvailable())
        colors = self.window.color_scheme.copy()
        with patch.object(self.store, 'load', side_effect=ValueError('Restore Default.json')), \
             patch('AgStudio.gui.color_scheme_dialog.QMessageBox.warning') as warning:
            dialog.reset_default()
            warning.assert_called_once()
        self.assertEqual(self.window.color_scheme, colors)
        self.assertEqual((tab.source, tab.dirty, tab.editor.document().isUndoAvailable()), before)

    def test_save_default_confirm_cancel_apply_reset_and_restart(self):
        from copy import deepcopy
        from PySide6.QtWidgets import QMessageBox
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        original = deepcopy(self.window.color_scheme)
        self.store.save('Default', original)
        tab = self.window.current()
        tab.editor.insertPlainText('unsaved text')
        document = (tab.source, tab.dirty, tab.editor.document().isUndoAvailable())
        dialog = self.dialog()
        dialog.child_opacity.setValue((original['deepest_child_opacity'] + 13) % 101)
        changed = deepcopy(dialog.working)
        path = self.store.path('Default')
        before = path.read_bytes()
        with patch('AgStudio.gui.color_scheme_dialog.QInputDialog.getText', return_value=('Default', False)):
            dialog.save_scheme()
        self.assertEqual(path.read_bytes(), before)
        with patch('AgStudio.gui.color_scheme_dialog.QInputDialog.getText', return_value=('Default', True)), \
             patch('AgStudio.gui.color_scheme_dialog.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            dialog.save_scheme()
        self.assertEqual(path.read_bytes(), before)
        with patch('AgStudio.gui.color_scheme_dialog.QInputDialog.getText', return_value=('Default', True)), \
             patch('AgStudio.gui.color_scheme_dialog.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), \
             patch('AgStudio.gui.color_schemes.os.replace', side_effect=OSError('blocked')), \
             patch('AgStudio.gui.color_scheme_dialog.QMessageBox.warning') as warning:
            dialog.save_scheme()
            warning.assert_called_once()
        self.assertEqual(path.read_bytes(), before)
        with patch('AgStudio.gui.color_scheme_dialog.QInputDialog.getText', return_value=('Default', True)), \
             patch('AgStudio.gui.color_scheme_dialog.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            dialog.save_scheme()
        self.assertEqual(dialog.scheme_name, 'Default')
        self.assertEqual(self.store.load('Default'), changed)
        dialog.reject()
        self.assertEqual(self.window.color_scheme, original)
        # Explicit Save persists, while dialog Cancel only rolls back live preview.
        self.assertEqual(self.store.load('Default'), changed)
        dialog = self.dialog()
        dialog.reset_default()
        self.assertEqual(dialog.working, changed)
        self.assertTrue(dialog.apply_scheme())
        reopened = StudioWindow('current', user_state=UserState(), background=False, scheme_store=SchemeStore(self.temp.name))
        self.addCleanup(reopened.deleteLater)
        self.assertEqual(reopened.color_scheme, changed)
        self.assertEqual(self.store.selected(), ('Default', changed, None))
        self.assertEqual((tab.source, tab.dirty, tab.editor.document().isUndoAvailable()), document)

    def test_color_type_labels_are_grouped_sorted_and_preserve_keys(self):
        dialog = self.dialog()
        items = [(dialog.roles.itemText(i), dialog.roles.itemData(i)) for i in range(dialog.roles.count())]
        labels = [label for label, _ in items]
        self.assertEqual(labels, sorted(labels, key=str.casefold))
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(dict((role, label) for label, role in items), ROLE_LABELS)
        groups = {'map_viewport': 'Infer Map', 'correlation_pulse': 'Editor', 'spelling_underline': 'Editor', 'editor': 'Editor', 'selection': 'Editor', 'active_row': 'Editor', 'gutter': 'Editor',
                  'symbol': 'Symbolic Referencing', 'symbol_body': 'Symbolic Referencing',
                  'operation': 'Context Operation', 'binder': 'Explicit Block Binding',
                  'alias': 'Inline Aliasing', 'priority': 'Listing', 'sequence': 'Listing', 'bullet': 'Listing',
                  'section': 'Sectioning', 'colon': 'Sectioning', 'wildcard': 'Wildcarding',
                  'delimiter': 'Literal Quote Block', 'literal': 'Literal Quote Block',
                  'double_quote': 'Inline Representation', 'double_quote_content': 'Inline Representation',
                  'backtick': 'Inline Representation', 'backtick_content': 'Inline Representation'}
        for label, role in items:
            self.assertEqual(label.split(' — ')[0], groups[role])
            dialog.roles.setCurrentIndex(dialog.roles.findData(role))
            for kind in ('foreground', 'background'):
                self.assertEqual([control.value() for control in dialog.controls[kind]], dialog.working[role][kind])
        self.assertEqual(dialog.windowTitle(), 'Color Scheme')
        action = next(action for action in self.window.menuBar().actions()
                      if action.text() == 'Color Scheme')
        self.assertIsNone(action.menu())
        self.assertNotIn(action, self.window.view_menu.actions())
        self.assertTrue(dialog.apply_scheme())
        data = json.loads((Path(self.temp.name) / 'selected.json').read_text())
        self.assertEqual(data['colors'], dialog.working)
        self.assertEqual(set(data['colors']), set(ROLE_LABELS) | {'deepest_child_opacity', 'pulse_cycles_per_minute'})

    def test_live_all_tabs_new_tabs_and_cancel_preserve_source_and_undo(self):
        first = self.window.current()
        first.editor.setPlainText('=> Parse [Source]\nP0. Important')
        first.editor.insertPlainText('x')
        before = first.source
        dirty = first.dirty
        undo = first.editor.document().isUndoAvailable()
        second = self.window.new_document()
        dialog = self.dialog()
        dialog.roles.setCurrentIndex(dialog.roles.findData('symbol'))
        dialog.controls['foreground'][0].setValue(30)
        dialog.controls['foreground'][3].setValue(80)
        dialog.controls['background'][3].setValue(150)
        third = self.window.new_document()
        for tab in [first, second, third]:
            self.assertEqual(tab.highlighter._formats['symbol'].foreground().color().getRgb(), tuple([30, *default_scheme()['symbol']['foreground'][1:3], 80]))
            self.assertEqual(tab.highlighter._formats['symbol'].background().color().alpha(), 150)
        dialog.reject()
        for tab in [first, second, third]:
            self.assertEqual(tab.editor.color_scheme, default_scheme())
        self.assertEqual((first.source, first.dirty, first.editor.document().isUndoAvailable()), (before, dirty, undo))
        self.assertFalse((Path(self.temp.name) / 'selected.json').exists())

    def test_apply_then_cancel_restores_applied_and_reloads_next_launch(self):
        dialog = self.dialog()
        dialog.controls['foreground'][0].setValue(31)
        self.assertTrue(dialog.apply_scheme())
        applied = self.window.color_scheme
        dialog.controls['foreground'][0].setValue(65)
        dialog.reject()
        self.assertEqual(self.window.color_scheme, applied)
        self.assertEqual(self.store.selected()[1], applied)
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        reopened = StudioWindow('current', user_state=UserState(), background=False, scheme_store=self.store)
        self.addCleanup(reopened.deleteLater)
        self.assertEqual(reopened.current().editor.color_scheme, applied)

    def test_reset_load_and_all_roles(self):
        dialog = self.dialog()
        self.assertEqual(dialog.roles.count(), len(ROLE_LABELS))
        changed = default_scheme()
        changed['editor']['background'] = [30, 40, 50, 60]
        self.store.save('Night', changed)
        dialog.refresh_names()
        dialog.schemes.setCurrentText('Night')
        dialog.load_scheme()
        self.assertEqual(self.window.color_scheme, changed)
        dialog.reset_default()
        self.assertEqual(self.window.color_scheme, default_scheme())
        dialog.reject()

    def test_picker_live_signals_and_cancel_restore_before_picker(self):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog, QDialog
        dialog = self.dialog()
        before = self.window.color_scheme
        observed = []
        def fake_exec(picker):
            self.assertEqual(picker.currentColor().getRgb(), tuple(before['editor']['foreground']))
            picker.setCurrentColor(QColor(11, 22, 33, 44))
            observed.append(self.window.current().editor.color_scheme['editor']['foreground'])
            return QDialog.DialogCode.Rejected
        with patch.object(QColorDialog, 'exec', fake_exec):
            dialog.choose_color('foreground')
        self.assertEqual(observed, [[11, 22, 33, 44]])
        self.assertEqual(self.window.color_scheme, before)
        dialog.reject()

    def test_apply_io_error_keeps_rollback_available(self):
        dialog = self.dialog()
        dialog.controls['foreground'][0].setValue(25)
        with patch.object(self.store, 'select', side_effect=OSError('read only')), patch('AgStudio.gui.color_scheme_dialog.QMessageBox.warning'):
            self.assertFalse(dialog.apply_scheme())
        dialog.reject()
        self.assertEqual(self.window.color_scheme, default_scheme())

    def test_window_close_rolls_back_live_colors(self):
        dialog = self.dialog()
        dialog.show()
        dialog.controls['background'][0].setValue(87)
        dialog.close()
        self.assertEqual(self.window.color_scheme, default_scheme())

    def test_bad_selection_starts_with_default_and_warning(self):
        (Path(self.temp.name) / 'selected.json').write_text('{broken')
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        reopened = StudioWindow('current', user_state=UserState(), background=False, scheme_store=self.store)
        self.addCleanup(reopened.deleteLater)
        self.assertEqual(reopened.current().editor.color_scheme, default_scheme())
        self.assertIn('using Default', reopened.statusBar().currentMessage())

    def test_color_change_does_not_emit_source_edits(self):
        from PySide6.QtTest import QSignalSpy
        tab = self.window.current()
        tab.editor.setPlainText('=> Read [Source]')
        spy = QSignalSpy(tab.editor.textChanged)
        ranges = tab.highlighter.ranges
        colors = default_scheme()
        colors['symbol']['foreground'] = [1, 2, 3, 4]
        self.window.apply_color_scheme(colors)
        self.assertEqual(spy.count(), 0)
        self.assertEqual(tab.highlighter.ranges, ranges)
