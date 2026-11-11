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

from .repository_resources import _mapping, _safe_file, _sequence, _text, _verified_bytes

def _cases(
    root: Path,
    package_root: str,
    case_set: Mapping[str, object],
) -> tuple[PlannedCaseInput, ...]:
    result = []
    for raw in _sequence(case_set.get("cases"), "cases"):
        case = _mapping(raw, "case")
        case_id = _text(case.get("case_id"), "case_id")
        source = _mapping(case.get("input"), f"{case_id}.input")
        reference = _text(source.get("reference"), f"{case_id}.reference")
        digest = _text(source.get("sha256"), f"{case_id}.sha256")
        data = _verified_bytes(
            _safe_file(root, reference, package_root=package_root),
            digest,
            f"case input {case_id}",
        )
        byte_length = source.get("byte_length")
        if type(byte_length) is not int or byte_length != len(data):
            raise RepositoryCompositionError(
                f"case input {case_id!r} has invalid byte_length"
            )
        result.append(
            PlannedCaseInput(
                case_id,
                digest,
                reference=reference,
                byte_length=byte_length,
            )
        )
    if not result or len({case.case_id for case in result}) != len(result):
        raise RepositoryCompositionError("case authority is empty or ambiguous")
    return tuple(result)

def _treatments(
    root: Path,
    package_root: str,
    treatment_set: Mapping[str, object],
    *, allow_contamination: bool = False,
) -> tuple[str, ...]:
    result = []
    for raw in _sequence(treatment_set.get("treatments"), "treatments"):
        treatment = _mapping(raw, "treatment")
        treatment_id = _text(treatment.get("treatment_id"), "treatment_id")
        prompt = _mapping(treatment.get("prompt"), f"{treatment_id}.prompt")
        reference = _text(prompt.get("reference"), f"{treatment_id}.reference")
        digest = _text(prompt.get("sha256"), f"{treatment_id}.sha256")
        path = _safe_file(root, reference, package_root=package_root)
        data = path.read_bytes() if allow_contamination else _verified_bytes(path, digest, f"treatment prompt {treatment_id}")
        if type(prompt.get("byte_length")) is not int or prompt["byte_length"] < 0 or (not allow_contamination and prompt["byte_length"] != len(data)):
            raise RepositoryCompositionError(
                f"treatment {treatment_id!r} has invalid byte_length"
            )
        result.append(treatment_id)
    if not result or len(set(result)) != len(result):
        raise RepositoryCompositionError("treatment authority is empty or ambiguous")
    return tuple(result)

def _contracts(registration: Mapping[str, object]) -> tuple[IdentityRef, ...]:
    resolved = []
    for raw in _sequence(registration.get("contracts"), "contracts"):
        contract = _mapping(raw, "contract")
        contract_id = _text(contract.get("id"), "contract id")
        contract_version = _text(contract.get("version"), "contract version")
        if contract_id == RUN_LIFECYCLE_CONTRACT_ID:
            if contract_version != RUN_LIFECYCLE_CONTRACT_VERSION:
                raise RepositoryCompositionError(
                    "benchmark run-lifecycle contract is incompatible with shared planning"
                )
            continue
        resolved.append(IdentityRef(contract_id, contract_version))
    return tuple(resolved)
