"""Canonical JSON primitives used by runtime identity.

``arcgrav.canonical-json.v1`` is intentionally narrow: JSON object keys are
strings, non-finite numbers are rejected, object keys are lexicographically
sorted, arrays retain their declared order, no insignificant whitespace is
emitted, and UTF-8 is used without ASCII-only escaping.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
from typing import Final


CANONICALIZATION: Final[str] = "arcgrav.canonical-json.v1"


class CanonicalizationError(ValueError):
    """Raised when a value cannot enter canonical JSON identity."""


def canonical_json_bytes(value: object) -> bytes:
    """Return deterministic UTF-8 JSON bytes for a JSON-compatible value."""

    normalized = _normalize_json_value(value, path="$", active=set())
    try:
        rendered = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # defensive; normalization owns errors
        raise CanonicalizationError(str(exc)) from exc
    return rendered.encode("utf-8")


def canonical_sha256(value: object) -> str:
    """Return the canonical SHA-256 identity for ``value``."""

    return sha256_bytes(canonical_json_bytes(value))


def sha256_bytes(data: bytes) -> str:
    """Return a shared-form SHA-256 identifier for exact bytes."""

    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _normalize_json_value(
    value: object,
    *,
    path: str,
    active: set[int],
) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"{path} contains a non-finite number")
        return value

    if isinstance(value, Mapping):
        marker = id(value)
        if marker in active:
            raise CanonicalizationError(f"{path} contains a reference cycle")
        active.add(marker)
        try:
            normalized: dict[str, object] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise CanonicalizationError(
                        f"{path} contains a non-string object key"
                    )
                child_path = f"{path}.{key}" if path != "$" else f"$.{key}"
                normalized[key] = _normalize_json_value(
                    item,
                    path=child_path,
                    active=active,
                )
            return normalized
        finally:
            active.remove(marker)

    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in active:
            raise CanonicalizationError(f"{path} contains a reference cycle")
        active.add(marker)
        try:
            return [
                _normalize_json_value(item, path=f"{path}[{index}]", active=active)
                for index, item in enumerate(value)
            ]
        finally:
            active.remove(marker)

    raise CanonicalizationError(
        f"{path} contains unsupported identity value type {type(value).__name__}"
    )


__all__ = [
    "CANONICALIZATION",
    "CanonicalizationError",
    "canonical_json_bytes",
    "canonical_sha256",
    "sha256_bytes",
]
