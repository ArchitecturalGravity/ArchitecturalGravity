"""Compact replay references retain only exact observation and source binding."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore
from AgMark.shared.runtime.orchestration import TreatmentCaseInput, TreatmentPrompt
from AgMark.shared.runtime.orchestration.replay import validate_finalized_run
from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture
from AgMark.shared.validation.codex_cache.capture import digest


class ReplayEvidenceBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.terminal, boundary, self.store, _ = accepted_fixture(Path(temporary.name))
        self.values = validate_finalized_run(terminal=self.terminal, artifact_store=self.store,
            boundary=boundary,
            case_inputs=(TreatmentCaseInput("case-runtime-scoring", b"runtime-scoring-case-input"),),
            treatment_prompts=(TreatmentPrompt("treatment-runtime-scoring", b"runtime-scoring-prompt"),))
        self.hashes = {json.loads(raw)["observation_id"]: digest(raw)
            for raw in self.terminal.treatment_observations}
        self.retained = ValidationArtifactStore(self.store)

    def test_each_replay_references_own_observation_and_manifest_keeps_all_evidence(self):
        before = tuple(self.terminal.treatment_observations)
        for summary in self.values:
            self.assertEqual(len(self.hashes), summary.coverage.validation_replays_planned)
            for replay in summary.replays:
                self.assertEqual((self.hashes[replay.validates_observation_id],), replay.evidence_references)
        reopened = self.retained.retain(self.terminal, self.values)
        self.assertEqual([v.to_dict() for v in self.values], [v.to_dict() for v in reopened])
        manifest = json.loads((self.retained.root / self.terminal.generation_id / "manifest.json").read_bytes())
        self.assertEqual({r.artifact_id: r.sha256 for r in self.terminal.artifact_index.artifacts},
            manifest["scored_evidence"])
        self.assertEqual(before, self.terminal.treatment_observations)
        self.terminal.revalidate(self.store)

    def test_unrelated_observation_reference_supersets_are_rejected(self):
        all_references = tuple(self.hashes.values())
        unrelated = tuple(replace(summary, replays=tuple(
            replace(replay, evidence_references=all_references) for replay in summary.replays))
            for summary in self.values)
        with self.assertRaisesRegex(ValueError, "only its observation"):
            self.retained.retain(self.terminal, unrelated)
        self.assertFalse((self.retained.root / self.terminal.generation_id).exists())

    def test_missing_or_other_observation_reference_rejected_before_publication(self):
        summary = self.values[0]
        first, second = summary.replays
        for references in (("unrelated-evidence",), second.evidence_references):
            invalid = replace(summary, replays=(replace(first, evidence_references=references), second))
            with self.subTest(references=references), self.assertRaises(ValueError):
                self.retained.retain(self.terminal, (invalid,))
            self.assertFalse((self.retained.root / self.terminal.generation_id).exists())

    def test_rehashed_document_with_swapped_reference_is_rejected_on_read(self):
        self.retained.retain(self.terminal, self.values)
        root = self.retained.root / self.terminal.generation_id
        path = root / "treatment-0.json"
        document = json.loads(path.read_bytes())
        document["replays"][0]["evidence_references"] = document["replays"][1]["evidence_references"]
        raw = json.dumps(document).encode()
        path.write_bytes(raw)
        manifest = json.loads((root / "manifest.json").read_bytes())
        manifest["validations"][0]["sha256"] = digest(raw)
        raw_manifest = json.dumps(manifest).encode()
        (root / "manifest.json").write_bytes(raw_manifest)
        (root / "manifest.sha256").write_text(digest(raw_manifest))
        with self.assertRaises(ValueError):
            self.retained.read(self.terminal)


if __name__ == "__main__":
    unittest.main()
