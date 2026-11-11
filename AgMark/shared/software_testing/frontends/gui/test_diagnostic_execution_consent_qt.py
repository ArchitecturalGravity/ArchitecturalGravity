"""Accepted-plan and queued-dispatch consent lifetime regressions, without providers."""

import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from AgMark.gui.application import BenchmarkDesktopApplication
from AgMark.gui.application.contracts import ApplicationProjectionUpdate
from AgMark.gui.application.session_boundary import PlanningSessionApplicationBoundary
from AgMark.gui.requests import ResolvedRunnerTestRequest
from AgMark.gui.shell.diagnostic_consent import DiagnosticConsentRequired
from AgMark.gui.shell.projections import CurrentRunProjection, ExecutionBoundaryProjection, RunPlanProjection
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef, ProviderRuntimeIdentity
from AgMark.shared.telemetry.profile import DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
from AgMark.shared.software_testing.frontends.gui.test_diagnostic_consent_qt import (
    projection, RUNNER, OTHER_RUNNER, SAFE, DIAGNOSTIC,
)


def boundary_document(profile=DIAGNOSTIC, runner=RUNNER):
    runner_id, runner_version = runner.split("@")
    return ExecutionBoundary.build(boundary_id="consent-fixture",
        framework=IdentityRef("fixture.framework", "1.0.0"),
        runner=IdentityRef(runner_id, runner_version),
        provider_runtime=ProviderRuntimeIdentity(runtime_id="fixture.runtime", runtime_version="1.0.0",
            provider=None, access_method="in_process", model="fixture"),
        controls={"capture_mode": profile,
                  "diagnostic_privacy_acknowledged": DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT})


class FakeBoundary:
    def __init__(self, profile=DIAGNOSTIC, runner=RUNNER):
        self.plan_request = SimpleNamespace(execution_boundary=boundary_document(profile, runner), extensions={})
        self.accepted_snapshot = object()
        self.starts = 0
        self.tests = 0

    def start_benchmark(self):
        self.starts += 1
        return object()

    def test_runner(self, intent):
        self.tests += 1
        return object()

    def discover(self): pass
    def build_plan(self, intent): pass
    def select_run(self, run_id): pass
    def delete_run(self, run_id): pass
    def accept_plan(self): pass
    def generate_report(self): pass
    def verify_reconstruction(self): pass


class DiagnosticExecutionConsentQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def application(self, *, profile=DIAGNOSTIC, accepted_runner=RUNNER):
        queue = []
        authority = FakeBoundary(profile, accepted_runner)
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.black)
        application = BenchmarkDesktopApplication(application_icon=QIcon(pixmap),
            shared_application_boundary=authority, initial_sidebar_projection=projection(), shell_preferences={},
            projector=lambda *_args: ApplicationProjectionUpdate(), authority_dispatcher=queue.append)
        application.window.set_current_run_projection(CurrentRunProjection(
            run_identity="accepted-fixture", state_label="Accepted", state_tone="success", timestamp="fixture",
            execution_boundary=ExecutionBoundaryProjection("Fixture", accepted_runner, "Fixture", "1", "fixture"),
            run_plan=RunPlanProjection("1", "1", "1", "Fixture", "Fixture"), start_benchmark_available=True))
        def cleanup():
            application.window.close()
            application.window.deleteLater()
            self.qt.processEvents()
        self.addCleanup(cleanup)
        return application, authority, queue

    def accept(self, window, *, save=False):
        window.additional_control_inputs["capture_mode"].set_value(DIAGNOSTIC)
        dialog = window._diagnostic_dialog
        dialog.save_decision.setChecked(save)
        dialog.accept_button.click()

    def work(self, queue):
        self.assertEqual(1, len(queue))
        thread = Thread(target=queue.pop())
        thread.start()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.qt.processEvents()

    def assert_blocked(self, application, authority):
        self.assertEqual(0, authority.starts)
        notice = getattr(application.window, "_diagnostic_dispatch_notice", None)
        if application.window._diagnostic_window_closed.is_set():
            self.assertTrue(notice is None or not notice.isVisible())
        else:
            self.assertIsNotNone(notice)
        self.assertIn("operation not started", application.window._requested_application_status[0])
        self.assertFalse(application._pending_commands)

    def test_close_dismisses_notice_and_late_failure_does_not_reopen_a_dialog(self):
        application, authority, queue = self.application()
        application.window.show()
        application.request_start_benchmark()
        self.assertIsNotNone(application.window._diagnostic_dispatch_notice)
        application.window.close()
        self.qt.processEvents()
        self.assertIsNone(application.window._diagnostic_dispatch_notice)
        application._apply_failure("start_benchmark", DiagnosticConsentRequired(), None)
        self.qt.processEvents()
        self.assertFalse(application.window.isVisible())
        self.assertIsNone(application.window._diagnostic_dispatch_notice)
        self.assertFalse(application._active_progress_timer.isActive())
        self.assertIsNone(application._active_progress_generation_id)
        self.assertEqual([], queue)
        self.assert_blocked(application, authority)

    def test_revoked_unsaved_accepted_plan_is_blocked_without_mutating_plan(self):
        application, authority, queue = self.application()
        self.accept(application.window)
        accepted = authority.plan_request
        fingerprint = accepted.execution_boundary.fingerprint
        application.window.additional_control_inputs["capture_mode"].set_value(SAFE)
        application.window.start_benchmark_button.click()
        self.assertEqual([], queue)
        self.assert_blocked(application, authority)
        self.assertIs(accepted, authority.plan_request)
        self.assertEqual(fingerprint, accepted.execution_boundary.fingerprint)

    def test_current_matching_grant_dispatches_without_worker_widget_or_settings_reads(self):
        application, authority, queue = self.application()
        self.accept(application.window)
        application.window.start_benchmark_button.click()
        with patch.object(application.window, "diagnostic_execution_grant", side_effect=AssertionError("GUI read in worker")), \
                patch.object(application.window._diagnostic_preferences, "remembers", side_effect=AssertionError("settings read in worker")):
            self.work(queue)
        self.assertEqual(1, authority.starts)

    def test_saved_matching_grant_authorizes_accepted_runner_even_when_sidebar_differs(self):
        application, authority, queue = self.application()
        self.accept(application.window, save=True)
        application.window.additional_control_inputs["capture_mode"].set_value(SAFE)
        application.window.runner_input.set_value(OTHER_RUNNER)
        application.window.start_benchmark_button.click()
        self.work(queue)
        self.assertEqual(1, authority.starts)

    def test_consent_for_another_runner_never_authorizes_accepted_plan(self):
        application, authority, queue = self.application(accepted_runner=OTHER_RUNNER)
        self.accept(application.window, save=True)
        application.window.start_benchmark_button.click()
        self.assertEqual([], queue)
        self.assert_blocked(application, authority)

    def test_queued_unsaved_grants_are_revoked_by_profile_runner_or_window_close(self):
        for revoke in ("profile", "runner", "close"):
            with self.subTest(revoke=revoke):
                application, authority, queue = self.application()
                self.accept(application.window)
                application.window.start_benchmark_button.click()
                if revoke == "profile":
                    application.window.additional_control_inputs["capture_mode"].set_value(SAFE)
                elif revoke == "runner":
                    application.window.runner_input.set_value(OTHER_RUNNER)
                else:
                    application.window.close()
                self.work(queue)
                self.assert_blocked(application, authority)

    def test_reaccepting_selection_does_not_revive_previously_queued_grant(self):
        application, authority, queue = self.application()
        self.accept(application.window)
        application.request_start_benchmark()
        application.window.additional_control_inputs["capture_mode"].set_value(SAFE)
        self.accept(application.window)
        self.work(queue)
        self.assert_blocked(application, authority)

    def test_changed_accepted_request_or_generation_blocks_queued_saved_grant(self):
        for changed in ("plan_request", "accepted_snapshot"):
            with self.subTest(changed=changed):
                application, authority, queue = self.application()
                self.accept(application.window, save=True)
                application.request_start_benchmark()
                replacement = (SimpleNamespace(execution_boundary=boundary_document(), extensions={})
                               if changed == "plan_request" else object())
                setattr(authority, changed, replacement)
                self.work(queue)
                self.assert_blocked(application, authority)

    def test_busy_repeated_start_does_not_queue_twice_and_ordinary_plan_is_unaffected(self):
        application, authority, queue = self.application(profile=SAFE)
        application.window.start_benchmark_button.click()
        application.window.start_benchmark_button.click()
        self.work(queue)
        self.assertEqual(1, authority.starts)
        self.assertIsNone(getattr(application.window, "_diagnostic_dispatch_notice", None))

    def test_stale_runner_test_intent_is_blocked_and_queued_test_rechecks_revocation(self):
        application, authority, queue = self.application()
        self.accept(application.window)
        intent = application.window.sidebar_input_snapshot()
        application.window.additional_control_inputs["capture_mode"].set_value(SAFE)
        application.request_test_runner(intent)
        self.assertEqual([], queue)
        self.assertEqual(0, authority.tests)
        application.window._diagnostic_dispatch_notice.accept()
        self.accept(application.window)
        application.request_test_runner(application.window.sidebar_input_snapshot())
        application.window.close()
        self.work(queue)
        self.assertEqual(0, authority.tests)
        self.assert_blocked(application, authority)

    def test_production_boundary_rechecks_after_execution_resolution(self):
        from AgMark.shared.software_testing.frontends.gui.test_application_lifecycle_qt import _session, _Resolver
        from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination
        application, _authority, _queue = self.application()
        self.accept(application.window)
        grant = application.window.diagnostic_execution_grant(RUNNER, DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            session, digest = _session()
            store = FilesystemArtifactStore(PublicationDestination.benchmark_owned(root / "evidence", benchmark_root=root))
            resolver = _Resolver(root=root, store=store, benchmark_sha256=digest, generation_id="consent-boundary")
            boundary = PlanningSessionApplicationBoundary(session=session, request_resolver=resolver)
            boundary.build_plan(application.window.sidebar_input_snapshot())
            boundary.accept_plan()
            original = resolver.resolve_execution_request
            def resolve(*args, **kwargs):
                result = original(*args, **kwargs)
                application.window._diagnostic_selection_revoked.set()
                return result
            with patch.object(resolver, "resolve_execution_request", side_effect=resolve), \
                    patch.object(session, "execute_accepted_run") as execute:
                with self.assertRaises(DiagnosticConsentRequired):
                    boundary.start_benchmark(before_execution=grant.require_valid)
                execute.assert_not_called()
                self.assertIsNone(boundary.execution_request)

    def test_production_runner_test_rechecks_after_readiness_resolution(self):
        application, _authority, _queue = self.application()
        self.accept(application.window)
        grant = application.window.diagnostic_execution_grant(RUNNER, DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT)
        intent = application.window.sidebar_input_snapshot()
        boundary = object.__new__(PlanningSessionApplicationBoundary)
        boundary._discovery = object()
        def resolve(*_args):
            application.window._diagnostic_selection_revoked.set()
            return ResolvedRunnerTestRequest(execution_boundary=boundary_document(), runner_registration={}, runner_transient_values=None)
        boundary._request_resolver = SimpleNamespace(resolve_runner_test_request=resolve)
        with patch("AgMark.gui.application.session_boundary._runner_test_factory") as factory:
            with self.assertRaises(DiagnosticConsentRequired):
                boundary.test_runner(intent, before_execution=grant.require_valid)
            factory.assert_not_called()

    def test_revocation_after_start_notification_restores_accepted_ui_and_rejects_late_events(self):
        from AgMark.shared.software_testing.frontends.gui.test_application_lifecycle_qt import _session, _Resolver
        from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            session, digest = _session()
            store = FilesystemArtifactStore(PublicationDestination.benchmark_owned(root / "evidence", benchmark_root=root))
            resolver = _Resolver(root=root, store=store, benchmark_sha256=digest, generation_id="consent-not-started")
            resolve_plan = resolver.resolve_plan_request
            def diagnostic_plan(*args):
                request = resolve_plan(*args)
                return replace(request, execution_boundary=boundary_document(runner="frontend.runner@1.0.0"))
            resolver.resolve_plan_request = diagnostic_plan
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.black)
            sidebar = replace(projection(), runner_options=("frontend.runner@1.0.0",), selected_runner="frontend.runner@1.0.0")
            application = BenchmarkDesktopApplication.from_planning_session(application_icon=QIcon(pixmap),
                session=session, request_resolver=resolver, shell_preferences={},
                initial_sidebar_projection=sidebar, authority_dispatcher=lambda operation: operation())
            self.addCleanup(application.window.deleteLater)
            application.window._on_sidebar_intent_changed = None
            self.accept(application.window)
            application._boundary.build_plan(application.window.sidebar_input_snapshot())
            snapshot = application._boundary.accept_plan()
            self.assertTrue(application.window._diagnostic_is_accepted(), repr(application.window.sidebar_input_snapshot()))
            self.assertEqual("frontend.runner@1.0.0", application.window.runner_input.value)
            approved_sidebar = replace(sidebar, additional_controls=tuple(
                replace(control, selected_value=DIAGNOSTIC if control.control_name == "capture_mode"
                        else DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT)
                for control in sidebar.additional_controls))
            started = []
            original_emit = application._emit_execution_started
            def notify(execution, plan):
                started.append((execution, plan))
                original_emit(execution, plan)
                self.qt.processEvents()
                self.assertTrue(application._active_progress_timer.isActive())
                self.assertEqual(execution.generation_id, application.window.console_widget.state.active_generation_id)
                application.window._diagnostic_selection_revoked.set()
            with patch.object(application._projector, "_sidebar", return_value=approved_sidebar), \
                    patch.object(application, "_emit_execution_started", side_effect=notify), \
                    patch.object(session, "execute_accepted_run") as execute:
                application.request_start_benchmark()
                self.qt.processEvents()
                execute.assert_not_called()
                self.assertEqual(1, len(started), repr(application._environment_projection))
                self.assertIs(snapshot, application._boundary.accepted_snapshot)
                self.assertIsNone(application._boundary.execution_request)
                self.assertNotIn("consent-not-started", application._boundary._artifact_stores)
                self.assertNotIn("consent-not-started", application._boundary._run_contexts)
                self.assertFalse(application._active_progress_timer.isActive())
                self.assertIsNone(application._active_progress_generation_id)
                self.assertIsNone(application.window.console_widget.state.active_generation_id)
                self.assertIsNone(application.window.workspace_projection_run_id)
                self.assertTrue(application.window.start_benchmark_button.isEnabled())
                self.assertIn("operation not started", application.window._requested_application_status[0])
                # A delayed producer notification cannot rebind abandoned console
                # state or remount a false running Progress view.
                original_emit(*started[0])
                application._gui_dispatcher.execution_started.emit(*started[0])
                self.qt.processEvents()
                self.assertFalse(application._active_progress_timer.isActive())
                self.assertIsNone(application.window.console_widget.state.active_generation_id)
                self.assertIsNone(application.window.workspace_projection_run_id)
                application._pending_commands.add("start_benchmark")
                application._boundary._execution_request = replace(started[0][0], generation_id="new-generation")
                application.window.console_widget.bind_generation("new-generation")
                original_emit(*started[0])
                application._gui_dispatcher.execution_started.emit(*started[0])
                self.qt.processEvents()
                self.assertFalse(application._active_progress_timer.isActive())
                self.assertEqual("new-generation", application.window.console_widget.state.active_generation_id)
                self.assertIsNone(application.window.workspace_projection_run_id)
                application._pending_commands.clear()
                application._boundary._execution_request = None
            application.window.close()


if __name__ == "__main__":
    unittest.main()
