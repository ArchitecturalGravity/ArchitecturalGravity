"""Versioned facts and measurements from invocation-scoped, sanitized evidence.

This module never opens a provider connection or infers a join from timestamps.
Capture owns privacy and immutable bytes; this parser owns their interpretation.
Unknown records and native metric points stay in facts for future parser versions.
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from copy import deepcopy
import hashlib
import json
import math
import threading

from ..adapters.Codex_CLI.token_usage import completed_response_usage

NORMALIZATION_VERSION = "2.0.0"
_RECONSTRUCTION_DIGESTS = OrderedDict()
_RECONSTRUCTION_CACHE_LOCK = threading.RLock()
_RECONSTRUCTION_CACHE_LIMIT = 128
NORMALIZED_EXTENSION = "agmark.telemetry:normalized"
CAPTURE_EXTENSION = "agmark.telemetry:capture"
TOKEN_FIELDS = {"input_tokens": "input_tokens", "cached_input_tokens": "cached_input_tokens",
                "output_tokens": "output_tokens", "reasoning_tokens": "reasoning_output_tokens",
                "total_tokens": "total_tokens", "cache_write_input_tokens": "cache_write_input_tokens"}
ID_ALIASES = {"thread_id": ("thread_id", "thread.id", "conversation.id"),
              "session_id": ("session_id", "session.id"), "turn_id": ("turn_id", "turn.id", "codex_turn_id"),
              "root_turn_id": ("root_turn_id",), "response_id": ("response_id", "response.id", "gen_ai.response.id"),
              "request_id": ("request_id", "request.id", "auth.request_id", "http.request.id", "upstream_request_id"),
              "tool_call_id": ("tool_call_id", "tool.call_id"), "model_call_id": ("call_id", "model_visible_call_id"),
              "inference_call_id": ("inference_call_id",), "runtime_cell_id": ("runtime_cell_id",),
              "code_mode_runtime_tool_id": ("code_mode_runtime_tool_id",), "mcp_call_id": ("mcp_call_id",),
              "terminal_id": ("terminal_id",), "terminal_operation_id": ("operation_id", "terminal_operation_id"),
              "code_cell_id": ("code_cell_id",), "conversation_item_id": ("item_id",),
              "compaction_id": ("compaction_id",), "compaction_request_id": ("compaction_request_id",), "edge_id": ("edge_id",), "rollout_id": ("rollout_id",),
              "trace_id": ("traceId", "trace_id"), "span_id": ("spanId", "span_id"),
              "parent_span_id": ("parentSpanId", "parent_span_id")}

_ID_NAMES_BY_ALIAS = {alias: name for name, aliases in ID_ALIASES.items() for alias in aliases}

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _number(value, *, integer=False):
    if isinstance(value, str):
        try:
            value = int(value) if integer else float(value)
        except (ValueError, OverflowError):
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return value if not integer or type(value) is int else None


def _any_value(value):
    if not isinstance(value, dict):
        return value
    for kind in ("stringValue", "boolValue", "intValue", "doubleValue", "bytesValue"):
        if kind in value:
            return value[kind]
    if "arrayValue" in value:
        return [_any_value(v) for v in value["arrayValue"].get("values", ())]
    if "kvlistValue" in value:
        return _attributes(value["kvlistValue"].get("values", ()))
    return value


def _attributes(value):
    if isinstance(value, dict):
        return {key: _any_value(item) for key, item in value.items()}
    result, conflicts = {}, {}
    for item in value or ():
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        key, parsed = item["key"], _any_value(item.get("value"))
        if key in result and result[key] != parsed:
            conflicts[key] = [result[key], parsed]
        result[key] = parsed
    for key in conflicts:
        result.pop(key, None)
    if conflicts:
        result["_attribute_conflicts"] = conflicts
    return result


def _ids(*supplied):
    candidates_by_name = defaultdict(set)
    for source in supplied:
        for alias, value in source.items():
            name = _ID_NAMES_BY_ALIAS.get(alias)
            if name is not None and isinstance(value, str) and value and value != "[REDACTED]":
                if name not in {"trace_id", "span_id", "parent_span_id"} or set(value) != {"0"}:
                    candidates_by_name[name].add(value)
    result, conflicts = {}, {}
    for name, candidates in candidates_by_name.items():
        if len(candidates) == 1:
            result[name] = next(iter(candidates))
        elif len(candidates) > 1:
            conflicts[name] = sorted(candidates)
    if conflicts:
        result["_identity_conflicts"] = conflicts
    return result


def _supported(manifest):
    runtime = manifest.get("runtime", {})
    return runtime.get("version") == "0.159.0" or runtime.get("capabilities", {}).get("token_usage_record_v1") is True


def _fact(record, suffix="", **values):
    return {"id": record.get("evidence_id", f'{record.get("source")}:{record.get("source_sequence")}') + suffix,
            "source": record.get("source", "unknown"), "source_sequence": record.get("source_sequence"),
            "received_at_unix_ns": record.get("received_at_unix_ns"),
            "received_at_monotonic_ns": record.get("received_at_monotonic_ns"),
            "evidence_references": [record.get("evidence_id", f'{record.get("source")}:{record.get("source_sequence")}')],
            **values}


def _parse_record(record, manifest):
    source, payload = record.get("source"), record.get("payload")
    if not isinstance(payload, dict):
        return [_fact(record, kind="unknown", identities={}, native=deepcopy(payload))]
    if source == "rollout":
        kind = payload.get("type", "unknown")
        content = payload.get("payload", {})
        if not isinstance(content, dict):
            return [_fact(record, kind="unknown", identities={}, native=deepcopy(payload))]
        identities = _ids(content)
        values = {"kind": "event", "event_type": kind, "identities": identities,
                  "timestamp": payload.get("timestamp"), "native": deepcopy(payload)}
        if kind == "token_usage_record" and _supported(manifest):
            usage = completed_response_usage(content, source=record.get("evidence_id", "rollout"),
                line_number=record.get("source_sequence"), expected_thread=manifest.get("thread_id", manifest.get("sources", {}).get("rollout", {}).get("thread_id")))
            values.update(kind="completed_response_usage", usage=usage)
        elif kind == "token_usage_record":
            values.update(kind="unknown", reason="Runtime token_usage_record schema lacks demonstrated capability.")
        elif kind == "session_meta":
            values.update(kind="session")
            if isinstance(content.get("id"), str):
                identities["thread_id"] = content["id"]
        elif kind == "turn_context":
            values.update(kind="turn", configuration=deepcopy(content))
        elif kind == "event_msg":
            values["event_type"] = content.get("type", "unknown")
            if content.get("type") == "token_count":
                info = content.get("info")
                if isinstance(info, dict) and isinstance(info.get("total_token_usage"), dict):
                    values.update(kind="usage_snapshot", usage=deepcopy(info["total_token_usage"]))
            elif content.get("type") in {"task_started", "task_complete", "turn_aborted"}:
                values["kind"] = "turn"
            elif content.get("type") == "item_completed":
                values["kind"] = "item"
                item = content.get("item", {})
                if isinstance(item, dict):
                    values["identities"].update(_ids(item))
        elif kind == "response_item":
            ptype = content.get("type", "unknown")
            values["event_type"] = ptype
            if ptype in {"function_call", "function_call_output", "custom_tool_call", "custom_tool_call_output", "web_search_call"}:
                values["kind"] = "tool"
            elif ptype == "message" and content.get("role") == "user":
                values["kind"] = "prompt"
        return [_fact(record, **values)]
    if source in {"otel_logs", "otel_traces"}:
        attrs = _attributes(payload.get("attributes"))
        identities = _ids(payload, attrs)
        name = attrs.get("event.name") or payload.get("name") or payload.get("eventName") or "unknown"
        values = {"kind": "span" if source == "otel_traces" else "log", "event_type": name,
                  "identities": identities, "attributes": attrs, "native": deepcopy(payload),
                  "timestamp": payload.get("timeUnixNano", payload.get("startTimeUnixNano"))}
        if name in {"codex.api_request", "codex.websocket_request"}:
            values["kind"] = "request"
        elif name in {"codex.websocket_connect", "codex.sse_event", "codex.auth_recovery"}:
            values["kind"] = "transport"
        elif name in {"codex.tool_result", "codex.tool_decision", "codex.sandbox_outcome"}:
            values["kind"] = "tool"
        facts = [_fact(record, **values)]
        # OTLP events inherit only the documented enclosing span ancestry.
        for index, event in enumerate(payload.get("events", ())):
            if not isinstance(event, dict):
                continue
            event_attrs = _attributes(event.get("attributes"))
            event_ids = _ids(event, event_attrs)
            for key in ("trace_id", "span_id"):
                if key in identities:
                    event_ids.setdefault(key, identities[key])
            event_name = event_attrs.get("event.name") or event.get("name", "unknown")
            event_kind = "request" if event_name in {"codex.api_request", "codex.websocket_request"} else "span_event"
            facts.append(_fact(record, f"/events/{index}", kind=event_kind, event_type=event_name,
                               identities=event_ids, attributes=event_attrs, native=deepcopy(event),
                               timestamp=event.get("timeUnixNano")))
        return facts
    if source == "otel_metrics":
        facts = []
        for metric_type in ("gauge", "sum", "histogram", "exponentialHistogram", "summary"):
            metric = payload.get(metric_type)
            if not isinstance(metric, dict):
                continue
            for index, point in enumerate(metric.get("dataPoints", ())):
                if not isinstance(point, dict):
                    continue
                attrs = _attributes(point.get("attributes"))
                facts.append(_fact(record, f"/{metric_type}/{index}", kind="metric", metric_name=payload.get("name", "unknown"),
                    metric_type=metric_type, unit=payload.get("unit", "1"), description=payload.get("description", ""),
                    temporality=metric.get("aggregationTemporality"), is_monotonic=metric.get("isMonotonic"),
                    dimensions=attrs, resource=deepcopy(payload.get("_resource", {})),
                    instrumentation_scope=deepcopy(payload.get("_scope", {})),
                    dimensions_complete=payload.get("_sanitization", {}).get("dimensions_complete") is True and "_attribute_conflicts" not in attrs,
                    identities=_ids(point, attrs),
                    native=deepcopy(point), metric_metadata={key: deepcopy(value) for key, value in payload.items()
                                                            if key not in {"gauge", "sum", "histogram", "exponentialHistogram", "summary"}}))
        return facts or [_fact(record, kind="unknown_metric", identities={}, native=deepcopy(payload))]
    if source == "diagnostics" and payload.get("type") in {"reduced_graph", "reduced_graph_node"}:
        node = payload.get("node", {})
        if not isinstance(node, dict):
            node = {}
        identities = _ids(node)
        if isinstance(payload.get("trace_id"), str):
            identities["diagnostic_trace_id"] = payload["trace_id"]
        relationships = []
        field_types = {"created_by_operation_id": "terminal_operation_id", "operation_ids": "terminal_operation_id",
                       "nested_tool_call_ids": "tool_call_id", "wait_tool_call_ids": "tool_call_id",
                       "source_item_id": "conversation_item_id", "output_item_ids": "conversation_item_id",
                       "model_visible_call_item_ids": "conversation_item_id", "model_visible_output_item_ids": "conversation_item_id",
                       "started_by_codex_turn_id": "turn_id"}
        for field, identity_type in field_types.items():
            supplied = node.get(field, ())
            for identity in supplied if isinstance(supplied, list) else [supplied]:
                if isinstance(identity, str) and identity:
                    relationships.append({"relation": field, "identity_type": identity_type, "identity": identity})
        for field in ("source", "target", "requester"):
            endpoint = node.get(field, {})
            if isinstance(endpoint, dict):
                for identity_type, identity in _ids(endpoint).items():
                    if not identity_type.startswith("_"):
                        relationships.append({"relation": field, "identity_type": identity_type, "identity": identity})
        return [_fact(record, kind="diagnostic_graph", event_type=payload.get("graph_family", payload["type"]),
            identities=identities, relationships=relationships, graph_object_id=payload.get("graph_object_id"),
            classification="derived", method="stock codex debug trace-reduce", native=deepcopy(payload))]
    if source == "diagnostics":
        content = payload.get("payload", {})
        if not isinstance(content, dict):
            content = {}
        identities = _ids(payload, content, content.get("metadata", {}) if isinstance(content.get("metadata"), dict) else {})
        if "trace_id" in identities:
            identities["diagnostic_trace_id"] = identities.pop("trace_id")
        requester = content.get("requester", {})
        relationships = []
        if isinstance(requester, dict) and requester.get("type") == "code_cell" and isinstance(requester.get("runtime_cell_id"), str):
            relationships.append({"relation": "requested_by_code_cell", "identity_type": "runtime_cell_id", "identity": requester["runtime_cell_id"]})
        if content.get("type") == "agent_result_observed":
            for field, relation in (("child_thread_id", "result_from_child_thread"), ("parent_thread_id", "result_delivered_to_parent_thread")):
                if isinstance(content.get(field), str):
                    relationships.append({"relation": relation, "identity_type": "thread_id", "identity": content[field]})
        return [_fact(record, kind="diagnostic", event_type=content.get("type", payload.get("type", "unknown")),
            identities=identities, relationships=relationships, timestamp=payload.get("wall_time_unix_ms"),
            writer_sequence=payload.get("seq"), diagnostic_schema_version=payload.get("schema_version"), native=deepcopy(payload))]
    return [_fact(record, kind={"stdout": "exec_event", "stderr": "stderr", "process": "lifecycle",
                               "diagnostics": "diagnostic"}.get(source, "unknown"),
                  event_type=payload.get("type", payload.get("event", "unknown")), identities=_ids(payload), native=deepcopy(payload))]


def _correlate(facts):
    indexes = defaultdict(list)
    for fact in facts:
        for key, value in fact["identities"].items():
            if key in {"span_id", "parent_span_id"}:
                continue
            indexes[(key, value)].append(fact["id"])
        ids = fact["identities"]
        if ids.get("trace_id") and ids.get("span_id"):
            indexes[("span", ids["trace_id"] + "/" + ids["span_id"])].append(fact["id"])
    links = [{"method": "exact_identifier", "identity_type": key, "identity": value, "facts": members}
             for (key, value), members in sorted(indexes.items()) if len(members) > 1]
    for fact in facts:
        ids = fact["identities"]
        if ids.get("trace_id") and ids.get("parent_span_id"):
            parents = indexes.get(("span", ids["trace_id"] + "/" + ids["parent_span_id"]), [])
            if parents:
                links.append({"method": "documented_span_ancestry", "identity_type": "parent_span", "identity": ids["parent_span_id"],
                              "facts": [fact["id"], *parents]})
    for fact in facts:
        for relation in fact.get("relationships", ()):
            matches = indexes.get((relation["identity_type"], relation["identity"]), ())
            links.append({"method": "documented_structural_relationship", **relation, "facts": [fact["id"], *matches]})
    linked = {identity for link in links for identity in link["facts"]}
    return links, [fact["id"] for fact in facts if fact["id"] not in linked]


def _measurement(role, value, *, manifest, source="not_observed", definition, unit="1", classification="observed",
                 scope="invocation", evidence=(), reason="", availability=None, aggregation="sum", **extra):
    health = manifest.get("sources", {}).get(source, {})
    partial = any(health.get(key) for key in ("partial", "dropped", "rejected", "parse_errors")) or health.get("state") not in {"complete", "settled", "sealed"}
    sealed = bool(manifest.get("sealed"))
    status = availability or ("unavailable" if value is None else "partial" if partial or not sealed else "available")
    return {"id": role, "value": value, "unit": unit, "scope": scope,
            "authority": manifest.get("authority", "original"), "source": source, "classification": classification,
            "definition": definition, "method": "agmark.stock-telemetry-normalizer", "method_version": NORMALIZATION_VERSION,
            "availability": status, "reason": reason, "quality_reasons": [reason] if reason else [],
            "evidence_references": list(evidence), "coverage": {"sealed": sealed, "source_state": health.get("state", "unavailable"),
                "partial": partial, "received_events": health.get("received_events"), "dropped": health.get("dropped", 0),
                "rejected": health.get("rejected", 0), "parse_errors": health.get("parse_errors", 0)},
            "aggregation": aggregation, **extra}


def _usage_measurements(facts, manifest, contradictions):
    values = {}
    snapshots = [fact for fact in facts if fact["kind"] == "usage_snapshot"]
    responses = [fact for fact in facts if fact["kind"] == "completed_response_usage"]
    valid_responses = [fact for fact in responses if fact["usage"]["valid_identity"]]
    selected = snapshots[-1] if snapshots else valid_responses[-1] if valid_responses else None
    usage = selected["usage"] if snapshots else selected["usage"]["thread_token_usage"] if selected else {}
    authority = "Final token_count cumulative snapshot" if snapshots else "Final token_usage_record thread cumulative snapshot"
    if snapshots and valid_responses:
        other = valid_responses[-1]["usage"]["thread_token_usage"]
        for field in TOKEN_FIELDS.values():
            if field in usage and field in other and usage[field] != other[field]:
                contradictions.append({"reason": "cumulative_representations_disagree", "field": field,
                    "values": [usage[field], other[field]], "facts": [selected["id"], valid_responses[-1]["id"]]})
    invalid = set()
    for child, parent in (("cached_input_tokens", "input_tokens"), ("reasoning_output_tokens", "output_tokens")):
        left, right = _number(usage.get(child), integer=True), _number(usage.get(parent), integer=True)
        if left is not None and right is not None and left > right:
            invalid.add(child)
            contradictions.append({"reason": "token_subset_exceeds_parent", "field": child, "parent": parent,
                                   "facts": [selected["id"]]})
    for role, field in TOKEN_FIELDS.items():
        number = _number(usage.get(field), integer=True) if field not in invalid else None
        reason = "Invalid subset counter retained as a contradiction." if field in invalid else "No compatible cumulative counter observed." if number is None else ""
        values[role] = _measurement(role, number, manifest=manifest, source="rollout", unit="tokens",
            definition=f"{authority}: {field}; cumulative snapshots and source representations are never added.",
            evidence=[selected["id"]] if selected else [], reason=reason)
    paired = all(values[key]["value"] is not None for key in ("input_tokens", "cached_input_tokens"))
    inputs, cached = values["input_tokens"]["value"], values["cached_input_tokens"]["value"]
    for role, number, unit, definition in (
        ("cache_read_fraction", cached / inputs if paired and inputs else None, "ratio", "Cached input / input from the same selected cumulative snapshot; missing components are excluded, never zero."),
        ("uncached_input_tokens", inputs - cached if paired else None, "tokens", "Input minus cached input from the same selected cumulative snapshot; cached input is a subset.")):
        values[role] = _measurement(role, number, manifest=manifest, source="rollout", unit=unit,
            definition=definition, classification="derived", evidence=[selected["id"]] if paired else [],
            reason="" if number is not None else "Paired input/cache counters with a nonzero ratio denominator are unavailable.",
            aggregation="paired_ratio" if role == "cache_read_fraction" else "sum",
            cohort={"input_tokens": inputs, "cached_input_tokens": cached} if paired else None)
    seen = {}
    conflicts = set()
    for fact in valid_responses:
        usage_record = fact["usage"]
        identity = tuple(usage_record[key] for key in ("thread_id", "turn_id", "response_id"))
        if identity in seen and seen[identity]["usage"]["usage"] != usage_record["usage"]:
            conflicts.add(identity)
            contradictions.append({"reason": "conflicting_completed_response_usage", "identity": list(identity),
                                   "facts": [seen[identity]["id"], fact["id"]]})
        seen[identity] = fact
    for fact in responses:
        contradictions.extend({"reason": reason, "facts": [fact["id"]]} for reason in fact["usage"]["quality_reasons"])
    values["completed_response_usage_count"] = _measurement("completed_response_usage_count", len(seen) if responses else None,
        manifest=manifest, source="rollout", unit="responses", scope="completed_response_with_usage",
        definition="Distinct observed completed-response IDs carrying usage; not a provider request count.",
        evidence=[fact["id"] for fact in valid_responses], availability="partial" if conflicts else None,
        reason="Only completed responses carrying usage are represented; failed, retried and warmup coverage is unproven.")
    return values


def _native_metric_measurements(facts, manifest, contradictions):
    grouped = defaultdict(list)
    for fact in facts:
        if fact["kind"] == "metric":
            key = _canonical({key: fact.get(key) for key in ("metric_name", "metric_type", "unit", "dimensions", "resource", "instrumentation_scope", "temporality", "is_monotonic")})
            if not fact.get("dimensions_complete"):
                key += ":incomplete_scope:" + fact["id"]
            grouped[key].append(fact)
    values = {}
    for key, points in grouped.items():
        metric = points[-1]
        role = "native_metric:" + metric["metric_name"] + ":" + hashlib.sha256(key.encode()).hexdigest()[:12]
        # Retain temporal sequence; no delta/cumulative mixing, bucket merging,
        # or conversion of aggregate histograms into individual request rows.
        cumulative = metric["temporality"] in {2, "2", "AGGREGATION_TEMPORALITY_CUMULATIVE"}
        point = metric["native"]
        representation = {"metric_type": metric["metric_type"], "temporality": metric["temporality"],
                          "dimensions": metric["dimensions"], "instrumentation_scope": metric["instrumentation_scope"],
                          "resource": metric["resource"], "dimensions_complete": metric.get("dimensions_complete", False), "points": [fact["native"] for fact in points]}
        if cumulative and metric.get("dimensions_complete"):
            representation["selected_final_point"] = point
            representation["selection"] = "Final source-ordered cumulative point; earlier cumulative exports are not added."
        else:
            representation["selection"] = "Native ordered points retained; no overlap assumptions or inferred request rows."
        if metric["metric_type"] in {"histogram", "exponentialHistogram"}:
            number = representation
        elif (cumulative or metric["metric_type"] == "gauge") and metric.get("dimensions_complete"):
            number = _number(point.get("asInt", point.get("asDouble")))
        else:
            number = representation
        duplicate_points = {}
        for fact in points:
            item = fact["native"]
            period = (item.get("startTimeUnixNano"), item.get("timeUnixNano"))
            if period in duplicate_points and duplicate_points[period]["native"] != item:
                contradictions.append({"reason": "conflicting_native_metric_snapshot", "facts": [duplicate_points[period]["id"], fact["id"]]})
            duplicate_points[period] = fact
        values[role] = _measurement(role, number, manifest=manifest, source="otel_metrics", unit=metric["unit"],
            definition=metric["description"] or "Native stock metric with original dimensions, temporality and scope; not request rows.",
            scope="native_metric_series", evidence=[fact["id"] for fact in points], aggregation="retain_only", native=representation,
            reason="" if metric.get("dimensions_complete") else "Some native dimensions were excluded or unverified; points are retained separately and cannot establish matching series.",
            availability=None if metric.get("dimensions_complete") else "partial")
    return values


def _activity_measurements(facts, manifest):
    values = {}
    # Prefer one signal representation. Mirrored log/trace events are never added.
    requests = [fact for fact in facts if fact["kind"] == "request"]
    source = "otel_logs" if any(fact["source"] == "otel_logs" for fact in requests) else "otel_traces"
    requests = [fact for fact in requests if fact["source"] == source]
    identified = {}
    for fact in requests:
        identity = fact["identities"].get("request_id")
        if identity:
            identified.setdefault(identity, fact)
    values["provider_request_count"] = _measurement("provider_request_count", len(identified) if identified else None,
        manifest=manifest, source=source, unit="requests", scope="observed_identified_requests",
        definition="Distinct genuine request IDs in one authoritative stock signal; count is a lower bound on observed coverage.",
        evidence=[fact["id"] for fact in identified.values()], availability="partial" if identified else None,
        reason="Stock signals do not establish complete failed, retried or WebSocket warmup coverage.")
    durations = [(fact, _number(fact.get("attributes", {}).get("duration_ms"))) for fact in identified.values()]
    durations = [(fact, number) for fact, number in durations if number is not None]
    values["observed_request_duration_ms"] = _measurement("observed_request_duration_ms",
        sum(number for _, number in durations) / len(durations) if durations else None,
        manifest=manifest, source=source, unit="ms", scope="observed_identified_requests",
        definition="Mean stock request timer for identified requests; not exact wire latency or full inference lifecycle.",
        evidence=[fact["id"] for fact, _ in durations], availability="partial" if durations else None,
        reason="Available stock request timers only; uncorrelated request records remain retained.", aggregation="weighted_average",
        numerator=sum(number for _, number in durations), denominator=len(durations))
    for role, definition in (("average_direct_ttft_ms", "Client request to first actual token latency."),
                             ("average_direct_tbt_ms", "Mean interval between individual client token arrivals.")):
        values[role] = _measurement(role, None, manifest=manifest, unit="ms", definition=definition,
            reason="Stock capture does not expose individual token arrival times or exact wire boundaries.", aggregation="retain_only")
    proxies = []
    proxy_source = "otel_logs" if any(f["source"] == "otel_logs" and "ttft_ms" in f.get("attributes", {}) for f in facts) else "otel_traces"
    for fact in facts:
        attrs = fact.get("attributes", {})
        if fact["source"] == proxy_source:
            number = _number(attrs.get("ttft_ms"))
            if number is not None:
                proxies.append((fact, number))
    values["first_output_item_latency_ms"] = _measurement("first_output_item_latency_ms",
        sum(number for _, number in proxies) / len(proxies) if proxies else None, manifest=manifest,
        source=proxies[0][0]["source"] if proxies else "otel_logs", unit="ms", classification="proxy",
        definition="Mean stock first-output-item delay, not client token TTFT.", evidence=[fact["id"] for fact, _ in proxies],
        aggregation="weighted_average", numerator=sum(number for _, number in proxies), denominator=len(proxies))
    tools = [fact for fact in facts if fact["kind"] == "tool" and fact["source"] == "rollout"
             and fact["event_type"] in {"function_call", "custom_tool_call", "web_search_call"}]
    tool_ids = {fact["identities"].get("model_call_id", fact["identities"].get("tool_call_id")) for fact in tools} - {None}
    values["tool_calls"] = _measurement("tool_calls", len(tool_ids) if tools else None, manifest=manifest, source="rollout", unit="calls",
        definition="Distinct explicit rollout tool call IDs; uncorrelated tool records are retained separately.",
        evidence=[fact["id"] for fact in tools], reason="Unidentified tool events are excluded." if len(tool_ids) < len(tools) else "")
    for role, kind, unit in (("prompt_count", "prompt", "prompts"), ("completed_turn_count", "turn", "turns")):
        chosen = [fact for fact in facts if fact["kind"] == kind and (kind != "turn" or fact.get("event_type") == "task_complete")]
        values[role] = _measurement(role, len(chosen) if chosen else None, manifest=manifest, source="rollout", unit=unit,
            definition="Observed rollout " + ("user prompt records." if kind == "prompt" else "task_complete records."),
            evidence=[fact["id"] for fact in chosen])
    for role, identity_type, event_type, unit in (("diagnostic_inference_count", "inference_call_id", "inference_started", "calls"),
            ("diagnostic_tool_call_count", "tool_call_id", "tool_call_started", "calls"),
            ("diagnostic_code_cell_count", "runtime_cell_id", "code_cell_started", "cells")):
        selected = [fact for fact in facts if fact["kind"] == "diagnostic" and fact.get("event_type") == event_type]
        identities = {fact["identities"].get(identity_type) for fact in selected} - {None}
        values[role] = _measurement(role, len(identities) if identities else None, manifest=manifest, source="diagnostics", unit=unit,
            scope="diagnostic_observed_lifecycles", definition="Distinct explicit stock diagnostic lifecycle identities; not complete transport/warmup coverage.",
            evidence=[fact["id"] for fact in selected], reason="Diagnostic profile adds overhead and is not comparable with standard capture.")
    values["cost"] = _measurement("cost", None, manifest=manifest, unit="currency", definition="Cost from compatible billing and retained pricing evidence.",
        reason="Stock usage counters alone do not establish billing cost.", aggregation="retain_only")
    start, end = manifest.get("started_at_unix_ns"), manifest.get("finished_at_unix_ns")
    lifecycle = [fact for fact in facts if fact["kind"] == "lifecycle"]
    # Invocation collector lifetime includes finalization; call it that explicitly.
    elapsed = (end - start) / 1_000_000 if type(start) is int and type(end) is int and end >= start else None
    values["capture_duration"] = _measurement("capture_duration", elapsed, manifest=manifest, source="process", unit="ms",
        definition="Capture wall-clock span including receiver drain and evidence finalization; not model or benchmark elapsed time.",
        evidence=[fact["id"] for fact in lifecycle], classification="derived")
    return values


def normalize_capture(manifest):
    """Normalize captured sanitized records, keeping original/replay authority apart."""
    from .evidence import validate_manifest
    validate_manifest(manifest)
    supplied = manifest["records"]
    facts, excluded = [], []
    for record in supplied:
        if not isinstance(record, dict) or record.get("sanitized") is not True:
            excluded.append({"reason": "Record is not labeled sanitized.", "evidence_reference": record.get("evidence_id") if isinstance(record, dict) else None})
            continue
        record = {**record, "evidence_id": str(manifest.get("invocation_id", "unknown")) + "/" + record.get("evidence_id", str(record.get("source_sequence")))}
        try:
            facts.extend(_parse_record(record, manifest))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            facts.append(_fact(record, kind="unparsed", identities={}, native=deepcopy(record.get("payload")), reason=type(exc).__name__))
    contradictions = []
    for fact in facts:
        conflicts = fact["identities"].pop("_identity_conflicts", {})
        if conflicts:
            fact["identity_conflicts"] = conflicts
            contradictions.append({"reason": "conflicting_identity_aliases", "fields": conflicts, "facts": [fact["id"]]})
        attr_conflicts = fact.get("attributes", fact.get("dimensions", {})).get("_attribute_conflicts", {})
        if attr_conflicts:
            contradictions.append({"reason": "conflicting_native_attributes", "fields": attr_conflicts, "facts": [fact["id"]]})
    links, uncorrelated = _correlate(facts)
    measurements = _usage_measurements(facts, manifest, contradictions)
    measurements.update(_activity_measurements(facts, manifest))
    measurements.update(_native_metric_measurements(facts, manifest, contradictions))
    return {"schema_version": "agmark.telemetry.normalized.v2", "parser_version": NORMALIZATION_VERSION,
            "invocation_id": manifest.get("invocation_id"), "authority": manifest.get("authority", "original"),
            "profile": deepcopy(manifest.get("profile", {})), "runtime": deepcopy(manifest.get("runtime", {})),
            "sealed": bool(manifest.get("sealed")), "facts": facts, "correlations": links,
            "uncorrelated": uncorrelated, "contradictions": contradictions, "measurements": measurements,
            "sources": deepcopy(manifest.get("sources", {})), "exclusions": excluded,
            "privacy": deepcopy(manifest.get("privacy", {})), "completeness": deepcopy(manifest.get("completeness", {})),
            "process_status": deepcopy(manifest.get("process_status", {})), "capture_integrity": deepcopy(manifest.get("integrity", {}))}


def _runtime_capture_identity(runtime):
    """Stable capability/runtime conditions, excluding per-invocation identity.

    Runtime version alone cannot establish binary or instrumentation equivalence.
    Request/frame hashes and accepted treatment boundaries deliberately stay out:
    they identify evidence contributors rather than capture capability.
    """
    fields = ("version", "launch_mode", "receiver_environment", "capability_status", "capability_version",
              "evidence_commit", "capabilities", "binary_sha256", "binary_hash_reason", "runner_id", "runner_version",
              "delivery", "complete_request_coverage", "individual_token_arrival_times", "exact_wire_latency", "reason")
    identity = {field: deepcopy(runtime.get(field)) for field in fields}
    signals = runtime.get("signals")
    identity["signals"] = sorted(set(signals)) if isinstance(signals, list) and all(isinstance(item, str) for item in signals) else deepcopy(signals)
    return identity


def aggregate_telemetry(documents):
    """Pool compatible invocations once; preserve incompatible groups and exclusions."""
    groups, exclusions, identities = defaultdict(list), [], set()
    for document in documents:
        identity = (document.get("authority", "original"), document.get("invocation_id"))
        if identity[1] is None or identity in identities:
            exclusions.append({"invocation_id": identity[1], "reason": "Missing or duplicate invocation identity."})
            continue
        identities.add(identity)
        runtime_identity = _runtime_capture_identity(document.get("runtime", {}))
        compatibility = {"profile": document.get("profile", {}), "authority": identity[0],
                         "runtime_version": runtime_identity["version"], "runtime": runtime_identity,
                         "parser_version": document.get("parser_version")}
        groups[_canonical(compatibility)].append(document)
    results = []
    for compatibility, members in groups.items():
        roles = set().union(*(document.get("measurements", {}) for document in members))
        measurements = {}
        for role in sorted(roles):
            entries = [(document, document["measurements"][role]) for document in members if role in document.get("measurements", {})]
            usable = [(document, value) for document, value in entries if value.get("value") is not None]
            sample = deepcopy(entries[0][1])
            signatures = {_canonical({key: value.get(key) for key in ("unit", "scope", "authority", "source", "classification", "definition", "method", "method_version", "aggregation")}) for _, value in usable}
            excluded = [{"invocation_id": document["invocation_id"], "reason": document.get("measurements", {}).get(role, {}).get("reason") or "Metric unavailable."}
                        for document in members if document not in [member for member, _ in usable]]
            sample.update(contributors=[document["invocation_id"] for document, _ in usable], exclusions=excluded,
                evidence_references=sorted({reference for _, value in usable for reference in value.get("evidence_references", ())}))
            aggregation = sample.get("aggregation", "retain_only")
            if len(signatures) > 1:
                sample.update(value=None, availability="non_comparable", reason="Metric scopes, authorities or methods differ.")
            elif not usable:
                sample.update(value=None, availability="unavailable")
            elif aggregation == "retain_only":
                sample.update(value=usable[0][1]["value"] if len(usable) == 1 else None,
                              availability=usable[0][1]["availability"] if len(usable) == 1 else "non_comparable",
                              reason="Native distributions/series retained per invocation; not pooled into request rows.",
                              inputs=[value for _, value in usable])
            elif aggregation == "paired_ratio":
                cohorts = [value["cohort"] for _, value in usable if value.get("cohort") is not None]
                numerator = sum(item["cached_input_tokens"] for item in cohorts)
                denominator = sum(item["input_tokens"] for item in cohorts)
                sample.update(value=numerator / denominator if denominator else None, numerator=numerator, denominator=denominator)
            elif aggregation == "weighted_average":
                numerator = sum(value["numerator"] for _, value in usable)
                denominator = sum(value["denominator"] for _, value in usable)
                sample.update(value=numerator / denominator if denominator else None, numerator=numerator, denominator=denominator)
            else:
                sample["value"] = sum(value["value"] for _, value in usable)
            if sample["value"] is not None and sample["availability"] != "non_comparable":
                sample["availability"] = "partial" if excluded or any(value["availability"] != "available" for _, value in usable) else "available"
            sample["coverage"] = {"measured_invocations": len(usable), "observed_invocations": len(members), "sealed": all(member.get("sealed") for member in members)}
            measurements[role] = sample
        results.append({"schema_version": "agmark.telemetry.aggregate.v2", **json.loads(compatibility),
                        "sealed": all(member.get("sealed") for member in members), "measurements": measurements,
                        "contributors": [member["invocation_id"] for member in members], "invocations": members,
                        "sources": {}, "contradictions": [item for member in members for item in member.get("contradictions", ())]})
    return {"schema_version": "agmark.telemetry.aggregate.v2", "groups": results, "exclusions": exclusions,
            "measurements": results[0]["measurements"] if len(results) == 1 else {},
            "availability": "available" if len(results) == 1 else "non_comparable" if results else "unavailable"}


def reconstruct_capture_extensions(extensions):
    """Verify and reconstruct retained normalization; never trust supplied facts.

    Callers surface a failure as unusable telemetry, independently of registered
    response scoring. Historical observations without either extension are valid.
    """
    from .evidence import canonical_bytes, digest, validate_manifest
    capture = extensions.get(CAPTURE_EXTENSION)
    retained = extensions.get(NORMALIZED_EXTENSION)
    if capture is None:
        if retained is not None:
            raise ValueError("Normalized telemetry lacks retained capture evidence.")
        return None
    validate_manifest(capture)
    if capture.get("authority") != "original":
        raise ValueError("Original observation cannot use replay capture authority.")
    cache_key = (NORMALIZATION_VERSION, capture["integrity"]["manifest_sha256"])
    retained_bytes = canonical_bytes(retained) if retained is not None else None
    retained_digest = digest(retained_bytes) if retained_bytes is not None else None
    with _RECONSTRUCTION_CACHE_LOCK:
        verified_digest = _RECONSTRUCTION_DIGESTS.get(cache_key)
        if verified_digest is not None:
            _RECONSTRUCTION_DIGESTS.move_to_end(cache_key)
    if verified_digest is not None and retained_bytes is not None:
        if retained_digest != verified_digest:
            raise ValueError("Normalized telemetry does not reconstruct from sealed capture evidence.")
        # Independent decoded snapshots prevent caller mutation from poisoning a
        # later projection. The bounded cache itself retains only SHA-256 values.
        return json.loads(retained_bytes)
    reconstructed = normalize_capture(capture)
    reconstructed_digest = digest(canonical_bytes(reconstructed))
    if retained is not None and retained_digest != reconstructed_digest:
        raise ValueError("Normalized telemetry does not reconstruct from sealed capture evidence.")
    with _RECONSTRUCTION_CACHE_LOCK:
        _RECONSTRUCTION_DIGESTS[cache_key] = reconstructed_digest
        _RECONSTRUCTION_DIGESTS.move_to_end(cache_key)
        while len(_RECONSTRUCTION_DIGESTS) > _RECONSTRUCTION_CACHE_LIMIT:
            _RECONSTRUCTION_DIGESTS.popitem(last=False)
    return reconstructed
