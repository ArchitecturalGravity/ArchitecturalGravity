"""Display-only duration normalization; canonical measurement evidence stays intact."""
from collections.abc import Mapping

DURATION_LABELS = {"duration": "Treatment Duration", "session_span_minutes": "Session Duration"}


def presentation_measurement(role: str, measurement: Mapping) -> dict:
    """Convert legacy session minutes once, using the supplied unit as authority."""
    displayed = dict(measurement)
    if role == "session_span_minutes" and measurement.get("unit") == "minutes":
        value = measurement.get("value")
        displayed["value"] = None if value is None else value * 60000
        displayed["unit"] = "ms"
    if role == "inference_call_count" and measurement.get("kind") == "timing_estimate" and (
            "not a provider request counter" in measurement.get("details", {}).get("definition", "")
            or measurement.get("method", "").startswith("registered Codex session extraction@")):
        displayed["kind"] = "token_event_proxy"
    return displayed
