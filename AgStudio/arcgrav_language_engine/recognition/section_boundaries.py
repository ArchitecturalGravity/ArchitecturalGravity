"""Bounded section-boundary recognition extensions.

This module layers gap-bound horizontal-separator section observations on top of the
source-preserving Stage 01 recognizer. It does not create ArcGrav grammar or
normative conformance; it only upgrades specific unclassified source shapes
whose source ranges and uncertainty can be preserved conservatively.
"""

from __future__ import annotations

import unicodedata

from ..core import SourceSession
from .source import RecognitionResult, SourceObservation
from .source import recognize_source as _recognize_source

_LINE_ENDINGS = "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def _strip_leading_horizontal_prefix(content: str) -> str:
    """Remove only the already gap-bound leading horizontal prefix."""
    prefix_end = 0
    for char in content:
        if char in " \t" or unicodedata.category(char) == "Zs":
            prefix_end += 1
            continue
        break
    return content[prefix_end:]


def _single_bracket_unwrap(label: str) -> str:
    if len(label) > 2 and label.startswith("[") and label.endswith("]"):
        return label[1:-1]
    return label


def _has_extended_horizontal_label_separator(label: str) -> bool:
    """Observe one complete horizontal run between two compact label parts.

    At least one tab or non-ASCII Zs keeps ordinary ASCII-space prose outside
    this boundary. The entire run must be contiguous, so additional words,
    punctuation, and other Unicode whitespace remain deferred. This only
    records the section-header gap; it establishes no accepted spacing rule.
    """
    body = _single_bracket_unwrap(label)
    positions = [
        index for index, char in enumerate(body)
        if char in " \t" or unicodedata.category(char) == "Zs"
    ]
    if not positions or positions[-1] - positions[0] + 1 != len(positions):
        return False
    separator = body[positions[0]:positions[-1] + 1]
    if not any(char == "\t" or (char != " " and unicodedata.category(char) == "Zs")
               for char in separator):
        return False
    left = body[:positions[0]]
    right = body[positions[-1] + 1:]
    return bool(left and right and left.isidentifier() and right.isidentifier())


def _plausible_gap_bound_suffix(suffix: str) -> bool:
    unicode_suffix = bool(suffix) and unicodedata.category(suffix[0]) == "Zs"
    return (
        not suffix.strip(" \t")
        or suffix.startswith((" ", "\t"))
        or unicode_suffix
        or bool(suffix and (suffix[0].isidentifier()
                            or suffix[0].isdigit() or suffix[0] == ":"))
    )


def _horizontal_section_boundary(text: str) -> bool:
    """Observe source-only two-part horizontal section-gap boundaries."""
    content = text.rstrip(_LINE_ENDINGS)
    unprefixed = _strip_leading_horizontal_prefix(content)
    label, colon, suffix = unprefixed.partition(":")
    if not colon or not label:
        return False
    if label[-1] in " \t" or unicodedata.category(label[-1]) == "Zs":
        return False
    return (_has_extended_horizontal_label_separator(label)
            and _plausible_gap_bound_suffix(suffix))


def recognize_source(session: SourceSession) -> RecognitionResult:
    """Add two-part horizontal separator section-gap candidates.

    An existing line observation, the exact source partition and independent
    source occurrences are never reinterpreted. This overlay cannot promote a
    candidate to an admitted header/scalar or a conformance claim.
    """
    result = _recognize_source(session)
    observations = []
    changed = False
    for region, observation in zip(result.regions, result.observations):
        if (observation.kind == "unclassified"
                and _horizontal_section_boundary(region.text)):
            observations.append(SourceObservation(
                region.span, "section_boundary_candidate"
            ))
            changed = True
        else:
            observations.append(observation)
    if not changed:
        return result
    return RecognitionResult(
        result.session, result.regions, tuple(observations), result.occurrences,
        result.recoveries,
    )


__all__ = ["recognize_source"]
