"""Constrained Infer Edit drags are previews until a lossless, legal release."""
import importlib.util
import time
import unittest
from unittest.mock import Mock, patch

from . import test_gui_inference_map as inference_helpers


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class BlockDragTests(unittest.TestCase):
    setUpClass = classmethod(inference_helpers.InferenceMapTests.setUpClass.__func__)
    make_tab = inference_helpers.InferenceMapTests.make_tab
    settle = inference_helpers.InferenceMapTests.settle
    point = inference_helpers.InferenceMapTests.point

    def edit_tab(self, source, **kwargs):
        tab = self.make_tab(source, **kwargs)
        tab.map_title.click()
        tab.document_map.rebuild()
        self.assertTrue(tab.document_map.edit_mode)
        self.assertFalse(tab.graph.enabled)
        self.assert_clean(tab, source)
        return tab

    def assert_clean(self, tab, source):
        self.assertEqual(tab.source, source)
        self.assertFalse(tab.dirty)
        self.assertFalse(tab.editor.document().isModified())
        self.assertFalse(tab.editor.document().isUndoAvailable())

    def settle_edit(self, tab):
        from PySide6.QtTest import QTest
        view = tab.document_map
        end = time.monotonic() + 8
        while time.monotonic() < end:
            if (view._document is not None and view._document.source == tab.source
                    and view._model_revision == view._source_revision
                    and not view._timer.isActive()):
                break
            QTest.qWait(20)
        self.assertIsNotNone(view._document)
        self.assertEqual(view._document.source, tab.source)
        self.assertEqual(view._model_revision, view._source_revision)
        view.rebuild()

    def mouse(self, view, kind, point):
        """Send real Qt events with precise positions and held-button state."""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        types = {'press': QEvent.Type.MouseButtonPress,
                 'move': QEvent.Type.MouseMove,
                 'release': QEvent.Type.MouseButtonRelease}
        button = Qt.MouseButton.NoButton if kind == 'move' else Qt.MouseButton.LeftButton
        buttons = Qt.MouseButton.NoButton if kind == 'release' else Qt.MouseButton.LeftButton
        point = QPointF(point)
        event = QMouseEvent(types[kind], point, point, button, buttons,
                            Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(view, event)

    def press_block(self, tab, label, *, x=None):
        view = tab.document_map
        start = tab.source.index(label)
        node = next(node for node in view._tree.nodes if node.span.start == start)
        return self.press_owner(tab, view._edit_owners[node.id], x=x)

    def press_owner(self, tab, owner, *, x=None):
        from PySide6.QtCore import QPointF
        view = tab.document_map
        region = next(region for region in view._edit_regions if region.owner == owner)
        point = QPointF(view.width() - 2 if x is None else x,
                        view.map_origin().y() + (region.top + region.bottom) / 2 * view.scale)
        self.assertTrue(view.rect().contains(point.toPoint()), (owner, point))
        self.mouse(view, 'press', point)
        self.assertEqual(view.selected_owner, owner)
        self.assertIsNotNone(view._drag_press)
        return point

    def drag_to(self, tab, label, destination, *, x=None):
        return self.drag_from_press(tab, self.press_block(tab, label, x=x), destination)

    def drag_from_press(self, tab, press, destination):
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication
        view = tab.document_map
        target = QPointF(press.x(), view._boundary_y(destination))
        # An adjacent/no-op boundary may be closer than the drag threshold.
        self.mouse(view, 'move', QPointF(press.x(), press.y() + QApplication.startDragDistance() + 1))
        self.mouse(view, 'move', target)
        self.assertTrue(view._drag_active)
        return target

    def assert_selected_label(self, tab, label):
        view = tab.document_map
        self.assertIsNotNone(view.selected_owner)
        node = view._tree.nodes[view.selected_owner]
        self.assertTrue(node.span.extract(tab.source).startswith(label),
                        node.span.extract(tab.source))

    def test_click_and_horizontal_motion_only_select_without_editing(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication
        source = '[A]:\n- alpha\n[B]:\n- beta\n'
        tab = self.edit_tab(source)
        view = tab.document_map
        cursor = tab.editor.textCursor().position()
        with patch.object(tab.graph, '_schedule') as schedule:
            for x in (0, view.width() - 1):
                press = self.press_block(tab, '[A]', x=x)
                point = QPointF(view.width() - 1 - x,
                                press.y() + QApplication.startDragDistance() - 1)
                self.mouse(view, 'move', point)
                self.assertFalse(view._drag_active)
                self.assertIsNone(view._drag_plan)
                self.mouse(view, 'release', point)
                self.assert_selected_label(tab, '[A]')
                self.assert_clean(tab, source)
            schedule.assert_not_called()
        self.assertEqual(tab.editor.textCursor().position(), cursor)

    def test_vertical_threshold_starts_preview_and_never_mutates_early(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication
        source = '[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- gamma\n'
        tab = self.edit_tab(source)
        view = tab.document_map
        heat = view.heat
        press = self.press_block(tab, '[B]')
        with patch.object(tab.graph, '_schedule') as schedule:
            self.mouse(view, 'move', QPointF(press.x(), press.y() - QApplication.startDragDistance()))
            self.assertTrue(view._drag_active)
            self.assertFalse(view.drag_rect().isEmpty())
            self.assertEqual(view.drag_rect().left(), 0)
            self.assertEqual(view.drag_rect().width(), view.width())
            self.assert_clean(tab, source)
            self.assertIs(view.heat, heat)
            schedule.assert_not_called()
        view.cancel_drag()
        self.assert_clean(tab, source)

    def test_retained_colors_hide_drag_source_and_restore_on_cancel_all_modes(self):
        from PySide6.QtCore import QRectF
        from AgStudio.gui.inference_heat import MODE_LABELS
        from AgStudio.gui.document_map import EDIT_SELECTED_COLOR
        source = '[A]:\n- alpha\n\n[B]:\n- beta\n\n[C]:\n- gamma\n'
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.edit_tab(source, inference_mode=mode)
                view = tab.document_map
                heat = view.heat
                original_colors = {view._tree.nodes[row.owner].span.extract(source):
                                   view.color_for_owner(row.owner).getRgb()[:3] for row in view.rows}
                press = self.press_block(tab, '[B]')
                with patch.object(view, '_paint_drag'), \
                        patch.object(view, '_paint_edit_dividers'), \
                        patch.object(view, '_paint_edit_arrows'), \
                        patch.object(view, 'mapped_viewport', return_value=QRectF(-10, -10, 1, 1)):
                    selected = view.grab().toImage()
                    target = self.drag_from_press(tab, press, len(source))
                    dragging = view.grab().toImage()
                    for row in view.rows:
                        point = self.point(view, row)
                        if view._shape_dragged(row.owner):
                            self.assertEqual(dragging.pixelColor(point).getRgb(),
                                             tuple(tab.editor.color_scheme['editor']['background']))
                            self.assertEqual(selected.pixelColor(point).getRgb()[:3], EDIT_SELECTED_COLOR)
                        else:
                            self.assertEqual(dragging.pixelColor(point), selected.pixelColor(point))
                    view.cancel_drag()
                    self.assertIs(view.heat, heat)
                    self.assertEqual(view.grab().toImage(), selected)
                self.assert_clean(tab, source)
                with patch.object(tab.graph, '_schedule') as schedule:
                    target = self.drag_to(tab, '[B]', len(source))
                    self.assertIsNotNone(view._drag_plan)
                    self.mouse(view, 'release', target)
                    self.settle_edit(tab)
                    self.assertNotEqual(tab.source, source)
                    self.assertIsNone(view.heat)
                    for row in view.rows:
                        original = original_colors[view._tree.nodes[row.owner].span.extract(tab.source)]
                        expected = EDIT_SELECTED_COLOR if view._owner_selected(row.owner) else original
                        self.assertEqual(view.color_for_owner(row.owner).getRgb()[:3], expected)
                    tab.editor.undo()
                    self.settle_edit(tab)
                    self.assertEqual(tab.source, source)
                    self.assertIsNone(view.heat)
                    for row in view.rows:
                        self.assertEqual(view.color_for_owner(row.owner).getRgb()[:3],
                                         original_colors[view._tree.nodes[row.owner].span.extract(source)])
                    self.assertFalse(tab.graph.enabled)
                    schedule.assert_not_called()

    def test_compressed_st2_selection_and_drag_match_winning_pixel_rows(self):
        import math
        from PySide6.QtCore import QRectF
        from AgStudio.gui.document_map import EDIT_SELECTED_COLOR
        source = ('[A]:\n' + '- alpha\n' * 100 + '[B]:\n' + '- beta\n' * 100
                  + '[C]:\n' + '- gamma\n' * 100)
        tab = self.edit_tab(source, inference_mode='semantic_triad_2')
        view = tab.document_map
        view.resize(150, 83)
        view.rebuild()
        press = self.press_block(tab, '[B]')
        with patch.object(view, '_paint_drag'), patch.object(view, '_paint_edit_dividers'), \
                patch.object(view, '_paint_edit_arrows'), \
                patch.object(view, 'mapped_viewport', return_value=QRectF(-10, -10, 1, 1)):
            selected = view.grab().toImage()
            base = view._position_frame.copy()
            # The last source row within each compressed physical pixel wins.
            dpr = base.devicePixelRatio()
            winners = {math.floor((view.map_origin().y() + row.top * view.scale) * dpr): row
                       for row in view.rows}
            self.assertTrue(all(row.height * view.scale * dpr < 1 for row in view.rows))
            self.drag_from_press(tab, press, len(source))
            dragging = view.grab().toImage()
            background = tuple(tab.editor.color_scheme['editor']['background'])
            examined = 0
            for y, row in winners.items():
                if not 0 <= y < base.height():
                    continue
                for x in range(base.width()):
                    original = base.pixelColor(x, y)
                    if not original.alpha():
                        continue
                    if view._shape_dragged(row.owner):
                        self.assertEqual(selected.pixelColor(x, y).getRgb()[:3], EDIT_SELECTED_COLOR)
                        self.assertEqual(dragging.pixelColor(x, y).getRgb(), background)
                        examined += 1
                    else:
                        self.assertEqual(selected.pixelColor(x, y), original)
                        self.assertEqual(dragging.pixelColor(x, y), original)
            self.assertGreater(examined, 100)
            self.assertEqual(view._position_frame, base)
            # The moving preview reuses its raster; no per-pointer span replay.
            with patch.object(view, '_position_commands_for_row', side_effect=AssertionError('replayed edit raster')):
                self.assertEqual(view.grab().toImage(), dragging)
            view.cancel_drag()
            self.assertEqual(view.grab().toImage(), selected)
            view._clear_edit_selection()
            view.grab()
            self.assertEqual(view._position_frame, base)

    def test_multiple_sources_and_dependents_bound_both_drag_directions(self):
        blocks = ('[A]:\n- alpha\n', '[B]:\n- beta\n', '[L]:\n- left\n',
                  '[M]:\n- [A] [B]\n', '[R]:\n- right\n',
                  '[D]:\n- [M]\n', '[E]:\n- [M]\n', '[T]:\n- tail\n')
        source = ''.join(blocks)
        cases = (('[L]', True, (0, 1, 3, 2, 4, 5, 6, 7)),
                 ('[B]', False, None),
                 ('[A]', False, None),
                 ('[D]', True, (0, 1, 2, 4, 3, 5, 6, 7)),
                 ('[E]', False, None),
                 (None, False, None))
        for destination, valid, order in cases:
            with self.subTest(destination=destination, valid=valid):
                tab = self.edit_tab(source)
                view = tab.document_map
                emitted = Mock()
                view.moveRequested.connect(emitted)
                offset = len(source) if destination is None else source.index(destination)
                target = self.drag_to(tab, '[M]', offset)
                self.assertEqual(view._drag_destination, offset)
                self.assertEqual(view._drag_plan is not None, valid)
                self.assert_clean(tab, source)
                self.mouse(view, 'release', target)
                self.assertFalse(view._drag_active)
                if valid:
                    expected = ''.join(blocks[index] for index in order)
                    emitted.assert_called_once()
                    self.assertEqual(tab.source, expected)
                    self.settle_edit(tab)
                    self.assert_selected_label(tab, '[M]')
                    tab.editor.undo()
                    self.assert_clean(tab, source)
                    tab.editor.redo()
                    self.assertEqual(tab.source, expected)
                else:
                    emitted.assert_not_called()
                    self.assert_clean(tab, source)

    def test_first_last_and_same_place_drops_are_lossless_noops(self):
        source = '[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- gamma\n'
        for label, offset in (('[A]', 0), ('[A]', source.index('[B]')),
                              ('[C]', source.index('[C]')), ('[C]', len(source))):
            with self.subTest(label=label, offset=offset):
                tab = self.edit_tab(source)
                emitted = Mock()
                tab.document_map.moveRequested.connect(emitted)
                point = self.drag_to(tab, label, offset)
                self.assertIsNotNone(tab.document_map._drag_plan)
                self.assertEqual(tab.document_map._drag_plan.source, source)
                self.mouse(tab.document_map, 'release', point)
                emitted.assert_not_called()
                self.assert_clean(tab, source)

    def test_legal_marker_is_one_line_and_invalid_overlay_only_two_red_strokes(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication
        from AgStudio.gui.document_map import EDIT_INVALID_COLOR, EDIT_SELECTED_COLOR
        source = '[A]:\n- alpha\n[M]:\n- [A]\n[R]:\n- unrelated\n[D]:\n- [M]\n'
        tab = self.edit_tab(source)
        view = tab.document_map
        cursor = view.cursor().shape()
        with patch.object(view, 'setCursor') as set_cursor:
            point = self.drag_to(tab, '[M]', source.index('[D]'))
            legal = Mock()
            view._paint_drag(legal)
            legal.drawLine.assert_called_once_with(QPointF(0, point.y()), QPointF(view.width(), point.y()))
            self.assertEqual(legal.setPen.call_args.args[0].color().getRgb()[:3], EDIT_SELECTED_COLOR)
            self.mouse(view, 'move', QPointF(point.x(), view._boundary_y(0)))
            self.assertIsNone(view._drag_plan)
            invalid = Mock()
            view._paint_drag(invalid)
            rect = view.drag_rect().adjusted(2, 1, -2, -1)
            self.assertEqual(invalid.drawLine.call_count, 2)
            self.assertEqual(invalid.drawLine.call_args_list[0].args, (rect.topLeft(), rect.bottomRight()))
            self.assertEqual(invalid.drawLine.call_args_list[1].args, (rect.bottomLeft(), rect.topRight()))
            self.assertEqual(invalid.setPen.call_args.args[0].color().getRgb()[:3], EDIT_INVALID_COLOR)
            invalid.drawText.assert_not_called()
            self.assertGreater(rect.width(), view.width() * .9)
            set_cursor.assert_not_called()
        self.assertEqual(view.cursor().shape(), cursor)
        self.assertIsNone(QApplication.overrideCursor())
        self.assert_clean(tab, source)

    def test_drag_hides_tooltip_including_invalid_reason_text(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QHelpEvent
        source = '[A]:\n- alpha\n[B]:\n- [A]\n'
        tab = self.edit_tab(source)
        view = tab.document_map
        point = self.drag_to(tab, '[B]', 0).toPoint()
        self.assertIsNone(view._drag_plan)
        with patch.object(view._tooltip, 'show_text') as show:
            self.app.sendEvent(view, QHelpEvent(QEvent.Type.ToolTip, point, view.mapToGlobal(point)))
            show.assert_not_called()

    def test_escape_from_map_or_editor_cancels_without_undo_or_mutation(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        source = '[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- gamma\n'
        for receiver in ('map', 'editor'):
            with self.subTest(receiver=receiver):
                tab = self.edit_tab(source)
                view = tab.document_map
                target = self.drag_to(tab, '[A]', len(source))
                self.assertIsNotNone(view._drag_plan)
                QTest.keyClick(view if receiver == 'map' else tab.editor, Qt.Key.Key_Escape)
                self.assertFalse(view._drag_active)
                self.assertIsNone(view._drag_press)
                self.assertFalse(view._drag_scroll.isActive())
                self.mouse(view, 'release', target)
                self.assert_clean(tab, source)

    def test_mode_exit_tab_hide_and_map_disable_cancel_active_drag(self):
        source = '[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- gamma\n'
        for action in ('mode', 'tab', 'map'):
            with self.subTest(action=action):
                tab = self.edit_tab(source)
                view = tab.document_map
                emitted = Mock()
                view.moveRequested.connect(emitted)
                point = self.drag_to(tab, '[A]', len(source))
                if action == 'mode':
                    tab.map_title.click()
                elif action == 'tab':
                    tab.hide()
                else:
                    tab.set_map_enabled(False)
                self.assertIsNone(view._drag_press)
                self.assertFalse(view._drag_active)
                self.assertFalse(view._drag_scroll.isActive())
                self.mouse(view, 'release', point)
                emitted.assert_not_called()
                self.assert_clean(tab, source)

    def test_source_edit_invalidates_preview_before_a_late_release(self):
        source = '[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- gamma\n'
        tab = self.edit_tab(source)
        view = tab.document_map
        emitted = Mock()
        view.moveRequested.connect(emitted)
        point = self.drag_to(tab, '[A]', len(source))
        tab.editor.insertPlainText('changed ')
        edited = tab.source
        self.assertNotEqual(edited, source)
        self.assertFalse(view._drag_active)
        self.assertIsNone(view._drag_press)
        self.mouse(view, 'release', point)
        emitted.assert_not_called()
        self.assertEqual(tab.source, edited)
        tab.editor.undo()
        self.assert_clean(tab, source)

    def test_drop_outside_map_cancels_and_readonly_editor_rejects_commit(self):
        from PySide6.QtCore import QPointF
        from AgStudio.gui.document_map import EDIT_INVALID_COLOR
        source = '[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- gamma\n'
        for action in ('left', 'right', 'above', 'below', 'readonly'):
            with self.subTest(action=action):
                tab = self.edit_tab(source)
                view = tab.document_map
                point = self.drag_to(tab, '[A]', len(source))
                self.assertIsNotNone(view._drag_plan)
                if action != 'readonly':
                    outside = {'left': QPointF(-1, point.y()),
                               'right': QPointF(view.width(), point.y()),
                               'above': QPointF(point.x(), -1),
                               'below': QPointF(point.x(), view.height())}[action]
                    # Leaving and re-entering the viewport must update the
                    # feedback immediately, before the release decides to cancel.
                    self.mouse(view, 'move', outside)
                    self.assertIsNone(view._drag_plan)
                    self.assertIsNone(view._drag_destination)
                    painter = Mock()
                    view._paint_drag(painter)
                    self.assertEqual(painter.drawLine.call_count, 2)
                    self.assertEqual(painter.setPen.call_args.args[0].color().getRgb()[:3],
                                     EDIT_INVALID_COLOR)
                    self.mouse(view, 'move', point)
                    self.assertIsNotNone(view._drag_plan)
                    self.mouse(view, 'move', outside)
                    self.assertIsNone(view._drag_plan)
                    point = outside
                else:
                    tab.editor.setReadOnly(True)
                self.mouse(view, 'release', point)
                self.assertFalse(view._drag_active)
                self.assert_clean(tab, source)

    def test_bom_headers_select_the_exact_owner_and_moves_keep_bom_in_all_modes(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        prefix = '\ufeffpinned\n'
        blocks = ('[A]:\n- a\n', '[B]:\n- b\n', '[C]:\n- c\n')
        source = prefix + ''.join(blocks)
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.edit_tab(source, inference_mode=mode)
                view = tab.document_map
                emitted = Mock()
                view.moveRequested.connect(emitted)
                for label, line in (('[A]', 1), ('[B]', 3), ('[C]', 5)):
                    # Find the actual displayed header, independently of the
                    # owner bands. Otherwise shifted BOM ownership can hide.
                    position = tab.editor.document().findBlockByNumber(line).position()
                    row = next(row for row in view.rows if row.start == position)
                    node = next(node for node in view._tree.nodes
                                if node.span.start == source.index(label))
                    point = self.point(view, row)
                    self.mouse(view, 'press', point)
                    self.mouse(view, 'release', point)
                    self.assertEqual(view._edit_owners[row.owner], view._edit_owners[node.id])
                    self.assertEqual(view.selected_owner, view._edit_owners[node.id])
                    self.assert_selected_label(tab, label)
                    self.assert_clean(tab, source)
                for label, destination, expected in (
                        ('[B]', len(source), prefix + blocks[0] + blocks[2] + blocks[1]),
                        ('[C]', len(prefix), prefix + blocks[2] + blocks[0] + blocks[1])):
                    with self.subTest(label=label):
                        emitted.reset_mock()
                        point = self.drag_to(tab, label, destination)
                        self.assertIsNotNone(view._drag_plan)
                        self.mouse(view, 'release', point)
                        emitted.assert_called_once()
                        self.assertEqual(emitted.call_args.args[0], source)
                        self.assertEqual(emitted.call_args.args[1].source, expected)
                        self.assertEqual(tab.source.encode('utf-8'), expected.encode('utf-8'))
                        self.assertTrue(tab.source.startswith(prefix))
                        self.assertEqual(tab.source.count('\ufeff'), 1)
                        self.settle_edit(tab)
                        self.assert_selected_label(tab, label)
                        tab.editor.undo()
                        self.assert_clean(tab, source)
                        tab.editor.redo()
                        self.assertEqual(tab.source.encode('utf-8'), expected.encode('utf-8'))
                        tab.editor.undo()
                        self.assert_clean(tab, source)
                        self.settle_edit(tab)

    def test_interior_bom_character_survives_insert_at_replacement_start(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        source = 'pre\nx\n\ufeffy\nz\n'
        expected = 'pre\n\ufeffy\nx\nz\n'
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.edit_tab(source, inference_mode=mode)
                view = tab.document_map
                point = self.drag_from_press(tab, self.press_owner(tab, 2), 4)
                self.assertIsNotNone(view._drag_plan)
                self.assertEqual(view._drag_plan.source, expected)
                self.mouse(view, 'release', point)
                self.assertEqual(tab.source, expected)
                # Inspect Qt as well as the exact-source sidecar, so missing
                # display characters cannot be hidden by saved source history.
                self.assertEqual(tab.editor.document().toRawText().replace('\u2029', '\n'), expected)
                self.settle_edit(tab)
                tab.editor.undo()
                self.assert_clean(tab, source)
                self.assertEqual(tab.editor.document().toRawText().replace('\u2029', '\n'), source)
                tab.editor.redo()
                self.assertEqual(tab.source, expected)
                self.assertEqual(tab.editor.document().toRawText().replace('\u2029', '\n'), expected)
                tab.editor.undo()
                self.assert_clean(tab, source)

    def test_unicode_mixed_endings_and_blank_separators_survive_undo_redo(self):
        blocks = ('[A]:\r\n- café 😀\r\n\r\n', '[B]:\n- 東京\n\n',
                  '[C]:\r- τέλος 🦊\r')
        source = ''.join(blocks)
        expected = blocks[1] + blocks[0] + blocks[2]
        tab = self.edit_tab(source)
        point = self.drag_to(tab, '[B]', 0)
        self.assertIsNotNone(tab.document_map._drag_plan)
        self.mouse(tab.document_map, 'release', point)
        self.assertEqual(tab.source.encode('utf-8'), expected.encode('utf-8'))
        self.assertTrue(tab.dirty)
        self.settle_edit(tab)
        self.assert_selected_label(tab, '[B]')
        tab.editor.undo()
        self.assert_clean(tab, source)
        self.assertTrue(tab.editor.document().isRedoAvailable())
        tab.editor.redo()
        self.assertEqual(tab.source.encode('utf-8'), expected.encode('utf-8'))
        self.assertFalse(tab.editor.document().isRedoAvailable())
        tab.editor.undo()
        self.assert_clean(tab, source)

    def test_duplicate_display_text_keeps_each_exact_move_in_undo_history_and_edit_branch(self):
        from PySide6.QtGui import QTextCursor
        states = ('x\r\ny\nx\n', 'x\r\nx\ny\n', 'x\ny\nx\r\n', 'x\nx\r\ny\n')
        tab = self.edit_tab(states[0])
        view = tab.document_map
        for index, owner in enumerate((1, 0, 1), start=1):
            point = self.drag_from_press(tab, self.press_owner(tab, owner), len(tab.source))
            self.assertIsNotNone(view._drag_plan)
            self.mouse(view, 'release', point)
            self.assertEqual(tab.source, states[index])
            self.settle_edit(tab)
        # States 1 and 3 have identical Qt text but different exact line endings.
        self.assertEqual(states[1].replace('\r\n', '\n'), states[3].replace('\r\n', '\n'))
        for expected in reversed(states[:-1]):
            tab.editor.undo()
            self.assertEqual(tab.source, expected)
        self.assert_clean(tab, states[0])
        for expected in states[1:]:
            tab.editor.redo()
            self.assertEqual(tab.source, expected)
        self.assertFalse(tab.editor.document().isRedoAvailable())
        tab.editor.undo()
        tab.editor.undo()
        self.assertEqual(tab.source, states[1])
        cursor = tab.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        tab.editor.setTextCursor(cursor)
        tab.editor.insertPlainText('z')
        branch = 'zx\nx\ny\n'  # Ordinary edits retain the document's dominant LF policy.
        self.assertEqual(tab.source, branch)
        self.assertFalse(tab.editor.document().isRedoAvailable())
        tab.editor.undo()
        self.assertEqual(tab.source, states[1])
        tab.editor.redo()
        self.assertEqual(tab.source, branch)

    def test_parent_drag_moves_all_nested_children_without_reordering_them(self):
        parent = '[Parent]:\n  Details:\n    - intro\n  [A]:\n  - alpha\n  [B]:\n  - beta\n'
        other = '[Other]:\n- unrelated\n'
        source = parent + other
        tab = self.edit_tab(source)
        view = tab.document_map
        point = self.drag_to(tab, '[Parent]', len(source))
        self.assertIsNotNone(view._drag_plan)
        self.assertEqual(view._drag_block.end, len(parent))
        children = [node.id for node in view._tree.nodes if node.span.start < len(parent)]
        self.assertTrue(all(view._shape_dragged(owner) for owner in children))
        self.mouse(view, 'release', point)
        self.assertEqual(tab.source, other + parent)
        self.settle_edit(tab)
        self.assert_selected_label(tab, '[Parent]')
        tab.editor.undo()
        self.assert_clean(tab, source)

    def test_nested_child_can_move_among_siblings_but_cannot_escape_scope(self):
        # A plain container has separate named children; nested declarations
        # inside a named parent intentionally share that parent's whole owner.
        prefix = 'Holder:\n'
        first = '  [A]:\n  - alpha\n'
        second = '  [B]:\n  - beta\n'
        outside = '[Outside]:\n- unrelated\n'
        source = prefix + first + second + outside
        for destination, valid in ((len(prefix), True), (0, False), (len(source), False)):
            with self.subTest(destination=destination):
                tab = self.edit_tab(source)
                view = tab.document_map
                point = self.drag_to(tab, '  [B]', destination)
                self.assertEqual(view._drag_plan is not None, valid)
                self.mouse(view, 'release', point)
                if valid:
                    self.assertEqual(tab.source, prefix + second + first + outside)
                    tab.editor.undo()
                self.assert_clean(tab, source)

    def test_repeated_moves_have_independent_undo_steps_and_current_selection(self):
        blocks = ('[A]:\n- alpha\n', '[B]:\n- beta\n', '[C]:\n- gamma\n', '[D]:\n- delta\n')
        source = ''.join(blocks)
        tab = self.edit_tab(source)
        view = tab.document_map
        first = self.drag_to(tab, '[B]', len(source))
        self.mouse(view, 'release', first)
        expected_first = blocks[0] + blocks[2] + blocks[3] + blocks[1]
        self.assertEqual(tab.source, expected_first)
        self.settle_edit(tab)
        self.assert_selected_label(tab, '[B]')
        second = self.drag_to(tab, '[B]', 0)
        self.mouse(view, 'release', second)
        self.assertEqual(tab.source, blocks[1] + blocks[0] + blocks[2] + blocks[3])
        self.settle_edit(tab)
        self.assert_selected_label(tab, '[B]')
        tab.editor.undo()
        self.assertEqual(tab.source, expected_first)
        self.assertTrue(tab.editor.document().isUndoAvailable())
        tab.editor.undo()
        self.assert_clean(tab, source)

    def test_zoom_scroll_and_horizontal_motion_keep_vertical_drop_geometry(self):
        from PySide6.QtCore import QPointF
        source = ''.join(f'[N{index}]:\n- item {index}\n' for index in range(60))
        for scale in ('fit', 'half', 'full'):
            with self.subTest(scale=scale):
                tab = self.edit_tab(source)
                view = tab.document_map
                view._fit = scale == 'fit'
                view.scale = (view.minimum_scale if scale == 'fit' else
                              (1 + view.minimum_scale) / 2 if scale == 'half' else 1)
                tab.editor.verticalScrollBar().setValue(35)
                press = self.press_block(tab, '[N20]', x=1)
                source_rect = view._drag_source_rect()
                target = QPointF(view.width() - 2, view._boundary_y(source.index('[N22]')))
                self.mouse(view, 'move', target)
                self.assertTrue(view._drag_active)
                self.assertEqual(view._drag_destination, source.index('[N22]'))
                self.assertIsNotNone(view._drag_plan)
                self.assertEqual(view.drag_rect().left(), 0)
                self.assertEqual(view.drag_rect().width(), view.width())
                self.assertAlmostEqual(view.drag_rect().top() - source_rect.top(), target.y() - press.y())
                self.assert_clean(tab, source)
                self.mouse(view, 'release', target)
                moved = '[N20]:\n- item 20\n'
                expected = source.replace(moved, '').replace('[N22]:', moved + '[N22]:')
                self.assertEqual(tab.source, expected)
                tab.editor.undo()
                self.assert_clean(tab, source)

    def test_background_refresh_restores_moved_selection_and_rejects_stale_drag(self):
        source = '[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- gamma\n'
        tab = self.edit_tab(source, background=True)
        view = tab.document_map
        point = self.drag_to(tab, '[B]', 0)
        self.mouse(view, 'release', point)
        expected = '[B]:\n- beta\n[A]:\n- alpha\n[C]:\n- gamma\n'
        self.assertEqual(tab.source, expected)
        self.settle_edit(tab)
        self.assert_selected_label(tab, '[B]')
        self.assertFalse(tab.graph.enabled)
        point = self.drag_to(tab, '[B]', len(expected))
        tab.refresh_model()
        self.assertFalse(view._drag_active)
        self.assertIsNone(view._drag_press)
        self.mouse(view, 'release', point)
        self.assertEqual(tab.source, expected)
        self.settle_edit(tab)
        self.assertIsNone(view.selected_owner)  # An unrelated refresh cancels the second drag.
        tab.editor.undo()
        self.assert_clean(tab, source)

    def test_valid_move_works_in_each_inference_mode_without_rescoring(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        source = '[A]:\n- alpha\n[B]:\n- beta\n[C]:\n- [A]\n'
        expected = '[B]:\n- beta\n[A]:\n- alpha\n[C]:\n- [A]\n'
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.edit_tab(source, inference_mode=mode)
                with patch.object(tab.graph, '_schedule') as schedule:
                    point = self.drag_to(tab, '[B]', 0)
                    self.mouse(tab.document_map, 'release', point)
                    self.assertEqual(tab.source, expected)
                    self.settle_edit(tab)
                    self.assert_selected_label(tab, '[B]')
                    schedule.assert_not_called()
                    self.assertIsNone(tab.document_map.heat)
                tab.editor.undo()
                self.assert_clean(tab, source)


if __name__ == '__main__':
    unittest.main()
