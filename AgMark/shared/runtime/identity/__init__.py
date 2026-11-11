"""Canonical runtime identity for accepted benchmark execution."""

from .boundary import (
    EXECUTION_BOUNDARY_SCHEMA_ID,
    EXECUTION_BOUNDARY_SCHEMA_VERSION,
    AcceptedBoundaryIdentity,
    DuplicateExecutionBoundaryFingerprint,
    ExecutionBoundary,
    IdentityError,
    IdentityIntegrityError,
    IdentityRef,
    ProviderRuntimeIdentity,
    SecretIdentityInputError,
    ensure_unique_boundary_fingerprints,
)
from .canonical import (
    CANONICALIZATION,
    CanonicalizationError,
    canonical_json_bytes,
    canonical_sha256,
    sha256_bytes,
)

__all__ = [
    "CANONICALIZATION",
    "EXECUTION_BOUNDARY_SCHEMA_ID",
    "EXECUTION_BOUNDARY_SCHEMA_VERSION",
    "AcceptedBoundaryIdentity",
    "CanonicalizationError",
    "DuplicateExecutionBoundaryFingerprint",
    "ExecutionBoundary",
    "IdentityError",
    "IdentityIntegrityError",
    "IdentityRef",
    "ProviderRuntimeIdentity",
    "SecretIdentityInputError",
    "canonical_json_bytes",
    "canonical_sha256",
    "ensure_unique_boundary_fingerprints",
    "sha256_bytes",
]
