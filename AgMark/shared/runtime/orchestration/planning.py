"""Canonical run planning and immutable accepted-snapshot authority."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from random import shuffle

from AgMark.shared.runtime.identity import (
    CANONICALIZATION,
    EXECUTION_BOUNDARY_SCHEMA_ID,
    EXECUTION_BOUNDARY_SCHEMA_VERSION,
    AcceptedBoundaryIdentity,
    ExecutionBoundary,
    IdentityRef,
    canonical_json_bytes,
    canonical_sha256,
)

RUN_PLAN_SCHEMA_ID = "arcgrav.shared.schema.run-plan"
RUN_PLAN_SCHEMA_VERSION = "1.0.0"
RUN_LIFECYCLE_CONTRACT_ID = "arcgrav.shared.run-lifecycle"
RUN_LIFECYCLE_CONTRACT_VERSION = "1.0.0"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXTENSION = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[^\s]+$")
_PLAN_KEYS = {
    "schema_id", "schema_version", "extensions", "run_plan_id",
    "canonicalization", "plan_sha256", "benchmark", "case_set",
    "treatment_set", "execution_boundary", "execution_boundary_fingerprint",
    "repetitions", "golden_required", "contracts", "observations",
}
_OBS_KEYS = {
    "request_id", "observation_id", "case_id", "treatment_id", "repetition",
    "execution_boundary_fingerprint", "input",
}


class PlanningError(ValueError):
    """Base class for canonical planning failures."""


class DuplicatePlanIdentityError(PlanningError):
    """A planning identity is duplicated or ambiguous."""


class IncompletePlanError(PlanningError):
    """Complete matrix authority cannot be materialized."""


class PlanIntegrityError(PlanningError):
    """Retained run-plan identity no longer matches its contents."""


class AcceptedSnapshotIntegrityError(PlanningError):
    """Accepted source or boundary authority drifted."""


@dataclass(frozen=True, slots=True)
class PlannedCaseInput:
    case_id: str
    sha256: str
    reference: str | None = None
    byte_length: int | None = None

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _sha(self.sha256, "case input sha256")
        if self.reference is not None:
            _text(self.reference, "case input reference")
            from ..identity.boundary import _retained_reference
            try:
                _retained_reference(self.reference)
            except ValueError as exc:
                raise PlanningError("case input reference must be a relative resource") from exc
        if self.byte_length is not None:
            _nonnegative_int(self.byte_length, "case input byte_length")

    def input_dict(self) -> dict[str, object]:
        value: dict[str, object] = {"sha256": self.sha256}
        if self.reference is not None:
            value["reference"] = self.reference
        if self.byte_length is not None:
            value["byte_length"] = self.byte_length
        return value


@dataclass(frozen=True, slots=True)
class PlannedObservation:
    request_id: str
    observation_id: str
    case_id: str
    treatment_id: str
    repetition: int
    execution_boundary_fingerprint: str
    input_sha256: str
    input_reference: str | None = None
    input_byte_length: int | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "observation_id", "case_id", "treatment_id"):
            _text(getattr(self, name), name)
        _positive_int(self.repetition, "repetition")
        _sha(self.execution_boundary_fingerprint, "execution_boundary_fingerprint")
        PlannedCaseInput(
            self.case_id, self.input_sha256, self.input_reference, self.input_byte_length
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "observation_id": self.observation_id,
            "case_id": self.case_id,
            "treatment_id": self.treatment_id,
            "repetition": self.repetition,
            "execution_boundary_fingerprint": self.execution_boundary_fingerprint,
            "input": PlannedCaseInput(
                self.case_id,
                self.input_sha256,
                self.input_reference,
                self.input_byte_length,
            ).input_dict(),
        }

    @classmethod
    def _from_document(cls, value: object) -> "PlannedObservation":
        if not isinstance(value, Mapping) or set(value) != _OBS_KEYS:
            raise PlanningError("planned observation fields do not match the published schema")
        input_value = value["input"]
        if not isinstance(input_value, Mapping):
            raise PlanningError("planned observation input must be an object")
        if set(input_value) - {"sha256", "reference", "byte_length"} or "sha256" not in input_value:
            raise PlanningError("planned observation input is invalid")
        return cls(
            request_id=_text(value["request_id"], "request_id"),
            observation_id=_text(value["observation_id"], "observation_id"),
            case_id=_text(value["case_id"], "case_id"),
            treatment_id=_text(value["treatment_id"], "treatment_id"),
            repetition=_positive_int(value["repetition"], "repetition"),
            execution_boundary_fingerprint=_sha(
                value["execution_boundary_fingerprint"], "execution_boundary_fingerprint"
            ),
            input_sha256=_sha(input_value["sha256"], "input.sha256"),
            input_reference=(
                None if input_value.get("reference") is None
                else _text(input_value["reference"], "input.reference")
            ),
            input_byte_length=(
                None if input_value.get("byte_length") is None
                else _nonnegative_int(input_value["byte_length"], "input.byte_length")
            ),
        )


@dataclass(frozen=True, slots=True)
class RunPlan:
    run_plan_id: str
    plan_sha256: str
    benchmark: IdentityRef
    case_set: IdentityRef
    treatment_set: IdentityRef
    execution_boundary_id: str
    execution_boundary_sha256: str
    execution_boundary_fingerprint: str
    repetitions: int
    golden_required: bool
    contracts: tuple[IdentityRef, ...]
    observations: tuple[PlannedObservation, ...]
    _canonical_bytes: bytes = field(repr=False)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    def to_dict(self) -> dict[str, object]:
        return json.loads(self._canonical_bytes.decode("utf-8"))

    def revalidate(self) -> None:
        rebuilt = _plan_from_document(self.to_dict())
        if rebuilt.canonical_bytes != self.canonical_bytes:
            raise PlanIntegrityError("run plan canonical bytes changed after construction")

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "RunPlan":
        """Reconstitute a retained canonical plan and verify its integrity identity."""
        return _plan_from_document(document)


@dataclass(frozen=True, slots=True)
class AcceptedRunSnapshot:
    accepted_snapshot_id: str
    run_plan_id: str
    plan_sha256: str
    execution_boundary_fingerprint: str
    plan_completed_at: str
    accepted_at: str
    _plan_bytes: bytes = field(repr=False)
    _accepted_boundary: AcceptedBoundaryIdentity = field(repr=False)

    def plan(self) -> RunPlan:
        return _plan_from_document(json.loads(self._plan_bytes.decode("utf-8")))

    def revalidate_authority(
        self,
        *,
        benchmark: IdentityRef | Mapping[str, object],
        case_set: IdentityRef | Mapping[str, object],
        treatment_set: IdentityRef | Mapping[str, object],
        execution_boundary: ExecutionBoundary,
    ) -> RunPlan:
        plan = self.plan()
        if (plan.run_plan_id, plan.plan_sha256, plan.execution_boundary_fingerprint) != (
            self.run_plan_id, self.plan_sha256, self.execution_boundary_fingerprint
        ):
            raise AcceptedSnapshotIntegrityError("accepted plan identity changed")
        current = (
            _source(benchmark, "benchmark"),
            _source(case_set, "case_set"),
            _source(treatment_set, "treatment_set"),
        )
        for label, expected, observed in zip(
            ("benchmark", "case_set", "treatment_set"),
            (plan.benchmark, plan.case_set, plan.treatment_set),
            current,
            strict=True,
        ):
            if expected.to_dict() != observed.to_dict():
                raise AcceptedSnapshotIntegrityError(
                    f"accepted {label} identity changed before execution"
                )
        if type(execution_boundary) is not ExecutionBoundary:
            raise AcceptedSnapshotIntegrityError("execution_boundary must be an ExecutionBoundary")
        try:
            boundary = self._accepted_boundary.revalidate(execution_boundary.to_dict())
        except Exception as exc:
            raise AcceptedSnapshotIntegrityError(
                "accepted execution-boundary authority changed before execution"
            ) from exc
        if boundary.fingerprint != plan.execution_boundary_fingerprint:
            raise AcceptedSnapshotIntegrityError("accepted boundary no longer matches the plan")
        return plan


def plan_run(
    *,
    benchmark: IdentityRef | Mapping[str, object],
    case_set: IdentityRef | Mapping[str, object],
    treatment_set: IdentityRef | Mapping[str, object],
    cases: Sequence[PlannedCaseInput],
    treatments: Sequence[str],
    repetitions: int,
    execution_boundary: ExecutionBoundary,
    golden_required: bool,
    contracts: Sequence[IdentityRef | Mapping[str, object]] = (),
    extensions: Mapping[str, object] | None = None,
) -> RunPlan:
    """Materialize the complete canonical matrix before acceptance."""

    benchmark_ref = _source(benchmark, "benchmark")
    case_set_ref = _source(case_set, "case_set")
    treatment_set_ref = _source(treatment_set, "treatment_set")
    repetitions = _positive_int(repetitions, "repetitions")
    if type(golden_required) is not bool:
        raise PlanningError("golden_required must be boolean")
    if type(execution_boundary) is not ExecutionBoundary:
        raise PlanningError("execution_boundary must be an ExecutionBoundary")
    execution_boundary.revalidate()

    case_values = tuple(cases)
    treatment_values = tuple(treatments)
    if not case_values or not treatment_values:
        raise IncompletePlanError("at least one case and treatment are required")
    if any(type(case) is not PlannedCaseInput for case in case_values):
        raise PlanningError("cases must contain PlannedCaseInput values")
    _unique((case.case_id for case in case_values), "case_id")
    _unique(treatment_values, "treatment_id")

    contract_values = [IdentityRef(RUN_LIFECYCLE_CONTRACT_ID, RUN_LIFECYCLE_CONTRACT_VERSION)]
    contract_values.extend(
        IdentityRef.from_value(value, field=f"contracts[{index}]")
        for index, value in enumerate(contracts)
    )
    contract_values.sort(key=lambda item: (item.id, item.version, item.sha256 or "", item.reference or ""))
    _unique_refs(contract_values, "contracts")

    normalized_extensions = _extensions(extensions or {})
    randomize_per_iteration = normalized_extensions.get(
        "arcgrav.runtime:randomize-per-iteration", False
    )
    if type(randomize_per_iteration) is not bool:
        raise PlanningError("randomize-per-iteration extension must be boolean")

    observations: list[PlannedObservation] = []
    for repetition in range(1, repetitions + 1):
        # Choose each round's order before acceptance; execution only follows
        # the immutable planned observation sequence.
        iteration_treatments = list(treatment_values)
        if randomize_per_iteration:
            shuffle(iteration_treatments)
        for case in case_values:
            for treatment_id in iteration_treatments:
                _text(treatment_id, "treatment_id")
                slot = {
                    "case_id": case.case_id,
                    "treatment_id": treatment_id,
                    "repetition": repetition,
                    "execution_boundary_fingerprint": execution_boundary.fingerprint,
                    "input": case.input_dict(),
                }
                request_id = "request:" + canonical_sha256(
                    {"kind": "request", **slot}
                ).removeprefix("sha256:")
                observation_id = "observation:" + canonical_sha256(
                    {
                        "kind": "treatment-observation",
                        "request_id": request_id,
                        "execution_boundary_fingerprint": execution_boundary.fingerprint,
                    }
                ).removeprefix("sha256:")
                observations.append(
                    PlannedObservation(
                        request_id,
                        observation_id,
                        case.case_id,
                        treatment_id,
                        repetition,
                        execution_boundary.fingerprint,
                        case.sha256,
                        case.reference,
                        case.byte_length,
                    )
                )

    document = _build_document(
        benchmark_ref,
        case_set_ref,
        treatment_set_ref,
        execution_boundary,
        repetitions,
        golden_required,
        tuple(contract_values),
        tuple(observations),
        normalized_extensions,
    )
    return _plan_from_document(document)


def accept_run_plan(*, plan: RunPlan, execution_boundary: ExecutionBoundary) -> AcceptedRunSnapshot:
    """Freeze one canonical plan and exact execution-boundary authority."""

    if type(plan) is not RunPlan:
        raise PlanningError("plan must be a canonical RunPlan")
    if type(execution_boundary) is not ExecutionBoundary:
        raise PlanningError("execution_boundary must be an ExecutionBoundary")
    plan.revalidate()
    execution_boundary.revalidate()
    plan_completed_at = _utc_now()
    if (
        execution_boundary.boundary_id != plan.execution_boundary_id
        or execution_boundary.canonical_sha256 != plan.execution_boundary_sha256
        or execution_boundary.fingerprint != plan.execution_boundary_fingerprint
    ):
        raise AcceptedSnapshotIntegrityError("execution boundary does not match run plan")
    accepted_boundary = AcceptedBoundaryIdentity.accept(
        accepted_identity_id="accepted-boundary:" + plan.plan_sha256.removeprefix("sha256:"),
        boundary=execution_boundary,
    )
    digest = canonical_sha256(
        {
            "kind": "accepted-run-snapshot",
            "run_plan_id": plan.run_plan_id,
            "plan_sha256": plan.plan_sha256,
            "execution_boundary_sha256": plan.execution_boundary_sha256,
            "execution_boundary_fingerprint": plan.execution_boundary_fingerprint,
            "benchmark": plan.benchmark.to_dict(),
            "case_set": plan.case_set.to_dict(),
            "treatment_set": plan.treatment_set.to_dict(),
        }
    )
    accepted_at = _utc_now()
    return AcceptedRunSnapshot(
        accepted_snapshot_id="accepted-snapshot:" + digest.removeprefix("sha256:"),
        run_plan_id=plan.run_plan_id,
        plan_sha256=plan.plan_sha256,
        execution_boundary_fingerprint=plan.execution_boundary_fingerprint,
        plan_completed_at=plan_completed_at,
        accepted_at=accepted_at,
        _plan_bytes=bytes(plan.canonical_bytes),
        _accepted_boundary=accepted_boundary,
    )


def _build_document(
    benchmark: IdentityRef,
    case_set: IdentityRef,
    treatment_set: IdentityRef,
    boundary: ExecutionBoundary,
    repetitions: int,
    golden_required: bool,
    contracts: tuple[IdentityRef, ...],
    observations: tuple[PlannedObservation, ...],
    extensions: Mapping[str, object],
) -> dict[str, object]:
    core: dict[str, object] = {
        "schema_id": RUN_PLAN_SCHEMA_ID,
        "schema_version": RUN_PLAN_SCHEMA_VERSION,
        "extensions": dict(extensions),
        "canonicalization": CANONICALIZATION,
        "benchmark": benchmark.to_dict(),
        "case_set": case_set.to_dict(),
        "treatment_set": treatment_set.to_dict(),
        "execution_boundary": {
            "artifact_id": boundary.boundary_id,
            "sha256": boundary.canonical_sha256,
            "schema": {
                "schema_id": EXECUTION_BOUNDARY_SCHEMA_ID,
                "schema_version": EXECUTION_BOUNDARY_SCHEMA_VERSION,
            },
            "availability": "retained",
        },
        "execution_boundary_fingerprint": boundary.fingerprint,
        "repetitions": repetitions,
        "golden_required": golden_required,
        "contracts": [contract.to_dict() for contract in contracts],
        "observations": [observation.to_dict() for observation in observations],
    }
    run_plan_id = "run-plan:" + canonical_sha256(core).removeprefix("sha256:")
    preimage = {**core, "run_plan_id": run_plan_id}
    return {**preimage, "plan_sha256": canonical_sha256(preimage)}


def _plan_from_document(document: object) -> RunPlan:
    if not isinstance(document, Mapping) or set(document) != _PLAN_KEYS:
        raise PlanningError("run plan fields do not match the published schema")
    if document["schema_id"] != RUN_PLAN_SCHEMA_ID or document["schema_version"] != RUN_PLAN_SCHEMA_VERSION:
        raise PlanningError("run plan schema is not supported")
    if document["canonicalization"] != CANONICALIZATION:
        raise PlanningError("run plan canonicalization is not supported")
    benchmark = _source(document["benchmark"], "benchmark")
    case_set = _source(document["case_set"], "case_set")
    treatment_set = _source(document["treatment_set"], "treatment_set")
    boundary_ref = document["execution_boundary"]
    if not isinstance(boundary_ref, Mapping) or set(boundary_ref) != {"artifact_id", "sha256", "schema", "availability"}:
        raise PlanningError("execution_boundary reference is invalid")
    schema = boundary_ref["schema"]
    if not isinstance(schema, Mapping) or schema != {
        "schema_id": EXECUTION_BOUNDARY_SCHEMA_ID,
        "schema_version": EXECUTION_BOUNDARY_SCHEMA_VERSION,
    }:
        raise PlanningError("execution_boundary schema identity is invalid")
    if boundary_ref["availability"] != "retained":
        raise PlanningError("execution_boundary must be retained")
    boundary_id = _text(boundary_ref["artifact_id"], "execution_boundary.artifact_id")
    boundary_sha = _sha(boundary_ref["sha256"], "execution_boundary.sha256")
    boundary_fp = _sha(document["execution_boundary_fingerprint"], "execution_boundary_fingerprint")
    repetitions = _positive_int(document["repetitions"], "repetitions")
    if type(document["golden_required"]) is not bool:
        raise PlanningError("golden_required must be boolean")
    extensions = _extensions(document["extensions"])
    from AgMark.shared.treatments import content_entries
    content_entries(document)
    contracts_doc = document["contracts"]
    if not isinstance(contracts_doc, list) or not contracts_doc:
        raise PlanningError("contracts must be a non-empty array")
    contracts = tuple(
        IdentityRef.from_value(value, field=f"contracts[{index}]")
        for index, value in enumerate(contracts_doc)
    )
    _unique_refs(contracts, "contracts")
    observations_doc = document["observations"]
    if not isinstance(observations_doc, list) or not observations_doc:
        raise IncompletePlanError("observations must be a non-empty matrix")
    observations = tuple(PlannedObservation._from_document(value) for value in observations_doc)
    _validate_matrix(observations, repetitions, boundary_fp)

    boundary_document = {
        "artifact_id": boundary_id,
        "sha256": boundary_sha,
        "schema": {
            "schema_id": EXECUTION_BOUNDARY_SCHEMA_ID,
            "schema_version": EXECUTION_BOUNDARY_SCHEMA_VERSION,
        },
        "availability": "retained",
    }
    core = {
        "schema_id": RUN_PLAN_SCHEMA_ID,
        "schema_version": RUN_PLAN_SCHEMA_VERSION,
        "extensions": extensions,
        "canonicalization": CANONICALIZATION,
        "benchmark": benchmark.to_dict(),
        "case_set": case_set.to_dict(),
        "treatment_set": treatment_set.to_dict(),
        "execution_boundary": boundary_document,
        "execution_boundary_fingerprint": boundary_fp,
        "repetitions": repetitions,
        "golden_required": document["golden_required"],
        "contracts": [value.to_dict() for value in contracts],
        "observations": [value.to_dict() for value in observations],
    }
    expected_id = "run-plan:" + canonical_sha256(core).removeprefix("sha256:")
    preimage = {**core, "run_plan_id": expected_id}
    expected_hash = canonical_sha256(preimage)
    if document["run_plan_id"] != expected_id or document["plan_sha256"] != expected_hash:
        raise PlanIntegrityError("run plan identity does not match canonical contents")
    canonical = canonical_json_bytes({**preimage, "plan_sha256": expected_hash})
    if canonical != canonical_json_bytes(document):
        raise PlanIntegrityError("run plan is not in canonical retained form")
    return RunPlan(
        expected_id,
        expected_hash,
        benchmark,
        case_set,
        treatment_set,
        boundary_id,
        boundary_sha,
        boundary_fp,
        repetitions,
        document["golden_required"],
        contracts,
        observations,
        canonical,
    )


def _validate_matrix(
    observations: tuple[PlannedObservation, ...], repetitions: int, boundary_fp: str
) -> None:
    requests: set[str] = set()
    observation_ids: set[str] = set()
    slots: set[tuple[str, str, int]] = set()
    cases: set[str] = set()
    treatments: set[str] = set()
    for item in observations:
        if item.execution_boundary_fingerprint != boundary_fp:
            raise PlanIntegrityError("observation boundary fingerprint changed")
        if item.request_id in requests or item.observation_id in observation_ids:
            raise DuplicatePlanIdentityError("duplicate request or observation identity")
        slot = (item.case_id, item.treatment_id, item.repetition)
        if slot in slots:
            raise DuplicatePlanIdentityError("duplicate planned matrix slot")
        requests.add(item.request_id)
        observation_ids.add(item.observation_id)
        slots.add(slot)
        cases.add(item.case_id)
        treatments.add(item.treatment_id)
    expected = {
        (case_id, treatment_id, repetition)
        for case_id in cases
        for treatment_id in treatments
        for repetition in range(1, repetitions + 1)
    }
    if slots != expected:
        raise IncompletePlanError("case x treatment x repetition x boundary matrix is incomplete")


def _source(value: object, field: str) -> IdentityRef:
    ref = IdentityRef.from_value(value, field=field)
    if ref.sha256 is None:
        raise PlanningError(f"{field} requires exact sha256 source identity")
    return ref


def _extensions(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise PlanningError("extensions must be an object")
    flags = {"arcgrav.runtime:cache-validation-replays", "arcgrav.runtime:randomize-treatment-start",
             "arcgrav.runtime:randomize-per-iteration", "arcgrav.runtime:execution-only"}
    from ...telemetry.runtime_reference import PLAN_EXTENSION, validate_runtime_advisory
    from ...treatments import CONTENT, content_entries
    if set(value) - flags - {PLAN_EXTENSION, CONTENT}:
        raise PlanningError("undeclared run-plan extensions cannot enter retained evidence")
    normalized = json.loads(canonical_json_bytes(dict(value)).decode("utf-8"))
    for key in flags & set(normalized):
        if type(normalized[key]) is not bool:
            raise PlanningError("run-plan execution flags must be explicit booleans")
    try:
        if PLAN_EXTENSION in normalized:
            validate_runtime_advisory(normalized[PLAN_EXTENSION])
        if CONTENT in normalized:
            content_entries({"extensions": normalized})
    except (ValueError, TypeError, KeyError) as exc:
        raise PlanningError("invalid retained run-plan evidence") from exc
    return normalized


def _unique(values, field: str) -> None:
    seen: set[str] = set()
    for value in values:
        value = _text(value, field)
        if value in seen:
            raise DuplicatePlanIdentityError(f"duplicate {field} {value!r}")
        seen.add(value)


def _unique_refs(values, field: str) -> None:
    seen: set[tuple[object, ...]] = set()
    for value in values:
        key = (value.id, value.version, value.sha256, value.reference)
        if key in seen:
            raise DuplicatePlanIdentityError(f"duplicate {field} identity {value.id!r}")
        seen.add(key)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlanningError(f"{field} must be a non-empty string")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PlanningError(f"{field} must use 'sha256:' plus 64 lowercase hex digits")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlanningError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlanningError(f"{field} must be a non-negative integer")
    return value


__all__ = [
    "AcceptedRunSnapshot",
    "AcceptedSnapshotIntegrityError",
    "DuplicatePlanIdentityError",
    "IncompletePlanError",
    "PlanIntegrityError",
    "PlannedCaseInput",
    "PlannedObservation",
    "PlanningError",
    "RUN_LIFECYCLE_CONTRACT_ID",
    "RUN_LIFECYCLE_CONTRACT_VERSION",
    "RUN_PLAN_SCHEMA_ID",
    "RUN_PLAN_SCHEMA_VERSION",
    "RunPlan",
    "accept_run_plan",
    "plan_run",
]
