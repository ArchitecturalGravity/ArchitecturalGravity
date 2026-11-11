"""Exact, whole double-quoted element identity in the current document."""
from collections import Counter

from .syntax import active_double_quoted_elements, double_quote_collisions

RULE_ID = 'AG-QUOTED-ELEMENT-NO-MATCH'
MESSAGE = 'No other identical double-quoted element was found in this document'
COLLISION_RULE_ID = 'AG-DOUBLE-QUOTE-COLLISION'
COLLISION_MESSAGE = 'Embedded double quotes collide with the outer double quotes. Use a literal quote block instead'


def quoted_element_collisions(tree):
    return frozenset((node.id, span) for node in tree.nodes
                     for span in double_quote_collisions(node))


def unmatched_quoted_elements(tree):
    """Index canonical active scalar occurrences once; an element cannot match itself.

    Matching is independent of source order, nesting and symbol ownership. No
    substring, escape decoding, whitespace or Unicode normalization is applied.
    Fence bodies, other quote kinds and unfinished recovery values are excluded.
    """
    occurrences = [(node.id, token) for node in tree.nodes
                   for token in active_double_quoted_elements(node)]
    counts = Counter(token.text for _, token in occurrences)
    return frozenset((node_id, token.span) for node_id, token in occurrences
                     if counts[token.text] == 1)
