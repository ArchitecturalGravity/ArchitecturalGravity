"""Target-independent runner execution orchestration primitives."""

from __future__ import annotations

from contextvars import ContextVar
from contextlib import contextmanager

_STARTUP_OBSERVER = ContextVar("arcgrav_invocation_startup_observer", default=None)


@contextmanager
def observe_invocation_startup(observer):
    """Runtime-owned observer; never changes a scored invocation or its result."""
    token = _STARTUP_OBSERVER.set(observer)
    try:
        yield
    finally:
        _STARTUP_OBSERVER.reset(token)


def observe_startup(**facts):
    observer = _STARTUP_OBSERVER.get()
    if observer is not None:
        # Optional validation cannot prevent the accepted scored invocation.
        try:
            observer(**facts)
        except Exception:
            pass

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import subprocess
import tempfile
import time
from types import MappingProxyType
from typing import Any, Callable, ContextManager, Iterator, Mapping


class ExecutionFailureKind(str, Enum):
    """Internal failure causes derived from runner-observed execution facts."""

    PREFLIGHT_UNSUPPORTED = "preflight_unsupported"

    ISOLATION_FAILED = "isolation_failed"
    INVOCATION_FAILED = "invocation_failed"
    CAPTURE_INVALID = "capture_invalid"
    PROCESS_FAILED = "process_failed"
    RESPONSE_EXTRACTION_FAILED = "response_extraction_failed"
    RESPONSE_UNAVAILABLE = "response_unavailable"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ExecutionIsolation:
    """Target-independent isolation facts established for one invocation."""

    fresh_process: bool
    fresh_workdir: bool
    prior_observation_context_reused: bool
    session_home_reused: bool | None

    def __post_init__(self) -> None:
        for name in (
            "fresh_process",
            "fresh_workdir",
            "prior_observation_context_reused",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        if self.session_home_reused is not None and not isinstance(
            self.session_home_reused, bool
        ):
            raise ValueError("session_home_reused must be boolean or None")


@dataclass(frozen=True)
class InvocationContext:
    """Transient invocation context; environment values are not retained in results."""

    cwd: Path
    environment: Mapping[str, str]
    isolation: ExecutionIsolation

    def __post_init__(self) -> None:
        cwd = Path(self.cwd)
        environment = dict(self.environment)
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in environment.items()
        ):
            raise ValueError(
                "invocation environment must contain only string names and values"
            )
        if not isinstance(self.isolation, ExecutionIsolation):
            raise ValueError("isolation must be ExecutionIsolation")
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(self, "environment", MappingProxyType(environment))


@dataclass(frozen=True)
class InvocationCapture:
    """Exact process/transport facts returned by one target invocation."""

    succeeded: bool
    exit_status: int | None
    transport_status: str | None
    stdout: bytes
    stderr: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.succeeded, bool):
            raise ValueError("capture succeeded must be boolean")
        if self.exit_status is not None and (
            isinstance(self.exit_status, bool) or not isinstance(self.exit_status, int)
        ):
            raise ValueError("capture exit_status must be an integer or None")
        if self.transport_status is not None and (
            not isinstance(self.transport_status, str) or not self.transport_status
        ):
            raise ValueError(
                "capture transport_status must be non-empty text or None"
            )
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise ValueError("capture stdout/stderr must be exact bytes")


@dataclass(frozen=True)
class TerminalExecutionResult:
    """One terminal result produced from one shared execution attempt."""

    terminal_status: str
    failure_kind: ExecutionFailureKind | None
    started_at: str
    completed_at: str
    duration_ms: float
    invocation_occurred: bool
    capture: InvocationCapture
    response_bytes: bytes | None
    isolation: ExecutionIsolation | None
    # A bare interrupt has no trustworthy channel capture, unlike cancellation
    # which explicitly carries observed partial stdout/stderr.
    process_channels_observed: bool = True

    def __post_init__(self) -> None:
        if self.terminal_status not in {
            "completed",
            "failed",
            "timed_out",
            "cancelled",
            "unsupported",
        }:
            raise ValueError(
                f"invalid execution terminal status: {self.terminal_status}"
            )
        if self.terminal_status == "unsupported":
            if (
                self.failure_kind is not ExecutionFailureKind.PREFLIGHT_UNSUPPORTED
                or self.invocation_occurred
                or self.response_bytes is not None
                or self.isolation is not None
            ):
                raise ValueError(
                    "unsupported preflight must not represent a target invocation"
                )
        elif self.failure_kind is ExecutionFailureKind.PREFLIGHT_UNSUPPORTED:
            raise ValueError(
                "preflight_unsupported requires unsupported terminal status"
            )
        if self.terminal_status == "completed" and self.failure_kind is not None:
            raise ValueError("completed execution cannot retain a failure kind")
        if self.terminal_status != "completed" and self.failure_kind is None:
            raise ValueError("non-completed execution requires a failure kind")
        if not isinstance(self.process_channels_observed, bool):
            raise ValueError("process_channels_observed must be boolean")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if self.response_bytes is not None and not isinstance(
            self.response_bytes, bytes
        ):
            raise ValueError("response_bytes must be exact bytes or None")


class InvocationCancelled(Exception):
    """Signal accepted orchestration cancellation while preserving partial output."""

    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"") -> None:
        super().__init__("invocation cancelled")
        if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
            raise ValueError("cancelled stdout/stderr must be exact bytes")
        self.stdout = stdout
        self.stderr = stderr


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace")
    return b""


def _capture(value: InvocationCapture | Mapping[str, Any]) -> InvocationCapture:
    if isinstance(value, InvocationCapture):
        # Typed transport results must obey the mapping capture's exit/success rule.
        if value.exit_status is not None and value.succeeded != (value.exit_status == 0):
            raise ValueError("invocation result success conflicts with exit status")
        return value
    if not isinstance(value, Mapping):
        raise ValueError("invocation result must be InvocationCapture or a mapping")

    raw_exit_status = value.get("exit_status", value.get("returncode"))
    exit_status: int | None
    if raw_exit_status is None:
        exit_status = None
    elif isinstance(raw_exit_status, bool) or not isinstance(raw_exit_status, int):
        raise ValueError(
            "invocation result exit status must be an integer or None"
        )
    else:
        exit_status = raw_exit_status

    if "succeeded" in value:
        succeeded = value["succeeded"]
        if not isinstance(succeeded, bool):
            raise ValueError("invocation result succeeded must be boolean")
        if exit_status is not None and succeeded != (exit_status == 0):
            raise ValueError(
                "invocation result success conflicts with exit status"
            )
    elif exit_status is not None:
        succeeded = exit_status == 0
    else:
        raise ValueError(
            "invocation result without exit status must declare succeeded"
        )

    stdout = value.get("stdout", b"")
    stderr = value.get("stderr", b"")
    if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
        raise ValueError("invocation result stdout/stderr must be exact bytes")
    transport_status = value.get("transport_status")
    if transport_status is not None and (
        not isinstance(transport_status, str) or not transport_status
    ):
        raise ValueError(
            "invocation result transport_status must be non-empty text or None"
        )

    return InvocationCapture(
        succeeded=succeeded,
        exit_status=exit_status,
        transport_status=transport_status,
        stdout=stdout,
        stderr=stderr,
    )


def _partial_capture(
    *,
    stdout: object = None,
    stderr: object = None,
    transport_status: str | None,
) -> InvocationCapture:
    return InvocationCapture(
        succeeded=False,
        exit_status=None,
        transport_status=transport_status,
        stdout=_bytes(stdout),
        stderr=_bytes(stderr),
    )


def _finish(
    *,
    terminal_status: str,
    failure_kind: ExecutionFailureKind | None,
    started_at: str,
    started_mono: float,
    invocation_occurred: bool,
    capture: InvocationCapture,
    response_bytes: bytes | None,
    isolation: ExecutionIsolation | None,
    timestamp: Callable[[], str],
    monotonic: Callable[[], float],
    process_channels_observed: bool = True,
) -> TerminalExecutionResult:
    return TerminalExecutionResult(
        terminal_status=terminal_status,
        failure_kind=failure_kind,
        started_at=started_at,
        completed_at=timestamp(),
        duration_ms=max(0.0, (monotonic() - started_mono) * 1000.0),
        invocation_occurred=invocation_occurred,
        capture=capture,
        response_bytes=response_bytes,
        isolation=isolation,
        process_channels_observed=process_channels_observed,
    )


def execute_target(
    *,
    isolation: ContextManager[InvocationContext],
    invoke: Callable[
        [InvocationContext, int],
        InvocationCapture | Mapping[str, Any],
    ],
    response_extractor: Callable[[InvocationCapture], bytes | None],
    timeout_ms: int,
    timestamp: Callable[[], str] | None = None,
    monotonic: Callable[[], float] | None = None,
    before_invoke: Callable[[InvocationContext], None] | None = None,
) -> TerminalExecutionResult:
    """Execute one target through shared isolation, capture, and terminal handling.

    Target-specific code supplies only the isolation context, invocation operation, and
    response extraction rule. Terminal status is derived from observed orchestration
    facts, never from target class, evidence class, or scenario identity.
    """

    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or timeout_ms < 1
    ):
        raise ValueError("timeout_ms must be a positive integer")
    if not callable(invoke):
        raise TypeError("invoke must be callable")
    if not callable(response_extractor):
        raise TypeError("response_extractor must be callable")

    timestamp_fn = timestamp or _utc_now
    monotonic_fn = monotonic or time.monotonic
    started_at = timestamp_fn()
    started_mono = monotonic_fn()
    invocation_occurred = False
    isolation_evidence: ExecutionIsolation | None = None
    observed_capture: InvocationCapture | None = None
    observed_channels = False

    try:
        with isolation as context:
            if not isinstance(context, InvocationContext):
                raise TypeError(
                    "isolation context must yield InvocationContext"
                )
            isolation_evidence = context.isolation
            if (
                not isolation_evidence.fresh_process
                or not isolation_evidence.fresh_workdir
                or isolation_evidence.prior_observation_context_reused
            ):
                raise ValueError("execution isolation is not clean")
            if before_invoke is not None:
                preparation_started = monotonic_fn()
                try:
                    before_invoke(context)
                finally:
                    # Validation preparation is outside scored process latency.
                    started_mono += max(0.0, monotonic_fn() - preparation_started)
            invocation_occurred = True
            try:
                raw_capture = invoke(context, timeout_ms)
            except subprocess.TimeoutExpired as exc:
                observed_capture = _partial_capture(
                    stdout=getattr(exc, "output", None),
                    stderr=getattr(exc, "stderr", None),
                    transport_status="timed_out",
                )
                observed_channels = True
                return _finish(
                    terminal_status="timed_out",
                    failure_kind=ExecutionFailureKind.TIMED_OUT,
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=observed_capture,
                    response_bytes=None,
                    isolation=isolation_evidence,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )
            except InvocationCancelled as exc:
                observed_capture = _partial_capture(
                    stdout=exc.stdout,
                    stderr=exc.stderr,
                    transport_status="cancelled",
                )
                observed_channels = True
                return _finish(
                    terminal_status="cancelled",
                    failure_kind=ExecutionFailureKind.CANCELLED,
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=observed_capture,
                    response_bytes=None,
                    isolation=isolation_evidence,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )
            except KeyboardInterrupt:
                return _finish(
                    terminal_status="cancelled",
                    failure_kind=ExecutionFailureKind.CANCELLED,
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=_partial_capture(
                        transport_status="cancelled"
                    ),
                    response_bytes=None,
                    isolation=isolation_evidence,
                    process_channels_observed=False,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )
            except Exception:
                return _finish(
                    terminal_status="failed",
                    failure_kind=ExecutionFailureKind.INVOCATION_FAILED,
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=_partial_capture(
                        transport_status="failed"
                    ),
                    response_bytes=None,
                    isolation=isolation_evidence,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )

            try:
                capture = _capture(raw_capture)
            except (TypeError, ValueError):
                return _finish(
                    terminal_status="failed",
                    failure_kind=ExecutionFailureKind.CAPTURE_INVALID,
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=_partial_capture(
                        transport_status="invalid_capture"
                    ),
                    response_bytes=None,
                    isolation=isolation_evidence,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )
            observed_capture = capture
            observed_channels = True

            if not capture.succeeded:
                return _finish(
                    terminal_status="failed",
                    failure_kind=ExecutionFailureKind.PROCESS_FAILED,
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=capture,
                    response_bytes=None,
                    isolation=isolation_evidence,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )

            try:
                response_bytes = response_extractor(capture)
            except Exception:
                return _finish(
                    terminal_status="failed",
                    failure_kind=(
                        ExecutionFailureKind.RESPONSE_EXTRACTION_FAILED
                    ),
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=capture,
                    response_bytes=None,
                    isolation=isolation_evidence,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )
            if response_bytes is not None and not isinstance(
                response_bytes, bytes
            ):
                return _finish(
                    terminal_status="failed",
                    failure_kind=(
                        ExecutionFailureKind.RESPONSE_EXTRACTION_FAILED
                    ),
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=capture,
                    response_bytes=None,
                    isolation=isolation_evidence,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )
            if response_bytes is None:
                return _finish(
                    terminal_status="failed",
                    failure_kind=ExecutionFailureKind.RESPONSE_UNAVAILABLE,
                    started_at=started_at,
                    started_mono=started_mono,
                    invocation_occurred=True,
                    capture=capture,
                    response_bytes=None,
                    isolation=isolation_evidence,
                    timestamp=timestamp_fn,
                    monotonic=monotonic_fn,
                )

            return _finish(
                terminal_status="completed",
                failure_kind=None,
                started_at=started_at,
                started_mono=started_mono,
                invocation_occurred=True,
                capture=capture,
                response_bytes=response_bytes,
                isolation=isolation_evidence,
                timestamp=timestamp_fn,
                monotonic=monotonic_fn,
            )
    except KeyboardInterrupt:
        return _finish(
            terminal_status="cancelled",
            failure_kind=ExecutionFailureKind.CANCELLED,
            started_at=started_at,
            started_mono=started_mono,
            invocation_occurred=invocation_occurred,
            capture=_partial_capture(
                transport_status="cancelled"
            ),
            response_bytes=None,
            isolation=isolation_evidence,
            process_channels_observed=False,
            timestamp=timestamp_fn,
            monotonic=monotonic_fn,
        )
    except Exception:
        return _finish(
            terminal_status="failed",
            failure_kind=ExecutionFailureKind.ISOLATION_FAILED,
            started_at=started_at,
            started_mono=started_mono,
            invocation_occurred=invocation_occurred,
            capture=(
                observed_capture
                if observed_capture is not None
                else _partial_capture(transport_status=None)
            ),
            response_bytes=None,
            isolation=isolation_evidence,
            process_channels_observed=observed_channels,
            timestamp=timestamp_fn,
            monotonic=monotonic_fn,
        )


@contextmanager
def temporary_workdir_isolation(
    environment: Mapping[str, str],
    *,
    session_home_reused: bool | None,
    prefix: str = "arcgrav-runner-work-",
) -> Iterator[InvocationContext]:
    """Create one clean local work directory while retaining session-home truth."""

    if not isinstance(prefix, str) or not prefix:
        raise ValueError("prefix must be non-empty text")
    with tempfile.TemporaryDirectory(prefix=prefix) as workdir:
        yield InvocationContext(
            cwd=Path(workdir),
            environment=environment,
            isolation=ExecutionIsolation(
                fresh_process=True,
                fresh_workdir=True,
                prior_observation_context_reused=False,
                session_home_reused=session_home_reused,
            ),
        )
