"""Queued workspace sizing follows the lifetime of the receiving page."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSize
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QTextEdit, QVBoxLayout

from AgMark.gui.widgets.responsive import ResponsiveView, apply_minimum, wrap_text


class ResponsiveLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_queued_sizing_updates_live_page_and_cancels_deleted_page(self):
        def page():
            view = ResponsiveView()
            layout = QVBoxLayout(view)
            label = QLabel("Workspace content", view)
            label.setMinimumHeight(360)
            layout.addWidget(label)
            QCoreApplication.sendEvent(view, QEvent(QEvent.Type.LayoutRequest))
            return view

        with patch("sys.excepthook") as errors:
            live = page()
            QApplication.processEvents()
            self.assertGreaterEqual(live.minimumHeight(), 360)
            live.deleteLater()
            retired = page()
            retired.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QApplication.processEvents()
            errors.assert_not_called()

    def test_scroll_begins_at_component_minimum_not_preferred_height(self):
        class TallEditor(QTextEdit):
            def sizeHint(self):
                return QSize(500, 600)

        view = ResponsiveView()
        layout = QVBoxLayout(view)
        label = QLabel("Wrapped workspace description " * 4, view)
        wrap_text(label)
        layout.addWidget(label)
        editor = TallEditor(view)
        apply_minimum(editor, 100, 120)
        layout.addWidget(editor, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(view)
        scroll.resize(600, 400)
        scroll.show()
        self.addCleanup(scroll.close)
        self.addCleanup(scroll.deleteLater)

        def settle():
            for _ in range(5):
                self.application.processEvents()

        settle()
        self.assertEqual(0, scroll.verticalScrollBar().maximum())
        first_height = editor.height()
        scroll.resize(600, 300)
        settle()
        self.assertLess(editor.height(), first_height)
        self.assertGreaterEqual(editor.height(), 120)
        self.assertEqual(0, scroll.verticalScrollBar().maximum())
        scroll.resize(600, 180)
        settle()
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        self.assertGreaterEqual(editor.height(), 120)
        scroll.resize(600, 400)
        settle()
        self.assertEqual(0, scroll.verticalScrollBar().maximum())
        self.assertEqual(first_height, editor.height())
