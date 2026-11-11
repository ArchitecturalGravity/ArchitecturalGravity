"""Custom prompt execution reaches unscored Results without reporting authority."""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from AgMark.Custom_Benchmark.source import load_prompts
from AgMark.gui.composition import compose_repository_planning_session
from AgMark.gui.requests.resolver import RepositoryApplicationRequestResolver
from AgMark.gui.application.session_boundary import PlanningSessionApplicationBoundary
from AgMark.gui.shell.input_snapshot import SidebarInputSnapshot, SidebarControlInputSnapshot
from AgMark.gui.projection.workspace.results import _results_projection
from AgMark.gui.projection.workspace.projector import SharedWorkspaceProjector
from AgMark.gui.views.results import ResultsView
from AgMark.shared.runtime.orchestration import ExecutedRun
from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore
from AgMark.shared.runtime.artifacts.archive import archive_path, read_archive_member
from AgMark.shared.software_testing.frontends.gui.isolated_repository import isolate_repository

ROOT = Path(__file__).resolve().parents[5]


class CustomBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        isolate_repository(self, 'ROOT', archive_backed=True)
        self.folder = TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        (self.path/'b.txt').write_text('Second complete prompt\n', encoding='utf-8')
        (self.path/'a.txt').write_bytes(b'First complete prompt\r\n')
        self.composition = compose_repository_planning_session(ROOT)
        self.resolver = RepositoryApplicationRequestResolver(self.composition.authority)
        self.boundary = PlanningSessionApplicationBoundary(session=self.composition.session,
            request_resolver=self.resolver)
        self.intent = SidebarInputSnapshot(benchmark='arcgrav.custom.benchmark.core@1.0.0',
            runner='arcgrav.mock-model.runner@1.0.0', model='mock-base::scenario:completed',
            credential='', temperature=None, max_tokens=None, prompt_folder=str(self.path),
            run_cache_validation_replays=False, iterations=2,
            randomize_treatment_start=False,
            additional_controls=())

    def offline_desktop_options(self):
        """Pin the registered mock before startup can choose a user's runner."""
        from AgMark.gui.shell.projections import SidebarProjection
        from AgMark.gui.application.desktop import (
            probe_registered_runner_authentication,
            probe_registered_runner_model_discovery,
        )
        def authentication(source, selected_control_values=None):
            self.assertEqual('arcgrav.mock-model.runner', source.registration['registration_id'])
            return probe_registered_runner_authentication(source, repository_root=ROOT,
                selected_control_values=selected_control_values)
        def catalog(source, selected_control_values=None):
            self.assertEqual('arcgrav.mock-model.runner', source.registration['registration_id'])
            return probe_registered_runner_model_discovery(source, repository_root=ROOT,
                selected_control_values=selected_control_values)
        return dict(shell_preferences={},
            initial_sidebar_projection=SidebarProjection(
                runner_options=('arcgrav.mock-model.runner@1.0.0',),
                selected_runner='arcgrav.mock-model.runner@1.0.0'),
            authentication_probe=authentication, model_discovery_probe=catalog)

    def execute(self, **changes):
        self.boundary.build_plan(replace(self.intent, **changes))
        self.boundary.accept_plan()
        with patch('AgMark.shared.application.score_accepted_treatments', side_effect=AssertionError('must not score')):
            return self.boundary.start_benchmark()

    def test_folder_discovery_and_errors(self):
        (self.path/'included.md').write_text('Markdown prompt')
        (self.path/'nested').mkdir(); (self.path/'nested/c.txt').write_text('nested')
        prompts = load_prompts(str(self.path))
        self.assertEqual(['a.txt', 'b.txt', 'included.md'], [p.treatment_id for p in prompts])
        self.assertEqual(b'First complete prompt\r\n', prompts[0].data)
        (self.path/'binary.bin').write_bytes(b'\x00\xff')
        self.assertEqual(
            ['a.txt', 'b.txt', 'binary.bin', 'included.md'],
            [p.treatment_id for p in load_prompts(str(self.path))],
        )
        self.assertEqual(b'\x00\xff', load_prompts(str(self.path))[2].data)
        (self.path/'empty.txt').write_text('  ')
        with self.assertRaisesRegex(ValueError, 'empty.txt'):
            load_prompts(str(self.path))
        for path in ('', str(self.path/'missing'), str(self.path/'a.txt'), str(self.path/'nested/missing')):
            with self.subTest(path=path), self.assertRaises(ValueError): load_prompts(path)

    def test_all_file_types_can_be_planned_and_excluded(self):
        (self.path/'content.json').write_text('{"prompt": "ready"}')
        (self.path/'raw.bin').write_bytes(b'\x00\xff')
        self.boundary.build_plan(self.intent)
        request = self.boundary.plan_request
        self.assertEqual(
            ('a.txt', 'b.txt', 'content.json', 'raw.bin'),
            request.treatments,
        )
        original_digest = request.treatment_set.sha256
        self.boundary.build_plan(replace(
            self.intent, excluded_treatments=('b.txt', 'raw.bin'),
        ))
        self.assertEqual(('a.txt', 'content.json'), self.boundary.plan_request.treatments)
        self.assertNotEqual(original_digest, self.boundary.plan_request.treatment_set.sha256)
        with self.assertRaisesRegex(ValueError, 'At least one treatment'):
            self.boundary.build_plan(replace(
                self.intent,
                excluded_treatments=('a.txt', 'b.txt', 'content.json', 'raw.bin'),
            ))
        self.assertEqual(('a.txt', 'content.json'), self.boundary.plan_request.treatments)
        with self.assertRaisesRegex(ValueError, 'not in the selected folder'):
            self.boundary.build_plan(replace(
                self.intent, excluded_treatments=('missing.txt',),
            ))

    def test_unscored_execution_results_and_repeat(self):
        run = self.execute()
        self.assertIs(type(run), ExecutedRun)
        self.assertEqual(4, len(run.treatment_observations))
        self.assertFalse(run.score_artifacts)
        store = self.boundary.artifact_store(run.generation_id)
        self.assertEqual(b'executed', read_archive_member(
            archive_path(store.root, run.generation_id), f'.{run.generation_id}.terminal'))
        projection = _results_projection(run, None, plan=self.boundary.accepted_snapshot.plan(), store=store)
        self.assertTrue(projection.unscored)
        self.assertEqual(['a.txt', 'b.txt'], [r.treatment for r in projection.rows])
        self.assertTrue(all(r.score is None for r in projection.rows))
        view = ResultsView(projection); self.addCleanup(view.deleteLater)
        self.assertEqual(['a.txt', 'b.txt'], [button.text() for button in view.treatment_buttons])
        self.assertEqual(2, view.cache_table.table_model.rowCount())
        self.assertEqual('Execution Treatments', view.treatment_heading.text())
        self.assertEqual(2, len(ValidationArtifactStore(store).read(run)))
        self.assertIsNone(self.boundary.report_bundle)
        rerun = self.execute(iterations=1)
        self.assertNotEqual(run.generation_id, rerun.generation_id)
        self.assertEqual(2, len(rerun.treatment_observations))
        self.assertIs(self.boundary.select_run(run.generation_id), run)

    def test_cache_selection_reaches_unscored_results(self):
        run = self.execute(iterations=1, run_cache_validation_replays=True)
        store = self.boundary.artifact_store(run.generation_id)
        summaries = ValidationArtifactStore(store).read(run)
        self.assertEqual(2, len(summaries))
        self.assertTrue(all(s.sampling_policy != 'disabled_by_user' for s in summaries))
        projection = _results_projection(run,None,plan=self.boundary.accepted_snapshot.plan(),store=store)
        self.assertTrue(all(row.validation is not None for row in projection.rows))

    def test_cancel_before_submission_and_retry(self):
        self.boundary.build_plan(self.intent); self.boundary.accept_plan()
        run = self.boundary.start_benchmark(on_execution_started=lambda *_: self.boundary.cancel_benchmark())
        self.assertTrue(run.cancelled)
        self.assertFalse(run.treatment_observations)
        rows = _results_projection(run,None,plan=self.boundary.accepted_snapshot.plan(),
            store=self.boundary.artifact_store(run.generation_id)).rows
        self.assertTrue(all(r.status=='cancelled' for r in rows))
        self.assertEqual(2,len(self.execute(iterations=1).treatment_observations))

    def test_treatments_card_removal_replans_execution(self):
        import time
        from AgMark.gui.application import BenchmarkDesktopApplication
        from AgMark.gui.design_system.theme import arcgrav_application_icon

        (self.path/'instructions.md').write_text('A markdown treatment')
        desktop = BenchmarkDesktopApplication.from_repository_authority(
            repository_root=ROOT, application_icon=arcgrav_application_icon(),
            **self.offline_desktop_options(),
        )
        self.addCleanup(desktop.window.deleteLater)
        desktop.show()

        def idle():
            deadline = time.monotonic() + 20
            while (desktop._pending_commands or desktop._sidebar_refresh_pending) and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
            self.app.processEvents()
            self.assertFalse(desktop._pending_commands)
            self.assertFalse(desktop._sidebar_refresh_pending)

        idle()
        window = desktop.window
        self.assertEqual("arcgrav.mock-model.runner@1.0.0", window.sidebar_input_snapshot().runner)
        combo = window.benchmark_input.combo_box
        combo.setCurrentIndex(combo.findText('Custom Benchmark'))
        idle()
        window.prompt_folder_input.setText(str(self.path))
        window.cache_replays_checkbox.setChecked(False)
        window.randomize_treatment_start_checkbox.setChecked(False)
        idle()
        self.assertTrue(window.build_plan_button.isEnabled())
        window.build_plan_button.click()
        idle()

        self.assertEqual(
            ('a.txt', 'b.txt', 'instructions.md'),
            desktop._boundary.plan_request.treatments,
        )
        self.assertEqual('Treatments', window.treatments_card.title)
        self.assertEqual(
            ['a.txt', 'b.txt', 'instructions.md'],
            [label.text() for label in window.treatment_file_labels],
        )
        self.assertNotIn('Treatments', [
            label.text() for label, _ in window.run_plan_rows
        ])
        self.assertEqual('×', window.treatment_remove_buttons['a.txt'].text())
        window.treatment_remove_buttons['a.txt'].click()
        idle()
        self.assertEqual(
            ('b.txt', 'instructions.md'),
            desktop._boundary.plan_request.treatments,
        )
        self.assertEqual(
            ['b.txt', 'instructions.md'],
            [label.text() for label in window.treatment_file_labels],
        )
        window.treatment_remove_buttons['b.txt'].click()
        idle()
        self.assertEqual(
            ('instructions.md',), desktop._boundary.plan_request.treatments,
        )
        self.assertEqual(('a.txt', 'b.txt'),
                         window.sidebar_input_snapshot().excluded_treatments)
        self.assertFalse(window.treatment_remove_buttons['instructions.md'].isEnabled())
        window.accept_plan_button.click()
        idle()
        window.start_benchmark_button.click()
        idle()
        self.assertEqual(
            ['instructions.md'],
            [row.treatment for row in window.workspace_pages['Results'].projection.rows],
        )

    def test_desktop_folder_results_history_and_existing_benchmark(self):
        import time
        from AgMark.gui.application import BenchmarkDesktopApplication
        from AgMark.gui.design_system.theme import arcgrav_application_icon
        from AgMark.gui.application.history import HistoricalRun
        desktop = BenchmarkDesktopApplication.from_repository_authority(repository_root=ROOT,
            application_icon=arcgrav_application_icon(),
            **self.offline_desktop_options())
        self.addCleanup(desktop.window.deleteLater)
        desktop.show()
        def idle():
            deadline = time.monotonic() + 20
            while (desktop._pending_commands or desktop._sidebar_refresh_pending) and time.monotonic() < deadline:
                self.app.processEvents(); time.sleep(.01)
            self.app.processEvents()
            self.assertFalse(desktop._pending_commands)
            self.assertFalse(desktop._sidebar_refresh_pending)
        idle()
        window = desktop.window
        self.assertEqual("arcgrav.mock-model.runner@1.0.0", window.sidebar_input_snapshot().runner)
        combo = window.benchmark_input.combo_box
        index = combo.findText('Custom Benchmark')
        self.assertGreaterEqual(index, 0)
        verification_index = next(
            i for i in range(window.workspace_tabs.count())
            if window.workspace_tabs.tabText(i) == 'Verification'
        )
        if window.workspace_tabs.isTabVisible(verification_index):
            window.workspace_tabs.set_selected_index(verification_index)
        combo.setCurrentIndex(index); idle()
        self.assertFalse(window.prompt_folder_controls.isHidden())
        self.assertIn(window.workspace_tabs.selected_label, ('Progress', 'Scoring', 'Results', 'Evidence'))
        self.assertEqual('secondary', window.prompt_folder_browse.role)
        self.assertIn('background-color:', window.prompt_folder_browse.styleSheet())
        scoring_index = next(i for i in range(window.workspace_tabs.count())
                             if window.workspace_tabs.tabText(i) == 'Scoring')
        self.assertTrue(window.workspace_tabs.isTabVisible(scoring_index))
        for label in ('Verification', 'Reports'):
            tab_index = next(i for i in range(window.workspace_tabs.count())
                             if window.workspace_tabs.tabText(i) == label)
            self.assertFalse(window.workspace_tabs.isTabVisible(tab_index))
        with patch('AgMark.gui.shell.sidebar.QFileDialog.getExistingDirectory', return_value=str(self.path)):
            window.prompt_folder_browse.click()
        self.assertEqual(str(self.path), window.sidebar_input_snapshot().prompt_folder)
        window.cache_replays_checkbox.setChecked(False)
        window.randomize_treatment_start_checkbox.setChecked(False)
        idle()
        self.assertTrue(window.build_plan_button.isEnabled())
        window.build_plan_button.click(); idle()
        self.assertIsNotNone(desktop._boundary.plan_request)
        self.assertEqual(('a.txt','b.txt'), desktop._boundary.plan_request.treatments)
        window.accept_plan_button.click(); idle()
        window.start_benchmark_button.click(); idle()
        self.assertIs(type(desktop._boundary.selected_terminal), ExecutedRun)
        view = window.workspace_pages['Results']
        self.assertTrue(view.projection.unscored)
        self.assertEqual(2, view.cache_table.table_model.rowCount())
        scoring_view = window.workspace_pages['Scoring']
        self.assertTrue(window.workspace_tabs.isTabVisible(scoring_index))
        self.assertEqual(2, len(scoring_view.table.rows))
        self.assertNotIn('Accuracy', [column.label for column in scoring_view.table.columns])
        self.assertTrue(all('score' not in row.cells for row in scoring_view.table.rows))
        window.workspace_tabs.set_selected_index(scoring_index)
        self.assertEqual('Scoring', window.workspace_tabs.selected_label)
        for label in ('Reports', 'Verification'):
            index = next(i for i in range(window.workspace_tabs.count()) if window.workspace_tabs.tabText(i)==label)
            self.assertFalse(window.workspace_tabs.isTabVisible(index))
        self.assertEqual(['a.txt', 'b.txt'], [button.text() for button in view.treatment_buttons])
        from AgMark.gui.application.console_projection import _terminal_console_update
        console = _terminal_console_update(desktop._boundary.selected_terminal)
        self.assertEqual(2,len(console.live_view))
        self.assertTrue(all(output is not None for _, _, output in console.live_view))
        run = desktop._boundary.selected_terminal
        store = desktop._boundary.artifact_store(run.generation_id)
        historical = HistoricalRun(run.generation_id,store.root,'Completed','success','Saved')
        with patch('AgMark.shared.application.score_accepted_treatments', side_effect=AssertionError('history must not score')), \
             patch('AgMark.shared.reporting.generation.generate_report_bundle', side_effect=AssertionError('history must not generate')):
            current, workspace = historical.presentation()
        self.assertTrue(workspace.results.projection.unscored)
        self.assertEqual(2,len(workspace.results.projection.rows))
        self.assertEqual(['a.txt', 'b.txt'], [row.treatment for row in workspace.results.projection.rows])
        self.assertTrue(all(row.score is None for row in workspace.results.projection.rows))
        self.assertTrue(all(row.execution_summary['planned_observations'] is None
                            for row in workspace.results.projection.rows))
        self.assertTrue(all('original plan was not retained' in row.details
                            for row in workspace.results.projection.rows))
        for page in workspace.ordered_pages: page.deleteLater()
        # Returning to Authority Resolution restores the scored path and all tabs.
        combo = window.benchmark_input.combo_box
        registered = next(item for item in self.composition.authority.discovery.benchmarks
                          if item.registration_id == 'arcgrav.authority-resolution.benchmark.core')
        index = combo.findData(f'{registered.registration_id}@{registered.registration_version}')
        self.assertGreaterEqual(index, 0)
        combo.setCurrentIndex(index)
        idle()
        self.assertTrue(window.prompt_folder_controls.isHidden())
        window.build_plan_button.click(); idle()
        self.assertTrue(desktop._boundary.plan_request.golden_required)
        self.assertEqual(5,len(desktop._boundary.plan_request.treatments))
        for label in ('Scoring', 'Verification', 'Reports'):
            tab_index = next(i for i in range(window.workspace_tabs.count())
                             if window.workspace_tabs.tabText(i) == label)
            self.assertTrue(window.workspace_tabs.isTabVisible(tab_index))

    def test_partial_cancel_preserves_first_response(self):
        from AgMark.shared.runtime.orchestration import execution
        original = execution._validated_observation
        def cancel_after_observation(*args, **kwargs):
            value = original(*args, **kwargs)
            self.boundary.cancel_benchmark()
            return value
        self.boundary.build_plan(self.intent); self.boundary.accept_plan()
        with patch.object(execution, '_validated_observation', side_effect=cancel_after_observation):
            run = self.boundary.start_benchmark()
        self.assertTrue(run.cancelled)
        self.assertEqual(1,len(run.treatment_observations))
        rows = _results_projection(run,None,plan=self.boundary.accepted_snapshot.plan(),
            store=self.boundary.artifact_store(run.generation_id)).rows
        self.assertEqual(['a.txt','b.txt'],[r.treatment for r in rows])
        self.assertTrue(all(r.status=='cancelled' for r in rows))
        self.assertTrue(rows[0].measurements)
        self.assertTrue(all(m.get("value") is None for m in rows[1].measurements.values()))

    def test_invalid_folder_preserves_prepared_plan_and_does_not_execute(self):
        plan = self.boundary.build_plan(self.intent)
        with self.assertRaises(ValueError): self.boundary.build_plan(replace(self.intent,prompt_folder=''))
        self.assertIs(plan,self.boundary.session.prepared_plan)
        self.assertFalse(self.boundary.retained_runs)
        # Prepared bytes stay fixed until another Build Plan, without rereading files at execution.
        (self.path/'a.txt').unlink()
        self.boundary.accept_plan()
        run = self.boundary.start_benchmark()
        self.assertEqual(4,len(run.treatment_observations))


if __name__ == '__main__': unittest.main()
