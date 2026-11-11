"""Final cumulative token facts and retained cache snapshots."""
from __future__ import annotations

from .session_values import _number
from .session_facts import TOKEN_FIELDS, TokenFacts
_CACHE_FIELDS = ("cached_input_tokens", "cache_write_input_tokens")

def _cache_snapshots(records, line_numbers, source, complete):
    """Keep raw snapshots and signed changes, without assigning provider requests."""
    snapshots = []
    first = None
    previous = None
    for entry, line_number in zip(records, line_numbers):
        payload = entry["payload"]
        if entry["type"] != "event_msg" or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue
        total = info.get("total_token_usage")
        counters = {field: _number(total.get(field), integer=True) if isinstance(total, dict) else None
                    for field in _CACHE_FIELDS}
        usable = any(number is not None for number in counters.values())
        changes = {field: counters[field] - previous[field]
                   if previous is not None and counters[field] is not None and previous[field] is not None
                   else None for field in _CACHE_FIELDS}
        if usable:
            if first is None:
                first = len(snapshots)
            previous = counters
        snapshots.append({"line_number": line_number, "timestamp": entry.get("timestamp"),
                          "info": info, "cache_counters": counters,
                          "change_from_previous_usable_snapshot": changes,
                          "evidence_references": [source]})
    return {"availability": ("available" if complete else "partial") if first is not None else "unavailable",
            "definition": "Retained token_count snapshots; first usable cumulative cache snapshot index, not first provider request.",
            "request_correlation": "unavailable", "first_token_count_snapshot": first,
            "snapshots": snapshots, "evidence_references": [source]}



def completed_response_usage(payload, *, source, line_number, expected_thread=None):
    """Normalize stock 0.159.0 usage without promoting it to request coverage.

    The three usage mappings have different scopes and must never be added.
    Raw fields remain retained so a later parser can reconstruct its own facts.
    """
    identities = {key: payload.get(key) for key in
                  ("thread_id", "turn_id", "session_id", "root_turn_id", "response_id")}
    reasons = []
    if any(not isinstance(value, str) or not value for value in identities.values()):
        reasons.append("missing_completed_response_identity")
    if expected_thread is not None and identities["thread_id"] != expected_thread:
        reasons.append("completed_response_thread_mismatch")
    counters = {}
    for scope in ("usage", "turn_token_usage", "thread_token_usage"):
        supplied = payload.get(scope)
        counters[scope] = {key: value for key, raw in (supplied.items() if isinstance(supplied, dict) else ())
                           if (value := _number(raw, integer=True)) is not None}
        for child, parent in (("cached_input_tokens", "input_tokens"), ("reasoning_output_tokens", "output_tokens")):
            if child in counters[scope] and parent in counters[scope] and counters[scope][child] > counters[scope][parent]:
                reasons.append(scope + ":" + child + "_exceeds_" + parent)
                del counters[scope][child]
    return {**identities, **counters, "line_number": line_number,
            "classification": "observed", "scope": "completed_response_with_usage",
            "coverage_reason": "Only response.completed events carrying usage are represented; failed, retried and warmup coverage is unproven.",
            "valid_identity": not any("identity" in reason or "mismatch" in reason for reason in reasons),
            "quality_reasons": reasons, "raw": payload, "evidence_references": [source]}


def extract_token_usage(retained):
    records, line_numbers, source, complete = retained.records, retained.line_numbers, retained.source, retained.source_complete
    last_usage = None
    token_events = 0
    context_windows = []
    for entry in records:
        payload = entry["payload"]
        if entry["type"] != "event_msg":
            continue
        if payload.get("type") == "task_started":
            window = _number(payload.get("model_context_window"), integer=True)
            if window is not None:
                context_windows.append(window)
        elif payload.get("type") == "token_count":
            info = payload.get("info")
            if not isinstance(info, dict) or not isinstance(info.get("total_token_usage"), dict):
                continue
            last_usage = info["total_token_usage"]
            token_events += 1
            window = _number(info.get("model_context_window"), integer=True)
            if window is not None:
                context_windows.append(window)
    completed = []
    contradictions = []
    authority = "token_count.info.total_token_usage"
    # Explicitly retained extraction versions remain byte-for-byte reconstructable.
    # Other runtime versions require a demonstrated capability, not schema guesses.
    if retained.extraction_version == "4.0.0" and (retained.runtime_version == "0.159.0"
            or retained.record.get("capabilities", {}).get("token_usage_record_v1") is True):
        seen = {}
        for entry, line_number in zip(records, line_numbers):
            if entry["type"] != "token_usage_record":
                continue
            fact = completed_response_usage(entry["payload"], source=source, line_number=line_number,
                                             expected_thread=retained.thread_id)
            completed.append(fact)
            identity = tuple(fact.get(key) for key in ("thread_id", "turn_id", "response_id"))
            previous = seen.get(identity)
            if previous is not None and previous["usage"] != fact["usage"]:
                contradictions.append({"reason": "conflicting_completed_response_usage", "identity": list(identity),
                                       "lines": [previous["line_number"], line_number], "evidence_references": [source]})
            seen[identity] = fact
            contradictions.extend({"reason": reason, "line_number": line_number, "evidence_references": [source]}
                                  for reason in fact["quality_reasons"])
        if last_usage is None:
            candidates = [fact for fact in completed if fact["valid_identity"] and fact["thread_token_usage"]]
            if candidates:
                last_usage = candidates[-1]["thread_token_usage"]
                authority = "token_usage_record.thread_token_usage"
        elif completed:
            latest = next((fact for fact in reversed(completed) if fact["valid_identity"]), None)
            if latest is not None:
                for field in TOKEN_FIELDS.values():
                    left, right = last_usage.get(field), latest["thread_token_usage"].get(field)
                    if left is not None and right is not None and left != right:
                        contradictions.append({"reason": "cumulative_representations_disagree", "field": field,
                                               "token_count": left, "token_usage_record": right,
                                               "evidence_references": [source]})
    tokens = {}
    for role, field in TOKEN_FIELDS.items():
        number = _number(last_usage.get(field), integer=True) if last_usage is not None else None
        if number is not None:
            tokens[role] = number
    for child, parent in (("cached_input_tokens", "input_tokens"), ("reasoning_tokens", "output_tokens")):
        if child in tokens and parent in tokens and tokens[child] > tokens[parent]:
            del tokens[child]
    writes = _number(last_usage.get("cache_write_input_tokens"), integer=True) if last_usage is not None else None
    return TokenFacts(tokens, writes, tuple(context_windows), token_events, last_usage is not None,
                      _cache_snapshots(records, line_numbers, source, complete), complete, authority,
                      tuple(completed), tuple(contradictions))
