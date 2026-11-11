"""AG-BLOCK-SEPARATOR: exact sibling block boundary verification."""
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-BLOCK-SEPARATOR"


def spans(tree, semantics):
    """Missing separators at sibling block starts, using canonical ownership.

    A first block in each physical parent needs no separator from its parent.
    Symbol-shaped headers count only when semantics establishes a new anchor.
    """
    anchors = {(s.node, s.span) for s in semantics.symbols if s.kind == 'anchor'} if semantics else set()
    previous_blocks = {}
    spans = {}
    previous = None
    for node in tree.nodes:
        if node.recovered:
            previous_blocks.clear()
        if not node.recovered and node.kind in ('section_header_candidate', 'section_scalar_candidate'):
            span = node.symbol_body_span
            if span is not None:
                is_block = (node.id, span) in anchors
            else:
                span = next((t.span for t in node.tokens if t.kind == 'section_colon'), None)
                is_block = span is not None
            if is_block:
                # Blank physical lines separate blocks; literal contents do not.
                blank = previous is not None and not any(
                    t.kind not in ('indentation', 'whitespace', 'newline') for t in previous.tokens)
                if node.parent in previous_blocks and not blank:
                    spans[node.id] = span
                previous_blocks[node.parent] = node.id
        previous = node
    return spans



def detect(context, node):
    if node is not None:
        return
    result = context.evidence(
        "block_separators", lambda: spans(context.tree, context.semantics))
    for node_id, span in result.items():
        yield RuleProposal(span, node_id,
                           "Add a blank line before this block to separate it from the preceding block",
                           ("adjacent_distinct_blocks",))


def verify(context, candidate):
    index = context.evidence(
        "block_separators", lambda: spans(context.tree, context.semantics),
        verification=True)
    return (() if index.get(candidate.node_id) == candidate.span
            else ("unsupported_block_boundary",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "semantics", "block_boundaries"),
                    detect, verify, scope="document")
