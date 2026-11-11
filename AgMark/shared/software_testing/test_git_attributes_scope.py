"""Regression coverage for the AgMark-local Git attributes policy."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ATTRIBUTES = REPOSITORY_ROOT / "AgMark" / ".gitattributes"


@unittest.skipUnless(shutil.which("git"), "Git is required for attributes tests")
class GitAttributesScopeTests(unittest.TestCase):
    def test_only_agmark_has_lf_and_binary_policies(self):
        self.assertTrue(ATTRIBUTES.is_file())
        self.assertFalse((REPOSITORY_ROOT / ".gitattributes").exists())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            agmark = root / "AgMark"
            agmark.mkdir()
            (agmark / ".gitattributes").write_bytes(ATTRIBUTES.read_bytes())
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root, check=True, capture_output=True,
            )
            paths = (
                "AgMark/.gitattributes",
                "AgMark/src/module.py",
                "AgMark/docs/note.md",
                "AgMark/assets/icon.png",
                "AgMark/cache/module.pyc",
                "AgMark/docs/guide.pdf",
                "AgStudio/src/module.py",
                "CAC/src/module.py",
            )
            process = subprocess.run(
                ["git", "-c", f"core.attributesFile={os.devnull}",
                 "check-attr", "-z", "text", "eol", "--", *paths],
                cwd=root, check=True, capture_output=True,
            )
            fields = process.stdout.decode("utf-8").rstrip("\0").split("\0")
            attributes = {path: {} for path in paths}
            for offset in range(0, len(fields), 3):
                path, name, value = fields[offset:offset + 3]
                attributes[path][name] = value

            for path in ("AgMark/.gitattributes", "AgMark/src/module.py",
                         "AgMark/docs/note.md"):
                self.assertIn(attributes[path]["text"], {"set", "auto"})
                self.assertEqual(attributes[path]["eol"], "lf")
            for path in ("AgMark/assets/icon.png", "AgMark/cache/module.pyc",
                         "AgMark/docs/guide.pdf"):
                self.assertEqual(attributes[path]["text"], "unset")
            for path in ("AgStudio/src/module.py", "CAC/src/module.py"):
                self.assertEqual(attributes[path]["text"], "unspecified")
                self.assertEqual(attributes[path]["eol"], "unspecified")


if __name__ == "__main__":
    unittest.main()
