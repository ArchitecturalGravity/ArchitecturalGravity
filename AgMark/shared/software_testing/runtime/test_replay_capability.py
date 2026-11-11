"""Optional replay is registration-capability gated, not a generic runner duty."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.runtime.orchestration.replay import (
    REPLAY_CAPABILITY, CODEX_REPLAY_PROFILE, supports_validation_replay,
    validate_finalized_run,
)
from AgMark.shared.runtime.artifacts.validation import ValidationArtifactStore
from AgMark.shared.software_testing.validation.codex_cache.fixtures import accepted_fixture
from AgMark.shared.validation.codex_cache.serialization import admit_validation, validation_bytes


class ReplayCapabilityTests(unittest.TestCase):
    def test_only_explicit_supported_profile_authorizes_replay(self):
        supported = {'extensions': {REPLAY_CAPABILITY: {'profile': CODEX_REPLAY_PROFILE}}}
        self.assertTrue(supports_validation_replay(supported))
        for declaration in (None, {}, {'profile': 'unsupported'}, {'profile': 'another_adapter'},
                            {'profile': CODEX_REPLAY_PROFILE, 'fallback': True}, 'codex_cli_cache_v1'):
            with self.subTest(declaration=declaration):
                self.assertFalse(supports_validation_replay({'extensions': {REPLAY_CAPABILITY: declaration}}))
        for registration in (None, {}, {'registration_id': 'openai.codex-cli'}):
            self.assertFalse(supports_validation_replay(registration))

    def test_unsupported_adapter_skips_codex_inputs_and_preserves_explicit_unavailability(self):
        with tempfile.TemporaryDirectory() as directory:
            terminal, boundary, store, _ = accepted_fixture(Path(directory), replay_supported=False)
            before = {r.reference: store.read_verified(r) for r in terminal.artifact_index.artifacts}
            with patch('AgMark.shared.runtime.orchestration.replay.configuration_values', side_effect=AssertionError('Codex configuration forbidden')), \
                 patch('AgMark.shared.runtime.orchestration.replay.capture_replay', side_effect=AssertionError('No replay invocation')), \
                 patch('AgMark.shared.runtime.orchestration.replay._managed_replay', side_effect=AssertionError('No startup interpretation')):
                summaries = validate_finalized_run(terminal=terminal, artifact_store=store,
                    boundary=boundary, case_inputs=(), treatment_prompts=(),
                    capture_options={'unrelated': object()}, startup_records={'unrelated': object()})
            self.assertTrue(summaries)
            for summary in summaries:
                self.assertEqual('unsupported_by_adapter', summary.sampling_policy)
                self.assertEqual('adapter_validation_replay_unsupported', summary.sampling_reason)
                self.assertEqual((), summary.replays)
                self.assertEqual(0, summary.coverage.validation_replays_planned)
                self.assertEqual(0, summary.coverage.validation_replays_attempted)
                self.assertGreater(summary.coverage.scored_observation_count, 0)
                self.assertEqual('unavailable', summary.coverage.comparable_coverage.availability)
                self.assertIsNone(summary.coverage.comparable_coverage.value)
                self.assertEqual(summary.to_dict(), admit_validation(json.loads(validation_bytes(summary))).to_dict())
                from AgMark.shared.reporting.replay import validation_markdown
                rendered = validation_markdown(summary)
                self.assertIn("Unsupported by the selected adapter", rendered)
                self.assertIn("No replay invocations", rendered)
                self.assertNotIn("Separate invocation", rendered)
            reopened = ValidationArtifactStore(store).retain(terminal, summaries)
            self.assertEqual([s.to_dict() for s in summaries], [s.to_dict() for s in reopened])
            self.assertEqual(before, {r.reference: store.read_verified(r) for r in terminal.artifact_index.artifacts})

    def test_application_never_constructs_codex_startup_for_unsupported_adapter(self):
        from AgMark.shared.software_testing.integration.test_application_boundary import ApplicationBoundaryIntegrationTests
        with tempfile.TemporaryDirectory() as directory, \
             patch('AgMark.shared.runtime.orchestration.replay.supports_validation_replay', return_value=False), \
             patch('AgMark.shared.validation.codex_cache.startup.StartupCollector', side_effect=AssertionError('Adapter has no replay capability')):
            session, request, *_ = ApplicationBoundaryIntegrationTests()._complete_accepted(directory)
            self.assertEqual('complete', session.completion_record(request.generation_id)['status'])
