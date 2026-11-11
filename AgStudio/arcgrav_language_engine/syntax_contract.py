"""Executable lexical boundaries shared by recognition, parsing and validation.

Symbols are non-nested ASCII PascalCase names; [] is an empty collection.
Ordered markers start at 1 with no leading zero; priority markers also admit 0.
Two ASCII spaces form an indentation level. Alternate separators are preserved
as boundary observations, not silently normalized into supported syntax.
Wildcards and external references are inert source; no filesystem resolution,
execution, implicit mutation or document-directed action is performed.
"""
from __future__ import annotations
import re

SYMBOL_NAME = re.compile(r"[A-Z][A-Za-z0-9]*\Z")
NUMERIC_LIST = re.compile(r"(?:[1-9][0-9]*\.|P(?:0|[1-9][0-9]*)\.)\Z")
INDENT_WIDTH = 2


def syntax_id(kind: str) -> str | None:
    """Classify validated observation kinds without an external lookup table."""
    for prefix, family in (
        ('unterminated_literal', 'literal'), ('literal', 'literal'),
        ('section_', 'section'), ('unordered_list_', 'unordered'),
        ('ordered_list_', 'ordered'), ('priority_list_', 'priority'),
        ('operation_', 'operation'), ('block_binding_', 'block_binding'),
        ('indentation_', 'grouping'), ('symbol_', 'symbol'),
        ('alias_', 'alias'), ('wildcard_', 'wildcard'),
    ):
        if kind.startswith(prefix):
            return 'syntax.' + family
    return None


def limitations(kind: str) -> tuple[str, ...]:
    """Report only conditions actually observed in this source occurrence."""
    if kind == 'wildcard_candidate':
        return ('wildcard_not_expanded',)
    if kind == 'backticked_reference_candidate':
        return ('external_resolution_not_performed',)
    if kind.startswith('unterminated_literal'):
        return ('unterminated_literal',)
    if 'boundary_candidate' in kind:
        return (kind.removesuffix('_candidate'),)
    return ()
