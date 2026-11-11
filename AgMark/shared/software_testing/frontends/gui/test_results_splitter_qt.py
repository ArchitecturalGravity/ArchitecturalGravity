"""Results splitter interaction and session-only replacement regressions."""
import os
import unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget
from AgMark.gui.views.results import ResultsProjection, ResultsView, ResultRowProjection
from AgMark.gui.shell.projections import WORKSPACE_TAB_LABELS, WorkspaceProjection
from AgMark.shared.software_testing.frontends.gui import test_shell_runtime_replacement_rendered_qt as shell_fixture


def projection():
    return ResultsProjection("splitter-test", rows=tuple(
        ResultRowProjection(name, 0, "Retained", "Scored", "✓", details="Detail\n" * 30)
        for name in ("First", "Second")))


class ResultsSplitterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def settle(self):
        for _ in range(5):
            self.app.processEvents()

    def test_drag_keyboard_limits_selection_tabs_resize_and_projection(self):
        view = ResultsView(projection())
        tabs = QTabWidget()
        tabs.addTab(view, "Results")
        tabs.addTab(QWidget(), "Other")
        tabs.resize(900, 800)
        tabs.show()
        self.addCleanup(tabs.close)
        self.settle()
        splitter = view.results_splitter
        handle = splitter.handle(1)
        self.assertEqual(splitter.orientation(), Qt.Orientation.Vertical)
        self.assertFalse(splitter.childrenCollapsible())
        self.assertTrue(handle.accessibleName())
        self.assertIn("Drag", handle.accessibleDescription())
        # Start away from the new compact selector's minimum height so both drags can move.
        splitter.setSizes([220, 360])
        self.settle()
        view.cache_table.selectRow(1)
        for delta in (-80, 100):
            before = splitter.sizes()[0]
            center = handle.rect().center()
            QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=center)
            QTest.mouseMove(handle, center + QPoint(0, delta))
            QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=center + QPoint(0, delta))
            self.settle()
            after = splitter.sizes()[0]
            self.assertGreater((after - before) * delta, 0)
            self.assertEqual(view.cache_table.currentIndex().row(), 1)
        handle.setFocus()
        before = splitter.sizes()[0]
        QTest.keyClick(handle, Qt.Key.Key_Up)
        self.assertLess(splitter.sizes()[0], before)
        QTest.keyClick(handle, Qt.Key.Key_Down)
        self.assertEqual(splitter.sizes()[0], before)
        chosen = splitter.sizes()
        for _ in range(3):
            tabs.setCurrentIndex(1); tabs.setCurrentIndex(0)
            view.set_projection(projection())
            self.settle()
            self.assertEqual(splitter.sizes(), chosen)
            self.assertEqual(view.cache_table.currentIndex().row(), 1)
            self.assertEqual("Second", view._selected_row.treatment)
        view.set_projection(ResultsProjection("empty", empty_state="No retained results"))
        self.settle()
        self.assertTrue(splitter.isHidden())
        view.set_projection(projection())
        self.settle()
        self.assertEqual(splitter.sizes(), chosen)
        for sizes in ([0, 1000], [1000, 0]):
            splitter.setSizes(sizes)
            self.settle()
            self.assertGreaterEqual(view.treatment_scroll.height(), 64)
            self.assertGreaterEqual(view.cache_table.height(), 160)
        for width, height in ((560, 350), (1000, 900), (600, 500)):
            tabs.resize(width, height)
            self.settle()
            self.assertEqual(2, len(view.treatment_buttons))
            self.assertEqual(2, view.cache_table.table_model.rowCount())
            self.assertEqual("First", view._selected_row.treatment)
            # Six columns retain local horizontal overflow at narrow sizes.
            self.assertGreaterEqual(view.cache_table.horizontalScrollBar().maximum(), 0)
            self.settle()
            for component in (view.treatment_scroll, view.cache_table):
                origin = component.mapTo(view, QPoint(0, 0))
                self.assertGreaterEqual(origin.y(), 0)
                self.assertLessEqual(origin.y() + component.height(), view.height())
                self.assertGreaterEqual(component.height(), component.minimumHeight())

    def test_shell_replacements_and_empty_interlude_keep_divider(self):
        # Reuse only the shell fixture, without running its broader Qt suite.
        helper = shell_fixture.RenderedShellRuntimeReplacementTests()
        self.addCleanup(helper.doCleanups)
        window = helper._window()
        self.addCleanup(window.close)
        def workspace():
            return WorkspaceProjection(progress=QWidget(), results=ResultsView(projection()),
                evidence=QWidget(), verification=QWidget(), reports=QWidget())
        first = workspace()
        window.set_workspace_projection(first, run_id="splitter-test")
        window.workspace_tabs.setCurrentIndex(WORKSPACE_TAB_LABELS.index("Results"))
        self.settle()
        first.results.results_splitter.setSizes([180, 500])
        self.settle()
        chosen = first.results.results_splitter.sizes()
        for _ in range(3):
            replacement = workspace()
            window.set_workspace_projection(replacement, run_id="splitter-test")
            self.settle()
            self.assertEqual(replacement.results.results_splitter.sizes(), chosen)
        window.clear_workspace_projection()
        self.settle()
        replacement = workspace()
        window.set_workspace_projection(replacement, run_id="splitter-test")
        self.settle()
        self.assertEqual(replacement.results.results_splitter.sizes(), chosen)
