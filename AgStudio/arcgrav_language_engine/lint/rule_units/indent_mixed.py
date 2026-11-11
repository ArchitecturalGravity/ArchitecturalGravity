"""AG-INDENT-MIXED: detect active indentation mixing tabs and spaces."""
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-INDENT-MIXED"


def detect(context, node):
    active = node.kind != "unclassified" or bool(node.prefix_tokens)
    indentation = next((t for t in node.tokens if t.kind == "indentation"), None)
    if active and indentation and " " in indentation.text and "\t" in indentation.text:
        yield RuleProposal(indentation.span, node.id,
                           "Indentation mixes spaces and tabs",
                           ("active_indentation",))


def verify(context, candidate):
    node = context.tree.nodes[candidate.node_id]
    indentation = next((t for t in node.tokens if t.kind == "indentation"), None)
    active = node.kind != "unclassified" or bool(node.prefix_tokens)
    valid = (indentation is not None and indentation.span == candidate.span
             and active and " " in indentation.text and "\t" in indentation.text)
    return () if valid else ("unsupported_indentation_evidence",)


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "indentation_tokens"), detect, verify, literal_policy="exclude")
