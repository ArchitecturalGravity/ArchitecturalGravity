"""Opaque examples cannot change active ownership or language evidence."""
import unittest

from AgStudio.shared.lint import analyze
from AgStudio.shared.highlighting import highlight_tokens


class OpaqueFenceTests(unittest.TestCase):
    def test_exact_user_example(self):
        source = '[SomeFence]:\n""""\nLook at this fence:\n"""\nSomething\n"""\n""""'
        result = analyze(source)
        self.assertEqual([n.kind for n in result.tree.nodes],
                         ['section_header_candidate', 'literal_open',
                          'literal_content', 'literal_content', 'literal_content',
                          'literal_content', 'literal_close'])
        self.assertEqual([s.name for s in result.semantics.symbols], ['SomeFence'])
        self.assertFalse(any(f.rule_id == 'AG-LITERAL-FENCE-WIDTH'
                             for f in result.diagnostics.findings))
        self.assertEqual(''.join(t.text for t in result.tree.tokens), source)

    def test_fenced_fake_headings_never_steal_following_owner(self):
        for opening, closing in [('""""', '""""'), ('```arcgrav', '```'), ('~~~', '~~~~')]:
            source = ('Scope:\n- Read text\n\n[Owner]:\n' + opening + '\n'
                      'Fake:\n[Hidden]:\n=> - recieve [9bad] [Missing] ↳   \n'
                      '  """\n  Task:\n  """\n' + closing + '\n'
                      '- Context\n\nTask:\n- Read [Owner]\n')
            result = analyze(source)
            child = next(n for n in result.tree.nodes if n.span.extract(source) == '- Context\n')
            owner = result.tree.nodes[child.section]
            self.assertEqual(owner.span.extract(source), '[Owner]:\n', source)
            self.assertFalse(any(s.name in {'Hidden', '9bad', 'Missing'} for s in result.semantics.symbols))
            left, right = source.index(opening), source.index(closing, source.index(opening) + len(opening)) + len(closing)
            self.assertFalse([f for f in result.diagnostics.findings
                              if left < f.source_range.span.start < right], source)
            self.assertFalse([t for t in highlight_tokens(result.document)
                              if left < t.span.start < right and t.role not in ('literal', 'delimiter')], source)
            self.assertEqual(''.join(t.text for t in result.tree.tokens), source)

    def test_markdown_quote_text_cannot_steal_close_or_following_structure(self):
        for opener, closer in [('```python', '````'), ('~~~text', '~~~')]:
            source = 'Scope:\n' + opener + '\n"""\nTask:\n[9bad]\n' + closer + '\n\nTask:\n- Read text\n'
            result = analyze(source)
            self.assertEqual(result.tree.nodes[-2].kind, 'section_header_candidate')
            self.assertFalse(result.diagnostics.findings)
            self.assertFalse(any(8 <= f.span.start < source.index(closer) for f in result.document.occurrence_facts))

    def test_unclosed_markdown_shields_to_eof_without_quote_diagnostics(self):
        result = analyze('Scope:\n```\n"""\n[9bad]\n=> - recieve\nTask:\n')
        self.assertFalse(result.semantics.symbols)
        self.assertFalse(result.diagnostics.findings)
        self.assertTrue(all(n.kind == 'markdown_fence_content' for n in result.tree.nodes[2:]))

    def test_invalid_quote_width_only_checks_delimiters_inside(self):
        source = 'Scope:\n"""\n""""\n[9bad]\n=> - recieve\n""""\n"""\n\nTask:\n- Read text\n'
        result = analyze(source)
        self.assertEqual([f.rule_id for f in result.diagnostics.findings], ['AG-LITERAL-FENCE-WIDTH'])
        self.assertFalse(result.semantics.symbols)

    def test_unclosed_quote_keeps_invalid_content_opaque(self):
        result = analyze('Scope:\n""""\n"""\n[9bad]\n=> - recieve\n"""\nFake:\n')
        self.assertEqual([f.rule_id for f in result.diagnostics.findings], ['AG-LITERAL-UNCLOSED'])
        self.assertFalse(result.semantics.symbols)


if __name__ == '__main__':
    unittest.main()
