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
from AgMark.shared.validation import (
    BenchmarkDiscoveryCandidate,
    implementation_artifact_sha256,
)

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

def _invoke_optional_control_probe(
    probe: Callable[..., object],
    primary: object,
    selected_control_values: Mapping[str, object],
    *,
    keyword: str | None = None,
) -> object:
    """Call a readiness probe with selected controls when its signature accepts them."""

    try:
        probe_signature = signature(probe)
    except (TypeError, ValueError):
        return probe(primary)

    if keyword is None:
        args = (primary, selected_control_values)
        kwargs: dict[str, object] = {}
    else:
        args = (primary,)
        kwargs = {keyword: selected_control_values}

    try:
        probe_signature.bind(*args, **kwargs)
    except TypeError:
        return probe(primary)
    return probe(*args, **kwargs)

def probe_registered_runner_authentication(
    source: ApplicationRegistrationSource,
    *,
    repository_root: str | Path,
    selected_control_values: Mapping[str, object] | None = None,
) -> bool | None:
    """Invoke one exact registration-declared adapter authentication probe."""

    if not isinstance(source, ApplicationRegistrationSource):
        raise TypeError("source must be an ApplicationRegistrationSource")
    if selected_control_values is not None and not isinstance(
        selected_control_values, Mapping
    ):
        raise TypeError("selected_control_values must be a mapping or None")
    selected_controls = selected_control_values or {}
    root = Path(repository_root).expanduser().resolve()
    registration = source.registration
    validation = source.registration_validation
    if (
        not validation.valid
        or not validation.matches(
            registration,
            source_id=source.registration_source_id,
        )
    ):
        return None

    extensions = registration.get("extensions")
    if not isinstance(extensions, Mapping):
        return None
    declaration = extensions.get(_AUTHENTICATION_PROBE)
    if not isinstance(declaration, Mapping):
        return None
    if set(declaration) != {"entry_point", "implementation_artifact_id"}:
        return None
    entry_point = declaration.get("entry_point")
    artifact_id = declaration.get("implementation_artifact_id")
    if (
        not isinstance(entry_point, str)
        or ":" not in entry_point
        or not isinstance(artifact_id, str)
        or not artifact_id
    ):
        return None

    raw_artifacts = registration.get("implementation_artifacts")
    if isinstance(raw_artifacts, (str, bytes)) or not isinstance(
        raw_artifacts, Sequence
    ):
        return None
    artifacts = [
        artifact
        for artifact in raw_artifacts
        if isinstance(artifact, Mapping)
        and artifact.get("artifact_id") == artifact_id
    ]
    if len(artifacts) != 1:
        return None
    artifact = artifacts[0]
    reference = artifact.get("reference")
    expected_sha256 = artifact.get("sha256")
    if (
        not isinstance(reference, str)
        or not reference.endswith(".py")
        or not isinstance(expected_sha256, str)
        or not expected_sha256.startswith("sha256:")
    ):
        return None

    try:
        artifact_path = (root / PurePosixPath(reference)).resolve(strict=True)
        artifact_path.relative_to(root)
    except (OSError, ValueError):
        return None
    if not artifact_path.is_file():
        return None
    try:
        observed_sha256 = implementation_artifact_sha256(
            reference,
            artifact_path.read_bytes(),
        )
    except OSError:
        return None
    if observed_sha256 != expected_sha256:
        return None

    module_name, separator, attribute_name = entry_point.partition(":")
    expected_module = reference[:-3].replace("/", ".")
    if (
        separator != ":"
        or module_name != expected_module
        or not attribute_name
        or "." in attribute_name
    ):
        return None

    try:
        module = import_module(module_name)
        module_file = Path(module.__file__).resolve(strict=True)
    except (ImportError, AttributeError, OSError, TypeError, ValueError):
        return None
    if module_file != artifact_path:
        return None
    probe = getattr(module, attribute_name, None)
    if not callable(probe):
        return None

    try:
        result = _invoke_optional_control_probe(
            probe,
            registration,
            selected_controls,
            keyword="control_values",
        )
    except Exception:
        return None
    return result if type(result) is bool else None
