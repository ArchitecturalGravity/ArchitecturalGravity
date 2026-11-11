"""Linear observation lookup keeps exact-byte ambiguity and drift failures."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from AgMark.shared.evaluation.telemetry import consumption
from AgMark.shared.runtime.orchestration import AcceptedRun
from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture


class RetainedMeasurementIndexTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.run, _, self.store, self.plan = accepted_fixture(Path(temporary.name))

    def test_record_hashes_are_indexed_once_and_observation_order_is_preserved(self):
        records = [record for record in self.run.artifact_index.artifacts
                   if record.role == "treatment_observation"]
        lookups = []

        class CountedRecord:
            role = "treatment_observation"

            def __init__(self, record):
                self.record = record

            @property
            def sha256(self):
                lookups.append(self.record.sha256)
                return self.record.sha256

        object.__setattr__(self.run, "artifact_index",
                           SimpleNamespace(artifacts=tuple(CountedRecord(record) for record in records)))
        with patch.object(AcceptedRun, "revalidate"), patch.object(
                consumption, "aggregate_treatment_measurements", return_value={}) as aggregate:
            consumption.retained_run_measurements(self.run, plan=self.plan)
        self.assertEqual(2 * len(records), len(lookups))
        self.assertEqual([consumption.sha256_bytes(raw) for raw in self.run.treatment_observations],
                         [identity for _, identity in aggregate.call_args.args[0]])

    def test_duplicate_and_missing_observation_records_are_not_collapsed(self):
        records = tuple(self.run.artifact_index.artifacts)
        observation = next(record for record in records if record.role == "treatment_observation")
        for changed in (records + (observation,), tuple(record for record in records if record is not observation)):
            with self.subTest(duplicate=len(changed) > len(records)):
                object.__setattr__(self.run, "artifact_index", SimpleNamespace(artifacts=changed))
                with patch.object(AcceptedRun, "revalidate"), self.assertRaisesRegex(
                        ValueError, "lack exact accepted artifact identity"):
                    consumption.retained_run_measurements(self.run, plan=self.plan)

    def test_current_stored_bytes_are_still_checked(self):
        with patch.object(AcceptedRun, "revalidate"), patch.object(
                self.store, "read_verified", return_value=b"changed"), self.assertRaisesRegex(
                    ValueError, "retained measurement byte drift"):
            consumption.retained_run_measurements(self.run, plan=self.plan, store=self.store)


if __name__ == "__main__":
    unittest.main()
