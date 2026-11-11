"""Consent is explicit, narrowly scoped and bound into retained evidence."""
from dataclasses import asdict
import copy
import unittest

from AgMark.shared.telemetry.evidence import EvidenceLedger, canonical_bytes, digest, validate_manifest
from AgMark.shared.telemetry.normalization import normalize_capture
from AgMark.shared.telemetry.profile import (
    CaptureProfile,
    DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT,
    DIAGNOSTIC_CONSENT_SCOPE,
    DIAGNOSTIC_CONSENT_VERSION,
)


class DiagnosticConsentProvenanceTests(unittest.TestCase):
    def seal(self, profile):
        ledger = EvidenceLedger(profile, "gui-runner-test:echo-test", {"version": "0.159.0"})
        return ledger.seal(process_status={"status": "failed"})

    def test_explicit_consent_survives_selected_host_profile_transfer_and_seal(self):
        profile = CaptureProfile.from_control("deep_telemetry", diagnostic_privacy_acknowledged=True)
        transferred = CaptureProfile(**asdict(profile))
        manifest = self.seal(transferred)
        consent = manifest["privacy"]["diagnostic_consent"]
        self.assertEqual(DIAGNOSTIC_CONSENT_SCOPE, consent["scope"])
        self.assertEqual(DIAGNOSTIC_CONSENT_VERSION, consent["version"])
        self.assertTrue(consent["acknowledged"])
        self.assertEqual(DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT, consent["acknowledgement_control"])
        self.assertTrue(consent["active"])
        self.assertEqual("original_run_stock_diagnostics_only", consent["applies_to"])
        self.assertEqual(consent, manifest["profile"]["diagnostic_consent"])
        self.assertTrue(validate_manifest(manifest))
        manifest["privacy"]["diagnostic_consent"]["version"] = "different-policy"
        with self.assertRaises(ValueError):
            validate_manifest(manifest)

    def test_acknowledgement_does_not_enable_another_profile_or_replay(self):
        for profile_id in ("session", "telemetry"):
            with self.subTest(profile=profile_id):
                profile = CaptureProfile.from_control(profile_id, diagnostic_privacy_acknowledged=True)
                manifest = self.seal(profile)
                self.assertFalse(manifest["privacy"]["diagnostic_consent"]["active"])
                self.assertFalse(manifest["profile"]["diagnostics_enabled"])
                self.assertEqual("original", manifest["authority"])
        with self.assertRaisesRegex(ValueError, "explicit"):
            CaptureProfile.from_control("deep_telemetry")

    def test_historical_evidence_without_current_metadata_is_rejected(self):
        for profile in (CaptureProfile(), CaptureProfile(
                id="deep_telemetry", diagnostic_privacy_acknowledged=True)):
            with self.subTest(profile=profile.id):
                manifest = self.seal(profile)
                historical = copy.deepcopy(manifest)
                historical["profile"].pop("diagnostic_consent")
                historical["privacy"].pop("diagnostic_consent")
                historical["integrity"].pop("manifest_sha256")
                historical["integrity"]["manifest_sha256"] = digest(canonical_bytes(historical))
                with self.assertRaises(ValueError):
                    validate_manifest(historical)
                with self.assertRaises(ValueError):
                    normalize_capture(historical)
