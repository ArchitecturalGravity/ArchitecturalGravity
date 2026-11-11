"""Registration-driven GUI readiness projection.

This module converts explicitly supplied, already-validated runner registration
metadata and optional provider-neutral authentication preflights into
authority-neutral desktop controls and diagnostics. It does not validate
registrations, select benchmark authority, construct execution boundaries, or
infer provider-specific behavior.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from importlib import import_module
from inspect import signature
from math import isfinite
from os import W_OK, X_OK, access
from os import name as os_name
from pathlib import Path, PurePosixPath
from shutil import which

from AgMark.shared.application import (
    ApplicationDiscovery,
    ApplicationRegistrationSource,
    DiscoveredRegistration,
)
from AgMark.shared.runtime.artifacts import (
    ArtifactDestinationError,
    PublicationDestination,
)
from AgMark.shared.validation import BenchmarkDiscoveryCandidate

from AgMark.gui.diagnostics import (
    ApplicationEnvironmentProjection,
    EnvironmentDiagnosticEntry,
)
from AgMark.gui.shell.window import (
    NumericInputProjection,
    SidebarChoiceControlProjection,
    SidebarModelChoiceProjection,
    SidebarNumericControlProjection,
    SidebarPrerequisiteDiagnosticProjection,
    SidebarProjection,
    SidebarResolvedTextProjection,
    SidebarTextControlProjection,
)


_SUPPORTED_CONTROLS = "arcgrav.adapters:supported_controls"
_FIXED_CONTROLS = "arcgrav.adapters:fixed_controls"
_ACCESS_METHODS = "arcgrav.adapters:access_methods"
_SECRET_HANDLING = "arcgrav.adapters:secret_handling"
_AUTHENTICATION_PROBE = "arcgrav.adapters:authentication_probe"
_MODEL_DISCOVERY = "arcgrav.adapters:model_discovery"
_RESOLVED_CONFIGURATION = "arcgrav.adapters:resolved_configuration"
_LAUNCH_ENVIRONMENT = "arcgrav.adapters:launch_environment"
_MODEL_CONFIGURATION_CONTROLS = frozenset({"model", "model_id"})
_NUMERIC_CONFIGURATION_CONTROLS = ("temperature", "max_tokens")
_DEFAULT_CONFIGURATION_CONTROLS = frozenset(
    {*_MODEL_CONFIGURATION_CONTROLS, *_NUMERIC_CONFIGURATION_CONTROLS}
)
_MISSING = object()

from .models import RunnerReadinessProjection
from .controls import _MISSING, _control_applicable, _control_projection, _diagnostic, _effective_selected_control_values, _matching_source, _model_control_projection, _model_discovery_context_controls, _numeric_control_projection, _project_model_discovery, _project_resolved_configuration, _selected_control_projection, _selected_wsl_launch, _visible_values
from .probes.authentication import _invoke_optional_control_probe
from .probes.model_discovery import _model_discovery_context_fingerprints

def derive_runner_readiness(
    *,
    discovered_runner: DiscoveredRegistration,
    runner_sources: Sequence[ApplicationRegistrationSource],
    executable_resolver: Callable[[str], str | None] | None = None,
    authentication_probe: Callable[..., bool | None] | None = None,
    model_discovery_probe: Callable[..., Mapping[str, object] | None] | None = None,
    selected_control_values: Mapping[str, object] | None = None,
) -> RunnerReadinessProjection:
    """Project unresolved non-default controls and runner prerequisites."""

    if not isinstance(discovered_runner, DiscoveredRegistration):
        raise TypeError("discovered_runner must be a DiscoveredRegistration")
    if isinstance(runner_sources, (str, bytes)) or not isinstance(
        runner_sources, Sequence
    ):
        raise TypeError("runner_sources must be a sequence")
    resolver = executable_resolver or which
    if not callable(resolver):
        raise TypeError("executable_resolver must be callable or None")
    if authentication_probe is not None and not callable(authentication_probe):
        raise TypeError("authentication_probe must be callable or None")
    if model_discovery_probe is not None and not callable(model_discovery_probe):
        raise TypeError("model_discovery_probe must be callable or None")
    if selected_control_values is not None and not isinstance(
        selected_control_values, Mapping
    ):
        raise TypeError("selected_control_values must be a mapping or None")
    raw_selected_controls = selected_control_values or {}

    source, source_diagnostics = _matching_source(
        discovered_runner,
        runner_sources,
    )
    if source is None:
        return RunnerReadinessProjection(diagnostics=source_diagnostics)

    registration = source.registration
    extensions = registration.get("extensions")
    if not isinstance(extensions, Mapping):
        return RunnerReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "runner-registration-extensions",
                    "The selected runner registration lacks usable extension metadata.",
                    "Correct and revalidate the runner registration before building a plan.",
                ),
            )
        )

    controls_raw = extensions.get(_SUPPORTED_CONTROLS, ())
    fixed_raw = extensions.get(_FIXED_CONTROLS, ())
    if (
        isinstance(controls_raw, (str, bytes))
        or not isinstance(controls_raw, Sequence)
        or isinstance(fixed_raw, (str, bytes))
        or not isinstance(fixed_raw, Sequence)
    ):
        return RunnerReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "runner-control-metadata",
                    "The selected runner registration has unusable control metadata.",
                    "Correct and revalidate supported and fixed runner controls.",
                ),
            )
        )

    fixed_names: set[str] = set()
    fixed_values: dict[str, object] = {}
    for fixed in fixed_raw:
        if not isinstance(fixed, Mapping):
            return RunnerReadinessProjection(
                diagnostics=(
                    _diagnostic(
                        "runner-control-metadata",
                        "The selected runner registration has unusable fixed-control metadata.",
                        "Correct and revalidate the fixed runner controls.",
                    ),
                )
            )
        name = fixed.get("name")
        if not isinstance(name, str) or not name:
            return RunnerReadinessProjection(
                diagnostics=(
                    _diagnostic(
                        "runner-control-metadata",
                        "The selected runner registration has an invalid fixed control name.",
                        "Correct and revalidate the fixed runner controls.",
                    ),
                )
            )
        if name in fixed_values:
            return RunnerReadinessProjection(
                diagnostics=(
                    _diagnostic(
                        "runner-control-metadata",
                        "The selected runner registration has duplicate fixed control names.",
                        "Correct and revalidate the fixed runner controls.",
                    ),
                )
            )
        fixed_names.add(name)
        fixed_values[name] = fixed.get("value")

    selected_controls = _effective_selected_control_values(
        controls_raw=controls_raw,
        fixed_values=fixed_values,
        extensions=extensions,
        selected_control_values=raw_selected_controls,
    )

    controls: list[
        SidebarTextControlProjection | SidebarChoiceControlProjection
    ] = []
    diagnostics: list[SidebarPrerequisiteDiagnosticProjection] = []
    visible_controls = _visible_values(extensions.get("arcgrav.adapters:visible_controls", ())) or ()
    discovery_declaration = extensions.get(_MODEL_DISCOVERY)
    reasoning_control = (discovery_declaration.get("reasoning_effort_control")
                         if isinstance(discovery_declaration, Mapping) else None)
    supported_names: set[str] = set()
    model_controls: list[Mapping[str, object]] = []
    numeric_controls: dict[str, Mapping[str, object]] = {}
    for raw in controls_raw:
        if not isinstance(raw, Mapping):
            diagnostics.append(
                _diagnostic(
                    "runner-control-metadata",
                    "The selected runner registration has unusable supported-control metadata.",
                    "Correct and revalidate the supported runner controls.",
                )
            )
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name or name in supported_names:
            diagnostics.append(
                _diagnostic(
                    "runner-control-metadata",
                    "The selected runner registration has duplicate or invalid supported control names.",
                    "Correct and revalidate the supported runner controls.",
                )
            )
            continue
        supported_names.add(name)
        if name == reasoning_control:
            continue
        if not _control_applicable(name, extensions, selected_controls):
            continue
        if name in _MODEL_CONFIGURATION_CONTROLS:
            model_controls.append(raw)
            continue
        if name in _NUMERIC_CONFIGURATION_CONTROLS:
            numeric_controls[name] = raw
            continue
        explicitly_visible = name in visible_controls
        if (raw.get("required") is not True and not explicitly_visible) or name in fixed_names:
            continue
        if "default" in raw and raw.get("default") is not None and not explicitly_visible:
            continue
        if "values" in raw:
            values = _visible_values(raw.get("values"))
            if values is not None and len(values) == 1:
                continue
        if name in _DEFAULT_CONFIGURATION_CONTROLS:
            continue
        projection, diagnostic = _control_projection(raw)
        if projection is not None:
            if explicitly_visible:
                projection = replace(projection, required=raw.get("required") is True)
            controls.append(
                _selected_control_projection(projection, selected_controls)
            )
        if diagnostic is not None:
            diagnostics.append(diagnostic)

    model_control_present = False
    model_options: tuple[str, ...] = ()
    selected_model: str | None = None
    model_choices: tuple[SidebarModelChoiceProjection, ...] = ()
    selected_model_selection_mode: str | None = None
    model_editable = False
    model_required = False
    model_discovery_authoritative = _MODEL_DISCOVERY in extensions
    model_discovery_determining_controls: tuple[str, ...] = ()
    model_discovery_context_fingerprints: tuple[str, ...] = ()
    runtime_readiness_operation = (
        "planning" if model_discovery_authoritative else "execution"
    )
    discovery_result: object = None
    connectivity = ("Runner not checked", "neutral",
                    "This runner has no declared connection probe.")
    discovery_probe_invoked = False

    fixed_model_names = tuple(
        name for name in _MODEL_CONFIGURATION_CONTROLS if name in fixed_values
    )
    if len(model_controls) > 1 or (
        model_controls and fixed_model_names
        and model_controls[0].get("name") not in fixed_model_names
    ) or len(fixed_model_names) > 1:
        diagnostics.append(
            _diagnostic(
                "runner-control:model",
                "The selected runner registration has ambiguous Model controls.",
                "Declare exactly one provider-neutral model or model_id control.",
            )
        )
    elif model_controls:
        model_control = model_controls[0]
        model_name = model_control.get("name")
        model_control_present = True
        (
            model_options,
            selected_model,
            model_editable,
            model_required,
            model_diagnostic,
        ) = _model_control_projection(
            model_control,
            fixed_value=fixed_values.get(model_name, _MISSING),
            discovery_backed=model_discovery_authoritative,
        )
        if model_diagnostic is not None:
            diagnostics.append(model_diagnostic)
    elif len(fixed_model_names) == 1:
        model_name = fixed_model_names[0]
        fixed_model = fixed_values[model_name]
        if isinstance(fixed_model, str) and fixed_model.strip():
            model_control_present = True
            model_options = (fixed_model,)
            selected_model = fixed_model
        else:
            diagnostics.append(
                _diagnostic(
                    "runner-control:model",
                    "The selected runner has an unusable fixed Model value.",
                    "Correct and revalidate the fixed runner Model control.",
                )
            )

    temperature: NumericInputProjection | None = None
    max_tokens: NumericInputProjection | None = None
    numeric_projections: dict[str, NumericInputProjection | None] = {
        "temperature": None,
        "max_tokens": None,
    }
    for numeric_name in _NUMERIC_CONFIGURATION_CONTROLS:
        numeric_control = numeric_controls.get(numeric_name)
        if numeric_control is not None:
            projection, diagnostic = _numeric_control_projection(
                numeric_name,
                numeric_control,
                fixed_value=fixed_values.get(numeric_name, _MISSING),
            )
        elif numeric_name in fixed_values:
            projection, diagnostic = _numeric_control_projection(
                numeric_name,
                {
                    "name": numeric_name,
                    "kind": "integer" if numeric_name == "max_tokens" else "number",
                    "required": False,
                },
                fixed_value=fixed_values[numeric_name],
            )
        else:
            projection, diagnostic = None, None
        numeric_projections[numeric_name] = projection
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    temperature = numeric_projections["temperature"]
    max_tokens = numeric_projections["max_tokens"]

    if _ACCESS_METHODS in extensions:
        access_methods = extensions.get(_ACCESS_METHODS)
        if isinstance(access_methods, (str, bytes)) or not isinstance(
            access_methods, Sequence
        ):
            diagnostics.append(
                _diagnostic(
                    "runner-access-methods",
                    "The selected runner registration has unusable access-method metadata.",
                    "Correct and revalidate the runner access-method metadata.",
                )
            )
        else:
            cli_names: list[str] = []
            for method in access_methods:
                if not isinstance(method, Mapping):
                    diagnostics.append(
                        _diagnostic(
                            "runner-access-methods",
                            "The selected runner registration has an invalid access method.",
                            "Correct and revalidate the runner access-method metadata.",
                        )
                    )
                    continue
                if method.get("type") != "cli":
                    continue
                client_name = method.get("client_name")
                if isinstance(client_name, str) and client_name:
                    cli_names.append(client_name)
                else:
                    diagnostics.append(
                        _diagnostic(
                            "runner-executable",
                            "A registered CLI runner does not identify its executable.",
                            "Correct and revalidate the CLI access-method metadata.",
                        )
                    )
            if cli_names and not _selected_wsl_launch(
                extensions,
                selected_controls,
            ):
                launch = extensions.get(_LAUNCH_ENVIRONMENT)
                if (
                    isinstance(launch, Mapping)
                    and selected_controls.get("launch_mode") == "native"
                ):
                    executable_control = launch.get("executable_control")
                    selected_binary = selected_controls.get(executable_control) if isinstance(executable_control, str) else None
                    executable_names = (
                        [selected_binary]
                        if isinstance(selected_binary, str) and selected_binary
                        else ([] if isinstance(executable_control, str) else cli_names)
                    )
                else:
                    executable_names = cli_names
                resolved = False
                for client_name in executable_names:
                    try:
                        if resolver(client_name):
                            resolved = True
                            break
                    except OSError:
                        continue
                if not resolved:
                    diagnostics.append(
                        _diagnostic(
                            "runner-executable",
                            "No registered CLI runner executable is currently available.",
                            "Install or configure one of the registered CLI executables: "
                            + ", ".join(executable_names or cli_names),
                            operation=runtime_readiness_operation,
                        )
                    )

    authentication_required_for_discovery = False
    authentication_ready: bool | None = None
    credentials_required = False
    if _SECRET_HANDLING in extensions:
        secret_handling = extensions.get(_SECRET_HANDLING)
        if not isinstance(secret_handling, Mapping):
            diagnostics.append(
                _diagnostic(
                    "runner-credential-source",
                    "The selected runner registration has unusable secret-handling metadata.",
                    "Correct and revalidate the runner secret-handling metadata.",
                )
            )
        elif secret_handling.get("credentials_required") is True:
            credentials_required = True
            authentication_required_for_discovery = True
            supported_sources = _visible_values(
                secret_handling.get("supported_sources", ())
            )
            credential_source_usable = True
            if not supported_sources:
                credential_source_usable = False
                diagnostics.append(
                    _diagnostic(
                        "runner-credential-source",
                        "The selected runner requires credentials but declares no usable credential source.",
                        "Correct and revalidate the runner secret-handling metadata.",
                        operation=runtime_readiness_operation,
                    )
                )
            elif (
                len(supported_sources) > 1
                and "credential_source" not in supported_names
            ):
                credential_source_usable = False
                diagnostics.append(
                    _diagnostic(
                        "runner-credential-source",
                        "The selected runner exposes multiple credential sources without a resolvable credential-source control.",
                        "Declare a provider-neutral credential_source control or a single authoritative source.",
                        operation=runtime_readiness_operation,
                    )
                )

            if credential_source_usable:
                authenticated: bool | None = None
                if authentication_probe is not None:
                    try:
                        probe_result = _invoke_optional_control_probe(
                            authentication_probe,
                            source,
                            selected_controls,
                        )
                    except Exception:
                        probe_result = None
                    if type(probe_result) is bool:
                        authenticated = probe_result
                authentication_ready = authenticated

                if authenticated is not True:
                    if authenticated is False:
                        message = (
                            "Authentication for the selected runner is currently unavailable."
                        )
                        remediation = (
                            "Restore authentication through one of the registered credential "
                            "sources, then re-run the runner authentication preflight."
                        )
                    else:
                        message = (
                            "Authentication readiness for the selected runner has not been "
                            "established by a provider-neutral production preflight."
                        )
                        remediation = (
                            "Supply a provider-neutral authentication probe for the exact "
                            "validated runner registration before building or executing a plan."
                        )
                    diagnostics.append(
                        _diagnostic(
                            "runner-authentication",
                            message,
                            remediation,
                            operation=runtime_readiness_operation,
                        )
                    )

    if model_discovery_authoritative:
        model_control_present = True
        model_options = ()
        selected_model = None
        model_choices = ()
        selected_model_selection_mode = None
        model_editable = False
        model_required = True

        (
            model_discovery_determining_controls,
            determining_controls_diagnostic,
        ) = _model_discovery_context_controls(
            extensions.get(_MODEL_DISCOVERY),
            supported_names,
        )
        if determining_controls_diagnostic is not None:
            diagnostics.append(determining_controls_diagnostic)
        elif (
            not authentication_required_for_discovery
            or authentication_ready is True
        ):
            if model_discovery_probe is not None:
                try:
                    discovery_probe_invoked = True
                    discovery_result = _invoke_optional_control_probe(
                        model_discovery_probe,
                        source,
                        selected_controls,
                    )
                except Exception:
                    discovery_result = None

        (
            discovered_choices,
            discovered_model,
            discovered_selection_mode,
            discovery_diagnostic,
        ) = _project_model_discovery(
            extensions.get(_MODEL_DISCOVERY),
            discovery_result,
            controls_raw,
        )
        if determining_controls_diagnostic is None:
            if discovery_diagnostic is not None:
                diagnostics.append(discovery_diagnostic)
            else:
                model_choices = discovered_choices
                selected_model = discovered_model
                selected_model_selection_mode = discovered_selection_mode
                model_discovery_context_fingerprints = (
                    _model_discovery_context_fingerprints(
                        extensions.get(_MODEL_DISCOVERY),
                        discovery_result,
                    )
                )
                model_required = False

    # This is the selected runner's declared, no-inference protocol response,
    # not an internet test or proof that a provider will accept a benchmark.
    if model_discovery_authoritative:
        if authentication_required_for_discovery and authentication_ready is not True:
            connectivity = (
                "Runner authentication unavailable" if authentication_ready is False
                else "Runner authentication not checked", "warning",
                "The selected runner's authentication prerequisite is not satisfied; "
                "its connection has not been established.",
            )
        elif determining_controls_diagnostic is not None:
            connectivity = ("Runner configuration incomplete", "warning",
                            determining_controls_diagnostic.message)
        elif discovery_probe_invoked:
            if discovery_diagnostic is None:
                connectivity = (
                    "Connected", "success",
                    "The selected runner responded to its registered discovery handshake. "
                    "Last checked response only; provider availability and benchmark execution "
                    "are not verified by this check.",
                )
            else:
                if discovery_result is None:
                    label = "Runner check inconclusive"
                elif isinstance(discovery_result, Mapping) and discovery_result.get("status") == "ready":
                    label = "Runner response invalid"
                else:
                    label = "Runner connection unavailable"
                connectivity = (
                    label, "warning",
                    discovery_diagnostic.details or discovery_diagnostic.message,
                )
        else:
            connectivity = ("Runner not checked", "neutral",
                            "No usable connection probe was supplied for the selected runner.")

    resolved_configuration = _project_resolved_configuration(
        extensions.get(_RESOLVED_CONFIGURATION),
        discovery_result,
        selected_controls,
    )

    if reasoning_control is not None:
        if (not isinstance(reasoning_control, str)
                or reasoning_control not in supported_names
                or not model_choices
                or any(not choice.reasoning_efforts for choice in model_choices)):
            diagnostics.append(_diagnostic(
                "runner-control:reasoning_effort",
                "Reasoning levels unavailable for the selected runner.",
                "Refresh model discovery with a runner version that advertises reasoning levels.",
            ))

    unique_diagnostics: list[SidebarPrerequisiteDiagnosticProjection] = []
    seen_diagnostics: set[str] = set()
    for diagnostic in diagnostics:
        if diagnostic.diagnostic_name in seen_diagnostics:
            continue
        seen_diagnostics.add(diagnostic.diagnostic_name)
        unique_diagnostics.append(diagnostic)

    return RunnerReadinessProjection(
        runner_connectivity=connectivity,
        runner_test_supported=(isinstance(extensions.get("arcgrav.adapters:runner_test"), Mapping)
                               and extensions["arcgrav.adapters:runner_test"].get("supported") is True),
        model_control_present=model_control_present,
        scenario_visible=isinstance(extensions.get(_MODEL_DISCOVERY), Mapping) and "scenario_projection" in extensions[_MODEL_DISCOVERY],
        reasoning_effort_control_name=reasoning_control,
        model_options=model_options,
        selected_model=selected_model,
        model_choices=model_choices,
        selected_model_selection_mode=selected_model_selection_mode,
        model_editable=model_editable,
        model_required=model_required,
        model_discovery_authoritative=model_discovery_authoritative,
        model_discovery_determining_controls=(
            model_discovery_determining_controls
        ),
        model_discovery_context_fingerprints=(
            model_discovery_context_fingerprints
        ),
        authentication_satisfied=authentication_ready is True,
        credentials_required=credentials_required,
        numeric_controls_projected=True,
        temperature=temperature,
        max_tokens=max_tokens,
        additional_controls=tuple(controls),
        resolved_configuration=resolved_configuration,
        diagnostics=tuple(unique_diagnostics),
    )
