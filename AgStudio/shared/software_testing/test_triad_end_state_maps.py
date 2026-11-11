"""Complete-document Semantic Triad maps and source-aligned ST2 presentation.

The map readout is fixed at N. Source coordinates still describe occurrence
geometry, while the separately supported causal kernels keep their old meaning.
"""
from contextlib import ExitStack
from dataclasses import asdict, replace
import importlib.util
import json
import math
import os
import pickle
import unittest
from unittest.mock import patch

from AgStudio.shared.analysis_snapshot import freeze_analysis
from AgStudio.shared.graph import (
    GraphResult, GraphSnapshot, HeatScore, PreparedSemantic, SemanticCoverage,
    SemanticFootprint, SemanticOptions, SemanticPosition,
    calculate_graph, semantic_state,
)
from AgStudio.shared.graph.adapter import build_graph_snapshot
from AgStudio.shared.graph.map_request import MapRequest, calculate_map_request
from AgStudio.shared.graph.semantic import calculate_inherited_details, calculate_semantic_details
from AgStudio.shared.lint import analyze

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

MODES = ('semantic_triad_1', 'semantic_triad_2')
SOURCE = ('[A]: short\n[B]: a much longer supported definition body\n'
          'Task:\n  before [A] then [B] and [A] after\n')


def graph(source=SOURCE, mode='semantic_triad_2', **options):
    analysis = analyze(source)
    return build_graph_snapshot(analysis.tree, analysis.semantics, mode=mode,
                                options=options)


def values(details):
    return {item.object: item.adjusted_linked for item in details}


class EndStateMapCalculationTests(unittest.TestCase):
    def test_each_mode_carries_one_complete_document_vector(self):
        for mode in MODES:
            for decay in (0, .7, 20):
                with self.subTest(mode=mode, decay=decay):
                    snapshot = graph(mode=mode, decay=decay)
                    expected = calculate_inherited_details(snapshot)
                    result = calculate_graph(snapshot)
                    self.assertEqual(result.final_details, expected)
                    self.assertEqual(tuple(item.object for item in result.final_details),
                                     tuple(item.object for item in snapshot.semantic_elements))
                    for _, details in result.view_details:
                        self.assertEqual(details, expected)
                    for _, samples in result.position_values:
                        for name, score in samples:
                            self.assertEqual(score, values(expected)[name])

    def test_repeated_occurrences_keep_coordinates_but_share_final_scores(self):
        source = '[A]: first\n[B]: second\nTask: [A] then [A] then [B] then [A]\n'
        for mode in MODES:
            with self.subTest(mode=mode):
                snapshot = graph(source, mode=mode, decay=0)
                result = calculate_graph(snapshot)
                final = values(result.final_details)
                self.assertEqual({name: final[name] for name in ('A', 'B')},
                                 dict(semantic_state(snapshot, len(source))))
                if mode == 'semantic_triad_2':
                    endpoints = [event.position for event in snapshot.semantic_positions
                                 if event.kind == 'reference_use' and event.objects == ('A',)]
                    self.assertEqual(len(set(endpoints)), 3)
                    samples = dict(result.position_values)
                    self.assertEqual([dict(samples[point])['A'] for point in endpoints],
                                     [final['A']] * 3)
                else:
                    self.assertGreater(len(result.view_details), 1)
                    self.assertTrue(all(values(details)['A'] == final['A']
                                        for _, details in result.view_details))

    def test_adding_a_later_reference_changes_earlier_map_readout(self):
        before = '[A]: seed\n[B]: a much longer body of ordinary words\nTask: [A]\n'
        after = before + 'Later: [A] [A] [A] [A]\n'
        for mode in MODES:
            with self.subTest(mode=mode):
                old = calculate_graph(graph(before, mode=mode, decay=0))
                new = calculate_graph(graph(after, mode=mode, decay=0))
                self.assertGreater(values(new.final_details)['A'], values(old.final_details)['A'])
                if mode == 'semantic_triad_2':
                    early = before.index('[A]', before.index('Task:')) + 3
                    self.assertEqual(dict(dict(new.position_values)[early])['A'],
                                     values(new.final_details)['A'])
                else:
                    early = next(view.node for view in new.semantic_views
                                 if view.kind == 'reference_use')
                    self.assertEqual(values(dict(new.view_details)[early])['A'],
                                     values(new.final_details)['A'])

    def test_st2_scale_is_final_vector_maximum_not_earlier_causal_peak(self):
        snapshot = GraphSnapshot(
            (0,), (), ((0, 0),), mode='semantic_triad_2',
            options=SemanticOptions(decay=10), points=((0, 100),), document_length=100,
            semantic_footprints=(SemanticFootprint('A', ((0, 10),)),
                                 SemanticFootprint('B', ((90, 91),))),
            semantic_positions=(SemanticPosition(10, ('A',), 'object_end', 0),
                                SemanticPosition(91, ('B',), 'object_end', 0)))
        result = calculate_graph(snapshot)
        self.assertEqual(result.position_maximum, max(values(result.final_details).values()))
        self.assertGreater(PreparedSemantic(snapshot).maximum(), result.position_maximum)

    def test_replacing_later_plain_text_with_reference_adds_exact_support_at_fixed_n(self):
        before = '[A]: seed\nTask: [A]\nLater: xyz\n'
        after = before.replace('xyz', '[A]')
        self.assertEqual(len(before), len(after))
        for mode in MODES:
            with self.subTest(mode=mode):
                old = calculate_graph(graph(before, mode=mode, decay=0))
                new = calculate_graph(graph(after, mode=mode, decay=0))
                self.assertAlmostEqual(values(new.final_details)['A'] - values(old.final_details)['A'],
                                       3 / len(before))

    def test_final_vector_is_automatic_despite_legacy_selection_options(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                snapshot = graph(mode=mode, decay=0)
                selected = replace(snapshot, options=replace(snapshot.options,
                                   selected_object='B', comparison_objects=('B',)))
                self.assertEqual(calculate_graph(snapshot).final_details,
                                 calculate_graph(selected).final_details)

    def test_map_request_and_numeric_transport_return_same_final_vector(self):
        analysis = analyze(SOURCE)
        for mode in MODES:
            with self.subTest(mode=mode):
                expected = calculate_graph(graph(mode=mode, decay=.7))
                actual = calculate_map_request(MapRequest(freeze_analysis(analysis), mode,
                                                         json.dumps({'decay': .7})))
                self.assertEqual(actual, expected)
                self.assertEqual(pickle.loads(pickle.dumps(actual)), actual)
                record = json.loads(json.dumps(asdict(actual), allow_nan=False))
                # HeatScore has an explicitly typed constructor contract; the
                # new coverage vector accepts detached JSON records directly.
                record['scores'] = [(block, HeatScore(**score)) for block, score in record['scores']]
                restored = GraphResult(**record)
                self.assertEqual(restored.final_details, actual.final_details)

    def test_final_details_detach_mutable_input_and_reject_duplicate_identities(self):
        source = [{'object': 'A', 'adjusted_linked': .25, 'relationships': ['Uses B']}]
        result = GraphResult((), (), (), final_details=source)
        source[0]['adjusted_linked'] = .9
        source[0]['relationships'].clear()
        self.assertEqual(result.final_details,
                         (SemanticCoverage('A', adjusted_linked=.25, relationships=('Uses B',)),))
        with self.assertRaises(ValueError):
            GraphResult((), (), (), final_details=(SemanticCoverage('A'), SemanticCoverage('A')))

    def test_empty_and_parser_disabled_maps_have_empty_final_vectors(self):
        for mode in MODES:
            for source, options in (('', {}), (SOURCE, {'parser_support': False})):
                with self.subTest(mode=mode, source=bool(source)):
                    result = calculate_graph(graph(source, mode=mode, **options))
                    self.assertEqual(result.final_details, ())

    def test_explicit_causal_apis_still_exclude_future_mentions(self):
        snapshot = GraphSnapshot(
            (0, 1), (), (), mode='semantic_triad_2', options=SemanticOptions(decay=0),
            points=((0, 40), (1, 100)), document_length=100,
            semantic_footprints=(SemanticFootprint('A', ((0, 10),), ((70, 80),)),
                                 SemanticFootprint('Later', ((60, 70),), available_from=60)))
        changed = replace(snapshot, semantic_footprints=(
            replace(snapshot.semantic_footprints[0], mentions=((70, 100),)),
            snapshot.semantic_footprints[1]))
        self.assertEqual(semantic_state(snapshot, 40), semantic_state(changed, 40))
        self.assertEqual(dict(semantic_state(snapshot, 40)), {'A': .1, 'Later': 0})
        first, second = PreparedSemantic(snapshot), PreparedSemantic(changed)
        self.assertEqual(first.details_at(40), second.details_at(40))
        self.assertNotEqual(first.details_at(100), second.details_at(100))
        _, _, details = calculate_semantic_details(snapshot)
        self.assertEqual(values(dict(details)[0]), {'A': .1, 'Later': 0})
        self.assertEqual(values(dict(details)[1]), {'A': .2, 'Later': .1})


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class EndStateMapPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_map(self, source=SOURCE, mode='semantic_triad_2', *, wrap=False,
                 width=420, height=320, decay=0):
        from PySide6.QtWidgets import QPlainTextEdit
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import DocumentMap
        from AgStudio.gui.inference_heat import compute_heat
        editor = SourceEditor()
        editor.resize(235 if wrap else 800, height)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if wrap else
                               QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setPlainText(source)
        editor.show()
        view = DocumentMap(editor, mode=mode)
        view.resize(width, height)
        view.show()
        self.app.processEvents()
        analysis = analyze(source)
        heat = compute_heat(analysis.tree, analysis.semantics, mode=mode,
                            options={'decay': decay})
        view.set_model(analysis.document, analysis.tree, heat=heat)
        view.rebuild()
        self.app.processEvents()
        self.addCleanup(editor.deleteLater)
        self.addCleanup(editor.close)
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        return editor, view

    def interval_at(self, view, position):
        candidates = [(row, interval) for row in view.rows
                      for interval in view._position_intervals(row)
                      if interval.start <= position < interval.end]
        self.assertEqual(len(candidates), 1, (position, candidates))
        return candidates[0]

    def source_point(self, view, position):
        from PySide6.QtCore import QPointF
        row, _ = self.interval_at(view, position)
        block, line = view._position_line(row)
        x = line.cursorToX(view._source_index.display(position) - block.position())[0]
        origin = view.map_origin()
        return QPointF(origin.x() + x * view.horizontal_scale,
                       origin.y() + (row.top + row.height / 2) * view.scale)

    def test_heat_facade_publishes_identical_final_values_in_all_modes(self):
        observed = []
        for mode in MODES:
            _, view = self.make_map(mode=mode)
            self.assertEqual(view.heat.final_values, values(view.heat.final_details))
            self.assertEqual(view._heat_range,
                             (0., max(view.heat.final_values.values(), default=0.)))
            observed.append(view.heat.final_details)
        self.assertEqual(observed, [observed[0]] * len(MODES))

    def test_st2_all_occurrences_have_same_identity_color(self):
        from AgStudio.gui.inference_heat import heat_rgb
        _, view = self.make_map()
        occurrences = [(item.object, item.color) for row in view.rows
                       for item in view.position_segments(row)]
        for name in ('A', 'B'):
            colors = [color for identity, color in occurrences if identity == name]
            self.assertGreater(len(colors), 1)
            self.assertEqual(set(colors), {heat_rgb(view.heat.final_values[name], *view._heat_range)})

    def test_st1_summaries_average_final_st2_components_not_occurrence_readouts(self):
        _, view = self.make_map(mode='semantic_triad_1')
        maximum = view._heat_range[1]
        components = {}
        for node in view._tree.nodes:
            item = view.heat.views.get(node.id)
            owner = view.heat.owners.get(node.id)
            if owner is None or item is None or not any(token.text.strip() for token in node.tokens):
                continue
            components.setdefault(owner, []).extend(view.heat.final_values[name] / maximum
                                                   for name in item.objects)
        for owner, samples in components.items():
            if samples:
                summary = view._block_summaries[owner]
                self.assertEqual(summary.component_count, len(samples))
                self.assertAlmostEqual(summary.mean_intensity, math.fsum(samples) / len(samples))

    def test_later_reference_updates_earlier_display_color(self):
        before = '[A]: seed\n[B]: a much longer body of ordinary words\nTask: [A]\n'
        after = before + 'Later: [A] [A] [A] [A]\n'
        _, old = self.make_map(before)
        _, new = self.make_map(after)
        first = next(item.color for row in old.rows for item in old.position_segments(row)
                     if item.object == 'A')
        second = next(item.color for row in new.rows for item in new.position_segments(row)
                      if item.object == 'A')
        self.assertNotEqual(first, second)

    def test_st2_plain_syntax_named_body_and_references_keep_source_ownership(self):
        source = ('Unowned preamble [Missing]\n[B]: beta\n[A]:\n  Named words\n'
                  '  Plain:\n    - ordinary [B] tail\nTask:\n  before [A] after [Missing]\n')
        _, view = self.make_map(source)
        checks = (('Unowned', ('@element:0',)), ('[Missing]', ('@element:0',)),
                  ('[B]:', ('B',)), ('[A]:', ('A',)), ('Named words', ('A',)),
                  ('Plain:', ('@element:4',)), ('- ordinary', ('@element:4',)),
                  ('[B] tail', ('B',)), ('tail', ('@element:4',)),
                  ('Task:', ('@element:6',)), ('before', ('@element:6',)),
                  ('[A] after', ('A',)), ('after', ('@element:6',)))
        for text, names in checks:
            with self.subTest(text=text):
                _, interval = self.interval_at(view, source.index(text))
                self.assertEqual(interval.objects, names)
        for row in view.rows:
            for interval in view._position_intervals(row):
                self.assertLessEqual(len(interval.objects), 1)
            for segment in view.position_segments(row):
                if segment.object is None:
                    self.assertEqual(segment.color, (128, 128, 128))

    def test_st2_owned_zero_support_stays_blue_while_task_has_its_own_support(self):
        from AgStudio.gui.document_map import UNOWNED_COLOR
        from AgStudio.gui.inference_heat import heat_rgb
        source = '[A]: seed\nTask:\n  plain words only\n'
        _, view = self.make_map(source, decay=1e308)
        self.assertEqual(view.heat.final_values['A'], 0)
        self.assertGreater(view.heat.final_values['@element:1'], 0)
        for row in view.rows:
            for segment in view.position_segments(row):
                self.assertIsNotNone(segment.object)
                self.assertEqual(segment.color,
                                 heat_rgb(view.heat.final_values[segment.object], *view._heat_range))
                if segment.object == 'A':
                    self.assertEqual(segment.color, (0, 0, 255))
        self.assertNotEqual(UNOWNED_COLOR, heat_rgb(0, *view._heat_range))

    def test_st2_segments_match_actual_source_span_geometry_without_compression(self):
        _, view = self.make_map()
        for row in view.rows:
            segments = view.position_segments(row)
            intervals = view._position_intervals(row)
            self.assertEqual(len(segments), len(intervals))
            for segment, interval in zip(segments, intervals):
                self.assertEqual(segment.position, interval.start)
                self.assertEqual(segment.object, interval.objects[0] if interval.objects else None)
                self.assertAlmostEqual(segment.rect.left(), interval.left)
                self.assertAlmostEqual(segment.rect.right(), interval.right)
                self.assertAlmostEqual(segment.rect.top(), row.top)
                self.assertAlmostEqual(segment.rect.height(), row.height)

    def test_st2_syntax_plain_prefix_and_reference_are_separate_actual_spans(self):
        source = '[Constraint]: bound\nTask:\n- Follow [Constraint] closely\n'
        _, view = self.make_map(source)
        marker = source.index('- Follow')
        token = source.index('[Constraint]', marker)
        _, syntax = self.interval_at(view, marker)
        _, plain = self.interval_at(view, marker + 2)
        _, reference = self.interval_at(view, token + 1)
        _, tail = self.interval_at(view, token + len('[Constraint]') + 1)
        self.assertEqual((syntax.start, syntax.end, syntax.objects), (marker, marker + 1, ('@element:1',)))
        self.assertEqual((plain.start, plain.end, plain.objects), (marker + 1, token, ('@element:1',)))
        self.assertEqual((reference.start, reference.end, reference.objects),
                         (token, token + len('[Constraint]'), ('Constraint',)))
        self.assertEqual(tail.objects, ('@element:1',))

    def test_st2_hover_changes_source_location_but_not_identity_score(self):
        _, view = self.make_map()
        first = SOURCE.index('[A]', SOURCE.index('Task:')) + 1
        last = SOURCE.rindex('[A]') + 1
        first_text = view.tooltip_at(self.source_point(view, first))
        last_text = view.tooltip_at(self.source_point(view, last))
        self.assertNotEqual(first_text, last_text)
        expected = f'A: baseline B {view.heat.final_values["A"]:.3g}'
        self.assertIn(expected, first_text)
        self.assertIn(expected, last_text)
        neutral = view.tooltip_at(self.source_point(view, SOURCE.index('before')))
        self.assertIn('Task: baseline B', neutral)

    def test_st2_wrapped_unicode_tabs_preserve_source_hit_and_final_colors(self):
        from AgStudio.gui.document_map import UNOWNED_COLOR
        from AgStudio.gui.inference_heat import heat_rgb
        source = ('\ufeff[B]: beta\r\n[A]: alpha\r\nTask:\r\n  😀\tordinary words '
                  '[A] then many more ordinary words e\u0301 [B] final words\r\n')
        _, view = self.make_map(source, wrap=True)
        line_start = source.index('  😀')
        rows = [row for row in view.rows if row.start >= view._source_index.display(line_start)]
        self.assertGreater(len(rows), 1)
        targets = (source.index('[A]', line_start), source.index('[B]', line_start),
                   source.index('ordinary', line_start), source.index('final'))
        for scale in (view.minimum_scale, 1.0):
            view.scale = scale
            for target in targets:
                point = self.source_point(view, target)
                self.assertEqual(view.source_position_at(point), target)
            for row in rows:
                for segment in view.position_segments(row):
                    self.assertEqual(segment.color,
                                     UNOWNED_COLOR if segment.object is None else
                                     heat_rgb(view.heat.final_values[segment.object],
                                              *view._heat_range))

    def test_hover_scroll_zoom_resize_and_rebuild_never_score_again(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        source = SOURCE + '  before [A] then [B] after\n' * 90
        for mode in MODES:
            with self.subTest(mode=mode):
                editor, view = self.make_map(source, mode=mode, height=120)
                final = view.heat.final_details
                with ExitStack() as stack:
                    guards = [stack.enter_context(patch.object(PreparedSemantic, method,
                              side_effect=AssertionError('GUI attempted semantic scoring')))
                              for method in ('__init__', 'details_at', 'values_at', 'maximum')]
                    guards.append(stack.enter_context(patch(
                        'AgStudio.shared.graph.semantic._readouts',
                        side_effect=AssertionError('GUI attempted causal scoring'))))
                    view.rebuild()
                    for row in view.rows[:5]:
                        view.row_segments(row)
                        view.tooltip_at(QPointF((row.left + row.right) / 2 * view.horizontal_scale,
                                                view.map_origin().y() + (row.top + row.height / 2) * view.scale))
                    editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum())
                    self.app.processEvents()
                    wheel = QWheelEvent(QPointF(20, 20), QPointF(20, 20), QPoint(), QPoint(0, 120),
                                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                        Qt.ScrollPhase.NoScrollPhase, False)
                    view.wheelEvent(wheel)
                    view.resize(210, 140)
                    view.grab()
                    self.app.processEvents()
                    for row in view.rows[-5:]:
                        view.row_segments(row)
                    for guard in guards:
                        guard.assert_not_called()
                self.assertEqual(view.heat.final_details, final)


if __name__ == '__main__':
    unittest.main()
