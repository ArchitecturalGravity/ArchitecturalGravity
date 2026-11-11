"""Concrete PySide6 conformance tests for the Verification workspace view."""

from __future__ import annotations

import os
from dataclasses import replace
import threading
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.views.verification import (
    PYSIDE6_AVAILABLE,
    VERIFICATION_CHECK_LABELS,
    VERIFICATION_SUMMARY_FIELDS,
    VerificationBannerProjection,
    VerificationCheckProjection,
    VerificationProjection,
    VerificationSummaryProjection,
    VerificationView,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel, QWidget
    from AgMark.gui.shell.window import BenchmarkShellWindow


def _checks(
    *,
    artifact_result: str = "Verified",
    artifact_tone: str = "success",
) -> tuple[VerificationCheckProjection, ...]:
    rows = (
        ("manifest", "Manifest Integrity", "Verified", "✓", "success"),
        ("artifacts", "Artifact Hashes", artifact_result, "✓", artifact_tone),
        ("boundary", "Boundary Match", "Matched", "✓", "success"),
        ("reconstruction", "Reconstruction Match", "Matched", "✓", "success"),
    )
    return tuple(
        VerificationCheckProjection(
            check_id=check_id,
            label=label,
            result=result,
            icon=icon,
            tone=tone,
            details=f"{label} details supplied by retained verification evidence.",
        )
        for check_id, label, result, icon, tone in rows
    )


def _summary(
    *,
    result: str = "Verified",
    notes: str = "Exact retained reconstruction verified.",
) -> VerificationSummaryProjection:
    return VerificationSummaryProjection(
        manifest_id="manifest-verified-001",
        verification_time="2026-09-21 18:00",
        result=result,
        verified_by="arcgrav.shared.verifier@1.0.0",
        artifacts_checked="7",
        total_size="18.4 MB",
        boundary_fingerprint="sha256:boundary",
        notes=notes,
    )


def _projection(
    *,
    run_id: str = "run-retained",
    checks: tuple[VerificationCheckProjection, ...] | None = None,
    checks_empty_state: str | None = None,
    artifact_result: str = "Verified",
    artifact_tone: str = "success",
) -> VerificationProjection:
    if checks is None:
        checks = _checks(
            artifact_result=artifact_result,
            artifact_tone=artifact_tone,
        )
    return VerificationProjection(
        run_id=run_id,
        banner=VerificationBannerProjection(
            status="verified",
            icon="✓",
            heading="Verified",
            summary="Exact retained report reconstruction matches.",
            tone="success",
        ),
        summary=_summary(),
        
        checks=checks,
        checks_empty_state=checks_empty_state,
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class VerificationViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_completion_hides_absent_notes_and_restores_later_details(self) -> None:
        original = _projection()
        completed = replace(
            original,
            banner=VerificationBannerProjection(
                "passed", "✓", "Completion validation passed", None, "success",
            ),
            summary=replace(original.summary, notes=None),
            checks=(),
            checks_empty_state=None,
        )
        view = VerificationView(original)
        self.addCleanup(view.deleteLater)
        for _ in range(2):
            view.set_projection(completed)
            self.assertEqual(view.banner_heading_label.text(), "Completion validation passed")
            self.assertTrue(view.banner_summary_label.isHidden())
            self.assertEqual(view.banner_summary_label.text(), "")
            self.assertEqual(view.banner_frame.accessibleName(), "Completion validation passed")
            self.assertTrue(view._summary_value_labels["notes"].parentWidget().isHidden())
            self.assertEqual(view._summary_value_labels["notes"].text(), "")
            self.assertTrue(view.checks_empty_state_label.isHidden())
            self.assertTrue(view.checks_holder.isHidden())
            view.set_projection(original)
            self.assertFalse(view.banner_summary_label.isHidden())
            self.assertEqual(view.banner_summary_label.text(), original.banner.summary)
            self.assertFalse(view._summary_value_labels["notes"].parentWidget().isHidden())
            self.assertEqual(view._summary_value_labels["notes"].text(), original.summary.notes)
            self.assertFalse(view.checks_holder.isHidden())

    def test_summary_rows_are_compact_and_grow_only_for_wrapped_text(self) -> None:
        original = _projection()
        view = VerificationView(original)
        self.addCleanup(view.deleteLater)
        view.resize(1200, 700)
        view.show()
        self.addCleanup(view.close)
        for _ in range(5):
            self._application.processEvents()

        rows = [value.parentWidget() for value in view._summary_value_labels.values()]
        result = view._summary_value_labels["result"]
        self.assertEqual(result.parentWidget().height(), result.sizeHint().height())
        for previous, current in zip(rows, rows[1:]):
            self.assertEqual(current.y() - previous.geometry().bottom() - 1, 2)

        long_notes = "Retained evidence remains available for inspection. " * 12
        for width in (600, 1200, 600):
            view.resize(width, 900)
            view.set_projection(replace(original, summary=replace(original.summary, notes=long_notes)))
            for _ in range(5):
                self._application.processEvents()
            notes = view._summary_value_labels["notes"]
            self.assertGreater(notes.height(), notes.fontMetrics().height())
            self.assertGreaterEqual(notes.height(), notes.heightForWidth(notes.width()))
            self.assertEqual(notes.text(), long_notes)
            self.assertTrue(notes.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByKeyboard)
            self.assertTrue(notes.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse)

            view.set_projection(replace(original, summary=replace(original.summary, notes=None)))
            for _ in range(5):
                self._application.processEvents()
            self.assertTrue(notes.parentWidget().isHidden())
            self.assertEqual(notes.text(), "")
            view.set_projection(original)
            for _ in range(5):
                self._application.processEvents()
            self.assertFalse(notes.parentWidget().isHidden())
            self.assertEqual(result.parentWidget().height(), result.sizeHint().height())

    def test_both_cards_reflow_in_real_tab_scroll_container(self) -> None:
        original = _projection()
        text = "Retained evidence is available for inspection. " * 16
        fingerprint = "sha256:" + "abcdef0123456789" * 16
        projection = replace(
            original,
            banner=replace(original.banner, summary=text),
            summary=replace(original.summary, notes=text, boundary_fingerprint=fingerprint),
            checks=tuple(replace(check, details=text, expanded=True) for check in original.checks),
        )
        view = VerificationView(projection)
        parent = QWidget()
        scroll = BenchmarkShellWindow._wrap_workspace_page(
            SimpleNamespace(workspace=parent), "Verification", view,
        )
        scroll.setParent(None)
        self.addCleanup(parent.deleteLater)
        self.addCleanup(scroll.deleteLater)
        self.addCleanup(scroll.close)
        scroll.show()
        for width in (320, 420, 600, 850, 1000, 1600, 320):
            scroll.resize(width, 480)
            for _ in range(20):
                self._application.processEvents()
            self.assertEqual(scroll.width(), width)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            self.assertLessEqual(view.width(), scroll.viewport().width())
            for card in (view.status_card, view.summary_card):
                self.assertTrue(view.rect().contains(card.geometry()))
            if view.width() < 850:
                self.assertGreater(view.summary_card.y(), view.status_card.geometry().bottom())
            else:
                self.assertGreater(view.summary_card.x(), view.status_card.geometry().right())
            for label in view.findChildren(QLabel):
                if label.isVisible() and label.wordWrap():
                    self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()), label.objectName())
            for value in view._summary_value_labels.values():
                self.assertGreaterEqual(value.height(), value.heightForWidth(value.width()), value.objectName())
                self.assertEqual(value.verticalScrollBar().maximum(), 0, value.objectName())
                self.assertEqual(value.horizontalScrollBar().maximum(), 0, value.objectName())
            self.assertEqual(view._summary_value_labels["boundary_fingerprint"].text(), fingerprint)
            self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            notes = view._summary_value_labels["notes"]
            self.assertLessEqual(notes.mapTo(scroll.viewport(), notes.rect().bottomRight()).y(), scroll.viewport().height())

    def test_summary_preserves_literal_text_and_exact_copy(self) -> None:
        projection = _projection()
        text = "<not markup> & sha256:" + "abc123" * 80
        view = VerificationView(replace(projection, summary=replace(projection.summary, notes=text)))
        self.addCleanup(view.deleteLater)
        notes = view._summary_value_labels["notes"]
        notes.selectAll()
        self.assertEqual(notes.text(), text)
        self.assertEqual(notes.textCursor().selectedText(), text)
        self.assertGreater(notes.heightForWidth(200), notes.heightForWidth(800))

    def test_default_composition_preserves_exact_cards_checks_summary(self) -> None:
        view = VerificationView(_projection())
        self.addCleanup(view.deleteLater)

        self.assertEqual(view.status_card.title, "Verification Status")
        self.assertEqual(view.summary_card.title, "Verification Summary")
        self.assertEqual(view.banner_heading_label.text(), "Verified")
        self.assertEqual(view.banner_icon_label.text(), "✓")
        self.assertEqual(
            view.banner_summary_label.text(),
            "Exact retained report reconstruction matches.",
        )
        self.assertEqual(
            view.banner_frame.property("verificationStatus"),
            "verified",
        )
        self.assertEqual(view.banner_frame.property("semanticTone"), "success")
        self.assertEqual(view.check_order, VERIFICATION_CHECK_LABELS)
        self.assertNotIn("Claim Readiness", view.check_order)
        self.assertEqual(
            view.summary_labels,
            tuple(label for _, label in VERIFICATION_SUMMARY_FIELDS),
        )
        self.assertEqual(
            dict(view.summary_values),
            {
                "manifest_id": "manifest-verified-001",
                "verification_time": "2026-09-21 18:00",
                "result": "Verified",
                "verified_by": "arcgrav.shared.verifier@1.0.0",
                "artifacts_checked": "7",
                "total_size": "18.4 MB",
                "boundary_fingerprint": "sha256:boundary",
                "notes": "Exact retained reconstruction verified.",
            },
        )
        self.assertEqual(view.run_id, "run-retained")
        self.assertEqual(view.authority_semantics, "presentation-only")

    def test_verified_reconstruction_preserves_unavailable_artifacts(self) -> None:
        view = VerificationView(
            _projection(
                artifact_result="Unavailable",
                artifact_tone="warning",
            )
        )
        self.addCleanup(view.deleteLater)

        self.assertEqual(view.banner_heading_label.text(), "Verified")
        self.assertEqual(
            view.check_result_labels["artifacts"].text(),
            "Unavailable",
        )
        self.assertEqual(
            view.check_result_labels["artifacts"].property("semanticTone"),
            "warning",
        )

    def test_disclosure_rows_are_keyboard_reachable_and_preserve_supplied_details(self) -> None:
        view = VerificationView(_projection())
        self.addCleanup(view.deleteLater)

        button = view.check_disclosure_buttons["manifest"]
        details = view.check_details_labels["manifest"]
        self.assertEqual(
            button.focusPolicy(),
            Qt.FocusPolicy.StrongFocus,
        )
        self.assertEqual(
            button.accessibleName(),
            "Details for Manifest Integrity",
        )
        self.assertTrue(details.isHidden())
        self.assertIn("Manifest Integrity details", details.text())

        button.click()
        self.assertFalse(details.isHidden())
        self.assertEqual(button.property("expanded"), True)

        button.click()
        self.assertTrue(details.isHidden())
        self.assertEqual(button.property("expanded"), False)

    def test_status_cues_are_textual_and_accessible_in_addition_to_color(self) -> None:
        view = VerificationView(
            _projection(
                artifact_result="Unavailable",
                artifact_tone="warning",
            )
        )
        self.addCleanup(view.deleteLater)

        self.assertEqual(
            view.banner_frame.accessibleName(),
            "Verified: Exact retained report reconstruction matches.",
        )
        self.assertEqual(view.banner_heading_label.text(), "Verified")
        self.assertEqual(view.banner_icon_label.text(), "✓")

        icons = view.findChildren(
            type(view.banner_icon_label),
            "verificationCheckIcon",
        )
        self.assertEqual(
            tuple(icon.accessibleName() for icon in icons),
            tuple(f"{label} status cue" for label in VERIFICATION_CHECK_LABELS),
        )
        self.assertTrue(all(icon.text() for icon in icons))

        artifact_result = view.check_result_labels["artifacts"]
        self.assertEqual(artifact_result.text(), "Unavailable")
        self.assertEqual(artifact_result.accessibleName(), "Artifact Hashes result")
        self.assertEqual(artifact_result.property("semanticTone"), "warning")

    def test_empty_and_partial_check_states_are_explicit(self) -> None:
        empty = VerificationView(
            _projection(
                run_id="run-pending",
                checks=(),
                checks_empty_state="Verification checks are not yet available",
            )
        )
        self.addCleanup(empty.deleteLater)

        self.assertTrue(empty.checks_holder.isHidden())
        self.assertFalse(empty.checks_empty_state_label.isHidden())
        self.assertEqual(
            empty.checks_empty_state_label.text(),
            "Verification checks are not yet available",
        )

        partial_checks = (
            VerificationCheckProjection(
                check_id="manifest",
                label="Manifest Integrity",
                result="Unavailable",
                icon="!",
                tone="warning",
                details="Manifest verification input is unavailable.",
            ),
            VerificationCheckProjection(
                check_id="artifacts",
                label="Artifact Hashes",
                result="Unavailable",
                icon="!",
                tone="warning",
                details="Artifact hash verification input is unavailable.",
            ),
        )
        empty.set_projection(
            _projection(
                run_id="run-partial",
                checks=partial_checks,
            )
        )

        self.assertEqual(empty.run_id, "run-partial")
        self.assertFalse(empty.checks_holder.isHidden())
        self.assertTrue(empty.checks_empty_state_label.isHidden())
        self.assertEqual(
            empty.check_order,
            ("Manifest Integrity", "Artifact Hashes"),
        )

    def test_invalid_projection_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "verified status requires",
        ):
            VerificationBannerProjection(
                status="verified",
                icon="✓",
                heading="Complete",
                summary="Looks successful",
                tone="success",
            )

        with self.assertRaisesRegex(
            ValueError,
            "non-verified status cannot use",
        ):
            VerificationBannerProjection(
                status="incomplete",
                icon="!",
                heading="Verified",
                summary="Incomplete verification",
                tone="success",
            )

        with self.assertRaisesRegex(
            ValueError,
            "explicit caller-supplied checks_empty_state",
        ):
            _projection(checks=())

        duplicate = _checks()[0]
        with self.assertRaisesRegex(ValueError, "check_id values must be unique"):
            _projection(checks=(duplicate, duplicate))

        reversed_defaults = (
            VerificationCheckProjection(
                check_id="boundary",
                label="Boundary Match",
                result="Matched",
                icon="✓",
                tone="success",
                details="Boundary matched.",
            ),
            VerificationCheckProjection(
                check_id="manifest",
                label="Manifest Integrity",
                result="Verified",
                icon="✓",
                tone="success",
                details="Manifest verified.",
            ),
        )
        with self.assertRaisesRegex(ValueError, "preserve specification order"):
            _projection(checks=reversed_defaults)

    def test_worker_projection_updates_are_queued_to_the_gui_thread(self) -> None:
        view = VerificationView(_projection(run_id="run-a"))
        self.addCleanup(view.deleteLater)

        next_projection = VerificationProjection(
            run_id="run-b",
            banner=VerificationBannerProjection(
                status="incomplete",
                icon="!",
                heading="Incomplete",
                summary="Required verification checks have not all completed.",
                tone="warning",
            ),
            summary=_summary(
                result="Incomplete",
                notes="Awaiting reconstruction verification.",
            ),
            
            checks=(
                VerificationCheckProjection(
                    check_id="manifest-b",
                    label="Manifest Integrity",
                    result="Verified",
                    icon="✓",
                    tone="success",
                    details="Manifest integrity completed.",
                ),
                VerificationCheckProjection(
                    check_id="reconstruction-b",
                    label="Reconstruction Match",
                    result="Incomplete",
                    icon="!",
                    tone="warning",
                    details="Reconstruction comparison is still incomplete.",
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
        self.assertEqual(view.banner_heading_label.text(), "Incomplete")
        self.assertEqual(
            view.banner_frame.property("verificationStatus"),
            "incomplete",
        )
        self.assertEqual(
            view.check_order,
            ("Manifest Integrity", "Reconstruction Match"),
        )
        self.assertNotIn("manifest", view.check_disclosure_buttons)
        self.assertIn("manifest-b", view.check_disclosure_buttons)


if __name__ == "__main__":
    unittest.main()
