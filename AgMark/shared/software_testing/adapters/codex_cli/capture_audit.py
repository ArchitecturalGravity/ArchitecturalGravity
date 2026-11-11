"""Opt-in real CLI capture audit against a disposable loopback Responses server.

Run as a module from the directory containing AgMark. This developer tool uses
no credentials or real provider. Evidence is sanitized by production capture;
simulated counters establish extraction semantics, not provider cache behavior.
The WSL option is run from the selected Linux distribution with wsl.exe interop.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import threading
import time
from unittest.mock import patch

from AgMark.shared.adapters.Codex_CLI.runner import CodexCliRunner
from AgMark.shared.adapters.Codex_CLI.session import extract_session_measurements, returned_thread_id
from AgMark.shared.adapters.Codex_CLI.session_capture import read_session
from AgMark.shared.telemetry.capture import CaptureSession
from AgMark.shared.telemetry.evidence import canonical_bytes, digest, validate_manifest
from AgMark.shared.telemetry.normalization import normalize_capture
from AgMark.shared.telemetry.profile import CaptureProfile
from AgMark.shared.telemetry.wsl import WslCaptureSession
from AgMark.shared.validation.codex_cache import collector, host_worker
from AgMark.shared.validation.codex_cache.capabilities import admit_controlled_probe


def diagnostic_scope_accounted(manifest):
    """Allow excluded auxiliary roots only with a complete primary graph."""
    health = manifest["sources"]["diagnostics"]
    payloads = [r["payload"] for r in manifest["records"] if r["source"] == "diagnostics"]
    graphs = [p for p in payloads if p.get("type") == "reduced_graph"]
    nodes = [p for p in payloads if p.get("type") == "reduced_graph_node"]
    return (health.get("reduced_graph", {}).get("state") == "retained" and bool(graphs)
        and not any(health[k] for k in ("parse_errors", "dropped", "partial"))
        and all(p.get("schema_version") != 2 or p.get("recording_complete") is True for p in graphs)
        and sum(sum(p["graph_counts"].values()) for p in graphs) == len(nodes)
        and (health["state"] == "settled" and health["rejected"] == 0 or
             health["state"] == "partial" and health["reason"] == "diagnostic_graph_root_unmatched"))


def audit_case(binary, identity, profile_id, transport, *, output, launch=None, scenario="completed"):
    mode = "wsl" if launch else "native"
    name = f"{mode}-{profile_id}-{transport}-{scenario}"
    provider_received = threading.Event()
    evidence = {}
    server_type = host_worker.ThreadingHTTPServer

    def provider_server(address, handler):
        events = handler.events
        def observed_events(self, body):
            result = events(self, body)
            provider_received.set()
            if scenario == "failed":
                return [{"type": "response.failed", "response": {"id": "controlled_failure",
                    "error": {"code": "invalid_prompt", "message": "Controlled local failure"}}}]
            if scenario == "cancelled":
                time.sleep(1)
            return result
        handler.events = observed_events
        server = server_type(address, handler)
        # A cancellation can close the controlled provider's socket mid-write.
        server.handle_error = lambda *_: None
        return server

    def execute(args, *, data, cwd, env, timeout):
        profile = CaptureProfile(id=profile_id,
            diagnostic_privacy_acknowledged=profile_id == "deep_telemetry")
        common = dict(profile=profile, runtime_version=identity["version"],
            invocation_id="observation:" + hashlib.sha256(name.encode()).hexdigest())
        capture = (WslCaptureSession(**common, launch_metadata=launch, environment=dict(os.environ))
                   if launch else CaptureSession(**common))
        with capture:
            capture.runtime["binary_sha256"] = identity["binary_sha256"]
            provider_flags = tuple(args[1:args.index("exec")])
            if launch:
                # Keep the real user's configuration/auth out of this audit.
                wrapper = Path(cwd) / "audit-codex"
                wrapper.write_text("#!/bin/sh\nexport CODEX_HOME=" + shlex.quote(env["CODEX_HOME"])
                    + "\nexec " + shlex.quote(binary) + ' "$@"\n')
                wrapper.chmod(0o700)
                base = CodexCliRunner._wsl_exec_argv({**launch, "executable": str(wrapper)}, "gpt-5-codex")
                base = (*base, *provider_flags)
            else:
                base = CodexCliRunner._native_exec_argv({"executable": binary}, "gpt-5-codex")
                base = (*base[:-1], *provider_flags, base[-1])
            argv = CodexCliRunner._capture_argv(base, capture.config_overrides, mode,
                capture.env_overrides, getattr(capture, "process_control_path", None))
            environment = dict(env)
            if not launch:
                for key, value in capture.env_overrides.items():
                    if value is None:
                        environment.pop(key, None)
                    else:
                        environment[key] = value
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=cwd, env=environment,
                start_new_session=os.name == "posix")
            def cancel():
                if provider_received.wait(timeout=15) and process.poll() is None:
                    if launch:
                        capture.stop_execution()
                    elif os.name == "posix":
                        try:
                            os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    else:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            killer = threading.Thread(target=cancel, daemon=True) if scenario == "cancelled" else None
            if killer:
                killer.start()
            try:
                stdout, stderr = process.communicate(data, timeout=timeout)
            except subprocess.TimeoutExpired:
                if launch:
                    capture.stop_execution()
                process.kill()
                stdout, stderr = process.communicate(timeout=10)
            if killer:
                killer.join(timeout=5)
            thread = returned_thread_id(stdout)
            record = read_session(thread, root=Path(env["CODEX_HOME"]) / "sessions")
            version = identity["version"].removeprefix("codex-cli ")
            measurements, retained = extract_session_measurements(record, stdout,
                runtime_version=version, process_complete=True)
            reductions = capture.reduce_diagnostics(binary) if profile.diagnostics_enabled else ()
            status = scenario if scenario != "completed" else ("completed" if process.returncode == 0 else "failed")
            manifest = capture.finish(stdout=stdout, stderr=stderr,
                rollout_record=record, process_status={"status": status})
            normalized = normalize_capture(manifest)
            validate_manifest(manifest)
            assert normalized == normalize_capture(json.loads(json.dumps(manifest)))
            assert (measurements, retained) == extract_session_measurements(retained, stdout,
                runtime_version=version, process_complete=True)
            events = [json.loads(line)["type"] for line in stdout.splitlines() if line.strip()]
            checks = {"manifest_valid": True, "reconstruction_equal": True,
                "runtime_identity_unchanged": host_worker._runtime_identity(binary) == identity}
            if scenario == "completed":
                expected = {"stdout", "process", "rollout"}
                if profile.enabled:
                    expected.update(("otel_logs", "otel_traces", "otel_metrics"))
                checks.update(process_completed=process.returncode == 0,
                    expected_sources_settled=all(manifest["sources"][s]["state"] == "settled" for s in expected),
                    rollout_complete=retained["trace_complete"],
                    usage_records_observed=bool(retained["completed_response_usage"]),
                    tool_observed=any(r["type"] == "response_item" and r["payload"].get("type") == "function_call"
                                      for r in retained["source_records"]))
                if profile.diagnostics_enabled:
                    checks["diagnostic_graph_scope_accounted"] = diagnostic_scope_accounted(manifest)
                raw_rows = [json.loads(line) for line in base64.b64decode(record["content_base64"]).splitlines() if line.strip()]
                usages = [row["payload"] for row in raw_rows if row["type"] == "token_usage_record"]
                fields = {"input_tokens": 100, "cached_input_tokens": 20,
                    "cache_write_input_tokens": 11, "output_tokens": 7, "reasoning_output_tokens": 3}
                checks["independent_response_counters_equal"] = bool(usages) and all(
                    row["response_id"].startswith("resp_") and all(
                        row["usage"][field] == scale * int(row["response_id"].removeprefix("resp_"))
                        for field, scale in fields.items()) for row in usages)
                checks["cumulative_counters_equal"] = all(
                    measurements["roles"][role]["value"] == sum(row["usage"][field] for row in usages)
                    for role, field in (("input_tokens", "input_tokens"), ("cached_input_tokens", "cached_input_tokens"),
                        ("output_tokens", "output_tokens"), ("reasoning_tokens", "reasoning_output_tokens")))
            else:
                checks.update(process_did_not_complete=process.returncode != 0,
                    failure_visible="turn.failed" in events if scenario == "failed" else manifest["completeness"]["status"] == "partial")
            evidence.update(manifest=manifest, normalized=normalized,
                measurements=measurements, session_record=retained)
            evidence["summary"] = {"name": name, "runtime": identity, "checks": checks,
                "passed": all(checks.values()), "returncode": process.returncode,
                "stdout_events": {event: events.count(event) for event in sorted(set(events))},
                "sources": {source: {k: health[k] for k in ("state", "reason", "retained_events", "rejected", "parse_errors")}
                            for source, health in manifest["sources"].items()},
                "manifest_sha256": manifest["integrity"]["manifest_sha256"],
                "session_source_sha256": retained["sha256"],
                "normalized_sha256": digest(canonical_bytes(normalized)),
                "token_counters": {role: measurements["roles"][role]["value"]
                    for role in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")},
                "reductions": reductions}
            return process.returncode, None

    with patch.object(host_worker, "LoopbackTraceCollector", collector.LoopbackTraceCollector, create=True), \
         patch.object(host_worker, "observation_overrides", return_value=(), create=True), \
         patch.object(host_worker, "ThreadingHTTPServer", provider_server), \
         patch.object(host_worker, "_run_process", execute):
        probe = host_worker._probe_transport({"snapshot": {"executable": binary, **identity}}, transport)
    evidence["summary"]["provider_requests"] = probe["provider_requests"]
    path = output / (name + ".json")
    path.write_bytes(canonical_bytes(evidence) + b"\n")
    print(name + ": " + ("passed" if evidence["summary"]["passed"] else "FAILED"), flush=True)
    return evidence["summary"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--wsl-launcher")
    parser.add_argument("--distribution", default="Ubuntu")
    options = parser.parse_args()
    binary = str(Path(shutil.which(options.binary) or options.binary).resolve(strict=True))
    options.output.mkdir(parents=True, exist_ok=True)
    identity = host_worker._runtime_identity(binary)
    host_worker.LoopbackTraceCollector = collector.LoopbackTraceCollector
    host_worker.observation_overrides = collector.observation_overrides
    probe = host_worker._probe({"snapshot": {"executable": binary, **identity}})
    _, admitted = admit_controlled_probe(probe, binary_sha256=identity["binary_sha256"],
        runtime_version=identity["version"].removeprefix("codex-cli "))
    for name, raw in admitted.items():
        (options.output / (name + ".json")).write_bytes(raw)
    launch = ({"launcher": options.wsl_launcher, "distribution": options.distribution,
               "executable": binary} if options.wsl_launcher else None)
    results = [audit_case(binary, identity, profile, transport, output=options.output, launch=launch)
        for profile in ("session", "telemetry", "deep_telemetry") for transport in ("http", "websocket")]
    results.extend(audit_case(binary, identity, "telemetry", "http", scenario=scenario,
        output=options.output, launch=launch) for scenario in ("failed", "cancelled"))
    summary = {"runtime": identity, "request_capability_admission": "passed",
        "provider": "controlled loopback only; synthetic usage; no provider cache behavior claim",
        "cases": results, "passed": all(result["passed"] for result in results)}
    (options.output / "summary.json").write_bytes(canonical_bytes(summary) + b"\n")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
