"""Focused scored-session responsibility conformance."""
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import *
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import _boundary, _request
from AgMark.shared.adapters.Codex_CLI.runner import _SubprocessTransport, _SESSION_CANCELLATION


class SessionRecordTests(unittest.TestCase):
    def test_missing_and_wrong_session_cannot_fall_back_to_stdout_or_prove_zero(self):
        for record in ({"availability": "unavailable", "reason": "missing"}, {"availability": "retained", "thread_id": "trial", "content_base64": base64.b64encode(rollout("other")).decode()}):
            value, capture = extract_session_measurements(record, stdout(), runtime_version="0.159.0", process_complete=True)
            self.assertEqual("unavailable", capture["availability"])
            self.assertIsNone(value["roles"]["input_tokens"]["value"])
            self.assertIsNone(aggregate([value])["roles"]["tool_calls"]["value"])
        self.assertIsNone(returned_thread_id(stdout()+stdout()))

    def test_exact_id_ignores_newer_unrelated_file_and_checks_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "rollout-trial.jsonl"
            target.write_bytes(rollout())
            unrelated = root / "rollout-other.jsonl"
            unrelated.write_bytes(rollout("other"))
            os.utime(unrelated, (2_000_000_000, 2_000_000_000))
            record = read_session("trial", root=root)
            self.assertEqual("retained", record["availability"])
            self.assertEqual(str(target), record["path"])
            target.write_bytes(rollout("wrong"))
            self.assertEqual("session_thread_id_mismatch", read_session("trial", root=root)["reason"])

    def test_duplicate_missing_and_invalid_ids_do_not_select_any_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a-trial.jsonl", "b-trial.jsonl"):
                (root / name).write_bytes(rollout())
            self.assertEqual("ambiguous_session_records", read_session("trial", root=root)["reason"])
            self.assertEqual("session_discovery_timeout", read_session("missing", root=root, timeout_seconds=0)["reason"])
            for identity in ("../trial", "*", "", None):
                self.assertEqual("invalid_thread_id", read_session(identity, root=root)["reason"])

    def test_delayed_writer_and_concurrent_trials_are_matched_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def write():
                time.sleep(.06)
                (root / "rollout-a.jsonl").write_bytes(rollout("a"))
                (root / "rollout-b.jsonl").write_bytes(rollout("b"))
            writer = threading.Thread(target=write)
            writer.start()
            records = {}
            def capture(identity):
                records[identity] = read_session(identity, root=root)
            workers = [threading.Thread(target=capture, args=(identity,)) for identity in ("a", "b")]
            for worker in workers: worker.start()
            for worker in workers: worker.join()
            writer.join()
            for identity, record in records.items():
                self.assertEqual(identity, json.loads(base64.b64decode(record["content_base64"]).splitlines()[0])["payload"]["id"])

    def test_wsl_reader_runs_inside_selected_distribution_with_runtime_home(self):
        transport = _SubprocessTransport()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sessions"
            root.mkdir()
            (root / "rollout-trial.jsonl").write_bytes(rollout())
            def run(argv, **kwargs):
                self.assertEqual(("wsl.exe", "--distribution", "Selected", "--exec", "sh", "-lc"), argv[:6])
                # Execute the actual standalone reader source in a separate process.
                result = subprocess.run(("python3", "-c", argv[-2], argv[-1]), env={**os.environ, "CODEX_HOME": directory}, capture_output=True, check=True)
                return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
            with patch.object(transport, "run", side_effect=run):
                record = transport.read_session("trial", launch_environment={"mode": "wsl", "launcher": "wsl.exe", "distribution": "Selected"}, environment={})
            self.assertEqual("retained", record["availability"])
            self.assertEqual(str(root), record["root"])

    def test_stable_prefix_does_not_hide_delayed_final_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout-trial.jsonl"
            raw = rollout()
            prefix = b"\n".join(raw.splitlines()[:-2]) + b"\n"
            path.write_bytes(prefix)
            def finish():
                time.sleep(.2)
                with path.open("ab") as handle:
                    handle.write(raw[len(prefix):])
            writer = threading.Thread(target=finish)
            writer.start()
            captured = read_session("trial", root=path.parent)
            writer.join()
            self.assertEqual(raw, base64.b64decode(captured["content_base64"]))

    def test_large_tree_limit_never_selects_an_unverified_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first-trial.jsonl").write_bytes(rollout())
            for index in range(200):
                (root / ("unrelated-" + str(index) + ".jsonl")).touch()
            record = read_session("trial", root=root, maximum_entries=20)
            self.assertEqual("unavailable", record["availability"])
            self.assertEqual("session_discovery_entry_limit", record["reason"])
            self.assertFalse(record["capture_complete"])
            self.assertNotIn("content_base64", record)
            self.assertEqual(21, record["discovery_entries_examined"])

    def test_discovery_cancellation_and_file_size_limits_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(200):
                (root / ("unrelated-" + str(index) + ".jsonl")).touch()
            checks = []
            def cancelled():
                checks.append(True)
                return len(checks) >= 20
            record = read_session("trial", root=root, cancellation_requested=cancelled)
            self.assertEqual("session_capture_cancelled", record["reason"])
            self.assertLess(record["discovery_entries_examined"], 20)
            (root / "trial.jsonl").write_bytes(rollout())
            record = read_session("trial", root=root, maximum_bytes=16)
            self.assertEqual("session_record_byte_limit", record["reason"])
            self.assertNotIn("content_base64", record)

    def test_native_helper_can_cancel_a_stalled_filesystem_operation(self):
        import sys
        from AgMark.shared.adapters.Codex_CLI import session_capture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "helper-started"
            helper = root / "blocked-reader.py"
            helper.write_text("import pathlib, time\npathlib.Path(" + repr(str(marker))
                              + ").touch()\ntime.sleep(30)\n")
            token = _SESSION_CANCELLATION.set(marker.exists)
            try:
                started = time.monotonic()
                with patch.object(session_capture, "__file__", str(helper)):
                    record = _SubprocessTransport().read_session("trial",
                        launch_environment={"mode": "native", "executable": sys.executable},
                        environment=dict(os.environ))
                self.assertLess(time.monotonic() - started, 2)
            finally:
                _SESSION_CANCELLATION.reset(token)
            self.assertTrue(marker.exists())
            self.assertEqual("session_capture_cancelled", record["reason"])
            self.assertFalse(record["capture_complete"])

    def test_native_helper_returns_only_exact_thread_and_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sessions"
            root.mkdir()
            (root / "rollout-trial.jsonl").write_bytes(rollout())
            record = _SubprocessTransport().read_session("trial", launch_environment={"mode": "native"},
                environment={**os.environ, "CODEX_HOME": directory})
            self.assertEqual("retained", record["availability"])
            self.assertEqual(rollout(), base64.b64decode(record["content_base64"]))
            self.assertTrue(record["capture_complete"])
            self.assertGreater(record["discovery_entries_examined"], 0)

    def test_native_helper_deadline_bounds_a_blocked_reader(self):
        from AgMark.shared.adapters.Codex_CLI import session_capture
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "blocked-reader.py"
            helper.write_text("import time\ntime.sleep(30)\n")
            started = time.monotonic()
            with patch.object(session_capture, "__file__", str(helper)):
                record = _SubprocessTransport().read_session("trial", launch_environment={"mode": "native"},
                    environment=dict(os.environ))
            self.assertLess(time.monotonic() - started, 5)
            self.assertEqual("session_capture_timeout", record["reason"])
            self.assertFalse(record["capture_complete"])
