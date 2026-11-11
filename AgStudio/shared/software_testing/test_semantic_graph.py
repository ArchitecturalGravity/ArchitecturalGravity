"""Character-coverage transport and explicit legacy migration contracts.

These are presentation/geometry tests, not language conformance claims.
Detailed interval and discrete-kernel oracles live in test_triad_coverage.py.
"""
from dataclasses import FrozenInstanceError, asdict, replace
import json
import math
import pickle
import unittest

from AgStudio.shared.graph import (
    GRAPH_MODES, GraphResult, GraphSnapshot, HeatCancelled, HeatScore, SemanticFootprint,
    SemanticOptions, SemanticRepresentation, SemanticTransformation, SemanticView, calculate_graph,
    normalize_graph_mode, score_relations, semantic_state, validate_options,
)


def representation(name='A', position=0, weight=1.0):
    return {'object': name, 'position': position, 'weight': weight}


def transformation(kind, position, factor, name='A', target=None):
    record = {'kind': kind, 'object': name, 'position': position, 'factor': factor}
    if target is not None:
        record['target'] = target
    return record


def snapshot(*, mode='semantic_triad_1', footprints=(), sources=(), operations=(), decay=0.0,
             points=((0, 100),), length=100, evidence=(), parser_support=True):
    return GraphSnapshot(tuple(block for block, _ in points), (), (), mode,
                         {'decay': decay, 'parser_support': parser_support,
                          'representations': sources, 'transformations': operations},
                         evidence, points, length, semantic_footprints=footprints)


def oracle(spans, point, length, decay):
    characters = {x for start, end in spans for x in range(start, min(point, end))}
    return math.fsum(math.exp(-decay * (point - x - 1) / length) / length
                     for x in characters) if length else 0.0


class SemanticTransportTests(unittest.TestCase):
    def test_known_exponential_character_support_fixture(self):
        support = ((0, 20), (50, 80))
        graph = snapshot(footprints=(SemanticFootprint('A', support),), decay=1,
                         points=((0, 0), (1, 50), (2, 100)))
        scores = dict(calculate_graph(graph).scores)
        for block, point in graph.points:
            self.assertAlmostEqual(scores[block].total, oracle(support, point, 100, 1))
            self.assertEqual((scores[block].direct_count, scores[block].indirect_count), (0, 0))

    def test_more_characters_add_raw_coverage_and_nearer_support_is_stronger(self):
        early = snapshot(footprints=(SemanticFootprint('A', ((0, 10),)),), decay=2)
        late = snapshot(footprints=(SemanticFootprint('A', ((90, 100),)),), decay=2)
        one = snapshot(footprints=(SemanticFootprint('A', ((0, 10),)),))
        two = snapshot(footprints=(SemanticFootprint('A', ((0, 20),)),))
        self.assertLess(dict(semantic_state(early, 100))['A'], dict(semantic_state(late, 100))['A'])
        self.assertEqual(dict(semantic_state(two, 100))['A'], 2 * dict(semantic_state(one, 100))['A'])

    def test_no_future_character_support_affects_earlier_use(self):
        graph = snapshot(footprints=(SemanticFootprint('A', ((10, 20),), ((60, 80),)),),
                         points=((0, 50), (1, 100)))
        scores = dict(calculate_graph(graph).scores)
        self.assertEqual(scores[0], HeatScore(.1))
        self.assertEqual(scores[1], HeatScore(.3))
        self.assertEqual(dict(semantic_state(graph, 0))['A'], 0)

    def test_legacy_operator_kinds_and_identity_factors_are_explicitly_rejected(self):
        operations = [transformation('reinforce', 50, 4),
                      transformation('suppress', 50, .25),
                      transformation('reinterpret', 50, .25, target='B'),
                      transformation('reinforce', 50, 1),
                      transformation('suppress', 50, 1),
                      transformation('reinterpret', 50, 0, target='B')]
        for operation in operations:
            graph = snapshot(footprints=(SemanticFootprint('A', ((0, 10),)),), operations=[operation])
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'footprint|coverage'):
                calculate_graph(graph)

    def test_legacy_operator_order_or_position_does_not_bypass_migration_error(self):
        redirect = transformation('reinterpret', 30, .5, target='B')
        reinforce = transformation('reinforce', 60, 3, name='B')
        for operations in ([redirect, reinforce], [reinforce, redirect],
                           [transformation('suppress', 0, 0)]):
            with self.subTest(operations=operations), self.assertRaisesRegex(ValueError, 'footprint|coverage'):
                semantic_state(snapshot(operations=operations), 100)

    def test_legacy_point_sources_cannot_mix_with_character_footprints(self):
        for footprints in ((), (SemanticFootprint('A', ((0, 10),)),)):
            with self.subTest(footprints=footprints), self.assertRaisesRegex(ValueError, 'footprint|coverage'):
                calculate_graph(snapshot(footprints=footprints, sources=[representation()]))

    def test_combined_character_readouts_match_independent_discrete_oracle(self):
        positions = (0, 20, 40, 60, 70, 100)
        a = SemanticFootprint('A', ((0, 20),), ((70, 73),))
        b = SemanticFootprint('B', ((10, 40),), ((60, 63),))
        graph = snapshot(footprints=(a, b), decay=1, points=tuple(enumerate(positions)))
        result = calculate_graph(graph)
        for block, point in graph.points:
            state = dict(dict(result.states)[block])
            self.assertEqual(dict(result.states)[block], semantic_state(graph, point))
            for footprint in (a, b):
                expected = oracle(footprint.definitions + footprint.mentions, point, 100, 1)
                self.assertAlmostEqual(state[footprint.object], expected, places=14)
            self.assertAlmostEqual(dict(result.scores)[block].total, state['A'], places=14)

    def test_zero_decay_adds_unique_characters_without_distance_penalty(self):
        graph = snapshot(footprints=(SemanticFootprint('A', ((0, 20),), ((90, 100),)),))
        self.assertEqual(dict(semantic_state(graph, 100)), {'A': .3})

    def test_raw_normalized_geometry_is_invariant_under_uniform_rescaling(self):
        one = snapshot(footprints=(SemanticFootprint('A', ((25, 50),)),), points=((0, 75),))
        two = snapshot(footprints=(SemanticFootprint('A', ((50, 100),)),), points=((0, 150),), length=200)
        self.assertEqual(calculate_graph(one), calculate_graph(two))

    def test_zero_length_and_eof_positions_are_well_defined(self):
        graph = snapshot(footprints=(SemanticFootprint('A'),), points=((0, 0),), length=0, decay=9)
        self.assertEqual(dict(calculate_graph(graph).scores)[0].total, 0)
        self.assertEqual(calculate_graph(snapshot(points=(), length=0)).scores, ())

    def test_extreme_finite_decay_underflows_safely(self):
        graph = snapshot(footprints=(SemanticFootprint('A', ((0, 1),)),), decay=1e308)
        self.assertEqual(dict(semantic_state(graph, 100)), {'A': 0})

    def test_declared_parser_footprints_can_be_disabled(self):
        graph = snapshot(footprints=(SemanticFootprint('A', ((0, 10),)),))
        self.assertEqual(dict(semantic_state(graph, 100)), {'A': .1})
        self.assertEqual(semantic_state(replace(graph, options={'parser_support': False}), 100), ())

    def test_semantic_scoring_ignores_graph_hops(self):
        graph = snapshot(footprints=(SemanticFootprint('A', ((0, 10),)),), points=((0, 100), (1, 100)))
        edges = replace(graph, occurrences=((0, 1),) * 15)
        self.assertEqual(calculate_graph(graph).scores, calculate_graph(edges).scores)
        self.assertEqual(calculate_graph(edges).relations, edges.occurrences)


class SemanticContractTests(unittest.TestCase):
    def test_canonical_mode_membership_and_legacy_aliases(self):
        self.assertEqual(GRAPH_MODES, ('heuristic', 'semantic_triad_1', 'semantic_triad_2'))
        self.assertEqual(GraphSnapshot((), (), ()).mode, 'heuristic')
        for mode in GRAPH_MODES:
            self.assertEqual(normalize_graph_mode(mode), mode)
        for legacy in ('semantic_triad', 'semantic_triad_3'):
            self.assertEqual(snapshot(mode=legacy).mode, 'semantic_triad_2')
            self.assertEqual(normalize_graph_mode(legacy), 'semantic_triad_2')
        for mode in ('semantic_basic', 'semantic_full'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                snapshot(mode=mode)

    def test_result_object_vectors_are_detached_finite_and_serializable(self):
        values = [['A', 1.0]]
        result = GraphResult([], [[0, HeatScore(1)]], [], [[0, values]])
        values[0][1] = 99
        self.assertEqual(result.states, ((0, (('A', 1.0),)),))
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)
        self.assertIsInstance(hash(result), int)
        self.assertEqual(json.loads(json.dumps(asdict(result)))['states'], [[0, [['A', 1.0]]]])
        for states in ([[0, [['A', math.inf]]]], [[0, [['A', -1]]]],
                       [[0, [['A', 1], ['A', 2]]]], [[0, []], [0, []]]):
            with self.subTest(states=states), self.assertRaises(ValueError):
                GraphResult((), (), (), states)

    def test_invalid_options_rejected_without_silent_coercion(self):
        invalid = [[], 1, {'unknown': 3}, {'parser_support': 1}, {'parser_transformations': 1}, {'decay': True},
                   {'decay': -1}, {'decay': math.nan}, {'decay': math.inf}, {'decay': '1'},
                   {'representations': {}}, {'transformations': {}},
                   {'representations': [representation(name=' ')]},
                   {'representations': [representation(position=-1)]},
                   {'representations': [representation(position=True)]},
                   {'representations': [representation(position=1.5)]},
                   {'representations': [representation(position=101)]},
                   {'representations': [representation(weight=-1)]},
                   {'representations': [representation(weight=math.nan)]},
                   {'transformations': [transformation('guess', 50, 1)]},
                   {'transformations': [transformation('reinforce', 50, 0.5)]},
                   {'transformations': [transformation('suppress', 50, 2)]},
                   {'transformations': [transformation('reinterpret', 50, -0.5, target='B')]},
                   {'transformations': [transformation('reinterpret', 50, 0.5)]},
                   {'transformations': [transformation('reinforce', 50, 2, target='B')]},
                   {'transformations': [transformation('suppress', 50, math.inf)]}]
        for options in invalid:
            with self.subTest(options=options), self.assertRaises((ValueError, TypeError)):
                validate_options(options, 100)

    def test_invalid_snapshot_geometry_and_modes_rejected(self):
        graph = snapshot()
        for changes in ({'mode': 'SEMANTIC'}, {'points': ()}, {'points': ((99, 100),)},
                        {'points': ((0, -1),)}, {'points': ((0, 101),)},
                        {'points': ((0, 20), (0, 30))}, {'document_length': -1},
                        {'semantic_evidence': [SemanticRepresentation('A', 101)]}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                replace(graph, **changes)

    def test_state_api_rejects_nonsemantic_and_out_of_bounds_use(self):
        for graph, point in ((GraphSnapshot((), (), ()), 0), (snapshot(), -1),
                             (snapshot(), 101), (snapshot(), True)):
            with self.subTest(point=point), self.assertRaises(ValueError):
                semantic_state(graph, point)


    def test_json_pickle_and_hash_roundtrips(self):
        graph = snapshot(footprints=(SemanticFootprint('A', ((0, 20),), ((50, 53),)),))
        record = json.loads(json.dumps(asdict(graph), allow_nan=False))
        restored = GraphSnapshot(**record)
        self.assertEqual(graph, restored)
        self.assertEqual(hash(graph), hash(restored))
        self.assertEqual(pickle.loads(pickle.dumps(graph)), graph)
        self.assertEqual(calculate_graph(restored), calculate_graph(graph))
        self.assertEqual(hash(calculate_graph(restored)), hash(calculate_graph(graph)))

    def test_configuration_is_deeply_detached_and_frozen(self):
        spans = [[0, 20]]
        graph = snapshot(footprints=[{'object': 'A', 'definitions': spans}])
        spans[0][1] = 90
        self.assertEqual(dict(semantic_state(graph, 100)), {'A': .2})
        with self.assertRaises(FrozenInstanceError):
            graph.options.decay = 9
        with self.assertRaises(FrozenInstanceError):
            graph.semantic_footprints[0].definitions = ((0, 90),)

    def test_finite_geometry_and_extreme_decay_publish_only_finite_results(self):
        graph = snapshot(footprints=(SemanticFootprint('A', ((0, 100),)),), decay=1e308)
        result = calculate_graph(graph)
        self.assertTrue(all(math.isfinite(value) for _, values in result.states for _, value in values))
        self.assertEqual(result.scores[0][1].total, .01)
        json.dumps(asdict(result), allow_nan=False)

    def test_cancellation_interrupts_character_calculation_and_readout(self):
        graph = snapshot(footprints=tuple(SemanticFootprint(str(i), ((i, i+1),)) for i in range(100)))
        for stop in (1, 25, 75):
            polls = 0
            def cancelled():
                nonlocal polls
                polls += 1
                return polls >= stop
            with self.subTest(stop=stop), self.assertRaises(HeatCancelled):
                calculate_graph(graph, cancelled=cancelled)
            self.assertEqual(polls, stop)


class SemanticAdapterTests(unittest.TestCase):
    def graph(self, source, mode='semantic_triad_1', options=None):
        from AgStudio.shared.graph.adapter import build_graph_snapshot
        from AgStudio.shared.lint import analyze
        analysis = analyze(source)
        return build_graph_snapshot(analysis.tree, analysis.semantics, mode=mode,
                                    options={'decay': 0} if options is None else options)

    def test_adapter_and_gui_heat_facade_reject_legacy_mode_ids(self):
        from AgStudio.gui.inference_heat import compute_heat
        from AgStudio.shared.graph.adapter import build_graph_snapshot
        from AgStudio.shared.lint import analyze
        analysis = analyze('[A]: value\n[B]: [A]\n')
        for mode in ('semantic_basic', 'semantic_full'):
            for builder in (build_graph_snapshot, compute_heat):
                with self.subTest(mode=mode, builder=builder), self.assertRaises(ValueError):
                    builder(analysis.tree, analysis.semantics, mode=mode)

    def test_unknown_unresolved_and_quoted_prose_create_no_semantic_events(self):
        source = 'Instructions:\n- Suppress the prior rule\n- Use [Missing]\n- "[Quoted]"\n'
        graph = self.graph(source)
        self.assertEqual(graph.semantic_evidence, ())
        self.assertEqual(graph.semantic_transformations, ())
        self.assertTrue(all(score.total == 0 for _, score in calculate_graph(graph).scores))

    def test_prose_verbs_are_neutral_when_geometry_matches(self):
        cancel = self.graph('[A]: value\n- Cancel [A]\n')
        praise = self.graph('[A]: value\n- Praise [A]\n')
        # Source labels remain honest presentation metadata; prose wording
        # itself must not add numeric reinforcement or suppression.
        unlabeled = lambda graph: replace(graph, semantic_elements=tuple(
            replace(item, label='') for item in graph.semantic_elements))
        self.assertEqual(unlabeled(cancel), unlabeled(praise))
        self.assertEqual(replace(calculate_graph(cancel), position_snapshot=None),
                         replace(calculate_graph(praise), position_snapshot=None))


    def test_automatic_operator_flag_has_no_effect_on_character_coverage(self):
        source = '[A]: value\n\n[B]:\n- Use [A] [A] AS [Alias]\n'
        disabled = self.graph(source, options={'decay': 1.7, 'parser_transformations': False})
        enabled = self.graph(source, options={'decay': 1.7, 'parser_transformations': True})
        self.assertEqual(disabled.semantic_footprints, enabled.semantic_footprints)
        self.assertEqual(enabled.semantic_evidence, ())
        self.assertEqual(enabled.semantic_transformations, ())
        self.assertEqual(disabled.semantic_elements, enabled.semantic_elements)
        self.assertEqual(replace(calculate_graph(disabled), position_snapshot=None),
                         replace(calculate_graph(enabled), position_snapshot=None))

    def test_disabling_parser_support_omits_all_extracted_footprints(self):
        graph = self.graph('[A]: value\n[B]: [A]\n', options={'parser_support': False})
        self.assertEqual(graph.semantic_footprints, ())
        self.assertTrue(all(score.total == 0 for _, score in calculate_graph(graph).scores))

    def test_aliases_stay_distinct_within_one_whole_block_without_source_depletion(self):
        source = '[A]:\n- value\n=> Read [A] AS [Alias]\n'
        graph = self.graph(source)
        self.assertEqual(len(graph.blocks), 1)
        footprints = {item.object: item for item in graph.semantic_footprints}
        self.assertEqual(set(footprints), {'A', 'Alias'})
        self.assertEqual(footprints['Alias'].definitions, ((source.index('=>'), len(source)),))
        state = dict(semantic_state(graph, len(source)))
        self.assertEqual(state['A'], 1)
        self.assertEqual(state['Alias'], (len(source) - source.index('=>')) / len(source))
        self.assertEqual(dict(calculate_graph(graph).states)[graph.blocks[0]], tuple(sorted(state.items())))

    def test_alias_lists_each_exact_source_identity_once(self):
        source = '[A]: value\n[B]: value\n[C]: value\n=> [A] [A] [B] AS [Alias]\n'
        graph = self.graph(source)
        footprints = {item.object: item for item in graph.semantic_footprints}
        self.assertEqual(footprints['Alias'].relationships,
                         ('AS source references A', 'AS source references B'))
        self.assertEqual(len(footprints['A'].mentions), 2)
        self.assertEqual(len(footprints['B'].mentions), 1)
        self.assertEqual(graph.semantic_transformations, ())

    def test_duplicate_alias_does_not_extend_original_definition_or_infer_self_edge(self):
        source = '[A]: value\n=> Read [A] AS [A]\n'
        graph = self.graph(source)
        self.assertEqual(len(graph.semantic_footprints), 1)
        footprint = graph.semantic_footprints[0]
        self.assertEqual(footprint.object, 'A')
        self.assertEqual(footprint.definitions, ((0, source.index('=>')),))
        self.assertFalse(any('AS source' in relation for relation in footprint.relationships))

    def test_duplicate_alias_target_does_not_extend_original_definition(self):
        source = '[A]: value\n[B]: value\n=> [A] AS [Alias]\n=> [B] AS [Alias]\n'
        graph = self.graph(source)
        footprints = {item.object: item for item in graph.semantic_footprints}
        self.assertEqual(set(footprints), {'A', 'B', 'Alias'})
        self.assertEqual(footprints['Alias'].definitions,
                         ((source.index('=>'), source.rindex('=>')),))
        self.assertEqual(footprints['Alias'].relationships, ('AS source references A',))

    def test_duplicate_body_does_not_extend_original_definition_characters(self):
        source = '[A]: first\n[A]: second\n'
        graph = self.graph(source)
        self.assertEqual(len(graph.semantic_footprints), 1)
        self.assertEqual(graph.semantic_footprints[0].definitions,
                         ((0, source.index('[A]', 1)),))
        self.assertLess(dict(semantic_state(graph, len(source)))['A'], 1)

    def test_nested_duplicate_body_stays_with_parent_without_child_identity(self):
        source = ('[Child]: value\n\n[Parent]:\n  [Child]:\n  - details\n'
                  '  Tail:\n  - more\n\nNext: value\n')
        graph = self.graph(source)
        footprints = {item.object: item for item in graph.semantic_footprints}
        parent_start = source.index('[Parent]')
        child_start = source.index('  [Child]')
        child_end = source.index('  Tail:')
        parent_end = source.index('\n\nNext:') + 1
        self.assertEqual(footprints['Parent'].definitions, ((parent_start, parent_end),))
        self.assertEqual(footprints['Parent'].children, ())
        self.assertEqual(footprints['Child'].definitions,
                         ((0, source.index('\n') + 1),))
        parent_block = next(block for block, end in graph.points if end == parent_end)
        values = {item.object: item for item in dict(calculate_graph(graph).details)[parent_block]}
        self.assertEqual(values['Parent'].inclusive_weight, (parent_end - parent_start) / len(source))
        self.assertEqual(values['Parent'].own_weight, values['Parent'].inclusive_weight)
        self.assertEqual(values['Parent'].shared, 0)

    def test_alias_footprint_excludes_earlier_lines_and_following_children(self):
        source = '[A]: value\n=> Read [A] AS [Alias]\n  - Unrelated child\n'
        footprint = next(item for item in self.graph(source).semantic_footprints if item.object == 'Alias')
        start = source.index('=>')
        end = source.index('\n', start) + 1
        self.assertEqual(footprint.definitions, ((start, end),))
        self.assertEqual(footprint.relationships, ('AS source references A',))

    def test_section_alias_excludes_label_from_source_expression(self):
        source = '[A]: value\n[Section]: [A] AS [Alias]\n'
        footprints = {item.object: item for item in self.graph(source).semantic_footprints}
        self.assertEqual(footprints['Alias'].definitions,
                         ((source.index(':', source.index('[Section]')) + 1, len(source)),))
        self.assertEqual(footprints['Alias'].relationships, ('AS source references A',))

    def test_future_and_uncertain_references_do_not_inject_support(self):
        source = '- Use [A]\n[A]: value\n- Use [Missing]\n'
        graph = self.graph(source)
        self.assertEqual(len(graph.semantic_footprints), 1)
        self.assertEqual(graph.semantic_footprints[0].mentions, ())
        self.assertEqual(graph.semantic_transformations, ())
        self.assertTrue(all(value == 0 for _, value in semantic_state(graph, source.index('[A]:'))))

    def test_character_records_are_reproducible_and_detached(self):
        source = '[A]: value\n[B]: value\n=> Read [A] AS [Alias]\n[C]: value\n'
        graph = self.graph(source)
        self.assertEqual(graph, self.graph(source))
        self.assertEqual(calculate_graph(graph), calculate_graph(self.graph(source)))
        self.assertEqual(GraphSnapshot(**json.loads(json.dumps(asdict(graph)))), graph)

    def test_readout_positions_are_whole_block_ends_in_source_characters(self):
        source = '[A]: 😀 café\n- body\n\n[B]: value\n'
        graph = self.graph(source)
        self.assertEqual(graph.document_length, len(source))
        self.assertNotEqual(graph.document_length, len(source.encode('utf-8')))
        self.assertEqual(dict(graph.points)[graph.blocks[-1]], len(source))
        footprints = {item.object: item for item in graph.semantic_footprints}
        self.assertEqual(footprints['A'].available_from, len('[A]'))
        self.assertEqual(footprints['B'].available_from, source.index('[B]') + len('[B]'))

    def test_cancellation_interrupts_footprint_generation(self):
        from AgStudio.shared.graph.adapter import _inclusive_node_ends, _semantic_footprints
        from AgStudio.shared.lint import analyze
        analysis = analyze(''.join(f'[A{i}]: value\n' for i in range(30)))
        declarations = {s.span: s for s in analysis.semantics.symbols if s.kind in ('anchor', 'alias')}
        inclusive_ends = _inclusive_node_ends(analysis.tree)
        polls = 0
        def cancelled():
            nonlocal polls
            polls += 1
            return polls >= 25
        with self.assertRaises(HeatCancelled):
            _semantic_footprints(analysis.tree, analysis.semantics, declarations, inclusive_ends,
                                 cancelled=cancelled)
        self.assertEqual(polls, 25)


class SemanticModeVariantTests(unittest.TestCase):
    def fixture(self, mode, decay=1.7):
        return GraphSnapshot(
            blocks=(1, 2), occurrences=((2, 1),), owners=((1, 1), (2, 2), (3, 2)),
            mode=mode, document_length=100, options=SemanticOptions(decay=decay),
            points=((1, 40), (2, 100)),
            semantic_footprints=(
                SemanticFootprint('Zed', ((0, 40),), ((60, 65), (80, 85)), children=('Able',)),
                SemanticFootprint('Able', ((20, 30),), ((90, 95),)),
            ),
            semantic_views=(SemanticView(1, 40, ('Zed',), 'named_block'),
                            SemanticView(2, 65, ('Zed',), 'reference_use'),
                            SemanticView(3, 95, ('Able',), 'reference_use')),
        )

    def test_st1_and_st2_preserve_final_vectors_and_distinct_transport_contracts(self):
        for decay in (0, 1.7, 1e308):
            first = self.fixture('semantic_triad_1', decay)
            second = self.fixture('semantic_triad_2', decay)
            with self.subTest(decay=decay):
                one, two = calculate_graph(first), calculate_graph(second)
                self.assertEqual(one.final_details, two.final_details)
                self.assertEqual(one.semantic_views, two.semantic_views)
                self.assertEqual(tuple(block for block, _ in one.scores),
                                 tuple(block for block, _ in two.scores))
                for (_, left), (_, right) in zip(one.scores, two.scores):
                    self.assertAlmostEqual(left.total, right.total, places=14)
                self.assertTrue(one.states)
                self.assertTrue(one.details)
                self.assertTrue(one.semantic_views)
                self.assertTrue(one.view_details)
                self.assertEqual(tuple(item.object for item in one.view_details[0][1]), ('Zed', 'Able'))
                self.assertEqual((two.states, two.details, two.view_details), ((), (), ()))
                self.assertEqual(two.position_snapshot, second)

    def test_st1_and_st2_arbitrary_causal_readouts_are_identical(self):
        first = self.fixture('semantic_triad_1')
        second = self.fixture('semantic_triad_2')
        for point in (0, 1, 20, 30, 40, 64, 65, 84, 95, 100):
            with self.subTest(point=point):
                self.assertEqual(semantic_state(first, point), semantic_state(second, point))

    def test_legacy_semantic_aliases_are_exactly_canonical_st2(self):
        current = self.fixture('semantic_triad_2')
        for legacy in ('semantic_triad', 'semantic_triad_3'):
            with self.subTest(legacy=legacy):
                old = self.fixture(legacy)
                self.assertEqual(old, current)
                self.assertEqual(old.mode, 'semantic_triad_2')
                self.assertEqual(calculate_graph(old), calculate_graph(current))
                record = json.loads(json.dumps(asdict(old)))
                self.assertEqual(record['mode'], 'semantic_triad_2')
                record['mode'] = legacy
                self.assertEqual(GraphSnapshot(**record), current)
                self.assertEqual(pickle.loads(pickle.dumps(old)), current)

    def test_switching_semantic_modes_never_changes_input_geometry_or_evidence(self):
        original = self.fixture('semantic_triad_2')
        before = pickle.dumps(original)
        summarized = replace(original, mode='semantic_triad_1')
        self.assertEqual(replace(summarized, mode='semantic_triad_2'), original)
        self.assertEqual(summarized.semantic_footprints, original.semantic_footprints)
        self.assertEqual(summarized.semantic_views, original.semantic_views)
        calculate_graph(summarized)
        self.assertEqual(pickle.dumps(original), before)

    def test_heuristic_numeric_contract_remains_unchanged(self):
        source = GraphSnapshot((0, 1, 2), ((1, 0), (1, 0), (2, 1)), ((0, 0), (1, 1), (2, 2)))
        result = calculate_graph(source)
        self.assertEqual(source.mode, 'heuristic')
        self.assertEqual(dict(result.scores), score_relations(source.blocks, source.occurrences))
        self.assertEqual(result.scores, ((0, HeatScore(2, .5, 2, 1)),
                                         (1, HeatScore(2, 0, 2, 0)),
                                         (2, HeatScore(1, .5, 1, 1))))
        self.assertEqual((result.states, result.details, result.semantic_views, result.view_details),
                         ((), (), (), ()))

    def test_adapter_keeps_shared_geometry_and_aliases_extract_exact_st2_positions(self):
        from AgStudio.shared.graph.adapter import build_graph_snapshot
        from AgStudio.shared.lint import analyze
        source = '[Zed]: value\n[Able]:\n- text\n=> [Zed] AS [Derived]\nTask:\n- [Derived] [Zed]\n'
        analysis = analyze(source)
        graphs = [build_graph_snapshot(analysis.tree, analysis.semantics, mode=mode)
                  for mode in ('semantic_triad_1', 'semantic_triad_2', 'semantic_triad', 'semantic_triad_3')]
        self.assertEqual(tuple(graph.mode for graph in graphs),
                         ('semantic_triad_1', 'semantic_triad_2', 'semantic_triad_2', 'semantic_triad_2'))
        self.assertEqual(replace(graphs[0], mode='semantic_triad_2'),
                         replace(graphs[1], semantic_positions=()))
        self.assertEqual(graphs[0].semantic_positions, ())
        self.assertTrue(graphs[1].semantic_positions)
        self.assertEqual(calculate_graph(graphs[0]).final_details,
                         calculate_graph(graphs[1]).final_details)
        for migrated in graphs[2:]:
            self.assertEqual(graphs[1], migrated)
            self.assertEqual(calculate_graph(graphs[1]), calculate_graph(migrated))


if __name__ == '__main__':
    unittest.main()
