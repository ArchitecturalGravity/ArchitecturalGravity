"""Canonical parser-to-footprint tests; no Qt or manual calibration required."""
import unittest
from dataclasses import asdict, replace
import json
import pickle

from AgStudio.shared.graph.adapter import build_graph_snapshot
from AgStudio.shared.graph.core import GraphSnapshot, HeatCancelled, calculate_graph
from AgStudio.shared.lint import analyze


def snapshot(source, **kwargs):
    # ST1 retains eager automatic vectors; detailed ST2 uses source positions.
    analysis = analyze(source)
    return build_graph_snapshot(analysis.tree, analysis.semantics,
                                mode='semantic_triad_1', **kwargs)


def objects(result):
    return {item.object: item for item in result.semantic_footprints}


class TriadAdapterTests(unittest.TestCase):
    def test_whole_document_length_is_exact_source_character_length(self):
        sources = (
            '', '\ufeff', '\ufeff[A]: x\r\n\r\n', '[A]: x\n\n',
            '[A]:\n"""\nabc\n', '[A]: a\v\f\x1c\x1d\x1e\x85\u2028\u2029',
            '[A]: a\n\tbad\n', '[A]: \U0001f600e\u0301\n',
        )
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(snapshot(source).document_length, len(source))

    def test_inclusive_body_covers_same_indent_members_and_blank_gaps(self):
        source = '[A]:\n- first\n\nTail\nNext: separate\n'
        a = objects(snapshot(source))['A']
        self.assertEqual(a.definitions, ((0, source.index('Next:')),))
        self.assertEqual(a.mentions, ())

    def test_nested_duplicate_body_does_not_extend_existing_object_footprint(self):
        source = '[B]: b\n[A]:\n  [B]:\n  - child\n  - same\nTail: z\n'
        values = objects(snapshot(source))
        end = source.index('Tail:')
        self.assertEqual(values['A'].definitions, ((source.index('[A]'), end),))
        self.assertEqual(values['B'].definitions, ((0, source.index('[A]')),))
        self.assertEqual(values['A'].children, ())
        self.assertNotIn('Contains B', values['A'].relationships)
        self.assertNotIn('Resolved use of B', values['A'].relationships)
        self.assertEqual(values['B'].mentions, ())

    def test_duplicate_nested_header_does_not_create_a_semantic_sampling_point(self):
        source = '[B]: seed\n[A]:\n  [B]:\n  - child\n[C]: sibling\n'
        analysis = analyze(source)
        result = snapshot(source)
        points = dict(result.points)
        nodes = analysis.tree.nodes
        self.assertEqual(points[1], source.index('[C]'))
        self.assertNotIn(2, points)
        self.assertEqual(points[0], nodes[0].span.end)
        self.assertEqual(points[4], len(source))
        # Geometry changes only semantic sampling, not the heuristic contract.
        heuristic = build_graph_snapshot(analysis.tree, analysis.semantics,
                                         options={'decay': 1})
        self.assertEqual(dict(heuristic.points)[1], source.index('[C]'))

    def test_generic_sections_include_their_children_without_absorbing_siblings(self):
        source = 'Task:\n  Child:\n  - local\nNext:\n- other\n'
        result = snapshot(source)
        self.assertEqual(dict(result.points)[0], source.index('Next:'))
        self.assertEqual(dict(result.points)[3], len(source))

    def test_duplicate_body_is_neither_definition_nor_resolved_mention(self):
        source = '[A]: one\nTask: separate\n[A]: two\n  - child\n'
        values = objects(snapshot(source))
        self.assertEqual(tuple(values), ('A',))
        start = source.rindex('[A]')
        self.assertEqual(values['A'].definitions, ((0, source.index('Task:')),))
        self.assertEqual(values['A'].mentions, ())
        self.assertEqual(values['A'].available_from, 3)

    def test_alias_has_local_expression_geometry_and_exact_source_relationship(self):
        source = '[A]: seed\n[B]:\n  => [A] [A] AS [C]\n  - after\nTail: end\n'
        values = objects(snapshot(source))
        start = source.index('  =>')
        end = source.index('  - after')
        self.assertEqual(values['C'].definitions, ((start, end),))
        self.assertEqual(values['C'].relationships, ('AS source references A',))
        self.assertEqual(values['B'].children, ('C',))
        self.assertIn('Contains C', values['B'].relationships)
        self.assertEqual(values['B'].definitions,
                         ((source.index('[B]'), source.index('Tail:')),))
        self.assertEqual(values['C'].available_from, source.index('[C]') + 3)

    def test_alias_source_excludes_section_label(self):
        source = '[A]: seed\nJob: [A] AS [B]\n'
        values = objects(snapshot(source))
        self.assertEqual(values['B'].definitions, ((source.index('Job:') + 4, len(source)),))
        self.assertEqual(values['B'].relationships, ('AS source references A',))

    def test_same_line_symbol_body_and_alias_have_distinct_footprints(self):
        source = '[A]: value AS [B]\n  - child\n'
        values = objects(snapshot(source))
        self.assertEqual(values['A'].definitions, ((0, len(source)),))
        self.assertEqual(values['B'].definitions, ((4, source.index('  - child')),))
        self.assertEqual(values['A'].children, ('B',))
        self.assertEqual(values['B'].relationships, ())

    def test_duplicate_as_keeps_original_identity_without_second_definition(self):
        source = 'Make value AS [A]\nUpdate [A] AS [A]\n'
        values = objects(snapshot(source))
        self.assertEqual(tuple(values), ('A',))
        self.assertEqual(values['A'].definitions, ((0, source.index('Update')),))
        self.assertEqual(len(values['A'].mentions), 1)
        self.assertEqual(values['A'].relationships, ())
        self.assertEqual(values['A'].children, ())
        self.assertEqual(values['A'].available_from, source.index('[A]') + 3)

    def test_unresolved_prior_reference_does_not_become_alias_dependency(self):
        source = 'Use [R] AS [R]\n'
        r = objects(snapshot(source))['R']
        self.assertEqual(r.mentions, ())
        self.assertEqual(r.relationships, ())
        self.assertEqual(r.available_from, source.rindex('[R]') + 3)

    def test_unsupported_recovered_quoted_and_forward_symbols_are_not_objects(self):
        source = ('Use [Future]\n"[Fake]"\n[Unfinished\n'
                  '[Root]:\n  [Nested]: value\n  - "[Quoted]"\n'
                  'Next: separate\n[Future]: yes\n')
        values = objects(snapshot(source))
        self.assertEqual(set(values), {'Root', 'Future'})
        self.assertEqual(values['Future'].mentions, ())
        self.assertEqual(values['Root'].children, ())

    def test_duplicate_resolution_records_do_not_double_count_mention_geometry(self):
        source = '[A]: seed\nUse: [A]\n'
        analysis = analyze(source)
        duplicated = replace(analysis.semantics,
                             resolutions=analysis.semantics.resolutions * 3)
        result = build_graph_snapshot(analysis.tree, duplicated, mode='semantic_triad')
        original = snapshot(source)
        self.assertEqual(result.semantic_footprints, original.semantic_footprints)
        self.assertEqual(len(result.occurrences), len(original.occurrences) * 3)

    def test_no_invented_unit_support_or_automatic_numeric_operators(self):
        source = '[A]: seed\nUse [A] AS [B]\nUse [A] [B]\n'
        result = snapshot(source)
        self.assertTrue(result.semantic_footprints)
        self.assertEqual(result.semantic_evidence, ())
        self.assertEqual(result.semantic_transformations, ())

    def test_parser_support_can_be_disabled_without_changing_heuristic_evidence(self):
        source = '[A]: seed\nUse: [A]\n'
        enabled = snapshot(source)
        disabled = snapshot(source, options={'parser_support': False})
        self.assertEqual(disabled.semantic_footprints, ())
        self.assertEqual(disabled.occurrences, enabled.occurrences)
        self.assertEqual(disabled.owners, enabled.owners)

    def test_heuristic_snapshot_retains_original_lightweight_contract(self):
        source = '[A]: alpha\n[B]: [A]\nTask:\n- [A] [B] [A]\n'
        analysis = analyze(source)
        result = build_graph_snapshot(analysis.tree, analysis.semantics)
        expected = GraphSnapshot((0, 1, 2), ((1, 0), (2, 0), (2, 1), (2, 0)),
                                 ((0, 0), (1, 1), (2, 2), (3, 2)))
        self.assertEqual(result, expected)

    def test_footprints_are_detached_serializable_and_cancelable(self):
        source = '[A]: seed\nUse [A] AS [B]\n'
        result = snapshot(source)
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)
        json.dumps(asdict(result))
        analysis = analyze(source)
        with self.assertRaises(HeatCancelled):
            build_graph_snapshot(analysis.tree, analysis.semantics,
                                 mode='semantic_triad', cancelled=lambda: True)


class AutomaticSemanticViewTests(unittest.TestCase):
    def test_every_syntax_node_has_automatic_view_including_blank_and_recovery(self):
        source = '[Z]: seed\n\nTask:\n- [Z]\n[Unfinished\n"[Fake]"\n'
        analysis = analyze(source)
        result = snapshot(source)
        self.assertEqual(tuple(view.node for view in result.semantic_views),
                         tuple(node.id for node in analysis.tree.nodes))
        self.assertTrue(all(0 <= view.position <= len(source)
                            for view in result.semantic_views))
        self.assertTrue(all(set(view.objects) <= {item.object for item in result.semantic_elements}
                            for view in result.semantic_views))
        result = calculate_graph(result)
        self.assertEqual(tuple(node for node, _ in result.view_details),
                         tuple(node.id for node in analysis.tree.nodes))

    def test_footprints_preserve_declaration_order_and_plain_rows_use_local_identity(self):
        source = '[Zulu]: z\n[Alpha]: a\n[Middle]: m\nTask:\nplain text\n'
        result = snapshot(source)
        order = ('Zulu', 'Alpha', 'Middle')
        self.assertEqual(tuple(item.object for item in result.semantic_footprints), order)
        self.assertEqual(result.semantic_views[3].objects, ('@element:3',))
        self.assertEqual(result.semantic_views[4].objects, ('@element:3',))
        self.assertEqual(result.semantic_views[3].kind, 'all_objects')
        calculated = calculate_graph(result)
        self.assertTrue(all(tuple(item.object for item in values) == order + ('@element:3',)
                            for _, values in calculated.view_details))

    def test_reference_view_retains_token_location_and_includes_final_task_references(self):
        source = '[Z]: seed\n[A]: seed\nTask:\n- [A] now\n- [Z] later\n'
        result = snapshot(source, options={'decay': 0})
        view = result.semantic_views[3]
        self.assertEqual(view.kind, 'reference_use')
        self.assertEqual(view.objects, ('A', '@element:2'))
        self.assertEqual(view.position, source.index('[A]', source.index('Task:')) + 3)
        details = {item.object: item for item in dict(calculate_graph(result).view_details)[3]}
        self.assertEqual(details['A'].mention, 3 / len(source))
        self.assertEqual(details['Z'].mention, 3 / len(source))
        self.assertEqual(tuple(details), ('Z', 'A', '@element:2'))

    def test_task_header_retains_local_end_with_final_member_support(self):
        source = '[Z]: seed\n[A]: seed\nTask:\n- [A]\n- [Z]\n'
        result = snapshot(source, options={'decay': 0})
        view = result.semantic_views[2]
        self.assertEqual(view.kind, 'all_objects')
        self.assertEqual(view.objects, ('@element:2',))
        self.assertEqual(view.position, source.index('- [A]'))
        details = dict(calculate_graph(result).view_details)[2]
        self.assertTrue(all(item.mention == 3 / len(source) for item in details
                            if item.object in ('Z', 'A')))
        self.assertEqual(details[-1].adjusted_linked, 1)

    def test_reference_targets_keep_source_order_without_duplicates(self):
        source = '[Zulu]: z\n[Alpha]: a\nTask: [Alpha] [Zulu] [Alpha] trailing\n'
        result = snapshot(source)
        view = result.semantic_views[2]
        self.assertEqual(view.kind, 'reference_use')
        self.assertEqual(view.objects, ('Zulu', 'Alpha', '@element:2'))
        self.assertEqual(view.position, source.rindex('[Alpha]') + len('[Alpha]'))

    def test_named_body_has_own_primary_identity_and_full_vector(self):
        source = '[Z]: seed\n[A]: [Z] AS [B]\n  - text\nTask: other\n'
        result = snapshot(source)
        view = result.semantic_views[1]
        self.assertEqual((view.kind, view.objects), ('named_block', ('Z', 'A', 'B')))
        self.assertEqual(view.position, source.index('Task:'))
        context = result.semantic_views[2]
        self.assertEqual((context.kind, context.objects, context.position),
                         ('named_context', ('A',), view.position))
        self.assertEqual(tuple(item.object for item in dict(calculate_graph(result).view_details)[1]),
                         ('Z', 'A', 'B', '@element:3'))

    def test_body_reference_uses_target_while_plain_nested_content_uses_own_body(self):
        source = '[Z]: seed\n[A]:\n  - [Z]\n  [Z]:\n  - plain\nTask: end\n'
        result = snapshot(source)
        views = result.semantic_views
        self.assertEqual((views[2].kind, views[2].objects), ('reference_use', ('Z', 'A')))
        # A nested duplicate declaration must not acquire a second Z body.
        self.assertEqual(views[3].kind, 'named_context')
        self.assertNotIn('Z', views[3].objects)
        self.assertNotIn('Z', views[4].objects)

    def test_alias_view_adds_new_identity_at_target_end_in_source_order(self):
        source = '[Z]: seed\n[A]: seed\nTask: [A] [Z] AS [B]\nLater: [B]\n'
        result = snapshot(source)
        view = result.semantic_views[2]
        self.assertEqual(view.kind, 'alias_use')
        self.assertEqual(view.objects, ('Z', 'A', 'B', '@element:2'))
        self.assertEqual(view.position, source.index('[B]') + 3)
        details = {item.object: item for item in dict(calculate_graph(result).view_details)[2]}
        self.assertGreater(details['B'].definition, 0)
        self.assertGreater(details['B'].mention, 0)

    def test_unresolved_alias_source_never_manufactures_object(self):
        source = 'Make [Missing] AS [B]\nTask: [Unknown]\n'
        result = snapshot(source)
        self.assertEqual(result.semantic_views[0].kind, 'alias_use')
        self.assertEqual(result.semantic_views[0].objects, ('B', '@element:0'))
        self.assertEqual(result.semantic_views[1].kind, 'all_objects')
        self.assertEqual(result.semantic_views[1].objects, ('@element:1',))

    def test_disabled_parser_has_empty_all_object_views_and_heuristic_has_none(self):
        source = '[A]: seed\nUse [A] AS [B]\n'
        result = snapshot(source, options={'parser_support': False})
        self.assertTrue(result.semantic_views)
        self.assertTrue(all(view.kind == 'all_objects' and view.objects == ()
                            for view in result.semantic_views))
        analysis = analyze(source)
        heuristic = build_graph_snapshot(analysis.tree, analysis.semantics)
        self.assertEqual(heuristic.semantic_views, ())
        heuristic = build_graph_snapshot(analysis.tree, analysis.semantics, options={'decay': 1})
        self.assertEqual(heuristic.semantic_views, ())


if __name__ == '__main__':
    unittest.main()
