"""Synthetic adversarial ingress and correctly rehashed retention attacks."""
import copy
import json
import unittest

from AgMark.shared.telemetry import CaptureProfile, CaptureSession, validate_manifest
from AgMark.shared.telemetry.evidence import canonical_bytes, digest, EvidenceLedger
from AgMark.shared.telemetry.normalization import normalize_capture
from AgMark.shared.telemetry.profile import observation_overrides
from AgMark.shared.telemetry.wsl import WslCaptureSession


class AdversarialPrivacyTests(unittest.TestCase):
    identity = "observation:" + "a" * 64

    def test_private_invocation_labels_rejected_at_every_ingress(self):
        for value in ("PRIVATE_CUSTOMER_HOST", "private@example.test", "../escape", "", None,
                      {"private": "PRIVATE SECRET"}, ["PRIVATE SECRET"], "observation:" + "a" * 63,
                      "observation:" + "A" * 64, "golden-private", "gui-runner-test-private"):
            for profile_id in ("session", "telemetry", "deep_telemetry"):
                profile = CaptureProfile(profile_id, diagnostic_privacy_acknowledged=profile_id == "deep_telemetry")
                with self.subTest(value=value, profile=profile_id):
                    for call in (
                        lambda: CaptureSession(profile, "0.159.0", value),
                        lambda: EvidenceLedger(profile, value, {}),
                        lambda: WslCaptureSession(profile, "0.159.0", value,
                            launch_metadata={"launcher": "wsl", "distribution": "Fixture", "executable": "codex"}),
                        lambda: observation_overrides(value, "http://127.0.0.1:12345"),
                    ):
                        with self.assertRaisesRegex(ValueError, "canonical non-personal"):
                            call()

    def test_correctly_rehashed_private_manifest_identity_cannot_reparse(self):
        capture = CaptureSession(CaptureProfile("session"), "0.159.0", self.identity).start()
        self.addCleanup(capture.close)
        manifest = capture.finish()
        for value in ("PRIVATE_CUSTOMER_HOST", "private@example.test", {"private": "PRIVATE SECRET"},
                      ["PRIVATE SECRET"], None):
            with self.subTest(value=value):
                forged = copy.deepcopy(manifest)
                forged["invocation_id"] = value
                forged["integrity"].pop("manifest_sha256")
                forged["integrity"]["manifest_sha256"] = digest(canonical_bytes(forged))
                for consumer in (validate_manifest, normalize_capture):
                    with self.assertRaisesRegex(ValueError, "canonical non-personal"):
                        consumer(forged)

    def test_profiles_drop_source_identities_and_error_payloads_before_sealing(self):
        for profile_id in ("session", "telemetry", "deep_telemetry"):
            with self.subTest(profile=profile_id):
                profile = CaptureProfile(profile_id, diagnostic_privacy_acknowledged=profile_id == "deep_telemetry")
                capture = CaptureSession(profile, "0.159.0", self.identity).start()
                self.addCleanup(capture.close)
                raw = (json.dumps({"type": "thread.started", "thread_id": "PRIVATE_ACCOUNT_ID",
                    "error": "PRIVATE ERROR", "metadata": {"content": "PRIVATE MESSAGE"}}) + "\n").encode()
                capture.ingest_stdout(raw)
                result = capture.finish(raw, b"PRIVATE STDERR", process_status="failed")
                self.assertTrue(validate_manifest(result))
                self.assertNotIn("PRIVATE", json.dumps(result))
                self.assertEqual(self.identity, result["invocation_id"])
                thread = next(record["payload"] for record in result["records"]
                    if record["source"] == "stdout")
                self.assertEqual("local-1", thread["thread_id"])
                self.assertEqual(result, capture.finish())

    def test_version_suffixes_never_survive_capture_or_rehashed_reparse(self):
        from AgMark.shared.telemetry.privacy import Sanitizer
        from AgMark.shared.telemetry.runtime_reference import _version
        raw_version = "0.159.0+PRIVATE-CUSTOMER-HOSTNAME"
        self.assertEqual("0.159.0", _version(raw_version))
        for key in ("version", "cli_version", "service.version", "telemetry.sdk.version"):
            self.assertEqual("0.159.0", Sanitizer().value(raw_version, key=key))
        capture = CaptureSession(CaptureProfile("session"), raw_version, self.identity).start()
        self.addCleanup(capture.close)
        manifest = capture.finish()
        self.assertNotIn("PRIVATE", json.dumps(manifest))
        self.assertEqual("0.159.0", manifest["runtime"]["version"])
        self.assertIsNone(manifest["runtime"]["evidence_commit"],
            "A reduced version core does not prove the audited binary was used.")
        forged = copy.deepcopy(manifest)
        forged["runtime"]["version"] = raw_version
        forged["integrity"].pop("manifest_sha256")
        forged["integrity"]["manifest_sha256"] = digest(canonical_bytes(forged))
        with self.assertRaisesRegex(ValueError, "runtime violates"):
            validate_manifest(forged)
