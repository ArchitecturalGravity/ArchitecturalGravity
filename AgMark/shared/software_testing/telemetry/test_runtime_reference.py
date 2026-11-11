"""Capture reference versions describe provenance, not runtime permission."""
import copy
import unittest

from AgMark.shared.adapters.Codex_CLI import load_registration
from AgMark.shared.telemetry.runtime_reference import UPDATE_EXTENSION, build_runtime_advisory, read_runtime_advisory
from AgMark.shared.software_testing.adapters.codex_cli import test_runner as runner_fixture


class RuntimeReferenceTests(unittest.TestCase):
    def test_shipped_metadata_retains_only_capture_version_and_revision(self):
        metadata = load_registration()['extensions'][UPDATE_EXTENSION]
        self.assertEqual({
            'revision': 'runtime-neutral-capture-v1',
            'reference_runtime_version': '0.166.0',
        }, metadata)

    def test_match_mismatch_and_unknown_are_nonblocking_and_retain_numeric_core(self):
        registration = load_registration()
        before = copy.deepcopy(registration)
        reference = registration['extensions'][UPDATE_EXTENSION]['reference_runtime_version']
        for version, expected, normalized in (
            (reference, 'match', reference),
            ('codex-cli ' + reference, 'match', reference),
            ('0.166.0-alpha.1', 'match', '0.166.0'),
            ('0.159.0', 'mismatch', '0.159.0'),
            ('9.9.9-rc.1+build.2', 'mismatch', '9.9.9'),
            (None, 'unknown', None), ('', 'unknown', None), ('latest', 'unknown', None),
            ('0.166', 'unknown', None), ('0.166.0\nprivate', 'unknown', None),
            ('1.' + '1' * 128 + '.0', 'unknown', None),
        ):
            with self.subTest(version=version):
                value = build_runtime_advisory(registration, {'runtime_version': version})
                self.assertEqual(expected, value['status'])
                self.assertEqual(normalized, value['selected_runtime_version'])
                self.assertEqual(reference, value['reference_runtime_version'])
                self.assertIs(False, value['blocking'])
                self.assertNotIn('reference_kind', value)
                self.assertNotIn('validation_status', value)
        self.assertEqual(before, registration)

    def test_undeclared_adapter_has_no_advisory_and_invalid_reference_is_unknown(self):
        registration = load_registration()
        del registration['extensions'][UPDATE_EXTENSION]
        self.assertIsNone(build_runtime_advisory(registration, {'runtime_version': '9.9.9'}))
        for metadata in ({}, None, {'reference_runtime_version': 'latest'},
                         {'reference_runtime_version': None}, {'reference_runtime_version': ''}):
            with self.subTest(metadata=metadata):
                registration['extensions'][UPDATE_EXTENSION] = metadata
                value = build_runtime_advisory(registration, {'runtime_version': '0.166.0'})
                self.assertEqual('unknown', value['status'])
                self.assertIsNone(value['reference_runtime_version'])
                self.assertIs(False, value['blocking'])

    def test_malformed_or_contradictory_retained_metadata_is_unknown_not_a_forged_match(self):
        valid = build_runtime_advisory(load_registration(), {'runtime_version': '9.9.9'})
        self.assertEqual('mismatch', read_runtime_advisory(valid)['status'])
        invalid = (None, [], 'asserted match', {},
            {**valid, 'status': 'match'}, {**valid, 'status': []},
            {**valid, 'blocking': True}, {**valid, 'schema_version': 'unsupported'},
            {**valid, 'selected_runtime_version': {'private': 'value'}},
            {**valid, 'unexpected': 'field'})
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual('unknown', read_runtime_advisory(value)['status'])
        matched = {**valid, 'selected_runtime_version': valid['reference_runtime_version'], 'status': 'match'}
        self.assertEqual('match', read_runtime_advisory(matched)['status'])
        matched['status'] = 'mismatch'
        self.assertEqual('unknown', read_runtime_advisory(matched)['status'])

    def test_metadata_update_is_reflected_without_rewriting_prior_advisory(self):
        registration = load_registration()
        before = build_runtime_advisory(registration, {'runtime_version': '9.9.9'})
        saved = copy.deepcopy(before)
        registration['extensions'][UPDATE_EXTENSION].update(
            revision='runtime-neutral-capture-v2', reference_runtime_version='9.9.9')
        after = build_runtime_advisory(registration, {'runtime_version': '9.9.9'})
        self.assertEqual('mismatch', before['status'])
        self.assertEqual('match', after['status'])
        self.assertEqual('runtime-neutral-capture-v2', after['update_revision'])
        self.assertEqual(saved, before)

    def test_legacy_qualifiers_are_rejected_and_never_emitted_in_new_advisories(self):
        registration = load_registration()
        valid = build_runtime_advisory(registration, {'runtime_version': '9.9.9'})
        expected = read_runtime_advisory(valid)
        for kind, status in (('implementation_target', 'controlled_tests_only'),
                             ('source_audit', 'runtime_probe_passed'),
                             (None, None), (['ignored'], {'obsolete': 'claim'})):
            with self.subTest(kind=kind, status=status):
                legacy = {**valid, 'reference_kind': kind, 'validation_status': status}
                retained = copy.deepcopy(legacy)
                self.assertEqual("unknown", read_runtime_advisory(legacy)["status"])
                self.assertEqual(retained, legacy)
                registration['extensions'][UPDATE_EXTENSION].update(
                    reference_kind=kind, validation_status=status)
                self.assertEqual(valid, build_runtime_advisory(registration, {'runtime_version': '9.9.9'}))
        self.assertNotIn('reference_kind', expected)
        self.assertNotIn('validation_status', expected)

    def test_legacy_metadata_still_checks_version_comparison_and_schema(self):
        legacy = {**build_runtime_advisory(load_registration(), {'runtime_version': '9.9.9'}),
            'reference_kind': 'implementation_target', 'validation_status': 'controlled_tests_only'}
        for change in ({'status': 'match'}, {'blocking': True}, {'schema_version': 'unsupported'},
                       {'unexpected': 'field'}):
            with self.subTest(change=change):
                self.assertEqual('unknown', read_runtime_advisory({**legacy, **change})['status'])


class RuntimeReferenceExecutionTests(unittest.TestCase):
    def setUp(self):
        self.owner = runner_fixture.CodexCliAdapterTests()
        self.owner.setUp()
        self.addCleanup(self.owner.doCleanups)

    def test_reference_mismatch_does_not_block_native_or_wsl_selected_runtime(self):
        reference = load_registration()['extensions'][UPDATE_EXTENSION]['reference_runtime_version']
        for mode in ('native', 'wsl'):
            for version in (reference, '0.159.0', '0.166.0-alpha.1', '9.9.9-rc.1+build.2'):
                with self.subTest(mode=mode, version=version):
                    transport = runner_fixture.FakeCodexTransport(version=version)
                    runner = getattr(self.owner, '_' + mode + '_runner')(transport)
                    self.addCleanup(runner.close)
                    boundary = runner_fixture._boundary(launch_mode=mode, runtime_version=version)
                    observation = runner.execute(runner_fixture._request(boundary))
                    self.assertEqual('completed', observation['terminal_status'])
                    self.assertEqual(version.split('-')[0].split('+')[0], observation['extensions']['openai.codex_cli:execution']['observed_runtime_version'])
                    self.assertTrue(any(call['input_bytes'] == b'adapter prompt\n\nadapter input'
                                        for call in transport.calls))

    def test_reference_warning_does_not_relax_accepted_version_drift_check(self):
        for mode in ('native', 'wsl'):
            with self.subTest(mode=mode):
                transport = runner_fixture.FakeCodexTransport(version='9.9.9')
                runner = getattr(self.owner, '_' + mode + '_runner')(transport)
                self.addCleanup(runner.close)
                boundary = runner_fixture._boundary(launch_mode=mode, runtime_version='0.166.0')
                observation = runner.execute(runner_fixture._request(boundary, suffix='drift'))
                self.assertEqual('unsupported', observation['terminal_status'])
                self.assertEqual('codex_cli_version_unsupported', observation['attempts'][0]['error_code'])
                self.assertFalse(observation['extensions']['openai.codex_cli:execution']['provider_submitted'])
                self.assertFalse(any(call['input_bytes'] is not None for call in transport.calls))

    def test_transient_full_version_binding_rejects_same_core_suffix_drift(self):
        from AgMark.shared.runtime.identity.runtime_version import retained_runtime_version
        for mode in ('native', 'wsl'):
            for actual, bound, expected in (
                ('1.2.3-privateA', '1.2.3-privateA', 'completed'),
                ('1.2.3-privateB', '1.2.3-privateA', 'unsupported'),
                ('1.2.3-privateA', None, 'unsupported')):
                with self.subTest(mode=mode, actual=actual, bound=bound):
                    transport = runner_fixture.FakeCodexTransport(version=actual)
                    runner = getattr(self.owner, '_' + mode + '_runner')(transport)
                    self.addCleanup(runner.close)
                    if bound is not None:
                        runner._launch_selection['expected_runtime_version'] = bound
                    boundary = runner_fixture._boundary(launch_mode=mode, runtime_version='1.2.3')
                    observation = runner.execute(runner_fixture._request(boundary))
                    self.assertEqual(expected, observation['terminal_status'])
                    self.assertEqual(retained_runtime_version(actual), observation['extensions']['openai.codex_cli:execution']['observed_runtime_version'])
                    self.assertNotIn('privateA', str(observation))
                    self.assertNotIn('privateB', str(observation))
