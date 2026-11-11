"""Existing stock policy stays inferred and tied to its retained original source."""
import base64
import copy
import unittest
from AgMark.shared.adapters.Codex_CLI.session import extract_session_measurements
from AgMark.shared.evaluation.telemetry.root_cache_policy import project_root_cache_policies, SESSION_RECORD
from AgMark.shared.evaluation.telemetry.session_metrics import SESSION_METRICS
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import rollout, stdout


def sample(version='0.159.0'):
    record = dict(availability='retained', thread_id='trial', generation_id='g', observation_id='o', attempt=1,
                  content_base64=base64.b64encode(rollout()).decode())
    envelope, record = extract_session_measurements(record, stdout(), runtime_version=version, process_complete=True)
    return ({'observation_id': 'o', 'accepted_generation_id': 'g', 'attempts': [{'attempt': 1}],
             'extensions': {SESSION_RECORD: record}}, {'attempt': 1}, envelope, 'sha256:' + 'a' * 64)


class RootCachePolicyProjectionTests(unittest.TestCase):
    def test_exact_retained_root_policy_is_inferred_not_wire_or_helper_evidence(self):
        source = sample()
        before = copy.deepcopy(source)
        result = project_root_cache_policies([source])[0]
        self.assertEqual('inferred', result['availability'])
        self.assertEqual('original_run_root', result['scope'])
        self.assertEqual('call_1', result['policy']['cache_key_value'])
        self.assertFalse(result['policy']['cache_key_observed'])
        self.assertFalse(result['policy']['derived_contexts_observed'])
        self.assertNotIn('derived_context_policy', result['policy'])
        self.assertEqual(before, source)
        self.assertEqual(2, len(result['evidence_references']))

    def test_unaudited_runtime_and_missing_retained_record_are_unavailable(self):
        for version in ('0.159.0-alpha.3', '0.159.0-privateCustomer+privateHost', '0.160.0', 'codex-cli 0.159.0'):
            source = sample(version)
            result = project_root_cache_policies([source])[0]
            self.assertNotIn('privateCustomer', str(source))
            self.assertNotIn('privateHost', str(source))
            # Reconstruction uses numeric retained identity, not the raw label.
            envelope, retained = extract_session_measurements(source[0]['extensions'][SESSION_RECORD], b'',
                runtime_version=source[2]['runtime_version'], process_complete=True)
            self.assertEqual(source[2], envelope)
            self.assertEqual(source[0]['extensions'][SESSION_RECORD], retained)
            self.assertEqual('unavailable', result['availability'])
            self.assertEqual('unaudited_codex_runtime_version', result['reason'])
        value = sample(); value[0]['extensions'].clear()
        self.assertIsNone(project_root_cache_policies([value])[0]['policy'])

    def test_observation_generation_attempt_and_source_mismatches_are_unavailable(self):
        for field, replacement in (('observation_id', 'other'), ('generation_id', 'other'), ('attempt', 2), ('thread_id', 'other'), ('sha256', 'sha256:' + 'b' * 64)):
            value = sample(); value[0]['extensions'][SESSION_RECORD][field] = replacement
            with self.subTest(field=field):
                self.assertEqual('unavailable', project_root_cache_policies([value])[0]['availability'])
        value = sample(); value[0]['attempts'].append({'attempt': 2})
        self.assertEqual('root_policy_attempt_scope_not_established', project_root_cache_policies([value])[0]['reason'])

    def test_observed_or_foreign_policy_and_replay_metadata_cannot_substitute(self):
        for key, replacement in (('cache_key_observed', True), ('derived_contexts_observed', True),
                                 ('cache_key_provenance', 'wire_observed'), ('root_thread_id', 'helper')):
            value = sample()
            record = value[0]['extensions'][SESSION_RECORD]
            record['cache_policy'][key] = replacement
            value[2]['extensions'][SESSION_METRICS]['extensions']['openai.codex_cli:session-capture'] = {k: copy.deepcopy(v) for k, v in record.items() if k != 'content_base64'}
            with self.subTest(key=key):
                self.assertEqual('unavailable', project_root_cache_policies([value])[0]['availability'])
        value = sample()
        value[0]['extensions']['replay'] = value[0]['extensions'].pop(SESSION_RECORD)
        self.assertEqual('unavailable', project_root_cache_policies([value])[0]['availability'])
