"""Centralized developer/CI test entry point for AgMark software tests.

By default this runs the centralized operation-path test suite. When a Git head (and
optionally a base) is supplied, dependency-aware impact selection narrows test
execution while failing closed to the full suite whenever impact is uncertain.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import unittest


_SOFTWARE_TESTING_ROOT = Path(__file__).resolve().parent
_PACKAGE_PARENT = _SOFTWARE_TESTING_ROOT.parents[2]
_REPOSITORY_ROOT = _PACKAGE_PARENT
_CI_REQUIREMENTS = _SOFTWARE_TESTING_ROOT / "requirements-ci.txt"
_CI_DEPENDENCIES_READY_ENV = "AGMARK_SOFTWARE_TESTING_CI_DEPENDENCIES_READY"

if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

from AgMark.shared.software_testing.select_tests import select_from_git  # noqa: E402


def _selected_tests_require_pyside6(
    selected_tests: tuple[str, ...] | None,
) -> bool:
    if selected_tests is None:
        return True

    return any(
        value.replace("\\", "/").startswith(
            "AgMark/shared/software_testing/frontends/gui/"
        )
        and value.endswith("_qt.py")
        for value in selected_tests
    )


def _ensure_ci_dependencies(
    selected_tests: tuple[str, ...] | None,
) -> bool:
    """Provision test-only GUI dependencies for GitHub Actions when required."""

    if os.environ.get("GITHUB_ACTIONS") != "true":
        return True
    if os.environ.get(_CI_DEPENDENCIES_READY_ENV) == "1":
        return True
    if not _selected_tests_require_pyside6(selected_tests):
        return True
    if not _CI_REQUIREMENTS.is_file():
        print(
            f"CI requirements are unavailable: {_CI_REQUIREMENTS}",
            file=sys.stderr,
        )
        return False

    print("installing CI Qt runtime dependency: libegl1")
    try:
        subprocess.run(
            ["sudo", "apt-get", "update"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "sudo",
                "apt-get",
                "install",
                "--yes",
                "--no-install-recommends",
                "libegl1",
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"CI Qt runtime installation failed: {exc}", file=sys.stderr)
        return False

    print(f"installing CI test dependencies from {_CI_REQUIREMENTS}")
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--requirement",
                str(_CI_REQUIREMENTS),
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"CI dependency installation failed: {exc}", file=sys.stderr)
        return False

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from PySide6.QtCore import Qt; "
                "from PySide6.QtGui import QFont, QFontDatabase; "
                "from PySide6.QtWidgets import QApplication, QWidget"
            ),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if probe.returncode != 0:
        detail = probe.stderr.strip() or probe.stdout.strip() or "unknown import failure"
        print(f"CI Qt dependency probe failed: {detail}", file=sys.stderr)
        return False

    environment = os.environ.copy()
    environment[_CI_DEPENDENCIES_READY_ENV] = "1"
    try:
        os.execve(
            sys.executable,
            [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            environment,
        )
    except OSError as exc:
        print(f"CI dependency process restart failed: {exc}", file=sys.stderr)
        return False
    return False


def _python_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for directory, children, names in os.walk(root):
        children[:] = sorted(
            child for child in children
            if child not in {"__pycache__", ".git", ".venv", "venv", ".linux-pyside6"}
            and not (Path(directory) / child / "pyvenv.cfg").is_file()
        )
        files.extend(Path(directory) / name for name in names if name.endswith(".py"))
    return tuple(sorted(files))


def _test_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in _python_files(root)
        if path.name.startswith("test_")
    )


def _compile_python(root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    for path in _python_files(root):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path.relative_to(root)}: {exc.msg}")
    return tuple(errors)


def _load_test_module(path: Path, root: Path):
    relative = path.relative_to(root).with_suffix("")
    module_name = "_agmark_software_testing_" + "_".join(relative.parts)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _selected_paths(
    root: Path,
    selected_tests: tuple[str, ...] | None,
) -> tuple[Path, ...] | None:
    if selected_tests is None:
        return None

    selected: list[Path] = []
    for value in selected_tests:
        candidate = (_REPOSITORY_ROOT / value).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            print(
                f"selected test is outside software_testing: {value}; "
                "falling back to the full suite",
                file=sys.stderr,
            )
            return None
        if (
            not candidate.is_file()
            or candidate.suffix != ".py"
            or not candidate.name.startswith("test_")
        ):
            print(
                f"selected test is unavailable: {value}; "
                "falling back to the full suite",
                file=sys.stderr,
            )
            return None
        selected.append(candidate)

    return tuple(sorted(set(selected)))


def build_suite(
    root: Path | str = _SOFTWARE_TESTING_ROOT,
    *,
    selected_tests: tuple[str, ...] | None = None,
) -> tuple[unittest.TestSuite, tuple[str, ...]]:
    """Collect each locally defined case once, excluding imported fixtures."""

    test_root = Path(root).resolve()
    requested = _selected_paths(test_root, selected_tests)
    paths = _test_files(test_root) if requested is None else requested

    suite = unittest.TestSuite()
    errors: list[str] = []
    loader = unittest.defaultTestLoader

    for path in paths:
        try:
            module = _load_test_module(path, test_root)
        except Exception as exc:
            errors.append(
                f"{path.relative_to(test_root)}: {type(exc).__name__}: {exc}"
            )
            continue
        # Imported TestCase classes are reusable fixtures, not additional test
        # definitions. Their owning modules are independently discovered.
        seen_classes: set[type] = set()
        for value in vars(module).values():
            if (not isinstance(value, type)
                    or not issubclass(value, unittest.TestCase)
                    or value is unittest.TestCase
                    or value.__module__ != module.__name__
                    or value in seen_classes):
                continue
            seen_classes.add(value)
            suite.addTests(loader.loadTestsFromTestCase(value))

    return suite, tuple(errors)


def _qt_top_level_widgets():
    """Inspect an already-loaded Qt runtime without adding a test dependency."""
    widgets = sys.modules.get("PySide6.QtWidgets")
    if widgets is None or widgets.QApplication.instance() is None:
        return ()
    return tuple(widgets.QApplication.topLevelWidgets())


def _cleanup_test_qt_widgets(existing):
    """Retire this test's windows and detached pages, preserving class fixtures."""
    widgets = sys.modules.get("PySide6.QtWidgets")
    core = sys.modules.get("PySide6.QtCore")
    if widgets is None or core is None or widgets.QApplication.instance() is None:
        return
    from shiboken6 import isValid
    for widget in _qt_top_level_widgets():
        if any(widget is previous for previous in existing) or not isValid(widget):
            continue
        widget.close()
        if isValid(widget):
            widget.deleteLater()
    core.QCoreApplication.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)


class IsolatedQtTestResult(unittest.TextTestResult):
    """Keep test-owned Qt trees out of later tests' global theme/layout work."""

    def startTest(self, test):
        super().startTest(test)
        # Registered before setUp, so this runs after the test's own cleanups.
        # A cleanup exception is a test error, not a silently ignored failure.
        test.addCleanup(_cleanup_test_qt_widgets, _qt_top_level_widgets())


def run_ci(
    *,
    root: Path | str = _SOFTWARE_TESTING_ROOT,
    selected_tests: tuple[str, ...] | None = None,
    verbosity: int = 2,
) -> bool:
    """Compile the estate and execute selected tests, failing closed on errors."""

    if not _ensure_ci_dependencies(selected_tests):
        return False

    test_root = Path(root).resolve()
    syntax_errors = _compile_python(test_root)
    if syntax_errors:
        print("software-testing syntax validation failed:", file=sys.stderr)
        for error in syntax_errors:
            print(f"  {error}", file=sys.stderr)
        return False

    suite, load_errors = build_suite(
        test_root,
        selected_tests=selected_tests,
    )
    if load_errors:
        print("software-test collection failed:", file=sys.stderr)
        for error in load_errors:
            print(f"  {error}", file=sys.stderr)
        return False

    test_count = suite.countTestCases()
    if test_count == 0:
        print("software-testing syntax validation passed; no impacted tests selected")
        return True

    result = unittest.TextTestRunner(verbosity=verbosity, resultclass=IsolatedQtTestResult).run(suite)
    if result.wasSuccessful():
        scope = "selected" if selected_tests is not None else "full"
        print(f"software testing passed: {test_count} {scope} test(s)")
    return result.wasSuccessful()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile and run centralized AgMark developer/CI software tests."
    )
    parser.add_argument(
        "--base",
        help="base Git commit for dependency-aware test selection",
    )
    parser.add_argument(
        "--head",
        help="head Git commit for dependency-aware test selection",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="bypass Git impact selection and run all operation-path tests",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="use compact unittest output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    verbosity = 1 if arguments.quiet else 2
    selected_tests: tuple[str, ...] | None = None

    if arguments.head and not arguments.all:
        selection = select_from_git(
            _REPOSITORY_ROOT,
            base=arguments.base,
            head=arguments.head,
        )
        for reason in selection.reasons:
            print(reason)

        if selection.full:
            print("impact selection requested the full software-testing suite")
        else:
            selected_tests = tuple(sorted(selection.tests))
            if selected_tests:
                print("running impacted tests:")
                for path in selected_tests:
                    print(f"  {path}")
            else:
                print("no executable software tests are impacted")

    return 0 if run_ci(
        selected_tests=selected_tests,
        verbosity=verbosity,
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
