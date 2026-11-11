"""Provider-free runtime tests for accepted treatment execution."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.adapters.Mock_Model import load_registration
from AgMark.shared.software_testing.adapters.mock_model_support import resolve_model_identity
from AgMark.shared.adapters.Mock_Model import MockRunner as ProductionMockRunner
from AgMark.shared.runtime.artifacts import (
    FilesystemArtifactStore,
    PublicationDestination,
)
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    PlannedCaseInput,
    TreatmentCaseInput,
    TreatmentExecutionError,
    TreatmentPrompt,
    accept_run_plan,
    admit_accepted_execution,
    execute_planned_treatments,
    plan_run,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_RUNNER_ID = "arcgrav.mock-model.runner"
_RUNNER_VERSION = "1.0.0"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _boundary(*, outcome: str = "completed") -> ExecutionBoundary:
    resolved_runtime, resolved_controls = resolve_model_identity("mock-base::scenario:process_failure" if outcome == "failed" else "mock-base::scenario:completed")
    return ExecutionBoundary.build(
        boundary_id="boundary-treatment-execution-test",
        framework=IdentityRef("arcgrav.framework.treatment-execution-test", "1.0.0"),
        runner=IdentityRef(_RUNNER_ID, _RUNNER_VERSION),
        provider_runtime=resolved_runtime,
        controls=resolved_controls,
        environment={"runtime_family": "provider-free"},
    )


class AcceptedTreatmentExecutionRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.benchmark = IdentityRef(
            "arcgrav.benchmark.treatment-execution-test",
            "1.0.0",
            sha256=_sha256(b"benchmark-treatment-execution-test"),
        )
        self.case_set = IdentityRef(
            "arcgrav.case-set.treatment-execution-test",
            "1.0.0",
            sha256=_sha256(b"case-set-treatment-execution-test"),
        )
        self.treatment_set = IdentityRef(
            "arcgrav.treatment-set.treatment-execution-test",
            "1.0.0",
            sha256=_sha256(b"treatment-set-treatment-execution-test"),
        )

    def _accepted(self, boundary: ExecutionBoundary, *, repetitions: int = 2):
        case_values = {
            "case-a": b"case-a-input",
            "case-b": b"case-b-input",
        }
        cases = tuple(
            PlannedCaseInput(
                case_id=case_id,
                sha256=TreatmentCaseInput(case_id, data).sha256,
                byte_length=len(data),
            )
            for case_id, data in case_values.items()
        )
        plan = plan_run(
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=self.treatment_set,
            cases=cases,
            treatments=("treatment-a", "treatment-b"),
            repetitions=repetitions,
            execution_boundary=boundary,
            golden_required=False,
        )
        return (
            plan,
            accept_run_plan(plan=plan, execution_boundary=boundary),
            tuple(
                TreatmentCaseInput(case_id, data)
                for case_id, data in case_values.items()
            ),
        )

    @staticmethod
    def _store(root: Path) -> FilesystemArtifactStore:
        return FilesystemArtifactStore(
            PublicationDestination.benchmark_owned(
                root / "evidence",
                benchmark_root=root,
            )
        )

    def test_forbidden_observation_never_reaches_disk(self):
        boundary = _boundary()
        _, snapshot, inputs = self._accepted(boundary, repetitions=1)
        sentinel = "private-owner-should-never-be-written"
        class UnsafeRunner(ProductionMockRunner):
            def execute(self, request, **kwargs):
                observation = super().execute(request, **kwargs)
                observation["extensions"]["thirdparty:private"] = {"name": sentinel}
                return observation
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = self._store(root)
            gate = admit_accepted_execution(generation_id="generation-private-admission", snapshot=snapshot,
                benchmark=self.benchmark, case_set=self.case_set, treatment_set=self.treatment_set,
                execution_boundary=boundary, benchmark_root=root, artifact_store=store)
            with patch("AgMark.shared.adapters.Mock_Model.MockRunner", UnsafeRunner):
                with self.assertRaisesRegex(TreatmentExecutionError, "before retention"):
                    execute_planned_treatments(gate=gate, snapshot=snapshot, benchmark=self.benchmark,
                        case_set=self.case_set, treatment_set=self.treatment_set, execution_boundary=boundary,
                        artifact_store=store, repository_root=_REPOSITORY_ROOT, runner_registration=load_registration(),
                        case_inputs=inputs, treatment_prompts=(TreatmentPrompt("treatment-a", b"a"), TreatmentPrompt("treatment-b", b"b")))
            self.assertEqual([], list(store.root.rglob("observation.json")))
            for path in store.root.rglob("*"):
                if path.is_file():
                    self.assertNotIn(sentinel.encode(), path.read_bytes())

    def test_complete_matrix_executes_and_reconciles_in_plan_order(self) -> None:
        boundary = _boundary()
        plan, snapshot, case_inputs = self._accepted(boundary)
        prompts = (
            TreatmentPrompt("treatment-a", b"prompt-a"),
            TreatmentPrompt("treatment-b", b"prompt-b"),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = self._store(root)
            gate = admit_accepted_execution(
                generation_id="generation-treatment-execution",
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=store,
            )
            result = execute_planned_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                artifact_store=store,
                repository_root=_REPOSITORY_ROOT,
                runner_registration=load_registration(),
                case_inputs=case_inputs,
                treatment_prompts=prompts,
            )

            expected_ids = tuple(item.observation_id for item in plan.observations)
            self.assertEqual(expected_ids, result.observation_ids)
            self.assertEqual(8, len(result.observations()))
            self.assertEqual(8, len(result.retained_observation_artifacts))
            runner_record = result.retained_runner_registration_artifact
            self.assertEqual("runner_registration", runner_record.role)
            self.assertEqual(result.runner_registration_sha256, runner_record.sha256)
            self.assertIsNotNone(runner_record.schema)
            self.assertEqual(
                "arcgrav.shared.schema.registration",
                runner_record.schema.schema_id,
            )
            self.assertEqual("1.0.0", runner_record.schema.schema_version)
            self.assertIsNotNone(runner_record.contract)
            self.assertEqual(
                "arcgrav.shared.runner-invocation",
                runner_record.contract.contract_id,
            )
            self.assertEqual("2.0.0", runner_record.contract.contract_version)
            self.assertEqual(
                load_registration(),
                json.loads(store.read_verified(runner_record).decode("utf-8")),
            )
            for record in result.retained_observation_artifacts:
                self.assertEqual("treatment_observation", record.role)
                self.assertIsNotNone(record.schema)
                self.assertEqual(
                    "arcgrav.shared.schema.treatment-observation",
                    record.schema.schema_id,
                )
                self.assertEqual("1.0.0", record.schema.schema_version)
                self.assertIsNotNone(record.contract)
                self.assertEqual(
                    "arcgrav.shared.runner-invocation",
                    record.contract.contract_id,
                )
                self.assertEqual("2.0.0", record.contract.contract_version)
            for slot, observation in zip(
                plan.observations,
                result.observations(),
                strict=True,
            ):
                self.assertEqual(slot.request_id, observation["request_id"])
                self.assertEqual(slot.observation_id, observation["observation_id"])
                self.assertEqual(slot.case_id, observation["case_id"])
                self.assertEqual(slot.treatment_id, observation["treatment_id"])
                self.assertEqual(slot.repetition, observation["repetition"])
                self.assertEqual("completed", observation["terminal_status"])
                self.assertEqual(
                    {"id": _RUNNER_ID, "version": _RUNNER_VERSION},
                    observation["runner"],
                )
                self.assertEqual("retained", observation["response"]["availability"])

    def test_consecutive_observations_use_fresh_isolated_request_state(self) -> None:
        boundary = _boundary()
        plan, snapshot, case_inputs = self._accepted(boundary, repetitions=2)
        prompts = (
            TreatmentPrompt("treatment-a", b"prompt-a"),
            TreatmentPrompt("treatment-b", b"prompt-b"),
        )

        class IsolationProbeRunner:
            next_instance = 0
            executed_instances: list[int] = []
            received_requests: list[dict[str, object]] = []
            received_request_objects: list[dict[str, object]] = []

            def __init__(self, *, registration=None) -> None:
                self._inner = ProductionMockRunner(registration=registration or load_registration())
                self._instance = type(self).next_instance
                type(self).next_instance += 1
                self._executed = False

            def describe(self):
                return self._inner.describe()

            def execute(self, request):
                if self._executed:
                    raise AssertionError("runner instance reused across observations")
                self._executed = True
                type(self).executed_instances.append(self._instance)
                type(self).received_requests.append(copy.deepcopy(request))
                type(self).received_request_objects.append(request)

                observation = self._inner.execute(request)

                # Deliberately corrupt this invocation's mutable request after use.
                # A later observation must be built independently and cannot inherit it.
                request["conversation_policy"]["new_conversation"] = False
                request["conversation_policy"]["reuse_prior_observation_context"] = True
                request["prompt"]["content"] = b"mutated-after-execution"
                request["input"]["content"] = b"mutated-after-execution"
                request["leak_marker"] = self._instance
                return observation

            def close(self) -> None:
                self._inner.close()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = self._store(root)
            gate = admit_accepted_execution(
                generation_id="generation-treatment-isolation",
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=store,
            )
            with patch(
                "AgMark.shared.adapters.Mock_Model.MockRunner",
                IsolationProbeRunner,
            ):
                result = execute_planned_treatments(
                    gate=gate,
                    snapshot=snapshot,
                    benchmark=self.benchmark,
                    case_set=self.case_set,
                    treatment_set=self.treatment_set,
                    execution_boundary=boundary,
                    artifact_store=store,
                    repository_root=_REPOSITORY_ROOT,
                    runner_registration=load_registration(),
                    case_inputs=case_inputs,
                    treatment_prompts=prompts,
                )

        self.assertEqual(len(plan.observations), len(IsolationProbeRunner.executed_instances))
        self.assertEqual(
            len(plan.observations),
            len(set(IsolationProbeRunner.executed_instances)),
        )
        self.assertEqual(
            len(plan.observations),
            len({id(request) for request in IsolationProbeRunner.received_request_objects}),
        )
        self.assertEqual(
            tuple(item.observation_id for item in plan.observations),
            result.observation_ids,
        )

        expected_inputs = {
            "case-a": b"case-a-input",
            "case-b": b"case-b-input",
        }
        expected_prompts = {
            "treatment-a": b"prompt-a",
            "treatment-b": b"prompt-b",
        }
        for slot, request in zip(
            plan.observations,
            IsolationProbeRunner.received_requests,
            strict=True,
        ):
            self.assertEqual(
                {
                    "new_conversation": True,
                    "reuse_prior_observation_context": False,
                },
                request["conversation_policy"],
            )
            self.assertNotIn("leak_marker", request)
            self.assertEqual(slot.request_id, request["request_id"])
            self.assertEqual(slot.observation_id, request["observation_id"])
            self.assertEqual(expected_inputs[slot.case_id], request["input"]["content"])
            self.assertEqual(
                expected_prompts[slot.treatment_id],
                request["prompt"]["content"],
            )

    def test_explicit_failed_terminal_observations_are_retained_not_coerced(self) -> None:
        boundary = _boundary(outcome="failed")
        plan, snapshot, case_inputs = self._accepted(boundary, repetitions=1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = self._store(root)
            gate = admit_accepted_execution(
                generation_id="generation-treatment-execution",
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=store,
            )
            result = execute_planned_treatments(
                gate=gate,
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                artifact_store=store,
                repository_root=_REPOSITORY_ROOT,
                runner_registration=load_registration(),
                case_inputs=case_inputs,
                treatment_prompts=(
                    TreatmentPrompt("treatment-a", b"prompt-a"),
                    TreatmentPrompt("treatment-b", b"prompt-b"),
                ),
            )

            self.assertEqual(
                tuple(item.observation_id for item in plan.observations),
                result.observation_ids,
            )
            for observation in result.observations():
                self.assertEqual("failed", observation["terminal_status"])
                self.assertEqual("not_produced", observation["response"]["availability"])
                self.assertEqual("failed", observation["attempts"][0]["status"])

    def test_registered_runner_transient_credentials_are_invocation_only(self) -> None:
        boundary = _boundary()
        _, snapshot, case_inputs = self._accepted(boundary, repetitions=1)
        registration = copy.deepcopy(load_registration())
        registration["extensions"]["arcgrav.adapters:secret_handling"] = {
            "credentials_required": True,
            "transient_secrets_supported": True,
            "supported_sources": ["ephemeral_prompt_material"],
            "retained_secret_values": False,
            "transient_inputs": [
                {
                    "name": "credential_locator",
                    "kind": "text",
                    "credential_sources": ["ephemeral_prompt_material"],
                }
            ],
        }
        registration["extensions"]["arcgrav.adapters:supported_controls"].extend(
            [
                {
                    "name": "credential_source",
                    "kind": "secret",
                    "required": True,
                    "values": ["ephemeral_prompt_material"],
                    "comparison_relevant": False,
                },
                {
                    "name": "credential_locator",
                    "kind": "text",
                    "required": False,
                    "comparison_relevant": False,
                },
            ]
        )
        registration["contracts"].append(
            {"id": "arcgrav.shared.transient-invocation", "version": "1.0.0"}
        )
        secret = "runtime-transient-secret-value"
        credential_locator = "/private/runtime-credential-profile"

        class TransientProbeRunner:
            received: list[dict[str, str]] = []

            def __init__(self, *, registration=None) -> None:
                self._inner = ProductionMockRunner(registration=registration or load_registration())

            def describe(self):
                description = self._inner.describe()
                description["registration"] = copy.deepcopy(registration)
                return description

            def execute(self, request):
                type(self).received.append(copy.deepcopy(request["transient_invocation"]))
                return self._inner.execute(request)

            def close(self) -> None:
                self._inner.close()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = self._store(root)
            gate = admit_accepted_execution(
                generation_id="generation-treatment-transient",
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=store,
            )
            with patch(
                "AgMark.shared.adapters.Mock_Model.MockRunner",
                TransientProbeRunner,
            ):
                with self.assertRaisesRegex(
                    TreatmentExecutionError,
                    "transient credential source is required",
                ):
                    execute_planned_treatments(
                        gate=gate,
                        snapshot=snapshot,
                        benchmark=self.benchmark,
                        case_set=self.case_set,
                        treatment_set=self.treatment_set,
                        execution_boundary=boundary,
                        artifact_store=store,
                        repository_root=_REPOSITORY_ROOT,
                        runner_registration=registration,
                        case_inputs=case_inputs,
                        treatment_prompts=(
                            TreatmentPrompt("treatment-a", b"prompt-a"),
                            TreatmentPrompt("treatment-b", b"prompt-b"),
                        ),
                    )

                result = execute_planned_treatments(
                    gate=gate,
                    snapshot=snapshot,
                    benchmark=self.benchmark,
                    case_set=self.case_set,
                    treatment_set=self.treatment_set,
                    execution_boundary=boundary,
                    artifact_store=store,
                    repository_root=_REPOSITORY_ROOT,
                    runner_registration=registration,
                    case_inputs=case_inputs,
                    treatment_prompts=(
                        TreatmentPrompt("treatment-a", b"prompt-a"),
                        TreatmentPrompt("treatment-b", b"prompt-b"),
                    ),
                    runner_transient_values={
                        "credential_source": "ephemeral_prompt_material",
                        "credential_material": secret,
                        "credential_locator": credential_locator,
                    },
                )

            self.assertTrue(TransientProbeRunner.received)
            self.assertTrue(
                all(
                    value
                    == {
                        "credential_source": "ephemeral_prompt_material",
                        "credential_material": secret,
                        "credential_locator": credential_locator,
                    }
                    for value in TransientProbeRunner.received
                )
            )
            for observation in result.observations():
                rendered = json.dumps(observation, sort_keys=True)
                self.assertNotIn(secret, rendered)
                self.assertNotIn(credential_locator, rendered)
            for record in result.retained_observation_artifacts:
                retained = store.read_verified(record)
                self.assertNotIn(secret.encode("utf-8"), retained)
                self.assertNotIn(credential_locator.encode("utf-8"), retained)
            retained_registration = store.read_verified(
                result.retained_runner_registration_artifact
            )
            self.assertNotIn(secret.encode("utf-8"), retained_registration)
            self.assertNotIn(credential_locator.encode("utf-8"), retained_registration)
            self.assertNotIn(secret, repr(result))
            self.assertNotIn(credential_locator, repr(result))

    def test_registration_or_case_input_substitution_fails_before_execution(self) -> None:
        boundary = _boundary()
        _, snapshot, case_inputs = self._accepted(boundary)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = self._store(root)
            gate = admit_accepted_execution(
                generation_id="generation-treatment-execution",
                snapshot=snapshot,
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=store,
            )
            registration = copy.deepcopy(load_registration())
            registration["registration_id"] = "arcgrav.runner.substituted"
            with self.assertRaises(TreatmentExecutionError):
                execute_planned_treatments(
                    gate=gate,
                    snapshot=snapshot,
                    benchmark=self.benchmark,
                    case_set=self.case_set,
                    treatment_set=self.treatment_set,
                    execution_boundary=boundary,
                    artifact_store=store,
                    repository_root=_REPOSITORY_ROOT,
                    runner_registration=registration,
                    case_inputs=case_inputs,
                    treatment_prompts=(
                        TreatmentPrompt("treatment-a", b"prompt-a"),
                        TreatmentPrompt("treatment-b", b"prompt-b"),
                    ),
                )

            wrong_inputs = (
                TreatmentCaseInput("case-a", b"wrong"),
                case_inputs[1],
            )
            with self.assertRaises(TreatmentExecutionError):
                execute_planned_treatments(
                    gate=gate,
                    snapshot=snapshot,
                    benchmark=self.benchmark,
                    case_set=self.case_set,
                    treatment_set=self.treatment_set,
                    execution_boundary=boundary,
                    artifact_store=store,
                    repository_root=_REPOSITORY_ROOT,
                    runner_registration=load_registration(),
                    case_inputs=wrong_inputs,
                    treatment_prompts=(
                        TreatmentPrompt("treatment-a", b"prompt-a"),
                        TreatmentPrompt("treatment-b", b"prompt-b"),
                    ),
                )

            evidence_root = root / "evidence"
            self.assertFalse(
                any(path.name == "observation.json" for path in evidence_root.rglob("*"))
            )


if __name__ == "__main__":
    unittest.main()
