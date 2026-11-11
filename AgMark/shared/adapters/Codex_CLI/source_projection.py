"""Allowlisted measurement source facts. Raw session/process data is transient."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from .session_values import _number, _time
from .tool_telemetry import _outcome, _duration

REPRESENTATION = "measurement-source/1"
_COUNTERS = {"input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"}

def digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()

def counters(value):
    return {k: v for k, v in value.items() if k in _COUNTERS and _number(v, integer=True) is not None} if isinstance(value, dict) else {}

def project_records(records):
    """Preserve positions and measurable facts, never arbitrary payload fields."""
    origin = next((_time(e.get("timestamp")) for e in records if _time(e.get("timestamp")) is not None), None)
    result = []
    arguments = {}
    for entry in records:
        kind, p = entry["type"], entry["payload"]
        q = {}
        if kind == "session_meta":
            q = {k: p[k] for k in ("id", "session_id", "source", "cli_version", "parent_thread_id", "forked_from_id") if k in p}
            if "source" in q and q["source"] != "exec": q["source"] = "other"
            # Suffixed labels are not audited stock builds. Drop them rather than
            # letting a numeric projection promote custom code to audited provenance.
            if "cli_version" in q and (not isinstance(q["cli_version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", q["cli_version"])): q["cli_version"] = "unknown"
        elif kind == "turn_context":
            settings = p.get("collaboration_mode", {})
            settings = settings.get("settings", {}) if isinstance(settings, dict) else {}
            if not isinstance(settings, dict): settings = {}
            q = {"model": p.get("model", settings.get("model")), "effort": p.get("effort", settings.get("reasoning_effort"))}
        elif kind == "token_usage_record":
            q = {k: p[k] for k in ("thread_id", "turn_id", "session_id", "root_turn_id", "response_id") if k in p}
            q.update({k: counters(p.get(k)) for k in ("usage", "turn_token_usage", "thread_token_usage")})
        elif kind in {"event_msg", "response_item"}:
            ptype = p.get("type")
            allowed = {"task_started", "task_complete", "turn_aborted", "compact_summary", "item_completed", "token_count", "message", "function_call", "custom_tool_call", "web_search_call", "tool_search_call", "function_call_output", "custom_tool_call_output", "tool_search_output"}
            q = {"type": ptype if ptype in allowed else "unrecognized_call" if isinstance(ptype, str) and ptype.endswith("_call") else "unrecognized"}
            if ptype == "token_count":
                info = p.get("info")
                if isinstance(info, dict):
                    q["info"] = {k: counters(info[k]) for k in ("total_token_usage", "last_token_usage") if isinstance(info.get(k), dict)}
                    if _number(info.get("model_context_window"), integer=True) is not None: q["info"]["model_context_window"] = info["model_context_window"]
            elif ptype == "task_started":
                if _number(p.get("model_context_window"), integer=True) is not None: q["model_context_window"] = p["model_context_window"]
            elif ptype == "message":
                if p.get("role") == "user":
                    content = p.get("content")
                    text = "\n".join(c["text"] for c in content if isinstance(c, dict) and isinstance(c.get("text"), str)).strip() if isinstance(content, list) else ""
                    excluded = any(text.startswith("<"+tag+">") and text.endswith("</"+tag+">") for tag in ("environment_context", "turn_aborted"))
                    q.update(role="user", prompt_character_count=len(text) if text and not excluded else 0)
            elif ptype == "item_completed":
                item = p.get("item")
                if isinstance(item, dict):
                    q["item"] = {k: item[k] for k in ("type", "id") if k in item}
                    if q["item"].get("type") not in {"Reasoning", "AgentMessage", "ToolCall"}: q["item"]["type"] = "other"
                    duration = _duration(p)
                    if duration is not None: q.update(started_at_ms=0, completed_at_ms=duration)
            elif ptype in allowed and (ptype.endswith("_call") or ptype.endswith("_output")):
                q.update({k: p[k] for k in ("call_id", "id", "name") if k in p})
                q["status"] = _outcome(p)
                if q["status"] == "proposed": q["status"] = "declined"
                if ptype.endswith("_call"):
                    fingerprint = digest(p.get("arguments", p.get("input")))
                    if fingerprint not in arguments: arguments[fingerprint] = "arguments_" + str(len(arguments) + 1)
                    q["arguments"] = arguments[fingerprint]
        else:
            kind = "unrecognized"
        scalar_fields = {"id", "session_id", "source", "cli_version", "parent_thread_id", "forked_from_id", "model", "effort", "thread_id", "turn_id", "root_turn_id", "response_id", "call_id", "name"}
        q = {k: v for k, v in q.items() if k not in scalar_fields or v is None or isinstance(v, str)}
        if isinstance(q.get("item"), dict):
            q["item"] = {k: v for k, v in q["item"].items() if isinstance(v, str)}
        for key in ("model", "effort", "name"):
            value = q.get(key)
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}", value) or ".." in value):
                q[key] = "unknown"
        row = {"type": kind, "payload": q}
        stamp = _time(entry.get("timestamp"))
        if stamp is not None and origin is not None:
            row["timestamp"] = (datetime(1970, 1, 1, tzinfo=timezone.utc) + (stamp - origin)).isoformat()
        result.append(row)
    return result

def stdout_facts(raw):
    from .events import decode_events
    events, valid = decode_events(raw)
    return {"valid": valid, "events": [{"type": e["type"] if e["type"] in {"thread.started", "turn.started", "turn.completed", "turn.failed"} else "other", **({"thread_id": e["thread_id"]} if e["type"] == "thread.started" and isinstance(e.get("thread_id"), str) else {})} for e in events]}

def validate_records(records):
    """Reject retained fields outside the measurement-source contract."""
    if not isinstance(records, list): raise ValueError("invalid measurement records")
    allowed = {
        "session_meta": {"id", "session_id", "source", "cli_version", "parent_thread_id", "forked_from_id"},
        "turn_context": {"model", "effort"},
        "token_usage_record": {"thread_id", "turn_id", "session_id", "root_turn_id", "response_id", "usage", "turn_token_usage", "thread_token_usage"},
        "event_msg": {"type", "info", "model_context_window", "item", "started_at_ms", "completed_at_ms"},
        "response_item": {"type", "role", "prompt_character_count", "call_id", "id", "name", "status", "arguments"},
        "unrecognized": set(),
    }
    for row in records:
        if not isinstance(row, dict) or set(row) - {"type", "payload", "timestamp"} or row.get("type") not in allowed:
            raise ValueError("invalid measurement source record")
        p = row.get("payload")
        if not isinstance(p, dict) or set(p) - allowed[row["type"]]: raise ValueError("unrelated measurement source fields")
        for key, value in p.items():
            if key in {"usage", "turn_token_usage", "thread_token_usage"}:
                if counters(value) != value: raise ValueError("invalid source counters")
            elif key == "info":
                if not isinstance(value, dict) or set(value) - {"total_token_usage", "last_token_usage", "model_context_window"}: raise ValueError("invalid usage source")
                for k, v in value.items():
                    if (k == "model_context_window" and _number(v, integer=True) is None) or (k != "model_context_window" and counters(v) != v): raise ValueError("invalid usage source")
            elif key == "item":
                if not isinstance(value, dict) or set(value) - {"id", "type"} or any(not isinstance(v, str) for v in value.values()) or ("id" in value and not re.fullmatch(r"call_[1-9][0-9]*", value["id"])): raise ValueError("invalid item source")
            elif key in {"model_context_window", "prompt_character_count", "started_at_ms", "completed_at_ms"}:
                if _number(value) is None: raise ValueError("invalid numeric source")
            elif value is not None and not isinstance(value, str): raise ValueError("invalid source scalar")
            if key in {"model", "effort", "name"} and value is not None and (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}", value) or ".." in value):
                raise ValueError("invalid runtime identity")
            if key == "source" and value not in {"exec", "other"}:
                raise ValueError("invalid source mode")
            if key == "cli_version" and value != "unknown" and (not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value)):
                raise ValueError("invalid source runtime version")
            if key == "role" and value != "user":
                raise ValueError("invalid retained message role")
            if key == "status" and value not in {"started", "completed", "failed", "declined"}:
                raise ValueError("invalid tool outcome")
            if key == "arguments" and (not isinstance(value, str) or not re.fullmatch(r"arguments_[1-9][0-9]*", value)):
                raise ValueError("argument equality must be invocation-local")
            if key == "type" and value not in {"task_started", "task_complete", "turn_aborted", "compact_summary", "item_completed", "token_count", "message", "function_call", "custom_tool_call", "web_search_call", "tool_search_call", "function_call_output", "custom_tool_call_output", "tool_search_output", "unrecognized", "unrecognized_call"}:
                raise ValueError("invalid source event type")
            if key == "item" and value.get("type") not in {"Reasoning", "AgentMessage", "ToolCall", "other"}:
                raise ValueError("invalid retained item type")
            if key in {"id", "session_id", "thread_id", "turn_id", "root_turn_id", "response_id", "parent_thread_id", "forked_from_id", "call_id"} and value is not None and not re.fullmatch(r"call_[1-9][0-9]*", value):
                raise ValueError("source identity must be invocation-local")
        if "timestamp" in row:
            stamp = _time(row["timestamp"])
            if stamp is None or stamp.year not in {1969, 1970}:
                raise ValueError("source time must use a relative epoch")

def source_digest(records, facts, lines):
    return digest({"records": records, "stdout": facts, "lines": lines})
