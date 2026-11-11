"""AG-BINDING-CHILD: physically bound expressions without recognized children."""
from bisect import bisect_right
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-BINDING-CHILD"


def detect(context, node):
    if node is not None or context.semantics is None:
        return
    starts = context.evidence(
        "node_starts", lambda: tuple(n.span.start for n in context.tree.nodes))
    for binding in context.semantics.bindings:
        if binding.status == "physical_whole_line" and not binding.children:
            node_id = bisect_right(starts, binding.marker.start) - 1
            yield RuleProposal(
                binding.marker, node_id,
                "Explicit whole-line binder has no recognized indented child",
                (binding.status,))


def verify(context, candidate):
    markers = context.evidence(
        "unowned_binders",
        lambda: frozenset(b.marker for b in context.semantics.bindings
                          if b.status == "physical_whole_line" and not b.children)
        if context.semantics is not None else frozenset(),
        verification=True)
    return (() if candidate.span in markers
            else ("missing_binding_relationship",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "semantics", "bindings"),
                    detect, verify, scope="document")
