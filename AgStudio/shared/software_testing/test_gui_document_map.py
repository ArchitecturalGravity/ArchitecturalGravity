"""Section-map partitioning, Qt geometry, zoom and non-navigation contracts."""
import importlib.util
import os
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class DocumentMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_tab(self, source='', **kwargs):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', source, **kwargs)
        tab.resize(1000, 620)
        tab.show()
        self.app.processEvents()
        tab.document_map.rebuild()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.close)
        return tab

    def wait_heat(self, tab):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 10
        while (not tab.document_map._heat_ready or tab.document_map._timer.isActive()) and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(tab.document_map._heat_ready)
        self.assertFalse(tab.document_map._timer.isActive())

    def wheel(self, widget, delta):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        event = QWheelEvent(QPointF(40, 80), QPointF(40, 80), QPoint(), QPoint(0, delta),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        widget.wheelEvent(event)
        self.assertTrue(event.isAccepted())

    def test_sections_partition_nested_members_without_duplicate_rows(self):
        tab = self.make_tab('First:\n- wide words\n  Nested:\n  - tiny\n- more\n\nSecond: value\nTail\n')
        m = tab.document_map
        self.assertEqual([row.owner for row in m.rows], [0, 0, 2, 2, 0, 6, 7])
        self.assertEqual(len({row.start for row in m.rows}), len(m.rows))
        self.assertEqual([owner for owner, _ in m.shapes], [0, 2, 0, 6, 7])
        self.assertLess(m.rows[0].right, m.rows[1].right)
        self.assertGreater(m.rows[2].left, m.rows[1].left)
        # A two-line block follows the width change, not its bounding rectangle.
        from PySide6.QtCore import QPointF
        first_shape = m.shapes[0][1]
        self.assertFalse(first_shape.contains(QPointF(m.rows[1].right - 1, m.rows[0].height / 2)))
        self.assertTrue(first_shape.contains(QPointF(m.rows[1].right - 1, m.rows[1].top + 2)))
        self.assertGreater(m.mapTo(tab, m.rect().topLeft()).x(), tab.editor.mapTo(tab, tab.editor.rect().topRight()).x())

    def test_right_map_splitter_resizes_and_keeps_zoom_and_overlay_bounded(self):
        tab = self.make_tab('Task:\n- ' + 'wide ' * 90 + '\n- short\n')
        tab.side_panel.show()
        self.app.processEvents()
        split = tab.editor_map_split
        m = tab.document_map
        self.assertIs(split.widget(0), tab.editor_column)
        self.assertIs(tab.editor.parentWidget(), tab.editor_column)
        self.assertIs(split.widget(1), tab.map_column)
        self.assertIs(m.parentWidget(), tab.map_column)
        self.assertIs(tab.editor_split.widget(1), tab.side_panel)
        self.assertFalse(split.childrenCollapsible())
        self.assertLess(m.mapTo(tab, m.rect().topRight()).x(),
                        tab.side_panel.mapTo(tab, tab.side_panel.rect().topLeft()).x())
        tab.side_panel.hide()
        self.app.processEvents()
        split.setSizes([600, 300])
        self.app.processEvents()
        m.rebuild()
        old_width, old_fit, old_x = m.width(), m.minimum_scale, m.horizontal_scale
        split.moveSplitter(split.handle(1).x() - 90, 1)
        self.app.processEvents()
        self.assertGreater(m.width(), old_width)
        self.assertEqual(m.minimum_scale, old_fit)
        self.assertGreater(m.horizontal_scale, old_x)
        self.assertAlmostEqual(m.horizontal_scale / old_x, m.width() / old_width)
        self.assertEqual(m.scale, m.minimum_scale)
        self.wheel(m, 240)
        ratio = m.scale / m.minimum_scale
        split.moveSplitter(split.handle(1).x() + 60, 1)
        self.app.processEvents()
        self.assertAlmostEqual(m.scale / m.minimum_scale, ratio)
        self.assertGreaterEqual(m.scale, m.minimum_scale)
        self.assertLessEqual(m.scale, 1)
        self.assertGreaterEqual(tab.editor.width(), 270)
        rect = m.viewport_rect().intersected(m.extent)
        self.assertEqual(m.mapped_viewport().left(), 0)
        self.assertEqual(m.mapped_viewport().width(), m.width())
        split.setSizes([100000, 1])
        self.app.processEvents()
        self.assertGreaterEqual(m.width(), 48)
        self.assertGreaterEqual(m.scale, m.minimum_scale)
        self.assertLessEqual(m.scale, 1)

    def test_map_background_previews_cancels_applies_and_reloads(self):
        import tempfile
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        from AgStudio.gui.color_schemes import SchemeStore
        from AgStudio.gui.user_state import UserState
        with tempfile.TemporaryDirectory() as directory:
            store = SchemeStore(directory)
            window = StudioWindow('current', background=False, scheme_store=store, user_state=UserState())
            self.addCleanup(window.deleteLater)
            window.show()
            tab = window.current()
            tab.editor.setPlainText('Task: text')
            self.app.processEvents()
            from unittest.mock import patch
            from PySide6.QtCore import QRectF
            def background(m):
                self.app.processEvents()
                # Test the background independently from the viewport overlay.
                with patch.object(m, 'mapped_viewport', return_value=QRectF()):
                    return m.grab().toImage().pixelColor(m.width() - 5, m.height() - 5).getRgb()
            original = tuple(window.color_scheme['editor']['background'])
            self.assertEqual(background(tab.document_map), original)
            dialog = ColorSchemeDialog(window)
            self.addCleanup(dialog.deleteLater)
            dialog.roles.setCurrentIndex(dialog.roles.findData('editor'))
            color = (20, 40, 80, 255)
            for spin, value in zip(dialog.controls['background'], color): spin.setValue(value)
            self.assertEqual(background(tab.document_map), color)
            dialog.reject()
            self.assertEqual(background(tab.document_map), original)
            dialog = ColorSchemeDialog(window)
            self.addCleanup(dialog.deleteLater)
            dialog.roles.setCurrentIndex(dialog.roles.findData('editor'))
            for spin, value in zip(dialog.controls['background'], color): spin.setValue(value)
            self.assertTrue(dialog.apply_scheme())
            store.save('Map background', dialog.working)
            dialog.reset_default()
            self.assertEqual(background(tab.document_map), original)
            dialog.refresh_names()
            dialog.schemes.setCurrentText('Map background')
            dialog.load_scheme()
            self.assertEqual(background(tab.document_map), color)
            dialog.reject()
            self.assertEqual(background(tab.document_map), color)
            reopened = StudioWindow('current', background=False, scheme_store=store, user_state=UserState())
            self.addCleanup(reopened.deleteLater)
            reopened.show()
            self.assertEqual(background(reopened.current().document_map), color)
            other = window.new_document()
            self.assertEqual(background(other.document_map), color)
            from copy import deepcopy
            from PySide6.QtCore import QPoint
            # Compare composited window pixels, including translucent backgrounds.
            for alpha in (0, 64, 128, 255):
                scheme = deepcopy(window.color_scheme)
                scheme['editor']['background'] = [40, 80, 120, alpha]
                window.apply_color_scheme(scheme)
                self.app.processEvents()
                with patch.object(other.document_map, 'mapped_viewport', return_value=QRectF()):
                    image = window.grab().toImage()
                editor = other.editor.viewport()
                m = other.document_map
                editor_point = editor.mapTo(window, QPoint(editor.width() - 5, editor.height() - 5))
                map_point = m.mapTo(window, QPoint(m.width() - 5, m.height() - 5))
                self.assertEqual(image.pixelColor(editor_point), image.pixelColor(map_point))

    def test_silhouettes_render_solid_with_independent_viewport_overlay(self):
        from unittest.mock import patch
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor
        tab = self.make_tab('Task:\n- Longest line in this block\n')
        m = tab.document_map
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 5
        while not m._heat_ready and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(m._heat_ready, 'graph result did not reach the map')
        row = m.rows[1]
        x = round((row.left + row.right) / 2 * m.horizontal_scale)
        y = round(m.map_origin().y() + (row.top + row.height / 2) * m.scale)
        with patch.object(m, 'mapped_viewport', return_value=QRectF()):
            image = m.grab().toImage()
        self.assertEqual(image.pixelColor(x, y), QColor(0, 0, 255))
        self.assertEqual(image.pixelColor(m.width() - 2, y), QColor(0, 0, 255))
        highlighted = m.grab().toImage()
        self.assertNotEqual(highlighted.pixelColor(x, y), image.pixelColor(x, y))
        self.assertEqual(m.mapped_viewport().left(), 0)
        self.assertEqual(m.mapped_viewport().right(), m.width())

    def test_widest_silhouette_touches_right_edge_at_every_pane_width(self):
        import math
        for source in ('Task:\n- short\n  - nested\n', 'Task:\n- ' + 'wide ' * 300 + '\n', '', '  \n\t\n'):
            with self.subTest(length=len(source)):
                tab = self.make_tab(source)
                m = tab.document_map
                for sizes in ([800, 100], [600, 300], [850, 50]):
                    tab.editor_map_split.setSizes(sizes)
                    self.app.processEvents()
                    m.rebuild()
                    self.assertTrue(math.isfinite(m.horizontal_scale))
                    self.assertGreater(m.horizontal_scale, 0)
                    if m.rows:
                        peak = max(row.right for row in m.rows)
                        self.assertAlmostEqual(peak * m.horizontal_scale, m.width())
                        for row in m.rows:
                            self.assertAlmostEqual((row.right * m.horizontal_scale) / m.width(), row.right / peak)
                            self.assertAlmostEqual((row.left * m.horizontal_scale) / m.width(), row.left / peak)
                    else:
                        self.assertTrue(m.path.isEmpty())
                    self.assertEqual(m.scale, m.minimum_scale)
                    self.assertEqual(m.mapped_viewport().width(), m.width())

    def test_vertical_fit_ignores_wide_lines_and_preserves_real_blank_space(self):
        for source in ('', 'Task: short', 'Task: ' + 'long ' * 500, 'Task: text\n' + '\n' * 90):
            with self.subTest(length=len(source)):
                tab = self.make_tab(source)
                m = tab.document_map
                expected = min(1.0, m.height() / m.extent.height())
                self.assertEqual(m.minimum_scale, expected)
                self.assertEqual(m.scale, expected)
                if m.extent.height() > m.height():
                    self.assertAlmostEqual(m.map_origin().y() + m.extent.height() * m.scale, m.height())
                else:
                    self.assertEqual(m.scale, 1)
                    self.assertAlmostEqual(m.map_origin().y(), -m.viewport_rect().top())
                self.assertEqual(m.mapped_viewport().left(), 0)
                self.assertEqual(m.mapped_viewport().right(), m.width())
                self.assertAlmostEqual(m.mapped_viewport().height(), m.editor.viewport().height() * m.scale)

    def test_one_to_one_tracks_editor_rows_and_width_resizes_only_x(self):
        tab = self.make_tab('Task:\n' + '- text\n' * 150)
        m = tab.document_map
        for _ in range(5): self.wheel(m, 2400)
        self.assertEqual(m.scale, 1)
        tab.editor.verticalScrollBar().setValue(45)
        self.app.processEvents()
        first = tab.editor.firstVisibleBlock()
        screen = tab.editor.blockBoundingGeometry(first).translated(tab.editor.contentOffset())
        self.assertAlmostEqual(m.block_tops[first.blockNumber()] + m.map_origin().y(), screen.top())
        self.assertEqual(m.mapped_viewport().top(), 0)
        self.assertEqual(m.mapped_viewport().height(), tab.editor.viewport().height())
        old_x = m.horizontal_scale
        tab.editor_map_split.moveSplitter(tab.editor_map_split.handle(1).x() - 100, 1)
        self.app.processEvents()
        self.assertEqual(m.scale, 1)
        self.assertGreater(m.horizontal_scale, old_x)
        tab.resize(1000, 800)
        self.app.processEvents()
        self.assertEqual(m.scale, 1)
        for _ in range(5): self.wheel(m, -2400)
        self.assertEqual(m.scale, m.minimum_scale)
        self.assertAlmostEqual(m.extent.height() * m.scale, m.height())
        x_scale = m.horizontal_scale
        self.wheel(m, 120)
        self.assertEqual(m.horizontal_scale, x_scale)

    def test_zoom_bounds_fit_and_one_to_one_do_not_navigate(self):
        tab = self.make_tab('Task:\n' + '- ' + 'wide ' * 100 + '\n' + '- text\n' * 160)
        m = tab.document_map
        before = (tab.source, tab.editor.textCursor().position(), tab.editor.verticalScrollBar().value())
        self.assertEqual(m.scale, m.minimum_scale)
        self.assertLessEqual(m.extent.width() * m.horizontal_scale, m.width() + 1e-6)
        self.assertAlmostEqual(m.extent.height() * m.scale, m.height())
        for _ in range(5): self.wheel(m, 2400)
        self.assertEqual(m.scale, 1.0)
        for _ in range(5): self.wheel(m, -2400)
        self.assertEqual(m.scale, m.minimum_scale)
        self.assertEqual(before, (tab.source, tab.editor.textCursor().position(), tab.editor.verticalScrollBar().value()))

    def test_scroll_overlay_and_resize_use_cached_geometry(self):
        tab = self.make_tab('Task:\n' + '- ' + 'wide ' * 200 + '\n' + '- text\n' * 180)
        m = tab.document_map
        # A graph result legitimately triggers one last set_model/rebuild.
        # Wait for that publication and geometry, rather than assuming process
        # startup finishes within 60 ms on a loaded full-suite run. Scrolling
        # below must still cause exactly zero additional geometry rebuilds.
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 10
        while (m.heat is None or not m._heat_ready or tab.graph.poll.isActive()
               or m._timer.isActive()) and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNotNone(m.heat, 'initial graph did not publish')
        self.assertIs(m.heat, tab.graph.heat)
        self.assertTrue(m._heat_ready)
        self.assertFalse(tab.graph.poll.isActive())
        self.assertFalse(m._timer.isActive())
        before = m.rebuild_count
        top = m.viewport_rect().top()
        tab.editor.verticalScrollBar().setValue(60)
        tab.editor.horizontalScrollBar().setValue(100)
        self.app.processEvents()
        self.assertGreater(m.viewport_rect().top(), top)
        self.assertGreater(m.viewport_rect().left(), 0)
        first = tab.editor.firstVisibleBlock()
        screen = tab.editor.blockBoundingGeometry(first).translated(tab.editor.contentOffset())
        self.assertAlmostEqual(m.viewport_rect().top() + screen.top(), m.block_tops[first.blockNumber()])
        overlay = m.mapped_viewport()
        visible = m.viewport_rect()
        self.assertAlmostEqual(overlay.height(), visible.height() * m.scale)
        self.assertEqual(overlay.left(), 0)
        self.assertEqual(overlay.width(), m.width())
        QTest.qWait(60)
        self.assertEqual(m.rebuild_count, before)
        tab.resize(800, 420)
        self.app.processEvents()
        self.assertEqual(m.scale, m.minimum_scale)
        self.assertLessEqual(m.mapped_viewport().height(), m.height())

    def test_unicode_tabs_line_separators_and_crlf_use_qt_positions(self):
        from AgStudio.gui.app import _display_offset
        from AgStudio.gui.document_map import display_offsets
        source = 'Task:\r\n  🌍 café\u2028\tWide 漢字\r\nTail\r\n'
        offsets = list(range(len(source) + 1))
        self.assertEqual(display_offsets(source, offsets), {p: _display_offset(source, p) for p in offsets})
        tab = self.make_tab(source)
        m = tab.document_map
        self.assertGreater(m.rows[1].left, m.rows[0].left)
        self.assertAlmostEqual(m.rows[2].left, m.rows[1].left)  # One tab becomes two spaces.
        for row in m.rows:
            block = tab.editor.document().findBlock(row.start)
            line = block.layout().lineForTextPosition(row.start - block.position())
            self.assertAlmostEqual(row.height, line.height())
            self.assertGreater(row.right, row.left)
        self.assertEqual(len(m.rows), 4)
        self.assertEqual(tab.source, source.replace("\t", "  "))

    def test_empty_small_and_edit_updates_and_background_pending(self):
        tab = self.make_tab('')
        m = tab.document_map
        self.assertEqual(m.rows, ())
        self.assertTrue(m.path.isEmpty())
        self.assertEqual(m.scale, 1)
        self.wheel(m, -120)
        self.assertEqual(m.scale, 1)
        tab.editor.setPlainText('A: x')
        self.assertEqual(m.rows, ())  # Keep the old empty frame until heat arrives.
        self.wait_heat(tab)
        m.rebuild()
        self.assertEqual(len(m.rows), 1)
        self.assertEqual(m.scale, 1)
        old_rows = m.rows
        tab.editor.setPlainText('One:\n- a\nTwo:\n- longer text\n')
        self.assertEqual(m.rows, old_rows)
        self.assertTrue(m.stale)
        self.wait_heat(tab)
        m.rebuild()
        self.assertEqual(len(m.rows), 4)
        self.assertEqual([owner for owner, _ in m.shapes], [0, 2])
        old_rows = m.rows
        old_colors = tuple(m.color_for_owner(row.owner) for row in m.rows)
        m.set_model(None)
        m.rebuild()
        self.assertTrue(m.stale)
        self.assertEqual(m.rows, old_rows)
        self.assertEqual(tuple(m.color_for_owner(row.owner) for row in m.rows), old_colors)
        self.assertIsNone(m._document)
        self.assertFalse(m._heat_ready)
        tab.refresh_model()
        self.wait_heat(tab)
        m.rebuild()
        self.assertEqual([owner for owner, _ in m.shapes], [0, 2])

    def test_background_edits_retain_stale_sections_and_refresh_automatically(self):
        from PySide6.QtTest import QTest
        tab = self.make_tab('Old:\n- item\n', background=True)
        self.wait_heat(tab)
        self.assertIsNotNone(tab.document_map._document)
        old_rows = tab.document_map.rows
        new = 'New:\n- longer item\nLast: value\n'
        tab.editor.setPlainText(new)
        self.assertIsNone(tab.document_map._document)
        self.assertEqual(tab.document_map.rows, old_rows)
        self.assertTrue(tab.document_map.stale)
        self.wait_heat(tab)
        self.assertEqual(tab.document_map._document.source, new)
        self.assertEqual(len(tab.document_map.rows), 3)
        self.assertEqual([owner for owner, _ in tab.document_map.shapes], [0, 2])

    def test_legacy_model_and_literal_blocks(self):
        tab = self.make_tab('Task:\n"""\n  Not a section:\n  contents\n"""\n', background=False)
        m = tab.document_map
        self.assertEqual(len(m.rows), 5)
        self.assertEqual(len({row.owner for row in m.rows}), 1)
        self.assertGreater(m.rows[2].left, m.rows[0].left)

    def test_large_geometry_is_linear_cached_and_font_responsive(self):
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import DocumentMap
        editor = SourceEditor()
        m = DocumentMap(editor)
        self.addCleanup(m.deleteLater)
        self.addCleanup(editor.deleteLater)
        editor.setPlainText(('  wide text 🌍\n' * 10000))
        started = time.perf_counter()
        m.rebuild()
        elapsed = time.perf_counter() - started
        self.assertEqual(len(m.rows), 10000)
        # A generous ceiling catches quadratic work without benchmarking CI load.
        self.assertLess(elapsed, 8.0)
        old_height = m.extent.height()
        editor.setStyleSheet('QPlainTextEdit#sourceEditor { font-size: 24px; }')
        m.rebuild()
        self.assertGreater(m.extent.height(), old_height)
        print(f'\nDocument map: 10,000 rows rebuilt in {elapsed:.3f}s')


if __name__ == '__main__':
    unittest.main()
