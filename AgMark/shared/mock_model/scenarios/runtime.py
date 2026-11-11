"""Deterministic cause-side scenarios for the provider-neutral mock model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import time
from typing import NoReturn


COMPLETED_SCENARIO = "completed"
STRUCTURED_RESPONSE_SCENARIO = "structured_response"
EMPTY_RESPONSE_SCENARIO = "empty_response"
MALFORMED_OUTPUT_SCENARIO = "malformed_output"
PROCESS_FAILURE_SCENARIO = "process_failure"
EXECUTION_REJECTION_SCENARIO = "execution_rejection"
SUCCESS_WITH_STDERR_SCENARIO = "success_with_stderr"
PARTIAL_OUTPUT_FAILURE_SCENARIO = "partial_output_failure"
PARTIAL_OUTPUT_TIMEOUT_SCENARIO = "partial_output_timeout"
PARTIAL_OUTPUT_CANCELLATION_SCENARIO = "partial_output_cancellation"
TIMEOUT_SCENARIO = "timeout"
CANCELLATION_SCENARIO = "cancellation"

RUNTIME_PROBE_FAILURE_SCENARIO = "runtime_probe_failure"
RUNTIME_VERSION_MISMATCH_SCENARIO = "runtime_version_mismatch"
CAPABILITY_FAILURE_SCENARIO = "capability_failure"
DISCOVERY_FAILURE_SCENARIO = "discovery_failure"
DISCOVERY_PROTOCOL_INVALID_SCENARIO = "discovery_protocol_invalid"

RUNTIME_IDENTITY_OPERATION = "runtime_identity"
CAPABILITY_INSPECTION_OPERATION = "capability_inspection"
MODEL_DISCOVERY_OPERATION = "model_discovery"

INTERRUPTIBLE_WAIT_SLICE_SECONDS = 1.0

KNOWN_INFERENCE_SCENARIOS = frozenset(
    {
        COMPLETED_SCENARIO,
        STRUCTURED_RESPONSE_SCENARIO,
        EMPTY_RESPONSE_SCENARIO,
        MALFORMED_OUTPUT_SCENARIO,
        PROCESS_FAILURE_SCENARIO,
        EXECUTION_REJECTION_SCENARIO,
        SUCCESS_WITH_STDERR_SCENARIO,
        PARTIAL_OUTPUT_FAILURE_SCENARIO,
        PARTIAL_OUTPUT_TIMEOUT_SCENARIO,
        PARTIAL_OUTPUT_CANCELLATION_SCENARIO,
        TIMEOUT_SCENARIO,
        CANCELLATION_SCENARIO,
    }
)

KNOWN_PREFLIGHT_SCENARIOS = frozenset(
    {
        RUNTIME_PROBE_FAILURE_SCENARIO,
        RUNTIME_VERSION_MISMATCH_SCENARIO,
        CAPABILITY_FAILURE_SCENARIO,
        DISCOVERY_FAILURE_SCENARIO,
        DISCOVERY_PROTOCOL_INVALID_SCENARIO,
    }
)


def _required_text(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _required_bytes(value: bytes, *, field: str) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError(f"{field} must be bytes")
    return value


def _digest_bytes(*values: bytes) -> bytes:
    digest = hashlib.sha256()
    for value in values:
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest().encode("ascii")


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    """Observable target/process facts created by one scenario invocation."""

    response: bytes
    stdout: bytes
    stderr: bytes
    exit_code: int

    def __post_init__(self) -> None:
        _required_bytes(self.response, field="response")
        _required_bytes(self.stdout, field="stdout")
        _required_bytes(self.stderr, field="stderr")
        if type(self.exit_code) is not int:
            raise TypeError("exit_code must be int")


@dataclass(frozen=True, slots=True)
class PreflightScenarioOutcome:
    """Provider-neutral target facts for one registered non-inference scenario."""

    scenario_id: str
    operation: str
    failure_code: str | None = None
    diagnostic: bytes = b""
    runtime_version: str | None = None
    protocol_payload: bytes | None = None

    def __post_init__(self) -> None:
        _required_text(self.scenario_id, field="scenario_id")
        _required_text(self.operation, field="operation")
        _required_bytes(self.diagnostic, field="diagnostic")
        if self.failure_code is not None:
            _required_text(self.failure_code, field="failure_code")
        if self.runtime_version is not None:
            _required_text(self.runtime_version, field="runtime_version")
        if self.protocol_payload is not None:
            _required_bytes(self.protocol_payload, field="protocol_payload")
            if not self.protocol_payload:
                raise ValueError("protocol_payload must not be empty")

        effects = sum(
            (
                self.failure_code is not None,
                self.runtime_version is not None,
                self.protocol_payload is not None,
            )
        )
        if effects != 1:
            raise ValueError("preflight scenario must define exactly one observable effect")
        if self.failure_code is None and self.diagnostic:
            raise ValueError("diagnostic requires failure_code")


def ensure_known_inference_scenario(scenario_id: str) -> str:
    """Validate one registered finite inference scenario identifier."""

    scenario_id = _required_text(scenario_id, field="scenario_id")
    if scenario_id not in KNOWN_INFERENCE_SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario_id}")
    return scenario_id


def ensure_known_preflight_scenario(scenario_id: str) -> str:
    """Validate one registered provider-neutral preflight scenario identifier."""

    scenario_id = _required_text(scenario_id, field="scenario_id")
    if scenario_id not in KNOWN_PREFLIGHT_SCENARIOS:
        raise ValueError(f"unknown preflight scenario: {scenario_id}")
    return scenario_id


def evaluate_preflight_scenario(scenario_id: str) -> PreflightScenarioOutcome:
    """Resolve one registered preflight scenario into runner-opaque target facts."""

    scenario_id = ensure_known_preflight_scenario(scenario_id)

    if scenario_id == RUNTIME_PROBE_FAILURE_SCENARIO:
        return PreflightScenarioOutcome(
            scenario_id=scenario_id,
            operation=RUNTIME_IDENTITY_OPERATION,
            failure_code="runtime_identity_unavailable",
            diagnostic=b"arcgrav-mock-runtime-probe-failure-v1\n",
        )

    if scenario_id == RUNTIME_VERSION_MISMATCH_SCENARIO:
        return PreflightScenarioOutcome(
            scenario_id=scenario_id,
            operation=RUNTIME_IDENTITY_OPERATION,
            runtime_version="0.0.0-incompatible",
        )

    if scenario_id == CAPABILITY_FAILURE_SCENARIO:
        return PreflightScenarioOutcome(
            scenario_id=scenario_id,
            operation=CAPABILITY_INSPECTION_OPERATION,
            failure_code="capability_probe_failed",
            diagnostic=b"arcgrav-mock-capability-failure-v1\n",
        )

    if scenario_id == DISCOVERY_FAILURE_SCENARIO:
        return PreflightScenarioOutcome(
            scenario_id=scenario_id,
            operation=MODEL_DISCOVERY_OPERATION,
            failure_code="model_catalog_unavailable",
            diagnostic=b"arcgrav-mock-discovery-failure-v1\n",
        )

    if scenario_id == DISCOVERY_PROTOCOL_INVALID_SCENARIO:
        return PreflightScenarioOutcome(
            scenario_id=scenario_id,
            operation=MODEL_DISCOVERY_OPERATION,
            protocol_payload=b"arcgrav-mock-invalid-discovery-v1\n",
        )

    raise AssertionError(f"unhandled preflight scenario: {scenario_id}")


def _remain_interruptible(
    sleeper: Callable[[float], None],
) -> NoReturn:
    """Remain alive until the owning process or caller interrupts execution."""

    while True:
        sleeper(INTERRUPTIBLE_WAIT_SLICE_SECONDS)


def evaluate_inference_scenario(
    scenario_id: str,
    *,
    model_id: str,
    invocation_id: str,
    request_bytes: bytes,
    default_response: bytes,
    partial_output_sink: Callable[[bytes, bytes], None] | None = None,
) -> ScenarioOutcome:
    """Create deterministic finite process facts without AgMark status semantics."""

    scenario_id = ensure_known_inference_scenario(scenario_id)
    model_id = _required_text(model_id, field="model_id")
    invocation_id = _required_text(invocation_id, field="invocation_id")
    request_bytes = _required_bytes(request_bytes, field="request_bytes")
    default_response = _required_bytes(default_response, field="default_response")

    digest = _digest_bytes(
        scenario_id.encode("utf-8"),
        model_id.encode("utf-8"),
        invocation_id.encode("utf-8"),
        request_bytes,
    )

    if scenario_id == COMPLETED_SCENARIO:
        return ScenarioOutcome(
            response=default_response,
            stdout=default_response,
            stderr=b"",
            exit_code=0,
        )

    if scenario_id == STRUCTURED_RESPONSE_SCENARIO:
        response = b'{"synthetic":true,"digest":"' + digest + b'"}\n'
        return ScenarioOutcome(
            response=response,
            stdout=response,
            stderr=b"",
            exit_code=0,
        )

    if scenario_id == EMPTY_RESPONSE_SCENARIO:
        return ScenarioOutcome(
            response=b"",
            stdout=b"",
            stderr=b"",
            exit_code=0,
        )

    if scenario_id == MALFORMED_OUTPUT_SCENARIO:
        response = b'{"synthetic":true,"digest":"' + digest[:20]
        return ScenarioOutcome(
            response=response,
            stdout=response,
            stderr=b"",
            exit_code=0,
        )

    if scenario_id == PROCESS_FAILURE_SCENARIO:
        stderr = b"arcgrav-mock-process-failure-v1:" + digest + b"\n"
        return ScenarioOutcome(
            response=b"",
            stdout=b"",
            stderr=stderr,
            exit_code=23,
        )

    if scenario_id == EXECUTION_REJECTION_SCENARIO:
        stderr = b"arcgrav-mock-execution-rejection-v1:" + digest + b"\n"
        return ScenarioOutcome(
            response=b"",
            stdout=b"",
            stderr=stderr,
            exit_code=25,
        )

    if scenario_id == SUCCESS_WITH_STDERR_SCENARIO:
        stderr = b"arcgrav-mock-diagnostic-v1:" + digest + b"\n"
        return ScenarioOutcome(
            response=default_response,
            stdout=default_response,
            stderr=stderr,
            exit_code=0,
        )

    if scenario_id == PARTIAL_OUTPUT_FAILURE_SCENARIO:
        stdout = b"arcgrav-mock-partial-v1:" + digest + b"\n"
        stderr = b"arcgrav-mock-partial-failure-v1:" + digest + b"\n"
        return ScenarioOutcome(
            response=b"",
            stdout=stdout,
            stderr=stderr,
            exit_code=24,
        )

    if scenario_id in {
        PARTIAL_OUTPUT_TIMEOUT_SCENARIO,
        PARTIAL_OUTPUT_CANCELLATION_SCENARIO,
    }:
        # Only the external target writes process streams. The sink flushes
        # genuine target bytes before the owning execution boundary interrupts
        # this invocation; the scenario does not choose a terminal status.
        if partial_output_sink is not None:
            partial_output_sink(
                b"arcgrav-mock-interrupted-stdout-v1:" + digest + b"\n",
                b"arcgrav-mock-interrupted-stderr-v1:" + digest + b"\n",
            )
        _remain_interruptible(time.sleep)

    if scenario_id in {TIMEOUT_SCENARIO, CANCELLATION_SCENARIO}:
        _remain_interruptible(time.sleep)

    raise AssertionError(f"unhandled scenario: {scenario_id}")
