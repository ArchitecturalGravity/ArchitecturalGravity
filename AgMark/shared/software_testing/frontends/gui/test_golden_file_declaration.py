"""Generic Golden dependency resolution for registered file inputs."""

from __future__ import annotations

import copy
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from AgMark.gui.composition import RepositoryCompositionError
from AgMark.gui.requests.execution import _golden_declaration


class GoldenFileDeclarationTests(unittest.TestCase):
    def _resources(self, root: Path):
        package = root / "ExampleBenchmark"
        package.mkdir()
        (package / "cases").mkdir()
        (package / "golden.py").write_bytes(b"print('example')\n")
        (package / "cases/source.json").write_bytes(b'{"records": []}\n')
        artifacts = []
        for artifact_id, reference in (
            ("golden-source", "ExampleBenchmark/golden.py"),
            ("case-input", "ExampleBenchmark/cases/source.json"),
        ):
            artifacts.append({
                "artifact_id": artifact_id,
                "reference": reference,
                "sha256": "sha256:" + sha256((root / reference).read_bytes()).hexdigest(),
                "availability": "retained",
            })
        registration = {"registration_version": "2.0.0", "implementation_artifacts": artifacts}
        selected = {"golden_authority": {
            "artifact_id": "golden-source",
            "implementation_artifact_ids": ["golden-source", "case-input"],
            "input_transport": "registered_file",
            "input_artifact_id": "case-input",
            "requires_successful_nonempty_retained_stdout_before_treatments": True,
        }}
        return registration, selected

    def _resolve(self, root, registration, selected):
        return _golden_declaration(
            root, "ExampleBenchmark", registration, selected,
            environment_family="native", runtime_executable=Path(sys.executable),
        )[0]

    def test_selected_input_and_dependency_identities_reach_runtime(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            registration, selected = self._resources(root)
            declaration = self._resolve(root, registration, selected)
            self.assertEqual("golden-source", declaration.golden_implementation.id)
            self.assertEqual("golden-source", declaration.entry_artifact_id)
            self.assertEqual("registered_file", declaration.input_transport)
            self.assertEqual("case-input", declaration.input_artifact_id)
            self.assertEqual(
                {"golden-source": "golden.py", "case-input": "cases/source.json"},
                {item.artifact_id: item.relative_path for item in declaration.artifacts},
            )

    def test_legacy_stdin_declaration_keeps_single_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            registration, _ = self._resources(root)
            declaration = self._resolve(
                root, registration, {"golden_authority": {"artifact_id": "golden-source"}}
            )
            self.assertEqual("stdin", declaration.input_transport)
            self.assertIsNone(declaration.input_artifact_id)
            self.assertEqual(("golden-source",), tuple(item.artifact_id for item in declaration.artifacts))

    def test_undeclared_or_changed_input_file_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            registration, selected = self._resources(root)
            undeclared = copy.deepcopy(selected)
            undeclared["golden_authority"]["implementation_artifact_ids"] = ["golden-source"]
            with self.assertRaisesRegex(RepositoryCompositionError, "declared golden dependency"):
                self._resolve(root, registration, undeclared)
            (root / "ExampleBenchmark/cases/source.json").write_bytes(b"changed")
            with self.assertRaisesRegex(RepositoryCompositionError, "drifted"):
                self._resolve(root, registration, selected)


if __name__ == "__main__":
    unittest.main()
