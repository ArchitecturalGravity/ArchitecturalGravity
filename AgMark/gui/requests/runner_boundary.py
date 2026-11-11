"""Production request resolution from validated repository authority."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
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
    implementation_artifact_sha256,
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

from .repository_resources import _mapping, _safe_file, _sequence, _text

def _coerce(value: object, declaration: Mapping[str, object], name: str) -> object:
    kind = declaration.get("kind")
    if kind in {"text", "choice", "secret"}:
        if not isinstance(value, str) or not value:
            raise RepositoryCompositionError(f"control {name!r} requires text")
        resolved: object = value
    elif kind == "integer":
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise RepositoryCompositionError(f"control {name!r} requires integer") from exc
        if isinstance(value, bool) or not number.is_integer():
            raise RepositoryCompositionError(f"control {name!r} requires integer")
        resolved = int(number)
    elif kind in {"number", "float"}:
        try:
            resolved = float(value)
        except (TypeError, ValueError) as exc:
            raise RepositoryCompositionError(f"control {name!r} requires number") from exc
        if isinstance(value, bool):
            raise RepositoryCompositionError(f"control {name!r} requires number")
    else:
        raise RepositoryCompositionError(f"control {name!r} has unsupported kind")

    if "values" in declaration and resolved not in _sequence(
        declaration["values"], f"{name}.values"
    ):
        raise RepositoryCompositionError(f"control {name!r} is not permitted")
    if isinstance(resolved, (int, float)) and not isinstance(resolved, bool):
        if "minimum" in declaration and resolved < declaration["minimum"]:
            raise RepositoryCompositionError(f"control {name!r} is below minimum")
        if "maximum" in declaration and resolved > declaration["maximum"]:
            raise RepositoryCompositionError(f"control {name!r} is above maximum")
    return resolved

def _registered_runner_planning_probe(
    source,
    *,
    repository_root: Path,
    control_values: Mapping[str, object],
) -> object:
    registration = _mapping(source.registration, "runner registration")
    validation = source.registration_validation
    if (
        not validation.valid
        or not validation.matches(
            registration,
            source_id=source.registration_source_id,
        )
    ):
        raise RepositoryCompositionError(
            "runner planning probe requires exact validated registration authority"
        )

    extensions = _mapping(registration.get("extensions"), "runner extensions")
    declaration = extensions.get(_PLANNING_PROBE)
    if declaration is None:
        return None
    declaration = _mapping(declaration, "runner planning probe")
    if set(declaration) != {"entry_point", "implementation_artifact_id"}:
        raise RepositoryCompositionError(
            "runner planning probe declaration is invalid"
        )

    entry_point = _text(declaration.get("entry_point"), "runner planning probe entry point")
    artifact_id = _text(
        declaration.get("implementation_artifact_id"),
        "runner planning probe implementation artifact",
    )
    artifacts = [
        _mapping(raw, "runner implementation artifact")
        for raw in _sequence(
            registration.get("implementation_artifacts"),
            "runner implementation artifacts",
        )
        if isinstance(raw, Mapping) and raw.get("artifact_id") == artifact_id
    ]
    if len(artifacts) != 1:
        raise RepositoryCompositionError(
            "runner planning probe implementation does not resolve uniquely"
        )
    artifact = artifacts[0]
    reference = _text(
        artifact.get("reference"),
        "runner planning probe implementation reference",
    )
    expected_sha256 = _text(
        artifact.get("sha256"),
        "runner planning probe implementation sha256",
    )
    if not reference.endswith(".py") or not expected_sha256.startswith("sha256:"):
        raise RepositoryCompositionError(
            "runner planning probe implementation binding is invalid"
        )
    path = _safe_file(repository_root, reference)
    try:
        observed_sha256 = implementation_artifact_sha256(reference, path.read_bytes())
    except OSError as exc:
        raise RepositoryCompositionError(
            "runner planning probe implementation is unreadable"
        ) from exc
    if observed_sha256 != expected_sha256:
        raise RepositoryCompositionError(
            "runner planning probe implementation drifted from registered authority"
        )

    module_name, separator, attribute_name = entry_point.partition(":")
    if (
        separator != ":"
        or module_name != reference[:-3].replace("/", ".")
        or not attribute_name
        or "." in attribute_name
    ):
        raise RepositoryCompositionError(
            "runner planning probe entry point does not match registered implementation"
        )
    try:
        module = import_module(module_name)
        module_path = Path(module.__file__).resolve(strict=True)
    except (ImportError, AttributeError, OSError, TypeError, ValueError) as exc:
        raise RepositoryCompositionError(
            "runner planning probe implementation cannot be imported"
        ) from exc
    if module_path != path:
        raise RepositoryCompositionError(
            "runner planning probe import does not match registered implementation"
        )
    probe = getattr(module, attribute_name, None)
    if not callable(probe):
        raise RepositoryCompositionError("runner planning probe is not callable")
    try:
        return probe(registration, control_values=dict(control_values))
    except Exception as exc:
        raise RepositoryCompositionError(
            "registered runner planning probe failed before canonical planning"
        ) from exc

def _control_applies_to_resolved_launch(
    name: str,
    extensions: Mapping[str, object],
    resolved_supported: Mapping[str, object],
) -> bool:
    """Return whether a registered control applies to the resolved launch mode."""

    launch = extensions.get(_LAUNCH_ENVIRONMENT)
    if not isinstance(launch, Mapping):
        return True
    selectors = launch.get("selectors")
    if not isinstance(selectors, Mapping):
        return True
    selector = selectors.get(name)
    if not isinstance(selector, Mapping):
        return True
    if selector.get("wsl_only") is True:
        return resolved_supported.get("launch_mode") == "wsl"
    return True

def _runner_boundary(
    intent: SidebarInputSnapshot,
    source,
    *,
    repository_root: Path,
    planning_probe: Callable[[object, Mapping[str, object]], object] | None = None,
    launch_selection: dict[str, str] | None = None,
):
    registration = _mapping(source.registration, "runner registration")
    extensions = _mapping(registration.get("extensions"), "runner extensions")
    supported = _sequence(extensions.get(_SUPPORTED_CONTROLS, ()), "supported controls")
    fixed = _sequence(extensions.get(_FIXED_CONTROLS, ()), "fixed controls")
    methods = _sequence(extensions.get(_ACCESS_METHODS, ()), "access methods")
    if len(methods) != 1:
        raise RepositoryCompositionError(
            "runner must expose exactly one registered access method"
        )
    has_planning_probe = extensions.get(_PLANNING_PROBE) is not None

    controls: dict[str, object] = {}
    for raw in fixed:
        item = _mapping(raw, "fixed control")
        name = _text(item.get("name"), "fixed control name")
        if name in controls or "value" not in item:
            raise RepositoryCompositionError("fixed control authority is ambiguous")
        controls[name] = item["value"]

    additional = {item.control_name: item.value for item in intent.additional_controls}
    if len(additional) != len(intent.additional_controls):
        raise RepositoryCompositionError("runner control intent is ambiguous")

    declarations: dict[str, Mapping[str, object]] = {}
    resolved_supported: dict[str, object] = {}
    model_count = 0
    numeric_seen = set()
    for raw in supported:
        declaration = _mapping(raw, "supported control")
        name = _text(declaration.get("name"), "control name")
        if name in declarations:
            raise RepositoryCompositionError("supported control authority is ambiguous")
        declarations[name] = declaration

        if name in controls:
            raw_value = controls[name]
        elif name in _MODEL_CONTROLS:
            model_count += 1
            raw_value = intent.model
        elif name == "temperature":
            numeric_seen.add(name)
            raw_value = intent.temperature
        elif name == "max_tokens":
            numeric_seen.add(name)
            raw_value = intent.max_tokens
        elif name in additional:
            raw_value = additional[name]
        elif declaration.get("default") is not None:
            raw_value = declaration["default"]
        elif "values" in declaration:
            values = _sequence(declaration["values"], f"{name}.values")
            raw_value = values[0] if len(values) == 1 else None
        else:
            raw_value = None

        if raw_value is None or raw_value == "":
            continue
        resolved = _coerce(raw_value, declaration, name)
        resolved_supported[name] = resolved
        if declaration.get("comparison_relevant") is True:
            controls[name] = resolved

    supported_names = set(declarations)
    if set(additional) - supported_names:
        raise RepositoryCompositionError("runner intent contains unregistered controls")
    if model_count > 1 or (model_count == 0 and intent.model is not None):
        raise RepositoryCompositionError("model intent is not uniquely registered")
    if "temperature" not in numeric_seen and intent.temperature is not None:
        raise RepositoryCompositionError("temperature intent is not registered")
    if "max_tokens" not in numeric_seen and intent.max_tokens is not None:
        raise RepositoryCompositionError("max_tokens intent is not registered")

    planning_result: Mapping[str, object] | None = None
    if has_planning_probe:
        probe_values = {
            name: value
            for name, value in resolved_supported.items()
            if declarations[name].get("kind") != "secret"
        }
        if planning_probe is None:
            raw_result = _registered_runner_planning_probe(
                source,
                repository_root=repository_root,
                control_values=probe_values,
            )
        else:
            try:
                raw_result = planning_probe(source, dict(probe_values))
            except Exception as exc:
                raise RepositoryCompositionError(
                    "runner planning probe failed before canonical planning"
                ) from exc
        planning_result = _mapping(raw_result, "runner planning probe result")
        if planning_result.get("provider_submitted") is not False:
            raise RepositoryCompositionError(
                "runner planning probe must be non-submitting"
            )
        if planning_result.get("status") != "ready":
            error_code = planning_result.get("error_code")
            if not isinstance(error_code, str) or not error_code:
                error_code = "runner_planning_probe_unavailable"
            raise RepositoryCompositionError(
                f"runner planning probe blocked canonical planning: {error_code}"
            )
        returned_controls = _mapping(
            planning_result.get("resolved_controls", {}),
            "runner planning probe resolved controls",
        )
        for name, raw_value in returned_controls.items():
            declaration = declarations.get(name)
            if declaration is None or declaration.get("kind") == "secret":
                raise RepositoryCompositionError(
                    "runner planning probe returned an unregistered control"
                )
            resolved = _coerce(raw_value, declaration, name)
            if name in resolved_supported and resolved_supported[name] != resolved:
                raise RepositoryCompositionError(
                    f"runner planning probe changed explicit control {name!r}"
                )
            resolved_supported[name] = resolved
            if declaration.get("comparison_relevant") is True:
                controls[name] = resolved

    for name, declaration in declarations.items():
        if (
            declaration.get("required") is True
            and declaration.get("kind") != "secret"
            and name not in resolved_supported
            and _control_applies_to_resolved_launch(
                name,
                extensions,
                resolved_supported,
            )
        ):
            raise RepositoryCompositionError(
                f"required runner control {name!r} is unresolved"
            )

    resolved_models = tuple(
        controls[name] for name in _MODEL_CONTROLS if name in controls
    )
    if len(resolved_models) > 1:
        raise RepositoryCompositionError("model authority is ambiguous")
    resolved_model = resolved_models[0] if resolved_models else intent.model

    method = _mapping(methods[0], "access method")
    method_type = _text(method.get("type"), "access method type")
    outcome = source.registration_validation
    runner = IdentityRef(
        _text(registration.get("registration_id"), "runner id"),
        _text(registration.get("registration_version"), "runner version"),
        sha256=outcome.registration_sha256,
        reference=source.registration_source_id,
    )
    if planning_result is None:
        runtime = ProviderRuntimeIdentity(
            runtime_id=runner.id,
            runtime_version=runner.version,
            provider=None,
            access_method=method_type,
            model=resolved_model,
        )
    else:
        probed_runtime = _mapping(
            planning_result.get("provider_runtime"),
            "runner planning probe provider runtime",
        )
        runtime_id = _text(
            probed_runtime.get("runtime_id"),
            "runner planning probe runtime_id",
        )
        runtime_version = _text(
            probed_runtime.get("runtime_version"),
            "runner planning probe runtime_version",
        )
        access_method = _text(
            probed_runtime.get("access_method"),
            "runner planning probe access_method",
        )
        if runtime_id != runner.id or access_method != method_type:
            raise RepositoryCompositionError(
                "runner planning probe returned incompatible runtime identity"
            )
        if probed_runtime.get("model") != resolved_model:
            raise RepositoryCompositionError(
                "runner planning probe changed canonical model identity"
            )
        provider = probed_runtime.get("provider")
        if provider is not None and (
            not isinstance(provider, str) or not provider
        ):
            raise RepositoryCompositionError(
                "runner planning probe provider must be non-empty text or null"
            )
        runtime = ProviderRuntimeIdentity(
            runtime_id=runtime_id,
            runtime_version=runtime_version,
            provider=provider,
            access_method=access_method,
            model=resolved_model,
        )
    # The full label is invocation-only; it must never enter boundary serialization.
    if has_planning_probe and launch_selection is not None:
        full_version = planning_result.get("runtime_version", runtime.runtime_version)
        if isinstance(full_version, str) and full_version != runtime.to_dict()["runtime_version"]:
            launch_selection["expected_runtime_version"] = full_version
    for name in ("codex_binary", "wsl_distribution"):
        raw = resolved_supported.get(name)
        if isinstance(raw, str) and launch_selection is not None:
            launch_selection[name] = raw
    if "codex_binary" in controls:
        controls["codex_binary"] = "runtime/codex"
    controls.pop("wsl_distribution", None)
    return runner, runtime, controls

def _execution_boundary_control_values(
    execution_boundary: ExecutionBoundary,
) -> dict[str, object]:
    boundary = execution_boundary.to_dict()
    controls: dict[str, object] = {}
    for raw in _sequence(
        boundary.get("controls", ()),
        "execution boundary controls",
    ):
        control = _mapping(raw, "execution boundary control")
        name = _text(control.get("name"), "execution boundary control name")
        if name in controls or "value" not in control:
            raise RepositoryCompositionError(
                "accepted execution boundary controls are ambiguous"
            )
        controls[name] = control.get("value")
    return controls

def _revalidate_runner_execution_readiness(
    source,
    *,
    repository_root: Path,
    execution_boundary: ExecutionBoundary,
    runner_transient_values: Mapping[str, str] | None,
    planning_probe: Callable[[object, Mapping[str, object]], object] | None,
    launch_selection: Mapping[str, str] | None = None,
) -> None:
    registration = _mapping(source.registration, "runner registration")
    extensions = _mapping(registration.get("extensions"), "runner extensions")
    if extensions.get(_PLANNING_PROBE) is None:
        return

    control_values = _execution_boundary_control_values(execution_boundary)
    probe_values = dict(control_values)
    probe_values.update(launch_selection or {})
    for name, value in dict(runner_transient_values or {}).items():
        if name == _TRANSIENT_CREDENTIAL_MATERIAL:
            continue
        if name in control_values and control_values[name] != value:
            raise RepositoryCompositionError(
                f"transient runner control {name!r} conflicts with accepted boundary"
            )

    if planning_probe is None:
        raw_result = _registered_runner_planning_probe(
            source,
            repository_root=repository_root,
            control_values=probe_values,
        )
    else:
        try:
            raw_result = planning_probe(source, dict(probe_values))
        except Exception as exc:
            raise RepositoryCompositionError(
                "runner execution revalidation probe failed before provider submission"
            ) from exc

    result = _mapping(raw_result, "runner execution revalidation probe result")
    if result.get("provider_submitted") is not False:
        raise RepositoryCompositionError(
            "runner execution revalidation probe must be non-submitting"
        )
    if result.get("status") != "ready":
        error_code = result.get("error_code")
        if not isinstance(error_code, str) or not error_code:
            error_code = "runner_execution_revalidation_unavailable"
        raise RepositoryCompositionError(
            "runner execution revalidation blocked accepted execution: "
            f"{error_code}"
        )

    boundary_document = execution_boundary.to_dict()
    accepted_runtime = _mapping(
        boundary_document.get("provider_runtime"),
        "accepted provider runtime",
    )
    observed_runtime = _mapping(
        result.get("provider_runtime"),
        "runner execution revalidation provider runtime",
    )
    expected_full_version = (launch_selection or {}).get("expected_runtime_version", accepted_runtime.get("runtime_version"))
    observed_full_version = result.get("runtime_version", observed_runtime.get("runtime_version"))
    if observed_full_version != expected_full_version:
        raise RepositoryCompositionError("runner execution revalidation changed transient runtime identity")
    # Compare the same minimized representation that acceptance retained. The
    # full label above remains an invocation-only drift check, including when
    # an injected probe supplies it only inside provider_runtime.
    if ProviderRuntimeIdentity.from_value(observed_runtime).to_dict() != dict(accepted_runtime):
        raise RepositoryCompositionError(
            "runner execution revalidation changed accepted runtime identity"
        )

    resolved_controls = _mapping(
        result.get("resolved_controls", {}),
        "runner execution revalidation resolved controls",
    )
    for name, value in resolved_controls.items():
        if name in {"codex_binary", "wsl_distribution"}:
            continue  # Private selectors were re-probed; they are not retained controls.
        if not isinstance(name, str) or not name:
            raise RepositoryCompositionError(
                "runner execution revalidation returned an invalid control"
            )
        if name in control_values and control_values[name] != value:
            raise RepositoryCompositionError(
                f"runner execution revalidation changed accepted control {name!r}"
            )

def _runner_transient_values(
    source,
    controls: Sequence[SidebarControlInputSnapshot],
    *,
    credential: str,
) -> Mapping[str, str] | None:
    if not isinstance(credential, str):
        raise TypeError("credential must be a string")
    if isinstance(controls, (str, bytes)) or not isinstance(controls, Sequence):
        raise TypeError("runner_transient_controls must be a sequence")
    items = tuple(controls)
    if any(type(item) is not SidebarControlInputSnapshot for item in items):
        raise TypeError(
            "runner_transient_controls must contain SidebarControlInputSnapshot values"
        )
    by_name = {item.control_name: item.value for item in items}
    if len(by_name) != len(items):
        raise RepositoryCompositionError("runner transient control intent is ambiguous")

    registration = _mapping(source.registration, "runner registration")
    extensions = _mapping(registration.get("extensions"), "runner extensions")
    raw_secret_handling = extensions.get(_SECRET_HANDLING)
    if raw_secret_handling is None:
        if _CREDENTIAL_SOURCE_CONTROL in by_name:
            raise RepositoryCompositionError(
                "runner transient credential source is not registered"
            )
        return None
    secret_handling = _mapping(raw_secret_handling, "runner secret handling")
    credentials_required = secret_handling.get("credentials_required") is True
    if not credentials_required:
        if _CREDENTIAL_SOURCE_CONTROL in by_name:
            raise RepositoryCompositionError(
                "credential source was supplied to a runner that does not require credentials"
            )
        return None
    if (
        secret_handling.get("transient_secrets_supported") is not True
        or secret_handling.get("retained_secret_values") is not False
    ):
        raise RepositoryCompositionError(
            "credential-required runner does not declare safe transient secret handling"
        )

    supported_sources = tuple(
        _text(value, "runner supported credential source")
        for value in _sequence(
            secret_handling.get("supported_sources"),
            "runner supported credential sources",
        )
    )
    if not supported_sources or len(set(supported_sources)) != len(supported_sources):
        raise RepositoryCompositionError(
            "runner supported credential sources are empty or ambiguous"
        )

    supported_controls = tuple(
        _mapping(raw, "supported control")
        for raw in _sequence(
            extensions.get(_SUPPORTED_CONTROLS, ()),
            "supported controls",
        )
    )
    credential_declarations = [
        declaration
        for declaration in supported_controls
        if declaration.get("name") == _CREDENTIAL_SOURCE_CONTROL
    ]
    if len(credential_declarations) != 1:
        raise RepositoryCompositionError(
            "credential-required runner must declare exactly one credential_source control"
        )
    credential_declaration = credential_declarations[0]
    if (
        credential_declaration.get("kind") != "secret"
        or credential_declaration.get("comparison_relevant") is not False
    ):
        raise RepositoryCompositionError(
            "credential_source must be a non-comparison transient secret control"
        )

    raw_source = by_name.get(_CREDENTIAL_SOURCE_CONTROL)
    if raw_source is None or raw_source == "":
        if len(supported_sources) != 1:
            raise RepositoryCompositionError(
                "registered runner transient credential source is required before execution"
            )
        raw_source = supported_sources[0]
    resolved_source = _coerce(
        raw_source,
        credential_declaration,
        _CREDENTIAL_SOURCE_CONTROL,
    )
    if (
        not isinstance(resolved_source, str)
        or resolved_source not in supported_sources
    ):
        raise RepositoryCompositionError(
            "runner transient credential source is not permitted by registration"
        )

    result = {_TRANSIENT_CREDENTIAL_SOURCE: resolved_source}
    if credential:
        result[_TRANSIENT_CREDENTIAL_MATERIAL] = credential

    raw_transient_inputs = _sequence(
        secret_handling.get(_TRANSIENT_INPUTS, ()),
        "runner transient inputs",
    )
    seen_inputs: set[str] = set()
    for raw_input in raw_transient_inputs:
        transient_input = _mapping(raw_input, "runner transient input")
        name = _text(transient_input.get("name"), "runner transient input name")
        kind = _text(transient_input.get("kind"), "runner transient input kind")
        if (
            name in {
                _CREDENTIAL_SOURCE_CONTROL,
                _TRANSIENT_CREDENTIAL_MATERIAL,
            }
            or name in seen_inputs
        ):
            raise RepositoryCompositionError(
                "runner transient input declaration is ambiguous"
            )
        seen_inputs.add(name)
        credential_sources = tuple(
            _text(value, "runner transient input credential source")
            for value in _sequence(
                transient_input.get("credential_sources"),
                "runner transient input credential sources",
            )
        )
        if (
            not credential_sources
            or len(set(credential_sources)) != len(credential_sources)
            or any(source_name not in supported_sources for source_name in credential_sources)
        ):
            raise RepositoryCompositionError(
                "runner transient input credential sources are invalid"
            )
        declarations = [
            declaration
            for declaration in supported_controls
            if declaration.get("name") == name
        ]
        if len(declarations) != 1:
            raise RepositoryCompositionError(
                "runner transient input must match one supported control"
            )
        declaration = declarations[0]
        if (
            declaration.get("kind") != kind
            or declaration.get("comparison_relevant") is not False
            or declaration.get("required") is True
        ):
            raise RepositoryCompositionError(
                "runner transient input must be an optional non-comparison control"
            )
        raw_value = by_name.get(name)
        if raw_value is None or raw_value == "":
            continue
        if resolved_source not in credential_sources:
            raise RepositoryCompositionError(
                "runner transient input is not permitted for the selected credential source"
            )
        value = _coerce(raw_value, declaration, name)
        if not isinstance(value, str) or not value:
            raise RepositoryCompositionError(
                "runner transient input must resolve to non-empty text"
            )
        result[name] = value
    return result
