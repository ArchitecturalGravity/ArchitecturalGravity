"""Runtime-owned pre-invocation authority and selected-host replay transport."""
from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import MappingProxyType
from .capture import digest
from .comparison import configuration_values
from .metrics import observed
from .models import RuntimeEquivalence, ProviderRequestFieldAvailability as Field
from .capabilities import admit_controlled_probe
from ...runtime.identity.runtime_version import retained_runtime_version
from .runtime_identity import cli_runtime_version, runtime_version as validate_runtime_version

_GUARD = object()


@dataclass(frozen=True)
class HostTransport:
    launch_mode: str
    prefix: tuple[str, ...]
    environment: object

    def request(self, payload, *, timeout=70):
        # Both collector and worker execute in the selected host. In WSL the
        # collector endpoint is WSL loopback, never Windows localhost forwarding.
        root = Path(__file__).parent
        code = (root / "collector.py").read_text() + "\n" + (root / "host_worker.py").read_text()
        if self.launch_mode == "wsl":
            command = (*self.prefix, "sh", "-lc",
                'linux_home="$(getent passwd "$(id -u)" | cut -d: -f6)"; '
                'if [ -n "$linux_home" ]; then export HOME="$linux_home"; fi; exec python3 -c "$1"',
                "agmark-replay-host", code)
        else:
            command = (sys.executable, "-c", code)
        result = subprocess.run(command, input=json.dumps(payload).encode(),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=dict(self.environment), timeout=timeout)
        if result.returncode or len(result.stdout) > 16 * 1024 * 1024:
            raise ValueError("selected_host_operation_failed")
        document = json.loads(result.stdout)
        if "error" in document:
            raise ValueError("selected_host_" + document["error"])
        return document["result"]


@dataclass(frozen=True)
class StartupRecord:
    observation_id: str
    generation_id: str
    frame_sha256: str
    snapshot_bytes: bytes
    transport: HostTransport
    _guard: object

    def revalidate(self):
        if self._guard is not _GUARD:
            raise ValueError("startup authority must be captured by runtime before invocation")
        snapshot = json.loads(self.snapshot_bytes)
        cli_runtime_version(snapshot["version"])
        return snapshot

    def public_document(self):
        s = self.revalidate()
        # Paths, argv, environment values and authentication are transient only.
        return {"observation_id": self.observation_id, "generation_id": self.generation_id,
            "frame_sha256": self.frame_sha256, "phase": "before_scored_invocation",
            "runtime_binary_sha256": s["binary_sha256"], "runtime_version": "codex-cli " + retained_runtime_version(s["version"]),
            "launch_mode": self.transport.launch_mode, "platform": s["platform"],
            "workspace_state_id": s["workspace_state_id"],
            "ambient_state_validation": "transient_equality_only"}

    def configuration(self, boundary, *, prompt_sha256, input_sha256, runner_registration_sha256, observed_launch=False, ambient_equivalent=True):
        s = self.revalidate()
        # Hash the observed determinants of tool/feature/permission configuration.
        # This is configuration-input equivalence, never provider trajectory proof.
        controls = digest(json.dumps(boundary.to_dict()["controls"], sort_keys=True).encode())
        values = configuration_values(boundary, prompt_sha256=prompt_sha256, input_sha256=input_sha256,
            runner_registration_sha256=runner_registration_sha256, runtime_binary_sha256=s["binary_sha256"],
            workspace_state_id=s["workspace_state_id"], supplemental={
                "tools_sha256": controls, "features_sha256": controls, "permissions_sha256": controls,
                "ambient_configuration_equal": ambient_equivalent, "repository_state_id": s["workspace_state_id"]})
        if observed_launch:
            values["runtime_version"] = observed(retained_runtime_version(s["version"]), "selected_host_runtime")
            if "--model" in s["args"]:
                values["model"] = observed(s["args"][s["args"].index("--model") + 1], "observed_launch_model")
        values["environment_sha256"] = observed(digest(json.dumps({"platform": s["platform"],
            "launch_mode": self.transport.launch_mode}, sort_keys=True).encode()), "controlled_host_characteristics")
        values["launch_mode"] = observed(self.transport.launch_mode, "pre_invocation_launch")
        if values["service_tier"].availability == "unavailable":
            values["service_tier"] = observed("not_explicitly_selected", "observed_launch_selection_not_effective_provider_tier")
        return values

    def current(self):
        expected = self.revalidate()
        actual = self.transport.request({"operation": "snapshot", "executable": expected["executable"],
            "args": expected["args"], "work_parent": expected["work_parent"], "profile_home": expected["retained_home"]})
        cli_runtime_version(actual["version"])
        actual.update(home=expected["home"], retained_home=expected["retained_home"], retained_owner=expected["retained_owner"])
        return actual

    def capabilities(self):
        snapshot = self.revalidate()
        probe = self.transport.request({"operation": "probe", "snapshot": snapshot})
        return admit_controlled_probe(probe, binary_sha256=snapshot["binary_sha256"],
            runtime_version=cli_runtime_version(snapshot["version"]))

    def capture(self, validation_id, frame, timeout):
        expected = self.revalidate()
        actual = self.current()
        a, b = observed(expected["binary_sha256"], "pre_invocation_binary"), observed(actual["binary_sha256"], "replay_binary")
        exact = a.value == b.value and actual["version"] == expected["version"]
        runtime = RuntimeEquivalence("exact_stock" if exact else "non_comparable", a, b,
            observed(retained_runtime_version(actual["version"]), "selected_host_runtime"), Field.unavailable("stock_has_no_patch"), "stock",
            reasons=() if exact else ("runtime_binary_or_version_changed",))
        if actual != expected:
            return (), runtime, "unavailable", ("replay_starting_configuration_changed",), actual
        result = self.transport.request({"operation": "capture", "snapshot": expected,
            "validation_id": validation_id, "frame_base64": base64.b64encode(frame).decode(),
            "timeout": timeout}, timeout=timeout + 20)
        reasons = (result["reason"],) if result.get("reason") else ()
        if result.get("rejected_payloads"):
            reasons += ("rejected_capture_payload",)
        return tuple(result["spans"]), runtime, result["status"], reasons, result["observed"]


class StartupCollector:
    """Only an actual registered runner invocation can populate this collector."""
    def __init__(self):
        self.records = {}
        self.diagnostics = {}

    def __call__(self, *, observation_id, generation_id, argv, environment, cwd,
                 runtime_version, launch_metadata, framed_request_sha256, external_provider_submission):
        try:
            if not external_provider_submission:
                return
            if observation_id in self.records:
                raise ValueError("duplicate_startup")
            validate_runtime_version(runtime_version)
            mode = launch_metadata["mode"]
            if mode == "native":
                if any(Path(cwd).iterdir()):
                    raise ValueError("nonempty_starting_workspace_not_supported")
                executable, args, prefix = argv[0], list(argv[1:]), ()
                parent = str(Path(cwd).parent)
            elif mode == "wsl":
                # The registered wrapper creates an empty /tmp workspace inside WSL.
                prefix = tuple(argv[:4])
                if prefix[1:2] != ("--distribution",) or prefix[-1] != "--exec":
                    raise ValueError("unsupported_wsl_launch")
                executable = launch_metadata["executable"]
                args = ["exec", "--model", argv[9], "--approve-for-me", "--ignore-user-config",
                        "--skip-git-repo-check", "--color", "never", "--json", *argv[10:], "-"]
                parent = None
            else:
                raise ValueError("unsupported_launch_mode")
            host = HostTransport(mode, prefix, MappingProxyType(dict(environment)))
            snapshot = host.request({"operation": "snapshot", "executable": executable,
                "args": args, "work_parent": parent, "retain": True}, timeout=20)
            try:
                if cli_runtime_version(snapshot["version"]) != runtime_version:
                    raise ValueError("startup_runtime_identity_changed")
            except (ValueError, KeyError, TypeError):
                host.request({"operation": "cleanup", "retained_home": snapshot["retained_home"],
                    "retained_owner": snapshot["retained_owner"]}, timeout=10)
                raise
            record = StartupRecord(observation_id, generation_id, framed_request_sha256,
                json.dumps(snapshot, sort_keys=True).encode(), host, _GUARD)
            record.revalidate()
            self.records[observation_id] = record
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
            self.diagnostics[observation_id] = "pre_invocation_startup_capture_unavailable"

    def close(self):
        for record in self.records.values():
            snapshot = record.revalidate()
            try:
                record.transport.request({"operation": "cleanup", "retained_home": snapshot["retained_home"],
                    "retained_owner": snapshot["retained_owner"]}, timeout=10)
            except (ValueError, OSError, subprocess.SubprocessError):
                self.diagnostics[record.observation_id] = "startup_disposal_unavailable"
