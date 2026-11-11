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

def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RepositoryCompositionError(f"{name} must be an object")
    return value

def _sequence(value: object, name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RepositoryCompositionError(f"{name} must be an array")
    return value

def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RepositoryCompositionError(f"{name} must be non-empty text")
    return value

def _safe_file(root: Path, reference: str, *, package_root: str | None = None) -> Path:
    base = root
    if package_root is not None:
        package = PurePosixPath(package_root)
        if package.is_absolute() or any(part in {".", ".."} for part in package.parts):
            raise RepositoryCompositionError("benchmark package root is unsafe")
        base = root.joinpath(*package.parts).resolve(strict=True)
    relative = PurePosixPath(reference)
    if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
        raise RepositoryCompositionError(f"registered reference is unsafe: {reference!r}")
    try:
        path = base.joinpath(*relative.parts).resolve(strict=True)
        path.relative_to(base)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RepositoryCompositionError(
            f"registered reference is inaccessible: {reference!r}"
        ) from exc
    if not path.is_file():
        raise RepositoryCompositionError(
            f"registered reference is not a file: {reference!r}"
        )
    return path

def _verified_bytes(path: Path, expected: str, name: str) -> bytes:
    data = path.read_bytes()
    if "sha256:" + sha256(data).hexdigest() != expected:
        raise RepositoryCompositionError(f"{name} drifted from registered authority")
    return data

def _artifact(registration: Mapping[str, object], artifact_id: str) -> Mapping[str, object]:
    matches = [
        item
        for item in _sequence(
            registration.get("implementation_artifacts"),
            "implementation_artifacts",
        )
        if isinstance(item, Mapping) and item.get("artifact_id") == artifact_id
    ]
    if len(matches) != 1:
        raise RepositoryCompositionError(
            f"artifact {artifact_id!r} does not resolve uniquely"
        )
    return matches[0]

def _selected_authority(registration: Mapping[str, object]) -> Mapping[str, object]:
    matches = []
    for value in _mapping(registration.get("extensions"), "extensions").values():
        if (
            isinstance(value, Mapping)
            and value.get("benchmark_id") == registration.get("registration_id")
            and value.get("benchmark_version")
            == registration.get("registration_version")
            and isinstance(value.get("selected_authority"), Mapping)
        ):
            matches.append(value["selected_authority"])
    if len(matches) != 1:
        raise RepositoryCompositionError(
            "benchmark must expose exactly one selected authority extension"
        )
    return _mapping(matches[0], "selected_authority")

def _label(registration: Mapping[str, object]) -> str:
    return (
        f"{_text(registration.get('registration_id'), 'registration_id')}@"
        f"{_text(registration.get('registration_version'), 'registration_version')}"
    )

def _selected_candidate(authority: RepositoryApplicationAuthority, label: str):
    matches = [
        candidate
        for candidate in authority.benchmark_candidates
        if _label(candidate.registration) == label
    ]
    if len(matches) != 1:
        raise RepositoryCompositionError(
            "selected benchmark does not resolve to one repository authority"
        )
    candidate = matches[0]
    outcome = candidate.registration_validation
    if not outcome.valid or not outcome.matches(
        candidate.registration,
        source_id=candidate.registration_source_id,
    ):
        raise RepositoryCompositionError("selected benchmark authority drifted")
    return candidate

def _selected_runner(authority: RepositoryApplicationAuthority, label: str):
    matches = [
        source
        for source in authority.runner_sources
        if _label(source.registration) == label
    ]
    if len(matches) != 1:
        raise RepositoryCompositionError(
            "selected runner does not resolve to one repository authority"
        )
    source = matches[0]
    outcome = source.registration_validation
    if not outcome.valid or not outcome.matches(
        source.registration,
        source_id=source.registration_source_id,
    ):
        raise RepositoryCompositionError("selected runner authority drifted")
    return source

def _resource(
    root: Path,
    registration: Mapping[str, object],
    selected: Mapping[str, object],
    kind: str,
) -> tuple[IdentityRef, Mapping[str, object]]:
    declaration = _artifact(
        registration,
        _text(selected.get("artifact_id"), f"{kind}.artifact_id"),
    )
    reference = _text(declaration.get("reference"), f"{kind}.reference")
    digest = _text(declaration.get("sha256"), f"{kind}.sha256")
    document = json.loads(
        _verified_bytes(
            _safe_file(root, reference),
            digest,
            f"registered {kind}",
        ).decode("utf-8")
    )
    document = _mapping(document, kind)
    identity = IdentityRef(
        _text(selected.get("id"), f"{kind}.id"),
        _text(selected.get("version"), f"{kind}.version"),
        sha256=digest,
        reference=reference,
    )
    if (
        document.get(f"{kind}_id") != identity.id
        or document.get(f"{kind}_version") != identity.version
    ):
        raise RepositoryCompositionError(
            f"{kind} document does not match selected authority"
        )
    return identity, document

def _package_directory(root: Path, package_root: str) -> Path:
    package = PurePosixPath(package_root)
    if (
        package.is_absolute()
        or not package.parts
        or package.as_posix() != package_root
        or any(part in {"", ".", ".."} for part in package.parts)
    ):
        raise RepositoryCompositionError("benchmark package root is unsafe")
    repository = root.resolve(strict=True)
    try:
        resolved = repository.joinpath(*package.parts).resolve(strict=True)
        resolved.relative_to(repository)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RepositoryCompositionError(
            "benchmark package root is not safely accessible"
        ) from exc
    if not resolved.is_dir():
        raise RepositoryCompositionError("benchmark package root must be a directory")
    return resolved

def _exact_benchmark_candidate(
    authority: RepositoryApplicationAuthority,
    benchmark: IdentityRef,
):
    candidate = _selected_candidate(authority, f"{benchmark.id}@{benchmark.version}")
    validation = candidate.registration_validation
    if (
        benchmark.sha256 != validation.registration_sha256
        or benchmark.reference != candidate.registration_source_id
    ):
        raise RepositoryCompositionError(
            "accepted benchmark identity no longer matches validated repository authority"
        )
    return candidate

def _exact_runner_source(
    authority: RepositoryApplicationAuthority,
    execution_boundary: ExecutionBoundary,
):
    boundary = execution_boundary.to_dict()
    runner = IdentityRef.from_value(
        _mapping(boundary.get("runner"), "execution boundary runner"),
        field="execution boundary runner",
    )
    source = _selected_runner(authority, f"{runner.id}@{runner.version}")
    validation = source.registration_validation
    if (
        runner.sha256 != validation.registration_sha256
        or runner.reference != source.registration_source_id
    ):
        raise RepositoryCompositionError(
            "accepted runner identity no longer matches validated repository authority"
        )
    return source

def _json_artifact(
    root: Path,
    registration: Mapping[str, object],
    artifact_id: str,
    name: str,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    artifact = _artifact(registration, artifact_id)
    reference = _text(artifact.get("reference"), f"{name} reference")
    digest = _text(artifact.get("sha256"), f"{name} sha256")
    raw = _verified_bytes(_safe_file(root, reference), digest, name)
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepositoryCompositionError(f"{name} must be valid UTF-8 JSON") from exc
    return artifact, _mapping(document, name)
