"""Shared physical-structure indexes and independent rule-specific predicates.

These predicates only inspect the existing canonical syntax facts. They do not
reparse text or infer undocumented grammar. Each rule owns its own premise
function; only physical traversal and parent-expression logic are shared.
"""
from ...syntax_contract import INDENT_WIDTH
import re
from types import MappingProxyType

from ...recognition import SourceSpan


def index(tree):
    occupied = set()
    previous = {}
    prior = None
    for node in tree.nodes:
        meaningful = [t for t in node.tokens
                      if t.kind not in ("indentation", "whitespace", "newline")]
        if not meaningful:
            continue
        if node.section is not None:
            occupied.add(node.section)
        if node.parent is not None:
            occupied.add(node.parent)
        # A broken first child cannot establish an empty section.
        if prior is not None and prior.kind == "section_header_candidate" and node.recovered:
            occupied.add(prior.id)
        previous[node.id] = prior
        prior = node
    return occupied, previous


def parent_expression(node, tree, *, allow_symbol_parent=False):
    """Conservative active expression before a whitespace-delimited annotation."""
    if (node.recovered or node.indent is None or not node.children
            or (node.possible_symbol_body_span is not None and not allow_symbol_parent)
            or len(node.prefix_tokens) != 1):
        return ()
    children = [tree.nodes[child] for child in node.children]
    if not any(not child.recovered and child.indent == node.indent + INDENT_WIDTH
               and "literal" not in child.kind and child.kind != "unclassified"
               for child in children):
        return ()
    tokens = []
    prior = None
    for token in node.tokens:
        if (token.kind == "text" and token.text.startswith("//")
                and prior is not None and prior.kind == "whitespace"
                and all(c == " " for c in prior.text)):
            break
        if token.kind not in ("indentation", "whitespace", "newline"):
            tokens.append(token)
        prior = token
    if any(t.kind == "whitespace" and "\t" in t.text for t in node.tokens):
        return ()
    marker = node.prefix_tokens[0]
    if marker.text not in ("-", "=>") and not re.fullmatch(
            r"(?:[1-9][0-9]*|P(?:0|[1-9][0-9]*))\.", marker.text):
        return ()
    return tuple(tokens[1:])


def parent_block_opener(node, tree, indexed, meaningful):
    if node.recovered or node.indent is None:
        return None
    # Ordered-parent syntax owns its own precise finding.
    if ordered_parent_colon(node, tree, indexed, meaningful) is not None:
        return None
    expression = parent_expression(node, tree, allow_symbol_parent=True)
    if expression and not expression[-1].text.endswith((":", "↳")):
        return node.prefix_tokens[0].span
    if (len(meaningful) == 1 and meaningful[0].kind == "symbol"
            and re.fullmatch(r"\[[A-Za-z][A-Za-z0-9]*\]", meaningful[0].text)):
        for next_id in range(node.id + 1, len(tree.nodes)):
            following = tree.nodes[next_id]
            if not any(t.kind not in ("indentation", "whitespace", "newline")
                       for t in following.tokens):
                continue
            if (not following.recovered
                    and following.indent in (node.indent, node.indent + INDENT_WIDTH)
                    and following.prefix_tokens
                    and following.prefix_tokens[0].kind == "list_marker"
                    and re.fullmatch(
                        r"(?:-|[1-9][0-9]*\.|P(?:0|[1-9][0-9]*)\.)",
                        following.prefix_tokens[0].text)):
                return meaningful[0].span
            break
    return None


def binding_reference_colon(node, tree, indexed, meaningful):
    expression = parent_expression(node, tree)
    if not expression:
        return None
    last = expression[-1]
    if (len(expression) >= 3 and last.text == ":"
            and expression[-2].kind == "symbol"
            and expression[-2].span.end == last.span.start
            and re.fullmatch(r"\[[A-Za-z][A-Za-z0-9]*\]", expression[-2].text)
            and not any(t.kind in ("alias_keyword", "section_colon")
                        for t in expression[:-2])):
        return last.span
    return None


def ordered_parent_colon(node, tree, indexed, meaningful):
    expression = parent_expression(node, tree)
    if not expression:
        return None
    last = expression[-1]
    if (re.fullmatch(r"[1-9][0-9]*\.", node.prefix_tokens[0].text)
            and not last.text.endswith((":", "↳"))
            and not any(t.kind in ("malformed_symbol", "alias_keyword")
                        for t in expression)):
        return node.prefix_tokens[0].span
    return None


def section_empty(node, tree, indexed, meaningful):
    occupied, _ = indexed
    if node.kind == "section_header_candidate" and node.id not in occupied and not node.recovered:
        return next((t.span for t in node.tokens if t.kind == "section_colon"), None)
    return None


def indent_jump(node, tree, indexed, meaningful):
    _, previous = indexed
    prior = previous.get(node.id)
    if (prior is not None and not prior.recovered and not node.recovered
            and "literal" not in prior.kind and prior.kind != "unclassified"
            and node.kind != "unclassified" and prior.indent is not None
            and node.indent is not None and node.indent > prior.indent + INDENT_WIDTH):
        return next((t.span for t in node.tokens if t.kind == "indentation"), None)
    return None


def alias_source(node, tree, indexed, meaningful):
    if (node.alias_marker_span is not None and node.alias_target_span is None
            and not node.alias_ambiguous and node.uncertain_declaration_spans):
        return node.alias_marker_span
    return None


def list_empty(node, tree, indexed, meaningful):
    if len(meaningful) == 1 and meaningful[0].kind == "list_marker":
        marker = meaningful[0]
        if marker.text == "-" or re.fullmatch(
                r"(?:[1-9][0-9]*|P(?:0|[1-9][0-9]*))\.", marker.text):
            return marker.span
    return None


def operation_multiple(node, tree, indexed, meaningful):
    arrows = [t for t in node.prefix_tokens if t.kind == "operation"]
    if len(arrows) > 1:
        prefix_end = node.prefix_tokens[-1].span.end
        if all(t.kind != "whitespace" or all(c == " " for c in t.text)
               for t in node.tokens
               if node.prefix_tokens[0].span.start <= t.span.start < prefix_end):
            return SourceSpan(arrows[0].span.start, arrows[-1].span.end)
    return None


def wildcard_bare(node, tree, indexed, meaningful):
    values = [t for t in meaningful if t not in node.prefix_tokens]
    if (len(values) == 1 and values[0].kind == "wildcard"
            and values[0].text == "*" and node.section is None
            and node.parent is None and not node.recovered):
        return values[0].span
    return None


_CHECKS = MappingProxyType({
    "AG-PARENT-BLOCK-OPENER": parent_block_opener,
    "AG-BINDING-REFERENCE-COLON": binding_reference_colon,
    "AG-ORDERED-PARENT-COLON": ordered_parent_colon,
    "AG-SECTION-EMPTY": section_empty,
    "AG-INDENT-JUMP": indent_jump,
    "AG-ALIAS-SOURCE": alias_source,
    "AG-LIST-EMPTY": list_empty,
    "AG-OPERATION-MULTIPLE": operation_multiple,
    "AG-WILDCARD-BARE": wildcard_bare,
})


def span(rule_id, node, tree, indexed):
    """Independently reconstruct one rule's exact range from canonical syntax."""
    check = _CHECKS.get(rule_id)
    if check is None or "literal" in node.kind:
        return None
    meaningful = [t for t in node.tokens
                  if t.kind not in ("indentation", "whitespace", "newline")]
    return check(node, tree, indexed, meaningful)
