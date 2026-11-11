"""AG-OPERATION-INCOMPLETE: identify bare operation-arrow syntax."""
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-OPERATION-INCOMPLETE"
_TRIVIA = frozenset(("indentation", "whitespace", "newline"))


def _meaningful(node):
    return tuple(t for t in node.tokens if t.kind not in _TRIVIA)


def detect(context, node):
    meaningful = _meaningful(node)
    if len(meaningful) == 1 and meaningful[0].kind == "operation":
        yield RuleProposal(meaningful[0].span, node.id,
                           "Operation arrow has no instruction; recovery stops at this line",
                           ("bare_operation",))


def verify(context, candidate):
    meaningful = _meaningful(context.tree.nodes[candidate.node_id])
    valid = (len(meaningful) == 1 and meaningful[0].kind == "operation"
             and meaningful[0].span == candidate.span)
    return () if valid else ("missing_bare_operation",)


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "operation_tokens"), detect, verify, literal_policy="exclude")
