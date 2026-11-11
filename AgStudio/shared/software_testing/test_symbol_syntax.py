"""Clarified symbolic names and matched, non-nested bracket syntax."""
import unittest
from AgStudio.shared.lint import analyze


class SymbolSyntaxTests(unittest.TestCase):
    def analyze(self, source):
        return analyze(source, configuration={'spellcheck': False})

    def errors(self, result):
        return [f for f in result.diagnostics.findings if f.rule_id == 'AG-SYNTAX-INCOMPLETE']

    def test_definitions_and_colonless_references(self):
        for name in ('Target', 'ThisIsASymbolicReference', 'API', 'HTTPServer', 'Version2', 'A'):
            with self.subTest(name=name):
                result = self.analyze(f'[{name}]: value\n\nTask:\n- Use [{name}]\n')
                self.assertEqual(self.errors(result), [])
                self.assertEqual([s.kind for s in result.semantics.symbols], ['anchor', 'reference'])
                self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_anchor')

    def test_colonless_reference_never_declares(self):
        result = self.analyze('Task:\n- Use [ThisIsASymbolicReference]\n')
        self.assertEqual(self.errors(result), [])
        self.assertEqual(result.semantics.symbols[0].kind, 'reference')
        self.assertIn('AG-SYMBOL-NO-LOCAL-ANCHOR', [f.rule_id for f in result.diagnostics.findings])

    def test_bad_names_and_brackets_are_errors(self):
        for shape in ('[Has Space]', '[ HasSpace]', '[HasSpace ]', '[lowercase]', '[badName]',
                      '[Bad_Name]', '[Bad-Name]', '[2Name]', '[Náme]', '[Name', '[', ']', 'Name]',
                      '[Outer [Inner] tail]', '[[Inner]]', '[Outer [Inner]', '[A\tB]'):
            with self.subTest(shape=shape):
                result = self.analyze('Task:\n- Use ' + shape + '\n')
                self.assertTrue(self.errors(result))
                self.assertTrue(all(f.severity == 'error' for f in self.errors(result)))
                self.assertFalse(result.semantics.symbols)
                self.assertFalse(any(f.kind == 'symbol_candidate' for f in result.document.occurrence_facts))
                self.assertEqual(''.join(t.text for t in result.tree.tokens), result.document.source)

    def test_nested_tokens_do_not_resolve_even_when_inner_exists(self):
        for prefix in ('', '[Inner]: value\n\n'):
            result = self.analyze(prefix + 'Task:\n- Use [Outer [Inner] tail]\n')
            self.assertEqual(len(self.errors(result)), 1)
            self.assertEqual(next(t.text for t in result.tree.tokens if t.kind == 'malformed_symbol'), '[Outer [Inner] tail]')
            self.assertFalse(result.semantics.resolutions)
            self.assertEqual([s.name for s in result.semantics.symbols], ['Inner'] if prefix else [])

    def test_recovery_is_line_bounded_and_keeps_sibling_references(self):
        result = self.analyze('[Good]: value\n\nTask:\n- [Outer [Inner] tail] [Good]\n- [Broken\n- [Good]\n')
        self.assertEqual(len(self.errors(result)), 2)
        self.assertEqual([r.status for r in result.semantics.resolutions], ['unique_prior_anchor'] * 2)

    def test_quoted_fenced_escaped_and_empty_collection_are_inert(self):
        for value in ('"[Outer [Inner] tail]"', "'[lowercase]'", '`[Broken`',
                      '"[Broken', '\\[Escaped]', '[]', '"""\n[Outer [Inner] tail]\n[Broken\n"""'):
            with self.subTest(value=value):
                result = self.analyze('Task:\n' + value + '\n')
                self.assertFalse(self.errors(result))
                self.assertFalse(result.semantics.symbols)

    def test_alias_names_follow_the_same_syntax(self):
        result = self.analyze('Task:\n=> Collect AS [GoodAlias2]\n=> Use [GoodAlias2]\n')
        self.assertFalse(self.errors(result))
        self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_alias')
        result = self.analyze('Task:\n=> Collect AS [bad_alias]\n')
        self.assertTrue(self.errors(result))
        self.assertFalse(result.semantics.symbols)

    def test_unfinished_quoted_brackets_do_not_swallow_later_active_symbols(self):
        result = self.analyze('[Good]: value\n\nTask:\n- "[Broken" [Good]\n')
        self.assertFalse(self.errors(result))
        self.assertEqual(result.semantics.resolutions[0].status, 'unique_prior_anchor')
        self.assertEqual([f.span.extract(result.document.source) for f in result.document.occurrence_facts
                          if f.kind == 'symbol_candidate'], ['[Good]', '[Good]'])

    def test_active_invalid_opener_is_not_hidden_by_an_inner_quote(self):
        result = self.analyze('Task:\n- [Outer "[Inner]" tail]\n')
        self.assertTrue(self.errors(result))
        self.assertFalse(result.semantics.symbols)
        self.assertTrue(any(t.kind == 'quoted_scalar' and t.text == '"[Inner]"' for t in result.tree.tokens))
        self.assertEqual(''.join(t.text for t in result.tree.tokens), result.document.source)

    def test_quote_contents_do_not_change_later_reference_recognition(self):
        for value in ('"`"', '"[Broken"', "'`'", '`[Broken`'):
            with self.subTest(value=value):
                result = self.analyze('[Good]: value\n\nTask:\n- ' + value + ' [Good]\n')
                self.assertFalse(self.errors(result))
                self.assertEqual([f.span.extract(result.document.source) for f in result.document.occurrence_facts
                                  if f.kind == 'symbol_candidate'], ['[Good]', '[Good]'])
