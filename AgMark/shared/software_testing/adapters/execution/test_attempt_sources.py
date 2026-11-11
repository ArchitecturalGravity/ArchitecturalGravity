"""Generic numeric source parity without process bytes or native identifiers."""
import copy
import json
import unittest

from AgMark.shared.evaluation.telemetry.source import ATTEMPT_SOURCES, build_attempt_source, validate_attempt_source
from AgMark.shared.evaluation.telemetry.consumption import ATTEMPT_MEASUREMENTS
from AgMark.shared.adapters.execution.emission import emit_terminal_observation, validate_retained_parity_observation, CanonicalObservationError
from AgMark.shared.software_testing.adapters.execution.test_emission import _request, _target, _result


class CommonAttemptSourceTests(unittest.TestCase):
    def source(self, tokens=7, status="unknown", complete=False):
        return build_attempt_source(runtime_version="1.2.3", tokens={"total_tokens": tokens},
            tool_events=[{"invocation_id": "private-native-call", "tool_id": "/home/private/tool", "status": status}],
            trace_complete=complete)

    def observation(self, record, envelope):
        return emit_terminal_observation(_request(), target=_target(target_class="mock-model"), execution=_result(),
            runner_id="arcgrav.runner.shared-test", runner_version="1.0.0", framed_request=b"prompt\n\ninput",
            request_framing_mode="test-fixture", extensions={ATTEMPT_MEASUREMENTS: envelope,
                ATTEMPT_SOURCES: {envelope["source_identity"]: record}})

    def test_source_reconstructs_unknown_tool_and_counter_without_native_identifiers(self):
        record, envelope = self.source()
        self.assertEqual(envelope, validate_attempt_source(record))
        encoded = json.dumps(record)
        self.assertNotIn("private", encoded)
        self.assertEqual("call-1", record["tool_events"][0]["invocation_id"])
        self.assertEqual("tool-1", record["tool_events"][0]["tool_id"])
        self.assertEqual("unknown", envelope["tool_events"][0]["status"])
        validate_retained_parity_observation(self.observation(record, envelope))

    def test_retries_preserve_exact_per_attempt_sources(self):
        first, one = self.source(7, "failed", True)
        second, two = self.source(11, "completed", True)
        observation = self.observation(first, one)
        observation["attempts"] = [{**observation["attempts"][0], "attempt": n, "status": state}
            for n, state in ((1, "failed"), (2, "completed"))]
        observation["extensions"].pop(ATTEMPT_MEASUREMENTS)
        observation["extensions"]["arcgrav.telemetry:attempt-series"] = {"1": one, "2": two}
        observation["extensions"][ATTEMPT_SOURCES][two["source_identity"]] = second
        validate_retained_parity_observation(observation)
        observation["extensions"]["arcgrav.telemetry:attempt-series"]["2"]["roles"]["total_tokens"]["value"] += 1
        with self.assertRaises(CanonicalObservationError):
            validate_retained_parity_observation(observation)

    def test_unknown_or_unlinked_source_facts_are_rejected(self):
        record, envelope = self.source()
        for changed in ({**record, "username": "private"}, {**record, "tokens": {"account_id": 123}},
                        {**record, "trace_complete": "yes"}):
            with self.assertRaises(ValueError):
                validate_attempt_source(changed)
        observation = self.observation(record, envelope)
        extra, other = self.source(8)
        observation["extensions"][ATTEMPT_SOURCES][other["source_identity"]] = extra
        with self.assertRaises(CanonicalObservationError):
            validate_retained_parity_observation(observation)

    def test_prerelease_build_runtime_identity_retains_only_numeric_core(self):
        record, envelope = build_attempt_source(runtime_version="1.0.0-privateCustomer+privateHost", tokens={"total_tokens": 0})
        self.assertEqual("1.0.0", validate_attempt_source(record)["runtime_version"])
        self.assertNotIn("privateCustomer", str((record, envelope)))
        self.assertNotIn("privateHost", str((record, envelope)))

    def test_rehashed_native_aliases_still_fail_minimization(self):
        record, _ = self.source()
        record = copy.deepcopy(record)
        record["tool_events"][0]["invocation_id"] = "native-session-id"
        with self.assertRaises(ValueError):
            validate_attempt_source(record)
