"""Source-ordered identity under the author's clarified symbol contract.

Explicit symbol bodies and AS outputs establish identity.
Only AS introduces new identities inside a body; those aliases export after
creation. Later occurrences retain identity, without inferring read vs mutation.
No external values, imports, property values or operations are evaluated.
Local member paths track only explicit definitions and exposure.
"""
from dataclasses import dataclass, replace

from ..document import ParsedDocument
from ..recognition import SourceSpan
from ..symbol_syntax import SYMBOL_NAME
from .syntax import SyntaxTree
from .members import MemberOccurrence, resolve_members


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    span: SourceSpan
    kind: str
    node: int
    body: int | None = None


@dataclass(frozen=True, slots=True)
class Resolution:
    reference: Symbol
    candidates: tuple[SourceSpan, ...]
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class Binding:
    marker: SourceSpan
    owner: SourceSpan
    children: tuple[int, ...]
    status: str


@dataclass(frozen=True, slots=True)
class Semantics:
    symbols: tuple[Symbol, ...]
    resolutions: tuple[Resolution, ...]
    bindings: tuple[Binding, ...]
    members: tuple[MemberOccurrence, ...] = ()


def symbol_bodies(tree: SyntaxTree) -> tuple[int | None, ...]:
    """Enclosing bodies from canonical ownership/containment, not a text scan.

    Same-indent section members belong to their section. A plain root section
    starts a new context; ordinary indentation beneath a non-symbol does not
    manufacture a symbol scope. A node's own symbol token is outside its body;
    following scalar tokens are inside (handled per occurrence by resolve).
    """
    owners: list[int | None] = []
    for node in tree.nodes:
        owner = None
        for link in (node.parent, node.section):
            if link is not None and 0 <= link < node.id:
                candidate = link if tree.nodes[link].symbol_body_span is not None else owners[link]
                if candidate is not None:
                    owner = candidate
        owners.append(owner)
    return tuple(owners)



def uncertain_symbol_bodies(tree: SyntaxTree) -> tuple[bool, ...]:
    """Colonless sole-symbol parents have unspecified symbolic body status."""
    uncertain = []
    for node in tree.nodes:
        uncertain.append(any(tree.nodes[link].possible_symbol_body_span is not None or uncertain[link]
                             for link in (node.parent, node.section) if link is not None and link < node.id))
    return tuple(uncertain)

def resolve(document: ParsedDocument, tree: SyntaxTree) -> Semantics:
    """Walk canonical occurrences once in source order; never look ahead."""
    symbols: list[Symbol] = []
    resolutions: list[Resolution] = []
    bindings: list[Binding] = []
    declared: dict[str, Symbol] = {}
    owners = symbol_bodies(tree)
    uncertain_bodies = uncertain_symbol_bodies(tree)
    ownership_uncertain = False
    last_body = None
    for node in tree.nodes:
        if (node.indent == 0 and not node.recovered
                and node.kind in ('section_header_candidate', 'section_scalar_candidate')):
            ownership_uncertain = False
        if node.recovered and node.indent is None and last_body is not None:
            ownership_uncertain = True
        if node.binding_marker_span is not None:
            supported = node.indent is not None and not node.recovered
            bindings.append(Binding(node.binding_marker_span, node.span, node.children,
                                    'physical_whole_line' if supported else 'uncertain'))
        for token in node.symbol_tokens:
            name = token.text[1:-1]
            body = owners[node.id]
            if node.symbol_body_span is not None and token.span.start > node.symbol_body_span.start:
                body = node.id
            # Exact names remain a bounded supported subset, not a full grammar.
            uncertain = (not SYMBOL_NAME.fullmatch(name)
                         or token.span in node.uncertain_declaration_spans
                         or node.recovered)
            prior = declared.get(name)
            is_alias = token.span == node.alias_target_span and not node.alias_ambiguous
            if uncertain:
                symbol = Symbol(name, token.span, 'uncertain', node.id, body)
            elif prior is not None:
                # Repeated declaration syntax is not an invocation. Preserve the
                # first identity without allowing a duplicate to count as a use.
                if is_alias or token.span == node.symbol_body_span:
                    declaration_kind = 'alias' if is_alias else 'anchor'
                    symbol = Symbol(name, token.span, 'duplicate_' + declaration_kind, node.id, body)
                    resolutions.append(Resolution(symbol, (prior.span,),
                        'duplicate_alias_instantiation' if is_alias else 'duplicate_symbol_instantiation',
                        'The name already has an identity; instantiation syntax cannot be used as a reference.'))
                else:
                    symbol = Symbol(name, token.span, 'reference', node.id, body)
                    resolutions.append(Resolution(symbol, (prior.span,),
                        'unique_prior_alias' if prior.kind == 'alias' else 'unique_prior_anchor',
                        'Same prior identity; reference versus mutation is intentionally not inferred.'))
            elif ownership_uncertain or (uncertain_bodies[node.id] and body is None and not is_alias):
                symbol = Symbol(name, token.span, 'uncertain', node.id, body)
            elif is_alias or (body is None and token.span == node.symbol_body_span):
                symbol = Symbol(name, token.span, 'alias' if is_alias else 'anchor', node.id, body)
                declared[name] = symbol
            elif body is not None and token.span == node.symbol_body_span:
                symbol = Symbol(name, token.span, 'reference', node.id, body)
                resolutions.append(Resolution(symbol, (), 'forbidden_nested_declaration',
                    'No prior local identity inside a symbol body; only AS may introduce one here. '
                    'External-symbol and property identity remain unresolved.'))
            else:
                symbol = Symbol(name, token.span, 'reference', node.id, body)
                resolutions.append(Resolution(symbol, (), 'unresolved', 'No prior explicit definition.'))
            symbols.append(symbol)
        if not node.recovered:
            last_body = node.id if node.symbol_body_span is not None else owners[node.id]
    uncertain_names = {s.name for s in symbols if s.kind == 'uncertain'}
    final = []
    for resolution in resolutions:
        if resolution.status == 'unresolved':
            name = resolution.reference.name
            later = declared.get(name)
            if name in uncertain_names:
                resolution = Resolution(resolution.reference, (), 'uncertain_identity',
                                        'An uncertain occurrence may define this identity.')
            elif later is not None:
                resolution = Resolution(resolution.reference, (later.span,), 'forward_candidate',
                                        'The explicit definition occurs after this reference.')
            else:
                resolution = Resolution(resolution.reference, (), 'missing_local_anchor',
                                        'No explicit definition exists in this document.')
        final.append(resolution)
    result = Semantics(tuple(symbols), tuple(final), tuple(bindings))
    return replace(result, members=resolve_members(tree, result, document.source))
