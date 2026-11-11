"""Coordinate scored Codex session extraction through normalized facts."""
from __future__ import annotations

from .session_facts import SESSION_RECORD, EXTRACTION_VERSION, SessionFacts
from .session_record import parse_session_record, returned_thread_id
from .token_usage import extract_token_usage
from .cache_policy import _cache_policy
from .tool_telemetry import extract_tool_telemetry
from .session_timing import extract_session_timing
from .measurements import build_session_measurements
from .validation import validate_session_observation

def extract_session_measurements(record, stdout, *, runtime_version, process_complete):
    retained = parse_session_record(record, stdout, runtime_version=runtime_version, process_complete=process_complete)
    usage = extract_token_usage(retained)
    metadata = retained.records[0]["payload"] if retained.records else None
    policy = _cache_policy(metadata, retained.thread_id, retained.runtime_version, retained.source)
    retained.record["cache_policy"] = policy
    retained.record["cache_telemetry"] = usage.snapshots
    retained.record["completed_response_usage"] = list(usage.completed_responses)
    retained.record["usage_contradictions"] = list(usage.contradictions)
    retained.record["usage_authority"] = usage.authority
    facts = SessionFacts(retained, usage, extract_tool_telemetry(retained), extract_session_timing(retained), policy)
    return build_session_measurements(facts), retained.record
