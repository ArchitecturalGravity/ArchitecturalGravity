"""Independent bounded oracles for detached, inherited map support geometry."""
from dataclasses import FrozenInstanceError, asdict, replace
import json
import math
import pickle
import random
import unittest

from AgStudio.shared.graph import (
    GraphSnapshot, HeatCancelled, SemanticElement, SemanticFootprint,
    SemanticPosition, SemanticView, calculate_graph, calculate_inherited_details,
    semantic_state,
)


def snapshot(elements, *, length=100, decay=1.0, **kwargs):
    return GraphSnapshot((), (), (), 'semantic_triad_2', {'decay': decay},
                         document_length=length, semantic_elements=elements, **kwargs)


class InheritedElementTransportTests(unittest.TestCase):
    def test_detached_frozen_records_and_transport_roundtrips(self):
        definitions, mentions, dependencies = [[0, 10]], [[20, 23]], ['B', 'B']
        element = SemanticElement('A', definitions, mentions, dependencies, 7, 'Label')
        definitions[0][0] = 99
        mentions.append([30, 40])
        dependencies.append('C')
        self.assertEqual(element.definitions, ((0, 10),))
        self.assertEqual(element.mentions, ((20, 23),))
        self.assertEqual(element.dependencies, ('B',))
        with self.assertRaises(FrozenInstanceError):
            element.label = 'changed'
        graph = snapshot((element, SemanticElement('B', ((50, 60),))))
        self.assertEqual(GraphSnapshot(**json.loads(json.dumps(asdict(graph)))), graph)
        self.assertEqual(pickle.loads(pickle.dumps(graph)), graph)
        result = calculate_graph(graph)
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)

    def test_invalid_elements_and_snapshot_references_fail_closed(self):
        for fields, error in (
                ({'object': ''}, ValueError),
                ({'definitions': ((3, 2),)}, ValueError),
                ({'mentions': ((-1, 2),)}, ValueError),
                ({'dependencies': 'B'}, TypeError),
                ({'dependencies': ('',)}, ValueError),
                ({'node': True}, TypeError),
                ({'label': 42}, TypeError)):
            with self.subTest(fields=fields), self.assertRaises(error):
                SemanticElement(**dict({'object': 'A'}, **fields))
        for elements in (
                (SemanticElement('A'), SemanticElement('A')),
                (SemanticElement('A', dependencies=('missing',)),),
                (SemanticElement('A', ((0, 101),)),)):
            with self.subTest(elements=elements), self.assertRaises(ValueError):
                snapshot(elements)

    def test_all_map_modes_retain_element_values_and_named_causal_api(self):
        elements = (SemanticElement('A', ((0, 10),)),
                    SemanticElement('@element:1', ((70, 80),), dependencies=('A',),
                                    node=1, label='Plain context'))
        graph = snapshot(elements, decay=0,
                         semantic_footprints=(SemanticFootprint('A', ((0, 10),)),),
                         semantic_views=(SemanticView(1, 80, ('@element:1',)),),
                         semantic_positions=(SemanticPosition(80, ('@element:1',)),))
        for mode in ('semantic_triad_1', 'semantic_triad_2'):
            with self.subTest(mode=mode):
                result = calculate_graph(replace(graph, mode=mode))
                self.assertEqual(tuple((item.object, item.adjusted_linked)
                                       for item in result.final_details),
                                 (('A', .1), ('@element:1', .2)))
                self.assertEqual(result.position_snapshot.semantic_elements, elements)
                if mode == 'semantic_triad_2':
                    self.assertEqual(result.position_values, ((80, (('@element:1', .2),)),))
                else:
                    self.assertEqual(result.view_details, ((1, result.final_details),))
                self.assertEqual(semantic_state(replace(graph, mode=mode), 5), (('A', .05),))


class InheritedElementOracleTests(unittest.TestCase):
    def test_seeded_dependency_graphs_match_discrete_physical_union_oracle(self):
        randomizer = random.Random(83531)
        for trial in range(30):
            count, length = randomizer.randrange(1, 19), randomizer.randrange(1, 65)
            elements = []
            for index in range(count):
                spans = []
                for _ in range(randomizer.randrange(6)):
                    start = randomizer.randrange(length + 1)
                    spans.append((start, randomizer.randrange(start, length + 1)))
                elements.append(SemanticElement(
                    str(index), spans[:2], spans[2:],
                    [str(other) for other in range(count) if randomizer.random() < .17]))
            decay = randomizer.choice((0, 1e-8, .3, 1, 5, 1000))
            actual = calculate_inherited_details(snapshot(elements, length=length, decay=decay))
            supports = []
            for index in range(count):
                visited, pending, characters = set(), [index], set()
                while pending:
                    current = pending.pop()
                    if current in visited:
                        continue
                    visited.add(current)
                    item = elements[current]
                    characters.update(character for start, end in item.definitions + item.mentions
                                      for character in range(start, end))
                    pending.extend(int(other) for other in item.dependencies)
                supports.append(characters)
                expected = math.fsum(math.exp(-decay * (length - character - 1) / length)
                                     / length for character in characters)
                with self.subTest(trial=trial, element=index):
                    self.assertAlmostEqual(actual[index].adjusted_linked, expected, places=13)
                    self.assertEqual(actual[index].linked, len(characters) / length)
            combined = set().union(*supports)
            for index, item in enumerate(actual):
                others = set().union(*(support for other, support in enumerate(supports)
                                       if other != index))
                self.assertEqual(item.comparison, len(combined) / length)
                self.assertEqual(item.shared, len(supports[index] & others) / length)
                self.assertEqual(item.other_only, len(others - supports[index]) / length)

    def test_deep_chain_and_cycle_are_iterative_and_cancellable(self):
        count = 1500
        for cyclic in (False, True):
            elements = tuple(SemanticElement(
                str(index), ((0, 1),),
                dependencies=(str(index + 1),) if index + 1 < count else
                (('0',) if cyclic else ())) for index in range(count))
            graph = snapshot(elements, length=10)
            polls = [0]

            def observed():
                polls[0] += 1
                return False

            actual = calculate_inherited_details(graph, cancelled=observed)
            self.assertEqual(len(actual), count)
            self.assertEqual(len({item.adjusted_linked for item in actual}), 1)
            for stop in (polls[0] // 2, polls[0] - 5):
                calls = [0]

                def cancelled():
                    calls[0] += 1
                    return calls[0] >= stop

                with self.subTest(cyclic=cyclic, stop=stop), self.assertRaises(HeatCancelled):
                    calculate_inherited_details(graph, cancelled=cancelled)

    def test_large_document_uses_intervals_instead_of_character_expansion(self):
        length = 10 ** 12
        graph = snapshot((SemanticElement('A', ((0, length),)),
                          SemanticElement('B', dependencies=('A',))), length=length, decay=0)
        self.assertEqual(tuple(item.linked for item in calculate_inherited_details(graph)), (1, 1))


if __name__ == '__main__':
    unittest.main()
