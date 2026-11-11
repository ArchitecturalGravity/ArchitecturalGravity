"""Selection-policy tests; these do not assert ArcGrav conformance."""

import unittest

from AgStudio.shared.software_testing.ci import available_tests, changed_paths, impacted_tests


class CISelectionTests(unittest.TestCase):
    def test_runner_imports_spawnable_canonical_modules_without_changing_selection(self):
        from unittest.mock import Mock, patch
        from AgStudio.shared.software_testing import ci
        path = 'AgStudio/shared/software_testing/test_feature_process.py'
        suite = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
        result = Mock()
        result.wasSuccessful.return_value = True
        with patch.object(ci.importlib, 'import_module', wraps=ci.importlib.import_module) as load, \
                patch.object(ci.unittest.defaultTestLoader, 'loadTestsFromModule', return_value=suite), \
                patch.object(ci.unittest, 'TextTestRunner') as runner:
            runner.return_value.run.return_value = result
            self.assertTrue(ci.run_tests((path,)))
        load.assert_called_once_with('AgStudio.shared.software_testing.test_feature_process')
        self.assertEqual(runner.return_value.run.call_args.args[0].countTestCases(), 1)

    def test_contract_removal_and_operation_witness_guards_are_selected(self):
        for source in ('AgStudio/arcgrav_language_engine/lint/rules.py',
                       'AgStudio/arcgrav_language_engine/lint/rule_units/operation_list.py'):
            with self.subTest(source=source):
                selected = impacted_tests((source,))
                self.assertIn('AgStudio/shared/software_testing/test_self_contained_contracts.py', selected)
                self.assertIn('AgStudio/shared/software_testing/test_normative_operation_dash.py', selected)

    def test_relocated_cli_selects_subprocess_contracts(self):
        selected = impacted_tests(("AgStudio/shared/cli.py",))
        for name in ("test_spelling.py", "test_lint_pipeline.py",
                     "test_diagnostic_metadata.py", "test_studio_corpus.py"):
            self.assertIn("AgStudio/shared/software_testing/" + name, selected)

    def test_changed_test_is_selected_directly(self):
        self.assertEqual(
            impacted_tests(("AgStudio/shared/software_testing/test_core_boundary.py",)),
            ("AgStudio/shared/software_testing/test_core_boundary.py",),
        )

    def test_python_changes_select_transitive_import_dependents(self):
        selected = impacted_tests(("AgStudio/shared/core.py",))
        self.assertIsNotNone(selected)
        self.assertIn("AgStudio/shared/software_testing/test_core_boundary.py", selected)
        self.assertNotIn("AgStudio/shared/software_testing/test_ci_selection.py", selected)
        self.assertLess(len(selected), len(available_tests()))

    def test_engine_change_and_packaging_metadata_are_scoped(self):
        for path in (
            "AgStudio/arcgrav_language_engine/api.py",
            "AgStudio/arcgrav_language_engine/syntax_contract.py",
            "AgStudio/arcgrav_language_engine/pyproject.toml",
        ):
            with self.subTest(path=path):
                selected = impacted_tests((path,))
                self.assertTrue(selected)
                self.assertNotIn(
                    "AgStudio/shared/software_testing/test_ci_selection.py", selected
                )
        self.assertEqual(
            impacted_tests(("AgStudio/arcgrav_language_engine/pyproject.toml",)),
            ("AgStudio/shared/software_testing/test_language_engine_package.py",
             "AgStudio/shared/software_testing/test_language_engine_relocation.py"),
        )
        self.assertEqual(impacted_tests(("pyproject.toml",)), ())
        self.assertEqual(
            impacted_tests(("AgStudio/shared/software_testing/requirements.txt",)),
            ("AgStudio/shared/software_testing/test_gui_integration.py",
             "AgStudio/shared/software_testing/test_language_engine_package.py",
             "AgStudio/shared/software_testing/test_spelling.py"),
        )

    def test_agent_reference_changes_select_regeneration_and_wheel_contracts(self):
        reference = "AgStudio/arcgrav_language_engine/arcgrav_agent_reference.yaml"
        selected = set(impacted_tests((reference,)))
        self.assertIn("AgStudio/shared/software_testing/test_agent_reference.py", selected)
        self.assertIn("AgStudio/shared/software_testing/test_language_engine_package.py", selected)

        for source in (
            "AgStudio/arcgrav_language_engine/lint/rules.py",
            "AgStudio/arcgrav_language_engine/lint/editor_checks.py",
            "AgStudio/arcgrav_language_engine/lint/members.py",
            "AgStudio/arcgrav_language_engine/lint/spelling.py",
            "AgStudio/arcgrav_language_engine/syntax_contract.py",
        ):
            with self.subTest(source=source):
                selected = set(impacted_tests((source,)))
                self.assertIn(
                    "AgStudio/shared/software_testing/test_agent_reference.py",
                    selected,
                )

    def test_compile_sources_includes_engine_without_importing_it(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from AgStudio.shared.software_testing import ci

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            studio = root / 'AgStudio'
            engine = studio / 'arcgrav_language_engine'
            studio.mkdir()
            engine.mkdir()
            (studio / 'valid.py').write_text('raise RuntimeError("do not import")\n')
            source = engine / 'api.py'
            source.write_text('def broken(\n')
            with patch.object(ci, 'REPO_ROOT', root), \
                    patch.object(ci, 'STUDIO_ROOT', studio):
                errors = StringIO()
                with redirect_stderr(errors):
                    self.assertFalse(ci.compile_sources())
                self.assertIn('AgStudio/arcgrav_language_engine/api.py', errors.getvalue())
                source.write_text('raise RuntimeError("do not import")\n')
                self.assertTrue(ci.compile_sources())

    def test_documentation_and_unrelated_changes_do_not_select_tests(self):
        self.assertEqual(
            impacted_tests((
                "AgStudio/README.md", "AgMark/shared/core.py",
                "AgMark/.gitattributes",
            )),
            (),
        )

    def test_agstudio_attributes_changes_select_studio_contracts(self):
        self.assertEqual(
            impacted_tests(("AgStudio/.gitattributes",)),
            (
                "AgStudio/shared/software_testing/test_ci_selection.py",
                "AgStudio/shared/software_testing/test_document_model.py",
                "AgStudio/shared/software_testing/test_git_attributes_scope.py",
                "AgStudio/shared/software_testing/test_recognition_source.py",
            ),
        )
        self.assertEqual(impacted_tests(("AgMark/.gitattributes",)), ())
        self.assertEqual(impacted_tests((".gitattributes",)), ())

    def test_ci_policy_change_runs_policy_tests_only(self):
        expected = ("AgStudio/shared/software_testing/test_ci_selection.py",)
        self.assertEqual(impacted_tests((".github/workflows/AgStudio_CI.yml",)),
                         expected)
        self.assertEqual(
            impacted_tests(("AgStudio/shared/software_testing/ci.py",)), expected
        )
        self.assertEqual(
            impacted_tests(("AgStudio/gui/requirements.txt",)),
            ("AgStudio/shared/software_testing/test_gui_integration.py",
             "AgStudio/shared/software_testing/test_language_engine_package.py",
             "AgStudio/shared/software_testing/test_spelling.py"),
        )

    def test_documentation_and_external_guide_are_not_executable_inputs(self):
        self.assertEqual(
            impacted_tests(("AgStudio/WORKGRAPH.md",
                            "AgStudio/shared/recognition/SPECIFICATION.md",
                            "AgStudio/DEVTREE.txt",
                            "ArcGrav/Guide/Syntax/Context_Operation.md")),
            (),
        )
        self.assertEqual(
            impacted_tests(("AgStudio/shared/README.md", "AgStudio/Docs/ROADMAP.md")),
            (),
        )

    def test_reverse_import_graph_avoids_unrelated_tests(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from AgStudio.shared.software_testing import ci

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            studio = root / "AgStudio"
            test_root = studio / "shared/software_testing"
            sources = {
                "AgStudio/__init__.py": "",
                "AgStudio/shared/__init__.py": "",
                "AgStudio/shared/software_testing/__init__.py": "",
                "AgStudio/gui/__init__.py": "",
                "AgStudio/shared/engine.py": "VALUE = 1\n",
                "AgStudio/shared/adapter.py": "from .engine import VALUE\n",
                "AgStudio/gui/widget.py": "VALUE = 2\n",
                "AgStudio/shared/software_testing/test_engine.py":
                    "from AgStudio.shared.adapter import VALUE\n",
                "AgStudio/shared/software_testing/test_widget.py":
                    "from AgStudio.gui.widget import VALUE\n",
            }
            for name, content in sources.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            with patch.object(ci, "REPO_ROOT", root), \
                    patch.object(ci, "STUDIO_ROOT", studio), \
                    patch.object(ci, "TEST_ROOT", test_root):
                self.assertEqual(
                    ci.impacted_tests(("AgStudio/shared/engine.py",)),
                    ("AgStudio/shared/software_testing/test_engine.py",),
                )
                self.assertEqual(
                    ci.impacted_tests(("AgStudio/gui/widget.py",)),
                    ("AgStudio/shared/software_testing/test_widget.py",),
                )
                (root / "AgStudio/shared/engine.py").unlink()
                self.assertEqual(
                    ci.impacted_tests(("AgStudio/shared/engine.py",)),
                    ("AgStudio/shared/software_testing/test_engine.py",),
                )


    def test_member_changes_select_contract_tests_instead_of_the_full_suite(self):
        source = "AgStudio/arcgrav_language_engine/lint/members.py"
        selected = set(impacted_tests((source,)))
        must_run = {
            "test_member_lint.py", "test_member_info.py", "test_block_move.py",
            "test_gui_analysis.py", "test_gui_correlations.py",
            "test_gui_finding_controls.py", "test_lint_pipeline.py",
            "test_diagnostic_evidence_indexes.py",
            "test_language_engine_integration.py",
        }
        self.assertTrue({
            "AgStudio/shared/software_testing/" + name for name in must_run
        } <= selected)
        self.assertLess(len(selected), 25)
        self.assertNotIn("AgStudio/shared/software_testing/test_triad_positions.py", selected)
        self.assertNotIn("AgStudio/shared/software_testing/test_recognition_lists.py", selected)
        self.assertNotIn("AgStudio/shared/software_testing/test_ci_selection.py", selected)

    def test_lint_rule_changes_have_bounded_owners(self):
        cases = (
            ("AgStudio/arcgrav_language_engine/lint/rule_units/backtick_whitespace.py",
             "test_startup_defaults.py", 20),
            ("AgStudio/arcgrav_language_engine/lint/rule_units/member_rule.py",
             "test_member_lint.py", 25),
            ("AgStudio/arcgrav_language_engine/lint/rules.py",
             "test_lint_pipeline.py", 45),
            ("AgStudio/arcgrav_language_engine/lint/semantics.py",
             "test_definition_order.py", 35),
        )
        for source, required, limit in cases:
            with self.subTest(source=source):
                selected = impacted_tests((source,))
                self.assertIsNotNone(selected)
                self.assertIn("AgStudio/shared/software_testing/" + required, selected)
                self.assertLess(len(selected), limit)

    def test_explicit_owners_union_with_changed_tests_and_import_graph(self):
        member_source = "AgStudio/arcgrav_language_engine/lint/members.py"
        changed_test = "AgStudio/shared/software_testing/test_ci_selection.py"
        related = set(impacted_tests((member_source,)))
        combined = set(impacted_tests((member_source, changed_test)))
        self.assertEqual(combined, related | {changed_test})
        other = set(impacted_tests(("AgStudio/shared/core.py",)))
        self.assertIn("AgStudio/shared/software_testing/test_core_boundary.py", other)
        self.assertNotEqual(other, related)

    def test_all_declared_owners_exist_and_new_rule_units_get_smoke_coverage(self):
        from AgStudio.shared.software_testing import ci
        available = {p.name for p in available_tests()}
        groups = list(ci._FOCUSED_SOURCE_OWNERS.values()) + [
            ci._RULE_INFRASTRUCTURE_TESTS,
            ci._RULE_UNIT_BASE_TESTS,
            *ci._RULE_UNIT_EXTRAS.values(),
        ]
        for owners in groups:
            self.assertFalse(set(owners) - available)
        new_rule = "AgStudio/arcgrav_language_engine/lint/rule_units/new_rule.py"
        self.assertIn("AgStudio/shared/software_testing/test_lint_rule_units.py",
                      impacted_tests((new_rule,)))

    def test_git_status_parser_preserves_rename_endpoints(self):
        self.assertEqual(
            changed_paths(
                b"M\0AgStudio/shared/core.py\0"
                b"R100\0AgStudio/old.py\0AgStudio/new.py\0"
            ),
            (
                "AgStudio/shared/core.py",
                "AgStudio/old.py",
                "AgStudio/new.py",
            ),
        )
        with self.assertRaises(ValueError):
            changed_paths(b"R100\0AgStudio/old.py\0")


if __name__ == "__main__":
    unittest.main()
