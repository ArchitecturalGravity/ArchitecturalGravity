"""Canonical/readable replay reporting with exact scored-resource parity."""
from dataclasses import replace
import json
import unittest
from AgMark.shared.software_testing.validation.codex_cache.fixtures import replay
from AgMark.shared.validation.codex_cache.metrics import treatment_summary
from AgMark.shared.validation.codex_cache.serialization import validation_bytes
from AgMark.shared.reporting.model import ReportArtifactRef
from AgMark.shared.reporting.replay import validation_markdown, VALIDATION_EXTENSION
from AgMark.shared.runtime.artifacts import sha256_bytes

class ReplayReportingIntegrationTests(unittest.TestCase):
    def test_exact_scored_resources_remain_separate_from_replay(self):
        self._exercise_report(False)

    def test_disabled_replay_preserves_scored_report(self):
        self._exercise_report(True)

    def _exercise_report(self, disabled):
        from AgMark.shared.software_testing.integration import test_reporting_revalidation as fixture
        from AgMark.shared.reporting.generation import generate_report_bundle
        owner=fixture.ReportingRevalidationIntegrationTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        authority=fixture.revalidate_accepted_reporting_input(owner.accepted,store=owner.store)
        model=fixture.build_canonical_report_model(authority,report_id='replay-report',report_version='1.0.0',
            status='complete',sections=owner._sections(),report_manifest_id='replay-manifest',
            generated_at='2026-10-05T00:00:00Z')
        observation=model.accepted.accepted.observation_matrix[0]
        r=replay()
        ids=dict(validates_observation_id=observation.observation_id,treatment_id=observation.treatment_id,repetition_id=str(observation.repetition_id))
        r=replace(r,**ids,generation_id=model.accepted_generation_id,replay_summary=replace(r.replay_summary,**ids))
        value=treatment_summary(generation_id=model.accepted_generation_id,treatment_id=observation.treatment_id,replays=() if disabled else (r,),scored_observation_ids=(observation.observation_id,),
            sampling_policy='disabled_by_user' if disabled else 'one_per_accepted_observation',
            sampling_reason='Disabled by user' if disabled else 'complete_selection')
        ref=ReportArtifactRef('validation-input',sha256_bytes(validation_bytes(value)),'.agmark-validation/'+model.accepted_generation_id+'/treatment-0.json')
        augmented=replace(model,validations=(value,),validation_inputs=(ref,))
        from AgMark.shared.evaluation import IdentityRef
        options=dict(input_evidence_set_id='replay-report-evidence',generator=IdentityRef('replay-generator','1.0.0'),procedure_id='replay-report',procedure_version='1.0.0',command_or_procedure='controlled report assembly',report_reference='report.json',canonical_evidence_reference='canonical.json',human_reference='report.md',manifest_reference='manifest.json')
        before=generate_report_bundle(model,**options);after=generate_report_bundle(augmented,**options)
        a,b=json.loads(before.canonical_evidence.data),json.loads(after.canonical_evidence.data)
        a.pop('extensions');b.pop('extensions')
        self.assertEqual(a,b)
        human = after.human.data.decode()
        self.assertIn('Original accepted run only', human)
        self.assertIn('canonical.json', human)
        self.assertNotIn('### Post-treatment cache validation', human)
        machine_validation = json.loads(after.report.data)['extensions'][VALIDATION_EXTENSION]
        evidence_validation = json.loads(after.canonical_evidence.data)['extensions'][VALIDATION_EXTENSION]
        self.assertEqual(machine_validation, evidence_validation)
        self.assertEqual(ref.to_dict(),json.loads(after.manifest.data)['extensions']['arcgrav.telemetry:validation-inputs'][0])
        from AgMark.shared.reporting.completion import completion_record
        completion=completion_record(model.accepted_generation_id,status="complete",bundle=after)
        if disabled:
            self.assertIn("Disabled by user", json.dumps(evidence_validation))
            self.assertEqual((), value.replays)
            return
        forged = json.loads(after.report.data)
        forged['extensions'][VALIDATION_EXTENSION][0]['replays'][0]['configuration_match']['matched_fields'] = []
        changed = replace(after, report=replace(after.report, data=json.dumps(forged).encode()))
        retained_machine = next(item for item in completion["report"]["components"] if item["role"] == "machine_json")
        self.assertNotEqual(retained_machine["sha256"], changed.report.sha256)
        self.assertIn('exact scored request trajectory',validation_markdown(value))

if __name__=='__main__': unittest.main()
