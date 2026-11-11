"""Production repository registration composition for the desktop GUI.

This module discovers registration documents from repository-owned production
surfaces, validates exact registration bytes and implementation artifacts through
the shared validation boundary, and constructs the shared application session.
It does not resolve benchmark semantics or manufacture lifecycle authority.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from AgMark.shared.application import (
    ApplicationDiscovery,
    ApplicationRegistrationSource,
    PlanningApplicationSession,
    discover_application_authority,
)
from AgMark.shared.validation import (
    ArtifactSource,
    BenchmarkDiscoveryCandidate,
    ContractRequirement,
    RegistrationValidationOutcome,
    SchemaIdentity,
    ValidationIssue,
    classify_registration_document,
    registration_document_inspection_issues,
    validate_registration_binding_outcome,
    validate_registration_document_schema,
)


_SUPPORTED_SHARED_CONTRACTS = (
    ("arcgrav.shared.runner-invocation", "2.0.0"),
    ("arcgrav.shared.launch-environment", "1.0.0"),
    ("arcgrav.shared.transient-invocation", "1.0.0"),
    ("arcgrav.shared.golden-execution", "2.0.0"),
    ("arcgrav.shared.run-lifecycle", "1.0.0"),
    ("arcgrav.shared.evidence-validation", "1.0.0"),
    ("arcgrav.shared.scorer-invocation", "1.0.0"),
    ("arcgrav.shared.failure-taxonomy", "1.0.0"),
    ("arcgrav.shared.effective-execution-evidence", "1.0.0"),
    ("arcgrav.shared.report-generation", "3.0.0"),
    ("arcgrav.shared.run-completion", "2.0.0"),
)
_RUNNER_CONTRACT_ID = "arcgrav.shared.runner-invocation"
class RepositoryCompositionError(RuntimeError):
    """Raised when repository registration authority cannot be composed safely."""


@dataclass(frozen=True, slots=True)
class RepositoryPrerequisiteDiagnostic:
    """Non-authoritative repository prerequisite blocker for GUI presentation."""

    diagnostic_name: str
    message: str
    remediation: str


@dataclass(frozen=True, slots=True)
class RepositoryApplicationAuthority:
    """Validated repository authority supplied to one GUI application session."""

    repository_root: Path
    benchmark_candidates: tuple[BenchmarkDiscoveryCandidate, ...]
    runner_sources: tuple[ApplicationRegistrationSource, ...]
    discovery: ApplicationDiscovery
    prerequisite_diagnostics: tuple[RepositoryPrerequisiteDiagnostic, ...] = ()
    repository_diagnostics: tuple[ValidationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryPlanningComposition:
    """Shared planning session plus the exact runner sources used to construct it."""

    authority: RepositoryApplicationAuthority
    session: PlanningApplicationSession


def _repository_root(value: str | Path | None) -> Path:
    root = Path(value) if value is not None else Path(__file__).resolve().parents[2]
    root = root.expanduser().resolve()
    benchmarking = root / "AgMark"
    if not benchmarking.is_dir():
        raise RepositoryCompositionError(
            f"Repository root does not contain AgMark/: {root}"
        )
    return root


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise RepositoryCompositionError(
            f"Repository resource escapes the repository root: {path}"
        ) from exc


def _load_json_object(path: Path, *, source_id: str) -> dict[str, object]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RepositoryCompositionError(
            f"Cannot read registration candidate {source_id}: {exc}"
        ) from exc
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise RepositoryCompositionError(
            f"Registration candidate is not valid UTF-8 JSON: {source_id}"
        ) from exc
    if not isinstance(value, dict):
        raise RepositoryCompositionError(
            f"Registration candidate must be a JSON object: {source_id}"
        )
    return value


def _load_shared_schema_object(path: Path, *, source_id: str) -> dict[str, object]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RepositoryCompositionError(
            f"Cannot read shared schema authority {source_id}: {exc}"
        ) from exc
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise RepositoryCompositionError(
            f"Shared schema authority is not valid UTF-8 JSON: {source_id}"
        ) from exc
    if not isinstance(value, dict):
        raise RepositoryCompositionError(
            f"Shared schema authority must be a JSON object: {source_id}"
        )
    return value


def _registration_schema_validation_inputs(
    root: Path,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[SchemaIdentity, Mapping[str, object]],
]:
    schema_root = root / "AgMark/shared/schemas"
    catalog_path = schema_root / "catalog.json"
    catalog_schema_path = schema_root / "schema_catalog.schema.json"
    catalog = _load_shared_schema_object(
        catalog_path,
        source_id=_relative_path(root, catalog_path),
    )
    catalog_schema = _load_shared_schema_object(
        catalog_schema_path,
        source_id=_relative_path(root, catalog_schema_path),
    )

    schema_documents: dict[SchemaIdentity, Mapping[str, object]] = {}
    for path in sorted(
        schema_root.glob("*.schema.json"),
        key=lambda value: value.as_posix(),
    ):
        document = _load_shared_schema_object(
            path,
            source_id=_relative_path(root, path),
        )
        schema_id = document.get("schema_id")
        schema_version = document.get("schema_version")
        if not isinstance(schema_id, str) or not isinstance(schema_version, str):
            continue
        identity = SchemaIdentity(schema_id, schema_version)
        if identity in schema_documents:
            raise RepositoryCompositionError(
                "Shared schema identity is duplicated: "
                f"{schema_id}@{schema_version}"
            )
        schema_documents[identity] = document

    return catalog, catalog_schema, schema_documents


def _registration_candidate_paths(root: Path) -> tuple[Path, ...]:
    benchmarking = root / "AgMark"
    paths: set[Path] = set()

    for package in benchmarking.iterdir():
        if not package.is_dir() or package.name in {"gui", "shared"}:
            continue
        registrations = package / "registrations"
        if registrations.is_dir():
            paths.update(registrations.rglob("*.json"))

    adapters = benchmarking / "shared" / "adapters"
    if adapters.is_dir():
        paths.update(adapters.rglob("*.json"))

    return tuple(sorted(paths, key=lambda value: value.as_posix()))


def _artifact_sources(
    root: Path,
    registration: Mapping[str, object],
) -> tuple[tuple[ArtifactSource, ...], tuple[str, ...]]:
    raw_artifacts = registration.get("implementation_artifacts")
    if not isinstance(raw_artifacts, Sequence) or isinstance(
        raw_artifacts, (str, bytes, bytearray)
    ):
        return (), ()

    sources: list[ArtifactSource] = []
    inaccessible: list[str] = []
    seen: set[str] = set()
    for raw in raw_artifacts:
        if not isinstance(raw, Mapping):
            continue
        artifact_id = raw.get("artifact_id")
        reference = raw.get("reference")
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or artifact_id in seen
            or not isinstance(reference, str)
            or not reference
        ):
            continue
        try:
            canonical = PurePosixPath(reference)
            if (
                str(canonical) != reference
                or canonical.is_absolute()
                or any(part in {"", ".", ".."} for part in canonical.parts)
            ):
                continue
            path = (root / Path(*canonical.parts)).resolve()
            path.relative_to(root)
            data = path.read_bytes()
            source = ArtifactSource(
                artifact_id=artifact_id,
                reference=reference,
                data=data,
            )
        except OSError:
            inaccessible.append(reference)
            seen.add(artifact_id)
            continue
        except ValueError:
            continue
        seen.add(artifact_id)
        sources.append(source)
    return tuple(sources), tuple(inaccessible)


def _contract_requirements(
    registration_kind: str,
) -> tuple[ContractRequirement, ...]:
    return tuple(
        ContractRequirement(
            contract_id,
            (version,),
            required=(
                registration_kind == "runner"
                and contract_id == _RUNNER_CONTRACT_ID
            ),
        )
        for contract_id, version in _SUPPORTED_SHARED_CONTRACTS
    )


def _benchmark_package_root(
    root: Path,
    registration_path: Path,
) -> str:
    relative = PurePosixPath(_relative_path(root, registration_path))
    if (
        len(relative.parts) < 3
        or relative.parts[0] != "AgMark"
        or relative.parts[1] in {"gui", "shared"}
    ):
        raise RepositoryCompositionError(
            "Benchmark registration must live under one production benchmark package: "
            + relative.as_posix()
        )
    return PurePosixPath(*relative.parts[:2]).as_posix()


def _allowed_artifact_roots(
    *,
    registration_kind: str,
    package_root: str | None,
) -> tuple[str, ...]:
    if registration_kind == "benchmark":
        if package_root is None:
            raise RepositoryCompositionError(
                "Benchmark registration validation requires a package root"
            )
        return (package_root,)
    if registration_kind == "runner":
        return ("AgMark/shared/adapters", "AgMark/shared/telemetry", "AgMark/shared/mock_model", "AgMark/shared/evaluation/telemetry/source.py", "AgMark/shared/runtime/identity/runtime_version.py")
    raise RepositoryCompositionError(
        f"Unsupported production registration kind: {registration_kind!r}"
    )


def _validate_registration(
    *,
    source_id: str,
    registration: Mapping[str, object],
    registration_kind: str,
    package_root: str | None,
    artifact_sources: Sequence[ArtifactSource],
) -> RegistrationValidationOutcome:
    registration_id = registration.get("registration_id")
    registration_version = registration.get("registration_version")
    if not isinstance(registration_id, str) or not registration_id:
        raise RepositoryCompositionError(
            f"Registration lacks a usable registration_id: {source_id}"
        )
    if not isinstance(registration_version, str) or not registration_version:
        raise RepositoryCompositionError(
            f"Registration lacks a usable registration_version: {source_id}"
        )

    try:
        outcome = validate_registration_binding_outcome(
            registration,
            expected_registration_id=registration_id,
            expected_registration_version=registration_version,
            contract_requirements=_contract_requirements(registration_kind),
            artifact_sources=artifact_sources,
            allowed_artifact_roots=_allowed_artifact_roots(
                registration_kind=registration_kind,
                package_root=package_root,
            ),
            source_id=source_id,
        )
    except (TypeError, ValueError) as exc:
        raise RepositoryCompositionError(
            f"Registration validation could not be completed for {source_id}: {exc}"
        ) from exc

    if not outcome.valid:
        codes = ", ".join(issue.code for issue in outcome.issues)
        raise RepositoryCompositionError(
            f"Registration validation failed for {source_id}: {codes}"
        )
    return outcome


def discover_repository_application_authority(
    repository_root: str | Path | None = None,
) -> RepositoryApplicationAuthority:
    """Discover and validate active benchmark and runner registration authority."""

    root = _repository_root(repository_root)
    benchmarks: list[BenchmarkDiscoveryCandidate] = []
    runners: list[ApplicationRegistrationSource] = []
    prerequisite_diagnostics: list[RepositoryPrerequisiteDiagnostic] = []
    repository_diagnostics: list[ValidationIssue] = []
    registration_schema_inputs: tuple[
        dict[str, object],
        dict[str, object],
        dict[SchemaIdentity, Mapping[str, object]],
    ] | None = None
    registration_schema_input_error: str | None = None

    def block(
        source_id: str,
        *,
        category: str,
        message: str,
        remediation: str,
    ) -> None:
        prerequisite_diagnostics.append(
            RepositoryPrerequisiteDiagnostic(
                diagnostic_name=f"repository-{category}:{source_id}",
                message=message,
                remediation=remediation,
            )
        )

    for path in _registration_candidate_paths(root):
        source_id = _relative_path(root, path)
        try:
            document = _load_json_object(path, source_id=source_id)
        except RepositoryCompositionError as exc:
            block(
                source_id,
                category="registration-discovery",
                message=str(exc),
                remediation=(
                    "Restore a readable UTF-8 JSON registration document and "
                    "reload repository discovery."
                ),
            )
            continue

        classification = classify_registration_document(document)
        if not classification.application_authority:
            if classification.family is not None:
                if (
                    registration_schema_inputs is None
                    and registration_schema_input_error is None
                ):
                    try:
                        registration_schema_inputs = (
                            _registration_schema_validation_inputs(root)
                        )
                    except RepositoryCompositionError as exc:
                        registration_schema_input_error = str(exc)

                if registration_schema_input_error is not None:
                    repository_diagnostics.append(
                        ValidationIssue(
                            code="REGISTRATION_SCHEMA_AUTHORITY_UNAVAILABLE",
                            source_id=source_id,
                            message=registration_schema_input_error,
                        )
                    )
                else:
                    if registration_schema_inputs is None:
                        raise RuntimeError(
                            "registration schema inputs are unavailable without an error"
                        )
                    (
                        schema_catalog,
                        catalog_schema_document,
                        schema_documents,
                    ) = registration_schema_inputs
                    repository_diagnostics.extend(
                        validate_registration_document_schema(
                            document,
                            catalog=schema_catalog,
                            catalog_schema_document=catalog_schema_document,
                            schema_documents=schema_documents,
                            source_id=source_id,
                        )
                    )

            repository_diagnostics.extend(
                registration_document_inspection_issues(
                    document,
                    source_id=source_id,
                )
            )
            continue

        kind = classification.family
        if kind not in {"benchmark", "runner"}:
            raise RepositoryCompositionError(
                "Application registration classification is internally inconsistent: "
                + source_id
            )
        status = document.get("status")
        if status != "active":
            continue

        try:
            package_root = (
                _benchmark_package_root(root, path)
                if kind == "benchmark"
                else None
            )
        except RepositoryCompositionError as exc:
            block(
                source_id,
                category="registration-location",
                message=str(exc),
                remediation=(
                    "Move the registration beneath its permitted production "
                    "package and reload repository discovery."
                ),
            )
            continue

        artifact_sources, inaccessible_artifacts = _artifact_sources(root, document)
        if inaccessible_artifacts:
            block(
                source_id,
                category="artifact-access",
                message=(
                    "Registered implementation artifacts are not readable: "
                    + ", ".join(inaccessible_artifacts)
                ),
                remediation=(
                    "Restore readable repository artifacts at the exact registered "
                    "references before building or executing a plan."
                ),
            )
            continue

        try:
            outcome = _validate_registration(
                source_id=source_id,
                registration=document,
                registration_kind=kind,
                package_root=package_root,
                artifact_sources=artifact_sources,
            )
        except RepositoryCompositionError as exc:
            block(
                source_id,
                category="registration-validation",
                message=str(exc),
                remediation=(
                    "Correct the repository registration or registered artifact "
                    "identity and reload repository discovery."
                ),
            )
            continue

        if kind == "benchmark":
            benchmarks.append(
                BenchmarkDiscoveryCandidate(
                    package_root=package_root,
                    registration_source_id=source_id,
                    registration=document,
                    registration_validation=outcome,
                )
            )
        else:
            runners.append(
                ApplicationRegistrationSource(
                    registration_source_id=source_id,
                    registration=document,
                    registration_validation=outcome,
                )
            )

    benchmark_candidates = tuple(benchmarks)
    runner_sources = tuple(runners)
    try:
        discovery = discover_application_authority(
            benchmark_candidates=benchmark_candidates,
            runner_sources=runner_sources,
        )
    except (TypeError, ValueError) as exc:
        raise RepositoryCompositionError(
            f"Repository application discovery failed: {exc}"
        ) from exc

    return RepositoryApplicationAuthority(
        repository_root=root,
        benchmark_candidates=benchmark_candidates,
        runner_sources=runner_sources,
        discovery=discovery,
        prerequisite_diagnostics=tuple(prerequisite_diagnostics),
        repository_diagnostics=tuple(
            sorted(set(repository_diagnostics), key=ValidationIssue.sort_key)
        ),
    )


def compose_repository_planning_session(
    repository_root: str | Path | None = None,
) -> RepositoryPlanningComposition:
    """Construct the shared planning session from validated repository authority."""

    authority = discover_repository_application_authority(repository_root)
    session = PlanningApplicationSession(
        benchmark_candidates=authority.benchmark_candidates,
        runner_sources=authority.runner_sources,
    )
    return RepositoryPlanningComposition(authority=authority, session=session)


__all__ = [
    "RepositoryApplicationAuthority",
    "RepositoryCompositionError",
    "RepositoryPlanningComposition",
    "RepositoryPrerequisiteDiagnostic",
    "compose_repository_planning_session",
    "discover_repository_application_authority",
]
