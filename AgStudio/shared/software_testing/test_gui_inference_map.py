"""Whole-block heat painting, normalization and current-analysis lifecycle."""
import importlib.util
import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class InferenceMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_tab(self, source, **kwargs):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', source, **kwargs)
        tab.resize(1000, 620)
        tab.show()
        self.app.processEvents()
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.close)
        self.settle(tab)
        tab.document_map.rebuild()
        return tab

    def settle(self, tab):
        from PySide6.QtTest import QTest
        end = time.monotonic() + 8
        while (not tab.document_map._heat_ready
               or tab.document_map._timer.isActive()
               or tab.analysis is None
               or tab.analysis.document.source != tab.source) and time.monotonic() < end:
            QTest.qWait(20)
        self.assertIsNotNone(tab.analysis)
        self.assertEqual(tab.analysis.document.source, tab.source)
        self.assertTrue(tab.document_map._heat_ready,
                        f'graph did not publish: enabled={tab.graph.enabled}, '
                        f'polling={tab.graph.poll.isActive()}, running={tab.graph.running}, '
                        f'pending={tab.graph.pending}, busy={tab.graph.worker.busy}, '
                        f'submitted={tab.graph._submitted}, heat={tab.graph.heat is not None}, '
                        f'error={tab.document_map.error}, closed={tab.graph.closed}')

    def point(self, m, row):
        from PySide6.QtCore import QPoint
        return QPoint(round((row.left + row.right) / 2 * m.horizontal_scale),
                      round(m.map_origin().y() + (row.top + row.height / 2) * m.scale))

    def test_default_help_has_requested_text_and_line_breaks(self):
        from PySide6.QtCore import QPoint
        from AgStudio.gui.document_map import MAP_HELP
        expected = ('Infer Map\n\n'
                    'Relative inferential-influence emphasis heuristic correlations.\n\n'
                    'Represents a portrayal of competing\n'
                    'semantics to speculate LLM interpretation.\n\n'
                    '- Blue is least influential\n'
                    '- Red is most influential')
        self.assertEqual(MAP_HELP, expected)
        for source in ('', '\n', '  \n\t\n'):
            with self.subTest(source=source):
                m = self.make_tab(source).document_map
                self.assertEqual(m.toolTip(), expected)
                self.assertEqual(m.tooltip_at(QPoint(m.width() // 2, m.height() // 2)), expected)

    def test_black_space_around_and_between_blocks_uses_default_help(self):
        from PySide6.QtCore import QPoint
        from AgStudio.gui.document_map import MAP_HELP
        m = self.make_tab('[A]:\n  - a much longer source line\n\n[B]:\n- [A]\n').document_map
        header = m.rows[0]
        indented = m.rows[1]
        points = (
            QPoint(m.width() - 2, self.point(m, header).y()),  # Beyond the short header.
            QPoint(1, self.point(m, indented).y()),  # Before the indented body.
            QPoint(m.width() // 2,
                   round(m.map_origin().y() + (m.block_tops[2] + header.height / 2) * m.scale)),
            QPoint(m.width() // 2, m.height() - 2),  # Below all source rows.
        )
        for point in points:
            with self.subTest(point=point):
                self.assertEqual(m.tooltip_at(point), MAP_HELP)
        self.assertIn('[A], line 1', m.tooltip_at(self.point(m, indented)))

    def test_tooltip_events_switch_between_default_and_block_without_stale_text(self):
        from PySide6.QtCore import QEvent, QPoint
        from PySide6.QtGui import QHelpEvent
        from PySide6.QtWidgets import QToolTip
        from AgStudio.gui.document_map import MAP_HELP
        m = self.make_tab('[A]: value\n[B]:\n- [A]\n').document_map
        block_point = self.point(m, m.rows[0])
        blank_point = QPoint(m.width() // 2, m.height() - 2)
        block_text = ('Infer Map - (2.00 total inf)<br><br>'
                      '[A], line 1<br>'
                      'Inheritances: 1x (1.00 inf)<br>'
                      'Propagations: 0x (0.00 inf)')
        self.addCleanup(QToolTip.hideText)
        for point, expected in ((blank_point, MAP_HELP.replace('\n', '<br>')),
                                (block_point, block_text),
                                (blank_point, MAP_HELP.replace('\n', '<br>')),
                                (block_point, block_text)):
            self.app.sendEvent(m, QHelpEvent(QEvent.Type.ToolTip, point, m.mapToGlobal(point)))
            self.assertTrue(QToolTip.isVisible())
            self.assertEqual(QToolTip.text(), '<p style="white-space:pre">' + expected + '</p>')
        m.set_model(None)
        self.app.sendEvent(m, QHelpEvent(QEvent.Type.ToolTip, block_point, m.mapToGlobal(block_point)))
        self.assertEqual(QToolTip.text(), '<p style="white-space:pre">' + MAP_HELP.replace('\n', '<br>') + '</p>')

    def test_exact_colors_are_painted_across_whole_block_partitions(self):
        from PySide6.QtCore import QRectF
        source = '[A]:\n- source\n  Details:\n  - nested prose\n[D]:\n- [A] [A] [A]\n'
        tab = self.make_tab(source)
        m = tab.document_map
        self.assertEqual([row.owner for row in m.rows], [0, 0, 2, 2, 4, 4])
        self.assertEqual(m._heat_range, (1, 3))
        with patch.object(m, 'mapped_viewport', return_value=QRectF()):
            image = m.grab().toImage()
        for row in m.rows:
            expected = (255, 0, 0) if row.owner in (0, 2) else (0, 0, 255)
            self.assertEqual(m.color_for_owner(row.owner).getRgb()[:3], expected)
            self.assertEqual(image.pixelColor(self.point(m, row)).getRgb()[:3], expected)

    def test_supported_symbolic_list_body_splits_enclosing_geometry(self):
        tab = self.make_tab('[A]: value\nHolder:\n- [B]:\n  - [A]\n  - [A]\n')
        m = tab.document_map
        self.assertEqual([row.owner for row in m.rows], [0, 1, 2, 2, 2])
        self.assertEqual(m.color_for_owner(0).getRgb()[:3], (255, 0, 0))
        self.assertEqual(m.color_for_owner(1).getRgb()[:3], (0, 0, 255))
        self.assertEqual(m.color_for_owner(2).getRgb()[:3], (128, 0, 128))

    def test_hover_uses_compact_format_and_owning_block_symbol_and_line(self):
        tab = self.make_tab('[A]: value\n[B]:\n  Details:\n  - [A]\n[C]:\n- [B]\n')
        m = tab.document_map
        a = m.tooltip_at(self.point(m, m.rows[0]))
        self.assertEqual(a, 'Infer Map - (5.00 total inf)\n\n'
                            '[A], line 1\n'
                            'Inheritances: 1x (1.00 inf)\n'
                            'Propagations: 1x (0.50 inf)')
        nested = m.tooltip_at(self.point(m, m.rows[2]))
        self.assertEqual(nested, 'Infer Map - (5.00 total inf)\n\n'
                                 '[B], line 2\n'
                                 'Inheritances: 2x (2.00 inf)\n'
                                 'Propagations: 0x (0.00 inf)')
        self.assertEqual(m._heat_range, (1.5, 2))
        self.assertIn('not measured model attention', m.accessibleDescription())
        self.assertEqual(m._document_influence, 5)
        for row in m.rows:
            self.assertTrue(m.tooltip_at(self.point(m, row)).startswith(
                'Infer Map - (5.00 total inf)\n\n'))

    def test_hover_direct_counts_preserve_source_receiver_asymmetry(self):
        m = self.make_tab('[A]: value\n[D]:\n- [A] [A] [A]\n').document_map
        source = m.tooltip_at(self.point(m, m.rows[0]))
        receiver = m.tooltip_at(self.point(m, m.rows[1]))
        self.assertIn('Inheritances: 3x (3.00 inf)', source)
        self.assertIn('Inheritances: 1x (1.00 inf)', receiver)
        self.assertIn('Propagations: 0x (0.00 inf)', source)
        self.assertIn('Propagations: 0x (0.00 inf)', receiver)

    def test_hover_propagation_counts_relations_not_occurrences_or_hops(self):
        source = '[A]: value\n[B]:\n- [A] [A] [A]\n[C]:\n- [A] [B]\n'
        m = self.make_tab(source).document_map
        c = m.tooltip_at(self.point(m, m.rows[3]))
        self.assertEqual(c, 'Infer Map - (10.50 total inf)\n\n'
                            '[C], line 4\n'
                            'Inheritances: 2x (2.00 inf)\n'
                            'Propagations: 1x (1.50 inf)')
        chain = '[A]: value\n[B]:\n- [A]\n[C]:\n- [B]\n[D]:\n- [C]\n[E]:\n- [D]\n'
        m = self.make_tab(chain).document_map
        a = m.tooltip_at(self.point(m, m.rows[0]))
        self.assertIn('[A], line 1', a)
        self.assertIn('Propagations: 3x (0.88 inf)', a)

    def test_hover_symbolic_list_body_and_physical_source_lines(self):
        m = self.make_tab('[A]: value\r\n\r\nHolder:\r\n- [B]:\r\n  - [A]\r\n').document_map
        b = m.tooltip_at(self.point(m, m.rows[-1]))
        self.assertIn('[B], line 4', b)
        self.assertNotIn('Holder', b)

    def test_hover_plain_block_uses_source_label_and_zero_counts(self):
        m = self.make_tab('Task:\n- text\n').document_map
        self.assertEqual(m.tooltip_at(self.point(m, m.rows[1])),
                         'Infer Map - (0.00 total inf)\n\n'
                         'Task:, line 1\n'
                         'Inheritances: 0x (0.00 inf)\n'
                         'Propagations: 0x (0.00 inf)')

    def test_tooltip_event_is_safe_and_does_not_navigate(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QHelpEvent
        from PySide6.QtWidgets import QToolTip
        tab = self.make_tab('Task <b>tag</b>:\n- text\n')
        m = tab.document_map
        point = self.point(m, m.rows[0])
        before = (tab.source, tab.editor.textCursor().position(), tab.editor.verticalScrollBar().value())
        with patch.object(QToolTip, 'showText') as show:
            self.app.sendEvent(m, QHelpEvent(QEvent.Type.ToolTip, point, m.mapToGlobal(point)))
        self.assertIn('&lt;b&gt;', show.call_args.args[1])
        self.assertEqual((tab.source, tab.editor.textCursor().position(), tab.editor.verticalScrollBar().value()), before)

    def test_tooltip_event_renders_the_compact_layout(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QHelpEvent
        from PySide6.QtWidgets import QToolTip
        m = self.make_tab('[A]: value\n[B]:\n- [A]\n').document_map
        point = self.point(m, m.rows[0])
        self.app.sendEvent(m, QHelpEvent(QEvent.Type.ToolTip, point, m.mapToGlobal(point)))
        self.assertTrue(QToolTip.isVisible())
        self.assertEqual(QToolTip.text(),
                         '<p style="white-space:pre">Infer Map - (2.00 total inf)<br><br>'
                         '[A], line 1<br>'
                         'Inheritances: 1x (1.00 inf)<br>'
                         'Propagations: 0x (0.00 inf)</p>')
        QToolTip.hideText()

    def test_offscreen_blocks_participate_in_document_normalization(self):
        tab = self.make_tab('[A]: value\n[D]:\n- [A] [A] [A]\n' + '\n' * 100 + 'Unused: text\n')
        m = tab.document_map
        m.scale = 1
        m._fit = False
        self.assertEqual(m._heat_range, (0, 3))
        self.assertEqual(m._document_influence, 4)
        self.assertEqual(m.color_for_owner(1).getRgb()[:3], (85, 0, 170))
        self.assertEqual(len(m.heat.scores), 3)  # Blank lines are not blocks.

    def test_equal_positive_zero_and_canonical_colors(self):
        for source, expected in (('[A]: value\n[B]:\n- [A]\n', (128, 0, 128)),
                                 ('Task:\n- text\n', (0, 0, 255))):
            with self.subTest(source=source):
                m = self.make_tab(source).document_map
                self.assertTrue(all(m.color_for_owner(row.owner).getRgb()[:3] == expected for row in m.rows))

    def test_background_edits_retain_display_heat_then_renormalize_current_graph(self):
        from AgStudio.gui.document_map import MAP_HELP
        tab = self.make_tab('[A]: value\n[D]:\n- [A] [A] [A]\n', background=True)
        self.settle(tab)
        m = tab.document_map
        old_analysis = tab.analysis
        self.assertEqual(m._heat_range, (1, 3))
        old_rows = m.rows
        old_colors = tuple(m.color_for_owner(row.owner) for row in m.rows)
        tab.editor.setPlainText('[A]: value\n[D]:\n- [A]\n')
        self.assertIsNone(m.heat)
        self.assertEqual(m._document_influence, 0)
        self.assertEqual(m.rows, old_rows)
        self.assertEqual(tuple(m.color_for_owner(row.owner) for row in m.rows), old_colors)
        self.assertTrue(m.stale)
        self.assertEqual(m.status_text, 'Pending · stale')
        self.assertEqual(m.tooltip_at(self.point(m, m.rows[0])), MAP_HELP)
        tab._analysis_ready(tab.controller.revision - 1, old_analysis)
        self.assertIsNone(m.heat)
        self.settle(tab)
        self.assertEqual(m._heat_range, (1, 1))
        self.assertEqual(m._document_influence, 2)
        self.assertEqual(m.color_for_owner(0).getRgb()[:3], (128, 0, 128))

    def test_failed_analysis_has_no_stale_scores(self):
        from PySide6.QtTest import QTest
        from AgStudio.gui.document_map import MAP_HELP
        tab = self.make_tab('[A]: value\n[D]:\n- [A] [A]\n', background=True)
        self.settle(tab)
        def failed(*args, **kwargs):
            raise RuntimeError('test failure')
        tab.controller.worker = failed
        tab.editor.insertPlainText(' edit')
        end = time.monotonic() + 5
        while 'unavailable' not in tab.diagnostic_status.text() and time.monotonic() < end:
            QTest.qWait(20)
        self.assertIn('unavailable', tab.diagnostic_status.text())
        self.assertIsNone(tab.document_map.heat)
        m = tab.document_map
        tooltip = m.tooltip_at(self.point(m, m.rows[0]))
        self.assertEqual(tooltip, MAP_HELP + '\n\nInfluence calculation unavailable: RuntimeError: test failure')
        self.assertNotIn('Inheritances:', tooltip)
        self.assertFalse(m._spinner_timer.isActive())
        self.assertTrue(m._spinner.isHidden())

    def test_snapshot_adaptation_runs_in_a_separate_process(self):
        with patch('AgStudio.gui.graph_analysis.build_graph_snapshot',
                   side_effect=AssertionError('production map adaptation ran in the GUI process')) as prepare:
            for background in (False, True):
                with self.subTest(background=background):
                    tab = self.make_tab('[A]: value\n[D]:\n- [A] [A] [A]\n',
                                        background=background)
                    self.assertEqual(tab.document_map._heat_range, (1, 3))
                    self.assertIs(tab.document_map.heat, tab.graph.heat)
                    self.assertIsNotNone(tab.graph.worker_pid)
                    self.assertNotEqual(tab.graph.worker_pid, os.getpid())
                    if background:
                        self.assertIs(tab.controller.graph, tab.graph)
                        self.assertIs(tab.controller.heat, tab.graph.heat)
        prepare.assert_not_called()

    def test_published_analysis_is_reused_and_geometry_does_not_rescore(self):
        from AgStudio.gui import document_map
        from AgStudio.gui.graph_analysis import GraphController
        tab = self.make_tab('[A]: value\n[D]:\n- [A]\n')
        m = tab.document_map
        heat = m.heat
        # Rendering has no semantic resolver or graph calculator to invoke.
        self.assertFalse(hasattr(document_map, 'compute_heat'))
        self.assertFalse(hasattr(document_map, 'resolve'))
        with patch.object(GraphController, 'set_analysis',
                          side_effect=AssertionError('geometry must not request graph work')), \
                patch('AgStudio.gui.document_map.parse',
                      side_effect=AssertionError('must reuse the published syntax tree')):
            m.set_model(tab.document, tab.analysis.tree, heat=heat)
            m.rebuild()
            m.resize(m.width() + 10, m.height())
            m.rebuild()
        self.assertIs(m.heat, heat)
        self.assertEqual(m._heat_range, (1, 1))

    def test_visible_rename_keeps_persisted_panel_key(self):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.user_state import UserState
        from PySide6.QtGui import QAction
        state = UserState()
        window = StudioWindow('current', background=False, user_state=state)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        self.assertEqual(window.panel_actions['document_map'].text(), 'Infer Map')
        self.assertEqual(window.current().document_map.accessibleName(), 'Infer Map')
        self.assertEqual(window.current().map_title.text(), 'Infer Map')
        self.assertEqual(window.current().map_title.accessibleName(), 'Infer Map')
        self.assertEqual(window.current().map_title.toolTip(), 'Toggle Infer Edit (inference paused)')
        self.assertEqual(window.inference_menu.title(), 'Inference mode')
        self.assertNotIn('Document Map', [a.text() for a in window.findChildren(QAction)])
        window.panel_actions['document_map'].trigger()
        self.assertFalse(state.panels['document_map'])
        self.assertTrue(window.current().document_map.isHidden())
        window.panel_actions['document_map'].trigger()
        self.assertTrue(state.panels['document_map'])


if __name__ == '__main__':
    unittest.main()
