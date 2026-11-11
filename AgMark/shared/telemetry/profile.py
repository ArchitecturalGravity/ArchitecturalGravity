"""Versioned, stock-only original invocation capture capabilities.

Capture setup is independent of Codex CLI version; exporter availability and
coverage are observed per invocation. Audited provenance does not grant or deny
capture admission.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from urllib.parse import urlsplit

CAPTURE_EXTENSION = "agmark.telemetry:capture"
CAPTURE_SCHEMA = "agmark.telemetry.capture.v2"
PROTOCOL_VERSION = "agmark.original-telemetry.v2"
SANITIZER_VERSION = "agmark.safe-telemetry.v2"
AUDITED_RUNTIME = "0.159.0"
AUDIT_COMMIT = "687a119f0fcaace47e1f1abcc77cec6c813fd6da"
PROFILE_IDS = ("session", "telemetry", "deep_telemetry")
# Bump this consent version when sensitive collection, location or retention
# changes materially, even if the parser/capture profile stays compatible.
# GUI preferences are scoped to these values and never become scoring inputs.
DIAGNOSTIC_CONSENT_SCOPE = "agmark.original-diagnostics.stock-rollout"
DIAGNOSTIC_CONSENT_VERSION = "2.0.0"
DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT = (
    "acknowledged:" + DIAGNOSTIC_CONSENT_SCOPE + "@" + DIAGNOSTIC_CONSENT_VERSION
)


def is_safe_invocation_id(value):
    """Admit generated application identities, never arbitrary caller labels.

    The fixed GUI diagnostic identity contains no caller data. Observation and
    golden identities are generated from canonical execution authority.
    """
    return isinstance(value, str) and (
        value == "gui-runner-test:echo-test"
        or re.fullmatch(r"(?:observation:[0-9a-f]{64}|golden-[0-9a-f]{32})", value) is not None)


@dataclass(frozen=True)
class CaptureProfile:
    id: str = "telemetry"
    diagnostic_privacy_acknowledged: bool = False
    version: str = "2.0.0"
    protocol_version: str = PROTOCOL_VERSION
    max_payload_bytes: int = 4 * 1024 * 1024
    max_records: int = 50000
    max_retained_bytes: int = 64 * 1024 * 1024
    flush_timeout_seconds: float = 1.0

    def __post_init__(self):
        if self.id not in PROFILE_IDS:
            raise ValueError("unsupported telemetry capture profile")
        if type(self.diagnostic_privacy_acknowledged) is not bool:
            raise TypeError("diagnostic privacy acknowledgement must be explicit boolean")
        if self.id == "deep_telemetry" and not self.diagnostic_privacy_acknowledged:
            raise ValueError("deep capture requires explicit additional instrumentation acknowledgement")
        if self.version != "2.0.0" or self.protocol_version != PROTOCOL_VERSION:
            raise ValueError("unsupported capture profile version")
        if not (1 <= self.max_payload_bytes <= 16 * 1024 * 1024
                and 1 <= self.max_records <= 100000
                and 1 <= self.max_retained_bytes <= 128 * 1024 * 1024
                and 0 <= self.flush_timeout_seconds <= 5):
            raise ValueError("capture limits must remain bounded")

    @classmethod
    def from_control(cls, value, *, diagnostic_privacy_acknowledged=False):
        return cls(id=value or "session", diagnostic_privacy_acknowledged=diagnostic_privacy_acknowledged)

    @property
    def diagnostics_enabled(self):
        return self.id == "deep_telemetry"

    @property
    def enabled(self):
        return self.id != "session"

    def diagnostic_consent(self):
        """Record the accepted boundary decision, not a GUI preference grant."""
        return {"scope": DIAGNOSTIC_CONSENT_SCOPE,
                "version": DIAGNOSTIC_CONSENT_VERSION,
                "profile_id": "deep_telemetry",
                "acknowledged": self.diagnostic_privacy_acknowledged,
                "acknowledgement_control": (
                    DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
                    if self.diagnostic_privacy_acknowledged else "not_acknowledged"),
                "active": self.diagnostics_enabled and self.diagnostic_privacy_acknowledged,
                "authority": "explicit_execution_boundary_control",
                "applies_to": "original_run_stock_diagnostics_only"}

    def to_dict(self):
        return {**asdict(self), "diagnostics_enabled": self.diagnostics_enabled,
                "diagnostic_consent": self.diagnostic_consent(),
                "authority": "original", "instrumentation": "stock_exposed_interfaces",
                "sanitizer_version": SANITIZER_VERSION,
                "diagnostic_overhead": "additional_local_io_and_reduction" if self.diagnostics_enabled else "disabled",
                "diagnostic_inference_header": "x-codex-inference-call-id" if self.diagnostics_enabled else None,
                "sensitive_diagnostic_payload_retention": "excluded_in_every_profile"}


def capability(runtime_version, launch_mode="native"):
    from .runtime_reference import _version
    version = _version(runtime_version) or ""
    launch_mode = launch_mode if launch_mode in {"native", "wsl"} else "unknown"
    reason = None if launch_mode == "native" else "execution_environment_local_receiver_unavailable"
    return {"version": version, "launch_mode": launch_mode,
            "capability_status": "supported" if reason is None else "unsupported",
            "reason": reason, "evidence_commit": AUDIT_COMMIT if isinstance(runtime_version, str)
                and runtime_version.removeprefix("codex-cli ") == AUDITED_RUNTIME else None,
            "signals": ["logs", "traces", "metrics"] if reason is None else [],
            "delivery": "best_effort_exporter", "complete_request_coverage": False,
            "individual_token_arrival_times": False, "exact_wire_latency": False}


def observation_overrides(invocation_id, endpoint):
    """Use stock OTLP/HTTP JSON exporters, always on the invocation's loopback."""
    import re
    if not is_safe_invocation_id(invocation_id):
        raise ValueError("capture requires a canonical non-personal invocation identifier")
    url = urlsplit(endpoint)
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
            or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment):
        raise ValueError("original capture requires a loopback-only collector")
    base = endpoint.rstrip("/")
    values = list(disabled_overrides()[:4])
    for setting, signal in (("exporter", "logs"), ("trace_exporter", "traces"), ("metrics_exporter", "metrics")):
        values.append("otel." + setting + "={otlp-http={endpoint="
                      + json.dumps(base + "/v1/" + signal) + ',protocol="json"}}')
    values.append("otel.span_attributes={agmark_invocation_id=" + json.dumps(invocation_id) + "}")
    return tuple(values)


def disabled_overrides():
    """Suppress external metrics exports when capture is disabled."""
    return ("otel.log_user_prompt=false", "otel.log_agent_responses=false",
            "otel.log_guardian_assessments=false", "otel.tool_result.max_bytes=0",
            'otel.exporter="none"', 'otel.trace_exporter="none"', 'otel.metrics_exporter="none"')
