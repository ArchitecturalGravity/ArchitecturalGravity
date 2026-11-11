"""Developer-only provider-free shared-framework lifecycle harness.

The test harness traverses the implemented shared lifecycle with synthetic,
registered diagnostic inputs and the actual registered mock-model process. The
synthetic inputs exercise the lifecycle rather than measuring a live model.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable

from AgMark.shared.adapters.Mock_Model import load_registration
from AgMark.shared.adapters.Mock_Model.catalog import probe_planning_identity
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


_SELF_TESTING_ROOT = Path(__file__).resolve().parent
_SOFTWARE_TESTING_ROOT = _SELF_TESTING_ROOT.parent
_SHARED_ROOT = _SOFTWARE_TESTING_ROOT.parent
_REPOSITORY_ROOT = _SHARED_ROOT.parents[1]
_DIAGNOSTIC_REFERENCE = "AgMark/shared/software_testing/self_testing/dry_run.py"
_DIAGNOSTIC_SCORER_REFERENCE = "AgMark/shared/software_testing/self_testing/diagnostic_scorer.py"

_REQUIRED_SPECIFICATIONS = (
    # Published contracts remain the behavioral authority exercised by this
    # developer harness; test fixtures do not define production contracts.
    "contracts/CONTRACT_CATALOG.md",
    "contracts/RUN_LIFECYCLE.md",
    "contracts/RUNNER_INVOCATION.md",
    "contracts/LAUNCH_ENVIRONMENT.md",
    "contracts/SCORER_INVOCATION.md",
    "contracts/GOLDEN_EXECUTION.md",
    "contracts/EVIDENCE_VALIDATION.md",
    "contracts/EFFECTIVE_EXECUTION.md",
    "contracts/REPORT_GENERATION.md",
    "contracts/RUN_COMPLETION.md",
    "contracts/FAILURE_TAXONOMY.md",
    "contracts/TRANSIENT_INVOCATION.md",
    "contracts/TREATMENT_MEASUREMENTS.md",
    "contracts/PROVIDER_REQUEST_CACHE_VALIDATION.md",
)

_BENCHMARK_ID = "arcgrav.benchmark.shared-self-test-diagnostic"
_BENCHMARK_VERSION = "1.0.0"
_BENCHMARK_REGISTRATION_SOURCE_ID = "shared-self-test-benchmark-registration"
_RUNNER_ID = "arcgrav.mock-model.runner"
_RUNNER_VERSION = "1.0.0"
_RUNNER_REGISTRATION_SOURCE_ID = "shared-self-test-runner-registration"
_SCORER_ID = "arcgrav.scorer.shared-self-test-diagnostic"
_SCORER_VERSION = "1.0.0"
_METRIC_ID = "arcgrav.metric.shared-self-test-diagnostic"
_METRIC_VERSION = "1.0.0"
_METRIC_REGISTRATION_ID = "arcgrav.metric-registration.shared-self-test-diagnostic"
_METRIC_REGISTRATION_VERSION = "1.0.0"
_COMPARISON_TRACK = "shared-self-test-diagnostic"


@dataclass(frozen=True)
class DiagnosticObservation:
    """One deterministic provider-free diagnostic check."""

    check_id: str
    status: str
    detail: str


@dataclass(frozen=True)
class VerificationResult:
    """Normalized verification state for a diagnostic dry run."""

    status: str
    issues: tuple[str, ...]


@dataclass(frozen=True)
class DeterministicDryRunResult:
    """Normalized, non-authoritative result from the shared lifecycle diagnostic."""

    observations: tuple[DiagnosticObservation, ...]
    verification_result: VerificationResult
    repetition_count: int
    diagnostic: bool = True
    authoritative: bool = False
    scope: str = "shared-lifecycle-registered-mock-model"
    runner_path_parity: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _iter_production_python() -> Iterable[Path]:
    def fail(error: OSError) -> None:
        raise error

    for directory, children, names in os.walk(_SHARED_ROOT, onerror=fail):
        children[:] = sorted(
            child for child in children
            if child not in {
                "software_testing", "__pycache__", ".git", ".venv",
                "venv", ".linux-pyside6",
            }
            and not (Path(directory) / child / "pyvenv.cfg").is_file()
        )
        for name in sorted(names):
            if name.endswith(".py"):
                yield Path(directory) / name


def _imports_software_testing(path: Path) -> tuple[str, ...]:
    """Return forbidden imports of the centralized developer-test estate."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return (f"could not inspect {path.relative_to(_SHARED_ROOT)}: {exc}",)

    violations: list[str] = []
    forbidden = "AgMark.shared.software_testing"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == forbidden or alias.name.startswith(forbidden + "."):
                    violations.append(
                        f"{path.relative_to(_SHARED_ROOT)} imports {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == forbidden or module.startswith(forbidden + "."):
                violations.append(
                    f"{path.relative_to(_SHARED_ROOT)} imports from {module}"
                )
            elif node.level and (
                module == "software_testing"
                or module.startswith("software_testing.")
            ):
                violations.append(
                    f"{path.relative_to(_SHARED_ROOT)} uses a relative software_testing import"
                )

    return tuple(violations)


def _check_required_specifications() -> DiagnosticObservation:
    missing = [
        relative
        for relative in _REQUIRED_SPECIFICATIONS
        if not (_SHARED_ROOT / relative).is_file()
    ]
    if missing:
        return DiagnosticObservation(
            check_id="required-specifications",
            status="failed",
            detail="missing: " + ", ".join(missing),
        )
    return DiagnosticObservation(
        check_id="required-specifications",
        status="passed",
        detail=f"{len(_REQUIRED_SPECIFICATIONS)} required published contract files are present",
    )


def _check_testing_ownership() -> DiagnosticObservation:
    violations: list[str] = []
    for path in _iter_production_python():
        violations.extend(_imports_software_testing(path))

    if violations:
        return DiagnosticObservation(
            check_id="software-testing-dependency-boundary",
            status="failed",
            detail="; ".join(violations),
        )
    return DiagnosticObservation(
        check_id="software-testing-dependency-boundary",
        status="passed",
        detail="shared production Python does not import the centralized software-testing estate",
    )


def _validated_diagnostic_benchmark() -> IdentityRef:
    implementation_bytes = Path(__file__).read_bytes()
    source = ArtifactSource(
        artifact_id="shared-self-test-diagnostic-source",
        reference=_DIAGNOSTIC_REFERENCE,
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
        allowed_artifact_roots=("AgMark/shared/software_testing/self_testing",),
        source_id=_BENCHMARK_REGISTRATION_SOURCE_ID,
    )
    if not outcome.valid:
        raise RuntimeError(
            "diagnostic benchmark registration invalid: "
            + ",".join(issue.code for issue in outcome.issues)
        )
    issues = validate_benchmark_discovery(
        (
            BenchmarkDiscoveryCandidate(
                package_root="AgMark/Shared_Self_Test_Diagnostic",
                registration_source_id=_BENCHMARK_REGISTRATION_SOURCE_ID,
                registration=registration,
                registration_validation=outcome,
            ),
        ),
        source_id="shared-self-test-discovery",
    )
    if issues:
        raise RuntimeError(
            "diagnostic benchmark discovery invalid: "
            + ",".join(issue.code for issue in issues)
        )
    return IdentityRef(
        _BENCHMARK_ID,
        _BENCHMARK_VERSION,
        sha256=_sha256(implementation_bytes),
        reference=_DIAGNOSTIC_REFERENCE,
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
        raise RuntimeError(
            "registered mock runner registration invalid: "
            + ",".join(issue.code for issue in outcome.issues)
        )
    return registration, outcome


def _metric_registration() -> dict[str, object]:
    return {
        "schema_id": "arcgrav.shared.schema.metric-registration",
        "schema_version": "1.0.0",
        "extensions": {},
        "registration_id": _METRIC_REGISTRATION_ID,
        "registration_version": _METRIC_REGISTRATION_VERSION,
        "metric_id": _METRIC_ID,
        "metric_version": _METRIC_VERSION,
        "name": "Shared self-test lifecycle health",
        "description": "Provider-free health signal for the shared production diagnostic.",
        "classification": "correctness",
        "comparison_track_id": _COMPARISON_TRACK,
        "is_primary_endpoint": True,
        "formula_or_algorithm": "Retain one only when the diagnostic observation completes.",
        "required_inputs": ["treatment_observation"],
        "unit": "health",
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
    implementation_bytes = (_REPOSITORY_ROOT / _DIAGNOSTIC_SCORER_REFERENCE).read_bytes()
    source = ArtifactSource(
        artifact_id="shared-self-test-diagnostic-scorer",
        reference=_DIAGNOSTIC_SCORER_REFERENCE,
        data=implementation_bytes,
    )
    registration = {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "extensions": {
            SCORER_ENTRY_POINT_EXTENSION: (
                "AgMark.shared.software_testing.self_testing.diagnostic_scorer:diagnostic_health_scorer"
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
        allowed_artifact_roots=("AgMark/shared/software_testing/self_testing",),
        source_id="shared-self-test-scorer-registration",
    )
    if not outcome.valid:
        raise RuntimeError(
            "diagnostic scorer registration invalid: "
            + ",".join(issue.code for issue in outcome.issues)
        )
    return RegisteredScoringDefinition(
        metric_registration=_metric_registration(),
        scorer_registration=registration,
        scorer_registration_outcome=outcome,
    )


def _exercise_provider_free_lifecycle() -> str:
    benchmark = _validated_diagnostic_benchmark()
    runner_registration, _ = _validated_runner_registration()
    scoring_definition = _scoring_definition()
    case_set = IdentityRef(
        "arcgrav.case-set.shared-self-test-diagnostic",
        "1.0.0",
        sha256=_sha256(b"shared-self-test-case-set"),
    )
    treatment_set = IdentityRef(
        "arcgrav.treatment-set.shared-self-test-diagnostic",
        "1.0.0",
        sha256=_sha256(b"shared-self-test-treatment-set"),
    )
    selected_controls = {"model_id": "mock-base::scenario:completed", "request_timeout_ms": 120000, "maximum_attempts": 1}
    identity = probe_planning_identity(runner_registration, control_values=selected_controls)
    if identity.get("status") != "ready":
        raise RuntimeError("registered mock runtime unresolved: " + str(identity.get("error_code")))
    resolved_runtime = ProviderRuntimeIdentity(**identity["provider_runtime"])
    resolved_controls = dict(identity["resolved_controls"])
    resolved_controls.update({item["name"]: item["value"] for item in runner_registration["extensions"]["arcgrav.adapters:fixed_controls"]})
    boundary = ExecutionBoundary.build(
        boundary_id="boundary-shared-self-test-diagnostic",
        framework=IdentityRef("arcgrav.framework.shared-self-test", "1.0.0"),
        runner=IdentityRef(_RUNNER_ID, _RUNNER_VERSION),
        provider_runtime=resolved_runtime,
        controls=resolved_controls,
        environment={"runtime_family": "provider-free"},
    )
    case_data = b"shared-self-test-case"

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
                    "case-shared-self-test",
                    _sha256(case_data),
                    byte_length=len(case_data),
                ),
            ),
            treatments=("treatment-shared-self-test",),
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
        snapshot = accept_run_plan(plan=plan, execution_boundary=boundary)
        gate = admit_accepted_execution(
            generation_id="generation-shared-self-test-diagnostic",
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
            case_inputs=(TreatmentCaseInput("case-shared-self-test", case_data),),
            treatment_prompts=(
                TreatmentPrompt(
                    "treatment-shared-self-test",
                    b"provider-free shared self-test prompt",
                ),
            ),
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
        finalized = finalize_scored_run(
            gate=gate,
            treatment_result=treatment,
            scoring_result=scoring,
            artifact_store=store,
        )
        if not isinstance(finalized, AcceptedRun):
            raise RuntimeError("provider-free diagnostic did not finalize as AcceptedRun")

        records_by_role: dict[str, list[object]] = {}
        for record in finalized.artifact_index.artifacts:
            records_by_role.setdefault(record.role, []).append(record)
        for required_role in (
            "execution_boundary",
            "metric_registration",
            "treatment_observation",
            "score_artifact",
        ):
            if len(records_by_role.get(required_role, ())) != 1:
                raise RuntimeError(
                    f"provider-free diagnostic retained invalid {required_role} cardinality"
                )

        boundary_record = records_by_role["execution_boundary"][0]
        treatment_record = records_by_role["treatment_observation"][0]
        score_record = records_by_role["score_artifact"][0]
        boundary_ref = ReportArtifactRef.from_record(boundary_record)
        treatment_ref = ReportArtifactRef.from_record(treatment_record)
        score_ref = ReportArtifactRef.from_record(score_record)
        score_document = json.loads(store.read_verified(score_record).decode("utf-8"))

        observation_availability = AvailabilityRecord(
            affected_kind="evidence_role",
            affected="treatment_observation",
            state="retained",
            reason="Finalized diagnostic treatment observation retained.",
            source_identity=treatment_ref.artifact_id,
        )
        score_availability = AvailabilityRecord(
            affected_kind="measurement",
            affected=_METRIC_ID,
            state="scored",
            reason="Finalized diagnostic health score retained.",
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
            treatment_set=EvaluationIdentityRef(treatment_set.id, treatment_set.version),
            comparison_track_id=_COMPARISON_TRACK,
            primary_endpoint=EvaluationIdentityRef(_METRIC_ID, _METRIC_VERSION),
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
                    numerator=1,
                    denominator=1,
                    value=score_document["value"],
                ),
            ),
        )
        if not authority.valid:
            raise RuntimeError(
                "finalized diagnostic run was not admitted for reporting: "
                + ",".join(issue.code for issue in authority.issues)
            )

        sections = {
            name: ReportSection(availability="available")
            for name in REQUIRED_REPORT_SECTIONS
        }
        report = build_canonical_report_model(
            authority,
            report_id="report-shared-self-test-diagnostic",
            report_version="1.0.0",
            status="dry_run",
            sections=sections,
            report_manifest_id="manifest-shared-self-test-diagnostic",
            generated_at="2000-01-01T00:00:00Z",
        )
        bundle = generate_report_bundle(
            report,
            input_evidence_set_id="evidence-set-shared-self-test-diagnostic",
            generator=EvaluationIdentityRef(
                "arcgrav.generator.shared-self-test-diagnostic",
                "1.0.0",
            ),
            procedure_id="arcgrav.procedure.shared-self-test-diagnostic",
            procedure_version="1.0.0",
            command_or_procedure="provider-free shared production lifecycle diagnostic",
            report_reference="generated/report.json",
            canonical_evidence_reference="generated/canonical-evidence.json",
            human_reference="generated/report.md",
            manifest_reference="generated/report-manifest.json",
        )
        if not all(component.data for component in bundle.components):
            raise RuntimeError("diagnostic report contains an empty component")

    return (
        "accepted_generation=generation-shared-self-test-diagnostic; "
        "report_status=dry_run; report_components=present"
    )


def _check_provider_free_lifecycle() -> DiagnosticObservation:
    try:
        detail = _exercise_provider_free_lifecycle()
    except Exception as exc:
        return DiagnosticObservation(
            check_id="provider-free-lifecycle",
            status="failed",
            detail=f"{type(exc).__name__}: {exc}",
        )
    return DiagnosticObservation(
        check_id="provider-free-lifecycle",
        status="passed",
        detail=detail,
    )


def run_deterministic_dry_run(
    *,
    repetition_count: int = 1,
) -> DeterministicDryRunResult:
    """Run the deterministic, provider-free shared production diagnostic."""

    if repetition_count < 1:
        raise ValueError("repetition_count must be at least 1")

    observations = (
        _check_required_specifications(),
        _check_testing_ownership(),
        _check_provider_free_lifecycle(),
    )
    issues = tuple(
        f"{observation.check_id}: {observation.detail}"
        for observation in observations
        if observation.status != "passed"
    )
    verification = VerificationResult(
        status="verified" if not issues else "failed",
        issues=issues,
    )
    return DeterministicDryRunResult(
        observations=observations,
        verification_result=verification,
        repetition_count=repetition_count,
    )


def main() -> int:
    result = run_deterministic_dry_run()
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.verification_result.status == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DeterministicDryRunResult",
    "DiagnosticObservation",
    "VerificationResult",
    "run_deterministic_dry_run",
]
