"""Production repository readiness coverage for the desktop frontend."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from AgMark.gui.application import (
    PlanningSessionApplicationBoundary,
    SharedApplicationProjector,
)
from AgMark.gui.composition import (
    RepositoryCompositionError,
    compose_repository_planning_session,
    discover_repository_application_authority,
)
from AgMark.gui.diagnostics import EnvironmentDiagnosticEntry
from AgMark.gui.request_resolution import RepositoryApplicationRequestResolver
from AgMark.shared.application import (
    ApplicationRegistrationSource,
    DiscoveredRegistration,
    PlanningApplicationSession,
)
from AgMark.shared.adapters.Codex_CLI.runner import probe_planning_identity
from AgMark.shared.validation import (
    BenchmarkDiscoveryCandidate,
    validate_registration_binding_outcome,
)
from AgMark.gui.readiness import (
    derive_application_environment,
    derive_benchmark_evidence_readiness,
    derive_runner_readiness,
)
from AgMark.gui.shell.window import (
    SidebarControlInputSnapshot,
    SidebarInputSnapshot,
    SidebarPrerequisiteDiagnosticProjection,
    SidebarProjection,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_SECRET_HANDLING = "arcgrav.adapters:secret_handling"
_ACCESS_METHODS = "arcgrav.adapters:access_methods"


def _discovered_runner_for_source(authority: object, source: object) -> object:
    registration = source.registration
    return next(
        runner
        for runner in authority.discovery.runners
        if runner.registration_id == registration["registration_id"]
        and runner.registration_version == registration["registration_version"]
    )


def _provider_free_source(authority: object) -> object:
    return next(
        source
        for source in authority.runner_sources
        if source.registration.get("registration_id") == "arcgrav.mock-model.runner"
    )


def _credential_cli_source(authority: object) -> object:
    return next(
        source
        for source in authority.runner_sources
        if source.registration.get("registration_id") == "openai.codex-cli"
    )

class _CodexPlanningTransport:
    _HELP_TEXT = (
        b"--output-last-message --ephemeral --ignore-user-config "
        b"--ignore-rules --sandbox --color --model --skip-git-repo-check"
    )

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None,
        cwd: Path,
        env: dict[str, str],
        timeout_ms: int,
    ) -> dict[str, object]:
        del cwd, env, timeout_ms
        self.calls.append(
            {
                "argv": tuple(argv),
                "input_bytes": input_bytes,
            }
        )
        if "--distribution" in argv and argv[-2:] == ("--exec", "true"):
            return {"returncode": 0, "stdout": b"", "stderr": b""}
        if "--distribution" in argv and "test" in argv and "-x" in argv:
            return {"returncode": 0, "stdout": b"", "stderr": b""}
        if argv[-1:] == ("--version",):
            return {
                "returncode": 0,
                "stdout": b"codex-cli 1.2.3\n",
                "stderr": b"",
            }
        if "--help" in argv and "exec" in argv:
            return {
                "returncode": 0,
                "stdout": self._HELP_TEXT,
                "stderr": b"",
            }
        raise AssertionError(f"unexpected Codex planning command: {argv!r}")


def _diagnostic_names(projection: object) -> set[str]:
    return {
        diagnostic.diagnostic_name
        for diagnostic in projection.diagnostics
    }


def _synthetic_execution_runtime_runner() -> tuple[
    ApplicationRegistrationSource,
    DiscoveredRegistration,
]:
    source_id = "synthetic-execution-runtime-runner"
    registration = {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "extensions": {
            "arcgrav.adapters:supported_controls": [],
            "arcgrav.adapters:fixed_controls": [],
            "arcgrav.adapters:access_methods": [
                {
                    "type": "cli",
                    "transport": "subprocess",
                    "client_name": "synthetic-runtime",
                    "authentication_class": "environment",
                },
            ],
            "arcgrav.adapters:secret_handling": {
                "credentials_required": True,
                "transient_secrets_supported": True,
                "supported_sources": ["environment"],
                "retained_secret_values": False,
            },
        },
        "registration_id": "synthetic.execution-runtime-runner",
        "registration_version": "1.0.0",
        "registration_kind": "runner",
        "status": "active",
        "contracts": [],
        "implementation_artifacts": [],
        "capabilities": [],
        "limitations": [],
    }
    validation = validate_registration_binding_outcome(
        registration,
        expected_registration_id=registration["registration_id"],
        expected_registration_version=registration["registration_version"],
        contract_requirements=(),
        artifact_sources=(),
        allowed_artifact_roots=("AgMark",),
        source_id=source_id,
    )
    if not validation.valid:
        raise AssertionError("synthetic execution-runtime runner must validate")
    source = ApplicationRegistrationSource(
        registration_source_id=source_id,
        registration=registration,
        registration_validation=validation,
    )
    discovered = DiscoveredRegistration(
        registration_id=registration["registration_id"],
        registration_version=registration["registration_version"],
        registration_kind="runner",
        registration_sha256=validation.registration_sha256,
        registration_source_id=source_id,
    )
    return source, discovered


def _synthetic_default_row_runner() -> tuple[
    ApplicationRegistrationSource,
    DiscoveredRegistration,
]:
    source_id = "synthetic-default-row-runner"
    registration = {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "extensions": {
            "arcgrav.adapters:supported_controls": [
                {
                    "name": "model_id",
                    "kind": "choice",
                    "required": True,
                    "values": ["model-a", "model-b"],
                    "comparison_relevant": True,
                },
                {
                    "name": "temperature",
                    "kind": "number",
                    "required": True,
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "comparison_relevant": True,
                },
                {
                    "name": "max_tokens",
                    "kind": "integer",
                    "required": True,
                    "default": 4096,
                    "minimum": 1,
                    "maximum": 8192,
                    "comparison_relevant": True,
                },
                {
                    "name": "region",
                    "kind": "choice",
                    "required": True,
                    "values": ["us-east", "us-west"],
                    "comparison_relevant": True,
                },
            ],
            "arcgrav.adapters:fixed_controls": [],
        },
        "registration_id": "synthetic.default-row-runner",
        "registration_version": "1.0.0",
        "registration_kind": "runner",
        "status": "active",
        "contracts": [],
        "implementation_artifacts": [],
        "capabilities": [],
        "limitations": [],
    }
    validation = validate_registration_binding_outcome(
        registration,
        expected_registration_id=registration["registration_id"],
        expected_registration_version=registration["registration_version"],
        contract_requirements=(),
        artifact_sources=(),
        allowed_artifact_roots=("AgMark",),
        source_id=source_id,
    )
    if not validation.valid:
        raise AssertionError("synthetic default-row runner registration must validate")
    source = ApplicationRegistrationSource(
        registration_source_id=source_id,
        registration=registration,
        registration_validation=validation,
    )
    discovered = DiscoveredRegistration(
        registration_id=registration["registration_id"],
        registration_version=registration["registration_version"],
        registration_kind="runner",
        registration_sha256=validation.registration_sha256,
        registration_source_id=source_id,
    )
    return source, discovered


class _UnusedRequestResolver:
    """Satisfy the GUI bridge contract for projection-only tests."""

    def _unexpected(self, name: str):
        raise AssertionError(f"projection-only test must not invoke {name}")

    def resolve_plan_request(self, *args, **kwargs):
        return self._unexpected("resolve_plan_request")

    def resolve_execution_request(self, *args, **kwargs):
        return self._unexpected("resolve_execution_request")

    def resolve_report_request(self, *args, **kwargs):
        return self._unexpected("resolve_report_request")

    def resolve_verification_request(self, *args, **kwargs):
        return self._unexpected("resolve_verification_request")


def _synthetic_selection_runner(
    registration_id: str,
    *,
    temperature_default: float,
    temperature_maximum: float,
    max_tokens_default: int,
    max_tokens_minimum: int,
    max_tokens_maximum: int,
    region_values: tuple[str, ...],
    region_default: str,
) -> ApplicationRegistrationSource:
    source_id = f"{registration_id}-source"
    registration = {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "extensions": {
            "arcgrav.adapters:supported_controls": [
                {
                    "name": "temperature",
                    "kind": "number",
                    "required": True,
                    "default": temperature_default,
                    "minimum": 0.0,
                    "maximum": temperature_maximum,
                    "comparison_relevant": True,
                },
                {
                    "name": "max_tokens",
                    "kind": "integer",
                    "required": True,
                    "default": max_tokens_default,
                    "minimum": max_tokens_minimum,
                    "maximum": max_tokens_maximum,
                    "comparison_relevant": True,
                },
                {
                    "name": "region",
                    "kind": "choice",
                    "required": True,
                    "values": list(region_values),
                    "default": region_default,
                    "comparison_relevant": True,
                },
            ],
            "arcgrav.adapters:fixed_controls": [],
        },
        "registration_id": registration_id,
        "registration_version": "1.0.0",
        "registration_kind": "runner",
        "status": "active",
        "contracts": [],
        "implementation_artifacts": [],
        "capabilities": [],
        "limitations": [],
    }
    validation = validate_registration_binding_outcome(
        registration,
        expected_registration_id=registration["registration_id"],
        expected_registration_version=registration["registration_version"],
        contract_requirements=(),
        artifact_sources=(),
        allowed_artifact_roots=("AgMark",),
        source_id=source_id,
    )
    if not validation.valid:
        raise AssertionError("synthetic selection runner registration must validate")
    return ApplicationRegistrationSource(
        registration_source_id=source_id,
        registration=registration,
        registration_validation=validation,
    )


def _synthetic_selection_benchmark() -> BenchmarkDiscoveryCandidate:
    source_id = "synthetic-selection-benchmark-source"
    registration = {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "extensions": {},
        "registration_id": "synthetic.selection-benchmark",
        "registration_version": "1.0.0",
        "registration_kind": "benchmark",
        "status": "active",
        "contracts": [],
        "implementation_artifacts": [],
        "capabilities": [],
        "limitations": [],
    }
    validation = validate_registration_binding_outcome(
        registration,
        expected_registration_id=registration["registration_id"],
        expected_registration_version=registration["registration_version"],
        contract_requirements=(),
        artifact_sources=(),
        allowed_artifact_roots=("AgMark",),
        source_id=source_id,
    )
    if not validation.valid:
        raise AssertionError("synthetic selection benchmark registration must validate")
    return BenchmarkDiscoveryCandidate(
        package_root="AgMark/Synthetic_Selection_Benchmark",
        registration_source_id=source_id,
        registration=registration,
        registration_validation=validation,
    )


class ProductionRepositoryReadinessTests(unittest.TestCase):
    def setUp(self):
        catalog = {"data": [{
            "model": model, "displayName": model, "isDefault": index == 0,
            "supportedReasoningEfforts": [{"reasoningEffort": "medium", "description": "Balanced"},
                                          {"reasoningEffort": "high", "description": "More reasoning"}],
            "defaultReasoningEffort": "medium",
        } for index, model in enumerate(("gpt-5.6", "gpt-5.6-mini"))], "nextCursor": None}
        patcher = patch("AgMark.shared.adapters.Codex_CLI.model_discovery._run_interactive_model_list", return_value=catalog)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_registered_mock_readiness_uses_own_catalog_without_foreign_executable(self):
        from AgMark.gui.readiness import probe_registered_runner_model_discovery
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
        source = next(item for item in authority.runner_sources
                      if item.registration["registration_id"] == "arcgrav.mock-model.runner")
        catalog = probe_registered_runner_model_discovery(source, repository_root=_REPOSITORY_ROOT)
        def reject_foreign_resolution(name):
            raise AssertionError("Bundled local-process adapter must not resolve a provider CLI")
        projection = derive_runner_readiness(
            discovered_runner=_discovered_runner_for_source(authority, source),
            runner_sources=authority.runner_sources,
            executable_resolver=reject_foreign_resolution,
            model_discovery_probe=lambda *_args: catalog,
        )
        self.assertEqual("success", projection.runner_connectivity[1])
        self.assertNotIn("runner-executable", _diagnostic_names(projection))
        self.assertNotIn("runner-authentication", _diagnostic_names(projection))
        self.assertIsNone(projection.reasoning_effort_control_name)
        self.assertTrue(projection.runner_test_supported)
        self.assertEqual({"request_timeout_ms"}, {c.control_name for c in projection.additional_controls})

    def test_runtime_only_readiness_uses_execution_scope_unless_planning_discovery_requires_it(
        self,
    ) -> None:
        source, discovered = _synthetic_execution_runtime_runner()
        execution_projection = derive_runner_readiness(
            discovered_runner=discovered,
            runner_sources=(source,),
            executable_resolver=lambda _name: None,
            authentication_probe=lambda *_args, **_kwargs: False,
        )
        execution_scopes = {
            diagnostic.diagnostic_name: diagnostic.operation
            for diagnostic in execution_projection.diagnostics
        }
        self.assertEqual("execution", execution_scopes["runner-executable"])
        self.assertEqual("execution", execution_scopes["runner-authentication"])

        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        codex_source = _credential_cli_source(composition.authority)
        codex_runner = _discovered_runner_for_source(
            composition.authority,
            codex_source,
        )
        planning_projection = derive_runner_readiness(
            discovered_runner=codex_runner,
            runner_sources=composition.authority.runner_sources,
            executable_resolver=lambda _name: None,
            authentication_probe=lambda *_args, **_kwargs: False,
        )
        planning_scopes = {
            diagnostic.diagnostic_name: diagnostic.operation
            for diagnostic in planning_projection.diagnostics
        }
        self.assertEqual("planning", planning_scopes["runner-executable"])
        self.assertIn("runner-model-discovery", planning_scopes)
        self.assertNotIn("runner-authentication", planning_scopes)


    @classmethod
    def setUpClass(cls) -> None:
        cls.authority = discover_repository_application_authority(_REPOSITORY_ROOT)

    def _prepare_real_codex_frontend(
        self,
        *,
        platform_name: str,
        executable_resolver: object,
        transport: _CodexPlanningTransport,
    ) -> tuple[
        PlanningSessionApplicationBoundary,
        RepositoryApplicationRequestResolver,
        SidebarInputSnapshot,
        list[dict[str, object]],
    ]:
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
        source = _credential_cli_source(authority)
        runner = _discovered_runner_for_source(authority, source)
        runner_label = f"{runner.registration_id}@{runner.registration_version}"
        benchmark = authority.discovery.benchmarks[0]
        benchmark_label = (
            f"{benchmark.registration_id}@{benchmark.registration_version}"
        )
        planning_results: list[dict[str, object]] = []

        def planning_probe(
            candidate: object,
            control_values: object,
        ) -> dict[str, object]:
            self.assertIs(source, candidate)
            result = probe_planning_identity(
                source.registration,
                control_values=dict(control_values),
                transport=transport,
                executable_resolver=executable_resolver,
                platform_name=platform_name,
            )
            planning_results.append(dict(result))
            return result

        request_resolver = RepositoryApplicationRequestResolver(
            authority,
            runner_planning_probe=planning_probe,
        )
        boundary = PlanningSessionApplicationBoundary(
            session=composition.session,
            request_resolver=request_resolver,
        )
        boundary.discover()
        projector = SharedApplicationProjector(
            boundary,
            runner_sources=authority.runner_sources,
            benchmark_candidates=authority.benchmark_candidates,
            repository_root=authority.repository_root,
            executable_resolver=executable_resolver,
            model_discovery_probe=lambda *_args, **_kwargs: {
                "status": "ready",
                "provider_submitted": False,
                "effective_default_model_id": "gpt-5.6",
                "selectable_model_ids": ["gpt-5.6", "gpt-5.6-mini"],
                "choices": [
                    {
                        "model_id": "gpt-5.6",
                        "selection_mode": "explicit",
                        "label": "Default (GPT-5.6)",
                        "reasoning_efforts": [{"value": "medium", "description": "Balanced"}, {"value": "high", "description": "More reasoning"}],
                        "default_reasoning_effort": "medium",
                    },
                    {
                        "model_id": "gpt-5.6-mini",
                        "selection_mode": "explicit",
                        "label": "GPT-5.6 Mini",
                        "reasoning_efforts": [{"value": "medium", "description": "Balanced"}, {"value": "high", "description": "More reasoning"}],
                        "default_reasoning_effort": "medium",
                    },
                ],
                "resolved_configuration": {
                    "wsl_user": "gunnanmon",
                    "codex_home": "/home/gunnanmon/.codex",
                },
            },
        )
        launch_mode = "wsl" if platform_name == "nt" else "native"
        codex_binary = "/usr/bin/codex" if launch_mode == "wsl" else "codex"
        base_controls = [
            SidebarControlInputSnapshot("launch_mode", launch_mode),
            SidebarControlInputSnapshot("codex_binary", codex_binary),
        ]
        if launch_mode == "wsl":
            base_controls.append(
                SidebarControlInputSnapshot("wsl_distribution", "Ubuntu")
            )

        ready_intent = SidebarInputSnapshot(
            benchmark=benchmark_label,
            runner=runner_label,
            model="gpt-5.6",
            credential="",
            temperature=None,
            max_tokens=None,
            additional_controls=tuple(base_controls),
        )
        with patch("AgMark.gui.readiness.os_name", platform_name):
            projected = projector.sidebar_from_intent(ready_intent)
            self.assertEqual("gpt-5.6", projected.selected_model)
            self.assertEqual("explicit", projected.selected_model_selection_mode)
            prerequisites = projector.prerequisite_projection(ready_intent)

        self.assertTrue(prerequisites.ready_for("planning"))
        boundary.set_prerequisite_projection(prerequisites)
        return boundary, request_resolver, ready_intent, planning_results

    def test_provider_free_runner_projects_real_unresolved_required_controls(self) -> None:
        source = _provider_free_source(self.authority)
        discovered = _discovered_runner_for_source(self.authority, source)

        projection = derive_runner_readiness(
            discovered_runner=discovered,
            runner_sources=self.authority.runner_sources,
            executable_resolver=lambda _name: None,
            authentication_probe=lambda _source: None,
        )

        self.assertTrue(projection.model_control_present)
        self.assertFalse(projection.credentials_required)
        self.assertEqual({"request_timeout_ms"}, {control.control_name for control in projection.additional_controls})
        self.assertEqual("120000", projection.additional_controls[0].value)
        self.assertIsNone(projection.reasoning_effort_control_name)
        self.assertTrue(projection.scenario_visible)
        self.assertEqual((), projection.model_choices)
        self.assertIn("runner-model-discovery", _diagnostic_names(projection))
        self.assertNotIn("runner-executable", _diagnostic_names(projection))
        self.assertTrue({
            "runner-control:request_timeout_ms", "runner-control:maximum_attempts",
        }.isdisjoint(_diagnostic_names(projection)))

    def test_real_codex_native_planning_probe_binds_runtime_and_noninteractive_surface(
        self,
    ) -> None:
        transport = _CodexPlanningTransport()
        resolver_calls: list[str] = []

        def resolver(name: str) -> str | None:
            resolver_calls.append(name)
            return "/opt/codex/bin/codex" if name == "codex" else None

        boundary, _request_resolver, ready_intent, planning_results = (
            self._prepare_real_codex_frontend(
                platform_name="posix",
                executable_resolver=resolver,
                transport=transport,
            )
        )
        plan = boundary.build_plan(ready_intent)

        self.assertEqual(1, len(planning_results))
        planning = planning_results[0]
        self.assertEqual("ready", planning["status"])
        self.assertFalse(planning["provider_submitted"])
        self.assertTrue(planning["noninteractive_surface_verified"])
        self.assertEqual("1.2.3", planning["runtime_version"])
        self.assertEqual(
            {
                "mode": "native",
                "executable": "runtime/codex",
            },
            planning["launch_environment"],
        )
        self.assertEqual({"codex"}, set(resolver_calls))
        self.assertEqual(2, len(transport.calls))
        self.assertEqual(("--version",), transport.calls[0]["argv"][1:])
        self.assertIn("--help", transport.calls[1]["argv"])
        self.assertTrue(
            all(call["input_bytes"] is None for call in transport.calls)
        )

        request = boundary.plan_request
        self.assertIsNotNone(request)
        boundary_document = request.execution_boundary.to_dict()
        controls = {
            item["name"]: item["value"]
            for item in boundary_document["controls"]
        }
        self.assertEqual("1.2.3", boundary_document["provider_runtime"]["runtime_version"])
        self.assertEqual("native", controls["launch_mode"])
        self.assertEqual("runtime/codex", controls["codex_binary"])
        self.assertEqual("gpt-5.6", controls["model_id"])
        self.assertEqual(
            request.execution_boundary.fingerprint,
            plan.execution_boundary_fingerprint,
        )

    def test_real_codex_wsl_plan_and_execution_revalidation_are_host_path_independent(
        self,
    ) -> None:
        transport = _CodexPlanningTransport()
        resolver_calls: list[str] = []
        wsl_launcher = r"C:\Windows\System32\wsl.exe"

        def resolver(name: str) -> str | None:
            resolver_calls.append(name)
            return wsl_launcher if name == wsl_launcher else None

        boundary, request_resolver, ready_intent, planning_results = (
            self._prepare_real_codex_frontend(
                platform_name="nt",
                executable_resolver=resolver,
                transport=transport,
            )
        )
        plan = boundary.build_plan(ready_intent)
        accepted = boundary.accept_plan()
        request = boundary.plan_request
        self.assertIsNotNone(request)
        execution = request_resolver.resolve_execution_request(
            request,
            accepted,
            credential="",
        )

        self.assertEqual(2, len(planning_results))
        for planning in planning_results:
            self.assertEqual("ready", planning["status"])
            self.assertFalse(planning["provider_submitted"])
            self.assertTrue(planning["noninteractive_surface_verified"])
            self.assertEqual("1.2.3", planning["runtime_version"])
            self.assertEqual(
                {
                    "mode": "wsl",
                    "executable": "runtime/codex",
                },
                planning["launch_environment"],
            )
        self.assertNotIn("codex", resolver_calls)
        self.assertEqual({wsl_launcher}, set(resolver_calls))
        self.assertEqual(6, len(transport.calls))
        self.assertTrue(
            all(call["input_bytes"] is None for call in transport.calls)
        )
        for offset in (0, 3):
            self.assertEqual(
                (
                    "--distribution",
                    "Ubuntu",
                    "--exec",
                    "test",
                    "-x",
                    "/usr/bin/codex",
                ),
                transport.calls[offset]["argv"][1:],
            )
            self.assertEqual(
                (
                    "--distribution",
                    "Ubuntu",
                    "--exec",
                    "/usr/bin/codex",
                    "--version",
                ),
                transport.calls[offset + 1]["argv"][1:],
            )
            self.assertIn("--help", transport.calls[offset + 2]["argv"])

        boundary_document = execution.execution_boundary.to_dict()
        controls = {
            item["name"]: item["value"]
            for item in boundary_document["controls"]
        }
        self.assertEqual("wsl", controls["launch_mode"])
        self.assertNotIn("wsl_distribution", controls)
        self.assertEqual("runtime/codex", controls["codex_binary"])
        self.assertEqual({"wsl_distribution": "Ubuntu", "codex_binary": "/usr/bin/codex"}, dict(execution.runner_launch_selection))
        self.assertEqual("1.2.3", boundary_document["provider_runtime"]["runtime_version"])
        self.assertEqual(
            plan.execution_boundary_fingerprint,
            execution.execution_boundary.fingerprint,
        )
        self.assertIsNone(execution.runner_transient_values)

    def test_real_codex_wsl_plan_rejects_missing_launcher_despite_host_codex(
        self,
    ) -> None:
        transport = _CodexPlanningTransport()
        resolver_calls: list[str] = []

        def resolver(name: str) -> str | None:
            resolver_calls.append(name)
            if name == "codex":
                return "/host/bin/codex"
            return None

        boundary, _request_resolver, ready_intent, planning_results = (
            self._prepare_real_codex_frontend(
                platform_name="nt",
                executable_resolver=resolver,
                transport=transport,
            )
        )

        with self.assertRaisesRegex(
            RepositoryCompositionError,
            "codex_cli_host_launcher_missing",
        ):
            boundary.build_plan(ready_intent)

        self.assertEqual(1, len(planning_results))
        self.assertEqual("unsupported", planning_results[0]["status"])
        self.assertEqual(
            "codex_cli_host_launcher_missing",
            planning_results[0]["error_code"],
        )
        self.assertNotIn("codex", resolver_calls)
        self.assertEqual(
            [r"C:\Windows\System32\wsl.exe"],
            resolver_calls,
        )
        self.assertEqual([], transport.calls)

    def test_runner_selection_drops_unowned_prior_runner_projection(self) -> None:
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        boundary = PlanningSessionApplicationBoundary(
            session=composition.session,
            request_resolver=RepositoryApplicationRequestResolver(
                composition.authority
            ),
        )
        boundary.discover()
        source = _provider_free_source(composition.authority)
        runner = _discovered_runner_for_source(composition.authority, source)
        runner_label = (
            f"{runner.registration_id}@{runner.registration_version}"
        )
        benchmark = composition.authority.discovery.benchmarks[0]
        benchmark_label = (
            f"{benchmark.registration_id}@{benchmark.registration_version}"
        )

        projector = SharedApplicationProjector(
            boundary,
            runner_sources=composition.authority.runner_sources,
            benchmark_candidates=composition.authority.benchmark_candidates,
            repository_root=composition.authority.repository_root,
            executable_resolver=lambda name: f"/validated/{name}",
        )
        switched = projector.sidebar_for_runner(
            SidebarInputSnapshot(
                benchmark=benchmark_label,
                runner=runner_label,
                model="gpt-5.6",
                credential="prior-runner-secret",
                temperature=None,
                max_tokens=None,
                additional_controls=(
                    SidebarControlInputSnapshot("launch_mode", "native"),
                    SidebarControlInputSnapshot("codex_binary", "codex"),
                    SidebarControlInputSnapshot(
                        "model_selection_mode",
                        "explicit",
                    ),
                ),
            ),
            runner_label,
        )

        self.assertEqual(runner_label, switched.selected_runner)
        self.assertEqual((), switched.model_options)
        self.assertEqual((), switched.model_choices)
        self.assertIsNone(switched.selected_model)
        self.assertEqual("", switched.credential_value)
        self.assertEqual(
            {"request_timeout_ms"},
            {
                control.control_name
                for control in switched.additional_controls
            },
        )
        diagnostic_names = {
            diagnostic.diagnostic_name
            for diagnostic in switched.prerequisite_diagnostics
        }
        self.assertNotIn("runner-executable", diagnostic_names)
        self.assertNotIn("runner-authentication", diagnostic_names)
        self.assertIn("runner-model-discovery", diagnostic_names)
        self.assertTrue(switched.scenario_visible)
        self.assertFalse(switched.build_plan_effectively_available)

    def test_runner_selection_revalidates_reverse_provider_free_to_cli_projection(self) -> None:
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        boundary = PlanningSessionApplicationBoundary(
            session=composition.session,
            request_resolver=RepositoryApplicationRequestResolver(
                composition.authority
            ),
        )
        boundary.discover()
        cli_source = _credential_cli_source(composition.authority)
        cli_runner = _discovered_runner_for_source(
            composition.authority,
            cli_source,
        )
        cli_label = (
            f"{cli_runner.registration_id}@{cli_runner.registration_version}"
        )
        provider_free_source = _provider_free_source(composition.authority)
        provider_free_runner = _discovered_runner_for_source(
            composition.authority,
            provider_free_source,
        )
        provider_free_label = (
            f"{provider_free_runner.registration_id}@"
            f"{provider_free_runner.registration_version}"
        )
        benchmark = composition.authority.discovery.benchmarks[0]
        benchmark_label = (
            f"{benchmark.registration_id}@{benchmark.registration_version}"
        )

        projector = SharedApplicationProjector(
            boundary,
            runner_sources=composition.authority.runner_sources,
            benchmark_candidates=composition.authority.benchmark_candidates,
            repository_root=composition.authority.repository_root,
            executable_resolver=lambda name: f"/validated/{name}",
        )
        switched = projector.sidebar_for_runner(
            SidebarInputSnapshot(
                benchmark=benchmark_label,
                runner=provider_free_label,
                model=None,
                credential="stale-provider-free-secret",
                temperature=None,
                max_tokens=None,
                additional_controls=(
                    SidebarControlInputSnapshot("mock_outcome", "failed"),
                    SidebarControlInputSnapshot(
                        "response_mode",
                        "request_digest",
                    ),
                ),
            ),
            cli_label,
        )

        self.assertEqual(cli_label, switched.selected_runner)
        self.assertEqual((), switched.model_choices)
        self.assertEqual((), switched.model_options)
        self.assertIsNone(switched.selected_model)
        self.assertIsNone(switched.selected_model_selection_mode)
        self.assertEqual("", switched.credential_value)
        additional_names = {
            control.control_name
            for control in switched.additional_controls
        }
        self.assertTrue(
            {"mock_outcome", "response_mode", "credential_source"}.isdisjoint(
                additional_names
            ),
            additional_names,
        )
        diagnostic_names = {
            diagnostic.diagnostic_name
            for diagnostic in switched.prerequisite_diagnostics
        }
        self.assertNotIn("runner-executable", diagnostic_names)
        self.assertNotIn("runner-authentication", diagnostic_names)
        self.assertIn("runner-model-discovery", diagnostic_names)

    def test_runner_readiness_rejects_mismatched_validated_repository_authority(self) -> None:
        provider_free = _provider_free_source(self.authority)
        credential_cli = _credential_cli_source(self.authority)
        discovered = _discovered_runner_for_source(self.authority, provider_free)

        projection = derive_runner_readiness(
            discovered_runner=discovered,
            runner_sources=(credential_cli,),
            executable_resolver=lambda _name: None,
        )

        self.assertEqual(
            {"runner-registration-source"},
            _diagnostic_names(projection),
        )

    def test_real_benchmark_projects_durable_evidence_destination_without_creating_it(self) -> None:
        candidate = self.authority.benchmark_candidates[0]
        registration = candidate.registration
        discovered = next(
            benchmark
            for benchmark in self.authority.discovery.benchmarks
            if benchmark.registration_id == registration["registration_id"]
            and benchmark.registration_version == registration["registration_version"]
        )
        expected_root = self.authority.repository_root / "AgMark" / "run_evidence"
        existed_before = expected_root.exists()

        projection = derive_benchmark_evidence_readiness(
            discovered_benchmark=discovered,
            benchmark_candidates=self.authority.benchmark_candidates,
            repository_root=self.authority.repository_root,
        )

        self.assertEqual(expected_root, projection.destination_root)
        self.assertEqual((), projection.diagnostics)
        self.assertEqual(existed_before, expected_root.exists())

    def test_inaccessible_benchmark_package_fails_closed_without_creating_storage(self) -> None:
        candidate = self.authority.benchmark_candidates[0]
        registration = candidate.registration
        discovered = next(
            benchmark
            for benchmark in self.authority.discovery.benchmarks
            if benchmark.registration_id == registration["registration_id"]
            and benchmark.registration_version == registration["registration_version"]
        )

        with TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            before = tuple(root.iterdir())
            projection = derive_benchmark_evidence_readiness(
                discovered_benchmark=discovered,
                benchmark_candidates=self.authority.benchmark_candidates,
                repository_root=root,
            )

            self.assertEqual(
                {"benchmark-evidence-destination"},
                _diagnostic_names(projection),
            )
            self.assertEqual("planning", projection.diagnostics[0].operation)
            self.assertEqual(before, tuple(root.iterdir()))

    def test_unusable_evidence_store_is_execution_scoped_after_package_resolution(self) -> None:
        candidate = self.authority.benchmark_candidates[0]
        registration = candidate.registration
        discovered = next(
            benchmark
            for benchmark in self.authority.discovery.benchmarks
            if benchmark.registration_id == registration["registration_id"]
            and benchmark.registration_version == registration["registration_version"]
        )

        with TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            benchmark_root = root.joinpath(
                *PurePosixPath(candidate.package_root).parts
            )
            benchmark_root.mkdir(parents=True)
            (root / "AgMark" / "run_evidence").write_text(
                "not a directory",
                encoding="utf-8",
            )

            projection = derive_benchmark_evidence_readiness(
                discovered_benchmark=discovered,
                benchmark_candidates=self.authority.benchmark_candidates,
                repository_root=root,
            )

            self.assertEqual(
                {"benchmark-evidence-destination"},
                _diagnostic_names(projection),
            )
            self.assertEqual("execution", projection.diagnostics[0].operation)

    def test_environment_snapshot_is_current_generation_free_and_drops_resolved_blockers(self) -> None:
        discovery = self.authority.discovery
        benchmark = discovery.benchmarks[0]
        runner = discovery.runners[0]
        benchmark_label = (
            f"{benchmark.registration_id}@{benchmark.registration_version}"
        )
        runner_label = f"{runner.registration_id}@{runner.registration_version}"
        blocker = SidebarPrerequisiteDiagnosticProjection(
            diagnostic_name="runner-authentication",
            message="Authentication readiness is unresolved.",
            remediation="Restore runner authentication.",
            details=(
                "codex_cli_authentication_context_unavailable — "
                "api_key=environment-secret"
            ),
        )
        sidebar = SidebarProjection(
            benchmark_options=(benchmark_label,),
            selected_benchmark=benchmark_label,
            runner_options=(runner_label,),
            selected_runner=runner_label,
            model_required=True,
            build_plan_available=True,
            prerequisite_diagnostics=(blocker,),
        )
        supplied = EnvironmentDiagnosticEntry(
            source="Startup",
            state="warning",
            summary="A non-blocking startup diagnostic is available.",
        )

        blocked = derive_application_environment(
            discovery=discovery,
            sidebar=sidebar,
            evidence_destination=_REPOSITORY_ROOT / "evidence",
            supplied_entries=(supplied,),
        )
        blocked_text = blocked.render()
        self.assertTrue(blocked.has_blockers)
        self.assertIn(benchmark_label, blocked_text)
        self.assertIn(runner_label, blocked_text)
        self.assertIn("Authentication readiness is unresolved.", blocked_text)
        self.assertIn(
            "codex_cli_authentication_context_unavailable",
            blocked_text,
        )
        self.assertIn("api_key=<redacted>", blocked_text)
        self.assertNotIn("environment-secret", blocked_text)
        self.assertIn("A non-blocking startup diagnostic is available.", blocked_text)

        refreshed = derive_application_environment(
            discovery=discovery,
            sidebar=SidebarProjection(
                benchmark_options=(benchmark_label,),
                selected_benchmark=benchmark_label,
                runner_options=(runner_label,),
                selected_runner=runner_label,
                model_required=False,
                build_plan_available=True,
            ),
        )
        refreshed_text = refreshed.render()
        self.assertFalse(refreshed.has_blockers)
        self.assertNotIn("Authentication readiness is unresolved.", refreshed_text)
        self.assertNotIn(
            "codex_cli_authentication_context_unavailable",
            refreshed_text,
        )
        self.assertNotIn("A non-blocking startup diagnostic is available.", refreshed_text)

    # Selection refresh may carry only values that the newly selected runner revalidates.
    def test_runner_selection_revalidates_only_common_values_per_new_runner_authority(self) -> None:
        first_source = _synthetic_selection_runner(
            "synthetic.selection-runner-a",
            temperature_default=0.25,
            temperature_maximum=2.0,
            max_tokens_default=4096,
            max_tokens_minimum=1,
            max_tokens_maximum=8192,
            region_values=("us-east", "us-west"),
            region_default="us-east",
        )
        second_source = _synthetic_selection_runner(
            "synthetic.selection-runner-b",
            temperature_default=0.5,
            temperature_maximum=1.0,
            max_tokens_default=2048,
            max_tokens_minimum=1024,
            max_tokens_maximum=4096,
            region_values=("us-east", "eu-west"),
            region_default="eu-west",
        )
        benchmark = _synthetic_selection_benchmark()
        session = PlanningApplicationSession(
            benchmark_candidates=(benchmark,),
            runner_sources=(first_source, second_source),
        )
        boundary = PlanningSessionApplicationBoundary(
            session=session,
            request_resolver=_UnusedRequestResolver(),
        )
        discovery = boundary.discover()
        projector = SharedApplicationProjector(
            boundary,
            runner_sources=(first_source, second_source),
        )

        benchmark_label = (
            f"{benchmark.registration['registration_id']}@"
            f"{benchmark.registration['registration_version']}"
        )
        first_label = (
            f"{first_source.registration['registration_id']}@"
            f"{first_source.registration['registration_version']}"
        )
        second_label = (
            f"{second_source.registration['registration_id']}@"
            f"{second_source.registration['registration_version']}"
        )
        self.assertEqual(
            {first_label, second_label},
            {
                f"{runner.registration_id}@{runner.registration_version}"
                for runner in discovery.runners
            },
        )

        carried = projector.sidebar_for_runner(
            SidebarInputSnapshot(
                benchmark=benchmark_label,
                runner=first_label,
                model=None,
                credential="transient-secret",
                temperature=0.75,
                max_tokens=2048,
            ),
            second_label,
        )
        self.assertEqual(second_label, carried.selected_runner)
        self.assertEqual("", carried.credential_value)
        self.assertEqual(0.75, carried.temperature.value)
        self.assertEqual(2048.0, carried.max_tokens.value)

        rejected = projector.sidebar_for_runner(
            SidebarInputSnapshot(
                benchmark=benchmark_label,
                runner=first_label,
                model=None,
                credential="transient-secret",
                temperature=1.5,
                max_tokens=7000,
            ),
            second_label,
        )
        self.assertEqual(0.5, rejected.temperature.value)
        self.assertEqual(2048.0, rejected.max_tokens.value)

    def test_validated_runner_projects_model_numeric_and_additional_controls_without_defaults(self) -> None:
        source, discovered = _synthetic_default_row_runner()

        projection = derive_runner_readiness(
            discovered_runner=discovered,
            runner_sources=(source,),
        )

        self.assertTrue(projection.model_control_present)
        self.assertEqual(("model-a", "model-b"), projection.model_options)
        self.assertIsNone(projection.selected_model)
        self.assertFalse(projection.model_editable)
        self.assertTrue(projection.model_required)

        self.assertIsNotNone(projection.temperature)
        self.assertIsNone(projection.temperature.value)
        self.assertEqual(
            (0.0, 2.0),
            (projection.temperature.minimum, projection.temperature.maximum),
        )
        self.assertTrue(projection.temperature.required)
        self.assertTrue(projection.temperature.editable)

        self.assertIsNotNone(projection.max_tokens)
        self.assertEqual(4096.0, projection.max_tokens.value)
        self.assertEqual(
            (1.0, 8192.0),
            (projection.max_tokens.minimum, projection.max_tokens.maximum),
        )
        self.assertTrue(projection.max_tokens.required)
        self.assertTrue(projection.max_tokens.editable)

        self.assertEqual(
            {"region"},
            {control.control_name for control in projection.additional_controls},
        )
        self.assertEqual(set(), _diagnostic_names(projection))


if __name__ == "__main__":
    unittest.main()
