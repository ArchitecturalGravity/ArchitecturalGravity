"""Central .agmark integrity, revision and imported-run checks."""

from __future__ import annotations

import json
import errno
import os
import stat
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
import unittest
from unittest.mock import patch

from AgMark.shared.runtime.artifacts.archive import (
    ArchiveCleanupWarning, ArchiveError, canonical_bytes, digest, read_archive_member, revise_archive, seal_generation as seal_archive, validate_archive,
)
from AgMark.shared.validation.run_archive import (
    import_run_archive, validate_run_archive, read_retained_report, read_completion_record,
)


def seal_generation(root, gid):
    """Construct an explicit new-format producer release for archive tests."""
    accepted = (root / ("." + gid + ".terminal")).read_text() == "accepted"
    record = {
        "schema_id": "arcgrav.shared.run-completion", "schema_version": "2.0.0",
        "generation_id": gid, "completed_at": "2026-11-03T00:00:00+00:00",
        "status": "complete" if accepted else "not_applicable",
        "validation": {"status": "passed" if accepted else "not_applicable", "diagnostic": None},
        "report": None,
    }
    blobs = {}
    if accepted:
        entries = []
        for role in ("markdown", "machine_json", "canonical_evidence_json", "manifest"):
            name = "reports/" + gid + "/" + role
            document = {"accepted_generation_id": gid, "report_id": "report-fixture"}
            if role == "machine_json":
                schema_path = Path(__file__).resolve().parents[2] / "schemas" / "report.schema.json"
                section_names = json.loads(schema_path.read_text())["properties"]["sections"]["required"]
                document.update(schema_id="arcgrav.shared.schema.report", schema_version="3.0.0",
                    report_manifest_id="manifest", extensions={}, report_version="1.0.0",
                    status="complete", generated_at=record["completed_at"],
                    benchmark={"id": "fixture", "version": "1.0.0"},
                    case_set={"id": "fixture", "version": "1.0.0"},
                    treatment_set={"id": "fixture", "version": "1.0.0"},
                    primary_endpoint={"id": "fixture", "version": "1.0.0"}, comparison_track_id="fixture",
                    execution_boundary={"artifact_id": "boundary", "sha256": digest(b"boundary")},
                    observation_counts={name: 0 for name in ("planned", "finalized", "completed", "scored",
                        "failed", "missing", "excluded", "non_scorable")},
                    sections={name: {"availability": "not_applicable", "reason": "fixture"} for name in section_names})
            if role == "manifest":
                document.pop("report_id")
                document.update(schema_id="arcgrav.shared.schema.report-manifest", schema_version="1.0.0",
                    manifest_id="manifest", extensions={}, generated_at=record["completed_at"],
                    inputs=[{"artifact_id": "source", "sha256": digest(b"original evidence"),
                             "reference": gid + "/evidence.bin"}], input_evidence_set_id="fixture",
                    generator={"id": "fixture", "version": "1.0.0"},
                    procedure={"id": "fixture", "version": "1.0.0", "command_or_procedure": "fixture"})
                document["report"] = {key: value for key, value in next(item for item in entries if item["role"] == "machine_json").items() if key != "role"}
                document["components"] = [{key: value for key, value in item.items() if key != "role"} for item in entries]
            data = b"# Exact retained report\n" if role == "markdown" else canonical_bytes(document)
            blobs[name] = data
            entries.append({"role": role, "reference": name, "sha256": digest(data), "artifact_id": role})
        record["report"] = {"report_id": "report-fixture", "components": entries}
    return seal_archive(root, gid, report_components=blobs, completion_record=record)


class RunArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gid = "generation-fixture"
        (self.root / self.gid).mkdir()
        (self.root / self.gid / "evidence.bin").write_bytes(b"original evidence")
        (self.root / ("." + self.gid + ".terminal")).write_text("accepted", encoding="ascii")
        self.archive = seal_generation(self.root, self.gid)

    def test_archive_is_single_sealed_run(self):
        self.assertTrue(self.archive.is_file())
        self.assertFalse((self.root / self.gid).exists())
        result = validate_run_archive(self.archive)
        self.assertTrue(result.consistent)
        self.assertEqual(result.generation_id, self.gid)
        self.assertEqual(read_archive_member(self.archive, self.gid + "/evidence.bin"),
                         b"original evidence")

    def test_sealing_retires_read_only_claims_after_archive_validation(self):
        # Emulate Windows DeleteFile's read-only rejection even on POSIX.
        # Real storage creates both claims read-only; the ordinary ZIP fixture
        # above intentionally uses writable files and cannot catch this bug.
        real_unlink = Path.unlink
        for status in ("accepted", "executed", "blocked"):
            with self.subTest(status=status):
                gid = "generation-readonly-" + status
                folder = self.root / gid
                folder.mkdir()
                (folder / "evidence.bin").write_bytes(b"retained evidence")
                claims = [self.root / ("." + gid + suffix)
                          for suffix in (".terminal", ".generation-claim")]
                claims[0].write_text(status, encoding="ascii")
                claims[1].write_bytes(b"")
                for claim in claims:
                    claim.chmod(0o400)
                retired = []

                def windows_unlink(path, *args, **kwargs):
                    if path in claims and path.exists():
                        if not path.stat().st_mode & stat.S_IWUSR:
                            raise PermissionError(13, "Windows read-only file", str(path))
                        # Never release terminal authority until its exact bytes
                        # are retained in the installed, validated archive.
                        target = self.root / (gid + ".agmark")
                        self.assertEqual(validate_archive(target)["terminal_status"], status)
                        self.assertEqual(read_archive_member(target, claims[0].name),
                                         status.encode("ascii"))
                        retired.append(path)
                    return real_unlink(path, *args, **kwargs)

                with patch.object(Path, "unlink", windows_unlink):
                    target = seal_generation(self.root, gid)
                self.assertEqual(retired, claims)
                self.assertTrue(validate_run_archive(target).consistent)
                self.assertEqual(read_archive_member(target, gid + "/evidence.bin"),
                                 b"retained evidence")
                self.assertFalse(folder.exists())
                self.assertTrue(all(not claim.exists() for claim in claims))

    def test_lock_cleanup_failure_is_a_published_warning_including_source_failure(self):
        for source_failure in (False, True):
            with self.subTest(source_failure=source_failure):
                gid = "generation-lock-warning-" + str(source_failure)
                folder = self.root / gid
                folder.mkdir()
                (folder / "evidence.bin").write_bytes(b"completed run")
                claim = self.root / ("." + gid + ".terminal")
                claim.write_bytes(b"executed")
                lock = self.root / ("." + gid + ".archive-lock")
                real_unlink = Path.unlink

                def deny_cleanup(path, *args, **kwargs):
                    if path == lock or (source_failure and path == claim):
                        raise PermissionError("secret token and private path")
                    return real_unlink(path, *args, **kwargs)

                with patch.object(Path, "unlink", deny_cleanup):
                    with self.assertRaises(ArchiveCleanupWarning) as caught:
                        seal_generation(self.root, gid)
                expected = (("loose_sources:PermissionError",) if source_failure else ())
                self.assertEqual(caught.exception.issues,
                                 expected + ("publication_lock:PermissionError",))
                self.assertNotIn("secret", str(caught.exception))
                self.assertTrue(validate_run_archive(caught.exception.archive_path).consistent)
                self.assertEqual(read_archive_member(caught.exception.archive_path,
                                                    gid + "/evidence.bin"), b"completed run")
                self.assertTrue(lock.is_file())  # No automatic retry or lock bypass.

    def test_source_retirement_errors_preserve_exact_completed_report(self):
        for operation in ("rmtree", "chmod", "progress", "rmdir", "sync"):
            with self.subTest(operation=operation):
                gid = "generation-retirement-" + operation
                folder = self.root / gid
                folder.mkdir()
                (folder / "evidence.bin").write_bytes(b"original evidence")
                (self.root / ("." + gid + ".terminal")).write_bytes(b"accepted")
                real_chmod, real_unlink, real_rmdir = Path.chmod, Path.unlink, Path.rmdir

                def chmod(path, *args, **kwargs):
                    if path == folder:
                        raise PermissionError("private source path")
                    return real_chmod(path, *args, **kwargs)

                def unlink(path, *args, **kwargs):
                    if path.name == gid + ".json":
                        raise PermissionError("private progress path")
                    return real_unlink(path, *args, **kwargs)

                def rmdir(path, *args, **kwargs):
                    if path == self.root / ".agmark-validation":
                        raise PermissionError("private validation path")
                    return real_rmdir(path, *args, **kwargs)

                patches = {
                    "rmtree": lambda: patch("AgMark.shared.runtime.artifacts.archive.shutil.rmtree",
                                             side_effect=PermissionError("private source path")),
                    "chmod": lambda: patch.object(Path, "chmod", chmod),
                    "progress": lambda: patch.object(Path, "unlink", unlink),
                    "rmdir": lambda: patch.object(Path, "rmdir", rmdir),
                    "sync": lambda: patch("AgMark.shared.runtime.artifacts.archive._sync_directory",
                                           side_effect=[None, PermissionError("private sync path")]),
                }
                with patches[operation]():
                    with self.assertRaises(ArchiveCleanupWarning) as caught:
                        seal_generation(self.root, gid)
                self.assertEqual(caught.exception.issues, ("loose_sources:PermissionError",))
                self.assertNotIn("private", str(caught.exception))
                retained = read_retained_report(caught.exception.archive_path)
                self.assertEqual(retained.markdown_bytes, b"# Exact retained report\n")
                self.assertTrue(validate_run_archive(caught.exception.archive_path).consistent)
                self.assertFalse((self.root / ("." + gid + ".archive-lock")).exists())

    def test_uncommitted_lock_cleanup_error_remains_a_failure(self):
        gid = "generation-no-commit"
        lock = self.root / ("." + gid + ".archive-lock")
        real_unlink = Path.unlink

        def deny_lock(path, *args, **kwargs):
            if path == lock:
                raise PermissionError("lock cleanup denied")
            return real_unlink(path, *args, **kwargs)

        # No terminal evidence: there is no publication to preserve as success.
        with patch.object(Path, "unlink", deny_lock):
            with self.assertRaises(PermissionError):
                seal_archive(self.root, gid, report_components={}, completion_record={})
        self.assertFalse((self.root / (gid + ".agmark")).exists())

    def test_post_install_validation_failure_is_not_a_cleanup_warning(self):
        gid = "generation-invalid-install"
        folder = self.root / gid
        folder.mkdir()
        (folder / "evidence.bin").write_bytes(b"evidence")
        claim = self.root / ("." + gid + ".terminal")
        claim.write_bytes(b"executed")
        target = self.root / (gid + ".agmark")
        real_validate = validate_archive

        def reject_install(path, **kwargs):
            if path == target:
                raise ArchiveError("installed bytes rejected")
            return real_validate(path, **kwargs)

        with patch("AgMark.shared.runtime.artifacts.archive.validate_archive", reject_install), \
             patch("AgMark.shared.runtime.artifacts.archive._retire_sources") as retire:
            with self.assertRaisesRegex(ArchiveError, "installed bytes rejected"):
                seal_generation(self.root, gid)
        retire.assert_not_called()
        self.assertTrue(claim.is_file())
        self.assertTrue(folder.is_dir())
        self.assertFalse(target.exists())

    def test_failed_archive_validation_preserves_read_only_terminal_claim(self):
        gid = "generation-unsealed"
        folder = self.root / gid
        folder.mkdir()
        (folder / "evidence.bin").write_bytes(b"evidence")
        claim = self.root / ("." + gid + ".terminal")
        claim.write_bytes(b"accepted")
        claim.chmod(0o400)
        with patch("AgMark.shared.runtime.artifacts.archive.validate_archive",
                   side_effect=ArchiveError("invalid staged archive")):
            with self.assertRaisesRegex(ArchiveError, "invalid staged archive"):
                seal_generation(self.root, gid)
        self.assertEqual(claim.read_bytes(), b"accepted")
        self.assertFalse(claim.stat().st_mode & stat.S_IWUSR)
        self.assertTrue(folder.is_dir())
        self.assertFalse((self.root / (gid + ".agmark")).exists())
        claim.chmod(0o600)  # Permit Windows TemporaryDirectory cleanup.

    def test_cleanup_failure_preserves_valid_archive_for_read_only_import(self):
        gid = "generation-cleanup-failure"
        folder = self.root / gid
        folder.mkdir()
        (folder / "evidence.bin").write_bytes(b"completed run")
        claim = self.root / ("." + gid + ".terminal")
        claim.write_bytes(b"executed")
        claim.chmod(0o400)
        real_unlink = Path.unlink

        def deny_claim_delete(path, *args, **kwargs):
            if path == claim:
                raise PermissionError(13, "injected cleanup denial", str(path))
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", deny_claim_delete):
            with self.assertRaises(ArchiveCleanupWarning) as caught:
                seal_generation(self.root, gid)
        self.assertEqual(caught.exception.issues, ("loose_sources:PermissionError",))
        self.assertNotIn("injected cleanup denial", str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))
        target = self.root / (gid + ".agmark")
        self.assertEqual(caught.exception.archive_path, target)
        self.assertTrue(validate_run_archive(target).consistent)
        self.assertEqual(read_archive_member(target, gid + "/evidence.bin"),
                         b"completed run")
        repository = self.root / "recovery-project"
        (repository / "AgMark").mkdir(parents=True)
        imported = import_run_archive(target, repository)
        self.assertEqual(imported.read_bytes(), target.read_bytes())
        self.assertTrue(validate_run_archive(imported).consistent)

    def test_cleanup_does_not_chmod_symlinked_generation_claim(self):
        gid = "generation-unsafe-claim"
        folder = self.root / gid
        folder.mkdir()
        (folder / "evidence.bin").write_bytes(b"evidence")
        (self.root / ("." + gid + ".terminal")).write_bytes(b"accepted")
        outside = self.root / "unrelated.txt"
        outside.write_bytes(b"unrelated")
        outside.chmod(0o400)
        claim = self.root / ("." + gid + ".generation-claim")
        try:
            claim.symlink_to(outside)
        except (OSError, NotImplementedError):
            outside.chmod(0o600)
            self.skipTest("symlink creation unavailable")
        try:
            with self.assertRaises(ArchiveCleanupWarning) as caught:
                seal_generation(self.root, gid)
            self.assertEqual(caught.exception.issues, ("loose_sources:ArchiveError",))
            self.assertTrue(claim.is_symlink())
            self.assertEqual(outside.read_bytes(), b"unrelated")
            self.assertFalse(outside.stat().st_mode & stat.S_IWUSR)
            self.assertTrue(validate_run_archive(self.root / (gid + ".agmark")).consistent)
        finally:
            outside.chmod(0o600)
            claim.unlink(missing_ok=True)

    def test_renaming_extension_does_not_change_bytes(self):
        renamed = self.archive.with_suffix(".zip")
        self.archive.rename(renamed)
        renamed.rename(self.archive)
        self.assertTrue(validate_run_archive(self.archive).consistent)

    def test_foreign_extension_rejected(self):
        self.assertFalse(validate_run_archive(self.archive.with_suffix(".zip")).consistent)

    def test_corrupt_member_is_rejected(self):
        with ZipFile(self.archive, "a") as bundle:
            bundle.writestr("extra.txt", "unlisted")
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_duplicate_entries_rejected(self):
        with ZipFile(self.archive, "a") as bundle:
            bundle.writestr(self.gid + "/evidence.bin", "evil")
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def _check_stage_fsync(self, operation, *, fail):
        gid = "generation-fsync-" + operation + ("-failure" if fail else "-success")
        if operation == "seal":
            folder = self.root / gid
            folder.mkdir()
            (folder / "evidence.bin").write_bytes(b"original evidence")
            (self.root / ("." + gid + ".terminal")).write_bytes(b"accepted")
            target = self.root / (gid + ".agmark")
            before = None
            publish = lambda: seal_generation(self.root, gid)
        else:
            target = self.archive
            before = target.read_bytes()
            publish = lambda: revise_archive(self.root, self.gid,
                                             {"history/presentation.json": b"{}"})
        real_open, real_fsync = Path.open, os.fsync
        staged_streams = {}
        calls = []

        def track_open(path, *args, **kwargs):
            stream = real_open(path, *args, **kwargs)
            if path.name.startswith(".agmark-stage-"):
                staged_streams[stream.fileno()] = stream
            return stream

        def windows_fsync(descriptor):
            # Directory fsync on POSIX is independent of the Windows file rule.
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                stream = staged_streams.get(descriptor)
                self.assertIsNotNone(stream, "regular-file fsync must target the staged ZIP")
                self.assertFalse(stream.closed)
                calls.append(stream.writable())
                if not stream.writable():
                    raise OSError(errno.EBADF, "Windows requires a writable descriptor")
                if fail:
                    raise OSError(errno.EIO, "injected staged archive sync failure")
            return real_fsync(descriptor)

        with patch.object(Path, "open", track_open), \
             patch("AgMark.shared.runtime.artifacts.archive.os.fsync", windows_fsync):
            if fail:
                with self.assertRaisesRegex(OSError, "injected staged archive sync failure"):
                    publish()
            else:
                self.assertEqual(publish(), target)
        self.assertEqual(calls, [True], "stage fsync must run exactly once on a writable file")
        self.assertFalse(list(self.root.glob(".agmark-stage-*")))
        if fail and before is None:
            self.assertFalse(target.exists())
            self.assertEqual((folder / "evidence.bin").read_bytes(), b"original evidence")
            self.assertEqual((self.root / ("." + gid + ".terminal")).read_bytes(), b"accepted")
        elif fail:
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(validate_archive(target)["revision"], 1)
        else:
            self.assertTrue(validate_run_archive(target).consistent)
            self.assertEqual(validate_archive(target)["revision"], 1 if operation == "seal" else 2)

    def test_seal_and_revision_fsync_use_writable_stage_descriptors(self):
        for operation in ("seal", "revise"):
            with self.subTest(operation=operation):
                self._check_stage_fsync(operation, fail=False)

    def test_seal_and_revision_stage_fsync_failures_are_not_swallowed(self):
        for operation in ("seal", "revise"):
            with self.subTest(operation=operation):
                self._check_stage_fsync(operation, fail=True)

    def test_revision_does_not_modify_original_evidence(self):
        first = validate_archive(self.archive)
        revise_archive(self.root, self.gid, {"history/presentation.json": b"{}"})
        second = validate_archive(self.archive)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(second["core_sha256"], first["core_sha256"])
        self.assertEqual(second["core_files"], first["core_files"])
        self.assertEqual(read_archive_member(self.archive, self.gid + "/evidence.bin"), b"original evidence")

    def test_reports_are_immutable(self):
        with self.assertRaises(ArchiveError):
            revise_archive(self.root, self.gid, {"reports/example/report.md": b"second"})
        with self.assertRaises(ArchiveError):
            revise_archive(self.root, self.gid, {"verification/new.json": b"{}"})

    def test_presentation_can_be_revised(self):
        revise_archive(self.root, self.gid, {"history/presentation.json": b'{"p":1}'})
        revise_archive(self.root, self.gid, {"history/presentation.json": b'{"p":2}'})
        self.assertEqual(validate_archive(self.archive)["revision"], 3)
        self.assertEqual(read_archive_member(self.archive, "history/presentation.json"), b'{"p":2}')

    def _rewrite(self, mutation):
        with ZipFile(self.archive) as source:
            blobs = {entry.filename: source.read(entry.filename) for entry in source.infolist()}
        manifest = json.loads(blobs["manifest.json"])
        mutation(manifest, blobs)
        blobs["manifest.json"] = canonical_bytes(manifest)
        with ZipFile(self.archive, "w", compression=ZIP_DEFLATED) as output:
            for name, data in sorted(blobs.items()):
                output.writestr(name, data)

    def test_manifest_rehash_cannot_change_original_core_identity(self):
        def change(manifest, contents):
            name = self.gid + "/evidence.bin"
            contents[name] = b"modified core evidence"
            manifest["files"][name] = digest(contents[name])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_prior_report_cannot_be_replaced_in_later_revision(self):
        report = "reports/" + self.gid + "/markdown"
        revise_archive(self.root, self.gid, {"history/presentation.json": b"{}"})
        def change(manifest, contents):
            contents[report] = b"changed"
            manifest["files"][report] = digest(contents[report])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_large_compressible_evidence_is_permitted(self):
        gid = "generation-high-compression"
        folder = self.root / gid
        folder.mkdir()
        (folder / "evidence.bin").write_bytes(b"0" * (2 * 1024 * 1024))
        (self.root / ("." + gid + ".terminal")).write_text("accepted")
        target = seal_generation(self.root, gid)
        self.assertTrue(validate_run_archive(target).consistent)

    def test_blocked_run_without_observations_is_sealable(self):
        gid = "generation-blocked"
        (self.root / ("." + gid + ".terminal")).write_text("blocked")
        target = seal_generation(self.root, gid)
        manifest = validate_archive(target)
        self.assertEqual(manifest["terminal_status"], "blocked")
        self.assertIn(gid + "/blocked-generation.json", manifest["core_files"])
        self.assertNotIn(gid + "/evidence.bin", manifest["core_files"])

    def test_retained_report_opens_exact_bytes_without_producer(self):
        report = read_retained_report(self.archive)
        self.assertEqual(report.markdown_bytes, b"# Exact retained report\n")
        self.assertEqual(report.report_id, "report-fixture")
        self.assertNotIn("claim_eligibility", report.completion_record)

    def test_old_format_is_rejected(self):
        self._rewrite(lambda manifest, contents: manifest.update(format="agmark.run-archive/2"))
        self.assertFalse(validate_run_archive(self.archive).consistent)
        with self.assertRaises(ArchiveError):
            read_retained_report(self.archive)

    def test_payload_rich_v3_format_is_rejected(self):
        self._rewrite(lambda manifest, contents: manifest.update(format="agmark.run-archive/3"))
        self.assertFalse(validate_run_archive(self.archive).consistent)
        with self.assertRaises(ArchiveError):
            read_retained_report(self.archive)

    def test_unknown_manifest_metadata_is_rejected(self):
        self._rewrite(lambda manifest, contents: manifest.update(hostname="private-host"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_publication_timestamp_cannot_carry_arbitrary_metadata(self):
        self._rewrite(lambda manifest, contents: manifest.update(sealed_at="/home/private-person"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_free_form_completion_diagnostic_is_rejected(self):
        def change(manifest, contents):
            name = "completion/release.json"
            record = json.loads(contents[name])
            record["validation"]["diagnostic"] = "private-host /home/private-user"
            contents[name] = canonical_bytes(record)
            manifest["files"][name] = digest(contents[name])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_unknown_completion_validation_metadata_is_rejected(self):
        def change(manifest, contents):
            name = "completion/release.json"
            record = json.loads(contents[name])
            record["validation"]["environment"] = {"private": "value"}
            contents[name] = canonical_bytes(record)
            manifest["files"][name] = digest(contents[name])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_structural_evidence_cannot_hide_as_opaque_scoring_bytes(self):
        for label, name, data in (
            ("opaque", "observation.json", b"not a structural observation"),
            ("unmarked", "observation.json", canonical_bytes({"extensions": {}})),
            ("legacy-boundary", "execution-boundary.json", canonical_bytes({"host": "/home/private"})),
        ):
            with self.subTest(label=label):
                gid = "generation-" + label
                folder = self.root / gid
                folder.mkdir()
                (folder / name).write_bytes(data)
                (self.root / ("." + gid + ".terminal")).write_text("executed")
                with self.assertRaises(ArchiveError):
                    seal_generation(self.root, gid)
                self.assertFalse((self.root / (gid + ".agmark")).exists())
                self.assertEqual((folder / name).read_bytes(), data)

    def test_current_observation_privacy_is_enforced_before_archive_publication(self):
        from AgMark.shared.software_testing.adapters.execution.test_emission import CanonicalExecutionEmissionTests
        for unsafe in (False, True):
            with self.subTest(unsafe=unsafe), TemporaryDirectory() as temporary:
                root = Path(temporary)
                gid = "generation-a"
                folder = root / gid
                folder.mkdir()
                document = CanonicalExecutionEmissionTests()._emit()
                if unsafe:
                    document["extensions"]["private:metadata"] = {"hostname": "personal-host"}
                (folder / "observation.json").write_bytes(canonical_bytes(document))
                (root / ("." + gid + ".terminal")).write_text("executed")
                if unsafe:
                    with self.assertRaises(ArchiveError):
                        seal_generation(root, gid)
                    self.assertFalse((root / (gid + ".agmark")).exists())
                else:
                    target = seal_generation(root, gid)
                    self.assertEqual(validate_archive(target)["format"], "agmark.run-archive/4")
                    # Rehash every integrity binding: structural privacy must
                    # still fail, independently of self-asserted ZIP hashes.
                    with ZipFile(target) as source:
                        blobs = {name: source.read(name) for name in source.namelist()}
                    document["extensions"]["private:metadata"] = {"hostname": "personal-host"}
                    name = gid + "/observation.json"
                    blobs[name] = canonical_bytes(document)
                    manifest = json.loads(blobs["manifest.json"])
                    manifest["core_files"][name] = manifest["files"][name] = digest(blobs[name])
                    manifest["core_sha256"] = digest(canonical_bytes(manifest["core_files"]))
                    record = json.loads(blobs["completion/release.json"])
                    record["core_sha256"] = manifest["core_sha256"]
                    blobs["completion/release.json"] = canonical_bytes(record)
                    manifest["files"]["completion/release.json"] = digest(blobs["completion/release.json"])
                    blobs["manifest.json"] = canonical_bytes(manifest)
                    with ZipFile(target, "w", compression=ZIP_DEFLATED) as output:
                        for name, data in blobs.items():
                            output.writestr(name, data)
                    with self.assertRaises(ArchiveError):
                        validate_archive(target)
                    original = gid + "/observation.json"
                    renamed = gid + "/innocent.bin"
                    blobs[renamed] = blobs.pop(original)
                    manifest["core_files"][renamed] = manifest["core_files"].pop(original)
                    manifest["files"][renamed] = manifest["files"].pop(original)
                    manifest["core_sha256"] = digest(canonical_bytes(manifest["core_files"]))
                    record["core_sha256"] = manifest["core_sha256"]
                    blobs["completion/release.json"] = canonical_bytes(record)
                    manifest["files"]["completion/release.json"] = digest(blobs["completion/release.json"])
                    blobs["manifest.json"] = canonical_bytes(manifest)
                    with ZipFile(target, "w", compression=ZIP_DEFLATED) as output:
                        for name, data in blobs.items():
                            output.writestr(name, data)
                    with self.assertRaises(ArchiveError):
                        validate_archive(target)

    def test_replay_companion_cannot_retain_unlisted_or_private_metadata(self):
        for variant in ("valid", "unknown-field", "unlisted-source", "raw-capture", "private-identity", "unrelated-scored"):
            with self.subTest(variant=variant), TemporaryDirectory() as temporary:
                root = Path(temporary)
                gid = "generation-companion"
                (root / gid).mkdir()
                (root / gid / "evidence.bin").write_bytes(b"benchmark evidence")
                (root / ("." + gid + ".terminal")).write_text("executed")
                folder = root / ".agmark-validation" / gid
                folder.mkdir(parents=True)
                manifest = {"generation_id": gid, "accepted_snapshot_id": "accepted-snapshot:" + "a" * 64,
                    "run_plan_sha256": digest(b"plan"), "execution_boundary_fingerprint": digest(b"boundary"),
                    "scored_evidence": {}, "validations": [], "captures": [], "sources": [],
                    "scope": "configuration_equivalent_replay", "included_in_score": False}
                if variant == "unknown-field":
                    manifest["hostname"] = "personal-host"
                elif variant == "private-identity":
                    manifest["accepted_snapshot_id"] = "/home/private-person"
                elif variant == "unrelated-scored":
                    manifest["scored_evidence"] = {"artifact": digest(b"not retained")}
                elif variant == "unlisted-source":
                    (folder / "private.json").write_bytes(canonical_bytes({"home": "/home/person"}))
                elif variant == "raw-capture":
                    data = canonical_bytes([{"path": "/home/person", "authorization": "private"}])
                    checksum = digest(data)
                    reference = "capture-" + checksum.removeprefix("sha256:") + ".json"
                    (folder / reference).write_bytes(data)
                    manifest["captures"].append({"reference": reference, "sha256": checksum})
                raw = canonical_bytes(manifest)
                (folder / "manifest.json").write_bytes(raw)
                (folder / "manifest.sha256").write_text(digest(raw))
                if variant == "valid":
                    self.assertTrue(validate_archive(seal_generation(root, gid)))
                else:
                    with self.assertRaises(ArchiveError):
                        seal_generation(root, gid)
                    self.assertFalse((root / (gid + ".agmark")).exists())

    def test_current_plan_rejects_arbitrary_namespaced_metadata(self):
        from AgMark.shared.software_testing.runtime.test_orchestration import OrchestrationPlanningRuntimeTests
        fixture = OrchestrationPlanningRuntimeTests()
        fixture.setUp()
        original = fixture._plan().to_dict()
        for unsafe in (False, True):
            with self.subTest(unsafe=unsafe), TemporaryDirectory() as temporary:
                root = Path(temporary)
                gid = "generation-plan-policy"
                folder = root / gid / "accepted-plan"
                folder.mkdir(parents=True)
                document = json.loads(canonical_bytes(original))
                if unsafe:
                    document["extensions"]["private:metadata"] = {"hostname": "personal-host"}
                    from AgMark.shared.runtime.identity.canonical import canonical_sha256
                    document["plan_sha256"] = canonical_sha256({key: value for key, value in document.items()
                                                               if key != "plan_sha256"})
                (folder / "plan.json").write_bytes(canonical_bytes(document))
                (root / ("." + gid + ".terminal")).write_text("executed")
                if unsafe:
                    with self.assertRaises(ArchiveError):
                        seal_generation(root, gid)
                else:
                    self.assertTrue(validate_archive(seal_generation(root, gid)))

    def test_missing_completion_record_rejected_even_with_rehashed_manifest(self):
        def change(manifest, contents):
            contents.pop("completion/release.json")
            manifest["files"].pop("completion/release.json")
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_sanitized_completion_diagnostics_are_retained(self):
        from AgMark.shared.runtime.completion_diagnostics import completion_diagnostic
        rows = [completion_diagnostic("report_build", "passed")]
        def change(manifest, contents):
            record = json.loads(contents["completion/release.json"])
            record["diagnostics"] = rows
            contents["completion/release.json"] = canonical_bytes(record)
            manifest["files"]["completion/release.json"] = digest(contents["completion/release.json"])
        self._rewrite(change)
        self.assertEqual(rows, read_completion_record(self.archive)["diagnostics"])

    def test_unsanitized_completion_diagnostics_fail_closed(self):
        def change(manifest, contents):
            record = json.loads(contents["completion/release.json"])
            record["diagnostics"] = [{"stage": "report_build", "message": "raw exception payload"}]
            contents["completion/release.json"] = canonical_bytes(record)
            manifest["files"]["completion/release.json"] = digest(contents["completion/release.json"])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_prior_completion_version_rejected_after_rehash(self):
        def change(manifest, contents):
            record = json.loads(contents["completion/release.json"])
            record["schema_version"] = "1.0.0"
            contents["completion/release.json"] = canonical_bytes(record)
            manifest["files"]["completion/release.json"] = digest(contents["completion/release.json"])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_removed_completion_field_rejected_after_rehash(self):
        def change(manifest, contents):
            record = json.loads(contents["completion/release.json"])
            record["claim_eligibility"] = "not_established"
            contents["completion/release.json"] = canonical_bytes(record)
            manifest["files"]["completion/release.json"] = digest(contents["completion/release.json"])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_completion_generation_binding_rejected(self):
        def change(manifest, contents):
            record = json.loads(contents["completion/release.json"])
            record["generation_id"] = "generation-other"
            contents["completion/release.json"] = canonical_bytes(record)
            manifest["files"]["completion/release.json"] = digest(contents["completion/release.json"])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_report_changed_with_rehashed_inventory_still_fails_receipt(self):
        def change(manifest, contents):
            name = "reports/" + self.gid + "/markdown"
            contents[name] = b"changed report"
            manifest["files"][name] = digest(contents[name])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_missing_required_report_role_fails_closed(self):
        def change(manifest, contents):
            record = json.loads(contents["completion/release.json"])
            record["report"]["components"][0]["role"] = "unknown"
            contents["completion/release.json"] = canonical_bytes(record)
            manifest["files"]["completion/release.json"] = digest(contents["completion/release.json"])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_wrong_completion_state_fails_without_raw_report_view(self):
        def change(manifest, contents):
            record = json.loads(contents["completion/release.json"])
            record["status"] = "report_failed"
            contents["completion/release.json"] = canonical_bytes(record)
            manifest["files"]["completion/release.json"] = digest(contents["completion/release.json"])
        self._rewrite(change)
        with self.assertRaises(ArchiveError):
            read_retained_report(self.archive)

    def test_invalid_completion_shape_returns_invalid_not_exception(self):
        def change(manifest, contents):
            record = json.loads(contents["completion/release.json"])
            record["status"] = []
            contents["completion/release.json"] = canonical_bytes(record)
            manifest["files"]["completion/release.json"] = digest(contents["completion/release.json"])
        self._rewrite(change)
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def _rewrite_report_document(self, role, mutation):
        """Rehash every binding so rejection tests exercise the semantic contract."""
        def change(manifest, contents):
            record_name = "completion/release.json"
            record = json.loads(contents[record_name])
            entries = {item["role"]: item for item in record["report"]["components"]}
            entry = entries[role]
            document = json.loads(contents[entry["reference"]])
            mutation(document)
            contents[entry["reference"]] = canonical_bytes(document)
            entry["sha256"] = digest(contents[entry["reference"]])
            manifest["files"][entry["reference"]] = entry["sha256"]
            if role != "manifest":
                manifest_entry = entries["manifest"]
                report_manifest = json.loads(contents[manifest_entry["reference"]])
                for component in [report_manifest["report"], *report_manifest["components"]]:
                    if component["reference"] == entry["reference"]:
                        component["sha256"] = entry["sha256"]
                contents[manifest_entry["reference"]] = canonical_bytes(report_manifest)
                manifest_entry["sha256"] = digest(contents[manifest_entry["reference"]])
                manifest["files"][manifest_entry["reference"]] = manifest_entry["sha256"]
            contents[record_name] = canonical_bytes(record)
            manifest["files"][record_name] = digest(contents[record_name])
        self._rewrite(change)

    def test_old_report_schema_rejected_after_all_hashes_recomputed(self):
        self._rewrite_report_document("machine_json", lambda document: document.update(schema_version="2.0.0"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_old_manifest_schema_rejected_after_all_hashes_recomputed(self):
        self._rewrite_report_document("manifest", lambda document: document.update(
            schema_id="arcgrav.shared.schema.reconstruction-manifest"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_invalid_report_status_rejected_after_all_hashes_recomputed(self):
        self._rewrite_report_document("machine_json", lambda document: document.update(status="invalid"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_removed_report_field_rejected_after_all_hashes_recomputed(self):
        self._rewrite_report_document("machine_json", lambda document: document.update(claim_state="eligible"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_missing_report_section_rejected_after_all_hashes_recomputed(self):
        self._rewrite_report_document("machine_json", lambda document: document["sections"].pop("executive_summary"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_missing_manifest_generator_rejected_after_all_hashes_recomputed(self):
        self._rewrite_report_document("manifest", lambda document: document.pop("generator"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_canonical_generation_mismatch_rejected_after_all_hashes_recomputed(self):
        self._rewrite_report_document("canonical_evidence_json", lambda document: document.update(accepted_generation_id="other"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_mismatched_manifest_identity_rejected_after_rehash(self):
        self._rewrite_report_document("machine_json", lambda document: document.update(report_manifest_id="other"))
        self.assertFalse(validate_run_archive(self.archive).consistent)

    def test_blocked_completion_does_not_invent_report(self):
        gid = "generation-blocked-report"
        (self.root / ("." + gid + ".terminal")).write_text("blocked")
        target = seal_generation(self.root, gid)
        self.assertIsNone(read_retained_report(target))
        self.assertEqual(read_completion_record(target)["status"], "not_applicable")

    def test_external_hash_anchor_rejects_mismatch(self):
        result = validate_run_archive(self.archive, expected_archive_sha256="sha256:" + "0"*64)
        self.assertFalse(result.consistent)

    def test_import_rejects_loose_generation_and_claim_collisions(self):
        for suffix in ("directory", ".generation-claim", ".terminal", ".deleted"):
            with self.subTest(suffix=suffix):
                repository = self.root / ("collision-" + suffix)
                destination = repository / "AgMark" / "run_evidence"
                destination.mkdir(parents=True)
                conflict = destination / (self.gid if suffix == "directory" else "." + self.gid + suffix)
                if suffix == "directory":
                    conflict.mkdir()
                else:
                    conflict.write_bytes(b"live")
                with self.assertRaisesRegex(ArchiveError, "already retained, active, or deleted"):
                    import_run_archive(self.archive, repository)
                self.assertFalse((destination / self.archive.name).exists())
                self.assertTrue(conflict.exists())

    def test_import_holds_shared_lock_against_live_mutation(self):
        from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination, ArtifactPayload, RETAINABLE_EVIDENCE
        repository = self.root / "race-project"
        (repository / "AgMark").mkdir(parents=True)
        destination = repository / "AgMark" / "run_evidence"
        store = FilesystemArtifactStore(PublicationDestination.central(destination, repository_root=repository))
        real_copy = shutil.copyfileobj
        attempted = []
        def interleave_copy(source, output, length):
            payload = ArtifactPayload(artifact_id="live", role="runtime_evidence", relative_path="live.json",
                data=b"live", provenance="test", retention_class=RETAINABLE_EVIDENCE)
            for action in (lambda: store.publish_generation(self.gid, [payload]),
                           lambda: store.claim_terminal_status(self.gid, "blocked"),
                           lambda: store.delete_generation(self.gid)):
                with self.assertRaisesRegex(ArchiveError, "another archive revision"):
                    action()
                attempted.append(True)
            return real_copy(source, output, length)
        with patch("AgMark.shared.validation.run_archive.shutil.copyfileobj", side_effect=interleave_copy):
            target = import_run_archive(self.archive, repository)
        self.assertEqual(len(attempted), 3)
        self.assertEqual(target.read_bytes(), self.archive.read_bytes())
        self.assertFalse((destination / self.gid).exists())
        self.assertFalse((destination / ("." + self.gid + ".archive-lock")).exists())

    def test_import_rejects_generation_with_active_publication_lock(self):
        from AgMark.shared.runtime.artifacts.archive import _publication_lock
        repository = self.root / "locked-project"
        destination = repository / "AgMark" / "run_evidence"
        destination.mkdir(parents=True)
        with _publication_lock(destination, self.gid):
            with self.assertRaisesRegex(ArchiveError, "another archive revision"):
                import_run_archive(self.archive, repository)
        self.assertFalse((destination / self.archive.name).exists())

    def test_import_is_read_only_and_rejects_collision(self):
        repository = self.root / "project"
        (repository / "AgMark").mkdir(parents=True)
        target = import_run_archive(self.archive, repository)
        self.assertEqual(target, repository / "AgMark" / "run_evidence" / self.archive.name)
        self.assertTrue(validate_run_archive(target).consistent)
        with self.assertRaises(ArchiveError):
            import_run_archive(self.archive, repository)


if __name__ == "__main__":
    unittest.main()
