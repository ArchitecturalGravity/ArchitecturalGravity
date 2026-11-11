"""Content colors stay in viewports, leaving native scrollbar tracks alone."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import importlib.util
import unittest
from copy import deepcopy
from unittest.mock import patch
if not importlib.util.find_spec("PySide6"):
    raise unittest.SkipTest("PySide6 is not installed")


class ScrollbarBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global Qt, QColor, QPalette, QApplication, QStyleFactory, QScrollBar, QMessageBox, StudioWindow, SchemeStore, default_scheme, UserState
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QApplication, QStyleFactory, QScrollBar, QMessageBox
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore, default_scheme
        from AgStudio.gui.user_state import UserState
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window = StudioWindow('test', user_state=UserState(), background=False,
                                   scheme_store=SchemeStore(self.temp.name))
        self.window.resize(1000, 650)
        self.window.show()

    def tearDown(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_native_scrollbar_palettes_are_isolated_from_content_themes(self):
        original_palette = self.app.palette()
        original_style = self.app.style().objectName()
        self.addCleanup(lambda: self.app.setPalette(original_palette))
        self.addCleanup(lambda: self.app.setStyle(original_style))
        for style in QStyleFactory.keys():
            self.app.setStyle(style)
            for dark in (False, True):
                palette = QPalette(original_palette)
                if dark:
                    palette.setColor(QPalette.Window, QColor('#353535'))
                    palette.setColor(QPalette.Base, QColor('#252525'))
                    palette.setColor(QPalette.Button, QColor('#454545'))
                    palette.setColor(QPalette.Text, QColor('white'))
                self.app.setPalette(palette)
                self.window.close()
                self.window.deleteLater()
                self.app.processEvents()
                self.window = StudioWindow('test', user_state=UserState(), background=False,
                                           scheme_store=SchemeStore(self.temp.name))
                self.window.show()
                tab = self.window.current()
                areas = (tab.editor, tab.outline, tab.correlations, tab.diagnostic_list)
                for background in ([0, 0, 0, 255], [40, 90, 130, 255], [240, 230, 210, 255]):
                    scheme = deepcopy(default_scheme())
                    scheme['editor']['background'] = background
                    self.window.apply_color_scheme(scheme)
                    self.app.processEvents()
                    self.assertEqual(tab.editor.viewport().palette().color(QPalette.Base), QColor(*background))
                    for area in areas:
                        for orientation, bar in ((Qt.Vertical, area.verticalScrollBar()),
                                                 (Qt.Horizontal, area.horizontalScrollBar())):
                            with self.subTest(style=style, dark=dark, background=background,
                                              area=area.objectName(), orientation=orientation):
                                # Native styles may draw disabled or transient bars
                                # differently. Verify their input palette is isolated
                                # rather than sampling a possibly hidden thumb.
                                self.assertEqual(area.palette().color(QPalette.Base),
                                                 palette.color(QPalette.Base))
                                self.assertEqual(bar.palette().color(QPalette.Base),
                                                 palette.color(QPalette.Base))
                                self.assertEqual(bar.styleSheet(), '')
                    for tree in areas[1:3]:
                        tree.viewport().ensurePolished()
                        self.assertEqual(tree.viewport().palette().color(QPalette.Base), QColor('black'))

    def test_editor_scroll_actions_keep_working(self):
        editor = self.window.current().editor
        editor.setPlainText(("long line " * 30 + "\n") * 50)
        self.app.processEvents()
        for bar in (editor.verticalScrollBar(), editor.horizontalScrollBar()):
            bar.setValue(0)
            bar.triggerAction(QScrollBar.SliderSingleStepAdd)
            self.assertGreater(bar.value(), 0)
        editor.document().setModified(False)


if __name__ == '__main__':
    unittest.main()
