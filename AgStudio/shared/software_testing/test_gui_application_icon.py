"""App/window identity and packaged Windows icon regressions."""
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 is not installed")
class ApplicationIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_windows_icon_includes_native_sizes_and_brand_colors(self):
        from PySide6.QtGui import QIcon
        from AgStudio.gui.application_icon import ICON_DIRECTORY
        raw = (ICON_DIRECTORY / "agstudio.ico").read_bytes()
        self.assertEqual(struct.unpack("<HHH", raw[:6]), (0, 1, 9))
        icon = QIcon(str(ICON_DIRECTORY / "agstudio.ico"))
        self.assertEqual({size.width() for size in icon.availableSizes()},
                         {16, 20, 24, 32, 40, 48, 64, 128, 256})
        for size in icon.availableSizes():
            image = icon.pixmap(size).toImage()
            self.assertFalse(image.isNull())
            self.assertEqual(image.pixelColor(0, 0).name(), "#000000")
        image = icon.pixmap(256, 256).toImage()
        self.assertEqual(image.pixelColor(30, 100).name(), "#ff8c00")
        self.assertEqual(image.pixelColor(96, 85).name(), "#ffd700")

    def test_assets_resolve_independently_of_working_directory(self):
        from AgStudio.gui.application_icon import application_icon
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                for platform in ("win32", "linux"):
                    with patch("AgStudio.gui.application_icon.sys.platform", platform):
                        self.assertFalse(application_icon().pixmap(32, 32).isNull())
            finally:
                os.chdir(previous)

    def test_windows_identity_uses_shell_only_on_windows(self):
        from AgStudio.gui.application_icon import set_windows_app_id, WINDOWS_APP_ID
        shell = Mock()
        with patch("ctypes.windll", create=True) as libraries:
            libraries.shell32 = shell
            with patch("AgStudio.gui.application_icon.sys.platform", "linux"):
                set_windows_app_id()
            shell.SetCurrentProcessExplicitAppUserModelID.assert_not_called()
            with patch("AgStudio.gui.application_icon.sys.platform", "win32"):
                set_windows_app_id()
            shell.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(WINDOWS_APP_ID)
            shell.SetCurrentProcessExplicitAppUserModelID.side_effect = OSError("No shell")
            with patch("AgStudio.gui.application_icon.sys.platform", "win32"):
                set_windows_app_id()  # Branding must never block startup.

    def test_window_has_icon_even_when_created_without_main(self):
        from PySide6.QtCore import QSettings
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        from AgStudio.gui.user_state import UserState
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "state.ini"), QSettings.Format.IniFormat)
            window = StudioWindow("test", background=False,
                                  user_state=UserState(settings),
                                  scheme_store=SchemeStore(Path(directory) / "colors"))
            try:
                self.assertFalse(window.windowIcon().pixmap(32, 32).isNull())
            finally:
                window.close()
                window.deleteLater()

    def test_launcher_sets_application_icon_before_constructing_window(self):
        from AgStudio.gui import app as module
        events = []
        fake_app = Mock()
        fake_app.setWindowIcon.side_effect = lambda icon: events.append("icon")
        fake_app.exec.return_value = 0
        with patch.object(module, "set_windows_app_id", side_effect=lambda: events.append("identity")), \
             patch.object(module, "QApplication") as app_type, \
             patch.object(module, "StudioWindow") as window_type:
            app_type.instance.side_effect = lambda: events.append("application") or fake_app
            window_type.side_effect = lambda *args: events.append("window") or Mock()
            self.assertEqual(module.main(["--arcgrav-version", "test"]), 0)
        self.assertEqual(events, ["identity", "application", "icon", "window"])
