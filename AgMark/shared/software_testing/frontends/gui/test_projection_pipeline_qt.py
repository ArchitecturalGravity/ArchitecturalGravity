"""Slow retained evidence never owns Qt's thread or an unbounded refresh queue."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from dataclasses import replace
from threading import Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

from AgMark.gui.application import BenchmarkDesktopApplication
from AgMark.gui.application.contracts import ApplicationProjectionUpdate
from AgMark.gui.application.dispatch import _ProjectionWorker
from AgMark.gui.shell.window import WorkspaceProjection
from AgMark.gui.views.progress import ProgressView
from AgMark.gui.views.evidence import EvidenceProjection, EvidenceView
from AgMark.gui.views.artifacts import ArtifactsProjection
from AgMark.gui.views.results import ResultsProjection, ResultsView
from AgMark.shared.runtime.orchestration.activity import RunActivity
from AgMark.shared.software_testing.frontends.gui.test_retained_evidence_projection import _active_plan, _active_progress_projection


class ProjectionPipelineQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def wait(self, condition):
        deadline = monotonic() + 4
        while not condition() and monotonic() < deadline:
            self.qt.processEvents()
            sleep(.005)
        self.assertTrue(condition())

    def desktop(self, projector):
        names = ("discover", "build_plan", "select_run", "delete_run", "accept_plan",
                 "start_benchmark")
        boundary = SimpleNamespace(**{name: lambda *args: args[0] if args else "completed" for name in names})
        desktop = BenchmarkDesktopApplication(application_icon=QIcon(QPixmap(16, 16)),
            shared_application_boundary=boundary, projector=projector)
        desktop.window.show()
        self.addCleanup(desktop.window.deleteLater)
        self.addCleanup(desktop.window.close)
        return desktop

    def mount_active_progress(self, desktop):
        generation = "generation-preparing"
        progress = _active_progress_projection(generation, _active_plan())
        progress = replace(progress,
            overall=replace(progress.overall, completed_cases=progress.overall.total_cases))
        desktop.window.set_workspace_projection(self.workspace(progress), run_id=generation)
        desktop._active_progress_generation_id = generation
        desktop._activity_generation_id = generation
        desktop._active_progress_projection = progress
        desktop._active_progress_timer.start()
        return progress, desktop.window.workspace_pages["Progress"]

    def workspace(self, progress):
        return WorkspaceProjection(ProgressView(progress),
            ResultsView(ResultsProjection(progress.run_id, empty_state="Fixture results")),
            QLabel(), QLabel(), EvidenceView(EvidenceProjection(progress,
                ArtifactsProjection(progress.run_id, empty_state="Fixture artifacts"))))

    def test_terminal_execution_stays_below_complete_through_preparation_and_mount(self):
        execution_release, entered, release = Event(), Event(), Event()
        self.addCleanup(execution_release.set)
        self.addCleanup(release.set)
        owner = self
        class Projector:
            def prepare_result(self, command, result, commands):
                entered.set()
                if not release.wait(4):
                    raise RuntimeError("fixture preparation was not released")
                return replace(progress, run_active=False, lifecycle_complete=True)
            def __call__(self, command, result, commands, *, prepared=None):
                owner.assertLess(page.overall_ring.presentation.percent, 100)
                return ApplicationProjectionUpdate(workspace=owner.workspace(prepared),
                    workspace_run_id=prepared.run_id,
                    application_status=("Run available; saving history failed", "warning"))
        desktop = self.desktop(Projector())
        progress, page = self.mount_active_progress(desktop)
        def execute():
            desktop._queue_activity(RunActivity(progress.generation_id, 1, "completion", 120,
                terminal=True, finalization_complete=True, benchmark_outcome="complete"))
            if not execution_release.wait(4):
                raise RuntimeError("fixture execution was not released")
            return "terminal"
        desktop._boundary.start_benchmark = execute
        desktop.request_start_benchmark()
        self.wait(lambda: desktop._active_activity is not None)
        # The execution terminal event must not produce even one 100% frame.
        self.assertEqual(98, page.overall_ring.presentation.percent)
        self.assertTrue(page.projection.run_active)
        self.assertFalse(page.projection.lifecycle_complete)
        self.assertEqual("Benchmark: complete", page.projection.benchmark_status)
        self.assertFalse(page.stage_stepper.visually_complete)
        self.assertTrue(page.overall_bar.isHidden())
        old_epoch = desktop._active_projection_epoch
        desktop._active_projection_pending = (progress.generation_id, old_epoch)
        execution_release.set()
        self.wait(entered.is_set)
        self.assertTrue(desktop._active_progress_timer.isActive())
        self.assertIn("Preparing retained results and saving history", page.activity_label.text())
        self.assertFalse(page.activity_indicator.isHidden())
        self.assertEqual("Finalization", page.stage_description_card.title)
        self.assertEqual(page.projection,
            desktop.window.workspace_pages["Evidence"].projection.capture)
        with patch("AgMark.gui.application.desktop.active_retained_progress_projection",
                   side_effect=AssertionError("Evidence refreshed during preparation")), \
                patch("AgMark.gui.application.desktop.monotonic",
                      return_value=desktop._activity_received_at + 65):
            desktop._refresh_active_progress()
        self.assertEqual("03:05", page.projection.overall.elapsed_time)
        # A refresh queued before preparation cannot overwrite its progress.
        before = page.projection
        desktop._apply_active_projection(progress.generation_id, old_epoch,
            replace(progress, run_active=False, lifecycle_complete=True), None)
        self.assertIs(before, page.projection)
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        self.wait(lambda: bool(heartbeat))
        release.set()
        self.wait(lambda: not desktop._pending_commands)
        final_page = desktop.window.workspace_pages["Progress"]
        self.assertEqual(100, final_page.overall_ring.presentation.percent)
        self.assertTrue(final_page.stage_stepper.visually_complete)
        self.assertFalse(desktop._active_progress_timer.isActive())
        self.assertFalse(desktop._preparing_benchmark_results)
        self.assertEqual(("Run available; saving history failed", "warning"),
            desktop.window._requested_application_status)

    def test_preparation_failure_stops_busy_progress_without_changing_benchmark_outcome(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        class Projector:
            def prepare_result(self, *args):
                entered.set()
                release.wait(4)
                raise OSError("fixture preparation failed")
            def __call__(self, *args):
                raise AssertionError("failed preparation was applied")
        desktop = self.desktop(Projector())
        progress, page = self.mount_active_progress(desktop)
        desktop._active_progress_projection = replace(progress,
            benchmark_status="Benchmark: complete", evidence_status="Evidence sealed")
        desktop.request_start_benchmark()
        self.wait(entered.is_set)
        release.set()
        self.wait(lambda: not desktop._pending_commands)
        self.assertFalse(page.projection.run_active)
        self.assertFalse(page.projection.lifecycle_complete)
        self.assertFalse(desktop._active_progress_timer.isActive())
        self.assertTrue(page.activity_indicator.isHidden())
        self.assertLess(page.overall_ring.presentation.percent, 100)
        self.assertIn("failed", page.activity_label.text())
        self.assertEqual("Benchmark: complete", page.projection.benchmark_status)
        self.assertEqual("Evidence sealed", page.projection.evidence_status)

    def test_close_during_benchmark_preparation_drops_late_result(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        applied = []
        class Projector:
            def prepare_result(self, *args):
                entered.set()
                release.wait(4)
            def __call__(self, *args, **kwargs):
                applied.append(True)
                return ApplicationProjectionUpdate()
        desktop = self.desktop(Projector())
        self.mount_active_progress(desktop)
        desktop.request_start_benchmark()
        self.wait(entered.is_set)
        desktop.window.close()
        self.assertFalse(desktop._active_progress_timer.isActive())
        with patch("sys.excepthook") as errors:
            release.set()
            desktop._projection_worker._thread.join(2)
            self.qt.processEvents()
            errors.assert_not_called()
        self.assertFalse(applied)

    def test_terminal_preparation_keeps_gui_and_cancellation_responsive(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        worker_threads, rendered = [], []
        class Projector:
            def prepare_result(self, command, result, commands):
                worker_threads.append(get_ident())
                entered.set()
                if not release.wait(4):
                    raise RuntimeError("fixture was not released")
                return "prepared"
            def __call__(self, command, result, commands, *, prepared=None):
                rendered.append((get_ident(), prepared))
                return ApplicationProjectionUpdate()
        desktop = self.desktop(Projector())
        cancelled = []
        desktop._boundary.cancel_benchmark = lambda: cancelled.append(True)
        desktop.request_start_benchmark()
        self.wait(entered.is_set)
        self.assertIn("start_benchmark", desktop._pending_commands)
        self.assertIn("Preparing retained results", desktop.window.operation_label.text())
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        desktop.window.workspace_tabs.setCurrentIndex(1)
        desktop.request_cancel_benchmark()
        self.wait(lambda: bool(heartbeat))
        self.assertEqual([True], cancelled)
        self.assertFalse(rendered)
        self.assertNotEqual(get_ident(), worker_threads[0])
        release.set()
        self.wait(lambda: not desktop._pending_commands)
        self.assertEqual([(get_ident(), "prepared")], rendered)

    def test_new_selection_supersedes_inflight_preparation_and_close_drops_late_delivery(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        rendered = []
        class Projector:
            def prepare_result(self, command, result, commands):
                if result == "old":
                    entered.set()
                    release.wait(4)
                return result
            def __call__(self, command, result, commands, *, prepared=None):
                rendered.append(result)
                return ApplicationProjectionUpdate()
        desktop = self.desktop(Projector())
        desktop.request_select_run("old")
        self.wait(entered.is_set)
        actions = []
        self.assertIsNone(desktop.request_delete_run("old"))
        self.assertFalse(actions)
        self.assertIn("Loading selected run", desktop.window.operation_label.text())
        desktop.request_select_run("new")
        self.qt.processEvents()
        release.set()
        self.wait(lambda: rendered == ["new"])
        self.assertFalse(desktop._selecting_run)
        entered.clear(); release.clear()
        desktop.request_select_run("old")
        self.wait(entered.is_set)
        desktop.window.close()
        with patch("sys.excepthook") as errors:
            release.set()
            desktop._projection_worker._thread.join(2)
            self.qt.processEvents()
            errors.assert_not_called()
        self.assertEqual(["new"], rendered)

    def test_close_preserves_started_authority_without_claiming_it_never_started(self):
        entered, release, completed = Event(), Event(), Event()
        self.addCleanup(release.set)
        rendered = []
        desktop = self.desktop(lambda *_: (rendered.append(True), ApplicationProjectionUpdate())[1])
        def execute():
            entered.set()
            release.wait(4)
            completed.set()
            return "completed"
        desktop._boundary.start_benchmark = execute
        desktop.window.set_application_status("Fixture execution active", "warning")
        worker = desktop.request_start_benchmark()
        self.wait(entered.is_set)
        desktop.window.close()
        self.assertEqual("Fixture execution active", desktop.window._requested_application_status[0])
        release.set()
        worker.join(2)
        self.qt.processEvents()
        self.assertTrue(completed.is_set())
        self.assertFalse(worker.is_alive())
        self.assertFalse(rendered)
        self.assertFalse(desktop._pending_commands)

    def test_active_work_is_coalesced_and_old_generation_cannot_overwrite_new(self):
        desktop = self.desktop(lambda *_: ApplicationProjectionUpdate())
        generation = "generation-pipeline"
        plan = _active_plan()
        progress = _active_progress_projection(generation, plan)
        page = ProgressView(progress)
        result_page = ResultsView(ResultsProjection(generation, empty_state="Waiting for retained observations."))
        desktop.window.set_workspace_projection(WorkspaceProjection(page, result_page, QLabel(), QLabel(), EvidenceView(EvidenceProjection(progress, ArtifactsProjection(generation, empty_state="Waiting")))), run_id=generation)
        capture_page = desktop.window.workspace_pages["Evidence"]
        desktop._active_progress_generation_id = generation
        desktop._active_progress_plan = plan
        desktop._active_progress_store = object()
        desktop._active_progress_projection = progress
        desktop._pending_commands.add("start_benchmark")
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        calls = []
        def reconstruct(*_):
            calls.append(get_ident()); entered.set(); release.wait(4)
            return ResultsProjection(generation, empty_state="Waiting for retained observations.")
        with patch("AgMark.gui.application.desktop.active_retained_progress_projection", return_value=progress), \
                patch("AgMark.gui.projection.workspace.activity.with_retained_activity", side_effect=lambda value, _: value), \
                patch("AgMark.gui.projection.workspace.results.active_results_projection", side_effect=reconstruct):
            desktop._refresh_active_progress()
            self.wait(entered.is_set)
            for _ in range(100):
                desktop._refresh_active_progress()
            self.assertEqual(1, len(calls))
            self.assertEqual(page.projection, capture_page.projection.capture)
            self.assertNotEqual(get_ident(), calls[0])
            notifications = []
            desktop._gui_dispatcher.activity_ready.connect(notifications.append)
            # Publish from a worker, as the real collector does, without pumping Qt.
            from threading import Thread
            def burst():
                for n in range(1, 1001):
                    desktop._queue_activity(RunActivity(generation, n, "execution", 1))
                desktop._queue_activity(RunActivity("generation-retired", 9999, "execution", 1))
            thread = Thread(target=burst)
            thread.start(); thread.join()
            self.wait(lambda: len(notifications) == 1)
            self.assertEqual(1000, notifications[0].sequence)
            self.assertEqual(1000, desktop._active_activity.sequence)
            desktop._stop_active_progress_poll()
            before = result_page.projection
            release.set()
            self.wait(lambda: not desktop._projection_worker._pending)
            desktop._projection_worker.close()
            desktop._projection_worker._thread.join(2)
            self.qt.processEvents()
            self.assertIs(before, result_page.projection)

    def test_pending_projection_replacements_are_bounded_and_terminal_has_priority(self):
        worker = _ProjectionWorker()
        self.addCleanup(worker.close)
        entered, release, done = Event(), Event(), Event()
        self.addCleanup(release.set)
        received = []
        worker.submit("active", lambda: (entered.set(), release.wait(4)))
        self.assertTrue(entered.wait(2))
        for index in range(1000):
            worker.submit("active", lambda index=index: received.append(index))
        self.assertEqual(1, len(worker._pending))
        worker.submit("result:start_benchmark", lambda: (received.append("terminal"), done.set()), priority=True)
        self.assertEqual(["result:start_benchmark"], list(worker._pending))
        release.set()
        self.assertTrue(done.wait(2))
        self.assertEqual(["terminal"], received)

    def test_slow_selection_authority_is_serial_and_only_latest_pending_choice_runs(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        selected, rendered = [], []
        desktop = self.desktop(lambda command, result, _: (rendered.append(result), ApplicationProjectionUpdate())[1])
        def select(identity):
            if identity == "old":
                entered.set(); release.wait(4)
            selected.append(identity)
            desktop._boundary.selected_terminal = identity
            return identity
        desktop._boundary.select_run = select
        desktop.request_select_run("old")
        self.wait(entered.is_set)
        for index in range(100):
            desktop.request_select_run(str(index))
        self.assertEqual(1, len(desktop._selection_worker._pending))
        release.set()
        self.wait(lambda: rendered == ["99"])
        self.assertEqual(["old", "99"], selected)
        self.assertEqual("99", desktop._boundary.selected_terminal)

    def test_priority_preparation_invalidates_dropped_active_refresh_token(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        class Projector:
            def prepare_result(self, *args):
                entered.set(); release.wait(4)
            def __call__(self, *args):
                return ApplicationProjectionUpdate()
        desktop = self.desktop(Projector())
        desktop._active_projection_epoch = 7
        desktop._active_projection_pending = ("generation-active", 7)
        desktop._command_revisions["start_benchmark"] = 1
        desktop._receive_result("start_benchmark", object(), 1, desktop._workspace_revision)
        self.wait(entered.is_set)
        self.assertIsNone(desktop._active_projection_pending)
        self.assertEqual(8, desktop._active_projection_epoch)
        release.set()
        desktop._projection_worker.close()
        desktop._projection_worker._thread.join(2)
