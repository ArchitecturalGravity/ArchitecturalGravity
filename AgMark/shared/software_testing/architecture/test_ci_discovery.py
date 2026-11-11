"""Central collection excludes disposable environments and loads owned tests."""

from pathlib import Path
import tempfile
import unittest

from AgMark.shared.software_testing.ci import _python_files, build_suite


class CentralDiscoveryTests(unittest.TestCase):
    def test_environment_templates_cannot_block_owned_test_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for environment in (".venv", ".linux-pyside6", "custom-runtime"):
                folder = root / environment
                folder.mkdir()
                (folder / "pyvenv.cfg").write_text("home = test\n")
                (folder / "test_vendor_template.py").write_text("{{ invalid template }}")
            (root / "test_owned.py").write_text(
                "import unittest\nclass Owned(unittest.TestCase):\n"
                "    def test_owned(self): self.assertTrue(True)\n"
            )
            self.assertEqual((root / "test_owned.py",), _python_files(root))
            suite, errors = build_suite(root)
            self.assertEqual((), errors)
            self.assertEqual(1, suite.countTestCases())

    def test_imported_cases_are_collected_only_in_their_own_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # A foreign class can be created without a filesystem import so this
            # regression remains independent of sys.path and import caching.
            (root / "test_owner.py").write_text(
                "import unittest\n"
                "class Owned(unittest.TestCase):\n"
                "    def test_owned(self): pass\n"
                "Alias = Owned\n"
                "Foreign = type('Foreign', (unittest.TestCase,), "
                "{'__module__': 'some_other_test', 'test_foreign': lambda self: None})\n"
            )
            suite, errors = build_suite(root)
            self.assertEqual((), errors)
            self.assertEqual(1, suite.countTestCases())
