"""Validated source permutations retain display colors without retaining evidence."""
from contextlib import ExitStack
import importlib.util
import math
import unittest
from unittest.mock import patch

from . import test_gui_block_drag as drag_helpers


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class MoveColorTests(unittest.TestCase):
    # Bind helpers rather than inheriting the drag suite and running it twice.
    setUpClass = classmethod(drag_helpers.BlockDragTests.setUpClass.__func__)
    make_tab = drag_helpers.BlockDragTests.make_tab
    settle = drag_helpers.BlockDragTests.settle
    point = drag_helpers.BlockDragTests.point
    edit_tab = drag_helpers.BlockDragTests.edit_tab
    assert_clean = drag_helpers.BlockDragTests.assert_clean
    settle_edit = drag_helpers.BlockDragTests.settle_edit
    mouse = drag_helpers.BlockDragTests.mouse
    press_block = drag_helpers.BlockDragTests.press_block
    press_owner = drag_helpers.BlockDragTests.press_owner
    drag_to = drag_helpers.BlockDragTests.drag_to
    drag_from_press = drag_helpers.BlockDragTests.drag_from_press
    assert_selected_label = drag_helpers.BlockDragTests.assert_selected_label

    SOURCE = ('[Seed]: seed\n[Left]:\n- [Seed] [Seed]\n'
              '[Move]:\n- ordinary words\n[Right]:\n- [Seed]\n')

    def colored_tab(self, source, mode, **kwargs):
        tab = self.edit_tab(source, inference_mode=mode, **kwargs)
        # Keep individual source characters wide enough to inspect real pixels.
        tab.resize(1450, 800)
        tab.document_map.setFixedWidth(450)
        self.app.processEvents()
        tab.document_map.rebuild()
        return tab

    def image(self, view):
        from PySide6.QtCore import QRectF
        with ExitStack() as stack:
            for method in ('_paint_edit_dividers', '_paint_edit_arrows', '_paint_drag'):
                stack.enter_context(patch.object(view, method))
            stack.enter_context(patch.object(view, 'mapped_viewport',
                                             return_value=QRectF(-10, -10, 1, 1)))
            return view.grab().toImage()

    def source_pixel(self, view, source, position, image):
        """Pick a character's center using Qt UTF-16 layout, not Python offsets."""
        from AgStudio.gui.document_map import SourcePositionIndex
        index = SourcePositionIndex(source)
        first, last = index.display(position), index.display(position + 1)
        row = next(row for row in view.rows if row.start <= first < row.end)
        block, line = view._position_line(row)
        left = line.cursorToX(first - block.position())[0]
        right = line.cursorToX(last - block.position())[0]
        origin, dpr = view.map_origin(), image.devicePixelRatio()
        x = math.floor((origin.x() + (left + right) / 2 * view.horizontal_scale) * dpr)
        y = math.floor((origin.y() + (row.top + row.height / 2) * view.scale) * dpr)
        self.assertTrue(0 <= x < image.width() and 0 <= y < image.height(),
                        (position, source[position], x, y))
        return image.pixelColor(x, y).getRgb()[:3], row

    def pixels(self, tab):
        view, source = tab.document_map, tab.source
        image = self.image(view)
        # Letters plus non-BMP characters exercise UTF-16/source conversion.
        positions = [i for i, char in enumerate(source)
                     if char.isalnum() or ord(char) > 0xffff]
        result = {position: self.source_pixel(view, source, position, image)[0]
                  for position in positions}
        self.assertGreater(len(result), 10)
        return result

    def assert_pixels(self, tab, expected, *, selected=False):
        from AgStudio.gui.document_map import EDIT_SELECTED_COLOR, PENDING_COLOR
        view = tab.document_map
        image = self.image(view)
        selected_count = 0
        for position, color in expected.items():
            actual, row = self.source_pixel(view, tab.source, position, image)
            if selected and view._owner_selected(row.owner):
                color = EDIT_SELECTED_COLOR
                selected_count += 1
            with self.subTest(mode=view.mode, position=position,
                              character=tab.source[position]):
                self.assertNotEqual(color, PENDING_COLOR)
                self.assertEqual(actual, color)
        if selected:
            self.assertGreater(selected_count, 0)

    def spans(self, view):
        """Exact source intervals keep their colors even when node IDs change."""
        result = {}
        for row in view.rows:
            intervals = view._position_intervals(row)
            segments = view.position_segments(row)
            self.assertEqual(len(intervals), len(segments))
            for interval, segment in zip(intervals, segments):
                self.assertEqual(segment.position, interval.start)
                result[interval.start, interval.end] = segment.color
        self.assertTrue(result)
        return result

    def map_spans(self, spans, plan):
        from AgStudio.shared.recognition import SourceSpan
        result = {}
        for (start, end), color in spans.items():
            span = plan.offset_map.span(SourceSpan(start, end))
            result[span.start, span.end] = color
        return result

    def move(self, tab, label, destination, *, owner=None):
        view = tab.document_map
        if owner is None:
            target = self.drag_to(tab, label, destination)
        else:
            target = self.drag_from_press(tab, self.press_owner(tab, owner), destination)
        plan = view._drag_plan
        self.assertIsNotNone(plan)
        self.assertNotEqual(plan.source, tab.source)
        self.mouse(view, 'release', target)
        self.assertEqual(tab.source, plan.source)
        self.settle_edit(tab)
        self.assertIsNone(view.heat)
        self.assertFalse(tab.graph.enabled)
        return plan

    def test_valid_drop_preserves_pixels_then_deselection_reveals_moved_colors(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.colored_tab(self.SOURCE, mode)
                before = self.pixels(tab)
                self.assertGreater(len(set(before.values())), 1)
                with patch.object(tab.graph, '_schedule') as schedule:
                    plan = self.move(tab, '[Move]', 0)
                    expected = {plan.offset_map(position): color
                                for position, color in before.items()}
                    self.assert_selected_label(tab, '[Move]')
                    self.assert_pixels(tab, expected, selected=True)
                    tab.document_map._clear_edit_selection()
                    self.assert_pixels(tab, expected)
                    # A geometry-only rebuild must not clear the detached colors.
                    tab.document_map.resize(360, 700)
                    tab.document_map.rebuild()
                    self.assert_pixels(tab, expected)
                    schedule.assert_not_called()

    def test_successive_moves_undo_and_redo_follow_exact_color_history(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.colored_tab(self.SOURCE, mode)
                states = [(tab.source, self.pixels(tab))]
                with patch.object(tab.graph, '_schedule') as schedule:
                    for label, destination in (('[Move]', 0), ('[Right]', '[Left]')):
                        offset = (tab.source.index(destination)
                                  if isinstance(destination, str) else destination)
                        plan = self.move(tab, label, offset)
                        expected = {plan.offset_map(position): color
                                    for position, color in states[-1][1].items()}
                        self.assert_pixels(tab, expected, selected=True)
                        tab.document_map._clear_edit_selection()
                        self.assert_pixels(tab, expected)
                        states.append((tab.source, expected))
                    for source, expected in reversed(states[:-1]):
                        tab.editor.undo()
                        self.settle_edit(tab)
                        self.assertEqual(tab.source, source)
                        self.assertIsNone(tab.document_map.heat)
                        tab.document_map._clear_edit_selection()
                        self.assert_pixels(tab, expected)
                    self.assert_clean(tab, self.SOURCE)
                    for source, expected in states[1:]:
                        tab.editor.redo()
                        self.settle_edit(tab)
                        self.assertEqual(tab.source, source)
                        self.assertIsNone(tab.document_map.heat)
                        tab.document_map._clear_edit_selection()
                        self.assert_pixels(tab, expected)
                    schedule.assert_not_called()

    def test_st2_reference_and_body_spans_keep_their_original_colors(self):
        source = ('[A]: alpha seed\n[B]: beta\n'
                  'Task:\n  before [A] between [B] after [A]\n'
                  '[Move]: independent\n')
        tab = self.colored_tab(source, 'semantic_triad_2')
        view = tab.document_map
        before = self.spans(view)
        self.assertGreater(len(set(before.values())), 2)
        # Moving Task itself transfers its interleaved reference/body intervals.
        with patch.object(tab.graph, '_schedule') as schedule:
            plan = self.move(tab, 'Task:', len(source))
            view._clear_edit_selection()
            self.assertEqual(self.spans(view), self.map_spans(before, plan))
            tab.editor.undo()
            self.settle_edit(tab)
            view._clear_edit_selection()
            self.assertEqual(self.spans(view), before)
            tab.editor.redo()
            self.settle_edit(tab)
            view._clear_edit_selection()
            self.assertEqual(self.spans(view), self.map_spans(before, plan))
            schedule.assert_not_called()

    def test_duplicate_nested_declarations_cannot_start_an_edit_drag(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        source = ('[Base]: value\n[Root]:\n  [Base]:\n  - first\n'
                  '  Notes:\n  - prose [Base]\n  [Base]:\n  - second\n[End]: done\n')
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.colored_tab(source, mode)
                view = tab.document_map
                before = self.pixels(tab)
                old_spans = self.spans(view) if mode == 'semantic_triad_2' else None
                start = source.index('  [Base]:')
                owner = next(node.id for node in view._tree.nodes if node.span.start == start)
                # Invalid repeated instantiations cannot advertise draggable regions.
                self.assertNotIn(owner, {region.owner for region in view._edit_regions})
                self.assertEqual(tab.editor.toPlainText(), source)
                self.assert_pixels(tab, before)
                if old_spans is not None:
                    self.assertEqual(self.spans(view), old_spans)

    def test_unicode_bom_and_mixed_endings_preserve_colors_through_move_history(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        prefix = '\ufeffpinned\r\n'
        blocks = ('[A]:\r\n- café 😀\r\n\r\n', '[B]:\n- 東京\n\n',
                  '[C]:\r- τέλος 🦊 [A]\r')
        source = prefix + ''.join(blocks)
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.colored_tab(source, mode)
                view = tab.document_map
                before = self.pixels(tab)
                with patch.object(tab.graph, '_schedule') as schedule:
                    plan = self.move(tab, '[B]', len(prefix))
                    expected = {plan.offset_map(position): color
                                for position, color in before.items()}
                    self.assertEqual(tab.source.encode('utf-8'),
                                     (prefix + blocks[1] + blocks[0] + blocks[2]).encode('utf-8'))
                    view._clear_edit_selection()
                    self.assert_pixels(tab, expected)
                    tab.editor.undo()
                    self.settle_edit(tab)
                    view._clear_edit_selection()
                    self.assertEqual(tab.source.encode('utf-8'), source.encode('utf-8'))
                    self.assert_pixels(tab, before)
                    tab.editor.redo()
                    self.settle_edit(tab)
                    view._clear_edit_selection()
                    self.assert_pixels(tab, expected)
                    schedule.assert_not_called()

    def test_cancel_and_invalid_drop_leave_retained_colors_unchanged(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.colored_tab(self.SOURCE, mode)
                view = tab.document_map
                with patch.object(tab.graph, '_schedule') as schedule:
                    self.move(tab, '[Move]', 0)
                    view._clear_edit_selection()
                    expected_source, expected = tab.source, self.pixels(tab)
                    undo_steps = tab.editor.document().availableUndoSteps()
                    press = self.press_block(tab, '[Move]')
                    selected = self.image(view)
                    target = self.drag_from_press(tab, press, len(tab.source))
                    self.assertIsNotNone(view._drag_plan)
                    view.cancel_drag()
                    self.mouse(view, 'release', target)
                    self.assertEqual(self.image(view), selected)
                    target = self.drag_to(tab, '[Right]', 0)
                    self.assertIsNone(view._drag_plan)  # Its [Seed] must stay prior.
                    self.mouse(view, 'release', target)
                    view._clear_edit_selection()
                    self.assertEqual(tab.source, expected_source)
                    self.assertEqual(tab.editor.document().availableUndoSteps(), undo_steps)
                    self.assert_pixels(tab, expected)
                    self.assertIsNone(view.heat)
                    schedule.assert_not_called()

    def test_ordinary_typing_invalidates_retained_palette_without_rescoring(self):
        from AgStudio.gui.document_map import PENDING_COLOR
        from AgStudio.gui.inference_heat import MODE_LABELS
        from PySide6.QtGui import QTextCursor
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.colored_tab(self.SOURCE, mode)
                view = tab.document_map
                with patch.object(tab.graph, '_schedule') as schedule:
                    self.move(tab, '[Move]', 0)
                    view._clear_edit_selection()
                    self.assertGreater(len(set(self.pixels(tab).values())), 1)
                    cursor = tab.editor.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    tab.editor.setTextCursor(cursor)
                    tab.editor.insertPlainText('ordinary typing\n')
                    self.settle_edit(tab)
                    self.assertIsNone(view.heat)
                    self.assertIsNone(view.selected_owner)
                    self.assertEqual(set(self.pixels(tab).values()), {PENDING_COLOR})
                    self.assertFalse(tab.graph.enabled)
                    schedule.assert_not_called()

    def test_background_moves_retain_pending_pixels_and_complete_undo_redo_history(self):
        from AgStudio.gui.document_map import PENDING_COLOR
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.colored_tab(self.SOURCE, mode, background=True)
                view = tab.document_map
                self.assertIsNotNone(tab.controller)
                before = self.pixels(tab)
                states = [(tab.source, before)]
                displayed_colors = dict(view._display_colors)
                displayed_rows = view.rows
                displayed_frame = view._position_frame.copy()
                # Keep the real parser pending deterministically while a resize
                # tries to rebuild with the old frame and no current document.
                delay = tab.controller.delay_ms
                tab.controller.delay_ms = 60000
                with patch.object(tab.graph, '_schedule') as schedule:
                    target = self.drag_to(tab, '[Move]', 0)
                    plan = view._drag_plan
                    self.assertIsNotNone(plan)
                    self.mouse(view, 'release', target)
                    self.assertIsNone(view._document)
                    self.assertIsNone(view.heat)
                    tab.resize(tab.width() + 1, tab.height() + 1)
                    view.rebuild()
                    self.assertEqual(view._display_colors, displayed_colors)
                    self.assertEqual(view.rows, displayed_rows)
                    self.assertEqual(view._position_frame, displayed_frame)
                    image = self.image(view)
                    visible_colors = {image.pixelColor(x, y).getRgb()[:3]
                                      for x in range(0, image.width(), 3)
                                      for y in range(0, image.height(), 3)}
                    self.assertNotIn(PENDING_COLOR, visible_colors)
                    self.assertGreater(len(visible_colors.intersection(before.values())), 1)
                    tab.controller.timer.stop()
                    tab.controller.delay_ms = delay
                    tab.controller._dispatch()
                    self.settle_edit(tab)
                    expected = {plan.offset_map(position): color
                                for position, color in before.items()}
                    self.assert_pixels(tab, expected, selected=True)
                    view._clear_edit_selection()
                    self.assert_pixels(tab, expected)
                    states.append((tab.source, expected))
                    plan = self.move(tab, '[Right]', tab.source.index('[Left]'))
                    expected = {plan.offset_map(position): color
                                for position, color in expected.items()}
                    view._clear_edit_selection()
                    self.assert_pixels(tab, expected)
                    states.append((tab.source, expected))
                    for source, expected in reversed(states[:-1]):
                        tab.editor.undo()
                        self.settle_edit(tab)
                        view._clear_edit_selection()
                        self.assertEqual(tab.source, source)
                        self.assert_pixels(tab, expected)
                    for source, expected in states[1:]:
                        tab.editor.redo()
                        self.settle_edit(tab)
                        view._clear_edit_selection()
                        self.assertEqual(tab.source, source)
                        self.assert_pixels(tab, expected)
                    self.assertIsNone(view.heat)
                    self.assertFalse(tab.graph.enabled)
                    schedule.assert_not_called()

    def test_undo_branch_and_identical_source_paste_cannot_reuse_abandoned_colors(self):
        from AgStudio.gui.document_map import PENDING_COLOR
        from AgStudio.gui.inference_heat import MODE_LABELS
        from PySide6.QtGui import QTextCursor
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.colored_tab(self.SOURCE, mode)
                view = tab.document_map
                original = self.pixels(tab)
                with patch.object(tab.graph, '_schedule') as schedule:
                    first = self.move(tab, '[Move]', 0)
                    first_colors = {first.offset_map(position): color
                                    for position, color in original.items()}
                    self.move(tab, '[Right]', tab.source.index('[Left]'))
                    abandoned_source = tab.source
                    tab.editor.undo()
                    self.settle_edit(tab)
                    view._clear_edit_selection()
                    self.assertEqual(tab.source, first.source)
                    self.assert_pixels(tab, first_colors)
                    branch = self.move(tab, '[Move]', len(tab.source))
                    branch_colors = {branch.offset_map(position): color
                                     for position, color in first_colors.items()}
                    view._clear_edit_selection()
                    self.assertNotEqual(tab.source, abandoned_source)
                    self.assertFalse(tab.editor.document().isRedoAvailable())
                    self.assert_pixels(tab, branch_colors)
                    tab.editor.undo()
                    self.settle_edit(tab)
                    view._clear_edit_selection()
                    self.assert_pixels(tab, first_colors)
                    tab.editor.redo()
                    self.settle_edit(tab)
                    view._clear_edit_selection()
                    self.assert_pixels(tab, branch_colors)
                    # Pasting a previously colored source is an ordinary text
                    # command, not permission to reuse its abandoned palette.
                    cursor = QTextCursor(tab.editor.document())
                    cursor.beginEditBlock()
                    cursor.select(QTextCursor.SelectionType.Document)
                    cursor.insertText(abandoned_source)
                    cursor.endEditBlock()
                    self.settle_edit(tab)
                    self.assertEqual(tab.source, abandoned_source)
                    self.assertIsNone(view.heat)
                    self.assertEqual(set(self.pixels(tab).values()), {PENDING_COLOR})
                    # Its undo still restores the actual preceding branch.
                    tab.editor.undo()
                    self.settle_edit(tab)
                    view._clear_edit_selection()
                    self.assertEqual(tab.source, branch.source)
                    self.assert_pixels(tab, branch_colors)
                    tab.editor.redo()
                    self.settle_edit(tab)
                    self.assertEqual(set(self.pixels(tab).values()), {PENDING_COLOR})
                    schedule.assert_not_called()

    def test_fresh_scoring_replaces_frozen_colors_for_the_next_edit_move(self):
        # Semantic baselines depend on source locality, so a real rescore after
        # the first move deliberately produces colors different from its copy.
        for mode in ('semantic_triad_1', 'semantic_triad_2'):
            with self.subTest(mode=mode):
                tab = self.colored_tab(self.SOURCE, mode, background=True)
                view = tab.document_map
                original = self.pixels(tab)
                with patch.object(tab.graph, '_schedule') as schedule:
                    first = self.move(tab, '[Move]', 0)
                    frozen = {first.offset_map(position): color
                              for position, color in original.items()}
                    view._clear_edit_selection()
                    self.assert_pixels(tab, frozen)
                    schedule.assert_not_called()
                tab.map_title.click()
                self.assertFalse(view.edit_mode)
                self.settle(tab)
                view.rebuild()
                self.assertIsNotNone(view.heat)
                fresh = self.pixels(tab)
                self.assertNotEqual(fresh, frozen)
                tab.map_title.click()
                self.assertTrue(view.edit_mode)
                view.rebuild()
                self.assert_pixels(tab, fresh)
                with patch.object(tab.graph, '_schedule') as schedule:
                    second = self.move(tab, '[Right]', tab.source.index('[Left]'))
                    expected = {second.offset_map(position): color
                                for position, color in fresh.items()}
                    self.assert_pixels(tab, expected, selected=True)
                    view._clear_edit_selection()
                    self.assert_pixels(tab, expected)
                    tab.editor.undo()
                    self.settle_edit(tab)
                    view._clear_edit_selection()
                    self.assert_pixels(tab, fresh)
                    tab.editor.redo()
                    self.settle_edit(tab)
                    view._clear_edit_selection()
                    self.assert_pixels(tab, expected)
                    schedule.assert_not_called()
