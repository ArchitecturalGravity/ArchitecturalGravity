"""Synthetic ingress checks do not grant stock capabilities or runtime equivalence."""
import copy
import json
import unittest
from AgMark.shared.validation.codex_cache.collector import sanitized_spans, canonical_capture_spans
from AgMark.shared.validation.codex_cache.diagnostics import diagnostic_field, PROFILE, UNSUPPORTED
from AgMark.shared.validation.codex_cache.normalization import normalize_spans
from AgMark.shared.software_testing.validation.codex_cache.synthetic_probes import synthetic_dual_probe
from AgMark.shared.validation.codex_cache.capabilities import admit_controlled_probe


def attr(key, value):
    return {'key': key, 'value': {'boolValue' if type(value) is bool else 'intValue' if type(value) is int else 'stringValue': value}}


class TransportDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.probe = synthetic_dual_probe()
        self.caps, _ = admit_controlled_probe(self.probe, binary_sha256=self.probe['runtime_binary_sha256'])
        self.ws = self.probe['websocket_probe']

    def test_privacy_allowlist_preserves_only_exported_transport_metadata(self):
        event = {'timeUnixNano': '100', 'name': 'PRIVATE BODY', 'attributes': [
            attr('event.name', 'codex.api_request'), attr('attempt', 2), attr('duration_ms', '27'),
            attr('http.response.status_code', 200), attr('prompt', 'PRIVATE PROMPT'),
            attr('response', 'PRIVATE RESPONSE'), attr('Authorization', 'PRIVATE SECRET'),
            attr('auth.request_id', 'PRIVATE HEADER'), attr('response_id', 'resp_UNPROVEN'),
            attr('previous_response_id', 'resp_UNPROVEN'), attr('auth.agent_id', 'PRIVATE AGENT')]}
        span = {'traceId': 'a'*32, 'spanId': 'b'*16, 'parentSpanId': 'c'*16,
                'name': 'responses.stream_request', 'attributes': [attr('validation_id', self.ws['validation_id'])],
                'events': [event, event, {'timeUnixNano':'102', 'attributes':[attr('event.name','private arbitrary event')]}]}
        spans = sanitized_spans({'resourceSpans':[{'resource':{'attributes':[attr('secret','PRIVATE RESOURCE')]},'scopeSpans':[{'spans':[span]}]}]})
        spans = canonical_capture_spans(spans)
        self.assertEqual(spans, canonical_capture_spans(spans))
        self.assertEqual(1, len(spans[0]['events']))
        self.assertEqual({'event.name':'codex.api_request','attempt':2,'duration_ms':27,'http.response.status_code':200},spans[0]['events'][0]['attributes'])
        field = diagnostic_field(spans*2, validation_id=self.ws['validation_id'], evidence_reference='fixture:safe')
        data = json.loads(field.value)
        self.assertEqual(1,len(data['transport_events']))
        self.assertNotIn('PRIVATE',field.value)
        self.assertNotIn('resp_UNPROVEN',field.value)
        self.assertIn('not logical request',data['transport_events'][0]['meaning'])

    def test_strings_negative_values_and_unknown_events_cannot_become_timing(self):
        events = [{'timeUnixNano':'101','attributes':[attr('event.name','codex.websocket_request'),
            attr('duration_ms','PRIVATE'),attr('auth.connection_reused','false')]}]
        span={'traceId':'a'*32,'spanId':'b'*16,'name':'responses_websocket.stream_request','events':events}
        safe=sanitized_spans({'resourceSpans':[{'scopeSpans':[{'spans':[span]}]}]})
        self.assertEqual({'event.name':'codex.websocket_request'},safe[0]['events'][0]['attributes'])

    def test_new_profile_deduplicates_deliveries_but_not_conflicting_identities(self):
        args=dict(validation_id=self.ws['validation_id'],capabilities=self.caps,evidence_reference='fixture:ws',profile=PROFILE)
        records, limits=normalize_spans(self.ws['spans'],**args)
        doubled, other=normalize_spans(self.ws['spans']*2,**args)
        self.assertEqual(records,doubled);self.assertEqual(limits,other)
        self.assertEqual(3,len(records))
        for record in records:
            for key in UNSUPPORTED:
                self.assertIsNone(record.fields[key].value)
                self.assertEqual('source_contract_limit',record.fields[key].method)
        for key in ('input_tokens','cached_input_tokens','cache_write_input_tokens','request_duration_ms'):
            self.assertIsNone(records[0].fields[key].value)
        conflict=copy.deepcopy(self.ws['spans'][0]);conflict['name']='responses.stream_request'
        failed,reasons=normalize_spans([*self.ws['spans'],conflict],**args)
        self.assertFalse(failed);self.assertIn('ambiguous_span_identity',reasons)

    def test_source_confirmed_events_do_not_promote_unsupported_capabilities(self):
        spans=copy.deepcopy(self.ws['spans'])
        spans[0]['events']=[{'time_ns':'999','attributes':{'event.name':'codex.sse_event','event.kind':'response.completed','input_token_count':123,'ttft_ms':4}}]
        field=diagnostic_field(spans,validation_id=self.ws['validation_id'],evidence_reference='fixture:ws')
        self.assertIn('not independently established',field.value)
        self.assertIn('not first-token timing',field.value)
        records,_=normalize_spans(spans,validation_id=self.ws['validation_id'],capabilities=self.caps,evidence_reference='fixture:ws',profile=PROFILE)
        self.assertIsNone(records[0].fields['input_tokens'].value)
        self.assertTrue(all(r.fields['request_duration_ms'].value is None for r in records))
        for key in ('response_identity','continuation_identity','retry','reconnect','request_duration_ms'):
            self.assertEqual('unsupported',self.caps.fields[key].status)
