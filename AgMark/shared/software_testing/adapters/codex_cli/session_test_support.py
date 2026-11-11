"""Session identity, rollout accounting and retained reconstruction conformance."""
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from AgMark.shared.adapters.Codex_CLI import CodexCliRunner, load_registration
from AgMark.shared.adapters.Codex_CLI.runner import _SubprocessTransport
from AgMark.shared.adapters.Codex_CLI.session import (
    SESSION_RECORD, extract_session_measurements, returned_thread_id,
)
from AgMark.shared.adapters.Codex_CLI.session_capture import read_session, session_root
from AgMark.shared.adapters.execution import validate_retained_parity_observation
from AgMark.shared.evaluation.telemetry.consumption import (
    ATTEMPT_MEASUREMENTS, aggregate_treatment_measurements, validate_attempt_measurements,
)
from AgMark.shared.evaluation.telemetry.session_metrics import SESSION_METRICS
from AgMark.gui.views.results import measurement_text, RESULTS_COLUMNS, ResultRowProjection
from AgMark.gui.projection.workspace.results import _measurement_details
from AgMark.shared.software_testing.adapters.codex_cli.test_runner import _boundary, _request, FakeCodexTransport


def entry(kind, payload, second=0):
    return {"timestamp": f"2026-10-03T12:00:{second:02d}Z", "type": kind, "payload": payload}


def rollout(thread="trial", *, prompts=("abcd",), tools=(), usage=None):
    rows = [entry("session_meta", {"id": thread, "session_id": thread, "source": "exec", "cli_version": "0.159.0"}), entry("turn_context", {"model": "model", "effort": "high"}),
            entry("event_msg", {"type": "task_started", "model_context_window": 8192})]
    for i, text in enumerate(prompts):
        rows.append(entry("response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}, i))
    rows.extend(tools)
    rows.append(entry("event_msg", {"type": "token_count", "info": {
        "total_token_usage": usage if usage is not None else {"input_tokens": 100, "cached_input_tokens": 40,
            "cache_write_input_tokens": 3, "output_tokens": 20, "reasoning_output_tokens": 5, "total_tokens": 125},
        "last_token_usage": {"output_tokens": 20}, "model_context_window": 16000}}, 10))
    rows.append(entry("event_msg", {"type": "task_complete"}, 11))
    return b"".join((json.dumps(e) + "\n").encode() for e in rows)


def stdout(thread="trial"):
    return b"".join((json.dumps(e)+"\n").encode() for e in (
        {"type": "thread.started", "thread_id": thread}, {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "answer", "type": "agent_message", "text": "answer"}},
        {"type": "turn.completed", "usage": {"input_tokens": 99999, "output_tokens": 99999}}))


def extract(raw=None, thread="trial", complete=True):
    raw = rollout(thread) if raw is None else raw
    record = {"availability": "retained", "thread_id": thread, "content_base64": base64.b64encode(raw).decode()}
    return extract_session_measurements(record, stdout(thread), runtime_version="0.159.0", process_complete=complete)


def aggregate(envelopes):
    documents = []
    for i, envelope in enumerate(envelopes):
        document = {"observation_id": f"observation-{i}", "accepted_generation_id": "g", "treatment_id": "t",
                    "attempts": [{"attempt": 1}], "extensions": {ATTEMPT_MEASUREMENTS: envelope}}
        documents.append((document, f"evidence-{i}"))
    return aggregate_treatment_measurements(documents, generation_id="g", planned_observations={"t": len(documents)})["t"]


def tool_call(identity, name="exec_command", duration=None, exit_code=0):
    items = [entry("response_item", {"type": "function_call", "name": name, "call_id": identity}),
             entry("response_item", {"type": "function_call_output", "call_id": identity, "output": f"Process exited with code {exit_code}"})]
    if duration is not None:
        items.append(entry("event_msg", {"type": "item_completed", "item": {"id": identity, "type": "ToolCall", "duration": {"secs": 0, "nanos": int(duration*1_000_000)}}}))
    return items


