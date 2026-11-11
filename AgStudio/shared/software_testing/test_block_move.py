"""Exact source permutations must preserve canonical structure and identity."""
import unittest

from AgStudio.shared.core import LanguageCore
from AgStudio.shared.graph.adapter import whole_block_owners
from AgStudio.shared.lint.block_move import BlockMoveModel, SourceOffsetMap
from AgStudio.shared.lint.semantics import resolve
from AgStudio.shared.lint.syntax import parse
from AgStudio.shared.recognition import SourceSpan


def model(source, **context):
    document = LanguageCore.parse_document(
        LanguageCore.open_source(source, arcgrav_version='current', **context))
    tree = parse(document)
    return BlockMoveModel(document, tree, resolve(document, tree))


def owner_at(move, text, occurrence=0):
    position = -1
    for _ in range(occurrence + 1):
        position = move.source.index(text, position + 1)
    return next(node.id for node in move.tree.nodes
                if node.span.start <= position < node.span.end)


class BlockMoveTests(unittest.TestCase):
    def assert_exact_permutation(self, move, plan):
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.source), len(move.source))
        self.assertEqual(plan.source[plan.new_start:plan.new_end],
                         move.source[plan.old_start:plan.old_end])
        # Every character keeps its identity, not just matching names or text.
        self.assertEqual(sorted(plan.offset_map(i) for i in range(len(move.source))),
                         list(range(len(move.source))))
        for i, char in enumerate(move.source):
            self.assertEqual(char, plan.source[plan.offset_map(i)])
        stationary = (move.source[:plan.old_start] + move.source[plan.old_end:])
        self.assertEqual(stationary, plan.source[:plan.new_start] + plan.source[plan.new_end:])

    def test_independent_block_move_both_directions_keeps_exact_slices(self):
        source = '[A]:\n- α 🌍  \n\n[B]:\n- beta\n[C]:\n- gamma\n'
        move = model(source)
        a, b, c = (owner_at(move, '[' + name + ']') for name in 'ABC')
        self.assertEqual(move.slots(b), (0, source.index('[B]'), source.index('[C]'), len(source)))
        plan = move.plan(a, len(source))
        self.assert_exact_permutation(move, plan)
        self.assertEqual(plan.source, source[source.index('[B]'):] + source[:source.index('[B]')])
        plan = move.plan(c, 0)
        self.assert_exact_permutation(move, plan)
        self.assertEqual(plan.new_start, 0)
        self.assertEqual(move.source, source)
        with self.assertRaises(TypeError):
            move.blocks[a] = move.blocks[b]

    def test_all_line_endings_tabs_trailing_spaces_and_literal_body_are_exact(self):
        for newline in ('\n', '\r\n', '\r', '\v', '\f', '\x1c', '\x1d', '\x1e',
                        '\x85', '\u2028', '\u2029'):
            with self.subTest(newline=repr(newline)):
                a = newline.join(('[A]:', '- Context  ', '  """', '\t[Opaque]: AS [Hidden]  ',
                                  '  """', '', ''))
                b = newline.join(('[B]:', '- beta', ''))
                move = model(a + b)
                plan = move.plan(owner_at(move, '[A]'), len(a + b))
                self.assert_exact_permutation(move, plan)
                self.assertEqual(plan.source, b + a)

    def test_mixed_line_endings_never_normalized(self):
        a = '[A]:\r\n- alpha\u2028 \t\r\n'
        b = '[B]:\n- beta\r'
        c = '[C]:\u2029- gamma\n'
        move = model(a + b + c)
        plan = move.plan(owner_at(move, '[B]'), len(a + b + c))
        self.assert_exact_permutation(move, plan)
        self.assertEqual(plan.source, a + c + b)

    def test_parent_carries_nested_contexts_and_their_children(self):
        prefix = '[Base]: value\n'
        parent = ('[Parent]:\n- parent\n  [Base]:\n  - child\n'
                  '    Notes:\n    - grandchild\n\n')
        other = '[Other]:\n- separate\n'
        move = model(prefix + parent + other)
        owner = owner_at(move, '[Parent]')
        self.assertEqual(move.blocks[owner].span.extract(move.source), parent)
        plan = move.plan(owner, len(move.source))
        self.assert_exact_permutation(move, plan)
        self.assertEqual(plan.source, prefix + other + parent)

    def test_nested_duplicate_headers_are_not_independently_movable(self):
        prefix = '[Base]: value\n[Root]:\n'
        first = '  [Base]:\n  - first\n'
        notes = '  Notes:\n  - prose\n'
        second = '  [Base]:\n  - second\n'
        suffix = '[End]: done\n'
        move = model(prefix + first + notes + second + suffix)
        owner = owner_at(move, '[Base]', 1)
        # A second [Base]: is invalid instantiation syntax, not a fresh
        # movable identity. The containing [Root] block remains selectable.
        self.assertNotIn(owner, move.blocks)
        self.assertEqual(move.slots(owner), ())
        self.assertIsNone(move.plan(owner, len(prefix + first + notes)))
        self.assertIn(owner_at(move, '[Root]'), move.blocks)

    def test_children_with_explicit_binding_keep_their_owner(self):
        first = '=> Apply context ↳\n  - first\n  - child\n\n'
        second = '=> Other context ↳\n  - second\n'
        move = model(first + second)
        plan = move.plan(0, len(move.source))
        self.assert_exact_permutation(move, plan)
        self.assertEqual(plan.source, second + first)

    def test_dependency_invalid_gaps_remain_visible_but_never_plan(self):
        source = '[A]:\n- alpha\n[B]:\n- [A]\n[C]:\n- independent\n[D]:\n- [B]\n'
        move = model(source)
        a, b, c, d = (owner_at(move, '[' + name + ']') for name in 'ABCD')
        self.assertIn(0, move.slots(b))
        self.assertIn(len(source), move.slots(a))
        self.assertIsNone(move.plan(a, len(source)))
        self.assertIsNone(move.plan(b, 0))
        self.assertIsNone(move.plan(b, len(source)))
        self.assertIsNone(move.plan(d, move.blocks[b].start))
        self.assert_exact_permutation(move, move.plan(b, move.blocks[d].start))
        self.assert_exact_permutation(move, move.plan(c, 0))

    def test_alias_exports_restrict_source_order(self):
        source = ('[A]:\n- create AS [Alias]\n[B]:\n- [Alias]\n'
                  '[C]:\n- other\n')
        move = model(source)
        a, b, c = (owner_at(move, '[' + name + ']') for name in 'ABC')
        self.assertIsNone(move.plan(a, move.blocks[c].start))
        self.assertIsNone(move.plan(b, 0))
        self.assert_exact_permutation(move, move.plan(b, len(source)))

    def test_preexisting_forward_reference_cannot_silently_resolve(self):
        source = '[Use]:\n- [Future]\n[Spacer]:\n- other\n[Future]: value\n'
        move = model(source)
        future = owner_at(move, '[Future]', 1)
        use = owner_at(move, '[Use]')
        spacer = owner_at(move, '[Spacer]')
        self.assertIsNone(move.plan(future, 0))
        self.assertIsNone(move.plan(use, len(source)))
        self.assert_exact_permutation(move, move.plan(spacer, 0))

    def test_repeated_body_headers_cannot_replace_the_original_identity(self):
        source = '[A]: first\n[Independent]: other\n[A]: second\n'
        move = model(source)
        first, second = owner_at(move, '[A]'), owner_at(move, '[A]', 1)
        self.assertIsNone(move.plan(first, len(source)))
        self.assertIsNone(move.plan(second, 0))
        self.assert_exact_permutation(move, move.plan(second, source.index('[Independent]')))

    def test_identical_source_spelling_does_not_hide_identity_change(self):
        source = '[A]: same\n[A]: same\n'
        move = model(source)
        self.assertIsNone(move.plan(0, len(source)))

    def test_repeated_alias_cannot_replace_original_alias_declaration(self):
        source = 'Create AS [Alias]\n[Middle]: value\nReplace AS [Alias]\n'
        move = model(source)
        first, middle = owner_at(move, 'Create'), owner_at(move, '[Middle]')
        # The second alias belongs to Middle's section only if it is a header;
        # scalar sections here keep the expression independently movable.
        second = owner_at(move, 'Replace')
        self.assertIsNone(move.plan(first, len(source)))
        self.assertIsNone(move.plan(second, 0))
        self.assert_exact_permutation(move, move.plan(middle, 0))

    def test_qualified_member_access_must_stay_after_member_definition(self):
        source = ('[A]:\n- `part`: definition\n[B]:\n- [A].part\n'
                  '[C]:\n- unrelated\n')
        move = model(source)
        a, b, c = (owner_at(move, '[' + name + ']') for name in 'ABC')
        self.assertIsNone(move.plan(a, len(source)))
        self.assertIsNone(move.plan(b, 0))
        self.assert_exact_permutation(move, move.plan(c, 0))

    def test_member_definition_and_exposure_are_checked_beyond_graph_edges(self):
        source = ('[A]:\n- `x`: value\n[A]:\n- first use `x`\n'
                  '[A]:\n- use `x`\n')
        move = model(source)
        first_use = owner_at(move, '[A]', 1)
        second_use = owner_at(move, '[A]', 2)
        self.assertTrue(move.semantics.members)
        # Repeated headers remain duplicate symbol declarations. Inline exact
        # member uses now correlate to the one prior top-level definition:
        # the first use invokes, and the later use references that identity.
        # Reordering these source blocks changes which occurrence invokes it.
        # Block moves must preserve that source-order semantic distinction.
        self.assertEqual([s.kind for s in move.semantics.symbols],
                         ['anchor', 'duplicate_anchor', 'duplicate_anchor'])
        self.assertEqual([m.kind for m in move.semantics.members],
                         ['definition', 'invocation', 'reference'])
        self.assertIsNone(move.plan(first_use, len(source)))
        self.assertIsNone(move.plan(second_use, move.blocks[first_use].start))

    def test_global_member_operand_cannot_become_ambiguous_after_move(self):
        source = ('[A]:\n- `x`: one\n[B]:\n- do work:\n  - `x`\n'
                  '[C]:\n- `x`: two\n')
        move = model(source)
        b, c = owner_at(move, '[B]'), owner_at(move, '[C]')
        self.assertEqual(move.semantics.members[1].kind, 'invocation')
        self.assertFalse(move.semantics.resolutions)
        # There are no symbol-resolution edges at all; global member lookup
        # still changes from one prior match to two prior matches at this gap.
        self.assertIsNone(move.plan(c, move.blocks[b].start))

    def test_uncertain_recovered_and_unterminated_blocks_are_not_movable(self):
        for source in ('[A]:\n   - bad indent\n[B]: value\n',
                       '[A]:\n- [Broken\n[B]: value\n',
                       '"""\nunclosed\n'):
            with self.subTest(source=source):
                move = model(source)
                recovered_owners = {move.owners[n.id] for n in move.tree.nodes if n.recovered}
                self.assertFalse(recovered_owners.intersection(move.blocks))
                for n in move.tree.nodes:
                    if n.recovered or n.kind == 'unterminated_literal_open':
                        self.assertNotIn(n.id, move.blocks)

    def test_parse_ownership_change_is_rejected_even_without_references(self):
        source = '[A]: value\nfree prose\n[B]:\n- body\n'
        move = model(source)
        a, prose = owner_at(move, '[A]'), owner_at(move, 'free prose')
        # Moving the scalar away would make prose a child of B's open section.
        self.assertIsNone(move.plan(prose, len(source)))
        self.assert_exact_permutation(move, move.plan(a, len(source)))

    def test_bom_is_pinned_and_never_inserted_inside_source(self):
        prefix = '\ufeffPreamble\r\n'
        a, b = '[A]: value\r\n', '[B]: value\r\n'
        move = model(prefix + a + b)
        self.assertNotIn(0, move.blocks)
        owner = owner_at(move, '[B]')
        self.assertNotIn(0, move.slots(owner))
        plan = move.plan(owner, len(prefix))
        self.assert_exact_permutation(move, plan)
        self.assertEqual(plan.source, prefix + b + a)
        self.assertEqual(plan.source.count('\ufeff'), 1)

    def test_no_final_newline_never_joins_lines_or_adds_text(self):
        source = '[A]: value\n[B]: value\n[C]: value'
        move = model(source)
        a, b, c = (owner_at(move, '[' + name + ']') for name in 'ABC')
        self.assertIsNone(move.plan(a, len(source)))
        self.assertIsNone(move.plan(c, 0))
        self.assert_exact_permutation(move, move.plan(b, 0))
        self.assertFalse(move.plan(b, 0).source.endswith('\n'))

    def test_no_op_and_invalid_targets_do_not_mutate_or_reparse(self):
        from unittest.mock import patch
        move = model('[A]: value\n[B]: value\n')
        block = move.blocks[0]
        with patch('AgStudio.shared.lint.block_move.parse', side_effect=AssertionError('reparse')):
            for position in (block.start, block.end):
                plan = move.plan(0, position)
                self.assertEqual(plan.source, move.source)
                self.assertEqual(plan.new_start, block.start)
            for owner, position in ((999, 0), (0, -1), (0, 1), (0, True), (0, '0')):
                self.assertIsNone(move.plan(owner, position))

    def test_dependency_rejection_does_not_require_full_reparse(self):
        from unittest.mock import patch
        move = model('[A]: value\n[B]: [A]\n')
        with patch('AgStudio.shared.lint.block_move.parse', side_effect=AssertionError('reparse')):
            self.assertIsNone(move.plan(0, len(move.source)))

    def test_stale_snapshot_fails_closed(self):
        move = model('[A]: value\n[B]: value\n')
        changed = LanguageCore.parse_document(move.document.session.with_source('changed'))
        stale = BlockMoveModel(changed, move.tree, move.semantics)
        self.assertFalse(stale.blocks)
        self.assertEqual(stale.slots(0), ())
        self.assertIsNone(stale.plan(0, 0))

    def test_supplied_owner_mapping_is_copied(self):
        move = model('[A]: value\n[B]: value\n')
        owners = whole_block_owners(move.tree, move.semantics)
        snapshot = BlockMoveModel(move.document, move.tree, move.semantics, owners)
        owners.clear()
        self.assertTrue(snapshot.owners)
        self.assertTrue(snapshot.blocks)

    def test_version_profile_and_configuration_survive_validation(self):
        from unittest.mock import patch
        move = model('[A]: value\n[B]: value\n', profile='editor', configuration={'example': [1, 2]})
        real_parse = LanguageCore.parse_document
        with patch.object(LanguageCore, 'parse_document', wraps=real_parse) as parse_document:
            self.assertIsNotNone(move.plan(0, len(move.source)))
        session = parse_document.call_args.args[0]
        self.assertEqual(session.arcgrav_version, move.document.session.arcgrav_version)
        self.assertEqual(session.profile, 'editor')
        self.assertEqual(session.configuration, {'example': [1, 2]})


class SourceOffsetMapTests(unittest.TestCase):
    def test_boundaries_and_half_open_spans_both_directions(self):
        for destination, expected in ((0, [2, 3, 0, 1, 4, 5]), (6, [0, 1, 4, 5, 2, 3])):
            mapping = SourceOffsetMap(2, 4, destination, 6)
            self.assertEqual([mapping(i) for i in range(6)], expected)
            self.assertEqual(mapping(6), 6)
            self.assertEqual(mapping.span(SourceSpan(2, 4)),
                             SourceSpan(mapping.new_start, mapping.new_start + 2))
            with self.assertRaises(ValueError):
                mapping.span(SourceSpan(0, 6))
            for offset in (-1, 7, True):
                with self.assertRaises(ValueError):
                    mapping(offset)


if __name__ == '__main__':
    unittest.main()
