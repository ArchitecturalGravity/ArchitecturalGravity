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

@dataclass(frozen=True, slots=True)
class RunnerReadinessProjection:
    """Registration-derived presentation state for one discovered runner."""

    runner_connectivity: tuple[str, str, str] = (
        "Runner not checked", "neutral", "Runner connection has not been checked."
    )
    runner_test_supported: bool = False
    model_control_present: bool = False
    scenario_visible: bool = False
    reasoning_effort_control_name: str | None = None
    model_options: tuple[str, ...] = ()
    selected_model: str | None = None
    model_choices: tuple[SidebarModelChoiceProjection, ...] = ()
    selected_model_selection_mode: str | None = None
    model_editable: bool = False
    model_required: bool = False
    model_discovery_authoritative: bool = False
    model_discovery_determining_controls: tuple[str, ...] = ()
    model_discovery_context_fingerprints: tuple[str, ...] = ()
    authentication_satisfied: bool = False
    credentials_required: bool = False
    numeric_controls_projected: bool = False
    temperature: NumericInputProjection | None = None
    max_tokens: NumericInputProjection | None = None
    additional_controls: tuple[
        SidebarTextControlProjection | SidebarChoiceControlProjection,
        ...,
    ] = ()
    resolved_configuration: tuple[SidebarResolvedTextProjection, ...] = ()
    diagnostics: tuple[SidebarPrerequisiteDiagnosticProjection, ...] = ()

@dataclass(frozen=True, slots=True)
class BenchmarkEvidenceReadinessProjection:
    """Repository-derived evidence-destination readiness for one benchmark."""

    destination_root: Path | None = None
    diagnostics: tuple[SidebarPrerequisiteDiagnosticProjection, ...] = ()
