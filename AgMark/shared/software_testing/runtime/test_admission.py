"""Provider-free runtime tests for accepted-execution golden admission."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination
from AgMark.shared.runtime.golden import (
    GoldenArtifactRequirement,
    GoldenCaseInput,
    GoldenDeclaration,
)
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef, ProviderRuntimeIdentity
from AgMark.shared.runtime.orchestration import (
    AcceptedExecutionGate,
    BlockedRun,
    PlannedCaseInput,
    accept_run_plan,
    admit_accepted_execution,
    plan_run,
)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _source(identity: str, payload: bytes) -> IdentityRef:
    return IdentityRef(identity, "1.0.0", sha256=_sha256(payload))


def _boundary(*, environment: dict[str, object] | None = None) -> ExecutionBoundary:
    values: dict[str, object] = {"runtime_family": "provider-free"}
    values.update(environment or {})
    return ExecutionBoundary.build(
        boundary_id="boundary-admission-test",
        framework=_source("arcgrav.framework.admission-test", b"framework-v1"),
        runner=_source("arcgrav.runner.admission-test", b"runner-v1"),
        provider_runtime=ProviderRuntimeIdentity(
            runtime_id="arcgrav.runtime.provider-free",
            runtime_version="1.0.0",
            provider=None,
            access_method="in_process",
            model=None,
        ),
        controls={"network_access": "disabled", "memory_policy": "disabled"},
        environment=values,
    )


class AcceptedExecutionAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.benchmark = _source("arcgrav.benchmark.admission-test", b"benchmark-v1")
        self.case_set = _source("arcgrav.case-set.admission-test", b"cases-v1")
        self.treatment_set = _source("arcgrav.treatment-set.admission-test", b"treatments-v1")
        self.cases = (
            PlannedCaseInput("case-a", _sha256(b"case-a-input"), byte_length=12),
            PlannedCaseInput("case-b", _sha256(b"case-b-input"), byte_length=12),
        )

    def _snapshot(self, boundary: ExecutionBoundary, *, golden_required: bool = True):
        plan = plan_run(
            benchmark=self.benchmark,
            case_set=self.case_set,
            treatment_set=self.treatment_set,
            cases=self.cases,
            treatments=("treatment-a", "treatment-b"),
            repetitions=2,
            execution_boundary=boundary,
            golden_required=golden_required,
        )
        return accept_run_plan(plan=plan, execution_boundary=boundary)

    def _declaration(self, benchmark_root: Path, source: str):
        script = benchmark_root / "golden.py"
        script.write_text(source, encoding="utf-8")
        executable = Path(sys.executable).resolve(strict=True)
        declaration = GoldenDeclaration(
            runtime_executable=str(executable),
            golden_implementation=IdentityRef("arcgrav.golden.admission-test", "1.0.0"),
            runtime_identity=IdentityRef(
                "arcgrav.runtime.python",
                "1.0.0",
                sha256=_sha256(executable.read_bytes()),
                reference="runtime/python",
            ),
            artifacts=(
                GoldenArtifactRequirement(
                    artifact_id="golden.py",
                    relative_path="golden.py",
                    sha256=_sha256(script.read_bytes()),
                ),
            ),
            entry_artifact_id="golden.py",
            environment_family="native",
        )
        return declaration, executable

    def _store(self, root: Path) -> FilesystemArtifactStore:
        return FilesystemArtifactStore(
            PublicationDestination.benchmark_owned(root / "evidence", benchmark_root=root)
        )

    def test_required_golden_failure_is_terminal_before_treatment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            declaration, executable = self._declaration(root, "import sys\nsys.exit(7)\n")
            boundary = _boundary(environment={
                "golden.environment_family": "native",
                "golden.runtime_sha256": _sha256(executable.read_bytes()),
            })
            outcome = admit_accepted_execution(
                generation_id="generation-golden-blocked",
                snapshot=self._snapshot(boundary),
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=self._store(root),
                golden_declaration=declaration,
                golden_case_inputs=(
                    GoldenCaseInput("case-a", b"case-a-input"),
                    GoldenCaseInput("case-b", b"case-b-input"),
                ),
            )

            self.assertIsInstance(outcome, BlockedRun)
            self.assertEqual("GOLDEN_NONZERO_EXIT", outcome.reason_code)
            self.assertEqual((), outcome.treatment_observations)
            self.assertEqual(1, len(outcome.golden_observations))
            states = {
                role.role: role.availability
                for role in outcome.artifact_manifest.evidence_roles
            }
            self.assertEqual("not_produced", states["treatment_observations"])
            self.assertEqual("not_produced", states["score_artifacts"])
            self.assertEqual(outcome.reason_code, outcome.artifact_manifest.reason_code)
            with self.assertRaises(TypeError):
                AcceptedExecutionGate()

    def test_all_required_cases_are_fixed_before_gate_is_minted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            declaration, executable = self._declaration(
                root,
                "import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n",
            )
            boundary = _boundary(environment={
                "golden.environment_family": "native",
                "golden.runtime_sha256": _sha256(executable.read_bytes()),
            })
            gate = admit_accepted_execution(
                generation_id="generation-golden-admitted",
                snapshot=self._snapshot(boundary),
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=self._store(root),
                golden_declaration=declaration,
                golden_case_inputs=(
                    GoldenCaseInput("case-a", b"case-a-input"),
                    GoldenCaseInput("case-b", b"case-b-input"),
                ),
            )

            self.assertIsInstance(gate, AcceptedExecutionGate)
            gate.revalidate()
            observations = [
                json.loads(value.decode("utf-8"))
                for value in gate.golden_observations
            ]
            self.assertEqual(2, len(observations))
            self.assertTrue(
                all(value["admission_state"] == "admitted" for value in observations)
            )
            self.assertEqual(4, len(gate.retained_golden_artifacts))

    def test_non_golden_plan_does_not_run_or_fabricate_golden_evidence(self) -> None:
        boundary = _boundary()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            gate = admit_accepted_execution(
                generation_id="generation-no-golden",
                snapshot=self._snapshot(boundary, golden_required=False),
                benchmark=self.benchmark,
                case_set=self.case_set,
                treatment_set=self.treatment_set,
                execution_boundary=boundary,
                benchmark_root=root,
                artifact_store=self._store(root),
            )
            self.assertIsInstance(gate, AcceptedExecutionGate)
            gate.revalidate()
            self.assertEqual((), gate.golden_observations)
            self.assertEqual((), gate.retained_golden_artifacts)


if __name__ == "__main__":
    unittest.main()
