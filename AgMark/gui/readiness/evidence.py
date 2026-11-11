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

from .controls import _diagnostic
from .models import BenchmarkEvidenceReadinessProjection

def _matching_benchmark_candidate(
    discovered_benchmark: DiscoveredRegistration,
    benchmark_candidates: Sequence[BenchmarkDiscoveryCandidate],
) -> tuple[
    BenchmarkDiscoveryCandidate | None,
    tuple[SidebarPrerequisiteDiagnosticProjection, ...],
]:
    matches: list[BenchmarkDiscoveryCandidate] = []
    for candidate in benchmark_candidates:
        if not isinstance(candidate, BenchmarkDiscoveryCandidate):
            return None, (
                _diagnostic(
                    "benchmark-registration-source",
                    "Benchmark evidence readiness metadata is not a validated discovery candidate.",
                    "Reload repository benchmark registrations through production validation.",
                ),
            )
        registration = candidate.registration
        if not isinstance(registration, Mapping):
            continue
        if (
            registration.get("registration_id") == discovered_benchmark.registration_id
            and registration.get("registration_version")
            == discovered_benchmark.registration_version
        ):
            matches.append(candidate)

    if len(matches) != 1:
        return None, (
            _diagnostic(
                "benchmark-registration-source",
                "The selected benchmark does not resolve to exactly one validated repository candidate.",
                "Reload repository discovery and resolve the benchmark from one exact validated registration.",
            ),
        )

    candidate = matches[0]
    registration = candidate.registration
    validation = candidate.registration_validation
    if (
        not isinstance(registration, Mapping)
        or validation is None
        or not validation.valid
        or not validation.matches(
            registration,
            source_id=candidate.registration_source_id,
        )
        or validation.registration_sha256 != discovered_benchmark.registration_sha256
    ):
        return None, (
            _diagnostic(
                "benchmark-registration-validation",
                "The selected benchmark registration is not validated for the exact discovered bytes.",
                "Re-run repository registration validation before building a plan.",
            ),
        )
    if (
        registration.get("registration_kind") != "benchmark"
        or registration.get("status") != "active"
    ):
        return None, (
            _diagnostic(
                "benchmark-registration-status",
                "The selected registration is not an active benchmark registration.",
                "Select an active validated benchmark registration.",
            ),
        )
    return candidate, ()

def derive_benchmark_evidence_readiness(
    *,
    discovered_benchmark: DiscoveredRegistration,
    benchmark_candidates: Sequence[BenchmarkDiscoveryCandidate],
    repository_root: str | Path,
) -> BenchmarkEvidenceReadinessProjection:
    """Project usability of the selected benchmark's durable evidence destination.

    This verifies only repository/path prerequisites. Repository/package
    accessibility remains planning-scoped; once the benchmark package resolves,
    durable evidence-destination usability is execution-scoped. This function
    does not create the destination, retain evidence, or turn diagnostic success
    into execution authority.
    """

    if not isinstance(discovered_benchmark, DiscoveredRegistration):
        raise TypeError("discovered_benchmark must be a DiscoveredRegistration")
    if isinstance(benchmark_candidates, (str, bytes)) or not isinstance(
        benchmark_candidates, Sequence
    ):
        raise TypeError("benchmark_candidates must be a sequence")
    if not isinstance(repository_root, (str, Path)):
        raise TypeError("repository_root must be a string or pathlib.Path")

    candidate, candidate_diagnostics = _matching_benchmark_candidate(
        discovered_benchmark,
        benchmark_candidates,
    )
    if candidate is None:
        return BenchmarkEvidenceReadinessProjection(
            diagnostics=candidate_diagnostics
        )

    try:
        repository = Path(repository_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return BenchmarkEvidenceReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The production repository root is not currently accessible.",
                    "Restore access to the repository before building or executing a benchmark.",
                ),
            )
        )
    if not repository.is_dir():
        return BenchmarkEvidenceReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The production repository root is not a directory.",
                    "Select a valid repository root before building or executing a benchmark.",
                ),
            )
        )

    raw_package_root = candidate.package_root
    if not isinstance(raw_package_root, str) or not raw_package_root:
        return BenchmarkEvidenceReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The selected benchmark has an unusable repository package root.",
                    "Correct and revalidate the benchmark discovery candidate.",
                ),
            )
        )
    package_root = PurePosixPath(raw_package_root)
    if (
        package_root.is_absolute()
        or package_root.as_posix() != raw_package_root
        or any(part in {"", ".", ".."} for part in package_root.parts)
    ):
        return BenchmarkEvidenceReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The selected benchmark has an unusable repository package root.",
                    "Correct and revalidate the benchmark discovery candidate.",
                ),
            )
        )

    try:
        benchmark_root = repository.joinpath(*package_root.parts).resolve(strict=True)
        benchmark_root.relative_to(repository)
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return BenchmarkEvidenceReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The selected benchmark package root is not safely accessible.",
                    "Restore the exact validated benchmark package before building or executing a plan.",
                ),
            )
        )
    if not benchmark_root.is_dir():
        return BenchmarkEvidenceReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The selected benchmark package root is not a directory.",
                    "Restore the exact validated benchmark package before building or executing a plan.",
                ),
            )
        )

    evidence_root = repository / "AgMark" / "run_evidence"
    try:
        destination = PublicationDestination.central(
            evidence_root,
            repository_root=repository,
        )
    except (ArtifactDestinationError, OSError, RuntimeError, ValueError):
        return BenchmarkEvidenceReadinessProjection(
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The selected benchmark does not resolve to a permitted central run-evidence destination.",
                    "Configure a durable permitted evidence destination before starting benchmark execution.",
                    operation="execution",
                ),
            )
        )

    root = destination.root
    if root.is_symlink():
        return BenchmarkEvidenceReadinessProjection(
            destination_root=root,
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The benchmark evidence destination is a symbolic link and cannot be trusted as a durable store root.",
                    "Replace it with a real central run-evidence directory before starting benchmark execution.",
                    operation="execution",
                ),
            ),
        )
    if root.exists() and not root.is_dir():
        return BenchmarkEvidenceReadinessProjection(
            destination_root=root,
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The benchmark evidence destination is not a directory.",
                    "Restore a writable benchmark-owned evidence directory before starting benchmark execution.",
                    operation="execution",
                ),
            ),
        )

    writable_root = root if root.exists() else repository / "AgMark"
    if not access(writable_root, W_OK | X_OK):
        return BenchmarkEvidenceReadinessProjection(
            destination_root=root,
            diagnostics=(
                _diagnostic(
                    "benchmark-evidence-destination",
                    "The benchmark evidence destination is not currently writable.",
                    "Restore write access or configure a permitted durable evidence destination before starting benchmark execution.",
                    operation="execution",
                ),
            ),
        )

    return BenchmarkEvidenceReadinessProjection(destination_root=root)
