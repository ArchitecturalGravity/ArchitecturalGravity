"""Synthetic raw session inputs, never captured provider or wire evidence.

Counts and identities are deterministic; root/guardian are input identity labels, not observations
of helper execution. Inputs are raw rollout bytes, never extractor output.
"""
import base64
import json


def synthetic_audit(*, guardian=False):
    count = 8 if guardian else 9
    results = []
    for index in range(count):
        key = f"synthetic-{'guardian' if guardian else 'root'}-{index}"
        rows = [
            {"type": "session_meta", "payload": {"id": key, "session_id": key,
                "source": "exec", "cli_version": "0.159.0"}},
            {"type": "turn_context", "payload": {"model": "synthetic-model", "effort": "high"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 100, "cached_input_tokens": 40,
                    "output_tokens": 20, "total_tokens": 120}}}},
            {"type": "event_msg", "payload": {"type": "task_complete"}},
        ]
        raw = b''.join((json.dumps(row) + '\n').encode() for row in rows)
        stdout = ''.join(json.dumps(row) + '\n' for row in (
            {"type": "thread.started", "thread_id": key}, {"type": "turn.started"},
            {"type": "turn.completed", "usage": {"input_tokens": 99999}}))
        result = {"stdout": stdout, "session_record": {"availability": "retained", "thread_id": key,
                "extraction_version": "4.0.0", "content_base64": base64.b64encode(raw).decode()}}
        results.append(result)
    return {"results": results}
