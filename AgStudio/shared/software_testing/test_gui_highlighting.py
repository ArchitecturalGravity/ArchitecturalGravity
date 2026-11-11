"""Guide-marker rendering and active-row integration, without conformance claims."""
from __future__ import annotations

import importlib.util
import os
import unittest

from AgStudio.shared import LanguageCore
from AgStudio.shared.highlighting import highlight_tokens

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def parse(source):
    return LanguageCore.parse_document(LanguageCore.open_source(source, arcgrav_version='current'))


def operation_findings(tab):
    return tuple(f for f in tab.diagnostics.findings if f.rule_id == 'AG-OPERATION-LIST')


def operation_item(tab):
    return next(tab.diagnostic_list.topLevelItem(i)
                for i in range(tab.diagnostic_list.topLevelItemCount())
                if tab.diagnostic_list.topLevelItem(i).text(1) == 'AG-OPERATION-LIST')


class TokenProjectionTests(unittest.TestCase):
    def test_exact_markers_not_candidate_bodies(self):
        source = ('Scope: file\n- Plain text\n1. First step\nP0. Important\n'
                  '=> Parse [Source] AS [Parsed] ↳\n  - Child:\n'
                  'All `*_test.py` under tests/*\n')
        tokens = highlight_tokens(parse(source))
        self.assertEqual([token.span.extract(source) for token in tokens],
                         ['Scope', ':', '-', '1.', 'P0.', '=>', '[', 'Source', ']', 'AS', '[', 'Parsed', ']', '↳', '-', '`', '*_test.py', '`', '*'])
        self.assertEqual(tokens, highlight_tokens(parse(source)))
        for token in tokens:
            if token.role not in {'bullet', 'priority', 'sequence'}:
                self.assertNotIn(' ', token.span.extract(source))

    def test_prose_and_unspecified_punctuation_are_not_operators(self):
        source = ('Ordinary AS prose and x => y, a - b, P0. in prose\n'
                  'prose: with words\n`name` + {} .Focus "scalar"\n')
        tokens = highlight_tokens(parse(source))
        # A compact arbitrary section label is recognized, never a reserved word.
        self.assertEqual([token.span.extract(source) for token in tokens], ['prose', ':', '`', 'name', '`', '"', 'scalar', '"'])

    def test_literal_body_is_never_active_syntax(self):
        for delimiter in ('"""', '""""'):
            source = f'{delimiter}\n[False]: => - AS [Alias] * ↳\n{delimiter}\n=> Real\n'
            tokens = highlight_tokens(parse(source))
            self.assertEqual([token.role for token in tokens],
                             ['delimiter', 'literal', 'delimiter', 'operation'])
            self.assertEqual(tokens[1].span.extract(source), '[False]: => - AS [Alias] * ↳')
        source = '"""\n=> - unfinished [Fake]\n'
        self.assertEqual([token.role for token in highlight_tokens(parse(source))],
                         ['delimiter', 'literal'])

    def test_unknown_boundaries_remain_recognition_not_validity(self):
        document = parse('=>\twork\n[Open\nScope:\tvalue\n')
        tokens = highlight_tokens(document)
        self.assertEqual([token.span.extract(document.source) for token in tokens], ['=>', '['])
        self.assertTrue(all('boundary' in token.recognition_kind for token in tokens))
        from AgStudio.shared.lint import analyze
        self.assertFalse(any(f.rule_id == 'AG-OPERATION-LIST' for f in analyze(document.source).diagnostics.findings))
        self.assertTrue(document.recoveries)
        self.assertTrue(all(document.relationship(f.id, 'containment').status != 'supported'
                            for f in document.facts()))


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is not installed')
class EditorHighlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.app import DocumentTab
        self.tab = DocumentTab('current', background=False)
        self.tab.resize(900, 600)
        self.tab.show()
        self.app.processEvents()

    def tearDown(self):
        self.tab.close()
        self.tab.deleteLater()
        self.app.processEvents()

    def test_critical_gui_label_navigation_and_same_line_precedence(self):
        from PySide6.QtWidgets import QApplication
        from AgStudio.gui.app import DocumentTab
        app = QApplication.instance() or QApplication([])
        # The second line also has AG-LINE-ENDING (Error).
        source = 'First: value\nSecond: value.\n'
        tab = DocumentTab('current', source)
        try:
            self.assertTrue(any(f.severity == 'error' and f.source_range.start.line == 2
                                for f in tab.diagnostics.findings))
            self.assertEqual(tab.editor.finding_severities[2], 'critical')
            rows = [tab.diagnostic_list.topLevelItem(i)
                    for i in range(tab.diagnostic_list.topLevelItemCount())]
            row = next(row for row in rows if row.text(1) == 'AG-BLOCK-SEPARATOR')
            self.assertEqual(row.text(0), 'Critical')
            self.assertFalse(row.icon(0).isNull())
            tab._navigate_finding(row)
            self.assertEqual(tab.editor.textCursor().selectedText(), ':')
            tab.show()
            app.processEvents()
            self.assertFalse(tab.editor.gutter.grab().isNull())
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

    def test_spelling_squiggles_without_hover_and_unavailable_info(self):
        from unittest.mock import patch
        from PySide6.QtGui import QTextCharFormat, QTextCursor, QHelpEvent
        from PySide6.QtCore import QEvent
        from AgStudio.shared.lint import spelling
        from AgStudio.gui.app import DocumentTab, _display_offset
        source = 'Task:\r\n- 🌍 Please recieve `mispelled` text\r\n'
        tab = DocumentTab('current', source)
        try:
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 1)
            self.assertIn('1 findings', tab.diagnostics_heading.toolTip())
            self.assertEqual(tab.editor.finding_severities, {2: 'warning'})
            self.assertEqual(tab.diagnostic_count_labels['warning'].text(), '1')
            row = tab.diagnostic_list.topLevelItem(0)
            self.assertEqual((row.text(0), row.text(1), row.text(3), row.text(4)),
                             ('Warning', 'AG-SPELLING', '2', '12'))
            self.assertFalse(row.icon(0).isNull())
            self.assertEqual(row.icon(0).cacheKey(), tab._finding_icons['warning'].cacheKey())
            tab._navigate_finding(row)
            self.assertEqual(tab.editor.textCursor().selectedText(), 'recieve')
            self.assertTrue(any(f.rule_id == 'AG-SPELLING' for f in tab.diagnostics.findings))
            underlines = tab.editor._spelling_selections
            self.assertEqual(len(underlines), 1)
            selection = underlines[0]
            self.assertEqual(selection.cursor.selectedText(), 'recieve')
            self.assertEqual(selection.format.underlineStyle(), QTextCharFormat.UnderlineStyle.WaveUnderline)
            start = _display_offset(source, source.index('recieve'))
            self.assertEqual((selection.cursor.selectionStart(), selection.cursor.selectionEnd()), (start, start + 7))
            self.assertEqual(tab.editor.spelling_message_at(start), 'Possible English misspelling: recieve')
            self.assertIsNone(tab.editor.spelling_message_at(start + 7))
            self.assertIsNone(tab.editor.spelling_message_at(start - 1))
            tab.editor.set_pulse_ranges(((0, 4),))
            tab.editor.paint_pulse(0.5)
            tab.editor.moveCursor(QTextCursor.MoveOperation.End)
            tab.editor.apply_color_scheme(tab.editor.color_scheme)
            self.assertEqual(sum(x.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
                                 for x in tab.editor.extraSelections()), 1)
            tab.show()
            self.app.processEvents()
            cursor = QTextCursor(tab.editor.document())
            cursor.setPosition(start + 2)
            point = tab.editor.cursorRect(cursor).center()
            event = QHelpEvent(QEvent.Type.ToolTip, point, tab.editor.viewport().mapToGlobal(point))
            with patch('AgStudio.gui.app.QToolTip.showText') as show:
                self.assertTrue(tab.editor.viewportEvent(event))
                show.assert_not_called()
            self.assertEqual(tab.source, source)
            tab.editor.setPlainText('Task:\n- Please receive text\n')
            self.assertFalse(tab.editor._spelling_selections)
            tab.editor.setPlainText('Task:\n- `recieve` text\n')
            self.assertFalse(tab.editor._spelling_selections)
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 0)
        finally:
            tab.close()
            tab.deleteLater()
            self.app.processEvents()
        with patch.object(spelling, '_CHECKER', None):
            tab = DocumentTab('current', source)
            try:
                self.assertFalse(tab.editor._spelling_selections)
                row = tab.diagnostic_list.topLevelItem(0)
                self.assertEqual((row.text(0), row.text(1)), ('Info', 'AG-SPELLCHECK-UNAVAILABLE'))
            finally:
                tab.close()
                tab.deleteLater()
                self.app.processEvents()

    def test_spelling_wave_ranges_preserve_unicode_line_endings(self):
        from AgStudio.gui.app import DocumentTab, _display_offset
        for ending in ('\n', '\r\n', '\u2028'):
            source = ending.join(['Task:', '- 🌍 mispelled text', ''])
            tab = DocumentTab('current', source)
            try:
                selection = tab.editor._spelling_selections[0]
                self.assertEqual(selection.cursor.selectedText(), 'mispelled')
                self.assertEqual(selection.cursor.selectionStart(), _display_offset(source, source.index('mispelled')))
                self.assertEqual(selection.cursor.selectionEnd(), _display_offset(source, source.index('mispelled') + 9))
                self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 1)
                row = tab.diagnostic_list.topLevelItem(0)
                self.assertEqual((row.text(0), row.text(3), row.text(4)), ('Warning', '2', '5'))
                tab._navigate_finding(row)
                self.assertEqual(tab.editor.textCursor().selectedText(), 'mispelled')
                self.assertEqual(tab.source, source)
            finally:
                tab.close()
                tab.deleteLater()
                self.app.processEvents()

    def test_initial_section_info_is_visible_and_clears_on_correction(self):
        from AgStudio.gui.app import DocumentTab
        from AgStudio.shared.lint.document_end import START_MESSAGE
        source = 'Read text\n\nTask: value\n'
        tab = DocumentTab('current', source)
        try:
            self.assertIsNone(tab.path)
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 1)
            row = tab.diagnostic_list.topLevelItem(0)
            self.assertEqual(row.text(0), 'Info')
            self.assertEqual(row.text(1), 'AG-DOCUMENT-START-SECTION')
            self.assertEqual(tab.diagnostic_list.columnCount(), 5)
            self.assertEqual([tab.diagnostic_list.headerItem().text(i) for i in range(5)],
                             ['Severity', 'Rule ID', 'Message', 'Line', 'Column'])
            self.assertTrue(row.toolTip(0).startswith('AG-DOCUMENT-START-SECTION\n'))
            self.assertFalse(row.icon(0).isNull())
            self.assertIn(START_MESSAGE, [row.text(i) for i in range(tab.diagnostic_list.columnCount())])
            self.assertEqual(set(tab.editor.finding_severities.values()), {'information'})
            tab._navigate_finding(row)
            self.assertEqual(tab.editor.textCursor().selectedText(), 'Read text')
            self.assertEqual(tab.source, source)
            tab.editor.setPlainText('Task:\n- Read text\n')
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 0)
        finally:
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_unsaved_symbolic_parent_has_critical_finding_without_text_change(self):
        from AgStudio.gui.app import DocumentTab
        source = '[Something]:\n- Whatever\n\n'
        tab = DocumentTab('current', source)
        try:
            self.assertIsNone(tab.path)
            rows = [tab.diagnostic_list.topLevelItem(i)
                    for i in range(tab.diagnostic_list.topLevelItemCount())]
            row = next(row for row in rows if row.text(1) == 'AG-DOCUMENT-END-SECTION')
            self.assertEqual(row.text(0), 'Critical')
            self.assertTrue(any(row.text(1) == 'AG-SYMBOL-UNUSED' for row in rows))
            tab._navigate_finding(row)
            self.assertEqual(tab.editor.textCursor().selectedText(), '[Something]:')
            self.assertEqual(tab.source, source)
        finally:
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_final_parent_critical_remains_in_finding_list(self):
        from AgStudio.gui.app import DocumentTab
        tab = DocumentTab('current', '=> Parent:\n  - Child\n')
        try:
            self.assertEqual(tab.diagnostics_heading.text(), 'Finding List')
            self.assertEqual(sum(int(label.text()) for label in tab.diagnostic_count_labels.values()), tab.diagnostic_list.topLevelItemCount())
            row = next(tab.diagnostic_list.topLevelItem(i)
                       for i in range(tab.diagnostic_list.topLevelItemCount())
                       if tab.diagnostic_list.topLevelItem(i).text(1) == 'AG-DOCUMENT-END-SECTION')
            self.assertEqual(row.text(0), 'Critical')
            tab._navigate_finding(row)
            self.assertEqual(tab.editor.textCursor().selectedText(), '=> Parent:')
            tab.editor.setPlainText('Task:\n- Child\n')
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 0)
        finally:
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_qt_formats_only_markers_with_utf16_and_crlf(self):
        from AgStudio.gui.app import DocumentTab, _display_offset
        self.tab.close()
        source = 'Scope: 🌍 [Target]\r\n=> Read prose\r\n'
        self.tab = DocumentTab('current', source, encoding='utf-8-sig', background=False)
        scheme = self.tab.editor.color_scheme.copy()
        # Distinct styles keep Qt from merging adjacent roles in editable palettes.
        scheme['colon'] = {'foreground': [20, 30, 40, 255], 'background': [0, 0, 0, 0]}
        scheme['symbol_body'] = {'foreground': [1, 2, 3, 255], 'background': [4, 5, 6, 50]}
        self.tab.highlighter.apply_color_scheme(scheme)
        self.app.processEvents()
        block = self.tab.editor.document().firstBlock()
        spans = [(f.start, f.length) for f in block.layout().formats()]
        self.assertEqual(spans, [(0, 5), (5, 1), (10, 1), (11, 6), (17, 1)])
        self.assertEqual(_display_offset(source, source.index('[')), 10)
        self.assertEqual(self.tab.source, source)
        self.assertTrue(self.tab.source.encode(self.tab.encoding).startswith(b'\xef\xbb\xbf'))
        block = block.next()
        self.assertEqual([(f.start, f.length) for f in block.layout().formats()], [(0, 2)])

    def test_rgba_bracket_formats_in_canonical_analysis(self):
        from PySide6.QtGui import QPalette
        from AgStudio.gui.app import DocumentTab
        from AgStudio.gui.color_schemes import default_scheme
        scheme = default_scheme()
        tab = DocumentTab('current', '🌍 [Target] prose\n"""\n[Literal]\n"""\n')
        try:
            # Distinct synthetic body style prevents Qt merging equal adjacent runs.
            scheme['symbol_body'] = {'foreground': [1, 2, 3, 255], 'background': [4, 5, 6, 50]}
            tab.highlighter.apply_color_scheme(scheme)
            self.app.processEvents()
            formats = tab.editor.document().firstBlock().layout().formats()
            self.assertEqual([(f.start, f.length) for f in formats], [(3, 1), (4, 6), (10, 1)])
            self.assertEqual(formats[0].format.foreground().color().getRgb(), tuple(scheme['symbol']['foreground']))
            self.assertEqual(formats[1].format.background().color().getRgb(), tuple(scheme['symbol_body']['background']))
            self.assertEqual(formats[1].format.foreground().color().getRgb(), tuple(scheme['symbol_body']['foreground']))
            self.assertEqual(formats[2].format.foreground().color().getRgb(), tuple(scheme['symbol']['foreground']))
            self.assertEqual(tab.editor.viewport().palette().color(QPalette.ColorRole.Base).getRgb(), tuple(scheme['editor']['background']))
            self.assertEqual(sum(role == 'symbol_body' for _, _, role in tab.highlighter.ranges), 1)
            self.assertEqual(tab.source, '🌍 [Target] prose\n"""\n[Literal]\n"""\n')
        finally:
            tab.close()
            tab.deleteLater()

    def test_rgba_list_roles_exclude_space_and_all_syntax_is_bold(self):
        from PySide6.QtGui import QFont
        from AgStudio.gui.app import DocumentTab
        from AgStudio.gui.color_schemes import default_scheme
        scheme = default_scheme()
        source = '[Source] AS [Target]\nP0. urgent\nP12. later\n1. first\n24. later\n- item\n'
        tab = DocumentTab('current', source)
        try:
            tokens = highlight_tokens(tab.document)
            list_tokens = [t for t in tokens if t.role in {'priority', 'sequence', 'bullet'}]
            self.assertEqual([(t.span.extract(source), t.role) for t in list_tokens],
                             [('P0.', 'priority'), ('P12.', 'priority'),
                              ('1.', 'sequence'), ('24.', 'sequence'), ('-', 'bullet')])
            self.assertEqual(tab.highlighter._formats['symbol'].background().color().getRgb(), tuple(scheme['symbol']['background']))
            self.assertEqual(tab.highlighter._formats['alias'].foreground().color().getRgb(), tuple(scheme['alias']['foreground']))
            for role, fmt in tab.highlighter._formats.items():
                if role not in {'literal', 'backtick_content', 'double_quote_content'}:
                    self.assertEqual(fmt.fontWeight(), QFont.Weight.Bold)
            for role in ('priority', 'sequence', 'bullet'):
                fmt = tab.highlighter._formats[role]
                self.assertEqual(fmt.foreground().color().getRgb(), tuple(scheme[role]['foreground']))
                self.assertEqual(fmt.background().color().getRgb(), tuple(scheme[role]['background']))
        finally:
            tab.close()
            tab.deleteLater()

    def test_complete_loaded_palette_and_transparent_roles(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont, QPalette
        from AgStudio.gui.color_schemes import default_scheme
        scheme = default_scheme()
        palette = self.tab.editor.palette()
        # Content backgrounds belong to the viewport so native scrollbar
        # tracks do not inherit the editor's dark/custom background.
        self.assertEqual(self.tab.editor.viewport().palette().color(QPalette.ColorRole.Base).getRgb(),
                         tuple(scheme['editor']['background']))
        for qt_role, role, kind in [(QPalette.ColorRole.Text, 'editor', 'foreground'),
                                    (QPalette.ColorRole.Highlight, 'selection', 'background'),
                                    (QPalette.ColorRole.HighlightedText, 'selection', 'foreground')]:
            self.assertEqual(palette.color(qt_role).getRgb(), tuple(scheme[role][kind]))
        for role, fmt in self.tab.highlighter._formats.items():
            self.assertEqual(fmt.foreground().color().getRgb(), tuple(scheme[role]['foreground']))
            if scheme[role]['background'][3]:
                self.assertEqual(fmt.background().color().getRgb(), tuple(scheme[role]['background']))
            else:
                self.assertEqual(fmt.background().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(self.tab.highlighter._formats['literal'].fontWeight(), QFont.Weight.Normal)
        self.assertEqual(self.tab.editor.font().weight(), QFont.Weight.Normal)

    def test_bracket_background_does_not_leak_after_edit_undo_redo(self):
        from AgStudio.gui.app import DocumentTab
        self.tab.close()
        self.tab = DocumentTab('current', '[Target] prose', background=False)
        editor = self.tab.editor
        self.assertIn('symbol_body', [r[2] for r in self.tab.highlighter.ranges])
        from PySide6.QtGui import QTextCursor
        editor.moveCursor(QTextCursor.MoveOperation.Start)
        editor.textCursor().deleteChar()
        self.assertNotIn('symbol_body', [r[2] for r in self.tab.highlighter.ranges])
        editor.undo()
        self.assertIn('symbol_body', [r[2] for r in self.tab.highlighter.ranges])
        editor.redo()
        self.assertNotIn('symbol_body', [r[2] for r in self.tab.highlighter.ranges])

    def test_full_width_row_preserves_diagnostic_and_multiline_selection(self):
        from PySide6.QtGui import QTextCursor, QTextFormat
        tab = self.tab
        tab.editor.setPlainText('[Task]: 🌍\n=> - Active\nlast\n')
        tab._navigate_finding(operation_item(tab))
        self.assertEqual(tab.editor.textCursor().selectedText(), '=> - ')
        selection = tab.editor.extraSelections()[0]
        self.assertTrue(selection.format.property(QTextFormat.Property.FullWidthSelection))
        self.assertFalse(selection.cursor.hasSelection())
        self.assertEqual(selection.cursor.blockNumber(), 1)
        cursor = tab.editor.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        tab.editor.setTextCursor(cursor)
        selected = tab.editor.textCursor().selectedText()
        self.app.processEvents()
        self.assertEqual(tab.editor.textCursor().selectedText(), selected)
        selection = tab.editor.extraSelections()[0]
        self.assertEqual(selection.cursor.blockNumber(), 3)
        self.assertFalse(selection.cursor.hasSelection())

    def test_row_background_reaches_far_edge_and_empty_line(self):
        from PySide6.QtGui import QColor, QTextCursor
        editor = self.tab.editor
        scheme = editor.color_scheme.copy()
        scheme['editor'] = {'foreground': [255, 255, 255, 255], 'background': [0, 0, 0, 255]}
        scheme['active_row'] = {'foreground': [0, 0, 0, 0], 'background': [40, 40, 40, 255]}
        editor.apply_color_scheme(scheme)
        editor.setPlainText('short\n\nthird')
        editor.moveCursor(QTextCursor.MoveOperation.Down)
        self.app.processEvents()
        rect = editor.cursorRect()
        shot = editor.viewport().grab().toImage()
        self.assertEqual(shot.pixelColor(shot.width() - 10, rect.center().y()), QColor(40, 40, 40, 255))
        self.assertNotEqual(shot.pixelColor(shot.width() - 10, rect.center().y() + rect.height()),
                            QColor(40, 40, 40, 255))

    def test_edit_undo_redo_recomputes_literal_isolation(self):
        from PySide6.QtGui import QTextCursor
        from AgStudio.gui.app import DocumentTab
        self.tab.close()
        self.tab = DocumentTab('current', '=> - Active\n', background=False)
        editor = self.tab.editor
        self.assertEqual(len(operation_findings(self.tab)), 1)
        editor.moveCursor(QTextCursor.MoveOperation.Start)
        editor.insertPlainText('"""\n')
        self.assertEqual(operation_findings(self.tab), ())
        self.assertEqual([r[2] for r in self.tab.highlighter.ranges], ['delimiter', 'literal'])
        editor.undo()
        self.assertEqual(len(operation_findings(self.tab)), 1)
        self.assertEqual([r[2] for r in self.tab.highlighter.ranges], ['operation', 'bullet'])
        editor.redo()
        self.assertEqual(operation_findings(self.tab), ())
        self.assertEqual([r[2] for r in self.tab.highlighter.ranges], ['delimiter', 'literal'])

    def test_tab_transitions_keep_independent_carets_and_exact_selection(self):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtGui import QTextCursor
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow
        window = StudioWindow('current', user_state=UserState(), background=False)
        try:
            first = window.current()
            first.editor.insertPlainText('first\n=> - Active\n')
            first._navigate_finding(operation_item(first))
            second = window.new_document()
            second.editor.insertPlainText('one\ntwo\nthree')
            second.editor.moveCursor(QTextCursor.MoveOperation.End)
            for _ in range(3):
                window.tabs.setCurrentWidget(first)
                self.assertEqual(first.editor.textCursor().selectedText(), '=> - ')
                selection = first.editor.extraSelections()[0]
                self.assertEqual(selection.cursor.blockNumber(), 1)
                window.tabs.setCurrentWidget(second)
                selection = second.editor.extraSelections()[0]
                self.assertEqual(selection.cursor.blockNumber(), 2)
                self.assertFalse(second.editor.textCursor().hasSelection())
        finally:
            with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
                window.close()
            window.deleteLater()

    def test_editor_diagnostics_matrix_keeps_unsupported_cases_unknown(self):
        cases = [('=> - Mixed\n', ['=> - ']), ('  => - Mixed\n', ['=> - ']),
                 ('=> Parse [Source]\n', []), ('=> 1. Mixed\n', ['=> 1. ']),
                 ('=> P0. Mixed\n', ['=> P0. ']), ('- => Mixed\n', ['- => ']),
                 # Editor input converts tabs to two ASCII spaces before analysis.
                 ('=>\t- Mixed\n', ['=>  - ']), ('"""\n=> - literal\n"""\n', []),
                 ('""""\n"""\n=> - literal\n"""\n""""\n', []),
                 ('[Unknown]\n[Duplicate]: first\n[Duplicate]: second\n', []),
                 ('Parent:\n   - odd\n\t- tab\n', [])]
        for source, expected in cases:
            with self.subTest(source=source):
                self.tab.editor.setPlainText(source)
                findings = operation_findings(self.tab)
                self.assertEqual([f.source_range.span.extract(self.tab.source) for f in findings], expected)
                self.assertEqual(self.tab.diagnostic_list.topLevelItemCount(),
                                 len(self.tab.diagnostics.findings))
                self.assertIn('conformance unknown', self.tab.diagnostics_heading.toolTip())
                self.assertTrue(all(f.severity == 'error' for f in findings))


if __name__ == '__main__':
    unittest.main()
