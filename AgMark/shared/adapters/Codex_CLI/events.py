"""Extract exact response text and measurements from the registered exec JSONL surface."""
from __future__ import annotations

import json
from collections.abc import Callable

from ...evaluation.telemetry import attempt_measurements
from .._contract import sha256_bytes


SOURCE = "Codex CLI stdout JSONL events"
EXTRACTION_VERSION = "2.0.0"
_TOOLS = {"command_execution", "file_change", "mcp_tool_call", "web_search", "collab_tool_call"}
_NON_TOOLS = {"agent_message", "reasoning", "todo_list", "error"}
_TOKEN_FIELDS = {"input_tokens": "input_tokens", "cached_input_tokens": "cached_input_tokens",
                 "output_tokens": "output_tokens", "reasoning_tokens": "reasoning_output_tokens"}
_RULES = {
    "input_tokens": "Codex turn.completed usage.input_tokens; includes cached input.",
    "cached_input_tokens": "Codex turn.completed usage.cached_input_tokens; subset of input.",
    "output_tokens": "Codex turn.completed usage.output_tokens; includes reasoning output.",
    "reasoning_tokens": "Codex turn.completed usage.reasoning_output_tokens; subset of output.",
    "total_tokens": "Input plus output from the same completed turn; cached/reasoning subsets counted once.",
    "cached_input_tokens_subset_of_input_tokens": "true",
    "reasoning_tokens_subset_of_output_tokens": "true",
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def decode_events(raw):
    """Retain a valid prefix after interruption; malformed records cannot prove completeness."""
    events = []
    valid = True
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line.decode("utf-8"), object_pairs_hook=_object)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ValueError("invalid event")
        except (ValueError, UnicodeError, RecursionError):
            valid = False
            break
        events.append(event)
    return events, valid


def extract_response(raw):
    events, valid = decode_events(raw)
    if not valid or not events or events[-1]["type"] != "turn.completed":
        return None
    messages = [event["item"].get("text") for event in events
                if event["type"] == "item.completed" and isinstance(event.get("item"), dict)
                and event["item"].get("type") == "agent_message"]
    if not messages or not isinstance(messages[-1], str):
        return None
    try:
        # No trimming, newline translation, or concatenation of intermediate messages.
        return messages[-1].encode("utf-8") or None
    except UnicodeError:
        return None


class IncrementalResponseDecoder:
    """Project JSONL agent-message snapshots without changing response authority.

    A record is decoded only once its bytes are complete, so pipe reads may split
    UTF-8 code points and JSON records anywhere. Updated item text is a snapshot,
    not a delta. Tool output, reasoning, and process diagnostics never enter this
    projection. Final response extraction remains the separate strict rule above.
    """

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback
        self._pending = bytearray()
        self._valid = True
        self._last_text: str | None = None

    def feed(self, chunk: bytes) -> None:
        if not self._valid:
            return
        self._pending.extend(chunk)
        while True:
            end = self._pending.find(b"\n")
            if end < 0:
                return
            line = bytes(self._pending[:end])
            del self._pending[:end + 1]
            self._record(line)
            if not self._valid:
                self._pending.clear()
                return

    def finish(self) -> None:
        if self._pending and self._valid:
            self._record(bytes(self._pending))
        self._pending.clear()

    def snapshot(self, text: str) -> None:
        if text != self._last_text:
            self._last_text = text
            self._callback(text)

    def _record(self, raw: bytes) -> None:
        events, valid = decode_events(raw)
        if not valid:
            self._valid = False
            return
        for event in events:
            if event["type"] not in {"item.started", "item.updated", "item.completed"}:
                continue
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") != "agent_message":
                continue
            text = item.get("text")
            if isinstance(text, str):
                try:
                    text.encode("utf-8")
                except UnicodeError:
                    continue
                self.snapshot(text)


class ControlledLiveResponseDecoder:
    """Drop live decoding/buffers while disabled, resuming at a JSONL boundary."""
    def __init__(self, callback, control=None):
        self._callback = callback
        self._control = control
        self._revision = None
        self._decoder = None
        self._at_boundary = True
        self._resync = False

    @property
    def revision(self):
        return self._revision

    def _current(self):
        enabled, revision = self._control.snapshot() if self._control is not None else (True, 0)
        if revision != self._revision:
            self._decoder = None
            self._resync = not self._at_boundary
            self._revision = revision
        if not enabled:
            self._decoder = None
            return None
        if self._decoder is None:
            self._decoder = IncrementalResponseDecoder(self._callback)
        return self._decoder

    def feed(self, chunk):
        decoder = self._current()
        self._at_boundary = chunk.endswith(b'\n') if chunk else self._at_boundary
        if decoder is None:
            return
        if self._resync:
            end = chunk.find(b'\n')
            if end < 0:
                return
            chunk = chunk[end + 1:]
            self._resync = False
        decoder.feed(chunk)

    def finish(self):
        decoder = self._current()
        if decoder is not None and not self._resync:
            decoder.finish()

    def snapshot(self, text):
        decoder = self._current()
        if decoder is not None:
            decoder.snapshot(text)


def extract_measurements(raw, *, runtime_version, process_complete):
    events, valid = decode_events(raw)
    source = sha256_bytes(raw)
    starts = sum(event["type"] == "turn.started" for event in events)
    threads = sum(event["type"] == "thread.started" for event in events)
    terminals = [event for event in events if event["type"] in {"turn.completed", "turn.failed"}]
    complete = (valid and process_complete and threads == 1 and starts == 1 and len(terminals) == 1
                and len(events) >= 3 and events[0]["type"] == "thread.started"
                and isinstance(events[0].get("thread_id"), str) and bool(events[0]["thread_id"])
                and events[1]["type"] == "turn.started"
                and events[-1] is terminals[0])
    usage_complete = complete
    tokens = {}
    # A single invocation executes one turn. Ambiguous repeated usage is never pooled.
    if len(terminals) == 1 and terminals[0]["type"] == "turn.completed":
        usage = terminals[0].get("usage")
        if isinstance(usage, dict):
            for role, field in _TOKEN_FIELDS.items():
                number = usage.get(field)
                if type(number) is int and number >= 0:
                    tokens[role] = number
            for child, parent in (("cached_input_tokens", "input_tokens"), ("reasoning_tokens", "output_tokens")):
                if child in tokens and parent in tokens and tokens[child] > tokens[parent]:
                    del tokens[child]
            if "input_tokens" in tokens and "output_tokens" in tokens:
                tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
    tools = {}
    invalid_ids = set()
    for event in events:
        event_type = event["type"]
        if event_type in {"thread.started", "turn.started", "turn.completed", "turn.failed", "error"}:
            continue
        if event_type not in {"item.started", "item.updated", "item.completed"}:
            complete = False
            continue
        item = event.get("item")
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            complete = False
            continue
        kind = item.get("type")
        if not isinstance(kind, str):
            complete = False
            continue
        if kind in _NON_TOOLS:
            continue
        if kind not in _TOOLS:
            complete = False
            continue
        identity = item["id"]
        status = item.get("status")
        # Declined commands were never dispatched, and therefore do not count.
        if status == "declined":
            if identity in tools:
                invalid_ids.add(identity)
            continue
        if kind != "web_search" and (not isinstance(status, str) or status not in {"in_progress", "completed", "failed"}):
            complete = False
            continue
        tool = kind
        if kind == "mcp_tool_call":
            if not all(isinstance(item.get(key), str) and item[key] for key in ("server", "tool")):
                complete = False
                continue
            tool += ":" + item["server"] + ":" + item["tool"]
        elif kind == "collab_tool_call":
            if not isinstance(item.get("tool"), str) or not item["tool"]:
                complete = False
                continue
            tool += ":" + item["tool"]
        outcome = "started"
        if event_type == "item.completed":
            if kind == "web_search":
                outcome = "completed"
            elif status in {"completed", "failed"}:
                outcome = status
                if kind == "command_execution" and type(item.get("exit_code")) is int and item["exit_code"] != 0:
                    outcome = "failed"
                if kind == "mcp_tool_call" and item.get("error") is not None:
                    outcome = "failed"
            else:
                complete = False
        prior = tools.get(identity)
        if prior and (prior["tool_id"] != tool or
                      (prior["status"] in {"completed", "failed"} and outcome in {"completed", "failed"}
                       and prior["status"] != outcome)):
            invalid_ids.add(identity)
            complete = False
            continue
        if not prior or prior["status"] == "started":
            tools[identity] = {"invocation_id": identity, "tool_id": tool, "status": outcome,
                               "evidence_references": [source]}
    for identity in invalid_ids:
        if identity in tools:
            tools[identity]["status"] = "started"
        complete = False
    value = attempt_measurements(runtime_version=runtime_version, source_identity=source,
        tokens=tokens, tool_events=tuple(tools.values()), trace_complete=complete,
        source=SOURCE, counting_rules=_RULES)
    for measurement in value["roles"].values():
        if measurement["value"] is not None:
            measurement["method"] = "registered Codex JSONL extraction@" + EXTRACTION_VERSION
            measurement["details"]["extraction_version"] = EXTRACTION_VERSION
            if not usage_complete:
                measurement["availability"] = "partial"
    return value
