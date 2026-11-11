"""Immutable, Qt-free highlighting data prepared outside the editor thread.

Coordinates use QTextDocument's normalized UTF-16 view. Splitting and indexing
presentation spans is disposable work; it does not parse or change the source.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from .highlighting import highlight_tokens


HighlightRange = tuple[int, int, str]


@dataclass(frozen=True, slots=True)
class HighlightProjection:
    document_id: str
    ranges: tuple[HighlightRange, ...]
    block_starts: tuple[int, ...]
    block_lengths: tuple[int, ...]
    blocks: tuple[tuple[HighlightRange, ...], ...]
    source_length: int


def derive_highlighting(document) -> HighlightProjection:
    """Project a document, analysis, or frozen process snapshot, without Qt.

    Snapshot restoration reuses the canonical parse rather than parsing source
    again. The result contains only immutable, pickleable presentation values.
    """
    from .analysis_snapshot import (AnalysisSnapshot, DocumentSnapshot, PackedAnalysisSnapshot,
                                    restore_document, unpack_analysis)
    if isinstance(document, PackedAnalysisSnapshot):
        document = unpack_analysis(document)

    if isinstance(document, AnalysisSnapshot):
        document = document.document
    elif hasattr(document, 'document'):
        document = document.document
    if isinstance(document, DocumentSnapshot):
        document = restore_document(document)

    offsets = [0]
    starts = [0]
    previous = ''
    for character in document.source:
        folded_lf = character == '\n' and previous == '\r'
        width = 0 if folded_lf else 2 if ord(character) > 0xffff else 1
        offsets.append(offsets[-1] + width)
        # U+2029 is a QTextDocument paragraph separator; U+2028 remains a
        # line separator within one paragraph, unlike Python's splitlines().
        if not folded_lf and character in ('\n', '\r', '\u2029'):
            starts.append(offsets[-1])
        previous = character
    lengths = tuple(end - start - 1 for start, end in zip(starts, starts[1:]))
    lengths += (offsets[-1] - starts[-1],)
    ranges = tuple(sorted(
        ((offsets[token.span.start], offsets[token.span.end], token.role)
         for token in highlight_tokens(document)),
        key=lambda item: (item[0], item[1]),
    ))
    blocks: list[list[HighlightRange]] = [[] for _ in starts]
    for start, end, role in ranges:
        index = bisect_right(starts, start) - 1
        while index < len(starts) and starts[index] < end:
            block_start = starts[index]
            left, right = max(start, block_start), min(end, block_start + lengths[index])
            if left < right:
                blocks[index].append((left - block_start, right - block_start, role))
            index += 1
    return HighlightProjection(document.document_id, ranges, tuple(starts), lengths,
                               tuple(tuple(block) for block in blocks), offsets[-1])
