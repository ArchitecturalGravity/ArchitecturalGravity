"""Ingress policy for safe structural telemetry, never free-form payload text.

Only documented measurement and structural fields survive. Unknown fields,
including numeric and boolean fields, are excluded. Strings require a documented
structural role and a bounded lexical shape. Original source bytes are never
mislabelled as sanitized records; excluded fields are counted explicitly.
"""
from __future__ import annotations

import math
import re
import threading
from datetime import datetime

_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}\Z")
_LABEL = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:/+-]{0,159}\Z")
_PRIVATE = re.compile(r"(?:authorization|password|passwd|secret|credential|api[_.-]?key|access[_.-]?token|refresh[_.-]?token|cookie|header|email|account[_.-]?id|user[_.-]?id|prompt_cache_key|error[_.-]?message)", re.I)
_PRIVATE_KEYS = frozenset({"text", "content", "content_base64", "prompt", "input", "output", "arguments",
    "command", "cwd", "path", "root", "message", "description", "rationale", "instructions",
    "error", "exception", "stacktrace", "stderr", "stdout", "environment", "env", "payloads",
    "source_js", "stdin", "display_command", "formatted_output", "input_preview", "output_preview",
    "message_preview", "raw_payloads"})
_STRING_KEYS = frozenset({"type", "kind", "name", "event.name", "event.kind", "event_name", "event_kind",
    "transport", "mode", "phase", "reason", "status", "outcome", "source", "scope", "role", "model",
    "model_provider", "model.slug", "model.name", "provider", "service.name", "service.version",
    "telemetry.sdk.name", "telemetry.sdk.version", "telemetry.sdk.language", "version", "unit",
    "tool", "tool_name", "tool.name", "tool.type", "agent.type", "session_source",
    "severityText", "thread_id", "turn_id", "session_id", "root_turn_id", "response_id", "request_id",
    "previous_response_id", "item_id", "call_id", "id", "conversation.id", "parent.conversation.id",
    "turn.id", "parent.turn.id", "root.turn.id", "item.id", "response.id", "request.id",
    "trace_id", "traceId", "span_id", "spanId", "parent_span_id", "parentSpanId", "agmark_invocation_id",
    "trace_id", "rollout_id", "root_thread_id", "inference_call_id", "tool_call_id", "terminal_id",
    "code_cell_id", "parent_id", "from_id", "to_id", "relation", "schema_version", "availability",
    "error_type", "error.type", "http.request.method", "rpc.method", "rpc.system", "server.type",
    "http.route", "route", "method", "operation", "retry_reason", "connection_state",
    "sandbox", "sandbox_policy", "approval_policy", "status_code", "return_code", "termination_reason",
    "auth.request_id", "cli_version", "aggregationTemporality", "success", "provider_name",
    "reasoning_effort", "reasoning_summary", "product_sku", "history_mode", "fork_mode", "multi_agent_version",
    "speed", "tool_type", "response_action", "completed", "otel.name", "gen_ai.request.model",
    "gen_ai.response.model", "gen_ai.operation.name", "gen_ai.system", "model_provider_id", "slug",
    "codex_turn_id", "upstream_request_id", "model_visible_call_id", "code_mode_runtime_tool_id",
    "runtime_cell_id", "edge_id", "child_thread_id", "child_codex_turn_id", "parent_thread_id", "mcp_call_id",
    "operation_id", "terminal_operation_id", "created_by_operation_id", "started_by_codex_turn_id",
    "source_item_id", "marker_item_id", "spawn_edge_id", "runtime_status", "agent_role",
    "compaction_id", "compaction_request_id", "conversation_item_id", "output_item_ids", "input_item_ids",
    "request_item_ids", "response_item_ids", "nested_tool_call_ids", "wait_tool_call_ids", "operation_ids",
    "model_visible_call_item_ids", "model_visible_output_item_ids", "call_item_ids", "replacement_item_ids",
    "request_ids", "carried_item_ids", "turn_ids", "inference_call_ids", "tool_call_ids", "code_cell_ids",
    "conversation_item_ids", "tool_call_ids_started_by_response", "channel", "default_model"})
_NUMERIC_STRINGS = frozenset({"intValue", "asInt", "count", "zeroCount", "bucketCounts", "positiveBucketCounts",
    "negativeBucketCounts", "timeUnixNano", "observedTimeUnixNano", "startTimeUnixNano", "endTimeUnixNano",
    "duration_ms", "ttft_ms", "input_token_count", "output_token_count", "cached_token_count",
    "cache_write_token_count", "reasoning_token_count", "total_token_count", "tool_token_count", "attempt",
    "http.response.status_code", "input_tokens", "output_tokens", "cached_input_tokens",
    "reasoning_output_tokens", "total_tokens"})
_HEX_KEYS = {"traceId": 32, "spanId": 16, "parentSpanId": 16}

# This is a retention allowlist, not a secret-name blacklist. Unknown data must
# not become durable just because its value happens to be numeric or boolean.
_NUMBER_KEYS = _NUMERIC_STRINGS | frozenset({
    "doubleValue", "boolValue", "asDouble", "sum", "min", "max", "scale", "offset",
    "explicitBounds", "zeroThreshold", "quantile", "value", "flags", "code",
    "droppedAttributesCount", "droppedEventsCount", "droppedLinksCount", "severityNumber",
    "isMonotonic", "cache_write_input_tokens", "reasoning_tokens", "model_context_window",
    "seq", "started_seq", "ended_seq", "started_at_unix_ms", "ended_at_unix_ms",
    "wall_time_unix_ms", "elapsed_ms", "latency_ms", "duration", "exit_code", "exit_status", "return_code",
    "status", "byte_length", "content_excluded", "yield_time_ms", "timeout_ms", "wall_time_seconds",
    "num_turns", "max_output_tokens", "max_input_tokens", "http.status_code",
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "gen_ai.usage.cache_read.input_tokens", "gen_ai.usage.cache_creation.input_tokens",
})
_CONTAINER_KEYS = frozenset({
    "payload", "item", "usage", "turn_token_usage", "thread_token_usage", "info",
    "total_token_usage", "last_token_usage", "input_tokens_details", "output_tokens_details",
    "attributes", "events", "links", "status", "histogram", "exponentialHistogram",
    "gauge", "sum", "summary", "dataPoints", "positive", "negative", "quantileValues",
    "exemplars", "filteredAttributes", "values", "arrayValue", "origin", "execution",
    "metadata", "requester", "request", "result", "source", "target", "produced_by", "kind",
})
_ALLOWED_KEYS = _STRING_KEYS | _NUMBER_KEYS | _CONTAINER_KEYS | frozenset({
    "timestamp", "started_at", "completed_at"})
# Generic labels such as `name` are otherwise a channel for host/user names.
_INSTRUMENT_NAMES = frozenset({
    "codex", "codex-cli", "codex-otel", "responses.stream_request",
    "codex.api_request", "codex.websocket_request", "codex.websocket_connect",
    "codex.sse_event", "codex.auth_recovery", "codex.tool_result", "codex.tool_decision",
    "codex.sandbox_outcome", "codex.api_request.duration_ms", "codex.backend.request.duration", "codex.responses_api_engine_iapi_tbt.duration_ms",
    "codex.responses_api_engine_iapi_ttft.duration_ms", "codex.request.duration_ms",
})
_NAME_KEYS = frozenset({"name", "event.name", "event_name", "otel.name", "service.name"})

_ID_KEYS = frozenset(k for k in _STRING_KEYS if k == "id" or k.endswith(("_id", ".id", "_ids"))) | frozenset(_HEX_KEYS) | {"tool_call_ids_started_by_response"}
# Values are protocol vocabulary, never user-defined labels. Runtime/model
# versions and identities have separate policies below.
_PROTOCOL_LABELS = frozenset("""
thread_started thread_completed thread_ended agent_result_observed inference_started inference_completed
tool_call_started tool_call_completed code_cell_started code_cell_completed codex_turn_started codex_turn_completed
terminal_operation_started terminal_operation_completed compaction_started compaction_completed
thread.started turn.started turn.completed turn.failed item.started item.updated item.completed
session_meta token_usage_record event_msg turn_context response_item token_count task_started task_complete turn_aborted item_completed
message agent_message user_message reasoning function_call function_call_output custom_tool_call custom_tool_call_output
response.created response.in_progress response.completed response.failed response.incomplete response.output_item.added response.output_item.done
response.output_text.delta response.reasoning_summary_text.delta response.function_call_arguments.delta
root spawned thread code_cell tool_call terminal_operation inference_call conversation_item compaction compaction_request
exec_command write_stdin spawn_agent send_message wait wait_agent close_agent resume_agent update_plan apply_patch
started completed failed cancelled timeout timed_out launch_failed pending running in_progress success error ok true false unknown unavailable available
native wsl telemetry session deep_telemetry original replay
websocket http https sse stream streaming unary generation prefill decode connection connect request response inference tool
client server internal producer consumer retry reconnect connecting connected disconnected open closed
assistant user system developer tool analysis final commentary summary
low medium high xhigh minimal none auto concise detailed standard fast default
read-only workspace-write danger-full-access never on-request untrusted on-failure
read_only workspace_write danger_full_access on_request on_failure
cli exec interactive noninteractive isolated inherited forked
GET POST PUT PATCH DELETE OPTIONS HEAD
INFO DEBUG WARN WARNING ERROR TRACE FATAL
AGGREGATION_TEMPORALITY_UNSPECIFIED AGGREGATION_TEMPORALITY_DELTA AGGREGATION_TEMPORALITY_CUMULATIVE
SPAN_KIND_UNSPECIFIED SPAN_KIND_INTERNAL SPAN_KIND_SERVER SPAN_KIND_CLIENT SPAN_KIND_PRODUCER SPAN_KIND_CONSUMER
STATUS_CODE_UNSET STATUS_CODE_OK STATUS_CODE_ERROR
collector_readiness completion reduction selected_host_cleanup selected_host_cleanup_unconfirmed not_started already_exited stopped
invocation_launch_cancelled_before_registration saved_child_process_identity_changed saved_guard_process_is_not_invocation_guard
saved_child_parent_identity_changed linux_process_table_unavailable owned_process_group_empty owned_process_group_did_not_stop
verified_invocation_process_group_terminated invalid_or_unavailable_private_control
""".split())
_RUNTIME_LABEL_KEYS = frozenset({"model", "model.slug", "model.name", "model_provider", "provider",
    "provider_name", "gen_ai.request.model", "gen_ai.response.model", "gen_ai.system", "model_provider_id",
    "default_model", "slug", "telemetry.sdk.name", "telemetry.sdk.language"})
_RUNTIME_LABELS = frozenset({"openai", "anthropic", "azure", "ollama", "codex", "codex-cli", "codex-otel",
    "rust", "python", "javascript", "typescript", "opentelemetry", "opentelemetry-rust"})
_MODEL_NAME = re.compile(r"(?:gpt-[0-9]+(?:\.[0-9]+)?(?:-(?:mini|nano|pro|codex|preview|latest|[0-9]{4}-[0-9]{2}-[0-9]{2}))*|o[0-9]+(?:-mini|-pro)?|claude-(?:sonnet|opus|haiku)-[0-9]+(?:-[0-9]+)*)\Z")
_UNITS = frozenset({"", "1", "ms", "s", "ns", "us", "By", "bytes", "tokens", "{token}", "{request}", "%"})
_TIME_KEYS = frozenset({"timeUnixNano", "observedTimeUnixNano", "startTimeUnixNano", "endTimeUnixNano",
    "started_at_unix_ms", "ended_at_unix_ms", "wall_time_unix_ms", "timestamp", "started_at", "completed_at"})


class AliasRegistry:
    """Invocation-local, non-reversible aliases and source-relative clock origins.

    Raw keys live only in memory. No alias lookup table or wall-clock origin is
    emitted into evidence. Equal source IDs remain equal across all sources.
    """
    def __init__(self):
        self._identities = {}
        self._clocks = {}
        self._lock = threading.RLock()

    def identity(self, value):
        if not isinstance(value, str) or not value or len(value) > 4096:
            return None
        with self._lock:
            if value not in self._identities:
                self._identities[value] = "local-" + str(len(self._identities) + 1)
            return self._identities[value]

    def time(self, value, key, source):
        try:
            if key in {"timestamp", "started_at", "completed_at"}:
                if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", value):
                    return None
                number = int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000000000)
                scale = "iso_ns"
            else:
                if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,25}", str(value)):
                    return None
                number = int(value)
                scale = "ms" if key.endswith("_ms") else "ns"
            with self._lock:
                origin = self._clocks.setdefault((source, scale), number)
            return str(number - origin) if isinstance(value, str) else number - origin
        except (ValueError, OverflowError):
            return None

_RETAINED_NUMBER_KEYS = frozenset({"resource_excluded_attributes", "scope_excluded_attributes",
    "record_excluded_attributes", "dimensions_complete", "attributes", "events", "links",
    "raw_payloads_excluded", "threads", "codex_turns", "conversation_items", "inference_calls",
    "code_cells", "tool_calls", "terminal_sessions", "terminal_operations", "compactions",
    "compaction_requests", "interaction_edges"})
_RETAINED_CONTAINER_KEYS = frozenset({"_resource", "_scope", "_sanitization", "_producer_reported_drops", "graph_counts", "node"})
_RETAINED_LABELS = {"representation": {"stock_reduced_graph"},
    "graph_family": {"threads", "codex_turns", "conversation_items", "inference_calls", "code_cells", "tool_calls",
        "terminal_sessions", "terminal_operations", "compactions", "compaction_requests", "interaction_edges"}}
_RETAINED_KEYS = _ALLOWED_KEYS | _RETAINED_NUMBER_KEYS | _RETAINED_CONTAINER_KEYS | set(_RETAINED_LABELS) | {"graph_object_id", "_schema_version"}


def private_key(key):
    return (not isinstance(key, str) or key not in _ALLOWED_KEYS or not _KEY.fullmatch(key)
            or bool(_PRIVATE.search(key)) or key.lower() in _PRIVATE_KEYS)


class Sanitizer:
    def __init__(self, *, aliases=None, source="source", retained=False):
        self.retained = retained
        self.aliases = aliases if aliases is not None else AliasRegistry()
        self.source = source
        self.excluded_fields = 0
        self.excluded_attributes = 0
        self.truncated_fields = 0

    def exclude(self):
        self.excluded_fields += 1
        return None

    def value(self, value, *, key="", depth=0):
        if depth > 24:
            self.truncated_fields += 1
            return None
        if value is None:
            return None
        if self.retained:
            if key in _ID_KEYS or key == "graph_object_id":
                if isinstance(value, str):
                    return value if re.fullmatch(r"local-[1-9][0-9]*", value) else self.exclude()
            if key in _TIME_KEYS:
                if isinstance(value, (int, str)) and not isinstance(value, bool) and re.fullmatch(r"-?[0-9]{1,17}", str(value)):
                    return value
                return self.exclude()
            if key == "_schema_version":
                return value if isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) else self.exclude()
            if key in _RETAINED_LABELS:
                return value if isinstance(value, str) and value in _RETAINED_LABELS[key] else self.exclude()
            if key in _RETAINED_NUMBER_KEYS and type(value) in {bool, int}:
                return value
            if key == "type" and value in ("reduced_graph", "reduced_graph_node"):
                return value
        if key in _ID_KEYS and isinstance(value, str):
            if key in _HEX_KEYS and (not re.fullmatch(r"[0-9a-fA-F]{" + str(_HEX_KEYS[key]) + "}", value) or not any(c != "0" for c in value)):
                return self.exclude()
            return self.aliases.identity(value) or self.exclude()
        if key in _TIME_KEYS:
            retained = self.aliases.time(value, key, self.source)
            return retained if retained is not None else self.exclude()
        if type(value) in {bool, int}:
            return value if key in _NUMBER_KEYS or key in {"schema_version", "kind", "aggregationTemporality", "status_code"} else self.exclude()
        if type(value) is float:
            return value if key in _NUMBER_KEYS and math.isfinite(value) else self.exclude()
        if isinstance(value, str):
            if re.search(r"(?:sk-[A-Za-z0-9_-]{10,}|Bearer(?:\s|[_.:-])|"
                         r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|"
                         r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{12,}|AKIA[A-Z0-9]{16})", value, re.I):
                return self.exclude()
            if key in {"timestamp", "started_at", "completed_at"} and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", value):
                return value
            if key == "unit" and value in _UNITS:
                return value
            if key in _HEX_KEYS:
                return value if (re.fullmatch(r"[0-9a-fA-F]{" + str(_HEX_KEYS[key]) + "}", value)
                                 and any(c != "0" for c in value)) else self.exclude()
            if key in _NUMBER_KEYS and re.fullmatch(r"-?[0-9]{1,25}", value):
                return value
            if key in _NAME_KEYS:
                return value if value in _INSTRUMENT_NAMES else self.exclude()
            if key in {"version", "cli_version", "service.version", "telemetry.sdk.version"}:
                from .runtime_reference import _version
                return _version(value) or self.exclude()
            if key in _STRING_KEYS and _LABEL.fullmatch(value) and not _PRIVATE.search(value) and "/" not in value and ".." not in value and (value in _PROTOCOL_LABELS or key in _RUNTIME_LABEL_KEYS and (value in _RUNTIME_LABELS or _MODEL_NAME.fullmatch(value))):
                return value
            return self.exclude()
        if isinstance(value, (list, tuple)):
            result = []
            for entry in value[:10000]:
                item = self.value(entry, key=key, depth=depth + 1)
                if item is not None:
                    result.append(item)
            self.truncated_fields += max(0, len(value) - 10000)
            return result
        if isinstance(value, dict):
            if key and key not in _CONTAINER_KEYS and not (self.retained and key in _RETAINED_CONTAINER_KEYS):
                return self.exclude()
            output = {}
            for k, entry in list(value.items())[:10000]:
                if (private_key(k) if not self.retained else k not in _RETAINED_KEYS):
                    self.exclude()
                    continue
                if k == "attributes" and not (self.retained and type(entry) is int):
                    output[k] = self.attributes(entry, depth=depth + 1)
                    continue
                item = self.value(entry, key=k, depth=depth + 1)
                if item is not None:
                    output[k] = item
            self.truncated_fields += max(0, len(value) - 10000)
            return output
        return self.exclude()

    def attributes(self, attributes, *, depth=0):
        if not isinstance(attributes, list):
            self.exclude()
            self.excluded_attributes += 1
            return []
        output = []
        for attribute in attributes[:10000]:
            if not isinstance(attribute, dict) or private_key(attribute.get("key")):
                self.exclude()
                self.excluded_attributes += 1
                continue
            key, value = attribute["key"], attribute.get("value")
            if not isinstance(value, dict) or len(value) != 1:
                self.exclude()
                self.excluded_attributes += 1
                continue
            kind, original = next(iter(value.items()))
            before = self.excluded_fields
            if kind == "stringValue":
                safe = self.value(original, key=key, depth=depth + 1)
            elif kind in {"intValue", "doubleValue", "boolValue"}:
                safe = self.value(original, key=key, depth=depth + 1)
            elif kind == "arrayValue" and isinstance(original, dict):
                # Unknown arrays retain numeric members only, never untyped strings.
                safe = self.value(original, depth=depth + 1)
            else:
                safe = self.exclude()
            if safe is not None:
                output.append({"key": key, "value": {kind: safe}})
            if self.excluded_fields > before:
                self.excluded_attributes += 1
        self.truncated_fields += max(0, len(attributes) - 10000)
        self.excluded_attributes += max(0, len(attributes) - 10000)
        return output


def runtime_identity(runtime):
    """Project runtime metadata, rejecting host inventory and opaque extras."""
    from .runtime_reference import _version
    output = {}
    if not isinstance(runtime, dict):
        return output
    for key in ("version", "runner_version"):
        value = _version(runtime.get(key))
        if value is not None:
            output[key] = value
    for key in ("binary_sha256", "runtime_binary_sha256", "framed_request_sha256", "accepted_boundary_fingerprint"):
        value = runtime.get(key)
        if value is None or isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            output[key] = value
    commit = runtime.get("evidence_commit")
    if commit is None or isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit):
        output["evidence_commit"] = commit
    enums = {
        "runner_id": {"openai.codex-cli"},
        "launch_mode": {"native", "wsl", "unknown"},
        "capability_status": {"supported", "unsupported", "unknown"},
        "reason": {None, "execution_environment_local_receiver_unavailable"},
        "binary_hash_reason": {None, "selected_host_binary_unreadable", "selected_host_binary_not_locally_readable"},
        "receiver_environment": {"selected_distribution", "native"},
        "configuration_authority": {"accepted_execution_boundary"},
        "delivery": {"best_effort_exporter"},
    }
    for key, allowed in enums.items():
        value = runtime.get(key)
        if key in runtime and isinstance(value, (str, type(None))) and value in allowed:
            output[key] = value
    for key in ("complete_request_coverage", "individual_token_arrival_times", "exact_wire_latency"):
        if type(runtime.get(key)) is bool:
            output[key] = runtime[key]
    signals = runtime.get("signals")
    if isinstance(signals, list):
        output["signals"] = [signal for signal in signals if isinstance(signal, str) and signal in {"logs", "traces", "metrics"}]
    capabilities = runtime.get("capabilities")
    if isinstance(capabilities, dict):
        output["capabilities"] = {key: capabilities[key] for key in ("token_usage_record_v1",)
            if type(capabilities.get(key)) is bool}
    return output


def validate_retained_payload(payload):
    """Reject policy-violating retained records, including correctly rehashed ones."""
    sanitizer = Sanitizer(retained=True)
    safe = sanitizer.value(payload)
    if not isinstance(payload, dict) or sanitizer.excluded_fields or sanitizer.truncated_fields or safe != payload:
        raise ValueError("telemetry retained payload violates minimization policy")
    return True
