"""Provider-free real-pipe streaming and unchanged response-authority coverage."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from AgMark.shared.adapters.Codex_CLI.events import IncrementalResponseDecoder, extract_response
from AgMark.shared.adapters.Codex_CLI.runner import CodexCliRunner, _SubprocessTransport
from AgMark.shared.adapters.execution import InvocationCancelled, validate_retained_parity_observation
from AgMark.shared.software_testing.adapters.codex_cli.test_runner import (
    FakeCodexTransport, _boundary, _request, _sha256,
)


def message(text, event="item.updated", kind="agent_message"):
    return (json.dumps({"type": event, "item": {"type": kind, "id": "answer", "text": text}},
                       ensure_ascii=False) + "\n").encode("utf-8")


class IncrementalDecoderTests(unittest.TestCase):
    def test_switch_discards_live_capture_and_resumes_after_partial_record(self):
        from AgMark.shared.adapters.execution.live_view import LiveViewControl
        from AgMark.shared.adapters.Codex_CLI.events import ControlledLiveResponseDecoder
        control = LiveViewControl(True)
        seen = []
        decoder = ControlledLiveResponseDecoder(seen.append, control)
        decoder.feed(message("before"))
        control.set_enabled(False)
        with patch.object(IncrementalResponseDecoder, 'feed', side_effect=AssertionError('disabled decoder ran')):
            decoder.feed(message("off") + b'{"type":')
        self.assertIsNone(decoder._decoder)
        control.set_enabled(True)
        decoder.feed(b'"ignored partial"}\n' + message("resumed"))
        self.assertEqual(["before", "resumed"], seen)
        control.set_enabled(False)
        decoder.finish()
        decoder.snapshot("must not show")
        self.assertEqual(["before", "resumed"], seen)

    def test_byte_splits_snapshots_deduplication_and_separate_diagnostics(self):
        seen = []
        decoder = IncrementalResponseDecoder(seen.append)
        raw = (message("secret reasoning", kind="reasoning") + message("  λ")
               + message("tool transcript", kind="command_execution")
               + message("  λ\nanswer\r\n", "item.completed")
               + message("  λ\nanswer\r\n", "item.completed"))
        for byte in raw:
            decoder.feed(bytes([byte]))
        decoder.finish()
        self.assertEqual(["  λ", "  λ\nanswer\r\n"], seen)

    def test_unterminated_final_line_and_replacement_are_not_concatenated(self):
        seen = []
        decoder = IncrementalResponseDecoder(seen.append)
        decoder.feed(message("first", "item.completed") + message("second", "item.completed").rstrip(b"\n"))
        self.assertEqual(["first"], seen)
        decoder.finish()
        decoder.finish()
        self.assertEqual(["first", "second"], seen)

    def test_malformed_prefix_stops_preview_and_cannot_become_response(self):
        seen = []
        decoder = IncrementalResponseDecoder(seen.append)
        raw = message("partial") + b"not JSON\n" + message("must not appear", "item.completed")
        decoder.feed(raw)
        decoder.finish()
        self.assertEqual(["partial"], seen)
        self.assertIsNone(extract_response(raw))


class _TemporaryProcessCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def invoke(self, script, **kwargs):
        return _SubprocessTransport().run_streaming(
            (sys.executable, "-u", "-c", script), cwd=self.root,
            env=os.environ.copy(), timeout_ms=kwargs.pop("timeout_ms", 5000), **kwargs,
        )


class PipeStreamingTests(_TemporaryProcessCase):
    def test_output_is_observed_before_child_can_exit(self):
        release, exited = self.root / "release", self.root / "exited"
        script = f"""
import os, pathlib, sys, time
sys.stdin.buffer.read()
os.write(1, b'first chunk')
deadline = time.monotonic() + 3
while not pathlib.Path({str(release)!r}).exists() and time.monotonic() < deadline:
    time.sleep(.01)
pathlib.Path({str(exited)!r}).write_text('exited')
os.write(1, b' final chunk')
"""
        before_exit = []
        def consume(chunk):
            if not before_exit:
                before_exit.append(not exited.exists())
                release.write_text("release")
        result = self.invoke(script, input_bytes=b"exact input", on_stdout=consume)
        self.assertEqual([True], before_exit)
        self.assertEqual(b"first chunk final chunk", result["stdout"])
        self.assertEqual(0, result["returncode"])

    def test_large_stdin_and_stderr_do_not_deadlock_or_mix(self):
        raw = b"\x00\r\n" * 100000
        result = self.invoke(
            "import os, sys; os.write(2, b'd' * 300000); "
            "sys.stdout.buffer.write(sys.stdin.buffer.read())",
            input_bytes=raw,
        )
        self.assertEqual(raw, result["stdout"])
        self.assertEqual(b"d" * 300000, result["stderr"])

    def test_timeout_preserves_partial_stdout_and_stderr_and_reaps_child(self):
        script = "import os, time; os.write(1, str(os.getpid()).encode()); os.write(2, b'diagnostic'); time.sleep(10)"
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            self.invoke(script, input_bytes=b"input", timeout_ms=500)
        self.assertEqual(b"diagnostic", caught.exception.stderr)
        pid = int(caught.exception.output)
        if os.name == "posix":
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_cancellation_preserves_streamed_prefix(self):
        cancel = threading.Event()
        seen = []
        def consume(chunk):
            seen.append(chunk)
            cancel.set()
        with self.assertRaises(InvocationCancelled) as caught:
            self.invoke("import os, time; os.write(1, b'partial'); time.sleep(10)",
                        input_bytes=b"input", on_stdout=consume,
                        cancellation_requested=cancel.is_set)
        self.assertEqual(b"partial", b"".join(seen))
        self.assertEqual(b"partial", caught.exception.stdout)

    def test_cancelled_backlog_preserves_all_bytes_without_dispatching_callbacks(self):
        ready = self.root / "burst-written"
        cancel = threading.Event()
        callbacks = []
        def consume(chunk):
            callbacks.append(chunk)
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(ready.exists())
            cancel.set()
        script = ("import os,pathlib,time\n"
                  "for _ in range(512): os.write(1,b'x'*8192)\n"
                  "os.write(2,b'final diagnostic')\n"
                  f"pathlib.Path({str(ready)!r}).touch()\n"
                  "time.sleep(30)\n")
        started = time.monotonic()
        with self.assertRaises(InvocationCancelled) as caught:
            self.invoke(script, input_bytes=None, on_stdout=consume, cancellation_requested=cancel.is_set)
        self.assertEqual(1, len(callbacks))
        self.assertEqual(b"x" * (8192 * 512), caught.exception.stdout)
        self.assertEqual(b"final diagnostic", caught.exception.stderr)
        self.assertLess(time.monotonic() - started, 3)

    def test_interrupted_callback_suffix_reconciles_into_sealed_telemetry(self):
        from AgMark.shared.telemetry import CaptureSession, validate_manifest
        session = CaptureSession(runtime_version="0.159.0", invocation_id="observation:" + "c" * 64).start()
        self.addCleanup(session.close)
        first = b'{"type":"thread.started","thread_id":"trial"}\n'
        final = b'{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}\n'
        session.ingest_stdout(first)
        sealed = session.finish(stdout=first + final, stderr=b"retained-tail", process_status="cancelled")
        self.assertTrue(validate_manifest(sealed))
        self.assertNotIn("raw_byte_length", sealed["sources"]["stdout"])
        self.assertNotIn("raw_sha256", sealed["sources"]["stdout"])
        self.assertEqual(2, sealed["sources"]["stdout"]["received_events"])
        self.assertNotIn("raw_byte_length", sealed["sources"]["stderr"])


class RunnerStreamingTests(_TemporaryProcessCase):
    def test_live_capture_toggle_preserves_final_bytes_and_scored_authority(self):
        from AgMark.shared.adapters.execution.live_view import LiveViewControl
        control = LiveViewControl()
        self.assertEqual((False, 0), control.snapshot())
        events = []
        start = b'{"type":"thread.started","thread_id":"toggle-thread"}\n{"type":"turn.started"}\n'
        off = message('disabled text')
        resumed = message('resumed text')
        final = message('final response', 'item.completed') + b'{"type":"turn.completed","usage":{}}\n'
        owner = self
        class ToggleTransport(FakeCodexTransport):
            def run_streaming(self, argv, **kwargs):
                if kwargs['input_bytes'] is None:
                    return self.run(argv, **{k: kwargs[k] for k in ('input_bytes', 'cwd', 'env', 'timeout_ms')})
                kwargs['on_input']()
                with patch.object(IncrementalResponseDecoder, 'feed', side_effect=AssertionError('off capture decoded')):
                    kwargs['on_stdout'](start + off)
                owner.assertEqual([], events)
                control.set_enabled(True)
                kwargs['on_stdout'](resumed)
                owner.assertEqual('resumed text', events[-1]['text'])
                control.set_enabled(False)
                kwargs['on_stdout'](final)
                self.process_stdout = start + off + resumed + final
                return {'returncode': 0, 'stdout': self.process_stdout, 'stderr': b'diagnostic'}
        transport = ToggleTransport()
        runner = CodexCliRunner(transport=transport, executable_resolver=lambda _: '/fixture/codex')
        self.addCleanup(runner.close)
        observation = runner.execute(_request(_boundary()), event_callback=events.append, live_view_control=control)
        self.assertEqual('completed', observation['terminal_status'])
        validate_retained_parity_observation(observation)
        self.assertNotIn('arcgrav.runner:process_stdout_base64', observation['extensions'])
        self.assertEqual(['resumed text'], [e['text'] for e in events])

    def test_existing_transport_run_interception_preserves_cancellation(self):
        probe = FakeCodexTransport()
        calls = []
        partial = message("partial")
        def intercepted(transport, argv, **kwargs):
            calls.append(argv)
            if kwargs["input_bytes"] is None:
                return probe.run(argv, **kwargs)
            raise InvocationCancelled(stdout=partial, stderr=b"interrupted")
        runner = CodexCliRunner(executable_resolver=lambda _: sys.executable)
        self.addCleanup(runner.close)
        with patch.object(_SubprocessTransport, "run", intercepted):
            observation = runner.execute(_request(_boundary()))
        self.assertEqual(3, len(calls))
        self.assertEqual("cancelled", observation["terminal_status"])
        self.assertNotIn("arcgrav.runner:process_stdout_base64", observation["extensions"])
        validate_retained_parity_observation(observation)

    def test_actual_timeout_and_cancellation_retain_partial_channels_without_response(self):
        from AgMark.shared.adapters.execution.live_view import LiveViewControl
        partial = (b'{"type":"thread.started","thread_id":"fixture"}\n'
                   b'{"type":"turn.started"}\n' + message("partial λ"))
        script = (f"import os, sys, time; sys.stdin.buffer.read(); "
                  f"os.write(2, b'diagnostic'); os.write(1, {partial!r}); time.sleep(10)")
        class PartialTransport(_SubprocessTransport):
            def run_streaming(self, argv, **kwargs):
                if kwargs["input_bytes"] is None:
                    return FakeCodexTransport().run(argv, **{
                        key: value for key, value in kwargs.items()
                        if key not in {"on_input", "on_stdout", "cancellation_requested"}
                    })
                return super().run_streaming((sys.executable, "-u", "-c", script), **kwargs)
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                cancellation = threading.Event()
                control = LiveViewControl(True)
                seen = []
                def consume(event):
                    seen.append(dict(event))
                    if event["channel"] == "output":
                        control.set_enabled(False)
                    if cancel and event["channel"] == "output":
                        cancellation.set()
                runner = CodexCliRunner(transport=PartialTransport(), executable_resolver=lambda _: sys.executable)
                self.addCleanup(runner.close)
                request = _request(_boundary(timeout_ms=500))
                observation = runner.execute(request, event_callback=consume,
                                             cancellation_requested=cancellation.is_set,
                                             live_view_control=control)
                self.assertEqual("cancelled" if cancel else "timed_out", observation["terminal_status"])
                validate_retained_parity_observation(observation)
                self.assertEqual(["input", "output"], [event["channel"] for event in seen])
                extensions = observation["extensions"]
                self.assertNotIn("arcgrav.runner:process_stdout_base64", extensions)
                self.assertNotIn("arcgrav.runner:process_stderr_base64", extensions)
                self.assertNotIn("openai.codex-cli:response_base64", extensions)
                self.assertIn("arcgrav.runner:submitted_input", extensions)

    def test_actual_runner_streams_exact_input_and_unicode_response_before_exit(self):
        script = self.root / "fake_cli.py"
        release, exited, stdin = (self.root / name for name in ("release", "exited", "stdin"))
        final = "  λ\nanswer\r\n"
        prefix = (b'{"type":"thread.started","thread_id":"fixture"}\n'
                  b'{"type":"turn.started"}\n')
        first = message("  λ")
        end = message(final, "item.completed") * 2 + b'{"type":"turn.completed","usage":{}}'
        split = first.index("λ".encode()) + 1
        script.write_text(f"""
import os, pathlib, sys, time
if sys.argv[-1:] == ['--version']:
    print('codex-cli 1.2.3'); sys.exit(0)
if sys.argv[-2:] == ['exec', '--help']:
    print('Usage: codex exec [OPTIONS]'); sys.exit(0)
pathlib.Path({str(stdin)!r}).write_bytes(sys.stdin.buffer.read())
os.write(2, b'diagnostic, not model output\\n')
os.write(1, {prefix + first[:split]!r})
time.sleep(.02)
os.write(1, {first[split:]!r})
deadline = time.monotonic() + 3
while not pathlib.Path({str(release)!r}).exists() and time.monotonic() < deadline:
    time.sleep(.01)
os.write(1, {end!r})
pathlib.Path({str(exited)!r}).write_text('exited')
""", encoding="utf-8")
        class ScriptTransport(_SubprocessTransport):
            def run_streaming(self, argv, **kwargs):
                return super().run_streaming((sys.executable, "-u", str(script), *argv[1:]), **kwargs)

        seen, before_exit = [], []
        def consume(event):
            seen.append(dict(event))
            if event["channel"] == "output" and not before_exit:
                before_exit.append(not exited.exists())
                release.write_text("release")
        runner = CodexCliRunner(transport=ScriptTransport(), executable_resolver=lambda _: sys.executable)
        self.addCleanup(runner.close)
        request = _request(_boundary())
        request["prompt"] = {"content": "  prompt\r\nλ".encode(), "sha256": _sha256("  prompt\r\nλ".encode())}
        request["request_identity"]["prompt_sha256"] = request["prompt"]["sha256"]
        frame = request["prompt"]["content"] + b"\n\n" + request["input"]["content"]
        observation = runner.execute(request, event_callback=consume)
        self.assertEqual("completed", observation["terminal_status"], observation)
        validate_retained_parity_observation(observation)
        self.assertEqual([True], before_exit)
        self.assertEqual(frame, stdin.read_bytes())
        self.assertEqual([
            {"channel": "input", "text": frame.decode(), "mode": "snapshot"},
            {"channel": "output", "text": "  λ", "mode": "snapshot"},
            {"channel": "output", "text": final, "mode": "snapshot"},
        ], seen)
        extensions = observation["extensions"]
        self.assertNotIn("content_base64", extensions["arcgrav.runner:submitted_input"])
        self.assertEqual(_sha256(frame), extensions["arcgrav.runner:submitted_input"]["sha256"])
        self.assertEqual(final.encode(), base64.b64decode(extensions["openai.codex-cli:response_base64"]))
        self.assertNotIn("arcgrav.runner:process_stdout_base64", extensions)
        self.assertNotIn("arcgrav.runner:process_stderr_base64", extensions)

    def test_callback_failure_cannot_change_terminal_response(self):
        runner = CodexCliRunner(transport=FakeCodexTransport(), executable_resolver=lambda _: sys.executable)
        self.addCleanup(runner.close)
        def broken(event):
            raise RuntimeError("presentation is closed")
        observation = runner.execute(_request(_boundary()), event_callback=broken)
        self.assertEqual("completed", observation["terminal_status"])
        self.assertEqual(b"exact final answer\n", base64.b64decode(observation["extensions"]["openai.codex-cli:response_base64"]))

    def test_text_view_does_not_repair_or_reject_binary_request_bytes(self):
        transport = FakeCodexTransport()
        runner = CodexCliRunner(transport=transport, executable_resolver=lambda _: sys.executable)
        self.addCleanup(runner.close)
        request = _request(_boundary())
        request["input"] = {"content": b"\xff\x00", "sha256": _sha256(b"\xff\x00")}
        request["request_identity"]["input_sha256"] = request["input"]["sha256"]
        seen = []
        observation = runner.execute(request, event_callback=seen.append)
        self.assertEqual("completed", observation["terminal_status"])
        self.assertEqual(b"\xff\x00", transport.calls[-1]["input_bytes"][-2:])
        self.assertEqual(["output"], [event["channel"] for event in seen])

    def test_preflight_and_spawn_failure_do_not_claim_submitted_input(self):
        class SpawnFailure(FakeCodexTransport):
            def run_streaming(self, argv, **kwargs):
                if kwargs["input_bytes"] is not None:
                    raise OSError("cannot spawn")
                kwargs = {key: value for key, value in kwargs.items()
                          if key not in {"on_input", "on_stdout", "cancellation_requested"}}
                return self.run(argv, **kwargs)
        for transport, resolver in ((FakeCodexTransport(), lambda _: None), (SpawnFailure(), lambda _: sys.executable)):
            seen = []
            runner = CodexCliRunner(transport=transport, executable_resolver=resolver)
            self.addCleanup(runner.close)
            observation = runner.execute(_request(_boundary()), event_callback=seen.append)
            self.assertNotEqual("completed", observation["terminal_status"])
            self.assertEqual([], seen)
            self.assertNotIn("arcgrav.runner:submitted_input", observation["extensions"])
