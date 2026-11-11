"""Duration display converts retained minute evidence without mutating authority."""
import copy
import json
import unittest
from unittest.mock import patch
from AgMark.shared.reporting.measurement_presentation import presentation_measurement
from AgMark.gui.views.results import ResultRowProjection, RESULTS_COLUMNS
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import extract, rollout, aggregate


class DurationPresentationTests(unittest.TestCase):
    def test_minutes_ms_partial_missing_and_repeated_projection(self):
        original = {'value': 1, 'unit': 'minutes', 'availability': 'partial',
                    'source': 'retained log', 'evidence_references': ['original-ref']}
        before = copy.deepcopy(original)
        normalized = presentation_measurement('session_span_minutes', original)
        self.assertEqual(60000, normalized['value'])
        self.assertEqual('ms', normalized['unit'])
        self.assertEqual('partial', normalized['availability'])
        self.assertEqual(normalized, presentation_measurement('session_span_minutes', normalized))
        for _ in range(2):
            row = ResultRowProjection('T', 1, 'retained', 'Scored', '✓', measurements={
                'duration': {'value': 12, 'unit': 'ms'}, 'session_span_minutes': original}).to_table_row()
            self.assertEqual('60000 ms (partial)', row.cells['session_span_minutes'].text)
            self.assertEqual('12 ms', row.cells['duration'].text)
            self.assertEqual(before, original)
        self.assertEqual(before, original)
        for unavailable in ({}, {'value': None, 'unit': 'minutes', 'availability': 'unavailable'}):
            row = ResultRowProjection('T', None, 'missing', 'Missing', '—', measurements={'session_span_minutes': unavailable}).to_table_row()
            self.assertEqual('Unavailable', row.cells['session_span_minutes'].text)
        labels = {column.key: column.label for column in RESULTS_COLUMNS}
        self.assertEqual('Treatment Duration', labels['duration'])
        self.assertEqual('Session Duration', labels['session_span_minutes'])

    def test_multiple_legacy_sessions_and_existing_floor_are_preserved(self):
        envelopes = []
        for thread, minutes in (('one', 1), ('two', 2)):
            rows = [json.loads(line) for line in rollout(thread).splitlines()]
            rows[-1]['timestamp'] = f'2026-10-03T12:0{minutes}:00Z'
            envelope, _ = extract(b'\n'.join(json.dumps(row).encode() for row in rows), thread)
            envelopes.append(envelope)
        pooled = aggregate(envelopes)
        before = copy.deepcopy(pooled)
        measurement = pooled['roles']['session_span_minutes']
        self.assertEqual(3, measurement['value'])
        self.assertEqual('minutes', measurement['unit'])
        cell = ResultRowProjection('T', 1, 'retained', 'Scored', '✓', measurements=pooled['roles']).to_table_row().cells['session_span_minutes']
        self.assertEqual('180000 ms', cell.text)
        self.assertEqual(before, pooled)
        short_rows = [json.loads(line) for line in rollout().splitlines()]
        for record in short_rows: record["timestamp"] = "2026-10-03T12:00:00Z"
        short, _ = extract(b"\n".join(json.dumps(record).encode() for record in short_rows))
        from AgMark.shared.evaluation.telemetry.session_metrics import SESSION_METRICS
        floor = short['extensions'][SESSION_METRICS]['roles']['session_span_minutes']
        self.assertEqual(.01, floor['value'])
        self.assertEqual(600, presentation_measurement('session_span_minutes', floor)['value'])

    def test_compact_report_links_session_evidence_without_rewriting_it(self):
        from AgMark.shared.software_testing.integration import test_reporting_revalidation as fixture
        from AgMark.shared.reporting.generation import generate_report_bundle
        from AgMark.shared.evaluation import IdentityRef
        owner = fixture.ReportingRevalidationIntegrationTests(); owner.setUp(); self.addCleanup(owner.doCleanups)
        authority = fixture.revalidate_accepted_reporting_input(owner.accepted, store=owner.store)
        model = fixture.build_canonical_report_model(authority, report_id='duration-report', report_version='1.0.0',
            status='complete', sections=owner._sections(), report_manifest_id='duration-manifest',
            generated_at='2026-10-05T00:00:00Z')
        envelope, _ = extract()
        pooled = aggregate([envelope]); before = copy.deepcopy(pooled)
        from AgMark.shared.reporting import generation
        original_thaw = generation._thaw
        with patch.object(generation, '_thaw', side_effect=lambda value: {'T': pooled} if value is model.accepted.treatment_measurements else original_thaw(value)):
            bundle = generate_report_bundle(model, input_evidence_set_id='duration-evidence',
                generator=IdentityRef('duration-generator', '1.0.0'),
                procedure_id='duration-projection', procedure_version='1.0.0',
                command_or_procedure='duration presentation test', report_reference='report.json',
                canonical_evidence_reference='canonical.json', human_reference='report.md',
                manifest_reference='manifest.json')
        text = bundle.human.data.decode()
        self.assertIn('canonical.json', text)
        self.assertIn('Average Inference Duration', text)
        self.assertNotIn('Session Duration', text)
        self.assertNotIn('paired_attempts', text)
        evidence = json.loads(bundle.canonical_evidence.data)['treatment_measurements']['T']
        self.assertEqual(before, evidence)
        self.assertEqual('minutes', evidence['roles']['session_span_minutes']['unit'])
        self.assertEqual(11000.0, presentation_measurement(
            'session_span_minutes', evidence['roles']['session_span_minutes'])['value'])
        self.assertEqual(60, evidence['roles']['uncached_input_tokens']['value'])
        self.assertEqual(0.4, evidence['roles']['cache_read_fraction']['value'])
        self.assertEqual(before, pooled)

    def test_retained_minute_evidence_reopens_in_ms_without_rewriting_measurements(self):
        from dataclasses import replace
        from PySide6.QtWidgets import QApplication
        from AgMark.gui.application.history import save_presentation, discover_history
        from AgMark.gui.views.results import ResultsView, ResultsProjection
        from AgMark.shared.software_testing.frontends.gui import test_run_history as fixture
        app = QApplication.instance() or QApplication([])
        owner = fixture.RunHistoryTests(); owner.setUp(); self.addCleanup(owner.doCleanups)
        current, workspace = discover_history(owner.repo)[owner.gid].presentation()
        legacy = {'value': 1, 'unit': 'minutes', 'availability': 'partial', 'source': 'retained session'}
        page = ResultsView(ResultsProjection(owner.gid, (ResultRowProjection('T', 1, 'retained', 'Scored', '✓', measurements={'session_span_minutes': legacy}),)))
        workspace = replace(workspace, results=page)
        before = owner.archive.read_bytes()
        for _ in range(2):
            save_presentation(owner.root, owner.gid, current, workspace)
            self.assertEqual(legacy, page.projection.rows[0].measurements['session_span_minutes'])
            self.assertEqual('60000 ms (partial)', page.projection._presentation['rows'][0].cells['session_span_minutes'].text)
            self.assertEqual(['T'], [button.text() for button in page.treatment_buttons])
        self.assertEqual(owner.archive.read_bytes(), before)
