"""Registered mock discovery and preservation of accepted boundary identity."""

from pathlib import Path
import json
import hashlib
import unittest

from AgMark.gui.composition import discover_repository_application_authority
from AgMark.shared.runtime.identity import AcceptedBoundaryIdentity, ExecutionBoundary, IdentityRef, ProviderRuntimeIdentity

_ROOT = Path(__file__).resolve().parents[4]
_RUNNER = "arcgrav.mock-model.runner"


class RegisteredRunnerIdentityTests(unittest.TestCase):
    def test_repository_discovery_includes_registered_mock(self):
        authority = discover_repository_application_authority(_ROOT)
        ids = {source.registration["registration_id"] for source in authority.runner_sources}
        self.assertIn("arcgrav.mock-model.runner", ids)
        self.assertNotIn("arcgrav.mock-model.codex-cli", ids)
        self.assertNotIn("fixture.codex-protocol", ids)

    def test_retained_runtime_version_helper_is_integrity_bound_for_both_runners(self):
        reference = "AgMark/shared/runtime/identity/runtime_version.py"
        expected = "sha256:" + hashlib.sha256((_ROOT / reference).read_bytes()).hexdigest()
        authority = discover_repository_application_authority(_ROOT)
        for source in authority.runner_sources:
            if source.registration["registration_id"] not in {"arcgrav.mock-model.runner", "openai.codex-cli"}:
                continue
            with self.subTest(runner=source.registration["registration_id"]):
                matches = [item for item in source.registration["implementation_artifacts"]
                           if item["reference"] == reference]
                self.assertEqual(1, len(matches))
                self.assertEqual(expected, matches[0]["sha256"])

    def test_accepted_boundary_keeps_exact_identity(self):
        boundary = ExecutionBoundary.build(
            boundary_id="accepted-diagnostic",
            framework=IdentityRef("arcgrav.framework.fixture", "1.0.0"),
            runner=IdentityRef(_RUNNER, "1.0.0"),
            provider_runtime=ProviderRuntimeIdentity(
                runtime_id="arcgrav.runtime.provider-free", runtime_version="1.0.0",
                provider=None, access_method="in_process", model=None,
            ),
            controls={"mock_outcome": "completed", "response_mode": "request_digest"},
        )
        original = boundary.to_dict()
        serialized = json.dumps(original, sort_keys=True).encode()
        accepted = AcceptedBoundaryIdentity.accept(accepted_identity_id="accepted-accepted", boundary=boundary)
        accepted.revalidate(original)
        self.assertEqual(_RUNNER, boundary.to_dict()["runner"]["id"])
        self.assertEqual(serialized, json.dumps(boundary.to_dict(), sort_keys=True).encode())
        self.assertEqual(boundary.fingerprint, accepted.revalidate(original).fingerprint)
