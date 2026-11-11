"""Public facade and retained reconstruction integration conformance."""
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import *
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import _boundary, _request


class SessionIntegrationTests(unittest.TestCase):
    def test_legacy_extraction_is_rejected_without_fallback(self):
        for version in ("3.0.0", "3.1.0", "3.2.0", "3.3.0"):
            with self.subTest(version=version):
                record = {"availability": "retained", "thread_id": "trial", "extraction_version": version,
                          "content_base64": base64.b64encode(rollout()).decode()}
                with self.assertRaisesRegex(ValueError, "unsupported Codex session extraction version"):
                    extract_session_measurements(record, stdout(), runtime_version="0.159.0", process_complete=True)

    def test_local_aliases_are_scoped_to_observations(self):
        value, record = extract()
        self.assertEqual("call_1", record["thread_id"])
        # Identical invocation-local aliases are not globally unique identities.
        aggregate([value, value])

    def test_retained_capture_reconstructs_and_rejects_counter_hash_or_thread_tampering(self):
        transport = FakeCodexTransport()
        observation = CodexCliRunner(transport=transport, executable_resolver=lambda _: "/fixture/codex").execute(_request(_boundary()))
        validate_retained_parity_observation(observation)
        for mutate in (
            lambda d: d["extensions"][SESSION_RECORD].update(sha256="sha256:"+"0"*64),
            lambda d: d["extensions"][SESSION_RECORD].update(thread_id="wrong"),
            lambda d: d["extensions"][SESSION_RECORD].update(observation_id="other"),
            lambda d: d["extensions"][SESSION_RECORD]["cache_policy"].update(cache_key_observed=True),
            lambda d: d["extensions"][SESSION_RECORD]["cache_policy"].update(cache_key_value="other"),
            lambda d: d["extensions"][SESSION_RECORD]["cache_telemetry"].update(first_token_count_snapshot=99),
            lambda d: d["extensions"][SESSION_RECORD]["cache_telemetry"]["snapshots"][0]["info"]["total_token_usage"].update(cached_input_tokens=99),
            lambda d: d["extensions"][ATTEMPT_MEASUREMENTS]["roles"]["total_tokens"].update(value=100, availability="available", kind="runtime_counter", evidence_references=["fake"]),
        ):
            corrupt = copy.deepcopy(observation)
            mutate(corrupt)
            with self.assertRaises(ValueError):
                validate_retained_parity_observation(corrupt)

    @unittest.skipUnless(os.name == "posix", "Repository mock executable uses POSIX launcher")
    def test_real_runner_persists_unique_trials_and_retains_source_after_original_removal(self):
        registration = load_registration()
        binary = str(Path(__file__).resolve().parent / "fixtures/codex_protocol/arcgrav-mock-model-cli")
        with tempfile.TemporaryDirectory() as directory:
            runner = CodexCliRunner(executable_resolver=lambda _: binary)
            from AgMark.shared.mock_model.protocol import DEFAULT_RUNTIME_VERSION
            from AgMark.shared.software_testing.adapters.codex_cli.fixtures.codex_protocol.protocol.cli import BASE_MODEL_ID
            boundary = _boundary(model_id=BASE_MODEL_ID, runtime_version=DEFAULT_RUNTIME_VERSION)
            environment = {**runner._environment(), "CODEX_HOME": directory}
            with patch.object(runner, "_environment", return_value=environment):
                first = runner.execute(_request(boundary, suffix="first"))
                second = runner.execute(_request(boundary, suffix="second"))
            self.assertEqual("completed", first["terminal_status"])
            self.assertEqual("call_1", first["extensions"][SESSION_RECORD]["thread_id"])
            self.assertEqual("call_1", second["extensions"][SESSION_RECORD]["thread_id"])
            self.assertNotEqual(first["observation_id"], second["observation_id"])
            # The synthetic runtime still starts unique threads. Inspect only this
            # test-owned temporary session directory, never the user's home.
            source_ids = {json.loads(path.read_text().splitlines()[0])["payload"]["id"] for path in Path(directory).rglob("*.jsonl")}
            self.assertEqual(2, len(source_ids))
            for raw_id in source_ids:
                self.assertNotIn(raw_id, json.dumps(first))
                self.assertNotIn(raw_id, json.dumps(second))
            self.assertEqual(42, first["extensions"][ATTEMPT_MEASUREMENTS]["roles"]["total_tokens"]["value"])
            for path in Path(directory).rglob("*.jsonl"): path.unlink()
            validate_retained_parity_observation(first)
            validate_retained_parity_observation(second)
