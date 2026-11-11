"""Thin Qt application of process-derived, block-local syntax presentation."""
from __future__ import annotations

from bisect import bisect_left, bisect_right

from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import QPlainTextEdit

from ..shared.highlight_projection import HighlightProjection, derive_highlighting
from .color_schemes import SYNTAX_ROLES, default_scheme


class _CoreHighlighter(QSyntaxHighlighter):
    """Retain safe presentation during edits and repaint only changed blocks.

    Local ranges follow block insertions/deletions using contentsChange before
    Qt's own incremental highlighting slot runs. No source snapshot, token
    derivation, UTF-16 conversion, or document-wide repaint occurs on a keypress.
    """

    def __init__(self, editor: QPlainTextEdit) -> None:
        self.editor = editor
        document = editor.document()
        self._blocks = [()] * document.blockCount()
        self._source_length = document.characterCount() - 1
        self._lengths = []
        block = document.begin()
        while block.isValid():
            self._lengths.append(block.length() - 1)
            block = block.next()
        self._projection = None
        self._ranges = ()
        self._ranges_dirty = False
        self._manual_ranges = False
        self._starts = self._max_ends = ()
        self.pending = False
        # Connect first: Qt must not paint old offsets during its edit callback.
        document.contentsChange.connect(self._contents_changed)
        super().__init__(document)
        self.apply_color_scheme(default_scheme())

    def apply_color_scheme(self, scheme) -> None:
        formats = {}
        for role in SYNTAX_ROLES:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(*scheme[role]['foreground']))
            if scheme[role]['background'][3]:
                fmt.setBackground(QColor(*scheme[role]['background']))
            fmt.setFontWeight(QFont.Weight.Normal if role in {
                'literal', 'backtick_content', 'double_quote_content'
            } else QFont.Weight.Bold)
            formats[role] = fmt
        changed = {role for role, fmt in formats.items()
                   if fmt != getattr(self, '_formats', {}).get(role)}
        self._formats = formats
        if not changed:
            return
        with QSignalBlocker(self.editor):
            if self._manual_ranges:
                # Compatibility for explicit legacy range assignment only.
                self.rehighlight()
            else:
                for number, ranges in enumerate(self._blocks):
                    if any(role in changed for _, _, role in ranges):
                        self.rehighlightBlock(self.document().findBlockByNumber(number))

    @property
    def ranges(self):
        # Legacy inspection API. Reconstruct only on explicit access, never in
        # the edit or paint path; the production index remains block-local.
        if self._ranges_dirty and not self._manual_ranges:
            ranges = []
            for number, local in enumerate(self._blocks):
                if local:
                    start = self.document().findBlockByNumber(number).position()
                    ranges.extend((start + left, start + right, role)
                                  for left, right, role in local)
            self._ranges = tuple(ranges)
            self._ranges_dirty = False
        return self._ranges

    @ranges.setter
    def ranges(self, ranges):
        # Retain the public interval-query API used by older callers/tests.
        self._manual_ranges = True
        self._blocks = [()] * self.document().blockCount()
        self._ranges_dirty = False
        self._ranges = tuple(sorted(ranges, key=lambda item: (item[0], item[1])))
        self._starts = tuple(item[0] for item in self._ranges)
        maximum, ends = 0, []
        for _, end, _ in self._ranges:
            maximum = max(maximum, end)
            ends.append(maximum)
        self._max_ends = tuple(ends)

    def block_ranges(self, start, end):
        if self._manual_ranges:
            left = bisect_right(self._max_ends, start)
            right = bisect_left(self._starts, end)
            return self._ranges[left:right]
        result = []
        block = self.document().findBlock(start)
        while block.isValid() and block.position() < end:
            number, offset = block.blockNumber(), block.position()
            if number < len(self._blocks):
                result.extend((offset + left, offset + right, role)
                              for left, right, role in self._blocks[number]
                              if offset + right > start and offset + left < end)
            block = block.next()
        return tuple(result)

    def invalidate(self) -> None:
        """Mark a result pending without blanking safe, mapped presentation."""
        self.pending = True

    def _contents_changed(self, position, removed, added):
        if not removed and not added:
            return  # Formatting-only changes are not source edits.
        document = self.editor.document()
        source_length = document.characterCount() - 1
        # setPlainText/clear can include Qt's final paragraph sentinel in the
        # notification. It is never part of the source or a highlight range.
        removed = min(removed, max(0, self._source_length - position))
        added = min(added, max(0, source_length - position))
        consistent = source_length == self._source_length - removed + added
        self._source_length = source_length
        first_block = document.findBlock(position)
        last_block = document.findBlock(position + added)
        if not consistent or not first_block.isValid() or not last_block.isValid():
            # QTextDocument.setPlainText can report removing its final sentinel.
            self._blocks = [()] * document.blockCount()
            self._lengths = []
            block = document.begin()
            while block.isValid():
                self._lengths.append(block.length() - 1)
                block = block.next()
            self._manual_ranges = False
            self._ranges_dirty = True
            self.pending = True
            return
        first, last = first_block.blockNumber(), last_block.blockNumber()
        delta = document.blockCount() - len(self._blocks)
        old_last = last - delta
        old_first_start = first_block.position()
        before = position - old_first_start
        old_last_start = old_first_start + sum(length + 1 for length in self._lengths[first:old_last])
        after = position + removed - old_last_start
        prefix = tuple(span for span in self._blocks[first] if span[1] <= before) if first < len(self._blocks) else ()
        tail = self._blocks[old_last] if 0 <= old_last < len(self._blocks) else ()
        shift = position + added - last_block.position() - after
        suffix = tuple((left + shift, right + shift, role)
                       for left, right, role in tail if left >= after)
        replacement = [()] * (last - first + 1)
        replacement[0] = prefix
        replacement[-1] += suffix
        self._blocks[first:old_last + 1] = replacement
        lengths, block = [], first_block
        for _ in replacement:
            lengths.append(block.length() - 1)
            block = block.next()
        self._lengths[first:old_last + 1] = lengths
        self._manual_ranges = False
        self._ranges_dirty = True
        self.pending = True

    def apply_projection(self, projection: HighlightProjection) -> bool:
        """Apply current-revision worker output; the caller owns revision guards."""
        document = self.document()
        if (projection.source_length != document.characterCount() - 1
                or len(projection.blocks) != document.blockCount()):
            return False
        manual = self._manual_ranges
        old = self._blocks
        self._blocks = list(projection.blocks)
        self._lengths = list(projection.block_lengths)
        self._source_length = projection.source_length
        self._projection = projection
        self._ranges = projection.ranges
        self._ranges_dirty = False
        self._manual_ranges = False
        self.pending = False
        # Compare only immutable metadata. Qt is visited only for changed
        # blocks; block text is neither fetched nor scanned on delivery.
        with QSignalBlocker(self.editor):
            for number, ranges in enumerate(projection.blocks):
                if manual or number >= len(old) or old[number] != ranges:
                    self.rehighlightBlock(document.findBlockByNumber(number))
        return True

    def update_model(self, document) -> None:
        """Synchronous compatibility for explicit previews/nonbackground tabs."""
        self.apply_projection(derive_highlighting(document))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        block = self.currentBlock()
        block_start = block.position()
        block_end = block_start + block.length() - 1
        for start, end, kind in self.block_ranges(block_start, block_end):
            if end > block_start and start < block_end:
                self.setFormat(max(0, start - block_start),
                               min(end, block_end) - max(start, block_start), self._formats[kind])
