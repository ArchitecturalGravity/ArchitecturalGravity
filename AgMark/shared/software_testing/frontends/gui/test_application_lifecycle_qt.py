"""Production GUI/shared lifecycle integration coverage."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from threading import get_ident
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.application import BenchmarkDesktopApplication, RunnerTestResult
from AgMark.gui.diagnostics import EnvironmentDiagnosticEntry
from AgMark.gui.shell.window import (
    PYSIDE6_AVAILABLE,
    SidebarChoiceControlProjection,
    SidebarInputSnapshot,
    SidebarPrerequisiteDiagnosticProjection,
    SidebarProjection,
)
from AgMark.shared.application import (
    ApplicationExecutionRequest,
    ApplicationPlanRequest,
    ApplicationRegistrationSource,
    ApplicationReportRequest,
    ApplicationRunDeletion,
    PlanningApplicationSession,
)
from AgMark.shared.evaluation import IdentityRef as ReportingIdentityRef
from AgMark.shared.reporting import (
    GeneratedReportBundle,
    GeneratedReportComponent,
    ObservationCounts,
    ReportArtifactRef,
)
from AgMark.shared.runtime.artifacts import (
    ArtifactRecord,
    FilesystemArtifactStore,
    PublicationDestination,
)
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    AcceptedRun,
    BlockedRun,
    PlannedCaseInput,
    TreatmentCaseInput,
    TreatmentPrompt,
)
from AgMark.shared.validation import (
    BenchmarkDiscoveryCandidate,
    validate_registration_binding_outcome,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QApplication


_SECRET = "transient-frontend-secret"


def _registration(registration_id: str, kind: str) -> dict[str, object]:
    return {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "extensions": {},
        "registration_id": registration_id,
        "registration_version": "1.0.0",
        "registration_kind": kind,
        "status": "active",
        "contracts": [],
        "implementation_artifacts": [],
        "capabilities": [f"{kind}-capability"],
        "limitations": [],
    }


def _validated(registration: dict[str, object], source_id: str):
    return validate_registration_binding_outcome(
        registration,
        expected_registration_id=registration["registration_id"],
        expected_registration_version=registration["registration_version"],
        contract_requirements=(),
        artifact_sources=(),
        allowed_artifact_roots=("AgMark",),
        source_id=source_id,
    )


def _session() -> tuple[PlanningApplicationSession, str]:
    benchmark_registration = _registration("frontend.benchmark", "benchmark")
    benchmark_validation = _validated(
        benchmark_registration,
        "frontend-benchmark-registration",
    )
    runner_registration = _registration("frontend.runner", "runner")
    runner_validation = _validated(
        runner_registration,
        "frontend-runner-registration",
    )
    benchmark_candidate = BenchmarkDiscoveryCandidate(
        package_root="AgMark/Frontend_Test_Benchmark",
        registration_source_id="frontend-benchmark-registration",
        registration=benchmark_registration,
        registration_validation=benchmark_validation,
    )
    runner_source = ApplicationRegistrationSource(
        registration_source_id="frontend-runner-registration",
        registration=runner_registration,
        registration_validation=runner_validation,
    )
    return (
        PlanningApplicationSession(
            benchmark_candidates=(benchmark_candidate,),
            runner_sources=(runner_source,),
        ),
        benchmark_validation.registration_sha256,
    )


def _artifact_record(generation_id: str, suffix: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=f"{generation_id}:{suffix}",
        role=suffix,
        reference=f"{generation_id}/{suffix}.json",
        sha256="sha256:" + "4" * 64,
        provenance="frontend-lifecycle-test",
        media_type="application/json",
        encoding="utf-8",
    )


def _accepted_run(generation_id: str) -> AcceptedRun:
    value = object.__new__(AcceptedRun)
    object.__setattr__(value, "generation_id", generation_id)
    object.__setattr__(
        value,
        "artifact_index",
        SimpleNamespace(artifacts=(_artifact_record(generation_id, "result"),)),
    )
    return value


def _blocked_run(generation_id: str) -> BlockedRun:
    value = object.__new__(BlockedRun)
    object.__setattr__(value, "generation_id", generation_id)
    object.__setattr__(value, "reason_code", "frontend-blocked")
    object.__setattr__(value, "diagnostics", ("blocked-by-shared-authority",))
    object.__setattr__(
        value,
        "artifact_manifest",
        SimpleNamespace(
            retained_diagnostics=(_artifact_record(generation_id, "diagnostic"),)
        ),
    )
    return value


def _report_component(
    artifact_id: str,
    *,
    media_type: str = "application/json",
) -> GeneratedReportComponent:
    return GeneratedReportComponent(
        artifact_id=artifact_id,
        reference=f"generated/{artifact_id}",
        data=f"retained:{artifact_id}".encode("utf-8"),
        media_type=media_type,
        encoding="utf-8",
    )


def _report_bundle(report_id: str) -> GeneratedReportBundle:
    return GeneratedReportBundle(
        report_document={
            "report_id": report_id,
            "accepted_generation_id": "generation-frontend-accepted",
            "status": "complete",
            "generated_at": "2026-09-21T00:00:00Z",
        },
        canonical_evidence_document={
            "execution_boundary_fingerprint": "sha256:" + "5" * 64,
            "treatment_summaries": (
                {
                    "treatment_id": "treatment-a",
                    "availability": {"state": "scored"},
                    "value": 1.0,
                },
            ),
        },
        report_manifest={
            "manifest_id": "frontend-manifest",
            "generated_at": "2026-09-21T00:00:00Z",
        },
        report=_report_component(f"{report_id}:machine"),
        canonical_evidence=_report_component(f"{report_id}:evidence"),
        human=_report_component(f"{report_id}:human", media_type="text/markdown"),
        manifest=_report_component(f"{report_id}:manifest"),
    )


class _Resolver:
    def __init__(
        self,
        *,
        root: Path,
        store: FilesystemArtifactStore,
        benchmark_sha256: str,
        generation_id: str,
    ) -> None:
        self.root = root
        self.store = store
        self.benchmark_sha256 = benchmark_sha256
        self.generation_id = generation_id
        self.plan_intents: list[SidebarInputSnapshot] = []
        self.execution_credentials: list[str] = []
        self.worker_threads: list[int] = []

    def resolve_plan_request(self, intent, discovery):
        self.worker_threads.append(get_ident())
        self.plan_intents.append(intent)
        benchmark = IdentityRef(
            discovery.benchmarks[0].registration_id,
            discovery.benchmarks[0].registration_version,
            sha256=self.benchmark_sha256,
        )
        case_set = IdentityRef(
            "frontend.case-set",
            "1.0.0",
            sha256="sha256:" + "1" * 64,
        )
        treatment_set = IdentityRef(
            "frontend.treatment-set",
            "1.0.0",
            sha256="sha256:" + "2" * 64,
        )
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-frontend-production-binding",
            framework=IdentityRef("arcgrav.framework", "1.0.0"),
            runner=IdentityRef(
                discovery.runners[0].registration_id,
                discovery.runners[0].registration_version,
            ),
            provider_runtime=ProviderRuntimeIdentity(
                runtime_id="frontend.runtime",
                runtime_version="1.0.0",
                provider=None,
                access_method="in_process",
                model=intent.model,
            ),
            controls={"memory_policy": "disabled"},
            environment={"runtime_family": "provider-free"},
        )
        return ApplicationPlanRequest(
            benchmark=benchmark,
            case_set=case_set,
            treatment_set=treatment_set,
            cases=(PlannedCaseInput("case-1", "sha256:" + "3" * 64),),
            treatments=("treatment-a",),
            repetitions=intent.iterations,
            execution_boundary=boundary,
            golden_required=False,
        )

    def resolve_execution_request(
        self,
        plan_request,
        accepted_snapshot,
        *,
        credential,
        runner_transient_controls=(),
    ):
        del accepted_snapshot, runner_transient_controls
        self.worker_threads.append(get_ident())
        self.execution_credentials.append(credential)
        return ApplicationExecutionRequest(
            generation_id=self.generation_id,
            benchmark=plan_request.benchmark,
            case_set=plan_request.case_set,
            treatment_set=plan_request.treatment_set,
            execution_boundary=plan_request.execution_boundary,
            benchmark_root=self.root,
            artifact_store=self.store,
            repository_root=self.root,
            runner_registration={},
            case_inputs=(TreatmentCaseInput("case-1", b"case"),),
            treatment_prompts=(TreatmentPrompt("treatment-a", b"prompt"),),
            scoring_definitions=(),
            transient_values={"credential": credential},
        )

    def resolve_report_request(self, retained_run):
        self.worker_threads.append(get_ident())
        generation_id = retained_run.generation_id
        return ApplicationReportRequest(
            generation_id=generation_id,
            execution_boundary=ReportArtifactRef(
                artifact_id="execution-boundary",
                sha256="sha256:" + "a" * 64,
                reference=f"{generation_id}/execution-boundary.json",
                availability="retained",
            ),
            benchmark=ReportingIdentityRef("frontend.benchmark", "1.0.0"),
            case_set=ReportingIdentityRef("frontend.case-set", "1.0.0"),
            treatment_set=ReportingIdentityRef("frontend.treatment-set", "1.0.0"),
            comparison_track_id="frontend-track",
            primary_endpoint=ReportingIdentityRef("frontend.metric", "1.0.0"),
            metrics=(),
            observation_counts=ObservationCounts(
                planned=0,
                finalized=0,
                completed=0,
                scored=0,
                failed=0,
                missing=0,
                excluded=0,
                non_scorable=0,
            ),
            observation_matrix=(),
            case_result_matrix=(),
            treatment_summaries=(),
            report_id="frontend-report",
            report_version="1.0.0",
            status="complete",
            sections={},
            report_manifest_id="frontend-manifest",
            generated_at="2026-09-21T00:00:00Z",

            input_evidence_set_id="frontend-evidence",
            generator=ReportingIdentityRef("frontend.generator", "1.0.0"),
            procedure_id="frontend.report",
            procedure_version="1.0.0",
            command_or_procedure="registered frontend report",
            report_reference="generated/report.json",
            canonical_evidence_reference="generated/canonical-evidence.json",
            human_reference="generated/report.md",
            manifest_reference="generated/report-manifest.json",
        )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ProductionSharedLifecycleGuiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name).resolve()
        self.store = FilesystemArtifactStore(
            PublicationDestination.benchmark_owned(
                self.root / "evidence",
                benchmark_root=self.root,
            )
        )
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.black)
        self.icon = QIcon(pixmap)

    def _wait_until(self, predicate, message: str, timeout: float = 4.0) -> None:
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            sleep(0.01)
        self.fail(message)

    def _application_for(
        self,
        generation_id: str,
        *,
        environment_entries=(),
        console_preferences=None,
        initial_sidebar_projection=None,
        authority_dispatcher=None,
        failure_handler=None,
    ):
        session, benchmark_sha256 = _session()
        resolver = _Resolver(
            root=self.root,
            store=self.store,
            benchmark_sha256=benchmark_sha256,
            generation_id=generation_id,
        )
        application = BenchmarkDesktopApplication.from_planning_session(
            application_icon=self.icon,
            session=session,
            request_resolver=resolver,
            console_preferences=console_preferences,
            initial_sidebar_projection=initial_sidebar_projection,
            environment_entries=environment_entries,
            authority_dispatcher=authority_dispatcher,
            failure_handler=failure_handler,
        )
        self.addCleanup(application.window.deleteLater)
        return application, session, resolver

    def test_runner_test_updates_environment_and_status_without_mutating_planning(self) -> None:
        application, session, _resolver = self._application_for(
            "generation-runner-test",
            initial_sidebar_projection=SidebarProjection(
                model_options=("frontend-model", "alternate-model"),
                selected_model="frontend-model",
                additional_controls=(
                    SidebarChoiceControlProjection(
                        control_name="profile",
                        label="Profile",
                        options=("default", "custom"),
                        selected_value="default",
                    ),
                ),
                build_plan_available=True,
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        self.assertIsNone(session.prepared_plan)
        self.assertIsNone(application.window.current_run_status)

        application.window.model_input.set_value("alternate-model")
        application.window.credential_input.set_value("transient-test-secret")
        application.window.additional_control_inputs["profile"].set_value("custom")
        QApplication.processEvents()

        sidebar_before = application.window.sidebar_input_snapshot()
        status_before = (
            application.window.application_readiness_status.label,
            application.window.application_readiness_status.tone,
        )
        environment_before = application.environment_projection.entries

        passed = RunnerTestResult(
            selected_runner=sidebar_before.runner or "frontend.runner@1.0.0",
            runner_id="frontend.runner",
            runner_version="1.0.0",
            model=sidebar_before.model or "alternate-model",
            submitted=True,
            terminal_status="completed",
            response_preview="Echo: test",
        )
        with patch.object(
            application.shared_application_boundary,
            "test_runner",
            return_value=passed,
        ):
            application.request_test_runner(sidebar_before)
        QApplication.processEvents()

        self.assertEqual(
            sidebar_before,
            application.window.sidebar_input_snapshot(),
        )
        self.assertIsNone(session.prepared_plan)
        self.assertIsNone(application.window.current_run_status)
        self.assertEqual(
            status_before,
            (
                application.window.application_readiness_status.label,
                application.window.application_readiness_status.tone,
            ),
        )
        self.assertEqual(
            ("Test passed", "success"),
            (application.window.connectivity_status.label,
             application.window.connectivity_status.tone),
        )
        self.assertEqual(
            environment_before,
            tuple(
                entry
                for entry in application.environment_projection.entries
                if entry.source != "Runner Test"
            ),
        )
        test_entries = tuple(
            entry
            for entry in application.environment_projection.entries
            if entry.source == "Runner Test"
        )
        self.assertEqual(1, len(test_entries))
        self.assertEqual("ready", test_entries[0].state)
        self.assertIn(
            "Echo: test completed with a retained response.",
            application.environment_projection.render(),
        )

        failed = RunnerTestResult(
            selected_runner=passed.selected_runner,
            diagnostics=("diagnostic failure",),
        )
        with patch.object(
            application.shared_application_boundary,
            "test_runner",
            return_value=failed,
        ):
            application.request_test_runner(sidebar_before)
        QApplication.processEvents()

        self.assertEqual(
            sidebar_before,
            application.window.sidebar_input_snapshot(),
        )
        self.assertEqual(
            status_before,
            (
                application.window.application_readiness_status.label,
                application.window.application_readiness_status.tone,
            ),
        )
        self.assertEqual(
            ("Test failed", "error"),
            (application.window.connectivity_status.label,
             application.window.connectivity_status.tone),
        )
        test_entries = tuple(
            entry
            for entry in application.environment_projection.entries
            if entry.source == "Runner Test"
        )
        self.assertEqual(1, len(test_entries))
        self.assertEqual("failure", test_entries[0].state)

    def test_rebuilding_accepted_plan_requires_fresh_acceptance(self) -> None:
        application, session, resolver = self._application_for(
            "generation-rebuilt-plan",
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential="",
            temperature=None,
            max_tokens=None,
        )
        application.request_build_plan(intent)
        QApplication.processEvents()
        application.request_accept_plan()
        QApplication.processEvents()

        self.assertIsNotNone(session.accepted_snapshot)
        self.assertIsNotNone(application.window.current_run_status)
        self.assertEqual("Accepted", application.window.current_run_status.label)

        application.request_build_plan(intent)
        QApplication.processEvents()

        self.assertEqual(2, len(resolver.plan_intents))
        self.assertIsNotNone(session.prepared_plan)
        self.assertIsNone(session.accepted_snapshot)
        self.assertIsNotNone(application.window.current_run_status)
        self.assertEqual("Pending", application.window.current_run_status.label)
        self.assertIsNotNone(application.window.accept_plan_button)
        self.assertTrue(application.window.accept_plan_button.isEnabled())
        self.assertIsNotNone(application.window.start_benchmark_button)
        self.assertFalse(application.window.start_benchmark_button.isEnabled())
        self.assertEqual(
            "Plan ready",
            application.window.application_readiness_status.label,
        )

        application.request_accept_plan()
        QApplication.processEvents()

        self.assertIsNotNone(session.accepted_snapshot)
        self.assertIsNotNone(application.window.current_run_status)
        self.assertEqual("Accepted", application.window.current_run_status.label)

    def test_run_history_stays_independent_when_a_new_plan_is_built(self) -> None:
        generation_id = "generation-history-complete"
        dispatch_state = {"defer": False, "pending": []}

        def dispatch(operation):
            if dispatch_state["defer"]:
                dispatch_state["pending"].append(operation)
                return operation
            return operation()

        application, _session, _resolver = self._application_for(
            generation_id,
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
            ),
            authority_dispatcher=dispatch,
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential="",
            temperature=None,
            max_tokens=None,
        )

        application.request_build_plan(intent)
        QApplication.processEvents()
        self.assertEqual("Current Run", application.window.current_run_heading.text())
        self.assertEqual("Pending", application.window.current_run_status.label)
        self.assertEqual({}, application.window.run_rows)
        self.assertIsNotNone(application.window.runs_empty_label)

        application.request_accept_plan()
        QApplication.processEvents()
        self.assertEqual("Accepted", application.window.current_run_status.label)
        self.assertEqual({}, application.window.run_rows)
        self.assertIsNotNone(application.window.runs_empty_label)

        accepted = _accepted_run(generation_id)

        def finish_execution(_request):
            QApplication.processEvents()
            self.assertEqual("Running", application.window.current_run_status.label)
            self.assertIn(generation_id, application.window.run_rows)
            running_row = application.window.run_rows[generation_id]
            self.assertEqual("Running", running_row.status_badge.label)
            self.assertEqual("status-active", running_row.status_badge.icon_key)
            return accepted

        with patch.object(
            application.shared_application_boundary.session,
            "execute_accepted_run",
            side_effect=finish_execution,
        ):
            application.request_start_benchmark()
        QApplication.processEvents()

        self.assertEqual("Completed", application.window.current_run_status.label)
        self.assertEqual("Current Run", application.window.current_run_heading.text())
        self.assertEqual((generation_id,), tuple(application.window.run_rows))
        self.assertEqual(
            generation_id,
            application.window.workspace_projection_run_id,
        )
        completed_workspace_pages = tuple(
            application.window.workspace_pages.values()
        )
        completed_row = application.window.run_rows[generation_id]
        completed_timestamp = completed_row.timestamp_label.text()
        self.assertEqual("Completed", completed_row.status_badge.label)
        self.assertEqual("status-success", completed_row.status_badge.icon_key)
        self.assertNotEqual(Qt.FocusPolicy.NoFocus, completed_row.focusPolicy())

        # Build Plan unmounts the completed generation synchronously,
        # before the background planning operation is allowed to run.
        dispatch_state["defer"] = True
        application.request_build_plan(intent)

        self.assertEqual(1, len(dispatch_state["pending"]))
        self.assertIsNone(application.window.workspace_projection_run_id)
        self.assertTrue(
            all(
                page not in completed_workspace_pages
                for page in application.window.workspace_pages.values()
            )
        )

        dispatch_state["defer"] = False
        dispatch_state["pending"].pop(0)()
        QApplication.processEvents()

        self.assertEqual("Current Run", application.window.current_run_heading.text())
        self.assertEqual("Pending", application.window.current_run_status.label)
        self.assertIsNone(application.window.selected_run_id)
        self.assertIsNone(application.window.workspace_projection_run_id)
        self.assertIsNone(
            application.shared_application_boundary.selected_terminal
        )

        application.request_accept_plan()
        QApplication.processEvents()

        self.assertEqual("Accepted", application.window.current_run_status.label)
        self.assertIsNone(application.window.selected_run_id)
        self.assertIsNone(application.window.workspace_projection_run_id)
        self.assertIsNone(
            application.shared_application_boundary.selected_terminal
        )

        with patch.object(
            application.shared_application_boundary.session,
            "select_run",
            return_value=accepted,
        ):
            application.request_select_run(generation_id)
        QApplication.processEvents()

        self.assertEqual("Prior Run", application.window.current_run_heading.text())
        self.assertEqual("Completed", application.window.current_run_status.label)
        self.assertIsNone(application.window.accept_plan_button)
        self.assertIsNone(application.window.start_benchmark_button)
        self.assertIsNotNone(application.window.delete_run_button)
        self.assertEqual(
            "destructive",
            application.window.delete_run_button.role,
        )

        application.request_build_plan(intent)
        QApplication.processEvents()

        self.assertEqual("Current Run", application.window.current_run_heading.text())
        self.assertEqual("Pending", application.window.current_run_status.label)
        self.assertIsNone(application.window.selected_run_id)
        self.assertIsNone(application.window.workspace_projection_run_id)
        self.assertEqual((generation_id,), tuple(application.window.run_rows))
        self.assertEqual(
            "Completed",
            application.window.run_rows[generation_id].status_badge.label,
        )
        self.assertEqual(
            completed_timestamp,
            application.window.run_rows[generation_id].timestamp_label.text(),
        )
        self.assertNotEqual(
            "Not accepted",
            application.window.run_rows[generation_id].timestamp_label.text(),
        )
        self.assertIsNone(
            application.shared_application_boundary.selected_terminal
        )

    def test_unstarted_plans_do_not_enter_runs_history(self) -> None:
        application, _session, _resolver = self._application_for(
            "generation-start-only",
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential="",
            temperature=None,
            max_tokens=None,
        )

        for _ in range(2):
            application.request_build_plan(intent)
            QApplication.processEvents()
            self.assertEqual("Pending", application.window.current_run_status.label)
            self.assertEqual({}, application.window.run_rows)
            self.assertIsNotNone(application.window.runs_empty_label)

        application.request_accept_plan()
        QApplication.processEvents()
        self.assertEqual("Accepted", application.window.current_run_status.label)
        self.assertEqual({}, application.window.run_rows)
        self.assertIsNotNone(application.window.runs_empty_label)

        application.request_build_plan(intent)
        QApplication.processEvents()
        self.assertEqual("Pending", application.window.current_run_status.label)
        self.assertEqual({}, application.window.run_rows)
        self.assertIsNotNone(application.window.runs_empty_label)

    def test_confirmed_prior_run_deletion_clears_immediately_and_stays_cleared(self) -> None:
        generation_id = "generation-delete-prior"
        application, _session, _resolver = self._application_for(
            generation_id,
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential="",
            temperature=None,
            max_tokens=None,
        )
        application.request_build_plan(intent)
        QApplication.processEvents()
        application.request_accept_plan()
        QApplication.processEvents()

        accepted = _accepted_run(generation_id)
        with patch.object(
            application.shared_application_boundary.session,
            "execute_accepted_run",
            return_value=accepted,
        ):
            application.request_start_benchmark()
        QApplication.processEvents()

        with patch.object(
            application.shared_application_boundary.session,
            "select_run",
            return_value=accepted,
        ):
            application.request_select_run(generation_id)
        QApplication.processEvents()

        self.assertEqual("Prior Run", application.window.current_run_heading.text())
        self.assertIn(generation_id, application.window.run_rows)
        self.assertIsNotNone(application.window.delete_run_button)

        pending_operations: list[object] = []
        application._authority_dispatcher = pending_operations.append
        application.window._confirm_delete_run = lambda _run_id: True

        with patch.object(
            application.shared_application_boundary.session,
            "delete_run",
            return_value=ApplicationRunDeletion(generation_id=generation_id),
        ) as delete_run:
            application.window.delete_run_button.click()
            QApplication.processEvents()

            self.assertEqual(1, len(pending_operations))
            self.assertNotIn(generation_id, application.window.run_rows)
            self.assertIsNone(application.window.current_run_status)
            self.assertIsNone(application.window.current_run_identity_label)
            self.assertIsNotNone(application.window.current_run_empty_state_card)
            self.assertIsNone(application.window.workspace_projection_run_id)
            self.assertEqual(
                f"Deleting run {generation_id}",
                application.window.application_readiness_status.label,
            )

            pending_operations.pop()()
            QApplication.processEvents()

        delete_run.assert_called_once_with(generation_id)
        self.assertNotIn(generation_id, application.window.run_rows)
        self.assertIsNone(application.window.current_run_status)
        self.assertIsNone(application.window.current_run_identity_label)
        self.assertIsNotNone(application.window.current_run_empty_state_card)
        self.assertIsNone(application.window.workspace_projection_run_id)
        self.assertEqual(
            f"Run {generation_id} deleted",
            application.window.application_readiness_status.label,
        )

    def test_multi_run_delete_clears_main_state_and_preserves_other_history(self) -> None:
        first_generation = "generation-delete-older"
        current_generation = "generation-delete-current"
        application, _session, resolver = self._application_for(
            first_generation,
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential="",
            temperature=None,
            max_tokens=None,
        )
        first = _accepted_run(first_generation)
        application.request_build_plan(intent)
        application.request_accept_plan()
        with patch.object(
            application.shared_application_boundary.session,
            "execute_accepted_run",
            return_value=first,
        ):
            application.request_start_benchmark()
        QApplication.processEvents()

        resolver.generation_id = current_generation
        current = _accepted_run(current_generation)
        application.request_build_plan(intent)
        application.request_accept_plan()
        with patch.object(
            application.shared_application_boundary.session,
            "execute_accepted_run",
            return_value=current,
        ):
            application.request_start_benchmark()
        QApplication.processEvents()

        self.assertEqual(
            {first_generation, current_generation},
            set(application.window.run_rows),
        )
        with patch.object(
            application.shared_application_boundary.session,
            "select_run",
            return_value=first,
        ):
            application.request_select_run(first_generation)
        QApplication.processEvents()
        self.assertEqual("Prior Run", application.window.current_run_heading.text())

        application.window._confirm_delete_run = lambda _run_id: True
        with patch.object(
            application.shared_application_boundary.session,
            "delete_run",
            return_value=ApplicationRunDeletion(generation_id=first_generation),
        ) as delete_run:
            application.window.delete_run_button.click()
        QApplication.processEvents()

        delete_run.assert_called_once_with(first_generation)
        self.assertNotIn(first_generation, application.window.run_rows)
        self.assertIn(current_generation, application.window.run_rows)
        self.assertIsNone(application.window.selected_run_id)
        self.assertIsNone(application.window.current_run_status)
        self.assertIsNone(application.window.current_run_identity_label)
        self.assertIsNotNone(application.window.current_run_empty_state_card)
        self.assertIsNone(application.window.workspace_projection_run_id)

    def test_failed_prior_run_deletion_restores_authoritative_prior_run(self) -> None:
        generation_id = "generation-delete-fails"
        application, _session, _resolver = self._application_for(
            generation_id,
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential="",
            temperature=None,
            max_tokens=None,
        )
        application.request_build_plan(intent)
        application.request_accept_plan()

        accepted = _accepted_run(generation_id)
        with patch.object(
            application.shared_application_boundary.session,
            "execute_accepted_run",
            return_value=accepted,
        ):
            application.request_start_benchmark()
        with patch.object(
            application.shared_application_boundary.session,
            "select_run",
            return_value=accepted,
        ):
            application.request_select_run(generation_id)
        QApplication.processEvents()

        application.window._confirm_delete_run = lambda _run_id: True
        with patch.object(
            application.shared_application_boundary.session,
            "delete_run",
            side_effect=RuntimeError("retained storage unavailable"),
        ):
            application.window.delete_run_button.click()
        QApplication.processEvents()

        self.assertIn(generation_id, application.window.run_rows)
        self.assertEqual("Prior Run", application.window.current_run_heading.text())
        self.assertEqual(generation_id, application.window.current_run_identity_label.text())
        self.assertEqual(
            "Delete Run failed",
            application.window.application_readiness_status.label,
        )

    def test_acceptance_prerequisite_preserves_prepared_current_run(self) -> None:
        blocker = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="acceptance-review",
            message="Acceptance review is unresolved.",
            remediation="Complete the acceptance review.",
            operation="acceptance",
        )
        application, session, _resolver = self._application_for(
            "generation-acceptance-blocked",
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
                prerequisite_diagnostics=(blocker,),
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential="",
            temperature=None,
            max_tokens=None,
        )
        application.request_build_plan(intent)
        QApplication.processEvents()

        prepared = session.prepared_plan
        self.assertIsNotNone(prepared)
        self.assertIsNotNone(application.window.current_run_status)
        self.assertEqual("Pending", application.window.current_run_status.label)
        self.assertIsNotNone(application.window.accept_plan_button)
        self.assertFalse(application.window.accept_plan_button.isEnabled())

        fingerprint = prepared.execution_boundary_fingerprint
        application.request_accept_plan()
        QApplication.processEvents()

        self.assertIsNone(session.accepted_snapshot)
        self.assertEqual(prepared, session.prepared_plan)
        self.assertEqual(
            fingerprint,
            application.shared_application_boundary.session.prepared_plan.execution_boundary_fingerprint,
        )
        self.assertEqual(
            "Accept Plan failed",
            application.window.application_readiness_status.label,
        )

    def test_execution_prerequisite_allows_plan_and_accept_but_blocks_start(self) -> None:
        blocker = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="runner-authentication",
            message="Execution authentication is unresolved.",
            remediation="Restore execution authentication.",
            operation="execution",
        )
        application, session, _resolver = self._application_for(
            "generation-execution-blocked",
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
                prerequisite_diagnostics=(blocker,),
            ),
            environment_entries=(
                EnvironmentDiagnosticEntry(
                    source="Startup",
                    state="warning",
                    summary="Informational startup warning.",
                ),
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential=_SECRET,
            temperature=None,
            max_tokens=None,
        )
        application.request_build_plan(intent)
        QApplication.processEvents()

        prepared = session.prepared_plan
        self.assertIsNotNone(prepared)
        self.assertIsNotNone(application.window.current_run_status)
        self.assertEqual("Pending", application.window.current_run_status.label)
        self.assertIsNotNone(application.window.accept_plan_button)
        self.assertTrue(application.window.accept_plan_button.isEnabled())
        self.assertIn(
            "Informational startup warning.",
            application.environment_projection.render(),
        )

        application.request_accept_plan()
        QApplication.processEvents()

        accepted = session.accepted_snapshot
        self.assertIsNotNone(accepted)
        self.assertIsNotNone(application.window.current_run_status)
        self.assertEqual("Accepted", application.window.current_run_status.label)
        self.assertIsNotNone(application.window.start_benchmark_button)
        self.assertFalse(application.window.start_benchmark_button.isEnabled())
        fingerprint = prepared.execution_boundary_fingerprint

        application.request_start_benchmark()
        QApplication.processEvents()

        self.assertEqual(prepared, session.prepared_plan)
        self.assertEqual(accepted, session.accepted_snapshot)
        self.assertEqual((), session.retained_run_ids)
        self.assertIsNotNone(application.window.current_run_status)
        self.assertEqual("Accepted", application.window.current_run_status.label)
        self.assertEqual(
            fingerprint,
            application.shared_application_boundary.session.prepared_plan.execution_boundary_fingerprint,
        )
        self.assertEqual(
            "Start Benchmark failed",
            application.window.application_readiness_status.label,
        )

    def test_started_execution_failure_routes_to_generation_diagnostics(self) -> None:
        generation_id = "generation-started-failure"
        application, session, _resolver = self._application_for(
            generation_id,
            initial_sidebar_projection=SidebarProjection(
                build_plan_available=True,
            ),
            authority_dispatcher=lambda operation: operation(),
        )
        application.show()
        QApplication.processEvents()

        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential="",
            temperature=None,
            max_tokens=None,
        )
        application.request_build_plan(intent)
        QApplication.processEvents()
        application.request_accept_plan()
        QApplication.processEvents()

        def fail_after_start(_request):
            QApplication.processEvents()
            self.assertEqual(
                generation_id,
                application.window.console_widget.state.active_generation_id,
            )
            self.assertIsNotNone(application.window.current_run_status)
            self.assertEqual("Running", application.window.current_run_status.label)
            raise RuntimeError("scoring failed after observations")

        with patch.object(
            session,
            "execute_accepted_run",
            side_effect=fail_after_start,
        ):
            application.request_start_benchmark()
        QApplication.processEvents()

        self.assertEqual(
            generation_id,
            application.window.console_widget.state.active_generation_id,
        )
        application.window.console_widget.set_active_tab("Diagnostics")
        diagnostics_text = application.window.console_widget.state.visible_text
        self.assertIn("Start Benchmark", diagnostics_text)
        self.assertIn("scoring failed after observations", diagnostics_text)
        self.assertEqual(
            "Start Benchmark failed",
            application.window.application_readiness_status.label,
        )

    def test_complete_shared_authority_lifecycle_projects_and_scrubs_credentials(self) -> None:
        gui_thread = get_ident()
        generation_id = "generation-frontend-accepted"
        application, session, resolver = self._application_for(generation_id)
        accepted = _accepted_run(generation_id)
        bundle = _report_bundle("frontend-report")

        with (
            patch.object(
                session,
                "execute_accepted_run",
                return_value=accepted,
            ) as execute,
            patch.object(session, "select_run", return_value=accepted) as select,
            patch.object(session, "completed_report", return_value=bundle) as report,
            patch.object(session, "completion_record", return_value={"status": "complete", "validation": {"status": "passed"}}),
            patch.object(
                AcceptedRun,
                "run_outcome",
                return_value={"status": "accepted"},
            ),
        ):
            application.show()
            boundary = application.shared_application_boundary

            self._wait_until(
                lambda: (
                    boundary.discovery is not None
                    and application.window.benchmark_input.options
                    == ("frontend.benchmark@1.0.0",)
                ),
                "shared discovery was not projected",
            )
            self.assertEqual(
                ("frontend.benchmark@1.0.0",),
                application.window.benchmark_input.options,
            )
            self.assertEqual(
                ("frontend.runner@1.0.0",),
                application.window.runner_input.options,
            )
            application.window.console_widget.set_active_tab("Environment")
            self.assertEqual(
                application.environment_projection.render(),
                application.window.console_widget.state.visible_text,
            )

            application.request_build_plan(
                SidebarInputSnapshot(
                    benchmark="frontend.benchmark@1.0.0",
                    runner="frontend.runner@1.0.0",
                    model="frontend-model",
                    credential=_SECRET,
                    temperature=None,
                    max_tokens=None,
                )
            )
            self._wait_until(
                lambda: (
                    boundary.plan_request is not None
                    and application.window.current_run_status is not None
                    and application.window.current_run_status.label == "Pending"
                ),
                "shared plan was not projected",
            )

            self.assertEqual("", resolver.plan_intents[0].credential)
            self.assertNotIn(_SECRET, repr(boundary.plan_request))
            self.assertEqual("", application.window.credential_input.value)
            self.assertIsNotNone(application.window.current_run_status)
            self.assertEqual("Pending", application.window.current_run_status.label)
            fingerprint = boundary.plan_request.execution_boundary.fingerprint
            self.assertEqual(
                fingerprint,
                application.shared_application_boundary.session.prepared_plan.execution_boundary_fingerprint,
            )

            application.request_accept_plan()
            self._wait_until(
                lambda: (
                    boundary.accepted_snapshot is not None
                    and application.window.current_run_status is not None
                    and application.window.current_run_status.label == "Accepted"
                ),
                "accepted snapshot was not projected",
            )
            self.assertEqual("Accepted", application.window.current_run_status.label)

            application.request_start_benchmark()
            self._wait_until(
                lambda: (
                    boundary.selected_terminal is accepted
                    and application.window.selected_run_id == generation_id
                    and application.window.console_widget.state.active_generation_id
                    == generation_id
                ),
                "accepted terminal result was not projected",
            )
            execute.assert_called_once()
            self.assertEqual([_SECRET], resolver.execution_credentials)
            self.assertIsNotNone(boundary.execution_request)
            self.assertIsNone(boundary.execution_request.transient_values)
            self.assertNotIn(_SECRET, repr(boundary.execution_request))
            self.assertEqual(generation_id, application.window.selected_run_id)
            self.assertEqual(
                generation_id,
                application.window.console_widget.state.active_generation_id,
            )
            self.assertEqual(
                generation_id,
                application.window.workspace_projection_run_id,
            )
            for label in ("Progress", "Results", "Reports", "Verification", "Evidence"):
                self.assertEqual(
                    generation_id,
                    application.window.workspace_pages[label].run_id,
                )
            console = application.window.console_widget
            self.assertFalse(
                console.append_live_output(
                    "generation-stale",
                    "stale-live-must-not-project",
                )
            )
            self.assertFalse(
                console.append_diagnostic(
                    "generation-stale",
                    "stale-diagnostic-must-not-project",
                )
            )
            self.assertFalse(
                console.set_raw_response(
                    "generation-stale",
                    "stale-raw-must-not-project",
                )
            )

            self.assertTrue(
                console.append_live_output(
                    generation_id,
                    "current-live-output",
                )
            )
            self.assertTrue(
                console.append_diagnostic(
                    generation_id,
                    "current-generation-diagnostic",
                )
            )
            retained_response = '{"response":"exact-retained-response"}'
            self.assertTrue(
                console.set_raw_response(
                    generation_id,
                    retained_response,
                )
            )

            console.set_active_tab("Live View")
            self.assertEqual("", console.state.visible_text)
            console.set_stream_live_view(True)
            self.assertIn("Input:\n", console.state.visible_text)
            self.assertIn("Output:\n" + retained_response, console.state.visible_text)
            self.assertNotIn("stale-live-must-not-project", console.state.visible_text)
            self.assertNotIn("stale-raw-must-not-project", console.state.visible_text)
            console.set_active_tab("Diagnostics")
            self.assertIn(
                "current-generation-diagnostic",
                console.state.visible_text,
            )
            self.assertNotIn(
                "stale-diagnostic-must-not-project",
                console.state.visible_text,
            )
            console.set_active_tab("Live View")
            self.assertTrue(console.state.visible_text.endswith(retained_response))
            self.assertNotIn("current-live-output", console.state.visible_text)
            self.assertNotIn(
                "current-generation-diagnostic",
                console.state.visible_text,
            )

            console.set_active_tab("Environment")
            environment_before_selection = console.state.visible_text
            self.assertEqual(
                application.environment_projection.render(),
                environment_before_selection,
            )
            self.assertNotIn("current-live-output", environment_before_selection)
            self.assertNotIn(
                "current-generation-diagnostic",
                environment_before_selection,
            )
            self.assertNotIn(retained_response, environment_before_selection)

            application.request_select_run(generation_id)
            self._wait_until(
                lambda: (
                    select.call_count == 1
                    and application.window.selected_run_id == generation_id
                    and not application._selecting_run
                ),
                "retained shared run was not selected",
            )
            self.assertEqual(generation_id, application.window.selected_run_id)
            self.assertEqual(
                generation_id,
                application.window.console_widget.state.active_generation_id,
            )
            self.assertEqual(
                environment_before_selection,
                application.window.console_widget.state.visible_text,
            )

            self.assertIs(bundle, boundary.report_bundle)
            self.assertEqual(("complete", None), boundary.report_state(generation_id))
            self.assertGreaterEqual(report.call_count, 1)
            self.assertEqual(
                "Runner not checked",
                application.window.connectivity_status.label,
            )
            self._wait_until(lambda: bool(application.window.workspace_pages["Reports"].projection.readable_content),
                             "automatic final report was not projected")
            reports_projection = application.window.workspace_pages["Reports"].projection
            self.assertTrue(reports_projection.readable_content)
            self.assertEqual(
                "frontend-report",
                reports_projection.report_id,
            )
            results_projection = application.window.workspace_pages["Results"].projection
            # This mocked command fixture has no accepted measurement evidence;
            # production must show unavailability rather than use report-only values.
            self.assertEqual((), results_projection.rows)
            self.assertIn("unavailable", results_projection.empty_state.lower())
            report_artifact_ids = {
                row.artifact_id
                for row in application.window.workspace_pages[
                    "Evidence"
                ].projection.artifacts.rows
            }
            self.assertIn("frontend-report:machine", report_artifact_ids)
            self.assertIn(
                f"{generation_id}:result",
                report_artifact_ids,
            )
            self.assertEqual(
                "passed",
                application.window.workspace_pages[
                    "Verification"
                ].projection.banner.status,
            )


        self.assertTrue(resolver.worker_threads)
        self.assertTrue(
            all(thread_id != gui_thread for thread_id in resolver.worker_threads),
            resolver.worker_threads,
        )

    def test_automatic_completion_failures_keep_evidence_without_final_report(self):
        from AgMark.shared.runtime.completion_diagnostics import completion_diagnostic
        for state in ("validation_failed", "report_failed", "not_applicable"):
            with self.subTest(state=state):
                generation_id = "generation-frontend-accepted"
                application, session, resolver = self._application_for(
                    generation_id, authority_dispatcher=lambda operation: operation())
                application.show()
                QApplication.processEvents()
                boundary = application.shared_application_boundary
                application.request_build_plan(SidebarInputSnapshot(
                    benchmark="frontend.benchmark@1.0.0", runner="frontend.runner@1.0.0",
                    model="frontend-model", credential="", temperature=None, max_tokens=None))
                application.request_accept_plan()
                accepted = _accepted_run(generation_id)
                with patch.object(session, "execute_accepted_run", return_value=accepted), patch.object(
                    session, "completion_record", return_value={"status": state,
                    "validation": {"diagnostic": "completion unavailable"},
                    "diagnostics": [completion_diagnostic("publication", "failed", PermissionError("secret /private/path"))]}), patch.object(
                    AcceptedRun, "run_outcome", return_value={"status": "accepted"}):
                    application.request_start_benchmark()
                QApplication.processEvents()
                self.assertIs(accepted, boundary.selected_terminal)
                self.assertIsNone(boundary.report_bundle)
                self.assertEqual((state, "completion unavailable"), boundary.report_state(generation_id))
                reports = application.window.workspace_pages["Reports"]
                self.assertEqual(state, reports.projection.generation_state)
                self.assertIsNone(reports.projection.report_id)
                self.assertIn("completion unavailable", reports.projection.empty_state)
                self.assertIn("Archive publication: failed", reports.completion_diagnostics_label.text())
                application.window.console_widget.set_active_tab("Diagnostics")
                diagnostic_text = application.window.console_widget.state.visible_text
                self.assertIn("Archive publication: failed", diagnostic_text)
                self.assertIn("PermissionError", diagnostic_text)
                self.assertNotIn("secret /private/path", diagnostic_text)
                self.assertTrue(application.window.workspace_pages["Evidence"].projection.artifacts.rows)
                self.assertTrue(callable(boundary.execution_request.report_request_factory))


    def test_new_application_session_starts_with_fresh_environment_state(self) -> None:
        preferences: dict[str, int] = {}
        first_entry = EnvironmentDiagnosticEntry(
            source="Session One",
            state="warning",
            summary="first-session-only-environment",
        )
        first_application, _, _ = self._application_for(
            "generation-session-one",
            environment_entries=(first_entry,),
            console_preferences=preferences,
        )
        first_application.show()
        self._wait_until(
            lambda: first_application.window.benchmark_input.options
            == ("frontend.benchmark@1.0.0",),
            "first application-session discovery was not projected",
        )
        first_application.window.console_widget.set_active_tab("Environment")
        self.assertIn(
            "first-session-only-environment",
            first_application.window.console_widget.state.visible_text,
        )

        first_application.window.console_widget.set_environment(
            "[WARNING] Session One: transient-prior-session-environment"
        )
        first_application.window.console_widget.record_splitter_height(311)
        self.assertIn(
            "transient-prior-session-environment",
            first_application.window.console_widget.state.visible_text,
        )
        first_application.window.close()
        QApplication.processEvents()

        second_entry = EnvironmentDiagnosticEntry(
            source="Session Two",
            state="ready",
            summary="second-session-only-environment",
        )
        second_application, _, _ = self._application_for(
            "generation-session-two",
            environment_entries=(second_entry,),
            console_preferences=preferences,
        )
        second_application.show()
        self._wait_until(
            lambda: second_application.window.benchmark_input.options
            == ("frontend.benchmark@1.0.0",),
            "second application-session discovery was not projected",
        )
        second_application.window.console_widget.set_active_tab("Environment")
        second_environment = second_application.window.console_widget.state.visible_text

        self.assertIn("second-session-only-environment", second_environment)
        self.assertNotIn("first-session-only-environment", second_environment)
        self.assertNotIn("transient-prior-session-environment", second_environment)
        self.assertEqual(
            second_application.environment_projection.render(),
            second_environment,
        )
        self.assertIsNot(
            first_application.environment_projection,
            second_application.environment_projection,
        )
        self.assertIsNot(
            first_application.window.console_widget.state,
            second_application.window.console_widget.state,
        )

    def test_operation_failures_route_by_scope_redact_and_preserve_custom_handler(self) -> None:
        generation_id = "generation-failure-routing"
        hook_observations: list[tuple[str, str, str]] = []
        application_holder: dict[str, object] = {}

        def failure_handler(command: str, _error: BaseException) -> None:
            application = application_holder["application"]
            hook_observations.append(
                (
                    command,
                    application.environment_projection.render(),
                    application.window.console_widget.state.visible_text,
                )
            )

        application, session, _resolver = self._application_for(
            generation_id,
            authority_dispatcher=lambda operation: operation(),
            failure_handler=failure_handler,
        )
        application_holder["application"] = application
        application.show()
        QApplication.processEvents()

        boundary = application.shared_application_boundary
        intent = SidebarInputSnapshot(
            benchmark="frontend.benchmark@1.0.0",
            runner="frontend.runner@1.0.0",
            model="frontend-model",
            credential=_SECRET,
            temperature=None,
            max_tokens=None,
        )

        application.window.console_widget.set_active_tab("Environment")
        with patch.object(
            boundary,
            "build_plan",
            side_effect=RuntimeError("token=pre-generation-secret"),
        ):
            application.request_build_plan(intent)
        QApplication.processEvents()

        environment_text = application.environment_projection.render()
        self.assertIn("Build Plan", environment_text)
        self.assertIn("token=<redacted>", environment_text)
        self.assertNotIn("pre-generation-secret", environment_text)
        self.assertEqual(
            environment_text,
            application.window.console_widget.state.visible_text,
        )
        self.assertIsNone(
            application.window.console_widget.state.active_generation_id
        )
        self.assertEqual("Build Plan failed", application.window.application_readiness_status.label)
        self.assertEqual("error", application.window.application_readiness_status.tone)
        self.assertEqual("build_plan", hook_observations[0][0])
        self.assertIn("token=<redacted>", hook_observations[0][1])

        accepted = _accepted_run(generation_id)
        application.request_build_plan(intent)
        application.request_accept_plan()
        with (
            patch.object(
                session,
                "execute_accepted_run",
                return_value=accepted,
            ),
            patch.object(
                AcceptedRun,
                "run_outcome",
                return_value={"status": "accepted"},
            ),
        ):
            application.request_start_benchmark()
        QApplication.processEvents()

        self.assertEqual(
            generation_id,
            application.window.console_widget.state.active_generation_id,
        )
        environment_before_bound_failure = application.environment_projection.render()
        application.window.console_widget.set_active_tab("Diagnostics")

        application._apply_failure("start_benchmark", RuntimeError("api_key=bound-generation-secret"), generation_id)
        QApplication.processEvents()

        diagnostics_text = application.window.console_widget.state.visible_text
        self.assertIn("Start Benchmark", diagnostics_text)
        self.assertIn("api_key=<redacted>", diagnostics_text)
        self.assertNotIn("bound-generation-secret", diagnostics_text)
        self.assertEqual(
            environment_before_bound_failure,
            application.environment_projection.render(),
        )
        self.assertEqual(
            generation_id,
            application.window.console_widget.state.active_generation_id,
        )
        self.assertEqual("Start Benchmark failed", application.window.application_readiness_status.label)
        self.assertEqual("error", application.window.application_readiness_status.tone)
        self.assertEqual(
            ["build_plan", "start_benchmark"],
            [observation[0] for observation in hook_observations],
        )
        self.assertIn("api_key=<redacted>", hook_observations[1][2])
        self.assertNotIn("bound-generation-secret", hook_observations[1][2])

    def test_blocked_shared_terminal_projects_diagnostics_without_report_authority(self) -> None:
        generation_id = "generation-frontend-blocked"
        application, session, resolver = self._application_for(generation_id)
        blocked = _blocked_run(generation_id)

        with patch.object(
            session,
            "execute_accepted_run",
            return_value=blocked,
        ):
            application.show()
            boundary = application.shared_application_boundary
            self._wait_until(
                lambda: (
                    boundary.discovery is not None
                    and application.window.benchmark_input.options
                    == ("frontend.benchmark@1.0.0",)
                ),
                "shared discovery was not projected",
            )

            application.request_build_plan(
                SidebarInputSnapshot(
                    benchmark="frontend.benchmark@1.0.0",
                    runner="frontend.runner@1.0.0",
                    model="frontend-model",
                    credential=_SECRET,
                    temperature=None,
                    max_tokens=None,
                )
            )
            self._wait_until(
                lambda: (
                    boundary.plan_request is not None
                    and application.window.current_run_status is not None
                    and application.window.current_run_status.label == "Pending"
                ),
                "shared plan was not projected",
            )
            application.request_accept_plan()
            self._wait_until(
                lambda: (
                    boundary.accepted_snapshot is not None
                    and application.window.current_run_status is not None
                    and application.window.current_run_status.label == "Accepted"
                ),
                "accepted snapshot was not projected",
            )
            application.request_start_benchmark()
            self._wait_until(
                lambda: (
                    boundary.selected_terminal is blocked
                    and application.window.current_run_status is not None
                    and application.window.current_run_status.label == "Failed"
                    and application.window.console_widget.state.active_generation_id
                    == generation_id
                    and "BlockedRun"
                    in (application.window.workspace_pages[
                        "Results"
                    ].projection.empty_state or "")
                ),
                "blocked terminal result was not projected",
            )

        self.assertEqual("Failed", application.window.current_run_status.label)
        self.assertEqual(
            "status-error",
            application.window.current_run_status.icon_key,
        )
        self.assertEqual(
            "Failed",
            application.window.run_rows[generation_id].status_badge.label,
        )
        self.assertEqual(
            "status-error",
            application.window.run_rows[generation_id].status_badge.icon_key,
        )
        self.assertEqual(
            generation_id,
            application.window.console_widget.state.active_generation_id,
        )
        self.assertEqual(
            generation_id,
            application.window.workspace_projection_run_id,
        )
        self.assertIn(
            "BlockedRun",
            application.window.workspace_pages["Results"].projection.empty_state,
        )
        self.assertIsNone(application.window.workspace_pages["Reports"].projection.report_id)
        self.assertIsNone(boundary.report_bundle)

        self.assertEqual(
            {f"{generation_id}:diagnostic"},
            {
                row.artifact_id
                for row in application.window.workspace_pages[
                    "Evidence"
                ].projection.artifacts.rows
            },
        )
        application.window.console_widget.set_active_tab("Diagnostics")
        self.assertIn(
            "blocked-by-shared-authority",
            application.window.console_widget.state.visible_text,
        )
        self.assertIsNone(boundary.execution_request.transient_values)


if __name__ == "__main__":
    unittest.main()
