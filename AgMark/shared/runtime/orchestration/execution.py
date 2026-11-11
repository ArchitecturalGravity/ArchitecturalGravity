"""Accepted treatment execution over exact registered runner authority."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib
import inspect
import json
from pathlib import Path, PurePosixPath
from typing import Any

from AgMark.shared.runtime.artifacts import (
    ArtifactPayload,
    ArtifactRecord,
    ContractBinding,
    FilesystemArtifactStore,
    RETAINABLE_EVIDENCE,
    SchemaBinding,
    retain_artifact_stage,
    sha256_bytes,
)
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef, canonical_json_bytes
from AgMark.shared.adapters.execution import (
    CanonicalObservationError,
    validate_retained_parity_observation,
)
from AgMark.shared.validation import (
    REGISTRATION_SCHEMA,
    ArtifactSource,
    ContractRequirement,
    validate_registration_binding_outcome,
)

from .admission import AcceptedExecutionError, AcceptedExecutionGate
from .planning import AcceptedRunSnapshot, PlannedObservation, RunPlan


RUNNER_INVOCATION_CONTRACT_ID = "arcgrav.shared.runner-invocation"
RUNNER_INVOCATION_CONTRACT_VERSION = "2.0.0"
TRANSIENT_INVOCATION_CONTRACT_ID = "arcgrav.shared.transient-invocation"
TRANSIENT_INVOCATION_CONTRACT_VERSION = "1.0.0"
TREATMENT_OBSERVATION_SCHEMA_ID = "arcgrav.shared.schema.treatment-observation"
TREATMENT_OBSERVATION_SCHEMA_VERSION = "1.0.0"

_RUNNER_ENTRY_POINT = "arcgrav.adapters:entry_point"
_SUPPORTED_CONTROLS = "arcgrav.adapters:supported_controls"
_SECRET_HANDLING = "arcgrav.adapters:secret_handling"
_TRANSIENT_INPUTS = "transient_inputs"
_CREDENTIAL_SOURCE = "credential_source"
_CREDENTIAL_MATERIAL = "credential_material"
_RUNNER_ARTIFACT_ROOTS = (PurePosixPath("AgMark/shared/adapters"), PurePosixPath("AgMark/shared/telemetry"), PurePosixPath("AgMark/shared/mock_model"), PurePosixPath("AgMark/shared/evaluation/telemetry/source.py"), PurePosixPath("AgMark/shared/runtime/identity/runtime_version.py"))
_EXECUTION_WINDOW_EXTENSION = "arcgrav.shared.runtime.orchestration:execution-window"
_RESULT_GUARD = object()


class TreatmentExecutionError(AcceptedExecutionError):
    """Accepted treatment execution cannot preserve exact runtime authority."""


@dataclass(frozen=True, slots=True)
class TreatmentCaseInput:
    """Exact accepted case bytes supplied for treatment invocation."""

    case_id: str
    data: bytes

    def __post_init__(self) -> None:
        _nonempty(self.case_id, "case_id")
        if not isinstance(self.data, bytes):
            raise TypeError("data must be exact bytes")

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.data)


@dataclass(frozen=True, slots=True)
class TreatmentPrompt:
    """Benchmark-owned prompt bytes selected for one accepted treatment identity."""

    treatment_id: str
    data: bytes

    def __post_init__(self) -> None:
        _nonempty(self.treatment_id, "treatment_id")
        if not isinstance(self.data, bytes):
            raise TypeError("data must be exact bytes")

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.data)


@dataclass(frozen=True, init=False, slots=True)
class TreatmentExecutionResult:
    """Opaque evidence that every planned treatment slot returned terminal evidence."""

    generation_id: str
    accepted_snapshot_id: str
    run_plan_id: str
    plan_sha256: str
    execution_boundary_fingerprint: str
    runner_registration_sha256: str
    retained_runner_registration_artifact: ArtifactRecord
    observation_bytes: tuple[bytes, ...]
    retained_observation_artifacts: tuple[ArtifactRecord, ...]
    _observation_ids: tuple[str, ...] = field(repr=False)
    _guard: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("created only by execute_planned_treatments")

    @property
    def observation_ids(self) -> tuple[str, ...]:
        self.revalidate()
        return self._observation_ids

    def observations(self) -> tuple[dict[str, object], ...]:
        """Return fresh decoded observation documents in canonical plan order."""

        self.revalidate()
        return tuple(
            json.loads(value.decode("utf-8"))
            for value in self.observation_bytes
        )

    def revalidate(self) -> None:
        if getattr(self, "_guard", None) is not _RESULT_GUARD:
            raise TreatmentExecutionError("treatment execution result authority is invalid")
        if type(self.retained_runner_registration_artifact) is not ArtifactRecord:
            raise TreatmentExecutionError("retained runner registration authority changed")
        runner_record = self.retained_runner_registration_artifact
        if runner_record.role != "runner_registration":
            raise TreatmentExecutionError("retained runner registration role changed")
        if runner_record.sha256 != self.runner_registration_sha256:
            raise TreatmentExecutionError("retained runner registration bytes changed")
        if runner_record.schema != SchemaBinding(
            REGISTRATION_SCHEMA.schema_id,
            REGISTRATION_SCHEMA.schema_version,
        ):
            raise TreatmentExecutionError("retained runner registration schema changed")
        if runner_record.contract != ContractBinding(
            RUNNER_INVOCATION_CONTRACT_ID,
            RUNNER_INVOCATION_CONTRACT_VERSION,
        ):
            raise TreatmentExecutionError("retained runner registration contract changed")
        if not runner_record.reference.startswith(self.generation_id + "/"):
            raise TreatmentExecutionError("retained runner registration generation changed")
        if len(self.observation_bytes) != len(self._observation_ids):
            raise TreatmentExecutionError("treatment observation evidence count changed")
        if len(self.retained_observation_artifacts) != len(self._observation_ids):
            raise TreatmentExecutionError("retained treatment artifact count changed")
        if len(set(self._observation_ids)) != len(self._observation_ids):
            raise TreatmentExecutionError("treatment observation identity is ambiguous")
        for expected_id, raw, record in zip(
            self._observation_ids,
            self.observation_bytes,
            self.retained_observation_artifacts,
            strict=True,
        ):
            document = _decoded_observation(raw)
            try:
                validate_retained_parity_observation(document)
            except CanonicalObservationError as exc:
                raise TreatmentExecutionError(
                    "retained treatment observation has invalid shared execution evidence"
                ) from exc
            if document.get("observation_id") != expected_id:
                raise TreatmentExecutionError("retained treatment observation identity changed")
            if record.artifact_id != expected_id + ".observation":
                raise TreatmentExecutionError("retained treatment artifact identity changed")
            if record.sha256 != sha256_bytes(raw):
                raise TreatmentExecutionError("retained treatment observation bytes changed")
            if record.role != "treatment_observation":
                raise TreatmentExecutionError("retained treatment observation role changed")
            if record.schema != SchemaBinding(
                TREATMENT_OBSERVATION_SCHEMA_ID,
                TREATMENT_OBSERVATION_SCHEMA_VERSION,
            ):
                raise TreatmentExecutionError("retained treatment observation schema changed")
            if record.contract != ContractBinding(
                RUNNER_INVOCATION_CONTRACT_ID,
                RUNNER_INVOCATION_CONTRACT_VERSION,
            ):
                raise TreatmentExecutionError("retained treatment observation contract changed")
            if not record.reference.startswith(self.generation_id + "/"):
                raise TreatmentExecutionError("retained treatment observation generation changed")


@dataclass(frozen=True, slots=True)
class _RunnerAuthority:
    registration_sha256: str
    runner_id: str
    runner_version: str
    factory: object
    registration: Mapping[str, object]


def execute_planned_treatments(
    *,
    gate: AcceptedExecutionGate,
    snapshot: AcceptedRunSnapshot,
    benchmark: IdentityRef | Mapping[str, object],
    case_set: IdentityRef | Mapping[str, object],
    treatment_set: IdentityRef | Mapping[str, object],
    execution_boundary: ExecutionBoundary,
    artifact_store: FilesystemArtifactStore,
    repository_root: str | Path,
    runner_registration: Mapping[str, object],
    case_inputs: Sequence[TreatmentCaseInput],
    treatment_prompts: Sequence[TreatmentPrompt],
    runner_transient_values: Mapping[str, str] | None = None,
    runner_launch_selection: Mapping[str, str] | None = None,
    live_view_callback=None,
    live_view_control=None,
    cancellation_requested=None,
) -> TreatmentExecutionResult:
    """Execute every accepted treatment slot from clean registered runner state.

    The accepted plan fixes slot identity and case-input identity. Benchmark-owned
    prompt bytes remain invocation material and are bound into the runner request
    identity and returned evidence; they do not replace accepted treatment-set
    authority. A fresh registered runner instance is created for every planned
    observation. Returned observations are retained immediately and no missing
    observation is synthesized when execution fails.
    """

    if type(gate) is not AcceptedExecutionGate:
        raise TypeError("gate must be an AcceptedExecutionGate")
    gate.revalidate()
    if type(snapshot) is not AcceptedRunSnapshot:
        raise TypeError("snapshot must be an AcceptedRunSnapshot")
    if type(execution_boundary) is not ExecutionBoundary:
        raise TypeError("execution_boundary must be an ExecutionBoundary")
    if type(artifact_store) is not FilesystemArtifactStore:
        raise TypeError("artifact_store must be a FilesystemArtifactStore")
    if not isinstance(runner_registration, Mapping):
        raise TypeError("runner_registration must be a mapping")

    plan = snapshot.revalidate_authority(
        benchmark=benchmark,
        case_set=case_set,
        treatment_set=treatment_set,
        execution_boundary=execution_boundary,
    )
    _gate_matches_plan(gate, snapshot, plan)

    inputs = _validated_case_inputs(plan, case_inputs)
    prompts = _validated_treatment_prompts(plan, treatment_prompts)
    runner = _resolve_runner_authority(
        registration=runner_registration,
        execution_boundary=execution_boundary,
        repository_root=repository_root,
    )
    transient_invocation = _validated_runner_transient_values(
        runner.registration,
        execution_boundary=execution_boundary,
        values=runner_transient_values,
    )

    runner_registration_raw = canonical_json_bytes(runner.registration)
    if sha256_bytes(runner_registration_raw) != runner.registration_sha256:
        raise TreatmentExecutionError(
            "validated runner registration identity changed before retention"
        )
    (runner_registration_record,) = retain_artifact_stage(
        store=artifact_store,
        generation_id=gate.generation_id,
        stage_id="runner-registration",
        artifacts=(
            ArtifactPayload(
                artifact_id="runner-registration",
                role="runner_registration",
                relative_path="registration.json",
                data=runner_registration_raw,
                provenance="arcgrav.shared.runtime.orchestration.runner-registration",
                retention_class=RETAINABLE_EVIDENCE,
                media_type="application/json",
                encoding="utf-8",
                schema=SchemaBinding(
                    REGISTRATION_SCHEMA.schema_id,
                    REGISTRATION_SCHEMA.schema_version,
                ),
                contract=ContractBinding(
                    RUNNER_INVOCATION_CONTRACT_ID,
                    RUNNER_INVOCATION_CONTRACT_VERSION,
                ),
            ),
        ),
    )

    retained_bytes: list[bytes] = []
    retained_records: list[ArtifactRecord] = []
    retained_ids: list[str] = []

    execution_only = plan.to_dict().get("extensions", {}).get("arcgrav.runtime:execution-only") is True
    for slot in plan.observations:
        if execution_only and cancellation_requested is not None and cancellation_requested():
            break
        request = _runner_request(
            gate=gate,
            plan=plan,
            slot=slot,
            execution_boundary=execution_boundary,
            case_input=inputs[slot.case_id],
            prompt=prompts[slot.treatment_id],
            transient_invocation=transient_invocation,
        )
        instance = _new_runner_instance(runner, launch_selection=runner_launch_selection)
        execution_started_at = _utc_now()
        try:
            def present(event, slot=slot):
                # Presentation is a narrow, non-authoritative channel. Never
                # forward invocation metadata, environment, credentials or logs.
                if not callable(live_view_callback) or not isinstance(event, Mapping):
                    return
                if live_view_control is not None and not live_view_control.snapshot()[0]:
                    return
                if event.get("channel") not in {"input", "output"} or not isinstance(event.get("text"), str):
                    return
                try:
                    projected = {
                        "generation_id": gate.generation_id,
                        "invocation_id": slot.observation_id,
                        "treatment_name": slot.treatment_id,
                        "channel": event["channel"],
                        "text": event["text"],
                    }
                    if type(event.get("stream_revision")) is int:
                        projected["stream_revision"] = event["stream_revision"]
                    live_view_callback(projected)
                except Exception:
                    pass  # A closed/failed display must not change execution.

            from inspect import signature
            cancel_options = {}
            if execution_only and cancellation_requested is not None and "cancellation_requested" in signature(instance.execute).parameters:
                cancel_options["cancellation_requested"] = cancellation_requested
            if getattr(instance, "supports_live_view", False):
                live_options = {"event_callback": present if callable(live_view_callback) else None}
                if getattr(instance, "supports_live_view_control", False):
                    live_options["live_view_control"] = live_view_control
                observed = instance.execute(copy.deepcopy(request), **live_options, **cancel_options)
            else:
                observed = instance.execute(copy.deepcopy(request), **cancel_options)
            execution_completed_at = _utc_now()
        except Exception as exc:
            raise TreatmentExecutionError(
                f"registered runner failed before returning terminal observation "
                f"{slot.observation_id!r}: {type(exc).__name__}"
            ) from exc
        finally:
            try:
                instance.close()
            except Exception as exc:
                raise TreatmentExecutionError(
                    f"registered runner close failed for {slot.observation_id!r}: "
                    f"{type(exc).__name__}"
                ) from exc

        document = _validated_observation(
            observed,
            gate=gate,
            slot=slot,
            runner=runner,
            execution_started_at=execution_started_at,
            execution_completed_at=execution_completed_at,
        )
        _reject_transient_material_in_evidence(document, transient_invocation)
        # Admission precedes even staging: failed privacy validation must leave
        # no rejected observation bytes on disk.
        try:
            validate_retained_parity_observation(document)
        except (CanonicalObservationError, ValueError) as exc:
            raise TreatmentExecutionError("runner observation failed evidence admission before retention") from exc
        raw = canonical_json_bytes(document)
        (record,) = retain_artifact_stage(
            store=artifact_store,
            generation_id=gate.generation_id,
            stage_id=(
                "observation-"
                + slot.observation_id.removeprefix("observation:")
                + "-observation"
            ),
            artifacts=(
                ArtifactPayload(
                    artifact_id=slot.observation_id + ".observation",
                    role="treatment_observation",
                    relative_path="observation.json",
                    data=raw,
                    provenance="arcgrav.shared.runtime.orchestration",
                    retention_class=RETAINABLE_EVIDENCE,
                    media_type="application/json",
                    encoding="utf-8",
                    schema=SchemaBinding(
                        TREATMENT_OBSERVATION_SCHEMA_ID,
                        TREATMENT_OBSERVATION_SCHEMA_VERSION,
                    ),
                    contract=ContractBinding(
                        RUNNER_INVOCATION_CONTRACT_ID,
                        RUNNER_INVOCATION_CONTRACT_VERSION,
                    ),
                ),
            ),
        )
        retained_ids.append(slot.observation_id)
        retained_bytes.append(raw)
        retained_records.append(record)

    expected_ids = tuple(slot.observation_id for slot in plan.observations)
    observed_ids = tuple(retained_ids)
    if observed_ids != expected_ids and not (execution_only and cancellation_requested is not None and cancellation_requested() and observed_ids == expected_ids[:len(observed_ids)]):
        raise TreatmentExecutionError(
            "started treatment observations do not exactly reconcile with the accepted plan"
        )

    value = object.__new__(TreatmentExecutionResult)
    for name, item in (
        ("generation_id", gate.generation_id),
        ("accepted_snapshot_id", gate.accepted_snapshot_id),
        ("run_plan_id", gate.run_plan_id),
        ("plan_sha256", gate.plan_sha256),
        ("execution_boundary_fingerprint", gate.execution_boundary_fingerprint),
        ("runner_registration_sha256", runner.registration_sha256),
        ("retained_runner_registration_artifact", runner_registration_record),
        ("observation_bytes", tuple(retained_bytes)),
        ("retained_observation_artifacts", tuple(retained_records)),
        ("_observation_ids", observed_ids),
        ("_guard", _RESULT_GUARD),
    ):
        object.__setattr__(value, name, item)
    value.revalidate()
    return value


def _gate_matches_plan(
    gate: AcceptedExecutionGate,
    snapshot: AcceptedRunSnapshot,
    plan: RunPlan,
) -> None:
    if (
        gate.accepted_snapshot_id != snapshot.accepted_snapshot_id
        or gate.run_plan_id != plan.run_plan_id
        or gate.plan_sha256 != plan.plan_sha256
        or gate.execution_boundary_fingerprint != plan.execution_boundary_fingerprint
    ):
        raise TreatmentExecutionError(
            "accepted execution gate does not bind this exact accepted plan"
        )


def _validated_case_inputs(
    plan: RunPlan,
    values: Sequence[TreatmentCaseInput],
) -> dict[str, TreatmentCaseInput]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("case_inputs must be a sequence of TreatmentCaseInput values")
    items = tuple(values)
    if not items or any(type(value) is not TreatmentCaseInput for value in items):
        raise TreatmentExecutionError(
            "case_inputs must contain exact TreatmentCaseInput values for every planned case"
        )
    by_id = {value.case_id: value for value in items}
    if len(by_id) != len(items):
        raise TreatmentExecutionError("treatment case-input identities must be unique")

    expected: dict[str, tuple[str, int | None]] = {}
    for slot in plan.observations:
        authority = (slot.input_sha256, slot.input_byte_length)
        previous = expected.get(slot.case_id)
        if previous is None:
            expected[slot.case_id] = authority
        elif previous != authority:
            raise TreatmentExecutionError(
                "accepted plan contains inconsistent input authority for one case"
            )
    if set(by_id) != set(expected):
        raise TreatmentExecutionError(
            "treatment case inputs must exactly match the accepted planned case set"
        )
    for case_id, (expected_sha256, expected_length) in expected.items():
        value = by_id[case_id]
        if value.sha256 != expected_sha256:
            raise TreatmentExecutionError(
                f"treatment input bytes do not match accepted authority for {case_id!r}"
            )
        if expected_length is not None and len(value.data) != expected_length:
            raise TreatmentExecutionError(
                f"treatment input length does not match accepted authority for {case_id!r}"
            )
    return by_id


def _validated_treatment_prompts(
    plan: RunPlan,
    values: Sequence[TreatmentPrompt],
) -> dict[str, TreatmentPrompt]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("treatment_prompts must be a sequence of TreatmentPrompt values")
    items = tuple(values)
    if not items or any(type(value) is not TreatmentPrompt for value in items):
        raise TreatmentExecutionError(
            "treatment_prompts must contain exact TreatmentPrompt values"
        )
    by_id = {value.treatment_id: value for value in items}
    if len(by_id) != len(items):
        raise TreatmentExecutionError("treatment prompt identities must be unique")
    planned = {slot.treatment_id for slot in plan.observations}
    if set(by_id) != planned:
        raise TreatmentExecutionError(
            "treatment prompts must exactly match the accepted treatment identities"
        )
    from AgMark.shared.treatments import content_entries
    entries = content_entries(plan.to_dict())
    if entries:
        if {e["treatment_id"] for e in entries} != planned:
            raise TreatmentExecutionError("frozen treatment set differs from accepted plan")
        for entry in entries:
            value = by_id[entry["treatment_id"]]
            if value.sha256 != entry["actual_sha256"] or len(value.data) != entry["actual_byte_length"]:
                raise TreatmentExecutionError("treatment bytes differ from accepted plan")
    return by_id


def _validated_runner_transient_values(
    registration: Mapping[str, object],
    *,
    execution_boundary: ExecutionBoundary,
    values: Mapping[str, str] | None,
) -> dict[str, str] | None:
    boundary = execution_boundary.to_dict()
    raw_controls = boundary.get("controls", ())
    boundary_control_names: set[str] = set()
    if isinstance(raw_controls, Sequence) and not isinstance(
        raw_controls, (str, bytes, bytearray)
    ):
        for raw in raw_controls:
            if isinstance(raw, Mapping) and isinstance(raw.get("name"), str):
                boundary_control_names.add(raw["name"])
    if _CREDENTIAL_SOURCE in boundary_control_names:
        raise TreatmentExecutionError(
            "transient credential source must not enter canonical execution boundary"
        )

    extensions = registration.get("extensions")
    if not isinstance(extensions, Mapping):
        if values is not None:
            raise TreatmentExecutionError(
                "runner transient invocation lacks registered extension authority"
            )
        return None
    raw_secret_handling = extensions.get(_SECRET_HANDLING)
    if raw_secret_handling is None:
        if values is not None:
            raise TreatmentExecutionError(
                "runner transient invocation is not declared by registration"
            )
        return None
    if not isinstance(raw_secret_handling, Mapping):
        raise TreatmentExecutionError("runner secret-handling metadata is invalid")

    credentials_required = raw_secret_handling.get("credentials_required") is True
    if not credentials_required:
        if values is not None:
            raise TreatmentExecutionError(
                "runner transient credentials were supplied to a credential-neutral runner"
            )
        return None
    if (
        raw_secret_handling.get("transient_secrets_supported") is not True
        or raw_secret_handling.get("retained_secret_values") is not False
    ):
        raise TreatmentExecutionError(
            "credential-required runner lacks safe transient-secret authority"
        )

    raw_sources = raw_secret_handling.get("supported_sources")
    if (
        isinstance(raw_sources, (str, bytes, bytearray))
        or not isinstance(raw_sources, Sequence)
    ):
        raise TreatmentExecutionError("runner supported credential sources are invalid")
    supported_sources = tuple(raw_sources)
    if (
        not supported_sources
        or any(not isinstance(source, str) or not source for source in supported_sources)
        or len(set(supported_sources)) != len(supported_sources)
    ):
        raise TreatmentExecutionError("runner supported credential sources are invalid")

    contracts = registration.get("contracts")
    if (
        isinstance(contracts, (str, bytes, bytearray))
        or not isinstance(contracts, Sequence)
        or not any(
            isinstance(contract, Mapping)
            and contract.get("id") == TRANSIENT_INVOCATION_CONTRACT_ID
            and contract.get("version") == TRANSIENT_INVOCATION_CONTRACT_VERSION
            for contract in contracts
        )
    ):
        raise TreatmentExecutionError(
            "credential-required runner does not bind the transient-invocation contract"
        )

    raw_supported = extensions.get(_SUPPORTED_CONTROLS, ())
    if (
        isinstance(raw_supported, (str, bytes, bytearray))
        or not isinstance(raw_supported, Sequence)
    ):
        raise TreatmentExecutionError("runner supported-control metadata is invalid")
    supported_controls = tuple(
        item for item in raw_supported if isinstance(item, Mapping)
    )
    credential_declarations = [
        item for item in supported_controls if item.get("name") == _CREDENTIAL_SOURCE
    ]
    if len(credential_declarations) != 1:
        raise TreatmentExecutionError(
            "credential-required runner must declare one credential_source control"
        )
    credential_declaration = credential_declarations[0]
    declared_values = credential_declaration.get("values")
    if (
        credential_declaration.get("kind") != "secret"
        or credential_declaration.get("comparison_relevant") is not False
        or isinstance(declared_values, (str, bytes, bytearray))
        or not isinstance(declared_values, Sequence)
    ):
        raise TreatmentExecutionError(
            "credential_source registration is not a transient non-comparison control"
        )

    raw_transient_inputs = raw_secret_handling.get(_TRANSIENT_INPUTS, ())
    if (
        isinstance(raw_transient_inputs, (str, bytes, bytearray))
        or not isinstance(raw_transient_inputs, Sequence)
    ):
        raise TreatmentExecutionError("runner transient-input metadata is invalid")
    transient_inputs: dict[str, tuple[str, ...]] = {}
    for raw_input in raw_transient_inputs:
        if not isinstance(raw_input, Mapping):
            raise TreatmentExecutionError("runner transient-input metadata is invalid")
        name = raw_input.get("name")
        kind = raw_input.get("kind")
        credential_sources = raw_input.get("credential_sources")
        if (
            not isinstance(name, str)
            or not name
            or name in {_CREDENTIAL_SOURCE, _CREDENTIAL_MATERIAL}
            or not isinstance(kind, str)
            or not kind
            or isinstance(credential_sources, (str, bytes, bytearray))
            or not isinstance(credential_sources, Sequence)
        ):
            raise TreatmentExecutionError("runner transient-input metadata is invalid")
        sources = tuple(credential_sources)
        if (
            not sources
            or any(
                not isinstance(source, str) or source not in supported_sources
                for source in sources
            )
            or len(set(sources)) != len(sources)
            or name in transient_inputs
        ):
            raise TreatmentExecutionError("runner transient-input metadata is invalid")
        declarations = [
            item for item in supported_controls if item.get("name") == name
        ]
        if len(declarations) != 1:
            raise TreatmentExecutionError(
                "runner transient input must match one supported control"
            )
        declaration = declarations[0]
        if (
            declaration.get("kind") != kind
            or declaration.get("comparison_relevant") is not False
            or declaration.get("required") is True
        ):
            raise TreatmentExecutionError(
                "runner transient input is not an optional non-comparison control"
            )
        transient_inputs[name] = sources

    if any(name in boundary_control_names for name in transient_inputs):
        raise TreatmentExecutionError(
            "registered transient input must not enter canonical execution boundary"
        )

    if values is None:
        raise TreatmentExecutionError(
            "registered runner transient credential source is required"
        )
    if not isinstance(values, Mapping):
        raise TypeError("runner_transient_values must be a mapping or None")
    allowed_names = {
        _CREDENTIAL_SOURCE,
        _CREDENTIAL_MATERIAL,
        *transient_inputs,
    }
    if set(values) - allowed_names:
        raise TreatmentExecutionError(
            "runner transient invocation contains undeclared values"
        )
    if any(
        not isinstance(key, str) or not isinstance(value, str) or not value
        for key, value in values.items()
    ):
        raise TreatmentExecutionError(
            "runner transient invocation values must be non-empty strings"
        )
    source = values.get(_CREDENTIAL_SOURCE)
    if source not in supported_sources or source not in declared_values:
        raise TreatmentExecutionError(
            "runner transient credential source is not registered"
        )
    for name, sources in transient_inputs.items():
        if name in values and source not in sources:
            raise TreatmentExecutionError(
                "runner transient input is not permitted for the selected credential source"
            )
    return dict(values)

def _contains_transient_material(value: object, secret: str) -> bool:
    if isinstance(value, str):
        return secret in value
    if isinstance(value, Mapping):
        return any(
            _contains_transient_material(key, secret)
            or _contains_transient_material(item, secret)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return any(_contains_transient_material(item, secret) for item in value)
    return False


def _reject_transient_material_in_evidence(
    document: Mapping[str, object],
    transient_invocation: Mapping[str, str] | None,
) -> None:
    if transient_invocation is None:
        return
    for name, transient_value in transient_invocation.items():
        if name == _CREDENTIAL_SOURCE:
            continue
        if transient_value and _contains_transient_material(document, transient_value):
            raise TreatmentExecutionError(
                "runner observation contains transient invocation material"
            )


def _resolve_runner_authority(
    *,
    registration: Mapping[str, object],
    execution_boundary: ExecutionBoundary,
    repository_root: str | Path,
) -> _RunnerAuthority:
    boundary = execution_boundary.to_dict()
    raw_runner = boundary.get("runner")
    if not isinstance(raw_runner, Mapping):
        raise TreatmentExecutionError("accepted boundary runner identity is invalid")
    runner_id = _nonempty(raw_runner.get("id"), "execution_boundary.runner.id")
    runner_version = _nonempty(
        raw_runner.get("version"), "execution_boundary.runner.version"
    )

    if registration.get("registration_kind") != "runner":
        raise TreatmentExecutionError("registered treatment collaborator must be a runner")
    if registration.get("status") != "active":
        raise TreatmentExecutionError("registered treatment runner must be active")

    sources = _registered_artifact_sources(registration, repository_root)
    source_id = f"treatment-runner:{runner_id}@{runner_version}"
    outcome = validate_registration_binding_outcome(
        registration,
        expected_registration_id=runner_id,
        expected_registration_version=runner_version,
        contract_requirements=(
            ContractRequirement(
                RUNNER_INVOCATION_CONTRACT_ID,
                (RUNNER_INVOCATION_CONTRACT_VERSION,),
            ),
            ContractRequirement(
                TRANSIENT_INVOCATION_CONTRACT_ID,
                (TRANSIENT_INVOCATION_CONTRACT_VERSION,),
                required=False,
            ),
        ),
        artifact_sources=sources,
        allowed_artifact_roots=tuple(root.as_posix() for root in _RUNNER_ARTIFACT_ROOTS),
        source_id=source_id,
    )
    if not outcome.valid:
        codes = ",".join(sorted({issue.code for issue in outcome.issues}))
        raise TreatmentExecutionError(
            "runner registration failed exact validation"
            + (f": {codes}" if codes else "")
        )

    extensions = registration.get("extensions")
    entry_point = extensions.get(_RUNNER_ENTRY_POINT) if isinstance(extensions, Mapping) else None
    if not isinstance(entry_point, str) or ":" not in entry_point:
        raise TreatmentExecutionError(
            "runner registration must declare arcgrav.adapters:entry_point"
        )
    module_name, separator, attribute = entry_point.partition(":")
    if (
        separator != ":"
        or not module_name.startswith("AgMark.shared.adapters.")
        or not attribute
        or "." in attribute
    ):
        raise TreatmentExecutionError("runner entry point is outside shared adapter/telemetry authority")
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attribute)
    except (ImportError, AttributeError) as exc:
        raise TreatmentExecutionError("registered runner entry point cannot be resolved") from exc
    if not callable(factory):
        raise TreatmentExecutionError("registered runner entry point must be callable")

    authority = _RunnerAuthority(
        registration_sha256=outcome.registration_sha256,
        runner_id=runner_id,
        runner_version=runner_version,
        factory=factory,
        registration=_json_clone(registration),
    )
    probe = _new_runner_instance(authority)
    try:
        description = probe.describe()
        _validate_runner_description(description, authority)
    finally:
        probe.close()
    return authority


def _registered_artifact_sources(
    registration: Mapping[str, object],
    repository_root: str | Path,
) -> tuple[ArtifactSource, ...]:
    root = Path(repository_root).resolve(strict=True)
    raw_artifacts = registration.get("implementation_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise TreatmentExecutionError(
            "runner registration must declare implementation artifacts"
        )

    sources: list[ArtifactSource] = []
    for item in raw_artifacts:
        if not isinstance(item, Mapping):
            raise TreatmentExecutionError("runner implementation artifact is invalid")
        artifact_id = _nonempty(item.get("artifact_id"), "implementation artifact_id")
        reference = _nonempty(item.get("reference"), "implementation reference")
        relative = PurePosixPath(reference)
        if (
            relative.is_absolute()
            or str(relative) != reference
            or any(part in {"", ".", ".."} for part in relative.parts)
            or not any(root in (relative, *relative.parents) for root in _RUNNER_ARTIFACT_ROOTS)
        ):
            raise TreatmentExecutionError(
                "runner implementation artifact is outside shared adapter/telemetry authority"
            )
        path = (root / Path(*relative.parts)).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise TreatmentExecutionError(
                "runner implementation artifact escapes repository authority"
            ) from exc
        if not path.is_file():
            raise TreatmentExecutionError(
                f"runner implementation artifact is not a file: {reference!r}"
            )
        sources.append(
            ArtifactSource(
                artifact_id=artifact_id,
                reference=reference,
                data=path.read_bytes(),
            )
        )
    return tuple(sources)


def _new_runner_instance(authority: _RunnerAuthority, *, launch_selection=None):
    try:
        # Different registrations may select the same production runner class.
        # Bind exact validated target data when the factory explicitly accepts it;
        # retain legacy no-argument runners under the same description check.
        parameters = inspect.signature(authority.factory).parameters
        kwargs = {}
        if launch_selection:
            if "launch_selection" not in parameters:
                raise TreatmentExecutionError("selected runner does not support private launch selectors")
            if set(launch_selection) - {"codex_binary", "wsl_distribution", "expected_runtime_version"} or any(
                    not isinstance(v, str) or not v for v in launch_selection.values()):
                raise TreatmentExecutionError("invalid private launch selector")
            kwargs["launch_selection"] = dict(launch_selection)
        registration_parameter = parameters.get("registration")
        if (
            registration_parameter is not None
            and registration_parameter.kind
            in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        ):
            instance = authority.factory(
                registration=_json_clone(authority.registration), **kwargs
            )
        else:
            instance = authority.factory(**kwargs)
    except Exception as exc:
        raise TreatmentExecutionError(
            f"registered runner could not be constructed: {type(exc).__name__}"
        ) from exc
    for method in ("describe", "execute", "close"):
        if not callable(getattr(instance, method, None)):
            raise TreatmentExecutionError(
                f"registered runner lacks required {method} semantics"
            )
    return instance


def _validate_runner_description(
    value: object,
    authority: _RunnerAuthority,
) -> None:
    if not isinstance(value, Mapping):
        raise TreatmentExecutionError("registered runner describe() must return a mapping")
    if value.get("runner") != {
        "id": authority.runner_id,
        "version": authority.runner_version,
    }:
        raise TreatmentExecutionError(
            "registered runner description identity does not match accepted boundary"
        )
    if value.get("contract") != {
        "id": RUNNER_INVOCATION_CONTRACT_ID,
        "version": RUNNER_INVOCATION_CONTRACT_VERSION,
    }:
        raise TreatmentExecutionError(
            "registered runner description contract is incompatible"
        )
    described_registration = value.get("registration")
    if not isinstance(described_registration, Mapping):
        raise TreatmentExecutionError(
            "registered runner description must retain registration authority"
        )
    if canonical_json_bytes(described_registration) != canonical_json_bytes(
        authority.registration
    ):
        raise TreatmentExecutionError(
            "registered runner description does not bind the validated registration"
        )


def _runner_request(
    *,
    gate: AcceptedExecutionGate,
    plan: RunPlan,
    slot: PlannedObservation,
    execution_boundary: ExecutionBoundary,
    case_input: TreatmentCaseInput,
    prompt: TreatmentPrompt,
    transient_invocation: Mapping[str, str] | None,
) -> dict[str, object]:
    request_identity = {
        "accepted_generation_id": gate.generation_id,
        "request_id": slot.request_id,
        "observation_id": slot.observation_id,
        "case_id": slot.case_id,
        "treatment_id": slot.treatment_id,
        "repetition": slot.repetition,
        "execution_boundary_fingerprint": slot.execution_boundary_fingerprint,
        "prompt_sha256": prompt.sha256,
        "input_sha256": case_input.sha256,
    }
    request: dict[str, object] = {
        "accepted_generation_id": gate.generation_id,
        "request_id": slot.request_id,
        "observation_id": slot.observation_id,
        "benchmark_id": plan.benchmark.id,
        "case_id": slot.case_id,
        "treatment_id": slot.treatment_id,
        "repetition": slot.repetition,
        "execution_boundary_fingerprint": slot.execution_boundary_fingerprint,
        "execution_boundary": execution_boundary.to_dict(),
        "conversation_policy": {
            "new_conversation": True,
            "reuse_prior_observation_context": False,
        },
        "prompt": {
            "content": prompt.data,
            "sha256": prompt.sha256,
        },
        "input": {
            "content": case_input.data,
            "sha256": case_input.sha256,
        },
        "request_identity": {
            "prompt_sha256": prompt.sha256,
            "input_sha256": case_input.sha256,
            "request_sha256": sha256_bytes(canonical_json_bytes(request_identity)),
        },
    }
    if transient_invocation is not None:
        request["transient_invocation"] = dict(transient_invocation)
    return request


def _validated_observation(
    value: object,
    *,
    gate: AcceptedExecutionGate,
    slot: PlannedObservation,
    runner: _RunnerAuthority,
    execution_started_at: str,
    execution_completed_at: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TreatmentExecutionError(
            f"runner returned no terminal mapping for {slot.observation_id!r}"
        )
    observed = _json_clone(value)
    expected = {
        "schema_id": TREATMENT_OBSERVATION_SCHEMA_ID,
        "schema_version": TREATMENT_OBSERVATION_SCHEMA_VERSION,
        "accepted_generation_id": gate.generation_id,
        "request_id": slot.request_id,
        "observation_id": slot.observation_id,
        "case_id": slot.case_id,
        "treatment_id": slot.treatment_id,
        "repetition": slot.repetition,
        "execution_boundary_fingerprint": slot.execution_boundary_fingerprint,
    }
    for field_name, expected_value in expected.items():
        if observed.get(field_name) != expected_value:
            raise TreatmentExecutionError(
                f"runner observation field {field_name!r} does not match accepted authority"
            )
    if observed.get("runner") != {
        "id": runner.runner_id,
        "version": runner.runner_version,
    }:
        raise TreatmentExecutionError(
            "runner observation identity does not match validated runner authority"
        )
    if observed.get("contract") != {
        "id": RUNNER_INVOCATION_CONTRACT_ID,
        "version": RUNNER_INVOCATION_CONTRACT_VERSION,
    }:
        raise TreatmentExecutionError(
            "runner observation does not bind the supported invocation contract"
        )
    terminal = observed.get("terminal_status")
    if not isinstance(terminal, str) or not terminal:
        raise TreatmentExecutionError(
            "runner observation must retain an explicit terminal_status"
        )
    attempts = observed.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise TreatmentExecutionError(
            "runner observation must retain terminal attempt evidence"
        )

    extensions = observed.get("extensions")
    if not isinstance(extensions, dict):
        raise TreatmentExecutionError(
            "runner observation extensions must remain a JSON object"
        )
    if _EXECUTION_WINDOW_EXTENSION in extensions:
        raise TreatmentExecutionError(
            "runner observation cannot claim orchestration execution-window authority"
        )
    extensions[_EXECUTION_WINDOW_EXTENSION] = {
        "started_at": execution_started_at,
        "completed_at": execution_completed_at,
    }
    return observed


def _decoded_observation(raw: bytes) -> dict[str, object]:
    if not isinstance(raw, bytes):
        raise TreatmentExecutionError("treatment observation evidence must be bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TreatmentExecutionError(
            "treatment observation evidence is not canonical JSON"
        ) from exc
    if not isinstance(value, dict):
        raise TreatmentExecutionError("treatment observation evidence must be an object")
    if canonical_json_bytes(value) != raw:
        raise TreatmentExecutionError("treatment observation bytes are not canonical")
    return value


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _json_clone(value: Mapping[str, object]) -> dict[str, object]:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise TreatmentExecutionError(
            "registered or observed runner data must be JSON-compatible"
        ) from exc
    if not isinstance(decoded, dict):
        raise TreatmentExecutionError("runner data must be a JSON object")
    return decoded


def _nonempty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TreatmentExecutionError(f"{field_name} must be a non-empty string")
    return value


__all__ = [
    "RUNNER_INVOCATION_CONTRACT_ID",
    "RUNNER_INVOCATION_CONTRACT_VERSION",
    "TREATMENT_OBSERVATION_SCHEMA_ID",
    "TREATMENT_OBSERVATION_SCHEMA_VERSION",
    "TreatmentCaseInput",
    "TreatmentExecutionError",
    "TreatmentExecutionResult",
    "TreatmentPrompt",
    "execute_planned_treatments",
]
