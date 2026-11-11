"""Provider-free in-flight feedback and interruption regressions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from threading import Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication
from AgMark.gui.application import BenchmarkDesktopApplication
from AgMark.gui.application.contracts import ApplicationProjectionUpdate
from AgMark.gui.shell.window import SidebarProjection


class OperationActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.release = Event()
        self.entered = Event()
        self.calls = []
        self.fail = False
        def work(*args):
            self.calls.append((args, get_ident()))
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError("fixture timed out")
            if self.fail:
                raise RuntimeError("controlled fixture failure")
            return object()
        names = ("discover", "build_plan", "select_run", "delete_run", "accept_plan",
                 "start_benchmark")
        self.boundary = SimpleNamespace(**{name: work for name in names})
        self.sidebar = SidebarProjection(build_plan_available=True, model_visible=False,
                                         credentials_visible=False)
        self.desktop = BenchmarkDesktopApplication(
            application_icon=QIcon(QPixmap(16, 16)),
            shared_application_boundary=self.boundary,
            initial_sidebar_projection=self.sidebar,
            projector=lambda *_: ApplicationProjectionUpdate(
                sidebar=self.sidebar, application_status=("Ready", "neutral")),
        )
        self.window = self.desktop.window
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.release.set()
        self.wait_for(lambda: not self.desktop._pending_commands)
        self.window.close()
        self.app.processEvents()

    def wait_for(self, predicate):
        deadline = monotonic() + 3
        while not predicate() and monotonic() < deadline:
            self.app.processEvents()
            sleep(.005)
        self.assertTrue(predicate())

    def build(self):
        self.window.build_plan_button.click()
        self.assertTrue(self.entered.wait(1))
        self.assertTrue(self.window.operation_banner.isVisible())
        self.assertTrue(self.window.shell_status_bar.isAncestorOf(self.window.operation_banner))
        self.assertEqual(self.window.workspace_layout.indexOf(self.window.operation_banner), -1)
        self.assertTrue(self.window.shell_status_bar.isVisible())
        self.assertEqual(self.window.operation_label.text(), "Building plan…")
        self.assertTrue(self.window.operation_progress.busy)
        self.assertFalse(self.window.build_plan_button.isEnabled())

    def test_immediate_feedback_duplicate_conflicts_and_responsive_navigation(self):
        self.build()
        self.window.build_plan_button.click()
        self.desktop.request_build_plan(self.window.sidebar_input_snapshot())
        self.desktop.request_accept_plan()
        self.desktop.request_start_benchmark()
        self.desktop.request_delete_run("fixture")
        self.assertEqual(len(self.calls), 1)
        self.assertNotEqual(self.calls[0][1], get_ident())
        self.window.workspace_tabs.setCurrentIndex(2)
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        self.app.processEvents()
        self.assertTrue(heartbeat)
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 2)
        self.window.set_sidebar_projection(self.sidebar)
        self.assertFalse(self.window.build_plan_button.isEnabled())
        self.release.set()
        self.wait_for(lambda: not self.desktop._pending_commands)
        self.assertFalse(self.window.operation_banner.isVisible())
        self.assertTrue(self.window.shell_status_bar.isVisible())
        self.assertFalse(self.window.operation_progress.busy)
        self.assertTrue(self.window.build_plan_button.isEnabled())
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 2)

    def test_failure_restores_controls_and_shows_failure(self):
        self.fail = True
        self.build()
        self.release.set()
        self.wait_for(lambda: not self.desktop._pending_commands)
        self.assertTrue(self.window.build_plan_button.isEnabled())
        self.assertFalse(self.window.operation_banner.isVisible())
        self.assertTrue(self.window.shell_status_bar.isVisible())
        self.assertFalse(self.window.operation_progress.busy)
        self.assertEqual(self.window._requested_application_status, ("Build Plan failed", "error"))

    def test_dispatch_failure_restores_controls(self):
        self.desktop._authority_dispatcher = lambda _: (_ for _ in ()).throw(RuntimeError("cannot dispatch"))
        self.window.build_plan_button.click()
        self.assertFalse(self.desktop._pending_commands)
        self.assertTrue(self.window.build_plan_button.isEnabled())
        self.assertFalse(self.window.operation_banner.isVisible())
        self.assertTrue(self.window.shell_status_bar.isVisible())
        self.assertFalse(self.window.operation_progress.busy)

    def test_close_while_pending_does_not_reopen(self):
        self.build()
        self.window.close()
        self.release.set()
        self.wait_for(lambda: not self.desktop._pending_commands)
        self.assertFalse(self.window.isVisible())

    def test_cancel_delete_does_not_dispatch_or_show_activity(self):
        with patch.object(self.window, "_confirm_delete_run", return_value=False):
            self.window._invoke_delete_run("fixture")
        self.assertEqual(self.calls, [])
        self.assertFalse(self.window.operation_banner.isVisible())
        self.assertTrue(self.window.shell_status_bar.isVisible())
        self.assertFalse(self.window.operation_progress.busy)

    def test_completion_sound_waits_for_all_work_and_preparation_and_plays_once(self):
        preparation_started, preparation_release = Event(), Event()

        def prepare(*_):
            preparation_started.set()
            if not preparation_release.wait(3):
                raise RuntimeError("preparation fixture timed out")
            return None

        self.desktop._projector.prepare_result = prepare
        sound_threads = []
        with patch("AgMark.gui.application.desktop.QApplication.beep",
                   side_effect=lambda: sound_threads.append(get_ident())) as beep:
            try:
                self.desktop.request_start_benchmark()
                self.assertTrue(self.entered.wait(1))
                self.app.processEvents()
                self.desktop._receive_prepared_result(
                    "start_benchmark", object(), None,
                    self.desktop._command_revisions["start_benchmark"] - 1,
                    self.desktop._workspace_revision, None)
                beep.assert_not_called()
                self.release.set()
                self.wait_for(preparation_started.is_set)
                beep.assert_not_called()
                preparation_release.set()
                self.wait_for(lambda: not self.desktop._pending_commands)
                beep.assert_called_once_with()
                self.assertEqual(sound_threads, [get_ident()])
                # Duplicate delivery and later UI updates are not new runs.
                self.desktop._receive_prepared_result(
                    "start_benchmark", object(), None,
                    self.desktop._command_revisions["start_benchmark"],
                    self.desktop._workspace_revision, None)
                self.app.processEvents()
                beep.assert_called_once_with()
                self.desktop.request_start_benchmark()
                self.wait_for(lambda: not self.desktop._pending_commands)
                self.assertEqual(beep.call_count, 2)
            finally:
                preparation_release.set()

    def test_completion_sound_survives_selection_change(self):
        with patch("AgMark.gui.application.desktop.QApplication.beep") as beep:
            self.desktop.request_start_benchmark()
            self.assertTrue(self.entered.wait(1))
            self.desktop.request_select_run("fixture-other")
            self.wait_for(lambda: len(self.calls) == 2)
            self.release.set()
            self.wait_for(lambda: not self.desktop._pending_commands)
            beep.assert_called_once_with()

    def test_completion_sound_ignores_other_operations_and_failures(self):
        with patch("AgMark.gui.application.desktop.QApplication.beep") as beep:
            self.build()
            self.release.set()
            self.wait_for(lambda: not self.desktop._pending_commands)
            beep.assert_not_called()
            self.fail = True
            self.desktop.request_start_benchmark()
            self.wait_for(lambda: not self.desktop._pending_commands)
            beep.assert_not_called()

    def test_completion_sound_ignores_preparation_failure_and_closed_window(self):
        def prepare(*_):
            raise RuntimeError("controlled preparation failure")

        self.desktop._projector.prepare_result = prepare
        with patch("AgMark.gui.application.desktop.QApplication.beep") as beep:
            self.release.set()
            self.desktop.request_start_benchmark()
            self.wait_for(lambda: not self.desktop._pending_commands)
            beep.assert_not_called()
            self.release.clear()
            self.entered.clear()
            self.desktop.request_start_benchmark()
            self.assertTrue(self.entered.wait(1))
            self.window.close()
            self.release.set()
            self.app.processEvents()
            beep.assert_not_called()

    def test_completion_feedback_allows_selection_and_coalesces_repeats(self):
        self.desktop.request_start_benchmark()
        self.assertTrue(self.entered.wait(1))
        self.assertEqual(self.window.operation_label.text(), "Running benchmark…")
        self.assertTrue(self.window.sidebar.isEnabled())
        self.desktop.request_start_benchmark()
        self.assertEqual(len(self.calls), 1)
        self.desktop.request_select_run("fixture-other")
        self.wait_for(lambda: len(self.calls) == 2)
        self.release.set()
        self.wait_for(lambda: not self.desktop._pending_commands)
        self.assertFalse(self.window.operation_banner.isVisible())
        self.assertTrue(self.window.shell_status_bar.isVisible())
        self.assertFalse(self.window.operation_progress.busy)

if __name__ == "__main__":
    unittest.main()
