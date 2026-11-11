"""Production request resolution from validated repository authority."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
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
from AgMark.shared.adapters.execution import (
    CanonicalObservationError,
    validate_retained_parity_observation,
)
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

from .repository_resources import _artifact, _exact_benchmark_candidate, _mapping, _package_directory, _resource, _safe_file, _selected_authority, _sequence, _text, _verified_bytes
from .execution import _scoring_definition

def _reporting_identity(value: object, name: str) -> ReportingIdentityRef:
    identity = _mapping(value, name)
    digest = identity.get("sha256")
    reference = identity.get("reference")
    if digest is not None:
        digest = _text(digest, f"{name}.sha256")
    if reference is not None:
        reference = _text(reference, f"{name}.reference")
    try:
        return ReportingIdentityRef(
            _text(identity.get("id"), f"{name}.id"),
            _text(identity.get("version"), f"{name}.version"),
            sha256=digest,
            reference=reference,
        )
    except (TypeError, ValueError) as exc:
        raise RepositoryCompositionError(f"{name} is invalid") from exc

def _contract_identities(registration: Mapping[str, object]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for raw in _sequence(registration.get("contracts"), "contracts"):
        contract = _mapping(raw, "contract")
        identity = (
            _text(contract.get("id"), "contract.id"),
            _text(contract.get("version"), "contract.version"),
        )
        if identity in result:
            raise RepositoryCompositionError("registration contract identity is duplicated")
        result.add(identity)
    return result

def _report_configuration(
    root: Path,
    registration: Mapping[str, object],
    selected: Mapping[str, object],
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    selection = _mapping(
        selected.get("report_configuration"),
        "selected report configuration",
    )
    artifact = _artifact(
        registration,
        _text(selection.get("artifact_id"), "report_configuration.artifact_id"),
    )
    reference = _text(
        artifact.get("reference"),
        "report_configuration.reference",
    )
    digest = _text(artifact.get("sha256"), "report_configuration.sha256")
    try:
        document = json.loads(
            _verified_bytes(
                _safe_file(root, reference),
                digest,
                "registered report configuration",
            ).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepositoryCompositionError(
            "registered report configuration is not valid UTF-8 JSON"
        ) from exc
    document = _mapping(document, "report configuration")
    if (
        document.get("registration_id") != selection.get("registration_id")
        or document.get("registration_version") != selection.get("registration_version")
        or document.get("registration_kind") != "report_configuration"
        or document.get("status") != "active"
    ):
        raise RepositoryCompositionError(
            "registered report configuration does not match selected authority"
        )
    if _REPORT_GENERATION_CONTRACT not in _contract_identities(document):
        raise RepositoryCompositionError(
            "selected report configuration lacks the supported report-generation contract"
        )
    benchmark_contracts = _contract_identities(registration)
    if _REPORT_GENERATION_CONTRACT not in benchmark_contracts:
        raise RepositoryCompositionError(
            "benchmark registration lacks the supported report-generation contract"
        )
    if _RUN_COMPLETION_CONTRACT not in benchmark_contracts:
        raise RepositoryCompositionError(
            "benchmark registration lacks the supported run-completion contract"
        )
    return artifact, document

def _registered_report_evaluator(root, candidate, selected, config_artifact):
    """Resolve an optional, exact registration-bound benchmark report evaluator."""
    declaration = selected.get("report_evaluator")
    if declaration is None:
        return None
    declaration = _mapping(declaration, "selected report evaluator")
    if set(declaration) != {"module", "callable", "artifact_id"}:
        raise RepositoryCompositionError("report evaluator declaration has unsupported fields")
    registration = candidate.registration
    artifact = _artifact(registration, _text(declaration.get("artifact_id"), "report evaluator artifact_id"))
    reference = _text(artifact.get("reference"), "report evaluator reference")
    digest = _text(artifact.get("sha256"), "report evaluator sha256")
    path = _safe_file(root, reference)
    source = _verified_bytes(path, digest, "registered report evaluator")
    module_name = _text(declaration.get("module"), "report evaluator module")
    callable_name = _text(declaration.get("callable"), "report evaluator callable")
    if not reference.endswith(".py") or module_name != reference[:-3].replace("/", ".") or not callable_name.isidentifier():
        raise RepositoryCompositionError("report evaluator does not match registered implementation")
    # Never import by name: sys.path and sys.modules can resolve stale or
    # unrelated code even when __file__ advertises the expected source path.
    # Execute only the bytes verified above, isolated from the module cache.
    import sys
    from types import ModuleType
    from uuid import uuid4
    private_name = "_agmark_report_evaluator_" + uuid4().hex
    module = ModuleType(private_name)
    module.__file__ = str(path)
    module.__package__ = module_name.rpartition(".")[0]
    try:
        code = compile(source, str(path), "exec", dont_inherit=True)
        # Dataclass annotation handling consults sys.modules during execution.
        # A unique temporary key avoids replacing any imported module.
        sys.modules[private_name] = module
        exec(code, module.__dict__)
    except Exception as exc:
        raise RepositoryCompositionError("registered report evaluator cannot be loaded") from exc
    finally:
        sys.modules.pop(private_name, None)
    evaluator = getattr(module, callable_name, None)
    if not callable(evaluator):
        raise RepositoryCompositionError("registered report evaluator implementation mismatch")
    logic = _mapping(selected.get("logic_set"), "selected logic set")
    logic_artifact = _artifact(registration, _text(logic.get("artifact_id"), "logic set artifact_id"))
    def read(artifact, label):
        return _verified_bytes(_safe_file(root, _text(artifact.get("reference"), label + " reference")),
            _text(artifact.get("sha256"), label + " sha256"), label)
    configuration_data = read(config_artifact, "registered report configuration")
    logic_data = read(logic_artifact, "registered logic set")

    def evaluate(**kwargs):
        _verified_bytes(path, digest, "registered report evaluator")
        return evaluator(benchmark_registration=registration,
            benchmark_registration_validation=candidate.registration_validation,
            report_configuration_data=configuration_data, logic_set_data=logic_data, **kwargs)
    return evaluate

def _retained_json_documents(
    retained_run: AcceptedRun,
    values: Sequence[bytes],
    *,
    role: str,
) -> tuple[tuple[object, Mapping[str, object]], ...]:
    records = tuple(
        record
        for record in retained_run.artifact_index.artifacts
        if record.role == role
    )
    result = []
    used_artifact_ids: set[str] = set()
    for index, raw in enumerate(values):
        if not isinstance(raw, bytes):
            raise RepositoryCompositionError(
                f"retained {role} evidence at index {index} is not exact bytes"
            )
        digest = sha256_bytes(raw)
        matches = [
            record
            for record in records
            if record.sha256 == digest and record.artifact_id not in used_artifact_ids
        ]
        if len(matches) != 1:
            raise RepositoryCompositionError(
                f"retained {role} evidence does not resolve to exact accepted artifact authority"
            )
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RepositoryCompositionError(
                f"retained {role} evidence is not valid UTF-8 JSON"
            ) from exc
        if role == "treatment_observation":
            try:
                validate_retained_parity_observation(document)
            except CanonicalObservationError as exc:
                raise RepositoryCompositionError(
                    "retained treatment observation has invalid canonical execution evidence"
                ) from exc
        used_artifact_ids.add(matches[0].artifact_id)
        result.append((matches[0], _mapping(document, f"retained {role}")))
    if len(result) != len(records):
        raise RepositoryCompositionError(
            f"accepted artifact authority contains unmatched {role} evidence"
        )
    return tuple(result)

def _single_retained_record(retained_run: AcceptedRun, role: str):
    matches = [
        record
        for record in retained_run.artifact_index.artifacts
        if record.role == role
    ]
    if len(matches) != 1:
        raise RepositoryCompositionError(
            f"accepted run must retain exactly one {role} artifact"
        )
    return matches[0]

def _same_identity(
    documents: Sequence[Mapping[str, object]],
    field: str,
) -> ReportingIdentityRef:
    if not documents:
        raise RepositoryCompositionError("accepted run has no retained score evidence")
    first = _reporting_identity(documents[0].get(field), f"score.{field}")
    for document in documents[1:]:
        current = _reporting_identity(document.get(field), f"score.{field}")
        if current != first:
            raise RepositoryCompositionError(
                f"retained score evidence mixes {field} identities"
            )
    return first

def _metric_availability(
    metric_registration: Mapping[str, object],
    score_document: Mapping[str, object],
    score_ref: ReportArtifactRef,
) -> AvailabilityRecord:
    state = _text(score_document.get("availability"), "score.availability")
    diagnostics = score_document.get("diagnostics", ())
    if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes)):
        details = tuple(item for item in diagnostics if isinstance(item, str) and item)
    else:
        details = ()
    reason = (
        "Retained registered score state: " + ", ".join(details)
        if details
        else f"Retained registered score state {state!r}."
    )
    exclusion_authority = None
    if state == "excluded":
        exclusion_authority = (
            _text(metric_registration.get("registration_id"), "metric.registration_id")
            + "@"
            + _text(
                metric_registration.get("registration_version"),
                "metric.registration_version",
            )
            + ":state_treatment:excluded"
        )
    try:
        return AvailabilityRecord(
            affected_kind="measurement",
            affected=_text(metric_registration.get("metric_id"), "metric.metric_id"),
            state=state,
            reason=reason,
            source_identity=score_ref.artifact_id,
            exclusion_authority=exclusion_authority,
        )
    except (TypeError, ValueError) as exc:
        raise RepositoryCompositionError(
            "retained score availability is incompatible with shared reporting"
        ) from exc

def _metric_state_disposition(
    metric_registration: Mapping[str, object],
    state: str,
) -> str | None:
    raw = metric_registration.get("state_treatment", ())
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise RepositoryCompositionError("metric state_treatment must be an array")
    matches = [
        _mapping(item, "metric state_treatment")
        for item in raw
        if isinstance(item, Mapping) and item.get("state") == state
    ]
    if len(matches) > 1:
        raise RepositoryCompositionError(
            f"metric state {state!r} has ambiguous registered treatment"
        )
    if not matches:
        return None
    return _text(matches[0].get("disposition"), f"metric state {state}.disposition")

def _report_dimensions(
    retained_run: AcceptedRun,
    metric_registration: Mapping[str, object],
) -> tuple[
    ObservationCounts,
    tuple[ObservationMatrixEntry, ...],
    tuple[CaseResultEntry, ...],
    tuple[TreatmentSummary, ...],
    tuple[Mapping[str, object], ...],
]:
    retained_run.revalidate()
    observations = _retained_json_documents(
        retained_run,
        retained_run.treatment_observations,
        role="treatment_observation",
    )
    scores = _retained_json_documents(
        retained_run,
        retained_run.score_artifacts,
        role="score_artifact",
    )
    if len(observations) != len(scores):
        raise RepositoryCompositionError(
            "production reporting requires one retained registered score per observation"
        )

    metric_registration_id = _text(
        metric_registration.get("registration_id"),
        "metric.registration_id",
    )
    metric_registration_version = _text(
        metric_registration.get("registration_version"),
        "metric.registration_version",
    )
    metric_id = _text(metric_registration.get("metric_id"), "metric.metric_id")
    metric_version = _text(metric_registration.get("metric_version"), "metric.metric_version")

    score_by_observation: dict[str, tuple[object, Mapping[str, object]]] = {}
    for record, score in scores:
        if (
            score.get("accepted_generation_id") != retained_run.generation_id
            or score.get("accepted_snapshot_id") != retained_run.accepted_snapshot_id
            or score.get("execution_boundary_fingerprint")
            != retained_run.execution_boundary_fingerprint
        ):
            raise RepositoryCompositionError(
                "retained score evidence differs from accepted run identity"
            )
        if _reporting_identity(
            score.get("metric_registration"),
            "score.metric_registration",
        ) != ReportingIdentityRef(metric_registration_id, metric_registration_version):
            raise RepositoryCompositionError(
                "retained score evidence differs from selected metric registration"
            )
        if _reporting_identity(score.get("metric"), "score.metric") != ReportingIdentityRef(
            metric_id,
            metric_version,
        ):
            raise RepositoryCompositionError(
                "retained score evidence differs from selected metric identity"
            )
        if score.get("scoring_grain") != "repetition":
            raise RepositoryCompositionError(
                "production reporting currently requires repetition-grain retained scores"
            )
        observation_ids = tuple(
            _text(value, "score.observation_id")
            for value in _sequence(score.get("observation_ids"), "score.observation_ids")
        )
        raw_repetition_ids = _sequence(
            score.get("repetition_ids"),
            "score.repetition_ids",
        )
        repetition_ids = tuple(value for value in raw_repetition_ids if type(value) is int)
        if (
            len(observation_ids) != 1
            or len(repetition_ids) != 1
            or len(repetition_ids) != len(raw_repetition_ids)
        ):
            raise RepositoryCompositionError(
                "production reporting currently requires one observation per retained score"
            )
        observation_id = observation_ids[0]
        if observation_id in score_by_observation:
            raise RepositoryCompositionError(
                "retained score evidence duplicates an observation identity"
            )
        score_by_observation[observation_id] = (record, score)

    rows = []
    for record, observation in observations:
        if (
            observation.get("accepted_generation_id") != retained_run.generation_id
            or observation.get("execution_boundary_fingerprint")
            != retained_run.execution_boundary_fingerprint
        ):
            raise RepositoryCompositionError(
                "retained treatment evidence differs from accepted run identity"
            )
        observation_id = _text(observation.get("observation_id"), "observation_id")
        score_item = score_by_observation.get(observation_id)
        if score_item is None:
            raise RepositoryCompositionError(
                "retained observation lacks exact registered score evidence"
            )
        score_record, score = score_item
        case_id = _text(observation.get("case_id"), "case_id")
        treatment_id = _text(observation.get("treatment_id"), "treatment_id")
        repetition = observation.get("repetition")
        if type(repetition) is not int or repetition < 1:
            raise RepositoryCompositionError("retained observation repetition is invalid")
        if (
            score.get("case_id") != case_id
            or score.get("treatment_id") != treatment_id
            or tuple(_sequence(score.get("repetition_ids"), "score.repetition_ids"))
            != (repetition,)
        ):
            raise RepositoryCompositionError(
                "retained score evidence differs from its observation coordinate"
            )
        rows.append(
            (
                case_id,
                treatment_id,
                repetition,
                observation_id,
                record,
                observation,
                score_record,
                score,
            )
        )
    rows.sort(key=lambda item: (item[0], item[1], item[2], item[3]))

    observation_matrix = []
    case_results = []
    grouped: dict[str, list[tuple[Mapping[str, object], Mapping[str, object]]]] = {}
    for (
        case_id,
        treatment_id,
        repetition,
        observation_id,
        observation_record,
        observation,
        score_record,
        score,
    ) in rows:
        observation_ref = ReportArtifactRef.from_record(observation_record)
        score_ref = ReportArtifactRef.from_record(score_record)
        observation_matrix.append(
            ObservationMatrixEntry(
                observation_id=observation_id,
                request_id=_text(observation.get("request_id"), "request_id"),
                case_id=case_id,
                treatment_id=treatment_id,
                repetition_id=repetition,
                execution_boundary_fingerprint=retained_run.execution_boundary_fingerprint,
                availability=AvailabilityRecord(
                    affected_kind="evidence_role",
                    affected="treatment_observation",
                    state="retained",
                    reason="Exact finalized treatment observation is retained.",
                    source_identity=observation_ref.artifact_id,
                ),
                evidence_refs=(observation_ref,),
            )
        )
        availability = _metric_availability(
            metric_registration,
            score,
            score_ref,
        )
        value = score.get("value") if availability.state == "scored" else None
        if availability.state == "scored" and "value" not in score:
            raise RepositoryCompositionError(
                "retained scored evidence lacks its registered value"
            )
        case_results.append(
            CaseResultEntry(
                case_id=case_id,
                treatment_id=treatment_id,
                execution_boundary_fingerprint=retained_run.execution_boundary_fingerprint,
                metric_registration_id=metric_registration_id,
                metric_registration_version=metric_registration_version,
                availability=availability,
                value=value,
                evidence_refs=(score_ref,),
            )
        )
        grouped.setdefault(treatment_id, []).append((observation, score))

    # The canonical case matrix has one row per case/treatment. Preserve every
    # iteration in observation_matrix and aggregate its registered rate values
    # with the same state/denominator policy used by treatment summaries.
    from dataclasses import replace
    from AgMark.shared.reporting.results import registered_rate_summary
    case_groups = {}
    for row, case_result in zip(rows, case_results):
        case_groups.setdefault((row[0], row[1]), []).append((row[-1], case_result))
    case_results = []
    for items in case_groups.values():
        if len(items) == 1:
            case_results.append(items[0][1])
            continue
        aggregate = registered_rate_summary([score for score, _ in items], metric_registration)
        first = items[0][1]
        availability = replace(first.availability,
            state=aggregate.get("availability", "scored" if aggregate["denominator"] else "unavailable"),
            exclusion_authority=None,
            reason=(f"Registered mean across {aggregate['evaluated_observations']} evaluated repetitions; "
                    "each repetition retains its score evidence and companion counts."))
        case_results.append(replace(first, availability=availability, value=aggregate['value'],
            evidence_refs=tuple(ref for _, result in items for ref in result.evidence_refs)))

    rate = _mapping(
        metric_registration.get("numerator_denominator"),
        "metric.numerator_denominator",
    )
    if rate.get("uses_rate") is not True:
        raise RepositoryCompositionError(
            "production reporting currently requires a registered rate primary metric"
        )

    treatment_summaries = []
    non_scorable_states = {
        "unavailable",
        "not_applicable",
        "non_comparable",
        "completed_non_scorable",
        "invalid",
    }
    for treatment_id in sorted(grouped):
        items = grouped[treatment_id]
        planned = len(items)
        completed = sum(
            1
            for observation, _score in items
            if observation.get("terminal_status") == "completed"
        )
        failed_observations = sum(
            1
            for observation, score in items
            if observation.get("terminal_status") in {"failed", "timed_out", "cancelled"}
            or score.get("availability") == "failed"
        )
        missing = sum(
            1 for _observation, score in items
            if score.get("availability") == "missing"
        )
        excluded = sum(
            1 for _observation, score in items
            if score.get("availability") == "excluded"
        )
        non_scorable = sum(
            1
            for _observation, score in items
            if score.get("availability") in non_scorable_states
        )
        scorable = sum(
            1
            for _observation, score in items
            if score.get("availability") == "scored"
        )
        registered_summary = registered_rate_summary([score for _, score in items], metric_registration)
        numerator = registered_summary["numerator"] or 0
        denominator = registered_summary["denominator"] or 0

        if denominator:
            summary_state = "scored"
            summary_value: object | None = numerator / denominator
            summary_numerator: int | float | None = numerator
            summary_denominator: int | None = denominator
            summary_reason = (
                "Registered mean of repetition means with equal case weight; "
                "the denominator counts cases, not fields or repetitions."
                if registered_summary.get("denominator_unit") == "cases"
                else "Registered retained score evidence supports an observation-rate summary."
            )
        else:
            summary_state = registered_summary.get("availability", "unavailable")
            summary_value = None
            summary_numerator = None
            summary_denominator = None
            summary_reason = (
                "Retained score availability does not authorize a registered numeric summary."
            )
        treatment_summaries.append(
            TreatmentSummary(
                treatment_id=treatment_id,
                metric_registration_id=metric_registration_id,
                metric_registration_version=metric_registration_version,
                availability=AvailabilityRecord(
                    affected_kind="measurement",
                    affected=metric_id,
                    state=summary_state,
                    reason=summary_reason,
                    source_identity=(
                        f"{metric_registration_id}@{metric_registration_version}:"
                        f"{treatment_id}"
                    ),
                ),
                planned=planned,
                finalized=planned,
                completed=completed,
                scorable=scorable,
                failed=failed_observations,
                missing=missing,
                excluded=excluded,
                non_scorable=non_scorable,
                numerator=summary_numerator,
                denominator=summary_denominator,
                value=summary_value,
            )
        )

    failed = sum(
        1
        for _case, _treatment, _rep, _obs_id, _record, observation, _score_record, score in rows
        if observation.get("terminal_status") in {"failed", "timed_out", "cancelled"}
        or score.get("availability") == "failed"
    )
    missing = sum(
        1
        for _case, _treatment, _rep, _obs_id, _record, _observation, _score_record, score in rows
        if score.get("availability") == "missing"
    )
    excluded = sum(
        1
        for _case, _treatment, _rep, _obs_id, _record, _observation, _score_record, score in rows
        if score.get("availability") == "excluded"
    )
    non_scorable = sum(
        1
        for _case, _treatment, _rep, _obs_id, _record, _observation, _score_record, score in rows
        if score.get("availability") in non_scorable_states
    )
    counts = ObservationCounts(
        planned=len(rows),
        finalized=len(rows),
        completed=sum(
            1
            for _case, _treatment, _rep, _obs_id, _record, observation, _score_record, _score in rows
            if observation.get("terminal_status") == "completed"
        ),
        scored=sum(
            1
            for _case, _treatment, _rep, _obs_id, _record, _observation, _score_record, score in rows
            if score.get("availability") == "scored"
        ),
        failed=failed,
        missing=missing,
        excluded=excluded,
        non_scorable=non_scorable,
    )
    return (
        counts,
        tuple(observation_matrix),
        tuple(case_results),
        tuple(treatment_summaries),
        tuple(row[-1] for row in rows),
    )

def _report_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _report_request_from_accepted(
    authority: RepositoryApplicationAuthority,
    retained_run: AcceptedRun,
) -> ApplicationReportRequest:
    if type(retained_run) is not AcceptedRun:
        raise TypeError("retained_run must be an AcceptedRun")
    retained_run.revalidate()

    scoring_documents = tuple(
        document
        for _record, document in _retained_json_documents(
            retained_run,
            retained_run.score_artifacts,
            role="score_artifact",
        )
    )
    benchmark = _same_identity(scoring_documents, "benchmark")
    case_set = _same_identity(scoring_documents, "case_set")
    treatment_set = _same_identity(scoring_documents, "treatment_set")

    benchmark_runtime = IdentityRef.from_value(
        benchmark.to_dict(),
        field="benchmark",
    )
    candidate = _exact_benchmark_candidate(authority, benchmark_runtime)
    registration = _mapping(candidate.registration, "benchmark registration")
    selected = _selected_authority(registration)
    package_root = candidate.package_root
    _package_directory(authority.repository_root, package_root)
    selected_case_set, _case_set_document = _resource(
        authority.repository_root,
        registration,
        _mapping(selected.get("case_set"), "selected case set"),
        "case_set",
    )
    selected_treatment_set, _treatment_set_document = _resource(
        authority.repository_root,
        registration,
        _mapping(selected.get("treatment_set"), "selected treatment set"),
        "treatment_set",
    )
    if case_set.to_dict() != ReportingIdentityRef(
        selected_case_set.id,
        selected_case_set.version,
        sha256=selected_case_set.sha256,
        reference=selected_case_set.reference,
    ).to_dict():
        raise RepositoryCompositionError(
            "retained score case-set identity differs from registered authority"
        )
    if treatment_set.to_dict() != ReportingIdentityRef(
        selected_treatment_set.id,
        selected_treatment_set.version,
        sha256=selected_treatment_set.sha256,
        reference=selected_treatment_set.reference,
    ).to_dict():
        raise RepositoryCompositionError(
            "retained score treatment-set identity differs from registered authority"
        )

    scoring = _scoring_definition(
        authority.repository_root,
        package_root,
        registration,
        selected,
    )
    metric_registration = _mapping(
        scoring.metric_registration,
        "metric registration",
    )
    scorer = _mapping(
        metric_registration.get("scorer_or_annotation"),
        "metric scorer",
    )
    registered_metric = RegisteredReportMetric(
        registration=metric_registration,
        scorer=ReportingIdentityRef(
            _text(scorer.get("procedure_id"), "metric scorer procedure_id"),
            _text(scorer.get("version"), "metric scorer version"),
        ),
        scoring_contracts=(
            ReportingIdentityRef(
                SCORER_INVOCATION_CONTRACT_ID,
                SCORER_INVOCATION_CONTRACT_VERSION,
            ),
        ),
    )
    primary = ReportingIdentityRef(
        _text(metric_registration.get("metric_id"), "metric.metric_id"),
        _text(metric_registration.get("metric_version"), "metric.metric_version"),
    )
    comparison_track_id = _text(
        metric_registration.get("comparison_track_id"),
        "metric.comparison_track_id",
    )

    config_artifact, report_configuration = _report_configuration(
        authority.repository_root,
        registration,
        selected,
    )
    counts, observation_matrix, case_results, summaries, score_documents = (
        _report_dimensions(
            retained_run,
            metric_registration,
        )
    )
    if _same_identity(score_documents, "benchmark") != benchmark:
        raise RepositoryCompositionError("retained reporting benchmark identity changed")

    boundary = ReportArtifactRef.from_record(
        _single_retained_record(retained_run, "execution_boundary")
    )
    expected_metric_record_id = (
        "metric-registration:"
        + registered_metric.registration_id
        + "@"
        + registered_metric.registration_version
    )
    metric_records = [
        record
        for record in retained_run.artifact_index.artifacts
        if record.role == "metric_registration"
        and record.artifact_id == expected_metric_record_id
    ]
    if len(metric_records) != 1:
        raise RepositoryCompositionError(
            "accepted run lacks exact retained selected metric authority"
        )

    evidence_preimage = json.dumps(
        [
            {
                "artifact_id": record.artifact_id,
                "sha256": record.sha256,
                "reference": record.reference,
            }
            for record in sorted(
                retained_run.artifact_index.artifacts,
                key=lambda value: (value.artifact_id, value.sha256, value.reference),
            )
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    evidence_set_id = "evidence-set:" + sha256(evidence_preimage).hexdigest()
    report_seed = (
        retained_run.generation_id
        + "\x00"
        + _text(report_configuration.get("registration_id"), "report configuration id")
        + "\x00"
        + _text(
            report_configuration.get("registration_version"),
            "report configuration version",
        )
    ).encode("utf-8")
    report_digest = sha256(report_seed).hexdigest()
    report_id = "report:" + report_digest
    manifest_id = "report-manifest:" + report_digest
    base_reference = "reports/" + report_digest
    registered_extensions = dict(
        _mapping(report_configuration.get("extensions"), "report configuration extensions")
    )
    registered_extensions[_REPORT_SELECTION_EXTENSION] = {
        "configuration": {
            "id": report_configuration["registration_id"],
            "version": report_configuration["registration_version"],
            "sha256": _text(
                config_artifact.get("sha256"),
                "report_configuration.sha256",
            ),
            "reference": _text(
                config_artifact.get("reference"),
                "report_configuration.reference",
            ),
        },
    }
    observation_documents = tuple(
        document
        for _record, document in _retained_json_documents(
            retained_run,
            retained_run.treatment_observations,
            role="treatment_observation",
        )
    )
    has_deviations = any(
        bool(_sequence(document.get("deviations"), "observation.deviations"))
        for document in observation_documents
    )

    return ApplicationReportRequest(
        generation_id=retained_run.generation_id,
        execution_boundary=boundary,
        benchmark=benchmark,
        case_set=case_set,
        treatment_set=treatment_set,
        comparison_track_id=comparison_track_id,
        primary_endpoint=primary,
        metrics=(registered_metric,),
        observation_counts=counts,
        observation_matrix=observation_matrix,
        case_result_matrix=case_results,
        treatment_summaries=summaries,
        report_id=report_id,
        report_version=_text(
            report_configuration.get("registration_version"),
            "report configuration version",
        ),
        status="complete_with_deviations" if has_deviations else "complete",
        sections={
            name: ReportSection(availability="available")
            for name in REQUIRED_REPORT_SECTIONS
        },
        report_manifest_id=manifest_id,
        generated_at=_report_timestamp(),
        input_evidence_set_id=evidence_set_id,
        generator=_REPORT_GENERATOR,
        procedure_id=_REPORT_PROCEDURE_ID,
        procedure_version=_REPORT_PROCEDURE_VERSION,
        command_or_procedure=(
            "deterministic shared report projection from exact retained accepted evidence"
        ),
        report_reference=base_reference + "/report.json",
        canonical_evidence_reference=base_reference + "/canonical-evidence.json",
        human_reference=base_reference + "/report.md",
        manifest_reference=base_reference + "/report-manifest.json",
        extensions=registered_extensions,
        extension_evaluator=_registered_report_evaluator(
            authority.repository_root, candidate, selected, config_artifact),
    )
