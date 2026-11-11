"""Sealed archive run-history regression tests. Legacy trees are intentionally absent."""

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from AgMark.gui.application.history import discover_history, save_presentation
from AgMark.gui.application import history
from AgMark.gui.artifact_actions import artifact_actions
from AgMark.gui.projection.workspace.projector import WorkspaceData
from AgMark.gui.shell.projections import CurrentRunProjection, ExecutionBoundaryProjection, RunPlanProjection
from AgMark.gui.views import progress, results, reports, verification, artifacts
from AgMark.shared.runtime.artifacts.archive import (
    validate_archive, read_archive_member, archive_path,
)

from AgMark.shared.software_testing.validation.test_imported_run import seal_generation


class RunHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.root = self.repo / "AgMark" / "run_evidence"
        self.root.mkdir(parents=True)
        self.gid = "generation-saved-test"
        self.generation = self.root / self.gid
        self.generation.mkdir()
        self.observation = {
            "accepted_generation_id": self.gid, "observation_id": "one",
            "treatment_id": "control", "attempts": [], "terminal_status": "completed",
        }
        self.observation_path = self.generation / "observation-one" / "evidence.bin"
        self.observation_path.parent.mkdir()
        self.observation_path.write_text(json.dumps(self.observation))
        self.marker = self.root / ("." + self.gid + ".terminal")
        self.marker.write_text("accepted")
        self.archive = seal_generation(self.root, self.gid)
        current, pages = self._initial_presentation()
        save_presentation(self.root, self.gid, current, pages)

    def _initial_presentation(self):
        gid = self.gid
        ref = gid + "/observation-one/evidence.bin"
        digest = validate_archive(self.archive)["core_files"][ref]
        open_action, reveal_action = artifact_actions(self.root, gid, ref, digest)
        row = artifacts.ArtifactRowProjection(
            ref, "evidence.bin", "▤", ".json", "Retained", "•",
            digest, "123", open_action, reveal_action, reference=ref,
        )
        unavailable = "Saved run is read-only"
        noop = lambda: None
        current = CurrentRunProjection(
            gid, "Report ready (saved)", "success", "Saved",
            ExecutionBoundaryProjection("Example", "Runner", "Model", "Saved", "fingerprint"),
            RunPlanProjection("One treatment", "One observation", "Saved", "One run", "One file"),
            heading="Prior Run", is_prior_run=True,
        )
        pages = WorkspaceData(
            progress=progress.ProgressProjection(gid, gid, None, (), None, None, (),
                summary_empty_state="Saved run progress", treatment_empty_state=unavailable,
                run_stage_empty_state=unavailable),
            results=results.ResultsProjection(gid, (), "No scores"),
            reports=reports.ReportsProjection(gid,
                empty_state="Report not generated"),
            verification=verification.VerificationProjection(
                gid, verification.VerificationBannerProjection("unavailable", "—",
                    "Unavailable", unavailable, "neutral"),
                verification.VerificationSummaryProjection("Unavailable", "Unavailable",
                    "unavailable", "Unavailable", "Unavailable", "Unavailable",
                    "Unavailable", unavailable),
                checks_empty_state=unavailable),
            artifacts=artifacts.ArtifactsProjection(gid, (row,), "No evidence"),
        )
        return current, pages

    def test_reopen_is_read_only_and_never_invokes_provider(self):
        with patch("subprocess.Popen", side_effect=AssertionError("No provider execution")):
            run = discover_history(self.repo)[self.gid]
            current, workspace = run.presentation()
        self.assertEqual(current.state_label, "Report ready (saved)")
        self.assertFalse(current.start_benchmark_available)
        self.assertFalse(current.accept_plan_available)
        self.assertEqual(len(workspace.evidence.projection.artifacts.rows), 1)
        self.assertTrue(workspace.evidence.projection.artifacts.rows[0].open_action.available)

    def test_fresh_process_can_reopen_saved_projections(self):
        script = """from PySide6.QtWidgets import QApplication
from AgMark.gui.application.history import discover_history
import sys
app=QApplication([])
run=discover_history(sys.argv[1])[sys.argv[2]]
current, workspace=run.presentation()
assert current.is_prior_run
assert len(workspace.evidence.projection.artifacts.rows)==1
print(current.run_identity)
"""
        proc = subprocess.run([sys.executable, "-c", script, str(self.repo), self.gid],
                              cwd=Path(__file__).resolve().parents[5],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(self.gid, proc.stdout)

    def test_report_and_verification_snapshot_revisions(self):
        from AgMark.gui.views.reports import ReportsView
        from AgMark.gui.views.verification import VerificationView
        current, workspace = discover_history(self.repo)[self.gid].presentation()
        updated_report = replace(workspace.reports.projection,
            report_id="report-fixture", readable_content="Saved report",
            generation_state="generated", empty_state=None)
        updated_verification = replace(workspace.verification.projection,
            summary=replace(workspace.verification.projection.summary, notes="Verification saved"))
        workspace = replace(workspace, reports=ReportsView(updated_report),
                            verification=VerificationView(updated_verification))
        previous = validate_archive(self.archive)
        save_presentation(self.root, self.gid, current, workspace)
        manifest = validate_archive(self.archive)
        self.assertEqual(manifest["core_sha256"], previous["core_sha256"])
        reopened = discover_history(self.repo)[self.gid].presentation()[1]
        self.assertEqual(reopened.reports.projection.readable_content, "# Exact retained report\n")
        self.assertNotEqual(reopened.verification.projection.summary.notes, "Verification saved")
        self.assertNotIn("history/presentation.json", manifest["files"])

    def test_tampered_archive_fails_without_fallback(self):
        with ZipFile(self.archive, "a") as zipfile:
            zipfile.writestr("unexpected-file.txt", "tampered")
        self.assertEqual(discover_history(self.repo)[self.gid].state_label, "Evidence changed")
        with self.assertRaises(ValueError):
            discover_history(self.repo)[self.gid].presentation()

    def test_deleted_archive_is_not_reopened_or_reused(self):
        run = discover_history(self.repo)[self.gid]
        current, pages = self._initial_presentation()
        run.delete()
        self.assertFalse(self.archive.exists())
        self.assertTrue((self.root / ("." + self.gid + ".deleted")).exists())
        self.assertEqual(discover_history(self.repo), {})
        with self.assertRaises(ValueError):
            save_presentation(self.root, self.gid, current, pages)

    def test_imported_archive_without_gui_snapshot_is_read_only_inspectable(self):
        gid = "generation-no-gui-snapshot"
        folder = self.root / gid
        folder.mkdir()
        (folder / "evidence.bin").write_text(
            json.dumps({"accepted_generation_id": gid, "terminal_status": "completed"})
        )
        (self.root / ("." + gid + ".terminal")).write_text("accepted")
        seal_generation(self.root, gid)
        run = discover_history(self.repo)[gid]
        current, projection = run.prepare_presentation()
        self.assertTrue(current.is_prior_run)
        self.assertFalse(current.start_benchmark_available)
        self.assertEqual(len(projection.artifacts.rows), 1)
        self.assertTrue(projection.artifacts.rows[0].open_action.available)
        self.assertIn("no rescore", projection.results.empty_state)
        self.assertEqual(projection.progress.treatments, ())
        self.assertEqual(projection.progress.treatment_empty_state,
                         "Treatment progress is unavailable in this read-only archive view.")

    def test_archive_has_no_per_benchmark_evidence_directories(self):
        self.assertFalse(self.generation.exists())
        self.assertFalse((self.repo / "AgMark" / "Example" / "evidence").exists())
        self.assertTrue(self.archive.is_file())


if __name__ == "__main__":
    unittest.main()
