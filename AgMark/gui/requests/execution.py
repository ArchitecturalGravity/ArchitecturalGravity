"""Production request resolution from validated repository authority."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path, PurePosixPath
import sys

from AgMark.gui.composition import (
    RepositoryApplicationAuthority,
    RepositoryCompositionError,
)
from AgMark.gui.shell.window import (
    SidebarControlInputSnapshot,
    SidebarInputSnapshot,
)
from AgMark.shared.application import (
    ApplicationDiscovery,
    ApplicationExecutionRequest,
    ApplicationPlanRequest,
    ApplicationReportRequest,
)
from AgMark.shared.evaluation import (
    SCORER_INVOCATION_CONTRACT_ID,
    SCORER_INVOCATION_CONTRACT_VERSION,
    IdentityRef as ReportingIdentityRef,
)
from AgMark.shared.evaluation.availability import AvailabilityRecord
from AgMark.shared.reporting import (
    REQUIRED_REPORT_SECTIONS,
    CaseResultEntry,
    GeneratedReportBundle,
    ObservationCounts,
    ObservationMatrixEntry,
    RegisteredReportMetric,
    ReportArtifactRef,
    ReportSection,
    TreatmentSummary,
)
from AgMark.shared.runtime.artifacts import (
    FilesystemArtifactStore,
    PublicationDestination,
    sha256_bytes,
)
from AgMark.shared.runtime.golden import (
    GoldenArtifactRequirement,
    GoldenCaseInput,
    GoldenDeclaration,
    TransientEnvironmentBinding,
)
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    AcceptedRun,
    AcceptedRunSnapshot,
    PlannedCaseInput,
    RegisteredScoringDefinition,
    RUN_LIFECYCLE_CONTRACT_ID,
    RUN_LIFECYCLE_CONTRACT_VERSION,
    TreatmentCaseInput,
    TreatmentPrompt,
)
from AgMark.shared.validation import (
    ArtifactSource,
    ContractRequirement,
    validate_registration_binding_outcome,
)


_SUPPORTED_CONTROLS = "arcgrav.adapters:supported_controls"
_FIXED_CONTROLS = "arcgrav.adapters:fixed_controls"
_ACCESS_METHODS = "arcgrav.adapters:access_methods"
_SECRET_HANDLING = "arcgrav.adapters:secret_handling"
_TRANSIENT_INPUTS = "transient_inputs"
_PLANNING_PROBE = "arcgrav.adapters:planning_probe"
_CREDENTIAL_SOURCE_CONTROL = "credential_source"
_TRANSIENT_CREDENTIAL_SOURCE = "credential_source"
_TRANSIENT_CREDENTIAL_MATERIAL = "credential_material"
_MODEL_CONTROLS = frozenset({"model", "model_id"})
_LAUNCH_ENVIRONMENT = "arcgrav.adapters:launch_environment"
_MISSING = object()
_REPORT_GENERATION_CONTRACT = ("arcgrav.shared.report-generation", "3.0.0")
_RUN_COMPLETION_CONTRACT = ("arcgrav.shared.run-completion", "2.0.0")
_REPORT_GENERATOR = ReportingIdentityRef(
    "arcgrav.generator.shared-report-bundle",
    "1.0.0",
)
_REPORT_PROCEDURE_ID = "arcgrav.procedure.shared-report-bundle"
_REPORT_PROCEDURE_VERSION = "1.0.0"
_REPORT_SELECTION_EXTENSION = "arcgrav.gui:registered-report-selection"

from .repository_resources import _artifact, _json_artifact, _mapping, _package_directory, _safe_file, _sequence, _text, _verified_bytes

def _execution_case_inputs(
    root: Path,
    package_root: str,
    case_set: Mapping[str, object],
) -> tuple[tuple[TreatmentCaseInput, ...], tuple[GoldenCaseInput, ...]]:
    treatment_inputs: list[TreatmentCaseInput] = []
    golden_inputs: list[GoldenCaseInput] = []
    seen: set[str] = set()
    for raw_case in _sequence(case_set.get("cases"), "case set cases"):
        case = _mapping(raw_case, "case")
        case_id = _text(case.get("case_id"), "case id")
        if case_id in seen:
            raise RepositoryCompositionError("case identities must be unique")
        seen.add(case_id)
        input_value = _mapping(case.get("input"), f"case {case_id} input")
        reference = _text(input_value.get("reference"), f"case {case_id} input reference")
        expected_sha256 = _text(
            input_value.get("sha256"),
            f"case {case_id} input sha256",
        )
        data = _verified_bytes(
            _safe_file(root, reference, package_root=package_root),
            expected_sha256,
            f"case {case_id} input",
        )
        expected_length = input_value.get("byte_length")
        if (
            not isinstance(expected_length, int)
            or isinstance(expected_length, bool)
            or expected_length < 0
            or len(data) != expected_length
        ):
            raise RepositoryCompositionError(
                f"case {case_id} input byte length does not match registration"
            )
        treatment_inputs.append(TreatmentCaseInput(case_id, data))
        golden_inputs.append(GoldenCaseInput(case_id, data))
    if not treatment_inputs:
        raise RepositoryCompositionError("registered case set must contain cases")
    return tuple(treatment_inputs), tuple(golden_inputs)

def _execution_treatment_prompts(
    root: Path,
    package_root: str,
    treatment_set: Mapping[str, object],
) -> tuple[TreatmentPrompt, ...]:
    prompts: list[TreatmentPrompt] = []
    seen: set[str] = set()
    for raw_treatment in _sequence(
        treatment_set.get("treatments"),
        "treatment set treatments",
    ):
        treatment = _mapping(raw_treatment, "treatment")
        treatment_id = _text(treatment.get("treatment_id"), "treatment id")
        if treatment_id in seen:
            raise RepositoryCompositionError("treatment identities must be unique")
        seen.add(treatment_id)
        prompt = _mapping(treatment.get("prompt"), f"treatment {treatment_id} prompt")
        reference = _text(
            prompt.get("reference"),
            f"treatment {treatment_id} prompt reference",
        )
        expected_sha256 = _text(
            prompt.get("sha256"),
            f"treatment {treatment_id} prompt sha256",
        )
        data = _verified_bytes(
            _safe_file(root, reference, package_root=package_root),
            expected_sha256,
            f"treatment {treatment_id} prompt",
        )
        expected_length = prompt.get("byte_length")
        if (
            not isinstance(expected_length, int)
            or isinstance(expected_length, bool)
            or expected_length < 0
            or len(data) != expected_length
        ):
            raise RepositoryCompositionError(
                f"treatment {treatment_id} prompt byte length does not match registration"
            )
        prompts.append(TreatmentPrompt(treatment_id, data))
    if not prompts:
        raise RepositoryCompositionError("registered treatment set must contain treatments")
    return tuple(prompts)

def _scoring_definition(
    root: Path,
    package_root: str,
    registration: Mapping[str, object],
    selected: Mapping[str, object],
) -> RegisteredScoringDefinition:
    metric_selected = _mapping(selected.get("primary_metric"), "selected primary metric")
    scorer_selected = _mapping(selected.get("scorer"), "selected scorer")

    metric_artifact_id = _text(
        metric_selected.get("artifact_id"),
        "selected primary metric artifact_id",
    )
    _, metric_registration = _json_artifact(
        root,
        registration,
        metric_artifact_id,
        "selected primary metric registration",
    )
    for field_name in (
        "registration_id",
        "registration_version",
        "metric_id",
        "metric_version",
    ):
        expected = _text(
            metric_selected.get(field_name),
            f"selected primary metric {field_name}",
        )
        if metric_registration.get(field_name) != expected:
            raise RepositoryCompositionError(
                f"selected primary metric {field_name} does not match registered bytes"
            )
    if metric_selected.get("is_primary_endpoint") is True and (
        metric_registration.get("is_primary_endpoint") is not True
    ):
        raise RepositoryCompositionError(
            "selected primary metric endpoint authority does not match registered bytes"
        )

    scorer_registration_artifact_id = _text(
        scorer_selected.get("registration_artifact_id"),
        "selected scorer registration artifact_id",
    )
    _, scorer_registration = _json_artifact(
        root,
        registration,
        scorer_registration_artifact_id,
        "selected scorer registration",
    )
    scorer_id = _text(scorer_selected.get("registration_id"), "selected scorer id")
    scorer_version = _text(
        scorer_selected.get("registration_version"),
        "selected scorer version",
    )
    if (
        scorer_registration.get("registration_id") != scorer_id
        or scorer_registration.get("registration_version") != scorer_version
        or scorer_registration.get("registration_kind") != "scorer"
        or scorer_registration.get("status") != "active"
    ):
        raise RepositoryCompositionError(
            "selected scorer registration identity or status does not match registered bytes"
        )

    implementation_artifact_id = _text(
        scorer_selected.get("implementation_artifact_id"),
        "selected scorer implementation artifact_id",
    )
    benchmark_implementation = _artifact(registration, implementation_artifact_id)
    scorer_implementation = _artifact(scorer_registration, implementation_artifact_id)
    for field_name in ("sha256", "reference"):
        if scorer_implementation.get(field_name) != benchmark_implementation.get(field_name):
            raise RepositoryCompositionError(
                "selected scorer implementation authority differs between benchmark and scorer registrations"
            )
    implementation_reference = _text(
        benchmark_implementation.get("reference"),
        "selected scorer implementation reference",
    )
    implementation_sha256 = _text(
        benchmark_implementation.get("sha256"),
        "selected scorer implementation sha256",
    )
    _verified_bytes(
        _safe_file(root, implementation_reference),
        implementation_sha256,
        "selected scorer implementation",
    )

    raw_artifacts = _sequence(
        scorer_registration.get("implementation_artifacts"),
        "scorer implementation artifacts",
    )
    sources: list[ArtifactSource] = []
    for raw_artifact in raw_artifacts:
        artifact = _mapping(raw_artifact, "scorer implementation artifact")
        artifact_id = _text(artifact.get("artifact_id"), "scorer artifact_id")
        reference = _text(artifact.get("reference"), "scorer artifact reference")
        path = _safe_file(root, reference)
        sources.append(
            ArtifactSource(
                artifact_id=artifact_id,
                reference=reference,
                data=path.read_bytes(),
            )
        )
    outcome = validate_registration_binding_outcome(
        scorer_registration,
        expected_registration_id=scorer_id,
        expected_registration_version=scorer_version,
        contract_requirements=(
            ContractRequirement(
                SCORER_INVOCATION_CONTRACT_ID,
                (SCORER_INVOCATION_CONTRACT_VERSION,),
            ),
        ),
        artifact_sources=tuple(sources),
        allowed_artifact_roots=(package_root,),
        source_id=f"gui-production-scorer:{scorer_id}@{scorer_version}",
    )
    if not outcome.valid:
        codes = ",".join(sorted({issue.code for issue in outcome.issues}))
        raise RepositoryCompositionError(
            "selected scorer registration failed exact validation"
            + (f": {codes}" if codes else "")
        )
    return RegisteredScoringDefinition(
        metric_registration=metric_registration,
        scorer_registration=scorer_registration,
        scorer_registration_outcome=outcome,
    )

def _golden_declaration(
    root: Path,
    package_root: str,
    registration: Mapping[str, object],
    selected: Mapping[str, object],
    *,
    environment_family: str,
    runtime_executable: Path,
) -> tuple[GoldenDeclaration | None, tuple[TransientEnvironmentBinding, ...]]:
    raw_authority = selected.get("golden_authority")
    if raw_authority is None:
        return None, ()
    authority = _mapping(raw_authority, "selected golden authority")
    if authority.get("caller_supplied_golden_allowed") is True:
        raise RepositoryCompositionError(
            "caller-supplied golden authority is not supported by production resolution"
        )
    artifact_id = _text(
        authority.get("artifact_id"),
        "selected golden authority artifact_id",
    )
    artifact = _artifact(registration, artifact_id)
    reference = _text(artifact.get("reference"), "selected golden artifact reference")
    expected_sha256 = _text(
        artifact.get("sha256"),
        "selected golden artifact sha256",
    )
    path = _safe_file(root, reference)
    _verified_bytes(path, expected_sha256, "selected golden artifact")
    benchmark_root = _package_directory(root, package_root)
    try:
        path.relative_to(benchmark_root)
    except ValueError as exc:
        raise RepositoryCompositionError(
            "selected golden artifact lies outside benchmark package authority"
        ) from exc

    artifact_ids = tuple(
        _text(value, "golden implementation artifact_id")
        for value in _sequence(
            authority.get("implementation_artifact_ids", (artifact_id,)),
            "golden implementation_artifact_ids",
        )
    )
    if artifact_id not in artifact_ids or len(set(artifact_ids)) != len(artifact_ids):
        raise RepositoryCompositionError(
            "golden implementation artifacts must uniquely include the selected source"
        )
    requirements: list[GoldenArtifactRequirement] = []
    for dependency_id in artifact_ids:
        dependency = _artifact(registration, dependency_id)
        dependency_reference = _text(
            dependency.get("reference"), "golden dependency reference"
        )
        dependency_hash = _text(dependency.get("sha256"), "golden dependency sha256")
        dependency_path = _safe_file(root, dependency_reference)
        _verified_bytes(dependency_path, dependency_hash, "golden dependency")
        try:
            dependency_relative = dependency_path.relative_to(benchmark_root).as_posix()
        except ValueError as exc:
            raise RepositoryCompositionError(
                "golden dependency lies outside benchmark package authority"
            ) from exc
        requirements.append(GoldenArtifactRequirement(
            artifact_id=dependency_id,
            relative_path=dependency_relative,
            sha256=dependency_hash,
        ))
    input_transport = _text(authority.get("input_transport", "stdin"), "golden input_transport")
    input_artifact_id = authority.get("input_artifact_id")
    if input_transport == "registered_file":
        input_artifact_id = _text(input_artifact_id, "golden input_artifact_id")
        if input_artifact_id not in artifact_ids:
            raise RepositoryCompositionError(
                "registered input file must be a declared golden dependency"
            )
    elif input_artifact_id is not None:
        raise RepositoryCompositionError(
            "golden input_artifact_id requires registered_file transport"
        )

    bindings: list[TransientEnvironmentBinding] = []
    raw_bindings = authority.get("transient_environment", ())
    for raw_binding in _sequence(raw_bindings, "golden transient_environment"):
        binding = _mapping(raw_binding, "golden transient environment binding")
        bindings.append(
            TransientEnvironmentBinding(
                source_id=_text(binding.get("source_id"), "golden transient source_id"),
                environment_variable=_text(
                    binding.get("environment_variable"),
                    "golden transient environment variable",
                ),
            )
        )

    executable = runtime_executable.resolve(strict=True)
    if not executable.is_file():
        raise RepositoryCompositionError(
            "configured golden runtime executable must be a file"
        )
    runtime_sha256 = "sha256:" + sha256(executable.read_bytes()).hexdigest()
    version = _text(
        registration.get("registration_version"),
        "benchmark registration version",
    )
    declaration = GoldenDeclaration(
        golden_implementation=IdentityRef(
            artifact_id,
            version,
            sha256=expected_sha256,
            reference=reference,
        ),
        runtime_identity=IdentityRef(
            "arcgrav.runtime.python",
            "1.0.0",
            sha256=runtime_sha256,
            reference="runtime/python",
        ),
        runtime_executable=str(executable),
        artifacts=tuple(requirements),
        entry_artifact_id=artifact_id,
        environment_family=environment_family,
        input_transport=input_transport,
        input_artifact_id=input_artifact_id,
        require_nonempty_output=(
            authority.get(
                "requires_successful_nonempty_retained_stdout_before_treatments"
            )
            is True
        ),
        transient_environment=tuple(bindings),
    )
    return declaration, tuple(bindings)

def _golden_transient_values(
    credential: str,
    bindings: Sequence[TransientEnvironmentBinding],
    *,
    credential_claimed_by_runner: bool = False,
) -> Mapping[str, str] | None:
    if not isinstance(credential, str):
        raise TypeError("credential must be a string")
    declared = tuple(bindings)
    if not declared:
        if credential and not credential_claimed_by_runner:
            raise RepositoryCompositionError(
                "credential material was supplied without a registered transient binding"
            )
        return None
    if len(declared) != 1:
        raise RepositoryCompositionError(
            "one GUI credential value cannot satisfy multiple registered golden transient sources"
        )
    if not credential:
        raise RepositoryCompositionError(
            "registered golden transient invocation material is required before execution"
        )
    return {declared[0].source_id: credential}
