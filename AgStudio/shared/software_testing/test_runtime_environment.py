"""Runtime layout/migration tests, plus real cmd.exe launcher tests on Windows."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

STUDIO = Path(__file__).resolve().parents[2]
SCRATCH = STUDIO / "Runtime" / ".tmp"
# Load the standalone helper without importing AgStudio's language/GUI packages.
_SPEC = importlib.util.spec_from_file_location(
    "agstudio_runtime_cleanup", STUDIO / "shared/runtime_cleanup.py")
_RUNTIME_CLEANUP = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RUNTIME_CLEANUP)
cleanup_legacy_runtime = _RUNTIME_CLEANUP.cleanup_legacy_runtime


class RuntimeTestCase(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.sandbox = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(self.sandbox.cleanup)
        self.root = Path(self.sandbox.name)
        self.studio = self.root / "checkout with spaces" / "AgStudio"
        self.studio.mkdir(parents=True)

    def put(self, relative, content="generated"):
        path = self.studio / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class RuntimeCleanupTests(RuntimeTestCase):
    def test_removes_legacy_environment_and_nested_source_caches(self):
        self.put(".venv/pyvenv.cfg", "home = old-python\n")
        self.put(".venv/Lib/site-packages/old.pyc")
        self.put("__pycache__/old.pyc")
        self.put("gui/nested/__pycache__/old.pyc")
        source = self.put("gui/nested/source.py", "pass\n")
        document = self.put("examples/user-document.txt", "keep me")
        runtime = self.put("Runtime/.venv/pyvenv.cfg", "keep me")
        cache = self.put("Runtime/__pycache__/cached.pyc", "keep me")
        cleanup_legacy_runtime(self.studio)
        self.assertFalse((self.studio / ".venv").exists())
        self.assertFalse((self.studio / "__pycache__").exists())
        self.assertFalse((source.parent / "__pycache__").exists())
        for kept in (source, document, runtime, cache):
            self.assertTrue(kept.is_file(), kept)
        cleanup_legacy_runtime(self.studio)  # Safe to rerun.

    def test_refuses_unrecognized_legacy_directory(self):
        keep = self.put(".venv/user-file.txt", "keep me")
        with self.assertRaisesRegex(OSError, "unrecognized"):
            cleanup_legacy_runtime(self.studio)
        self.assertEqual(keep.read_text(), "keep me")

    def test_preserves_hidden_development_folders(self):
        keep = self.put(".other-env/__pycache__/keep.pyc")
        cleanup_legacy_runtime(self.studio)
        self.assertTrue(keep.exists())

    def symlink(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Directory symlinks unavailable: {exc}")

    def test_does_not_follow_linked_source_directories(self):
        outside = self.root / "outside"
        outside.mkdir()
        cache = outside / "__pycache__"
        cache.mkdir()
        self.symlink(self.studio / "linked-source", outside)
        cleanup_legacy_runtime(self.studio)
        self.assertTrue(cache.is_dir())

    def test_refuses_linked_legacy_environment(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "pyvenv.cfg").write_text("keep me")
        self.symlink(self.studio / ".venv", outside)
        with self.assertRaisesRegex(OSError, "unrecognized"):
            cleanup_legacy_runtime(self.studio)
        self.assertTrue((outside / "pyvenv.cfg").exists())

    def test_refuses_linked_cache_directory(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.symlink(self.studio / "__pycache__", outside)
        with self.assertRaisesRegex(OSError, "linked cache"):
            cleanup_legacy_runtime(self.studio)
        self.assertTrue(outside.is_dir())

    def test_manual_cleanup_requires_replacement_interpreter(self):
        with mock.patch.object(_RUNTIME_CLEANUP.sys, "prefix", str(self.root)), \
                mock.patch.object(_RUNTIME_CLEANUP.sys, "stderr"), \
                mock.patch.object(_RUNTIME_CLEANUP, "cleanup_legacy_runtime") as cleanup:
            self.assertEqual(_RUNTIME_CLEANUP.main(), 1)
            cleanup.assert_not_called()

    def test_cleanup_errors_are_not_silently_ignored(self):
        self.put("__pycache__/old.pyc")
        with mock.patch.object(_RUNTIME_CLEANUP.shutil, "rmtree",
                               side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                cleanup_legacy_runtime(self.studio)


class RuntimeContractTests(RuntimeTestCase):
    def test_root_has_only_named_windows_batch_entrypoints(self):
        self.assertEqual(
            {"Windows_Run.bat", "Windows_Setup.bat"},
            {path.name for path in STUDIO.glob("*.bat")},
        )

    def test_both_entrypoints_configure_runtime_before_python(self):
        for name in ("Windows_Setup.bat", "Windows_Run.bat"):
            text = (STUDIO / name).read_text()
            self.assertIn("setlocal EnableExtensions DisableDelayedExpansion", text)
            call = text.index('call "%STUDIO_DIR%shared\\runtime_environment.bat"')
            self.assertLess(call, text.index('"%VENV_PYTHON%"'))
            self.assertNotIn('set "VENV_PYTHON=%STUDIO_DIR%.venv', text)
        setup = (STUDIO / "Windows_Setup.bat").read_text()
        self.assertIn('-m venv "%VENV_DIR%"', setup)
        self.assertLess(setup.index("PySide6 could not be loaded"),
                        setup.index('"%STUDIO_DIR%shared\\runtime_cleanup.py"'))
        run = (STUDIO / "Windows_Run.bat").read_text()
        self.assertIn("--arcgrav-version current %*", run)
        self.assertIn("exit /b %ERRORLEVEL%", run)

    def test_runtime_paths_are_centralized_and_git_ignored(self):
        text = (STUDIO / "shared/runtime_environment.bat").read_text()
        expected = {
            "RUNTIME_DIR": r"%STUDIO_DIR%Runtime",
            "VENV_DIR": r"%RUNTIME_DIR%\.venv",
            "VENV_PYTHON": r"%VENV_DIR%\Scripts\python.exe",
            "PYTHONPYCACHEPREFIX": r"%RUNTIME_DIR%\__pycache__",
            "PIP_CACHE_DIR": r"%RUNTIME_DIR%\.cache\pip",
            "TEMP": r"%RUNTIME_DIR%\.tmp",
            "TMP": "%TEMP%",
            "TMPDIR": "%TEMP%",
        }
        for name, value in expected.items():
            self.assertIn(f'set "{name}={value}"', text)
        self.assertIn("/Runtime/", (STUDIO / ".gitignore").read_text().splitlines())

    def test_python_and_children_redirect_bytecode_and_temp(self):
        self.put("gui/runtime_probe.py", "VALUE = 42\n")
        runtime = self.studio / "Runtime"
        temp = runtime / ".tmp"
        temp.mkdir(parents=True)
        prefix = runtime / "__pycache__"
        env = dict(os.environ, PYTHONPATH=str(self.studio / "gui"),
                   PYTHONPYCACHEPREFIX=str(prefix), TEMP=str(temp), TMP=str(temp),
                   TMPDIR=str(temp), PIP_CACHE_DIR=str(runtime / ".cache" / "pip"))
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        code = (
            "import json, sys, tempfile, subprocess, runtime_probe; "
            "child = subprocess.check_output([sys.executable, '-c', "
            "'import sys; print(sys.pycache_prefix)'], text=True).strip(); "
            "print(json.dumps([runtime_probe.__cached__, tempfile.gettempdir(), child]))"
        )
        result = subprocess.run([sys.executable, "-c", code], env=env,
                                capture_output=True, text=True, check=True, timeout=30)
        cached, temporary, child = json.loads(result.stdout)
        self.assertTrue(Path(cached).is_file())
        self.assertTrue(Path(cached).is_relative_to(prefix))
        self.assertEqual(Path(temporary), temp)
        self.assertEqual(Path(child), prefix)
        self.assertFalse((self.studio / "gui/__pycache__").exists())


@unittest.skipUnless(os.name == "nt", "Requires Windows cmd.exe")
class WindowsRuntimeTests(RuntimeTestCase):
    def setUp(self):
        super().setUp()
        for relative in ("Windows_Setup.bat", "Windows_Run.bat", "shared/runtime_environment.bat",
                         "shared/runtime_cleanup.py"):
            self.put(relative, (STUDIO / relative).read_text())
        # Exercise real Python/venv/pip without downloading Qt or opening a GUI.
        self.put("gui/requirements.txt", "# No network dependencies for this fixture.\n")
        self.put("__init__.py", "")
        self.put("gui/__init__.py", "")
        self.put("gui/__main__.py", """import json, os, sys, tempfile
print(json.dumps({'prefix': sys.prefix, 'pycache': sys.pycache_prefix,
                  'temp': tempfile.gettempdir(), 'pip_cache': os.environ['PIP_CACHE_DIR'],
                  'args': sys.argv[1:], 'cwd': os.getcwd()}))
sys.exit(7 if '--fail' in sys.argv else 0)
""")
        dependencies = self.root / "dependencies"
        (dependencies / "PySide6").mkdir(parents=True)
        (dependencies / "PySide6/__init__.py").write_text("__version__ = 'test-fixture'\n")
        (dependencies / "PySide6/QtWidgets.py").write_text("class QApplication: pass\n")
        self.put("arcgrav_language_engine/__init__.py", "")
        self.put("arcgrav_language_engine/lint/__init__.py", "")
        self.put("arcgrav_language_engine/lint/spelling.py", "def _get_checker(): return object()\n")
        self.env = dict(os.environ, PYTHONPATH=str(dependencies), PIP_NO_INDEX="1",
                        PIP_CONFIG_FILE=os.devnull)
        self.env.pop("PYTHONDONTWRITEBYTECODE", None)
        self.cwd = self.root / "unrelated working directory"
        self.cwd.mkdir()

    def batch(self, name, *args):
        command = (f'"{os.environ.get("COMSPEC", "cmd.exe")}" /d /s /c '
                   f'""{self.studio / name}" {subprocess.list2cmdline(args)}"')
        return subprocess.run(command, cwd=self.cwd, env=self.env,
                              capture_output=True, text=True, timeout=120)

    def test_setup_reuse_migration_launch_arguments_and_exit_code(self):
        self.put(".venv/pyvenv.cfg", "home = obsolete\n")
        self.put("gui/__pycache__/old.pyc")
        result = self.batch("Windows_Setup.bat")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        runtime = self.studio / "Runtime"
        config = runtime / ".venv/pyvenv.cfg"
        self.assertTrue(config.is_file())
        original_config = config.stat().st_mtime_ns
        self.assertFalse((self.studio / ".venv").exists())
        result = self.batch("Windows_Setup.bat")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(config.stat().st_mtime_ns, original_config)
        result = self.batch("Windows_Run.bat", "file with spaces.txt")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        actual = json.loads(result.stdout)
        self.assertEqual(Path(actual["prefix"]), runtime / ".venv")
        self.assertEqual(Path(actual["pycache"]), runtime / "__pycache__")
        self.assertEqual(Path(actual["temp"]), runtime / ".tmp")
        self.assertEqual(Path(actual["pip_cache"]), runtime / ".cache/pip")
        self.assertEqual(actual["args"], ["--arcgrav-version", "current", "file with spaces.txt"])
        self.assertEqual(Path(actual["cwd"]), self.cwd)
        self.assertEqual(self.batch("Windows_Run.bat", "--fail").returncode, 7)
        self.assertTrue(all(path.is_relative_to(runtime)
                            for path in self.studio.rglob("__pycache__")))

    def test_install_failure_preserves_legacy_environment_and_caches(self):
        legacy = self.put(".venv/pyvenv.cfg", "keep me")
        cache = self.put("gui/__pycache__/old.pyc")
        self.put("gui/requirements.txt", "missing-runtime-test-package==0.0.0\n")
        result = self.batch("Windows_Setup.bat")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Dependency installation failed", result.stdout)
        self.assertTrue(legacy.is_file())
        self.assertTrue(cache.is_file())

    def test_missing_requirements_does_not_create_runtime(self):
        (self.studio / "gui/requirements.txt").unlink()
        result = self.batch("Windows_Setup.bat")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Missing dependency file", result.stdout)
        self.assertFalse((self.studio / "Runtime").exists())

    def test_run_requires_new_environment(self):
        self.put(".venv/pyvenv.cfg", "legacy is not used")
        result = self.batch("Windows_Run.bat")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Runtime\\.venv is missing", result.stdout)

    def test_runtime_directory_creation_failure_is_reported(self):
        self.put("Runtime", "not a directory")
        result = self.batch("Windows_Setup.bat")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not create runtime directory", result.stdout)

    def test_launcher_environment_does_not_leak_to_caller(self):
        self.env["PYTHONPYCACHEPREFIX"] = "caller-cache"
        self.put("check-local.bat", '@echo off\ncall "%~dp0Windows_Run.bat"\n'
                 'echo CACHE_AFTER=%PYTHONPYCACHEPREFIX%\nexit /b 0\n')
        result = self.batch("check-local.bat")
        self.assertEqual(result.returncode, 0)
        self.assertIn("CACHE_AFTER=caller-cache", result.stdout)


if __name__ == "__main__":
    unittest.main()
