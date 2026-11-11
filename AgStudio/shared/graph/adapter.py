"""Convert canonical parser/analyzer evidence to detached graph input.

Only this boundary knows about syntax nodes and semantic resolution records.
Heuristic relationships retain the exact-local-evidence policy. Semantic Triad
receives character footprints and supported identities, never invented numeric
reinforcement, suppression, or alias-transfer operators.
"""
from .core import (GraphSnapshot, SemanticFootprint, SemanticView, SemanticPosition, SemanticElement,
                   _check_cancelled, validate_options, normalize_graph_mode)


RESOLVED = frozenset(('unique_prior_anchor', 'unique_prior_alias'))


def _span_union(spans, *, cancelled=None):
    """Return sorted, non-overlapping half-open source intervals."""
    merged = []
    for start, end in sorted(set(spans)):
        _check_cancelled(cancelled)
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _alias_expression_span(node):
    """The parser binds AS to its local expression, not a preceding section.

    A section's label is explicitly excluded by syntax._metadata's source
    check. Otherwise retain the whole physical expression, including its
    structural prefix, whitespace and line ending. AS does not claim that
    following children or earlier lines are part of the derived context.
    """
    start = node.span.start
    if node.kind in ('section_header_candidate', 'section_scalar_candidate'):
        colon = next((token for token in node.tokens
                      if token.kind == 'section_colon'
                      and token.span.end <= node.alias_marker_span.start), None)
        if colon is not None:
            start = colon.span.end
    return start, node.span.end


def _inclusive_node_ends(tree, *, cancelled=None):
    """Extend nodes through canonical containment and section ownership."""
    ends = {node.id: node.span.end for node in tree.nodes}
    for node in reversed(tree.nodes):
        _check_cancelled(cancelled)
        for link in (node.parent, node.section):
            if link in ends and link < node.id:
                ends[link] = max(ends[link], ends[node.id])
    return ends


def _semantic_footprints(tree, semantics, declarations, inclusive_ends, *, cancelled=None):
    """Detach definition geometry, mentions, containment and exact dependencies.

    Each canonical declaration establishes one stable identity. Duplicate
    [Name]: or AS [Name] instantiations are invalid and do not extend that
    identity's definition, references, or containment. A valid body's
    inclusive span covers its physical/section descendants, including gaps.

    Mentions remain separate evidence even when they overlap a definition.
    Consumers union the channels before measuring linked text, then subtract
    child footprints to derive own text. No source is depleted by AS.
    """
    declaration_names = {span: declaration.name for span, declaration in declarations.items()}
    identities = dict(declaration_names)
    definitions = {name: [] for name in identities.values()}
    mentions = {name: [] for name in identities.values()}
    children = {name: set() for name in identities.values()}
    relationships = {name: set() for name in identities.values()}
    available = {}
    for declaration in declarations.values():
        _check_cancelled(cancelled)
        available[declaration.name] = min(available.get(declaration.name, declaration.span.end),
                                          declaration.span.end)
    references = []
    for resolution in semantics.resolutions:
        _check_cancelled(cancelled)
        if resolution.status not in RESOLVED or len(resolution.candidates) != 1:
            continue
        name = declaration_names.get(resolution.candidates[0])
        if name is None:
            continue
        reference = resolution.reference
        identities[reference.span] = name
        mentions[name].append((reference.span.start, reference.span.end))
        references.append((reference, name))

    bodies = {node.id: identities[node.symbol_body_span] for node in tree.nodes
              if not node.recovered and node.symbol_body_span in identities}
    enclosing = {}
    aliases = {}
    for node in tree.nodes:
        _check_cancelled(cancelled)
        # Match canonical symbol_bodies: section ownership takes priority over
        # an indentation parent when both specify an enclosing symbol body.
        owner = None
        for link in (node.parent, node.section):
            if link is not None and link < node.id:
                candidate = bodies.get(link, enclosing.get(link))
                if candidate is not None:
                    owner = candidate
        enclosing[node.id] = owner
        name = bodies.get(node.id)
        if name is not None:
            definitions[name].append((node.span.start, inclusive_ends[node.id]))
            if owner is not None and owner != name:
                children[owner].add(name)
                relationships[owner].add(f'Contains {name}')
        alias = identities.get(node.alias_target_span)
        if alias is not None and not node.recovered and not node.alias_ambiguous:
            start, end = _alias_expression_span(node)
            definitions[alias].append((start, end))
            aliases[node.id] = (alias, start, node.alias_target_span.start)
            alias_owner = name if name is not None else owner
            if alias_owner is not None and alias_owner != alias:
                children[alias_owner].add(alias)
                relationships[alias_owner].add(f'Contains {alias}')

    for reference, target in references:
        _check_cancelled(cancelled)
        owner = bodies.get(reference.body)
        if owner is None:
            owner = enclosing.get(reference.node)
        if owner is not None and owner != target:
            relationships[owner].add(f'Resolved use of {target}')
        alias = aliases.get(reference.node)
        if alias is not None:
            name, start, stop = alias
            if start <= reference.span.start and reference.span.end <= stop and target != name:
                relationships[name].add(f'AS source references {target}')

    footprints = []
    for name in definitions:
        _check_cancelled(cancelled)
        footprints.append(SemanticFootprint(
            object=name,
            definitions=_span_union(definitions[name], cancelled=cancelled),
            mentions=_span_union(mentions[name], cancelled=cancelled),
            children=tuple(sorted(children[name])),
            relationships=tuple(sorted(relationships[name])),
            available_from=available[name],
        ))
    return tuple(footprints)


def _semantic_views(tree, semantics, declarations, inclusive_ends, *, cancelled=None):
    """Choose every node's display context automatically from parser evidence.

    Object segments retain declaration-source order, never influence ranking.
    Source positions preserve geometry and API context; automatic map values
    are evaluated at document end, independently of each node's location.
    Named bodies retain their inclusive end; ordinary unowned ST1/ST2 nodes
    retain the complete identity vector as a coarse presentation summary.
    """
    declaration_names = {span: declaration.name for span, declaration in declarations.items()}
    order = tuple(dict.fromkeys(declaration_names.values()))
    source_order = {name: index for index, name in enumerate(order)}
    identities = dict(declaration_names)
    references = {}
    for resolution in semantics.resolutions:
        _check_cancelled(cancelled)
        if resolution.status not in RESOLVED or len(resolution.candidates) != 1:
            continue
        name = declaration_names.get(resolution.candidates[0])
        if name is None:
            continue
        reference = resolution.reference
        identities[reference.span] = name
        references.setdefault(reference.node, []).append((name, reference.span.end))
    bodies = {node.id: identities[node.symbol_body_span] for node in tree.nodes
              if not node.recovered and node.symbol_body_span in identities}
    enclosing = {}
    result = []
    for node in tree.nodes:
        _check_cancelled(cancelled)
        owner = None
        for link in (node.parent, node.section):
            if link is not None and link < node.id:
                candidate = link if link in bodies else enclosing.get(link)
                if candidate is not None:
                    owner = candidate
        enclosing[node.id] = owner
        local = references.get(node.id, ()) if not node.recovered else ()
        alias = (identities.get(node.alias_target_span)
                 if not node.recovered and not node.alias_ambiguous else None)
        if node.id in bodies:
            objects = (bodies[node.id],)
            position = inclusive_ends[node.id]
            kind = 'named_block'
        elif alias is not None:
            names = {name for name, _ in local} | {alias}
            objects = tuple(sorted(names, key=source_order.__getitem__))
            position = node.alias_target_span.end
            kind = 'alias_use'
        elif local:
            names = {name for name, _ in local}
            objects = tuple(sorted(names, key=source_order.__getitem__))
            position = max(end for _, end in local)
            kind = 'reference_use'
        elif owner is not None and not node.recovered:
            objects = (bodies[owner],)
            position = inclusive_ends[owner]
            kind = 'named_context'
        else:
            objects = order
            position = node.span.end
            kind = 'all_objects'
        result.append(SemanticView(node.id, position, objects, kind))
    return tuple(result)


def _semantic_positions(tree, semantics, declarations, inclusive_ends, *, cancelled=None):
    """Keep each boundary and reference endpoint, including same-row uses.

    Geometry comes from canonical node boundaries before valid footprint
    unions merge adjacent representations. A duplicate instantiation does not
    add a resolved reference; distinct valid reference tokens retain positions.
    """
    identities = {span: declaration.name for span, declaration in declarations.items()}
    events = []
    for declaration in declarations.values():
        _check_cancelled(cancelled)
        events.append(SemanticPosition(declaration.span.end, (declaration.name,),
                                       'object_available', declaration.node))
    for resolution in semantics.resolutions:
        _check_cancelled(cancelled)
        if resolution.status not in RESOLVED or len(resolution.candidates) != 1:
            continue
        name = identities.get(resolution.candidates[0])
        if name is None:
            continue
        reference = resolution.reference
        identities[reference.span] = name
        if not tree.nodes[reference.node].recovered:
            events.append(SemanticPosition(reference.span.start, (name,),
                                           'reference_start', reference.node))
            events.append(SemanticPosition(reference.span.end, (name,),
                                           'reference_use', reference.node))
    for node in tree.nodes:
        _check_cancelled(cancelled)
        if node.recovered:
            continue
        name = identities.get(node.symbol_body_span)
        if name is not None:
            events.append(SemanticPosition(node.span.start, (name,), 'object_start', node.id))
            events.append(SemanticPosition(inclusive_ends[node.id], (name,), 'object_end', node.id))
        alias = identities.get(node.alias_target_span)
        if alias is not None and not node.alias_ambiguous:
            start, end = _alias_expression_span(node)
            events.append(SemanticPosition(start, (alias,), 'object_start', node.id))
            events.append(SemanticPosition(end, (alias,), 'object_end', node.id))
            events.append(SemanticPosition(node.alias_target_span.end, (alias,), 'alias_use', node.id))
    return tuple(sorted(dict.fromkeys(events), key=lambda event: (
        event.position, -1 if event.node is None else event.node, event.kind, event.objects)))


def _semantic_elements(tree, semantics, declarations, inclusive_ends, footprints, *, cancelled=None):
    """Structural map identities, separate from canonical parser symbols.

    Named bodies retain the resolver identity. Plain sections and otherwise
    unowned rows receive snapshot-stable internal IDs. Ordinary rows use their
    enclosing context. Containment is parent -> child; exact resolved uses are
    context -> target. Neither relationship imports the receiver into a target.
    """
    identities = {span: declaration.name for span, declaration in declarations.items()}
    resolved = []
    for resolution in semantics.resolutions:
        _check_cancelled(cancelled)
        if resolution.status in RESOLVED and len(resolution.candidates) == 1:
            target = identities.get(resolution.candidates[0])
            if target is not None:
                identities[resolution.reference.span] = target
                resolved.append((resolution.reference, target))
    definitions = {item.object: list(item.definitions) for item in footprints}
    mentions = {item.object: item.mentions for item in footprints}
    dependencies = {item.object: set() for item in footprints}
    labels = {item.object: item.object for item in footprints}
    nodes = {declaration.name: declaration.node for declaration in declarations.values()}
    contexts, local_aliases = {}, {}
    events = []
    prefix = '@element:'
    while any(name.startswith(prefix) for name in definitions):
        prefix = '@' + prefix
    for node in tree.nodes:
        _check_cancelled(cancelled)
        enclosing = next((contexts[link] for link in (node.section, node.parent)
                          if link in contexts), None)
        body = identities.get(node.symbol_body_span) if not node.recovered else None
        plain_section = node.kind in ('section_header_candidate', 'section_scalar_candidate')
        own_context = body is not None or plain_section or enclosing is None
        if own_context:
            name = body if body is not None else f'{prefix}{node.id}'
            if name not in definitions:
                definitions[name] = [(node.span.start, inclusive_ends[node.id])]
                mentions[name] = ()
                dependencies[name] = set()
                label = ''.join(token.text for token in node.tokens).strip()
                labels[name] = label[:80] or 'Blank source'
                nodes[name] = node.id
            if enclosing is not None and enclosing != name:
                dependencies[enclosing].add(name)
            events.extend((SemanticPosition(node.span.start, (name,), 'object_start', node.id),
                           SemanticPosition(inclusive_ends[node.id], (name,), 'object_end', node.id)))
        else:
            name = enclosing
        contexts[node.id] = name
        alias = identities.get(node.alias_target_span)
        if alias is not None and not node.recovered and not node.alias_ambiguous:
            start, end = _alias_expression_span(node)
            local_aliases[node.id] = (alias, start, node.alias_target_span.start)
            if alias != name:
                dependencies[name].add(alias)
    references = {}
    for reference, target in resolved:
        _check_cancelled(cancelled)
        if tree.nodes[reference.node].recovered:
            continue
        owner = contexts[reference.node]
        if owner != target:
            dependencies[owner].add(target)
        references.setdefault(reference.node, set()).add(target)
        alias = local_aliases.get(reference.node)
        if alias is not None:
            name, start, end = alias
            if start <= reference.span.start and reference.span.end <= end and name != target:
                dependencies[name].add(target)
    elements = tuple(SemanticElement(name, _span_union(spans, cancelled=cancelled),
                                    mentions[name], tuple(sorted(dependencies[name])),
                                    nodes.get(name), labels[name])
                     for name, spans in definitions.items())
    order = {item.object: index for index, item in enumerate(elements)}
    previous_views = {view.node: view for view in _semantic_views(
        tree, semantics, declarations, inclusive_ends, cancelled=cancelled)}
    views = []
    for node in tree.nodes:
        _check_cancelled(cancelled)
        names = {contexts[node.id]} | references.get(node.id, set())
        if node.id in local_aliases:
            names.add(local_aliases[node.id][0])
        previous = previous_views[node.id]
        views.append(SemanticView(node.id, previous.position,
                                 tuple(sorted(names, key=order.__getitem__)), previous.kind))
    return elements, tuple(views), tuple(events)


def whole_block_owners(tree, semantics, *, cancelled=None):
    """Whole contexts, independent of generic nested section partitions.

Supported symbolic body headers start contexts, including resolved identities
at nested headers. AS alone does not create a new body. Other nodes share their
enclosing context through the parser's section/parent links. Unsupported or
recovered headers do not manufacture semantic context identities.
    """
    identities = {s.span for s in semantics.symbols if s.kind in ('anchor', 'alias')}
    identities.update(r.reference.span for r in semantics.resolutions
                      if r.status in RESOLVED and len(r.candidates) == 1)
    owners = {}
    for node in tree.nodes:
        _check_cancelled(cancelled)
        enclosing = next((owners[link] for link in (node.section, node.parent)
                          if link in owners), None)
        separate = (node.symbol_body_span in identities and not node.recovered)
        owners[node.id] = node.id if separate or enclosing is None else enclosing
    return owners


def build_graph_snapshot(tree, semantics, *, mode='heuristic', options=None, cancelled=None):
    """Keep heuristic evidence exact; semantic mode adds character footprints."""
    mode = normalize_graph_mode(mode)
    _check_cancelled(cancelled)
    owners = whole_block_owners(tree, semantics, cancelled=cancelled)
    # Blank lines keep their geometry but must not lower the document minimum.
    blocks = set()
    for node in tree.nodes:
        _check_cancelled(cancelled)
        if any(token.text.strip() for token in node.tokens):
            blocks.add(owners[node.id])
    declarations = {s.span: s for s in sorted(semantics.symbols,
                                             key=lambda symbol: (symbol.span.start, symbol.span.end))
                    if s.kind in ('anchor', 'alias')}
    occurrences = []
    for resolution in semantics.resolutions:
        _check_cancelled(cancelled)
        if resolution.status not in RESOLVED or len(resolution.candidates) != 1:
            continue
        declaration = declarations.get(resolution.candidates[0])
        if declaration is None:
            continue
        receiver = owners[resolution.reference.node]
        source = owners[declaration.node]
        if receiver != source:
            occurrences.append((receiver, source))
    _check_cancelled(cancelled)
    if mode == 'heuristic' and options is None:
        # Preserve both the legacy calculation and its lightweight snapshot.
        return GraphSnapshot(tuple(sorted(blocks)), tuple(occurrences), tuple(owners.items()))
    # Canonical syntax nodes partition the complete source, retaining blank
    # lines, BOMs, physical line endings and recovered/literal source through EOF.
    length = max((node.span.end for node in tree.nodes), default=0)
    settings = validate_options(options, length)
    footprints = ()
    views = ()
    positions = ()
    elements = ()
    inclusive_ends = (_inclusive_node_ends(tree, cancelled=cancelled)
                      if mode != 'heuristic' else {})
    if mode != 'heuristic' and settings.parser_support:
        footprints = _semantic_footprints(tree, semantics, declarations, inclusive_ends,
                                          cancelled=cancelled)
    if mode != 'heuristic':
        views = _semantic_views(tree, semantics,
                                declarations if settings.parser_support else {},
                                inclusive_ends, cancelled=cancelled)
    if mode == 'semantic_triad_2' and settings.parser_support:
        positions = _semantic_positions(tree, semantics, declarations, inclusive_ends,
                                         cancelled=cancelled)
    if mode != 'heuristic' and settings.parser_support:
        elements, views, structural_events = _semantic_elements(
            tree, semantics, declarations, inclusive_ends, footprints, cancelled=cancelled)
        if mode == 'semantic_triad_2':
            positions = tuple(sorted(set(positions + structural_events), key=lambda event: (
                event.position, -1 if event.node is None else event.node, event.kind, event.objects)))
    ends = dict.fromkeys(blocks, 0)
    for node in tree.nodes:
        _check_cancelled(cancelled)
        owner = owners[node.id]
        if owner in ends:
            ends[owner] = max(ends[owner], node.span.end)
    if mode != 'heuristic':
        # Map silhouettes partition nested blocks, but a parent's semantic
        # point of use is the end of its whole inclusive source context.
        for block in ends:
            _check_cancelled(cancelled)
            ends[block] = max(ends[block], inclusive_ends[block])
    _check_cancelled(cancelled)
    return GraphSnapshot(tuple(sorted(blocks)), tuple(occurrences), tuple(owners.items()),
                         mode, settings, (), tuple(sorted(ends.items())), length, (), footprints, views, positions, elements)
