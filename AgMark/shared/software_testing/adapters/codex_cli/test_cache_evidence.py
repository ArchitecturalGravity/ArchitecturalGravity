"""Synthetic cache-contract regressions; optional genuine backend evidence audit.

Synthetic session inputs do not prove historical runtime/wire behavior. The
opt-in test_cache_wire suite remains the real-binary wire-policy check.
"""
import json
import os
from pathlib import Path
import unittest

from AgMark.shared.adapters._contract import sha256_bytes
from AgMark.shared.adapters.Codex_CLI.session import SESSION_RECORD, extract_session_measurements
from AgMark.shared.adapters.execution import validate_retained_parity_observation
from AgMark.shared.evaluation.telemetry.consumption import ATTEMPT_MEASUREMENTS
from AgMark.shared.evaluation.telemetry.session_metrics import SESSION_METRICS


from AgMark.shared.software_testing.adapters.codex_cli.synthetic_cache_fixtures import synthetic_audit


EVIDENCE = Path(__file__).parent / "evidence" / "cache_accounting_0_159_0"


class CacheEvidenceTests(unittest.TestCase):
    def read_audit(self, filename):
        audit = synthetic_audit(guardian=filename == "guardian-wire-audit.json")
        return audit

    def assert_reconstructed_roots(self, audit):
        """Exercise production extraction and reconstruction, not fixture wire data."""
        results = audit["results"]
        self.assertTrue(results)
        for result in results:
            key = result["session_record"]["thread_id"]
            record = result["session_record"]
            _, reconstructed = extract_session_measurements(record, result["stdout"].encode(),
                runtime_version="0.159.0", process_complete=True)
            self.assertEqual("call_1", reconstructed["thread_id"])
            self.assertNotIn(key, json.dumps(reconstructed))
            self.assertNotIn("content_base64", reconstructed)
            self.assertTrue(reconstructed["source_records"])
            self.assertTrue(reconstructed["trace_complete"])
            self.assertEqual(reconstructed, extract_session_measurements(
                reconstructed, result["stdout"].encode(), runtime_version="0.159.0",
                process_complete=True)[1])
            policy = reconstructed["cache_policy"]
            self.assertEqual("call_1", policy["cache_key_value"])
            self.assertEqual("inferred_codex_0_159_0_root_default", policy["cache_key_provenance"])
            self.assertFalse(policy["cache_key_observed"])
            self.assertFalse(policy["derived_contexts_observed"])
            self.assertEqual("guardian:<parent_thread_id>",
                             policy["derived_context_policy"]["guardian_review"])
            self.assertEqual("Inherited root session_id",
                             policy["derived_context_policy"]["subagent"])
            self.assertEqual("New root session_id",
                             policy["derived_context_policy"]["persistent_root_fork"])

    def test_synthetic_root_contract_and_rollout_provenance(self):
        audit = self.read_audit("wire-audit.json")
        self.assert_reconstructed_roots(audit)

    def test_synthetic_guardian_records_reconstruct(self):
        self.assert_reconstructed_roots(self.read_audit("guardian-wire-audit.json"))

    def test_selected_backend_evidence_hashes_reconstruction_and_summary(self):
        evidence = Path(os.environ.get("AGMARK_BACKEND_EVIDENCE_DIRECTORY", EVIDENCE))
        if not (evidence / "backend-summary.json").is_file():
            self.skipTest("Genuine selected-backend observations are not provisioned locally; not a semantic benchmark prerequisite")
        summaries = json.loads((evidence / "backend-summary.json").read_text())
        self.assertTrue(summaries, "Retained selected-backend observations are required")
        keys = []
        for summary in summaries:
            with self.subTest(trial=summary["trial"]):
                raw = (evidence / summary["evidence_file"]).read_bytes()
                self.assertEqual(summary["evidence_sha256"], sha256_bytes(raw))
                observation = json.loads(raw)
                validate_retained_parity_observation(observation)
                extensions = observation["extensions"]
                record = extensions[SESSION_RECORD]
                key = record["thread_id"]
                keys.append(observation["observation_id"])
                self.assertEqual(summary["thread_id"], key)
                self.assertEqual(key, record["cache_policy"]["cache_key_value"])
                self.assertEqual(summary["cache_key_provenance"], record["cache_policy"]["cache_key_provenance"])
                self.assertFalse(summary["cache_key_observed"])
                self.assertFalse(record["cache_policy"]["cache_key_observed"])
                telemetry = record["cache_telemetry"]
                self.assertEqual("unavailable", summary["request_correlation"])
                self.assertEqual("unavailable", telemetry["request_correlation"])
                self.assertEqual(summary["snapshot_count"], len(telemetry["snapshots"]))
                first = telemetry["snapshots"][telemetry["first_token_count_snapshot"]]
                self.assertEqual(summary["first_snapshot"], first["cache_counters"])
                measurements = extensions[ATTEMPT_MEASUREMENTS]
                self.assertEqual(summary["cumulative"], {
                    role: measurements["roles"][role]["value"] for role in summary["cumulative"]})
                session = measurements["extensions"][SESSION_METRICS]
                self.assertEqual(summary["model"], session["model"])
                self.assertEqual(summary["launch_mode"], extensions["arcgrav.runner:execution"]["launch_environment"]["mode"])
                self.assertEqual(summary["cache_write_input_tokens"], session["roles"]["cache_write_input_tokens"]["value"])
        self.assertEqual(len(keys), len(set(keys)))
