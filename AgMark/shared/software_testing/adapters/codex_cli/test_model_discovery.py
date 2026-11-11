"""Provider-free Codex model discovery and resolved-session coverage."""

from __future__ import annotations

from pathlib import Path
from queue import Queue
import subprocess
import threading
import time
import unittest

from AgMark.shared.adapters.Codex_CLI import load_registration
from AgMark.shared.adapters.Codex_CLI.model_discovery import (
    ModelDiscoveryError,
    _wait_for_response,
    decode_model_list_response,
    probe_model_discovery,
)


def _jsonrpc_stdout() -> bytes:
    return (
        b'{"id":"arcgrav-initialize","result":{"userAgent":"test"}}\n'
        b'{"id":"arcgrav-model-list","result":{"data":['
        b'{"model":"gpt-default","displayName":"GPT Default","hidden":false,"isDefault":true},'
        b'{"model":"gpt-fast","displayName":"GPT Fast","hidden":false,"isDefault":false}'
        b'],"nextCursor":null}}\n'
    )


class FakeProcessRunner:
    def __init__(self, *, app_server_returncode: int = 0) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
        self.app_server_returncode = app_server_returncode

    def __call__(self, argv, **kwargs):
        argv = tuple(argv)
        self.calls.append((argv, dict(kwargs)))
        if "sh" in argv and "-lc" in argv and "app-server" not in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=b"gunnanmon\n/home/gunnanmon\n",
                stderr=b"",
            )
        return subprocess.CompletedProcess(
            argv,
            self.app_server_returncode,
            stdout=_jsonrpc_stdout() if self.app_server_returncode == 0 else b"",
            stderr=b"" if self.app_server_returncode == 0 else b"app-server failed",
        )


class CodexModelDiscoveryTests(unittest.TestCase):
    def test_reasoning_capabilities_are_preserved_per_model_without_fixed_levels(self):
        projection = decode_model_list_response({"data": [{
            "model": "model", "displayName": "Model", "isDefault": True,
            "supportedReasoningEfforts": [
                {"reasoningEffort": "high", "description": "More thinking"},
                {"reasoningEffort": "future_level", "description": "New level"}],
            "defaultReasoningEffort": "future_level",
        }], "nextCursor": None})
        choice = projection["choices"][0]
        self.assertEqual("future_level", choice["default_reasoning_effort"])
        self.assertEqual([{"value": "high", "description": "More thinking"},
                          {"value": "future_level", "description": "New level"}], choice["reasoning_efforts"])

    def test_incomplete_ambiguous_or_invalid_reasoning_capabilities_are_rejected(self):
        for options, default in (
            ([], "medium"),
            ([{"reasoningEffort": "medium", "description": "Balanced"}], "high"),
            ([{"reasoningEffort": "medium"}], "medium"),
            ([{"reasoningEffort": "medium", "description": "A"},
              {"reasoningEffort": "medium", "description": "B"}], "medium"),
        ):
            with self.subTest(options=options, default=default), self.assertRaises(ModelDiscoveryError):
                decode_model_list_response({"data": [{
                    "model": "model", "displayName": "Model", "isDefault": True,
                    "supportedReasoningEfforts": options, "defaultReasoningEffort": default,
                }], "nextCursor": None})

    def test_wsl_default_discovers_codex_through_login_shell_path(self) -> None:
        runner = FakeProcessRunner()
        launcher = r"C:\Windows\System32\wsl.exe"
        result = probe_model_discovery(
            load_registration(),
            executable_resolver=lambda value: launcher if value == launcher else None,
            process_runner=runner,
            platform_name="nt",
        )
        self.assertEqual("ready", result["status"])
        self.assertEqual("codex", result["launch_environment"]["executable"])
        self.assertEqual(
            (launcher, "--distribution", "Ubuntu", "--exec", "sh", "-lc",
             'exec "$@"', "arcgrav-codex", "codex", "app-server", "--listen", "stdio://"),
            runner.calls[-1][0],
        )

    def test_early_launch_exit_identifies_executable_failure(self) -> None:
        class ExitedProcess:
            @staticmethod
            def poll() -> int:
                return 1

        with self.assertRaisesRegex(
            ModelDiscoveryError, "exited before answering.*exit code 1.*selected Codex executable"
        ):
            _wait_for_response(
                ExitedProcess(), Queue(), None, Queue(), [], [], set(),
                "arcgrav-initialize", deadline=time.monotonic() + 1.0,
            )

    def test_exited_process_waits_for_final_stdout_reader_delivery(self) -> None:
        stdout_queue: Queue[bytes] = Queue()
        stderr_queue: Queue[bytes] = Queue()
        line = b'{"id":"arcgrav-initialize","result":{}}\n'
        process_exit_seen = threading.Event()

        def deliver_final_line() -> None:
            process_exit_seen.wait(timeout=1.0)
            stdout_queue.put(line)

        reader = threading.Thread(target=deliver_final_line)
        reader.start()

        class ExitedProcess:
            @staticmethod
            def poll() -> int:
                process_exit_seen.set()
                return 0

        try:
            stdout_lines: list[bytes] = []
            response = _wait_for_response(
                ExitedProcess(), stdout_queue, reader, stderr_queue,
                stdout_lines, [], set(), "arcgrav-initialize",
                deadline=time.monotonic() + 1.0,
            )
            self.assertEqual({"id": "arcgrav-initialize", "result": {}}, response)
            self.assertEqual([line], stdout_lines)
        finally:
            reader.join(timeout=1.0)

    def test_model_list_projects_default_first_without_hidden_models(self) -> None:
        projection = decode_model_list_response(
            {
                "data": [
                    {
                        "model": "hidden",
                        "displayName": "Hidden",
                        "hidden": True,
                        "isDefault": False,
                    },
                    {
                        "model": "gpt-default",
                        "displayName": "GPT Default",
                        "hidden": False,
                        "isDefault": True,
                    },
                    {
                        "model": "gpt-fast",
                        "displayName": "GPT Fast",
                        "hidden": False,
                        "isDefault": False,
                    },
                ],
                "nextCursor": None,
            }
        )

        self.assertEqual("gpt-default", projection["effective_default_model_id"])
        self.assertEqual(
            ["gpt-default", "gpt-fast"],
            projection["selectable_model_ids"],
        )
        self.assertEqual(
            [
                {
                    "model_id": "gpt-default",
                    "selection_mode": "explicit",
                    "label": "Default (GPT Default)",
                },
                {
                    "model_id": "gpt-fast",
                    "selection_mode": "explicit",
                    "label": "GPT Fast",
                },
            ],
            projection["choices"],
        )

    def test_wsl_discovery_projects_user_codex_home_and_model_choices(self) -> None:
        runner = FakeProcessRunner()
        launcher = r"C:\Windows\System32\wsl.exe"
        result = probe_model_discovery(
            load_registration(),
            control_values={
                "launch_mode": "wsl",
                "wsl_distribution": "Ubuntu",
                "codex_binary": "/usr/bin/codex",
            },
            executable_resolver=lambda value: launcher if value == launcher else None,
            process_runner=runner,
            platform_name="nt",
        )

        self.assertEqual("ready", result["status"])
        self.assertFalse(result["provider_submitted"])
        self.assertEqual(
            {
                "wsl_user": "gunnanmon",
                "codex_home": "/home/gunnanmon/.codex",
            },
            result["resolved_configuration"],
        )
        self.assertEqual("gpt-default", result["effective_default_model_id"])
        self.assertEqual(2, len(result["choices"]))

        self.assertEqual(2, len(runner.calls))
        session_argv, _session_kwargs = runner.calls[0]
        self.assertEqual(
            (
                launcher,
                "--distribution",
                "Ubuntu",
                "--exec",
                "sh",
                "-lc",
            ),
            session_argv[:6],
        )
        app_argv, app_kwargs = runner.calls[1]
        self.assertEqual(
            (
                launcher,
                "--distribution",
                "Ubuntu",
                "--exec",
                "/usr/bin/codex",
                "app-server",
                "--listen",
                "stdio://",
            ),
            app_argv,
        )
        request = app_kwargs["input"]
        self.assertIsInstance(request, bytes)
        self.assertIn(b'"method":"model/list"', request)
        self.assertNotIn(b"account/read", request)
        self.assertNotIn(b"config/read", request)
        self.assertNotIn(b"login", request)

    def test_native_discovery_uses_selected_binary_and_default_codex_home(self) -> None:
        runner = FakeProcessRunner()
        executable = str(Path.home() / "codex" / "bin" / "codex")
        result = probe_model_discovery(
            load_registration(),
            control_values={
                "launch_mode": "native",
                "codex_binary": "codex",
            },
            executable_resolver=lambda value: (
                executable if value == "codex" else None
            ),
            process_runner=runner,
            platform_name="posix",
        )

        self.assertEqual("ready", result["status"])
        self.assertEqual(
            (executable, "app-server", "--listen", "stdio://"),
            runner.calls[0][0],
        )
        self.assertEqual(
            str(Path.home() / ".codex"),
            result["resolved_configuration"]["codex_home"],
        )

    def test_model_failure_preserves_resolved_wsl_session_projection(self) -> None:
        runner = FakeProcessRunner(app_server_returncode=1)
        launcher = r"C:\Windows\System32\wsl.exe"
        result = probe_model_discovery(
            load_registration(),
            control_values={
                "launch_mode": "wsl",
                "wsl_distribution": "Ubuntu",
                "codex_binary": "/usr/bin/codex",
            },
            executable_resolver=lambda value: launcher if value == launcher else None,
            process_runner=runner,
            platform_name="nt",
        )

        self.assertEqual("unsupported", result["status"])
        self.assertEqual(
            "codex_cli_model_catalog_unavailable",
            result["error_code"],
        )
        self.assertEqual(
            "/home/gunnanmon/.codex",
            result["resolved_configuration"]["codex_home"],
        )


if __name__ == "__main__":
    unittest.main()
