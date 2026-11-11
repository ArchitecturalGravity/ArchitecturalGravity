"""Private validation stages retain confinement without pretending to be runs."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from AgMark.shared.runtime.artifacts.storage import (
    ArtifactPathError, FilesystemArtifactStore, PublicationDestination,
)
from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore


class ValidationStagingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        repository = root / "repository"
        repository.mkdir()
        self.scored = FilesystemArtifactStore(PublicationDestination.external(
            root / "evidence", repository_root=repository))
        self.store = ValidationArtifactStore(self.scored)
        self.stage = self.store.root / ".validation-test"
        self.stage.mkdir(parents=True)
        # A minimal authority double isolates byte routing; lifecycle acceptance
        # and immutable scored parity are covered by FinalizedReplayIsolationTests.
        self.terminal = SimpleNamespace(
            generation_id="generation-test", accepted_snapshot_id="accepted-test",
            execution_boundary_fingerprint="boundary-test", plan_sha256="plan-test",
            artifact_index=SimpleNamespace(artifacts=()), treatment_observations=(),
            revalidate=Mock(),
        )
        manifest = {
            "generation_id": "generation-test", "accepted_snapshot_id": "accepted-test",
            "execution_boundary_fingerprint": "boundary-test", "run_plan_sha256": "plan-test",
            "scored_evidence": {}, "validations": [], "captures": [], "sources": [],
            "scope": "configuration_equivalent_replay", "included_in_score": False,
        }
        self.raw = json.dumps(manifest).encode()
        (self.stage / "manifest.json").write_bytes(self.raw)
        (self.stage / "manifest.sha256").write_text(
            "sha256:" + hashlib.sha256(self.raw).hexdigest())

    def test_private_stage_is_validated_without_archive_member_routing(self):
        with patch.object(self.scored, "read_member", side_effect=AssertionError("not published")):
            self.assertEqual(self.store._read_directory(
                self.terminal, self.stage, staging=True), ())
        self.terminal.revalidate.assert_called_once_with(self.scored)

    def test_private_stage_rejects_symlinked_manifest(self):
        original = self.stage / "manifest.json"
        target = self.stage.parent / "outside.json"
        target.write_bytes(self.raw)
        original.unlink()
        original.symlink_to(target)
        with self.assertRaises(ArtifactPathError):
            self.store._read_directory(self.terminal, self.stage, staging=True)

    def test_staging_mode_rejects_unowned_directory(self):
        with self.assertRaisesRegex(ValueError, "outside its owned root"):
            self.store._read_directory(self.terminal, self.scored.root, staging=True)

    def test_published_reads_use_sealed_archive_not_loose_staging_bytes(self):
        from AgMark.shared.runtime.artifacts.archive import seal_generation
        from AgMark.shared.reporting.completion import completion_record
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture
        # Publication now validates complete minimized evidence, so an empty
        # object can no longer stand in for a valid retained observation.
        with TemporaryDirectory() as directory:
            terminal, _, scored, _ = accepted_fixture(Path(directory))
            retained = ValidationArtifactStore(scored)
            retained.retain(terminal, ())
            published = retained.root / terminal.generation_id
            seal_generation(scored.root, terminal.generation_id, report_components={},
                completion_record=completion_record(terminal.generation_id, status="report_failed",
                    diagnostic="automatic_report_failed:ValueError"))
            self.assertFalse(published.exists())
            with patch.object(scored, "read_member", wraps=scored.read_member) as read, \
                    patch.object(scored, "_path_for_reference", side_effect=AssertionError("loose read attempted")):
                self.assertEqual(retained.read(terminal), ())
            self.assertGreaterEqual(read.call_count, 2)


if __name__ == "__main__":
    unittest.main()
