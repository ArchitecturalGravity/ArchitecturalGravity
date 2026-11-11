"""Bounded verified ZIP sessions preserve integrity while avoiding repeated opens."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile, ZipInfo

from AgMark.shared.runtime.artifacts import archive as archive_module
from AgMark.shared.runtime.artifacts.archive import ArchiveError, VerifiedArchiveReader, digest
from AgMark.shared.software_testing.validation.test_imported_run import seal_generation


class VerifiedArchiveReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gid = "generation-reader"
        folder = self.root / self.gid
        folder.mkdir()
        self.member = self.gid + "/evidence.bin"
        self.payload = b"original evidence"
        (folder / "evidence.bin").write_bytes(self.payload)
        (self.root / ("." + self.gid + ".terminal")).write_text("accepted", encoding="ascii")
        self.path = seal_generation(self.root, self.gid)
        self.original = self.path.read_bytes()

    def test_multiple_reads_and_verifications_use_one_zip_open(self):
        member_opens = []
        real_open = ZipFile.open

        def track_member_open(bundle, name, *args, **kwargs):
            member_opens.append(name.filename if isinstance(name, ZipInfo) else name)
            return real_open(bundle, name, *args, **kwargs)

        with patch.object(archive_module, "ZipFile", wraps=ZipFile) as opened, \
                patch.object(ZipFile, "open", track_member_open):
            with VerifiedArchiveReader(self.path) as reader:
                self.assertEqual(reader.manifest["generation_id"], self.gid)
                for _ in range(3):
                    self.assertEqual(reader.read_member(self.member), self.payload)
                    self.assertIsNone(reader.verify_member(self.member, digest(self.payload)))
                self.assertEqual(reader.read_member("reports/" + self.gid + "/markdown"),
                                 b"# Exact retained report\n")
            self.assertEqual(opened.call_count, 1)
            # One integrity read, one structural-policy sniff, and six explicit
            # requests, not a full rescan on every member or manifest access.
            self.assertEqual(member_opens.count(self.member), 8)

    def test_every_requested_member_is_rehashed_after_initial_validation(self):
        # Alter the stream rather than the file: identity checks alone must not
        # substitute for hashing the actual bytes returned by each operation.
        for operation in ("read_member", "verify_member"):
            with self.subTest(operation=operation):
                with VerifiedArchiveReader(self.path) as reader:
                    self.assertEqual(reader.read_member(self.member), self.payload)
                    real_open = ZipFile.open
                    calls = []

                    def changed_stream(bundle, name, *args, **kwargs):
                        actual_name = name.filename if isinstance(name, ZipInfo) else name
                        if actual_name == self.member:
                            calls.append(actual_name)
                            return BytesIO(b"modified evidence")
                        return real_open(bundle, name, *args, **kwargs)

                    with patch.object(ZipFile, "open", changed_stream):
                        with self.assertRaises(ArchiveError):
                            getattr(reader, operation)(self.member)
                    self.assertEqual(calls, [self.member])

    def test_verify_member_checks_optional_expected_digest(self):
        with VerifiedArchiveReader(self.path) as reader:
            self.assertIsNone(reader.verify_member(self.member))
            self.assertIsNone(reader.verify_member(self.member, digest(self.payload)))
            with self.assertRaises(ArchiveError):
                reader.verify_member(self.member, digest(b"other evidence"))

    def test_verify_member_uses_bounded_stream_reads(self):
        class BoundedStream(BytesIO):
            def read(stream, size=-1):
                self.assertGreater(size, 0, "verification must not buffer an entire member")
                return super().read(size)

        with VerifiedArchiveReader(self.path) as reader:
            real_open = ZipFile.open

            def bounded_stream(bundle, name, *args, **kwargs):
                actual_name = name.filename if isinstance(name, ZipInfo) else name
                if actual_name == self.member:
                    return BoundedStream(self.payload)
                return real_open(bundle, name, *args, **kwargs)

            with patch.object(ZipFile, "open", bounded_stream):
                self.assertIsNone(reader.verify_member(self.member))

    def test_entry_validates_all_members_and_failed_session_cannot_be_reused(self):
        with ZipFile(self.path) as bundle:
            contents = {name: bundle.read(name) for name in bundle.namelist()}
        contents[self.member] = b"changed but valid ZIP entry"
        with ZipFile(self.path, "w") as bundle:
            for name, data in contents.items():
                bundle.writestr(name, data)
        reader = VerifiedArchiveReader(self.path)
        with self.assertRaises(ArchiveError):
            with reader:
                self.fail("full validation must precede all requested reads")
        self.path.write_bytes(self.original)
        with self.assertRaises(ArchiveError):
            reader.__enter__()
        with VerifiedArchiveReader(self.path) as fresh:
            self.assertEqual(fresh.read_member(self.member), self.payload)

    def test_manifest_is_a_deep_copy_not_mutable_inventory_authority(self):
        with VerifiedArchiveReader(self.path) as reader:
            manifest = reader.manifest
            manifest["files"][self.member] = digest(b"forged evidence")
            manifest["core_files"].clear()
            manifest["generation_id"] = "generation-forged"
            self.assertEqual(reader.manifest["files"][self.member], digest(self.payload))
            self.assertEqual(reader.manifest["core_files"][self.member], digest(self.payload))
            self.assertEqual(reader.manifest["generation_id"], self.gid)
            self.assertEqual(reader.read_member(self.member), self.payload)
            self.assertIsNone(reader.verify_member(self.member, digest(self.payload)))

    def test_unlisted_and_unsafe_requested_members_are_rejected(self):
        with VerifiedArchiveReader(self.path) as reader:
            for name in (self.gid + "/missing.json", "../outside", "/absolute", "generation-reader\\evidence"):
                for operation in ("read_member", "verify_member"):
                    with self.subTest(name=name, operation=operation), self.assertRaises(ArchiveError):
                        getattr(reader, operation)(name)

    def test_operations_require_an_open_session_and_reader_is_single_use(self):
        reader = VerifiedArchiveReader(self.path)
        with self.assertRaises(ArchiveError):
            reader.read_member(self.member)
        with reader:
            self.assertEqual(reader.read_member(self.member), self.payload)
        for operation in (lambda: reader.read_member(self.member),
                          lambda: reader.verify_member(self.member),
                          lambda: reader.manifest,
                          reader.__enter__):
            with self.assertRaises(ArchiveError):
                operation()
        with VerifiedArchiveReader(self.path) as fresh:
            self.assertEqual(fresh.read_member(self.member), self.payload)

    def test_exception_exit_closes_session(self):
        reader = VerifiedArchiveReader(self.path)
        with self.assertRaisesRegex(RuntimeError, "caller failed"):
            with reader:
                raise RuntimeError("caller failed")
        with self.assertRaises(ArchiveError):
            reader.read_member(self.member)
        with self.assertRaises(ArchiveError):
            reader.__enter__()

    def test_cross_thread_operations_fail_without_invalidating_owner(self):
        with VerifiedArchiveReader(self.path) as reader:
            with ThreadPoolExecutor(max_workers=1) as executor:
                for operation in (lambda: reader.read_member(self.member),
                                  lambda: reader.verify_member(self.member),
                                  lambda: reader.manifest):
                    with self.assertRaises(ArchiveError):
                        executor.submit(operation).result(timeout=10)
            self.assertEqual(reader.read_member(self.member), self.payload)

    def test_concurrent_independent_sessions_succeed(self):
        barrier = Barrier(2)

        def read_independently():
            with VerifiedArchiveReader(self.path) as reader:
                barrier.wait(timeout=10)
                result = [reader.read_member(self.member) for _ in range(3)]
                reader.verify_member(self.member, digest(self.payload))
                return result

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(read_independently) for _ in range(2)]
            for future in futures:
                self.assertEqual(future.result(timeout=20), [self.payload] * 3)

    def test_replacement_and_deletion_invalidate_session(self):
        for change in ("replace", "delete"):
            for operation in ("read_member", "verify_member", "manifest"):
                with self.subTest(change=change, operation=operation):
                    self.path.write_bytes(self.original)
                    with self.assertRaises(ArchiveError), VerifiedArchiveReader(self.path) as reader:
                        if change == "replace":
                            replacement = self.root / "replacement.tmp"
                            replacement.write_bytes(self.original)
                            os.replace(replacement, self.path)
                        else:
                            self.path.unlink()
                        with self.assertRaises(ArchiveError):
                            if operation == "manifest":
                                _ = reader.manifest
                            else:
                                getattr(reader, operation)(self.member)

    def test_symlink_replacement_invalidates_session(self):
        target = self.root / "unchanged-copy.agmark"
        target.write_bytes(self.original)
        with self.assertRaises(ArchiveError), VerifiedArchiveReader(self.path) as reader:
            self.path.unlink()
            self.path.symlink_to(target)
            with self.assertRaises(ArchiveError):
                reader.read_member(self.member)
        with self.assertRaises(ArchiveError):
            with VerifiedArchiveReader(self.path):
                self.fail("symlink must not be accepted")

    def test_in_place_drift_even_with_unchanged_member_bytes_is_rejected(self):
        for operation in ("read_member", "verify_member"):
            with self.subTest(operation=operation):
                self.path.write_bytes(self.original)
                with self.assertRaises(ArchiveError), VerifiedArchiveReader(self.path) as reader:
                    # A trailing byte leaves all requested ZIP contents intact.
                    with self.path.open("ab") as stream:
                        stream.write(b"x")
                    with self.assertRaises(ArchiveError):
                        getattr(reader, operation)(self.member)

    def test_drift_during_member_read_is_rejected_before_returning_bytes(self):
        for operation in ("read_member", "verify_member"):
            with self.subTest(operation=operation):
                self.path.write_bytes(self.original)
                with self.assertRaises(ArchiveError), VerifiedArchiveReader(self.path) as reader:
                    real_open = ZipFile.open

                    def mutate_after_open(bundle, name, *args, **kwargs):
                        stream = real_open(bundle, name, *args, **kwargs)
                        actual_name = name.filename if isinstance(name, ZipInfo) else name
                        if actual_name == self.member:
                            with self.path.open("ab") as output:
                                output.write(b"x")
                        return stream

                    with patch.object(ZipFile, "open", mutate_after_open):
                        with self.assertRaises(ArchiveError):
                            getattr(reader, operation)(self.member)

    def test_duplicate_unsafe_and_symlink_zip_members_rejected_on_entry(self):
        for kind in ("duplicate", "traversal", "symlink"):
            with self.subTest(kind=kind):
                self.path.write_bytes(self.original)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with ZipFile(self.path, "a") as bundle:
                        if kind == "duplicate":
                            bundle.writestr(self.member, self.payload)
                        elif kind == "traversal":
                            bundle.writestr("../escape", b"unsafe")
                        else:
                            info = ZipInfo(self.gid + "/link")
                            info.create_system = 3
                            info.external_attr = 0o120777 << 16
                            bundle.writestr(info, b"outside")
                with self.assertRaises(ArchiveError):
                    with VerifiedArchiveReader(self.path):
                        self.fail("malformed archive must fail before entry")


if __name__ == "__main__":
    unittest.main()
