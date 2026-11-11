"""Echo startup diagnostics preserve safe guidance without exception payloads."""
import unittest

from AgMark.gui.application.runner_testing import (
    _CAPTURE_SETUP_HINTS,
    _runner_test_diagnostics,
    _runner_test_environment_entry,
    _runner_test_failure,
)
from AgMark.gui.application.contracts import RunnerTestResult


class RunnerTestSafeDiagnosticsTests(unittest.TestCase):
    def test_setup_stage_codes_produce_fixed_actionable_echo_guidance(self):
        for code, hint in _CAPTURE_SETUP_HINTS.items():
            with self.subTest(code=code):
                diagnostics = _runner_test_diagnostics({"attempts": [{"error_code": code,
                    "error_message": "PRIVATE credential=/private/path", "details": {"secret": "PRIVATE"}}]})
                entry = _runner_test_environment_entry(RunnerTestResult(
                    selected_runner="openai.codex-cli@1.0.0", terminal_status="failed",
                    diagnostics=diagnostics))
                self.assertIn("Submitted: no", entry.details)
                self.assertIn(code, entry.details)
                self.assertIn(hint, entry.details)
                self.assertNotIn("PRIVATE", entry.details)
                self.assertNotIn("/private/path", entry.details)

    def test_outer_setup_exceptions_never_echo_sensitive_messages_or_paths(self):
        for error_type in (PermissionError, FileNotFoundError, TimeoutError, ValueError, TypeError, RuntimeError):
            with self.subTest(error=error_type.__name__):
                result = _runner_test_failure(selected_runner="openai.codex-cli@1.0.0",
                    error=error_type("PRIVATE-SECRET in /sensitive/path"))
                entry = _runner_test_environment_entry(result)
                self.assertFalse(result.submitted)
                self.assertFalse(result.passed)
                self.assertNotIn("PRIVATE-SECRET", entry.details)
                self.assertNotIn("/sensitive/path", entry.details)
                self.assertTrue(result.diagnostics)

    def test_genuine_isolation_failure_is_not_reclassified_as_capture_failure(self):
        diagnostics = _runner_test_diagnostics({"attempts": [{"error_code": "codex_cli_isolation_failed"}]})
        self.assertEqual(("codex_cli_isolation_failed",), diagnostics)
