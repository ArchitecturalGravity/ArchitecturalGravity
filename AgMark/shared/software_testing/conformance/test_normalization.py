"""Provider-free conformance tests for registered normalization semantics."""

from __future__ import annotations

import hashlib
import unittest

from AgMark.shared.evaluation.normalization import (
    NormalizerRegistration,
    NormalizerRegistrationError,
    NormalizerRegistry,
    normalize_bytes,
)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


class NormalizationConformanceTests(unittest.TestCase):
    def test_declared_order_configuration_identity_and_hash_trace_are_reconstructable(
        self,
    ) -> None:
        registry = NormalizerRegistry()
        first = NormalizerRegistration.create(
            "normalizer.prepend",
            "1.0.0",
            {"prefix": "pre:"},
        )
        second = NormalizerRegistration.create(
            "normalizer.append",
            "2.1.0",
            {"suffix": ":post"},
        )
        calls: list[tuple[str, bytes]] = []

        def prepend(value: bytes, configuration: object) -> bytes:
            self.assertEqual({"prefix": "pre:"}, configuration)
            calls.append(("prepend", value))
            return b"pre:" + value

        def append(value: bytes, configuration: object) -> bytes:
            self.assertEqual({"suffix": ":post"}, configuration)
            calls.append(("append", value))
            return value + b":post"

        registry.register(first.transform_id, first.transform_version, prepend)
        registry.register(second.transform_id, second.transform_version, append)

        result = normalize_bytes(
            b"payload",
            source_identity="artifact:input",
            measurement_identity="metric.normalized",
            registrations=(first, second),
            registry=registry,
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(b"pre:payload:post", result.output_bytes)
        self.assertEqual(
            (first.identity, second.identity),
            result.declared_normalization_identities,
        )
        self.assertEqual(
            [("prepend", b"payload"), ("append", b"pre:payload")],
            calls,
        )
        self.assertEqual((0, 1), tuple(step.order for step in result.steps))
        self.assertEqual(first.configuration_sha256, result.steps[0].configuration_sha256)
        self.assertEqual(second.configuration_sha256, result.steps[1].configuration_sha256)
        self.assertEqual(_sha256(b"payload"), result.steps[0].input_sha256)
        self.assertEqual(_sha256(b"pre:payload"), result.steps[0].output_sha256)
        self.assertEqual(result.steps[0].output_sha256, result.steps[1].input_sha256)
        self.assertEqual(_sha256(b"pre:payload:post"), result.steps[1].output_sha256)
        self.assertEqual(_sha256(b"pre:payload:post"), result.output_sha256)

        same_configuration = NormalizerRegistration.create(
            "normalizer.prepend",
            "1.0.0",
            {"prefix": "pre:"},
        )
        different_configuration = NormalizerRegistration.create(
            "normalizer.prepend",
            "1.0.0",
            {"prefix": "other:"},
        )
        self.assertEqual(first.identity, same_configuration.identity)
        self.assertNotEqual(first.identity, different_configuration.identity)

        repeated = normalize_bytes(
            b"payload",
            source_identity="artifact:input",
            measurement_identity="metric.normalized",
            registrations=(first, second),
            registry=registry,
        )
        self.assertEqual(result.to_dict(), repeated.to_dict())

    def test_missing_registration_fails_closed_without_raw_fallback(self) -> None:
        registration = NormalizerRegistration.create(
            "normalizer.missing",
            "1.0.0",
            {},
        )

        result = normalize_bytes(
            b"raw-input",
            source_identity="artifact:missing",
            measurement_identity="metric.missing",
            registrations=(registration,),
            registry=NormalizerRegistry(),
        )

        self.assertFalse(result.succeeded)
        self.assertIsNone(result.output_bytes)
        self.assertIsNone(result.output_sha256)
        self.assertEqual("failed", result.availability.state)
        self.assertEqual((registration.identity,), result.declared_normalization_identities)
        self.assertEqual(1, len(result.steps))
        self.assertEqual("NORMALIZER_NOT_REGISTERED", result.steps[0].failure_code)
        self.assertIsNone(result.steps[0].output_sha256)

    def test_execution_failure_stops_pipeline_and_exposes_no_comparison_bytes(
        self,
    ) -> None:
        registry = NormalizerRegistry()
        first = NormalizerRegistration.create("normalizer.first", "1.0.0", {})
        failing = NormalizerRegistration.create("normalizer.fail", "1.0.0", {})
        downstream = NormalizerRegistration.create("normalizer.downstream", "1.0.0", {})
        downstream_calls = 0

        def fail(_value: bytes, _configuration: object) -> bytes:
            raise RuntimeError("expected transform failure")

        def must_not_run(value: bytes, _configuration: object) -> bytes:
            nonlocal downstream_calls
            downstream_calls += 1
            return value

        registry.register(
            first.transform_id,
            first.transform_version,
            lambda value, _configuration: b"x" + value,
        )
        registry.register(failing.transform_id, failing.transform_version, fail)
        registry.register(
            downstream.transform_id,
            downstream.transform_version,
            must_not_run,
        )

        result = normalize_bytes(
            b"raw-input",
            source_identity="artifact:raised",
            measurement_identity="metric.raised",
            registrations=(first, failing, downstream),
            registry=registry,
        )

        self.assertFalse(result.succeeded)
        self.assertIsNone(result.output_bytes)
        self.assertIsNone(result.output_sha256)
        self.assertEqual(0, downstream_calls)
        self.assertEqual(2, len(result.steps))
        self.assertTrue(result.steps[0].succeeded)
        self.assertEqual(_sha256(b"xraw-input"), result.steps[1].input_sha256)
        self.assertEqual("NORMALIZER_EXECUTION_FAILED", result.steps[1].failure_code)
        self.assertIn(
            "RuntimeError: expected transform failure",
            result.steps[1].failure_detail or "",
        )

    def test_invalid_transform_output_fails_closed(self) -> None:
        registry = NormalizerRegistry()
        registration = NormalizerRegistration.create(
            "normalizer.invalid-output",
            "1.0.0",
            {},
        )

        def invalid_output(_value: bytes, _configuration: object) -> bytes:
            return "not-bytes"  # type: ignore[return-value]

        registry.register(
            registration.transform_id,
            registration.transform_version,
            invalid_output,
        )

        result = normalize_bytes(
            b"raw-input",
            source_identity="artifact:invalid-output",
            measurement_identity="metric.invalid-output",
            registrations=(registration,),
            registry=registry,
        )

        self.assertFalse(result.succeeded)
        self.assertIsNone(result.output_bytes)
        self.assertIsNone(result.output_sha256)
        self.assertEqual("NORMALIZER_INVALID_OUTPUT", result.steps[0].failure_code)
        self.assertEqual("failed", result.steps[0].availability.state)

    def test_duplicate_registry_and_pipeline_registrations_are_rejected(self) -> None:
        registry = NormalizerRegistry()
        registration = NormalizerRegistration.create(
            "normalizer.duplicate",
            "1.0.0",
            {},
        )

        registry.register(
            registration.transform_id,
            registration.transform_version,
            lambda value, _configuration: value,
        )
        with self.assertRaises(NormalizerRegistrationError):
            registry.register(
                registration.transform_id,
                registration.transform_version,
                lambda value, _configuration: value,
            )

        with self.assertRaises(NormalizerRegistrationError):
            normalize_bytes(
                b"raw-input",
                source_identity="artifact:duplicate",
                measurement_identity="metric.duplicate",
                registrations=(registration, registration),
                registry=registry,
            )


if __name__ == "__main__":
    unittest.main()
