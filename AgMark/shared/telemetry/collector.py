"""Bounded invocation-local OTLP/HTTP JSON receiver for logs, traces and metrics.

No request headers or unsanitized document bytes are persisted. Each native
metric remains one metric, including temporality, dimensions and bucket counts;
histograms are never expanded into fictional request records.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time

from .privacy import Sanitizer

_SIGNALS = {
    "/v1/traces": ("otel_traces", "resourceSpans", "scopeSpans", "spans"),
    "/v1/logs": ("otel_logs", "resourceLogs", "scopeLogs", "logRecords"),
    "/v1/metrics": ("otel_metrics", "resourceMetrics", "scopeMetrics", "metrics"),
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def decode_document(raw):
    return json.loads(raw, object_pairs_hook=_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON")))


def _reported_drops(value):
    totals = {"attributes": 0, "events": 0, "links": 0}
    keys = {"droppedAttributesCount": "attributes", "droppedEventsCount": "events", "droppedLinksCount": "links"}
    if isinstance(value, dict):
        for key, entry in value.items():
            if key in keys and type(entry) is int and entry >= 0:
                totals[keys[key]] += entry
            elif isinstance(entry, (dict, list)):
                nested = _reported_drops(entry)
                for role in totals:
                    totals[role] += nested[role]
    elif isinstance(value, list):
        for entry in value:
            nested = _reported_drops(entry)
            for role in totals:
                totals[role] += nested[role]
    return totals


def sanitized_signal_records(document, path, sanitizer=None):
    """Retain individual native records with safe resource and scope context."""
    if path not in _SIGNALS or not isinstance(document, dict):
        raise ValueError("unsupported OTLP signal")
    _, resource_key, scope_key, items_key = _SIGNALS[path]
    resources = document.get(resource_key)
    if not isinstance(resources, list):
        raise ValueError("missing OTLP resource envelope")
    sanitizer = sanitizer or Sanitizer()
    result = []
    for resource in resources:
        if not isinstance(resource, dict) or not isinstance(resource.get(scope_key, []), list):
            raise ValueError("invalid OTLP resource envelope")
        before_resource = sanitizer.excluded_attributes
        safe_resource = sanitizer.value(resource.get("resource", {}))
        resource_exclusions = sanitizer.excluded_attributes - before_resource
        for scope in resource.get(scope_key, []):
            if not isinstance(scope, dict) or not isinstance(scope.get(items_key, []), list):
                raise ValueError("invalid OTLP scope envelope")
            before_scope = sanitizer.excluded_attributes
            safe_scope = sanitizer.value(scope.get("scope", {}))
            scope_exclusions = sanitizer.excluded_attributes - before_scope
            for entry in scope.get(items_key, []):
                if not isinstance(entry, dict):
                    raise ValueError("invalid OTLP record")
                before_record = sanitizer.excluded_attributes
                safe = sanitizer.value(entry)
                record_exclusions = sanitizer.excluded_attributes - before_record
                safe["_resource"] = safe_resource
                safe["_scope"] = safe_scope
                producer_drops = _reported_drops(safe)
                safe["_sanitization"] = {"resource_excluded_attributes": resource_exclusions,
                    "scope_excluded_attributes": scope_exclusions, "record_excluded_attributes": record_exclusions,
                    "dimensions_complete": not (resource_exclusions or scope_exclusions or record_exclusions or producer_drops["attributes"])}
                if any(producer_drops.values()):
                    safe["_producer_reported_drops"] = producer_drops
                # Public schema URLs are retained only for the known schema host.
                schema_url = scope.get("schemaUrl") or resource.get("schemaUrl")
                if isinstance(schema_url, str) and schema_url.startswith("https://opentelemetry.io/schemas/"):
                    suffix = schema_url.removeprefix("https://opentelemetry.io/schemas/")
                    if len(suffix) <= 24 and all(c in "0123456789." for c in suffix):
                        safe["_schema_version"] = suffix
                result.append(safe)
    return result


class MultiSignalCollector:
    def __init__(self, ledger, *, on_change=None):
        self.ledger = ledger
        self.on_change = on_change
        self.server = None
        self.thread = None
        self._condition = threading.Condition()
        self._inflight = 0
        self._accepting = False

    @property
    def endpoint(self):
        if self.server is None:
            raise RuntimeError("collector is not running")
        return "http://127.0.0.1:" + str(self.server.server_port)

    def start(self):
        if self.server is not None:
            raise RuntimeError("collector is already running")
        owner = self

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            block_on_close = False

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(0.5)

            def log_message(self, *args):
                pass

            def do_POST(self):
                source = _SIGNALS.get(self.path, (None,))[0]
                with owner._condition:
                    if not owner._accepting:
                        try:
                            self.send_error(503)
                        except OSError:
                            pass
                        return
                    owner._inflight += 1
                status = 200
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
                    if (source is None or not 0 < length <= owner.ledger.profile.max_payload_bytes
                            or media_type != "application/json" or self.headers.get("Content-Encoding")
                            or self.headers.get("Transfer-Encoding")):
                        raise ValueError("invalid OTLP request envelope")
                    raw = self.rfile.read(length)
                    owner.ledger.count(source, received_bytes=len(raw))
                    if len(raw) != length:
                        raise ValueError("incomplete OTLP body")
                    sanitizer = Sanitizer(aliases=owner.ledger.aliases, source=source)
                    records = sanitized_signal_records(decode_document(raw), self.path, sanitizer)
                    # Unsanitized body is discarded before the ledger can see it.
                    del raw
                    with owner.ledger.lock:
                        owner.ledger.excluded_fields += sanitizer.excluded_fields
                        owner.ledger.truncated_fields += sanitizer.truncated_fields
                    for record in records:
                        owner.ledger.add(source, record)
                        drops = record.get("_producer_reported_drops", {})
                        if any(drops.values()):
                            # Preserve native source loss separately from local
                            # retention limits; never claim complete delivery.
                            with owner.ledger.lock:
                                health = owner.ledger.sources[source]
                                previous = health.setdefault("producer_reported_drops", {"attributes": 0, "events": 0, "links": 0})
                                for key, value in drops.items():
                                    previous[key] = max(previous[key], value)
                                health["producer_drop_aggregation"] = "maximum_reported_per_record_not_total"
                            owner.ledger.count(source, partial=1)
                            owner.ledger.state(source, "partial", "producer_reported_dropped_telemetry")
                except OSError:
                    status = 400
                    if source is not None:
                        owner.ledger.count(source, rejected=1, partial=1)
                        owner.ledger.state(source, "partial", "otlp_transport_read_failed")
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    status = 400
                    if source is not None:
                        owner.ledger.count(source, rejected=1, parse_errors=1)
                        owner.ledger.state(source, "partial", "invalid_or_rejected_otlp_payload")
                finally:
                    with owner._condition:
                        owner._inflight -= 1
                        owner._condition.notify_all()
                    if owner.on_change is not None:
                        owner.on_change()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{}")
                except OSError:
                    pass

        self.server = Server(("127.0.0.1", 0), Handler)
        self._accepting = True
        self.thread = threading.Thread(target=self.server.serve_forever,
            kwargs={"poll_interval": 0.02}, name="agmark-original-otlp", daemon=True)
        self.thread.start()
        for source in ("otel_logs", "otel_traces", "otel_metrics"):
            self.ledger.state(source, "ready")
        return self

    def close(self, *, timeout_seconds=None):
        """Stop accepting, drain existing receiver work, and bound shutdown."""
        if self.server is None:
            return True
        timeout = self.ledger.profile.flush_timeout_seconds if timeout_seconds is None else timeout_seconds
        deadline = time.monotonic() + max(0, min(float(timeout), 5))
        with self._condition:
            self._accepting = False
            while self._inflight and time.monotonic() < deadline:
                self._condition.wait(timeout=max(0, deadline - time.monotonic()))
            drained = self._inflight == 0
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=max(0, deadline - time.monotonic()))
        self.server = None
        for source in ("otel_logs", "otel_traces", "otel_metrics"):
            health = self.ledger.snapshot()[source]
            if not drained:
                self.ledger.count(source, partial=1)
                self.ledger.state(source, "partial", "receiver_drain_timeout")
            elif health["state"] != "partial":
                self.ledger.state(source, "settled" if health["received_events"] else "unavailable",
                    None if health["received_events"] else "signal_not_exported_or_not_emitted")
        return drained

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()
