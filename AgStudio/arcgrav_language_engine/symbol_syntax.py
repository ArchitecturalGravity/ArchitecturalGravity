"""Shared line-bounded bracket syntax; values are never evaluated."""
import re
from .recognition import SourceSpan

_LINE_ENDINGS = '\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029'

from .syntax_contract import SYMBOL_NAME


def bracket_groups(text, opaque=()):
    """Yield (start, end, kind) without leaking tokens from nested groups.

    Empty [] is the documented empty collection, not a symbolic identifier.
    Escaped groups and caller-supplied opaque quote ranges stay inert.
    """
    index = 0
    limit = len(text.rstrip('\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029'))
    while index < limit:
        hidden = next((end for start, end in opaque if start <= index < end), None)
        if hidden is not None:
            index = hidden
            continue
        if text[index] == "\\":
            # Preserve the existing escaped-bracket convention for the whole group.
            if index + 1 < limit and text[index + 1] == '[':
                close = text.find(']', index + 2, limit)
                index = close + 1 if close >= 0 else limit
            else:
                index += 2
            continue
        if text[index] == ']':
            yield index, index + 1, 'malformed_symbol'
            index += 1
            continue
        if text[index] != '[':
            index += 1
            continue
        start = index
        depth = 1
        nested = False
        index += 1
        while index < limit and depth:
            if text[index] == '[':
                depth += 1
                nested = True
            elif text[index] == ']':
                depth -= 1
            index += 1
        value = text[start + 1:index - 1] if not depth else None
        if value == '' and not nested:
            continue
        kind = ('symbol' if not nested and value is not None and SYMBOL_NAME.fullmatch(value)
                else 'malformed_symbol')
        yield start, index, kind


def scalar_shields(text: str, start: int) -> tuple[SourceSpan, ...]:
    """Shield simple quoted values without asserting an escape grammar.

    Backslash plus its following character is kept opaque regardless of whether
    an external grammar would recognize that escape. Unfinished quoted values
    are shielded to their physical line end, never through following lines.
    Apostrophes within words remain text. Unsupported inline quote runs are
    opaque, without claiming that they are multiline literal delimiters.
    """
    shields: list[SourceSpan] = []
    index = 0
    end = len(text.rstrip(_LINE_ENDINGS))
    while index < end:
        quote = text[index]
        if quote not in '\"\'`' or (index and text[index - 1] == '\\'):
            index += 1
            continue
        if quote == "'" and index and text[index - 1].isalnum():
            index += 1
            continue
        if index + 1 < end and text[index + 1] == quote:
            run_end = index + 2
            while run_end < end and text[run_end] == quote:
                run_end += 1
            if run_end == index + 2:
                shields.append(SourceSpan(start + index, start + run_end))
            else:
                # Inline repeated-quote grammar is unspecified. Preserve it as
                # opaque source instead of leaking apparent syntax from it.
                marker = text[index:run_end]
                close = text.find(marker, run_end, end)
                run_end = close + len(marker) if close >= 0 else end
                shields.append(SourceSpan(start + index, start + run_end))
            index = run_end
            continue
        cursor = index + 1
        while cursor < end:
            if text[cursor] == '\\':
                cursor = min(end, cursor + 2)
            elif text[cursor] == quote:
                cursor += 1
                break
            else:
                cursor += 1
        shields.append(SourceSpan(start + index, start + cursor))
        index = cursor
    return tuple(shields)

