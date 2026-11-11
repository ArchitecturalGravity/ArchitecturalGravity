"""Benchmark-neutral evaluation primitives."""

from .scoring import (
    METRIC_REGISTRATION_SCHEMA,
    SCORER_INVOCATION_CONTRACT_ID,
    SCORER_INVOCATION_CONTRACT_VERSION,
    SCORE_ARTIFACT_SCHEMA,
    IdentityRef,
    RegisteredScorerAuthority,
    ScorerCall,
    ScoringContext,
    ScoringEvidenceInput,
    ScoringOutcome,
    invoke_registered_scorer,
    validate_registered_scorer,
    validate_registered_scorer_outcome,
    validate_score_artifact,
)

__all__ = [
    "METRIC_REGISTRATION_SCHEMA",
    "SCORER_INVOCATION_CONTRACT_ID",
    "SCORER_INVOCATION_CONTRACT_VERSION",
    "SCORE_ARTIFACT_SCHEMA",
    "IdentityRef",
    "RegisteredScorerAuthority",
    "ScorerCall",
    "ScoringContext",
    "ScoringEvidenceInput",
    "ScoringOutcome",
    "invoke_registered_scorer",
    "validate_registered_scorer",
    "validate_registered_scorer_outcome",
    "validate_score_artifact",
]
