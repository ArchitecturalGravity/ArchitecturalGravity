"""Select centralized AgMark software tests impacted by a Git diff.

The selector follows Python imports transitively, consults the base snapshot for
deleted or renamed sources, and supports ci-impact.json rules for dynamic
(non-import) dependencies. Unknown impact fails closed to the full centralized
software-testing suite.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict, deque
from dataclasses import dataclass, field
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tokenize
from typing import Iterable, Mapping, Sequence


AGMARK_ROOT = "AgMark"
SOFTWARE_TESTING_ROOT = f"{AGMARK_ROOT}/shared/software_testing"
MANIFEST_NAME = "ci-impact.json"
PYTHON_SUFFIXES = {".py", ".pyw"}
SELECTION_POLICY_FILES = {
    f"{SOFTWARE_TESTING_ROOT}/ci.py",
    f"{SOFTWARE_TESTING_ROOT}/select_tests.py",
}
CI_NEUTRAL_SUFFIXES = {".md", ".txt"}


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    old_path: str | None = None

    @property
    def paths(self) -> tuple[str, ...]:
        return (self.path,) if self.old_path is None else (self.old_path, self.path)


@dataclass(frozen=True)
class Snapshot:
    all_paths: set[str]
    python_sources: dict[str, str]
    text_sources: dict[str, str]

    def text(self, path: str) -> str | None:
        return self.text_sources.get(path)


@dataclass
class Selection:
    full: bool = False
    tests: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)

    def add_test(self, path: str, reason: str) -> None:
        if self.full:
            return
        self.tests.add(path)
        self.reasons.append(f"SELECT {path}: {reason}")

    def mark_full(self, reason: str) -> None:
        self.full = True
        self.tests.clear()
        self.reasons.append(f"FULL: {reason}")

    def as_dict(self) -> dict[str, object]:
        return {
            "full": self.full,
            "tests": [] if self.full else sorted(self.tests),
            "reasons": list(self.reasons),
        }


def _run_git(repo_root: Path, args: Sequence[str]) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _git_ref_exists(repo_root: Path, ref: str | None) -> bool:
    if not ref or ref == "0" * 40:
        return False
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def read_changes(repo_root: Path, base: str | None, head: str) -> list[Change]:
    """Read rename-aware changes from base..head, or the root commit if needed."""

    if _git_ref_exists(repo_root, base):
        raw = _run_git(
            repo_root,
            ["diff", "--name-status", "--find-renames", "-z", base or "", head],
        )
    else:
        raw = _run_git(
            repo_root,
            [
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-status",
                "--find-renames",
                "-r",
                "-z",
                head,
            ],
        )

    tokens = [token.decode("utf-8") for token in raw.split(b"\0") if token]
    changes: list[Change] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        code = status[:1]
        if code in {"R", "C"}:
            if index + 1 >= len(tokens):
                raise ValueError(f"incomplete git rename/copy record for {status}")
            old_path, new_path = tokens[index], tokens[index + 1]
            index += 2
            changes.append(Change(status=status, path=new_path, old_path=old_path))
        else:
            if index >= len(tokens):
                raise ValueError(f"incomplete git change record for {status}")
            changes.append(Change(status=status, path=tokens[index]))
            index += 1
    return changes


def _decode_python(data: bytes) -> str:
    try:
        encoding, _ = tokenize.detect_encoding(BytesIO(data).readline)
    except SyntaxError:
        encoding = "utf-8"
    return data.decode(encoding, errors="replace")


def _snapshot_from_files(files: Iterable[tuple[str, bytes]]) -> Snapshot:
    all_paths: set[str] = set()
    python_sources: dict[str, str] = {}
    text_sources: dict[str, str] = {}

    for path, data in files:
        all_paths.add(path)
        suffix = PurePosixPath(path).suffix
        if suffix in PYTHON_SUFFIXES:
            python_sources[path] = _decode_python(data)
        elif PurePosixPath(path).name == MANIFEST_NAME:
            text_sources[path] = data.decode("utf-8", errors="replace")

    return Snapshot(all_paths, python_sources, text_sources)


def read_worktree_snapshot(repo_root: Path) -> Snapshot:
    root = repo_root / AGMARK_ROOT
    if not root.exists():
        return Snapshot(set(), {}, {})

    files: list[tuple[str, bytes]] = []
    for path in root.rglob("*"):
        if path.is_file():
            files.append((path.relative_to(repo_root).as_posix(), path.read_bytes()))
    return _snapshot_from_files(files)


def read_git_snapshot(repo_root: Path, ref: str) -> Snapshot:
    archive = _run_git(
        repo_root,
        ["archive", "--format=tar", ref, AGMARK_ROOT],
    )
    files: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            extracted = tar.extractfile(member)
            if extracted is not None:
                files.append((PurePosixPath(member.name).as_posix(), extracted.read()))
    return _snapshot_from_files(files)


def is_test_path(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        path.startswith(SOFTWARE_TESTING_ROOT + "/")
        and pure.suffix == ".py"
        and pure.name.startswith("test_")
    )


def is_ci_neutral(path: str) -> bool:
    """Mirror workflow path exclusions for documentation-only changes."""

    return (
        path.startswith(AGMARK_ROOT + "/")
        and PurePosixPath(path).suffix in CI_NEUTRAL_SUFFIXES
    )


def _module_name(path: str) -> str | None:
    pure = PurePosixPath(path)
    if pure.suffix not in PYTHON_SUFFIXES:
        return None
    parts = list(pure.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else None


def _root_relative_module(path: str) -> str | None:
    try:
        relative = PurePosixPath(path).relative_to(PurePosixPath(SOFTWARE_TESTING_ROOT))
    except ValueError:
        return None
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else None


def _relative_import_module(importer: str, level: int, module: str | None) -> str | None:
    importer_module = _module_name(importer)
    if importer_module is None:
        return None

    parts = importer_module.split(".")
    if PurePosixPath(importer).stem != "__init__":
        parts = parts[:-1]

    if level > len(parts):
        return None
    if level > 1:
        parts = parts[: -(level - 1)]
    if module:
        parts.extend(module.split("."))
    return ".".join(parts)


class ImportGraph:
    """Reverse import graph used to find tests affected by a changed Python file."""

    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot
        self.aliases: dict[str, set[str]] = defaultdict(set)
        self.reverse: dict[str, set[str]] = defaultdict(set)
        self._build_aliases()
        self._build_edges()

    def _build_aliases(self) -> None:
        for path in self.snapshot.python_sources:
            canonical = _module_name(path)
            if canonical:
                self.aliases[canonical].add(path)
            relative = _root_relative_module(path)
            if relative:
                self.aliases[relative].add(path)

    def _resolve(self, importer: str, module: str) -> set[str]:
        candidates = set(self.aliases.get(module, ()))
        module_path = module.replace(".", "/")
        roots = [
            PurePosixPath(SOFTWARE_TESTING_ROOT),
            PurePosixPath(AGMARK_ROOT),
        ]
        importer_parent = PurePosixPath(importer).parent
        roots.insert(0, importer_parent)

        for root in roots:
            prefix = root / module_path
            for candidate in (
                f"{prefix.as_posix()}.py",
                f"{prefix.as_posix()}.pyw",
                f"{prefix.as_posix()}/__init__.py",
            ):
                if candidate in self.snapshot.python_sources:
                    candidates.add(candidate)

        if len(candidates) <= 1:
            return candidates

        preferred = {
            path
            for path in candidates
            if PurePosixPath(path).parent == importer_parent
        }
        return preferred or candidates

    def _build_edges(self) -> None:
        for importer, source in self.snapshot.python_sources.items():
            try:
                tree = ast.parse(source, filename=importer)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    base = node.module
                    if node.level:
                        base = _relative_import_module(importer, node.level, node.module)
                    if base:
                        modules.append(base)
                        modules.extend(
                            f"{base}.{alias.name}"
                            for alias in node.names
                            if alias.name != "*"
                        )

                for module in modules:
                    for dependency in self._resolve(importer, module):
                        if dependency != importer:
                            self.reverse[dependency].add(importer)

    def affected_tests(self, changed_path: str) -> set[str]:
        selected: set[str] = set()
        queue: deque[str] = deque([changed_path])
        seen = {changed_path}

        while queue:
            dependency = queue.popleft()
            for importer in self.reverse.get(dependency, ()):
                if importer in seen:
                    continue
                seen.add(importer)
                if is_test_path(importer):
                    selected.add(importer)
                queue.append(importer)

        return selected


def _glob_regex(pattern: str) -> re.Pattern[str]:
    pattern = pattern.replace("\\", "/").lstrip("./")
    regex = ""
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    index += 1
                    regex += "(?:.*/)?"
                else:
                    regex += ".*"
                continue
            regex += "[^/]*"
        elif char == "?":
            regex += "[^/]"
        else:
            regex += re.escape(char)
        index += 1
    return re.compile(rf"^{regex}$")


def _matches(path: str, pattern: str) -> bool:
    return bool(_glob_regex(pattern).match(path))


def _manifest_paths(snapshot: Snapshot) -> tuple[str, ...]:
    return tuple(
        sorted(
            path
            for path in snapshot.text_sources
            if PurePosixPath(path).name == MANIFEST_NAME
        )
    )


def _expand_test_patterns(
    snapshot: Snapshot,
    manifest_path: str,
    patterns: Iterable[object],
) -> set[str]:
    manifest_parent = PurePosixPath(manifest_path).parent
    tests = {path for path in snapshot.all_paths if is_test_path(path)}
    selected: set[str] = set()

    for value in patterns:
        if not isinstance(value, str):
            continue
        if value.startswith(AGMARK_ROOT + "/"):
            selected.update(path for path in tests if _matches(path, value))
            continue

        for path in tests:
            try:
                relative = PurePosixPath(path).relative_to(manifest_parent).as_posix()
            except ValueError:
                continue
            if _matches(relative, value):
                selected.add(path)

    return selected


def _apply_manifest(
    selection: Selection,
    snapshot: Snapshot,
    manifest_path: str,
    changed_path: str,
) -> bool:
    raw = snapshot.text(manifest_path)
    if raw is None:
        return False
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(manifest, dict):
        return False

    parent = PurePosixPath(manifest_path).parent
    try:
        relative = PurePosixPath(changed_path).relative_to(parent).as_posix()
    except ValueError:
        return False

    handled = False
    full_suite_on = manifest.get("full_suite_on", ())
    if isinstance(full_suite_on, list) and any(
        isinstance(pattern, str) and _matches(relative, pattern)
        for pattern in full_suite_on
    ):
        selection.mark_full(f"{changed_path} matched {manifest_path} full_suite_on")
        return True

    rules = manifest.get("rules", ())
    if not isinstance(rules, list):
        return False

    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        changed = rule.get("changed", ())
        if not isinstance(changed, list) or not any(
            isinstance(pattern, str) and _matches(relative, pattern)
            for pattern in changed
        ):
            continue

        excluded = rule.get("exclude", ())
        if isinstance(excluded, list) and any(
            isinstance(pattern, str) and _matches(relative, pattern)
            for pattern in excluded
        ):
            continue

        run = rule.get("run", ())
        if isinstance(run, list):
            for test in sorted(_expand_test_patterns(snapshot, manifest_path, run)):
                selection.add_test(
                    test,
                    f"{changed_path} matched {manifest_path} rule {index + 1}",
                )

        if rule.get("full") is True:
            selection.mark_full(
                f"{changed_path} matched {manifest_path} rule {index + 1}"
            )
            return True

        if rule.get("covers") is True:
            handled = True

    return handled


def apply_manifest_rules(
    selection: Selection,
    snapshot: Snapshot,
    changed_path: str,
) -> bool:
    handled = False
    for manifest_path in _manifest_paths(snapshot):
        handled = (
            _apply_manifest(selection, snapshot, manifest_path, changed_path)
            or handled
        )
        if selection.full:
            return True
    return handled


def classify_changes(
    changes: Sequence[Change],
    head_snapshot: Snapshot,
    base_snapshot: Snapshot | None = None,
) -> Selection:
    """Select impacted tests, failing closed to the full suite when uncertain."""

    selection = Selection()
    graphs = [ImportGraph(head_snapshot)]
    if base_snapshot is not None:
        graphs.append(ImportGraph(base_snapshot))

    for change in changes:
        for path in change.paths:
            selection.reasons.append(f"CHANGED {change.status} {path}")

        relevant_paths = [
            path
            for path in change.paths
            if path == AGMARK_ROOT
            or path.startswith(AGMARK_ROOT + "/")
        ]
        if not relevant_paths:
            continue

        for path in relevant_paths:
            if is_ci_neutral(path):
                selection.reasons.append(f"IGNORE {path}: CI-neutral documentation")
                continue

            if path in SELECTION_POLICY_FILES:
                selection.mark_full(f"selection policy changed: {path}")
                continue

            if PurePosixPath(path).name == MANIFEST_NAME:
                selection.mark_full(f"impact manifest changed: {path}")
                continue

            test_path = is_test_path(path)
            deleted = change.status.startswith("D") and path == change.path
            if test_path:
                if not deleted and path in head_snapshot.all_paths:
                    selection.add_test(path, "test file changed")
                continue

            manifest_handled = apply_manifest_rules(selection, head_snapshot, path)
            if base_snapshot is not None:
                manifest_handled = (
                    apply_manifest_rules(selection, base_snapshot, path)
                    or manifest_handled
                )
            if selection.full:
                continue

            suffix = PurePosixPath(path).suffix
            if suffix in PYTHON_SUFFIXES:
                impacted: set[str] = set()
                for graph in graphs:
                    impacted.update(graph.affected_tests(path))
                for test in sorted(impacted):
                    selection.add_test(
                        test,
                        f"depends on changed Python module {path}",
                    )
                if impacted or manifest_handled:
                    continue
                selection.mark_full(
                    f"no safe dependency mapping for changed Python file {path}"
                )
                continue

            if manifest_handled:
                continue

            selection.mark_full(
                f"no impact rule for changed non-Python file {path}"
            )

    return selection


def select_from_git(
    repo_root: Path,
    *,
    base: str | None,
    head: str,
) -> Selection:
    changes = read_changes(repo_root, base, head)
    head_snapshot = read_worktree_snapshot(repo_root)
    base_snapshot = (
        read_git_snapshot(repo_root, base)
        if _git_ref_exists(repo_root, base)
        else None
    )
    return classify_changes(changes, head_snapshot, base_snapshot)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    selection = select_from_git(
        args.repo_root.resolve(),
        base=args.base,
        head=args.head,
    )

    if args.json:
        print(json.dumps(selection.as_dict(), indent=2, sort_keys=True))
    else:
        for reason in selection.reasons:
            print(reason)
        if selection.full:
            print("selection=full")
        else:
            print(f"selection={json.dumps(sorted(selection.tests))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "Change",
    "ImportGraph",
    "Selection",
    "Snapshot",
    "classify_changes",
    "read_changes",
    "read_git_snapshot",
    "read_worktree_snapshot",
    "select_from_git",
]
