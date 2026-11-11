"""Build Plan smoke checks using the shipped registration and mock runner.

Do not replace registration authority or the planning probe with fixture values:
this path must catch stale implementation bindings after adapter edits.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel
from AgMark.gui.application import BenchmarkDesktopApplication
from AgMark.gui.design_system.theme import arcgrav_application_icon
from AgMark.shared.software_testing.frontends.gui.isolated_repository import isolate_repository

_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]


class RegisteredBuildPlanSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        isolate_repository(self, "_REPOSITORY_ROOT")
        self.application = BenchmarkDesktopApplication.from_repository_authority(
            repository_root=_REPOSITORY_ROOT,
            application_icon=arcgrav_application_icon(),
        )
        self.addCleanup(self.application.window.deleteLater)
        self.application.show()
        self.wait_until_idle()

    def wait_until_idle(self):
        deadline = time.monotonic() + 20
        while self.application._pending_commands and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)
        QApplication.processEvents()
        self.assertFalse(self.application._pending_commands)
        self.assertFalse(self.application.window.operation_banner.isVisible())

    def assert_treatments_icon(self):
        window = self.application.window
        card = window.treatments_card
        self.assertEqual("Treatments", card.accessibleName())
        self.assertEqual("current-run-treatments", card.icon_role)
        icon = card.title_icon_label
        title = card.findChild(QLabel, "semanticCardTitle")
        self.assertFalse(icon.pixmap().isNull())
        self.assertTrue(icon.isVisible())
        self.assertLess(icon.geometry().right(), title.geometry().left())
        self.assertEqual(window.execution_boundary_card.title_icon_label.pixmap().size(), icon.pixmap().size())
        self.assertEqual(window.run_plan_card.title_icon_label.pixmap().size(), icon.pixmap().size())

    def test_shipped_adapter_implementation_bindings_match_exact_bytes(self):
        for adapter in ("Codex_CLI", "Mock_Model"):
            registration_path = _REPOSITORY_ROOT / f"AgMark/shared/adapters/{adapter}/registration.json"
            registration = json.loads(registration_path.read_text())
            for artifact in registration["implementation_artifacts"]:
                with self.subTest(adapter=adapter, artifact=artifact["reference"]):
                    actual = hashlib.sha256((_REPOSITORY_ROOT / artifact["reference"]).read_bytes()).hexdigest()
                    self.assertEqual(artifact["sha256"], "sha256:" + actual)

    def test_real_registered_build_repeat_and_failure_recovery(self):
        window = self.application.window
        intent = window.sidebar_input_snapshot()
        self.assertEqual(intent.runner, "arcgrav.mock-model.runner@1.0.0")
        self.assertEqual(intent.benchmark, "arcgrav.authority-resolution.benchmark.core@2.0.0")
        self.assertEqual(window.runner_input.combo_box.currentText(), "Mock Model (Local Test)")
        self.assertEqual(window.benchmark_input.combo_box.currentText(), "Authority Resolution (v2.0.0)")
        self.assertTrue(window.build_plan_button.isEnabled())
        initial_rows = tuple(window.run_rows)
        window.build_plan_button.click()
        self.assertIn("build_plan", self.application._pending_commands)
        self.assertFalse(window.build_plan_button.isEnabled())
        # A repeat invocation while pending must not queue another plan.
        self.application.request_build_plan(intent)
        self.wait_until_idle()
        boundary = self.application.shared_application_boundary
        self.assertIsNotNone(boundary.session.prepared_plan, self.application.environment_projection.render())
        self.assertEqual(boundary.session.prepared_plan.benchmark.id,
                         "arcgrav.authority-resolution.benchmark.core")
        self.assertEqual(boundary.session.prepared_plan.benchmark.version, "2.0.0")
        runner = boundary.plan_request.execution_boundary.to_dict()["runner"]
        self.assertEqual((runner["id"], runner["version"]),
                         ("arcgrav.mock-model.runner", "1.0.0"))
        self.assertIsNone(boundary.accepted_snapshot)
        self.assertEqual(window.current_run_status.label, "Pending")
        self.assertEqual(tuple(window.run_rows), initial_rows)
        self.assertTrue(window.build_plan_button.isEnabled())
        window.build_plan_button.click()
        self.wait_until_idle()
        self.assertEqual(window.current_run_status.label, "Pending")
        self.assertEqual(tuple(window.run_rows), initial_rows)
        with patch.object(boundary, "build_plan", side_effect=RuntimeError("smoke planning failure")):
            window.build_plan_button.click()
            self.wait_until_idle()
        self.assertIn("smoke planning failure", self.application.environment_projection.render())
        self.assertTrue(window.build_plan_button.isEnabled())
        window.build_plan_button.click()
        self.wait_until_idle()
        self.assertEqual(window.current_run_status.label, "Pending")
        self.assertNotIn("smoke planning failure", self.application.environment_projection.render())
        self.assertEqual(tuple(window.run_rows), initial_rows)


    def test_authority_treatments_card_removal_replans_execution(self):
        window = self.application.window
        window.randomize_treatment_start_checkbox.setChecked(False)
        window.build_plan_button.click()
        self.wait_until_idle()
        boundary = self.application.shared_application_boundary
        original_treatments = boundary.plan_request.treatments
        original_digest = boundary.plan_request.treatment_set.sha256
        self.assertGreater(len(original_treatments), 1)
        self.assertEqual(window.treatments_card.title, "Treatments")
        self.assert_treatments_icon()
        self.assertEqual(
            tuple(label.text() for label in window.treatment_file_labels),
            original_treatments,
        )
        self.assertEqual(
            [label.text() for label, _ in window.run_plan_rows],
            ["1. Cases", "2. Execution", "3. Evaluation"],
        )

        window.treatment_remove_buttons[original_treatments[0]].click()
        self.wait_until_idle()
        selected = original_treatments[1:]
        self.assert_treatments_icon()
        self.assertEqual(boundary.plan_request.treatments, selected)
        self.assertEqual(boundary.plan_request.treatment_set.sha256, original_digest)
        self.assertEqual(
            {observation.treatment_id for observation in boundary.session.prepared_plan.observations},
            set(selected),
        )
        self.assertEqual(
            tuple(label.text() for label in window.treatment_file_labels),
            selected,
        )
        self.assertEqual(
            window.sidebar_input_snapshot().excluded_treatments,
            (original_treatments[0],),
        )

        window.accept_plan_button.click()
        self.wait_until_idle()
        request = boundary._request_resolver.resolve_execution_request(
            boundary.plan_request,
            boundary.accepted_snapshot,
            credential="",
            runner_transient_controls=window.sidebar_input_snapshot().additional_controls,
        )
        self.assertEqual(
            tuple(prompt.treatment_id for prompt in request.treatment_prompts),
            selected,
        )

    def test_authority_treatment_exclusions_reject_invalid_or_empty_selection(self):
        window = self.application.window
        window.build_plan_button.click()
        self.wait_until_idle()
        boundary = self.application.shared_application_boundary
        original_plan = boundary.session.prepared_plan
        original_treatments = boundary.plan_request.treatments
        intent = window.sidebar_input_snapshot()
        with self.assertRaisesRegex(ValueError, "selected benchmark"):
            boundary.build_plan(replace(
                intent, excluded_treatments=("not-registered",),
            ))
        with self.assertRaisesRegex(ValueError, "At least one treatment"):
            boundary.build_plan(replace(
                intent, excluded_treatments=original_treatments,
            ))
        self.assertIs(boundary.session.prepared_plan, original_plan)
        self.assertEqual(boundary.plan_request.treatments, original_treatments)


if __name__ == "__main__":
    unittest.main()
