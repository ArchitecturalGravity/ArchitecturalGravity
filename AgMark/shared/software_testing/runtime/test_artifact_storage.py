"""Provider-free runtime artifact storage conformance tests."""

from __future__ import annotations

from pathlib import Path
import os
import stat
import tempfile
import unittest
from unittest import mock

from AgMark.shared.runtime.artifacts import (
    ArtifactCollisionError,
    ArtifactDestinationError,
    ArtifactIntegrityError,
    ArtifactPathError,
    ArtifactPayload,
    FilesystemArtifactStore,
    GenerationReuseError,
    PublicationDestination,
    RETAINABLE_EVIDENCE,
    SecretRetentionError,
    TRANSIENT_INVOCATION,
)


def _store(benchmark_root: Path) -> FilesystemArtifactStore:
    return FilesystemArtifactStore(
        PublicationDestination.benchmark_owned(
            benchmark_root / "evidence",
            benchmark_root=benchmark_root,
        )
    )


def _payload(
    artifact_id: str,
    relative_path: str,
    *,
    retention_class: str | None = RETAINABLE_EVIDENCE,
) -> ArtifactPayload:
    return ArtifactPayload(
        artifact_id=artifact_id,
        role="runtime_evidence",
        relative_path=relative_path,
        data=f"bytes:{artifact_id}".encode("utf-8"),
        provenance="runtime-artifact-storage-test",
        retention_class=retention_class,
        media_type="application/octet-stream",
    )


class RuntimeArtifactStorageConformanceTests(unittest.TestCase):
    def test_destination_authority_rejects_unauthorized_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository_root = Path(directory).resolve() / "repo"
            benchmark_root = repository_root / "AgMark" / "benchmarks" / "sample"
            shared_root = repository_root / "AgMark" / "shared"
            benchmark_root.mkdir(parents=True)
            shared_root.mkdir(parents=True)

            with self.assertRaises(ArtifactDestinationError):
                PublicationDestination.benchmark_owned(
                    repository_root / "outside-benchmark",
                    benchmark_root=benchmark_root,
                )

            benchmarking_root = repository_root / "AgMark"
            with self.assertRaises(ArtifactDestinationError):
                PublicationDestination.benchmark_owned(
                    shared_root / "evidence",
                    benchmark_root=benchmarking_root,
                    forbidden_roots=(shared_root,),
                )

            with self.assertRaises(ArtifactDestinationError):
                PublicationDestination.external(
                    repository_root / "external-inside-repository",
                    repository_root=repository_root,
                )

    def test_transient_and_unclassified_material_cannot_be_retained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())

            with self.assertRaises(SecretRetentionError):
                store.publish_generation(
                    "generation-transient",
                    (
                        _payload(
                            "transient-secret",
                            "diagnostics/transient.bin",
                            retention_class=TRANSIENT_INVOCATION,
                        ),
                    ),
                )

            with self.assertRaises(SecretRetentionError):
                store.publish_generation(
                    "generation-unclassified",
                    (
                        _payload(
                            "unclassified",
                            "diagnostics/unclassified.bin",
                            retention_class=None,
                        ),
                    ),
                )

    def test_traversal_is_rejected_before_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())

            with self.assertRaises(ArtifactPathError):
                store.publish_generation(
                    "generation-traversal",
                    (_payload("escape", "../escape.bin"),),
                )

            self.assertFalse((store.root.parent / "escape.bin").exists())

    def test_generation_id_rejects_nonportable_path_segments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())

            for generation_id in (
                "generation:windows",
                "generation?windows",
                "generation*windows",
                "generation.",
                "generation ",
                "generation\x1fcontrol",
            ):
                with self.subTest(generation_id=generation_id):
                    with self.assertRaises(ArtifactPathError):
                        store.publish_generation(
                            generation_id,
                            (_payload("portable-segment", "artifact.bin"),),
                        )

    def test_artifact_writes_request_binary_mode_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())
            real_open = os.open
            binary_flag = 1 << 29
            opened: list[tuple[int, int]] = []

            def recording_open(path, flags, mode=0o777, *, dir_fd=None):
                opened.append((flags, mode))
                kwargs = {} if dir_fd is None else {"dir_fd": dir_fd}
                return real_open(path, flags & ~binary_flag, mode, **kwargs)

            with (
                mock.patch.object(os, "O_BINARY", binary_flag, create=True),
                mock.patch(
                    "AgMark.shared.runtime.artifacts.storage.os.open",
                    side_effect=recording_open,
                ),
            ):
                store.publish_generation(
                    "generation-binary-mode",
                    (
                        ArtifactPayload(
                            artifact_id="binary-mode",
                            role="runtime_evidence",
                            relative_path="artifact.bin",
                            data=b"line-one\nline-two\n",
                            provenance="runtime-artifact-storage-test",
                            retention_class=RETAINABLE_EVIDENCE,
                            media_type="application/octet-stream",
                        ),
                    ),
                )

            self.assertTrue(
                any(mode == 0o600 and flags & binary_flag for flags, mode in opened)
            )

    def test_symlink_escape_is_rejected_during_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            (record,) = store.publish_generation(
                "generation-symlink",
                (_payload("retained", "evidence/retained.bin"),),
            )
            retained_path = store.root / record.reference
            retained_path.parent.chmod(0o755)
            retained_path.unlink()
            outside = benchmark_root / "outside.bin"
            outside.write_bytes(b"outside-authority")
            try:
                retained_path.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            with self.assertRaises(ArtifactPathError):
                store.revalidate(record)

    def test_duplicate_identity_and_output_path_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())

            with self.assertRaises(ArtifactCollisionError):
                store.publish_generation(
                    "generation-duplicate-id",
                    (
                        _payload("duplicate", "one.bin"),
                        _payload("duplicate", "two.bin"),
                    ),
                )

            with self.assertRaises(ArtifactCollisionError):
                store.publish_generation(
                    "generation-output-collision",
                    (
                        _payload("first", "same.bin"),
                        _payload("second", "same.bin"),
                    ),
                )

    def test_whole_generation_deletion_removes_evidence_and_blocks_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())
            generation_id = "generation-delete"
            (record,) = store.publish_generation(
                generation_id,
                (_payload("deleted-artifact", "result.bin"),),
            )
            store.claim_terminal_status(generation_id, "accepted")

            self.assertTrue((store.root / generation_id).is_dir())
            self.assertTrue(
                (store.root / f".{generation_id}.generation-claim").is_file()
            )
            self.assertTrue((store.root / f".{generation_id}.terminal").is_file())

            store.delete_generation(generation_id)

            self.assertFalse((store.root / generation_id).exists())
            self.assertFalse(
                (store.root / f".{generation_id}.generation-claim").exists()
            )
            self.assertFalse((store.root / f".{generation_id}.terminal").exists())
            self.assertTrue((store.root / f".{generation_id}.deleted").is_file())
            with self.assertRaises(ArtifactIntegrityError):
                store.read_verified(record)
            with self.assertRaises(GenerationReuseError):
                store.publish_generation(
                    generation_id,
                    (_payload("replacement", "replacement.bin"),),
                )

    def test_whole_generation_deletion_handles_windows_read_only_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())
            generation_id = "generation-delete-read-only-markers"
            store.publish_generation(
                generation_id,
                (_payload("deleted-artifact", "result.bin"),),
            )
            store.claim_terminal_status(generation_id, "accepted")

            real_unlink = Path.unlink

            def windows_read_only_unlink(
                path: Path,
                missing_ok: bool = False,
            ) -> None:
                if (
                    path.name.endswith((".generation-claim", ".terminal"))
                    and path.exists()
                    and not (path.stat().st_mode & stat.S_IWUSR)
                ):
                    raise PermissionError(
                        "simulated Windows refusal to delete a read-only marker"
                    )
                real_unlink(path, missing_ok=missing_ok)

            with mock.patch.object(
                Path,
                "unlink",
                autospec=True,
                side_effect=windows_read_only_unlink,
            ):
                store.delete_generation(generation_id)

            self.assertFalse((store.root / generation_id).exists())
            self.assertFalse(
                (store.root / f".{generation_id}.generation-claim").exists()
            )
            self.assertFalse((store.root / f".{generation_id}.terminal").exists())
            self.assertTrue((store.root / f".{generation_id}.deleted").is_file())

    def test_deleting_generation_without_retained_files_still_retires_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())
            generation_id = "generation-no-files"

            store.delete_generation(generation_id)

            self.assertTrue((store.root / f".{generation_id}.deleted").is_file())
            with self.assertRaises(GenerationReuseError):
                store.publish_generation(
                    generation_id,
                    (_payload("replacement", "replacement.bin"),),
                )

    def test_generation_storage_is_write_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = _store(Path(directory).resolve())
            store.publish_generation(
                "generation-reuse",
                (_payload("first", "first.bin"),),
            )

            with self.assertRaises(GenerationReuseError):
                store.publish_generation(
                    "generation-reuse",
                    (_payload("second", "second.bin"),),
                )


if __name__ == "__main__":
    unittest.main()
