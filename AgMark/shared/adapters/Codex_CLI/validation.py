"""Reconstruct retained scored evidence without accessing live session state."""
from __future__ import annotations

import base64
from .session_facts import SESSION_RECORD

def validate_session_observation(extensions, execution, envelope):
    """Reconstruct extraction using retained bytes, never the live home directory."""
    from .session import extract_session_measurements
    record = extensions[SESSION_RECORD]
    if not isinstance(record, dict):
        raise ValueError("invalid retained session record")
    stdout = b""  # Reconstruction consumes only the retained measurement projection.
    process = execution["process"]
    expected, expected_record = extract_session_measurements(record, stdout,
        runtime_version=execution["runtime"]["runtime_version"],
        process_complete=process["exit_status"] is not None and process["transport_status"] is None)
    if expected != envelope or expected_record != record:
        raise ValueError("session measurements do not reconstruct from retained thread evidence")
    return record.get("sha256") if record.get("availability") == "retained" else None
