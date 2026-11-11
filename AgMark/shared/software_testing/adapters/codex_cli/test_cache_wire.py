"""Opt-in wire audit of the installed Codex CLI against a local Responses server.

AGMARK_CODEX_CACHE_TEST_BINARY selects the real binary, audited at 0.159.0.
AGMARK_CODEX_CACHE_TEST_WSL_LAUNCHER also exercises the actual WSL launcher.
The local server supplies deterministic tool activity and Guardian assessments;
its counters do not test provider cache behavior. No credentials or provider
submissions are required. AGMARK_CACHE_AUDIT_DIRECTORY retains request bodies
and identity headers separately from inferred rollout policy.
"""
import concurrent.futures
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import threading
import unittest

from AgMark.shared.adapters.Codex_CLI.runner import CodexCliRunner
from AgMark.shared.adapters.Codex_CLI.session import extract_session_measurements, returned_thread_id
from AgMark.shared.adapters.Codex_CLI.session_capture import read_session


@unittest.skipUnless(os.name == "posix" and os.environ.get("AGMARK_CODEX_CACHE_TEST_BINARY"),
                     "Select an installed Codex 0.159.0 binary for the wire audit")
class CacheWireTests(unittest.TestCase):
    @contextmanager
    def wire_audit(self, response_item):
        binary = os.environ["AGMARK_CODEX_CACHE_TEST_BINARY"]
        version = subprocess.run([binary, "--version"], capture_output=True, check=True, timeout=10)
        self.assertEqual(b"codex-cli 0.159.0", version.stdout.strip())
        captures, lock = [], threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with lock:
                    captures.append({"body": body, "headers": {
                        name: self.headers.get(name) for name in ("session-id", "thread-id")}})
                    response_id = "resp_" + str(len(captures))
                item = response_item(body)
                events = [{"type": "response.created", "response": {"id": response_id}},
                          {"type": "response.output_item.done", "item": item},
                          {"type": "response.completed", "response": {"id": response_id, "usage": {
                              "input_tokens": 100, "input_tokens_details": {"cached_tokens": 0},
                              "output_tokens": 5, "total_tokens": 105}}}]
                raw = "".join("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n" for event in events).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix="agmark-cache-wire-") as directory:
                root = Path(directory)
                home = root / "codex-home"
                home.mkdir()
                # Test-only supported provider configuration. AgMark's launch
                # arguments and benchmark framing pass through unchanged.
                config = ['model_provider="cache_audit"', 'model_providers.cache_audit.name="Cache audit"',
                          f'model_providers.cache_audit.base_url="http://127.0.0.1:{server.server_port}/v1"',
                          'model_providers.cache_audit.wire_api="responses"',
                          'model_providers.cache_audit.requires_openai_auth=false',
                          'model_providers.cache_audit.supports_websockets=false']
                prefix = [binary]
                for setting in config:
                    prefix.extend(["-c", setting])
                wrapper = root / "codex-wrapper"
                wrapper.write_text("#!/bin/sh\nexport CODEX_HOME=" + shlex.quote(str(home)) + "\nexec " + shlex.join(prefix) + ' "$@"\n')
                wrapper.chmod(0o700)

                def run(mode, prompt):
                    with tempfile.TemporaryDirectory(dir=root) as workdir:
                        if mode == "native":
                            argv = CodexCliRunner._native_exec_argv({"executable": str(wrapper)}, "gpt-5-codex")
                        else:
                            argv = CodexCliRunner._wsl_exec_argv({"launcher": os.environ["AGMARK_CODEX_CACHE_TEST_WSL_LAUNCHER"],
                                "distribution": os.environ.get("AGMARK_CODEX_CACHE_TEST_WSL_DISTRIBUTION", "Ubuntu"),
                                "executable": str(wrapper)}, "gpt-5-codex")
                        process = subprocess.run(argv, input=prompt, cwd=workdir, capture_output=True, timeout=35)
                        self.assertEqual(0, process.returncode, process.stderr.decode(errors="replace"))
                        thread_id = returned_thread_id(process.stdout)
                        self.assertIsNotNone(thread_id)
                        record = read_session(thread_id, root=home / "sessions")
                        self.assertEqual("retained", record["availability"])
                        _, record = extract_session_measurements(record, process.stdout, runtime_version="0.159.0", process_complete=True)
                        return {"mode": mode, "prompt": prompt.decode(), "stdout": process.stdout.decode(), "session_record": record}

                yield run, captures
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)

    def assert_root_requests(self, result, requests, count):
        key = result["session_record"]["thread_id"]
        self.assertEqual(count, len(requests))
        for request in requests:
            self.assertEqual(key, request["body"]["prompt_cache_key"])
            self.assertEqual(key, request["headers"]["session-id"])
            self.assert_implicit_request(request)
            user_content = [item["content"] for item in request["body"]["input"] if item.get("role") == "user"]
            self.assertTrue(any(any(part.get("text") == result["prompt"] for part in content) for content in user_content))
        policy = result["session_record"]["cache_policy"]
        self.assertEqual(key, policy["cache_key_value"])
        self.assertFalse(policy["cache_key_observed"])
        self.assertFalse(policy["derived_contexts_observed"])

    def assert_implicit_request(self, request):
        self.assertNotIn("prompt_cache_options", request["body"])
        self.assertNotIn("prompt_cache_breakpoint", json.dumps(request["body"]))

    def retain_audit(self, filename, results, captures):
        evidence_directory = os.environ.get("AGMARK_CACHE_AUDIT_DIRECTORY")
        if evidence_directory:
            output = Path(evidence_directory)
            output.mkdir(parents=True, exist_ok=True)
            (output / filename).write_text(json.dumps({"runtime_version": "0.159.0",
                "purpose": "Observed request-key policy; simulated counters are not provider behavior evidence.",
                "results": results, "captures": captures}, indent=2) + "\n")

    def test_fresh_repeated_concurrent_native_and_wsl_root_request_keys(self):
        def response_item(body):
            second = any(item.get("type") == "function_call_output" for item in body.get("input", []))
            return ({"type": "message", "role": "assistant", "id": "answer",
                     "content": [{"type": "output_text", "text": "done"}]} if second else
                    {"type": "function_call", "call_id": "call_probe", "name": "exec_command",
                     "namespace": "functions", "arguments": json.dumps({"cmd": "printf cache-probe", "max_output_tokens": 20})})

        with self.wire_audit(response_item) as (run, captures):
            prompt = b"adapter prompt\n\nadapter input"
            results = [run("native", prompt), run("native", prompt), run("native", b"other treatment\n\nadapter input")]
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                results.extend(pool.map(lambda _: run("native", prompt), range(2)))
            if os.environ.get("AGMARK_CODEX_CACHE_TEST_WSL_LAUNCHER"):
                results.extend([run("wsl", prompt), run("wsl", prompt)])
                with concurrent.futures.ThreadPoolExecutor(2) as pool:
                    results.extend(pool.map(lambda _: run("wsl", prompt), range(2)))
            keys = [result["session_record"]["thread_id"] for result in results]
            self.assertEqual(len(keys), len(set(keys)))
            for result, key in zip(results, keys):
                requests = [capture for capture in captures if capture["headers"]["thread-id"] == key]
                self.assert_root_requests(result, requests, 2)
            self.assertEqual(2 * len(results), len(captures))
            self.retain_audit("wire-audit.json", results, captures)

    def test_guardian_keys_are_stable_and_invocation_scoped_native_and_wsl(self):
        def response_item(body):
            if body.get("client_metadata", {}).get("x-openai-subagent") == "guardian":
                text = json.dumps({"risk_level": "low", "user_authorization": "high", "outcome": "allow",
                                   "rationale": "Harmless local diagnostic command."})
                return {"type": "message", "role": "assistant", "id": "review",
                        "content": [{"type": "output_text", "text": text}]}
            outputs = [item for item in body.get("input", []) if item.get("type") == "function_call_output"]
            if len(outputs) < 2:
                # A harmless test-only request deliberately exercises automatic
                # review twice. Production arguments and framing are unchanged.
                return {"type": "function_call", "call_id": "call_review_" + str(len(outputs)),
                        "name": "exec_command", "namespace": "functions", "arguments": json.dumps({
                            "cmd": "printf guardian-cache-probe", "sandbox_permissions": "require_escalated",
                            "justification": "Local cache-key audit.", "max_output_tokens": 20})}
            return {"type": "message", "role": "assistant", "id": "answer",
                    "content": [{"type": "output_text", "text": "done"}]}

        with self.wire_audit(response_item) as (run, captures):
            prompt = b"adapter prompt\n\nadapter input"
            modes = ["native"]
            if os.environ.get("AGMARK_CODEX_CACHE_TEST_WSL_LAUNCHER"):
                modes.append("wsl")
            results = []
            for mode in modes:
                results.extend([run(mode, prompt), run(mode, prompt)])
                with concurrent.futures.ThreadPoolExecutor(2) as pool:
                    results.extend(pool.map(lambda _: run(mode, prompt), range(2)))
            keys = [result["session_record"]["thread_id"] for result in results]
            self.assertEqual(len(keys), len(set(keys)))
            guardian_threads = []
            for result, key in zip(results, keys):
                root_requests = [capture for capture in captures if capture["headers"]["thread-id"] == key]
                self.assert_root_requests(result, root_requests, 3)
                reviews = [capture for capture in captures
                           if capture["body"].get("client_metadata", {}).get("x-codex-parent-thread-id") == key]
                self.assertEqual(2, len(reviews))
                threads = {review["headers"]["thread-id"] for review in reviews}
                self.assertEqual(1, len(threads))
                guardian_thread = threads.pop()
                self.assertIsInstance(guardian_thread, str)
                self.assertNotIn(guardian_thread, keys)
                guardian_threads.append(guardian_thread)
                for review in reviews:
                    body = review["body"]
                    self.assertEqual("guardian:" + key, body["prompt_cache_key"])
                    self.assertEqual(key, review["headers"]["session-id"])
                    metadata = body["client_metadata"]
                    self.assertEqual("guardian", metadata["x-openai-subagent"])
                    self.assertEqual(key, metadata["session_id"])
                    turn = json.loads(metadata["x-codex-turn-metadata"])
                    self.assertEqual(key, turn["parent_thread_id"])
                    self.assertEqual(guardian_thread, turn["thread_id"])
                    self.assert_implicit_request(review)
                # Wire captures are observed evidence; the separate rollout
                # extractor still has only inferred policy and no wire input.
                result["observed_guardian_context"] = {
                    "context_type": "guardian_review", "thread_id": guardian_thread,
                    "parent_thread_id": key, "cache_key_value": "guardian:" + key,
                    "cache_key_policy": "codex_guardian_parent_thread_id",
                    "cache_key_provenance": "observed_outgoing_request", "cache_key_observed": True,
                    "session_id_header": key, "request_count": len(reviews)}
            self.assertEqual(len(guardian_threads), len(set(guardian_threads)))
            self.assertEqual(5 * len(results), len(captures))
            self.retain_audit("guardian-wire-audit.json", results, captures)
