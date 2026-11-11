"""Conservative, GUI-independent Stage 01 source recognition."""

from .source import (
    RecognitionResult, SourceObservation, SourceOccurrence, SourceRecovery,
    SourceRegion, SourceSpan,
)
from .section_boundaries import recognize_source

__all__ = [
    "RecognitionResult", "SourceObservation", "SourceOccurrence", "SourceRecovery", "SourceRegion",
    "SourceSpan",
    "recognize_source",
]
