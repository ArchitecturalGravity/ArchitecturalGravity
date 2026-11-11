"""Provider-free integration evidence for benchmark-family neutrality."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import unittest


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_SHARED_ROOT = _REPOSITORY_ROOT / "AgMark" / "shared"
_FRONTEND_ROOT = _REPOSITORY_ROOT / "AgMark" / "gui"
_PRODUCTION_SUFFIXES = frozenset(
    {
        ".py",
        ".json",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".vue",
        ".yaml",
        ".yml",
        ".toml",
        ".sh",
    }
)
_FAMILY_MARKERS = (
    "authorityresolutionbenchmark",
)


def _normalized(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _contains_family_marker(value: str) -> bool:
    normalized = _normalized(value)
    return any(marker in normalized for marker in _FAMILY_MARKERS)


def _production_code_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for root in (_SHARED_ROOT, _FRONTEND_ROOT):
        for directory, children, names in os.walk(root):
            children[:] = sorted(
                name for name in children
                if name not in {"software_testing", ".venv", ".linux-pyside6", "__pycache__"}
                and not (Path(directory) / name / "pyvenv.cfg").is_file()
            )
            for name in names:
                path = Path(directory) / name
                if path.suffix.casefold() in _PRODUCTION_SUFFIXES:
                    files.append(path)
    return tuple(sorted(files))


def _python_executable_tokens(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.add(id(first.value))

    tokens: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstring_nodes:
                tokens.append(node.value)
        elif isinstance(node, ast.Name):
            tokens.append(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.append(node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module:
            tokens.append(node.module)
        elif isinstance(node, ast.alias):
            tokens.append(node.name)
            if node.asname:
                tokens.append(node.asname)
    return tuple(tokens)


class BenchmarkNeutralityIntegrationTests(unittest.TestCase):
    def test_shared_and_frontend_production_sources_are_family_name_neutral(self) -> None:
        files = _production_code_files()
        self.assertTrue(
            any(path.suffix.casefold() == ".py" for path in files),
            "neutrality scan did not discover shared production Python sources",
        )

        violations: list[str] = []
        for path in files:
            relative = path.relative_to(_REPOSITORY_ROOT).as_posix()
            if path.suffix.casefold() == ".py":
                matching_tokens = sorted(
                    {
                        token
                        for token in _python_executable_tokens(path)
                        if _contains_family_marker(token)
                    }
                )
                if matching_tokens:
                    violations.append(f"{relative}: {matching_tokens!r}")
                continue

            source = path.read_text(encoding="utf-8")
            if _contains_family_marker(source):
                violations.append(relative)

        self.assertEqual(
            [],
            violations,
            "shared/frontend production must resolve benchmark semantics through "
            "registered authority rather than family-name coupling",
        )


if __name__ == "__main__":
    unittest.main()
