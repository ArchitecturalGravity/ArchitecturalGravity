"""Actual archive reopen uses retained canonical plan reference metadata."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from AgMark.gui.application.history import HistoricalRun
from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination
from AgMark.shared.runtime.orchestration import admit_accepted_execution
from AgMark.shared.telemetry.runtime_reference import PLAN_EXTENSION, UPDATE_EXTENSION
from AgMark.shared.adapters.Codex_CLI import load_registration
from AgMark.shared.software_testing.integration.test_runtime_reference_planning import planning_fixture
from AgMark.shared.software_testing.validation.test_imported_run import seal_generation


class RuntimeReferenceHistoryTests(unittest.TestCase):
    def archive(self, *, version='9.9.9', metadata=True, corrupt_plan=False, capture_mode=None, retain_boundary=False, reasoning_effort=None, retain_plan=False):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        store = FilesystemArtifactStore(PublicationDestination.benchmark_owned(root / 'evidence', benchmark_root=root))
        session, request = planning_fixture(version=version, metadata=metadata, capture_mode=capture_mode, reasoning_effort=reasoning_effort)
        plan = session.build_plan(request)
        snapshot = session.accept_plan()
        gid = 'generation-reference-history'
        admit_accepted_execution(generation_id=gid, snapshot=snapshot, benchmark=request.benchmark,
            case_set=request.case_set, treatment_set=request.treatment_set,
            execution_boundary=request.execution_boundary, benchmark_root=root, artifact_store=store)
        folder = store.root / gid
        folder.mkdir(exist_ok=True)
        # Explicit archive fixture release: no provider execution or scoring claim.
        from dataclasses import replace
        from AgMark.shared.adapters._contract import validate_runner_request
        from AgMark.shared.software_testing.adapters.codex_cli.test_runner import _request
        from AgMark.shared.software_testing.adapters.execution.test_emission import _target, _result
        from AgMark.shared.adapters.execution import (
            emit_terminal_observation, validate_retained_parity_observation, ExecutionFailureKind)
        invocation = _request(request.execution_boundary.to_dict())
        slot = plan.observations[0]
        invocation.update(accepted_generation_id=gid, observation_id=slot.observation_id,
            request_id=slot.request_id, case_id=slot.case_id, treatment_id=slot.treatment_id,
            repetition=slot.repetition)
        validated = validate_runner_request(invocation)
        target = replace(_target(target_class='mock-model'), runtime_id='openai.codex-cli', runtime_version=version)
        observation = emit_terminal_observation(validated, target=target,
            execution=_result(terminal_status='unsupported', failure_kind=ExecutionFailureKind.PREFLIGHT_UNSUPPORTED,
                invocation_occurred=False, response_bytes=None),
            runner_id='openai.codex-cli', runner_version='1.0.0',
            framed_request=validated.prompt_bytes + b"\n\n" + validated.input_bytes,
            request_framing_mode='test-cli')
        validate_retained_parity_observation(observation)
        (folder / 'observation.json').write_text(json.dumps(observation))
        (store.root / ('.' + gid + '.terminal')).write_text('accepted')
        if retain_plan:
            plan_path = folder / 'accepted-plan' / 'plan.json'
            if not plan_path.exists():
                plan_path.parent.mkdir(parents=True, exist_ok=True)
                plan_path.write_bytes(plan.canonical_bytes)
        if retain_boundary:
            boundary_path = folder / 'reporting-authority' / 'execution-boundary.json'
            boundary_path.parent.mkdir(parents=True, exist_ok=True)
            boundary_path.write_bytes(request.execution_boundary.canonical_bytes)
        if corrupt_plan:
            path = folder / 'accepted-plan' / 'plan.json'
            document = json.loads(path.read_bytes())
            document['extensions'][PLAN_EXTENSION]['selected_runtime_version'] = '8.8.8'
            path.chmod(0o600)
            path.write_text(json.dumps(document))  # Intentionally keep the old canonical plan identity.
        archive = seal_generation(store.root, gid)
        return HistoricalRun(gid, store.root, 'Completed', 'success', 'Saved'), archive, plan

    def test_archive_reopen_preserves_frozen_reference_without_current_runtime_or_registration(self):
        reference = load_registration()['extensions'][UPDATE_EXTENSION]['reference_runtime_version']
        run, archive, plan = self.archive()
        before = archive.read_bytes()
        with (patch('subprocess.Popen', side_effect=AssertionError('No provider during history')),
              patch('AgMark.shared.adapters.Codex_CLI.load_registration', side_effect=AssertionError('No current registration during history'))):
            current, pages = run.prepare_presentation()
        details = dict(current.execution_boundary.runtime_details)
        self.assertEqual('9.9.9', details['Runtime version'])
        self.assertIn(reference, details['Capture'])
        self.assertEqual([f'• {reference}', '• Mode: Not recorded', '• Cache validation replays'],
            details['Capture'].splitlines())
        self.assertEqual((), current.run_plan.execution_details)
        self.assertEqual('warning', current.run_plan.capture_runtime_advisory_tone)
        self.assertIn('does not block', current.run_plan.capture_runtime_advisory)
        self.assertTrue(current.run_plan.capture_runtime_advisory.startswith('Recorded at plan build:'))
        self.assertTrue(current.is_prior_run)
        self.assertFalse(current.accept_plan_available)
        self.assertFalse(current.start_benchmark_available)
        self.assertEqual(before, archive.read_bytes())

    def test_matching_unknown_and_undeclared_archive_states_do_not_get_false_warning(self):
        reference = load_registration()['extensions'][UPDATE_EXTENSION]['reference_runtime_version']
        for version, metadata, unknown in ((reference, True, False), (None, True, True), ('9.9.9', False, False)):
            with self.subTest(version=version, metadata=metadata):
                run, archive, plan = self.archive(version=version, metadata=metadata)
                current, pages = run.prepare_presentation()
                self.assertEqual('neutral', current.run_plan.capture_runtime_advisory_tone)
                if unknown:
                    self.assertIn('could not be compared', current.run_plan.capture_runtime_advisory)
                else:
                    self.assertIsNone(current.run_plan.capture_runtime_advisory)
                if not metadata:
                    self.assertNotIn('Capture', dict(current.execution_boundary.runtime_details))

    def test_archive_integrity_cannot_replace_canonical_plan_identity(self):
        with self.assertRaises(ValueError):
            run, archive, plan = self.archive(corrupt_plan=True)
            run.prepare_presentation()

    def test_archive_capture_mode_comes_from_retained_matching_boundary(self):
        for mode, label in (('session', 'Session'), ('telemetry', 'Telemetry'), ('deep_telemetry', 'Deep Telemetry')):
            with self.subTest(mode=mode):
                run, archive, _ = self.archive(capture_mode=mode, retain_boundary=True)
                before = archive.read_bytes()
                with patch('AgMark.shared.adapters.Codex_CLI.load_registration', side_effect=AssertionError('No current selection')):
                    current, _ = run.prepare_presentation()
                self.assertEqual(f'• Mode: {label}',
                    dict(current.execution_boundary.runtime_details)['Capture'].splitlines()[1])
                self.assertEqual(before, archive.read_bytes())

    def test_legacy_archive_qualifiers_are_rejected_before_retention(self):
        from AgMark.shared.telemetry.runtime_reference import build_runtime_advisory
        def legacy_advisory(*args):
            return {**build_runtime_advisory(*args), 'reference_kind': 'implementation_target',
                'validation_status': 'controlled_tests_only'}
        with patch('AgMark.shared.telemetry.runtime_reference.build_runtime_advisory',
                   side_effect=legacy_advisory):
            session, request = planning_fixture(capture_mode='telemetry')
            with self.assertRaises(ValueError):
                session.build_plan(request)

    def test_archive_model_uses_retained_reasoning_or_omits_unknown_level(self):
        for reasoning, retain_boundary, metadata, retain_plan, expected in (
                ('high', True, True, False, 'fixture-model (High)'),
                ('xhigh', True, False, True, 'fixture-model (Extra High)'),
                ('high', True, False, False, 'See archived evidence'),
                (None, True, True, False, 'fixture-model'),
                ('high', False, True, False, 'See archived evidence')):
            with self.subTest(reasoning=reasoning, retain_boundary=retain_boundary, metadata=metadata):
                run, archive, _ = self.archive(reasoning_effort=reasoning,
                    retain_boundary=retain_boundary, metadata=metadata, retain_plan=retain_plan)
                before = archive.read_bytes()
                with patch('AgMark.shared.adapters.Codex_CLI.load_registration',
                           side_effect=AssertionError('No current selection during history')):
                    current, _ = run.prepare_presentation()
                self.assertEqual(expected, current.execution_boundary.model)
                self.assertEqual(before, archive.read_bytes())
