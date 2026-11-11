"""Pending map frames stay visible without becoming current source evidence."""
import importlib.util
import os
import json
import tempfile
import time
from functools import partial
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def _trace_map_process(request, marker):
    import sys
    from AgStudio.shared.graph import map_request
    original = map_request.build_graph_snapshot

    def traced(*args, **kwargs):
        Path(marker).write_text(json.dumps({
            'pid': os.getpid(),
            'qt_loaded': any(name.startswith('PySide6') for name in sys.modules),
        }), encoding='utf-8')
        return original(*args, **kwargs)

    with patch.object(map_request, 'build_graph_snapshot', side_effect=traced):
        return map_request.calculate_map_request(request)


class MapProcessTests(unittest.TestCase):
    def test_global_process_bookkeeping_cannot_block_gui_cancellation(self):
        from AgStudio.shared.feature_worker import FeatureWorker
        from AgStudio.shared.graph.core import GraphSnapshot, calculate_graph
        from AgStudio.shared.graph.worker import GraphWorker
        from AgStudio.shared.process_lifecycle import PROCESS_LOCK
        from AgStudio.shared.software_testing.graph_worker_fixtures import controllable_calculation
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'started'
            worker = GraphWorker(partial(controllable_calculation, started_file=str(marker)))
            feature = FeatureWorker(calculate_graph)
            try:
                self.assertIs(worker._process_lock, PROCESS_LOCK)
                self.assertIs(feature._process_lock, PROCESS_LOCK)
                worker.submit(1, GraphSnapshot((1,), (), ()))
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists())
                # Another manager may be starting/reaping a process. UI-facing
                # methods only discard the generation; they never wait on it.
                with PROCESS_LOCK:
                    started = time.monotonic()
                    worker.cancel()
                    worker.close()
                    self.assertLess(time.monotonic() - started, 0.2)
                self.assertTrue(worker.wait_closed(10))
                self.assertIsNone(worker.active_pid)
                self.assertIsNone(worker.poll())
            finally:
                worker.close()
                feature.close()
                self.assertTrue(worker.wait_closed(10))
                self.assertTrue(feature.wait_closed(10))

    def test_adaptation_and_scoring_share_qt_free_child_in_both_modes(self):
        from AgStudio.shared.analysis_snapshot import freeze_analysis
        from AgStudio.shared.graph.adapter import build_graph_snapshot
        from AgStudio.shared.graph.core import calculate_graph
        from AgStudio.shared.graph.map_request import MapRequest
        from AgStudio.shared.graph.worker import GraphWorker
        from AgStudio.shared.lint import analyze
        analysis = analyze('[A]: value\n[B]:\n- [A] [A]\n')
        for mode in ('heuristic', 'semantic_triad_1', 'semantic_triad_2'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                marker = Path(directory) / 'map-process.json'
                worker = GraphWorker(partial(_trace_map_process, marker=str(marker)),
                                     input_type=MapRequest)
                try:
                    worker.submit(9, MapRequest(freeze_analysis(analysis), mode))
                    deadline, outcome = time.monotonic() + 10, None
                    while outcome is None and time.monotonic() < deadline:
                        outcome = worker.poll()
                        time.sleep(0.01)
                    self.assertIsNotNone(outcome)
                    self.assertIsNone(outcome.error)
                    expected = calculate_graph(build_graph_snapshot(
                        analysis.tree, analysis.semantics, mode=mode))
                    self.assertEqual(outcome.result, expected)
                    record = json.loads(marker.read_text(encoding='utf-8'))
                    self.assertNotEqual(record['pid'], os.getpid())
                    self.assertFalse(record['qt_loaded'])
                finally:
                    worker.close()
                    self.assertTrue(worker.wait_closed(10))


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class PendingMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_map(self, source, mode='heuristic'):
        from AgStudio.gui.app import SourceEditor
        from AgStudio.gui.document_map import DocumentMap
        editor = SourceEditor()
        editor.resize(650, 480)
        editor.setPlainText(source)
        editor.show()
        view = DocumentMap(editor, mode=mode)
        view.resize(180, 480)
        view.show()
        self.app.processEvents()
        self.addCleanup(editor.deleteLater)
        self.addCleanup(editor.close)
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        result, heat = self.analysis(source, mode)
        view.set_model(result.document, result.tree, heat=heat)
        view.rebuild()
        self.assertTrue(view._heat_ready)
        return editor, view

    def analysis(self, source, mode='heuristic'):
        from AgStudio.shared.lint import analyze
        from AgStudio.gui.inference_heat import compute_heat
        result = analyze(source)
        return result, compute_heat(result.tree, result.semantics, mode=mode)

    def point(self, view, row):
        from PySide6.QtCore import QPoint
        return QPoint(round((row.left + row.right) / 2 * view.horizontal_scale),
                      round(view.map_origin().y() + (row.top + row.height / 2) * view.scale))

    def frame(self, view):
        return (view.rows, view.shapes, view.path, view.extent, view.block_tops,
                tuple(view.color_for_owner(row.owner).getRgb() for row in view.rows))

    def test_canonical_snapshot_bypasses_all_parent_process_map_preparation(self):
        from PySide6.QtTest import QTest
        from AgStudio.gui.graph_analysis import GraphController
        from AgStudio.shared.analysis_snapshot import freeze_analysis
        analysis, _ = self.analysis('[A]: value\n[B]:\n- [A]\n')
        controller = GraphController()
        self.addCleanup(controller.worker.wait_closed, 10)
        self.addCleanup(controller.close)
        results, failures = [], []
        controller.ready.connect(lambda revision, heat: results.append((revision, heat)))
        controller.failed.connect(lambda revision, error: failures.append(error))
        with patch('AgStudio.gui.graph_analysis._PREPARATION_POOL.submit',
                   side_effect=AssertionError('canonical snapshot must bypass thread')), \
                patch('AgStudio.gui.graph_analysis.build_graph_snapshot',
                      side_effect=AssertionError('map adaptation must run in its child')):
            controller.set_analysis(12, analysis, snapshot=freeze_analysis(analysis))
            deadline = time.monotonic() + 10
            while not results and not failures and time.monotonic() < deadline:
                QTest.qWait(10)
        self.assertEqual(failures, [])
        self.assertEqual([revision for revision, _ in results], [12])
        self.assertEqual(tuple(score.total for score in results[0][1].scores.values()), (1, 1))

    def test_edits_retain_exact_geometry_and_colors_in_all_three_modes(self):
        for mode in ('heuristic', 'semantic_triad_1', 'semantic_triad_2'):
            with self.subTest(mode=mode):
                editor, view = self.make_map('[A]: value\n[B]:\n- [A] [A]\n', mode)
                frame, rebuilds = self.frame(view), view.rebuild_count
                point = self.point(view, view.rows[-1])
                editor.insertPlainText('different\n')
                self.assertTrue(view.stale)
                self.assertEqual(view.status_text, 'Pending · stale')
                self.assertIn('Pending · stale', view.accessibleDescription())
                self.assertIsNone(view._document)
                self.assertIsNone(view._tree)
                self.assertIsNone(view.heat)
                self.assertFalse(view._heat_ready)
                self.assertEqual(view.tooltip_at(point), view.mode_help)
                view.rebuild()
                view.schedule_rebuild()
                self.assertFalse(view._timer.isActive())
                self.assertEqual(view.rebuild_count, rebuilds)
                self.assertEqual(self.frame(view), frame)

    def test_partial_model_cannot_replace_last_frame_until_current_heat_arrives(self):
        editor, view = self.make_map('[A]: value\n[B]:\n- [A] [A]\n')
        frame = self.frame(view)
        replacement = 'Fresh:\n- substantially wider content\nTail: value\n'
        editor.setPlainText(replacement)
        result, heat = self.analysis(replacement)
        view.set_model(result.document, result.tree)
        view.rebuild()
        self.assertEqual(self.frame(view), frame)
        self.assertTrue(view.stale)
        view.set_model(result.document, result.tree, heat=heat)
        # Ready means both geometry and heat have been atomically replaced.
        self.assertFalse(view._heat_ready)
        self.assertEqual(self.frame(view), frame)
        view.rebuild()
        self.assertFalse(view.stale)
        self.assertEqual(view.status_text, '')
        self.assertTrue(view._heat_ready)
        self.assertEqual(view._document.source, replacement)
        self.assertNotEqual(self.frame(view), frame)
        self.assertIn('Fresh:', view.tooltip_at(self.point(view, view.rows[0])))

    def test_stale_revision_and_edit_before_geometry_publication_are_rejected(self):
        editor, view = self.make_map('[A]: value\n[B]:\n- [A]\n')
        frame = self.frame(view)
        editor.insertPlainText('new ')
        view.invalidate(4)
        result, heat = self.analysis(editor.toPlainText())
        view.set_model(result.document, result.tree, heat=heat, revision=3)
        self.assertIsNone(view.heat)
        self.assertEqual(self.frame(view), frame)
        view.set_model(result.document, result.tree, heat=heat, revision=4)
        editor.insertPlainText('newer ')
        view.rebuild()
        self.assertFalse(view._heat_ready)
        self.assertEqual(self.frame(view), frame)

    def test_failure_keeps_display_but_blocks_hover_and_source_navigation(self):
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QHelpEvent, QWheelEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QToolTip
        editor, view = self.make_map('[A]: value\n[B]:\n- [A] [A]\n')
        frame = self.frame(view)
        point = self.point(view, view.rows[-1])
        view.invalidate()
        view.set_error('replacement failed')
        self.assertEqual(view.status_text, 'Unavailable · stale')
        self.assertEqual(self.frame(view), frame)
        tooltip = view.tooltip_at(point)
        self.assertIn('replacement failed', tooltip)
        self.assertNotIn('Inheritances:', tooltip)
        before = (editor.toPlainText(), editor.textCursor().position(),
                  editor.verticalScrollBar().value())
        with patch.object(QToolTip, 'showText') as show:
            self.app.sendEvent(view, QHelpEvent(QEvent.Type.ToolTip, point, view.mapToGlobal(point)))
        self.assertNotIn('Inheritances:', show.call_args.args[1])
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=point)
        wheel = QWheelEvent(QPointF(point), QPointF(point), QPoint(), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        view.wheelEvent(wheel)
        self.assertEqual(before, (editor.toPlainText(), editor.textCursor().position(),
                                  editor.verticalScrollBar().value()))

    def test_hidden_map_does_no_pending_geometry_work_and_reopens_fresh(self):
        editor, view = self.make_map('[A]: value\n[B]:\n- [A]\n')
        view.set_analysis_enabled(False)
        before = view.rebuild_count
        editor.setPlainText('Latest: value\n')
        result, heat = self.analysis(editor.toPlainText())
        with patch.object(view, '_geometry', side_effect=AssertionError('hidden geometry')):
            view.invalidate(8)
            view.set_model(result.document, result.tree, heat=heat, revision=8)
            view.schedule_rebuild()
            view.rebuild()
        self.assertEqual(view.rebuild_count, before)
        self.assertFalse(view._timer.isActive())
        self.assertEqual(view.rows, ())
        view.set_analysis_enabled(True)
        view.set_model(result.document, result.tree, heat=heat, revision=8)
        view.rebuild()
        self.assertEqual(view._document.source, 'Latest: value\n')
        self.assertTrue(view._heat_ready)
        self.assertFalse(view.stale)

    def test_spinner_is_only_visible_change_at_top_left_while_pending(self):
        editor, view = self.make_map('[A]: value\n[B]:\n- [A] [A]\n')
        self.assertFalse(view._spinner_timer.isActive())
        self.assertTrue(view._spinner.isHidden())
        before = view.grab().toImage()
        frame = self.frame(view)
        geometry = (view.size(), view.extent, view.scale, view.horizontal_scale)
        view.invalidate()
        self.app.processEvents()
        self.assertTrue(view._spinner.isVisible())
        self.assertTrue(view._spinner_timer.isActive())
        self.assertEqual(view._spinner.geometry().getRect(), (4, 4, 20, 20))
        self.assertIn('Pending · stale', view.accessibleDescription())
        after = view.grab().toImage()
        scale = after.devicePixelRatio()
        changed = [(x, y) for y in range(after.height()) for x in range(after.width())
                   if before.pixel(x, y) != after.pixel(x, y)]
        self.assertTrue(changed)
        self.assertTrue(all(4 * scale <= x < 24 * scale and 4 * scale <= y < 24 * scale
                            for x, y in changed), 'pending text or paint escaped the small overlay')
        self.assertEqual(self.frame(view), frame)
        self.assertEqual((view.size(), view.extent, view.scale, view.horizontal_scale), geometry)
        phase = view._spinner_phase
        view._advance_spinner()
        self.assertNotEqual(view._spinner_phase, phase)
        self.assertNotEqual(view.grab().toImage(), after)

    def test_spinner_ticks_only_repaint_its_overlay_not_map_geometry(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QEvent, QObject
        editor, view = self.make_map('[A]: value\n[B]:\n- [A] [A]\n')
        view.invalidate()
        self.app.processEvents()
        view.grab()
        self.app.processEvents()
        count = view.rebuild_count
        frame = self.frame(view)
        ticks, regions = [], []

        class PaintObserver(QObject):
            def eventFilter(self, watched, event):
                if event.type() == QEvent.Type.Paint:
                    regions.append(event.region().boundingRect())
                return False

        observer = PaintObserver(view)
        view.installEventFilter(observer)
        view._spinner_timer.timeout.connect(lambda: ticks.append(view._spinner_phase))
        with patch.object(view, '_geometry', side_effect=AssertionError('spinner rebuilt geometry')), \
                patch.object(view, 'rebuild', side_effect=AssertionError('spinner rebuilt map')), \
                patch.object(view, 'update') as parent_update:
            QTest.qWait(260)
            parent_update.assert_not_called()
        self.assertTrue(regions)
        self.assertTrue(all(view._spinner.geometry().contains(region) for region in regions))
        self.assertEqual(view._spinner_timer.interval(), 80)
        self.assertGreaterEqual(len(ticks), 2)
        self.assertLessEqual(len(ticks), 5)
        self.assertEqual(view.rebuild_count, count)
        self.assertEqual(self.frame(view), frame)

    def test_spinner_stops_for_current_error_disabled_hidden_and_closed_maps(self):
        from PySide6.QtWidgets import QWidget
        editor, view = self.make_map('[A]: value\n[B]:\n- [A]\n')
        result, heat = self.analysis(editor.toPlainText())
        view.invalidate()
        self.assertTrue(view._spinner_timer.isActive())
        view.set_model(result.document, result.tree, heat=heat)
        view.rebuild()
        self.assertFalse(view._spinner_timer.isActive())
        self.assertTrue(view._spinner.isHidden())
        view.invalidate()
        view.set_error('test failure')
        self.assertFalse(view._spinner_timer.isActive())
        self.assertTrue(view._spinner.isHidden())
        self.assertIn('Unavailable', view.status_text)
        view.invalidate()
        self.assertTrue(view._spinner_timer.isActive())
        view.hide()
        self.assertFalse(view._spinner_timer.isActive())
        self.assertTrue(view._spinner.isHidden())
        view.show()
        self.assertTrue(view._spinner_timer.isActive())
        view.set_analysis_enabled(False)
        self.assertFalse(view._spinner_timer.isActive())
        self.assertTrue(view._spinner.isHidden())
        view.set_analysis_enabled(True)
        self.assertTrue(view._spinner_timer.isActive())
        view.close()
        self.assertFalse(view._spinner_timer.isActive())
        self.assertTrue(view._spinner.isHidden())
        # Tab changes hide an ancestor, rather than the map itself.
        host = QWidget()
        self.addCleanup(host.deleteLater)
        self.addCleanup(host.close)
        view.setParent(host)
        view.show()
        host.show()
        self.app.processEvents()
        self.assertTrue(view._spinner_timer.isActive())
        host.hide()
        self.assertFalse(view._spinner_timer.isActive())
        host.show()
        self.assertTrue(view._spinner_timer.isActive())

    def test_spinner_transparency_animation_cleanup_and_palette_contrast(self):
        from copy import deepcopy
        from PySide6.QtCore import Qt
        editor, view = self.make_map('Section:\n- body\n')
        view.invalidate()
        view._spinner_timer.stop()  # Step phases deterministically below.
        self.assertFalse(view._spinner.autoFillBackground())
        self.assertFalse(view._spinner.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent))
        geometry = (view.size(), view.extent, view.scale, view.horizontal_scale)
        rebuilds = view.rebuild_count
        for background, foreground in (([245, 245, 245, 255], [25, 25, 25, 255]),
                                       ([15, 15, 15, 255], [235, 235, 235, 255]),
                                       ([245, 245, 245, 255], [245, 245, 245, 255]),
                                       ([15, 15, 15, 255], [15, 15, 15, 255])):
            with self.subTest(background=background, foreground=foreground):
                scheme = deepcopy(editor.color_scheme)
                scheme['editor']['background'] = background
                scheme['editor']['foreground'] = foreground
                editor.apply_color_scheme(scheme)
                view._spinner.hide()
                self.app.processEvents()
                underlying = view.grab().toImage()
                view._spinner.show()
                view._spinner_phase = 0
                first = view.grab().toImage()
                ratio = first.devicePixelRatio()
                # Cover both silhouette and empty-map pixels, not just the
                # editor background: a flat backplate must fail this check.
                clear_pixels = [(x, y) for y in range(int(20 * ratio))
                                for x in range(int(20 * ratio))
                                if ((x + .5) / ratio - 10) ** 2
                                + ((y + .5) / ratio - 10) ** 2 < 25
                                or ((x + .5) / ratio - 10) ** 2
                                + ((y + .5) / ratio - 10) ** 2 > 90]
                offset = int(4 * ratio)
                colors = {underlying.pixel(x + offset, y + offset) for x, y in clear_pixels}
                self.assertGreater(len(colors), 1)
                frames = []
                for _ in range(12):
                    view._advance_spinner()
                    self.app.processEvents()
                    frame = view.grab().toImage()
                    frames.append(frame)
                    for x, y in clear_pixels:
                        self.assertEqual(frame.pixel(x + offset, y + offset),
                                         underlying.pixel(x + offset, y + offset))
                    self.assertNotEqual(frame, underlying)
                self.assertNotEqual(frames[0], first)
                self.assertEqual(frames[-1], first, 'animation left old arc pixels behind')
                view._spinner.hide()
                self.app.processEvents()
                self.assertEqual(view.grab().toImage(), underlying)
        self.assertEqual((view.size(), view.extent, view.scale, view.horizontal_scale), geometry)
        self.assertEqual(view.rebuild_count, rebuilds)

    def test_set_model_none_is_the_same_safe_invalidation_api(self):
        editor, view = self.make_map('Section:\n- body\n')
        frame = self.frame(view)
        view.set_model(None)
        view.rebuild()
        self.assertEqual(self.frame(view), frame)
        self.assertTrue(view.stale)
        self.assertIsNone(view.heat)


if __name__ == '__main__':
    unittest.main()
