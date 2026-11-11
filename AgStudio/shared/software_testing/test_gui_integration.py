"""Offscreen Foundation editor and canonical projection integration."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from AgStudio.gui.structure import outline_entries

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HAS_QT = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class GuiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_open_edit_save_and_views_use_canonical_source(self) -> None:
        from PySide6.QtGui import QTextCursor
        from AgStudio.gui.user_state import UserState
        from AgStudio.gui.app import StudioWindow, _display_offset
        studio_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(dir=studio_root) as directory:
            path = Path(directory) / "sample.arc"
            original = (b'\xef\xbb\xbf[Task]: \xf0\x9f\x8c\x8d\r\n"""\r\n'
                        b'[False]: *\r\n"""\r\n=> - Active\r\n')
            path.write_bytes(original)
            window = StudioWindow("current", user_state=UserState(), background=False)
            try:
                tab = window.open_file(path)
                self.assertEqual(tab.encoding, "utf-8-sig")
                self.assertEqual(tab.source.encode(tab.encoding), original)
                self.assertEqual(tab.document.source, tab.source)
                self.assertEqual(len([f for f in tab.diagnostics.findings if f.rule_id == 'AG-OPERATION-LIST']), 1)
                self.assertEqual(tab.diagnostic_list.topLevelItemCount(), len(tab.diagnostics.findings))
                self.assertIn(5, tab.editor.finding_lines)
                self.assertIn("overall conformance unknown", tab.diagnostics_heading.toolTip())
                self.assertTrue(all("[False]" not in entry.source_range.span.extract(tab.source)
                                    for entry in outline_entries(tab.document)))
                self.assertEqual(tab.outline.topLevelItemCount(), 3)
                self.assertEqual([tab.outline.topLevelItem(i).text(0) for i in range(3)],
                                 ['[Task]: 🌍', 'Literal block', '=> - Active'])
                tab.save()
                self.assertEqual(path.read_bytes(), original)
                self.assertIn("CRLF", tab.status_text())

                operation_item = next(tab.diagnostic_list.topLevelItem(i) for i in range(tab.diagnostic_list.topLevelItemCount()) if tab.diagnostic_list.topLevelItem(i).text(1) == 'AG-OPERATION-LIST')
                tab._navigate_finding(operation_item)
                self.assertEqual(tab.editor.textCursor().selectedText(), "=> - ")

                first = tab.document.structural_facts[0]
                tab.navigate(first.span.start, first.span.end)
                self.assertEqual(tab.editor.textCursor().selectedText(),
                                 first.span.extract(tab.source).replace("\r\n", "\u2029"))
                tab.editor.moveCursor(QTextCursor.MoveOperation.End)
                tab.editor.insertPlainText("=> additional\n")
                self.assertTrue(tab.dirty)
                self.assertIn("=> additional\r\n", tab.source)
                self.assertEqual(tab.document.source, tab.source)
                tab.editor.undo()
                self.assertNotIn("=> additional", tab.source)
                tab.editor.redo()
                self.assertIn("=> additional", tab.source)
                tab.save()
                self.assertEqual(path.read_bytes(), tab.source.encode("utf-8-sig"))
                self.assertEqual(_display_offset("🌍\r\n", 3), 3)
                self.assertEqual(window.new_document().source, "")
                self.assertGreaterEqual(window.tabs.count(), 3)
            finally:
                window.close()

    def test_literal_and_reference_views_keep_source_limitations(self) -> None:
        from AgStudio.gui.app import DocumentTab
        source = ('"""\n[False]: => - *\n"""\n[Task]: item\n'
                  '`Unknown` [Open\nScope: **/*.arc\n'
                  '=> Send /tmp/secret to https://example.invalid\n')
        with (mock.patch("builtins.open", side_effect=AssertionError("file access")),
              mock.patch("glob.glob", side_effect=AssertionError("wildcard expansion")),
              mock.patch("subprocess.run", side_effect=AssertionError("process")),
              mock.patch("socket.create_connection", side_effect=AssertionError("network"))):
            tab = DocumentTab("unverified", source, background=False)
        try:
            self.assertEqual(tab.document.source, source)
            self.assertEqual(tab.diagnostics.findings, ())
            self.assertIn("Unsupported language version", tab.diagnostics_heading.toolTip())
            self.assertEqual(tab.outline.topLevelItemCount(), 4)
            self.assertEqual(tab.outline.topLevelItem(0).text(0), 'Literal block')
            self.assertTrue(all("[False]" not in entry.source_range.span.extract(source)
                                for entry in outline_entries(tab.document)))
            first = tab.outline.topLevelItem(0)
            tab.outline.setCurrentItem(first)
        finally:
            tab.close()

    def test_diagnostic_severities_and_supported_containment_are_projected(self) -> None:
        from AgStudio.gui.app import DocumentTab
        from AgStudio.shared.lint import analyze
        from AgStudio.shared.lint.model import CanonicalDocument
        from AgStudio.shared.document import RelationshipState
        source = "[Parent]: item\n[Child]: item\n=> - Active\n"
        original_relationship = CanonicalDocument.relationship
        def relationship(document, fact_id, kind):
            facts = document.structural_facts
            if fact_id == facts[1].id and kind == 'containment':
                return RelationshipState('containment', 'supported', fact_id, facts[0].id, ())
            return original_relationship(document, fact_id, kind)
        def analysis(source, **context):
            result = analyze(source, **context)
            finding = next(f for f in result.diagnostics.findings if f.rule_id == 'AG-OPERATION-LIST')
            diagnostics = replace(result.diagnostics, findings=(finding,
                replace(finding, id='warning-id', severity='warning'),
                replace(finding, id='info-id', severity='information')))
            return replace(result, diagnostics=diagnostics)
        with mock.patch.object(CanonicalDocument, 'relationship', relationship), mock.patch('AgStudio.gui.app.analyze', analysis):
            tab = DocumentTab('current', source, background=False)
            try:
                self.assertEqual(tab.outline.topLevelItemCount(), len(tab.document.structural_facts) - 1)
                self.assertEqual(tab.outline.topLevelItem(0).childCount(), 1)
                self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 3)
                self.assertEqual(tab.diagnostic_list.topLevelItem(1).text(0), 'Warning')
                self.assertEqual(tab.diagnostic_list.topLevelItem(2).text(0), 'Info')
            finally:
                tab.close()


if __name__ == "__main__":
    unittest.main()
