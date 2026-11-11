"""Independent acceptance tests for Semantic Triad's character geometry.

Run without third-party test dependencies:
    python -m unittest AgStudio.shared.software_testing.test_triad_coverage -v
"""
from dataclasses import asdict, FrozenInstanceError
import json
import math
import pickle
import random
import unittest

from AgStudio.shared.graph import (
    GraphResult, GraphSnapshot, HeatCancelled, SemanticCoverage,
    SemanticFootprint, SemanticOptions, SemanticRepresentation,
    SemanticTransformation, calculate_graph, semantic_state,
)
from AgStudio.shared.graph.semantic import subtract_spans, union_spans


def snapshot(footprints=(), *, length=1000, point=None, options=None, **kwargs):
    """One readout unless an individual test supplies an explicit point set."""
    if point is None:
        point = length
    return GraphSnapshot(
        blocks=(1,), occurrences=(), owners=((1, 1),),
        mode='semantic_triad_1', options=options or SemanticOptions(decay=0),
        points=((1, point),), document_length=length,
        semantic_footprints=tuple(footprints), **kwargs,
    )


def details(input_snapshot):
    return {item.object: item for item in calculate_graph(input_snapshot).details[0][1]}


def supporting_characters(spans, point):
    return {character for start, end in spans
            for character in range(start, min(end, point))}


def discrete_oracle(spans, point, length, decay):
    if not length:
        return 0.0
    return math.fsum(math.exp(-decay * ((point - character - 1) / length)) / length
                     for character in supporting_characters(spans, point))


class IntrinsicGeometryTests(unittest.TestCase):
    def test_nested_parent_inclusive_own_and_comparison_union(self):
        values = details(snapshot((
            SemanticFootprint('parent', ((100, 400),), children=('child',)),
            SemanticFootprint('child', ((200, 300),)),
        )))
        self.assertEqual(values['parent'].inclusive_weight, .30)
        self.assertEqual(values['parent'].own_weight, .20)
        self.assertEqual(values['child'].inclusive_weight, .10)
        self.assertEqual(values['child'].own_weight, .10)
        self.assertEqual(values['parent'].comparison, .30)
        self.assertEqual(values['child'].comparison, .30)
        self.assertEqual(values['parent'].shared, .10)
        self.assertEqual(values['parent'].other_only, 0)
        self.assertEqual(values['child'].shared, .10)
        self.assertEqual(values['child'].other_only, .20)

    def test_external_reference_adds_linked_not_intrinsic_support(self):
        value = details(snapshot((SemanticFootprint(
            'parent', ((100, 400),), ((900, 910),)),)))['parent']
        self.assertEqual(value.inclusive_weight, .30)
        self.assertEqual(value.own_weight, .30)
        self.assertEqual(value.definition, .30)
        self.assertEqual(value.mention, .01)
        self.assertEqual(value.linked, .31)

    def test_overlapping_and_repeated_spans_count_once_per_identity(self):
        value = details(snapshot((SemanticFootprint(
            'one', ((0, 100), (50, 150), (0, 100)),
            ((100, 200), (100, 200), (150, 200))),)))['one']
        self.assertEqual(value.definition, .15)
        self.assertEqual(value.mention, .10)
        self.assertEqual(value.linked, .20)
        self.assertEqual(value.adjusted_linked, .20)

    def test_overlap_is_preserved_for_different_identities(self):
        values = details(snapshot((
            SemanticFootprint('left', ((0, 200),)),
            SemanticFootprint('right', ((100, 300),)),
        )))
        self.assertEqual(values['left'].linked, .20)
        self.assertEqual(values['right'].linked, .20)
        self.assertEqual(values['left'].shared, .10)
        self.assertEqual(values['right'].shared, .10)
        self.assertEqual(values['left'].comparison, .30)
        self.assertEqual(values['left'].other_only, .10)

    def test_distinct_repeated_mentions_accumulate_character_support(self):
        value = details(snapshot((SemanticFootprint(
            'one', ((0, 100),), ((400, 410), (500, 510), (600, 610))),)))['one']
        self.assertEqual(value.mention, .03)
        self.assertEqual(value.linked, .13)
        self.assertEqual(value.inclusive_weight, .10)

    def test_mentions_inside_definition_do_not_add_linked_weight(self):
        value = details(snapshot((SemanticFootprint(
            'one', ((0, 300),), ((10, 20), (290, 300))),)))['one']
        self.assertEqual(value.definition, .30)
        self.assertEqual(value.mention, .02)
        self.assertEqual(value.linked, .30)

    def test_overlapping_children_are_subtracted_as_union(self):
        values = details(snapshot((
            SemanticFootprint('parent', ((100, 400),), children=('a', 'b')),
            SemanticFootprint('a', ((150, 250),)),
            SemanticFootprint('b', ((200, 300),)),
        )))
        self.assertEqual(values['parent'].own_weight, .15)
        self.assertEqual(values['parent'].inclusive_weight, .30)

    def test_child_outside_parent_does_not_subtract_unrelated_characters(self):
        values = details(snapshot((
            SemanticFootprint('parent', ((100, 400),), children=('child',)),
            SemanticFootprint('child', ((300, 500),)),
        )))
        self.assertEqual(values['parent'].own_weight, .20)
        self.assertEqual(values['parent'].inclusive_weight, .30)

    def test_uncovered_suffix_changes_document_normalization(self):
        footprint = SemanticFootprint('one', ((0, 100),))
        short = details(snapshot((footprint,), length=1000, point=100))['one']
        long = details(snapshot((footprint,), length=2000, point=100))['one']
        self.assertEqual(short.inclusive_weight, .10)
        self.assertEqual(long.inclusive_weight, .05)
        self.assertEqual(short.linked, .10)
        self.assertEqual(long.linked, .05)


class CausalReadoutTests(unittest.TestCase):
    def test_no_future_support_at_point_of_use(self):
        values = details(snapshot((SemanticFootprint(
            'one', ((10, 30), (70, 90)), ((40, 60), (100, 110))),),
            length=200, point=50))['one']
        self.assertEqual(values.definition, 20 / 200)
        self.assertEqual(values.mention, 10 / 200)
        self.assertEqual(values.linked, 30 / 200)

    def test_half_open_characters_appear_only_after_right_boundary(self):
        footprint = SemanticFootprint('one', ((10, 11),))
        before = semantic_state(snapshot((footprint,), length=20), 10)
        after = semantic_state(snapshot((footprint,), length=20), 11)
        self.assertEqual(before, (('one', 0),))
        self.assertEqual(after, (('one', 1 / 20),))

    def test_available_from_prevents_future_identity_activation(self):
        footprint = SemanticFootprint('alias', ((0, 50),), ((60, 70),), available_from=40)
        before = details(snapshot((footprint,), length=100, point=39))['alias']
        at = details(snapshot((footprint,), length=100, point=40))['alias']
        self.assertEqual(before.definition, 0)
        self.assertEqual(before.mention, 0)
        self.assertEqual(before.linked, 0)
        self.assertEqual(at.definition, .4)
        self.assertEqual(at.mention, 0)

    def test_future_spans_cannot_change_earlier_linked_readout(self):
        original = SemanticFootprint('one', ((0, 10),), ((20, 30),))
        extended = SemanticFootprint('one', ((0, 10), (80, 100)), ((20, 30), (70, 80)))
        settings = SemanticOptions(decay=1.7)
        first = semantic_state(snapshot((original,), length=100, options=settings), 40)
        second = semantic_state(snapshot((extended,), length=100, options=settings), 40)
        self.assertEqual(first, second)

    def test_multiple_readouts_are_independent_and_sorted_by_block(self):
        source = GraphSnapshot(
            (7, 2, 4), (), (), mode='semantic_triad_1',
            options=SemanticOptions(decay=0), points=((7, 70), (2, 20), (4, 40)),
            document_length=100, semantic_footprints=(SemanticFootprint('one', ((0, 100),)),),
        )
        result = calculate_graph(source)
        self.assertEqual(result.states, ((2, (('one', .2),)), (4, (('one', .4),)), (7, (('one', .7),))))
        self.assertEqual(tuple(block for block, _ in result.scores), (2, 4, 7))


class LocalityKernelTests(unittest.TestCase):
    def test_exponential_kernel_matches_exact_discrete_character_oracle(self):
        definitions = ((0, 7), (3, 12), (30, 45), (96, 100))
        mentions = ((10, 20), (40, 45), (60, 67), (96, 100))
        footprint = SemanticFootprint('one', definitions, mentions)
        for decay in (0, 1e-14, .125, 1, 7.25, 1000, 1e308):
            for point in (0, 1, 6, 12, 44, 66, 100):
                with self.subTest(decay=decay, point=point):
                    value = details(snapshot((footprint,), length=100, point=point,
                                             options=SemanticOptions(decay=decay)))['one']
                    for actual, spans in (
                        (value.adjusted_definition, definitions),
                        (value.adjusted_mention, mentions),
                        (value.adjusted_linked, definitions + mentions),
                        (value.adjusted_comparison, definitions + mentions),
                    ):
                        expected = discrete_oracle(spans, point, 100, decay)
                        self.assertTrue(math.isfinite(actual))
                        self.assertTrue(math.isclose(actual, expected, rel_tol=2e-12, abs_tol=1e-15),
                                        (actual, expected, decay, point))

    def test_subnormal_decay_has_stable_zero_decay_limit(self):
        value = details(snapshot((SemanticFootprint('one', ((0, 100),)),),
                                 options=SemanticOptions(decay=5e-324)))['one']
        self.assertEqual(value.adjusted_linked, .10)

    def test_readout_distance_uses_normalized_document_length(self):
        footprint = SemanticFootprint('one', ((0, 10),))
        settings = SemanticOptions(decay=2)
        a = details(snapshot((footprint,), length=100, point=50, options=settings))['one']
        b = details(snapshot((footprint,), length=200, point=50, options=settings))['one']
        self.assertAlmostEqual(a.adjusted_linked, discrete_oracle(((0, 10),), 50, 100, 2))
        self.assertAlmostEqual(b.adjusted_linked, discrete_oracle(((0, 10),), 50, 200, 2))
        self.assertNotAlmostEqual(a.adjusted_linked / 2, b.adjusted_linked)

    def test_decay_changes_adjusted_values_only(self):
        footprint = SemanticFootprint('one', ((0, 100),), ((300, 310),))
        flat = details(snapshot((footprint,)))['one']
        local = details(snapshot((footprint,), options=SemanticOptions(decay=2)))['one']
        for attribute in ('inclusive_weight', 'own_weight', 'definition', 'mention',
                          'linked', 'comparison', 'shared', 'other_only'):
            self.assertEqual(getattr(flat, attribute), getattr(local, attribute))
        self.assertLess(local.adjusted_linked, flat.adjusted_linked)


class SelectionAndComparisonTests(unittest.TestCase):
    def setUp(self):
        self.footprints = (
            SemanticFootprint('parent', ((0, 300),), children=('child',)),
            SemanticFootprint('child', ((100, 200),)),
            SemanticFootprint('outside', ((600, 700),)),
        )

    def test_score_is_selected_identity_never_sum_of_all_identities(self):
        result = calculate_graph(snapshot(self.footprints, options=SemanticOptions(
            decay=0, selected_object='parent')))
        score = result.scores[0][1]
        self.assertEqual(score.total, .30)
        self.assertEqual(score.indirect, 0)
        self.assertEqual(sum(dict(result.states[0][1]).values()), .50)
        child = calculate_graph(snapshot(self.footprints, options=SemanticOptions(
            decay=0, selected_object='child')))
        self.assertEqual(child.scores[0][1].total, .10)

    def test_selected_comparison_union_excludes_unselected_objects(self):
        values = details(snapshot(self.footprints, options=SemanticOptions(
            decay=0, selected_object='parent', comparison_objects=('parent', 'child'))))
        self.assertEqual(values['parent'].comparison, .30)
        self.assertEqual(values['parent'].shared, .10)
        self.assertEqual(values['parent'].other_only, 0)
        self.assertEqual(values['child'].other_only, .20)

    def test_invalid_selected_or_comparison_identity_is_rejected(self):
        for options in (SemanticOptions(selected_object='missing'),
                        SemanticOptions(comparison_objects=('missing',))):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'unknown'):
                calculate_graph(snapshot(self.footprints, options=options))

    def test_three_way_overlap_and_narrower_scope_match_set_oracle(self):
        footprints = (
            SemanticFootprint('a', ((0, 60),), ((80, 95),)),
            SemanticFootprint('b', ((20, 70),), ((90, 100),)),
            SemanticFootprint('c', ((40, 90),), ((10, 25),)),
            SemanticFootprint('outside', ((5, 50),), ((65, 85),)),
        )
        for scope in (('a', 'b', 'c', 'outside'), ('a', 'b', 'c'), ('b',), ('a', 'c')):
            for point in (0, 17, 45, 80, 100):
                settings = SemanticOptions(decay=1.7, comparison_objects=scope)
                values = details(snapshot(footprints, length=100, point=point, options=settings))
                character_sets = {item.object: supporting_characters(
                    item.definitions + item.mentions, point) for item in footprints}
                comparison = set().union(*(character_sets[name] for name in scope))
                for name, value in values.items():
                    with self.subTest(scope=scope, point=point, object=name):
                        others = set().union(*(character_sets[other] for other in scope if other != name))
                        self.assertEqual(value.comparison, len(comparison) / 100)
                        self.assertEqual(value.shared, len(character_sets[name] & others) / 100)
                        self.assertEqual(value.other_only, len(others - character_sets[name]) / 100)
                        expected = math.fsum(math.exp(-1.7 * (point - x - 1) / 100) / 100
                                             for x in comparison)
                        self.assertAlmostEqual(value.adjusted_comparison, expected, places=14)

    def test_cached_equal_readouts_keep_identical_details_and_independent_block_ids(self):
        source = GraphSnapshot((1, 2, 3), (), (), mode='semantic_triad_1',
                               options=SemanticOptions(decay=0), points=((1, 1000), (2, 1000), (3, 1000)),
                               document_length=1000, semantic_footprints=self.footprints)
        result = calculate_graph(source)
        self.assertEqual(tuple(block for block, _ in result.details), (1, 2, 3))
        self.assertEqual(result.details[0][1], result.details[1][1])
        self.assertEqual(result.details[1][1], result.details[2][1])


class EmptyCancellationAndValidationTests(unittest.TestCase):
    def test_empty_zero_length_document_returns_finite_zero(self):
        source = snapshot(length=0)
        result = calculate_graph(source)
        self.assertEqual(result.scores[0][1].total, 0)
        self.assertEqual(result.states, ((1, ()),))
        self.assertEqual(result.details, ((1, ()),))
        self.assertEqual(semantic_state(source, 0), ())

    def test_zero_length_spans_have_no_weight(self):
        value = details(snapshot((SemanticFootprint('one', ((0, 0),), ((0, 0),)),), length=0))['one']
        for name, number in asdict(value).items():
            if name not in ('object', 'relationships'):
                self.assertEqual(number, 0, name)

    def test_graph_with_no_readouts_returns_empty_result(self):
        source = GraphSnapshot((), (), (), mode='semantic_triad_1', document_length=0)
        result = calculate_graph(source)
        self.assertEqual((result.scores, result.states, result.details), ((), (), ()))

    def test_cancellation_at_start_and_mid_calculation_never_returns_partial_result(self):
        source = snapshot(tuple(SemanticFootprint(str(index), ((index, index + 1),))
                                for index in range(30)))
        with self.assertRaises(HeatCancelled):
            calculate_graph(source, cancelled=lambda: True)
        calls = 0

        def cancel_after_some_work():
            nonlocal calls
            calls += 1
            return calls >= 12

        with self.assertRaises(HeatCancelled):
            calculate_graph(source, cancelled=cancel_after_some_work)
        self.assertGreaterEqual(calls, 12)
        with self.assertRaises(HeatCancelled):
            semantic_state(source, 10, cancelled=lambda: True)

    def test_legacy_option_point_events_are_explicitly_rejected(self):
        for options in (
            SemanticOptions(representations=(SemanticRepresentation('one', 10),)),
            SemanticOptions(transformations=(SemanticTransformation('suppress', 'one', 10, .5),)),
        ):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'footprint|coverage'):
                calculate_graph(snapshot(options=options))

    def test_legacy_snapshot_point_events_are_explicitly_rejected(self):
        for extra in (
            {'semantic_evidence': (SemanticRepresentation('one', 10),)},
            {'semantic_transformations': (SemanticTransformation('suppress', 'one', 10, .5),)},
        ):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'footprint|coverage'):
                calculate_graph(snapshot(**extra))

    def test_malformed_spans_and_out_of_bounds_geometry_are_rejected(self):
        for spans in (((-1, 0),), ((2, 1),), ((False, 1),), ((0, 1.5),)):
            with self.subTest(spans=spans), self.assertRaises((TypeError, ValueError)):
                SemanticFootprint('one', spans)
        for footprint in (SemanticFootprint('one', ((0, 1001),)),
                          SemanticFootprint('one', available_from=1001)):
            with self.subTest(footprint=footprint), self.assertRaises(ValueError):
                snapshot((footprint,))
        with self.assertRaises(ValueError):
            snapshot((SemanticFootprint('same'), SemanticFootprint('same')))

    def test_readout_position_validation(self):
        source = snapshot()
        for point in (-1, 1001, True, 1.5):
            with self.subTest(point=point), self.assertRaises(ValueError):
                semantic_state(source, point)
        with self.assertRaises(ValueError):
            semantic_state(GraphSnapshot((), (), ()), 0)


class DetachedTransportAndSpanTests(unittest.TestCase):
    def test_snapshot_detaches_nested_caller_containers(self):
        definition = [[0, 100]]
        mention = [[200, 210]]
        children = ['child']
        relationships = ['parent contains child']
        footprint = SemanticFootprint('parent', definition, mention, children, relationships)
        footprints = [footprint]
        source = snapshot(footprints)
        definition[0][1] = 900
        mention.append([400, 900])
        children.append('other')
        relationships.append('mutated')
        footprints.clear()
        self.assertEqual(source.semantic_footprints[0].definitions, ((0, 100),))
        self.assertEqual(source.semantic_footprints[0].mentions, ((200, 210),))
        self.assertEqual(source.semantic_footprints[0].children, ('child',))
        self.assertEqual(source.semantic_footprints[0].relationships, ('parent contains child',))
        with self.assertRaises(FrozenInstanceError):
            source.semantic_footprints[0].object = 'changed'

    def test_snapshot_and_results_are_pickle_and_json_asdict_transportable(self):
        source = snapshot((SemanticFootprint('one', ((0, 100),), ((200, 210),),
                                             relationships=('declares one',)),))
        restored = pickle.loads(pickle.dumps(source))
        self.assertEqual(restored, source)
        self.assertEqual(calculate_graph(restored), calculate_graph(source))
        mapping = json.loads(json.dumps(asdict(source), allow_nan=False))
        self.assertEqual(GraphSnapshot(**mapping), source)
        result = calculate_graph(source)
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)
        output = json.loads(json.dumps(asdict(result), allow_nan=False))
        self.assertEqual(output['details'][0][1][0]['object'], 'one')
        self.assertEqual(output['details'][0][1][0]['relationships'], ['declares one'])

    def test_coverage_relationships_detach_caller_mutation(self):
        relationships = ['one contains child']
        value = SemanticCoverage('one', relationships=relationships)
        result = GraphResult((), (), (), details=((1, (value,)),))
        relationships.append('later mutation')
        self.assertEqual(result.details[0][1][0].relationships, ('one contains child',))

    def test_union_and_subtraction_match_independent_set_oracle(self):
        rng = random.Random(87211)
        for _ in range(250):
            spans, removed = [], []
            for output in (spans, removed):
                for _ in range(rng.randrange(0, 15)):
                    start, end = sorted((rng.randrange(0, 100), rng.randrange(0, 100)))
                    output.append((start, end))
            expected = supporting_characters(spans, 100)
            removed_characters = supporting_characters(removed, 100)
            self.assertEqual(supporting_characters(union_spans(spans), 100), expected)
            difference = subtract_spans(spans, removed)
            self.assertEqual(supporting_characters(difference, 100), expected - removed_characters)
            self.assertEqual(difference, union_spans(difference))


if __name__ == '__main__':
    unittest.main()
