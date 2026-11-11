"""Provider-free integration evidence for ARB traversal through the public shared lifecycle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from AgMark.Authority_Resolution_Benchmark.reporting.prerequisites import (
    derive_registered_prerequisites,
    evaluate_report_extensions,
)
from AgMark.shared.adapters.Codex_CLI import (
    CodexCliRunner,
    load_registration as load_codex_registration,
)
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
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    AcceptedExecutionError,
    RUNNER_INVOCATION_CONTRACT_ID,
    RUNNER_INVOCATION_CONTRACT_VERSION,
    AcceptedRun,
    BlockedRun,
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
from AgMark.shared.runtime.orchestration.execution import (
    TRANSIENT_INVOCATION_CONTRACT_ID,
    TRANSIENT_INVOCATION_CONTRACT_VERSION,
)
from AgMark.shared.validation import (
    ArtifactSource,
    BenchmarkDiscoveryCandidate,
    ContractRequirement,
    validate_benchmark_discovery,
    validate_registration_binding_outcome,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_REGISTRATION_REFERENCE = (
    "AgMark/Authority_Resolution_Benchmark/registrations/v2.0.0/"
    "benchmark-core.json"
)
_REGISTRATION_ID = "arcgrav.authority-resolution.benchmark.core"
_REGISTRATION_VERSION = "2.0.0"
_AUTHORITY_EXTENSION = "arcgrav.authority-resolution:benchmark-authority"
_RUNNER_ID = "arcgrav.mock-model.runner"
_RUNNER_VERSION = "1.0.0"
_CODEX_RUNNER_ID = "openai.codex-cli"
_CODEX_RUNNER_VERSION = "2.0.0"
_PACKAGE_PREFIX = Path("AgMark/Authority_Resolution_Benchmark")


class _ProviderFreeCodexFixtureRunner:
    """Test-only non-network runner behind the exact Codex registration."""

    def __init__(self) -> None:
        self._closed = False

    def describe(self) -> dict[str, object]:
        return {
            "runner": {"id": _CODEX_RUNNER_ID, "version": _CODEX_RUNNER_VERSION},
            "contract": {
                "id": RUNNER_INVOCATION_CONTRACT_ID,
                "version": RUNNER_INVOCATION_CONTRACT_VERSION,
            },
            "registration": load_codex_registration(),
        }

    def execute(self, request: dict[str, object]) -> dict[str, object]:
        if self._closed:
            raise RuntimeError("provider-free Codex fixture is closed")
        from uuid import uuid4
        thread_id = str(uuid4())
        class FixtureTransport:
            def run(self, argv, *, input_bytes, cwd, env, timeout_ms):
                if tuple(argv[1:]) == ("--version",):
                    stdout = b"codex-cli 1.0.0\n"
                elif tuple(argv[1:]) == ("exec", "--help"):
                    stdout = b"--model --approve-for-me --ephemeral --ignore-user-config --skip-git-repo-check --color"
                elif input_bytes is not None:
                    stdout = b'\n'.join(json.dumps(event).encode() for event in [
                        {"type": "thread.started", "thread_id": thread_id}, {"type": "turn.started"},
                        {"type": "item.completed", "item": {"id": "answer", "type": "agent_message", "text": "provider-free non-mock ARB fixture response"}},
                        {"type": "turn.completed", "usage": {}}]) + b'\n'
                else:
                    raise AssertionError(f"unexpected fixture command: {argv!r}")
                return {"returncode": 0, "stdout": stdout, "stderr": b""}
        runner = CodexCliRunner(
            registration=load_codex_registration(), transport=FixtureTransport(),
            executable_resolver=lambda selected: "/controlled/codex", platform_name="posix",
        )
        try:
            return runner.execute(request)
        finally:
            runner.close()

    def close(self) -> None:
        self._closed = True


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load_json(reference: str) -> dict[str, object]:
    return json.loads((_REPOSITORY_ROOT / reference).read_text(encoding="utf-8"))


def _benchmark_registration() -> tuple[dict[str, object], object]:
    registration = _load_json(_REGISTRATION_REFERENCE)
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
        expected_registration_id=_REGISTRATION_ID,
        expected_registration_version=_REGISTRATION_VERSION,
        contract_requirements=tuple(
            ContractRequirement(contract["id"], (contract["version"],))
            for contract in registration["contracts"]
        ),
        artifact_sources=sources,
        allowed_artifact_roots=("AgMark/Authority_Resolution_Benchmark",),
        source_id="arb-integration-benchmark-registration",
    )
    if not outcome.valid:
        raise AssertionError([issue.code for issue in outcome.issues])
    discovery = validate_benchmark_discovery(
        (
            BenchmarkDiscoveryCandidate(
                package_root="AgMark/Authority_Resolution_Benchmark",
                registration_source_id="arb-integration-benchmark-registration",
                registration=registration,
                registration_validation=outcome,
            ),
        ),
        source_id="arb-integration-benchmark-discovery",
    )
    if discovery:
        raise AssertionError([issue.code for issue in discovery])
    return registration, outcome


def _artifact_by_id(
    registration: dict[str, object],
    artifact_id: str,
) -> dict[str, object]:
    return next(
        artifact
        for artifact in registration["implementation_artifacts"]
        if artifact["artifact_id"] == artifact_id
    )


def _validated_runner_registration(
    registration: dict[str, object] | None = None,
    *,
    runner_id: str = _RUNNER_ID,
    runner_version: str = _RUNNER_VERSION,
) -> tuple[dict[str, object], object]:
    if registration is None:
        registration = load_registration()
    sources = tuple(
        ArtifactSource(
            artifact_id=artifact["artifact_id"],
            reference=artifact["reference"],
            data=(_REPOSITORY_ROOT / artifact["reference"]).read_bytes(),
        )
        for artifact in registration["implementation_artifacts"]
    )
    contract_requirements = [
        ContractRequirement(
            RUNNER_INVOCATION_CONTRACT_ID,
            (RUNNER_INVOCATION_CONTRACT_VERSION,),
        )
    ]
    if any(
        isinstance(contract, dict)
        and contract.get("id") == TRANSIENT_INVOCATION_CONTRACT_ID
        for contract in registration.get("contracts", ())
    ):
        contract_requirements.append(
            ContractRequirement(
                TRANSIENT_INVOCATION_CONTRACT_ID,
                (TRANSIENT_INVOCATION_CONTRACT_VERSION,),
            )
        )

    outcome = validate_registration_binding_outcome(
        registration,
        expected_registration_id=runner_id,
        expected_registration_version=runner_version,
        contract_requirements=tuple(contract_requirements),
        artifact_sources=sources,
        allowed_artifact_roots=("AgMark/shared/adapters", "AgMark/shared/telemetry", "AgMark/shared/mock_model", "AgMark/shared/evaluation/telemetry/source.py", "AgMark/shared/runtime/identity/runtime_version.py"),
        source_id="arb-integration-runner-registration",
    )
    if not outcome.valid:
        raise AssertionError([issue.code for issue in outcome.issues])
    return registration, outcome


def _scoring_definition(
    benchmark_registration: dict[str, object],
) -> RegisteredScoringDefinition:
    selected = benchmark_registration["extensions"][_AUTHORITY_EXTENSION][
        "selected_authority"
    ]
    metric_selected = selected["primary_metric"]
    scorer_selected = selected["scorer"]

    metric_artifact = _artifact_by_id(
        benchmark_registration,
        metric_selected["artifact_id"],
    )
    scorer_registration_artifact = _artifact_by_id(
        benchmark_registration,
        scorer_selected["registration_artifact_id"],
    )
    metric_registration = _load_json(metric_artifact["reference"])
    scorer_registration = _load_json(scorer_registration_artifact["reference"])

    sources = tuple(
        ArtifactSource(
            artifact_id=artifact["artifact_id"],
            reference=artifact["reference"],
            data=(_REPOSITORY_ROOT / artifact["reference"]).read_bytes(),
        )
        for artifact in scorer_registration["implementation_artifacts"]
    )
    scorer_outcome = validate_registration_binding_outcome(
        scorer_registration,
        expected_registration_id=scorer_selected["registration_id"],
        expected_registration_version=scorer_selected["registration_version"],
        contract_requirements=(
            ContractRequirement(
                SCORER_INVOCATION_CONTRACT_ID,
                (SCORER_INVOCATION_CONTRACT_VERSION,),
            ),
        ),
        artifact_sources=sources,
        allowed_artifact_roots=("AgMark/Authority_Resolution_Benchmark",),
        source_id="arb-integration-scorer-registration",
    )
    if not scorer_outcome.valid:
        raise AssertionError([issue.code for issue in scorer_outcome.issues])

    return RegisteredScoringDefinition(
        metric_registration=metric_registration,
        scorer_registration=scorer_registration,
        scorer_registration_outcome=scorer_outcome,
    )


def _selected_inputs(
    registration: dict[str, object],
) -> tuple[
    IdentityRef,
    IdentityRef,
    bytes,
    tuple[TreatmentPrompt, ...],
    dict[str, object],
]:
    selected = registration["extensions"][_AUTHORITY_EXTENSION]["selected_authority"]
    case_selected = selected["case_set"]
    treatment_selected = selected["treatment_set"]

    case_set_artifact = _artifact_by_id(registration, case_selected["artifact_id"])
    treatment_set_artifact = _artifact_by_id(
        registration,
        treatment_selected["artifact_id"],
    )
    case_set_document = _load_json(case_set_artifact["reference"])
    treatment_set_document = _load_json(treatment_set_artifact["reference"])

    (case_entry,) = case_set_document["cases"]
    case_reference = (
        "AgMark/Authority_Resolution_Benchmark/"
        + case_entry["input"]["reference"]
    )
    case_data = (_REPOSITORY_ROOT / case_reference).read_bytes()
    if _sha256(case_data) != case_entry["input"]["sha256"]:
        raise AssertionError("registered ARB case input hash drifted")

    prompts = []
    for treatment in treatment_set_document["treatments"]:
        prompt_reference = (
            "AgMark/Authority_Resolution_Benchmark/"
            + treatment["prompt"]["reference"]
        )
        prompt_data = (_REPOSITORY_ROOT / prompt_reference).read_bytes()
        if _sha256(prompt_data) != treatment["prompt"]["sha256"]:
            raise AssertionError(
                f"registered ARB treatment prompt drifted: {treatment['treatment_id']}"
            )
        prompts.append(
            TreatmentPrompt(
                treatment["treatment_id"],
                prompt_data,
            )
        )

    case_set = IdentityRef(
        case_selected["id"],
        case_selected["version"],
        sha256=case_set_artifact["sha256"],
        reference=case_set_artifact["reference"],
    )
    treatment_set = IdentityRef(
        treatment_selected["id"],
        treatment_selected["version"],
        sha256=treatment_set_artifact["sha256"],
        reference=treatment_set_artifact["reference"],
    )
    return (
        case_set,
        treatment_set,
        case_data,
        tuple(prompts),
        case_entry,
    )


def _prepare_golden(
    root: Path,
    registration: dict[str, object],
) -> tuple[Path, GoldenDeclaration]:
    selected = registration["extensions"][_AUTHORITY_EXTENSION]["selected_authority"]
    authority = selected["golden_authority"]
    golden_artifact = _artifact_by_id(
        registration,
        authority["artifact_id"],
    )
    benchmark_root = root / "arb"
    artifacts = []
    for artifact_id in authority["implementation_artifact_ids"]:
        artifact = _artifact_by_id(registration, artifact_id)
        registered_reference = Path(artifact["reference"])
        relative_reference = registered_reference.relative_to(_PACKAGE_PREFIX)
        source = (_REPOSITORY_ROOT / registered_reference).read_bytes()
        if _sha256(source) != artifact["sha256"]:
            raise AssertionError("registered ARB golden dependency hash drifted")
        target = benchmark_root / relative_reference
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source)
        artifacts.append(
            GoldenArtifactRequirement(
                artifact_id=artifact_id,
                relative_path=relative_reference.as_posix(),
                sha256=artifact["sha256"],
            )
        )

    executable = Path(sys.executable).resolve(strict=True)
    declaration = GoldenDeclaration(
        golden_implementation=IdentityRef(
            "arcgrav.authority-resolution.golden.core",
            _REGISTRATION_VERSION,
            sha256=golden_artifact["sha256"],
            reference=golden_artifact["reference"],
        ),
        runtime_executable=str(executable),
        runtime_identity=IdentityRef(
            "arcgrav.runtime.python",
            "1.0.0",
            sha256=_sha256(executable.read_bytes()),
            reference="runtime/python",
        ),
        artifacts=tuple(artifacts),
        entry_artifact_id=golden_artifact["artifact_id"],
        input_transport=authority["input_transport"],
        input_artifact_id=authority["input_artifact_id"],
        environment_family="native",
    )
    return benchmark_root, declaration


class AuthorityResolutionLifecycleIntegrationTests(unittest.TestCase):
    def test_active_arb_registration_traverses_public_shared_lifecycle(self) -> None:
        registration, registration_outcome = _benchmark_registration()
        selected = registration["extensions"][_AUTHORITY_EXTENSION][
            "selected_authority"
        ]
        case_set, treatment_set, case_data, prompts, case_entry = _selected_inputs(
            registration
        )
        scoring_definition = _scoring_definition(registration)
        runner_registration, runner_outcome = _validated_runner_registration()

        benchmark = IdentityRef(
            _REGISTRATION_ID,
            _REGISTRATION_VERSION,
            sha256=registration_outcome.registration_sha256,
            reference=_REGISTRATION_REFERENCE,
        )
        executable = Path(sys.executable).resolve(strict=True)
        resolved_runtime, resolved_controls = resolve_model_identity("mock-base::scenario:completed")
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-arb-provider-free-integration",
            framework=IdentityRef(
                "arcgrav.framework.arb-provider-free-integration",
                "1.0.0",
            ),
            runner=IdentityRef(_RUNNER_ID, _RUNNER_VERSION),
            provider_runtime=resolved_runtime,
            controls=resolved_controls,
            environment={
                "runtime_family": "provider-free",
                "golden.environment_family": "native",
                "golden.runtime_sha256": _sha256(executable.read_bytes()),
            },
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            benchmark_root, golden_declaration = _prepare_golden(root, registration)
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    benchmark_root / "evidence",
                    benchmark_root=benchmark_root,
                )
            )
            plan = plan_run(
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                cases=(
                    PlannedCaseInput(
                        case_entry["case_id"],
                        case_entry["input"]["sha256"],
                        byte_length=case_entry["input"]["byte_length"],
                    ),
                ),
                treatments=tuple(prompt.treatment_id for prompt in prompts),
                repetitions=1,
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
            gate = admit_accepted_execution(
                generation_id="generation-arb-provider-free-integration",
                snapshot=snapshot,
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                execution_boundary=boundary,
                benchmark_root=benchmark_root,
                artifact_store=store,
                golden_declaration=golden_declaration,
                golden_case_inputs=(
                    GoldenCaseInput(case_entry["case_id"], case_data),
                ),
            )
            self.assertNotIsInstance(gate, BlockedRun)
            self.assertEqual(1, len(gate.golden_observations))
            self.assertTrue(gate.golden_observations[0])

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
                    TreatmentCaseInput(case_entry["case_id"], case_data),
                ),
                treatment_prompts=prompts,
            )
            self.assertEqual(
                runner_outcome.registration_sha256,
                treatment.runner_registration_sha256,
            )
            observations = treatment.observations()
            self.assertEqual(
                {prompt.treatment_id for prompt in prompts},
                {observation["treatment_id"] for observation in observations},
            )
            self.assertTrue(
                all(
                    observation["terminal_status"] == "completed"
                    for observation in observations
                )
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
                scoring_definitions=(scoring_definition,),
            )
            self.assertEqual("accepted", scoring.classification, scoring.diagnostics)
            scores = scoring.scores()
            self.assertEqual(len(prompts), len(scores))
            self.assertTrue(all(score["availability"] == "scored" for score in scores))
            self.assertTrue(all(score["value"] == 0.0 for score in scores))
            self.assertTrue(
                all(
                    "ARB_TREATMENT_MALFORMED" in score["diagnostics"]
                    for score in scores
                )
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
            self.assertEqual(1, len(records_by_role["golden_stdout"]))
            self.assertEqual(len(prompts), len(records_by_role["treatment_observation"]))
            self.assertEqual(len(prompts), len(records_by_role["score_artifact"]))

            boundary_record = records_by_role["execution_boundary"][0]
            boundary_ref = ReportArtifactRef.from_record(boundary_record)
            treatment_records = {}
            for record in records_by_role["treatment_observation"]:
                document = json.loads(store.read_verified(record).decode("utf-8"))
                treatment_records[document["observation_id"]] = (
                    record,
                    document,
                )
            score_records = {}
            for record in records_by_role["score_artifact"]:
                document = json.loads(store.read_verified(record).decode("utf-8"))
                (observation_id,) = document["observation_ids"]
                score_records[observation_id] = (record, document)

            metric_registration = scoring_definition.metric_registration
            metric_id = metric_registration["metric_id"]
            metric_version = metric_registration["metric_version"]
            metric_registration_id = metric_registration["registration_id"]
            metric_registration_version = metric_registration["registration_version"]
            scorer_identity = metric_registration["scorer_or_annotation"]
            metric = RegisteredReportMetric(
                registration=metric_registration,
                scorer=EvaluationIdentityRef(
                    scorer_identity["procedure_id"],
                    scorer_identity["version"],
                ),
                scoring_contracts=(
                    EvaluationIdentityRef(
                        SCORER_INVOCATION_CONTRACT_ID,
                        SCORER_INVOCATION_CONTRACT_VERSION,
                    ),
                ),
            )

            observation_matrix = []
            case_results = []
            treatment_summaries = []
            for planned in plan.observations:
                treatment_record, _ = treatment_records[planned.observation_id]
                score_record, score_document = score_records[planned.observation_id]
                treatment_ref = ReportArtifactRef.from_record(treatment_record)
                score_ref = ReportArtifactRef.from_record(score_record)
                observation_availability = AvailabilityRecord(
                    affected_kind="evidence_role",
                    affected="treatment_observation",
                    state="retained",
                    reason="Finalized ARB treatment observation retained.",
                    source_identity=treatment_ref.artifact_id,
                )
                score_availability = AvailabilityRecord(
                    affected_kind="measurement",
                    affected=metric_id,
                    state="scored",
                    reason="Registered ARB field-accuracy score retained.",
                    source_identity=score_ref.artifact_id,
                )
                observation_matrix.append(
                    ObservationMatrixEntry(
                        observation_id=planned.observation_id,
                        request_id=planned.request_id,
                        case_id=planned.case_id,
                        treatment_id=planned.treatment_id,
                        repetition_id=planned.repetition,
                        execution_boundary_fingerprint=boundary.fingerprint,
                        availability=observation_availability,
                        evidence_refs=(treatment_ref,),
                    )
                )
                case_results.append(
                    CaseResultEntry(
                        case_id=planned.case_id,
                        treatment_id=planned.treatment_id,
                        execution_boundary_fingerprint=boundary.fingerprint,
                        metric_registration_id=metric_registration_id,
                        metric_registration_version=metric_registration_version,
                        availability=score_availability,
                        value=score_document["value"],
                        evidence_refs=(score_ref,),
                    )
                )
                treatment_summaries.append(
                    TreatmentSummary(
                        treatment_id=planned.treatment_id,
                        metric_registration_id=metric_registration_id,
                        metric_registration_version=metric_registration_version,
                        availability=score_availability,
                        planned=1,
                        finalized=1,
                        completed=1,
                        scorable=1,
                        failed=0,
                        missing=0,
                        excluded=0,
                        non_scorable=0,
                        numerator=0,
                        denominator=1,
                        value=score_document["value"],
                    )
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
                comparison_track_id=registration["extensions"][_AUTHORITY_EXTENSION][
                    "comparison_track_id"
                ],
                primary_endpoint=EvaluationIdentityRef(
                    metric_id,
                    metric_version,
                ),
                metrics=(metric,),
                observation_counts=ObservationCounts(
                    planned=len(prompts),
                    finalized=len(prompts),
                    completed=len(prompts),
                    scored=len(prompts),
                    failed=0,
                    missing=0,
                    excluded=0,
                    non_scorable=0,
                ),
                observation_matrix=tuple(observation_matrix),
                case_result_matrix=tuple(case_results),
                treatment_summaries=tuple(treatment_summaries),
            )
            self.assertTrue(authority.valid)
            self.assertEqual(finalized.generation_id, authority.accepted_generation_id)

            report_configuration = selected["report_configuration"]
            report_configuration_artifact = _artifact_by_id(
                registration,
                report_configuration["artifact_id"],
            )
            report_configuration_reference = report_configuration_artifact["reference"]
            report_configuration_document = _load_json(
                report_configuration_reference
            )
            logic_set_artifact = _artifact_by_id(
                registration,
                selected["logic_set"]["artifact_id"],
            )
            report_id = "report-arb-provider-free-integration"
            registered_prerequisites = derive_registered_prerequisites(
                report_id=report_id,
                report_status="complete",
                benchmark_registration=registration,
                benchmark_registration_validation=registration_outcome,
                report_configuration_data=(
                    _REPOSITORY_ROOT / report_configuration_reference
                ).read_bytes(),
                logic_set_data=(
                    _REPOSITORY_ROOT / logic_set_artifact["reference"]
                ).read_bytes(),
                finalized=finalized,
                reporting=authority,
                artifact_store=store,
            )
            self.assertTrue(registered_prerequisites.prerequisites_satisfied)
            self.assertEqual("satisfied", registered_prerequisites.state)
            self.assertNotEqual("live-provider-execution", registered_prerequisites.evidence_class)
            self.assertEqual((), registered_prerequisites.reasons)

            # A retained resource mismatch is a factual failed prerequisite,
            # independently of synthetic/provider classification.
            for resource, reason, index in (
                ("logic", "registered_logic_or_golden_binding_mismatch", 0),
                ("configuration", "report_configuration_or_registered_identity_mismatch", 1),
            ):
                with self.subTest(resource=resource):
                    logic_bytes = (_REPOSITORY_ROOT / logic_set_artifact["reference"]).read_bytes()
                    configuration_bytes = (_REPOSITORY_ROOT / report_configuration_reference).read_bytes()
                    # Whitespace leaves the document meaning intact but breaks
                    # the exact registered resource hash.
                    if resource == "logic":
                        logic_bytes += b" "
                    else:
                        configuration_bytes += b" "
                    outcome = derive_registered_prerequisites(
                        report_id=report_id,
                        report_status="complete",
                        benchmark_registration=registration,
                        benchmark_registration_validation=registration_outcome,
                        report_configuration_data=configuration_bytes,
                        logic_set_data=logic_bytes,
                        finalized=finalized,
                        reporting=authority,
                        artifact_store=store,
                    )
                    self.assertEqual("unsatisfied", outcome.state)
                    self.assertEqual("unsatisfied", outcome.registered_logic_prerequisites[index].state)
                    self.assertEqual(reason, outcome.registered_logic_prerequisites[index].reason)
                    self.assertIn(reason, outcome.reasons)
                    self.assertNotIn("claim_eligibility", outcome.section(content_boundary="Registered evidence"))
            self.assertEqual(
                report_configuration["registration_id"],
                report_configuration_document["registration_id"],
            )
            self.assertEqual(
                report_configuration["registration_version"],
                report_configuration_document["registration_version"],
            )
            report_configuration_extension = report_configuration_document[
                "extensions"
            ]["arcgrav.authority-resolution:report-configuration"]
            arb_section_policy = {
                item["role"]: item
                for item in report_configuration_extension["section_policy"][
                    "required_arb_sections"
                ]
            }
            self.assertEqual(
                {
                    "arb_authority_resolution_interpretation",
                    "arb_registered_prerequisites",
                    "arb_dependency_effective_execution",
                    "arb_limitations_and_scope",
                },
                set(arb_section_policy),
            )
            self.assertEqual(_RUNNER_ID, boundary.to_dict()["runner"]["id"])

            arb_report_interpretation = evaluate_report_extensions(
                report_id=report_id,
                report_status="complete",
                benchmark_registration=registration,
                benchmark_registration_validation=registration_outcome,
                report_configuration_data=(_REPOSITORY_ROOT / report_configuration_reference).read_bytes(),
                logic_set_data=(_REPOSITORY_ROOT / logic_set_artifact["reference"]).read_bytes(),
                finalized=finalized,
                reporting=authority,
                artifact_store=store,
            )["arcgrav.authority-resolution:report-interpretation"]

            sections = {
                name: ReportSection(availability="available")
                for name in REQUIRED_REPORT_SECTIONS
            }
            report = build_canonical_report_model(
                authority,
                report_id=report_id,
                report_version="1.0.0",
                status="complete",
                sections=sections,
                report_manifest_id="manifest-arb-provider-free-integration",
                generated_at="2026-09-20T00:00:00Z",
                extensions={
                    "arcgrav.authority-resolution:report-interpretation": (
                        arb_report_interpretation
                    )
                },
            )
            bundle = generate_report_bundle(
                report,
                input_evidence_set_id="evidence-set-arb-provider-free-integration",
                generator=EvaluationIdentityRef(
                    "arcgrav.generator.arb-provider-free-integration",
                    "1.0.0",
                ),
                procedure_id="arcgrav.procedure.arb-provider-free-integration",
                procedure_version="1.0.0",
                command_or_procedure=(
                    "provider-free ARB accepted lifecycle report assembly"
                ),
                report_reference="generated/report.json",
                canonical_evidence_reference="generated/canonical-evidence.json",
                human_reference="generated/report.md",
                manifest_reference="generated/report-manifest.json",
            )
            report_extension = bundle.report_document["extensions"][
                "arcgrav.authority-resolution:report-interpretation"
            ]
            self.assertEqual(
                set(arb_section_policy),
                set(report_extension["sections"]),
            )
            self.assertEqual(
                "ARB field accuracy",
                report_extension["sections"][
                    "arb_authority_resolution_interpretation"
                ]["primary_endpoint"]["label"],
            )
            self.assertEqual(
                "satisfied",
                report_extension["sections"]["arb_registered_prerequisites"][
                    "state"
                ],
            )
            self.assertEqual(
                "not_applicable",
                report_extension["sections"][
                    "arb_dependency_effective_execution"
                ]["availability"],
            )
            self.assertEqual(
                tuple(report_configuration_extension["conclusion_boundaries"]),
                report_extension["sections"]["arb_limitations_and_scope"][
                    "conclusion_boundaries"
                ],
            )
            from AgMark.shared.reporting.run_report import RUN_RESULTS_EXTENSION
            self.assertEqual(
                {key: value for key, value in bundle.report_document["extensions"].items()
                 if key != RUN_RESULTS_EXTENSION},
                bundle.canonical_evidence_document["extensions"],
            )
            self.assertEqual(bundle.report_document["extensions"][RUN_RESULTS_EXTENSION],
                             bundle.canonical_evidence_document["run_results"])
            from AgMark.shared.reporting.completion import completion_record
            completion = completion_record(finalized.generation_id, status="complete", bundle=bundle)
            self.assertNotIn("claim_eligibility", completion)
            self.assertEqual(finalized.generation_id, completion["generation_id"])
            self.assertEqual(bundle.report_document["report_id"], completion["report"]["report_id"])


    @patch(
        "AgMark.shared.adapters.Codex_CLI.CodexCliRunner",
        _ProviderFreeCodexFixtureRunner,
    )
    def test_active_arb_registration_preserves_nonmock_policy_without_promoting_completion(
        self,
    ) -> None:
        registration, registration_outcome = _benchmark_registration()
        selected = registration["extensions"][_AUTHORITY_EXTENSION][
            "selected_authority"
        ]
        case_set, treatment_set, case_data, prompts, case_entry = _selected_inputs(
            registration
        )
        scoring_definition = _scoring_definition(registration)
        runner_registration, runner_outcome = _validated_runner_registration(
            load_codex_registration(),
            runner_id=_CODEX_RUNNER_ID,
            runner_version=_CODEX_RUNNER_VERSION,
        )

        benchmark = IdentityRef(
            _REGISTRATION_ID,
            _REGISTRATION_VERSION,
            sha256=registration_outcome.registration_sha256,
            reference=_REGISTRATION_REFERENCE,
        )
        executable = Path(sys.executable).resolve(strict=True)
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-arb-provider-free-integration",
            framework=IdentityRef(
                "arcgrav.framework.arb-provider-free-integration",
                "1.0.0",
            ),
            runner=IdentityRef(_CODEX_RUNNER_ID, _CODEX_RUNNER_VERSION),
            provider_runtime=ProviderRuntimeIdentity(
                runtime_id=_CODEX_RUNNER_ID,
                runtime_version="1.0.0",
                provider="OpenAI",
                access_method="cli",
                model="fixture-model",
            ),
            controls={
                "launch_mode": "native",
                "codex_binary": "runtime/codex",
                "model_id": "fixture-model",
                "approval_mode": "full_auto",
                "request_timeout_ms": 1000,
                "maximum_attempts": 1,
                "memory_policy": "disabled",
                "request_framing": "codex_cli",
                "sampling_mode": "provider_default",
                "tool_policy": "workspace_write",
            },
            environment={
                "runtime_family": "provider-free",
                "golden.environment_family": "native",
                "golden.runtime_sha256": _sha256(executable.read_bytes()),
            },
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            benchmark_root, golden_declaration = _prepare_golden(root, registration)
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    benchmark_root / "evidence",
                    benchmark_root=benchmark_root,
                )
            )
            plan = plan_run(
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                cases=(
                    PlannedCaseInput(
                        case_entry["case_id"],
                        case_entry["input"]["sha256"],
                        byte_length=case_entry["input"]["byte_length"],
                    ),
                ),
                treatments=tuple(prompt.treatment_id for prompt in prompts),
                repetitions=1,
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
            gate = admit_accepted_execution(
                generation_id="generation-arb-provider-free-integration",
                snapshot=snapshot,
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                execution_boundary=boundary,
                benchmark_root=benchmark_root,
                artifact_store=store,
                golden_declaration=golden_declaration,
                golden_case_inputs=(
                    GoldenCaseInput(case_entry["case_id"], case_data),
                ),
            )
            self.assertNotIsInstance(gate, BlockedRun)
            self.assertEqual(1, len(gate.golden_observations))
            self.assertTrue(gate.golden_observations[0])

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
                    TreatmentCaseInput(case_entry["case_id"], case_data),
                ),
                treatment_prompts=prompts,
            )
            self.assertEqual(
                runner_outcome.registration_sha256,
                treatment.runner_registration_sha256,
            )
            observations = treatment.observations()
            self.assertEqual(
                {prompt.treatment_id for prompt in prompts},
                {observation["treatment_id"] for observation in observations},
            )
            self.assertTrue(
                all(
                    observation["terminal_status"] == "completed"
                    for observation in observations
                )
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
                scoring_definitions=(scoring_definition,),
            )
            self.assertEqual("accepted", scoring.classification, scoring.diagnostics)
            scores = scoring.scores()
            self.assertEqual(len(prompts), len(scores))
            self.assertTrue(all(score["availability"] == "scored" for score in scores))
            self.assertTrue(all(score["value"] == 0.0 for score in scores))
            self.assertTrue(
                all(
                    "ARB_TREATMENT_MALFORMED" in score["diagnostics"]
                    for score in scores
                )
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
            self.assertEqual(1, len(records_by_role["golden_stdout"]))
            self.assertEqual(len(prompts), len(records_by_role["treatment_observation"]))
            self.assertEqual(len(prompts), len(records_by_role["score_artifact"]))

            boundary_record = records_by_role["execution_boundary"][0]
            boundary_ref = ReportArtifactRef.from_record(boundary_record)
            treatment_records = {}
            for record in records_by_role["treatment_observation"]:
                document = json.loads(store.read_verified(record).decode("utf-8"))
                treatment_records[document["observation_id"]] = (
                    record,
                    document,
                )
            score_records = {}
            for record in records_by_role["score_artifact"]:
                document = json.loads(store.read_verified(record).decode("utf-8"))
                (observation_id,) = document["observation_ids"]
                score_records[observation_id] = (record, document)

            metric_registration = scoring_definition.metric_registration
            metric_id = metric_registration["metric_id"]
            metric_version = metric_registration["metric_version"]
            metric_registration_id = metric_registration["registration_id"]
            metric_registration_version = metric_registration["registration_version"]
            scorer_identity = metric_registration["scorer_or_annotation"]
            metric = RegisteredReportMetric(
                registration=metric_registration,
                scorer=EvaluationIdentityRef(
                    scorer_identity["procedure_id"],
                    scorer_identity["version"],
                ),
                scoring_contracts=(
                    EvaluationIdentityRef(
                        SCORER_INVOCATION_CONTRACT_ID,
                        SCORER_INVOCATION_CONTRACT_VERSION,
                    ),
                ),
            )

            observation_matrix = []
            case_results = []
            treatment_summaries = []
            for planned in plan.observations:
                treatment_record, _ = treatment_records[planned.observation_id]
                score_record, score_document = score_records[planned.observation_id]
                treatment_ref = ReportArtifactRef.from_record(treatment_record)
                score_ref = ReportArtifactRef.from_record(score_record)
                observation_availability = AvailabilityRecord(
                    affected_kind="evidence_role",
                    affected="treatment_observation",
                    state="retained",
                    reason="Finalized ARB treatment observation retained.",
                    source_identity=treatment_ref.artifact_id,
                )
                score_availability = AvailabilityRecord(
                    affected_kind="measurement",
                    affected=metric_id,
                    state="scored",
                    reason="Registered ARB field-accuracy score retained.",
                    source_identity=score_ref.artifact_id,
                )
                observation_matrix.append(
                    ObservationMatrixEntry(
                        observation_id=planned.observation_id,
                        request_id=planned.request_id,
                        case_id=planned.case_id,
                        treatment_id=planned.treatment_id,
                        repetition_id=planned.repetition,
                        execution_boundary_fingerprint=boundary.fingerprint,
                        availability=observation_availability,
                        evidence_refs=(treatment_ref,),
                    )
                )
                case_results.append(
                    CaseResultEntry(
                        case_id=planned.case_id,
                        treatment_id=planned.treatment_id,
                        execution_boundary_fingerprint=boundary.fingerprint,
                        metric_registration_id=metric_registration_id,
                        metric_registration_version=metric_registration_version,
                        availability=score_availability,
                        value=score_document["value"],
                        evidence_refs=(score_ref,),
                    )
                )
                treatment_summaries.append(
                    TreatmentSummary(
                        treatment_id=planned.treatment_id,
                        metric_registration_id=metric_registration_id,
                        metric_registration_version=metric_registration_version,
                        availability=score_availability,
                        planned=1,
                        finalized=1,
                        completed=1,
                        scorable=1,
                        failed=0,
                        missing=0,
                        excluded=0,
                        non_scorable=0,
                        numerator=0,
                        denominator=1,
                        value=score_document["value"],
                    )
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
                comparison_track_id=registration["extensions"][_AUTHORITY_EXTENSION][
                    "comparison_track_id"
                ],
                primary_endpoint=EvaluationIdentityRef(
                    metric_id,
                    metric_version,
                ),
                metrics=(metric,),
                observation_counts=ObservationCounts(
                    planned=len(prompts),
                    finalized=len(prompts),
                    completed=len(prompts),
                    scored=len(prompts),
                    failed=0,
                    missing=0,
                    excluded=0,
                    non_scorable=0,
                ),
                observation_matrix=tuple(observation_matrix),
                case_result_matrix=tuple(case_results),
                treatment_summaries=tuple(treatment_summaries),
            )
            self.assertTrue(authority.valid)
            self.assertEqual(finalized.generation_id, authority.accepted_generation_id)

            report_configuration = selected["report_configuration"]
            report_configuration_artifact = _artifact_by_id(
                registration,
                report_configuration["artifact_id"],
            )
            report_configuration_reference = report_configuration_artifact["reference"]
            report_configuration_document = _load_json(
                report_configuration_reference
            )
            logic_set_artifact = _artifact_by_id(
                registration,
                selected["logic_set"]["artifact_id"],
            )
            report_id = "report-arb-provider-free-prerequisites-integration"
            registered_prerequisites = derive_registered_prerequisites(
                report_id=report_id,
                report_status="complete",
                benchmark_registration=registration,
                benchmark_registration_validation=registration_outcome,
                report_configuration_data=(
                    _REPOSITORY_ROOT / report_configuration_reference
                ).read_bytes(),
                logic_set_data=(
                    _REPOSITORY_ROOT / logic_set_artifact["reference"]
                ).read_bytes(),
                finalized=finalized,
                reporting=authority,
                artifact_store=store,
            )
            self.assertTrue(
                registered_prerequisites.prerequisites_satisfied,
                registered_prerequisites.reasons,
            )
            self.assertEqual(
                "satisfied",
                registered_prerequisites.state,
            )
            self.assertEqual((), registered_prerequisites.reasons)
            self.assertEqual(
                "satisfied",
                registered_prerequisites.registered_logic_prerequisites[2].state,
            )
            self.assertEqual(
                report_configuration["registration_id"],
                report_configuration_document["registration_id"],
            )
            self.assertEqual(
                report_configuration["registration_version"],
                report_configuration_document["registration_version"],
            )
            report_configuration_extension = report_configuration_document[
                "extensions"
            ]["arcgrav.authority-resolution:report-configuration"]
            arb_section_policy = {
                item["role"]: item
                for item in report_configuration_extension["section_policy"][
                    "required_arb_sections"
                ]
            }
            self.assertEqual(
                {
                    "arb_authority_resolution_interpretation",
                    "arb_registered_prerequisites",
                    "arb_dependency_effective_execution",
                    "arb_limitations_and_scope",
                },
                set(arb_section_policy),
            )
            self.assertEqual(_CODEX_RUNNER_ID, boundary.to_dict()["runner"]["id"])

            arb_report_interpretation = evaluate_report_extensions(
                report_id=report_id,
                report_status="complete",
                benchmark_registration=registration,
                benchmark_registration_validation=registration_outcome,
                report_configuration_data=(_REPOSITORY_ROOT / report_configuration_reference).read_bytes(),
                logic_set_data=(_REPOSITORY_ROOT / logic_set_artifact["reference"]).read_bytes(),
                finalized=finalized,
                reporting=authority,
                artifact_store=store,
            )["arcgrav.authority-resolution:report-interpretation"]

            sections = {
                name: ReportSection(availability="available")
                for name in REQUIRED_REPORT_SECTIONS
            }
            report = build_canonical_report_model(
                authority,
                report_id=report_id,
                report_version="1.0.0",
                status="complete",
                sections=sections,
                report_manifest_id="manifest-arb-provider-free-integration",
                generated_at="2026-09-20T00:00:00Z",
                extensions={
                    "arcgrav.authority-resolution:report-interpretation": (
                        arb_report_interpretation
                    )
                },
            )
            bundle = generate_report_bundle(
                report,
                input_evidence_set_id="evidence-set-arb-provider-free-integration",
                generator=EvaluationIdentityRef(
                    "arcgrav.generator.arb-provider-free-integration",
                    "1.0.0",
                ),
                procedure_id="arcgrav.procedure.arb-provider-free-integration",
                procedure_version="1.0.0",
                command_or_procedure=(
                    "provider-free ARB accepted lifecycle report assembly"
                ),
                report_reference="generated/report.json",
                canonical_evidence_reference="generated/canonical-evidence.json",
                human_reference="generated/report.md",
                manifest_reference="generated/report-manifest.json",
            )
            report_extension = bundle.report_document["extensions"][
                "arcgrav.authority-resolution:report-interpretation"
            ]
            self.assertEqual(
                set(arb_section_policy),
                set(report_extension["sections"]),
            )
            self.assertEqual(
                "ARB field accuracy",
                report_extension["sections"][
                    "arb_authority_resolution_interpretation"
                ]["primary_endpoint"]["label"],
            )
            self.assertEqual(
                "satisfied",
                report_extension["sections"]["arb_registered_prerequisites"][
                    "state"
                ],
            )
            self.assertEqual(
                "not_applicable",
                report_extension["sections"][
                    "arb_dependency_effective_execution"
                ]["availability"],
            )
            self.assertEqual(
                tuple(report_configuration_extension["conclusion_boundaries"]),
                report_extension["sections"]["arb_limitations_and_scope"][
                    "conclusion_boundaries"
                ],
            )
            from AgMark.shared.reporting.run_report import RUN_RESULTS_EXTENSION
            self.assertEqual(
                {key: value for key, value in bundle.report_document["extensions"].items()
                 if key != RUN_RESULTS_EXTENSION},
                bundle.canonical_evidence_document["extensions"],
            )
            self.assertEqual(bundle.report_document["extensions"][RUN_RESULTS_EXTENSION],
                             bundle.canonical_evidence_document["run_results"])
            from AgMark.shared.reporting.completion import completion_record
            completion = completion_record(finalized.generation_id, status="complete", bundle=bundle)
            self.assertNotIn("claim_eligibility", completion)
            self.assertEqual(finalized.generation_id, completion["generation_id"])
            self.assertEqual(bundle.report_document["report_id"], completion["report"]["report_id"])


    def test_active_arb_registration_rejects_substituted_golden_case_inputs(self) -> None:
        registration, registration_outcome = _benchmark_registration()
        case_set, treatment_set, case_data, prompts, case_entry = _selected_inputs(
            registration
        )

        benchmark = IdentityRef(
            _REGISTRATION_ID,
            _REGISTRATION_VERSION,
            sha256=registration_outcome.registration_sha256,
            reference=_REGISTRATION_REFERENCE,
        )
        executable = Path(sys.executable).resolve(strict=True)
        resolved_runtime, resolved_controls = resolve_model_identity("mock-base::scenario:completed")
        boundary = ExecutionBoundary.build(
            boundary_id="boundary-arb-golden-input-rejection",
            framework=IdentityRef(
                "arcgrav.framework.arb-provider-free-integration",
                "1.0.0",
            ),
            runner=IdentityRef(_RUNNER_ID, _RUNNER_VERSION),
            provider_runtime=resolved_runtime,
            controls=resolved_controls,
            environment={
                "runtime_family": "provider-free",
                "golden.environment_family": "native",
                "golden.runtime_sha256": _sha256(executable.read_bytes()),
            },
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            benchmark_root, golden_declaration = _prepare_golden(root, registration)
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    benchmark_root / "evidence",
                    benchmark_root=benchmark_root,
                )
            )
            plan = plan_run(
                benchmark=benchmark,
                case_set=case_set,
                treatment_set=treatment_set,
                cases=(
                    PlannedCaseInput(
                        case_entry["case_id"],
                        case_entry["input"]["sha256"],
                        byte_length=case_entry["input"]["byte_length"],
                    ),
                ),
                treatments=(prompts[0].treatment_id,),
                repetitions=1,
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

            rejected_inputs = (
                (
                    "caller-substituted-bytes",
                    GoldenCaseInput(case_entry["case_id"], case_data + b"\n"),
                    "golden case input bytes do not match accepted authority",
                ),
                (
                    "accepted-plan-mismatched-case",
                    GoldenCaseInput(
                        case_entry["case_id"] + "-substituted",
                        case_data,
                    ),
                    "golden case inputs must exactly match the accepted planned case set",
                ),
            )
            for label, golden_input, expected_error in rejected_inputs:
                with self.subTest(label=label):
                    with self.assertRaisesRegex(
                        AcceptedExecutionError,
                        expected_error,
                    ):
                        admit_accepted_execution(
                            generation_id=f"generation-arb-{label}",
                            snapshot=snapshot,
                            benchmark=benchmark,
                            case_set=case_set,
                            treatment_set=treatment_set,
                            execution_boundary=boundary,
                            benchmark_root=benchmark_root,
                            artifact_store=store,
                            golden_declaration=golden_declaration,
                            golden_case_inputs=(golden_input,),
                        )
                    self.assertEqual((), tuple(store.root.iterdir()))

            duplicate_input = GoldenCaseInput(case_entry["case_id"], case_data)
            with self.assertRaisesRegex(
                AcceptedExecutionError,
                "golden case-input identities must be unique",
            ):
                admit_accepted_execution(
                    generation_id="generation-arb-duplicate-case-input",
                    snapshot=snapshot,
                    benchmark=benchmark,
                    case_set=case_set,
                    treatment_set=treatment_set,
                    execution_boundary=boundary,
                    benchmark_root=benchmark_root,
                    artifact_store=store,
                    golden_declaration=golden_declaration,
                    golden_case_inputs=(duplicate_input, duplicate_input),
                )
            self.assertEqual((), tuple(store.root.iterdir()))


if __name__ == "__main__":
    unittest.main()
