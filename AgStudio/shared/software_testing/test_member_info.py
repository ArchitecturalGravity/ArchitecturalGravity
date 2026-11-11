"""Distinct advisory Info findings for nested declaration and first invocation."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.members import MEMBER_INFO_MESSAGES
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission

SOURCE = ('[A]:\n- `parent`:\n  - `child`:\n    - `leaf`\n    - Use `leaf`\n'
          '  - Use `child`\n- Use `parent`\n- Read [A].parent.child.leaf\n\nTask: value\n')
DECL = 'AG-MEMBER-NESTED-DECLARATION'
INVOKE = 'AG-MEMBER-NESTED-INVOCATION'


class MemberInfoTests(unittest.TestCase):
    def infos(self, source):
        return [f for f in analyze(source).diagnostics.findings if f.rule_id in MEMBER_INFO_MESSAGES]

    def test_top_level_is_exempt_and_multiple_depths_are_informational(self):
        self.assertFalse(self.infos('[A]:\n- `item`\n- Use `item`\n- Read [A].item\n'))
        findings = self.infos(SOURCE)
        self.assertEqual([(f.rule_id, f.source_range.span.extract(SOURCE)) for f in findings],
                         [(DECL, '`child`'), (DECL, '`leaf`'), (INVOKE, '`leaf`'), (INVOKE, '`child`')])
        self.assertTrue(all(f.severity == 'information' for f in findings))
        self.assertEqual(analyze(SOURCE).diagnostics.findings[1:], tuple(findings))
        self.assertEqual(analyze(SOURCE).diagnostics.findings[0].rule_id, 'AG-DOCUMENT-START-SECTION')
        for f in findings:
            self.assertIn('near the surface', f.message)
            self.assertIn('LLM does not guarantee deterministic state tracking', f.message)
        self.assertIn('declaring', findings[0].message)
        self.assertIn('invoking', findings[2].message)

    def test_first_invocation_only_and_redeclarations_stay_declarations(self):
        source = SOURCE.replace('  - Use `child`\n', '  - `child`\n  - Use `child`\n  - Use `child`\n')
        self.assertEqual([f.rule_id for f in self.infos(source)], [DECL, DECL, INVOKE, DECL, INVOKE])
        result = analyze(source)
        self.assertEqual(result.semantics.members[-1].kind, 'access')
        self.assertFalse(any(f.source_range.span.extract(source).startswith('[A]') for f in self.infos(source)))

    def test_scope_isolation_and_orphans_do_not_invoke(self):
        source = ('[A]:\n- `parent`:\n  - `child`\n- Use `child`\n- Read [A].parent.child\n'
                  '\n[B]:\n- `parent`:\n  - Use `child`\n')
        self.assertEqual([f.rule_id for f in self.infos(source)], [DECL, INVOKE])
        self.assertTrue(any(f.rule_id == 'AG-MEMBER-ORPHAN' for f in analyze(source).diagnostics.findings))
        invoked = [m for m in analyze(source).semantics.members if m.kind == 'invocation']
        self.assertEqual([m.path for m in invoked], [('parent', 'child'), ('parent',)])
        self.assertTrue(all(m.owner.extract(source) == '[A]' for m in invoked))
        orphan = '[A]:\n- Text:\n  - `child`\n  - Use `child`\n'
        self.assertFalse(self.infos(orphan))

    def test_exact_ranges_shielding_versions_and_admission(self):
        for ending in ('\n', '\r\n', '\u2028'):
            source = SOURCE.replace('\n', ending)
            result = analyze(source)
            for finding in self.infos(source):
                span = finding.source_range.span
                node = next(n for n in result.tree.nodes if n.span.start <= span.start < n.span.end)
                candidate = Candidate(finding.rule_id, span, node.id, 'untrusted', REGISTRY[finding.rule_id].required_evidence)
                self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
                self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
                other = DECL if finding.rule_id == INVOKE else INVOKE
                self.assertIn('unsupported_member_evidence', admission(replace(candidate, rule_id=other), result.document, result.tree, result.semantics))
            self.assertEqual(result.as_record(), analyze(source).as_record())
        self.assertFalse(self.infos('"""\n' + SOURCE + '"""\n'))
        quoted = '[A]:\n- `parent`:\n  - "`child`"\n  - Use "`child`"\n  - `unfinished\n'
        self.assertFalse(self.infos(quoted))
        self.assertFalse(analyze(SOURCE, arcgrav_version='future').diagnostics.findings)

    def test_cli_and_finding_list_show_info_and_navigate_exact_ranges(self):
        root = Path(__file__).resolve().parents[3]
        for threshold in ('error', 'warning'):
            process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '--fail-on', threshold, '-'],
                                     input=SOURCE.encode(), cwd=root, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue(all(f['severity'] == 'information' for f in json.loads(process.stdout)['results'][0]['findings']))
        from PySide6.QtWidgets import QApplication
        from AgStudio.gui.app import DocumentTab
        app = QApplication.instance() or QApplication([])
        tab = DocumentTab('current', SOURCE)
        try:
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), 5)
            for i, finding in enumerate(self.infos(SOURCE)):
                row = tab.diagnostic_list.topLevelItem(i + 1)
                self.assertEqual(row.text(0), 'Info')
                self.assertFalse(row.icon(0).isNull())
                self.assertEqual(row.text(1), finding.rule_id)
                tab._navigate_finding(row)
                self.assertEqual(tab.editor.textCursor().selectedText(), finding.source_range.span.extract(SOURCE))
            self.assertEqual(set(tab.editor.finding_severities.values()), {'information'})
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()
