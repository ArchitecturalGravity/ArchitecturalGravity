"""Content-verified bounded caches for repeated telemetry projections."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from AgMark.shared.telemetry import evidence, normalization
from AgMark.shared.evaluation.telemetry import consumption
from AgMark.shared.runtime.orchestration import PlannedCaseInput, plan_run
from AgMark.shared.software_testing.runtime.test_orchestration import _boundary, _source, _sha256
from AgMark.shared.software_testing.telemetry.test_normalization import manifest, snapshot
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import extract


class VerifiedProjectionCacheTests(unittest.TestCase):
    def setUp(self):
        with evidence._VERIFIED_MANIFEST_LOCK:
            evidence._VERIFIED_MANIFESTS.clear()
        with normalization._RECONSTRUCTION_CACHE_LOCK:
            normalization._RECONSTRUCTION_DIGESTS.clear()

    def test_manifest_cache_rechecks_current_bytes_and_resealed_invalid_records(self):
        capture = manifest([("rollout", snapshot())])
        self.assertTrue(evidence.validate_manifest(capture))
        self.assertTrue(evidence.validate_manifest(capture))
        capture["records"][0]["payload"]["changed"] = True
        with self.assertRaisesRegex(ValueError, "manifest integrity"):
            evidence.validate_manifest(capture)
        capture["integrity"].pop("manifest_sha256")
        capture["integrity"]["manifest_sha256"] = evidence.digest(evidence.canonical_bytes(capture))
        with self.assertRaisesRegex(ValueError, "minimization policy"):
            evidence.validate_manifest(capture)

    def test_reconstruction_reuses_only_matching_current_normalized_digest(self):
        capture = manifest([("rollout", snapshot())])
        normalized = normalization.normalize_capture(capture)
        extensions = {normalization.CAPTURE_EXTENSION: capture, normalization.NORMALIZED_EXTENSION: normalized}
        before = deepcopy(extensions)
        with patch.object(normalization, "normalize_capture", wraps=normalization.normalize_capture) as parser:
            first = normalization.reconstruct_capture_extensions(extensions)
            second = normalization.reconstruct_capture_extensions(extensions)
            self.assertEqual(1, parser.call_count)
            self.assertEqual(first, second)
            first["measurements"]["input_tokens"]["value"] = 500
            self.assertEqual(100, normalization.reconstruct_capture_extensions(extensions)["measurements"]["input_tokens"]["value"])
            self.assertEqual(before, extensions)
            extensions[normalization.NORMALIZED_EXTENSION]["measurements"]["input_tokens"]["value"] = 500
            with self.assertRaisesRegex(ValueError, "reconstruct"):
                normalization.reconstruct_capture_extensions(extensions)
            self.assertEqual(1, parser.call_count)

    def test_digest_caches_are_bounded_and_store_no_payloads(self):
        with patch.object(evidence, "_VERIFIED_MANIFEST_LIMIT", 2), patch.object(normalization, "_RECONSTRUCTION_CACHE_LIMIT", 2):
            for index in range(3):
                capture = manifest([("rollout", snapshot())], identity=str(index))
                normalization.reconstruct_capture_extensions({normalization.CAPTURE_EXTENSION: capture})
        self.assertEqual(2, len(evidence._VERIFIED_MANIFESTS))
        self.assertEqual(2, len(normalization._RECONSTRUCTION_DIGESTS))
        self.assertTrue(all(value is True for value in evidence._VERIFIED_MANIFESTS.values()))
        self.assertTrue(all(isinstance(value, str) and value.startswith("sha256:") for value in normalization._RECONSTRUCTION_DIGESTS.values()))

    def fixture(self, root):
        plan = plan_run(benchmark=_source("test.benchmark", b"benchmark"),
            case_set=_source("test.cases", b"cases"), treatment_set=_source("test.treatments", b"treatments"),
            cases=(PlannedCaseInput("case", _sha256(b"input")),), treatments=("treatment",),
            repetitions=1, execution_boundary=_boundary(), golden_required=False)
        slot = plan.observations[0]
        capture = manifest([("rollout", snapshot())], identity=slot.observation_id)
        from AgMark.shared.software_testing.telemetry.test_runner_capture import runner, request
        from AgMark.shared.software_testing.adapters.codex_cli.test_runner import FakeCodexTransport
        from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import rollout
        import base64
        class Transport(FakeCodexTransport):
            def read_session(self, thread_id, **kwargs):
                return {"availability": "retained", "thread_id": thread_id,
                        "content_base64": base64.b64encode(rollout(thread_id)).decode()}
        invocation = request()
        invocation.update(observation_id=slot.observation_id, request_id=slot.request_id, case_id=slot.case_id,
            treatment_id=slot.treatment_id, repetition=slot.repetition, accepted_generation_id="generation-a")
        document = runner(Transport()).execute(invocation)
        document["execution_boundary_fingerprint"] = plan.execution_boundary_fingerprint
        document["extensions"].update({normalization.CAPTURE_EXTENSION: capture,
            normalization.NORMALIZED_EXTENSION: normalization.normalize_capture(capture)})
        path = root / "generation-a" / ("observation-" + slot.observation_id) / "observation.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(document))
        return plan, document, path

    def test_active_cache_skips_repeated_work_but_checks_changed_bytes_with_same_stat(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, document, path = self.fixture(root)
            cache = consumption._ActiveProjectionCache()
            with patch.object(consumption, "_ACTIVE_PROJECTION_CACHE", cache), patch.object(
                    consumption, "aggregate_treatment_measurements", wraps=consumption.aggregate_treatment_measurements) as aggregate:
                first = consumption.active_treatment_measurements("generation-a", plan, SimpleNamespace(root=root))
                second = consumption.active_treatment_measurements("generation-a", plan, SimpleNamespace(root=root))
                self.assertEqual(1, aggregate.call_count)
                self.assertEqual(first, second)
                first["treatment"]["roles"]["input_tokens"]["value"] = 999
                self.assertEqual(100, consumption.active_treatment_measurements("generation-a", plan, SimpleNamespace(root=root))["treatment"]["roles"]["input_tokens"]["value"])
                original_stat = path.stat()
                document["accepted_generation_id"] = "generation-b"
                path.write_text(json.dumps(document))
                os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                self.assertEqual(original_stat.st_size, path.stat().st_size)
                with self.assertRaisesRegex(ValueError, "binding mismatch"):
                    consumption.active_treatment_measurements("generation-a", plan, SimpleNamespace(root=root))
                self.assertEqual(1, aggregate.call_count)

    def test_active_cache_rechecks_current_authorized_scope_even_with_same_plan_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, _, _ = self.fixture(root)
            with patch.object(consumption, "_ACTIVE_PROJECTION_CACHE", consumption._ActiveProjectionCache()):
                consumption.active_treatment_measurements("generation-a", plan, SimpleNamespace(root=root))
                altered = replace(plan, observations=(replace(plan.observations[0], treatment_id="other-treatment"),))
                self.assertEqual(plan.plan_sha256, altered.plan_sha256)
                with self.assertRaisesRegex(ValueError, "authorized observation scope"):
                    consumption.active_treatment_measurements("generation-a", altered, SimpleNamespace(root=root))

    def test_projection_cache_bounds_bytes_entries_and_mutation(self):
        cache = consumption._ActiveProjectionCache(max_bytes=60, max_entries=2)
        for index in range(4):
            cache.put(index, {"value": index})
        self.assertEqual(2, len(cache.entries))
        self.assertIsNone(cache.get(0))
        self.assertLessEqual(cache.byte_length, 60)
        cached = cache.get(3)
        cached["value"] = 88
        self.assertEqual(3, cache.get(3)["value"])
        cache.put("oversized", {"value": "x" * 100})
        self.assertIsNone(cache.get("oversized"))
        self.assertLessEqual(cache.byte_length, 60)
