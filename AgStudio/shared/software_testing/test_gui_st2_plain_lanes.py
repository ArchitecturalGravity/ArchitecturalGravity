"""ST2 source spans preserve structural baselines and exact inline identities."""
import importlib.util
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class PlainPositionalSegmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_map(self, source, *, width=420, height=480, wrap=False):
        from PySide6.QtWidgets import QPlainTextEdit
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import DocumentMap
        from AgStudio.gui.inference_heat import compute_heat
        from AgStudio.shared.lint import analyze
        editor = SourceEditor()
        editor.resize(200 if wrap else 650, height)
        if wrap:
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        editor.setPlainText(source)
        editor.show()
        view = DocumentMap(editor, mode='semantic_triad_2')
        view.resize(width, height)
        view.show()
        self.app.processEvents()
        analysis = analyze(source)
        heat = compute_heat(analysis.tree, analysis.semantics, mode='semantic_triad_2')
        view.set_model(analysis.document, analysis.tree, heat=heat)
        view.rebuild()
        self.addCleanup(editor.deleteLater)
        self.addCleanup(editor.close)
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        return editor, view

    def assert_exact_colors(self, view, segments):
        from AgStudio.gui.inference_heat import heat_rgb
        for segment in segments:
            if segment.object is None:
                self.assertEqual(segment.color, (128, 128, 128))
            else:
                value = view.heat.final_values[segment.object]
                self.assertEqual(segment.color, heat_rgb(value, *view._heat_range))

    def assert_source_segments(self, view, row):
        segments = view.position_segments(row)
        self.assertTrue(segments)
        for segment in segments:
            self.assertAlmostEqual(segment.rect.top(), row.top)
            self.assertAlmostEqual(segment.rect.height(), row.height)
            self.assertGreater(segment.rect.width(), 0)
        self.assertAlmostEqual(segments[0].rect.left(), row.left)
        self.assertAlmostEqual(segments[-1].rect.right(), row.right)
        for left, right in zip(segments, segments[1:]):
            self.assertAlmostEqual(left.rect.right(), right.rect.left())
        self.assert_exact_colors(view, segments)

    def test_plain_references_own_only_their_actual_token_spans(self):
        source = '[Zed]: alpha\n[Able]: beta\nTask:\n  before [Zed] between [Able] after\n'
        _, view = self.make_map(source)
        row = view.rows[-1]
        self.assert_source_segments(view, row)
        segments = view.position_segments(row)
        for event in view.heat.position_snapshot.semantic_positions:
            if event.kind == 'reference_start':
                matching = [item for item in segments
                            if item.position == event.position and item.object in event.objects]
                self.assertTrue(matching)
                self.assertTrue(all(item.rect.height() == row.height for item in matching))
        self.assertEqual([item.object for item in segments],
                         ['@element:2', 'Zed', '@element:2', 'Able', '@element:2'])

    def test_plain_alias_has_final_color_while_underlying_availability_remains_causal(self):
        source = '[A]: alpha\nTask:\n  transform [A] AS [Codes]\n  output [Codes]\n'
        _, view = self.make_map(source)
        row = view.rows[2]
        self.assert_source_segments(view, row)
        end = source.index('[Codes]') + len('[Codes]')
        evaluator = view.heat.position_evaluator
        self.assertEqual(dict(evaluator.values_at(end - 1))['Codes'], 0)
        self.assertGreater(dict(evaluator.values_at(end))['Codes'], 0)
        # Exact source boundaries are retained even though display values use N.
        following = [item for row in view.rows for item in view.position_segments(row)
                     if item.position >= end]
        self.assertTrue(following)
        output = view.position_segments(view.rows[3])
        self.assertTrue(any(item.object == 'Codes' and item.position >= end
                            and dict(evaluator.values_at(item.position))['Codes'] > 0
                            for item in output))
        self.assert_exact_colors(view, output)
        self.assertTrue(any(item.object == 'A' and item.position < end
                            for item in view.position_segments(row)))
        alias_segments = [item for item in view.position_segments(row)
                          if item.object == 'Codes' and item.position < end]
        self.assertTrue(alias_segments)
        self.assertTrue(all(item.color != (0, 0, 255) for item in alias_segments))

    def test_nested_plain_section_preserves_named_context_and_local_reference_behavior(self):
        source = ('[B]: beta\n[A]:\n  Named words\n  Plain:\n'
                  '    ordinary [B] tail\nTask:\n  ordinary [A] tail\n')
        _, view = self.make_map(source)
        nested = view.rows[4]
        self.assert_source_segments(view, nested)
        self.assertEqual({item.object for item in view.position_segments(nested)}, {'@element:3', 'B'})
        self.assert_source_segments(view, view.rows[-1])
        self.assertTrue(any(item.object == 'A'
                            for item in view.position_segments(view.rows[-1])))

    def test_wrapped_unicode_plain_rows_keep_source_order_and_exact_values(self):
        source = ('[Zed]: alpha\n[Able]: beta\nTask:\n  😀\tordinary words '
                  '[Zed] then more ordinary words e\u0301 [Able] final words\n')
        _, view = self.make_map(source, wrap=True)
        start = source.index('  😀')
        rows = [row for row in view.rows if row.start >= view._source_index.display(start)]
        self.assertGreater(len(rows), 1)
        for row in rows:
            self.assert_source_segments(view, row)
            segments = view.position_segments(row)
            self.assertEqual([item.position for item in segments],
                             sorted(item.position for item in segments))
            self.assertTrue(all(
                view._source_index.source(row.start) <= item.position
                <= view._source_index.source(row.end)
                for item in segments
            ))

    def test_compression_and_zoom_preserve_exact_evidence(self):
        source = '[A]: alpha\n[B]: beta\nTask:\n' + '  before [A] then [B] after\n' * 500
        _, view = self.make_map(source, width=100, height=100)
        evidence = dict(view.heat.position_values)
        events = view.heat.position_snapshot.semantic_positions
        self.assertLess(view.rows[-1].height * view.scale, 1)
        # Vertical compression can discard displayed rows, never source ownership
        # from the span geometry or detached event evidence.
        for row in view.rows[-5:]:
            self.assert_source_segments(view, row)
        view.grab()
        view.scale = 1.0
        for row in view.rows[3:]:
            self.assert_source_segments(view, row)
        self.assertEqual(view.heat.position_values, evidence)
        self.assertEqual(view.heat.position_snapshot.semantic_positions, events)
        view.invalidate(7)
        self.assertTrue(view.stale)
        self.assertIsNone(view.heat)

    def test_plain_document_without_declared_symbols_uses_structural_baseline(self):
        _, view = self.make_map('Task:\n  ordinary words only\n')
        for row in view.rows:
            self.assert_source_segments(view, row)
            self.assertTrue(all(item.object == '@element:0' and item.color == (255, 0, 0)
                                for item in view.position_segments(row)))


if __name__ == '__main__':
    unittest.main()
