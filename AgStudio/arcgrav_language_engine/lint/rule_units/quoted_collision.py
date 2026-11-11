"""AG-DOUBLE-QUOTE-COLLISION: independent quoted-scalar collision evidence."""
from ..quoted_elements import COLLISION_MESSAGE, quoted_element_collisions
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-DOUBLE-QUOTE-COLLISION"


def detect(context, node):
    if node is not None:
        return
    collisions = context.evidence(
        "quote_collisions", lambda: quoted_element_collisions(context.tree))
    for node_id, span in sorted(collisions, key=lambda row: row[1].start):
        yield RuleProposal(span, node_id, COLLISION_MESSAGE,
                           ("embedded_double_quote_collision",))


def verify(context, candidate):
    collisions = context.evidence(
        "quote_collisions", lambda: quoted_element_collisions(context.tree),
        verification=True)
    return (() if (candidate.node_id, candidate.span) in collisions
            else ("unsupported_double_quote_collision",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "quoted_scalars"), detect, verify, scope="document")
