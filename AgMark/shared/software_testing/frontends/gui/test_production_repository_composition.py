"""Production repository-authority composition coverage."""

from __future__ import annotations

from dataclasses import replace
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest import mock as unittest_mock

from AgMark.gui.composition import (
    RepositoryCompositionError,
    compose_repository_planning_session,
    discover_repository_application_authority,
)
from AgMark.gui.request_resolution import RepositoryApplicationRequestResolver
from AgMark.gui.requests import ResolvedRunnerTestRequest
from AgMark.gui.application.runner_testing import _runner_test_result_from_observation
from AgMark.gui.projection.retained_evidence import _decode_retained_json_documents
from AgMark.gui.application.projector import (
    _decode_retained_json_documents as _decode_console_documents,
)
from AgMark.gui.application.console_projection import (
    _accepted_run_live_output,
    _accepted_run_raw_response,
)
from AgMark.gui.projection.retained_evidence import _observation_status_text
from AgMark.gui.projection.workspace.progress import active_retained_progress_projection
from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination
from AgMark.shared.adapters.execution import validate_retained_parity_observation
from AgMark.gui.shell.window import (
    SidebarControlInputSnapshot,
    SidebarInputSnapshot,
)
from AgMark.shared.application import PlanningApplicationSession
from AgMark.shared.runtime.orchestration import AcceptedRun, BlockedRun


_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_CODEX_RUNTIME_VERSION = "1.2.3"
_REGISTRATION_SCHEMA_AUTHORITY_FILENAMES = (
    "catalog.json",
    "schema_catalog.schema.json",
    "registration.schema.json",
    "metric_registration.schema.json",
)


def _copy_registration_schema_authority(root: Path) -> None:
    source_root = _REPOSITORY_ROOT / "AgMark/shared/schemas"
    destination_root = root / "AgMark/shared/schemas"
    destination_root.mkdir(parents=True, exist_ok=True)
    for filename in _REGISTRATION_SCHEMA_AUTHORITY_FILENAMES:
        (destination_root / filename).write_bytes(
            (source_root / filename).read_bytes()
        )


def _codex_planning_probe(source: object, control_values: object) -> dict[str, object]:
    registration = source.registration
    if registration["registration_id"] != "openai.codex-cli":
        raise AssertionError("Codex planning probe received another runner")
    if not isinstance(control_values, dict):
        control_values = dict(control_values)
    if "credential_source" in control_values:
        raise AssertionError("transient credential controls reached planning probe")

    mode = control_values.get("launch_mode", "native")
    if mode == "wsl":
        codex_binary = control_values.get("codex_binary", "/usr/bin/codex")
        distribution = control_values.get("wsl_distribution", "Ubuntu")
    else:
        codex_binary = control_values.get("codex_binary", "codex")
        distribution = None
    model_id = control_values.get("model_id")
    if not isinstance(model_id, str) or not model_id:
        raise AssertionError("Codex planning probe requires explicit model_id")
    resolved_controls: dict[str, object] = {
        "launch_mode": mode,
        "codex_binary": codex_binary,
    }
    if distribution is not None:
        resolved_controls["wsl_distribution"] = distribution
    return {
        "status": "ready",
        "provider_submitted": False,
        "noninteractive_surface_verified": True,
        "resolved_controls": resolved_controls,
        "provider_runtime": {
            "runtime_id": "openai.codex-cli",
            "runtime_version": _CODEX_RUNTIME_VERSION,
            "provider": "OpenAI",
            "access_method": "cli",
            "model": model_id,
        },
    }


def _projection_identity(value: object) -> tuple[object, ...]:
    return (
        value.registration_id,
        value.registration_version,
        value.registration_kind,
        value.registration_sha256,
        value.registration_source_id,
    )


def _candidate_identity(candidate: object) -> tuple[object, ...]:
    registration = candidate.registration
    validation = candidate.registration_validation
    return (
        registration["registration_id"],
        registration["registration_version"],
        registration["registration_kind"],
        validation.registration_sha256,
        candidate.registration_source_id,
    )


def _runner_identity(source: object) -> tuple[object, ...]:
    registration = source.registration
    validation = source.registration_validation
    return (
        registration["registration_id"],
        registration["registration_version"],
        registration["registration_kind"],
        validation.registration_sha256,
        source.registration_source_id,
    )


class ProductionRepositoryCompositionTests(unittest.TestCase):
    def setUp(self):
        from AgMark.shared.software_testing.frontends.gui.isolated_repository import isolate_repository
        isolate_repository(self, "_REPOSITORY_ROOT")


    def test_registered_mock_uses_normal_repository_lifecycle_and_common_projection(self):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
        benchmark = next(
            candidate for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        mock = next(
            source for source in authority.runner_sources
            if source.registration["registration_id"] == "arcgrav.mock-model.runner"
        )
        live = next(
            source for source in authority.runner_sources
            if source.registration["registration_id"] == "openai.codex-cli"
        )
        self.assertNotEqual(
            live.registration["extensions"]["arcgrav.adapters:entry_point"],
            mock.registration["extensions"]["arcgrav.adapters:entry_point"],
        )
        from AgMark.gui.readiness import probe_registered_runner_model_discovery
        discovery = probe_registered_runner_model_discovery(mock, repository_root=_REPOSITORY_ROOT)
        self.assertEqual("ready", discovery["status"])
        self.assertFalse(discovery["provider_submitted"])
        model_id = "mock-base::scenario:structured_response"
        self.assertIn(model_id, discovery["selectable_model_ids"])

        intent = SidebarInputSnapshot(
            benchmark=(f"{benchmark.registration['registration_id']}@"
                       f"{benchmark.registration['registration_version']}"),
            runner=(f"{mock.registration['registration_id']}@"
                    f"{mock.registration['registration_version']}"),
            model=model_id,
            credential="",
            temperature=None,
            max_tokens=None,
            additional_controls=(),
        )
        resolver = RepositoryApplicationRequestResolver(authority)
        request = resolver.resolve_plan_request(intent, authority.discovery)
        controls = {
            item["name"]: item["value"]
            for item in request.execution_boundary.to_dict()["controls"]
        }
        self.assertEqual(model_id, controls["model_id"])
        plan = composition.session.build_plan(request)
        self.assertTrue(plan.observations)
        snapshot = composition.session.accept_plan()
        execution_request = resolver.resolve_execution_request(
            request, snapshot, credential=""
        )
        retained = composition.session.execute_accepted_run(execution_request)
        self.assertIsInstance(retained, AcceptedRun)
        observations, diagnostics = _decode_console_documents(
            retained.treatment_observations, label="treatment observation"
        )
        self.assertEqual((), diagnostics)
        self.assertEqual(len(plan.observations), len(observations))
        for observation in observations:
            validate_retained_parity_observation(observation)
            execution = observation["extensions"]["arcgrav.runner:execution"]
            self.assertEqual("mock-model", execution["target"]["class"])
            self.assertEqual(model_id, execution["runtime"]["model_id"])
            self.assertFalse(execution["submission"]["external_provider"])

        scores, score_diagnostics = _decode_console_documents(
            retained.score_artifacts, label="score artifact"
        )
        self.assertEqual((), score_diagnostics)
        projected = (
            _accepted_run_live_output(retained, observations, scores),
            _accepted_run_raw_response(observations),
            tuple(_observation_status_text(item) for item in observations),
        )
        without_unrelated = []
        for observation in observations:
            changed = json.loads(json.dumps(observation))
            changed["extensions"]["thirdparty.example:private"] = {"note": "unrelated diagnostic"}
            with self.assertRaises(ValueError):
                validate_retained_parity_observation(changed)
            without_unrelated.append(changed)
        self.assertEqual(
            projected,
            (
                _accepted_run_live_output(retained, without_unrelated, scores),
                _accepted_run_raw_response(without_unrelated),
                tuple(_observation_status_text(item) for item in without_unrelated),
            ),
        )
        runner_test_request = ResolvedRunnerTestRequest(
            request.execution_boundary, mock.registration, None,
        )
        runner_test = _runner_test_result_from_observation(
            selected_runner=intent.runner,
            resolved=runner_test_request,
            observation=observations[0],
        )
        with self.assertRaises(ValueError):
            _runner_test_result_from_observation(
                selected_runner=intent.runner, resolved=runner_test_request,
                observation=without_unrelated[0],
            )
        cleaned = json.loads(json.dumps(without_unrelated[0]))
        cleaned["extensions"].pop("thirdparty.example:private")
        without_target_details = _runner_test_result_from_observation(
            selected_runner=intent.runner, resolved=runner_test_request, observation=cleaned,
        )
        self.assertTrue(runner_test.submitted)
        self.assertEqual(runner_test, without_target_details)
        self._assert_active_projection_common_evidence(
            plan, retained.generation_id, observations[0], runner_test_request,
            intent.runner,
        )
        altered_response = json.loads(json.dumps(cleaned))
        response_key = altered_response["response"]["reference"].removeprefix(
            "extensions:/"
        )
        altered_response["extensions"][response_key] = base64.b64encode(
            b"altered retained response"
        ).decode("ascii")
        validate_retained_parity_observation(altered_response)
        altered_text, altered_diagnostics = _accepted_run_raw_response(
            (altered_response,)
        )
        self.assertIsNone(altered_text)
        self.assertTrue(
            any("integrity check failed" in item for item in altered_diagnostics)
        )
        self.assertEqual(
            "",
            _runner_test_result_from_observation(
                selected_runner=intent.runner,
                resolved=runner_test_request,
                observation=altered_response,
            ).response_preview,
        )
        invalid = json.loads(json.dumps(without_unrelated[0]))
        del invalid["extensions"]["arcgrav.runner:execution"]
        with self.assertRaises(ValueError):
            _runner_test_result_from_observation(
                selected_runner=intent.runner,
                resolved=runner_test_request,
                observation=invalid,
            )
        for field, value in (("id", "unrelated.runner"), ("version", "9.9.9")):
            with self.subTest(mismatched_runner_field=field):
                mismatched = json.loads(json.dumps(without_unrelated[0]))
                mismatched["runner"][field] = value
                mismatched["extensions"].pop("arcgrav.runner:execution")
                with self.assertRaises(ValueError):
                    _runner_test_result_from_observation(
                        selected_runner=intent.runner,
                        resolved=runner_test_request,
                        observation=mismatched,
                    )

        resolver.resolve_report_request(retained)

        bundle = composition.session.completed_report(retained.generation_id)
        self.assertIsNotNone(bundle)
        prerequisites = bundle.report_document["extensions"][
            "arcgrav.authority-resolution:report-interpretation"]["sections"]["arb_registered_prerequisites"]
        self.assertEqual("satisfied", prerequisites["state"])
        self.assertEqual("provider-free-mock-model-execution", prerequisites["evidence_class"])
        self.assertEqual(retained.generation_id, prerequisites["accepted_generation_id"])
        self.assertEqual(6, len(prerequisites["registered_logic_prerequisites"]))
        self.assertTrue(all(row["state"] == "satisfied" for row in prerequisites["registered_logic_prerequisites"]))
        completion = composition.session.completion_record(retained.generation_id)
        self.assertEqual("complete", completion["status"])
        self.assertNotIn("claim_eligibility", completion)


    def _assert_active_projection_common_evidence(
        self, plan, generation_id, observation, runner_test_request, selected_runner,
    ):
        """Exercise active file projection with actual registered process evidence."""
        categories = (
            "target", "submission", "runtime", "launch_environment",
            "authentication", "isolation", "request_framing", "process",
            "usage", "error",
        )
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    root / "evidence", benchmark_root=root,
                )
            )
            stage = store.root / generation_id / "observation-projection-check"
            stage.mkdir(parents=True)
            path = stage / "observation.json"

            def project(document):
                path.write_text(json.dumps(document), encoding="utf-8")
                return active_retained_progress_projection(generation_id, plan, store)

            expected = project(observation)
            self.assertEqual(1, expected.overall.completed_cases)
            stripped = copy.deepcopy(observation)
            for key in tuple(stripped["extensions"]):
                if (key.startswith("openai.codex_cli:") and key != "openai.codex_cli:session-record"):
                    del stripped["extensions"][key]
            stripped["extensions"]["test.target:misleading-state"] = {
                "terminal_status": "failed", "usage": "available",
                "process": {"stdout": "unavailable"},
            }
            self.assertEqual(0, project(stripped).overall.completed_cases)
            stripped["extensions"].pop("test.target:misleading-state")
            self.assertEqual(expected, project(stripped))

            for category in categories:
                for fault in ("missing", "invalid_availability"):
                    with self.subTest(category=category, fault=fault):
                        changed = copy.deepcopy(stripped)
                        execution = changed["extensions"]["arcgrav.runner:execution"]
                        if fault == "missing":
                            del execution[category]
                        else:
                            execution[category]["availability"] = "invented"
                        raw = json.dumps(changed).encode("utf-8")
                        for decoder in (
                            _decode_retained_json_documents, _decode_console_documents,
                        ):
                            documents, diagnostics = decoder(
                                (raw,), label="treatment observation",
                            )
                            self.assertEqual((), documents)
                            self.assertIn("invalid canonical execution evidence", diagnostics[0])
                        with self.assertRaises(ValueError):
                            _runner_test_result_from_observation(
                                selected_runner=selected_runner,
                                resolved=runner_test_request, observation=changed,
                            )
                        rejected = project(changed)
                        self.assertEqual(0, rejected.overall.completed_cases)
                        self.assertTrue(any(
                            "invalid canonical execution evidence" in event.text
                            for event in rejected.events
                        ))
                        self.assertTrue(all(
                            row.completed_cases == 0 for row in rejected.treatments
                        ))

    def test_retained_parity_observations_require_canonical_nested_evidence(self):
        for extensions in ({}, {"arcgrav.runner:execution": {"process": {}}}):
            raw = json.dumps({
                "runner": {"id": "arcgrav.mock-model.runner", "version": "1.0.0"},
                "extensions": extensions,
                "terminal_status": "completed",
            }).encode("utf-8")
            documents, diagnostics = _decode_retained_json_documents(
                (raw,), label="treatment observation"
            )
            self.assertEqual((), documents)
            self.assertEqual(1, len(diagnostics))
            self.assertIn("invalid canonical execution evidence", diagnostics[0])
            console_documents, console_diagnostics = _decode_console_documents(
                (raw,), label="treatment observation"
            )
            self.assertEqual((), console_documents)
            self.assertIn("invalid canonical execution evidence", console_diagnostics[0])

    def test_real_blocked_and_scored_zero_frontend_decoders_reject_invalid_common_evidence(self):
        for scenario in ("process_failure", "malformed_output"):
            with self.subTest(scenario=scenario):
                composition = compose_repository_planning_session(_REPOSITORY_ROOT)
                authority = composition.authority
                benchmark = next(
                    candidate for candidate in authority.benchmark_candidates
                    if candidate.registration["registration_id"]
                    == "arcgrav.authority-resolution.benchmark.core"
                )
                runner = next(
                    source for source in authority.runner_sources
                    if source.registration["registration_id"]
                    == "arcgrav.mock-model.runner"
                )
                intent = SidebarInputSnapshot(
                    benchmark=(f"{benchmark.registration['registration_id']}@"
                               f"{benchmark.registration['registration_version']}"),
                    runner=(f"{runner.registration['registration_id']}@"
                            f"{runner.registration['registration_version']}"),
                    model=f"mock-base::scenario:{scenario}",
                    credential="", temperature=None, max_tokens=None,
                )
                resolver = RepositoryApplicationRequestResolver(authority)
                request = resolver.resolve_plan_request(intent, authority.discovery)
                composition.session.build_plan(request)
                snapshot = composition.session.accept_plan()
                terminal = composition.session.execute_accepted_run(
                    resolver.resolve_execution_request(
                        request, snapshot, credential=""
                    )
                )
                self.assertIs(
                    BlockedRun if scenario == "process_failure" else AcceptedRun,
                    type(terminal),
                )
                retained_observation = terminal.treatment_observations[0]
                source = (
                    retained_observation
                    if isinstance(retained_observation, dict)
                    else json.loads(retained_observation)
                )
                validate_retained_parity_observation(source)
                for fault in ("missing_category", "missing_channel", "invalid_error"):
                    with self.subTest(fault=fault):
                        altered = copy.deepcopy(source)
                        execution = altered["extensions"]["arcgrav.runner:execution"]
                        if fault == "missing_category":
                            del execution["usage"]
                        elif fault == "missing_channel":
                            del execution["process"]["stdout"]["availability"]
                        else:
                            execution["error"]["availability"] = "invented"
                        raw = json.dumps(altered).encode("utf-8")
                        for decoder in (
                            _decode_retained_json_documents,
                            _decode_console_documents,
                        ):
                            documents, diagnostics = decoder(
                                (raw,), label="treatment observation"
                            )
                            self.assertEqual((), documents)
                            self.assertEqual(1, len(diagnostics))
                            self.assertIn(
                                "invalid canonical execution evidence", diagnostics[0]
                            )


    def test_real_repository_discovery_projects_only_validated_production_authority(self):
        authority = discover_repository_application_authority()

        self.assertEqual(_REPOSITORY_ROOT, authority.repository_root)
        self.assertTrue(
            authority.benchmark_candidates,
            "production discovery must expose at least one active benchmark registration",
        )
        self.assertTrue(
            authority.runner_sources,
            "production discovery must expose at least one active runner registration",
        )

        for candidate in authority.benchmark_candidates:
            self.assertTrue(candidate.registration_validation.valid)
            self.assertEqual("benchmark", candidate.registration["registration_kind"])
            self.assertEqual("active", candidate.registration["status"])
            self.assertTrue(
                candidate.registration_source_id.startswith("AgMark/")
            )
            self.assertNotIn(
                "shared/software_testing/",
                candidate.registration_source_id,
            )

        for source in authority.runner_sources:
            self.assertTrue(source.registration_validation.valid)
            self.assertEqual("runner", source.registration["registration_kind"])
            self.assertEqual("active", source.registration["status"])
            self.assertTrue(
                source.registration_source_id.startswith(
                    "AgMark/shared/adapters/"
                )
            )
            self.assertNotIn(
                "shared/software_testing/",
                source.registration_source_id,
            )

        expected_benchmarks = tuple(
            sorted(
                (
                    _candidate_identity(candidate)
                    for candidate in authority.benchmark_candidates
                ),
                key=lambda value: (value[0], value[1]),
            )
        )
        expected_runners = tuple(
            sorted(
                (_runner_identity(source) for source in authority.runner_sources),
                key=lambda value: (value[0], value[1]),
            )
        )

        self.assertEqual(
            expected_benchmarks,
            tuple(
                _projection_identity(value)
                for value in authority.discovery.benchmarks
            ),
        )
        self.assertEqual(
            expected_runners,
            tuple(
                _projection_identity(value)
                for value in authority.discovery.runners
            ),
        )

    def test_real_repository_authority_constructs_the_shared_planning_session(self):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)

        self.assertIs(type(composition.session), PlanningApplicationSession)
        self.assertTrue(composition.authority.benchmark_candidates)
        self.assertTrue(composition.authority.runner_sources)
        self.assertEqual(
            composition.authority.discovery,
            composition.session.discover(),
        )

    def test_treatment_randomization_is_planned_once_for_all_repetitions(self):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
        benchmark = next(
            candidate for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        runner = next(
            source for source in authority.runner_sources
            if source.registration["registration_id"]
            == "arcgrav.mock-model.runner"
        )
        intent = SidebarInputSnapshot(
            benchmark=(
                f"{benchmark.registration['registration_id']}@"
                f"{benchmark.registration['registration_version']}"
            ),
            runner=(
                f"{runner.registration['registration_id']}@"
                f"{runner.registration['registration_version']}"
            ),
            model="mock-base::scenario:completed",
            credential="", temperature=None, max_tokens=None, iterations=3,
            randomize_per_iteration=False,
            additional_controls=(),
        )
        resolver = RepositoryApplicationRequestResolver(authority)
        sequential = resolver.resolve_plan_request(
            replace(intent, randomize_treatment_start=False), authority.discovery
        )
        with unittest_mock.patch(
            "AgMark.gui.requests.resolver.shuffle",
            side_effect=lambda values: values.reverse(),
        ) as random_shuffle:
            randomized = resolver.resolve_plan_request(intent, authority.discovery)
        random_shuffle.assert_called_once_with(unittest_mock.ANY)
        self.assertGreater(len(sequential.treatments), 1)
        self.assertEqual(tuple(reversed(sequential.treatments)), randomized.treatments)
        self.assertEqual(sequential.treatment_set.sha256, randomized.treatment_set.sha256)
        self.assertFalse(sequential.extensions["arcgrav.runtime:randomize-treatment-start"])
        self.assertFalse(randomized.extensions["arcgrav.runtime:randomize-per-iteration"])
        with unittest_mock.patch(
            "AgMark.shared.runtime.orchestration.planning.shuffle",
            side_effect=AssertionError("one-time shuffle is already frozen in the request"),
        ):
            plan = composition.session.build_plan(randomized)
            snapshot = composition.session.accept_plan()
        self.assertTrue(snapshot.plan().to_dict()["extensions"]["arcgrav.runtime:randomize-treatment-start"])
        for case in randomized.cases:
            orders = [
                tuple(
                    observation.treatment_id
                    for observation in plan.observations
                    if observation.case_id == case.case_id and observation.repetition == repetition
                )
                for repetition in range(1, 4)
            ]
            self.assertEqual([randomized.treatments] * 3, orders)
        self.assertEqual(
            tuple(observation.observation_id for observation in plan.observations),
            tuple(observation.observation_id for observation in snapshot.plan().observations),
        )

    def test_treatment_randomization_per_iteration_is_frozen_before_acceptance(self):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
        benchmark = next(
            candidate for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        runner = next(
            source for source in authority.runner_sources
            if source.registration["registration_id"]
            == "arcgrav.mock-model.runner"
        )
        intent = SidebarInputSnapshot(
            benchmark=(
                f"{benchmark.registration['registration_id']}@"
                f"{benchmark.registration['registration_version']}"
            ),
            runner=(
                f"{runner.registration['registration_id']}@"
                f"{runner.registration['registration_version']}"
            ),
            model="mock-base::scenario:completed",
            credential="", temperature=None, max_tokens=None, iterations=3,
            randomize_per_iteration=True,
            additional_controls=(),
        )
        resolver = RepositoryApplicationRequestResolver(authority)
        with unittest_mock.patch(
            "AgMark.gui.requests.resolver.shuffle",
            side_effect=AssertionError("per-iteration shuffling belongs in planning"),
        ):
            request = resolver.resolve_plan_request(intent, authority.discovery)
        self.assertTrue(request.extensions["arcgrav.runtime:randomize-per-iteration"])
        expected_orders = []

        def rotate(values):
            offset = (len(expected_orders) + 1) % len(values)
            values[:] = values[offset:] + values[:offset]
            expected_orders.append(tuple(values))

        with unittest_mock.patch(
            "AgMark.shared.runtime.orchestration.planning.shuffle",
            side_effect=rotate,
        ) as random_shuffle:
            plan = composition.session.build_plan(request)
        self.assertEqual(3, random_shuffle.call_count)
        self.assertNotEqual(expected_orders[0], expected_orders[1])
        snapshot = composition.session.accept_plan()
        self.assertEqual(
            tuple(observation.observation_id for observation in plan.observations),
            tuple(observation.observation_id for observation in snapshot.plan().observations),
        )
        for case in request.cases:
            actual = [
                tuple(
                    observation.treatment_id for observation in plan.observations
                    if observation.case_id == case.case_id
                    and observation.repetition == repetition
                )
                for repetition in range(1, 4)
            ]
            self.assertEqual(expected_orders, actual)

        disabled = resolver.resolve_plan_request(
            replace(intent, randomize_treatment_start=False), authority.discovery
        )
        self.assertFalse(disabled.extensions["arcgrav.runtime:randomize-per-iteration"])
        with unittest_mock.patch(
            "AgMark.shared.runtime.orchestration.planning.shuffle",
            side_effect=AssertionError("parent disabled: no shuffling"),
        ):
            composition.session.build_plan(disabled)

    def test_real_repository_planning_resolution_uses_exact_registered_authority(self):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
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
        resolver = RepositoryApplicationRequestResolver(authority)
        intent = SidebarInputSnapshot(
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
            randomize_treatment_start=False,
            additional_controls=(),
        )

        request = resolver.resolve_plan_request(intent, authority.discovery)
        plan = composition.session.build_plan(request)
        registration = benchmark.registration
        selected = next(
            value["selected_authority"]
            for value in registration["extensions"].values()
            if isinstance(value, dict)
            and value.get("benchmark_id") == registration["registration_id"]
            and value.get("benchmark_version")
            == registration["registration_version"]
            and isinstance(value.get("selected_authority"), dict)
        )
        case_artifact = next(
            artifact
            for artifact in registration["implementation_artifacts"]
            if artifact["artifact_id"] == selected["case_set"]["artifact_id"]
        )
        treatment_artifact = next(
            artifact
            for artifact in registration["implementation_artifacts"]
            if artifact["artifact_id"] == selected["treatment_set"]["artifact_id"]
        )
        case_document = json.loads(
            (_REPOSITORY_ROOT / case_artifact["reference"]).read_text(
                encoding="utf-8"
            )
        )
        treatment_document = json.loads(
            (_REPOSITORY_ROOT / treatment_artifact["reference"]).read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(registration["registration_id"], request.benchmark.id)
        self.assertEqual(
            benchmark.registration_validation.registration_sha256,
            request.benchmark.sha256,
        )
        self.assertEqual(selected["case_set"]["id"], request.case_set.id)
        self.assertEqual(case_artifact["sha256"], request.case_set.sha256)
        self.assertEqual(selected["treatment_set"]["id"], request.treatment_set.id)
        self.assertEqual(treatment_artifact["sha256"], request.treatment_set.sha256)
        self.assertEqual(
            tuple(case["case_id"] for case in case_document["cases"]),
            tuple(case.case_id for case in request.cases),
        )
        self.assertEqual(
            tuple(treatment["treatment_id"] for treatment in treatment_document["treatments"]),
            request.treatments,
        )
        self.assertEqual(1, request.repetitions)
        self.assertTrue(request.golden_required)
        self.assertEqual(request.benchmark.id, plan.benchmark.id)
        self.assertEqual(request.case_set.id, plan.case_set.id)
        self.assertEqual(request.treatment_set.id, plan.treatment_set.id)
        self.assertEqual(
            len(request.cases) * len(request.treatments) * request.repetitions,
            len(plan.observations),
        )
        registered_contracts = {
            (contract["id"], contract["version"])
            for contract in registration["contracts"]
        }
        self.assertEqual(
            registered_contracts - {("arcgrav.shared.run-lifecycle", "1.0.0")},
            {(contract.id, contract.version) for contract in request.contracts},
        )
        self.assertEqual(
            registered_contracts,
            {(contract.id, contract.version) for contract in plan.contracts},
        )

        boundary = json.loads(
            request.execution_boundary.canonical_bytes.decode("utf-8")
        )
        self.assertEqual(
            runner.registration["registration_id"],
            boundary["runner"]["id"],
        )
        self.assertEqual(
            runner.registration_validation.registration_sha256,
            boundary["runner"]["sha256"],
        )
        self.assertEqual(
            "local_process",
            boundary["provider_runtime"]["access_method"],
        )
        controls = {
            item["name"]: item["value"]
            for item in boundary["controls"]
        }
        self.assertEqual(
            {
                "model_id": "mock-base::scenario:completed",
                "request_timeout_ms": 120000, "maximum_attempts": 1,
                "memory_policy": "disabled", "request_framing": "mock_json_v1",
                "sampling_mode": "deterministic", "tool_policy": "none",
            },
            controls,
        )
        environment = {
            item["name"]: item["value"]
            for item in boundary["environment"]
        }
        self.assertEqual("native", environment["golden.environment_family"])
        self.assertRegex(environment["golden.runtime_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("golden.runtime_executable", environment)

    def test_real_repository_execution_resolution_uses_exact_registered_authority(self):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
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
        resolver = RepositoryApplicationRequestResolver(authority)
        intent = SidebarInputSnapshot(
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

        request = resolver.resolve_plan_request(intent, authority.discovery)
        composition.session.build_plan(request)
        snapshot = composition.session.accept_plan()
        execution = resolver.resolve_execution_request(
            request,
            snapshot,
            credential="",
        )
        registration = benchmark.registration
        selected = next(
            value["selected_authority"]
            for value in registration["extensions"].values()
            if isinstance(value, dict)
            and value.get("benchmark_id") == registration["registration_id"]
            and value.get("benchmark_version")
            == registration["registration_version"]
            and isinstance(value.get("selected_authority"), dict)
        )
        golden_artifact = next(
            artifact
            for artifact in registration["implementation_artifacts"]
            if artifact["artifact_id"]
            == selected["golden_authority"]["artifact_id"]
        )

        self.assertTrue(execution.generation_id.startswith("generation-"))
        self.assertEqual(request.execution_boundary, execution.execution_boundary)
        self.assertEqual(
            _REPOSITORY_ROOT / benchmark.package_root,
            Path(execution.benchmark_root),
        )
        from AgMark.gui.requests import resolver as request_resolver
        requested_destination = request_resolver.FilesystemArtifactStore.call_args.args[0]
        self.assertEqual(
            _REPOSITORY_ROOT / "AgMark" / "run_evidence",
            requested_destination.root,
        )
        self.assertEqual(_REPOSITORY_ROOT, requested_destination.authority_root)
        self.assertEqual("central", requested_destination.ownership)
        self.assertEqual(
            self._test_evidence_root / _REPOSITORY_ROOT.name,
            execution.artifact_store.root,
        )
        self.assertEqual("external", execution.artifact_store.destination.ownership)
        self.assertEqual(
            runner.registration["registration_id"],
            execution.runner_registration["registration_id"],
        )
        self.assertEqual(
            tuple(case.case_id for case in request.cases),
            tuple(case.case_id for case in execution.case_inputs),
        )
        self.assertEqual(
            tuple(case.sha256 for case in request.cases),
            tuple(case.sha256 for case in execution.case_inputs),
        )
        self.assertEqual(
            request.treatments,
            tuple(prompt.treatment_id for prompt in execution.treatment_prompts),
        )
        self.assertEqual(1, len(execution.scoring_definitions))
        scoring = execution.scoring_definitions[0]
        self.assertEqual(
            selected["primary_metric"]["registration_id"],
            scoring.metric_registration["registration_id"],
        )
        self.assertEqual(
            selected["scorer"]["registration_id"],
            scoring.scorer_registration["registration_id"],
        )
        self.assertIsNotNone(execution.golden_declaration)
        self.assertEqual(
            golden_artifact["artifact_id"],
            execution.golden_declaration.entry_artifact_id,
        )
        self.assertEqual(
            golden_artifact["sha256"],
            execution.golden_declaration.golden_implementation.sha256,
        )
        self.assertEqual(
            tuple(case.case_id for case in execution.case_inputs),
            tuple(case.case_id for case in execution.golden_case_inputs),
        )
        self.assertEqual(
            tuple(case.sha256 for case in execution.case_inputs),
            tuple(case.sha256 for case in execution.golden_case_inputs),
        )
        self.assertIsNone(execution.transient_values)

        with self.assertRaisesRegex(
            RepositoryCompositionError,
            "without a registered transient binding",
        ):
            resolver.resolve_execution_request(
                request,
                snapshot,
                credential="must-not-be-retained",
            )

    def test_codex_explicit_model_is_bound_into_canonical_boundary(self):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
        benchmark = next(
            candidate
            for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        runner = next(
            source
            for source in authority.runner_sources
            if source.registration["registration_id"] == "openai.codex-cli"
        )
        resolver = RepositoryApplicationRequestResolver(
            authority,
            runner_planning_probe=_codex_planning_probe,
        )
        intent = SidebarInputSnapshot(
            benchmark=(
                f"{benchmark.registration['registration_id']}@"
                f"{benchmark.registration['registration_version']}"
            ),
            runner=(
                f"{runner.registration['registration_id']}@"
                f"{runner.registration['registration_version']}"
            ),
            model="gpt-5.6",
            credential="",
            temperature=None,
            max_tokens=None,
            additional_controls=(SidebarControlInputSnapshot("reasoning_effort", "medium"),
                                 SidebarControlInputSnapshot("codex_binary", "/home/private-owner/bin/codex")),
        )

        request = resolver.resolve_plan_request(intent, authority.discovery)
        boundary = request.execution_boundary.to_dict()
        controls = {
            item["name"]: item["value"]
            for item in boundary["controls"]
        }

        self.assertEqual("native", controls["launch_mode"])
        self.assertEqual("runtime/codex", controls["codex_binary"])
        self.assertNotIn("wsl_distribution", controls)
        self.assertEqual("/home/private-owner/bin/codex", resolver._launch_selections[id(request.execution_boundary)]["codex_binary"])
        self.assertNotIn(b"private-owner", request.execution_boundary.canonical_bytes)
        self.assertEqual("gpt-5.6", controls["model_id"])
        self.assertEqual("medium", controls["reasoning_effort"])
        self.assertEqual("gpt-5.6", boundary["provider_runtime"]["model"])
        self.assertEqual(
            _CODEX_RUNTIME_VERSION,
            boundary["provider_runtime"]["runtime_version"],
        )
        self.assertEqual("OpenAI", boundary["provider_runtime"]["provider"])
        self.assertIn(
            b'"model":"gpt-5.6"',
            request.execution_boundary.canonical_bytes,
        )

    def test_codex_planning_fails_closed_when_runtime_probe_is_unavailable(self):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
        benchmark = next(
            candidate
            for candidate in authority.benchmark_candidates
            if candidate.registration["registration_id"]
            == "arcgrav.authority-resolution.benchmark.core"
        )
        runner = next(
            source
            for source in authority.runner_sources
            if source.registration["registration_id"] == "openai.codex-cli"
        )
        resolver = RepositoryApplicationRequestResolver(
            authority,
            runner_planning_probe=lambda _source, _controls: {
                "status": "unsupported",
                "provider_submitted": False,
                "resolved_controls": {},
                "error_code": "codex_cli_version_unavailable",
            },
        )
        intent = SidebarInputSnapshot(
            benchmark=(
                f"{benchmark.registration['registration_id']}@"
                f"{benchmark.registration['registration_version']}"
            ),
            runner=(
                f"{runner.registration['registration_id']}@"
                f"{runner.registration['registration_version']}"
            ),
            model="gpt-5-codex",
            credential="",
            temperature=None,
            max_tokens=None,
            additional_controls=(),
        )

        with self.assertRaisesRegex(
            RepositoryCompositionError,
            "codex_cli_version_unavailable",
        ):
            resolver.resolve_plan_request(intent, authority.discovery)

    def test_real_repository_completion_uses_exact_accepted_authority(self):
        self._assert_repository_completion_iterations(1)

    def test_repeated_benchmark_rounds_preserve_completed_report(self):
        self._assert_repository_completion_iterations(3)

    def _assert_repository_completion_iterations(self, iterations):
        composition = compose_repository_planning_session(_REPOSITORY_ROOT)
        authority = composition.authority
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
        resolver = RepositoryApplicationRequestResolver(authority)
        intent = SidebarInputSnapshot(
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

        from dataclasses import replace
        intent = replace(intent, iterations=iterations)
        plan_request = resolver.resolve_plan_request(intent, authority.discovery)
        self.assertEqual(iterations, plan_request.repetitions)
        composition.session.build_plan(plan_request)
        snapshot = composition.session.accept_plan()
        execution_request = resolver.resolve_execution_request(
            plan_request,
            snapshot,
            credential="",
        )
        retained = composition.session.execute_accepted_run(execution_request)

        report_request = resolver.resolve_report_request(retained)
        selected = next(
            value["selected_authority"]
            for value in benchmark.registration["extensions"].values()
            if isinstance(value, dict)
            and value.get("benchmark_id")
            == benchmark.registration["registration_id"]
            and value.get("benchmark_version")
            == benchmark.registration["registration_version"]
            and isinstance(value.get("selected_authority"), dict)
        )
        report_selection = selected["report_configuration"]
        report_artifact = next(
            artifact
            for artifact in benchmark.registration["implementation_artifacts"]
            if artifact["artifact_id"] == report_selection["artifact_id"]
        )
        accepted_ids = {
            record.artifact_id
            for record in retained.artifact_index.artifacts
        }

        self.assertEqual(retained.generation_id, report_request.generation_id)
        self.assertEqual(
            retained.execution_boundary_fingerprint,
            report_request.observation_matrix[0].execution_boundary_fingerprint,
        )
        self.assertEqual(
            len(retained.treatment_observations),
            report_request.observation_counts.planned,
        )
        self.assertEqual(
            len(retained.treatment_observations),
            len(report_request.observation_matrix),
        )
        self.assertEqual(
            len(retained.score_artifacts) // iterations,
            len(report_request.case_result_matrix),
        )
        if iterations > 1:
            scores = [json.loads(raw) for raw in retained.score_artifacts]
            for case in report_request.case_result_matrix:
                exact = [score for score in scores if score['case_id'] == case.case_id
                         and score['treatment_id'] == case.treatment_id]
                self.assertEqual(iterations, len(exact))
                self.assertEqual(iterations, len(case.evidence_refs))
                self.assertEqual(sum(score['value'] for score in exact) / iterations, case.value)
        self.assertTrue(
            all(
                ref.artifact_id in accepted_ids
                for row in report_request.observation_matrix
                for ref in row.evidence_refs
            )
        )
        self.assertTrue(
            all(
                ref.artifact_id in accepted_ids
                for row in report_request.case_result_matrix
                for ref in row.evidence_refs
            )
        )
        self.assertEqual(
            selected["primary_metric"]["registration_id"],
            report_request.metrics[0].registration_id,
        )

        selection_extension = report_request.extensions[
            "arcgrav.gui:registered-report-selection"
        ]
        self.assertEqual(
            report_selection["registration_id"],
            selection_extension["configuration"]["id"],
        )
        self.assertEqual(
            report_artifact["sha256"],
            selection_extension["configuration"]["sha256"],
        )
        self.assertEqual(
            report_artifact["reference"],
            selection_extension["configuration"]["reference"],
        )

        bundle = composition.session.completed_report(retained.generation_id)
        self.assertIsNotNone(bundle)
        prerequisites = bundle.report_document["extensions"][
            "arcgrav.authority-resolution:report-interpretation"]["sections"]["arb_registered_prerequisites"]
        self.assertEqual("satisfied", prerequisites["state"])
        self.assertEqual("provider-free-mock-model-execution", prerequisites["evidence_class"])
        self.assertEqual(retained.generation_id, prerequisites["accepted_generation_id"])
        self.assertEqual(6, len(prerequisites["registered_logic_prerequisites"]))
        self.assertTrue(all(row["state"] == "satisfied" for row in prerequisites["registered_logic_prerequisites"]))
        completion = composition.session.completion_record(retained.generation_id)
        self.assertEqual("complete", completion["status"])
        self.assertNotIn("claim_eligibility", completion)

        original_bytes = tuple(component.data for component in (*bundle.components, bundle.manifest))
        self.assertIs(bundle, composition.session.completed_report(retained.generation_id))
        self.assertEqual(original_bytes, tuple(component.data for component in (*bundle.components, bundle.manifest)))

        from AgMark.gui.projection.workspace.results import _results_projection
        before = _results_projection(retained, None, plan=snapshot.plan(), store=execution_request.artifact_store)
        after = _results_projection(retained, bundle, plan=snapshot.plan(), store=execution_request.artifact_store)
        self.assertEqual(before, after)
        self.assertTrue(before.rows)
        for row in before.rows:
            self.assertIn("cached_input_tokens", row.measurements)
            self.assertIn("input_tokens", row.measurements)

    def test_real_repository_planning_resolution_does_not_invent_required_controls(self):
        authority = discover_repository_application_authority(_REPOSITORY_ROOT)
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
        resolver = RepositoryApplicationRequestResolver(authority)
        intent = SidebarInputSnapshot(
            benchmark=(
                f"{benchmark.registration['registration_id']}@"
                f"{benchmark.registration['registration_version']}"
            ),
            runner=(
                f"{runner.registration['registration_id']}@"
                f"{runner.registration['registration_version']}"
            ),
            model=None,
            credential="",
            temperature=None,
            max_tokens=None,
        )

        with unittest_mock.patch("subprocess.Popen") as transport:
            with self.assertRaisesRegex(
                RepositoryCompositionError,
                "mock_boundary_unsupported",
            ):
                resolver.resolve_plan_request(intent, authority.discovery)
            transport.assert_not_called()

    def test_repository_discovery_separates_inspection_diagnostics_from_application_prerequisites(self):
        with TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            adapter_root = root / "AgMark/shared/adapters/Broken"
            adapter_root.mkdir(parents=True)
            _copy_registration_schema_authority(root)

            malformed = adapter_root / "malformed.json"
            malformed.write_text("{not-valid-json", encoding="utf-8")

            metric_registration = (
                _REPOSITORY_ROOT
                / "AgMark/Authority_Resolution_Benchmark/registrations/v2.0.0"
                / "metric-field-accuracy.json"
            )
            (adapter_root / "metric-dedicated-schema.json").write_bytes(
                metric_registration.read_bytes()
            )
            invalid_metric = json.loads(
                metric_registration.read_text(encoding="utf-8")
            )
            invalid_metric["registration_kind"] = "metric"
            (adapter_root / "invalid-metric-dedicated-schema.json").write_text(
                json.dumps(invalid_metric),
                encoding="utf-8",
            )

            for registration_kind in (
                "metric",
                "scorer",
                "report_configuration",
                "golden_runtime",
                "reconstruction_procedure",
                "other",
            ):
                (adapter_root / f"{registration_kind}.json").write_text(
                    json.dumps(
                        {
                            "schema_id": "arcgrav.shared.schema.registration",
                            "schema_version": "1.0.0",
                            "extensions": {},
                            "registration_id": f"supported.{registration_kind}",
                            "registration_version": "1.0.0",
                            "registration_kind": registration_kind,
                            "status": "active",
                            "contracts": [],
                            "implementation_artifacts": [],
                            "capabilities": [],
                            "limitations": [],
                        }
                    ),
                    encoding="utf-8",
                )

            (adapter_root / "invalid-scorer.json").write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.registration",
                        "schema_version": "1.0.0",
                        "extensions": {},
                        "registration_id": "invalid.scorer",
                        "registration_version": "1.0.0",
                        "registration_kind": "scorer",
                        "status": "active",
                        "implementation_artifacts": [],
                        "capabilities": [],
                        "limitations": [],
                    }
                ),
                encoding="utf-8",
            )

            unsupported_non_application = adapter_root / "unsupported-scorer.json"
            unsupported_non_application.write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.unsupported",
                        "schema_version": "1.0.0",
                        "registration_id": "unsupported.scorer",
                        "registration_version": "1.0.0",
                        "registration_kind": "scorer",
                        "status": "active",
                    }
                ),
                encoding="utf-8",
            )

            unknown_family = adapter_root / "unknown-family.json"
            unknown_family.write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.registration",
                        "schema_version": "1.0.0",
                        "registration_id": "unknown.family",
                        "registration_version": "1.0.0",
                        "registration_kind": "unrecognized-extension",
                        "status": "active",
                    }
                ),
                encoding="utf-8",
            )

            unsupported_runner = adapter_root / "unsupported-runner.json"
            unsupported_runner.write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.unsupported",
                        "schema_version": "1.0.0",
                        "extensions": {},
                        "registration_id": "unsupported.runner",
                        "registration_version": "1.0.0",
                        "registration_kind": "runner",
                        "status": "active",
                        "contracts": [],
                        "implementation_artifacts": [],
                        "capabilities": [],
                        "limitations": [],
                    }
                ),
                encoding="utf-8",
            )

            invalid_benchmark = adapter_root / "invalid-benchmark.json"
            invalid_benchmark.write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.registration",
                        "schema_version": "1.0.0",
                        "extensions": {},
                        "registration_id": "broken.benchmark",
                        "registration_version": "1.0.0",
                        "registration_kind": "benchmark",
                        "status": "active",
                        "contracts": [],
                        "implementation_artifacts": [],
                        "capabilities": [],
                        "limitations": [],
                    }
                ),
                encoding="utf-8",
            )

            missing_artifact = adapter_root / "registration.json"
            missing_artifact.write_text(
                json.dumps(
                    {
                        "schema_id": "arcgrav.shared.schema.registration",
                        "schema_version": "1.0.0",
                        "extensions": {},
                        "registration_id": "broken.runner",
                        "registration_version": "1.0.0",
                        "registration_kind": "runner",
                        "status": "active",
                        "contracts": [],
                        "implementation_artifacts": [
                            {
                                "artifact_id": "missing-runner.py",
                                "sha256": "sha256:" + "0" * 64,
                                "reference": "AgMark/shared/adapters/Broken/missing-runner.py",
                            }
                        ],
                        "capabilities": [],
                        "limitations": [],
                    }
                ),
                encoding="utf-8",
            )

            authority = discover_repository_application_authority(root)
            repeated = discover_repository_application_authority(root)
            self.assertEqual(
                authority.repository_diagnostics,
                repeated.repository_diagnostics,
            )
            repository_diagnostics = {
                (issue.source_id, issue.code, issue.json_pointer)
                for issue in authority.repository_diagnostics
            }
            self.assertEqual(
                {
                    (
                        "AgMark/shared/adapters/Broken/invalid-metric-dedicated-schema.json",
                        "SCHEMA_STRUCTURE_INVALID",
                        "/registration_kind",
                    ),
                    (
                        "AgMark/shared/adapters/Broken/invalid-scorer.json",
                        "SCHEMA_STRUCTURE_INVALID",
                        "/contracts",
                    ),
                    (
                        "AgMark/shared/adapters/Broken/unsupported-scorer.json",
                        "REGISTRATION_SCHEMA_UNSUPPORTED",
                        "/schema_id",
                    ),
                    (
                        "AgMark/shared/adapters/Broken/unknown-family.json",
                        "REGISTRATION_FAMILY_UNSUPPORTED",
                        "/registration_kind",
                    ),
                },
                repository_diagnostics,
            )

            diagnostic_names = {
                diagnostic.diagnostic_name
                for diagnostic in authority.prerequisite_diagnostics
            }

            self.assertIn(
                "repository-registration-discovery:AgMark/shared/adapters/Broken/malformed.json",
                diagnostic_names,
            )
            self.assertEqual(
                {
                    "repository-registration-discovery:AgMark/shared/adapters/Broken/malformed.json",
                    "repository-registration-location:AgMark/shared/adapters/Broken/invalid-benchmark.json",
                    "repository-artifact-access:AgMark/shared/adapters/Broken/registration.json",
                    "repository-registration-validation:AgMark/shared/adapters/Broken/unsupported-runner.json",
                },
                diagnostic_names,
            )
            self.assertEqual((), authority.benchmark_candidates)
            self.assertEqual((), authority.discovery.benchmarks)
            self.assertEqual((), authority.runner_sources)
            self.assertEqual((), authority.discovery.runners)


if __name__ == "__main__":
    unittest.main()
