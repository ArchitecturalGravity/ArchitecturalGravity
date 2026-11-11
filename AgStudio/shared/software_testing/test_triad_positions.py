"""ST2 source event transport, final map values, and causal indexed kernels."""
from dataclasses import asdict, replace
import json
import math
import pickle
import random
import unittest

from AgStudio.shared.graph import (
    GraphResult, GraphSnapshot, HeatCancelled, PreparedSemantic, SemanticFootprint,
    SemanticOptions, SemanticPosition, calculate_graph, semantic_state,
)
from AgStudio.shared.graph.adapter import build_graph_snapshot
from AgStudio.shared.graph.semantic import calculate_semantic_views
from AgStudio.shared.lint import analyze


def graph(source, **options):
    analysis = analyze(source)
    return build_graph_snapshot(analysis.tree, analysis.semantics,
                                mode='semantic_triad_2', options=options)


def detached(footprints=(), *, length=100, decay=1, positions=()):
    return GraphSnapshot((0,), (), (), mode='semantic_triad_2', options={'decay': decay},
                         points=((0, length),), document_length=length,
                         semantic_footprints=footprints, semantic_positions=positions)


def oracle(footprint, point, length, decay):
    if not length or point < footprint.available_from:
        return 0.0
    characters = {x for start, end in footprint.definitions + footprint.mentions
                  for x in range(start, min(point, end))}
    return math.fsum(math.exp(-decay * (point - x - 1) / length) / length
                     for x in characters)


class PositionTransportTests(unittest.TestCase):
    def test_same_physical_row_preserves_every_distinct_reference_endpoint(self):
        source = '[A]: seed\nTask: [A] then [A] then [A]\n'
        snapshot = graph(source, decay=0)
        refs = [event for event in snapshot.semantic_positions if event.kind == 'reference_use']
        self.assertEqual(len(refs), 3)
        self.assertEqual(len({event.node for event in refs}), 1)
        self.assertEqual([event.position for event in refs], [19, 28, 37])
        result = calculate_graph(snapshot)
        samples = dict(result.position_values)
        values = [dict(samples[event.position])['A'] for event in refs]
        final_value = dict(semantic_state(snapshot, len(source)))['A']
        self.assertEqual(values, [final_value] * 3)
        old_view = next(view for view in snapshot.semantic_views if view.kind == 'reference_use')
        self.assertEqual(old_view.position, refs[-1].position)

    def test_duplicate_body_boundaries_do_not_expand_definition_footprint(self):
        source = '[A]: first\n[A]: second\n'
        snapshot = graph(source)
        starts = [event.position for event in snapshot.semantic_positions if event.kind == 'object_start']
        ends = [event.position for event in snapshot.semantic_positions if event.kind == 'object_end']
        self.assertEqual(starts, [0, source.index('[A]', 1)])
        self.assertEqual(ends, [source.index('[A]', 1), len(source)])
        self.assertEqual(snapshot.semantic_footprints[0].definitions, ((0, source.index('[A]', 1)),))

    def test_resolved_references_have_both_start_and_end_and_unresolved_have_neither(self):
        source = 'Before [Missing]\n[A]: seed\nTask: [A] [Missing]\n'
        snapshot = graph(source)
        start = source.index('[A]', source.index('Task:'))
        refs = [(event.kind, event.position) for event in snapshot.semantic_positions
                if event.kind.startswith('reference_')]
        self.assertEqual(refs, [('reference_start', start), ('reference_use', start + 3)])

    def test_alias_and_parent_boundaries_are_independent(self):
        source = '[A]: seed\n[B]:\n  => [A] AS [Derived]\n  - tail\n'
        snapshot = graph(source)
        aliases = [event for event in snapshot.semantic_positions if event.kind == 'alias_use']
        self.assertEqual(len(aliases), 1)
        self.assertEqual(aliases[0].position, source.index('[Derived]') + len('[Derived]'))
        self.assertEqual(aliases[0].objects, ('Derived',))
        ends = {(event.objects, event.position) for event in snapshot.semantic_positions
                if event.kind == 'object_end'}
        self.assertIn((('B',), len(source)), ends)
        self.assertIn((('Derived',), source.index('  - tail')), ends)

    def test_unicode_crlf_offsets_are_python_character_boundaries(self):
        source = '\ufeff\r\n[A]: 😀é\r\nTask: [A] [A]\r\n'
        snapshot = graph(source)
        refs = [event.position for event in snapshot.semantic_positions if event.kind == 'reference_use']
        self.assertEqual(snapshot.document_length, len(source))
        self.assertEqual(refs, [source.index('[A]', source.index('Task:')) + 3,
                                source.rindex('[A]') + 3])

    def test_snapshot_result_pickle_and_json_keep_compact_detached_input(self):
        source = graph('[A]: seed\nTask: [A] [A]\n')
        restored = GraphSnapshot(**json.loads(json.dumps(asdict(source))))
        self.assertEqual(restored, source)
        result = calculate_graph(restored)
        self.assertEqual(result.position_snapshot, source)
        self.assertEqual(result.states, ())
        self.assertEqual(result.details, ())
        self.assertEqual(result.view_details, ())
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)
        self.assertIsInstance(hash(result), int)
        self.assertTrue(json.dumps(asdict(result), allow_nan=False))
        # All transported samples have only actual event-associated identities.
        associations = {}
        for event in source.semantic_positions:
            associations.setdefault(event.position, set()).update(event.objects)
        for position, values in result.position_values:
            self.assertEqual({name for name, _ in values}, associations[position])

    def test_positions_detach_validate_and_allow_same_node_multiple_events(self):
        names = ['A', 'A']
        event = SemanticPosition(20, names, 'reference_use', 4)
        names.clear()
        self.assertEqual(event.objects, ('A',))
        source = detached((SemanticFootprint('A', ((0, 10),)),), positions=(event,
                          SemanticPosition(30, ('A',), 'reference_use', 4)))
        self.assertEqual(len(source.semantic_positions), 2)
        for kwargs in ({'position': -1}, {'position': True}, {'position': 1, 'node': True},
                       {'position': 1, 'objects': 'A'}, {'position': 1, 'kind': 'guessed'}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                SemanticPosition(**kwargs)
        with self.assertRaisesRegex(ValueError, 'unknown object'):
            replace(source, semantic_positions=(SemanticPosition(2, ('missing',)),))
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            replace(source, semantic_positions=(SemanticPosition(101, ('A',)),))

    def test_result_rejects_invalid_or_duplicate_sparse_samples(self):
        for values in (((True, ()),), ((-1, ()),), ((1, (('A', -1),)),),
                       ((1, (('A', 0), ('A', 1))),), ((1, ()), (1, ()))):
            with self.subTest(values=values), self.assertRaises((TypeError, ValueError)):
                GraphResult((), (), (), position_values=values)

    def test_duplicate_resolution_records_do_not_duplicate_events(self):
        source = '[A]: seed\nTask: [A] [A]\n'
        analysis = analyze(source)
        original = graph(source)
        duplicate = build_graph_snapshot(analysis.tree, replace(analysis.semantics,
            resolutions=analysis.semantics.resolutions * 3), mode='semantic_triad_2')
        self.assertEqual(duplicate.semantic_positions, original.semantic_positions)


class IndexedPositionTests(unittest.TestCase):
    def test_indexed_values_match_character_oracle_at_every_boundary(self):
        rng = random.Random(37)
        footprints = []
        for i in range(8):
            spans = [tuple(sorted((rng.randrange(51), rng.randrange(51)))) for _ in range(6)]
            footprints.append(SemanticFootprint(str(i), spans[:3], spans[3:],
                                               available_from=rng.randrange(51)))
        for decay in (0, 1e-320, .7, 40, 1e308):
            source = detached(footprints, length=50, decay=decay)
            prepared = PreparedSemantic(source)
            for point in range(51):
                for item, (_, actual) in zip(footprints, prepared.values_at(point)):
                    expected = oracle(item, point, 50, decay)
                    self.assertAlmostEqual(actual, expected, places=12)
            maximum = max(oracle(item, point, 50, decay)
                          for point in range(51) for item in footprints)
            self.assertAlmostEqual(prepared.maximum(), maximum, places=12)
            self.assertEqual(prepared.cached_positions, ())

    def test_hover_details_are_exact_existing_triad_readouts_in_source_order(self):
        source = graph('[Zed]: seed\n[Able]: other\nTask: [Zed] AS [Alias]\n', decay=.7)
        prepared = PreparedSemantic(source)
        order = tuple(item.object for item in source.semantic_footprints)
        for point in range(source.document_length + 1):
            values = prepared.details_at(point)
            self.assertEqual(tuple(item.object for item in values), order)
            self.assertEqual(dict((item.object, item.adjusted_linked) for item in values),
                             dict(semantic_state(source, point)))
        final = calculate_graph(source).final_details
        self.assertGreater(len(final), len(order))
        for _node, values in calculate_semantic_views(source):
            self.assertEqual(final, values)

    def test_future_support_never_leaks_and_availability_gate_is_preserved(self):
        a = SemanticFootprint('A', ((0, 10),), ((70, 80),))
        future = SemanticFootprint('Future', ((0, 100),), available_from=60)
        source = detached((a, future), decay=0)
        prepared = PreparedSemantic(source)
        early = {item.object: item for item in prepared.details_at(50)}
        self.assertEqual(early['A'].linked, .1)
        self.assertEqual(early['A'].mention, 0)
        self.assertEqual(early['Future'].linked, 0)
        self.assertEqual(dict(prepared.values_at(60))['Future'], .6)
        self.assertEqual(dict(prepared.values_at(100))['A'], .2)
        changed = PreparedSemantic(replace(source, semantic_footprints=(
            replace(a, mentions=((80, 100),)), future)))
        self.assertEqual(prepared.details_at(50), changed.details_at(50))

    def test_full_vectors_are_bounded_lru_and_partial_values_never_fill_cache(self):
        source = detached((SemanticFootprint('A', ((0, 100),)),))
        prepared = PreparedSemantic(source, cache_size=3)
        for point in range(101):
            prepared.details_at(point)
            self.assertLessEqual(len(prepared.cached_positions), 3)
        self.assertEqual(prepared.cached_positions, (98, 99, 100))
        prepared.details_at(98)
        prepared.details_at(0)
        self.assertEqual(prepared.cached_positions, (100, 98, 0))
        prepared.values_at(50, ('A',))
        self.assertEqual(prepared.cached_positions, (100, 98, 0))
        uncached = PreparedSemantic(source, cache_size=0)
        uncached.details_at(10)
        self.assertEqual(uncached.cached_positions, ())
        for size in (-1, True, 65):
            with self.assertRaises(ValueError):
                PreparedSemantic(source, cache_size=size)

    def test_global_scale_covers_all_final_objects_including_untagged_support(self):
        source = detached((SemanticFootprint('A', ((0, 20),)),
                           SemanticFootprint('B', ((40, 90),))),
                          positions=(SemanticPosition(100, ('A',), 'reference_use'),))
        result = calculate_graph(source)
        prepared = PreparedSemantic(source)
        sampled_max = max(value for _, values in result.position_values for _, value in values)
        self.assertGreater(result.position_maximum, sampled_max)
        final_values = prepared.values_at(source.document_length)
        self.assertEqual(result.position_maximum, max(value for _, value in final_values))
        self.assertGreater(prepared.maximum(), result.position_maximum)

    def test_automatic_preparation_ignores_selection_and_comparison_options(self):
        source = detached((SemanticFootprint('Zed', ((0, 30),)),
                           SemanticFootprint('Able', ((10, 40),))))
        biased = replace(source, options=SemanticOptions(selected_object='gone',
                                                        comparison_objects=('gone',)))
        self.assertEqual(PreparedSemantic(source).details_at(50),
                         PreparedSemantic(biased).details_at(50))

    def test_empty_sources_parser_disabled_and_out_of_range_queries(self):
        prepared = PreparedSemantic(detached(length=0))
        self.assertEqual(prepared.details_at(0), ())
        self.assertEqual(prepared.values_at(0), ())
        self.assertEqual(prepared.maximum(), 0)
        for point in (-1, 1, True, .5):
            with self.assertRaises(ValueError):
                prepared.details_at(point)
        source = graph('[A]: seed\nTask: [A]\n', parser_support=False)
        self.assertEqual(source.semantic_positions, ())
        self.assertEqual(calculate_graph(source).position_values, ())

    def test_cancellation_interrupts_preparation_sampling_and_cached_hover(self):
        source = graph('[A]: seed\nTask: [A] [A]\n')
        for call in (lambda: PreparedSemantic(source, cancelled=lambda: True),
                     lambda: calculate_graph(source, cancelled=lambda: True)):
            with self.assertRaises(HeatCancelled):
                call()
        prepared = PreparedSemantic(source)
        prepared.details_at(0)
        for call in (lambda: prepared.details_at(0, cancelled=lambda: True),
                     lambda: prepared.values_at(0, cancelled=lambda: True),
                     lambda: prepared.maximum(cancelled=lambda: True)):
            with self.assertRaises(HeatCancelled):
                call()
        polls = 0
        def cancelled():
            nonlocal polls
            polls += 1
            return polls >= 8
        with self.assertRaises(HeatCancelled):
            calculate_graph(source, cancelled=cancelled)
        self.assertEqual(polls, 8)

    def test_large_sparse_fixture_has_linear_sample_and_snapshot_sizes(self):
        count = 1000
        footprints = tuple(SemanticFootprint(f'O{i}', ((i * 20, i * 20 + 5),),
                            ((i * 20 + 10, i * 20 + 13), (i * 20 + 15, i * 20 + 18)))
                           for i in range(count))
        events = tuple(SemanticPosition(i * 20 + end, (f'O{i}',), 'reference_use', i)
                       for i in range(count) for end in (13, 18))
        source = detached(footprints, length=count * 20, positions=events)
        result = calculate_graph(source)
        self.assertEqual(len(result.position_values), 2 * count)
        self.assertEqual(sum(len(values) for _, values in result.position_values), 2 * count)
        self.assertEqual(result.view_details, ())
        self.assertEqual(result.details, ())
        self.assertLess(len(pickle.dumps(result)), count * 500)
        prepared = PreparedSemantic(result.position_snapshot, cache_size=2)
        for point in (0, 1000, 5000, 19000):
            self.assertEqual(len(prepared.details_at(point)), count)
        self.assertEqual(len(prepared.cached_positions), 2)


if __name__ == '__main__':
    unittest.main()
