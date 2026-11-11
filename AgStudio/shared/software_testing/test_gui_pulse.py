"""Correlation pulses use exact semantic ranges and reversible scheme settings."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PulseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow, DocumentTab
        from AgStudio.gui.color_schemes import SchemeStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SchemeStore(self.temp.name)
        self.window = StudioWindow('current', user_state=UserState(), background=False, scheme_store=self.store)
        self.window.show()
        self.addCleanup(self.window.deleteLater)
        self.source = '[A]: value\r\n\r\nTask:\r\n- 🌍 [A] and [A]\r\n- "[A]" and `[A]`\r\n- [AB]\r\n"""\r\n[A]\r\n"""\r\n'
        self.tab = self.window._add_tab(DocumentTab('current', self.source))
        self.window._show_side_panel()
        self.app.processEvents()
        self.tab.outline.setCurrentItem(self.tab.outline.topLevelItem(0))
        self.tab._outline_clicked(self.tab.outline.topLevelItem(0))
        self.addCleanup(self.tab.dispose_analysis)

    def test_exact_ranges_layering_and_smooth_alpha_without_analysis(self):
        from PySide6.QtGui import QTextFormat
        from AgStudio.gui.app import _display_offset
        tab = self.tab
        self.assertTrue(tab.pulse_timer.isActive())
        offsets = [0, self.source.index('[A]', self.source.index('🌍')), self.source.index('[A]', self.source.index('and'))]
        self.assertEqual(tab._pulse_ranges, tuple((_display_offset(self.source, p), _display_offset(self.source, p + 3)) for p in offsets))
        selections = tab.editor._pulse_selections
        self.assertEqual([s.cursor.selectedText() for s in selections], ['[A]'] * 3)
        scheme = deepcopy(self.window.color_scheme)
        scheme['correlation_pulse']['background'] = [20, 70, 150, 120]
        scheme['pulse_cycles_per_minute'] = 15
        self.window.apply_color_scheme(scheme)
        cursor = tab.editor.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(5, cursor.MoveMode.KeepAnchor)
        # Set under sync guard to exercise a real selection without changing context.
        tab._syncing_context = True
        tab.editor.setTextCursor(cursor)
        tab._syncing_context = False
        before = (cursor.anchor(), cursor.position(), tab.source)
        with patch('AgStudio.gui.app.analyze', side_effect=AssertionError('analysis during animation')):
            tab._pulse_phase = 0
            tab._pulse_last = 100
            for clock, expected in [(100, 0), (101, 60), (102, 120), (103, 60), (104, 0)]:
                with patch('AgStudio.gui.app.time.monotonic', return_value=clock):
                    tab._pulse_tick()
                for selection in tab.editor._pulse_selections:
                    self.assertEqual(selection.format.background().color().getRgb(), (20, 70, 150, expected))
                    self.assertFalse(selection.format.hasProperty(QTextFormat.Property.ForegroundBrush))
                    self.assertFalse(selection.format.property(QTextFormat.Property.FullWidthSelection))
                self.assertEqual(len(tab.editor.extraSelections()), len(tab.editor._base_selections) + 3)
        self.assertEqual((tab.editor.textCursor().anchor(), tab.editor.textCursor().position(), tab.source), before)

    def test_maximum_speed_is_one_cycle_per_six_tenths_second(self):
        scheme = deepcopy(self.window.color_scheme)
        scheme['pulse_cycles_per_minute'] = 100
        self.window.apply_color_scheme(scheme)
        for elapsed, expected in ((0, 0), (0.15, 0.5), (0.3, 1), (0.45, 0.5), (0.6, 0)):
            self.tab._pulse_phase = 0
            self.tab._pulse_last = 100
            with patch('AgStudio.gui.app.time.monotonic', return_value=100 + elapsed), \
                    patch.object(self.tab.editor, 'paint_pulse') as paint:
                self.tab._pulse_tick()
            self.assertAlmostEqual(paint.call_args.args[0], expected)

    def test_lifecycle_hidden_inactive_stale_and_disposed(self):
        tab = self.tab
        tab.correlations.setCurrentItem(tab.correlations.topLevelItem(1))
        self.assertTrue(tab.pulse_timer.isActive())
        tab.side_panel.hide()
        self.assertFalse(tab.pulse_timer.isActive())
        self.assertFalse(tab.editor._pulse_selections)
        self.window._show_side_panel()
        self.assertTrue(tab.pulse_timer.isActive())
        other = self.window.new_document()
        self.assertFalse(tab.pulse_timer.isActive())
        self.assertFalse(other.pulse_timer.isActive())
        self.window.tabs.setCurrentWidget(tab)
        self.assertTrue(tab.pulse_timer.isActive())
        tab.editor.insertPlainText('edited ')
        self.assertFalse(tab.pulse_timer.isActive())
        self.assertFalse(tab.editor._pulse_selections)
        tab.outline.setCurrentItem(tab.outline.topLevelItem(0))
        tab._outline_clicked(tab.outline.topLevelItem(0))
        tab.dispose_analysis()
        self.assertFalse(tab.pulse_timer.isActive())
        self.assertFalse(tab.editor._pulse_selections)

    def test_rendered_pulse_composites_over_scope_below_real_selection(self):
        from PySide6.QtGui import QColor, QTextCursor
        tab = self.tab
        scheme = deepcopy(self.window.color_scheme)
        scheme['editor']['background'] = [0, 0, 0, 255]
        scheme['active_row']['background'] = [200, 0, 0, 255]
        scheme['correlation_pulse']['background'] = [0, 0, 200, 128]
        scheme['selection']['background'] = [0, 200, 0, 255]
        self.window.apply_color_scheme(scheme)
        tab.pulse_timer.stop()
        rect = tab.editor.cursorRect()
        for factor, color in ((0, QColor(200, 0, 0)), (1, QColor(100, 0, 100))):
            tab.editor.paint_pulse(factor)
            self.app.processEvents()
            image = tab.editor.viewport().grab().toImage()
            self.assertEqual(image.pixelColor(rect.left() + 2, rect.top() + 1), color)
            self.assertEqual(image.pixelColor(rect.left() + 100, rect.top() + 1), QColor(200, 0, 0))
        cursor = tab.editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
        tab._syncing_context = True
        tab.editor.setTextCursor(cursor)
        tab._syncing_context = False
        tab.editor.setFocus()
        self.app.processEvents()
        image = tab.editor.viewport().grab().toImage()
        self.assertEqual(image.pixelColor(rect.left() + 2, rect.top() + 1), QColor(0, 200, 0))

    def test_live_color_speed_cancel_apply_restart_and_off(self):
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        from AgStudio.gui.color_schemes import default_scheme
        original = deepcopy(self.window.color_scheme)
        dialog = ColorSchemeDialog(self.window)
        self.addCleanup(dialog.deleteLater)
        dialog.roles.setCurrentIndex(dialog.roles.findData('correlation_pulse'))
        self.assertFalse(dialog.controls['foreground'][0].isEnabled())
        dialog.controls['background'][0].setValue(213)
        dialog.pulse_speed.setValue(0)
        self.assertFalse(self.tab.pulse_timer.isActive())
        self.assertEqual(dialog.pulse_speed_value.text(), 'Off')
        dialog.pulse_speed.setValue(10)
        self.assertTrue(self.tab.pulse_timer.isActive())
        self.tab.editor.paint_pulse(1)
        self.assertEqual(self.tab.editor._pulse_selections[0].format.background().color().red(), 213)
        dialog.reject()
        self.assertEqual(self.window.color_scheme, original)
        dialog = ColorSchemeDialog(self.window)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.pulse_speed.maximum(), 100)
        dialog.pulse_speed.setValue(100)
        self.assertEqual(dialog.pulse_speed_value.text(), '100 cycles/min')
        self.assertTrue(dialog.apply_scheme())
        applied = deepcopy(dialog.working)
        self.store.save('Pulse', applied)
        self.assertEqual(self.store.load('Pulse'), applied)
        self.assertEqual(self.store.selected()[1], applied)
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        restarted = StudioWindow('current', user_state=UserState(), background=False, scheme_store=self.store)
        self.addCleanup(restarted.deleteLater)
        self.assertEqual(restarted.color_scheme, applied)
        dialog.pulse_speed.setValue(22)
        dialog.reject()
        self.assertEqual(self.window.color_scheme, applied)
        dialog = ColorSchemeDialog(self.window)
        self.addCleanup(dialog.deleteLater)
        dialog.reset_default()
        self.assertEqual(dialog.working, default_scheme())


class PulseMigrationTests(unittest.TestCase):
    def test_additive_legacy_migration_preserves_all_existing_values(self):
        from AgStudio.gui.color_schemes import default_scheme, validate_scheme, SchemeStore
        scheme = default_scheme()
        old = deepcopy(scheme)
        del old['correlation_pulse']
        del old['pulse_cycles_per_minute']
        old['symbol']['foreground'] = [9, 7, 5, 3]
        migrated = validate_scheme(old)
        for key, value in old.items():
            self.assertEqual(migrated[key], value)
        self.assertEqual(migrated['correlation_pulse'], scheme['correlation_pulse'])
        self.assertEqual(migrated['pulse_cycles_per_minute'], scheme['pulse_cycles_per_minute'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Default.json'
            path.write_text(json.dumps({'version': 1, 'name': 'Default', 'colors': old}))
            before = path.read_bytes()
            self.assertEqual(SchemeStore(directory).load('Default'), migrated)
            self.assertEqual(path.read_bytes(), before)
        for invalid in (-1, 101, True, 1.2, '12', None):
            with self.assertRaises(ValueError):
                validate_scheme({**scheme, 'pulse_cycles_per_minute': invalid})
