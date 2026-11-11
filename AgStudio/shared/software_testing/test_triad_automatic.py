"""Automatic final-document coverage, node views and source-aligned spans."""
import importlib.util
import os
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class AutomaticSemanticMapTests(unittest.TestCase):
    SOURCE = '[Zed]:\n  alpha\n[Able]:\n  beta [Zed]\nTask:\n  [Able] [Zed]\n  tail\n'

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import DocumentTab
        self.tab = DocumentTab('current', self.SOURCE, inference_mode='semantic_triad_2')
        self.tab.resize(980, 650)
        self.tab.show()
        self.wait_heat()
        self.view = self.tab.document_map

    def tearDown(self):
        self.tab.dispose_analysis()
        self.tab.close()
        self.tab.deleteLater()
        self.app.processEvents()

    def wait_heat(self):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            view = self.tab.document_map
            if view.heat is not None and view._heat_ready and not view._timer.isActive():
                return
            QTest.qWait(10)
        self.fail('Current map result did not arrive')

    def publish(self, heat, revision=None):
        self.view.set_model(self.tab.document, self.tab.analysis.tree,
                            heat=heat, revision=revision)
        self.view.rebuild()

    def displayed_segments(self):
        return tuple(self.view.position_segments(row) for row in self.view.rows)

    def assert_colors(self):
        from AgStudio.gui.document_map import UNOWNED_COLOR
        from AgStudio.gui.inference_heat import heat_rgb
        heat = self.view.heat
        values = {item.object: item.adjusted_linked for item in heat.final_details}
        maximum = max(values.values(), default=0)
        self.assertEqual(self.view._heat_range, (0, maximum))
        self.assertEqual(heat.view_details, {})
        self.assertEqual(self.view._display_segments, {})
        displayed = self.displayed_segments()
        self.assertTrue(any(displayed))
        for row, segments in zip(self.view.rows, displayed):
            intervals = self.view._position_intervals(row)
            self.assertEqual(len(segments), len(intervals))
            for segment, interval in zip(segments, intervals):
                name = interval.objects[0] if interval.objects else None
                self.assertEqual(segment.object, name)
                self.assertEqual(segment.position, interval.start)
                self.assertAlmostEqual(segment.rect.left(), interval.left)
                self.assertAlmostEqual(segment.rect.right(), interval.right)
                self.assertEqual(segment.color, heat_rgb(values[name], 0, maximum)
                                 if name is not None else UNOWNED_COLOR)

    def point(self, row):
        from PySide6.QtCore import QPoint
        view = self.view
        return QPoint(round((row.left + row.right) / 2 * view.horizontal_scale),
                      round(view.map_origin().y() + (row.top + row.height / 2) * view.scale))

    def test_worker_delivery_has_final_vector_without_selection_controls(self):
        from PySide6.QtWidgets import QComboBox
        self.assertIsNone(self.tab.findChild(QComboBox, 'semanticObjectSelector'))
        self.assertFalse(hasattr(self.tab, 'semantic_object_selector'))
        self.assertFalse(hasattr(self.view, 'selected_object'))
        self.assertFalse(hasattr(self.view, 'set_selected_object'))
        self.assertTrue(self.tab.map_title.isVisible())
        self.assertTrue(self.view.heat.views)
        self.assertIsNotNone(self.tab.graph.worker_pid)
        self.assertEqual(tuple(item.object for item in self.view.heat.final_details),
                         ('Zed', 'Able', '@element:4'))
        self.assertEqual(self.view.heat.view_details, {})
        self.assertIsNotNone(self.view.heat.position_snapshot)
        self.assertEqual(self.view.mapTo(self.tab, self.view.rect().topLeft()).y(),
                         self.tab.editor.mapTo(self.tab, self.tab.editor.rect().topLeft()).y())

    def test_named_contexts_and_reference_rows_automatically_paint_correct_identities(self):
        heat = self.view.heat
        self.assertEqual(heat.views[0].kind, 'named_block')
        self.assertEqual(heat.views[0].objects, ('Zed',))
        self.assertEqual(heat.views[1].objects, ('Zed',))
        self.assertEqual(heat.views[2].objects, ('Able',))
        self.assertEqual(heat.views[3].kind, 'reference_use')
        self.assertEqual(heat.views[3].objects, ('Zed', 'Able'))
        self.assertEqual(heat.views[5].objects, ('Zed', 'Able', '@element:4'))
        self.assertEqual(heat.views[5].position, self.SOURCE.index('[Zed]', self.SOURCE.index('Task:')) + 5)
        self.assertEqual([row.owner for row in self.view.rows], list(range(7)))
        task_start = self.SOURCE.index('Task:')
        checks = ((self.SOURCE.index('alpha'), 'Zed'),
                  (self.SOURCE.index('beta'), 'Able'),
                  (self.SOURCE.index('[Zed]', self.SOURCE.index('beta')) + 1, 'Zed'),
                  (self.SOURCE.index('[Able]', task_start) + 1, 'Able'),
                  (self.SOURCE.index('[Zed]', task_start) + 1, 'Zed'),
                  (self.SOURCE.index('tail'), '@element:4'))
        for position, expected in checks:
            with self.subTest(position=position):
                matches = [(row, interval) for row in self.view.rows
                           for interval in self.view._position_intervals(row)
                           if interval.start <= position < interval.end]
                self.assertEqual(len(matches), 1)
                row, interval = matches[0]
                self.assertEqual(interval.objects, (expected,))
                segment = next(segment for segment in self.view.position_segments(row)
                               if segment.position == interval.start)
                self.assertEqual(segment.object, expected)
        self.assert_colors()

    def test_plain_rows_show_their_structural_baseline_across_the_whole_width(self):
        for node in (4, 6):
            self.assertEqual(self.view.heat.views[node].kind, 'all_objects')
            self.assertEqual(self.view.heat.views[node].objects, ('@element:4',))
            row = next(row for row in self.view.rows if row.owner == node)
            segments = self.view.row_segments(row)
            self.assertEqual({name for name, _, _ in segments}, {'@element:4'})
            self.assertAlmostEqual(sum(rect.width() for _, rect, _ in segments), row.right - row.left)
            self.assertEqual(segments[0][1].left(), row.left)
            self.assertAlmostEqual(segments[-1][1].right(), row.right)

    def test_shared_color_scale_is_global_zero_to_maximum_not_per_identity(self):
        self.assert_colors()
        maximum = self.view._heat_range[1]
        seen_nonmaximum = False
        details = {item.object: item for item in self.view.heat.final_details}
        for segments in self.displayed_segments():
            for segment in segments:
                value = details[segment.object].adjusted_linked
                if 0 < value < maximum * .99:
                    seen_nonmaximum = True
                    self.assertNotEqual(segment.color, (255, 0, 0))
        self.assertTrue(seen_nonmaximum)

    def test_block_scores_cannot_replace_or_aggregate_source_span_colors(self):
        from AgStudio.shared.graph import HeatScore
        heat = self.view.heat
        before = self.displayed_segments()
        self.publish(replace(heat, scores={block: HeatScore(1000 - block) for block in heat.scores}))
        self.assertEqual(self.displayed_segments(), before)
        self.assert_colors()

    def test_every_hover_shows_only_concise_source_context_support(self):
        from PySide6.QtCore import QPointF
        for row in self.view.rows:
            for segment in self.view.position_segments(row):
                rect = segment.rect
                origin = self.view.map_origin()
                point = QPointF(origin.x() + rect.center().x() * self.view.horizontal_scale,
                                origin.y() + rect.center().y() * self.view.scale)
                text = self.view.tooltip_at(point)
                name = segment.object
                if name is not None:
                    label = self.view.heat.final_labels[name].rstrip(':')
                    self.assertIn(f'{label}: baseline B', text)
                    self.assertEqual(text.count('baseline B'), 1)
                else:
                    self.assertIn('No attributed semantic object.', text)
                self.assertTrue(text.startswith('Infer Map · Semantic Triad 2\n\n'))
                self.assertIn(f'source {self.view.source_position_at(point)}', text)
                self.assertLessEqual(len(text.splitlines()), 5)
                for phrase in ('inclusive', 'Kernel:', 'All objects,', 'Click', 'Selected object:'):
                    self.assertNotIn(phrase, text)
        details = {item.object: item for item in self.view.heat.final_details}
        self.assertGreater(details['Able'].inclusive_weight, 0)
        self.assertGreater(details['Able'].linked, 0)
        self.assertGreater(details['Able'].adjusted_linked, 0)

    def test_st1_hover_summarizes_whole_block_with_h_style_spacing(self):
        self.tab.set_inference_mode('semantic_triad_1')
        self.wait_heat()
        row = self.view.rows[1]
        owner = self.view.heat.owners[row.owner]
        summary = self.view._block_summaries[owner]
        text = self.view.tooltip_at(self.point(row))
        self.assertTrue(text.startswith('Infer Map · Semantic Triad 1\n\n'))
        self.assertIn('[Zed], line 1', text)
        self.assertIn(f'Mean intensity: {summary.mean_intensity:.1%}', text)
        self.assertIn(f'Components: {summary.component_count}', text)
        self.assertEqual(len(text.splitlines()), 5)
        self.assertNotIn('support', text)
        self.assertNotIn('Click', text)

    def test_legacy_selected_and_comparison_options_do_not_bias_automatic_views(self):
        before_views = dict(self.view.heat.views)
        before_details = self.view.heat.final_details
        before_colors = self.displayed_segments()
        self.tab.set_semantic_options({'selected_object': 'Able', 'comparison_objects': ['Able']})
        self.wait_heat()
        self.assertEqual(self.view.heat.views, before_views)
        self.assertEqual(self.view.heat.final_details, before_details)
        self.assertEqual(self.displayed_segments(), before_colors)

    def test_source_updates_recalculate_all_views_without_remembered_choice(self):
        self.tab.editor.setPlainText('[Fresh]:\n  new text\nTask:\n  [Fresh]\n')
        self.assertIsNone(self.view.heat)
        self.wait_heat()
        self.assertEqual(tuple(item.object for item in self.view.heat.final_details),
                         ('Fresh', '@element:2'))
        self.assertEqual({segment.object for segments in self.displayed_segments()
                          for segment in segments}, {'Fresh', '@element:2'})
        self.assert_colors()

    def test_pending_wrong_revision_and_failure_keep_frame_but_hide_evidence(self):
        from PySide6.QtCore import QPointF
        heat = self.view.heat
        self.view.grab()
        frame = self.view._position_frame.copy()
        self.assertFalse(frame.isNull())
        rows = self.displayed_segments()
        self.view.invalidate(91)
        self.assertTrue(self.view.stale)
        self.assertEqual(self.view._position_frame, frame)
        self.assertTrue(all(not segments for segments in self.displayed_segments()))
        self.assertNotIn('Zed: baseline B', self.view.tooltip_at(QPointF(1, 1)))
        self.publish(heat, revision=90)
        self.assertIsNone(self.view.heat)
        self.publish(heat, revision=91)
        self.assertFalse(self.view.stale)
        self.assertEqual(self.displayed_segments(), rows)
        self.view.grab()
        self.view.set_error('test replacement failure')
        self.assertIsNone(self.view.heat)
        self.assertTrue(self.view.stale)
        self.assertEqual(self.view._position_frame, frame)
        self.assertTrue(all(not segments for segments in self.displayed_segments()))
        text = self.view.tooltip_at(QPointF(1, 1))
        self.assertIn('test replacement failure', text)
        self.assertNotIn('Zed: baseline B', text)
        self.publish(heat, revision=91)
        self.assert_colors()

    def test_display_changes_do_not_rescore_or_change_source(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        tab, view = self.tab, self.view
        before = (tab.graph.epoch, tab.source, tab.dirty, tab.analysis, tab.diagnostics)
        heat = view.heat
        with patch.object(tab.graph, '_schedule', side_effect=AssertionError('display rescheduled scoring')):
            wheel = QWheelEvent(QPointF(40, 80), QPointF(40, 80), QPoint(), QPoint(0, 120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            view.wheelEvent(wheel)
            view.tooltip_at(self.point(view.rows[0]))
            view.position_segments(view.rows[0])
            tab.resize(800, 580)
            self.app.processEvents()
        self.assertIs(view.heat, heat)
        self.assertEqual(before, (tab.graph.epoch, tab.source, tab.dirty, tab.analysis, tab.diagnostics))

    def test_no_declared_support_has_no_fabricated_identity_or_score(self):
        from AgStudio.gui.document_map import UNOWNED_COLOR
        self.tab.set_semantic_options({'parser_support': False})
        self.wait_heat()
        self.assertEqual(self.view._heat_range, (0, 0))
        self.assertEqual(self.view.heat.final_details, ())
        self.assertEqual(self.view.heat.view_details, {})
        segments = tuple(segment for row in self.displayed_segments() for segment in row)
        self.assertTrue(segments)
        self.assertTrue(all(segment.object is None for segment in segments))
        self.assertTrue(all(segment.color == UNOWNED_COLOR for segment in segments))

    def test_hidden_map_discards_segments_and_reopens_current_evidence(self):
        self.tab.set_map_enabled(False)
        self.assertFalse(self.view.analysis_enabled)
        self.assertIsNone(self.view.heat)
        self.assertEqual(self.view._display_segments, {})
        self.assertIsNone(self.view._source_index)
        self.assertEqual(self.view._position_cache, {})
        self.assertTrue(self.view._position_frame.isNull())
        self.tab.set_map_enabled(True)
        self.wait_heat()
        self.assert_colors()

    def test_heuristic_keeps_original_score_palette_and_header(self):
        from AgStudio.gui.inference_heat import heat_rgb
        self.tab.set_inference_mode('heuristic')
        self.wait_heat()
        self.assertTrue(self.tab.map_title.isVisible())
        self.assertEqual(self.view._display_segments, {})
        scores = self.view.heat.scores
        values = [score.total for score in scores.values()]
        self.assertEqual(self.view._document_influence, sum(values))
        for owner, block in self.view.heat.owners.items():
            self.assertEqual(self.view.color_for_owner(owner).getRgb()[:3],
                             heat_rgb(scores[block].total, min(values), max(values)))
        text = self.view.tooltip_at(self.point(self.view.rows[-1]))
        self.assertIn('Inheritances:', text)
        self.assertIn('Propagations:', text)


if __name__ == '__main__':
    unittest.main()
