"""Decode retained ARB structured responses without repairing their content.

Schema defects are deliberately left to the field scorer so a missing field does
not discard credit for otherwise correct output. Duplicate JSON object members
are rejected; repeated finding IDs remain ordinary array occurrences. The
non-finite constants accepted by the Golden's Python JSON boundary are retained.
"""

from __future__ import annotations

import json
from typing import Any


class StructuredOutputParseError(ValueError):
    """The retained response is not one unambiguous UTF-8 JSON object."""


def _unique_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StructuredOutputParseError("duplicate JSON object member")
        result[key] = value
    return result


def parse_structured_output(raw: bytes) -> dict[str, Any]:
    """Parse exact bytes, accepting JSON whitespace and Golden's NaN/Infinity.

No Markdown stripping, coercion, defaulting, field selection, or Golden
execution occurs here. Array order and duplicate array occurrences are retained.
"""
    if not isinstance(raw, bytes):
        raise TypeError("raw must be exact bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_members)
    except StructuredOutputParseError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise StructuredOutputParseError("invalid UTF-8 JSON response") from exc
    if not isinstance(value, dict):
        raise StructuredOutputParseError("ARB response must be a JSON object")
    return value


__all__ = ["StructuredOutputParseError", "parse_structured_output"]
