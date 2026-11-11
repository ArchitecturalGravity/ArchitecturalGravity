"""Source-ordered symbolic reference and duplicate-instantiation rule units."""
from .contracts import RuleProposal, RuleUnit

RULE_IDS = {
    "AG-SYMBOL-BEFORE-DEFINITION": "forward_candidate",
    "AG-SYMBOL-NO-LOCAL-ANCHOR": "missing_local_anchor",
    "AG-SYMBOL-DUPLICATE-INSTANTIATION": "duplicate_symbol_instantiation",
    "AG-ALIAS-DUPLICATE-INSTANTIATION": "duplicate_alias_instantiation",
}


def _resolutions(context):
    return {(r.reference.span, r.reference.node): r.status
            for r in context.semantics.resolutions} if context.semantics is not None else {}


def build_rule(metadata):
    rule_id = metadata.id
    status = RULE_IDS[rule_id]

    def detect(context, node):
        if node is not None or context.semantics is None:
            return
        for sequence, resolution in enumerate(context.semantics.resolutions):
            if resolution.status == status:
                symbol = resolution.reference
                if status.startswith("duplicate_"):
                    message = (f"[{symbol.name}] is already instantiated; "
                               "reference it without ':' or 'AS'.")
                else:
                    message = (f"[{symbol.name}] must be instantiated before being referenced; "
                               + resolution.reason)
                yield RuleProposal(
                    symbol.span, symbol.node, message, (status,), sequence)

    def verify(context, candidate):
        resolutions = context.evidence("semantic_resolutions",
                                       lambda: _resolutions(context),
                                       verification=True)
        return (() if resolutions.get((candidate.span, candidate.node_id)) == status
                else ("missing_semantic_resolution",))

    return RuleUnit(metadata, ("semantics", "symbol_resolutions"),
                    detect, verify, scope="document", batch_group="semantic_resolutions")
