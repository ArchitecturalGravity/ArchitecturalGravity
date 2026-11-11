"""Global backtick correlation and independently owned dotted member access."""
from dataclasses import dataclass
import re

from ..recognition import SourceSpan

MEMBER_MESSAGES = {
    'AG-MEMBER-DUPLICATE': 'This backticked name defines multiple distinct members; unqualified references may be ambiguous.',
    'AG-MEMBER-ORPHAN': 'This backticked member is defined but never used.',
    'AG-MEMBER-AMBIGUOUS': 'This backticked name matches multiple prior definitions. Use dotted symbol access to identify the intended member.',
    'AG-MEMBER-UNDEFINED': 'This backticked member is referenced but has no definition.',
    'AG-MEMBER-NOT-EXPOSED': 'The referenced element has not been exposed or is missing.',
}
MEMBER_INFO_MESSAGES = {
    'AG-MEMBER-NESTED-DECLARATION': 'Avoid declaring nested backticked children; keep members near the surface to reduce reference-resolution errors; an LLM does not guarantee deterministic state tracking.',
    'AG-MEMBER-NESTED-INVOCATION': 'Avoid invoking nested backticked children; keep members near the surface to reduce reference-resolution errors; an LLM does not guarantee deterministic state tracking.',
}
MEMBER_FINDING_MESSAGES = {**MEMBER_MESSAGES, **MEMBER_INFO_MESSAGES}
_TRIVIA = {'indentation', 'whitespace', 'newline'}
_DOT_CHAIN = re.compile(r'(?:\.[A-Za-z_][A-Za-z0-9_]*)+')


@dataclass(frozen=True, slots=True)
class MemberOccurrence:
    owner: SourceSpan | None
    path: tuple[str, ...]
    span: SourceSpan
    node: int
    kind: str
    definition: SourceSpan | None = None


def _resolve_bare_reference(name, span, node_id, owner, definitions_by_name, invoked):
    """Correlate an unqualified backtick by its exact prior name, globally.

    Neither the enclosing owner/path nor inline symbolic operands participate
    in selection. A second distinct prior declaration makes the name ambiguous.
    """
    candidates = definitions_by_name.get(name, ())
    if not candidates:
        # Without any known member or symbolic context, the text may simply
        # be ordinary prose. Once declarations exist, an unowned bare name is
        # still eligible for a document-wide undefined-member finding.
        if owner is None and not definitions_by_name:
            return None
        return MemberOccurrence(owner, (name,), span, node_id, 'unresolved_reference')
    if len(candidates) > 1:
        first = candidates[0]
        return MemberOccurrence(first.owner, first.path, span, node_id, 'ambiguous')

    definition = candidates[0]
    key = (definition.owner, definition.path)
    kind = 'reference' if key in invoked else 'invocation'
    invoked.add(key)
    return MemberOccurrence(definition.owner, definition.path, span, node_id,
                            kind, definition.span)


def _resolve_dotted_access(token, node, source, identity, declarations, invoked):
    """Validate every dotted segment against prior, explicitly declared paths.

    A same-named member elsewhere never exposes a path on this symbol.
    Successful segments count as uses, but use is not a prerequisite for exposure.
    """
    target = identity(token.span)
    if target is None:
        return ()
    match = _DOT_CHAIN.match(source[token.span.end:node.span.end])
    if match is None:
        return ()
    end = token.span.end + match.end()
    if end < node.span.end and (source[end].isalnum()
                                or source[end] in '_.[]-' or ord(source[end]) == 96):
        return ()
    full_span = SourceSpan(token.span.start, end)
    if any(q.start < full_span.end and full_span.start < q.end
           for q in node.quoted_spans):
        return ()

    result = []
    accessed = ()
    definition = None
    for segment in re.finditer(r'\.([A-Za-z_][A-Za-z0-9_]*)', match.group()):
        accessed += (segment.group(1),)
        key = (target, accessed)
        definition = declarations.get(key)
        span = SourceSpan(token.span.end + segment.start(1),
                          token.span.end + segment.end(1))
        if definition is None:
            result.append(MemberOccurrence(target, accessed, span, node.id,
                                           'unexposed_access'))
            return tuple(result)
        if key not in invoked:
            invoked.add(key)
            result.append(MemberOccurrence(target, accessed, span, node.id,
                                           'invocation', definition.span))
    result.append(MemberOccurrence(target, accessed, full_span, node.id,
                                   'access', definition.span))
    return tuple(result)


def resolve_members(tree, semantics, source):
    """Collect explicit declarations, resolve bare names and check dotted paths.

    Backtick references are document-wide, exact-name, source-ordered uses.
    Symbol ownership and nested paths are retained only to register definitions
    and validate explicit dotted access; neither constrains bare name matching.
    """
    from .semantics import symbol_bodies, uncertain_symbol_bodies

    bodies = symbol_bodies(tree)
    uncertain = uncertain_symbol_bodies(tree)
    symbols = {s.span: s for s in semantics.symbols}
    resolutions = {r.reference.span: r for r in semantics.resolutions}

    def identity(span):
        symbol = symbols.get(span)
        if symbol is None or symbol.kind == 'uncertain':
            return None
        if symbol.kind in ('anchor', 'alias'):
            return symbol.span
        resolution = resolutions.get(span)
        if resolution is not None and resolution.status in (
                'unique_prior_anchor', 'unique_prior_alias'):
            return resolution.candidates[0]
        return None

    # Definitions are indexed twice for separate consumers:
    # - by name, exclusively for global bare-backtick correlation
    # - by owner/path, exclusively for strict dotted access
    declarations = {}
    definitions_by_name = {}
    invoked = set()
    occurrences = []
    scopes = []
    defined_nodes = set()
    ownership_uncertain = False
    for node in tree.nodes:
        if (node.indent == 0 and not node.recovered
                and node.kind in ('section_header_candidate', 'section_scalar_candidate')):
            ownership_uncertain = False
        if node.recovered and node.indent is None:
            ownership_uncertain = True

        scope = None
        for link in (node.parent, node.section):
            if link is not None and link < node.id and scopes[link] is not None:
                scope = scopes[link]
        scopes.append(scope)
        if ('literal' in node.kind or node.recovered
                or ownership_uncertain or uncertain[node.id]):
            continue

        values = [t for t in node.tokens if t.kind not in _TRIVIA]
        list_definition = (len(node.prefix_tokens) == 1
                           and (node.prefix_tokens[0].text == '-'
                                or node.kind == 'ordered_list_candidate')
                           and len(values) > 1
                           and values[1].kind == 'backtick_scalar')
        body_id = node.id if node.symbol_body_span is not None else bodies[node.id]
        owner = (identity(tree.nodes[body_id].symbol_body_span)
                 if body_id is not None else None)
        parent_path = scope[1] if scope is not None and scope[0] == owner else ()

        # Preserve the syntax distinction between declarations and incidental
        # list-led operands. This is only used to register definitions.
        orphan_parent = (list_definition and node.parent is not None
                         and node.parent != body_id
                         and node.parent not in defined_nodes)
        operand = orphan_parent and len(values) == 2 and not node.children

        for token in node.tokens:
            if token.kind == 'backtick_scalar':
                name = token.text[1:-1]
                if (len(token.text) < 3 or not token.text.endswith(chr(96))
                        or any(c.isspace() or ord(c) == 96 or c == '\\'
                               for c in name)
                        or (token.span.start and source[token.span.start - 1] == '.')):
                    continue

                first_item = list_definition and token == values[1]
                if first_item and owner is not None and not orphan_parent:
                    path = parent_path + (name,)
                    key = (owner, path)
                    prior = declarations.get(key)
                    if prior is None:
                        occurrence = MemberOccurrence(owner, path, token.span, node.id,
                                                      'definition', token.span)
                        declarations[key] = occurrence
                        definitions_by_name.setdefault(name, []).append(occurrence)
                    else:
                        occurrence = MemberOccurrence(owner, path, token.span, node.id,
                                                      'redefinition', prior.span)
                    scopes[node.id] = key
                    defined_nodes.add(node.id)
                    occurrences.append(occurrence)
                    continue

                if first_item and orphan_parent and not operand:
                    if owner is not None:
                        occurrences.append(MemberOccurrence(
                            owner, parent_path + (name,), token.span, node.id,
                            'unsupported_declaration'))
                    continue
                if first_item and owner is None and len(values) > 2:
                    continue

                occurrence = _resolve_bare_reference(
                    name, token.span, node.id, owner, definitions_by_name, invoked)
                if occurrence is not None:
                    occurrences.append(occurrence)
            elif token.kind == 'symbol':
                occurrences.extend(_resolve_dotted_access(
                    token, node, source, identity, declarations, invoked))
    return tuple(occurrences)


def member_warning_spans(occurrences):
    """Compute independent warnings from declared identities and resolved uses."""
    result = set()
    definitions = {}
    definitions_by_name = {}
    invoked = set()
    unresolved = []
    for occurrence in occurrences:
        key = (occurrence.owner, occurrence.path)
        if occurrence.kind == 'definition':
            existing = definitions_by_name.setdefault(occurrence.path[-1], set())
            if existing and key not in existing:
                result.add(('AG-MEMBER-DUPLICATE', occurrence.node, occurrence.span))
            existing.add(key)
            definitions[key] = occurrence
        elif occurrence.kind in ('invocation', 'reference', 'access'):
            invoked.add(key)
        elif occurrence.kind == 'unresolved_reference':
            unresolved.append(occurrence)
        elif occurrence.kind == 'ambiguous':
            result.add(('AG-MEMBER-AMBIGUOUS', occurrence.node, occurrence.span))
        elif occurrence.kind == 'unexposed_access':
            result.add(('AG-MEMBER-NOT-EXPOSED', occurrence.node, occurrence.span))

    for occurrence in unresolved:
        # A later definition proves the name exists but cannot retroactively
        # turn an earlier bare use into an invocation.
        if occurrence.path[-1] not in definitions_by_name:
            result.add(('AG-MEMBER-UNDEFINED', occurrence.node, occurrence.span))
    for key, occurrence in definitions.items():
        if key not in invoked:
            result.add(('AG-MEMBER-ORPHAN', occurrence.node, occurrence.span))
    return frozenset(result)


def member_finding_spans(occurrences):
    """Keep nesting advice separate from warnings and exposure decisions."""
    result = set(member_warning_spans(occurrences))
    for occurrence in occurrences:
        if len(occurrence.path) <= 1:
            continue
        if occurrence.kind in ('definition', 'redefinition'):
            rule = 'AG-MEMBER-NESTED-DECLARATION'
        elif occurrence.kind == 'invocation':
            rule = 'AG-MEMBER-NESTED-INVOCATION'
        else:
            continue
        result.add((rule, occurrence.node, occurrence.span))
    return frozenset(result)
