"""Stage 00 source gateway checks; these are not conformance fixtures."""

import subprocess
import sys
import unittest
from pathlib import Path

from AgStudio.shared import LanguageCore, SourceSession


class CoreBoundaryTests(unittest.TestCase):
    def test_preserves_exact_text_and_does_not_interpret_document(self):
        source = (
            "Header:\r\n```\n=> pretend command\n```\n"
            "*.arc ↳ `target`\n__import__('os').system('exit 12')\n"
        )
        session = LanguageCore.open_source(source, arcgrav_version="unresolved")
        self.assertIsInstance(session, SourceSession)
        self.assertEqual(session.source, source)
        self.assertEqual(session.with_source("new\r\n").source, "new\r\n")
        self.assertEqual(session.source, source)
        self.assertFalse(hasattr(session, "conforms"))
        self.assertFalse(hasattr(session, "execute"))

    def test_context_is_snapshot_and_order_independent(self):
        original = {"nested": {"b": [1, 2]}, "a": True}
        first = LanguageCore.open_source(
            "x", arcgrav_version="v1", profile="p", configuration=original
        )
        second = LanguageCore.open_source(
            "x", arcgrav_version="v1", profile="p",
            configuration={"a": True, "nested": {"b": [1, 2]}},
        )
        self.assertEqual(first, second)
        self.assertEqual(first.configuration_key, second.configuration_key)
        original["nested"]["b"].append(3)
        mutable_copy = first.configuration
        mutable_copy["nested"]["b"].append(4)
        self.assertEqual(first.configuration["nested"]["b"], [1, 2])
        self.assertEqual(first.with_source("y").configuration_key, first.configuration_key)

    def test_requires_explicit_context_and_rejects_mutable_config_objects(self):
        with self.assertRaises(ValueError):
            LanguageCore.open_source("text", arcgrav_version="")
        with self.assertRaises(TypeError):
            LanguageCore.open_source(b"text", arcgrav_version="v1")
        with self.assertRaises(TypeError):
            LanguageCore.open_source("text", arcgrav_version="v1", configuration=[])
        with self.assertRaises(ValueError):
            LanguageCore.open_source("text", arcgrav_version="v1", configuration={"a": object()})

    def test_core_import_does_not_import_qt(self):
        root = Path(__file__).resolve().parents[3]
        check = (
            "import sys; from AgStudio.shared import LanguageCore; "
            "LanguageCore.open_source('x', arcgrav_version='v1'); "
            "assert not any(n.startswith(('PySide', 'PyQt')) "
            "or n.split('.')[0] == 'Qt' for n in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", check], cwd=root,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
