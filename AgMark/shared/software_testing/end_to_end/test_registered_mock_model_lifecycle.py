"""Accepted registered Mock Model CLI lifecycle through diagnostic report completion.

Uses the independent mock adapter and its isolated Python worker; the
registered scorer fixture is benchmark-neutral and does not interpret scenarios.
"""

from __future__ import annotations

import base64
from contextlib import nullcontext
from dataclasses import fields, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from AgMark.shared.adapters.Mock_Model import runner as mock_runner_module
from AgMark.shared.adapters.Mock_Model.catalog import probe_model_discovery, probe_planning_identity
from AgMark.shared.adapters.execution import (
    EXECUTION_EVIDENCE_EXTENSION_KEY,
    validate_execution_evidence,
)
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
)
from AgMark.shared.reporting.revalidation import (
    ReportingInputRevalidationError,
    _validate_schema_bound_document,
    revalidate_accepted_reporting_input,
)
from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination
from AgMark.shared.runtime.orchestration.execution import TreatmentExecutionError
from AgMark.shared.runtime.golden import (
    GOLDEN_EXECUTION_CONTRACT_ID,
    GOLDEN_EXECUTION_CONTRACT_VERSION,
    GoldenArtifactRequirement,
    GoldenCaseInput,
    GoldenDeclaration,
)
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    RUNNER_INVOCATION_CONTRACT_ID,
    RUNNER_INVOCATION_CONTRACT_VERSION,
    AcceptedExecutionGate,
    AcceptedRun,
    BlockedRun,
    PlannedCaseInput,
    TreatmentCaseInput,
    TreatmentPrompt,
    accept_run_plan,
    admit_accepted_execution,
    execute_planned_treatments,
    finalize_scored_run,
    plan_run,
    score_accepted_treatments,
)
from AgMark.shared.software_testing.integration import (
    test_reporting_runtime_handoff as reporting_fixture,
)
from AgMark.shared.validation import (
    ArtifactSource,
    ContractRequirement,
    validate_registration_binding_outcome,
)


_ROOT = Path(__file__).resolve().parents[4]
_REGISTRATION = _ROOT / "AgMark/shared/adapters/Mock_Model/registration.json"
_MODEL_ID = "mock-base::scenario:structured_response"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class RegisteredMockModelLifecycleTests(unittest.TestCase):
    def test_accepted_process_scores_and_reports_with_synthetic_identity(self) -> None:
        self._exercise_lifecycle(golden_required=False)

    def test_required_golden_precedes_registered_mock_report(self) -> None:
        self._exercise_lifecycle(golden_required=True)

    def test_downstream_lifecycle_rejects_unrelated_adapter_extensions(self) -> None:
        with self.assertRaises(TreatmentExecutionError):
            self._exercise_lifecycle(golden_required=False, inject_opaque_extensions=True)

    def _exercise_lifecycle(
        self, *, golden_required: bool, inject_opaque_extensions: bool = False,
    ) -> None:
        registration = json.loads(_REGISTRATION.read_text(encoding="utf-8"))
        binding = validate_registration_binding_outcome(
            registration,
            expected_registration_id="arcgrav.mock-model.runner",
            expected_registration_version="1.0.0",
            contract_requirements=(
                ContractRequirement(
                    RUNNER_INVOCATION_CONTRACT_ID,
                    (RUNNER_INVOCATION_CONTRACT_VERSION,),
                ),
            ),
            artifact_sources=tuple(
                ArtifactSource(
                    artifact_id=item["artifact_id"],
                    reference=item["reference"],
                    data=(_ROOT / item["reference"]).read_bytes(),
                )
                for item in registration["implementation_artifacts"]
            ),
            allowed_artifact_roots=("AgMark/shared/adapters", "AgMark/shared/telemetry", "AgMark/shared/mock_model", "AgMark/shared/evaluation/telemetry/source.py", "AgMark/shared/runtime/identity/runtime_version.py"),
            source_id="registered-mock-lifecycle-runner",
        )
        self.assertTrue(binding.valid, [issue.code for issue in binding.issues])
        self.assertEqual("AgMark.shared.adapters.Mock_Model:MockRunner", registration["extensions"]["arcgrav.adapters:entry_point"])
        supported = {item["name"] for item in registration["extensions"]["arcgrav.adapters:supported_controls"]}
        self.assertEqual({"model_id", "request_timeout_ms", "maximum_attempts"}, supported)
        self.assertFalse(any("Codex_CLI" in item["reference"] for item in registration["implementation_artifacts"]))
        golden_runtime = Path(sys.executable).resolve(strict=True) if golden_required else None
        catalog = probe_model_discovery(
            registration,
            control_values={},
            process_cwd=_ROOT,
        )
        self.assertEqual("ready", catalog["status"], catalog)
        self.assertIn(_MODEL_ID, catalog["selectable_model_ids"])
        probe = probe_planning_identity(
            registration,
            control_values={
                "model_id": _MODEL_ID,
            },
            platform_name="posix",
        )
        self.assertEqual("ready", probe["status"], probe)

        # Reuse the registered benchmark and scorer integration fixtures, not
        # an in-memory runner/score shortcut or scenario-aware benchmark code.
        benchmark = reporting_fixture._discovered_benchmark_identity()
        definition = reporting_fixture._scoring_definition()
        metric_document = reporting_fixture._metric_registration()
        metric_id = metric_document["metric_id"]
        metric_version = metric_document["metric_version"]
        metric_registration_id = metric_document["registration_id"]
        metric_registration_version = metric_document["registration_version"]
        scorer_id = definition.scorer_registration["registration_id"]
        scorer_version = definition.scorer_registration["registration_version"]
        case_set = IdentityRef(
            "arcgrav.case-set.registered-mock-lifecycle",
            "1.0.0",
            sha256=_sha256(b"registered-mock-lifecycle-case-set"),
        )
        treatment_set = IdentityRef(
            "arcgrav.treatment-set.registered-mock-lifecycle",
            "1.0.0",
            sha256=_sha256(b"registered-mock-lifecycle-treatment-set"),
        )
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-registered-mock-lifecycle",
            framework=IdentityRef("arcgrav.framework.registered-mock-lifecycle", "1.0.0"),
            runner=IdentityRef(
                registration["registration_id"], registration["registration_version"]
            ),
            provider_runtime=ProviderRuntimeIdentity(
                runtime_id=registration["registration_id"],
                runtime_version=probe["runtime_version"],
                provider="AgMark Mock Model",
                access_method="local_process",
                model=_MODEL_ID,
            ),
            controls={
                "model_id": _MODEL_ID,
                "request_timeout_ms": 120000,
                "maximum_attempts": 1,
                "memory_policy": "disabled",
                "request_framing": "mock_json_v1",
                "sampling_mode": "deterministic",
                "tool_policy": "none",
            },
            environment=(
                {
                    "golden.environment_family": "native",
                    "golden.runtime_sha256": _sha256(golden_runtime.read_bytes()),
                }
                if golden_required else {}
            ),
        )
        case_data = b"registered mock lifecycle input"
        prompt = b"registered mock lifecycle prompt"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    root / "evidence", benchmark_root=root
                )
            )
            plan = plan_run(
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                cases=(
                    PlannedCaseInput(
                        "case-registered-mock", _sha256(case_data), byte_length=len(case_data)
                    ),
                ),
                treatments=("treatment-registered-mock",),
                repetitions=1,
                execution_boundary=boundary,
                golden_required=golden_required,
                contracts=(
                    IdentityRef(
                        RUNNER_INVOCATION_CONTRACT_ID,
                        RUNNER_INVOCATION_CONTRACT_VERSION,
                    ),
                    IdentityRef(
                        SCORER_INVOCATION_CONTRACT_ID,
                        SCORER_INVOCATION_CONTRACT_VERSION,
                    ),
                    *(
                        (IdentityRef(
                            GOLDEN_EXECUTION_CONTRACT_ID,
                            GOLDEN_EXECUTION_CONTRACT_VERSION,
                        ),)
                        if golden_required else ()
                    ),
                ),
            )
            snapshot = accept_run_plan(plan=plan, execution_boundary=boundary)
            golden_inputs = (
                (GoldenCaseInput("case-registered-mock", case_data),)
                if golden_required else ()
            )
            golden_declaration = None
            if golden_required:
                self.assertIsNotNone(golden_runtime)
                script = root / "golden.py"

                def declaration() -> GoldenDeclaration:
                    return GoldenDeclaration(
                        golden_implementation=IdentityRef(
                            "arcgrav.golden.registered-mock-lifecycle", "1.0.0"
                        ),
                        runtime_executable=str(golden_runtime),
                        runtime_identity=IdentityRef(
                            "arcgrav.runtime.python", "1.0.0",
                            sha256=_sha256(golden_runtime.read_bytes()),
                            reference="runtime/python",
                        ),
                        artifacts=(
                            GoldenArtifactRequirement(
                                artifact_id="golden.py",
                                relative_path="golden.py",
                                sha256=_sha256(script.read_bytes()),
                            ),
                        ),
                        entry_artifact_id="golden.py",
                        environment_family="native",
                    )

                # A required golden failure is terminal: no runner registration,
                # mock inference, scoring, or treatment observations may follow.
                script.write_bytes(b"import sys\nsys.exit(7)\n")
                blocked = admit_accepted_execution(
                    generation_id="generation-registered-mock-lifecycle-blocked",
                    snapshot=snapshot,
                    benchmark=benchmark,
                    case_set=case_set,
                    treatment_set=treatment_set,
                    execution_boundary=boundary,
                    benchmark_root=root,
                    artifact_store=store,
                    golden_declaration=declaration(),
                    golden_case_inputs=golden_inputs,
                )
                self.assertIsInstance(blocked, BlockedRun)
                self.assertEqual("GOLDEN_NONZERO_EXIT", blocked.reason_code)
                self.assertEqual((), blocked.treatment_observations)
                self.assertEqual(1, len(blocked.golden_observations))
                blocked_roles = {
                    item.role: item.availability
                    for item in blocked.artifact_manifest.evidence_roles
                }
                self.assertEqual("not_produced", blocked_roles["treatment_observations"])
                self.assertEqual("not_produced", blocked_roles["score_artifacts"])
                with self.assertRaises(TypeError):
                    execute_planned_treatments(
                        gate=blocked,
                        snapshot=snapshot,
                        benchmark=benchmark,
                        case_set=case_set,
                        treatment_set=treatment_set,
                        execution_boundary=boundary,
                        artifact_store=store,
                        repository_root=_ROOT,
                        runner_registration=registration,
                        case_inputs=(TreatmentCaseInput("case-registered-mock", case_data),),
                        treatment_prompts=(
                            TreatmentPrompt("treatment-registered-mock", prompt),
                        ),
                    )

                # Bind new exact golden bytes before admitting the same accepted
                # plan to the normal mock treatment/scoring/reporting lifecycle.
                script.write_bytes(
                    b"import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n"
                )
                golden_declaration = declaration()

            gate = admit_accepted_execution(
                generation_id="generation-registered-mock-lifecycle",
                snapshot=snapshot,
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=store,
                golden_declaration=golden_declaration,
                golden_case_inputs=golden_inputs,
            )
            self.assertIsInstance(gate, AcceptedExecutionGate)
            gate.revalidate()
            if golden_required:
                self.assertEqual(1, len(gate.golden_observations))
                golden_observation = json.loads(gate.golden_observations[0].decode("utf-8"))
                self.assertEqual("admitted", golden_observation["admission_state"])
                self.assertEqual(_sha256(case_data), golden_observation["output"]["sha256"])
                self.assertEqual(
                    {"golden_observation", "golden_stdout"},
                    {record.role for record in gate.retained_golden_artifacts},
                )
                for record in gate.retained_golden_artifacts:
                    retained_bytes = store.read_verified(record)
                    if record.role == "golden_stdout":
                        self.assertEqual(case_data, retained_bytes)
            else:
                self.assertEqual((), gate.golden_observations)
                self.assertEqual((), gate.retained_golden_artifacts)
            original_emit = mock_runner_module.emit_terminal_observation

            def emit_with_opaque_extension(*args, **kwargs):
                result = original_emit(*args, **kwargs)
                result["extensions"]["fixture:opaque-adapter"] = {"not_authority": True}
                return result

            emission_scope = (
                mock.patch.object(
                    mock_runner_module, "emit_terminal_observation",
                    side_effect=emit_with_opaque_extension,
                ) if inject_opaque_extensions else nullcontext()
            )
            with emission_scope:
                treatment = execute_planned_treatments(
                    gate=gate,
                    snapshot=snapshot,
                    benchmark=benchmark,
                    case_set=case_set,
                    treatment_set=treatment_set,
                    execution_boundary=boundary,
                    artifact_store=store,
                    repository_root=_ROOT,
                    runner_registration=registration,
                    case_inputs=(TreatmentCaseInput("case-registered-mock", case_data),),
                    treatment_prompts=(
                        TreatmentPrompt("treatment-registered-mock", prompt),
                    ),
                )
            self.assertEqual(binding.registration_sha256, treatment.runner_registration_sha256)
            (observation,) = treatment.observations()
            self.assertEqual("completed", observation["terminal_status"], observation)
            self.assertEqual("retained", observation["response"]["availability"])
            evidence = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
            validate_execution_evidence(evidence)
            invalid_treatments = []
            for invalid in ("missing", "malformed"):
                changed = json.loads(json.dumps(observation))
                if invalid == "missing":
                    del changed["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
                else:
                    del changed["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]["process"]["stdout"]
                raw = json.dumps(
                    changed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
                altered = object.__new__(type(treatment))
                for field in fields(treatment):
                    value = getattr(treatment, field.name)
                    if field.name == "observation_bytes":
                        value = (raw,)
                    elif field.name == "retained_observation_artifacts":
                        value = (replace(value[0], sha256=_sha256(raw)),)
                    object.__setattr__(altered, field.name, value)
                with self.subTest(invalid_nested_evidence=invalid):
                    with self.assertRaises(TreatmentExecutionError):
                        altered.revalidate()
                    invalid_scoring = score_accepted_treatments(
                        gate=gate,
                        snapshot=snapshot,
                        benchmark=benchmark,
                        case_set=case_set,
                        treatment_set=treatment_set,
                        execution_boundary=boundary,
                        treatment_result=altered,
                        artifact_store=store,
                        scoring_definitions=(definition,),
                    )
                    self.assertEqual("blocked", invalid_scoring.classification)
                    self.assertIn(
                        "ORCHESTRATION_TREATMENT_RESULT_INVALID",
                        invalid_scoring.diagnostics,
                    )
                    self.assertEqual((), invalid_scoring.retained_score_artifacts)
                    with self.assertRaises(ReportingInputRevalidationError):
                        _validate_schema_bound_document(
                            altered.retained_observation_artifacts[0], raw
                        )
                invalid_treatments.append(altered)
            self.assertEqual(
                {"target", "submission", "runtime", "launch_environment",
                 "authentication", "isolation", "request_framing", "process",
                 "usage", "error"},
                set(evidence) - {"schema_id", "schema_version", "extensions"},
            )
            self.assertEqual("mock-model", evidence["target"]["class"])
            self.assertEqual(
                "provider-free-mock-model-execution", evidence["target"]["evidence_class"]
            )
            self.assertTrue(evidence["submission"]["occurred"])
            self.assertFalse(evidence["submission"]["external_provider"])
            self.assertEqual("not_applicable", evidence["authentication"]["availability"])
            self.assertEqual("observed", evidence["usage"]["availability"])
            self.assertFalse(evidence["usage"]["provider_reported"])
            self.assertFalse(any("token" in item["name"] for item in observation["telemetry"]))
            self.assertNotIn("openai.codex_cli:session-record", observation["extensions"])
            self.assertEqual(_MODEL_ID, evidence["runtime"]["model_id"])
            self.assertTrue(evidence["isolation"]["fresh_process"])
            self.assertTrue(evidence["isolation"]["fresh_workdir"])
            self.assertFalse(evidence["isolation"]["prior_observation_context_reused"])

            # The worker returns exact response bytes on stdout, not a provider event protocol.
            self.assertFalse(any(key.startswith("openai.codex_cli:") for key in observation["extensions"]))
            response = base64.b64decode(observation["extensions"][registration["registration_id"] + ":response_base64"], validate=True)
            self.assertNotIn("arcgrav.runner:process_stdout_base64", observation["extensions"])
            self.assertEqual(_sha256(response), observation["response"]["sha256"])
            self.assertEqual("excluded", evidence["process"]["stdout"]["availability"])
            self.assertIsNone(evidence["process"]["stdout"]["sha256"])
            self.assertIsNone(evidence["process"]["stdout"]["byte_length"])
            self.assertEqual("mock_json_v1", evidence["request_framing"]["mode"])
            self.assertFalse(evidence["isolation"]["session_home_reused"])

            treatment.revalidate()
            (observation_record,) = treatment.retained_observation_artifacts
            retained = json.loads(store.read_verified(observation_record).decode("utf-8"))
            self.assertEqual(observation, retained)
            validate_execution_evidence(
                retained["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
            )

            scoring = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(definition,),
            )
            for altered in invalid_treatments:
                with self.assertRaises(TreatmentExecutionError):
                    finalize_scored_run(
                        gate=gate,
                        treatment_result=altered,
                        scoring_result=scoring,
                        artifact_store=store,
                    )
            finalized = finalize_scored_run(
                gate=gate,
                treatment_result=treatment,
                scoring_result=scoring,
                artifact_store=store,
            )
            self.assertIsInstance(finalized, AcceptedRun)
            finalized.revalidate(store)
            records = {record.role: record for record in finalized.artifact_index.artifacts}
            expected_roles = {
                "execution_boundary", "metric_registration", "runner_registration",
                "treatment_observation", "score_artifact",
            }
            if golden_required:
                expected_roles.update(
                    {"golden_observation", "golden_stdout"}
                )
            self.assertEqual(expected_roles, set(records))
            self.assertEqual(
                registration["registration_id"],
                json.loads(
                    store.read_verified(records["runner_registration"]).decode("utf-8")
                )["registration_id"],
            )
            self.assertEqual(observation_record.artifact_id, records["treatment_observation"].artifact_id)
            score_document = json.loads(
                store.read_verified(records["score_artifact"]).decode("utf-8")
            )
            self.assertEqual("scored", score_document["availability"])
            # The registered reporting handoff scorer deliberately returns a
            # non-perfect score; lifecycle retention must preserve that value.
            self.assertEqual(0.75, score_document["value"])
            boundary_ref = ReportArtifactRef.from_record(records["execution_boundary"])
            treatment_ref = ReportArtifactRef.from_record(records["treatment_observation"])
            score_ref = ReportArtifactRef.from_record(records["score_artifact"])
            slot = plan.observations[0]
            observation_availability = AvailabilityRecord(
                affected_kind="evidence_role",
                affected="treatment_observation",
                state="retained",
                reason="Real registered mock process observation retained.",
                source_identity=treatment_ref.artifact_id,
            )
            score_availability = AvailabilityRecord(
                affected_kind="measurement",
                affected=metric_id,
                state="scored",
                reason="Registered diagnostic score retained.",
                source_identity=score_ref.artifact_id,
            )
            metric = RegisteredReportMetric(
                registration=metric_document,
                scorer=EvaluationIdentityRef(scorer_id, scorer_version),
                scoring_contracts=(
                    EvaluationIdentityRef(
                        SCORER_INVOCATION_CONTRACT_ID, SCORER_INVOCATION_CONTRACT_VERSION
                    ),
                ),
            )
            authority = admit_finalized_run_for_reporting(
                finalized,
                store=store,
                execution_boundary=boundary_ref,
                benchmark=EvaluationIdentityRef(benchmark.id, benchmark.version),
                case_set=EvaluationIdentityRef(case_set.id, case_set.version),
                treatment_set=EvaluationIdentityRef(treatment_set.id, treatment_set.version),
                comparison_track_id=metric_document["comparison_track_id"],
                primary_endpoint=EvaluationIdentityRef(metric_id, metric_version),
                metrics=(metric,),
                observation_counts=ObservationCounts(
                    planned=1, finalized=1, completed=1, scored=1,
                    failed=0, missing=0, excluded=0, non_scorable=0,
                ),
                observation_matrix=(
                    ObservationMatrixEntry(
                        observation_id=slot.observation_id,
                        request_id=slot.request_id,
                        case_id=slot.case_id,
                        treatment_id=slot.treatment_id,
                        repetition_id=slot.repetition,
                        execution_boundary_fingerprint=boundary.fingerprint,
                        availability=observation_availability,
                        evidence_refs=(treatment_ref,),
                    ),
                ),
                case_result_matrix=(
                    CaseResultEntry(
                        case_id=slot.case_id,
                        treatment_id=slot.treatment_id,
                        execution_boundary_fingerprint=boundary.fingerprint,
                        metric_registration_id=metric_registration_id,
                        metric_registration_version=metric_registration_version,
                        availability=score_availability,
                        value=score_document["value"],
                        evidence_refs=(score_ref,),
                    ),
                ),
                treatment_summaries=(
                    TreatmentSummary(
                        treatment_id=slot.treatment_id,
                        metric_registration_id=metric_registration_id,
                        metric_registration_version=metric_registration_version,
                        availability=score_availability,
                        planned=1, finalized=1, completed=1, scorable=1,
                        failed=0, missing=0, excluded=0, non_scorable=0,
                        numerator=0.75, denominator=1, value=score_document["value"],
                    ),
                ),
            )
            self.assertTrue(authority.valid)
            self.assertTrue(authority.synthetic_conformance)
            self.assertEqual(finalized.generation_id, authority.accepted_generation_id)
            original_read_verified = store.read_verified
            for altered in invalid_treatments:
                invalid_raw = altered.observation_bytes[0]

                def read_with_invalid_nested_evidence(record):
                    if record.artifact_id == observation_record.artifact_id:
                        return invalid_raw
                    return original_read_verified(record)

                # Isolate the reporting schema boundary after verified storage
                # has supplied bytes; the enclosing observation still validates.
                with mock.patch.object(
                    store, "read_verified", side_effect=read_with_invalid_nested_evidence,
                ):
                    with self.assertRaisesRegex(
                        ReportingInputRevalidationError,
                        "invalid shared execution evidence",
                    ):
                        revalidate_accepted_reporting_input(authority.accepted, store=store)
            sections = {
                name: ReportSection(availability="available")
                for name in REQUIRED_REPORT_SECTIONS
            }
            report = build_canonical_report_model(
                authority,
                report_id="report-registered-mock-lifecycle",
                report_version="1.0.0",
                status="complete",
                sections=sections,
                report_manifest_id="manifest-registered-mock-lifecycle",
                generated_at="2026-09-28T00:00:00Z",
            )
            bundle = generate_report_bundle(
                report,
                input_evidence_set_id="evidence-set-registered-mock-lifecycle",
                generator=EvaluationIdentityRef(
                    "arcgrav.generator.registered-mock-lifecycle", "1.0.0"
                ),
                procedure_id="arcgrav.procedure.registered-mock-lifecycle",
                procedure_version="1.0.0",
                command_or_procedure="registered diagnostic lifecycle report assembly",
                report_reference="generated/report.json",
                canonical_evidence_reference="generated/canonical-evidence.json",
                human_reference="generated/report.md",
                manifest_reference="generated/report-manifest.json",
            )
            self.assertEqual(
                {
                    "model_identity_kind": "synthetic_conformance_profile",
                },
                bundle.report_document["extensions"][
                    "arcgrav.reporting:synthetic-conformance"
                ],
            )
            self.assertIn(
                b"**Synthetic Conformance Profile:** Deterministic fixture evidence; no live model measurements.",
                bundle.human.data,
            )
            from AgMark.shared.reporting.completion import completion_record
            completion = completion_record(report.accepted_generation_id, status="complete", bundle=bundle)
            self.assertEqual(
                {component.artifact_id for component in (*bundle.components, bundle.manifest)},
                {item["artifact_id"] for item in completion["report"]["components"]},
            )


if __name__ == "__main__":
    unittest.main()
