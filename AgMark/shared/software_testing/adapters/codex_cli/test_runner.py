"""Provider-free conformance tests for the simplified Codex CLI runner."""

from __future__ import annotations

import copy
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from AgMark.shared.adapters.Codex_CLI import CodexCliRunner, load_registration
from AgMark.shared.adapters.Codex_CLI.model_discovery import probe_model_discovery
from AgMark.shared.adapters.Codex_CLI.runner import (
    probe_planning_identity,
    resolve_target_composition,
)
from AgMark.shared.software_testing.adapters.codex_cli.fixtures.codex_protocol.protocol.cli import (
    AUTHENTICATION_LIKE_MODEL_ID,
    PREFLIGHT_PROFILE_ENV,
    SCENARIO_MODEL_ID_PREFIX,
)
from AgMark.shared.adapters.execution import (
    EXECUTION_EVIDENCE_EXTENSION_KEY,
    InvocationCancelled,
    validate_execution_evidence,
)
from AgMark.shared.mock_model.protocol import DEFAULT_RUNTIME_VERSION
from AgMark.shared.mock_model.scenarios import (
    CANCELLATION_SCENARIO,
    CAPABILITY_FAILURE_SCENARIO,
    COMPLETED_SCENARIO,
    DISCOVERY_FAILURE_SCENARIO,
    DISCOVERY_PROTOCOL_INVALID_SCENARIO,
    RUNTIME_PROBE_FAILURE_SCENARIO,
    RUNTIME_VERSION_MISMATCH_SCENARIO,
    TIMEOUT_SCENARIO,
)
from AgMark.shared.validation import (
    ArtifactSource,
    ContractRequirement,
    validate_registration_binding_outcome,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_RUNNER_ID = "openai.codex-cli"
_RUNNER_VERSION = "2.0.0"
_MOCK_RUNNER_ID = "fixture.codex-protocol"
_MOCK_RUNNER_VERSION = "1.0.0"
_MOCK_PROVIDER = "AgMark Mock Model"
_MOCK_CLI_MODULE = "AgMark.shared.software_testing.adapters.codex_cli.fixtures.codex_protocol.protocol"
_VERSION = "1.2.3"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _controls(
    *,
    launch_mode: str = "native",
    model_id: str = "gpt-5-codex",
    timeout_ms: int = 120000,
) -> list[dict[str, object]]:
    values: list[dict[str, object]] = [
        {"name": "launch_mode", "value": launch_mode},
        {
            "name": "codex_binary",
            "value": "/usr/bin/codex" if launch_mode == "wsl" else "codex",
        },
        {"name": "model_id", "value": model_id},
        {"name": "approval_mode", "value": "full_auto"},
        {"name": "request_timeout_ms", "value": timeout_ms},
        {"name": "maximum_attempts", "value": 1},
        {"name": "memory_policy", "value": "disabled"},
        {"name": "request_framing", "value": "codex_cli"},
        {"name": "sampling_mode", "value": "provider_default"},
        {"name": "tool_policy", "value": "workspace_write"},
    ]
    if launch_mode == "wsl":
        values.insert(2, {"name": "wsl_distribution", "value": "Ubuntu"})
    return values


def _boundary(
    *,
    launch_mode: str = "native",
    model_id: str = "gpt-5-codex",
    runtime_version: str | None = _VERSION,
    timeout_ms: int = 120000,
    runner_id: str = _RUNNER_ID,
    runner_version: str = _RUNNER_VERSION,
    provider: str = "OpenAI",
) -> dict[str, object]:
    fingerprint = _sha256(b"codex-cli-simplified-boundary")
    return {
        "schema_id": "arcgrav.shared.schema.execution-boundary",
        "schema_version": "1.0.0",
        "extensions": {},
        "boundary_id": "boundary-codex-cli-simplified",
        "canonicalization": "arcgrav.canonical-json.v1",
        "canonical_sha256": _sha256(b"codex-cli-simplified-canonical"),
        "fingerprint": fingerprint,
        "framework": {"id": "arcgrav.framework.test", "version": "1.0.0"},
        "runner": {"id": runner_id, "version": runner_version},
        "provider_runtime": {
            "runtime_id": runner_id,
            "runtime_version": runtime_version,
            "provider": provider,
            "access_method": "cli",
            "model": model_id,
        },
        "controls": _controls(
            launch_mode=launch_mode,
            model_id=model_id,
            timeout_ms=timeout_ms,
        ),
        "environment": [],
    }


def _mock_registration() -> dict[str, object]:
    registration = copy.deepcopy(load_registration())
    registration["registration_id"] = _MOCK_RUNNER_ID
    registration["registration_version"] = _MOCK_RUNNER_VERSION
    extensions = registration["extensions"]
    extensions["arcgrav.adapters:model_discovery"].pop("reasoning_effort_control", None)
    extensions["arcgrav.adapters:supported_controls"] = [control for control in
        extensions["arcgrav.adapters:supported_controls"] if control["name"] != "reasoning_effort"]
    extensions["arcgrav.adapters:evidence_class"] = "provider-free-mock-model-execution"
    extensions["arcgrav.adapters:access_methods"][0]["authentication_class"] = (
        "not_applicable"
    )
    composition = extensions["arcgrav.adapters:target_composition"]
    composition.update(
        {
            "target_class": "mock-model",
            "external_provider_submission": False,
            "compatibility_profile": "codex-cli",
            "runtime_provider": _MOCK_PROVIDER,
            "authentication_source": None,
        }
    )
    return registration


def _request(boundary: dict[str, object], *, suffix: str = "a") -> dict[str, object]:
    prompt = b"adapter prompt"
    case_input = b"adapter input"
    return {
        "accepted_generation_id": "generation-codex-cli-simplified",
        "request_id": f"request-{suffix}",
        "observation_id": "observation:" + hashlib.sha256(suffix.encode("utf-8")).hexdigest(),
        "benchmark_id": "benchmark-neutral-adapter-test",
        "case_id": "case-adapter-test",
        "treatment_id": "treatment-adapter-test",
        "repetition": 1,
        "execution_boundary_fingerprint": boundary["fingerprint"],
        "execution_boundary": copy.deepcopy(boundary),
        "conversation_policy": {
            "new_conversation": True,
            "reuse_prior_observation_context": False,
        },
        "prompt": {"content": prompt, "sha256": _sha256(prompt)},
        "input": {"content": case_input, "sha256": _sha256(case_input)},
        "request_identity": {
            "prompt_sha256": _sha256(prompt),
            "input_sha256": _sha256(case_input),
            "request_sha256": _sha256(f"request-{suffix}".encode("utf-8")),
        },
    }


def _mock_cli_environment(env_value: object | None) -> dict[str, str]:
    if env_value is None:
        env = os.environ.copy()
    elif isinstance(env_value, Mapping):
        env = dict(env_value)
    else:
        raise TypeError("mock CLI environment must be a mapping")
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(_REPOSITORY_ROOT)
        if not current_pythonpath
        else str(_REPOSITORY_ROOT) + os.pathsep + current_pythonpath
    )
    return env


def _run_mock_cli_process(
    argv: tuple[str, ...],
    **kwargs: object,
) -> subprocess.CompletedProcess[bytes]:
    kwargs["env"] = _mock_cli_environment(kwargs.get("env"))
    return subprocess.run(
        (sys.executable, "-m", _MOCK_CLI_MODULE, *argv[1:]),
        **kwargs,
    )


class FakeCodexTransport:
    def read_session(self, thread_id, *, launch_environment, environment):
        # Explicit persisted-rollout fixture for this injected transport. This
        # conversion is test-only; production never synthesizes a rollout.
        import base64
        entries = [{"type": "session_meta", "payload": {"id": thread_id}},
                   {"type": "turn_context", "payload": {"model": "fixture-model", "effort": "medium"}}]
        from AgMark.shared.adapters.Codex_CLI.events import decode_events
        events, _ = decode_events(getattr(self, "process_stdout", b""))
        for event in events:
            if event["type"] == "turn.completed":
                usage = dict(event.get("usage", {}))
                if "input_tokens" in usage and "output_tokens" in usage:
                    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
                entries.append({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage}}})
            elif event["type"] == "item.completed" and event.get("item", {}).get("type") == "command_execution":
                item = event["item"]
                entries.extend([{"type": "response_item", "payload": {"type": "function_call", "call_id": item["id"], "name": "exec_command"}},
                                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": item["id"], "exit_code": item.get("exit_code", 0), "status": item.get("status")}}])
        entries.append({"type": "event_msg", "payload": {"type": "task_complete"}})
        raw = b"".join((json.dumps({"timestamp": "2026-10-03T12:00:00Z", **entry}) + "\n").encode() for entry in entries)
        return {"availability": "retained", "thread_id": thread_id, "content_base64": base64.b64encode(raw).decode(), "root": "fixture", "path": "fixture.jsonl"}

    def __init__(
        self,
        *,
        response: bytes = b"exact final answer\n",
        actual_returncode: int = 0,
        actual_stderr: bytes = b"",
        actual_exception: BaseException | None = None,
        version: str = _VERSION,
        structured_output: bool = False,
    ) -> None:
        self.response = response
        self.structured_output = structured_output
        self.actual_returncode = actual_returncode
        self.actual_stderr = actual_stderr
        self.actual_exception = actual_exception
        self.version = version
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None,
        cwd: Path,
        env: dict[str, str],
        timeout_ms: int,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "argv": tuple(argv),
                "input_bytes": input_bytes,
                "cwd": str(cwd),
                "env": copy.deepcopy(env),
                "timeout_ms": timeout_ms,
            }
        )
        if "--distribution" in argv and "test" in argv and "-x" in argv:
            return {"returncode": 0, "stdout": b"", "stderr": b""}
        if argv[-1:] == ("--version",):
            return {
                "returncode": 0,
                "stdout": f"codex-cli {self.version}\n".encode("ascii"),
                "stderr": b"",
            }
        if argv[-2:] == ("exec", "--help"):
            return {
                "returncode": 0,
                "stdout": b"Usage: codex exec [OPTIONS]",
                "stderr": b"",
            }
        if self.actual_exception is not None:
            raise self.actual_exception
        from uuid import uuid4
        events = [{"type": "thread.started", "thread_id": str(uuid4())}, {"type": "turn.started"}]
        if self.response:
            events.append({"type": "item.completed", "item": {"id": "answer", "type": "agent_message", "text": self.response.decode("utf-8")}})
        events.append({"type": "turn.completed", "usage": {}})
        self.process_stdout = self.response if self.structured_output else b"".join((json.dumps(e) + "\n").encode() for e in events)
        return {
            "returncode": self.actual_returncode,
            "stdout": self.process_stdout,
            "stderr": self.actual_stderr,
        }


class MockCodexCliProcessTransport:
    def read_session(self, thread_id, *, launch_environment, environment):
        from AgMark.shared.adapters.Codex_CLI.session_capture import read_session, session_root
        return read_session(thread_id, root=session_root(environment))

    def __init__(self, *, preflight_profile_id: str | None = None) -> None:
        self.preflight_profile_id = preflight_profile_id
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None,
        cwd: Path,
        env: dict[str, str],
        timeout_ms: int,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "argv": tuple(argv),
                "input_bytes": input_bytes,
                "cwd": str(cwd),
                "env": copy.deepcopy(env),
                "timeout_ms": timeout_ms,
            }
        )
        process_env = copy.deepcopy(env)
        if self.preflight_profile_id is not None:
            process_env[PREFLIGHT_PROFILE_ENV] = self.preflight_profile_id
        completed = _run_mock_cli_process(
            argv,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_ms / 1000.0,
            check=False,
            cwd=cwd,
            env=process_env,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }


class CancellingMockCodexCliProcessTransport(MockCodexCliProcessTransport):
    def run(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None,
        cwd: Path,
        env: dict[str, str],
        timeout_ms: int,
    ) -> dict[str, object]:
        if argv[1:2] != ("exec",) or argv[-1:] != ("-",):
            return super().run(
                argv,
                input_bytes=input_bytes,
                cwd=cwd,
                env=env,
                timeout_ms=timeout_ms,
            )

        self.calls.append(
            {
                "argv": tuple(argv),
                "input_bytes": input_bytes,
                "cwd": str(cwd),
                "env": copy.deepcopy(env),
                "timeout_ms": timeout_ms,
            }
        )
        process = subprocess.Popen(
            (sys.executable, "-m", _MOCK_CLI_MODULE, *argv[1:]),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=_mock_cli_environment(env),
        )
        try:
            stdout, stderr = process.communicate(
                input=input_bytes,
                timeout=0.5,
            )
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=2.0)
            raise InvocationCancelled(stdout=stdout, stderr=stderr)
        return {
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }


class CodexCliAdapterTests(unittest.TestCase):
    def setUp(self):
        catalog = {"data": [{
            "model": "gpt-5-codex", "displayName": "Codex", "isDefault": True,
            "supportedReasoningEfforts": [{"reasoningEffort": "medium", "description": "Balanced"},
                                          {"reasoningEffort": "high", "description": "More reasoning"}],
            "defaultReasoningEffort": "medium",
        }], "nextCursor": None}
        self.catalog_patch = patch("AgMark.shared.adapters.Codex_CLI.model_discovery._run_interactive_model_list", return_value=catalog)
        self.catalog_probe = self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)

    def test_text_counter_cannot_override_registered_structured_source(self):
        from AgMark.shared.evaluation.telemetry.consumption import ATTEMPT_MEASUREMENTS
        from AgMark.shared.adapters.execution import validate_retained_parity_observation
        from AgMark.shared.adapters.execution.emission import CanonicalObservationError
        import base64
        for stderr, expected in ((b"tokens used\n1,234\n",1234), (b"tokens used\r\n0\r\n",0),
                                 (b"tokens used\n1,23\n",None), (b"tokens used\n1\ntokens used\n2\n",None), (b"",None)):
            for code in (0, 23):
                with self.subTest(stderr=stderr, code=code):
                    runner=self._native_runner(FakeCodexTransport(actual_stderr=stderr, actual_returncode=code))
                    self.addCleanup(runner.close)
                    value=runner.execute(_request(_boundary()))
                    validate_retained_parity_observation(value)
                    measured=value["extensions"][ATTEMPT_MEASUREMENTS]
                    self.assertIsNone(measured["roles"]["total_tokens"]["value"])
                    self.assertEqual(value["extensions"]["openai.codex_cli:session-record"]["sha256"],measured["source_identity"])
                    self.assertNotIn("arcgrav.runner:process_stderr_base64", value["extensions"])
                    for role in ("input_tokens","cached_input_tokens","output_tokens","cost"):
                        self.assertIsNone(measured["roles"][role]["value"])
                    self.assertTrue(measured["tool_trace_complete"])
                    if expected is not None:
                        bad=copy.deepcopy(value)
                        bad["extensions"][ATTEMPT_MEASUREMENTS]["source_identity"]="sha256:"+"f"*64
                        with self.assertRaises(CanonicalObservationError): validate_retained_parity_observation(bad)
                        bad=copy.deepcopy(value)
                        bad["extensions"]["arcgrav.runner:process_stderr_base64"]=base64.b64encode(b"changed").decode()
                        with self.assertRaises(CanonicalObservationError): validate_retained_parity_observation(bad)

    def _native_runner(self, transport: FakeCodexTransport) -> CodexCliRunner:
        return CodexCliRunner(
            transport=transport,
            executable_resolver=lambda value: (
                "/opt/codex/bin/codex" if value == "codex" else None
            ),
            timestamp=lambda: "2026-09-26T12:00:00Z",
            monotonic=lambda: 100.0,
            platform_name="posix",
        )

    def _wsl_runner(self, transport: FakeCodexTransport) -> CodexCliRunner:
        return CodexCliRunner(
            transport=transport,
            executable_resolver=lambda value: (
                value if value == r"C:\Windows\System32\wsl.exe" else None
            ),
            timestamp=lambda: "2026-09-26T12:00:00Z",
            monotonic=lambda: 100.0,
            platform_name="nt",
        )

    def _mock_runner(self, transport: object) -> CodexCliRunner:
        return CodexCliRunner(
            registration=_mock_registration(),
            transport=transport,
            executable_resolver=lambda value: (
                "/opt/mock/bin/codex" if value == "codex" else None
            ),
            timestamp=lambda: "2026-09-26T12:00:00Z",
            monotonic=lambda: 100.0,
            platform_name="posix",
        )

    def test_registration_is_schema_bound_and_simplified(self) -> None:
        registration = load_registration()
        sources = tuple(
            ArtifactSource(
                artifact_id=item["artifact_id"],
                reference=item["reference"],
                data=(_REPOSITORY_ROOT / item["reference"]).read_bytes(),
            )
            for item in registration["implementation_artifacts"]
        )
        outcome = validate_registration_binding_outcome(
            registration,
            expected_registration_id=_RUNNER_ID,
            expected_registration_version=_RUNNER_VERSION,
            contract_requirements=(
                ContractRequirement(
                    "arcgrav.shared.runner-invocation",
                    ("2.0.0",),
                ),
            ),
            artifact_sources=sources,
            allowed_artifact_roots=("AgMark/shared/adapters", "AgMark/shared/telemetry", "AgMark/shared/evaluation/telemetry/source.py", "AgMark/shared/runtime/identity/runtime_version.py"),
            source_id="codex-cli-simplified-registration-test",
        )
        self.assertTrue(outcome.valid, [issue.code for issue in outcome.issues])

        extensions = registration["extensions"]
        target_composition = extensions["arcgrav.adapters:target_composition"]
        self.assertEqual("live-provider", target_composition["target_class"])
        self.assertTrue(target_composition["external_provider_submission"])
        self.assertIsNone(target_composition["compatibility_profile"])
        self.assertIn("arcgrav.adapters:model_discovery", extensions)
        self.assertIn("arcgrav.adapters:resolved_configuration", extensions)
        self.assertNotIn("arcgrav.adapters:secret_handling", extensions)
        self.assertEqual(
            "codex_session",
            extensions["arcgrav.adapters:access_methods"][0][
                "authentication_class"
            ],
        )
        controls = {
            item["name"]: item
            for item in extensions["arcgrav.adapters:supported_controls"]
        }
        self.assertEqual("choice", controls["model_id"]["kind"])
        self.assertTrue(controls["model_id"]["required"])
        self.assertTrue(controls["wsl_distribution"]["required"])
        self.assertEqual("choice", controls["model_selection_mode"]["kind"])
        self.assertEqual(["explicit"], controls["model_selection_mode"]["values"])
        self.assertFalse(controls["model_selection_mode"]["comparison_relevant"])
        artifact_ids = {
            item["artifact_id"] for item in registration["implementation_artifacts"]
        }
        self.assertNotIn(
            "AgMark/shared/adapters/Codex_CLI/authentication.py",
            artifact_ids,
        )
        self.assertIn(
            "AgMark/shared/adapters/Codex_CLI/model_discovery.py",
            artifact_ids,
        )

    def test_describe_exposes_discovery_backed_model_and_no_credentials(self) -> None:
        runner = self._native_runner(FakeCodexTransport())
        description = runner.describe()
        self.assertEqual("choice", description["supported_controls"]["model_id"]["kind"])
        self.assertTrue(
            description["supported_controls"]["wsl_distribution"]["required"]
        )
        self.assertFalse(description["secret_handling"]["credentials_required"])
        self.assertEqual(
            "codex_session",
            description["access_methods"][0]["authentication_class"],
        )

    def test_live_target_composition_is_registration_and_boundary_bound(self) -> None:
        registration = load_registration()
        expected_artifacts = tuple(
            item["artifact_id"] for item in registration["implementation_artifacts"]
        )
        cases = (
            (
                "native",
                {"mode": "native", "executable": "/opt/codex/bin/codex"},
                (),
                "/opt/codex/bin/codex",
            ),
            (
                "wsl",
                {
                    "mode": "wsl",
                    "distribution": "Ubuntu",
                    "executable": "/usr/bin/codex",
                },
                (("wsl_distribution", "Ubuntu"),),
                "/usr/bin/codex",
            ),
        )
        for launch_mode, launch_environment, selector, executable in cases:
            with self.subTest(launch_mode=launch_mode):
                descriptor = resolve_target_composition(
                    registration,
                    execution_boundary=_boundary(launch_mode=launch_mode),
                    launch_environment=launch_environment,
                )
                self.assertEqual("live-provider", descriptor.target_class)
                self.assertEqual(
                    "live-provider-execution",
                    descriptor.evidence_class,
                )
                self.assertEqual(_RUNNER_ID, descriptor.runtime_id)
                self.assertEqual(_VERSION, descriptor.runtime_version)
                self.assertEqual("cli", descriptor.access_method)
                self.assertTrue(descriptor.external_provider_submission)
                self.assertEqual(launch_mode, descriptor.launch_mode)
                self.assertEqual(selector, descriptor.launch_environment_selector)
                self.assertEqual(executable, descriptor.executable)
                self.assertEqual(
                    "codex_session",
                    descriptor.authentication_class,
                )
                self.assertIsNone(descriptor.compatibility_profile)
                self.assertEqual(
                    "AgMark.shared.adapters.Codex_CLI:CodexCliRunner",
                    descriptor.production_runner_entry_point,
                )
                self.assertEqual(
                    expected_artifacts,
                    descriptor.runner_implementation_artifact_ids,
                )

    def test_live_target_composition_rejects_registration_boundary_mismatch(self) -> None:
        registration = load_registration()
        boundary = _boundary()
        boundary["provider_runtime"]["runtime_id"] = "other.runtime"
        with self.assertRaises(ValueError):
            resolve_target_composition(
                registration,
                execution_boundary=boundary,
                launch_environment={
                    "mode": "native",
                    "executable": "/opt/codex/bin/codex",
                },
            )

    def test_registration_bound_mock_composition_uses_same_execution_path(self) -> None:
        transport = FakeCodexTransport()
        registration = _mock_registration()
        runner = CodexCliRunner(
            registration=registration,
            transport=transport,
            executable_resolver=lambda value: (
                "/opt/mock/bin/codex" if value == "codex" else None
            ),
            timestamp=lambda: "2026-09-26T12:00:00Z",
            monotonic=lambda: 100.0,
            platform_name="posix",
        )
        model_id = "arcgrav.mock-model:completed"
        boundary = _boundary(
            model_id=model_id,
            runner_id=_MOCK_RUNNER_ID,
            runner_version=_MOCK_RUNNER_VERSION,
            provider=_MOCK_PROVIDER,
        )
        descriptor = resolve_target_composition(
            registration,
            execution_boundary=boundary,
            launch_environment={
                "mode": "native",
                "executable": "/opt/mock/bin/codex",
            },
        )
        self.assertEqual("mock-model", descriptor.target_class)
        self.assertEqual(
            "AgMark.shared.adapters.Codex_CLI:CodexCliRunner",
            descriptor.production_runner_entry_point,
        )
        self.assertEqual(
            tuple(
                registration["extensions"]["arcgrav.adapters:target_composition"][
                    "runner_implementation_artifact_ids"
                ]
            ),
            descriptor.runner_implementation_artifact_ids,
        )

        observation = runner.execute(_request(boundary, suffix="mock"))

        self.assertEqual(
            {"id": _MOCK_RUNNER_ID, "version": _MOCK_RUNNER_VERSION},
            observation["runner"],
        )
        self.assertEqual("completed", observation["terminal_status"])
        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        validate_execution_evidence(canonical)
        self.assertEqual("mock-model", canonical["target"]["class"])
        self.assertEqual(
            "provider-free-mock-model-execution",
            canonical["target"]["evidence_class"],
        )
        self.assertEqual(
            {
                "availability": "observed",
                "occurred": True,
                "external_provider": False,
            },
            canonical["submission"],
        )
        self.assertEqual(
            {
                "availability": "not_applicable",
                "class": None,
                "source": None,
            },
            canonical["authentication"],
        )
        self.assertEqual(
            (
                "/opt/mock/bin/codex",
                "exec",
                "--model",
                model_id,
                "--approve-for-me",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--json",
                "-",
            ),
            transport.calls[-1]["argv"],
        )

    def test_discovered_mock_scenario_model_uses_unchanged_explicit_model_path(self) -> None:
        registration = _mock_registration()
        model_id = f"{SCENARIO_MODEL_ID_PREFIX}{COMPLETED_SCENARIO}"
        discovery = probe_model_discovery(
            registration,
            control_values={
                "launch_mode": "native",
                "codex_binary": "codex",
            },
            executable_resolver=lambda value: (
                "/opt/mock/bin/codex" if value == "codex" else None
            ),
            process_runner=_run_mock_cli_process,
            platform_name="posix",
            process_cwd=_REPOSITORY_ROOT,
        )
        self.assertEqual("ready", discovery["status"])
        self.assertFalse(discovery["provider_submitted"])
        self.assertIn(model_id, discovery["selectable_model_ids"])

        transport = MockCodexCliProcessTransport()
        runner = CodexCliRunner(
            registration=registration,
            transport=transport,
            executable_resolver=lambda value: (
                "/opt/mock/bin/codex" if value == "codex" else None
            ),
            timestamp=lambda: "2026-09-26T12:00:00Z",
            monotonic=lambda: 100.0,
            platform_name="posix",
        )
        boundary = _boundary(
            model_id=model_id,
            runtime_version=DEFAULT_RUNTIME_VERSION,
            runner_id=_MOCK_RUNNER_ID,
            runner_version=_MOCK_RUNNER_VERSION,
            provider=_MOCK_PROVIDER,
        )
        observation = runner.execute(_request(boundary, suffix="scenario"))

        self.assertEqual("completed", observation["terminal_status"])
        self.assertEqual(
            (
                "/opt/mock/bin/codex",
                "exec",
                "--model",
                model_id,
                "--approve-for-me",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--json",
                "-",
            ),
            transport.calls[-1]["argv"],
        )
        self.assertEqual(
            b"adapter prompt\n\nadapter input",
            transport.calls[-1]["input_bytes"],
        )
        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        validate_execution_evidence(canonical)
        self.assertEqual("mock-model", canonical["target"]["class"])
        self.assertFalse(canonical["submission"]["external_provider"])

    def test_mock_preflight_failure_profiles_use_unchanged_probes(self) -> None:
        model_id = f"{SCENARIO_MODEL_ID_PREFIX}{COMPLETED_SCENARIO}"
        boundary = _boundary(
            model_id=model_id,
            runtime_version=DEFAULT_RUNTIME_VERSION,
            runner_id=_MOCK_RUNNER_ID,
            runner_version=_MOCK_RUNNER_VERSION,
            provider=_MOCK_PROVIDER,
        )
        cases = (
            (
                RUNTIME_PROBE_FAILURE_SCENARIO,
                "codex_cli_version_unavailable",
                [
                    ("/opt/mock/bin/codex", "--version"),
                ],
            ),
            (
                CAPABILITY_FAILURE_SCENARIO,
                "codex_cli_noninteractive_unavailable",
                [
                    ("/opt/mock/bin/codex", "--version"),
                    ("/opt/mock/bin/codex", "exec", "--help"),
                ],
            ),
            (
                RUNTIME_VERSION_MISMATCH_SCENARIO,
                "codex_cli_version_unsupported",
                [
                    ("/opt/mock/bin/codex", "--version"),
                    ("/opt/mock/bin/codex", "exec", "--help"),
                ],
            ),
        )

        for profile_id, error_code, expected_calls in cases:
            with self.subTest(profile_id=profile_id):
                transport = MockCodexCliProcessTransport(
                    preflight_profile_id=profile_id,
                )
                observation = self._mock_runner(transport).execute(
                    _request(boundary, suffix=f"preflight-{profile_id}")
                )

                self.assertEqual("unsupported", observation["terminal_status"])
                self.assertEqual(
                    error_code,
                    observation["attempts"][0]["error_code"],
                )
                self.assertEqual(
                    expected_calls,
                    [call["argv"] for call in transport.calls],
                )
                self.assertFalse(
                    any(
                        call["argv"][1:2] == ("exec",)
                        and call["argv"][-1:] == ("-",)
                        for call in transport.calls
                    )
                )

    def test_mock_discovery_failure_profiles_use_production_decoder(self) -> None:
        registration = _mock_registration()
        for profile_id in (
            DISCOVERY_FAILURE_SCENARIO,
            DISCOVERY_PROTOCOL_INVALID_SCENARIO,
        ):
            with self.subTest(profile_id=profile_id):
                result = probe_model_discovery(
                    registration,
                    control_values={
                        "launch_mode": "native",
                        "codex_binary": "codex",
                    },
                    executable_resolver=lambda value: (
                        "/opt/mock/bin/codex" if value == "codex" else None
                    ),
                    process_runner=_run_mock_cli_process,
                    platform_name="posix",
                    process_cwd=_REPOSITORY_ROOT,
                    process_env={PREFLIGHT_PROFILE_ENV: profile_id},
                )

                self.assertEqual("unsupported", result["status"])
                self.assertEqual(
                    "codex_cli_model_catalog_unavailable",
                    result["error_code"],
                )
                self.assertFalse(result["provider_submitted"])

    def test_mock_authentication_rejection_uses_existing_classifier(self) -> None:
        registration = _mock_registration()
        discovery = probe_model_discovery(
            registration,
            control_values={
                "launch_mode": "native",
                "codex_binary": "codex",
            },
            executable_resolver=lambda value: (
                "/opt/mock/bin/codex" if value == "codex" else None
            ),
            process_runner=_run_mock_cli_process,
            platform_name="posix",
            process_cwd=_REPOSITORY_ROOT,
        )
        self.assertEqual("ready", discovery["status"])
        self.assertIn(
            AUTHENTICATION_LIKE_MODEL_ID,
            discovery["selectable_model_ids"],
        )

        boundary = _boundary(
            model_id=AUTHENTICATION_LIKE_MODEL_ID,
            runtime_version=DEFAULT_RUNTIME_VERSION,
            runner_id=_MOCK_RUNNER_ID,
            runner_version=_MOCK_RUNNER_VERSION,
            provider=_MOCK_PROVIDER,
        )
        observation = self._mock_runner(
            MockCodexCliProcessTransport()
        ).execute(_request(boundary, suffix="mock-auth"))

        self.assertEqual("failed", observation["terminal_status"])
        self.assertEqual(
            "codex_cli_authentication_failed",
            observation["attempts"][0]["error_code"],
        )
        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        validate_execution_evidence(canonical)
        self.assertEqual(25, canonical["process"]["exit_status"])
        self.assertEqual(
            "codex_cli_authentication_failed",
            canonical["error"]["classification"],
        )
        self.assertTrue(canonical["submission"]["occurred"])
        self.assertFalse(canonical["submission"]["external_provider"])

    def test_mock_timeout_scenario_uses_shared_timeout_path(self) -> None:
        model_id = f"{SCENARIO_MODEL_ID_PREFIX}{TIMEOUT_SCENARIO}"
        # Leave time for the real Python target's version/help startup. This
        # case exercises an inference timeout, not an earlier preflight timeout.
        timeout_ms = 5000
        boundary = _boundary(
            model_id=model_id,
            timeout_ms=timeout_ms,
            runtime_version=DEFAULT_RUNTIME_VERSION,
            runner_id=_MOCK_RUNNER_ID,
            runner_version=_MOCK_RUNNER_VERSION,
            provider=_MOCK_PROVIDER,
        )

        self.assertEqual(
            timeout_ms,
            next(
                control["value"]
                for control in boundary["controls"]
                if control["name"] == "request_timeout_ms"
            ),
        )
        transport = MockCodexCliProcessTransport()
        observation = self._mock_runner(transport).execute(
            _request(boundary, suffix="mock-timeout")
        )

        self.assertEqual(
            timeout_ms,
            transport.calls[-1]["timeout_ms"],
        )
        self.assertEqual(
            ("/opt/mock/bin/codex", "exec", "--model", model_id),
            transport.calls[-1]["argv"][:4],
        )
        self.assertEqual("timed_out", observation["terminal_status"])
        self.assertEqual(
            "codex_cli_process_timed_out",
            observation["attempts"][0]["error_code"],
        )
        self.assertEqual("not_produced", observation["response"]["availability"])
        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        validate_execution_evidence(canonical)
        self.assertEqual("timed_out", canonical["process"]["transport_status"])
        self.assertTrue(canonical["submission"]["occurred"])
        self.assertFalse(canonical["submission"]["external_provider"])

    def test_mock_cancellation_scenario_uses_shared_cancellation_path(self) -> None:
        model_id = f"{SCENARIO_MODEL_ID_PREFIX}{CANCELLATION_SCENARIO}"
        boundary = _boundary(
            model_id=model_id,
            runtime_version=DEFAULT_RUNTIME_VERSION,
            runner_id=_MOCK_RUNNER_ID,
            runner_version=_MOCK_RUNNER_VERSION,
            provider=_MOCK_PROVIDER,
        )

        observation = self._mock_runner(
            CancellingMockCodexCliProcessTransport()
        ).execute(_request(boundary, suffix="mock-cancel"))

        self.assertEqual("cancelled", observation["terminal_status"])
        self.assertEqual(
            "codex_cli_process_cancelled",
            observation["attempts"][0]["error_code"],
        )
        self.assertEqual("not_produced", observation["response"]["availability"])
        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        validate_execution_evidence(canonical)
        self.assertEqual("cancelled", canonical["process"]["transport_status"])
        self.assertTrue(canonical["submission"]["occurred"])
        self.assertFalse(canonical["submission"]["external_provider"])

    def test_startup_observer_precedes_inference_and_cannot_change_scored_outcome(self):
        from AgMark.shared.adapters.execution.orchestration import observe_invocation_startup
        for fail in (False, True):
            transport = FakeCodexTransport()
            runner = self._native_runner(transport)
            seen = []
            def observer(**facts):
                seen.append((facts["observation_id"], len(transport.calls), tuple(facts["argv"])))
                self.assertEqual([], list(facts["cwd"].iterdir()))
                self.assertTrue(facts["external_provider_submission"])
                if fail:
                    raise ValueError("optional startup observer failure")
            with observe_invocation_startup(observer):
                result = runner.execute(_request(_boundary()))
            self.assertEqual("completed", result["terminal_status"])
            self.assertEqual(1, len(seen))
            self.assertEqual(2, seen[0][1])  # Version/help probes precede inference.
            self.assertEqual(seen[0][2], transport.calls[-1]["argv"])
            self.assertFalse(any("otel." in arg for arg in seen[0][2]))

    def test_native_exec_uses_explicit_model_and_existing_session_context(self) -> None:
        transport = FakeCodexTransport()
        runner = self._native_runner(transport)
        boundary = _boundary()
        observation = runner.execute(_request(boundary))

        self.assertEqual("completed", observation["terminal_status"])
        self.assertEqual(
            _sha256(transport.response),
            observation["response"]["sha256"],
        )
        actual = transport.calls[-1]
        self.assertEqual(
            (
                "/opt/codex/bin/codex",
                "exec",
                "--model",
                "gpt-5-codex",
                "--approve-for-me",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--json",
                "-",
            ),
            actual["argv"],
        )
        self.assertEqual(
            b"adapter prompt\n\nadapter input",
            actual["input_bytes"],
        )
        # The selected native user's session home is inherited when present.
        import os
        self.assertEqual(os.environ.get("CODEX_HOME"), actual["env"].get("CODEX_HOME"))
        execution = observation["extensions"]["openai.codex_cli:execution"]
        self.assertTrue(execution["isolation"]["session_home_reused"])
        self.assertEqual(
            "codex_session",
            execution["authentication"]["class"],
        )

        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        validate_execution_evidence(canonical)
        self.assertEqual("live-provider", canonical["target"]["class"])
        self.assertEqual(
            "live-provider-execution",
            canonical["target"]["evidence_class"],
        )
        self.assertEqual(
            {
                "availability": "observed",
                "occurred": True,
                "external_provider": True,
            },
            canonical["submission"],
        )
        self.assertEqual("native", canonical["launch_environment"]["mode"])
        self.assertIsNone(canonical["process"]["stdout"]["sha256"])
        self.assertEqual("excluded", canonical["process"]["stderr"]["availability"])
        self.assertNotIn(
            "openai.codex_cli:process_output",
            observation["extensions"],
        )

    def test_selected_reasoning_is_validated_and_passed_to_native_and_wsl_execution(self):
        for mode in ("native", "wsl"):
            with self.subTest(mode=mode):
                transport = FakeCodexTransport()
                runner = self._native_runner(transport) if mode == "native" else self._wsl_runner(transport)
                boundary = _boundary(launch_mode=mode)
                boundary["controls"].append({"name": "reasoning_effort", "value": "high"})
                observation = runner.execute(_request(boundary))
                self.assertEqual("completed", observation["terminal_status"])
                argv = transport.calls[-1]["argv"]
                self.assertIn('model_reasoning_effort="high"', argv)
                self.assertEqual("-c", argv[argv.index('model_reasoning_effort="high"') - 1])
                catalog_argv = self.catalog_probe.call_args.args[0]
                self.assertIn("app-server", catalog_argv)
                if mode == "wsl":
                    self.assertIn("--distribution", catalog_argv)
                    self.assertNotIn('model_reasoning_effort=', argv[6])

    def test_invalid_or_unavailable_reasoning_is_rejected_before_submission(self):
        for effort in ("unsupported", "", 3):
            with self.subTest(effort=effort):
                transport = FakeCodexTransport()
                boundary = _boundary()
                boundary["controls"].append({"name": "reasoning_effort", "value": effort})
                observation = self._native_runner(transport).execute(_request(boundary))
                self.assertEqual("unsupported", observation["terminal_status"])
                self.assertFalse(any(call["input_bytes"] is not None for call in transport.calls))
        self.catalog_probe.side_effect = RuntimeError("catalog unavailable")
        transport = FakeCodexTransport()
        boundary = _boundary()
        boundary["controls"].append({"name": "reasoning_effort", "value": "high"})
        observation = self._native_runner(transport).execute(_request(boundary))
        self.assertEqual("unsupported", observation["terminal_status"])
        self.assertFalse(any(call["input_bytes"] is not None for call in transport.calls))

    def test_wsl_exec_creates_workdir_inside_wsl_and_reuses_wsl_home(self) -> None:
        transport = FakeCodexTransport()
        runner = self._wsl_runner(transport)
        boundary = _boundary(launch_mode="wsl")
        observation = runner.execute(_request(boundary, suffix="wsl"))

        self.assertEqual("completed", observation["terminal_status"])
        actual = transport.calls[-1]["argv"]
        self.assertEqual(
            (
                r"C:\Windows\System32\wsl.exe",
                "--distribution",
                "Ubuntu",
                "--exec",
                "sh",
                "-lc",
            ),
            actual[:6],
        )
        script = actual[6]
        self.assertIn("mktemp -d /tmp/arcgrav-codex-work-", script)
        self.assertIn('cd "$workdir"', script)
        self.assertNotIn("CODEX_HOME", script)
        self.assertNotIn("auth.json", script)
        self.assertEqual("/usr/bin/codex", actual[-2])
        self.assertEqual("gpt-5-codex", actual[-1])

        all_argv = [call["argv"] for call in transport.calls]
        self.assertFalse(any("wslpath" in argv for argv in all_argv))
        self.assertFalse(any("login" in argv for argv in all_argv))
        self.assertFalse(any("app-server" in argv for argv in all_argv))
        execution = observation["extensions"]["openai.codex_cli:execution"]
        self.assertNotIn("workdir_scope", execution["isolation"])
        self.assertNotIn("codex_session_source", execution["isolation"])

    def test_authentication_failure_is_classified_from_actual_exec(self) -> None:
        transport = FakeCodexTransport(
            response=b"",
            actual_returncode=1,
            actual_stderr=b"Not logged in; authentication required",
        )
        runner = self._native_runner(transport)
        observation = runner.execute(_request(_boundary(), suffix="auth"))
        self.assertEqual("failed", observation["terminal_status"])
        self.assertEqual(
            "codex_cli_authentication_failed",
            observation["attempts"][0]["error_code"],
        )
        self.assertTrue(
            observation["extensions"]["openai.codex_cli:execution"][
                "provider_submitted"
            ]
        )
        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        self.assertEqual(
            "codex_cli_authentication_failed",
            canonical["error"]["code"],
        )
        self.assertEqual(
            "codex_cli_authentication_failed",
            canonical["error"]["classification"],
        )
        self.assertEqual(1, canonical["process"]["exit_status"])

    def test_runtime_version_drift_blocks_before_exec(self) -> None:
        transport = FakeCodexTransport(version="9.9.9")
        runner = self._native_runner(transport)
        observation = runner.execute(_request(_boundary(), suffix="drift"))
        self.assertEqual("unsupported", observation["terminal_status"])
        self.assertEqual(
            "codex_cli_version_unsupported",
            observation["attempts"][0]["error_code"],
        )
        self.assertFalse(
            observation["extensions"]["openai.codex_cli:execution"][
                "provider_submitted"
            ]
        )
        self.assertFalse(
            any(
                call["argv"][1:2] == ("exec",)
                and call["argv"][-1:] == ("-",)
                for call in transport.calls
            )
        )

    def test_timeout_is_terminal_and_preserves_no_fake_response(self) -> None:
        transport = FakeCodexTransport(
            actual_exception=subprocess.TimeoutExpired(
                cmd=("codex", "exec"),
                timeout=120,
            )
        )
        runner = self._native_runner(transport)
        observation = runner.execute(_request(_boundary(), suffix="timeout"))
        self.assertEqual("timed_out", observation["terminal_status"])
        self.assertEqual(
            "codex_cli_process_timed_out",
            observation["attempts"][0]["error_code"],
        )
        self.assertEqual("not_produced", observation["response"]["availability"])
        canonical = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        self.assertEqual("timed_out", observation["terminal_status"])
        self.assertTrue(canonical["submission"]["occurred"])
        self.assertTrue(canonical["submission"]["external_provider"])
        self.assertEqual(
            "codex_cli_process_timed_out",
            canonical["error"]["code"],
        )

    def test_planning_probe_resolves_runtime_surface_and_default_reasoning(self) -> None:
        transport = FakeCodexTransport()
        result = probe_planning_identity(
            load_registration(),
            control_values={
                "launch_mode": "native",
                "codex_binary": "codex",
                "model_id": "gpt-5-codex",
                "request_timeout_ms": 120000,
            },
            transport=transport,
            executable_resolver=lambda value: (
                "/opt/codex/bin/codex" if value == "codex" else None
            ),
            platform_name="posix",
        )
        self.assertEqual("ready", result["status"])
        self.assertFalse(result["provider_submitted"])
        self.assertEqual("gpt-5-codex", result["provider_runtime"]["model"])
        self.assertEqual("medium", result["resolved_controls"]["reasoning_effort"])
        all_argv = [call["argv"] for call in transport.calls]
        self.assertEqual(
            [
                ("/opt/codex/bin/codex", "--version"),
                ("/opt/codex/bin/codex", "exec", "--help"),
            ],
            all_argv,
        )

    def test_wsl_default_planning_uses_login_shell_for_executable_and_probes(self) -> None:
        launcher = r"C:\Windows\System32\wsl.exe"
        transport = FakeCodexTransport()
        result = probe_planning_identity(
            load_registration(),
            control_values={"model_id": "gpt-5-codex"},
            transport=transport,
            executable_resolver=lambda value: launcher if value == launcher else None,
            platform_name="nt",
        )
        self.assertEqual("ready", result["status"])
        self.assertFalse(result["provider_submitted"])
        commands = [call["argv"] for call in transport.calls]
        prefix = (launcher, "--distribution", "Ubuntu", "--exec", "sh", "-lc")
        self.assertEqual(prefix, commands[0][:6])
        self.assertIn('command -v "$1"', commands[0][6])
        self.assertEqual(("arcgrav-codex", "codex"), commands[0][-2:])
        self.assertEqual(
            (*prefix, 'exec "$@"', "arcgrav-codex", "codex", "--version"),
            commands[1],
        )
        self.assertEqual(
            (*prefix, 'exec "$@"', "arcgrav-codex", "codex", "exec", "--help"),
            commands[2],
        )

    def test_mock_planning_identity_uses_registration_data_and_same_probes(self) -> None:
        transport = FakeCodexTransport()
        model_id = "arcgrav.mock-model:completed"
        result = probe_planning_identity(
            _mock_registration(),
            control_values={
                "launch_mode": "native",
                "codex_binary": "codex",
                "model_id": model_id,
                "request_timeout_ms": 120000,
            },
            transport=transport,
            executable_resolver=lambda value: (
                "/opt/mock/bin/codex" if value == "codex" else None
            ),
            platform_name="posix",
        )
        self.assertEqual("ready", result["status"])
        self.assertFalse(result["provider_submitted"])
        self.assertEqual(
            {
                "runtime_id": _MOCK_RUNNER_ID,
                "runtime_version": _VERSION,
                "provider": _MOCK_PROVIDER,
                "access_method": "cli",
                "model": model_id,
            },
            result["provider_runtime"],
        )
        self.assertEqual(
            [
                ("/opt/mock/bin/codex", "--version"),
                ("/opt/mock/bin/codex", "exec", "--help"),
            ],
            [call["argv"] for call in transport.calls],
        )

    def test_runner_orders_target_resolution_and_uses_shared_execution(self) -> None:
        source = (
            _REPOSITORY_ROOT
            / "AgMark/shared/adapters/Codex_CLI/runner.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            source.index("target = resolve_target_composition("),
            source.index("version, preflight_error = self._preflight("),
        )
        self.assertIn("execution = execute_target(", source)
        self.assertIn("return emit_terminal_observation(", source)
        self.assertIn("response_extractor=self._extract_response", source)


if __name__ == "__main__":
    unittest.main()
