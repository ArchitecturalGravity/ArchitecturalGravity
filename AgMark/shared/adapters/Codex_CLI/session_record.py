"""Project transient rollout bytes into minimal reconstructable source facts."""
from __future__ import annotations
import base64
import json
import re
from .._contract import sha256_bytes
from .events import decode_events, _object
from .session_facts import EXTRACTION_VERSION, RetainedSession
from .source_projection import REPRESENTATION, digest, project_records, stdout_facts, validate_records, source_digest

def returned_thread_id(stdout):
    events, _ = decode_events(stdout)
    starts = [e for e in events if e["type"] == "thread.started"]
    if len(starts) != 1 or not isinstance(starts[0].get("thread_id"), str) or not starts[0]["thread_id"]:
        return None
    return starts[0]["thread_id"]

def parse_session_record(record, stdout, *, runtime_version, process_complete):
    from ...runtime.identity.runtime_version import retained_runtime_version
    full_runtime_version = runtime_version
    runtime_version = retained_runtime_version(runtime_version) or "unobserved"
    projected = record.get("source_representation") == REPRESENTATION
    if "extraction_version" in record and record["extraction_version"] != EXTRACTION_VERSION:
        raise ValueError("unsupported Codex session extraction version")
    if projected:
        safe = dict(record)
        allowed = {"availability", "source_representation", "thread_id", "source_records", "line_numbers", "sha256", "stdout_facts", "extraction_version", "runtime_version", "trace_complete", "reason", "generation_id", "observation_id", "attempt", "launch_environment", "cache_policy", "cache_telemetry", "completed_response_usage", "usage_contradictions", "usage_authority", "source_valid", "capabilities"}
        if set(safe) - allowed:
            raise ValueError("unrelated retained session fields")
        if "capabilities" in safe and safe["capabilities"] != {"token_usage_record_v1": True}:
            raise ValueError("invalid source capability")
        if "launch_environment" in safe and safe["launch_environment"] not in ({"mode": "native", "executable": "runtime/codex"}, {"mode": "wsl", "executable": "runtime/codex"}):
            raise ValueError("invalid retained launch reference")
        records, facts, lines = safe.get("source_records", []), safe["stdout_facts"], safe["line_numbers"]
        validate_records(records)
        if not isinstance(lines, list) or len(lines) != len(records) or any(type(n) is not int or n < 1 for n in lines) or lines != sorted(set(lines)):
            raise ValueError("invalid measurement source positions")
        if not isinstance(facts, dict) or set(facts) != {"valid", "events"} or type(facts["valid"]) is not bool or not isinstance(facts["events"], list):
            raise ValueError("invalid stdout source facts")
        if safe.get("availability") not in {"retained", "unavailable"} or type(safe.get("source_valid")) is not bool:
            raise ValueError("invalid source availability")
        for event in facts["events"]:
            if not isinstance(event, dict) or set(event) - {"type", "thread_id"} or event.get("type") not in {"thread.started", "turn.started", "turn.completed", "turn.failed", "other"}:
                raise ValueError("invalid stdout source event")
            if "thread_id" in event and (not isinstance(event["thread_id"], str) or not re.fullmatch(r"call_[1-9][0-9]*", event["thread_id"])):
                raise ValueError("stdout identity must be invocation-local")
        source = source_digest(records, facts, lines)
        if source != safe.get("sha256") or safe.get("runtime_version") != runtime_version:
            raise ValueError("measurement source integrity mismatch")
        starts = [e for e in facts["events"] if e["type"] == "thread.started"]
        thread_id = starts[0].get("thread_id") if len(starts) == 1 else None
        if thread_id != safe.get("thread_id"):
            raise ValueError("measurement source thread mismatch")
        metas = [e for e in records if e["type"] == "session_meta"]
        if safe["availability"] == "retained" and (len(metas) != 1 or records[0] is not metas[0] or metas[0]["payload"].get("id") != thread_id or metas[0]["payload"].get("forked_from_id") is not None):
            raise ValueError("measurement source session mismatch")
        terminals = [e for e in facts["events"] if e["type"] in {"turn.completed", "turn.failed"}]
        complete = bool(safe["availability"] == "retained" and safe.get("source_valid") is True and records
            and records[-1]["type"] == "event_msg" and records[-1]["payload"].get("type") in {"task_complete", "turn_aborted"}
            and process_complete and facts["valid"] and len(terminals) == 1 and facts["events"][-1] is terminals[0]
            and sum(e["type"] == "turn.started" for e in facts["events"]) == 1)
        if complete != safe.get("trace_complete"):
            raise ValueError("measurement source completeness mismatch")
        return RetainedSession(safe, tuple(records), tuple(lines), source,
            json.dumps(records).encode() if safe["availability"] == "retained" else None,
            thread_id, EXTRACTION_VERSION, runtime_version, complete)
    thread_id = returned_thread_id(stdout)
    records, lines, valid = [], [], True
    raw = None
    if record.get("availability") == "retained":
        try:
            raw = base64.b64decode(record["content_base64"], validate=True)
        except (ValueError, KeyError, TypeError):
            pass
    if raw is not None:
        for number, line in enumerate(raw.splitlines(), 1):
            if not line.strip(): continue
            try:
                entry = json.loads(line.decode("utf-8"), object_pairs_hook=_object)
                if not isinstance(entry, dict) or not isinstance(entry.get("type"), str) or not isinstance(entry.get("payload"), dict):
                    raise ValueError("invalid rollout record")
            except (ValueError, UnicodeError, RecursionError):
                valid = False
                break
            records.append(entry); lines.append(number)
        metas = [e for e in records if e["type"] == "session_meta"]
        if (thread_id is None or record.get("thread_id") != thread_id or len(metas) != 1
                or not records or records[0] is not metas[0] or metas[0]["payload"].get("id") != thread_id
                or metas[0]["payload"].get("forked_from_id") is not None):
            raw = None; records = []; lines = []
    facts = stdout_facts(stdout)
    events = facts["events"]
    terminal = [e for e in events if e["type"] in {"turn.completed", "turn.failed"}]
    complete = bool(raw is not None and valid and records and records[-1]["type"] == "event_msg"
        and records[-1]["payload"].get("type") in {"task_complete", "turn_aborted"}
        and process_complete and facts["valid"] and len(terminal) == 1 and events[-1] is terminal[0]
        and sum(e["type"] == "turn.started" for e in events) == 1)
    records = project_records(records)
    if full_runtime_version != runtime_version:
        # A numeric core cannot establish stock-runtime provenance. Preserve
        # that uncertainty in the minimized source so reconstruction agrees.
        for entry in records:
            if entry["type"] == "session_meta":
                entry["payload"]["cli_version"] = "unknown"
    # Identity equality matters, globally identifying values do not. Correlations
    # remain exact within this source projection, without hashing personal IDs.
    aliases = {}
    def alias(value):
        if not isinstance(value, str) or not value: return None
        if value not in aliases: aliases[value] = "call_" + str(len(aliases) + 1)
        return aliases[value]
    thread_id = alias(thread_id)
    def identities(value):
        if isinstance(value, list): return [identities(v) for v in value]
        if not isinstance(value, dict): return value
        return {k: alias(v) if k in {"id", "call_id", "thread_id", "session_id", "turn_id", "root_turn_id", "response_id", "parent_thread_id", "forked_from_id"} else identities(v) for k,v in value.items()}
    records, facts = identities(records), identities(facts)
    validate_records(records)
    source = source_digest(records, facts, lines)
    safe = {"availability": "retained" if raw is not None else "unavailable",
        "source_representation": REPRESENTATION, "thread_id": thread_id,
        "source_records": records, "line_numbers": lines, "sha256": source,
        "stdout_facts": facts,
        "extraction_version": EXTRACTION_VERSION, "runtime_version": runtime_version,
        "trace_complete": complete, "source_valid": valid}
    if raw is None:
        safe["reason"] = "matched_session_source_unavailable"
    if record.get("capabilities", {}).get("token_usage_record_v1") is True:
        safe["capabilities"] = {"token_usage_record_v1": True}
    for key in ("generation_id", "observation_id", "attempt"):
        if key in record: safe[key] = record[key]
    if "launch_environment" in record:
        safe["launch_environment"] = {"mode": record["launch_environment"].get("mode"), "executable": "runtime/codex"}
    return RetainedSession(safe, tuple(records), tuple(lines), source, raw,
        thread_id, EXTRACTION_VERSION, runtime_version, complete)
