"""Paired original-run cache accounting, without provider execution."""
import copy
import json
import unittest

from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import extract, rollout, aggregate, entry
from AgMark.shared.evaluation.telemetry.consumption import ATTEMPT_MEASUREMENTS, aggregate_treatment_measurements


class PairedCacheTests(unittest.TestCase):
    def measured(self, thread, input_tokens=100, cached=40, complete=True):
        usage = {"input_tokens": input_tokens}
        if cached is not None:
            usage["cached_input_tokens"] = cached
        return extract(rollout(thread, usage=usage), thread=thread, complete=complete)[0]

    def test_weighted_fraction_uses_same_pairs_and_keeps_missing_coverage(self):
        roles = aggregate([self.measured("a", 100, 40), self.measured("b", 300, 240), self.measured("c", 999, None)])["roles"]
        self.assertEqual(120, roles["uncached_input_tokens"]["value"])
        fraction = roles["cache_read_fraction"]
        self.assertEqual(.7, fraction["value"])
        self.assertEqual("partial", fraction["availability"])
        self.assertEqual(400, fraction["details"]["paired_input_tokens"])
        self.assertEqual(2, fraction["details"]["coverage"]["paired_attempts"])
        self.assertEqual(1, fraction["details"]["coverage"]["excluded_attempts"])
        self.assertEqual(1399, roles["input_tokens"]["value"])

    def test_zero_is_not_missing_and_zero_denominator_is_unavailable(self):
        roles = aggregate([self.measured("a", 100, 0)])["roles"]
        self.assertEqual(100, roles["uncached_input_tokens"]["value"])
        self.assertEqual(0, roles["cache_read_fraction"]["value"])
        roles = aggregate([self.measured("b", 0, 0)])["roles"]
        self.assertEqual(0, roles["uncached_input_tokens"]["value"])
        self.assertEqual("unavailable", roles["cache_read_fraction"]["availability"])
        self.assertIn("zero", roles["cache_read_fraction"]["details"]["reason"])

    def test_failed_retry_attempts_and_missing_planned_observation(self):
        envelopes = [self.measured("failed", 100, 20), self.measured("retry", 200, 100)]
        document = {"observation_id": "o", "accepted_generation_id": "g", "treatment_id": "t",
                    "attempts": [{"attempt": 1, "status": "failed"}, {"attempt": 2, "status": "succeeded"}],
                    "extensions": {"arcgrav.telemetry:attempt-series": {str(i+1): e for i, e in enumerate(envelopes)}}}
        roles = aggregate_treatment_measurements([(document, "artifact")], generation_id="g", planned_observations={"t": 2})["t"]["roles"]
        self.assertEqual(180, roles["uncached_input_tokens"]["value"])
        self.assertEqual(.4, roles["cache_read_fraction"]["value"])
        self.assertEqual("partial", roles["cache_read_fraction"]["availability"])
        self.assertEqual([1, 2], [p["attempt"] for p in roles["cache_read_fraction"]["details"]["inputs"]])

    def test_pair_requires_subset_and_source_provenance(self):
        for change in ("subset", "source", "method", "references"):
            with self.subTest(change=change):
                envelope = self.measured("a")
                roles = envelope["roles"]
                if change == "subset":
                    for key in ("input_tokens", "cached_input_tokens"):
                        roles[key]["details"]["counting_rules"].pop("cached_input_tokens_subset_of_input_tokens", None)
                elif change == "references":
                    roles["cached_input_tokens"]["evidence_references"] = ["different-source"]
                else:
                    roles["cached_input_tokens"][change] = "different"
                result = aggregate([envelope])["roles"]["cache_read_fraction"]
                self.assertEqual("unavailable", result["availability"])
                self.assertEqual(1, result["details"]["coverage"]["excluded_attempts"])

    def test_incompatible_pairs_are_not_pooled(self):
        first, second = self.measured("a"), self.measured("b")
        for role in ("input_tokens", "cached_input_tokens"):
            second["roles"][role]["source"] = "different-source"
        result = aggregate([first, second])["roles"]["cache_read_fraction"]
        self.assertEqual("non_comparable", result["availability"])
        self.assertIsNone(result["details"]["paired_input_tokens"])

    def test_offline_estimates_cannot_supply_counter_derivations(self):
        envelope = self.measured("a")
        for key in ("input_tokens", "cached_input_tokens"):
            envelope["roles"][key]["kind"] = "offline_token_estimate"
        self.assertEqual("unavailable", aggregate([envelope])["roles"]["cache_read_fraction"]["availability"])

    def test_different_pair_extraction_contracts_are_not_pooled(self):
        for field in ("method", "extraction_version"):
            first, second = self.measured("a"), self.measured("b")
            for key in ("input_tokens", "cached_input_tokens"):
                target = second["roles"][key] if field == "method" else second["roles"][key]["details"]
                target[field] = "different"
            self.assertEqual("non_comparable", aggregate([first, second])["roles"]["cache_read_fraction"]["availability"])

    def test_partial_source_stays_partial_and_envelope_is_unchanged(self):
        envelope = self.measured("a", complete=False)
        before = copy.deepcopy(envelope)
        result = aggregate([envelope])["roles"]["cache_read_fraction"]
        self.assertEqual("partial", result["availability"])
        self.assertEqual(before, envelope)

    def test_invalid_subset_and_missing_parent_do_not_become_zero(self):
        for usage in ({"input_tokens": 10, "cached_input_tokens": 11}, {"cached_input_tokens": 10}, {}):
            envelope, _ = extract(rollout("a", usage=usage), thread="a")
            roles = aggregate([envelope])["roles"]
            for key in ("uncached_input_tokens", "cache_read_fraction"):
                self.assertIsNone(roles[key]["value"])
                self.assertEqual("unavailable", roles[key]["availability"])

    def test_final_cumulative_snapshot_is_counted_once(self):
        raw = rollout("a")
        rows = [json.loads(line) for line in raw.splitlines()]
        rows.insert(3, entry("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 50, "cached_input_tokens": 10}}}, 2))
        envelope = extract(b"".join((json.dumps(row)+"\n").encode() for row in rows), thread="a")[0]
        roles = aggregate([envelope])["roles"]
        self.assertEqual(60, roles["uncached_input_tokens"]["value"])
        self.assertEqual(.4, roles["cache_read_fraction"]["value"])


if __name__ == "__main__":
    unittest.main()
