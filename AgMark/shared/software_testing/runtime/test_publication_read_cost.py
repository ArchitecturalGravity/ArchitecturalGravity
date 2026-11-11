"""Count bounded publication reads without weakening evidence revalidation."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from AgMark.shared.reporting.completion import completion_record
from AgMark.shared.runtime.artifacts import archive
from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore
from AgMark.shared.runtime.orchestration.replay import disabled_validation_summaries
from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture


class PublicationReadCostTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.terminal, _, self.store, _ = accepted_fixture(Path(temporary.name))
        self.companion = ValidationArtifactStore(self.store)
        self.values = disabled_validation_summaries(self.terminal)
        self.companion.retain(self.terminal, self.values)

    def test_one_companion_admission_provides_summaries_and_exact_records(self):
        with patch.object(self.companion, "read", wraps=self.companion.read) as read:
            summaries, records = self.companion.read_with_records(self.terminal, required=True)
        self.assertEqual(1, read.call_count)
        self.assertEqual([value.to_dict() for value in self.values], [value.to_dict() for value in summaries])
        self.assertEqual(records, self.companion.records(self.terminal))
        for record in records:
            self.store.read_verified(record)

    def test_later_companion_boundary_rechecks_current_bytes(self):
        self.companion.read_with_records(self.terminal)
        path = self.companion.root / self.terminal.generation_id / "treatment-0.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.companion.read_with_records(self.terminal)

    def test_nested_store_and_companion_reads_share_one_verified_zip_operation(self):
        gid = self.terminal.generation_id
        archive.seal_generation(self.store.root, gid, report_components={},
            completion_record=completion_record(gid, status="report_failed",
                diagnostic="automatic_report_failed:ValueError"))
        with patch.object(archive, "ZipFile", wraps=ZipFile) as opened:
            with self.store.verified_reads(gid):
                self.terminal.revalidate(self.store)
                summaries, records = self.companion.read_with_records(self.terminal)
                for record in records:
                    self.store.read_verified(record)
            self.assertEqual(1, opened.call_count)
        self.assertEqual([value.to_dict() for value in self.values], [value.to_dict() for value in summaries])
        # A later independent boundary must not reuse the previous operation.
        with patch.object(archive, "ZipFile", wraps=ZipFile) as opened:
            self.companion.read(self.terminal)
            self.assertEqual(1, opened.call_count)


if __name__ == "__main__":
    unittest.main()
