"""Benchmark-neutral exact byte and UTF-8 text comparison primitives.

The exactness layer never normalizes implicitly. A caller may supply comparison
bytes produced by an explicitly registered normalization pipeline, but must also
supply the ordered normalization identities that authorize those bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Final

from ..availability import AvailabilityRecord


COMPARISON_MODES: Final[frozenset[str]] = frozenset({"bytes", "utf8_text"})


class ExactnessError(ValueError):
    """Raised when exact comparison cannot be performed without repair."""


@dataclass(frozen=True, slots=True)
class ExactComparisonOperand:
    """One retained input and the exact bytes authorized for comparison."""

    source_identity: str
    raw_bytes: bytes
    compared_bytes: bytes | None = None
    normalization_identities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty(self.source_identity, "source_identity")
        if type(self.raw_bytes) is not bytes:
            raise TypeError("raw_bytes must be bytes")
        if not isinstance(self.normalization_identities, tuple) or any(
            not isinstance(identity, str) or not identity.strip()
            for identity in self.normalization_identities
        ):
            raise ValueError(
                "normalization_identities must be a tuple of non-empty strings"
            )

        if self.compared_bytes is None:
            if self.normalization_identities:
                raise ExactnessError(
                    "registered normalization identities require explicit "
                    "compared_bytes; raw fallback is prohibited"
                )
            object.__setattr__(self, "compared_bytes", self.raw_bytes)
        elif type(self.compared_bytes) is not bytes:
            raise TypeError("compared_bytes must be bytes or None")
        elif (
            not self.normalization_identities
            and self.compared_bytes != self.raw_bytes
        ):
            raise ExactnessError(
                "comparison bytes may differ from raw bytes only when an "
                "explicit normalization identity is retained"
            )

    @property
    def raw_sha256(self) -> str:
        return _sha256(self.raw_bytes)

    @property
    def compared_sha256(self) -> str:
        compared = self.compared_bytes
        if compared is None:
            raise ExactnessError("compared bytes are unavailable")
        return _sha256(compared)


@dataclass(frozen=True, slots=True)
class ExactComparisonEvidence:
    """Reconstructable evidence for one exact comparison."""

    comparison_mode: str
    left_source_identity: str
    right_source_identity: str
    left_raw_sha256: str
    right_raw_sha256: str
    left_compared_sha256: str
    right_compared_sha256: str
    left_raw_byte_count: int
    right_raw_byte_count: int
    left_compared_byte_count: int
    right_compared_byte_count: int
    left_normalization_identities: tuple[str, ...]
    right_normalization_identities: tuple[str, ...]
    equal: bool
    computation_sha256: str
    availability: AvailabilityRecord

    def __post_init__(self) -> None:
        if self.comparison_mode not in COMPARISON_MODES:
            raise ValueError(f"unknown comparison_mode {self.comparison_mode!r}")
        for field_name in (
            "left_source_identity",
            "right_source_identity",
            "left_raw_sha256",
            "right_raw_sha256",
            "left_compared_sha256",
            "right_compared_sha256",
            "computation_sha256",
        ):
            _require_nonempty(getattr(self, field_name), field_name)
        for field_name in (
            "left_raw_byte_count",
            "right_raw_byte_count",
            "left_compared_byte_count",
            "right_compared_byte_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if type(self.equal) is not bool:
            raise TypeError("equal must be bool")
        if type(self.availability) is not AvailabilityRecord:
            raise TypeError("availability must be AvailabilityRecord")
        if self.availability.affected_kind != "measurement":
            raise ValueError(
                "exact comparison availability must describe a measurement"
            )
        if self.availability.state != "available":
            raise ValueError(
                "completed exact comparison evidence must be available"
            )
        if self.availability.source_identity != self.computation_sha256:
            raise ValueError(
                "availability source_identity must equal computation_sha256"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "comparison_mode": self.comparison_mode,
            "left_source_identity": self.left_source_identity,
            "right_source_identity": self.right_source_identity,
            "left_raw_sha256": self.left_raw_sha256,
            "right_raw_sha256": self.right_raw_sha256,
            "left_compared_sha256": self.left_compared_sha256,
            "right_compared_sha256": self.right_compared_sha256,
            "left_raw_byte_count": self.left_raw_byte_count,
            "right_raw_byte_count": self.right_raw_byte_count,
            "left_compared_byte_count": self.left_compared_byte_count,
            "right_compared_byte_count": self.right_compared_byte_count,
            "left_normalization_identities": list(
                self.left_normalization_identities
            ),
            "right_normalization_identities": list(
                self.right_normalization_identities
            ),
            "equal": self.equal,
            "computation_sha256": self.computation_sha256,
            "availability": self.availability.to_dict(),
        }


def compare_bytes(
    left: ExactComparisonOperand,
    right: ExactComparisonOperand,
    *,
    measurement_identity: str,
) -> ExactComparisonEvidence:
    """Compare the exact authorized bytes without implicit transformation."""

    left = _require_operand(left, "left")
    right = _require_operand(right, "right")
    left_compared = _compared_bytes(left)
    right_compared = _compared_bytes(right)
    return _build_evidence(
        comparison_mode="bytes",
        left=left,
        right=right,
        equal=left_compared == right_compared,
        measurement_identity=measurement_identity,
    )


def compare_utf8_text(
    left: ExactComparisonOperand,
    right: ExactComparisonOperand,
    *,
    measurement_identity: str,
) -> ExactComparisonEvidence:
    """Compare strict UTF-8 text exactly, with no decoding repair."""

    left = _require_operand(left, "left")
    right = _require_operand(right, "right")
    try:
        left_text = _compared_bytes(left).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ExactnessError(
            "left compared bytes are not valid UTF-8; decoding repair is "
            "prohibited"
        ) from exc
    try:
        right_text = _compared_bytes(right).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ExactnessError(
            "right compared bytes are not valid UTF-8; decoding repair is "
            "prohibited"
        ) from exc

    return _build_evidence(
        comparison_mode="utf8_text",
        left=left,
        right=right,
        equal=left_text == right_text,
        measurement_identity=measurement_identity,
    )


def _build_evidence(
    *,
    comparison_mode: str,
    left: ExactComparisonOperand,
    right: ExactComparisonOperand,
    equal: bool,
    measurement_identity: str,
) -> ExactComparisonEvidence:
    _require_nonempty(measurement_identity, "measurement_identity")
    left_compared = _compared_bytes(left)
    right_compared = _compared_bytes(right)
    identity_payload = {
        "comparison_mode": comparison_mode,
        "left_source_identity": left.source_identity,
        "right_source_identity": right.source_identity,
        "left_raw_sha256": left.raw_sha256,
        "right_raw_sha256": right.raw_sha256,
        "left_compared_sha256": left.compared_sha256,
        "right_compared_sha256": right.compared_sha256,
        "left_raw_byte_count": len(left.raw_bytes),
        "right_raw_byte_count": len(right.raw_bytes),
        "left_compared_byte_count": len(left_compared),
        "right_compared_byte_count": len(right_compared),
        "left_normalization_identities": list(left.normalization_identities),
        "right_normalization_identities": list(right.normalization_identities),
        "equal": equal,
        "measurement_identity": measurement_identity,
    }
    computation_sha256 = _sha256(
        json.dumps(
            identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    availability = AvailabilityRecord(
        affected_kind="measurement",
        affected=measurement_identity,
        state="available",
        reason="exact comparison completed",
        source_identity=computation_sha256,
    )
    return ExactComparisonEvidence(
        comparison_mode=comparison_mode,
        left_source_identity=left.source_identity,
        right_source_identity=right.source_identity,
        left_raw_sha256=left.raw_sha256,
        right_raw_sha256=right.raw_sha256,
        left_compared_sha256=left.compared_sha256,
        right_compared_sha256=right.compared_sha256,
        left_raw_byte_count=len(left.raw_bytes),
        right_raw_byte_count=len(right.raw_bytes),
        left_compared_byte_count=len(left_compared),
        right_compared_byte_count=len(right_compared),
        left_normalization_identities=left.normalization_identities,
        right_normalization_identities=right.normalization_identities,
        equal=equal,
        computation_sha256=computation_sha256,
        availability=availability,
    )


def _require_operand(
    value: ExactComparisonOperand,
    field_name: str,
) -> ExactComparisonOperand:
    if type(value) is not ExactComparisonOperand:
        raise TypeError(f"{field_name} must be ExactComparisonOperand")
    return value


def _compared_bytes(value: ExactComparisonOperand) -> bytes:
    compared = value.compared_bytes
    if compared is None:
        raise ExactnessError(
            "missing compared bytes cannot be treated as exact empty output"
        )
    return compared


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _require_nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


__all__ = [
    "COMPARISON_MODES",
    "ExactComparisonEvidence",
    "ExactComparisonOperand",
    "ExactnessError",
    "compare_bytes",
    "compare_utf8_text",
]
