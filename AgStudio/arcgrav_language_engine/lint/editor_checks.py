"""Explicit editor formatting requirements; source-exact and non-executing.

Checks below own their exact predicates and exclusions. They do not reinterpret
literal material or expand references.
"""
import re
import unicodedata
from ..recognition import SourceSpan
from .syntax import _LINE_ENDINGS

MESSAGES = {
    'AG-LINE-ENDING': 'Remove terminal punctuation or quote it as an exact value; ordinary ArcGrav lines end without punctuation',
    'AG-BINDING-SPACING': 'Explicit block binding requires exactly one ASCII space before ↳',
    'AG-TRAILING-WHITESPACE': 'Remove whitespace at the end of this line',
    'AG-SYMBOL-ORPHAN': 'Symbol body is empty; add meaningful context or remove the empty symbol header',
}
_TRIVIA = {'indentation', 'whitespace', 'newline'}


def content_owners(tree):
    """Index physical owners once, excluding bare list markers as content."""
    occupied = set()
    for node in tree.nodes:
        values = [t for t in node.tokens if t.kind not in _TRIVIA | {'list_marker'}]
        if values or node.recovered:
            occupied.update(owner for owner in (node.section, node.parent) if owner is not None)
    return occupied


def spans(node, tree, source, occupied=None):
    """Return all supported ranges, also used by the independent admission gate."""
    if node.kind.startswith('markdown_fence_') or node.kind in ('literal_content', 'unterminated_literal_content'):
        return {}
    result = {}
    raw = node.span.extract(source).rstrip(_LINE_ENDINGS)
    text = raw.rstrip()
    end = node.span.start + len(text)

    def shielded(start, stop):
        return any(q.start < stop and start < q.end for q in node.quoted_spans)

    if len(text) < len(raw) and not shielded(end, node.span.start + len(raw)):
        result['AG-TRAILING-WHITESPACE'] = SourceSpan(end, node.span.start + len(raw))
    if not text or 'literal' in node.kind:
        return result

    # Restrict the binder check to a terminal glyph outside an opaque value.
    if text.endswith('↳') and not shielded(end - 1, end):
        before = text[:-1]
        stem = before.rstrip()
        if stem and before[len(stem):] != ' ':
            result['AG-BINDING-SPACING'] = SourceSpan(node.span.start + len(stem), end)

    meaningful = [t for t in node.tokens if t.kind not in _TRIVIA]
    body = [t for t in meaningful if t not in node.prefix_tokens]
    if (not node.recovered and node.symbol_body_span is not None and len(body) == 2
            and body[0].kind == 'symbol' and body[1].text == ':'):
        occupied = content_owners(tree) if occupied is None else occupied
        if node.id not in occupied:
            result['AG-SYMBOL-ORPHAN'] = body[0].span

    # Dedicated incomplete-item/operation findings own bare marker lines.
    if not body or shielded(end - 1, end):
        return result
    last = text[-1]
    # Pictographs are content (e.g. emoji), not terminal syntax punctuation.
    if unicodedata.category(last)[0] not in 'PS' or unicodedata.category(last) == 'So':
        return result
    # Structural parents, binders and wildcard selectors are valid endings.
    if last in ':↳' or any(t.span.end == end and t.kind in ('symbol', 'wildcard') for t in meaningful):
        return result
    # Balanced containers also appear as exact values and executable syntax.
    pairs = {')': '(', ']': '[', '}': '{'}
    if last in pairs and text.count(pairs[last]) == text.count(last) and pairs[last] in text:
        return result
    word = text.split()[-1]
    # Preserve explicit paths/URLs and compact code values; do not guess their
    # external grammar. Quote exact values to make ambiguous cases explicit.
    if re.match(r'(?:[a-zA-Z][\w+.-]*://|[a-zA-Z]:[\\/]|[./~][\\/]|/|[\w.-]+[\\/])', word):
        return result
    if last == ';' and re.search(r'\w+\([^\n]*\);$', word):
        return result
    result['AG-LINE-ENDING'] = SourceSpan(end - 1, end)
    return result
