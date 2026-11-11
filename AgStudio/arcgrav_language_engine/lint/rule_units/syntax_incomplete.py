"""AG-SYNTAX-INCOMPLETE: reject malformed active bracket tokens."""
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-SYNTAX-INCOMPLETE"


def detect(context, node):
    for token in node.tokens:
        if token.kind == "malformed_symbol":
            yield RuleProposal(
                token.span, node.id,
                "Use matched, non-nested brackets around a PascalCase name without spaces; use a colon only for a definition",
                ("malformed_symbol",))


def verify(context, candidate):
    node = context.tree.nodes[candidate.node_id]
    return (() if any(t.kind == "malformed_symbol" and t.span == candidate.span
                      for t in node.tokens) else ("missing_recovery_token",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "malformed_symbol_tokens"), detect, verify, literal_policy="exclude")
