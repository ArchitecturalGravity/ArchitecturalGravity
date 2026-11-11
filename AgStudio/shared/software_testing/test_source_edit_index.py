"""Incremental physical source positions and presentation-only signal safety."""
import os
import importlib.util
import random
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class SourceEditIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_incremental_unicode_positions_match_full_reference_after_edits(self):
        from PySide6.QtGui import QTextCursor
        from AgStudio.gui.app import SourceEditor
        editor = SourceEditor()
        self.addCleanup(editor.deleteLater)
        randomizer = random.Random(72)
        for _ in range(250):
            raw = editor.document().toRawText()
            positions, offset = [0], 0
            for char in raw:
                offset += len(char.encode('utf-16-le')) // 2
                positions.append(offset)
            left = randomizer.randrange(len(positions))
            right = randomizer.randrange(left, len(positions)) if randomizer.random() < .5 else left
            cursor = editor.textCursor()
            cursor.setPosition(positions[left])
            cursor.setPosition(positions[right], QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(randomizer.choice(['a', '🌍', '\n', '\u2028', '\u00a0', 'a\nb\n', '']))
            raw = editor.document().toRawText()
            self.assertEqual(editor._display_bytes, raw.encode('utf-16-le'))
            starts, offset = [0], 0
            for line in raw.splitlines(keepends=True):
                offset += len(line.encode('utf-16-le')) // 2
                if line and line[-1] in '\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029':
                    starts.append(offset)
            self.assertEqual(editor._line_positions, tuple(starts))

    def test_dirty_source_preserves_nonbreaking_space_and_line_separator(self):
        from PySide6.QtGui import QTextCursor
        from AgStudio.gui.app import DocumentTab
        source = 'Header:\u2028🌍\u00a0body\n'
        tab = DocumentTab('current', source, map_enabled=False)
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.dispose_analysis)
        cursor = tab.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        tab.editor.setTextCursor(cursor)
        tab.editor.insertPlainText('x')
        self.assertEqual(tab.source, source + 'x')
        self.assertEqual(tab.document.source, source + 'x')
        tab.editor.undo()
        self.assertEqual(tab.source, source)
        tab.editor.redo()
        self.assertEqual(tab.source, source + 'x')

    def test_palette_and_current_projection_never_trigger_source_analysis(self):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', '[A]: value\n', map_enabled=False)
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.dispose_analysis)
        with patch.object(tab, 'refresh_model', side_effect=AssertionError('source changed')):
            tab.highlighter.apply_color_scheme(tab.editor.color_scheme)
            tab.highlighter.update_model(tab.document)
            self.app.processEvents()
        self.assertFalse(tab.dirty)

    def test_large_findings_delivery_batches_metadata_without_reset(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QSignalSpy
        from AgStudio.gui.app import DocumentTab
        from AgStudio.gui.panel_rendering import apply_findings
        from AgStudio.shared.lint import analyze
        from AgStudio.shared.panel_projections import derive_findings
        source = ''.join(f'[Section{i}]: description\n  - value\n  => - do [Section{i}]\n' for i in range(300))
        tab = DocumentTab('current', source, map_enabled=False)
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.dispose_analysis)
        tab.show()
        self.app.processEvents()
        rows = tuple(tab.diagnostic_list.topLevelItem(i) for i in range(tab.diagnostic_list.topLevelItemCount()))
        projection = derive_findings(analyze(source + 'x'))
        changed = QSignalSpy(tab.diagnostic_list.model().dataChanged)
        reset = QSignalSpy(tab.diagnostic_list.model().modelReset)
        apply_findings(tab, projection)
        self.assertEqual(reset.count(), 0)
        self.assertEqual(changed.count(), 1)
        self.assertNotIn(Qt.ItemDataRole.DisplayRole, changed.at(0)[2])
        self.assertEqual(rows, tuple(tab.diagnostic_list.topLevelItem(i) for i in range(len(rows))))
        self.assertEqual([row.data(0, Qt.ItemDataRole.UserRole) for row in rows],
                         [row.finding for row in projection.rows])
