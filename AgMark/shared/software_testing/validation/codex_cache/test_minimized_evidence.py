"""Privacy regressions for independent replay source evidence."""
import copy
import json
import os
import unittest

from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef
from AgMark.shared.validation.codex_cache.collector import canonical_capture_spans, LoopbackTraceCollector
from AgMark.shared.validation.codex_cache.source_evidence import validate_source
from AgMark.shared.software_testing.validation.codex_cache import test_startup_integration as startup_fixture


class MinimizedReplayEvidenceTests(unittest.TestCase):
    def test_graph_aliases_and_relative_times_preserve_links_without_native_identity(self):
        spans = [
            {"trace_id": "a" * 32, "span_id": "b" * 16, "parent_span_id": None,
             "name": "try_run_sampling_request", "start_time_ns": "1700000000000000000",
             "end_time_ns": "1700000000000000120", "attributes": {}, "events": []},
            {"trace_id": "a" * 32, "span_id": "c" * 16, "parent_span_id": "b" * 16,
             "name": "responses.stream_request", "start_time_ns": "1700000000000000010",
             "end_time_ns": "1700000000000000100", "attributes": {"user_id": "private-user"},
             "events": [{"time_ns": "1700000000000000050", "attributes": {
                 "event.name": "codex.api_request", "duration_ms": 90, "account_id": 123}}]},
        ]
        minimized = canonical_capture_spans(spans)
        self.assertEqual(minimized, canonical_capture_spans(minimized))
        self.assertEqual(minimized[0]["span_id"], minimized[1]["parent_span_id"])
        self.assertEqual("0", minimized[0]["start_time_ns"])
        self.assertEqual("10", minimized[1]["start_time_ns"])
        self.assertEqual("50", minimized[1]["events"][0]["time_ns"])
        encoded = json.dumps(minimized)
        for forbidden in ("a" * 32, "b" * 16, "c" * 16, "1700000000000000000", "private-user", "account_id"):
            self.assertNotIn(forbidden, encoded)
        # Duplicate and contradictory identities remain visible to validation.
        repeated = canonical_capture_spans(spans + [copy.deepcopy(spans[1])])
        self.assertEqual(repeated[1], repeated[2])

    def test_live_loopback_batches_preserve_graph_without_persisting_native_ids(self):
        from urllib.request import Request, urlopen
        with LoopbackTraceCollector() as collector:
            for span_id, parent in (("b" * 16, None), ("c" * 16, "b" * 16)):
                payload = {"resourceSpans": [{"resource": {"account": "private-account"},
                    "scopeSpans": [{"spans": [{"traceId": "a" * 32, "spanId": span_id,
                        "parentSpanId": parent, "name": "try_run_sampling_request" if parent is None else "responses.stream_request",
                        "startTimeUnixNano": "1700000000000000000", "endTimeUnixNano": "1700000000000000050"}]}]}]}
                request = Request(collector.endpoint, data=json.dumps(payload).encode(), method="POST",
                    headers={"Content-Type": "application/json", "Authorization": "Bearer private-secret"})
                with urlopen(request, timeout=3) as response:
                    self.assertEqual(200, response.status)
            evidence = collector.spans
            self.assertEqual(2, len(evidence))
            self.assertEqual(evidence[0]["span_id"], evidence[1]["parent_span_id"])
            self.assertEqual(evidence, canonical_capture_spans(evidence))
            self.assertEqual(0, collector.rejected_payloads)
            encoded = json.dumps(evidence)
            for token in ("private-account", "private-secret", "a" * 32, "b" * 16, "c" * 16, "1700000000000000000"):
                self.assertNotIn(token, encoded)

    @unittest.skipUnless(os.name == "posix", "Uses controlled POSIX launcher")
    def test_startup_exports_no_ambient_fingerprints_and_attests_transient_comparison(self):
        owner = startup_fixture.StartupIntegrationTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        record = owner.capture()
        private = record.revalidate()
        public = record.public_document()
        raw = json.dumps(public).encode()
        self.assertEqual(public, validate_source("startup", raw))
        self.assertEqual("transient_equality_only", public["ambient_state_validation"])
        for name in ("home", "work_parent", "profile", "ancestors", "args", "profile_sha256",
                     "instructions_sha256", "environment_sha256", "launch_controls_sha256"):
            self.assertNotIn(name, public)
        for value in (str(owner.root), "before-scored", "credential-canary", private["profile_sha256"],
                      private["instructions_sha256"], private["environment_sha256"]):
            self.assertNotIn(value, raw.decode())
        boundary = ExecutionBoundary.build(boundary_id="test", framework=IdentityRef("framework", "1.0.0"),
            runner=IdentityRef("runner", "1.0.0"), provider_runtime={"runtime_id": "codex", "access_method": "cli"},
            controls={"model": "gpt-5-codex"})
        arguments = dict(prompt_sha256="sha256:" + "a" * 64, input_sha256="sha256:" + "b" * 64,
                         runner_registration_sha256="sha256:" + "c" * 64)
        expected = record.configuration(boundary, **arguments)
        actual = record.configuration(boundary, ambient_equivalent=False, **arguments)
        self.assertIs(True, expected["ambient_configuration_equal"].value)
        self.assertIs(False, actual["ambient_configuration_equal"].value)
        for values in (expected, actual):
            encoded = json.dumps({k: v.value for k, v in values.items()})
            self.assertNotIn(private["environment_sha256"], encoded)
            self.assertNotIn(private["profile_sha256"], encoded)
        with self.assertRaises(ValueError):
            validate_source("startup", json.dumps({**public, "profile_sha256": private["profile_sha256"]}).encode())
