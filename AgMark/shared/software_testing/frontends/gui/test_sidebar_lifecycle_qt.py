"""Deferred sidebar restoration follows the receiving window's lifetime."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from AgMark.gui.shell.window import BenchmarkShellWindow, SidebarProjection


class SidebarLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def _window(self):
        pixmap = QPixmap(16, 16)
        pixmap.fill()
        return BenchmarkShellWindow(
            application_icon=QIcon(pixmap),
            shell_preferences={}, console_preferences={},
            sidebar_projection=SidebarProjection(),
        )

    def test_queued_restore_runs_for_live_window(self):
        window = self._window()
        try:
            with patch.object(window, "_restore_sidebar_refresh_state",
                              wraps=window._restore_sidebar_refresh_state) as restore:
                window.set_sidebar_projection(SidebarProjection())
                restore.assert_not_called()
                QApplication.processEvents()
                restore.assert_called_once_with(0, 0, None)
        finally:
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_queued_restore_is_cancelled_when_window_is_deleted(self):
        window = self._window()
        with patch("sys.excepthook") as errors:
            window.set_sidebar_projection(SidebarProjection())
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QApplication.processEvents()
            errors.assert_not_called()
