"""Completion diagnostics survive failed publication without retaining payloads."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.runtime.completion_diagnostics import (
    completion_diagnostic, persist_completion_diagnostics,
    retained_completion_diagnostics, sanitize_completion_diagnostics,
)


class CompletionDiagnosticsTests(unittest.TestCase):
    def test_atomic_failure_preserves_last_diagnostic_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [completion_diagnostic("report_build", "failed", ValueError("secret /private/path"))]
            persist_completion_diagnostics(directory, "generation-test", rows)
            with patch("AgMark.shared.runtime.completion_diagnostics.os.replace", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    persist_completion_diagnostics(directory, "generation-test", [])
            self.assertEqual(rows, retained_completion_diagnostics(directory, "generation-test"))
            files = list((Path(directory) / ".agmark-completion").iterdir())
            self.assertEqual(["generation-test.json"], [file.name for file in files])
            self.assertNotIn("secret", files[0].read_text())
            self.assertNotIn("/private", files[0].read_text())

    def test_closed_payload_sanitizer_and_cross_generation_rejection(self):
        unknown = type("secretToken", (Exception,), {})
        row = completion_diagnostic("publication", "failed", unknown("credential"))
        self.assertEqual("Exception", row["error_class"])
        self.assertEqual([], sanitize_completion_diagnostics([{**row, "stage": "/private/path"}]))
        self.assertEqual([], sanitize_completion_diagnostics([{**row, "extra": "credential"}]))
        self.assertEqual("Exception", sanitize_completion_diagnostics([{**row, "error_class": {"secret": 1}}])[0]["error_class"])
        with tempfile.TemporaryDirectory() as directory:
            persist_completion_diagnostics(directory, "generation-test", [row])
            path = Path(directory) / ".agmark-completion/generation-test.json"
            document = json.loads(path.read_text())
            document["generation_id"] = "generation-other"
            path.write_text(json.dumps(document))
            self.assertEqual([], retained_completion_diagnostics(directory, "generation-test"))

    def test_symlink_and_traversal_are_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            (root / ".agmark-completion").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                persist_completion_diagnostics(root, "generation-test", [])
            with self.assertRaises(ValueError):
                persist_completion_diagnostics(root, "../../private", [])
            self.assertEqual([], list(outside.iterdir()))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fifo_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / ".agmark-completion"
            parent.mkdir()
            os.mkfifo(parent / "generation-test.json")
            self.assertEqual([], retained_completion_diagnostics(directory, "generation-test"))

    def test_failed_generation_can_be_discovered_without_archive(self):
        from AgMark.shared.runtime.completion_diagnostics import list_retained_completion_diagnostics
        with tempfile.TemporaryDirectory() as directory:
            rows = [completion_diagnostic("publication", "failed", PermissionError("private"))]
            persist_completion_diagnostics(directory, "generation-test", rows)
            self.assertEqual({"generation-test": rows}, list_retained_completion_diagnostics(directory))
            self.assertFalse((Path(directory) / "generation-test.agmark").exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fifo_substituted_during_open_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            persist_completion_diagnostics(directory, "generation-test", [])
            path = Path(directory) / ".agmark-completion/generation-test.json"
            original_open = os.open
            def substitute(target, flags):
                path.unlink()
                os.mkfifo(path)
                return original_open(target, flags)
            with patch("AgMark.shared.runtime.completion_diagnostics.os.open", side_effect=substitute):
                self.assertEqual([], retained_completion_diagnostics(directory, "generation-test"))
