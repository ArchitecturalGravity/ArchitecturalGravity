"""AG-OPERATION-LIST: one implementation for mixed operation/list prefixes."""
from .contracts import RuleProposal, RuleUnit
from .prefix_shared import _NUMERIC_LIST, canonical_prefix, prefix_span

RULE_ID = "AG-OPERATION-LIST"


def finding_span(context, node):
    """An exact leading => - plus content highlights its five-character prefix.

    Other mixed chains highlight all adjacent prefix tokens. This is a single
    source predicate; no previous finding or second diagnostic run is consulted.
    """
    from ...recognition import SourceSpan
    raw = node.span.extract(context.source)
    indent = len(raw) - len(raw.lstrip(' '))
    if raw[indent:].startswith('=> - ') and raw[indent + 5:].strip():
        start = node.span.start + indent
        return SourceSpan(start, start + 5), 'Operation arrow and dash list marker share one line'
    return prefix_span(node), 'Operation and list prefixes share one line'


def detect(context, node):
    markers = node.prefix_tokens
    if len(markers) < 2:
        return
    if not (any(t.kind == "operation" for t in markers)
            and any(t.kind == "list_marker" for t in markers)):
        return
    span, message = finding_span(context, node)
    markers = tuple(t for t in markers if span.start <= t.span.start and t.span.end <= span.end)
    yield RuleProposal(
        span, node.id, message,
        ("canonical_prefix_chain",) if canonical_prefix(node, markers)
        else ("uncertain_numeric_form",))


def verify(context, candidate):
    node = context.tree.nodes[candidate.node_id]
    # Recompute the source witness independently; proposed ranges cannot select
    # a convenient subset of a malformed chain. An exact leading arrow/dash
    # proves its conflict without depending on later, unrelated prefix tokens.
    expected_span, _ = finding_span(context, node)
    markers = tuple(t for t in node.prefix_tokens
                    if expected_span is not None
                    and expected_span.start <= t.span.start
                    and t.span.end <= expected_span.end)
    blockers = []
    if not (any(t.kind == "operation" for t in markers)
            and any(t.kind == "list_marker" for t in markers)):
        blockers.append("missing_prefix_combination")
    if any(t.kind == "indentation" and "\t" in t.text for t in node.tokens):
        blockers.append("unresolved_marker_indentation")
    if markers and any(
            t.kind == "whitespace" and any(c != " " for c in t.text)
            for t in node.tokens
            if markers[0].span.start <= t.span.start < markers[-1].span.end):
        blockers.append("unresolved_marker_spacing")
    if any(t.kind == "list_marker" and t.text != "-"
           and not _NUMERIC_LIST.fullmatch(t.text) for t in markers):
        blockers.append("unresolved_numeric_form")
    if markers:
        if candidate.span != expected_span:
            blockers.append("imprecise_prefix_range")
    else:
        blockers.append("missing_prefix_chain")
    return tuple(blockers)


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "prefix_tokens"),
                    detect, verify, literal_policy="exclude")
