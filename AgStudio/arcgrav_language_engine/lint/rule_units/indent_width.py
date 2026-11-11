"""AG-INDENT-WIDTH: recognize odd-width active ASCII indentation."""
from ...syntax_contract import INDENT_WIDTH
from .contracts import RuleContext, RuleProposal, RuleUnit

RULE_ID = "AG-INDENT-WIDTH"


def detect(context, node):
    active = node.kind != "unclassified" or bool(node.prefix_tokens)
    indentation = next((t for t in node.tokens if t.kind == "indentation"), None)
    if (active and indentation and indentation.text
            and all(c == " " for c in indentation.text)
            and len(indentation.text) % INDENT_WIDTH):
        yield RuleProposal(indentation.span, node.id,
                           "Recognized syntax has an odd number of indentation spaces",
                           ("active_indentation",))


def verify(context, candidate):
    node = context.tree.nodes[candidate.node_id]
    indentation = next((t for t in node.tokens if t.kind == "indentation"), None)
    active = node.kind != "unclassified" or bool(node.prefix_tokens)
    valid = (indentation is not None and indentation.span == candidate.span
             and active and bool(indentation.text)
             and all(c == " " for c in indentation.text)
             and len(indentation.text) % INDENT_WIDTH == 1)
    return () if valid else ("unsupported_indentation_evidence",)


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "indentation_tokens"), detect, verify, literal_policy="exclude")
