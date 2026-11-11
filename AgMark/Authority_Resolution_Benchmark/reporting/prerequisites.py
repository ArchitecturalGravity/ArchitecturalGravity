"""ARB registered-prerequisite derivation from retained accepted authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Final

from AgMark.shared.reporting import RevalidatedReportingInput
from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, sha256_bytes
from AgMark.shared.runtime.orchestration import AcceptedRun
from AgMark.shared.validation import RegistrationValidationOutcome


_AUTHORITY_EXTENSION: Final[str] = "arcgrav.authority-resolution:benchmark-authority"
_REPORT_CONFIGURATION_EXTENSION: Final[str] = (
    "arcgrav.authority-resolution:report-configuration"
)
_INPUT_ROLE_BINDINGS: Final[str] = "arcgrav.shared.evaluation:input-role-bindings"
_COMPLETE_STATUSES: Final[frozenset[str]] = frozenset(
    {"complete", "complete_with_deviations"}
)


class RegisteredPrerequisitesError(ValueError):
    """Required ARB prerequisite authority is malformed or unavailable."""


@dataclass(frozen=True, slots=True)
class RegisteredPrerequisiteResult:
    prerequisite: str
    state: str
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "prerequisite": self.prerequisite,
            "state": self.state,
        }
        if self.reason is not None:
            value["reason"] = self.reason
        return value


@dataclass(frozen=True, slots=True)
class RegisteredPrerequisites:
    """Derived completion-time prerequisite state for one exact ARB report attempt."""

    report_id: str
    accepted_generation_id: str
    state: str
    evidence_class: str
    registered_logic_set: Mapping[str, str]
    registered_logic_prerequisites: tuple[RegisteredPrerequisiteResult, ...]
    reasons: tuple[str, ...]

    @property
    def prerequisites_satisfied(self) -> bool:
        return all(item.state == "satisfied" for item in self.registered_logic_prerequisites)

    def section(self, *, content_boundary: str) -> dict[str, object]:
        if not isinstance(content_boundary, str) or not content_boundary:
            raise ValueError("content_boundary must be a non-empty string")
        return {
            "availability": "available",
            "content_boundary": content_boundary,
            "report_id": self.report_id,
            "accepted_generation_id": self.accepted_generation_id,
            "state": self.state,
            "evidence_class": self.evidence_class,
            "registered_logic_set": dict(self.registered_logic_set),
            "registered_logic_prerequisites": [
                item.to_dict() for item in self.registered_logic_prerequisites
            ],
            "finalized_accepted_run": "satisfied",
            "completion_validation": "required",
            "reasons": list(self.reasons),
        }


def derive_registered_prerequisites(
    *,
    report_id: str,
    report_status: str,
    benchmark_registration: Mapping[str, object],
    benchmark_registration_validation: RegistrationValidationOutcome,
    report_configuration_data: bytes,
    logic_set_data: bytes,
    finalized: AcceptedRun,
    reporting: RevalidatedReportingInput,
    artifact_store: FilesystemArtifactStore,
) -> RegisteredPrerequisites:
    """Derive factual prerequisite outcomes from exact retained authority."""

    _text(report_id, "report_id")
    if report_status not in {
        "complete",
        "complete_with_deviations",
        "incomplete",
        "invalid",
        "dry_run",
    }:
        raise RegisteredPrerequisitesError("report_status is invalid")
    if not isinstance(benchmark_registration, Mapping):
        raise TypeError("benchmark_registration must be a mapping")
    if type(benchmark_registration_validation) is not RegistrationValidationOutcome:
        raise TypeError(
            "benchmark_registration_validation must be RegistrationValidationOutcome"
        )
    if not isinstance(report_configuration_data, bytes):
        raise TypeError("report_configuration_data must be exact bytes")
    if not isinstance(logic_set_data, bytes):
        raise TypeError("logic_set_data must be exact bytes")
    if type(finalized) is not AcceptedRun:
        raise TypeError("finalized must be AcceptedRun")
    if type(reporting) is not RevalidatedReportingInput:
        raise TypeError("reporting must be RevalidatedReportingInput")
    if type(artifact_store) is not FilesystemArtifactStore:
        raise TypeError("artifact_store must be FilesystemArtifactStore")

    finalized.revalidate(artifact_store)
    if not reporting.valid:
        raise RegisteredPrerequisitesError("reporting authority is invalid")
    if reporting.accepted_generation_id != finalized.generation_id:
        raise RegisteredPrerequisitesError(
            "reporting authority and finalized run bind different generations"
        )
    if reporting.accepted.artifact_index != finalized.artifact_index:
        raise RegisteredPrerequisitesError(
            "reporting authority does not retain the finalized artifact index"
        )

    source_id = benchmark_registration_validation.source_id
    registration_valid = (
        benchmark_registration_validation.valid
        and benchmark_registration_validation.matches(
            benchmark_registration,
            source_id=source_id,
        )
    )

    authority = _mapping(
        _mapping(benchmark_registration.get("extensions"), "registration.extensions").get(
            _AUTHORITY_EXTENSION
        ),
        "ARB benchmark authority extension",
    )
    selected = _mapping(authority.get("selected_authority"), "selected_authority")
    implementation_artifacts = _artifact_declarations(benchmark_registration)

    logic = _json_object(logic_set_data, "logic set")
    configuration_document = _json_object(
        report_configuration_data,
        "report configuration",
    )
    configuration = _mapping(
        _mapping(configuration_document.get("extensions"), "report configuration extensions").get(
            _REPORT_CONFIGURATION_EXTENSION
        ),
        "report configuration extension",
    )
    prerequisite_policy = _mapping(
        configuration.get("registered_prerequisites"),
        "registered_prerequisites",
    )

    logic_selected = _mapping(selected.get("logic_set"), "selected logic_set")
    golden_selected = _mapping(
        selected.get("golden_authority"),
        "selected golden_authority",
    )
    report_selected = _mapping(
        selected.get("report_configuration"),
        "selected report_configuration",
    )
    primary_selected = _mapping(
        selected.get("primary_metric"),
        "selected primary_metric",
    )
    scorer_selected = _mapping(selected.get("scorer"), "selected scorer")
    case_selected = _mapping(selected.get("case_set"), "selected case_set")
    treatment_selected = _mapping(
        selected.get("treatment_set"),
        "selected treatment_set",
    )

    logic_artifact = _declared_artifact(
        implementation_artifacts,
        _text(logic_selected.get("artifact_id"), "logic artifact_id"),
    )
    golden_artifact = _declared_artifact(
        implementation_artifacts,
        _text(golden_selected.get("artifact_id"), "golden artifact_id"),
    )
    report_artifact = _declared_artifact(
        implementation_artifacts,
        _text(report_selected.get("artifact_id"), "report artifact_id"),
    )

    p1 = (
        registration_valid
        and logic.get("logic_set_id") == logic_selected.get("id")
        and logic.get("logic_set_version") == logic_selected.get("version")
        and logic_artifact.get("sha256") == sha256_bytes(logic_set_data)
        and _mapping(logic.get("frozen_golden_source"), "frozen_golden_source").get(
            "sha256"
        )
        == golden_artifact.get("sha256")
        and _mapping(logic.get("frozen_golden_source"), "frozen_golden_source").get(
            "reference"
        )
        == _relative_golden_reference(golden_artifact.get("reference"))
    )

    config_exact = (
        report_artifact.get("sha256") == sha256_bytes(report_configuration_data)
        and configuration_document.get("registration_id")
        == report_selected.get("registration_id")
        and configuration_document.get("registration_version")
        == report_selected.get("registration_version")
        and _mapping(prerequisite_policy.get("logic_set"), "configured logic_set")
        == {
            "id": logic.get("logic_set_id"),
            "version": logic.get("logic_set_version"),
        }
    )
    reporting_identities_match = (
        reporting.accepted.benchmark.id == benchmark_registration.get("registration_id")
        and reporting.accepted.benchmark.version
        == benchmark_registration.get("registration_version")
        and reporting.accepted.case_set.id == case_selected.get("id")
        and reporting.accepted.case_set.version == case_selected.get("version")
        and reporting.accepted.treatment_set.id == treatment_selected.get("id")
        and reporting.accepted.treatment_set.version == treatment_selected.get("version")
        and reporting.accepted.primary_endpoint.id == primary_selected.get("metric_id")
        and reporting.accepted.primary_endpoint.version
        == primary_selected.get("metric_version")
        and reporting.accepted.comparison_track_id
        == authority.get("comparison_track_id")
    )
    contract_ids = {
        (item.get("id"), item.get("version"))
        for item in _mapping_sequence(
            benchmark_registration.get("contracts"),
            "benchmark contracts",
        )
    }
    required_contracts = {
        ("arcgrav.shared.golden-execution", "2.0.0"),
        ("arcgrav.shared.runner-invocation", "2.0.0"),
        ("arcgrav.shared.scorer-invocation", "1.0.0"),
        ("arcgrav.shared.report-generation", "3.0.0"),
        ("arcgrav.shared.run-completion", "2.0.0"),
    }
    p2 = config_exact and reporting_identities_match and required_contracts <= contract_ids

    records_by_role: dict[str, list[object]] = {}
    for record in finalized.artifact_index.artifacts:
        records_by_role.setdefault(record.role, []).append(record)

    golden_records = records_by_role.get("golden_stdout", [])
    golden_documents = [
        _json_object(value, "golden observation")
        for value in finalized.golden_observations
    ]
    golden_by_reference: dict[str, tuple[object, bytes]] = {}
    for record in golden_records:
        if record.reference in golden_by_reference:
            raise RegisteredPrerequisitesError(
                "accepted generation retains ambiguous golden stdout references"
            )
        golden_by_reference[record.reference] = (
            record,
            artifact_store.read_verified(record),
        )
    golden_outputs = [
        _mapping(document.get("output"), "golden observation output")
        for document in golden_documents
    ]
    p3 = (
        bool(golden_documents)
        and len(golden_documents) == len(golden_by_reference)
        and all(
            document.get("accepted_generation_id") == finalized.generation_id
            and document.get("status") == "completed"
            and document.get("admission_state") == "admitted"
            and output.get("availability") == "retained"
            and isinstance(output.get("reference"), str)
            and output.get("reference") in golden_by_reference
            and (
                golden_by_reference[output["reference"]][0].sha256
                == output.get("sha256")
            )
            and bool(golden_by_reference[output["reference"]][1])
            and (
                sha256_bytes(golden_by_reference[output["reference"]][1])
                == output.get("sha256")
            )
            and len(golden_by_reference[output["reference"]][1])
            == output.get("byte_length")
            for document, output in zip(
                golden_documents,
                golden_outputs,
                strict=True,
            )
        )
    )

    runner_records = records_by_role.get("runner_registration", [])
    if len(runner_records) != 1:
        raise RegisteredPrerequisitesError(
            "accepted generation must retain exactly one runner registration"
        )
    runner_registration = _json_object(
        artifact_store.read_verified(runner_records[0]),
        "retained runner registration",
    )
    runner_id = _text(runner_registration.get("registration_id"), "runner id")
    runner_version = _text(
        runner_registration.get("registration_version"),
        "runner version",
    )
    runner_extensions = _mapping(
        runner_registration.get("extensions"),
        "runner registration extensions",
    )
    evidence_class = runner_extensions.get("arcgrav.adapters:evidence_class")

    treatment_documents = [
        _json_object(artifact_store.read_verified(record), "treatment observation")
        for record in records_by_role.get("treatment_observation", [])
    ]
    treatment_ids = [value.get("observation_id") for value in treatment_documents]
    p4 = (
        bool(treatment_documents)
        and len(treatment_documents) == reporting.accepted.observation_counts.finalized
        and len(treatment_ids) == len(set(treatment_ids))
        and all(
            value.get("accepted_generation_id") == finalized.generation_id
            and value.get("execution_boundary_fingerprint")
            == finalized.execution_boundary_fingerprint
            and value.get("runner") == {"id": runner_id, "version": runner_version}
            for value in treatment_documents
        )
    )

    score_documents = [
        _json_object(artifact_store.read_verified(record), "score artifact")
        for record in records_by_role.get("score_artifact", [])
    ]
    expected_metric_registration = {
        "id": primary_selected.get("registration_id"),
        "version": primary_selected.get("registration_version"),
    }
    expected_metric = {
        "id": primary_selected.get("metric_id"),
        "version": primary_selected.get("metric_version"),
    }
    expected_scorer = {
        "id": scorer_selected.get("registration_id"),
        "version": scorer_selected.get("registration_version"),
    }
    p5 = (
        len(score_documents) == len(treatment_documents)
        and bool(score_documents)
        and all(
            value.get("accepted_generation_id") == finalized.generation_id
            and value.get("accepted_snapshot_id") == finalized.accepted_snapshot_id
            and value.get("execution_boundary_fingerprint")
            == finalized.execution_boundary_fingerprint
            and value.get("metric_registration") == expected_metric_registration
            and value.get("metric") == expected_metric
            and value.get("scorer") == expected_scorer
            and value.get("invocation_status") == "succeeded"
            and set(
                _mapping(
                    _mapping(value.get("extensions"), "score extensions").get(
                        _INPUT_ROLE_BINDINGS
                    ),
                    "score input role bindings",
                )
            )
            == {"golden_stdout", "treatment_response"}
            for value in score_documents
        )
    )

    prerequisites = logic.get("registered_prerequisites")
    if not isinstance(prerequisites, list) or len(prerequisites) != 6 or any(
        not isinstance(value, str) or not value for value in prerequisites
    ):
        raise RegisteredPrerequisitesError(
            "registered logic set must declare the six executable core prerequisites"
        )

    checks = (p1, p2, p3, p4, p5)
    results: list[RegisteredPrerequisiteResult] = []
    failure_reasons = (
        "registered_logic_or_golden_binding_mismatch",
        "report_configuration_or_registered_identity_mismatch",
        "retained_golden_output_missing_empty_or_inconsistent",
        "treatment_observation_generation_boundary_or_runner_mismatch",
        "score_artifact_identity_status_or_input_binding_mismatch",
    )
    for prerequisite, satisfied, reason in zip(prerequisites[:5], checks, failure_reasons, strict=True):
        results.append(
            RegisteredPrerequisiteResult(
                prerequisite=prerequisite,
                state="satisfied" if satisfied else "unsatisfied",
                reason=None if satisfied else reason,
            )
        )

    finalized_ready = (
        finalized.run_outcome().get("status") == "accepted"
        and reporting.valid
        and reporting.accepted_generation_id == finalized.generation_id
    )
    results.append(
        RegisteredPrerequisiteResult(
            prerequisite=prerequisites[5],
            state="satisfied" if finalized_ready else "unsatisfied",
            reason=(
                None
                if finalized_ready
                else "finalized_accepted_reporting_authority_not_satisfied"
            ),
        )
    )

    reasons = [item.reason for item in results if item.reason is not None]
    if report_status not in _COMPLETE_STATUSES:
        reasons.append("report_status_not_complete:" + report_status)
    for key in (
        "require_all_registered_logic_set_prerequisites",
        "require_finalized_accepted_run",
        "require_automatic_completion_validation",
    ):
        if prerequisite_policy.get(key) is not True:
            reasons.append("report_configuration_policy_invalid:" + key)

    return RegisteredPrerequisites(
        report_id=report_id,
        accepted_generation_id=finalized.generation_id,
        state="unsatisfied" if reasons else "satisfied",
        evidence_class=str(evidence_class) if evidence_class is not None else "unclassified",
        registered_logic_set={
            "id": _text(logic.get("logic_set_id"), "logic_set_id"),
            "version": _text(logic.get("logic_set_version"), "logic_set_version"),
        },
        registered_logic_prerequisites=tuple(results),
        reasons=tuple(reasons),
    )


def evaluate_report_extensions(**inputs: object) -> dict[str, object]:
    """Build the registered factual section after shared source admission."""
    outcome = derive_registered_prerequisites(**inputs)
    configuration_document = _json_object(inputs["report_configuration_data"], "report configuration")
    configuration = _mapping(
        _mapping(configuration_document.get("extensions"), "report configuration extensions").get(
            _REPORT_CONFIGURATION_EXTENSION
        ),
        "report configuration extension",
    )
    policies = _mapping_sequence(
        _mapping(configuration.get("section_policy"), "section policy").get("required_arb_sections"),
        "required ARB sections",
    )
    section_policy = {_text(item.get("role"), "section role"): item for item in policies}
    required_roles = {
        "arb_registered_prerequisites", "arb_authority_resolution_interpretation",
        "arb_dependency_effective_execution", "arb_limitations_and_scope",
    }
    if set(section_policy) != required_roles or len(policies) != len(required_roles):
        raise RegisteredPrerequisitesError("registered report sections are missing, ambiguous or unsupported")

    reporting = inputs["reporting"]
    accepted = reporting.accepted
    metric_display = _mapping(configuration.get("metric_display"), "metric display")
    sections = {
        role: {"content_boundary": _text(policy.get("content_boundary"), "content boundary")}
        for role, policy in section_policy.items()
    }
    sections["arb_registered_prerequisites"] = outcome.section(
        content_boundary=sections["arb_registered_prerequisites"]["content_boundary"]
    )
    sections["arb_authority_resolution_interpretation"].update({
        "availability": "available",
        "primary_endpoint": {
            "id": accepted.primary_endpoint.id,
            "version": accepted.primary_endpoint.version,
            "label": _text(metric_display.get("primary_endpoint_label"), "primary endpoint label"),
        },
        "treatment_results": [
            {"treatment_id": summary.treatment_id,
             "availability": summary.availability.state,
             "numerator": summary.numerator,
             "denominator": summary.denominator,
             "value": summary.value}
            for summary in accepted.treatment_summaries
        ],
    })
    registration = inputs["benchmark_registration"]
    authority = _mapping(_mapping(registration.get("extensions"), "registration extensions").get(
        _AUTHORITY_EXTENSION), "benchmark authority")
    selected = _mapping(authority.get("selected_authority"), "selected authority")
    if any("dependency" in key or "effective_execution" in key for key in selected):
        raise RegisteredPrerequisitesError("selected dependency/effective-execution interpretation is unsupported")
    sections["arb_dependency_effective_execution"].update({
        "availability": "not_applicable",
        "reason": "No dependency/effective-execution evidence is selected by the active core registration.",
    })
    limitations = configuration.get("conclusion_boundaries")
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise RegisteredPrerequisitesError("registered measurement limitations must be strings")
    sections["arb_limitations_and_scope"].update({
        "availability": "available",
        "conclusion_boundaries": list(limitations),
    })
    return {
        "arcgrav.authority-resolution:report-interpretation": {
            "configuration": {
                "id": configuration_document["registration_id"],
                "version": configuration_document["registration_version"],
            },
            "sections": sections,
        },
    }


def _artifact_declarations(
    registration: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    values = _mapping_sequence(
        registration.get("implementation_artifacts"),
        "implementation_artifacts",
    )
    result: dict[str, Mapping[str, object]] = {}
    for value in values:
        artifact_id = _text(value.get("artifact_id"), "artifact_id")
        if artifact_id in result:
            raise RegisteredPrerequisitesError("implementation artifact id is ambiguous")
        result[artifact_id] = value
    return result


def _declared_artifact(
    artifacts: Mapping[str, Mapping[str, object]],
    artifact_id: str,
) -> Mapping[str, object]:
    try:
        return artifacts[artifact_id]
    except KeyError as exc:
        raise RegisteredPrerequisitesError(
            f"selected artifact {artifact_id!r} is not registration-bound"
        ) from exc


def _relative_golden_reference(value: object) -> object:
    prefix = "AgMark/Authority_Resolution_Benchmark/"
    if isinstance(value, str) and value.startswith(prefix):
        return value[len(prefix) :]
    return value


def _json_object(data: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegisteredPrerequisitesError(f"{label} is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise RegisteredPrerequisitesError(f"{label} must be an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RegisteredPrerequisitesError(f"{label} must be an object")
    return value


def _mapping_sequence(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise RegisteredPrerequisitesError(f"{label} must be an array of objects")
    return tuple(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegisteredPrerequisitesError(f"{label} must be a non-empty string")
    return value


__all__ = [
    "RegisteredPrerequisites",
    "RegisteredPrerequisitesError",
    "RegisteredPrerequisiteResult",
    "derive_registered_prerequisites",
    "evaluate_report_extensions",
]
