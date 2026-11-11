"""Canonical runner-observation emission for the shared execution boundary."""

from __future__ import annotations

import base64
import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .._contract import RUNNER_CONTRACT_ID, RUNNER_CONTRACT_VERSION, ValidatedRequest, sha256_bytes, terminal_observation
from ...validation import (
    CatalogEntry,
    SchemaIdentity,
    ValidationIssue,
    resolve_catalog_entry,
    validate_cataloged_document,
)
from .orchestration import ExecutionFailureKind, TerminalExecutionResult
from .target import TargetCompositionDescriptor


EXECUTION_EVIDENCE_EXTENSION_KEY = "arcgrav.runner:execution"
EXECUTION_EVIDENCE_SCHEMA_ID = "arcgrav.shared.schema.runner-execution-evidence"
EXECUTION_EVIDENCE_SCHEMA_VERSION = "2.0.0"
_OBSERVATION_SCHEMA_ID = "arcgrav.shared.schema.treatment-observation"
_OBSERVATION_SCHEMA_VERSION = "1.0.0"
EXECUTION_CATEGORY_AVAILABILITY = frozenset(
    {"observed", "unavailable", "not_applicable"}
)
PROCESS_CHANNEL_AVAILABILITY = frozenset(
    {"excluded", "unavailable", "not_produced", "not_applicable"}
)
TERMINAL_RUNNER_STATUSES = frozenset(
    {"completed", "failed", "timed_out", "cancelled", "unsupported"}
)

_PROCESS_STDOUT_EXTENSION_KEY = "arcgrav.runner:process_stdout_base64"
_PROCESS_STDERR_EXTENSION_KEY = "arcgrav.runner:process_stderr_base64"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_ROOT = _REPOSITORY_ROOT / "AgMark" / "shared" / "schemas"


class CanonicalObservationError(ValueError):
    """Raised when canonical runner evidence cannot be emitted or validated."""


def _require_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CanonicalObservationError(f"{name} must be non-empty text")
    return value


def _require_bytes(value: object, *, name: str) -> bytes:
    if not isinstance(value, bytes):
        raise CanonicalObservationError(f"{name} must be exact bytes")
    return value


def _format_issues(issues: tuple[ValidationIssue, ...]) -> str:
    return "; ".join(
        f"{issue.code}@{issue.json_pointer or '/'}: {issue.message}"
        for issue in issues
    )


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalObservationError(
            f"shared schema authority is unavailable: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise CanonicalObservationError(
            f"shared schema authority must be an object: {path}"
        )
    return value


@lru_cache(maxsize=4)
def _cataloged_schema(
    schema_id: str,
    schema_version: str,
) -> tuple[CatalogEntry, Mapping[str, Any]]:
    expected = SchemaIdentity(schema_id, schema_version)
    catalog = _load_json(_SCHEMA_ROOT / "catalog.json")
    catalog_schema = _load_json(_SCHEMA_ROOT / "schema_catalog.schema.json")
    entry, issues = resolve_catalog_entry(
        catalog,
        expected=expected,
        catalog_schema_document=catalog_schema,
        source_id="shared-schema-catalog",
    )
    if issues or entry is None:
        detail = _format_issues(issues) if issues else "schema entry is missing"
        raise CanonicalObservationError(
            f"cannot resolve exact cataloged schema {schema_id}@{schema_version}: "
            f"{detail}"
        )
    schema_document = _load_json(_REPOSITORY_ROOT / entry.file)
    return entry, schema_document


def _validate_cataloged(
    document: Mapping[str, Any],
    *,
    schema_id: str,
    schema_version: str,
    source_id: str,
) -> None:
    entry, schema_document = _cataloged_schema(schema_id, schema_version)
    issues = validate_cataloged_document(
        document,
        schema_document=schema_document,
        entry=entry,
        source_id=source_id,
    )
    if issues:
        raise CanonicalObservationError(
            f"{source_id} does not satisfy {schema_id}@{schema_version}: "
            f"{_format_issues(issues)}"
        )


def validate_execution_evidence(evidence: Mapping[str, Any]) -> None:
    """Fail closed unless evidence matches the exact cataloged shared schema."""

    if not isinstance(evidence, Mapping):
        raise CanonicalObservationError("execution evidence must be a mapping")
    _validate_cataloged(
        evidence,
        schema_id=EXECUTION_EVIDENCE_SCHEMA_ID,
        schema_version=EXECUTION_EVIDENCE_SCHEMA_VERSION,
        source_id=EXECUTION_EVIDENCE_EXTENSION_KEY,
    )


_RETAINED_ERROR_CODES = frozenset({kind.value for kind in ExecutionFailureKind} | {
    "codex_cli_" + suffix for suffix in (
        "authentication_failed", "boundary_unsupported", "executable_missing", "host_launcher_missing",
        "isolation_failed", "noninteractive_unavailable", "process_cancelled", "process_failed",
        "process_timed_out", "reasoning_effort_unsupported", "response_unavailable", "version_unavailable",
        "version_unsupported", "telemetry_collector_unavailable", "telemetry_configuration_invalid",
        "telemetry_diagnostics_unavailable", "telemetry_initialization_failed", "telemetry_launch_configuration_failed",
        "telemetry_selected_host_unavailable")
} | {"runner_" + suffix for suffix in (
    "boundary_unsupported", "control_unsupported", "boundary_fingerprint_mismatch", "control_mismatch",
    "conversation_policy_unsupported", "fixed_control_mismatch", "identity_unsupported", "input_hash_mismatch",
    "input_identity_mismatch", "prompt_hash_mismatch", "prompt_identity_mismatch", "request_invalid")})


def _closed_fields(value, allowed, label):
    if not isinstance(value, Mapping) or set(value) - set(allowed):
        raise CanonicalObservationError("unrelated retained " + label)


from ...runtime.identity.runtime_version import retained_runtime_version


def _validate_retained_content(observation):
    """Closed admission: namespacing alone never authorizes retained content."""
    extensions = observation.get("extensions", {})
    response_key = str(observation.get("runner", {}).get("id")) + ":response_base64"
    allowed = {EXECUTION_EVIDENCE_EXTENSION_KEY, response_key, "arcgrav.telemetry:attempt-measurements", "arcgrav.telemetry:attempt-series", "arcgrav.telemetry:attempt-sources",
        "openai.codex_cli:session-record", "openai.codex_cli:execution", "openai.codex_cli:provider_usage",
        "openai.codex_cli:error", "arcgrav.runner:submitted_input", "agmark.telemetry:capture",
        "agmark.telemetry:normalized", "agmark.telemetry:error", "arcgrav.shared.runtime.orchestration:execution-window"}
    _closed_fields(extensions, allowed, "observation extensions")
    from ...evaluation.telemetry.source import ATTEMPT_SOURCES, validate_attempt_source
    if ATTEMPT_SOURCES in extensions:
        records = extensions[ATTEMPT_SOURCES]
        if not isinstance(records, Mapping):
            raise CanonicalObservationError("invalid common attempt sources")
        try:
            for identity, record in records.items():
                if validate_attempt_source(record)["source_identity"] != identity:
                    raise ValueError("source hash mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            raise CanonicalObservationError("invalid minimized attempt source") from exc
    canonical = extensions.get(EXECUTION_EVIDENCE_EXTENSION_KEY, {})
    if canonical.get("extensions") not in ({}, None):
        raise CanonicalObservationError("unknown canonical execution extensions")
    runtime_version = canonical.get("runtime", {}).get("runtime_version")
    if runtime_version not in (None, "unobserved") and retained_runtime_version(runtime_version) != runtime_version:
        raise CanonicalObservationError("invalid retained runtime version")
    canonical_error = canonical.get("error", {})
    if canonical_error.get("availability") == "observed" and (canonical_error.get("code") not in _RETAINED_ERROR_CODES or canonical_error.get("classification") not in _RETAINED_ERROR_CODES or canonical_error.get("message") != canonical_error.get("code")):
        raise CanonicalObservationError("unregistered canonical error details")
    for attempt in observation.get("attempts", []):
        if attempt.get("error_code") is not None and attempt["error_code"] not in _RETAINED_ERROR_CODES:
            raise CanonicalObservationError("unregistered attempt error")
    diagnostics = observation.get("diagnostics", [])
    if not isinstance(diagnostics, list) or any(code not in _RETAINED_ERROR_CODES for code in diagnostics):
        raise CanonicalObservationError("unregistered retained diagnostic label")
    if observation.get("deviations", []) != []:
        raise CanonicalObservationError("free-form retained deviations are forbidden")
    if "openai.codex_cli:execution" in extensions:
        meta = extensions["openai.codex_cli:execution"]
        _closed_fields(meta, {"provider_submitted", "observed_runtime_version", "launch_environment", "isolation", "authentication", "request_framing", "process_exit_status"}, "adapter execution fields")
        for key, fields in {"launch_environment": {"mode", "executable"}, "isolation": {"availability", "fresh_process", "fresh_workdir", "prior_observation_context_reused", "session_home_reused"}, "authentication": {"class", "source", "credential_material_retained"}, "request_framing": {"mode", "separator", "sha256", "byte_length"}}.items():
            if key in meta: _closed_fields(meta[key], fields, key)
        version = meta.get("observed_runtime_version")
        if version is not None and retained_runtime_version(version) != version:
            raise CanonicalObservationError("invalid retained observed runtime version")
        if "provider_submitted" in meta and type(meta["provider_submitted"]) is not bool:
            raise CanonicalObservationError("invalid submission fact")
        for key, value in meta.get("isolation", {}).items():
            if (key == "availability" and value not in {"observed", "unavailable"}) or (key != "availability" and value is not None and type(value) is not bool):
                raise CanonicalObservationError("invalid isolation fact")
        auth = meta.get("authentication")
        if auth is not None and (auth.get("class") not in {"codex_session", "not_applicable"} or auth.get("source") not in {None, "selected-user-codex-home"} or auth.get("credential_material_retained") is not False):
            raise CanonicalObservationError("invalid authentication fact")
        if "launch_environment" in meta and meta["launch_environment"] not in ({"mode": "native", "executable": "runtime/codex"}, {"mode": "wsl", "executable": "runtime/codex"}):
            raise CanonicalObservationError("invalid retained runtime reference")
    if "openai.codex_cli:provider_usage" in extensions and extensions["openai.codex_cli:provider_usage"] != {"availability": "unavailable", "reason": "not_reported_by_registered_surface"}:
        raise CanonicalObservationError("invalid provider usage evidence")
    if "openai.codex_cli:error" in extensions:
        error = extensions["openai.codex_cli:error"]
        _closed_fields(error, {"classification", "message", "retryable", "details"}, "adapter error")
        if error.get("classification") not in _RETAINED_ERROR_CODES or error.get("message") != error.get("classification") or error.get("details") != {}:
            raise CanonicalObservationError("unregistered adapter error details")
    if "arcgrav.runner:submitted_input" in extensions:
        _closed_fields(extensions["arcgrav.runner:submitted_input"], {"sha256", "byte_length", "encoding"}, "submitted input")
    if "agmark.telemetry:error" in extensions:
        error = extensions["agmark.telemetry:error"]
        _closed_fields(error, {"reason", "profile"}, "telemetry error")
        if error.get("reason") not in {"capture_or_normalization_failed", "capture_cleanup_failed"} or error.get("profile") not in {"session", "telemetry", "deep_telemetry"}:
            raise CanonicalObservationError("unregistered telemetry error")
    if "agmark.telemetry:normalized" in extensions:
        if "agmark.telemetry:capture" not in extensions:
            raise CanonicalObservationError("normalized telemetry lacks retained source")
        from ...telemetry.normalization import normalize_capture
        if normalize_capture(extensions["agmark.telemetry:capture"]) != extensions["agmark.telemetry:normalized"]:
            raise CanonicalObservationError("normalized telemetry does not reconstruct")
    if "agmark.telemetry:capture" in extensions:
        from ...telemetry.evidence import validate_manifest
        validate_manifest(extensions["agmark.telemetry:capture"])
    for metric in observation.get("telemetry", []):
        _closed_fields(metric, {"name", "value", "provenance", "unit"}, "runner metric")
        if metric.get("name") not in {"prompt_bytes", "input_bytes", "response_bytes", "framed_request_bytes"} or metric.get("provenance") != "runner-measured" or metric.get("unit") != "bytes" or type(metric.get("value")) not in {int, float}:
            raise CanonicalObservationError("unregistered runner metric")


def validate_retained_parity_observation(observation: Mapping[str, Any]) -> None:
    """Validate both schema layers before retained parity evidence is consumed."""

    if not isinstance(observation, Mapping):
        raise CanonicalObservationError("retained observation must be a mapping")
    _validate_retained_content(observation)
    from ...evaluation.telemetry import ATTEMPT_MEASUREMENTS, validate_attempt_measurements
    from ...evaluation.telemetry.model import TelemetryError
    extensions = observation.get("extensions")
    measurements = extensions.get(ATTEMPT_MEASUREMENTS) if isinstance(extensions, Mapping) else None
    try:
        from ...evaluation.telemetry.consumption import _attempt_envelopes
        envelopes = _attempt_envelopes(observation) if isinstance(extensions, Mapping) else []
    except (TelemetryError, TypeError, AttributeError, KeyError) as exc:
        raise CanonicalObservationError("invalid common measurement evidence") from exc
    extensions = observation.get("extensions")
    # This boundary consumes normalized runner-invocation observations, not
    # adapter identities. Every conforming adapter must retain the common
    # envelope; unavailable categories remain explicit within that envelope.
    _validate_cataloged(
        observation,
        schema_id=_OBSERVATION_SCHEMA_ID,
        schema_version=_OBSERVATION_SCHEMA_VERSION,
        source_id="retained-treatment-observation",
    )
    if observation.get("contract") != {"id": RUNNER_CONTRACT_ID, "version": RUNNER_CONTRACT_VERSION}:
        raise CanonicalObservationError("unsupported retained runner-invocation contract")
    if not isinstance(extensions, Mapping):
        raise CanonicalObservationError("runner observation lacks extensions")
    if EXECUTION_EVIDENCE_EXTENSION_KEY not in extensions:
        raise CanonicalObservationError("runner observation lacks shared execution evidence")
    validate_execution_evidence(extensions[EXECUTION_EVIDENCE_EXTENSION_KEY])
    execution = extensions[EXECUTION_EVIDENCE_EXTENSION_KEY]
    sources = set()
    from ...evaluation.telemetry.source import ATTEMPT_SOURCES, validate_attempt_source
    common_sources = extensions.get(ATTEMPT_SOURCES, {})
    if not isinstance(common_sources, Mapping):
        raise CanonicalObservationError("invalid common attempt sources")
    source_envelopes = {}
    try:
        for identity, source in common_sources.items():
            rebuilt = validate_attempt_source(source)
            if identity != rebuilt["source_identity"]:
                raise ValueError("common attempt source hash mismatch")
            source_envelopes[identity] = rebuilt
        used_common = set()
        for _, envelope in envelopes:
            if envelope is not None and envelope["source_identity"] in source_envelopes:
                if envelope != source_envelopes[envelope["source_identity"]]:
                    raise ValueError("common measurements do not reconstruct from source")
                used_common.add(envelope["source_identity"])
        if used_common != set(common_sources):
            raise ValueError("common attempt sources must be exactly linked")
        sources.update(used_common)
    except (ValueError, TypeError, KeyError) as exc:
        raise CanonicalObservationError("invalid common attempt source evidence") from exc
    for channel in ("stdout", "stderr"):
        retained = execution["process"][channel]
        if retained["availability"] == "excluded":
            if any(retained[k] is not None for k in ("reference", "sha256", "byte_length")):
                raise CanonicalObservationError("invalid integrity-only process evidence")
        if any(key in extensions for key in (_PROCESS_STDOUT_EXTENSION_KEY, _PROCESS_STDERR_EXTENSION_KEY)):
            raise CanonicalObservationError("raw process evidence is forbidden")
    session_key = "openai.codex_cli:session-record"
    if session_key in extensions:
        from ..Codex_CLI.session import validate_session_observation
        try:
            if len(envelopes) != 1 or envelopes[0][1] is None:
                raise ValueError("session record requires exactly one attempt envelope")
            record = extensions[session_key]
            if (record.get("generation_id") != observation["accepted_generation_id"]
                    or record.get("observation_id") != observation["observation_id"]
                    or record.get("attempt") != envelopes[0][0]["attempt"]):
                raise ValueError("session record observation binding mismatch")
            launch = record.get("launch_environment", {})
            retained_launch = execution["launch_environment"]
            if (launch.get("mode") != retained_launch["mode"]
                    or launch.get("executable") != retained_launch["executable"]
                    or launch.get("distribution") != retained_launch["environment_id"]):
                raise ValueError("session record launch environment mismatch")
            source = validate_session_observation(extensions, execution, envelopes[0][1])
            if source is not None:
                sources.add(source)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise CanonicalObservationError("invalid retained session measurement evidence: " + str(exc)) from exc
    for _, envelope in envelopes:
        if envelope is None:
            continue
        counters = [m for m in envelope["roles"].values() if m["kind"] == "runtime_counter" and m["value"] is not None]
        if counters or envelope["tool_events"] or envelope["tool_trace_complete"]:
            if envelope["source_identity"] not in sources:
                raise CanonicalObservationError("measurement source is not retained execution evidence")
            if envelope["runtime_version"] != execution["runtime"]["runtime_version"]:
                raise CanonicalObservationError("measurement runtime differs from retained execution")
            if any(envelope["source_identity"] not in m["evidence_references"] for m in counters):
                raise CanonicalObservationError("counter source reference mismatch")


def _model_id(validated: ValidatedRequest) -> str | None:
    runtime = validated.execution_boundary.get("provider_runtime")
    if isinstance(runtime, Mapping):
        value = runtime.get("model")
        if isinstance(value, str) and value:
            return value
    value = validated.boundary_controls.get("model_id")
    return value if isinstance(value, str) and value else None


def _authentication_evidence(
    target: TargetCompositionDescriptor,
    *,
    source: str | None,
) -> dict[str, Any]:
    if target.authentication_class == "not_applicable":
        if source is not None:
            raise CanonicalObservationError(
                "authentication_source must be absent for not-applicable authentication"
            )
        return {
            "availability": "not_applicable",
            "class": None,
            "source": None,
        }
    return {
        "availability": "observed",
        "class": target.authentication_class,
        "source": source,
    }


def _usage_evidence(
    *,
    external_provider_submission: bool,
    provider_reported: bool | None,
    provenance: str | None,
) -> dict[str, Any]:
    if provider_reported is None:
        if provenance is not None:
            raise CanonicalObservationError(
                "usage_provenance requires an observed usage value"
            )
        return {
            "availability": "unavailable",
            "provider_reported": None,
            "provenance": None,
        }
    if not isinstance(provider_reported, bool):
        raise CanonicalObservationError(
            "usage_provider_reported must be boolean or None"
        )
    if not external_provider_submission and provider_reported:
        raise CanonicalObservationError(
            "provider-reported usage requires an external-provider submission surface"
        )
    return {
        "availability": "observed",
        "provider_reported": provider_reported,
        "provenance": (
            _require_text(provenance, name="usage_provenance")
            if provenance is not None
            else None
        ),
    }


def _channel_evidence(
    *,
    data: bytes,
    availability: str,
    extension_key: str,
    observation_extensions: dict[str, Any],
) -> dict[str, Any]:
    if availability not in PROCESS_CHANNEL_AVAILABILITY:
        raise CanonicalObservationError(
            f"invalid process channel availability: {availability}"
        )
    if availability != "excluded":
        return {
            "availability": availability,
            "sha256": None,
            "byte_length": None,
            "reference": None,
        }

    return {
        "availability": "excluded",
        "sha256": None,
        "byte_length": None,
        "reference": None,
    }


def _process_evidence(
    execution: TerminalExecutionResult,
    *,
    observation_extensions: dict[str, Any],
) -> dict[str, Any]:
    if not execution.invocation_occurred:
        category_availability = "not_applicable"
        channel_availability = "not_produced"
    elif not execution.process_channels_observed or execution.failure_kind in {
        ExecutionFailureKind.INVOCATION_FAILED,
        ExecutionFailureKind.CAPTURE_INVALID,
    }:
        category_availability = "observed"
        channel_availability = "unavailable"
    else:
        category_availability = "observed"
        channel_availability = "excluded"

    return {
        "availability": category_availability,
        "exit_status": (
            execution.capture.exit_status if execution.invocation_occurred else None
        ),
        "transport_status": (
            (execution.capture.transport_status if execution.capture.transport_status in {None, "timed_out", "cancelled", "failed", "invalid_capture", "local_process"} else "other")
            if execution.invocation_occurred
            else None
        ),
        "stdout": _channel_evidence(
            data=execution.capture.stdout,
            availability=channel_availability,
            extension_key=_PROCESS_STDOUT_EXTENSION_KEY,
            observation_extensions=observation_extensions,
        ),
        "stderr": _channel_evidence(
            data=execution.capture.stderr,
            availability=channel_availability,
            extension_key=_PROCESS_STDERR_EXTENSION_KEY,
            observation_extensions=observation_extensions,
        ),
    }


def _error_evidence(
    execution: TerminalExecutionResult,
    *,
    code: str | None,
    classification: str | None,
    message: str | None,
) -> tuple[dict[str, Any], str | None]:
    if execution.failure_kind is None:
        if any(value is not None for value in (code, classification, message)):
            raise CanonicalObservationError(
                "completed execution cannot retain canonical error details"
            )
        return (
            {
                "availability": "not_applicable",
                "code": None,
                "classification": None,
                "message": None,
            },
            None,
        )

    default = execution.failure_kind.value
    canonical_code = _require_text(code or default, name="error_code")
    canonical_classification = _require_text(
        classification or default,
        name="error_classification",
    )
    if canonical_code not in _RETAINED_ERROR_CODES:
        canonical_code = default
    if canonical_classification not in _RETAINED_ERROR_CODES:
        canonical_classification = default
    canonical_message = canonical_code
    return (
        {
            "availability": "observed",
            "code": canonical_code,
            "classification": canonical_classification,
            "message": canonical_message,
        },
        canonical_code,
    )


def emit_terminal_observation(
    validated: ValidatedRequest,
    *,
    target: TargetCompositionDescriptor,
    execution: TerminalExecutionResult,
    runner_id: str,
    runner_version: str,
    framed_request: bytes,
    request_framing_mode: str,
    authentication_source: str | None = None,
    launch_environment_id: str | None = None,
    usage_provider_reported: bool | None = None,
    usage_provenance: str | None = None,
    error_code: str | None = None,
    error_classification: str | None = None,
    error_message: str | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit one exact-schema-valid canonical terminal runner observation.

    Target identity contributes only truthful evidence values. Terminal meaning is
    taken from the shared execution result and the versioned shared vocabularies.
    Free-form transport/error identifiers are retained as data and never select
    alternate terminal status or availability semantics.
    """

    if not isinstance(validated, ValidatedRequest):
        raise CanonicalObservationError("validated must be a ValidatedRequest")
    if not isinstance(target, TargetCompositionDescriptor):
        raise CanonicalObservationError(
            "target must be a TargetCompositionDescriptor"
        )
    if not isinstance(execution, TerminalExecutionResult):
        raise CanonicalObservationError(
            "execution must be a TerminalExecutionResult"
        )
    runner_id = _require_text(runner_id, name="runner_id")
    runner_version = _require_text(runner_version, name="runner_version")
    framed_request = _require_bytes(framed_request, name="framed_request")
    request_framing_mode = _require_text(
        request_framing_mode,
        name="request_framing_mode",
    )
    if launch_environment_id is not None:
        launch_environment_id = _require_text(
            launch_environment_id,
            name="launch_environment_id",
        )
    if authentication_source is not None:
        authentication_source = _require_text(
            authentication_source,
            name="authentication_source",
        )
    if execution.terminal_status not in TERMINAL_RUNNER_STATUSES:
        raise CanonicalObservationError(
            f"terminal status is outside the shared vocabulary: "
            f"{execution.terminal_status}"
        )

    observation_extensions = copy.deepcopy(dict(extensions or {}))
    response_extension_key = f"{runner_id}:response_base64"
    reserved = {
        EXECUTION_EVIDENCE_EXTENSION_KEY,
        _PROCESS_STDOUT_EXTENSION_KEY,
        _PROCESS_STDERR_EXTENSION_KEY,
        response_extension_key,
    }
    collisions = sorted(reserved.intersection(observation_extensions))
    if collisions:
        raise CanonicalObservationError(
            "caller extensions collide with canonical runner evidence: "
            + ", ".join(collisions)
        )

    process = _process_evidence(
        execution,
        observation_extensions=observation_extensions,
    )
    external_provider_submission_occurred = (
        execution.invocation_occurred
        and target.external_provider_submission
    )
    error, attempt_error_code = _error_evidence(
        execution,
        code=error_code,
        classification=error_classification,
        message=error_message,
    )
    isolation = execution.isolation
    execution_evidence: dict[str, Any] = {
        "schema_id": EXECUTION_EVIDENCE_SCHEMA_ID,
        "schema_version": EXECUTION_EVIDENCE_SCHEMA_VERSION,
        "extensions": {},
        "target": {
            "availability": "observed",
            "class": target.target_class,
            "evidence_class": target.evidence_class,
        },
        "submission": {
            "availability": "observed",
            "occurred": execution.invocation_occurred,
            "external_provider": external_provider_submission_occurred,
        },
        "runtime": {
            "availability": "observed",
            "runtime_id": target.runtime_id,
            "runtime_version": retained_runtime_version(target.runtime_version) if target.runtime_version != "unobserved" else "unobserved",
            "model_id": _model_id(validated),
            "access_method": target.access_method,
        },
        "launch_environment": {
            "availability": "observed",
            "mode": target.launch_mode,
            "environment_id": None,
            "executable": "runtime/codex" if "openai.codex_cli:session-record" in observation_extensions or runner_id == "openai.codex-cli" else "runtime/executable",
        },
        "authentication": _authentication_evidence(
            target,
            source=authentication_source,
        ),
        "isolation": {
            "availability": "observed" if isolation is not None else "unavailable",
            "fresh_process": isolation.fresh_process if isolation is not None else None,
            "fresh_workdir": isolation.fresh_workdir if isolation is not None else None,
            "prior_observation_context_reused": (
                isolation.prior_observation_context_reused
                if isolation is not None
                else None
            ),
            "session_home_reused": (
                isolation.session_home_reused if isolation is not None else None
            ),
        },
        "request_framing": {
            "availability": "observed",
            "mode": request_framing_mode,
            "sha256": sha256_bytes(framed_request),
            "byte_length": len(framed_request),
        },
        "process": process,
        "usage": _usage_evidence(
            external_provider_submission=external_provider_submission_occurred,
            provider_reported=usage_provider_reported,
            provenance=usage_provenance,
        ),
        "error": error,
    }
    validate_execution_evidence(execution_evidence)
    observation_extensions[EXECUTION_EVIDENCE_EXTENSION_KEY] = execution_evidence

    observation = terminal_observation(
        validated,
        runner_id=runner_id,
        runner_version=runner_version,
        terminal_status=execution.terminal_status,
        response_bytes=execution.response_bytes,
        error_code=attempt_error_code,
        extensions=observation_extensions,
    )
    if execution.terminal_status == "unsupported":
        observation["diagnostics"] = [attempt_error_code]
    if (
        execution.response_bytes is None
        and execution.failure_kind is ExecutionFailureKind.RESPONSE_UNAVAILABLE
    ):
        observation["response"] = {"availability": "unavailable"}

    observation["attempts"][0].update(
        {
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "duration_ms": execution.duration_ms,
        }
    )
    observation["telemetry"].append(
        {
            "name": "framed_request_bytes",
            "value": len(framed_request),
            "provenance": "runner-measured",
            "unit": "bytes",
        }
    )
    for name in ("stdout", "stderr"):
        channel = process[name]
        if channel["availability"] == "retained":
            observation["telemetry"].append(
                {
                    "name": f"{name}_bytes",
                    "value": channel["byte_length"],
                    "provenance": "runner-measured",
                    "unit": "bytes",
                }
            )

    _validate_cataloged(
        observation,
        schema_id="arcgrav.shared.schema.treatment-observation",
        schema_version="1.0.0",
        source_id="canonical-treatment-observation",
    )
    _validate_retained_content(observation)
    return observation
