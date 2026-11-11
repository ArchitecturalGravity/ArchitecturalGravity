"""Editor-formatting rule units backed by one shared per-node source scan."""
from ..editor_checks import MESSAGES, content_owners, spans as editor_spans
from .contracts import RuleProposal, RuleUnit

RULE_IDS = tuple(MESSAGES)


def _spans(context, node, *, verification=False):
    owners = context.evidence("editor_owners",
        lambda: content_owners(context.tree), verification=verification)
    return context.evidence(f"editor_node_{node.id}",
        lambda: editor_spans(node, context.tree, context.source, owners),
        verification=verification)


def build_rule(metadata):
    rule_id = metadata.id
    if rule_id not in MESSAGES:
        raise ValueError(rule_id)

    def detect(context, node):
        if node is None:
            return
        span = _spans(context, node).get(rule_id)
        if span is not None:
            yield RuleProposal(span, node.id, MESSAGES[rule_id],
                               ("editor_formatting",))

    def verify(context, candidate):
        node = context.tree.nodes[candidate.node_id]
        return (() if _spans(context, node, verification=True).get(rule_id)
                == candidate.span else ("unsupported_editor_formatting",))

    return RuleUnit(metadata, ("syntax", "editor_formatting"),
                    detect, verify)
