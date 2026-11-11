"""Automatic per-node Semantic Triad views, independent of user selections."""
from dataclasses import asdict, FrozenInstanceError, replace
import json
import pickle
import unittest

from AgStudio.shared.graph import (
    GraphResult, GraphSnapshot, HeatCancelled, SemanticCoverage, SemanticFootprint,
    SemanticOptions, SemanticView, calculate_graph,
)
from AgStudio.shared.graph.semantic import calculate_semantic_views


def snapshot(*, options=None, views=None, footprints=None):
    if footprints is None:
        footprints = (
            SemanticFootprint('Zed', ((0, 20),), ((40, 45), (80, 85))),
            SemanticFootprint('Able', ((10, 30),), ((90, 95),)),
            SemanticFootprint('Middle', ((50, 60),)),
        )
    if views is None:
        views = (SemanticView(7, 45, ('Zed',), 'reference_use'),
                 SemanticView(9, 100, ('Able',), 'named_block'))
    return GraphSnapshot((1,), (), ((7, 1), (9, 1)), mode='semantic_triad_1',
                         options=options or SemanticOptions(decay=0), points=((1, 100),),
                         document_length=100, semantic_footprints=footprints, semantic_views=views)


def by_object(values):
    return {item.object: item for item in values}


class AutomaticViewTransportTests(unittest.TestCase):
    def test_view_detaches_caller_objects_and_preserves_first_occurrence_order(self):
        objects = ['Zed', 'Able', 'Zed']
        view = SemanticView(7, 45, objects, 'reference_use')
        objects.clear()
        self.assertEqual(view.objects, ('Zed', 'Able'))
        self.assertIsInstance(hash(view), int)
        with self.assertRaises(FrozenInstanceError):
            view.position = 50

    def test_snapshot_detaches_view_lists_and_mapping_contents(self):
        names = ['Zed']
        views = [{'node': 7, 'position': 45, 'objects': names, 'kind': 'reference_use'}]
        source = snapshot(views=views)
        names.append('Able')
        views[0]['position'] = 100
        views.clear()
        self.assertEqual(source.semantic_views, (SemanticView(7, 45, ('Zed',), 'reference_use'),))

    def test_snapshot_view_pickle_and_json_asdict_roundtrips(self):
        source = snapshot()
        self.assertEqual(pickle.loads(pickle.dumps(source)), source)
        restored = GraphSnapshot(**json.loads(json.dumps(asdict(source), allow_nan=False)))
        self.assertEqual(restored, source)
        self.assertEqual(hash(restored), hash(source))
        self.assertEqual(calculate_graph(restored), calculate_graph(source))

    def test_result_retains_views_and_detached_serializable_details(self):
        source = snapshot()
        result = calculate_graph(source)
        self.assertEqual(result.semantic_views, source.semantic_views)
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)
        self.assertIsInstance(hash(result), int)
        record = json.loads(json.dumps(asdict(result), allow_nan=False))
        self.assertEqual(record['semantic_views'][0]['objects'], ['Zed'])
        self.assertEqual(record['view_details'][0][0], 7)
        self.assertEqual([item['object'] for item in record['view_details'][0][1]],
                         ['Zed', 'Able', 'Middle'])

    def test_result_constructor_detaches_caller_view_records(self):
        primary = ['Zed']
        views = [{'node': 7, 'position': 45, 'objects': primary, 'kind': 'reference_use'}]
        values = [{'object': 'Zed', 'linked': .2, 'relationships': ['Uses Able']}]
        rows = [[7, values]]
        result = GraphResult((), (), (), semantic_views=views, view_details=rows)
        primary.append('Able')
        values[0]['linked'] = .9
        values[0]['relationships'].clear()
        rows[0][0] = 99
        self.assertEqual(result.semantic_views[0].objects, ('Zed',))
        self.assertEqual(result.view_details[0][0], 7)
        self.assertEqual(result.view_details[0][1][0].linked, .2)
        self.assertEqual(result.view_details[0][1][0].relationships, ('Uses Able',))

    def test_unknown_primary_identity_is_rejected_by_snapshot(self):
        with self.assertRaisesRegex(ValueError, 'unknown object'):
            snapshot(views=(SemanticView(7, 45, ('Missing',)),))

    def test_invalid_view_ids_positions_kinds_and_duplicate_nodes_are_rejected(self):
        invalid = ({'node': True, 'position': 0}, {'node': '7', 'position': 0},
                   {'node': 7, 'position': -1}, {'node': 7, 'position': True},
                   {'node': 7, 'position': 1.5}, {'node': 7, 'position': 0, 'kind': 'ranked'},
                   {'node': 7, 'position': 0, 'objects': 'Zed'})
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                SemanticView(**kwargs)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            snapshot(views=(SemanticView(7, 101),))
        with self.assertRaisesRegex(ValueError, 'unique node'):
            snapshot(views=(SemanticView(7, 45), SemanticView(7, 50)))

    def test_duplicate_result_views_details_and_objects_are_rejected(self):
        invalid = (
            {'semantic_views': (SemanticView(7, 45), SemanticView(7, 50))},
            {'view_details': ((7, ()), (7, ()))},
            {'view_details': ((True, ()),)},
            {'view_details': ((7, (SemanticCoverage('Zed'), SemanticCoverage('Zed'))),)},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                GraphResult((), (), (), **kwargs)


class AutomaticViewCalculationTests(unittest.TestCase):
    def test_single_primary_identity_never_discards_other_object_states(self):
        result = calculate_graph(snapshot())
        first = dict(result.view_details)[7]
        self.assertEqual(result.semantic_views[0].objects, ('Zed',))
        self.assertEqual(tuple(item.object for item in first), ('Zed', 'Able', 'Middle'))
        values = by_object(first)
        self.assertEqual(values['Able'].linked, .25)
        self.assertEqual(values['Middle'].linked, .1)

    def test_all_object_union_is_denominator_even_for_single_primary(self):
        values = by_object(dict(calculate_graph(snapshot()).view_details)[7])
        self.assertEqual(values['Zed'].linked, .3)
        self.assertEqual(values['Able'].linked, .25)
        for item in values.values():
            self.assertEqual(item.comparison, .55)
            self.assertEqual(item.adjusted_comparison, .55)
        self.assertNotEqual(sum(item.linked for item in values.values()), .55)

    def test_primary_identity_and_kind_change_only_display_association(self):
        first = snapshot(views=(SemanticView(7, 45, ('Zed',), 'reference_use'),))
        second = snapshot(views=(SemanticView(7, 45, ('Able',), 'named_block'),))
        third = snapshot(views=(SemanticView(7, 45, ('Zed', 'Able', 'Middle'), 'all_objects'),))
        self.assertEqual(calculate_semantic_views(first), calculate_semantic_views(second))
        self.assertEqual(calculate_semantic_views(first), calculate_semantic_views(third))

    def test_internal_selection_and_comparison_cannot_bias_automatic_views(self):
        baseline = snapshot()
        biased = snapshot(options=SemanticOptions(decay=0, selected_object='Able',
                                                  comparison_objects=('Able',)))
        self.assertEqual(calculate_graph(baseline).view_details, calculate_graph(biased).view_details)
        # Legacy block helper remains independently compatible, not a display filter.
        self.assertNotEqual(calculate_graph(baseline).details, calculate_graph(biased).details)

    def test_automatic_view_helper_ignores_even_stale_internal_selector_names(self):
        baseline = snapshot()
        stale = snapshot(options=SemanticOptions(decay=0, selected_object='gone',
                                                 comparison_objects=('also_gone',)))
        self.assertEqual(calculate_semantic_views(stale), calculate_semantic_views(baseline))

    def test_reference_view_uses_final_mentions_despite_earlier_source_location(self):
        result = calculate_graph(snapshot())
        view = by_object(dict(result.view_details)[7])
        block = by_object(dict(result.details)[1])
        self.assertEqual(view['Zed'].mention, .1)
        self.assertEqual(block['Zed'].mention, .1)
        self.assertEqual(view['Able'].mention, .05)
        self.assertEqual(block['Able'].mention, .05)

    def test_automatic_vectors_preserve_footprint_declaration_order(self):
        result = calculate_graph(snapshot())
        for _, values in result.view_details:
            self.assertEqual(tuple(item.object for item in values), ('Zed', 'Able', 'Middle'))
        # The greatest support is not necessarily first, nor is alphabetical order used.
        self.assertNotEqual(tuple(item.object for item in result.view_details[0][1]),
                            tuple(sorted(item.object for item in result.view_details[0][1])))

    def test_later_available_identity_has_final_support_in_earlier_map_view(self):
        footprints = (SemanticFootprint('future', ((0, 100),), available_from=60),)
        source = snapshot(footprints=footprints, views=(SemanticView(7, 45, ('future',)),))
        values = dict(calculate_semantic_views(source))[7]
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].object, 'future')
        self.assertEqual(values[0].linked, 1)
        self.assertEqual(values[0].comparison, 1)

    def test_empty_source_and_empty_object_vectors_are_supported(self):
        source = GraphSnapshot((), (), (), mode='semantic_triad_1',
                               semantic_views=(SemanticView(0, 0),))
        result = calculate_graph(source)
        self.assertEqual(result.view_details, ((0, ()),))
        self.assertEqual(calculate_semantic_views(replace(source, semantic_views=())), ())

    def test_cancellation_interrupts_automatic_view_calculation(self):
        source = snapshot()
        with self.assertRaises(HeatCancelled):
            calculate_semantic_views(source, cancelled=lambda: True)
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 12
        with self.assertRaises(HeatCancelled):
            calculate_semantic_views(source, cancelled=cancelled)
        self.assertEqual(calls, 12)


class AutomaticViewAdapterTests(unittest.TestCase):
    def graph(self, source, options=None):
        from AgStudio.shared.graph.adapter import build_graph_snapshot
        from AgStudio.shared.lint import analyze
        analysis = analyze(source)
        return analysis, build_graph_snapshot(analysis.tree, analysis.semantics,
                                               mode='semantic_triad_1',
                                               options={'decay': 0} if options is None else options)

    def test_every_syntax_node_gets_exactly_one_known_identity_view(self):
        source = '[Zed]: value\n\n[Able]: value\nTask:\n- Use [Zed]\n- [Missing]\n'
        analysis, graph = self.graph(source)
        names = {item.object for item in graph.semantic_elements}
        self.assertEqual(tuple(view.node for view in graph.semantic_views),
                         tuple(node.id for node in analysis.tree.nodes))
        for view in graph.semantic_views:
            self.assertLessEqual(view.position, len(source))
            self.assertTrue(set(view.objects) <= names)

    def test_declaration_source_order_is_not_alphabetical_or_reference_order(self):
        source = '[Zed]: value\n[Able]: value\n[Middle]: value\nTask:\n- [Middle] [Able] [Zed]\n'
        _, graph = self.graph(source)
        order = ('Zed', 'Able', 'Middle')
        self.assertEqual(tuple(item.object for item in graph.semantic_footprints), order)
        reference = next(view for view in graph.semantic_views if view.kind == 'reference_use')
        self.assertEqual(reference.objects, order + ('@element:3',))
        for _, values in calculate_graph(graph).view_details:
            self.assertEqual(tuple(item.object for item in values), order + ('@element:3',))

    def test_reference_view_retains_token_end_with_final_document_values(self):
        source = '[Zed]: value\n[Able]: value\nTask:\n- Use [Zed]\n- Later [Zed] [Able]\n'
        _, graph = self.graph(source)
        refs = [view for view in graph.semantic_views if view.kind == 'reference_use']
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].position, source.index('[Zed]', source.index('- Use')) + len('[Zed]'))
        self.assertEqual(refs[1].position, source.rindex('[Able]') + len('[Able]'))
        self.assertEqual(refs[0].objects, ('Zed', '@element:2'))
        result = calculate_graph(graph)
        early = by_object(dict(result.view_details)[refs[0].node])
        late = by_object(dict(result.view_details)[refs[1].node])
        self.assertEqual(early['Zed'].mention, 2 * len('[Zed]') / len(source))
        self.assertEqual(late['Zed'].mention, 2 * len('[Zed]') / len(source))
        self.assertEqual(early['Able'].mention, len('[Able]') / len(source))
        self.assertEqual(late['Able'].mention, len('[Able]') / len(source))

    def test_named_context_uses_own_inclusive_body_and_alias_reads_target_end(self):
        source = '[Zed]:\n- text\n=> Use [Zed] AS [Derived]\n'
        _, graph = self.graph(source)
        named = next(view for view in graph.semantic_views if view.kind == 'named_block')
        context = next(view for view in graph.semantic_views if view.kind == 'named_context')
        alias = next(view for view in graph.semantic_views if view.kind == 'alias_use')
        self.assertEqual(named.objects, ('Zed',))
        self.assertEqual(context.objects, ('Zed',))
        self.assertEqual(named.position, len(source))
        self.assertEqual(context.position, len(source))
        self.assertEqual(alias.objects, ('Zed', 'Derived'))
        self.assertEqual(alias.position, source.index('[Derived]') + len('[Derived]'))
        values = dict(calculate_graph(graph).view_details)
        self.assertEqual(tuple(item.object for item in values[named.node]), ('Zed', 'Derived'))

    def test_plain_text_uses_enclosing_structural_identity_at_own_physical_end(self):
        source = '[Zed]: value\n[Able]: value\nTask:\n- plain text\n'
        analysis, graph = self.graph(source)
        nodes = {node.id: node for node in analysis.tree.nodes}
        unowned = [view for view in graph.semantic_views if view.kind == 'all_objects']
        self.assertTrue(unowned)
        for view in unowned:
            self.assertEqual(view.objects, ('@element:2',))
            self.assertEqual(view.position, nodes[view.node].span.end)

    def test_disabling_parser_support_creates_no_unknown_object_associations(self):
        source = '[Zed]: value\nTask:\n- [Zed] AS [Derived]\n'
        analysis, graph = self.graph(source, options={'parser_support': False})
        self.assertEqual(len(graph.semantic_views), len(analysis.tree.nodes))
        self.assertTrue(all(view.objects == () for view in graph.semantic_views))
        self.assertTrue(all(values == () for _, values in calculate_graph(graph).view_details))


if __name__ == '__main__':
    unittest.main()
