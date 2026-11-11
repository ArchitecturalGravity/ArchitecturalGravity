"""Namespaced replay authority, independent availability and arithmetic conformance."""
import copy
from dataclasses import replace
import unittest
from AgMark.shared.software_testing.validation.codex_cache.fixtures import request, replay, configuration
from AgMark.shared.validation.codex_cache.models import ProviderRequestFieldAvailability as Field
from AgMark.shared.validation.codex_cache.metrics import treatment_summary
from AgMark.shared.validation.codex_cache.serialization import admit_validation, validation_bytes

class ProviderRequestValidationConformanceTests(unittest.TestCase):
    def test_cataloged_schema_and_typed_roundtrip(self):
        r = replay()
        self.assertEqual(r.to_dict(), admit_validation(validation_bytes(r)).to_dict())

    def test_unavailable_never_coerces_to_zero_empty_or_false(self):
        for value in (0, "", False):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Field(value, "unavailable", "fixture", "missing", "not_observed")
        r = request(write=None)
        self.assertIsNone(r.fields["cache_write_input_tokens"].value)
        self.assertEqual(60, r.fields["uncached_input_tokens"].value)

    def test_schema_rejects_unknown_identity_fields_and_scored_authority(self):
        for field, value in (("schema_version", "1.0.0"), ("included_in_score", True),
                             ("validation_scope", "exact_scored_request_replay"), ("raw_otlp", {})):
            document = replay().to_dict()
            document[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                admit_validation(document)

    def test_independent_fields_and_missing_to_false_are_rejected(self):
        doc = replay().to_dict()
        doc["requests"][0]["fields"]["after_prewarm"]["value"] = False
        with self.assertRaises(ValueError):
            admit_validation(doc)

    def test_counter_bounds_preserve_source_anomaly(self):
        r = request(input_tokens=10, cached=12)
        self.assertEqual(12, r.fields["cached_input_tokens"].value)
        self.assertIsNone(r.fields["uncached_input_tokens"].value)
        self.assertIn("cached_input_exceeds_input", r.limitations)

    def test_zero_denominators_and_unobserved_warmup(self):
        r = replay(requests=(request(input_tokens=0, cached=0),))
        self.assertIsNone(r.requests[0].fields["cache_read_fraction"].value)
        self.assertIsNone(r.replay_summary.metrics["warmup_reuse_ratio"].field.value)
        t = treatment_summary(generation_id="generation", treatment_id="treatment", replays=(), scored_observation_ids=())
        self.assertIsNone(t.coverage.comparable_coverage.value)

    def test_warmup_reuse_requires_observed_positive_write_and_explicit_pair(self):
        warmup = request(kind="warmup", write=20)
        for paired, expected in ((None, None), (warmup.request_id, 2)):
            r = replay(requests=(warmup, request(2, warmup_request_id=paired)))
            self.assertEqual(expected, r.replay_summary.metrics["warmup_reuse_ratio"].field.value)
        r = replay(requests=(request(kind="warmup", write=0), request(2, warmup_request_id="request-1")))
        self.assertIsNone(r.replay_summary.metrics["warmup_reuse_ratio"].field.value)

    def test_transport_time_cannot_be_lifecycle_duration(self):
        r = request()
        values = dict(r.fields)
        values["request_duration_ms"] = replace(values["request_duration_ms"], method="websocket_send")
        with self.assertRaises(ValueError):
            replace(r, fields=values)
        with self.assertRaises(ValueError):
            replace(r, correlation_method="nearest_timestamp")

    def test_order_and_replay_identity_cannot_merge(self):
        with self.assertRaises(ValueError):
            replay(requests=(request(2),))
        with self.assertRaises(ValueError):
            treatment_summary(generation_id="generation", treatment_id="treatment", replays=(replay(), replay()),
                              scored_observation_ids=("observation-1",))

    def test_treatment_statistics_follow_replay_grain_and_coverage(self):
        a, b = replay(), replay(2, requests=(request(input_tokens=200, cached=100),))
        t = treatment_summary(generation_id="generation", treatment_id="treatment", replays=(a,b),
                              scored_observation_ids=("observation-1", "observation-2", "observation-3"))
        self.assertEqual(2/3, t.coverage.comparable_coverage.value)
        self.assertEqual("partial", t.coverage.comparable_coverage.availability)
        value = t.metrics["first_generation_cached_input_tokens"]["mean"]
        self.assertEqual(70, value.field.value)
        self.assertEqual((2, 2, "mean"), (value.contributors, value.eligible, value.statistic))
        self.assertEqual(t.to_dict(), admit_validation(validation_bytes(t)).to_dict())

    def test_incomplete_generation_field_coverage_is_partial(self):
        r = replay(requests=(request(write=10), request(2, write=None)))
        value = r.replay_summary.metrics["generation_cache_write_input_tokens"]
        self.assertEqual((10, "partial", 1, 2), (value.field.value, value.field.availability, value.contributors, value.eligible))

    def test_tampered_summary_cannot_establish_authority(self):
        doc = replay().to_dict()
        doc["replay_summary"]["metrics"]["generation_input_tokens"]["field"]["value"] = 10000
        with self.assertRaises(ValueError):
            admit_validation(doc)

    def test_forged_configuration_classifications_are_rejected(self):
        for key, value in (("matched_fields", []), ("unavailable_fields", ["model"]),
                           ("status", "unavailable"), ("mismatch_reasons", ["invented"])):
            doc = replay().to_dict()
            doc["configuration_match"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                admit_validation(doc)
        cfg = configuration()
        actual = dict(cfg.observed)
        actual["model"] = replace(actual["model"], value="different")
        with self.assertRaises(ValueError):
            replace(cfg, observed=actual)

    def test_requests_cannot_exceed_capability_authority(self):
        for name in ("input_tokens", "transport", "request_boundaries", "request_duration_ms"):
            doc = replay().to_dict()
            doc["capabilities"]["fields"][name]["status"] = "unavailable"
            with self.subTest(name=name), self.assertRaises(ValueError):
                admit_validation(doc)

    def test_partial_request_observation_does_not_claim_full_replay_totals(self):
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import runtime, capabilities
        from AgMark.shared.validation.codex_cache.metrics import replay_summary
        caps = capabilities()
        values = dict(caps.fields)
        values["request_kind"] = replace(values["request_kind"], status="partial")
        caps = replace(caps, fields=values)
        summary = replay_summary(validation_id="v", validates_observation_id="o", treatment_id="t", repetition_id="1",
            configuration_match=configuration(), runtime_equivalence=runtime(), capabilities=caps,
            requests=(request(),), limitations=("ambiguous_request_completion_ancestry",))
        self.assertEqual("partial", summary.metrics["provider_request_count"].field.availability)
        self.assertEqual("partial", summary.metrics["generation_input_tokens"].field.availability)
        self.assertIsNone(summary.metrics["warmup_request_count"].field.value)

    def test_runtime_cannot_claim_stock_with_patch_or_missing_version(self):
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import runtime
        with self.assertRaises(ValueError):
            replace(runtime(), patch_sha256=runtime().stock_binary_sha256)
        with self.assertRaises(ValueError):
            replace(runtime(), runtime_version=Field.unavailable())

    def test_unregistered_instrumented_runtime_cannot_self_assert_equivalence(self):
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import runtime
        with self.assertRaises(ValueError):
            replace(runtime(), status="instrumented_equivalent", instrumentation="unverified hook",
                    patch_sha256=runtime().stock_binary_sha256, demonstrated_scope=("all",),
                    evidence_references=("sha256:" + "b" * 64,))

    def test_observed_request_kind_and_identity_fields_are_consistent(self):
        values = dict(request().fields)
        values["generate"] = replace(values["generate"], value=False)
        with self.assertRaises(ValueError):
            replace(request(), fields=values)
        values = dict(request().fields)
        values["response_id"] = Field(10, "available", "fixture", "fixture")
        with self.assertRaises(ValueError):
            replace(request(), fields=values)

    def test_public_sequences_are_detached_from_mutable_inputs(self):
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import runtime, capabilities
        refs = ["fixture:original"]
        rt = replace(runtime(), evidence_references=refs)
        cap = replace(capabilities().fields["input_tokens"], evidence_references=refs)
        req = replace(request(), limitations=refs)
        r = replace(replay(), evidence_references=refs)
        t = treatment_summary(generation_id="generation", treatment_id="treatment", replays=(r,),
                              scored_observation_ids=("observation-1",))
        replays = [r]
        t = replace(t, replays=replays, limitations=refs)
        refs.append("fixture:mutation")
        replays.clear()
        self.assertEqual(("fixture:original",), rt.evidence_references)
        self.assertEqual(("fixture:original",), cap.evidence_references)
        self.assertEqual(("fixture:original",), req.limitations)
        self.assertEqual(("fixture:original",), r.evidence_references)
        self.assertEqual((r,), t.replays)
        self.assertEqual(("fixture:original",), t.limitations)

    def test_noncomparable_replays_do_not_contribute_statistics(self):
        from AgMark.shared.validation.codex_cache.comparison import compare_configuration
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import runtime
        cfg = configuration()
        actual = dict(cfg.observed)
        actual["model"] = replace(actual["model"], value="different-model")
        cfg = compare_configuration(cfg.expected, actual, runtime_equivalence=runtime())
        t = treatment_summary(generation_id="generation", treatment_id="treatment", replays=(replay(config=cfg),),
                              scored_observation_ids=("observation-1",))
        self.assertEqual(0, t.coverage.validation_replays_comparable)
        self.assertIsNone(t.metrics["generation_input_tokens"]["mean"].field.value)

if __name__ == "__main__":
    unittest.main()
