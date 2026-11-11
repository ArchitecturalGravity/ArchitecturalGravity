"""Matching-length standalone literal fences share one core across consumers."""
import unittest
from dataclasses import replace
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission
from AgStudio.shared import LanguageCore
from AgStudio.shared.lint import analyze
from AgStudio.shared.highlighting import highlight_tokens


class LiteralFenceWidthTests(unittest.TestCase):
    def test_arbitrary_width_matching_and_opaque_mismatches(self):
        for n in (3, 4, 5, 9):
            fence = '"' * n
            source = ('[A]: value\r\n\r\n[Literal]:\r\n  ' + fence + '\r\n'
                      + '"' * (n - 1) + '\r\n[Hidden]: 🌍 * => AS [Alias] ↳\r\n'
                      + '"' * (n + 1) + '\r\n' + '  ' + fence + '\r\n\r\nTask:\r\n- Use [A] and [Literal]\r\n')
            result = analyze(source)
            self.assertEqual([f.rule_id for f in result.diagnostics.findings], ['AG-DOCUMENT-START-SECTION', 'AG-LITERAL-FENCE-WIDTH'])
            self.assertFalse(any(s.name in ('Hidden', 'Alias') for s in result.semantics.symbols))
            self.assertEqual(''.join(t.text for t in result.tree.tokens), source)
            legacy = LanguageCore.parse_document(LanguageCore.open_source(source, arcgrav_version='current'))
            for model in (result.document, legacy):
                with self.subTest(width=n, canonical=hasattr(model, 'syntax')):
                    tokens = highlight_tokens(model)
                    self.assertEqual([t.span.extract(source) for t in tokens if t.role == 'delimiter'], [fence, fence])
                    self.assertEqual(len([t for t in tokens if t.role == 'literal']), 3)
                    start, end = source.index(fence), source.rindex(fence) + n
                    self.assertFalse(any(start < t.span.start < end and t.role not in ('literal', 'delimiter') for t in tokens))

    def test_unmatched_fence_recovery_to_eof_and_inline_is_not_fence(self):
        for n in (3, 4, 5):
            fence = '"' * n
            source = fence + '\n' + '"' * (n + 1) + '\n[Hidden]: value\n'
            result = analyze(source)
            self.assertIn('AG-LITERAL-UNCLOSED', [f.rule_id for f in result.diagnostics.findings])
            self.assertFalse(result.semantics.symbols)
            self.assertFalse(any(t.role == 'symbol' for t in highlight_tokens(result.document)))
        result = analyze('Task:\n- "text" and """""inline"""""\n=> Work\n')
        self.assertFalse(any(t.kind in ('literal_open', 'literal_close') for t in result.tree.tokens))
        self.assertTrue(any(t.kind == 'operation' for t in result.tree.tokens))

    def test_gui_buffer_edit_changes_fence_width_without_stale_shielding(self):
        from PySide6.QtGui import QTextCursor
        from PySide6.QtWidgets import QApplication
        from AgStudio.gui.app import DocumentTab
        source = '""""\n"""\n[Hidden]: value\n"""\n""""\n'
        app = QApplication.instance() or QApplication([])
        tab = DocumentTab('current', source, map_enabled=False)
        try:
            self.assertFalse(tab.analysis.semantics.symbols)
            cursor = tab.editor.textCursor()
            cursor.setPosition(3)
            cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            changed = source[:3] + source[4:]
            self.assertEqual(tab.source, changed)
            self.assertEqual(tab.analysis.as_record(), analyze(changed).as_record())
            self.assertTrue(any(s.name == 'Hidden' for s in tab.analysis.semantics.symbols))
            cursor.setPosition(3)
            cursor.insertText('"')
            self.assertEqual(tab.source, source)
            self.assertEqual(tab.analysis.as_record(), analyze(source).as_record())
            self.assertFalse(tab.analysis.semantics.symbols)
            tab.editor.undo()
            self.assertEqual(tab.source, changed)
            self.assertTrue(any(s.name == 'Hidden' for s in tab.analysis.semantics.symbols))
            tab.editor.redo()
            self.assertEqual(tab.source, source)
            self.assertFalse(tab.analysis.semantics.symbols)
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

    def test_outline_single_leaf_scope_and_correlation_exclusion(self):
        from PySide6.QtWidgets import QApplication, QTreeWidgetItem
        from AgStudio.gui.app import DocumentTab
        app = QApplication.instance() or QApplication([])
        source = '[A]: value\n\n[Literal]:\n"""""\n"""\n[A] 🌍\n"""\n"""""\n\nTask:\n- Use [A] and [Literal]\n'
        tab = DocumentTab('current', source)
        try:
            leaf = next(i for i in tab._outline_items.values() if i.text(0) == 'Literal block')
            self.assertEqual(leaf.childIndicatorPolicy(), QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
            tab.outline.setCurrentItem(leaf)
            self.assertEqual([r.cursor.blockNumber() for r in tab.editor._base_selections], [3, 4, 5, 6, 7])
            tab.outline.setCurrentItem(tab.outline.topLevelItem(0))
            self.assertEqual(tab.correlations.topLevelItemCount(), 2)
            self.assertFalse(any(i.text(0) == '[A] 🌍' for i in tab._outline_items.values()))
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()



RULE = 'AG-LITERAL-FENCE-WIDTH'


class LiteralFenceWidthLintTests(unittest.TestCase):
    def findings(self, source):
        return [f for f in analyze(source).diagnostics.findings if f.rule_id == RULE]

    def test_larger_inner_fences_report_outer_opener(self):
        for ending in ('\n', '\r\n', '\u2028'):
            for outer, inner in ((3, 4), (4, 5), (5, 12)):
                for closed in (False, True):
                    lines = [' \t' + '"' * outer, 'Below is some text:',
                             '\t' + '"' * inner + ' ', '[Hidden]:', '=> - Hidden', '"' * inner]
                    if closed:
                        lines.append('"' * outer)
                    source = ending.join(lines)
                    findings = self.findings(source)
                    self.assertEqual(len(findings), 1, source)
                    self.assertEqual(findings[0].severity, 'error')
                    self.assertEqual(findings[0].source_range.span.extract(source), '"' * outer)
                    self.assertFalse(any(f.rule_id == 'AG-OPERATION-LIST'
                                         for f in analyze(source).diagnostics.findings))

    def test_larger_outer_and_adjacent_supported_forms(self):
        for outer in (4, 5, 12):
            source = '\n'.join(['"' * outer, 'Below is some text:', '"""', 'Some text', '"""', '"' * outer])
            self.assertFalse(self.findings(source))
        for source in ('"""\nOne\n"""\n"""\nTwo\n"""',
                       '"""\n"""\n"""\n"""',
                       '"""\nOne\n"""\n""""\nTwo\n""""',
                       '"""\ninline """" text\n"""',
                       '"""\n\\""""\n"""'):
            self.assertFalse(self.findings(source), source)

    def test_equal_width_user_example_retains_unresolved_boundaries(self):
        source = '\n'.join(['"""', 'Below is some text:', '"""', 'Some text', '"""', '"""'])
        result = analyze(source)
        self.assertEqual([n.kind for n in result.tree.nodes],
                         ['literal_open', 'literal_content', 'literal_close',
                          'unclassified', 'literal_open', 'literal_close'])
        # Equal runs close under the current contract. No unapproved context
        # heuristic may turn these siblings into a claimed parent-child edge.
        self.assertFalse(self.findings(source))

    def test_admission_rejects_forged_evidence_and_unknown_version(self):
        source = '"""\n""""\n"""'
        result = analyze(source)
        finding = self.findings(source)[0]
        candidate = Candidate(RULE, finding.source_range.span, 0, 'untrusted', REGISTRY[RULE].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
        clean = analyze('"""\ntext\n"""')
        self.assertIn('unsupported_literal_width', admission(candidate, clean.document, clean.tree, clean.semantics))
        self.assertFalse(analyze(source, arcgrav_version='future').diagnostics.findings)

    def test_recursive_descendant_violations_mark_each_parent(self):
        # Grandchild 7 exceeds both root 5 and child 4: report both parents.
        source = '\n'.join('"' * n if isinstance(n, int) else n
                           for n in (5, 'Outer', 4, 'Child', 7, 'Deep', 7, 4, 5))
        findings = self.findings(source)
        self.assertEqual([f.source_range.span.extract(source) for f in findings], ['"' * 5, '"' * 4])
        self.assertEqual(findings[1].source_range.span.start, source.index('\n""""\n') + 1)
        # Both 5 < 6 and 6 < 8 fail; unrelated valid 3-fence sibling stays clean.
        source = '\n'.join('"' * n if isinstance(n, int) else n
                           for n in (5, 3, 'One', 3, 6, 8, 'Deep', 8, 6, 5))
        findings = self.findings(source)
        self.assertEqual([f.source_range.span.extract(source) for f in findings], ['"' * 5, '"' * 6])
        # Every identified level decreases: clean at all depths.
        source = '\n'.join('"' * n if isinstance(n, int) else n
                           for n in (7, 6, 5, 4, 3, 'Deep', 3, 4, 5, 6, 7))
        self.assertFalse(self.findings(source))

    def test_recursive_ranges_admission_and_active_syntax_shielding(self):
        for ending in ('\n', '\r\n', '\u2028'):
            source = ending.join(['"""""""', '  """"', '\t""""""', '[Hidden]:',
                                  '=> - Hidden', '""""""', '""""', '"""""""'])
            result = analyze(source)
            findings = self.findings(source)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].source_range.span.start, len('"""""""' + ending) + 2)
            self.assertEqual(findings[0].source_range.span.extract(source), '""""')
            self.assertEqual(findings, self.findings(source))
            self.assertFalse(result.semantics.symbols)
            self.assertEqual(tuple(f for f in result.diagnostics.findings
                                       if f.rule_id not in {'AG-DOCUMENT-END-SECTION', 'AG-DOCUMENT-START-SECTION'}), tuple(findings))
            candidate = Candidate(RULE, findings[0].source_range.span, 1, 'untrusted', REGISTRY[RULE].required_evidence)
            self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
            # A literal body's content cannot be relabeled as fence evidence.
            forged = replace(candidate, node_id=3, span=result.tree.nodes[3].span)
            self.assertIn('unsupported_literal_width', admission(forged, result.document, result.tree, result.semantics))
            active = Candidate('AG-LINE-ENDING', result.tree.nodes[3].span, 3, 'untrusted', ('editor_formatting',))
            self.assertIn('literal_source', admission(active, result.document, result.tree, result.semantics))

    def test_equal_width_siblings_are_not_inferred_as_nested(self):
        for source in ('"""\nOne\n"""\nProse\n"""\nTwo\n"""',
                       '"""\nOne\n"""\nProse\n"""\n"""',
                       '"""\nOne\n"""\nOther:\n"""\n"""',
                       '"""""\n"""\nOne\n"""\nProse\n"""\n"""\n"""""'):
            self.assertFalse(self.findings(source), source)

    def test_recursive_violation_reaches_cli_and_finding_projection(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        from AgStudio.shared.panel_projections import derive_findings
        source = '\r\n'.join(['"""""""', '  """"', '""""""', 'Deep', '""""""', '""""', '"""""""'])
        process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '-'],
                                 input=source.encode(), capture_output=True, timeout=15,
                                 cwd=Path(__file__).resolve().parents[3])
        self.assertEqual(process.returncode, 1)
        record = json.loads(process.stdout)['results'][0]
        record.pop('file')
        analysis = analyze(source)
        self.assertEqual(record, json.loads(json.dumps(analysis.as_record())))
        rows = [row for row in derive_findings(analysis).rows if row.finding.rule_id == RULE]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].texts[0], 'Error')
        self.assertEqual(rows[0].texts[3:], ('2', '3'))
        finding = rows[0].finding
        self.assertEqual(finding.severity, 'error')
        self.assertEqual(finding.source_range.span.extract(source), '""""')
        self.assertEqual((finding.source_range.end.line, finding.source_range.end.column), (2, 7))
