"""Provider-free conformance tests for shared exact comparison semantics."""

from __future__ import annotations

import unittest

from AgMark.shared.evaluation.exactness import (
    ExactComparisonOperand,
    ExactnessError,
    compare_bytes,
    compare_utf8_text,
)


class ExactnessConformanceTests(unittest.TestCase):
    def test_byte_equality_is_sensitive_to_whitespace_newlines_and_order(self) -> None:
        left = ExactComparisonOperand(
            source_identity="left",
            raw_bytes=b"alpha beta",
        )

        equal = compare_bytes(
            left,
            ExactComparisonOperand(
                source_identity="right-equal",
                raw_bytes=b"alpha beta",
            ),
            measurement_identity="exact-bytes-equal",
        )
        self.assertTrue(equal.equal)

        for source_identity, raw_bytes in (
            ("right-space", b"alpha  beta"),
            ("right-newline", b"alpha beta\n"),
            ("right-order", b"beta alpha"),
            ("right-byte", b"alpha betA"),
        ):
            with self.subTest(source_identity=source_identity):
                evidence = compare_bytes(
                    left,
                    ExactComparisonOperand(
                        source_identity=source_identity,
                        raw_bytes=raw_bytes,
                    ),
                    measurement_identity=f"exact-{source_identity}",
                )
                self.assertFalse(evidence.equal)

    def test_utf8_text_comparison_is_exact_and_rejects_invalid_utf8(self) -> None:
        left = ExactComparisonOperand(
            source_identity="left-text",
            raw_bytes="café".encode("utf-8"),
        )
        same = ExactComparisonOperand(
            source_identity="right-text",
            raw_bytes="café".encode("utf-8"),
        )
        changed = ExactComparisonOperand(
            source_identity="right-text-newline",
            raw_bytes="café\n".encode("utf-8"),
        )

        self.assertTrue(
            compare_utf8_text(
                left,
                same,
                measurement_identity="exact-text-equal",
            ).equal
        )
        self.assertFalse(
            compare_utf8_text(
                left,
                changed,
                measurement_identity="exact-text-newline",
            ).equal
        )

        with self.assertRaises(ExactnessError):
            compare_utf8_text(
                ExactComparisonOperand(
                    source_identity="invalid-utf8",
                    raw_bytes=b"\xff",
                ),
                same,
                measurement_identity="exact-text-invalid",
            )

    def test_normalized_bytes_require_retained_transform_identity(self) -> None:
        with self.assertRaises(ExactnessError):
            ExactComparisonOperand(
                source_identity="unauthorized-comparison-bytes",
                raw_bytes=b" A ",
                compared_bytes=b"A",
            )

        with self.assertRaises(ExactnessError):
            ExactComparisonOperand(
                source_identity="missing-comparison-bytes",
                raw_bytes=b" A ",
                normalization_identities=("arcgrav.normalization.trim@1",),
            )

    def test_normalized_evidence_retains_distinct_reproducible_identities(self) -> None:
        left = ExactComparisonOperand(
            source_identity="left-normalized",
            raw_bytes=b" A ",
            compared_bytes=b"A",
            normalization_identities=("arcgrav.normalization.trim@1",),
        )
        right = ExactComparisonOperand(
            source_identity="right-normalized",
            raw_bytes=b"A\n",
            compared_bytes=b"A",
            normalization_identities=("arcgrav.normalization.chomp@1",),
        )

        first = compare_bytes(
            left,
            right,
            measurement_identity="exact-normalized",
        )
        second = compare_bytes(
            left,
            right,
            measurement_identity="exact-normalized",
        )

        self.assertTrue(first.equal)
        self.assertNotEqual(first.left_raw_sha256, first.left_compared_sha256)
        self.assertNotEqual(first.right_raw_sha256, first.right_compared_sha256)
        self.assertEqual(
            ("arcgrav.normalization.trim@1",),
            first.left_normalization_identities,
        )
        self.assertEqual(
            ("arcgrav.normalization.chomp@1",),
            first.right_normalization_identities,
        )
        self.assertEqual(first.computation_sha256, second.computation_sha256)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.computation_sha256, first.availability.source_identity)

    def test_missing_output_cannot_be_coerced_to_exact_empty_output(self) -> None:
        with self.assertRaises(TypeError):
            ExactComparisonOperand(  # type: ignore[arg-type]
                source_identity="missing-output",
                raw_bytes=None,
            )


if __name__ == "__main__":
    unittest.main()
