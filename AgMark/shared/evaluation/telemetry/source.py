"""Adapter-neutral, minimized source facts for runtime-counter attempts.

The source retains counter observations and anonymous tool graph facts, never
process bytes or native tool/call names. Its exact bytes independently rebuild
one common measurement envelope, including unknown and incomplete outcomes.
"""
from collections.abc import Mapping
import re
from ...runtime.identity import canonical_sha256
from .consumption import TOKEN_ROLES, attempt_measurements

ATTEMPT_SOURCES = "arcgrav.telemetry:attempt-sources"
SOURCE_FORMAT = "agmark.attempt-source.v1"
_FIELDS = {"format", "runtime_version", "tokens", "tool_events", "trace_complete"}
_STATUSES = {"proposed", "completed", "failed", "unknown"}
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")


def build_attempt_source(*, runtime_version, tokens=None, tool_events=(), trace_complete=False):
    """Project transient source facts and return (retained source, envelope)."""
    if not isinstance(runtime_version, str) or len(runtime_version) > 128 or not _VERSION.fullmatch(runtime_version):
        raise ValueError("invalid measurement runtime version")
    runtime_version = re.split(r"[-+]", runtime_version, maxsplit=1)[0]
    if type(trace_complete) is not bool:
        raise ValueError("trace completeness must be boolean")
    tokens = {} if tokens is None else dict(tokens)
    if set(tokens) - set(TOKEN_ROLES) or any(type(n) is not int or n < 0 for n in tokens.values()):
        raise ValueError("attempt source requires registered nonnegative token counters")
    calls, tools, events = {}, {}, []
    for event in tool_events:
        if not isinstance(event, Mapping) or set(event) - {"invocation_id", "tool_id", "status", "evidence_references"}:
            raise ValueError("unknown tool source fields")
        call, tool, status = event.get("invocation_id"), event.get("tool_id"), event.get("status")
        if not isinstance(call, str) or not call or not isinstance(tool, str) or not tool or status not in _STATUSES:
            raise ValueError("invalid tool source fact")
        events.append({"invocation_id": calls.setdefault(call, "call-" + str(len(calls) + 1)),
            "tool_id": tools.setdefault(tool, "tool-" + str(len(tools) + 1)), "status": status})
    source = {"format": SOURCE_FORMAT,
        "runtime_version": runtime_version, "tokens": tokens, "tool_events": events, "trace_complete": trace_complete}
    identity = canonical_sha256(source)
    envelope = attempt_measurements(runtime_version=runtime_version, source_identity=identity,
        tokens=tokens, tool_events=[{**event, "evidence_references": [identity]} for event in events],
        trace_complete=trace_complete)
    return source, envelope


def validate_attempt_source(source):
    """Reject extra fields/native identifiers; reconstruct exact measurements."""
    if (not isinstance(source, Mapping) or set(source) != _FIELDS
            or source.get("format") != SOURCE_FORMAT):
        raise ValueError("unsupported attempt source")
    rebuilt, envelope = build_attempt_source(runtime_version=source["runtime_version"], tokens=source["tokens"],
        tool_events=source["tool_events"], trace_complete=source["trace_complete"])
    if rebuilt != source:
        raise ValueError("attempt source is not minimized canonical facts")
    return envelope
