"""Ordered sanitized evidence ledger and deterministic integrity validation."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import re
import threading
import time

from .profile import is_safe_invocation_id, CAPTURE_SCHEMA, SANITIZER_VERSION, CaptureProfile
from .privacy import AliasRegistry, runtime_identity, validate_retained_payload

SOURCES = ("stdout", "stderr", "process", "rollout", "otel_logs", "otel_traces", "otel_metrics", "diagnostics")
# Cache only verified digests, never mutable evidence or sensitive payloads.
_VERIFIED_MANIFESTS = OrderedDict()
_VERIFIED_MANIFEST_LOCK = threading.RLock()
_VERIFIED_MANIFEST_LIMIT = 128


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


_CLOCK = {"receipt_wall": "invocation_relative_nanoseconds", "receipt_monotonic": "invocation_relative_nanoseconds",
                    "source_times": "source_relative_offsets_native_units", "ordering": "per_source_receipt_sequence",
                    "cross_source_temporal_correlation": "prohibited"}

def _privacy(profile, excluded_fields, truncated_fields):
    return {"sanitizer_version": SANITIZER_VERSION, "credential_capture": "excluded",
                    "payload_text": "excluded", "raw_otlp_retained": False,
                    "evidence_representation": "labeled_sanitized_records",
                    "raw_source_references": "excluded",
                    "excluded_fields": excluded_fields, "truncated_fields": truncated_fields,
                    "exclusion_policy": ["credentials_headers_and_identity", "prompt_response_tool_payload_text",
                        "arbitrary_strings", "unknown_fields_including_numbers", "source_native_identifiers", "absolute_clock_origins", "invalid_or_unbounded_fields"],
                    "identity_representation": "invocation_local_aliases",
                    "diagnostic_instrumentation_acknowledged": profile.diagnostic_privacy_acknowledged,
                    "diagnostic_consent": profile.diagnostic_consent()}


class EvidenceLedger:
    """Mutation stops at seal; consumers receive independent decoded snapshots."""
    def __init__(self, profile, invocation_id, runtime):
        if not is_safe_invocation_id(invocation_id):
            raise ValueError("capture requires a canonical non-personal invocation identifier")
        self.profile = profile
        self.invocation_id = invocation_id
        self.runtime = runtime
        self.aliases = AliasRegistry()
        self.lock = threading.RLock()
        self.started_at_unix_ns = time.time_ns()
        self.started_at_monotonic_ns = time.monotonic_ns()
        self.records = []
        self.retained_bytes = 0
        self.excluded_fields = 0
        self.truncated_fields = 0
        self._sealed = None
        self.sources = {name: {"source_id": name, "state": "pending", "reason": None,
            "received_events": 0, "received_bytes": 0, "retained_events": 0, "dropped": 0,
            "rejected": 0, "parse_errors": 0, "partial": 0} for name in SOURCES}

    def state(self, source, state, reason=None):
        with self.lock:
            if self._sealed is not None:
                return
            self.sources[source].update(state=state, reason=reason)

    def count(self, source, **counts):
        with self.lock:
            if self._sealed is not None:
                return
            for key, value in counts.items():
                self.sources[source][key] += value

    def add(self, source, payload, *, received_bytes=0):
        with self.lock:
            if self._sealed is not None:
                return False
            health = self.sources[source]
            health["received_events"] += 1
            health["received_bytes"] += received_bytes
            validate_retained_payload(payload)
            encoded = canonical_bytes(payload)
            if (len(self.records) >= self.profile.max_records
                    or self.retained_bytes + len(encoded) > self.profile.max_retained_bytes):
                health["dropped"] += 1
                health.update(state="partial", reason="capture_retention_limit")
                return False
            sequence = health["retained_events"] + 1
            self.records.append({"source": source, "source_sequence": sequence,
                "received_at_unix_ns": time.time_ns() - self.started_at_unix_ns,
                "received_at_monotonic_ns": time.monotonic_ns() - self.started_at_monotonic_ns,
                "payload": json.loads(encoded), "sanitized": True,
                "evidence_id": source + ":" + str(sequence), "payload_sha256": digest(encoded)})
            health["retained_events"] = sequence
            health["state"] = "active" if health["state"] != "partial" else "partial"
            self.retained_bytes += len(encoded)
            return True

    def snapshot(self):
        with self.lock:
            return json.loads(canonical_bytes(self.sources))

    def seal(self, *, process_status):
        with self.lock:
            if self._sealed is not None:
                return json.loads(self._sealed)
            for name, health in self.sources.items():
                records = [record for record in self.records if record["source"] == name]
                health["records_sha256"] = digest(canonical_bytes(records))
            required = ("stdout", "process", "rollout")
            required_complete = all(self.sources[name]["state"] == "settled" for name in required)
            errors = self.truncated_fields + sum(s["dropped"] + s["rejected"] + s["parse_errors"] + s["partial"] for s in self.sources.values())
            enabled = [s for s in self.sources.values() if s["state"] != "disabled"]
            complete = required_complete and not errors and all(s["state"] == "settled" for s in enabled)
            manifest = {"schema_version": CAPTURE_SCHEMA, "invocation_id": self.invocation_id,
                "authority": "original", "profile": self.profile.to_dict(), "runtime": runtime_identity(self.runtime),
                "started_at_unix_ns": 0,
                "finished_at_unix_ns": time.time_ns() - self.started_at_unix_ns, "started_at_monotonic_ns": 0,
                "finished_at_monotonic_ns": time.monotonic_ns() - self.started_at_monotonic_ns, "sealed": True,
                "sources": self.sources, "records": self.records, "process_status": process_status,
                "completeness": {"status": "complete" if complete else "partial",
                    "required_sources_complete": required_complete,
                    "exporter_delivery_guarantee": "best_effort", "provider_request_coverage": "not_established"},
                "privacy": _privacy(self.profile, self.excluded_fields, self.truncated_fields),
                "clock": _CLOCK,
                "integrity": {"algorithm": "sha256", "canonicalization": "sorted_compact_ascii_json_v1"}}
            manifest["integrity"]["manifest_sha256"] = digest(canonical_bytes(manifest))
            _validate_metadata(manifest)
            self._sealed = canonical_bytes(manifest)
            return json.loads(self._sealed)


def validate_manifest(manifest):
    """Verify current bytes on every call; reuse checks only for identical seals."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != CAPTURE_SCHEMA or manifest.get("sealed") is not True:
        raise ValueError("unsupported or unsealed telemetry capture")
    if manifest.get("privacy", {}).get("sanitizer_version") != SANITIZER_VERSION:
        raise ValueError("unsupported telemetry minimization policy")
    if runtime_identity(manifest.get("runtime")) != manifest.get("runtime"):
        raise ValueError("telemetry runtime violates minimization policy")
    _validate_metadata(manifest)
    integrity = dict(manifest.get("integrity", {}))
    expected = integrity.pop("manifest_sha256", None)
    encoded = canonical_bytes({**manifest, "integrity": integrity})
    actual = digest(encoded)
    if expected != actual:
        raise ValueError("telemetry manifest integrity mismatch")
    with _VERIFIED_MANIFEST_LOCK:
        if actual in _VERIFIED_MANIFESTS:
            _VERIFIED_MANIFESTS.move_to_end(actual)
            return True
    # Validate the exact serialized snapshot whose seal was checked above.
    snapshot = json.loads(encoded)
    grouped = {source: [] for source in SOURCES}
    if set(snapshot["sources"]) != set(SOURCES):
        raise ValueError("unknown telemetry source")
    for record in snapshot["records"]:
        source = record.get("source")
        if source not in grouped:
            raise ValueError("unknown telemetry source")
        validate_retained_payload(record.get("payload"))
        grouped[source].append(record)
    for source, health in snapshot["sources"].items():
        records = grouped[source]
        if health["records_sha256"] != digest(canonical_bytes(records)) or health["retained_events"] != len(records):
            raise ValueError("telemetry source integrity mismatch")
        for index, record in enumerate(records, 1):
            if (record["source_sequence"] != index or record["evidence_id"] != source + ":" + str(index)
                    or record["payload_sha256"] != digest(canonical_bytes(record["payload"]))):
                raise ValueError("telemetry record integrity mismatch")
    with _VERIFIED_MANIFEST_LOCK:
        _VERIFIED_MANIFESTS[actual] = True
        _VERIFIED_MANIFESTS.move_to_end(actual)
        while len(_VERIFIED_MANIFESTS) > _VERIFIED_MANIFEST_LIMIT:
            _VERIFIED_MANIFESTS.popitem(last=False)
    return True


_HEALTH_LABELS = frozenset("""
pending ready active partial failed settled disabled unsupported unavailable retained removed incomplete
capture_retention_limit legacy_capture_profile execution_environment_local_receiver_unavailable
local_receiver_start_failed private_diagnostic_directory_unavailable explicit_sensitive_diagnostic_opt_in_required
stream_capture_failed malformed_or_truncated_structural_event stream_event_size_limit stream_final_bytes_disagree stream_not_supplied
stdout_empty process_ended_without_terminal_event exact_thread_rollout_unavailable rollout_byte_limit
session_thread_id_mismatch rollout_terminal_event_unobserved malformed_rollout_bytes diagnostic_reduction_deadline
stock_trace_reduce_failed_or_timed_out diagnostic_capture_cancelled diagnostic_parse_deadline diagnostic_record_limit
stock_reduced_graph_not_available diagnostic_bundle_partially_retained stock_diagnostic_bundle_not_written
stock_diagnostic_recording_incomplete
diagnostic_graph_root_unmatched
stock_diagnostic_bundle_unreadable sensitive_diagnostic_cleanup_failed diagnostic_cleanup_failed
diagnostic_cleanup_timeout diagnostic_cleanup_unavailable producer_reported_dropped_telemetry
otlp_transport_read_failed invalid_or_rejected_otlp_payload receiver_drain_timeout signal_not_exported_or_not_emitted
selected_host_bridge_backpressure selected_host_cleanup_unconfirmed saved_child_process_identity_changed
saved_guard_process_is_not_invocation_guard saved_child_parent_identity_changed linux_process_table_unavailable
owned_process_group_did_not_stop invalid_or_unavailable_private_control
ambiguous_session_records invalid_session_path invalid_thread_id session_capture_cancelled session_discovery_entry_limit
session_discovery_timeout session_record_byte_limit session_record_missing session_record_unreadable session_settlement_timeout
session_terminal_event_unobserved session_writer_not_settled
maximum_reported_per_record_not_total
""".split())
_HEALTH_KEYS = frozenset("""
source_id state reason reasons received_events received_bytes retained_events dropped rejected parse_errors partial
records_sha256 thread_id reduced_graph cleanup processing producer_reported_drops
producer_drop_aggregation reduction_attempted budget_seconds attributes events links
""".split())


def _validate_health(value, key=""):
    if value is None:
        return
    if isinstance(value, dict):
        if set(value) - _HEALTH_KEYS:
            raise ValueError("unknown telemetry source health field")
        for child, item in value.items():
            _validate_health(item, child)
    elif isinstance(value, list) and key == "reasons":
        for item in value:
            _validate_health(item, "reason")
    elif key in {"state", "reason", "reasons", "producer_drop_aggregation"}:
        if not isinstance(value, str) or value not in _HEALTH_LABELS:
            raise ValueError("unknown telemetry source health label")
    elif key == "source_id":
        if value not in SOURCES:
            raise ValueError("unknown telemetry source")
    elif key == "records_sha256":
        if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ValueError("invalid telemetry source digest")
    elif key == "thread_id":
        if not isinstance(value, str) or not re.fullmatch(r"local-[1-9][0-9]*", value):
            raise ValueError("source-native identity in telemetry health")
    elif key == "reduction_attempted":
        if type(value) is not bool:
            raise ValueError("invalid diagnostic reduction flag")
    elif key == "budget_seconds":
        if type(value) not in {int, float} or not 0 <= value <= 5:
            raise ValueError("invalid diagnostic budget")
    elif type(value) is not int or value < 0:
        raise ValueError("invalid telemetry source counter")


def _validate_metadata(manifest):
    """No arbitrary metadata may bypass source payload minimization."""
    from dataclasses import fields
    required = {"schema_version", "invocation_id", "authority", "profile", "runtime", "started_at_unix_ns",
        "finished_at_unix_ns", "started_at_monotonic_ns", "finished_at_monotonic_ns", "sealed", "sources", "records",
        "process_status", "completeness", "privacy", "clock", "integrity"}
    if set(manifest) != required or manifest["authority"] != "original" or manifest["clock"] != _CLOCK:
        raise ValueError("unsupported telemetry manifest metadata")
    # Match producer admission before trusting an untrusted, rehashed archive.
    if not is_safe_invocation_id(manifest["invocation_id"]):
        raise ValueError("capture requires a canonical non-personal invocation identifier")
    supplied = manifest["profile"]
    if not isinstance(supplied, dict):
        raise ValueError("invalid telemetry profile")
    profile = CaptureProfile(**{field.name: supplied[field.name] for field in fields(CaptureProfile)})
    if supplied != profile.to_dict():
        raise ValueError("unsupported telemetry profile metadata")
    privacy = manifest["privacy"]
    if (not isinstance(privacy, dict) or any(type(privacy.get(key)) is not int or privacy[key] < 0
            for key in ("excluded_fields", "truncated_fields"))
            or privacy != _privacy(profile, privacy["excluded_fields"], privacy["truncated_fields"])):
        raise ValueError("unsupported telemetry privacy metadata")
    if (manifest["started_at_unix_ns"] != 0 or manifest["started_at_monotonic_ns"] != 0
            or any(type(manifest[key]) is not int or not 0 <= manifest[key] <= 10**17
                   for key in ("finished_at_unix_ns", "finished_at_monotonic_ns"))):
        raise ValueError("absolute or invalid telemetry clock origin")
    validate_retained_payload(manifest["process_status"])
    for health in manifest["sources"].values():
        _validate_health(health)
    completeness = manifest["completeness"]
    if (set(completeness) != {"status", "required_sources_complete", "exporter_delivery_guarantee", "provider_request_coverage"}
            or completeness["status"] not in {"complete", "partial"}
            or type(completeness["required_sources_complete"]) is not bool
            or completeness["exporter_delivery_guarantee"] != "best_effort"
            or completeness["provider_request_coverage"] != "not_established"):
        raise ValueError("unsupported telemetry completeness metadata")
    if set(manifest["integrity"]) != {"algorithm", "canonicalization", "manifest_sha256"} or manifest["integrity"]["algorithm"] != "sha256" or manifest["integrity"]["canonicalization"] != "sorted_compact_ascii_json_v1":
        raise ValueError("unsupported telemetry integrity metadata")
    for record in manifest["records"]:
        if (set(record) != {"source", "source_sequence", "received_at_unix_ns", "received_at_monotonic_ns", "payload", "sanitized", "evidence_id", "payload_sha256"}
                or record["sanitized"] is not True
                or any(type(record[key]) is not int or not 0 <= record[key] <= 10**17
                       for key in ("received_at_unix_ns", "received_at_monotonic_ns"))):
            raise ValueError("unsupported telemetry record metadata")
