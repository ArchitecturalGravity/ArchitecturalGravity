"""GUI diagnostic selection is read-only; repair controls are not exposed."""
import importlib.util
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class GuiDiagnosticInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import DocumentTab
        self.source = '[A]: 🌍\r\n=> - Keep é\nTail\rEnd'
        self.tab = DocumentTab('current', self.source)

    def tearDown(self):
        self.tab.dispose_analysis()
        self.tab.deleteLater()
        self.app.processEvents()

    def test_no_gui_repair_controls_or_dispatch(self):
        from PySide6.QtWidgets import QToolButton
        buttons = self.tab.diagnostics_panel.findChildren(QToolButton)
        self.assertEqual([button.accessibleName() for button in buttons], ['Collapse Finding List'])
        for name in ('quickfix_button', 'selected_quick_fixes', '_show_quick_fixes',
                     '_confirm_quick_fix', 'apply_quick_fix'):
            self.assertFalse(hasattr(self.tab, name))

    def test_selection_and_navigation_do_not_edit_or_save(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.arc'
            path.write_bytes(self.source.encode('utf-8'))
            self.tab.path = path
            row = next(self.tab.diagnostic_list.topLevelItem(i)
                       for i in range(self.tab.diagnostic_list.topLevelItemCount())
                       if self.tab.diagnostic_list.topLevelItem(i).text(1) == 'AG-OPERATION-LIST')
            self.tab.diagnostic_list.setCurrentItem(row)
            self.tab._navigate_finding(row)
            self.assertEqual(self.tab.editor.textCursor().selectedText(), '=> - ')
            self.tab.diagnostic_list.setCurrentItem(None)
            self.assertEqual(self.tab.source, self.source)
            self.assertFalse(self.tab.dirty)
            self.assertFalse(self.tab.editor.document().isUndoAvailable())
            self.assertEqual(path.read_bytes(), self.source.encode('utf-8'))

    def test_background_failure_and_stale_result_stay_safe(self):
        from AgStudio.gui.app import DocumentTab
        from AgStudio.shared.lint import analyze
        self.tab.dispose_analysis()
        self.tab.deleteLater()
        self.tab = DocumentTab('current', self.source, background=True)
        old_result = analyze(self.source)
        revision = self.tab.controller.revision
        self.tab._analysis_failed(revision, 'test failure')
        self.assertIn('failed', self.tab.diagnostics_heading.toolTip())
        self.tab.editor.insertPlainText('x')
        self.tab._analysis_ready(revision, old_result)
        self.assertIsNone(self.tab.analysis)
        current = analyze(self.tab.source)
        self.tab._analysis_ready(self.tab.controller.revision, current)
        self.assertIs(self.tab.analysis, current)
        self.tab.dispose_analysis()
        self.tab._analysis_ready(self.tab.controller.revision, old_result)
        self.assertIs(self.tab.analysis, current)
