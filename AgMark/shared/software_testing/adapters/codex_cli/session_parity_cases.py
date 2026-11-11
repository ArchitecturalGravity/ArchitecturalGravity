"""Inputs for independent serialized scored-session compatibility evidence."""
import base64
import itertools
import json
from pathlib import Path


def cases():
    def row(kind, payload, second=0):
        return {"type": kind, "payload": payload, "timestamp": f"2026-10-03T12:00:{second:02d}Z"}
    out = b'\n'.join(json.dumps(e).encode() for e in (
        {"type": "thread.started", "thread_id": "parity"}, {"type": "turn.started"},
        {"type": "turn.completed", "usage": {"input_tokens": 99999}})) + b'\n'
    tools = [row("response_item", {"type": "function_call", "call_id": "call_1", "name": "exec_command", "arguments": "{}"}),
             row("response_item", {"type": "function_call_output", "call_id": "call_1", "output": "Exit code: 7"}),
             row("event_msg", {"type": "item_completed", "item": {"id": "call_1", "duration": {"secs": 0, "nanos": 250000000}}})]
    variants = [[], tools, tools + tools, tools + [row("response_item", {"type": "function_call_output", "call_id": "call_1", "output": "Exit code: 0"})],
                [row("response_item", {"type": "future_call", "id": "unknown"})],
                [row("response_item", {"type": "function_call_output", "call_id": "orphan"})],
                [row("event_msg", {"type": "item_completed", "item": {"type": "Reasoning", "duration": {"secs": 1}}}),
                 row("event_msg", {"type": "item_completed", "item": {"type": "AgentMessage", "duration": {"nanos": 190000000}}})]]
    usages = [{"input_tokens": 100, "cached_input_tokens": 40, "cache_write_input_tokens": 3, "output_tokens": 20, "reasoning_output_tokens": 5, "total_tokens": 125},
              {"input_tokens": 0, "total_tokens": 0}, {"input_tokens": True, "cached_input_tokens": -1},
              {"input_tokens": 3, "cached_input_tokens": 8, "output_tokens": 2, "reasoning_output_tokens": 6}, {}]
    for index, (version, complete, usage, extra) in enumerate(itertools.product(("4.0.0", "4.0.0"), (False, True), usages, variants)):
        rows = [row("session_meta", {"id": "parity", "session_id": "parity", "source": "exec", "cli_version": "0.159.0"}),
                row("turn_context", {"model": "model", "effort": "high"}),
                row("event_msg", {"type": "task_started", "model_context_window": 8192}),
                row("response_item", {"type": "message", "role": "user", "content": [{"text": "abcd"}]}),
                *extra,
                row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"cached_input_tokens": 50, "cache_write_input_tokens": 4}}}, 5),
                row("event_msg", {"type": "token_count", "info": {"total_token_usage": usage, "last_token_usage": {"output_tokens": 20}, "model_context_window": 16000}}, 10),
                row("event_msg", {"type": "task_complete"}, 11)]
        raw = b'\n'.join(json.dumps(e).encode() for e in rows) + b'\n'
        for suffix, content, identity in (("valid", raw, "parity"), ("truncated", raw + b'{"type":', "parity"), ("mismatch", raw, "other")):
            yield f"matrix-{index}-{suffix}", {"availability": "retained", "thread_id": identity, "extraction_version": version, "content_base64": base64.b64encode(content).decode()}, out, "0.159.0", complete
    for record in ({"availability": "unavailable", "reason": "missing"}, {"availability": "retained", "content_base64": "!"}):
        yield record.get("reason", "invalid-base64"), {**record, "extraction_version": "4.0.0"}, out, "0.159.0", True
