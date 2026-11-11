"""Cross-artifact lifecycle validation for accepted benchmark generations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from .catalog import validate_exact_schema_identity
from .core import SchemaIdentity, ValidationIssue, sha256_bytes


RUN_PLAN_SCHEMA = SchemaIdentity("arcgrav.shared.schema.run-plan", "1.0.0")
GOLDEN_OBSERVATION_SCHEMA = SchemaIdentity("arcgrav.shared.schema.golden-observation", "2.0.0")
TREATMENT_OBSERVATION_SCHEMA = SchemaIdentity("arcgrav.shared.schema.treatment-observation", "1.0.0")
SCORE_ARTIFACT_SCHEMA = SchemaIdentity("arcgrav.shared.schema.score-artifact", "1.0.0")
RUN_OUTCOME_SCHEMA = SchemaIdentity("arcgrav.shared.schema.run-outcome", "1.0.0")
_ORCHESTRATION_EXECUTION_WINDOW = "arcgrav.shared.runtime.orchestration:execution-window"
_GUARD = object()


@dataclass(frozen=True, init=False)
class LifecycleValidationOutcome:
    """Opaque lifecycle authority bound to one exact terminal outcome."""

    source_id: str
    generation_id: str
    run_outcome_sha256: str
    issues: tuple[ValidationIssue, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by validate_lifecycle_evidence_outcome")

    @property
    def valid(self) -> bool:
        return (
            getattr(self, "_guard", None) is _GUARD
            and isinstance(getattr(self, "issues", None), tuple)
            and not self.issues
        )

    def matches(self, run_outcome: Mapping[str, Any], *, source_id: str) -> bool:
        _source_id(source_id)
        return (
            self.valid
            and source_id == self.source_id
            and _mapping_sha256(run_outcome) == self.run_outcome_sha256
        )


def validate_lifecycle_evidence(
    *,
    run_plan: Mapping[str, Any],
    plan_completed_at: str,
    accepted_at: str,
    run_outcome: Mapping[str, Any],
    golden_observation: Mapping[str, Any] | None = None,
    golden_observations: Sequence[Mapping[str, Any]] = (),
    treatment_observations: Sequence[Mapping[str, Any]] = (),
    score_artifacts: Sequence[Mapping[str, Any]] = (),
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate planning, chronology, matrix reconciliation, and terminal separation."""

    _source_id(source_id)
    if not isinstance(run_plan, Mapping) or not isinstance(run_outcome, Mapping):
        raise TypeError("run_plan and run_outcome must be mappings")
    if golden_observation is not None and not isinstance(golden_observation, Mapping):
        raise TypeError("golden_observation must be a mapping")
    if isinstance(golden_observations, (str, bytes, bytearray)):
        raise TypeError("golden_observations must be a sequence of mappings")
    golden_values = tuple(golden_observations)
    if any(not isinstance(value, Mapping) for value in golden_values):
        raise TypeError("golden_observations must contain mappings")
    if golden_observation is not None and golden_values:
        raise ValueError(
            "provide either golden_observation or golden_observations, not both"
        )
    if golden_observation is not None:
        golden_values = (golden_observation,)

    issues: list[ValidationIssue] = []
    issues.extend(validate_exact_schema_identity(run_plan, expected=RUN_PLAN_SCHEMA, source_id=f"{source_id}:run-plan"))
    issues.extend(validate_exact_schema_identity(run_outcome, expected=RUN_OUTCOME_SCHEMA, source_id=f"{source_id}:run-outcome"))

    plan_time = _time(plan_completed_at, issues, source_id, "/chronology/plan_completed_at", "plan completion")
    accepted_time = _time(accepted_at, issues, source_id, "/chronology/accepted_at", "acceptance")
    if plan_time and accepted_time and plan_time > accepted_time:
        _add(issues, "LIFECYCLE_PLAN_AFTER_ACCEPTANCE", source_id, "/chronology", "complete planning must precede acceptance")

    generation = run_outcome.get("generation_id")
    if not isinstance(generation, str) or not generation:
        _add(issues, "LIFECYCLE_GENERATION_ID_INVALID", source_id, "/run_outcome/generation_id", "terminal generation_id must be non-empty")
    boundary = run_plan.get("execution_boundary_fingerprint")
    if boundary != run_outcome.get("execution_boundary_fingerprint"):
        _add(issues, "LIFECYCLE_EXECUTION_BOUNDARY_MISMATCH", source_id, "/run_outcome/execution_boundary_fingerprint", "plan and outcome must bind the same boundary")

    plan_ref = run_outcome.get("run_plan")
    if not isinstance(plan_ref, Mapping):
        _add(issues, "LIFECYCLE_RUN_PLAN_REFERENCE_MISSING", source_id, "/run_outcome/run_plan", "terminal outcome must identify the accepted plan")
    else:
        if plan_ref.get("artifact_id") != run_plan.get("run_plan_id"):
            _add(issues, "LIFECYCLE_RUN_PLAN_ID_MISMATCH", source_id, "/run_outcome/run_plan/artifact_id", "run-plan identity mismatch")
        if plan_ref.get("sha256") != run_plan.get("plan_sha256"):
            _add(issues, "LIFECYCLE_RUN_PLAN_HASH_MISMATCH", source_id, "/run_outcome/run_plan/sha256", "run-plan hash mismatch")

    slots = _plan_slots(run_plan, issues, source_id)
    contracts = _contracts(run_plan.get("contracts"))
    golden_completed_times: list[datetime] = []
    golden_admitted = run_plan.get("golden_required") is not True

    if golden_values:
        admitted_values: list[bool] = []
        singular = golden_observation is not None and len(golden_values) == 1
        for index, current_golden in enumerate(golden_values):
            pointer = "/golden_observation" if singular else f"/golden_observations/{index}"
            issues.extend(
                validate_exact_schema_identity(
                    current_golden,
                    expected=GOLDEN_OBSERVATION_SCHEMA,
                    source_id=f"{source_id}:golden:{index}",
                )
            )
            if current_golden.get("accepted_generation_id") != generation:
                _add(issues, "LIFECYCLE_GOLDEN_GENERATION_MISMATCH", source_id, f"{pointer}/accepted_generation_id", "golden evidence must bind the terminal generation")
            if current_golden.get("execution_boundary_fingerprint") != boundary:
                _add(issues, "LIFECYCLE_GOLDEN_BOUNDARY_MISMATCH", source_id, f"{pointer}/execution_boundary_fingerprint", "golden evidence must bind the accepted boundary")
            _contract_check(current_golden.get("contract"), contracts, issues, source_id, f"{pointer}/contract")
            started = _time(current_golden.get("started_at"), issues, source_id, f"{pointer}/started_at", "golden start", optional=True)
            completed = _time(current_golden.get("completed_at"), issues, source_id, f"{pointer}/completed_at", "golden completion", optional=True)
            if completed is not None:
                golden_completed_times.append(completed)
            if accepted_time and started and started < accepted_time:
                _add(issues, "LIFECYCLE_GOLDEN_BEFORE_ACCEPTANCE", source_id, f"{pointer}/started_at", "golden execution must not precede acceptance")
            if started and completed and completed < started:
                _add(issues, "LIFECYCLE_GOLDEN_CHRONOLOGY_INVALID", source_id, f"{pointer}/completed_at", "golden completion precedes start")
            if current_golden.get("admission_state") == "admitted" and completed is None:
                _add(issues, "LIFECYCLE_GOLDEN_COMPLETION_MISSING", source_id, f"{pointer}/completed_at", "admitted golden authority requires completion time")
            output = current_golden.get("output")
            admitted_values.append(
                current_golden.get("admission_state") == "admitted"
                and current_golden.get("status") == "completed"
                and isinstance(output, Mapping)
                and output.get("availability") == "retained"
                and completed is not None
            )
        golden_admitted = all(admitted_values)
    elif run_plan.get("golden_required") is True:
        _add(issues, "LIFECYCLE_GOLDEN_EVIDENCE_MISSING", source_id, "/golden_observations", "required golden authority is missing")

    golden_completed = max(golden_completed_times) if golden_completed_times else None

    observed: set[str] = set()
    request_ids: set[str] = set()
    terminal_times: list[datetime] = []
    treatment_started = bool(treatment_observations)
    for index, obs in enumerate(treatment_observations):
        pointer = f"/treatment_observations/{index}"
        if not isinstance(obs, Mapping):
            _add(issues, "LIFECYCLE_TREATMENT_OBSERVATION_INVALID", source_id, pointer, "treatment observation must be an object")
            continue
        issues.extend(validate_exact_schema_identity(obs, expected=TREATMENT_OBSERVATION_SCHEMA, source_id=f"{source_id}:treatment:{index}"))
        oid, rid = obs.get("observation_id"), obs.get("request_id")
        if isinstance(oid, str) and oid:
            if oid in observed:
                _add(issues, "LIFECYCLE_TREATMENT_OBSERVATION_ID_AMBIGUOUS", source_id, f"{pointer}/observation_id", "observation_id is duplicated")
            observed.add(oid)
        if isinstance(rid, str) and rid:
            if rid in request_ids:
                _add(issues, "LIFECYCLE_TREATMENT_REQUEST_ID_AMBIGUOUS", source_id, f"{pointer}/request_id", "request_id is duplicated")
            request_ids.add(rid)
        if obs.get("accepted_generation_id") != generation:
            _add(issues, "LIFECYCLE_TREATMENT_GENERATION_MISMATCH", source_id, f"{pointer}/accepted_generation_id", "treatment evidence must bind the terminal generation")
        if obs.get("execution_boundary_fingerprint") != boundary:
            _add(issues, "LIFECYCLE_TREATMENT_BOUNDARY_MISMATCH", source_id, f"{pointer}/execution_boundary_fingerprint", "treatment evidence must bind the accepted boundary")
        _contract_check(obs.get("contract"), contracts, issues, source_id, f"{pointer}/contract")
        planned = slots.get(oid) if isinstance(oid, str) else None
        if planned:
            for field, expected in zip(("request_id", "case_id", "treatment_id", "repetition", "execution_boundary_fingerprint"), planned):
                if obs.get(field) != expected:
                    _add(issues, "LIFECYCLE_TREATMENT_PLAN_MISMATCH", source_id, f"{pointer}/{field}", "retained treatment field differs from accepted plan")
        attempts = obs.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            _add(issues, "LIFECYCLE_TREATMENT_ATTEMPTS_MISSING", source_id, f"{pointer}/attempts", "treatment evidence requires attempt chronology")
            continue
        execution_window: tuple[datetime | None, datetime | None] | None = None
        for ai, attempt in enumerate(attempts):
            if not isinstance(attempt, Mapping):
                _add(issues, "LIFECYCLE_TREATMENT_ATTEMPT_INVALID", source_id, f"{pointer}/attempts/{ai}", "attempt must be an object")
                continue
            raw_start = attempt.get("started_at")
            raw_done = attempt.get("completed_at")
            start = _time(raw_start, issues, source_id, f"{pointer}/attempts/{ai}/started_at", "treatment start", optional=raw_start is None)
            done = _time(raw_done, issues, source_id, f"{pointer}/attempts/{ai}/completed_at", "treatment completion", optional=raw_done is None)
            if len(attempts) == 1 and (raw_start is None or raw_done is None):
                if execution_window is None:
                    execution_window = _orchestration_execution_window(
                        obs,
                        issues=issues,
                        source_id=source_id,
                        pointer=pointer,
                    )
                window_start, window_done = execution_window
                if raw_start is None:
                    start = window_start
                if raw_done is None:
                    done = window_done
            if start is None:
                _add(issues, "LIFECYCLE_TIMESTAMP_MISSING", source_id, f"{pointer}/attempts/{ai}/started_at", "treatment start timestamp must be retained")
            if done is None:
                _add(issues, "LIFECYCLE_TIMESTAMP_MISSING", source_id, f"{pointer}/attempts/{ai}/completed_at", "treatment completion timestamp must be retained")
            if start and accepted_time and start < accepted_time:
                _add(issues, "LIFECYCLE_TREATMENT_BEFORE_ACCEPTANCE", source_id, f"{pointer}/attempts/{ai}/started_at", "treatment starts before acceptance")
            if start and run_plan.get("golden_required") is True and (golden_completed is None or start < golden_completed):
                _add(issues, "LIFECYCLE_TREATMENT_BEFORE_GOLDEN_AUTHORITY", source_id, f"{pointer}/attempts/{ai}/started_at", "treatment starts before required golden completion")
            if start and done and done < start:
                _add(issues, "LIFECYCLE_TREATMENT_CHRONOLOGY_INVALID", source_id, f"{pointer}/attempts/{ai}/completed_at", "treatment completion precedes start")
            if done:
                terminal_times.append(done)

    if run_plan.get("golden_required") is True and not golden_admitted:
        if treatment_observations:
            _add(issues, "LIFECYCLE_TREATMENT_BEFORE_GOLDEN_AUTHORITY", source_id, "/treatment_observations", "blocked golden gate must produce zero treatment observations")
        if score_artifacts:
            _add(issues, "LIFECYCLE_SCORE_BEFORE_GOLDEN_AUTHORITY", source_id, "/score_artifacts", "scoring cannot replace required golden authority")
        if run_outcome.get("status") != "blocked":
            _add(issues, "LIFECYCLE_GOLDEN_FAILURE_NOT_BLOCKED", source_id, "/run_outcome/status", "failed golden authority must terminate blocked")

    planned_ids = set(slots)
    if run_outcome.get("status") == "accepted" or treatment_started:
        for oid in sorted(planned_ids - observed):
            _add(issues, "LIFECYCLE_PLANNED_OBSERVATION_MISSING", source_id, "/treatment_observations", f"planned observation {oid!r} is missing")
        for oid in sorted(observed - planned_ids):
            _add(issues, "LIFECYCLE_UNPLANNED_OBSERVATION", source_id, "/treatment_observations", f"observation {oid!r} is not in the accepted plan")

    for index, score in enumerate(score_artifacts):
        pointer = f"/score_artifacts/{index}"
        if not isinstance(score, Mapping):
            _add(issues, "LIFECYCLE_SCORE_ARTIFACT_INVALID", source_id, pointer, "score artifact must be an object")
            continue
        issues.extend(validate_exact_schema_identity(score, expected=SCORE_ARTIFACT_SCHEMA, source_id=f"{source_id}:score:{index}"))
        if score.get("accepted_generation_id") != generation:
            _add(issues, "LIFECYCLE_SCORE_GENERATION_MISMATCH", source_id, f"{pointer}/accepted_generation_id", "score must bind the terminal generation")
        if score.get("execution_boundary_fingerprint") != boundary:
            _add(issues, "LIFECYCLE_SCORE_BOUNDARY_MISMATCH", source_id, f"{pointer}/execution_boundary_fingerprint", "score must bind the accepted boundary")
        ids = score.get("observation_ids")
        if isinstance(ids, list):
            for oid in ids:
                if oid not in observed:
                    _add(issues, "LIFECYCLE_SCORE_INPUT_UNKNOWN", source_id, f"{pointer}/observation_ids", f"score input {oid!r} lacks retained observation authority")

    status = run_outcome.get("status")
    if status == "accepted":
        if not isinstance(run_outcome.get("artifact_index"), list) or not run_outcome["artifact_index"]:
            _add(issues, "LIFECYCLE_ACCEPTED_ARTIFACT_INDEX_MISSING", source_id, "/run_outcome/artifact_index", "accepted outcome requires artifact index")
        if "blocked_manifest" in run_outcome:
            _add(issues, "LIFECYCLE_TERMINAL_AUTHORITY_MIXED", source_id, "/run_outcome/blocked_manifest", "accepted and blocked authority must remain distinct")
    elif status == "blocked":
        if not isinstance(run_outcome.get("blocked_manifest"), Mapping):
            _add(issues, "LIFECYCLE_BLOCKED_MANIFEST_MISSING", source_id, "/run_outcome/blocked_manifest", "blocked outcome requires blocked manifest")
        if "artifact_index" in run_outcome:
            _add(issues, "LIFECYCLE_TERMINAL_AUTHORITY_MIXED", source_id, "/run_outcome/artifact_index", "blocked outcome cannot publish accepted artifact index")
    else:
        _add(issues, "LIFECYCLE_TERMINAL_STATUS_INVALID", source_id, "/run_outcome/status", "status must be accepted or blocked")

    finalized = _time(run_outcome.get("finalized_at"), issues, source_id, "/run_outcome/finalized_at", "finalization")
    if finalized and accepted_time and finalized < accepted_time:
        _add(issues, "LIFECYCLE_FINALIZED_BEFORE_ACCEPTANCE", source_id, "/run_outcome/finalized_at", "finalization precedes acceptance")
    for done in golden_completed_times + terminal_times:
        if finalized and done and finalized < done:
            _add(issues, "LIFECYCLE_FINALIZED_BEFORE_EVIDENCE", source_id, "/run_outcome/finalized_at", "finalization precedes terminal evidence")
            break
    return _norm(issues)


def validate_lifecycle_evidence_outcome(**kwargs: Any) -> LifecycleValidationOutcome:
    """Validate lifecycle evidence and mint exact terminal authority."""

    issues = validate_lifecycle_evidence(**kwargs)
    run_outcome = kwargs["run_outcome"]
    value = object.__new__(LifecycleValidationOutcome)
    for name, item in (
        ("source_id", kwargs["source_id"]),
        ("generation_id", run_outcome.get("generation_id")),
        ("run_outcome_sha256", _mapping_sha256(run_outcome)),
        ("issues", issues),
        ("_guard", _GUARD),
    ):
        object.__setattr__(value, name, item)
    return value


def _plan_slots(run_plan: Mapping[str, Any], issues: list[ValidationIssue], source_id: str) -> dict[str, tuple[object, ...]]:
    raw = run_plan.get("observations")
    if not isinstance(raw, list) or not raw:
        _add(issues, "LIFECYCLE_PLAN_MATRIX_INVALID", source_id, "/run_plan/observations", "accepted plan requires a non-empty matrix")
        return {}
    repetitions = run_plan.get("repetitions")
    boundary = run_plan.get("execution_boundary_fingerprint")
    slots: dict[str, tuple[object, ...]] = {}
    requests: set[str] = set()
    matrix: set[tuple[str, str, int]] = set()
    cases: set[str] = set()
    treatments: set[str] = set()
    for index, item in enumerate(raw):
        pointer = f"/run_plan/observations/{index}"
        if not isinstance(item, Mapping):
            _add(issues, "LIFECYCLE_PLAN_OBSERVATION_INVALID", source_id, pointer, "planned observation must be an object")
            continue
        rid, oid, cid, tid, rep = (item.get(k) for k in ("request_id", "observation_id", "case_id", "treatment_id", "repetition"))
        if not all(isinstance(v, str) and v for v in (rid, oid, cid, tid)) or not isinstance(rep, int) or isinstance(rep, bool):
            _add(issues, "LIFECYCLE_PLAN_OBSERVATION_INVALID", source_id, pointer, "planned observation identities and repetition are invalid")
            continue
        if isinstance(repetitions, int) and not isinstance(repetitions, bool) and not 1 <= rep <= repetitions:
            _add(issues, "LIFECYCLE_PLAN_REPETITION_OUT_OF_RANGE", source_id, f"{pointer}/repetition", "repetition lies outside declared intent")
        if item.get("execution_boundary_fingerprint") != boundary:
            _add(issues, "LIFECYCLE_PLAN_BOUNDARY_MISMATCH", source_id, f"{pointer}/execution_boundary_fingerprint", "planned observation boundary mismatch")
        if oid in slots:
            _add(issues, "LIFECYCLE_PLAN_OBSERVATION_ID_AMBIGUOUS", source_id, f"{pointer}/observation_id", "observation_id is duplicated")
        else:
            slots[oid] = (rid, cid, tid, rep, item.get("execution_boundary_fingerprint"))
        if rid in requests:
            _add(issues, "LIFECYCLE_PLAN_REQUEST_ID_AMBIGUOUS", source_id, f"{pointer}/request_id", "request_id is duplicated")
        requests.add(rid)
        key = (cid, tid, rep)
        if key in matrix:
            _add(issues, "LIFECYCLE_PLAN_MATRIX_SLOT_AMBIGUOUS", source_id, pointer, "matrix slot is duplicated")
        matrix.add(key)
        cases.add(cid)
        treatments.add(tid)
    if isinstance(repetitions, int) and not isinstance(repetitions, bool) and repetitions >= 1 and cases and treatments:
        expected = {(c, t, r) for c in cases for t in treatments for r in range(1, repetitions + 1)}
        if matrix != expected:
            _add(issues, "LIFECYCLE_PLAN_MATRIX_INCOMPLETE", source_id, "/run_plan/observations", "case x treatment x repetition x boundary matrix is incomplete")
    return slots


def _contracts(value: object) -> set[tuple[str, str]]:
    if not isinstance(value, list):
        return set()
    return {
        (item["id"], item["version"])
        for item in value
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str) and item.get("id")
        and isinstance(item.get("version"), str) and item.get("version")
    }


def _orchestration_execution_window(
    observation: Mapping[str, Any],
    *,
    issues: list[ValidationIssue],
    source_id: str,
    pointer: str,
) -> tuple[datetime | None, datetime | None]:
    extensions = observation.get("extensions")
    window = (
        extensions.get(_ORCHESTRATION_EXECUTION_WINDOW)
        if isinstance(extensions, Mapping)
        else None
    )
    if not isinstance(window, Mapping):
        return None, None
    started_at = _time(
        window.get("started_at"),
        issues,
        source_id,
        pointer + "/extensions/orchestration-execution-window/started_at",
        "orchestration treatment start",
        optional=True,
    )
    completed_at = _time(
        window.get("completed_at"),
        issues,
        source_id,
        pointer + "/extensions/orchestration-execution-window/completed_at",
        "orchestration treatment completion",
        optional=True,
    )
    if started_at and completed_at and completed_at < started_at:
        _add(
            issues,
            "LIFECYCLE_TREATMENT_CHRONOLOGY_INVALID",
            source_id,
            pointer + "/extensions/orchestration-execution-window",
            "orchestration treatment completion precedes start",
        )
    return started_at, completed_at


def _contract_check(value: object, allowed: set[tuple[str, str]], issues: list[ValidationIssue], source_id: str, pointer: str) -> None:
    if not isinstance(value, Mapping) or (value.get("id"), value.get("version")) not in allowed:
        _add(issues, "LIFECYCLE_CONTRACT_AUTHORITY_MISMATCH", source_id, pointer, "evidence contract is not exact accepted-plan authority")


def _time(value: object, issues: list[ValidationIssue], source_id: str, pointer: str, label: str, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        _add(issues, "LIFECYCLE_TIMESTAMP_MISSING", source_id, pointer, f"{label} timestamp must be retained")
        return None
    normalized = value.replace("t", "T").replace("z", "Z")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        _add(issues, "LIFECYCLE_TIMESTAMP_INVALID", source_id, pointer, f"{label} must be offset-aware RFC 3339")
        return None
    return parsed


def _mapping_sha256(value: Mapping[str, Any]) -> str:
    try:
        data = json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("lifecycle evidence must be JSON-compatible") from exc
    return sha256_bytes(data)


def _source_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("source_id must be a non-empty string")


def _add(issues: list[ValidationIssue], code: str, source_id: str, pointer: str, message: str) -> None:
    issues.append(ValidationIssue(code=code, source_id=source_id, json_pointer=pointer, message=message))


def _norm(issues: Sequence[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


__all__ = [
    "GOLDEN_OBSERVATION_SCHEMA",
    "LifecycleValidationOutcome",
    "RUN_OUTCOME_SCHEMA",
    "RUN_PLAN_SCHEMA",
    "SCORE_ARTIFACT_SCHEMA",
    "TREATMENT_OBSERVATION_SCHEMA",
    "validate_lifecycle_evidence",
    "validate_lifecycle_evidence_outcome",
]
