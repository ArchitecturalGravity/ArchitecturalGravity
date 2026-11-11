"""AG-LIST-MIXED: canonical adjacent list-prefix families."""
from .contracts import RuleProposal, RuleUnit
from .prefix_shared import prefix_span

RULE_ID = "AG-LIST-MIXED"


def _families(markers):
    return {"dash" if t.text == "-" else "priority" if t.text.startswith("P")
            else "ordered" for t in markers if t.kind == "list_marker"}


def detect(context, node):
    markers = node.prefix_tokens
    if (len(markers) >= 2 and not any(t.kind == "operation" for t in markers)
            and len(_families(markers)) > 1):
        yield RuleProposal(prefix_span(node), node.id,
                           "Distinct list prefix families share one line",
                           ("prefix_chain",))


def verify(context, candidate):
    markers = context.tree.nodes[candidate.node_id].prefix_tokens
    blockers = []
    if markers:
        if candidate.span != prefix_span(context.tree.nodes[candidate.node_id]):
            blockers.append("imprecise_prefix_range")
    else:
        blockers.append("missing_prefix_chain")
    if len(_families(markers)) < 2 or any(t.kind == "operation" for t in markers):
        blockers.append("missing_distinct_list_families")
    return tuple(blockers)


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "prefix_tokens"), detect, verify, literal_policy="exclude")
