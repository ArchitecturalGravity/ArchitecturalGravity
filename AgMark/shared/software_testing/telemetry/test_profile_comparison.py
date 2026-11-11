"""Different instrumentation cannot become equivalent through boundary reuse."""
import unittest
from AgMark.shared.runtime.orchestration.replay import _compare_capture_profile
from AgMark.shared.validation.codex_cache.comparison import compare_configuration
from AgMark.shared.validation.codex_cache.metrics import observed
from AgMark.shared.validation.codex_cache.models import CONFIG_FIELDS


class CaptureProfileComparisonTests(unittest.TestCase):
    def comparison(self):
        fields = {key: observed(True if key == 'ambient_configuration_equal' else 'fixture', 'fixture') for key in CONFIG_FIELDS}
        return compare_configuration(fields, fields, runtime_equivalence=None)

    def test_session_replay_interpretation_is_preserved(self):
        expected = self.comparison()
        actual, reasons = _compare_capture_profile(expected, None, 'session')
        self.assertIs(expected, actual)
        self.assertEqual((), reasons)

    def test_expanded_original_and_traces_only_replay_are_noncomparable(self):
        expected = self.comparison()
        for profile in ('telemetry', 'deep_telemetry'):
            actual, reasons = _compare_capture_profile(expected, None, profile)
            self.assertEqual('non_comparable', actual.status)
            self.assertIn('original_and_replay_capture_profiles_differ', reasons)
            self.assertEqual(expected.expected, actual.expected)
            self.assertNotEqual(actual.expected['relevant_controls'].value,
                                actual.observed['relevant_controls'].value)
        self.assertIn('original_sensitive_diagnostic_header_and_overhead_not_replayed', reasons)
