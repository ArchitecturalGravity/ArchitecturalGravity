"""Owner-separated local member definitions, exposure and nested access."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.members import MEMBER_MESSAGES
from AgStudio.shared.lint.rules import Candidate, REGISTRY, admission

ROOT = Path(__file__).resolve().parents[3]
NESTED = ('[Order]:\n- `customer`:\n  - `address`:\n    - `city`\n'
          '    - Use `city`\n  - Use `address`\n- Use `customer`\n\n'
          'Task:\n- Use [Order].customer.address.city\n')


class MemberLintTests(unittest.TestCase):
    def findings(self, source):
        return [f for f in analyze(source).diagnostics.findings if f.rule_id in MEMBER_MESSAGES]

    def ids(self, source):
        return [f.rule_id for f in self.findings(source)]

    def test_definition_invocation_and_access_are_distinct(self):
        source = '[A]:\n- `item`\n- Read [A].item\n- Use `item`\n- Read [A].item\n'
        result = analyze(source)
        self.assertEqual([m.kind for m in result.semantics.members],
                         ['definition', 'invocation', 'access', 'reference', 'access'])
        self.assertFalse(self.findings(source))
        self.assertFalse(self.findings('[A]:\n- `item`\n- Read [A].item\n'))
        self.assertEqual(self.ids('[A]:\n- `item`\n'), ['AG-MEMBER-ORPHAN'])

    def test_inline_backticks_correlate_without_dot_notation(self):
        for declaration in ('- `whatever`', '  - `whatever`: string'):
            for ending in ('\n', '\r\n', '\u2028'):
                with self.subTest(declaration=declaration, ending=ending):
                    source = ending.join((
                        '[Something]:', declaration, '', 'Task:',
                        '- Check that [Something] contains `whatever`',
                        '- Confirm `whatever` exists', '',
                    ))
                    result = analyze(source)
                    self.assertEqual(
                        [(m.kind, m.path, m.owner.extract(source)) for m in result.semantics.members],
                        [('definition', ('whatever',), '[Something]'),
                         ('invocation', ('whatever',), '[Something]'),
                         ('reference', ('whatever',), '[Something]')])
                    self.assertFalse(self.findings(source))

    def test_inline_and_dot_member_usage_independently_satisfy_unused_check(self):
        cases = (
            ('inline', '- Check that [Something] contains `whatever`',
             ('definition', 'invocation'), '`whatever`'),
            ('dot', '- Read [Something].whatever',
             ('definition', 'invocation', 'access'), '[Something].whatever'),
        )
        for declaration in ('- `whatever`', '  - `whatever`: string'):
            for syntax, use, kinds, expected_span in cases:
                with self.subTest(declaration=declaration, syntax=syntax):
                    source = '[Something]:\n' + declaration + '\n\nTask:\n' + use + '\n'
                    members = analyze(source).semantics.members
                    self.assertEqual(tuple(m.kind for m in members), kinds)
                    original = members[0]
                    self.assertEqual(
                        tuple((m.owner, m.path, m.definition) for m in members[1:]),
                        ((original.owner, original.path, original.span),) * (len(members) - 1))
                    self.assertEqual(members[-1].span.extract(source), expected_span)
                    self.assertFalse(self.findings(source))

    def test_inline_and_dot_usage_in_both_orders_share_one_member_identity(self):
        inline = '- Check that [Something] contains `whatever`'
        dotted = '- Read [Something].whatever'
        for uses, kinds in (
            ((inline, dotted), ('definition', 'invocation', 'access')),
            ((dotted, inline), ('definition', 'invocation', 'access', 'reference')),
        ):
            with self.subTest(first=uses[0]):
                source = '[Something]:\n- `whatever`: string\n\nTask:\n' + '\n'.join(uses) + '\n'
                members = analyze(source).semantics.members
                self.assertEqual(tuple(m.kind for m in members), kinds)
                original = members[0]
                self.assertTrue(all(
                    (m.owner, m.path, m.definition) == (original.owner, original.path, original.span)
                    for m in members[1:]))
                self.assertEqual(
                    [m.span.extract(source) for m in members
                     if m.kind in ('invocation', 'reference')
                     and m.span.extract(source).startswith('`')],
                    ['`whatever`'])
                self.assertEqual(
                    [m.span.extract(source) for m in members if m.kind == 'access'],
                    ['[Something].whatever'])
                self.assertFalse(self.findings(source))


    def test_inline_symbols_do_not_qualify_bare_member_uses(self):
        prefix = ('[A]:\n- `item`\n\n[B]:\n- `item`\n\nTask:\n')
        for expression in ('- Check that [A] contains `item`',
                           '- Check that [B] contains `item`',
                           '- Check `item`'):
            with self.subTest(expression=expression):
                source = prefix + expression + '\n'
                result = analyze(source)
                self.assertEqual([m.kind for m in result.semantics.members],
                                 ['definition', 'definition', 'ambiguous'])
                self.assertEqual(self.ids(source).count('AG-MEMBER-ORPHAN'), 2)
                self.assertEqual(self.ids(source).count('AG-MEMBER-DUPLICATE'), 1)
                self.assertIn('AG-MEMBER-AMBIGUOUS', self.ids(source))
                self.assertIsNone(result.semantics.members[-1].definition)

        # The dotted path, unlike the bare reference, selects one exact owner.
        source = prefix + '- Read [A].item\n'
        self.assertEqual(analyze(source).semantics.members[-1].kind, 'access')
        self.assertEqual(self.ids(source).count('AG-MEMBER-ORPHAN'), 1)
        self.assertNotIn('AG-MEMBER-NOT-EXPOSED', self.ids(source))

    def test_cross_section_inline_correlates_only_prior_exact_name(self):
        source = ('[A]:\n- `value`\n\nTask:\n'
                  '- Read `value`\n- Read `Value`\n')
        members = analyze(source).semantics.members
        self.assertEqual([m.kind for m in members],
                         ['definition', 'invocation', 'unresolved_reference'])
        self.assertNotIn('AG-MEMBER-ORPHAN', self.ids(source))
        self.assertEqual([(f.rule_id, f.source_range.span.extract(source))
                          for f in self.findings(source)],
                         [('AG-MEMBER-UNDEFINED', chr(96) + 'Value' + chr(96))])
        future = ('Task:\n- Read `late`\n\n[A]:\n- `late`\n')
        self.assertEqual([m.kind for m in analyze(future).semantics.members], ['definition'])
        self.assertIn('AG-MEMBER-ORPHAN', self.ids(future))

    def test_orphan_and_undefined_mean_opposite_facts(self):
        source = ('[Something]:\n- `unused`: string\n- `used`: string\n\n'
                  'Task:\n- Check [Something] contains `used`\n'
                  '- Check [Something] contains `missing`\n')
        result = analyze(source)
        member_findings = [finding for finding in result.diagnostics.findings
                           if finding.rule_id in ('AG-MEMBER-ORPHAN',
                                                  'AG-MEMBER-UNDEFINED')]
        self.assertEqual(
            [(finding.rule_id, finding.severity, finding.source_range.span.extract(source))
             for finding in member_findings],
            [('AG-MEMBER-ORPHAN', 'warning', '`unused`'),
             ('AG-MEMBER-UNDEFINED', 'warning', '`missing`')])
        self.assertEqual(member_findings[0].message,
                         'This backticked member is defined but never used.')
        self.assertEqual(member_findings[1].message,
                         'This backticked member is referenced but has no definition.')
        self.assertNotIn('AG-MEMBER-UNUSED', REGISTRY)
        self.assertTrue(all(f.message and f.evidence for f in member_findings))
        for finding in member_findings:
            node = next(n for n in result.tree.nodes
                        if n.span.start <= finding.source_range.span.start < n.span.end)
            candidate = Candidate(finding.rule_id, finding.source_range.span, node.id,
                                  'forged', REGISTRY[finding.rule_id].required_evidence)
            self.assertEqual(admission(candidate, result.document, result.tree,
                                       result.semantics), ())

    def test_never_defined_does_not_misdiagnose_a_future_definition(self):
        for ending in ('\n', '\r\n', '\u2028'):
            source = ending.join(('[A]:', '- Use `future`', '- `future`: string', '',
                                  'Task:', '- Read [A].future', ''))
            with self.subTest(ending=ending):
                result = analyze(source)
                self.assertEqual([m.kind for m in result.semantics.members],
                                 ['unresolved_reference', 'definition', 'invocation', 'access'])
                self.assertNotIn('AG-MEMBER-UNDEFINED', self.ids(source))
                self.assertNotIn('AG-MEMBER-ORPHAN', self.ids(source))


    def test_undefined_is_global_but_dotted_exposure_is_owner_specific(self):
        source = ('[A]:\n- `field`: string\n\n[B]:\n- `other`: string\n\n'
                  'Task:\n- Check [B] contains `field`\n- Read [B].field\n')
        result = analyze(source)
        findings = self.findings(source)
        self.assertEqual([(f.rule_id, f.source_range.span.extract(source)) for f in findings],
                         [('AG-MEMBER-ORPHAN', '`other`'),
                          ('AG-MEMBER-NOT-EXPOSED', 'field')])
        self.assertEqual(result.semantics.members[-2].kind, 'invocation')
        self.assertEqual(result.semantics.members[-2].owner.extract(source), '[A]')
        for value in ('"`missing`"', '`incomplete', '``missing``'):
            with self.subTest(protected=value):
                self.assertNotIn('AG-MEMBER-UNDEFINED',
                                 self.ids('[A]:\n- ' + value + '\n'))
        # A dash-prefixed triple quote is not a literal opener; its following
        # standalone backtick is active and can be undefined.
        self.assertIn('AG-MEMBER-UNDEFINED',
                      self.ids('[A]:\n- """\n`missing`\n"""\n'))
        self.assertNotIn('AG-MEMBER-UNDEFINED',
                         self.ids('[A]:\n"""\n`missing`\n"""\n'))

    def test_forward_references_and_undefined_member_uses(self):
        source = '[A]:\n- Set `item` to 1\n- `item`\n'
        self.assertEqual(self.ids(source), ['AG-MEMBER-ORPHAN'])
        self.assertEqual(self.ids('[A]:\n- Text about `item`\n'), ['AG-MEMBER-UNDEFINED'])
        self.assertEqual(self.ids('[A]:\n1. `item`\n'), ['AG-MEMBER-ORPHAN'])
        self.assertFalse(self.findings('[A]:\n- `item` then use `item`\n'))
        source = '[A]:\n- Read [A].item\n- `item`\n- Use `item`\n'
        self.assertEqual(self.ids(source), ['AG-MEMBER-NOT-EXPOSED'])

    def test_numbered_category_members_are_definitions_and_correlate(self):
        names = ('conflict', 'missing', 'instruction-content', 'relation')
        for ending in ('\n', '\r\n', '\u2028'):
            for indent in ('', '  '):
                with self.subTest(ending=ending, indent=indent):
                    lines = ['[CategoryOrder]:'] + [
                        f'{indent}{i}. `{name}`' for i, name in enumerate(names, 1)]
                    declarations = ending.join(lines) + ending
                    result = analyze(declarations)
                    self.assertEqual([m.kind for m in result.semantics.members], ['definition'] * 4)
                    self.assertEqual(self.ids(declarations), ['AG-MEMBER-ORPHAN'] * 4)
                    source = ending.join(lines + ['', 'Task:'] + [
                        f'{i}. Read `{name}`' for i, name in enumerate(names, 1)]) + ending
                    members = analyze(source).semantics.members
                    self.assertEqual([m.kind for m in members], ['definition'] * 4 + ['invocation'] * 4)
                    for declaration, use, name in zip(members[:4], members[4:], names):
                        self.assertEqual(declaration.path, (name,))
                        self.assertEqual(declaration.span.extract(source), f'`{name}`')
                        self.assertEqual(use.definition, declaration.span)
                        self.assertEqual(use.owner.extract(source), '[CategoryOrder]')
                    self.assertFalse(self.findings(source))

    def test_numbered_values_and_redefinitions_match_dash_members(self):
        for marker in ('-', '1.', '10.'):
            with self.subTest(marker=marker):
                source = ('[A]:\n' + marker + ' `seed`: 0\n' + marker + ' `value`: `seed`\n'
                          + marker + ' `value`: string\n'
                          '2. Read [A].value\n3. Use `value`\n')
                members = analyze(source).semantics.members
                self.assertEqual([m.kind for m in members],
                                 ['definition', 'definition', 'invocation', 'redefinition',
                                  'invocation', 'access', 'reference'])
                self.assertEqual(members[2].definition, members[0].span)
                self.assertEqual(members[3].definition, members[1].span)
                self.assertTrue(all(m.definition == members[1].span for m in members[4:]))
                self.assertFalse(self.findings(source))

    def test_numbered_nested_members_and_mixed_markers_preserve_paths(self):
        for parent in ('-', '1.'):
            for child in ('-', '2.'):
                with self.subTest(parent=parent, child=child):
                    source = (f'[A]:\n{parent} `parent`:\n  {child} `child`:\n'
                              '    3. `leaf`: string\n\nTask:\n1. Read [A].parent.child.leaf\n')
                    result = analyze(source)
                    self.assertEqual([(m.kind, m.path) for m in result.semantics.members], [
                        ('definition', ('parent',)), ('definition', ('parent', 'child')),
                        ('definition', ('parent', 'child', 'leaf')),
                        ('invocation', ('parent',)), ('invocation', ('parent', 'child')),
                        ('invocation', ('parent', 'child', 'leaf')),
                        ('access', ('parent', 'child', 'leaf'))])
                    self.assertFalse(self.findings(source))
                    self.assertEqual([f.rule_id for f in result.diagnostics.findings
                                      if f.rule_id.startswith('AG-MEMBER-NESTED')],
                                     ['AG-MEMBER-NESTED-DECLARATION'] * 2
                                     + ['AG-MEMBER-NESTED-INVOCATION'] * 2)

    def test_numbered_procedural_operands_remain_uses_not_declarations(self):
        for marker in ('-', '1.'):
            with self.subTest(marker=marker):
                source = ('[A]:\n1. `item`\n\n[B]:\n1. Inspect:\n'
                          f'  {marker} `item`\n  2. Use `item`\n'
                          '2. Read [B].item\n\nTask:\n1. `item`\n2. Use `missing`\n')
                members = analyze(source).semantics.members
                self.assertEqual([m.kind for m in members],
                                 ['definition', 'invocation', 'reference', 'unexposed_access',
                                  'reference', 'unresolved_reference'])
                self.assertEqual([members[i].owner.extract(source) for i in (0, 1, 2, 4)], ['[A]'] * 4)
                self.assertEqual(self.ids(source), ['AG-MEMBER-NOT-EXPOSED', 'AG-MEMBER-UNDEFINED'])
        for item in ('`item`:', '`item`: value', '`item` value', '`item`\n    1. child'):
            source = '[A]:\n1. `item`\n\n[B]:\n1. Inspect:\n  1. ' + item + '\n'
            self.assertEqual([m.kind for m in analyze(source).semantics.members],
                             ['definition', 'unsupported_declaration'])

    def test_numbered_members_preserve_shielding_and_uncertain_ownership(self):
        for body in ('[A]:\n1. "`item`"\n', '[A]:\n1. `unfinished\n',
                     '[A]:\n1. ``item``\n', '[A]:\n1. `two words`\n',
                     '[A]\n  1. `item`\n', '[A]:\n   1. `item`\n',
                     '[A]:\n"""\n1. `item`\n"""\n'):
            with self.subTest(body=body):
                self.assertFalse(analyze(body).semantics.members)
        source = '[A]:\n1. `item`\n'
        result = analyze(source)
        finding = self.findings(source)[0]
        candidate = Candidate(finding.rule_id, finding.source_range.span, 1, 'untrusted',
                              REGISTRY[finding.rule_id].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        self.assertFalse(analyze(source, arcgrav_version='future').diagnostics.findings)

    def test_repeated_definitions_are_not_invocations(self):
        result = analyze('[A]:\n- `item`\n- `item`\n')
        self.assertEqual([m.kind for m in result.semantics.members], ['definition', 'redefinition'])
        self.assertEqual(self.ids(result.document.source), ['AG-MEMBER-ORPHAN'])
        repeated = analyze('[A]:\n- `item`\n\n[A]:\n- Use `item`\n- Read [A].item\n')
        self.assertIn('AG-SYMBOL-DUPLICATE-INSTANTIATION',
                      [finding.rule_id for finding in repeated.diagnostics.findings])
        self.assertEqual([symbol.kind for symbol in repeated.semantics.symbols],
                         ['anchor', 'duplicate_anchor', 'reference'])

    def test_duplicate_names_warn_but_do_not_share_identity(self):
        source = ('[A]:\n- `item`\n- Use `item`\n\n[B]:\n- `item`\n'
                  '- Read [B].item\n- Read [A].item\n')
        self.assertEqual(self.ids(source), ['AG-MEMBER-DUPLICATE'])
        members = analyze(source).semantics.members
        self.assertNotEqual(members[0].owner, members[2].owner)
        self.assertEqual(members[-1].kind, 'access')
        self.assertEqual(self.ids('[A]:\n- `Item`\n- Use `item`\n- Read [A].Item\n'),
                         ['AG-MEMBER-UNDEFINED'])

    def test_nested_success_and_dot_invokes_each_defined_segment(self):
        self.assertFalse(self.findings(NESTED))
        self.assertEqual(analyze(NESTED).semantics.members[-1].path, ('customer', 'address', 'city'))
        source = NESTED
        for line in ('- Use `customer`\n', '  - Use `address`\n', '    - Use `city`\n'):
            source = source.replace(line, '')
            self.assertFalse(self.findings(source))
        self.assertEqual([m.path for m in analyze(source).semantics.members if m.kind == 'invocation'],
                         [('customer',), ('customer', 'address'), ('customer', 'address', 'city')])

    def test_missing_levels_wrong_parents_and_source_order(self):
        for path, missing in [('absent.address.city', 'absent'), ('customer.absent.city', 'absent'),
                              ('customer.address.absent', 'absent'), ('customer.city', 'city')]:
            source = NESTED.replace('customer.address.city\n', path + '\n')
            self.assertEqual([f.source_range.span.extract(source) for f in self.findings(source)], [missing])
        source = NESTED.replace('    - `city`\n', '    - Use `city`\n    - `city`\n', 1)
        self.assertFalse(self.findings(source))  # Forward use is not "never defined".
        source = NESTED.replace('- Use `customer`\n', '- Read [Order].customer.address.city\n- Use `customer`\n')
        self.assertFalse(self.findings(source))


    def test_same_spelling_in_sibling_scopes_stays_separate_for_dots(self):
        source = ('[A]:\n- `left`:\n  - `item`\n  - Use `item`\n- `right`:\n  - `item`\n'
                  '- Use `left` and `right`\n- Read [A].right.item\n- Read [A].left.item\n')
        self.assertEqual(self.ids(source), ['AG-MEMBER-DUPLICATE'])
        self.assertEqual(analyze(source).semantics.members[-1].kind, 'access')
        ambiguous = source.replace('- Use `left` and `right`\n',
                                   '- Use `left` and `right` and `item`\n')
        self.assertIn('AG-MEMBER-AMBIGUOUS', self.ids(ambiguous))
        source = '[A]:\n- Text:\n  - `item`\n- Read [A].item\n'
        self.assertEqual(self.ids(source), ['AG-MEMBER-UNDEFINED', 'AG-MEMBER-NOT-EXPOSED'])

    def test_no_bare_label_schema_or_external_resource_inference(self):
        source = '[A]:\n- item: value\n- https://example.invalid/schema\n- Read [A].item\n'
        with patch('builtins.open', side_effect=AssertionError('external read')), \
             patch('socket.create_connection', side_effect=AssertionError('external network')):
            result = analyze(source)
        self.assertEqual([f.rule_id for f in result.diagnostics.findings if f.rule_id in MEMBER_MESSAGES],
                         ['AG-MEMBER-NOT-EXPOSED'])
        self.assertEqual([m.kind for m in result.semantics.members], ['unexposed_access'])

    def test_opaque_uncertain_incomplete_and_outside_owner_forms(self):
        for text in ('"Use `item` and [A].item"', '`unfinished', '``item``', '`two words`',
                     '`esca\\ped`', '[A].item.', '[A].item..child', '[A].`item`'):
            source = '[A]:\n- ' + text + '\n'
            self.assertFalse(self.findings(source), source)
        source = '[A]:\n"""\n- `item`\n- Use `item`\n- [A].item\n"""\n'
        self.assertFalse(self.findings(source))
        self.assertFalse(analyze(source).semantics.members)
        self.assertFalse(self.findings('Task:\n- Use `item`\n'))
        self.assertFalse(self.findings('[Uncertain-Owner]:\n- `item`\n'))
        self.assertFalse(self.findings('[A]\n  - `item`\n'))
        self.assertFalse(analyze('[A]:\n- `item`\n', arcgrav_version='future').diagnostics.findings)

    def test_independent_admission_does_not_trust_member_records(self):
        source = '[A]:\n- `item`\n'
        result = analyze(source)
        finding = self.findings(source)[0]
        candidate = Candidate(finding.rule_id, finding.source_range.span, 1, 'untrusted',
                              REGISTRY[finding.rule_id].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
        clean = analyze(source + '- Use `item`\n')
        forged_semantics = replace(clean.semantics, members=result.semantics.members)
        self.assertIn('unsupported_member_evidence', admission(candidate, clean.document, clean.tree, forged_semantics))
        self.assertIn('literal_source', admission(replace(candidate, rule_id='AG-LINE-ENDING'),
                      result.document, result.tree, result.semantics))

    def test_cli_and_gui_warning_propagation(self):
        source = '[A]:\r\n- 🌍 Read [A].item\r\n\r\nTask: value\r\n'
        result = analyze(source)
        self.assertEqual(result.as_record(), analyze(source).as_record())
        process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '-'], input=source.encode(),
                                 cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0)  # Advisory warning, not an error.
        record = json.loads(process.stdout)['results'][0]
        record.pop('file')
        self.assertEqual(record, json.loads(json.dumps(result.as_record())))
        from PySide6.QtWidgets import QApplication, QTabWidget
        from AgStudio.gui.app import DocumentTab
        app = QApplication.instance() or QApplication([])
        tab = DocumentTab('current', source)
        try:
            self.assertFalse(any(widget.tabText(i) == 'External Resources'
                                 for widget in tab.findChildren(QTabWidget)
                                 for i in range(widget.count())))
            self.assertEqual(tab.analysis.as_record(), result.as_record())
            self.assertEqual(tab.diagnostic_list.topLevelItemCount(), len(result.diagnostics.findings))
            from PySide6.QtCore import Qt
            for i in range(tab.diagnostic_list.topLevelItemCount()):
                finding = tab.diagnostic_list.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
                if finding.rule_id in MEMBER_MESSAGES:
                    self.assertEqual(finding.severity, 'warning')
                    tab._navigate_finding(tab.diagnostic_list.topLevelItem(i))
                    cursor = tab.editor.textCursor()
                    self.assertEqual(cursor.selectedText(), 'item')
                    self.assertEqual(cursor.blockNumber(), 1)
                    self.assertEqual(cursor.selectionStart() - cursor.block().position(), 14)
                    self.assertEqual(cursor.selectionEnd() - cursor.block().position(), 18)
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

    def test_nested_definition_requires_immediate_declared_parent(self):
        source = ('[A]:\n- `customer`:\n  - Prose:\n    - `city`\n'
                  '  - Use `city`\n- Use `customer`\n- Read [A].customer.city\n')
        self.assertEqual(self.ids(source), ['AG-MEMBER-UNDEFINED', 'AG-MEMBER-UNDEFINED',
                                             'AG-MEMBER-NOT-EXPOSED'])

    def test_bare_label_compatibility_and_corrected_backticked_member(self):
        old = '[Document]:\n- Origin: https://example.invalid/notes\n- Focus: notes\n\nTask:\n- Read [Document].Focus\n'
        findings = self.findings(old)
        self.assertEqual([f.rule_id for f in findings], ['AG-MEMBER-NOT-EXPOSED'])
        self.assertEqual(findings[0].source_range.span.extract(old), 'Focus')
        corrected = old.replace('- Focus: notes', '- `Focus`: notes\n- Use `Focus`')
        self.assertFalse(self.findings(corrected))

    def test_user_child_access_invokes_defined_path_with_editor_line_endings(self):
        from AgStudio.shared.lint.members import MEMBER_INFO_MESSAGES
        for ending in ('\n', '\r\n', '\u2028'):
            source = ending.join(['[Parent]:', '- `child1`:', '  - `child2`: "some value"',
                                  '', 'Task:', '- See [Parent].child1.child2'])
            result = analyze(source)
            self.assertFalse(self.findings(source))
            self.assertEqual([m.path for m in result.semantics.members if m.kind == 'invocation'],
                             [('child1',), ('child1', 'child2')])
            infos = [f for f in result.diagnostics.findings if f.rule_id in MEMBER_INFO_MESSAGES]
            self.assertEqual([(f.rule_id, f.source_range.span.extract(source)) for f in infos],
                             [('AG-MEMBER-NESTED-DECLARATION', '`child2`'),
                              ('AG-MEMBER-NESTED-INVOCATION', 'child2')])
            self.assertEqual(len(result.diagnostics.findings), 4)
            quotes = [f for f in result.diagnostics.findings if f.rule_id == 'AG-QUOTED-ELEMENT-NO-MATCH']
            self.assertEqual([(f.severity, f.source_range.span.extract(source)) for f in quotes],
                             [('warning', '"some value"')])
            self.assertEqual(infos[-1].source_range.span.start, source.rindex('child2'))
            again = source + ending + '- See [Parent].child1.child2'
            self.assertEqual(len([f for f in analyze(again).diagnostics.findings
                                 if f.rule_id == 'AG-MEMBER-NESTED-INVOCATION']), 1)

    def test_partial_path_invokes_defined_prefix_only_and_future_child_still_warns(self):
        source = ('[Parent]:\n- `child1`:\n  - `child2`: "some value"\n\n'
                  'Task:\n- See [Parent].child1.missing.child2\n')
        result = analyze(source)
        self.assertEqual([m.path for m in result.semantics.members if m.kind == 'invocation'], [('child1',)])
        self.assertEqual([(f.rule_id, f.source_range.span.extract(source)) for f in self.findings(source)],
                         [('AG-MEMBER-ORPHAN', '`child2`'), ('AG-MEMBER-NOT-EXPOSED', 'missing')])
        future = ('[Parent]:\n- `child1`:\n  - See [Parent].child1.child2\n'
                  '  - `child2`: "some value"\n\nTask:\n- See [Parent].child1.child2\n')
        self.assertEqual(self.ids(future), ['AG-MEMBER-NOT-EXPOSED'])
        result = analyze(future)
        self.assertEqual([m.path for m in result.semantics.members if m.kind == 'invocation'],
                         [('child1',), ('child1', 'child2')])

    def test_dot_first_invocation_info_admission_and_source_ranges(self):
        source = '[A]:\r\n- `parent`:\r\n  - `child`\r\n\r\nTask:\r\n- 🌍 See [A].parent.child\r\n'
        result = analyze(source)
        info = next(f for f in result.diagnostics.findings if f.rule_id == 'AG-MEMBER-NESTED-INVOCATION')
        candidate = Candidate(info.rule_id, info.source_range.span, 5, 'untrusted', REGISTRY[info.rule_id].required_evidence)
        self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
        repeated = source + '- See [A].parent.child\r\n'
        clean = analyze(repeated)
        last = clean.tree.nodes[-1]
        from AgStudio.shared.recognition import SourceSpan
        start = repeated.rindex('child')
        self.assertIn('unsupported_member_evidence', admission(replace(candidate, node_id=last.id, span=SourceSpan(start, start+5)),
                      clean.document, clean.tree, clean.semantics))
        self.assertEqual(info.severity, 'information')
        self.assertEqual(info.source_range.span.extract(source), 'child')
        self.assertEqual((info.source_range.start.line, info.source_range.start.column), (6, 20))
        self.assertEqual((info.source_range.end.line, info.source_range.end.column), (6, 25))

    def test_ingestion_operands_preserve_declaration_identity(self):
        source = ('[IngestionResult]:\n- `specification`\n- `implementation`\n'
                  '- `environment`\n- `evidence`\n- `constraints`\n\n'
                  '[Process]:\n1. Inspect:\n  - `specification`\n  - `implementation`\n'
                  '  - `environment`\n  - `evidence`\n  - `constraints`\n'
                  '4. Determine whether the inputs agree\n\nTask:\n- Run [Process]\n')
        names = {'specification', 'implementation', 'environment', 'evidence', 'constraints'}
        for text in (source.split('4. Determine whether', 1)[0], source):
            result = analyze(text)
            declarations = {m.path: m for m in result.semantics.members
                            if m.kind == 'definition' and m.path[0] in names}
            operands = [m for m in result.semantics.members if m.node in range(9, 14)]
            self.assertEqual({m.path[0] for m in operands}, names)
            for m in operands:
                self.assertEqual(m.kind, 'invocation')
                self.assertEqual(m.owner.extract(text), '[IngestionResult]')
                self.assertEqual(m.definition, declarations[m.path].span)
            self.assertFalse([f for f in self.findings(text)
                              if f.source_range.span.extract(text).strip('`') in names])
        explicit = source.replace('  - `specification`', '  - [IngestionResult].specification', 1)
        self.assertFalse([f for f in self.findings(explicit)
                          if f.source_range.span.extract(explicit).strip('`') == 'specification'])

    def test_operand_ambiguity_warns_without_invoking_candidates(self):
        source = '[A]:\n- `item`\n\n[B]:\n- `item`\n\n[C]:\n1. Inspect:\n  - `item`\n\nTask: value\n'
        result = analyze(source)
        self.assertEqual([m.kind for m in result.semantics.members],
                         ['definition', 'definition', 'ambiguous'])
        self.assertEqual(self.ids(source).count('AG-MEMBER-ORPHAN'), 2)
        warning = next(f for f in self.findings(source) if f.rule_id == 'AG-MEMBER-AMBIGUOUS')
        self.assertEqual((warning.severity), ('warning'))
        self.assertEqual(warning.message,
                         'This backticked name matches multiple prior definitions. Use dotted symbol access to identify the intended member.')
        self.assertEqual(warning.source_range.span.extract(source), '`item`')
        self.assertIsNone(result.semantics.members[-1].definition)
        process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '-'],
                                 input=source.encode(), cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 1, process.stderr)
        self.assertIn('AG-SYMBOL-UNUSED', [f.rule_id for f in result.diagnostics.findings])


    def test_bare_operands_never_prefer_a_lexical_owner(self):
        prefix = '[A]:\n- `item`\n\n[B]:\n- `item`\n\n[C]:\n'
        for body, extra_orphan in (
                ('- `item`\n1. Inspect:\n  - `item`\n', 0),
                ('- `parent`:\n  - `item`\n  1. Inspect:\n    - `item`\n', 1)):
            source = prefix + body
            result = analyze(source)
            use = result.semantics.members[-1]
            self.assertEqual(use.kind, 'ambiguous')
            self.assertIsNone(use.definition)
            self.assertEqual(self.ids(source).count('AG-MEMBER-DUPLICATE'), 2)
            self.assertEqual(self.ids(source).count('AG-MEMBER-ORPHAN'), 3 + extra_orphan)
            self.assertIn('AG-MEMBER-AMBIGUOUS', self.ids(source))

    def test_operands_obey_order_case_and_missing_names(self):
        source = ('[A]:\n- `Item`\n\n[B]:\n1. Inspect:\n  - `item`\n  - `future`\n'
                  '  - `missing`\n\n[C]:\n- `future`\n')
        members = analyze(source).semantics.members
        self.assertEqual([m.kind for m in members],
                         ['definition', 'unresolved_reference', 'unresolved_reference',
                           'unresolved_reference', 'definition'])
        # A later conflicting declaration cannot retroactively make a use ambiguous.
        source = '[A]:\n- `item`\n\n[B]:\n1. Inspect:\n  - `item`\n\n[C]:\n- `item`\n'
        self.assertEqual([m.kind for m in analyze(source).semantics.members],
                         ['definition', 'invocation', 'definition'])


    def test_bare_operands_can_correlate_to_unique_nested_names(self):
        source = ('[A]:\n- `left`:\n  - `item`\n- `right`:\n  1. Inspect:\n    - `item`\n'
                  '\n[B]:\n1. Inspect:\n  - `item`\n')
        result = analyze(source)
        self.assertEqual([m.kind for m in result.semantics.members][-2:],
                         ['invocation', 'reference'])
        self.assertEqual([m.path for m in result.semantics.members][-2:],
                         [('left', 'item'), ('left', 'item')])
        source += '\n[C]:\n- `item`\n\n[D]:\n1. Inspect:\n  - `item`\n'
        use = analyze(source).semantics.members[-1]
        self.assertEqual(use.kind, 'ambiguous')
        self.assertIn('AG-MEMBER-AMBIGUOUS', self.ids(source))

    def test_bare_schemas_redeclarations_and_operand_references(self):
        source = '[A]:\n- `item`\n- `item`\n\n[B]:\n1. Inspect:\n  - `item`\n  - `item`\n'
        self.assertEqual([m.kind for m in analyze(source).semantics.members],
                         ['definition', 'redefinition', 'invocation', 'reference'])
        self.assertFalse(self.findings(source))
        # Bare declarations directly below another owner remain separate identities.
        self.assertEqual([m.kind for m in analyze('[A]:\n- `item`\n\n[B]:\n- `item`\n').semantics.members],
                         ['definition', 'definition'])
        self.assertEqual([m.kind for m in analyze('[A]:\n- `parent`:\n  - `item`\n  - `item`\n').semantics.members],
                         ['definition', 'definition', 'redefinition'])

    def test_declaration_like_bullets_and_prose_do_not_gain_fallback(self):
        for bullet in ('`item`:', '`item`: value', '`item` value', '`item`\n    - child'):
            source = '[A]:\n- `item`\n\n[B]:\n1. Inspect:\n  - ' + bullet + '\n'
            self.assertEqual([m.kind for m in analyze(source).semantics.members],
                             ['definition', 'unsupported_declaration'], source)
        source = '[A]:\n- `item`\n\n[B]:\n1. Inspect:\n  - Use `item`\n'
        self.assertEqual([m.kind for m in analyze(source).semantics.members],
                         ['definition', 'invocation'])

    def test_operand_shielding_and_uncertain_ownership(self):
        prefix = '[A]:\n- `item`\n\n'
        for body in ('[B]:\n"""\n1. Inspect:\n  - `item`\n"""\n',
                     '[B]:\n1. Inspect:\n  - "`item`"\n',
                     '[B]:\n1. Inspect:\n   - `item`\n',
                     '[B]\n  1. Inspect:\n    - `item`\n'):
            self.assertEqual([m.kind for m in analyze(prefix + body).semantics.members], ['definition'], body)
        plain = prefix + 'Task:\n1. Inspect:\n  - `item`\n'
        self.assertEqual([m.kind for m in analyze(plain).semantics.members],
                         ['definition', 'invocation'])
        self.assertFalse(analyze(prefix + '[B]:\n1. Inspect:\n  - `item`\n',
                                 arcgrav_version='future').diagnostics.findings)


    def test_members_correlate_across_inline_symbols(self):
        source = ('[State]:\n- `position`\n- `remaining`\n\n'
                  '[Step]:\n1. Inspect:\n  - `position`\n  - `remaining`\n'
                  '2. Read `position`\n3. Move `position`\n\nTask:\n- Run [Step]\n')
        result = analyze(source)
        for name, expected in (
                ('position', ['definition', 'invocation', 'reference', 'reference']),
                ('remaining', ['definition', 'invocation'])):
            with self.subTest(name=name):
                hits = [m for m in result.semantics.members
                        if m.span.extract(source) == chr(96) + name + chr(96)]
                self.assertEqual([m.kind for m in hits], expected)
                self.assertTrue(all(m.definition == hits[0].span for m in hits[1:]))
                self.assertFalse([
                    f for f in self.findings(source)
                    if f.source_range.span.extract(source) == chr(96) + name + chr(96)
                    and f.rule_id in ('AG-MEMBER-UNDEFINED', 'AG-MEMBER-ORPHAN')
                ])

    def test_ambiguity_admission_and_unicode_source_ranges(self):
        from AgStudio.shared.panel_projections import derive_findings
        from AgStudio.shared.recognition import SourceSpan
        for ending in ('\n', '\r\n', '\u2028'):
            source = ending.join(['[A]:', '- `🌍`', '', '[B]:', '- `🌍`', '',
                                  '[C]:', '1. Inspect:', '  - `🌍`', ''])
            result = analyze(source)
            finding = next(f for f in self.findings(source) if f.rule_id == 'AG-MEMBER-AMBIGUOUS')
            span = finding.source_range.span
            self.assertEqual(span, SourceSpan(source.rindex('`🌍`'), source.rindex('`🌍`') + 3))
            candidate = Candidate(finding.rule_id, span, 8, 'untrusted', REGISTRY[finding.rule_id].required_evidence)
            self.assertEqual(admission(candidate, result.document, result.tree, result.semantics), ())
            self.assertTrue(admission(replace(candidate, evidence=()), result.document, result.tree, result.semantics))
            self.assertIn('unsupported_member_evidence', admission(
                replace(candidate, span=SourceSpan(span.start + 1, span.end)),
                result.document, result.tree, result.semantics))
            clean = analyze(source.replace('- `🌍`', '- `x`', 1))
            forged = replace(clean.semantics, members=result.semantics.members)
            clean_use = clean.semantics.members[-1]
            self.assertIn('unsupported_member_evidence', admission(
                replace(candidate, span=clean_use.span), clean.document, clean.tree, forged))
            self.assertEqual(finding.severity, 'warning')
            self.assertEqual((finding.source_range.start.line, finding.source_range.start.column), (9, 5))
            self.assertEqual((finding.source_range.end.line, finding.source_range.end.column), (9, 8))
            row = next(row for row in derive_findings(result).rows if row.finding.rule_id == finding.rule_id)
            self.assertEqual(row.texts[0], 'Warning')
            self.assertEqual(row.texts[3:], ('9', '5'))
            self.assertEqual(row.finding.source_range.span.extract(source), '`🌍`')
