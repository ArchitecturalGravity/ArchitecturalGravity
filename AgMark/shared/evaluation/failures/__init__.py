"""Shared failure taxonomy and deterministic precedence resolution."""

from .resolver import (
    AUTHORITY_LAYERS,
    CANONICAL_CLASS_PRECEDENCE,
    FAILURE_TAXONOMY_CONTRACT_ID,
    FAILURE_TAXONOMY_CONTRACT_VERSION,
    RUNNER_STATUS_FAILURE_CLASS,
    CandidateValidationIssue,
    ContractIdentity,
    ExtensionFailureClassRegistration,
    FailureCandidate,
    FailureResolution,
    FailureValidationError,
    MetricPrecedenceOverride,
    resolve_failures,
    resolve_metric_failures,
    runner_terminal_failure_class,
)

__all__ = [
    "AUTHORITY_LAYERS",
    "CANONICAL_CLASS_PRECEDENCE",
    "FAILURE_TAXONOMY_CONTRACT_ID",
    "FAILURE_TAXONOMY_CONTRACT_VERSION",
    "RUNNER_STATUS_FAILURE_CLASS",
    "CandidateValidationIssue",
    "ContractIdentity",
    "ExtensionFailureClassRegistration",
    "FailureCandidate",
    "FailureResolution",
    "FailureValidationError",
    "MetricPrecedenceOverride",
    "resolve_failures",
    "resolve_metric_failures",
    "runner_terminal_failure_class",
]
