"""Shared runner-adapter contract helpers.

This module contains benchmark-neutral validation and observation construction
used by concrete adapters. It deliberately does not own planning, scoring,
accepted-run authority, or benchmark semantics.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

RUNNER_CONTRACT_ID = "arcgrav.shared.runner-invocation"
RUNNER_CONTRACT_VERSION = "2.0.0"
OBSERVATION_SCHEMA_ID = "arcgrav.shared.schema.treatment-observation"
OBSERVATION_SCHEMA_VERSION = "1.0.0"

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "timed_out", "cancelled", "unsupported"}
)


class AdapterValidationError(ValueError):
    """Raised when a runner request is structurally invalid before acceptance."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class UnsupportedBoundaryError(ValueError):
    """Raised when an otherwise valid request cannot be honored by an adapter."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedRequest:
    request: Mapping[str, Any]
    accepted_generation_id: str
    request_id: str
    observation_id: str
    benchmark_id: str
    case_id: str
    treatment_id: str
    repetition: int
    execution_boundary_fingerprint: str
    execution_boundary: Mapping[str, Any]
    conversation_policy: Mapping[str, Any]
    prompt_bytes: bytes
    input_bytes: bytes
    request_sha256: str
    boundary_controls: Mapping[str, Any]
    request_controls: Mapping[str, Any] | None


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AdapterValidationError(
            "runner_request_invalid",
            f"{field} must be a mapping",
        )
    return value


def _require_text(mapping: Mapping[str, Any], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value:
        raise AdapterValidationError(
            "runner_request_invalid",
            f"{field} must be a non-empty string",
        )
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise AdapterValidationError(
            "runner_request_invalid",
            f"{field} must be a sha256:<lowercase-hex> identity",
        )
    return value


def _content_bytes(record: Mapping[str, Any], field: str) -> bytes:
    value = record.get("content")
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, str):
        encoding = record.get("encoding", "utf-8")
        if encoding != "utf-8":
            raise AdapterValidationError(
                "runner_request_invalid",
                f"{field}.encoding must be utf-8 for textual content",
            )
        return value.encode("utf-8")
    raise AdapterValidationError(
        "runner_request_invalid",
        f"{field}.content must be bytes-like or UTF-8 text",
    )


def controls_to_mapping(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        result: dict[str, Any] = {}
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                raise AdapterValidationError(
                    "runner_request_invalid",
                    f"{field}[{index}] must be a name/value mapping",
                )
            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise AdapterValidationError(
                    "runner_request_invalid",
                    f"{field}[{index}].name must be a non-empty string",
                )
            if "value" not in item:
                raise AdapterValidationError(
                    "runner_request_invalid",
                    f"{field}[{index}] must contain value",
                )
            if name in result:
                raise AdapterValidationError(
                    "runner_request_invalid",
                    f"{field} contains duplicate control {name!r}",
                )
            result[name] = item["value"]
        return result
    raise AdapterValidationError(
        "runner_request_invalid",
        f"{field} must be a mapping or name/value sequence",
    )


def validate_runner_request(request: Mapping[str, Any]) -> ValidatedRequest:
    """Validate immutable request identity without deciding adapter support."""

    if not isinstance(request, Mapping):
        raise AdapterValidationError(
            "runner_request_invalid",
            "request must be a mapping",
        )

    snapshot = copy.deepcopy(request)

    accepted_generation_id = _require_text(snapshot, "accepted_generation_id")
    request_id = _require_text(snapshot, "request_id")
    observation_id = _require_text(snapshot, "observation_id")
    benchmark_id = _require_text(snapshot, "benchmark_id")
    case_id = _require_text(snapshot, "case_id")
    treatment_id = _require_text(snapshot, "treatment_id")

    repetition = snapshot.get("repetition")
    if isinstance(repetition, bool) or not isinstance(repetition, int) or repetition < 1:
        raise AdapterValidationError(
            "runner_request_invalid",
            "repetition must be a positive integer",
        )

    request_fingerprint = _require_sha256(
        snapshot.get("execution_boundary_fingerprint"),
        "execution_boundary_fingerprint",
    )
    boundary = _require_mapping(snapshot.get("execution_boundary"), "execution_boundary")
    _require_sha256(boundary.get("fingerprint"), "execution_boundary.fingerprint")
    _require_mapping(boundary.get("runner"), "execution_boundary.runner")
    conversation = _require_mapping(
        snapshot.get("conversation_policy"),
        "conversation_policy",
    )

    prompt = _require_mapping(snapshot.get("prompt"), "prompt")
    input_record = _require_mapping(snapshot.get("input"), "input")
    prompt_bytes = _content_bytes(prompt, "prompt")
    input_bytes = _content_bytes(input_record, "input")
    prompt_sha256 = _require_sha256(prompt.get("sha256"), "prompt.sha256")
    input_sha256 = _require_sha256(input_record.get("sha256"), "input.sha256")
    if sha256_bytes(prompt_bytes) != prompt_sha256:
        raise AdapterValidationError(
            "runner_prompt_hash_mismatch",
            "prompt bytes do not match prompt.sha256",
        )
    if sha256_bytes(input_bytes) != input_sha256:
        raise AdapterValidationError(
            "runner_input_hash_mismatch",
            "input bytes do not match input.sha256",
        )

    request_identity = _require_mapping(
        snapshot.get("request_identity"),
        "request_identity",
    )
    if (
        _require_sha256(
            request_identity.get("prompt_sha256"),
            "request_identity.prompt_sha256",
        )
        != prompt_sha256
    ):
        raise AdapterValidationError(
            "runner_prompt_identity_mismatch",
            "request_identity.prompt_sha256 does not match prompt.sha256",
        )
    if (
        _require_sha256(
            request_identity.get("input_sha256"),
            "request_identity.input_sha256",
        )
        != input_sha256
    ):
        raise AdapterValidationError(
            "runner_input_identity_mismatch",
            "request_identity.input_sha256 does not match input.sha256",
        )
    request_sha256 = _require_sha256(
        request_identity.get("request_sha256"),
        "request_identity.request_sha256",
    )

    boundary_controls = controls_to_mapping(
        boundary.get("controls", []),
        "execution_boundary.controls",
    )
    request_controls = (
        controls_to_mapping(snapshot["controls"], "controls")
        if "controls" in snapshot
        else None
    )

    return ValidatedRequest(
        request=snapshot,
        accepted_generation_id=accepted_generation_id,
        request_id=request_id,
        observation_id=observation_id,
        benchmark_id=benchmark_id,
        case_id=case_id,
        treatment_id=treatment_id,
        repetition=repetition,
        execution_boundary_fingerprint=request_fingerprint,
        execution_boundary=boundary,
        conversation_policy=conversation,
        prompt_bytes=prompt_bytes,
        input_bytes=input_bytes,
        request_sha256=request_sha256,
        boundary_controls=boundary_controls,
        request_controls=request_controls,
    )


def validate_boundary_support(
    validated: ValidatedRequest,
    *,
    runner_id: str,
    runner_version: str,
    supported_controls: Mapping[str, frozenset[Any] | None],
    required_controls: frozenset[str],
    fixed_controls: Mapping[str, Any],
) -> None:
    """Reject comparison-relevant boundaries the configured adapter cannot honor."""

    boundary = validated.execution_boundary
    if boundary.get("fingerprint") != validated.execution_boundary_fingerprint:
        raise UnsupportedBoundaryError(
            "runner_boundary_fingerprint_mismatch",
            "request and execution boundary fingerprints differ",
        )

    boundary_runner = boundary["runner"]
    if boundary_runner.get("id") != runner_id or boundary_runner.get("version") != runner_version:
        raise UnsupportedBoundaryError(
            "runner_identity_unsupported",
            "execution boundary selects a different runner identity or version",
        )

    conversation = validated.conversation_policy
    if conversation.get("new_conversation") is not True:
        raise UnsupportedBoundaryError(
            "runner_conversation_policy_unsupported",
            "new_conversation must be true",
        )
    if conversation.get("reuse_prior_observation_context") is not False:
        raise UnsupportedBoundaryError(
            "runner_conversation_policy_unsupported",
            "reuse_prior_observation_context must be false",
        )

    boundary_controls = validated.boundary_controls
    declared = set(supported_controls) | set(fixed_controls)
    undeclared = sorted(set(boundary_controls) - declared)
    if undeclared:
        raise UnsupportedBoundaryError(
            "runner_control_unsupported",
            "execution boundary contains undeclared controls: " + ", ".join(undeclared),
        )

    missing = sorted(required_controls - set(boundary_controls))
    if missing:
        raise UnsupportedBoundaryError(
            "runner_control_unsupported",
            "execution boundary is missing required controls: " + ", ".join(missing),
        )

    for name, expected in fixed_controls.items():
        if boundary_controls.get(name) != expected:
            raise UnsupportedBoundaryError(
                "runner_fixed_control_mismatch",
                f"execution boundary control {name!r} does not match registration",
            )

    for name, allowed in supported_controls.items():
        if name not in boundary_controls:
            continue
        if allowed is not None and boundary_controls[name] not in allowed:
            raise UnsupportedBoundaryError(
                "runner_control_unsupported",
                f"execution boundary control {name!r} has an unsupported value",
            )

    if validated.request_controls is not None:
        settable_boundary = {
            name: boundary_controls[name]
            for name in supported_controls
            if name in boundary_controls
        }
        if validated.request_controls != settable_boundary:
            raise UnsupportedBoundaryError(
                "runner_control_mismatch",
                "request controls do not match execution-boundary settable controls",
            )


def terminal_observation(
    validated: ValidatedRequest,
    *,
    runner_id: str,
    runner_version: str,
    terminal_status: str,
    response_bytes: bytes | None,
    error_code: str | None = None,
    diagnostics: Sequence[str] = (),
    deterministic_timestamp: str | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct one schema-shaped terminal treatment observation."""

    if terminal_status not in _TERMINAL_STATUSES:
        raise ValueError(f"unknown terminal status: {terminal_status}")

    response: dict[str, Any]
    observation_extensions = dict(extensions or {})
    if response_bytes is None:
        response = {"availability": "not_produced"}
    else:
        response_sha256 = sha256_bytes(response_bytes)
        extension_key = f"{runner_id}:response_base64"
        observation_extensions[extension_key] = base64.b64encode(response_bytes).decode("ascii")
        response = {
            "availability": "retained",
            "sha256": response_sha256,
            "reference": f"extensions:/{extension_key}",
            "byte_length": len(response_bytes),
        }

    attempt: dict[str, Any] = {
        "attempt": 1,
        "status": terminal_status,
        "started_at": deterministic_timestamp,
        "completed_at": deterministic_timestamp,
        "duration_ms": 0.0 if deterministic_timestamp is not None else None,
        "error_code": error_code,
    }

    telemetry = [
        {
            "name": "prompt_bytes",
            "value": len(validated.prompt_bytes),
            "provenance": "runner-measured",
            "unit": "bytes",
        },
        {
            "name": "input_bytes",
            "value": len(validated.input_bytes),
            "provenance": "runner-measured",
            "unit": "bytes",
        },
    ]
    if response_bytes is not None:
        telemetry.append(
            {
                "name": "response_bytes",
                "value": len(response_bytes),
                "provenance": "runner-measured",
                "unit": "bytes",
            }
        )

    result: dict[str, Any] = {
        "schema_id": OBSERVATION_SCHEMA_ID,
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "extensions": observation_extensions,
        "accepted_generation_id": validated.accepted_generation_id,
        "request_id": validated.request_id,
        "observation_id": validated.observation_id,
        "case_id": validated.case_id,
        "treatment_id": validated.treatment_id,
        "repetition": validated.repetition,
        "execution_boundary_fingerprint": validated.execution_boundary_fingerprint,
        "runner": {"id": runner_id, "version": runner_version},
        "contract": {"id": RUNNER_CONTRACT_ID, "version": RUNNER_CONTRACT_VERSION},
        "terminal_status": terminal_status,
        "response": response,
        "attempts": [attempt],
        "telemetry": telemetry,
        "deviations": [],
    }
    if diagnostics:
        result["diagnostics"] = list(diagnostics)
    return result
