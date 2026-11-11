"""Tree-backed IDE projection of the canonical coordinate document.

All consumers share the same parser and semantic analysis, including
Outline, Correlations, diagnostics navigation and highlighting.
"""
from bisect import bisect_left
from dataclasses import FrozenInstanceError, fields, replace
from types import MappingProxyType

from ..document.model import ParsedDocument, DocumentFact, RelationshipState


class CanonicalDocument(ParsedDocument):
    __slots__ = ('syntax', 'semantics', '_relationships')

    def __setattr__(self, name, value):
        # Frozen dataclass parents do not reliably cover subclass-only slots.
        # Construction/restoration deliberately use object.__setattr__ instead.
        raise FrozenInstanceError(f"cannot assign to field {name!r}")

    def __delattr__(self, name):
        raise FrozenInstanceError(f"cannot delete field {name!r}")

    def __init__(self, document, tree, semantics):
        for field in fields(ParsedDocument):
            object.__setattr__(self, field.name, getattr(document, field.name))
        object.__setattr__(self, 'syntax', tree)
        object.__setattr__(self, 'semantics', semantics)
        structures = list(document.structural_facts)
        by_span = {f.span: f for f in structures}
        node_facts = {}
        for node in tree.nodes:
            fact = by_span.get(node.span)
            if fact is None and (node.binding_marker_span is not None or node.alias_target_span is not None):
                fact = DocumentFact(f'n:{node.id}', 'expression', 'structure',
                                    document.source_range(node.span), None, (),
                                    'recovered_untrusted' if node.recovered else 'observed', None)
                structures.append(fact)
            if fact is not None:
                node_facts[node.id] = fact
        shields = sorted((t.span for t in tree.tokens if t.kind in ('literal', 'quoted_scalar')),
                         key=lambda span: span.start)
        shield_starts = []
        shield_max_ends = []
        maximum_end = 0
        for shield in shields:
            shield_starts.append(shield.start)
            maximum_end = max(maximum_end, shield.end)
            shield_max_ends.append(maximum_end)

        def shielded(span):
            # Keep the exact strict overlap predicate, including zero-width
            # spans. Prefix maxima also handle nested or unordered shields.
            stop = bisect_left(shield_starts, span.end)
            return stop > 0 and span.start < shield_max_ends[stop - 1]

        active_spans = {t.span for t in tree.tokens if t.kind not in ('literal', 'quoted_scalar', 'text', 'whitespace', 'newline')}
        occurrences = tuple(f for f in document.occurrence_facts
                            if (f.kind != 'symbol_candidate' or f.span in active_spans)
                            and not shielded(f.span))
        recovery_spans = set(tree.recovery_spans)
        object.__setattr__(self, 'recoveries', tuple(r for r in document.recoveries if r.span in recovery_spans))
        facts = tuple(structures) + occurrences
        relations = {}
        for node in tree.nodes:
            fact = node_facts.get(node.id)
            if fact is None:
                continue
            parent = node_facts.get(node.parent)
            owner = node_facts.get(node.section)
            if parent is not None and not node.recovered:
                relations[fact.id, 'containment'] = parent.id
                if owner is None:
                    relations[fact.id, 'ownership'] = parent.id
            if owner is not None and not node.recovered:
                relations[fact.id, 'ownership'] = owner.id
        facts_by_span = {f.span: f for f in occurrences}
        for resolution in semantics.resolutions:
            if resolution.status not in ('unique_prior_anchor', 'unique_prior_alias') or len(resolution.candidates) != 1:
                continue
            source = facts_by_span.get(resolution.reference.span)
            target = facts_by_span.get(resolution.candidates[0])
            if source is not None and target is not None:
                relations[source.id, 'identity'] = target.id
        object.__setattr__(self, 'structural_facts', tuple(sorted(structures, key=lambda f: f.span.start)))
        object.__setattr__(self, 'occurrence_facts', occurrences)
        object.__setattr__(self, '_facts_by_id', MappingProxyType({f.id: f for f in facts}))
        object.__setattr__(self, '_relationships', MappingProxyType(relations))

    def relationship(self, fact_id, kind):
        if kind not in ('containment', 'ownership', 'identity'):
            raise ValueError('unknown relationship kind')
        fact = self.fact(fact_id)
        if fact is None:
            raise KeyError(fact_id)
        target = self._relationships.get((fact_id, kind))
        return RelationshipState(kind, 'supported' if target is not None else 'untrusted',
                                 fact_id, target, fact.limitations)
