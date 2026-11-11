"""Raw token-event facts remain distinct from unavailable direct provider telemetry."""
import base64
import copy
import json
import unittest
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import rollout, stdout, extract, aggregate
from AgMark.shared.adapters.Codex_CLI.session import extract_session_measurements
from AgMark.shared.evaluation.telemetry.session_metrics import SESSION_METRICS, RAW_METRICS
from AgMark.gui.views.results import ResultRowProjection


class RawTelemetryScopeTests(unittest.TestCase):
    def test_repeated_cumulative_events_are_counted_not_provider_requests(self):
        rows = rollout().splitlines()
        rows.insert(-1, rows[-2])  # A second export of usage is still a token event.
        envelope, record = extract(b'\n'.join(rows) + b'\n')
        roles = envelope['extensions'][SESSION_METRICS]['roles']
        self.assertEqual('4.0.0', record['extraction_version'])
        self.assertEqual(2, roles['token_usage_event_count']['value'])
        self.assertEqual('session_counter', roles['token_usage_event_count']['kind'])
        self.assertEqual(2, roles['inference_call_count']['value'])
        self.assertEqual('token_event_proxy', roles['inference_call_count']['kind'])
        self.assertEqual(100, envelope['roles']['input_tokens']['value'])
        for role in RAW_METRICS.keys() - {'token_usage_event_count'}:
            self.assertIsNone(roles[role]['value'])
            self.assertEqual('unavailable', roles[role]['availability'])
        cells = ResultRowProjection('t', 1, 'retained', 'Scored', '✓', measurements=roles).to_table_row().cells
        self.assertEqual('2 events', cells['token_usage_event_count'].text)
        self.assertIn('estimate: token-event proxy', cells['inference_call_count'].text)
        self.assertEqual('Unavailable', cells['provider_request_count'].text)
        self.assertIn('not requests', roles['provider_request_count']['details']['reason'])

    def test_old_versions_are_rejected_without_fallback(self):
        for version in ('3.0.0', '3.1.0', '3.2.0', '3.3.0'):
            record = {'availability': 'retained', 'thread_id': 'trial', 'extraction_version': version,
                      'content_base64': base64.b64encode(rollout()).decode()}
            with self.assertRaisesRegex(ValueError, "unsupported Codex session extraction version"):
                extract_session_measurements(record, stdout(), runtime_version='0.159.0', process_complete=True)

    def test_partial_events_and_item_timing_never_supply_direct_timings(self):
        a, _ = extract(complete=False)
        roles = aggregate([a])['roles']
        self.assertEqual('partial', roles['token_usage_event_count']['availability'])
        for role in RAW_METRICS.keys() - {'token_usage_event_count'}:
            self.assertIsNone(roles[role]['value'])
            self.assertIn('Original rollout', roles[role]['meaning'])
