"""Completion diagnostics remain payload-free and separate from report authority."""
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from AgMark.gui.completion_diagnostics import completion_diagnostic_lines, retained_diagnostic_lines
from AgMark.gui.application.console_projection import _terminal_console_update
from AgMark.gui.application.session_boundary import PlanningSessionApplicationBoundary
from AgMark.gui.projection.workspace.reports import _reports_projection
from AgMark.shared.runtime.completion_diagnostics import completion_diagnostic, persist_completion_diagnostics
from AgMark.shared.software_testing.frontends.gui.test_retained_evidence_projection import _accepted_run


class CompletionDiagnosticPresentationTests(unittest.TestCase):
    def test_failed_publication_reaches_console_and_reports(self):
        rows = [completion_diagnostic("publication", "failed", PermissionError("secret prompt /private/credentials"))]
        boundary = object.__new__(PlanningSessionApplicationBoundary)
        boundary._session = SimpleNamespace(completion_record=lambda gid: {"diagnostics": rows} if gid == "generation-failed" else {})
        lines = boundary.completion_diagnostics("generation-failed")
        terminal = _accepted_run(generation_id="generation-failed")
        console = _terminal_console_update(terminal, lines)
        reports = _reports_projection(terminal, None, None, SimpleNamespace(), generation_state="report_failed", completion_diagnostics=lines)
        self.assertIn("Archive publication: failed", lines[0])
        self.assertIn("PermissionError", lines[0])
        self.assertIn(lines[0] + "\n", console.diagnostics)
        self.assertEqual(lines, reports.completion_diagnostics)
        self.assertIsNone(reports.report_id)
        self.assertFalse(reports.export_action and reports.export_action.available)
        self.assertNotIn("secret", str(console.diagnostics))
        self.assertNotIn("/private", str(reports))
        self.assertEqual((), boundary.completion_diagnostics("generation-other"))

    def test_arbitrary_diagnostic_payload_is_not_displayed(self):
        row = completion_diagnostic("publication", "failed", ValueError())
        for name in ("stage", "status", "error_class", "code"):
            with self.subTest(name=name):
                malformed = dict(row, **{name: "secret prompt /home/private token=123"})
                self.assertNotIn("secret", str(completion_diagnostic_lines([malformed])))

    def test_cleanup_operation_is_visible_without_raw_path(self):
        warning = completion_diagnostic("post_publication_cleanup", "warning", PermissionError("/private/path"))
        warning["operation"] = "publication_lock"
        text = "\n".join(completion_diagnostic_lines([warning]))
        self.assertIn("publication lock release", text)
        self.assertIn("PermissionError", text)
        self.assertNotIn("/private/path", text)

    def test_sidecar_cleanup_warning_does_not_rewrite_completion(self):
        completed = {"status": "complete", "diagnostics": [completion_diagnostic("publication", "passed")]}
        with TemporaryDirectory() as root:
            warning = completion_diagnostic("post_publication_cleanup", "warning", PermissionError("/private/path"))
            persist_completion_diagnostics(root, "generation-cleanup", completed["diagnostics"] + [warning])
            lines = retained_diagnostic_lines(root, "generation-cleanup", completed)
        self.assertEqual("complete", completed["status"])
        self.assertIn("Post-publication cleanup: warning", lines[-1])
        self.assertIn("published archive remains available", lines[-1])
        self.assertNotIn("/private/path", str(lines))

    def test_restart_discovers_publication_failure_without_archive_authority(self):
        from pathlib import Path
        from AgMark.gui.application.history import discover_history
        from AgMark.gui.application.console_projection import historical_console_update
        with TemporaryDirectory() as directory:
            root = Path(directory) / "AgMark" / "run_evidence"
            root.mkdir(parents=True)
            persist_completion_diagnostics(root, "generation-no-archive", [completion_diagnostic("publication", "failed", PermissionError("/private/path"))])
            run = discover_history(directory)["generation-no-archive"]
            self.assertTrue(run.diagnostic_only)
            self.assertFalse(run.can_delete)
            current, workspace = run.prepare_presentation()
            console = historical_console_update(run)
            self.assertFalse(current.start_benchmark_available)
            self.assertFalse(current.delete_run_available)
            self.assertEqual("unavailable", workspace.reports.generation_state)
            self.assertIsNone(workspace.reports.report_id)
            self.assertIsNone(workspace.reports.export_action)
            self.assertEqual((), workspace.artifacts.rows)

            self.assertIn("Archive publication: failed", str(console.diagnostics))
            self.assertIn("Archive publication: failed", str(workspace.reports.completion_diagnostics))
            with self.assertRaises(ValueError):
                run.delete()
