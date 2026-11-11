"""Original invocation capture lifecycle; does not run or score a benchmark."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
from itertools import islice
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time

from .collector import MultiSignalCollector, decode_document
from .evidence import EvidenceLedger, digest, validate_manifest, _HEALTH_LABELS
from .privacy import AliasRegistry, Sanitizer
from .profile import is_safe_invocation_id
from .profile import CaptureProfile, capability, disabled_overrides, observation_overrides

_GRAPH_FAMILIES = ("threads", "codex_turns", "conversation_items", "inference_calls", "code_cells",
    "tool_calls", "terminal_sessions", "terminal_operations", "compactions", "compaction_requests", "interaction_edges")


@contextmanager
def _preserve_source_problems(ledger, *sources):
    """Final evidence arrivals cannot erase earlier source failure authority."""
    previous = {name: (ledger.sources[name]["state"], ledger.sources[name]["reason"])
                for name in sources if ledger.sources[name]["state"] in {"partial", "failed"}}
    try:
        yield
    finally:
        for name, (state, reason) in previous.items():
            current = ledger.sources[name]
            later_problem = current["reason"] if current["state"] in {"partial", "failed"} else None
            reasons = list(dict.fromkeys(r for r in (*current.get("reasons", ()), reason, later_problem) if r))
            if reasons:
                current["reasons"] = reasons
            # A newly observed outright failure can strengthen an earlier
            # partial state. Otherwise preserve the original failure and reason.
            if current["state"] != "failed" or state == "failed":
                ledger.state(name, state, reason)


class CaptureSession:
    """Start before stock exec, finish after process exit and rollout settlement.

``config_overrides`` are stock ``-c`` settings; ``env_overrides`` values of None
mean remove inherited variables. No prompt, runtime, credential, or input bytes
are changed. Telemetry failure does not manufacture benchmark failure/success.
    """
    def __init__(self, profile=None, runtime_version=None, invocation_id=None, on_progress=None,
                 *, launch_mode="native", temporary_root=None, cancellation_requested=None):
        self.profile = profile or CaptureProfile()
        if not isinstance(self.profile, CaptureProfile):
            raise TypeError("capture requires a versioned CaptureProfile")
        # Observation IDs remain verbatim evidence identities, never filenames.
        # GUI diagnostics use a colon; scratch paths are independently generated.
        if not is_safe_invocation_id(invocation_id):
            raise ValueError("capture requires a canonical non-personal invocation identifier")
        self.runtime = capability(runtime_version, launch_mode)
        self.invocation_id = invocation_id
        self.on_progress = on_progress
        self.temporary_root = temporary_root
        self.aliases = AliasRegistry()
        self.ledger = EvidenceLedger(self.profile, invocation_id, self.runtime)
        self.ledger.aliases = self.aliases
        self.config_overrides = ()
        self.env_overrides = {"CODEX_ROLLOUT_TRACE_ROOT": None}
        self.collector = None
        self.diagnostic_root = None
        self._started = False
        self._finished = False
        self._finishing = False
        self._manifest = None
        self._lock = threading.RLock()
        self._stdout_buffer = bytearray()
        self._hashers = {name: hashlib.sha256() for name in ("stdout", "stderr")}
        self._stream_bytes = {"stdout": 0, "stderr": 0}
        self._returned_threads = []
        self._last_progress = 0.0
        self._last_stdout_type = None
        self._stdout_discard_until_newline = False
        self._diagnostic_reduction_attempted = False
        self._cancellation_requested = cancellation_requested
        self._diagnostic_cancelled = False

    def _progress(self, phase, *, force=True, sealed=False):
        if self.on_progress is None:
            return
        if phase == "capture" and (self._finished or self._finishing):
            return
        now = time.monotonic()
        if not force and now - self._last_progress < 0.1:
            return
        self._last_progress = now
        sources = list(self.ledger.snapshot().values())
        outcome = "pending"
        if sealed:
            outcome = self._manifest["completeness"]["status"]
        try:
            self.on_progress({"invocation_id": self.invocation_id, "scope": "original", "phase": phase,
                "sources": sources, "evidence_sealed": sealed, "telemetry_outcome": outcome})
        except Exception:
            # Presentation callbacks cannot terminate capture or stock execution.
            pass

    def start(self):
        with self._lock:
            if self._started:
                raise RuntimeError("capture session is invocation-scoped and cannot restart")
            self._started = True
            self._progress("preflight")
            for source in ("stdout", "stderr", "process", "rollout"):
                self.ledger.state(source, "ready")
            self.ledger.add("process", {"phase": "collector_readiness", "status": "started"})
            if not self.profile.enabled:
                self.config_overrides = disabled_overrides()
                for source in ("otel_logs", "otel_traces", "otel_metrics", "diagnostics"):
                    self.ledger.state(source, "disabled", "legacy_capture_profile")
            elif self.runtime["capability_status"] != "supported":
                for source in ("otel_logs", "otel_traces", "otel_metrics", "diagnostics"):
                    self.ledger.state(source, "unsupported", self.runtime["reason"])
            else:
                try:
                    self.collector = MultiSignalCollector(self.ledger,
                        on_change=lambda: self._progress("capture", force=False)).start()
                    self.config_overrides = observation_overrides(self.invocation_id, self.collector.endpoint)
                except (OSError, RuntimeError, ValueError):
                    if self.collector is not None:
                        self.collector.close()
                    self.collector = None
                    for source in ("otel_logs", "otel_traces", "otel_metrics"):
                        self.ledger.state(source, "failed", "local_receiver_start_failed")
                if self.profile.diagnostics_enabled:
                    try:
                        self.diagnostic_root = Path(tempfile.mkdtemp(prefix="agmark-diagnostic-", dir=self.temporary_root))
                        self.diagnostic_root.chmod(0o700)
                        self.env_overrides["CODEX_ROLLOUT_TRACE_ROOT"] = str(self.diagnostic_root)
                        self.ledger.state("diagnostics", "ready")
                    except OSError:
                        self.ledger.state("diagnostics", "failed", "private_diagnostic_directory_unavailable")
                else:
                    self.ledger.state("diagnostics", "disabled", "explicit_sensitive_diagnostic_opt_in_required")
            self._progress("collector_readiness")
            self._progress("execution")
            return self

    def _record_json(self, source, raw):
        try:
            record = decode_document(raw)
            if not isinstance(record, dict):
                raise ValueError("structural event must be an object")
            sanitizer = Sanitizer(aliases=self.aliases, source=source)
            safe = sanitizer.value(record)
            self.ledger.excluded_fields += sanitizer.excluded_fields
            self.ledger.truncated_fields += sanitizer.truncated_fields
            if source == "stdout":
                self._last_stdout_type = safe.get("type")
                if safe.get("type") == "thread.started" and isinstance(safe.get("thread_id"), str):
                    self._returned_threads.append(record["thread_id"])
            self.ledger.add(source, safe)
            return True
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self.ledger.count(source, parse_errors=1)
            self.ledger.state(source, "partial", "malformed_or_truncated_structural_event")
            return False

    def ingest_stdout(self, chunk):
        self._ingest("stdout", chunk)

    def ingest_stderr(self, chunk):
        self._ingest("stderr", chunk)

    def _ingest(self, source, chunk):
        with self._lock:
            if not self._started or self._finished:
                raise RuntimeError("stream ingestion requires an active invocation")
            if not isinstance(chunk, bytes):
                raise TypeError("captured stream chunks must be bytes")
            if not chunk:
                return
            self._hashers[source].update(chunk)
            self._stream_bytes[source] += len(chunk)
            self.ledger.count(source, received_bytes=len(chunk))
            if source == "stderr":
                # Stderr is free-form and may carry credentials. Only its channel
                # presence, chunk order and byte count enter sanitized telemetry.
                self.ledger.add(source, {"byte_length": len(chunk), "content_excluded": True})
            else:
                if self._stdout_discard_until_newline:
                    _, newline, chunk = chunk.partition(b"\n")
                    if not newline:
                        return
                    self._stdout_discard_until_newline = False
                self._stdout_buffer.extend(chunk)
                while b"\n" in self._stdout_buffer:
                    line, _, rest = self._stdout_buffer.partition(b"\n")
                    self._stdout_buffer = bytearray(rest)
                    if line.strip():
                        if len(line) <= self.profile.max_payload_bytes:
                            self._record_json(source, bytes(line))
                        else:
                            self.ledger.count(source, dropped=1)
                            self.ledger.state(source, "partial", "stream_event_size_limit")
                if len(self._stdout_buffer) > self.profile.max_payload_bytes:
                    self._stdout_buffer.clear()
                    self._stdout_discard_until_newline = True
                    self.ledger.count(source, dropped=1)
                    self.ledger.state(source, "partial", "stream_event_size_limit")
            self._progress("capture", force=False)

    def _finish_stream(self, source, raw):
        if raw is not None and not isinstance(raw, bytes):
            raise TypeError("final captured stream must be bytes or None")
        if raw is not None:
            count = self._stream_bytes[source]
            if count == 0:
                self._ingest(source, raw)
            elif count < len(raw) and self._hashers[source].hexdigest() == hashlib.sha256(raw[:count]).hexdigest():
                self._ingest(source, raw[count:])
            elif count != len(raw) or self._hashers[source].hexdigest() != hashlib.sha256(raw).hexdigest():
                self.ledger.count(source, partial=1)
                self.ledger.state(source, "partial", "stream_final_bytes_disagree")
        if source == "stdout" and self._stdout_buffer.strip():
            self._record_json("stdout", bytes(self._stdout_buffer))
            self._stdout_buffer.clear()
        health = self.ledger.sources[source]
        if health["state"] != "partial":
            self.ledger.state(source, "settled" if raw is not None or self._stream_bytes[source] else "unavailable",
                None if raw is not None or self._stream_bytes[source] else "stream_not_supplied")
            if source == "stdout" and not self._stream_bytes[source]:
                self.ledger.state(source, "unavailable", "stdout_empty")
            elif source == "stdout" and self._last_stdout_type not in {"turn.completed", "turn.failed"}:
                self.ledger.count(source, partial=1)
                self.ledger.state(source, "partial", "process_ended_without_terminal_event")

    def _finish_rollout(self, record):
        if not isinstance(record, dict) or record.get("availability") != "retained":
            reason = record.get("reason") if isinstance(record, dict) else None
            reason = reason if isinstance(reason, str) and reason in _HEALTH_LABELS else "exact_thread_rollout_unavailable"
            self.ledger.state("rollout", "unavailable", reason)
            return
        try:
            raw = base64.b64decode(record["content_base64"], validate=True)
            if len(raw) > self.profile.max_retained_bytes:
                self.ledger.count("rollout", dropped=1)
                self.ledger.state("rollout", "partial", "rollout_byte_limit")
                return
            lines = [line for line in raw.splitlines() if line.strip()]
            first = decode_document(lines[0]) if lines else {}
            thread_id = self._returned_threads[0] if len(self._returned_threads) == 1 else None
            if (thread_id is None or record.get("thread_id") != thread_id or not lines
                    or first.get("type") != "session_meta"
                    or first.get("payload", {}).get("id") != thread_id
                    or first.get("payload", {}).get("forked_from_id") is not None):
                self.ledger.state("rollout", "unavailable", "session_thread_id_mismatch")
                return
            self.ledger.count("rollout", received_bytes=len(raw))
            self.ledger.sources["rollout"].update(thread_id=self.aliases.identity(thread_id))
            for line in lines:
                self._record_json("rollout", line)
            try:
                last = decode_document(lines[-1])
                terminal = isinstance(last, dict) and last.get("type") == "event_msg" and isinstance(last.get("payload"), dict) and last["payload"].get("type") in {"task_complete", "turn_aborted"}
            except (ValueError, UnicodeError, RecursionError):
                terminal = False
            if not terminal:
                self.ledger.count("rollout", partial=1)
                self.ledger.state("rollout", "partial", "rollout_terminal_event_unobserved")
            elif self.ledger.sources["rollout"]["state"] != "partial":
                self.ledger.state("rollout", "settled")
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError, RecursionError):
            self.ledger.count("rollout", parse_errors=1)
            self.ledger.state("rollout", "partial", "malformed_rollout_bytes")

    def reduce_diagnostics(self, executable, *, timeout_seconds=10):
        """Run the exposed stock offline reducer only for an admitted opt-in profile.

The stock reducer's sensitive state remains in the private temporary bundle.
Only its return status is retained here; no subprocess output is captured.
        """
        if not self.profile.diagnostics_enabled or self.diagnostic_root is None or self._finished:
            raise ValueError("diagnostic reduction requires active explicit privacy opt-in")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("diagnostic reducer timeout must be bounded")
        self._diagnostic_reduction_attempted = True
        results = []
        deadline = time.monotonic() + timeout_seconds
        manifests = list(islice(self.diagnostic_root.glob("*/manifest.json"), 65))
        if len(manifests) > 64:
            self.ledger.count("diagnostics", dropped=1)
        for manifest in sorted(manifests[:64]):
            if manifest.is_symlink() or manifest.parent.is_symlink():
                continue
            if time.monotonic() >= deadline:
                self.ledger.count("diagnostics", partial=1)
                self.ledger.state("diagnostics", "partial", "diagnostic_reduction_deadline")
                break
            try:
                completed = subprocess.run([str(executable), "debug", "trace-reduce", str(manifest.parent)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=max(0.001, deadline - time.monotonic()), check=False)
                result = {"phase": "reduction", "return_code": completed.returncode,
                    "status": "completed" if completed.returncode == 0 else "failed"}
            except (OSError, subprocess.TimeoutExpired):
                result = {"phase": "reduction", "status": "failed", "reason": "stock_trace_reduce_failed_or_timed_out"}
            self.ledger.add("diagnostics", result)
            if result["status"] != "completed":
                self.ledger.count("diagnostics", partial=1)
            results.append(result)
        return tuple(results)

    def _retain_diagnostic_graph(self, raw, *, deadline):
        """Retain stock reducer nodes and explicit edges, excluding all text payloads."""
        try:
            state = decode_document(raw)
            if (not isinstance(state, dict) or type(state.get("schema_version")) is not int
                    or state["schema_version"] not in {1, 2}):
                raise ValueError("unsupported stock diagnostic graph schema")
            if state["schema_version"] == 2 and type(state.get("recording_complete")) is not bool:
                raise ValueError("missing stock diagnostic recording outcome")
            thread_id = self._returned_threads[0] if len(self._returned_threads) == 1 else None
            if thread_id is None or state.get("root_thread_id") != thread_id:
                self.ledger.count("diagnostics", rejected=1)
                self.ledger.state("diagnostics", "partial", "diagnostic_graph_root_unmatched")
                return 0
            sanitizer = Sanitizer(aliases=self.aliases, source="diagnostics")
            header = sanitizer.value({k: v for k, v in state.items() if k not in _GRAPH_FAMILIES and k != "raw_payloads"})
            context = {k: header[k] for k in ("trace_id", "rollout_id", "root_thread_id") if k in header}
            counts = {family: len(state.get(family, {})) for family in _GRAPH_FAMILIES if isinstance(state.get(family), dict)}
            excluded_payloads = len(state.get("raw_payloads", {})) if isinstance(state.get("raw_payloads"), dict) else 0
            self.ledger.add("diagnostics", {**header, "type": "reduced_graph", "representation": "stock_reduced_graph",
                "graph_counts": counts, "raw_payloads_excluded": excluded_payloads})
            if state.get("recording_complete") is False:
                self.ledger.count("diagnostics", partial=1)
                self.ledger.state("diagnostics", "partial", "stock_diagnostic_recording_incomplete")
            retained = 1
            for family in _GRAPH_FAMILIES:
                nodes = state.get(family, {})
                if not isinstance(nodes, dict):
                    self.ledger.count("diagnostics", parse_errors=1)
                    continue
                for object_id, node in nodes.items():
                    if self._diagnostic_processing_stopped(deadline):
                        self.ledger.excluded_fields += sanitizer.excluded_fields + excluded_payloads
                        self.ledger.truncated_fields += sanitizer.truncated_fields
                        return retained
                    safe_id = sanitizer.value(object_id, key="id")
                    if safe_id is None or not isinstance(node, dict):
                        self.ledger.count("diagnostics", rejected=1)
                        continue
                    # Structural graph evidence retains identities/lifecycles.
                    # Conversation bodies, JS and card summaries contain model
                    # text even where an inner key is otherwise structural.
                    safe_node = sanitizer.value({k: v for k, v in node.items()
                        if k not in {"body", "source_js", "summary"}})
                    sanitizer.excluded_fields += sum(k in node for k in ("body", "source_js", "summary"))
                    self.ledger.add("diagnostics", {**context, "type": "reduced_graph_node",
                        "representation": "stock_reduced_graph", "graph_family": family,
                        "graph_object_id": safe_id, "node": safe_node})
                    retained += 1
            self.ledger.excluded_fields += sanitizer.excluded_fields + excluded_payloads
            self.ledger.truncated_fields += sanitizer.truncated_fields
            return retained
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self.ledger.count("diagnostics", parse_errors=1)
            return 0

    def _diagnostic_processing_stopped(self, deadline):
        reason = None
        if self._diagnostic_cancelled or (self._cancellation_requested is not None and self._cancellation_requested()):
            reason = "diagnostic_capture_cancelled"
        elif time.monotonic() >= deadline:
            reason = "diagnostic_parse_deadline"
        elif len(self.ledger.records) >= self.profile.max_records:
            reason = "diagnostic_record_limit"
        if reason is not None:
            self.ledger.count("diagnostics", partial=1)
            self.ledger.state("diagnostics", "partial", reason)
            self.ledger.sources["diagnostics"]["processing"] = {
                "state": "partial", "reason": reason,
                "budget_seconds": max(0.1, self.profile.flush_timeout_seconds)}
            return True
        return False

    def _finish_diagnostics(self):
        if self.diagnostic_root is None:
            return
        seen = 0
        retained_bytes = 0
        graph_records = 0
        deadline = time.monotonic() + max(0.1, self.profile.flush_timeout_seconds)
        try:
            if self._diagnostic_processing_stopped(deadline):
                return
            # Parse the ordered event spine only. Payload files can contain
            # credentials in arbitrary tool output and are deliberately excluded.
            paths = list(islice(self.diagnostic_root.glob("*/trace.jsonl"), 65))
            if len(paths) > 64:
                self.ledger.count("diagnostics", dropped=1)
            for path in sorted(paths[:64]):
                if self._diagnostic_processing_stopped(deadline):
                    break
                if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(self.diagnostic_root.resolve()):
                    self.ledger.count("diagnostics", rejected=1)
                    continue
                size = path.stat().st_size
                if size > self.profile.max_payload_bytes or retained_bytes + size > self.profile.max_retained_bytes:
                    self.ledger.count("diagnostics", dropped=1)
                    continue
                raw = path.read_bytes()
                retained_bytes += len(raw)
                self.ledger.count("diagnostics", received_bytes=len(raw))
                for line in raw.splitlines():
                    if self._diagnostic_processing_stopped(deadline):
                        break
                    if line.strip():
                        seen += int(self._record_json("diagnostics", line))
            states = list(islice(self.diagnostic_root.glob("*/state.json"), 65))
            if len(states) > 64:
                self.ledger.count("diagnostics", dropped=1)
            for path in sorted(states[:64]):
                if self._diagnostic_processing_stopped(deadline):
                    break
                if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(self.diagnostic_root.resolve()):
                    self.ledger.count("diagnostics", rejected=1)
                    continue
                size = path.stat().st_size
                if size > self.profile.max_payload_bytes or retained_bytes + size > self.profile.max_retained_bytes:
                    self.ledger.count("diagnostics", dropped=1)
                    continue
                raw = path.read_bytes()
                retained_bytes += len(raw)
                self.ledger.count("diagnostics", received_bytes=len(raw))
                graph_records += self._retain_diagnostic_graph(raw, deadline=deadline)
            self.ledger.sources["diagnostics"]["reduced_graph"] = {
                "state": "retained" if graph_records else "unavailable", "retained_events": graph_records,
                "reason": None if graph_records else "stock_reduced_graph_not_available",
                "reduction_attempted": self._diagnostic_reduction_attempted}
            health = self.ledger.sources["diagnostics"]
            if health["parse_errors"] or health["rejected"] or health["dropped"] or health["partial"]:
                self.ledger.state("diagnostics", "partial", health.get("reason") or "diagnostic_bundle_partially_retained")
            else:
                self.ledger.state("diagnostics", "settled" if seen or graph_records else "unavailable",
                    None if seen or graph_records else "stock_diagnostic_bundle_not_written")
        except OSError:
            self.ledger.state("diagnostics", "partial", "stock_diagnostic_bundle_unreadable")
        finally:
            if not self._dispose_diagnostics():
                self.ledger.count("diagnostics", partial=1)
                self.ledger.state("diagnostics", "partial", "sensitive_diagnostic_cleanup_failed")

    def _dispose_diagnostics(self):
        """Bound private-tree deletion; keep failed cleanup locally retryable."""
        if self.diagnostic_root is None:
            return True
        timeout = max(0.1, self.profile.flush_timeout_seconds)
        # A filesystem unlink may block independently of a Python deadline.
        # The helper receives only this invocation's private directory path;
        # no payload, subprocess output or private path enters sealed evidence.
        script = ("import os,shutil,sys\n"
                  "try: shutil.rmtree(sys.argv[1])\n"
                  "except FileNotFoundError:\n"
                  " if os.path.lexists(sys.argv[1]): raise\n")
        reason = None
        try:
            completed = subprocess.run([sys.executable, "-I", "-c", script, str(self.diagnostic_root)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=timeout, check=False)
            if completed.returncode != 0:
                reason = "diagnostic_cleanup_failed"
        except subprocess.TimeoutExpired:
            reason = "diagnostic_cleanup_timeout"
        except OSError:
            reason = "diagnostic_cleanup_unavailable"
        if not self._finished:
            self.ledger.sources["diagnostics"]["cleanup"] = {
                "state": "removed" if reason is None else "incomplete",
                "reason": reason, "budget_seconds": timeout}
        if reason is None:
            self.diagnostic_root = None
            return True
        return False

    def finish(self, stdout=None, stderr=None, rollout_record=None, process_status="completed"):
        with self._lock:
            if self._manifest is not None:
                return json.loads(json.dumps(self._manifest))
            if not self._started:
                self.start()
            self._finishing = True
            self._diagnostic_cancelled = (process_status.get("status") if isinstance(process_status, dict)
                                          else process_status) == "cancelled"
            self._progress("drain")
            with _preserve_source_problems(self.ledger, "stdout", "stderr"):
                self._finish_stream("stdout", stdout)
                self._finish_stream("stderr", stderr)
            self._progress("flush")
            if self.collector is not None:
                with _preserve_source_problems(self.ledger, "otel_logs", "otel_traces", "otel_metrics"):
                    self.collector.close()
            self._progress("rollout_settlement")
            with _preserve_source_problems(self.ledger, "rollout"):
                self._finish_rollout(rollout_record)
            with _preserve_source_problems(self.ledger, "diagnostics"):
                self._finish_diagnostics()
            sanitizer = Sanitizer(aliases=self.aliases, source="process")
            status = sanitizer.value(process_status if isinstance(process_status, dict) else {"status": process_status})
            with _preserve_source_problems(self.ledger, "process"):
                self.ledger.add("process", {"phase": "completion", **status})
                if self.ledger.sources["process"]["state"] not in {"partial", "failed"}:
                    self.ledger.state("process", "settled")
            if status.get("status") in {"cancelled", "timeout", "timed_out", "failed", "launch_failed"}:
                for source in ("stdout", "rollout"):
                    if self.ledger.sources[source]["state"] == "settled" and source == "stdout" and self._last_stdout_type not in {"turn.completed", "turn.failed"}:
                        self.ledger.count(source, partial=1)
                        self.ledger.state(source, "partial", "process_ended_without_terminal_event")
            self._progress("evidence_validation")
            self._finished = True
            self._manifest = self.ledger.seal(process_status=status)
            validate_manifest(self._manifest)
            self._progress("evidence_validation", sealed=True)
            return json.loads(json.dumps(self._manifest))

    def close(self):
        """Abort cleanup always drains receivers and disposes sensitive scratch."""
        if self._manifest is None:
            return self.finish(process_status="cancelled")
        self._dispose_diagnostics()
        return json.loads(json.dumps(self._manifest))

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        if self._manifest is None:
            self.finish(process_status="failed" if exc_type is not None else "cancelled")
        else:
            self._dispose_diagnostics()
