"""Lossless typed tokens and a recovering, non-executing syntax tree.

Recognition supplies source candidates, not presentation colors. Lexing shields
quoted values before exposing symbols, aliases or binding facts. Unknown syntax
remains exact text; the tree does not execute or expand any source content.
"""
from dataclasses import dataclass, replace
import re

from ..syntax_contract import INDENT_WIDTH
from ..document import ParsedDocument
from ..recognition import SourceSpan
from ..symbol_syntax import bracket_groups, scalar_shields as _scalar_shields

_LINE_ENDINGS = '\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029'
_PREFIX = re.compile(r'(?:=>|-|[0-9]+\.|P[0-9]+\.)(?=[ \t]|$)')
_TRIVIA = frozenset(('indentation', 'whitespace', 'newline'))


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    span: SourceSpan
    text: str = ''


@dataclass(frozen=True, slots=True)
class Node:
    id: int
    kind: str
    span: SourceSpan
    indent: int | None
    parent: int | None
    section: int | None
    recovered: bool
    prefix_tokens: tuple[Token, ...] = ()
    symbol_tokens: tuple[Token, ...] = ()
    alias_marker_span: SourceSpan | None = None
    alias_target_span: SourceSpan | None = None
    alias_ambiguous: bool = False
    binding_marker_span: SourceSpan | None = None
    children: tuple[int, ...] = ()
    quoted_spans: tuple[SourceSpan, ...] = ()
    anchor_span: SourceSpan | None = None
    symbol_body_span: SourceSpan | None = None
    possible_symbol_body_span: SourceSpan | None = None
    uncertain_declaration_spans: tuple[SourceSpan, ...] = ()
    tokens: tuple[Token, ...] = ()


@dataclass(frozen=True, slots=True)
class SyntaxTree:
    tokens: tuple[Token, ...]
    nodes: tuple[Node, ...]
    recovery_spans: tuple[SourceSpan, ...]

    def find_quoted_element(self, quoted_text: str) -> tuple[Token, ...]:
        """Return whole, source-exact double-quoted tokens in source order.

        The query includes both delimiters. Bare, incomplete, multiline and
        repeated-quote forms do not identify an inline element. This is lexical
        occurrence matching, not symbolic resolution or inferred equivalence.
        Case, spacing, Unicode and backslashes are never normalized. Opaque
        fence bodies are absent from the canonical quoted-scalar token stream.
        """
        if not isinstance(quoted_text, str):
            raise TypeError('quoted element query must be a string')
        if not _complete_double_quoted_element(quoted_text):
            return ()
        return tuple(token for node in self.nodes for token in active_double_quoted_elements(node)
                     if token.text == quoted_text)




def _complete_double_quoted_element(quoted_text: str) -> bool:
    if (len(quoted_text) < 2 or not quoted_text.startswith('"')
        or not quoted_text.endswith('"') or quoted_text.startswith('"""')
        or any(char in _LINE_ENDINGS for char in quoted_text)):
        return False
    # Follow the scanner's conservative backslash shielding, without
    # decoding escapes or treating an escaped terminal quote as a closer.
    trailing = len(quoted_text[:-1]) - len(quoted_text[:-1].rstrip('\\'))
    if trailing % 2 or _scalar_shields(quoted_text, 0) != (SourceSpan(0, len(quoted_text)),):
        return False
    return True



def double_quote_collisions(node: Node) -> tuple[SourceSpan, ...]:
    """Detect bare-word collisions between otherwise complete quote pairs.

    Quotes touching both ends of intervening bare text cannot delimit separate
    textual elements. Whitespace/punctuation-separated elements remain valid;
    this does not infer quote intent in arbitrary prose or define escape syntax.
    Canonical tokens keep fences, other quote kinds and recovery text opaque.
    """
    if 'literal' in node.kind or node.kind.startswith('markdown_fence_'):
        return ()
    spans = []
    previous = None
    gap = []
    for token in node.tokens:
        if token.kind == 'quoted_scalar' and _complete_double_quoted_element(token.text):
            between = ''.join(gap)
            if (previous is not None and between and
                    (between[0].isalnum() or between[0] == '_') and
                    (between[-1].isalnum() or between[-1] == '_')):
                start = previous.span.start
                if spans and spans[-1].end == previous.span.end:
                    start = spans.pop().start
                spans.append(SourceSpan(start, token.span.end))
            previous = token
            gap = []
        elif previous is not None and token.kind in ('text', 'whitespace'):
            gap.append(token.text)
        else:
            previous = None
            gap = []
    return tuple(spans)


def active_double_quoted_elements(node: Node) -> tuple[Token, ...]:
    """Complete source elements, excluding ambiguous collision fragments."""
    if 'literal' in node.kind or node.kind.startswith('markdown_fence_'):
        return ()
    collisions = iter(double_quote_collisions(node))
    collision = next(collisions, None)
    result = []
    for token in node.tokens:
        if token.kind != 'quoted_scalar' or not _complete_double_quoted_element(token.text):
            continue
        while collision is not None and collision.end <= token.span.start:
            collision = next(collisions, None)
        if collision is None or token.span.end <= collision.start:
            result.append(token)
    return tuple(result)


def _plain_tokens(source: str, start: int, end: int) -> list[Token]:
    """Retain trivia and every otherwise unclassified code point."""
    result: list[Token] = []
    cursor = start
    while cursor < end:
        if source[cursor] in _LINE_ENDINGS:
            stop = cursor + 2 if source[cursor:cursor + 2] == '\r\n' and cursor + 2 <= end else cursor + 1
            kind = 'newline'
        elif source[cursor] in ' \t':
            stop = cursor + 1
            while stop < end and source[stop] in ' \t':
                stop += 1
            kind = 'whitespace'
        else:
            stop = cursor + 1
            while stop < end and source[stop] not in ' \t' + _LINE_ENDINGS:
                stop += 1
            kind = 'text'
        result.append(Token(kind, SourceSpan(cursor, stop), source[cursor:stop]))
        cursor = stop
    return result


def lex(document: ParsedDocument) -> tuple[Token, ...]:
    """Partition source into typed, exact tokens without consulting highlighting.

    A token is a lexical fact, not proof of normative validity. Candidate names
    remain subject to semantic confidence checks. Literal bodies and quoted
    scalars cannot produce symbols, aliases, binders or recovery facts.
    """
    source = document.source
    result: list[Token] = []
    occurrences = document.occurrence_facts
    occurrence_index = 0
    for observation in document.recognition.observations:
        span = observation.span
        text = span.extract(source)
        if observation.kind.startswith('markdown_fence_'):
            result.append(Token('literal', span, text))
            continue
        if 'literal_content' in observation.kind:
            result.append(Token('literal', span, text))
            continue
        if 'literal' in observation.kind:
            left = len(text) - len(text.lstrip(' \t'))
            right = len(text.rstrip(' \t' + _LINE_ENDINGS))
            result.extend(_plain_tokens(source, span.start, span.start + left))
            kind = 'literal_close' if observation.kind == 'literal_close' else 'literal_open'
            marker = SourceSpan(span.start + left, span.start + right)
            result.append(Token(kind, marker, marker.extract(source)))
            result.extend(_plain_tokens(source, marker.end, span.end))
            continue

        shields = _scalar_shields(text, span.start)
        candidates: list[Token] = [Token('backtick_scalar' if shield.extract(source).startswith('`')
                                        and not shield.extract(source).startswith('``') else 'quoted_scalar',
                                        shield, shield.extract(source))
                                   for shield in shields]

        def add(kind: str, start: int, end: int) -> None:
            if start < end and not any(start < shield.end and shield.start < end for shield in shields):
                candidate_span = SourceSpan(start, end)
                candidates.append(Token(kind, candidate_span, candidate_span.extract(source)))

        for start, end, kind in bracket_groups(text, tuple((q.start - span.start, q.end - span.start) for q in shields)):
            start, end = span.start + start, span.start + end
            if kind == 'malformed_symbol':
                # An active invalid opener remains an error even when its
                # attempted name contains a quoted value. Mark only its active
                # prefix, keeping every quoted byte opaque and lossless.
                end = min((q.start for q in shields if start < q.start < end), default=end)
            add(kind, start, end)

        prefix_end = len(text) - len(text.lstrip(' \t'))
        if prefix_end:
            add('indentation', span.start, span.start + prefix_end)
        body_end = len(text.rstrip(_LINE_ENDINGS))
        cursor = prefix_end
        while cursor < body_end:
            marker = _PREFIX.match(text[:body_end], cursor)
            if marker is None:
                break
            add('operation' if marker.group() == '=>' else 'list_marker',
                span.start + cursor, span.start + marker.end())
            cursor = marker.end()
            while cursor < body_end and text[cursor] in ' \t':
                cursor += 1
        if observation.kind in ('section_header_candidate', 'section_scalar_candidate'):
            colon = text.find(':', prefix_end)
            if colon >= 0:
                add('section_colon', span.start + colon, span.start + colon + 1)

        while occurrence_index < len(occurrences) and occurrences[occurrence_index].span.end <= span.start:
            occurrence_index += 1
        index = occurrence_index
        while index < len(occurrences) and occurrences[index].span.start < span.end:
            fact = occurrences[index]
            start, end = fact.span.start, fact.span.end
            if fact.kind == 'alias_marker_candidate':
                add('alias_keyword', start, start + len(source[start:end].rstrip()))
            elif fact.kind.startswith('block_binding_'):
                value = source[start:end]
                left = len(value) - len(value.lstrip())
                add('binder', start + left, end)
            elif fact.kind == 'wildcard_candidate':
                add('wildcard', start, end)
            index += 1

        # Retain attempted aliases without inventing a declaration. The old
        # candidate scanner intentionally excludes a line beginning AS [Name],
        # but consumers need to distinguish it from an invocation of [Name].
        for token in tuple(candidates):
            if token.kind != 'symbol':
                continue
            marker_start = token.span.start - 3
            if (marker_start >= span.start and source[marker_start:token.span.start] == 'AS '
                    and (marker_start == span.start or source[marker_start - 1].isspace())):
                add('alias_keyword', marker_start, marker_start + 2)

        # Shapes retained by recognition can overlap (e.g. wildcard glyphs).
        # Prefer an enclosing typed value, never split a quote or symbol.
        candidates.sort(key=lambda token: (token.span.start, -token.span.end))
        cursor = span.start
        for token in candidates:
            if token.span.start < cursor:
                continue
            result.extend(_plain_tokens(source, cursor, token.span.start))
            result.append(token)
            cursor = token.span.end
        result.extend(_plain_tokens(source, cursor, span.end))
    return tuple(result)


def _metadata(tokens: tuple[Token, ...], kind: str) -> dict:
    meaningful = [token for token in tokens if token.kind not in _TRIVIA]
    prefixes: list[Token] = []
    for token in meaningful:
        if token.kind not in ('operation', 'list_marker'):
            break
        prefixes.append(token)
    symbols = tuple(token for token in tokens if token.kind == 'symbol')
    binder = meaningful[-1].span if meaningful and meaningful[-1].kind == 'binder' else None
    tail = meaningful[:-1] if binder else meaningful
    marker = target = anchor = None
    uncertain: list[SourceSpan] = []
    ambiguous = False
    if len(tail) >= 2 and tail[-2].kind == 'alias_keyword' and tail[-1].kind == 'symbol':
        marker = tail[-2].span
        prior = tail[:-2]
        if kind in ('section_header_candidate', 'section_scalar_candidate'):
            # A section label alone is not its scalar value's source context.
            colons = [index for index, token in enumerate(prior) if token.kind == 'section_colon']
            if colons:
                prior = prior[colons[0] + 1:]
        # A list marker or an operation arrow is not an aliased expression.
        has_source = any(token.kind not in ('operation', 'list_marker') for token in prior)
        ambiguous = bool(binder)
        if has_source and not binder:
            target = tail[-1].span
        else:
            uncertain.append(tail[-1].span)
    if len(meaningful) >= 2 and meaningful[0].kind == 'symbol':
        following = meaningful[1]
        if kind in ('section_header_candidate', 'section_scalar_candidate') and following.kind == 'section_colon':
            anchor = meaningful[0].span
        elif following.text.startswith(':'):
            uncertain.append(meaningful[0].span)
    # Preserve declaration-shaped list bodies as evidence. Semantic resolution
    # separately decides whether the current owner permits a new identity.
    body_symbol = anchor
    body = meaningful[len(prefixes):]
    if (len(prefixes) == 1 and prefixes[0].kind == 'list_marker'
            and len(body) >= 2 and body[0].kind == 'symbol'
            and body[1].text.startswith(':')):
        if body[1].text == ':':
            body_symbol = body[0].span
        else:
            uncertain.append(body[0].span)
    possible_body = (body[0].span if len(body) == 1 and body[0].kind == 'symbol'
                     and not any(t.kind == 'operation' for t in prefixes) else None)
    return dict(prefix_tokens=tuple(prefixes), symbol_tokens=symbols,
                alias_marker_span=marker, alias_target_span=target,
                alias_ambiguous=ambiguous, binding_marker_span=binder,
                quoted_spans=tuple(token.span for token in tokens if token.kind in ('quoted_scalar', 'backtick_scalar')),
                anchor_span=anchor, symbol_body_span=body_symbol, possible_symbol_body_span=possible_body, uncertain_declaration_spans=tuple(uncertain), tokens=tokens)


def parse(document: ParsedDocument) -> SyntaxTree:
    tokens = lex(document)
    nodes: list[Node] = []
    stack: list[Node] = []
    sections: dict[int, int] = {}
    literal_owner = None
    token_index = 0
    recovery_index = 0
    # Recognition observes bracket fragments before scalar-quote shielding.
    # Do not expose fragments hidden by the lexer as canonical recoveries.
    quoted = tuple(token.span for token in tokens if token.kind in ('quoted_scalar', 'backtick_scalar'))
    quoted_index = 0
    visible_recoveries = []
    for recovery in document.recoveries:
        while quoted_index < len(quoted) and quoted[quoted_index].end <= recovery.span.start:
            quoted_index += 1
        if (quoted_index < len(quoted) and quoted[quoted_index].start <= recovery.span.start
                and recovery.span.end <= quoted[quoted_index].end):
            continue
        visible_recoveries.append(recovery)
    recoveries = tuple(visible_recoveries)
    for observation in document.recognition.observations:
        text = observation.span.extract(document.source)
        prefix = text[:len(text) - len(text.lstrip(' \t'))]
        indent = len(prefix) if '\t' not in prefix and len(prefix) % INDENT_WIDTH == 0 else None
        kind = observation.kind
        while token_index < len(tokens) and tokens[token_index].span.end <= observation.span.start:
            token_index += 1
        stop = token_index
        while stop < len(tokens) and tokens[stop].span.start < observation.span.end:
            stop += 1
        line_tokens = tokens[token_index:stop]
        # A protected heading cannot become a section merely because the
        # source candidate scanner found a colon inside quoted text.
        if (kind in ('section_header_candidate', 'section_scalar_candidate')
                and not any(t.kind == 'section_colon' for t in line_tokens)):
            kind = 'unclassified'
        metadata = _metadata(line_tokens, kind)
        token_index = stop
        while recovery_index < len(recoveries) and recoveries[recovery_index].span.end <= observation.span.start:
            recovery_index += 1
        recovered = (recovery_index < len(recoveries)
                     and recoveries[recovery_index].span.start < observation.span.end)
        if kind.startswith('markdown_fence_'):
            # Neither body indentation nor fake headings alter the live stack
            # or section map. The whole example belongs to its opening owner.
            if kind == 'markdown_fence_open':
                literal_owner = len(nodes)
                parent = stack[-1].id if stack and indent is not None and stack[-1].indent == indent - 2 else None
                nodes.append(Node(len(nodes), kind, observation.span, indent, parent,
                                  sections.get(indent), False, **metadata))
            else:
                owner_section = nodes[literal_owner].section if literal_owner is not None else None
                nodes.append(Node(len(nodes), kind, observation.span, indent, literal_owner,
                                  owner_section, False, **metadata))
                if kind == 'markdown_fence_close':
                    literal_owner = None
            continue
        if 'literal' in kind:
            if kind in ('literal_open', 'unterminated_literal_open'):
                while stack and (indent is None or stack[-1].indent >= indent):
                    stack.pop()
                sections = ({level: ident for level, ident in sections.items() if level <= indent}
                            if indent is not None else {})
                parent = stack[-1].id if stack and indent is not None and stack[-1].indent == indent - 2 else None
                literal_owner = len(nodes)
                nodes.append(Node(len(nodes), kind, observation.span, indent, parent,
                                  sections.get(indent), recovered, **metadata))
            else:
                owner_section = nodes[literal_owner].section if literal_owner is not None else None
                nodes.append(Node(len(nodes), kind, observation.span, indent, literal_owner,
                                  owner_section, recovered, **metadata))
                if kind == 'literal_close':
                    literal_owner = None
            continue
        if not text.strip():
            nodes.append(Node(len(nodes), kind, observation.span, indent, None, None, recovered, **metadata))
            continue
        if indent is None:
            stack.clear()
            sections.clear()
            nodes.append(Node(len(nodes), kind, observation.span, None, None, None, True, **metadata))
            continue
        while stack and stack[-1].indent >= indent:
            stack.pop()
        parent = stack[-1].id if stack and stack[-1].indent == indent - 2 else None
        sections = {level: ident for level, ident in sections.items() if level <= indent}
        is_header = kind == 'section_header_candidate'
        section = sections.get(indent)
        node = Node(len(nodes), kind, observation.span, indent, parent,
                    None if is_header or kind == 'section_scalar_candidate' else section, recovered, **metadata)
        nodes.append(node)
        # A header at N owns subsequent members at N independently from an
        # indentation parent at N-2; literal bodies preserve this distinction.
        if is_header:
            sections[indent] = node.id
        elif kind == 'section_scalar_candidate':
            sections.pop(indent, None)
        # Explicit binding belongs to a complete expression, including prose.
        explicit_parent = node.binding_marker_span is not None and bool(
            document.source[node.span.start:node.binding_marker_span.start].strip())
        if (kind != 'unclassified' and 'boundary' not in kind) or explicit_parent or node.possible_symbol_body_span is not None:
            stack.append(node)
    children: dict[int, list[int]] = {}
    for node in nodes:
        if node.parent is not None:
            children.setdefault(node.parent, []).append(node.id)
    nodes = [replace(node, children=tuple(children.get(node.id, ()))) for node in nodes]
    return SyntaxTree(tokens, tuple(nodes), tuple(r.span for r in recoveries))
