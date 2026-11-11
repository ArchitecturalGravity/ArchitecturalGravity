"""Concrete PySide6 conformance tests for progress and stage-stepper widgets."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.widgets.progress import (
    PYSIDE6_AVAILABLE,
    ProgressIndicator,
    StageStepper,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QApplication, QLabel, QProgressBar


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ProgressWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_bar_projects_caller_progress_label(self) -> None:
        progress = ProgressIndicator(
            2,
            5,
            form="bar",
            label="Generation",
        )
        self.addCleanup(progress.deleteLater)

        self.assertEqual(progress.current, 2)
        self.assertEqual(progress.total, 5)
        self.assertEqual(progress.displayed_label, "Generation")
        self.assertFalse(progress.visually_complete)
        self.assertEqual(progress.authority_semantics, "presentation-only")
        self.assertEqual(progress.completion_semantics, "visual-only")
        self.assertEqual(progress.property("authoritySemantics"), "presentation-only")
        self.assertEqual(progress.property("completionSemantics"), "visual-only")
        self.assertIsInstance(progress.indicator, QProgressBar)
        self.assertEqual(progress.indicator.minimum(), 0)
        self.assertEqual(progress.indicator.maximum(), 5)
        self.assertEqual(progress.indicator.value(), 2)

    def test_required_indicator_forms_preserve_visual_only_completion(self) -> None:
        ring = ProgressIndicator(4, 4, form="ring", label="accepted")
        counter = ProgressIndicator(1, 4, form="counter", label="verified")
        self.addCleanup(ring.deleteLater)
        self.addCleanup(counter.deleteLater)

        self.assertTrue(ring.visually_complete)
        self.assertEqual(ring.completion_semantics, "visual-only")
        self.assertEqual(ring.authority_semantics, "presentation-only")

        self.assertIsInstance(counter.indicator, QLabel)
        self.assertEqual(counter.indicator.text(), "1 of 4")
        self.assertFalse(counter.visually_complete)

    def test_stage_stepper_preserves_labels_and_explicit_position(self) -> None:
        stepper = StageStepper(
            ("Plan", "Run", "Verify"),
            1,
            label="Benchmark progress",
        )
        self.addCleanup(stepper.deleteLater)

        self.assertEqual(stepper.stages, ("Plan", "Run", "Verify"))
        self.assertEqual(stepper.current, 1)
        self.assertEqual(stepper.current_stage_label, "Run")
        self.assertEqual(stepper.stage_states, ("reached", "current", "pending"))
        self.assertEqual(stepper.authority_semantics, "presentation-only")
        self.assertEqual(stepper.completion_semantics, "visual-only")

        stepper.set_progress(3, label="accepted")
        self.assertTrue(stepper.visually_complete)
        self.assertIsNone(stepper.current_stage_label)
        self.assertEqual(stepper.stage_states, ("reached", "reached", "reached"))
        self.assertEqual(stepper.authority_semantics, "presentation-only")

        stepper.replace(("blocked", "verified"), 0)
        self.assertEqual(stepper.stages, ("blocked", "verified"))
        self.assertEqual(stepper.current_stage_label, "blocked")
        self.assertEqual(stepper.stage_states, ("current", "pending"))

    def test_vertical_stage_stepper_preserves_readable_rows_and_position(self) -> None:
        stepper = StageStepper(
            ("Planning", "Golden Admission", "Execution", "Evaluation", "Finalization"),
            2,
            orientation="vertical",
        )
        self.addCleanup(stepper.deleteLater)
        stepper.resize(260, 180)
        stepper.show()
        QApplication.processEvents()

        self.assertEqual(stepper.orientation, "vertical")
        self.assertEqual(stepper.current_stage_label, "Execution")
        self.assertEqual(stepper.stage_states, ("reached", "reached", "current", "pending", "pending"))
        last_bottom = -1
        for row, cue, label in zip(stepper._step_widgets, stepper._cue_labels, stepper._text_labels):
            self.assertGreaterEqual(row.height(), 28)
            self.assertGreater(row.y(), last_bottom)
            self.assertGreaterEqual(cue.width(), 40)
            self.assertGreaterEqual(label.width(), 120)
            self.assertGreater(label.x(), cue.geometry().right())
            self.assertTrue(label.wordWrap())
            last_bottom = row.geometry().bottom()
        stepper.replace(("New plan", "New execution"), 1)
        self.assertEqual(stepper.orientation, "vertical")
        self.assertEqual(stepper.current_stage_label, "New execution")
        self.assertEqual(stepper.stage_states, ("reached", "current"))

    def test_invalid_progress_and_stage_contracts_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "bar, ring, or counter"):
            ProgressIndicator(1, 2, form="stepper")

        with self.assertRaises(ValueError):
            ProgressIndicator(3, 2)

        with self.assertRaisesRegex(ValueError, "sequence"):
            StageStepper("Plan", 0)

        with self.assertRaisesRegex(ValueError, "at least one"):
            StageStepper((), 0)

        with self.assertRaisesRegex(ValueError, "visible"):
            StageStepper(("Plan", "   "), 0)

        with self.assertRaises(ValueError):
            StageStepper(("Plan", "Run"), 3)

        with self.assertRaisesRegex(ValueError, "horizontal or vertical"):
            StageStepper(("Plan", "Run"), 0, orientation="diagonal")


if __name__ == "__main__":
    unittest.main()
