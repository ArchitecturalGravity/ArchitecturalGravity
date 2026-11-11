"""The controlled provider distinguishes Responses traffic and generations."""
import json
import copy
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from AgMark.shared.validation.codex_cache import collector, host_worker


class ProbeSurfaceTests(unittest.TestCase):
    def test_auxiliary_exclusion_cannot_hide_an_incomplete_primary_diagnostic_graph(self):
        from AgMark.shared.software_testing.adapters.codex_cli.capture_audit import diagnostic_scope_accounted
        manifest = {"sources": {"diagnostics": {"state": "partial",
            "reason": "diagnostic_graph_root_unmatched", "parse_errors": 0, "dropped": 0,
            "partial": 0, "rejected": 1, "reduced_graph": {"state": "retained"}}},
            "records": [{"source": "diagnostics", "payload": {"type": "reduced_graph",
                "schema_version": 2, "recording_complete": True, "graph_counts": {"threads": 1}}},
                {"source": "diagnostics", "payload": {"type": "reduced_graph_node"}}]}
        self.assertTrue(diagnostic_scope_accounted(manifest))
        for failure in ("recording", "nodes", "partial", "parse_errors", "dropped"):
            broken = copy.deepcopy(manifest)
            if failure == "recording":
                broken["records"][0]["payload"]["recording_complete"] = False
            elif failure == "nodes":
                broken["records"].pop()
            else:
                broken["sources"]["diagnostics"][failure] = 1
            with self.subTest(failure=failure):
                self.assertFalse(diagnostic_scope_accounted(broken))

    def test_ancillary_requests_do_not_consume_a_generation_and_warmup_does_not_consume_the_tool(self):
        identity = {"version": "codex-cli 0.167.0", "binary_sha256": "sha256:" + "a" * 64}
        def run(args, **_):
            setting = next(x for x in args if x.startswith("model_providers.agmark_probe.base_url="))
            base = json.loads(setting.split("=", 1)[1])
            def post(path, body):
                with urlopen(Request(base + path, data=json.dumps(body).encode(),
                        headers={"Content-Type": "application/json"}), timeout=2) as response:
                    return response.read().decode()
            with self.assertRaises(HTTPError) as error:
                post("/analytics/codex/turn-costs", {"turn_ids": ["controlled"]})
            self.assertEqual(404, error.exception.code)
            self.assertNotIn('"function_call"', post("/responses", {"generate": False}))
            self.assertIn('"function_call"', post("/responses", {}))
            self.assertIn('"probe-complete"', post("/responses", {}))
            return 0, None
        with patch.object(host_worker, "LoopbackTraceCollector", collector.LoopbackTraceCollector, create=True), \
             patch.object(host_worker, "observation_overrides", collector.observation_overrides, create=True), \
             patch.object(host_worker, "_runtime_identity", return_value=identity), \
             patch.object(host_worker, "_run_process", run):
            result = host_worker._probe_transport({"snapshot": {"executable": "controlled", **identity}}, "http")
        self.assertEqual([{"ordinal": 1}, {"ordinal": 2}, {"ordinal": 3}], result["provider_requests"])
        self.assertEqual(0, result["returncode"])
