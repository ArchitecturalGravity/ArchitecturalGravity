"""Retained terminal evidence projection coverage for the desktop GUI."""

from __future__ import annotations

import base64
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from AgMark.shared.adapters._contract import validate_runner_request
from AgMark.shared.adapters.execution import (
    ExecutionIsolation,
    InvocationCapture,
    TargetCompositionDescriptor,
    TerminalExecutionResult,
    emit_terminal_observation,
    validate_retained_parity_observation,
)
from AgMark.gui.application import _terminal_console_update
from AgMark.gui.widgets.console import BottomConsoleState
from AgMark.gui.workspace_projection import (
    active_retained_progress_projection,
    _artifacts_projection,
    _active_progress_projection,
    _progress_projection,
    _reports_projection,
    _results_projection,
    _verification_projection,
)
from AgMark.shared.reporting import (
    GeneratedReportBundle,
    GeneratedReportComponent,
)
from AgMark.shared.runtime.artifacts import (
    ArtifactRecord,
    FilesystemArtifactStore,
    PublicationDestination,
    sha256_bytes,
)
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.runtime.orchestration import AcceptedRun
from AgMark.shared.runtime.orchestration import PlannedCaseInput, plan_run


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _observation(
    treatment_id: str,
    response: str,
    *,
    extension_key: str = "test.runner:response_base64",
    runner_id: str = "test.runner",
    runner_version: str = "1.0.0",
    response_bytes: int | None = None,
    stderr_bytes: int = 9,
    observation_id: str | None = None,
    generation_id: str = "generation-retained",
    case_id: str = "case-retained",
    repetition: int = 1,
    boundary_fingerprint: str | None = None,
) -> dict[str, object]:
    """Create a complete shared-contract fixture, without executing an adapter."""
    response_payload = response.encode("utf-8")
    prompt, input_payload = b"fixture prompt", b"fixture input"
    fingerprint = boundary_fingerprint or sha256_bytes(b"projection fixture boundary")
    identity = observation_id or f"observation:{treatment_id}"
    validated = validate_runner_request({
        "accepted_generation_id": generation_id,
        "request_id": f"request:{identity}",
        "observation_id": identity,
        "benchmark_id": "test.projection-benchmark",
        "case_id": case_id,
        "treatment_id": treatment_id,
        "repetition": repetition,
        "execution_boundary_fingerprint": fingerprint,
        "execution_boundary": {
            "fingerprint": fingerprint,
            "runner": {"id": runner_id, "version": runner_version},
            "provider_runtime": {
                "runtime_id": runner_id, "runtime_version": runner_version,
                "provider": "Projection test fixture", "access_method": "local_process",
                "model": "fixture-model",
            },
            "controls": [],
        },
        "conversation_policy": {"new_conversation": True, "reuse_prior_observation_context": False},
        "prompt": {"content": prompt, "sha256": sha256_bytes(prompt)},
        "input": {"content": input_payload, "sha256": sha256_bytes(input_payload)},
        "request_identity": {
            "prompt_sha256": sha256_bytes(prompt),
            "input_sha256": sha256_bytes(input_payload),
            "request_sha256": sha256_bytes(prompt + input_payload),
        },
    })
    target = TargetCompositionDescriptor.create(
        target_class="mock-model", evidence_class="synthetic-projection-fixture",
        runtime_id=runner_id, runtime_version=runner_version,
        access_method="local_process", external_provider_submission=False,
        launch_mode="native", launch_environment_selector={},
        executable="projection-test-fixture", authentication_class="not_applicable",
        compatibility_profile=None, production_runner_entry_point="test.projection:FixtureRunner",
        runner_implementation_artifact_ids=("test.projection:fixture",),
    )
    execution = TerminalExecutionResult(
        terminal_status="completed", failure_kind=None,
        started_at="2026-09-27T00:00:00Z", completed_at="2026-09-27T00:00:01Z",
        duration_ms=1000.0, invocation_occurred=True,
        capture=InvocationCapture(True, 0, "fixture", response_payload, b"x" * stderr_bytes),
        response_bytes=response_payload,
        isolation=ExecutionIsolation(True, True, False, False),
    )
    observation = emit_terminal_observation(
        validated, target=target, execution=execution,
        runner_id=runner_id, runner_version=runner_version,
        framed_request=prompt + input_payload, request_framing_mode="projection-test-fixture",
        extensions={"arcgrav.shared.runtime.orchestration:execution-window": {
            "started_at": execution.started_at, "completed_at": execution.completed_at,
        }},
    )
    response_key = f"{runner_id}:response_base64"
    if extension_key != response_key:
        observation["extensions"][extension_key] = observation["extensions"].pop(response_key)
        observation["response"]["reference"] = f"extensions:/{extension_key}"
    if response_bytes is not None:
        next(item for item in observation["telemetry"] if item["name"] == "response_bytes")["value"] = response_bytes
    validate_retained_parity_observation(observation)
    return observation


def _score(treatment_id: str, diagnostic: str) -> dict[str, object]:
    return {
        "treatment_id": treatment_id,
        "availability": "invalid",
        "diagnostics": (diagnostic,),
        "unit": "proportion",
    }


def _accepted_run(
    *,
    observations: tuple[dict[str, object], ...] = (),
    score_artifacts: tuple[dict[str, object], ...] = (),
    raw_observations: tuple[bytes, ...] = (),
    raw_scores: tuple[bytes, ...] = (),
    generation_id: str = "generation-retained",
) -> AcceptedRun:
    run = object.__new__(AcceptedRun)
    object.__setattr__(run, "run_outcome_bytes", b'{"extensions": {}}')
    object.__setattr__(run, "generation_id", generation_id)
    object.__setattr__(
        run,
        "treatment_observations",
        raw_observations or tuple(
            _json_bytes({**value, "accepted_generation_id": generation_id})
            for value in observations
        ),
    )
    object.__setattr__(
        run,
        "score_artifacts",
        raw_scores or tuple(_json_bytes(value) for value in score_artifacts),
    )
    object.__setattr__(run, "artifact_index", SimpleNamespace(artifacts=()))
    return run


def _sha256(value: str) -> str:
    return "sha256:" + value * 64


def _active_plan():
    boundary = ExecutionBoundary.build(
        boundary_id="boundary-active-progress",
        framework=IdentityRef("arcgrav.framework.frontend-test", "1.0.0"),
        runner=IdentityRef("test.runner", "1.0.0"),
        provider_runtime=ProviderRuntimeIdentity(
            runtime_id="test.runner",
            runtime_version="1.0.0",
            provider="Projection test fixture",
            access_method="local_process",
            model="fixture-model",
        ),
        controls={"memory_policy": "disabled"},
        environment={"runtime_family": "provider"},
    )
    return plan_run(
        benchmark=IdentityRef(
            "arcgrav.benchmark.frontend-test",
            "1.0.0",
            sha256=_sha256("b"),
        ),
        case_set=IdentityRef(
            "arcgrav.case-set.frontend-test",
            "1.0.0",
            sha256=_sha256("c"),
        ),
        treatment_set=IdentityRef(
            "arcgrav.treatment-set.frontend-test",
            "1.0.0",
            sha256=_sha256("d"),
        ),
        cases=(PlannedCaseInput("case-1", _sha256("1")),),
        treatments=("arb-yaml", "arb-xml"),
        repetitions=1,
        execution_boundary=boundary,
        golden_required=False,
    )


class RetainedEvidenceProjectionTests(unittest.TestCase):
    def test_retained_observation_requires_common_contract_evidence(self) -> None:
        for missing in ("contract", "execution"):
            with self.subTest(missing=missing):
                observation = _observation("generic-treatment", "retained")
                if missing == "contract":
                    del observation["contract"]
                else:
                    del observation["extensions"]["arcgrav.runner:execution"]
                projection = _progress_projection(_accepted_run(observations=(observation,)))
                self.assertIsNone(projection.overall)
                self.assertTrue(any(
                    "invalid canonical execution evidence" in event.text
                    for event in projection.events
                ))

    def test_terminal_artifacts_projection_does_not_require_report_bundle(self) -> None:
        run = _accepted_run()
        object.__setattr__(
            run,
            "artifact_index",
            SimpleNamespace(
                artifacts=(
                    ArtifactRecord(
                        artifact_id="artifact-1",
                        role="treatment_observation",
                        reference="generation-retained/observation.json",
                        sha256=_sha256("a"),
                        provenance="test",
                        media_type="application/json",
                        encoding="utf-8",
                    ),
                )
            ),
        )

        projection = _artifacts_projection(run, None, None)

        self.assertEqual(["artifact-1"], [row.artifact_id for row in projection.rows])

    def test_live_artifact_store_enables_hash_bound_actions(self):
        run = _accepted_run()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / run.generation_id / "observation.json"
            path.parent.mkdir()
            path.write_bytes(b"{}")
            record = ArtifactRecord("artifact-live", "treatment_observation",
                path.relative_to(root).as_posix(), sha256_bytes(b"{}"), "test")
            object.__setattr__(run, "artifact_index", SimpleNamespace(artifacts=(record,)))
            store = FilesystemArtifactStore(PublicationDestination.benchmark_owned(root, benchmark_root=root))
            projection = _artifacts_projection(run, None, None, store=store)
            self.assertTrue(projection.rows[0].open_action.available)
            self.assertTrue(projection.rows[0].reveal_action.available)
            path.write_bytes(b"changed")
            self.assertFalse(_artifacts_projection(run, None, None, store=store).rows[0].open_action.available)

    def test_active_progress_counts_observation_slots_and_reads_retained_files(self) -> None:
        plan = _active_plan()
        initial = _active_progress_projection("generation-active", plan)

        self.assertIsNotNone(initial.overall)
        assert initial.overall is not None
        self.assertEqual(0, initial.overall.completed_cases)
        self.assertEqual(2, initial.overall.total_cases)
        self.assertEqual(
            {"arb-yaml": 1, "arb-xml": 1},
            {row.treatment_id: row.total_cases for row in initial.treatments},
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    root / "evidence",
                    benchmark_root=root,
                )
            )
            slot = plan.observations[0]
            stage = (
                store.root
                / "generation-active"
                / (
                    "observation-"
                    + slot.observation_id.removeprefix("observation:")
                    + "-observation"
                )
            )
            stage.mkdir(parents=True)
            (stage / "observation.json").write_text(
                json.dumps(
                    _observation(
                        slot.treatment_id, "retained response",
                        observation_id=slot.observation_id, generation_id="generation-active",
                        case_id=slot.case_id, repetition=slot.repetition,
                        boundary_fingerprint=plan.execution_boundary_fingerprint,
                    )
                ),
                encoding="utf-8",
            )

            projection = active_retained_progress_projection(
                "generation-active",
                plan,
                store,
            )

        self.assertIsNotNone(projection.overall)
        assert projection.overall is not None
        self.assertEqual(1, projection.overall.completed_cases)
        self.assertEqual(2, projection.overall.total_cases)
        by_treatment = {row.treatment_id: row for row in projection.treatments}
        self.assertEqual(1, by_treatment[slot.treatment_id].completed_cases)
        self.assertEqual(0, by_treatment["arb-xml"].completed_cases)
        self.assertTrue(
            any(slot.treatment_id in event.text for event in projection.events)
        )

    def test_accepted_run_progress_projects_retained_observation_rows(self) -> None:
        run = _accepted_run(
            observations=(
                _observation("arb-markdown", "markdown response"),
                _observation("arb-yaml", "yaml response", stderr_bytes=11),
            )
        )

        projection = _progress_projection(run)

        self.assertIsNotNone(projection.overall)
        assert projection.overall is not None
        self.assertEqual(projection.overall.completed_cases, 2)
        self.assertEqual(projection.overall.total_cases, 2)
        self.assertEqual(
            [row.treatment for row in projection.treatments],
            ["arb-markdown", "arb-yaml"],
        )
        self.assertTrue(
            all("Waiting" not in row.status for row in projection.treatments)
        )
        self.assertTrue(
            all(row.completed_cases == 1 for row in projection.treatments)
        )
        self.assertIn("response", projection.treatments[0].status)
        self.assertEqual(len(projection.events), 2)

    def test_accepted_run_results_project_retained_score_diagnostics(self) -> None:
        run = _accepted_run(
            score_artifacts=(
                _score("arb-markdown", "ARB_GOLDEN_MALFORMED"),
            )
        )

        projection = _results_projection(run, None)

        self.assertEqual(1, len(projection.rows))
        row = projection.rows[0]
        self.assertEqual(row.treatment, "arb-markdown")
        self.assertIsNone(row.score)
        self.assertIn("invalid", row.evidence)
        self.assertIn("ARB_GOLDEN_MALFORMED", row.status)
        self.assertEqual(row.status_semantics, "error")

    def test_verified_synthetic_profile_remains_diagnostic_in_workspace(self) -> None:
        # Project shared typed report/verification results, never GUI-owned
        # mock scenarios or claim-authority shortcuts.
        def component(name: str) -> GeneratedReportComponent:
            return GeneratedReportComponent(
                artifact_id=f"synthetic-report:{name}",
                reference=f"generated/{name}.json",
                data=b"{}",
                media_type="application/json",
                encoding="utf-8",
            )

        report_document = {
            "report_id": "synthetic-report",
            "accepted_generation_id": "generation-synthetic",
            "status": "complete",
            "generated_at": "2026-09-28T00:00:00Z",
            "extensions": {
                "arcgrav.reporting:synthetic-conformance": {
                    "model_identity_kind": "synthetic_conformance_profile",
                },
            },
        }
        bundle = GeneratedReportBundle(
            report_document=report_document,
            canonical_evidence_document={
                "execution_boundary_fingerprint": _sha256("f"),
            },
            report_manifest={"manifest_id": "manifest-synthetic"},
            report=component("machine"),
            canonical_evidence=component("evidence"),
            human=component("human"),
            manifest=component("manifest"),
        )
        commands = SimpleNamespace()
        run = _accepted_run(generation_id="generation-synthetic")
        reports = _reports_projection(run, bundle, None, commands)
        self.assertEqual("passed", reports.verification_state)

        self.assertEqual(bundle.human.data.decode(), reports.readable_content)
        self.assertIn("Synthetic conformance", reports.limitations)
        self.assertEqual("Synthetic conformance evidence from deterministic fixtures; no live model measurements.", reports.limitations)
        self.assertFalse(reports.export_action.available)
        with self.assertRaises(ValueError):
            _reports_projection(_accepted_run(generation_id="generation-other"), bundle, None, commands)
        completed = _verification_projection(run, bundle, None, commands)
        self.assertEqual("passed", completed.banner.status)
        self.assertIsNone(completed.banner.summary)
        self.assertIsNone(completed.summary.notes)
        self.assertIsNone(completed.checks_empty_state)
        generic_bundle = replace(bundle, report_document={**report_document, "extensions": {"vendor:decoration": {"label": "live"}}})
        generic = _reports_projection(run, generic_bundle, None, commands)
        self.assertEqual("", generic.limitations)
        self.assertEqual(reports.verification_state, generic.verification_state)

        self.assertEqual(reports.export_action.available, generic.export_action.available)

    def test_terminal_console_update_decodes_generic_raw_responses(self) -> None:
        run = _accepted_run(
            observations=(
                _observation("arb-codex", "codex retained response"),
                _observation(
                    "mock-deterministic",
                    "mock retained response",
                    extension_key="mock.runner:response_base64",
                    runner_id="mock.runner",
                    runner_version="1.0.0",
                ),
            ),
            score_artifacts=(
                _score("arb-codex", "ARB_GOLDEN_MALFORMED"),
            ),
        )

        update = _terminal_console_update(run)

        self.assertTrue(update.bind_generation)
        self.assertEqual(
            (("observation:arb-codex", None, "codex retained response"),
             ("observation:mock-deterministic", None, "mock retained response")),
            update.live_view,
        )
        self.assertFalse(update.raw_response_supplied)
        self.assertIsNone(update.raw_response)

        live_output = "".join(update.live_output)
        self.assertIn("Generation: generation-retained", live_output)
        self.assertIn("Runner: test.runner@1.0.0", live_output)
        self.assertIn("Treatments completed: 2/2", live_output)
        self.assertIn("Response bytes:", live_output)
        self.assertIn("Stderr bytes:", live_output)
        self.assertIn("ARB_GOLDEN_MALFORMED x1", live_output)

    def test_console_rejects_stale_generation_raw_response_update(self) -> None:
        run = _accepted_run(
            observations=(_observation("arb-codex", "retained"),),
            generation_id="generation-old",
        )
        update = _terminal_console_update(run)
        state = BottomConsoleState()
        state.bind_generation("generation-current")

        self.assertFalse(
            state.set_raw_response(update.generation_id, update.raw_response)
        )
        self.assertFalse(state.raw_response_available)
        self.assertIsNone(state.retained_raw_response)

    def test_console_rejects_altered_retained_response_bytes(self) -> None:
        for alteration in ("bytes", "length", "availability"):
            with self.subTest(alteration=alteration):
                observation = _observation("arb-generic", "retained")
                if alteration == "bytes":
                    observation["extensions"]["test.runner:response_base64"] = (
                        base64.b64encode(b"altered").decode("ascii")
                    )
                elif alteration == "length":
                    observation["response"]["byte_length"] += 1
                else:
                    observation["response"]["availability"] = "unavailable"
                update = _terminal_console_update(
                    _accepted_run(observations=(observation,))
                )
                self.assertIsNone(update.raw_response)
                self.assertFalse(update.raw_response_supplied)
                self.assertEqual((("observation:arb-generic", None, None),), update.live_view)
                self.assertTrue(
                    any("response" in diagnostic.lower() for diagnostic in update.diagnostics)
                )

    def test_console_byte_summary_keeps_missing_telemetry_unavailable(self) -> None:
        missing = _observation("arb-missing", "retained")
        missing["telemetry"] = []
        update = _terminal_console_update(_accepted_run(observations=(missing,)))
        output = "".join(update.live_output)
        self.assertIn(
            "Response bytes: Unavailable (arb-missing=unavailable)", output
        )
        self.assertIn(
            "Stderr bytes: Unavailable (arb-missing=unavailable)", output
        )

        observed = _observation("arb-observed", "bytes")
        mixed = _terminal_console_update(
            _accepted_run(observations=(observed, missing))
        )
        mixed_output = "".join(mixed.live_output)
        self.assertIn("Response bytes: 5 observed total", mixed_output)
        self.assertIn("arb-missing=unavailable", mixed_output)

    def test_malformed_retained_json_is_nonfatal_and_visible(self) -> None:
        run = _accepted_run(
            raw_observations=(b"{",),
            raw_scores=(b"[]",),
        )

        progress = _progress_projection(run)
        results = _results_projection(run, None)
        update = _terminal_console_update(run)

        self.assertTrue(
            any("could not be decoded" in event.text for event in progress.events)
        )
        self.assertEqual(1, len(results.rows))
        self.assertEqual(results.rows[0].evidence, "decode_error")
        self.assertTrue(
            any("could not be decoded" in value for value in update.diagnostics)
        )
        self.assertTrue(
            any("is not a JSON object" in value for value in update.diagnostics)
        )


if __name__ == "__main__":
    unittest.main()
