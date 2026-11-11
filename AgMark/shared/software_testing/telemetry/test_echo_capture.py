"""The actual GUI Echo request through local native/selected-host fixtures.

No stock CLI or provider is invoked. WSL is represented by local sh; the real
bridge, process guard and three-signal receivers still execute.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from AgMark.gui.application.runner_testing import _runner_test_request
from AgMark.gui.requests import ResolvedRunnerTestRequest
from AgMark.shared.adapters.Codex_CLI import CodexCliRunner
from AgMark.shared.adapters.Codex_CLI.runner import _SubprocessTransport
from AgMark.shared.adapters.Codex_CLI.session_capture import read_session
from AgMark.shared.runtime.identity import ExecutionBoundary
from AgMark.shared.software_testing.adapters.codex_cli.test_runner import _boundary
from AgMark.shared.software_testing.telemetry.test_runner_capture import MultiSignalTransport, runner
from AgMark.shared.software_testing.telemetry.test_runner_wsl_capture import (
    FAKE_CODEX, LocalSelectedHostTransport,
)
from AgMark.shared.telemetry import CaptureProfile, CaptureSession, validate_manifest
from AgMark.shared.telemetry.profile import DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT, observation_overrides
from AgMark.shared.telemetry.wsl import WslCaptureSession
from AgMark.shared.telemetry.wsl import WslCaptureUnavailable


def echo_request(binary, mode, profile, acknowledgement=None):
    document = _boundary(launch_mode=mode, runtime_version="0.159.0", timeout_ms=10000)
    controls = {record["name"]: record["value"] for record in document["controls"]}
    controls.update(codex_binary="runtime/codex", capture_mode=profile,
                    diagnostic_privacy_acknowledged=(acknowledgement if acknowledgement is not None else
                        DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT if profile == "deep_telemetry" else "not_acknowledged"))
    controls.pop("wsl_distribution", None)
    boundary = ExecutionBoundary.build(boundary_id=document["boundary_id"],
        framework=document["framework"], runner=document["runner"],
        provider_runtime=document["provider_runtime"], controls=controls)
    return _runner_test_request(ResolvedRunnerTestRequest(boundary, {}, None))


class LocalNativeTransport(_SubprocessTransport):
    def __init__(self, fixture):
        self.fixture = fixture

    def read_session(self, thread_id, *, launch_environment, environment):
        return read_session(thread_id, root=self.fixture, timeout_seconds=0.2)


@unittest.skipUnless(os.name == "posix", "local sh and Linux process fixture required")
class EchoCaptureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="agmark-echo-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = Path(self.temporary.name)
        self.binary = self.fixture / "offline codex 'quoted' $literal"
        self.binary.write_text("#!" + sys.executable + "\nFIXTURE = " + repr(str(self.fixture)) + "\n" + FAKE_CODEX)
        self.binary.chmod(0o700)
        self.bridges = []

    def bridge(self, *args, **kwargs):
        def local_worker(command, **options):
            self.assertEqual(command[1:4], ("--distribution", "Selected Fixture Distribution", "--exec"))
            return subprocess.Popen(command[4:], **options)
        bridge = WslCaptureSession(*args, **kwargs, popen_factory=local_worker)
        self.bridges.append(bridge)
        self.addCleanup(bridge.close)
        return bridge

    def assert_echo_executes(self, mode):
        for profile in ("telemetry", "deep_telemetry"):
            with self.subTest(mode=mode, profile=profile):
                request = echo_request(self.binary, mode, profile)
                self.assertEqual(request["observation_id"], "gui-runner-test:echo-test")
                transport = LocalNativeTransport(self.fixture) if mode == "native" else LocalSelectedHostTransport(self.fixture)
                adapter = CodexCliRunner(transport=transport, platform_name="posix" if mode == "native" else "nt",
                                         executable_resolver=lambda value: value,
                    launch_selection={"codex_binary": str(getattr(self, "binary", "/fixture/codex")), "wsl_distribution": "Selected Fixture Distribution"})
                with patch("AgMark.shared.telemetry.wsl.WslCaptureSession", side_effect=self.bridge):
                    observation = adapter.execute(request)
                self.assertEqual(observation["terminal_status"], "completed",
                                 observation.get("extensions", {}).get("openai.codex_cli:error"))
                capture = observation["extensions"]["agmark.telemetry:capture"]
                self.assertTrue(validate_manifest(capture))
                self.assertEqual(capture["invocation_id"], request["observation_id"])
                self.assertEqual(capture["profile"]["id"], profile)
                self.assertEqual(capture["runtime"]["accepted_boundary_fingerprint"], request["execution_boundary_fingerprint"])
                for source in ("otel_logs", "otel_traces", "otel_metrics", "stdout", "rollout"):
                    self.assertGreater(capture["sources"][source]["received_events"], 0)
                launched = json.loads((self.fixture / "launched.json").read_text())
                args = launched["args"]
                config = tomllib.loads("\n".join(args[i + 1] for i, value in enumerate(args[:-1]) if value == "-c"))
                self.assertEqual(config["otel"]["span_attributes"]["agmark_invocation_id"], request["observation_id"])
                self.assertNotIn(":", Path(launched["cwd"]).name)
                self.assertFalse(Path(launched["cwd"]).exists())
                if profile == "deep_telemetry":
                    self.assertIsNotNone(launched["trace_root"])
                    self.assertNotIn(":", Path(launched["trace_root"]).name)
                    self.assertNotIn(request["observation_id"], launched["trace_root"])
                    self.assertFalse(Path(launched["trace_root"]).exists())
                else:
                    self.assertIsNone(launched["trace_root"])
                if mode == "wsl":
                    control = Path(self.bridges[-1].process_control_path)
                    self.assertNotIn(":", str(control))
                    self.assertNotIn(request["observation_id"], str(control))
                    self.assertFalse(control.parent.exists())

    def test_actual_echo_request_native_profiles(self):
        self.assert_echo_executes("native")

    def test_actual_echo_request_selected_host_profiles(self):
        self.assert_echo_executes("wsl")

    def test_private_diagnostic_directory_permission_failure_prevents_submission(self):
        original_chmod = Path.chmod
        scratch_paths = []

        def permission_denied(path, mode, **kwargs):
            if path.name.startswith("agmark-diagnostic-"):
                scratch_paths.append(path)
                raise PermissionError("/private/diagnostics Bearer offline-private")
            return original_chmod(path, mode, **kwargs)

        transport = MultiSignalTransport()
        with patch.object(Path, "chmod", permission_denied):
            observation = runner(transport).execute(echo_request(self.binary, "native", "deep_telemetry"))
        self.assertEqual(observation["terminal_status"], "unsupported")
        self.assertEqual(observation["extensions"]["arcgrav.runner:execution"]["error"]["code"],
                         "codex_cli_telemetry_diagnostics_unavailable")
        self.assertTrue(scratch_paths)
        self.assertTrue(all(not path.exists() for path in scratch_paths))
        self.assertFalse(any(call["input_bytes"] is not None for call in transport.calls))
        self.assertNotIn("offline-private", json.dumps(observation))

    def test_selected_host_diagnostic_permission_failure_is_safe_and_blocks_launch(self):
        from AgMark.shared.telemetry.wsl import BOOTSTRAP

        def failed_private_directory(*args, **kwargs):
            def local_worker(command, **options):
                # Only this offline worker fixture denies diagnostic chmod.
                prelude = """import pathlib
_original_chmod = pathlib.Path.chmod
def deny_diagnostic_chmod(path, mode, **kwargs):
    if path.name.startswith('agmark-diagnostic-'):
        raise PermissionError('/private/selected-host Bearer offline-private')
    return _original_chmod(path, mode, **kwargs)
pathlib.Path.chmod = deny_diagnostic_chmod
"""
                options["env"] = {**options["env"], "TMPDIR": str(self.fixture)}
                return subprocess.Popen((sys.executable, "-u", "-c", prelude + BOOTSTRAP), **options)
            capture = WslCaptureSession(*args, **kwargs, popen_factory=local_worker)
            self.addCleanup(capture.close)
            return capture

        transport = LocalSelectedHostTransport(self.fixture)
        adapter = CodexCliRunner(transport=transport, platform_name="nt", executable_resolver=lambda value: value,
                    launch_selection={"codex_binary": str(getattr(self, "binary", "/fixture/codex")), "wsl_distribution": "Selected Fixture Distribution"})
        with patch("AgMark.shared.telemetry.wsl.WslCaptureSession", side_effect=failed_private_directory):
            observation = adapter.execute(echo_request(self.binary, "wsl", "deep_telemetry"))
        self.assertEqual(observation["terminal_status"], "unsupported")
        self.assertEqual(observation["extensions"]["arcgrav.runner:execution"]["error"]["code"],
                         "codex_cli_telemetry_diagnostics_unavailable")
        self.assertFalse(any(actual for _, actual in transport.calls))
        self.assertFalse((self.fixture / "launched.json").exists())
        self.assertEqual(list(self.fixture.glob("agmark-diagnostic-*")), [])
        self.assertNotIn("offline-private", json.dumps(observation))


class CaptureSetupFailureTests(unittest.TestCase):
    def test_diagnostic_execution_rejects_unversioned_or_stale_acknowledgement(self):
        for mode in ("native", "wsl"):
            for acknowledgement in ("acknowledged", "acknowledged:agmark.original-diagnostics.stock-rollout@0.0.0",
                                    "not_acknowledged"):
                with self.subTest(mode=mode, acknowledgement=acknowledgement):
                    transport = MultiSignalTransport()
                    adapter = CodexCliRunner(transport=transport, platform_name="posix" if mode == "native" else "nt",
                                             executable_resolver=lambda value: value,
                    launch_selection={"codex_binary": str(getattr(self, "binary", "/fixture/codex")), "wsl_distribution": "Selected Fixture Distribution"})
                    observation = adapter.execute(echo_request("/fixture/codex", mode, "deep_telemetry", acknowledgement))
                    self.assertEqual(observation["terminal_status"], "unsupported")
                    self.assertEqual(transport.calls, [])

    def test_historical_acknowledgement_does_not_block_non_diagnostic_profiles(self):
        from AgMark.shared.software_testing.adapters.codex_cli.test_runner import FakeCodexTransport
        for profile in ("session", "telemetry"):
            with self.subTest(profile=profile):
                transport = FakeCodexTransport(version="0.159.0") if profile == "session" else MultiSignalTransport()
                observation = runner(transport).execute(echo_request("/fixture/codex", "native", profile, "acknowledged"))
                self.assertEqual(observation["terminal_status"], "completed")
                capture = observation["extensions"].get("agmark.telemetry:capture")
                if capture is not None:
                    self.assertFalse(capture["profile"]["diagnostics_enabled"])
                    self.assertEqual(capture["sources"]["diagnostics"]["state"], "disabled")

    def test_setup_errors_are_safe_specific_and_prevent_submission(self):
        stages = (
            ("AgMark.shared.telemetry.CaptureProfile.from_control", "codex_cli_telemetry_configuration_invalid"),
            ("AgMark.shared.telemetry.CaptureSession", "codex_cli_telemetry_initialization_failed"),
            ("AgMark.shared.telemetry.collector.MultiSignalCollector.start", "codex_cli_telemetry_collector_unavailable"),
            ("AgMark.shared.adapters.Codex_CLI.runner.CodexCliRunner._capture_argv", "codex_cli_telemetry_launch_configuration_failed"),
        )
        for profile in ("telemetry", "deep_telemetry"):
            for target, code in stages:
                with self.subTest(profile=profile, stage=code):
                    transport = MultiSignalTransport()
                    with patch(target, side_effect=OSError("/private/setup Bearer offline-private")):
                        observation = runner(transport).execute(echo_request("/fixture/codex", "native", profile))
                    self.assertEqual(observation["terminal_status"], "unsupported")
                    self.assertEqual(observation["extensions"]["arcgrav.runner:execution"]["error"]["code"], code)
                    self.assertFalse(any(call["input_bytes"] is not None for call in transport.calls))
                    self.assertNotIn("offline-private", json.dumps(observation))

    def test_selected_host_errors_use_only_known_stage_codes(self):
        for reason, code in (("selected_host_collector_unavailable", "codex_cli_telemetry_collector_unavailable"),
                             ("selected_host_diagnostics_unavailable", "codex_cli_telemetry_diagnostics_unavailable"),
                             ("/private/host Bearer offline-private", "codex_cli_telemetry_selected_host_unavailable")):
            with self.subTest(reason=reason):
                transport = MultiSignalTransport()
                adapter = CodexCliRunner(transport=transport, platform_name="nt", executable_resolver=lambda value: value,
                    launch_selection={"codex_binary": str(getattr(self, "binary", "/fixture/codex")), "wsl_distribution": "Selected Fixture Distribution"})
                with patch("AgMark.shared.telemetry.wsl.WslCaptureSession.start", side_effect=WslCaptureUnavailable(reason)):
                    observation = adapter.execute(echo_request("/fixture/codex", "wsl", "deep_telemetry"))
                self.assertEqual(observation["terminal_status"], "unsupported")
                self.assertEqual(observation["extensions"]["arcgrav.runner:execution"]["error"]["code"], code)
                self.assertFalse(any(call["input_bytes"] is not None for call in transport.calls))
                self.assertNotIn("offline-private", json.dumps(observation))

    def test_genuine_isolation_error_remains_distinct(self):
        @contextmanager
        def failed_isolation(*args, **kwargs):
            raise PermissionError("/private/workdir Bearer offline-private")
            yield  # pragma: no cover - establish a failing context manager

        transport = MultiSignalTransport()
        with patch("AgMark.shared.adapters.Codex_CLI.runner.temporary_workdir_isolation", failed_isolation):
            observation = runner(transport).execute(echo_request("/fixture/codex", "native", "telemetry"))
        self.assertEqual(observation["terminal_status"], "failed")
        self.assertEqual(observation["extensions"]["arcgrav.runner:execution"]["error"]["code"], "codex_cli_isolation_failed")
        self.assertFalse(any(call["input_bytes"] is not None for call in transport.calls))
        self.assertNotIn("offline-private", json.dumps(observation))


class CaptureIdentityTests(unittest.TestCase):
    def test_canonical_ids_round_trip_without_collisions(self):
        identifiers = ("gui-runner-test:echo-test", "observation:" + "a" * 64)
        for profile_id in ("telemetry", "deep_telemetry"):
            profile = CaptureProfile(profile_id, diagnostic_privacy_acknowledged=profile_id == "deep_telemetry")
            observed = []
            for identifier in identifiers:
                with self.subTest(profile=profile_id, identifier=identifier):
                    session = CaptureSession(profile, "0.159.0", identifier)
                    self.assertEqual(session.invocation_id, identifier)
                    bridge = WslCaptureSession(profile, "0.159.0", identifier,
                        launch_metadata={"launcher":"wsl", "distribution":"Fixture", "executable":"codex"})
                    self.assertEqual(bridge.invocation_id, identifier)
                    values = observation_overrides(identifier, "http://127.0.0.1:12345")
                    observed.append(tomllib.loads("\n".join(values))["otel"]["span_attributes"]["agmark_invocation_id"])
            self.assertEqual(observed, list(identifiers))
            self.assertEqual(len(set(observed)), 2)

    def test_path_and_shell_characters_remain_rejected_before_setup(self):
        for profile_id in ("telemetry", "deep_telemetry"):
            profile = CaptureProfile(profile_id, diagnostic_privacy_acknowledged=profile_id == "deep_telemetry")
            for identifier in ("../echo", "echo/test", "echo\\test", "echo..test", "echo test", 'echo"test', "echo\ntest", "$(echo)", "", "x" * 129):
                with self.subTest(profile=profile_id, identifier=identifier):
                    with self.assertRaises(ValueError):
                        CaptureSession(profile, "0.159.0", identifier)
                    with self.assertRaises(ValueError):
                        WslCaptureSession(profile, "0.159.0", identifier,
                            launch_metadata={"launcher":"wsl", "distribution":"Fixture", "executable":"codex"})
                    with self.assertRaises(ValueError):
                        observation_overrides(identifier, "http://127.0.0.1:12345")
