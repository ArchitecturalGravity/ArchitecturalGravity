"""AG-DOCUMENT-START-SECTION: document-level starting-section evidence."""
from ..document_end import START_MESSAGE, document_start_span
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-DOCUMENT-START-SECTION"


def detect(context, node):
    if node is not None:
        return
    evidence = document_start_span(context.tree)
    if evidence is not None:
        node_id, span = evidence
        yield RuleProposal(span, node_id, START_MESSAGE, ("initial_root_element",))


def verify(context, candidate):
    return (() if document_start_span(context.tree) == (candidate.node_id, candidate.span)
            else ("unsupported_document_start",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "document_start"), detect, verify, scope="document")
