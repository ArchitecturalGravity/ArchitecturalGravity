"""Disposable runtime rebuilds and strict startup, without provider/package downloads."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
from unittest.mock import patch

from AgMark.gui import runtime_environment as policy
from AgMark.gui.setup_environment import fresh_setup


_GUI_ROOT = Path(policy.__file__).absolute().parent


def _site_packages(target):
    return target / ("Lib/site-packages" if os.name == "nt" else
                     f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")


def _clean_environment():
    environment = dict(os.environ)
    for key in ("PYTHONPYCACHEPREFIX", "PYTHONPATH", "PYTHONHOME", "PYTHONDONTWRITEBYTECODE"):
        environment.pop(key, None)
    return environment


class FreshSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="agmark setup spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "AgMark"
        (self.root / "gui").mkdir(parents=True)
        (self.root / "gui/requirements.txt").write_text("PySide6==6.11.2")
        shutil.copyfile(_GUI_ROOT / "runtime_environment.py", self.root / "gui/runtime_environment.py")
        self.calls = []

    def command(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[1:4] == ["-m", "venv", "--without-pip"]:
            target = Path(command[4])
            _site_packages(target).mkdir(parents=True)
            (target / "fresh").write_text("new")

    def test_repeat_rebuilds_only_the_managed_environment(self):
        for name in ("runs", "evidence", "config", ".env"):
            (self.root / name).write_text(name)
        target = fresh_setup(self.root, self.command)
        self.assertEqual(self.root / "Runtime/.venv", target)
        (target / "extra").write_text("old installed package")
        fresh_setup(self.root, self.command)
        self.assertFalse((target / "extra").exists())
        self.assertEqual(8, len(self.calls))
        self.assertIn("--no-cache-dir", self.calls[2][0])
        self.assertFalse((self.root / "Runtime/.setup-lock").exists())
        for name in ("runs", "evidence", "config", ".env"):
            self.assertEqual(name, (self.root / name).read_text())

    def test_hook_is_installed_before_ensurepip_and_package_install(self):
        def command(args, **kwargs):
            self.command(args, **kwargs)
            if args[1:3] in (["-m", "ensurepip"], ["-m", "pip"]):
                self.assertTrue((_site_packages(self.root / "Runtime/.venv") / "00_agmark_runtime.pth").is_file())
        fresh_setup(self.root, command)
        self.assertEqual(["-m", "venv", "--without-pip"], self.calls[0][0][1:4])
        self.assertEqual(["-m", "ensurepip"], self.calls[1][0][1:3])
        self.assertEqual(["-m", "pip"], self.calls[2][0][1:3])

    def test_every_setup_subprocess_uses_runtime_cache_and_temp(self):
        with patch.dict(os.environ, {"SAMPLE_PROVIDER_TOKEN": "untouched"}):
            before = dict(os.environ)
            fresh_setup(self.root, self.command)
            self.assertEqual(before, dict(os.environ))
        for _command, kwargs in self.calls:
            environment = kwargs["env"]
            self.assertTrue(kwargs["check"])
            self.assertEqual("untouched", environment["SAMPLE_PROVIDER_TOKEN"])
            self.assertEqual(str(self.root / "Runtime/__pycache__"), environment["PYTHONPYCACHEPREFIX"])
            for key in ("TMP", "TEMP", "TMPDIR"):
                self.assertEqual(str(self.root / "Runtime/temp"), environment[key])
            self.assertEqual(str(self.root / "Runtime/pip-cache"), environment["PIP_CACHE_DIR"])

    def test_failure_at_each_stage_removes_partial_environment(self):
        for stage in range(4):
            with self.subTest(stage=stage):
                target = self.root / "Runtime/.venv"
                target.mkdir(parents=True, exist_ok=True)
                (target / "original").write_text("discarded")
                count = 0
                def failing(command, **kwargs):
                    nonlocal count
                    self.command(command, **kwargs)
                    current = count
                    count += 1
                    if current == stage:
                        raise subprocess.CalledProcessError(1, command)
                with self.assertRaises(subprocess.CalledProcessError):
                    fresh_setup(self.root, failing)
                self.assertFalse(target.exists())
                self.assertFalse((self.root / "Runtime/.setup-lock").exists())

    def test_hook_failure_removes_partial_environment(self):
        with patch("AgMark.gui.setup_environment.install_runtime_hook", side_effect=OSError("cannot write hook")):
            with self.assertRaises(OSError):
                fresh_setup(self.root, self.command)
        self.assertFalse((self.root / "Runtime/.venv").exists())
        self.assertFalse((self.root / "Runtime/.setup-lock").exists())

    def test_runtime_links_are_rejected_before_commands_or_deletion(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "keep").write_text("preserved")
        path = self.root / "Runtime"
        try:
            path.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Directory symlinks unavailable: {exc}")
        with self.assertRaises(RuntimeError):
            fresh_setup(self.root, self.command)
        self.assertEqual("preserved", (outside / "keep").read_text())
        self.assertEqual([], self.calls)
        path.unlink()

    def test_runtime_child_link_is_rejected(self):
        (self.root / "Runtime").mkdir()
        outside = self.root.parent / "outside"
        outside.mkdir()
        for name in (".venv", "__pycache__", "temp", "pip-cache", ".setup-lock"):
            path = self.root / "Runtime" / name
            try:
                path.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Directory symlinks unavailable: {exc}")
            try:
                with self.assertRaises(RuntimeError):
                    fresh_setup(self.root, self.command)
            finally:
                path.unlink()
            for prepared in ("__pycache__", "temp", "pip-cache"):
                candidate = self.root / "Runtime" / prepared
                if candidate.exists():
                    candidate.rmdir()
        self.assertEqual([], self.calls)

    def test_concurrent_setup_cannot_displace_current_environment(self):
        target = self.root / "Runtime/.venv"
        target.mkdir(parents=True)
        (target / "original").write_text("preserved")
        (self.root / "Runtime/.setup-lock").mkdir()
        with self.assertRaises(FileExistsError):
            fresh_setup(self.root, self.command)
        self.assertEqual("preserved", (target / "original").read_text())
        self.assertEqual([], self.calls)

    def test_main_resolves_script_location_independent_of_cwd(self):
        from AgMark.gui import setup_environment
        with patch.object(setup_environment, "__file__", str(self.root / "gui/setup_environment.py")), patch.object(setup_environment, "fresh_setup") as setup:
            self.assertEqual(0, setup_environment.main())
            setup.assert_called_once_with(self.root)

    def test_deletion_failure_reports_failure_without_starting_install(self):
        target = self.root / "Runtime/.venv"
        target.mkdir(parents=True)
        (target / "original").write_text("preserved")
        with patch("AgMark.gui.setup_environment.shutil.rmtree", side_effect=PermissionError("in use")):
            with self.assertRaises(PermissionError):
                fresh_setup(self.root, self.command)
        self.assertEqual("preserved", (target / "original").read_text())
        self.assertFalse((self.root / "Runtime/.setup-lock").exists())
        self.assertEqual([], self.calls)

    def test_path_escape_and_missing_requirements_do_not_modify_environment(self):
        with self.assertRaises(RuntimeError):
            fresh_setup(self.root / "gui/..", self.command)
        (self.root / "gui/requirements.txt").unlink()
        with self.assertRaises(RuntimeError):
            fresh_setup(self.root, self.command)
        self.assertEqual([], self.calls)

    def test_unwritable_runtime_aborts_before_deleting_environment(self):
        target = self.root / "Runtime/.venv"
        target.mkdir(parents=True)
        (target / "keep").write_text("preserved")
        with patch.object(policy, "_writable_directory", side_effect=PermissionError("read only")):
            with self.assertRaises(PermissionError):
                fresh_setup(self.root, self.command)
        self.assertEqual("preserved", (target / "keep").read_text())
        self.assertEqual([], self.calls)


class RuntimeProcessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="agmark runtime spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "checkout \u03b1" / "AgMark"
        (self.root / "gui").mkdir(parents=True)
        for name in ("runtime_environment.py", "__main__.py"):
            shutil.copyfile(_GUI_ROOT / name, self.root / "gui" / name)
        self.environment = policy.runtime_environment(self.root, create=True)
        self.target = self.root / "Runtime/.venv"
        venv.EnvBuilder(with_pip=False).create(self.target)
        policy.install_runtime_hook(self.target, self.environment)
        self.python = self.target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.hook = _site_packages(self.target) / "00_agmark_runtime.pth"
        self.clean = _clean_environment()

    def run_python(self, script, *, flags=(), check=True):
        return subprocess.run([str(self.python), *flags, "-c", script], cwd=self.root.parent,
                              env=self.clean, check=check, capture_output=True, text=True)

    def test_direct_venv_and_child_process_keep_bytecode_and_temp_under_runtime(self):
        (self.root / "runtime_probe.py").write_text("value = 42\n")
        script = (
            "import json, sys, tempfile, subprocess; from AgMark import runtime_probe; "
            "child = subprocess.check_output([sys.executable, '-c', "
            "'import json, sys, tempfile; print(json.dumps([sys.pycache_prefix, tempfile.gettempdir()]))'], text=True); "
            "print(json.dumps([runtime_probe.__cached__, tempfile.gettempdir(), child]))"
        )
        cached, temporary, child = json.loads(self.run_python(script).stdout)
        self.assertTrue(Path(cached).is_relative_to(self.root / "Runtime/__pycache__"))
        self.assertTrue(Path(cached).is_file())
        self.assertEqual(str(self.root / "Runtime/temp"), temporary)
        self.assertEqual([str(self.root / "Runtime/__pycache__"), temporary], json.loads(child))
        self.assertFalse(any(p for p in self.root.rglob("__pycache__")
                             if "Runtime" not in p.relative_to(self.root).parts))

    def test_missing_temp_at_startup_is_fatal_not_recreated(self):
        (self.root / "Runtime/temp").rmdir()
        result = self.run_python("print('APPLICATION-RAN')", check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("APPLICATION-RAN", result.stdout)
        self.assertIn("AgMark Runtime initialization failed", result.stderr)
        self.assertFalse((self.root / "Runtime/temp").exists())

    def test_broken_policy_is_fatal_instead_of_swallowed_by_site(self):
        (self.root / "gui/runtime_environment.py").write_text("raise RuntimeError('broken-policy')\n")
        result = self.run_python("print('APPLICATION-RAN')", check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("APPLICATION-RAN", result.stdout)
        self.assertIn("broken-policy", result.stderr)

    def test_missing_hook_is_rejected_before_desktop_import(self):
        self.hook.unlink()
        result = self.run_python("from AgMark.gui.__main__ import launch; raise SystemExit(launch())", flags=("-B",), check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("hook is missing or outdated", result.stderr)
        self.assertNotIn("No module named 'AgMark.gui.startup'", result.stderr)

    def test_old_hook_marker_is_rejected(self):
        result = self.run_python("import sys; sys._agmark_runtime_policy = (1, 'old'); from AgMark.gui.__main__ import launch; raise SystemExit(launch())", check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("hook is missing or outdated", result.stderr)

    def test_altered_cache_and_temp_settings_are_rejected(self):
        for mutation in ("sys.pycache_prefix = None", "tempfile.tempdir = '/tmp'", "os.environ['TMPDIR'] = '/tmp'"):
            with self.subTest(mutation=mutation):
                script = f"import sys, tempfile, os; {mutation}; from AgMark.gui.__main__ import launch; raise SystemExit(launch())"
                result = self.run_python(script, flags=("-B",), check=False)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("settings were changed", result.stderr)

    def test_system_python_and_no_site_cannot_launch_gui(self):
        for python, flags in ((sys.executable, ("-B",)), (str(self.python), ("-B", "-S"))):
            with self.subTest(python=python, flags=flags):
                result = subprocess.run([python, *flags, "-m", "AgMark.gui"], cwd=self.root.parent,
                                        env=self.clean, check=False, capture_output=True, text=True)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("requires Runtime/.venv", result.stderr)
                self.assertNotIn("No module named 'AgMark.gui.startup'", result.stderr)

    def test_isolated_python_still_uses_the_runtime_hook(self):
        result = self.run_python("import json, sys, tempfile; print(json.dumps([sys.pycache_prefix, tempfile.tempdir]))", flags=("-I",))
        self.assertEqual([str(self.root / "Runtime/__pycache__"), str(self.root / "Runtime/temp")], json.loads(result.stdout))

    def test_real_ensurepip_runs_under_the_strict_hook_without_network(self):
        completed = subprocess.run([str(self.python), "-m", "ensurepip", "--upgrade", "--default-pip"],
                                   cwd=self.root.parent, env=self.clean, check=False,
                                   capture_output=True, text=True)
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.run_python("import pip, tempfile; print(tempfile.gettempdir())")
        self.assertEqual(str(self.root / "Runtime/temp"), result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
