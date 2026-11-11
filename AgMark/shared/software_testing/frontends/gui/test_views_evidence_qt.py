"""Combined evidence navigation, live updates, identity and saved history."""

import json
import os
from dataclasses import replace
from hashlib import sha256
from threading import Thread
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from AgMark.gui.application.history import _encode, _decode
from AgMark.gui.projection.workspace.activity import _source_projection, with_activity
from AgMark.gui.projection.workspace.artifacts import _artifacts_projection
from AgMark.gui.projection.workspace.projector import SharedWorkspaceProjector
from AgMark.gui.shell.preferences import _stored_tab_index
from AgMark.gui.shell.projections import WORKSPACE_TAB_LABELS
from AgMark.gui.shell.window import BenchmarkShellWindow
from AgMark.gui.views.artifacts import ArtifactActionProjection, ArtifactRowProjection, ArtifactsProjection
from AgMark.gui.views.evidence import EvidenceProjection, EvidenceView
from AgMark.shared.runtime.artifacts import ArtifactRecord
from AgMark.shared.runtime.orchestration.activity import CaptureSourceActivity, RunActivity
from AgMark.shared.software_testing.frontends.gui.test_retained_evidence_projection import (
    _accepted_run, _active_plan, _active_progress_projection,
)


GENERATION = "generation-evidence"


def _capture():
    progress = _active_progress_projection(GENERATION, _active_plan())
    event = RunActivity(GENERATION, 1, "capture", 1, sources=(
        CaptureSourceActivity("stdout", "partial", received_events=4, received_bytes=123,
                              dropped=1, scope="original", treatment_id="control", invocation_id="observation-one"),
        CaptureSourceActivity("process", "settled", scope="original", treatment_id="control", invocation_id="observation-one"),
        CaptureSourceActivity("otel_logs", "failed", reason="collector_failed", scope="original", treatment_id="control", invocation_id="observation-two"),
        CaptureSourceActivity("stdout", "settled", scope="replay", treatment_id="control", invocation_id="observation-one"),
    ))
    return replace(with_activity(progress, event, 1),
                   capture_sources=tuple(_source_projection(source) for source in event.sources),
                   capture_summary=None)


def _artifact(identity="observation-file", *, linked=True, operation=lambda: None, available=True):
    action = ArtifactActionProjection(operation, available, None if available else "File is unavailable")
    return ArtifactRowProjection(identity, identity + ".json", "▣", "application/json", "retained", "•",
        "sha256:" + "a" * 64, "123 bytes", action, action, reference=GENERATION + "/" + identity + ".json",
        capture_invocation_ids=("observation-one",) if linked else (), capture_scope="original" if linked else None)


class EvidenceViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def view(self, artifacts=None):
        view = EvidenceView(EvidenceProjection(_capture(), artifacts or ArtifactsProjection(
            GENERATION, (_artifact(), _artifact("report", linked=False)))))
        self.addCleanup(view.deleteLater)
        view.resize(900, 650)
        view.show()
        self.app.processEvents()
        return view

    def source_item(self, view, source):
        return view._items[view._source_key(source)]

    def test_sources_share_files_without_linking_failed_or_replay_sources_by_name(self):
        view = self.view()
        sources = view.projection.capture.capture_sources
        self.assertEqual(1, self.source_item(view, sources[0]).childCount())
        self.assertEqual(1, self.source_item(view, sources[1]).childCount())
        self.assertEqual(0, self.source_item(view, sources[2]).childCount())
        self.assertEqual("failed", self.source_item(view, sources[2]).text(1))
        self.assertEqual(0, self.source_item(view, sources[3]).childCount())
        self.assertEqual("Other artifacts", view._items[("other",)].text(0))
        self.assertEqual(1, view._items[("other",)].childCount())
        source = self.source_item(view, sources[0])
        self.assertIn("Dropped 1", source.text(4))
        self.assertEqual("retained", source.child(0).text(5))
        view.tree.setCurrentItem(source)
        self.assertIn("Capture state: partial", view.details.text())
        view.tree.setCurrentItem(source.child(0))
        self.assertIn("File status: retained", view.details.text())
        self.assertIn("sha256:" + "a" * 64, view.details.text())

    def test_multiple_linked_files_and_actions_keep_caller_availability(self):
        calls = []
        artifacts = ArtifactsProjection(GENERATION, (
            _artifact(operation=lambda: calls.append("open")),
            _artifact("unavailable", available=False),
        ))
        view = self.view(artifacts)
        source = self.source_item(view, view.projection.capture.capture_sources[0])
        self.assertEqual(2, source.childCount())
        view.tree.setCurrentItem(source.child(0))
        view.open_button.click()
        self.assertEqual(["open"], calls)
        view.tree.setCurrentItem(source.child(1))
        self.assertFalse(view.open_button.isEnabled())
        self.assertFalse(view.reveal_button.isEnabled())
        view.open_button.click()
        self.assertEqual(["open"], calls)

    def test_live_updates_preserve_selection_expansion_width_and_file_actions(self):
        view = self.view()
        source = self.source_item(view, view.projection.capture.capture_sources[0])
        source.setExpanded(True)
        file = source.child(0)
        view.tree.setCurrentItem(file)
        button = view.open_button
        view.tree.setColumnWidth(0, 411)
        for count in range(5, 15):
            capture = view.projection.capture
            view.set_capture_projection(replace(capture, capture_sources=(
                replace(capture.capture_sources[0], events=str(count)), *capture.capture_sources[1:])))
        self.assertIs(file, view.tree.currentItem())
        self.assertIs(button, view.open_button)
        self.assertTrue(source.isExpanded())
        self.assertEqual(411, view.tree.columnWidth(0))
        self.assertEqual("14", source.text(2))
        old = view.projection
        view.set_capture_projection(replace(old.capture, run_id="generation-stale", generation_id="generation-stale"))
        self.assertIs(old, view.projection)
        view.set_capture_projection(replace(old.capture, generation_id="generation-stale"))
        self.assertIs(old, view.projection)

    def test_worker_capture_updates_are_queued_and_wrong_run_ignored(self):
        view = self.view()
        previous = view.projection.capture
        source = replace(previous.capture_sources[0], events="8")
        capture = replace(previous, capture_sources=(source, *previous.capture_sources[1:]))
        thread = Thread(target=lambda: view.set_capture_projection(capture))
        thread.start()
        thread.join(2)
        self.app.processEvents()
        self.assertEqual(capture, view.projection.capture)
        self.assertEqual("8", self.source_item(view, source).text(2))

    def test_repeated_attempt_labels_keep_distinct_invocations(self):
        view = self.view()
        source = view.projection.capture.capture_sources[0]
        first = replace(source, attempt_id="attempt-1", capture="Original Run / control / attempt-1")
        second = replace(first, invocation_id="observation-two", events="9")
        view.set_capture_projection(replace(view.projection.capture, capture_sources=(first, second)))
        self.assertEqual(1, self.source_item(view, first).childCount())
        self.assertEqual(0, self.source_item(view, second).childCount())
        self.assertEqual("4", self.source_item(view, first).text(2))
        self.assertEqual("9", self.source_item(view, second).text(2))

    def test_small_workspace_keeps_tree_and_file_actions_reachable(self):
        from AgMark.gui.shell.window import _TabContentScrollArea
        view = self.view()
        scroll = _TabContentScrollArea()
        self.addCleanup(scroll.deleteLater)
        scroll.setWidgetResizable(True)
        scroll.setWidget(view)
        scroll.show()
        source = self.source_item(view, view.projection.capture.capture_sources[0])
        view.tree.setCurrentItem(source.child(0))
        for width, height in ((560, 320), (1100, 700), (560, 320)):
            scroll.resize(width, height)
            for _ in range(4):
                self.app.processEvents()
            self.assertGreaterEqual(view.tree.height(), 260)
            self.assertLessEqual(view.tree.width(), view.width())
            self.assertFalse(view.actions.isHidden())
            self.assertLessEqual(view.actions.geometry().bottom(), view.height())
            self.assertEqual(0, scroll.horizontalScrollBar().maximum())

    def test_empty_files_do_not_hide_failed_sources_and_no_capture_does_not_hide_files(self):
        view = self.view(ArtifactsProjection(GENERATION, empty_state="No files were retained."))
        self.assertFalse(view.tree.isHidden())
        self.assertIn("No files were retained", view.retention_label.text())
        view.set_projection(EvidenceProjection(replace(_capture(), capture_sources=()),
            ArtifactsProjection(GENERATION, (_artifact("report", linked=False),))))
        self.assertEqual("Saved artifacts", view._items[("other",)].text(0))
        self.assertEqual(1, view._items[("other",)].childCount())

    def test_history_roundtrip_preserves_links_and_accepts_older_projection_fields(self):
        capture = _capture()
        artifacts = ArtifactsProjection(GENERATION, (_artifact(),))
        restored = EvidenceProjection(_decode(_encode(capture)), _decode(_encode(artifacts)))
        view = EvidenceView(restored)
        self.addCleanup(view.deleteLater)
        self.assertEqual(1, self.source_item(view, restored.capture.capture_sources[0]).childCount())
        old_source = _encode(capture.capture_sources[0])
        for name in ("scope", "invocation_id", "treatment_id", "attempt_id"):
            old_source["fields"].pop(name)
        self.assertIsNone(_decode(old_source).invocation_id)
        old_file = _encode(artifacts.rows[0])
        old_file["fields"].pop("capture_invocation_ids")
        old_file["fields"].pop("capture_scope")
        self.assertEqual((), _decode(old_file).capture_invocation_ids)

    def test_projection_rejects_mixed_run_data(self):
        with self.assertRaisesRegex(ValueError, "same run"):
            EvidenceProjection(_capture(), ArtifactsProjection("generation-other", empty_state="None"))

    def test_exact_observation_bytes_link_to_original_capture_only(self):
        raw = json.dumps({"observation_id": "observation-one", "treatment_id": "control"}).encode()
        terminal = _accepted_run(raw_observations=(raw,), generation_id=GENERATION)
        record = ArtifactRecord("observation-one.observation", "treatment_observation",
            GENERATION + "/observation.json", "sha256:" + sha256(raw).hexdigest(), "test")
        object.__setattr__(terminal, "artifact_index", SimpleNamespace(artifacts=(record,)))
        projection = _artifacts_projection(terminal, None, None)
        self.assertEqual(("observation-one",), projection.rows[0].capture_invocation_ids)
        self.assertEqual("original", projection.rows[0].capture_scope)
        self.assertEqual(f"{len(raw)} bytes", projection.rows[0].size)
        object.__setattr__(terminal, "artifact_index", SimpleNamespace(artifacts=(replace(record, sha256="sha256:" + "b" * 64),)))
        self.assertEqual((), _artifacts_projection(terminal, None, None).rows[0].capture_invocation_ids)

    def test_shell_has_one_evidence_tab_in_scored_and_unscored_runs(self):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.black)
        window = BenchmarkShellWindow(application_icon=QIcon(pixmap))
        self.addCleanup(window.deleteLater)
        projector = SharedWorkspaceProjector(None)
        workspace = projector.active_execution(GENERATION, _active_plan())
        window.set_workspace_projection(workspace, run_id=GENERATION)
        self.assertEqual(("Progress", "Scoring", "Results", "Evidence", "Verification", "Reports"), window.workspace_tabs.labels)
        self.assertIs(workspace.evidence, window.workspace_pages["Evidence"])
        window.workspace_tabs.setCurrentIndex(WORKSPACE_TAB_LABELS.index("Evidence"))
        unscored_results = replace(workspace.results.projection, unscored=True)
        workspace.results.set_projection(unscored_results)
        workspace.scoring.set_projection(unscored_results)
        window.set_workspace_projection(workspace, run_id=GENERATION)
        for index, label in enumerate(WORKSPACE_TAB_LABELS):
            self.assertEqual(label in {"Progress", "Scoring", "Results", "Evidence"}, window.workspace_tabs.isTabVisible(index))
        self.assertNotIn("score", [column.key for column in window.workspace_pages["Scoring"].table.columns])
        window.clear_workspace_projection()
        self.assertEqual("Evidence", window.workspace_tabs.selected_label)
        self.assertEqual("unavailable", window.workspace_pages["Evidence"].property("projectionState"))

    def test_old_tab_preferences_open_evidence(self):
        for label in ("Capture", "Artifacts", "Evidence", 4):
            self.assertEqual(WORKSPACE_TAB_LABELS.index("Evidence"), _stored_tab_index({"tab": label}, "tab"))


if __name__ == "__main__":
    unittest.main()
