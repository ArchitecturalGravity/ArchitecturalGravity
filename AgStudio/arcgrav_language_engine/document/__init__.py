"""Canonical, Qt-free structural view of conservative recognition."""

from .model import (
    DocumentFact, ParsedDocument, RelationshipState, SourcePoint, SourceRange,
    parse_document,
)

__all__ = [
    "DocumentFact", "ParsedDocument", "RelationshipState", "SourcePoint",
    "SourceRange", "parse_document",
]
