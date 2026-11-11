"""Validated registration provenance produces a frozen advisory, never a gate."""
import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from AgMark.shared.application import ApplicationPlanRequest, ApplicationRegistrationSource, PlanningApplicationSession
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef
from AgMark.shared.runtime.orchestration import PlannedCaseInput
from AgMark.shared.validation import BenchmarkDiscoveryCandidate
from AgMark.shared.telemetry.runtime_reference import UPDATE_EXTENSION, PLAN_EXTENSION
from AgMark.shared.adapters.Codex_CLI import load_registration
from AgMark.shared.software_testing.integration import test_application_boundary as fixture


def planning_fixture(*, version='9.9.9', mode='native', metadata=True, caller_extensions=None, update=None, capture_mode=None, reasoning_effort=None):
    benchmark = fixture._registration('reference.benchmark', 'benchmark')
    benchmark_validation = fixture._validated(benchmark, 'reference-benchmark')
    runner = fixture._registration('openai.codex-cli', 'runner')
    if metadata:
        runner['extensions'][UPDATE_EXTENSION] = copy.deepcopy(
            load_registration()['extensions'][UPDATE_EXTENSION] if update is None else update)
    runner_validation = fixture._validated(runner, 'reference-runner')
    session = PlanningApplicationSession(
        benchmark_candidates=(BenchmarkDiscoveryCandidate(package_root='AgMark/Reference_Fixture',
            registration_source_id='reference-benchmark', registration=benchmark,
            registration_validation=benchmark_validation),),
        runner_sources=(ApplicationRegistrationSource(registration_source_id='reference-runner',
            registration=runner, registration_validation=runner_validation),))
    controls = {'launch_mode': mode, 'memory_policy': 'disabled'}
    if capture_mode is not None:
        controls['capture_mode'] = capture_mode
    if reasoning_effort is not None:
        controls['reasoning_effort'] = reasoning_effort
    boundary = ExecutionBoundary.build(boundary_id='reference-boundary',
        framework=IdentityRef('arcgrav.framework', '1.0.0'), runner=IdentityRef('openai.codex-cli', '1.0.0'),
        provider_runtime={'runtime_id': 'openai.codex-cli', 'runtime_version': version,
                          'provider': 'OpenAI', 'access_method': 'cli', 'model': 'fixture-model'},
        controls=controls, environment={'runtime_family': 'provider-free-controlled-fixture'})
    request = ApplicationPlanRequest(
        benchmark=IdentityRef('reference.benchmark', '1.0.0', sha256=benchmark_validation.registration_sha256),
        case_set=IdentityRef('reference.cases', '1.0.0', sha256='sha256:' + '1' * 64),
        treatment_set=IdentityRef('reference.treatments', '1.0.0', sha256='sha256:' + '2' * 64),
        cases=(PlannedCaseInput('case-reference', 'sha256:' + '3' * 64),), treatments=('treatment-reference',),
        repetitions=1, execution_boundary=boundary, golden_required=False,
        extensions=caller_extensions or {})
    return session, request


class RuntimeReferencePlanningTests(unittest.TestCase):
    def test_matching_mismatching_and_unknown_native_and_wsl_plans_remain_acceptable(self):
        reference = load_registration()['extensions'][UPDATE_EXTENSION]['reference_runtime_version']
        for mode in ('native', 'wsl'):
            for version, status in ((reference, 'match'), (reference + '-alpha.1', 'match'), ('0.166.0', 'mismatch'), ('9.9.9', 'mismatch'), (None, 'unknown')):
                with self.subTest(mode=mode, version=version):
                    session, request = planning_fixture(version=version, mode=mode)
                    boundary_before = request.execution_boundary.to_dict()
                    plan = session.build_plan(request)
                    advisory = plan.to_dict()['extensions'][PLAN_EXTENSION]
                    self.assertEqual(status, advisory['status'])
                    self.assertEqual(version.split('-')[0].split('+')[0] if version else None, advisory['selected_runtime_version'])
                    self.assertIs(False, advisory['blocking'])
                    accepted = session.accept_plan()
                    self.assertEqual(plan.plan_sha256, accepted.plan().plan_sha256)
                    self.assertEqual(advisory, accepted.plan().to_dict()['extensions'][PLAN_EXTENSION])
                    self.assertEqual(boundary_before, request.execution_boundary.to_dict())
                    self.assertNotIn(PLAN_EXTENSION, request.extensions)
                    self.assertEqual(1, len(accepted.plan().observations))

    def test_advisory_only_plan_is_retained_at_execution_admission(self):
        from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination
        from AgMark.shared.runtime.orchestration import admit_accepted_execution
        session, request = planning_fixture()
        plan = session.build_plan(request)
        snapshot = session.accept_plan()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FilesystemArtifactStore(PublicationDestination.benchmark_owned(root / 'evidence', benchmark_root=root))
            admit_accepted_execution(generation_id='generation-reference-retained', snapshot=snapshot,
                benchmark=request.benchmark, case_set=request.case_set, treatment_set=request.treatment_set,
                execution_boundary=request.execution_boundary, benchmark_root=root, artifact_store=store)
            retained = store.root / 'generation-reference-retained' / 'accepted-plan' / 'plan.json'
            self.assertTrue(retained.is_file())
            self.assertEqual(plan.canonical_bytes, retained.read_bytes())

    def test_caller_cannot_override_registered_advisory_or_create_one_without_metadata(self):
        forged = {PLAN_EXTENSION: {'status': 'match', 'blocking': True, 'reference_runtime_version': '9.9.9'}}
        for metadata in (True, False):
            with self.subTest(metadata=metadata):
                session, request = planning_fixture(metadata=metadata, caller_extensions=forged)
                plan = session.build_plan(request)
                if metadata:
                    advisory = plan.to_dict()['extensions'][PLAN_EXTENSION]
                    self.assertEqual('mismatch', advisory['status'])
                    self.assertIs(False, advisory['blocking'])
                    self.assertNotIn('reference_kind', advisory)
                    self.assertNotIn('validation_status', advisory)
                else:
                    self.assertNotIn(PLAN_EXTENSION, plan.to_dict()['extensions'])
                self.assertIsNotNone(session.accept_plan())

    def test_updated_registration_affects_new_plan_but_not_accepted_history(self):
        session, request = planning_fixture()
        old = session.build_plan(request)
        accepted = session.accept_plan()
        retained = copy.deepcopy(accepted.plan().to_dict())
        update = copy.deepcopy(load_registration()['extensions'][UPDATE_EXTENSION])
        update.update(revision='runtime-neutral-capture-v2', reference_runtime_version='9.9.9')
        next_session, next_request = planning_fixture(update=update)
        new = next_session.build_plan(next_request)
        self.assertEqual('match', new.to_dict()['extensions'][PLAN_EXTENSION]['status'])
        self.assertEqual('mismatch', retained['extensions'][PLAN_EXTENSION]['status'])
        self.assertEqual(retained, accepted.plan().to_dict())
        self.assertNotEqual(old.plan_sha256, new.plan_sha256)
        self.assertEqual(request.execution_boundary.fingerprint, next_request.execution_boundary.fingerprint)
