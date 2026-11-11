"""One disposable source-coordinate and fact model for structural consumers.

The model copies Stage 01 source observations into a shared coordinate space.
Its indexes say where candidate source facts occur; they do not establish
ArcGrav validity, hierarchy, ownership, identity, or reference targets.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from hashlib import sha256
from heapq import heappop, heappush
import json
from typing import Literal, Mapping
from types import MappingProxyType

from ..core import SourceSession
from ..recognition import RecognitionResult, SourceRecovery, SourceSpan, recognize_source


@dataclass(frozen=True, slots=True)
class SourcePoint:
    """Python-string offset and one-based physical line and code-point column."""

    offset: int
    line: int
    column: int

    def __post_init__(self) -> None:
        if (type(self.offset) is not int or type(self.line) is not int
                or type(self.column) is not int or self.offset < 0
                or self.line < 1 or self.column < 1):
            raise ValueError("source point requires a nonnegative offset and positive line/column")


@dataclass(frozen=True, slots=True)
class SourceRange:
    """Half-open source range with exact Stage 01 character offsets."""

    span: SourceSpan
    start: SourcePoint
    end: SourcePoint

    def __post_init__(self) -> None:
        if (not isinstance(self.span, SourceSpan)
                or not isinstance(self.start, SourcePoint)
                or not isinstance(self.end, SourcePoint)
                or self.start.offset != self.span.start
                or self.end.offset != self.span.end):
            raise ValueError("source range points must match its half-open span")


@dataclass(frozen=True, slots=True)
class DocumentFact:
    """One source observation or occurrence, without a semantic verdict."""

    id: str
    kind: str
    family: Literal["structure", "occurrence"]
    source_range: SourceRange
    syntax_id: str | None
    limitations: tuple[str, ...]
    source_trust: Literal["observed", "recovered_untrusted"]
    recovery: SourceRecovery | None
    claim_class: Literal["recognition"] = field(default="recognition", init=False)

    @property
    def span(self) -> SourceSpan:
        return self.source_range.span


@dataclass(frozen=True, slots=True)
class RelationshipState:
    """A distinct relationship slot; source proximity never fills its target."""

    kind: Literal["containment", "ownership", "identity"]
    status: Literal["supported", "absent", "untrusted"]
    source_fact_id: str
    target_fact_id: str | None
    limitations: tuple[str, ...]


_LITERAL_CONTENT = frozenset(("literal_content", "unterminated_literal_content"))


def _recovery_segments(
    recoveries: tuple[SourceRecovery, ...],
) -> tuple[tuple[int, ...], tuple[SourceRecovery | None, ...]]:
    """Index the first original recovery at every half-open interval boundary.

    Source order is not required: the heap prioritizes the original tuple
    index, preserving first-match behavior for overlapping custom inputs too.
    Each recovery enters and leaves the heap at most once. Construction costs
    O(R log R) time and O(R) space; the resulting point lookup is O(log R).
    """
    events = []
    for index, recovery in enumerate(recoveries):
        start, end = recovery.span.start, recovery.span.end
        if start < end:
            events.append((start, index, end))
            events.append((end, -1, end))
    events.sort()
    active: list[tuple[int, int]] = []
    starts: list[int] = []
    matches: list[SourceRecovery | None] = []
    cursor = 0
    while cursor < len(events):
        offset = events[cursor][0]
        while cursor < len(events) and events[cursor][0] == offset:
            _, index, end = events[cursor]
            if index >= 0:
                heappush(active, (index, end))
            cursor += 1
        while active and active[0][1] <= offset:
            heappop(active)
        match = recoveries[active[0][0]] if active else None
        if not matches or matches[-1] is not match:
            starts.append(offset)
            matches.append(match)
    return tuple(starts), tuple(matches)


@dataclass(frozen=True, slots=True, init=False)
class ParsedDocument:
    """Canonical derived model; only its SourceSession carries source authority."""

    recognition: RecognitionResult
    document_id: str
    line_starts: tuple[int, ...]
    structural_facts: tuple[DocumentFact, ...]
    occurrence_facts: tuple[DocumentFact, ...]
    recoveries: tuple[SourceRecovery, ...]
    _facts_by_id: Mapping[str, DocumentFact] = field(repr=False, compare=False)

    def __init__(self, recognition: RecognitionResult) -> None:
        if not isinstance(recognition, RecognitionResult):
            raise TypeError("ParsedDocument requires Stage 01 recognition")
        session = recognition.session
        identity = json.dumps(
            [session.source, session.arcgrav_version, session.profile,
             session.configuration_key],
            ensure_ascii=True, separators=(",", ":"),
        ).encode("ascii")
        document_id = sha256(identity).hexdigest()
        starts = tuple(region.span.start for region in recognition.regions)
        if not starts:
            starts = (0,)
        elif recognition.source.endswith(("\r", "\n", "\v", "\f", "\x1c", "\x1d",
                                          "\x1e", "\x85", "\u2028", "\u2029")):
            starts += (len(recognition.source),)

        def point(offset: int) -> SourcePoint:
            line_index = bisect_right(starts, offset) - 1
            return SourcePoint(offset, line_index + 1, offset - starts[line_index] + 1)

        def fact_range(span: SourceSpan) -> SourceRange:
            return SourceRange(span, point(span.start), point(span.end))

        recovery_starts, recovery_matches = _recovery_segments(recognition.recoveries)

        def matching_recovery(span: SourceSpan) -> SourceRecovery | None:
            index = bisect_right(recovery_starts, span.start) - 1
            return recovery_matches[index] if index >= 0 else None

        structural = []
        for index, observation in enumerate(recognition.observations):
            if observation.kind == "unclassified" or observation.kind in _LITERAL_CONTENT:
                continue
            recovery = matching_recovery(observation.span)
            structural.append(DocumentFact(
                f"s:{index}", observation.kind, "structure",
                fact_range(observation.span), observation.syntax_id,
                observation.limitations,
                "recovered_untrusted" if recovery else "observed", recovery,
            ))
        occurrences = []
        for index, occurrence in enumerate(recognition.occurrences):
            recovery = matching_recovery(occurrence.span)
            occurrences.append(DocumentFact(
                f"o:{index}", occurrence.kind, "occurrence",
                fact_range(occurrence.span), occurrence.syntax_id,
                occurrence.limitations,
                "recovered_untrusted" if recovery else "observed", recovery,
            ))
        object.__setattr__(self, "recognition", recognition)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "line_starts", starts)
        object.__setattr__(self, "structural_facts", tuple(structural))
        object.__setattr__(self, "occurrence_facts", tuple(occurrences))
        object.__setattr__(self, "recoveries", recognition.recoveries)
        object.__setattr__(self, "_facts_by_id", MappingProxyType({f.id: f for f in structural + occurrences}))

    @property
    def session(self) -> SourceSession:
        return self.recognition.session

    @property
    def source(self) -> str:
        return self.session.source

    def position(self, offset: int) -> SourcePoint:
        """Map an exact code-point offset, including EOF, to a physical point."""
        if type(offset) is not int or not 0 <= offset <= len(self.source):
            raise ValueError("offset must be inside the original source")
        line_index = bisect_right(self.line_starts, offset) - 1
        return SourcePoint(offset, line_index + 1,
                           offset - self.line_starts[line_index] + 1)

    def source_range(self, span: SourceSpan) -> SourceRange:
        if not isinstance(span, SourceSpan) or span.end > len(self.source):
            raise ValueError("range must be within original source")
        return SourceRange(span, self.position(span.start), self.position(span.end))

    def facts(self, family: Literal["structure", "occurrence"] | None = None,
              kind: str | None = None) -> tuple[DocumentFact, ...]:
        """Traverse source facts in stable family and source order."""
        if family not in (None, "structure", "occurrence"):
            raise ValueError("unknown fact family")
        selected = (self.structural_facts if family == "structure"
                    else self.occurrence_facts if family == "occurrence"
                    else self.structural_facts + self.occurrence_facts)
        return tuple(fact for fact in selected if kind is None or fact.kind == kind)

    @property
    def structural_index(self) -> dict[str, tuple[DocumentFact, ...]]:
        return {kind: self.facts("structure", kind)
                for kind in sorted({fact.kind for fact in self.structural_facts})}

    @property
    def occurrence_index(self) -> dict[str, tuple[DocumentFact, ...]]:
        return {kind: self.facts("occurrence", kind)
                for kind in sorted({fact.kind for fact in self.occurrence_facts})}

    def at(self, offset: int) -> tuple[DocumentFact, ...]:
        """Find source facts covering a character; EOF contains no fact."""
        self.position(offset)
        if offset == len(self.source):
            return ()
        return tuple(fact for fact in self.facts()
                     if fact.span.start <= offset < fact.span.end)

    def fact(self, fact_id: str) -> DocumentFact | None:
        """Constant-time immutable canonical fact lookup for language services."""
        return self._facts_by_id.get(fact_id)

    def relationship(
        self, fact_id: str,
        kind: Literal["containment", "ownership", "identity"],
    ) -> RelationshipState:
        """Expose an unresolved relationship without fabricating an edge."""
        if kind not in ("containment", "ownership", "identity"):
            raise ValueError("unknown relationship kind")
        fact = self._facts_by_id.get(fact_id)
        if fact is None:
            raise KeyError(fact_id)
        return RelationshipState(kind, "untrusted", fact.id, None,
                                 fact.limitations)


def parse_document(session: SourceSession) -> ParsedDocument:
    """Rebuild one canonical model from exact source and detached context."""
    if not isinstance(session, SourceSession):
        raise TypeError("parse_document requires a SourceSession")
    return ParsedDocument(recognize_source(session))
