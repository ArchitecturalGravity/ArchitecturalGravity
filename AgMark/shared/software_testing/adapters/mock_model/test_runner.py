"""Dedicated mock adapter tests; no provider CLI protocol or shared config fiction."""
import copy
import json
import unittest
from unittest.mock import patch
from AgMark.shared.adapters.Mock_Model import MockRunner, load_registration
from AgMark.shared.adapters.Mock_Model.catalog import probe_model_discovery, probe_planning_identity, MODELS
from AgMark.shared.software_testing.adapters.test_registered_runner_contract import request, mock_boundary

class MockRunnerTests(unittest.TestCase):
    def test_catalog_and_planning_need_no_external_process_or_credentials(self):
        with patch("subprocess.Popen", side_effect=AssertionError("catalog must be local")):
            result = probe_model_discovery(load_registration())
            self.assertEqual("ready", result["status"])
            self.assertEqual(len(result["selectable_model_ids"]), len(set(result["selectable_model_ids"])))
            self.assertEqual({m.model_id for m in MODELS}, set(result["selectable_model_ids"]))
            self.assertFalse(any("reasoning" in key for item in result["choices"] for key in item))
            planned = probe_planning_identity(load_registration(), control_values={"model_id": "mock-base"})
            self.assertEqual("ready", planned["status"])
            self.assertEqual("local_process", planned["provider_runtime"]["access_method"])
            self.assertFalse(planned["provider_submitted"])

    def test_registered_mock_entry_point(self):
        self.assertEqual("AgMark.shared.adapters.Mock_Model:MockRunner", load_registration()["extensions"]["arcgrav.adapters:entry_point"])

    def test_terminal_scenarios_use_own_worker_and_common_status_vocabulary(self):
        for scenario, expected, timeout in (("completed", "completed", 2000),
                ("malformed_output", "completed", 2000), ("empty_response", "failed", 2000),
                ("process_failure", "failed", 2000), ("timeout", "timed_out", 100)):
            with self.subTest(scenario=scenario):
                runner = MockRunner(); self.addCleanup(runner.close)
                result = runner.execute(request(mock_boundary("mock-base::scenario:" + scenario, timeout=timeout)))
                self.assertEqual(expected, result["terminal_status"], result)
                self.assertFalse(result["extensions"]["arcgrav.runner:execution"]["submission"]["external_provider"])

    def test_cancellation_is_not_another_adapter_fallback(self):
        runner = MockRunner(); self.addCleanup(runner.close)
        with patch("subprocess.Popen", side_effect=AssertionError("cancelled before submission")):
            observed = runner.execute(request(mock_boundary()), cancellation_requested=lambda: True)
        self.assertEqual("cancelled", observed["terminal_status"])

    def test_unknown_model_and_foreign_controls_fail_without_worker(self):
        for field, value in (("model_id", "unknown-model"), ("reasoning_effort", "high"), ("codex_binary", "/no/provider")):
            boundary = mock_boundary()
            if field == "model_id":
                next(item for item in boundary["controls"] if item["name"] == field)["value"] = value
            else: boundary["controls"].append({"name": field, "value": value})
            runner = MockRunner(); self.addCleanup(runner.close)
            with patch("subprocess.Popen", side_effect=AssertionError("unsupported must not launch")):
                result = runner.execute(request(boundary))
            self.assertEqual("unsupported", result["terminal_status"])
