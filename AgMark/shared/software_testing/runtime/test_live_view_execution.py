"""Provider-free isolated runtime presentation plumbing."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from AgMark.shared.software_testing.runtime import test_treatment_execution as fixture
from AgMark.shared.runtime.orchestration import TreatmentPrompt, admit_accepted_execution, execute_planned_treatments
from AgMark.shared.adapters.Mock_Model import load_registration


class LiveViewExecutionTests(unittest.TestCase):
    def test_runtime_scopes_exact_input_and_output_without_metadata(self):
        helper=fixture.AcceptedTreatmentExecutionRuntimeTests()
        helper.setUp()
        registration=load_registration()
        with patch.object(fixture, '_RUNNER_VERSION', registration['registration_version']):
            boundary=fixture._boundary()
        plan,snapshot,inputs=helper._accepted(boundary, repetitions=1)
        prompts=(TreatmentPrompt('treatment-a',b'prompt-a'),TreatmentPrompt('treatment-b',b'prompt-b'))
        events=[]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); store=helper._store(root)
            gate=admit_accepted_execution(generation_id='generation-stream-fixture',snapshot=snapshot,benchmark=helper.benchmark,case_set=helper.case_set,treatment_set=helper.treatment_set,execution_boundary=boundary,benchmark_root=root,artifact_store=store)
            result=execute_planned_treatments(gate=gate,snapshot=snapshot,benchmark=helper.benchmark,case_set=helper.case_set,treatment_set=helper.treatment_set,execution_boundary=boundary,artifact_store=store,repository_root=fixture._REPOSITORY_ROOT,runner_registration=registration,case_inputs=inputs,treatment_prompts=prompts,live_view_callback=events.append)
            self.assertEqual(len(plan.observations),len(result.observations()))
        self.assertTrue(events)
        for event in events:
            self.assertEqual(set(event),{'generation_id','invocation_id','channel','text','treatment_name'})
            self.assertEqual(event['generation_id'],'generation-stream-fixture')
        for slot in plan.observations:
            per=[e for e in events if e['invocation_id']==slot.observation_id]
            self.assertEqual([e['channel'] for e in per],['input','output'])
            self.assertTrue(all(e['treatment_name'] == slot.treatment_id for e in per))
            case=next(i for i in inputs if i.case_id==slot.case_id)
            prompt=next(p for p in prompts if p.treatment_id==slot.treatment_id)
            self.assertEqual(per[0]['text'],(prompt.data+b'\n\n'+case.data).decode())
