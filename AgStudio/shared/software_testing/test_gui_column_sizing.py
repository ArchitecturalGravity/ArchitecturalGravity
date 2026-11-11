"""Content-sized columns, stable outline expansion, and narrow-pane overflow."""
import importlib.util
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class ColumnSizingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import DocumentTab, STUDIO_STYLE
        self.tab = DocumentTab('current', '[A]:\n- Content\n\nTask:\n- Use [A]\n- Another [A]\n',
                               map_enabled=False)
        self.tab.setStyleSheet(STUDIO_STYLE)
        self.tab.resize(1100, 700)
        self.tab.side_panel.show()
        self.tab.show()
        self.settle()
        parent = self.tab.outline.topLevelItem(0)
        self.tab.outline.setCurrentItem(parent)
        self.tab._outline_clicked(parent)
        self.settle()

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        self.tab.close()
        self.tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.settle()

    def settle(self):
        for _ in range(4):
            self.app.processEvents()

    def widths(self, tree):
        return tuple(tree.columnWidth(i) for i in range(tree.columnCount()))

    def test_all_columns_use_contents_without_last_column_stretch(self):
        from PySide6.QtWidgets import QHeaderView
        for tree in (self.tab.outline, self.tab.correlations, self.tab.diagnostic_list):
            header = tree.header()
            self.assertFalse(header.stretchLastSection())
            for column in range(tree.columnCount()):
                self.assertEqual(header.sectionResizeMode(column), QHeaderView.ResizeMode.ResizeToContents)

    def assert_fills_or_overflows(self, tree):
        required = sum(max(tree.contentWidth(i), tree.header().sectionSizeHint(i),
                           tree.header().minimumSectionSize())
                       for i in range(tree.columnCount()))
        self.assertEqual(sum(self.widths(tree)), max(required, tree.viewport().width()))

    def test_spare_pane_width_is_shared_by_every_column_without_blank_area(self):
        trees = (self.tab.outline, self.tab.correlations)
        self.tab.side_panel.setFixedWidth(400)
        self.settle()
        before = [self.widths(tree) for tree in trees]
        self.tab.side_panel.setFixedWidth(800)
        self.settle()
        for tree, old in zip(trees, before):
            self.assert_fills_or_overflows(tree)
            self.assertEqual(sum(self.widths(tree)), tree.viewport().width())
            self.assertTrue(all(new > previous for new, previous in zip(self.widths(tree), old)))
        self.tab.side_panel.setFixedWidth(400)
        self.settle()
        for tree, old in zip(trees, before):
            self.assertEqual(self.widths(tree), old)
            self.assert_fills_or_overflows(tree)

    def test_window_resize_and_refresh_leave_no_blank_finding_columns(self):
        tree = self.tab.diagnostic_list
        for width in (900, 1400, 900):
            self.tab.resize(width, 700)
            self.settle()
            self.assert_fills_or_overflows(tree)
        for source in ('=> - Act', 'Task:\n- Act\n'):
            self.tab.editor.setPlainText(source)
            self.settle()
            self.assert_fills_or_overflows(tree)
            self.assert_fills_or_overflows(self.tab.outline)

    def test_header_dividers_cannot_be_dragged(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        for tree in (self.tab.outline, self.tab.correlations, self.tab.diagnostic_list):
            header = tree.header()
            before = self.widths(tree)
            edge = QPoint(header.sectionViewportPosition(0) + header.sectionSize(0) - 1,
                          header.height() // 2)
            QTest.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=edge)
            QTest.mouseMove(header.viewport(), edge + QPoint(40, 0))
            QTest.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=edge + QPoint(40, 0))
            self.settle()
            self.assertEqual(self.widths(tree), before)

    def test_expanding_long_descendants_never_widens_context(self):
        from PySide6.QtWidgets import QTreeWidgetItem
        tree = self.tab.outline
        parent = tree.topLevelItem(0)
        child = QTreeWidgetItem(parent, ['Long descendant ' * 30, '12'])
        QTreeWidgetItem(child, ['Even deeper descendant ' * 30, '13'])
        parent.setExpanded(False)
        self.settle()
        before = tree.columnWidth(0)
        for _ in range(2):
            tree.expandAll()
            self.settle()
            self.assertEqual(tree.columnWidth(0), before)
            tree.collapseAll()
            self.settle()
            self.assertEqual(tree.columnWidth(0), before)
        parent.setText(0, 'A substantially longer top-level context')
        self.settle()
        self.assertGreater(tree.columnWidth(0), before)

    def test_pane_resize_preserves_contents_and_scrolls_when_too_narrow(self):
        from PySide6.QtWidgets import QTreeWidgetItem
        QTreeWidgetItem(self.tab.outline, ['Long top-level context ' * 8, '123456'])
        QTreeWidgetItem(self.tab.correlations, ['[Long correlation symbol ' + 'x' * 80 + ']', '123456', '789'])
        self.tab.side_panel.setFixedWidth(650)
        self.settle()
        trees = (self.tab.outline, self.tab.correlations)
        widths = [self.widths(tree) for tree in trees]
        for width in (200, 400, 200, 650):
            self.tab.side_panel.setFixedWidth(width)
            self.settle()
            for tree, expected in zip(trees, widths):
                self.assertEqual(self.widths(tree), expected)
                self.assertGreater(tree.horizontalScrollBar().maximum(), 0)
                tree.horizontalScrollBar().setValue(tree.horizontalScrollBar().maximum())
                self.assertGreater(tree.header().offset(), 0)
        self.tab.side_panel.setFixedWidth(3000)
        self.settle()
        for tree in trees:
            self.assert_fills_or_overflows(tree)
            self.assertEqual(tree.horizontalScrollBar().maximum(), 0)
            self.assertEqual(tree.header().offset(), 0)
        self.tab.side_panel.setFixedWidth(200)
        self.settle()
        for tree, expected in zip(trees, widths):
            self.assertEqual(self.widths(tree), expected)
            self.assertGreater(tree.horizontalScrollBar().maximum(), 0)

    def test_font_changes_and_refresh_remeasure_contents(self):
        from AgStudio.gui.app import STUDIO_STYLE
        tree = self.tab.outline
        self.tab.editor.setPlainText('[A_reasonably_long_context_name]:\n- Child\n')
        self.settle()
        before = tree.columnWidth(0)
        self.tab.setStyleSheet(STUDIO_STYLE + '\nQWidget { font-size: 24px; }')
        self.settle()
        self.assertGreater(tree.columnWidth(0), before)
        large = tree.columnWidth(0)
        self.tab.editor.setPlainText('[A]:\n- Child\n')
        self.settle()
        self.assertLess(tree.columnWidth(0), large)

    def test_finding_message_fits_content_and_survives_sort_and_refresh(self):
        from PySide6.QtCore import Qt
        tree = self.tab.diagnostic_list
        self.tab.editor.setPlainText('=> - Act')
        self.settle()
        self.assertGreater(tree.topLevelItemCount(), 0)
        row = tree.topLevelItem(0)
        row.setText(2, 'Long finding message ' * 60)
        self.settle()
        before = tree.columnWidth(2)
        self.assertGreater(before, tree.viewport().width())
        for column in range(5):
            tree.sortItems(column, Qt.SortOrder.AscendingOrder)
            self.settle()
            self.assertEqual(tree.columnWidth(2), before)
        self.tab.editor.setPlainText('Task:\n- Act\n')
        self.settle()
        self.assertLess(tree.columnWidth(2), before)
