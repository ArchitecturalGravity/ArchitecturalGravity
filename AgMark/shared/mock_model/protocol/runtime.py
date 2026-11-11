"""Provider-neutral mock-model runtime protocol surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Callable, Iterable, Mapping

from ..scenarios import (
    PreflightScenarioOutcome,
    evaluate_inference_scenario,
    evaluate_preflight_scenario,
)


RUNTIME_IDENTITY_OPERATION = "runtime_identity"
CAPABILITY_INSPECTION_OPERATION = "capability_inspection"
MODEL_DISCOVERY_OPERATION = "model_discovery"
INFERENCE_OPERATION = "inference"
DEFAULT_RUNTIME_ID = "arcgrav.mock-model.runtime"
DEFAULT_RUNTIME_VERSION = "1.0.0"
DEFAULT_EXECUTABLE_ID = "arcgrav.mock-model.runtime.python"

_SUPPORTED_PROBE_OPERATIONS = frozenset(
    {
        RUNTIME_IDENTITY_OPERATION,
        CAPABILITY_INSPECTION_OPERATION,
        MODEL_DISCOVERY_OPERATION,
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


@dataclass(frozen=True, slots=True)
class ProbeFailure:
    """Provider-neutral explicit failure for one non-inference probe."""

    code: str
    diagnostic: bytes = b""

    def __post_init__(self) -> None:
        _required_text(self.code, field="code")
        _required_bytes(self.diagnostic, field="diagnostic")


class ProtocolProbeError(RuntimeError):
    """Raised when a configured provider-neutral probe fails explicitly."""

    def __init__(self, *, operation: str, failure: ProbeFailure) -> None:
        self.operation = operation
        self.code = failure.code
        self.diagnostic = failure.diagnostic
        super().__init__(f"{operation} failed: {failure.code}")


class ProtocolInferenceError(RuntimeError):
    """Raised when provider-neutral inference cannot accept an invocation."""

    def __init__(self, *, code: str, diagnostic: bytes = b"") -> None:
        self.operation = INFERENCE_OPERATION
        self.code = _required_text(code, field="code")
        self.diagnostic = _required_bytes(diagnostic, field="diagnostic")
        super().__init__(f"{INFERENCE_OPERATION} failed: {self.code}")


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """Stable synthetic executable/runtime identity returned without inference."""

    runtime_id: str
    runtime_version: str
    executable_id: str
    synthetic: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    """Stable provider-neutral capability declaration for one runtime."""

    runtime_id: str
    runtime_version: str
    executable_id: str
    capabilities: tuple[str, ...]
    synthetic: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ModelProfileMapping:
    """Registered provider-neutral mapping from a profile ID to model inputs."""

    base_model_id: str
    scenario_id: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.base_model_id, field="base_model_id")
        if self.scenario_id is not None:
            _required_text(self.scenario_id, field="scenario_id")


@dataclass(frozen=True, slots=True)
class ModelCatalogEntry:
    """One canonical synthetic model identity and its presentation metadata."""

    model_id: str
    label: str
    hidden: bool = False
    is_default: bool = False
    profile: ModelProfileMapping | None = None
    synthetic: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        _required_text(self.model_id, field="model_id")
        _required_text(self.label, field="label")
        if type(self.hidden) is not bool:
            raise TypeError("hidden must be bool")
        if type(self.is_default) is not bool:
            raise TypeError("is_default must be bool")
        if self.profile is not None and not isinstance(
            self.profile,
            ModelProfileMapping,
        ):
            raise TypeError("profile must be a ModelProfileMapping")


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """Stable non-inference discovery result for one mock runtime."""

    models: tuple[ModelCatalogEntry, ...]
    default_model_id: str | None
    synthetic: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.models, tuple):
            raise TypeError("models must be a tuple")
        for model in self.models:
            if not isinstance(model, ModelCatalogEntry):
                raise TypeError("models must contain ModelCatalogEntry values")
        if self.default_model_id is not None:
            _required_text(self.default_model_id, field="default_model_id")


@dataclass(frozen=True, slots=True)
class InferenceResult:
    """Exact provider-neutral result and observable process facts."""

    model_id: str
    base_model_id: str
    scenario_id: str | None
    response: bytes
    diagnostic: bytes = b""
    stdout: bytes = b""
    stderr: bytes = b""
    exit_code: int = 0
    synthetic: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        _required_text(self.model_id, field="model_id")
        _required_text(self.base_model_id, field="base_model_id")
        if self.scenario_id is not None:
            _required_text(self.scenario_id, field="scenario_id")
        _required_bytes(self.response, field="response")
        _required_bytes(self.diagnostic, field="diagnostic")
        _required_bytes(self.stdout, field="stdout")
        _required_bytes(self.stderr, field="stderr")
        if type(self.exit_code) is not int:
            raise TypeError("exit_code must be int")


class MockRuntimeProtocol:
    """Provider-neutral operations for a deterministic mock runtime."""

    def __init__(
        self,
        *,
        runtime_id: str = DEFAULT_RUNTIME_ID,
        runtime_version: str = DEFAULT_RUNTIME_VERSION,
        executable_id: str = DEFAULT_EXECUTABLE_ID,
        capabilities: Iterable[str] = (),
        models: Iterable[ModelCatalogEntry] = (),
        probe_failures: Mapping[str, ProbeFailure] | None = None,
        preflight_scenario_id: str | None = None,
    ) -> None:
        self._runtime_id = _required_text(runtime_id, field="runtime_id")
        self._runtime_version = _required_text(
            runtime_version,
            field="runtime_version",
        )
        self._executable_id = _required_text(executable_id, field="executable_id")

        normalized_capabilities: list[str] = []
        seen_capabilities: set[str] = set()
        for capability in capabilities:
            capability = _required_text(capability, field="capability")
            if capability in seen_capabilities:
                raise ValueError(f"duplicate capability: {capability}")
            seen_capabilities.add(capability)
            normalized_capabilities.append(capability)
        self._capabilities = tuple(sorted(normalized_capabilities))

        normalized_models: list[ModelCatalogEntry] = []
        seen_model_ids: set[str] = set()
        defaults: list[str] = []
        for model in models:
            if not isinstance(model, ModelCatalogEntry):
                raise TypeError("models must contain ModelCatalogEntry values")
            if model.model_id in seen_model_ids:
                raise ValueError(f"duplicate model_id: {model.model_id}")
            seen_model_ids.add(model.model_id)
            normalized_models.append(model)
            if model.is_default:
                defaults.append(model.model_id)
        if len(defaults) > 1:
            raise ValueError("model catalog must not declare multiple defaults")

        normalized_models.sort(key=lambda model: model.model_id)
        known_model_ids = {model.model_id for model in normalized_models}
        for model in normalized_models:
            if (
                model.profile is not None
                and model.profile.base_model_id not in known_model_ids
            ):
                raise ValueError(
                    "profile base_model_id must reference a catalog model"
                )
        self._models = tuple(normalized_models)
        self._default_model_id = defaults[0] if defaults else None

        normalized_failures: list[tuple[str, ProbeFailure]] = []
        for operation, failure in (probe_failures or {}).items():
            if operation not in _SUPPORTED_PROBE_OPERATIONS:
                raise ValueError(f"unsupported probe operation: {operation}")
            if not isinstance(failure, ProbeFailure):
                raise TypeError("probe failure values must be ProbeFailure instances")
            normalized_failures.append((operation, failure))
        self._probe_failures = tuple(sorted(normalized_failures))

        self._preflight_scenario: PreflightScenarioOutcome | None = None
        if preflight_scenario_id is not None:
            self._preflight_scenario = evaluate_preflight_scenario(
                preflight_scenario_id
            )
            if any(
                operation == self._preflight_scenario.operation
                for operation, _ in self._probe_failures
            ):
                raise ValueError(
                    "preflight scenario conflicts with configured probe failure"
                )

    def runtime_identity(self) -> RuntimeIdentity:
        """Return stable executable/runtime identity without performing inference."""

        self._raise_if_failed(RUNTIME_IDENTITY_OPERATION)
        runtime_version = self._runtime_version
        scenario = self._preflight_for(RUNTIME_IDENTITY_OPERATION)
        if scenario is not None and scenario.runtime_version is not None:
            runtime_version = scenario.runtime_version
        return RuntimeIdentity(
            runtime_id=self._runtime_id,
            runtime_version=runtime_version,
            executable_id=self._executable_id,
        )

    def inspect_capabilities(self) -> RuntimeCapabilities:
        """Return stable provider-neutral capabilities without inference."""

        self._raise_if_failed(CAPABILITY_INSPECTION_OPERATION)
        return RuntimeCapabilities(
            runtime_id=self._runtime_id,
            runtime_version=self._runtime_version,
            executable_id=self._executable_id,
            capabilities=self._capabilities,
        )

    def discover_models(self) -> ModelCatalog:
        """Return the immutable registered model catalog without inference."""

        self._raise_if_failed(MODEL_DISCOVERY_OPERATION)
        if not self._models:
            raise ProtocolProbeError(
                operation=MODEL_DISCOVERY_OPERATION,
                failure=ProbeFailure(code="model_catalog_unavailable"),
            )
        return ModelCatalog(
            models=self._models,
            default_model_id=self._default_model_id,
        )

    def infer(
        self,
        *,
        model_id: str,
        request_bytes: bytes,
        invocation_id: str,
        scenario_id: str | None = None,
        partial_output_sink: Callable[[bytes, bytes], None] | None = None,
    ) -> InferenceResult:
        """Run deterministic provider-neutral inference over exact request bytes."""

        model_id = _required_text(model_id, field="model_id")
        request_bytes = _required_bytes(request_bytes, field="request_bytes")
        invocation_id = _required_text(invocation_id, field="invocation_id")
        if scenario_id is not None:
            scenario_id = _required_text(scenario_id, field="scenario_id")

        model = self._find_model(model_id)
        if model is None:
            raise ProtocolInferenceError(code="unknown_model")

        base_model_id = model.model_id
        registered_scenario_id: str | None = None
        if model.profile is not None:
            base_model_id = model.profile.base_model_id
            registered_scenario_id = model.profile.scenario_id

        if scenario_id is not None and scenario_id != registered_scenario_id:
            raise ProtocolInferenceError(code="unauthorized_scenario")
        effective_scenario_id = (
            registered_scenario_id if scenario_id is None else scenario_id
        )

        default_response = self._deterministic_response(
            model_id=model_id,
            base_model_id=base_model_id,
            scenario_id=effective_scenario_id,
            invocation_id=invocation_id,
            request_bytes=request_bytes,
        )

        if effective_scenario_id is None:
            response = default_response
            stdout = default_response
            stderr = b""
            exit_code = 0
        else:
            try:
                outcome = evaluate_inference_scenario(
                    effective_scenario_id,
                    model_id=model_id,
                    invocation_id=invocation_id,
                    request_bytes=request_bytes,
                    default_response=default_response,
                    partial_output_sink=partial_output_sink,
                )
            except ValueError as exc:
                raise ProtocolInferenceError(code="unknown_scenario") from exc
            response = outcome.response
            stdout = outcome.stdout
            stderr = outcome.stderr
            exit_code = outcome.exit_code

        return InferenceResult(
            model_id=model_id,
            base_model_id=base_model_id,
            scenario_id=effective_scenario_id,
            response=response,
            diagnostic=stderr,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )

    def _find_model(self, model_id: str) -> ModelCatalogEntry | None:
        for model in self._models:
            if model.model_id == model_id:
                return model
        return None

    def _deterministic_response(
        self,
        *,
        model_id: str,
        base_model_id: str,
        scenario_id: str | None,
        invocation_id: str,
        request_bytes: bytes,
    ) -> bytes:
        digest = hashlib.sha256()
        for value in (
            self._runtime_id.encode("utf-8"),
            self._runtime_version.encode("utf-8"),
            model_id.encode("utf-8"),
            base_model_id.encode("utf-8"),
            (scenario_id or "").encode("utf-8"),
            invocation_id.encode("utf-8"),
            request_bytes,
        ):
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)
        return b"arcgrav-mock-response-v1:" + digest.hexdigest().encode("ascii") + b"\n"

    def _preflight_for(self, operation: str) -> PreflightScenarioOutcome | None:
        scenario = self._preflight_scenario
        if scenario is not None and scenario.operation == operation:
            return scenario
        return None

    def _raise_if_failed(self, operation: str) -> None:
        scenario = self._preflight_for(operation)
        if scenario is not None:
            if scenario.failure_code is not None:
                raise ProtocolProbeError(
                    operation=operation,
                    failure=ProbeFailure(
                        code=scenario.failure_code,
                        diagnostic=scenario.diagnostic,
                    ),
                )
            if scenario.protocol_payload is not None:
                raise ProtocolProbeError(
                    operation=operation,
                    failure=ProbeFailure(
                        code="protocol_invalid_result",
                        diagnostic=scenario.protocol_payload,
                    ),
                )

        for configured_operation, failure in self._probe_failures:
            if configured_operation == operation:
                raise ProtocolProbeError(operation=operation, failure=failure)
