"""Repository architecture conformance tests.

These tests exercise the current AgMark tree through production validation
boundaries. They protect dependency direction and centralized developer-test
ownership without freezing private module topology.
"""

from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest

from AgMark.shared.validation import (
    RepositoryOwnedPath,
    RepositoryPythonSource,
    validate_repository_dependencies,
    validate_repository_ownership,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_AGMARK_ROOT = _REPOSITORY_ROOT / "AgMark"
_SOFTWARE_TESTING_ROOT = _AGMARK_ROOT / "shared" / "software_testing"
_BENCHMARK_MODULE_PREFIXES = (
    "AgMark.Authority_Resolution_Benchmark",
)
_ARCHIVE_DIRECTORY_NAMES = frozenset({"Legacy_Content"})
_ENVIRONMENT_DIRECTORY_NAMES = frozenset({".venv", ".linux-pyside6", "__pycache__", "Runtime"})


def _repository_relative(path: Path) -> str:
    return path.relative_to(_REPOSITORY_ROOT).as_posix()


def _is_archived(path: Path) -> bool:
    relative = path.relative_to(_AGMARK_ROOT)
    return any(part in _ARCHIVE_DIRECTORY_NAMES for part in relative.parts)


def _current_python_sources() -> tuple[RepositoryPythonSource, ...]:
    sources: list[RepositoryPythonSource] = []
    for path in _current_paths():
        if not path.is_file() or path.suffix != ".py":
            continue
        sources.append(
            RepositoryPythonSource(
                path=_repository_relative(path),
                source=path.read_text(encoding="utf-8"),
            )
        )
    return tuple(sources)


def _developer_test_routes() -> tuple[RepositoryOwnedPath, ...]:
    routes: list[RepositoryOwnedPath] = []
    for path in _current_paths():
        is_test_module = (
            path.is_file()
            and path.suffix == ".py"
            and (path.name.startswith("test_") or path.name.endswith("_test.py"))
        )
        is_test_directory = path.is_dir() and path.name == "tests"
        if is_test_module or is_test_directory:
            routes.append(
                RepositoryOwnedPath(
                    path=_repository_relative(path),
                    role="developer_testing",
                )
            )
    return tuple(routes)


def _current_paths(root: Path = _AGMARK_ROOT):
    """Inspect owned sources, pruning installed runtimes before traversal."""
    excluded = _ARCHIVE_DIRECTORY_NAMES | _ENVIRONMENT_DIRECTORY_NAMES
    for directory, children, filenames in os.walk(root):
        children[:] = sorted(name for name in children if name not in excluded)
        for name in (*children, *sorted(filenames)):
            yield Path(directory) / name


class RepositoryArchitectureTests(unittest.TestCase):
    def test_installed_gui_dependencies_are_outside_owned_source_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("gui/.linux-pyside6/PySide6/test_vendor.py", "gui/.venv/test_vendor.py", "Runtime/temp/test_scratch.py", "Runtime/.venv/test_vendor.py", "gui/views/results.py", "shared/software_testing/test_owned.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("pass\n", encoding="utf-8")
            sources = {path.relative_to(root).as_posix() for path in _current_paths(root) if path.is_file()}
            self.assertEqual({"gui/views/results.py", "shared/software_testing/test_owned.py"}, sources)

    def test_current_python_dependencies_respect_architecture_boundaries(self) -> None:
        sources = _current_python_sources()
        self.assertTrue(sources, "architecture scan discovered no AgMark Python")

        issues = validate_repository_dependencies(
            sources,
            benchmark_module_prefixes=_BENCHMARK_MODULE_PREFIXES,
            source_id="architecture-current-tree",
        )

        self.assertEqual(
            (),
            issues,
            "current AgMark imports violate dependency direction",
        )

    def test_developer_test_routes_remain_centralized(self) -> None:
        routes = _developer_test_routes()
        self.assertTrue(
            any(
                (_REPOSITORY_ROOT / route.path).is_relative_to(_SOFTWARE_TESTING_ROOT)
                for route in routes
            ),
            "architecture scan discovered no centralized developer tests",
        )

        issues = validate_repository_ownership(
            routes,
            source_id="architecture-current-test-estate",
        )

        self.assertEqual(
            (),
            issues,
            "AgMark developer/CI tests must remain under shared/software_testing",
        )


if __name__ == "__main__":
    unittest.main()
