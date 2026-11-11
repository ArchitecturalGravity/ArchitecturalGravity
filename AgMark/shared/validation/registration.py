"""Fail-closed semantic validation for durable shared registrations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re
from typing import Any

from .catalog import resolve_catalog_entry, validate_exact_schema_identity
from .core import SchemaIdentity, ValidationIssue, sha256_bytes
from .structure import validate_cataloged_document


REGISTRATION_SCHEMA = SchemaIdentity(
    "arcgrav.shared.schema.registration",
    "1.0.0",
)

_METRIC_REGISTRATION_SCHEMA = SchemaIdentity(
    "arcgrav.shared.schema.metric-registration",
    "1.0.0",
)
_APPLICATION_REGISTRATION_KINDS = frozenset({"benchmark", "runner"})
_NON_APPLICATION_REGISTRATION_KINDS = frozenset(
    {
        "metric",
        "scorer",
        "report_configuration",
        "golden_runtime",
        "reconstruction_procedure",
        "other",
    }
)
_DEDICATED_REGISTRATION_SCHEMAS = {
    (
        _METRIC_REGISTRATION_SCHEMA.schema_id,
        _METRIC_REGISTRATION_SCHEMA.schema_version,
    ): _METRIC_REGISTRATION_SCHEMA,
}
_DEDICATED_REGISTRATION_SCHEMA_FAMILIES = {
    (
        _METRIC_REGISTRATION_SCHEMA.schema_id,
        _METRIC_REGISTRATION_SCHEMA.schema_version,
    ): "metric",
}


@dataclass(frozen=True)
class RegistrationDocumentClassification:
    """Deterministic family classification for one registration-like document."""

    family: str | None
    application_authority: bool
    schema_supported: bool


def classify_registration_document(
    document: Mapping[str, Any],
) -> RegistrationDocumentClassification:
    """Classify declared registration semantics before family-specific validation."""

    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")

    schema_id = document.get("schema_id")
    schema_version = document.get("schema_version")
    schema_key = (
        (schema_id, schema_version)
        if isinstance(schema_id, str) and isinstance(schema_version, str)
        else None
    )

    dedicated_family = _DEDICATED_REGISTRATION_SCHEMA_FAMILIES.get(schema_key)
    if dedicated_family is not None:
        return RegistrationDocumentClassification(
            family=dedicated_family,
            application_authority=False,
            schema_supported=True,
        )

    registration_kind = document.get("registration_kind")
    generic_schema = schema_key == (
        REGISTRATION_SCHEMA.schema_id,
        REGISTRATION_SCHEMA.schema_version,
    )
    if generic_schema:
        if (
            isinstance(registration_kind, str)
            and registration_kind in _APPLICATION_REGISTRATION_KINDS
        ):
            return RegistrationDocumentClassification(
                family=registration_kind,
                application_authority=True,
                schema_supported=True,
            )
        if (
            isinstance(registration_kind, str)
            and registration_kind in _NON_APPLICATION_REGISTRATION_KINDS
        ):
            return RegistrationDocumentClassification(
                family=registration_kind,
                application_authority=False,
                schema_supported=True,
            )
        return RegistrationDocumentClassification(
            family=None,
            application_authority=False,
            schema_supported=True,
        )

    if (
        isinstance(registration_kind, str)
        and registration_kind in _APPLICATION_REGISTRATION_KINDS
    ):
        return RegistrationDocumentClassification(
            family=registration_kind,
            application_authority=True,
            schema_supported=False,
        )

    return RegistrationDocumentClassification(
        family=None,
        application_authority=False,
        schema_supported=False,
    )


def registration_document_inspection_issues(
    document: Mapping[str, Any],
    *,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Return non-blocking diagnostics for unrecognized non-application material.

    Explicit benchmark/runner claims remain on the fail-closed application
    validation path and therefore do not produce inspection-only issues here.
    """

    _require_source_id(source_id)
    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")

    classification = classify_registration_document(document)
    if classification.application_authority or classification.family is not None:
        return ()

    if not classification.schema_supported:
        return (
            ValidationIssue(
                code="REGISTRATION_SCHEMA_UNSUPPORTED",
                source_id=source_id,
                json_pointer="/schema_id",
                message=(
                    "registration-like document does not declare a supported "
                    "registration schema identity"
                ),
            ),
        )

    return (
        ValidationIssue(
            code="REGISTRATION_FAMILY_UNSUPPORTED",
            source_id=source_id,
            json_pointer="/registration_kind",
            message=(
                "registration-like document does not declare a supported "
                "registration family"
            ),
            schema=REGISTRATION_SCHEMA,
        ),
    )


def validate_registration_document_schema(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    catalog_schema_document: Mapping[str, Any],
    schema_documents: Mapping[SchemaIdentity, Mapping[str, Any]],
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate a registration-like document under its exact declared schema.

    Supported dedicated registration schemas are validated as themselves rather
    than being coerced through the generic benchmark/runner registration schema.
    The caller supplies exact catalog and schema documents so validation does not
    infer, repair, or load authority implicitly.
    """

    _require_source_id(source_id)
    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")
    if not isinstance(catalog, Mapping):
        raise TypeError("catalog must be a mapping")
    if not isinstance(catalog_schema_document, Mapping):
        raise TypeError("catalog_schema_document must be a mapping")
    if not isinstance(schema_documents, Mapping):
        raise TypeError("schema_documents must be a mapping")

    classification = classify_registration_document(document)
    schema_key = (
        document.get("schema_id"),
        document.get("schema_version"),
    )
    if schema_key == (
        REGISTRATION_SCHEMA.schema_id,
        REGISTRATION_SCHEMA.schema_version,
    ):
        expected_schema = REGISTRATION_SCHEMA
    else:
        expected_schema = _DEDICATED_REGISTRATION_SCHEMAS.get(schema_key)

    if not classification.schema_supported or expected_schema is None:
        return (
            ValidationIssue(
                code="REGISTRATION_SCHEMA_UNSUPPORTED",
                source_id=source_id,
                json_pointer="/schema_id",
                message=(
                    "registration-like document does not declare a supported "
                    "registration schema identity"
                ),
            ),
        )

    entry, catalog_issues = resolve_catalog_entry(
        catalog,
        expected=expected_schema,
        catalog_schema_document=catalog_schema_document,
    )
    if catalog_issues:
        return catalog_issues
    if entry is None:
        raise RuntimeError("catalog resolution returned no entry without issues")

    schema_document = schema_documents.get(expected_schema)
    if schema_document is None:
        return (
            ValidationIssue(
                code="REGISTRATION_SCHEMA_DOCUMENT_UNAVAILABLE",
                source_id=source_id,
                json_pointer="/schema_id",
                message=(
                    "exact schema document is unavailable for "
                    f"{expected_schema.schema_id} "
                    f"version {expected_schema.schema_version}"
                ),
                schema=expected_schema,
            ),
        )
    if not isinstance(schema_document, Mapping):
        raise TypeError("schema_documents values must be mappings")

    return validate_cataloged_document(
        document,
        schema_document=schema_document,
        entry=entry,
        source_id=source_id,
    )


_SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_REGISTRATION_VALIDATION_OUTCOME_GUARD = object()


@dataclass(frozen=True)
class ContractRequirement:
    """Explicit consumer support for one shared contract identity."""

    contract_id: str
    supported_versions: tuple[str, ...]
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.contract_id, str) or not self.contract_id:
            raise ValueError("contract_id must be a non-empty string")
        if not isinstance(self.required, bool):
            raise ValueError("required must be a boolean")
        versions = self.supported_versions
        if isinstance(versions, str):
            raise ValueError("supported_versions must be a sequence of versions")
        try:
            normalized = tuple(versions)
        except TypeError as exc:
            raise ValueError(
                "supported_versions must be a sequence of versions"
            ) from exc
        if not normalized:
            raise ValueError("supported_versions must not be empty")
        if not all(
            isinstance(version, str) and _SEMANTIC_VERSION.fullmatch(version)
            for version in normalized
        ):
            raise ValueError("supported_versions must contain semantic versions")
        if len(set(normalized)) != len(normalized):
            raise ValueError("supported_versions must not contain duplicates")
        object.__setattr__(self, "supported_versions", normalized)


@dataclass(frozen=True)
class ArtifactSource:
    """Trusted exact bytes for one registered implementation artifact."""

    artifact_id: str
    reference: str
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id:
            raise ValueError("artifact_id must be a non-empty string")
        if not isinstance(self.reference, str) or not self.reference:
            raise ValueError("reference must be non-empty")
        if _repository_path(self.reference) is None:
            raise ValueError(
                "reference must be a canonical repository-relative path"
            )
        if not isinstance(self.data, bytes):
            raise TypeError("data must be exact bytes")


def implementation_artifact_sha256(reference: str, data: bytes) -> str:
    """Hash the exact repository bytes for one implementation artifact.

    AgMark repository-controlled text is stored and checked out as canonical LF
    by repository policy. Hashing therefore performs no line-ending
    normalization: CRLF is a different byte sequence and a policy violation,
    while binary and other byte-sensitive artifacts remain exact by definition.
    """

    if _repository_path(reference) is None:
        raise ValueError("reference must be a canonical repository-relative path")
    if not isinstance(data, bytes):
        raise TypeError("data must be exact bytes")
    return sha256_bytes(data)


@dataclass(frozen=True, init=False)
class RegistrationValidationOutcome:
    """Opaque prior-validation authority bound to one exact registration value."""

    source_id: str
    registration_sha256: str
    issues: tuple[ValidationIssue, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "RegistrationValidationOutcome values are created by "
            "validate_registration_binding_outcome"
        )

    @property
    def valid(self) -> bool:
        issues = getattr(self, "issues", None)
        return (
            getattr(self, "_authority_guard", None)
            is _REGISTRATION_VALIDATION_OUTCOME_GUARD
            and isinstance(issues, tuple)
            and not issues
        )

    def matches(
        self,
        registration: Mapping[str, Any],
        *,
        source_id: str,
    ) -> bool:
        """Return whether this outcome authorizes this exact registration input."""

        _require_source_id(source_id)
        if (
            getattr(self, "_authority_guard", None)
            is not _REGISTRATION_VALIDATION_OUTCOME_GUARD
        ):
            return False
        stored_source_id = getattr(self, "source_id", None)
        stored_sha256 = getattr(self, "registration_sha256", None)
        if (
            not isinstance(stored_source_id, str)
            or not stored_source_id
            or not isinstance(stored_sha256, str)
            or _SHA256.fullmatch(stored_sha256) is None
        ):
            return False
        if source_id != stored_source_id:
            return False
        try:
            return _registration_sha256(registration) == stored_sha256
        except (TypeError, ValueError):
            return False


def validate_registration_binding(
    registration: Mapping[str, Any],
    *,
    expected_registration_id: str,
    expected_registration_version: str,
    contract_requirements: Sequence[ContractRequirement],
    artifact_sources: Sequence[ArtifactSource],
    allowed_artifact_roots: Sequence[str],
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate exact registration authority beyond JSON Schema structure.

    Callers provide the expected registration identity, the exact contract
    versions they support, trusted implementation-artifact bytes, and the
    repository roots those artifacts may occupy. Missing authority is reported
    as issues; no identity, compatibility, path, or content value is inferred.
    """

    _require_source_id(source_id)
    _validate_expectation(
        expected_registration_id,
        expected_registration_version,
    )
    requirements = _requirements_by_id(contract_requirements)
    sources = _sources_by_id(artifact_sources)
    roots = _allowed_roots(allowed_artifact_roots)

    issues: list[ValidationIssue] = list(
        validate_exact_schema_identity(
            registration,
            expected=REGISTRATION_SCHEMA,
            source_id=source_id,
        )
    )
    _check_registration_identity(
        registration,
        expected_registration_id=expected_registration_id,
        expected_registration_version=expected_registration_version,
        source_id=source_id,
        issues=issues,
    )
    _check_contract_compatibility(
        registration,
        requirements=requirements,
        source_id=source_id,
        issues=issues,
    )
    _check_implementation_artifacts(
        registration,
        sources=sources,
        roots=roots,
        source_id=source_id,
        issues=issues,
    )
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


def validate_registration_binding_outcome(
    registration: Mapping[str, Any],
    *,
    expected_registration_id: str,
    expected_registration_version: str,
    contract_requirements: Sequence[ContractRequirement],
    artifact_sources: Sequence[ArtifactSource],
    allowed_artifact_roots: Sequence[str],
    source_id: str,
) -> RegistrationValidationOutcome:
    """Validate and bind the resulting authority to this exact registration."""

    _require_source_id(source_id)
    registration_sha256 = _registration_sha256(registration)
    issues = validate_registration_binding(
        registration,
        expected_registration_id=expected_registration_id,
        expected_registration_version=expected_registration_version,
        contract_requirements=contract_requirements,
        artifact_sources=artifact_sources,
        allowed_artifact_roots=allowed_artifact_roots,
        source_id=source_id,
    )
    value = object.__new__(RegistrationValidationOutcome)
    object.__setattr__(value, "source_id", source_id)
    object.__setattr__(value, "registration_sha256", registration_sha256)
    object.__setattr__(value, "issues", issues)
    object.__setattr__(
        value,
        "_authority_guard",
        _REGISTRATION_VALIDATION_OUTCOME_GUARD,
    )
    return value


def _check_registration_identity(
    registration: Mapping[str, Any],
    *,
    expected_registration_id: str,
    expected_registration_version: str,
    source_id: str,
    issues: list[ValidationIssue],
) -> None:
    _check_exact_registration_field(
        registration,
        field="registration_id",
        expected=expected_registration_id,
        missing_code="REGISTRATION_ID_MISSING",
        mismatch_code="REGISTRATION_ID_MISMATCH",
        source_id=source_id,
        issues=issues,
    )
    _check_exact_registration_field(
        registration,
        field="registration_version",
        expected=expected_registration_version,
        missing_code="REGISTRATION_VERSION_MISSING",
        mismatch_code="REGISTRATION_VERSION_MISMATCH",
        source_id=source_id,
        issues=issues,
    )


def _check_exact_registration_field(
    registration: Mapping[str, Any],
    *,
    field: str,
    expected: str,
    missing_code: str,
    mismatch_code: str,
    source_id: str,
    issues: list[ValidationIssue],
) -> None:
    pointer = f"/{field}"
    if field not in registration:
        issues.append(
            _issue(
                missing_code,
                source_id,
                pointer,
                f"{field} must be exactly {expected!r}; value is missing",
            )
        )
    elif registration[field] != expected:
        issues.append(
            _issue(
                mismatch_code,
                source_id,
                pointer,
                f"{field} must be exactly {expected!r}",
            )
        )


def _check_contract_compatibility(
    registration: Mapping[str, Any],
    *,
    requirements: Mapping[str, ContractRequirement],
    source_id: str,
    issues: list[ValidationIssue],
) -> None:
    raw_contracts = registration.get("contracts")
    if not isinstance(raw_contracts, list):
        issues.append(
            _issue(
                "REGISTRATION_CONTRACTS_INVALID",
                source_id,
                "/contracts",
                "contracts must be an array before compatibility can be validated",
            )
        )
        return

    seen: set[str] = set()
    for index, raw_contract in enumerate(raw_contracts):
        pointer = f"/contracts/{index}"
        if not isinstance(raw_contract, Mapping):
            issues.append(
                _issue(
                    "REGISTRATION_CONTRACT_INVALID",
                    source_id,
                    pointer,
                    "contract declaration must be an object",
                )
            )
            continue

        contract_id = raw_contract.get("id")
        version = raw_contract.get("version")
        if not isinstance(contract_id, str) or not contract_id:
            issues.append(
                _issue(
                    "REGISTRATION_CONTRACT_INVALID",
                    source_id,
                    f"{pointer}/id",
                    "contract id must be a non-empty string",
                )
            )
            continue
        if (
            not isinstance(version, str)
            or _SEMANTIC_VERSION.fullmatch(version) is None
        ):
            issues.append(
                _issue(
                    "REGISTRATION_CONTRACT_INVALID",
                    source_id,
                    f"{pointer}/version",
                    "contract version must be an exact semantic version",
                )
            )
            continue

        if contract_id in seen:
            issues.append(
                _issue(
                    "REGISTRATION_CONTRACT_ID_AMBIGUOUS",
                    source_id,
                    f"{pointer}/id",
                    f"contract {contract_id!r} is declared more than once",
                )
            )
        else:
            seen.add(contract_id)

        requirement = requirements.get(contract_id)
        if requirement is None:
            issues.append(
                _issue(
                    "REGISTRATION_CONTRACT_UNSUPPORTED",
                    source_id,
                    pointer,
                    f"contract {contract_id!r} is not explicitly supported",
                )
            )
            continue
        if version not in requirement.supported_versions:
            issues.append(
                _issue(
                    "REGISTRATION_CONTRACT_VERSION_UNSUPPORTED",
                    source_id,
                    f"{pointer}/version",
                    (
                        f"contract {contract_id!r} version {version!r} is not "
                        "explicitly supported"
                    ),
                )
            )

    for requirement in requirements.values():
        if requirement.required and requirement.contract_id not in seen:
            issues.append(
                _issue(
                    "REGISTRATION_CONTRACT_REQUIRED_MISSING",
                    source_id,
                    "/contracts",
                    f"required contract {requirement.contract_id!r} is not declared",
                )
            )


def _check_implementation_artifacts(
    registration: Mapping[str, Any],
    *,
    sources: Mapping[str, ArtifactSource],
    roots: tuple[PurePosixPath, ...],
    source_id: str,
    issues: list[ValidationIssue],
) -> None:
    raw_artifacts = registration.get("implementation_artifacts")
    if not isinstance(raw_artifacts, list):
        issues.append(
            _issue(
                "REGISTRATION_ARTIFACTS_INVALID",
                source_id,
                "/implementation_artifacts",
                (
                    "implementation_artifacts must be an array before artifact "
                    "authority can be validated"
                ),
            )
        )
        return

    seen: set[str] = set()
    for index, raw_artifact in enumerate(raw_artifacts):
        pointer = f"/implementation_artifacts/{index}"
        if not isinstance(raw_artifact, Mapping):
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_INVALID",
                    source_id,
                    pointer,
                    "implementation artifact declaration must be an object",
                )
            )
            continue

        artifact_id = raw_artifact.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id:
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_INVALID",
                    source_id,
                    f"{pointer}/artifact_id",
                    "artifact_id must be a non-empty string",
                )
            )
            continue

        if artifact_id in seen:
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_ID_AMBIGUOUS",
                    source_id,
                    f"{pointer}/artifact_id",
                    f"artifact {artifact_id!r} is declared more than once",
                )
            )
        else:
            seen.add(artifact_id)

        reference = raw_artifact.get("reference")
        path = (
            _repository_path(reference)
            if isinstance(reference, str)
            else None
        )
        if reference is None:
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_REFERENCE_MISSING",
                    source_id,
                    f"{pointer}/reference",
                    "implementation artifact reference must be explicitly declared",
                )
            )
        elif path is None:
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_REFERENCE_INVALID",
                    source_id,
                    f"{pointer}/reference",
                    (
                        "artifact reference must be a canonical "
                        "repository-relative path"
                    ),
                )
            )
        elif not any(_path_within(path, root) for root in roots):
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_PATH_OUTSIDE_ROOT",
                    source_id,
                    f"{pointer}/reference",
                    "artifact reference is outside every allowed repository root",
                )
            )

        source = sources.get(artifact_id)
        if source is None:
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_SOURCE_MISSING",
                    source_id,
                    pointer,
                    (
                        f"trusted bytes for artifact {artifact_id!r} were not "
                        "provided"
                    ),
                )
            )
        elif reference != source.reference:
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_REFERENCE_MISMATCH",
                    source_id,
                    f"{pointer}/reference",
                    f"artifact reference must be exactly {source.reference!r}",
                )
            )

        declared_hash = raw_artifact.get("sha256")
        if (
            not isinstance(declared_hash, str)
            or _SHA256.fullmatch(declared_hash) is None
        ):
            issues.append(
                _issue(
                    "REGISTRATION_ARTIFACT_HASH_INVALID",
                    source_id,
                    f"{pointer}/sha256",
                    (
                        "artifact sha256 must use 'sha256:' plus 64 lowercase "
                        "hex digits"
                    ),
                )
            )
        elif source is not None:
            actual_hash = implementation_artifact_sha256(source.reference, source.data)
            if declared_hash != actual_hash and not _is_contaminable_prompt(
                registration, raw_artifacts, sources, artifact_id, reference, declared_hash
            ):
                issues.append(
                    _issue(
                        "REGISTRATION_ARTIFACT_HASH_MISMATCH",
                        source_id,
                        f"{pointer}/sha256",
                        (
                            "artifact hash does not match repository identity for "
                            f"{artifact_id!r}"
                        ),
                    )
                )


def _is_contaminable_prompt(registration, artifacts, sources, artifact_id, reference, digest):
    """Only prompt content selected by an intact registered manifest may differ."""
    extensions = registration.get("extensions")
    policy = extensions.get("arcgrav.benchmark:treatment-content-policy") if isinstance(extensions, Mapping) else None
    if not isinstance(policy, Mapping) or policy.get("mismatch") != "contaminated":
        return False
    prompts = policy.get("prompt_artifacts")
    if not isinstance(prompts, Mapping) or artifact_id not in prompts.values():
        return False
    manifest_id = policy.get("treatment_set_artifact_id")
    if not isinstance(manifest_id, str) or not isinstance(reference, str):
        return False
    source = sources.get(manifest_id)
    declarations = [a for a in artifacts if isinstance(a, Mapping) and a.get("artifact_id") == manifest_id]
    if (source is None or len(declarations) != 1
            or source.reference != declarations[0].get("reference")
            or sha256_bytes(source.data) != declarations[0].get("sha256")):
        return False
    try:
        manifest = json.loads(source.data)
    except (ValueError, UnicodeError):
        return False
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("treatments"), list):
        return False
    for treatment in manifest["treatments"]:
        if not isinstance(treatment, Mapping) or not isinstance(treatment.get("prompt"), Mapping):
            continue
        prompt = treatment["prompt"]
        if (prompts.get(treatment.get("treatment_id")) == artifact_id
                and isinstance(prompt.get("reference"), str)
                and reference.endswith("/" + prompt["reference"])
                and digest == prompt.get("sha256")):
            return True
    return False


def _requirements_by_id(
    requirements: Sequence[ContractRequirement],
) -> dict[str, ContractRequirement]:
    by_id: dict[str, ContractRequirement] = {}
    for requirement in requirements:
        if type(requirement) is not ContractRequirement:
            raise TypeError(
                "contract_requirements must contain ContractRequirement values"
            )
        if requirement.contract_id in by_id:
            raise ValueError(
                f"duplicate contract requirement for {requirement.contract_id!r}"
            )
        by_id[requirement.contract_id] = requirement
    return by_id


def _sources_by_id(
    sources: Sequence[ArtifactSource],
) -> dict[str, ArtifactSource]:
    by_id: dict[str, ArtifactSource] = {}
    for source in sources:
        if type(source) is not ArtifactSource:
            raise TypeError("artifact_sources must contain ArtifactSource values")
        if source.artifact_id in by_id:
            raise ValueError(f"duplicate artifact source for {source.artifact_id!r}")
        by_id[source.artifact_id] = source
    return by_id


def _allowed_roots(values: Sequence[str]) -> tuple[PurePosixPath, ...]:
    if isinstance(values, str):
        raise ValueError("allowed_artifact_roots must be a sequence of paths")
    if not values:
        raise ValueError("allowed_artifact_roots must not be empty")
    roots: list[PurePosixPath] = []
    for value in values:
        if value == ".":
            roots.append(PurePosixPath("."))
            continue
        root = _repository_path(value)
        if root is None:
            raise ValueError(
                (
                    "allowed_artifact_roots must be canonical "
                    "repository-relative paths"
                )
            )
        roots.append(root)
    if len(set(roots)) != len(roots):
        raise ValueError("allowed_artifact_roots must not contain duplicates")
    return tuple(roots)


def _registration_sha256(registration: Mapping[str, Any]) -> str:
    if not isinstance(registration, Mapping):
        raise TypeError("registration must be a mapping")
    try:
        canonical = json.dumps(
            registration,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "registration must be JSON-compatible before it can establish authority"
        ) from exc
    return sha256_bytes(canonical.encode("utf-8"))


def _repository_path(value: str) -> PurePosixPath | None:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or (len(value) >= 2 and value[1] == ":")
    ):
        return None
    path = PurePosixPath(value)
    if str(path) != value or path == PurePosixPath("."):
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def _path_within(path: PurePosixPath, root: PurePosixPath) -> bool:
    return (
        root == PurePosixPath(".")
        or path == root
        or root in path.parents
    )


def _require_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id must be a non-empty string")


def _validate_expectation(
    registration_id: str,
    registration_version: str,
) -> None:
    if not isinstance(registration_id, str) or not registration_id:
        raise ValueError("expected_registration_id must be a non-empty string")
    if (
        not isinstance(registration_version, str)
        or _SEMANTIC_VERSION.fullmatch(registration_version) is None
    ):
        raise ValueError(
            "expected_registration_version must be a semantic version"
        )


def _issue(
    code: str,
    source_id: str,
    pointer: str,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        source_id=source_id,
        json_pointer=pointer,
        message=message,
        schema=REGISTRATION_SCHEMA,
    )


__all__ = [
    "REGISTRATION_SCHEMA",
    "ArtifactSource",
    "ContractRequirement",
    "implementation_artifact_sha256",
    "RegistrationDocumentClassification",
    "RegistrationValidationOutcome",
    "classify_registration_document",
    "registration_document_inspection_issues",
    "validate_registration_document_schema",
    "validate_registration_binding",
    "validate_registration_binding_outcome",
]
