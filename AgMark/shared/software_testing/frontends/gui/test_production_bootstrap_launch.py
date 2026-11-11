"""Production bootstrap and launch conformance coverage for the desktop frontend."""

from __future__ import annotations

import builtins
import hashlib
from pathlib import Path
import json
import re
import unittest
from unittest.mock import MagicMock, patch

from AgMark.gui import startup
from AgMark.gui.application import (
    PlanningSessionApplicationBoundary,
    SharedApplicationProjector,
)
from AgMark.gui.composition import (
    RepositoryCompositionError,
    compose_repository_planning_session,
)
from AgMark.gui.diagnostics import EnvironmentDiagnosticEntry
from AgMark.gui.request_resolution import RepositoryApplicationRequestResolver
from AgMark.shared.application import (
    ApplicationAcceptanceError,
    ApplicationExecutionError,
)
from AgMark.gui.shell.window import (
    SidebarControlInputSnapshot,
    SidebarInputSnapshot,
    SidebarPrerequisiteDiagnosticProjection,
    SidebarProjection,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_GUI_ROOT = _REPOSITORY_ROOT / "AgMark" / "gui"


def _provider_free_intent(authority: object) -> SidebarInputSnapshot:
    benchmark = next(
        candidate
        for candidate in authority.benchmark_candidates
        if candidate.registration["registration_id"]
        == "arcgrav.authority-resolution.benchmark.core"
    )
    runner = next(
        source
        for source in authority.runner_sources
        if source.registration["registration_id"]
        == "arcgrav.mock-model.runner"
    )
    return SidebarInputSnapshot(
        benchmark=(
            f"{benchmark.registration['registration_id']}@"
            f"{benchmark.registration['registration_version']}"
        ),
        runner=(
            f"{runner.registration['registration_id']}@"
            f"{runner.registration['registration_version']}"
        ),
        model="mock-base::scenario:completed",
        credential="",
        temperature=None,
        max_tokens=None,
        additional_controls=(),
    )


def _scope_planning_probe(source: object, control_values: object) -> dict[str, object]:
    """Supply planning identity for projection tests that block before execution."""
    registration = source.registration
    if registration["registration_id"] != "arcgrav.mock-model.runner":
        raise AssertionError("scope fixture requires the registered mock composition")
    controls = dict(control_values)
    return {
        "status": "ready",
        "provider_submitted": False,
        "resolved_controls": controls,
        "provider_runtime": {
            "runtime_id": registration["registration_id"],
            "runtime_version": "scope-fixture-1.0",
            "provider": "AgMark Mock Model",
            "access_method": "local_process",
            "model": controls["model_id"],
        },
    }


class ProductionBootstrapLaunchTests(unittest.TestCase):
    def test_root_has_only_named_windows_launchers(self):
        self.assertEqual(
            {"Windows_Run.bat", "Windows_Setup.bat"},
            {path.name for path in _GUI_ROOT.parent.glob("*.bat")},
        )
        self.assertFalse((_GUI_ROOT.parent / "run_gui.pyw").exists())

    def test_production_startup_has_no_version_authority_dependency(self) -> None:
        self.assertFalse((_GUI_ROOT.parent / "VERSION").exists())
        self.assertFalse(hasattr(startup, "production_application_version"))
        source = (_GUI_ROOT / "startup.py").read_text(encoding="utf-8")
        self.assertNotIn("setApplicationVersion", source)
        self.assertNotIn("application_version", source)

    def test_production_startup_activates_design_system_before_desktop_composition(self) -> None:
        source = (_GUI_ROOT / "startup.py").read_text(encoding="utf-8")

        activation = "apply_application_theme(application)"
        composition = "desktop = BenchmarkDesktopApplication.from_repository_authority"
        self.assertIn(activation, source)
        self.assertIn(composition, source)
        self.assertLess(source.index(activation), source.index(composition))

    def test_production_startup_applies_one_arcgrav_icon_to_application_and_desktop(self) -> None:
        source = (_GUI_ROOT / "startup.py").read_text(encoding="utf-8")

        icon_build = "application_icon = arcgrav_application_icon()"
        application_assignment = "application.setWindowIcon(application_icon)"
        composition = "desktop = BenchmarkDesktopApplication.from_repository_authority"
        desktop_assignment = "application_icon=application_icon,"

        for required_source in (
            icon_build,
            application_assignment,
            composition,
            desktop_assignment,
        ):
            self.assertIn(required_source, source)

        self.assertLess(source.index(icon_build), source.index(application_assignment))
        self.assertLess(source.index(application_assignment), source.index(composition))
        self.assertGreater(
            source.index(desktop_assignment),
            source.index(composition),
        )

    def test_production_dependency_manifest_is_gui_owned_and_test_independent(self) -> None:
        requirements = (_GUI_ROOT / "requirements.txt").read_text(encoding="utf-8")
        dependencies = tuple(
            line.strip()
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )

        self.assertTrue(
            any(value.startswith("PySide6==") for value in dependencies),
            "production GUI dependencies must pin PySide6",
        )
        self.assertTrue(
            all(
                "shared/software_testing" not in value.replace("\\", "/")
                for value in dependencies
            )
        )

    def test_setup_bootstraps_supported_isolated_runtime_without_credential_mutation(
        self,
    ) -> None:
        setup_text = (_GUI_ROOT.parent / "Windows_Setup.bat").read_text(encoding="utf-8")
        normalized = setup_text.replace("\\", "/")
        variables = {
            match.group(1).upper()
            for match in re.finditer(
                r'(?im)^\s*set\s+"([^=]+)=',
                setup_text,
            )
        }

        self.assertIn("sys.version_info.minor in (10, 11, 12, 13, 14)", setup_text)
        self.assertIn('gui\\setup_environment.py', setup_text)
        self.assertNotIn("shared/software_testing", normalized)
        self.assertNotIn("setx ", setup_text.lower())
        self.assertEqual({"SCRIPT_DIR", "PYTHON_EXE"}, variables)
        self.assertIn('"%PYTHON_EXE%" -B ', setup_text)
        self.assertNotIn("python -B -c", setup_text)
        self.assertNotIn(":resolve_python", setup_text)

    def test_module_and_batch_launchers_converge_on_production_module(
        self,
    ) -> None:
        module_entry = (_GUI_ROOT / "__main__.py").read_text(encoding="utf-8")
        batch_entry = (_GUI_ROOT.parent / "Windows_Run.bat").read_text(encoding="utf-8")

        self.assertIn("from AgMark.gui.startup import main", module_entry)
        self.assertIn("-m AgMark.gui", batch_entry)
        self.assertIn("Runtime\\.venv\\Scripts\\python.exe", batch_entry)
        self.assertIn("Runtime\\__pycache__", batch_entry)

    def test_supported_windows_operability_harness_tracks_required_execution_surface(
        self,
    ) -> None:
        harness = Path(__file__).with_name("verify_windows_operability.ps1").read_text(
            encoding="utf-8"
        )

        for required_surface in (
            "Windows_Setup.bat",
            "Windows_Run.bat",
            "python -m AgMark.gui",
        ):
            self.assertIn(required_surface, harness)

        self.assertIn("windows_operability_evidence.json", harness)
        self.assertIn("Get-FileHash -Algorithm SHA256", harness)
        self.assertIn("[System.Text.UTF8Encoding]::new($false)", harness)
        self.assertIn("[System.IO.File]::WriteAllText", harness)
        self.assertIn("Move-Item -LiteralPath $VenvRoot", harness)
        self.assertIn("finally {", harness)
        self.assertNotIn("run_gui.pyw", harness)
        self.assertNotIn("pythonw", harness)

    def test_committed_supported_windows_evidence_preserves_observed_hashes(
        self,
    ) -> None:
        evidence_path = Path(__file__).with_name("windows_operability_evidence.json")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))

        self.assertEqual("arcgrav.frontend.windows-operability/v1", evidence["schema"])
        self.assertTrue(evidence["passed"])
        self.assertIsNone(evidence["failure"])

        expected_checks = {
            "setup.bat",
            "python -m AgMark.gui",
            "run_gui.bat",
            "run_gui.pyw",
            "run_gui.bat missing-environment failure",
            "run_gui.pyw missing-environment failure",
        }
        checks = evidence["checks"]
        current_checks = {
            "Windows_Setup.bat", "python -m AgMark.gui", "Windows_Run.bat",
            "Windows_Run.bat missing-environment failure",
        }
        self.assertIn({item["name"] for item in checks}, (expected_checks, current_checks))
        self.assertTrue(all(item["passed"] is True for item in checks))

        expected_sources = {
            "AgMark\\VERSION",
            "AgMark\\gui\\requirements.txt",
            "AgMark\\gui\\setup.bat",
            "AgMark\\gui\\run_gui.bat",
            "AgMark\\gui\\run_gui.pyw",
            "AgMark\\gui\\startup.py",
            "AgMark\\gui\\__main__.py",
        }
        current_sources = {path.replace("AgMark\\gui\\setup.bat", "AgMark\\setup.bat")
                           .replace("AgMark\\gui\\run_gui.bat", "AgMark\\run_gui.bat")
                           .replace("AgMark\\gui\\run_gui.pyw", "AgMark\\run_gui.pyw") for path in expected_sources}
        current_sources.add("AgMark\\gui\\setup_environment.py")
        runtime_sources = current_sources | {"AgMark\\gui\\runtime_environment.py"}
        aligned_sources = {
            path.replace("AgMark\\setup.bat", "AgMark\\Windows_Setup.bat")
                .replace("AgMark\\run_gui.bat", "AgMark\\Windows_Run.bat")
            for path in runtime_sources if not path.endswith("run_gui.pyw")
        }
        unversioned_sources = aligned_sources - {"AgMark\\VERSION"}
        self.assertIn(set(evidence["source_sha256"]),
                      (expected_sources, current_sources, runtime_sources, aligned_sources, unversioned_sources))
        for relative_path, digest in evidence["source_sha256"].items():
            self.assertEqual(64, len(digest))
            self.assertTrue(all(character in "0123456789abcdef" for character in digest))
            if set(evidence["source_sha256"]) == unversioned_sources:
                source = (_REPOSITORY_ROOT / relative_path.replace("\\", "/")).read_bytes()
                normalized = source.replace(b"\r\n", b"\n")
                self.assertIn(digest, {hashlib.sha256(raw).hexdigest() for raw in
                    (source, normalized, normalized.replace(b"\n", b"\r\n"))})
        # Earlier evidence is historical. Runtime relocation requires a new native
        # Windows run, never fabricated replacement source hashes.

        # Retained Windows evidence records the exact bytes observed by that run.
        # It is not rewritten to make historical CRLF observations equivalent to
        # the repository's canonical LF identities.

    def test_invalid_runtime_stops_before_desktop_creation(self) -> None:
        with (
            patch.object(startup, "require_managed_runtime", side_effect=RuntimeError("invalid runtime")),
            patch.object(startup, "create_production_application") as create,
            patch.object(startup, "present_startup_failure") as present,
        ):
            self.assertEqual(1, startup.main([]))
        create.assert_not_called()
        present.assert_called_once()

    def test_production_main_validates_runtime_before_event_loop(self) -> None:
        application = MagicMock()
        application.exec.return_value = 0
        desktop = MagicMock()

        with (
            patch.object(startup, "require_managed_runtime") as admission,
            patch.object(
                startup,
                "create_production_application",
                return_value=(application, desktop),
            ),
        ):
            self.assertEqual(0, startup.main([]))

        admission.assert_called_once_with(_GUI_ROOT.parent)
        desktop.show.assert_called_once_with()
        application.exec.assert_called_once_with()

    def test_crash_diagnostics_have_no_interpreter_or_output_override(self) -> None:
        source = (_GUI_ROOT / "diagnose_crash.ps1").read_text(encoding="utf-8")
        self.assertIn('".venv/Scripts/python.exe"', source)
        self.assertIn("require_managed_runtime(root)", source)
        self.assertIn('Join-Path $RuntimeRoot "diagnostics"', source)

    def test_startup_reports_unavailable_gui_runtime_actionably(self) -> None:
        real_import = builtins.__import__

        def import_without_pyside6(name, *args, **kwargs):
            if name == "PySide6" or name.startswith("PySide6."):
                raise ImportError("PySide6 unavailable for test")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_pyside6):
            with self.assertRaisesRegex(
                RuntimeError,
                r"Run AgMark\\Windows_Setup\.bat",
            ):
                startup.create_production_application([])

    def test_startup_reports_invalid_repository_authority_actionably(self) -> None:
        error = RepositoryCompositionError("invalid registration authority")
        with (
            patch.object(startup, "require_managed_runtime"),
            patch.object(
                startup,
                "create_production_application",
                side_effect=error,
            ),
            patch.object(startup, "present_startup_failure") as present,
        ):
            self.assertEqual(1, startup.main([]))

        present.assert_called_once()
        diagnostic = present.call_args.args[0]
        self.assertIn("invalid registration authority", diagnostic.details)
        self.assertIn("registration files", diagnostic.remediation)
        self.assertFalse(present.call_args.kwargs["native"])

    def test_sidebar_prerequisite_scope_only_blocks_matching_plan_transition(
        self,
    ) -> None:
        planning = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="planning-boundary",
            message="Planning identity is unresolved.",
            remediation="Resolve the canonical planning identity.",
            operation="planning",
        )
        execution = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="runner-authentication",
            message="Execution authentication is unresolved.",
            remediation="Restore execution authentication.",
            operation="execution",
        )

        planning_blocked = SidebarProjection(
            build_plan_available=True,
            prerequisite_diagnostics=(planning,),
        )
        execution_pending = SidebarProjection(
            build_plan_available=True,
            prerequisite_diagnostics=(execution,),
        )

        self.assertFalse(planning_blocked.build_plan_effectively_available)
        self.assertTrue(execution_pending.build_plan_effectively_available)
        self.assertEqual(
            execution_pending.planning_prerequisite_diagnostics,
            (),
        )
        self.assertEqual(execution.scope_label, "Execution readiness")

    def test_prepared_runtime_readiness_reclassifies_to_execution(self) -> None:
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        boundary = PlanningSessionApplicationBoundary(
            session=composition.session,
            request_resolver=RepositoryApplicationRequestResolver(
                composition.authority, runner_planning_probe=_scope_planning_probe,
            ),
        )
        boundary.discover()
        intent = _provider_free_intent(composition.authority)
        plan = boundary.build_plan(intent)
        self.assertEqual(plan, composition.session.prepared_plan)

        runtime = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="runner-authentication",
            message="Authentication was required for planning discovery and is now unavailable.",
            remediation="Restore the accepted runner authentication context before execution.",
            operation="planning",
        )
        discovery = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="runner-model-discovery",
            message="Accepted model discovery can no longer be revalidated.",
            remediation="Restore current model discovery before execution.",
            operation="planning",
        )
        projector = SharedApplicationProjector(
            boundary,
            sidebar_template=SidebarProjection(
                runner_options=("arcgrav.mock-model.runner@1.0.0",),
                selected_runner="arcgrav.mock-model.runner@1.0.0",
                prerequisite_diagnostics=(runtime, discovery),
            ),
            workspace_projector=lambda *_args: None,
        )

        projection = projector.prerequisite_projection()
        self.assertEqual((), projection.unresolved_for("planning"))
        self.assertEqual(
            ("runner-authentication", "runner-model-discovery"),
            tuple(
                state.prerequisite_id
                for state in projection.unresolved_for("execution")
            ),
        )

        boundary.set_prerequisite_projection(projection)
        snapshot = boundary.accept_plan()
        update = projector("accept_plan", snapshot, object())
        self.assertIsNotNone(update.current_run)
        self.assertFalse(update.current_run.start_benchmark_available)
        with self.assertRaises(ApplicationExecutionError):
            boundary.start_benchmark()
        self.assertEqual(plan, composition.session.prepared_plan)
        self.assertEqual(snapshot, composition.session.accepted_snapshot)

    def test_operation_scoped_prerequisites_preserve_prepared_authority(
        self,
    ) -> None:
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        resolver = RepositoryApplicationRequestResolver(
            composition.authority, runner_planning_probe=_scope_planning_probe,
        )
        boundary = PlanningSessionApplicationBoundary(
            session=composition.session,
            request_resolver=resolver,
        )
        discovery = boundary.discover()
        intent = _provider_free_intent(composition.authority)
        acceptance = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="acceptance-review",
            message="Acceptance review is unresolved.",
            remediation="Complete the acceptance review.",
            operation="acceptance",
        )
        execution = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="runner-authentication",
            message="Execution authentication is unresolved.",
            remediation="Restore execution authentication.",
            operation="execution",
        )
        blocked_acceptance = SharedApplicationProjector(
            boundary,
            sidebar_template=SidebarProjection(
                runner_options=("arcgrav.mock-model.runner@1.0.0",),
                selected_runner="arcgrav.mock-model.runner@1.0.0",
                prerequisite_diagnostics=(acceptance, execution),
            ),
            workspace_projector=lambda *_args: None,
        )

        discovery_update = blocked_acceptance("discover", discovery, object())
        self.assertTrue(discovery_update.clear_current_run)
        self.assertIsNone(discovery_update.current_run)

        boundary.set_prerequisite_projection(
            blocked_acceptance.prerequisite_projection(intent)
        )
        plan = boundary.build_plan(intent)
        self.assertEqual(plan, composition.session.prepared_plan)

        planned_update = blocked_acceptance("build_plan", plan, object())
        self.assertIsNotNone(planned_update.current_run)
        self.assertEqual(plan.run_plan_id, planned_update.current_run.run_identity)
        self.assertFalse(planned_update.current_run.accept_plan_available)
        self.assertTrue(planned_update.sidebar.build_plan_effectively_available)
        self.assertTrue(planned_update.environment.has_blockers)
        with self.assertRaises(ApplicationAcceptanceError):
            boundary.accept_plan()
        self.assertEqual(plan, composition.session.prepared_plan)
        self.assertIsNone(composition.session.accepted_snapshot)

        execution_pending = SharedApplicationProjector(
            boundary,
            sidebar_template=SidebarProjection(
                runner_options=("arcgrav.mock-model.runner@1.0.0",),
                selected_runner="arcgrav.mock-model.runner@1.0.0",
                prerequisite_diagnostics=(execution,),
            ),
            workspace_projector=lambda *_args: None,
        )
        boundary.set_prerequisite_projection(
            execution_pending.prerequisite_projection()
        )
        snapshot = boundary.accept_plan()
        accepted_update = execution_pending("accept_plan", snapshot, object())

        self.assertIsNotNone(accepted_update.current_run)
        self.assertEqual(plan.run_plan_id, accepted_update.current_run.run_identity)
        self.assertEqual(
            plan.execution_boundary_fingerprint,
            accepted_update.current_run.execution_boundary.boundary_fingerprint,
        )
        self.assertFalse(accepted_update.current_run.accept_plan_available)
        self.assertFalse(accepted_update.current_run.start_benchmark_available)
        self.assertTrue(accepted_update.sidebar.build_plan_effectively_available)
        self.assertTrue(accepted_update.environment.has_blockers)
        with self.assertRaises(ApplicationExecutionError):
            boundary.start_benchmark()
        self.assertEqual(plan, composition.session.prepared_plan)
        self.assertEqual(snapshot, composition.session.accepted_snapshot)

        unblocked = SharedApplicationProjector(
            boundary,
            sidebar_template=SidebarProjection(runner_options=("arcgrav.mock-model.runner@1.0.0",), selected_runner="arcgrav.mock-model.runner@1.0.0"),
            workspace_projector=lambda *_args: None,
            environment_entries=(
                EnvironmentDiagnosticEntry(
                    source="Startup",
                    state="warning",
                    summary="Informational startup warning.",
                ),
            ),
        )
        unblocked_update = unblocked("accept_plan", snapshot, object())
        self.assertTrue(unblocked_update.current_run.start_benchmark_available)
        self.assertTrue(unblocked_update.sidebar.build_plan_effectively_available)
        self.assertIsNone(unblocked_update.connectivity)
        self.assertEqual(
            ("Plan accepted", "success"),
            unblocked_update.application_status,
        )
        self.assertIsNotNone(unblocked_update.environment)
        self.assertFalse(unblocked_update.environment.has_blockers)
        self.assertIn(
            "Informational startup warning.",
            unblocked_update.environment.render(),
        )


if __name__ == "__main__":
    unittest.main()
