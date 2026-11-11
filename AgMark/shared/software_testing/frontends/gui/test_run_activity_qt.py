"""Blocked worker phases remain visible without premature terminal authority."""
import json
from dataclasses import replace
from threading import Event
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from AgMark.shared.runtime.orchestration.activity import ActivityPublisher, RunActivity
from AgMark.gui.projection.workspace.activity import with_activity
from AgMark.gui.shell.window import SidebarInputSnapshot
from AgMark.shared.software_testing.frontends.gui import test_application_lifecycle_qt as fixture
from AgMark.shared.software_testing.frontends.gui import test_retained_evidence_projection as retained


class RunActivityGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.ProductionSharedLifecycleGuiIntegrationTests.setUpClass()

    def test_active_finalization_keeps_exact_case_counts_without_eta(self):
        p=retained._active_progress_projection('generation-active',retained._active_plan())
        p=replace(p,overall=replace(p.overall,completed_cases=p.overall.total_cases))
        e=RunActivity(p.generation_id,1,'replay',141.6,2,5)
        result=with_activity(p,e,144.1)
        self.assertEqual((2,2),(result.overall.completed_cases,result.overall.total_cases))
        self.assertEqual('02:24',result.overall.elapsed_time)
        self.assertEqual(4,result.active_stage_index)
        self.assertIn('Scored cases complete',result.activity_text)
        self.assertIn('2 of 5',result.activity_text)
        self.assertIs(p,with_activity(p,replace(e,generation_id='generation-other'),999))

    def test_blocked_phases_busy_until_return_and_stale_repeated_run_events_ignored(self):
        owner=fixture.ProductionSharedLifecycleGuiIntegrationTests();owner.setUp();self.addCleanup(owner.doCleanups)
        app,session,resolver=owner._application_for('generation-activity')
        app.window.show()
        app.request_discovery();owner._wait_until(lambda: bool(app.window.benchmark_input.options),'discovery')
        def prepare():
            app.request_build_plan(SidebarInputSnapshot(benchmark='frontend.benchmark@1.0.0',runner='frontend.runner@1.0.0',model='frontend-model',credential='',temperature=None,max_tokens=None,iterations=2 if run_number == 1 else 1))
            owner._wait_until(lambda: not app._pending_commands and app._boundary.plan_request is not None,'plan')
            app.request_accept_plan();owner._wait_until(lambda: not app._pending_commands and app._boundary.accepted_snapshot is not None,'accept')
        previous=None
        for run_number in range(3):
            resolver.generation_id='generation-activity-'+str(run_number)
            prepare()
            releases=[Event() for _ in range(4)]
            phases=('capability','replay','validation_retention','cleanup')
            terminals=[]
            def execute(request):
                # Controlled source authority: a completed scored observation is
                # already retained before the first post-scoring callback.
                plan=app._boundary.accepted_snapshot.plan()
                for slot in plan.observations:
                    directory=request.artifact_store.root/request.generation_id/('observation-'+slot.observation_id.removeprefix('observation:')+'-observation')
                    directory.mkdir(parents=True,exist_ok=True)
                    (directory/'observation.json').write_text(json.dumps(retained._observation(
                        slot.treatment_id, 'controlled', runner_id='frontend.runner',
                        extension_key='frontend.runner:response_base64',
                        observation_id=slot.observation_id, generation_id=request.generation_id,
                        case_id=slot.case_id, repetition=slot.repetition,
                        boundary_fingerprint=plan.execution_boundary_fingerprint,
                    )))
                publisher=ActivityPublisher(request.generation_id,request.activity_callback)
                for index,phase in enumerate(phases):
                    publisher.emit(phase,1,1)
                    if not releases[index].wait(8): raise RuntimeError('test phase was not released')
                if run_number == 2: raise RuntimeError('controlled terminal failure')
                terminal=fixture._accepted_run(request.generation_id);terminals.append(terminal);return terminal
            try:
                with patch.object(session,'execute_accepted_run',side_effect=execute):
                    worker=app.request_start_benchmark()
                    for index,phase in enumerate(phases):
                        owner._wait_until(lambda: app._active_activity is not None and app._active_activity.phase==phase,phase)
                        # Activity ingress is immediate; retained observation
                        # reconstruction now runs independently off Qt's thread.
                        owner._wait_until(lambda: app.window.workspace_pages['Progress'].projection.overall.completed_cases
                            == app.window.workspace_pages['Progress'].projection.overall.total_cases, 'retained counts')
                        event=app._active_activity;page=app.window.workspace_pages['Progress']
                        self.assertIn('start_benchmark',app._pending_commands)
                        self.assertIsNone(app._boundary.selected_terminal)
                        self.assertIsNone(app._boundary.execution_request.activity_callback)
                        self.assertIsNone(app._boundary.execution_request.live_view_control)
                        self.assertEqual(page.projection.overall.total_cases,page.projection.overall.completed_cases)
                        self.assertIsNotNone(page.activity_indicator)
                        self.assertEqual((0,0),(page.activity_indicator.minimum(),page.activity_indicator.maximum()))
                        self.assertFalse(app.window.operation_banner.isHidden())
                        self.assertIn(page.projection.activity_text.split('. ')[-1],page.stage_description_label.text())
                        if previous is not None:app._apply_activity(previous)
                        app._apply_activity(replace(event,sequence=event.sequence-1) if event.sequence>1 else replace(event,generation_id='generation-stale'))
                        self.assertIs(event,app._active_activity)
                        previous=event
                        releases[index].set()
                    owner._wait_until(lambda: 'start_benchmark' not in app._pending_commands,'terminal')
                    worker.join(2)
                    if run_number == 2:
                        self.assertIsNone(app._boundary.selected_terminal)
                        failed_page = app.window.workspace_pages['Progress']
                        self.assertFalse(failed_page.projection.run_active)
                        self.assertEqual('Benchmark: failed', failed_page.projection.benchmark_status)
                        self.assertEqual('Failed', app.window.current_run_status.label)
                    else:
                        self.assertIs(terminals[0],app._boundary.selected_terminal)
                    self.assertIsNone(app._active_activity)
                    self.assertTrue(app.window.operation_banner.isHidden())
                    app._apply_activity(previous);self.assertIsNone(app._active_activity)
            finally:
                for release in releases:release.set()
                if 'worker' in locals():worker.join(2)


class CaptureProgressGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_full_capture_lifecycle_stays_provisional_through_drain_and_reopens(self):
        from AgMark.gui.views.progress import ProgressView
        from AgMark.gui.views.capture import CaptureView
        from AgMark.gui.application.history import _encode, _decode
        from AgMark.shared.runtime.orchestration.activity import capture_progress_callback, retained_activity
        import tempfile
        projection = retained._active_progress_projection('generation-expanded-progress', retained._active_plan())
        projection = replace(projection, overall=replace(projection.overall, completed_cases=projection.overall.total_cases),
            treatments=tuple(replace(row, completed_cases=row.total_cases) for row in projection.treatments))
        view = ProgressView(projection)
        capture_view = CaptureView(projection)
        self.addCleanup(view.deleteLater)
        self.addCleanup(capture_view.deleteLater)
        view.resize(1100, 850)
        view.show()
        with tempfile.TemporaryDirectory() as directory:
            publisher = ActivityPublisher(projection.generation_id, persistence_root=directory)
            with publisher.bind():
                callback = capture_progress_callback(treatment_id=projection.treatments[0].treatment_id, attempt_id='attempt-1')
            previous_wheel_percent = 0.0
            for phase in ('preflight', 'collector_readiness', 'execution', 'capture', 'drain', 'flush',
                          'rollout_settlement', 'evidence_validation', 'normalization', 'aggregation'):
                sealed = phase in ('normalization', 'aggregation')
                callback(dict(phase=phase, invocation_id='invocation-1', evidence_sealed=sealed,
                    telemetry_outcome='partial' if sealed else 'pending', sources=[
                        dict(source_id='stdout', state='settled' if sealed else 'active', received_events=14,
                             received_bytes=1500, dropped=1, rejected=2, parse_errors=3, partial=1),
                        dict(source_id='diagnostics', state='disabled', reason='explicit_opt_in_required'),
                        dict(source_id='otel_metrics', state='unsupported', reason='stock_capability_not_demonstrated')]))
                projected = with_activity(projection, publisher.latest, publisher.latest.elapsed_seconds)
                wheel_current, wheel_total = projected.wheel_progress
                wheel_percent = wheel_current / wheel_total * 100
                self.assertGreaterEqual(wheel_percent, previous_wheel_percent)
                previous_wheel_percent = wheel_percent
                self.assertEqual(projected.overall.completed_cases, projected.overall.total_cases)
                self.assertIsNotNone(projected.current_stage_step)
                view.set_projection(projected)
                capture_view.set_projection(projected)
                QApplication.processEvents()
                self.assertTrue(view.projection.run_active)
                self.assertFalse(view.overall_ring.isHidden())
                self.assertLess(view.overall_ring.presentation.percent, 100)
                self.assertTrue(view.overall_bar.isHidden())
                model = view.treatment_table.table_model
                for row in range(model.rowCount()):
                    self.assertIn('cases · finalizing', model.data(model.index(row, 1)))
                    self.assertNotIn('%', model.data(model.index(row, 1)))
                    self.assertIsNone(view.treatment_table.indexWidget(model.index(row, 1)))
                self.assertFalse(view.stage_stepper.visually_complete)
                self.assertFalse(view.activity_indicator.isHidden())
                self.assertIn('Original Run', projected.capture_identity)
                self.assertIn('attempt-1', projected.capture_identity)
                self.assertEqual(3, capture_view.capture_source_table.table_model.rowCount())
                self.assertIn('Dropped 1', projected.capture_sources[0].health)
                self.assertEqual('—', projected.capture_sources[1].events)
                self.assertIn('explicit opt in required', projected.capture_sources[1].reason)
                if not sealed:
                    self.assertIn('Provisional', capture_view.capture_status_label.text())
                self.assertFalse(view.grab().isNull())
            terminal = publisher.finish('complete')
            self.assertEqual(terminal, retained_activity(directory, projection.generation_id))
            complete = with_activity(projection, terminal, terminal.elapsed_seconds)
            view.set_projection(complete)
            capture_view.set_projection(complete)
            QApplication.processEvents()
            self.assertFalse(view.projection.run_active)
            self.assertTrue(view.stage_stepper.visually_complete)
            self.assertEqual(('reached',) * 5, view.stage_stepper.stage_states)
            self.assertTrue(all(label.text().startswith('✓') for label in view.stage_stepper._cue_labels))
            self.assertTrue(view.activity_indicator.isHidden())
            self.assertIn('Benchmark: complete', capture_view.capture_status_label.text())
            self.assertIn('Telemetry: partial', capture_view.capture_status_label.text())
            self.assertIn('Evidence sealed', capture_view.capture_status_label.text())
            reopened = _decode(_encode(complete))
            self.assertEqual(complete, reopened)
            self.assertFalse(reopened.run_active)
            self.assertEqual(3, len(reopened.capture_sources))

    def test_cancellation_and_telemetry_failure_are_independent(self):
        from AgMark.shared.runtime.orchestration.activity import CaptureSourceActivity
        projection = retained._active_progress_projection('generation-cancelled-progress', retained._active_plan())
        source = CaptureSourceActivity('otel_logs', 'failed', parse_errors=2, reason='invalid_otlp_json')
        event = RunActivity(projection.generation_id, 3, 'completion', 3.5, sources=(source,),
                            terminal=True, benchmark_outcome='cancelled', telemetry_outcome='failed')
        result = with_activity(projection, event, event.elapsed_seconds)
        self.assertFalse(result.run_active)
        self.assertEqual('Benchmark: cancelled', result.benchmark_status)
        self.assertEqual('Telemetry: failed', result.telemetry_status)
        self.assertIn('Cancelled', result.activity_text)
        self.assertIn('unsealed', result.evidence_status)
        self.assertEqual('failed', result.capture_sources[0].state)

    def test_many_invocations_render_only_recent_sources_with_retained_counts(self):
        from AgMark.shared.runtime.orchestration.activity import CaptureSourceActivity
        from AgMark.gui.views.progress import ProgressView
        from AgMark.gui.views.capture import CaptureView
        from AgMark.gui.application.history import _encode, _decode
        projection = retained._active_progress_projection('generation-many-captures', retained._active_plan())
        sources = tuple(CaptureSourceActivity(source, 'settled', received_events=index,
                        invocation_id=f'invocation-{index}', treatment_id='control')
            for index in range(1000) for source in ('stdout', 'stderr', 'process', 'rollout', 'otel_logs', 'otel_traces', 'otel_metrics', 'diagnostics'))
        event = RunActivity(projection.generation_id, 5000, 'completion', 30.0, sources=sources,
                            terminal=True, evidence_sealed=True, benchmark_outcome='complete', telemetry_outcome='complete')
        result = with_activity(projection, event, 30.0)
        self.assertEqual(16, len(result.capture_sources))
        self.assertIn('998 earlier captures / 7984 source rows', result.capture_summary)
        capture_view = CaptureView(result)
        self.addCleanup(capture_view.deleteLater)
        self.assertEqual(16, capture_view.capture_source_table.table_model.rowCount())
        self.assertIn('saved progress', capture_view.capture_status_label.text())
        self.assertEqual(result, _decode(_encode(result)))

    def test_finalized_execution_failure_is_independent_of_telemetry_and_stage_completion(self):
        projection = retained._active_progress_projection('generation-failed-finalization', retained._active_plan())
        event = RunActivity(projection.generation_id, 9, 'completion', 30.0, terminal=True,
                            finalization_complete=True, benchmark_outcome='completed_with_failures', telemetry_outcome='complete')
        result = with_activity(projection, event, 30.0)
        self.assertEqual('Benchmark: completed with failures', result.benchmark_status)
        self.assertEqual('Telemetry: complete', result.telemetry_status)
        self.assertTrue(result.lifecycle_complete)
        self.assertFalse(result.run_active)
        self.assertIn('failed observations or attempts', result.activity_text)
        invocation = replace(event, scope='original', terminal=False, finalization_complete=False,
                             benchmark_outcome='timed_out', invocation_id='invocation-failed')
        active = with_activity(projection, invocation, 30.0)
        self.assertEqual('Invocation: timed out', active.benchmark_status)
        self.assertFalse(active.lifecycle_complete)
        self.assertTrue(active.run_active)
