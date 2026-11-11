"""All three inference modes use the same detached spawned-process contract."""
import time
import unittest

from AgStudio.shared.graph import calculate_graph
from AgStudio.shared.graph.adapter import build_graph_snapshot
from AgStudio.shared.graph.worker import GraphWorker
from AgStudio.shared.lint import analyze


class SemanticProcessTests(unittest.TestCase):
    SOURCE = '[A]:\n- Keep details\n\n[B]:\n- [A]\n- [A] AS [C]\n\nTask:\n- [C]\n'

    def setUp(self):
        self.worker = GraphWorker()
        self.analysis = analyze(self.SOURCE, arcgrav_version='current')

    def tearDown(self):
        self.worker.close()
        self.assertTrue(self.worker.wait_closed(10))
        self.assertIsNone(self.worker.active_pid)

    def snapshot(self, mode):
        return build_graph_snapshot(self.analysis.tree, self.analysis.semantics, mode=mode)

    def outcome(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = self.worker.poll()
            if result is not None:
                self.assertIsNone(result.error)
                return result
            time.sleep(.005)
        self.fail('semantic process did not finish')

    def test_all_modes_match_pure_core_through_spawn(self):
        for index, mode in enumerate(('heuristic', 'semantic_triad_1', 'semantic_triad_2')):
            with self.subTest(mode=mode):
                snapshot = self.snapshot(mode)
                self.worker.submit(index, snapshot)
                result = self.outcome()
                self.assertEqual(result.revision, index)
                self.assertEqual(result.result, calculate_graph(snapshot))

    def test_legacy_triad_aliases_use_canonical_st2_snapshot_through_spawn(self):
        canonical = self.snapshot('semantic_triad_2')
        for mode in ('semantic_triad', 'semantic_triad_3'):
            with self.subTest(mode=mode):
                legacy = self.snapshot(mode)
                self.assertEqual(legacy.mode, 'semantic_triad_2')
                self.assertEqual(legacy, canonical)
                self.assertTrue(legacy.semantic_positions)
                self.worker.submit(5, legacy)
                self.assertEqual(self.outcome().result, calculate_graph(canonical))

    def test_repeated_revision_mode_replacement_keeps_only_latest(self):
        self.worker.submit(7, self.snapshot('heuristic'))
        self.worker.submit(7, self.snapshot('semantic_triad_1'))
        latest = self.snapshot('semantic_triad_2')
        self.worker.submit(7, latest)
        result = self.outcome()
        self.assertEqual(result.result, calculate_graph(latest))
        self.assertIsNone(self.worker.poll())

    def test_hidden_equivalent_cancel_clears_semantic_result(self):
        for mode in ('semantic_triad_1', 'semantic_triad_2'):
            self.worker.submit(8, self.snapshot(mode))
            self.worker.cancel()
            self.assertFalse(self.worker.busy)
            self.assertIsNone(self.worker.poll())
        self.worker.submit(9, self.snapshot('semantic_triad_2'))
        self.assertEqual(self.outcome().revision, 9)
