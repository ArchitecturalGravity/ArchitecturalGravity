"""Standalone Golden reads the separate registered source without stdin or args."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from AgMark.Authority_Resolution_Benchmark.Legacy_Content.Authority_Resolution_Benchmark import (
    DEFAULT_SOURCE_PATH,
    run_orchestration,
)


_PACKAGE = Path(__file__).resolve().parents[4] / "Authority_Resolution_Benchmark"
_GOLDEN = _PACKAGE / "Legacy_Content/Authority_Resolution_Benchmark.py"


class GoldenDefaultSourceTests(unittest.TestCase):
    def test_no_arguments_reads_case_from_unrelated_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, str(_GOLDEN)], cwd=directory,
                input=b"stdin is not the selected source", capture_output=True, check=True,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(asdict(run_orchestration(DEFAULT_SOURCE_PATH.read_text())), result)
        self.assertEqual(8, result["records"][0]["value"])
        self.assertEqual(
            {"processed": 4, "resolved": 3, "findings": 5, "validated": True},
            result["execution"],
        )

    def test_copied_program_uses_its_adjacent_case_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "benchmark"
            program = package / "Legacy_Content/Authority_Resolution_Benchmark.py"
            source = package / "cases/v1.0.0/arb-core-001.json"
            program.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            shutil.copyfile(_GOLDEN, program)
            case = json.loads(DEFAULT_SOURCE_PATH.read_bytes())
            case["records"][0]["value"] = 81
            source.write_text(json.dumps(case), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(program)], cwd=directory,
                capture_output=True, check=True,
            )
            self.assertEqual(81, json.loads(completed.stdout)["records"][0]["value"])
            for contents in (None, b"\xff"):
                with self.subTest(contents=contents):
                    if contents is None:
                        source.unlink()
                    else:
                        source.write_bytes(contents)
                    failed = subprocess.run(
                        [sys.executable, str(program)], cwd=directory, capture_output=True,
                    )
                    self.assertNotEqual(0, failed.returncode)
                    self.assertEqual(b"", failed.stdout)

    def test_processing_api_still_requires_explicit_source(self) -> None:
        with self.assertRaises(TypeError):
            run_orchestration()


if __name__ == "__main__":
    unittest.main()
