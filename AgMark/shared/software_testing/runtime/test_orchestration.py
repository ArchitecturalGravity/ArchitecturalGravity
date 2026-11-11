"""Provider-free runtime tests for canonical orchestration planning authority."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import unittest
from unittest import mock

from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import (
    AcceptedSnapshotIntegrityError,
    DuplicatePlanIdentityError,
    IncompletePlanError,
    PlannedCaseInput,
    PlanningError,
    RunPlan,
    accept_run_plan,
    plan_run,
)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _source(identity: str, payload: bytes) -> IdentityRef:
    return IdentityRef(identity, "1.0.0", sha256=_sha256(payload))


def _boundary(*, runner_bytes: bytes = b"runner-v1") -> ExecutionBoundary:
    return ExecutionBoundary.build(
        boundary_id="boundary-orchestration-test",
        framework=_source("arcgrav.framework.orchestration-test", b"framework-v1"),
        runner=_source("arcgrav.runner.orchestration-test", runner_bytes),
        provider_runtime=ProviderRuntimeIdentity(
            runtime_id="arcgrav.runtime.provider-free",
            runtime_version="1.0.0",
            provider=None,
            access_method="in_process",
            model=None,
        ),
        controls={
            "network_access": "disabled",
            "memory_policy": "disabled",
        },
        environment={"runtime_family": "provider-free"},
    )


class OrchestrationPlanningRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.benchmark = _source("arcgrav.benchmark.test", b"benchmark-v1")
        self.case_set = _source("arcgrav.case-set.test", b"case-set-v1")
        self.treatment_set = _source("arcgrav.treatment-set.test", b"treatment-set-v1")
        self.boundary = _boundary()
        self.cases = (
            PlannedCaseInput(
                case_id="case-a",
                sha256=_sha256(b"case-a-input"),
                reference="cases/case-a.txt",
                byte_length=len(b"case-a-input"),
            ),
            PlannedCaseInput(
                case_id="case-b",
                sha256=_sha256(b"case-b-input"),
                reference="cases/case-b.txt",
                byte_length=len(b"case-b-input"),
            ),
        )
        self.treatments = ("treatment-a", "treatment-b")

    def _plan(self) -> RunPlan:
        return plan_run(
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=self.treatment_set,
            cases=self.cases,
            treatments=self.treatments,
            repetitions=2,
            execution_boundary=self.boundary,
            golden_required=True,
        )

    def test_complete_matrix_and_stable_identities_precede_acceptance(self) -> None:
        first = self._plan()
        second = self._plan()

        self.assertEqual(first.run_plan_id, second.run_plan_id)
        self.assertEqual(first.plan_sha256, second.plan_sha256)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(8, len(first.observations))
        self.assertEqual([1] * 4 + [2] * 4, [item.repetition for item in first.observations])
        self.assertEqual(8, len({item.request_id for item in first.observations}))
        self.assertEqual(8, len({item.observation_id for item in first.observations}))
        self.assertEqual(
            {
                (case_id, treatment_id, repetition)
                for case_id in ("case-a", "case-b")
                for treatment_id in ("treatment-a", "treatment-b")
                for repetition in (1, 2)
            },
            {
                (item.case_id, item.treatment_id, item.repetition)
                for item in first.observations
            },
        )
        self.assertTrue(
            all(
                item.execution_boundary_fingerprint == self.boundary.fingerprint
                for item in first.observations
            )
        )

    def test_per_iteration_randomization_is_frozen_in_the_accepted_plan(self) -> None:
        arguments = dict(
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=self.treatment_set,
            cases=self.cases,
            treatments=self.treatments,
            repetitions=2,
            execution_boundary=self.boundary,
            golden_required=True,
        )
        orders = []

        def alternate(values):
            if not orders:
                values.reverse()
            orders.append(tuple(values))

        with mock.patch(
            "AgMark.shared.runtime.orchestration.planning.shuffle",
            side_effect=alternate,
        ) as shuffled:
            plan = plan_run(
                **arguments,
                extensions={"arcgrav.runtime:randomize-per-iteration": True},
            )
        self.assertEqual(2, shuffled.call_count)
        self.assertEqual(
            [("treatment-b", "treatment-a"), ("treatment-a", "treatment-b")],
            orders,
        )
        for case in self.cases:
            self.assertEqual(
                orders,
                [
                    tuple(
                        item.treatment_id for item in plan.observations
                        if item.case_id == case.case_id and item.repetition == repetition
                    )
                    for repetition in (1, 2)
                ],
            )
        snapshot = accept_run_plan(plan=plan, execution_boundary=self.boundary)
        self.assertEqual(plan.canonical_bytes, snapshot.plan().canonical_bytes)
        self.assertEqual(plan.canonical_bytes, RunPlan.from_document(plan.to_dict()).canonical_bytes)

        with mock.patch(
            "AgMark.shared.runtime.orchestration.planning.shuffle",
            side_effect=AssertionError("default planning must not shuffle"),
        ):
            self.assertEqual(self._plan().to_dict()["extensions"], {})
        with self.assertRaises(PlanningError):
            plan_run(
                **arguments,
                extensions={"arcgrav.runtime:randomize-per-iteration": "yes"},
            )

    def test_duplicate_or_incomplete_plan_authority_fails_closed(self) -> None:
        with self.assertRaises(DuplicatePlanIdentityError):
            plan_run(
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                cases=(self.cases[0], self.cases[0]),
                treatments=self.treatments,
                repetitions=1,
                execution_boundary=self.boundary,
                golden_required=False,
            )

        with self.assertRaises(DuplicatePlanIdentityError):
            plan_run(
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                cases=self.cases,
                treatments=("treatment-a", "treatment-a"),
                repetitions=1,
                execution_boundary=self.boundary,
                golden_required=False,
            )

        with self.assertRaises(IncompletePlanError):
            plan_run(
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                cases=(),
                treatments=self.treatments,
                repetitions=1,
                execution_boundary=self.boundary,
                golden_required=False,
            )

        document = self._plan().to_dict()
        document["observations"] = document["observations"][:-1]
        with self.assertRaises(IncompletePlanError):
            RunPlan.from_document(document)

    def test_acceptance_is_immutable_and_source_drift_fails_closed(self) -> None:
        plan = self._plan()
        snapshot = accept_run_plan(plan=plan, execution_boundary=self.boundary)

        with self.assertRaises(FrozenInstanceError):
            snapshot.run_plan_id = "changed"  # type: ignore[misc]

        retained_copy = plan.to_dict()
        retained_copy["run_plan_id"] = "caller-substituted"
        self.assertEqual(plan.run_plan_id, snapshot.plan().run_plan_id)

        resolved = snapshot.revalidate_authority(
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=self.treatment_set,
            execution_boundary=self.boundary,
        )
        self.assertEqual(plan.canonical_bytes, resolved.canonical_bytes)

        with self.assertRaises(AcceptedSnapshotIntegrityError):
            snapshot.revalidate_authority(
                benchmark=self.benchmark,
                case_set=_source("arcgrav.case-set.test", b"case-set-v2"),
                treatment_set=self.treatment_set,
                execution_boundary=self.boundary,
            )

        with self.assertRaises(AcceptedSnapshotIntegrityError):
            snapshot.revalidate_authority(
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=_boundary(runner_bytes=b"runner-v2"),
            )

    def test_acceptance_rejects_boundary_substitution(self) -> None:
        plan = self._plan()
        with self.assertRaises(AcceptedSnapshotIntegrityError):
            accept_run_plan(
                plan=plan,
                execution_boundary=_boundary(runner_bytes=b"runner-v2"),
            )


if __name__ == "__main__":
    unittest.main()
