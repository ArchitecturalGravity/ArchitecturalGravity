"""Presentation failures and phase publication cannot change scored authority."""
from contextlib import ExitStack
from dataclasses import replace
import tempfile
import json
import unittest
from unittest.mock import patch
from AgMark.shared.runtime.orchestration.activity import ActivityPublisher, RunActivity, retained_activity
from AgMark.shared.runtime.orchestration import AcceptedRun
from AgMark.shared.software_testing.integration import test_application_boundary as fixture


class RunActivityTests(unittest.TestCase):
    def test_application_phases_cleanup_and_validation_failure_preserve_terminal(self):
        for validation_failure, callback_failure in ((False, False), (True, False), (False, True)):
            with self.subTest(validation_failure=validation_failure, callback_failure=callback_failure), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                session, request = fixture._execution_request(directory)
                terminal = fixture._accepted_run(request.generation_id)
                object.__setattr__(terminal, "treatment_observations", (json.dumps({"terminal_status": "completed", "attempts": [{"status": "completed"}]}).encode(),))
                events = []
                def callback(event):
                    events.append(event)
                    if callback_failure: raise RuntimeError('presentation disconnected')
                request = replace(request, activity_callback=callback)
                for name, value in (('admit_accepted_execution',fixture._accepted_gate(request.generation_id)),
                        ('execute_planned_treatments',object()),('score_accepted_treatments',object()),('finalize_scored_run',terminal)):
                    stack.enter_context(patch('AgMark.shared.application.'+name,return_value=value))
                stack.enter_context(patch.object(AcceptedRun,'revalidate'))
                def validate(**kwargs):
                    activity=kwargs['activity']; activity.emit('capability',1,2); activity.emit('replay',1,2)
                    if validation_failure: raise ValueError('private failure detail')
                    activity.emit('replay',2,2)
                    return ()
                stack.enter_context(patch('AgMark.shared.runtime.orchestration.replay.validate_finalized_run',side_effect=validate))
                def retain(*args,**kwargs): self.assertEqual('validation_retention',events[-1].phase)
                stack.enter_context(patch('AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.retain',side_effect=retain))
                stack.enter_context(patch('AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.retain_failure'))
                def cleanup(*args): self.assertEqual('cleanup',events[-1].phase)
                stack.enter_context(patch('AgMark.shared.validation.codex_cache.startup.StartupCollector.close',side_effect=cleanup))
                self.assertIs(terminal,session.execute_accepted_run(request))
                self.assertEqual(['admission','execution','evaluation','finalization'],[e.phase for e in events[:4]])
                self.assertEqual('completion',events[-1].phase)
                self.assertTrue(events[-1].terminal)
                self.assertEqual('complete', events[-1].benchmark_outcome)
                self.assertEqual(events[-1], retained_activity(request.artifact_store.root, request.generation_id))
                self.assertEqual(list(range(1,len(events)+1)),[e.sequence for e in events])
                self.assertTrue(all(e.generation_id==request.generation_id for e in events))
                self.assertEqual(sorted(e.elapsed_seconds for e in events),[e.elapsed_seconds for e in events])
                self.assertNotIn('private failure detail',repr(events))
                self.assertIs(terminal,session.select_run(request.generation_id))

    def test_activity_contract_rejects_invalid_counts_and_nonfinite_time(self):
        for kwargs in ({'current':2,'total':1},{'elapsed_seconds':float('nan')},{'sequence':0},{'phase':'provider-secret'}):
            values=dict(generation_id='generation-test',sequence=1,phase='replay',elapsed_seconds=0)
            values.update(kwargs)
            with self.assertRaises(ValueError):RunActivity(**values)

    def test_finalized_accepted_run_preserves_failed_original_outcomes(self):
        cases = ((('failed',), 'failed'), (('timed_out',), 'timed_out'),
                 (('cancelled',), 'cancelled'), (('completed', 'failed'), 'completed_with_failures'),
                 (('completed', 'timed_out'), 'completed_with_failures'))
        for statuses, expected in cases:
            with self.subTest(statuses=statuses), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                session, request = fixture._execution_request(directory)
                terminal = fixture._accepted_run(request.generation_id)
                object.__setattr__(terminal, 'treatment_observations', tuple(json.dumps({
                    'treatment_id': f'treatment-{index}', 'terminal_status': status,
                    'attempts': [{'attempt': 1, 'status': status}]}).encode() for index, status in enumerate(statuses)))
                events = []
                request = replace(request, activity_callback=events.append)
                for name, value in (('admit_accepted_execution', fixture._accepted_gate(request.generation_id)),
                        ('execute_planned_treatments', object()), ('score_accepted_treatments', object()), ('finalize_scored_run', terminal)):
                    stack.enter_context(patch('AgMark.shared.application.' + name, return_value=value))
                stack.enter_context(patch.object(AcceptedRun, 'revalidate'))
                stack.enter_context(patch('AgMark.shared.runtime.orchestration.replay.validate_finalized_run', return_value=()))
                stack.enter_context(patch('AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.retain'))
                self.assertIs(terminal, session.execute_accepted_run(request))
                final = events[-1]
                self.assertEqual(expected, final.benchmark_outcome)
                self.assertTrue(final.terminal)
                self.assertTrue(final.finalization_complete)
                self.assertEqual('unavailable', final.telemetry_outcome)
                self.assertEqual(final, retained_activity(request.artifact_store.root, request.generation_id))

    def test_summary_preserves_recovered_attempt_failures_and_missing_outcomes(self):
        from AgMark.shared.runtime.orchestration.activity import benchmark_outcome_from_observations
        for failed_attempt in ('failed', 'timed_out', 'cancelled', 'unsupported'):
            observation = {'terminal_status': 'completed', 'attempts': [{'status': failed_attempt}, {'status': 'completed'}]}
            self.assertEqual('completed_with_failures', benchmark_outcome_from_observations((observation,)))
        for missing in ((), (b'{invalid',), ({'terminal_status': 'unknown'},)):
            self.assertEqual('unavailable', benchmark_outcome_from_observations(missing))
