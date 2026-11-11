"""Original capture integration through the production runner, entirely offline."""
import json
import unittest
from urllib.request import Request, urlopen

from AgMark.shared.adapters.Codex_CLI import CodexCliRunner
from AgMark.shared.adapters.execution import InvocationCancelled
from AgMark.shared.software_testing.adapters.codex_cli.test_runner import (
    FakeCodexTransport, _boundary, _request,
)


def request(profile='telemetry', version='0.159.0', suffix='a', diagnostic_consent=False):
    boundary = _boundary(runtime_version=version)
    boundary['controls'].append({'name': 'capture_mode', 'value': profile})
    if diagnostic_consent:
        from AgMark.shared.telemetry.profile import DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
        boundary['controls'].append({'name': 'diagnostic_privacy_acknowledged',
                                     'value': DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT})
    return _request(boundary, suffix=suffix)


def runner(transport):
    return CodexCliRunner(transport=transport, platform_name='posix',
        executable_resolver=lambda _value: '/fixture/codex')


class MultiSignalTransport(FakeCodexTransport):
    def __init__(self, version='0.159.0'):
        super().__init__(version=version)
        self.endpoints = []

    def run(self, argv, **kwargs):
        if kwargs.get('input_bytes') is not None:
            self.assert_local_capture(argv)
        return super().run(argv, **kwargs)

    def assert_local_capture(self, argv):
        import re
        endpoints = re.findall(r'endpoint="(http://127\.0\.0\.1:\d+/v1/[^\"]+)"', ' '.join(argv))
        assert len(endpoints) == 3
        self.endpoints.extend(endpoints)
        for endpoint in endpoints:
            if endpoint.endswith('/logs'):
                body = {'resourceLogs': [{'scopeLogs': [{'scope': {'name': 'codex'}, 'logRecords': [
                    {'timeUnixNano': '100', 'attributes': [
                        {'key': 'event.name', 'value': {'stringValue': 'codex.api_request'}},
                        {'key': 'duration_ms', 'value': {'intValue': '12'}},
                        {'key': 'authorization', 'value': {'stringValue': 'Bearer offline-secret'}},
                    ]}]}]}]}
            elif endpoint.endswith('/traces'):
                body = {'resourceSpans': [{'scopeSpans': [{'spans': [
                    {'name': 'responses.stream_request', 'traceId': 'a'*32, 'spanId': 'b'*16,
                     'startTimeUnixNano': '100', 'endTimeUnixNano': '200'}]}]}]}
            else:
                body = {'resourceMetrics': [{'scopeMetrics': [{'scope': {'name': 'codex'}, 'metrics': [
                    {'name': 'codex.backend.request.duration', 'unit': 'ms', 'histogram': {
                        'aggregationTemporality': 2, 'dataPoints': [{'count': '2', 'sum': 24,
                        'bucketCounts': ['0', '2'], 'explicitBounds': [10],
                        'startTimeUnixNano': '100', 'timeUnixNano': '200'}]}}]}]}]}
            with urlopen(Request(endpoint, data=json.dumps(body).encode(), headers={'Content-Type':'application/json'}), timeout=2) as result:
                assert result.status == 200


class OriginalCaptureIntegrationTests(unittest.TestCase):
    def test_real_local_multi_signal_receivers_seal_original_evidence(self):
        from AgMark.shared.telemetry.evidence import validate_manifest
        transport = MultiSignalTransport()
        observation = runner(transport).execute(request())
        self.assertEqual('completed', observation['terminal_status'])
        extensions = observation['extensions']
        capture = extensions['agmark.telemetry:capture']
        self.assertTrue(validate_manifest(capture))
        self.assertEqual('original', capture['authority'])
        self.assertTrue(capture['sealed'])
        for signal in ('otel_logs', 'otel_traces', 'otel_metrics'):
            self.assertGreater(capture['sources'][signal]['received_events'], 0)
        self.assertNotIn('offline-secret', json.dumps(capture))
        self.assertIn('agmark.telemetry:normalized', extensions)
        self.assertEqual('disabled', capture['sources']['diagnostics']['state'])

    def test_repeated_invocations_have_distinct_receivers_and_evidence(self):
        transport = MultiSignalTransport()
        adapter = runner(transport)
        first = adapter.execute(request(suffix='first'))['extensions']['agmark.telemetry:capture']
        second = adapter.execute(request(suffix='second'))['extensions']['agmark.telemetry:capture']
        self.assertNotEqual(first['invocation_id'], second['invocation_id'])
        self.assertEqual(first['sources']['otel_logs']['received_events'], second['sources']['otel_logs']['received_events'])
        self.assertNotEqual(transport.endpoints[0], transport.endpoints[3])

    def test_capture_profiles_ignore_cli_version_and_never_downgrade(self):
        for version in ('0.159.0', '0.160.0', '9.9.9'):
            for profile in ('telemetry', 'deep_telemetry'):
                with self.subTest(version=version, profile=profile):
                    transport = MultiSignalTransport(version=version)
                    observation = runner(transport).execute(request(
                        profile=profile, version='unrelated-version',
                        suffix=f'{profile}-{version}', diagnostic_consent=profile == 'deep_telemetry'))
                    self.assertEqual('completed', observation['terminal_status'])
                    self.assertTrue(any(call['input_bytes'] is not None for call in transport.calls))
                    capture = observation['extensions']['agmark.telemetry:capture']
                    self.assertEqual(profile, capture['profile']['id'])
                    self.assertEqual(version, capture['runtime']['version'])
                    self.assertEqual('supported', capture['runtime']['capability_status'])
                    for signal in ('otel_logs', 'otel_traces', 'otel_metrics'):
                        self.assertGreater(capture['sources'][signal]['received_events'], 0)
                    self.assertEqual(3, len(transport.endpoints))

    def test_version_probe_failure_does_not_downgrade_capture_mode(self):
        class NoVersionTransport(MultiSignalTransport):
            def run(self, argv, **kwargs):
                if argv[-1:] == ('--version',):
                    return {'returncode': 1, 'stdout': b'', 'stderr': b''}
                return super().run(argv, **kwargs)
        for profile in ('telemetry', 'deep_telemetry'):
            with self.subTest(profile=profile):
                transport = NoVersionTransport()
                observation = runner(transport).execute(request(
                    profile=profile, version=None, diagnostic_consent=profile == 'deep_telemetry'))
                self.assertEqual('completed', observation['terminal_status'])
                capture = observation['extensions']['agmark.telemetry:capture']
                self.assertEqual(profile, capture['profile']['id'])
                self.assertNotIn('version', capture['runtime'])
                self.assertEqual('supported', capture['runtime']['capability_status'])

    def test_diagnostics_requires_explicit_privacy_choice(self):
        transport = FakeCodexTransport(version='0.159.0')
        observation = runner(transport).execute(request(profile='deep_telemetry'))
        self.assertEqual('unsupported', observation['terminal_status'])
        self.assertEqual([], transport.calls)

    def test_session_request_keeps_uninstrumented_launch(self):
        transport = FakeCodexTransport(version='0.159.0')
        observation = runner(transport).execute(request(profile='session'))
        self.assertEqual('completed', observation['terminal_status'])
        self.assertNotIn('agmark.telemetry:capture', observation['extensions'])
        self.assertFalse(any('otel.' in arg for c in transport.calls for arg in c['argv']))

    def test_session_mode_accepts_unaudited_runtime_without_capture(self):
        transport = FakeCodexTransport(version='9.9.9')
        observation = runner(transport).execute(request(profile='session', version='9.9.9'))
        self.assertEqual('completed', observation['terminal_status'])
        self.assertTrue(any(call['input_bytes'] is not None for call in transport.calls))
        self.assertNotIn('agmark.telemetry:capture', observation['extensions'])

    def test_cancelled_process_still_seals_partial_capture(self):
        partial = b'{"type":"thread.started","thread_id":"partial-thread"}\n'
        transport = FakeCodexTransport(version='0.159.0', actual_exception=InvocationCancelled(stdout=partial))
        observation = runner(transport).execute(request())
        self.assertEqual('cancelled', observation['terminal_status'])
        capture = observation['extensions']['agmark.telemetry:capture']
        self.assertTrue(capture['sealed'])
        self.assertEqual('partial', capture['completeness']['status'])
        self.assertEqual('cancelled', capture['process_status']['status'])

    def test_collector_start_failure_prevents_profile_downgrade_and_exec(self):
        from unittest.mock import patch
        transport = FakeCodexTransport(version='0.159.0')
        with patch('AgMark.shared.telemetry.collector.MultiSignalCollector.start', side_effect=OSError('offline fixture')):
            observation = runner(transport).execute(request())
        self.assertEqual('unsupported', observation['terminal_status'])
        self.assertFalse(any(call['input_bytes'] is not None for call in transport.calls))

    def test_stream_telemetry_failure_does_not_change_benchmark_outcome(self):
        from unittest.mock import patch
        class StreamTransport(FakeCodexTransport):
            def run_streaming(self, argv, **kwargs):
                result = self.run(argv, **{key: kwargs[key] for key in
                    ('input_bytes', 'cwd', 'env', 'timeout_ms')})
                if kwargs.get('on_stdout') is not None:
                    kwargs['on_stdout'](result['stdout'])
                return result
        transport = StreamTransport(version='0.159.0')
        with patch('AgMark.shared.telemetry.CaptureSession.ingest_stdout', side_effect=RuntimeError('fixture failure')):
            observation = runner(transport).execute(request())
        self.assertEqual('completed', observation['terminal_status'])
        capture = observation['extensions']['agmark.telemetry:capture']
        self.assertGreater(capture['sources']['stdout']['partial'], 0)

    def test_wsl_overrides_are_positional_not_shell_interpolation(self):
        adapter = runner(FakeCodexTransport())
        argv = adapter._wsl_exec_argv({'launcher':'wsl','distribution':'Ubuntu','executable':'codex'}, 'model')
        actual = adapter._capture_argv(argv, ('otel.exporter="none"',), 'wsl')
        self.assertIn('"$@"', actual[6])
        self.assertIn('unset CODEX_ROLLOUT_TRACE_ROOT', actual[6])
        self.assertEqual(('-c', 'otel.exporter="none"'), actual[-2:])
        self.assertNotIn('otel.exporter=', actual[6])
