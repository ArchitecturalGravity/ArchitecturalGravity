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

def derive_application_environment(
    *,
    discovery: ApplicationDiscovery | None,
    sidebar: SidebarProjection,
    evidence_destination: str | Path | None = None,
    supplied_entries: Sequence[EnvironmentDiagnosticEntry] = (),
) -> ApplicationEnvironmentProjection:
    """Derive one generation-free current Environment snapshot.

    The snapshot is presentation-only. It reports supplied discovery,
    configuration, readiness, and pre-generation diagnostics without retaining
    historical warnings or rendering transient secret values.
    """

    if discovery is not None and type(discovery) is not ApplicationDiscovery:
        raise TypeError("discovery must be ApplicationDiscovery or None")
    if not isinstance(sidebar, SidebarProjection):
        raise TypeError("sidebar must be SidebarProjection")
    if evidence_destination is not None and not isinstance(
        evidence_destination, (str, Path)
    ):
        raise TypeError("evidence_destination must be a string, pathlib.Path, or None")
    if isinstance(supplied_entries, (str, bytes)) or not isinstance(
        supplied_entries, Sequence
    ):
        raise TypeError("supplied_entries must be a sequence")
    supplied = tuple(supplied_entries)
    if any(not isinstance(entry, EnvironmentDiagnosticEntry) for entry in supplied):
        raise TypeError(
            "supplied_entries must contain EnvironmentDiagnosticEntry values"
        )

    entries: list[EnvironmentDiagnosticEntry] = []
    if discovery is None:
        entries.append(
            EnvironmentDiagnosticEntry(
                source="Discovery",
                state="unresolved",
                summary="Repository application discovery has not completed.",
                blocking=True,
            )
        )
    else:
        usable = bool(discovery.benchmarks and discovery.runners)
        entries.append(
            EnvironmentDiagnosticEntry(
                source="Discovery",
                state="ready" if usable else "unresolved",
                summary=(
                    f"Discovered {len(discovery.benchmarks)} benchmark registration(s) "
                    f"and {len(discovery.runners)} runner registration(s)."
                ),
                blocking=not usable,
            )
        )

    if sidebar.selected_benchmark is not None:
        entries.append(
            EnvironmentDiagnosticEntry(
                source="Benchmark",
                state="info",
                summary="Selected benchmark registration.",
                details=sidebar.selected_benchmark,
            )
        )
    elif sidebar.benchmark_options:
        entries.append(
            EnvironmentDiagnosticEntry(
                source="Benchmark",
                state="unresolved",
                summary="A benchmark registration must be selected.",
                blocking=True,
            )
        )

    if sidebar.selected_runner is not None:
        entries.append(
            EnvironmentDiagnosticEntry(
                source="Runner",
                state="info",
                summary="Selected runner registration.",
                details=sidebar.selected_runner,
            )
        )
    elif sidebar.runner_options:
        entries.append(
            EnvironmentDiagnosticEntry(
                source="Runner",
                state="unresolved",
                summary="A runner registration must be selected.",
                blocking=True,
            )
        )

    if evidence_destination is not None:
        entries.append(
            EnvironmentDiagnosticEntry(
                source="Evidence destination",
                state="ready",
                summary="Benchmark-owned evidence destination is usable.",
                details=str(evidence_destination),
            )
        )

    if sidebar.model_required:
        entries.append(
            EnvironmentDiagnosticEntry(
                source="Model",
                state="ready" if sidebar.selected_model is not None else "unresolved",
                summary=(
                    "Required model selection is supplied."
                    if sidebar.selected_model is not None
                    else "A required model selection is unresolved."
                ),
                details=sidebar.selected_model,
                blocking=sidebar.selected_model is None,
            )
        )

    for label, numeric in (
        ("Temperature", sidebar.temperature),
        ("Max tokens", sidebar.max_tokens),
    ):
        if numeric is None or not numeric.required:
            continue
        resolved = numeric.value is not None
        entries.append(
            EnvironmentDiagnosticEntry(
                source=label,
                state="ready" if resolved else "unresolved",
                summary=(
                    f"Required {label.lower()} configuration is supplied."
                    if resolved
                    else f"Required {label.lower()} configuration is unresolved."
                ),
                blocking=not resolved,
            )
        )

    for control in sidebar.additional_controls:
        if not control.required:
            continue
        if isinstance(control, SidebarTextControlProjection) and control.secret:
            entries.append(
                EnvironmentDiagnosticEntry(
                    source=control.label,
                    state="info",
                    summary=(
                        "This required transient secret input is excluded from "
                        "Environment state."
                    ),
                )
            )
            continue
        if isinstance(control, SidebarTextControlProjection):
            resolved = bool(control.value)
        elif isinstance(control, SidebarChoiceControlProjection):
            resolved = control.selected_value is not None
        elif isinstance(control, SidebarNumericControlProjection):
            resolved = control.numeric.value is not None
        else:
            resolved = False
        entries.append(
            EnvironmentDiagnosticEntry(
                source=control.label,
                state="ready" if resolved else "unresolved",
                summary=(
                    "Required configuration is supplied."
                    if resolved
                    else "Required configuration is unresolved."
                ),
                blocking=not resolved,
            )
        )

    for diagnostic in sidebar.prerequisite_diagnostics:
        entries.append(
            EnvironmentDiagnosticEntry(
                source=f"Prerequisite {diagnostic.diagnostic_name}",
                state="unresolved",
                summary=diagnostic.message,
                details=diagnostic.details,
                remediation=diagnostic.remediation,
                blocking=True,
            )
        )

    entries.extend(supplied)
    return ApplicationEnvironmentProjection(entries=tuple(entries))
