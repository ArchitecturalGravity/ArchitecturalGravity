"""Fail-closed golden runtime admission and retained evidence."""

from .execution import (
    GOLDEN_EVIDENCE_EXTENSION,
    GOLDEN_EXECUTION_CONTRACT_ID,
    GOLDEN_EXECUTION_CONTRACT_VERSION,
    GOLDEN_OBSERVATION_SCHEMA_ID,
    GOLDEN_OBSERVATION_SCHEMA_VERSION,
    GoldenArtifactRequirement,
    GoldenCaseInput,
    GoldenDeclaration,
    GoldenExecutionError,
    GoldenExecutionResult,
    GoldenIntegrityError,
    GoldenRegistrationError,
    TransientEnvironmentBinding,
    execute_required_golden,
)

__all__ = [
    "GOLDEN_EVIDENCE_EXTENSION",
    "GOLDEN_EXECUTION_CONTRACT_ID",
    "GOLDEN_EXECUTION_CONTRACT_VERSION",
    "GOLDEN_OBSERVATION_SCHEMA_ID",
    "GOLDEN_OBSERVATION_SCHEMA_VERSION",
    "GoldenArtifactRequirement",
    "GoldenCaseInput",
    "GoldenDeclaration",
    "GoldenExecutionError",
    "GoldenExecutionResult",
    "GoldenIntegrityError",
    "GoldenRegistrationError",
    "TransientEnvironmentBinding",
    "execute_required_golden",
]
