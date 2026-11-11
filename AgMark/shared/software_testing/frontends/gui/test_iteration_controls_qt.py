"""User iteration intent and activity affordances survive normal shell updates."""
from dataclasses import replace
import unittest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from AgMark.gui.shell.input_snapshot import SidebarInputSnapshot
from AgMark.shared.software_testing.frontends.gui import test_application_lifecycle_qt as fixture


class IterationControlsGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.ProductionSharedLifecycleGuiIntegrationTests.setUpClass()

    def test_fresh_defaults_and_saved_choices_survive_reopening(self):
        from AgMark.gui.shell.window import BenchmarkShellWindow
        owner = fixture.ProductionSharedLifecycleGuiIntegrationTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        defaults = {
            "run_cache_validation_replays": False,
            "randomize_treatment_start": True,
            "randomize_per_iteration": True,
        }
        for initial, expected in (
            ({}, defaults),
            ({name: "invalid" for name in defaults}, defaults),
            ({name: not value for name, value in defaults.items()},
             {name: not value for name, value in defaults.items()}),
        ):
            with self.subTest(initial=initial):
                preferences = dict(initial)
                window = BenchmarkShellWindow(application_icon=owner.icon,
                    shell_preferences=preferences)
                self.addCleanup(window.deleteLater)
                for _ in range(2):
                    self.assertEqual(expected["run_cache_validation_replays"],
                        window.cache_replays_checkbox.isChecked())
                    self.assertEqual(expected["randomize_treatment_start"],
                        window.randomize_treatment_start_checkbox.isChecked())
                    self.assertEqual(expected["randomize_per_iteration"],
                        window.randomize_per_iteration_checkbox.isChecked())
                    window.set_sidebar_projection(window._sidebar_projection)
                window.cache_replays_checkbox.setChecked(True)
                window.randomize_treatment_start_checkbox.setChecked(False)
                window.randomize_per_iteration_checkbox.setChecked(False)
                reopened = BenchmarkShellWindow(application_icon=owner.icon,
                    shell_preferences=preferences)
                self.addCleanup(reopened.deleteLater)
                self.assertTrue(reopened.cache_replays_checkbox.isChecked())
                self.assertFalse(reopened.randomize_treatment_start_checkbox.isChecked())
                self.assertFalse(reopened.randomize_per_iteration_checkbox.isChecked())
                self.assertFalse(reopened.randomize_per_iteration_checkbox.isEnabled())

    def test_snapshot_defaults_match_fresh_controls(self):
        intent = SidebarInputSnapshot(benchmark=None, runner=None, model=None,
            credential="", temperature=None, max_tokens=None)
        self.assertFalse(intent.run_cache_validation_replays)
        self.assertTrue(intent.randomize_treatment_start)
        self.assertTrue(intent.randomize_per_iteration)

    def test_iteration_input_survives_refresh_and_reaches_accepted_plan_preview(self):
        owner = fixture.ProductionSharedLifecycleGuiIntegrationTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        application, _, _ = owner._application_for('generation-iterations')
        window = application.window
        window.show()
        self.assertEqual(1, window.iterations_input.value())
        self.assertTrue(window.benchmark_card.isAncestorOf(window.iterations_input))
        for width in (560, 1024):
            window.resize(width, 768)
            QApplication.processEvents()
            row = window.iterations_input.parentWidget()
            self.assertLessEqual(window.iterations_input.geometry().right(), row.width())
            self.assertGreaterEqual(window.iterations_input.height(), 30)
            origin = window.iterations_input.mapTo(window.benchmark_card, QPoint(0, 0))
            self.assertLessEqual(origin.y() + window.iterations_input.height(), window.benchmark_card.height())
        window.set_operation_activity(('Working',), lock_controls=True)
        self.assertFalse(window.iterations_input.isEnabled())
        window.set_operation_activity((), lock_controls=False)
        self.assertTrue(window.iterations_input.isEnabled())
        application.request_discovery()
        owner._wait_until(lambda: bool(window.benchmark_input.options), 'discovery')
        window.iterations_input.setValue(3)
        window.set_sidebar_projection(window._sidebar_projection)
        self.assertEqual(3, window.iterations_input.value())
        intent = SidebarInputSnapshot(benchmark='frontend.benchmark@1.0.0',
            runner='frontend.runner@1.0.0', model='frontend-model', credential='',
            temperature=None, max_tokens=None, iterations=window.sidebar_input_snapshot().iterations)
        for count in (3, 1):
            application.request_build_plan(replace(intent, iterations=count))
            owner._wait_until(lambda: not application._pending_commands, 'plan')
            self.assertEqual(count, application._boundary.plan_request.repetitions)
            application.request_accept_plan()
            owner._wait_until(lambda: not application._pending_commands, 'accept')
            plan = application._boundary.accepted_snapshot.plan()
            self.assertEqual(count, len(plan.observations))
            self.assertEqual(list(range(1, count + 1)), [o.repetition for o in plan.observations])
        for value in (0, -1, 1.5, True, '2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(intent, iterations=value)

    def test_randomize_treatment_start_control_defaults_on_and_survives_refresh(self):
        owner = fixture.ProductionSharedLifecycleGuiIntegrationTests()
        owner.setUp(); self.addCleanup(owner.doCleanups)
        application, _, _ = owner._application_for('generation-randomize-choice')
        window = application.window
        window._shell_preferences = {}
        window.show()
        checkbox = window.randomize_treatment_start_checkbox
        self.assertTrue(checkbox.isChecked())
        self.assertTrue(window.benchmark_card.isAncestorOf(checkbox))
        benchmark_layout = checkbox.parentWidget().parentWidget().layout()
        replay_index = benchmark_layout.indexOf(
            window.cache_replays_checkbox.parentWidget()
        )
        randomize_index = benchmark_layout.indexOf(checkbox.parentWidget())
        self.assertGreaterEqual(replay_index, 0)
        self.assertEqual(replay_index + 1, randomize_index)
        self.assertTrue(window.sidebar_input_snapshot().randomize_treatment_start)
        checkbox.setChecked(False)
        self.assertFalse(window.sidebar_input_snapshot().randomize_treatment_start)
        self.assertFalse(window._shell_preferences['randomize_treatment_start'])
        window.set_sidebar_projection(window._sidebar_projection)
        self.assertFalse(window.randomize_treatment_start_checkbox.isChecked())
        window.set_operation_activity(('Running',), lock_controls=True)
        self.assertFalse(window.randomize_treatment_start_checkbox.isEnabled())
        window.set_operation_activity((), lock_controls=False)
        window.randomize_treatment_start_checkbox.setChecked(True)
        self.assertTrue(window.sidebar_input_snapshot().randomize_treatment_start)
        from AgMark.gui.application.projector import _redacted_intent
        self.assertTrue(_redacted_intent(window.sidebar_input_snapshot()).randomize_treatment_start)
        with self.assertRaises(ValueError):
            replace(window.sidebar_input_snapshot(), randomize_treatment_start=1)

    def test_randomize_per_iteration_is_disabled_without_parent_and_restored(self):
        owner = fixture.ProductionSharedLifecycleGuiIntegrationTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        application, _, _ = owner._application_for('generation-per-iteration-choice')
        window = application.window
        window._shell_preferences = {}
        window.show()
        checkbox = window.randomize_per_iteration_checkbox
        parent = window.randomize_treatment_start_checkbox
        self.assertEqual("Randomize Per Iteration", checkbox.accessibleName())
        self.assertTrue(window.benchmark_card.isAncestorOf(checkbox))
        layout = parent.parentWidget().parentWidget().layout()
        self.assertEqual(
            layout.indexOf(parent.parentWidget()) + 1,
            layout.indexOf(checkbox.parentWidget()),
        )
        self.assertTrue(parent.isChecked())
        self.assertTrue(checkbox.isChecked())
        self.assertTrue(checkbox.isEnabled())

        checkbox.setChecked(False)
        self.assertFalse(window._shell_preferences['randomize_per_iteration'])
        checkbox.setChecked(True)
        self.assertTrue(window._shell_preferences['randomize_per_iteration'])
        self.assertTrue(window.sidebar_input_snapshot().randomize_per_iteration)
        parent.setChecked(False)
        self.assertFalse(checkbox.isEnabled())
        self.assertTrue(checkbox.isChecked())  # Retain the preference when disabled.
        self.assertFalse(window.sidebar_input_snapshot().randomize_per_iteration)
        window.set_sidebar_projection(window._sidebar_projection)
        self.assertFalse(window.randomize_per_iteration_checkbox.isEnabled())
        self.assertTrue(window.randomize_per_iteration_checkbox.isChecked())

        window.set_operation_activity(('Running',), lock_controls=True)
        self.assertFalse(window.randomize_per_iteration_checkbox.isEnabled())
        window.set_operation_activity((), lock_controls=False)
        window.randomize_treatment_start_checkbox.setChecked(True)
        self.assertTrue(window.randomize_per_iteration_checkbox.isEnabled())
        intent = window.sidebar_input_snapshot()
        self.assertTrue(intent.randomize_per_iteration)
        from AgMark.gui.application.projector import _redacted_intent
        self.assertTrue(_redacted_intent(intent).randomize_per_iteration)
        with self.assertRaises(ValueError):
            replace(intent, randomize_per_iteration=1)

    def test_benchmark_checkbox_labels_size_to_wrapped_text(self):
        owner = fixture.ProductionSharedLifecycleGuiIntegrationTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        application, _, _ = owner._application_for('generation-natural-checkbox-spacing')
        window = application.window
        window.show()
        for width in (560, 1024):
            window.resize(width, 768)
            for _ in range(3):
                QApplication.processEvents()
            for checkbox in (
                window.randomize_treatment_start_checkbox,
                window.randomize_per_iteration_checkbox,
                window.cache_replays_checkbox,
            ):
                with self.subTest(width=width, label=checkbox.accessibleName()):
                    row = checkbox.parentWidget()
                    label = row.layout().itemAt(1).widget()
                    self.assertTrue(label.wordWrap())
                    self.assertEqual(0, label.minimumHeight())
                    self.assertGreater(label.width(), 0)
                    self.assertGreaterEqual(
                        label.height(), label.heightForWidth(label.width())
                    )
                    self.assertEqual(label.geometry().top(), checkbox.geometry().top())
                    self.assertLessEqual(label.geometry().bottom(), row.height())
                    if label.fontMetrics().horizontalAdvance(label.text()) <= label.width():
                        self.assertLessEqual(
                            label.height(), label.fontMetrics().lineSpacing() + 2
                        )

    def test_optional_replay_control_retains_choice_is_busy_gated_and_fits_narrow_card(self):
        owner = fixture.ProductionSharedLifecycleGuiIntegrationTests()
        owner.setUp(); self.addCleanup(owner.doCleanups)
        application, _, _ = owner._application_for('generation-replay-choice')
        window = application.window
        window._shell_preferences = {}
        window.show()
        self.assertFalse(window.cache_replays_checkbox.isChecked())
        self.assertEqual("Cache Validation Replays", window.cache_replays_checkbox.accessibleName())
        self.assertTrue(window.benchmark_card.isAncestorOf(window.cache_replays_checkbox))
        window.cache_replays_checkbox.setChecked(True)
        window.cache_replays_checkbox.setChecked(False)
        window.iterations_input.setValue(3)
        window.set_sidebar_projection(window._sidebar_projection)
        intent = window.sidebar_input_snapshot()
        self.assertFalse(intent.run_cache_validation_replays)
        self.assertEqual(3, intent.iterations)
        self.assertFalse(window._shell_preferences['run_cache_validation_replays'])
        from AgMark.gui.application.projector import _redacted_intent
        self.assertFalse(_redacted_intent(intent).run_cache_validation_replays)
        for width in (560, 1024):
            window.resize(width, 768)
            for _ in range(3): QApplication.processEvents()
            row = window.cache_replays_checkbox.parentWidget()
            origin = row.mapTo(window.benchmark_card, QPoint(0, 0))
            self.assertLessEqual(origin.y() + row.height(), window.benchmark_card.height())
            label = row.layout().itemAt(1).widget()
            self.assertLessEqual(label.geometry().bottom(), row.height())
            self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
            self.assertEqual(label.geometry().top(), window.cache_replays_checkbox.geometry().top())
            self.assertEqual(label.fontMetrics().lineSpacing(), window.cache_replays_checkbox.height())
        window.set_operation_activity(('Running',), lock_controls=True)
        self.assertFalse(window.cache_replays_checkbox.isEnabled())
        window.set_operation_activity((), lock_controls=False)
        window.cache_replays_checkbox.setChecked(True)
        self.assertTrue(window.sidebar_input_snapshot().run_cache_validation_replays)
        with self.assertRaises(ValueError): replace(intent, run_cache_validation_replays=1)

    def test_production_resolver_binds_replay_choice_and_iterations_to_accepted_plan(self):
        from pathlib import Path
        from AgMark.gui.composition import compose_repository_planning_session
        from AgMark.gui.request_resolution import RepositoryApplicationRequestResolver
        from AgMark.gui.shell.input_snapshot import SidebarControlInputSnapshot
        composition = compose_repository_planning_session(Path(__file__).resolve().parents[5])
        authority = composition.authority
        benchmark = next(c.registration for c in authority.benchmark_candidates if c.registration['registration_id'] == 'arcgrav.authority-resolution.benchmark.core')
        runner = next(c.registration for c in authority.runner_sources if c.registration['registration_id'] == 'arcgrav.mock-model.runner')
        intent = SidebarInputSnapshot(benchmark=f"{benchmark['registration_id']}@{benchmark['registration_version']}",
            runner=f"{runner['registration_id']}@{runner['registration_version']}", model='mock-base::scenario:completed',
            credential='', temperature=None, max_tokens=None,
            additional_controls=())
        resolver = RepositoryApplicationRequestResolver(authority)
        for enabled, iterations in ((False, 3), (True, 1)):
            requested = replace(intent, run_cache_validation_replays=enabled, iterations=iterations)
            plan_request = resolver.resolve_plan_request(requested, authority.discovery)
            composition.session.build_plan(plan_request)
            snapshot = composition.session.accept_plan()
            self.assertIs(enabled, snapshot.plan().to_dict()['extensions']['arcgrav.runtime:cache-validation-replays'])
            self.assertEqual(iterations, snapshot.plan().repetitions)
            requested = replace(requested, run_cache_validation_replays=not enabled)
            self.assertIs(enabled, snapshot.plan().to_dict()['extensions']['arcgrav.runtime:cache-validation-replays'])

    def test_blue_spinner_is_left_and_animates_only_while_work_is_visible(self):
        owner = fixture.ProductionSharedLifecycleGuiIntegrationTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        application, _, _ = owner._application_for('generation-spinner')
        window = application.window
        window.show()
        window.set_operation_activity(('Finalizing results',), lock_controls=False)
        QApplication.processEvents()
        spinner = window.operation_progress
        self.assertIs(spinner, window.operation_banner.layout().itemAt(0).widget())
        self.assertTrue(spinner.busy)
        self.assertTrue(spinner._timer.isActive())
        image = spinner.grab().toImage()
        self.assertTrue(any(image.pixelColor(x, y).blue() > image.pixelColor(x, y).red() + 40
                            for x in range(image.width()) for y in range(image.height())))
        window.hide()
        self.assertFalse(spinner._timer.isActive())
        window.show()
        window.set_operation_activity((), lock_controls=False)
        self.assertFalse(spinner.busy)
        self.assertFalse(spinner._timer.isActive())
