from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from AgMark.gui.composition import discover_repository_application_authority


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_SCHEMA_FILENAMES = (
    "catalog.json",
    "schema_catalog.schema.json",
    "registration.schema.json",
    "metric_registration.schema.json",
)


def _copy_registration_schema_authority(root: Path) -> None:
    source_root = _REPOSITORY_ROOT / "AgMark/shared/schemas"
    destination_root = root / "AgMark/shared/schemas"
    destination_root.mkdir(parents=True, exist_ok=True)
    for filename in _SCHEMA_FILENAMES:
        (destination_root / filename).write_bytes(
            (source_root / filename).read_bytes()
        )


class RepositoryRegistrationDiagnosticsTests(unittest.TestCase):
    def test_non_application_diagnostics_are_ordered_and_nonblocking(self) -> None:
        with TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            adapter_root = root / "AgMark/shared/adapters/Diagnostics"
            adapter_root.mkdir(parents=True)
            _copy_registration_schema_authority(root)

            metric_registration = (
                _REPOSITORY_ROOT
                / "AgMark/Authority_Resolution_Benchmark/registrations/v2.0.0"
                / "metric-field-accuracy.json"
            )
            (adapter_root / "metric-dedicated-schema.json").write_bytes(
                metric_registration.read_bytes()
            )
            invalid_metric = json.loads(
                metric_registration.read_text(encoding="utf-8")
            )
            self.assertNotIn("registration_kind", invalid_metric)
            invalid_metric["registration_kind"] = "metric"
            (adapter_root / "invalid-metric-dedicated-schema.json").write_text(
                json.dumps(invalid_metric),
                encoding="utf-8",
            )

            (adapter_root / "invalid-scorer.json").write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.registration",
                        "schema_version": "1.0.0",
                        "extensions": {},
                        "registration_id": "invalid.scorer",
                        "registration_version": "1.0.0",
                        "registration_kind": "scorer",
                        "status": "active",
                        "implementation_artifacts": [],
                        "capabilities": [],
                        "limitations": [],
                    }
                ),
                encoding="utf-8",
            )

            (adapter_root / "unknown-family.json").write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.registration",
                        "schema_version": "1.0.0",
                        "registration_id": "unknown.family",
                        "registration_version": "1.0.0",
                        "registration_kind": "unrecognized-extension",
                        "status": "active",
                    }
                ),
                encoding="utf-8",
            )

            (adapter_root / "unsupported-scorer.json").write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.unsupported",
                        "schema_version": "1.0.0",
                        "registration_id": "unsupported.scorer",
                        "registration_version": "1.0.0",
                        "registration_kind": "scorer",
                        "status": "active",
                    }
                ),
                encoding="utf-8",
            )

            (adapter_root / "unsupported-runner.json").write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.unsupported",
                        "schema_version": "1.0.0",
                        "extensions": {},
                        "registration_id": "unsupported.runner",
                        "registration_version": "1.0.0",
                        "registration_kind": "runner",
                        "status": "active",
                        "contracts": [],
                        "implementation_artifacts": [],
                        "capabilities": [],
                        "limitations": [],
                    }
                ),
                encoding="utf-8",
            )

            authority = discover_repository_application_authority(root)
            repeated = discover_repository_application_authority(root)

            self.assertEqual(
                authority.repository_diagnostics,
                repeated.repository_diagnostics,
            )
            self.assertEqual(
                (
                    (
                        "AgMark/shared/adapters/Diagnostics/invalid-metric-dedicated-schema.json",
                        "SCHEMA_STRUCTURE_INVALID",
                        "/registration_kind",
                    ),
                    (
                        "AgMark/shared/adapters/Diagnostics/invalid-scorer.json",
                        "SCHEMA_STRUCTURE_INVALID",
                        "/contracts",
                    ),
                    (
                        "AgMark/shared/adapters/Diagnostics/unknown-family.json",
                        "REGISTRATION_FAMILY_UNSUPPORTED",
                        "/registration_kind",
                    ),
                    (
                        "AgMark/shared/adapters/Diagnostics/unsupported-scorer.json",
                        "REGISTRATION_SCHEMA_UNSUPPORTED",
                        "/schema_id",
                    ),
                ),
                tuple(
                    (issue.source_id, issue.code, issue.json_pointer)
                    for issue in authority.repository_diagnostics
                ),
            )
            self.assertEqual(
                authority.prerequisite_diagnostics,
                repeated.prerequisite_diagnostics,
            )
            self.assertEqual(
                (
                    "repository-registration-validation:"
                    "AgMark/shared/adapters/Diagnostics/unsupported-runner.json",
                ),
                tuple(
                    diagnostic.diagnostic_name
                    for diagnostic in authority.prerequisite_diagnostics
                ),
            )
            self.assertEqual((), authority.benchmark_candidates)
            self.assertEqual((), authority.discovery.benchmarks)
            self.assertEqual((), authority.runner_sources)
            self.assertEqual((), authority.discovery.runners)


if __name__ == "__main__":
    unittest.main()
