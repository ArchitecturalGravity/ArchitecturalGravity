"""Structured Codex capture, availability and Results conformance without a provider."""
import base64
import json
import os
import unittest

from AgMark.shared.adapters.Codex_CLI.events import extract_measurements, extract_response
from AgMark.shared.adapters.Codex_CLI import CodexCliRunner
from AgMark.shared.adapters.execution import validate_retained_parity_observation
from AgMark.shared.evaluation.telemetry.consumption import aggregate_treatment_measurements
from AgMark.gui.views.results import measurement_text
from AgMark.shared.software_testing.adapters.codex_cli.test_runner import FakeCodexTransport, _boundary, _request


def stream(items=(), usage=None, terminal="turn.completed"):
    events = [{"type": "thread.started", "thread_id": "thread"}, {"type": "turn.started"}]
    events.extend(items)
    events.append({"type": "item.completed", "item": {"type": "agent_message", "id": "answer", "text": "  exact\r\nλ\n"}})
    events.append({"type": terminal, "usage": usage if usage is not None else {
        "input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 20, "reasoning_output_tokens": 5}})
    return b"".join((json.dumps(e, ensure_ascii=False) + "\n").encode() for e in events)


def tool(kind, identity, status="completed", event="item.completed", **extra):
    return {"type": event, "item": {"type": kind, "id": identity, "status": status, **extra}}


class StructuredEventsTests(unittest.TestCase):
    def measure(self, raw, complete=True):
        return extract_measurements(raw, runtime_version="0.159.0", process_complete=complete)

    def aggregate(self, measured):
        doc = {"accepted_generation_id": "generation", "observation_id": "observation", "treatment_id": "treatment",
               "attempts": [{"attempt": 1}], "extensions": {"arcgrav.telemetry:attempt-measurements": measured}}
        return aggregate_treatment_measurements([(doc, "sha256:" + "a" * 64)], generation_id="generation",
            planned_observations={"treatment": 1})["treatment"]["roles"]

    def test_components_subset_total_exact_response_and_zero_calls(self):
        raw = stream()
        self.assertEqual(b"  exact\r\n\xce\xbb\n", extract_response(raw))
        roles = self.aggregate(self.measure(raw))
        self.assertEqual([120, 100, 40, 20, 5, 0, 0], [roles[k]["value"] for k in (
            "total_tokens", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "tool_calls", "failed_tool_calls")])
        self.assertEqual("0", measurement_text(roles["tool_calls"]))
        self.assertEqual("—", measurement_text(roles["cost"]))
        self.assertEqual("runtime_counter", roles["input_tokens"]["kind"])

    def test_invocations_deduplicate_and_classify_failures(self):
        start = tool("command_execution", "command", "in_progress", "item.started")
        end = tool("command_execution", "command", exit_code=7)
        raw = stream([start, end, end, tool("mcp_tool_call", "mcp", server="server", tool="tool", error={"message": "error"}),
            tool("file_change", "patch", "failed"), tool("web_search", "search"),
            tool("collab_tool_call", "collab", tool="wait"), tool("command_execution", "declined", "declined"),
            tool("todo_list", "plan"), tool("reasoning", "reason")])
        roles = self.aggregate(self.measure(raw))
        self.assertEqual(5, roles["tool_calls"]["value"])
        self.assertEqual(3, roles["failed_tool_calls"]["value"])

    def test_missing_independent_components_are_not_zero(self):
        roles = self.aggregate(self.measure(stream(usage={"input_tokens": 12, "cached_input_tokens": 0})))
        self.assertEqual(12, roles["input_tokens"]["value"])
        self.assertEqual(0, roles["cached_input_tokens"]["value"])
        self.assertIsNone(roles["total_tokens"]["value"])
        self.assertIsNone(roles["output_tokens"]["value"])

    def test_incomplete_unknown_and_conflicting_traces_preserve_availability(self):
        for raw, complete in ((stream() + b'{"type":', True), (stream(), False),
                              (stream([tool("future_tool", "future")]), True), (b"", False),
                              (stream([tool(["invalid"], "future")]), True),
                              (stream([tool("command_execution", "future", status=["invalid"])]), True)):
            with self.subTest(raw=raw[-50:], complete=complete):
                value = self.measure(raw, complete)
                self.assertFalse(value["tool_trace_complete"])
                self.assertIsNone(self.aggregate(value)["tool_calls"]["value"])
        value = self.measure(stream([tool("command_execution", "c", "in_progress", "item.started")]), False)
        roles = self.aggregate(value)
        self.assertEqual(1, roles["tool_calls"]["value"])
        self.assertEqual("partial", roles["failed_tool_calls"]["availability"])
        value = self.measure(stream([tool("command_execution", "c"), tool("command_execution", "c", "failed")]))
        self.assertFalse(value["tool_trace_complete"])
        self.assertEqual("partial", self.aggregate(value)["failed_tool_calls"]["availability"])
        value = self.measure(stream([tool("future_tool", "future")]))
        self.assertEqual("available", value["roles"]["input_tokens"]["availability"])

    def test_malformed_usage_duplicates_and_messages(self):
        value = self.measure(stream(usage={"input_tokens": True, "cached_input_tokens": -1, "output_tokens": 2.5}))
        self.assertTrue(all(m["value"] is None for m in value["roles"].values()))
        self.assertIsNone(extract_response(b'{"type":"item.completed","type":"turn.completed"}\n'))
        self.assertIsNone(extract_response(stream() + b"broken"))
        self.assertIsNone(extract_response(b"plain text response"))
        raw = stream() + json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1}}).encode()
        self.assertIsNone(self.measure(raw)["roles"]["input_tokens"]["value"])

    @unittest.skipUnless(os.name == "posix", "Registered mock launcher is POSIX")
    def test_real_mock_executable_exposes_synthetic_components_and_zero_tools(self):
        from pathlib import Path
        from AgMark.shared.software_testing.adapters.codex_cli.fixtures.codex_protocol import load_registration
        from AgMark.shared.software_testing.adapters.codex_cli.fixtures.codex_protocol.protocol.cli import BASE_MODEL_ID
        from AgMark.shared.mock_model.protocol import DEFAULT_RUNTIME_VERSION
        registration = load_registration()
        executable = Path(__file__).resolve().parents[5] / "AgMark/shared/software_testing/adapters/codex_cli/fixtures/codex_protocol/arcgrav-mock-model-cli"
        boundary = _boundary(runner_id=registration["registration_id"], runner_version=registration["registration_version"],
            runtime_version=DEFAULT_RUNTIME_VERSION, provider="AgMark Mock Model", model_id=BASE_MODEL_ID)
        runner = CodexCliRunner(registration=registration, executable_resolver=lambda _: str(executable), platform_name="posix")
        self.addCleanup(runner.close)
        doc = runner.execute(_request(boundary))
        self.assertEqual("completed", doc["terminal_status"], doc)
        validate_retained_parity_observation(doc)
        measured = doc["extensions"]["arcgrav.telemetry:attempt-measurements"]
        roles = self.aggregate(measured)
        self.assertEqual([42, 40, 10, 2, 0, 0], [roles[k]["value"] for k in
            ("total_tokens", "input_tokens", "cached_input_tokens", "output_tokens", "tool_calls", "failed_tool_calls")])
        self.assertFalse(doc["extensions"]["arcgrav.runner:execution"]["submission"]["external_provider"])

    def test_production_native_and_wsl_capture_and_results(self):
        raw = stream([tool("command_execution", "c", "failed", exit_code=1)])
        for mode in ("native", "wsl"):
            for code in (0, 23):
                with self.subTest(mode=mode, code=code):
                    transport = FakeCodexTransport(response=raw, actual_returncode=code, structured_output=True)
                    runner = CodexCliRunner(transport=transport, executable_resolver=lambda _: "/controlled/codex",
                        platform_name="nt" if mode == "wsl" else "posix")
                    self.addCleanup(runner.close)
                    doc = runner.execute(_request(_boundary(launch_mode=mode)))
                    validate_retained_parity_observation(doc)
                    self.assertNotIn("arcgrav.runner:process_stdout_base64", doc["extensions"])
                    measured = doc["extensions"]["arcgrav.telemetry:attempt-measurements"]
                    roles = self.aggregate(measured)
                    self.assertEqual("100", measurement_text(roles["input_tokens"]))
                    self.assertEqual("1", measurement_text(roles["failed_tool_calls"]))
                    if code == 0:
                        self.assertEqual(extract_response(raw), base64.b64decode(doc["extensions"]["openai.codex-cli:response_base64"]))
                    else:
                        self.assertEqual("failed", doc["terminal_status"])
                    command = transport.calls[-1]["argv"]
                    self.assertTrue("--json" in command or any("--json" in part for part in command))
