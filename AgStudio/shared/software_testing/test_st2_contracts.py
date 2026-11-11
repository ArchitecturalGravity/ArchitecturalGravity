"""Independent positional contracts, using character-set oracles only in tests."""
from dataclasses import asdict, replace
import importlib.util
import json
import math
import os
import pickle
import random
import unittest

from AgStudio.shared.graph import (
    GraphResult, GraphSnapshot, HeatCancelled, HeatScore, PreparedSemantic, SemanticFootprint,
    SemanticOptions, SemanticPosition, calculate_graph,
)
from AgStudio.shared.graph.adapter import build_graph_snapshot
from AgStudio.shared.lint import analyze

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def graph(footprints, *, length=80, decay=1.0, positions=()):
    return GraphSnapshot(
        (1,), (), ((1, 1),), mode='semantic_triad_2',
        options=SemanticOptions(decay=decay), points=((1, length),),
        document_length=length, semantic_footprints=tuple(footprints),
        semantic_positions=tuple(positions),
    )


def characters(spans, position):
    return {index for start, end in spans for index in range(start, min(position, end))}


def weighted(indices, position, length, decay):
    return math.fsum(math.exp(-decay * ((position - index - 1) / length)) / length
                     for index in indices) if length else 0.0


class PositionalEvaluatorContractTests(unittest.TestCase):
    def test_independent_randomized_character_oracle_at_every_boundary(self):
        rng = random.Random(18302)
        for decay in (0.0, 1e-14, .7, 8.0, 1e308):
            footprints = []
            for name in ('Zed', 'Able', 'Middle'):
                endpoints = [sorted(rng.sample(range(81), 2)) for _ in range(8)]
                footprints.append(SemanticFootprint(
                    name, tuple(map(tuple, endpoints[:4])), tuple(map(tuple, endpoints[4:])),
                    available_from=rng.randrange(81)))
            prepared = PreparedSemantic(graph(footprints, decay=decay), cache_size=3)
            for position in range(81):
                with self.subTest(decay=decay, position=position):
                    linked = {item.object: characters(item.definitions + item.mentions, position)
                              if position >= item.available_from else set()
                              for item in footprints}
                    combined = set().union(*linked.values())
                    values = dict(prepared.values_at(position))
                    details = prepared.details_at(position)
                    self.assertEqual(tuple(values), ('Zed', 'Able', 'Middle'))
                    self.assertEqual(tuple(item.object for item in details), tuple(values))
                    for item in details:
                        expected = weighted(linked[item.object], position, 80, decay)
                        self.assertTrue(math.isclose(values[item.object], expected,
                                                    rel_tol=2e-12, abs_tol=1e-15))
                        self.assertAlmostEqual(item.adjusted_linked, expected, places=13)
                        self.assertEqual(item.linked, len(linked[item.object]) / 80)
                        self.assertEqual(item.comparison, len(combined) / 80)
                        self.assertAlmostEqual(item.adjusted_comparison,
                                               weighted(combined, position, 80, decay), places=13)
                    self.assertLessEqual(len(prepared.cached_positions), 3)

    def test_new_future_support_cannot_change_earlier_object_values(self):
        early = SemanticFootprint('A', ((0, 10),), ((20, 25),), available_from=3)
        future = replace(early, definitions=early.definitions + ((60, 80),),
                         mentions=early.mentions + ((50, 54),))
        a, b = PreparedSemantic(graph((early,))), PreparedSemantic(graph((future,)))
        for position in range(50):
            self.assertEqual(a.values_at(position), b.values_at(position))

    def test_unavailable_identity_is_zero_until_exact_declaration_end(self):
        prepared = PreparedSemantic(graph((SemanticFootprint(
            'Alias', ((0, 40),), available_from=22),), decay=0))
        self.assertEqual(prepared.values_at(21), (('Alias', 0),))
        self.assertEqual(prepared.details_at(21)[0].comparison, 0)
        self.assertEqual(prepared.values_at(22), (('Alias', 22 / 80),))

    def test_individual_objects_are_never_replaced_by_maximum_or_mean(self):
        prepared = PreparedSemantic(graph((
            SemanticFootprint('Zed', ((0, 20),)),
            SemanticFootprint('Able', ((0, 40),)),
        ), decay=0))
        self.assertEqual(prepared.values_at(60), (('Zed', .25), ('Able', .5)))
        self.assertEqual(prepared.values_at(60, ('Able',)), (('Able', .5),))
        self.assertEqual(tuple(item.comparison for item in prepared.details_at(60)), (.5, .5))

    def test_scale_covers_exact_intermediate_maximum_and_availability_jumps(self):
        footprints = (SemanticFootprint('A', ((0, 20), (35, 40)), available_from=30),
                      SemanticFootprint('B', ((10, 45),), ((70, 74),), available_from=14))
        for decay in (0, .01, 1, 10, 1e308):
            prepared = PreparedSemantic(graph(footprints, decay=decay))
            exhaustive = max(value for p in range(81) for _, value in prepared.values_at(p))
            self.assertAlmostEqual(prepared.maximum(), exhaustive, places=14)

    def test_hover_cache_is_lru_bounded_and_paint_reads_do_not_populate_it(self):
        prepared = PreparedSemantic(graph((SemanticFootprint('A', ((0, 80),)),)), cache_size=2)
        for position in range(81):
            prepared.values_at(position)
        self.assertEqual(prepared.cached_positions, ())
        first = prepared.details_at(4)
        prepared.details_at(5)
        self.assertIs(prepared.details_at(4), first)
        prepared.details_at(6)
        self.assertEqual(prepared.cached_positions, (4, 6))

    def test_cancellation_of_cached_read_and_in_progress_vector_does_not_publish(self):
        prepared = PreparedSemantic(graph(tuple(
            SemanticFootprint(str(index), ((0, 80),)) for index in range(20))), cache_size=2)
        prepared.details_at(4)
        for read in (prepared.values_at, prepared.details_at):
            with self.assertRaises(HeatCancelled):
                read(4, cancelled=lambda: True)
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls == 10
        with self.assertRaises(HeatCancelled):
            prepared.details_at(40, cancelled=cancelled)
        self.assertEqual(prepared.cached_positions, (4,))

    def test_automatic_evaluator_ignores_internal_object_selection(self):
        source = graph((SemanticFootprint('Zed', ((0, 20),)),
                        SemanticFootprint('Able', ((10, 40),))))
        biased = replace(source, options=SemanticOptions(selected_object='Able',
                                                         comparison_objects=('Able',)))
        self.assertEqual(PreparedSemantic(source).details_at(50),
                         PreparedSemantic(biased).details_at(50))

    def test_storage_does_not_expand_to_source_character_count(self):
        footprints = (SemanticFootprint('A', ((0, 80),)),)
        short = calculate_graph(graph(footprints, length=80))
        large = calculate_graph(graph(footprints, length=10**12))
        self.assertEqual(short.states, ())
        self.assertEqual(short.details, ())
        self.assertEqual(short.view_details, ())
        self.assertLess(len(pickle.dumps(large)) - len(pickle.dumps(short)), 100)
        prepared = PreparedSemantic(large.position_snapshot)
        self.assertTrue(math.isfinite(prepared.values_at(10**12)[0][1]))


class PositionalTransportContractTests(unittest.TestCase):
    SOURCE = '[Zed]: value\r\n[Able]: x\r\nTask:\r\n- 🌍\t[Zed] then [Able] and [Zed]\r\n'

    def snapshot(self):
        analysis = analyze(self.SOURCE)
        return build_graph_snapshot(analysis.tree, analysis.semantics, mode='semantic_triad_2',
                                    options={'decay': 0})

    def test_same_physical_row_keeps_each_reference_end_in_python_offsets(self):
        source = self.SOURCE
        snapshot = self.snapshot()
        events = [event for event in snapshot.semantic_positions if event.kind == 'reference_use']
        expected = [(source.index('[Zed]', source.index('Task:')) + 5, ('Zed',)),
                    (source.rindex('[Able]') + 6, ('Able',)),
                    (source.rindex('[Zed]') + 5, ('Zed',))]
        self.assertEqual([(event.position, event.objects) for event in events], expected)
        self.assertEqual(len({event.node for event in events}), 1)
        values = dict(calculate_graph(snapshot).position_values)
        self.assertEqual(dict(values[expected[0][0]])['Zed'], dict(values[expected[2][0]])['Zed'])
        self.assertEqual(dict(values[expected[0][0]])['Zed'],
                         dict(PreparedSemantic(snapshot).values_at(len(source)))['Zed'])
        prepared = PreparedSemantic(snapshot)
        first = {item.object: item for item in prepared.details_at(expected[0][0])}
        self.assertEqual(first['Zed'].mention, 5 / len(source))
        self.assertEqual(first['Able'].mention, 0)

    def test_sparse_result_is_detached_and_roundtrips_through_json_and_pickle(self):
        snapshot = self.snapshot()
        result = calculate_graph(snapshot)
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)
        raw = json.loads(json.dumps(asdict(result), allow_nan=False))
        # Existing GraphResult scores require HeatScore instances; new position
        # snapshot and records accept ordinary dataclass/JSON mappings.
        raw['scores'] = [(node, HeatScore(**score)) for node, score in raw['scores']]
        self.assertEqual(GraphResult(**raw), result)
        self.assertIsInstance(hash(result), int)
        self.assertEqual(result.position_snapshot, snapshot)
        self.assertTrue(all(len(values) <= 2 for _, values in result.position_values))
        raw['position_values'][0][1].clear()
        self.assertTrue(result.position_values[0][1])

    def test_disabling_parser_support_on_detached_snapshot_clears_positional_values(self):
        source = replace(self.snapshot(), options=SemanticOptions(parser_support=False))
        result = calculate_graph(source)
        self.assertFalse(any(values for _, values in result.position_values))
        self.assertEqual(result.position_maximum, 0)
        self.assertEqual(PreparedSemantic(result.position_snapshot).details_at(20), ())

    def test_same_boundary_multiple_objects_keeps_individual_source_order_values(self):
        source = graph((SemanticFootprint('Zed', ((0, 20),)),
                        SemanticFootprint('Able', ((0, 40),))), decay=0,
                       positions=(SemanticPosition(50, ('Able',)),
                                  SemanticPosition(50, ('Zed',))))
        self.assertEqual(calculate_graph(source).position_values,
                         ((50, (('Zed', .25), ('Able', .5))),))


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class PositionalCoordinateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_sparse_transform_matches_prefix_normalization_at_every_source_boundary(self):
        from AgStudio.gui.document_map import SourcePositionIndex
        sources = ('', '\r\n', '\r\n\r\r\n\n', '🌍🌎a😀', '\ufeff\ufeffx',
                   '\ufeff[A]: e\u0301\r\n\t🌍\r\nTask: [A]\u2028x\u2029z\r',
                   'a\v\f\x1c\x1d\x1e\x85\u2028\u2029🌍\r\nb')
        for source in sources:
            index = SourcePositionIndex(source)
            expected = [len(source[:position].removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
                            .encode('utf-16-le')) // 2 for position in range(len(source) + 1)]
            for position, display in enumerate(expected):
                with self.subTest(source=source, position=position):
                    self.assertEqual(index.display(position), display)
            for display in range(expected[-1] + 1):
                # A surrogate interior maps before its character. A collapsed
                # CRLF maps after LF; invisible boundaries share one pixel.
                self.assertEqual(index.source(display), max(
                    position for position, qt in enumerate(expected) if qt <= display))

    def test_actual_qt_document_find_matches_codepoint_transform_after_line_endings(self):
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import SourcePositionIndex
        editor = SourceEditor()
        self.addCleanup(editor.deleteLater)
        self.addCleanup(editor.close)
        for separator in ('\n', '\r', '\r\n', '\u2028', '\u2029'):
            source = f'\ufeffHeader:{separator}🌍\te\u0301 {separator}Task: [Unique]\t🌎 tail'
            editor.setPlainText(source)
            self.app.processEvents()
            found = editor.document().find('[Unique]')
            source = source.replace("\t", "  ")
            index = SourcePositionIndex(source)
            self.assertFalse(found.isNull())
            start = source.index('[Unique]')
            self.assertEqual(found.selectionStart(), index.display(start))
            self.assertEqual(found.selectionEnd(), index.display(start + len('[Unique]')))
            self.assertEqual(index.source(found.selectionEnd()), start + len('[Unique]'))

    def make_map(self, source, *, wrapped=False):
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import DocumentMap
        from AgStudio.gui.inference_heat import compute_heat
        from PySide6.QtWidgets import QPlainTextEdit
        editor = SourceEditor()
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if wrapped
                               else QPlainTextEdit.LineWrapMode.NoWrap)
        editor.resize(245 if wrapped else 800, 500)
        editor.setPlainText(source)
        editor.show()
        view = DocumentMap(editor, mode='semantic_triad_2')
        view.resize(180, 180)
        view.show()
        self.app.processEvents()
        analysis = analyze(source)
        view.set_model(analysis.document, analysis.tree,
                       heat=compute_heat(analysis.tree, analysis.semantics,
                                         mode='semantic_triad_2', options={'decay': 0}))
        view.rebuild()
        self.app.processEvents()
        self.addCleanup(editor.deleteLater)
        self.addCleanup(editor.close)
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        return editor, view

    def point_for_source(self, view, source, position, name=None):
        """Forward oracle using the actual, uncompressed Qt source cursor."""
        from PySide6.QtCore import QPointF
        prefix = source[:position].removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
        q = len(prefix.encode('utf-16-le')) // 2
        candidates = [(row, interval) for row in view.rows
                      for interval in view._position_intervals(row)
                      if interval.start <= position <= interval.end
                      and (name is None or name in interval.objects)]
        # At coincident endpoints select the following source interval,
        # including wrapped rows, without repeating it for every identity.
        row, interval = next(((row, item) for row, item in candidates if item.start == position),
                             candidates[-1])
        block, line = view._position_line(row)
        x = line.cursorToX(q - block.position())[0]
        return QPointF(view.map_origin().x() + x * view.horizontal_scale,
                       view.map_origin().y() + (row.top + row.height / 2) * view.scale)

    def test_exact_reference_hover_retains_each_same_row_endpoint_across_zoom_and_width(self):
        source = ('\ufeff\r\n[Zed]: first\r\n[Able]: second\r\nTask:\r\n'
                  '- 🌍\t[Zed] then [Able] and [Zed] done\r\n' + 'filler\r\n' * 35)
        _, view = self.make_map(source)
        endpoints = [event.position for event in view.heat.position_snapshot.semantic_positions
                     if event.kind == 'reference_use']
        self.assertEqual(len(endpoints), 3)
        for width in (80, 260):
            view.resize(width, 180)
            for scale in (view.minimum_scale, .65, 1.0):
                view.scale = scale
                for position in endpoints:
                    point = self.point_for_source(view, source, position)
                    self.assertEqual(view.source_position_at(point), position)
                    tooltip = view.tooltip_at(point)
                    self.assertIn(f'· source {position}', tooltip)
                    _, name, _ = view._position_hit(point)
                    if name is None:
                        self.assertIn('No attributed semantic object.', tooltip)
                    else:
                        label = view.heat.final_labels.get(name, name).rstrip(':')
                        self.assertIn(f'{label}: baseline B', tooltip)
                    self.assertEqual(len(tooltip.splitlines()), 4)

    def test_wrapped_reference_hover_maps_to_source_and_keeps_final_identity_colors(self):
        source = ('[Zed]: first\r\n[Able]: second\r\nTask:\r\n'
                  '- 🌍\t[Zed] then more words and [Able] with further words and [Zed] done\r\n')
        _, view = self.make_map(source, wrapped=True)
        events = [event for event in view.heat.position_snapshot.semantic_positions
                  if event.kind == 'reference_start']
        rows = [row for row in view.rows if row.owner == events[0].node]
        self.assertGreater(len(rows), 1)
        for event in events:
            point = self.point_for_source(view, source, event.position)
            self.assertEqual(view.source_position_at(point), event.position)
        cells = [cell for row in rows for cell in view.position_segments(row)]
        for event in events:
            self.assertTrue(any(cell.position == event.position and cell.object == event.objects[0]
                                for cell in cells), event)
        early = next(cell for cell in cells if cell.position == events[0].position and cell.object == 'Zed')
        late = next(cell for cell in cells if cell.position == events[-1].position and cell.object == 'Zed')
        self.assertEqual(early.color, late.color)

    def test_each_owned_or_neutral_span_maps_actual_source_with_unicode(self):
        source = ('\ufeff\r\n[Zed]: first\r\n[Able]: second\r\nTask:\r\n'
                  '  🌍\talpha e\u0301 beta words [Zed] then [Able] tail\r\n')
        for wrapped in (False, True):
            _, view = self.make_map(source, wrapped=wrapped)
            row_start = source.index('  🌍')
            for scale in (.35, 1.0, 1.7):
                view.scale = scale
                for row in view.rows:
                    for interval in view._position_intervals(row):
                        if interval.start < row_start or interval.end <= interval.start:
                            continue
                        self.assertLessEqual(len(interval.objects), 1)
                        block, line = view._position_line(row)
                        for position in range(interval.start, interval.end):
                            # Combining interiors share cursor pixels. Only
                            # assert exact inverses at Qt's legal cursor stops.
                            display = view._source_index.display(position)
                            local = display - block.position()
                            if not block.layout().isValidCursorPosition(local):
                                continue
                            if view._source_index.source(display) != position:
                                continue
                            for name in interval.objects or (None,):
                                point = self.point_for_source(view, source, position, name)
                                hit = view._position_hit(point)
                                self.assertIsNotNone(hit, (wrapped, scale, position, name))
                                self.assertEqual(hit[:2], (position, name),
                                                 (wrapped, scale, position, name))

    def test_source_edit_retains_frame_but_invalidates_position_evidence(self):
        source = '[A]: text\nTask: 🌍 [A] then [A]\n'
        editor, view = self.make_map(source)
        endpoint = source.rindex('[A]') + 3
        point = self.point_for_source(view, source, endpoint)
        self.assertEqual(view.source_position_at(point), endpoint)
        view._paint_positional_frame()
        self.assertFalse(view._position_frame.isNull())
        editor.insertPlainText('new ')
        self.assertTrue(view.stale)
        self.assertIsNone(view.heat)
        self.assertIsNone(view.source_position_at(point))
        self.assertNotIn('· source ', view.tooltip_at(point))
        self.assertFalse(view._position_frame.isNull())


if __name__ == '__main__':
    unittest.main()
