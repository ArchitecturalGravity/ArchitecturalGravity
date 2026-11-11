"""AG-SYMBOL-UNUSED: per-identity evidence for required later references."""
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-SYMBOL-UNUSED"


def _scan(context):
    # Both phases call the same source predicate but maintain separate caches.
    # Instrumentation therefore observes the independent verification scan.
    from .. import rules
    return rules._unused_declarations(context.tree, context.semantics)


def detect(context, node):
    if node is not None:
        return
    symbols = context.evidence("unused_symbols", lambda: _scan(context))
    for symbol in symbols:
        yield RuleProposal(
            symbol.span, symbol.node,
            f"[{symbol.name}] was instantiated but has no later resolved reference in this document",
            ("unused_explicit_declaration",))


def verify(context, candidate):
    unused = context.evidence(
        "unused_symbols",
        lambda: frozenset((symbol.span, symbol.node) for symbol in _scan(context)),
        verification=True)
    return (() if (candidate.span, candidate.node_id) in unused
            else ("unsupported_unused_declaration",))


def build_rule(metadata):
    return RuleUnit(metadata, ("semantics", "symbol_declarations"),
                    detect, verify, scope="document")
