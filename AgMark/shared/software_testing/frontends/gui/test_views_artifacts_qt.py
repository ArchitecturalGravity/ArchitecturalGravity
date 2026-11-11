"""Concrete PySide6 conformance tests for the Artifacts workspace view."""

from __future__ import annotations

import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.views.artifacts import (
    ARTIFACTS_COLUMNS,
    PYSIDE6_AVAILABLE,
    STATUS_SEMANTICS_ROLE,
    ArtifactActionProjection,
    ArtifactRowProjection,
    ArtifactsProjection,
    ArtifactsView,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication


def _row(
    *,
    artifact_id: str = "artifact-1",
    artifact: str = "Evidence Bundle",
    status: str = "Available",
    integrity_hash: str = "a" * 64,
    open_available: bool = True,
    reveal_available: bool = True,
    calls: list[str] | None = None,
) -> ArtifactRowProjection:
    recorded = calls if calls is not None else []
    return ArtifactRowProjection(
        artifact_id=artifact_id,
        artifact=artifact,
        artifact_icon="▣",
        artifact_type="Bundle",
        status=status,
        status_icon="✓",
        status_semantics="success",
        integrity_hash=integrity_hash,
        size="42 KB",
        open_action=ArtifactActionProjection(
            lambda: recorded.append(f"open:{artifact_id}"),
            available=open_available,
            unavailable_reason=None if open_available else "Safe open is unavailable",
        ),
        reveal_action=ArtifactActionProjection(
            lambda: recorded.append(f"reveal:{artifact_id}"),
            available=reveal_available,
            unavailable_reason=None if reveal_available else "Safe reveal is unavailable",
        ),
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ArtifactsViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_default_composition_preserves_exact_columns_metadata_and_actions(self) -> None:
        calls: list[str] = []
        row = _row(reveal_available=False, calls=calls)
        view = ArtifactsView(
            ArtifactsProjection(
                run_id="run-retained",
                rows=(row,),
            )
        )
        self.addCleanup(view.deleteLater)

        self.assertEqual(
            tuple(column.label for column in ARTIFACTS_COLUMNS),
            (
                "Artifact",
                "Type",
                "Status",
                "Integrity Hash (SHA256)",
                "Size",
                "Actions",
            ),
        )
        self.assertEqual(
            tuple(column.label for column in view.table.columns),
            (
                "Artifact",
                "Type",
                "Status",
                "Integrity Hash (SHA256)",
                "Size",
                "Actions",
            ),
        )
        self.assertEqual(view.run_id, "run-retained")
        self.assertEqual(view.authority_semantics, "presentation-only")

        model = view.table.table_model
        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(model.columnCount(), 6)
        self.assertEqual(
            model.data(model.index(0, 0), int(Qt.ItemDataRole.DisplayRole)),
            "▣ Evidence Bundle",
        )
        self.assertEqual(
            model.data(model.index(0, 2), int(Qt.ItemDataRole.DisplayRole)),
            "✓ Available",
        )
        self.assertEqual(
            model.data(model.index(0, 2), STATUS_SEMANTICS_ROLE),
            "success",
        )
        self.assertEqual(
            model.data(model.index(0, 3), int(Qt.ItemDataRole.DisplayRole)),
            "a" * 64,
        )

        open_button, reveal_button = view.action_buttons["artifact-1"]
        self.assertEqual(open_button.displayed_label, "Open")
        self.assertEqual(reveal_button.displayed_label, "Reveal")
        self.assertTrue(open_button.isEnabled())
        self.assertFalse(reveal_button.isEnabled())

        open_button.click()
        reveal_button.click()
        self.assertEqual(calls, ["open:artifact-1"])

    def test_visible_status_or_hash_never_infers_safe_access(self) -> None:
        calls: list[str] = []
        row = _row(
            status="Verified",
            integrity_hash="f" * 64,
            open_available=False,
            reveal_available=False,
            calls=calls,
        )
        view = ArtifactsView(
            ArtifactsProjection(run_id="run-blocked", rows=(row,))
        )
        self.addCleanup(view.deleteLater)

        open_button, reveal_button = view.action_buttons["artifact-1"]
        self.assertFalse(open_button.isEnabled())
        self.assertFalse(reveal_button.isEnabled())
        open_button.click()
        reveal_button.click()
        self.assertEqual(calls, [])

    def test_empty_and_partial_state_is_explicit_and_does_not_invent_rows(self) -> None:
        view = ArtifactsView(
            ArtifactsProjection(
                run_id="run-pending",
                rows=(),
                empty_state="Artifacts not yet retained",
            )
        )
        self.addCleanup(view.deleteLater)

        self.assertEqual(view.table.table_model.rowCount(), 0)
        self.assertTrue(view.table.isHidden())
        self.assertFalse(view.empty_state_label.isHidden())
        self.assertEqual(
            view.empty_state_label.text(),
            "Artifacts not yet retained",
        )

        view.set_projection(
            ArtifactsProjection(
                run_id="run-partial",
                rows=(
                    _row(
                        artifact_id="artifact-missing",
                        artifact="Raw Response",
                        status="Missing",
                        integrity_hash="—",
                        open_available=False,
                        reveal_available=False,
                    ),
                ),
            )
        )
        self.assertEqual(view.run_id, "run-partial")
        self.assertFalse(view.table.isHidden())
        self.assertTrue(view.empty_state_label.isHidden())
        model = view.table.table_model
        self.assertEqual(
            model.data(model.index(0, 2), int(Qt.ItemDataRole.DisplayRole)),
            "✓ Missing",
        )
        self.assertEqual(
            model.data(model.index(0, 3), int(Qt.ItemDataRole.DisplayRole)),
            "—",
        )

    def test_invalid_projection_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit caller-supplied empty_state"):
            ArtifactsProjection(run_id="run-empty")

        duplicate = _row()
        with self.assertRaisesRegex(ValueError, "artifact_id values must be unique"):
            ArtifactsProjection(
                run_id="run-duplicate",
                rows=(duplicate, duplicate),
            )

        with self.assertRaisesRegex(
            ValueError,
            "unavailable_reason requires available=False",
        ):
            ArtifactActionProjection(
                lambda: None,
                available=True,
                unavailable_reason="Contradictory state",
            )

        with self.assertRaisesRegex(ValueError, "open_action"):
            ArtifactRowProjection(
                artifact_id="artifact-invalid",
                artifact="Logs",
                artifact_icon="▣",
                artifact_type="Log",
                status="Available",
                status_icon="✓",
                integrity_hash="b" * 64,
                size="1 KB",
                open_action=object(),  # type: ignore[arg-type]
                reveal_action=ArtifactActionProjection(lambda: None, available=True),
            )

    def test_worker_projection_updates_are_queued_to_the_gui_thread(self) -> None:
        view = ArtifactsView(
            ArtifactsProjection(
                run_id="run-a",
                rows=(_row(artifact_id="artifact-a"),),
            )
        )
        self.addCleanup(view.deleteLater)

        next_projection = ArtifactsProjection(
            run_id="run-b",
            rows=(
                _row(
                    artifact_id="artifact-b",
                    artifact="Verification Manifest",
                    status="Unavailable",
                    integrity_hash="—",
                    open_available=False,
                    reveal_available=False,
                ),
            ),
        )
        worker = threading.Thread(
            target=view.set_projection,
            args=(next_projection,),
        )
        worker.start()
        worker.join()
        QApplication.processEvents()

        self.assertEqual(view.run_id, "run-b")
        self.assertNotIn("artifact-a", view.action_buttons)
        self.assertIn("artifact-b", view.action_buttons)
        model = view.table.table_model
        self.assertEqual(
            model.data(model.index(0, 0), int(Qt.ItemDataRole.DisplayRole)),
            "▣ Verification Manifest",
        )
        self.assertEqual(
            model.data(model.index(0, 2), int(Qt.ItemDataRole.DisplayRole)),
            "✓ Unavailable",
        )


if __name__ == "__main__":
    unittest.main()
