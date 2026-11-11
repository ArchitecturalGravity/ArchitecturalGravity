"""Explicit, deterministic ordering of self-contained lint units."""
from dataclasses import replace
from types import MappingProxyType

from ..editor_checks import MESSAGES as EDITOR_MESSAGES
from ..members import MEMBER_FINDING_MESSAGES
from ..spelling import SPELLING_MESSAGES
from . import (
    backtick_whitespace, indent_mixed, indent_width, literal_unclosed,
    operation_incomplete, syntax_incomplete, document_start, document_end,
    quoted_collision, quoted_unmatched, literal_fence_width, block_separator,
    symbol_unused, operation_list, list_mixed, structural_rule,
    symbolic_reference, symbol_nested, binding_child, editor_rule,
    spelling_rule, member_rule,
)

_SINGLETONS = (
    backtick_whitespace, indent_mixed, indent_width, literal_unclosed,
    operation_incomplete, syntax_incomplete, document_start, document_end,
    quoted_collision, quoted_unmatched, literal_fence_width, block_separator,
    symbol_unused, operation_list, list_mixed, symbol_nested, binding_child,
)
_FAMILIES = (structural_rule, symbolic_reference, editor_rule,
             spelling_rule, member_rule)

# Registration describes the source-order scan lifecycle, never a second
# grammar. Adding a rule extends this table and its rule unit; the runner
# does not need a new conditional.
_NODE_ORDER = (
    "AG-TRAILING-WHITESPACE",
    "AG-BINDING-SPACING",
    "AG-SYMBOL-ORPHAN",
    "AG-LINE-ENDING",
    "AG-BACKTICK-WHITESPACE",
    *sorted(structural_rule.RULE_IDS),
    "AG-LITERAL-UNCLOSED",
    "AG-INDENT-MIXED",
    "AG-INDENT-WIDTH",
    "AG-OPERATION-INCOMPLETE",
    "AG-OPERATION-LIST",
    "AG-LIST-MIXED",
    "AG-SYNTAX-INCOMPLETE",
)
_DOCUMENT_ORDER = (
    "AG-DOCUMENT-START-SECTION",
    "AG-DOCUMENT-END-SECTION",
    *SPELLING_MESSAGES,
    *MEMBER_FINDING_MESSAGES,
    "AG-DOUBLE-QUOTE-COLLISION",
    "AG-QUOTED-ELEMENT-NO-MATCH",
    "AG-LITERAL-FENCE-WIDTH",
    "AG-BLOCK-SEPARATOR",
    "AG-SYMBOL-UNUSED",
    "AG-SYMBOL-BEFORE-DEFINITION",
    "AG-SYMBOL-NO-LOCAL-ANCHOR",
    "AG-SYMBOL-DUPLICATE-INSTANTIATION",
    "AG-ALIAS-DUPLICATE-INSTANTIATION",
    "AG-SYMBOL-NESTED-DECLARATION",
    "AG-BINDING-CHILD",
)


def build_units(metadata):
    """Bind rule-owned metadata, detector, verifier, scope and evidence needs."""
    result = {}

    def register(rule_id, build_rule):
        if rule_id in result:
            raise ValueError(f"duplicate lint rule unit: {rule_id}")
        if rule_id not in metadata:
            raise ValueError(f"lint rule unit lacks metadata: {rule_id}")
        unit = build_rule(metadata[rule_id])
        if unit.id != rule_id or not callable(unit.detect) or not callable(unit.verify):
            raise ValueError(f"invalid lint rule unit: {rule_id}")
        result[rule_id] = unit

    for module in _SINGLETONS:
        register(module.RULE_ID, module.build_rule)
    for module in _FAMILIES:
        for rule_id in module.RULE_IDS:
            register(rule_id, module.build_rule)

    all_ids = (*_NODE_ORDER, *_DOCUMENT_ORDER)
    if len(all_ids) != len(set(all_ids)) or set(result) != set(all_ids):
        raise ValueError("every rule unit must have exactly one scan placement")
    for order, rule_id in enumerate(_NODE_ORDER):
        unit = result[rule_id]
        if unit.scope != "node":
            raise ValueError(f"document rule in node scan: {rule_id}")
        result[rule_id] = replace(unit, order=order)
    for order, rule_id in enumerate(_DOCUMENT_ORDER):
        unit = result[rule_id]
        if unit.scope != "document":
            raise ValueError(f"node rule in document scan: {rule_id}")
        result[rule_id] = replace(unit, order=order)
    return MappingProxyType(result)
