"""Shared structural-evidence adapter; one RuleUnit per independent rule ID.

The structural source-shape helpers are intentionally shared by nine related
rules; each registered unit independently detects and verifies its own span.
"""
from .contracts import RuleProposal, RuleUnit
from .structural_checks import index as _structural_index, span as _extra_span

RULE_IDS = (
    "AG-SECTION-EMPTY", "AG-INDENT-JUMP", "AG-ALIAS-SOURCE",
    "AG-LIST-EMPTY", "AG-OPERATION-MULTIPLE", "AG-WILDCARD-BARE",
    "AG-BINDING-REFERENCE-COLON", "AG-ORDERED-PARENT-COLON",
    "AG-PARENT-BLOCK-OPENER",
)


def build_rule(metadata):
    rule_id = metadata.id
    if rule_id not in RULE_IDS:
        raise ValueError(f"unsupported structural rule: {rule_id}")

    def detect(context, node):
        index = context.evidence(
            "structural_index", lambda: _structural_index(context.tree))
        span = _extra_span(rule_id, node, context.tree, index)
        if span is not None:
            yield RuleProposal(span, node.id,
                               metadata.claim + "; " + metadata.limits,
                               metadata.required_evidence)

    def verify(context, candidate):
        index = context.evidence(
            "structural_index", lambda: _structural_index(context.tree),
            verification=True)
        expected = _extra_span(rule_id,
                                     context.tree.nodes[candidate.node_id],
                                     context.tree, index)
        return (() if expected == candidate.span
                else ("unsupported_structural_evidence",))

    return RuleUnit(metadata, ("syntax", "structural_index"), detect, verify)
