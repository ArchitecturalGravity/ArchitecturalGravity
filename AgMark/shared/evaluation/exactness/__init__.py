"""Shared exact byte and strict UTF-8 text comparison semantics."""

from .comparison import (
    COMPARISON_MODES,
    ExactComparisonEvidence,
    ExactComparisonOperand,
    ExactnessError,
    compare_bytes,
    compare_utf8_text,
)

__all__ = [
    "COMPARISON_MODES",
    "ExactComparisonEvidence",
    "ExactComparisonOperand",
    "ExactnessError",
    "compare_bytes",
    "compare_utf8_text",
]
