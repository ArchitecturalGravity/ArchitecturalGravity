"""Construct public scored measurement envelopes only from normalized facts."""
from __future__ import annotations

from ...evaluation.telemetry.consumption import attempt_measurements, observed_measurement, unavailable_measurement
from ...evaluation.telemetry.session_metrics import ALL_METRICS as METRICS, METRICS as LEGACY_METRICS, SCHEMA_ID, SCHEMA_VERSION, SESSION_METRICS
from .session_facts import RULES, SOURCE, TOKEN_FIELDS

def build_session_measurements(facts):
    retained, usage, tools, timing = facts.retained, facts.usage, facts.tools, facts.timing
    record, raw, source = retained.record, retained.raw, retained.source
    runtime_version, extraction_version = retained.runtime_version, retained.extraction_version
    thread_id, source_complete = retained.thread_id, retained.source_complete
    tokens, context_windows, token_events = usage.tokens, usage.context_windows, usage.token_events
    events, actual_tools, tool_durations, complete = tools.events, tools.actual_tools, tools.durations, tools.complete
    model, effort = timing.model, timing.effort
    timestamps, prompts, prompt_times = timing.timestamps, timing.prompts, timing.prompt_times
    inference, ttft, tbt, compacted, aborted = timing.inference, timing.ttft, timing.tbt, timing.compacted, timing.aborted
    method = "registered Codex session extraction@" + extraction_version
    value = attempt_measurements(runtime_version=runtime_version, source_identity=source,
        tokens=tokens, tool_events=list(events), trace_complete=complete, source=SOURCE, counting_rules=({**RULES, **{role: "Final " + usage.authority + "." + field
            for role, field in TOKEN_FIELDS.items()}}
            if extraction_version == "4.0.0" else RULES))
    for measurement in value["roles"].values():
        if measurement["value"] is not None:
            measurement["method"] = method
            measurement["details"]["extraction_version"] = extraction_version
            if not source_complete:
                measurement["availability"] = "partial"
    new_telemetry = True
    emitted_metrics = METRICS if new_telemetry else LEGACY_METRICS
    roles = {r: unavailable_measurement(r, record.get("reason", "Session does not expose this metric."), source=SOURCE, unit=u) for r, (u, _) in emitted_metrics.items()}

    def put(role, number, *, numerator=None, denominator=None, extra=None, estimate=False, covered=True):
        if number is None or raw is None:
            return
        details = {"runtime_version": runtime_version, "extraction_version": extraction_version, **(extra or {})}
        if numerator is not None:
            details.update(numerator=numerator, denominator=denominator)
        measurement = observed_measurement(number, unit=METRICS[role][0], kind="timing_estimate" if estimate else "session_counter",
            source=SOURCE, meaning="CodexUsageReport rollout rule: " + role, method=method,
            evidence_references=[source], details=details)
        if not source_complete or not covered:
            measurement["availability"] = "partial"
        roles[role] = measurement

    def average(role, samples, *, estimate=False, covered=True):
        if samples:
            put(role, sum(samples) / len(samples), numerator=sum(samples), denominator=len(samples), estimate=estimate, covered=covered)

    put("cache_write_input_tokens", usage.cache_write_input_tokens)
    put("context_window", max(context_windows) if context_windows else None)
    put("prompt_count", len(prompts))
    if timestamps:
        raw_span = (max(timestamps) - min(timestamps)).total_seconds() / 60
        put("session_span_minutes", max(raw_span, 0.01) if prompts else raw_span, extra={"raw_span_minutes": raw_span})
    if prompt_times and len(prompt_times) == len(prompts):
        prompt_times = sorted(prompt_times)
        put("prompt_span_minutes", (prompt_times[-1] - prompt_times[0]).total_seconds() / 60)
        gaps = [(b-a).total_seconds() / 60 for a, b in zip(prompt_times, prompt_times[1:])]
        average("avg_gap_between_user_prompts_minutes", gaps)
    average("average_characters_per_prompt", prompts)
    put("distinct_tool_count", len(set(actual_tools.values())), extra={"tool_names": sorted(set(actual_tools.values()))}, covered=complete)
    put("compaction_count", compacted)
    put("turn_aborted", aborted)
    timed = [tool_durations[i] for i in actual_tools if i in tool_durations]
    timing_covered = len(timed) == len(actual_tools)
    if timed or not actual_tools and complete:
        put("tool_call_span_duration", sum(timed), extra={"timed_tool_calls": len(timed), "tool_calls": len(actual_tools)}, covered=timing_covered and complete)
    average("tool_call_avg_duration", timed, covered=timing_covered and complete)
    if token_events or usage.has_usage and extraction_version != "4.0.0":
        put("inference_call_count", token_events, estimate=True, extra={"definition": "Count of usable token_count events; not a provider request counter."})
    if inference:
        put("total_inference_ms", sum(inference), estimate=True, covered=len(inference) == token_events)
    average("average_inference_ms", inference, estimate=True, covered=len(inference) == token_events)
    average("average_ttft_ms", ttft, estimate=True, covered=len(ttft) == token_events)
    average("average_tbt_ms", tbt, estimate=True, covered=len(tbt) == token_events)
    if new_telemetry:
        if token_events or usage.has_usage and extraction_version != "4.0.0":
            put("token_usage_event_count", token_events, extra={"definition":
                "Exact count of observed usable token_count events; events may repeat cumulative counters."})
            roles["inference_call_count"]["kind"] = "token_event_proxy"
            roles["inference_call_count"]["meaning"] = "Token-event proxy for inference calls; no demonstrated one-to-one provider-request mapping."
        reasons = {
            "provider_request_count": "Original rollout does not expose complete uniquely identified provider request boundaries; token events are not requests.",
            "average_request_duration_ms": "Original rollout lacks correlated finalized-transmission and terminal-completion timestamps.",
            "average_direct_ttft_ms": "Original rollout lacks request-start and first actual token timestamps; item durations and first-output-item delay are proxies.",
            "average_direct_tbt_ms": "Original rollout lacks ordered actual token timestamps; output chunks are not individual tokens.",
        }
        for role, reason in reasons.items():
            roles[role] = unavailable_measurement(role, reason, source=SOURCE, unit=METRICS[role][0])
        for role, definition in {
            "total_inference_ms": "Sum of paired reasoning and agent-message item durations; not provider request lifecycle duration.",
            "average_inference_ms": "Mean paired reasoning and agent-message item duration; not provider request lifecycle duration.",
            "average_ttft_ms": "Mean reasoning-item duration proxy; not request-to-first-token timing.",
            "average_tbt_ms": "Mean agent-message item duration divided by output_tokens minus one; not observed inter-token timing.",
        }.items():
            roles[role]["meaning"] = definition
            roles[role]["details"]["timing_basis"] = "item_duration_proxy"
    value["extensions"][SESSION_METRICS] = {"schema_id": SCHEMA_ID, "schema_version": SCHEMA_VERSION,
        "thread_id": thread_id, "model": model if isinstance(model, str) else "unknown",
        "reasoning_effort": effort if isinstance(effort, str) else "unknown", "roles": roles,
        "extensions": {"openai.codex_cli:session-capture": {k: v for k, v in record.items() if k != "content_base64"}}}
    return value
