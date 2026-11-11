"""Normalized session and prompt spans and inference timing estimates."""
from __future__ import annotations

from .session_values import _number, _time
from .tool_telemetry import _duration
from .session_facts import TimingFacts

def extract_session_timing(retained):
    model = effort = "unknown"
    timestamps, prompts, prompt_times = [], [], []
    pending = []
    inference, ttft, tbt = [], [], []
    aborted = compacted = 0
    for entry in retained.records:
        stamp = _time(entry.get("timestamp"))
        if stamp is not None:
            timestamps.append(stamp)
        kind, payload = entry["type"], entry["payload"]
        ptype = payload.get("type")
        if kind == "turn_context":
            collaboration = payload.get("collaboration_mode")
            settings = collaboration.get("settings", {}) if isinstance(collaboration, dict) else {}
            if not isinstance(settings, dict):
                settings = {}
            model = payload.get("model") or settings.get("model") or model
            effort = payload.get("effort") or settings.get("reasoning_effort") or effort
        elif kind == "response_item":
            if ptype == "message" and payload.get("role") == "user":
                count = payload.get("prompt_character_count")
                if type(count) is int and count > 0:
                    prompts.append(count)
                    if stamp is not None:
                        prompt_times.append(stamp)
        elif kind == "event_msg":
            if ptype == "turn_aborted":
                aborted += 1
            elif ptype == "compact_summary":
                compacted += 1
            elif ptype == "item_completed":
                item = payload.get("item")
                if not isinstance(item, dict):
                    continue
                duration = _duration(payload)
                if item.get("type") == "Reasoning" and duration is not None:
                    pending.append([duration, 0.0])
                elif item.get("type") == "AgentMessage" and pending and duration is not None:
                    pending[-1][1] += duration
            elif ptype == "token_count":
                info = payload.get("info")
                if not isinstance(info, dict) or not isinstance(info.get("total_token_usage"), dict):
                    continue
                if pending:
                    first, stream = pending.pop(0)
                    inference.append(first + stream)
                    ttft.append(first)
                    last = info.get("last_token_usage")
                    outputs = _number(last.get("output_tokens"), integer=True) if isinstance(last, dict) else None
                    if outputs is not None and outputs > 1 and stream > 0:
                        tbt.append(stream / (outputs - 1))
    return TimingFacts(model, effort, tuple(timestamps), tuple(prompts), tuple(prompt_times),
                       tuple(inference), tuple(ttft), tuple(tbt), compacted, aborted)
