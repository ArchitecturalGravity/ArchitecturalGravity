"""Focused scored-session responsibility conformance."""
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import *
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import _boundary, _request


class ToolTelemetryTests(unittest.TestCase):
    def test_call_deduplication_failures_distinct_tools_and_timing_coverage(self):
        calls = tool_call("call_a", duration=100, exit_code=7) + tool_call("call_b", name="apply_patch", duration=300)
        calls += calls[:3]
        value, _ = extract(rollout(tools=calls))
        roles = aggregate([value])["roles"]
        self.assertEqual([2, 1, 2, 400, 200], [roles[r]["value"] for r in ("tool_calls", "failed_tool_calls", "distinct_tool_count", "tool_call_span_duration", "tool_call_avg_duration")])
        untimed, _ = extract(rollout(tools=tool_call("call_a", duration=0) + tool_call("call_b")))
        roles = aggregate([untimed])["roles"]
        self.assertEqual("partial", roles["tool_call_avg_duration"]["availability"])
        self.assertEqual(0, roles["tool_call_avg_duration"]["value"])
        unknown, _ = extract(rollout(tools=[entry("response_item", {"type": "function_call", "name": "x", "call_id": "call_x"})]))
        roles = aggregate([unknown])["roles"]
        self.assertEqual("partial", roles["failed_tool_calls"]["availability"])
        self.assertEqual("available", roles["tool_calls"]["availability"])

    def test_truncated_cancelled_unknown_tools_and_conflicting_outcomes_remain_partial(self):
        for raw, complete in ((rollout()+b'{"type":', True), (rollout(), False)):
            value, _ = extract(raw, complete=complete)
            self.assertEqual("partial", value["roles"]["total_tokens"]["availability"])
            self.assertIsNone(aggregate([value])["roles"]["tool_calls"]["value"])
        unknown, _ = extract(rollout(tools=[entry("response_item", {"type": "future_call", "id": "call_x"})]))
        self.assertFalse(unknown["tool_trace_complete"])
        self.assertEqual("available", unknown["roles"]["total_tokens"]["availability"])
        conflict, _ = extract(rollout(tools=tool_call("call_x", exit_code=0)+tool_call("call_x", exit_code=1)))
        self.assertEqual("partial", aggregate([conflict])["roles"]["failed_tool_calls"]["availability"])

    def test_duration_placeholders_use_bounds_and_missing_samples_remain_unavailable(self):
        for duration in ({}, {"secs": 0, "nanos": 0}):
            calls = tool_call("call_a") + [entry("event_msg", {
                "type": "item_completed", "started_at_ms": 100, "completed_at_ms": 350,
                "item": {"type": "ToolCall", "id": "call_a", "duration": duration}})]
            measured, _ = extract(rollout(tools=calls))
            roles = measured["extensions"][SESSION_METRICS]["roles"]
            self.assertEqual(250, roles["tool_call_span_duration"]["value"])
            self.assertEqual(250, roles["tool_call_avg_duration"]["value"])
        calls = tool_call("call_a") + [entry("event_msg", {
            "type": "item_completed", "item": {"type": "ToolCall", "id": "call_a", "duration": {}}})]
        measured, _ = extract(rollout(tools=calls))
        self.assertIsNone(measured["extensions"][SESSION_METRICS]["roles"]["tool_call_span_duration"]["value"])

    def test_custom_web_and_tool_search_calls_join_outputs_and_deduplicate(self):
        calls = [
            entry("response_item", {"type": "custom_tool_call", "call_id": "call_patch", "name": "apply_patch", "input": "patch"}),
            entry("response_item", {"type": "custom_tool_call_output", "call_id": "call_patch", "output": '{"isError": true}'}),
            entry("response_item", {"type": "web_search_call", "id": "ws_a", "status": "completed"}),
            entry("response_item", {"type": "tool_search_call", "call_id": "call_search"}),
            entry("response_item", {"type": "tool_search_output", "call_id": "call_search", "status": "completed"}),
        ]
        measured, _ = extract(rollout(tools=calls + calls))
        roles = aggregate([measured])["roles"]
        self.assertEqual(3, roles["tool_calls"]["value"])
        self.assertEqual(1, roles["failed_tool_calls"]["value"])
        self.assertEqual(3, roles["distinct_tool_count"]["value"])
        self.assertEqual(["apply_patch", "tool_search", "web_search"], roles["distinct_tool_count"]["details"]["tool_names"])

    def test_orphan_outputs_and_declined_proposals_do_not_establish_invocation_zero(self):
        orphan, _ = extract(rollout(tools=[entry("response_item", {"type": "function_call_output", "call_id": "call_x", "output": "Exit code: 0"})]))
        self.assertIsNone(aggregate([orphan])["roles"]["tool_calls"]["value"])
        declined = [entry("response_item", {"type": "function_call", "call_id": "call_x", "name": "exec_command"}),
                    entry("response_item", {"type": "function_call_output", "call_id": "call_x", "status": "declined"})]
        proposal, _ = extract(rollout(tools=declined))
        roles = aggregate([proposal])["roles"]
        self.assertEqual(0, roles["tool_calls"]["value"])
        self.assertEqual(0, roles["distinct_tool_count"]["value"])
