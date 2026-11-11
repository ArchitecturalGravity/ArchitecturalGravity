"""Controlled capability admission, safe unavailable replay and scored separation."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture, configuration, runtime
from AgMark.shared.validation.codex_cache.capabilities import load_capabilities, admit_controlled_probe
from AgMark.shared.software_testing.validation.codex_cache.synthetic_probes import synthetic_http_probe, write_http_bundle
from AgMark.shared.validation.codex_cache.comparison import compare_configuration
from AgMark.shared.validation.codex_cache.capture import ReplayStartingState
from AgMark.shared.validation.codex_cache.collector import sanitized_spans, observation_overrides
from AgMark.shared.validation.codex_cache.normalization import normalize_spans
from AgMark.shared.runtime.orchestration.replay import validate_finalized_run
from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore
from AgMark.shared.runtime.orchestration import TreatmentCaseInput, TreatmentPrompt



class ControlledReplayCapabilityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.evidence_root = write_http_bundle(directory.name)

    def evidence(self):
        probe = json.loads((self.evidence_root / "probe.json").read_text())
        path = self.evidence_root / "synthetic-capabilities.json"
        caps = load_capabilities(path, binary_sha256=probe["runtime_binary_sha256"], runtime_version="0.159.0",
            evidence_sha256="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
        return probe, caps

    def test_synthetic_sampling_ancestry_and_each_counter_are_independent(self):
        probe, caps = self.evidence()
        records, reasons = normalize_spans(probe["spans"], validation_id=probe["validation_id"], capabilities=caps, evidence_reference="fixture:synthetic-http-probe")
        self.assertEqual((), reasons)
        self.assertEqual(2, len(records))
        for i, record in enumerate(records,1):
            for field, expected in (("input_tokens",100*i),("cached_input_tokens",20*i),("cache_write_input_tokens",11*i),("output_tokens",7*i),("reasoning_tokens",3*i)):
                self.assertEqual(expected, record.fields[field].value)
            for field in ("request_duration_ms","response_id","cache_key_value","retry","reconnect"):
                self.assertEqual("unavailable",record.fields[field].availability)
                self.assertIsNone(record.fields[field].value)

    def test_ambiguous_missing_foreign_and_cyclic_span_identity_fail_closed(self):
        probe,caps = self.evidence()
        spans = probe["spans"]
        request = next(s for s in spans if s["name"]=="responses.stream_request")
        cases = (spans + [{**request, "name": "unobserved"}], [s for s in spans if s["name"]!="try_run_sampling_request"])
        for case in cases:
            records, reasons = normalize_spans(case,validation_id=probe["validation_id"],capabilities=caps,evidence_reference="fixture:probe")
            self.assertTrue(reasons)
            self.assertEqual((),records)
        self.assertEqual((),normalize_spans(spans,validation_id="foreign-validation",capabilities=caps,evidence_reference="fixture:probe")[0])

    def test_capability_binary_version_and_integrity_are_exact(self):
        probe,caps = self.evidence()
        path=self.evidence_root/'synthetic-capabilities.json'
        with self.assertRaises(ValueError):
            load_capabilities(path,binary_sha256=probe['runtime_binary_sha256'],runtime_version='0.159.0',evidence_sha256='sha256:'+'0'*64)
        other=load_capabilities(path,binary_sha256='sha256:'+'0'*64,runtime_version='0.159.0',evidence_sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(all(v.status=='unavailable' for v in other.fields.values()))

    def test_prompt_response_guardian_authorization_are_excluded_at_ingress(self):
        secret='content-canary'
        spans=sanitized_spans({'resourceSpans':[{'resource':{'attributes':[{'key':'Authorization','value':{'stringValue':secret}}]},'scopeSpans':[{'spans':[{'name':'handle_responses','attributes':[{'key':key,'value':{'stringValue':secret}} for key in ('prompt','response','guardian','Authorization')]}]}]}]})
        self.assertNotIn(secret,json.dumps(spans))
        with self.assertRaises(ValueError):
            observation_overrides('bad-id','http://127.0.0.1:1234/v1/traces')
        with self.assertRaises(ValueError):
            observation_overrides('12345678-1234-1234-1234-123456789012','https://external.invalid/v1/traces')

    def test_span_names_and_unvalidated_string_fields_cannot_retain_content(self):
        secret = "prompt-response-canary"
        spans = sanitized_spans({"resourceSpans": [{"scopeSpans": [{"spans": [{
            "name": secret, "traceId": secret, "spanId": secret,
            "attributes": [{"key": key, "value": {"stringValue": secret}}
                           for key in ("transport", "validation_id", "response_id", "gen_ai.usage.input_tokens")],
            "events": [{"name": secret, "attributes": [{"key": "from", "value": {"stringValue": secret}}]}],
        }]}]}]})
        self.assertNotIn(secret, json.dumps(spans))

    def test_capability_probe_and_assertions_are_revalidated(self):
        probe, _ = self.evidence()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = json.loads((self.evidence_root / "synthetic-capabilities.json").read_bytes())
            (root / "probe.json").write_bytes((self.evidence_root / "probe.json").read_bytes())
            path = root / "synthetic-capabilities.json"
            document["fields"]["request_duration_ms"]["status"] = "supported"
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                load_capabilities(path, binary_sha256=probe["runtime_binary_sha256"], runtime_version="0.159.0",
                    evidence_sha256="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
            path.write_bytes((self.evidence_root / "synthetic-capabilities.json").read_bytes())
            (root / "probe.json").write_text("{}")
            with self.assertRaises(ValueError):
                load_capabilities(path, binary_sha256=probe["runtime_binary_sha256"], runtime_version="0.159.0",
                    evidence_sha256="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())

    def test_http_experiment_cannot_admit_websocket_requests(self):
        probe, caps = self.evidence()
        for span in probe["spans"]:
            if span["name"] == "responses.stream_request":
                span["attributes"]["transport"] = "responses_websocket"
        records, reasons = normalize_spans(probe["spans"], validation_id=probe["validation_id"],
            capabilities=caps, evidence_reference="fixture:probe")
        self.assertEqual((), records)
        self.assertIn("transport_capability_not_demonstrated", reasons)

    def test_configuration_values_mismatch_and_missing_are_not_booleans(self):
        cfg=configuration()
        changed=dict(cfg.observed)
        changed['model']=replace(changed['model'],value='other-model')
        result=compare_configuration(cfg.expected,changed,runtime_equivalence=runtime())
        self.assertEqual('non_comparable',result.status)
        self.assertTrue(result.mismatch_reasons)
        self.assertEqual('other-model',result.observed['model'].value)

    def test_capture_restores_private_state_and_cleans_up_on_timeout(self):
        import os
        from AgMark.shared.validation.codex_cache.capture import ReplayCaptureOptions, capture_replay, digest
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import capabilities
        if os.name != "posix":
            self.skipTest("Controlled executable fixture uses a POSIX launcher")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "state").write_bytes(b"before")
            state = ReplayStartingState.capture(source, ("state",))
            executable = root / "controlled-codex"
            executable.write_text("#!/usr/bin/env python3\nimport os,sys,time\nfrom pathlib import Path\n"
                "if '--version' in sys.argv: print('codex-cli 0.159.0'); sys.exit(0)\n"
                "assert Path('state').read_bytes() == b'before'\nPath('state').write_bytes(b'after')\n"
                "Path(os.environ['CODEX_HOME'], 'private-state').write_bytes(b'private')\n"
                "if '--timeout' in sys.argv: time.sleep(5)\n")
            executable.chmod(0o700)
            for timeout in (False, True):
                argv = (str(executable), "exec", "--timeout" if timeout else "--complete")
                options = ReplayCaptureOptions(executable, argv, {"PATH": os.environ["PATH"]}, state,
                    configuration().expected, configuration().observed, capabilities(), "0.159.0",
                    digest(executable.read_bytes()), timeout_seconds=1)
                spans, rt, status, limits = capture_replay(options,
                    validation_id="12345678-1234-1234-1234-123456789012", prompt=b"prompt", case_input=b"input", temporary_root=root)
                self.assertEqual("failed" if timeout else "completed", status)
                self.assertEqual("exact_stock", rt.status)
                self.assertEqual(b"before", (source / "state").read_bytes())
                self.assertEqual([], list(root.glob("replay-*")))
                if timeout:
                    self.assertIn("replay_timeout", limits)

    def test_starting_state_is_restorable_and_exact_with_path_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'state').write_bytes(b'before')
            state=ReplayStartingState.capture(root,('state',))
            (root/'state').write_bytes(b'after')
            self.assertEqual(b'before',state.files['state'])
            with self.assertRaises(TypeError): state.files['state']=b'changed'
            with self.assertRaises(ValueError): ReplayStartingState({'../escape':b'x'},state.state_id)

class FinalizedReplayIsolationTests(unittest.TestCase):
    def test_real_finalized_lifecycle_unavailability_retention_and_exact_scored_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal,boundary,store,plan=accepted_fixture(Path(directory))
            before={r.reference:store.read_verified(r) for r in terminal.artifact_index.artifacts}
            args=dict(terminal=terminal,artifact_store=store,boundary=boundary,
                case_inputs=(TreatmentCaseInput('case-runtime-scoring',b'runtime-scoring-case-input'),),
                treatment_prompts=(TreatmentPrompt('treatment-runtime-scoring',b'runtime-scoring-prompt'),))
            with patch('AgMark.shared.runtime.orchestration.replay.capture_replay') as capture:
                summaries=validate_finalized_run(**args)
                capture.assert_not_called()
            self.assertEqual(2,summaries[0].coverage.scored_observation_count)
            self.assertEqual(0,summaries[0].coverage.validation_replays_attempted)
            self.assertTrue(all(r.status=='unavailable' and 'replay_start_state_not_reproducible' in r.limitations for r in summaries[0].replays))
            retained=ValidationArtifactStore(store)
            self.assertEqual(tuple(s.to_dict() for s in summaries),tuple(s.to_dict() for s in retained.retain(terminal,summaries)))
            self.assertEqual(before,{r.reference:store.read_verified(r) for r in terminal.artifact_index.artifacts})
            with self.assertRaises(ValueError): retained.retain(terminal,summaries)
            path=retained.root/terminal.generation_id/'treatment-0.json'
            path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaises(ValueError): retained.read(terminal)

    def test_retained_capture_reconstructs_and_tampering_is_rejected(self):
        from AgMark.shared.validation.codex_cache.metrics import replay_summary, treatment_summary
        from AgMark.shared.validation.codex_cache.capture import digest
        with tempfile.TemporaryDirectory() as directory:
            terminal, boundary, store, _ = accepted_fixture(Path(directory))
            values = validate_finalized_run(terminal=terminal, artifact_store=store, boundary=boundary,
                case_inputs=(TreatmentCaseInput("case-runtime-scoring", b"runtime-scoring-case-input"),),
                treatment_prompts=(TreatmentPrompt("treatment-runtime-scoring", b"runtime-scoring-prompt"),))
            probe = synthetic_http_probe()
            caps, _ = admit_controlled_probe(probe, binary_sha256=probe["runtime_binary_sha256"])
            from AgMark.shared.validation.codex_cache.collector import canonical_capture_spans
            probe["spans"] = canonical_capture_spans(probe["spans"])
            first = values[0].replays[0]
            for span in probe["spans"]:
                span["attributes"]["validation_id"] = first.validation_id
            raw = json.dumps(probe["spans"], sort_keys=True, separators=(",", ":")).encode()
            identity = digest(raw)
            requests, _ = normalize_spans(probe["spans"], validation_id=first.validation_id,
                capabilities=caps, evidence_reference=identity)
            summary = replay_summary(validation_id=first.validation_id, validates_observation_id=first.validates_observation_id,
                treatment_id=first.treatment_id, repetition_id=first.repetition_id, configuration_match=first.configuration_match,
                runtime_equivalence=first.runtime_equivalence, capabilities=caps, requests=requests)
            first = replace(first, status="completed", requests=requests, capabilities=caps, replay_summary=summary)
            value = treatment_summary(generation_id=terminal.generation_id, treatment_id=first.treatment_id,
                replays=(first, *values[0].replays[1:]), scored_observation_ids=values[0].scored_observation_ids)
            retained = ValidationArtifactStore(store)
            reopened = retained.retain(terminal, (value,), capture_evidence={identity: raw})
            self.assertEqual(value.to_dict(), reopened[0].to_dict())
            path = retained.root / terminal.generation_id / ("capture-" + identity[7:] + ".json")
            path.write_bytes(raw + b" ")
            with self.assertRaises(ValueError):
                retained.read(terminal)

    def test_supplied_maps_cannot_create_missing_accepted_startup_authority(self):
        from AgMark.shared.validation.codex_cache.capture import ReplayCaptureOptions, digest
        from AgMark.shared.validation.codex_cache.metrics import observed
        from AgMark.shared.validation.codex_cache.comparison import configuration_values
        from AgMark.shared.software_testing.validation.codex_cache.fixtures import capabilities
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            terminal, boundary, store, _ = accepted_fixture(root)
            state = ReplayStartingState.capture(root, ())
            registration = next(r for r in terminal.artifact_index.artifacts if r.role == "runner_registration")
            expected = configuration_values(boundary, prompt_sha256=digest(b"runtime-scoring-prompt"),
                input_sha256=digest(b"runtime-scoring-case-input"), runner_registration_sha256=registration.sha256)
            expected = {k: v if v.availability == "available" else observed("asserted:" + k, "caller") for k, v in expected.items()}
            expected["workspace_state_id"] = observed(state.state_id, "caller")
            options = ReplayCaptureOptions(Path("/not-executed/codex"), ("/not-executed/codex", "exec"), {},
                state, expected, expected, capabilities(), "0.159.0", "sha256:" + "a" * 64)
            ids = [json.loads(raw)["observation_id"] for raw in terminal.treatment_observations]
            with patch("AgMark.shared.runtime.orchestration.replay.capture_replay") as capture, \
                    self.assertRaisesRegex(ValueError, "runtime-owned pre-invocation"):
                validate_finalized_run(terminal=terminal, artifact_store=store, boundary=boundary,
                    case_inputs=(TreatmentCaseInput("case-runtime-scoring", b"runtime-scoring-case-input"),),
                    treatment_prompts=(TreatmentPrompt("treatment-runtime-scoring", b"runtime-scoring-prompt"),),
                    capture_options={key: options for key in ids}, capture_evidence={})
                capture.assert_not_called()
            capture.assert_not_called()

    def test_validation_failure_survives_reopening_without_changing_scored_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal, _, store, _ = accepted_fixture(Path(directory))
            before = {r.reference: store.read_verified(r) for r in terminal.artifact_index.artifacts}
            retained = ValidationArtifactStore(store)
            retained.retain_failure(terminal, "post_treatment_validation_failed:ValueError")
            with self.assertRaisesRegex(ValueError, "post_treatment_validation_failed:ValueError"):
                ValidationArtifactStore(store).read(terminal)
            self.assertEqual(before, {r.reference: store.read_verified(r) for r in terminal.artifact_index.artifacts})

    def test_deletion_during_publication_cannot_resurrect_companion(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            terminal, boundary, store, _ = accepted_fixture(Path(directory))
            values = validate_finalized_run(terminal=terminal, artifact_store=store, boundary=boundary,
                case_inputs=(TreatmentCaseInput("case-runtime-scoring", b"runtime-scoring-case-input"),),
                treatment_prompts=(TreatmentPrompt("treatment-runtime-scoring", b"runtime-scoring-prompt"),))
            retained = ValidationArtifactStore(store)
            rename = os.rename
            def delete_after_rename(source, destination):
                rename(source, destination)
                store.delete_generation(terminal.generation_id)
                retained.delete_generation(terminal.generation_id)
            with patch("AgMark.shared.runtime.artifacts.validation.os.rename", side_effect=delete_after_rename):
                with self.assertRaises(ValueError):
                    retained.retain(terminal, values)
            self.assertFalse((retained.root / terminal.generation_id).exists())

    def test_failed_startup_capture_retains_safe_stage_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal,boundary,store,_=accepted_fixture(Path(directory))
            ids=[json.loads(raw)['observation_id'] for raw in terminal.treatment_observations]
            values=validate_finalized_run(terminal=terminal,artifact_store=store,boundary=boundary,
                case_inputs=(TreatmentCaseInput('case-runtime-scoring',b'runtime-scoring-case-input'),),
                treatment_prompts=(TreatmentPrompt('treatment-runtime-scoring',b'runtime-scoring-prompt'),),
                startup_diagnostics={identity:'pre_invocation_startup_capture_unavailable' for identity in ids})
            reopened=ValidationArtifactStore(store).retain(terminal,values)
            for replay in reopened[0].replays:
                self.assertIn('pre_invocation_startup_capture_unavailable',replay.limitations)
                self.assertIn('replay_start_state_not_reproducible',replay.limitations)
                self.assertEqual('unavailable',replay.status)

    def test_nonfinalized_authority_cannot_schedule_replay(self):
        with self.assertRaises(TypeError):
            validate_finalized_run(terminal=object(),artifact_store=None,boundary=None,case_inputs=(),treatment_prompts=())

if __name__ == '__main__': unittest.main()
