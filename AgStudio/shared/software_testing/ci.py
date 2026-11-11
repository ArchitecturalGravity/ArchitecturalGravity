"""Changed-file-aware AgStudio software-test entry point.

Changed tests run directly. High-fan-out lint internals use explicit contract
test owners rather than treating an import of the broad analysis facade as proof
that every GUI or feature test is impacted. Other Python changes use transitive
import dependents; non-Python assets and packaging use explicit owners.
Unresolvable revisions fail closed to the full suite. Weekly/manual CI retains
complete integration coverage. External Guide files are not AgStudio test inputs.
"""

from __future__ import annotations

import argparse
import ast
import importlib
from pathlib import Path, PurePosixPath
import subprocess
import sys
import unittest
from collections import defaultdict
from collections.abc import Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
STUDIO_ROOT = REPO_ROOT / "AgStudio"
TEST_ROOT = STUDIO_ROOT / "shared" / "software_testing"
TEST_PREFIX = "AgStudio/shared/software_testing/"
WORKFLOW_PATH = ".github/workflows/AgStudio_CI.yml"
GIT_ATTRIBUTES_PATH = "AgStudio/.gitattributes"
PACKAGE_MANIFEST = "AgStudio/arcgrav_language_engine/pyproject.toml"
CI_ENTRY_PATH = TEST_PREFIX + "ci.py"



# Imports via lint/semantics and the public analysis facade reach nearly every
# Studio test. That is too coarse for localized lint changes: an edit to
# lint/members.py previously selected 118 test modules. Reviewed owners cover
# rule behavior, diagnostic admission, CLI/GUI display and structural editing.
# Public API/recognition changes and unmapped sources retain the conservative
# reverse-import analysis; a scheduled/manual full suite guards broader effects.
_MEMBER_TESTS = frozenset({
    "test_member_lint.py", "test_member_info.py", "test_block_move.py",
    "test_gui_block_drag.py", "test_lint_pipeline.py", "test_lint_rule_units.py",
    "test_diagnostic_evidence_indexes.py", "test_diagnostic_metadata.py",
    "test_lint_identity_contract.py", "test_language_engine_integration.py",
    "test_language_engine_package.py", "test_gui_analysis.py",
    "test_gui_finding_controls.py", "test_gui_correlations.py",
    "test_startup_defaults.py",
    "test_studio_corpus.py",
})
_BACKTICK_TESTS = frozenset({
    "test_startup_defaults.py", "test_editor_requirements.py",
    "test_lint_rule_units.py", "test_lint_pipeline.py",
    "test_gui_analysis.py",
    "test_gui_finding_controls.py", "test_language_engine_integration.py",
})
_QUOTED_TESTS = frozenset({
    "test_quoted_element_diagnostics.py", "test_double_quote_collisions.py",
    "test_exact_quoted_elements.py", "test_double_quote_colors.py",
    "test_lint_pipeline.py", "test_lint_rule_units.py",
    "test_gui_analysis.py", "test_language_engine_integration.py",
})
_SPELLING_TESTS = frozenset({
    "test_spelling.py", "test_lint_pipeline.py",
    "test_diagnostic_evidence_indexes.py", "test_gui_analysis.py",
    "test_gui_finding_controls.py", "test_language_engine_integration.py",
})
_EDITOR_TESTS = frozenset({
    "test_editor_requirements.py", "test_lint_pipeline.py",
    "test_lint_rule_units.py", "test_gui_analysis.py",
    "test_gui_finding_controls.py", "test_gui_quickfix.py",
    "test_studio_corpus.py",
})
_SEMANTIC_TESTS = _MEMBER_TESTS | frozenset({
    "test_semantic_graph.py", "test_definition_order.py",
    "test_analysis_stages.py", "test_lint_canonical.py",
    "test_unused_symbols.py", "test_lint_parent_binding.py",
})
_RULE_INFRASTRUCTURE_TESTS = (
    _MEMBER_TESTS | _BACKTICK_TESTS | _QUOTED_TESTS |
    _SPELLING_TESTS | _EDITOR_TESTS |
    frozenset({
        "test_diagnostic_admission.py", "test_diagnostic_metadata.py",
        "test_self_contained_contracts.py", "test_lint_coverage.py", "test_lint_canonical.py",
        "test_definition_order.py", "test_normative_operation_dash.py",
        "test_block_separator.py", "test_literal_fence_width.py",
        "test_document_start_section.py", "test_document_end_section.py",
        "test_unused_symbols.py",
    })
)
_RULE_UNIT_BASE_TESTS = frozenset({
    "test_lint_rule_units.py", "test_lint_pipeline.py",
    "test_diagnostic_admission.py", "test_diagnostic_metadata.py",
    "test_language_engine_integration.py",
    "test_self_contained_contracts.py",
})
_RULE_UNIT_EXTRAS = {
    "operation_list.py": {"test_normative_operation_dash.py"},
    "member_rule.py": _MEMBER_TESTS,
    "backtick_whitespace.py": _BACKTICK_TESTS,
    "quoted_collision.py": _QUOTED_TESTS,
    "quoted_unmatched.py": _QUOTED_TESTS,
    "spelling_rule.py": _SPELLING_TESTS,
    "editor_rule.py": _EDITOR_TESTS,
    "block_separator.py": {"test_block_separator.py"},
    "literal_fence_width.py": {"test_literal_fence_width.py"},
    "document_start.py": {"test_document_start_section.py"},
    "document_end.py": {"test_document_end_section.py"},
    "symbol_unused.py": {"test_unused_symbols.py", "test_definition_order.py"},
    "symbolic_reference.py": {"test_definition_order.py", "test_unused_symbols.py"},
    "symbol_nested.py": {"test_definition_order.py", "test_lint_identity_contract.py"},
}
_FOCUSED_SOURCE_OWNERS = {
    "AgStudio/shared/cli.py": frozenset({
        "test_analysis_stages.py",
        "test_block_separator.py",
        "test_diagnostic_metadata.py",
        "test_document_end_section.py",
        "test_document_start_section.py",
        "test_lint_identity_contract.py",
        "test_lint_pipeline.py",
        "test_literal_fence_width.py",
        "test_member_info.py",
        "test_member_lint.py",
        "test_spelling.py",
        "test_startup_defaults.py",
        "test_studio_corpus.py",
    }),
    "AgStudio/arcgrav_language_engine/lint/members.py": _MEMBER_TESTS,
    "AgStudio/arcgrav_language_engine/lint/semantics.py": _SEMANTIC_TESTS,
    "AgStudio/arcgrav_language_engine/lint/rules.py": _RULE_INFRASTRUCTURE_TESTS,
    "AgStudio/arcgrav_language_engine/lint/findings.py": _RULE_INFRASTRUCTURE_TESTS,
    "AgStudio/arcgrav_language_engine/lint/quoted_elements.py": _QUOTED_TESTS,
    "AgStudio/arcgrav_language_engine/lint/spelling.py": _SPELLING_TESTS,
    "AgStudio/arcgrav_language_engine/lint/editor_checks.py": _EDITOR_TESTS,
}
_RULE_UNIT_PREFIX = "AgStudio/arcgrav_language_engine/lint/rule_units/"
_AGENT_REFERENCE_SOURCES = frozenset({
    "AgStudio/arcgrav_language_engine/lint/rules.py",
    "AgStudio/arcgrav_language_engine/lint/document_end.py",
    "AgStudio/arcgrav_language_engine/lint/quoted_elements.py",
    "AgStudio/arcgrav_language_engine/lint/editor_checks.py",
    "AgStudio/arcgrav_language_engine/lint/members.py",
    "AgStudio/arcgrav_language_engine/lint/spelling.py",
    "AgStudio/arcgrav_language_engine/version.py",
    "AgStudio/arcgrav_language_engine/syntax_contract.py",
    "AgStudio/arcgrav_language_engine/recognition/source.py",
})



def _explicit_test_owners(source: str) -> set[str] | None:
    """Return reviewed owners, or None to retain import-dependent selection."""
    owner_tests = _FOCUSED_SOURCE_OWNERS.get(source)
    if owner_tests is None and source.startswith(_RULE_UNIT_PREFIX) and source.endswith(".py"):
        # The shared registry/contracts are broader than any individual rule.
        filename = PurePosixPath(source).name
        owner_tests = (_RULE_INFRASTRUCTURE_TESTS if filename in
                       {"registry.py", "contracts.py", "__init__.py",
                        "prefix_shared.py", "structural_checks.py"}
                       else _RULE_UNIT_BASE_TESTS | _RULE_UNIT_EXTRAS.get(filename, set()))
    return None if owner_tests is None else {
        TEST_PREFIX + filename for filename in owner_tests
    }


def changed_paths(raw: bytes) -> tuple[str, ...]:
    """Decode rename-aware NUL-separated git --name-status output."""
    tokens = [part.decode("utf-8", errors="surrogateescape")
              for part in raw.split(b"\0") if part]
    paths: list[str] = []
    cursor = 0
    while cursor < len(tokens):
        status = tokens[cursor]
        cursor += 1
        if not status or status[0] not in "ACDMRTUXB":
            raise ValueError("unrecognized git diff status")
        count = 2 if status[0] in "RC" else 1
        if cursor + count > len(tokens):
            raise ValueError("incomplete git diff record")
        paths.extend(tokens[cursor:cursor + count])
        cursor += count
    return tuple(paths)


def changed_since(base: str | None, head: str | None) -> tuple[str, ...] | None:
    """Return changed paths, or None if the diff cannot safely be resolved."""
    if not base or not head or set(base) == {"0"}:
        return None
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "-z", "--find-renames",
             base, head, "--"],
            cwd=REPO_ROOT, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return changed_paths(result.stdout)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Could not determine changed files; running all tests: {exc}",
              file=sys.stderr)
        return None


def available_tests() -> tuple[Path, ...]:
    return tuple(sorted(
        path for path in TEST_ROOT.rglob("test_*.py")
        if path.is_file() and "__pycache__" not in path.parts
    ))


def _module_name(path: Path) -> str:
    """Canonical checkout module name for a Python source file."""
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _source_imports(path: Path, module: str) -> set[str]:
    """Find static imports, including local relative and literal dynamic imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current_package = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(current_package):
                    continue
                pieces = current_package[:len(current_package) - node.level + 1]
                if node.module:
                    pieces.extend(node.module.split("."))
                prefix = ".".join(pieces)
            else:
                prefix = node.module or ""
            if prefix:
                names.add(prefix)
            for alias in node.names:
                if alias.name != "*":
                    names.add(f"{prefix}.{alias.name}" if prefix else alias.name)
        elif (isinstance(node, ast.Call) and node.args
              and isinstance(node.args[0], ast.Constant)
              and isinstance(node.args[0].value, str)
              and (isinstance(node.func, ast.Name)
                   and node.func.id in ("__import__", "import_module", "_import_module")
                   or isinstance(node.func, ast.Attribute)
                   and node.func.attr == "import_module")):
            names.add(node.args[0].value)
    return names


def _import_dependents(changed: set[str]) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Reverse Python import graph; standard-library dependencies are excluded.

    This maps concrete imports rather than guessing that every source change
    may affect every test. Package initializers and standalone-engine aliases
    are explicitly represented.
    """
    modules: dict[str, str] = {}
    paths: dict[str, Path] = {}
    for path in STUDIO_ROOT.rglob("*.py"):
        if any(part.startswith(".") or part == "__pycache__"
               for part in path.relative_to(STUDIO_ROOT).parts[:-1]):
            continue
        name = _module_name(path)
        modules[name] = path.relative_to(REPO_ROOT).as_posix()
        paths[name] = path
    # Deleted modules are still import targets in the remaining source tree.
    # Without these placeholders, removing a production file could skip tests
    # that should report an unresolved import.
    for deleted in changed:
        modules.setdefault(_module_name(REPO_ROOT / deleted), deleted)

    reverse: dict[str, set[str]] = defaultdict(set)
    for name, path in paths.items():
        imports = _source_imports(path, name)
        for imported in imports:
            if imported == "arcgrav_language_engine" or imported.startswith(
                    "arcgrav_language_engine."):
                imported = "AgStudio." + imported
            # Only explicit imports participate. Treating every intermediate
            # package as a dependency makes a shared package initializer
            # accidentally pull unrelated tests into nearly every change.
            if imported in modules and imported != name:
                reverse[imported].add(name)
    return modules, reverse


def _tests_for_source_changes(changed: set[str]) -> set[str]:
    modules, reverse = _import_dependents(changed)
    changed_modules = {name for name, path in modules.items() if path in changed}
    affected = set(changed_modules)
    pending = list(changed_modules)
    while pending:
        for importer in reverse.get(pending.pop(), ()):
            if importer not in affected:
                affected.add(importer)
                pending.append(importer)
    return {
        path for name, path in modules.items()
        if name in affected and path.startswith(TEST_PREFIX)
        and PurePosixPath(path).name.startswith("test_")
    }


def _resource_tests(path: str) -> set[str]:
    """Explicit owners for non-Python assets that static imports cannot see."""
    if path == WORKFLOW_PATH or path == CI_ENTRY_PATH:
        return {"test_ci_selection.py"}
    if path == PACKAGE_MANIFEST:
        return {"test_language_engine_package.py", "test_language_engine_relocation.py"}
    if path == GIT_ATTRIBUTES_PATH:
        return {"test_git_attributes_scope.py", "test_ci_selection.py",
                "test_recognition_source.py", "test_document_model.py"}
    if path == "AgStudio/arcgrav_language_engine/arcgrav_agent_reference.yaml":
        return {"test_agent_reference.py", "test_language_engine_package.py"}
    if path.endswith("/requirements.txt"):
        return {"test_gui_integration.py", "test_spelling.py",
                "test_language_engine_package.py"}
    if path.startswith("AgStudio/examples/"):
        return {"test_studio_corpus.py",
                "test_gui_triad_positions.py"}
    if path.startswith("AgStudio/color_schemes/"):
        return {"test_gui_color_schemes.py", "test_gui_move_colors.py"}
    if path.startswith("AgStudio/gui/icons/"):
        return {"test_gui_integration.py", "test_gui_pane_headers.py"}
    if path.startswith(TEST_PREFIX + "corpus/"):
        return {"test_studio_corpus.py", "test_language_engine_package.py"}
    if path.startswith("AgStudio/gui/"):
        return {"test_gui_integration.py"}
    if path.startswith("AgStudio/arcgrav_language_engine/"):
        return {"test_language_engine_integration.py"}
    return {"test_composed_service.py"}


def impacted_tests(paths: Sequence[str]) -> tuple[str, ...] | None:
    """Select changed tests and transitive import dependents of changed sources.

    A missing/unusable git comparison (handled by changed_since) is the only
    normal full-suite fallback. External repositories, including ArcGrav guide
    files, are not AgStudio test inputs or CI triggers. Documentation is inert.
    """
    changed_tests: set[str] = set()
    changed_sources: set[str] = set()
    resources: set[str] = set()
    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        if path != WORKFLOW_PATH and not path.startswith("AgStudio/"):
            continue
        if path in (WORKFLOW_PATH, PACKAGE_MANIFEST):
            resources.add(path)
            continue
        # Dependency manifests are executable CI inputs, not documentation.
        if path.endswith("/requirements.txt"):
            resources.add(path)
            continue
        if PurePosixPath(path).suffix.lower() in (".md", ".txt"):
            continue
        if (path.startswith(TEST_PREFIX)
                and PurePosixPath(path).name.startswith("test_")
                and path.endswith(".py")):
            if (REPO_ROOT / path).is_file():
                changed_tests.add(path)
            continue
        if path == CI_ENTRY_PATH:
            resources.add(path)
        elif path.endswith(".py"):
            changed_sources.add(path)
        else:
            resources.add(path)

    if not (changed_tests or changed_sources or resources):
        return ()
    selected = set(changed_tests)
    import_graph_sources: set[str] = set()
    for source in changed_sources:
        owners = _explicit_test_owners(source)
        if owners is None:
            import_graph_sources.add(source)
        else:
            selected.update(owners)
    if import_graph_sources:
        selected.update(_tests_for_source_changes(import_graph_sources))
    if any(source in _AGENT_REFERENCE_SOURCES for source in changed_sources):
        selected.add(TEST_PREFIX + "test_agent_reference.py")
    # New or as-yet-unimported modules still receive a focused smoke test.
    if changed_sources and not (selected - changed_tests):
        for source in changed_sources:
            selected.update(TEST_PREFIX + name for name in _resource_tests(source))
    # Focused boundary smoke checks cover dynamic/late imports that are
    # deliberately not inferred from arbitrary runtime strings.
    if any(source.startswith("AgStudio/arcgrav_language_engine/")
           for source in changed_sources):
        selected.add(TEST_PREFIX + "test_language_engine_integration.py")
    if any(source.startswith("AgStudio/gui/") for source in changed_sources):
        selected.add(TEST_PREFIX + "test_gui_integration.py")
    # An engine package entry-point change also exercises isolated imports and
    # wheel transport; these subprocess tests cannot be inferred from AST.
    if any(source in ("AgStudio/arcgrav_language_engine/__init__.py",
                      "AgStudio/arcgrav_language_engine/api.py")
           for source in changed_sources):
        selected.update((TEST_PREFIX + "test_language_engine_package.py",
                         TEST_PREFIX + "test_language_engine_relocation.py"))
    for asset in resources:
        selected.update(TEST_PREFIX + name for name in _resource_tests(asset))
    available = {path.relative_to(REPO_ROOT).as_posix() for path in available_tests()}
    return tuple(sorted(selected & available))


def compile_sources() -> bool:
    """Syntax-check source and tests without importing GUI dependencies."""
    errors: list[str] = []
    for root in (STUDIO_ROOT,):
        for path in sorted(root.rglob("*.py")):
            # Local virtual environments can live under either project during
            # development; their packaged templates are not project sources.
            if any(part == "__pycache__" or part.startswith(".")
                   for part in path.relative_to(root).parts[:-1]):
                continue
            try:
                compile(path.read_bytes(), str(path), "exec")
            except (OSError, SyntaxError, ValueError) as exc:
                errors.append(f"{path.relative_to(REPO_ROOT)}: {exc}")
    for error in errors:
        print(error, file=sys.stderr)
    return not errors


def run_tests(selected: tuple[str, ...] | None) -> bool:
    tests = available_tests() if selected is None else tuple(
        sorted({REPO_ROOT / path for path in selected})
    )
    if not tests and selected is not None:
        print("No executable AgStudio tests impacted by this change.")
        return True
    if not tests:
        print("No AgStudio software tests available.", file=sys.stderr)
        return False

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for path in tests:
        if not path.is_file() or not path.is_relative_to(TEST_ROOT):
            print(f"Selected test is unavailable: {path}", file=sys.stderr)
            return False
        # Spawned workers must be able to import fixture callables by the same
        # stable module name in a fresh interpreter (not a parent-only alias).
        module_name = '.'.join(path.relative_to(REPO_ROOT).with_suffix('').parts)
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            print(f"Test import failed for {path}: {exc}", file=sys.stderr)
            return False
        suite.addTests(loader.loadTestsFromModule(module))

    if not suite.countTestCases():
        print("Selected tests contain zero test cases.", file=sys.stderr)
        return False
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base revision for changed-file selection")
    parser.add_argument("--head", help="head revision for changed-file selection")
    parser.add_argument("--all", action="store_true", help="run every AgStudio test")
    args = parser.parse_args(argv)

    changes = None if args.all else changed_since(args.base, args.head)
    selected = None if changes is None else impacted_tests(changes)
    if selected is None:
        print("Running the full AgStudio software-test suite.")
    else:
        print(f"Impacted tests: {len(selected)} of {len(available_tests())} test modules")
        for path in selected:
            print("  " + path)
    if not compile_sources():
        return 1
    return 0 if run_tests(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
