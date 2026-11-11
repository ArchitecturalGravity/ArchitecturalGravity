"""Provider-free runtime tests for registered scoring and lifecycle reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.adapters.Mock_Model import load_registration
from AgMark.shared.software_testing.adapters.mock_model_support import resolve_model_identity
from AgMark.shared.evaluation import (
    SCORER_INVOCATION_CONTRACT_ID,
    SCORER_INVOCATION_CONTRACT_VERSION,
)
from AgMark.shared.runtime.artifacts import (
    FilesystemArtifactStore,
    PublicationDestination,
)
from AgMark.shared.runtime.golden import (
    GOLDEN_EXECUTION_CONTRACT_ID,
    GOLDEN_EXECUTION_CONTRACT_VERSION,
    GoldenArtifactRequirement,
    GoldenCaseInput,
    GoldenDeclaration,
)
from AgMark.shared.runtime.golden import execution as golden_execution
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    RUNNER_INVOCATION_CONTRACT_ID,
    RUNNER_INVOCATION_CONTRACT_VERSION,
    AcceptedRun,
    AcceptedScoringError,
    BlockedRun,
    PlannedCaseInput,
    RegisteredScoringDefinition,
    RuntimeFinalizationError,
    SCORER_ENTRY_POINT_EXTENSION,
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
    ContractRequirement,
    validate_registration_binding_outcome,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_TEST_MODULE = "AgMark.shared.software_testing.runtime.test_scoring_orchestration"
_TEST_REFERENCE = (
    "AgMark/shared/software_testing/runtime/test_scoring_orchestration.py"
)
_RUNNER_ID = "arcgrav.mock-model.runner"
_RUNNER_VERSION = "1.0.0"
_SCORER_ID = "arcgrav.scorer.runtime-test"
_FAILED_SCORER_ID = "arcgrav.scorer.runtime-test-failing"
_EXACT_PAYLOAD_SCORER_ID = "arcgrav.scorer.runtime-test-exact-payload"
_SCORER_VERSION = "1.0.0"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def registered_runtime_scorer(call) -> Mapping[str, object]:
    observation = json.loads(
        call.evidence_by_role["treatment_observation"].decode("utf-8")
    )
    if observation["terminal_status"] == "completed":
        return {
            "availability": "scored",
            "value": 1.0,
            "companion_values": [],
            "failure_refs": [],
            "diagnostics": [],
            "extensions": {"arcgrav.test:runtime-scoring": "provider-free"},
        }
    return {
        "availability": "failed",
        "companion_values": [],
        "failure_refs": ["failure:" + observation["observation_id"]],
        "diagnostics": ["RUNTIME_SCORER_OBSERVED_FAILED_TREATMENT"],
        "extensions": {"arcgrav.test:runtime-scoring": "provider-free"},
    }


def failing_runtime_scorer(call) -> Mapping[str, object]:
    del call
    raise RuntimeError("provider-free registered scorer failure")


def registered_exact_payload_scorer(call) -> Mapping[str, object]:
    golden = call.evidence_by_role["golden_stdout"]
    response = call.evidence_by_role["treatment_response"]
    if golden != b"runtime-scoring-case-input":
        raise RuntimeError("exact retained golden stdout was not supplied")
    return {
        "availability": "scored",
        "value": len(golden) + len(response),
        "companion_values": [],
        "failure_refs": [],
        "diagnostics": [],
        "extensions": {"arcgrav.test:exact-payload-scoring": True},
    }


def _metric_registration(scorer_id: str) -> dict[str, object]:
    return {
        "schema_id": "arcgrav.shared.schema.metric-registration",
        "schema_version": "1.0.0",
        "extensions": {},
        "registration_id": "arcgrav.metric.runtime-score",
        "registration_version": "1.0.0",
        "metric_id": "arcgrav.metric.runtime-score",
        "metric_version": "1.0.0",
        "name": "Runtime registered score",
        "description": "Provider-free runtime scoring lifecycle evidence.",
        "classification": "correctness",
        "comparison_track_id": "runtime",
        "is_primary_endpoint": False,
        "formula_or_algorithm": (
            "Score exact retained treatment-observation evidence without repair."
        ),
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
        "normalization_and_equivalence": (
            "No normalization or semantic equivalence."
        ),
        "availability_and_noncomparability": (
            "Preserve explicit shared availability and failure states."
        ),
        "required_companion_values": [],
        "presentation_precision": 3,
        "scorer_or_annotation": {
            "procedure_id": scorer_id,
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


def _exact_payload_metric_registration(scorer_id: str) -> dict[str, object]:
    registration = _metric_registration(scorer_id)
    registration.update(
        {
            "registration_id": "arcgrav.metric.runtime-exact-payload",
            "metric_id": "arcgrav.metric.runtime-exact-payload",
            "name": "Runtime exact retained payload score",
            "description": (
                "Provider-free proof that declared golden stdout and treatment "
                "response roles receive exact retained payload bytes."
            ),
            "formula_or_algorithm": (
                "Return the combined exact retained byte length after verifying "
                "the golden payload."
            ),
            "required_inputs": ["golden_stdout", "treatment_response"],
            "unit": "bytes",
            "valid_range": {
                "kind": "numeric",
                "minimum": 0.0,
                "maximum": None,
            },
            "directionality": "none",
            "normalization_and_equivalence": (
                "No normalization; scorer consumes exact retained bytes."
            ),
        }
    )
    return registration


def _boundary(
    *,
    outcome: str = "completed",
    environment: Mapping[str, object] | None = None,
) -> ExecutionBoundary:
    resolved_runtime, resolved_controls = resolve_model_identity("mock-base::scenario:process_failure" if outcome == "failed" else "mock-base::scenario:completed")
    return ExecutionBoundary.build(
        boundary_id="boundary-runtime-scoring-test-" + outcome,
        framework=IdentityRef(
            "arcgrav.framework.runtime-scoring-test",
            "1.0.0",
        ),
        runner=IdentityRef(_RUNNER_ID, _RUNNER_VERSION),
        provider_runtime=resolved_runtime,
        controls=resolved_controls,
        environment=dict(
            environment
            if environment is not None
            else {"runtime_family": "provider-free"}
        ),
    )


class RegisteredScoringRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.benchmark = IdentityRef(
            "arcgrav.benchmark.runtime-scoring-test",
            "1.0.0",
            sha256=_sha256(b"benchmark-runtime-scoring-test"),
        )
        self.case_set = IdentityRef(
            "arcgrav.case-set.runtime-scoring-test",
            "1.0.0",
            sha256=_sha256(b"case-set-runtime-scoring-test"),
        )
        self.treatment_set = IdentityRef(
            "arcgrav.treatment-set.runtime-scoring-test",
            "1.0.0",
            sha256=_sha256(b"treatment-set-runtime-scoring-test"),
        )

    def _definition(
        self,
        *,
        scorer_id: str = _SCORER_ID,
        entry_point: str = "registered_runtime_scorer",
        metric_registration: Mapping[str, object] | None = None,
    ) -> RegisteredScoringDefinition:
        implementation_bytes = Path(__file__).read_bytes()
        source = ArtifactSource(
            artifact_id="runtime-test-scorer",
            reference=_TEST_REFERENCE,
            data=implementation_bytes,
        )
        registration = {
            "schema_id": "arcgrav.shared.schema.registration",
            "schema_version": "1.0.0",
            "extensions": {
                SCORER_ENTRY_POINT_EXTENSION: (
                    _TEST_MODULE + ":" + entry_point
                ),
            },
            "registration_id": scorer_id,
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
            expected_registration_id=scorer_id,
            expected_registration_version=_SCORER_VERSION,
            contract_requirements=(
                ContractRequirement(
                    SCORER_INVOCATION_CONTRACT_ID,
                    (SCORER_INVOCATION_CONTRACT_VERSION,),
                ),
            ),
            artifact_sources=(source,),
            allowed_artifact_roots=(
                "AgMark/shared/software_testing/runtime",
            ),
            source_id="runtime-scorer-registration:" + scorer_id,
        )
        self.assertTrue(
            outcome.valid,
            [issue.code for issue in outcome.issues],
        )
        return RegisteredScoringDefinition(
            metric_registration=(
                _metric_registration(scorer_id)
                if metric_registration is None
                else metric_registration
            ),
            scorer_registration=registration,
            scorer_registration_outcome=outcome,
        )

    def _started(
        self,
        root: Path,
        *,
        generation_id: str,
        outcome: str = "completed",
        treatment_set: IdentityRef | None = None,
    ):
        boundary = _boundary(outcome=outcome)
        active_treatment_set = treatment_set or self.treatment_set
        case_data = b"runtime-scoring-case-input"
        plan = plan_run(
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=active_treatment_set,
            cases=(
                PlannedCaseInput(
                    "case-runtime-scoring",
                    _sha256(case_data),
                    byte_length=len(case_data),
                ),
            ),
            treatments=("treatment-runtime-scoring",),
            repetitions=2,
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
        store = FilesystemArtifactStore(
            PublicationDestination.benchmark_owned(
                root / "evidence",
                benchmark_root=root,
            )
        )
        gate = admit_accepted_execution(
            generation_id=generation_id,
            snapshot=snapshot,
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=active_treatment_set,
            execution_boundary=boundary,
            benchmark_root=root,
            artifact_store=store,
        )
        treatment = execute_planned_treatments(
            gate=gate,
            snapshot=snapshot,
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=active_treatment_set,
            execution_boundary=boundary,
            artifact_store=store,
            repository_root=_REPOSITORY_ROOT,
            runner_registration=load_registration(),
            case_inputs=(
                TreatmentCaseInput(
                    "case-runtime-scoring",
                    case_data,
                ),
            ),
            treatment_prompts=(
                TreatmentPrompt(
                    "treatment-runtime-scoring",
                    b"runtime-scoring-prompt",
                ),
            ),
        )
        return boundary, plan, snapshot, store, gate, treatment

    def _started_with_golden(
        self,
        root: Path,
        *,
        generation_id: str,
        registered_file: bool = False,
        treatment_ids: tuple[str, ...] = ("treatment-runtime-scoring",),
        repetitions: int = 1,
    ):
        case_data = b"runtime-scoring-case-input"
        golden_script = root / "runtime_scoring_golden.py"
        golden_script.write_text(
            (
                "import sys\nfrom pathlib import Path\n"
                "sys.stdout.buffer.write((Path(__file__).parent / 'source.json').read_bytes())\n"
                if registered_file
                else "import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n"
            ),
            encoding="utf-8",
        )
        executable = Path(sys.executable).resolve(strict=True)
        boundary = _boundary(
            environment={
                "runtime_family": "provider-free",
                "golden.environment_family": "native",
                "golden.runtime_sha256": _sha256(executable.read_bytes()),
            }
        )
        plan = plan_run(
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=self.treatment_set,
            cases=(
                PlannedCaseInput(
                    "case-runtime-scoring",
                    _sha256(case_data),
                    byte_length=len(case_data),
                ),
            ),
            treatments=treatment_ids,
            repetitions=repetitions,
            execution_boundary=boundary,
            golden_required=True,
            contracts=(
                IdentityRef(
                    GOLDEN_EXECUTION_CONTRACT_ID,
                    GOLDEN_EXECUTION_CONTRACT_VERSION,
                ),
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
        store = FilesystemArtifactStore(
            PublicationDestination.benchmark_owned(
                root / "evidence",
                benchmark_root=root,
            )
        )
        dependencies = [GoldenArtifactRequirement(
            artifact_id=golden_script.name,
            relative_path=golden_script.name,
            sha256=_sha256(golden_script.read_bytes()),
        )]
        if registered_file:
            (root / "source.json").write_bytes(case_data)
            dependencies.append(GoldenArtifactRequirement(
                artifact_id="case-input", relative_path="source.json", sha256=_sha256(case_data)
            ))
        declaration = GoldenDeclaration(
            runtime_executable=str(executable),
            golden_implementation=IdentityRef(
                "arcgrav.golden.runtime-scoring-test",
                "1.0.0",
            ),
            runtime_identity=IdentityRef(
                "arcgrav.runtime.python",
                "1.0.0",
                sha256=_sha256(executable.read_bytes()),
                reference="runtime/python",
            ),
            artifacts=tuple(dependencies),
            entry_artifact_id=golden_script.name,
            environment_family="native",
            input_transport="registered_file" if registered_file else "stdin",
            input_artifact_id="case-input" if registered_file else None,
        )
        gate = admit_accepted_execution(
            generation_id=generation_id,
            snapshot=snapshot,
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=self.treatment_set,
            execution_boundary=boundary,
            benchmark_root=root,
            artifact_store=store,
            golden_declaration=declaration,
            golden_case_inputs=(
                GoldenCaseInput("case-runtime-scoring", case_data),
            ),
        )
        self.assertNotIsInstance(gate, BlockedRun)
        treatment = execute_planned_treatments(
            gate=gate,
            snapshot=snapshot,
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=self.treatment_set,
            execution_boundary=boundary,
            artifact_store=store,
            repository_root=_REPOSITORY_ROOT,
            runner_registration=load_registration(),
            case_inputs=(
                TreatmentCaseInput("case-runtime-scoring", case_data),
            ),
            treatment_prompts=tuple(
                TreatmentPrompt(treatment_id, b"runtime-scoring-prompt")
                for treatment_id in treatment_ids
            ),
        )
        return boundary, plan, snapshot, store, gate, treatment, case_data

    def test_registered_scoring_supplies_exact_retained_payload_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (
                boundary,
                _,
                snapshot,
                store,
                gate,
                treatment,
                case_data,
            ) = self._started_with_golden(
                root,
                generation_id="generation-runtime-scoring-exact-payloads",
            )
            metric = _exact_payload_metric_registration(
                _EXACT_PAYLOAD_SCORER_ID
            )
            result = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(
                    self._definition(
                        scorer_id=_EXACT_PAYLOAD_SCORER_ID,
                        entry_point="registered_exact_payload_scorer",
                        metric_registration=metric,
                    ),
                ),
            )

            self.assertEqual("accepted", result.classification)
            (score,) = result.scores()
            (observation,) = treatment.observations()
            self.assertEqual(
                len(case_data) + observation["response"]["byte_length"],
                score["value"],
            )
            self.assertEqual(
                {"golden_stdout", "treatment_response"},
                set(
                    score["extensions"][
                        "arcgrav.shared.evaluation:input-role-bindings"
                    ]
                ),
            )
            self.assertEqual(2, len(score["input_evidence"]))
            self.assertTrue(
                any(
                    item["artifact_id"].endswith(".stdout")
                    for item in score["input_evidence"]
                )
            )
            self.assertTrue(
                any(
                    item["artifact_id"].endswith(".response")
                    for item in score["input_evidence"]
                )
            )
            result.revalidate(store)

    def test_one_registered_file_golden_is_reused_across_treatments_and_repetitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.object(
                golden_execution, "_run_process", wraps=golden_execution._run_process
            ) as workload:
                boundary, _, snapshot, store, gate, treatment, case_data = self._started_with_golden(
                    root,
                    generation_id="generation-file-golden-reuse",
                    registered_file=True,
                    treatment_ids=("treatment-a", "treatment-b", "treatment-c"),
                    repetitions=2,
                )
            self.assertEqual(1, workload.call_count)
            self.assertEqual(1, len(gate.golden_observations))
            self.assertEqual(6, len(treatment.observations()))
            golden_record, = (
                record for record in gate.retained_golden_artifacts
                if record.role == "golden_stdout"
            )
            self.assertEqual(case_data, store.read_verified(golden_record))
            # Evaluation and finalization must use captured evidence even when
            # the live implementation and input no longer exist.
            (root / "source.json").unlink()
            (root / "runtime_scoring_golden.py").unlink()
            with patch.object(
                golden_execution, "_run_process", side_effect=AssertionError("Golden rerun")
            ) as rerun:
                scoring = score_accepted_treatments(
                    gate=gate,
                    snapshot=snapshot,
                    benchmark=self.benchmark,
                    case_set=self.case_set,
                    treatment_set=self.treatment_set,
                    execution_boundary=boundary,
                    treatment_result=treatment,
                    artifact_store=store,
                    scoring_definitions=(self._definition(
                        scorer_id=_EXACT_PAYLOAD_SCORER_ID,
                        entry_point="registered_exact_payload_scorer",
                        metric_registration=_exact_payload_metric_registration(_EXACT_PAYLOAD_SCORER_ID),
                    ),),
                )
                terminal = finalize_scored_run(
                    gate=gate, treatment_result=treatment,
                    scoring_result=scoring, artifact_store=store,
                )
            rerun.assert_not_called()
            self.assertIsInstance(terminal, AcceptedRun)
            self.assertEqual(6, len(scoring.scores()))
            for score in scoring.scores():
                self.assertEqual("scored", score["availability"])
                golden_input, = (
                    item for item in score["input_evidence"]
                    if item["artifact_id"] == golden_record.artifact_id
                )
                self.assertEqual(golden_record.sha256, golden_input["sha256"])
                self.assertEqual(golden_record.reference, golden_input["reference"])

    def test_registered_scoring_retains_exact_scores_and_valid_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            boundary, plan, snapshot, store, gate, treatment = self._started(
                root,
                generation_id="generation-runtime-scoring-success",
            )
            result = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(self._definition(),),
            )

            self.assertEqual("accepted", result.classification)
            self.assertIsNone(result.reason_code)
            self.assertEqual((), result.diagnostics)
            self.assertTrue(result.lifecycle_outcome.valid)
            self.assertEqual(2, len(result.retained_score_artifacts))
            for observation in treatment.observations():
                self.assertIsInstance(observation["attempts"][0]["started_at"], str)
                self.assertIsInstance(observation["attempts"][0]["completed_at"], str)
                execution_window = observation["extensions"][
                    "arcgrav.shared.runtime.orchestration:execution-window"
                ]
                self.assertIsInstance(execution_window["started_at"], str)
                self.assertIsInstance(execution_window["completed_at"], str)
            scores = result.scores()
            self.assertEqual(
                tuple(item.observation_id for item in plan.observations),
                tuple(score["observation_ids"][0] for score in scores),
            )
            self.assertTrue(
                all(score["availability"] == "scored" for score in scores)
            )
            self.assertTrue(all(score["value"] == 1.0 for score in scores))
            result.revalidate(store)
            self.assertFalse(
                (
                    store.root
                    / ".generation-runtime-scoring-success.terminal"
                ).exists()
            )

    def test_registered_scorer_failure_blocks_without_synthetic_scores(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            boundary, _, snapshot, store, gate, treatment = self._started(
                root,
                generation_id="generation-runtime-scoring-failure",
            )
            result = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(
                    self._definition(
                        scorer_id=_FAILED_SCORER_ID,
                        entry_point="failing_runtime_scorer",
                    ),
                ),
            )

            self.assertEqual("blocked", result.classification)
            self.assertEqual(
                "registered_scoring_failed",
                result.reason_code,
            )
            self.assertEqual((), result.retained_reporting_artifacts)
            self.assertEqual((), result.scores())
            self.assertTrue(
                any(
                    diagnostic.startswith("SCORER_INVOCATION_FAILED:")
                    for diagnostic in result.diagnostics
                ),
                result.diagnostics,
            )
            self.assertTrue(result.lifecycle_outcome.valid)

    def test_explicit_failed_observation_remains_non_scored_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            boundary, _, snapshot, store, gate, treatment = self._started(
                root,
                generation_id="generation-runtime-scoring-non-success",
                outcome="failed",
            )
            result = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(self._definition(),),
            )

            self.assertEqual("accepted", result.classification)
            self.assertTrue(result.lifecycle_outcome.valid)
            for score in result.scores():
                self.assertEqual("failed", score["availability"])
                self.assertNotIn("value", score)
                self.assertTrue(score["failure_refs"])

    def test_treatment_plan_mismatch_classifies_blocked_before_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            boundary, _, _, store, _, treatment = self._started(
                root,
                generation_id="generation-runtime-scoring-mismatch",
            )
            alternate_treatment_set = IdentityRef(
                "arcgrav.treatment-set.runtime-scoring-test-alternate",
                "1.0.0",
                sha256=_sha256(b"alternate-treatment-set"),
            )
            alternate_plan = plan_run(
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=alternate_treatment_set,
                cases=(
                    PlannedCaseInput(
                        "case-runtime-scoring",
                        _sha256(b"runtime-scoring-case-input"),
                        byte_length=len(b"runtime-scoring-case-input"),
                    ),
                ),
                treatments=("treatment-runtime-scoring",),
                repetitions=2,
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
            alternate_snapshot = accept_run_plan(
                plan=alternate_plan,
                execution_boundary=boundary,
            )
            alternate_gate = admit_accepted_execution(
                generation_id="generation-runtime-scoring-mismatch",
                snapshot=alternate_snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=alternate_treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=store,
            )

            result = score_accepted_treatments(
                gate=alternate_gate,
                snapshot=alternate_snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=alternate_treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(self._definition(),),
            )

            self.assertEqual("blocked", result.classification)
            self.assertIn(
                "ORCHESTRATION_TREATMENT_PLAN_MISMATCH",
                result.diagnostics,
            )
            self.assertTrue(
                any(
                    issue.code == "LIFECYCLE_TREATMENT_BEFORE_ACCEPTANCE"
                    for issue in result.lifecycle_outcome.issues
                ),
                [issue.code for issue in result.lifecycle_outcome.issues],
            )
            self.assertEqual((), result.scores())

    def test_unsupported_registered_input_role_blocks_with_missing_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            boundary, _, snapshot, store, gate, treatment = self._started(
                root,
                generation_id="generation-runtime-scoring-missing-input",
            )
            definition = self._definition()
            metric = dict(definition.metric_registration)
            metric["required_inputs"] = ["unsupported_runtime_input"]
            definition = RegisteredScoringDefinition(
                metric_registration=metric,
                scorer_registration=definition.scorer_registration,
                scorer_registration_outcome=(
                    definition.scorer_registration_outcome
                ),
            )

            result = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(definition,),
            )

            self.assertEqual("blocked", result.classification)
            self.assertEqual((), result.scores())
            self.assertTrue(
                any(
                    diagnostic.startswith(
                        "SCORER_REQUIRED_INPUT_ROLE_UNSUPPORTED:"
                    )
                    for diagnostic in result.diagnostics
                ),
                result.diagnostics,
            )

    def test_finalization_publishes_one_accepted_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            boundary, _, snapshot, store, gate, treatment = self._started(
                root,
                generation_id="generation-runtime-finalization-accepted",
            )
            scoring = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(self._definition(),),
            )

            terminal = finalize_scored_run(
                gate=gate,
                treatment_result=treatment,
                scoring_result=scoring,
                artifact_store=store,
            )

            self.assertIsInstance(terminal, AcceptedRun)
            self.assertEqual(
                "accepted",
                terminal.run_outcome()["status"],
            )
            self.assertEqual(
                scoring.generation_id,
                terminal.artifact_index.generation_id,
            )
            self.assertEqual(
                {
                    record.artifact_id
                    for record in (
                        *gate.retained_golden_artifacts,
                        treatment.retained_runner_registration_artifact,
                        *treatment.retained_observation_artifacts,
                        *scoring.retained_score_artifacts,
                        *scoring.retained_reporting_artifacts,
                    )
                },
                {record.artifact_id for record in terminal.artifact_index.artifacts},
            )
            self.assertTrue(
                any(
                    record.role == "score_artifact"
                    for record in terminal.artifact_index.artifacts
                )
            )
            self.assertEqual(
                {"execution_boundary", "metric_registration"},
                {
                    record.role
                    for record in scoring.retained_reporting_artifacts
                },
            )
            self.assertTrue(
                all(
                    record in terminal.artifact_index.artifacts
                    for record in scoring.retained_reporting_artifacts
                )
            )
            self.assertEqual(
                b"accepted",
                (
                    store.root
                    / ".generation-runtime-finalization-accepted.terminal"
                ).read_bytes(),
            )
            terminal.revalidate(store)

            with self.assertRaises(RuntimeFinalizationError):
                finalize_scored_run(
                    gate=gate,
                    treatment_result=treatment,
                    scoring_result=scoring,
                    artifact_store=store,
                )

    def test_finalization_retains_started_blocked_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            boundary, _, snapshot, store, gate, treatment = self._started(
                root,
                generation_id="generation-runtime-finalization-blocked",
            )
            scoring = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(
                    self._definition(
                        scorer_id=_FAILED_SCORER_ID,
                        entry_point="failing_runtime_scorer",
                    ),
                ),
            )

            terminal = finalize_scored_run(
                gate=gate,
                treatment_result=treatment,
                scoring_result=scoring,
                artifact_store=store,
            )

            self.assertIsInstance(terminal, BlockedRun)
            self.assertEqual("registered_scoring_failed", terminal.reason_code)
            self.assertEqual(2, len(terminal.treatment_observations))
            manifest = terminal.artifact_manifest.to_run_outcome_field()
            self.assertEqual("registered_scoring_failed", manifest["reason_code"])
            self.assertTrue(manifest["retained_diagnostics"])
            self.assertFalse(
                any(
                    role.role == "accepted_artifact_index"
                    and role.availability == "retained"
                    for role in terminal.artifact_manifest.evidence_roles
                )
            )
            self.assertEqual(
                b"blocked",
                (
                    store.root
                    / ".generation-runtime-finalization-blocked.terminal"
                ).read_bytes(),
            )

            with self.assertRaises(RuntimeFinalizationError):
                finalize_scored_run(
                    gate=gate,
                    treatment_result=treatment,
                    scoring_result=scoring,
                    artifact_store=store,
                )

    def test_retained_score_drift_fails_exact_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            boundary, _, snapshot, store, gate, treatment = self._started(
                root,
                generation_id="generation-runtime-scoring-drift",
            )
            result = score_accepted_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                treatment_result=treatment,
                artifact_store=store,
                scoring_definitions=(self._definition(),),
            )
            record = result.retained_score_artifacts[0]
            path = store.root / record.reference
            path.chmod(0o600)
            path.write_bytes(b"tampered-score-artifact")

            with self.assertRaises(AcceptedScoringError):
                result.revalidate(store)


if __name__ == "__main__":
    unittest.main()
