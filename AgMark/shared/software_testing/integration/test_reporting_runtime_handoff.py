"""Provider-free integration evidence for finalized runtime-to-reporting admission."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import posixpath
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

from AgMark.shared.adapters.Mock_Model import load_registration
from AgMark.shared.software_testing.adapters.mock_model_support import resolve_model_identity
from AgMark.shared.evaluation import (
    SCORER_INVOCATION_CONTRACT_ID,
    SCORER_INVOCATION_CONTRACT_VERSION,
    IdentityRef as EvaluationIdentityRef,
)
from AgMark.shared.evaluation.availability import AvailabilityRecord
from AgMark.shared.reporting import (
    REQUIRED_REPORT_SECTIONS,
    CaseResultEntry,
    ObservationCounts,
    ObservationMatrixEntry,
    RegisteredReportMetric,
    ReportArtifactRef,
    ReportSection,
    TreatmentSummary,
    admit_finalized_run_for_reporting,
    build_canonical_report_model,
    generate_report_bundle,
    revalidate_accepted_reporting_input,
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
    RUNNER_INVOCATION_CONTRACT_ID,
    RUNNER_INVOCATION_CONTRACT_VERSION,
    SCORER_ENTRY_POINT_EXTENSION,
    AcceptedRun,
    PlannedCaseInput,
    RegisteredScoringDefinition,
    TreatmentCaseInput,
    TreatmentPrompt,
    accept_run_plan,
    admit_accepted_execution,
    execute_planned_treatments,
    finalize_scored_run,
    plan_run,
    score_accepted_treatments,
)
from AgMark.shared.validation import (
    ArtifactSource,
    BenchmarkDiscoveryCandidate,
    ContractRequirement,
    validate_benchmark_discovery,
    validate_registration_binding_outcome,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_TEST_MODULE = (
    "AgMark.shared.software_testing.integration."
    "test_reporting_runtime_handoff"
)
_TEST_REFERENCE = (
    "AgMark/shared/software_testing/integration/"
    "test_reporting_runtime_handoff.py"
)
_BENCHMARK_ID = "arcgrav.benchmark.reporting-runtime-handoff"
_BENCHMARK_VERSION = "1.0.0"
_BENCHMARK_REGISTRATION_SOURCE_ID = "reporting-runtime-handoff-benchmark-registration"
_RUNNER_ID = "arcgrav.mock-model.runner"
_RUNNER_VERSION = "1.0.0"
_RUNNER_REGISTRATION_SOURCE_ID = "reporting-runtime-handoff-runner-registration"
_SCORER_ID = "arcgrav.scorer.reporting-runtime-handoff"
_SCORER_VERSION = "1.0.0"
_METRIC_ID = "arcgrav.metric.reporting-runtime-handoff"
_METRIC_VERSION = "1.0.0"
_METRIC_REGISTRATION_ID = "arcgrav.metric-registration.reporting-runtime-handoff"
_METRIC_REGISTRATION_VERSION = "1.0.0"
_COMPARISON_TRACK = "reporting-runtime-handoff"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _discovered_benchmark_identity() -> IdentityRef:
    implementation_bytes = Path(__file__).read_bytes()
    source = ArtifactSource(
        artifact_id="reporting-runtime-handoff-benchmark-fixture",
        reference=_TEST_REFERENCE,
        data=implementation_bytes,
    )
    registration = {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "extensions": {},
        "registration_id": _BENCHMARK_ID,
        "registration_version": _BENCHMARK_VERSION,
        "registration_kind": "benchmark",
        "status": "active",
        "contracts": [],
        "implementation_artifacts": [
            {
                "artifact_id": source.artifact_id,
                "sha256": _sha256(implementation_bytes),
                "reference": source.reference,
            }
        ],
    }
    outcome = validate_registration_binding_outcome(
        registration,
        expected_registration_id=_BENCHMARK_ID,
        expected_registration_version=_BENCHMARK_VERSION,
        contract_requirements=(),
        artifact_sources=(source,),
        allowed_artifact_roots=(
            "AgMark/shared/software_testing/integration",
        ),
        source_id=_BENCHMARK_REGISTRATION_SOURCE_ID,
    )
    if not outcome.valid:
        raise AssertionError([issue.code for issue in outcome.issues])
    issues = validate_benchmark_discovery(
        (
            BenchmarkDiscoveryCandidate(
                package_root="AgMark/Registration_Driven_Integration_Fixture",
                registration_source_id=_BENCHMARK_REGISTRATION_SOURCE_ID,
                registration=registration,
                registration_validation=outcome,
            ),
        ),
        source_id="reporting-runtime-handoff-discovery",
    )
    if issues:
        raise AssertionError([issue.code for issue in issues])
    return IdentityRef(
        _BENCHMARK_ID,
        _BENCHMARK_VERSION,
        sha256=_sha256(implementation_bytes),
        reference=_TEST_REFERENCE,
    )


def _validated_runner_registration() -> tuple[dict[str, object], object]:
    registration = load_registration()
    sources = tuple(
        ArtifactSource(
            artifact_id=artifact["artifact_id"],
            reference=artifact["reference"],
            data=(_REPOSITORY_ROOT / artifact["reference"]).read_bytes(),
        )
        for artifact in registration["implementation_artifacts"]
    )
    outcome = validate_registration_binding_outcome(
        registration,
        expected_registration_id=_RUNNER_ID,
        expected_registration_version=_RUNNER_VERSION,
        contract_requirements=(
            ContractRequirement(
                RUNNER_INVOCATION_CONTRACT_ID,
                (RUNNER_INVOCATION_CONTRACT_VERSION,),
            ),
        ),
        artifact_sources=sources,
        allowed_artifact_roots=("AgMark/shared/adapters", "AgMark/shared/telemetry", "AgMark/shared/mock_model", "AgMark/shared/evaluation/telemetry/source.py", "AgMark/shared/runtime/identity/runtime_version.py"),
        source_id=_RUNNER_REGISTRATION_SOURCE_ID,
    )
    if not outcome.valid:
        raise AssertionError([issue.code for issue in outcome.issues])
    return registration, outcome


def registered_reporting_scorer(call) -> Mapping[str, object]:
    observation = json.loads(
        call.evidence_by_role["treatment_observation"].decode("utf-8")
    )
    if observation["terminal_status"] != "completed":
        return {
            "availability": "failed",
            "companion_values": [],
            "failure_refs": ["failure:" + observation["observation_id"]],
            "diagnostics": ["REPORTING_HANDOFF_TREATMENT_NOT_COMPLETED"],
            "extensions": {},
        }
    return {
        "availability": "scored",
        "value": 0.75,
        "companion_values": [
            {"name": "correct_units", "value": 3},
            {"name": "expected_units", "value": 4},
            {"name": "unexpected_units", "value": 0},
        ],
        "failure_refs": [],
        "diagnostics": ["REPORTING_HANDOFF_PARTIAL_MATCH"],
        "extensions": {
            "fixture:comparison": {"path": "/answer", "expected": "yes", "observed": "no"},
            "fixture:unselected": {"excluded_from_presentation": True},
        },
    }


def _metric_registration() -> dict[str, object]:
    return {
        "schema_id": "arcgrav.shared.schema.metric-registration",
        "schema_version": "1.0.0",
        "extensions": {
            "arcgrav.shared.reporting:score-details": {"extension_keys": ["fixture:comparison"]}
        },
        "registration_id": _METRIC_REGISTRATION_ID,
        "registration_version": _METRIC_REGISTRATION_VERSION,
        "metric_id": _METRIC_ID,
        "metric_version": _METRIC_VERSION,
        "name": "Reporting runtime handoff score",
        "description": "Provider-free score for finalized runtime-to-reporting admission.",
        "classification": "correctness",
        "comparison_track_id": _COMPARISON_TRACK,
        "is_primary_endpoint": True,
        "formula_or_algorithm": "Retain the exact registered score.",
        "required_inputs": ["treatment_observation"],
        "unit": "score",
        "valid_range": {
            "kind": "numeric",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "directionality": "higher_is_better",
        "numerator_denominator": {
            "uses_rate": False,
            "numerator_rule": "not a rate",
            "denominator_rule": "not a rate",
        },
        "repetition_aggregation": "identity",
        "case_aggregation": "identity",
        "state_treatment": [
            {"state": "completed", "disposition": "score"},
            {"state": "failed", "disposition": "fail"},
        ],
        "normalization_and_equivalence": "No normalization or semantic equivalence.",
        "availability_and_noncomparability": "Preserve explicit availability states.",
        "required_companion_values": [],
        "presentation_precision": 3,
        "scorer_or_annotation": {
            "procedure_id": _SCORER_ID,
            "version": _SCORER_VERSION,
            "kind": "scorer",
        },
        "contracts": [
            {
                "id": SCORER_INVOCATION_CONTRACT_ID,
                "version": SCORER_INVOCATION_CONTRACT_VERSION,
            }
        ],
    }


def _scoring_definition() -> RegisteredScoringDefinition:
    implementation_bytes = Path(__file__).read_bytes()
    source = ArtifactSource(
        artifact_id="reporting-runtime-handoff-scorer",
        reference=_TEST_REFERENCE,
        data=implementation_bytes,
    )
    registration = {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "extensions": {
            SCORER_ENTRY_POINT_EXTENSION: (
                _TEST_MODULE + ":registered_reporting_scorer"
            ),
        },
        "registration_id": _SCORER_ID,
        "registration_version": _SCORER_VERSION,
        "registration_kind": "scorer",
        "status": "active",
        "contracts": [
            {
                "id": SCORER_INVOCATION_CONTRACT_ID,
                "version": SCORER_INVOCATION_CONTRACT_VERSION,
            }
        ],
        "implementation_artifacts": [
            {
                "artifact_id": source.artifact_id,
                "sha256": _sha256(implementation_bytes),
                "reference": source.reference,
                "availability": "retained",
            }
        ],
    }
    outcome = validate_registration_binding_outcome(
        registration,
        expected_registration_id=_SCORER_ID,
        expected_registration_version=_SCORER_VERSION,
        contract_requirements=(
            ContractRequirement(
                SCORER_INVOCATION_CONTRACT_ID,
                (SCORER_INVOCATION_CONTRACT_VERSION,),
            ),
        ),
        artifact_sources=(source,),
        allowed_artifact_roots=(
            "AgMark/shared/software_testing/integration",
        ),
        source_id="reporting-runtime-handoff-scorer-registration",
    )
    if not outcome.valid:
        raise AssertionError([issue.code for issue in outcome.issues])
    return RegisteredScoringDefinition(
        metric_registration=_metric_registration(),
        scorer_registration=registration,
        scorer_registration_outcome=outcome,
    )


class ReportingRuntimeHandoffIntegrationTests(unittest.TestCase):
    def test_registration_driven_lifecycle_binds_completed_report_components(self) -> None:
        benchmark = _discovered_benchmark_identity()
        runner_registration, runner_registration_outcome = _validated_runner_registration()
        scoring_definition = _scoring_definition()
        case_set = IdentityRef(
            "arcgrav.case-set.reporting-runtime-handoff",
            "1.0.0",
            sha256=_sha256(b"case-set-reporting-runtime-handoff"),
        )
        treatment_set = IdentityRef(
            "arcgrav.treatment-set.reporting-runtime-handoff",
            "1.0.0",
            sha256=_sha256(b"treatment-set-reporting-runtime-handoff"),
        )
        resolved_runtime, resolved_controls = resolve_model_identity("mock-base::scenario:completed")
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-reporting-runtime-handoff",
            framework=IdentityRef(
                "arcgrav.framework.reporting-runtime-handoff",
                "1.0.0",
            ),
            runner=IdentityRef(
                _RUNNER_ID,
                _RUNNER_VERSION,
            ),
            provider_runtime=resolved_runtime,
            controls=resolved_controls,
            environment={"runtime_family": "provider-free"},
        )
        case_data = b"reporting-runtime-handoff-case"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    root / "evidence",
                    benchmark_root=root,
                )
            )
            plan = plan_run(
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                cases=(
                    PlannedCaseInput(
                        "case-reporting-runtime-handoff",
                        _sha256(case_data),
                        byte_length=len(case_data),
                    ),
                ),
                treatments=("treatment-reporting-runtime-handoff",),
                repetitions=1,
                execution_boundary=boundary,
                golden_required=False,
                contracts=(
                    IdentityRef(
                        RUNNER_INVOCATION_CONTRACT_ID,
                        RUNNER_INVOCATION_CONTRACT_VERSION,
                    ),
                    IdentityRef(
                        SCORER_INVOCATION_CONTRACT_ID,
                        SCORER_INVOCATION_CONTRACT_VERSION,
                    ),
                ),
            )
            snapshot = accept_run_plan(
                plan=plan,
                execution_boundary=boundary,
            )
            gate = admit_accepted_execution(
                generation_id="generation-reporting-runtime-handoff",
                snapshot=snapshot,
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=store,
            )
            treatment = execute_planned_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                execution_boundary=boundary,
                artifact_store=store,
                repository_root=_REPOSITORY_ROOT,
                runner_registration=runner_registration,
                case_inputs=(
                    TreatmentCaseInput(
                        "case-reporting-runtime-handoff",
                        case_data,
                    ),
                ),
                treatment_prompts=(
                    TreatmentPrompt(
                        "treatment-reporting-runtime-handoff",
                        b"provider-free reporting handoff prompt",
                    ),
                ),
            )
            self.assertEqual(
                runner_registration_outcome.registration_sha256,
                treatment.runner_registration_sha256,
            )
            self.assertEqual(benchmark.to_dict(), plan.benchmark.to_dict())

            scoring = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(scoring_definition,),
            )
            finalized = finalize_scored_run(
                gate=gate,
                treatment_result=treatment,
                scoring_result=scoring,
                artifact_store=store,
            )
            self.assertIsInstance(finalized, AcceptedRun)
            assert isinstance(finalized, AcceptedRun)

            records_by_role: dict[str, list[object]] = {}
            for record in finalized.artifact_index.artifacts:
                records_by_role.setdefault(record.role, []).append(record)
            self.assertEqual(1, len(records_by_role["execution_boundary"]))
            self.assertEqual(1, len(records_by_role["metric_registration"]))
            self.assertEqual(1, len(records_by_role["treatment_observation"]))
            self.assertEqual(1, len(records_by_role["score_artifact"]))

            boundary_record = records_by_role["execution_boundary"][0]
            treatment_record = records_by_role["treatment_observation"][0]
            score_record = records_by_role["score_artifact"][0]
            boundary_ref = ReportArtifactRef.from_record(boundary_record)
            treatment_ref = ReportArtifactRef.from_record(treatment_record)
            score_ref = ReportArtifactRef.from_record(score_record)
            score_document = json.loads(store.read_verified(score_record).decode("utf-8"))
            self.assertEqual(benchmark.to_dict(), score_document["benchmark"])
            self.assertEqual(
                {
                    "id": _METRIC_REGISTRATION_ID,
                    "version": _METRIC_REGISTRATION_VERSION,
                },
                score_document["metric_registration"],
            )
            self.assertEqual(
                {"id": _SCORER_ID, "version": _SCORER_VERSION},
                score_document["scorer"],
            )
            self.assertTrue(
                scoring_definition.scorer_registration_outcome.matches(
                    scoring_definition.scorer_registration,
                    source_id="reporting-runtime-handoff-scorer-registration",
                )
            )

            observation_availability = AvailabilityRecord(
                affected_kind="evidence_role",
                affected="treatment_observation",
                state="retained",
                reason="Finalized treatment observation retained.",
                source_identity=treatment_ref.artifact_id,
            )
            score_availability = AvailabilityRecord(
                affected_kind="measurement",
                affected=_METRIC_ID,
                state="scored",
                reason="Finalized registered score retained.",
                source_identity=score_ref.artifact_id,
            )
            metric = RegisteredReportMetric(
                registration=_metric_registration(),
                scorer=EvaluationIdentityRef(_SCORER_ID, _SCORER_VERSION),
                scoring_contracts=(
                    EvaluationIdentityRef(
                        SCORER_INVOCATION_CONTRACT_ID,
                        SCORER_INVOCATION_CONTRACT_VERSION,
                    ),
                ),
            )
            authority = admit_finalized_run_for_reporting(
                finalized,
                store=store,
                execution_boundary=boundary_ref,
                benchmark=EvaluationIdentityRef(benchmark.id, benchmark.version),
                case_set=EvaluationIdentityRef(case_set.id, case_set.version),
                treatment_set=EvaluationIdentityRef(
                    treatment_set.id,
                    treatment_set.version,
                ),
                comparison_track_id=_COMPARISON_TRACK,
                primary_endpoint=EvaluationIdentityRef(
                    _METRIC_ID,
                    _METRIC_VERSION,
                ),
                metrics=(metric,),
                observation_counts=ObservationCounts(
                    planned=1,
                    finalized=1,
                    completed=1,
                    scored=1,
                    failed=0,
                    missing=0,
                    excluded=0,
                    non_scorable=0,
                ),
                observation_matrix=(
                    ObservationMatrixEntry(
                        observation_id=plan.observations[0].observation_id,
                        request_id=plan.observations[0].request_id,
                        case_id=plan.observations[0].case_id,
                        treatment_id=plan.observations[0].treatment_id,
                        repetition_id=plan.observations[0].repetition,
                        execution_boundary_fingerprint=boundary.fingerprint,
                        availability=observation_availability,
                        evidence_refs=(treatment_ref,),
                    ),
                ),
                case_result_matrix=(
                    CaseResultEntry(
                        case_id=plan.observations[0].case_id,
                        treatment_id=plan.observations[0].treatment_id,
                        execution_boundary_fingerprint=boundary.fingerprint,
                        metric_registration_id=_METRIC_REGISTRATION_ID,
                        metric_registration_version=_METRIC_REGISTRATION_VERSION,
                        availability=score_availability,
                        value=score_document["value"],
                        evidence_refs=(score_ref,),
                    ),
                ),
                treatment_summaries=(
                    TreatmentSummary(
                        treatment_id=plan.observations[0].treatment_id,
                        metric_registration_id=_METRIC_REGISTRATION_ID,
                        metric_registration_version=_METRIC_REGISTRATION_VERSION,
                        availability=score_availability,
                        planned=1,
                        finalized=1,
                        completed=1,
                        scorable=1,
                        failed=0,
                        missing=0,
                        excluded=0,
                        non_scorable=0,
                        numerator=score_document["value"],
                        denominator=1,
                        value=score_document["value"],
                    ),
                ),
            )
            self.assertTrue(authority.valid)
            self.assertEqual(finalized.generation_id, authority.accepted_generation_id)

            sections = {
                name: ReportSection(availability="available")
                for name in REQUIRED_REPORT_SECTIONS
            }
            report = build_canonical_report_model(
                authority,
                report_id="report-reporting-runtime-handoff",
                report_version="1.0.0",
                status="complete",
                sections=sections,
                report_manifest_id="manifest-reporting-runtime-handoff",
                generated_at="2026-09-20T00:00:00Z",

            )
            self.assertEqual(finalized.generation_id, report.accepted_generation_id)

            bundle_arguments = dict(
                input_evidence_set_id="evidence-set-reporting-runtime-handoff",
                generator=EvaluationIdentityRef(
                    "arcgrav.generator.reporting-runtime-handoff",
                    "1.0.0",
                ),
                procedure_id="arcgrav.procedure.reporting-runtime-handoff",
                procedure_version="1.0.0",
                command_or_procedure=(
                    "provider-free finalized runtime reporting assembly"
                ),
                report_reference="reports/generation-reporting-runtime-handoff/report.json",
                canonical_evidence_reference="reports/generation-reporting-runtime-handoff/canonical-evidence.json",
                human_reference="reports/generation-reporting-runtime-handoff/report.md",
                manifest_reference="reports/generation-reporting-runtime-handoff/report-manifest.json",
            )
            bundle = generate_report_bundle(report, **bundle_arguments)
            evidence = json.loads(bundle.canonical_evidence.data)
            details = evidence["score_details"]
            self.assertEqual(1, len(details))
            detail = details[0]
            self.assertEqual(score_document["companion_values"], detail["companion_values"])
            self.assertEqual(score_document["diagnostics"], detail["diagnostics"])
            self.assertEqual({"fixture:comparison": score_document["extensions"]["fixture:comparison"]}, detail["extensions"])
            self.assertEqual(score_record.sha256, detail["source_artifact"]["sha256"])
            self.assertEqual(score_record.reference, detail["source_artifact"]["reference"])
            with self.assertRaises(TypeError):
                authority.score_details[0]["value"] = 1
            human = bundle.human.data.decode("utf-8")
            self.assertIn("Treatment Results per Observation in Execution Order", human)
            self.assertIn("canonical-evidence.json", human)
            self.assertNotIn("REPORTING_HANDOFF_PARTIAL_MATCH", human)
            self.assertNotIn('"path": "/answer"', human)
            self.assertNotIn("excluded_from_presentation", human)
            treatment_document = json.loads(store.read_verified(treatment_record))
            observations = evidence["observation_results"]
            self.assertEqual(1, len(observations))
            self.assertEqual(treatment_document["observation_id"], observations[0]["observation_id"])
            self.assertEqual(treatment_document["attempts"][0]["started_at"], observations[0]["attempt_started_at"])
            self.assertEqual(score_document["value"], observations[0]["score"]["value"])
            self.assertEqual("scored", observations[0]["score"]["availability"])
            self.assertEqual(score_record.sha256, observations[0]["score_artifact"]["sha256"])
            self.assertEqual(treatment_record.sha256, observations[0]["source_artifact"]["sha256"])
            from AgMark.shared.reporting.run_report import RUN_RESULTS_EXTENSION
            self.assertEqual(evidence["run_results"],
                             json.loads(bundle.report.data)["extensions"][RUN_RESULTS_EXTENSION])
            with self.assertRaises(TypeError):
                authority.observation_results[0]["score"]["value"] = 0
            from AgMark.shared.reporting.completion import completion_record
            completion = completion_record(finalized.generation_id, status="complete", bundle=bundle)
            self.assertEqual("complete", completion["status"])
            self.assertEqual(finalized.generation_id, completion["generation_id"])
            self.assertEqual(
                {component.artifact_id: component.sha256 for component in (*bundle.components, bundle.manifest)},
                {component["artifact_id"]: component["sha256"] for component in completion["report"]["components"]},
            )
            # The concise report and its separate relative-linked evidence
            # survive sealing, export/import and exact-byte reopen together.
            from AgMark.shared.reporting.completion import report_components
            from AgMark.shared.runtime.artifacts.archive import read_archive_member, seal_generation
            from AgMark.shared.validation.run_archive import import_run_archive, read_retained_report
            components = report_components(bundle)
            archive = seal_generation(store.root, finalized.generation_id,
                report_components=components, completion_record=completion)
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", human):
                reference = posixpath.normpath(posixpath.join(
                    posixpath.dirname(bundle.human.reference), unquote(target)))
                self.assertIn(reference, components)
                self.assertEqual(components[reference], read_archive_member(archive, reference))
            destination = root / "imported-installation"
            (destination / "AgMark").mkdir(parents=True)
            with patch("AgMark.shared.reporting.generation.generate_report_bundle",
                       side_effect=AssertionError("must not regenerate")):
                imported = import_run_archive(archive, destination)
                self.assertEqual(archive.read_bytes(), imported.read_bytes())
                self.assertEqual(bundle.human.data, read_retained_report(imported).markdown_bytes)
                self.assertEqual(bundle.canonical_evidence.data,
                                 read_archive_member(imported, bundle.canonical_evidence.reference))


if __name__ == "__main__":
    unittest.main()
