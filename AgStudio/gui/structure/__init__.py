"""Canonical ParsedDocument projections for Outline."""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.document import ParsedDocument, RelationshipState, SourceRange


@dataclass(frozen=True, slots=True)
class OutlineEntry:
    fact_id: str
    kind: str
    source_range: SourceRange
    source_trust: str
    limitations: tuple[str, ...]
    containment: RelationshipState
    recovery_kind: str | None
    claim_class: str = "recognition"


def outline_entries(document: ParsedDocument) -> tuple[OutlineEntry, ...]:
    """Project only canonical structural facts; no UI inferred parent edges."""
    if not isinstance(document, ParsedDocument):
        raise TypeError("outline requires a ParsedDocument")
    return tuple(
        OutlineEntry(fact.id, fact.kind, fact.source_range, fact.source_trust,
                     fact.limitations, document.relationship(fact.id, "containment"),
                     fact.recovery.kind if fact.recovery else None)
        for fact in document.structural_facts
    )


__all__ = ["OutlineEntry", "outline_entries"]
