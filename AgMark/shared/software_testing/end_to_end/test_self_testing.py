"""End-to-end checks for the developer-only provider-free lifecycle harness."""

from __future__ import annotations

from contextlib import redirect_stdout
from importlib import import_module
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from AgMark.shared.adapters.Mock_Model import catalog
from AgMark.shared.software_testing.self_testing import dry_run
from AgMark.shared.software_testing.self_testing import run_deterministic_dry_run


class SharedSelfTestingDiagnosticTests(unittest.TestCase):
    def test_harness_registrations_resolve_developer_owned_sources(self) -> None:
        testing_root = Path(__file__).resolve().parents[1]
        self.assertEqual(testing_root, dry_run._SOFTWARE_TESTING_ROOT)
        self.assertEqual(testing_root.parent, dry_run._SHARED_ROOT)
        self.assertEqual(testing_root / "self_testing", dry_run._SELF_TESTING_ROOT)

        benchmark = dry_run._validated_diagnostic_benchmark()
        definition = dry_run._scoring_definition()
        self.assertTrue(definition.scorer_registration_outcome.valid)
        scorer_artifact, = definition.scorer_registration["implementation_artifacts"]
        for reference, filename in (
            (benchmark.reference, "dry_run.py"),
            (scorer_artifact["reference"], "diagnostic_scorer.py"),
        ):
            self.assertEqual(
                testing_root / "self_testing" / filename,
                dry_run._REPOSITORY_ROOT / reference,
            )
            self.assertTrue((dry_run._REPOSITORY_ROOT / reference).is_file())

        entry_point = definition.scorer_registration["extensions"][
            dry_run.SCORER_ENTRY_POINT_EXTENSION
        ]
        module_name, function_name = entry_point.split(":")
        scorer_module = import_module(module_name)
        self.assertEqual(
            testing_root / "self_testing" / "diagnostic_scorer.py",
            Path(scorer_module.__file__).resolve(),
        )
        self.assertTrue(callable(getattr(scorer_module, function_name)))

    def test_developer_cli_runs_the_provider_free_lifecycle(self) -> None:
        process = subprocess.run(
            [sys.executable, "-m", "AgMark.shared.software_testing.self_testing"],
            cwd=Path(__file__).resolve().parents[4],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, process.returncode, process.stderr or process.stdout)
        self.assertEqual("", process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual("verified", result["verification_result"]["status"])
        self.assertTrue(result["diagnostic"])
        self.assertFalse(result["authoritative"])

    def test_cli_reports_failed_checks_with_nonzero_exit_status(self) -> None:
        result = dry_run.DeterministicDryRunResult(
            observations=(),
            verification_result=dry_run.VerificationResult(
                status="failed", issues=("fixture failure",),
            ),
            repetition_count=1,
        )
        output = StringIO()
        with patch.object(dry_run, "run_deterministic_dry_run", return_value=result):
            with redirect_stdout(output):
                self.assertEqual(1, dry_run.main())
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["diagnostic"])
        self.assertFalse(payload["authoritative"])
        self.assertEqual(
            {"status": "failed", "issues": ["fixture failure"]},
            payload["verification_result"],
        )

    def test_required_authority_uses_published_contracts_and_fails_closed_if_missing(self):
        self.assertTrue(all(path.startswith("contracts/")
                            for path in dry_run._REQUIRED_SPECIFICATIONS))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in dry_run._REQUIRED_SPECIFICATIONS:
                path = root / relative
                path.parent.mkdir(exist_ok=True)
                path.write_text("Test-only contract presence fixture\n")
            with patch.object(dry_run, "_SHARED_ROOT", root):
                self.assertEqual("passed", dry_run._check_required_specifications().status)
                missing = dry_run._REQUIRED_SPECIFICATIONS[1]
                (root / missing).unlink()
                result = dry_run._check_required_specifications()
                self.assertEqual("failed", result.status)
                self.assertIn(missing, result.detail)

    def test_production_ownership_scan_prunes_testing_and_installed_environments(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            production = root / "runtime" / "production.py"
            production.parent.mkdir()
            production.write_text("value = 1\n")
            excluded = ("software_testing", "__pycache__", ".venv", "custom_environment")
            for name in excluded:
                target = root / name
                target.mkdir()
                (target / "excluded.py").write_text("value = 2\n")
            (root / "custom_environment" / "pyvenv.cfg").write_text("home = fixture\n")
            scandir = os.scandir

            def inspect_production_only(path):
                self.assertNotIn(Path(path).name, excluded)
                return scandir(path)

            with patch.object(dry_run, "_SHARED_ROOT", root), patch(
                "os.scandir", side_effect=inspect_production_only,
            ):
                self.assertEqual([production], list(dry_run._iter_production_python()))

    def test_provider_free_lifecycle_is_deterministic_and_non_authoritative(self) -> None:
        first = run_deterministic_dry_run(repetition_count=2)
        second = run_deterministic_dry_run(repetition_count=2)

        self.assertEqual(first, second)
        self.assertTrue(first.diagnostic)
        self.assertFalse(first.authoritative)
        self.assertEqual("shared-lifecycle-registered-mock-model", first.to_dict()["scope"])
        self.assertFalse(first.to_dict()["runner_path_parity"])
        self.assertEqual(2, first.repetition_count)
        self.assertEqual("verified", first.verification_result.status)
        self.assertEqual((), first.verification_result.issues)

        observations = {observation.check_id: observation for observation in first.observations}
        self.assertEqual(
            {
                "required-specifications",
                "software-testing-dependency-boundary",
                "provider-free-lifecycle",
            },
            set(observations),
        )
        self.assertTrue(
            all(observation.status == "passed" for observation in observations.values())
        )

        lifecycle = observations["provider-free-lifecycle"]
        self.assertEqual(
            "accepted_generation=generation-shared-self-test-diagnostic; "
            "report_status=dry_run; report_components=present",
            lifecycle.detail,
        )

    def test_invalid_repetition_count_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_deterministic_dry_run(repetition_count=0)

    def test_unavailable_mock_prerequisites_fail_without_replacement_execution(self) -> None:
        failures = (
            patch.object(dry_run, "load_registration", side_effect=FileNotFoundError("mock registration missing")),
            patch.object(catalog, "probe_model_discovery", return_value={
                "status": "unsupported", "error_code": "mock_catalog_unavailable",
            }),
            patch.object(dry_run, "probe_planning_identity", return_value={
                "status": "unsupported", "error_code": "mock_identity_unavailable",
            }),
        )
        for failure, expected in zip(failures, (
            "mock registration missing", "mock_boundary_unsupported", "mock_identity_unavailable",
        )):
            with (
                self.subTest(prerequisite=expected), failure,
                patch.object(dry_run, "execute_planned_treatments") as execute,
                patch.object(dry_run, "generate_report_bundle") as report,
            ):
                result = run_deterministic_dry_run()
                lifecycle = next(item for item in result.observations if item.check_id == "provider-free-lifecycle")
                self.assertEqual("failed", lifecycle.status)
                self.assertIn(expected, lifecycle.detail)
                self.assertEqual("failed", result.verification_result.status)
                self.assertTrue(result.verification_result.issues)
                self.assertTrue(result.diagnostic)
                self.assertFalse(result.authoritative)
                self.assertFalse(result.runner_path_parity)
                self.assertNotIn("accepted_generation=", lifecycle.detail)
                execute.assert_not_called()
                report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
