"""Finding-list controls and safe, source-exact spelling menu edits."""
import os
import importlib.util
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from AgStudio.shared.diagnostics import SEVERITY_ORDER


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class FindingControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import DocumentTab
        self.tab = DocumentTab('current', '=> - Act\nUse `two words`\n- mispelled text\n')
        self.tab.resize(900, 600)
        self.tab.show()
        self.app.processEvents()

    def tearDown(self):
        self.tab.close()
        self.tab.deleteLater()
        self.app.processEvents()

    def test_count_severity_order_navigation_and_collapse(self):
        from PySide6.QtCore import Qt
        tab = self.tab
        tree = tab.diagnostic_list
        rows = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
        self.assertEqual(tab.diagnostics_heading.text(), 'Finding List')
        self.assertEqual(sum(int(label.text()) for label in tab.diagnostic_count_labels.values()), len(rows))
        ranks = [SEVERITY_ORDER[row.data(0, Qt.ItemDataRole.UserRole).severity] for row in rows]
        self.assertEqual(set(ranks), {0, 1, 2, 3})
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        for row in rows:
            finding = row.data(0, Qt.ItemDataRole.UserRole)
            tab._navigate_finding(row)
            self.assertEqual(tab.editor.textCursor().selectedText(), finding.source_range.span.extract(tab.source))
        layout = tab.diagnostics_heading.parentWidget().layout()
        self.assertEqual(layout.indexOf(tab.diagnostics_toggle), 0)
        self.assertEqual(layout.contentsMargins().left(), 0)
        self.assertEqual(tab.diagnostics_toggle.x(), 0)
        self.assertEqual(tab.diagnostics_toggle.width(), 20)
        self.assertEqual(tab.diagnostics_toggle.arrowType(), Qt.ArrowType.DownArrow)
        self.assertEqual(tab.diagnostics_toggle.toolTip(), 'Collapse Finding List')
        before = tab.diagnostics_panel.height()
        tab.diagnostics_toggle.click()
        self.app.processEvents()
        self.assertTrue(tree.isHidden())
        self.assertTrue(tab.diagnostics_heading.isVisible())
        self.assertLess(tab.diagnostics_panel.height(), before)
        self.assertEqual(tab.diagnostics_toggle.accessibleName(), 'Expand Finding List')
        self.assertEqual(tab.diagnostics_toggle.arrowType(), Qt.ArrowType.UpArrow)
        self.assertEqual(tab.diagnostics_toggle.toolTip(), 'Expand Finding List')
        tab.editor.setPlainText('Task: Please recieve text\n')
        self.assertEqual(tab.diagnostics_heading.text(), 'Finding List')
        self.assertEqual({severity: label.text() for severity, label in tab.diagnostic_count_labels.items()},
                         {'critical': '0', 'error': '0', 'warning': '1', 'information': '0'})
        self.assertTrue(tree.isHidden())
        self.assertTrue(tab.editor._spelling_selections)
        tab.diagnostics_toggle.click()
        self.app.processEvents()
        self.assertFalse(tree.isHidden())
        self.assertEqual(tab.diagnostics_toggle.arrowType(), Qt.ArrowType.DownArrow)
        self.assertEqual(tab.diagnostics_toggle.accessibleName(), 'Collapse Finding List')
        self.assertEqual(tab.diagnostics_toggle.toolTip(), 'Collapse Finding List')
        self.assertGreater(tab.diagnostics_panel.height(), before // 2)

    def test_header_counts_match_rows_in_severity_order_with_shared_icons(self):
        from collections import Counter
        from PySide6.QtCore import QSize, Qt
        from AgStudio.gui.app import _finding_icon
        tab = self.tab
        severities = ('critical', 'error', 'warning', 'information')
        self.assertEqual(tuple(tab.diagnostic_count_labels), severities)
        self.assertEqual(tuple(tab.diagnostic_count_icons), severities)
        rows = [tab.diagnostic_list.topLevelItem(i) for i in range(tab.diagnostic_list.topLevelItemCount())]
        counts = Counter(row.data(0, Qt.ItemDataRole.UserRole).severity for row in rows)
        self.assertEqual(set(counts), set(severities))
        positions = []
        for index, severity in enumerate(severities):
            count = tab.diagnostic_count_labels[severity]
            icon = tab.diagnostic_count_icons[severity]
            self.assertEqual(count.text(), str(counts[severity]))
            self.assertIs(tab.diagnostic_counts.layout().itemAt(index).widget(), count.parentWidget())
            pair = count.parentWidget().layout()
            self.assertIs(pair.itemAt(0).widget(), count)
            self.assertIs(pair.itemAt(1).widget(), icon)
            self.assertFalse(icon.pixmap().isNull())
            expected = _finding_icon(tab.style(), severity).pixmap(QSize(16, 16), tab.devicePixelRatioF())
            self.assertEqual(icon.pixmap().toImage(), expected.toImage())
            for row in rows:
                if row.data(0, Qt.ItemDataRole.UserRole).severity == severity:
                    self.assertEqual(row.icon(0).pixmap(QSize(16, 16), tab.devicePixelRatioF()).toImage(),
                                     icon.pixmap().toImage())
            self.assertIn(severity, count.accessibleName())
            self.assertIn(str(counts[severity]), count.parentWidget().toolTip())
            self.assertTrue(count.isVisible())
            self.assertTrue(icon.isVisible())
            self.assertLess(count.geometry().right(), icon.geometry().left())
            positions.append(count.parentWidget().x())
        self.assertEqual(positions, sorted(positions))
        before = {severity: label.text() for severity, label in tab.diagnostic_count_labels.items()}
        tab.diagnostics_toggle.click()
        self.app.processEvents()
        self.assertTrue(tab.diagnostic_list.isHidden())
        self.assertEqual({severity: label.text() for severity, label in tab.diagnostic_count_labels.items()}, before)
        self.assertTrue(tab.diagnostic_counts.isVisible())
        tab.editor.setPlainText('Task: ordinary prose\n')
        self.app.processEvents()
        self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 0)
        for severity in severities:
            self.assertEqual(tab.diagnostic_count_labels[severity].text(), '0')
            self.assertTrue(tab.diagnostic_count_labels[severity].isVisible())
            self.assertTrue(tab.diagnostic_count_icons[severity].isVisible())
        self.assertEqual(tab.diagnostic_status.text(), '')

    def test_critical_icon_is_distinct_readable_and_scalable(self):
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QStyle
        from AgStudio.gui.app import _finding_icon
        style = self.tab.style()
        critical = _finding_icon(style, 'critical')
        for size in (16, 24, 32):
            with self.subTest(size=size):
                image = critical.pixmap(size, size).toImage()
                self.assertEqual(image.size(), QSize(size, size))
                for severity in ('error', 'warning', 'information'):
                    # Compare rendered pixels; separately created identical icons
                    # have different cache keys and must still fail this check.
                    self.assertNotEqual(image, _finding_icon(style, severity).pixmap(size, size).toImage())
                self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
                center = image.pixelColor(size // 2, size // 2)
                self.assertGreater(center.red(), 240)
                self.assertGreater(center.green(), 240)
                self.assertGreater(center.blue(), 240)
                fill = image.pixelColor(size // 4, size // 2)
                self.assertGreater(fill.red(), fill.green() + 100)
                self.assertEqual(fill.alpha(), 255)
        hidpi = critical.pixmap(QSize(16, 16), 2.0)
        self.assertEqual(hidpi.size(), QSize(32, 32))
        self.assertEqual(hidpi.devicePixelRatio(), 2.0)
        # Keep the other severity artwork unchanged.
        for severity, standard in (('error', QStyle.StandardPixmap.SP_MessageBoxCritical),
                                   ('warning', QStyle.StandardPixmap.SP_MessageBoxWarning),
                                   ('information', QStyle.StandardPixmap.SP_MessageBoxInformation)):
            self.assertEqual(_finding_icon(style, severity).pixmap(16, 16).toImage(),
                             style.standardIcon(standard).pixmap(16, 16).toImage())

    def spelling_menu(self, source='Task:\r\n- 🌍 Please recieve text\r\n'):
        from AgStudio.gui.app import DocumentTab, _display_offset
        self.tab.close()
        self.tab.deleteLater()
        self.tab = DocumentTab('current', source)
        start = _display_offset(source, source.index('recieve'))
        menu = self.tab.editor.spelling_context_menu(start + 2)
        self.addCleanup(menu.deleteLater)
        return menu, start

    def test_replacement_uses_clicked_word_preserves_crlf_unicode_and_undo(self):
        from PySide6.QtGui import QTextCursor
        source = 'Task:\r\n- 🌍 Please recieve text and recieve more\r\n'
        menu, start = self.spelling_menu(source)
        editor = self.tab.editor
        editor.moveCursor(QTextCursor.MoveOperation.End)
        target = editor.spelling_target_at(start)
        self.assertNotIn('receive', [a.text() for a in menu.actions()])
        self.assertTrue(any('Copy' in action.text() for action in menu.actions()))
        editor._replace_spelling(target.start, target.end, target.word, target.revision, 'receive')
        self.assertEqual(self.tab.source, source.replace('recieve', 'receive', 1))
        self.assertEqual(editor.textCursor().position(), start + len('receive'))
        editor.undo()
        self.assertEqual(self.tab.source, source)
        editor.redo()
        self.assertEqual(self.tab.source, source.replace('recieve', 'receive', 1))
        self.assertEqual(self.tab.diagnostic_list.topLevelItemCount(), 1)
        self.assertEqual(self.tab.diagnostic_list.topLevelItem(0).text(0), 'Warning')

    def test_stale_and_read_only_menu_actions_do_not_modify_source(self):
        menu, start = self.spelling_menu()
        editor = self.tab.editor
        target = editor.spelling_target_at(start)
        editor.setPlainText('Task: Different text\n')
        editor._replace_spelling(target.start, target.end, target.word, target.revision, 'receive')
        self.assertEqual(self.tab.source, 'Task: Different text\r\n')
        menu, start = self.spelling_menu()
        editor = self.tab.editor
        target = editor.spelling_target_at(start)
        source = self.tab.source
        editor.setReadOnly(True)
        editor._replace_spelling(target.start, target.end, target.word, target.revision, 'receive')
        self.assertEqual(self.tab.source, source)
        read_only = editor.spelling_context_menu(start)
        self.addCleanup(read_only.deleteLater)
        self.assertNotIn('receive', [a.text() for a in read_only.actions()])
        self.assertIsNone(editor.spelling_target_at(start))

    def test_menu_boundary_no_suggestions_and_real_context_event(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QContextMenuEvent, QTextCursor
        from PySide6.QtWidgets import QApplication, QMenu
        menu, start = self.spelling_menu()
        outside = self.tab.editor.spelling_context_menu(start + 7)
        self.addCleanup(outside.deleteLater)
        self.assertNotIn('receive', [a.text() for a in outside.actions()])
        # Construction is inert, even for a flagged word. Only the mouse event
        # delegates to the asynchronous correction controller.
        self.assertNotIn('receive', [a.text() for a in menu.actions()])
        self.assertNotIn('Loading suggestions…', [a.text() for a in menu.actions()])
        self.tab.show()
        self.app.processEvents()
        cursor = QTextCursor(self.tab.editor.document())
        cursor.setPosition(start + 2)
        point = self.tab.editor.cursorRect(cursor).center()
        def close_popup():
            popup = QApplication.activePopupWidget()
            if isinstance(popup, QMenu):
                popup.close()
        for reason, calls in ((QContextMenuEvent.Reason.Mouse, 1),
                              (QContextMenuEvent.Reason.Keyboard, 0)):
            event = QContextMenuEvent(reason, point,
                                      self.tab.editor.viewport().mapToGlobal(point))
            with patch.object(self.tab.editor.spelling_suggestions, 'attach') as attach:
                QTimer.singleShot(30, close_popup)
                self.tab.editor.contextMenuEvent(event)
                self.assertEqual(attach.call_count, calls)
                if calls:
                    self.assertEqual(attach.call_args.args[1].word, 'recieve')
            self.assertTrue(event.isAccepted())

    def test_suggestions_preserve_title_and_uppercase(self):
        from AgStudio.shared.lint.spelling import suggestions_for_word
        self.assertIn('Receive', suggestions_for_word('Recieve'))
        self.assertIn('RECEIVE', suggestions_for_word('RECIEVE'))


if __name__ == '__main__':
    unittest.main()
