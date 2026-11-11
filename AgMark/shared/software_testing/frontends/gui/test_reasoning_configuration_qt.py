"""Reasoning selection across the production sidebar and accepted plan boundary."""

import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.application import BenchmarkDesktopApplication
from AgMark.gui.composition import compose_repository_planning_session
from AgMark.gui.requests import RepositoryApplicationRequestResolver
from AgMark.gui.shell.window import PYSIDE6_AVAILABLE
from AgMark.shared.adapters.Codex_CLI.model_discovery import decode_model_list_response

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

_ROOT = Path(__file__).resolve().parents[5]


def catalog():
    result = decode_model_list_response({"data": [{
        "model": model, "displayName": model, "isDefault": index == 0,
        "scenario": {"scenario_id": "completed-" + str(index), "label": "Completed " + str(index),
                     "base_model_id": model, "model_id": model, "is_default": index == 0},
        "supportedReasoningEfforts": [
            {"reasoningEffort": value, "description": "Description for " + value}
            for value in values],
        "defaultReasoningEffort": values[0],
    } for index, (model, values) in enumerate((
        ("model-a", ("medium", "high")), ("model-b", ("low", "medium")),
    ))], "nextCursor": None})
    return {"status": "ready", "provider_submitted": False, **result}


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 required")
class ReasoningConfigurationTests(unittest.TestCase):
    runner_identity = "openai.codex-cli@2.0.0"
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgMark.shared.software_testing.frontends.gui.isolated_repository import isolate_repository
        isolate_repository(self, "_ROOT")
        self.composition = compose_repository_planning_session(_ROOT)
        self.probed_controls = []

        def planning_probe(source, controls):
            self.probed_controls.append(dict(controls))
            return {
                "status": "ready", "provider_submitted": False,
                "provider_runtime": {
                    "runtime_id": source.registration["registration_id"],
                    "runtime_version": "0.163.0", "provider": "OpenAI",
                    "access_method": "cli", "model": controls["model_id"],
                },
                "resolved_controls": {"reasoning_effort": controls["reasoning_effort"]},
            }

        self.resolver = RepositoryApplicationRequestResolver(
            self.composition.authority, runner_planning_probe=planning_probe,
        )

    def compose(self, discovery=None):
        authority = self.composition.authority
        app = BenchmarkDesktopApplication.from_planning_session(
            application_icon=QIcon(QPixmap(1, 1)),
            session=self.composition.session, request_resolver=self.resolver,
            runner_sources=authority.runner_sources,
            benchmark_candidates=authority.benchmark_candidates,
            repository_root=authority.repository_root,
            executable_resolver=lambda name: name,
            authentication_probe=lambda *_args: True,
            model_discovery_probe=lambda *_: catalog() if discovery is None else discovery,
            authority_dispatcher=lambda operation: operation(),
        )
        self.addCleanup(app.window.deleteLater)
        app.show()
        app.window.resize(1440, 1080)
        app.window.runner_input.set_value(self.runner_identity)
        QApplication.processEvents()
        return app

    def test_selector_placement_defaults_keyboard_and_model_changes(self):
        app = self.compose()
        window = app.window
        labels = tuple(window.configuration_row_labels)
        self.assertEqual("Reasoning Level", labels[labels.index("Model") + 1])
        control = window.reasoning_input
        self.assertEqual("medium", control.value)
        self.assertEqual("Medium (default)", control.combo_box.currentText())
        self.assertFalse(control.combo_box.isEditable())
        self.assertEqual(window.model_input.width(), control.width())
        model_position = window.model_input.mapTo(window.configuration_widget, QPoint(0, 0))
        reason_position = control.mapTo(window.configuration_widget, QPoint(0, 0))
        self.assertGreater(reason_position.y(), model_position.y())
        window.model_input.combo_box.setFocus()
        QApplication.processEvents()
        QTest.keyClick(window.model_input.combo_box, Qt.Key.Key_Tab)
        QApplication.processEvents()
        self.assertTrue(window.reasoning_input.combo_box.hasFocus())
        window.reasoning_input.set_value("high")
        self.assertEqual("high", window.reasoning_input.value)
        window.model_input.set_value("model-b")
        self.assertEqual(("low", "medium"), window.reasoning_input.options)
        self.assertEqual("low", window.reasoning_input.value)
        window.reasoning_input.set_value("medium")
        window.model_input.set_value("Default (model-a)")
        self.assertEqual("medium", window.reasoning_input.value)
        window.runner_input.set_value("arcgrav.mock-model.runner@1.0.0")
        self.assertIsNone(window.reasoning_input)
        self.assertNotIn("Reasoning Level", window.configuration_row_labels)

    def test_missing_capabilities_disable_selection_and_plan(self):
        discovery = catalog()
        for choice in discovery["choices"]:
            del choice["reasoning_efforts"]
            del choice["default_reasoning_effort"]
        app = self.compose(discovery)
        window = app.window
        self.assertFalse(window.reasoning_input.combo_box.isEnabled())
        self.assertIsNone(window.reasoning_input.value)
        self.assertFalse(window.build_plan_button.isEnabled())
        self.assertFalse(window.runner_test_action.isEnabled())

    def test_planning_and_test_runner_retain_effort_and_change_boundary_identity(self):
        app = self.compose()
        window = app.window
        discovery = self.composition.authority.discovery
        before = self.resolver.resolve_plan_request(window.sidebar_input_snapshot(), discovery)
        window.reasoning_input.set_value("high")
        intent = window.sidebar_input_snapshot()
        after = self.resolver.resolve_plan_request(intent, discovery)
        self.assertNotEqual(before.execution_boundary.fingerprint, after.execution_boundary.fingerprint)
        before_controls = {c["name"]: c["value"] for c in before.execution_boundary.to_dict()["controls"]}
        after_controls = {c["name"]: c["value"] for c in after.execution_boundary.to_dict()["controls"]}
        self.assertEqual("medium", before_controls["reasoning_effort"])
        self.assertEqual("high", after_controls["reasoning_effort"])
        self.resolver.resolve_runner_test_request(intent, discovery)
        self.assertEqual("high", self.probed_controls[-1]["reasoning_effort"])

    def test_built_plan_shows_reasoning_next_to_model_and_updates_on_rebuild(self):
        app = self.compose()
        window = app.window
        for effort, expected in (('medium', 'model-a (Medium)'), ('high', 'model-a (High)')):
            with self.subTest(effort=effort):
                window.reasoning_input.set_value(effort)
                window.build_plan_button.click()
                for _ in range(5):
                    QApplication.processEvents()
                model = next(value for label, value in window.execution_boundary_rows
                    if label.text() == 'Model:')
                self.assertEqual(expected, model.text())
                self.assertTrue(model.isVisible())
                self.assertTrue(window.execution_boundary_card.isAncestorOf(model))
        # Changing the selector alone must not rewrite already-built authority.
        window.reasoning_input.set_value('medium')
        QApplication.processEvents()
        self.assertEqual('model-a (High)', model.text())

    def _assert_live_launch_survives_planning(self, mode, executable, distribution=None):
        import json
        from unittest.mock import patch
        # Simulate host selection only. No external executable, WSL, or inference.
        with patch('AgMark.gui.readiness.os_name', 'nt' if mode == 'wsl' else 'posix'):
            app = self.compose()
            window = app.window
            window.additional_control_inputs['launch_mode'].set_value(mode)
            window.additional_control_inputs['codex_binary'].set_value(executable)
            if distribution is not None:
                window.additional_control_inputs['wsl_distribution'].set_value(distribution)
            calls = []

            def discover(source, controls=None):
                selected = dict(controls or {})
                calls.append(selected)
                if selected.get('codex_binary') == 'runtime/codex':
                    return {'status': 'unsupported', 'provider_submitted': False,
                            'error_code': 'codex_cli_model_catalog_unavailable'}
                return catalog()

            app._projector._model_discovery_probe = discover
            for effort in ('medium', 'high'):
                window.reasoning_input.set_value(effort)
                window.build_plan_button.click()
                for _ in range(5):
                    QApplication.processEvents()
                self.assertIsNotNone(app._boundary.session.prepared_plan)
                self.assertEqual(executable, window.additional_control_inputs['codex_binary'].value)
                self.assertEqual(effort, window.reasoning_input.value)
                self.assertTrue(window.build_plan_button.isEnabled())
                self.assertTrue(calls)
                self.assertTrue(all(c.get('codex_binary') == executable for c in calls))
                if distribution is not None:
                    self.assertEqual(distribution, window.additional_control_inputs['wsl_distribution'].value)
                    self.assertTrue(all(c.get('wsl_distribution') == distribution for c in calls))
                boundary = app._boundary.plan_request.execution_boundary.to_dict()
                controls = {c['name']: c['value'] for c in boundary['controls']}
                self.assertEqual('runtime/codex', controls['codex_binary'])
                self.assertNotIn('wsl_distribution', controls)
                retained = json.dumps(boundary) + app._boundary.session.prepared_plan.canonical_bytes.decode()
                if executable != 'codex':
                    self.assertNotIn(executable, retained)
                if distribution is not None:
                    self.assertNotIn(distribution, retained)
                calls.clear()
            app.request_accept_plan()
            for _ in range(5):
                QApplication.processEvents()
            self.assertIsNotNone(app._boundary.accepted_snapshot)
            # Acceptance remains in memory until execution. Verify the exact
            # canonical plan/boundary bytes that become retained authority.
            retained = (app._boundary.accepted_snapshot.plan().canonical_bytes
                        + app._boundary.plan_request.execution_boundary.canonical_bytes)
            for value in (executable, distribution or ''):
                if value and value not in ('codex', 'Ubuntu'):
                    self.assertNotIn(value.encode(), retained)
            self.assertEqual(executable, window.additional_control_inputs['codex_binary'].value)
            self.assertTrue(all(c.get('codex_binary') == executable for c in calls))
            selection = app._boundary.transient_plan_launch_controls
            selection['codex_binary'] = 'mutated-copy'
            self.assertEqual(executable, app._boundary.transient_plan_launch_controls['codex_binary'])
            # Switching adapters must not leak this plan's launch controls.
            window.runner_input.set_value('arcgrav.mock-model.runner@1.0.0')
            QApplication.processEvents()
            self.assertNotIn('codex_binary', window.additional_control_inputs)
            window.runner_input.set_value(self.runner_identity)
            QApplication.processEvents()
            self.assertEqual('codex', window.additional_control_inputs['codex_binary'].value)

    def test_default_native_launch_survives_build_rebuild_and_accept(self):
        self._assert_live_launch_survives_planning('native', 'codex')

    def test_private_native_launch_stays_transient_across_planning(self):
        self._assert_live_launch_survives_planning('native', '/private-launch-user/bin/codex')

    def test_private_wsl_launch_stays_transient_across_planning(self):
        self._assert_live_launch_survives_planning('wsl', '/private-wsl-user/bin/codex', 'Private-Distro')

    def test_default_wsl_launch_survives_build_rebuild_and_accept(self):
        self._assert_live_launch_survives_planning('wsl', 'codex', 'Ubuntu')
