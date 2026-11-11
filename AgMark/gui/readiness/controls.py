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

def _diagnostic(
    name: str,
    message: str,
    remediation: str,
    *,
    operation: str = "planning",
    details: str | None = None,
) -> SidebarPrerequisiteDiagnosticProjection:
    return SidebarPrerequisiteDiagnosticProjection(
        diagnostic_name=name,
        message=message,
        remediation=remediation,
        operation=operation,
        details=details,
    )

def _human_label(control_name: str) -> str:
    # Preserve the registered control key in requests and retained boundaries.
    if control_name == "capture_mode":
        return "Capture Mode"
    return " ".join(part.capitalize() for part in control_name.split("_"))

def _visible_values(value: object) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    visible: list[str] = []
    for item in value:
        nested = isinstance(item, (Mapping, Sequence)) and not isinstance(
            item, (str, bytes)
        )
        if item is None or nested:
            return None
        rendered = str(item)
        if not rendered:
            return None
        visible.append(rendered)
    if len(set(visible)) != len(visible):
        return None
    return tuple(visible)

def _model_discovery_context_controls(
    declaration: object,
    supported_names: set[str],
) -> tuple[
    tuple[str, ...],
    SidebarPrerequisiteDiagnosticProjection | None,
]:
    """Validate registered inputs that determine model discovery authority."""

    if not isinstance(declaration, Mapping):
        return (), _diagnostic(
            "runner-model-discovery",
            "The selected runner has unusable model-discovery metadata.",
            "Correct and revalidate the runner model-discovery declaration.",
        )
    controls = _visible_values(declaration.get("determining_controls"))
    if controls is None:
        return (), _diagnostic(
            "runner-model-discovery",
            "The selected runner does not declare its model-discovery determining context.",
            "Declare every registered input that can change the model catalog, effective default, or concrete identity.",
        )
    if any(name not in supported_names for name in controls):
        return (), _diagnostic(
            "runner-model-discovery",
            "The selected runner declares unknown model-discovery determining controls.",
            "Correct and revalidate the runner model-discovery determining-control declaration.",
        )
    return controls, None

def _matching_source(
    discovered_runner: DiscoveredRegistration,
    runner_sources: Sequence[ApplicationRegistrationSource],
) -> tuple[
    ApplicationRegistrationSource | None,
    tuple[SidebarPrerequisiteDiagnosticProjection, ...],
]:
    matches: list[ApplicationRegistrationSource] = []
    for source in runner_sources:
        if not isinstance(source, ApplicationRegistrationSource):
            return None, (
                _diagnostic(
                    "runner-registration-source",
                    "Runner readiness metadata is not a validated registration source.",
                    "Reload repository runner registrations through production validation.",
                ),
            )
        registration = source.registration
        if (
            registration.get("registration_id") == discovered_runner.registration_id
            and registration.get("registration_version")
            == discovered_runner.registration_version
        ):
            matches.append(source)

    if len(matches) != 1:
        return None, (
            _diagnostic(
                "runner-registration-source",
                "The selected runner does not resolve to exactly one validated registration source.",
                "Reload repository discovery and resolve the selected runner from one exact validated registration.",
            ),
        )

    source = matches[0]
    validation = source.registration_validation
    if (
        not validation.valid
        or not validation.matches(
            source.registration,
            source_id=source.registration_source_id,
        )
        or validation.registration_sha256 != discovered_runner.registration_sha256
    ):
        return None, (
            _diagnostic(
                "runner-registration-validation",
                "The selected runner registration is not validated for the exact discovered bytes.",
                "Re-run repository registration validation before building a plan.",
            ),
        )

    registration = source.registration
    if (
        registration.get("registration_kind") != "runner"
        or registration.get("status") != "active"
    ):
        return None, (
            _diagnostic(
                "runner-registration-status",
                "The selected registration is not an active runner registration.",
                "Select an active validated runner registration.",
            ),
        )
    return source, ()

def _model_control_projection(
    control: Mapping[str, object],
    *,
    fixed_value: object = _MISSING,
    discovery_backed: bool = False,
) -> tuple[
    tuple[str, ...],
    str | None,
    bool,
    bool,
    SidebarPrerequisiteDiagnosticProjection | None,
]:
    name = control.get("name")
    kind = control.get("kind")
    if (
        not isinstance(name, str)
        or name not in _MODEL_CONFIGURATION_CONTROLS
        or kind not in {"text", "choice"}
    ):
        return (), None, False, False, _diagnostic(
            "runner-control:model",
            "The selected runner has unsupported Model control metadata.",
            "Correct and revalidate the runner Model control metadata.",
        )

    values: tuple[str, ...] | None = None
    if "values" in control:
        raw_values = control.get("values")
        values = _visible_values(raw_values)
        if (
            values is None
            or any(
                not isinstance(item, str) or not item.strip()
                for item in raw_values
            )
        ):
            return (), None, False, False, _diagnostic(
                "runner-control:model",
                "The selected runner has unsupported permitted Model values.",
                "Correct and revalidate the runner Model control values.",
            )

    resolved: str | None = None
    if fixed_value is not _MISSING:
        if not isinstance(fixed_value, str) or not fixed_value.strip():
            return (), None, False, False, _diagnostic(
                "runner-control:model",
                "The selected runner has an unusable fixed Model value.",
                "Correct and revalidate the fixed runner Model control.",
            )
        resolved = fixed_value
    elif "default" in control and control.get("default") is not None:
        default = control.get("default")
        if not isinstance(default, str) or not default.strip():
            return (), None, False, False, _diagnostic(
                "runner-control:model",
                "The selected runner has an unusable default Model value.",
                "Correct and revalidate the runner Model control default.",
            )
        resolved = default
    elif values is not None and len(values) == 1:
        resolved = values[0]

    if values is not None and resolved is not None and resolved not in values:
        return (), None, False, False, _diagnostic(
            "runner-control:model",
            "The selected runner Model default or fixed value is not permitted.",
            "Correct and revalidate the runner Model control metadata.",
        )

    if kind == "choice" and values is None and not discovery_backed:
        return (), None, False, False, _diagnostic(
            "runner-control:model",
            "The selected runner Model choice control has no usable values.",
            "Correct and revalidate the runner Model choice metadata.",
        )

    unresolved_required = control.get("required") is True and resolved is None
    if values is not None:
        return values, resolved, False, unresolved_required, None
    if kind == "choice":
        return (), resolved, False, unresolved_required, None
    return (), resolved, True, unresolved_required, None

def _numeric_control_projection(
    name: str,
    control: Mapping[str, object],
    *,
    fixed_value: object = _MISSING,
) -> tuple[
    NumericInputProjection | None,
    SidebarPrerequisiteDiagnosticProjection | None,
]:
    kind = control.get("kind")
    if kind not in {"integer", "number", "float"}:
        return None, _diagnostic(
            f"runner-control:{name}",
            f"The selected runner has unsupported {name} numeric metadata.",
            f"Correct and revalidate the runner {name} control metadata.",
        )

    def numeric(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        normalized = float(value)
        return normalized if isfinite(normalized) else None

    raw_values = control.get("values", _MISSING)
    permitted_values: tuple[float, ...] = ()
    sole_value: float | None = None
    if raw_values is not _MISSING:
        if isinstance(raw_values, (str, bytes)) or not isinstance(raw_values, Sequence):
            return None, _diagnostic(
                f"runner-control:{name}",
                f"The selected runner has unusable permitted {name} values.",
                f"Correct and revalidate the runner {name} control metadata.",
            )
        parsed_values = tuple(numeric(value) for value in raw_values)
        if any(value is None for value in parsed_values) or not parsed_values:
            return None, _diagnostic(
                f"runner-control:{name}",
                f"The selected runner has unusable permitted {name} values.",
                f"Correct and revalidate the runner {name} control metadata.",
            )
        permitted_values = tuple(value for value in parsed_values if value is not None)
        if len(permitted_values) > 1 and fixed_value is _MISSING:
            return None, _diagnostic(
                f"runner-control:{name}",
                f"The selected runner exposes discrete {name} values that cannot be represented by the default numeric row.",
                f"Use numeric range metadata, one permitted value, or a fixed authoritative {name} value.",
            )
        if len(permitted_values) == 1:
            sole_value = permitted_values[0]

    resolved: float | None = None
    fixed = fixed_value is not _MISSING
    if fixed:
        resolved = numeric(fixed_value)
    elif control.get("default") is not None:
        resolved = numeric(control.get("default"))
    elif sole_value is not None:
        resolved = sole_value
    if (fixed or control.get("default") is not None) and resolved is None:
        return None, _diagnostic(
            f"runner-control:{name}",
            f"The selected runner has an unusable resolved {name} value.",
            f"Correct and revalidate the runner {name} control metadata.",
        )
    if (
        permitted_values
        and resolved is not None
        and resolved not in permitted_values
    ):
        return None, _diagnostic(
            f"runner-control:{name}",
            f"The selected runner resolved {name} to a value that is not permitted.",
            f"Correct and revalidate the runner {name} control metadata.",
        )

    minimum = numeric(control.get("minimum"))
    maximum = numeric(control.get("maximum"))
    editable = not fixed and sole_value is None
    if minimum is None or maximum is None:
        if not editable and resolved is not None:
            minimum = resolved
            maximum = resolved
        else:
            return None, _diagnostic(
                f"runner-control:{name}",
                f"The selected runner lacks a complete numeric range for {name}.",
                f"Declare finite minimum and maximum metadata for the editable {name} control.",
            )
    if minimum > maximum:
        return None, _diagnostic(
            f"runner-control:{name}",
            f"The selected runner has an invalid numeric range for {name}.",
            f"Correct and revalidate the runner {name} range metadata.",
        )

    step = numeric(control.get("step", 1))
    if step is None or step <= 0:
        return None, _diagnostic(
            f"runner-control:{name}",
            f"The selected runner has an invalid numeric step for {name}.",
            f"Correct and revalidate the runner {name} step metadata.",
        )
    decimals_raw = control.get("decimals", 0 if kind == "integer" else 6)
    if (
        not isinstance(decimals_raw, int)
        or isinstance(decimals_raw, bool)
        or decimals_raw < 0
    ):
        return None, _diagnostic(
            f"runner-control:{name}",
            f"The selected runner has invalid numeric precision for {name}.",
            f"Correct and revalidate the runner {name} precision metadata.",
        )

    if kind == "integer":
        integral = (minimum, maximum, step) + (() if resolved is None else (resolved,))
        if any(not value.is_integer() for value in integral):
            return None, _diagnostic(
                f"runner-control:{name}",
                f"The selected runner declares non-integer metadata for integer control {name}.",
                f"Correct and revalidate the runner {name} control metadata.",
            )
    if resolved is not None and not minimum <= resolved <= maximum:
        return None, _diagnostic(
            f"runner-control:{name}",
            f"The selected runner resolved {name} outside its registered numeric range.",
            f"Correct and revalidate the runner {name} control metadata.",
        )

    return (
        NumericInputProjection(
            value=resolved,
            minimum=minimum,
            maximum=maximum,
            step=step,
            decimals=decimals_raw,
            required=control.get("required") is True,
            editable=editable,
        ),
        None,
    )

def _control_projection(
    control: Mapping[str, object],
) -> tuple[
    SidebarTextControlProjection | SidebarChoiceControlProjection | None,
    SidebarPrerequisiteDiagnosticProjection | None,
]:
    name = control.get("name")
    kind = control.get("kind")
    if not isinstance(name, str) or not name or not isinstance(kind, str) or not kind:
        return None, _diagnostic(
            "runner-control-metadata",
            "A required runner control has unsupported registration metadata.",
            "Correct and revalidate the runner registration before building a plan.",
        )

    values = None
    if "values" in control:
        values = _visible_values(control.get("values"))
        if values is None:
            return None, _diagnostic(
                f"runner-control:{name}",
                f"Required runner control '{name}' has unsupported permitted values.",
                "Correct and revalidate the runner registration control metadata.",
            )

    label = _human_label(name)
    if values is not None and len(values) > 1:
        return (
            SidebarChoiceControlProjection(
                control_name=name,
                label=label,
                options=values,
                selected_value=None,
                required=True,
            ),
            None,
        )

    if kind in {"text", "secret", "integer", "number", "float"}:
        return (
            SidebarTextControlProjection(
                control_name=name,
                label=label,
                value="",
                secret=kind == "secret",
                required=True,
            ),
            None,
        )

    return None, _diagnostic(
        f"runner-control:{name}",
        f"Required runner control '{name}' uses unsupported kind '{kind}'.",
        "Use a supported provider-neutral control kind or provide an authoritative default, fixed value, or sole permitted value.",
    )

def _selected_control_projection(
    control: SidebarTextControlProjection | SidebarChoiceControlProjection,
    control_values: Mapping[str, object],
) -> SidebarTextControlProjection | SidebarChoiceControlProjection:
    if control.control_name not in control_values:
        return control
    value = control_values[control.control_name]
    if type(value) in (int, float):
        import math
        if math.isfinite(value):
            value = str(value)
    if isinstance(control, SidebarTextControlProjection):
        if isinstance(value, str):
            return replace(control, value=value)
        return control
    if isinstance(value, str) and value in control.options:
        return replace(control, selected_value=value)
    return control

def _default_launch_mode(launch: Mapping[str, object]) -> str | None:
    supported = _visible_values(launch.get("supported_modes", ()))
    policy = launch.get("default_mode_policy")
    if not supported or not isinstance(policy, Mapping):
        return None
    from . import os_name as current_os_name

    declared = policy.get("windows") if current_os_name == "nt" else policy.get("non_windows")
    if declared == "native_if_supported_else_unsupported":
        return "native" if "native" in supported else None
    if isinstance(declared, str) and declared in supported:
        return declared
    return None

def _string_default(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None

def _control_applicable(
    name: str,
    extensions: Mapping[str, object],
    selected_controls: Mapping[str, object],
) -> bool:
    """Return whether a registered control applies to the selected launch mode."""

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
        return selected_controls.get("launch_mode") == "wsl"
    return True

def _effective_selected_control_values(
    *,
    controls_raw: Sequence[object],
    fixed_values: Mapping[str, object],
    extensions: Mapping[str, object],
    selected_control_values: Mapping[str, object],
) -> dict[str, object]:
    selected = {
        name: value
        for name, value in selected_control_values.items()
        if isinstance(name, str) and name and value is not None
    }
    declarations = {
        raw.get("name"): raw
        for raw in controls_raw
        if isinstance(raw, Mapping)
        and isinstance(raw.get("name"), str)
        and raw.get("name")
    }

    for name, value in fixed_values.items():
        selected.setdefault(name, value)

    launch = extensions.get(_LAUNCH_ENVIRONMENT)
    if isinstance(launch, Mapping):
        mode = selected.get("launch_mode")
        if not isinstance(mode, str) or not mode.strip():
            default_mode = _default_launch_mode(launch)
            if default_mode is not None and "launch_mode" in declarations:
                selected["launch_mode"] = default_mode
                mode = default_mode
        if isinstance(mode, str) and mode.strip():
            mode_config = launch.get(mode)
            if isinstance(mode_config, Mapping):
                executable_control = launch.get("executable_control")
                for control_name, default_name in (
                    (executable_control, "executable_default"),
                    ("wsl_launcher", "launcher_default"),
                    ("wsl_distribution", "distribution_default"),
                ):
                    if not isinstance(control_name, str) or control_name not in declarations:
                        continue
                    value = _string_default(mode_config.get(default_name))
                    if value is not None:
                        selected.setdefault(control_name, value)

    for name, declaration in declarations.items():
        if name in selected:
            continue
        default = declaration.get("default", _MISSING)
        if default is not _MISSING and default is not None:
            selected[name] = default
            continue
        if "values" in declaration:
            values = _visible_values(declaration.get("values"))
            if values is not None and len(values) == 1:
                selected[name] = values[0]
    return selected

def _selected_wsl_launch(
    extensions: Mapping[str, object],
    selected: Mapping[str, object],
) -> bool:
    launch = extensions.get(_LAUNCH_ENVIRONMENT)
    if not isinstance(launch, Mapping):
        return False
    from . import os_name as current_os_name

    return current_os_name == "nt" and selected.get("launch_mode") == "wsl"

def _project_model_discovery(
    declaration: object,
    result: object,
    controls_raw: Sequence[object],
) -> tuple[
    tuple[SidebarModelChoiceProjection, ...],
    str | None,
    str | None,
    SidebarPrerequisiteDiagnosticProjection | None,
]:
    """Validate one registered discovery result into authority-neutral choices."""

    def unavailable(
        message: str,
        remediation: str,
        *,
        details: str | None = None,
    ) -> tuple[
        tuple[SidebarModelChoiceProjection, ...],
        str | None,
        str | None,
        SidebarPrerequisiteDiagnosticProjection,
    ]:
        return (), None, None, _diagnostic(
            "runner-model-discovery",
            message,
            remediation,
            details=details,
        )

    if not isinstance(declaration, Mapping):
        return unavailable(
            "The selected runner has unusable model-discovery metadata.",
            "Correct and revalidate the runner model-discovery declaration.",
        )
    choice_projection = declaration.get("choice_projection")
    if not isinstance(choice_projection, Mapping):
        return unavailable(
            "The selected runner has unusable model-choice projection metadata.",
            "Correct and revalidate the runner model-discovery choice projection.",
        )
    selection_modes = _visible_values(choice_projection.get("selection_modes", ()))
    if (
        choice_projection.get("default_first") is not True
        or choice_projection.get("normal_path_free_text") is not False
        or not selection_modes
    ):
        return unavailable(
            "The selected runner does not declare a fail-closed discovery-backed model picker.",
            "Declare default-first model choices, explicit selection modes, and no normal free-text fallback.",
        )

    mode_controls: list[Mapping[str, object]] = []
    for raw in controls_raw:
        if not isinstance(raw, Mapping) or raw.get("kind") != "choice":
            continue
        values = _visible_values(raw.get("values", ()))
        if values == selection_modes:
            mode_controls.append(raw)
    # A catalog with one fixed explicit mode needs no extra adapter control.
    # Configurable modes must still bind exactly one declared choice control.
    if not mode_controls and selection_modes == ("explicit",):
        selection_mode_control_name = None
    elif len(mode_controls) == 1:
        selection_mode_control_name = mode_controls[0].get("name")
        if not isinstance(selection_mode_control_name, str) or not selection_mode_control_name:
            return unavailable(
                "The selected runner model selection-mode control has no usable name.",
                "Correct and revalidate the model selection-mode control metadata.",
            )
    else:
        return unavailable(
            "The selected runner does not resolve model selection-mode authority unambiguously.",
            "Declare a unique choice control for configurable model selection modes.",
        )

    if (
        not isinstance(result, Mapping)
        or result.get("status") != "ready"
        or result.get("provider_submitted") is not False
    ):
        details = None
        if isinstance(result, Mapping):
            error_code = result.get("error_code")
            error_message = result.get("error_message")
            if isinstance(error_code, str) and error_code.strip():
                details = error_code.strip()
                if isinstance(error_message, str) and error_message.strip():
                    details += f" — {error_message.strip()}"
        return unavailable(
            "Authoritative model discovery for the selected runner is unresolved.",
            "Restore the declared discovery prerequisites and refresh runner readiness before building a plan.",
            details=details,
        )

    raw_choices = result.get("choices")
    if isinstance(raw_choices, (str, bytes)) or not isinstance(
        raw_choices, Sequence
    ) or not raw_choices:
        return unavailable(
            "Authoritative model discovery returned no usable model choices.",
            "Refresh the registered model-discovery surface and require a complete choice projection.",
        )

    choices: list[SidebarModelChoiceProjection] = []
    try:
        for raw_choice in raw_choices:
            if not isinstance(raw_choice, Mapping):
                raise ValueError("model choice must be an object")
            model_value = raw_choice.get("model_id")
            if model_value is None:
                model_value = raw_choice.get("model")
            label = raw_choice.get("label")
            selection_mode = raw_choice.get("selection_mode")
            if (
                not isinstance(model_value, str)
                or not model_value.strip()
                or not isinstance(label, str)
                or not label.strip()
                or not isinstance(selection_mode, str)
                or selection_mode not in selection_modes
            ):
                raise ValueError("model choice is incomplete")
            scenario_fields = {}
            scenario_declaration = declaration.get("scenario_projection")
            if scenario_declaration is not None:
                if not isinstance(scenario_declaration, Mapping) or scenario_declaration.get("source") != "scenario" or scenario_declaration.get("required") is not True:
                    raise ValueError("invalid scenario projection declaration")
                scenario = raw_choice.get("scenario")
                if not isinstance(scenario, Mapping) or scenario.get("model_id") != model_value:
                    raise ValueError("scenario mapping must bind the exact discovered model")
                scenario_fields = {
                    "scenario_id": scenario.get("scenario_id"),
                    "scenario_label": scenario.get("label"),
                    "base_model_id": scenario.get("base_model_id"),
                    "scenario_default": scenario.get("is_default"),
                }
                if any(not isinstance(scenario_fields[key], str) or not scenario_fields[key].strip() for key in ("scenario_id", "scenario_label", "base_model_id")):
                    raise ValueError("scenario identity is incomplete")
            reasoning_fields = {}
            if declaration.get("reasoning_effort_control") is not None:
                efforts = raw_choice.get("reasoning_efforts")
                if not isinstance(efforts, (list, tuple)) or not efforts:
                    raise ValueError("reasoning levels unavailable")
                reasoning_fields = {
                    "reasoning_efforts": tuple(
                        (effort["value"], effort["description"]) for effort in efforts
                        if isinstance(effort, Mapping)
                    ),
                    "default_reasoning_effort": raw_choice.get("default_reasoning_effort"),
                }
                if len(reasoning_fields["reasoning_efforts"]) != len(efforts):
                    raise ValueError("invalid reasoning option")
            choices.append(
                SidebarModelChoiceProjection(
                    label=label,
                    model_value=model_value,
                    selection_mode=selection_mode if selection_mode_control_name is not None else None,
                    selection_mode_control_name=selection_mode_control_name,
                    **scenario_fields,
                    **reasoning_fields,
                )
            )
    except (ValueError, KeyError, TypeError):
        return unavailable(
            "Authoritative model discovery returned unusable model-choice identity.",
            "Refresh the registered model-discovery surface and require exact canonical model and selection-mode identity.",
        )

    labels = tuple(choice.label for choice in choices)
    identities = tuple(choice.authority_identity for choice in choices)
    if len(set(labels)) != len(labels) or len(set(identities)) != len(identities):
        return unavailable(
            "Authoritative model discovery returned ambiguous model choices.",
            "Require deterministic unique labels and canonical model-selection identities from the owning runner.",
        )

    if declaration.get("scenario_projection") is not None:
        scenario_identities = [(choice.base_model_id, choice.scenario_id) for choice in choices]
        scenario_labels = [choice.scenario_label for choice in choices]
        defaults = [choice for choice in choices if choice.scenario_default]
        if len(set(scenario_identities)) != len(choices) or len(set(scenario_labels)) != len(choices) or len(defaults) != 1 or defaults[0] != choices[0]:
            return unavailable("Authoritative scenario mapping is ambiguous or lacks its authorized default.", "Refresh complete registered scenario discovery.")

    effective_default = result.get("effective_default_model_id")
    first_choice = choices[0]
    if (
        not isinstance(effective_default, str)
        or not effective_default
        or first_choice.model_value != effective_default
    ):
        return unavailable(
            "Authoritative model discovery did not preserve the effective model as the first default choice.",
            "Refresh the registered discovery surface and require exact effective-default identity.",
        )
    return (
        tuple(choices),
        first_choice.model_value,
        first_choice.selection_mode,
        None,
    )

def _project_resolved_configuration(
    declaration: object,
    result: object,
    selected_controls: Mapping[str, object],
) -> tuple[SidebarResolvedTextProjection, ...]:
    """Project registered read-only configuration resolved by a discovery probe."""

    if not isinstance(declaration, Mapping) or not isinstance(result, Mapping):
        return ()
    if declaration.get("source") != "model_discovery":
        return ()
    result_field = declaration.get("result_field", "resolved_configuration")
    if not isinstance(result_field, str) or not result_field:
        return ()
    resolved = result.get(result_field)
    if not isinstance(resolved, Mapping):
        return ()
    fields = declaration.get("fields", ())
    if isinstance(fields, (str, bytes)) or not isinstance(fields, Sequence):
        return ()

    launch_mode = selected_controls.get("launch_mode")
    projected: list[SidebarResolvedTextProjection] = []
    for field in fields:
        if not isinstance(field, Mapping):
            return ()
        name = field.get("name")
        label = field.get("label")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(label, str)
            or not label
        ):
            return ()
        launch_modes = field.get("launch_modes")
        if launch_modes is not None:
            visible_modes = _visible_values(launch_modes)
            if visible_modes is None:
                return ()
            if launch_mode not in visible_modes:
                continue
        value = resolved.get(name)
        if not isinstance(value, str) or not value.strip():
            continue
        projected.append(
            SidebarResolvedTextProjection(
                control_name=name,
                label=label,
                value=value,
            )
        )
    return tuple(projected)
