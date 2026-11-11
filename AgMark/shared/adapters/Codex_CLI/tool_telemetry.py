"""Normalized tool identities, outcomes, duration samples and coverage."""
from __future__ import annotations

import json
import re
from .session_values import _number
from .session_facts import ToolFacts
_CALLS = {"function_call", "custom_tool_call", "web_search_call", "tool_search_call"}
_OUTPUTS = {"function_call_output", "custom_tool_call_output", "tool_search_output"}
_SUCCESS = {"completed", "success", "succeeded"}
_FAILURE = {"failed", "error", "errored", "cancelled", "canceled"}
_EXIT = re.compile(r"(?:Process exited with code|Exit code:)\s+(-?\d+)")


def _duration(payload):
    item = payload.get("item", {})
    duration = item.get("duration") if isinstance(item, dict) else None
    item_duration = None
    if isinstance(duration, dict) and any(key in duration for key in ("secs", "nanos")):
        secs, nanos = _number(duration.get("secs", 0)), _number(duration.get("nanos", 0))
        if secs is not None and nanos is not None:
            item_duration = secs * 1000 + nanos / 1_000_000
            if item_duration > 0:
                return item_duration
    start, end = _number(payload.get("started_at_ms")), _number(payload.get("completed_at_ms"))
    return end - start if start is not None and end is not None and end >= start else item_duration


def _outcome(payload):
    status = payload.get("status")
    if status == "declined":
        return "proposed"
    if isinstance(status, str) and status.lower() in _FAILURE:
        return "failed"
    output = payload.get("output")
    code = payload.get("exit_code")
    if isinstance(output, dict):
        code = output.get("exit_code", code)
        status = output.get("status", status)
    if isinstance(output, str):
        match = _EXIT.search(output)
        if match:
            code = int(match[1])
        else:
            try:
                obj = json.loads(output)
                if isinstance(obj, dict):
                    code = obj.get("exit_code", code)
                    status = obj.get("status", status)
                    if obj.get("isError") is True:
                        return "failed"
            except ValueError:
                pass
    if payload.get("error") is not None or payload.get("isError") is True:
        return "failed"
    if type(code) is int:
        return "failed" if code else "completed"
    if isinstance(status, str):
        if status.lower() in _FAILURE:
            return "failed"
        if status.lower() in _SUCCESS:
            return "completed"
    return "started"



def extract_tool_telemetry(retained):
    source, complete = retained.source, retained.source_complete
    tools, signatures, outcomes, tool_durations = {}, {}, {}, {}
    invalid_outcomes = set()
    output_ids = set()
    for entry in retained.records:
        kind, payload = entry["type"], entry["payload"]
        ptype = payload.get("type")
        if kind == "response_item":
            if not isinstance(ptype, str):
                complete = False
            if ptype in _CALLS:
                identity = payload.get("call_id") or payload.get("id")
                name = payload.get("name") if ptype in {"function_call", "custom_tool_call"} else {"web_search_call": "web_search", "tool_search_call": "tool_search"}[ptype]
                if not isinstance(identity, str) or not identity or not isinstance(name, str) or not name:
                    complete = False
                    continue
                signature = (ptype, name, payload.get("arguments", payload.get("input")))
                if identity in signatures and signatures[identity] != signature:
                    complete = False
                    invalid_outcomes.add(identity)
                signatures[identity] = signature
                tools[identity] = name
                outcome = _outcome(payload)
                if outcome != "started":
                    outcomes.setdefault(identity, set()).add(outcome)
            elif ptype in _OUTPUTS:
                identity = payload.get("call_id") or payload.get("id")
                if not isinstance(identity, str) or not identity:
                    complete = False
                    continue
                output_ids.add(identity)
                outcome = _outcome(payload)
                if isinstance(identity, str) and outcome != "started":
                    outcomes.setdefault(identity, set()).add(outcome)
            elif isinstance(ptype, str) and ptype.endswith("_call"):
                complete = False
        elif kind == "event_msg" and ptype == "item_completed":
            item = payload.get("item")
            if not isinstance(item, dict):
                continue
            duration = _duration(payload)
            if isinstance(item.get("id"), str) and item["id"].startswith(("call_", "ws_")) and duration is not None:
                prior = tool_durations.get(item["id"])
                if prior is not None and prior != duration:
                    complete = False
                tool_durations[item["id"]] = duration
    events = []
    if output_ids.difference(tools):
        complete = False
    for identity, name in tools.items():
        states = outcomes.get(identity, set())
        if len(states) > 1 or identity in invalid_outcomes:
            complete = False
            status = "started"
        else:
            status = next(iter(states), "started")
        events.append({"invocation_id": identity, "tool_id": name, "status": status, "evidence_references": [source]})
    actual_tools = {e["invocation_id"]: e["tool_id"] for e in events if e["status"] != "proposed"}
    return ToolFacts(tuple(events), actual_tools, tool_durations, complete)
