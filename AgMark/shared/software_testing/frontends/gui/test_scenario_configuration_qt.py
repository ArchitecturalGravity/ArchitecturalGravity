"""Scenario selection exercises production composition and immutable lifecycle identity."""

import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.application import BenchmarkDesktopApplication
from AgMark.gui.design_system.theme import arcgrav_application_icon, apply_application_theme
from AgMark.gui.shell.window import PYSIDE6_AVAILABLE
from AgMark.shared.runtime.orchestration import BlockedRun

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

_ROOT = Path(__file__).resolve().parents[5]


@unittest.skipUnless(PYSIDE6_AVAILABLE and os.name == "posix", "Registered native mock process and PySide6 required")
class ScenarioConfigurationTests(unittest.TestCase):
    def setUp(self):
        from AgMark.shared.software_testing.frontends.gui.isolated_repository import isolate_repository
        isolate_repository(self, "_ROOT")

    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def compose(self, **kwargs):
        apply_application_theme(self.qt)
        application = BenchmarkDesktopApplication.from_repository_authority(
            application_icon=arcgrav_application_icon(),
            repository_root=_ROOT,
            authority_dispatcher=lambda operation: operation(), **kwargs,
        )
        self.addCleanup(application.window.deleteLater)
        application.show()
        application.window.resize(1440, 1080)
        window = application.window
        window.runner_input.set_value("arcgrav.mock-model.runner@1.0.0")
        QApplication.processEvents()
        return application

    @staticmethod
    def select(window, scenario_id):
        choice = next(choice for choice in window._scenario_choice_by_label.values() if choice.scenario_id == scenario_id)
        window.scenario_input.set_value(choice.scenario_label)
        QApplication.processEvents()
        return choice.model_value

    def test_registered_selector_is_accessible_synchronized_and_within_configuration(self):
        application = self.compose()
        window = application.window
        labels = tuple(window.configuration_row_labels)
        self.assertEqual("Scenario", labels[labels.index("Model") + 1])
        self.assertIsNone(window.reasoning_input)
        self.assertNotIn("capture_mode", window.additional_control_inputs)
        self.assertTrue(window.configuration_widget.isAncestorOf(window.scenario_input))
        label = window.configuration_row_labels["Scenario"]
        label_position = label.mapTo(window.configuration_widget, QPoint(0, 0))
        scenario_position = window.scenario_input.mapTo(window.configuration_widget, QPoint(0, 0))
        model_position = window.model_input.mapTo(window.configuration_widget, QPoint(0, 0))
        self.assertLessEqual(label_position.y() + label.height(), scenario_position.y())
        self.assertGreater(label_position.y(), model_position.y() + window.model_input.height())
        self.assertEqual(label_position.x(), scenario_position.x())
        self.assertEqual(window.model_input.width(), window.scenario_input.width())
        self.assertFalse(window.scenario_input.combo_box.isEditable())
        self.assertTrue(window.scenario_input.combo_box.isEnabled())
        self.assertEqual("default", window._scenario_choice_by_label[window.scenario_input.value].scenario_id)
        self.assertEqual("mock-base", window.sidebar_input_snapshot().model)
        window.model_input.combo_box.setFocus()
        QTest.keyClick(window.model_input.combo_box, Qt.Key.Key_Tab)
        QApplication.processEvents()
        self.assertTrue(window.scenario_input.combo_box.hasFocus())
        QTest.keyClick(window.scenario_input.combo_box, Qt.Key.Key_Down)
        QApplication.processEvents()
        choice = window._scenario_choice_by_label[window.scenario_input.value]
        self.assertEqual(choice.model_value, window.sidebar_input_snapshot().model)
        self.assertEqual(choice.label, window.model_input.value)
        model = next(choice for choice in window._model_choice_by_label.values() if choice.scenario_id == "structured_response")
        window.model_input.set_value(model.label)
        QApplication.processEvents()
        self.assertEqual(model.scenario_label, window.scenario_input.value)
        self.assertEqual(model.model_value, window.sidebar_input_snapshot().model)
        names = {control.control_name for control in window.sidebar_input_snapshot().additional_controls}
        self.assertTrue({"scenario", "scenario_id", "mock_outcome"}.isdisjoint(names))
        self.assertEqual(0, window.sidebar_scroll.horizontalScrollBar().maximum())
        self.assertEqual(0, window.configuration_scroll.horizontalScrollBar().maximum())
        self.assertEqual(0, window.configuration_scroll.verticalScrollBar().maximum())
        self.assertLessEqual(window.configuration_scroll.height(), 310)
        self.assertFalse(window.grab().isNull())

    def test_editing_scenario_preserves_accepted_identity_until_new_plan_then_executes_actual_failure(self):
        application = self.compose()
        window = application.window
        selected = self.select(window, "structured_response")
        application.request_build_plan(window.sidebar_input_snapshot())
        application.request_accept_plan()
        QApplication.processEvents()
        boundary = application.shared_application_boundary
        accepted = boundary.accepted_snapshot
        prepared = boundary.session.prepared_plan
        self.assertIsNotNone(accepted)
        self.assertEqual(selected, boundary.plan_request.execution_boundary.to_dict()["provider_runtime"]["model"])
        fingerprint = boundary.plan_request.execution_boundary.fingerprint
        failure_model = self.select(window, "process_failure")
        self.assertIs(accepted, boundary.accepted_snapshot)
        self.assertIs(prepared, boundary.session.prepared_plan)
        self.assertEqual(fingerprint, boundary.plan_request.execution_boundary.fingerprint)
        application.request_build_plan(window.sidebar_input_snapshot())
        self.assertIsNone(boundary.accepted_snapshot)
        self.assertNotEqual(fingerprint, boundary.plan_request.execution_boundary.fingerprint)
        application.request_accept_plan()
        application.request_start_benchmark()
        QApplication.processEvents()
        terminal = boundary.selected_terminal
        self.assertIs(type(terminal), BlockedRun)
        self.assertEqual(failure_model, boundary.plan_request.execution_boundary.to_dict()["provider_runtime"]["model"])
        self.assertEqual("Failed", window.run_rows[terminal.generation_id].status_badge.label)
        retained_manifest = terminal.artifact_manifest.to_run_outcome_field()
        self.select(window, "structured_response")
        self.assertEqual(retained_manifest, terminal.artifact_manifest.to_run_outcome_field())
        self.assertEqual(failure_model, boundary.plan_request.execution_boundary.to_dict()["provider_runtime"]["model"])

    def test_unresolved_metadata_is_disabled_and_switching_to_live_removes_scenario(self):
        application = self.compose(model_discovery_probe=lambda *_: None)
        window = application.window
        self.assertIsNotNone(window.scenario_input)
        self.assertFalse(window.scenario_input.combo_box.isEnabled())
        self.assertIsNone(window.scenario_input.value)
        self.assertFalse(window.build_plan_button.isEnabled())
        window.runner_input.set_value("openai.codex-cli@2.0.0")
        QApplication.processEvents()
        self.assertIsNone(window.scenario_input)
        self.assertNotIn("Scenario", window.configuration_row_labels)
        self.assertIsNone(window.sidebar_input_snapshot().model)
