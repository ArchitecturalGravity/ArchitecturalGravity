"""Default-off live capture and collapsed startup agree with runtime and rendering."""
import unittest
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSpinBox
from AgMark.gui.widgets.console import BottomConsoleWidget, BottomConsoleState
from AgMark.gui.shell.window import BenchmarkShellWindow, SHELL_CONSOLE_EXPANDED_KEY
from AgMark.shared.adapters.execution.live_view import LiveViewControl
from AgMark.shared.software_testing.frontends.gui import test_application_lifecycle_qt as fixture


class UiDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_console_defaults_before_first_show_and_output_never_expand_it(self):
        self.assertFalse(BottomConsoleState().expanded)
        self.assertEqual((False, 0), LiveViewControl().snapshot())
        console = BottomConsoleWidget()
        self.addCleanup(console.close)
        self.assertFalse(console.expanded)
        self.assertTrue(console._content.isHidden())
        self.assertFalse(console.stream_output_checkbox.isChecked())
        self.assertFalse(console.stream_input_checkbox.isChecked())
        self.assertEqual((False, 0), console.live_view_control.snapshot())
        self.assertEqual('Expand console', console.collapse_button.accessibleName())
        shows = []
        class Watch(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.Show: shows.append(event.type())
                return False
        watch = Watch(console)
        console._content.installEventFilter(watch)
        console.show()
        console.bind_generation('startup')
        console.queue_live_view('startup', 'one', output_text='off')
        console.append_diagnostic('startup', 'routine output')
        console.set_environment('ready')
        for _ in range(3): self.app.processEvents()
        self.assertEqual([], shows)
        self.assertFalse(console.expanded)
        self.assertFalse(console._pending_live)
        self.assertFalse(console._live_timer.isActive())
        self.assertFalse(console.set_live_view('startup', 'one', output_text='off'))
        console.stream_output_checkbox.click()
        self.assertTrue(console.live_view_control.snapshot()[0])
        console.queue_live_view('startup', 'one', output_text='enabled', stream_revision=1)
        console._flush_live_view()
        self.assertIn('enabled', console.state.visible_text)
        self.assertFalse(console.expanded)
        console.collapse_button.click()
        self.assertTrue(console.expanded)
        self.assertEqual('Collapse console', console.collapse_button.accessibleName())
        self.assertTrue(console._content.isVisible())

    def test_shell_first_layout_collapsed_and_saved_expansion_is_restored(self):
        for expanded in (None, True, False):
            prefs = {} if expanded is None else {SHELL_CONSOLE_EXPANDED_KEY: expanded}
            pixmap = QPixmap(16, 16); pixmap.fill(Qt.GlobalColor.black)
            window = BenchmarkShellWindow(application_icon=QIcon(pixmap), shell_preferences=prefs, console_preferences={})
            self.addCleanup(window.close)
            expected = expanded is True
            self.assertEqual(expected, window.console_widget.expanded)
            window.show()
            for _ in range(3): self.app.processEvents()
            console = window.console_widget
            self.assertEqual(expected, console._content.isVisible())
            self.assertFalse(console.live_view_control.snapshot()[0])
            if not expected:
                self.assertLess(window.vertical_splitter.sizes()[1], 80)
            console.set_expanded(True)
            self.app.processEvents()
            self.assertGreater(window.vertical_splitter.sizes()[1], 80)

    def test_iterations_chrome_focus_integer_arrows_and_disabled_state(self):
        fixture.ProductionSharedLifecycleGuiIntegrationTests.setUpClass()
        owner = fixture.ProductionSharedLifecycleGuiIntegrationTests()
        owner.setUp(); self.addCleanup(owner.doCleanups)
        application, _, _ = owner._application_for('styled-iterations')
        window = application.window
        window.show(); self.app.processEvents()
        spin = window.iterations_input
        combo = window.benchmark_input.combo_box
        self.assertEqual(combo.minimumHeight(), spin.minimumHeight())
        self.assertEqual(combo.font(), spin.font())
        self.assertTrue(spin.styleSheet().startswith(combo.styleSheet().replace('QComboBox', 'QSpinBox')))
        self.assertEqual('input-control', spin.property('arcgravSemanticComponent'))
        spin.setFocus(); self.app.processEvents()
        self.assertTrue(spin.hasFocus())
        QTest.keyClick(spin, Qt.Key.Key_Up)
        self.assertEqual(2, spin.value()); self.assertIs(type(spin.value()), int)
        option = QStyleOptionSpinBox(); spin.initStyleOption(option)
        for control, expected in ((QStyle.SubControl.SC_SpinBoxUp, 3), (QStyle.SubControl.SC_SpinBoxDown, 2)):
            rect = spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, spin)
            self.assertFalse(rect.isEmpty())
            QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=rect.center())
            self.assertEqual(expected, spin.value())
        window.set_operation_activity(('Running',), lock_controls=True)
        self.assertFalse(spin.isEnabled())
        QTest.keyClick(spin, Qt.Key.Key_Up)
        self.assertEqual(2, spin.value())
        window.set_operation_activity((), lock_controls=False)
        self.assertTrue(spin.isEnabled())
