"""AG-SYMBOL-NESTED-DECLARATION: independent scope and identity proof."""
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-SYMBOL-NESTED-DECLARATION"


def detect(context, node):
    if node is not None or context.semantics is None:
        return
    for sequence, resolution in enumerate(context.semantics.resolutions):
        if resolution.status == "forbidden_nested_declaration":
            symbol = resolution.reference
            yield RuleProposal(
                symbol.span, symbol.node,
                f"[{symbol.name}] has no prior local identity inside this symbol body; only AS may introduce it here; external identity unresolved",
                ("forbidden_nested_declaration",), sequence)


def verify(context, candidate):
    from ..semantics import symbol_bodies
    if context.semantics is None:
        return ("missing_nested_introduction_evidence",)
    tree = context.tree
    node = tree.nodes[candidate.node_id]
    resolutions = context.evidence(
        "semantic_resolutions",
        lambda: {(r.reference.span, r.reference.node): r.status
                 for r in context.semantics.resolutions}, verification=True)
    bodies = context.evidence("symbol_bodies", lambda: symbol_bodies(tree),
                              verification=True)
    body = bodies[node.id]
    if node.symbol_body_span is not None and candidate.span.start > node.symbol_body_span.start:
        body = node.id
    blockers = []
    if (resolutions.get((candidate.span, node.id)) != "forbidden_nested_declaration"
            or body is None or node.recovered or candidate.span != node.symbol_body_span
            or candidate.span == node.alias_target_span
            or not any(t.span == candidate.span for t in node.symbol_tokens)
            or candidate.span in node.uncertain_declaration_spans):
        blockers.append("missing_nested_introduction_evidence")
    declarations = context.evidence(
        "symbol_declarations",
        lambda: {s.name: s.span.start for s in context.semantics.symbols
                 if s.kind in ("anchor", "alias")}, verification=True)
    prior_start = declarations.get(candidate.span.extract(context.source)[1:-1])
    if prior_start is not None and prior_start < candidate.span.start:
        blockers.append("prior_identity_exists")
    return tuple(blockers)


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "semantics", "symbol_bodies"),
                    detect, verify, scope="document", batch_group="semantic_resolutions")
