"""Provider-free tests for canonical shared execution-evidence emission."""

from __future__ import annotations

import ast
import copy
from dataclasses import replace
import hashlib
import inspect
import unittest

import AgMark.shared.adapters.execution.emission as emission_module
import AgMark.shared.adapters.execution.orchestration as orchestration_module

from AgMark.shared.adapters._contract import validate_runner_request
from AgMark.shared.adapters.execution import (
    CanonicalObservationError,
    EXECUTION_EVIDENCE_EXTENSION_KEY,
    EXECUTION_CATEGORY_AVAILABILITY,
    PROCESS_CHANNEL_AVAILABILITY,
    TERMINAL_RUNNER_STATUSES,
    ExecutionFailureKind,
    ExecutionIsolation,
    InvocationCapture,
    TargetCompositionDescriptor,
    TerminalExecutionResult,
    emit_terminal_observation,
    validate_execution_evidence,
)


_RUNNER_ID = "arcgrav.runner.shared-test"
_RUNNER_VERSION = "1.0.0"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _request(*, model_id: str = "model-a"):
    prompt = b"prompt"
    case_input = b"input"
    fingerprint = _sha256(b"shared-execution-boundary")
    boundary = {
        "fingerprint": fingerprint,
        "runner": {"id": _RUNNER_ID, "version": _RUNNER_VERSION},
        "provider_runtime": {
            "runtime_id": "runtime-a",
            "runtime_version": "1.2.3",
            "provider": "test-provider",
            "access_method": "cli",
            "model": model_id,
        },
        "controls": [
            {"name": "model_id", "value": model_id},
        ],
    }
    return validate_runner_request(
        {
            "accepted_generation_id": "generation-a",
            "request_id": "request-a",
            "observation_id": "observation-a",
            "benchmark_id": "benchmark-neutral-test",
            "case_id": "case-a",
            "treatment_id": "treatment-a",
            "repetition": 1,
            "execution_boundary_fingerprint": fingerprint,
            "execution_boundary": boundary,
            "conversation_policy": {
                "new_conversation": True,
                "reuse_prior_observation_context": False,
            },
            "prompt": {"content": prompt, "sha256": _sha256(prompt)},
            "input": {"content": case_input, "sha256": _sha256(case_input)},
            "request_identity": {
                "prompt_sha256": _sha256(prompt),
                "input_sha256": _sha256(case_input),
                "request_sha256": _sha256(b"request-a"),
            },
        }
    )


def _target(*, target_class: str) -> TargetCompositionDescriptor:
    is_mock = target_class == "mock-model"
    return TargetCompositionDescriptor.create(
        target_class=target_class,
        evidence_class=(
            "provider-free-conformance" if is_mock else "live-provider-execution"
        ),
        runtime_id="mock.runtime" if is_mock else "live.runtime",
        runtime_version="1.2.3",
        access_method="cli",
        external_provider_submission=not is_mock,
        launch_mode="native",
        launch_environment_selector={},
        executable="mock-cli" if is_mock else "live-cli",
        authentication_class="none" if is_mock else "session",
        compatibility_profile="test-cli" if is_mock else None,
        production_runner_entry_point=(
            "AgMark.shared.adapters.TestRunner:SharedRunner"
        ),
        runner_implementation_artifact_ids=(
            "AgMark/shared/adapters/execution/orchestration.py",
            "AgMark/shared/adapters/execution/emission.py",
        ),
    )


def _result(
    *,
    terminal_status: str = "completed",
    failure_kind: ExecutionFailureKind | None = None,
    invocation_occurred: bool = True,
    capture: InvocationCapture | None = None,
    response_bytes: bytes | None = b"response",
    isolation: ExecutionIsolation | None = None,
) -> TerminalExecutionResult:
    if capture is None:
        capture = InvocationCapture(
            succeeded=terminal_status == "completed",
            exit_status=0 if terminal_status == "completed" else 7,
            transport_status="opaque.transport:state",
            stdout=b"response",
            stderr=b"diagnostic",
        )
    if isolation is None and invocation_occurred:
        isolation = ExecutionIsolation(
            fresh_process=True,
            fresh_workdir=True,
            prior_observation_context_reused=False,
            session_home_reused=True,
        )
    return TerminalExecutionResult(
        terminal_status=terminal_status,
        failure_kind=failure_kind,
        started_at="2026-09-27T12:00:00Z",
        completed_at="2026-09-27T12:00:01Z",
        duration_ms=1000.0,
        invocation_occurred=invocation_occurred,
        capture=capture,
        response_bytes=response_bytes,
        isolation=isolation,
    )


def _pointer_set(value: object, pointer: str = "") -> set[str]:
    result = {pointer or "/"}
    if isinstance(value, dict):
        for key, item in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            result.update(_pointer_set(item, f"{pointer}/{escaped}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.update(_pointer_set(item, f"{pointer}/{index}"))
    return result


class CanonicalExecutionEmissionTests(unittest.TestCase):
    def _emit(
        self,
        *,
        target_class: str = "live-provider",
        target: TargetCompositionDescriptor | None = None,
        model_id: str = "model-a",
        execution: TerminalExecutionResult | None = None,
        **kwargs,
    ):
        return emit_terminal_observation(
            _request(model_id=model_id),
            target=target or _target(target_class=target_class),
            execution=execution or _result(),
            runner_id=_RUNNER_ID,
            runner_version=_RUNNER_VERSION,
            framed_request=b"prompt\n\ninput",
            request_framing_mode="test-cli",
            **kwargs,
        )

    def test_arbitrary_adapter_contract_requires_common_execution_evidence(self):
        observation = self._emit()
        observation["runner"] = {"id": "vendor.third-adapter", "version": "7.0.0"}
        observation["extensions"]["vendor.third-adapter:response_base64"] = observation["extensions"].pop(_RUNNER_ID + ":response_base64")
        emission_module.validate_retained_parity_observation(observation)
        for mutate in (
            lambda value: value["extensions"].pop(EXECUTION_EVIDENCE_EXTENSION_KEY),
            lambda value: value.pop("extensions"),
            lambda value: value.pop("contract"),
            lambda value: value["contract"].update(id="unrelated.contract"),
            lambda value: value["contract"].update(version="99.0.0"),
        ):
            damaged = copy.deepcopy(observation)
            mutate(damaged)
            with self.subTest(observation=damaged.get("contract")), self.assertRaises(CanonicalObservationError):
                emission_module.validate_retained_parity_observation(damaged)

    def test_arbitrary_synthetic_adapter_registration_cannot_claim_live_target(self):
        from types import SimpleNamespace
        from AgMark.shared.reporting.revalidation import (
            _synthetic_conformance_from_evidence, ReportingInputRevalidationError)
        records = {"registration": SimpleNamespace(role="runner_registration", artifact_id="registration"),
                   "observation": SimpleNamespace(role="treatment_observation", artifact_id="observation")}
        documents = {"boundary": {"runner": {"id": "vendor.third-adapter", "version": "7.0.0"}},
            "registration": {"registration_id": "vendor.third-adapter", "registration_version": "7.0.0",
                "extensions": {"arcgrav.adapters:target_composition": {"target_class": "mock-model"},
                    "arcgrav.adapters:evidence_class": "provider-free-mock-model-execution"}},
            "observation": self._emit(target_class="mock-model")}
        documents["observation"]["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]["target"]["evidence_class"] = "provider-free-mock-model-execution"
        self.assertTrue(_synthetic_conformance_from_evidence(execution_boundary_artifact_id="boundary", records=records, documents=documents))
        documents["observation"] = self._emit(target_class="live-provider")
        with self.assertRaises(ReportingInputRevalidationError):
            _synthetic_conformance_from_evidence(execution_boundary_artifact_id="boundary", records=records, documents=documents)

    def test_completed_live_and_mock_share_canonical_pointer_shape(self) -> None:
        live = self._emit(
            target_class="live-provider",
            authentication_source="selected-user-session",
        )
        mock = self._emit(target_class="mock-model")

        self.assertEqual(_pointer_set(live), _pointer_set(mock))
        live_evidence = live["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        mock_evidence = mock["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        self.assertEqual(_pointer_set(live_evidence), _pointer_set(mock_evidence))

        self.assertEqual("live-provider", live_evidence["target"]["class"])
        self.assertEqual("mock-model", mock_evidence["target"]["class"])
        self.assertTrue(live_evidence["submission"]["external_provider"])
        self.assertFalse(mock_evidence["submission"]["external_provider"])

        stdout = live_evidence["process"]["stdout"]
        stderr = live_evidence["process"]["stderr"]
        for channel in (stdout, stderr):
            self.assertEqual({"availability": "excluded", "sha256": None,
                              "byte_length": None, "reference": None}, channel)
        self.assertNotIn("arcgrav.runner:process_stdout_base64", live["extensions"])
        self.assertNotIn("arcgrav.runner:process_stderr_base64", live["extensions"])

        self.assertEqual(
            {
                "availability": "not_applicable",
                "code": None,
                "classification": None,
                "message": None,
            },
            live_evidence["error"],
        )
        self.assertEqual("retained", live["response"]["availability"])
        self.assertEqual(1000.0, live["attempts"][0]["duration_ms"])

    def test_preinvocation_failure_retains_nullable_common_shape(self) -> None:
        execution = _result(
            terminal_status="failed",
            failure_kind=ExecutionFailureKind.ISOLATION_FAILED,
            invocation_occurred=False,
            capture=InvocationCapture(
                succeeded=False,
                exit_status=None,
                transport_status=None,
                stdout=b"",
                stderr=b"",
            ),
            response_bytes=None,
            isolation=None,
        )
        observation = self._emit(execution=execution)
        evidence = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]

        self.assertEqual(
            {
                "availability": "observed",
                "occurred": False,
                "external_provider": False,
            },
            evidence["submission"],
        )
        self.assertEqual("unavailable", evidence["isolation"]["availability"])
        self.assertIsNone(evidence["isolation"]["fresh_process"])
        self.assertEqual("not_applicable", evidence["process"]["availability"])
        for name in ("stdout", "stderr"):
            channel = evidence["process"][name]
            self.assertEqual("not_produced", channel["availability"])
            self.assertIsNone(channel["sha256"])
            self.assertIsNone(channel["byte_length"])
            self.assertIsNone(channel["reference"])
        self.assertEqual("not_produced", observation["response"]["availability"])
        self.assertEqual("isolation_failed", evidence["error"]["code"])

    def test_post_composition_unsupported_preflight_uses_shared_evidence(self) -> None:
        execution = _result(
            terminal_status="unsupported",
            failure_kind=ExecutionFailureKind.PREFLIGHT_UNSUPPORTED,
            invocation_occurred=False,
            capture=InvocationCapture(
                succeeded=False,
                exit_status=None,
                transport_status=None,
                stdout=b"",
                stderr=b"",
            ),
            response_bytes=None,
            isolation=None,
        )
        observations = (
            self._emit(
                target_class="live-provider",
                execution=execution,
                authentication_source="selected-user-session",
                error_code="codex_cli_version_unavailable",
            ),
            self._emit(
                target_class="mock-model",
                execution=execution,
                error_code="codex_cli_version_unavailable",
            ),
        )
        self.assertEqual(_pointer_set(observations[0]), _pointer_set(observations[1]))
        for observation in observations:
            evidence = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
            validate_execution_evidence(evidence)
            self.assertEqual("unsupported", observation["terminal_status"])
            self.assertEqual(
                ["codex_cli_version_unavailable"], observation["diagnostics"]
            )
            self.assertEqual("not_produced", observation["response"]["availability"])
            self.assertEqual(
                {
                    "availability": "observed",
                    "occurred": False,
                    "external_provider": False,
                },
                evidence["submission"],
            )
            self.assertEqual("unavailable", evidence["isolation"]["availability"])
            self.assertEqual("not_applicable", evidence["process"]["availability"])
            self.assertIsNone(evidence["process"]["exit_status"])
            self.assertIsNone(evidence["process"]["transport_status"])
            for channel_name in ("stdout", "stderr"):
                self.assertEqual(
                    {
                        "availability": "not_produced",
                        "sha256": None,
                        "byte_length": None,
                        "reference": None,
                    },
                    evidence["process"][channel_name],
                )
            self.assertEqual(
                "codex_cli_version_unavailable", evidence["error"]["code"]
            )
            self.assertEqual("observed", evidence["request_framing"]["availability"])
            self.assertNotIn(
                "arcgrav.runner:process_stdout_base64", observation["extensions"]
            )
            self.assertNotIn(
                "arcgrav.runner:process_stderr_base64", observation["extensions"]
            )

    def test_response_unavailable_is_not_successful_empty_response(self) -> None:
        execution = _result(
            terminal_status="failed",
            failure_kind=ExecutionFailureKind.RESPONSE_UNAVAILABLE,
            capture=InvocationCapture(
                succeeded=True,
                exit_status=0,
                transport_status="completed-without-response",
                stdout=b"progress-only",
                stderr=b"",
            ),
            response_bytes=None,
        )
        observation = self._emit(execution=execution)
        evidence = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]

        self.assertEqual("failed", observation["terminal_status"])
        self.assertEqual("unavailable", observation["response"]["availability"])
        self.assertEqual("excluded", evidence["process"]["stdout"]["availability"])
        self.assertIsNone(evidence["process"]["stdout"]["sha256"])
        self.assertEqual("response_unavailable", evidence["error"]["classification"])

    def test_uncaptured_interrupt_never_retains_invented_empty_channels(self) -> None:
        capture = InvocationCapture(
            succeeded=False,
            exit_status=None,
            transport_status="cancelled",
            stdout=b"",
            stderr=b"",
        )
        interrupted = replace(
            _result(
                terminal_status="cancelled",
                failure_kind=ExecutionFailureKind.CANCELLED,
                capture=capture,
                response_bytes=None,
            ),
            process_channels_observed=False,
        )
        observation = self._emit(
            execution=interrupted,
            error_code="runner_cancelled",
        )
        evidence = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        validate_execution_evidence(evidence)
        self.assertEqual("cancelled", observation["terminal_status"])
        self.assertEqual({"availability": "not_produced"}, observation["response"])
        self.assertTrue(evidence["submission"]["occurred"])
        self.assertEqual("observed", evidence["isolation"]["availability"])
        self.assertEqual("observed", evidence["process"]["availability"])
        for channel in ("stdout", "stderr"):
            self.assertEqual(
                {"availability": "unavailable", "sha256": None,
                 "byte_length": None, "reference": None},
                evidence["process"][channel],
            )
            self.assertNotIn(
                f"arcgrav.runner:process_{channel}_base64",
                observation["extensions"],
            )
            self.assertNotIn(
                f"{channel}_bytes",
                {item["name"] for item in observation["telemetry"]},
            )

        # Observed partial output is also excluded from durable evidence.
        observed = replace(interrupted, process_channels_observed=True,
                           capture=replace(capture, stdout=b"observed-partial"))
        result = self._emit(execution=observed, error_code="runner_cancelled")
        channel = result["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]["process"]["stdout"]
        self.assertEqual("excluded", channel["availability"])
        self.assertIsNone(channel["sha256"])
        self.assertIsNone(channel["byte_length"])
        self.assertIsNone(channel["reference"])

    def test_free_form_transport_and_error_identifiers_do_not_select_status(self) -> None:
        execution = _result(
            terminal_status="failed",
            failure_kind=ExecutionFailureKind.PROCESS_FAILED,
            capture=InvocationCapture(
                succeeded=False,
                exit_status=23,
                transport_status="vendor-x:opaque-state/17",
                stdout=b"",
                stderr=b"opaque",
            ),
            response_bytes=None,
        )
        observation = self._emit(
            execution=execution,
            error_code="vendor-x:E-9000",
            error_classification="vendor-defined classifier",
            error_message="redacted vendor diagnostic",
        )
        evidence = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]

        self.assertEqual("failed", observation["terminal_status"])
        self.assertEqual(
            "other",
            evidence["process"]["transport_status"],
        )
        self.assertEqual("process_failed", evidence["error"]["code"])
        self.assertEqual(
            "process_failed",
            evidence["error"]["classification"],
        )

    def test_identity_fields_do_not_select_emission_behavior(self) -> None:
        base = replace(
            _target(target_class="live-provider"),
            external_provider_submission=False,
            compatibility_profile="profile-a",
        )
        variant = replace(
            base,
            target_class="mock-model",
            evidence_class="provider-free-conformance",
            compatibility_profile="profile-b",
        )

        first = self._emit(
            target=base,
            model_id="scenario-a",
            usage_provider_reported=False,
            usage_provenance="runner-observed",
        )
        second = self._emit(
            target=variant,
            model_id="scenario-b",
            usage_provider_reported=False,
            usage_provenance="runner-observed",
        )

        first_evidence = first["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        second_evidence = second["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        for category in (
            "submission",
            "authentication",
            "isolation",
            "request_framing",
            "process",
            "usage",
            "error",
        ):
            self.assertEqual(first_evidence[category], second_evidence[category])
        self.assertEqual(first["terminal_status"], second["terminal_status"])
        self.assertEqual(first["response"], second["response"])
        self.assertEqual(first["attempts"], second["attempts"])
        self.assertEqual(first["telemetry"], second["telemetry"])

        self.assertNotEqual(
            first_evidence["target"]["class"],
            second_evidence["target"]["class"],
        )
        self.assertNotEqual(
            first_evidence["target"]["evidence_class"],
            second_evidence["target"]["evidence_class"],
        )
        self.assertNotEqual(
            first_evidence["runtime"]["model_id"],
            second_evidence["runtime"]["model_id"],
        )

    def test_external_provider_submission_fact_controls_provider_semantics(self) -> None:
        local_live = replace(
            _target(target_class="live-provider"),
            external_provider_submission=False,
        )
        observation = self._emit(target=local_live)
        evidence = observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        self.assertFalse(evidence["submission"]["external_provider"])

        with self.assertRaises(CanonicalObservationError):
            self._emit(
                target=local_live,
                usage_provider_reported=True,
                usage_provenance="provider-report",
            )

    def test_post_composition_identity_fields_do_not_drive_control_flow(self) -> None:
        forbidden = {"target_class", "evidence_class", "compatibility_profile"}
        violations: list[str] = []
        for module in (emission_module, orchestration_module):
            tree = ast.parse(inspect.getsource(module))
            for node in ast.walk(tree):
                test = None
                if isinstance(node, (ast.If, ast.IfExp, ast.While)):
                    test = node.test
                elif isinstance(node, ast.Match):
                    test = node.subject
                if test is None:
                    continue
                attributes = {
                    child.attr
                    for child in ast.walk(test)
                    if isinstance(child, ast.Attribute)
                }
                overlap = sorted(forbidden.intersection(attributes))
                if overlap:
                    violations.append(
                        f"{module.__name__}:{getattr(node, 'lineno', '?')}:"
                        + ",".join(overlap)
                    )
        self.assertEqual([], violations)

    def test_nested_schema_validation_fails_closed(self) -> None:
        observation = self._emit()
        evidence = copy.deepcopy(
            observation["extensions"][EXECUTION_EVIDENCE_EXTENSION_KEY]
        )
        evidence["process"]["stdout"]["availability"] = "invented-state"
        with self.assertRaises(CanonicalObservationError):
            validate_execution_evidence(evidence)

        del evidence["error"]["message"]
        with self.assertRaises(CanonicalObservationError):
            validate_execution_evidence(evidence)

    def test_shared_vocabularies_are_explicit_and_closed(self) -> None:
        self.assertEqual(
            {"observed", "unavailable", "not_applicable"},
            EXECUTION_CATEGORY_AVAILABILITY,
        )
        self.assertEqual(
            {"excluded", "unavailable", "not_produced", "not_applicable"},
            PROCESS_CHANNEL_AVAILABILITY,
        )
        self.assertEqual(
            {"completed", "failed", "timed_out", "cancelled", "unsupported"},
            TERMINAL_RUNNER_STATUSES,
        )


if __name__ == "__main__":
    unittest.main()
