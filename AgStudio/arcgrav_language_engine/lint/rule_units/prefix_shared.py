"""Shared token-shape mechanics for operation/list prefix rules."""
from ...recognition import SourceSpan

from ...syntax_contract import NUMERIC_LIST as _NUMERIC_LIST


def prefix_span(node):
    markers = node.prefix_tokens
    if not markers:
        return None
    last = markers[-1]
    trailing = next((t for t in node.tokens
                     if t.span.start == last.span.end and t.kind == "whitespace"), None)
    return SourceSpan(markers[0].span.start,
                      trailing.span.end if trailing else last.span.end)


def canonical_prefix(node, markers):
    """Check the concrete marker witness, not unrelated later source tokens."""
    if not markers:
        return False
    indentation = next((t for t in node.tokens if t.kind == "indentation"), None)
    clear_spacing = not (indentation and "\t" in indentation.text) and all(
        t.kind != "whitespace" or all(c == " " for c in t.text)
        for t in node.tokens
        if markers[0].span.start <= t.span.start < markers[-1].span.end
    )
    lists = (t for t in markers if t.kind == "list_marker")
    return clear_spacing and all(t.text == "-" or _NUMERIC_LIST.fullmatch(t.text)
                                 for t in lists)
