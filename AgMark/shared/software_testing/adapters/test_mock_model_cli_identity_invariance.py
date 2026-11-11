"""Guard post-composition live/mock parity against identity-selected runner algorithms.

This is a conservative source-level regression guard, supplementary to the
registered real-process/live-transport parity tests. Target identity may be
retained as truthful evidence, and launch mode / authentication class may
control their documented operational or evidence consequences. Target class,
evidence class, registration identity, compatibility profile, and synthetic
scenario must never select a different runner algorithm.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


_ROOT = Path(__file__).resolve().parents[4] / "AgMark/shared/adapters"

# Keep this inventory explicit. A renamed or extracted behavioral entry point
# must be reviewed and re-enrolled instead of silently escaping inspection.
_SCOPES: dict[str, tuple[str, ...]] = {
    "Codex_CLI/runner.py": (
        "_registered_executable_resolver",
        "execute",
        "_preflight",
        "_preflight_terminal",
        "_launch_argv",
        "_native_exec_argv",
        "_wsl_exec_argv",
        "_launch_metadata",
        "_execute_process",
        "_extract_response",
        "_execution_error_code",
        "_invoke_capture",
        "_invoke",
        "_terminal",
    ),
    "Codex_CLI/model_discovery.py": (
        "probe_model_discovery",
        "_launch_command",
        "_probe_wsl_session",
        "_run_interactive_model_list",
        "_wait_for_response",
        "_decode_batch_model_list",
        "decode_model_list_response",
    ),
    "execution/orchestration.py": (
        "execute_target",
        "_capture",
        "_partial_capture",
        "_finish",
    ),
    "execution/emission.py": (
        "emit_terminal_observation",
        "_authentication_evidence",
        "_usage_evidence",
        "_process_evidence",
        "_error_evidence",
    ),
}

_IDENTITY_FIELDS = frozenset({
    "target_class", "evidence_class", "compatibility_profile",
    "registration_id", "scenario", "scenario_id",
})
# Non-secret target-specific labels are legitimate as *emitted data*, never
# as predicates or lookup keys choosing runner-owned implementation behavior.
_IDENTITY_LITERALS = (
    "mock-model", "arcgrav.mock", "mock_model", "scenario:",
)


def _literal(value: ast.AST) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _reads_identity(value: ast.AST, aliases: set[str], *, literals: bool) -> bool:
    """Recognize direct identity access, copied scalar aliases and scenario tests."""
    for node in ast.walk(value):
        if isinstance(node, ast.Attribute) and node.attr in _IDENTITY_FIELDS:
            return True
        if isinstance(node, ast.Subscript) and _literal(node.slice) in _IDENTITY_FIELDS:
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "hasattr"}
            and len(node.args) > 1
            and _literal(node.args[1]) in _IDENTITY_FIELDS
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and _literal(node.args[0]) in _IDENTITY_FIELDS
        ):
            return True
        if isinstance(node, ast.Name) and (
            node.id in aliases
            or "MOCK" in node.id.upper()
            or "SCENARIO" in node.id.upper()
        ):
            return True
        if literals and isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(marker in node.value.lower() for marker in _IDENTITY_LITERALS):
                return True
    return False


def _identity_aliases(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Follow simple scalar identity assignments, including successive aliases.

    Deliberately do not taint aggregate evidence dictionaries: reading target
    identity solely to retain truthful target metadata is allowed.
    """
    assignments: list[tuple[ast.AST, list[str]]] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            names = [
                target.id for target in node.targets if isinstance(target, ast.Name)
            ]
            assignments.append((node.value, names))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                assignments.append((node.value, [node.target.id]))
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            assignments.append((node.value, [node.target.id]))
    aliases: set[str] = set()
    for _ in range(len(assignments) + 1):
        changed = False
        for value, names in assignments:
            # Track derived scalar identity, but not evidence aggregates whose
            # identity members are retained as data rather than dispatch keys.
            scalar = isinstance(value, (
                ast.Attribute, ast.Subscript, ast.Name, ast.Call,
                ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.JoinedStr,
                ast.IfExp, ast.Compare,
            ))
            if scalar and _reads_identity(value, aliases, literals=False):
                for name in names:
                    if name not in aliases:
                        aliases.add(name)
                        changed = True
        if not changed:
            break
    return aliases


def _identity_dispatch_lines(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[int, ...]:
    """Find identity-based branching and indexed algorithm dispatch.

    Covers conditional statements/expressions, match/case, loop and
    comprehension filters, and table dispatch keyed by identity or its alias.
    """
    aliases = _identity_aliases(function)
    lines: set[int] = set()
    for node in ast.walk(function):
        predicate: ast.AST | None = None
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)):
            predicate = node.test
        elif isinstance(node, ast.Match):
            # Inspect both the match selector and literal case patterns.
            if _reads_identity(node.subject, aliases, literals=True) or any(
                _reads_identity(case.pattern, aliases, literals=True)
                or (
                    case.guard is not None
                    and _reads_identity(case.guard, aliases, literals=True)
                )
                for case in node.cases
            ):
                lines.add(node.lineno)
        elif isinstance(node, ast.comprehension):
            for condition in node.ifs:
                if _reads_identity(condition, aliases, literals=True):
                    lines.add(condition.lineno)
        elif isinstance(node, ast.Subscript):
            # Reading target["target_class"] as data is not dispatch.
            # Choosing an algorithm with handlers[target.target_class] is.
            if not isinstance(node.slice, ast.Constant) and _reads_identity(
                node.slice, aliases, literals=True
            ):
                lines.add(node.lineno)
        if predicate is not None and _reads_identity(predicate, aliases, literals=True):
            lines.add(node.lineno)
    return tuple(sorted(lines))


class MockModelIdentityInvarianceTests(unittest.TestCase):
    def test_post_composition_runner_has_no_target_identity_dispatch(self) -> None:
        for relative_path, required_functions in _SCOPES.items():
            with self.subTest(file=relative_path):
                path = _ROOT / relative_path
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                functions = {
                    node.name: node
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                self.assertTrue(set(required_functions) <= set(functions))
                for name in required_functions:
                    with self.subTest(file=relative_path, function=name):
                        self.assertEqual(
                            (), _identity_dispatch_lines(functions[name]),
                            f"{relative_path}:{name} branches on mock/live identity",
                        )

    def test_guard_rejects_identity_branches_and_alias_dispatch(self) -> None:
        mutations = (
            'if target.target_class == "mock-model": return mock_path()',
            'if target.evidence_class: return alternate()',
            'kind = target.compatibility_profile\nif kind: return alternate()',
            'kind = target.target_class\ncopy = kind\nreturn handlers[copy]()',
            'if registration["registration_id"] == "arcgrav.mock-model": pass',
            'if registration.get("registration_id") == "arcgrav.mock-model": pass',
            'kind = registration.get("target_class")\nif kind: return alternate()',
            'kind = str(registration.get("target_class"))\nif kind: return alternate()',
            'kind = registration.get("target_class") or ""\nif kind: return alternate()',
            'if model_id.endswith("scenario:completed"): return canned_result()',
            'match target.target_class:\n    case "mock-model": return alternate()',
            'return implementations[getattr(target, "evidence_class")]()',
            'return [item for item in sources if item["scenario_id"]]',
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                function = ast.parse("def run(target, registration, model_id):\n"
                                     + "\n".join("    " + line for line in mutation.splitlines()))
                self.assertTrue(
                    _identity_dispatch_lines(function.body[0]),
                    "the identity dispatch regression guard missed a mutation",
                )

    def test_guard_allows_truthful_identity_data_and_launch_mode(self) -> None:
        source = """
def run(target):
    evidence = {"class": target.target_class,
                "evidence_class": target.evidence_class,
                "profile": target.compatibility_profile}
    if target.launch_mode == "wsl":
        return execute_wsl(evidence)
    if target.authentication_class == "not_applicable":
        evidence["authentication"] = None
    return execute_native(evidence)
"""
        function = ast.parse(source).body[0]
        self.assertEqual((), _identity_dispatch_lines(function))


if __name__ == "__main__":
    unittest.main()
