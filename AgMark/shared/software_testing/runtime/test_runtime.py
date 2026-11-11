"""Provider-free runtime tests for accepted identity and terminal artifact authority."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from AgMark.shared.runtime.artifacts import (
    ArtifactIntegrityError,
    ArtifactPathError,
    ArtifactPayload,
    BlockedEvidenceRole,
    FilesystemArtifactStore,
    GenerationReuseError,
    PublicationDestination,
    RETAINABLE_EVIDENCE,
    TerminalAuthorityConflictError,
    TerminalPublicationError,
    publish_accepted_artifact_index,
    publish_blocked_artifact_manifest,
    retain_artifact_stage,
)
from AgMark.shared.runtime.identity import (
    AcceptedBoundaryIdentity,
    ExecutionBoundary,
    IdentityIntegrityError,
    IdentityRef,
    ProviderRuntimeIdentity,
)
from AgMark.shared.validation import (
    ValidationIssue,
    validate_lifecycle_evidence,
    validate_lifecycle_evidence_outcome,
)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _boundary(*, runner_bytes: bytes = b"runner-v1") -> ExecutionBoundary:
    return ExecutionBoundary.build(
        boundary_id="boundary-runtime-test",
        framework=IdentityRef(
            "arcgrav.framework.runtime-test",
            "1.0.0",
            sha256=_sha256(b"framework-v1"),
        ),
        runner=IdentityRef(
            "arcgrav.runner.runtime-test",
            "1.0.0",
            sha256=_sha256(runner_bytes),
        ),
        provider_runtime=ProviderRuntimeIdentity(
            runtime_id="arcgrav.runtime.provider-free",
            runtime_version="1.0.0",
            provider=None,
            access_method="in_process",
            model=None,
        ),
        controls={
            "network_access": "disabled",
            "memory_policy": "disabled",
        },
        environment={"runtime_family": "provider-free"},
    )


def _store(benchmark_root: Path) -> FilesystemArtifactStore:
    return FilesystemArtifactStore(
        PublicationDestination.benchmark_owned(
            benchmark_root / "evidence",
            benchmark_root=benchmark_root,
        )
    )


def _payload(
    artifact_id: str,
    role: str,
    relative_path: str,
    data: bytes,
) -> ArtifactPayload:
    return ArtifactPayload(
        artifact_id=artifact_id,
        role=role,
        relative_path=relative_path,
        data=data,
        provenance="runtime-software-test",
        retention_class=RETAINABLE_EVIDENCE,
        media_type="application/octet-stream",
    )


class AcceptedIdentityRuntimeTests(unittest.TestCase):
    def test_accepted_boundary_is_immutable_and_exactly_reresolved(self) -> None:
        boundary = _boundary()
        accepted = AcceptedBoundaryIdentity.accept(
            accepted_identity_id="accepted-boundary-runtime-test",
            boundary=boundary,
        )

        with self.assertRaises(FrozenInstanceError):
            accepted.boundary_id = "changed"  # type: ignore[misc]

        resolved = accepted.revalidate(boundary.to_dict())
        self.assertEqual(boundary.canonical_bytes, resolved.canonical_bytes)
        self.assertEqual(boundary.fingerprint, resolved.fingerprint)

    def test_source_identity_drift_fails_closed_after_acceptance(self) -> None:
        accepted = AcceptedBoundaryIdentity.accept(
            accepted_identity_id="accepted-boundary-runtime-test",
            boundary=_boundary(runner_bytes=b"runner-v1"),
        )
        drifted = _boundary(runner_bytes=b"runner-v2")

        with self.assertRaises(IdentityIntegrityError):
            accepted.revalidate(drifted.to_dict())


class StagedArtifactRuntimeTests(unittest.TestCase):
    def test_stage_retains_exact_bytes_and_revalidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            data = b"immutable-golden-observation"
            (record,) = retain_artifact_stage(
                store=store,
                generation_id="generation-staged",
                stage_id="golden",
                artifacts=(
                    _payload(
                        "golden-observation",
                        "golden_observation",
                        "observations/golden.bin",
                        data,
                    ),
                ),
            )

            self.assertEqual(
                "generation-staged/golden/observations/golden.bin",
                record.reference,
            )
            self.assertEqual(_sha256(data), record.sha256)
            self.assertEqual(data, (store.root / record.reference).read_bytes())
            store.revalidate(record)

    def test_stage_writes_request_binary_mode_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            real_open = os.open
            binary_flag = 1 << 29
            opened: list[tuple[int, int]] = []

            def recording_open(path, flags, mode=0o777, *, dir_fd=None):
                opened.append((flags, mode))
                kwargs = {} if dir_fd is None else {"dir_fd": dir_fd}
                return real_open(path, flags & ~binary_flag, mode, **kwargs)

            with (
                mock.patch.object(os, "O_BINARY", binary_flag, create=True),
                mock.patch(
                    "AgMark.shared.runtime.artifacts.staging.os.open",
                    side_effect=recording_open,
                ),
            ):
                retain_artifact_stage(
                    store=store,
                    generation_id="generation-binary-stage",
                    stage_id="golden",
                    artifacts=(
                        _payload(
                            "golden-output",
                            "golden_output",
                            "outputs/golden.bin",
                            b"line-one\nline-two\n",
                        ),
                    ),
                )

            self.assertTrue(
                any(mode == 0o600 and flags & binary_flag for flags, mode in opened)
            )

    def test_stage_rejects_nonportable_path_segments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            payloads = (
                _payload(
                    "golden-command",
                    "golden_command",
                    "commands/golden.bin",
                    b"command",
                ),
            )

            with self.assertRaises(ArtifactPathError):
                retain_artifact_stage(
                    store=store,
                    generation_id="generation:windows",
                    stage_id="golden",
                    artifacts=payloads,
                )

            with self.assertRaises(ArtifactPathError):
                retain_artifact_stage(
                    store=store,
                    generation_id="generation-portable",
                    stage_id="observation:windows",
                    artifacts=payloads,
                )

    def test_stage_is_write_once_for_generation_and_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            payloads = (
                _payload(
                    "golden-command",
                    "golden_command",
                    "commands/golden.bin",
                    b"command",
                ),
            )
            retain_artifact_stage(
                store=store,
                generation_id="generation-stage-reuse",
                stage_id="golden",
                artifacts=payloads,
            )

            with self.assertRaises(GenerationReuseError):
                retain_artifact_stage(
                    store=store,
                    generation_id="generation-stage-reuse",
                    stage_id="golden",
                    artifacts=payloads,
                )

    def test_terminal_generation_rejects_late_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            records = retain_artifact_stage(
                store=store,
                generation_id="generation-terminal-stage",
                stage_id="golden",
                artifacts=(
                    _payload(
                        "golden-output",
                        "golden_output",
                        "outputs/golden.bin",
                        b"golden-output",
                    ),
                ),
            )
            publish_accepted_artifact_index(
                store=store,
                generation_id="generation-terminal-stage",
                terminal_status="accepted",
                artifacts=records,
            )

            with self.assertRaises(GenerationReuseError):
                retain_artifact_stage(
                    store=store,
                    generation_id="generation-terminal-stage",
                    stage_id="treatment",
                    artifacts=(
                        _payload(
                            "treatment-output",
                            "treatment_output",
                            "outputs/treatment.bin",
                            b"treatment-output",
                        ),
                    ),
                )

    def test_staged_artifact_drift_fails_authority_sensitive_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            (record,) = retain_artifact_stage(
                store=store,
                generation_id="generation-stage-drift",
                stage_id="golden",
                artifacts=(
                    _payload(
                        "golden-evidence",
                        "golden_evidence",
                        "evidence/golden.bin",
                        b"authoritative-golden-evidence",
                    ),
                ),
            )
            retained_path = store.root / record.reference
            retained_path.chmod(0o600)
            retained_path.write_bytes(b"tampered-golden-evidence")

            with self.assertRaises(ArtifactIntegrityError):
                store.revalidate(record)


class TerminalArtifactRuntimeTests(unittest.TestCase):
    def test_accepted_publication_revalidates_exact_retained_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            records = store.publish_generation(
                "generation-accepted",
                (
                    _payload(
                        "score-1",
                        "score_artifact",
                        "scores/score-1.bin",
                        b"score-bytes",
                    ),
                ),
            )

            index = publish_accepted_artifact_index(
                store=store,
                generation_id="generation-accepted",
                terminal_status="accepted",
                artifacts=records,
            )

            self.assertEqual("generation-accepted", index.generation_id)
            self.assertEqual(records, index.artifacts)
            self.assertEqual(
                [
                    {
                        "artifact_id": "score-1",
                        "sha256": _sha256(b"score-bytes"),
                        "reference": "generation-accepted/scores/score-1.bin",
                        "availability": "retained",
                    }
                ],
                index.to_run_outcome_field(),
            )

    def test_accepted_publication_rejects_artifacts_from_another_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            records = store.publish_generation(
                "generation-source",
                (
                    _payload(
                        "score-cross-generation",
                        "score_artifact",
                        "scores/score-cross-generation.bin",
                        b"score-bytes",
                    ),
                ),
            )

            with self.assertRaises(TerminalPublicationError):
                publish_accepted_artifact_index(
                    store=store,
                    generation_id="generation-target",
                    terminal_status="accepted",
                    artifacts=records,
                )

    def test_retained_artifact_drift_blocks_accepted_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            records = store.publish_generation(
                "generation-drift",
                (
                    _payload(
                        "observation-1",
                        "treatment_observation",
                        "observations/observation-1.bin",
                        b"authoritative-observation",
                    ),
                ),
            )

            retained_path = store.root / records[0].reference
            retained_path.chmod(0o600)
            retained_path.write_bytes(b"tampered-observation")

            with self.assertRaises(ArtifactIntegrityError):
                publish_accepted_artifact_index(
                    store=store,
                    generation_id="generation-drift",
                    terminal_status="accepted",
                    artifacts=records,
                )

    def test_blocked_manifest_preserves_retained_and_not_produced_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            (diagnostic,) = store.publish_generation(
                "generation-blocked",
                (
                    _payload(
                        "golden-diagnostic",
                        "golden_diagnostic",
                        "diagnostics/golden.txt",
                        b"golden failed before treatment authorization",
                    ),
                ),
            )

            manifest = publish_blocked_artifact_manifest(
                store=store,
                generation_id="generation-blocked",
                terminal_status="blocked",
                reason_code="golden_gate_failed",
                diagnostics=("golden admission blocked the run",),
                evidence_roles=(
                    BlockedEvidenceRole(
                        "golden_diagnostic",
                        "retained",
                        "golden failure evidence is retained",
                    ),
                    BlockedEvidenceRole(
                        "treatment_observations",
                        "not_produced",
                        "treatment execution was never authorized",
                    ),
                    BlockedEvidenceRole(
                        "score_artifacts",
                        "not_produced",
                        "no treatment observation existed to score",
                    ),
                ),
                retained_diagnostics=(diagnostic,),
            )

            states = {
                role.role: role.availability for role in manifest.evidence_roles
            }
            self.assertEqual("retained", states["golden_diagnostic"])
            self.assertEqual("not_produced", states["treatment_observations"])
            self.assertEqual("not_produced", states["score_artifacts"])
            projection = manifest.to_run_outcome_field()
            self.assertEqual("golden_gate_failed", projection["reason_code"])
            self.assertEqual(
                "generation-blocked/diagnostics/golden.txt",
                projection["retained_diagnostics"][0]["reference"],
            )

    def test_failed_accepted_publication_does_not_claim_terminal_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)

            with self.assertRaises(TerminalPublicationError):
                publish_accepted_artifact_index(
                    store=store,
                    generation_id="generation-incomplete-accepted",
                    terminal_status="accepted",
                    artifacts=(),
                )

            manifest = publish_blocked_artifact_manifest(
                store=store,
                generation_id="generation-incomplete-accepted",
                terminal_status="blocked",
                reason_code="accepted_output_incomplete",
                evidence_roles=(
                    BlockedEvidenceRole(
                        "accepted_artifacts",
                        "not_produced",
                        "accepted publication failed before terminal authority",
                    ),
                ),
            )
            self.assertEqual("generation-incomplete-accepted", manifest.generation_id)

    def test_accepted_terminal_authority_cannot_be_republished_with_partial_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            records = store.publish_generation(
                "generation-accepted-single-assignment",
                (
                    _payload(
                        "observation-final",
                        "treatment_observation",
                        "observations/final.bin",
                        b"final-observation",
                    ),
                    _payload(
                        "score-final",
                        "score_artifact",
                        "scores/final.bin",
                        b"final-score",
                    ),
                ),
            )
            publish_accepted_artifact_index(
                store=store,
                generation_id="generation-accepted-single-assignment",
                terminal_status="accepted",
                artifacts=records,
            )

            with self.assertRaises(TerminalAuthorityConflictError):
                publish_accepted_artifact_index(
                    store=store,
                    generation_id="generation-accepted-single-assignment",
                    terminal_status="accepted",
                    artifacts=(records[0],),
                )

    def test_blocked_manifest_rejects_contradictory_retained_role_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            (diagnostic,) = store.publish_generation(
                "generation-blocked-contradiction",
                (
                    _payload(
                        "golden-diagnostic-contradiction",
                        "golden_diagnostic",
                        "diagnostics/golden.txt",
                        b"retained golden failure",
                    ),
                ),
            )

            with self.assertRaises(TerminalPublicationError):
                publish_blocked_artifact_manifest(
                    store=store,
                    generation_id="generation-blocked-contradiction",
                    terminal_status="blocked",
                    reason_code="golden_gate_failed",
                    evidence_roles=(
                        BlockedEvidenceRole(
                            "golden_diagnostic",
                            "not_produced",
                            "contradicts the retained diagnostic",
                        ),
                    ),
                    retained_diagnostics=(diagnostic,),
                )

            manifest = publish_blocked_artifact_manifest(
                store=store,
                generation_id="generation-blocked-contradiction",
                terminal_status="blocked",
                reason_code="golden_gate_failed",
                evidence_roles=(
                    BlockedEvidenceRole(
                        "golden_diagnostic",
                        "retained",
                        "golden failure evidence is retained",
                    ),
                ),
                retained_diagnostics=(diagnostic,),
            )
            self.assertEqual("retained", manifest.evidence_roles[0].availability)

    def test_blocked_terminal_authority_is_single_assignment_and_rejects_late_retention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            publish_blocked_artifact_manifest(
                store=store,
                generation_id="generation-blocked-single-assignment",
                terminal_status="blocked",
                reason_code="golden_gate_failed",
                evidence_roles=(
                    BlockedEvidenceRole(
                        "treatment_observations",
                        "not_produced",
                        "treatment execution was never authorized",
                    ),
                ),
            )

            with self.assertRaises(TerminalAuthorityConflictError):
                publish_blocked_artifact_manifest(
                    store=store,
                    generation_id="generation-blocked-single-assignment",
                    terminal_status="blocked",
                    reason_code="different_terminal_reason",
                    evidence_roles=(
                        BlockedEvidenceRole(
                            "treatment_observations",
                            "unavailable",
                            "a later caller cannot rewrite terminal authority",
                        ),
                    ),
                )

            with self.assertRaises(GenerationReuseError):
                store.publish_generation(
                    "generation-blocked-single-assignment",
                    (
                        _payload(
                            "late-diagnostic",
                            "late_diagnostic",
                            "diagnostics/late.bin",
                            b"late",
                        ),
                    ),
                )

    def test_generation_cannot_publish_opposite_terminal_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            store = _store(benchmark_root)
            records = store.publish_generation(
                "generation-terminal",
                (
                    _payload(
                        "final-evidence",
                        "final_evidence",
                        "final/evidence.bin",
                        b"final",
                    ),
                ),
            )
            publish_accepted_artifact_index(
                store=store,
                generation_id="generation-terminal",
                terminal_status="accepted",
                artifacts=records,
            )

            with self.assertRaises(TerminalAuthorityConflictError):
                publish_blocked_artifact_manifest(
                    store=store,
                    generation_id="generation-terminal",
                    terminal_status="blocked",
                    reason_code="late_failure",
                )


class LifecycleValidationRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_id = "runtime-lifecycle-validation"
        self.generation_id = "generation-lifecycle-runtime"
        self.boundary = _sha256(b"boundary-lifecycle-runtime")
        self.plan_hash = _sha256(b"run-plan-lifecycle-runtime")
        self.golden_contract = {
            "id": "arcgrav.shared.contract.golden-execution",
            "version": "1.0.0",
        }
        self.treatment_contract = {
            "id": "arcgrav.shared.contract.runner-invocation",
            "version": "1.0.0",
        }
        self.run_plan = {
            "schema_id": "arcgrav.shared.schema.run-plan",
            "schema_version": "1.0.0",
            "run_plan_id": "plan-lifecycle-runtime",
            "plan_sha256": self.plan_hash,
            "execution_boundary_fingerprint": self.boundary,
            "golden_required": True,
            "contracts": [
                self.golden_contract,
                self.treatment_contract,
            ],
            "repetitions": 1,
            "observations": [
                {
                    "request_id": "request-case-a-treatment-a-r1",
                    "observation_id": "observation-case-a-treatment-a-r1",
                    "case_id": "case-a",
                    "treatment_id": "treatment-a",
                    "repetition": 1,
                    "execution_boundary_fingerprint": self.boundary,
                }
            ],
        }
        self.golden_observation = {
            "schema_id": "arcgrav.shared.schema.golden-observation",
            "schema_version": "2.0.0",
            "accepted_generation_id": self.generation_id,
            "execution_boundary_fingerprint": self.boundary,
            "contract": self.golden_contract,
            "started_at": "2026-01-01T00:01:10Z",
            "completed_at": "2026-01-01T00:01:20Z",
            "admission_state": "admitted",
            "status": "completed",
            "output": {"availability": "retained"},
        }
        self.treatment_observation = {
            "schema_id": "arcgrav.shared.schema.treatment-observation",
            "schema_version": "1.0.0",
            "accepted_generation_id": self.generation_id,
            "execution_boundary_fingerprint": self.boundary,
            "contract": self.treatment_contract,
            "request_id": "request-case-a-treatment-a-r1",
            "observation_id": "observation-case-a-treatment-a-r1",
            "case_id": "case-a",
            "treatment_id": "treatment-a",
            "repetition": 1,
            "attempts": [
                {
                    "started_at": "2026-01-01T00:01:30Z",
                    "completed_at": "2026-01-01T00:01:40Z",
                }
            ],
        }
        self.score_artifact = {
            "schema_id": "arcgrav.shared.schema.score-artifact",
            "schema_version": "1.0.0",
            "accepted_generation_id": self.generation_id,
            "execution_boundary_fingerprint": self.boundary,
            "observation_ids": ["observation-case-a-treatment-a-r1"],
        }
        self.run_outcome = {
            "schema_id": "arcgrav.shared.schema.run-outcome",
            "schema_version": "1.0.0",
            "generation_id": self.generation_id,
            "execution_boundary_fingerprint": self.boundary,
            "run_plan": {
                "artifact_id": self.run_plan["run_plan_id"],
                "sha256": self.plan_hash,
            },
            "status": "accepted",
            "artifact_index": [
                {
                    "artifact_id": "accepted-lifecycle-evidence",
                    "sha256": _sha256(b"accepted-lifecycle-evidence"),
                    "reference": "accepted/lifecycle-evidence.json",
                    "availability": "retained",
                }
            ],
            "finalized_at": "2026-01-01T00:02:00Z",
        }

    def _validate(
        self,
        *,
        run_plan: dict[str, object] | None = None,
        plan_completed_at: str = "2026-01-01T00:00:00Z",
        accepted_at: str = "2026-01-01T00:01:00Z",
        run_outcome: dict[str, object] | None = None,
        golden_observation: dict[str, object] | None = None,
        treatment_observations: tuple[dict[str, object], ...] | None = None,
        score_artifacts: tuple[dict[str, object], ...] | None = None,
    ) -> tuple[ValidationIssue, ...]:
        return validate_lifecycle_evidence(
            run_plan=run_plan or self.run_plan,
            plan_completed_at=plan_completed_at,
            accepted_at=accepted_at,
            run_outcome=run_outcome or self.run_outcome,
            golden_observation=(
                self.golden_observation
                if golden_observation is None
                else golden_observation
            ),
            treatment_observations=(
                (self.treatment_observation,)
                if treatment_observations is None
                else treatment_observations
            ),
            score_artifacts=(
                (self.score_artifact,)
                if score_artifacts is None
                else score_artifacts
            ),
            source_id=self.source_id,
        )

    def test_valid_lifecycle_binds_exact_terminal_authority(self) -> None:
        self.assertEqual((), self._validate())

        authority = validate_lifecycle_evidence_outcome(
            run_plan=self.run_plan,
            plan_completed_at="2026-01-01T00:00:00Z",
            accepted_at="2026-01-01T00:01:00Z",
            run_outcome=self.run_outcome,
            golden_observation=self.golden_observation,
            treatment_observations=(self.treatment_observation,),
            score_artifacts=(self.score_artifact,),
            source_id=self.source_id,
        )
        self.assertTrue(authority.valid)
        self.assertTrue(authority.matches(self.run_outcome, source_id=self.source_id))

        changed_outcome = copy.deepcopy(self.run_outcome)
        changed_outcome["finalized_at"] = "2026-01-01T00:02:01Z"
        self.assertFalse(authority.matches(changed_outcome, source_id=self.source_id))

    def test_plan_and_golden_chronology_fail_closed(self) -> None:
        treatment = copy.deepcopy(self.treatment_observation)
        treatment["attempts"][0]["started_at"] = "2026-01-01T00:01:15Z"

        issues = self._validate(
            plan_completed_at="2026-01-01T00:01:05Z",
            treatment_observations=(treatment,),
        )
        codes = {issue.code for issue in issues}
        self.assertIn("LIFECYCLE_PLAN_AFTER_ACCEPTANCE", codes)
        self.assertIn("LIFECYCLE_TREATMENT_BEFORE_GOLDEN_AUTHORITY", codes)

    def test_accepted_identity_and_complete_matrix_are_enforced(self) -> None:
        outcome = copy.deepcopy(self.run_outcome)
        outcome["execution_boundary_fingerprint"] = _sha256(b"wrong-boundary")
        outcome["run_plan"]["sha256"] = _sha256(b"wrong-plan")
        treatment = copy.deepcopy(self.treatment_observation)
        treatment["accepted_generation_id"] = "generation-other"

        issues = self._validate(
            run_outcome=outcome,
            treatment_observations=(treatment,),
        )
        codes = {issue.code for issue in issues}
        self.assertIn("LIFECYCLE_EXECUTION_BOUNDARY_MISMATCH", codes)
        self.assertIn("LIFECYCLE_RUN_PLAN_HASH_MISMATCH", codes)
        self.assertIn("LIFECYCLE_TREATMENT_GENERATION_MISMATCH", codes)

        incomplete_plan = copy.deepcopy(self.run_plan)
        incomplete_plan["observations"] = [
            self.run_plan["observations"][0],
            {
                "request_id": "request-case-a-treatment-b-r1",
                "observation_id": "observation-case-a-treatment-b-r1",
                "case_id": "case-a",
                "treatment_id": "treatment-b",
                "repetition": 1,
                "execution_boundary_fingerprint": self.boundary,
            },
            {
                "request_id": "request-case-b-treatment-a-r1",
                "observation_id": "observation-case-b-treatment-a-r1",
                "case_id": "case-b",
                "treatment_id": "treatment-a",
                "repetition": 1,
                "execution_boundary_fingerprint": self.boundary,
            },
        ]
        matrix_issues = self._validate(run_plan=incomplete_plan)
        self.assertIn(
            "LIFECYCLE_PLAN_MATRIX_INCOMPLETE",
            {issue.code for issue in matrix_issues},
        )

    def test_score_references_and_terminal_authority_remain_separate(self) -> None:
        score = copy.deepcopy(self.score_artifact)
        score["observation_ids"] = ["observation-not-retained"]
        accepted_mixed = copy.deepcopy(self.run_outcome)
        accepted_mixed["blocked_manifest"] = {}

        issues = self._validate(
            run_outcome=accepted_mixed,
            score_artifacts=(score,),
        )
        codes = {issue.code for issue in issues}
        self.assertIn("LIFECYCLE_SCORE_INPUT_UNKNOWN", codes)
        self.assertIn("LIFECYCLE_TERMINAL_AUTHORITY_MIXED", codes)

        blocked_mixed = copy.deepcopy(self.run_outcome)
        blocked_mixed["status"] = "blocked"
        blocked_mixed["blocked_manifest"] = {}
        blocked_issues = self._validate(run_outcome=blocked_mixed)
        self.assertIn(
            "LIFECYCLE_TERMINAL_AUTHORITY_MIXED",
            {issue.code for issue in blocked_issues},
        )


if __name__ == "__main__":
    unittest.main()
