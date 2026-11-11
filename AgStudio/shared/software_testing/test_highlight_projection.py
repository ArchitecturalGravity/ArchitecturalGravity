"""Worker projection and incremental Qt highlighting regression coverage."""
import importlib.util
import multiprocessing
import os
import pickle
from concurrent.futures import ProcessPoolExecutor
from dataclasses import FrozenInstanceError
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from AgStudio.shared.highlight_projection import derive_highlighting
from AgStudio.shared.highlighting import highlight_tokens
from AgStudio.shared.lint import analyze


def _projection_process_probe(snapshot):
    import sys
    projection = derive_highlighting(snapshot)
    return projection, any(name.startswith('PySide6') for name in sys.modules)


class HighlightProjectionTests(unittest.TestCase):
    def test_utf16_normalized_offsets_and_multiline_blocks(self):
        source = '[🌏]: value\r\n=> Read [🌏]\rTask: "quoted"\n'
        document = analyze(source).document
        projection = derive_highlighting(document)
        def offset(index):
            return len(source[:index].replace('\r\n', '\n').replace('\r', '\n').encode('utf-16-le')) // 2
        expected = tuple(sorted(((offset(t.span.start), offset(t.span.end), t.role)
                                 for t in highlight_tokens(document)), key=lambda r: (r[0], r[1])))
        self.assertEqual(projection.ranges, expected)
        self.assertEqual(projection, derive_highlighting(analyze(source)))
        self.assertEqual(len(projection.blocks), 4)
        for length, ranges in zip(projection.block_lengths, projection.blocks):
            self.assertTrue(all(0 <= start < end <= length for start, end, _ in ranges))
        self.assertEqual(projection.blocks[-1], ())

    def test_projection_is_immutable_pickleable_and_qt_free_in_spawn(self):
        from AgStudio.shared.analysis_snapshot import freeze_document
        document = analyze('[One]: first\n=> Read [One]\n').document
        projection = derive_highlighting(document)
        with self.assertRaises(FrozenInstanceError):
            projection.source_length = 9
        self.assertEqual(pickle.loads(pickle.dumps(projection)), projection)
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn')) as pool:
            actual, loaded_qt = pool.submit(_projection_process_probe, freeze_document(document)).result(timeout=15)
        self.assertEqual(actual, projection)
        self.assertFalse(loaded_qt)

    def test_empty_document_has_one_empty_block(self):
        projection = derive_highlighting(analyze(''))
        self.assertEqual(projection.blocks, ((),))
        self.assertEqual(projection.block_lengths, (0,))
        self.assertEqual(projection.source_length, 0)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class IncrementalHighlighterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtWidgets import QPlainTextEdit
        from AgStudio.gui.syntax_highlighter import _CoreHighlighter
        self.editor = QPlainTextEdit()
        self.highlighter = _CoreHighlighter(self.editor)
        self.app.processEvents()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def populate(self, source):
        self.editor.setPlainText(source)
        self.app.processEvents()
        projection = derive_highlighting(analyze(source))
        self.assertTrue(self.highlighter.apply_projection(projection))
        return projection

    def replace(self, start, end, text):
        from PySide6.QtGui import QTextCursor
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)

    def assert_cached_positions(self):
        document = self.editor.document()
        h = self.highlighter
        self.assertEqual(len(h._blocks), document.blockCount())
        self.assertEqual(len(h._lengths), document.blockCount())
        for number, ranges in enumerate(h._blocks):
            block = document.findBlockByNumber(number)
            self.assertEqual(h._lengths[number], block.length() - 1)
            self.assertTrue(all(0 <= a < b <= block.length() - 1 for a, b, _ in ranges), ranges)

    def test_unchanged_delivery_does_not_rehighlight_or_emit_source_edit(self):
        from PySide6.QtTest import QSignalSpy
        projection = self.populate('[One]: first\nordinary text\n[Two]: second')
        spy = QSignalSpy(self.editor.textChanged)
        with mock.patch.object(self.highlighter, 'rehighlightBlock') as block, mock.patch.object(self.highlighter, 'rehighlight') as full:
            self.assertTrue(self.highlighter.apply_projection(projection))
            self.highlighter.invalidate()
        block.assert_not_called()
        full.assert_not_called()
        self.assertEqual(spy.count(), 0)
        self.assertEqual(self.highlighter.ranges, projection.ranges)
        self.assertTrue(self.highlighter.pending)

    def test_mismatched_document_shape_is_rejected_without_clearing_styles(self):
        projection = self.populate('[One]: first\n[Two]: second')
        self.highlighter.invalidate()
        with mock.patch.object(self.highlighter, 'rehighlightBlock') as block:
            self.assertFalse(self.highlighter.apply_projection(derive_highlighting(analyze(''))))
        block.assert_not_called()
        self.assertEqual(self.highlighter.ranges, projection.ranges)
        self.assertTrue(self.highlighter.pending)

    def test_worker_delivery_applies_only_changed_block_without_source_cascade(self):
        from PySide6.QtTest import QSignalSpy
        self.populate('[One]: first\nplain text\n[Two]: second')
        self.replace(1, 4, 'New')
        self.highlighter.invalidate()
        projection = derive_highlighting(analyze(self.editor.toPlainText()))
        spy = QSignalSpy(self.editor.textChanged)
        h = self.highlighter
        with mock.patch.object(h, 'rehighlightBlock', wraps=h.rehighlightBlock) as block, mock.patch.object(h, 'rehighlight') as full:
            h.apply_projection(projection)
        self.assertEqual([call.args[0].blockNumber() for call in block.call_args_list], [0])
        full.assert_not_called()
        self.assertEqual(spy.count(), 0)
        self.assertFalse(h.pending)
        self.assert_cached_positions()

    def test_insertion_preserves_local_tokens_and_shifts_unaffected_blocks(self):
        self.populate('[One]: first\n[Two]: second\n[Three]: third')
        old = self.highlighter._blocks.copy()
        with mock.patch.object(self.highlighter, 'rehighlight') as full, mock.patch.object(self.editor, 'toPlainText', side_effect=AssertionError('no source scan during edit')):
            self.replace(0, 0, '🌏\nnew line\n')
            self.highlighter.invalidate()
        full.assert_not_called()
        self.assertEqual(self.highlighter._blocks[2:], old)
        self.assertEqual(self.highlighter._blocks[:2], [(), ()])
        self.assert_cached_positions()
        self.assertEqual(self.highlighter.ranges[0][:2], (12, 13))

    def test_deletion_join_maps_suffix_and_discards_intersected_tokens(self):
        self.populate('[One]: first\n[Two]: second\n[Three]: third')
        before = self.highlighter._blocks[2]
        self.replace(5, 18, '')
        self.assertEqual(self.highlighter._blocks[-1], before)
        self.assertEqual(self.highlighter._blocks[0], ((0, 1, 'symbol'), (1, 4, 'symbol_body'), (4, 5, 'symbol'), (5, 6, 'colon')))
        self.assert_cached_positions()

    def test_unicode_insert_delete_undo_redo_and_clear_keep_safe_offsets(self):
        self.populate('[One]: 🌏\n[Two]: second\n[Three]: third')
        self.replace(7, 9, '🌏🌏\n[New]')
        self.assert_cached_positions()
        self.editor.undo()
        self.assert_cached_positions()
        self.editor.redo()
        self.assert_cached_positions()
        self.editor.clear()
        self.assert_cached_positions()
        self.assertEqual(self.highlighter.ranges, ())
        self.populate('[Again]: okay')
        self.assert_cached_positions()

    def test_palette_changes_only_repaint_blocks_using_changed_roles(self):
        from AgStudio.gui.color_schemes import default_scheme
        from PySide6.QtTest import QSignalSpy
        self.populate('[One]: first\nTask: ordinary text\n[Two]: second')
        scheme = default_scheme()
        scheme['symbol']['foreground'] = [3, 5, 7, 200]
        h = self.highlighter
        spy = QSignalSpy(self.editor.textChanged)
        with mock.patch.object(h, 'rehighlightBlock', wraps=h.rehighlightBlock) as block, mock.patch.object(h, 'rehighlight') as full:
            h.apply_color_scheme(scheme)
        self.assertEqual([call.args[0].blockNumber() for call in block.call_args_list], [0, 2])
        full.assert_not_called()
        self.assertEqual(spy.count(), 0)
        self.assertEqual(h._formats['symbol'].foreground().color().getRgb(), (3, 5, 7, 200))

    def test_qt_paragraph_normalization_matches_worker(self):
        for source in ('[A]: one\r\n[B]: 🌏\r[C]: three\n', '[A]: one\u2028[B]: two\u2029[C]: three'):
            self.populate(source)
            self.assert_cached_positions()

    def test_large_delivery_visits_only_the_changed_qt_block(self):
        source = '[Source]: value\n' + '- Read [Source]\n' * 1000
        self.populate(source)
        self.replace(2, 2, 'X')
        projection = derive_highlighting(analyze(self.editor.toPlainText()))
        h = self.highlighter
        with mock.patch.object(h, 'rehighlightBlock', wraps=h.rehighlightBlock) as block:
            self.assertTrue(h.apply_projection(projection))
        self.assertEqual([call.args[0].blockNumber() for call in block.call_args_list], [0])

    def test_repeated_edits_match_safe_interval_mapping_and_qt_formats(self):
        import random
        randomizer = random.Random(124)
        source = '[One]: first\n[Two]: 🌏second\n[Three]: third'
        h = self.highlighter
        def signature(fmt):
            return (fmt.foreground().color().rgba(), fmt.background().color().rgba(),
                    fmt.fontWeight())
        for index in range(200):
            if index % 30 == 0:
                self.populate(source)
            text = self.editor.toPlainText()
            first = randomizer.randrange(len(text) + 1)
            last = randomizer.randrange(first, len(text) + 1) if randomizer.random() < .5 else first
            replacement = randomizer.choice(['X', '\n', '🌏', '', '[Add]', 'a\nb\nc'])
            if first == last and not replacement:
                continue
            start = len(text[:first].encode('utf-16-le')) // 2
            end = len(text[:last].encode('utf-16-le')) // 2
            delta = len(replacement.encode('utf-16-le')) // 2 - (end - start)
            expected = tuple((a, b, role) if b <= start else (a + delta, b + delta, role)
                             for a, b, role in h.ranges if b <= start or a >= end)
            self.replace(start, end, replacement)
            self.assertEqual(h.ranges, expected)
            self.assert_cached_positions()
            for number, ranges in enumerate(h._blocks):
                block = self.editor.document().findBlockByNumber(number)
                wanted = [None] * (block.length() - 1)
                for a, b, role in ranges:
                    wanted[a:b] = [signature(h._formats[role])] * (b - a)
                actual = [None] * len(wanted)
                for span in block.layout().formats():
                    actual[span.start:span.start + span.length] = [signature(span.format)] * span.length
                self.assertEqual(actual, wanted)

    def test_legacy_interval_index_supports_nested_spans(self):
        h = self.highlighter
        h.ranges = ((0, 30, 'literal'), (5, 7, 'symbol'), (20, 25, 'colon'), (30, 32, 'operation'))
        for start, end in ((0, 5), (7, 20), (25, 30), (30, 32), (40, 45)):
            self.assertEqual(tuple(r for r in h.block_ranges(start, end) if r[1] > start and r[0] < end),
                             tuple(r for r in h.ranges if r[1] > start and r[0] < end))


if __name__ == '__main__':
    unittest.main()
