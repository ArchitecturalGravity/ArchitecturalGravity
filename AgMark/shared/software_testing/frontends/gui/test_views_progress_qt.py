"""Concrete PySide6 conformance tests for the Progress workspace view."""

from __future__ import annotations

from dataclasses import replace
import os
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.views.capture import CaptureView
from AgMark.gui.views.progress import (
    PYSIDE6_AVAILABLE,
    RUN_STAGES,
    STATUS_SEMANTICS_ROLE,
    TREATMENT_PROGRESS_COLUMNS,
    CaptureSourceProjection,
    OverallProgressProjection,
    ProgressEventProjection,
    ProgressProjection,
    ProgressView,
    TreatmentProgressProjection,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QBoxLayout, QSizePolicy, QWidget
    from AgMark.gui.shell.window import _TabContentScrollArea


def _treatment(
    *,
    treatment_id: str = "control",
    treatment: str = "Control",
    completed: int = 2,
    total: int = 4,
    stage: str = "Execution",
    status: str = "Running",
    status_icon: str = "●",
    semantics: str | None = "info",
) -> TreatmentProgressProjection:
    return TreatmentProgressProjection(
        treatment_id=treatment_id,
        treatment=treatment,
        completed_cases=completed,
        total_cases=total,
        current_stage=stage,
        status=status,
        status_icon=status_icon,
        status_semantics=semantics,
    )


def _projection(
    *,
    run_id: str = "run-active",
    generation_id: str = "generation-2",
    calls: list[str] | None = None,
) -> ProgressProjection:
    recorded = calls if calls is not None else []
    return ProgressProjection(
        run_id=run_id,
        generation_id=generation_id,
        overall=OverallProgressProjection(
            completed_cases=3,
            total_cases=8,
            elapsed_time="1m 20s",
        ),
        treatments=(
            _treatment(),
            _treatment(
                treatment_id="treatment-a",
                treatment="Treatment A",
                completed=1,
                total=4,
                stage="Golden Admission",
                status="Pending",
                status_icon="○",
                semantics="neutral",
            ),
        ),
        active_stage_index=2,
        active_stage_description="Running the accepted observation plan.",
        events=(
            ProgressEventProjection(
                generation_id="generation-1",
                timestamp="10:00:00",
                event_icon="!",
                text="Superseded generation event",
            ),
            ProgressEventProjection(
                generation_id=generation_id,
                timestamp="10:01:00",
                event_icon="●",
                text="Execution started",
            ),
        ),
        
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ProgressViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    @staticmethod
    def _settle_layout() -> None:
        for _ in range(8):
            QApplication.processEvents()

    def _live_projection(self):
        return replace(_projection(), run_active=True,
            overall=OverallProgressProjection(0, 200, "0s"),
            treatments=(_treatment(completed=0, total=100),
                        _treatment(treatment_id="other", completed=0, total=100)),
            capture_sources=(CaptureSourceProjection("Original / control / attempt-1", "stdout", "active", "0", "0", "Healthy", "—"),),
            capture_stage="Execution", capture_identity="Original Run / control / attempt-1",
            evidence_status="Provisional", benchmark_status="Benchmark: running", telemetry_status="Telemetry: pending")

    def test_live_counter_updates_preserve_widgets_models_selection_and_widths(self):
        projection = self._live_projection()
        view = ProgressView(projection)
        self.addCleanup(view.deleteLater)
        # Capture now has its own workspace; both consume the same projection.
        capture_view = CaptureView(projection)
        self.addCleanup(capture_view.deleteLater)
        view.resize(1100, 850)
        view.show()
        self._settle_layout()
        treatment_model = view.treatment_table.table_model
        capture_model = capture_view.capture_source_table.table_model
        resets, changed = [], []
        treatment_model.modelReset.connect(lambda: resets.append("treatment"))
        capture_model.modelReset.connect(lambda: resets.append("capture"))
        capture_model.dataChanged.connect(lambda *_: changed.append(True))
        view.treatment_table.selectRow(1)
        capture_view.capture_source_table.setColumnWidth(0, 321)
        ring, bar, stage = view.overall_ring, view.overall_bar, view.stage_stepper
        holders = tuple(view.treatment_table.indexWidget(treatment_model.index(index, 1)) for index in range(2))
        with patch.object(view.treatment_table, "resizeColumnsToContents", side_effect=AssertionError("live full-table sizing")), \
                patch.object(view.treatment_table, "resizeColumnToContents", side_effect=AssertionError("live column sizing")), \
                patch.object(capture_view.capture_source_table, "resizeColumnsToContents", side_effect=AssertionError("live source sizing")), \
                patch.object(view.treatment_table, "setIndexWidget", side_effect=AssertionError("live index-widget rebuild")):
            for count in range(1, 21):
                projection = replace(projection,
                    overall=replace(projection.overall, completed_cases=count, elapsed_time=f"{count}s"),
                    treatments=(replace(projection.treatments[0], completed_cases=count), projection.treatments[1]),
                    capture_sources=(replace(projection.capture_sources[0], events=str(count), bytes=str(count * 20), health="Dropped 2"),),
                    capture_stage="Drain" if count == 20 else "Execution",
                    activity_text=f"Receiving evidence: {count}")
                view.set_projection(projection)
                capture_view.set_projection(projection)
        self.assertEqual([], resets)
        self.assertEqual(20, len(changed))
        self.assertEqual("20", capture_model.data(capture_model.index(0, 3)))
        self.assertEqual("Dropped 2", capture_model.data(capture_model.index(0, 5)))
        self.assertEqual(321, capture_view.capture_source_table.columnWidth(0))
        self.assertEqual([1], [index.row() for index in view.treatment_table.selectionModel().selectedRows()])
        self.assertIs(ring, view.overall_ring)
        self.assertIs(bar, view.overall_bar)
        self.assertIs(stage, view.stage_stepper)
        self.assertEqual("Elapsed: 20s", view._summary_elapsed.text())
        self.assertEqual("Drain", view._capture_stage_label.text())
        self.assertEqual("20", view.summary_value_labels["Completed Cases"].text())
        for index, holder in enumerate(holders):
            self.assertIs(holder, view.treatment_table.indexWidget(treatment_model.index(index, 1)))

    def test_wheel_advances_on_stage_changes_without_case_completion(self):
        projection = self._live_projection()
        view = ProgressView(projection)
        self.addCleanup(view.deleteLater)
        ring, bar = view.overall_ring, view.overall_bar
        initial = ring.presentation.percent

        capture_update = replace(
            projection,
            current_stage_step=4,
            capture_stage="4 · Stream drain",
            treatments=(
                replace(projection.treatments[0], current_stage="4 · Stream drain"),
                projection.treatments[1],
            ),
        )
        view.set_projection(capture_update)
        self.assertGreater(ring.presentation.percent, initial)
        self.assertEqual((bar.current, bar.total), (0, 200))

        stage_update = replace(capture_update, active_stage_index=3, current_stage_step=None)
        view.set_projection(stage_update)
        self.assertIs(ring, view.overall_ring)
        self.assertIs(bar, view.overall_bar)
        self.assertGreater(ring.presentation.percent, initial)
        self.assertEqual((bar.current, bar.total), (0, 200))

        finished_cases = replace(
            stage_update,
            overall=replace(projection.overall, completed_cases=200),
            active_stage_index=4,
        )
        view.set_projection(finished_cases)
        self.assertFalse(ring.isHidden())
        self.assertLess(ring.presentation.percent, 100)
        self.assertTrue(bar.isHidden())

        complete = replace(finished_cases, run_active=False, lifecycle_complete=True)
        view.set_projection(complete)
        self.assertEqual(ring.presentation.percent, 100)
        self.assertTrue(ring.visually_complete)

    def test_unscored_finalization_is_not_labeled_finished_until_complete(self):
        progress = replace(self._live_projection(), unscored=True,
            active_stage_index=4, activity_text="Preparing retained results and saving history…")
        view = ProgressView(progress)
        self.addCleanup(view.deleteLater)
        self.assertEqual("Finalization", view.stage_description_card.title)
        self.assertEqual("Finalization", view.stage_stepper.stages[-1])
        self.assertFalse(view.stage_stepper.visually_complete)
        view.set_projection(replace(progress, run_active=False, lifecycle_complete=True))
        self.assertEqual("Finished", view.stage_description_card.title)
        self.assertTrue(view.stage_stepper.visually_complete)

    def test_inactive_failure_text_does_not_show_busy_indicator_without_benchmark_status(self):
        progress = replace(self._live_projection(), run_active=False,
            benchmark_status=None, activity_text="Retained result preparation failed.")
        view = ProgressView(progress)
        self.addCleanup(view.deleteLater)
        self.assertTrue(view.activity_indicator.isHidden())
        self.assertIn("failed", view.activity_label.text())

    def test_event_only_updates_do_not_rebuild_visible_progress(self):
        view = ProgressView(self._live_projection())
        self.addCleanup(view.deleteLater)
        event = ProgressEventProjection(view.generation_id, "later", "●", "Retained activity")
        with patch.object(view, "_rebuild_summary", side_effect=AssertionError("event rebuilt summary")), \
                patch.object(view, "_update_summary", side_effect=AssertionError("event updated summary")), \
                patch.object(view, "_update_treatments", side_effect=AssertionError("event updated treatments")), \
                patch.object(view, "_update_stage", side_effect=AssertionError("event updated stage")):
            view.push_event(event)
            view.push_event(replace(event, generation_id="generation-stale"))
        self.assertEqual(event, view.visible_events[-1])
        self.assertNotIn("generation-stale", [value.generation_id for value in view.visible_events])

    def test_finalization_changes_only_affected_row_then_marks_completed_stage(self):
        projection = self._live_projection()
        view = ProgressView(projection)
        self.addCleanup(view.deleteLater)
        model = view.treatment_table.table_model
        unchanged = view.treatment_table.indexWidget(model.index(1, 1))
        stage = view.stage_stepper
        finalized_row = replace(projection.treatments[0], completed_cases=100)
        pending = replace(projection, treatments=(finalized_row, projection.treatments[1]),
            overall=replace(projection.overall, completed_cases=200), active_stage_index=4,
            capture_stage="Evidence validation", activity_text="Finalizing evidence")
        view.set_projection(pending)
        self.assertIsNone(view.treatment_table.indexWidget(model.index(0, 1)))
        self.assertIs(unchanged, view.treatment_table.indexWidget(model.index(1, 1)))
        self.assertIn("cases · finalizing", model.data(model.index(0, 1)))
        self.assertNotIn("%", model.data(model.index(0, 1)))
        self.assertFalse(view.overall_ring.isHidden())
        self.assertLess(view.overall_ring.presentation.percent, 100)
        self.assertIs(stage, view.stage_stepper)
        self.assertFalse(view.stage_stepper.visually_complete)
        complete = replace(pending, run_active=False, lifecycle_complete=True,
            benchmark_status="Benchmark: complete", evidence_status="Evidence sealed")
        view.set_projection(complete)
        self.assertIsNotNone(view.treatment_table.indexWidget(model.index(0, 1)))
        self.assertIs(unchanged, view.treatment_table.indexWidget(model.index(1, 1)))
        self.assertTrue(view.stage_stepper.visually_complete)
        self.assertFalse(view.overall_ring.isHidden())
        self.assertTrue(view.activity_indicator.isHidden())

    def test_changed_generation_or_source_identity_resets_only_matching_structure(self):
        projection = self._live_projection()
        view = ProgressView(projection)
        self.addCleanup(view.deleteLater)
        # Capture now has its own workspace; both consume the same projection.
        capture_view = CaptureView(projection)
        self.addCleanup(capture_view.deleteLater)
        resets = []
        capture_view.capture_source_table.table_model.modelReset.connect(lambda: resets.append("capture"))
        view.treatment_table.table_model.modelReset.connect(lambda: resets.append("treatment"))
        ring = view.overall_ring
        changed = replace(projection, capture_sources=(replace(projection.capture_sources[0], capture="Original / control / attempt-2", events="0"),))
        view.set_projection(changed)
        capture_view.set_projection(changed)
        self.assertEqual(["capture"], resets)
        self.assertIs(ring, view.overall_ring)
        next_generation = replace(changed, run_id="next-run", generation_id="generation-next", events=())
        view.set_projection(next_generation)
        capture_view.set_projection(next_generation)
        self.assertEqual(["capture", "treatment", "capture"], resets)
        self.assertIsNot(ring, view.overall_ring)
        self.assertEqual((), view.visible_events)

    def test_treatment_table_fills_available_width_during_active_run(self) -> None:
        projection = self._live_projection()
        view = ProgressView(projection)
        self.addCleanup(view.deleteLater)
        view.resize(1280, 850)
        view.show()
        self._settle_layout()

        table = view.treatment_table
        header = table.horizontalHeader()
        self.assertTrue(header.stretchLastSection())
        last_column = table.table_model.columnCount() - 1
        widths = []
        for width in (1280, 1660, 1280):
            view.resize(width, 850)
            self._settle_layout()
            widths.append(table.columnWidth(last_column))
            self.assertAlmostEqual(header.length(), table.viewport().width(), delta=3)

        self.assertGreater(widths[1], widths[0])
        self.assertAlmostEqual(widths[2], widths[0], delta=3)

        # Incoming case progress must not undo the viewport-filling header.
        view.set_projection(replace(
            projection,
            treatments=(replace(projection.treatments[0], completed_cases=9),
                        projection.treatments[1]),
        ))
        self._settle_layout()
        self.assertAlmostEqual(header.length(), table.viewport().width(), delta=3)

    def test_component_floors_reflow_inside_narrow_scroll_viewport(self) -> None:
        view = ProgressView(_projection())
        view.setMinimumSize(560, 240)
        scroll = _TabContentScrollArea()
        self.addCleanup(scroll.deleteLater)
        scroll.setWidgetResizable(True)
        scroll.setWidget(view)
        scroll.resize(600, 320)
        scroll.show()
        self._settle_layout()

        self.assertEqual(view._body_layout.direction(), QBoxLayout.Direction.TopToBottom)
        self.assertEqual(view._summary_layout.direction(), QBoxLayout.Direction.TopToBottom)
        self.assertGreaterEqual(view.treatment_table.width(), 480)
        self.assertGreaterEqual(view.treatment_table.height(), 220)
        self.assertGreaterEqual(view.treatment_card.width(), 510)
        self.assertGreaterEqual(view.run_stage_card.width(), 300)
        self.assertGreaterEqual(view.run_stage_card.height(), 300)
        self.assertEqual(view.stage_stepper.orientation, "vertical")
        stage_top = view.run_stage_card.mapTo(view, view.run_stage_card.rect().topLeft()).y()
        self.assertGreater(stage_top, view.treatment_card.geometry().bottom())
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.assertEqual(view.treatment_table.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)

        narrow_height = view.minimumHeight()
        scroll.resize(1150, 650)
        self._settle_layout()
        self.assertEqual(view._body_layout.direction(), QBoxLayout.Direction.LeftToRight)
        self.assertEqual(view._summary_layout.direction(), QBoxLayout.Direction.LeftToRight)
        self.assertLess(view.minimumHeight(), narrow_height)
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
        for card in (view.treatment_card, view.run_stage_card):
            origin = card.mapTo(view, card.rect().topLeft())
            self.assertLessEqual(origin.x() + card.width(), view.width())
            self.assertLessEqual(origin.y() + card.height(), view.height())

        scroll.resize(600, 320)
        self._settle_layout()
        self.assertEqual(view._body_layout.direction(), QBoxLayout.Direction.TopToBottom)
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)

    def test_progress_cell_controls_fit_after_repeated_projection_updates(self) -> None:
        view = ProgressView(_projection())
        self.addCleanup(view.deleteLater)
        view.resize(1100, 600)
        view.show()
        for completed in (0, 1, 4):
            projection = replace(_projection(), treatments=(_treatment(completed=completed),))
            view.set_projection(projection)
            self._settle_layout()
            holder = view.treatment_table.indexWidget(view.treatment_table.table_model.index(0, 1))
            progress = view.treatment_progress_widgets["control"]
            bar_origin = progress.indicator.mapTo(holder, progress.indicator.rect().topLeft())
            self.assertGreaterEqual(holder.height(), 32)
            self.assertGreaterEqual(view.treatment_table.rowHeight(0), holder.minimumHeight() + 1)
            self.assertGreaterEqual(progress.indicator.height(), 16)
            self.assertLessEqual(bar_origin.y() + progress.indicator.height(), holder.height())
            self.assertLessEqual(bar_origin.x() + progress.indicator.width(), holder.width())
            self.assertGreaterEqual(view.treatment_table.columnWidth(1), holder.minimumWidth())

    def test_summary_and_stage_long_text_preserve_narrow_component_widths(self) -> None:
        projection = replace(
            _projection(),
            overall=OverallProgressProjection(3, 8, "elapsed-" + "a" * 96),
            active_stage_description="generation-" + "c" * 128,
        )
        view = ProgressView(projection)
        self.addCleanup(view.deleteLater)
        view.setMinimumWidth(560)
        view.set_available_width(560)
        view.resize(560, 320)
        view.show()
        self._settle_layout()

        self.assertEqual(view.width(), 560)
        for name in ("progressSummaryOverview", "progressSummaryText", "progressSummaryCounters"):
            component = view.findChild(QWidget, name)
            self.assertIsNotNone(component)
            origin = component.mapTo(view, component.rect().topLeft())
            self.assertLessEqual(origin.x() + component.width(), view.width())
        self.assertGreaterEqual(view.stage_description_label.height(), 36)
        self.assertEqual(view.stage_description_label.text(), projection.active_stage_description)

    def test_wrapped_summary_and_stage_paragraphs_receive_required_height(self) -> None:
        projection = replace(
            _projection(),
            overall=OverallProgressProjection(3, 8, "1 minute"),
            active_stage_description="Running the accepted observation plan. " * 30,
        )
        view = ProgressView(projection)
        self.addCleanup(view.deleteLater)
        view.setMinimumWidth(560)
        view.set_available_width(560)
        view.resize(560, 320)
        view.show()
        self._settle_layout()
        for label in (view._summary_elapsed, view.stage_description_label):
            self.assertTrue(label.hasHeightForWidth())
            self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))

    def test_default_composition_preserves_exact_progress_projection(self) -> None:
        calls: list[str] = []
        view = ProgressView(_projection(calls=calls))
        self.addCleanup(view.deleteLater)

        self.assertEqual(
            tuple(column.label for column in TREATMENT_PROGRESS_COLUMNS),
            ("Treatment", "Progress", "Cases", "Current Stage", "Status"),
        )
        self.assertEqual(
            tuple(column.label for column in view.treatment_table.columns),
            ("Treatment", "Progress", "Cases", "Current Stage", "Status"),
        )
        self.assertEqual(
            RUN_STAGES,
            (
                "Planning",
                "Golden Admission",
                "Execution",
                "Evaluation",
                "Finalization",
            ),
        )
        self.assertEqual(view.run_id, "run-active")
        self.assertEqual(view.generation_id, "generation-2")
        self.assertEqual(view.authority_semantics, "presentation-only")
        self.assertEqual(view.completion_semantics, "visual-only")

        self.assertEqual((view.overall_ring.current, view.overall_ring.total), _projection().wheel_progress)
        self.assertEqual(view.overall_bar.current, 3)
        self.assertEqual(
            {label: widget.text() for label, widget in view.summary_value_labels.items()},
            {
                "Completed Cases": "3",
                "Remaining Cases": "5",
                "Total Cases": "8",
            },
        )

        model = view.treatment_table.table_model
        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.columnCount(), 5)
        self.assertEqual(
            model.data(model.index(0, 2), int(Qt.ItemDataRole.DisplayRole)),
            "2/4",
        )
        self.assertEqual(
            model.data(model.index(0, 3), int(Qt.ItemDataRole.DisplayRole)),
            "Execution",
        )
        self.assertEqual(
            model.data(model.index(0, 4), int(Qt.ItemDataRole.DisplayRole)),
            "● Running",
        )
        self.assertEqual(
            model.data(model.index(0, 4), STATUS_SEMANTICS_ROLE),
            "info",
        )
        self.assertEqual(view.treatment_progress_widgets["control"].current, 2)
        self.assertEqual(view.treatment_progress_widgets["control"].total, 4)

        self.assertEqual(view.stage_stepper.stages, RUN_STAGES)
        self.assertEqual(view.stage_stepper.current, 2)
        self.assertEqual(view.stage_stepper.current_stage_label, "Execution")
        self.assertEqual(view.stage_description_card.title, "Execution")
        self.assertEqual(
            view.stage_description_label.text(),
            "Running the accepted observation plan.",
        )

        self.assertEqual(len(view.visible_events), 1)
        self.assertEqual(view.visible_events[0].generation_id, "generation-2")
        view.resize(1100, 600)
        view.show()
        QApplication.processEvents()
        self.assertEqual(view.run_stage_card.mapTo(view, view.run_stage_card.rect().topLeft()).y(), view.treatment_card.mapTo(view, view.treatment_card.rect().topLeft()).y())
        self.assertEqual(view.run_stage_card.height(), view.treatment_card.height())

    def test_long_generation_description_preserves_refreshed_panel_geometry(self) -> None:
        initial = _projection()
        view = ProgressView(initial)
        self.addCleanup(view.deleteLater)
        view.resize(1100, 600)
        view.show()
        QApplication.processEvents()
        description = "Executing accepted observations for generation-" + "a" * 96
        updated = replace(initial, active_stage_description=description)
        view.set_projection(updated)
        for _ in range(5):
            QApplication.processEvents()
        self.assertEqual(description, view.stage_description_label.text())
        self.assertEqual(initial.generation_id, view.generation_id)
        self.assertGreater(view.treatment_card.width(), view.run_stage_card.width())
        for card in (view.treatment_card, view.run_stage_card):
            origin = card.mapTo(view, card.rect().topLeft())
            self.assertGreaterEqual(origin.x(), 0)
            self.assertLessEqual(origin.x() + card.width(), view.width())
            self.assertLessEqual(origin.y() + card.height(), view.height())
        self.assertFalse(view.grab().isNull())

    def test_visual_completion_does_not_create_terminal_authority(self) -> None:
        view = ProgressView(
            ProgressProjection(
                run_id="run-complete-looking",
                generation_id="generation-current",
                overall=OverallProgressProjection(
                    completed_cases=4,
                    total_cases=4,
                    elapsed_time="2m",
                ),
                treatments=(_treatment(completed=4, total=4, status="Complete"),),
                active_stage_index=4,
                active_stage_description="Finalizing caller-supplied execution state.",
                events=(
                    ProgressEventProjection(
                        generation_id="generation-current",
                        timestamp="10:02:00",
                        event_icon="✓",
                        text="All visual progress counters reached their totals",
                    ),
                ),
                
                
            )
        )
        self.addCleanup(view.deleteLater)

        self.assertFalse(view.overall_ring.visually_complete)
        self.assertLess(view.overall_ring.presentation.percent, 100)
        self.assertEqual(view.overall_ring.completion_semantics, "visual-only")
    def test_incomplete_states_and_stale_events_do_not_invent_progress(self) -> None:
        view = ProgressView(
            ProgressProjection(
                run_id="run-pending",
                generation_id="generation-pending",
                overall=None,
                treatments=(),
                active_stage_index=None,
                active_stage_description=None,
                events=(),
                summary_empty_state="Overall progress is not yet available",
                treatment_empty_state="Treatment progress is not yet available",
                run_stage_empty_state="Run stage is not yet available",
                
                
                
            )
        )
        self.addCleanup(view.deleteLater)

        self.assertIsNone(view.overall_ring)
        self.assertIsNone(view.overall_bar)
        self.assertEqual(view.treatment_table.table_model.rowCount(), 0)
        self.assertTrue(view.treatment_table.isHidden())
        self.assertFalse(view.treatment_empty_label.isHidden())
        self.assertEqual(
            view.treatment_empty_label.text(),
            "Treatment progress is not yet available",
        )
        self.assertIsNone(view.stage_stepper)
        self.assertEqual(view.visible_events, ())

        view.push_event(
            ProgressEventProjection(
                generation_id="generation-old",
                timestamp="09:59:00",
                event_icon="!",
                text="Stale event",
            )
        )
        self.assertEqual(view.visible_events, ())

        view.push_event(
            ProgressEventProjection(
                generation_id="generation-pending",
                timestamp="10:03:00",
                event_icon="●",
                text="Current generation event",
            )
        )
        self.assertEqual(len(view.visible_events), 1)

    def test_invalid_projection_fails_closed_and_worker_update_is_queued(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            OverallProgressProjection(
                completed_cases=0,
                total_cases=0,
                elapsed_time="0s",
            )

        with self.assertRaisesRegex(ValueError, "summary_empty_state"):
            ProgressProjection(
                run_id="run-empty",
                generation_id="generation-empty",
                overall=None,
                treatments=(),
                active_stage_index=None,
                active_stage_description=None,
                events=(),
                treatment_empty_state="No treatments",
                run_stage_empty_state="No active stage",
                
            )

        view = ProgressView(_projection())
        self.addCleanup(view.deleteLater)
        next_projection = _projection(
            run_id="run-next",
            generation_id="generation-3",
        )
        worker = threading.Thread(target=view.set_projection, args=(next_projection,))
        worker.start()
        worker.join()
        QApplication.processEvents()

        self.assertEqual(view.run_id, "run-next")
        self.assertEqual(view.generation_id, "generation-3")
        self.assertEqual(
            tuple(event.generation_id for event in view.visible_events),
            ("generation-3",),
        )


    def test_worker_event_delivery_is_queued_and_generation_filtered(self) -> None:
        view = ProgressView(_projection())
        self.addCleanup(view.deleteLater)
        self.assertEqual(len(view.visible_events), 1)

        stale_event = ProgressEventProjection(
            generation_id="generation-old",
            timestamp="10:04:00",
            event_icon="!",
            text="Worker stale event",
        )
        current_event = ProgressEventProjection(
            generation_id="generation-2",
            timestamp="10:05:00",
            event_icon="●",
            text="Worker current event",
        )

        worker = threading.Thread(
            target=lambda: (
                view.push_event(stale_event),
                view.push_event(current_event),
            )
        )
        worker.start()
        worker.join()

        # Worker-originated signals must not mutate widgets directly.
        self.assertEqual(len(view.visible_events), 1)

        QApplication.processEvents()

        self.assertEqual(len(view.visible_events), 2)
        self.assertEqual(
            tuple(event.generation_id for event in view.visible_events),
            ("generation-2", "generation-2"),
        )
        self.assertTrue(any("Worker current event" in event.text for event in view.visible_events))
        self.assertFalse(any("Worker stale event" in event.text for event in view.visible_events))


class ProgressWheelArithmeticTests(unittest.TestCase):
    def test_stage_share_and_case_share_remain_visual_only(self):
        p = _projection()
        self.assertEqual(p.wheel_progress, (1057, 2800))
        self.assertEqual(replace(p, current_stage_step=3).wheel_progress, (1081, 2800))
        self.assertEqual(replace(p, current_stage_step=4).wheel_progress, (1089, 2800))
        self.assertEqual(replace(p, active_stage_index=3).wheel_progress, (1113, 2800))
        self.assertEqual(replace(p, overall=replace(p.overall, completed_cases=4)).wheel_progress, (1372, 2800))
        full_cases = replace(p, overall=replace(p.overall, completed_cases=8), run_active=True, active_stage_index=4)
        self.assertEqual(full_cases.wheel_progress, (2744, 2800))
        self.assertEqual(replace(full_cases, run_active=False, lifecycle_complete=True).wheel_progress, (2800, 2800))
        self.assertIsNone(replace(p, overall=None, summary_empty_state="No counts").wheel_progress)
        with self.assertRaisesRegex(ValueError, "current_stage_step"):
            replace(p, current_stage_step=8)


if __name__ == "__main__":
    unittest.main()
