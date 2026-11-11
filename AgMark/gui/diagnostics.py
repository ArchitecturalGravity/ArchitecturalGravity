"""Production frontend diagnostics for the Python desktop client."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
import sys


_STARTUP_ERROR_TITLE = "AgMark - Startup Error"
_ENVIRONMENT_STATES = frozenset(
    {"info", "ready", "warning", "failure", "unavailable", "unresolved"}
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|api[_ -]?key|token|secret|password|passwd|credential)"
    r"(\s*[:=]\s*)(?:Bearer\s+)?([^\s,;]+)"
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def sanitize_environment_text(value: str) -> str:
    """Redact common secret-bearing text before Environment presentation."""

    if not isinstance(value, str):
        raise TypeError("environment text must be a string")
    redacted = _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        value,
    )
    return _BEARER_VALUE.sub("Bearer <redacted>", redacted)


def _environment_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return sanitize_environment_text(value.strip())


@dataclass(frozen=True, slots=True)
class EnvironmentDiagnosticEntry:
    """One non-authoritative application/session Environment state entry."""

    source: str
    state: str
    summary: str
    details: str | None = None
    remediation: str | None = None
    blocking: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source",
            _environment_text(self.source, name="environment source"),
        )
        if self.state not in _ENVIRONMENT_STATES:
            raise ValueError(
                "environment state must be info, ready, warning, failure, "
                "unavailable, or unresolved"
            )
        object.__setattr__(
            self,
            "summary",
            _environment_text(self.summary, name="environment summary"),
        )
        for field_name in ("details", "remediation"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, str):
                raise ValueError(f"{field_name} must be text or None")
            normalized = value.strip()
            object.__setattr__(
                self,
                field_name,
                sanitize_environment_text(normalized) if normalized else None,
            )
        if type(self.blocking) is not bool:
            raise ValueError("blocking must be boolean")

    def render(self) -> str:
        lines = [f"[{self.state.upper()}] {self.source}: {self.summary}"]
        if self.details is not None:
            lines.append(f"  Detail: {self.details}")
        if self.remediation is not None:
            lines.append(f"  Remediation: {self.remediation}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ApplicationEnvironmentProjection:
    """Refreshable current application/session Environment snapshot."""

    entries: tuple[EnvironmentDiagnosticEntry, ...] = ()

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        if any(not isinstance(entry, EnvironmentDiagnosticEntry) for entry in entries):
            raise ValueError(
                "entries must contain only EnvironmentDiagnosticEntry values"
            )
        object.__setattr__(self, "entries", entries)

    @property
    def has_blockers(self) -> bool:
        return any(entry.blocking for entry in self.entries)

    def render(self) -> str:
        if not self.entries:
            return (
                "[UNAVAILABLE] Environment: No application/session Environment "
                "state is currently available."
            )
        return "\n\n".join(entry.render() for entry in self.entries)


@dataclass(frozen=True, slots=True)
class StartupFailureDiagnostic:
    """Actionable, presentation-only startup failure information."""

    summary: str
    details: str
    remediation: str

    def render(self) -> str:
        return f"{self.summary}\n\n{self.details}\n\n{self.remediation}"


def startup_failure_diagnostic(error: BaseException) -> StartupFailureDiagnostic:
    """Normalize a startup exception into actionable non-authoritative diagnostics."""

    if not isinstance(error, BaseException):
        raise ValueError("error must be an exception")

    details = str(error).strip() or error.__class__.__name__
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        remediation = (
            "Run AgMark\\Windows_Setup.bat, then launch again from the "
            "repository checkout."
        )
    elif error.__class__.__name__ == "RepositoryCompositionError":
        remediation = (
            "Check the repository registration files and referenced production "
            "artifacts, correct the reported authority problem, then launch again."
        )
    else:
        remediation = (
            "Review the reported startup detail. If the GUI environment is not "
            "initialized, run AgMark\\Windows_Setup.bat; otherwise correct "
            "the repository/runtime prerequisite and launch again."
        )

    return StartupFailureDiagnostic(
        summary="AgMark could not start.",
        details=details,
        remediation=remediation,
    )


def startup_environment_entry(
    diagnostic: StartupFailureDiagnostic,
) -> EnvironmentDiagnosticEntry:
    """Convert a startup failure into session-scoped Environment state."""

    if not isinstance(diagnostic, StartupFailureDiagnostic):
        raise ValueError("diagnostic must be StartupFailureDiagnostic")
    return EnvironmentDiagnosticEntry(
        source="Startup",
        state="failure",
        summary=diagnostic.summary,
        details=diagnostic.details,
        remediation=diagnostic.remediation,
        blocking=True,
    )


def environment_failure_entry(
    error: BaseException,
    *,
    source: str = "Application",
) -> EnvironmentDiagnosticEntry:
    """Normalize a pre-generation failure for Environment presentation."""

    if not isinstance(error, BaseException):
        raise ValueError("error must be an exception")
    return EnvironmentDiagnosticEntry(
        source=source,
        state="failure",
        summary="A pre-generation application operation failed.",
        details=str(error).strip() or error.__class__.__name__,
        blocking=True,
    )


def environment_projection_failure_entry(
    error: BaseException,
) -> EnvironmentDiagnosticEntry:
    """Normalize an Environment projection failure for fail-closed presentation."""

    if not isinstance(error, BaseException):
        raise ValueError("error must be an exception")
    return EnvironmentDiagnosticEntry(
        source="Environment Projection",
        state="failure",
        summary="Environment projection could not be produced.",
        details=str(error).strip() or error.__class__.__name__,
        blocking=True,
    )


def application_failure_diagnostic(
    error: BaseException,
    *,
    source: str = "Application",
) -> str:
    """Render one sanitized generation-scoped application failure diagnostic."""

    if not isinstance(error, BaseException):
        raise ValueError("error must be an exception")
    source_text = _environment_text(source, name="diagnostic source")
    detail = sanitize_environment_text(
        str(error).strip() or error.__class__.__name__
    )
    return (
        f"[FAILURE] {source_text}: An application operation failed.\n"
        f"  Detail: {detail}\n"
    )


def present_startup_failure(
    diagnostic: StartupFailureDiagnostic,
    *,
    native: bool = False,
) -> None:
    """Present startup diagnostics to a console or a native Windows error dialog."""

    if not isinstance(diagnostic, StartupFailureDiagnostic):
        raise ValueError("diagnostic must be StartupFailureDiagnostic")

    message = diagnostic.render()
    if native and os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                message,
                _STARTUP_ERROR_TITLE,
                0x00000010,
            )
            return
        except (AttributeError, OSError):
            pass

    print(f"{_STARTUP_ERROR_TITLE}\n{message}", file=sys.stderr)


__all__ = [
    "ApplicationEnvironmentProjection",
    "EnvironmentDiagnosticEntry",
    "application_failure_diagnostic",
    "StartupFailureDiagnostic",
    "environment_failure_entry",
    "environment_projection_failure_entry",
    "present_startup_failure",
    "sanitize_environment_text",
    "startup_environment_entry",
    "startup_failure_diagnostic",
]
