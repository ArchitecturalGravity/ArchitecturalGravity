"""Real offline modal consent, UI preference and asynchronous state regressions."""

import json
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from AgMark.gui.shell.diagnostic_consent import consent_identity, consent_key
from AgMark.shared.telemetry.profile import DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
from AgMark.gui.shell.window import (
    BenchmarkShellWindow, SidebarChoiceControlProjection, SidebarControlInputSnapshot, SidebarProjection,
)

RUNNER = "openai.codex-cli@1.0.0"
OTHER_RUNNER = "openai.codex-cli@2.0.0"
SAFE = "telemetry"
DIAGNOSTIC = "deep_telemetry"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]


def projection(*, profile=SAFE, acknowledgement="not_acknowledged", runner=RUNNER, available=True):
    return SidebarProjection(
        runner_options=(RUNNER, OTHER_RUNNER), selected_runner=runner, runner_test_supported=True,
        build_plan_available=available,
        additional_controls=(
            SidebarChoiceControlProjection("capture_mode", "Capture Mode",
                ("session", SAFE, DIAGNOSTIC), profile),
            SidebarChoiceControlProjection("diagnostic_privacy_acknowledged", "Diagnostic privacy",
                ("not_acknowledged", DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT), acknowledgement),
        ),
    )


class DiagnosticConsentQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, *, preferences=None, native_preferences=False, sidebar=None, **kwargs):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.black)
        window = BenchmarkShellWindow(
            application_icon=QIcon(pixmap),
            shell_preferences=None if native_preferences else ({} if preferences is None else preferences),
            sidebar_projection=sidebar or projection(),
            on_build_plan=kwargs.pop("on_build_plan", lambda _: None), **kwargs,
        )
        def cleanup():
            window.close()
            window.deleteLater()
            self.app.processEvents()
        self.addCleanup(cleanup)
        return window

    def controls(self, window):
        return {item.control_name: item.value for item in window.sidebar_input_snapshot().additional_controls}

    def choose(self, window):
        window.additional_control_inputs["capture_mode"].set_value(DIAGNOSTIC)
        self.app.processEvents()
        return window._diagnostic_dialog

    def assert_safe(self, window, *, profile=SAFE):
        self.assertEqual(profile, self.controls(window)["capture_mode"])
        self.assertEqual("not_acknowledged", self.controls(window)["diagnostic_privacy_acknowledged"])

    def assert_accepted(self, window):
        self.assertEqual(DIAGNOSTIC, self.controls(window)["capture_mode"])
        self.assertEqual(DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT, self.controls(window)["diagnostic_privacy_acknowledged"])
        self.assertTrue(window._required_additional_controls_resolved())

    def test_explicit_modal_disclosure_without_default_accept_or_save(self):
        window = self.window()
        window.show()
        dialog = self.choose(window)
        self.assertIs(self.app.activeModalWidget(), dialog)
        self.assertTrue(dialog.isModal())
        self.assertFalse(dialog.save_decision.isChecked())
        self.assertFalse(dialog.accept_button.isDefault())
        self.assertFalse(dialog.accept_button.autoDefault())
        self.assertTrue(dialog.cancel_button.isDefault())
        self.assert_safe(window)
        self.assertTrue(window.additional_control_inputs["diagnostic_privacy_acknowledged"].isHidden())
        self.assertIsNone(window.findChild(QLabel, "diagnosticPrivacyNotice"))
        text = " ".join(label.text() for label in dialog.findChildren(QLabel))
        for phrase in ("private temporary", "inside WSL", "Payload text may contain secrets",
                       "no encryption guarantee", "local trace reducer", "sanitized structural",
                       "best-effort", "crash", "external telemetry", "inference-call header",
                       "Selecting another Capture Mode or runner ends it"):
            self.assertIn(phrase, text)
        dialog.accept_button.click()
        self.assert_accepted(window)

    def test_decline_close_escape_and_default_enter_preserve_prior_profile(self):
        preferences = {}
        for action in ("decline", "close", "escape", "enter"):
            with self.subTest(action=action):
                window = self.window(preferences=preferences, sidebar=projection(profile="session"))
                window.show()
                dialog = self.choose(window)
                dialog.save_decision.setChecked(True)
                if action == "decline":
                    dialog.cancel_button.click()
                elif action == "close":
                    dialog.close()
                elif action == "escape":
                    QTest.keyClick(dialog, Qt.Key.Key_Escape)
                else:
                    QTest.keyClick(dialog, Qt.Key.Key_Return)
                self.assertIsNone(window._diagnostic_dialog)
                self.assert_safe(window, profile="session")
        self.assertFalse(any(key.startswith("privacy/") for key in preferences))

    def test_unsaved_acceptance_survives_passive_refresh_but_not_reselection(self):
        preferences = {}
        window = self.window(preferences=preferences)
        self.choose(window).accept_button.click()
        self.assert_accepted(window)
        window.set_sidebar_projection(projection(profile=DIAGNOSTIC, acknowledgement=DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT))
        self.assert_accepted(window)
        self.assertIsNone(window._diagnostic_dialog)
        # Selecting an unchanged combo value emits no additional consent dialog.
        window.additional_control_inputs["capture_mode"].set_value(DIAGNOSTIC)
        self.assertIsNone(window._diagnostic_dialog)
        window.additional_control_inputs["capture_mode"].set_value(SAFE)
        self.assert_safe(window)
        self.assertIsNotNone(self.choose(window))
        self.assertFalse(any(key.startswith("privacy/") for key in preferences))

    def test_unsaved_consent_does_not_survive_window_close_or_new_window(self):
        preferences = {}
        first = self.window(preferences=preferences)
        self.choose(first).accept_button.click()
        first.close()
        self.assert_safe(first)
        self.assertIsNotNone(self.choose(first))
        first._diagnostic_dialog.reject()
        second = self.window(preferences=preferences,
            sidebar=projection(profile=DIAGNOSTIC, acknowledgement=DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT))
        self.assert_safe(second)
        self.assertIsNotNone(self.choose(second))

    def test_saved_affirmative_decision_survives_reselection_and_restart(self):
        preferences = {}
        first = self.window(preferences=preferences)
        dialog = self.choose(first)
        dialog.save_decision.setChecked(True)
        dialog.accept_button.click()
        expected = consent_identity(RUNNER)
        self.assertEqual(expected, json.loads(preferences[consent_key(expected)]))
        first.additional_control_inputs["capture_mode"].set_value(SAFE)
        self.assertIsNone(self.choose(first))
        self.assert_accepted(first)
        first.close()
        second = self.window(preferences=preferences)
        self.assertIsNone(self.choose(second))
        self.assert_accepted(second)
        self.assertEqual({"capture_mode", "diagnostic_privacy_acknowledged"}, set(self.controls(second)))

    def test_native_qsettings_saved_decision_materializes_and_reloads(self):
        with TemporaryDirectory() as temporary:
            path = str(Path(temporary) / "ui-preferences.ini")
            def settings(*_args):
                return QSettings(path, QSettings.Format.IniFormat)
            with patch("PySide6.QtCore.QSettings", side_effect=settings):
                first = self.window(native_preferences=True)
                dialog = self.choose(first)
                dialog.save_decision.setChecked(True)
                dialog.accept_button.click()
                self.assertTrue(Path(path).is_file())
                first.close()
                second = self.window(native_preferences=True)
                self.assertIsNone(self.choose(second))
                self.assert_accepted(second)

    def test_saved_consent_reprompts_for_new_version_scope_runner_and_corrupt_record(self):
        identity = consent_identity(RUNNER)
        preferences = {consent_key(identity): json.dumps(identity)}
        for constant in ("DIAGNOSTIC_CONSENT_VERSION", "DIAGNOSTIC_CONSENT_SCOPE"):
            with self.subTest(constant=constant), patch("AgMark.gui.shell.diagnostic_consent." + constant, "changed"):
                window = self.window(preferences=preferences)
                self.assertIsNotNone(self.choose(window))
                window._diagnostic_dialog.reject()
        window = self.window(preferences=preferences, sidebar=projection(runner=OTHER_RUNNER))
        self.assertIsNotNone(self.choose(window))
        window._diagnostic_dialog.reject()
        for invalid in (True, "true", "{broken", json.dumps({**identity, "decision": "declined"})):
            preferences[consent_key(identity)] = invalid
            window = self.window(preferences=preferences)
            self.assertIsNotNone(self.choose(window))
            window._diagnostic_dialog.reject()

    def test_runner_switch_revokes_unsaved_consent(self):
        window = self.window()
        self.choose(window).accept_button.click()
        window.runner_input.set_value(OTHER_RUNNER)
        self.assert_safe(window)
        dialog = self.choose(window)
        self.assertIn(OTHER_RUNNER, dialog.findChild(QLabel, "diagnosticConsentScope").text())
        dialog.cancel_button.click()
        window.runner_input.set_value(RUNNER)
        self.assertIsNotNone(self.choose(window))

    def test_repeated_pending_selection_does_not_create_extra_dialogs(self):
        window = self.window()
        first = self.choose(window)
        second = self.choose(window)
        self.assertIs(first, second)
        self.assert_safe(window)
        first.accept_button.click()
        self.assert_accepted(window)

    def test_refresh_invalidates_stale_dialog_accept_and_persistence(self):
        preferences = {}
        window = self.window(preferences=preferences)
        old_control = window.additional_control_inputs["capture_mode"]
        dialog = self.choose(window)
        dialog.save_decision.setChecked(True)
        window.set_sidebar_projection(projection(runner=OTHER_RUNNER))
        dialog.finished.emit(dialog.DialogCode.Accepted)
        old_control.set_value("session")
        self.assert_safe(window)
        self.assertIsNone(window._diagnostic_dialog)
        self.assertFalse(any(key.startswith("privacy/") for key in preferences))

    def test_busy_state_dismisses_and_rejects_pending_or_programmatic_selection(self):
        preferences = {}
        window = self.window(preferences=preferences)
        dialog = self.choose(window)
        dialog.save_decision.setChecked(True)
        window.set_operation_activity(("Running",), lock_controls=True)
        dialog.finished.emit(dialog.DialogCode.Accepted)
        self.assert_safe(window)
        self.assertIsNone(self.choose(window))
        self.assert_safe(window)
        self.assertFalse(any(key.startswith("privacy/") for key in preferences))
        window.set_operation_activity((), lock_controls=False)
        self.assertIsNotNone(self.choose(window))

    def test_unavailable_profile_and_missing_runner_do_not_enable_diagnostics(self):
        window = self.window()
        window.additional_control_inputs["capture_mode"].setEnabled(False)
        self.assertIsNone(self.choose(window))
        self.assert_safe(window)
        window = self.window(sidebar=projection(runner=None))
        self.assertIsNone(self.choose(window))
        self.assert_safe(window)
        window = self.window(sidebar=replace(projection(), additional_controls=projection().additional_controls[:1]))
        self.assertIsNone(self.choose(window))
        self.assertEqual(SAFE, self.controls(window)["capture_mode"])

    def test_readiness_and_plan_receive_only_accepted_registered_controls(self):
        plans, readiness, intents = [], [], []
        window = self.window(on_build_plan=plans.append, on_test_runner=readiness.append,
                             on_sidebar_intent_changed=intents.append)
        dialog = self.choose(window)
        window._invoke_build_plan()
        window._invoke_test_runner()
        self.assertEqual(SAFE, dict((c.control_name, c.value) for c in plans[-1].additional_controls)["capture_mode"])
        self.assertEqual(SAFE, dict((c.control_name, c.value) for c in readiness[-1].additional_controls)["capture_mode"])
        dialog.accept_button.click()
        window._invoke_build_plan()
        window._invoke_test_runner()
        for snapshot in (plans[-1], readiness[-1], intents[-1]):
            self.assertEqual({"capture_mode": DIAGNOSTIC, "diagnostic_privacy_acknowledged": DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT},
                {c.control_name: c.value for c in snapshot.additional_controls})
        unavailable = self.window(sidebar=projection(available=False), on_build_plan=plans.append)
        self.choose(unavailable).accept_button.click()
        self.assertFalse(unavailable.build_plan_button.isEnabled())
        count = len(plans)
        unavailable._invoke_build_plan()
        self.assertEqual(count, len(plans))

    def test_untrusted_projected_acknowledgement_does_not_grant_consent(self):
        window = self.window(sidebar=projection(profile=DIAGNOSTIC, acknowledgement=DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT))
        self.assert_safe(window)
        self.assertIsNotNone(self.choose(window))

    def test_legacy_unversioned_registration_cannot_enable_new_diagnostic_capture(self):
        sidebar = projection()
        sidebar = replace(sidebar, additional_controls=(sidebar.additional_controls[0],
            SidebarChoiceControlProjection("diagnostic_privacy_acknowledged", "Old consent",
                ("not_acknowledged", "acknowledged"), "acknowledged")))
        window = self.window(sidebar=sidebar)
        self.assertIsNone(self.choose(window))
        self.assert_safe(window)

    def test_production_resolvers_preserve_versioned_consent_and_reject_old_token(self):
        from AgMark.gui.composition import compose_repository_planning_session, RepositoryCompositionError
        from AgMark.gui.requests import RepositoryApplicationRequestResolver
        from AgMark.shared.software_testing.frontends.gui.isolated_repository import isolate_repository
        isolate_repository(self, "_REPOSITORY_ROOT")
        authority = compose_repository_planning_session(_REPOSITORY_ROOT).authority
        benchmark = next(candidate.registration for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"] == "arcgrav.authority-resolution.benchmark.core")
        runner = next(source.registration for source in authority.runner_sources
            if source.registration["registration_id"] == "openai.codex-cli")
        runner_id = f"{runner['registration_id']}@{runner['registration_version']}"
        benchmark_id = f"{benchmark['registration_id']}@{benchmark['registration_version']}"
        sidebar = replace(projection(), runner_options=(runner_id,), selected_runner=runner_id,
            benchmark_options=(benchmark_id,), selected_benchmark=benchmark_id,
            model_options=("fixture-model",), selected_model="fixture-model")
        window = self.window(sidebar=sidebar)
        self.choose(window).accept_button.click()
        intent = window.sidebar_input_snapshot()
        intent = replace(intent, additional_controls=intent.additional_controls + (
            SidebarControlInputSnapshot("launch_mode", "native"),
            SidebarControlInputSnapshot("codex_binary", "fixture-codex"),
            SidebarControlInputSnapshot("reasoning_effort", "medium"),
        ))
        def planning_probe(source, controls):
            return {"status": "ready", "provider_submitted": False,
                    "resolved_controls": dict(controls),
                    "provider_runtime": {"runtime_id": "openai.codex-cli", "runtime_version": "fixture",
                        "provider": "OpenAI", "access_method": "cli", "model": controls["model_id"]}}
        resolver = RepositoryApplicationRequestResolver(authority, runner_planning_probe=planning_probe)
        for resolve in (resolver.resolve_plan_request, resolver.resolve_runner_test_request):
            request = resolve(intent, authority.discovery)
            controls = {control["name"]: control["value"]
                        for control in request.execution_boundary.to_dict()["controls"]}
            self.assertEqual(DIAGNOSTIC, controls["capture_mode"])
            self.assertEqual(DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT, controls["diagnostic_privacy_acknowledged"])
            stale = replace(intent, additional_controls=tuple(
                SidebarControlInputSnapshot(item.control_name,
                    "acknowledged" if item.control_name == "diagnostic_privacy_acknowledged" else item.value)
                for item in intent.additional_controls))
            with self.assertRaises(RepositoryCompositionError):
                resolve(stale, authority.discovery)


if __name__ == "__main__":
    unittest.main()
