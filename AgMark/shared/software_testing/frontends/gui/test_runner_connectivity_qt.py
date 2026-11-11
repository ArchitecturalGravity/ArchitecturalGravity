"""Selected-runner connection evidence and asynchronous refresh regressions."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from dataclasses import replace
from threading import Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace
import unittest

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from AgMark.gui.application import BenchmarkDesktopApplication
from AgMark.gui.application.contracts import ApplicationProjectionUpdate, RunnerTestResult
from AgMark.gui.composition import discover_repository_application_authority
from AgMark.gui.readiness import derive_runner_readiness
from AgMark.gui.shell.window import SidebarControlInputSnapshot, SidebarProjection


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_RUNNERS = ("runner-a@1", "runner-b@1")


def _sidebar(runner, status=("Connected", "success", "Runner handshake succeeded.")):
    return SidebarProjection(
        runner_options=_RUNNERS, selected_runner=runner,
        runner_connectivity=status,
        model_visible=False, credentials_visible=False,
    )


def _diagnostic_sidebar():
    runner = "third-party.example-runner@1"
    return SidebarProjection(
        runner_options=(runner,), selected_runner=runner, runner_test_supported=True,
        runner_connectivity=("Connected", "success", "Runner handshake succeeded."),
        model_visible=False, credentials_visible=False,
    )


class RunnerConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.release = Event()
        self.entered = Event()
        self.calls = []
        self.desktop = None

    def tearDown(self):
        self.release.set()
        if self.desktop is not None:
            self.wait_for(lambda: not self.desktop._sidebar_refresh_pending)
            self.desktop.window.close()
            self.app.processEvents()

    def wait_for(self, predicate):
        deadline = monotonic() + 4
        while not predicate() and monotonic() < deadline:
            self.app.processEvents()
            sleep(.005)
        self.assertTrue(predicate())

    def make_desktop(self, refresher, *, initial=None, diagnostic=None):
        names = ("discover", "build_plan", "select_run", "delete_run", "accept_plan",
                 "start_benchmark", "generate_report", "verify_reconstruction")
        boundary = SimpleNamespace(**{name: lambda *args: object() for name in names})
        if diagnostic is not None:
            boundary.test_runner = diagnostic
        self.desktop = BenchmarkDesktopApplication(
            application_icon=QIcon(QPixmap(16, 16)),
            shared_application_boundary=boundary,
            initial_sidebar_projection=initial or _sidebar(_RUNNERS[0]),
            projector=lambda *_: ApplicationProjectionUpdate(),
            sidebar_refresh_projector=refresher,
            sidebar_intent_projector=lambda intent: refresher(intent, intent.runner),
        )
        self.desktop.window.show()
        self.app.processEvents()
        return self.desktop

    def test_connection_refresh_is_background_and_publishes_selected_identity(self):
        def refresh(intent, runner):
            self.calls.append((runner, get_ident()))
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError("fixture watchdog")
            return _sidebar(runner)
        desktop = self.make_desktop(refresh)
        desktop._refresh_runner_selection(_RUNNERS[0])
        self.assertTrue(self.entered.wait(1))
        self.assertTrue(desktop._sidebar_refresh_pending)
        self.assertNotEqual(desktop.window.connectivity_status.tone, "success")
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        self.app.processEvents()
        self.assertTrue(heartbeat)
        self.assertNotEqual(self.calls[0][1], get_ident())
        self.release.set()
        self.wait_for(lambda: not desktop._sidebar_refresh_pending)
        self.assertEqual(desktop.window.connectivity_status.tone, "success")

    def test_older_connection_response_cannot_replace_new_runner(self):
        def refresh(intent, runner):
            if runner == _RUNNERS[0]:
                self.entered.set()
                if not self.release.wait(3):
                    raise RuntimeError("fixture watchdog")
                return _sidebar(runner)
            return _sidebar(runner, ("Runner unavailable", "error", "Selected runner refused handshake."))
        desktop = self.make_desktop(refresh)
        desktop._refresh_runner_selection(_RUNNERS[0])
        self.assertTrue(self.entered.wait(1))
        old_revision = desktop._sidebar_refresh_revision
        desktop._refresh_runner_selection(_RUNNERS[1])
        # Exercise delivery of an already-completed old result while B is pending.
        desktop._receive_sidebar_refresh(old_revision, _sidebar(_RUNNERS[0]), None, None)
        self.assertNotEqual(desktop.window.connectivity_status.tone, "success")
        self.release.set()
        self.wait_for(lambda: not desktop._sidebar_refresh_pending)
        self.assertEqual(desktop.window.connectivity_status.tone, "error")
        self.assertEqual(desktop.window.connectivity_status.displayed_label,
                         "Runner B: Runner unavailable")
        self.assertEqual(desktop.window.sidebar_input_snapshot().runner, _RUNNERS[1])

    def test_old_controls_during_runner_switch_use_switch_projection(self):
        switches = []
        normal_intents = []
        def refresh(intent, runner):
            switches.append((intent, runner))
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError("fixture watchdog")
            return _sidebar(runner)
        desktop = self.make_desktop(refresh)
        desktop._sidebar_intent_projector = lambda intent: normal_intents.append(intent)
        old_intent = desktop.window.sidebar_input_snapshot()
        desktop._refresh_runner_selection(_RUNNERS[1])
        self.assertTrue(self.entered.wait(1))
        stale_controls = replace(
            old_intent, runner=_RUNNERS[1],
            additional_controls=(SidebarControlInputSnapshot("codex_binary", "/old/runner-a"),),
        )
        desktop._refresh_sidebar_intent(stale_controls)
        self.release.set()
        self.wait_for(lambda: not desktop._sidebar_refresh_pending)
        self.assertEqual(normal_intents, [])
        self.assertEqual([runner for _, runner in switches], [_RUNNERS[1], _RUNNERS[1]])
        self.assertEqual(switches[-1][0], stale_controls)
        self.assertEqual(desktop.window.sidebar_input_snapshot().runner, _RUNNERS[1])

    def test_probe_exception_invalidates_success_and_manual_refresh_recovers(self):
        failed = True
        def refresh(intent, runner):
            if failed:
                raise RuntimeError("probe failed")
            return _sidebar(runner)
        desktop = self.make_desktop(refresh)
        desktop._refresh_runner_selection(_RUNNERS[0])
        self.wait_for(lambda: not desktop._sidebar_refresh_pending)
        self.assertNotEqual(desktop.window.connectivity_status.tone, "success")
        failed = False
        desktop.request_refresh_connectivity()
        self.wait_for(lambda: not desktop._sidebar_refresh_pending)
        self.assertEqual(desktop.window.connectivity_status.tone, "success")

    def test_no_runner_does_not_retain_connected_status(self):
        desktop = self.make_desktop(lambda intent, runner: _sidebar(runner))
        desktop.window.set_sidebar_projection(_sidebar(None))
        self.assertNotEqual(desktop.window.connectivity_status.tone, "success")
        self.assertIn("not selected", desktop.window.connectivity_status.label.lower())

    def test_check_button_refreshes_unresolved_runner_without_diagnostic(self):
        runner = "third-party.example-runner@1"
        initial = SidebarProjection(
            runner_options=(runner,), selected_runner=runner, runner_test_supported=True,
            model_visible=True, model_required=True, credentials_visible=False,
        )
        diagnostics = []
        def refresh(intent, selected):
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError("fixture watchdog")
            return replace(
                initial, model_options=("fixture-model",), selected_model="fixture-model",
                runner_connectivity=("Connected", "success", "Handshake succeeded."),
            )
        desktop = self.make_desktop(
            refresh, initial=initial,
            diagnostic=lambda *args, **kwargs: diagnostics.append(args) or object(),
        )
        self.assertIsNotNone(desktop.window.runner_test_action)
        self.assertFalse(desktop.window.runner_test_action.isEnabled())
        self.assertTrue(desktop.window.runner_check_action.isEnabled())
        desktop.window.runner_check_action.trigger()
        self.assertTrue(self.entered.wait(1))
        self.assertFalse(desktop.window.runner_check_action.isEnabled())
        self.assertEqual(diagnostics, [])
        self.release.set()
        self.wait_for(lambda: not desktop._sidebar_refresh_pending)
        self.assertEqual(diagnostics, [])
        self.assertEqual(desktop.window.connectivity_status.tone, "success")
        self.assertTrue(desktop.window.runner_test_action.isEnabled())
        desktop.window.runner_test_action.trigger()
        self.wait_for(lambda: not desktop._pending_commands)
        self.assertEqual(len(diagnostics), 1)

    def test_test_action_shows_active_then_passed_and_check_restores_handshake(self):
        initial = _diagnostic_sidebar()

        def diagnostic(intent):
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError("fixture watchdog")
            return RunnerTestResult(
                selected_runner=intent.runner,
                submitted=True, terminal_status="completed", response_preview="echo",
            )

        desktop = self.make_desktop(
            lambda intent, runner: initial, initial=initial, diagnostic=diagnostic,
        )
        self.assertTrue(desktop.window.runner_test_action.isEnabled())
        desktop.window.runner_test_action.trigger()
        self.assertTrue(self.entered.wait(1))
        self.assertEqual("Testing runner…", desktop.window.connectivity_status.label)
        self.assertEqual("active", desktop.window.connectivity_status.tone)
        self.assertFalse(desktop.window.runner_test_action.isEnabled())

        self.release.set()
        self.wait_for(lambda: not desktop._pending_commands)
        self.assertEqual("Test passed", desktop.window.connectivity_status.label)
        self.assertEqual("success", desktop.window.connectivity_status.tone)

        desktop.window.runner_check_action.trigger()
        self.wait_for(lambda: not desktop._sidebar_refresh_pending)
        self.assertEqual("Connected", desktop.window.connectivity_status.label)

    def test_test_failure_and_dispatch_error_update_button_without_leaking_exception(self):
        initial = _diagnostic_sidebar()
        attempts = []

        def diagnostic(intent):
            attempts.append(intent)
            if len(attempts) == 1:
                return RunnerTestResult(
                    selected_runner=intent.runner,
                    diagnostics=("Diagnostic response not retained.",),
                )
            raise RuntimeError("PRIVATE diagnostic path /sensitive/path")

        desktop = self.make_desktop(
            lambda intent, runner: initial, initial=initial, diagnostic=diagnostic,
        )
        desktop.window.runner_test_action.trigger()
        self.wait_for(lambda: not desktop._pending_commands)
        self.assertEqual("Test failed", desktop.window.connectivity_status.label)
        self.assertEqual("error", desktop.window.connectivity_status.tone)

        desktop.window.runner_test_action.trigger()
        self.wait_for(lambda: not desktop._pending_commands)
        self.assertEqual(2, len(attempts))
        self.assertEqual("Test failed", desktop.window.connectivity_status.label)
        self.assertEqual("error", desktop.window.connectivity_status.tone)

        desktop.window.set_sidebar_projection(_sidebar(None))
        self.assertEqual("Runner not selected", desktop.window.connectivity_status.label)

    def test_closed_window_ignores_late_connection_result(self):
        def refresh(intent, runner):
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError("fixture watchdog")
            return _sidebar(runner)
        desktop = self.make_desktop(refresh)
        desktop._refresh_runner_selection(_RUNNERS[0])
        self.assertTrue(self.entered.wait(1))
        revision = desktop._sidebar_refresh_revision
        before_close = desktop.window.connectivity_status.label
        desktop.window.close()
        self.app.processEvents()
        self.assertTrue(desktop._closed)
        desktop._receive_sidebar_refresh(revision, _sidebar(_RUNNERS[0]), None, None)
        self.assertEqual(desktop.window.connectivity_status.label, before_close)
        self.release.set()
        self.desktop = None

    def test_only_successful_validated_runner_response_reports_connected(self):
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        source = next(item for item in authority.runner_sources
                      if item.registration["registration_id"] == "arcgrav.mock-model.runner")
        discovered = next(item for item in authority.discovery.runners
                          if item.registration_id == source.registration["registration_id"])
        model = "mock-base::scenario:completed"
        ready = {
            "status": "ready", "provider_submitted": False,
            "effective_default_model_id": model, "selectable_model_ids": [model],
            "choices": [{"model_id": model, "selection_mode": "explicit", "label": "Mock",
                         "reasoning_efforts": [{"value": "medium", "description": "Default"}],
                         "default_reasoning_effort": "medium",
                         "scenario": {"model_id": model, "scenario_id": "completed",
                                      "label": "Completed", "base_model_id": "mock-base",
                                      "is_default": True}}],
            "resolved_configuration": {},
        }
        def unavailable(*args):
            raise OSError("runner unavailable")
        cases = (
            (lambda *args: ready, True),
            (lambda *args: {"status": "unsupported", "error_code": "runner_unavailable"}, False),
            (lambda *args: {"status": "ready", "provider_submitted": False}, False),
            (lambda *args: None, False),
            (unavailable, False),
        )
        for probe, connected in cases:
            with self.subTest(connected=connected, probe=probe):
                projection = derive_runner_readiness(
                    discovered_runner=discovered, runner_sources=authority.runner_sources,
                    executable_resolver=lambda name: name,
                    model_discovery_probe=probe,
                    selected_control_values={"launch_mode": "native"},
                )
                self.assertEqual(projection.runner_connectivity[1] == "success", connected)


if __name__ == "__main__":
    unittest.main()
