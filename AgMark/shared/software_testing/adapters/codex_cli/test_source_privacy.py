"""Source minimization preserves reconstruction without retaining private payloads."""
import base64
import copy
import json
import unittest
from AgMark.shared.adapters.Codex_CLI.session import extract_session_measurements
from AgMark.shared.adapters.Codex_CLI.session_record import parse_session_record
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import rollout, stdout, tool_call

class SourcePrivacyTests(unittest.TestCase):
    def test_measurements_reconstruct_without_raw_payload_or_identifiers(self):
        private = "PRIVATE-PERSON-SECRET"
        rows = [json.loads(line) for line in rollout(thread=private, prompts=(private,), tools=tool_call("call_"+private, duration=15)).splitlines()]
        rows[0]["payload"].update(cwd="/home/"+private, user=private, git={"remote": private})
        rows[0]["private"] = private
        for row in rows:
            row["payload"]["unrelated"] = private
            if row["payload"].get("type") == "function_call": row["payload"]["arguments"] = private
        raw = b"\n".join(json.dumps(r).encode() for r in rows)
        record = {"availability": "retained", "thread_id": private, "content_base64": base64.b64encode(raw).decode(), "root": "/home/"+private, "path": private}
        measured, retained = extract_session_measurements(record, stdout(private), runtime_version="0.159.0", process_complete=True)
        serialized = json.dumps([measured, retained])
        self.assertNotIn(private, serialized)
        self.assertNotIn("content_base64", serialized)
        self.assertNotIn("stdout_sha256", serialized)
        self.assertNotIn("original_sha256", serialized)
        self.assertNotIn("2026-10-03", serialized)
        self.assertEqual(100, measured["roles"]["input_tokens"]["value"])
        self.assertEqual("completed", measured["tool_events"][0]["status"])
        self.assertEqual((measured, retained), extract_session_measurements(retained, b"", runtime_version="0.159.0", process_complete=True))

    def test_tampering_and_extra_fields_fail_closed(self):
        raw = rollout()
        _, retained = extract_session_measurements({"availability": "retained", "thread_id": "trial", "content_base64": base64.b64encode(raw).decode()}, stdout(), runtime_version="0.159.0", process_complete=True)
        for change in ("extra", "source", "completeness", "thread", "version"):
            with self.subTest(change=change):
                bad = copy.deepcopy(retained)
                if change == "extra": bad["home"] = "/home/private"
                elif change == "source": bad["source_records"][0]["payload"]["user"] = "private"
                elif change == "completeness": bad["trace_complete"] = False
                elif change == "thread": bad["thread_id"] = "other"
                else: bad["extraction_version"] = "3.3.0"
                with self.assertRaises(ValueError): parse_session_record(bad, b"", runtime_version="0.159.0", process_complete=True)

    def test_resealed_projection_cannot_smuggle_unrelated_values(self):
        from AgMark.shared.adapters.Codex_CLI.source_projection import source_digest
        raw = rollout(tools=tool_call("call_tool", duration=10))
        _, retained = extract_session_measurements({"availability": "retained", "thread_id": "trial", "content_base64": base64.b64encode(raw).decode()}, stdout(), runtime_version="0.159.0", process_complete=True)
        for mutation in ("user", "absolute_model", "wall_clock", "raw_argument", "raw_identity"):
            with self.subTest(mutation=mutation):
                bad = copy.deepcopy(retained)
                rows = bad["source_records"]
                if mutation == "user": rows[0]["payload"]["source"] = "private-user"
                elif mutation == "absolute_model": rows[1]["payload"]["model"] = "/home/private/model"
                elif mutation == "wall_clock": rows[0]["timestamp"] = "2026-11-04T12:00:00Z"
                elif mutation == "raw_argument":
                    next(r for r in rows if r["payload"].get("type") == "function_call")["payload"]["arguments"] = "private command"
                else: rows[0]["payload"]["session_id"] = "private-session"
                bad["sha256"] = source_digest(rows, bad["stdout_facts"], bad["line_numbers"])
                with self.assertRaises(ValueError): parse_session_record(bad, b"", runtime_version="0.159.0", process_complete=True)

    def test_precomposition_failures_use_the_same_minimal_retention_surface(self):
        from AgMark.shared.adapters.Codex_CLI import CodexCliRunner
        from AgMark.shared.adapters.execution.emission import _validate_retained_content, validate_retained_parity_observation
        from AgMark.shared.software_testing.adapters.codex_cli.test_runner import _boundary, _request, FakeCodexTransport
        for failure in ("unsupported_control", "missing_executable", "invalid_composition"):
            with self.subTest(failure=failure):
                boundary = _boundary()
                if failure == "unsupported_control":
                    boundary["controls"].append({"name": "unregistered", "value": "PRIVATE-MARKER"})
                elif failure == "invalid_composition":
                    boundary["provider_runtime"]["runtime_id"] = "PRIVATE-MARKER"
                adapter = CodexCliRunner(transport=FakeCodexTransport(),
                    executable_resolver=lambda _: None if failure == "missing_executable" else "/private/runtime/codex")
                observation = adapter.execute(_request(boundary))
                self.assertEqual("unsupported", observation["terminal_status"])
                _validate_retained_content(observation)
                validate_retained_parity_observation(observation)
                canonical = observation["extensions"]["arcgrav.runner:execution"]
                self.assertFalse(canonical["submission"]["occurred"])
                self.assertFalse(canonical["submission"]["external_provider"])
                self.assertEqual("unavailable", canonical["runtime"]["availability"])
                self.assertEqual("unavailable", canonical["launch_environment"]["availability"])
                self.assertEqual("not_produced", canonical["process"]["stdout"]["availability"])
                self.assertFalse({"stdout_bytes", "stderr_bytes"} & {m["name"] for m in observation["telemetry"]})
                serialized = json.dumps(observation)
                for private in ("PRIVATE-MARKER", "/private/runtime", "process_stdout_base64", "process_stderr_base64", "environment_keys"):
                    self.assertNotIn(private, serialized)

    def test_lifecycle_retains_missing_executable_as_unsupported(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from AgMark.shared.adapters.Codex_CLI import CodexCliRunner
        from AgMark.shared.adapters.execution import validate_retained_parity_observation
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture
        execute = CodexCliRunner.execute
        def missing_only_during_execution(adapter, *args, **kwargs):
            with patch.object(adapter, "_executable_resolver", return_value=None):
                return execute(adapter, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory, patch.object(CodexCliRunner, "execute", missing_only_during_execution):
            terminal, boundary, store, _ = accepted_fixture(Path(directory), replay_supported=False)
            terminal.revalidate(store)
            self.assertTrue(terminal.treatment_observations)
            for raw in terminal.treatment_observations:
                observation = json.loads(raw)
                self.assertEqual("unsupported", observation["terminal_status"])
                validate_retained_parity_observation(observation)
                self.assertFalse(observation["extensions"]["arcgrav.runner:execution"]["submission"]["occurred"])
