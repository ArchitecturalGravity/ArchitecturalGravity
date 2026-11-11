"""One-pass completion and exact retained-report publication contracts."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.reporting import GeneratedReportBundle, GeneratedReportComponent, REQUIRED_REPORT_SECTIONS
from AgMark.shared.reporting.completion import completion_record, report_components
from AgMark.shared.runtime.artifacts.archive import (
    ArchiveError, canonical_bytes, digest, read_archive_member, seal_generation,
)
from AgMark.shared.validation.run_archive import read_retained_report, import_run_archive


def report_bundle(generation_id="generation-completion"):
    document = {"accepted_generation_id": generation_id, "report_id": "report-completion",
                "status": "complete",
                "schema_id": "arcgrav.shared.schema.report", "schema_version": "3.0.0",
                "report_manifest_id": "manifest.json", "report_version": "1.0.0",
                "extensions": {}, "generated_at": "2026-11-03T00:00:00+00:00",
                "benchmark": {"id": "fixture", "version": "1.0.0"},
                "case_set": {"id": "fixture", "version": "1.0.0"},
                "treatment_set": {"id": "fixture", "version": "1.0.0"},
                "primary_endpoint": {"id": "fixture", "version": "1.0.0"},
                "comparison_track_id": "fixture",
                "execution_boundary": {"artifact_id": "boundary", "sha256": digest(b"boundary")},
                "observation_counts": {name: 0 for name in ("planned", "finalized", "completed", "scored", "failed", "missing", "excluded", "non_scorable")},
                "sections": {name: {"availability": "not_applicable", "reason": "fixture"} for name in REQUIRED_REPORT_SECTIONS}}
    prefix = "reports/" + generation_id + "/"
    def component(role, data, media="application/json"):
        return GeneratedReportComponent(role, prefix + role, data, media, "utf-8")
    raw = canonical_bytes(document)
    machine = component("report.json", raw)
    canonical = component("canonical.json", raw)
    human = component("report.md", b"# Exact completed report\n\nUnavailable is not zero.\n", "text/markdown")
    manifest_document = {"accepted_generation_id": generation_id,
        "schema_id": "arcgrav.shared.schema.report-manifest", "schema_version": "1.0.0",
        "manifest_id": "manifest.json", "extensions": {},
        "generated_at": document["generated_at"], "input_evidence_set_id": "fixture",
        "inputs": [{"artifact_id": "source", "sha256": digest(b'{"retained":true}'), "reference": generation_id + "/evidence.json"}],
        "generator": {"id": "fixture", "version": "1.0.0"},
        "procedure": {"id": "fixture", "version": "1.0.0", "command_or_procedure": "fixture"},
        "report": machine.to_artifact_ref().to_dict(),
        "components": [c.to_artifact_ref().to_dict() for c in (machine, canonical, human)]}
    return GeneratedReportBundle(document, document, manifest_document, machine, canonical,
        human, component("manifest.json", canonical_bytes(manifest_document)))



class ReportingCompletionIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gid = "generation-completion"
        (self.root / self.gid).mkdir()
        (self.root / self.gid / "evidence.json").write_bytes(b'{"retained":true}')
        (self.root / ("." + self.gid + ".terminal")).write_text("accepted")
        self.bundle = report_bundle(self.gid)
        self.record = completion_record(self.gid, status="complete", bundle=self.bundle)
        self.components = report_components(self.bundle)

    def seal(self, record=None, components=None):
        return seal_generation(self.root, self.gid,
            report_components=self.components if components is None else components,
            completion_record=self.record if record is None else record)

    def test_completion_retains_all_exact_components(self):
        self.assertEqual({"markdown", "machine_json", "canonical_evidence_json", "manifest"},
                         {item["role"] for item in self.record["report"]["components"]})
        for item in self.record["report"]["components"]:
            self.assertIn(item["reference"], self.components)
        archive = self.seal()
        retained = read_retained_report(archive)
        self.assertEqual(self.bundle.human.data, retained.markdown_bytes)
        self.assertEqual(self.bundle.report_document, retained.report_document)

    def test_import_opens_exact_bytes_without_generator_or_scorer_execution(self):
        archive = self.seal()
        destination = self.root / "other-installation"
        (destination / "AgMark").mkdir(parents=True)
        with patch("AgMark.shared.reporting.generation.generate_report_bundle", side_effect=AssertionError("must not regenerate")), \
             patch("AgMark.shared.application.score_accepted_treatments", side_effect=AssertionError("must not rescore")):
            imported = import_run_archive(archive, destination)
            self.assertEqual(archive.read_bytes(), imported.read_bytes())
            self.assertEqual(self.bundle.human.data, read_retained_report(imported).markdown_bytes)

    def _replace_json_component(self, field, document):
        component = replace(getattr(self.bundle, field), data=canonical_bytes(document))
        manifest = copy.deepcopy(self.bundle.report_manifest)
        for entry in (manifest["report"], *manifest["components"]):
            if entry["artifact_id"] == component.artifact_id:
                entry["sha256"] = component.sha256
        return replace(self.bundle, **{field: component},
            manifest=replace(self.bundle.manifest, data=canonical_bytes(manifest)),
            report_manifest=manifest)

    def test_telemetry_report_larger_than_manifest_limit_seals_and_imports_exact_bytes(self):
        # Five treatments with five telemetry-bearing observations exceed the
        # metadata bound even though each observation is a valid archive member.
        document = copy.deepcopy(self.bundle.canonical_evidence_document)
        document["treatment_measurements"] = {
            "treatment-" + str(treatment): {"telemetry": {"groups": [{"invocations": [
                {"invocation_id": f"observation-{treatment}-{iteration}",
                 "facts": [{"attributes": {"message": "t" * (700 * 1024)}}]}
                for iteration in range(5)]}]}}
            for treatment in range(5)
        }
        bundle = self._replace_json_component("canonical_evidence", document)
        self.assertGreater(len(bundle.canonical_evidence.data), 16 * 1024 * 1024)
        archive = self.seal(completion_record(self.gid, status="complete", bundle=bundle),
                            report_components(bundle))
        destination = self.root / "imported-installation"
        (destination / "AgMark").mkdir(parents=True)
        with patch("AgMark.shared.reporting.generation.generate_report_bundle",
                   side_effect=AssertionError("must not regenerate")):
            imported = import_run_archive(archive, destination)
            self.assertEqual(bundle.canonical_evidence.data,
                read_archive_member(imported, bundle.canonical_evidence.reference))
            self.assertEqual(bundle.report_document, read_retained_report(imported).report_document)
            self.assertEqual(bundle.human.data, read_retained_report(imported).markdown_bytes)

    def test_machine_report_larger_than_metadata_limit_seals(self):
        document = copy.deepcopy(self.bundle.report_document)
        document["extensions"]["fixture:telemetry"] = "t" * 8192
        bundle = self._replace_json_component("report", document)
        record = completion_record(self.gid, status="complete", bundle=bundle)
        with patch("AgMark.shared.runtime.artifacts.archive._MAX_MANIFEST", 4096):
            archive = self.seal(record, report_components(bundle))
        self.assertEqual(document, read_retained_report(archive).report_document)

    def test_report_manifest_cannot_exceed_metadata_limit(self):
        document = copy.deepcopy(self.bundle.report_manifest)
        document["extensions"]["fixture:oversized"] = "t" * 8192
        bundle = replace(self.bundle,
            manifest=replace(self.bundle.manifest, data=canonical_bytes(document)))
        with patch("AgMark.shared.runtime.artifacts.archive._MAX_MANIFEST", 4096):
            with self.assertRaisesRegex(ArchiveError, "oversized report JSON component"):
                self.seal(completion_record(self.gid, status="complete", bundle=bundle),
                          report_components(bundle))
        self.assertFalse((self.root / (self.gid + ".agmark")).exists())
        self.assertTrue((self.root / self.gid / "evidence.json").is_file())

    def test_report_evidence_cannot_exceed_archive_member_limit(self):
        document = copy.deepcopy(self.bundle.canonical_evidence_document)
        document["treatment_measurements"] = {"fixture": "t" * 8192}
        bundle = self._replace_json_component("canonical_evidence", document)
        with patch("AgMark.shared.runtime.artifacts.archive._MAX_FILE", 4096):
            with self.assertRaisesRegex(ArchiveError, "oversized or suspicious ZIP member"):
                self.seal(completion_record(self.gid, status="complete", bundle=bundle),
                          report_components(bundle))
        self.assertFalse((self.root / (self.gid + ".agmark")).exists())
        self.assertTrue((self.root / self.gid / "evidence.json").is_file())

    def test_missing_duplicate_and_cross_generation_components_fail_closed(self):
        mutations = (
            lambda r: r["report"]["components"].pop(),
            lambda r: r["report"]["components"][1].update(role="machine_json"),
            lambda r: r["report"]["components"][1].update(artifact_id="report.json"),
            lambda r: r["report"].update(report_id="another-report"),
            lambda r: r.update(generation_id="generation-other"),
            lambda r: r.update(schema_version="99.0.0"),
            lambda r: r["validation"].update(status="failed"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                record = copy.deepcopy(self.record)
                mutate(record)
                with self.assertRaises(ArchiveError):
                    self.seal(record)
                self.assertFalse((self.root / (self.gid + ".agmark")).exists())
                self.assertTrue((self.root / self.gid / "evidence.json").is_file())

    def test_changed_report_bytes_cannot_use_original_completion_receipt(self):
        blobs = dict(self.components)
        blobs[self.bundle.human.reference] += b"altered report"
        with self.assertRaises(ArchiveError):
            self.seal(components=blobs)
        self.assertTrue((self.root / self.gid / "evidence.json").is_file())

    def test_failures_never_publish_report_and_preserve_execution_evidence(self):
        for status in ("validation_failed", "report_failed", "not_applicable"):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    completion_record(self.gid, status=status, bundle=self.bundle)
                record = completion_record(self.gid, status=status, diagnostic="automatic_report_failed:ValueError")
                self.assertIsNone(record["report"])
                with self.assertRaises(ArchiveError):
                    self.seal(record)
        with self.assertRaises(ValueError):
            completion_record(self.gid, status="complete")
        with self.assertRaises(ValueError):
            completion_record(self.gid, status="verified", bundle=self.bundle)

    def test_failure_archive_is_readable_without_a_final_report(self):
        record = completion_record(self.gid, status="report_failed", diagnostic="automatic_report_failed:ValueError")
        archive = self.seal(record, components={})
        self.assertIsNone(read_retained_report(archive))


if __name__ == "__main__":
    unittest.main()
