"""Structural map inheritance, independently checked against source characters.

These are map/presentation contracts, not additional ArcGrav language rules.
Named causal readouts remain a separate API from the final structural vector.
"""
from dataclasses import asdict, replace
import importlib.util
import json
import math
import os
import pickle
import unittest

from AgStudio.shared.graph import GraphSnapshot, PreparedSemantic, calculate_graph, semantic_state
from AgStudio.shared.graph.adapter import build_graph_snapshot
from AgStudio.shared.lint import analyze

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
MODES = ('semantic_triad_1', 'semantic_triad_2')


def graph(source, mode='semantic_triad_2', **options):
    analysis = analyze(source)
    return build_graph_snapshot(analysis.tree, analysis.semantics, mode=mode,
                                options={'decay': 0, **options})


def values(result):
    return {item.object: item.adjusted_linked for item in result.final_details}


def elements(snapshot):
    return {item.object: item for item in snapshot.semantic_elements}


def structural(snapshot, node):
    named = {item.object for item in snapshot.semantic_footprints}
    return next(item for item in snapshot.semantic_elements
                if item.node == node and item.object not in named)


def occurrences(source, token):
    start = 0
    while (start := source.find(token, start)) >= 0:
        yield start, start + len(token)
        start += len(token)


def character_oracle(source, spans, decay=0):
    """Deliberately expand source characters instead of reusing interval code."""
    length = len(source)
    characters = {position for start, end in spans for position in range(start, end)}
    return math.fsum(math.exp(-decay * (length - position - 1) / length) / length
                     for position in characters) if length else 0.


class InheritedStructuralBaselineTests(unittest.TestCase):
    def test_plain_task_has_its_own_nonzero_baseline_in_every_mode(self):
        source = 'Task:\n  - ordinary words only\n'
        for mode in MODES:
            with self.subTest(mode=mode):
                snapshot = graph(source, mode)
                task = structural(snapshot, 0)
                self.assertEqual(task.label, 'Task:')
                self.assertNotEqual(task.object, 'Task')
                self.assertEqual(task.definitions, ((0, len(source)),))
                self.assertEqual(task.dependencies, ())
                self.assertEqual(snapshot.semantic_footprints, ())
                self.assertEqual(values(calculate_graph(snapshot)), {task.object: 1.})
                self.assertEqual(snapshot.semantic_views[1].objects, (task.object,))

    def test_task_inherits_constraint_and_shared_reference_text_is_counted_once(self):
        source = '[Constraint]: bound\nTask:\n  - follow [Constraint] closely\n'
        for mode in MODES:
            for decay in (0, .7, 4):
                with self.subTest(mode=mode, decay=decay):
                    snapshot = graph(source, mode, decay=decay)
                    task = structural(snapshot, 1)
                    self.assertEqual(task.dependencies, ('Constraint',))
                    final = values(calculate_graph(snapshot))
                    self.assertAlmostEqual(final[task.object],
                                           character_oracle(source, ((0, len(source)),), decay),
                                           places=14)
                    target_spans = ((0, source.index('Task:')), *occurrences(source, '[Constraint]'))
                    self.assertAlmostEqual(final['Constraint'],
                                           character_oracle(source, target_spans, decay), places=14)

    def test_repeated_references_add_only_their_new_physical_support(self):
        before = '[A]: seed\nTask: [A] [A]\nLater: xxx\n'
        after = before.replace('xxx', '[A]')
        self.assertEqual(len(before), len(after))
        old, new = graph(before), graph(after)
        task = structural(new, 1).object
        self.assertEqual(elements(new)[task].dependencies, ('A',))
        previous, current = values(calculate_graph(old)), values(calculate_graph(new))
        self.assertAlmostEqual(current['A'] - previous['A'], 3 / len(after))
        self.assertAlmostEqual(current[task] - previous[task], 3 / len(after))
        # Mention support elsewhere does not bring along its receiver's label.
        self.assertAlmostEqual(current[task],
                               (after.index('Later:') + 3) / len(after))

    def test_duplicate_resolution_evidence_never_duplicates_support_or_dependencies(self):
        source = '[A]: seed\nTask: [A] [A]\n'
        analysis = analyze(source)
        original = graph(source)
        repeated = build_graph_snapshot(
            analysis.tree, replace(analysis.semantics,
                                   resolutions=analysis.semantics.resolutions * 5),
            mode='semantic_triad_2', options={'decay': 0})
        self.assertEqual(repeated.semantic_elements, original.semantic_elements)
        self.assertEqual(calculate_graph(repeated).final_details,
                         calculate_graph(original).final_details)

    def test_transitive_diamond_uses_union_instead_of_counting_paths(self):
        source = ('[A]: seed\n[B]: left [A]\n[C]: right [A]\n'
                  '[D]: use [B] [C]\nTask: [D]\n')
        for decay in (0, 2):
            snapshot = graph(source, decay=decay)
            entries = elements(snapshot)
            self.assertEqual(entries['D'].dependencies, ('B', 'C'))
            self.assertEqual(entries['B'].dependencies, ('A',))
            self.assertEqual(entries['C'].dependencies, ('A',))
            task = structural(snapshot, 4)
            final = values(calculate_graph(snapshot))
            d_spans = ((0, source.index('Task:')), *occurrences(source, '[D]'))
            b_spans = ((0, source.index('[C]:')),
                       *occurrences(source, '[A]'), *occurrences(source, '[B]'))
            self.assertAlmostEqual(final['D'], character_oracle(source, d_spans, decay), places=14)
            self.assertAlmostEqual(final['B'], character_oracle(source, b_spans, decay), places=14)
            self.assertAlmostEqual(final[task.object],
                                   character_oracle(source, ((0, len(source)),), decay), places=14)
            self.assertTrue(all(0 <= score <= 1 for score in final.values()))

    def test_duplicate_anchor_does_not_create_spurious_cyclic_support(self):
        source = '[A]: seed\n[B]: uses [A]\n[A]: uses [B]\nTask: use [A]\n'
        for decay in (0, 1.5):
            snapshot = graph(source, decay=decay)
            entries = elements(snapshot)
            self.assertEqual(entries['A'].dependencies, ())
            self.assertEqual(entries['B'].dependencies, ('A',))
            final = values(calculate_graph(snapshot))
            self.assertGreater(final['A'], 0)
            self.assertGreater(final['B'], 0)
            self.assertTrue(all(0 <= score <= 1 for score in final.values()))

    def test_alias_inherits_its_expression_sources_without_stealing_source_support(self):
        source = '[A]: seed\nBuild: [A] AS [B]\nTask: use [B]\n'
        snapshot = graph(source)
        entries = elements(snapshot)
        self.assertEqual(entries['B'].dependencies, ('A',))
        final = values(calculate_graph(snapshot))
        alias_spans = ((0, source.index('Build:')),
                       (source.index('Build:') + len('Build:'), source.index('Task:')),
                       *occurrences(source, '[B]'))
        a_spans = ((0, source.index('Build:')), *occurrences(source, '[A]'))
        self.assertAlmostEqual(final['B'], character_oracle(source, alias_spans), places=14)
        self.assertAlmostEqual(final['A'], character_oracle(source, a_spans), places=14)
        self.assertGreater(final[structural(snapshot, 2).object], final['B'])

    def test_nested_plain_body_has_own_baseline_and_inherits_into_parent(self):
        source = '[A]: seed\nTask:\n  Child:\n    obey [A]\nNext: other\n'
        snapshot = graph(source)
        task, child, other = (structural(snapshot, node) for node in (1, 2, 4))
        self.assertNotEqual(task.object, child.object)
        self.assertIn(child.object, task.dependencies)
        self.assertEqual(child.dependencies, ('A',))
        self.assertEqual(snapshot.semantic_views[3].objects, ('A', child.object))
        final = values(calculate_graph(snapshot))
        child_spans = ((0, source.index('Task:')),
                       (source.index('  Child:'), source.index('Next:')))
        self.assertAlmostEqual(final[child.object], character_oracle(source, child_spans))
        self.assertAlmostEqual(final[task.object], source.index('Next:') / len(source))
        self.assertEqual(other.dependencies, ())

    def test_unresolved_forward_quoted_and_wildcard_tokens_do_not_invent_dependencies(self):
        source = ('[A]: seed\nTask: [Missing] [Future] "[A]" [A*]\n'
                  '[Future]: declared later\n')
        snapshot = graph(source)
        task = structural(snapshot, 1)
        self.assertEqual(task.dependencies, ())
        self.assertNotIn('Missing', elements(snapshot))
        self.assertNotIn('A*', elements(snapshot))
        self.assertAlmostEqual(values(calculate_graph(snapshot))[task.object],
                               (source.index('[Future]:') - source.index('Task:')) / len(source))

    def test_internal_structural_identity_does_not_create_named_causal_objects(self):
        source = '[A]: seed\n[B]: uses [A]\nTask: [B]\n'
        snapshot = graph(source, decay=.7)
        causal_only = replace(snapshot, semantic_elements=(), semantic_views=(), semantic_positions=())
        for position in (0, source.index('Task:'), len(source)):
            self.assertEqual(semantic_state(snapshot, position), semantic_state(causal_only, position))
            self.assertEqual(PreparedSemantic(snapshot).details_at(position),
                             PreparedSemantic(causal_only).details_at(position))
        self.assertEqual({name for name, _ in semantic_state(snapshot, len(source))}, {'A', 'B'})
        self.assertGreater(values(calculate_graph(snapshot))['B'],
                           dict(semantic_state(snapshot, len(source)))['B'])

    def test_all_map_modes_publish_same_complete_inherited_vector(self):
        source = '[A]: seed\n[B]: [A]\nTask:\n  before [B] after\n'
        vectors = []
        for mode in MODES:
            snapshot = graph(source, mode, decay=.7)
            result = calculate_graph(snapshot)
            vectors.append(result.final_details)
            for _, details in result.view_details:
                self.assertEqual(details, result.final_details)
            for _, samples in result.position_values:
                for name, score in samples:
                    self.assertEqual(score, values(result)[name])
        self.assertEqual(vectors, [vectors[0]] * len(MODES))

    def test_structural_transport_is_detached_and_round_trips(self):
        snapshot = graph('[A]: seed\nTask: [A]\n')
        restored = GraphSnapshot(**json.loads(json.dumps(asdict(snapshot))))
        self.assertEqual(restored, snapshot)
        self.assertEqual(pickle.loads(pickle.dumps(snapshot)), snapshot)
        self.assertEqual(calculate_graph(restored), calculate_graph(snapshot))

    def test_disabling_parser_support_disables_structural_evidence(self):
        snapshot = graph('[A]: seed\nTask: [A]\n', parser_support=False)
        self.assertEqual(snapshot.semantic_elements, ())
        self.assertEqual(calculate_graph(snapshot).final_details, ())


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class InheritedBaselinePresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_map(self, source):
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import DocumentMap
        from AgStudio.gui.inference_heat import compute_heat
        editor = SourceEditor()
        editor.resize(800, 350)
        editor.setPlainText(source)
        editor.show()
        view = DocumentMap(editor, mode='semantic_triad_2')
        view.resize(500, 350)
        view.show()
        self.app.processEvents()
        analysis = analyze(source)
        heat = compute_heat(analysis.tree, analysis.semantics, mode='semantic_triad_2',
                            options={'decay': 0})
        view.set_model(analysis.document, analysis.tree, heat=heat)
        view.rebuild()
        self.app.processEvents()
        for widget in (editor, view):
            self.addCleanup(widget.deleteLater)
            self.addCleanup(widget.close)
        return view

    def segment_at(self, view, position):
        matches = [segment for row in view.rows
                   for interval, segment in zip(view._position_intervals(row),
                                                view.position_segments(row))
                   if interval.start <= position < interval.end]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_task_words_use_task_baseline_and_inline_token_uses_constraint(self):
        from AgStudio.gui.inference_heat import heat_rgb
        source = '[Constraint]: bound\nTask:\n  - follow [Constraint] closely\n'
        view = self.make_map(source)
        task = structural(view.heat.position_snapshot, 1)
        for text in ('Task:', 'follow', 'closely'):
            segment = self.segment_at(view, source.index(text))
            self.assertEqual(segment.object, task.object)
            self.assertEqual(segment.color,
                             heat_rgb(view.heat.final_values[task.object], *view._heat_range))
        target = self.segment_at(view, source.rindex('[Constraint]'))
        self.assertEqual(target.object, 'Constraint')
        self.assertEqual(target.color,
                         heat_rgb(view.heat.final_values['Constraint'], *view._heat_range))
        self.assertNotEqual(target.color, self.segment_at(view, source.index('follow')).color)

    def test_plain_task_without_symbols_is_painted_with_its_own_support(self):
        source = 'Task:\n  ordinary words only\n'
        view = self.make_map(source)
        task = structural(view.heat.position_snapshot, 0)
        self.assertGreater(view.heat.final_values[task.object], 0)
        for row in view.rows:
            for segment in view.position_segments(row):
                self.assertEqual(segment.object, task.object)
                self.assertNotEqual(segment.color, (128, 128, 128))

    def test_nested_plain_section_paints_its_baseline_in_named_body(self):
        source = '[B]: bound\n[A]:\n  named words\n  Child:\n    plain [B] tail\n'
        view = self.make_map(source)
        child = structural(view.heat.position_snapshot, 3)
        self.assertEqual(self.segment_at(view, source.index('named words')).object, 'A')
        for text in ('Child:', 'plain', 'tail'):
            self.assertEqual(self.segment_at(view, source.index(text)).object, child.object)
        self.assertEqual(self.segment_at(view, source.rindex('[B]')).object, 'B')


if __name__ == '__main__':
    unittest.main()
