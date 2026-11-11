"""Mode selection is global and persistent; source and lint remain untouched."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from AgStudio.gui.user_state import UserState

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class _Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass


class InferenceModeStateTests(unittest.TestCase):
    def test_mode_is_independent_versioned_preference_and_invalid_values_default(self):
        settings = _Settings()
        state = UserState(settings)
        self.assertEqual(state.inference_mode, 'heuristic')
        self.assertEqual(settings.values, {})
        for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic'):
            state.set_inference_mode(mode)
            self.assertEqual(UserState(settings).inference_mode, mode)
            self.assertEqual(settings.values,
                             {UserState.INFERENCE_MODE_KEY: json.dumps({'version': 1, 'mode': mode})})
        for saved in (None, '{', 'null', '[]', '{}', '{"version":true,"mode":"semantic_triad"}',
                      '{"version":2,"mode":"semantic_triad"}', '{"version":1,"mode":[]}',
                      '{"version":1,"mode":"unknown"}'):
            settings.values[UserState.INFERENCE_MODE_KEY] = saved
            self.assertEqual(UserState(settings).inference_mode, 'heuristic')
            self.assertEqual(settings.values[UserState.INFERENCE_MODE_KEY], saved)
        for invalid in ('semantic_basic', 'semantic_full', 'unknown', None, [], 1, True):
            with self.assertRaises(ValueError):
                state.set_inference_mode(invalid)

    def test_only_the_three_supported_modes_have_labels_and_help(self):
        from AgStudio.gui.inference_heat import MODE_HELP, MODE_LABELS
        from AgStudio.shared.graph import GRAPH_MODES
        self.assertEqual(GRAPH_MODES, ('heuristic', 'semantic_triad_1', 'semantic_triad_2'))
        self.assertEqual(MODE_LABELS, {'heuristic': 'Heuristic', 'semantic_triad_1': 'Semantic Triad 1',
                                       'semantic_triad_2': 'Semantic Triad 2'})
        self.assertEqual(tuple(MODE_HELP), GRAPH_MODES)
        self.assertEqual(MODE_HELP['heuristic'],
                         'Heuristic based LLM inference speculation:\n'
                         '- Direct and indirect local-reference reinforcement')
        self.assertIn('plain text\n\nWhole-block color:', MODE_HELP['semantic_triad_1'])
        self.assertIn('plain text\n\nSource-aligned color:', MODE_HELP['semantic_triad_2'])
        self.assertIn('exact source-position hover', MODE_HELP['semantic_triad_2'])

    def test_all_semantic_modes_keep_plain_labels_and_common_final_baselines(self):
        from AgStudio.gui.inference_heat import compute_heat
        from AgStudio.shared.lint import analyze
        analysis = analyze('[A]: alpha\nTask:\n  Follow [A]\n')
        states = []
        for mode in ('semantic_triad_1', 'semantic_triad_2'):
            with self.subTest(mode=mode):
                heat = compute_heat(analysis.tree, analysis.semantics, mode=mode)
                task = next(item for item in heat.position_snapshot.semantic_elements
                            if item.label == 'Task:')
                self.assertEqual(heat.final_labels[task.object], 'Task:')
                self.assertGreater(heat.final_values[task.object], heat.final_values['A'])
                states.append(heat.final_values)
        self.assertEqual(states, [states[0]] * 2)

    def test_all_version_one_legacy_preferences_migrate_to_st2_and_write_back(self):
        for legacy in ('semantic_triad', 'semantic_triad_3', 'semantic_basic', 'semantic_full'):
            with self.subTest(legacy=legacy):
                settings = _Settings()
                panels = json.dumps({'side_panel': False, 'error_list': True, 'document_map': False})
                settings.values = {UserState.INFERENCE_MODE_KEY: json.dumps({'version': 1, 'mode': legacy}),
                                   UserState.KEY: panels, 'unrelated': 'retained'}
                state = UserState(settings)
                self.assertEqual(state.inference_mode, 'semantic_triad_2')
                self.assertEqual(settings.values, {
                    UserState.INFERENCE_MODE_KEY: json.dumps({'version': 1, 'mode': 'semantic_triad_2'}),
                    UserState.KEY: panels, 'unrelated': 'retained'})
                self.assertEqual(UserState(settings).inference_mode, 'semantic_triad_2')
                if legacy in ('semantic_basic', 'semantic_full'):
                    with self.assertRaises(ValueError):
                        state.set_inference_mode(legacy)
                else:
                    state.set_inference_mode(legacy)
                self.assertEqual(state.inference_mode, 'semantic_triad_2')

    def test_migration_requires_an_exact_supported_version_and_legacy_id(self):
        records = [{'version': version, 'mode': legacy}
                   for version in (None, False, True, 0, 1.0, '1', 2)
                   for legacy in ('semantic_triad', 'semantic_triad_3', 'semantic_basic', 'semantic_full')]
        records += [{'mode': 'semantic_basic'}, {'version': 1, 'mode': 'Semantic Triad'},
                    {'version': 1, 'mode': 'semantic_full '}, {'version': 1, 'mode': {}}]
        for record in records:
            with self.subTest(record=record):
                settings = _Settings()
                saved = json.dumps(record)
                settings.values[UserState.INFERENCE_MODE_KEY] = saved
                self.assertEqual(UserState(settings).inference_mode, 'heuristic')
                self.assertEqual(settings.values[UserState.INFERENCE_MODE_KEY], saved)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class InferenceModeGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = _Settings()
        self.windows = []

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            for window in self.windows:
                window.close()
                window.deleteLater()
        self.app.processEvents()

    def window(self, *, background=False, visible_map=True):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        state = UserState(self.settings)
        state.panels['document_map'] = visible_map
        window = StudioWindow('current', background=background, user_state=state,
                              scheme_store=SchemeStore(Path(self.temp.name) / 'colors'))
        self.windows.append(window)
        window.resize(1100, 740)
        window.show()
        self.app.processEvents()
        return window

    def wait_for(self, predicate):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if predicate():
                return
            QTest.qWait(10)
        self.fail('Current graph state did not publish in time')

    def wait_heat(self, tab):
        self.wait_for(lambda: tab.document_map.heat is not None
                      and tab.document_map.heat.mode == tab.graph.mode
                      and tab.document_map._heat_ready)

    def test_exclusive_menu_preserves_all_tabs_and_new_opened_tabs_inherit_mode(self):
        from AgStudio.gui.app import DocumentTab
        from PySide6.QtGui import QTextCursor
        window = self.window(visible_map=False)
        self.assertEqual(tuple(window.inference_mode_actions), ('heuristic', 'semantic_triad_1', 'semantic_triad_2'))
        self.assertEqual([action.text() for action in window.inference_mode_actions.values()],
                         ['Heuristic', 'Semantic Triad 1', 'Semantic Triad 2'])
        tab = window.current()
        tab.editor.insertPlainText('[A]: 🌍\n[B]: [A]\n')
        cursor = tab.editor.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
        tab.editor.setTextCursor(cursor)
        before = (tab.source, tab.dirty, cursor.position(), cursor.anchor(),
                  tab.editor.document().availableUndoSteps(), tab.analysis, tab.diagnostics)
        for mode in ('semantic_triad_1', 'semantic_triad_2', 'heuristic', 'semantic_triad_1', 'semantic_triad_2'):
            with patch.object(tab, 'refresh_model', side_effect=AssertionError('mode must not rerun lint')):
                window.inference_mode_actions[mode].trigger()
            self.assertEqual([key for key, action in window.inference_mode_actions.items()
                              if action.isChecked()], [mode])
            self.assertEqual(tab.graph.mode, mode)
            self.assertEqual(tab.document_map.mode, mode)
            self.assertEqual((tab.source, tab.dirty, tab.editor.textCursor().position(),
                              tab.editor.textCursor().anchor(), tab.editor.document().availableUndoSteps(),
                              tab.analysis, tab.diagnostics), before)
        new = window.new_document()
        self.assertEqual(new.graph.mode, 'semantic_triad_2')
        path = Path(self.temp.name) / 'untouched.arc'
        original = b'[Source]: value\r\n'
        path.write_bytes(original)
        opened = window.open_file(path)
        self.assertEqual(opened.graph.mode, 'semantic_triad_2')
        self.assertIs(window.open_file(path), opened)
        self.assertEqual(path.read_bytes(), original)
        adopted = window._add_tab(DocumentTab('current', map_enabled=False))
        self.assertEqual(adopted.graph.mode, 'semantic_triad_2')
        self.assertEqual(window.tabs.count(), 4)
        restarted = self.window(visible_map=False)
        self.assertEqual(restarted.current().graph.mode, 'semantic_triad_2')
        self.assertTrue(restarted.inference_mode_actions['semantic_triad_2'].isChecked())
        window.inference_mode_actions['heuristic'].trigger()
        self.assertTrue(all(window.tabs.widget(i).graph.mode == 'heuristic'
                            for i in range(window.tabs.count())))

    def test_st2_selection_persists_and_new_tabs_inherit_without_source_changes(self):
        window = self.window(visible_map=False)
        tab = window.current()
        tab.editor.insertPlainText('[A]: value\nTask:\n- [A] [A]\n')
        before = (tab.source, tab.dirty, tab.editor.document().availableUndoSteps())
        window.inference_mode_actions['semantic_triad_2'].trigger()
        self.assertEqual(tab.inference_mode_button.text(), 'ST2')
        self.assertEqual((tab.source, tab.dirty, tab.editor.document().availableUndoSteps()), before)
        self.assertEqual(window.new_document().graph.mode, 'semantic_triad_2')
        restarted = self.window(visible_map=False)
        self.assertEqual(restarted.current().graph.mode, 'semantic_triad_2')
        self.assertTrue(restarted.inference_mode_actions['semantic_triad_2'].isChecked())

    def test_migrated_preferences_start_with_only_canonical_menu_and_button_state(self):
        for legacy in ('semantic_triad', 'semantic_triad_3', 'semantic_basic', 'semantic_full'):
            with self.subTest(legacy=legacy):
                self.settings.values[UserState.INFERENCE_MODE_KEY] = json.dumps({'version': 1, 'mode': legacy})
                window = self.window(visible_map=False)
                self.assertEqual(tuple(window.inference_mode_actions), ('heuristic', 'semantic_triad_1', 'semantic_triad_2'))
                self.assertTrue(window.inference_mode_actions['semantic_triad_2'].isChecked())
                self.assertEqual(window.current().graph.mode, 'semantic_triad_2')
                self.assertEqual(window.current().document_map.mode, 'semantic_triad_2')
                self.assertEqual(window.current().inference_mode_button.text(), 'ST2')
                self.assertEqual(window.new_document().graph.mode, 'semantic_triad_2')
                self.assertEqual(json.loads(self.settings.value(UserState.INFERENCE_MODE_KEY)),
                                 {'version': 1, 'mode': 'semantic_triad_2'})

    def test_runtime_gui_entry_points_reject_legacy_ids_without_changing_selection(self):
        from AgStudio.gui.document_map import DocumentMap
        window = self.window(visible_map=False)
        tab = window.current()
        for legacy in ('semantic_basic', 'semantic_full'):
            for setter in (tab.set_inference_mode, tab.document_map.set_mode, window._set_inference_mode):
                with self.subTest(legacy=legacy, setter=setter), self.assertRaises(ValueError):
                    setter(legacy)
                self.assertEqual(window.user_state.inference_mode, 'heuristic')
                self.assertEqual(tab.graph.mode, 'heuristic')
                self.assertEqual(tab.document_map.mode, 'heuristic')
                self.assertEqual(tab.inference_mode_button.text(), 'H')
                self.assertEqual([mode for mode, action in window.inference_mode_actions.items()
                                  if action.isChecked()], ['heuristic'])
            with self.subTest(legacy=legacy, constructor='DocumentMap'), self.assertRaises(ValueError):
                DocumentMap(tab.editor, enabled=False, mode=legacy)

    def test_submenu_mouse_activation_is_discoverable(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        window = self.window(visible_map=False)
        menu = window.view_menu
        menu.popup(window.mapToGlobal(QPoint(100, 100)))
        self.app.processEvents()
        action = window.inference_menu.menuAction()
        QTest.mouseMove(menu, menu.actionGeometry(action).center())
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center())
        self.wait_for(window.inference_menu.isVisible)
        target = window.inference_mode_actions['semantic_triad_2']
        QTest.mouseClick(window.inference_menu, Qt.MouseButton.LeftButton,
                         pos=window.inference_menu.actionGeometry(target).center())
        self.assertEqual(window.current().graph.mode, 'semantic_triad_2')
        self.assertTrue(target.isChecked())

    def test_mode_change_clears_old_heat_no_lint_and_hidden_mode_waits_for_show(self):
        from AgStudio.gui.document_map import PENDING_COLOR
        window = self.window(background=True)
        tab = window.current()
        tab.editor.insertPlainText('[A]: value\n[B]: [A]\n[C]: [A] [B]\n')
        self.wait_heat(tab)
        self.wait_for(lambda: tab.diagnostics is not None)
        before = (tab.controller.revision, tab.analysis, tab.diagnostics)
        with patch.object(tab.controller, 'request', side_effect=AssertionError('mode must not rerun lint')):
            window.inference_mode_actions['semantic_triad_2'].trigger()
            self.assertIsNone(tab.document_map.heat)
            self.assertEqual(tab.document_map.color_for_owner(0).getRgb()[:3], PENDING_COLOR)
            self.wait_heat(tab)
            window.panel_actions['document_map'].trigger()
            self.assertFalse(tab.graph.enabled)
            self.assertIsNone(tab.document_map.heat)
            with patch.object(tab.graph, '_schedule', side_effect=AssertionError('hidden graph must not start')):
                window.inference_mode_actions['heuristic'].trigger()
            self.assertIsNone(tab.graph.heat)
            self.assertIsNone(tab.graph.pending)
            window.panel_actions['document_map'].trigger()
            self.wait_heat(tab)
        self.assertEqual((tab.controller.revision, tab.analysis, tab.diagnostics), before)
        self.assertEqual(tab.document_map.heat.mode, 'heuristic')

    def test_semantic_hover_is_concise_and_keeps_detailed_mode_help(self):
        from PySide6.QtCore import QPointF
        window = self.window()
        tab = window.current()
        tab.editor.insertPlainText('[A]: value\n[B]: [A]\n[C]: [A] [B]\n')
        window.inference_mode_actions['semantic_triad_2'].trigger()
        self.wait_heat(tab)
        m = tab.document_map
        row = m.rows[-1]
        segment = next(item for item in m.position_segments(row) if item.object == 'C')
        point = QPointF(segment.rect.center().x() * m.horizontal_scale,
                        m.map_origin().y() + segment.rect.center().y() * m.scale)
        text = m.tooltip_at(point)
        self.assertIn('Semantic Triad', text)
        self.assertIn('C: baseline B', text)
        self.assertIn('share', text)
        self.assertIn('\n\n', text)
        self.assertLessEqual(len(text.splitlines()), 6)
        self.assertNotIn('A: baseline B', text)
        self.assertNotIn('B: baseline B', text)
        self.assertIn('Line 3, column', text)
        self.assertNotIn('Kernel:', text)
        self.assertNotIn('Click', text)
        self.assertNotIn('Selected object:', text)
        self.assertNotIn('Inheritances:', text)
        self.assertNotIn('Propagations:', text)
        self.assertIn('not a probability or measured model attention', ' '.join(m.toolTip().split()))
        self.assertLessEqual(max(map(len, m.toolTip().splitlines())), 80)
        self.assertIn('source-character', m.toolTip())
        self.assertNotIn('0.95', m.toolTip())
        self.assertNotIn('Total modeled effective support:', text)
        window.inference_mode_actions['heuristic'].trigger()
        self.wait_heat(tab)
        self.assertIn('Inheritances:', m.tooltip_at(point))
        self.assertIn('Propagations:', m.tooltip_at(point))

    def test_object_breakdown_has_context_only_and_bounded_literal_names(self):
        from types import SimpleNamespace
        from AgStudio.gui.inference_heat import HeatModel
        from AgStudio.shared.graph import SemanticCoverage, SemanticView
        window = self.window(visible_map=False)
        m = window.current().document_map
        name = '<literal>&\n' + 'longname' * 20
        details = (SemanticCoverage(object=name, inclusive_weight=.5, own_weight=.4,
                                    definition=.3, linked=.3, adjusted_definition=.2,
                                    adjusted_linked=.2, comparison=.6, adjusted_comparison=.4),
                   SemanticCoverage(object='Other object', linked=.4))
        m.heat = HeatModel({}, {}, (), 'semantic_triad_2',
                           {0: {name: .2, 'Other object': .4}}, details={0: details},
                           views={0: SemanticView(0, 70, (name,), 'named_block')},
                           view_details={0: details})
        m._document = SimpleNamespace(source='x' * 100)
        result = m._semantic_breakdown(0)
        object_line = next(line for line in result.splitlines() if ': baseline B' in line)
        self.assertTrue(object_line.startswith('<literal>& longname'))
        label = object_line.split(': baseline B')[0]
        self.assertTrue(label.endswith('…'))
        self.assertLessEqual(len(label), 101)
        self.assertNotIn('Other object:', result)
        self.assertIn('baseline B 0.2 · source 0.2 · share 50.0%', result)
        self.assertEqual(len(result.splitlines()), 1)
        self.assertIn('Current coverage details unavailable.', m._semantic_breakdown(1))
        m.heat = HeatModel({}, {}, (), 'semantic_triad_2',
                           views={0: SemanticView(0, 70, (), 'all_objects')}, view_details={0: ()})
        self.assertIn('No declared object support.', m._semantic_breakdown(0))

    def test_context_breakdown_bounds_large_object_lists(self):
        from AgStudio.gui.inference_heat import HeatModel
        from AgStudio.shared.graph import SemanticCoverage, SemanticView
        window = self.window(visible_map=False)
        m = window.current().document_map
        names = tuple(f'Object {i}' for i in range(50))
        details = tuple(SemanticCoverage(object=name, adjusted_linked=.2,
                                        adjusted_comparison=.4) for name in names)
        m.heat = HeatModel({}, {}, (), 'semantic_triad_2',
                           views={0: SemanticView(0, 70, names, 'all_objects')},
                           view_details={0: details})
        result = m._semantic_breakdown(0)
        self.assertEqual(len(result.splitlines()), 4)
        self.assertIn('Object 0: baseline B 0.2 · source 0 · share 50.0%', result)
        self.assertIn('+ 47 more elements', result)
        self.assertNotIn('Object 3:', result)

    def test_source_edit_discards_document_specific_options_and_keeps_mode(self):
        window = self.window(visible_map=False)
        tab = window.current()
        tab.editor.insertPlainText('[A]: value\n')
        window.inference_mode_actions['semantic_triad_2'].trigger()
        tab.set_semantic_options({'representations': [{'object': 'test', 'position': 0, 'weight': 2}]})
        self.assertTrue(tab.graph.options)
        tab.editor.insertPlainText('more')
        self.assertEqual(tab.graph.options, {})
        self.assertEqual(tab.graph.mode, 'semantic_triad_2')
        self.assertEqual(window.new_document().graph.options, {})
        saved = json.loads(self.settings.value(UserState.INFERENCE_MODE_KEY))
        self.assertEqual(saved, {'version': 1, 'mode': 'semantic_triad_2'})


if __name__ == '__main__':
    unittest.main()
