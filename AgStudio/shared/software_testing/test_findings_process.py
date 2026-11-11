"""One parse per revision, immutable transport, and Findings process delivery."""
from dataclasses import FrozenInstanceError, fields, is_dataclass
from functools import partial
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import pickle
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from AgStudio.shared.analysis_snapshot import (
    AnalysisRequest, AnalysisSnapshot, PackedAnalysisSnapshot, FindingsUpdate,
    calculate_analysis_snapshot, calculate_parse_snapshot, calculate_packed_parse,
    calculate_findings_update, pack_analysis, unpack_analysis,
    freeze_analysis, freeze_document, restore_analysis, restore_document,
)
from AgStudio.shared.core import LanguageCore
from AgStudio.shared.feature_worker import FeatureWorker
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.model import CanonicalDocument


_SOURCE = '[A]: 🌍\r\nScope:\r\n  - Use [A]\r\n=> 1. Act\r\n'


def _inspect_analysis(snapshot):
    from AgStudio.shared.lint.rules import evaluate_with_admission
    with patch('AgStudio.arcgrav_language_engine.api.parse', side_effect=AssertionError('Findings reparsed')), \
            patch('AgStudio.shared.analysis_snapshot.LanguageCore.parse_document', side_effect=AssertionError('Findings reparsed')), \
            patch('AgStudio.shared.lint.findings.evaluate_with_admission', wraps=evaluate_with_admission) as run:
        result = calculate_analysis_snapshot(snapshot)
    return result, run.call_count, any(name.startswith('PySide6') for name in sys.modules)


def _inspect_parse(request):
    from AgStudio.shared.lint.syntax import parse
    with patch('AgStudio.arcgrav_language_engine.api.parse', wraps=parse) as parser, \
            patch('AgStudio.shared.analysis_snapshot.LanguageCore.parse_document', wraps=LanguageCore.parse_document) as recognition, \
            patch('AgStudio.arcgrav_language_engine.api.diagnose', side_effect=AssertionError('Parser ran findings')), \
            patch('AgStudio.shared.lint.findings.assemble_diagnostics', side_effect=AssertionError('Parser ran findings')):
        result = calculate_parse_snapshot(request)
    return result, parser.call_count, recognition.call_count


def _gated_analysis(request, *, started_path):
    if unpack_analysis(request).document.recognition.session.source == 'old':
        Path(started_path).write_text(str(os.getpid()), encoding='ascii')
        # Deliberately does not cooperate with controller cancellation.
        while True:
            time.sleep(0.01)
    return calculate_analysis_snapshot(request)


def _failing_findings(snapshot):
    raise RuntimeError('Findings failure after shared parse')


class AnalysisSnapshotTests(unittest.TestCase):
    def assert_immutable_data(self, value, seen=None):
        seen = set() if seen is None else seen
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, (str, bytes, int, float, bool, type(None))):
            return
        if isinstance(value, (tuple, frozenset)):
            for item in value:
                self.assert_immutable_data(item, seen)
            return
        self.assertTrue(is_dataclass(value), type(value).__name__)
        self.assertTrue(value.__dataclass_params__.frozen, type(value).__name__)
        for field in fields(value):
            self.assert_immutable_data(getattr(value, field.name), seen)

    def test_canonical_round_trip_preserves_context_facts_relationships_and_results(self):
        analysis = analyze(_SOURCE, profile='review', configuration={'nested': ['one', {'two': 2}]})
        snapshot = freeze_analysis(analysis)
        self.assert_immutable_data(snapshot)
        snapshot = pickle.loads(pickle.dumps(snapshot))
        with patch('AgStudio.shared.document.model.ParsedDocument.__init__', side_effect=AssertionError('reparse')), \
                patch('AgStudio.shared.lint.model.CanonicalDocument.__init__', side_effect=AssertionError('rebuild')), \
                patch('AgStudio.shared.lint.syntax.parse', side_effect=AssertionError('reparse')):
            restored = restore_analysis(snapshot)
        self.assertEqual(restored.as_record(), analysis.as_record())
        self.assertEqual(restored.document.session.configuration, {'nested': ['one', {'two': 2}]})
        self.assertIsInstance(restored.document, CanonicalDocument)
        self.assertIs(restored.document.syntax, restored.tree)
        self.assertIs(restored.document.semantics, restored.semantics)
        for fact in analysis.document.facts():
            self.assertEqual(restored.document.fact(fact.id), fact)
            for kind in ('containment', 'ownership', 'identity'):
                self.assertEqual(restored.document.relationship(fact.id, kind),
                                 analysis.document.relationship(fact.id, kind))
        with self.assertRaises(TypeError):
            restored.document._facts_by_id['new'] = None
        with self.assertRaises(TypeError):
            restored.document._relationships[('new', 'identity')] = 'old'
        with self.assertRaises(FrozenInstanceError):
            snapshot.conformance = 'changed'

    def test_recognition_only_document_round_trip_does_not_become_canonical(self):
        document = LanguageCore.parse_document(LanguageCore.open_source(_SOURCE, arcgrav_version='current'))
        snapshot = freeze_document(document)
        self.assert_immutable_data(snapshot)
        restored = restore_document(pickle.loads(pickle.dumps(snapshot)))
        self.assertEqual(restored, document)
        self.assertFalse(isinstance(restored, CanonicalDocument))
        for offset in range(len(document.source) + 1):
            self.assertEqual(restored.position(offset), document.position(offset))

    def test_single_parse_feeds_checks_without_reparsing_and_returns_immutable_projection(self):
        request = AnalysisRequest(_SOURCE, 'current', None, '{}')
        snapshot, parses, recognitions = _inspect_parse(request)
        self.assertEqual((parses, recognitions), (1, 1))
        self.assertEqual(snapshot.diagnostics.status, 'pending')
        result, calls, _ = _inspect_analysis(snapshot)
        self.assertEqual(calls, 1)
        self.assertIsInstance(result.snapshot, AnalysisSnapshot)
        self.assert_immutable_data(result)
        self.assertEqual(result.findings_projection.document_id, result.snapshot.document.document_id)
        self.assertEqual(restore_analysis(result.snapshot).as_record(), analyze(_SOURCE).as_record())

    def test_packed_transport_forwards_bytes_without_reserializing_parse_objects(self):
        request = AnalysisRequest(_SOURCE, 'current', 'review', '{"nested":[1]}')
        packed = calculate_packed_parse(request)
        self.assertIsInstance(packed, PackedAnalysisSnapshot)
        self.assert_immutable_data(packed)
        with patch.object(AnalysisSnapshot, '__getstate__', side_effect=AssertionError('walked parse again')):
            forwarded = pickle.loads(pickle.dumps(packed))
        self.assertEqual(forwarded, packed)
        restored = restore_analysis(unpack_analysis(forwarded))
        self.assertEqual(restored.document.source, _SOURCE)
        self.assertEqual(restored.document.session.configuration, {'nested': [1]})

    def test_findings_update_returns_only_new_data_with_full_analysis_parity(self):
        from dataclasses import replace
        packed = calculate_packed_parse(AnalysisRequest(_SOURCE, 'current', None, '{}'))
        parsed = restore_analysis(unpack_analysis(packed))
        with patch('AgStudio.arcgrav_language_engine.api.parse', side_effect=AssertionError('reparse')):
            result = calculate_findings_update(packed)
        self.assertIsInstance(result, FindingsUpdate)
        self.assert_immutable_data(result)
        self.assertEqual(tuple(field.name for field in fields(result)),
                         ('document_id', 'diagnostics', 'findings_projection'))
        self.assertEqual(replace(parsed, diagnostics=result.diagnostics).as_record(), analyze(_SOURCE).as_record())
        self.assertEqual(result.document_id, parsed.document.document_id)

    def test_worker_analyzes_in_a_distinct_qt_free_process(self):
        worker = FeatureWorker(_inspect_analysis, name='findings-test')
        try:
            worker.submit(7, calculate_parse_snapshot(
                AnalysisRequest(_SOURCE, 'current', 'review', json.dumps({'a': [1]}))))
            deadline, outcome = time.monotonic() + 15, None
            while outcome is None and time.monotonic() < deadline:
                outcome = worker.poll()
                time.sleep(0.005)
            self.assertIsNotNone(outcome)
            self.assertIsNone(outcome.error)
            self.assertNotEqual(outcome.worker_pid, os.getpid())
            result, calls, qt_loaded = outcome.result
            self.assertEqual(calls, 1)
            self.assertFalse(qt_loaded)
            self.assertEqual(outcome.revision, 7)
            self.assertEqual(result.snapshot.document.recognition.session.profile, 'review')
        finally:
            worker.close()
            self.assertTrue(worker.wait_closed(10))


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class FindingsControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def controller(self, **kwargs):
        from AgStudio.gui.analysis import AnalysisController
        controller = AnalysisController(delay_ms=0, heat_enabled=False, **kwargs)
        self.addCleanup(controller.deleteLater)
        self.addCleanup(self.close_controller, controller)
        return controller

    def close_controller(self, controller):
        controller.close()
        self.assertTrue(controller.process_worker.wait_closed(10))
        self.assertTrue(controller.parser_worker.wait_closed(10))
        self.assertTrue(controller.graph.worker.wait_closed(10))

    def wait_for(self, predicate, timeout=15):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), 'Findings delivery did not reach expected state')

    def test_default_uses_process_and_publishes_prepared_snapshot_on_gui_thread(self):
        from PySide6.QtCore import QThread
        controller = self.controller()
        published = []
        controller.ready.connect(lambda revision, result: published.append(
            (revision, result, QThread.currentThread(), controller.findings_projection,
             controller.analysis_snapshot)))
        options = {'items': ['original']}
        with patch('AgStudio.gui.analysis._POOL.submit', side_effect=AssertionError('production thread analysis')):
            revision = controller.request(_SOURCE, 'current', profile='review', configuration=options)
            options['items'].append('changed')
            self.wait_for(lambda: bool(published))
        actual_revision, result, thread, projection, snapshot = published[0]
        self.assertEqual(actual_revision, revision)
        self.assertEqual(thread, self.app.thread())
        self.assertEqual(result.document.session.configuration, {'items': ['original']})
        self.assertEqual(projection.document_id, result.document.document_id)
        self.assertIs(controller.document_snapshot, snapshot.document)
        self.assertIs(controller.prepared_analysis, result)
        self.assertIsInstance(controller.packed_snapshot, PackedAnalysisSnapshot)
        self.assertIs(result.document, controller.parsed_analysis.document)
        self.assertIs(result.tree, controller.parsed_analysis.tree)
        self.assertNotEqual(controller.worker_pid, os.getpid())
        self.assertIs(controller.graph.analysis, controller.parsed_analysis)
        self.assertEqual(controller.graph.analysis.tree, result.tree)
        self.assertNotEqual(controller.parser_pid, controller.worker_pid)

    def test_replaced_revision_terminates_old_process_and_only_delivers_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'old.started'
            worker = FeatureWorker(partial(_gated_analysis, started_path=str(marker)), name='findings-test')
            with patch('AgStudio.gui.analysis.FeatureWorker', side_effect=lambda calculation, *, name: (
                    worker if name == 'findings' else FeatureWorker(calculation, name=name))):
                controller = self.controller()
            published = []
            controller.ready.connect(lambda revision, result: published.append((revision, result)))
            controller.request('old', 'current', immediate=True)
            # File creation precedes write completion; wait for the PID payload.
            self.wait_for(lambda: marker.exists() and bool(marker.read_text().strip()))
            old_pid = int(marker.read_text())
            self.assertIsNotNone(controller.parsed_analysis)
            self.assertIs(controller.graph.analysis, controller.parsed_analysis)
            self.assertFalse(published)
            started = time.monotonic()
            latest = controller.request('Scope: newest\n', 'current', immediate=True)
            self.assertLess(time.monotonic() - started, 0.25)
            self.wait_for(lambda: bool(published))
            self.assertEqual([revision for revision, _ in published], [latest])
            self.assertEqual(published[0][1].document.source, 'Scope: newest\n')
            self.assertNotIn(old_pid, [child.pid for child in multiprocessing.active_children()])

    def test_worker_failure_recovers_on_next_context(self):
        controller = self.controller()
        failures, published = [], []
        controller.failed.connect(lambda revision, error: failures.append((revision, error)))
        controller.ready.connect(lambda revision, result: published.append((revision, result)))
        failed_revision = controller.request('Scope: source', '')
        self.wait_for(lambda: bool(failures))
        self.assertEqual(failures[0][0], failed_revision)
        self.assertIn('version', failures[0][1])
        self.assertIsNone(controller.prepared_analysis)
        self.assertIsNone(controller.analysis_snapshot)
        current = controller.request('Scope: source', 'current')
        self.wait_for(lambda: bool(published))
        self.assertEqual(published[0][0], current)
        self.assertIsNotNone(controller.findings_projection)

    def test_findings_failure_keeps_independently_published_parse(self):
        worker = FeatureWorker(_failing_findings, name='findings-test')
        with patch('AgStudio.gui.analysis.FeatureWorker', side_effect=lambda calculation, *, name: (
                worker if name == 'findings' else FeatureWorker(calculation, name=name))):
            controller = self.controller()
        parsed, ready, failed = [], [], []
        controller.parsed.connect(lambda revision, result: parsed.append((revision, result)))
        controller.ready.connect(lambda *args: ready.append(args))
        controller.failed.connect(lambda *args: failed.append(args))
        revision = controller.request('Scope: source', 'current')
        self.wait_for(lambda: bool(failed))
        self.assertEqual(parsed[0][0], revision)
        self.assertEqual(failed[0][0], revision)
        self.assertIn('Findings failure', failed[0][1])
        self.assertFalse(ready)
        self.assertIs(controller.graph.analysis, parsed[0][1])
        self.assertIs(controller.parsed_analysis, parsed[0][1])
        self.assertIsNotNone(controller.analysis_snapshot)
        self.assertIsNone(controller.prepared_analysis)

    def test_qobject_destruction_closes_both_workers_without_close_event(self):
        from PySide6.QtCore import QObject
        from shiboken6 import delete
        from AgStudio.gui.analysis import AnalysisController
        owner = QObject()
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'old.started'
            worker = FeatureWorker(partial(_gated_analysis, started_path=str(marker)), name='findings-test')
            with patch('AgStudio.gui.analysis.FeatureWorker', side_effect=lambda calculation, *, name: (
                    worker if name == 'findings' else FeatureWorker(calculation, name=name))):
                controller = AnalysisController(owner, delay_ms=0, heat_enabled=False)
            workers = (controller.parser_worker, controller.process_worker, controller.graph.worker)
            try:
                controller.request('old', 'current')
                self.wait_for(marker.exists)
                delete(owner)
                owner = None
                for process in workers:
                    self.assertTrue(process.closed)
                    self.assertTrue(process.wait_closed(10))
            finally:
                if owner is not None:
                    delete(owner)
                for process in workers:
                    process.close()
                    self.assertTrue(process.wait_closed(10))

    def test_close_cancels_process_without_blocking_or_late_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'old.started'
            worker = FeatureWorker(partial(_gated_analysis, started_path=str(marker)), name='findings-test')
            with patch('AgStudio.gui.analysis.FeatureWorker', side_effect=lambda calculation, *, name: (
                    worker if name == 'findings' else FeatureWorker(calculation, name=name))):
                controller = self.controller()
            published, failed = [], []
            controller.ready.connect(lambda *args: published.append(args))
            controller.failed.connect(lambda *args: failed.append(args))
            controller.request('old', 'current', immediate=True)
            self.wait_for(marker.exists)
            started = time.monotonic()
            controller.close()
            self.assertLess(time.monotonic() - started, 0.25)
            self.assertTrue(worker.wait_closed(10))
            controller._collect()
            self.assertFalse(published)
            self.assertFalse(failed)
            self.assertIsNone(controller.pending)
            self.assertIsNone(controller.analysis_snapshot)
            self.assertFalse(controller.poll.isActive())


if __name__ == '__main__':
    unittest.main()
