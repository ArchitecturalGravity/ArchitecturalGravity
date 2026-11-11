"""Independent typed-lexer, quote isolation and recovering ownership checks."""
from dataclasses import FrozenInstanceError
import unittest
from unittest import mock

from AgStudio.shared import LanguageCore
from AgStudio.shared.lint.syntax import lex, parse


def tree_for(source):
    session = LanguageCore.open_source(source, arcgrav_version='current')
    return parse(LanguageCore.parse_document(session))


class LintSyntaxRecoveryTests(unittest.TestCase):
    def test_typed_tokens_are_lossless_and_do_not_consume_colors(self):
        source = '[État]: 🌍\r\n=> Use [État] AS [Result]\r\n- src/*.py\r\n'
        with mock.patch('AgStudio.shared.highlighting.highlight_tokens', side_effect=AssertionError('presentation')):
            tree = tree_for(source)
        self.assertEqual(''.join(t.text for t in tree.tokens), source)
        cursor = 0
        for token in tree.tokens:
            self.assertEqual(token.span.start, cursor)
            self.assertEqual(token.span.extract(source), token.text)
            cursor = token.span.end
        self.assertEqual(cursor, len(source))
        self.assertTrue({'symbol', 'section_colon', 'operation', 'alias_keyword', 'list_marker',
                         'wildcard', 'newline'} <= {t.kind for t in tree.tokens})
        self.assertEqual(tree, tree_for(source))
        with self.assertRaises(FrozenInstanceError):
            tree.nodes[0].kind = 'changed'

    def test_all_prefixes_are_typed_but_internal_prose_markers_are_not(self):
        for source, markers in [('- - => Act', ['-', '-', '=>']),
                                ('=> => - Act', ['=>', '=>', '-']),
                                ('P0. => Act', ['P0.', '=>']),
                                ('=> 1. Act', ['=>', '1.']),
                                ('=> Compare x - y', ['=>'])]:
            with self.subTest(source=source):
                node = tree_for(source).nodes[0]
                self.assertEqual([t.text for t in node.prefix_tokens], markers)

    def test_quoted_scalars_shield_all_syntax_and_uncertain_escapes(self):
        source = ('[Text]: "[Missing] AS [Alias] ↳ *"\n'
                  '- "unknown \\q [Hidden]" and [Visible]\n'
                  "- '[AlsoHidden]'\n")
        tree = tree_for(source)
        self.assertEqual([t.text for t in tree.tokens if t.kind == 'symbol'], ['[Text]', '[Visible]'])
        self.assertEqual(len([t for t in tree.tokens if t.kind == 'quoted_scalar']), 3)
        self.assertFalse(any(n.alias_target_span or n.binding_marker_span for n in tree.nodes))
        self.assertFalse(any(t.kind == 'wildcard' for t in tree.tokens))
        self.assertEqual(tree.recovery_spans, ())

    def test_unfinished_scalar_is_bounded_to_line_and_hides_bracket_recovery(self):
        source = '- "[Open\n- Use [Visible]\n'
        tree = tree_for(source)
        self.assertEqual(tree.recovery_spans, ())
        self.assertFalse(tree.nodes[0].recovered)
        self.assertEqual([t.text for t in tree.tokens if t.kind == 'symbol'], ['[Visible]'])

    def test_unsupported_inline_quote_runs_are_opaque_without_block_claim(self):
        source = 'Text: """[Hidden] AS [Alias]"""\n=> Use [Visible]\n'
        tree = tree_for(source)
        self.assertEqual([t.text for t in tree.tokens if t.kind == 'symbol'], ['[Visible]'])
        self.assertFalse(any(t.kind == 'literal_open' for t in tree.tokens))
        self.assertEqual(tree.recovery_spans, ())

    def test_literal_delimiter_widths_do_not_leak_inner_syntax(self):
        source = '[Source]:\n""""\n"""\n=> - [Fake] AS [Hidden] ↳\n"""\n""""\n=> Apply [Source]\n'
        tree = tree_for(source)
        self.assertEqual(''.join(t.text for t in tree.tokens), source)
        self.assertEqual([t.text for t in tree.tokens if t.kind == 'symbol'], ['[Source]', '[Source]'])
        self.assertEqual(len([t for t in tree.tokens if t.kind == 'literal_open']), 1)
        self.assertEqual(len([t for t in tree.tokens if t.kind == 'literal_close']), 1)
        self.assertEqual(tree.nodes[1].children, (2, 3, 4, 5))
        for node in tree.nodes[2:6]:
            self.assertEqual(node.parent, 1)
            self.assertEqual(node.symbol_tokens, ())

    def test_unclosed_literal_shields_to_eof_with_one_recovery(self):
        source = '""""\n"""\n[Missing] AS [Hidden]\n=> - Fake\n'
        tree = tree_for(source)
        self.assertEqual(len(tree.recovery_spans), 1)
        self.assertEqual(tree.recovery_spans[0].end, len(source))
        self.assertFalse(any(t.kind in ('symbol', 'operation', 'list_marker', 'alias_keyword') for t in tree.tokens))

    def test_plain_expression_binder_owns_indented_children(self):
        source = '[A]: value\nTransform [A] ↳\n  - Child\n  => Nested\n- Peer\n'
        tree = tree_for(source)
        self.assertEqual(tree.nodes[1].children, (2, 3))
        self.assertEqual(tree.nodes[2].parent, 1)
        self.assertEqual(tree.nodes[3].parent, 1)
        self.assertIsNone(tree.nodes[4].parent)
        self.assertEqual(tree.nodes[1].binding_marker_span.extract(source), '↳')
        self.assertEqual(tree.nodes[1].symbol_tokens[0].text, '[A]')
        self.assertIsNone(tree.nodes[1].anchor_span)

    def test_literal_dedent_ends_nested_section_scope(self):
        source = 'Task:\n- Root:\n  Inner:\n  - First\n"""\ntext\n"""\n  - After\n'
        tree = tree_for(source)
        self.assertEqual(tree.nodes[3].section, 2)
        self.assertIsNone(tree.nodes[-1].section)
        self.assertIsNone(tree.nodes[-1].parent)

    def test_same_indent_section_body_and_scalar_sections(self):
        tree = tree_for('Scope: C:\\Project\nTask:\n- First\n=> Next\n')
        self.assertEqual(tree.nodes[0].kind, 'section_scalar_candidate')
        self.assertEqual(tree.nodes[2].section, 1)
        self.assertEqual(tree.nodes[3].section, 1)
        self.assertEqual(tree.nodes[0].symbol_tokens, ())

    def test_anchors_require_unambiguous_canonical_section(self):
        for source, declared in [('[A]: value', True), ('[A]:', True), ('[A]::', False),
                                 ('[A]:=> x', False), ('[A] : x', False), ('A: value', False)]:
            with self.subTest(source=source):
                node = tree_for(source).nodes[0]
                self.assertEqual(node.anchor_span is not None, declared)
                if source.startswith('[A]') and not declared:
                    self.assertEqual(len(node.uncertain_declaration_spans), 1)

    def test_alias_requires_prior_expression_and_terminal_unambiguous_target(self):
        source = 'Use [R] AS [R]\n'
        node = tree_for(source).nodes[0]
        self.assertEqual(node.alias_target_span.extract(source), '[R]')
        self.assertEqual(node.alias_target_span.start, source.rindex('[R]'))
        for source in ('AS [A]', '- AS [A]', '=> AS [A]', 'Get AS [A] ↳',
                       'Context: AS [A]', '[Context]: AS [A]'):
            with self.subTest(source=source):
                node = tree_for(source).nodes[0]
                self.assertIsNone(node.alias_target_span)
                self.assertEqual(len(node.uncertain_declaration_spans), 1)
        self.assertTrue(tree_for('Get AS [A] ↳').nodes[0].alias_ambiguous)

    def test_incomplete_symbol_recovers_on_its_line_and_marks_indent(self):
        source = '  - [Open\n=> Real [Visible]\n'
        tree = tree_for(source)
        self.assertEqual(len(tree.recovery_spans), 1)
        self.assertEqual(tree.recovery_spans[0].extract(source), '[Open')
        self.assertTrue(tree.nodes[0].recovered)
        self.assertFalse(tree.nodes[1].recovered)
        self.assertEqual([t.text for t in tree.tokens if t.kind == 'symbol'], ['[Visible]'])


if __name__ == '__main__':
    unittest.main()
