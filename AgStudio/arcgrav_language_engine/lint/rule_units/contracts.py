"""Uniform, read-only input and callable contract for lint rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Literal, Protocol, TypeVar

from ...document import ParsedDocument
from ...recognition import SourceSpan
from ..semantics import Semantics
from ..syntax import Node, SyntaxTree


class RuleMetadata(Protocol):
    id: str
    required_evidence: tuple[str, ...]


class CandidateView(Protocol):
    rule_id: str
    node_id: int
    span: SourceSpan
    evidence: tuple[str, ...]


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Shared analysis and lazy, phase-isolated derived evidence.

    Evidence must be derived from authoritative document/tree/semantics inputs.
    The verification phase has a separate namespace from proposals: caching
    never allows proposed evidence to validate itself.
    """

    document: ParsedDocument
    tree: SyntaxTree
    semantics: Semantics | None
    _proposal_cache: dict[str, object] = field(default_factory=dict, repr=False, compare=False)
    _verification_cache: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    @property
    def source(self) -> str:
        return self.document.source

    def evidence(self, key: str, factory: Callable[[], T], *, verification: bool = False) -> T:
        cache = self._verification_cache if verification else self._proposal_cache
        if key not in cache:
            cache[key] = factory()
        return cache[key]  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class RuleProposal:
    span: SourceSpan
    node_id: int
    message: str
    evidence: tuple[str, ...]
    sequence: int | None = None


@dataclass(frozen=True, slots=True)
class RuleUnit:
    """One rule, one contract: metadata, dependencies, detection, verification."""

    definition: RuleMetadata
    requires: tuple[str, ...]
    detect: Callable[[RuleContext, Node | None], Iterable[RuleProposal]]
    verify: Callable[[RuleContext, CandidateView], tuple[str, ...]]
    scope: Literal["node", "document"] = "node"
    literal_policy: Literal["any", "only", "exclude"] = "any"
    order: int = 0
    batch_group: str | None = None

    @property
    def id(self) -> str:
        return self.definition.id
