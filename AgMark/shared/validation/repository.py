"""Fail-closed repository-boundary and benchmark-discovery validation."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any

from .core import ValidationIssue
from .registration import RegistrationValidationOutcome


_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_TESTING_ROOT = PurePosixPath("AgMark/shared/software_testing")
_SHARED_MODULE = "AgMark.shared"
_TESTING_MODULE = "AgMark.shared.software_testing"
_FRONTEND_MODULE = "AgMark.gui"


@dataclass(frozen=True)
class RepositoryOwnedPath:
    """Explicit production or developer-testing ownership for one path."""

    path: str
    role: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str):
            raise TypeError("path must be a string")
        if not isinstance(self.role, str):
            raise TypeError("role must be a string")


@dataclass(frozen=True)
class RepositoryPythonSource:
    """One exact repository-relative Python source observation."""

    path: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str):
            raise TypeError("path must be a string")
        if not isinstance(self.source, str):
            raise TypeError("source must be text")


@dataclass(frozen=True)
class BenchmarkDiscoveryCandidate:
    """One candidate and the explicit registration that may activate it."""

    package_root: str
    registration_source_id: str
    registration: Mapping[str, Any] | None
    registration_validation: RegistrationValidationOutcome | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.registration_source_id, str)
            or not self.registration_source_id
        ):
            raise ValueError("registration_source_id must be non-empty")
        if self.registration is not None and not isinstance(self.registration, Mapping):
            raise TypeError("registration must be a mapping or None")
        if (
            self.registration_validation is not None
            and type(self.registration_validation) is not RegistrationValidationOutcome
        ):
            raise TypeError(
                "registration_validation must be a RegistrationValidationOutcome "
                "or None"
            )


def validate_repository_ownership(
    paths: Sequence[RepositoryOwnedPath],
    *,
    source_id: str = "benchmarking-repository",
) -> tuple[ValidationIssue, ...]:
    """Enforce centralized developer/CI testing ownership."""

    _require_source_id(source_id)
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for index, observed in enumerate(paths):
        if type(observed) is not RepositoryOwnedPath:
            raise TypeError("paths must contain RepositoryOwnedPath values")
        pointer = f"/paths/{index}"
        path = _repository_path(observed.path)
        if path is None:
            issues.append(_issue(
                "REPOSITORY_OWNERSHIP_PATH_INVALID", source_id,
                "owned path must be canonical and repository-relative",
                f"{pointer}/path",
            ))
            continue
        if observed.path in seen:
            issues.append(_issue(
                "REPOSITORY_OWNERSHIP_PATH_AMBIGUOUS", source_id,
                f"repository path {observed.path!r} is classified more than once",
                f"{pointer}/path",
            ))
            continue
        seen.add(observed.path)
        if observed.role not in {"production", "developer_testing"}:
            issues.append(_issue(
                "REPOSITORY_OWNERSHIP_ROLE_INVALID", source_id,
                "role must be exactly 'production' or 'developer_testing'",
                f"{pointer}/role",
            ))
            continue
        in_testing = _path_within(path, _TESTING_ROOT)
        if observed.role == "developer_testing" and not in_testing:
            issues.append(_issue(
                "DEVELOPER_TESTING_OWNERSHIP_INVALID", observed.path,
                "developer/CI testing resources must reside under shared/software_testing",
            ))
        elif observed.role == "production" and in_testing:
            issues.append(_issue(
                "PRODUCTION_OWNERSHIP_INVALID", observed.path,
                "production behavior must not reside in shared/software_testing",
            ))
    return _normalize(issues)


def validate_repository_dependencies(
    python_sources: Sequence[RepositoryPythonSource],
    *,
    benchmark_module_prefixes: Sequence[str],
    source_id: str = "benchmarking-repository",
) -> tuple[ValidationIssue, ...]:
    """Validate dependency direction without importing observed code.

    Concrete benchmark prefixes are explicit inputs so benchmark identity is
    never inferred from repository directory names.
    """

    _require_source_id(source_id)
    benchmark_prefixes = _module_prefixes(benchmark_module_prefixes)
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for index, observed in enumerate(python_sources):
        if type(observed) is not RepositoryPythonSource:
            raise TypeError("python_sources must contain RepositoryPythonSource values")
        path = _repository_path(observed.path)
        pointer = f"/python_sources/{index}/path"
        if path is None or path.suffix != ".py":
            issues.append(_issue(
                "REPOSITORY_SOURCE_PATH_INVALID", source_id,
                "Python source path must be canonical, repository-relative, and end in .py",
                pointer,
            ))
            continue
        if observed.path in seen:
            issues.append(_issue(
                "REPOSITORY_SOURCE_DUPLICATE", source_id,
                f"repository source {observed.path!r} is supplied more than once",
                pointer,
            ))
            continue
        seen.add(observed.path)
        module = _module_for_path(path)
        try:
            tree = ast.parse(observed.source, filename=observed.path)
        except SyntaxError as exc:
            line = f"line {exc.lineno}" if exc.lineno else "unknown line"
            issues.append(_issue(
                "REPOSITORY_SOURCE_PARSE_INVALID", observed.path,
                f"Python source cannot be parsed safely ({line})",
            ))
            continue

        shared = _within_module(module, _SHARED_MODULE)
        testing = _within_module(module, _TESTING_MODULE)
        frontend = _within_module(module, _FRONTEND_MODULE)
        for imported, line in _imports(tree, module):
            if not testing and _within_module(imported, _TESTING_MODULE):
                issues.append(_dependency_issue(
                    "PRODUCTION_TESTING_IMPORT_FORBIDDEN", observed.path,
                    imported, line,
                    "production code must not import centralized testing resources",
                ))
            if shared and not testing and _within_module(imported, _FRONTEND_MODULE):
                issues.append(_dependency_issue(
                    "SHARED_FRONTEND_IMPORT_FORBIDDEN", observed.path,
                    imported, line, "shared production code must not import GUI code",
                ))
            if shared and not testing and _matches(imported, benchmark_prefixes):
                issues.append(_dependency_issue(
                    "SHARED_BENCHMARK_IMPORT_FORBIDDEN", observed.path,
                    imported, line,
                    "shared production code must not import a concrete benchmark",
                ))
            if frontend and _matches(imported, benchmark_prefixes):
                issues.append(_dependency_issue(
                    "FRONTEND_BENCHMARK_IMPORT_FORBIDDEN", observed.path,
                    imported, line,
                    "frontend code must use shared registration boundaries",
                ))
    return _normalize(issues)


def validate_benchmark_discovery(
    candidates: Sequence[BenchmarkDiscoveryCandidate],
    *,
    source_id: str = "benchmark-discovery",
) -> tuple[ValidationIssue, ...]:
    """Require explicit, validated, active registrations for discovery."""

    _require_source_id(source_id)
    issues: list[ValidationIssue] = []
    identities: set[tuple[str, str]] = set()
    roots: set[PurePosixPath] = set()
    for index, candidate in enumerate(candidates):
        if type(candidate) is not BenchmarkDiscoveryCandidate:
            raise TypeError("candidates must contain BenchmarkDiscoveryCandidate values")
        pointer = f"/candidates/{index}"
        sid = candidate.registration_source_id
        root = _repository_path(candidate.package_root)
        if root is None:
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_PACKAGE_ROOT_INVALID", sid,
                "benchmark package root must be canonical and repository-relative",
                f"{pointer}/package_root",
            ))
        elif root in roots:
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_PACKAGE_ROOT_AMBIGUOUS", sid,
                f"benchmark package root {candidate.package_root!r} is duplicated",
                f"{pointer}/package_root",
            ))
        else:
            roots.add(root)
            if _path_within(root, PurePosixPath("AgMark/shared")) or _path_within(
                root, PurePosixPath("AgMark/gui")
            ):
                issues.append(_issue(
                    "BENCHMARK_DISCOVERY_PACKAGE_ROOT_FORBIDDEN", sid,
                    "benchmark packages must remain outside shared and GUI ownership roots",
                    f"{pointer}/package_root",
                ))

        registration = candidate.registration
        if registration is None:
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_REGISTRATION_MISSING", sid,
                "directory/package presence cannot activate a benchmark",
                f"{pointer}/registration",
            ))
            continue
        validation = candidate.registration_validation
        if validation is None:
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_REGISTRATION_UNVALIDATED", sid,
                "registration must be explicitly validated before discovery",
                f"{pointer}/registration",
            ))
        elif not validation.matches(registration, source_id=sid):
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_REGISTRATION_VALIDATION_MISMATCH", sid,
                (
                    "registration validation outcome is not bound to this exact "
                    "registration and source identity"
                ),
                f"{pointer}/registration",
            ))
        elif not validation.valid:
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_REGISTRATION_INVALID", sid,
                "registration validation failed and cannot authorize discovery",
                f"{pointer}/registration",
            ))
        if registration.get("registration_kind") != "benchmark":
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_REGISTRATION_KIND_INVALID", sid,
                "registration_kind must be exactly 'benchmark'",
                f"{pointer}/registration/registration_kind",
            ))
        if registration.get("status") != "active":
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_REGISTRATION_INACTIVE", sid,
                "only an explicitly active registration may authorize discovery",
                f"{pointer}/registration/status",
            ))

        registration_id = registration.get("registration_id")
        version = registration.get("registration_version")
        if not isinstance(registration_id, str) or not registration_id:
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_IDENTITY_INVALID", sid,
                "benchmark discovery requires an explicit registration_id",
                f"{pointer}/registration/registration_id",
            ))
            continue
        if not isinstance(version, str) or not version:
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_IDENTITY_INVALID", sid,
                "benchmark discovery requires an explicit registration_version",
                f"{pointer}/registration/registration_version",
            ))
            continue
        identity = (registration_id, version)
        if identity in identities:
            issues.append(_issue(
                "BENCHMARK_DISCOVERY_IDENTITY_AMBIGUOUS", sid,
                f"benchmark registration {registration_id!r} {version!r} is duplicated",
                f"{pointer}/registration/registration_id",
            ))
        else:
            identities.add(identity)
    return _normalize(issues)


def _imports(tree: ast.AST, module: str) -> tuple[tuple[str, int], ...]:
    package = module.rpartition(".")[0]
    if module.endswith(".__init__"):
        package = module[: -len(".__init__")]
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_import(package, node.level, node.module)
            if base:
                for alias in node.names:
                    imported = base if alias.name == "*" else f"{base}.{alias.name}"
                    found.append((imported, node.lineno))
    return tuple(found)


def _resolve_import(package: str, level: int, module: str | None) -> str | None:
    if level == 0:
        return module
    parts = package.split(".") if package else []
    drop = level - 1
    if drop > len(parts):
        return None
    prefix = parts[: len(parts) - drop]
    if module:
        prefix.extend(module.split("."))
    return ".".join(prefix) or None


def _module_for_path(path: PurePosixPath) -> str:
    parts = list(path.with_suffix("").parts)
    return ".".join(parts)


def _module_prefixes(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, str):
        raise ValueError("benchmark_module_prefixes must be a sequence")
    result = tuple(values)
    if not result:
        raise ValueError("benchmark_module_prefixes must not be empty")
    if len(set(result)) != len(result):
        raise ValueError("benchmark_module_prefixes must not contain duplicates")
    if not all(isinstance(value, str) and _MODULE.fullmatch(value) for value in result):
        raise ValueError("benchmark_module_prefixes must contain dotted Python modules")
    return result


def _repository_path(value: str) -> PurePosixPath | None:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        return None
    if len(value) >= 2 and value[1] == ":":
        return None
    path = PurePosixPath(value)
    if str(path) != value or path == PurePosixPath("."):
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def _path_within(path: PurePosixPath, root: PurePosixPath) -> bool:
    return path == root or root in path.parents


def _within_module(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _matches(module: str, prefixes: Sequence[str]) -> bool:
    return any(_within_module(module, prefix) for prefix in prefixes)


def _dependency_issue(
    code: str,
    source_path: str,
    imported: str,
    line: int,
    reason: str,
) -> ValidationIssue:
    return _issue(code, source_path, f"{reason}: import {imported!r} at line {line}")


def _issue(
    code: str,
    source_id: str,
    message: str,
    pointer: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        source_id=source_id,
        message=message,
        json_pointer=pointer,
    )


def _require_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id must be non-empty")


def _normalize(issues: Sequence[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


__all__ = [
    "BenchmarkDiscoveryCandidate",
    "RepositoryOwnedPath",
    "RepositoryPythonSource",
    "validate_benchmark_discovery",
    "validate_repository_dependencies",
    "validate_repository_ownership",
]
