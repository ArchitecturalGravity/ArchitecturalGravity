"""Shared runner execution and evidence primitives."""

from .emission import (
    CanonicalObservationError,
    EXECUTION_CATEGORY_AVAILABILITY,
    EXECUTION_EVIDENCE_EXTENSION_KEY,
    EXECUTION_EVIDENCE_SCHEMA_ID,
    EXECUTION_EVIDENCE_SCHEMA_VERSION,
    PROCESS_CHANNEL_AVAILABILITY,
    TERMINAL_RUNNER_STATUSES,
    emit_terminal_observation,
    validate_execution_evidence,
    validate_retained_parity_observation,
)
from .orchestration import (
    ExecutionFailureKind,
    ExecutionIsolation,
    InvocationCancelled,
    InvocationCapture,
    InvocationContext,
    TerminalExecutionResult,
    execute_target,
    temporary_workdir_isolation,
)
from .target import SelectorValue, TargetCompositionDescriptor

__all__ = [
    "CanonicalObservationError",
    "EXECUTION_CATEGORY_AVAILABILITY",
    "EXECUTION_EVIDENCE_EXTENSION_KEY",
    "EXECUTION_EVIDENCE_SCHEMA_ID",
    "EXECUTION_EVIDENCE_SCHEMA_VERSION",
    "PROCESS_CHANNEL_AVAILABILITY",
    "TERMINAL_RUNNER_STATUSES",
    "ExecutionFailureKind",
    "ExecutionIsolation",
    "InvocationCancelled",
    "InvocationCapture",
    "InvocationContext",
    "SelectorValue",
    "TargetCompositionDescriptor",
    "TerminalExecutionResult",
    "emit_terminal_observation",
    "execute_target",
    "temporary_workdir_isolation",
    "validate_execution_evidence",
    "validate_retained_parity_observation",
]
