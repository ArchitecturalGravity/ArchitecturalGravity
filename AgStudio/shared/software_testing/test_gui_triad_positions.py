"""ST2 source-position paint, exact hover, bounded caches, and retained pixels."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class PositionalSemanticMapTests(unittest.TestCase):
    SOURCE = '[A]: first\n[B]: second\nTask:\n  [A] then [B] and [A]\n'

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_map(self, source=None, *, width=420, height=480, options=None):
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import DocumentMap
        from AgStudio.gui.inference_heat import compute_heat
        from AgStudio.shared.lint import analyze
        source = self.SOURCE if source is None else source
        editor = SourceEditor()
        editor.resize(650, height)
        editor.setPlainText(source)
        editor.show()
        view = DocumentMap(editor, mode='semantic_triad_2')
        view.resize(width, height)
        view.show()
        self.app.processEvents()
        analysis = analyze(source)
        heat = compute_heat(analysis.tree, analysis.semantics, mode='semantic_triad_2', options=options)
        view.set_model(analysis.document, analysis.tree, heat=heat)
        view.rebuild()
        self.addCleanup(editor.deleteLater)
        self.addCleanup(editor.close)
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        return editor, view

    def source_point(self, view, position, row=None):
        from PySide6.QtCore import QPointF
        q = view._source_index.display(position)
        row = row or next(row for row in view.rows if row.start <= q <= row.end)
        block, line = view._position_line(row)
        source_x = line.cursorToX(q - block.position())[0]
        return QPointF(view.map_origin().x() + source_x * view.horizontal_scale,
                       view.map_origin().y() + (row.top + row.height / 2) * view.scale)

    def test_each_same_row_reference_has_own_source_span_and_final_color(self):
        from AgStudio.gui.inference_heat import heat_rgb
        _, view = self.make_map()
        row = view.rows[-1]
        segments = view.position_segments(row)
        endpoints = [event for event in view.heat.position_snapshot.semantic_positions
                     if event.kind == 'reference_start']
        self.assertEqual(len(endpoints), 3)
        marks = []
        for endpoint in endpoints:
            matching = [item for item in segments
                        if item.position == endpoint.position and item.object in endpoint.objects]
            self.assertTrue(matching)
            for segment in matching:
                value = view.heat.final_values[segment.object]
                self.assertEqual(segment.color, heat_rgb(value, *view._heat_range))
            marks.append(matching[-1])
        self.assertEqual([item.object for item in marks], ['A', 'B', 'A'])
        self.assertLess(marks[0].rect.left(), marks[1].rect.left())
        self.assertLess(marks[1].rect.left(), marks[2].rect.left())
        self.assertEqual(marks[0].color, marks[2].color)

    def test_interior_uses_constant_final_support_without_evaluator_calls(self):
        from AgStudio.gui.inference_heat import heat_rgb
        _, view = self.make_map('[A]: ' + 'long ordinary definition body ' * 5 + '\n')
        evaluator = view.heat.position_evaluator
        self.assertEqual(evaluator.cached_positions, ())
        with patch.object(evaluator, 'values_at', side_effect=AssertionError('paint rescored')), \
                patch.object(evaluator, 'details_at', side_effect=AssertionError('hover rescored')):
            segments = view.position_segments(view.rows[0])
            self.assertEqual(len(segments), len(view._position_intervals(view.rows[0])))
            self.assertEqual(segments[0].position, 0)
            self.assertTrue(all(item.object == 'A' for item in segments))
            expected = heat_rgb(view.heat.final_values['A'], *view._heat_range)
            self.assertTrue(all(item.color == expected for item in segments))
            u = 24
            text = view.tooltip_at(self.source_point(view, u))
            self.assertIn(f'· source {u}', text)
        self.assertEqual(evaluator.cached_positions, ())

    def test_hover_is_exact_picked_identity_and_retains_tooltip_spacing(self):
        _, view = self.make_map()
        for u in (self.SOURCE.index('[A]', self.SOURCE.index('Task:')) + 1,
                  self.SOURCE.rindex('[A]') + 2):
            point = self.source_point(view, u)
            self.assertEqual(view.source_position_at(point), u)
            text = view.tooltip_at(point)
            self.assertTrue(text.startswith('Infer Map · Semantic Triad 2\n\n'))
            self.assertIn(f'· source {u}', text)
            _, name, _ = view._position_hit(point)
            self.assertIn(f'{name}: baseline B', text)
            self.assertEqual(len(text.splitlines()), 4)
            self.assertNotIn('inclusive', text)
            self.assertNotIn('Click', text)
            self.assertNotIn('Selected object', text)

    def test_hover_reports_only_the_hit_identity_at_the_exact_boundary(self):
        from PySide6.QtCore import QPointF
        _, view = self.make_map()
        u = self.SOURCE.rindex('[A]') + 2
        detail = next(item for item in view.heat.final_details
                      if item.object == 'A')
        location = view._document.position(u)
        with patch.object(view, '_position_hit', return_value=(u, 'A', None), create=True):
            text = view.tooltip_at(QPointF(12, 12))
        self.assertIn(f'Line {location.line}, column {location.column} · source {u}', text)
        self.assertIn(f'A: baseline B {detail.adjusted_linked:.3g}', text)
        self.assertNotIn('B:', text)
        self.assertEqual(len(text.splitlines()), 4)
        with patch.object(view, '_position_hit', return_value=None, create=True):
            self.assertEqual(view.tooltip_at(QPointF()), view.mode_help)

    def test_reference_context_overrides_the_plain_body_baseline_locally(self):
        source = '[A]: alpha\n[B]: beta\nTask:\n  before [A] between [B] after\n'
        _, view = self.make_map(source)
        task = next(item.object for item in view.heat.position_snapshot.semantic_elements
                    if item.label == 'Task:')
        self.assertEqual(view._objects_at_position(source.index('alpha'), event=False), ('A',))
        self.assertEqual(view._objects_at_position(source.index('beta'), event=False), ('B',))
        self.assertEqual(view._objects_at_position(source.index('before'), event=False), (task,))
        ref = source.index('[A]', source.index('Task:'))
        self.assertEqual(view._objects_at_position(ref + 1, event=False), ('A',))
        self.assertEqual(view._objects_at_position(source.index('between'), event=False), (task,))

    def test_plain_body_hover_uses_label_and_cached_element_baseline(self):
        source = '[A]: alpha\nTask:\n  Follow [A] and finish\n'
        _, view = self.make_map(source)
        task = next(item for item in view.heat.position_snapshot.semantic_elements
                    if item.label == 'Task:')
        self.assertIn(task.object, view.heat.final_values)
        self.assertNotIn(task.object, view.heat.position_evaluator.object_names)
        point = self.source_point(view, source.index('Follow') + 1)
        with patch.object(view.heat.position_evaluator, 'values_at',
                          side_effect=AssertionError('plain body paint rescored')), \
                patch.object(view.heat.position_evaluator, 'details_at',
                             side_effect=AssertionError('plain body hover rescored')):
            tooltip = view.tooltip_at(point)
            self.assertIn(f'Task: baseline B {view.heat.final_values[task.object]:.3g}', tooltip)
            self.assertIn(' · source ', tooltip)
            self.assertNotIn(task.object, tooltip)
            self.assertTrue(all(segment.object is not None
                                for row in view.rows for segment in view.position_segments(row)))

    def assert_source_ownership(self, view, expected):
        """Check source ownership and actual cached-raster pixels together."""
        from AgStudio.gui.inference_heat import heat_rgb
        view._paint_positional_frame()
        frame = view._position_frame
        dpr = view.devicePixelRatioF()
        for position, name in expected:
            with self.subTest(position=position, name=name):
                self.assertEqual(view._objects_at_position(position, event=False), (name,))
                left, right = (self.source_point(view, position),
                               self.source_point(view, position + 1))
                color = frame.pixelColor(int((left.x() + right.x()) / 2 * dpr),
                                         int(left.y() * dpr)).getRgb()[:3]
                self.assertEqual(color, heat_rgb(view.heat.final_values[name], *view._heat_range))

    def test_hello_world_alias_colors_only_its_name_while_task_words_stay_red(self):
        source = (Path(__file__).parents[2] / 'examples' / 'HelloWorld.arc').read_text()
        _, view = self.make_map(source, width=900, height=720)
        task = next(item.object for item in view.heat.position_snapshot.semantic_elements
                    if item.label == 'Task:')
        start = source.index('1. Select')
        expected = [(source.index(text, start), task)
                    for text in ('1.', 'Select', 'in name order', 'AS', '2.', '3.', 'Follow')]
        expected += [(source.index('[Blueprint]', start) + 1, 'Blueprint'),
                     (source.index('[Codes]', start) + 1, 'Codes')]
        self.assert_source_ownership(view, expected)
        from AgStudio.gui.inference_heat import heat_rgb
        self.assertEqual(heat_rgb(view.heat.final_values[task], *view._heat_range), (255, 0, 0))
        self.assertNotEqual(view.heat.final_values[task], view.heat.final_values['Codes'])
        # Presentation narrowing never changes the full AS support evidence.
        alias = next(item for item in view.heat.position_snapshot.semantic_elements
                     if item.object == 'Codes')
        self.assertTrue(any(left <= start < right for left, right in alias.definitions))

    def test_alias_expression_words_keep_plain_scalar_named_and_nested_contexts(self):
        cases = (
            ('[A]: seed\nBuild: Select [A] AS [Codes]\n', 'Build: Select [A] AS [Codes]'),
            ('[A]: seed\n[Work]: Select [A] AS [Codes]\n', 'Work'),
            ('[A]: seed\n[Work]:\n  Nested:\n    Select [A] AS [Codes]\n', 'Nested:'),
        )
        for source, label in cases:
            with self.subTest(label=label):
                _, view = self.make_map(source, width=750)
                context = next(item.object for item in view.heat.position_snapshot.semantic_elements
                               if item.label == label)
                start = source.index('Select')
                self.assert_source_ownership(view, [(start, context),
                    (source.index('AS', start), context),
                    (source.index('[A]', start) + 1, 'A'),
                    (source.index('[Codes]', start) + 1, 'Codes')])

    def test_duplicate_alias_and_body_fall_back_to_local_source_ownership(self):
        source = ('[A]: seed\nTask:\n  Select [A] AS [Codes]\n'
                  '[Codes]:\n  retained body words\n'
                  'Next:\n  Again [A] AS [Codes]\n')
        _, view = self.make_map(source, width=750)
        contexts = {item.label: item.object for item in view.heat.position_snapshot.semantic_elements}
        self.assert_source_ownership(view, [
            (source.index('Select'), contexts['Task:']),
            (source.index('retained'), '@element:3'),
            (source.index('Again'), contexts['Next:']),
            (source.rindex('AS'), contexts['Next:']),
            (source.rindex('[Codes]') + 1, '@element:5')])

    def test_alias_ownership_is_replaced_after_edit_and_rebuild(self):
        from AgStudio.gui.inference_heat import compute_heat
        from AgStudio.shared.lint import analyze
        original = '[A]: seed\nTask:\n  First [A] AS [Codes]\n  Second words\n'
        editor, view = self.make_map(original, width=750)
        for source in ('[A]: seed\nTask:\n  First [A]\n  Second words\n',
                       '[A]: seed\nTask:\n  First words\n  Second [A] AS [Codes]\n'):
            view.invalidate(9)
            editor.setPlainText(source)
            analysis = analyze(source)
            heat = compute_heat(analysis.tree, analysis.semantics, mode='semantic_triad_2')
            view.set_model(analysis.document, analysis.tree, heat=heat)
            view.rebuild()
            task = next(item.object for item in heat.position_snapshot.semantic_elements
                        if item.label == 'Task:')
            expected = [(source.index('First'), task), (source.index('Second'), task)]
            if 'AS' in source:
                expected.extend(((source.index('AS'), task),
                                 (source.index('[Codes]') + 1, 'Codes')))
            else:
                self.assertNotIn('Codes', heat.final_values)
            self.assert_source_ownership(view, expected)

    def test_resize_and_zoom_leave_sparse_evidence_unchanged_and_bound_cache(self):
        source = '[A]: words\n[B]: more\nTask:\n' + '  [A] ordinary words and [B]\n' * 160
        _, view = self.make_map(source)
        evidence = dict(view.heat.position_values)
        for width in (80, 130, 250):
            view.resize(width, 300)
            view.scale = 1
            for row in view.rows:
                view.position_segments(row)
            self.assertLessEqual(view._position_cache_cells, 16384)
            self.assertLessEqual(len(view._position_cache), 128)
        self.assertEqual(view.heat.position_values, evidence)
        self.assertEqual(view.heat.position_evaluator.cached_positions, ())

    def test_fitted_scroll_and_repaint_reuse_raster_beyond_row_cache_capacity(self):
        source = '[A]:\n' + '  ordinary body\n' * 240
        editor, view = self.make_map(source, width=100, height=320)
        evaluator = view.heat.position_evaluator
        # More than 128 sampled rows defeats the bounded row cache: repainting
        # every row again would evict the next one before it can be reused.
        with patch.object(view, 'position_segments', wraps=view.position_segments) as sample:
            before = view.grab().toImage()
        self.assertGreater(sample.call_count, 128)
        frame = view._position_frame.copy()
        frame_key = view._position_frame.cacheKey()
        viewport = view.mapped_viewport()
        origin = view.map_origin()
        rebuilds = view.rebuild_count
        self.assertGreater(editor.verticalScrollBar().maximum(), 0)
        with patch.object(evaluator, 'values_at', wraps=evaluator.values_at) as values, \
                patch.object(view, '_position_line', wraps=view._position_line) as line, \
                patch.object(view, '_geometry', wraps=view._geometry) as geometry, \
                patch.object(view, 'position_segments', wraps=view.position_segments) as sample:
            view.grab()
            view.grab()
            editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum() // 2)
            self.app.processEvents()
            after = view.grab().toImage()
            self.assertGreater(view.mapped_viewport().top(), viewport.top())
            self.assertEqual(view.map_origin(), origin)
            self.assertNotEqual(after, before, 'the viewport overlay must still move')
            editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum())
            self.app.processEvents()
            view.grab()
            values.assert_not_called()
            line.assert_not_called()
            geometry.assert_not_called()
            sample.assert_not_called()
        self.assertEqual(view.rebuild_count, rebuilds)
        self.assertFalse(view._timer.isActive())
        self.assertEqual(view._position_frame.cacheKey(), frame_key)
        self.assertEqual(view._position_frame, frame)
        self.assertLessEqual(len(view._position_cache), 128)
        self.assertLessEqual(view._position_cache_cells, 16384)
        self.assertEqual(evaluator.cached_positions, ())

    def test_raster_refreshes_for_width_height_zoom_and_device_pixel_ratio(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        _, view = self.make_map('[A]:\n' + '  ordinary body\n' * 80, width=100, height=200)
        view.grab()

        def zoom():
            event = QWheelEvent(QPointF(40, 80), QPointF(40, 80), QPoint(), QPoint(0, 120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            view.wheelEvent(event)

        changes = (('width', lambda: view.resize(130, view.height())),
                   ('height', lambda: view.resize(view.width(), 240)),
                   ('zoom', zoom))
        for name, change in changes:
            with self.subTest(change=name):
                previous = view._position_frame.cacheKey()
                with patch.object(view, 'position_segments', wraps=view.position_segments) as sample:
                    change()
                    view.grab()
                    self.assertGreater(sample.call_count, 0)
                    self.assertNotEqual(view._position_frame.cacheKey(), previous)
                    sample.reset_mock()
                    current = view._position_frame.cacheKey()
                    view.grab()
                    sample.assert_not_called()
                    self.assertEqual(view._position_frame.cacheKey(), current)

        previous = view._position_frame.cacheKey()
        dpr = view.devicePixelRatioF() * 2
        with patch.object(view, 'devicePixelRatioF', return_value=dpr), \
                patch.object(view, 'position_segments', wraps=view.position_segments) as sample:
            view.grab()
            self.assertGreater(sample.call_count, 0)
            self.assertNotEqual(view._position_frame.cacheKey(), previous)
            self.assertEqual(view._position_frame.devicePixelRatio(), dpr)
            self.assertEqual(view._position_frame.width(), round(view.width() * dpr))
            self.assertEqual(view._position_frame.height(), round(view.height() * dpr))
            sample.reset_mock()
            current = view._position_frame.cacheKey()
            view.grab()
            sample.assert_not_called()
            self.assertEqual(view._position_frame.cacheKey(), current)

    def test_zoomed_scroll_refreshes_raster_when_origin_changes(self):
        editor, view = self.make_map('[A]:\n' + '  ordinary body\n' * 80, width=100, height=200)
        view._fit = False
        view.scale = 1.0
        view.grab()
        previous = view._position_frame.cacheKey()
        origin = view.map_origin()
        with patch.object(view, 'position_segments', wraps=view.position_segments) as sample:
            editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum() // 2)
            view.grab()
            self.assertNotEqual(view.map_origin(), origin)
            self.assertGreater(sample.call_count, 0)
            self.assertNotEqual(view._position_frame.cacheKey(), previous)
            sample.reset_mock()
            current = view._position_frame.cacheKey()
            view.grab()
            sample.assert_not_called()
            self.assertEqual(view._position_frame.cacheKey(), current)

    def test_zoomed_scroll_samples_only_new_rows_beyond_segment_cache_capacity(self):
        from AgStudio.gui.document_map import POSITION_COMMAND_BYTE_LIMIT, POSITION_COMMAND_ROW_LIMIT
        editor, view = self.make_map('[A]:\n' + '  ordinary body\n' * 480,
                                     width=100, height=360)
        view._fit = False
        view.scale = view.minimum_scale * 2
        scrollbar = editor.verticalScrollBar()
        start = scrollbar.maximum() // 2
        scrollbar.setValue(start)
        evaluator = view.heat.position_evaluator
        with patch.object(view, 'position_segments', wraps=view.position_segments) as sample:
            view.grab()
            initial_rows = {call.args[0].start for call in sample.call_args_list}
        self.assertGreater(len(initial_rows), 128)
        commands_by_key = dict(view._position_commands)
        self.assertGreater(len(commands_by_key), len(view._position_cache))
        origin = view.map_origin()
        rebuilds = view.rebuild_count
        with patch.object(view, '_position_commands_for_row', wraps=view._position_commands_for_row) as commands, \
                patch.object(view, 'position_segments', wraps=view.position_segments) as sample, \
                patch.object(evaluator, 'values_at', wraps=evaluator.values_at) as values, \
                patch.object(view, '_geometry', wraps=view._geometry) as geometry:
            scrollbar.setValue(start + 10)
            view.grab()
            visible_rows = {call.args[0].start for call in commands.call_args_list}
            sampled_rows = {call.args[0].start for call in sample.call_args_list}
            self.assertNotEqual(view.map_origin(), origin)
            self.assertGreater(len(visible_rows & initial_rows), 128)
            self.assertTrue(sampled_rows)
            self.assertEqual(sampled_rows, visible_rows - initial_rows)
            self.assertEqual(sample.call_count, len(sampled_rows))
            values.assert_not_called()
            for key, retained in commands_by_key.items():
                self.assertIs(view._position_commands[key], retained)
            sample.reset_mock()
            values.reset_mock()
            commands.reset_mock()
            view.grab()
            commands.assert_not_called()
            sample.assert_not_called()
            values.assert_not_called()
            # Revisiting the earlier window must also work after its segment
            # entries were evicted: the compact drawing commands are enough.
            scrollbar.setValue(start)
            view.grab()
            self.assertGreater(commands.call_count, 128)
            sample.assert_not_called()
            values.assert_not_called()
            geometry.assert_not_called()
        self.assertEqual(view.rebuild_count, rebuilds)
        self.assertLessEqual(len(view._position_cache), 128)
        self.assertLessEqual(view._position_cache_cells, 16384)
        self.assertLessEqual(len(view._position_commands), POSITION_COMMAND_ROW_LIMIT)
        self.assertLessEqual(view._position_command_bytes, POSITION_COMMAND_BYTE_LIMIT)
        self.assertEqual(view._position_command_bytes,
                         sum(len(commands) for commands in view._position_commands.values()))
        self.assertEqual(evaluator.cached_positions, ())

    def test_row_command_cache_evicts_oldest_rows_and_accounts_for_bytes(self):
        from AgStudio.gui.document_map import POSITION_COMMAND_BYTE_LIMIT, POSITION_COMMAND_ROW_LIMIT
        source = '[A]:\n' + '  a\n' * (POSITION_COMMAND_ROW_LIMIT + 2)
        _, view = self.make_map(source, width=48, height=200)
        view._fit = False
        view.scale = 1.0
        dpr = view.devicePixelRatioF()
        first = view._position_commands_for_row(view.rows[0], dpr)
        for row in view.rows[1:]:
            view._position_commands_for_row(row, dpr)
        self.assertEqual(len(view._position_commands), POSITION_COMMAND_ROW_LIMIT)
        self.assertTrue(all(commands is not first for commands in view._position_commands.values()))
        self.assertLessEqual(view._position_command_bytes, POSITION_COMMAND_BYTE_LIMIT)
        self.assertEqual(view._position_command_bytes,
                         sum(len(commands) for commands in view._position_commands.values()))
        with patch.object(view, 'position_segments', wraps=view.position_segments) as sample:
            # This row's full cells are outside the 128-entry LRU, but its
            # commands remain within the independently bounded commands cache.
            view._position_commands_for_row(view.rows[-200], dpr)
            sample.assert_not_called()

    def test_row_command_cache_enforces_byte_budget_and_skips_oversized_rows(self):
        from AgStudio.gui import document_map
        _, view = self.make_map('[A]:\n' + '  ordinary body\n' * 20, width=100, height=200)
        view._fit = False
        view.scale = 1.0
        dpr = view.devicePixelRatioF()
        first = view._position_commands_for_row(view.rows[1], dpr)
        # A small budget exercises real packed-command eviction without
        # requiring a large allocation or depending on the number of samples in each row.
        limit = len(first) * 2
        with patch.object(document_map, 'POSITION_COMMAND_BYTE_LIMIT', limit):
            for row in view.rows[2:]:
                view._position_commands_for_row(row, dpr)
                self.assertLessEqual(view._position_command_bytes, limit)
                self.assertEqual(view._position_command_bytes,
                                 sum(len(commands) for commands in view._position_commands.values()))
        self.assertTrue(view._position_commands)
        self.assertLess(len(view._position_commands), len(view.rows) - 1)
        self.assertTrue(all(commands is not first for commands in view._position_commands.values()))
        view.rebuild()
        with patch.object(document_map, 'POSITION_COMMAND_BYTE_LIMIT', 1):
            uncached = view._position_commands_for_row(view.rows[1], dpr)
        self.assertGreater(len(uncached), 1)
        self.assertEqual(view._position_commands, {})
        self.assertEqual(view._position_command_bytes, 0)

    def test_matching_model_replaces_stale_raster_at_unchanged_geometry(self):
        from AgStudio.gui.inference_heat import compute_heat
        from AgStudio.shared.lint import analyze
        source = '[A]: alpha\n[B]: bravo\nTask:\n  [A] then [B]\n'
        editor, view = self.make_map(source)
        view.grab()
        frame = view._position_frame.copy()
        previous = view._position_frame.cacheKey()
        commands_by_key = dict(view._position_commands)
        self.assertTrue(commands_by_key)
        geometry = (view.size(), view.extent, view.scale, view.horizontal_scale)
        replacement = source.replace('[A] then [B]', '[B] then [A]')
        editor.setPlainText(replacement)
        view.invalidate(7)
        view.grab()
        self.assertTrue(view.stale)
        self.assertEqual(view._position_frame.cacheKey(), previous)
        self.assertEqual(view._position_frame, frame)
        self.assertEqual(view._position_commands, commands_by_key)
        result = analyze(replacement)
        heat = compute_heat(result.tree, result.semantics, mode='semantic_triad_2')
        view.set_model(result.document, result.tree, heat=heat, revision=6)
        self.assertIsNone(view.heat, 'an old result must not replace the retained frame')
        view.grab()
        self.assertEqual(view._position_frame.cacheKey(), previous)
        view.set_model(result.document, result.tree, heat=heat, revision=7)
        view.rebuild()
        self.assertEqual(view._position_commands, {})
        self.assertEqual(view._position_command_bytes, 0)
        with patch.object(heat.position_evaluator, 'values_at',
                          wraps=heat.position_evaluator.values_at) as values:
            view.grab()
            values.assert_not_called()
            self.assertNotEqual(view._position_frame.cacheKey(), previous)
            self.assertNotEqual(view._position_frame, frame)
            self.assertEqual((view.size(), view.extent, view.scale, view.horizontal_scale), geometry)
            self.assertFalse(view.stale)
            values.reset_mock()
            current = view._position_frame.cacheKey()
            view.grab()
            values.assert_not_called()
            self.assertEqual(view._position_frame.cacheKey(), current)

    def test_wrapping_geometry_rebuild_invalidates_raster_and_row_samples(self):
        from PySide6.QtWidgets import QPlainTextEdit
        editor, view = self.make_map('[A]: ' + 'ordinary body ' * 35 + '\n', width=120, height=240)
        view.grab()
        frame = view._position_frame.copy()
        previous = view._position_frame.cacheKey()
        self.assertTrue(view._position_commands)
        rows = len(view.rows)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        editor.resize(200, editor.height())
        self.app.processEvents()
        view.rebuild()
        self.assertGreater(len(view.rows), rows)
        self.assertEqual(view._position_commands, {})
        self.assertEqual(view._position_command_bytes, 0)
        with patch.object(view, '_position_line', wraps=view._position_line) as line:
            view.grab()
            self.assertGreater(line.call_count, 0)
            self.assertNotEqual(view._position_frame.cacheKey(), previous)
            self.assertNotEqual(view._position_frame, frame)
            line.reset_mock()
            current = view._position_frame.cacheKey()
            view.grab()
            line.assert_not_called()
            self.assertEqual(view._position_frame.cacheKey(), current)

    def test_stale_frame_never_queries_cleared_model_or_changed_text(self):
        from PySide6.QtCore import QRectF
        editor, view = self.make_map()
        with patch.object(view, 'mapped_viewport', return_value=QRectF()):
            view.grab()
        before = view._position_frame.copy()
        editor.insertPlainText('unrelated replacement\n')
        self.assertTrue(view.stale)
        self.assertIsNone(view.heat)
        with patch.object(view, '_position_line', side_effect=AssertionError('stale Qt geometry query')), \
                patch.object(view, '_paint_positional_frame', side_effect=AssertionError('stale sampling')):
            view.grab()
        self.assertEqual(view._position_frame, before)
        self.assertEqual(view.tooltip_at(view.rect().center()), view.mode_help)

    def test_compressed_rows_remain_a_visible_contiguous_silhouette(self):
        source = '[A]:\n' + '  repeated body\n' * 1000
        _, view = self.make_map(source, width=160, height=100)
        view._paint_positional_frame()
        frame = view._position_frame
        row = view.rows[-1]
        x = round((row.left + row.right) / 2 * view.horizontal_scale)
        # Every physical row inside the fitted contiguous body is represented.
        missing = [y for y in range(2, frame.height() - 2) if frame.pixelColor(x, y).alpha() == 0]
        self.assertEqual(missing, [])

    def test_fractional_source_spans_cover_rows_at_physical_pixel_boundaries(self):
        import math
        source = ''.join(f'[Object{i}]: value\n' for i in range(12))
        source += 'Task:\n' + '  ordinary words outside named source bodies\n' * 12
        _, view = self.make_map(source, width=175, height=498)
        evidence = dict(view.heat.position_values)
        for dpr in (1, 1.25, 1.5, 2):
            for scale in (1, .73, .31):
                with self.subTest(dpr=dpr, scale=scale), \
                        patch.object(view, 'devicePixelRatioF', return_value=dpr):
                    view.scale = scale
                    view._position_frame_key = None
                    view._paint_positional_frame()
                    frame = view._position_frame.copy()
                    origin = view.map_origin()
                    checked = 0
                    for row in view.rows:
                        top = math.floor((origin.y() + row.top * scale) * dpr + .5)
                        bottom = math.floor((origin.y() + (row.top + row.height) * scale) * dpr + .5)
                        left = math.ceil((origin.x() + row.left * view.horizontal_scale) * dpr) + 1
                        right = math.floor((origin.x() + row.right * view.horizontal_scale) * dpr) - 1
                        if top < 0 or bottom > frame.height():
                            continue
                        for y in range(top, bottom):
                            for x in range(left, right):
                                self.assertEqual(frame.pixelColor(x, y).alpha(), 255,
                                                 (dpr, scale, x, y))
                                checked += 1
                    self.assertGreater(checked, 0)
                    # Replaying retained commands and sampling from scratch
                    # produce precisely the same corrected physical pixels.
                    view._position_frame_key = None
                    with patch.object(view, 'position_segments', side_effect=AssertionError('cache miss')):
                        view._paint_positional_frame()
                    self.assertEqual(frame, view._position_frame)
                    view._position_commands.clear()
                    view._position_command_bytes = 0
                    view._position_cache.clear()
                    view._position_cache_cells = 0
                    view._position_frame_key = None
                    view._paint_positional_frame()
                    self.assertEqual(frame, view._position_frame)
        self.assertEqual(view.heat.position_values, evidence)

    def test_fractional_grid_has_no_cracks_and_preserves_silhouette_gaps(self):
        import math
        from PySide6.QtCore import QPointF, QRectF
        from AgStudio.gui.document_map import MapRow, PositionSegment
        _, view = self.make_map(width=80, height=70)
        # Independent fractional columns exercise the same horizontal failure;
        # a real blank row and indentation must remain transparent.
        for dpr in (1, 1.25, 1.5, 2):
            for scale in (1, .73, .31):
                for offset in (0, 1000000.0, 1000000000.0):
                    for phase in (0, .5, .125):
                        with self.subTest(dpr=dpr, scale=scale, offset=offset, phase=phase):
                            view.scale = scale
                            view.extent = QRectF(0, 0, view.width() / .83, 100)
                            rows = [MapRow(i, offset + i * 30, 19, 4.25, 74.75, None, i + 1)
                                    for i in range(2)]
                            view.rows = rows
                            view._row_tops = tuple(row.top for row in rows)
                            origin = QPointF(.375, 3 + phase / dpr - offset * scale)
                            def segments(row):
                                return tuple(PositionSegment(0, str(band),
                                             QRectF(row.left + col * (row.right-row.left) / 7,
                                                    row.top + band * row.height / 12,
                                                    (row.right-row.left) / 7, row.height / 12),
                                             (band * 20, col * 35, 120))
                                             for col in range(7) for band in range(12))
                            view._position_commands.clear()
                            view._position_command_bytes = 0
                            view._position_frame_key = None
                            with patch.object(view, 'devicePixelRatioF', return_value=dpr), \
                                    patch.object(view, 'map_origin', return_value=origin), \
                                    patch.object(view, 'position_segments', side_effect=segments):
                                view._paint_positional_frame()
                            frame = view._position_frame
                            for row in rows:
                                top = math.floor((row.top * scale + origin.y()) * dpr + .5 + 1e-5)
                                bottom = math.floor(((row.top + row.height) * scale + origin.y()) * dpr + .5 + 1e-5)
                                left = math.floor((row.left * view.horizontal_scale + origin.x()) * dpr + .5)
                                right = math.floor((row.right * view.horizontal_scale + origin.x()) * dpr + .5)
                                for y in range(top, bottom):
                                    for x in range(left, right):
                                        color = frame.pixelColor(x, y)
                                        self.assertEqual(color.alpha(), 255, (x, y))
                                        self.assertIn(color.red(), range(0, 240, 20))
                                        self.assertIn(color.green(), range(0, 245, 35))
                                        self.assertEqual(color.blue(), 120)
                                    self.assertEqual(frame.pixelColor(left - 1, y).alpha(), 0)
                                    self.assertEqual(frame.pixelColor(right, y).alpha(), 0)
                            gap = round(((rows[0].top + 24) * scale + origin.y()) * dpr)
                            self.assertEqual(frame.pixelColor(20, gap).alpha(), 0)

    def test_parser_support_disabled_stays_neutral_without_invented_support(self):
        _, view = self.make_map(options={'parser_support': False})
        self.assertEqual(view._heat_range, (0, 0))
        for row in view.rows:
            segments = view.position_segments(row)
            self.assertTrue(segments)
            self.assertTrue(all(item.object is None and item.color == (128, 128, 128)
                                for item in segments))


if __name__ == '__main__':
    unittest.main()
