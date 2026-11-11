"""Detached graph contract; these are presentation, not conformance, tests."""
from dataclasses import FrozenInstanceError, asdict
import json
from pathlib import Path
import pickle
import subprocess
import sys
import unittest

from AgStudio.shared.graph import (
    GraphResult, GraphSnapshot, HeatCancelled, HeatScore, calculate_graph,
    score_relations,
)


class GraphContractTests(unittest.TestCase):
    def test_empty_snapshot_has_an_empty_immutable_result(self):
        snapshot = GraphSnapshot((), (), ())
        self.assertEqual(calculate_graph(snapshot), GraphResult((), (), ()))
        self.assertEqual(hash(snapshot), hash(GraphSnapshot((), (), ())))

    def test_snapshot_detaches_nested_caller_owned_sequences(self):
        blocks = [0, 1]
        occurrences = [[1, 0]]
        owners = [[0, 0], [1, 1], [2, 1]]
        snapshot = GraphSnapshot(blocks, occurrences, owners)
        blocks.append(2)
        occurrences[0][0] = 9
        owners[2][1] = 9
        self.assertEqual(snapshot.blocks, (0, 1))
        self.assertEqual(snapshot.occurrences, ((1, 0),))
        self.assertEqual(snapshot.owners, ((0, 0), (1, 1), (2, 1)))
        with self.assertRaises(FrozenInstanceError):
            snapshot.blocks = ()
        with self.assertRaises(TypeError):
            snapshot.owners[0][1] = 1

    def test_snapshot_only_accepts_serializable_integer_ids(self):
        invalid = (
            ([object()], (), ()),
            ((True,), (), ()),
            ((0,), ((0, object()),), ()),
            ((0,), (), ((0, 'owner'),)),
            ((0,), ((0, 1, 2),), ()),
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(TypeError):
                GraphSnapshot(*values)

    def test_result_and_nested_scores_are_frozen_and_hashable(self):
        score = HeatScore(1, 0.5, 1, 1)
        owners, scores, relations = [[0, 0]], [[0, score]], [[1, 0]]
        result = GraphResult(owners, scores, relations)
        owners[0][1] = 7
        scores[0][0] = 7
        relations[0][0] = 7
        self.assertEqual(result, GraphResult(((0, 0),), ((0, score),), ((1, 0),)))
        self.assertIsInstance(hash(result), int)
        with self.assertRaises(FrozenInstanceError):
            result.scores = ()
        with self.assertRaises(FrozenInstanceError):
            score.direct = 9
        with self.assertRaises(TypeError):
            GraphResult((), ((0, {'direct': 1}),), ())

    def test_snapshot_json_and_result_pickle_round_trip(self):
        snapshot = GraphSnapshot((0, 1, 2), ((1, 0), (1, 0), (2, 1)),
                                 ((0, 0), (1, 1), (2, 2), (3, 2)))
        restored = GraphSnapshot(**json.loads(json.dumps(asdict(snapshot))))
        self.assertEqual(restored, snapshot)
        result = calculate_graph(restored)
        self.assertEqual(pickle.loads(pickle.dumps(snapshot)), snapshot)
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)
        record = json.loads(json.dumps(asdict(result)))
        self.assertEqual(record['scores'][0],
                         [0, {'direct': 2, 'indirect': 0.5,
                              'direct_count': 2, 'indirect_count': 1}])

    def test_exact_scores_and_raw_occurrences_are_preserved(self):
        occurrences = ((1, 0), (1, 0), (2, 1), (2, 2), (0, 99))
        snapshot = GraphSnapshot((3, 2, 1, 0), occurrences,
                                 ((4, 1), (0, 0), (1, 1), (2, 2)))
        result = calculate_graph(snapshot)
        self.assertEqual(result.owners, snapshot.owners)
        self.assertEqual(result.relations, occurrences)
        self.assertEqual(result.scores, (
            (0, HeatScore(2, 0.5, 2, 1)),
            (1, HeatScore(2, 0, 2, 0)),
            (2, HeatScore(1, 0.5, 1, 1)),
            (3, HeatScore()),
        ))
        self.assertEqual(dict(result.scores), score_relations(snapshot.blocks, occurrences))

    def test_scoring_is_deterministic_and_does_not_modify_input(self):
        snapshot = GraphSnapshot((0, 1, 2, 3), ((1, 0), (2, 1), (0, 2)),
                                 ((0, 0), (1, 1), (2, 2), (3, 3)))
        before = pickle.dumps(snapshot)
        expected = calculate_graph(snapshot)
        reordered = GraphSnapshot(tuple(reversed(snapshot.blocks)),
                                  tuple(reversed(snapshot.occurrences)), snapshot.owners)
        for _ in range(3):
            self.assertEqual(calculate_graph(snapshot), expected)
        self.assertEqual(calculate_graph(reordered).scores, expected.scores)
        self.assertEqual(pickle.dumps(snapshot), before)
        copied_scores = dict(expected.scores)
        copied_scores[0] = HeatScore(999)
        self.assertNotEqual(copied_scores[0], dict(expected.scores)[0])
        self.assertEqual(calculate_graph(snapshot), expected)

    def test_cancelled_calculation_never_returns_a_partial_result(self):
        for snapshot in (GraphSnapshot((), (), ()),
                         GraphSnapshot((0, 1), ((1, 0),), ((0, 0), (1, 1)))):
            with self.subTest(snapshot=snapshot), self.assertRaises(HeatCancelled):
                calculate_graph(snapshot, cancelled=lambda: True)

    def test_cancellation_is_checked_while_grouping_occurrences(self):
        polls = 0

        def cancelled():
            nonlocal polls
            polls += 1
            return polls == 10

        snapshot = GraphSnapshot((0, 1), ((1, 0),) * 100, ())
        with self.assertRaises(HeatCancelled):
            calculate_graph(snapshot, cancelled=cancelled)
        self.assertEqual(polls, 10)
        self.assertEqual(dict(calculate_graph(snapshot).scores)[0].direct, 100)

    def test_cancellation_is_checked_during_graph_traversal(self):
        polls = 0

        def cancelled():
            nonlocal polls
            polls += 1
            return polls == 45

        snapshot = GraphSnapshot(tuple(range(20)),
                                 tuple((block, block - 1) for block in range(1, 20)), ())
        with self.assertRaises(HeatCancelled):
            calculate_graph(snapshot, cancelled=cancelled)
        self.assertEqual(polls, 45)

    def test_core_loads_and_calculates_without_its_surrounding_application(self):
        # Loading by path prevents the shared package's legacy eager language
        # exports from masking an accidental dependency of this core itself.
        core = Path(__file__).resolve().parents[1] / 'graph' / 'core.py'
        check = '''
import importlib.util
import sys
class BlockApplicationImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('AgStudio', 'PySide', 'PyQt')):
            raise AssertionError('Unexpected application dependency: ' + fullname)
sys.meta_path.insert(0, BlockApplicationImports())
spec = importlib.util.spec_from_file_location('detached_graph_core', sys.argv[1])
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)
snapshot = core.GraphSnapshot((0, 1), ((1, 0),), ((0, 0), (1, 1)))
assert dict(core.calculate_graph(snapshot).scores)[0].total == 1
'''
        result = subprocess.run([sys.executable, '-I', '-c', check, str(core)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_public_graph_import_does_not_import_gui_or_adapter(self):
        root = Path(__file__).resolve().parents[3]
        check = '''
import sys
from AgStudio.shared.graph import GraphSnapshot, calculate_graph
calculate_graph(GraphSnapshot((), (), ()))
assert not any(name.startswith(('PySide', 'PyQt', 'AgStudio.gui')) for name in sys.modules)
assert 'AgStudio.shared.graph.adapter' not in sys.modules
'''
        result = subprocess.run([sys.executable, '-c', check], cwd=root,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


class GraphAdapterTests(unittest.TestCase):
    def test_adapter_snapshot_reproduces_legacy_heat_view(self):
        from AgStudio.gui.inference_heat import compute_heat
        from AgStudio.shared.graph.adapter import build_graph_snapshot
        from AgStudio.shared.lint import analyze

        sources = (
            '', '\n  \n',
            '[A]: value\n\n[D]:\n- Use [A] [A] [A]\n',
            '[Base]: text\n\n[Producer]:\n=> Read [Base] AS [Alias]\n'
            '\nConsumer:\n- Use [Alias]\n',
            '[Base]: text\n\n[Outer]:\n  [Base]:\n  - More [Base]\n'
            '  Details:\n  - Other [Base]\n\nTail: text\n',
            'Root:\n  Nested:\n    - Leaf\n\nOther: plain\n',
        )
        for source in sources:
            with self.subTest(source=source):
                analysis = analyze(source)
                snapshot = build_graph_snapshot(analysis.tree, analysis.semantics)
                self.assertIsInstance(snapshot, GraphSnapshot)
                self.assertEqual(snapshot.blocks, tuple(sorted(set(snapshot.blocks))))
                self.assertTrue(all(type(block) is int for block in snapshot.blocks))
                self.assertTrue(all(type(value) is int for pair in snapshot.owners
                                    + snapshot.occurrences for value in pair))
                result = calculate_graph(snapshot)
                legacy = compute_heat(analysis.tree, analysis.semantics)
                self.assertEqual(dict(result.owners), legacy.owners)
                self.assertEqual(dict(result.scores), legacy.scores)
                self.assertEqual(result.relations, legacy.relations)
                self.assertEqual(pickle.loads(pickle.dumps(snapshot)), snapshot)

    def test_adapter_cancels_before_inspecting_parser_objects(self):
        from AgStudio.shared.graph.adapter import build_graph_snapshot

        with self.assertRaises(HeatCancelled):
            build_graph_snapshot(None, None, cancelled=lambda: True)

    def test_compatibility_facade_reexports_the_core_types(self):
        from AgStudio.gui import inference_heat
        from AgStudio.shared.graph.adapter import whole_block_owners

        self.assertIs(inference_heat.HeatCancelled, HeatCancelled)
        self.assertIs(inference_heat.HeatScore, HeatScore)
        self.assertIs(inference_heat.score_relations, score_relations)
        self.assertIs(inference_heat.whole_block_owners, whole_block_owners)


if __name__ == '__main__':
    unittest.main()
