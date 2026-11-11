"""AG-BACKTICK-WHITESPACE: reject whitespace in exact structural names."""
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-BACKTICK-WHITESPACE"
_MESSAGE = ("Backticked structural name contains whitespace; use double quotes for "
            "textual values, or use a whitespace-free structural identifier")


def spans(node, source):
    """Source-exact backtick spans, excluding literal and escaped values."""
    if "literal" in node.kind:
        return ()
    return tuple(t.span for t in node.tokens if t.kind == "backtick_scalar"
                 and len(t.text) > 2 and t.text.endswith("`") and "\\" not in t.text
                 and any(c.isspace() for c in t.text[1:-1]))


def detect(context, node):
    for span in spans(node, context.source):
        yield RuleProposal(span, node.id, _MESSAGE, ("backtick_whitespace",))


def verify(context, candidate):
    node = context.tree.nodes[candidate.node_id]
    return (() if candidate.span in spans(node, context.source)
            else ("unsupported_backtick_whitespace",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "backtick_tokens"), detect, verify)
