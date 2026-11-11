"""Focused scored-session responsibility conformance."""
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import *
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import _boundary, _request
from AgMark.gui.projection.workspace.results import _measurement_details


class SessionTimingTests(unittest.TestCase):
    def test_prompt_filtering_context_and_weighted_averages_union_across_trials(self):
        a, _ = extract(rollout("a", prompts=("aa", "<environment_context>x</environment_context>", "<turn_aborted>x</turn_aborted>"), tools=tool_call("call_a", duration=100)), "a")
        b, _ = extract(rollout("b", prompts=("bbbb", "cccc", "dddd"), tools=tool_call("call_a", duration=300)+tool_call("call_b", duration=500)), "b")
        results = aggregate([a,b])
        self.assertEqual(4, results["roles"]["prompt_count"]["value"])
        self.assertEqual(3.5, results["roles"]["average_characters_per_prompt"]["value"])
        self.assertEqual(300, results["roles"]["tool_call_avg_duration"]["value"])
        self.assertEqual(1, results["roles"]["distinct_tool_count"]["value"])
        self.assertEqual(16000, results["roles"]["context_window"]["value"])
        self.assertEqual(2, len(results["sessions"]))
        details = _measurement_details(results,"accepted")
        self.assertIn("Thread: call_1; model: model; reasoning: high", details)
        projection = ResultRowProjection("t",1,"accepted","Scored","✓",measurements=results["roles"])
        row = projection.to_table_row()
        from AgMark.gui.views.results import CACHE_METRICS
        self.assertIn("cache_write_input_tokens", row.cells)
        cache_write = results["roles"]["cache_write_input_tokens"]
        self.assertEqual(measurement_text(cache_write), row.cells["cache_write_input_tokens"].text)
        projected = next(metric for section in projection.telemetry_projection["sections"] for metric in section["rows"]
            if metric["id"] == "cache_write_input_tokens")
        for field in ("value", "unit", "availability", "source", "evidence_references"):
            self.assertEqual(cache_write.get(field), projected.get(field), field)
        self.assertIn("cache_write_input_tokens", {original_key for original_key, _, _ in CACHE_METRICS})
        self.assertIn("cache_write_input_tokens", results["roles"])

    def test_inference_timing_matches_reference_rule_with_estimate_label(self):
        timed = [entry("event_msg", {"type": "item_completed", "item": {"type": "Reasoning", "duration": {"secs": 1, "nanos": 0}}}),
                 entry("event_msg", {"type": "item_completed", "item": {"type": "AgentMessage", "duration": {"secs": 0, "nanos": 190000000}}}),
                 entry("event_msg", {"type": "compact_summary"}), entry("event_msg", {"type": "turn_aborted"})]
        measured, _ = extract(rollout(tools=timed))
        roles = measured["extensions"][SESSION_METRICS]["roles"]
        self.assertEqual(1190, roles["total_inference_ms"]["value"])
        self.assertEqual(1000, roles["average_ttft_ms"]["value"])
        self.assertEqual(10, roles["average_tbt_ms"]["value"])
        self.assertIn("(estimate)", measurement_text(roles["total_inference_ms"]))
        self.assertEqual(1, roles["compaction_count"]["value"])
        self.assertEqual(1, roles["turn_aborted"]["value"])

    def test_malformed_optional_model_settings_do_not_discard_session_counters(self):
        for settings in (None, [], "invalid", 7):
            rows = rollout().splitlines()
            rows[1] = json.dumps(entry("turn_context", {
                "collaboration_mode": {"settings": settings}})).encode()
            measured, _ = extract(b"\n".join(rows) + b"\n")
            self.assertEqual(125, measured["roles"]["total_tokens"]["value"])
            session = measured["extensions"][SESSION_METRICS]
            self.assertEqual("unknown", session["model"])
            self.assertEqual("unknown", session["reasoning_effort"])
