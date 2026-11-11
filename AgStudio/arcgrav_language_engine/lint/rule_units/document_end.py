"""AG-DOCUMENT-END-SECTION: document-level final-parent evidence."""
from ..document_end import MESSAGE, document_end_span
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-DOCUMENT-END-SECTION"


def detect(context, node):
    if node is not None:
        return
    evidence = document_end_span(context.tree)
    if evidence is not None:
        node_id, span = evidence
        yield RuleProposal(span, node_id, MESSAGE, ("final_root_parent",))


def verify(context, candidate):
    return (() if document_end_span(context.tree) == (candidate.node_id, candidate.span)
            else ("unsupported_document_end",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "document_end"), detect, verify, scope="document")
