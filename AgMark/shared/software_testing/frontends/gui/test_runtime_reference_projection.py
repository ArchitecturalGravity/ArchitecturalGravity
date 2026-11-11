"""Headless projection and codec checks for frozen runtime reference provenance."""
import json
import unittest
from unittest.mock import patch

from AgMark.gui.application.projector import SharedApplicationProjector, _capture_runtime_presentation
from AgMark.gui.application.history import _encode, _decode
from AgMark.gui.shell.projections import CurrentRunProjection, RunPlanProjection
from AgMark.shared.adapters.Codex_CLI import load_registration
from AgMark.shared.telemetry.runtime_reference import UPDATE_EXTENSION
from AgMark.shared.software_testing.integration.test_runtime_reference_planning import planning_fixture


class RuntimeReferenceProjectionTests(unittest.TestCase):
    def projection(self, version='9.9.9', *, mode='native', metadata=True):
        session, request = planning_fixture(version=version, mode=mode, metadata=metadata)
        plan = session.build_plan(request)
        return plan, request, SharedApplicationProjector._plan_summary(None, plan, request)

    def test_native_and_wsl_mismatch_projects_warning_and_explicit_nonblocking_message(self):
        reference = load_registration()['extensions'][UPDATE_EXTENSION]['reference_runtime_version']
        for mode in ('native', 'wsl'):
            with self.subTest(mode=mode):
                plan, request, (boundary, projection) = self.projection(mode=mode)
                details = dict(boundary.runtime_details)
                self.assertEqual('9.9.9', details['Runtime version'])
                self.assertEqual(plan.execution_boundary_fingerprint, boundary.boundary_fingerprint)
                self.assertNotIn(boundary.boundary_fingerprint, boundary.ordered_values)
                self.assertEqual(f'Canonical plan {plan.plan_sha256}', projection.outputs)
                self.assertNotIn(projection.outputs, projection.ordered_values)
                self.assertIn(reference, details['Capture'])
                self.assertEqual([f'• {reference}', '• Mode: Not recorded', '• Cache validation replays'],
                    details['Capture'].splitlines())
                self.assertFalse({'Runtime version', 'Capture'} & dict(projection.execution_details).keys())
                self.assertEqual(('Planned observations', 'Iterations'),
                    tuple(label for label, _ in projection.execution_details))
                self.assertEqual('warning', projection.capture_runtime_advisory_tone)
                self.assertEqual('status-warning', projection.capture_runtime_advisory_icon_role)
                self.assertIn('9.9.9', projection.capture_runtime_advisory)
                self.assertIn(reference, projection.capture_runtime_advisory)
                self.assertIn('does not block benchmark runs', projection.capture_runtime_advisory)

    def test_match_removes_warning_unknown_is_neutral_and_missing_metadata_is_absent(self):
        reference = load_registration()['extensions'][UPDATE_EXTENSION]['reference_runtime_version']
        for version, metadata, expectation in ((reference, True, 'match'), (None, True, 'unknown'), ('9.9.9', False, 'absent')):
            with self.subTest(expectation=expectation):
                _, _, (boundary, projection) = self.projection(version, metadata=metadata)
                self.assertEqual('neutral', projection.capture_runtime_advisory_tone)
                self.assertEqual('status-neutral', projection.capture_runtime_advisory_icon_role)
                if expectation == 'unknown':
                    self.assertIn('could not be compared', projection.capture_runtime_advisory)
                    self.assertNotIn('version mismatch', projection.capture_runtime_advisory)
                    self.assertEqual('Unavailable', dict(boundary.runtime_details)['Runtime version'])
                else:
                    self.assertIsNone(projection.capture_runtime_advisory)
                if expectation == 'absent':
                    self.assertEqual({'Capture': '• Cache validation replays'}, dict(boundary.runtime_details))

    def test_cache_validation_replays_appear_only_in_capture_when_enabled(self):
        for enabled in (True, False):
            for metadata in (True, False):
                with self.subTest(enabled=enabled, metadata=metadata):
                    session, request = planning_fixture(metadata=metadata,
                        caller_extensions={'arcgrav.runtime:cache-validation-replays': enabled})
                    plan = session.build_plan(request)
                    boundary, summary = SharedApplicationProjector._plan_summary(None, plan, request)
                    capture = dict(boundary.runtime_details).get('Capture', '')
                    self.assertEqual(enabled, '• Cache validation replays' in capture.splitlines())
                    self.assertNotIn('Enabled', capture)
                    self.assertNotIn('Disabled by user', capture)
                    self.assertNotIn('Cache validation replays', dict(summary.execution_details))

    def test_old_plan_presentation_does_not_consult_current_registration(self):
        plan, request, expected = self.projection()
        with patch('AgMark.shared.adapters.Codex_CLI.load_registration', side_effect=AssertionError('must use frozen plan')):
            actual = SharedApplicationProjector._plan_summary(None, plan, request)
        self.assertEqual(expected, actual)
        self.assertEqual('warning', actual[1].capture_runtime_advisory_tone)

    def test_capture_mode_uses_the_exact_plan_boundary_not_a_new_selection(self):
        plans = []
        for mode, label in (('session', 'Session'), ('telemetry', 'Telemetry'), ('deep_telemetry', 'Deep Telemetry')):
            session, request = planning_fixture(capture_mode=mode)
            plan = session.build_plan(request)
            boundary, _ = SharedApplicationProjector._plan_summary(None, plan, request)
            self.assertEqual(f'• Mode: {label}', dict(boundary.runtime_details)['Capture'].splitlines()[1])
            plans.append((plan, request))
        original_plan, original_request = plans[0]
        _, changed_request = plans[1]
        with self.assertRaisesRegex(ValueError, 'does not match the retained plan'):
            SharedApplicationProjector._plan_summary(None, original_plan, changed_request)
        boundary, _ = SharedApplicationProjector._plan_summary(None, original_plan, original_request)
        self.assertEqual('• Mode: Session', dict(boundary.runtime_details)['Capture'].splitlines()[1])

    def test_projection_codec_round_trip_preserves_warning_and_provenance(self):
        for version in ('9.9.9', None, '0.166.0-alpha.1'):
            with self.subTest(version=version):
                _, _, (boundary, projection) = self.projection(version)
                current = CurrentRunProjection(run_identity='generation-reference', state_label='Completed',
                    state_tone='success', timestamp='2026-11-04T00:00:00Z',
                    execution_boundary=boundary, run_plan=projection, heading='Prior Run', is_prior_run=True,
                    delete_run_available=True)
                encoded = json.loads(json.dumps(_encode(current)))
                reopened = _decode(encoded)
                self.assertEqual(current, reopened)
                self.assertEqual(projection.capture_runtime_advisory_icon_role,
                    reopened.run_plan.capture_runtime_advisory_icon_role)
                self.assertEqual(projection.execution_details, reopened.run_plan.execution_details)
                self.assertEqual(boundary.runtime_details, reopened.execution_boundary.runtime_details)
                self.assertFalse(reopened.accept_plan_available)
                self.assertFalse(reopened.start_benchmark_available)

    def test_advisory_projection_cannot_gain_blocking_error_tone(self):
        base = dict(treatments='one', cases='one', execution='one', evaluation='one', outputs='one')
        for tone in ('error', 'blocked', 'success', ''):
            with self.subTest(tone=tone), self.assertRaises(ValueError):
                RunPlanProjection(**base, capture_runtime_advisory='notice', capture_runtime_advisory_tone=tone)

    def test_legacy_qualifiers_are_rejected_as_unknown_in_projection(self):
        from AgMark.shared.telemetry.runtime_reference import PLAN_EXTENSION, build_runtime_advisory
        valid = build_runtime_advisory(load_registration(), {'runtime_version': '9.9.9'})
        expected = _capture_runtime_presentation({'extensions': {PLAN_EXTENSION: valid}})
        for kind, status in (('implementation_target', 'controlled_tests_only'),
                             ('controlled_runtime_probe', 'runtime_probe_passed'),
                             (None, None), ('undeclared', ['ignored'])):
            with self.subTest(kind=kind, status=status):
                legacy = {**valid, 'reference_kind': kind, 'validation_status': status}
                details, text, tone = _capture_runtime_presentation({'extensions': {PLAN_EXTENSION: legacy}})
                self.assertEqual('neutral', tone)
                self.assertIn('could not be compared', text)
                self.assertNotEqual(expected, (details, text, tone))

    def test_absent_advisory_has_no_notice_and_malformed_claim_is_neutral_unknown(self):
        from AgMark.shared.telemetry.runtime_reference import PLAN_EXTENSION, build_runtime_advisory
        for document in ({'extensions': {'arcgrav.runtime:cache-validation-replays': False}}, {'extensions': None}):
            with self.subTest(document=document):
                self.assertEqual(((), None, 'neutral'), _capture_runtime_presentation(document))
        valid = build_runtime_advisory(load_registration(), {'runtime_version': '9.9.9'})
        for value in (None, [], 'untrusted assertion', {}, {**valid, 'status': 'match'},
                      {**valid, 'blocking': True}, {**valid, 'selected_runtime_version': ['invalid']}):
            with self.subTest(value=value):
                details, text, tone = _capture_runtime_presentation({'extensions': {PLAN_EXTENSION: value}})
                self.assertEqual('neutral', tone)
                self.assertIn('could not be compared', text)
                self.assertNotIn('version mismatch', text)

    def test_model_includes_frozen_reasoning_level_without_changing_execution(self):
        for effort, label in (('low', 'Low'), ('medium', 'Medium'), ('high', 'High'),
                              ('xhigh', 'Extra High'), ('ultra', 'Ultra'), ('none', 'None')):
            with self.subTest(effort=effort):
                session, request = planning_fixture(reasoning_effort=effort)
                plan = session.build_plan(request)
                before = (plan.canonical_bytes, request.execution_boundary.canonical_bytes)
                boundary, _ = SharedApplicationProjector._plan_summary(None, plan, request)
                self.assertEqual(f'fixture-model ({label})', boundary.model)
                self.assertEqual(before, (plan.canonical_bytes, request.execution_boundary.canonical_bytes))

    def test_model_without_recorded_reasoning_does_not_invent_a_default(self):
        for effort in (None, '', False):
            with self.subTest(effort=effort):
                session, request = planning_fixture(reasoning_effort=effort)
                plan = session.build_plan(request)
                boundary, _ = SharedApplicationProjector._plan_summary(None, plan, request)
                self.assertEqual('fixture-model', boundary.model)

    def test_model_reasoning_rejects_a_different_boundary_even_without_capture_metadata(self):
        session, request = planning_fixture(reasoning_effort='medium', metadata=False)
        plan = session.build_plan(request)
        _, changed_request = planning_fixture(reasoning_effort='high', metadata=False)
        with self.assertRaisesRegex(ValueError, 'does not match the retained plan'):
            SharedApplicationProjector._plan_summary(None, plan, changed_request)
        boundary, _ = SharedApplicationProjector._plan_summary(None, plan, request)
        self.assertEqual('fixture-model (Medium)', boundary.model)
