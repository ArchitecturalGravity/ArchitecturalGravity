"""Regression tests for dependency-aware centralized CI selection."""

# This module also serves as the minimal end-to-end CI selection smoke target.

from __future__ import annotations

import json
import unittest

from AgMark.shared.software_testing.select_tests import (
    Change,
    Snapshot,
    classify_changes,
)


_ROOT = "AgMark/shared/software_testing"
_PRODUCTION_ROOT = "AgMark"


def _snapshot(
    sources: dict[str, str],
    *,
    text_sources: dict[str, str] | None = None,
    extra_paths: tuple[str, ...] = (),
) -> Snapshot:
    text = dict(text_sources or {})
    return Snapshot(
        all_paths=set(sources) | set(text) | set(extra_paths),
        python_sources=dict(sources),
        text_sources=text,
    )


class ImpactSelectionTests(unittest.TestCase):
    def test_changed_test_runs_only_itself(self) -> None:
        first = f"{_ROOT}/runtime/test_first.py"
        second = f"{_ROOT}/runtime/test_second.py"
        snapshot = _snapshot(
            {
                first: "import unittest\n",
                second: "import unittest\n",
            }
        )

        selected = classify_changes([Change("M", first)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual({first}, selected.tests)

    def test_rootless_directory_path_is_not_accepted(self) -> None:
        canonical = f"{_ROOT}/runtime/test_first.py"
        rootless = "shared/software_testing/runtime/test_first.py"
        snapshot = _snapshot({canonical: "import unittest\n"})

        selected = classify_changes([Change("M", rootless)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual(set(), selected.tests)

    def test_production_python_dependency_selects_dependent_frontend_test(self) -> None:
        production = f"{_PRODUCTION_ROOT}/gui/composition.py"
        dependent = (
            f"{_ROOT}/frontends/gui/"
            "test_production_repository_composition.py"
        )
        unrelated = f"{_ROOT}/frontends/gui/test_unrelated.py"
        snapshot = _snapshot(
            {
                production: "VALUE = 1\n",
                dependent: "from AgMark.gui.composition import VALUE\n",
                unrelated: "import unittest\n",
            }
        )

        selected = classify_changes([Change("M", production)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual({dependent}, selected.tests)

    def test_unmapped_production_python_change_fails_closed_to_full_suite(self) -> None:
        production = f"{_PRODUCTION_ROOT}/gui/unmapped.py"
        test_path = f"{_ROOT}/frontends/gui/test_unrelated.py"
        snapshot = _snapshot(
            {
                production: "VALUE = 1\n",
                test_path: "import unittest\n",
            }
        )

        selected = classify_changes([Change("M", production)], snapshot)

        self.assertTrue(selected.full)
        self.assertEqual(set(), selected.tests)

    def test_python_dependency_selects_only_dependent_test(self) -> None:
        helper = f"{_ROOT}/runtime/helper.py"
        dependent = f"{_ROOT}/runtime/test_dependent.py"
        unrelated = f"{_ROOT}/runtime/test_unrelated.py"
        snapshot = _snapshot(
            {
                helper: "VALUE = 1\n",
                dependent: (
                    "from AgMark.shared.software_testing.runtime.helper "
                    "import VALUE\n"
                ),
                unrelated: "import unittest\n",
            }
        )

        selected = classify_changes([Change("M", helper)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual({dependent}, selected.tests)

    def test_package_init_relative_reexport_selects_facade_consumer(self) -> None:
        implementation = f"{_PRODUCTION_ROOT}/shared/runtime/artifacts/storage.py"
        package_init = f"{_PRODUCTION_ROOT}/shared/runtime/artifacts/__init__.py"
        dependent = f"{_ROOT}/runtime/test_artifact_storage.py"
        unrelated = f"{_ROOT}/runtime/test_unrelated.py"
        snapshot = _snapshot(
            {
                implementation: "VALUE = 1\n",
                package_init: "from .storage import VALUE\n",
                dependent: (
                    "from AgMark.shared.runtime.artifacts import VALUE\n"
                ),
                unrelated: "import unittest\n",
            }
        )

        selected = classify_changes([Change("M", implementation)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual({dependent}, selected.tests)

    def test_package_init_parent_relative_import_resolves_from_package(self) -> None:
        implementation = f"{_PRODUCTION_ROOT}/shared/runtime/model.py"
        package_init = f"{_PRODUCTION_ROOT}/shared/runtime/artifacts/__init__.py"
        dependent = f"{_ROOT}/runtime/test_artifacts.py"
        snapshot = _snapshot(
            {
                implementation: "VALUE = 1\n",
                package_init: "from ..model import VALUE\n",
                dependent: (
                    "from AgMark.shared.runtime.artifacts import VALUE\n"
                ),
            }
        )

        selected = classify_changes([Change("M", implementation)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual({dependent}, selected.tests)

    def test_transitive_dependency_selects_consumer_test(self) -> None:
        helper = f"{_ROOT}/runtime/helper.py"
        facade = f"{_ROOT}/runtime/facade.py"
        test_path = f"{_ROOT}/end_to_end/test_runtime.py"
        snapshot = _snapshot(
            {
                helper: "VALUE = 1\n",
                facade: (
                    "from AgMark.shared.software_testing.runtime.helper "
                    "import VALUE\n"
                ),
                test_path: (
                    "from AgMark.shared.software_testing.runtime.facade "
                    "import VALUE\n"
                ),
            }
        )

        selected = classify_changes([Change("M", helper)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual({test_path}, selected.tests)

    def test_deleted_source_uses_base_dependency_graph(self) -> None:
        helper = f"{_ROOT}/runtime/helper.py"
        test_path = f"{_ROOT}/runtime/test_helper.py"
        base = _snapshot(
            {
                helper: "VALUE = 1\n",
                test_path: (
                    "from AgMark.shared.software_testing.runtime.helper "
                    "import VALUE\n"
                ),
            }
        )
        head = _snapshot({test_path: "import unittest\n"})

        selected = classify_changes(
            [Change("D", helper)],
            head,
            base,
        )

        self.assertFalse(selected.full)
        self.assertEqual({test_path}, selected.tests)

    def test_unknown_non_python_change_falls_back_to_full_suite(self) -> None:
        changed = f"{_ROOT}/runtime/fixture.json"
        test_path = f"{_ROOT}/runtime/test_fixture.py"
        snapshot = _snapshot(
            {test_path: "import unittest\n"},
            extra_paths=(changed,),
        )

        selected = classify_changes([Change("M", changed)], snapshot)

        self.assertTrue(selected.full)
        self.assertEqual(set(), selected.tests)

    def test_manifest_can_cover_dynamic_dependency(self) -> None:
        manifest_path = f"{_ROOT}/runtime/ci-impact.json"
        fixture = f"{_ROOT}/runtime/fixtures/example.json"
        target = f"{_ROOT}/runtime/test_fixture.py"
        other = f"{_ROOT}/runtime/test_other.py"
        manifest = json.dumps(
            {
                "rules": [
                    {
                        "changed": ["fixtures/**"],
                        "run": ["test_fixture.py"],
                        "covers": True,
                    }
                ]
            }
        )
        snapshot = _snapshot(
            {
                target: "import unittest\n",
                other: "import unittest\n",
            },
            text_sources={manifest_path: manifest},
            extra_paths=(fixture,),
        )

        selected = classify_changes([Change("M", fixture)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual({target}, selected.tests)

    def test_selection_policy_change_runs_full_suite(self) -> None:
        selector = f"{_ROOT}/select_tests.py"
        snapshot = _snapshot(
            {
                selector: "# selector\n",
                f"{_ROOT}/runtime/test_one.py": "import unittest\n",
            }
        )

        selected = classify_changes([Change("M", selector)], snapshot)

        self.assertTrue(selected.full)

    def test_workgraph_change_is_ci_neutral(self) -> None:
        workgraph = f"{_ROOT}/runtime/WORKGRAPH.md"
        snapshot = _snapshot(
            {f"{_ROOT}/runtime/test_one.py": "import unittest\n"},
            extra_paths=(workgraph,),
        )

        selected = classify_changes([Change("M", workgraph)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual(set(), selected.tests)

    def test_markdown_change_anywhere_under_benchmarking_is_ci_neutral(self) -> None:
        specification = f"{_PRODUCTION_ROOT}/gui/SPECIFICATION.md"
        snapshot = _snapshot(
            {f"{_ROOT}/runtime/test_one.py": "import unittest\n"},
            extra_paths=(specification,),
        )

        selected = classify_changes([Change("M", specification)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual(set(), selected.tests)

    def test_text_change_anywhere_under_benchmarking_is_ci_neutral(self) -> None:
        developer_tree = f"{_PRODUCTION_ROOT}/DEVTREE.txt"
        snapshot = _snapshot(
            {f"{_ROOT}/runtime/test_one.py": "import unittest\n"},
            extra_paths=(developer_tree,),
        )

        selected = classify_changes([Change("M", developer_tree)], snapshot)

        self.assertFalse(selected.full)
        self.assertEqual(set(), selected.tests)

    def test_mixed_python_and_markdown_change_selects_only_python_impact(self) -> None:
        production = f"{_PRODUCTION_ROOT}/gui/composition.py"
        specification = f"{_PRODUCTION_ROOT}/gui/SPECIFICATION.md"
        dependent = f"{_ROOT}/frontends/gui/test_production_repository_composition.py"
        unrelated = f"{_ROOT}/frontends/gui/test_unrelated.py"
        snapshot = _snapshot(
            {
                production: "VALUE = 1\n",
                dependent: "from AgMark.gui.composition import VALUE\n",
                unrelated: "import unittest\n",
            },
            extra_paths=(specification,),
        )

        selected = classify_changes(
            [
                Change("M", production),
                Change("M", specification),
            ],
            snapshot,
        )

        self.assertFalse(selected.full)
        self.assertEqual({dependent}, selected.tests)


if __name__ == "__main__":
    unittest.main()
