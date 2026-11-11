"""Provider-free conformance tests for shared telemetry semantics."""

from __future__ import annotations

import unittest

from AgMark.shared.evaluation.telemetry import (
    RegisteredEfficiencyFormula,
    TelemetryCompatibility,
    TelemetryCompatibilityError,
    TelemetryError,
    assert_poolable,
    derive_efficiency_ratio,
    estimate_cost,
    measure_bytes,
    measure_latency,
    record_measurement,
    record_unavailable_measurement,
)


_COMPARISON_CONTEXT = "comparison:telemetry-primary"
_COMPATIBILITY_GROUP = "telemetry-compatible-v1"


def _compatibility(**overrides: str) -> TelemetryCompatibility:
    values = {
        "tokenizer_identity": "tokenizer:example@1.0.0",
        "request_representation": "canonical-request-v1",
        "provider_framing": "provider-framing-v1",
        "timestamp_boundary": "not-applicable",
        "usage_source": "provider-reported",
        "pricing_source": "not-applicable",
        "currency": "not-applicable",
        "runner_identity": "runner:deterministic@1.0.0",
        "model_identity": "model:deterministic-v1",
        "execution_boundary_identity": "sha256:" + ("7" * 64),
        "registered_scope": "case",
    }
    values.update(overrides)
    return TelemetryCompatibility(**values)


def _usage(
    *,
    measurement_identity: str = "telemetry.provider.input_tokens",
    value: int | float = 1250,
    compatibility: TelemetryCompatibility | None = None,
    comparison_context: str | None = _COMPARISON_CONTEXT,
):
    return record_measurement(
        measurement_identity=measurement_identity,
        measurement_kind="provider_reported_usage",
        value=value,
        unit="token",
        source="provider_usage",
        method="provider_reported",
        observation_scope="case",
        compatibility_group=_COMPATIBILITY_GROUP,
        compatibility=compatibility or _compatibility(),
        reason="provider retained explicit input-token usage",
        evidence_references=("artifact:provider-usage",),
        comparison_context=comparison_context,
    )


class TelemetryConformanceTests(unittest.TestCase):
    def test_observed_zero_and_unavailable_value_remain_distinct(self) -> None:
        observed_zero = _usage(
            measurement_identity="telemetry.provider.zero_tokens",
            value=0,
            comparison_context=None,
        )
        unavailable = record_unavailable_measurement(
            measurement_identity="telemetry.provider.missing_tokens",
            measurement_kind="provider_reported_usage",
            unit="token",
            source="provider_usage",
            method="provider_reported",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(),
            availability_state="unavailable",
            reason="provider usage evidence was not supplied",
            evidence_references=("artifact:provider-response",),
        )

        self.assertEqual("available", observed_zero.availability.state)
        self.assertEqual(0, observed_zero.value)
        self.assertEqual("unavailable", unavailable.availability.state)
        self.assertIsNone(unavailable.value)

    def test_byte_measurement_is_not_provider_token_usage(self) -> None:
        retained = b"prompt bytes"
        byte_measurement = measure_bytes(
            retained,
            measurement_identity="telemetry.request.bytes",
            source_identity="artifact:request",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(),
            comparison_context=_COMPARISON_CONTEXT,
        )
        repeated = measure_bytes(
            retained,
            measurement_identity="telemetry.request.bytes",
            source_identity="artifact:request",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(),
            comparison_context=_COMPARISON_CONTEXT,
        )
        usage = _usage(value=len(retained))

        self.assertEqual("runner_measured_bytes", byte_measurement.measurement_kind)
        self.assertEqual("byte", byte_measurement.unit)
        self.assertEqual("provider_reported_usage", usage.measurement_kind)
        self.assertEqual("token", usage.unit)
        self.assertEqual(byte_measurement.computation_sha256, repeated.computation_sha256)
        with self.assertRaises(TelemetryCompatibilityError):
            assert_poolable(
                (byte_measurement, usage),
                comparison_context=_COMPARISON_CONTEXT,
            )

    def test_latency_retains_exact_boundaries_and_clock_identity(self) -> None:
        compatibility = _compatibility(
            timestamp_boundary="request_sent->response_retained@monotonic_ns"
        )
        latency = measure_latency(
            measurement_identity="telemetry.latency.end_to_end",
            start_ns=10,
            end_ns=35,
            start_boundary="request_sent",
            end_boundary="response_retained",
            clock_source="monotonic_ns",
            source_identity="artifact:timing",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=compatibility,
        )

        self.assertEqual(25, latency.value)
        self.assertEqual("nanosecond", latency.unit)
        self.assertEqual(
            {
                "start_boundary": "request_sent",
                "end_boundary": "response_retained",
                "clock_source": "monotonic_ns",
                "start_ns": "10",
                "end_ns": "35",
            },
            dict(latency.method_details),
        )

        with self.assertRaises(TelemetryCompatibilityError):
            measure_latency(
                measurement_identity="telemetry.latency.bad-boundary",
                start_ns=10,
                end_ns=35,
                start_boundary="request_sent",
                end_boundary="response_retained",
                clock_source="monotonic_ns",
                source_identity="artifact:timing",
                observation_scope="case",
                compatibility_group=_COMPATIBILITY_GROUP,
                compatibility=_compatibility(timestamp_boundary="different-boundary"),
            )

    def test_estimated_cost_retains_pricing_identity_currency_and_companions(self) -> None:
        usage = _usage(comparison_context=None)
        cost_compatibility = _compatibility(
            pricing_source="pricing:example@2026-09-20",
            currency="USD",
        )
        cost = estimate_cost(
            usage,
            measurement_identity="telemetry.cost.estimated",
            price_per_unit=0.002,
            usage_units_per_price_unit=1000,
            pricing_date="2026-09-20",
            calculation_method="usage_times_registered_unit_price",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=cost_compatibility,
        )

        self.assertEqual("estimated_cost", cost.measurement_kind)
        self.assertEqual("USD", cost.unit)
        self.assertAlmostEqual(0.0025, cost.value)
        self.assertEqual(
            ("usage", "price_per_unit", "usage_units_per_price_unit"),
            tuple(companion.name for companion in cost.companions),
        )
        self.assertEqual("pricing:example@2026-09-20", cost.compatibility.pricing_source)
        self.assertEqual("2026-09-20", dict(cost.method_details)["pricing_date"])

        unavailable_usage = record_unavailable_measurement(
            measurement_identity="telemetry.provider.unavailable_tokens",
            measurement_kind="provider_reported_usage",
            unit="token",
            source="provider_usage",
            method="provider_reported",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(),
            availability_state="unavailable",
            reason="provider did not return usage",
            evidence_references=("artifact:provider-response",),
        )
        with self.assertRaises(TelemetryError):
            estimate_cost(
                unavailable_usage,
                measurement_identity="telemetry.cost.invalid",
                price_per_unit=0.002,
                usage_units_per_price_unit=1000,
                pricing_date="2026-09-20",
                calculation_method="usage_times_registered_unit_price",
                observation_scope="case",
                compatibility_group=_COMPATIBILITY_GROUP,
                compatibility=cost_compatibility,
            )

    def test_registered_efficiency_retains_formula_and_companion_values(self) -> None:
        usage = _usage(comparison_context=None)
        formula = RegisteredEfficiencyFormula(
            registration_identity="registration:efficiency-primary",
            formula_id="arcgrav.efficiency.score_per_token",
            formula_version="1.0.0",
            numerator_role="score",
            denominator_role="input_tokens",
            output_unit="score/token",
        )
        efficiency = derive_efficiency_ratio(
            measurement_identity="telemetry.efficiency.score_per_token",
            numerator_value=0.8,
            numerator_unit="score",
            numerator_source_identity="score-artifact:primary",
            denominator=usage,
            formula=formula,
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(),
        )

        self.assertEqual("efficiency", efficiency.measurement_kind)
        self.assertEqual(formula.identity, efficiency.method)
        self.assertEqual(("score", "input_tokens"), tuple(c.name for c in efficiency.companions))
        self.assertAlmostEqual(0.8 / 1250, efficiency.value)

        with self.assertRaises(TelemetryError):
            derive_efficiency_ratio(
                measurement_identity="telemetry.efficiency.undefined",
                numerator_value=0.8,
                numerator_unit="score",
                numerator_source_identity="score-artifact:primary",
                denominator=_usage(
                    measurement_identity="telemetry.provider.zero_denominator",
                    value=0,
                    comparison_context=None,
                ),
                formula=formula,
                observation_scope="case",
                compatibility_group=_COMPATIBILITY_GROUP,
                compatibility=_compatibility(),
            )

    def test_pooling_requires_complete_compatible_context(self) -> None:
        first = record_measurement(
            measurement_identity="telemetry.generic.first",
            measurement_kind="generic_numeric",
            value=1,
            unit="count",
            source="retained_observation",
            method="exact_count",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(),
            reason="retained exact count",
            evidence_references=("artifact:first",),
            comparison_context=_COMPARISON_CONTEXT,
        )
        second = record_measurement(
            measurement_identity="telemetry.generic.second",
            measurement_kind="generic_numeric",
            value=2,
            unit="count",
            source="retained_observation",
            method="exact_count",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(),
            reason="retained exact count",
            evidence_references=("artifact:second",),
            comparison_context=_COMPARISON_CONTEXT,
        )

        first_pool = assert_poolable(
            (first, second),
            comparison_context=_COMPARISON_CONTEXT,
        )
        second_pool = assert_poolable(
            (first, second),
            comparison_context=_COMPARISON_CONTEXT,
        )
        self.assertEqual(first_pool, second_pool)
        self.assertTrue(first_pool.startswith("sha256:"))

        incompatible_model = record_measurement(
            measurement_identity="telemetry.generic.other-model",
            measurement_kind="generic_numeric",
            value=3,
            unit="count",
            source="retained_observation",
            method="exact_count",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(model_identity="model:other"),
            reason="retained exact count",
            evidence_references=("artifact:other-model",),
            comparison_context=_COMPARISON_CONTEXT,
        )
        with self.assertRaises(TelemetryCompatibilityError):
            assert_poolable(
                (first, incompatible_model),
                comparison_context=_COMPARISON_CONTEXT,
            )

        non_comparable = record_unavailable_measurement(
            measurement_identity="telemetry.generic.non-comparable",
            measurement_kind="generic_numeric",
            unit="count",
            source="retained_observation",
            method="exact_count",
            observation_scope="case",
            compatibility_group=_COMPATIBILITY_GROUP,
            compatibility=_compatibility(),
            availability_state="non_comparable",
            reason="comparison context is incompatible",
            evidence_references=("artifact:non-comparable",),
            comparison_context=_COMPARISON_CONTEXT,
        )
        with self.assertRaises(TelemetryCompatibilityError):
            assert_poolable(
                (first, non_comparable),
                comparison_context=_COMPARISON_CONTEXT,
            )


if __name__ == "__main__":
    unittest.main()
