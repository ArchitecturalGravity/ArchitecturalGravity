"""Synthetic extraction contract and retained reconstruction regressions."""
import base64
import copy
import hashlib
import json
import unittest

from AgMark.shared.adapters.Codex_CLI.session import extract_session_measurements
from AgMark.shared.adapters.Codex_CLI.session_record import parse_session_record
from AgMark.shared.adapters.Codex_CLI.token_usage import extract_token_usage
from AgMark.shared.adapters.Codex_CLI.tool_telemetry import extract_tool_telemetry
from AgMark.shared.adapters.Codex_CLI.session_timing import extract_session_timing
from AgMark.shared.software_testing.adapters.codex_cli.session_parity_cases import cases

# Literal expected counters below are an independent contract oracle.
# Synthetic inputs establish extraction behavior, not observed provider activity.
from AgMark.shared.evaluation.telemetry.consumption import validate_attempt_measurements
from AgMark.shared.adapters.Codex_CLI.validation import validate_session_observation
from AgMark.shared.adapters.Codex_CLI.session import SESSION_RECORD
from AgMark.shared.software_testing.adapters.codex_cli.synthetic_cache_fixtures import synthetic_audit

TOKEN_ROLES = ("total_tokens", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")
EXPECTED_COUNTERS = (
    (125, 100, 40, 20, 5),
    (0, 0, None, None, None),
    (None, None, None, None, None),
    (None, 3, None, 2, None),  # Subset counters exceeding parents are rejected.
    (None, None, None, None, None),
)


class SessionParityTests(unittest.TestCase):
    def test_synthetic_matrix_preserves_serialization_identity_and_counter_contract(self):
        seen = set()
        for name, record, stdout, version, complete in cases():
            with self.subTest(case=name):
                original = copy.deepcopy(record)
                measured, retained = extract_session_measurements(
                    record, stdout, runtime_version=version, process_complete=complete)
                self.assertEqual(original, record, "extraction must not mutate its input")
                validate_attempt_measurements(measured)
                self.assertEqual((measured, retained), extract_session_measurements(
                    json.loads(json.dumps(retained)), stdout,
                    runtime_version=version, process_complete=complete))
                self.assertEqual("4.0.0", retained["extraction_version"])
                self.assertEqual("call_1", retained["thread_id"])
                self.assertNotIn("content_base64", retained)
                self.assertEqual("measurement-source/1", retained["source_representation"])
                if name.startswith("matrix-") and not name.endswith("mismatch"):
                    self.assertEqual(bool(complete and name.endswith("valid")), retained["trace_complete"])
                    index = int(name.split("-")[1])
                    expected = EXPECTED_COUNTERS[(index // 7) % 5]
                else:
                    expected = (None,) * len(TOKEN_ROLES)
                    self.assertEqual("unavailable", retained["availability"])
                self.assertEqual(expected, tuple(measured["roles"][role]["value"] for role in TOKEN_ROLES))
                seen.add(name)
        self.assertEqual(422, len(seen))

    def test_synthetic_retained_records_reconstruct_and_reject_tampering(self):
        for guardian in (False, True):
            for item in synthetic_audit(guardian=guardian)["results"]:
                with self.subTest(thread=item["session_record"]["thread_id"]):
                    stdout = item["stdout"].encode()
                    measured, retained = extract_session_measurements(item["session_record"], stdout,
                        runtime_version="0.159.0", process_complete=True)
                    self.assertEqual((120, 100, 40, 20, None),
                        tuple(measured["roles"][role]["value"] for role in TOKEN_ROLES))
                    execution = {"runtime": {"runtime_version": "0.159.0"},
                        "process": {"exit_status": 0, "transport_status": None}}
                    extensions = {SESSION_RECORD: retained,
                        "arcgrav.runner:process_stdout_base64": base64.b64encode(stdout).decode()}
                    self.assertEqual(retained["sha256"],
                        validate_session_observation(extensions, execution, measured))
                    for mutation in ("counter", "source_hash", "thread"):
                        bad_extensions, bad_measured = copy.deepcopy(extensions), copy.deepcopy(measured)
                        if mutation == "counter":
                            bad_measured["roles"]["input_tokens"]["value"] += 1
                        elif mutation == "source_hash":
                            bad_extensions[SESSION_RECORD]["sha256"] = "0" * 64
                        else:
                            bad_extensions[SESSION_RECORD]["thread_id"] = "different-root"
                        with self.assertRaises(ValueError):
                            validate_session_observation(bad_extensions, execution, bad_measured)

    def test_normalized_responsibilities_preserve_cumulative_and_partial_facts(self):
        for _, record, stdout, version, complete in cases():
            retained = parse_session_record(record, stdout, runtime_version=version, process_complete=complete)
            usage = extract_token_usage(retained)
            tools = extract_tool_telemetry(retained)
            timing = extract_session_timing(retained)
            self.assertEqual(retained.source_complete, usage.source_complete)
            self.assertIsInstance(tools.events, tuple)
            self.assertIsInstance(timing.prompts, tuple)
            self.assertEqual("unavailable", usage.snapshots["request_correlation"])
            self.assertNotIn("cache_key_policy", usage.tokens)
            self.assertEqual(complete and retained.source_complete, retained.source_complete)
