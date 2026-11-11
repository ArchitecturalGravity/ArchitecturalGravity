"""Offline normalized authority, retained reconstruction and projection evidence."""
from copy import deepcopy
import hashlib
import unittest

from AgMark.shared.telemetry.evidence import EvidenceLedger
from AgMark.shared.telemetry.privacy import Sanitizer
from AgMark.shared.telemetry.profile import CaptureProfile, capability
from AgMark.shared.telemetry.normalization import (
    aggregate_telemetry, normalize_capture, reconstruct_capture_extensions,
)
from AgMark.shared.telemetry.projection import project_telemetry, project_treatment_telemetry
from AgMark.shared.evaluation.telemetry.consumption import ATTEMPT_MEASUREMENTS, aggregate_treatment_measurements
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import extract


def usage(inputs=100, cached=40):
    return {"input_tokens": inputs, "cached_input_tokens": cached, "output_tokens": 20,
            "reasoning_output_tokens": 5, "total_tokens": inputs + 20}


def response(identity="response-1", counters=None):
    counters = counters or usage()
    return {"type": "token_usage_record", "payload": {"thread_id": "trial", "turn_id": "turn-1",
        "session_id": "trial", "root_turn_id": "turn-1", "response_id": identity,
        "usage": counters, "turn_token_usage": counters, "thread_token_usage": counters}}


def snapshot(counters=None):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": counters or usage()}}}


def attrs(**values):
    return [{"key": key, "value": {"stringValue" if isinstance(value, str) else "intValue": value}} for key, value in values.items()]


def fixture_identity(label):
    if label.startswith("observation:") and len(label) == 76:
        return label
    return "observation:" + hashlib.sha256(label.encode()).hexdigest()


def manifest(records=(), *, identity="invocation-1", profile=None, version="0.159.0", runtime_overrides=None):
    identity = fixture_identity(identity)
    ledger = EvidenceLedger(profile or CaptureProfile(), identity, capability(version))
    ledger.runtime.update(runtime_overrides or {})
    for source in ledger.sources:
        ledger.state(source, "disabled")
    for source, payload in records:
        sanitizer = Sanitizer(aliases=ledger.aliases, source=source)
        safe = sanitizer.value(payload)
        for key in ("_sanitization", "graph_family"):
            if key in payload:
                safe[key] = payload[key]
        if "_scope" in payload:
            safe["_scope"] = sanitizer.value(payload["_scope"])
        if payload.get("type") == "reduced_graph_node":
            safe.update(type="reduced_graph_node", graph_object_id=ledger.aliases.identity(payload["graph_object_id"]),
                        node=sanitizer.value(payload["node"]))
        ledger.add(source, safe)
    for source in {source for source, _ in records}:
        ledger.state(source, "settled")
    return ledger.seal(process_status={"status": "completed"})


class NormalizationTests(unittest.TestCase):
    def test_final_cumulative_once_and_response_records_distinct(self):
        result = normalize_capture(manifest([("rollout", snapshot(usage(30, 10))), ("rollout", response()),
                                              ("rollout", snapshot()), ("rollout", snapshot())]))
        self.assertEqual(100, result["measurements"]["input_tokens"]["value"])
        self.assertEqual(1, result["measurements"]["completed_response_usage_count"]["value"])
        self.assertEqual(.4, result["measurements"]["cache_read_fraction"]["value"])
        self.assertEqual("completed_response_with_usage", result["measurements"]["completed_response_usage_count"]["scope"])
        self.assertIsNone(result["measurements"]["provider_request_count"]["value"])

    def test_response_fallback_capability_gate_and_unknown_retention(self):
        known = normalize_capture(manifest([("rollout", response())]))
        self.assertEqual(100, known["measurements"]["input_tokens"]["value"])
        unknown = normalize_capture(manifest([("rollout", response())], version="0.160.0"))
        self.assertIsNone(unknown["measurements"]["input_tokens"]["value"])
        self.assertEqual(Sanitizer().value(response()), unknown["facts"][0]["native"])
        self.assertEqual("unknown", unknown["facts"][0]["kind"])

    def test_invalid_subsets_and_disagreement_retained(self):
        invalid = usage(cached=101)
        result = normalize_capture(manifest([("rollout", response()), ("rollout", snapshot(invalid))]))
        self.assertIsNone(result["measurements"]["cached_input_tokens"]["value"])
        self.assertIsNone(result["measurements"]["cache_read_fraction"]["value"])
        self.assertEqual({"token_subset_exceeds_parent", "cumulative_representations_disagree"},
                         {item["reason"] for item in result["contradictions"]})
        self.assertEqual(101, result["facts"][-1]["native"]["payload"]["info"]["total_token_usage"]["cached_input_tokens"])

    def test_repeated_response_ids_deduplicate_and_contradictions_survive(self):
        result = normalize_capture(manifest([("rollout", response()), ("rollout", response()),
                                              ("rollout", response(counters=usage(200, 50)))]))
        self.assertEqual(1, result["measurements"]["completed_response_usage_count"]["value"])
        self.assertEqual("partial", result["measurements"]["completed_response_usage_count"]["availability"])
        self.assertTrue(any(item["reason"] == "conflicting_completed_response_usage" for item in result["contradictions"]))

    def test_exact_id_and_span_ancestry_only_never_timestamp_proximity(self):
        events = [("otel_logs", {"timeUnixNano": "50", "attributes": attrs(**{"event.name": "future", "request_id": "req-1"})}),
                  ("otel_logs", {"timeUnixNano": "50", "attributes": attrs(**{"event.name": "future"})}),
                  ("otel_traces", {"name": "parent", "traceId": "a" * 32, "spanId": "b" * 16}),
                  ("otel_traces", {"name": "child", "traceId": "a" * 32, "spanId": "c" * 16, "parentSpanId": "b" * 16})]
        result = normalize_capture(manifest(events))
        self.assertIn(fixture_identity("invocation-1") + "/otel_logs:2", result["uncorrelated"])
        self.assertTrue(any(item["method"] == "documented_span_ancestry" for item in result["correlations"]))
        self.assertFalse(any("otel_logs:2" in ref for item in result["correlations"] for ref in item["facts"]))

    def test_conflicting_aliases_and_duplicate_attributes_never_create_joins(self):
        payload = {"request_id": "one", "attributes": attrs(request_id="two")}
        duplicate = {"attributes": attrs(request_id="one") + attrs(request_id="two")}
        result = normalize_capture(manifest([("otel_logs", payload), ("otel_logs", duplicate)]))
        self.assertEqual({}, result["facts"][0]["identities"])
        self.assertEqual({}, result["facts"][1]["identities"])
        self.assertEqual({"conflicting_identity_aliases", "conflicting_native_attributes"},
                         {item["reason"] for item in result["contradictions"]})
        self.assertFalse(result["correlations"])

    def test_private_or_unknown_dimensions_cannot_collapse_metric_series(self):
        metric = {"name": "codex.calls", "sum": {"aggregationTemporality": 2, "dataPoints": [{"asInt": "4"}]},
                  "_sanitization": {"dimensions_complete": False}}
        result = normalize_capture(manifest([("otel_metrics", metric), ("otel_metrics", metric)]))
        entries = [value for key, value in result["measurements"].items() if key.startswith("native_metric:")]
        self.assertEqual(2, len(entries))
        self.assertTrue(all(value["availability"] == "partial" for value in entries))
        self.assertTrue(all(isinstance(value["value"], dict) for value in entries))

    def test_multi_signal_request_authority_is_not_added_and_proxies_labeled(self):
        payload = {"attributes": attrs(**{"event.name": "codex.api_request", "auth.request_id": "req-1", "duration_ms": "25", "ttft_ms": 10})}
        result = normalize_capture(manifest([("otel_logs", payload), ("otel_traces", payload)]))
        self.assertEqual(1, result["measurements"]["provider_request_count"]["value"])
        self.assertEqual(25, result["measurements"]["observed_request_duration_ms"]["value"])
        self.assertEqual("proxy", result["measurements"]["first_output_item_latency_ms"]["classification"])
        self.assertIsNone(result["measurements"]["average_direct_ttft_ms"]["value"])

    def test_native_histograms_preserve_buckets_dimensions_scope_and_temporality(self):
        metric = {"name": "codex.api_request.duration_ms", "unit": "ms", "_scope": {"name": "codex"},
                  "_sanitization": {"dimensions_complete": True},
                  "histogram": {"aggregationTemporality": 2, "dataPoints": [{"attributes": attrs(status="200"),
                    "count": "2", "sum": 32, "bucketCounts": ["1", "1"], "explicitBounds": [20],
                    "startTimeUnixNano": "1", "timeUnixNano": "5"}]}}
        later = deepcopy(metric)
        later["histogram"]["dataPoints"][0].update(count="3", sum=50, timeUnixNano="9", bucketCounts=["1", "2"])
        result = normalize_capture(manifest([("otel_metrics", metric), ("otel_metrics", later)]))
        item = next(value for key, value in result["measurements"].items() if key.startswith("native_metric:"))
        self.assertEqual("3", item["value"]["selected_final_point"]["count"])
        self.assertEqual(["1", "2"], item["value"]["selected_final_point"]["bucketCounts"])
        self.assertEqual({"status": "200"}, item["value"]["dimensions"])
        self.assertEqual(2, len(item["value"]["points"]))
        self.assertIsNone(result["measurements"]["provider_request_count"]["value"])

    def test_diagnostic_exact_edges_and_lifecycles_are_separate_scope(self):
        events = [("diagnostics", {"schema_version": 1, "seq": 1, "thread_id": "parent", "payload": {"type": "thread_started", "thread_id": "parent"}}),
                  ("diagnostics", {"schema_version": 1, "seq": 2, "payload": {"type": "agent_result_observed", "edge_id": "edge", "parent_thread_id": "parent", "child_thread_id": "child"}}),
                  ("diagnostics", {"schema_version": 1, "seq": 3, "payload": {"type": "inference_started", "inference_call_id": "inference", "codex_turn_id": "turn"}})]
        result = normalize_capture(manifest(events, profile=CaptureProfile("deep_telemetry", True)))
        self.assertEqual(1, result["measurements"]["diagnostic_inference_count"]["value"])
        self.assertTrue(any(link["method"] == "documented_structural_relationship" for link in result["correlations"]))

    def test_reduced_graph_terminal_links_retained_without_lifecycle_double_count(self):
        records = [("diagnostics", {"type": "reduced_graph_node", "graph_family": "terminal_operations", "graph_object_id": "operation",
                     "trace_id": "diagnostic-trace", "node": {"operation_id": "operation", "terminal_id": "terminal", "tool_call_id": "tool"}}),
                   ("diagnostics", {"type": "reduced_graph_node", "graph_family": "tool_calls", "graph_object_id": "tool",
                     "trace_id": "diagnostic-trace", "node": {"tool_call_id": "tool", "terminal_operation_id": "operation"}})]
        result = normalize_capture(manifest(records))
        self.assertTrue(all(fact["kind"] == "diagnostic_graph" and fact["classification"] == "derived" for fact in result["facts"]))
        self.assertTrue(any(link.get("identity_type") == "terminal_operation_id" for link in result["correlations"]))
        self.assertIsNone(result["measurements"]["diagnostic_tool_call_count"]["value"])

    def test_zero_otel_ids_cannot_correlate_unrelated_events(self):
        payload = {"traceId": "0" * 32, "spanId": "0" * 16}
        result = normalize_capture(manifest([("otel_logs", payload), ("otel_logs", payload)]))
        self.assertFalse(result["correlations"])
        self.assertEqual(2, len(result["uncorrelated"]))

    def test_paired_cohort_aggregation_excludes_missing_not_zero(self):
        first = normalize_capture(manifest([("rollout", snapshot())], identity="a"))
        second = normalize_capture(manifest([("rollout", snapshot({"input_tokens": 900}))], identity="b"))
        total = aggregate_telemetry([first, second])
        self.assertEqual(.4, total["measurements"]["cache_read_fraction"]["value"])
        self.assertEqual([fixture_identity("a")], total["measurements"]["cache_read_fraction"]["contributors"])
        self.assertEqual("partial", total["measurements"]["cache_read_fraction"]["availability"])
        self.assertEqual(1, len(total["measurements"]["cache_read_fraction"]["exclusions"]))

    def test_profiles_and_authorities_not_pooled_duplicates_excluded(self):
        first = normalize_capture(manifest([("rollout", snapshot())], identity="a"))
        other = normalize_capture(manifest([("rollout", snapshot())], identity="b", profile=CaptureProfile("deep_telemetry", True)))
        replay = deepcopy(first)
        replay["authority"] = "replay"
        result = aggregate_telemetry([first, other, first, replay])
        self.assertEqual(3, len(result["groups"]))
        self.assertEqual({}, result["measurements"])
        self.assertEqual(1, len(result["exclusions"]))
        self.assertEqual("non_comparable", result["availability"])

    def test_runtime_capture_capabilities_binary_and_environment_must_match(self):
        first = normalize_capture(manifest([("rollout", snapshot())], identity="a"))
        first["runtime"].update(binary_sha256="sha256:binary-a", receiver_environment="native")
        changes = {"launch_mode": "wsl", "receiver_environment": "selected_distribution",
                   "capability_status": "unsupported", "signals": ["traces"], "binary_sha256": "sha256:binary-b",
                   "evidence_commit": "different-audit", "capabilities": {"token_usage_record_v1": False},
                   "delivery": "different-delivery", "runner_version": "different-runner"}
        for field, value in changes.items():
            with self.subTest(field=field):
                second = deepcopy(first)
                second["invocation_id"] = "b"
                second["runtime"][field] = value
                result = aggregate_telemetry([first, second])
                self.assertEqual(2, len(result["groups"]))
                self.assertEqual("non_comparable", result["availability"])
                self.assertEqual({}, result["measurements"])
        unknown_binary = deepcopy(first)
        unknown_binary["invocation_id"] = "unknown-binary"
        unknown_binary["runtime"]["binary_sha256"] = None
        self.assertEqual(2, len(aggregate_telemetry([first, unknown_binary])["groups"]))

    def test_runtime_capture_compatibility_excludes_invocation_hashes_and_signal_order(self):
        first = normalize_capture(manifest([("rollout", snapshot())], identity="a"))
        second = normalize_capture(manifest([("rollout", snapshot())], identity="b"))
        first["runtime"].update(accepted_boundary_fingerprint="boundary-a", framed_request_sha256="frame-a", treatment_id="treatment-a")
        second["runtime"].update(accepted_boundary_fingerprint="boundary-b", framed_request_sha256="frame-b", treatment_id="treatment-b")
        second["runtime"]["signals"].reverse()
        result = aggregate_telemetry([first, second])
        self.assertEqual(1, len(result["groups"]))
        self.assertEqual(200, result["measurements"]["input_tokens"]["value"])
        runtime = result["groups"][0]["runtime"]
        self.assertNotIn("framed_request_sha256", runtime)
        self.assertNotIn("accepted_boundary_fingerprint", runtime)
        self.assertNotIn("treatment_id", runtime)
        self.assertEqual(["logs", "metrics", "traces"], runtime["signals"])

    def test_reconstruction_rejects_forged_measurements_and_capture_bytes(self):
        capture = manifest([("rollout", snapshot())])
        extensions = {"agmark.telemetry:capture": capture, "agmark.telemetry:normalized": normalize_capture(capture)}
        self.assertEqual(extensions["agmark.telemetry:normalized"], reconstruct_capture_extensions(extensions))
        extensions["agmark.telemetry:normalized"]["measurements"]["input_tokens"]["value"] = 200
        with self.assertRaisesRegex(ValueError, "reconstruct"):
            reconstruct_capture_extensions(extensions)
        capture["records"][0]["payload"]["unknown"] = 10
        with self.assertRaisesRegex(ValueError, "integrity"):
            reconstruct_capture_extensions(extensions)

    def test_projection_keeps_shared_roles_original_and_exposes_native_evidence(self):
        result = normalize_capture(manifest([("rollout", snapshot())]))
        view = project_treatment_telemetry({"roles": {"total_tokens": {"value": 9, "availability": "available", "unit": "tokens"}}, "telemetry": result})
        self.assertEqual(9, view["overview"]["total_tokens"]["value"])
        self.assertTrue(any(row["id"].startswith("event:") for section in view["sections"] for row in section["rows"]))
        self.assertTrue(all({"id", "definition", "source", "classification", "coverage", "reason", "evidence_references"} <= row.keys()
                            for section in view["sections"] for row in section["rows"]))
        result["sealed"] = False
        self.assertEqual("Provisional", project_telemetry(result)["overview"]["telemetry_completeness"]["value"])
        legacy = project_treatment_telemetry({})
        self.assertEqual("Session evidence", legacy["overview"]["telemetry_completeness"]["value"])
        self.assertEqual("Session evidence", next(row for section in legacy["sections"] for row in section["rows"] if row["id"] == "telemetry_completeness")["value"])

    def test_aggregate_projection_keeps_disabled_diagnostics_out_of_capture_gaps(self):
        documents = []
        for identity in (fixture_identity("first"), fixture_identity("second")):
            ledger = EvidenceLedger(CaptureProfile(), identity, capability("0.159.0"))
            ledger.add("rollout", snapshot(), received_bytes=25)
            for source in ledger.sources:
                ledger.state(source, "disabled" if source == "diagnostics" else "settled")
            capture = ledger.seal(process_status={"status": "completed"})
            self.assertEqual("complete", capture["completeness"]["status"])
            documents.append(normalize_capture(capture))
            retained = deepcopy(documents)
            view = project_treatment_telemetry({"telemetry": aggregate_telemetry(documents)})
            completeness = view["overview"]["telemetry_completeness"]
            self.assertEqual("Sealed", completeness["value"])
            self.assertEqual("available", completeness["availability"])
            self.assertEqual(["diagnostics"], completeness["coverage"]["disabled_sources"])
            self.assertEqual([], completeness["coverage"]["incomplete_sources"])
            self.assertEqual("disabled", view["sources"]["diagnostics"]["state"])
            self.assertEqual(len(documents), view["sources"]["rollout"]["received_events"])
            self.assertEqual(25 * len(documents), view["sources"]["rollout"]["received_bytes"])
            self.assertEqual(retained, documents)

    def test_aggregate_projection_combines_terminal_states_without_losing_gaps(self):
        cases = (
            (("settled", "complete", "sealed"), "complete", "Sealed"),
            (("disabled", "disabled"), "disabled", "Sealed"),
            (("unavailable",), "unavailable", "Partial"),
            (("unavailable", "unavailable"), "unavailable", "Partial"),
            (("unsupported", "unsupported"), "unsupported", "Partial"),
            (("disabled", "settled"), "mixed", "Partial"),
            (("settled", "unavailable"), "mixed", "Partial"),
            (("unavailable", "settled"), "mixed", "Partial"),
        )
        for states, expected_state, expected_completeness in cases:
            with self.subTest(states=states):
                documents = []
                for index, state in enumerate(states):
                    document = normalize_capture(manifest(identity=str(index)))
                    document["sources"]["otel_logs"].update(state=state, reason="retained source reason")
                    documents.append(document)
                view = project_treatment_telemetry({"telemetry": aggregate_telemetry(documents)})
                summary = view["sources"]["otel_logs"]
                self.assertEqual(expected_state, summary["state"])
                self.assertEqual(list(states), [item["state"] for item in summary["invocations"]])
                self.assertEqual("retained source reason", summary["reason"])
                self.assertEqual(expected_completeness, view["overview"]["telemetry_completeness"]["value"])

    def test_non_comparable_aggregate_projection_preserves_original_provenance(self):
        for incompatibility in ("profile", "runtime", "parser"):
            with self.subTest(incompatibility=incompatibility):
                first = normalize_capture(manifest([("rollout", snapshot())], identity="first"))
                second_profile = CaptureProfile("deep_telemetry", True) if incompatibility == "profile" else CaptureProfile()
                second = normalize_capture(manifest([("rollout", snapshot())], identity="second", profile=second_profile))
                if incompatibility == "runtime":
                    second["runtime"]["binary_sha256"] = "different-runtime-binary"
                elif incompatibility == "parser":
                    second["parser_version"] = "different-parser-version"
                first["contradictions"].append({"reason": "retained original contradiction"})
                replay = deepcopy(first)
                replay.update(authority="replay", invocation_id="replay")
                aggregate = aggregate_telemetry([first, second, replay])
                retained = deepcopy(aggregate)
                view = project_treatment_telemetry({"telemetry": aggregate, "run_status": "Completed",
                    "roles": {"total_tokens": {"value": 240, "availability": "available", "unit": "tokens"}}})
                self.assertEqual("non_comparable", view["availability"])
                self.assertEqual("Non-comparable", view["overview"]["telemetry_completeness"]["value"])
                self.assertEqual("non_comparable", view["overview"]["telemetry_completeness"]["availability"])
                self.assertIn("not pooled", view["reason"])
                self.assertFalse(view["provisional"])
                self.assertEqual("Completed", view["overview"]["run_status"]["value"])
                self.assertEqual({fixture_identity("first"), fixture_identity("second")}, {item["invocation_id"] for item in view["invocations"]})
                self.assertEqual(2, len(view["compatibility_groups"]))
                self.assertEqual(2, len(view["sources"]["rollout"]["invocations"]))
                self.assertTrue(all(item["capture_integrity"] for item in view["invocations"]))
                event_rows = [row for section in view["sections"] for row in section["rows"] if row["id"].startswith("event:")]
                self.assertEqual({"event:" + fixture_identity(label) + "/rollout:1" for label in ("first", "second")}, {row["id"] for row in event_rows})
                self.assertTrue(all(row["evidence_references"] for row in event_rows))
                tokens = view["overview"]["total_tokens"]
                self.assertIsNone(tokens["value"])
                self.assertEqual("non_comparable", tokens["availability"])
                self.assertEqual([120, 120], [item["measurement"]["value"] for item in tokens["coverage"]["group_measurements"]])
                self.assertEqual("2 incompatible capture groups", tokens["coverage_text"])
                self.assertIn({"reason": "retained original contradiction"}, view["contradictions"])
                self.assertEqual(retained, aggregate)

    def test_public_original_roles_use_expanded_runtime_compatibility(self):
        def document(identity, runtime):
            envelope, _ = extract(thread=identity)
            capture = manifest([("rollout", snapshot())], identity=identity, runtime_overrides=runtime)
            return {"observation_id": fixture_identity(identity), "accepted_generation_id": "g", "treatment_id": "t",
                    "attempts": [{"attempt": 1, "status": "succeeded", "started_at": "2026-10-01T00:00:00Z", "completed_at": "2026-10-01T00:00:01Z"}],
                    "extensions": {ATTEMPT_MEASUREMENTS: envelope, "agmark.telemetry:capture": capture,
                                   "agmark.telemetry:normalized": normalize_capture(capture), "fixture:score": {"accuracy": 1}}}
        first = document("a", {"binary_sha256": "sha256:" + "a" * 64, "receiver_environment": "native"})
        for runtime in ({"binary_sha256": "sha256:" + "b" * 64, "receiver_environment": "native"},
                        {"binary_sha256": "sha256:" + "a" * 64, "receiver_environment": "selected_distribution", "launch_mode": "wsl"},
                        {"binary_sha256": "sha256:" + "a" * 64, "receiver_environment": "native", "signals": ["traces"]}):
            with self.subTest(runtime=runtime):
                second = document("b", runtime)
                before = deepcopy([first, second])
                result = aggregate_treatment_measurements([(first, "evidence-a"), (second, "evidence-b")],
                    generation_id="g", planned_observations={"t": 2})["t"]
                self.assertEqual("non_comparable", result["telemetry"]["availability"])
                for role in ("input_tokens", "cache_read_fraction", "duration", "tool_calls"):
                    self.assertIsNone(result["roles"][role]["value"])
                    self.assertEqual("non_comparable", result["roles"][role]["availability"])
                    self.assertIn("runtime capabilities", result["roles"][role]["details"]["reason"])
                self.assertEqual(before, [first, second])
        second = document("b", {"binary_sha256": "sha256:" + "a" * 64, "receiver_environment": "native",
                                "accepted_boundary_fingerprint": "sha256:" + "c" * 64, "framed_request_sha256": "sha256:" + "d" * 64})
        result = aggregate_treatment_measurements([(first, "evidence-a"), (second, "evidence-b")],
            generation_id="g", planned_observations={"t": 2})["t"]
        self.assertEqual("available", result["telemetry"]["availability"])
        self.assertEqual(200, result["roles"]["input_tokens"]["value"])
        self.assertEqual(.4, result["roles"]["cache_read_fraction"]["value"])
        self.assertEqual(1000, result["roles"]["duration"]["value"])

    def test_capture_cannot_be_transplanted_between_observations_or_known_bindings(self):
        envelope, _ = extract()
        for mismatch, capture_id, capture_boundary, capture_frame in (
                ("owning observation", "observation-a", "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"),
                ("execution boundary", "observation-b", "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"),
                ("framed request", "observation-b", "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")):
            with self.subTest(mismatch=mismatch):
                capture = manifest([("rollout", snapshot())], identity=capture_id,
                    runtime_overrides={"accepted_boundary_fingerprint": capture_boundary, "framed_request_sha256": capture_frame})
                document = {"observation_id": fixture_identity("observation-b"), "accepted_generation_id": "g", "treatment_id": "t",
                            "execution_boundary_fingerprint": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "attempts": [{"attempt": 1}],
                            "extensions": {ATTEMPT_MEASUREMENTS: envelope, "agmark.telemetry:capture": capture,
                                           "agmark.telemetry:normalized": normalize_capture(capture),
                                           "arcgrav.runner:execution": {"request_framing": {"availability": "observed", "sha256": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}},
                                           "fixture:score": {"accuracy": 1}}}
                before = deepcopy(document)
                result = aggregate_treatment_measurements([(document, "evidence-b")], generation_id="g", planned_observations={"t": 1})["t"]
                self.assertEqual("unavailable", result["telemetry"]["availability"])
                self.assertEqual([], result["telemetry"]["groups"])
                self.assertEqual({}, result["telemetry"]["measurements"])
                self.assertEqual(fixture_identity("observation-b"), result["telemetry"]["exclusions"][0]["observation_id"])
                self.assertIn(mismatch, result["telemetry"]["exclusions"][0]["reason"])
                self.assertEqual(100, result["roles"]["input_tokens"]["value"])
                self.assertEqual(before, document)

    def test_capture_bindings_validate_available_authorities_without_inventing_missing_ones(self):
        envelope, _ = extract()
        for boundary_present, frame_present, captured_present in ((True, True, True), (False, False, True), (True, True, False)):
            with self.subTest(boundary=boundary_present, frame=frame_present, captured=captured_present):
                capture = manifest([("rollout", snapshot())], identity="observation",
                    runtime_overrides={"accepted_boundary_fingerprint": "sha256:" + "a" * 64, "framed_request_sha256": "sha256:" + "b" * 64} if captured_present else {})
                document = {"observation_id": fixture_identity("observation"), "accepted_generation_id": "g", "treatment_id": "t", "attempts": [{"attempt": 1}],
                            "extensions": {ATTEMPT_MEASUREMENTS: envelope, "agmark.telemetry:capture": capture,
                                           "agmark.telemetry:normalized": normalize_capture(capture)}}
                if boundary_present:
                    document["execution_boundary_fingerprint"] = "sha256:" + "a" * 64
                if frame_present:
                    document["extensions"]["arcgrav.runner:execution"] = {"request_framing": {"availability": "observed", "sha256": "sha256:" + "b" * 64}}
                result = aggregate_treatment_measurements([(document, "evidence")], generation_id="g", planned_observations={"t": 1})["t"]
                self.assertEqual("available", result["telemetry"]["availability"])
                self.assertEqual([fixture_identity("observation")], result["telemetry"]["groups"][0]["contributors"])
                self.assertEqual([], result["telemetry"]["exclusions"])

    def test_capture_one_attempt_scope_cannot_be_assigned_to_multiple_attempts(self):
        capture = manifest([("rollout", snapshot())], identity="observation")
        document = {"observation_id": fixture_identity("observation"), "accepted_generation_id": "g", "treatment_id": "t", "attempts": [{"attempt": 1}, {"attempt": 2}],
                    "extensions": {"agmark.telemetry:capture": capture, "agmark.telemetry:normalized": normalize_capture(capture)}}
        result = aggregate_treatment_measurements([(document, "evidence")], generation_id="g", planned_observations={"t": 1})["t"]
        self.assertEqual("unavailable", result["telemetry"]["availability"])
        self.assertEqual([], result["telemetry"]["groups"])
        self.assertIn("per-attempt", result["telemetry"]["exclusions"][0]["reason"])

    def test_actual_treatment_aggregation_reconstructs_capture_and_isolates_failure(self):
        envelope, _ = extract()
        capture = manifest([("rollout", snapshot())], identity="observation")
        extensions = {ATTEMPT_MEASUREMENTS: envelope, "agmark.telemetry:capture": capture,
                      "agmark.telemetry:normalized": normalize_capture(capture)}
        document = {"observation_id": fixture_identity("observation"), "accepted_generation_id": "g", "treatment_id": "t", "attempts": [{"attempt": 1}], "extensions": extensions}
        first = aggregate_treatment_measurements([(document, "evidence")], generation_id="g", planned_observations={"t": 1})["t"]
        self.assertEqual(100, first["telemetry"]["measurements"]["input_tokens"]["value"])
        extensions["agmark.telemetry:normalized"]["measurements"]["input_tokens"]["value"] = 7
        failed = aggregate_treatment_measurements([(document, "evidence")], generation_id="g", planned_observations={"t": 1})["t"]
        self.assertEqual(100, failed["roles"]["input_tokens"]["value"])
        self.assertEqual("unavailable", failed["telemetry"]["availability"])
        self.assertIn("reconstruct", failed["telemetry"]["exclusions"][0]["reason"])
