"""Current capability admission is runtime-neutral, exact, and fail-closed.

All executable/probe data here are controlled fixtures, not evidence that an
installed Codex release or a real provider exports the admitted trace surface.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.validation.codex_cache.capabilities import admit_controlled_probe, load_capabilities
from AgMark.shared.validation.codex_cache.capture import (
    ReplayCaptureOptions, ReplayStartingState, capture_replay, digest,
)
from AgMark.shared.validation.codex_cache.diagnostics import PROFILE
from AgMark.shared.validation.codex_cache.normalization import normalize_spans
from AgMark.shared.validation.codex_cache.source_evidence import validate_source
from AgMark.shared.validation.codex_cache.startup import HostTransport, StartupRecord
from AgMark.shared.software_testing.validation.codex_cache.fixtures import (
    accepted_fixture, capabilities, configuration,
)
from AgMark.shared.software_testing.validation.codex_cache.synthetic_probes import (
    synthetic_dual_probe, synthetic_http_probe, write_http_bundle,
)
from AgMark.shared.software_testing.validation.codex_cache import test_startup_integration as startup_fixture


VERSIONS = ('0.160.0', '0.166.0', '9.9.9', '1.0.0-rc.1+build.2')


class RuntimeNeutralCapabilityTests(unittest.TestCase):
    def test_selected_version_survives_http_and_websocket_admission_and_reopening(self):
        for version in VERSIONS:
            for factory in (synthetic_http_probe, synthetic_dual_probe):
                with self.subTest(version=version, transport=factory.__name__), tempfile.TemporaryDirectory() as directory:
                    probe = factory(version)
                    caps, proof = admit_controlled_probe(probe,
                        binary_sha256=probe['runtime_binary_sha256'], runtime_version=version)
                    document = json.loads(proof['capabilities'])
                    self.assertEqual(version.split('-')[0].split('+')[0], document['runtime_version'])
                    self.assertNotIn('rc.1', str(proof))
                    self.assertNotIn('build.2', str(proof))
                    method = ('controlled_stock_http_websocket_sampling_span_ancestry_v1'
                              if 'websocket_probe' in probe else 'controlled_stock_http_sampling_span_ancestry_v1')
                    self.assertEqual({method}, {v.method for v in caps.fields.values()})
                    for kind, raw in proof.items():
                        validate_source(kind, raw)
                    root = Path(directory)
                    (root / 'probe.json').write_bytes(proof['probe'])
                    path = root / 'capabilities.json'
                    path.write_bytes(proof['capabilities'])
                    reopened = load_capabilities(path, binary_sha256=probe['runtime_binary_sha256'],
                        runtime_version=version, evidence_sha256=digest(path.read_bytes()))
                    self.assertEqual(caps.to_dict(), reopened.to_dict())
                    source = probe.get('websocket_probe', probe)
                    requests, reasons = normalize_spans(source['spans'], validation_id=source['validation_id'],
                        capabilities=reopened, evidence_reference=digest(proof['probe']), profile=PROFILE)
                    self.assertEqual((), reasons)
                    self.assertEqual(3 if 'websocket_probe' in probe else 2, len(requests))

    def test_same_core_suffix_drift_fails_before_retained_projection(self):
        probe = synthetic_http_probe('1.0.0-privateA')
        with self.assertRaises(ValueError):
            admit_controlled_probe(probe, binary_sha256=probe['runtime_binary_sha256'], runtime_version='1.0.0-privateB')
        caps, proof = admit_controlled_probe(probe, binary_sha256=probe['runtime_binary_sha256'], runtime_version='1.0.0-privateA')
        self.assertNotIn('privateA', str(proof))
        unsafe = json.loads(proof['probe'])
        unsafe['runtime_version'] = 'codex-cli 1.0.0-privateA'
        with self.assertRaises(ValueError):
            validate_source('probe', json.dumps(unsafe).encode())

    def test_current_runtime_does_not_authorize_mismatched_binary_or_version(self):
        probe = synthetic_http_probe('0.166.0')
        for binary, version in ((probe['runtime_binary_sha256'], '0.159.0'), ('sha256:' + 'b' * 64, '0.166.0')):
            with self.subTest(binary=binary, version=version):
                with self.assertRaises(ValueError):
                    admit_controlled_probe(probe, binary_sha256=binary, runtime_version=version)
        with tempfile.TemporaryDirectory() as directory:
            path = write_http_bundle(directory, '0.166.0') / 'synthetic-capabilities.json'
            for binary, version in ((probe['runtime_binary_sha256'], '0.159.0'), ('sha256:' + 'b' * 64, '0.166.0')):
                result = load_capabilities(path, binary_sha256=binary, runtime_version=version,
                    evidence_sha256=digest(path.read_bytes()))
                self.assertTrue(all(field.status == 'unavailable' for field in result.fields.values()))

    def test_new_release_does_not_bypass_failed_or_changed_exporter_proof(self):
        for failure in ('process', 'missing_spans', 'rejected_payload', 'counter', 'websocket_identity'):
            with self.subTest(failure=failure):
                probe = synthetic_dual_probe('9.9.9')
                if failure == 'process':
                    probe['returncode'] = 1
                elif failure == 'missing_spans':
                    probe['spans'] = []
                elif failure == 'rejected_payload':
                    probe['rejected_payloads'] = 1
                elif failure == 'counter':
                    next(s for s in probe['spans'] if s['name'] == 'handle_responses')['attributes']['gen_ai.usage.input_tokens'] += 1
                else:
                    probe['websocket_probe']['runtime_version'] = 'codex-cli 0.166.0'
                with self.assertRaises(ValueError):
                    admit_controlled_probe(probe, binary_sha256=probe['runtime_binary_sha256'], runtime_version='9.9.9')

    def test_legacy_methods_and_profiles_are_rejected_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = write_http_bundle(directory)
            path = root / 'synthetic-capabilities.json'
            document = json.loads(path.read_bytes())
            for field in document['fields'].values():
                field['method'] = 'controlled_stock_0.159.0_http_sampling_span_ancestry'
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                load_capabilities(path, binary_sha256=document['runtime_binary_sha256'],
                    runtime_version='0.159.0', evidence_sha256=digest(path.read_bytes()))
        probe = synthetic_dual_probe('0.166.0')
        caps, _ = admit_controlled_probe(probe, binary_sha256=probe['runtime_binary_sha256'])
        self.assertEqual('stock-capability-diagnostics-v2', PROFILE)
        for profile in ('stock-0.159.0-diagnostics-v1', 'unknown-profile'):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                normalize_spans(probe['spans'], validation_id=probe['validation_id'],
                    capabilities=caps, evidence_reference='fixture:current', profile=profile)

    def test_legacy_unknown_and_mixed_capability_methods_do_not_normalize_requests(self):
        probe = synthetic_dual_probe('0.166.0')
        caps, _ = admit_controlled_probe(probe, binary_sha256=probe['runtime_binary_sha256'])
        for method, mixed in (('controlled_stock_0.159.0_http_websocket_sampling_span_ancestry', False),
                              ('unknown-method', False), ('controlled_stock_http_sampling_span_ancestry_v1', True)):
            with self.subTest(method=method, mixed=mixed):
                fields = {name: replace(field, method=method) if not mixed or name == 'transport' else field
                          for name, field in caps.fields.items()}
                changed = replace(caps, fields=fields)
                for source in (probe, probe['websocket_probe']):
                    requests, reasons = normalize_spans(source['spans'], validation_id=source['validation_id'],
                        capabilities=changed, evidence_reference='fixture:legacy-or-mixed', profile=PROFILE)
                    self.assertEqual((), requests)
                    self.assertEqual(('unsupported_capability_method',), reasons)

    def test_malformed_and_unbounded_runtime_identity_is_not_admitted(self):
        for version in ('', 'latest', '0.166', '0.166.0 extra', '0.166.0\nsecret', '1.' + '1' * 128 + '.0'):
            with self.subTest(version=version):
                probe = synthetic_http_probe(version)
                with self.assertRaises(ValueError):
                    admit_controlled_probe(probe, binary_sha256=probe['runtime_binary_sha256'])


@unittest.skipUnless(os.name == 'posix', 'Controlled executable fixture uses a POSIX launcher')
class RuntimeNeutralStartupTests(unittest.TestCase):
    def fixture(self, version):
        owner = startup_fixture.StartupIntegrationTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        owner.set_runtime_version(version)
        return owner

    def test_selected_native_and_wsl_runtime_is_captured_without_release_allowlist(self):
        for version in VERSIONS:
            for mode in ('native', 'wsl'):
                with self.subTest(version=version, mode=mode):
                    owner = self.fixture(version)
                    record = owner.capture(mode=mode)
                    document = record.public_document()
                    self.assertEqual('codex-cli ' + version.split('-')[0].split('+')[0], document['runtime_version'])
                    self.assertEqual(document, validate_source('startup', json.dumps(document).encode()))
                    self.assertEqual(record.revalidate(), record.current())
                    _, runtime, status, reasons, _ = record.capture(
                        '12345678-1234-1234-1234-123456789012', b'prompt\n\ninput', 3)
                    self.assertEqual('completed', status)
                    self.assertEqual('exact_stock', runtime.status)
                    self.assertEqual(version.split('-')[0].split('+')[0], runtime.runtime_version.value)
                    self.assertEqual((), reasons)
                    # Controlled WSL launcher verifies dispatch, not actual WSL installation.

    def test_same_core_suffix_drift_blocks_replay_before_capture(self):
        owner = self.fixture('1.0.0-privateA')
        record = owner.capture()
        changed = {**record.revalidate(), 'version': 'codex-cli 1.0.0-privateB'}
        with patch.object(StartupRecord, 'current', return_value=changed):
            spans, runtime, status, reasons, _ = record.capture(
                '12345678-1234-1234-1234-123456789012', b'prompt\n\ninput', 3)
        self.assertEqual('non_comparable', runtime.status)
        self.assertEqual('unavailable', status)
        self.assertEqual((), spans)
        self.assertEqual('1.0.0', runtime.runtime_version.value)
        self.assertNotIn('private', str(runtime.to_dict()))

    def test_declared_startup_version_must_match_selected_executable(self):
        owner = self.fixture('0.166.0')
        with self.assertRaises(AssertionError):
            owner.capture(runtime_version='0.159.0')
        self.assertEqual({}, owner.collector.records)
        self.assertEqual('pre_invocation_startup_capture_unavailable', owner.collector.diagnostics['observation'])

    def test_startup_probe_must_match_captured_runtime_identity(self):
        owner = self.fixture('0.166.0')
        record = owner.capture()
        probe = startup_fixture.controlled_probe(record.revalidate()['binary_sha256'], '0.159.0')
        with patch.object(HostTransport, 'request', return_value=probe) as request:
            with self.assertRaises(ValueError):
                record.capabilities()
            self.assertEqual(1, request.call_count)

    def test_current_and_future_runtime_complete_managed_retention_without_scored_changes(self):
        for version in ('0.166.0', '9.9.9', '1.0.0-rc.1+build.2'):
            with self.subTest(version=version):
                owner = self.fixture(version)
                owner.test_managed_replay_retains_independent_sources_and_rejects_tampering()

    def test_capability_cache_is_bound_to_full_runtime_and_selected_host_identity(self):
        from AgMark.shared.runtime.identity import ExecutionBoundary
        from AgMark.shared.runtime.orchestration.replay import _managed_replay
        owner = self.fixture('0.166.0')
        accepted = owner.root / 'accepted'; accepted.mkdir()
        terminal, boundary, store, _ = accepted_fixture(accepted, runtime_version='0.166.0')
        observation = json.loads(terminal.treatment_observations[0])
        record = owner.capture(observation['observation_id'], terminal.generation_id, mode='wsl',
            frame=b'runtime-scoring-prompt\n\nruntime-scoring-case-input',
            model=boundary.to_dict()['provider_runtime']['model'])
        registration = next(r for r in terminal.artifact_index.artifacts if r.role == 'runner_registration')
        snapshot = record.revalidate()
        # Model host-observed identities, with subprocess behavior isolated. The
        # binary digest deliberately stays equal across every cache candidate.
        changed_version = replace(record, snapshot_bytes=json.dumps(
            {**snapshot, 'version': 'codex-cli 9.9.9'}).encode())
        changed_host = replace(record, transport=replace(record.transport,
            prefix=(record.transport.prefix[0], '--distribution', 'Debian', '--exec')))
        changed_snapshot_environment = replace(record, snapshot_bytes=json.dumps(
            {**snapshot, 'environment_sha256': 'sha256:' + 'e' * 64}).encode())
        changed_transport_environment = replace(record, transport=replace(record.transport,
            environment={**dict(record.transport.environment), 'MODELED_HOST_SELECTION': 'different'}))
        candidates = (record, record, changed_version, changed_host,
                      changed_snapshot_environment, changed_transport_environment, record)
        probes, cache = [], {}
        def probe(candidate):
            selected = candidate.revalidate()
            probes.append((selected['version'], candidate.transport.prefix, selected['environment_sha256']))
            evidence = startup_fixture.controlled_probe(selected['binary_sha256'],
                selected['version'].removeprefix('codex-cli '))
            return admit_controlled_probe(evidence, binary_sha256=selected['binary_sha256'],
                runtime_version=selected['version'].removeprefix('codex-cli '))
        with patch.object(StartupRecord, 'current', lambda candidate: candidate.revalidate()), \
                patch.object(StartupRecord, 'capabilities', probe), \
                patch.object(StartupRecord, 'capture', side_effect=ValueError('stop after capability admission')):
            for candidate in candidates:
                document = boundary.to_dict()
                provider = {**document['provider_runtime'],
                    'runtime_version': candidate.revalidate()['version'].removeprefix('codex-cli ')}
                selected_boundary = ExecutionBoundary.build(boundary_id=document['boundary_id'],
                    framework=document['framework'], runner=document['runner'], provider_runtime=provider,
                    controls={v['name']: v['value'] for v in document['controls']},
                    environment={v['name']: v['value'] for v in document['environment']})
                result = _managed_replay(candidate, boundary=selected_boundary,
                    generation_id=terminal.generation_id, observation_id=observation['observation_id'],
                    validation_id='12345678-1234-1234-1234-123456789012',
                    prompt=b'runtime-scoring-prompt', case_input=b'runtime-scoring-case-input',
                    registration_sha256=registration.sha256, capture_evidence={},
                    source_evidence={}, capability_cache=cache)
                self.assertEqual('supported', result[2].fields['request_boundaries'].status)
        self.assertEqual(5, len(probes))
        self.assertEqual(5, len(cache))
        self.assertEqual(1, sum(version == 'codex-cli 9.9.9' for version, prefix, environment in probes))
        self.assertEqual(1, sum('Debian' in prefix for version, prefix, environment in probes))

    def test_failed_probe_never_launches_capture_or_uses_old_capability_fallback(self):
        from AgMark.shared.runtime.orchestration.replay import _managed_replay
        owner = self.fixture('0.166.0')
        accepted = owner.root / 'accepted'; accepted.mkdir()
        terminal, boundary, store, _ = accepted_fixture(accepted, runtime_version='0.166.0')
        observation = json.loads(terminal.treatment_observations[0])
        frame = b'runtime-scoring-prompt\n\nruntime-scoring-case-input'
        record = owner.capture(observation['observation_id'], terminal.generation_id,
            frame=frame, model=boundary.to_dict()['provider_runtime']['model'])
        registration = next(r for r in terminal.artifact_index.artifacts if r.role == 'runner_registration')
        sources, captures, cache = {}, {}, {}
        with patch.object(StartupRecord, 'capabilities', side_effect=ValueError('unsupported exporter')) as probe, \
                patch.object(StartupRecord, 'capture') as capture, \
                patch('AgMark.shared.runtime.orchestration.replay.capture_replay') as fallback:
            result = _managed_replay(record, boundary=boundary, generation_id=terminal.generation_id,
                observation_id=observation['observation_id'], validation_id='12345678-1234-1234-1234-123456789012',
                prompt=b'runtime-scoring-prompt', case_input=b'runtime-scoring-case-input',
                registration_sha256=registration.sha256, capture_evidence=captures,
                source_evidence=sources, capability_cache=cache)
        probe.assert_called_once(); capture.assert_not_called(); fallback.assert_not_called()
        self.assertEqual('unavailable', result[4])
        self.assertEqual(('selected_host_replay_admission_unavailable',), result[5])
        self.assertTrue(all(field.status == 'unavailable' for field in result[2].fields.values()))
        self.assertEqual({}, cache)
        self.assertEqual({}, captures)
        self.assertEqual({'startup'}, {kind for kind, raw in sources.values()})


@unittest.skipUnless(os.name == 'posix', 'Controlled executable fixture uses a POSIX launcher')
class RuntimeNeutralDirectCaptureTests(unittest.TestCase):
    def test_capture_uses_selected_identity_and_rejects_drift_without_launch(self):
        for version in VERSIONS:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                executable = root / 'codex'
                executable.write_text('#!/usr/bin/env python3\nimport sys\n'
                    f"if '--version' in sys.argv: print('codex-cli {version}'); sys.exit(0)\n")
                executable.chmod(0o700)
                state = ReplayStartingState.capture(root, ())
                options = ReplayCaptureOptions(executable, (str(executable), 'exec'), {'PATH': os.environ['PATH']},
                    state, configuration().expected, configuration().observed, capabilities(),
                    version, digest(executable.read_bytes()), timeout_seconds=1)
                args = dict(validation_id='12345678-1234-1234-1234-123456789012',
                    prompt=b'prompt', case_input=b'input', temporary_root=root)
                _, runtime, status, reasons = capture_replay(options, **args)
                self.assertEqual(('exact_stock', version.split('-')[0].split('+')[0], 'completed', ()),
                    (runtime.status, runtime.runtime_version.value, status, reasons))
                # Version-response drift with an otherwise unchanged executable identity.
                with patch('AgMark.shared.validation.codex_cache.capture.subprocess.run',
                        return_value=subprocess.CompletedProcess([], 0, b'codex-cli 99.0.0\n', b'')), \
                        patch('AgMark.shared.validation.codex_cache.capture.subprocess.Popen') as launch:
                    _, runtime, status, reasons = capture_replay(options, **args)
                launch.assert_not_called()
                self.assertEqual('unavailable', status)
                self.assertEqual('non_comparable', runtime.status)
                self.assertEqual('99.0.0', runtime.runtime_version.value)
                self.assertIn('runtime_binary_or_version_mismatch', reasons)
                for code, response in ((1, ('codex-cli ' + version).encode()), (0, b'unknown runtime'), (0, b'\xff')):
                    with self.subTest(returncode=code, response=response), \
                            patch('AgMark.shared.validation.codex_cache.capture.subprocess.run',
                                return_value=subprocess.CompletedProcess([], code, response, b'')), \
                            patch('AgMark.shared.validation.codex_cache.capture.subprocess.Popen') as launch:
                        _, runtime, status, _ = capture_replay(options, **args)
                    launch.assert_not_called()
                    self.assertEqual('unavailable', status)
                    self.assertEqual('non_comparable', runtime.status)
                    self.assertEqual('unavailable', runtime.runtime_version.availability)
                # Version text alone cannot authorize a different executable.
                executable.write_text(executable.read_text() + '# changed binary\n')
                with patch('AgMark.shared.validation.codex_cache.capture.subprocess.run',
                        return_value=subprocess.CompletedProcess([], 0, ('codex-cli ' + version + '\n').encode(), b'')), \
                        patch('AgMark.shared.validation.codex_cache.capture.subprocess.Popen') as launch:
                    _, runtime, status, _ = capture_replay(options, **args)
                launch.assert_not_called()
                self.assertEqual('unavailable', status)
                self.assertEqual('non_comparable', runtime.status)
