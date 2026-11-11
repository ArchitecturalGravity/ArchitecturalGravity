"""Coverage for production environment diagnostics without test-harness imports."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

from AgMark.gui.diagnostics import (
    ApplicationEnvironmentProjection,
    EnvironmentDiagnosticEntry,
    environment_failure_entry,
)


class EnvironmentDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_imports_without_developer_test_support(self) -> None:
        process = subprocess.run(
            [sys.executable, "-c", """
import importlib.abc
import sys

class RejectTestSupport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        for prefix in (
            "AgMark.shared.software_testing",
            "AgMark.shared.self_testing",
        ):
            if fullname == prefix or fullname.startswith(prefix + "."):
                raise AssertionError("production imported test support: " + fullname)

sys.meta_path.insert(0, RejectTestSupport())
from AgMark.gui import diagnostics
assert not hasattr(diagnostics, "run_frontend_self_test")
assert not hasattr(diagnostics, "FrontendSelfTestResult")
assert not hasattr(diagnostics, "FrontendSelfTestError")
assert diagnostics.environment_failure_entry(RuntimeError("fixture")).blocking
"""],
            cwd=Path(__file__).resolve().parents[5],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, process.returncode, process.stderr or process.stdout)

    def test_environment_projection_is_generation_free_and_redacts_common_secret_text(self) -> None:
        entry = environment_failure_entry(
            RuntimeError(
                "token=visible-secret Authorization: Bearer second-secret"
            ),
            source="Discovery",
        )
        projection = ApplicationEnvironmentProjection(entries=(entry,))

        rendered = projection.render()
        self.assertTrue(projection.has_blockers)
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("visible-secret", rendered)
        self.assertNotIn("second-secret", rendered)

        informational = EnvironmentDiagnosticEntry(
            source="Configuration",
            state="info",
            summary="Non-secret configuration is available.",
        )
        self.assertFalse(
            ApplicationEnvironmentProjection(entries=(informational,)).has_blockers
        )


if __name__ == "__main__":
    unittest.main()
