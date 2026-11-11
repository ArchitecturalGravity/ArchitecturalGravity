"""Integration coverage for the coarse shared application planning boundary."""

from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from AgMark.shared.application import (
    ApplicationAcceptanceError,
    ApplicationDiscoveryError,
    ApplicationExecutionError,
    ApplicationExecutionRequest,
    ApplicationPlanRequest,
    ApplicationPlanningError,
    ApplicationPrerequisiteProjection,
    ApplicationPrerequisiteState,
    ApplicationRegistrationSource,
    ApplicationReportRequest,
    ApplicationReportingError,
    ApplicationRetentionError,
    ApplicationRunDeletion,
    PlanningApplicationSession,
    discover_application_authority,
)
from AgMark.shared.evaluation import IdentityRef as ReportingIdentityRef
from AgMark.shared.reporting import (
    GeneratedReportBundle,
    ObservationCounts,
    ReportArtifactRef,
)
from AgMark.shared.runtime.artifacts import (
    FilesystemArtifactStore,
    PublicationDestination,
)
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    AcceptedExecutionGate,
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


def _session():
    benchmark_registration = _registration("example.benchmark", "benchmark")
    benchmark_validation = _validated(
        benchmark_registration,
        "example-benchmark-registration",
    )
    runner_registration = _registration("example.runner", "runner")
    runner_validation = _validated(
        runner_registration,
        "example-runner-registration",
    )
    benchmark_candidate = BenchmarkDiscoveryCandidate(
        package_root="AgMark/Example_Benchmark",
        registration_source_id="example-benchmark-registration",
        registration=benchmark_registration,
        registration_validation=benchmark_validation,
    )
    runner_source = ApplicationRegistrationSource(
        registration_source_id="example-runner-registration",
        registration=runner_registration,
        registration_validation=runner_validation,
    )
    return (
        PlanningApplicationSession(
            benchmark_candidates=(benchmark_candidate,),
            runner_sources=(runner_source,),
        ),
        benchmark_registration,
        benchmark_validation,
        runner_registration,
    )


def _accepted_execution_session():
    session, _, benchmark_validation, _ = _session()
    benchmark = IdentityRef(
        "example.benchmark",
        "1.0.0",
        sha256=benchmark_validation.registration_sha256,
    )
    case_set = IdentityRef(
        "example.case-set",
        "1.0.0",
        sha256="sha256:" + "1" * 64,
    )
    treatment_set = IdentityRef(
        "example.treatment-set",
        "1.0.0",
        sha256="sha256:" + "2" * 64,
    )
    boundary = ExecutionBoundary.build(
        boundary_id="boundary-application-execution",
        framework=IdentityRef("arcgrav.framework", "1.0.0"),
        runner=IdentityRef("example.runner", "1.0.0"),
        provider_runtime=ProviderRuntimeIdentity(
            runtime_id="example.runtime",
            runtime_version="1.0.0",
            provider=None,
            access_method="in_process",
            model=None,
        ),
        controls={"memory_policy": "disabled"},
        environment={"runtime_family": "provider-free"},
    )
    session.build_plan(
        ApplicationPlanRequest(
            benchmark=benchmark,
            case_set=case_set,
            treatment_set=treatment_set,
            cases=(PlannedCaseInput("case-1", "sha256:" + "3" * 64),),
            treatments=("treatment-a",),
            repetitions=1,
            execution_boundary=boundary,
            golden_required=False,
        )
    )
    session.accept_plan()
    return session, benchmark, case_set, treatment_set, boundary


def _execution_request(
    directory: str,
    *,
    generation_id: str = "generation-application-1",
):
    session, benchmark, case_set, treatment_set, boundary = _accepted_execution_session()
    root = Path(directory).resolve()
    store = FilesystemArtifactStore(
        PublicationDestination.benchmark_owned(
            root / "evidence",
            benchmark_root=root,
        )
    )
    request = ApplicationExecutionRequest(
        generation_id=generation_id,
        benchmark=benchmark,
        case_set=case_set,
        treatment_set=treatment_set,
        execution_boundary=boundary,
        benchmark_root=root,
        artifact_store=store,
        repository_root=root,
        runner_registration={},
        case_inputs=(TreatmentCaseInput("case-1", b"case"),),
        treatment_prompts=(TreatmentPrompt("treatment-a", b"prompt"),),
        scoring_definitions=(),
    )
    return session, request


def _accepted_gate(generation_id: str) -> AcceptedExecutionGate:
    gate = object.__new__(AcceptedExecutionGate)
    object.__setattr__(gate, "generation_id", generation_id)
    return gate


def _blocked_run(generation_id: str) -> BlockedRun:
    blocked = object.__new__(BlockedRun)
    object.__setattr__(blocked, "generation_id", generation_id)
    return blocked


def _accepted_run(generation_id: str) -> AcceptedRun:
    accepted = object.__new__(AcceptedRun)
    object.__setattr__(accepted, "run_outcome_bytes", b'{"extensions": {}}')
    object.__setattr__(accepted, "generation_id", generation_id)
    return accepted


def _report_request(generation_id: str) -> ApplicationReportRequest:
    return ApplicationReportRequest(
        generation_id=generation_id,
        execution_boundary=ReportArtifactRef(
            artifact_id="execution-boundary",
            sha256="sha256:" + "a" * 64,
            reference=f"{generation_id}/execution-boundary.json",
            availability="retained",
        ),
        benchmark=ReportingIdentityRef("example.benchmark", "1.0.0"),
        case_set=ReportingIdentityRef("example.case-set", "1.0.0"),
        treatment_set=ReportingIdentityRef("example.treatment-set", "1.0.0"),
        comparison_track_id="example-comparison-track",
        primary_endpoint=ReportingIdentityRef("example.metric", "1.0.0"),
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
        report_id="example-report",
        report_version="1.0.0",
        status="complete",
        sections={},
        report_manifest_id="example-report-manifest",
        generated_at="2026-09-21T00:00:00Z",

        input_evidence_set_id="example-evidence-set",
        generator=ReportingIdentityRef("example.report-generator", "1.0.0"),
        procedure_id="example.report-procedure",
        procedure_version="1.0.0",
        command_or_procedure="registered report generation",
        report_reference="generated/report.json",
        canonical_evidence_reference="generated/canonical-evidence.json",
        human_reference="generated/report.md",
        manifest_reference="generated/reconstruction-manifest.json",
    )


class ApplicationBoundaryIntegrationTests(unittest.TestCase):
    def test_discovery_requires_exact_validated_active_registrations(self) -> None:
        session, benchmark_registration, benchmark_validation, _ = _session()
        discovery = session.discover()
        self.assertEqual(
            ("example.benchmark", "1.0.0", benchmark_validation.registration_sha256),
            (
                discovery.benchmarks[0].registration_id,
                discovery.benchmarks[0].registration_version,
                discovery.benchmarks[0].registration_sha256,
            ),
        )
        self.assertEqual("example.runner", discovery.runners[0].registration_id)
        self.assertEqual(("benchmark-capability",), discovery.benchmarks[0].capabilities)

        benchmark_registration["status"] = "disabled"
        with self.assertRaises(ApplicationDiscoveryError):
            session.discover()

    def test_duplicate_runner_identity_fails_closed(self) -> None:
        runner = _registration("example.runner", "runner")
        first_validation = _validated(runner, "runner-one")
        second = dict(runner)
        second_validation = _validated(second, "runner-two")
        with self.assertRaisesRegex(ApplicationDiscoveryError, "ambiguous"):
            discover_application_authority(
                benchmark_candidates=(),
                runner_sources=(
                    ApplicationRegistrationSource("runner-one", runner, first_validation),
                    ApplicationRegistrationSource("runner-two", second, second_validation),
                ),
            )

    def test_session_builds_and_accepts_only_discovered_authority(self) -> None:
        session, _, benchmark_validation, _ = _session()
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-application-session",
            framework=IdentityRef("arcgrav.framework", "1.0.0"),
            runner=IdentityRef("example.runner", "1.0.0"),
            provider_runtime=ProviderRuntimeIdentity(
                runtime_id="example.runtime",
                runtime_version="1.0.0",
                provider=None,
                access_method="in_process",
                model=None,
            ),
            controls={"memory_policy": "disabled"},
            environment={"runtime_family": "provider-free"},
        )
        request = ApplicationPlanRequest(
            benchmark=IdentityRef(
                "example.benchmark",
                "1.0.0",
                sha256=benchmark_validation.registration_sha256,
                reference="AgMark/Example_Benchmark/registration.json",
            ),
            case_set=IdentityRef(
                "example.case-set",
                "1.0.0",
                sha256="sha256:" + "1" * 64,
                reference="AgMark/Example_Benchmark/cases.json",
            ),
            treatment_set=IdentityRef(
                "example.treatment-set",
                "1.0.0",
                sha256="sha256:" + "2" * 64,
                reference="AgMark/Example_Benchmark/treatments.json",
            ),
            cases=(PlannedCaseInput("case-1", "sha256:" + "3" * 64),),
            treatments=("treatment-a",),
            repetitions=1,
            execution_boundary=boundary,
            golden_required=False,
        )
        plan = session.build_plan(request)
        self.assertIs(session.prepared_plan, plan)
        self.assertEqual(boundary.fingerprint, plan.execution_boundary_fingerprint)

        accepted = session.accept_plan()
        self.assertIs(session.accepted_snapshot, accepted)
        self.assertEqual(plan.run_plan_id, accepted.run_plan_id)
        with self.assertRaisesRegex(ApplicationPlanningError, "already been accepted"):
            session.accept_plan()

        rebuilt = session.build_plan(request)
        self.assertIs(session.prepared_plan, rebuilt)
        self.assertIsNone(session.accepted_snapshot)

        reaccepted = session.accept_plan()
        self.assertIs(session.accepted_snapshot, reaccepted)
        self.assertEqual(rebuilt.run_plan_id, reaccepted.run_plan_id)

    def test_session_rejects_undiscovered_benchmark_or_runner(self) -> None:
        session, _, benchmark_validation, _ = _session()
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-undiscovered-runner",
            framework=IdentityRef("arcgrav.framework", "1.0.0"),
            runner=IdentityRef("other.runner", "1.0.0"),
            provider_runtime=ProviderRuntimeIdentity(
                runtime_id="example.runtime",
                runtime_version="1.0.0",
                provider=None,
                access_method="in_process",
                model=None,
            ),
        )
        base = dict(
            case_set=IdentityRef(
                "example.case-set",
                "1.0.0",
                sha256="sha256:" + "1" * 64,
            ),
            treatment_set=IdentityRef(
                "example.treatment-set",
                "1.0.0",
                sha256="sha256:" + "2" * 64,
            ),
            cases=(PlannedCaseInput("case-1", "sha256:" + "3" * 64),),
            treatments=("treatment-a",),
            repetitions=1,
            execution_boundary=boundary,
            golden_required=False,
        )
        with self.assertRaisesRegex(ApplicationPlanningError, "benchmark identity"):
            session.build_plan(
                ApplicationPlanRequest(
                    benchmark=IdentityRef(
                        "other.benchmark",
                        "1.0.0",
                        sha256="sha256:" + "4" * 64,
                    ),
                    **base,
                )
            )
        with self.assertRaisesRegex(ApplicationPlanningError, "runner"):
            session.build_plan(
                ApplicationPlanRequest(
                    benchmark=IdentityRef(
                        "example.benchmark",
                        "1.0.0",
                        sha256=benchmark_validation.registration_sha256,
                    ),
                    **base,
                )
            )

    def test_prerequisites_gate_only_their_earliest_material_transition(self) -> None:
        session, _, benchmark_validation, runner_registration = _session()
        benchmark = IdentityRef(
            "example.benchmark",
            "1.0.0",
            sha256=benchmark_validation.registration_sha256,
        )
        case_set = IdentityRef(
            "example.case-set",
            "1.0.0",
            sha256="sha256:" + "1" * 64,
        )
        treatment_set = IdentityRef(
            "example.treatment-set",
            "1.0.0",
            sha256="sha256:" + "2" * 64,
        )
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-prerequisite-scopes",
            framework=IdentityRef("arcgrav.framework", "1.0.0"),
            runner=IdentityRef("example.runner", "1.0.0"),
            provider_runtime=ProviderRuntimeIdentity(
                runtime_id="example.runtime",
                runtime_version="1.0.0",
                provider=None,
                access_method="in_process",
                model=None,
            ),
            controls={"memory_policy": "disabled"},
            environment={"runtime_family": "provider-free"},
        )
        plan_request = ApplicationPlanRequest(
            benchmark=benchmark,
            case_set=case_set,
            treatment_set=treatment_set,
            cases=(PlannedCaseInput("case-1", "sha256:" + "3" * 64),),
            treatments=("treatment-a",),
            repetitions=1,
            execution_boundary=boundary,
            golden_required=False,
        )

        execution_blocker = ApplicationPrerequisiteState(
            "runner.authentication",
            "execution",
            False,
            "authentication is not ready",
        )
        session.set_prerequisite_projection(
            ApplicationPrerequisiteProjection.from_states((execution_blocker,))
        )
        plan = session.build_plan(plan_request)
        self.assertIs(session.prepared_plan, plan)

        acceptance_blocker = ApplicationPrerequisiteState(
            "acceptance.policy",
            "acceptance",
            False,
            "acceptance policy is unresolved",
        )
        session.set_prerequisite_projection(
            ApplicationPrerequisiteProjection.from_states(
                (acceptance_blocker, execution_blocker)
            )
        )
        with self.assertRaisesRegex(
            ApplicationAcceptanceError,
            "acceptance prerequisites are unresolved: acceptance.policy",
        ):
            session.accept_plan()
        self.assertIs(session.prepared_plan, plan)
        self.assertIsNone(session.accepted_snapshot)

        session.set_prerequisite_projection(
            ApplicationPrerequisiteProjection.from_states((execution_blocker,))
        )
        accepted = session.accept_plan()
        self.assertIs(session.accepted_snapshot, accepted)
        self.assertIs(session.prepared_plan, plan)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            request = ApplicationExecutionRequest(
                generation_id="generation-prerequisite-blocked",
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=FilesystemArtifactStore(
                    PublicationDestination.benchmark_owned(
                        root / "evidence",
                        benchmark_root=root,
                    )
                ),
                repository_root=root,
                runner_registration=runner_registration,
                case_inputs=(TreatmentCaseInput("case-1", b"case"),),
                treatment_prompts=(TreatmentPrompt("treatment-a", b"prompt"),),
                scoring_definitions=(),
            )
            with patch(
                "AgMark.shared.application.admit_accepted_execution"
            ) as admit:
                with self.assertRaisesRegex(
                    ApplicationExecutionError,
                    "execution prerequisites are unresolved: runner.authentication",
                ):
                    session.execute_accepted_run(request)
            admit.assert_not_called()

            session.set_prerequisite_projection(
                ApplicationPrerequisiteProjection.from_states(
                    (
                        ApplicationPrerequisiteState(
                            "runner.authentication",
                            "execution",
                            True,
                            "authentication is ready",
                        ),
                    )
                )
            )
            self.assertTrue(session.prerequisite_projection.ready_for("execution"))
            self.assertIs(session.prepared_plan, plan)
            self.assertIs(session.accepted_snapshot, accepted)

        self.assertIs(session.prepared_plan, plan)
        self.assertIs(session.accepted_snapshot, accepted)
        self.assertEqual((), session.retained_run_ids)

        planning_session, _, _, _ = _session()
        planning_session.set_prerequisite_projection(
            ApplicationPrerequisiteProjection.from_states(
                (
                    ApplicationPrerequisiteState(
                        "boundary.identity",
                        "planning",
                        False,
                        "canonical boundary identity is unresolved",
                    ),
                )
            )
        )
        with self.assertRaisesRegex(
            ApplicationPlanningError,
            "planning prerequisites are unresolved: boundary.identity",
        ):
            planning_session.build_plan(plan_request)
        self.assertIsNone(planning_session.prepared_plan)

    def test_prerequisite_projection_rejects_scope_mismatch_and_duplicate_identity(
        self,
    ) -> None:
        state = ApplicationPrerequisiteState(
            "runner.launchability",
            "execution",
            False,
        )
        with self.assertRaisesRegex(ValueError, "scoped to 'execution'"):
            ApplicationPrerequisiteProjection(planning=(state,))
        with self.assertRaisesRegex(ValueError, "duplicated"):
            ApplicationPrerequisiteProjection(
                execution=(
                    state,
                    ApplicationPrerequisiteState(
                        "runner.launchability",
                        "execution",
                        True,
                    ),
                )
            )

    def test_session_owns_execution_sequence_and_retains_terminal_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session, request = _execution_request(directory)
            gate = _accepted_gate(request.generation_id)
            terminal = _blocked_run(request.generation_id)

            with (
                patch(
                    "AgMark.shared.application.admit_accepted_execution",
                    return_value=gate,
                ) as admit,
                patch(
                    "AgMark.shared.application.execute_planned_treatments",
                    return_value=object(),
                ) as execute,
                patch(
                    "AgMark.shared.application.score_accepted_treatments",
                    return_value=object(),
                ) as score,
                patch(
                    "AgMark.shared.application.finalize_scored_run",
                    return_value=terminal,
                ) as finalize,
            ):
                observed = session.execute_accepted_run(request)

            self.assertIs(terminal, observed)
            admit.assert_called_once()
            execute.assert_called_once()
            score.assert_called_once()
            finalize.assert_called_once()
            self.assertEqual((request.generation_id,), session.retained_run_ids)
            self.assertIs(session.select_run(request.generation_id), terminal)
            self.assertEqual(request.generation_id, session.selected_run_id)

            with self.assertRaisesRegex(
                ApplicationExecutionError,
                "already been attempted",
            ):
                session.execute_accepted_run(request)

    def test_post_finalization_validation_failure_preserves_accepted_result(self):
        with tempfile.TemporaryDirectory() as directory:
            session, request = _execution_request(directory)
            terminal = _accepted_run(request.generation_id)
            with (
                patch("AgMark.shared.application.admit_accepted_execution", return_value=_accepted_gate(request.generation_id)),
                patch("AgMark.shared.application.execute_planned_treatments", return_value=object()),
                patch("AgMark.shared.application.score_accepted_treatments", return_value=object()),
                patch("AgMark.shared.application.finalize_scored_run", return_value=terminal),
                patch.object(AcceptedRun, "revalidate"),
                patch("AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.retain_failure") as retain_failure,
                patch("AgMark.shared.runtime.orchestration.replay.validate_finalized_run", side_effect=ValueError("sensitive detail")),
            ):
                self.assertIs(terminal, session.execute_accepted_run(request))
                self.assertIs(terminal, session.select_run(request.generation_id))
                retain_failure.assert_called_once_with(terminal, "post_treatment_validation_failed:ValueError")
            self.assertEqual("post_treatment_validation_failed:ValueError", session.validation_diagnostic(request.generation_id))
            self.assertNotIn("sensitive detail", session.validation_diagnostic(request.generation_id))

    def test_golden_blocked_admission_is_terminal_and_short_circuits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session, request = _execution_request(
                directory,
                generation_id="generation-application-blocked",
            )
            terminal = _blocked_run(request.generation_id)

            with (
                patch(
                    "AgMark.shared.application.admit_accepted_execution",
                    return_value=terminal,
                ),
                patch(
                    "AgMark.shared.application.execute_planned_treatments",
                ) as execute,
                patch(
                    "AgMark.shared.application.score_accepted_treatments",
                ) as score,
                patch(
                    "AgMark.shared.application.finalize_scored_run",
                ) as finalize,
            ):
                observed = session.execute_accepted_run(request)

            self.assertIs(terminal, observed)
            execute.assert_not_called()
            score.assert_not_called()
            finalize.assert_not_called()
            self.assertEqual((request.generation_id,), session.retained_run_ids)

    def test_retained_run_selection_fails_closed_for_unknown_generation(self) -> None:
        session, _, _, _, _ = _accepted_execution_session()
        with self.assertRaisesRegex(
            ApplicationExecutionError,
            "not available",
        ):
            session.select_run("generation-not-retained")

    def test_retained_run_deletion_delegates_storage_and_keeps_identity_retired(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session, request = _execution_request(
                directory,
                generation_id="generation-delete-session",
            )
            terminal = _blocked_run(request.generation_id)

            with patch(
                "AgMark.shared.application.admit_accepted_execution",
                return_value=terminal,
            ):
                observed = session.execute_accepted_run(request)

            self.assertIs(observed, terminal)
            self.assertIs(session.select_run(request.generation_id), terminal)
            self.assertEqual(request.generation_id, session.selected_run_id)

            generation_directory = (
                request.artifact_store.root / request.generation_id
            )
            generation_directory.mkdir()
            retained_file = generation_directory / "retained.bin"
            retained_file.write_bytes(b"retained")
            retained_file.chmod(0o444)
            generation_directory.chmod(0o555)

            deletion = session.delete_run(request.generation_id)

            self.assertEqual(
                ApplicationRunDeletion(generation_id=request.generation_id),
                deletion,
            )
            self.assertFalse(generation_directory.exists())
            self.assertTrue(
                (
                    request.artifact_store.root
                    / f".{request.generation_id}.deleted"
                ).is_file()
            )
            self.assertEqual((), session.retained_run_ids)
            self.assertIsNone(session.selected_run_id)

            with self.assertRaisesRegex(ApplicationRetentionError, "not available"):
                session.delete_run(request.generation_id)
            with self.assertRaisesRegex(ApplicationExecutionError, "already been attempted"):
                session.execute_accepted_run(request)

    def _complete_accepted(self, directory, *, factory=True, build_failure=None, validation_failure=None, wrong_generation=False, drift_after_build=False):
        from AgMark.shared.software_testing.integration.test_reporting_completion import report_bundle
        session, request = _execution_request(directory)
        terminal = _accepted_run(request.generation_id)
        factory_mock = Mock(return_value=_report_request("generation-other" if wrong_generation else request.generation_id))
        request = replace(request, report_request_factory=factory_mock if factory else None)
        bundle = report_bundle(request.generation_id)
        with (
            patch("AgMark.shared.application.admit_accepted_execution", return_value=_accepted_gate(request.generation_id)),
            patch("AgMark.shared.application.execute_planned_treatments", return_value=object()),
            patch("AgMark.shared.application.score_accepted_treatments", return_value=object()),
            patch("AgMark.shared.application.finalize_scored_run", return_value=terminal),
            patch.object(AcceptedRun, "revalidate", side_effect=([None, None, ValueError("drift after render")] if drift_after_build else [None, validation_failure] if validation_failure else None)),
            patch("AgMark.shared.runtime.orchestration.replay.validate_finalized_run", return_value=()),
            patch("AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.retain"),
            patch("AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.read", return_value=()),
            patch.object(session, "_build_report", return_value=bundle, side_effect=build_failure) as build,
        ):
            observed = session.execute_accepted_run(request)
        self.assertIs(terminal, observed)
        return session, request, bundle, factory_mock, build

    def test_report_extension_evaluator_receives_revalidated_authority_and_merges_results(self):
        from AgMark.shared.software_testing.integration.test_reporting_completion import report_bundle
        with tempfile.TemporaryDirectory() as directory:
            session, execution = _execution_request(directory)
            terminal = _accepted_run(execution.generation_id)
            with patch.object(AcceptedRun, "revalidate"):
                session._retain_terminal_run(terminal, execution.artifact_store)
            authority = object()
            evaluated = {"fixture:prerequisites": {"state": "satisfied"}}
            supplied = {"fixture:metadata": {"source": "registered"}}
            bundle = report_bundle(execution.generation_id)
            with (
                patch.object(AcceptedRun, "revalidate") as revalidate,
                patch("AgMark.shared.application.admit_finalized_run_for_reporting", return_value=authority) as admit,
                patch("AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.read_with_records", return_value=((), ())) as read,
                patch("AgMark.shared.application.build_canonical_report_model") as build,
                patch("AgMark.shared.application.generate_report_bundle", return_value=bundle) as generate,
            ):
                def evaluate(**kwargs):
                    revalidate.assert_called_once_with(execution.artifact_store)
                    admit.assert_called_once()
                    self.assertEqual({
                        "report_id": "example-report", "report_status": "complete",
                        "finalized": terminal, "reporting": authority,
                        "artifact_store": execution.artifact_store,
                    }, kwargs)
                    return evaluated
                evaluator = Mock(side_effect=evaluate)
                request = replace(_report_request(execution.generation_id),
                    extensions=supplied, extension_evaluator=evaluator)
                self.assertIs(bundle, session._build_report(request))
                evaluator.assert_called_once()
                read.assert_called_once_with(terminal, required=True)
                self.assertIs(authority, build.call_args.args[0])
                self.assertEqual({**supplied, **evaluated}, build.call_args.kwargs["extensions"])
                self.assertEqual(supplied, request.extensions)
                self.assertIs(build.return_value, generate.call_args.args[0])

    def test_report_extension_evaluator_rejects_collisions_and_nonmapping_results(self):
        for evaluated, message in (({"fixture:metadata": {}}, "collide"),
                                   (None, "must return a mapping"),
                                   ([], "must return a mapping")):
            with self.subTest(evaluated=evaluated), tempfile.TemporaryDirectory() as directory:
                session, execution = _execution_request(directory)
                terminal = _accepted_run(execution.generation_id)
                with patch.object(AcceptedRun, "revalidate"):
                    session._retain_terminal_run(terminal, execution.artifact_store)
                evaluator = Mock(return_value=evaluated)
                request = replace(_report_request(execution.generation_id),
                    extensions={"fixture:metadata": {"source": "registered"}},
                    extension_evaluator=evaluator)
                with (
                    patch.object(AcceptedRun, "revalidate"),
                    patch("AgMark.shared.application.admit_finalized_run_for_reporting"),
                    patch("AgMark.shared.application.build_canonical_report_model") as build,
                    patch("AgMark.shared.application.generate_report_bundle") as generate,
                    self.assertRaisesRegex(ApplicationReportingError, message),
                ):
                    session._build_report(request)
                evaluator.assert_called_once()
                build.assert_not_called()
                generate.assert_not_called()
                self.assertIsNone(session.completed_report(execution.generation_id))

    def test_report_extension_evaluator_is_not_called_after_source_validation_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            session, execution = _execution_request(directory)
            terminal = _accepted_run(execution.generation_id)
            with patch.object(AcceptedRun, "revalidate"):
                session._retain_terminal_run(terminal, execution.artifact_store)
            evaluator = Mock()
            request = replace(_report_request(execution.generation_id), extension_evaluator=evaluator)
            with (
                patch.object(AcceptedRun, "revalidate", side_effect=ValueError("retained evidence changed")),
                patch("AgMark.shared.application.admit_finalized_run_for_reporting") as admit,
                self.assertRaisesRegex(ValueError, "retained evidence changed"),
            ):
                session._build_report(request)
            admit.assert_not_called()
            evaluator.assert_not_called()

    def test_accepted_execution_automatically_completes_report_once(self):
        with tempfile.TemporaryDirectory() as directory:
            session, request, bundle, factory, build = self._complete_accepted(directory)
            factory.assert_called_once()
            build.assert_called_once()
            self.assertIs(bundle, session.completed_report(request.generation_id))
            self.assertEqual("complete", session.completion_record(request.generation_id)["status"])
            self.assertTrue(build.call_args.args[0].human_reference.startswith("reports/" + request.generation_id + "/"))
            with self.assertRaises(ApplicationExecutionError):
                session.execute_accepted_run(request)
            self.assertEqual(1, factory.call_count)
            copied = session.completion_record(request.generation_id)
            copied["report"]["components"].clear()
            self.assertEqual(4, len(session.completion_record(request.generation_id)["report"]["components"]))

    def test_missing_report_factory_fails_closed_without_manual_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            session, request, _, factory, build = self._complete_accepted(directory, factory=False)
            build.assert_not_called()
            factory.assert_not_called()
            self.assertIsNone(session.completed_report(request.generation_id))
            self.assertEqual("report_failed", session.completion_record(request.generation_id)["status"])

    def test_report_failure_preserves_terminal_run_without_exposing_partial_report(self):
        with tempfile.TemporaryDirectory() as directory:
            session, request, _, _, build = self._complete_accepted(directory, build_failure=ValueError("private source"))
            build.assert_called_once()
            self.assertIn(request.generation_id, session.retained_run_ids)
            self.assertIsNone(session.completed_report(request.generation_id))
            record = session.completion_record(request.generation_id)
            self.assertEqual("report_failed", record["status"])
            self.assertNotIn("private source", str(record))
            self.assertIsNone(record["report"])

    def test_input_validation_failure_never_invokes_report_factory(self):
        with tempfile.TemporaryDirectory() as directory:
            session, request, _, factory, build = self._complete_accepted(directory, validation_failure=ValueError("source drift"))
            factory.assert_not_called()
            build.assert_not_called()
            self.assertEqual("validation_failed", session.completion_record(request.generation_id)["status"])
            self.assertIsNone(session.completed_report(request.generation_id))


    def test_factory_cannot_redirect_report_to_another_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            session, request, _, factory, build = self._complete_accepted(directory, wrong_generation=True)
            factory.assert_called_once()
            build.assert_not_called()
            self.assertEqual("report_failed", session.completion_record(request.generation_id)["status"])
            self.assertIsNone(session.completed_report(request.generation_id))
            self.assertIsNone(session.completed_report("generation-other"))

    def test_source_drift_after_render_does_not_release_report(self):
        with tempfile.TemporaryDirectory() as directory:
            session, request, _, _, build = self._complete_accepted(directory, drift_after_build=True)
            build.assert_called_once()
            self.assertEqual("validation_failed", session.completion_record(request.generation_id)["status"])
            self.assertIsNone(session.completed_report(request.generation_id))

    def test_archive_publication_failure_never_exposes_completed_report(self):
        from AgMark.shared.software_testing.integration.test_reporting_completion import report_bundle
        with tempfile.TemporaryDirectory() as directory:
            session, request = _execution_request(directory)
            root = Path(directory)
            (root / "AgMark").mkdir()
            store = FilesystemArtifactStore(PublicationDestination.central(
                root / "AgMark" / "run_evidence", repository_root=root))
            request = replace(request, artifact_store=store,
                report_request_factory=lambda terminal: _report_request(terminal.generation_id))
            terminal = _accepted_run(request.generation_id)
            evidence = store.root / request.generation_id / "source.json"
            evidence.parent.mkdir()
            evidence.write_bytes(b"original evidence")
            with (
                patch.object(AcceptedRun, "revalidate"),
                patch("AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.read", return_value=()),
                patch.object(session, "_build_report", return_value=report_bundle(request.generation_id)),
                patch.object(store, "seal_generation", side_effect=OSError("publication interrupted")) as seal,
            ):
                session._complete_run(terminal, request)
            seal.assert_called_once()
            self.assertEqual(b"original evidence", evidence.read_bytes())
            self.assertIsNone(session.completed_report(request.generation_id))
            record = session.completion_record(request.generation_id)
            self.assertEqual("report_failed", record["status"])
            self.assertIsNone(record["report"])
            self.assertEqual("automatic_publication_failed:OSError", record["publication"]["diagnostic"])
            self.assertEqual("passed", record["validation"]["status"])
            self.assertIsNone(record["validation"]["diagnostic"])
            self.assertNotIn("publication interrupted", str(record))
            from AgMark.shared.runtime.completion_diagnostics import retained_completion_diagnostics
            rows = retained_completion_diagnostics(store.root, request.generation_id)
            self.assertEqual(record["diagnostics"], rows)
            self.assertEqual("publication", rows[-1]["stage"])
            self.assertEqual("OSError", rows[-1]["error_class"])
            self.assertFalse((store.root / (request.generation_id + ".agmark")).exists())
            with self.assertRaisesRegex(ApplicationReportingError, "write-once"):
                session._complete_run(terminal, request)
            seal.assert_called_once()

    def test_publication_failure_preserves_independent_validation_state(self):
        for state in ("failed", "not_applicable"):
            with self.subTest(validation=state), tempfile.TemporaryDirectory() as directory:
                session, request = _execution_request(directory)
                root = Path(directory)
                (root / "AgMark").mkdir()
                store = FilesystemArtifactStore(PublicationDestination.central(
                    root / "AgMark" / "run_evidence", repository_root=root))
                request = replace(request, artifact_store=store)
                terminal = (_accepted_run(request.generation_id) if state == "failed"
                            else _blocked_run(request.generation_id))
                diagnostic = "post_treatment_validation_failed:ValueError"
                if state == "failed":
                    session._validation_diagnostics[request.generation_id] = diagnostic
                with patch.object(store, "seal_generation", side_effect=OSError("unavailable")) as seal:
                    session._complete_run(terminal, request)
                seal.assert_called_once()
                record = session.completion_record(request.generation_id)
                self.assertEqual("report_failed", record["status"])
                self.assertEqual(state, record["validation"]["status"])
                self.assertEqual(diagnostic if state == "failed" else None,
                                 record["validation"]["diagnostic"])
                self.assertEqual("automatic_publication_failed:OSError",
                                 record["publication"]["diagnostic"])
                self.assertIsNone(record["report"])
                self.assertIsNone(session.completed_report(request.generation_id))
                if state == "failed":
                    rows = [row for row in record["diagnostics"] if row["stage"] == "post_treatment_validation"]
                    self.assertEqual("ValueError", rows[0]["error_class"])

    def test_completion_diagnostic_stage_matches_failure_and_survives_restart(self):
        from AgMark.shared.runtime.completion_diagnostics import retained_completion_diagnostics
        cases = (({"factory": False}, "report_request", "ApplicationReportingError"),
                 ({"build_failure": ValueError("prompt sk-secret /private/path")}, "report_build", "ValueError"),
                 ({"validation_failure": OSError("credential")}, "source_validation", "OSError"),
                 ({"drift_after_build": True}, "prepublication_validation", "ValueError"))
        for options, stage, error_class in cases:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                session, request, _, _, _ = self._complete_accepted(directory, **options)
                rows = session.completion_record(request.generation_id)["diagnostics"]
                failed = [row for row in rows if row["status"] == "failed"]
                self.assertEqual([(stage, error_class)], [(row["stage"], row["error_class"]) for row in failed])
                self.assertEqual(rows, retained_completion_diagnostics(request.artifact_store.root, request.generation_id))
                self.assertNotIn("sk-secret", str(rows))
                self.assertNotIn("/private/path", str(rows))

    def test_diagnostic_write_failure_does_not_mask_original_stage(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                "AgMark.shared.runtime.completion_diagnostics.persist_completion_diagnostics",
                side_effect=PermissionError("private directory")):
            session, request, _, _, _ = self._complete_accepted(directory, build_failure=ValueError("prompt"))
            rows = session.completion_record(request.generation_id)["diagnostics"]
            self.assertIn(("report_build", "failed", "ValueError"),
                [(row["stage"], row["status"], row["error_class"]) for row in rows])
            self.assertIn(("diagnostic_persistence", "warning", "PermissionError"),
                [(row["stage"], row["status"], row["error_class"]) for row in rows])
            self.assertIsNone(session.completed_report(request.generation_id))

    def test_postpublication_cleanup_warning_preserves_completed_report(self):
        import json
        from AgMark.shared.runtime.artifacts.archive import ArchiveCleanupWarning
        from AgMark.shared.reporting.completion import completion_record
        from AgMark.shared.software_testing.integration.test_reporting_completion import report_bundle
        with tempfile.TemporaryDirectory() as directory:
            session, request = _execution_request(directory)
            root = Path(directory)
            (root / "AgMark").mkdir()
            store = FilesystemArtifactStore(PublicationDestination.central(
                root / "AgMark" / "run_evidence", repository_root=root))
            request = replace(request, artifact_store=store,
                report_request_factory=lambda terminal: _report_request(terminal.generation_id))
            terminal = _accepted_run(request.generation_id)
            bundle = report_bundle(request.generation_id)
            record = completion_record(request.generation_id, status="complete", bundle=bundle)
            with (patch.object(AcceptedRun, "revalidate"),
                  patch("AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.read", return_value=()),
                  patch.object(session, "_build_report", return_value=bundle),
                  patch.object(store, "seal_generation", side_effect=ArchiveCleanupWarning(
                      store.root / (request.generation_id + ".agmark"), ("loose_sources:PermissionError",))) as seal,
                  patch("AgMark.shared.runtime.artifacts.archive.read_archive_member", return_value=json.dumps(record).encode())):
                session._complete_run(terminal, request)
            seal.assert_called_once()
            self.assertIs(bundle, session.completed_report(request.generation_id))
            result = session.completion_record(request.generation_id)
            self.assertEqual("complete", result["status"])
            self.assertIn("post_publication_cleanup", [row["stage"] for row in result["diagnostics"] if row["status"] == "warning"])

    def test_deleted_validation_companion_blocks_automatic_report(self):
        import shutil
        for removed in ("directory", "manifest"):
            with self.subTest(removed=removed), tempfile.TemporaryDirectory() as directory:
                session, request = _execution_request(directory)
                terminal = _accepted_run(request.generation_id)
                factory = Mock(return_value=_report_request(request.generation_id))
                request = replace(request, report_request_factory=factory)
                companion = request.artifact_store.root / ".agmark-validation" / request.generation_id
                companion.mkdir(parents=True)
                manifest = companion / "manifest.json"
                manifest.write_bytes(b"retained companion before deletion")
                if removed == "directory":
                    shutil.rmtree(companion)
                else:
                    manifest.unlink()
                with patch.object(AcceptedRun, "revalidate"), patch.object(session, "_build_report") as build:
                    session._complete_run(terminal, request)
                factory.assert_not_called()
                build.assert_not_called()
                record = session.completion_record(request.generation_id)
                self.assertEqual("validation_failed", record["status"])
                self.assertEqual("failed", record["validation"]["status"])
                self.assertIsNone(record["report"])
                self.assertIsNone(session.completed_report(request.generation_id))

if __name__ == "__main__":
    unittest.main()
