"""Runtime-owned startup authority, host-local execution, and durable source proof."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.validation.codex_cache.startup import StartupCollector, StartupRecord
from AgMark.shared.validation.codex_cache.capture import digest
from AgMark.shared.validation.codex_cache.capabilities import admit_controlled_probe
from AgMark.shared.validation.codex_cache.collector import canonical_capture_spans
from AgMark.shared.validation.codex_cache.source_evidence import validate_source
from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture
from AgMark.shared.runtime.orchestration import TreatmentCaseInput, TreatmentPrompt
from AgMark.shared.runtime.orchestration.replay import validate_finalized_run
from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore

from AgMark.shared.software_testing.validation.codex_cache.synthetic_probes import synthetic_http_probe


def controlled_probe(binary, runtime_version="0.159.0"):
    probe = synthetic_http_probe(runtime_version)
    return {"runtime_version": "codex-cli " + runtime_version, "runtime_binary_sha256": binary,
        "validation_id": probe["validation_id"], "returncode": 0,
        "provider_requests": [{"ordinal": 1}, {"ordinal": 2}],
        "spans": canonical_capture_spans(probe["spans"]), "rejected_payloads": 0,
        "purpose": "Controlled HTTP generation with independently supplied synthetic counters; not live-provider behavior."}


@unittest.skipUnless(os.name == 'posix', 'Controlled subprocess fixture uses a POSIX launcher')
class StartupIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.home = self.root / 'home'; self.home.mkdir()
        self.work = self.root / 'work'; self.work.mkdir()
        self.binary = self.root / 'codex'
        self.runtime_version = '0.159.0'
        self.binary.write_text('#!/usr/bin/env python3\nimport sys,os\nfrom pathlib import Path\n'
            "if '--version' in sys.argv: print('codex-cli 0.159.0'); sys.exit(0)\n"
            "home=Path(os.environ['CODEX_HOME'])\n"
            "assert home.joinpath('AGENTS.md').read_text()=='before-scored'\n"
            "assert home.joinpath('auth.json').read_text()=='credential-canary'\n"
            "assert not list(Path.cwd().iterdir())\n"
            "home.joinpath('AGENTS.md').write_text('replay-mutated')\n"
            "Path('local-only').write_text('replay-output')\n")
        self.binary.chmod(0o700)
        (self.home / 'AGENTS.md').write_text('before-scored')
        (self.home / 'auth.json').write_text('credential-canary')
        self.environment = {'PATH': os.environ['PATH'], 'HOME': str(self.home), 'CODEX_HOME': str(self.home)}
        self.collector = StartupCollector()
        self.addCleanup(self.collector.close)

    def set_runtime_version(self, runtime_version):
        self.binary.write_text(self.binary.read_text().replace(
            'codex-cli ' + self.runtime_version, 'codex-cli ' + runtime_version))
        self.runtime_version = runtime_version

    def capture(self, observation='observation', generation='generation', mode='native', frame=b'prompt\n\ninput', model='fixture-model', effort=None, runtime_version=None):
        reasoning_flags = ('-c', 'model_reasoning_effort=' + json.dumps(effort)) if effort else ()
        args = (str(self.binary), 'exec', '--model', model, '--approve-for-me', '--ignore-user-config',
                '--skip-git-repo-check', '--color', 'never', '--json', *reasoning_flags, '-')
        metadata = {'mode': mode, 'executable': str(self.binary)}
        if mode == 'wsl':
            launcher = self.root / 'wsl'
            launcher.write_text('#!/bin/sh\nshift 3\nexec "$@"\n'); launcher.chmod(0o700)
            args = (str(launcher), '--distribution', 'Ubuntu', '--exec', 'sh', '-lc', 'registered wrapper',
                    'arcgrav-codex', str(self.binary), model, *reasoning_flags)
            metadata['distribution'] = 'Ubuntu'
        self.collector(observation_id=observation, generation_id=generation, argv=args,
            environment=self.environment, cwd=self.work, runtime_version=runtime_version or self.runtime_version, launch_metadata=metadata,
            framed_request_sha256=digest(frame), external_provider_submission=True)
        self.assertIn(observation, self.collector.records, self.collector.diagnostics)
        return self.collector.records[observation]

    def test_pre_score_profile_is_restored_even_after_scored_mutation_and_disposed(self):
        record = self.capture()
        snapshot = record.revalidate()
        (self.home / 'AGENTS.md').write_text('after-scored')
        self.assertEqual(snapshot, record.current())
        spans, runtime, status, _, _ = record.capture('12345678-1234-1234-1234-123456789012', b'prompt\n\ninput', 3)
        self.assertEqual('completed', status)
        self.assertEqual('exact_stock', runtime.status)
        self.assertEqual('after-scored', (self.home / 'AGENTS.md').read_text())
        self.assertEqual([], list(self.work.iterdir()))
        self.assertNotIn('credential-canary', json.dumps(record.public_document()))
        self.assertNotIn('before-scored', json.dumps(record.public_document()))
        self.collector.close()
        self.assertFalse(Path(snapshot['retained_home']).exists())
        self.assertEqual([], list(self.root.glob('agmark-replay-*')))

    def test_changed_runtime_cannot_launch_replay(self):
        record = self.capture()
        self.binary.write_text(self.binary.read_text()+'\n# mutated\n')
        _, runtime, status, reasons, _ = record.capture('12345678-1234-1234-1234-123456789012', b'prompt\n\ninput', 3)
        self.assertEqual('unavailable', status)
        self.assertEqual('non_comparable', runtime.status)
        self.assertIn('replay_starting_configuration_changed', reasons)

    def test_version_drift_retains_noncomparable_identity(self):
        record = self.capture()
        self.binary.write_text(self.binary.read_text().replace("codex-cli 0.159.0", "codex-cli 0.160.0"))
        _, runtime, status, reasons, actual = record.capture('12345678-1234-1234-1234-123456789012', b'prompt\n\ninput', 3)
        self.assertEqual('unavailable', status)
        self.assertEqual('non_comparable', runtime.status)
        self.assertEqual('0.160.0', runtime.runtime_version.value)
        self.assertEqual('codex-cli 0.160.0', actual['version'])

    def test_unsafe_policy_never_probes_or_launches_replay(self):
        from AgMark.shared.software_testing.runtime.test_scoring_orchestration import _boundary
        from AgMark.shared.runtime.identity import ExecutionBoundary
        from AgMark.shared.runtime.orchestration.replay import _managed_replay
        record = self.capture()
        doc = _boundary().to_dict()
        controls = {x['name']: x['value'] for x in doc['controls']}; controls['tool_policy'] = 'unrestricted'
        boundary = ExecutionBoundary.build(boundary_id=doc['boundary_id'], framework=doc['framework'],
            runner=doc['runner'], provider_runtime=doc['provider_runtime'], controls=controls,
            environment={x['name']: x['value'] for x in doc['environment']})
        with patch.object(StartupRecord, 'current') as current, patch.object(StartupRecord, 'capture') as capture:
            result = _managed_replay(record, boundary=boundary, generation_id='generation', observation_id='observation',
                validation_id='12345678-1234-1234-1234-123456789012', prompt=b'prompt', case_input=b'input',
                registration_sha256='sha256:'+'a'*64, capture_evidence={}, source_evidence={}, capability_cache={})
            current.assert_not_called(); capture.assert_not_called()
        self.assertEqual('unavailable', result[4])
        self.assertEqual(('replay_safety_policy_not_admitted',), result[5])

    def test_wsl_dispatch_runs_host_worker_inside_selected_distribution(self):
        record = self.capture(mode='wsl')
        self.assertEqual('wsl', record.public_document()['launch_mode'])
        self.assertEqual(record.revalidate(), record.current())
        self.assertEqual(('--distribution', 'Ubuntu', '--exec'), record.transport.prefix[1:])
        # This verifies real dispatch via a controlled launcher, not actual WSL conformance.

    def test_wsl_replay_preserves_selected_model_and_reasoning_arguments(self):
        record = self.capture(mode='wsl', model='selected-model', effort='high')
        args = record.revalidate()['args']
        self.assertEqual('selected-model', args[args.index('--model') + 1])
        self.assertIn('model_reasoning_effort="high"', args)
        self.assertEqual('-', args[-1])

    def test_nonempty_or_symlinked_startup_remains_unavailable(self):
        (self.work / 'unknown').write_text('unselected-state')
        with self.assertRaises(AssertionError): self.capture()
        self.assertIn('observation', self.collector.diagnostics)
        (self.work / 'unknown').unlink()
        (self.home / 'AGENTS.md').unlink()
        (self.home / 'AGENTS.md').symlink_to(self.binary)
        with self.assertRaises(AssertionError): self.capture()

    def test_startup_authority_rejects_forged_guard(self):
        record = self.capture()
        with self.assertRaises(ValueError): replace(record, _guard=object()).revalidate()

    def test_managed_replay_retains_independent_sources_and_rejects_tampering(self):
        (self.root / 'accepted').mkdir()
        terminal, boundary, store, _ = accepted_fixture(
            self.root / 'accepted', runtime_version=self.runtime_version)
        observations = [json.loads(raw) for raw in terminal.treatment_observations]
        before = {r.reference: store.read_verified(r) for r in terminal.artifact_index.artifacts}
        frame = b'runtime-scoring-prompt\n\nruntime-scoring-case-input'
        records = {o['observation_id']: self.capture(o['observation_id'], terminal.generation_id, frame=frame, model=boundary.to_dict()['provider_runtime']['model']) for o in observations}
        record = next(iter(records.values()))
        probe = controlled_probe(record.revalidate()['binary_sha256'], self.runtime_version)
        caps, proof = admit_controlled_probe(probe, binary_sha256=probe['runtime_binary_sha256'])
        self.assertEqual({**probe, 'runtime_version': 'codex-cli ' + self.runtime_version.split('-')[0].split('+')[0]}, validate_source('probe', proof['probe']))
        calls = []
        events = []
        from AgMark.shared.runtime.orchestration.activity import ActivityPublisher
        activity = ActivityPublisher(terminal.generation_id, events.append)
        def capabilities():
            self.assertEqual("capability", events[-1].phase)
            return caps, proof
        def capture(actual_record, validation_id, frame, timeout):
            self.assertEqual("replay", events[-1].phase)
            self.assertEqual(len(calls)+1, events[-1].current)
            calls.append(validation_id)
            spans = json.loads(json.dumps(probe['spans']))
            for span in spans: span['attributes']['validation_id'] = validation_id
            from AgMark.shared.software_testing.validation.codex_cache.fixtures import runtime
            from AgMark.shared.validation.codex_cache.metrics import observed
            rt = runtime(self.runtime_version.split("-")[0].split("+")[0]); binary = observed(probe['runtime_binary_sha256'], 'controlled-test-binary')
            return tuple(spans), replace(rt, stock_binary_sha256=binary, observed_binary_sha256=binary), 'completed', (), actual_record.revalidate()
        captures, sources = {}, {}
        with patch.object(StartupRecord, 'capabilities', side_effect=capabilities), patch.object(StartupRecord, 'capture', capture):
            values = validate_finalized_run(terminal=terminal, artifact_store=store, boundary=boundary,
                case_inputs=(TreatmentCaseInput('case-runtime-scoring', b'runtime-scoring-case-input'),),
                treatment_prompts=(TreatmentPrompt('treatment-runtime-scoring', b'runtime-scoring-prompt'),),
                startup_records=records, capture_evidence=captures, source_evidence=sources, activity=activity)
        self.assertEqual(1, sum(e.phase == "capability" for e in events))
        self.assertTrue(all(e.total == len(observations) for e in events))
        self.assertEqual(len(observations), len(calls))
        self.assertEqual(len(observations), values[0].coverage.validation_replays_attempted)
        retained = ValidationArtifactStore(store)
        reopened = retained.retain(terminal, values, capture_evidence=captures, source_evidence=sources)
        self.assertEqual([v.to_dict() for v in values], [v.to_dict() for v in reopened])
        self.assertEqual(before, {r.reference: store.read_verified(r) for r in terminal.artifact_index.artifacts})
        path = next((retained.root / terminal.generation_id).glob('source-*.json'))
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError): retained.read(terminal)
