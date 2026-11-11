"""Parity and deterministic work bounds for canonical occurrence filtering."""

from dataclasses import fields
import random
from types import MappingProxyType
import unittest
from unittest.mock import patch

from AgStudio.arcgrav_language_engine.core import LanguageCore
from AgStudio.arcgrav_language_engine.document import DocumentFact, ParsedDocument, parse_document
from AgStudio.arcgrav_language_engine.lint.model import CanonicalDocument
from AgStudio.arcgrav_language_engine.lint.semantics import Semantics, resolve
from AgStudio.arcgrav_language_engine.lint.syntax import SyntaxTree, Token, parse
from AgStudio.arcgrav_language_engine.recognition import SourceRecovery, SourceSpan


EMPTY_SEMANTICS = Semantics((), (), ())


def document_fixture(specs=(), recoveries=(), size=256):
    """Supply exact-coordinate facts, including cases not emitted by recognition.

    Deliberately retain arbitrary occurrence order, overlaps and empty spans so
    the projection cannot silently depend on the recognizer's current ordering.
    """
    base = parse_document(LanguageCore.open_source('x' * size, arcgrav_version='current'))
    document = object.__new__(ParsedDocument)
    for field in fields(ParsedDocument):
        object.__setattr__(document, field.name, getattr(base, field.name))
    facts = tuple(DocumentFact(f'o:{index}', kind, 'occurrence',
                               base.source_range(span), None, (), 'observed', None)
                  for index, (kind, span) in enumerate(specs))
    object.__setattr__(document, 'occurrence_facts', facts)
    object.__setattr__(document, 'recoveries', tuple(recoveries))
    object.__setattr__(document, '_facts_by_id', MappingProxyType({f.id: f for f in facts}))
    return document


def naive_occurrences(document, tree):
    shields = tuple(t.span for t in tree.tokens if t.kind in ('literal', 'quoted_scalar'))
    active_spans = {t.span for t in tree.tokens
                    if t.kind not in ('literal', 'quoted_scalar', 'text', 'whitespace', 'newline')}
    return tuple(f for f in document.occurrence_facts
                 if (f.kind != 'symbol_candidate' or f.span in active_spans)
                 and not any(q.start < f.span.end and f.span.start < q.end for q in shields))


class CanonicalFilterIndexTests(unittest.TestCase):
    def assert_projection_parity(self, document, tree, semantics=EMPTY_SEMANTICS):
        expected = naive_occurrences(document, tree)
        expected_recoveries = tuple(r for r in document.recoveries if r.span in tree.recovery_spans)
        projected = CanonicalDocument(document, tree, semantics)
        self.assertEqual(projected.occurrence_facts, expected)
        self.assertEqual(projected.recoveries, expected_recoveries)
        for actual, original in zip(projected.occurrence_facts, expected):
            self.assertIs(actual, original)
            self.assertIs(projected.fact(actual.id), original)
        for actual, original in zip(projected.recoveries, expected_recoveries):
            self.assertIs(actual, original)
        return projected

    def test_strict_overlap_boundaries_nested_and_zero_width_spans(self):
        spans = ((0, 10), (9, 11), (10, 10), (10, 11), (15, 15),
                 (20, 20), (20, 30), (29, 31), (30, 30), (30, 31),
                 (48, 49), (50, 50), (49, 51), (60, 61))
        document = document_fixture(tuple(('wildcard_candidate', SourceSpan(*span)) for span in spans))
        tokens = (Token('literal', SourceSpan(10, 20)),
                  Token('quoted_scalar', SourceSpan(30, 30)),
                  Token('literal', SourceSpan(40, 50)),
                  Token('quoted_scalar', SourceSpan(45, 46)),
                  Token('quoted_scalar', SourceSpan(50, 60)))
        expected_ids = tuple(f'o:{i}' for i in (0, 2, 5, 6, 8, 9, 11, 13))
        for ordered in (tokens, tuple(reversed(tokens)), tokens[2:] + tokens[:2]):
            with self.subTest(tokens=ordered):
                projected = self.assert_projection_parity(document, SyntaxTree(ordered, (), ()))
                self.assertEqual(tuple(f.id for f in projected.occurrence_facts), expected_ids)

    def test_active_symbol_filter_and_shield_kinds_are_unchanged(self):
        spans = ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11),
                 (12, 13), (14, 15), (16, 17), (22, 23), (26, 27),
                 (30, 31), (32, 33), (35, 36))
        kinds = ('symbol_candidate',) * 8 + ('wildcard_candidate',) * 4 + ('symbol_candidate',) * 2
        document = document_fixture(tuple((kind, SourceSpan(*span)) for kind, span in zip(kinds, spans)))
        tokens = tuple(Token(kind, SourceSpan(*span)) for kind, span in (
            ('symbol', (0, 1)), ('text', (2, 3)), ('whitespace', (4, 5)),
            ('newline', (6, 7)), ('backtick_scalar', (8, 9)),
            ('literal_open', (12, 13)), ('literal_close', (14, 15)),
            ('backtick_scalar', (15, 20)), ('quoted_scalar', (21, 24)),
            ('literal', (25, 28)), ('text', (30, 31)),
            ('symbol', (32, 33)), ('quoted_scalar', (31, 34)), ('symbol', (35, 38)),
        ))
        projected = self.assert_projection_parity(document, SyntaxTree(tuple(reversed(tokens)), (), ()))
        self.assertEqual(tuple(f.id for f in projected.occurrence_facts),
                         ('o:0', 'o:4', 'o:6', 'o:7', 'o:8', 'o:11'))

    def test_recovery_membership_preserves_order_duplicates_and_objects(self):
        recoveries = tuple(SourceRecovery(SourceSpan(i, i + 1), i + 1, 'unfinished_symbol')
                           for i in (40, 10, 20, 30))
        first, second, excluded, last = recoveries
        document = document_fixture(recoveries=(first, second, first, excluded, last, second))
        tree = SyntaxTree((), (), (SourceSpan(30, 31), SourceSpan(40, 41),
                                  SourceSpan(40, 41), SourceSpan(10, 11)))
        projected = self.assert_projection_parity(document, tree)
        self.assertEqual(projected.recoveries, (first, second, first, last, second))

    def test_randomized_unordered_inputs_match_naive_filter(self):
        randomizer = random.Random(73041)
        token_kinds = ('literal', 'quoted_scalar', 'backtick_scalar', 'symbol',
                       'text', 'whitespace', 'newline', 'literal_open', 'literal_close')
        fact_kinds = ('symbol_candidate', 'wildcard_candidate',
                      'alias_marker_candidate', 'backticked_reference_candidate')
        for case in range(80):
            with self.subTest(case=case):
                spans = tuple(SourceSpan(start, min(256, start + randomizer.randrange(15)))
                              for start in (randomizer.randrange(257) for _ in range(100)))
                tokens = tuple(Token(randomizer.choice(token_kinds), randomizer.choice(spans))
                               for _ in range(randomizer.randrange(65)))
                recoveries = tuple(SourceRecovery(span, span.end, 'unfinished_symbol')
                                   for span in (randomizer.choice(spans) for _ in range(25)))
                document = document_fixture(tuple((randomizer.choice(fact_kinds), span) for span in spans),
                                            recoveries)
                tree = SyntaxTree(tokens, (), tuple(randomizer.choice(spans) for _ in range(30)))
                self.assert_projection_parity(document, tree)

    def test_real_parser_projection_matches_naive_filter(self):
        sources = ('', 'Task:\n- Use [A] and `path`\n',
                   '[A]: value\n- Use [A]\n"[Hidden] *"\n',
                   '\n'.join(('Task:', '"""', '[Hidden] *', '"""', '=>', '[Open')),
                   '[Text]: "[Missing] AS [False] ↳ *"\n\nTask:\n- Use [Text]')
        for source in sources:
            with self.subTest(source=source):
                document = parse_document(LanguageCore.open_source(source, arcgrav_version='current'))
                tree = parse(document)
                self.assert_projection_parity(document, tree, resolve(document, tree))

    def test_shield_filter_has_subquadratic_coordinate_work(self):
        original_getattribute = SourceSpan.__getattribute__
        for size in (128, 512):
            with self.subTest(size=size):
                document = document_fixture(tuple(('wildcard_candidate', SourceSpan(2 * size + i, 2 * size + i + 1))
                                                  for i in range(size)), size=3 * size)
                tree = SyntaxTree(tuple(Token('quoted_scalar', SourceSpan(2 * i, 2 * i + 1))
                                        for i in reversed(range(size))), (), ())
                coordinate_reads = 0

                def count_coordinates(span, name):
                    nonlocal coordinate_reads
                    if name in ('start', 'end'):
                        coordinate_reads += 1
                    return original_getattribute(span, name)

                with patch.object(SourceSpan, '__getattribute__', count_coordinates):
                    projected = CanonicalDocument(document, tree, EMPTY_SEMANTICS)
                self.assertEqual(projected.occurrence_facts, document.occurrence_facts)
                # Index construction and per-fact lookups read only O(S + F)
                # span coordinates; binary search compares the copied integers.
                self.assertLess(coordinate_reads, 20 * size)

    def test_recovery_filter_has_linear_membership_work(self):
        original_equal = SourceSpan.__eq__
        original_hash = SourceSpan.__hash__
        for size in (128, 512):
            with self.subTest(size=size):
                document = document_fixture(recoveries=tuple(
                    SourceRecovery(SourceSpan(i, i + 1), i + 1, 'unfinished_symbol')
                    for i in range(size)), size=size)
                tree = SyntaxTree((), (), tuple(SourceSpan(i, i + 1) for i in reversed(range(size))))
                operations = 0

                def count_equal(left, right):
                    nonlocal operations
                    operations += 1
                    return original_equal(left, right)

                def count_hash(span):
                    nonlocal operations
                    operations += 1
                    return original_hash(span)

                with patch.object(SourceSpan, '__eq__', count_equal), patch.object(SourceSpan, '__hash__', count_hash):
                    projected = CanonicalDocument(document, tree, EMPTY_SEMANTICS)
                self.assertEqual(projected.recoveries, document.recoveries)
                self.assertLess(operations, 5 * size)


if __name__ == '__main__':
    unittest.main()
