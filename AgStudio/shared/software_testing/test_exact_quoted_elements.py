"""Public engine occurrence lookup preserves whole double-quoted identity."""
import pickle
import unittest
from unittest.mock import patch

from AgStudio.arcgrav_language_engine import AnalysisContext, analyze, prepare


CONTEXT = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})


class ExactQuotedElementTests(unittest.TestCase):
    def tree(self, source):
        return prepare(source, CONTEXT).tree

    def test_user_examples_are_distinct_whole_values(self):
        values = ('"This is a double quoted element"', '"This is something else"',
                  '"this is something else"')
        source = '\n'.join('- ' + value for value in values)
        tree = self.tree(source)
        for value in values:
            with self.subTest(value=value):
                matches = tree.find_quoted_element(value)
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0].text, value)
                self.assertEqual(matches[0].span.extract(source), value)
        self.assertEqual(tree.find_quoted_element('"something else"'), ())

    def test_only_identical_quoted_tokens_match_in_source_order(self):
        source = ('- this is an element\n- "this is an element"\n'
                  '- "this is an element with more"\n- "prefix this is an element"\n'
                  '- "This is an element"\n- "this  is an element"\n'
                  '- "this is an element "\n- \'this is an element\'\n'
                  '- `this is an element`\n- "this is an element"\n')
        tree = self.tree(source)
        matches = tree.find_quoted_element('"this is an element"')
        self.assertEqual([t.span.start for t in matches],
                         [source.index('"this is an element"'), source.rindex('"this is an element"')])
        self.assertEqual(tree.find_quoted_element('this is an element'), ())
        self.assertEqual(tree.find_quoted_element('"is an element"'), ())

    def test_literal_markdown_and_other_quote_bodies_stay_opaque(self):
        source = ('""""\n"same"\n"""\n"same"\n""""\n'
                  '```arc\n"same"\n```\n~~~\n"same"\n~~~\n'
                  '- \'"same"\'\n- `"same"`\n- """same"""\n'
                  '- "same"\n')
        matches = self.tree(source).find_quoted_element('"same"')
        self.assertEqual([t.span.start for t in matches], [source.rindex('"same"')])

    def test_invalid_queries_do_not_match_recovery_or_subtokens(self):
        tree = self.tree('- "unfinished\n- "a\\"\n- """opaque"""\n- "a" "b"\n')
        for query in ('', 'a', '"unfinished', '"a\\"', '"""opaque"""',
                      '"a" "b"', '"a""b"', ' "a"', '"a" ',
                      '\'a\'', '`a`', '"a\nb"', '"a\u2028b"'):
            with self.subTest(query=query):
                self.assertEqual(tree.find_quoted_element(query), ())
        with self.assertRaises(TypeError):
            tree.find_quoted_element(None)

    def test_backslashes_empty_values_and_unicode_are_source_exact(self):
        values = ('""', '"a\\"b"', '"a\\\\"', '"é"', '"e\u0301"',
                  '"a\\nb"', '"a\tb"', '"a b"')
        tree = self.tree('\n'.join('- ' + value for value in values))
        for value in values:
            with self.subTest(value=value):
                self.assertEqual([t.text for t in tree.find_quoted_element(value)], [value])

    def test_prepare_analyze_and_snapshot_roundtrip_share_canonical_lookup(self):
        source = '[A]: "[B] AS [Hidden]"\n\nTask:\n- "[B] AS [Hidden]"\n'
        prepared = prepare(source, CONTEXT)
        complete = analyze(source, CONTEXT)
        restored = pickle.loads(pickle.dumps(prepared))
        # Lookup uses existing canonical source tokens; it never reparses the
        # document or introduces symbol references from quoted content.
        with patch('AgStudio.arcgrav_language_engine.lint.syntax.parse', side_effect=AssertionError):
            for tree in (prepared.tree, complete.tree, restored.tree):
                self.assertEqual(len(tree.find_quoted_element('"[B] AS [Hidden]"')), 2)
        self.assertFalse(any(s.name in ('B', 'Hidden') for s in complete.semantics.symbols))


if __name__ == '__main__':
    unittest.main()
