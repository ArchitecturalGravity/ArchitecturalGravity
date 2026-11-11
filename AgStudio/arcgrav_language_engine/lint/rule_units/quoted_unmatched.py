"""AG-QUOTED-ELEMENT-NO-MATCH: independently matched exact scalar elements."""
from ..quoted_elements import MESSAGE, unmatched_quoted_elements
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-QUOTED-ELEMENT-NO-MATCH"


def detect(context, node):
    if node is not None:
        return
    unmatched = context.evidence(
        "unmatched_quotes", lambda: unmatched_quoted_elements(context.tree))
    for node_id, span in sorted(unmatched, key=lambda row: row[1].start):
        yield RuleProposal(span, node_id, MESSAGE,
                           ("unmatched_exact_quoted_element",))


def verify(context, candidate):
    unmatched = context.evidence(
        "unmatched_quotes", lambda: unmatched_quoted_elements(context.tree),
        verification=True)
    return (() if (candidate.node_id, candidate.span) in unmatched
            else ("unsupported_quoted_element_match",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "quoted_scalars"), detect, verify, scope="document")
