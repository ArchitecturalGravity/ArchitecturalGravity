"""AG-LITERAL-UNCLOSED: identify unpaired exact literal delimiters."""
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-LITERAL-UNCLOSED"


def detect(context, node):
    if node.kind != "unterminated_literal_open":
        return
    opening = next((t for t in node.tokens if t.kind == "literal_open"), None)
    if opening:
        yield RuleProposal(opening.span, node.id,
                           "Literal opener has no matching close; remaining source is shielded",
                           ("unclosed_literal",))


def verify(context, candidate):
    node = context.tree.nodes[candidate.node_id]
    valid = (node.kind == "unterminated_literal_open"
             and any(t.kind == "literal_open" and t.span == candidate.span
                     for t in node.tokens))
    return () if valid else ("missing_unclosed_literal",)


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "literal_openers"), detect, verify, literal_policy="only")
