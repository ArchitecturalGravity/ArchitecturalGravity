"""Accepted replay choice gates preparation and invocation without changing scoring."""
from dataclasses import replace
import json
import tempfile
import unittest
from unittest.mock import patch
from AgMark.shared.software_testing.integration import test_application_boundary as fixture
from AgMark.shared.application import ApplicationPlanRequest
from AgMark.shared.runtime.orchestration import PlannedCaseInput, AcceptedRun
from AgMark.shared.validation.codex_cache.serialization import admit_validation

POLICY = 'arcgrav.runtime:cache-validation-replays'


class OptionalCacheReplayTests(unittest.TestCase):
    def test_accepted_choice_controls_startup_and_replays_across_next_run_toggles(self):
        with tempfile.TemporaryDirectory() as directory:
            session, request = fixture._execution_request(directory)
            for number, enabled in enumerate((False, True, False)):
                session.build_plan(ApplicationPlanRequest(
                    benchmark=request.benchmark, case_set=request.case_set,
                    treatment_set=request.treatment_set,
                    cases=(PlannedCaseInput('case-1', 'sha256:' + '3' * 64),),
                    treatments=('treatment-a',), repetitions=3,
                    execution_boundary=request.execution_boundary, golden_required=False,
                    extensions={POLICY: enabled}))
                accepted = session.accept_plan()
                self.assertIs(enabled, accepted.plan().to_dict()['extensions'][POLICY])
                self.assertEqual(3, len(accepted.plan().observations))
                current = replace(request, generation_id=f'optional-replays-{number}',
                    runner_registration={'extensions': {
                        'arcgrav.adapters:validation_replay': {'profile': 'codex_cli_cache_v1'},
                    }})
                terminal = fixture._accepted_run(current.generation_id)
                object.__setattr__(terminal, 'treatment_observations', tuple(json.dumps({
                    'observation_id': f'obs-{i}', 'treatment_id': 'treatment-a', 'repetition': i}).encode() for i in (1, 2, 3)))
                accepted_plan = accepted.plan
                with (
                    patch.object(type(accepted), 'plan', autospec=True,
                                 side_effect=lambda snapshot: accepted_plan()) as read_plan,
                    patch('AgMark.shared.application.admit_accepted_execution', return_value=fixture._accepted_gate(current.generation_id)),
                    patch('AgMark.shared.application.execute_planned_treatments', return_value=object()) as execute,
                    patch('AgMark.shared.application.score_accepted_treatments', return_value=object()) as score,
                    patch('AgMark.shared.application.finalize_scored_run', return_value=terminal),
                    patch.object(AcceptedRun, 'revalidate'),
                    patch('AgMark.shared.validation.codex_cache.startup.StartupCollector') as startup,
                    patch('AgMark.shared.runtime.orchestration.replay.validate_finalized_run', return_value=()) as validate,
                    patch('AgMark.shared.runtime.artifacts.validation.ValidationArtifactStore.retain') as retain,
                ):
                    self.assertIs(terminal, session.execute_accepted_run(current))
                read_plan.assert_called_once_with(accepted)
                execute.assert_called_once(); score.assert_called_once(); retain.assert_called_once()
                self.assertIsNone(session.validation_diagnostic(current.generation_id))
                if enabled:
                    startup.assert_called_once(); validate.assert_called_once()
                else:
                    startup.assert_not_called(); validate.assert_not_called()
                    summaries = retain.call_args.args[1]
                    self.assertEqual(1, len(summaries))
                    value = admit_validation(summaries[0].to_dict())
                    self.assertEqual('disabled_by_user', value.sampling_policy)
                    self.assertEqual('Disabled by user', value.sampling_reason)
                    self.assertEqual(('obs-1', 'obs-2', 'obs-3'), value.scored_observation_ids)
                    self.assertEqual((), value.replays)
                    self.assertEqual({}, dict(value.metrics))
                    self.assertIsNone(value.coverage.comparable_coverage.value)

    def test_disabled_summary_rejects_replay_records(self):
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import replay
        from AgMark.shared.validation.codex_cache.metrics import treatment_summary
        value = replay()
        with self.assertRaisesRegex(ValueError, 'Disabled or unsupported validation'):
            treatment_summary(generation_id=value.generation_id, treatment_id=value.treatment_id,
                replays=(value,), scored_observation_ids=(value.validates_observation_id,),
                sampling_policy='disabled_by_user', sampling_reason='Disabled by user')

    def test_disabled_disposition_reopens_from_exact_retained_scored_authority(self):
        from pathlib import Path
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture
        from AgMark.shared.runtime.orchestration.replay import disabled_validation_summaries
        from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore
        with tempfile.TemporaryDirectory() as directory:
            terminal, _, store, _ = accepted_fixture(Path(directory))
            before = tuple(terminal.treatment_observations)
            values = disabled_validation_summaries(terminal)
            retained = ValidationArtifactStore(store)
            retained.retain(terminal, values)
            self.assertEqual(tuple(v.to_dict() for v in values), tuple(v.to_dict() for v in retained.read(terminal)))
            self.assertEqual(before, terminal.treatment_observations)
            terminal.revalidate(store)
