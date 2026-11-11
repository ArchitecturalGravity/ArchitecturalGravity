"""Workspace identity, available width, and overflow survive projection replacement."""
import os
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from AgMark.gui.design_system.theme import apply_application_theme
from AgMark.gui.projection.workspace.projector import SharedWorkspaceProjector
from AgMark.gui.shell.window import BenchmarkShellWindow
from AgMark.gui.shell.projections import WORKSPACE_TAB_LABELS
from AgMark.shared.software_testing.frontends.gui.test_retained_evidence_projection import (
    _accepted_run, _active_plan,
)


class WorkspacePaddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_application_theme(cls.app)

    def test_pages_preserve_identity_width_and_overflow_across_projection_states(self):
        pixmap = QPixmap(16, 16)
        pixmap.fill()
        window = BenchmarkShellWindow(application_icon=QIcon(pixmap))
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.show()
        projector = SharedWorkspaceProjector(SimpleNamespace(report_bundle=None, verification=None))
        active = projector.active_execution("generation-padding", _active_plan())
        terminal = projector("select_run", _accepted_run(generation_id="generation-padding"), SimpleNamespace())

        def check_pages(state):
            for width in (1180, 800, 1440):
                window.resize(width, 812)
                for index, label in enumerate(WORKSPACE_TAB_LABELS):
                    if not window.workspace_tabs.isTabVisible(index):
                        continue
                    with self.subTest(state=state, width=width, tab=label):
                        window.workspace_tabs.setCurrentIndex(index)
                        for _ in range(5):
                            self.app.processEvents()
                        scroll = window.workspace_tabs.widget(index)
                        page = window.workspace_pages[label]
                        self.assertIs(scroll.widget(), page)
                        if hasattr(page, "_available_width"):
                            self.assertEqual(scroll.viewport().width(), page._available_width)
                        self.assertEqual(0, window.workspace_scroll.horizontalScrollBar().maximum())

        check_pages("idle")
        for state, projection in (("active", active), ("completed", terminal),
                                  ("saved-reselection", terminal), ("active-again", active)):
            window.set_workspace_projection(projection, run_id="generation-padding")
            check_pages(state)
        window.clear_workspace_projection()
        check_pages("cleared")
