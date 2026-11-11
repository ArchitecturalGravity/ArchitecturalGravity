"""Document boundary requirements over canonical section and ownership facts."""

from ..recognition import SourceSpan

RULE_ID = 'AG-DOCUMENT-END-SECTION'
MESSAGE = 'The last top-level parent element must be a plain section, such as "Task".'
START_RULE_ID = 'AG-DOCUMENT-START-SECTION'
START_MESSAGE = 'Define an initial invocation at the top like "Scope" to constrain the overall LLM inference boundary.'
_SECTIONS = {'section_header_candidate', 'section_scalar_candidate'}
_TRIVIA = {'indentation', 'whitespace', 'newline'}


def document_end_span(tree):
    """Return one (node, range) when the final root parent is not a section.

    Physical containment and same-indent section ownership both exclude a node
    from the roots. Trailing leaves do not replace a parent. Empty documents
    have no actionable range and are exempt until content is entered.
    """
    last_parent = last_content = None
    active = []
    for node in tree.nodes:
        values = [token for token in node.tokens if token.kind not in _TRIVIA]
        if not values or not any(token.text.strip() for token in values):
            continue
        last_content = node, values
        if 'literal' in node.kind or node.kind.startswith('markdown_fence_'):
            continue
        active.append((node, values))
    active_ids = {node.id for node, _ in active}
    owners = {node.section for node, _ in active if node.section in active_ids}
    for node, values in active:
        if node.parent in active_ids or node.section in active_ids:
            continue
        if (node.kind in _SECTIONS or node.kind == 'section_boundary_candidate'
                or node.children or node.id in owners or node.binding_marker_span is not None):
            last_parent = node, values
    if last_content is None:
        return None
    if last_parent is not None:
        node, values = last_parent
        if is_plain_section(node, values):
            return None
    else:
        node, values = last_content
    return node.id, content_span(values)


def is_plain_section(node, values):
    """Canonical section candidates include symbols; require an undecorated label."""
    return (node.kind in _SECTIONS and node.indent == 0 and not node.recovered
            and len(values) >= 2 and values[0].kind == 'text'
            and values[0].text.isidentifier() and values[1].kind == 'section_colon'
            and not any(token.kind in ('symbol', 'malformed_symbol', 'alias_keyword', 'binder')
                        for token in values))


def content_span(values):
    first, last = values[0], values[-1]
    start = first.span.start + len(first.text) - len(first.text.lstrip())
    end = last.span.end - len(last.text) + len(last.text.rstrip())
    return SourceSpan(start, end)


def document_start_span(tree):
    """Check the first meaningful element; later headings cannot cure its absence.

    Blank lines are ignored and empty documents are exempt, as for the end rule.
    Protected/recovered contents cannot provide a plain canonical section.
    """
    for node in tree.nodes:
        values = [token for token in node.tokens if token.kind not in _TRIVIA]
        if not values or not any(token.text.strip() for token in values):
            continue
        if (node.parent is None and node.section is None
                and is_plain_section(node, values)):
            return None
        return node.id, content_span(values)
    return None
