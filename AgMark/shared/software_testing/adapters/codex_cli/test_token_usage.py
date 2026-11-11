"""Focused scored-session responsibility conformance."""
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import *
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import _boundary, _request


class TokenUsageTests(unittest.TestCase):
    def test_first_cache_snapshot_raw_counters_deltas_and_cumulative_values_are_separate(self):
        rows = rollout().splitlines()
        infos = [{"total_token_usage": {"input_tokens": 1, "cached_input_tokens": True}},
                 {"total_token_usage": {"input_tokens": 80, "cached_input_tokens": 10, "cache_write_input_tokens": 2, "future_counter": 7},
                  "last_token_usage": {"cached_input_tokens": 10}},
                 {"total_token_usage": {"cached_input_tokens": 30}},
                 {"last_token_usage": {"cached_input_tokens": 999}}]
        extras = [(json.dumps(entry("event_msg", {"type": "token_count", "info": info}))+"\n").encode() for info in infos]
        raw = b"\n".join(rows[:-2])+b"\n\n"+b"".join(extras)+b"\n".join(rows[-2:])+b"\n"
        value, record = extract(raw)
        diagnostics = record["cache_telemetry"]
        self.assertEqual("available", diagnostics["availability"])
        self.assertEqual("unavailable", diagnostics["request_correlation"])
        self.assertEqual(1, diagnostics["first_token_count_snapshot"])
        snapshots = diagnostics["snapshots"]
        expected_info = copy.deepcopy(infos[1])
        expected_info["total_token_usage"].pop("future_counter")
        self.assertEqual(expected_info, snapshots[1]["info"])
        self.assertNotIn("future_counter", json.dumps(record))
        self.assertEqual({"cached_input_tokens": 20, "cache_write_input_tokens": None}, snapshots[2]["change_from_previous_usable_snapshot"])
        self.assertEqual({"cached_input_tokens": 10, "cache_write_input_tokens": None}, snapshots[-1]["change_from_previous_usable_snapshot"])
        self.assertEqual(json.loads(raw.splitlines()[snapshots[1]["line_number"]-1])["payload"]["info"], infos[1])
        self.assertEqual(40, value["roles"]["cached_input_tokens"]["value"])
        self.assertEqual(3, value["extensions"][SESSION_METRICS]["roles"]["cache_write_input_tokens"]["value"])
        partial, partial_record = extract(raw+b'{"type":')
        self.assertEqual("partial", partial_record["cache_telemetry"]["availability"])
        self.assertEqual("partial", partial["roles"]["cached_input_tokens"]["availability"])

    def test_missing_cache_counters_are_unavailable_and_counter_decreases_are_retained(self):
        _, record = extract(rollout(usage={"input_tokens": 100}))
        self.assertEqual("unavailable", record["cache_telemetry"]["availability"])
        self.assertIsNone(record["cache_telemetry"]["first_token_count_snapshot"])
        rows = rollout().splitlines()
        earlier = json.dumps(entry("event_msg", {"type": "token_count", "info": {"total_token_usage": {"cached_input_tokens": 50, "cache_write_input_tokens": 4}}})).encode()
        _, record = extract(b"\n".join(rows[:-2]+[earlier]+rows[-2:])+b"\n")
        self.assertEqual({"cached_input_tokens": -10, "cache_write_input_tokens": -1}, record["cache_telemetry"]["snapshots"][-1]["change_from_previous_usable_snapshot"])
        zero, record = extract(rollout(usage={"cached_input_tokens": 0}))
        self.assertEqual(0, record["cache_telemetry"]["first_token_count_snapshot"])

    def test_final_cumulative_snapshot_and_explicit_total_override_stdout(self):
        rows = rollout().splitlines()
        earlier = entry("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10000, "cached_input_tokens": 5000, "output_tokens": 2000, "total_tokens": 12000}}})
        raw = b"\n".join(rows[:-2] + [json.dumps(earlier).encode(), rows[-2], rows[-2], rows[-1]]) + b"\n"
        value, record = extract(raw)
        self.assertEqual([125, 100, 40, 20, 5], [value["roles"][r]["value"] for r in ("total_tokens", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")])
        self.assertEqual(3, value["extensions"][SESSION_METRICS]["roles"]["cache_write_input_tokens"]["value"])
        self.assertEqual(record["sha256"], value["source_identity"])
        validate_attempt_measurements(value)

    def test_missing_component_is_not_zero_or_backfilled_from_previous_snapshot(self):
        value, _ = extract(rollout(usage={"input_tokens": 0, "total_tokens": 0}))
        self.assertEqual(0, value["roles"]["total_tokens"]["value"])
        self.assertIsNone(value["roles"]["output_tokens"]["value"])
        self.assertIsNone(value["extensions"][SESSION_METRICS]["roles"]["cache_write_input_tokens"]["value"])
        for usage in ({"input_tokens": True}, {"input_tokens": -1}, {"input_tokens": float("inf")}, {"input_tokens": 1.5}):
            measured, _ = extract(rollout(usage=usage))
            self.assertIsNone(measured["roles"]["input_tokens"]["value"])
