"""Registered report evaluator resolution preserves exact implementation identity."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
import inspect
import sys
from unittest.mock import patch

from AgMark.gui.composition import discover_repository_application_authority, RepositoryCompositionError
from AgMark.gui.requests.reporting import _registered_report_evaluator, _report_configuration
from AgMark.gui.requests.repository_resources import _selected_authority


class RegisteredReportEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[5]
        authority = discover_repository_application_authority(self.root)
        self.candidate = next(item for item in authority.benchmark_candidates
            if "report_evaluator" in _selected_authority(item.registration))
        self.selected = deepcopy(_selected_authority(self.candidate.registration))
        self.configuration, _ = _report_configuration(self.root, self.candidate.registration, self.selected)

    def resolve(self):
        return _registered_report_evaluator(self.root, self.candidate, self.selected, self.configuration)

    def test_registered_evaluator_resolves_without_executing_it(self):
        self.assertTrue(callable(self.resolve()))

    def test_absent_optional_evaluator_has_no_substitute(self):
        del self.selected["report_evaluator"]
        self.assertIsNone(self.resolve())

    def test_unregistered_module_and_extra_fields_are_rejected(self):
        self.selected["report_evaluator"]["module"] = "unregistered.module"
        with self.assertRaisesRegex(RepositoryCompositionError, "does not match"):
            self.resolve()
        self.selected["report_evaluator"]["fallback"] = "unregistered.module"
        with self.assertRaisesRegex(RepositoryCompositionError, "unsupported fields"):
            self.resolve()

    def test_missing_callable_is_rejected(self):
        self.selected["report_evaluator"]["callable"] = "absent_report_evaluator"
        with self.assertRaisesRegex(RepositoryCompositionError, "implementation mismatch"):
            self.resolve()

    def test_same_path_stale_cached_module_is_never_used(self):
        declaration = self.selected["report_evaluator"]
        module_name = declaration["module"]
        expected_path = self.root / (module_name.replace(".", "/") + ".py")
        stale = SimpleNamespace(__file__=str(expected_path),
            evaluate_report_extensions=lambda **_: {"stale": True})
        with patch.dict(sys.modules, {module_name: stale}):
            resolved = self.resolve()
            evaluator = inspect.getclosurevars(resolved).nonlocals["evaluator"]
            self.assertIsNot(evaluator, stale.evaluate_report_extensions)
            self.assertTrue(evaluator.__module__.startswith("_agmark_report_evaluator_"))
            self.assertIs(sys.modules[module_name], stale)
        self.assertNotIn(evaluator.__module__, sys.modules)

    def test_registered_module_is_not_imported_before_origin_validation(self):
        with patch("importlib.import_module", side_effect=AssertionError("by-name import forbidden")):
            self.assertTrue(callable(self.resolve()))

    def test_changed_source_is_rejected_before_compilation_or_execution(self):
        module_name = self.selected["report_evaluator"]["module"]
        expected_path = self.root / (module_name.replace(".", "/") + ".py")
        original = Path.read_bytes
        def read(path):
            return b"raise AssertionError('unregistered code executed')" if path == expected_path else original(path)
        with patch.object(Path, "read_bytes", read), patch("builtins.compile") as compile_source:
            with self.assertRaises(RepositoryCompositionError):
                self.resolve()
            compile_source.assert_not_called()
