"""Fail-closed registered scorer invocation and score-artifact construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ..validation import (
    ArtifactSource,
    CatalogEntry,
    EvidenceSetValidationOutcome,
    RegistrationValidationOutcome,
    RetainedArtifactSource,
    SchemaIdentity,
    ValidationIssue,
    sha256_bytes,
    validate_artifact_reference,
    validate_cataloged_document,
)


SCORER_INVOCATION_CONTRACT_ID = "arcgrav.shared.scorer-invocation"
SCORER_INVOCATION_CONTRACT_VERSION = "1.0.0"
SCORE_ARTIFACT_SCHEMA = SchemaIdentity(
    "arcgrav.shared.schema.score-artifact",
    "1.0.0",
)
METRIC_REGISTRATION_SCHEMA = SchemaIdentity(
    "arcgrav.shared.schema.metric-registration",
    "1.0.0",
)
_SCORE_SCHEMA_ENTRY = CatalogEntry(
    schema=SCORE_ARTIFACT_SCHEMA,
    urn="urn:arcgrav:shared:schema:score-artifact:1.0.0",
    file="AgMark/shared/schemas/score_artifact.schema.json",
)
_METRIC_SCHEMA_ENTRY = CatalogEntry(
    schema=METRIC_REGISTRATION_SCHEMA,
    urn="urn:arcgrav:shared:schema:metric-registration:1.0.0",
    file="AgMark/shared/schemas/metric_registration.schema.json",
)

_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_NAMESPACE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[^\s]+$")
_DIAGNOSTIC = re.compile(r"^[A-Z][A-Z0-9_.:-]*$")
_SECRET_NAME = re.compile(
    r"(?:^|_)(?:api_?key|access_?token|auth_?token|authorization|bearer|"
    r"client_?secret|credential|password|private_?key|secret|session_?token)(?:_|$)"
)
_ALLOWED_GRAINS = frozenset({"repetition", "case", "treatment", "run"})
_ALLOWED_AVAILABILITY = frozenset(
    {
        "scored",
        "unavailable",
        "not_applicable",
        "non_comparable",
        "excluded",
        "completed_non_scorable",
        "failed",
        "missing",
        "invalid",
    }
)
_ALLOWED_OUTPUT_KEYS = frozenset(
    {
        "availability",
        "value",
        "companion_values",
        "failure_refs",
        "diagnostics",
        "extensions",
    }
)
_SHARED_ROLE_BINDINGS = "arcgrav.shared.evaluation:input-role-bindings"
_AUTHORITY_GUARD = object()


@dataclass(frozen=True, slots=True)
class IdentityRef:
    """Exact versioned identity carried into score evidence."""

    id: str
    version: str
    sha256: str | None = None
    reference: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.id, "id")
        _semver(self.version, "version")
        if self.sha256 is not None and (
            not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None
        ):
            raise ValueError("sha256 must be canonical when provided")
        if self.reference is not None:
            _nonempty(self.reference, "reference")

    def to_dict(self) -> dict[str, str]:
        value = {"id": self.id, "version": self.version}
        if self.sha256 is not None:
            value["sha256"] = self.sha256
        if self.reference is not None:
            value["reference"] = self.reference
        return value


@dataclass(frozen=True, slots=True)
class ScoringContext:
    """Accepted identity boundary for one scoring attempt."""

    accepted_generation_id: str
    accepted_snapshot_id: str
    execution_boundary_fingerprint: str
    benchmark: IdentityRef
    case_set: IdentityRef
    treatment_set: IdentityRef
    case_id: str
    treatment_id: str
    repetition_ids: tuple[int, ...]
    observation_ids: tuple[str, ...]
    scoring_grain: str
    invocation_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "accepted_generation_id",
            "accepted_snapshot_id",
            "case_id",
            "treatment_id",
            "invocation_id",
        ):
            _nonempty(getattr(self, field_name), field_name)
        if (
            not isinstance(self.execution_boundary_fingerprint, str)
            or _SHA256.fullmatch(self.execution_boundary_fingerprint) is None
        ):
            raise ValueError("execution_boundary_fingerprint must be canonical SHA-256")
        for value, name in (
            (self.benchmark, "benchmark"),
            (self.case_set, "case_set"),
            (self.treatment_set, "treatment_set"),
        ):
            if type(value) is not IdentityRef:
                raise TypeError(f"{name} must be IdentityRef")
        if not isinstance(self.repetition_ids, tuple) or any(
            type(value) is not int or value < 1 for value in self.repetition_ids
        ):
            raise ValueError("repetition_ids must be a tuple of positive integers")
        if len(set(self.repetition_ids)) != len(self.repetition_ids):
            raise ValueError("repetition_ids must be unique")
        if not isinstance(self.observation_ids, tuple) or any(
            not isinstance(value, str) or not value for value in self.observation_ids
        ):
            raise ValueError("observation_ids must be a tuple of non-empty strings")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("observation_ids must be unique")
        if self.scoring_grain not in _ALLOWED_GRAINS:
            raise ValueError("scoring_grain must be repetition, case, treatment, or run")


@dataclass(frozen=True, slots=True)
class ScoringEvidenceInput:
    """One declared scorer role bound to exact retained artifact bytes."""

    role: str
    artifact: Mapping[str, Any]
    source: RetainedArtifactSource

    def __post_init__(self) -> None:
        _nonempty(self.role, "role")
        if not isinstance(self.artifact, Mapping):
            raise TypeError("artifact must be a mapping")
        if type(self.source) is not RetainedArtifactSource:
            raise TypeError("source must be RetainedArtifactSource")
        frozen = _freeze_json(_clone_json(self.artifact))
        object.__setattr__(self, "artifact", frozen)


@dataclass(frozen=True, init=False)
class RegisteredScorerAuthority:
    """Opaque authority binding one validated scorer registration to exact code bytes."""

    source_id: str
    registration_sha256: str
    scorer_id: str
    scorer_version: str
    implementation_artifact_id: str
    implementation_reference: str | None
    implementation_sha256: str | None
    issues: tuple[ValidationIssue, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by validate_registered_scorer_outcome")

    @property
    def valid(self) -> bool:
        return (
            getattr(self, "_guard", None) is _AUTHORITY_GUARD
            and not getattr(self, "issues", (None,))
            and isinstance(getattr(self, "implementation_reference", None), str)
            and isinstance(getattr(self, "implementation_sha256", None), str)
        )


@dataclass(frozen=True, slots=True)
class ScorerCall:
    """Mutation-isolated benchmark-owned scorer input."""

    context: ScoringContext
    metric_registration: Mapping[str, object]
    evidence_by_role: Mapping[str, bytes]
    evidence_identity_by_role: Mapping[str, Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class ScoringOutcome:
    """Explicit scorer invocation result; only succeeded outcomes carry score authority."""

    invocation_id: str
    invocation_status: str
    artifact: Mapping[str, object] | None
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return self.invocation_status == "succeeded" and not self.issues and self.artifact is not None


def validate_registered_scorer(
    registration: Mapping[str, Any],
    *,
    registration_outcome: RegistrationValidationOutcome,
    metric_registration: Mapping[str, Any],
    implementation_artifact_id: str,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate exact active scorer authority for one preregistered metric."""

    _nonempty(source_id, "source_id")
    _nonempty(implementation_artifact_id, "implementation_artifact_id")
    if not isinstance(registration, Mapping):
        raise TypeError("registration must be a mapping")
    if type(registration_outcome) is not RegistrationValidationOutcome:
        raise TypeError("registration_outcome must be RegistrationValidationOutcome")
    if not isinstance(metric_registration, Mapping):
        raise TypeError("metric_registration must be a mapping")

    issues: list[ValidationIssue] = list(
        _cataloged_document_issues(
            metric_registration,
            entry=_METRIC_SCHEMA_ENTRY,
            filename="metric_registration.schema.json",
            source_id=f"{source_id}:metric-registration",
        )
    )
    if not registration_outcome.valid:
        _add(issues, "SCORER_REGISTRATION_AUTHORITY_INVALID", source_id, None, "valid scorer registration authority is required")
    elif not registration_outcome.matches(
        registration, source_id=registration_outcome.source_id
    ):
        _add(issues, "SCORER_REGISTRATION_AUTHORITY_MISMATCH", source_id, None, "registration authority does not bind this exact scorer registration")

    if registration.get("schema_id") != "arcgrav.shared.schema.registration" or registration.get("schema_version") != "1.0.0":
        _add(issues, "SCORER_REGISTRATION_SCHEMA_MISMATCH", source_id, None, "scorer registration must use the published registration schema")
    if registration.get("registration_kind") != "scorer":
        _add(issues, "SCORER_REGISTRATION_KIND_INVALID", source_id, "/registration_kind", "registration_kind must be scorer")
    if registration.get("status") != "active":
        _add(issues, "SCORER_REGISTRATION_NOT_ACTIVE", source_id, "/status", "only an active scorer registration may establish score authority")

    scorer = metric_registration.get("scorer_or_annotation")
    scorer_id = registration.get("registration_id")
    scorer_version = registration.get("registration_version")
    if not isinstance(scorer, Mapping):
        _add(issues, "SCORER_METRIC_PROCEDURE_MISSING", source_id, None, "metric registration must declare scorer_or_annotation")
    else:
        if scorer.get("procedure_id") != scorer_id:
            _add(issues, "SCORER_METRIC_ID_MISMATCH", source_id, None, "metric procedure_id must match the exact scorer registration")
        if scorer.get("version") != scorer_version:
            _add(issues, "SCORER_METRIC_VERSION_MISMATCH", source_id, None, "metric scorer version must match the exact scorer registration")
        if scorer.get("kind") not in {"scorer", "parser_and_scorer", "annotation", "deterministic_rule"}:
            _add(issues, "SCORER_METRIC_KIND_INVALID", source_id, None, "metric scorer kind is invalid")

    if metric_registration.get("schema_id") != METRIC_REGISTRATION_SCHEMA.schema_id or metric_registration.get("schema_version") != METRIC_REGISTRATION_SCHEMA.schema_version:
        _add(issues, "SCORER_METRIC_SCHEMA_MISMATCH", source_id, None, "metric registration must use the published metric-registration schema")
    if not _has_contract(metric_registration.get("contracts")):
        _add(issues, "SCORER_METRIC_CONTRACT_MISSING", source_id, None, "metric registration must require the scorer-invocation contract")
    if not _has_contract(registration.get("contracts")):
        _add(issues, "SCORER_REGISTRATION_CONTRACT_MISSING", source_id, None, "scorer registration must declare the scorer-invocation contract")

    artifact = _registered_artifact(registration, implementation_artifact_id)
    if artifact is None:
        _add(issues, "SCORER_IMPLEMENTATION_ARTIFACT_MISSING", source_id, "/implementation_artifacts", "exactly one registered scorer implementation artifact is required")
    elif not isinstance(artifact.get("reference"), str) or not isinstance(artifact.get("sha256"), str):
        _add(issues, "SCORER_IMPLEMENTATION_ARTIFACT_IDENTITY_INVALID", source_id, "/implementation_artifacts", "registered scorer implementation requires reference and SHA-256 identity")

    return _norm(issues)


def validate_registered_scorer_outcome(
    registration: Mapping[str, Any],
    *,
    registration_outcome: RegistrationValidationOutcome,
    metric_registration: Mapping[str, Any],
    implementation_artifact_id: str,
    source_id: str,
) -> RegisteredScorerAuthority:
    """Mint opaque scorer authority after exact registration checks."""

    issues = validate_registered_scorer(
        registration,
        registration_outcome=registration_outcome,
        metric_registration=metric_registration,
        implementation_artifact_id=implementation_artifact_id,
        source_id=source_id,
    )
    artifact = _registered_artifact(registration, implementation_artifact_id)
    value = object.__new__(RegisteredScorerAuthority)
    for name, item in (
        ("source_id", source_id),
        ("registration_sha256", registration_outcome.registration_sha256),
        ("scorer_id", registration.get("registration_id")),
        ("scorer_version", registration.get("registration_version")),
        ("implementation_artifact_id", implementation_artifact_id),
        ("implementation_reference", artifact.get("reference") if artifact else None),
        ("implementation_sha256", artifact.get("sha256") if artifact else None),
        ("issues", issues),
        ("_guard", _AUTHORITY_GUARD),
    ):
        object.__setattr__(value, name, item)
    return value


def invoke_registered_scorer(
    *,
    authority: RegisteredScorerAuthority,
    implementation_source: ArtifactSource,
    scorer: Callable[[ScorerCall], Mapping[str, Any]],
    metric_registration: Mapping[str, Any],
    context: ScoringContext,
    evidence: Sequence[ScoringEvidenceInput],
    evidence_outcome: EvidenceSetValidationOutcome,
    source_id: str,
) -> ScoringOutcome:
    """Invoke registered benchmark-owned scoring over exact retained accepted evidence."""

    _nonempty(source_id, "source_id")
    if type(authority) is not RegisteredScorerAuthority:
        raise TypeError("authority must be RegisteredScorerAuthority")
    if type(implementation_source) is not ArtifactSource:
        raise TypeError("implementation_source must be ArtifactSource")
    if not callable(scorer):
        raise TypeError("scorer must be callable")
    if not isinstance(metric_registration, Mapping):
        raise TypeError("metric_registration must be a mapping")
    if type(context) is not ScoringContext:
        raise TypeError("context must be ScoringContext")
    if type(evidence_outcome) is not EvidenceSetValidationOutcome:
        raise TypeError("evidence_outcome must be EvidenceSetValidationOutcome")
    evidence_values = _typed_evidence(evidence)

    gate_issues = list(
        _invocation_gate_issues(
            authority=authority,
            implementation_source=implementation_source,
            metric_registration=metric_registration,
            context=context,
            evidence=evidence_values,
            evidence_outcome=evidence_outcome,
            source_id=source_id,
        )
    )
    if gate_issues:
        return ScoringOutcome(
            invocation_id=context.invocation_id,
            invocation_status="not_invoked",
            artifact=None,
            issues=_norm(gate_issues),
        )

    ordered_evidence = _order_evidence(metric_registration, evidence_values)
    call = ScorerCall(
        context=context,
        metric_registration=_freeze_json(_clone_json(metric_registration)),
        evidence_by_role=MappingProxyType(
            {item.role: item.source.data for item in ordered_evidence}
        ),
        evidence_identity_by_role=MappingProxyType(
            {item.role: _freeze_json(_clone_json(item.artifact)) for item in ordered_evidence}
        ),
    )
    try:
        raw_output = scorer(call)
    except Exception:
        return ScoringOutcome(
            invocation_id=context.invocation_id,
            invocation_status="failed",
            artifact=None,
            issues=(
                _issue(
                    "SCORER_INVOCATION_FAILED",
                    source_id,
                    None,
                    "registered scorer execution failed without establishing score authority",
                ),
            ),
        )

    output_issues = _validate_scorer_output(
        raw_output,
        metric_registration=metric_registration,
        source_id=source_id,
    )
    if output_issues:
        return ScoringOutcome(
            invocation_id=context.invocation_id,
            invocation_status="invalid_result",
            artifact=None,
            issues=output_issues,
        )

    artifact = _build_score_artifact(
        raw_output,
        authority=authority,
        metric_registration=metric_registration,
        context=context,
        evidence=ordered_evidence,
    )
    artifact_issues = validate_score_artifact(
        artifact,
        authority=authority,
        metric_registration=metric_registration,
        context=context,
        evidence=ordered_evidence,
        source_id=source_id,
    )
    if artifact_issues:
        return ScoringOutcome(
            invocation_id=context.invocation_id,
            invocation_status="invalid_result",
            artifact=None,
            issues=artifact_issues,
        )
    return ScoringOutcome(
        invocation_id=context.invocation_id,
        invocation_status="succeeded",
        artifact=_freeze_json(artifact),
        issues=(),
    )


def validate_score_artifact(
    artifact: Mapping[str, Any],
    *,
    authority: RegisteredScorerAuthority,
    metric_registration: Mapping[str, Any],
    context: ScoringContext,
    evidence: Sequence[ScoringEvidenceInput],
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate one score artifact against exact invocation and metric authority."""

    _nonempty(source_id, "source_id")
    if not isinstance(artifact, Mapping):
        raise TypeError("artifact must be a mapping")
    if type(authority) is not RegisteredScorerAuthority:
        raise TypeError("authority must be RegisteredScorerAuthority")
    if not isinstance(metric_registration, Mapping):
        raise TypeError("metric_registration must be a mapping")
    if type(context) is not ScoringContext:
        raise TypeError("context must be ScoringContext")
    artifact = _clone_json(artifact)
    inputs = _typed_evidence(evidence)
    issues: list[ValidationIssue] = list(
        _cataloged_document_issues(
            artifact,
            entry=_SCORE_SCHEMA_ENTRY,
            filename="score_artifact.schema.json",
            source_id=f"{source_id}:score-artifact",
        )
    )

    required = {
        "schema_id", "schema_version", "extensions", "score_artifact_id",
        "accepted_generation_id", "accepted_snapshot_id",
        "execution_boundary_fingerprint", "benchmark", "case_set",
        "treatment_set", "case_id", "treatment_id", "repetition_ids",
        "observation_ids", "metric_registration", "metric", "scorer",
        "scoring_grain", "input_evidence", "invocation_id",
        "invocation_status", "availability", "unit", "companion_values",
        "rule_snapshot", "failure_refs",
    }
    allowed = required | {"value", "diagnostics"}
    for key in sorted(required - set(artifact)):
        _add(issues, "SCORE_ARTIFACT_FIELD_MISSING", source_id, f"/{_escape(key)}", f"required score artifact field {key!r} is missing")
    for key in sorted(set(artifact) - allowed):
        _add(issues, "SCORE_ARTIFACT_FIELD_UNKNOWN", source_id, f"/{_escape(str(key))}", f"unknown score artifact field {key!r}")

    expected_pairs = {
        "schema_id": SCORE_ARTIFACT_SCHEMA.schema_id,
        "schema_version": SCORE_ARTIFACT_SCHEMA.schema_version,
        "accepted_generation_id": context.accepted_generation_id,
        "accepted_snapshot_id": context.accepted_snapshot_id,
        "execution_boundary_fingerprint": context.execution_boundary_fingerprint,
        "case_id": context.case_id,
        "treatment_id": context.treatment_id,
        "scoring_grain": context.scoring_grain,
        "invocation_id": context.invocation_id,
        "invocation_status": "succeeded",
        "unit": metric_registration.get("unit"),
    }
    for key, expected in expected_pairs.items():
        if artifact.get(key) != expected:
            _add(issues, "SCORE_ARTIFACT_AUTHORITY_MISMATCH", source_id, f"/{_escape(key)}", f"{key} does not match invocation authority")

    for key, expected in (
        ("benchmark", context.benchmark.to_dict()),
        ("case_set", context.case_set.to_dict()),
        ("treatment_set", context.treatment_set.to_dict()),
    ):
        if artifact.get(key) != expected:
            _add(issues, "SCORE_ARTIFACT_IDENTITY_MISMATCH", source_id, f"/{key}", f"{key} identity does not match accepted scoring context")
    if artifact.get("repetition_ids") != list(context.repetition_ids):
        _add(issues, "SCORE_ARTIFACT_REPETITION_MISMATCH", source_id, "/repetition_ids", "repetition identities do not match the scoring context")
    if artifact.get("observation_ids") != list(context.observation_ids):
        _add(issues, "SCORE_ARTIFACT_OBSERVATION_MISMATCH", source_id, "/observation_ids", "observation identities do not match the scoring context")

    expected_metric_registration = {
        "id": metric_registration.get("registration_id"),
        "version": metric_registration.get("registration_version"),
    }
    expected_metric = {
        "id": metric_registration.get("metric_id"),
        "version": metric_registration.get("metric_version"),
    }
    expected_scorer = {"id": authority.scorer_id, "version": authority.scorer_version}
    for key, expected in (
        ("metric_registration", expected_metric_registration),
        ("metric", expected_metric),
        ("scorer", expected_scorer),
    ):
        if artifact.get(key) != expected:
            _add(issues, "SCORE_ARTIFACT_REGISTRATION_MISMATCH", source_id, f"/{key}", f"{key} does not match exact registered authority")

    expected_inputs = [_artifact_projection(item.artifact) for item in inputs]
    if artifact.get("input_evidence") != expected_inputs:
        _add(issues, "SCORE_ARTIFACT_INPUT_EVIDENCE_MISMATCH", source_id, "/input_evidence", "score input evidence does not match the exact declared retained inputs")

    extensions = artifact.get("extensions")
    if not isinstance(extensions, Mapping) or extensions.get(_SHARED_ROLE_BINDINGS) != _role_bindings(inputs):
        _add(issues, "SCORE_ARTIFACT_ROLE_BINDING_MISSING", source_id, "/extensions", "score artifact must retain exact declared input-role bindings")

    expected_identity = dict(artifact)
    expected_identity.pop("score_artifact_id", None)
    expected_score_id = "score:" + hashlib.sha256(_canonical_json(expected_identity)).hexdigest()
    if artifact.get("score_artifact_id") != expected_score_id:
        _add(issues, "SCORE_ARTIFACT_IDENTITY_INVALID", source_id, "/score_artifact_id", "score_artifact_id does not match the exact artifact content")

    output_view = {
        key: artifact[key]
        for key in ("availability", "value", "companion_values", "failure_refs", "diagnostics", "extensions")
        if key in artifact
    }
    issues.extend(
        _validate_scorer_output(
            output_view,
            metric_registration=metric_registration,
            source_id=source_id,
            allow_shared_role_binding=True,
        )
    )
    return _norm(issues)


def _invocation_gate_issues(
    *,
    authority: RegisteredScorerAuthority,
    implementation_source: ArtifactSource,
    metric_registration: Mapping[str, Any],
    context: ScoringContext,
    evidence: tuple[ScoringEvidenceInput, ...],
    evidence_outcome: EvidenceSetValidationOutcome,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = list(
        _cataloged_document_issues(
            metric_registration,
            entry=_METRIC_SCHEMA_ENTRY,
            filename="metric_registration.schema.json",
            source_id=f"{source_id}:metric-registration",
        )
    )
    if (
        metric_registration.get("schema_id") != METRIC_REGISTRATION_SCHEMA.schema_id
        or metric_registration.get("schema_version") != METRIC_REGISTRATION_SCHEMA.schema_version
    ):
        _add(issues, "SCORER_METRIC_SCHEMA_MISMATCH", source_id, None, "metric registration must use the published metric-registration schema")
    for field_name in (
        "registration_id",
        "metric_id",
        "name",
        "formula_or_algorithm",
        "unit",
        "normalization_and_equivalence",
        "availability_and_noncomparability",
    ):
        if not isinstance(metric_registration.get(field_name), str) or not metric_registration.get(field_name):
            _add(issues, "SCORER_METRIC_FIELD_INVALID", source_id, f"/{field_name}", f"metric field {field_name!r} must be a non-empty string")
    for field_name in ("registration_version", "metric_version"):
        value = metric_registration.get(field_name)
        if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
            _add(issues, "SCORER_METRIC_VERSION_INVALID", source_id, f"/{field_name}", f"metric field {field_name!r} must be an exact semantic version")
    if not isinstance(metric_registration.get("numerator_denominator"), Mapping):
        _add(issues, "SCORER_METRIC_DENOMINATOR_RULE_INVALID", source_id, "/numerator_denominator", "metric numerator_denominator must be an object")
    if not isinstance(metric_registration.get("state_treatment"), list):
        _add(issues, "SCORER_METRIC_STATE_RULE_INVALID", source_id, "/state_treatment", "metric state_treatment must be an array")
    if not authority.valid:
        _add(issues, "SCORER_AUTHORITY_INVALID", source_id, None, "validated scorer authority is required")
    if implementation_source.artifact_id != authority.implementation_artifact_id:
        _add(issues, "SCORER_IMPLEMENTATION_ID_MISMATCH", source_id, None, "implementation artifact_id does not match scorer authority")
    if implementation_source.reference != authority.implementation_reference:
        _add(issues, "SCORER_IMPLEMENTATION_REFERENCE_MISMATCH", source_id, None, "implementation reference does not match scorer authority")
    if sha256_bytes(implementation_source.data) != authority.implementation_sha256:
        _add(issues, "SCORER_IMPLEMENTATION_HASH_MISMATCH", source_id, None, "implementation bytes do not match scorer authority")

    scorer = metric_registration.get("scorer_or_annotation")
    if not isinstance(scorer, Mapping) or scorer.get("procedure_id") != authority.scorer_id or scorer.get("version") != authority.scorer_version:
        _add(issues, "SCORER_METRIC_AUTHORITY_MISMATCH", source_id, None, "metric registration does not authorize this exact scorer")
    if not _has_contract(metric_registration.get("contracts")):
        _add(issues, "SCORER_METRIC_CONTRACT_MISSING", source_id, None, "metric registration lacks scorer-invocation contract authority")

    if not evidence_outcome.publication_authorized:
        _add(issues, "SCORER_EVIDENCE_AUTHORITY_INVALID", source_id, None, "accepted evidence validation authority is required before scoring")
    if evidence_outcome.generation_id != context.accepted_generation_id:
        _add(issues, "SCORER_EVIDENCE_GENERATION_MISMATCH", source_id, None, "retained evidence authority does not match the accepted scoring generation")

    required_roles = metric_registration.get("required_inputs")
    if not isinstance(required_roles, list) or any(
        not isinstance(role, str) or not role for role in required_roles
    ) or len(set(required_roles)) != len(required_roles):
        _add(issues, "SCORER_REQUIRED_INPUTS_INVALID", source_id, None, "metric required_inputs must be a unique list of non-empty role names")
        required_set: set[str] = set()
    else:
        required_set = set(required_roles)
    actual_roles = [item.role for item in evidence]
    if len(set(actual_roles)) != len(actual_roles):
        _add(issues, "SCORER_INPUT_ROLE_AMBIGUOUS", source_id, None, "each scorer input role must be bound exactly once")
    if set(actual_roles) != required_set:
        _add(issues, "SCORER_INPUT_ROLE_SET_MISMATCH", source_id, None, "scorer input roles must exactly match metric required_inputs")

    seen_artifacts: set[str] = set()
    for index, item in enumerate(evidence):
        local = validate_artifact_reference(
            item.artifact,
            source=item.source,
            source_id=source_id,
            json_pointer=f"/evidence/{index}/artifact",
            require_available=True,
        )
        issues.extend(local)
        artifact_id = item.artifact.get("artifact_id")
        digest = item.artifact.get("sha256")
        if isinstance(artifact_id, str):
            if artifact_id in seen_artifacts:
                _add(issues, "SCORER_INPUT_ARTIFACT_AMBIGUOUS", source_id, f"/evidence/{index}/artifact/artifact_id", "one retained artifact cannot satisfy multiple declared roles implicitly")
            seen_artifacts.add(artifact_id)
        if not isinstance(artifact_id, str) or not isinstance(digest, str) or not evidence_outcome.authorizes(artifact_id, digest):
            _add(issues, "SCORER_INPUT_NOT_AUTHORIZED", source_id, f"/evidence/{index}/artifact", "input evidence is not authorized by the exact accepted evidence set")
    return _norm(issues)


def _validate_scorer_output(
    output: object,
    *,
    metric_registration: Mapping[str, Any],
    source_id: str,
    allow_shared_role_binding: bool = False,
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    if not isinstance(output, Mapping):
        return (
            _issue("SCORER_OUTPUT_INVALID", source_id, None, "registered scorer must return an object"),
        )
    unknown = set(output) - _ALLOWED_OUTPUT_KEYS
    for key in sorted(unknown, key=str):
        _add(issues, "SCORER_OUTPUT_FIELD_UNKNOWN", source_id, f"/{_escape(str(key))}", f"unknown scorer output field {key!r}")

    availability = output.get("availability")
    if availability not in _ALLOWED_AVAILABILITY:
        _add(issues, "SCORER_OUTPUT_AVAILABILITY_INVALID", source_id, "/availability", "scorer output requires an explicit shared score availability state")
    if availability == "scored":
        if "value" not in output:
            _add(issues, "SCORER_OUTPUT_VALUE_MISSING", source_id, "/value", "scored output requires a value")
        else:
            issues.extend(_metric_value_issues(output.get("value"), metric_registration, source_id))
    elif "value" in output:
        _add(issues, "SCORER_OUTPUT_VALUE_FORBIDDEN", source_id, "/value", "non-scored output must not carry a fabricated value")

    companions = output.get("companion_values", [])
    if not isinstance(companions, (list, tuple)):
        _add(issues, "SCORER_OUTPUT_COMPANIONS_INVALID", source_id, "/companion_values", "companion_values must be a sequence")
        companion_names: set[str] = set()
    else:
        companion_names = set()
        for index, item in enumerate(companions):
            if not isinstance(item, Mapping) or not isinstance(item.get("name"), str) or not item.get("name") or "value" not in item:
                _add(issues, "SCORER_OUTPUT_COMPANION_INVALID", source_id, f"/companion_values/{index}", "each companion requires name and value")
                continue
            name = item["name"]
            if name in companion_names:
                _add(issues, "SCORER_OUTPUT_COMPANION_AMBIGUOUS", source_id, f"/companion_values/{index}/name", "companion names must be unique")
            companion_names.add(name)
            if set(item) - {"name", "value", "unit"}:
                _add(issues, "SCORER_OUTPUT_COMPANION_FIELD_UNKNOWN", source_id, f"/companion_values/{index}", "companion values may contain only name, value, and optional unit")
            if "unit" in item and item["unit"] is not None and not isinstance(item["unit"], str):
                _add(issues, "SCORER_OUTPUT_COMPANION_UNIT_INVALID", source_id, f"/companion_values/{index}/unit", "companion unit must be string or null")
            if not _json_value(item.get("value")):
                _add(issues, "SCORER_OUTPUT_COMPANION_VALUE_INVALID", source_id, f"/companion_values/{index}/value", "companion value must be finite JSON-compatible evidence")

    required_companions = metric_registration.get("required_companion_values")
    if not isinstance(required_companions, list) or any(
        not isinstance(name, str) or not name for name in required_companions
    ):
        _add(issues, "SCORER_METRIC_COMPANION_RULE_INVALID", source_id, None, "metric required_companion_values must be a list of names")
    elif not set(required_companions).issubset(companion_names):
        _add(issues, "SCORER_OUTPUT_REQUIRED_COMPANION_MISSING", source_id, "/companion_values", "scorer output is missing a required companion value")

    for field in ("failure_refs", "diagnostics"):
        values = output.get(field, [])
        if not isinstance(values, (list, tuple)) or any(not isinstance(value, str) or not value for value in values):
            _add(issues, f"SCORER_OUTPUT_{field.upper()}_INVALID", source_id, f"/{field}", f"{field} must be a sequence of non-empty strings")
        elif len(set(values)) != len(values):
            _add(issues, f"SCORER_OUTPUT_{field.upper()}_AMBIGUOUS", source_id, f"/{field}", f"{field} must not contain duplicates")
        elif field == "diagnostics" and any(_DIAGNOSTIC.fullmatch(value) is None for value in values):
            _add(issues, "SCORER_OUTPUT_DIAGNOSTIC_NOT_REDACTED", source_id, "/diagnostics", "retained diagnostics must be stable redacted diagnostic codes")

    if availability != "scored" and not output.get("failure_refs") and not output.get("diagnostics"):
        _add(issues, "SCORER_OUTPUT_REASON_MISSING", source_id, None, "non-scored output must retain an explicit failure reference or redacted diagnostic reason")

    extensions = output.get("extensions", {})
    if not isinstance(extensions, Mapping):
        _add(issues, "SCORER_OUTPUT_EXTENSIONS_INVALID", source_id, "/extensions", "extensions must be an object")
    else:
        for key, value in extensions.items():
            if not isinstance(key, str) or _NAMESPACE.fullmatch(key) is None:
                _add(issues, "SCORER_OUTPUT_EXTENSION_KEY_INVALID", source_id, "/extensions", "extension keys must be namespaced")
                continue
            if _secret_key(key):
                _add(issues, "SCORER_OUTPUT_SECRET_EXTENSION_FORBIDDEN", source_id, f"/extensions/{_escape(key)}", "secret-bearing extension keys are forbidden")
            if key == _SHARED_ROLE_BINDINGS and not allow_shared_role_binding:
                _add(issues, "SCORER_OUTPUT_SHARED_EXTENSION_FORBIDDEN", source_id, f"/extensions/{_escape(key)}", "shared input-role authority is constructed only by shared evaluation")
            if not _json_value(value):
                _add(issues, "SCORER_OUTPUT_EXTENSION_VALUE_INVALID", source_id, f"/extensions/{_escape(key)}", "extension values must be finite JSON-compatible evidence")
    return _norm(issues)


def _metric_value_issues(
    value: object,
    metric_registration: Mapping[str, Any],
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    domain = metric_registration.get("valid_range")
    if not isinstance(domain, Mapping):
        return (_issue("SCORER_METRIC_VALUE_DOMAIN_INVALID", source_id, None, "metric valid_range is missing or invalid"),)
    kind = domain.get("kind")
    if kind == "numeric":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            _add(issues, "SCORER_OUTPUT_VALUE_TYPE_INVALID", source_id, "/value", "numeric metric requires a finite number")
        else:
            minimum = domain.get("minimum")
            maximum = domain.get("maximum")
            if minimum is not None and (isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or (isinstance(minimum, float) and not math.isfinite(minimum))):
                _add(issues, "SCORER_METRIC_VALUE_DOMAIN_INVALID", source_id, None, "registered numeric minimum must be finite or null")
            elif minimum is not None and value < minimum:
                _add(issues, "SCORER_OUTPUT_VALUE_RANGE_INVALID", source_id, "/value", "numeric score is below the registered minimum")
            if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, (int, float)) or (isinstance(maximum, float) and not math.isfinite(maximum))):
                _add(issues, "SCORER_METRIC_VALUE_DOMAIN_INVALID", source_id, None, "registered numeric maximum must be finite or null")
            elif maximum is not None and value > maximum:
                _add(issues, "SCORER_OUTPUT_VALUE_RANGE_INVALID", source_id, "/value", "numeric score is above the registered maximum")
    elif kind == "categorical":
        allowed = domain.get("allowed_values")
        if not isinstance(allowed, list) or value not in allowed:
            _add(issues, "SCORER_OUTPUT_VALUE_RANGE_INVALID", source_id, "/value", "categorical score is not in the registered domain")
    elif kind == "boolean":
        if type(value) is not bool:
            _add(issues, "SCORER_OUTPUT_VALUE_TYPE_INVALID", source_id, "/value", "boolean metric requires true or false")
    elif kind == "json":
        if not _json_value(value):
            _add(issues, "SCORER_OUTPUT_VALUE_TYPE_INVALID", source_id, "/value", "JSON metric requires finite JSON-compatible evidence")
    else:
        _add(issues, "SCORER_METRIC_VALUE_DOMAIN_INVALID", source_id, None, "metric valid_range kind is invalid")
    return _norm(issues)


def _build_score_artifact(
    output: Mapping[str, Any],
    *,
    authority: RegisteredScorerAuthority,
    metric_registration: Mapping[str, Any],
    context: ScoringContext,
    evidence: tuple[ScoringEvidenceInput, ...],
) -> dict[str, object]:
    extensions = _clone_json(output.get("extensions", {}))
    extensions[_SHARED_ROLE_BINDINGS] = _role_bindings(evidence)
    artifact: dict[str, object] = {
        "schema_id": SCORE_ARTIFACT_SCHEMA.schema_id,
        "schema_version": SCORE_ARTIFACT_SCHEMA.schema_version,
        "extensions": extensions,
        "score_artifact_id": "",
        "accepted_generation_id": context.accepted_generation_id,
        "accepted_snapshot_id": context.accepted_snapshot_id,
        "execution_boundary_fingerprint": context.execution_boundary_fingerprint,
        "benchmark": context.benchmark.to_dict(),
        "case_set": context.case_set.to_dict(),
        "treatment_set": context.treatment_set.to_dict(),
        "case_id": context.case_id,
        "treatment_id": context.treatment_id,
        "repetition_ids": list(context.repetition_ids),
        "observation_ids": list(context.observation_ids),
        "metric_registration": {
            "id": metric_registration["registration_id"],
            "version": metric_registration["registration_version"],
        },
        "metric": {
            "id": metric_registration["metric_id"],
            "version": metric_registration["metric_version"],
        },
        "scorer": {"id": authority.scorer_id, "version": authority.scorer_version},
        "scoring_grain": context.scoring_grain,
        "input_evidence": [_artifact_projection(item.artifact) for item in evidence],
        "invocation_id": context.invocation_id,
        "invocation_status": "succeeded",
        "availability": output["availability"],
        "unit": metric_registration["unit"],
        "companion_values": _clone_json(output.get("companion_values", [])),
        "rule_snapshot": _rule_snapshot(metric_registration),
        "failure_refs": list(output.get("failure_refs", [])),
    }
    if "value" in output:
        artifact["value"] = _clone_json(output["value"])
    if output.get("diagnostics"):
        artifact["diagnostics"] = list(output["diagnostics"])
    identity_payload = dict(artifact)
    identity_payload.pop("score_artifact_id")
    artifact["score_artifact_id"] = "score:" + hashlib.sha256(
        _canonical_json(identity_payload)
    ).hexdigest()
    return artifact


def _rule_snapshot(metric_registration: Mapping[str, Any]) -> dict[str, str]:
    numerator = metric_registration.get("numerator_denominator")
    denominator = numerator.get("denominator_rule") if isinstance(numerator, Mapping) else None
    availability = {
        "state_treatment": metric_registration.get("state_treatment"),
        "availability_and_noncomparability": metric_registration.get("availability_and_noncomparability"),
    }
    return {
        "normalization_equivalence": str(metric_registration.get("normalization_and_equivalence", "")),
        "denominator": str(denominator or ""),
        "failure_missing_exclusion_noncomparability": _canonical_json(availability).decode("utf-8"),
    }


def _role_bindings(evidence: Sequence[ScoringEvidenceInput]) -> dict[str, object]:
    return {
        item.role: {
            "artifact_id": item.artifact.get("artifact_id"),
            "sha256": item.artifact.get("sha256"),
            "reference": item.artifact.get("reference"),
            "availability": item.artifact.get("availability"),
            "provenance": item.source.provenance,
        }
        for item in evidence
    }


def _artifact_projection(artifact: Mapping[str, Any]) -> dict[str, object]:
    allowed = {"artifact_id", "sha256", "schema", "reference", "availability"}
    return {
        key: _clone_json(value)
        for key, value in artifact.items()
        if key in allowed
    }


def _cataloged_document_issues(
    document: object,
    *,
    entry: CatalogEntry,
    filename: str,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    try:
        schema_document = _load_schema_document(filename)
        return validate_cataloged_document(
            document,
            schema_document=schema_document,
            entry=entry,
            source_id=source_id,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return (
            _issue(
                "SCORER_SHARED_SCHEMA_UNAVAILABLE",
                source_id,
                None,
                "published shared schema authority is unavailable or invalid",
            ),
        )


@lru_cache(maxsize=2)
def _load_schema_document(filename: str) -> Mapping[str, Any]:
    path = Path(__file__).resolve().parents[1] / "schemas" / filename
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("shared schema document must be an object")
    return value


def _registered_artifact(
    registration: Mapping[str, Any], artifact_id: str
) -> Mapping[str, Any] | None:
    artifacts = registration.get("implementation_artifacts")
    if not isinstance(artifacts, list):
        return None
    matches = [
        item for item in artifacts
        if isinstance(item, Mapping) and item.get("artifact_id") == artifact_id
    ]
    return matches[0] if len(matches) == 1 else None


def _has_contract(raw: object) -> bool:
    if not isinstance(raw, list):
        return False
    matches = [
        item for item in raw
        if isinstance(item, Mapping)
        and item.get("id") == SCORER_INVOCATION_CONTRACT_ID
        and item.get("version") == SCORER_INVOCATION_CONTRACT_VERSION
    ]
    return len(matches) == 1


def _order_evidence(
    metric_registration: Mapping[str, Any],
    evidence: tuple[ScoringEvidenceInput, ...],
) -> tuple[ScoringEvidenceInput, ...]:
    roles = metric_registration.get("required_inputs")
    if not isinstance(roles, list):
        return evidence
    by_role = {item.role: item for item in evidence}
    return tuple(by_role[role] for role in roles)


def _typed_evidence(
    values: Sequence[ScoringEvidenceInput],
) -> tuple[ScoringEvidenceInput, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError("evidence must be a sequence")
    result = tuple(values)
    if any(type(item) is not ScoringEvidenceInput for item in result):
        raise TypeError("evidence must contain only ScoringEvidenceInput values")
    return result


def _clone_json(value: object) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("value must not contain non-finite numbers")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("value must not contain non-string object keys")
            result[key] = _clone_json(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_clone_json(item) for item in value]
    raise ValueError("value must be finite JSON-compatible data")


def _freeze_json(value: object) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, (list, tuple)):
        return all(_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _clone_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _secret_key(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return _SECRET_NAME.search(normalized) is not None


def _nonempty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _semver(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SEMVER.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an exact semantic version")
    return value


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _issue(
    code: str,
    source_id: str,
    pointer: str | None,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        source_id=source_id,
        json_pointer=pointer,
        message=message,
    )


def _add(
    issues: list[ValidationIssue],
    code: str,
    source_id: str,
    pointer: str | None,
    message: str,
) -> None:
    issues.append(_issue(code, source_id, pointer, message))


def _norm(issues: Sequence[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


__all__ = [
    "METRIC_REGISTRATION_SCHEMA",
    "SCORER_INVOCATION_CONTRACT_ID",
    "SCORER_INVOCATION_CONTRACT_VERSION",
    "SCORE_ARTIFACT_SCHEMA",
    "IdentityRef",
    "RegisteredScorerAuthority",
    "ScorerCall",
    "ScoringContext",
    "ScoringEvidenceInput",
    "ScoringOutcome",
    "invoke_registered_scorer",
    "validate_registered_scorer",
    "validate_registered_scorer_outcome",
    "validate_score_artifact",
]
