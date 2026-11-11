"""Completed-response usage support preserves historical extraction authority."""
import base64
import json
import unittest
from AgMark.shared.adapters.Codex_CLI.session import extract_session_measurements
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import rollout, stdout, extract
from AgMark.shared.software_testing.telemetry.test_normalization import response, usage
from AgMark.shared.evaluation.telemetry.session_metrics import SESSION_METRICS


def with_records(records, *, token_count=True):
    rows = [json.loads(line) for line in rollout().splitlines()]
    if not token_count:
        rows = [row for row in rows if row.get("payload", {}).get("type") != "token_count"]
    rows[-1:-1] = records
    return b"".join((json.dumps(row) + "\n").encode() for row in rows)


class CompletedResponseUsageTests(unittest.TestCase):
    def test_audited_new_capture_marks_usage_capability_without_reinterpreting_old_sources(self):
        from AgMark.shared.telemetry.runtime_reference import capture_schema_audit
        from unittest.mock import patch
        rows = [json.loads(line) for line in with_records([response()], token_count=False).splitlines()]
        rows[0]["payload"]["cli_version"] = "0.167.0"
        raw = b"".join((json.dumps(row) + "\n").encode() for row in rows)
        source = {"availability": "retained", "thread_id": "trial",
                  "content_base64": base64.b64encode(raw).decode()}
        def capture(version="0.167.0"):
            return extract_session_measurements(source, stdout(), runtime_version=version, process_complete=True)
        with patch('AgMark.shared.telemetry.runtime_reference.capture_schema_audit', return_value={}):
            old_value, old_record = capture()
        value, record = capture()
        self.assertEqual({"token_usage_record_v1": True}, record["capabilities"])
        self.assertEqual("token_usage_record.thread_token_usage", record["usage_authority"])
        self.assertTrue(record["completed_response_usage"])
        self.assertEqual((value, record), extract_session_measurements(record, stdout(), runtime_version="0.167.0", process_complete=True))
        self.assertNotIn("capabilities", old_record)
        self.assertEqual((old_value, old_record), extract_session_measurements(old_record, stdout(), runtime_version="0.167.0", process_complete=True))
        for version in ("0.167.0-alpha.1", "0.167.0+private", "9.9.9"):
            self.assertEqual({}, capture_schema_audit(version))
            self.assertNotIn("capabilities", capture(version)[1])

    def test_fresh_capture_retains_scopes_and_final_cumulative_fallback(self):
        value, record = extract(with_records([response(), response("response-2", usage(200, 80))], token_count=False))
        self.assertEqual("4.0.0", record["extraction_version"])
        self.assertEqual(200, value["roles"]["input_tokens"]["value"])
        self.assertEqual(2, len(record["completed_response_usage"]))
        self.assertEqual("token_usage_record.thread_token_usage", record["usage_authority"])
        self.assertIsNone(value["extensions"][SESSION_METRICS]["roles"]["inference_call_count"]["value"])
        self.assertEqual((value, record), extract_session_measurements(record, stdout(), runtime_version="0.159.0", process_complete=True))

    def test_token_count_authority_retained_disagreements_not_added(self):
        value, record = extract(with_records([response(counters=usage(200, 80))]))
        self.assertEqual(100, value["roles"]["input_tokens"]["value"])
        self.assertTrue(record["usage_contradictions"])
        self.assertEqual("token_count.info.total_token_usage", record["usage_authority"])

    def test_old_extractors_are_rejected_without_fallback(self):
        raw = with_records([response()], token_count=False)
        for version in ("3.0.0", "3.1.0", "3.2.0", "3.3.0"):
            retained = {"availability": "retained", "thread_id": "trial", "extraction_version": version,
                        "content_base64": base64.b64encode(raw).decode()}
            with self.assertRaisesRegex(ValueError, "unsupported Codex session extraction version"):
                extract_session_measurements(retained, stdout(), runtime_version="0.159.0", process_complete=True)

    def test_unknown_version_and_wrong_thread_cannot_supply_usage(self):
        raw = with_records([response()], token_count=False)
        record = {"availability": "retained", "thread_id": "trial", "content_base64": base64.b64encode(raw).decode()}
        value, _ = extract_session_measurements(record, stdout(), runtime_version="0.160.0", process_complete=True)
        self.assertIsNone(value["roles"]["input_tokens"]["value"])
        other = response()
        other["payload"]["thread_id"] = "different"
        value, retained = extract(with_records([other], token_count=False))
        self.assertIsNone(value["roles"]["input_tokens"]["value"])
        self.assertTrue(retained["usage_contradictions"])
