"""Isolated supported native capture; never invokes a scored runner/scorer."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import os
import signal
import tempfile
from types import MappingProxyType
from collections.abc import Mapping
from .collector import LoopbackTraceCollector, observation_overrides
from .models import RuntimeEquivalence, ProviderRequestFieldAvailability as Field
from .metrics import observed
from ...runtime.identity.runtime_version import retained_runtime_version
from .runtime_identity import cli_runtime_version, runtime_version as validate_runtime_version


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ReplayStartingState:
    """Exact explicitly selected starting files, captured before scored execution."""
    files: Mapping[str, bytes]
    state_id: str

    def __post_init__(self):
        copied = dict(self.files)
        for name, raw in copied.items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or not path.parts or type(raw) is not bytes:
                raise ValueError("unsafe replay starting file")
        expected = digest(json.dumps({k:digest(v) for k,v in sorted(copied.items())},sort_keys=True).encode())
        if self.state_id != expected:
            raise ValueError("starting-state identity mismatch")
        object.__setattr__(self, "files", MappingProxyType(copied))

    @classmethod
    def capture(cls, root, relative_files):
        root = Path(root).resolve()
        values = {}
        for name in relative_files:
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError("starting state requires ordinary files inside its declared root")
            values[name] = path.read_bytes()
        identity = digest(json.dumps({k:digest(v) for k,v in sorted(values.items())},sort_keys=True).encode())
        return cls(values, identity)


@dataclass(frozen=True)
class ReplayCaptureOptions:
    executable: Path
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    starting_state: ReplayStartingState
    expected_configuration: Mapping
    observed_configuration: Mapping
    capabilities: object
    runtime_version: str
    expected_binary_sha256: str
    timeout_seconds: int = 60

    def __post_init__(self):
        if type(self.starting_state) is not ReplayStartingState:
            raise TypeError("replay requires retained/restorable starting authority")
        validate_runtime_version(self.runtime_version)
        if not self.argv or self.argv[0] != str(self.executable):
            raise ValueError("exact runtime launch argv required")
        if not 1 <= self.timeout_seconds <= 300:
            raise ValueError("bounded replay timeout required")
        if any("otel." in arg for arg in self.argv):
            raise ValueError("scored launch argv must not carry replay instrumentation")
        if any(type(v) is not str or not v for v in self.argv):
            raise ValueError("launch argv requires nonempty strings")
        object.__setattr__(self, "argv", tuple(self.argv))
        if any(type(k) is not str or type(v) is not str for k, v in self.environment.items()):
            raise ValueError("launch environment requires strings")
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        object.__setattr__(self, "expected_configuration", MappingProxyType(dict(self.expected_configuration)))
        object.__setattr__(self, "observed_configuration", MappingProxyType(dict(self.observed_configuration)))


def capture_replay(options, *, validation_id, prompt, case_input, temporary_root):
    """Return sanitized spans only; stdout, response and prompt are not retained."""
    if type(options) is not ReplayCaptureOptions:
        raise TypeError("typed replay options required")
    actual_binary = digest(options.executable.resolve().read_bytes())
    expected = observed(options.expected_binary_sha256, "accepted_runtime_binary")
    actual = observed(actual_binary, "observed_runtime_binary")
    version = subprocess.run([str(options.executable), "--version"], capture_output=True, timeout=10,
        env=dict(options.environment))
    try:
        observed_version = cli_runtime_version(version.stdout.decode().strip()) if version.returncode == 0 else None
    except (ValueError, UnicodeError):
        observed_version = None
    exact = actual_binary == options.expected_binary_sha256 and observed_version == options.runtime_version
    runtime = RuntimeEquivalence("exact_stock" if exact else "non_comparable", expected, actual,
        observed(retained_runtime_version(observed_version), "observed_runtime_version") if observed_version is not None else Field.unavailable("runtime_version_not_observed"),
        Field.unavailable("stock_has_no_patch"), "stock",
        reasons=() if exact else ("runtime_binary_or_version_mismatch",))
    if not exact:
        return (), runtime, "unavailable", ("runtime_binary_or_version_mismatch",)
    # Caller-owned accepted starting authority is restored into a disposable copy.
    # An independent CODEX_HOME prevents replay rollout/profile side effects from
    # reaching the selected scored user's session. No credential material is retained.
    with tempfile.TemporaryDirectory(dir=temporary_root, prefix="replay-") as directory:
        root = Path(directory)
        work = root / "workspace"
        home = root / "codex-home"
        work.mkdir(); home.mkdir()
        for name, raw in options.starting_state.files.items():
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        environment = dict(options.environment)
        environment["CODEX_HOME"] = str(home)
        with LoopbackTraceCollector() as collector:
            overrides = observation_overrides(validation_id, collector.endpoint)
            args = [str(options.executable)]
            for setting in overrides:
                args.extend(("-c", setting))
            args.extend(options.argv[1:])
            process = None
            try:
                process = subprocess.Popen(args, stdin=subprocess.PIPE, cwd=work,
                    env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=os.name == "posix")
                process.communicate(input=prompt + b"\n\n" + case_input, timeout=options.timeout_seconds)
                status = "completed" if process.returncode == 0 else "failed"
                limitations = () if process.returncode == 0 else ("replay_process_non_success",)
            except subprocess.TimeoutExpired:
                status, limitations = "failed", ("replay_timeout",)
            except OSError:
                status, limitations = "failed", ("replay_process_launch_failed",)
            finally:
                if process is not None:
                    if os.name == "posix":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    elif process.poll() is None:
                        process.kill()
                    process.wait()
            return collector.spans, runtime, status, limitations
