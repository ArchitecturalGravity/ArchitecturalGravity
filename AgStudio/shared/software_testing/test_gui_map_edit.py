"""Map edit mode pauses scoring while keeping source geometry live."""
import unittest
from unittest.mock import patch
from .test_gui_inference_map import InferenceMapTests


class MapEditTests(unittest.TestCase):
    setUpClass = classmethod(InferenceMapTests.setUpClass.__func__)
    make_tab = InferenceMapTests.make_tab
    settle = InferenceMapTests.settle
    point = InferenceMapTests.point

    def test_edit_toggle_all_algorithms(self):
        from PySide6.QtCore import QPoint
        from AgStudio.gui.document_map import EDIT_HELP
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.make_tab('[A]:\n- alpha\n[B]:\n- [A]\n', inference_mode=mode)
                view = tab.document_map
                heat = view.heat
                colors = [view.color_for_owner(row.owner) for row in view.rows]
                segments = [view.row_segments(row) for row in view.rows]
                tab.map_title.click()
                self.app.processEvents()
                view.rebuild()
                self.assertTrue(tab.map_title.isChecked())
                self.assertEqual(tab.map_title.text(), 'Infer Edit')
                self.assertEqual(tab.map_title.accessibleName(), 'Infer Edit')
                self.assertEqual(view.accessibleName(), 'Infer Edit')
                self.assertTrue(EDIT_HELP.startswith('Infer Edit\n\n'))
                self.assertFalse(tab.inference_mode_button.isEnabled())
                self.assertFalse(tab.graph.enabled)
                self.assertIsNone(tab.graph.heat)
                self.assertIs(view.heat, heat)
                self.assertFalse(view._spinner.isVisible())
                self.assertEqual(view.tooltip_at(QPoint(0, 0)), EDIT_HELP)
                self.assertTrue(view.rows)
                self.assertEqual([view.color_for_owner(row.owner) for row in view.rows], colors)
                self.assertEqual([view.row_segments(row) for row in view.rows], segments)
                tab.map_title.click()
                self.settle(tab)
                self.assertEqual(tab.map_title.text(), 'Infer Map')
                self.assertEqual(tab.map_title.accessibleName(), 'Infer Map')
                self.assertEqual(view.accessibleName(), 'Infer Map')
                self.assertTrue(tab.graph.enabled)
                self.assertTrue(tab.inference_mode_button.isEnabled())
                self.assertTrue(view._heat_ready)
                self.assertEqual(tab.graph.mode, mode)
                self.assertEqual([view.color_for_owner(row.owner) for row in view.rows], colors)
                self.assertEqual([view.row_segments(row) for row in view.rows], segments)

    def test_edit_refresh_and_visibility_do_not_restart_scoring(self):
        from AgStudio.gui.document_map import PENDING_COLOR
        tab = self.make_tab('[A]:\n- alpha\n')
        tab.map_title.click()
        with patch.object(tab.graph, '_schedule', wraps=tab.graph._schedule) as schedule:
            tab.editor.setPlainText('[B]:\n- beta\n[C]:\n- gamma\n')
            tab.refresh_model()
            tab.document_map.rebuild()
            self.assertEqual(len(tab.document_map.rows), 4)
            tab.set_map_enabled(False)
            tab.set_map_enabled(True)
            tab.document_map.rebuild()
            self.assertFalse(tab.graph.enabled)
            schedule.assert_not_called()
            self.assertTrue(tab.document_map.rows)
            self.assertTrue(all(tab.document_map.color_for_owner(row.owner).getRgb()[:3] == PENDING_COLOR
                                for row in tab.document_map.rows))
        tab.map_title.click()
        self.settle(tab)
        self.assertEqual(tab.graph.analysis.document.source, tab.source)

    def test_background_edits_and_late_results_do_not_reuse_old_scores(self):
        from PySide6.QtTest import QTest
        import time
        tab = self.make_tab('[A]:\n- alpha\n[B]:\n- [A]\n', background=True)
        view = tab.document_map
        geometry = [(r.top, r.left, r.right, r.height) for r in view.rows]
        tab.map_title.click()
        view.rebuild()
        self.assertEqual(geometry, [(r.top, r.left, r.right, r.height) for r in view.rows])
        with patch.object(tab, '_render_map') as render:
            tab._graph_ready(tab.graph.revision, object())
            tab._graph_failed(tab.graph.revision, 'late error')
            render.assert_not_called()
        self.assertIsNone(view.error)
        tab.editor.setPlainText('[C]:\n- changed\n')
        end = time.monotonic() + 8
        while (tab.analysis is None or tab.analysis.document.source != tab.source or len(view.rows) != 2) and time.monotonic() < end:
            QTest.qWait(20)
        self.assertEqual(len(view.rows), 2)
        self.assertFalse(tab.graph.enabled)
        self.assertIsNone(view.heat)
        tab.map_title.click()
        self.settle(tab)


    def select_row(self, view, index):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=self.point(view, view.rows[index]))
        self.app.processEvents()

    def color_frame(self, view):
        from PySide6.QtCore import QRectF
        # Compare object paint independently of the unchanged edit decorations.
        with patch.object(view, '_paint_edit_dividers'), \
                patch.object(view, '_paint_edit_arrows'), \
                patch.object(view, 'mapped_viewport', return_value=QRectF(-10, -10, 1, 1)):
            return view.grab().toImage()

    def test_edit_pixels_and_deselection_restore_exact_map_colors_all_modes(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from AgStudio.gui.document_map import EDIT_SELECTED_COLOR
        from AgStudio.gui.inference_heat import MODE_LABELS
        source = ('[A]:\n- alpha AS [Alias]\n\n[B]:\n  Detail:\n'
                  '    - context [A] [Alias] tail\n\n[C]:\n- [B]\n')
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.make_tab(source, inference_mode=mode)
                view = tab.document_map
                baseline = self.color_frame(view)
                original_segments = [view.row_segments(row) for row in view.rows]
                heat = view.heat
                if mode == 'semantic_triad_2':
                    self.assertTrue(any(len({color for _, _, color in segments}) > 1
                                        for segments in original_segments))
                tab.map_title.click()
                view.rebuild()
                with patch.object(tab.graph, '_schedule') as schedule:
                    self.assertEqual(self.color_frame(view), baseline)
                    for index in (3, 0, 3):
                        self.select_row(view, index)
                        selected = view.selected_owner
                        frame = self.color_frame(view)
                        self.assertNotEqual(frame, baseline)
                        for row, segments in zip(view.rows, original_segments):
                            is_selected = view._edit_owners[row.owner] == selected
                            if not is_selected:
                                self.assertEqual(view.row_segments(row), segments)
                            # Inspect actual pixels inside each exact ST2 span,
                            # not only the color accessor used for H/ST1.
                            for _, rect, color in segments:
                                if rect.width() * view.horizontal_scale < 3:
                                    continue
                                x = round(rect.center().x() * view.horizontal_scale)
                                y = round(view.map_origin().y() + rect.center().y() * view.scale)
                                expected = EDIT_SELECTED_COLOR if is_selected else color
                                self.assertEqual(frame.pixelColor(x, y).getRgb()[:3], expected)
                        QTest.mouseClick(view, Qt.MouseButton.LeftButton,
                                         pos=QPoint(view.width() - 1, view.height() - 1))
                        self.assertIsNone(view.selected_owner)
                        self.assertEqual(self.color_frame(view), baseline)
                    self.assertIs(view.heat, heat)
                    schedule.assert_not_called()

    def test_source_change_discards_palette_and_st2_frame_before_new_geometry(self):
        from AgStudio.gui.document_map import PENDING_COLOR
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.make_tab('[A]:\n- alpha\n[B]:\n- [A]\n', inference_mode=mode)
                view = tab.document_map
                tab.map_title.click()
                view.rebuild()
                self.select_row(view, 2)
                self.color_frame(view)
                with patch.object(tab.graph, '_schedule') as schedule:
                    tab.editor.setPlainText('[Different]:\n- no relation\n[New]:\n- unrelated\n')
                    self.assertIsNone(view.heat)
                    self.assertIsNone(view.selected_owner)
                    self.assertFalse(view._edit_regions)
                    tab.refresh_model()
                    view.rebuild()
                    self.assertEqual(view._document.source, tab.source)
                    self.assertTrue(view._position_frame.isNull())
                    self.assertIsNone(view._source_index)
                    self.assertFalse(view._position_commands)
                    self.assertFalse(view._display_colors)
                    for row in view.rows:
                        self.assertEqual(view.color_for_owner(row.owner).getRgb()[:3], PENDING_COLOR)
                        self.assertTrue(all(color == PENDING_COLOR for _, _, color in view.row_segments(row)))
                    self.select_row(view, 2)
                    self.assertIsNotNone(view.selected_owner)
                    schedule.assert_not_called()
                tab.map_title.click()
                self.settle(tab)
                self.assertTrue(view._heat_ready)
                self.assertEqual(view._document.source, tab.source)

    def test_rapid_mode_roundtrips_retain_palette_before_scoring_restarts(self):
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.make_tab('[A]:\n- alpha\n[B]:\n- context [A] tail\n', inference_mode=mode)
                view = tab.document_map
                heat = view.heat
                baseline = self.color_frame(view)
                segments = [view.row_segments(row) for row in view.rows]
                with patch.object(tab.graph, '_schedule'):
                    for _ in range(3):
                        tab.set_map_edit_mode(True)
                        view.rebuild()
                        self.assertIs(view.heat, heat)
                        self.assertEqual([view.row_segments(row) for row in view.rows], segments)
                        self.assertEqual(self.color_frame(view), baseline)
                        self.select_row(view, 2)
                        tab.set_map_edit_mode(False)
                        self.assertIsNone(view.heat)
                        self.assertFalse(view._heat_ready)
                        self.assertTrue(view.stale)
                        self.assertIsNone(view.selected_owner)
                        view.rebuild()  # Pending scoring keeps the last frame.
                tab.set_map_edit_mode(True)
                view.rebuild()
                self.assertIs(view.heat, heat)
                self.assertEqual(self.color_frame(view), baseline)

    def test_algorithm_change_during_edit_cannot_reuse_another_palette(self):
        from AgStudio.gui.document_map import PENDING_COLOR
        from AgStudio.gui.inference_heat import MODE_LABELS
        modes = tuple(MODE_LABELS)
        tab = self.make_tab('[A]:\n- alpha\n[B]:\n- [A]\n')
        for mode in modes[1:] + modes[:1]:
            tab.map_title.click()
            view = tab.document_map
            view.rebuild()
            self.assertIsNotNone(view.heat)
            with patch.object(tab.graph, '_schedule') as schedule:
                tab.set_inference_mode(mode)
                view.rebuild()
                self.assertIsNone(view.heat)
                self.assertFalse(view._display_segments)
                self.assertTrue(view._position_frame.isNull())
                self.assertTrue(all(view.color_for_owner(row.owner).getRgb()[:3] == PENDING_COLOR
                                    for row in view.rows))
                schedule.assert_not_called()
            tab.map_title.click()
            self.settle(tab)
            self.assertEqual(view.mode, mode)
            self.assertIsNotNone(view.heat)

    def test_entering_edit_without_ready_scores_keeps_the_pending_palette(self):
        from AgStudio.gui.document_map import EDIT_SELECTED_COLOR, PENDING_COLOR
        from AgStudio.gui.app import DocumentTab
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = DocumentTab('current', '[A]:\n- alpha\n[B]:\n- beta\n',
                                  map_enabled=False, inference_mode=mode)
                self.addCleanup(tab.deleteLater)
                self.addCleanup(tab.close)
                tab.resize(1000, 620)
                tab.show()
                with patch.object(tab.graph, '_schedule') as schedule:
                    tab.set_map_edit_mode(True)
                    tab.set_map_enabled(True)
                    self.app.processEvents()
                    view = tab.document_map
                    view.rebuild()
                    self.assertTrue(view.rows)
                    self.assertIsNone(view.heat)
                    self.assertTrue(all(view.color_for_owner(row.owner).getRgb()[:3] == PENDING_COLOR
                                        for row in view.rows))
                    self.select_row(view, 0)
                    self.assertEqual(view.color_for_owner(view.rows[0].owner).getRgb()[:3], EDIT_SELECTED_COLOR)
                    schedule.assert_not_called()

    def test_direct_arrows_and_orange_selection_all_modes(self):
        from AgStudio.gui.document_map import EDIT_SELECTED_COLOR
        from AgStudio.gui.inference_heat import MODE_LABELS
        source = '[A]:\n- alpha\n[B]:\n- [A] [A]\n[C]:\n- [B]\n[D]:\n- unrelated\n'
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.make_tab(source, inference_mode=mode)
                view = tab.document_map
                heat = view.heat
                colors = {row.owner: view.color_for_owner(row.owner).getRgb()[:3] for row in view.rows}
                segments = {row.start: view.row_segments(row) for row in view.rows}
                tab.map_title.click()
                view.rebuild()
                with patch.object(tab.graph, '_schedule') as schedule:
                    self.select_row(view, 2)
                    chosen = view._edit_owners[view.rows[2].owner]
                    self.assertEqual(view.selected_owner, chosen)
                    arrows = view.edit_arrows()
                    self.assertEqual({(o, d) for o, d, _ in arrows},
                                     {(view._edit_owners[view.rows[0].owner], 'down'),
                                      (view._edit_owners[view.rows[4].owner], 'up')})
                    self.assertEqual(len(arrows), 2)  # Repeated uses give one marker.
                    for row in view.rows:
                        expected = (EDIT_SELECTED_COLOR if view._edit_owners[row.owner] == chosen
                                    else colors[row.owner])
                        self.assertEqual(view.color_for_owner(row.owner).getRgb()[:3], expected)
                        if view._edit_owners[row.owner] == chosen:
                            self.assertTrue(all(color == EDIT_SELECTED_COLOR for _, _, color in view.row_segments(row)))
                        else:
                            self.assertEqual(view.row_segments(row), segments[row.start])
                    self.assertEqual(tab.editor.textCursor().position(), source.index('[B]:'))
                    self.assertEqual(tab.source, source)
                    self.assertFalse(tab.graph.enabled)
                    self.assertIs(view.heat, heat)
                    schedule.assert_not_called()
                self.select_row(view, 6)
                self.assertFalse(view.edit_arrows())
                self.assertNotEqual(view.selected_owner, chosen)

    def test_arrow_right_inset_follows_resize_independent_of_zoom_and_scroll(self):
        tab = self.make_tab('[A]:\n- alpha\n\n[B]:\n- [A]\n[C]:\n- [B]\n' + '\n' * 80)
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        self.select_row(view, 2)
        for scale, width in ((view.minimum_scale, 48), (view.minimum_scale, 150),
                             (1.0, 220), (1.0, 48)):
            view.scale = scale
            view.resize(width, view.height())
            tab.editor.verticalScrollBar().setValue(1)
            for owner, _, center in view.edit_arrows():
                shapes = [shape.boundingRect() for node, shape in view.shapes
                          if view._edit_owners[node] == owner]
                top = min(r.top() for r in shapes)
                bottom = max(r.bottom() for r in shapes)
                self.assertEqual(center.x(), view.width() - 10)
                self.assertAlmostEqual(center.y(), view.map_origin().y() + (top + bottom) / 2 * view.scale)

    def test_selection_clears_on_blank_mode_exit_and_document_update(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        tab = self.make_tab('[A]:\n- alpha\n[B]:\n- [A]\n')
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        self.select_row(view, 2)
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=QPoint(view.width() - 1, view.height() - 1))
        self.assertIsNone(view.selected_owner)
        self.assertFalse(view.edit_arrows())
        self.select_row(view, 2)
        tab.editor.insertPlainText('changed ')
        self.assertIsNone(view.selected_owner)
        self.assertFalse(view.edit_arrows())
        view.invalidate()  # Simulate waiting for the next analysis snapshot.
        self.select_row(view, 2)  # Retained stale geometry cannot be selected.
        self.assertIsNone(view.selected_owner)
        tab.refresh_model()
        view.rebuild()
        self.select_row(view, 2)
        self.assertIsNotNone(view.selected_owner)
        tab.map_title.click()
        self.settle(tab)
        self.assertIsNone(view.selected_owner)
        self.assertFalse(view.edit_arrows())
        self.select_row(view, 2)  # Normal mode retains its non-selection behavior.
        self.assertIsNone(view.selected_owner)
        tab.map_title.click()
        view.rebuild()
        self.assertIsNone(view.selected_owner)
        self.select_row(view, 2)
        tab.set_map_enabled(False)
        tab.set_map_enabled(True)
        view.rebuild()
        self.assertIsNone(view.selected_owner)
        self.assertFalse(view.edit_arrows())

    def test_only_resolved_direct_relationships_and_alias_owner(self):
        source = ('[A]:\n- alpha AS [Alias]\n[B]:\n- [Alias]\n'
                  '[C]:\n- [B]\n[D]:\n- [Missing] [Future]\n'
                  '[Future]:\n- future\n')
        tab = self.make_tab(source)
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        self.select_row(view, 0)
        self.assertEqual([(o, d) for o, d, _ in view.edit_arrows()],
                         [(view._edit_owners[view.rows[2].owner], 'up')])
        self.select_row(view, 6)
        self.assertEqual(view.edit_arrows(), ())

    def test_arrows_are_painted_near_right_edge_with_clear_space(self):
        from AgStudio.gui.document_map import EDIT_ARROW_COLOR
        tab = self.make_tab('[A]:\n- alpha\n[B]:\n- [A]\n[C]:\n- [B]\n')
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        self.select_row(view, 2)
        for width in (48, 130, 220):
            with self.subTest(width=width):
                view.resize(width, view.height())
                frame = view.grab().toImage()
                self.assertEqual(len(view.edit_arrows()), 2)
                for _, _, center in view.edit_arrows():
                    self.assertEqual(center.x(), width - 10)
                    self.assertEqual(frame.pixelColor(round(center.x()), round(center.y())).getRgb()[:3],
                                     EDIT_ARROW_COLOR)
                    # The entire painted head, including its antialiased stroke,
                    # stays inset; neither the edge nor the old center is green.
                    for y in range(round(center.y()) - 8, round(center.y()) + 9):
                        for x in (*range(width - 4, width), width // 2):
                            color = frame.pixelColor(x, y)
                            self.assertFalse(color.green() > color.red() + 30
                                             and color.green() > color.blue() + 30)

    def test_right_edge_arrows_preserve_painted_up_and_down_directions(self):
        from unittest.mock import Mock
        from PySide6.QtCore import QPointF
        tab = self.make_tab('[A]:\n- alpha\n[B]:\n- [A]\n[C]:\n- [B]\n')
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        self.select_row(view, 2)
        painter = Mock()
        view._paint_edit_arrows(painter)
        arrows = view.edit_arrows()
        self.assertEqual({direction for _, direction, _ in arrows}, {'up', 'down'})
        self.assertEqual(painter.drawLine.call_count, len(arrows))
        self.assertEqual(painter.drawPolyline.call_count, len(arrows))
        for index, (_, direction, center) in enumerate(arrows):
            sign = 1 if direction == 'down' else -1
            x, y = center.x(), center.y()
            self.assertEqual(painter.drawLine.call_args_list[index].args,
                             (QPointF(x, y - sign * 6), QPointF(x, y + sign * 6)))
            self.assertEqual(list(painter.drawPolyline.call_args_list[index].args[0]),
                             [QPointF(x - 4, y + sign * 2), QPointF(x, y + sign * 6),
                              QPointF(x + 4, y + sign * 2)])

    def test_nested_geometry_uses_whole_block_identity(self):
        tab = self.make_tab('[A]:\n  Details:\n    - alpha\n[B]:\n- [A]\n')
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        self.select_row(view, 1)
        self.assertEqual(view.selected_owner, view._edit_owners[view.rows[0].owner])
        self.assertEqual(len(view.edit_arrows()), 1)
        self.select_row(view, 3)
        self.assertEqual(len(view.edit_arrows()), 1)
        owner, direction, _ = view.edit_arrows()[0]
        self.assertEqual(owner, view._edit_owners[view.rows[0].owner])
        self.assertEqual(direction, 'down')

    def test_full_width_whitespace_selects_whole_objects_in_all_modes(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from AgStudio.gui.inference_heat import MODE_LABELS
        source = '[A]:\n  - a much longer source line\n\n[B]:\n  - [A]\n'
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.make_tab(source, inference_mode=mode)
                view = tab.document_map
                tab.map_title.click()
                view.rebuild()
                cursor = tab.editor.textCursor().position()
                self.assertEqual(len(view._edit_regions), 2)
                for row_index in (0, 1, 2, 3, 0, 0):
                    row = view.rows[row_index]
                    owner = view._edit_owners[row.owner]
                    for x in (0, view.width() - 1):
                        point = QPoint(x, self.point(view, row).y())
                        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=point)
                        self.assertEqual(view.selected_owner, owner)
                self.assertEqual(tab.editor.textCursor().position(), cursor)
                self.assertEqual(tab.source, source)
                self.assertFalse(tab.editor.document().isModified())

    def test_blank_gap_is_split_by_divider_and_boundary_selects_below(self):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent
        tab = self.make_tab('[A]:\n- alpha\n\n\n[B]:\n- beta\n')
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        first, last = view._edit_regions
        above, below = view.rows[1], view.rows[2]
        divider = (above.top + above.height + below.top) / 2
        self.assertEqual(first.bottom, divider)
        self.assertEqual(last.top, divider)
        for y, owner in ((above.top + above.height + 1, first.owner),
                         (divider - 0.01, first.owner),
                         (divider, last.owner),
                         (divider + 0.01, last.owner),
                         (below.top - 1, last.owner)):
            point = QPointF(view.width() - 1, view.map_origin().y() + y * view.scale)
            event = QMouseEvent(QEvent.Type.MouseButtonPress, point, point,
                                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(view, event)
            self.assertEqual(view.selected_owner, owner)

    def test_first_last_bounds_and_no_objects(self):
        from PySide6.QtCore import QPointF
        for source in ('\n\n[A]:\n- alpha\n\n[B]:\n- beta\n\n',
                       '\n[A]:\n- alpha\n\n', '', '\n \n\t\n'):
            with self.subTest(source=source):
                tab = self.make_tab(source)
                view = tab.document_map
                tab.map_title.click()
                view.rebuild()
                def owner_at(y, x=1):
                    return view.edit_owner_at(QPointF(x, view.map_origin().y() + y * view.scale))
                if not view.rows:
                    self.assertFalse(view._edit_regions)
                    self.assertIsNone(owner_at(0))
                    continue
                first, last = view._edit_regions[0], view._edit_regions[-1]
                self.assertEqual(first.top, view.rows[0].top)
                self.assertEqual(last.bottom, view.rows[-1].top + view.rows[-1].height)
                self.assertIsNone(owner_at(first.top - 0.01))
                self.assertEqual(owner_at(first.top), first.owner)
                self.assertEqual(owner_at(last.bottom - 0.01), last.owner)
                self.assertIsNone(owner_at(last.bottom))
                self.assertIsNone(owner_at(last.bottom + 1))
                self.assertIsNone(owner_at(first.top, -1))
                self.assertIsNone(owner_at(first.top, view.width()))

    def test_exact_divider_boundary_at_fitted_zoom_selects_below(self):
        from PySide6.QtCore import QPointF
        tab = self.make_tab(''.join(f'[A{index}]:\n- alpha\n\n' for index in range(100)))
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        self.assertLess(view.scale, 1)
        for region in view._edit_regions[1:]:
            y = view.map_origin().y() + region.top * view.scale
            self.assertEqual(view.edit_owner_at(QPointF(view.width() - 1, y)), region.owner)

    def test_nested_partitions_and_internal_blank_lines_share_region(self):
        from PySide6.QtCore import QPointF
        from AgStudio.gui.inference_heat import MODE_LABELS
        for mode in MODE_LABELS:
            with self.subTest(mode=mode):
                tab = self.make_tab('[A]:\n  Details:\n    - alpha\n\n    - beta\n'
                                    '\n[B]:\n- [A]\n', inference_mode=mode)
                view = tab.document_map
                tab.map_title.click()
                view.rebuild()
                self.assertEqual(len(view._edit_regions), 2)
                first = view._edit_regions[0]
                y = (view.rows[2].top + view.rows[2].height + view.rows[3].top) / 2
                point = QPointF(view.width() - 1, view.map_origin().y() + y * view.scale)
                self.assertEqual(view.edit_owner_at(point), first.owner)

    def test_divider_pen_is_dotted_orange_and_restores_painter(self):
        from unittest.mock import Mock
        from PySide6.QtCore import Qt
        from AgStudio.gui.document_map import EDIT_SELECTED_COLOR
        tab = self.make_tab('[A]:\n- alpha\n\n[B]:\n- beta\n')
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        painter = Mock()
        view._paint_edit_dividers(painter)
        pen = painter.setPen.call_args.args[0]
        self.assertEqual(pen.style(), Qt.PenStyle.DotLine)
        self.assertEqual(pen.color().getRgb()[:3], EDIT_SELECTED_COLOR)
        self.assertEqual(pen.widthF(), 1)
        painter.save.assert_called_once_with()
        painter.restore.assert_called_once_with()

    def test_dotted_dividers_span_full_width_and_track_zoom_resize_scroll(self):
        import math
        from PySide6.QtCore import QPointF
        from AgStudio.gui.document_map import EDIT_SELECTED_COLOR
        tab = self.make_tab('[A]:\n- alpha\n\n[B]:\n- [A]\n\n[C]:\n- beta\n' + '\n' * 80)
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        for scale, width in ((view.minimum_scale, 48), (1.0, 220)):
            view._fit = False
            view.scale = scale
            view.resize(width, view.height())
            tab.editor.verticalScrollBar().setValue(1)
            frame = view.grab().toImage()
            for region in view._edit_regions[1:]:
                y = view.map_origin().y() + region.top * view.scale
                self.assertTrue(0 < y < view.height())
                pixels = [frame.pixelColor(x, math.floor(y)).getRgb()[:3] == EDIT_SELECTED_COLOR
                          for x in range(view.width())]
                # Dots and gaps persist across the full pane, at both zoom levels.
                for start in range(0, view.width(), 8):
                    segment = pixels[start:start + 8]
                    self.assertTrue(any(segment))
                    self.assertFalse(all(segment))
                for x in (0, view.width() // 2, view.width() - 1):
                    self.assertEqual(view.edit_owner_at(QPointF(x, y + 0.1)), region.owner)

    def test_regions_clear_on_stale_hide_and_mode_switch(self):
        from PySide6.QtCore import QPointF
        tab = self.make_tab('[A]:\n- alpha\n\n[B]:\n- [A]\n')
        view = tab.document_map
        tab.map_title.click()
        view.rebuild()
        point = QPointF(view.width() - 1, self.point(view, view.rows[0]).y())
        self.assertIsNotNone(view.edit_owner_at(point))
        view.invalidate()
        self.assertFalse(view._edit_regions)
        self.assertIsNone(view.edit_owner_at(point))
        tab.refresh_model()
        view.rebuild()
        self.assertTrue(view._edit_regions)
        tab.set_map_enabled(False)
        self.assertFalse(view._edit_regions)
        tab.set_map_enabled(True)
        view.rebuild()
        self.assertTrue(view._edit_regions)
        for _ in range(2):
            tab.map_title.click()
            self.settle(tab)
            self.assertFalse(view._edit_regions)
            self.assertIsNone(view.edit_owner_at(point))
            tab.map_title.click()
            view.rebuild()
            self.assertEqual(len(view._edit_regions), 2)
            self.assertIsNotNone(view.edit_owner_at(point))


del InferenceMapTests
