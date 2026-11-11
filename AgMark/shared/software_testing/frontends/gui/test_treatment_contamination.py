"""Contaminated prompt content uses the registered execution/scoring path."""
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from AgMark.gui.design_system.theme import arcgrav_application_icon

from AgMark.gui.composition import compose_repository_planning_session
from AgMark.gui.requests import RepositoryApplicationRequestResolver
from AgMark.gui.shell.window import BenchmarkShellWindow, SidebarInputSnapshot, SidebarProjection
from AgMark.gui.shell.projections import WORKSPACE_TAB_LABELS
from AgMark.gui.application.history import HistoricalRun, prepare_presentation, save_presentation
from AgMark.shared.runtime.orchestration import AcceptedRun, TreatmentPrompt
from AgMark.shared.runtime.orchestration.execution import _validated_treatment_prompts
from AgMark.shared.reporting.results import registered_rate_summary
from AgMark.shared.treatments import CONTENT, contaminated, content_entries
from AgMark.shared.software_testing.frontends.gui.isolated_repository import isolate_repository

_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_PROMPT = _REPOSITORY_ROOT / "AgMark/Authority_Resolution_Benchmark/treatments/v2.0.0/prompts/arb-arcgrav.txt"


class TreatmentContaminationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        isolate_repository(self, "_REPOSITORY_ROOT", archive_backed=True)

    def resolve(self, changed=False):
        original = Path.read_bytes
        def read(path):
            data = original(path)
            return data + b"\nSupplied changed treatment.\n" if changed and path == _PROMPT else data
        # Changes only the supplied prompt bytes; registration expectations stay intact.
        with patch.object(Path, "read_bytes", read):
            composition = compose_repository_planning_session(_REPOSITORY_ROOT)
            resolver = RepositoryApplicationRequestResolver(composition.authority)
            intent = SidebarInputSnapshot(
                benchmark="arcgrav.authority-resolution.benchmark.core@2.0.0",
                runner="arcgrav.mock-model.runner@1.0.0",
                model="mock-base::scenario:completed", credential="", temperature=None,
                max_tokens=None, additional_controls=(), randomize_treatment_start=False,
                run_cache_validation_replays=True)
            request = resolver.resolve_plan_request(intent, composition.authority.discovery)
        plan = composition.session.build_plan(request)
        snapshot = composition.session.accept_plan()
        # Original disk content has already returned. Execution must use frozen bytes.
        execution = resolver.resolve_execution_request(request, snapshot, credential="")
        return composition, resolver, request, plan, execution

    def test_frozen_mismatch_executes_scores_replays_and_reopens(self):
        from AgMark.shared.runtime.orchestration import replay, execution as execution_module
        clean, clean_resolver, _, clean_plan, clean_request = self.resolve()
        baseline = clean.session.execute_accepted_run(clean_request)
        self.assertIs(type(baseline), AcceptedRun, getattr(baseline, "diagnostics", ()))
        bundle = clean.session.completed_report(baseline.generation_id)
        self.assertIsNotNone(bundle)
        self.assertEqual("complete", clean.session.completion_record(baseline.generation_id)["status"])
        dirty, resolver, request, plan, execute = self.resolve(True)
        self.assertFalse(contaminated(clean_plan.to_dict()))
        self.assertTrue(contaminated(plan.to_dict()))
        altered = next(p for p in execute.treatment_prompts if p.treatment_id == "arb-arcgrav")
        self.assertTrue(altered.data.endswith(b"Supplied changed treatment.\n"))
        with patch.object(replay, "validate_finalized_run", wraps=replay.validate_finalized_run) as replays, \
             patch.object(execution_module, "_runner_request", wraps=execution_module._runner_request) as invocations:
            terminal = dirty.session.execute_accepted_run(execute)
        self.assertIsInstance(terminal, AcceptedRun)
        self.assertTrue(contaminated(terminal.run_outcome()))
        self.assertEqual(1, replays.call_count)
        self.assertIn(altered, replays.call_args.kwargs["treatment_prompts"])
        self.assertTrue(any(c.kwargs["prompt"].data == altered.data for c in invocations.call_args_list))
        metric = execute.scoring_definitions[0].metric_registration
        clean_scores = [json.loads(v) for v in baseline.score_artifacts]
        dirty_scores = [json.loads(v) for v in terminal.score_artifacts]
        self.assertEqual(registered_rate_summary(clean_scores, metric), registered_rate_summary(dirty_scores, metric))
        report = resolver.resolve_report_request(terminal)
        self.assertIsNone(dirty.session.completed_report(terminal.generation_id))
        completion = dirty.session.completion_record(terminal.generation_id)
        self.assertIn(completion["status"], {"validation_failed", "report_failed"})
        self.assertIsNone(completion["report"])
        self.assertNotIn("claim_eligibility", completion)

        self.assertIs(bundle, clean.session.completed_report(baseline.generation_id))
        from AgMark.shared.reporting.revalidation import admit_finalized_run_for_reporting
        with self.assertRaisesRegex(ValueError, "Treatments Contaminated"):
            admit_finalized_run_for_reporting(terminal, store=execute.artifact_store,
                **{name: getattr(report, name) for name in (
                    "execution_boundary", "benchmark", "case_set", "treatment_set", "comparison_track_id",
                    "primary_endpoint", "metrics", "observation_counts", "observation_matrix",
                    "case_result_matrix", "treatment_summaries")})
        run = HistoricalRun(terminal.generation_id, execute.artifact_store.root,
                            "Completed", "success", "Saved", "")
        current, prepared = prepare_presentation(run)
        self.assertTrue(prepared.treatments_contaminated)
        save_presentation(execute.artifact_store.root, terminal.generation_id, current, prepared)
        _, prepared = prepare_presentation(run)
        self.assertTrue(prepared.treatments_contaminated)
        from AgMark.gui.projection.workspace.projector import render_workspace
        workspace = render_workspace(prepared)
        for page in workspace.ordered_pages:
            self.addCleanup(page.deleteLater)
        self.assertTrue(workspace.evidence.projection.treatments_contaminated)
        self.assertEqual(content_entries(plan.to_dict()), content_entries(terminal.run_outcome()))

    def test_execution_rejects_replacement_bytes_and_plan_cannot_drop_identity(self):
        composition, _, request, plan, execution = self.resolve(True)
        prompts = list(execution.treatment_prompts)
        prompts[0] = TreatmentPrompt(prompts[0].treatment_id, b"replacement")
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            _validated_treatment_prompts(plan, prompts)
        extensions = dict(request.extensions)
        del extensions[CONTENT]
        with self.assertRaisesRegex(ValueError, "frozen content"):
            composition.session.build_plan(replace(request, extensions=extensions))

    def test_preview_and_retained_workspace_ignore_stale_refresh(self):
        from AgMark.gui.application.session_boundary import PlanningSessionApplicationBoundary
        from AgMark.gui.application.projector import SharedApplicationProjector
        from AgMark.gui.projection.workspace.projector import SharedWorkspaceProjector
        composition, resolver, _, dirty_plan, _ = self.resolve(True)
        boundary = PlanningSessionApplicationBoundary(session=composition.session, request_resolver=resolver)
        boundary.discover()
        authority = composition.authority
        projector = SharedApplicationProjector(boundary,
            runner_sources=authority.runner_sources, benchmark_candidates=authority.benchmark_candidates,
            repository_root=_REPOSITORY_ROOT)
        intent = SidebarInputSnapshot(
            benchmark="arcgrav.authority-resolution.benchmark.core@2.0.0",
            runner="arcgrav.mock-model.runner@1.0.0", model="mock-base::scenario:completed",
            credential="", temperature=None, max_tokens=None, additional_controls=())
        original = Path.read_bytes
        def changed(path):
            data = original(path)
            return data + b" changed" if path == _PROMPT else data
        with patch.object(Path, "read_bytes", changed):
            preview = projector.sidebar_from_intent(intent)
        self.assertTrue(preview.treatments_contaminated)
        self.assertTrue(preview.build_plan_available)
        clean_preview = projector.sidebar_from_intent(intent)
        self.assertFalse(clean_preview.treatments_contaminated)
        window = BenchmarkShellWindow(sidebar_projection=replace(preview, build_plan_available=False),
            application_icon=arcgrav_application_icon())
        self.addCleanup(window.deleteLater)
        workspace_projector = SharedWorkspaceProjector(SimpleNamespace())
        window.set_workspace_projection(workspace_projector.active_execution("generation-dirty", dirty_plan))
        window.set_sidebar_projection(replace(clean_preview, build_plan_available=False))
        self.assertFalse(window.workspace_tabs.isTabEnabled(4))
        window.set_sidebar_projection(SidebarProjection(
            benchmark_options=("arcgrav.custom.benchmark.core@1.0.0",),
            selected_benchmark="arcgrav.custom.benchmark.core@1.0.0"))
        self.assertTrue(window.workspace_tabs.isTabVisible(4))
        self.assertFalse(window.workspace_tabs.isTabEnabled(4))
        self.assertTrue(window.workspace_pages["Evidence"].projection.treatments_contaminated)
        _, _, _, clean_plan, _ = self.resolve()
        window.set_workspace_projection(workspace_projector.active_execution("generation-clean", clean_plan))
        self.assertTrue(window.workspace_tabs.isTabEnabled(4))
        self.assertTrue(window.workspace_tabs.tabIcon(4).isNull())

    def test_case_and_treatment_manifest_mismatches_still_block_discovery(self):
        original = Path.read_bytes
        for suffix in ("cases/v1.0.0/arb-core-001.json", "treatments/v2.0.0/treatment-set.json"):
            target = _REPOSITORY_ROOT / "AgMark/Authority_Resolution_Benchmark" / suffix
            def changed(path):
                data = original(path)
                return data + b" " if path == target else data
            with self.subTest(suffix=suffix), patch.object(Path, "read_bytes", changed):
                composition = compose_repository_planning_session(_REPOSITORY_ROOT)
                self.assertFalse(any(b.registration_id == "arcgrav.authority-resolution.benchmark.core"
                    for b in composition.authority.discovery.benchmarks))

    def test_warning_position_red_icons_disabled_tabs_and_clean_transition(self):
        projection = SidebarProjection(treatments_contaminated=True)
        window = BenchmarkShellWindow(sidebar_projection=projection, application_icon=arcgrav_application_icon())
        self.addCleanup(window.deleteLater)
        window.show()
        QApplication.processEvents()
        self.assertTrue(window.contamination_warning.isVisible())
        layout = window.contamination_warning.parentWidget().layout()
        self.assertEqual(layout.indexOf(window.benchmark_input) + 1, layout.indexOf(window.contamination_warning))
        self.assertLess(window.contamination_icon.x(), window.contamination_text.x())
        self.assertIn("#F0212D", window.contamination_text.styleSheet())
        for label in ("Verification", "Reports"):
            index = WORKSPACE_TAB_LABELS.index(label)
            self.assertTrue(window.workspace_tabs.isTabVisible(index))
            self.assertFalse(window.workspace_tabs.isTabEnabled(index))
            icon = window.workspace_tabs.tabIcon(index)
            self.assertFalse(icon.isNull())
            pixels = icon.pixmap(18, 18, QIcon.Mode.Disabled).toImage()
            self.assertTrue(any(pixels.pixelColor(x, y).red() > 180 and pixels.pixelColor(x, y).green() < 100
                                for x in range(18) for y in range(18)))
        self.assertTrue(window.workspace_tabs.isTabEnabled(WORKSPACE_TAB_LABELS.index("Evidence")))
        for contaminated_value in (False, True, False):
            window.set_sidebar_projection(replace(projection, treatments_contaminated=contaminated_value))
            self.assertEqual(contaminated_value, window.contamination_warning.isVisible())
            self.assertEqual(not contaminated_value, window.workspace_tabs.isTabEnabled(4))
