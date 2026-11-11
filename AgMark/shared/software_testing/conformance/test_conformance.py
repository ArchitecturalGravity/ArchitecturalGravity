"""Provider-free conformance tests for shared registered authority surfaces."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from AgMark.shared.adapters.Mock_Model import load_registration
from AgMark.shared.software_testing.adapters.mock_model_support import resolve_model_identity
from AgMark.shared.adapters.Mock_Model import MockRunner
from AgMark.shared.runtime.artifacts import (
    FilesystemArtifactStore,
    PublicationDestination,
)
from AgMark.shared.runtime.golden import (
    GoldenArtifactRequirement,
    GoldenCaseInput,
    GoldenDeclaration,
    TransientEnvironmentBinding,
    execute_required_golden,
)
from AgMark.shared.runtime.identity import (
    AcceptedBoundaryIdentity,
    ExecutionBoundary,
    IdentityIntegrityError,
    IdentityRef,
    ProviderRuntimeIdentity,
    SecretIdentityInputError,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_CATALOG = _REPOSITORY_ROOT / "AgMark/shared/schemas/catalog.json"

_RUNNER_ID = "arcgrav.mock-model.runner"
_RUNNER_VERSION = "1.0.0"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _boundary(
    *,
    boundary_id: str = "boundary-conformance",
    controls: dict[str, object] | None = None,
    environment: dict[str, object] | None = None,
) -> ExecutionBoundary:
    return ExecutionBoundary.build(
        boundary_id=boundary_id,
        framework=IdentityRef("arcgrav.framework.conformance-test", "1.0.0"),
        runner=IdentityRef(_RUNNER_ID, _RUNNER_VERSION),
        provider_runtime=resolve_model_identity("mock-base::scenario:completed")[0],
        controls=controls if controls is not None else resolve_model_identity("mock-base::scenario:completed")[1],
        environment=environment or {},
    )


def _runner_request(boundary: ExecutionBoundary) -> dict[str, object]:
    prompt = b"conformance prompt"
    case_input = b"conformance input"
    return {
        "accepted_generation_id": "generation-conformance",
        "request_id": "request-conformance",
        "observation_id": "observation-conformance",
        "benchmark_id": "benchmark-conformance",
        "case_id": "case-conformance",
        "treatment_id": "treatment-conformance",
        "repetition": 1,
        "execution_boundary_fingerprint": boundary.fingerprint,
        "execution_boundary": boundary.to_dict(),
        "conversation_policy": {
            "new_conversation": True,
            "reuse_prior_observation_context": False,
        },
        "prompt": {
            "content": prompt,
            "sha256": _sha256(prompt),
        },
        "input": {
            "content": case_input,
            "sha256": _sha256(case_input),
        },
        "request_identity": {
            "prompt_sha256": _sha256(prompt),
            "input_sha256": _sha256(case_input),
            "request_sha256": _sha256(b"request-conformance"),
        },
    }


class IdentityConformanceTests(unittest.TestCase):
    def test_exact_reresolution_accepts_only_exact_retained_boundary(self) -> None:
        boundary = _boundary(
            controls=resolve_model_identity("mock-base::scenario:completed")[1]
        )
        accepted = AcceptedBoundaryIdentity.accept(
            accepted_identity_id="accepted-boundary-conformance",
            boundary=boundary,
        )

        resolved = accepted.revalidate(boundary.to_dict())
        self.assertEqual(boundary.canonical_sha256, resolved.canonical_sha256)
        self.assertEqual(boundary.fingerprint, resolved.fingerprint)

        tampered = copy.deepcopy(boundary.to_dict())
        for control in tampered["controls"]:
            if control["name"] == "model_id":
                control["value"] = "mock-base::scenario:empty_response"
                break

        with self.assertRaises(IdentityIntegrityError):
            accepted.revalidate(tampered)

    def test_secret_bearing_identity_inputs_are_rejected(self) -> None:
        with self.assertRaises(SecretIdentityInputError):
            _boundary(controls={"api_key": "not-retainable"})

        with self.assertRaises(SecretIdentityInputError):
            ExecutionBoundary.build(
                boundary_id="boundary-secret-extension",
                framework=IdentityRef("arcgrav.framework.conformance-test", "1.0.0"),
                runner=IdentityRef(_RUNNER_ID, _RUNNER_VERSION),
                provider_runtime=ProviderRuntimeIdentity(
                    runtime_id="arcgrav.runtime.provider-free",
                    runtime_version="1.0.0",
                    provider=None,
                    access_method="in_process",
                    model=None,
                ),
                extensions={"arcgrav.test:credential_locator": "ENV:SECRET"},
            )


class CatalogConformanceTests(unittest.TestCase):
    def test_schema_catalog_exactly_matches_published_schema_identity(self) -> None:
        catalog = json.loads(_SCHEMA_CATALOG.read_text(encoding="utf-8"))
        self.assertEqual("arcgrav.shared.schema.catalog", catalog["schema_id"])
        self.assertEqual("1.0.0", catalog["schema_version"])

        identities: set[tuple[str, str]] = set()
        urns: set[str] = set()
        files: set[str] = set()

        for entry in catalog["entries"]:
            identity = (entry["schema_id"], entry["schema_version"])
            self.assertNotIn(identity, identities)
            self.assertNotIn(entry["urn"], urns)
            self.assertNotIn(entry["file"], files)
            identities.add(identity)
            urns.add(entry["urn"])
            files.add(entry["file"])

            schema_path = _REPOSITORY_ROOT / entry["file"]
            self.assertTrue(schema_path.is_file(), entry["file"])
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(entry["schema_id"], schema["schema_id"])
            self.assertEqual(entry["schema_version"], schema["schema_version"])
            self.assertEqual(entry["urn"], schema["$id"])

            policy = schema["x-arcgrav-extension-policy"]
            self.assertEqual(entry["extension_points"], policy["extension_points"])
            for key, value in entry["extension_policy"].items():
                self.assertEqual(value, policy[key], f"{entry['file']}: {key}")


class RunnerRegistrationConformanceTests(unittest.TestCase):
    def test_registered_runner_identity_and_contract_are_exact(self) -> None:
        registration = load_registration()
        runner = MockRunner(registration=registration)
        description = runner.describe()

        self.assertEqual(_RUNNER_ID, registration["registration_id"])
        self.assertEqual(_RUNNER_VERSION, registration["registration_version"])
        self.assertEqual("runner", registration["registration_kind"])
        self.assertEqual("active", registration["status"])
        self.assertEqual(
            {"id": _RUNNER_ID, "version": _RUNNER_VERSION},
            description["runner"],
        )
        self.assertEqual(
            {"id": "arcgrav.shared.runner-invocation", "version": "2.0.0"},
            description["contract"],
        )
        self.assertIn(description["contract"], registration["contracts"])
        self.assertEqual(registration, description["registration"])
        self.assertFalse(registration["extensions"]["arcgrav.adapters:target_composition"]["external_provider_submission"])
        self.assertIsNone(registration["extensions"]["arcgrav.adapters:target_composition"]["authentication_source"])

    def test_registered_implementation_artifacts_match_exact_bytes(self) -> None:
        registration = load_registration()

        for artifact in registration["implementation_artifacts"]:
            reference = artifact["reference"]
            source_path = _REPOSITORY_ROOT / reference
            self.assertTrue(source_path.is_file(), reference)
            self.assertEqual(reference, artifact["artifact_id"])
            self.assertEqual(artifact["sha256"], _sha256(source_path.read_bytes()))

    def test_unsupported_boundary_control_fails_closed(self) -> None:
        from AgMark.shared.runtime.identity.boundary import IdentityError
        with self.assertRaises(IdentityError):
            _boundary(controls={"undeclared_control": True})


class TransientInvocationConformanceTests(unittest.TestCase):
    def test_declared_transient_binding_is_invocation_only_and_not_retained(self) -> None:
        secret = "conformance-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            benchmark_root = Path(directory).resolve()
            script = benchmark_root / "golden.py"
            expected_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
            script.write_text(
                "import hashlib, os, sys\n"
                "value = os.environ.get('ARCGRAV_CONFORMANCE_SECRET')\n"
                f"expected_digest = {expected_digest!r}\n"
                "if value is None or hashlib.sha256(value.encode('utf-8')).hexdigest() != expected_digest:\n"
                "    raise SystemExit(7)\n"
                "sys.stdout.write('ok')\n",
                encoding="utf-8",
            )

            executable = Path(sys.executable).resolve(strict=True)
            boundary = _boundary(
                boundary_id="boundary-golden-transient",
                environment={
                    "golden.environment_family": "native",
                    "golden.runtime_sha256": _sha256(executable.read_bytes()),
                },
            )
            accepted = AcceptedBoundaryIdentity.accept(
                accepted_identity_id="accepted-golden-transient",
                boundary=boundary,
            )
            declaration = GoldenDeclaration(
                golden_implementation=IdentityRef(
                    "arcgrav.golden.conformance-test",
                    "1.0.0",
                ),
                runtime_executable=str(executable),
                runtime_identity=IdentityRef(
                    "arcgrav.runtime.python",
                    "1.0.0",
                    sha256=_sha256(executable.read_bytes()),
                    reference="runtime/python",
                ),
                artifacts=(
                    GoldenArtifactRequirement(
                        artifact_id="golden.py",
                        relative_path="golden.py",
                        sha256=_sha256(script.read_bytes()),
                    ),
                ),
                entry_artifact_id="golden.py",
                environment_family="native",
                transient_environment=(
                    TransientEnvironmentBinding(
                        source_id="conformance-secret",
                        environment_variable="ARCGRAV_CONFORMANCE_SECRET",
                    ),
                ),
            )
            evidence_root = benchmark_root / "evidence"
            store = FilesystemArtifactStore(
                PublicationDestination.benchmark_owned(
                    evidence_root,
                    benchmark_root=benchmark_root,
                )
            )

            result = execute_required_golden(
                accepted_generation_id="generation-transient-valid",
                benchmark=IdentityRef("arcgrav.benchmark.conformance-test", "1.0.0"),
                benchmark_root=benchmark_root,
                accepted_boundary=accepted,
                retained_boundary_document=boundary.to_dict(),
                declaration=declaration,
                case_input=GoldenCaseInput("case-transient", b"input"),
                artifact_store=store,
                transient_values={"conformance-secret": secret},
            )

            self.assertTrue(result.treatment_authorized)
            self.assertEqual("admitted", result.observation["admission_state"])
            self.assertNotIn(secret.encode("utf-8"), result.observation_bytes)
            for retained_file in evidence_root.rglob("*"):
                if retained_file.is_file():
                    self.assertNotIn(secret.encode("utf-8"), retained_file.read_bytes())

            blocked = execute_required_golden(
                accepted_generation_id="generation-transient-invalid",
                benchmark=IdentityRef("arcgrav.benchmark.conformance-test", "1.0.0"),
                benchmark_root=benchmark_root,
                accepted_boundary=accepted,
                retained_boundary_document=boundary.to_dict(),
                declaration=declaration,
                case_input=GoldenCaseInput("case-transient", b"input"),
                artifact_store=store,
                transient_values={
                    "conformance-secret": secret,
                    "undeclared-secret": "must-not-bind",
                },
            )

            self.assertFalse(blocked.treatment_authorized)
            self.assertEqual("blocked", blocked.observation["admission_state"])
            self.assertEqual("failed", blocked.observation["status"])
            self.assertTrue(
                any(
                    "GOLDEN_TRANSIENT_MATERIAL_UNDECLARED" in diagnostic
                    for diagnostic in blocked.observation["diagnostics"]
                )
            )
            self.assertNotIn(secret.encode("utf-8"), blocked.observation_bytes)
            for retained_file in evidence_root.rglob("*"):
                if retained_file.is_file():
                    self.assertNotIn(secret.encode("utf-8"), retained_file.read_bytes())


if __name__ == "__main__":
    unittest.main()
