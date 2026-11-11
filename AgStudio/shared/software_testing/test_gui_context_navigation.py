"""Bidirectional context navigation without editing or focus changes."""
import importlib.util
import os
from pathlib import Path
import time
import unittest
from unittest import mock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class ContextNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        self.window = StudioWindow('current', user_state=UserState())
        self.window.resize(1000, 700)
        self.window.show()
        self.tab = self.window.current()

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def settle(self):
        from PySide6.QtTest import QTest
        until = time.monotonic() + 5
        def ready():
            document = self.tab.document
            return (self.tab.analysis is not None and document is not None
                    and document.source == self.tab.source
                    and self.tab.diagnostics is not None
                    and self.tab._highlight_document_id == document.document_id
                    and not self.tab.highlighter.pending
                    and self.tab._outline_document_id == document.document_id)
        while not ready() and time.monotonic() < until:
            QTest.qWait(10)
        self.assertTrue(ready(), 'current analysis and projections did not settle: '
                        f'analysis={self.tab.analysis is not None}, diagnostics={self.tab.diagnostics is not None}, '
                        f'highlight={self.tab._highlight_document_id}, outline={self.tab._outline_document_id}, '
                        f'document={getattr(self.tab.document, "document_id", None)}, '
                        f'status={self.tab.diagnostics_heading.toolTip()}, '
                        f'outline_error={self.tab.outline_status.toolTip()}, '
                        f'highlight_error={self.tab.editor.toolTip()}')

    def move(self, text):
        from AgStudio.gui.app import _display_offset
        cursor = self.tab.editor.textCursor()
        cursor.setPosition(_display_offset(self.tab.source, self.tab.source.index(text)))
        self.tab.editor.setTextCursor(cursor)

    def test_hello_world_editor_and_outline_clicks_in_both_directions(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        source = (Path(__file__).resolve().parents[2] / 'examples/HelloWorld.arc').read_text()
        self.tab.editor.setPlainText(source)
        self.settle()
        self.window._show_side_panel()
        self.settle()
        self.tab.editor.setFocus()
        self.move('[CharacterFactory]:')
        self.assertEqual(self.tab.outline.currentItem().text(0), '[CharacterFactory]:')
        self.assertTrue(self.tab.editor.hasFocus())
        item = next(i for i in self.tab._outline_items.values() if i.text(0) == '[Constraint]:')
        self.tab.outline.scrollToItem(item)
        self.app.processEvents()
        for _ in range(2):
            QTest.mouseClick(self.tab.outline.viewport(), Qt.MouseButton.LeftButton,
                            pos=self.tab.outline.visualItemRect(item).center())
            self.assertEqual(self.tab.editor.textCursor().position(), source.index('[Constraint]:'))
            self.assertTrue(self.tab.outline.hasFocus())
        self.assertEqual(self.tab.source, source)

    def test_nested_unicode_crlf_hidden_panels_reanalysis_and_tabs(self):
        self.window._set_panel_visibility('side_panel', False)
        source = '[Root]:\r\n- Parent:\r\n  - 🌍 Child\r\n'
        # Model a loaded document: undo must restore this source baseline.
        self.tab.original_source = source
        self.tab.line_ending = '\r\n'
        self.tab.editor.setPlainText(source)
        self.settle()
        self.move('🌍')
        selected = self.tab.outline.currentItem()
        self.assertIn('Child', selected.text(0))
        self.assertIn('Parent', selected.parent().text(0))
        self.assertTrue(self.tab.side_panel.isHidden())
        self.tab.editor.insertPlainText('New ')
        self.settle()
        current_source = self.tab.source
        first = self.tab
        other = self.window.new_document()
        other.editor.setPlainText('[Other]: value')
        self.window.tabs.setCurrentWidget(first)
        self.assertIn('New', first.outline.currentItem().text(0))
        self.assertEqual(first.source, current_source)
        first.editor.undo()
        self.settle()
        first.editor.selectAll()
        first.editor.insertPlainText('')
        self.settle()
        self.assertIsNone(first.outline.currentItem())

    def test_active_selection_endpoint_and_unclassified_ownership(self):
        from PySide6.QtGui import QTextCursor
        source = 'Root:\n- Parent:\n  - Child\n\nOutside prose\nNext:\n'
        self.tab.editor.setPlainText(source)
        self.settle()
        for anchor, endpoint, label in ((0, source.index('Child'), '- Child'),
                                        (source.index('Child'), 0, 'Root:')):
            cursor = self.tab.editor.textCursor()
            cursor.setPosition(anchor)
            cursor.setPosition(endpoint, QTextCursor.MoveMode.KeepAnchor)
            self.tab.editor.setTextCursor(cursor)
            self.assertEqual(self.tab.outline.currentItem().text(0), label)
        self.move('Outside')
        self.assertEqual(self.tab.outline.currentItem().text(0), 'Root:')
        cursor = self.tab.editor.textCursor()
        cursor.setPosition(source.index('\n\n') + 1)
        self.tab.editor.setTextCursor(cursor)
        self.assertIsNone(self.tab.outline.currentItem())

    def test_literal_is_one_leaf_and_highlights_complete_block(self):
        from PySide6.QtWidgets import QTreeWidgetItem
        from PySide6.QtGui import QColor
        source = '[Literal]:\n"""\nfirst\n\nlast\n"""\n[Next]: value\n'
        self.tab.editor.setPlainText(source)
        self.settle()
        literal = next(item for item in self.tab._outline_items.values() if item.text(0) == 'Literal block')
        self.assertEqual(literal.childCount(), 0)
        self.assertEqual(literal.childIndicatorPolicy(), QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
        self.assertEqual(len([i for i in self.tab._outline_items.values() if i.text(0) == 'Literal block']), 1)
        self.tab._outline_clicked(literal)
        self.assertEqual(self.tab.editor.context_highlight, (source.index('"""'), source.rindex('"""') + 3))
        selection = self.tab.editor.extraSelections()[0]
        from PySide6.QtGui import QTextFormat
        selections = self.tab.editor.extraSelections()
        self.assertEqual([row.cursor.blockNumber() for row in selections], [1, 2, 3, 4, 5])
        for row in selections:
            self.assertFalse(row.cursor.hasSelection())
            self.assertTrue(row.format.property(QTextFormat.Property.FullWidthSelection))
        self.assertFalse(self.tab.editor.textCursor().hasSelection())
        self.assertEqual(selection.format.background().color(), QColor(*self.tab.editor.color_scheme['active_row']['background']))
        self.move('last')
        self.assertIs(self.tab.outline.currentItem(), literal)
        self.move('[Next]')
        self.assertEqual(self.tab.editor.context_highlight, (source.index('[Next]'), len(source) - 1))
        self.assertEqual(self.tab.source, source)

    def test_symbol_descendants_exclude_siblings_and_refresh_after_edits(self):
        source = '[Root]:\n- Parent:\n  - Child\n\n  - Other\n[Sibling]: value\n'
        self.tab.editor.setPlainText(source)
        self.tab.original_source = source  # Model a loaded document's undo baseline.
        self.settle()
        self.move('[Root]')
        self.assertEqual(self.tab.editor.context_highlight, (0, source.index('[Sibling]') - 1))
        from PySide6.QtGui import QTextFormat
        rows = self.tab.editor.extraSelections()
        self.assertEqual([row.cursor.blockNumber() for row in rows], [0, 1, 2, 3, 4])
        self.assertFalse(rows[-1].cursor.hasSelection())
        self.assertTrue(rows[-1].format.property(QTextFormat.Property.FullWidthSelection))
        self.move('Child')
        self.assertEqual(self.tab.editor.context_highlight, (source.index('  - Child'), source.index('  - Child') + len('  - Child')))
        self.move('[Root]')
        self.tab.editor.insertPlainText('X')
        self.assertIsNone(self.tab.editor.context_highlight)
        self.settle()
        self.tab.editor.undo()
        self.settle()
        self.move('[Root]')
        self.assertEqual(self.tab.editor.context_highlight, (0, source.index('[Sibling]') - 1))
        scheme = self.tab.editor.color_scheme.copy()
        scheme['active_row'] = {'background': [1, 2, 3, 255], 'foreground': [0, 0, 0, 0]}
        self.tab.editor.apply_color_scheme(scheme)
        selection = self.tab.editor.extraSelections()[0]
        color = selection.format.background().color()
        self.assertEqual(color.getRgb(), (1, 2, 3, 255))
        self.assertEqual(self.tab.source, source)

    def test_depth_alpha_for_unbalanced_tree_and_nested_selection(self):
        source = 'Task:\n- Parent:\n  1. Nested:\n    => Deep\n- Shallow\nSibling: done\n'
        self.tab.editor.setPlainText(source)
        self.settle()
        scheme = self.tab.editor.color_scheme.copy()
        scheme['deepest_child_opacity'] = 25  # Isolated behavior fixture, independent of shipped palette.
        scheme['active_row'] = {'background': [40, 80, 120, 200], 'foreground': [0, 0, 0, 0]}
        self.tab.editor.apply_color_scheme(scheme)
        def colors():
            rows = self.tab.editor.extraSelections()
            return [row.format.background().color().getRgb() for row in rows]
        self.move('Task:')
        self.assertEqual(colors(), [(40, 80, 120, a) for a in (200, 150, 100, 50, 150)])
        self.move('1. Nested')
        self.assertEqual(colors(), [(40, 80, 120, 200), (40, 80, 120, 50)])
        self.move('=> Deep')
        self.assertEqual(colors(), [(40, 80, 120, 200)])
        scheme['active_row']['background'] = [11, 22, 33, 80]
        self.tab.editor.apply_color_scheme(scheme)
        self.move('- Parent:')
        self.assertEqual(colors(), [(11, 22, 33, a) for a in (80, 50, 20)])

    def test_literal_contents_share_one_depth_under_parent(self):
        source = 'Task:\n"""\nbody\n\nlast\n"""\nNext: done\n'
        self.tab.editor.setPlainText(source)
        self.settle()
        self.move('Task:')
        self.assertEqual(self.tab.editor.context_depths, {0: 0, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1})
        self.move('body')
        self.assertEqual(set(self.tab.editor.context_depths.values()), {0})

    def test_outline_initial_collapse_navigation_reanalysis_and_tabs(self):
        import tempfile
        source = 'Root:\n- Parent:\n  1. Child\n\nOther:\n- Item\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'outline.arc'
            path.write_text(source)
            self.tab = self.window.open_file(path)
            self.settle()
            self.window._show_side_panel()
            self.settle()
            self.assertFalse(any(item.isExpanded() for item in self.tab._outline_items.values()))
            self.move('1. Child')
            root = self.tab.outline.topLevelItem(0)
            self.assertTrue(root.isExpanded())
            self.assertTrue(root.child(0).isExpanded())
            root.setExpanded(False)
            self.tab.refresh_model()
            self.settle()
            self.assertFalse(self.tab.outline.topLevelItem(0).isExpanded())
            self.assertTrue(self.tab.outline.topLevelItem(0).child(0).isExpanded())
            first = self.tab
            second_path = Path(directory) / 'second.arc'
            second_path.write_text(source)
            self.tab = self.window.open_file(second_path)
            self.settle()
            self.assertFalse(any(item.isExpanded() for item in self.tab._outline_items.values()))
            self.window.tabs.setCurrentWidget(first)
            self.window._show_side_panel()
            self.settle()
            self.assertFalse(first.outline.topLevelItem(0).isExpanded())
            self.assertIs(self.window.open_file(path), first)
            self.assertFalse(first.outline.topLevelItem(0).isExpanded())
            # A genuinely reopened document has fresh, collapsed state.
            self.window._close_tab(self.window.tabs.indexOf(first))
            self.tab = self.window.open_file(path)
            self.settle()
            self.assertFalse(any(item.isExpanded() for item in self.tab._outline_items.values()))

    def test_outline_uses_black_and_live_syntax_foregrounds(self):
        from copy import deepcopy
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPalette, QColor
        from PySide6.QtWidgets import QStyleOptionViewItem
        from AgStudio.gui.color_scheme_dialog import ColorSchemeDialog
        from AgStudio.gui.color_schemes import ROLE_LABELS
        source = '[Symbol]: value\n\nTask:\n- Bullet\n12. Ordered\nP0. Priority\n=> Act ↳\n  - Child\n\n"""\nopaque\n"""\n'
        self.tab.editor.setPlainText(source)
        self.settle()
        self.window._show_side_panel()
        self.settle()
        palette = deepcopy(self.window.color_scheme)
        for index, role in enumerate(ROLE_LABELS):
            palette[role]['foreground'] = [30 + index, 80 + index, 130 + index, 255]
        self.window.apply_color_scheme(palette)
        expected = {'[Symbol]: value': 'symbol', 'Task:': 'section', '- Bullet': 'bullet',
                    '12. Ordered': 'sequence', 'P0. Priority': 'priority', '=> Act ↳': 'operation',
                    '- Child': 'bullet', 'Literal block': 'delimiter'}
        for item in self.tab._outline_items.values():
            role = expected.get(item.text(0), 'editor')
            self.assertEqual(item.data(0, Qt.ItemDataRole.UserRole + 2), role)
            for column in range(item.columnCount()):
                self.assertEqual(item.foreground(column).color().getRgb(), tuple(palette[role]['foreground']))
        self.app.processEvents()
        self.assertEqual(self.tab.outline.viewport().palette().color(QPalette.ColorRole.Base), QColor('black'))
        item = self.tab.outline.topLevelItem(0)
        option = QStyleOptionViewItem()
        self.tab.outline.itemDelegate().initStyleOption(option, self.tab.outline.indexFromItem(item))
        self.assertEqual(option.palette.color(QPalette.ColorRole.HighlightedText), QColor(*palette['active_row']['foreground']))
        before = self.tab.source
        dialog = ColorSchemeDialog(self.window)
        try:
            dialog.roles.setCurrentIndex(dialog.roles.findData('symbol'))
            dialog.controls['foreground'][0].setValue(211)
            self.assertEqual(item.foreground(0).color().red(), 211)
            dialog.reject()
            self.assertEqual(item.foreground(0).color().getRgb(), tuple(palette['symbol']['foreground']))
            self.assertEqual(self.tab.source, before)
        finally:
            dialog.deleteLater()

    def test_outline_arrows_stay_white_and_literal_leaves_have_none(self):
        from PySide6.QtCore import Qt, QRect
        from PySide6.QtGui import QColor, QImage, QPainter
        from PySide6.QtWidgets import QTreeWidgetItem
        from AgStudio.gui.app import _OutlineTree
        tree = _OutlineTree()
        try:
            parent = QTreeWidgetItem(tree, ['Parent'])
            QTreeWidgetItem(parent, ['Child'])
            leaf = QTreeWidgetItem(tree, ['Literal block'])
            leaf.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
            QTreeWidgetItem(leaf, ['Hidden'])
            images = []
            for expanded in (False, True):
                for selected in (False, True):
                    for color in ('red', 'black', 'green'):
                        parent.setExpanded(expanded)
                        parent.setSelected(selected)
                        parent.setForeground(0, QColor(color))
                        tree.setStyleSheet('QTreeWidget::branch:hover { color: red; }')
                        image = QImage(40, 24, QImage.Format.Format_ARGB32)
                        image.fill(QColor('black'))
                        painter = QPainter(image)
                        tree.drawBranches(painter, QRect(0, 0, 40, 24), tree.indexFromItem(parent))
                        painter.end()
                        pixels = {image.pixelColor(x, y).name() for x in range(40) for y in range(24)}
                        self.assertEqual(pixels, {'#000000', '#ffffff', '#59616b'} if expanded else {'#000000', '#ffffff'})
                        if selected is False and color == 'red':
                            images.append(image)
            self.assertNotEqual(images[0], images[1])
            image = QImage(40, 24, QImage.Format.Format_ARGB32)
            image.fill(QColor('black'))
            painter = QPainter(image)
            tree.drawBranches(painter, QRect(0, 0, 40, 24), tree.indexFromItem(leaf))
            painter.end()
            self.assertEqual({image.pixelColor(x, y).name() for x in range(40) for y in range(24)}, {'#000000'})
        finally:
            tree.deleteLater()
