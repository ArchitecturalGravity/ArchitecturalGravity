"""Worker-only run-archive preparation and GUI rendering regressions."""

import json
import os
import gc
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, ExitStack
from dataclasses import fields
from tempfile import TemporaryDirectory
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget

from AgMark.gui.application import history
from AgMark.gui.application import projector as application_projector
from AgMark.gui.application.projector import SharedApplicationProjector
from AgMark.gui.application.session_boundary import PlanningSessionApplicationBoundary
from AgMark.gui.projection.workspace import projector as workspace_module
from AgMark.gui.projection.workspace.projector import WorkspaceData, render_workspace
from AgMark.gui.views.results import ResultRowProjection, ResultsProjection
from AgMark.shared.software_testing.frontends.gui.test_retained_evidence_projection import _accepted_run
from AgMark.shared.software_testing.frontends.gui.test_run_history import RunHistoryTests
from AgMark.shared.runtime.artifacts.archive import validate_archive, archive_path
from AgMark.shared.runtime.orchestration import ExecutedRun


class PreparedWorkspaceQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        fixture = RunHistoryTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.repo = fixture.repo
        self.root = fixture.root
        self.generation = fixture.gid
        self.observation = fixture.observation
        self.run = history.discover_history(self.repo)[self.generation]
        self.gui_thread = get_ident()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(self.pool.shutdown)
        self.commands = SimpleNamespace()

    def worker(self, operation):
        return self.pool.submit(operation).result(timeout=15)

    def view_construction(self, stack):
        observed = []
        for name in ("ProgressView", "ResultsView", "ReportsView", "VerificationView", "EvidenceView"):
            original = getattr(workspace_module, name)
            def construct(*args, original=original, **kwargs):
                observed.append(get_ident())
                self.assertEqual(self.gui_thread, get_ident(), "QWidget constructed on worker")
                widget = original(*args, **kwargs)
                self.addCleanup(widget.deleteLater)
                return widget
            stack.enter_context(patch.object(workspace_module, name, side_effect=construct))
        return observed

    def boundary(self, terminal=None):
        boundary = object.__new__(PlanningSessionApplicationBoundary)
        boundary._history_enabled = True
        boundary.history_diagnostics = ["existing GUI diagnostic"]
        boundary._selected_terminal = terminal
        boundary._terminal_runs = {} if terminal is None else {terminal.generation_id: terminal}
        boundary._artifact_stores = {self.generation: SimpleNamespace(root=self.root)}
        boundary._run_contexts = {}
        boundary._report_bundles = {}
        boundary._report_requests = {}
        boundary._verifications = {}
        boundary._report_states = {}
        boundary._export_feedback = {}
        boundary._history = {self.generation: self.run}
        boundary._discovery = None
        boundary._session = SimpleNamespace(prepared_plan=None)
        boundary._plan_request = None
        boundary._accepted_snapshot = None
        boundary._execution_request = None
        return boundary

    def test_workspace_read_scope_preserves_optional_store_and_unavailable_paths(self):
        with workspace_module._workspace_verified_reads(SimpleNamespace(root=self.root), self.generation):
            pass
        events = []

        @contextmanager
        def rejected(_generation):
            events.append("admission rejected")
            raise ValueError("archive integrity differs")
            yield

        with workspace_module._workspace_verified_reads(
                SimpleNamespace(verified_reads=rejected), self.generation):
            events.append("render unavailable diagnostics")
        self.assertEqual(["admission rejected", "render unavailable diagnostics"], events)

    def test_workspace_read_scope_does_not_hide_drift_during_operation(self):
        @contextmanager
        def changed(_generation):
            yield
            raise ValueError("archive changed during operation")

        with self.assertRaisesRegex(ValueError, "changed during operation"):
            with workspace_module._workspace_verified_reads(
                    SimpleNamespace(verified_reads=changed), self.generation):
                pass

    def test_archive_history_validation_and_projection_off_gui(self):
        io_threads = []
        from AgMark.shared.runtime.artifacts import archive
        original_read = archive.read_archive_member
        def read(*args):
            io_threads.append(get_ident())
            return original_read(*args)
        with ExitStack() as stack:
            constructions = self.view_construction(stack)
            stack.enter_context(patch.object(archive, "read_archive_member", side_effect=read))
            current, data = self.worker(self.run.prepare_presentation)
            self.assertIsInstance(data, WorkspaceData)
            self.worker(lambda: history.save_presentation(self.root, self.generation, current, data))
            saved_current, saved_data = self.worker(self.run.prepare_presentation)
            self.assertEqual(current, saved_current)
            self.assertTrue(io_threads)
            self.assertTrue(all(thread != self.gui_thread for thread in io_threads))
            self.assertEqual([], constructions)
        with ExitStack() as stack:
            constructions = self.view_construction(stack)
            stack.enter_context(patch.object(history, "read_archive_member",
                                             side_effect=AssertionError("GUI performed disk IO")))
            workspace = render_workspace(saved_data)
            self.assertIsInstance(workspace.results, QWidget)
            self.assertEqual([self.gui_thread] * 5, constructions)

    def test_corrupt_archived_evidence_is_rejected_in_worker_without_fallback(self):
        with ZipFile(archive_path(self.root, self.generation), "a") as bundle:
            bundle.writestr("unexpected.txt", "tampered")
        with ExitStack() as stack:
            constructions = self.view_construction(stack)
            with self.assertRaises(ValueError):
                self.worker(self.run.prepare_presentation)
            self.assertEqual([], constructions)

    def test_transient_result_cache_is_never_encoded_or_decoded_from_disk(self):
        data = ResultsProjection(self.generation,
            (ResultRowProjection("one", 0.5, "fixture", "Scored", "✓"),))
        self.assertTrue(next(field for field in fields(data)
                             if field.name == "_presentation").metadata["transient"])
        encoded = history._encode(data)
        self.assertNotIn("_presentation", encoded["fields"])
        encoded["fields"]["_presentation"] = {
            "type": "UntrustedUnknownType", "fields": {"bad": object()},
        }
        decoded = self.worker(lambda: history._decode(encoded))
        self.assertEqual(history._encode(data), history._encode(decoded))

    def test_terminal_preparation_saves_archive_snapshot_off_gui(self):
        terminal = _accepted_run(observations=(self.observation,), generation_id=self.generation)
        boundary = self.boundary(terminal)
        projector = SharedApplicationProjector(boundary)
        current, _ = self.worker(self.run.prepare_presentation)
        save_threads = []
        original_save = history.save_presentation
        def save(*args, **kwargs):
            save_threads.append(get_ident())
            return original_save(*args, **kwargs)
        with ExitStack() as stack:
            constructions = self.view_construction(stack)
            stack.enter_context(patch.object(projector, "_prior_run", return_value=current))
            stack.enter_context(patch.object(history, "save_presentation", side_effect=save))
            prepared = self.worker(lambda: projector.prepare_result(
                "start_benchmark", terminal, self.commands))
            self.assertEqual([], constructions)
            self.assertTrue(save_threads)
            self.assertTrue(all(t != self.gui_thread for t in save_threads))
            self.assertNotIn("history/presentation.json",
                validate_archive(archive_path(self.root, self.generation))["files"])
        with ExitStack() as stack:
            constructions = self.view_construction(stack)
            stack.enter_context(patch.object(projector, "_environment_update",
                                             side_effect=lambda _sidebar, status: (None, status)))
            stack.enter_context(patch.object(history, "save_presentation",
                                             side_effect=AssertionError("GUI persisted history")))
            update = projector("start_benchmark", terminal, self.commands, prepared=prepared)
            self.assertEqual(self.generation, update.workspace_run_id)
            self.assertEqual([self.gui_thread] * 5, constructions)

    def test_history_prepare_apply_never_revalidates(self):
        boundary = self.boundary()
        projector = SharedApplicationProjector(boundary)
        prepared = self.worker(lambda: projector.prepare_result(
            "select_run", self.run, self.commands))
        with ExitStack() as stack:
            self.view_construction(stack)
            stack.enter_context(patch.object(history, "read_archive_member",
                                             side_effect=AssertionError("GUI read archive")))
            update = projector("select_run", self.run, self.commands, prepared=prepared)
            self.assertEqual(self.generation, update.workspace_run_id)
            self.assertTrue(update.current_run.is_prior_run)

    def test_archive_history_save_failure_is_explicit(self):
        terminal = _accepted_run(observations=(self.observation,), generation_id=self.generation)
        boundary = self.boundary(terminal)
        projector = SharedApplicationProjector(boundary)
        current, _ = self.worker(self.run.prepare_presentation)
        with patch.object(projector, "_prior_run", return_value=current), \
             patch.object(history, "save_presentation", side_effect=OSError("fixture disk full")):
            prepared = self.worker(lambda: projector.prepare_result(
                "start_benchmark", terminal, self.commands))
        self.assertIn("Run history could not be saved", prepared.history_diagnostics[0])
        self.assertNotIn("fixture disk full", prepared.history_diagnostics[0])
    def _executed_terminal(self, status="completed"):
        terminal = object.__new__(ExecutedRun)
        for name, value in (("generation_id", self.generation), ("cancelled", False),
                ("treatment_observations", (json.dumps({"terminal_status": status,
                    "fixture": "large retained evidence " * 10000}).encode(),))):
            object.__setattr__(terminal, name, value)
        return terminal

    def test_executed_terminal_labels_are_prepared_once_off_gui_for_all_retained_runs(self):
        first, second = self._executed_terminal(), self._executed_terminal("failed")
        object.__setattr__(second, "generation_id", "generation-other-terminal")
        boundary = self.boundary(first)
        boundary._terminal_runs["other-retained-key"] = second
        projector = SharedApplicationProjector(boundary)
        projector._workspace_projector = SimpleNamespace(prepare_result=lambda *_: None, render=lambda value: value)
        threads = []
        original_loads = application_projector.json.loads
        def loads(*args, **kwargs):
            threads.append(get_ident())
            return original_loads(*args, **kwargs)
        with patch.object(application_projector.json, "loads", side_effect=loads):
            self.worker(lambda: projector.prepare_result("select_run", first, self.commands))
        self.assertEqual(2, len(threads))
        self.assertTrue(all(thread != self.gui_thread for thread in threads))
        boundary._discovery = SimpleNamespace(benchmarks=(), runners=())
        with patch.object(application_projector.json, "loads", side_effect=AssertionError("GUI parsed terminal observations")):
            self.assertEqual(("Completed", "success"), application_projector._terminal_state(first))
            self.assertEqual(("Completed with errors", "warning"), application_projector._terminal_state(second))
            sidebar = projector._sidebar()
            self.assertEqual(["Completed", "Completed with errors"], [run.state_label for run in sidebar.runs[:2]])

    def test_terminal_state_cache_is_identity_scoped_and_releases_authority(self):
        first, replacement = self._executed_terminal(), self._executed_terminal("timed_out")
        key = id(first)
        self.assertEqual(("Completed", "success"), self.worker(lambda: application_projector._terminal_state(first)))
        self.assertEqual(("Completed with errors", "warning"), self.worker(lambda: application_projector._terminal_state(replacement)))
        self.assertIn(key, application_projector._EXECUTED_TERMINAL_STATES)
        del first
        gc.collect()
        self.assertNotIn(key, application_projector._EXECUTED_TERMINAL_STATES)

    def test_terminal_current_run_skips_inapplicable_readiness_probes(self):
        terminal = self._executed_terminal()
        boundary = self.boundary(terminal)
        current, _data = self.worker(self.run.prepare_presentation)
        plan = SimpleNamespace(run_plan_id="fixture-plan")
        request = SimpleNamespace(extensions={})
        boundary._session = SimpleNamespace(prepared_plan=plan)
        boundary._plan_request = request
        boundary._execution_request = SimpleNamespace(generation_id=self.generation)
        boundary._run_contexts[self.generation] = SimpleNamespace(
            plan=plan, plan_request=request, accepted_at="fixture-time")
        projector = SharedApplicationProjector(boundary)
        self.worker(lambda: application_projector._terminal_state(terminal))
        with patch.object(projector, "prerequisite_projection", side_effect=AssertionError("Terminal state cannot accept or start")), \
                patch.object(projector, "_plan_summary", return_value=(current.execution_boundary, current.run_plan)), \
                patch.object(application_projector.json, "loads", side_effect=AssertionError("GUI parsed observations")):
            projected = projector._current_run(terminal)
            self.assertEqual("Completed", projected.state_label)
            self.assertFalse(projected.accept_plan_available)
            self.assertFalse(projected.start_benchmark_available)


if __name__ == "__main__":
    unittest.main()
