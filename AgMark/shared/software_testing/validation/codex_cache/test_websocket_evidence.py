"""Synthetic WebSocket admission contract tests; no exporter execution claims."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
from AgMark.shared.validation.codex_cache.capabilities import admit_controlled_probe, load_capabilities
from AgMark.shared.validation.codex_cache.collector import canonical_capture_spans
from AgMark.shared.validation.codex_cache.normalization import normalize_spans, TOKEN_ATTRIBUTES
from AgMark.shared.validation.codex_cache.source_evidence import validate_source
from AgMark.shared.validation.codex_cache.metrics import replay_summary, treatment_summary
from AgMark.shared.validation.codex_cache.models import ProviderRequestCacheValidation, SCHEMA_ID, SCHEMA_VERSION, SCOPE
from AgMark.shared.software_testing.validation.codex_cache.fixtures import configuration, runtime

from AgMark.shared.software_testing.validation.codex_cache.synthetic_probes import synthetic_dual_probe

class WebSocketEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.probe = synthetic_dual_probe()
        self.caps,self.proof=admit_controlled_probe(self.probe,binary_sha256=self.probe['runtime_binary_sha256'])
        self.ws=self.probe['websocket_probe']

    def normalize(self,spans=None,caps=None):
        return normalize_spans(self.ws['spans'] if spans is None else spans,validation_id=self.ws['validation_id'],capabilities=caps or self.caps,evidence_reference='fixture:synthetic-ws')

    def test_synthetic_probe_bytes_are_integrity_bound_without_execution_claims(self):
        self.assertEqual(self.probe, json.loads(self.proof['probe']))
        expected = 'sha256:' + hashlib.sha256(self.proof['probe']).hexdigest()
        document = json.loads(self.proof['capabilities'])
        self.assertEqual(expected, document['probe_sha256'])
        self.assertTrue(all(field['evidence_references'] == [expected]
                            for field in document['fields'].values()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'capabilities.json'
            path.write_bytes(self.proof['capabilities'])
            (root / 'probe.json').write_bytes(self.proof['probe'] + b' ')
            with self.assertRaisesRegex(ValueError, 'probe integrity differs'):
                load_capabilities(path, binary_sha256=self.probe['runtime_binary_sha256'],
                    runtime_version='0.159.0', evidence_sha256='sha256:' +
                    hashlib.sha256(self.proof['capabilities']).hexdigest())

    def test_synthetic_warmup_and_two_generations_have_independent_counters(self):
        records,reasons=self.normalize()
        self.assertEqual((),reasons)
        self.assertEqual(['warmup','generation','generation'],[r.request_kind for r in records])
        self.assertTrue(all(r.transport=='websocket' for r in records))
        self.assertIs(False,records[0].fields['generate'].value)
        for field in TOKEN_ATTRIBUTES:
            self.assertEqual('unavailable',records[0].fields[field].availability)
        for ordinal,r in enumerate(records[1:],2):
            for field,scale in (('input_tokens',100),('cached_input_tokens',20),('cache_write_input_tokens',11),('output_tokens',7),('reasoning_tokens',3)):
                self.assertEqual(ordinal*scale,r.fields[field].value)
            for field in ('request_duration_ms','response_id','previous_response_id','cache_key_value'):
                self.assertIsNone(r.fields[field].value)
        for kind,raw in self.proof.items():validate_source(kind,raw)

    def test_hundreds_of_nonusage_streaming_spans_do_not_create_completions(self):
        # Deliberately large synthetic noise population must not alter the
        # independently specified request count or token tuples.
        spans=copy.deepcopy(self.ws['spans'])
        completion=next(s for s in spans if s['name']=='handle_responses' and any(k in s['attributes'] for k in TOKEN_ATTRIBUTES.values()))
        for i in range(476):
            noise=copy.deepcopy(completion);noise['span_id']=f'{i+1000000:016x}';noise['attributes']={'validation_id':self.ws['validation_id']};spans.append(noise)
        self.assertEqual(self.normalize(),self.normalize(spans))

    def test_missing_boundaries_are_not_reported_as_ambiguity(self):
        spans=[s for s in self.ws['spans'] if s['name']!='responses_websocket.stream_request']
        records,reasons=self.normalize(spans)
        self.assertEqual((),records)
        self.assertIn('request_boundary_unavailable',reasons)
        self.assertIn('websocket_boundary_not_observed',reasons)
        self.assertNotIn('ambiguous_request_completion_ancestry',reasons)

    def test_http_only_proof_cannot_admit_websocket(self):
        probe=copy.deepcopy(self.probe);probe.pop('websocket_probe')
        caps,_=admit_controlled_probe(probe,binary_sha256=probe['runtime_binary_sha256'])
        records,reasons=self.normalize(caps=caps)
        self.assertEqual((),records)
        self.assertIn('websocket_capability_not_demonstrated',reasons)

    def test_duplicate_candidates_and_completions_remain_ambiguous(self):
        for name in ('responses_websocket.stream_request','handle_responses'):
            spans=copy.deepcopy(self.ws['spans'])
            if name=='handle_responses':
                extra=next(s for s in spans if s['name']==name and any(k in s['attributes'] for k in TOKEN_ATTRIBUTES.values()))
            else:
                requests=[s for s in spans if s['name']==name];extra=requests[1]
            extra=copy.deepcopy(extra);extra['span_id']='abcdef0123456789';spans.append(extra)
            records,reasons=self.normalize(spans)
            self.assertIn('ambiguous_request_completion_ancestry',reasons)
            self.assertLess(len(records),3)

    def test_missing_warmup_boolean_and_transport_conflicts_fail_closed(self):
        spans=copy.deepcopy(self.ws['spans'])
        for s in spans:
            if s['name']=='model_client.stream_responses_websocket':s['attributes'].pop('websocket.warmup',None)
        records,reasons=self.normalize(spans)
        self.assertFalse(records);self.assertIn('websocket_request_kind_unavailable',reasons)
        spans=copy.deepcopy(self.ws['spans'])
        for s in spans:
            if s['name']=='responses_websocket.stream_request':s['attributes']['transport']='responses_http'
        records,reasons=self.normalize(spans)
        self.assertFalse(records);self.assertIn('request_transport_identity_conflict',reasons)

    def test_provider_counter_tampering_cannot_be_admitted(self):
        probe=copy.deepcopy(self.probe)
        for s in probe['websocket_probe']['spans']:
            if 'gen_ai.usage.input_tokens' in s['attributes']:s['attributes']['gen_ai.usage.input_tokens']+=1
        with self.assertRaises(ValueError):admit_controlled_probe(probe,binary_sha256=probe['runtime_binary_sha256'])

    def test_allowlist_retains_only_reviewed_names_boolean_and_counters(self):
        spans=copy.deepcopy(self.ws['spans']);spans[0]['name']='secret-canary';spans[0]['attributes'].update(prompt='secret-canary',authorization='secret-canary')
        clean=canonical_capture_spans(spans)
        self.assertNotIn('secret-canary',json.dumps(clean))
        self.assertTrue(any(type(s['attributes'].get('websocket.warmup')) is bool for s in clean))
        self.assertEqual(clean,canonical_capture_spans(clean))

    def test_generation_coverage_is_available_without_inventing_warmup_usage_or_duration(self):
        requests,reasons=self.normalize()
        ids=dict(validation_id='controlled-ws',validates_observation_id='observation',treatment_id='treatment',repetition_id='1')
        summary=replay_summary(**ids,configuration_match=configuration(),runtime_equivalence=runtime(),capabilities=self.caps,requests=requests,limitations=reasons)
        replay=ProviderRequestCacheValidation(SCHEMA_ID,SCHEMA_VERSION,**ids,generation_id='generation',validation_scope=SCOPE,separate_invocation=True,included_in_score=False,status='completed',configuration_match=configuration(),runtime_equivalence=runtime(),capabilities=self.caps,replay_summary=summary,requests=requests,provenance='authored synthetic probe; synthetic accepted linkage',evidence_references=('fixture:synthetic-ws',))
        treatment=treatment_summary(generation_id='generation',treatment_id='treatment',replays=(replay,),scored_observation_ids=('observation',))
        self.assertEqual(1,treatment.coverage.token_usage_available)
        self.assertEqual(0,treatment.coverage.request_lifecycle_available)
        self.assertEqual(500,summary.metrics['generation_input_tokens'].field.value)
        self.assertEqual(1,summary.metrics['warmup_request_count'].field.value)
        self.assertIsNone(summary.metrics['warmup_cache_write_input_tokens'].field.value)
        self.assertIsNone(summary.metrics['warmup_reuse_ratio'].field.value)

    def test_controlled_websocket_report_preserves_exact_scored_resources(self):
        from dataclasses import replace
        from AgMark.shared.software_testing.integration import test_reporting_revalidation as fixture
        from AgMark.shared.reporting.generation import generate_report_bundle
        from AgMark.shared.reporting.model import ReportArtifactRef
        from AgMark.shared.validation.codex_cache.serialization import validation_bytes
        from AgMark.shared.evaluation import IdentityRef
        from AgMark.shared.runtime.artifacts import sha256_bytes
        owner=fixture.ReportingRevalidationIntegrationTests();owner.setUp();self.addCleanup(owner.doCleanups)
        authority=fixture.revalidate_accepted_reporting_input(owner.accepted,store=owner.store)
        model=fixture.build_canonical_report_model(authority,report_id='controlled-ws-report',report_version='1.0.0',status='complete',sections=owner._sections(),report_manifest_id='controlled-ws-manifest',generated_at='2026-10-05T00:00:00Z')
        observation=model.accepted.accepted.observation_matrix[0]
        ids=dict(validation_id='controlled-ws-report',validates_observation_id=observation.observation_id,treatment_id=observation.treatment_id,repetition_id=str(observation.repetition_id))
        requests,reasons=self.normalize()
        summary=replay_summary(**ids,configuration_match=configuration(),runtime_equivalence=runtime(),capabilities=self.caps,requests=requests,limitations=reasons)
        replay=ProviderRequestCacheValidation(SCHEMA_ID,SCHEMA_VERSION,**ids,generation_id=model.accepted_generation_id,validation_scope=SCOPE,separate_invocation=True,included_in_score=False,status='completed',configuration_match=configuration(),runtime_equivalence=runtime(),capabilities=self.caps,replay_summary=summary,requests=requests,provenance='authored synthetic probe; synthetic report linkage',evidence_references=('fixture:synthetic-ws',))
        value=treatment_summary(generation_id=model.accepted_generation_id,treatment_id=observation.treatment_id,replays=(replay,),scored_observation_ids=(observation.observation_id,))
        ref=ReportArtifactRef('controlled-ws-validation',sha256_bytes(validation_bytes(value)),'.agmark-validation/'+model.accepted_generation_id+'/treatment-0.json')
        augmented=replace(model,validations=(value,),validation_inputs=(ref,))
        options=dict(input_evidence_set_id='controlled-ws-report',generator=IdentityRef('controlled-generator','1.0.0'),procedure_id='controlled-ws-report',procedure_version='1.0.0',command_or_procedure='controlled report assembly',report_reference='report.json',canonical_evidence_reference='canonical.json',human_reference='report.md',manifest_reference='manifest.json')
        before=generate_report_bundle(model,**options);after=generate_report_bundle(augmented,**options)
        a,b=json.loads(before.canonical_evidence.data),json.loads(after.canonical_evidence.data);a.pop('extensions');b.pop('extensions');self.assertEqual(a,b)
        from AgMark.shared.reporting.completion import completion_record
        completion=completion_record(model.accepted_generation_id,status="complete",bundle=after)
        self.assertNotIn("claim_eligibility",completion)
        self.assertEqual(after.report.sha256, next(item["sha256"] for item in completion["report"]["components"] if item["role"] == "machine_json"))
        text = after.human.data.decode()
        self.assertIn('validation evidence is retained separately', text)
        self.assertIn('canonical.json', text)
        self.assertNotIn('warmup', text)
        self.assertNotIn('websocket', text)
        from AgMark.shared.reporting.replay import VALIDATION_EXTENSION
        evidence = json.loads(after.canonical_evidence.data)['extensions'][VALIDATION_EXTENSION]
        self.assertEqual([value.to_dict()], evidence)
        self.assertIn('warmup', json.dumps(evidence))
        self.assertIn('websocket', json.dumps(evidence))
