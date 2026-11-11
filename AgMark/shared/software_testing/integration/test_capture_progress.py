"""Offline invocation lifecycle, persistence and presentation isolation."""
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from AgMark.shared.runtime.orchestration.activity import (
    ActivityPublisher, CaptureSourceActivity,
    capture_progress_callback, publish_capture_progress, retained_activity,
)


class CaptureProgressTests(unittest.TestCase):
    def test_threaded_collectors_share_sequence_and_keep_attempt_sources(self):
        events = []
        publisher = ActivityPublisher("generation-concurrent", events.append)
        with publisher.bind():
            first = capture_progress_callback(treatment_id="treatment-a", attempt_id="attempt-a")
            second = capture_progress_callback(treatment_id="treatment-b", attempt_id="attempt-b")
        def collect(callback, invocation):
            for count in range(20):
                callback(dict(phase="capture", invocation_id=invocation, sources=[dict(
                    source_id="stdout", state="active", received_events=count, received_bytes=count * 10)]))
            callback(dict(phase="evidence_validation", invocation_id=invocation, evidence_sealed=True,
                          telemetry_outcome="complete", sources=[dict(source_id="stdout", state="settled", received_events=20)]))
        threads = [Thread(target=collect, args=(first, "invocation-a")), Thread(target=collect, args=(second, "invocation-b"))]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        final = publisher.finish("complete")
        self.assertEqual(list(range(1, len(events) + 1)), [event.sequence for event in events])
        self.assertTrue(final.evidence_sealed)
        self.assertEqual("complete", final.telemetry_outcome)
        self.assertEqual({"attempt-a", "attempt-b"}, {source.attempt_id for source in final.sources})
        second(dict(phase="capture", invocation_id="invocation-b"))
        self.assertIs(final, publisher.latest)

    def test_interruption_persists_health_and_cancellation_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            publisher = ActivityPublisher("generation-cancelled", persistence_root=directory)
            with publisher.bind():
                publish_capture_progress(dict(phase="drain", invocation_id="invocation-a", sources=[dict(
                    source_id="rollout", state="active", received_events=3, received_bytes=100,
                    dropped=1, rejected=2, parse_errors=3)]))
            final = publisher.finish("cancelled")
            retained = retained_activity(directory, "generation-cancelled")
            self.assertEqual(final, retained)
            self.assertTrue(retained.terminal)
            self.assertFalse(retained.evidence_sealed)
            self.assertEqual("cancelled", retained.benchmark_outcome)
            self.assertEqual("partial", retained.telemetry_outcome)
            self.assertEqual("partial", retained.sources[0].state)
            self.assertEqual((1, 2, 3), (retained.sources[0].dropped, retained.sources[0].rejected, retained.sources[0].parse_errors))
            self.assertIsNone(retained_activity(directory, "generation-other"))

    def test_source_reasons_are_codes_no_provider_payload_or_credentials(self):
        publisher = ActivityPublisher("generation-sanitized")
        with publisher.bind():
            publish_capture_progress(dict(phase="capture", invocation_id="invocation-a", sources=[dict(
                source_id="stderr", state="failed", reason="Authorization: Bearer private-token", payload="secret prompt")]))
        self.assertEqual("source_reported_unavailability", publisher.latest.sources[0].reason)
        self.assertNotIn("private-token", repr(publisher.latest))
        self.assertNotIn("secret prompt", repr(publisher.latest))
        with self.assertRaises(ValueError): CaptureSourceActivity("stdout", "active", received_events=True)
        with self.assertRaises(ValueError): CaptureSourceActivity("stdout", "active", received_bytes=-1)

    def test_disabled_and_unsupported_remain_explicit_and_missing_not_zero(self):
        publisher = ActivityPublisher("generation-capability")
        with publisher.bind():
            publish_capture_progress(dict(phase="collector_readiness", invocation_id="invocation-a", sources=[
                dict(source_id="diagnostics", state="disabled", reason="explicit_opt_in_required"),
                dict(source_id="otel_metrics", state="unsupported", reason="stock_capability_not_demonstrated")]))
        final = publisher.finish("failed")
        self.assertEqual(["disabled", "unsupported"], [source.state for source in final.sources])
        self.assertFalse(final.evidence_sealed)
        self.assertEqual("failed", final.benchmark_outcome)

    def test_persistence_refuses_symlink_and_malformed_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = root / "other"
            other.mkdir()
            (root / ".agmark-progress").symlink_to(other, target_is_directory=True)
            publisher = ActivityPublisher("generation-safe", persistence_root=root)
            publisher.finish("complete")
            self.assertEqual([], list(other.iterdir()))
            self.assertIsNone(retained_activity(root, "generation-safe"))
            self.assertIsNone(retained_activity(root, "../escape"))

    def test_scope_and_sealing_survive_normalization_without_new_sources(self):
        publisher = ActivityPublisher("generation-normalization")
        with publisher.bind():
            callback = capture_progress_callback()
        callback(dict(phase="evidence_validation", invocation_id="invocation-a", evidence_sealed=True, telemetry_outcome="partial"))
        callback(dict(phase="normalization", invocation_id="invocation-a"))
        self.assertTrue(publisher.latest.evidence_sealed)
        self.assertEqual("partial", publisher.latest.telemetry_outcome)
        final = publisher.finish("complete")
        self.assertEqual("complete", final.benchmark_outcome)
        self.assertEqual("partial", final.telemetry_outcome)

    def test_runner_normalization_failure_cannot_publish_sealed_completion(self):
        from unittest.mock import patch
        from AgMark.shared.software_testing.telemetry.test_runner_capture import runner, request, MultiSignalTransport
        publisher = ActivityPublisher("generation-normalization-failure")
        with publisher.bind(), patch("AgMark.shared.telemetry.normalization.normalize_capture", side_effect=ValueError("private payload")):
            observation = runner(MultiSignalTransport()).execute(request())
        self.assertEqual("completed", observation["terminal_status"])
        self.assertFalse(publisher.latest.evidence_sealed)
        self.assertFalse(publisher.latest.terminal)
        self.assertEqual("failed", publisher.latest.telemetry_outcome)
        final = publisher.finish("complete")
        self.assertEqual("complete", final.benchmark_outcome)
        self.assertEqual("failed", final.telemetry_outcome)
        self.assertFalse(final.evidence_sealed)
        self.assertNotIn("private payload", repr(final))

    def test_long_runs_bound_callbacks_but_persist_all_capture_sources(self):
        from unittest.mock import patch
        from AgMark.shared.runtime.orchestration.activity import capture_source_window
        import os
        sources = ('stdout', 'stderr', 'process', 'rollout', 'otel_logs', 'otel_traces', 'otel_metrics', 'diagnostics')
        events = []
        with tempfile.TemporaryDirectory() as directory, patch('AgMark.shared.runtime.orchestration.activity.monotonic', return_value=100.0), patch('AgMark.shared.runtime.orchestration.activity.os.replace', wraps=os.replace) as writes:
            publisher = ActivityPublisher('generation-long', events.append, persistence_root=directory)
            with publisher.bind():
                callback = capture_progress_callback()
            for index in range(1000):
                callback(dict(phase='evidence_validation', invocation_id=f'invocation-{index}',
                    evidence_sealed=True, telemetry_outcome='complete', sources=[dict(
                        source_id=source, state='settled', received_events=index + 1) for source in sources]))
            final = publisher.finish('complete')
            self.assertLessEqual(max(len(event.sources) for event in events), 16)
            self.assertEqual(7984, final.omitted_source_count)
            self.assertEqual(998, final.omitted_invocation_count)
            self.assertEqual(2, writes.call_count, 'sub-second phase changes must not rewrite the full snapshot')
            persisted = retained_activity(directory, 'generation-long')
            self.assertEqual(8000, len(persisted.sources))
            self.assertEqual(0, persisted.omitted_source_count)
            window = capture_source_window(persisted)
            self.assertEqual(16, len(window.sources))
            self.assertEqual(7984, window.omitted_source_count)
            self.assertEqual({'invocation-998', 'invocation-999'}, {source.invocation_id for source in window.sources})

    def test_preflight_unavailable_exec_publishes_explicit_source_reasons(self):
        from AgMark.shared.software_testing.telemetry.test_runner_capture import runner, request
        from AgMark.shared.software_testing.adapters.codex_cli.test_runner import FakeCodexTransport
        class UnavailableExecTransport(FakeCodexTransport):
            def run(self, argv, **kwargs):
                if argv[-2:] == ("exec", "--help"):
                    return {"returncode": 1, "stdout": b"", "stderr": b""}
                return super().run(argv, **kwargs)

        publisher = ActivityPublisher('generation-unsupported-progress')
        transport = UnavailableExecTransport(version='9.9.9')
        with publisher.bind():
            observation = runner(transport).execute(request(version='9.9.9'))
        self.assertEqual('unsupported', observation['terminal_status'])
        self.assertIsNotNone(publisher.latest.invocation_id)
        self.assertTrue(publisher.latest.sources)
        unsupported = [source for source in publisher.latest.sources if source.state == 'unsupported']
        self.assertTrue(unsupported)
        self.assertTrue(all(source.reason for source in unsupported))
        self.assertEqual({'codex_cli_noninteractive_unavailable'}, {source.reason for source in unsupported})
        self.assertFalse(any(call['input_bytes'] is not None for call in transport.calls))
        self.assertFalse(publisher.latest.evidence_sealed)

    def test_actual_failed_timeout_cancel_callbacks_preserve_registered_outcomes(self):
        import subprocess
        from AgMark.shared.adapters.execution import InvocationCancelled
        from AgMark.shared.software_testing.telemetry.test_runner_capture import runner, request
        from AgMark.shared.software_testing.adapters.codex_cli.test_runner import FakeCodexTransport
        transports = (
            ('failed', FakeCodexTransport(version='0.159.0', actual_returncode=1)),
            ('timed_out', FakeCodexTransport(version='0.159.0', actual_exception=subprocess.TimeoutExpired('codex', 1))),
            ('cancelled', FakeCodexTransport(version='0.159.0', actual_exception=InvocationCancelled(stdout=b''))),
        )
        with tempfile.TemporaryDirectory() as directory:
            publisher = ActivityPublisher('generation-attempt-outcomes', persistence_root=directory)
            for status, transport in transports:
                with self.subTest(status=status), publisher.bind():
                    observation = runner(transport).execute(request(suffix=status))
                self.assertEqual(status, observation['terminal_status'])
                event = publisher.latest
                self.assertEqual(status, event.benchmark_outcome)
                self.assertFalse(event.terminal)
                self.assertFalse(event.finalization_complete)
                matching = [outcome for outcome in event.invocation_outcomes if outcome.invocation_id == event.invocation_id]
                self.assertEqual(status, matching[0].registered_outcome)
                self.assertEqual(status, matching[0].outcome)
            publisher.finish('cancelled', finalization_complete=True)
            persisted = retained_activity(directory, publisher.generation_id)
            self.assertEqual({'failed', 'timed_out', 'cancelled'}, {outcome.registered_outcome for outcome in persisted.invocation_outcomes})
            self.assertEqual('cancelled', persisted.benchmark_outcome)
            self.assertTrue(persisted.finalization_complete)

    def test_next_invocation_does_not_inherit_previous_invocation_failure(self):
        publisher = ActivityPublisher('generation-outcome-isolation')
        with publisher.bind():
            callback = capture_progress_callback()
        callback({'phase': 'completion', 'invocation_id': 'first', 'benchmark_outcome': 'failed'})
        self.assertEqual('failed', publisher.latest.benchmark_outcome)
        callback({'phase': 'preflight', 'invocation_id': 'second'})
        self.assertEqual('pending', publisher.latest.benchmark_outcome)
        callback({'phase': 'completion', 'invocation_id': 'second', 'benchmark_outcome': 'completed'})
        self.assertEqual('complete', publisher.latest.benchmark_outcome)
        self.assertEqual({'failed', 'completed'}, {outcome.registered_outcome for outcome in publisher.latest.invocation_outcomes})
