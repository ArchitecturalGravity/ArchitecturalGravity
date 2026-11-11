"""Verify AgStudio's Python LF attributes do not reach sibling projects."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ATTRIBUTES = REPOSITORY_ROOT / "AgStudio" / ".gitattributes"


@unittest.skipUnless(shutil.which("git"), "Git is required for attributes tests")
class GitAttributesScopeTests(unittest.TestCase):
    def test_python_lf_is_scoped_to_agstudio(self):
        self.assertTrue(ATTRIBUTES.is_file())
        self.assertFalse((REPOSITORY_ROOT / ".gitattributes").exists())
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "AgStudio").mkdir()
            (root / "AgStudio/.gitattributes").write_bytes(ATTRIBUTES.read_bytes())
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root, check=True, capture_output=True,
            )
            paths = (
                "AgStudio/__init__.py",
                "AgStudio/arcgrav_language_engine/lint/rules.py",
                "AgStudio/gui/panel.py",
                "AgStudio/.gitattributes",
                "AgStudio/docs/guide.md",
                "AgStudio/gui/logo.png",
                "AgMark/shared/runner.py",
                "CAC/tool.py",
            )
            process = subprocess.run(
                ["git", "-c", f"core.attributesFile={os.devnull}",
                 "check-attr", "-z", "text", "eol", "--", *paths],
                cwd=root, check=True, capture_output=True,
            )
            fields = process.stdout.decode("utf-8").split("\0")
            self.assertEqual(fields.pop(), "")
            self.assertEqual(len(fields) % 3, 0)
            attributes = {path: {} for path in paths}
            for index in range(0, len(fields), 3):
                path, name, value = fields[index:index + 3]
                attributes[path][name] = value

            for path in paths[:3]:
                self.assertEqual(attributes[path], {"text": "set", "eol": "lf"})
            for path in paths[3:]:
                self.assertEqual(
                    attributes[path],
                    {"text": "unspecified", "eol": "unspecified"},
                )


if __name__ == "__main__":
    unittest.main()
