"""Qt-free, source-exact presentation spans projected from core recognition.

Colors are not conformance: each token retains its originating observation kind.
This projection styles already recognized candidates and their bracket interiors;
it never discovers relationships, expands patterns, or diagnoses source. Unknown
punctuation and unsupported quoted-scalar grammar remain ordinary source text.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .document import ParsedDocument
from .recognition import SourceSpan


@dataclass(frozen=True, slots=True)
class HighlightToken:
    span: SourceSpan
    role: str
    recognition_kind: str


def _backtick_tokens(token):
    start, end = token.span.start, token.span.end
    yield HighlightToken(SourceSpan(start, start + 1), 'backtick', token.kind)
    closed = len(token.text) > 1 and token.text.endswith('`') and not token.text.endswith('\\`')
    if end - int(closed) > start + 1:
        yield HighlightToken(SourceSpan(start + 1, end - int(closed)), 'backtick_content', token.kind)
    if closed:
        yield HighlightToken(SourceSpan(end - 1, end), 'backtick', token.kind)


def _double_quote_tokens(token):
    """Style the lexer's single-pair representation, retaining its recovery bounds."""
    start, end = token.span.start, token.span.end
    yield HighlightToken(SourceSpan(start, start + 1), 'double_quote', token.kind)
    # Match the existing conservative shield scanner's backslash handling;
    # this is presentation of its token, not a new normative escape grammar.
    before_close = token.text[:-1]
    backslashes = len(before_close) - len(before_close.rstrip('\\'))
    closed = len(token.text) > 1 and token.text.endswith('"') and backslashes % 2 == 0
    if end - int(closed) > start + 1:
        yield HighlightToken(SourceSpan(start + 1, end - int(closed)), 'double_quote_content', token.kind)
    if closed:
        yield HighlightToken(SourceSpan(end - 1, end), 'double_quote', token.kind)


def _is_double_quote(token):
    return token.kind == 'quoted_scalar' and token.text.startswith('"') and not token.text.startswith('"""')


def highlight_tokens(document: ParsedDocument) -> tuple[HighlightToken, ...]:
    """Return deterministic code-point ranges; literal boundaries own their body."""
    if hasattr(document, 'syntax'):
        lexical = document.syntax.tokens
        projected = []
        roles = {'operation': 'operation', 'alias_keyword': 'alias', 'binder': 'binder',
                 'section_colon': 'colon', 'wildcard': 'wildcard',
                 'literal_open': 'delimiter', 'literal_close': 'delimiter', 'literal': 'literal',
                 'quoted_scalar': 'literal'}
        for node in document.syntax.nodes:
            colon = next((t for t in node.tokens if t.kind == 'section_colon'), None)
            if colon is not None:
                for token in node.tokens:
                    if token.span.end <= colon.span.start and token.kind in ('text', 'whitespace'):
                        projected.append(HighlightToken(token.span, 'section', node.kind))
        for token in lexical:
            if token.kind == 'backtick_scalar':
                projected.extend(_backtick_tokens(token))
            elif _is_double_quote(token):
                projected.extend(_double_quote_tokens(token))
            elif token.kind == 'symbol':
                projected.append(HighlightToken(SourceSpan(token.span.start, token.span.start + 1), 'symbol', token.kind))
                if token.span.end - token.span.start > 2:
                    projected.append(HighlightToken(SourceSpan(token.span.start + 1, token.span.end - 1), 'symbol_body', token.kind))
                projected.append(HighlightToken(SourceSpan(token.span.end - 1, token.span.end), 'symbol', token.kind))
            elif token.kind == 'malformed_symbol':
                projected.append(HighlightToken(SourceSpan(token.span.start, token.span.start + 1), 'symbol', token.kind))
            elif token.kind == 'list_marker':
                text = token.span.extract(document.source)
                role = 'bullet' if text == '-' else 'priority' if text.startswith('P') else 'sequence'
                projected.append(HighlightToken(token.span, role, token.kind))
            elif token.kind in roles:
                projected.append(HighlightToken(token.span, roles[token.kind], token.kind))
        return tuple(sorted(projected, key=lambda token: (token.span.start, token.span.end, token.role)))
    tokens: list[HighlightToken] = []

    def add(start: int, end: int, role: str, kind: str) -> None:
        if end > start:
            tokens.append(HighlightToken(SourceSpan(start, end), role, kind))

    for observation in document.recognition.observations:
        kind = observation.kind
        text = observation.span.extract(document.source)
        start = observation.span.start
        # Strip only for the display extent, never to accept or classify input.
        left = len(text) - len(text.lstrip())
        end = len(text.rstrip())
        if 'literal_content' in kind:
            add(start, start + end, 'literal', kind)
        elif 'literal' in kind:
            add(start + left, start + end, 'delimiter', kind)
        elif kind in ('section_header_candidate', 'section_scalar_candidate'):
            colon = text.find(':', left)
            if colon >= 0:
                if not text[left:colon].startswith('['):
                    add(start + left, start + len(text[:colon].rstrip()), 'section', kind)
                add(start + colon, start + colon + 1, 'colon', kind)
        elif '_list_' in kind:
            # Candidate family and source extent are supplied by recognition.
            marker = re.match(r'(?:-|[0-9]+\.|P[0-9]+\.)', text[left:])
            if marker:
                end_marker = start + left + marker.end()
                role = 'bullet' if marker.group() == '-' else 'priority' if marker.group().startswith('P') else 'sequence'
                add(start + left, end_marker, role, kind)
        elif kind.startswith('operation_') and text[left:].startswith('=>'):
            add(start + left, start + left + 2, 'operation', kind)

    for fact in document.occurrence_facts:
        start, end, kind = fact.span.start, fact.span.end, fact.kind
        if kind.startswith('indentation_'):
            continue  # Whitespace remains whitespace, not a claimed hierarchy.
        if kind == 'alias_marker_candidate':
            # The existing exact occurrence is the AS keyword, not its context.
            text = fact.span.extract(document.source)
            add(start, start + len(text.rstrip()), 'alias', kind)
        elif kind.startswith('block_binding_'):
            text = fact.span.extract(document.source)
            left = len(text) - len(text.lstrip())
            add(start + left, start + len(text.rstrip()), 'binder', kind)
        elif kind == 'wildcard_candidate':
            add(start, end, 'wildcard', kind)
        elif kind.startswith('symbol_'):
            add(start, start + 1, 'symbol', kind)
            if document.source[end - 1] == ']':
                add(start + 1, end - 1, 'symbol_body', kind)
                add(end - 1, end, 'symbol', kind)
        # Backticks are a representation convention, not a syntax primitive.
    from .lint.syntax import lex
    lexical = lex(document)
    backticks = [t for t in lexical if t.kind == 'backtick_scalar']
    shields = [t for t in lexical if t.kind in {'backtick_scalar', 'quoted_scalar'}]
    tokens = [t for t in tokens if not any(b.span.start < t.span.end and t.span.start < b.span.end for b in shields)]
    for token in backticks:
        tokens.extend(_backtick_tokens(token))
    for token in lexical:
        if _is_double_quote(token):
            tokens.extend(_double_quote_tokens(token))
    return tuple(sorted(tokens, key=lambda token: (token.span.start, token.span.end,
                                                   token.role)))
