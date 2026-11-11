"""Provider-free tests for shared execution orchestration."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import subprocess
import unittest

from AgMark.shared.adapters.execution import (
    ExecutionFailureKind,
    ExecutionIsolation,
    InvocationCancelled,
    InvocationCapture,
    InvocationContext,
    execute_target,
    temporary_workdir_isolation,
)


class _Clock:
    def __init__(self) -> None:
        self._timestamps = iter(
            ("2026-09-27T12:00:00Z", "2026-09-27T12:00:01Z")
        )
        self._monotonic = iter((10.0, 10.25))

    def timestamp(self) -> str:
        return next(self._timestamps)

    def monotonic(self) -> float:
        return next(self._monotonic)


class SharedExecutionOrchestrationTests(unittest.TestCase):
    def test_optional_preparation_is_excluded_from_scored_duration(self):
        now = [10.0]
        order = []
        def prepare(context):
            order.append("prepare")
            now[0] += 20.0
        def invoke(context, timeout):
            order.append("invoke")
            now[0] += 0.25
            return InvocationCapture(succeeded=True, exit_status=0, transport_status=None, stdout=b"result", stderr=b"")
        result = execute_target(isolation=temporary_workdir_isolation({}, session_home_reused=True),
            invoke=invoke, response_extractor=lambda capture: capture.stdout, timeout_ms=1000,
            before_invoke=prepare, monotonic=lambda: now[0])
        self.assertEqual(["prepare", "invoke"], order)
        self.assertEqual(250.0, result.duration_ms)
        self.assertEqual("completed", result.terminal_status)

    def _run(
        self,
        *,
        invoke,
        response_extractor=lambda capture: capture.stdout,
    ):
        clock = _Clock()
        return execute_target(
            isolation=temporary_workdir_isolation(
                {"PATH": "/usr/bin"},
                session_home_reused=True,
            ),
            invoke=invoke,
            response_extractor=response_extractor,
            timeout_ms=1000,
            timestamp=clock.timestamp,
            monotonic=clock.monotonic,
        )

    def test_completed_execution_preserves_exact_capture_and_response(
        self,
    ) -> None:
        observed: dict[str, object] = {}

        def invoke(
            context: InvocationContext,
            timeout_ms: int,
        ) -> InvocationCapture:
            observed["cwd"] = context.cwd
            observed["environment"] = dict(context.environment)
            observed["timeout_ms"] = timeout_ms
            self.assertTrue(context.cwd.is_dir())
            return InvocationCapture(
                succeeded=True,
                exit_status=0,
                transport_status="exited",
                stdout=b"\x00exact response\n",
                stderr=b"diagnostic\n",
            )

        result = self._run(invoke=invoke)

        self.assertEqual("completed", result.terminal_status)
        self.assertIsNone(result.failure_kind)
        self.assertTrue(result.invocation_occurred)
        self.assertEqual(b"\x00exact response\n", result.response_bytes)
        self.assertEqual(b"diagnostic\n", result.capture.stderr)
        self.assertEqual(250.0, result.duration_ms)
        self.assertEqual(
            {"PATH": "/usr/bin"},
            observed["environment"],
        )
        self.assertEqual(1000, observed["timeout_ms"])
        self.assertFalse(
            Path(observed["cwd"]).exists()  # type: ignore[arg-type]
        )
        self.assertIsNotNone(result.isolation)
        assert result.isolation is not None
        self.assertTrue(result.isolation.fresh_process)
        self.assertTrue(result.isolation.fresh_workdir)
        self.assertFalse(
            result.isolation.prior_observation_context_reused
        )
        self.assertTrue(result.isolation.session_home_reused)

    def test_nonzero_process_failure_does_not_extract_response(
        self,
    ) -> None:
        extracted = False

        def extract(_: InvocationCapture) -> bytes:
            nonlocal extracted
            extracted = True
            return b"should not happen"

        result = self._run(
            invoke=lambda _context, _timeout_ms: {
                "returncode": 7,
                "stdout": b"partial",
                "stderr": b"failed",
                "transport_status": "exited",
            },
            response_extractor=extract,
        )

        self.assertEqual("failed", result.terminal_status)
        self.assertEqual(
            ExecutionFailureKind.PROCESS_FAILED,
            result.failure_kind,
        )
        self.assertFalse(extracted)
        self.assertEqual(7, result.capture.exit_status)
        self.assertEqual(b"partial", result.capture.stdout)
        self.assertEqual(b"failed", result.capture.stderr)

    def test_timeout_retains_partial_process_bytes(self) -> None:
        def invoke(
            _context: InvocationContext,
            _timeout_ms: int,
        ) -> InvocationCapture:
            raise subprocess.TimeoutExpired(
                cmd=("tool",),
                timeout=1,
                output=b"partial-out",
                stderr=b"partial-err",
            )

        result = self._run(invoke=invoke)

        self.assertEqual("timed_out", result.terminal_status)
        self.assertEqual(
            ExecutionFailureKind.TIMED_OUT,
            result.failure_kind,
        )
        self.assertEqual(b"partial-out", result.capture.stdout)
        self.assertEqual(b"partial-err", result.capture.stderr)
        self.assertIsNone(result.response_bytes)

    def test_cancellation_retains_available_partial_process_bytes(
        self,
    ) -> None:
        def invoke(
            _context: InvocationContext,
            _timeout_ms: int,
        ) -> InvocationCapture:
            raise InvocationCancelled(
                stdout=b"before-cancel",
                stderr=b"cancel-note",
            )

        result = self._run(invoke=invoke)

        self.assertEqual("cancelled", result.terminal_status)
        self.assertEqual(
            ExecutionFailureKind.CANCELLED,
            result.failure_kind,
        )
        self.assertEqual(b"before-cancel", result.capture.stdout)
        self.assertEqual(b"cancel-note", result.capture.stderr)
        self.assertTrue(result.process_channels_observed)

    def test_keyboard_interrupt_has_no_trustworthy_process_capture(self) -> None:
        def interrupt(_context: InvocationContext, _timeout_ms: int) -> None:
            raise KeyboardInterrupt("test-owned interruption without capture")

        result = self._run(invoke=interrupt)

        self.assertEqual("cancelled", result.terminal_status)
        self.assertEqual(ExecutionFailureKind.CANCELLED, result.failure_kind)
        self.assertTrue(result.invocation_occurred)
        self.assertIsNotNone(result.isolation)
        self.assertFalse(result.process_channels_observed)
        self.assertIsNone(result.capture.exit_status)
        self.assertIsNone(result.response_bytes)
        self.assertEqual(b"", result.capture.stdout)
        self.assertEqual(b"", result.capture.stderr)

    def test_success_without_extracted_response_is_explicit_failure(
        self,
    ) -> None:
        result = self._run(
            invoke=lambda _context, _timeout_ms: {
                "returncode": 0,
                "stdout": b"",
                "stderr": b"",
            },
            response_extractor=lambda _capture: None,
        )

        self.assertEqual("failed", result.terminal_status)
        self.assertEqual(
            ExecutionFailureKind.RESPONSE_UNAVAILABLE,
            result.failure_kind,
        )
        self.assertIsNone(result.response_bytes)

    def test_malformed_capture_fails_closed(self) -> None:
        result = self._run(
            invoke=lambda _context, _timeout_ms: {
                "returncode": "zero",
                "stdout": b"answer",
                "stderr": b"",
            }
        )

        self.assertEqual("failed", result.terminal_status)
        self.assertEqual(
            ExecutionFailureKind.CAPTURE_INVALID,
            result.failure_kind,
        )
        self.assertIsNone(result.response_bytes)

    def test_nonclean_isolation_prevents_target_invocation(self) -> None:
        invoked = False
        clock = _Clock()

        @contextmanager
        def nonclean_isolation():
            yield InvocationContext(
                cwd=Path.cwd(),
                environment={},
                isolation=ExecutionIsolation(
                    fresh_process=True,
                    fresh_workdir=False,
                    prior_observation_context_reused=False,
                    session_home_reused=True,
                ),
            )

        def invoke(
            _context: InvocationContext,
            _timeout_ms: int,
        ) -> InvocationCapture:
            nonlocal invoked
            invoked = True
            raise AssertionError("must not run")

        result = execute_target(
            isolation=nonclean_isolation(),
            invoke=invoke,
            response_extractor=lambda capture: capture.stdout,
            timeout_ms=1000,
            timestamp=clock.timestamp,
            monotonic=clock.monotonic,
        )

        self.assertEqual("failed", result.terminal_status)
        self.assertEqual(
            ExecutionFailureKind.ISOLATION_FAILED,
            result.failure_kind,
        )
        self.assertFalse(result.invocation_occurred)
        self.assertFalse(invoked)

    def test_isolation_failure_prevents_target_invocation(self) -> None:
        invoked = False
        clock = _Clock()

        @contextmanager
        def failing_isolation():
            raise OSError("no workspace")
            yield  # pragma: no cover

        def invoke(
            _context: InvocationContext,
            _timeout_ms: int,
        ) -> InvocationCapture:
            nonlocal invoked
            invoked = True
            raise AssertionError("must not run")

        result = execute_target(
            isolation=failing_isolation(),
            invoke=invoke,
            response_extractor=lambda capture: capture.stdout,
            timeout_ms=1000,
            timestamp=clock.timestamp,
            monotonic=clock.monotonic,
        )

        self.assertEqual("failed", result.terminal_status)
        self.assertEqual(
            ExecutionFailureKind.ISOLATION_FAILED,
            result.failure_kind,
        )
        self.assertFalse(result.invocation_occurred)
        self.assertFalse(invoked)
        self.assertIsNone(result.isolation)


if __name__ == "__main__":
    unittest.main()
