"""Pure document-map heat heuristics, separate from ArcGrav conformance.

These checks exercise presentation scoring without importing Qt or asserting
new language semantics. Relation evidence comes from the existing analyzer.
"""
from collections import Counter
from dataclasses import replace
from itertools import permutations
import random
import unittest

from AgStudio.gui.inference_heat import compute_heat, heat_rgb, score_relations
from AgStudio.shared.lint import analyze


class RelationHeatTests(unittest.TestCase):
    def assert_score(self, score, direct, indirect):
        self.assertAlmostEqual(score.direct, direct)
        self.assertAlmostEqual(score.indirect, indirect)
        self.assertAlmostEqual(score.total, direct + indirect)

    def assert_counts(self, score, direct, indirect):
        self.assertIs(type(score.direct_count), int)
        self.assertIs(type(score.indirect_count), int)
        self.assertEqual((score.direct_count, score.indirect_count), (direct, indirect))

    def test_empty_and_single_isolated_block(self):
        self.assertEqual(score_relations((), ()), {})
        scores = score_relations((7,), ())
        self.assertEqual(set(scores), {7})
        self.assert_score(scores[7], 0, 0)
        self.assert_counts(scores[7], 0, 0)

    def test_one_reference_has_no_endpoint_reflection(self):
        scores = score_relations((0, 1), ((1, 0),))
        self.assert_score(scores[0], 1, 0)
        self.assert_score(scores[1], 1, 0)
        self.assert_counts(scores[0], 1, 0)
        self.assert_counts(scores[1], 1, 0)

    def test_repeated_source_credits_receiver_only_once(self):
        # D names A three times: A receives three credits; D receives one.
        scores = score_relations((0, 3), ((3, 0),) * 3)
        self.assert_score(scores[0], 3, 0)
        self.assert_score(scores[3], 1, 0)
        self.assert_counts(scores[0], 3, 0)
        self.assert_counts(scores[3], 1, 0)

    def test_raw_values_are_not_clamped_to_color_channels(self):
        scores = score_relations((0, 1), ((1, 0),) * 300)
        self.assert_score(scores[0], 300, 0)
        self.assert_score(scores[1], 1, 0)
        self.assertEqual(heat_rgb(scores[0].total, 1, 300), (255, 0, 0))
        self.assertEqual(heat_rgb(scores[1].total, 1, 300), (0, 0, 255))

    def test_opposite_directions_are_separate_relations(self):
        scores = score_relations((0, 1), ((1, 0), (1, 0), (0, 1)))
        self.assert_score(scores[0], 3, 0)
        self.assert_score(scores[1], 2, 0)

    def test_self_relations_contribute_nothing(self):
        scores = score_relations((0, 1), ((0, 0),) * 4 + ((1, 1),))
        self.assert_score(scores[0], 0, 0)
        self.assert_score(scores[1], 0, 0)
        baseline = score_relations((0, 1, 2), ((1, 0), (2, 1)))
        self.assertEqual(
            score_relations((0, 1, 2), ((1, 0), (2, 1), (1, 1))), baseline)

    def test_three_block_chain_attenuates_over_undirected_links(self):
        scores = score_relations((0, 1, 2), ((1, 0), (2, 1)))
        self.assert_score(scores[0], 1, 0.5)
        self.assert_score(scores[1], 2, 0)
        self.assert_score(scores[2], 1, 0.5)

    def test_long_chain_attenuates_once_per_shortest_hop(self):
        scores = score_relations(range(5), ((1, 0), (2, 1), (3, 2), (4, 3)))
        expected = ((1, 0.875), (2, 0.75), (2, 1), (2, 0.75), (1, 0.875))
        for block, (direct, indirect) in enumerate(expected):
            with self.subTest(block=block):
                self.assert_score(scores[block], direct, indirect)
                self.assert_counts(scores[block], direct, 4 - direct)

    def test_branch_propagates_each_distinct_relation_once(self):
        scores = score_relations(range(4), ((1, 0), (2, 0), (3, 0)))
        self.assert_score(scores[0], 3, 0)
        for block in (1, 2, 3):
            self.assert_score(scores[block], 1, 1)

    def test_equal_distance_uses_larger_endpoint_once(self):
        # C is one hop from both ends of triple B->A. Its increment is 1.5,
        # rather than 0.5, 2.0, or two separately propagated endpoint values.
        scores = score_relations(range(3), ((1, 0),) * 3 + ((2, 0), (2, 1)))
        self.assert_score(scores[0], 4, 0.5)
        self.assert_score(scores[1], 2, 0.5)
        self.assert_score(scores[2], 2, 1.5)
        self.assert_counts(scores[0], 4, 1)
        self.assert_counts(scores[1], 2, 1)
        self.assert_counts(scores[2], 2, 1)

    def test_nearer_endpoint_wins_even_if_farther_endpoint_is_heavier(self):
        ordinary = score_relations(range(4), ((1, 0), (2, 1), (3, 2)))
        repeated = score_relations(range(4), ((1, 0),) * 10 + ((2, 1), (3, 2)))
        self.assertEqual(repeated[1], ordinary[1])
        self.assertEqual(repeated[2], ordinary[2])
        self.assertEqual(repeated[3], ordinary[3])
        self.assertAlmostEqual(repeated[0].total - ordinary[0].total, 9)

    def test_diamond_does_not_duplicate_multiple_paths(self):
        scores = score_relations(range(4), ((1, 0), (2, 0), (3, 1), (3, 2)))
        for score in scores.values():
            self.assert_score(score, 2, 1)
            self.assert_counts(score, 2, 2)

    def test_triangle_cycle_does_not_recirculate_heat(self):
        scores = score_relations(range(3), ((1, 0), (2, 1), (0, 2)))
        for score in scores.values():
            self.assert_score(score, 2, 0.5)
            self.assert_counts(score, 2, 1)

    def test_disconnected_components_do_not_share_heat(self):
        scores = score_relations(range(6), ((1, 0), (2, 1), (4, 3)))
        self.assert_score(scores[0], 1, 0.5)
        self.assert_score(scores[1], 2, 0)
        self.assert_score(scores[2], 1, 0.5)
        self.assert_score(scores[3], 1, 0)
        self.assert_score(scores[4], 1, 0)
        self.assert_score(scores[5], 0, 0)
        for block, counts in enumerate(((1, 1), (2, 0), (1, 1), (1, 0), (1, 0), (0, 0))):
            self.assert_counts(scores[block], *counts)

    def test_occurrence_and_block_iteration_order_do_not_change_scores(self):
        relations = ((1, 0), (1, 0), (2, 1), (3, 1), (3, 2))
        expected = score_relations(range(5), relations)
        for ordering in set(permutations(relations)):
            self.assertEqual(score_relations(reversed(range(5)), iter(ordering)), expected)

    def test_small_graphs_match_independent_all_pairs_distance_oracle(self):
        # Floyd-Warshall deliberately differs from the helper's propagation
        # algorithm, including its traversal and equal-distance handling.
        random_source = random.Random(1327)
        for size in range(1, 8):
            for trial in range(30):
                occurrences = [(random_source.randrange(size), random_source.randrange(size))
                               for _ in range(random_source.randrange(size * size + 1))]
                counts = Counter(pair for pair in occurrences if pair[0] != pair[1])
                distance = [[0 if a == b else float('inf') for b in range(size)]
                            for a in range(size)]
                for receiver, source in counts:
                    distance[receiver][source] = distance[source][receiver] = 1
                for via in range(size):
                    for start in range(size):
                        for end in range(size):
                            distance[start][end] = min(distance[start][end],
                                                      distance[start][via] + distance[via][end])
                actual = score_relations(range(size), occurrences)
                for block in range(size):
                    direct = indirect = indirect_count = 0
                    for (receiver, source), count in counts.items():
                        if block == receiver:
                            direct += 1
                        elif block == source:
                            direct += count
                        else:
                            near_receiver = distance[block][receiver]
                            near_source = distance[block][source]
                            hops = min(near_receiver, near_source)
                            if hops == float('inf'):
                                continue
                            weight = 1 if near_receiver < near_source else count
                            indirect += weight * 0.5 ** hops
                            indirect_count += 1
                    with self.subTest(size=size, trial=trial, block=block):
                        self.assert_score(actual[block], direct, indirect)
                        self.assert_counts(actual[block], direct, indirect_count)


class HeatColorTests(unittest.TestCase):
    def test_full_blue_red_endpoints_and_midpoint(self):
        self.assertEqual(heat_rgb(10, 10, 30), (0, 0, 255))
        self.assertEqual(heat_rgb(20, 10, 30), (128, 0, 128))
        self.assertEqual(heat_rgb(30, 10, 30), (255, 0, 0))

    def test_zero_range_is_blue_and_positive_equal_range_is_purple(self):
        self.assertEqual(heat_rgb(0, 0, 0), (0, 0, 255))
        for value in (0.25, 1, 300):
            self.assertEqual(heat_rgb(value, value, value), (128, 0, 128))

    def test_color_channels_are_integers_and_monotonic(self):
        colors = [heat_rgb(value / 10, 0, 1) for value in range(11)]
        for color in colors:
            self.assertEqual(len(color), 3)
            self.assertTrue(all(type(channel) is int and 0 <= channel <= 255 for channel in color))
            self.assertEqual(color[1], 0)
        self.assertEqual([c[0] for c in colors], sorted(c[0] for c in colors))
        self.assertEqual([c[2] for c in colors], sorted((c[2] for c in colors), reverse=True))


class SemanticHeatTests(unittest.TestCase):
    def make_heat(self, source):
        analysis = analyze(source)
        return analysis, compute_heat(analysis.tree, analysis.semantics)

    def node(self, analysis, text):
        source = analysis.document.source
        matches = [node.id for node in analysis.tree.nodes
                   if node.span.extract(source).strip() == text]
        self.assertEqual(len(matches), 1, f'Expected one node matching {text!r}')
        return matches[0]

    def test_semantic_occurrences_preserve_multiplicity(self):
        analysis, heat = self.make_heat('[A]: value\n\n[D]:\n- Use [A] [A] [A]\n')
        a, d = self.node(analysis, '[A]: value'), self.node(analysis, '[D]:')
        self.assertEqual(heat.relations, ((d, a),) * 3)
        self.assertEqual(heat.scores[a].direct, 3)
        self.assertEqual(heat.scores[d].direct, 1)

    def test_blank_lines_do_not_add_zero_score_normalization_blocks(self):
        analysis, heat = self.make_heat('\n[A]: text\n\n\nTask:\n- [A]\n\n')
        a = self.node(analysis, '[A]: text')
        task = self.node(analysis, 'Task:')
        self.assertEqual(set(heat.scores), {a, task})
        self.assertEqual([heat.scores[b].total for b in (a, task)], [1, 1])

    def test_empty_and_whitespace_documents_have_no_scored_blocks(self):
        for source in ('', '\n', '  \n\t\n'):
            with self.subTest(source=source):
                _, heat = self.make_heat(source)
                self.assertEqual(heat.scores, {})
                self.assertEqual(heat.relations, ())

    def test_alias_points_to_declaration_whole_block_not_a_new_block(self):
        source = ('[Base]: text\n\n[Producer]:\n=> Read [Base] AS [Alias]\n'
                  '\nConsumer:\n- Use [Alias]\n')
        analysis, heat = self.make_heat(source)
        base = self.node(analysis, '[Base]: text')
        producer = self.node(analysis, '[Producer]:')
        consumer = self.node(analysis, 'Consumer:')
        declaration = self.node(analysis, '=> Read [Base] AS [Alias]')
        self.assertEqual(heat.owners[declaration], producer)
        self.assertNotIn(declaration, heat.scores)
        self.assertEqual(heat.relations, ((producer, base), (consumer, producer)))
        self.assertEqual([heat.scores[b].total for b in (base, producer, consumer)], [1.5, 2, 1.5])

    def test_forward_unresolved_literal_and_quoted_occurrences_are_ignored(self):
        source = ('Task:\n- Use [Future] [Missing]\n\n[Future]: value\n\nUse:\n'
                  '- "[Future]"\n"""\n[Future] [Future]\n"""\n- [Future]\n')
        analysis, heat = self.make_heat(source)
        future = self.node(analysis, '[Future]: value')
        use = self.node(analysis, 'Use:')
        task = self.node(analysis, 'Task:')
        self.assertEqual(heat.relations, ((use, future),))
        self.assertEqual(heat.scores[task].total, 0)

    def test_unsupported_resolution_status_cannot_supply_an_edge(self):
        analysis = analyze('[Known]: value\n\nTask:\n- [Known]\n')
        reference = analysis.semantics.resolutions[0]
        for status in ('forward_candidate', 'missing_local_anchor', 'uncertain_identity',
                       'forbidden_nested_declaration', 'unsupported'):
            with self.subTest(status=status):
                semantics = replace(analysis.semantics, resolutions=(replace(reference, status=status),))
                heat = compute_heat(analysis.tree, semantics)
                self.assertEqual(heat.relations, ())
                self.assertTrue(all(score.total == 0 for score in heat.scores.values()))

    def test_plain_nested_headers_keep_enclosing_whole_block(self):
        source = ('[Base]: text\n\n[Consumer]:\n  Details:\n  - Use [Base]\n'
                  '\nIndependent: text\n')
        analysis, heat = self.make_heat(source)
        base = self.node(analysis, '[Base]: text')
        consumer = self.node(analysis, '[Consumer]:')
        nested = self.node(analysis, 'Details:')
        use = self.node(analysis, '- Use [Base]')
        independent = self.node(analysis, 'Independent: text')
        self.assertEqual(heat.owners[nested], consumer)
        self.assertEqual(heat.owners[use], consumer)
        self.assertNotIn(nested, heat.scores)
        self.assertEqual(heat.relations, ((consumer, base),))
        self.assertEqual(heat.scores[independent].total, 0)

    def test_nested_duplicate_symbol_header_keeps_enclosing_owner(self):
        source = ('[Base]: text\n\n[Outer]:\n  [Base]:\n  - More [Base]\n'
                  '  Details:\n  - Other [Base]\n\nTail: text\n')
        analysis, heat = self.make_heat(source)
        base = self.node(analysis, '[Base]: text')
        outer = self.node(analysis, '[Outer]:')
        nested = self.node(analysis, '[Base]:')
        self.assertEqual(heat.owners[nested], outer)
        self.assertEqual(heat.owners[self.node(analysis, '- More [Base]')], outer)
        self.assertEqual(heat.owners[self.node(analysis, 'Details:')], outer)
        self.assertEqual(heat.relations, ((outer, base), (outer, base)))

    def test_symbol_body_in_list_starts_whole_block_inside_plain_section(self):
        source = '[A]: value\nHolder:\n- [B]:\n  - [A]\n  - [A]\n'
        analysis, heat = self.make_heat(source)
        a = self.node(analysis, '[A]: value')
        holder = self.node(analysis, 'Holder:')
        b = self.node(analysis, '- [B]:')
        self.assertEqual(heat.owners[b], b)
        for node in analysis.tree.nodes:
            if node.parent == b:
                self.assertEqual(heat.owners[node.id], b)
        self.assertEqual(heat.relations, ((b, a), (b, a)))
        self.assertEqual(heat.scores[a].total, 2)
        self.assertEqual(heat.scores[b].total, 1)
        self.assertEqual(heat.scores[holder].total, 0)

    def test_unsupported_nested_symbol_does_not_manufacture_a_block(self):
        source = '[Outer]:\n  [Unknown]:\n  - Body\n\nTail: text\n'
        analysis, heat = self.make_heat(source)
        outer = self.node(analysis, '[Outer]:')
        nested = self.node(analysis, '[Unknown]:')
        self.assertEqual(heat.owners[nested], outer)
        self.assertNotIn(nested, heat.scores)
        self.assertEqual(heat.relations, ())

    def test_top_level_sections_and_structural_roots_own_their_descendants(self):
        source = ('Loose prose\n- A root item\n  - A nested item\n\nPlain:\n- Text\n'
                  '  Nested:\n  - Inner text\n\n[Symbol]: value\n')
        analysis, heat = self.make_heat(source)
        root = self.node(analysis, '- A root item')
        plain = self.node(analysis, 'Plain:')
        self.assertEqual(heat.owners[self.node(analysis, '- A nested item')], root)
        for text in ('- Text', 'Nested:', '- Inner text'):
            self.assertEqual(heat.owners[self.node(analysis, text)], plain)
        for text in ('Loose prose', '- A root item', 'Plain:', '[Symbol]: value'):
            node = self.node(analysis, text)
            self.assertEqual(heat.owners[node], node)
            self.assertEqual(heat.scores[node].total, 0)
        self.assertEqual(heat.relations, ())

    def test_canonical_links_take_priority_over_visual_indentation(self):
        analysis, heat = self.make_heat('[Base]: text\n\n[Consumer]:\n  Details:\n  - Use [Base]\n')
        # Changing only presentation indentation cannot change known ownership.
        moved = replace(analysis.tree, nodes=tuple(replace(node, indent=0)
                                                  for node in analysis.tree.nodes))
        again = compute_heat(moved, analysis.semantics)
        self.assertEqual(again.owners, heat.owners)
        self.assertEqual(again.relations, heat.relations)
        self.assertEqual(again.scores, heat.scores)

    def test_plain_layout_changes_do_not_change_whole_block_heat(self):
        for body in ('- Use [Base]\n', '  - Use [Base]\n',
                     '  Details:\n  - Use [Base]\n',
                     '  Details:\n    Deeper:\n    - Use [Base]\n'):
            with self.subTest(body=body):
                analysis, heat = self.make_heat('[Base]: text\n\n[Consumer]:\n' + body)
                base = self.node(analysis, '[Base]: text')
                consumer = self.node(analysis, '[Consumer]:')
                self.assertEqual(heat.relations, ((consumer, base),))
                self.assertEqual(heat.scores[base].total, 1)
                self.assertEqual(heat.scores[consumer].total, 1)

    def test_self_reference_and_local_alias_usage_do_not_create_heat(self):
        source = '[Owner]:\n=> Collect AS [Local]\n- Use [Owner] [Local]\n'
        analysis, heat = self.make_heat(source)
        self.assertEqual(heat.relations, ())
        self.assertTrue(all(score.total == 0 for score in heat.scores.values()))

    def test_containment_alone_never_creates_relations(self):
        analysis, heat = self.make_heat('Root:\n  Nested:\n    - Leaf\n\nOther: plain\n')
        self.assertEqual(heat.relations, ())
        self.assertTrue(all(score.total == 0 for score in heat.scores.values()))


if __name__ == '__main__':
    unittest.main()
