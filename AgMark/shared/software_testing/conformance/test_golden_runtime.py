"""Provider-free conformance coverage for required golden runtime admission."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.runtime.artifacts import (
    FilesystemArtifactStore,
    PublicationDestination,
)
from AgMark.shared.runtime.golden import (
    GoldenArtifactRequirement,
    GoldenCaseInput,
    GoldenDeclaration,
    GoldenRegistrationError,
    execute_required_golden,
)
from AgMark.shared.runtime.golden import execution as golden_execution
from AgMark.shared.runtime.identity import (
    AcceptedBoundaryIdentity,
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)


_RUNNER_ID = "arcgrav.fixture.golden-runtime-runner"
_RUNNER_VERSION = "1.0.0"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _boundary(*, boundary_id: str, environment: dict[str, object]) -> ExecutionBoundary:
    return ExecutionBoundary.build(
        boundary_id=boundary_id,
        framework=IdentityRef("arcgrav.framework.golden-conformance", "1.0.0"),
        runner=IdentityRef(_RUNNER_ID, _RUNNER_VERSION),
        provider_runtime=ProviderRuntimeIdentity(
            runtime_id="arcgrav.runtime.provider-free",
            runtime_version="1.0.0",
            provider=None,
            access_method="in_process",
            model=None,
        ),
        environment=environment,
    )


class GoldenRuntimeConformanceTests(unittest.TestCase):
    def _execute(
        self,
        benchmark_root: Path,
        *,
        generation_id: str,
        source: str = "import sys\nsys.stdout.write('ok')\n",
        environment: dict[str, object] | None = None,
        declaration_overrides: dict[str, object] | None = None,
        additional_artifacts: tuple[GoldenArtifactRequirement, ...] = (),
        input_data: bytes = b"input",
    ):
        script = benchmark_root / f"{generation_id}.py"
        script.write_text(source, encoding="utf-8")
        executable = Path(sys.executable).resolve(strict=True)
        accepted_environment = environment or {
            "golden.environment_family": "native",
            "golden.runtime_sha256": _sha256(executable.read_bytes()),
        }
        boundary = _boundary(
            boundary_id=f"boundary-{generation_id}",
            environment=accepted_environment,
        )
        accepted = AcceptedBoundaryIdentity.accept(
            accepted_identity_id=f"accepted-{generation_id}",
            boundary=boundary,
        )
        declaration_values: dict[str, object] = {
            "golden_implementation": IdentityRef(
                "arcgrav.golden.conformance-test",
                "1.0.0",
            ),
            "runtime_executable": str(executable),
            "runtime_identity": IdentityRef(
                "arcgrav.runtime.python",
                "1.0.0",
                sha256=_sha256(executable.read_bytes()),
                reference="runtime/python",
            ),
            "artifacts": (
                GoldenArtifactRequirement(
                    artifact_id=script.name,
                    relative_path=script.name,
                    sha256=_sha256(script.read_bytes()),
                ),
                *additional_artifacts,
            ),
            "entry_artifact_id": script.name,
            "environment_family": "native",
        }
        declaration_values.update(declaration_overrides or {})
        declaration = GoldenDeclaration(**declaration_values)
        store = FilesystemArtifactStore(
            PublicationDestination.benchmark_owned(
                benchmark_root / "evidence",
                benchmark_root=benchmark_root,
            )
        )
        return execute_required_golden(
            accepted_generation_id=generation_id,
            benchmark=IdentityRef("arcgrav.benchmark.golden-conformance", "1.0.0"),
            benchmark_root=benchmark_root,
            accepted_boundary=accepted,
            retained_boundary_document=boundary.to_dict(),
            declaration=declaration,
            case_input=GoldenCaseInput("case-golden-conformance", input_data),
            artifact_store=store,
        )

    def _assert_blocked(self, result, reason_code: str, *, status: str | None = None) -> None:
        observation = result.observation
        self.assertFalse(result.treatment_authorized)
        self.assertEqual("blocked", observation["admission_state"])
        if status is not None:
            self.assertEqual(status, observation["status"])
        self.assertTrue(
            any(
                diagnostic == reason_code
                for diagnostic in observation["diagnostics"]
            ),
            observation["diagnostics"],
        )

    def test_artifact_hash_mismatch_and_path_escape_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = (Path(directory) / "benchmark").resolve()
            benchmark_root.mkdir()
            executable = Path(sys.executable).resolve(strict=True)
            script = benchmark_root / "golden.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            environment = {
                "golden.environment_family": "native",
                "golden.runtime_sha256": _sha256(executable.read_bytes()),
            }
            boundary = _boundary(
                boundary_id="boundary-artifact-integrity",
                environment=environment,
            )
            accepted = AcceptedBoundaryIdentity.accept(
                accepted_identity_id="accepted-artifact-integrity",
                boundary=boundary,
            )
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    benchmark_root / "evidence",
                    benchmark_root=benchmark_root,
                )
            )

            mismatched = GoldenDeclaration(
            runtime_executable=str(executable),
                golden_implementation=IdentityRef(
                    "arcgrav.golden.conformance-test",
                    "1.0.0",
                ),
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
                        sha256="sha256:" + "0" * 64,
                    ),
                ),
                entry_artifact_id="golden.py",
                environment_family="native",
            )
            result = execute_required_golden(
                accepted_generation_id="generation-artifact-hash-mismatch",
                benchmark=IdentityRef(
                    "arcgrav.benchmark.golden-conformance",
                    "1.0.0",
                ),
                benchmark_root=benchmark_root,
                accepted_boundary=accepted,
                retained_boundary_document=boundary.to_dict(),
                declaration=mismatched,
                case_input=GoldenCaseInput("case-golden-conformance", b"input"),
                artifact_store=store,
            )
            self._assert_blocked(
                result,
                "GOLDEN_ARTIFACT_HASH_MISMATCH",
                status="failed",
            )

            outside = Path(directory) / "outside.py"
            outside.write_text("print('outside')\n", encoding="utf-8")
            link = benchmark_root / "escaped.py"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            escaped = GoldenDeclaration(
            runtime_executable=str(executable),
                golden_implementation=IdentityRef(
                    "arcgrav.golden.conformance-test",
                    "1.0.0",
                ),
                runtime_identity=IdentityRef(
                    "arcgrav.runtime.python",
                    "1.0.0",
                    sha256=_sha256(executable.read_bytes()),
                    reference="runtime/python",
                ),
                artifacts=(
                    GoldenArtifactRequirement(
                        artifact_id="escaped.py",
                        relative_path="escaped.py",
                        sha256=_sha256(outside.read_bytes()),
                    ),
                ),
                entry_artifact_id="escaped.py",
                environment_family="native",
            )
            escaped_result = execute_required_golden(
                accepted_generation_id="generation-artifact-path-escape",
                benchmark=IdentityRef(
                    "arcgrav.benchmark.golden-conformance",
                    "1.0.0",
                ),
                benchmark_root=benchmark_root,
                accepted_boundary=accepted,
                retained_boundary_document=boundary.to_dict(),
                declaration=escaped,
                case_input=GoldenCaseInput("case-golden-conformance", b"input"),
                artifact_store=store,
            )
            self._assert_blocked(
                escaped_result,
                "GOLDEN_ARTIFACT_PATH_ESCAPE",
                status="failed",
            )

    def test_current_golden_reader_rejects_relabelled_legacy_payloads(self):
        from copy import deepcopy
        from AgMark.shared.runtime.golden.execution import validate_golden_evidence
        with tempfile.TemporaryDirectory() as directory:
            result = self._execute(Path(directory), generation_id="generation-reader-policy")
            document = result.observation
            validate_golden_evidence(document)
            for field, value in (("command", ["/home/private-person/python", "script.py"]),
                                 ("private_metadata", "private-person@example.test"),
                                 ("stderr", {"byte_length": 2, "sha256": "sha256:" + "0" * 64})):
                changed = deepcopy(document)
                changed["extensions"]["arcgrav.shared.golden:evidence"]["observed"][field] = value
                with self.assertRaises(ValueError):
                    validate_golden_evidence(changed)
            changed = deepcopy(document)
            changed["runtime_identity"]["reference"] = "/home/private-person/python"
            with self.assertRaises(ValueError):
                validate_golden_evidence(changed)

    def test_private_stderr_and_host_paths_never_enter_retained_evidence(self):
        with tempfile.TemporaryDirectory(prefix="private-user-") as directory:
            root = Path(directory).resolve()
            marker = "private-person@example.test /home/private-person/work"
            result = self._execute(root, generation_id="generation-privacy",
                source="import sys\nsys.stdout.write('required-score-output')\nsys.stderr.write(" + repr(marker) + ")\n")
            self.assertTrue(result.treatment_authorized)
            self.assertNotIn("golden_stderr", [r.role for r in result.retained_artifacts])
            for record in result.retained_artifacts:
                raw = (root / "evidence" / record.reference).read_bytes()
                self.assertNotIn(marker.encode(), raw)
                self.assertNotIn(directory.encode(), raw)
                self.assertNotIn(str(Path(sys.executable).resolve()).encode(), raw)
            failed = self._execute(root, generation_id="generation-privacy-failure",
                source="import sys\nsys.stderr.write(" + repr(marker) + ")\nsys.exit(2)\n")
            self.assertEqual(["GOLDEN_NONZERO_EXIT"], failed.observation["diagnostics"])

    def test_accepted_environment_and_exact_runtime_are_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            result = self._execute(
                benchmark_root,
                generation_id="generation-runtime-reuse",
            )
            observation = result.observation
            observed = observation["extensions"][
                "arcgrav.shared.golden:evidence"
            ]["observed"]
            executable = str(Path(sys.executable).resolve(strict=True))

            self.assertTrue(result.treatment_authorized)
            self.assertEqual("admitted", observation["admission_state"])
            self.assertEqual("native", observed["environment_family"])
            self.assertEqual("runtime/python", observed["runtime_reference"])
            self.assertEqual("runtime/python", observed["preflight"]["runtime_reference"])
            self.assertEqual("runtime/python", observed["command"]["runtime"])
            self.assertEqual(
                _sha256(Path(executable).read_bytes()),
                observed["runtime_sha256"],
            )

    def test_python_golden_launch_controls_text_output_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            result = self._execute(
                benchmark_root,
                generation_id="generation-python-lf-output",
                source="import sys\nsys.stdout.write('alpha\\nbeta')\n",
            )
            observation = result.observation
            observed = observation["extensions"][
                "arcgrav.shared.golden:evidence"
            ]["observed"]
            command = observed["command"]
            self.assertEqual("runtime/python", command["runtime"])
            self.assertEqual("generation-python-lf-output.py", command["entry"])
            self.assertEqual([], command["arguments"])

            stdout_record = next(
                record
                for record in result.retained_artifacts
                if record.role == "golden_stdout"
            )
            retained_stdout = (
                benchmark_root / "evidence" / stdout_record.reference
            ).read_bytes()
            self.assertEqual(b"alpha\nbeta", retained_stdout)

    def test_registered_file_uses_private_snapshot_and_closed_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            case_path = root / "cases" / "source.json"
            case_path.parent.mkdir()
            accepted_input = b'{"records": []}\n'
            case_path.write_bytes(accepted_input)
            requirement = GoldenArtifactRequirement(
                "case-input", "cases/source.json", _sha256(accepted_input)
            )
            (root / "unregistered.txt").write_bytes(b"ambient file")
            real_run = golden_execution._run_process
            snapshots: list[Path] = []

            def run_snapshot(**kwargs):
                snapshot = kwargs["cwd"]
                snapshots.append(snapshot)
                self.assertNotEqual(root, snapshot)
                self.assertIsNone(kwargs["input_bytes"])
                self.assertFalse((snapshot / "unregistered.txt").exists())
                self.assertEqual(
                    accepted_input, (snapshot / "cases/source.json").read_bytes()
                )
                # Changing the live repository after staging cannot replace the
                # case that this accepted generation actually reads.
                case_path.write_bytes(b'{"changed": true}\n')
                return real_run(**kwargs)

            with patch.object(golden_execution, "_run_process", side_effect=run_snapshot):
                result = self._execute(
                    root,
                    generation_id="generation-file-snapshot",
                    source=(
                        "import sys\nfrom pathlib import Path\n"
                        "assert sys.stdin.buffer.read() == b''\n"
                        "source = Path(__file__).parent / 'cases/source.json'\n"
                        "sys.stdout.buffer.write(source.read_bytes())\n"
                    ),
                    input_data=accepted_input,
                    additional_artifacts=(requirement,),
                    declaration_overrides={
                        "input_transport": "registered_file",
                        "input_artifact_id": "case-input",
                    },
                )
            self.assertTrue(result.treatment_authorized, result.observation["diagnostics"])
            stdout_record = next(
                record for record in result.retained_artifacts if record.role == "golden_stdout"
            )
            self.assertEqual(
                accepted_input, (root / "evidence" / stdout_record.reference).read_bytes()
            )
            evidence = result.observation["extensions"]["arcgrav.shared.golden:evidence"]
            self.assertEqual({
                "transport": "registered_file",
                "artifact_id": "case-input",
                "relative_path": "cases/source.json",
                "sha256": _sha256(accepted_input),
                "byte_length": len(accepted_input),
            }, evidence["input"])
            self.assertEqual("case-input", evidence["observed"]["input_file_snapshot"]["artifact_id"])
            self.assertEqual(1, len(snapshots))
            self.assertFalse(snapshots[0].exists())

    def test_registered_file_rejects_wrong_or_mutated_case_before_workload(self) -> None:
        for mutated in (False, True):
            with self.subTest(mutated=mutated), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                case_path = root / "source.json"
                case_path.write_bytes(b"registered input")
                requirement = GoldenArtifactRequirement(
                    "case-input", "source.json", _sha256(case_path.read_bytes())
                )
                if mutated:
                    case_path.write_bytes(b"changed input")
                with patch.object(golden_execution, "_run_process") as workload:
                    result = self._execute(
                        root,
                        generation_id=f"generation-file-mismatch-{int(mutated)}",
                        input_data=b"different accepted case",
                        additional_artifacts=(requirement,),
                        declaration_overrides={
                            "input_transport": "registered_file",
                            "input_artifact_id": "case-input",
                        },
                    )
                workload.assert_not_called()
                self._assert_blocked(
                    result,
                    "GOLDEN_ARTIFACT_HASH_MISMATCH" if mutated else "GOLDEN_INPUT_ARTIFACT_MISMATCH",
                    status="failed",
                )
                self.assertEqual([], list((root / "evidence").glob(".golden-input-*")))

    def test_registered_file_requires_declared_input_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(GoldenRegistrationError):
                self._execute(
                    Path(directory).resolve(),
                    generation_id="generation-file-undeclared",
                    declaration_overrides={
                        "input_transport": "registered_file",
                        "input_artifact_id": "undeclared-case-input",
                    },
                )

    def test_registered_runtime_identity_must_match_resolved_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            executable = Path(sys.executable).resolve(strict=True)
            hash_result = self._execute(
                benchmark_root,
                generation_id="generation-runtime-hash-mismatch",
                declaration_overrides={
                    "runtime_identity": IdentityRef(
                        "arcgrav.runtime.python",
                        "1.0.0",
                        sha256="sha256:" + "0" * 64,
                        reference="runtime/python",
                    )
                },
            )
            self._assert_blocked(
                hash_result,
                "GOLDEN_RUNTIME_REFERENCE_MISMATCH",
                status="failed",
            )

            other = benchmark_root / "registered-other-runtime"
            other.write_bytes(b"not-the-accepted-runtime")
            reference_result = self._execute(
                benchmark_root,
                generation_id="generation-runtime-reference-mismatch",
                declaration_overrides={
                    "runtime_identity": IdentityRef(
                        "arcgrav.runtime.python",
                        "1.0.0",
                        sha256=_sha256(other.read_bytes()),
                        reference="runtime/python",
                    )
                },
            )
            self._assert_blocked(
                reference_result,
                "GOLDEN_RUNTIME_REFERENCE_MISMATCH",
                status="failed",
            )

    def test_environment_and_transport_authority_fail_closed(self) -> None:
        executable = str(Path(sys.executable).resolve(strict=True))
        cases = (
            (
                "environment-mismatch",
                {
                    "golden.environment_family": "native",
                    "golden.runtime_sha256": _sha256(Path(executable).read_bytes()),
                },
                {"environment_family": "wsl"},
                "GOLDEN_ENVIRONMENT_FAMILY_MISMATCH",
                "unsupported",
            ),
            (
                "environment-unsupported",
                {
                    "golden.environment_family": "wsl",
                    "golden.runtime_sha256": _sha256(Path(executable).read_bytes()),
                },
                {"environment_family": "wsl"},
                "GOLDEN_ENVIRONMENT_UNSUPPORTED",
                "unsupported",
            ),
            (
                "input-transport",
                None,
                {"input_transport": "file"},
                "GOLDEN_INPUT_TRANSPORT_UNSUPPORTED",
                "unsupported",
            ),
            (
                "output-transport",
                None,
                {"output_transport": "file"},
                "GOLDEN_OUTPUT_TRANSPORT_UNSUPPORTED",
                "unsupported",
            ),
        )
        for name, environment, overrides, reason_code, status in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                result = self._execute(
                    Path(directory).resolve(),
                    generation_id=f"generation-{name}",
                    environment=environment,
                    declaration_overrides=overrides,
                )
                self._assert_blocked(result, reason_code, status=status)

    def test_preflight_launch_timeout_nonzero_empty_and_output_limits_block(self) -> None:
        cases = (
            (
                "preflight-nonzero",
                "import sys\nsys.stdout.write('ok')\n",
                {"preflight_arguments": ("-c", "raise SystemExit(9)")},
                "GOLDEN_RUNTIME_PREFLIGHT_FAILED",
                "failed",
            ),
            (
                "preflight-timeout",
                "import sys\nsys.stdout.write('ok')\n",
                {
                    "preflight_arguments": (
                        "-c",
                        "import time; time.sleep(1)",
                    ),
                    "preflight_timeout_seconds": 0.01,
                },
                "GOLDEN_RUNTIME_PREFLIGHT_TIMEOUT",
                "timed_out",
            ),
            (
                "timeout",
                "import time\ntime.sleep(1)\n",
                {"timeout_seconds": 0.01},
                "GOLDEN_TIMEOUT",
                "timed_out",
            ),
            (
                "nonzero",
                "raise SystemExit(7)\n",
                {},
                "GOLDEN_NONZERO_EXIT",
                "failed",
            ),
            (
                "required-empty",
                "pass\n",
                {},
                "GOLDEN_REQUIRED_OUTPUT_EMPTY",
                "failed",
            ),
            (
                "stdout-limit",
                "import sys\nsys.stdout.write('abcd')\n",
                {"max_stdout_bytes": 3},
                "GOLDEN_STDOUT_LIMIT_EXCEEDED",
                "failed",
            ),
            (
                "stderr-limit",
                "import sys\nsys.stdout.write('ok')\nsys.stderr.write('abcd')\n",
                {"max_stderr_bytes": 3},
                "GOLDEN_STDERR_LIMIT_EXCEEDED",
                "failed",
            ),
        )
        for name, source, overrides, reason_code, status in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                result = self._execute(
                    Path(directory).resolve(),
                    generation_id=f"generation-{name}",
                    source=source,
                    declaration_overrides=overrides,
                )
                self._assert_blocked(result, reason_code, status=status)

        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            real_popen = golden_execution.subprocess.Popen
            calls = 0

            def fail_workload_launch(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("forced launch failure")
                return real_popen(*args, **kwargs)

            with patch.object(
                golden_execution.subprocess,
                "Popen",
                side_effect=fail_workload_launch,
            ):
                result = self._execute(
                    benchmark_root,
                    generation_id="generation-launch-failure",
                )
            self.assertEqual(2, calls)
            self._assert_blocked(
                result,
                "GOLDEN_LAUNCH_FAILED",
                status="unavailable",
            )

    def test_observation_retention_failure_revokes_admission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            real_retain = golden_execution.retain_artifact_stage
            calls = 0

            def fail_observation_retention(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("forced observation retention failure")
                return real_retain(*args, **kwargs)

            with patch.object(
                golden_execution,
                "retain_artifact_stage",
                side_effect=fail_observation_retention,
            ):
                result = self._execute(
                    benchmark_root,
                    generation_id="generation-retention-failure",
                )

            self.assertEqual(2, calls)
            self._assert_blocked(
                result,
                "GOLDEN_OBSERVATION_RETENTION_FAILED",
                status="failed",
            )


if __name__ == "__main__":
    unittest.main()
