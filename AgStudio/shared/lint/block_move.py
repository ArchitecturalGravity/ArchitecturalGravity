"""Conservative, lossless moves of canonical source blocks, independent of Qt.

This is an editor operation, not another language interpretation. A candidate
is a permutation of exact source slices; the existing parser and resolver must
then reproduce every original structural and semantic fact at its new offset.
Unsupported moves fail closed without repairing source or changing semantics.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, replace
from types import MappingProxyType

from ..core import LanguageCore
from ..graph.adapter import whole_block_owners
from ..recognition import SourceSpan
from .semantics import resolve
from .syntax import parse


@dataclass(frozen=True, slots=True)
class SourceBlock:
    owner: int
    start: int
    end: int
    scope_start: int
    scope_end: int

    @property
    def span(self) -> SourceSpan:
        return SourceSpan(self.start, self.end)


@dataclass(frozen=True, slots=True)
class SourceOffsetMap:
    """Map original character offsets through a single exact cut-and-insert.

    Boundary offsets use the character on their right; EOF remains EOF. Use
    ``span`` for a half-open source span, whose end belongs to its last character.
    """
    old_start: int
    old_end: int
    destination: int
    source_length: int

    @property
    def new_start(self) -> int:
        if self.old_start <= self.destination <= self.old_end:
            return self.old_start
        return (self.destination if self.destination < self.old_start else
                self.destination - (self.old_end - self.old_start))

    def __call__(self, offset: int) -> int:
        if type(offset) is not int or not 0 <= offset <= self.source_length:
            raise ValueError('offset must be within the original source')
        start, end, destination = self.old_start, self.old_end, self.destination
        if start <= destination <= end or offset == self.source_length:
            return offset
        if start <= offset < end:
            return self.new_start + offset - start
        if destination < start and destination <= offset < start:
            return offset + end - start
        if destination > end and end <= offset < destination:
            return offset - (end - start)
        return offset

    def span(self, span: SourceSpan) -> SourceSpan:
        if span.start == span.end:
            return SourceSpan(self(span.start), self(span.start))
        start, end = self(span.start), self(span.end - 1) + 1
        if end - start != span.end - span.start:
            raise ValueError('source span was split by the move')
        # Endpoints alone can hide a permutation wholly inside a large span.
        for boundary in (self.old_start, self.old_end, self.destination):
            if (span.start < boundary < span.end
                    and self(boundary) != start + boundary - span.start):
                raise ValueError('source span was split by the move')
        return SourceSpan(start, end)


@dataclass(frozen=True, slots=True)
class BlockMovePlan:
    source: str
    old_start: int
    old_end: int
    destination: int
    new_start: int
    new_end: int
    offset_map: SourceOffsetMap


def _inclusive_ends(tree):
    ends = {node.id: node.span.end for node in tree.nodes}
    for node in reversed(tree.nodes):
        for link in (node.parent, node.section):
            if link is not None and link < node.id:
                ends[link] = max(ends[link], ends[node.id])
    return ends


def _scope_key(node):
    return node.parent, node.section, node.indent


class BlockMoveModel:
    """Immutable source snapshot with candidate gaps and validated move plans.

    ``blocks`` uses the same whole-block owner IDs as the map. Nested contexts
    travel with their parent when that parent is selected. A trailing run of
    blank physical lines belongs to the preceding block; leading blank lines
    and a BOM-bearing first line stay at their original position.

    ``slots(owner)`` includes same-scope syntactic gaps regardless of reference
    dependencies. ``plan`` returns None for illegal/unsupported placement, or a
    complete proposed source. Neither method edits the document. The caller
    must verify its current source still equals ``source`` before applying it.
    """

    def __init__(self, document, tree, semantics, owners=None):
        self.source = document.source
        self.document = document
        self.tree = tree
        self.semantics = semantics
        self.owners = MappingProxyType(dict(
            whole_block_owners(tree, semantics) if owners is None else owners))
        self._slot_cache = {}
        self._nodes = {node.id: node for node in tree.nodes}
        self._ends = _inclusive_ends(tree)
        self._valid_snapshot = self._exact_snapshot()
        blocks = {}
        if self._valid_snapshot:
            self._extend_blank_separators()
            starts = tuple(node.span.start for node in tree.nodes)
            recovery_counts = [0]
            for node in tree.nodes:
                recovery_counts.append(recovery_counts[-1] + bool(node.recovered))
            for node in tree.nodes:
                if self.owners.get(node.id) != node.id or not self._supported(node):
                    continue
                end = self._ends[node.id]
                stop = bisect_left(starts, end)
                if recovery_counts[stop] != recovery_counts[node.id]:
                    continue
                scope_links = [self._nodes[link] for link in (node.parent, node.section)
                               if link is not None]
                scope_start = max((link.span.end for link in scope_links), default=0)
                scope_end = min((self._ends[link.id] for link in scope_links),
                                default=len(self.source))
                if self.source.startswith('\ufeff'):
                    # Recognition does not presently treat a BOM transparently.
                    # Pin its whole first line; never move it into the file body.
                    scope_start = max(scope_start, tree.nodes[0].span.end)
                if scope_start <= node.span.start < end <= scope_end:
                    blocks[node.id] = SourceBlock(node.id, node.span.start, end,
                                                  scope_start, scope_end)
        self.blocks = MappingProxyType(blocks)

    def _exact_snapshot(self):
        cursor = 0
        for node in self.tree.nodes:
            if node.span.start != cursor or node.span.end <= cursor:
                return False
            cursor = node.span.end
        if cursor != len(self.source):
            return False
        cursor = 0
        for token in self.tree.tokens:
            if (token.span.start != cursor or token.span.end <= cursor
                    or token.text != token.span.extract(self.source)):
                return False
            cursor = token.span.end
        return cursor == len(self.source)

    def _extend_blank_separators(self):
        # Compute blank runs once, avoiding a scan per block in blank-heavy files.
        blank_ends = {}
        for node in reversed(self.tree.nodes):
            if not node.span.extract(self.source).strip():
                blank_ends[node.span.start] = blank_ends.get(node.span.end, node.span.end)
        self._ends = {ident: blank_ends.get(end, end) for ident, end in self._ends.items()}

    def _supported(self, node):
        return (node.indent is not None and not node.recovered
                and node.kind not in ('literal_content', 'literal_close',
                                      'unterminated_literal_content', 'unterminated_literal_open')
                and bool(node.span.extract(self.source).strip())
                and not (node.span.start == 0 and self.source.startswith('\ufeff')))

    def slots(self, owner: int) -> tuple[int, ...]:
        """Original-source insertion gaps; semantic legality is checked by plan."""
        block = self.blocks.get(owner)
        if block is None:
            return ()
        if owner not in self._slot_cache:
            selected = self._nodes[owner]
            gaps = {block.start, block.end}
            for node in self.tree.nodes:
                if self._supported(node) and _scope_key(node) == _scope_key(selected):
                    gaps.update((node.span.start, self._ends[node.id]))
            self._slot_cache[owner] = tuple(sorted(
                offset for offset in gaps
                if block.scope_start <= offset <= block.scope_end
                and not block.start < offset < block.end))
        return self._slot_cache[owner]

    def plan(self, owner: int, destination: int) -> BlockMovePlan | None:
        """Validate a same-scope exact move, preserving every canonical identity."""
        block = self.blocks.get(owner)
        if (block is None or type(destination) is not int
                or destination not in self.slots(owner)):
            return None
        start, end = block.start, block.end
        mapping = SourceOffsetMap(start, end, destination, len(self.source))
        if destination in (start, end):
            source = self.source
        elif destination < start:
            source = (self.source[:destination] + self.source[start:end]
                      + self.source[destination:start] + self.source[end:])
        else:
            source = (self.source[:start] + self.source[end:destination]
                      + self.source[start:end] + self.source[destination:])
        if destination not in (start, end) and not self._preserves_analysis(source, mapping):
            return None
        return BlockMovePlan(source, start, end, destination, mapping.new_start,
                             mapping.new_start + end - start, mapping)

    def _preserves_analysis(self, source, mapping):
        # Fast rejection of the common invalid drag, using the complete
        # resolver records (not the deliberately smaller display-arrow graph).
        for resolution in self.semantics.resolutions:
            if len(resolution.candidates) != 1:
                continue
            target = mapping(resolution.candidates[0].start)
            reference = mapping(resolution.reference.span.start)
            if resolution.status in ('unique_prior_anchor', 'unique_prior_alias'):
                if target >= reference:
                    return False
            elif resolution.status == 'forward_candidate' and target <= reference:
                return False
        document = LanguageCore.parse_document(self.document.session.with_source(source))
        tree = parse(document)
        semantics = resolve(document, tree)
        if len(tree.nodes) != len(self.tree.nodes):
            return False
        by_span = {node.span: node for node in tree.nodes}
        remap_span = mapping.span
        try:
            node_ids = {node.id: by_span[remap_span(node.span)].id for node in self.tree.nodes}

            def node_id(ident):
                return None if ident is None else node_ids[ident]

            def span(value):
                return None if value is None else remap_span(value)

            def token(value):
                return replace(value, span=remap_span(value.span))

            for old in self.tree.nodes:
                new = tree.nodes[node_ids[old.id]]
                expected = replace(old, id=node_ids[old.id], span=remap_span(old.span),
                    parent=node_id(old.parent), section=node_id(old.section),
                    children=tuple(sorted(node_ids[child] for child in old.children)),
                    prefix_tokens=tuple(token(t) for t in old.prefix_tokens),
                    symbol_tokens=tuple(token(t) for t in old.symbol_tokens),
                    alias_marker_span=span(old.alias_marker_span),
                    alias_target_span=span(old.alias_target_span),
                    binding_marker_span=span(old.binding_marker_span),
                    quoted_spans=tuple(map(remap_span, old.quoted_spans)),
                    anchor_span=span(old.anchor_span),
                    symbol_body_span=span(old.symbol_body_span),
                    possible_symbol_body_span=span(old.possible_symbol_body_span),
                    uncertain_declaration_spans=tuple(map(remap_span, old.uncertain_declaration_spans)),
                    tokens=tuple(token(t) for t in old.tokens))
                if expected != replace(new, children=tuple(sorted(new.children))):
                    return False
            if (Counter(map(token, self.tree.tokens)) != Counter(tree.tokens)
                    or Counter(map(remap_span, self.tree.recovery_spans)) != Counter(tree.recovery_spans)):
                return False

            def symbol(value):
                return replace(value, span=remap_span(value.span), node=node_ids[value.node],
                               body=node_id(value.body))

            expected_symbols = map(symbol, self.semantics.symbols)
            expected_resolutions = (replace(r, reference=symbol(r.reference),
                                           candidates=tuple(map(remap_span, r.candidates)))
                                    for r in self.semantics.resolutions)
            expected_bindings = (replace(b, marker=remap_span(b.marker), owner=remap_span(b.owner),
                                         children=tuple(sorted(node_ids[c] for c in b.children)))
                                 for b in self.semantics.bindings)
            expected_members = (replace(m, owner=span(m.owner), span=remap_span(m.span),
                                        node=node_ids[m.node], definition=span(m.definition))
                                for m in self.semantics.members)
            return (Counter(expected_symbols) == Counter(semantics.symbols)
                    and Counter(expected_resolutions) == Counter(semantics.resolutions)
                    and Counter(expected_bindings) == Counter(
                        replace(b, children=tuple(sorted(b.children))) for b in semantics.bindings)
                    and Counter(expected_members) == Counter(semantics.members))
        except (KeyError, ValueError):
            # A split fact, changed line boundary, or missing counterpart is
            # unsupported, including unsafe moves across unterminated EOF text.
            return False
