"""Completion-only desktop reports open and export exact sealed bytes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import os
import json
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QPushButton
from AgMark.gui.application.history import discover_history, export_retained_report, save_presentation
from AgMark.gui.views.reports import ReportsView
from AgMark.shared.runtime.artifacts.archive import canonical_bytes, digest, seal_generation, revise_archive
from AgMark.shared.validation.run_archive import read_retained_report


class CompletionArchiveGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.root = self.repo / "AgMark" / "run_evidence"
        self.root.mkdir(parents=True)
        self.gid = "generation-completion-gui"
        (self.root / self.gid).mkdir()
        (self.root / self.gid / "evidence.json").write_text('{}')
        (self.root / ("." + self.gid + ".terminal")).write_text('accepted')
        self.markdown = b'# Original report\r\n\r\nExact UTF-8 bytes: \xc3\xa9\n'
        document = {"accepted_generation_id": self.gid, "report_id": "report-gui", "status": "complete", "generated_at": "2026-11-03T00:00:00Z"}
        blobs = {}
        entries = []
        for role in ('markdown', 'machine_json', 'canonical_evidence_json', 'manifest'):
            ref = 'reports/' + self.gid + '/' + role
            value = dict(document)
            if role == 'machine_json':
                schema_path = Path(__file__).resolve().parents[3] / 'schemas' / 'report.schema.json'
                sections = json.loads(schema_path.read_text())['properties']['sections']['required']
                value.update(schema_id='arcgrav.shared.schema.report', schema_version='3.0.0',
                    report_manifest_id='manifest', extensions={}, report_version='1.0.0',
                    benchmark={'id': 'fixture', 'version': '1.0.0'},
                    case_set={'id': 'fixture', 'version': '1.0.0'},
                    treatment_set={'id': 'fixture', 'version': '1.0.0'},
                    primary_endpoint={'id': 'fixture', 'version': '1.0.0'}, comparison_track_id='fixture',
                    execution_boundary={'artifact_id': 'boundary', 'sha256': digest(b'boundary')},
                    observation_counts={name: 0 for name in ('planned', 'finalized', 'completed', 'scored',
                        'failed', 'missing', 'excluded', 'non_scorable')},
                    sections={name: {'availability': 'not_applicable', 'reason': 'fixture'} for name in sections})
            if role == 'manifest':
                value = dict(accepted_generation_id=self.gid, generated_at=document['generated_at'],
                    schema_id='arcgrav.shared.schema.report-manifest', schema_version='1.0.0',
                    manifest_id='manifest', extensions={},
                    inputs=[{'artifact_id': 'source', 'sha256': digest(b'{}'),
                             'reference': self.gid + '/evidence.json'}], input_evidence_set_id='fixture',
                    generator={'id': 'fixture', 'version': '1.0.0'},
                    procedure={'id': 'fixture', 'version': '1.0.0', 'command_or_procedure': 'fixture'})
                value['report'] = {key: item for key, item in next(item for item in entries if item['role'] == 'machine_json').items() if key != 'role'}
                value['components'] = [{key: item for key, item in component.items() if key != 'role'} for component in entries]
            data = self.markdown if role == 'markdown' else canonical_bytes(value)
            blobs[ref] = data
            entries.append({"role": role, "reference": ref, "sha256": digest(data), "artifact_id": role})
        completion = {"schema_id": "arcgrav.shared.run-completion", "schema_version": "2.0.0", "generation_id": self.gid, "completed_at": "2026-11-03T00:00:00Z", "status": "complete", "validation": {"status": "passed", "diagnostic": None}, "report": {"report_id": "report-gui", "components": entries}}
        self.path = seal_generation(self.root, self.gid, report_components=blobs, completion_record=completion)

    def test_restart_reads_report_without_runtime_or_snapshot(self):
        with patch('subprocess.Popen', side_effect=AssertionError('Provider execution forbidden')):
            run = discover_history(self.repo)[self.gid]
            current, data = run.prepare_presentation()
        self.assertEqual(data.reports.readable_content.encode('utf-8'), self.markdown)
        self.assertEqual(data.reports.generation_state, 'complete')
        self.assertEqual(data.verification.banner.heading, 'Verification details unavailable')
        self.assertNotIn('independently', data.verification.banner.summary)

        self.assertTrue(data.reports.export_action.available)
        self.assertFalse(current.start_benchmark_available)
        view = ReportsView(data.reports)
        self.addCleanup(view.deleteLater)
        self.assertIn('Archive integrity checks passed.', view.status_label.text())
        self.assertNotIn('Claims:', view.status_label.text())
        self.assertNotIn('independently authenticated', view.status_label.text())
        self.assertNotIn('comparative claims', view.status_label.text())
        labels = [button.text() for button in view.findChildren(QPushButton)]
        self.assertIn('Open Report', labels)
        self.assertFalse(any('Generate' in label or 'Verify' in label for label in labels))

    def test_export_copies_exact_bytes_and_rechecks_identity(self):
        run = discover_history(self.repo)[self.gid]
        target = self.repo / 'export.md'
        export_retained_report(run, 'report-gui', target)
        self.assertEqual(target.read_bytes(), self.markdown)
        with self.assertRaises(ValueError):
            export_retained_report(run, 'other-report', target)
        self.assertEqual(target.read_bytes(), self.markdown)

    def test_stale_gui_snapshot_cannot_replace_report(self):
        revise_archive(self.root, self.gid, {'history/presentation.json': b'{"malicious":"replacement report"}'})
        run = discover_history(self.repo)[self.gid]
        _, data = run.prepare_presentation()
        self.assertEqual(data.reports.readable_content.encode('utf-8'), self.markdown)
        before = self.path.read_bytes()
        save_presentation(self.root, self.gid, None, None)
        self.assertEqual(self.path.read_bytes(), before)

    def test_tampered_report_never_opens_or_exports(self):
        run = discover_history(self.repo)[self.gid]
        with ZipFile(self.path, 'a') as archive:
            archive.writestr('reports/' + self.gid + '/markdown', 'corrupt')
        with self.assertRaises(ValueError):
            run.prepare_presentation()
        with self.assertRaises(ValueError):
            export_retained_report(run, 'report-gui', self.repo / 'bad.md')
        self.assertFalse((self.repo / 'bad.md').exists())


    def test_archive_deletion_removes_completion_sidecar(self):
        from AgMark.shared.runtime.completion_diagnostics import completion_diagnostic, persist_completion_diagnostics, retained_completion_diagnostics
        persist_completion_diagnostics(self.root, self.gid, [completion_diagnostic("publication", "passed")])
        run = discover_history(self.repo)[self.gid]
        run.delete()
        self.assertFalse(self.path.exists())
        self.assertEqual([], retained_completion_diagnostics(self.root, self.gid))
        self.assertNotIn(self.gid, discover_history(self.repo))
