"""Typed header sorting without changing diagnostic identity or editor state."""
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class FindingSortingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import DocumentTab
        self.tab = DocumentTab('current', ('x' * 120 + '\n') * 110,
                               background=False, map_enabled=False)
        self.tab.resize(1200, 800)
        self.tab.show()
        self.tree = self.tab.diagnostic_list
        self.publish(self.findings())
        self.app.processEvents()

    def tearDown(self):
        self.tab.close()
        self.tab.deleteLater()
        self.app.processEvents()

    def findings(self):
        from AgStudio.shared.diagnostics import Finding, RuleEvidence
        from AgStudio.shared.recognition import SourceSpan
        evidence = RuleEvidence('current', 'test', (), '')
        specs = [('critical', 'AG-Z', 'Zulu', 10, 100),
                 ('information', 'AG-B', 'beta', 100, 10),
                 ('warning', 'AG-SPELLING', 'Alpha', 2, 2),
                 ('error', 'AG-A', 'alpha', 10, 10),
                 ('critical', 'AG-Z', 'Zulu', 2, 100),
                 ('warning', 'AG-SPELLING', 'Alpha', 2, 2)]
        result = []
        for i, (severity, rule, message, line, column) in enumerate(specs):
            offset = (line - 1) * 121 + column - 1
            result.append(Finding(str(i), rule, severity,
                                  self.tab.document.source_range(SourceSpan(offset, offset + 1)),
                                  evidence, (), message))
        return tuple(result)

    def publish(self, findings):
        from AgStudio.shared.diagnostics import DiagnosticResult
        from AgStudio.shared.panel_projections import derive_findings
        from AgStudio.gui.panel_rendering import apply_findings
        diagnostics = DiagnosticResult(self.tab.document.document_id, 'current', findings, 'evaluated')
        self.tab.diagnostics = diagnostics
        apply_findings(self.tab, derive_findings(SimpleNamespace(
            document=self.tab.document, diagnostics=diagnostics)))
        self.app.processEvents()

    def rows(self):
        return [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]

    def click(self, column):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        header = self.tree.header()
        position = QPoint(header.sectionViewportPosition(column) + header.sectionSize(column) // 2,
                          header.height() // 2)
        QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=position)
        self.app.processEvents()
        self.assertEqual(header.sortIndicatorSection(), column)

    def assert_order(self, column):
        from PySide6.QtCore import Qt
        from AgStudio.gui.finding_list import finding_sort_key
        keys = [finding_sort_key(row.data(0, Qt.ItemDataRole.UserRole), column, row.finding_key)
                for row in self.rows()]
        descending = self.tree.header().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
        expected = sorted(sorted(keys, key=lambda key: key[1]), key=lambda key: key[0], reverse=descending)
        self.assertEqual(keys, expected)

    def test_actual_header_clicks_all_columns_both_directions(self):
        from PySide6.QtCore import Qt
        self.assertTrue(self.tree.header().isSortIndicatorShown())
        self.assertEqual(self.tree.header().sortIndicatorOrder(), Qt.SortOrder.DescendingOrder)
        self.assert_order(0)
        # The initial severity sort retains ascending source order within a rank.
        self.assertEqual([r.text(3) for r in self.rows()[:2]], ['2', '10'])
        source, dirty = self.tab.source, self.tab.dirty
        cursor = self.tab.editor.textCursor().position()
        counts = [label.text() for label in self.tab.diagnostic_count_labels.values()]
        for column in range(5):
            self.click(column)
            order = self.tree.header().sortIndicatorOrder()
            self.assert_order(column)
            self.click(column)
            self.assertNotEqual(self.tree.header().sortIndicatorOrder(), order)
            self.assert_order(column)
        self.assertEqual((self.tab.source, self.tab.dirty), (source, dirty))
        self.assertEqual(self.tab.editor.textCursor().position(), cursor)
        self.assertEqual([label.text() for label in self.tab.diagnostic_count_labels.values()], counts)

    def test_numeric_locations_are_not_lexical(self):
        from PySide6.QtCore import Qt
        for column in (3, 4):
            self.click(column)
            if self.tree.header().sortIndicatorOrder() != Qt.SortOrder.AscendingOrder:
                self.click(column)
            values = [int(row.text(column)) for row in self.rows()]
            self.assertEqual(values, sorted(values))
            self.assertEqual(sorted(set(values)), [2, 10, 100])

    def test_refresh_preserves_sort_selection_and_row_identity(self):
        from dataclasses import replace
        from PySide6.QtCore import Qt
        from AgStudio.shared.recognition import SourceSpan
        self.click(3)
        selected = self.rows()[1]
        self.tree.setCurrentItem(selected)
        before = dict(self.tab._finding_by_key)
        findings = self.findings()
        # Identical source text lets the existing stable row keys survive offsets changing.
        changed = tuple(replace(f, source_range=self.tab.document.source_range(
            SourceSpan(f.source_range.span.start + 121, f.source_range.span.end + 121))) for f in findings)
        self.publish(changed)
        self.assertEqual(self.tree.header().sortIndicatorSection(), 3)
        self.assert_order(3)
        self.assertIs(self.tree.currentItem(), selected)
        self.assertTrue(selected.isSelected())
        self.assertTrue(all(self.tab._finding_by_key[key] is row for key, row in before.items()))
        self.assertIn(selected.data(0, Qt.ItemDataRole.UserRole), changed)
        self.publish(changed[1:])
        self.assert_order(3)
        self.publish(())
        self.assertEqual(self.tree.topLevelItemCount(), 0)
        self.publish(findings)
        self.assert_order(3)

    def test_keyboard_activation_and_spelling_menu_use_sorted_item(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.click(2)
        row = next(row for row in self.rows() if row.text(1) == 'AG-SPELLING')
        finding = row.data(0, Qt.ItemDataRole.UserRole)
        self.tree.setCurrentItem(row)
        self.tree.setFocus()
        QTest.keyClick(self.tree, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.tab.editor.textCursor().selectionStart(), finding.source_range.span.start)
        self.assertEqual(self.tab.editor.textCursor().selectionEnd(), finding.source_range.span.end)
        menu = Mock()
        with patch.object(self.tab.editor, 'spelling_context_menu', return_value=menu) as factory:
            self.tab._spelling_finding_menu(self.tree.visualItemRect(row).center())
        factory.assert_called_once_with(finding.source_range.span.start, native_actions=False)
        menu.exec.assert_called_once()
        menu.deleteLater.assert_called_once()
        self.tab._findings_current = False
        with patch.object(self.tab, 'navigate') as navigate:
            self.tab._navigate_finding(row)
            navigate.assert_not_called()

    def test_tabs_and_collapsing_keep_independent_sort(self):
        from AgStudio.gui.app import DocumentTab
        other = DocumentTab('current', background=False, map_enabled=False)
        try:
            self.click(4)
            direction = self.tree.header().sortIndicatorOrder()
            for _ in range(2):
                self.tab._toggle_diagnostics()
                self.app.processEvents()
            self.assertEqual(self.tree.header().sortIndicatorSection(), 4)
            self.assertEqual(self.tree.header().sortIndicatorOrder(), direction)
            self.assertEqual(other.diagnostic_list.header().sortIndicatorSection(), 0)
            self.assert_order(4)
        finally:
            other.close()
            other.deleteLater()

    def test_interrupted_batch_restores_sorting(self):
        from AgStudio.gui.finding_list import finding_update
        self.click(1)
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            with finding_update(self.tree):
                self.assertFalse(self.tree.isSortingEnabled())
                raise RuntimeError('interrupted')
        self.assertTrue(self.tree.isSortingEnabled())
        self.assert_order(1)
